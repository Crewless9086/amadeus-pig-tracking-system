from datetime import datetime, timedelta, timezone

from modules.telemetry.rootline_irrigation_coordinator import advance_irrigation_execution, _digest
from modules.telemetry.rootline_execution_authority import build_execution_eligibility
from modules.telemetry.rootline_irrigation_execution_store import RootlineExecutionStoreUnavailable
from modules.telemetry.rootline_irrigation_execution_contract import validate_commissioning
from tests.test_rootline_irrigation_execution_contract import evidence as commissioning_evidence

NOW = datetime(2026, 8, 5, 8, 0, tzinfo=timezone.utc)


class Store:
    def __init__(self, active=None): self.active=active; self.rows=[]; self.contained={}
    def __call__(self, action, payload):
        if action == "load_active": return self.active
        if action == "load_off_attempts":
            return [value for name,value in self.rows if name=="record_off_outcome"]
        if action == "load_zone_containment":
            return ({"contained":True,"evidence":self.contained[payload]}
                    if payload in self.contained else {"contained":False})
        if action == "claim_before_on":
            if self.active: return {"created": False}
            self.active = payload; self.rows.append((action,payload)); return {"created": True}
        if action == "claim_off_attempt":
            if any(name==action and value["attempt"]==payload["attempt"] for name,value in self.rows):
                return {"created":False}
            self.rows.append((action,payload)); return {"created":True}
        self.rows.append((action,payload))
        if action == "mark_active": self.active=payload
        if action == "contain_zone": self.contained[payload["zone_id"]]=payload
        if action == "release_zone_containment": self.contained.pop(payload["zone_id"],None)
        if action in {"record_completed","contain_zone"}: self.active=None
        return {"created": True, "success": True}


class Transport:
    def __init__(self, *, safety=True, on="accepted", readback="ON"):
        self.safety=safety; self.on=on; self.readback=readback; self.calls=[]
    def read_safety_configuration(self, **kwargs):
        if not self.safety: return {"authoritative": False}
        return {"authoritative": True, "zone_id": "B12345", "channel": 1,
                "native_inching_enabled": True, "native_inching_seconds": 3599,
                "power_restoration_state": "OFF", "schedules_enabled": False,
                "interlock_enabled": False, "scenes_enabled": False,
                "relevant_outputs_off": True, "controller_safety_generation":"BASELINE-1",
                "response_digest":"READBACK-1"}
    def configuration_status(self, **kwargs):
        return {"configured":True,**kwargs}
    def set_state(self, **kwargs):
        self.calls.append(kwargs)
        return {"accepted_unambiguous": self.on == "accepted" or kwargs["state"] == "OFF"}
    def read_output_state(self, **kwargs):
        return {"authoritative": self.readback is not None, "state": self.readback,
                "evidence_id":"READBACK-1","retrieved_at":NOW.isoformat()}


