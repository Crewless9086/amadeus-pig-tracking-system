from datetime import datetime, timezone
import importlib
import pytest
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from modules.oom_sakkie.farm_manager_loop import (
    Authority, Provenance, SpecialistAvailability, SpecialistResult,
    SpecialistWorkItem, WorkState)
from modules.oom_sakkie.morning_scheduler import run_synthetic_acceptance


IDENTITY = "synthetic_acceptance:ROOTLINE-SCHEDULE-TEST:20260813-A"
ENV = {"OOM_SAKKIE_DAILY_MANAGER_OWNER_USER_ID": "42",
       "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42,43,44"}


def test_synthetic_real_plan_claims_and_delivers_once_under_concurrent_replay():
    rows = {}; lock = Lock(); sends = []
    def store(action, identity, payload):
        with lock:
            created = identity not in rows
            rows.setdefault(identity, dict(payload or {}))
        return {"success": True, "created": created}
    now = datetime(2026, 8, 13, 12, 0, tzinfo=timezone.utc)
    provenance = Provenance("rootline", "current", ("canonical_read_models",), now, 1.0)
    rootline = SpecialistResult("rootline", "current", now,
        SpecialistAvailability.AVAILABLE, work_items=(SpecialistWorkItem(
            item_id="rootline-plan", dedupe_key="rootline:daily-plan",
            domain="water_energy", title="ROOTLINE current plan", why="Current evidence",
            next_action="Hold all controls; reassess current evidence.", assignee="charl",
            state=WorkState.PLANNED, authority=Authority.ADVISORY, provenance=provenance),))
    def deliver(*args, **kwargs):
        sends.append(kwargs["mission_id"])
        return {"success": True, "telegram_message_id": "test-1",
                "telegram_sends": 1, "telegram_edits": 0}
    args = dict(environ=ENV, now=now, store=store, rootline_loader=lambda: rootline,
                deliver=deliver)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: run_synthetic_acceptance(IDENTITY, **args), range(2)))
    assert sorted(result["status"] for result in results) == [
        "synthetic_acceptance_replay_suppressed", "synthetic_acceptance_rootline_plan"]
    assert list(rows) == [IDENTITY]
    assert sends == [IDENTITY]
    assert all(result["hardware_commands"] == result["provider_control_calls"] == 0
               and result["writes_farm_data"] is False for result in results)


def test_synthetic_identity_cannot_collide_with_daily_claim():
    result = run_synthetic_acceptance("OOM-DAILY-FARM-MANAGER-2026-08-14:DELIVERY",
                                      environ=ENV)
    assert result["status"] == "synthetic_acceptance_invalid"
    assert result["telegram_sends"] == result["telegram_edits"] == 0


def test_scheduler_route_requires_strong_bearer_and_dispatches_synthetic(monkeypatch):
    import modules.oom_sakkie.routes as routes
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(routes.oom_sakkie_bp, url_prefix="/api")
    monkeypatch.setenv("OOM_SAKKIE_MORNING_SCHEDULER_TOKEN", "t" * 32)
    monkeypatch.setattr(routes, "run_synthetic_acceptance", lambda identity: {
        "success": True, "status": "synthetic_acceptance_rootline_plan",
        "identity_seen": identity, "telegram_sends": 1, "telegram_edits": 0})
    client = app.test_client()
    denied = client.post("/api/oom-sakkie/management/morning-schedule", json={})
    accepted = client.post("/api/oom-sakkie/management/morning-schedule",
        headers={"Authorization": "Bearer " + "t" * 32},
        json={"synthetic_acceptance_identity": IDENTITY})
    assert denied.status_code == 403
    assert denied.get_json()["telegram_sends"] == 0
    assert accepted.status_code == 200
    assert accepted.get_json()["identity_seen"] == IDENTITY


def test_payment_recovery_route_uses_same_strong_scheduler_authority(monkeypatch):
    import modules.oom_sakkie.routes as routes
    from flask import Flask
    app = Flask(__name__)
    app.register_blueprint(routes.oom_sakkie_bp, url_prefix="/api")
    monkeypatch.setenv("OOM_SAKKIE_MORNING_SCHEDULER_TOKEN", "r" * 32)
    monkeypatch.setattr(routes, "run_payment_recovery_cycle", lambda: {
        "success": True, "status": "payment_recovery_idle",
        "worker_id": "oom-sakkie-protected-payment-recovery-v1",
        "telegram_sends": 0, "telegram_edits": 0})
    client = app.test_client()
    denied = client.post("/api/oom-sakkie/management/protected-payment-recovery")
    accepted = client.post("/api/oom-sakkie/management/protected-payment-recovery",
        headers={"Authorization": "Bearer " + "r" * 32})
    assert denied.status_code == 403
    assert accepted.status_code == 200
    assert accepted.get_json()["status"] == "payment_recovery_idle"


