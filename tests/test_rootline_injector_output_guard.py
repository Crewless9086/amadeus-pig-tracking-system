"""Real projection, initial/final dependency gates and owned injector OFF regressions."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from modules.telemetry.rootline_ifttt_transport import (
    RootlineIFTTTTransport, output_evidence_from_snapshot, irrigation_dependency_verified)
from modules.telemetry.rootline_execution_runtime import _refresh_active_irrigation_readback
from modules.telemetry.rootline_auxiliary_management import _injection_gate
from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
from tests import test_rootline_fertilizer_auxiliary as aux
from tests.test_rootline_ifttt_transport import irrigation_snapshot, irrigation_output

NOW = aux.NOW
LEFT = "100204e9bc"


def project(snapshot, channel=1):
    return output_evidence_from_snapshot(snapshot, device_id=LEFT, channel=channel)


def verified(output, *, channel=1, now=NOW):
    return irrigation_dependency_verified(output, device_id=LEFT, channel=channel, now=now)


@pytest.mark.parametrize("channel", [1, 2])
@pytest.mark.parametrize("age", [0, 300])
def test_complete_native_proof_accepts_only_exact_bc_and_fresh_boundary(channel, age):
    snapshot = irrigation_snapshot(NOW-timedelta(seconds=age), channel=channel)
    before = deepcopy(snapshot)
    output = project(snapshot, channel)
    assert verified(output, channel=channel)
    assert snapshot == before
    snapshot["channels"][0]["output_state"] = "Unknown"
    assert output["irrigation_output_evidence"]["channels"] == before["channels"]


@pytest.mark.parametrize("on_channels,selected,expected", [
    ([1], 1, True), ([2], 2, True), ([1,2], 1, False),
    ([1,3], 1, False), ([1,4], 1, False), ([], 1, False)])
def test_actual_readback_normalizer_and_transport_preserve_all_provider_outputs(on_channels, selected, expected):
    from tests.test_rootline_ewelink_readback import provider, Store, env, NOW as at
    from modules.telemetry.rootline_ewelink_readback import read_current_device
    request, calls = provider()
    def fake_request(method, url, **kwargs):
        value = request(method, url, **kwargs)
        if "thingList" in value:
            for row in value["thingList"][0]["itemData"]["params"]["switches"]:
                row["switch"] = "on" if row["outlet"]+1 in on_channels else "off"
        return value
    snapshot = read_current_device(token_store=Store(), environ=env(), http_request=fake_request, now=at)
    output = RootlineIFTTTTransport(token_store=None, environ={},
        readback=lambda **_: snapshot).read_output_state(device_id=LEFT, channel=selected)
    assert verified(output, channel=selected, now=at) is expected
    assert output["irrigation_output_evidence"]["channels"] == snapshot["channels"]
    assert len(calls) == 3 and all(method == "GET" for method, _ in calls)


BAD = ["both_bc", "a_on", "e_on", "unknown", "missing", "duplicate", "extra",
       "bool_channel", "string_channel", "row_not_dict", "channels_not_list", "channels_scalar",
       "wrong_device", "not_authoritative", "missing_digest", "malformed_digest", "control_call",
       "bool_control_count", "missing_time", "naive_time", "stale", "future", "selected_off"]


def malformed(case):
    value = irrigation_snapshot(NOW)
    rows = value["channels"]
    if case == "both_bc": rows[1]["output_state"] = "ON"
    elif case == "a_on": rows[3]["output_state"] = "ON"
    elif case == "e_on": rows[2]["output_state"] = "ON"
    elif case == "unknown": rows[1]["output_state"] = "Unknown"
    elif case == "missing": rows.pop()
    elif case == "duplicate": rows[-1]["channel"] = 1
    elif case == "extra": rows.append({"channel": 5, "output_state": "OFF"})
    elif case == "bool_channel": rows[0]["channel"] = True
    elif case == "string_channel": rows[0]["channel"] = "1"
    elif case == "row_not_dict": rows[3] = None
    elif case == "channels_not_list": value["channels"] = tuple(rows)
    elif case == "channels_scalar": value["channels"] = 4
    elif case == "wrong_device": value["device_id"] = "100204d497"
    elif case == "not_authoritative": value["current_outputs_authoritative"] = False
    elif case == "missing_digest": value.pop("response_digest")
    elif case == "malformed_digest": value["response_digest"] = "fake-not-native-hash"
    elif case == "control_call": value["provider_control_calls"] = 1
    elif case == "bool_control_count": value["provider_control_calls"] = False
    elif case == "missing_time": value.pop("retrieved_at")
    elif case == "naive_time": value["retrieved_at"] = NOW.replace(tzinfo=None).isoformat()
    elif case == "stale": value["retrieved_at"] = (NOW-timedelta(seconds=301)).isoformat()
    elif case == "future": value["retrieved_at"] = (NOW+timedelta(microseconds=1)).isoformat()
    elif case == "selected_off": rows[0]["output_state"] = "OFF"
    else: raise AssertionError(case)
    return value


@pytest.mark.parametrize("case", BAD)
def test_shared_projection_and_planning_gate_refuse_incomplete_or_conflicting_evidence(case):
    output = project(malformed(case))
    assert not verified(output)
    context = aux.injection_context(zone_output_evidence={**output,
        "zone_execution_id": "ZONE-EXEC-1", "observed_at": NOW.isoformat()})
    assert _injection_gate(context, NOW) is not None
    assert aux.injection_eligibility(**context)["eligible"] is False


@pytest.mark.parametrize("changes", [
    {"device_id":"100204d497"}, {"channel":2}, {"channel":True},
    {"evidence_id":"b"*64}, {"response_digest":"b"*64},
    {"observed_at":(NOW-timedelta(seconds=1)).isoformat()},
    {"retrieved_at":(NOW-timedelta(seconds=1)).isoformat()},
    {"authoritative":False}, {"irrigation_output_evidence":None}])
def test_projection_envelope_conflicts_do_not_verify(changes):
    assert not verified({**irrigation_output(NOW), **changes})


@pytest.mark.parametrize("changes", [
    {"active_zone_ids":["C12345"]}, {"zone_device_id":"100204d497"},
    {"zone_channel":2}, {"zone_channel":True}, {"zone_channel":None}])
def test_context_zone_and_provider_mapping_cannot_be_crossed(changes):
    assert _injection_gate(aux.injection_context(**changes), NOW) == "active_irrigation_outputs_unverified"


def test_selected_off_readback_survives_unknown_siblings_and_missing_proof():
    value = irrigation_snapshot(NOW, states={1:"OFF", 2:"Unknown", 3:"ON"})
    value.pop("response_digest")
    output = RootlineIFTTTTransport(token_store=None, environ={},
        readback=lambda **_:value).read_output_state(device_id=LEFT, channel=1)
    assert output["authoritative"] is True and output["state"] == "OFF"
    assert not verified(output)


@pytest.mark.parametrize("failure", ["raises", "missing", "stale", "both_bc", "wrong_device"])
def test_failed_refresh_erases_prior_eligible_on_proof_without_mutating_input(failure):
    original = {"active_irrigation_context": aux.injection_context()}
    before = deepcopy(original)
    class Reader:
        def read_output_state(self, **kwargs):
            if failure == "raises": raise TimeoutError("offline read failed")
            return {} if failure == "missing" else project(malformed(failure))
    refreshed = _refresh_active_irrigation_readback(original, Reader(), NOW)
    assert refreshed["active_irrigation_context"]["zone_output_evidence"] == {}
    assert original == before
    assert _injection_gate(refreshed["active_irrigation_context"], NOW) == "active_zone_unverified"


class PhysicalTransport(aux.Transport):
    def __init__(self, snapshots, *, off=True, after_read=None):
        super().__init__(off=off)
        self.snapshots = snapshots
        self.left_reads = 0
        self.after_read = after_read
    def read_output_state(self, **kwargs):
        if kwargs["device_id"] != LEFT:
            return super().read_output_state(**kwargs)
        value = self.snapshots[min(self.left_reads, len(self.snapshots)-1)]
        self.left_reads += 1
        if self.after_read: self.after_read(self.left_reads)
        if isinstance(value, Exception): raise value
        return RootlineIFTTTTransport(token_store=None, environ={},
            readback=lambda **_:value).read_output_state(**kwargs)


def run(store, transport, *, now=NOW, clock=None, context=None):
    context = context or aux.injection_context()
    return advance_auxiliary_execution(eligibility=aux.injection_eligibility(**context),
        store=store, transport=transport, revalidate=lambda _:context,
        now=now, clock=clock or (lambda:now))


@pytest.mark.parametrize("case", ["both_bc", "a_on", "e_on", "unknown", "missing", "duplicate",
                                  "wrong_device", "stale", "future", "failure"])
def test_initial_native_dependency_read_never_claims_or_commands_on_conflict(case):
    value = TimeoutError("offline read") if case == "failure" else malformed(case)
    store = aux.Store(); transport = PhysicalTransport([value])
    result = run(store, transport)
    assert result["status"] == "auxiliary_irrigation_dependency_unproven"
    assert store.consumed == set() and transport.calls == []


@pytest.mark.parametrize("case", ["both_bc", "a_on", "e_on", "unknown", "missing", "stale", "failure"])
def test_race_after_claim_rechecks_inside_dispatch_consumes_attempt_and_only_stops_injector(case):
    value = TimeoutError("offline read") if case == "failure" else malformed(case)
    store = aux.Store(); transport = PhysicalTransport([irrigation_snapshot(NOW), value])
    result = run(store, transport)
    assert len(store.consumed) == 1 and transport.left_reads == 2
    assert [(r["device_id"], r["channel"], r["state"]) for r in transport.calls] == [("100204d497",1,"OFF")]
    outcome = next(row["on_outcome"] for action,row in store.rows if action == "record_auxiliary_on_outcome")
    assert outcome["provider_command_attempted"] is False
    assert outcome["status"] == "auxiliary_irrigation_dependency_unproven"
    assert result["hardware_commands"] == 1 and result["automatic_on_retry"] is False
    run(store, transport)
    assert all(r["state"] == "OFF" for r in transport.calls)


@pytest.mark.parametrize("case", ["both_bc", "a_on", "e_on", "unknown", "missing", "stale", "failure"])
def test_active_injector_loses_dependency_and_uses_own_bounded_off(case):
    value = TimeoutError("offline read") if case == "failure" else malformed(case)
    store = aux.Store(); transport = PhysicalTransport([irrigation_snapshot(NOW), irrigation_snapshot(NOW), value])
    assert run(store, transport)["status"] == "auxiliary_started"
    result = run(store, transport, now=NOW+timedelta(seconds=10))
    assert result["status"] == "auxiliary_emergency_off_verified"
    assert [(r["device_id"],r["channel"],r["state"]) for r in transport.calls] == [
        ("100204d497",1,"ON"), ("100204d497",1,"OFF")]
    assert result["irrigation_shutdown_authority_unchanged"] is True
    assert not any(action == "record_auxiliary_completed" for action,_ in store.rows)


def test_active_dependency_loss_preserves_three_off_budget_across_replay():
    store = aux.Store(); transport = PhysicalTransport([
        irrigation_snapshot(NOW), irrigation_snapshot(NOW), malformed("both_bc")], off=False)
    assert run(store, transport)["status"] == "auxiliary_started"
    for _ in range(2):
        result = run(store, transport, now=NOW+timedelta(seconds=10))
        assert result["status"] == "auxiliary_emergency_off_unverified"
    assert [r["state"] for r in transport.calls] == ["ON", "OFF", "OFF", "OFF"]
    assert len(store.off) == 3


def test_final_slow_read_past_parent_deadline_never_sends_on():
    current = [NOW]
    def after_read(number):
        if number == 2: current[0] = NOW+timedelta(seconds=1801)
    store = aux.Store(); transport = PhysicalTransport([irrigation_snapshot(NOW)], after_read=after_read)
    result = run(store, transport, clock=lambda:current[0])
    assert result["hardware_commands"] == 1
    assert [r["state"] for r in transport.calls] == ["OFF"]


@pytest.mark.parametrize("completed_pulses,required", [(0,1440),(1,720)])
@pytest.mark.parametrize("margin,delay,starts", [(0,0,True),(1,1,True),(0,1,False),(30,31,False)])
def test_final_provider_read_preserves_full_programme_and_flush_time(completed_pulses, required, margin, delay, starts):
    current = [NOW]
    context = aux.injection_context(completed_pulses=completed_pulses,
        irrigation_stop_deadline=(NOW+timedelta(seconds=required+margin)).isoformat(),
        prior_pulse_shutdown_evidence={"evidence_id":"PULSE-1-OFF",
            "zone_execution_id":"ZONE-EXEC-1", "shutdown_verified":True,
            "observed_at":(NOW-timedelta(seconds=600)).isoformat()})
    original = aux.Store()
    def store(action,payload):
        result = original(action,payload)
        return {**result,"primary_stop_deadline":context["irrigation_stop_deadline"]} if action == "load_active" else result
    def after_read(number):
        if number == 2: current[0] = NOW+timedelta(seconds=delay)
    transport = PhysicalTransport([irrigation_snapshot(NOW)], after_read=after_read)
    result = run(store,transport,context=context,clock=lambda:current[0])
    assert len(original.consumed) == 1 and transport.left_reads == 2
    assert [r["state"] for r in transport.calls] == (["ON"] if starts else ["OFF"])
    assert result["hardware_commands"] == 1
    if starts:
        assert result["status"] == "auxiliary_started"
    else:
        outcome = next(row["on_outcome"] for action,row in original.rows if action == "record_auxiliary_on_outcome")
        assert outcome["provider_command_attempted"] is False
        assert outcome["status"] == ("auxiliary_irrigation_dependency_unproven" if delay > 30
            else "auxiliary_edge_revalidation_failed")
        assert all((r["device_id"],r["channel"]) == ("100204d497",1) for r in transport.calls)
        run(store,transport,context=context,clock=lambda:current[0])
        assert all(r["state"] == "OFF" for r in transport.calls)


@pytest.mark.parametrize("aged_evidence", ["safety","context_output"])
def test_final_provider_read_rechecks_full_evidence_freshness(aged_evidence):
    current = [NOW]
    context = aux.injection_context()
    if aged_evidence == "context_output":
        at = NOW-timedelta(seconds=300)
        context["zone_output_evidence"] = {**irrigation_output(at),
            "zone_execution_id":"ZONE-EXEC-1","observed_at":at.isoformat()}
    def after_read(number):
        if number == 2: current[0] = NOW+timedelta(seconds=1)
    transport = PhysicalTransport([irrigation_snapshot(NOW),
        irrigation_snapshot(NOW+timedelta(seconds=1))], after_read=after_read)
    if aged_evidence == "safety":
        transport.read_safety_configuration = lambda **_:aux.safety(
            observed_at=(NOW-timedelta(seconds=300)).isoformat())
    store = aux.Store()
    result = run(store,transport,context=context,clock=lambda:current[0])
    assert len(store.consumed) == 1 and transport.left_reads == 2
    assert result["hardware_commands"] == 1
    assert [(r["device_id"],r["channel"],r["state"]) for r in transport.calls] == [("100204d497",1,"OFF")]
    outcome = next(row["on_outcome"] for action,row in store.rows if action == "record_auxiliary_on_outcome")
    assert outcome["provider_command_attempted"] is False
    assert outcome["status"] == "auxiliary_edge_revalidation_failed"


@pytest.mark.parametrize("parent_changes", [
    {"device_id":"100204d497"}, {"channel":True}, {"channel":2},
    {"zone_id":"C12345"}, {"state":"Completed"}, {"execution_id":"OTHER"}])
def test_canonical_parent_mapping_and_identity_fail_closed(parent_changes):
    original = aux.Store()
    def store(action,payload):
        result = original(action,payload)
        return {**result,**parent_changes} if action == "load_active" else result
    transport = PhysicalTransport([irrigation_snapshot(NOW)])
    assert run(store,transport)["status"] == "auxiliary_irrigation_dependency_unproven"
    assert transport.calls == []


def test_exact_c_parent_starts_once_and_remains_active_with_other_outputs_off():
    context = aux.injection_context(active_zone_ids=["C12345"],zone_channel=2,
        zone_output_evidence={**irrigation_output(NOW,channel=2),"zone_execution_id":"ZONE-EXEC-1",
            "observed_at":NOW.isoformat()})
    original = aux.Store()
    def store(action,payload):
        result = original(action,payload)
        return {**result,"zone_id":"C12345","channel":2} if action == "load_active" else result
    transport = PhysicalTransport([irrigation_snapshot(NOW,channel=2)])
    assert run(store,transport,context=context)["status"] == "auxiliary_started"
    assert run(store,transport,context=context,now=NOW+timedelta(seconds=10))["status"] == "auxiliary_active"
    assert [r["state"] for r in transport.calls] == ["ON"]



@pytest.mark.parametrize("age", [0,300])
def test_injection_history_accepts_exact_existing_five_minute_boundary(age):
    context=aux.injection_context(fertilizer_history_complete_through=(
        NOW-timedelta(seconds=age)).isoformat())
    assert _injection_gate(context,NOW) is None


@pytest.mark.parametrize("cutoff", [None,"", "not-a-time", NOW.replace(tzinfo=None).isoformat(),
    (NOW+timedelta(microseconds=1)).isoformat(),
    (NOW-timedelta(seconds=300,microseconds=1)).isoformat()])
def test_injection_refuses_missing_naive_future_or_stale_canonical_history(cutoff):
    context=aux.injection_context(fertilizer_history_complete_through=cutoff)
    assert _injection_gate(context,NOW) == "current_day_fertilizer_history_incomplete"
    assert aux.injection_eligibility(**context)["eligible"] is False


@pytest.mark.parametrize("crosses_midnight", [False,True])
def test_final_edge_preserves_canonical_history_age_and_sast_day_on_replay(crosses_midnight):
    start = datetime(2026,8,25,21,59,59,500000,tzinfo=timezone.utc) if crosses_midnight else NOW
    current=[start]
    cutoff=start if crosses_midnight else start-timedelta(seconds=300)
    context=aux.injection_context(fertilizer_history_complete_through=cutoff.isoformat(),
        zone_start_evidence={"evidence_id":"START-1","zone_execution_id":"ZONE-EXEC-1",
            "observed_at":(start-timedelta(minutes=10)).isoformat()},
        zone_output_evidence={**irrigation_output(start),"zone_execution_id":"ZONE-EXEC-1",
            "observed_at":start.isoformat()},
        irrigation_stop_deadline=(start+timedelta(seconds=1800)).isoformat())
    from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
    eligibility=build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
        context=context,safety=aux.safety(observed_at=start.isoformat()),
        flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=start)
    assert eligibility["eligible"] is True
    original=aux.Store()
    def store(action,payload):
        value=original(action,payload)
        return {**value,"primary_stop_deadline":context["irrigation_stop_deadline"]} if action == "load_active" else value
    def after_read(number):
        if number == 2: current[0]=start+timedelta(seconds=1)
    transport=PhysicalTransport([irrigation_snapshot(start),irrigation_snapshot(start+timedelta(seconds=1))],
        after_read=after_read)
    transport.read_safety_configuration=lambda **_:aux.safety(observed_at=start.isoformat())
    def execute():
        return advance_auxiliary_execution(eligibility=eligibility,store=store,transport=transport,
            revalidate=lambda _:context,now=start,clock=lambda:current[0])
    result=execute()
    assert len(original.consumed) == 1 and transport.left_reads == 2
    assert [(r["device_id"],r["channel"],r["state"]) for r in transport.calls] == [("100204d497",1,"OFF")]
    outcome=next(row["on_outcome"] for action,row in original.rows if action == "record_auxiliary_on_outcome")
    assert outcome["provider_command_attempted"] is False
    assert outcome["status"] == "auxiliary_edge_revalidation_failed"
    assert result["automatic_on_retry"] is False
    execute()
    assert len(original.consumed) == 1 and all(r["state"] == "OFF" for r in transport.calls)
    assert context["fertilizer_history_complete_through"] == cutoff.isoformat()


def test_active_parent_read_crossing_own_120_second_deadline_stops_now():
    current = [NOW]
    store = aux.Store()
    def after_read(number):
        if number == 3:
            current[0] = NOW+timedelta(seconds=121)
    transport = PhysicalTransport([irrigation_snapshot(NOW)], after_read=after_read)
    assert run(store, transport, clock=lambda:current[0])["status"] == "auxiliary_started"
    current[0] = NOW+timedelta(seconds=119)
    result = run(store, transport, now=current[0], clock=lambda:current[0])
    assert result["status"] != "auxiliary_active"
    assert [row["state"] for row in transport.calls] == ["ON", "OFF"]


@pytest.mark.parametrize("injection_enabled", [True, False])
def test_due_final_flush_reads_once_and_completed_sequence_stops_optional_reading(injection_enabled):
    from modules.telemetry.rootline_auxiliary_management import injection_parent_read_due
    context = aux.injection_context(completed_pulses=2,
        prior_pulse_shutdown_evidence={"zone_execution_id":"ZONE-EXEC-1", "shutdown_verified":True,
            "observed_at":(NOW-timedelta(seconds=599)).isoformat()})
    assert not injection_parent_read_due(context, now=NOW)
    assert injection_parent_read_due(context, now=NOW+timedelta(seconds=1))
    assert not injection_parent_read_due({**context,"controller_sequence_completed":True},
        now=NOW+timedelta(seconds=1))
    reads=[]
    class Reader:
        def read_output_state(self, **kwargs):
            reads.append(kwargs)
            return irrigation_output(NOW+timedelta(seconds=1))
    if not injection_enabled:
        disabled = _refresh_active_irrigation_readback(
            {"active_irrigation_context":aux.injection_context()}, Reader(), NOW,
            only_when_due=True, injection_enabled=False, clock=lambda:NOW)
        assert not reads and disabled["active_irrigation_context"]["zone_output_evidence"] == {}
    before = _refresh_active_irrigation_readback({"active_irrigation_context":context}, Reader(), NOW,
        only_when_due=True, injection_enabled=injection_enabled, clock=lambda:NOW)
    assert not reads and before["active_irrigation_context"]["zone_output_evidence"] == {}
    due = _refresh_active_irrigation_readback({"active_irrigation_context":context}, Reader(),
        NOW+timedelta(seconds=1), only_when_due=True, injection_enabled=injection_enabled,
        clock=lambda:NOW+timedelta(seconds=1))
    assert len(reads) == 1 and due["active_irrigation_context"]["zone_output_evidence"]["state"] == "ON"