def decision(**changes):
    commissioned=commissioning(); proof=validate_commissioning("B12345",commissioned["evidence"],now=NOW)
    plan={"evidence_generation":"GEN-1","operating_date":"2026-08-05",
          "candidate_tasks":[{"task_id":"irrigation_B12345",
        "zone_decision":"Run now","recommendation":"Recommend","planned_duration_minutes":60,
        "requested_total_duration_minutes":120,"expected_segment_count":2,
        "rank":1,"weekly_obligation":{"status":"available","delivery_debt_days":2,
                                        "remaining_weekly_obligation_days":4}}]}
    evidence={"weather":{"observed_at":NOW.isoformat(),"rain_rate_mm_h":0,"rain_today_mm":0},
              "tanks":{"observed_at":NOW.isoformat(),"reservoir_state":"FULL","reservoir_fraction":1.0}}
    controller={"device_id":"100204e9bc","online":True,"firmware":"3.8.2",
        "actuation_configuration_safe":True,"timers_enabled":False,"scenes_enabled":False,
        "interlock_enabled":False,"provider_control_calls":0,"trusted_receipt_at":NOW.isoformat(),
        "commissioned_baseline_id":"BASELINE-1","response_digest":"READ-ELIG",
        "channels":[{"channel":n,"output_state":"OFF","native_auto_off_enabled":True,
            "native_auto_off_seconds":3599,"power_restoration_state":"OFF"} for n in range(1,5)]}
    artifact=build_execution_eligibility(plan=plan,evidence=evidence,controller=controller,now=NOW)
    value={"decision_id":"DEC-1","decision":"Run now","standing_authority":True,"zone_id":"B12345",
           "runtime_minutes":59,"runtime_seconds":artifact["maximum_duration_seconds"],
           "execution_id":artifact["execution_id"],"eligibility_id":artifact["eligibility_id"],
           "evidence_generation":artifact["plan_generation"],"assessed_at":NOW.isoformat(),
           "commissioning_id":commissioned["commissioning_id"],
           "commissioning_generation":proof["configuration_generation"],
           "execution_eligibility":artifact}
    value.update(changes); value["decision_sha256"]=_digest(value); return value


def commissioning():
    raw=commissioning_evidence(); proof=validate_commissioning("B12345",raw,now=NOW)
    return {"commissioning_id":proof["commissioning_id"],"evidence":raw}


def valid_revalidation(value): return value["execution_eligibility"]


def run(store, transport, notices, value=None, now=NOW, outcome=None, revalidate=valid_revalidation):
    chosen=value or decision(); commissioned=commissioning()
    return advance_irrigation_execution(decision_id=chosen["decision_id"],
        commissioning_id=commissioned["commissioning_id"], decision_reader=lambda _:chosen,
        commissioning_reader=lambda _:commissioned, store=store, transport=transport,
        notify=lambda *x:(notices.append(x) or {"success":True,"provider_delivery_confirmed":True,
            "provider_message_id":f"MSG-{len(notices)}"}), outcome_reader=lambda _:outcome,
        eligibility_revalidator=revalidate, now=now, clock=lambda: now)


def test_missing_provider_safety_readback_disables_on():
    transport=Transport(safety=False); notices=[]
    result=run(Store(),transport,notices)
    assert result["status"]=="provider_safety_readback_unavailable"
    assert result["hardware_commands"]==0 and transport.calls==[] and notices==[]


def test_execution_store_timeout_is_degraded_hold_before_any_provider_authority():
    class UnavailableStore:
        def __call__(self, action, payload):
            raise RootlineExecutionStoreUnavailable(action)
    transport=Transport();notices=[]
    result=run(UnavailableStore(),transport,notices)
    assert result["status"]=="execution_store_degraded_hold"
    assert result["durable_execution_truth_loaded"] is False
    assert result["current_segment_consumed"] is False
    assert result["hardware_commands"]==0 and transport.calls==[] and notices==[]


def test_containment_read_timeout_is_not_interpreted_as_uncontained():
    class ContainmentUnavailable(Store):
        def __call__(self, action, payload):
            if action=="load_zone_containment":
                raise RootlineExecutionStoreUnavailable(action)
            return super().__call__(action,payload)
    transport=Transport();notices=[]
    result=run(ContainmentUnavailable(),transport,notices)
    assert result["status"]=="execution_store_degraded_hold"
    assert result["current_segment_consumed"] is False
    assert result["hardware_commands"]==0 and transport.calls==[] and notices==[]


def test_claim_database_timeout_never_reaches_on():
    class ClaimUnavailable(Store):
        def __call__(self, action, payload):
            if action=="claim_before_on":
                raise RootlineExecutionStoreUnavailable(action)
            return super().__call__(action,payload)
    transport=Transport();notices=[]
    result=run(ClaimUnavailable(),transport,notices)
    assert result["status"]=="execution_store_degraded_hold"
    assert result["current_segment_consumed"] is None
    assert result["segment_consumption_proven"] is False
    assert result["hardware_commands"]==0 and transport.calls==[] and notices==[]