def _script_module(monkeypatch):
    monkeypatch.setenv("OOM_SAKKIE_MORNING_SCHEDULER_URL", "https://example.test/morning-schedule")
    monkeypatch.setenv("OOM_SAKKIE_MORNING_SCHEDULER_TOKEN", "x" * 32)
    return importlib.import_module("scripts.oom_sakkie_morning_scheduler")


def _scheduler_post(morning, calls):
    def call(url, payload):
        calls.append((url, payload))
        if url.endswith("morning-schedule"): return morning
        if url.endswith("protected-payment-recovery"): return {"status":"payment_recovery_idle"}
        if url.endswith("green-print-recovery"): return {"status":"documents_green_recovery_idle"}
        if url.endswith("general-manager-cycle"): return {"status":"general_manager_cycle_completed"}
        return {"success":True}
    return call


def test_late_provider_tick_still_invokes_morning(monkeypatch):
    module=_script_module(monkeypatch); calls=[]
    result,code=module.run_scheduler(now=datetime(2026,8,26,5,12,tzinfo=timezone.utc),
        post_fn=_scheduler_post({"success":True,"status":"daily_manager_replay_suppressed"},calls))
    assert code==0 and result["success"] is True
    assert any(url.endswith("morning-schedule") for url,_ in calls)


def test_morning_failure_propagates_to_scheduler_exit(monkeypatch):
    module=_script_module(monkeypatch); calls=[]
    result,code=module.run_scheduler(now=datetime(2026,8,26,4,46,tzinfo=timezone.utc),
        post_fn=_scheduler_post({"success":False,"status":"daily_manager_claim_unproven"},calls))
    assert code==1 and result["success"] is False


def test_manager_timeout_is_contained_without_blocking_beacon_or_morning(monkeypatch):
    module=_script_module(monkeypatch); calls=[]
    def call(url,payload):
        calls.append(url)
        if url.endswith("protected-payment-recovery"):
            return {"status":"payment_recovery_idle"}
        if url.endswith("green-print-recovery"):
            return {"status":"documents_green_recovery_idle"}
        if url.endswith("general-manager-cycle"):
            raise TimeoutError("manager exceeded bounded request window")
        if url.endswith("beacon-publication-cycle"):
            return {"success":True,"status":"beacon_publication_cycle_completed"}
        return {"success":True,"status":"daily_manager_replay_suppressed"}

    result,code=module.run_scheduler(
        now=datetime(2026,8,26,14,45,tzinfo=timezone.utc),post_fn=call)

    assert code==1 and result["success"] is False
    assert result["manager_status"]=="general_manager_cycle_request_contained"
    assert result["manager_failure_kind"]=="TimeoutError"
    assert result["beacon_publication_status"]=="beacon_publication_cycle_completed"
    assert result["morning_status"]=="daily_manager_replay_suppressed"
    assert any(url.endswith("beacon-publication-cycle") for url in calls)
    assert any(url.endswith("morning-schedule") for url in calls)
    manager_position = next(index for index,url in enumerate(calls)
                            if url.endswith("general-manager-cycle"))
    assert next(index for index,url in enumerate(calls)
                if url.endswith("beacon-publication-cycle")) < manager_position
    assert next(index for index,url in enumerate(calls)
                if url.endswith("morning-schedule")) < manager_position


