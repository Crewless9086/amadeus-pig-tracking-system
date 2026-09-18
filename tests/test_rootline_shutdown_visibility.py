"""Actual history -> specialist -> family delivery, with synthetic readbacks."""
from datetime import datetime, timedelta

import pytest

from modules.telemetry.rootline_irrigation_history import project_canonical_irrigation_history, _attach_latest_zone_executions
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_specialist_result import build_rootline_specialist_result, _project_existing_plan
from modules.oom_sakkie.rootline_daily_presentation import compose_daily_rootline_manager_item, compose_daily_rootline_plan
from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger, _rootline_irrigation_completion_summary, _rootline_irrigation_start_summary
from tests.test_rootline_specialist_result import evidence
from tests.test_oom_sakkie_rootline_reassessment_delivery import memory_store, ENV, HEADERS

NOW = datetime.fromisoformat("2026-07-29T12:00:00+02:00")


def readback(state, at):
    transport = RootlineIFTTTTransport(token_store=lambda *_: pytest.fail("token access forbidden"), environ={})
    transport._snapshot = lambda *_: {"current_outputs_authoritative": True,
        "response_digest": "synthetic-" + state, "retrieved_at": at,
        "channels": [{"channel": 2, "output_state": state}]}
    return transport.read_output_state(device_id="100204e9bc", channel=2)


def execution(kind="overdue", identity="SYNTHETIC-EXEC-1", zone="C12345"):
    row = {"execution_id": identity, "zone_id": zone, "action": "mark_active", "state": "Active",
           "shutdown_verified": False, "primary_stop_deadline": "2026-07-29T11:35:00+02:00",
           "native_fail_stop_deadline": "2026-07-29T11:35:00+02:00",
           "start_evidence": readback("ON", "2026-07-29T10:35:16+02:00")}
    if kind == "unverified":
        row.update(action="contain_zone", state="ambiguous")
    elif kind in {"late", "timely"}:
        at = "2026-07-29T11:54:24+02:00" if kind == "late" else "2026-07-29T11:34:59+02:00"
        row.update(action="record_completed", state="Completed", shutdown_verified=True,
                   objective_satisfied=True, shutdown_evidence=readback("OFF", at))
    return row


def specialist(rows=(), now=NOW, persisted=False):
    history = project_canonical_irrigation_history([], snapshot_cutoff=now)
    _attach_latest_zone_executions(history, rows)
    if persisted:
        return _project_existing_plan({"operating_date": "2026-07-29", "evidence_generation": "SYNTHETIC",
            "recent_irrigation_history": history, "candidate_tasks": []}, now)
    return build_rootline_specialist_result(evidence(irrigation_history=history), "2026-07-29", now=now)


def deliver(current, store, calls):
    def send(_parsed, result, **_kwargs):
        calls.append(result["answer"])
        return {"success": True, "telegram_message_id": str(9000 + len(calls)), "telegram_sends": 1}
    outcome, status = handle_rootline_reassessment_trigger({"owner_user_id": "42", "chat_id": "42",
        "trigger": "declared_time", "trigger_id": "SYNTHETIC", "trigger_timestamp": NOW.isoformat()},
        HEADERS, ENV, specialist_loader=lambda: current, state_store=store, family_delivery=send)
    assert status == 200
    assert outcome["hardware_commands"] == 0 and outcome["writes_farm_data"] is False
    return outcome


@pytest.mark.parametrize("persisted", [False, True])
@pytest.mark.parametrize("kind", ["overdue", "unverified", "late"])
def test_real_history_exceptions_are_visible_through_raw_and_persisted_paths(kind, persisted):
    value = specialist([execution(kind)], persisted=persisted)
    _, store = memory_store(); calls = []
    assert deliver(value, store, calls)["notify_owner"] is True
    text = calls[0]
    assert "Held safely" not in text and "No action required" not in text and ":</b> Nothing" not in text
    assert ("timing discrepancy unresolved" if kind == "late" else "Shutdown unverified") in text
    assert "11:35" in text
    manager = compose_daily_rootline_manager_item(value)
    assert "exception" in manager["title"]
    assert "minutes" not in manager["title"] and "litres" not in manager["title"]
    af = compose_daily_rootline_plan(value, language="af")
    assert ("tydsverskil onopgelos" if kind == "late" else "Afskakeling ongeverifieer") in af
    assert "Veilig teruggehou" not in af and "Geen aksie" not in af


def test_exception_replay_clock_churn_and_distinct_execution_identity():
    _, store = memory_store(); calls = []
    assert deliver(specialist([execution("unverified", "A")]), store, calls)["notify_owner"]
    assert not deliver(specialist([execution("unverified", "A")], now=NOW+timedelta(minutes=5)), store, calls)["notify_owner"]
    assert deliver(specialist([execution("unverified", "B")]), store, calls)["notify_owner"]
    assert not deliver(specialist([execution("unverified", "B")]), store, calls)["notify_owner"]
    assert len(calls) == 2


