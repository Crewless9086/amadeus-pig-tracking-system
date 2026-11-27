"""External HA reports reconcile command duties without becoming physical proof."""
from copy import deepcopy
from datetime import timedelta

import pytest

from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_home_assistant as ha
from modules.telemetry.rootline_borehole_commissioning import (
    advance_borehole_execution, build_borehole_runtime_eligibility)
from modules.telemetry.rootline_borehole_conditions import advance_conditions
from modules.telemetry.rootline_ifttt_transport import output_evidence_from_snapshot
from tests.test_rootline_command_mode import route, receipt, ENV, NOW
from tests.test_rootline_home_assistant import fixture


def reported(*, now=NOW, changed=None, state="OFF", **changes):
    value = route("1002851416", now=now, reported=state)
    value.update(reported_state_source="home_assistant_entity_report_not_independently_verified",
        reported_state_changed_at=(changed or now-timedelta(minutes=1)).isoformat(),
        reported_state_updated_at=(changed or now-timedelta(minutes=1)).isoformat(), **changes)
    value["response_digest"] = ca.digest({k:v for k,v in value.items() if k != "response_digest"})
    return output_evidence_from_snapshot(value, device_id="1002851416", channel=1)


def active():
    start = NOW-timedelta(hours=10)
    item = {"execution_id":"ROOTLINE-BOREHOLE-EXTERNAL-OFF-TEST", "device_id":"1002851416",
        "channel":1, "acceptance_mode":ca.MODE, "state":"Active", "on_attempts":1,
        "claimed_at":start.isoformat(), "stop_mode":"conditions", "primary_stop_deadline":None,
        "contract_version":"rootline_borehole_runtime_eligibility.v5", "native_fail_stop_deadline":None,
        "requested_seconds":None, "native_fail_stop_seconds":0,
        "device_key":"ewelink:ewelink_owner_account:1002851416:1",
        "auxiliary_device_id":"BOREHOLE-1-MINI-R4-CH1"}
    item["command_on_receipt"] = receipt(item, "ON", at=start)
    return item


class Store:
    def __init__(self, item=None):
        self.active = active() if item is None else item
        self.rows = []
    def __call__(self, action, body):
        if action == "load_active_borehole": return deepcopy(self.active)
        if action == "load_borehole_off_attempts":
            return [r for r in self.rows if r.get("execution_id")==body and r["action"]=="record_borehole_off_outcome"]
        if action == "dispatch_borehole_on_edge": return body["dispatch"]()
        if action == "dispatch_borehole_off_edge":
            if any(r.get("execution_id")==body["execution_id"] and r.get("attempt")==body["attempt"] for r in self.rows):
                return {"provider_command_attempted":False}
            result=body["dispatch"]()
            self.rows.append({"action":"record_borehole_off_outcome","execution_id":body["execution_id"],
                "attempt":body["attempt"],"outcome":result})
            return result
        if action == "record_borehole_completed": self.active=None
        if action in {"claim_borehole_before_on","mark_borehole_active"}:self.active=deepcopy(body)
        self.rows.append({**deepcopy(body), "action":action})
        return {"success":True,"created":True}


class Transport:
    def __init__(self, store, report=None):
        self.store=store; self.report=reported() if report is None else report; self.commands=[]; self.reject=False
    def read_output_state(self, **kwargs): return deepcopy(self.report)
    def set_state(self, **kwargs):
        self.commands.append(kwargs)
        if self.reject:return {"provider_command_attempted":True,"accepted_unambiguous":False}
        return receipt(self.store.active, kwargs["state"], at=NOW,
            attempt=1 if kwargs["state"]=="ON" else int(kwargs["idempotency_key"].rsplit(":",1)[1]))


def advance(store, transport, **kwargs):
    return advance_borehole_execution(eligibility={}, store=store, transport=transport,
        now=NOW, clock=lambda:NOW, **kwargs)


