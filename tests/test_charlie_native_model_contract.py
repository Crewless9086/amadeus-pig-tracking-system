"""Real SDK serialization/error handling against an in-memory HTTP transport only."""
import hashlib
import json
import re
import socket
import sys
import traceback
from contextlib import nullcontext
from types import ModuleType, SimpleNamespace

import httpx
import openai
import pytest

from modules.charlie.native_runner.execution import (
    HermesIndependentReviewer, HermesStructuredPatchWorker, NativeExecutionError,
)
from modules.charlie.native_runner.model_adapter import (
    DEFAULT_MODEL, STRICT_BASE_URL, HermesAuxiliaryModel, NativeModelFailure,
    model_failure_diagnostics, run_schema_canary,
)
from modules.charlie.native_runner.schemas import NATIVE_PATCH_SCHEMA, NATIVE_REVIEW_SCHEMA


@pytest.fixture
def sdk(monkeypatch):
    calls, reservations, resolves, transports = [], [], [], []
    state = SimpleNamespace(status=200, error=None, resolution_error=None,
                            reservation_error=None, content={"ok": True})
    private = "synthetic-private-provider-content-91827"

    def reject_network(*args, **kwargs):
        pytest.fail("a real network connection was attempted")
    monkeypatch.setattr(socket, "create_connection", reject_network)
    monkeypatch.setattr(socket.socket, "connect", reject_network)

    def handler(request):
        body = json.loads(request.content)
        calls.append(body)
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", body["response_format"]["json_schema"]["name"])
        if state.error:
            raise state.error(private, request=request)
        if state.status != 200:
            return httpx.Response(state.status, json={"error": {"message": private,
                "code": private, "param": private}}, headers={"x-request-id": private,
                "authorization": private, "retry-after": "0"})
        content = state.content if isinstance(state.content, str) else json.dumps(state.content)
        return httpx.Response(200, json={"id": "gen-synthetic", "object": "chat.completion",
            "created": 1, "model": DEFAULT_MODEL,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content}}]})

    def transport(**options):
        transports.append(options)
        assert options == {"retries": 0, "verify": True, "trust_env": False}
        return httpx.MockTransport(handler)

    # The cached Hermes SDK client is never used for I/O or closed by the adapter.
    parent_http = httpx.Client(transport=httpx.MockTransport(reject_network), trust_env=False)
    parent = openai.OpenAI(api_key="synthetic-only", base_url=STRICT_BASE_URL,
                           http_client=parent_http)
    monkeypatch.setattr(httpx, "HTTPTransport", transport)
    aux = ModuleType("agent.auxiliary_client")
    def resolve(**kwargs):
        resolves.append(kwargs)
        if state.resolution_error:
            raise state.resolution_error
        return parent, DEFAULT_MODEL
    aux.resolve_provider_client = resolve
    monkeypatch.setitem(sys.modules, "agent", ModuleType("agent"))
    monkeypatch.setitem(sys.modules, "agent.auxiliary_client", aux)
    plugins = ModuleType("hermes_cli.plugins")
    plugins._plugin_home_scope = lambda home: nullcontext()
    monkeypatch.setitem(sys.modules, "hermes_cli", ModuleType("hermes_cli"))
    monkeypatch.setitem(sys.modules, "hermes_cli.plugins", plugins)
    def reserve(**row):
        reservations.append(row)
        if state.reservation_error:
            raise state.reservation_error
    model = HermesAuxiliaryModel(profile_home="synthetic", strict_budget=True, before_attempt=reserve)
    args = dict(instructions="synthetic", input=[], json_schema={"type": "object",
        "properties": {"ok": {"type": "boolean"}}, "required": ["ok"],
        "additionalProperties": False}, schema_name="synthetic.contract.v1",
        purpose="synthetic", task="charlie_native_builder", max_tokens=64)
    yield SimpleNamespace(model=model, args=args, state=state, calls=calls,
        reservations=reservations, resolves=resolves, transports=transports, private=private)
    parent.close()


