from datetime import datetime, timedelta, timezone
from unittest import mock
import pytest

from modules.telemetry.rootline_execution_runtime import (
    _bc_authority_policy_proven, _current, _persist_stale_parent_resolutions,
    _planning_observation,
    run_protected_rootline_segment, run_rootline_execution_cycle,
)
from modules.telemetry.rootline_irrigation_execution_store import RootlineExecutionStoreUnavailable

NOW=datetime(2026,8,8,18,0,tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def current_dry_active_weather(monkeypatch):
    # Ongoing-run regressions now explicitly provide canonical local weather.
    # Missing/unavailable active evidence has separate fail-closed coverage.
    from tests.test_rootline_active_weather_stop import dry_weather_reader
    monkeypatch.setattr("modules.telemetry.rootline_execution_runtime.read_active_irrigation_weather",
        dry_weather_reader)


def test_stale_parent_resolution_is_digest_bound_and_zero_control():
    calls=[]
    parent={"job":{"job_id":"JOB-OLD","job_sha256":"a"*64,"zone_id":"C12345",
        "operating_date":"2026-08-07","expected_segment_count":2},
        "projection":{"current_segment":2,"cumulative_verified_runtime_seconds":3599},
        "remaining_seconds":3599}
    current={"evidence_generation":"PLAN-CURRENT","candidate_tasks":[{
        "task_id":"irrigation_C12345","stale_incomplete_parent_jobs":[parent]}]}
    def store(action,payload):
        calls.append((action,payload)); return {"success":True,"created":len(calls)==1}
    _persist_stale_parent_resolutions(current,store)
    _persist_stale_parent_resolutions(current,store)
    assert [action for action,_ in calls]==["record_job_resolution","record_job_resolution"]
    assert calls[0][1]==calls[1][1]
    assert calls[0][1]["resolution"]=="Deferred"
    assert calls[0][1]["terminal"] is True
    assert "source_plan_generation" not in calls[0][1]
    assert calls[0][1]["remaining_seconds"]==3599

    contained={**parent,
        "resolution_reason":"segment_contained_without_verified_shutdown_or_runtime"}
    _persist_stale_parent_resolutions({"evidence_generation":"PLAN-CURRENT",
        "candidate_tasks":[{"contained_parent_jobs":[contained]}]},store)
    assert calls[-1][1]["reason"]=="segment_contained_without_verified_shutdown_or_runtime"


def plan():
    return {"evidence_generation":"PLAN-GEN-1","operating_date":"2026-08-08",
            "candidate_tasks":[{
        "task_id":"irrigation_B12345","zone_decision":"Run now","recommendation":"Recommend",
        "planned_duration_minutes":60,"requested_total_duration_minutes":120,
        "expected_segment_count":2,"rank":1,"weekly_obligation":{"status":"available",
            "delivery_debt_days":2,"remaining_weekly_obligation_days":4}}]}


def evidence(rain=0):
    return {"weather":{"observed_at":NOW.isoformat(),"rain_rate_mm_h":rain,"rain_today_mm":rain},
            "irrigation":{"source":"rootline_daily_advisor",
                "advisor_generated_at":NOW.isoformat(),
                "advisor_operating_date":"2026-08-08",
                "zones":[{"zone_id":"B12345","live_rain_release_proven":True}]},
            "tanks":{"observed_at":NOW.isoformat(),"reservoir_state":"FULL","reservoir_fraction":1.0}}


def controller(response_digest="READ-1"):
    return {"device_id":"100204e9bc","online":True,"firmware":"3.8.2",
        "actuation_configuration_safe":True,"timers_enabled":False,"scenes_enabled":False,
        "interlock_enabled":False,"provider_control_calls":0,"trusted_receipt_at":NOW.isoformat(),
        "commissioned_baseline_id":"ROOTLINE-EWELINK-BASELINE-1AB8753412B8851C4513D6CC",
        "response_digest":response_digest,"channels":[{"channel":n,"output_state":"OFF",
            "native_auto_off_enabled":True,"native_auto_off_seconds":3599,
            "power_restoration_state":"OFF"} for n in range(1,5)]}


class Store:
    def __init__(self): self.active=None; self.rows=[]; self.contained=set()
    def __call__(self,action,payload):
        if action=="load_active": return self.active
        if action=="load_job_events":
            return [row for name,row in self.rows if name in {
                "claim_before_on","mark_active","record_completed"}
                and row.get("job_id")==payload]
        if action=="load_zone_containment": return {"contained":payload in self.contained}
        if action=="load_off_attempts": return []
        if action=="claim_before_on":
            if any(name==action and row["execution_id"]==payload["execution_id"] for name,row in self.rows):
                return {"created":False,"success":True}
            self.active=payload; self.rows.append((action,payload)); return {"created":True,"success":True}
        if action=="claim_notification":
            if any(name==action and row["execution_id"]==payload["execution_id"] for name,row in self.rows):
                return {"created":False,"success":True}
            self.rows.append((action,payload)); return {"created":True,"success":True}
        self.rows.append((action,payload))
        if action=="mark_active": self.active=payload
        if action=="contain_zone": self.contained.add(payload["zone_id"])
        if action=="record_completed": self.active=None
        return {"created":True,"success":True}


class Transport:
    def __init__(self): self.calls=[]
    def read_safety_configuration(self,**kwargs):
        return {"authoritative":True,"zone_id":"B12345","channel":1,
            "native_inching_enabled":True,"native_inching_seconds":3599,
            "power_restoration_state":"OFF","schedules_enabled":False,
            "interlock_enabled":False,"scenes_enabled":False}
    def set_state(self,**kwargs): self.calls.append(kwargs); return {"accepted_unambiguous":True}
    def read_output_state(self,**kwargs): return {"authoritative":True,"state":"ON","evidence_id":"OUT-1"}


def run(store,transport,rain=0,notify=None,clock=lambda:NOW):
    loader=lambda **_kwargs:(evidence(rain),"2026-08-08",NOW)
    observations={}
    def observation_store(action,identity,payload):
        created=identity not in observations; observations.setdefault(identity,payload)
        return {"success":True,"created":created}
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",
                    return_value=plan()):
        return run_rootline_execution_cycle(notify=notify or (lambda *_:{"success":True,
            "provider_delivery_confirmed":True,"provider_message_id":"MSG-1"}),
            environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,store=store,
            token_store=object(),transport=transport,evidence_loader=loader,
            readback=lambda **_kwargs:controller(),clock=clock,
            owner_user_id="42",chat_id="42",observation_store=observation_store,
            authority_checker=lambda _database_url, _artifact: True)


