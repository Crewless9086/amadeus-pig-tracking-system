from datetime import datetime, timezone
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
