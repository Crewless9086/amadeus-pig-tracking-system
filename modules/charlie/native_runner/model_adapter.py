"""No-tool adapter for Hermes v0.20.6's low-level auxiliary inference API."""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from contextlib import nullcontext
from dataclasses import dataclass

from .execution import NativeExecutionError, RUNTIME_BOUNDARY

ALLOWED_TASKS = frozenset({
    "charlie_native_builder",
    "charlie_native_security_reviewer",
    "charlie_native_functional_reviewer",
    "charlie_native_challenge_reviewer",
})
DEFAULT_PROVIDER = "openrouter"
DEFAULT_MODEL = "openai/gpt-5-mini"
STRICT_REQUEST_BYTES = 340000
STRICT_OUTPUT_TOKENS = 6000
STRICT_BASE_URL = "https://openrouter.ai/api/v1/"
_FAILURE_STAGES = frozenset({"resolution", "transport_setup", "reservation",
                             "sdk_submission", "transport_cleanup", "legacy_call"})
_FAILURE_KINDS = frozenset({"unexpected_error", "timeout", "connection", "http_status"})
_FAILURE_STATUSES = frozenset({400, 401, 402, 403, 404, 408, 409, 422, 429,
                              500, 502, 503, 504})


class NativeModelFailure(NativeExecutionError):
    """Safe diagnostics separate from the existing retry-suppression reason."""

    def __init__(self, *, stage, kind="unexpected_error", status=None):
        super().__init__("hermes_auxiliary_inference_failed")
        self.failure_stage = stage
        self.failure_kind = kind
        self.failure_status = status


def model_failure_diagnostics(exc):
    """Only exact adapter failures with freshly validated scalar fields escape."""
    if type(exc) is not NativeModelFailure:
        return {}
    stage, kind, status = (getattr(exc, field, None) for field in
                           ("failure_stage", "failure_kind", "failure_status"))
    if (type(stage) is not str or stage not in _FAILURE_STAGES
            or type(kind) is not str or kind not in _FAILURE_KINDS
            or (status is not None and (type(status) is not int or status not in _FAILURE_STATUSES))
            or (status is not None and (stage != "sdk_submission" or kind != "http_status"))
            or (stage != "sdk_submission" and kind != "unexpected_error")):
        return {}
    result = {"model_failure_stage": stage, "model_failure_kind": kind}
    if status is not None:
        result["model_failure_status"] = status
    return result


def _model_failure(stage, exc):
    # Do not inspect exception text, bodies, response headers, request IDs or URLs.
    # Entering the SDK is not evidence of delivery or model execution.
    kind, status = "unexpected_error", None
    if stage == "sdk_submission":
        import openai
        if isinstance(exc, (TimeoutError, getattr(openai, "APITimeoutError", type(None)))):
            kind = "timeout"
        elif isinstance(exc, (ConnectionError, getattr(openai, "APIConnectionError", type(None)))):
            kind = "connection"
        elif isinstance(exc, getattr(openai, "APIStatusError", ())):
            kind = "http_status"
            value = getattr(exc, "status_code", None)
            if type(value) is int and value in _FAILURE_STATUSES:
                status = value
    return NativeModelFailure(stage=stage, kind=kind, status=status)


def _wire_schema_name(name):
    # Internal dotted role identities remain unchanged in audit records. Restrict
    # input first; never turn arbitrary/private input into a provider label.
    if (type(name) is not str or not 1 <= len(name) <= 64
            or not re.fullmatch(r"[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*", name)):
        raise NativeExecutionError("native_model_schema_name_invalid")
    if "." not in name:
        return name
    # Preserve a readable prefix while keeping dotted and underscore labels distinct.
    return name.replace(".", "_")[:47] + "_" + hashlib.sha256(name.encode("ascii")).hexdigest()[:16]


def _validate_request_schema(schema):
    """Check the native root-object envelope, without rewriting any constraint."""
    if not isinstance(schema, dict) or schema.get("type") != "object":
        raise NativeExecutionError("native_model_request_schema_invalid")
    properties, required = schema.get("properties"), schema.get("required")
    if (not isinstance(properties, dict) or not isinstance(required, list)
            or any(type(key) is not str for key in properties)
            or any(type(key) is not str for key in required)
            or len(set(required)) != len(required) or set(required) != set(properties)
            or schema.get("additionalProperties") is not False):
        raise NativeExecutionError("native_model_request_schema_invalid")