def test_scheduler_owner_binding_persists_hold_observation_without_notification_or_command():
    execution_store=Store(); transport=Transport(); observations={}; notices=[]
    def observation_store(action,identity,payload):
        created=identity not in observations; observations.setdefault(identity,payload)
        return {"success":True,"created":created}
    loader=lambda **_kwargs:(evidence(.25),"2026-08-08",NOW)
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",
                    return_value=plan()):
        value=run_rootline_execution_cycle(notify=lambda *args:notices.append(args),
            environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,store=execution_store,
            token_store=object(),transport=transport,evidence_loader=loader,
            readback=lambda **_kwargs:controller(),owner_user_id="42",chat_id="42",
            next_reassessment_at="2026-08-08T20:15:00+02:00",
            observation_store=observation_store)
    assert value["status"]=="observed_weather_not_fresh_and_dry"
    assert len(observations)==1 and next(iter(observations.values()))["delivery_state"]=="observation_only"
    assert notices==[] and transport.calls==[]


def test_run_projection_never_inherits_opaque_global_parent_deferment():
    initial={"plan":plan(),"evidence":evidence(),"operating_date":"2026-08-08",
        "artifact":{"eligible":False,"status":"durable_parent_job_deferred",
            "zone_eligibility_reasons":{
                "B12345":"parent_operating_date_mismatch",
                "C12345":"zone_decision_not_run_now"}}}
    observation=_planning_observation(initial,"42","42","2026-08-08T18:15:00+00:00")
    zones={row["zone_id"]:row for row in observation["zones"]}
    assert zones["B12345"]["decision"]=="Run"
    assert zones["B12345"]["eligibility_blocker"]=="parent_operating_date_mismatch"
    assert zones["C12345"]["eligibility_blocker"]=="zone_decision_not_run_now"


def test_run_projection_without_exact_defer_predicate_fails_closed():
    initial={"plan":plan(),"evidence":evidence(),"operating_date":"2026-08-08",
        "artifact":{"eligible":False,"status":"durable_parent_job_deferred"}}
    observation=_planning_observation(initial,"42","42","")
    b=next(row for row in observation["zones"] if row["zone_id"]=="B12345")
    assert b["decision"]=="Run"
    assert b["eligibility_blocker"]=="run_projection_eligibility_invariant_failed"


def test_rain_hold_creates_no_artifact_command_or_notification():
    store=Store(); transport=Transport(); notices=[]
    value=run(store,transport,rain=.25,notify=lambda *args:notices.append(args))
    assert value["status"]=="observed_weather_not_fresh_and_dry"
    assert transport.calls==[] and notices==[]
    assert not any(name=="record_eligibility" for name,_ in store.rows)


def test_dry_b_creates_artifact_and_exactly_one_coordinator_execution():
    store=Store(); transport=Transport()
    first=run(store,transport); replay=run(store,transport)
    assert first["status"]=="segment_started" and first["telegram_messages"]==1
    assert replay["status"]=="active_segment_owned"
    assert [call["state"] for call in transport.calls]==["ON"]
    artifacts=[row for name,row in store.rows if name=="record_eligibility"]
    assert len(artifacts)==1 and artifacts[0]["zone_id"]=="B12345"


