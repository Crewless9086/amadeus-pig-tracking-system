from datetime import datetime, timedelta, timezone

from modules.telemetry.rootline_irrigation_coordinator import advance_irrigation_execution, _digest
from modules.telemetry.rootline_irrigation_execution_contract import validate_commissioning
from tests.test_rootline_irrigation_execution_contract import evidence as commissioning_evidence

NOW = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)


class Store:
    def __init__(self, active=None): self.active=active; self.rows=[]; self.contained=set()
    def __call__(self, action, payload):
        if action == "load_active": return self.active
        if action == "load_off_attempts":
            return [value for name,value in self.rows if name=="record_off_outcome"]
        if action == "load_zone_containment": return {"contained":payload in self.contained}
        if action == "claim_before_on":
            if self.active: return {"created": False}
            self.active = payload; self.rows.append((action,payload)); return {"created": True}
        if action == "claim_off_attempt":
            if any(name==action and value["attempt"]==payload["attempt"] for name,value in self.rows):
                return {"created":False}
            self.rows.append((action,payload)); return {"created":True}
        self.rows.append((action,payload))
        if action == "mark_active": self.active=payload
        if action == "contain_zone": self.contained.add(payload["zone_id"])
        if action in {"record_completed","contain_zone"}: self.active=None
        return {"created": True}


class Transport:
    def __init__(self, *, safety=True, on="accepted", readback="ON"):
        self.safety=safety; self.on=on; self.readback=readback; self.calls=[]
    def read_safety_configuration(self, **kwargs):
        if not self.safety: return {"authoritative": False}
        return {"authoritative": True, "zone_id": "B12345", "channel": 1,
                "native_inching_enabled": True, "native_inching_seconds": 3600,
                "power_restoration_state": "OFF", "schedules_enabled": False,
                "interlock_enabled": False}
    def set_state(self, **kwargs):
        self.calls.append(kwargs)
        return {"accepted_unambiguous": self.on == "accepted" or kwargs["state"] == "OFF"}
    def read_output_state(self, **kwargs):
        return {"authoritative": self.readback is not None, "state": self.readback,
                "evidence_id":"READBACK-1"}


def decision(**changes):
    commissioned=commissioning(); proof=validate_commissioning("B12345",commissioned["evidence"],now=NOW)
    value={"decision_id":"DEC-1","decision":"Run now","standing_authority":True,"zone_id":"B12345",
           "runtime_minutes":60,"execution_id":"EXEC-1","eligibility_id":"ELIG-1",
           "evidence_generation":"GEN-1","assessed_at":NOW.isoformat(),
           "commissioning_id":commissioned["commissioning_id"],
           "commissioning_generation":proof["configuration_generation"]}
    value.update(changes); value["decision_sha256"]=_digest(value); return value


def commissioning():
    raw=commissioning_evidence(); proof=validate_commissioning("B12345",raw,now=NOW)
    return {"commissioning_id":proof["commissioning_id"],"evidence":raw}


def run(store, transport, notices, value=None, now=NOW, outcome=None):
    chosen=value or decision(); commissioned=commissioning()
    return advance_irrigation_execution(decision_id=chosen["decision_id"],
        commissioning_id=commissioned["commissioning_id"], decision_reader=lambda _:chosen,
        commissioning_reader=lambda _:commissioned, store=store, transport=transport,
        notify=lambda *x:notices.append(x), outcome_reader=lambda _:outcome, now=now)


def test_missing_provider_safety_readback_disables_on():
    transport=Transport(safety=False); notices=[]
    result=run(Store(),transport,notices)
    assert result["status"]=="provider_safety_readback_unavailable"
    assert result["hardware_commands"]==0 and transport.calls==[] and notices==[]


def test_forged_decision_or_commissioning_identity_never_reaches_on():
    transport=Transport(); notices=[]; chosen=decision(); chosen["standing_authority"]=False
    result=run(Store(),transport,notices,chosen)
    assert result["status"]=="not_eligible" and transport.calls==[]


def test_exactly_one_unambiguous_on_after_durable_claim():
    store=Store(); transport=Transport(); notices=[]
    result=run(store,transport,notices)
    assert result["status"]=="segment_started"
    assert [call["state"] for call in transport.calls]==["ON"]
    assert store.rows[0][0]=="claim_before_on" and notices[0][0]=="Active"
    active=next(value for name,value in store.rows if name=="mark_active")
    assert result["execution"]==active==notices[0][1]
    assert active["state"]=="Active" and active["start_evidence"]["authoritative"] is True


def test_ambiguous_on_is_never_retried_and_uses_safe_off():
    store=Store(); transport=Transport(on="ambiguous"); notices=[]
    result=run(store,transport,notices)
    assert [call["state"] for call in transport.calls].count("ON")==1
    assert [call["state"] for call in transport.calls].count("OFF")==1
    assert result["status"]=="ambiguous_on_contained" and notices==[("Exception",notices[0][1])]
    assert result["telegram_messages"]==1


