"""No-tool adapter for Hermes v0.20.6's low-level auxiliary inference API."""

from __future__ import annotations

import json
from contextlib import nullcontext
from dataclasses import dataclass

from .execution import NativeExecutionError, RUNTIME_BOUNDARY

ALLOWED_TASKS = frozenset({
    "charlie_native_builder",
    "charlie_native_security_reviewer",
    "charlie_native_functional_reviewer",
    "charlie_native_challenge_reviewer",
})


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
    except (TypeError, ValueError) as exc:
        raise NativeExecutionError("native_model_response_invalid") from exc
    if not isinstance(parsed, dict):
        raise NativeExecutionError("native_model_response_invalid")
    return parsed


class HermesAuxiliaryModel:
    """One structured completion at a time, with no model-visible tools or secrets."""

    def __init__(self, *, profile_home, call=None, provider="", model="", profile="default"):
        self.profile_home = str(profile_home)
        self.provider = str(provider or "")
        self.model = str(model or "")
        self.profile = str(profile or "default")
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

    def complete_structured(self, *, instructions, input, json_schema, schema_name,
                            purpose, task, temperature=0.0, max_tokens=4000,
                            timeout=120, **_ignored):
        if task not in ALLOWED_TASKS:
            raise NativeExecutionError("native_model_task_invalid")
        messages = [{"role": "system", "content": str(instructions)}]
        for item in list(input or []):
            messages.append({"role": "user", "content": str(dict(item).get("text") or "")})
        kwargs = dict(
            task=task, messages=messages, temperature=float(temperature),
            max_tokens=min(int(max_tokens), 6000), tools=[], timeout=min(float(timeout), 120),
            extra_body={"response_format": {"type": "json_schema", "json_schema": {
                "name": str(schema_name), "strict": True, "schema": dict(json_schema),
            }}},
        )
        if self.provider:
            kwargs["provider"] = self.provider
        if self.model:
            kwargs["model"] = self.model
        last = None
        for _ in range(2):
            try:
                with self._profile_scope():
                    raw = self.call(**kwargs)
                parsed = _parsed_json(getattr(raw, "content", raw))
                provider = str(getattr(raw, "provider", "") or self.provider).strip()
                model = str(getattr(raw, "model", "") or self.model).strip()
                if not provider or not model:
                    raise NativeExecutionError("native_runtime_identity_missing")
                return StructuredResult(parsed, provider, model, "standalone", {
                    "runtime_boundary": RUNTIME_BOUNDARY, "task": task,
                    "purpose": str(purpose), "schema_name": str(schema_name),
                    "profile": self.profile, "tools_count": 0,
                })
            except NativeExecutionError:
                raise
            except Exception as exc:
                last = exc
        raise NativeExecutionError("hermes_auxiliary_inference_failed") from last


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