def test_bc_authority_policy_requires_explicit_standing_water_evidence_semantics():
    keys=("ifttt_ewelink:ewelink_owner_account:100204e9bc:1",
          "ifttt_ewelink:ewelink_owner_account:100204e9bc:2")
    policy={"contract_version":"rootline_bc_standing_authority.v2",
      "device_keys":list(keys),"zone_ids":["B12345","C12345"],"allowed_channels":[1,2],
      "provider":"ifttt_ewelink","provider_account_binding":"ewelink_owner_account",
      "device_id":"100204e9bc","maximum_runtime_seconds":3599,
      "simultaneous_outputs_allowed":False,"mutual_exclusion_required":True,
      "missing_or_stale_reservoir_observation_is_hold":False,
      "fresh_adverse_reservoir_evidence_is_hold":True,
      "unproven_reservoir_water_credit_litres":0,
      "fresh_weather_and_rain_hold_required":True,"current_plan_identity_required":True,
      "application_timeout_required":True,"provider_on_off_readback_required":True,
      "explicit_exclusions":["fertilizer_injection","fertilizer_mixing","borehole_pump"],
      "emergency_off_owner":"deployed ROOTLINE irrigation coordinator",
      "emergency_off_procedure":"exact provider OFF and readback",
      "provider_fail_stop_proven":True,"physical_fail_safe_proven":True,
      "power_restoration_off_proven":True,"automatic_on_retry":False}
    artifact={"maximum_duration_seconds":3599}
    assert _bc_authority_policy_proven(policy,artifact,keys) is True
    assert _bc_authority_policy_proven({**policy,
      "contract_version":"rootline_bc_standing_authority.v1"},artifact,keys) is False
    assert _bc_authority_policy_proven({**policy,
      "fresh_adverse_reservoir_evidence_is_hold":False},artifact,keys) is False
    assert _bc_authority_policy_proven({**policy,
      "unproven_reservoir_water_credit_litres":1},artifact,keys) is False


def test_eligible_artifact_without_canonical_database_fails_closed_before_on():
    store=Store(); transport=Transport(); loader=lambda **_kwargs:(evidence(),"2026-08-08",NOW)
    observations={}
    def observation_store(action,identity,payload):
        observations.setdefault(identity,payload); return {"success":True,"created":True}
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",
                    return_value=plan()):
        result=run_rootline_execution_cycle(notify=lambda *_:None,
            environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,store=store,
            clock=lambda:NOW,
            token_store=object(),transport=transport,evidence_loader=loader,
            readback=lambda **_kwargs:controller(),owner_user_id="42",chat_id="42",
            observation_store=observation_store)
    assert result["status"]=="canonical_standing_authority_unproven"
    assert result["hardware_commands"]==0 and transport.calls==[]
    assert not any(action=="record_eligibility" for action,_ in store.rows)


def test_notification_ambiguity_is_quarantined_without_retry_or_false_count():
    store=Store(); transport=Transport(); attempts=[]
    first=run(store,transport,notify=lambda *args:(attempts.append(args) or {
        "success":False,"status":"family_message_delivery_ambiguous",
        "provider_delivery_ambiguous":True}))
    replay=run(store,transport,notify=lambda *args:attempts.append(args))
    assert first["notification"]["ambiguous"] is True and first["telegram_messages"]==0
    assert replay["status"]=="active_segment_owned" and len(attempts)==1


def test_disabled_flag_is_zero_effect():
    store=Store(); transport=Transport()
    value=run_rootline_execution_cycle(notify=lambda *_:None,
        environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"false"},now=NOW,
        store=store,token_store=object(),transport=transport)
    assert value["status"]=="autonomous_bc_disabled" and store.rows==[] and transport.calls==[]


def test_new_execution_requires_exact_owner_chat_binding_before_claim_or_on():
    for owner,chat in (("",""),("42","99")):
        store=Store(); transport=Transport(); notices=[]
        value=run_rootline_execution_cycle(notify=lambda *args:notices.append(args),
            environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,store=store,
            token_store=object(),transport=transport,owner_user_id=owner,chat_id=chat)
        assert value["status"]=="canonical_observation_binding_invalid"
        assert store.rows==[] and transport.calls==[] and notices==[]


