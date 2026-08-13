from datetime import datetime, timezone

from modules.oom_sakkie.farm_manager_loop import SpecialistAvailability, SpecialistResult
from modules.oom_sakkie.morning_runtime import run_morning_cycle, start_production_morning_runtime


NOW = datetime(2026, 8, 13, 5, 0, tzinfo=timezone.utc)  # 07:00 SAST
ENV = {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"}


def _specialist(name):
    return SpecialistResult(name, name + "-result", NOW, SpecialistAvailability.AVAILABLE)


def test_backend_owned_cycle_delivers_once_and_replay_is_silent():
    events = {}
    sends = []

    def store(action, identity, payload):
        if action == "load_daily":
            matches = [row for row in events.values()
                       if row.get("daily_identity") == identity
                       and row.get("status") in {"presented", "unchanged", "provider_ambiguous"}]
            return matches[-1] if matches else None
        if action == "load_answered_questions":
            return ()
        created = identity not in events
        events.setdefault(identity, dict(payload or {}))
        return {"success": True, "created": created}

    def deliver(*args, **kwargs):
        sends.append(kwargs.get("mission_id"))
        return {"success": True, "telegram_message_id": "9001", "telegram_sends": 1,
                "telegram_edits": 0}

    args = dict(now=NOW, environ=ENV, deliver=deliver, store=store,
                herd_loader=lambda: _specialist("herdmaster"),
                rootline_loader=lambda: _specialist("rootline"),
                litter_loader=lambda: {"allocation_inputs": {"litter_rows": []}},
                sales_loader=lambda: ({"success": True, "sales_transactions": []}, 200))
    first = run_morning_cycle(**args)
    replay = run_morning_cycle(**args)
    assert first["status"] == "daily_manager_presented"
    assert replay["status"] == "daily_manager_unchanged_silent"
    assert sends == [sends[0]]
    assert first["hardware_commands"] == 0


def test_catchup_retries_before_deadline_and_escalates_after_deadline():
    def broken():
        raise RuntimeError("source unavailable")
    before = run_morning_cycle(now=NOW, environ=ENV, herd_loader=broken,
        rootline_loader=lambda: _specialist("rootline"),
        litter_loader=lambda: {}, sales_loader=lambda: ({}, 503),
        deliver=lambda *a, **k: {})
    assert before["status"] == "morning_runtime_recovery_pending"
    assert before["telegram_sends"] == 0

    deliveries = []
    after = run_morning_cycle(now=datetime(2026, 8, 13, 10, 30, tzinfo=timezone.utc),
        environ=ENV, herd_loader=broken,
        rootline_loader=lambda: _specialist("rootline"), litter_loader=lambda: {},
        sales_loader=lambda: ({}, 503),
        deliver=lambda *a, **k: deliveries.append(k["mission_id"]) or {
            "success": True, "telegram_message_id": "failure-1", "telegram_sends": 1})
    assert after["status"] == "morning_runtime_failure_escalated"
    assert after["provider_delivery_confirmed"] is True
    assert deliveries == ["OOM-DAILY-FARM-MANAGER-2026-08-13:FAILURE"]


def test_runtime_starts_only_under_production_ownership(monkeypatch):
    import modules.oom_sakkie.morning_runtime as runtime
    monkeypatch.setattr(runtime, "_STARTED", False)
    assert start_production_morning_runtime(environ={}, runner=lambda **k: None) is False
    assert start_production_morning_runtime(environ={"RENDER": "true"},
                                            runner=lambda **k: None) is True
    assert start_production_morning_runtime(environ={"RENDER": "true"},
                                            runner=lambda **k: None) is False