def test_accepted_on_without_authoritative_on_state_never_becomes_active():
    for state in ("OFF",None):
        store=Store(); transport=Transport(readback=state); notices=[]
        result=run(store,transport,notices)
        assert result["status"]=="start_unverified_contained"
        assert not any(name=="mark_active" for name,_ in store.rows)
        assert notices[-1][0]=="Exception"


def test_restart_before_deadline_preserves_shutdown_ownership_without_commands():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "eligibility_id":"ELIG-1","evidence_generation":"GEN-1",
            "primary_stop_deadline":(NOW+timedelta(minutes=30)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=60)).isoformat()}
    transport=Transport(); result=run(Store(active),transport,[])
    assert result["status"]=="active_segment_owned" and transport.calls==[]


def test_expired_active_segment_repeats_safe_off_and_requires_readback():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "primary_stop_deadline":(NOW-timedelta(minutes=1)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=1)).isoformat()}
    transport=Transport(readback=None); notices=[]
    result=run(Store(active),transport,notices)
    assert all(call["state"]=="OFF" for call in transport.calls)
    assert result["status"]=="shutdown_unverified" and notices[-1][0]=="Exception"


def test_off_attempt_bound_is_durable_across_restart():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "primary_stop_deadline":(NOW-timedelta(minutes=2)).isoformat(),
            "native_fail_stop_deadline":(NOW-timedelta(minutes=1)).isoformat()}
    store=Store(active)
    store.rows.extend(("record_off_outcome",{"attempt":attempt}) for attempt in (1,2,3))
    transport=Transport(readback=None); result=run(store,transport,[])
    assert result["status"]=="shutdown_unverified" and transport.calls==[]


def test_verified_segment_can_carry_canonical_objective_satisfaction():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "eligibility_id":"ELIG-1","evidence_generation":"GEN-1",
            "primary_stop_deadline":(NOW-timedelta(minutes=1)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=1)).isoformat(),
            "objective_satisfied_after_segment":True}
    store=Store(active); notices=[]
    outcome={"execution_id":"EXEC-1","observed_at":NOW.isoformat(),
             "provenance":"canonical_post_segment","objective_satisfied":True,
             "zone_id":"B12345","channel":1,"eligibility_id":"ELIG-1",
             "evidence_generation":"GEN-1","shutdown_evidence_id":"READBACK-1",
             "actor":"ROOTLINE_CANONICAL_OUTCOME"}
    outcome["outcome_sha256"]=_digest(outcome)
    active["claimed_at"]=(NOW-timedelta(minutes=61)).isoformat()
    result=run(store,Transport(readback="OFF"),notices,outcome=outcome)
    assert result["status"]=="segment_completed"
    assert result["execution"]["objective_satisfied"] is True
    assert notices==[("Completed",result["execution"])]


def test_pre_stop_objective_packet_cannot_discharge_completion():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "eligibility_id":"ELIG-1","evidence_generation":"GEN-1",
            "claimed_at":(NOW-timedelta(minutes=30)).isoformat(),
            "primary_stop_deadline":(NOW-timedelta(minutes=1)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=1)).isoformat()}
    outcome={"execution_id":"EXEC-1","observed_at":(NOW-timedelta(minutes=2)).isoformat(),
             "provenance":"canonical_post_segment","objective_satisfied":True,
             "zone_id":"B12345","channel":1,"eligibility_id":"ELIG-1",
             "evidence_generation":"GEN-1","shutdown_evidence_id":"READBACK-1",
             "actor":"ROOTLINE_CANONICAL_OUTCOME"}
    outcome["outcome_sha256"]=_digest(outcome)
    result=run(Store(active),Transport(readback="OFF"),[],outcome=outcome)
    assert result["execution"]["objective_satisfied"] is False


def test_contained_zone_cannot_restart_after_unverified_shutdown():
    active={"execution_id":"EXEC-OLD","zone_id":"B12345","channel":1,
            "primary_stop_deadline":(NOW-timedelta(minutes=1)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=1)).isoformat()}
    store=Store(active); first_transport=Transport(readback=None)
    assert run(store,first_transport,[])["status"]=="shutdown_unverified"
    next_transport=Transport()
    result=run(store,next_transport,[])
    assert result["status"]=="zone_contained" and next_transport.calls==[]


def test_second_segment_requires_new_fresh_execution_identity():
    stale=decision(assessed_at=(NOW-timedelta(minutes=16)).isoformat())
    result=run(Store(),Transport(),[],stale)
    assert result["status"]=="not_eligible" and result["hardware_commands"]==0