def test_run_to_technical_block_notifies_once_and_replay_is_silent():
    store=Store(); transport=Transport(); notices=[]
    unsafe={**controller(),"actuation_configuration_safe":False}
    loader=lambda **_kwargs:(evidence(),"2026-08-08",NOW)
    observations={}
    def observation_store(action,identity,payload):
        created=identity not in observations; observations.setdefault(identity,payload)
        return {"success":True,"created":created}
    def notify(state,payload):
        notices.append((state,payload)); return {"provider_delivery_confirmed":True,
            "provider_message_id":"BLOCK-1"}
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=plan()):
        args=dict(notify=notify,environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,clock=lambda:NOW,
            store=store,token_store=object(),transport=transport,evidence_loader=loader,
            readback=lambda **_kwargs:unsafe,owner_user_id="42",chat_id="42",
            next_reassessment_at="2026-08-08T20:15:00+02:00",observation_store=observation_store)
        first=run_rootline_execution_cycle(**args); replay=run_rootline_execution_cycle(**args)
    assert first["status"]==replay["status"]=="controller_safety_not_dispatchable"
    assert len(notices)==1 and notices[0][0]=="Blocked"
    assert transport.calls==[] and first["telegram_messages"]==1 and replay["telegram_messages"]==0


def test_blocked_notification_failure_is_durable_and_never_retried():
    for response in (RuntimeError("delivery failed"), None,
                     {"provider_delivery_ambiguous":True}, {"success":False}):
        store=Store(); transport=Transport(); calls=[]; observations={}
        unsafe={**controller(),"actuation_configuration_safe":False}
        def obs(action,identity,payload):
            created=identity not in observations; observations.setdefault(identity,payload)
            return {"success":True,"created":created}
        def notify(*args):
            calls.append(1)
            if isinstance(response,Exception): raise response
            return response
        loader=lambda **_kwargs:(evidence(),"2026-08-08",NOW)
        with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=plan()):
            args=dict(notify=notify,environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,clock=lambda:NOW,
                store=store,token_store=object(),transport=transport,evidence_loader=loader,
                readback=lambda **_kwargs:unsafe,owner_user_id="42",chat_id="42",observation_store=obs)
            first=run_rootline_execution_cycle(**args); replay=run_rootline_execution_cycle(**args)
        assert len(calls)==1 and first["telegram_messages"]==replay["telegram_messages"]==0
        outcomes=[row for name,row in store.rows if name=="record_notification_delivery"]
        assert len(outcomes)==1 and outcomes[0]["delivery_outcome"] in {"failed","ambiguous"}


def test_blocked_notification_outcome_store_failure_is_unproven_and_not_retried():
    backing=Store(); transport=Transport(); calls=[]; observations={}
    unsafe={**controller(),"actuation_configuration_safe":False}
    def store(action,payload):
        if action=="record_notification_delivery": return {"success":False}
        return backing(action,payload)
    def obs(action,identity,payload):
        created=identity not in observations; observations.setdefault(identity,payload)
        return {"success":True,"created":created}
    def notify(*_args):
        calls.append(1); return {"provider_delivery_confirmed":True,"provider_message_id":"BLOCK-1"}
    loader=lambda **_kwargs:(evidence(),"2026-08-08",NOW)
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=plan()):
        args=dict(notify=notify,environ={"ROOTLINE_AUTONOMOUS_BC_ENABLED":"true"},now=NOW,clock=lambda:NOW,
            store=store,token_store=object(),transport=transport,evidence_loader=loader,
            readback=lambda **_kwargs:unsafe,owner_user_id="42",chat_id="42",observation_store=obs)
        first=run_rootline_execution_cycle(**args); replay=run_rootline_execution_cycle(**args)
    assert first["status"]=="blocked_notification_persistence_unproven" and first["success"] is False
    assert replay["telegram_messages"]==0 and len(calls)==1 and transport.calls==[]


def test_expired_artifact_at_real_preclaim_time_creates_no_on():
    store=Store(); transport=Transport()
    later=NOW+timedelta(minutes=16)
    value=run(store,transport,clock=lambda:later)
    assert value["status"]=="controller_safety_not_dispatchable"
    assert transport.calls==[]


def test_real_advancing_clock_accepts_fresh_revalidation_before_claim():
    store=Store(); transport=Transport()
    instants=iter(NOW+timedelta(seconds=second) for second in range(1,20))
    value=run(store,transport,clock=lambda:next(instants))
    assert value["status"]=="segment_started"
    assert [call["state"] for call in transport.calls]==["ON"]