def test_actual_builder_and_all_review_callers_pass_real_sdk_wire_contract(sdk):
    sdk.state.content = {"state": "BLOCKED", "context_paths": [], "unified_diff": "",
                         "test_proposal": [], "reason": "synthetic"}
    result = HermesStructuredPatchWorker(sdk.model).complete({"instruction": "synthetic"})
    assert result["worker_identity"].startswith("HNW-")
    names = ["charlie.native.patch.v1"]
    packet = {"candidate": {"pr_number": 1, "base_sha": "a" * 40, "head_sha": "b" * 40,
        "candidate_diff_sha256": "c" * 64, "changed_files": ["synthetic.py"]}}
    for role in ("SECURITY", "FUNCTIONAL", "CHALLENGE"):
        sdk.state.content = {"verdict": "SEND_BACK", "findings": ["synthetic"]}
        review = HermesIndependentReviewer(sdk.model).review(role, packet)
        assert review["reviewer_identity"].startswith("HNR-")
        names.append("charlie.native." + role.lower() + ".review.v1")
    for body, name in zip(sdk.calls, names):
        wire = body["response_format"]["json_schema"]
        assert wire["name"].startswith(name.replace(".", "_") + "_")
        assert wire["schema"] == (NATIVE_PATCH_SCHEMA if name == names[0] else NATIVE_REVIEW_SCHEMA)
        assert wire["strict"] is True and body["tools"] == []
        assert body["provider"] == {"allow_fallbacks": False, "require_parameters": True,
                                     "max_price": {"prompt": 0.25, "completion": 2.0}}
    assert len(sdk.reservations) == len(sdk.calls) == 4
    tasks = ["charlie_native_builder", "charlie_native_security_reviewer",
             "charlie_native_functional_reviewer", "charlie_native_challenge_reviewer"]
    for body, reservation, task in zip(sdk.calls, sdk.reservations, tasks):
        encoded = json.dumps(body, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False).encode("utf-8")
        assert reservation == {"request_sha256": hashlib.sha256(encoded).hexdigest(),
                               "input_bytes": len(encoded), "max_tokens": body["max_tokens"],
                               "task": task}


def test_strict_canary_and_legacy_canary_preserve_audit_and_attempts(sdk):
    sdk.state.content = {"status": "READY"}
    assert run_schema_canary(sdk.model)["status"] == "READY"
    strict_name = sdk.calls[-1]["response_format"]["json_schema"]["name"]
    calls = []
    def legacy(**kwargs):
        calls.append(kwargs)
        wire = kwargs["extra_body"]["response_format"]["json_schema"]
        assert re.fullmatch(r"[A-Za-z0-9_-]{1,64}", wire["name"])
        assert wire["name"] == strict_name
        if len(calls) == 1:
            raise TimeoutError(sdk.private)
        kwargs["route_info"].update(provider="openrouter", model=DEFAULT_MODEL)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"status":"READY"}'))])
    model = HermesAuxiliaryModel(profile_home="synthetic", call=legacy)
    assert run_schema_canary(model)["status"] == "READY"
    assert len(calls) == 2 and len(sdk.reservations) == 1


@pytest.mark.parametrize("name", ["", None, 12, "a" * 65, "a..b", ".a", "a.", "a b",
                                  "a/b", "a\nb", "aé", "a\x00b"])
def test_invalid_names_never_resolve_reserve_or_submit(sdk, name):
    for model in (sdk.model, HermesAuxiliaryModel(profile_home="synthetic", call=lambda **kw: pytest.fail("legacy called"))):
        with pytest.raises(NativeExecutionError, match="schema_name_invalid"):
            model.complete_structured(**{**sdk.args, "schema_name": name})
    assert sdk.resolves == sdk.reservations == sdk.calls == []


@pytest.mark.parametrize("name", ["wire_SAFE-1", "a" * 64, "a." + "b" * 62])
def test_names_are_deterministic_bounded_and_audit_identity_is_unchanged(sdk, name):
    for _ in range(2):
        result = sdk.model.complete_structured(**{**sdk.args, "schema_name": name})
        assert result.audit["schema_name"] == name
    names = [body["response_format"]["json_schema"]["name"] for body in sdk.calls]
    assert names[0] == names[1]
    assert len(names[0]) <= 64
    if "." not in name:
        assert names[0] == name