def test_later_external_off_closes_only_old_command_duty_and_replay_does_not_send_on():
    store=Store(); transport=Transport(store)
    result=advance(store,transport)
    assert result["status"]=="borehole_off_command_accepted"
    assert [x["state"] for x in transport.commands]==["OFF"]
    assert store.active is None
    terminal=result["execution"]
    assert terminal["stop_reason"]=="external_off_reported"
    assert terminal["command_duty_closed"] and not terminal["shutdown_verified"]
    assert terminal["physical_state"]=="Unverified" and not terminal["objective_satisfied"]
    assert terminal["stop_trigger"]["reported_off_evidence"]["command_route"]["reported_output_state"]=="OFF"
    advance(store,transport)
    assert [x["state"] for x in transport.commands]==["OFF"]


@pytest.mark.parametrize("fault",["old", "equal", "on", "unknown", "unavailable", "missing_clock",
    "future", "inverted", "wrong_source", "wrong_digest", "missing_report", "stale_route"])
def test_stale_or_unsupported_report_does_not_retire_or_reissue_on(fault):
    store=Store(); value=reported(); r=value["command_route"]
    if fault=="old":r["reported_state_changed_at"]=(NOW-timedelta(hours=11)).isoformat()
    if fault=="equal":r["reported_state_changed_at"]=store.active["claimed_at"]
    if fault in {"on","unknown","unavailable"}:r["reported_output_state"]=fault.upper()
    if fault=="missing_clock":r.pop("reported_state_changed_at")
    if fault=="future":r["reported_state_updated_at"]=(NOW+timedelta(seconds=1)).isoformat()
    if fault=="inverted":r["reported_state_updated_at"]=(NOW-timedelta(minutes=2)).isoformat()
    if fault=="wrong_source":r["reported_state_source"]="made_up"
    if fault=="stale_route":r["route_checked_at"]=(NOW-timedelta(minutes=6)).isoformat()
    r["response_digest"]=ca.digest({k:v for k,v in r.items() if k!="response_digest"})
    if fault=="wrong_digest":r["response_digest"]="a"*64
    if fault=="missing_report":value={}
    transport=Transport(store,value)
    result=advance(store,transport)
    assert result["status"]=="borehole_command_duty_active"
    assert store.active is not None and transport.commands==[]


def test_failed_reconciliation_off_remains_contained_without_on_retry():
    store=Store(); transport=Transport(store);transport.reject=True
    result=advance(store,transport)
    assert result["status"]=="borehole_off_command_unknown" and store.active is not None
    assert [x["state"] for x in transport.commands]==["OFF"]*3
    advance(store,transport)
    assert len(transport.commands)==3


def test_interrupted_read_keeps_duty_and_checks_owned_deadlines_after_read():
    from modules.telemetry.rootline_owned_deadlines import owned_deadline_checkpoint
    store=Store(); order=[]
    class Interrupted(Transport):
        def read_output_state(self,**kwargs):
            order.append("read")
            raise TimeoutError("synthetic read unavailable")
    transport=Interrupted(store)
    with owned_deadline_checkpoint(lambda **kwargs:order.append("deadline")):
        result=advance(store,transport)
    assert result["status"]=="borehole_command_duty_active"
    assert order==["deadline","read","deadline"]
    assert store.active is not None and transport.commands==[]


def test_owned_deadline_checkpoint_precedes_reconciliation_off():
    from modules.telemetry.rootline_owned_deadlines import owned_deadline_checkpoint
    store=Store();order=[]
    class Delayed(Transport):
        def read_output_state(self,**kwargs):
            order.append("read_crossed_deadline")
            return super().read_output_state(**kwargs)
        def set_state(self,**kwargs):
            order.append("off")
            return super().set_state(**kwargs)
    with owned_deadline_checkpoint(lambda **kwargs:order.append("deadline")):
        advance(store,Delayed(store))
    assert order==["deadline","read_crossed_deadline","deadline","off"]


def test_explicit_stop_uses_existing_stop_reason_and_does_not_reconcile_on():
    store=Store();transport=Transport(store,reported(state="ON"))
    result=advance(store,transport,stop_for_energy=True,stop_reason="manual_off_active")
    assert result["execution"]["stop_reason"]=="manual_off_active"
    assert [x["state"] for x in transport.commands]==["OFF"]