def test_protected_segment_accepts_fresh_provider_receipt_digest_for_same_governed_identity():
    store=Store();transport=Transport();loader=lambda **_kwargs:(evidence(),"2026-08-08",NOW)
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=plan()):
        expected=_current(loader,lambda **_kwargs:controller("PREVIEW-RECEIPT"),object(),{},"db",NOW,store,clock=lambda:NOW)["artifact"]
        result=run_protected_rootline_segment(expected_artifact=expected,notify=lambda *_:None,
          environ={},now=NOW,database_url="db",store=store,token_store=object(),transport=transport,
          evidence_loader=loader,readback=lambda **_kwargs:controller("CURRENT-RECEIPT"),clock=lambda:NOW,
          owner_user_id="42",chat_id="42")
    assert result["status"]=="segment_started"
    assert [call["state"] for call in transport.calls]==["ON"]
    fresh=next(row for action,row in store.rows if action=="record_eligibility")
    claimed=next(row for action,row in store.rows if action=="claim_before_on")
    assert fresh["eligibility_sha256"]!=expected["eligibility_sha256"]
    assert claimed["eligibility_sha256"]==fresh["eligibility_sha256"]
    assert claimed["eligibility_id"]==fresh["eligibility_id"]
    assert claimed["execution_id"]==fresh["execution_id"]
    assert store.active["eligibility_sha256"]==fresh["eligibility_sha256"]


def test_protected_segment_rejects_changed_stable_job_identity_with_zero_control():
    store=Store();transport=Transport();loader=lambda **_kwargs:(evidence(),"2026-08-08",NOW)
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=plan()):
        expected=_current(loader,lambda **_kwargs:controller(),object(),{},"db",NOW,store,clock=lambda:NOW)["artifact"]
        expected={**expected,"job_sha256":"wrong"}
        result=run_protected_rootline_segment(expected_artifact=expected,notify=lambda *_:None,
          environ={},now=NOW,database_url="db",store=store,token_store=object(),transport=transport,
          evidence_loader=loader,readback=lambda **_kwargs:controller(),owner_user_id="42",chat_id="42")
    assert result["status"]=="protected_irrigation_eligibility_changed"
    assert result["hardware_commands"]==0 and transport.calls==[]


def test_protected_runner_rejects_registry_channel_mismatch_before_provider_access():
    store=Store();transport=Transport()
    expected={"zone_id":"C12345","channel":4,"current_segment":1,
      "segment_requested_seconds":3599,"requested_total_duration_seconds":7200,
      "governed_executable_duration_seconds":7198,"expected_segment_count":2}
    result=run_protected_rootline_segment(expected_artifact=expected,notify=lambda *_:None,
      environ={},now=NOW,database_url="db",store=store,token_store=object(),transport=transport,
      evidence_loader=lambda **_kwargs:(_ for _ in ()).throw(AssertionError("evidence accessed")),
      readback=lambda **_kwargs:(_ for _ in ()).throw(AssertionError("provider accessed")),
      owner_user_id="42",chat_id="42")
    assert result["status"]=="protected_irrigation_boundary_invalid"
    assert result["hardware_commands"]==0 and transport.calls==[]


def test_protected_runner_contains_actual_pre_coordinator_database_timeout():
    class UnavailableStore:
        def __call__(self, action, payload):
            raise RootlineExecutionStoreUnavailable(action)
    transport=Transport()
    expected={"zone_id":"B12345","channel":1,"current_segment":1,
      "segment_requested_seconds":3599,"requested_total_duration_seconds":7200,
      "governed_executable_duration_seconds":7198,"expected_segment_count":2}
    result=run_protected_rootline_segment(expected_artifact=expected,notify=lambda *_:None,
      environ={},now=NOW,database_url="db",store=UnavailableStore(),token_store=object(),
      transport=transport,
      evidence_loader=lambda **_kwargs:(_ for _ in ()).throw(AssertionError("evidence accessed")),
      readback=lambda **_kwargs:(_ for _ in ()).throw(AssertionError("provider accessed")),
      owner_user_id="42",chat_id="42")
    assert result["status"]=="execution_store_degraded_hold"
    assert result["durable_execution_truth_loaded"] is False
    assert result["current_segment_consumed"] is False
    assert result["hardware_commands"]==0 and transport.calls==[]


def test_protected_runner_contains_unavailable_canonical_history_before_provider():
    store=Store();transport=Transport()
    expected={"zone_id":"B12345","channel":1,"current_segment":1,
      "segment_requested_seconds":3599,"requested_total_duration_seconds":7200,
      "governed_executable_duration_seconds":7198,"expected_segment_count":2}
    unavailable={**evidence(),"irrigation_history":{"status":"Unavailable"}}
    result=run_protected_rootline_segment(expected_artifact=expected,notify=lambda *_:None,
      environ={},now=NOW,database_url="db",store=store,token_store=object(),transport=transport,
      evidence_loader=lambda **_kwargs:(unavailable,"2026-08-08",NOW),
      readback=lambda **_kwargs:(_ for _ in ()).throw(AssertionError("provider accessed")),
      owner_user_id="42",chat_id="42")
    assert result["status"]=="execution_store_degraded_hold"
    assert result["hardware_commands"]==0 and transport.calls==[]