def test_dotted_label_does_not_alias_underscore_label(sdk):
    for name in ("a.b", "a_b"):
        sdk.model.complete_structured(**{**sdk.args, "schema_name": name})
    assert sdk.calls[0]["response_format"] != sdk.calls[1]["response_format"]


@pytest.mark.parametrize("change", [{"required": None}, {"required": []}, {"required": ["ok", "ok"]},
    {"required": ["missing"]}, {"required": [1]}, {"additionalProperties": True},
    {"properties": []}, {"type": "array"}])
def test_invalid_root_schema_envelope_fails_before_reservation(sdk, change):
    schema = {**sdk.args["json_schema"], **change}
    with pytest.raises(NativeExecutionError, match="request_schema_invalid"):
        sdk.model.complete_structured(**{**sdk.args, "json_schema": schema})
    assert sdk.resolves == sdk.reservations == sdk.calls == []


@pytest.mark.parametrize("status", [400, 401, 402, 429, 500, 418])
def test_real_sdk_status_failure_is_safe_and_never_retried(sdk, status):
    sdk.state.status = status
    with pytest.raises(NativeModelFailure) as caught:
        sdk.model.complete_structured(**sdk.args)
    exc = caught.value
    diagnostic = model_failure_diagnostics(exc)
    assert str(exc) == "hermes_auxiliary_inference_failed"
    assert diagnostic == {"model_failure_stage": "sdk_submission", "model_failure_kind": "http_status",
                           **({"model_failure_status": status} if status != 418 else {})}
    assert sdk.private not in "".join(traceback.format_exception(exc)) + json.dumps(vars(exc))
    assert len(sdk.calls) == len(sdk.reservations) == 1


@pytest.mark.parametrize("error,kind", [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "connection")])
def test_real_sdk_transport_failure_is_safe_and_never_retried(sdk, error, kind):
    sdk.state.error = error
    with pytest.raises(NativeModelFailure) as caught:
        sdk.model.complete_structured(**sdk.args)
    assert model_failure_diagnostics(caught.value) == {
        "model_failure_stage": "sdk_submission", "model_failure_kind": kind}
    assert sdk.private not in "".join(traceback.format_exception(caught.value))
    assert len(sdk.calls) == len(sdk.reservations) == 1


@pytest.mark.parametrize("stage", ["resolution", "reservation", "transport_setup"])
def test_before_submit_failure_does_not_imply_request_delivery(sdk, monkeypatch, stage):
    error = RuntimeError(sdk.private)
    if stage == "resolution":
        sdk.state.resolution_error = error
    elif stage == "reservation":
        sdk.state.reservation_error = error
    else:
        def broken(**kwargs):
            raise error
        monkeypatch.setattr(httpx, "HTTPTransport", broken)
    with pytest.raises(NativeModelFailure) as caught:
        sdk.model.complete_structured(**sdk.args)
    assert model_failure_diagnostics(caught.value) == {
        "model_failure_stage": stage, "model_failure_kind": "unexpected_error"}
    assert len(sdk.reservations) == (1 if stage == "reservation" else 0)
    assert sdk.calls == []
    assert sdk.private not in "".join(traceback.format_exception(caught.value))


def test_malformed_provider_json_does_not_leak_raw_body_or_retry(sdk):
    sdk.state.content = sdk.private
    with pytest.raises(NativeExecutionError, match="native_model_response_invalid") as caught:
        sdk.model.complete_structured(**sdk.args)
    assert sdk.private not in "".join(traceback.format_exception(caught.value))
    assert len(sdk.calls) == len(sdk.reservations) == 1


def test_legacy_failure_retains_two_attempts_and_suppresses_private_cause(sdk):
    calls = []
    def legacy(**kwargs):
        calls.append(kwargs)
        raise RuntimeError(sdk.private)
    with pytest.raises(NativeModelFailure) as caught:
        HermesAuxiliaryModel(profile_home="synthetic", call=legacy).complete_structured(**sdk.args)
    assert len(calls) == 2 and sdk.reservations == []
    assert model_failure_diagnostics(caught.value) == {
        "model_failure_stage": "legacy_call", "model_failure_kind": "unexpected_error"}
    assert sdk.private not in "".join(traceback.format_exception(caught.value))