def test_morning_http_error_is_not_retried_and_manager_still_runs(monkeypatch):
    module = _script_module(monkeypatch); calls = []

    def call(url, payload):
        calls.append(url)
        if url.endswith("protected-payment-recovery"):
            return {"status": "payment_recovery_idle"}
        if url.endswith("green-print-recovery"):
            return {"status": "documents_green_recovery_idle"}
        if url.endswith("beacon-publication-cycle"):
            return {"success": True, "status": "beacon_publication_cycle_completed"}
        if url.endswith("morning-schedule"):
            raise HTTPError(url, 503, "Service Unavailable", {}, None)
        if url.endswith("general-manager-cycle"):
            return {"status": "general_manager_cycle_completed"}
        raise AssertionError(url)

    result, code = module.run_scheduler(
        now=datetime(2026, 8, 26, 14, 45, tzinfo=timezone.utc), post_fn=call)

    assert code == 1 and result["success"] is False
    assert result["morning_status"] == "morning_schedule_request_contained"
    assert result["morning_failure_kind"] == "HTTPError"
    assert result["manager_status"] == "general_manager_cycle_completed"
    assert sum(url.endswith("morning-schedule") for url in calls) == 1
    assert sum(url.endswith("general-manager-cycle") for url in calls) == 1
    beacon_position = next(index for index, url in enumerate(calls)
                           if url.endswith("beacon-publication-cycle"))
    morning_position = next(index for index, url in enumerate(calls)
                            if url.endswith("morning-schedule"))
    manager_position = next(index for index, url in enumerate(calls)
                            if url.endswith("general-manager-cycle"))
    assert beacon_position < morning_position < manager_position


def test_multi_recipient_runtime_success_is_scheduler_success(monkeypatch):
    module=_script_module(monkeypatch); calls=[]
    result,code=module.run_scheduler(now=datetime(2026,8,26,5,12,tzinfo=timezone.utc),
        post_fn=_scheduler_post({"success":True,
            "status":"morning_runtime_recipients_projected"},calls))
    assert code==0 and result["success"] is True


@pytest.mark.parametrize("failed_stage", [
    "protected-payment-recovery", "green-print-recovery", "beacon-publication-cycle"])
@pytest.mark.parametrize("failure", ["http", "timeout", "json", "non_object", "truncated", "http_truncated"])
def test_independent_lane_failure_does_not_starve_manager(monkeypatch, failed_stage, failure):
    import io
    module = _script_module(monkeypatch)
    calls = []
    ordinary = _scheduler_post({"success": True, "status": "daily_manager_replay_suppressed"}, [])

    def post(url, payload):
        calls.append(url.rsplit("/", 1)[-1])
        if url.endswith(failed_stage):
            if failure in {"truncated", "http_truncated"}:
                from http.client import IncompleteRead
                if failure == "truncated":
                    raise IncompleteRead(b"private partial response", 100)
                class TruncatedBody(io.BytesIO):
                    def read(self, *args):
                        raise IncompleteRead(b"private partial response", 100)
                raise HTTPError(url, 503, "private details", {}, TruncatedBody())
            if failure == "http":
                raise HTTPError(url, 503, "private details", {}, io.BytesIO(
                    b'{"status":"upstream_unavailable","private_data":"never log this"}'))
            if failure == "timeout":
                raise TimeoutError("ambiguous request")
            if failure == "json":
                raise ValueError("invalid JSON")
            return []
        return ordinary(url, payload)

    result, code = module.run_scheduler(
        now=datetime(2026, 9, 21, 10, 0, tzinfo=timezone.utc), post_fn=post)
    assert code == 1 and result["success"] is False
    assert calls.count("general-manager-cycle") == 1
    assert calls.count(failed_stage) == 1
    assert len(calls) == 5
    assert result["manager_status"] == "general_manager_cycle_completed"
    assert result["request_failures"][0]["provider_effects_unknown"] is True
    assert "private" not in str(result)
    if failure == "http":
        assert result["request_failures"][0]["http_status"] == 503
        assert result["request_failures"][0]["response_status"] == "upstream_unavailable"


@pytest.mark.parametrize("now,invoked", [
    (datetime(2026, 9, 21, 21, 59, tzinfo=timezone.utc), True),
    (datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc), False),
    (datetime(2026, 9, 22, 0, 0, tzinfo=timezone.utc), False),
    (datetime(2026, 9, 22, 4, 44, tzinfo=timezone.utc), False),
    (datetime(2026, 9, 22, 4, 45, tzinfo=timezone.utc), True),
])
def test_morning_gate_uses_sast_date_boundary(monkeypatch, now, invoked):
    module = _script_module(monkeypatch)
    monkeypatch.setattr(module, "synthetic", "")
    calls = []
    result, code = module.run_scheduler(now=now, post_fn=_scheduler_post(
        {"success": True, "status": "daily_manager_unchanged_silent"}, calls))
    assert code == 0 and result["success"] is True
    assert sum(url.endswith("morning-schedule") for url, _ in calls) == int(invoked)
    assert sum(url.endswith("general-manager-cycle") for url, _ in calls) == 1