def test_protected_segment_delegates_exactly_one_bounded_on_after_confirmation():
    store=Store();transport=Transport();loader=lambda **_kwargs:(evidence(),"2026-08-08",NOW)
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=plan()):
        expected=_current(loader,lambda **_kwargs:controller(),object(),{},"db",NOW,store,clock=lambda:NOW)["artifact"]
        result=run_protected_rootline_segment(expected_artifact=expected,notify=lambda *_:{"success":True},
          environ={},now=NOW,database_url="db",store=store,token_store=object(),transport=transport,
          evidence_loader=loader,readback=lambda **_kwargs:controller(),clock=lambda:NOW,
          owner_user_id="42",chat_id="42")
    assert result["status"]=="segment_started"
    assert [call["state"] for call in transport.calls]==["ON"]
    assert store.active["planned_runtime_seconds"]==3599


def test_protected_restart_requires_full_claim_binding_and_never_reissues_on():
    store=Store();transport=Transport();loader=lambda **_kwargs:(evidence(),"2026-08-08",NOW)
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=plan()):
        expected=_current(loader,lambda **_kwargs:controller(),object(),{},"db",NOW,store,clock=lambda:NOW)["artifact"]
        first=run_protected_rootline_segment(expected_artifact=expected,notify=lambda *_:{"success":True},
          environ={},now=NOW,database_url="db",store=store,token_store=object(),transport=transport,
          evidence_loader=loader,readback=lambda **_kwargs:controller(),clock=lambda:NOW,
          owner_user_id="42",chat_id="42")
        replay=run_protected_rootline_segment(expected_artifact={**expected,"eligibility_sha256":"preview-receipt-digest"},notify=lambda *_:{"success":True},
          environ={},now=NOW,database_url="db",store=store,token_store=object(),transport=transport,
          evidence_loader=loader,readback=lambda **_kwargs:controller(),clock=lambda:NOW,
          owner_user_id="42",chat_id="42")
        mismatch=run_protected_rootline_segment(expected_artifact={**expected,"controller_safety_generation":"OTHER"},notify=lambda *_:None,
          environ={},now=NOW,database_url="db",store=store,token_store=object(),transport=transport,
          evidence_loader=loader,readback=lambda **_kwargs:controller(),clock=lambda:NOW,
          owner_user_id="42",chat_id="42")
    assert first["status"]=="segment_started" and replay["status"]=="active_segment_owned"
    assert mismatch["status"]=="active_execution_conflicts_with_protected_claim"
    assert [call["state"] for call in transport.calls]==["ON"]


def test_weather_ages_past_thirty_minutes_during_provider_read():
    sampled = evidence()
    sampled["weather"]["observed_at"] = (NOW-timedelta(minutes=29, seconds=59)).isoformat()
    current = [NOW]
    def read(**kwargs):
        current[0] += timedelta(seconds=2)
        return {**controller(), "trusted_receipt_at": current[0].isoformat()}
    with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=plan()):
        result = _current(lambda **_: (sampled,"2026-08-08",NOW), read, object(), {}, "db", NOW,
            Store(), clock=lambda:current[0])
    assert result["artifact"]["eligible"] is False
    assert result["artifact"]["status"] == "observed_weather_not_fresh_and_dry"
    assert sampled["weather"]["observed_at"] == (NOW-timedelta(minutes=29, seconds=59)).isoformat()


def test_no_dispatchable_work_never_requests_optional_controller_evidence():
    for task in ({}, {"zone_decision":"Hold"}, {"weekly_obligation":{"status":"available","delivery_debt_days":0}}):
        planned = plan()
        if not task:
            planned["candidate_tasks"] = []
        else:
            planned["candidate_tasks"][0].update(task)
        with mock.patch("modules.telemetry.rootline_execution_runtime.project_saved_program_for_execution",return_value=planned):
            result = _current(lambda **_: (evidence(),"2026-08-08",NOW),
                lambda **_: (_ for _ in ()).throw(AssertionError("unnecessary provider read")),
                object(), {}, "db", NOW, Store(), clock=lambda:NOW)
        assert result["artifact"]["eligible"] is False


# Initial pulse-parent readback: real transport and request-budget regressions.
from copy import deepcopy as _pulse_parent_deepcopy
from datetime import datetime as _pulse_parent_datetime, timedelta as _pulse_parent_timedelta
from pathlib import Path as _pulse_parent_Path
from urllib.parse import urlparse as _pulse_parent_urlparse
import importlib.util as _pulse_parent_importlib, json as _pulse_parent_json, sys as _pulse_parent_sys
import pytest as _pulse_parent_pytest
from modules.telemetry import rootline_execution_runtime as _pulse_parent_runtime
from modules.telemetry import rootline_ewelink_request_budget as _pulse_parent_budget
from modules.telemetry.rootline_ewelink_readback import read_registered_device as _pulse_parent_read_registered_device
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport as _pulse_parent_RootlineIFTTTTransport
from modules.telemetry.rootline_ewelink_oauth import OAuthFailure as _pulse_parent_OAuthFailure
from tests.test_rootline_routine_efficiency import fixture as _pulse_parent_fixture
from tests.test_rootline_ewelink_readback import NOW as _pulse_parent_NOW
from tests.test_rootline_ewelink_request_budget import MemoryBudget as _pulse_parent_MemoryBudget, fail as _pulse_parent_fail, snapshot as _pulse_parent_snapshot
from tests.test_rootline_fertilizer_auxiliary import injection_context as _pulse_parent_injection_context

