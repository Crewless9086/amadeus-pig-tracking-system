from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from threading import Lock
from unittest.mock import patch
import json

from modules.oom_sakkie.farm_manager_loop import SpecialistAvailability, SpecialistResult
from modules.oom_sakkie.morning_runtime import (
    _load_inputs, run_morning_cycle, start_production_morning_runtime)


NOW = datetime(2026, 8, 13, 4, 50, tzinfo=timezone.utc)  # 06:50 SAST
ENV = {"OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"}


def _two_manager_env():
    return {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": "42",
        "OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE": "en",
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42,77",
        "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps([{
            "telegram_user_id": "77", "role": "farm_manager", "family_key": "dad",
            "permissions": ["farm_observation"], "summary_domains": ["farm"],
            "authorization_id": "AUTH-ANTON", "authorized_by_user_id": "42",
            "authorized_at": "2026-08-01T00:00:00+00:00", "language": "af"}])}


def _specialist(name):
    return SpecialistResult(name, name + "-result", NOW, SpecialistAvailability.AVAILABLE)


@patch("modules.oom_sakkie.morning_runtime.wait", return_value=(set(), set()))
def test_synchronous_morning_input_wait_is_below_worker_timeout(waiter):
    try:
        _load_inputs("42", NOW, ENV, herd_loader=lambda: _specialist("herdmaster"),
            rootline_loader=lambda: _specialist("rootline"),
            litter_loader=lambda: {"allocation_inputs": {"litter_rows": []}},
            sales_loader=lambda: ({"success": True, "sales_transactions": []}, 200))
    except TimeoutError as exc:
        assert str(exc) == "morning_runtime_specialist_deadline"
    else:
        raise AssertionError("deadline must contain incomplete specialist reads")
    assert waiter.call_args.kwargs["timeout"] == 12


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
    assert len(deliveries) == 1
    assert deliveries[0].startswith("OOM-DAILY-FARM-MANAGER-2026-08-13:OWNER:")
    assert deliveries[0].endswith(":DELIVERY")


def test_source_failure_remains_visible_for_late_durable_retry():
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
    assert after["status"] == "morning_runtime_recovery_pending"
    assert deliveries == []
    replay = run_morning_cycle(now=datetime(2026, 8, 13, 10, 31, tzinfo=timezone.utc),
        environ=ENV, herd_loader=broken,
        rootline_loader=lambda: _specialist("rootline"), litter_loader=lambda: {},
        sales_loader=lambda: ({}, 503), store=store,
        deliver=lambda *a, **k: deliveries.append(k["mission_id"]) or {})
    assert replay["status"] == "morning_runtime_recovery_pending"
    assert replay["telegram_sends"] == replay["telegram_edits"] == 0
    assert deliveries == []


def test_optional_source_exception_does_not_block_date_stable_morning_claim():
    events = {}
    deliveries = []

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
        deliveries.append(kwargs["mission_id"])
        return {"success": True, "telegram_message_id": "optional-gap-brief",
                "telegram_sends": 1, "telegram_edits": 0}

    args = dict(now=NOW, environ=ENV, deliver=deliver, store=store,
        herd_loader=lambda: _specialist("herdmaster"),
        rootline_loader=lambda: _specialist("rootline"),
        litter_loader=lambda: (_ for _ in ()).throw(RuntimeError("breeding unavailable")),
        sales_loader=lambda: ({"success": True, "sales_transactions": []}, 200))
    first = run_morning_cycle(**args)
    replay = run_morning_cycle(**args)

    assert first["status"] == "daily_manager_presented"
    assert first["optional_source_failures"] == [
        {"source": "breeding_attention", "failure_class": "RuntimeError"}]
    assert replay["status"] == "daily_manager_unchanged_silent"
    assert replay["optional_source_failure_count"] == 1
    assert len(deliveries) == 1


def test_restart_at_0712_sast_loads_and_delivers_date_stable_plan_once():
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

    def late_loader():
        loader_calls.append(True)
        return _specialist("late")

    def deliver(*args, **kwargs):
        deliveries.append(kwargs["mission_id"])
        return {"success": True, "telegram_message_id": "late-brief-1",
                "telegram_sends": 1, "telegram_edits": 0}

    args = dict(now=datetime(2026, 8, 14, 5, 12, tzinfo=timezone.utc),
                environ=ENV, store=store, deliver=deliver,
                herd_loader=late_loader, rootline_loader=late_loader,
                litter_loader=lambda: {"allocation_inputs":{"litter_rows":[]}},
                sales_loader=lambda: ({"success":True,"sales_transactions":[]},200))
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: run_morning_cycle(**args), range(2)))

    first = next(result for result in results
                 if result["status"] == "daily_manager_presented")
    concurrent_restart = next(result for result in results
                              if result["status"] == "daily_manager_replay_suppressed")
    assert concurrent_restart["telegram_sends"] == concurrent_restart["telegram_edits"] == 0
    assert loader_calls
    assert len(deliveries) == 1 and ":OWNER:" in deliveries[0]
    assert deliveries[0].endswith(":DELIVERY")


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
    assert failed["status"] == "morning_runtime_recovery_pending"
    assert failed["telegram_sends"] == failed["telegram_edits"] == 0
    assert len(deliveries) == 1
    assert deliveries[0].startswith("OOM-DAILY-FARM-MANAGER-2026-08-13:OWNER:")
    assert deliveries[0].endswith(":DELIVERY")


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