def test_adopted_on_uses_claim_barrier_without_inventing_on_receipt():
    item=active();item.update(execution_origin="ha_reported_external_on",on_attempts=0,
        command_on_receipt=None,original_start_at=None,provider_start_evidence=None,
        command_adoption_evidence=reported(now=NOW-timedelta(hours=10),state="ON"))
    store=Store(item);transport=Transport(store)
    result=advance(store,transport)
    assert result["status"]=="borehole_off_command_accepted"
    assert result["execution"]["commanded_runtime_seconds"]==0


def test_retired_duty_renews_condition_opportunity_and_new_identity_but_manual_isolation_blocks():
    prior={"opportunity_id":"old","last_owned_execution_id":active()["execution_id"]}
    weather={"fresh":True,"dry_hour":True,"observed_at":NOW.isoformat(),"rain_detected":False}
    conditions=advance_conditions(prior,weather=weather,forecast=None,active=None,now=NOW)
    assert conditions["opportunity_id"]!="old" and conditions["last_owned_execution_id"] is None
    args=dict(need={"eligible":True},baseline={"current":True,"stop_mode":"conditions",
        "registry_generation":3,"baseline_sha256":"b"*64,"maximum_routine_runtime_seconds":0,
        "native_fail_stop_seconds":0},authority={"inside_standing_authority":True},
        provider=reported(),energy={"eligible":True},requested_seconds=None,now=NOW)
    with ca.scope(ENV):
        new=build_borehole_runtime_eligibility(**args,interlocks={},conditions={**conditions,"event_id":"ROOTLINE-EXEC-"+"C"*32})
        isolated=build_borehole_runtime_eligibility(**args,interlocks={"manual_off_active":True},conditions={**conditions,"event_id":"ROOTLINE-EXEC-"+"C"*32})
    assert new["eligible"] and new["execution_id"]!=active()["execution_id"]
    assert not isolated["eligible"]
    store=Store();transport=Transport(store)
    advance(store,transport)
    with ca.scope(ENV):
        restarted=advance_borehole_execution(eligibility=new,store=store,transport=transport,
            now=NOW,clock=lambda:NOW)
    assert restarted["status"]=="borehole_on_command_accepted"
    assert restarted["execution"]["execution_id"]==new["execution_id"]
    # The same cached pre-ON OFF report cannot close the newly accepted duty.
    assert advance(store,transport)["status"]=="borehole_command_duty_active"
    assert [x["state"] for x in transport.commands]==["OFF","ON"]


def test_actual_command_route_preserves_original_entity_clocks_without_hardware_authority():
    devices,entities,states=fixture("1002851416")
    changed=(NOW-timedelta(hours=2)).isoformat()
    states[0].update(last_changed=changed,last_updated=changed)
    topic="cube2ha/switch/1002851416/power/state"
    debug={"entities":[{"entity_id":entities[0]["entity_id"],"discovery_data":{"payload":{
        "unique_id":entities[0]["unique_id"],"platform":"switch","state_topic":topic,
        "command_topic":topic[:-5]+"set","value_template":"{{ value_json.state }}",
        "availability_topic":"cube2ha/1002851416/availability",
        "device":{"identifiers":"1002851416","manufacturer":"SONOFF","model":"MINIR4"}}}}]}
    class Client:
        def __init__(self,_):pass
        def __enter__(self):return self
        def __exit__(self,*_):pass
        def request(self,kind,**kwargs):return {"config/device_registry/list":devices,
            "config/entity_registry/list":entities,"mqtt/device/debug_info":debug}[kind]
        def states(self):return states
    result=ha.read_command_route("1002851416",environ=ENV,now=NOW,client_factory=Client)
    assert result["reported_state_changed_at"]==changed==result["reported_state_updated_at"]
    assert not result["current_outputs_authoritative"] and not result["observation_fresh"]
    assert ca.route_valid(result,device_id="1002851416",channel=1,now=NOW)