def _pulse_parent_harness(monkeypatch,fault=None,hold=False,due=False,expired=False):
 source,tokens,raw,rawcalls=_pulse_parent_fixture();client=_pulse_parent_MemoryBudget(environ=source);client.backend.now=_pulse_parent_NOW
 monkeypatch.setattr(_pulse_parent_budget,'RequestBudget',lambda *_a,**_k:client)
 class FixtureClock(_pulse_parent_datetime):
  @classmethod
  def now(cls,tz=None):return client.backend.now if tz else client.backend.now.replace(tzinfo=None)
 monkeypatch.setattr(_pulse_parent_budget,'datetime',FixtureClock)
 if hold:
  with _pulse_parent_pytest.raises(_pulse_parent_OAuthFailure):_pulse_parent_snapshot(client,send=_pulse_parent_fail())
  if due:client.backend.advance(3601)
 tokens.record['access_expires_at']=client.backend.now+_pulse_parent_timedelta(days=1)
 if expired:tokens.record['access_expires_at']=client.backend.now-_pulse_parent_timedelta(seconds=1)
 endpoints=[];state=['on'];read_flags=[]
 def request(method,url,**kwargs):
  endpoint=_pulse_parent_urlparse(url).path
  def send(_):
   endpoints.append(endpoint);value=_pulse_parent_deepcopy(raw(method,url,**kwargs))
   if endpoint=='/v2/device/thing':
    item=value['thingList'][0]['itemData'];item['updatedAt']=client.backend.now.isoformat()
    if fault in ('stale','future'):item['updatedAt']=(client.backend.now+_pulse_parent_timedelta(seconds=-301 if fault=='stale' else 60)).isoformat()
    item['params']['switches']=[{'outlet':i,'switch':state[0] if i==0 else 'off'} for i in range(4)]
    if fault=='account':item['apikey']='changed'
    if fault=='missing_account':item.pop('apikey')
    if fault=='wrong_device':item['deviceid']='other'
    if fault=='uiid':item['extra']['uiid']=138
    if fault=='duplicate':value['thingList'].append(_pulse_parent_deepcopy(value['thingList'][0]))
    if fault=='offline':item['online']=False
    if fault=='other_on':item['params']['switches'][1]['switch']='on'
    if fault=='off':item['params']['switches'][0]['switch']='off'
    if fault=='timeout':raise TimeoutError('synthetic read failed')
   if endpoint=='/v2/device/thing/status':
    value['params']={'switches':[{'outlet':i,'switch':state[0] if i==0 else 'off'} for i in range(4)]}
    if fault=='other_on':value['params']['switches'][1]['switch']='on'
    if fault=='off':value['params']['switches'][0]['switch']='off'
    if fault=='timeout':raise TimeoutError('synthetic read failed')
   return value
  return client.dispatch(region='eu',endpoint=endpoint,send=send)
 class NativeSnapshot(_pulse_parent_RootlineIFTTTTransport):
  def _snapshot(self,device_id,channel,*,routine_read=False):
   read_flags.append(routine_read)
   return self._validated_snapshot(_pulse_parent_read_registered_device(device_id,token_store=tokens,
    environ=source,http_request=request,now=client.backend.now+(_pulse_parent_timedelta(seconds=-301) if fault=='stale' else _pulse_parent_timedelta(seconds=60) if fault=='future' else _pulse_parent_timedelta()),routine_read=routine_read),device_id,channel)
 transport=NativeSnapshot(token_store=tokens,environ=source,http_open=lambda *_a,**_k:_pulse_parent_pytest.fail('no hardware'))
 now=client.backend.now
 context=_pulse_parent_injection_context(zone_start_evidence={'evidence_id':'START','zone_execution_id':'ZONE-EXEC-1','observed_at':(now-_pulse_parent_timedelta(seconds=600)).isoformat()},
  fertilizer_history_complete_through=now.isoformat(),irrigation_stop_deadline=(now+_pulse_parent_timedelta(seconds=1800)).isoformat())
 return transport,endpoints,read_flags,client,context,state