def test_final_provider_readback_rejects_3600_second_fail_stop():
    class UnsafeDuration(Transport):
        def read_safety_configuration(self, **kwargs):
            return {**super().read_safety_configuration(**kwargs),
                    "native_inching_seconds":3600}
    transport=UnsafeDuration();result=run(Store(),transport,[])
    assert result["status"]=="provider_safety_readback_unavailable"
    assert result["hardware_commands"]==0 and transport.calls==[]


def test_forged_decision_or_commissioning_identity_never_reaches_on():
    transport=Transport(); notices=[]; chosen=decision(); chosen["standing_authority"]=False
    result=run(Store(),transport,notices,chosen)
    assert result["status"]=="not_eligible" and transport.calls==[]


def test_exactly_one_unambiguous_on_after_durable_claim():
    store=Store(); transport=Transport(); notices=[]
    result=run(store,transport,notices)
    assert result["status"]=="segment_started"
    assert [call["state"] for call in transport.calls]==["ON"]
    assert store.rows[0][0]=="claim_before_on" and notices[0][0]=="Started"
    active=next(value for name,value in store.rows if name=="mark_active")
    assert result["execution"]==active
    assert notices[0][1]=={**active,
        "notification_identity":f"{active['execution_id']}:Started"}
    assert active["state"]=="Active" and active["start_evidence"]["authoritative"] is True


def test_ambiguous_on_is_never_retried_and_uses_safe_off():
    store=Store(); transport=Transport(on="ambiguous"); notices=[]
    result=run(store,transport,notices)
    assert [call["state"] for call in transport.calls].count("ON")==1
    assert [call["state"] for call in transport.calls].count("OFF")==1
    assert result["status"]=="ambiguous_on_shutdown_unverified" and notices==[("Intervention",notices[0][1])]
    assert "B12345" in store.contained
    assert result["telegram_messages"]==1


def test_proven_missing_transport_containment_releases_without_on_then_reassesses():
    store=Store(); chosen=decision(); execution_id="EXEC-NONCONFIG"
    store.contained["B12345"]={"execution_id":execution_id,"zone_id":"B12345",
        "transport_status":"transport_not_configured","shutdown_verified":True}
    transport=Transport(); notices=[]
    first=run(store,transport,notices,chosen)
    assert first["status"]=="zone_containment_released_reassess"
    assert first["hardware_commands"]==0 and transport.calls==[] and notices==[]
    assert "B12345" not in store.contained
    assert any(name=="release_zone_containment" for name,_ in store.rows)
    second=run(store,transport,notices,chosen)
    assert second["status"]=="segment_started"
    assert [call["state"] for call in transport.calls]==["ON"]


def test_provider_ambiguity_containment_never_auto_releases():
    store=Store(); store.contained["B12345"]={"execution_id":"EXEC-AMB",
        "zone_id":"B12345","transport_status":"provider_outcome_ambiguous",
        "shutdown_verified":True}
    transport=Transport(); notices=[]
    result=run(store,transport,notices)
    assert result["status"]=="zone_contained"
    assert transport.calls==[] and notices==[]


def test_accepted_on_without_authoritative_on_state_never_becomes_active():
    for state in ("OFF",None):
        store=Store(); transport=Transport(readback=state); notices=[]
        result=run(store,transport,notices)
        assert result["status"]=="start_unverified_contained"
        assert not any(name=="mark_active" for name,_ in store.rows)
        assert notices[-1][0]=="Intervention"


def test_restart_before_deadline_preserves_shutdown_ownership_without_commands():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "eligibility_id":"ELIG-1","evidence_generation":"GEN-1",
            "primary_stop_deadline":(NOW+timedelta(minutes=30)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=60)).isoformat()}
    transport=Transport(); result=run(Store(active),transport,[])
    assert result["status"]=="active_segment_owned" and transport.calls==[]