def test_shared_plan_projects_once_per_owner_with_language_and_scoped_identity():
    events, deliveries, loads = {}, [], []
    def store(action, identity, payload):
        if action == "load_daily":
            return None
        if action == "load_answered_questions":
            return ()
        created = identity not in events
        events.setdefault(identity, dict(payload or {}))
        return {"success": True, "created": created}
    def herd():
        loads.append("herd")
        return _specialist("herdmaster")
    def deliver(parsed, result, **kwargs):
        deliveries.append((parsed["telegram_user_id"], result["answer"], kwargs["mission_id"]))
        return {"success": True, "telegram_message_id": "m-" + parsed["telegram_user_id"],
                "telegram_sends": 1, "telegram_edits": 0}
    outcome = run_morning_cycle(now=NOW, environ=_two_manager_env(), deliver=deliver,
        store=store, herd_loader=herd, rootline_loader=lambda: _specialist("rootline"),
        litter_loader=lambda: {"allocation_inputs": {"litter_rows": []}},
        sales_loader=lambda: ({"success": True, "sales_transactions": []}, 200))
    assert outcome["status"] == "morning_runtime_recipients_projected"
    assert outcome["recipient_count"] == 2 and outcome["telegram_sends"] == 2
    assert loads == ["herd"]
    by_owner = {row[0]: row for row in deliveries}
    assert "TODAY'S FARM PLAN" in by_owner["42"][1]
    assert "VANDAG SE PLAASPLAN" in by_owner["77"][1]
    assert by_owner["42"][2] != by_owner["77"][2]
    assert all(":OWNER:" in row[2] for row in deliveries)


def test_one_recipient_provider_failure_does_not_block_other_recipient():
    events, daily, attempted, retry_provider_sends = {}, {}, [], []
    retry_lock = Lock()
    retry_barrier = __import__("threading").Barrier(2)
    concurrent_phase = [False]
    def store(action, identity, payload):
        if action == "load_daily":
            value = daily.get((identity, payload["owner_user_id"], payload["chat_id"]))
            if concurrent_phase[0] and payload["owner_user_id"] == "77" \
                    and value and value.get("status") == "provider_ambiguous":
                retry_barrier.wait(timeout=3)
            return value
        if action == "load_answered_questions": return ()
        if action == "record_daily":
            key = (payload["daily_identity"], payload.get("owner_user_id", ""),
                   payload.get("chat_id", ""))
            daily[key] = dict(payload)
            return {"success": True, "created": True}
        created = identity not in events; events.setdefault(identity, dict(payload or {}))
        return {"success": True, "created": created}
    def deliver(parsed, result, **kwargs):
        with retry_lock:
            attempted.append(parsed["telegram_user_id"])
            anton_count = attempted.count("77")
            if parsed["telegram_user_id"] == "77" and anton_count == 1:
                return {"success": False, "telegram_sends": 0, "telegram_edits": 0,
                        "delivery_definitely_not_sent": True}
            if parsed["telegram_user_id"] == "77":
                first_provider_effect = not retry_provider_sends
                if first_provider_effect: retry_provider_sends.append("anton-card")
                return {"success": True, "telegram_message_id": "anton-card",
                        "telegram_sends": int(first_provider_effect), "telegram_edits": 0}
            return {"success": True, "telegram_message_id": "charl-card", "telegram_sends": 1}
    args = dict(now=NOW, environ=_two_manager_env(), deliver=deliver,
        store=store, herd_loader=lambda: _specialist("herdmaster"),
        rootline_loader=lambda: _specialist("rootline"),
        litter_loader=lambda: {"allocation_inputs": {"litter_rows": []}},
        sales_loader=lambda: ({"success": True, "sales_transactions": []}, 200))
    outcome = run_morning_cycle(**args)
    assert attempted == ["42", "77"]
    assert outcome["success"] is False and outcome["telegram_sends"] == 1
    assert [row["status"] for row in outcome["recipient_results"]] == [
        "daily_manager_presented", "daily_manager_delivery_ambiguous"]
    concurrent_phase[0] = True
    with ThreadPoolExecutor(max_workers=2) as executor:
        recovered = list(executor.map(lambda _: run_morning_cycle(**args), range(2)))
    assert attempted.count("42") == 1 and attempted.count("77") == 3
    assert retry_provider_sends == ["anton-card"]
    assert all(row["recipient_results"][0]["status"] == "daily_manager_unchanged_silent"
               for row in recovered)
    assert sum(row["telegram_sends"] for row in recovered) == 1
    assert daily[("OOM-DAILY-FARM-MANAGER-2026-08-13", "42", "42")]["telegram_message_id"] == "charl-card"
    assert daily[("OOM-DAILY-FARM-MANAGER-2026-08-13", "77", "77")]["telegram_message_id"] == "anton-card"