def _pulse_parent_refresh(module,transport,client,context,**kwargs):
 return module._refresh_active_irrigation_readback({'active_irrigation_context':_pulse_parent_deepcopy(context)},transport,
  client.backend.now,clock=lambda:client.backend.now,only_when_due=True,preparation_token='one-invocation',**kwargs)['active_irrigation_context']['zone_output_evidence']


def test_pulse_parent_initial_parent_single_http_fresh_authoritative_proof(monkeypatch):
 transport,calls,flags,client,context,_=_pulse_parent_harness(monkeypatch)
 output=_pulse_parent_refresh(_pulse_parent_runtime,transport,client,context)
 assert output['state']=='ON' and output['authoritative']
 assert calls==['/v2/device/thing']
 assert flags==[True]
 assert len(output['evidence_id'])==64
 assert output['evidence_id']==output['irrigation_output_evidence']['response_digest']


def test_pulse_parent_final_flush_retains_fresh_snapshot_even_new_injection_disabled(monkeypatch):
 for module in (_pulse_parent_runtime,):
  with monkeypatch.context() as mp:
   transport,calls,flags,client,context,_=_pulse_parent_harness(mp)
   context.update(completed_pulses=2,prior_pulse_shutdown_evidence={'zone_execution_id':'ZONE-EXEC-1','shutdown_verified':True,'observed_at':(client.backend.now-_pulse_parent_timedelta(seconds=600)).isoformat()})
   assert _pulse_parent_refresh(module,transport,client,context,injection_enabled=False)['state']=='ON'
   assert calls==['/v2/device/thing'] and flags==[False]


@_pulse_parent_pytest.mark.parametrize('fault',['account','missing_account','wrong_device','uiid','duplicate','offline','stale','future','other_on','off','timeout'])
def test_pulse_parent_changed_identity_or_unfresh_parent_never_retains_historical_on(monkeypatch,fault):
 transport,calls,flags,client,context,_=_pulse_parent_harness(monkeypatch,fault=fault)
 assert _pulse_parent_refresh(_pulse_parent_runtime,transport,client,context)=={}
 assert '/v2/family' not in calls


@_pulse_parent_pytest.mark.parametrize('expired',[False,True])
def test_pulse_parent_due412_restores_full_discovery_same_charge(monkeypatch,expired):
 transport,calls,flags,client,context,_=_pulse_parent_harness(monkeypatch,hold=True,due=True,expired=expired)
 units=sum(row['units'] for row in client.backend.events)
 output=_pulse_parent_refresh(_pulse_parent_runtime,transport,client,context)
 assert output['state']=='ON'
 assert calls==(['/v2/user/refresh'] if expired else [])+['/v2/family','/v2/device/thing','/v2/device/thing/status']
 assert sum(row['units'] for row in client.backend.events)-units==3+int(expired)
 assert not client.backend.state['scopes'][_pulse_parent_budget.scope_digest(transport.environ,'eu')]['category']


def test_pulse_parent_not_due412_no_provider_attempt(monkeypatch):
 transport,calls,flags,client,context,_=_pulse_parent_harness(monkeypatch,hold=True)
 assert _pulse_parent_refresh(_pulse_parent_runtime,transport,client,context)=={} and calls==[]


def test_pulse_parent_optional_slot_still_suppresses_new_worker_invocation(monkeypatch):
 transport,calls,flags,client,context,_=_pulse_parent_harness(monkeypatch)
 assert _pulse_parent_refresh(_pulse_parent_runtime,transport,client,context)['state']=='ON';assert len(calls)==1
 output=_pulse_parent_runtime._refresh_active_irrigation_readback({'active_irrigation_context':context},transport,client.backend.now,
  clock=lambda:client.backend.now,only_when_due=True,preparation_token='another-invocation')
 assert output['active_irrigation_context']['zone_output_evidence']=={} and len(calls)==1


def test_pulse_parent_default_nonpreparation_and_changed_output_stay_fresh(monkeypatch):
 transport,calls,flags,client,context,state=_pulse_parent_harness(monkeypatch)
 assert _pulse_parent_refresh(_pulse_parent_runtime,transport,client,context)['state']=='ON';calls.clear();state[0]='off'
 output=_pulse_parent_runtime._refresh_active_irrigation_readback({'active_irrigation_context':context},transport,client.backend.now,clock=lambda:client.backend.now)
 assert output['active_irrigation_context']['zone_output_evidence']=={}
 assert calls==['/v2/device/thing']


def test_pulse_parent_custom_transport_signature_is_unchanged(monkeypatch):
 native,calls,flags,client,context,_=_pulse_parent_harness(monkeypatch)
 class Custom:
  def read_output_state(self,*,device_id,channel):return native.read_output_state(device_id=device_id,channel=channel)
 assert _pulse_parent_refresh(_pulse_parent_runtime,Custom(),client,context)['state']=='ON'
 assert calls==['/v2/device/thing']