@dataclass(frozen=True)
class StructuredResult:
    parsed: dict
    provider: str
    model: str
    agent_id: str
    audit: dict


def _parsed_json(value):
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if len(lines) > 2 else []).strip()
    try:
        parsed = json.loads(text)
    except (TypeError, ValueError):
        raise NativeExecutionError("native_model_response_invalid") from None
    if not isinstance(parsed, dict):
        raise NativeExecutionError("native_model_response_invalid")
    return parsed


def _validate_schema(value, schema):
    """Validate the bounded JSON-schema subset used by native runner calls."""
    if not isinstance(value, dict) or schema.get("type") != "object":
        raise NativeExecutionError("native_model_schema_invalid")
    required = set(schema.get("required") or ())
    properties = dict(schema.get("properties") or {})
    if not required.issubset(value):
        raise NativeExecutionError("native_model_schema_invalid")
    if schema.get("additionalProperties") is False and set(value) - set(properties):
        raise NativeExecutionError("native_model_schema_invalid")
    for key, item in value.items():
        rule = dict(properties.get(key) or {})
        if "const" in rule and item != rule["const"]:
            raise NativeExecutionError("native_model_schema_invalid")
        if "enum" in rule and item not in rule["enum"]:
            raise NativeExecutionError("native_model_schema_invalid")
        expected = rule.get("type")
        valid = {"string": isinstance(item, str), "array": isinstance(item, list),
                 "object": isinstance(item, dict), "integer": isinstance(item, int) and not isinstance(item, bool),
                 "boolean": isinstance(item, bool)}.get(expected, True)
        if not valid:
            raise NativeExecutionError("native_model_schema_invalid")
    return value