def test_restart_after_claim_owns_immediate_off_recovery_and_never_reissues_on():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "state":"claimed_recovery_required",
            "primary_stop_deadline":(NOW+timedelta(minutes=30)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=60)).isoformat()}
    store=Store(active); transport=Transport(readback="OFF"); notices=[]
    result=run(store,transport,notices)
    assert result["status"]=="interrupted_start_contained"
    assert [call["state"] for call in transport.calls]==["OFF"]
    assert "B12345" in store.contained and notices[0][0]=="Intervention"


def test_expired_active_segment_repeats_safe_off_and_requires_readback():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "primary_stop_deadline":(NOW-timedelta(minutes=1)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=1)).isoformat()}
    transport=Transport(readback=None); notices=[]
    result=run(Store(active),transport,notices)
    assert all(call["state"]=="OFF" for call in transport.calls)
    assert result["status"]=="shutdown_unverified" and notices[-1][0]=="Intervention"


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
    assert notices[0][0]=="Completed"
    assert notices[0][1]["notification_identity"]=="EXEC-1:Completed"


def test_provider_confirmed_bounded_segment_builds_canonical_control_outcome():
    active={"execution_id":"EXEC-PROVIDER","zone_id":"B12345","channel":1,
        "eligibility_id":"ELIG-P","evidence_generation":"GEN-P","state":"Active",
        "on_attempts":1,"planned_runtime_minutes":60,"planned_runtime_seconds":3599,
        "claimed_at":(NOW-timedelta(seconds=3599)).isoformat(),
        "primary_stop_deadline":NOW.isoformat(),"native_fail_stop_deadline":NOW.isoformat(),
        "start_evidence":{"authoritative":True,"state":"ON","evidence_id":"START-P",
            "retrieved_at":(NOW-timedelta(seconds=3599)).isoformat()}}
    store=Store(active); notices=[]
    result=run(store,Transport(readback="OFF"),notices,now=NOW)
    assert result["status"]=="segment_completed"
    evidence=result["execution"]["objective_evidence"]
    assert evidence["objective_satisfied"] is True
    assert evidence["verified_runtime_minutes"]==3599/60
    assert evidence["physical_flow_confirmation"]=="Unavailable"
    assert evidence["delivered_volume"]=="Unavailable"
    assert notices[0][0]=="Completed"


def test_provider_off_before_deadline_never_satisfies_control_objective():
    active={"execution_id":"EXEC-EARLY","zone_id":"B12345","channel":1,
        "eligibility_id":"ELIG-E","evidence_generation":"GEN-E","state":"Active",
        "on_attempts":1,"planned_runtime_minutes":60,"planned_runtime_seconds":3599,
        "claimed_at":(NOW-timedelta(seconds=3600)).isoformat(),
        "primary_stop_deadline":NOW.isoformat(),"native_fail_stop_deadline":NOW.isoformat(),
        "start_evidence":{"authoritative":True,"state":"ON","evidence_id":"START-E",
            "retrieved_at":(NOW-timedelta(seconds=3599)).isoformat()}}
    transport=Transport(readback="OFF")
    def early_readback(**kwargs):
        return {"authoritative":True,"state":"OFF","evidence_id":"EARLY",
                "retrieved_at":(NOW-timedelta(seconds=1)).isoformat()}
    transport.read_output_state=early_readback
    notices=[]; result=run(Store(active),transport,notices,now=NOW)
    assert result["status"]=="segment_stopped_outcome_unconfirmed"
    assert notices[0][0]=="Intervention"


