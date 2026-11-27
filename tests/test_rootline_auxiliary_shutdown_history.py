"""Offline replay of canonical mixed-mode history; no provider/database calls."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

import pytest

from modules.telemetry.rootline_irrigation_lifecycle import auxiliary_shutdown_unverified
from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context
from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_command_mode import ENV, Store, Transport, completed_command_mix_rows


CAPTURE = json.loads((Path(__file__).parent / "fixtures/rootline_auxiliary_closure_history.json").read_text())
NOW = datetime.fromisoformat(CAPTURE["observed_at"])
# Later-stage injector tests use a synthetic confirmed parent, while the captured
# auxiliary shutdown rows and the immutable on-disk replay remain untouched.
from tests.test_rootline_command_mode import confirm_fixture
_parent = CAPTURE["active_irrigation_context"]["command_parent_execution"]
confirm_fixture(_parent, at=datetime.fromisoformat(_parent["command_on_receipt"]["accepted_at"])+timedelta(seconds=1))


def history():
    return deepcopy(CAPTURE["fertilizer_executions"])


def unresolved(rows):
    return auxiliary_shutdown_unverified(rows, evidence_cutoff=NOW)


def test_three_captured_physical_shutdowns_close_without_rewriting_history():
    rows = history()
    before = deepcopy(rows)
    held = [r for r in rows if r["action"] == "contain_auxiliary_device"]
    assert len(held) == 3
    assert "channel" not in held[0]["shutdown_evidence"]
    assert not unresolved(rows)
    for item in held:
        assert not unresolved([r for r in rows if r["execution_id"] == item["execution_id"]])
    assert rows == before


@pytest.mark.parametrize("field,value", [
    ("shutdown_verified", False), ("shutdown_verified", "true"),
    ("device_id", "other"), ("channel", 1), ("channel", True),
    ("auxiliary_device_id", "FERTILIZER-INJECTION-CH1"),
    ("execution_id", "other"), ("claimed_at", "bad"),
    ("consumption_key", "other"), ("maximum_duration_seconds", 120),
    ("acceptance_mode", "command_accepted"),
])
def test_conflicting_canonical_terminal_cannot_close(field, value):
    rows = history()
    rows[-1][field] = value
    assert unresolved(rows)


@pytest.mark.parametrize("field,value", [
    ("authoritative", False), ("authoritative", "true"), ("state", "ON"),
    ("device_id", "other"), ("channel", 1), ("channel", True),
    ("execution_id", "other"), ("retrieved_at", "bad"),
    ("retrieved_at", "2026-11-20T13:05:02"),
    ("retrieved_at", "2026-11-19T00:00:00+00:00"),
    ("retrieved_at", "2026-11-23T00:00:00+00:00"),
    ("observed_at", "2026-11-20T13:06:02+00:00"),
    ("evidence_id", ""), ("evidence_id", "x" * 64),
])
def test_provider_proof_conflicts_and_malformed_times_stay_unknown(field, value):
    rows = history()
    rows[-1]["shutdown_evidence"][field] = value
    assert unresolved(rows)


@pytest.mark.parametrize("field", ["device_id", "channel", "execution_id", "claimed_at", "consumption_key"])
def test_missing_enclosing_claim_or_terminal_binding_is_not_compact_readback(field):
    rows = history()
    del rows[-1][field]
    assert unresolved(rows)
    rows = history()
    del rows[-3][field]
    assert unresolved(rows)


@pytest.mark.parametrize("field", ["device_id", "channel", "evidence_id", "retrieved_at"])
def test_partial_nested_binding_or_missing_proof_is_not_legacy_compact_shape(field):
    rows = history()
    del rows[-1]["shutdown_evidence"][field]
    assert unresolved(rows)


@pytest.mark.parametrize("fault", ["missing_claim", "missing_off", "wrong_execution", "wrong_event", "ambiguous", "wrong_status"])
def test_compact_shape_requires_same_claim_and_bound_off_outcome(fault):
    rows = history()[:3]
    if fault == "missing_claim": rows.pop(0)
    elif fault == "missing_off": rows.pop(1)
    elif fault == "wrong_execution": rows[1]["execution_id"] = "other"
    elif fault == "wrong_event": rows[1]["outcome"]["event"] = "controller_1_ch1_off"
    elif fault == "ambiguous": rows[1]["outcome"]["accepted_unambiguous"] = False
    elif fault == "wrong_status": rows[1]["outcome"]["provider_status"] = 500
    assert unresolved(rows)


@pytest.mark.parametrize("action", ["claim_auxiliary_before_on", "mark_auxiliary_active", "record_auxiliary_on_outcome",
    "claim_auxiliary_off_attempt", "record_auxiliary_off_outcome", "contain_auxiliary_device"])
def test_later_reopened_or_unresolved_duty_overrides_earlier_off(action):
    rows = history()
    rows.append({**rows[-3], "action": action, "shutdown_verified": False})
    assert unresolved(rows)


def test_earlier_unresolved_hold_can_close_with_later_exact_physical_off():
    rows = history()
    rows.insert(len(rows)-1, {**rows[-1], "shutdown_verified": False,
        "shutdown_evidence": {"authoritative": False, "state": "Unknown"}})
    assert not unresolved(rows)


def command_rows():
    claimed = NOW-timedelta(minutes=20)
    rows = completed_command_mix_rows("OFFLINE-COMMAND-MIX", claimed, claimed+timedelta(seconds=601), "OFFLINE-BATCH")
    for row in rows:
        if "device_id" in row:
            row["consumption_key"] = "OFFLINE-COMMAND-CONSUME"
    rows.insert(2, {**rows[0], "action": "contain_auxiliary_device", "shutdown_verified": False})
    return rows


def test_valid_command_terminal_and_physical_records_share_closure_projection():
    assert not unresolved(history()+command_rows())


@pytest.mark.parametrize("fault", ["missing_off", "wrong_receipt", "wrong_execution", "wrong_device", "wrong_channel", "false_physical", "reopen"])
def test_command_closure_still_requires_exact_receipt_and_canonical_terminal(fault):
    rows = command_rows()
    if fault == "missing_off": rows.pop(-2)
    elif fault == "wrong_receipt": rows[-1]["command_off_receipt"]["receipt_sha256"] = "0"*64
    elif fault == "wrong_execution": rows[-2]["execution_id"] = "other"
    elif fault == "wrong_device": rows[-1]["command_off_receipt"]["device_id"] = "other"
    elif fault == "wrong_channel": rows[-1]["command_off_receipt"]["channel"] = 1
    elif fault == "false_physical": rows[-1]["shutdown_verified"] = True
    elif fault == "reopen": rows.append(deepcopy(rows[2]))
    assert unresolved(history()+rows)


def test_same_evidence_digest_cannot_close_another_execution():
    rows = history()
    rows[-1]["shutdown_evidence"] = deepcopy(rows[2]["shutdown_evidence"])
    assert unresolved(rows)


@pytest.mark.parametrize("command_parent", [True, False])
def test_both_parent_modes_use_identical_historical_closure(command_parent):
    active = deepcopy(CAPTURE["active_irrigation_context"]["command_parent_execution"])
    if not command_parent:
        active.pop("acceptance_mode")
        active["start_evidence"] = {"state": "ON", "authoritative": True, "evidence_id": "1"*64,
            "device_id": active["device_id"], "channel": active["channel"],
            "retrieved_at": active["claimed_at"]}
    context = _active_irrigation_context(active, history(), True, "OFFLINE-BATCH", now=NOW)
    assert context is not None and context["prior_shutdown_unverified"] is False
    broken = history()
    broken[-1]["shutdown_verified"] = False
    assert _active_irrigation_context(active, broken, True, "OFFLINE-BATCH", now=NOW)["prior_shutdown_unverified"]


def test_captured_b_parent_reaches_real_injector_gate_with_offline_qualified_premix():
    """Hypothetical current premix/route only; never a claim about live eligibility."""
    active = deepcopy(CAPTURE["active_irrigation_context"]["command_parent_execution"])
    context = _active_irrigation_context(active, history(), True, "OFFLINE-BATCH", now=NOW)
    store = Store()
    transport = Transport(store, lambda: NOW)
    context.update(premix_command_accepted=True, fertilizer_history_complete_through=NOW.isoformat())
    context["zone_output_evidence"] = transport.read_output_state(device_id=active["device_id"], channel=active["channel"])
    safety = transport.read_safety_configuration(device_id="100204d497", channel=1)
    with timed_control_scope(ENV):
        result = build_auxiliary_eligibility(task={"auxiliary_device_id": "FERTILIZER-INJECTION-CH1"},
            safety=safety, context=context, flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": True}, now=NOW)
        assert result["eligible"], result
        context["premix_command_accepted"] = False
        assert build_auxiliary_eligibility(task={"auxiliary_device_id": "FERTILIZER-INJECTION-CH1"},
            safety=safety, context=context, flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": True}, now=NOW)["status"] == "current_batch_premix_unproven"
    assert not transport.calls and not store.rows




@pytest.mark.parametrize("action", ["claim_auxiliary_off_attempt", "claim_auxiliary_dispatch"])
@pytest.mark.parametrize("after_terminal", [False, True])
@pytest.mark.parametrize("mode", ["physical", "command"])
def test_actual_reader_preserves_consumed_slots_and_canonical_closure_order(monkeypatch, action, after_terminal, mode):
    from tests.test_rootline_command_plan_truth import ReadConnection
    from modules.oom_sakkie import bounded_postgres_read
    from modules.telemetry.rootline_water_energy_plan import _read_managed_device_evidence
    rows = history() if mode == "physical" else command_rows()
    identity = rows[-1]["execution_id"]
    # OFF slots are canonically compact: identity+attempt, not a duplicated
    # auxiliary binding. The SQL reader must retain them before grouping.
    slot = {"action": action, "execution_id": identity, "attempt": 2}
    if action == "claim_auxiliary_dispatch":
        claim = next(row for row in reversed(rows) if row.get("action") == "claim_auxiliary_before_on")
        slot = {**deepcopy(claim), "action": action, "on_attempts": 1}
    rows.insert(len(rows) if after_terminal else len(rows)-1, slot)
    parent = deepcopy(CAPTURE["active_irrigation_context"]["command_parent_execution"])
    rows += [{**parent, "action": "claim_before_on"},
        {**parent, "action": "record_on_outcome", "on_outcome": parent["command_on_receipt"]},
        {**parent, "action": "mark_active"}]
    connection = ReadConnection(rows)
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_read", lambda **k: connection)
    with timed_control_scope(ENV):
        result = _read_managed_device_evidence("offline://fixture", NOW, evidence_cutoff=NOW)
    assert result["status"] == "Available", result
    # The cursor emulates the actual query allowlist, so this fails when a
    # consumed slot disappears at SELECT rather than reaching the projection.
    assert slot in result["fertilizer_executions"]
    assert unresolved(result["fertilizer_executions"]) is after_terminal
    assert result["active_irrigation_context"]["prior_shutdown_unverified"] is after_terminal
    assert all("order by created_at,review_event_id" in sql for sql, _ in connection.queries)
    assert all("created_at <= %s" in sql and params == (NOW,) for sql, params in connection.queries)


def aborted_startup_history():
    from tests.test_rootline_startup_command_recovery import terminal_history
    terminal, rows = terminal_history()
    return rows+[terminal]


def test_valid_never_started_abort_closes_only_its_historical_hold():
    rows = aborted_startup_history()
    before = deepcopy(rows)
    cutoff = datetime.now(timezone.utc)
    assert not auxiliary_shutdown_unverified(rows, evidence_cutoff=cutoff)
    assert rows == before
    assert rows[-1]["mixing_credit"] is False and rows[-1]["shutdown_verified"] is False
    assert auxiliary_shutdown_unverified(rows, evidence_cutoff=datetime.fromisoformat(rows[-1]["aborted_at"])-timedelta(microseconds=1))


@pytest.mark.parametrize("dispatched", [False, True])
def test_existing_physical_startup_abort_contracts_close_the_same_original_duty(dispatched):
    from tests.test_rootline_startup_command_recovery import terminal_history, event, store
    _, rows = terminal_history()
    claim = next(row for row in rows if row["action"] == "claim_auxiliary_before_on")
    held = next(row for row in rows if row["action"] == "contain_auxiliary_device")
    if dispatched:
        rows.insert(rows.index(claim)+1, event("claim_auxiliary_dispatch", claim))
    preimage = store._auxiliary_startup_abort_preimage(rows, held["event_id"])
    assert preimage is not None
    at = datetime.now(timezone.utc)
    terminal = event("record_auxiliary_startup_aborted", {**claim, **store._auxiliary_abort_binding(preimage),
        "state":"Aborted", "terminal_contract":store._AUXILIARY_STARTUP_ABORT if dispatched else store._AUXILIARY_UNSTARTED_ABORT,
        "startup_aborted_verified":True, "reservation_preserved":True, "on_authority":False,
        "objective_satisfied":False, "control_completed":False, "shutdown_verified":True,
        "provider_on_outcome":"Unknown" if dispatched else "Not dispatched", "on_attempts":int(dispatched),
        **({} if dispatched else {"startup_unstarted_verified":True}),
        "read_started_at":at.isoformat(), "read_elapsed_seconds":0,
        "aborted_at":at.isoformat(), "shutdown_evidence":{"authoritative":True,"state":"OFF",
            "device_id":claim["device_id"],"channel":claim["channel"],"evidence_id":"a"*64,"retrieved_at":at.isoformat()}})
    rows.append(terminal)
    assert store._verified_auxiliary_startup_abort(terminal, rows)
    assert not auxiliary_shutdown_unverified(rows, evidence_cutoff=at)


@pytest.mark.parametrize("fault", ["forged", "duplicate", "late_claim", "late_dispatch", "late_on", "late_off", "late_hold"])
def test_aborted_startup_cannot_hide_forged_or_later_duty(fault):
    rows = aborted_startup_history()
    if fault == "forged": rows[-1]["off_outcome_sha256"] = "0"*64
    elif fault == "duplicate": rows.append(deepcopy(rows[-1]))
    else:
        action = {"late_claim":"claim_auxiliary_before_on", "late_dispatch":"claim_auxiliary_dispatch",
            "late_on":"record_auxiliary_on_outcome", "late_off":"claim_auxiliary_off_attempt",
            "late_hold":"contain_auxiliary_device"}[fault]
        rows.append({"execution_id":rows[-1]["execution_id"], "action":action})
    assert auxiliary_shutdown_unverified(rows, evidence_cutoff=datetime.now(timezone.utc))


@pytest.mark.parametrize("closed", [True, False])
def test_real_reader_and_managed_preparation_preserve_abort_closure_and_refusal(monkeypatch, closed):
    from tests.test_rootline_command_plan_truth import ReadConnection
    from tests.test_rootline_command_mode import start
    from modules.oom_sakkie import bounded_postgres_read
    from modules.telemetry import rootline_execution_runtime as runtime
    from modules.telemetry import rootline_managed_devices_runtime as managed
    from modules.telemetry.rootline_water_energy_plan import _read_managed_device_evidence
    now = datetime.now(timezone.utc)
    rows = aborted_startup_history()
    if not closed: rows.pop()
    _, _, memory, transport, clock = start("E12345", at=now-timedelta(seconds=660))
    clock[0] = now
    connection = ReadConnection(rows+memory.rows)
    monkeypatch.setattr(bounded_postgres_read, "connect_bounded_read", lambda **k: connection)
    with timed_control_scope(ENV):
        evidence = _read_managed_device_evidence("offline://fixture", now, evidence_cutoff=now)
    context = evidence["active_irrigation_context"]
    assert context["prior_shutdown_unverified"] is (not closed)
    # These current premix/route inputs are explicitly hypothetical. The old
    # abort rows and production reader/preparation paths remain unmodified.
    context.update(premix_command_accepted=True, fertilizer_needed=True,
        fertilizer_history_complete_through=now.isoformat(), batch_generation="OFFLINE-BATCH")
    evidence["owner_controls"] = {"devices":{"injection":{"fields":{"pulse_minutes":10,
        "pulses_per_60_minutes":2, "inject_camp_a":True, "inject_camp_b":True,
        "inject_camp_c":True, "inject_camp_e":True}}}}
    task = {"auxiliary_device_id":"FERTILIZER-INJECTION-CH1", "decision":"Run now"}
    monkeypatch.setattr(runtime, "project_saved_program_for_execution", lambda *a, **k: {"irrigation_auxiliary_tasks":[task]})
    reads = []
    original = transport.read_safety_configuration
    def read(**kwargs):
        reads.append(kwargs)
        return original(device_id=kwargs["device_id"], channel=kwargs["channel"])
    transport.read_safety_configuration = read
    def cycle(**kwargs):
        packet = kwargs["evidence_factory"](pending_devices=frozenset({"FERTILIZER-INJECTION-CH1"}))
        result = build_auxiliary_eligibility(task=task,
            safety=packet["auxiliary_safety"].get("FERTILIZER-INJECTION-CH1"),
            context=packet["auxiliary_contexts"]["FERTILIZER-INJECTION-CH1"],
            flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True}, now=now)
        return {**result, "short_auxiliary_duty_owned":True}
    monkeypatch.setattr(managed, "run_rootline_managed_device_cycle", cycle)
    result = runtime.run_rootline_managed_device_reassessment(environ={**ENV,"ROOTLINE_FERTILIZER_INJECTION_ENABLED":"true"},
        now=now, clock=lambda:now, database_url="offline://fixture", token_store=object(),
        store=memory, transport=transport,
        evidence_loader=lambda **k:(evidence,now.astimezone(timezone(timedelta(hours=2))).date().isoformat(),now))
    assert result["eligible"] is closed, result
    assert len(reads) == int(closed)
    if closed: assert result["maximum_duration_seconds"] == 600
    else: assert result["status"] == "fertilizer_exception_or_shutdown_unverified"
