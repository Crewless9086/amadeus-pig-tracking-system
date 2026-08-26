from datetime import datetime, timezone
import importlib
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