def test_equal_but_shifted_deadlines_never_satisfy_control_objective():
    shifted=NOW+timedelta(seconds=1)
    active={"execution_id":"EXEC-SHIFT","zone_id":"B12345","channel":1,
        "eligibility_id":"ELIG-S","evidence_generation":"GEN-S","state":"Active",
        "on_attempts":1,"planned_runtime_minutes":60,"planned_runtime_seconds":3599,
        "claimed_at":(NOW-timedelta(seconds=3600)).isoformat(),
        "primary_stop_deadline":shifted.isoformat(),
        "native_fail_stop_deadline":shifted.isoformat(),
        "start_evidence":{"authoritative":True,"state":"ON","evidence_id":"START-S",
            "retrieved_at":(NOW-timedelta(seconds=3599)).isoformat()}}
    transport=Transport(readback="OFF")
    def late_readback(**kwargs):
        return {"authoritative":True,"state":"OFF","evidence_id":"STOP-S",
                "retrieved_at":(shifted+timedelta(seconds=1)).isoformat()}
    transport.read_output_state=late_readback
    notices=[]
    result=run(Store(active),transport,notices,now=shifted+timedelta(seconds=1))
    assert result["status"]=="segment_stopped_outcome_unconfirmed"
    assert notices[0][0]=="Intervention"


def test_provider_receipt_after_fixed_scheduler_timestamp_is_not_future_evidence():
    fixed=NOW; receipt=NOW+timedelta(seconds=5)
    claimed=NOW-timedelta(seconds=3599)
    active={"execution_id":"EXEC-CLOCK","zone_id":"B12345","channel":1,
        "eligibility_id":"ELIG-C","evidence_generation":"GEN-C","state":"Active",
        "on_attempts":1,"planned_runtime_minutes":60,"planned_runtime_seconds":3599,
        "claimed_at":claimed.isoformat(),"primary_stop_deadline":NOW.isoformat(),
        "native_fail_stop_deadline":NOW.isoformat(),
        "start_evidence":{"authoritative":True,"state":"ON","evidence_id":"START-C",
            "retrieved_at":(claimed+timedelta(seconds=2)).isoformat()}}
    transport=Transport(readback="OFF")
    transport.read_output_state=lambda **kwargs:{"authoritative":True,"state":"OFF",
        "evidence_id":"STOP-C","retrieved_at":receipt.isoformat()}
    notices=[]; result=run(Store(active),transport,notices,now=fixed)
    assert result["status"]=="segment_completed"
    assert result["execution"]["completed_at"]==receipt.isoformat()
    assert notices[0][0]=="Completed"


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


def test_shutdown_without_objective_is_truthfully_intervention_not_completed():
    active={"execution_id":"EXEC-1","zone_id":"B12345","channel":1,
            "eligibility_id":"ELIG-1","evidence_generation":"GEN-1",
            "claimed_at":(NOW-timedelta(minutes=60)).isoformat(),
            "primary_stop_deadline":(NOW-timedelta(seconds=1)).isoformat(),
            "native_fail_stop_deadline":(NOW+timedelta(minutes=1)).isoformat()}
    notices=[]
    result=run(Store(active),Transport(readback="OFF"),notices)
    assert result["status"]=="segment_stopped_outcome_unconfirmed"
    assert notices[0][0]=="Intervention"
    assert notices[0][1]["notification_identity"]=="EXEC-1:Intervention"


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


def test_fresh_rain_or_generation_change_immediately_before_claim_prevents_on():
    store=Store(); transport=Transport(); notices=[]
    result=run(store,transport,notices,revalidate=lambda _decision:None)
    assert result["status"]=="execution_eligibility_changed"
    assert transport.calls==[] and store.active is None and notices==[]


def test_revalidation_must_bind_exact_decision_generation():
    result=run(Store(),Transport(),[],revalidate=lambda value:{
        **value["execution_eligibility"],"plan_generation":"OTHER"})
    assert result["status"]=="execution_eligibility_changed"


def test_ambiguous_on_persists_containment_even_when_readback_raises():
    class ThrowingReadback(Transport):
        def read_output_state(self, **kwargs): raise RuntimeError("provider unavailable")
    store=Store(); result=run(store,ThrowingReadback(on="ambiguous"),[])
    assert result["status"]=="ambiguous_on_shutdown_unverified"
    assert "B12345" in store.contained