class HermesAuxiliaryModel:
    """One structured completion at a time, with no model-visible tools or secrets."""

    def __init__(self, *, profile_home, call=None, provider=DEFAULT_PROVIDER,
                 model=DEFAULT_MODEL, profile="default", strict_budget=False,
                 before_attempt=None, max_attempts=None):
        self.profile_home = str(profile_home)
        self.provider = str(provider or "")
        self.model = str(model or "")
        self.profile = str(profile or "default")
        self.strict_budget = strict_budget
        self.before_attempt = before_attempt
        self.max_attempts = (1 if strict_budget else 2) if max_attempts is None else max_attempts
        if type(strict_budget) is not bool or type(self.max_attempts) is not int:
            raise NativeExecutionError("native_model_budget_configuration_invalid")
        if strict_budget:
            self._check_strict_configuration()
            # call_llm has reactive retries/fallback and can omit max_tokens.
            # Its public client resolver performs no completion. Strict calls use
            # the resolved SDK directly with their own one-request transport.
            if call is not None:
                raise NativeExecutionError("native_model_strict_transport_required")
            try:
                from agent.auxiliary_client import resolve_provider_client
            except ImportError as exc:
                raise NativeExecutionError("hermes_auxiliary_inference_unavailable") from exc
            call = resolve_provider_client
        elif self.max_attempts not in (1, 2):
            raise NativeExecutionError("native_model_budget_configuration_invalid")
        if call is None:
            try:
                from agent.auxiliary_client import call_llm
            except ImportError as exc:
                raise NativeExecutionError("hermes_auxiliary_inference_unavailable") from exc
            call = call_llm
        self.call = call

    def _profile_scope(self):
        try:
            from hermes_cli.plugins import _plugin_home_scope
        except ImportError:
            if self.call.__module__.startswith("agent."):
                raise NativeExecutionError("hermes_profile_scope_unavailable")
            return nullcontext()
        return _plugin_home_scope(self.profile_home)

    def _check_strict_configuration(self):
        if (self.provider != DEFAULT_PROVIDER or self.model != DEFAULT_MODEL
                or self.max_attempts != 1 or not callable(self.before_attempt)):
            raise NativeExecutionError("native_model_budget_configuration_invalid")

    def _strict_complete(self, *, messages, json_schema, schema_name, purpose,
                         task, max_tokens, timeout):
        self._check_strict_configuration()
        if type(max_tokens) is not int or not 1 <= max_tokens <= STRICT_OUTPUT_TOKENS:
            raise NativeExecutionError("native_model_output_budget_invalid")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 120:
            raise NativeExecutionError("native_model_timeout_invalid")
        # This is the complete canonical JSON body, including schema and routing
        # controls. Task/purpose are local audit labels, not provider parameters.
        body = {
            "model": DEFAULT_MODEL, "messages": messages, "tools": [],
            "max_tokens": max_tokens,
            "response_format": {"type": "json_schema", "json_schema": {
                "name": _wire_schema_name(schema_name), "strict": True, "schema": dict(json_schema),
            }},
            "provider": {"allow_fallbacks": False, "require_parameters": True,
                         "max_price": {"prompt": 0.25, "completion": 2.00}},
            "reasoning": {"effort": "low"},
        }
        try:
            request = json.dumps(body, sort_keys=True, separators=(",", ":"),
                                 ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (TypeError, ValueError, UnicodeError):
            raise NativeExecutionError("native_model_request_invalid") from None
        if len(request) > STRICT_REQUEST_BYTES:
            raise NativeExecutionError("native_model_request_too_large")
        # Detach caller-owned schema/input containers before the durable callback.
        body = json.loads(request)
        request_sha256 = hashlib.sha256(request).hexdigest()
        try:
            import httpx
            from openai import OpenAI
        except ImportError as exc:
            raise NativeExecutionError("native_model_strict_transport_unavailable") from exc
        stage = "resolution"
        try:
            with self._profile_scope():
                client, model = self.call(provider=DEFAULT_PROVIDER, model=DEFAULT_MODEL,
                                          task=task, async_mode=False)
                if (type(client) is not OpenAI or model != DEFAULT_MODEL
                        or str(client.base_url) != STRICT_BASE_URL):
                    raise NativeExecutionError("native_runtime_route_mismatch")
                # Do not modify/close Hermes' parent client. A fresh transport has
                # no SDK/HTTP retries, redirects, environment proxies or TLS override.
                stage = "transport_setup"
                with httpx.Client(transport=httpx.HTTPTransport(retries=0, verify=True, trust_env=False),
                                  follow_redirects=False, trust_env=False) as transport:
                    bounded = client.with_options(max_retries=0, timeout=timeout,
                                                  http_client=transport)
                    if (type(bounded) is not OpenAI or bounded.max_retries != 0
                            or str(bounded.base_url) != STRICT_BASE_URL):
                        raise NativeExecutionError("native_model_strict_transport_unproven")
                    # A callback failure prevents submission. After it succeeds,
                    # errors/invalid responses never refund or retry this attempt.
                    stage = "reservation"
                    reserved = self.before_attempt(request_sha256=request_sha256,
                                                   input_bytes=len(request),
                                                   max_tokens=max_tokens, task=task)
                    if reserved is False:
                        raise NativeExecutionError("native_model_reservation_refused")
                    stage = "sdk_submission"
                    raw = bounded.chat.completions.create(
                        model=body["model"], messages=body["messages"], tools=[],
                        max_tokens=body["max_tokens"], response_format=body["response_format"],
                        extra_body={"provider": body["provider"], "reasoning": body["reasoning"]},
                    )
                    stage = "transport_cleanup"
        except NativeExecutionError:
            raise
        except Exception as exc:
            raise _model_failure(stage, exc) from None
        if getattr(raw, "model", None) != DEFAULT_MODEL:
            raise NativeExecutionError("native_runtime_route_mismatch")
        choices = getattr(raw, "choices", None)
        if not isinstance(choices, (list, tuple)) or len(choices) != 1:
            raise NativeExecutionError("native_model_response_invalid")
        message = getattr(choices[0], "message", None)
        if getattr(message, "tool_calls", None):
            raise NativeExecutionError("native_model_response_invalid")
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise NativeExecutionError("native_model_response_invalid")
        parsed = _validate_schema(_parsed_json(content), body["response_format"]["json_schema"]["schema"])
        usage = getattr(raw, "usage", None)
        safe_usage = {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = getattr(usage, key, None)
            if type(value) is int and value >= 0:
                safe_usage[key] = value
        if safe_usage.get("completion_tokens", 0) > max_tokens:
            raise NativeExecutionError("native_model_output_budget_exceeded")
        cost = getattr(usage, "cost", None)
        if type(cost) in (int, float) and math.isfinite(cost) and cost >= 0:
            safe_usage["cost_usd"] = cost
        request_id = getattr(raw, "id", None)
        if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9._:-]{1,200}", request_id):
            request_id = None
        invocation_id = "native-" + uuid.uuid4().hex
        return StructuredResult(parsed, DEFAULT_PROVIDER, DEFAULT_MODEL, request_id or invocation_id, {
            "runtime_boundary": RUNTIME_BOUNDARY, "task": task, "purpose": str(purpose),
            "schema_name": str(schema_name), "profile": self.profile, "tools_count": 0,
            "strict_budget": True, "attempt_count": 1, "request_sha256": request_sha256,
            "input_bytes": len(request), "max_tokens": max_tokens,
            "provider_request_id": request_id, "invocation_id": invocation_id, "usage": safe_usage,
        })

    def complete_structured(self, *, instructions, input, json_schema, schema_name,
                            purpose, task, temperature=0.0, max_tokens=4000,
                            timeout=120, **_ignored):
        if task not in ALLOWED_TASKS:
            raise NativeExecutionError("native_model_task_invalid")
        _wire_schema_name(schema_name)
        _validate_request_schema(json_schema)
        messages = [{"role": "system", "content": str(instructions)}]
        for item in list(input or []):
            messages.append({"role": "user", "content": str(dict(item).get("text") or "")})
        if self.strict_budget:
            if _ignored:
                raise NativeExecutionError("native_model_request_options_invalid")
            return self._strict_complete(messages=messages, json_schema=json_schema,
                                         schema_name=schema_name, purpose=purpose, task=task,
                                         max_tokens=max_tokens, timeout=timeout)
        kwargs = dict(
            task=task, messages=messages, temperature=float(temperature),
            max_tokens=min(int(max_tokens), 6000), tools=[], timeout=min(float(timeout), 120),
            extra_body={"response_format": {"type": "json_schema", "json_schema": {
                "name": _wire_schema_name(schema_name), "strict": True, "schema": dict(json_schema),
            }}},
        )
        if self.provider:
            kwargs["provider"] = self.provider
        if self.model:
            kwargs["model"] = self.model
        last = None
        for _ in range(self.max_attempts):
            try:
                route_info = {}
                with self._profile_scope():
                    raw = self.call(route_info=route_info, **kwargs)
                choices = getattr(raw, "choices", None)
                if not isinstance(choices, (list, tuple)) or not choices:
                    raise NativeExecutionError("native_model_response_invalid")
                message = getattr(choices[0], "message", None)
                content = getattr(message, "content", None) if message is not None else None
                if not isinstance(content, str) or not content.strip():
                    raise NativeExecutionError("native_model_response_invalid")
                parsed = _validate_schema(_parsed_json(content), json_schema)
                provider = str(route_info.get("provider") or "").strip()
                model = str(route_info.get("model") or "").strip()
                if not provider or not model:
                    raise NativeExecutionError("native_runtime_identity_missing")
                if provider != self.provider or model != self.model:
                    raise NativeExecutionError("native_runtime_route_mismatch")
                return StructuredResult(parsed, provider, model, "standalone", {
                    "runtime_boundary": RUNTIME_BOUNDARY, "task": task,
                    "purpose": str(purpose), "schema_name": str(schema_name),
                    "profile": self.profile, "tools_count": 0,
                })
            except NativeExecutionError:
                raise
            except Exception as exc:
                last = exc
        raise _model_failure("legacy_call", last) from None


def run_schema_canary(model):
    result = model.complete_structured(
        instructions="Return only the requested harmless JSON object. Use no tools.",
        input=[{"type": "text", "text": "Return {\"status\":\"READY\"}."}],
        json_schema={"type": "object", "additionalProperties": False,
                     "required": ["status"], "properties": {"status": {"const": "READY"}}},
        schema_name="charlie.native.canary.v1", purpose="charlie.native.canary",
        task="charlie_native_builder", max_tokens=64, timeout=30,
    )
    if result.parsed != {"status": "READY"} or result.audit.get("tools_count") != 0:
        raise NativeExecutionError("hermes_auxiliary_canary_failed")
    return {"status": "READY", "provider": result.provider, "model": result.model,
            "tools_count": 0}
