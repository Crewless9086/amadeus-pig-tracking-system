from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock

from modules.oom_sakkie.farm_manager_loop import SpecialistAvailability, SpecialistResult
from modules.oom_sakkie.morning_runtime import run_morning_cycle, start_production_morning_runtime


NOW = datetime(2026, 8, 13, 4, 50, tzinfo=timezone.utc)  # 06:50 SAST
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


def test_changed_evidence_after_restart_cannot_edit_or_send_again():
    events = {}
    deliveries = []

    def store(action, identity, payload):
        if action == "load_daily":
            return None
        if action == "load_answered_questions":
            return ()
        created = identity not in events
        events.setdefault(identity, dict(payload or {}))
        return {"success": True, "created": created}

    def deliver(*args, **kwargs):
        deliveries.append(kwargs["mission_id"])
        return {"success": True, "telegram_message_id": "9001",
                "telegram_sends": 1, "telegram_edits": 0}

    common = dict(now=NOW, environ=ENV, deliver=deliver, store=store,
                  rootline_loader=lambda: _specialist("rootline"),
                  litter_loader=lambda: {"allocation_inputs": {"litter_rows": []}},
                  sales_loader=lambda: ({"success": True, "sales_transactions": []}, 200))
    first = run_morning_cycle(
        **common, herd_loader=lambda: _specialist("herdmaster-first"))
    restarted = run_morning_cycle(
        **common, herd_loader=lambda: _specialist("herdmaster-changed"))

    assert first["status"] == "daily_manager_presented"
    assert restarted["status"] == "daily_manager_replay_suppressed"
    assert restarted["telegram_sends"] == restarted["telegram_edits"] == 0
    assert deliveries == ["OOM-DAILY-FARM-MANAGER-2026-08-13:DELIVERY"]


def test_in_window_failure_retries_then_missed_window_escalates_once():
    def broken():
        raise RuntimeError("source unavailable")
    before = run_morning_cycle(now=NOW, environ=ENV, herd_loader=broken,
        rootline_loader=lambda: _specialist("rootline"),
        litter_loader=lambda: {}, sales_loader=lambda: ({}, 503),
        deliver=lambda *a, **k: {})
    assert before["status"] == "morning_runtime_recovery_pending"
    assert before["telegram_sends"] == 0

    deliveries = []
    events = {}
    def store(action, identity, payload):
        if action == "load_daily":
            return None
        if action == "load_answered_questions":
            return ()
        created = identity not in events
        events.setdefault(identity, dict(payload or {}))
        return {"success": True, "created": created}
    after = run_morning_cycle(now=datetime(2026, 8, 13, 10, 30, tzinfo=timezone.utc),
        environ=ENV, herd_loader=broken,
        rootline_loader=lambda: _specialist("rootline"), litter_loader=lambda: {},
        sales_loader=lambda: ({}, 503),
        store=store,
        deliver=lambda *a, **k: deliveries.append(k["mission_id"]) or {
            "success": True, "telegram_message_id": "failure-1", "telegram_sends": 1})
    assert after["status"] == "morning_runtime_failure_escalated"
    assert after["provider_delivery_confirmed"] is True
    assert deliveries == ["OOM-DAILY-FARM-MANAGER-2026-08-13:FAILURE"]
    replay = run_morning_cycle(now=datetime(2026, 8, 13, 10, 31, tzinfo=timezone.utc),
        environ=ENV, herd_loader=broken,
        rootline_loader=lambda: _specialist("rootline"), litter_loader=lambda: {},
        sales_loader=lambda: ({}, 503), store=store,
        deliver=lambda *a, **k: deliveries.append(k["mission_id"]) or {})
    assert replay["status"] == "morning_runtime_failure_replay_suppressed"
    assert replay["telegram_sends"] == replay["telegram_edits"] == 0
    assert len(deliveries) == 1


def test_restart_after_window_never_loads_or_creates_a_plan():
    events = {}
    deliveries = []
    loader_calls = []
    claim_lock = Lock()

    def store(action, identity, payload):
        if action == "load_daily":
            return None
        with claim_lock:
            created = identity not in events
            events.setdefault(identity, dict(payload or {}))
        return {"success": True, "created": created}

    def forbidden_loader():
        loader_calls.append(True)
        raise AssertionError("missed-window restart must not load plan evidence")

    def deliver(*args, **kwargs):
        deliveries.append(kwargs["mission_id"])
        return {"success": True, "telegram_message_id": "failure-1",
                "telegram_sends": 1, "telegram_edits": 0}

    args = dict(now=datetime(2026, 8, 14, 5, 1, tzinfo=timezone.utc),
                environ=ENV, store=store, deliver=deliver,
                herd_loader=forbidden_loader, rootline_loader=forbidden_loader,
                litter_loader=forbidden_loader, sales_loader=forbidden_loader)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_morning_cycle(**args), range(2)))

    first = next(result for result in results
                 if result["status"] == "morning_runtime_failure_escalated")
    concurrent_restart = next(result for result in results
                              if result["status"] == "morning_runtime_failure_replay_suppressed")
    assert first["failure_class"] == "MorningWindowMissed"
    assert concurrent_restart["status"] == "morning_runtime_failure_replay_suppressed"
    assert concurrent_restart["telegram_sends"] == concurrent_restart["telegram_edits"] == 0
    assert loader_calls == []
    assert deliveries == ["OOM-DAILY-FARM-MANAGER-2026-08-14:FAILURE"]


def test_success_claim_blocks_later_failure_card_for_same_date():
    events = {}
    deliveries = []
    def store(action, identity, payload):
        if action == "load_daily":
            return None
        if action == "load_answered_questions":
            return ()
        created = identity not in events
        events.setdefault(identity, dict(payload or {}))
        return {"success": True, "created": created}
    def deliver(*args, **kwargs):
        deliveries.append(kwargs["mission_id"])
        return {"success": True, "telegram_message_id": "9001", "telegram_sends": 1}
    common = dict(environ=ENV, store=store, deliver=deliver,
                  rootline_loader=lambda: _specialist("rootline"),
                  litter_loader=lambda: {"allocation_inputs": {"litter_rows": []}},
                  sales_loader=lambda: ({"success": True, "sales_transactions": []}, 200))
    first = run_morning_cycle(now=NOW, herd_loader=lambda: _specialist("herd"), **common)
    failed = run_morning_cycle(now=datetime(2026, 8, 13, 10, 30, tzinfo=timezone.utc),
        herd_loader=lambda: (_ for _ in ()).throw(RuntimeError("down")), **common)
    assert first["status"] == "daily_manager_presented"
    assert failed["status"] == "morning_runtime_failure_replay_suppressed"
    assert failed["telegram_sends"] == failed["telegram_edits"] == 0
    assert deliveries == ["OOM-DAILY-FARM-MANAGER-2026-08-13:DELIVERY"]


def test_runtime_starts_only_under_production_ownership(monkeypatch):
    import modules.oom_sakkie.morning_runtime as runtime
    monkeypatch.setattr(runtime, "_STARTED", False)
    assert start_production_morning_runtime(environ={}, runner=lambda **k: None) is False
    assert start_production_morning_runtime(environ={"RENDER": "true"},
                                            runner=lambda **k: None) is False
    assert start_production_morning_runtime(environ={"OOM_SAKKIE_DAILY_MANAGER_RUNTIME_ENABLED": "true"},
                                            runner=lambda **k: None) is True
    assert start_production_morning_runtime(environ={"OOM_SAKKIE_DAILY_MANAGER_RUNTIME_ENABLED": "true"},
                                            runner=lambda **k: None) is False