def test_newer_success_does_not_erase_an_older_unresolved_exception():
    current = specialist([execution("unverified", "OLD"), execution("timely", "NEW")])
    assert current["irrigation_lifecycle"]["C12345"]["state"] == "Completed"
    assert [row["execution_id"] for row in current["irrigation_lifecycle"]["C12345"]["execution_exceptions"]] == ["OLD"]
    _, store = memory_store(); calls = []
    assert deliver(current, store, calls)["notify_owner"]
    assert "Shutdown unverified" in compose_daily_rootline_manager_item(current)["title"]


@pytest.mark.parametrize("zone,identity,resolved", [("C12345", "A", True), ("B12345", "A", False), ("C12345", "OTHER", False)])
def test_only_exact_identity_and_zone_recovery_resolves_unverified_off(zone, identity, resolved):
    recovery = execution("timely", identity, zone)
    recovery["action"] = "record_claim_recovery"
    value = specialist([execution("unverified", "A"), recovery])
    assert bool(value["irrigation_lifecycle"]["C12345"]["execution_exceptions"]) is not resolved


def test_exact_late_recovery_keeps_deadline_discrepancy():
    recovery = execution("late", "A"); recovery["action"] = "record_claim_recovery"
    value = specialist([execution("unverified", "A"), recovery])
    assert value["irrigation_lifecycle"]["C12345"]["execution_exceptions"][0]["kind"] == "off_readback_after_deadline"


@pytest.mark.parametrize("rows,now", [([], NOW), ([execution()], NOW.replace(hour=11, minute=0)), ([execution("timely")], NOW)])
def test_routine_before_deadline_and_timely_off_remain_silent(rows, now):
    _, store = memory_store(); calls = []
    assert not deliver(specialist(rows, now=now), store, calls)["notify_owner"]
    assert calls == []


def test_direct_boundaries_use_actual_adapter_shape_without_duration_claims():
    row = execution("timely")
    assert "observed_at" not in row["shutdown_evidence"]
    assert "10:35:16 SAST" in _rootline_irrigation_start_summary("C12345", row)
    assert "11:34:59 SAST" in _rootline_irrigation_completion_summary("C12345", row)
    text = _rootline_irrigation_completion_summary("C12345", execution("late"))
    assert "11:35" in text and "11:54" in text and "discrepancy unresolved" in text
    assert "minutes" not in text and "litres" not in text


@pytest.mark.parametrize("bad_time", ["invalid", "2026-07-29T11:34:59", "2026-07-30T11:34:59+02:00"])
def test_invalid_naive_and_future_off_never_clear_shutdown_uncertainty(bad_time):
    row = execution("timely"); row["shutdown_evidence"]["retrieved_at"] = bad_time
    current = specialist([row])
    assert current["irrigation_lifecycle"]["C12345"]["execution_exceptions"][0]["kind"] == "shutdown_unverified"
    assert "Shutdown unverified" in compose_daily_rootline_plan(current)


def test_legacy_timestamp_readback_remains_compatible():
    row = execution("late")
    for key in ("start_evidence", "shutdown_evidence"):
        row[key]["observed_at"] = row[key].pop("retrieved_at")
    assert "timing discrepancy unresolved" in compose_daily_rootline_plan(specialist([row]))


@pytest.mark.parametrize("deadlines", [{}, {"primary_stop_deadline": "invalid"},
    {"primary_stop_deadline": "2026-07-29T11:35:00+02:00", "native_fail_stop_deadline": "2026-07-29T11:30:00+02:00"}])
def test_verified_off_does_not_prove_missing_malformed_or_inverted_deadline_met(deadlines):
    row = execution("timely")
    row.pop("primary_stop_deadline"); row.pop("native_fail_stop_deadline")
    row.update(deadlines)
    text = compose_daily_rootline_plan(specialist([row]))
    assert "Controller OFF verified; shutdown deadline timing is unknown" in text
    assert "No action required" not in text


def test_conflicting_readback_timestamps_cannot_certify_shutdown():
    row = execution("timely")
    row["shutdown_evidence"]["observed_at"] = "2026-07-29T11:54:24+02:00"
    text = compose_daily_rootline_plan(specialist([row]))
    assert "Shutdown unverified" in text
    assert "controller OFF verification is unavailable" in _rootline_irrigation_completion_summary("C12345", row)


def test_later_off_row_does_not_erase_an_already_recorded_deadline_discrepancy():
    later = execution("timely", "A"); later["action"] = "record_claim_recovery"
    current = specialist([execution("late", "A"), later])
    assert "timing discrepancy unresolved" in compose_daily_rootline_plan(current)


def test_recovery_flag_without_its_own_readback_cannot_borrow_earlier_evidence():
    contained = execution("unverified", "A")
    contained["shutdown_evidence"] = readback("OFF", "2026-07-29T11:34:59+02:00")
    recovery = {"execution_id": "A", "zone_id": "C12345", "action": "record_claim_recovery", "shutdown_verified": True}
    assert "Shutdown unverified" in compose_daily_rootline_plan(specialist([contained, recovery]))


@pytest.mark.parametrize("action", [None, "mark_active"])
def test_direct_coordinator_completion_payload_retains_deadline_discrepancy(action):
    row = execution("late")
    if action is None:
        row.pop("action")
    else:
        row["action"] = action
    text = _rootline_irrigation_completion_summary("C12345", row)
    assert "11:35" in text and "11:54" in text and "timing discrepancy unresolved" in text