def test_explicit_synthetic_schedule_still_runs_before_morning(monkeypatch):
    module = _script_module(monkeypatch)
    monkeypatch.setattr(module, "synthetic", "synthetic_acceptance:LOCAL-ONLY")
    calls = []
    module.run_scheduler(now=datetime(2026, 9, 21, 22, 0, tzinfo=timezone.utc),
        post_fn=_scheduler_post({"success": True, "status": "morning_runtime_not_due"}, calls))
    morning = [(url, body) for url, body in calls if url.endswith("morning-schedule")]
    assert len(morning) == 1
    assert morning[0][1] == {"synthetic_acceptance_identity": "synthetic_acceptance:LOCAL-ONLY"}


@pytest.mark.parametrize("status", ["morning_runtime_not_due", "daily_manager_not_due",
                                    "daily_manager_internal_work_silent"])
@pytest.mark.parametrize("success", [True, False])
def test_proven_silent_morning_status_requires_true_success(monkeypatch, status, success):
    module = _script_module(monkeypatch)
    result, code = module.run_scheduler(now=datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc),
        post_fn=_scheduler_post({"success": success, "status": status}, []))
    assert code == (0 if success else 1)
    assert result["success"] is success


@pytest.mark.parametrize("transport", ["http503", "body_false", "contradictory_success"])
def test_morning_recipient_failures_stay_failed_and_emit_only_safe_diagnostics(monkeypatch, transport):
    import io, json
    module = _script_module(monkeypatch)
    calls = []
    body = {"success": transport == "contradictory_success",
        "status": "morning_runtime_recipients_projected",
        "recipient_results": [
            {"success": True, "status": "daily_manager_unchanged_silent",
             "owner_user_id": "private-owner", "answer": "private message"},
            {"success": False, "status": "daily_manager_delivery_ambiguous",
             "failure_class": "ValueError", "failure_kind": "private exception text",
             "delivery_failure_reason": "brief_replacement_generation_binding_conflict",
             "owner_user_id": "private-owner", "chat_id": "private-chat", "answer": "private message"},
            {"success": False, "status": "private unstructured body", "failure_class": "private\ntrace",
             "delivery_failure_reason": "private unstructured reason"},
        ], "private_data": "private body"}
    ordinary = _scheduler_post({"success": True, "status": "daily_manager_presented"}, [])
    error_body = io.BytesIO(json.dumps(body).encode())
    def post(url, payload):
        calls.append(url)
        if url.endswith("morning-schedule"):
            if transport == "http503":
                raise HTTPError(url, 503, "private reason", {}, error_body)
            return body
        return ordinary(url, payload)
    result, code = module.run_scheduler(now=datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc), post_fn=post)
    assert code == 1 and result["success"] is False
    assert result["morning_recipient_failures"] == [
        {"recipient_index": 2, "success": False, "status": "daily_manager_delivery_ambiguous",
         "delivery_failure_reason": "brief_replacement_generation_binding_conflict",
         "failure_class": "ValueError"},
        {"recipient_index": 3, "success": False}]
    assert "private" not in json.dumps(result)
    assert sum(url.endswith("morning-schedule") for url in calls) == 1
    assert sum(url.endswith("general-manager-cycle") for url in calls) == 1
    if transport == "http503":
        assert result["request_failures"][0]["http_status"] == 503
        assert result["request_failures"][0]["recipient_failures"] == result["morning_recipient_failures"]
        assert error_body.closed


def test_morning_recipient_diagnostics_are_bounded_and_validate_field_types(monkeypatch):
    module = _script_module(monkeypatch)
    body = {"success": False, "status": "morning_runtime_recipients_projected",
        "recipient_results": [{"success": False, "status": "x" * 121,
            "failure_kind": {"private": "object"}, "failure_class": 123}] * 20}
    result, code = module.run_scheduler(now=datetime(2026, 9, 22, 5, 0, tzinfo=timezone.utc),
        post_fn=_scheduler_post(body, []))
    assert code == 1
    assert result["morning_recipient_failures"] == [
        {"recipient_index": index, "success": False} for index in range(1, 9)]
