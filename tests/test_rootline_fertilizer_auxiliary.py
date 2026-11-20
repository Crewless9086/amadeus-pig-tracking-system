from tests.test_rootline_ifttt_transport import irrigation_output
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

import pytest

from modules.telemetry.rootline_auxiliary_management import (
    auxiliary_notification_projection,
    build_auxiliary_eligibility, build_auxiliary_tasks,
    build_fertilized_irrigation_sequence, build_fertilizer_batch_lifecycle,
    mixer_configuration_preview, validate_auxiliary_eligibility,
)
from modules.telemetry.rootline_device_registry import (
    get_device_contract, rootline_device_registry, source_authority_defaults,
    validate_device_registry,
)
from modules.telemetry.rootline_irrigation_coordinator import (
    advance_auxiliary_execution as _advance_auxiliary_execution, emergency_off_auxiliary_execution,
    _recover_or_observe,
)

NOW=datetime(2026,8,9,8,0,tzinfo=timezone.utc)


def advance_auxiliary_execution(**kwargs):
    kwargs.setdefault("clock", lambda: kwargs.get("now", NOW))
    return _advance_auxiliary_execution(**kwargs)


def resign(row):
    row.pop("contract_sha256",None)
    row["contract_sha256"]=sha256(json.dumps(row,sort_keys=True,
        separators=(",",":"),default=str).encode()).hexdigest()


def safety(device="injection",**changes):
    channel=1 if device=="injection" else 2
    value={"authoritative":True,"response_digest":"READ-SAFETY-1",
        "device_id":"100204d497","channel":channel,"output_state":"OFF",
        "native_inching_enabled":True,"native_inching_seconds":120 if channel==1 else 1800,
        "power_restoration_state":"OFF","schedules_enabled":False,"timers_enabled":False,
        "scenes_enabled":False,"interlock_enabled":False,
        "controller_safety_generation":"SAFETY-1",
        "physical_commissioning_generation":"COMMISSION-1","commissioned":True,
        "observed_at":NOW.isoformat()}
    value.update(changes);return value


def injection_context(**changes):
    value={"plan_generation":"PLAN-1","batch_generation":"BATCH-1",
        "fertilizer_needed":True,"premix_verified":True,
        "fertilizer_history_complete_through": NOW.isoformat(),
        "job_id":"ROOTLINE-IRRIGATION-JOB-"+"A"*24,"job_sha256":"a"*64,
        "segment_identity":"ROOTLINE-JOB-SEGMENT-"+"B"*24,
        "active_zone_ids":["B12345"],"zone_execution_id":"ZONE-EXEC-1",
        "zone_device_id":"100204e9bc","zone_channel":1,
        "zone_start_evidence":{"evidence_id":"START-1","zone_execution_id":"ZONE-EXEC-1",
            "observed_at":(NOW-timedelta(seconds=600)).isoformat()},
        "zone_output_evidence":{**irrigation_output(NOW),"zone_execution_id":"ZONE-EXEC-1",
            "observed_at":NOW.isoformat(),"state":"ON"},
        "irrigation_stop_deadline":(NOW+timedelta(seconds=1800)).isoformat(),
        "completed_pulses":0,
        "mixer_active":False,"prior_shutdown_unverified":False}
    value.update(changes);return value


def injection_eligibility(**context_changes):
    return build_auxiliary_eligibility(task={
        "auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},safety=safety(),
        context=injection_context(**context_changes),
        flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=NOW)


def mixer_eligibility(**context_changes):
    context={"plan_generation":"PLAN-MIX-1","injection_active":False,
        "verified_mixing_minutes_today":0,"verified_mixing_sessions_today":0,
        "mixing_history_valid":True,"reserved_mixing_seconds_today":0,
        "mixing_history_complete_through":NOW.isoformat(),"power_suitable":True}
    context.update(context_changes)
    context["reserved_mixing_seconds_today"] = float(context.get("verified_mixing_minutes_today") or 0)*60
    return build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-MIXER-CH2",
        "planned_seconds":int((30-float(context.get("verified_mixing_minutes_today") or 0))*60)},
        safety=safety("mixer"),context=context,
        flags={"ROOTLINE_FERTILIZER_MIXING_ENABLED":True},now=NOW)


def test_exact_typed_registry_mappings_and_source_flags_are_off():
    registry=rootline_device_registry()
    injection=registry["FERTILIZER-INJECTION-CH1"]
    mixer=registry["FERTILIZER-MIXER-CH2"]
    assert (injection["device_id"],injection["channel"],injection["on_event"],injection["off_event"])==(
        "100204d497",1,"controller_1_ch1_on","controller_1_ch1_off")
    assert (mixer["channel"],mixer["on_event"],mixer["off_event"])==(
        2,"controller_1_ch2_on","controller_1_ch2_off")
    assert injection["collection"]==mixer["collection"]=="irrigation_auxiliary_devices"
    assert source_authority_defaults({})=={
        "ROOTLINE_FERTILIZER_MIXING_ENABLED":False,
        "ROOTLINE_FERTILIZER_INJECTION_ENABLED":False,
        "ROOTLINE_BOREHOLE_ENABLED":False}
    assert not injection["commissioned"] and not mixer["commissioned"]


def test_registry_rejects_event_and_provider_binding_collisions():
    rows=rootline_device_registry(); duplicate=deepcopy(rows["FERTILIZER-MIXER-CH2"])
    duplicate.update(identity="COLLISION",device_id="test-device",on_event="controller_1_ch1_on")
    resign(duplicate)
    rows["COLLISION"]=duplicate
    with pytest.raises(ValueError,match="event_collision"):validate_device_registry(rows)
    rows=rootline_device_registry(); duplicate=deepcopy(rows["FERTILIZER-MIXER-CH2"])
    duplicate.update(identity="COLLISION",on_event="unique_on",off_event="unique_off")
    resign(duplicate)
    rows["COLLISION"]=duplicate
    with pytest.raises(ValueError,match="binding_collision"):validate_device_registry(rows)


def test_mixer_preview_is_thirty_minutes_and_never_applies_configuration():
    preview=mixer_configuration_preview()
    assert preview["after"]["native_inching_seconds"]==1800
    assert preview["apply_configuration"] is False
    assert preview["configuration_authority"] is False


def test_sequence_has_two_120_second_pulses_preflow_spacing_and_flush():
    sequence=build_fertilized_irrigation_sequence(zone_id="B12345")
    stages={row["stage"]:row for row in sequence["stages"]}
    assert stages["clean_water_preflow"]["minimum_seconds"]==600
    assert stages["injection_pulse_1"]["maximum_seconds"]==120
    assert stages["pulse_spacing"]["minimum_seconds"]==600
    assert stages["injection_pulse_2"]["maximum_seconds"]==120
    assert stages["clean_water_flush"]["minimum_seconds"]==600
    assert sequence["max_injection_pulses"]==2
    assert sequence["irrigation_may_complete_if_fertilizer_fails"] is True
    assert sequence["nutrient_dose"]=="Unknown"


def test_injection_requires_exact_zone_preflow_spacing_flush_and_only_two_pulses():
    first=injection_eligibility()
    assert first["eligible"] and first["pulse_number"]==1
    second=injection_eligibility(completed_pulses=1,prior_pulse_shutdown_evidence={
        "evidence_id":"PULSE-1-OFF","zone_execution_id":"ZONE-EXEC-1",
        "shutdown_verified":True,"observed_at":(NOW-timedelta(seconds=600)).isoformat()})
    assert second["eligible"] and second["pulse_number"]==2
    cases=[
        ({"job_id":None},"irrigation_job_binding_incomplete"),
        ({"active_zone_ids":[]},"exactly_one_bc_zone_required"),
        ({"active_zone_ids":["B12345","C12345"]},"exactly_one_bc_zone_required"),
        ({"zone_start_evidence":{"evidence_id":"START-X","zone_execution_id":"ZONE-EXEC-1",
            "observed_at":(NOW-timedelta(seconds=599)).isoformat()}},"clean_water_preflow_incomplete"),
        ({"irrigation_stop_deadline":(NOW+timedelta(seconds=1439)).isoformat()},
            "clean_water_flush_window_incomplete"),
        ({"completed_pulses":1,"prior_pulse_shutdown_evidence":{
            "evidence_id":"PULSE-1-OFF","zone_execution_id":"ZONE-EXEC-1",
            "shutdown_verified":True,"observed_at":(NOW-timedelta(seconds=599)).isoformat()}},
            "pulse_spacing_incomplete"),
        ({"completed_pulses":1,"prior_pulse_shutdown_evidence":{
            "evidence_id":"PULSE-1-OFF","zone_execution_id":"ZONE-EXEC-1",
            "shutdown_verified":True,"observed_at":(NOW-timedelta(seconds=600)).isoformat()},
            "irrigation_stop_deadline":(NOW+timedelta(seconds=719)).isoformat()},
            "clean_water_flush_window_incomplete"),

        ({"completed_pulses":2},"two_pulse_limit_reached"),
    ]
    for changes,status in cases:
        assert injection_eligibility(**changes)["status"]==status


def test_unverified_reported_inching_and_disabled_flag_fail_closed():
    disabled=build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
        safety=safety(),context=injection_context(),flags={},now=NOW)
    assert disabled["status"]=="auxiliary_authority_disabled"
    unverified=safety(physical_commissioning_generation=None,commissioned=False)
    value=build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
        safety=unverified,context=injection_context(),
        flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=NOW)
    assert value["status"]=="auxiliary_safety_unproven"
    for untrusted in (safety(authoritative=False),safety(response_digest=None)):
        value=build_auxiliary_eligibility(task={
            "auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},safety=untrusted,
            context=injection_context(),flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},
            now=NOW)
        assert value["status"]=="auxiliary_safety_unproven"


def test_mixing_thirty_minute_fail_stop_daily_cap_and_low_power_deferral():
    assert mixer_eligibility()["maximum_duration_seconds"]==1800
    assert mixer_eligibility(verified_mixing_minutes_today=0)["eligible"]
    split=mixer_eligibility(verified_mixing_minutes_today=25)
    assert split["eligible"] and split["maximum_duration_seconds"]==300
    assert mixer_eligibility(verified_mixing_minutes_today=30)["status"]=="planned_mixing_runtime_invalid"
    assert mixer_eligibility(verified_mixing_sessions_today=6)["status"]=="daily_mixing_session_cap_reached"
    assert mixer_eligibility(power_suitable=False)["status"]=="low_power_mix_deferred"
    assert mixer_eligibility(injection_active=True)["eligible"] is True
    assert injection_eligibility(mixer_active=True)["eligible"] is True


def test_batch_lifecycle_monday_dedup_dilution_and_unknown_nutrients():
    due=build_fertilizer_batch_lifecycle(now=NOW)
    assert due["state"]=="monday_batch_due" and due["monday_work_item"]["emit"]
    assert due["nutrient_dose"]==due["concentration"]=="Unknown"
    repeated=build_fertilizer_batch_lifecycle(now=NOW,
        previous_work_item_key=due["monday_work_item"]["deduplication_key"])
    assert repeated["monday_work_item"]["emit"] is False
    prepared=build_fertilizer_batch_lifecycle(observations=[
        {"event_type":"fertilizer_batch_prepared","observed_at":"2026-08-03T06:00:00+02:00"},
        {"event_type":"water_only_refill","observed_at":"2026-08-05T12:00:00+02:00"}],now=NOW)
    assert prepared["state"]=="batch_reported_prepared"
    assert prepared["monday_work_item"]["emit"] is False
    assert prepared["dilution_acknowledged"] is True
    assert prepared["concentration"]=="Unknown"
    notification=auxiliary_notification_projection(batch=due,
        previous_batch_work_item_key=due["monday_work_item"]["deduplication_key"])
    assert notification["emit_monday_batch_reminder"] is False
    assert notification["unchanged_auxiliary_tasks_silent"] is True


def test_batch_lifecycle_rejects_future_malformed_and_prior_week_evidence():
    value=build_fertilizer_batch_lifecycle(observations=[
        {"event_type":"fertilizer_batch_prepared","observed_at":"2026-08-10T08:00:00+02:00"},
        {"event_type":"water_only_refill","observed_at":"not-a-time"}],executions=[
        {"execution_id":"OLD-MIX","device_type":"fertilizer_mixer",
         "shutdown_verified":True,"completed_at":"2026-08-02T08:00:00+02:00"}],now=NOW)
    assert value["state"]=="monday_batch_due"
    assert value["dilution_acknowledged"] is False
    assert value["invalid_timestamp_evidence_count"]==1
    assert value["mixing_execution_ids"]==[]


def test_auxiliary_tasks_never_become_zones_and_power_only_defers_mixing():
    batch=build_fertilizer_batch_lifecycle(observations=[{
        "event_type":"fertilizer_batch_prepared",
        "observed_at":"2026-08-09T09:30:00+02:00"}],now=NOW)
    incomplete=build_auxiliary_tasks(batch=batch,power={"battery_soc_pct":90,
        "solar_power_w":2000,"grid_power_w":0},now=NOW)
    assert incomplete["irrigation_auxiliary_tasks"][0]["decision"]=="Needs Data"
    assert incomplete["irrigation_auxiliary_tasks"][0]["reason"]=="mixing_history_incomplete"
    missing=build_auxiliary_tasks(batch=batch,power={},
        mixing_history_complete_through=NOW.isoformat(),now=NOW)
    assert missing["irrigation_auxiliary_tasks"][0]["decision"]=="Needs Data"
    low=build_auxiliary_tasks(batch=batch,power={"battery_soc_pct":20,
        "solar_power_w":0,"grid_power_w":0,"load_power_w":1000,"observed_at":NOW.isoformat()},
        mixing_history_complete_through=NOW.isoformat(),now=NOW)
    assert low["irrigation_zones"]==[] and low["zone_delivery_debt_changes"]==0
    tasks={row["device_type"]:row for row in low["irrigation_auxiliary_tasks"]}
    assert tasks["fertilizer_mixer"]["decision"]=="Run later"
    assert tasks["fertilizer_injection_valve"]["does_not_block_bc_irrigation"] is True
    capped=build_auxiliary_tasks(batch=batch,verified_mixing=[{
        "execution_id":"MIX-TODAY","device_type":"fertilizer_mixer",
        "claimed_at":"2026-08-09T06:30:00+02:00","maximum_duration_seconds":1800,
        "shutdown_verified":True,"accounted_mixing_seconds":1800,"control_completed":True,
        "completed_at":"2026-08-09T07:00:00+02:00"}],
        mixing_history_complete_through=NOW.isoformat(),now=NOW)
    mixer=next(row for row in capped["irrigation_auxiliary_tasks"]
               if row["device_type"]=="fertilizer_mixer")
    assert mixer["decision"]=="Completed" and mixer["planned_seconds"]==0


def test_injector_task_promotes_only_from_exact_need_active_preflow_and_flush():
    batch=build_fertilizer_batch_lifecycle(observations=[{
        "event_type":"fertilizer_batch_prepared",
        "observed_at":"2026-08-09T09:30:00+02:00"}],now=NOW)
    ready=build_auxiliary_tasks(batch=batch,active_irrigation_context=injection_context(),now=NOW)
    task=next(row for row in ready["irrigation_auxiliary_tasks"]
        if row["device_type"]=="fertilizer_injection_valve")
    assert task["decision"]=="Run now"
    for change in ({"fertilizer_needed":False},
            {"zone_start_evidence":{}},
            {"irrigation_stop_deadline":(NOW+timedelta(minutes=5)).isoformat()}):
        held=build_auxiliary_tasks(batch=batch,
            active_irrigation_context=injection_context(**change),now=NOW)
        injection=next(row for row in held["irrigation_auxiliary_tasks"]
            if row["device_type"]=="fertilizer_injection_valve")
        assert injection["decision"]=="Await eligible irrigation"


class Store:
    def __init__(self):
        self.active=None;self.rows=[];self.consumed=set();self.off=[];self.lock=Lock()
        self.contained=False;self.physical=None
    def __call__(self,action,payload):
        if action=="load_active":
            ctx=injection_context()
            return {"execution_id":ctx["zone_execution_id"],"state":"Active",
                "device_id":"100204e9bc","channel":1,"zone_id":"B12345",
                "primary_stop_deadline":ctx["irrigation_stop_deadline"],
                **{key:ctx[key] for key in ("job_id","job_sha256","segment_identity")}}
        if action=="load_active_auxiliaries":return [self.active] if self.active else []
        if action=="load_active_auxiliary":return self.active
        if action=="load_auxiliary_containment":return {"contained":self.contained}
        if action=="load_auxiliary_off_attempts":return list(self.off)
        if action=="load_auxiliary_physical_outcome":return self.physical
        if action=="claim_auxiliary_before_on":
            with self.lock:
                key=payload["consumption_key"]
                if key in self.consumed:return {"success":True,"created":False}
                self.consumed.add(key);self.active=payload;self.rows.append((action,payload))
                return {"success":True,"created":True}
        if action=="dispatch_auxiliary_on_edge":return payload["dispatch"]()
        if action == "dispatch_auxiliary_off_edge":
            slot = {key: payload[key] for key in ("execution_id", "attempt")}
            claimed = self("claim_auxiliary_off_attempt", slot)
            if claimed.get("created") is not True:
                return {"accepted_unambiguous": False, "provider_command_attempted": False}
            outcome = payload["dispatch"]()
            self("record_auxiliary_off_outcome", {**slot, "outcome": outcome})
            return {**outcome, "provider_command_attempted": True}
        if action=="claim_auxiliary_off_attempt":
            row={"attempt":payload["attempt"]};self.off.append(row);return {"created":True,"success":True}
        self.rows.append((action,payload))
        if action=="mark_auxiliary_active":self.active=payload
        if action in {"record_auxiliary_completed","record_auxiliary_control_pulse_stopped"}:
            self.active=None
        if action=="contain_auxiliary_device" and payload.get("shutdown_verified") is True:
            self.active=None
        return {"success":True,"created":True}


class Transport:
    def __init__(self,on=True,read="ON",off=True):self.on=on;self.read=read;self.off=off;self.calls=[]
    def set_state(self,**kwargs):
        self.calls.append(kwargs)
        accepted=self.on if kwargs["state"]=="ON" else self.off
        if kwargs["state"]=="OFF" and accepted:self.read="OFF"
        return {"accepted_unambiguous":accepted}
    def read_output_state(self,**_kwargs):
        if _kwargs.get("device_id")=="100204e9bc":
            return irrigation_output(NOW,channel=_kwargs["channel"])
        state=self.read
        return {"authoritative":True,"state":state,"evidence_id":"READ-1",
            "retrieved_at":(NOW+timedelta(seconds=120 if state=='OFF' else 0)).isoformat()}
    def read_safety_configuration(self,**kwargs):
        return safety("injection" if kwargs["channel"]==1 else "mixer")


def test_coordinator_exactly_once_replay_completion_and_bounded_off():
    artifact=injection_eligibility();store=Store();transport=Transport()
    started=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,revalidate=lambda _artifact:injection_context(),now=NOW)
    replay=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,now=NOW+timedelta(seconds=1))
    completed=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,now=NOW+timedelta(seconds=121))
    duplicate=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,revalidate=lambda _artifact:injection_context(),
        now=NOW+timedelta(seconds=121))
    assert started["status"]=="auxiliary_started" and replay["status"]=="auxiliary_active"
    assert completed["status"]=="auxiliary_injection_control_completed"
    assert duplicate["status"]=="auxiliary_claim_conflict"
    assert [row["state"] for row in transport.calls]==["ON","OFF"]
    assert completed["execution"]["nutrient_dose"]=="Unknown"
    assert completed["execution"]["verified_runtime_seconds"] is None
    assert completed["execution"]["maximum_runtime_seconds"]==120
    assert completed["execution"]["completion_scope"]=="provider_canonical_control_pulse"
    assert completed["physical_delivery_verified"] is False
    assert any(action=="record_auxiliary_completed" for action,_ in store.rows)


def test_injection_delivery_completion_requires_exact_bound_canonical_provider_and_physical_evidence():
    artifact=injection_eligibility();store=Store();transport=Transport()
    started=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,revalidate=lambda _artifact:injection_context(),now=NOW)
    active=started["execution"]
    complete={key:active.get(key) for key in ("execution_id","job_id","job_sha256",
        "segment_identity","zone_id","zone_execution_id","pulse_number")}
    store.physical={**complete,"evidence_id":"PHYSICAL-INJECTION-1",
        "canonical_pulse_recorded":True,"provider_pulse_on_verified":True,
        "provider_pulse_off_verified":True,"physical_fertilizer_flow_verified":True,
        "clean_water_preflow_verified":True,"clean_water_flush_verified":False}
    result=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,now=NOW+timedelta(seconds=121))
    assert result["status"]=="auxiliary_injection_control_completed"
    assert result["physical_delivery_verified"] is True
    assert result["execution"]["completion_scope"]==(
        "provider_canonical_control_pulse")
    assert result["execution"]["fertilizer_lifecycle_completed"] is False
    assert result["execution"]["postflow_flush_required"] is True
    assert any(action=="record_auxiliary_completed" for action,_ in store.rows)


@pytest.mark.parametrize("field,replacement",[
    ("execution_id","WRONG"),("job_sha256","b"*64),
    ("zone_execution_id","WRONG"),("pulse_number",2),
    ("canonical_pulse_recorded",False),("provider_pulse_on_verified",False),
    ("provider_pulse_off_verified",False),("physical_fertilizer_flow_verified",False),
    ("clean_water_preflow_verified",False),
])
def test_injection_mismatched_or_incomplete_evidence_never_promotes_delivery(field,replacement):
    artifact=injection_eligibility();store=Store();transport=Transport()
    started=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,revalidate=lambda _artifact:injection_context(),now=NOW)
    active=started["execution"]
    store.physical={key:active.get(key) for key in ("execution_id","job_id","job_sha256",
        "segment_identity","zone_id","zone_execution_id","pulse_number")}
    store.physical.update({"evidence_id":"PHYSICAL-INJECTION-1",
        "canonical_pulse_recorded":True,"provider_pulse_on_verified":True,
        "provider_pulse_off_verified":True,"physical_fertilizer_flow_verified":True,
        "clean_water_preflow_verified":True,"clean_water_flush_verified":False,
        field:replacement})
    result=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,now=NOW+timedelta(seconds=121))
    assert result["status"]=="auxiliary_injection_control_completed"
    assert result["physical_delivery_verified"] is False
    assert any(action=="record_auxiliary_completed" for action,_ in store.rows)


def test_concurrent_consumption_creates_exactly_one_on_attempt():
    artifact=injection_eligibility();store=Store();transport=Transport()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _index:advance_auxiliary_execution(
            eligibility=artifact,store=store,transport=transport,
            revalidate=lambda _artifact:injection_context(),now=NOW),range(2)))
    assert "auxiliary_started" in [row["status"] for row in results]
    assert set(row["status"] for row in results)<={"auxiliary_started",
        "auxiliary_claim_conflict","auxiliary_claim_in_progress","auxiliary_active"}
    assert [row["state"] for row in transport.calls]==["ON"]


def test_emergency_off_is_exact_bound_and_authoritatively_verified():
    store=Store();transport=Transport();artifact=mixer_eligibility()
    started=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,revalidate=lambda _artifact:{
            "plan_generation":"PLAN-MIX-1","injection_active":False,
            "verified_mixing_minutes_today":0,"verified_mixing_sessions_today":0,
            "reserved_mixing_seconds_today":0,"mixing_history_valid":True,
            "mixing_history_complete_through":NOW.isoformat(),"power_suitable":True},
        now=NOW)
    assert started["status"]=="auxiliary_started"
    stopped=emergency_off_auxiliary_execution(
        store=store,transport=transport,reason="owner_emergency_stop")
    assert stopped["status"]=="auxiliary_emergency_off_verified"
    assert stopped["shutdown_verified"] is True
    assert [row["state"] for row in transport.calls]==["ON","OFF"]


def test_emergency_off_contains_unverified_shutdown_without_other_authority():
    store=Store();store.active={"execution_id":"MIXER-1",
        "auxiliary_device_id":"FERTILIZER-MIXER-CH2","device_id":"100204d497",
        "channel":2,"state":"Active"}
    transport=Transport(off=False,read="ON")
    result=emergency_off_auxiliary_execution(
        store=store,transport=transport)
    assert result["status"]=="auxiliary_emergency_off_unverified"
    assert result["shutdown_verified"] is False
    assert result["auxiliary_contained"] is True
    assert result["borehole_authority"] is False
    assert result["channels_3_4_authority"] is False
    assert [row["state"] for row in transport.calls]==["OFF","OFF","OFF"]


def test_emergency_off_rejects_an_active_injection_execution_without_command():
    store=Store();store.active={"execution_id":"INJECTION-1",
        "auxiliary_device_id":"FERTILIZER-INJECTION-CH1","device_id":"100204d497",
        "channel":1,"state":"Active"}
    transport=Transport(read="ON")
    result=emergency_off_auxiliary_execution(store=store,transport=transport)
    assert result["status"]=="auxiliary_emergency_off_binding_mismatch"
    assert result["hardware_commands"]==0
    assert transport.calls==[]


def test_irrigation_abort_can_stop_exact_active_injection_and_verify_off():
    store=Store();store.active={"execution_id":"INJECTION-1",
        "auxiliary_device_id":"FERTILIZER-INJECTION-CH1","device_id":"100204d497",
        "channel":1,"state":"Active"}
    transport=Transport(read="ON")
    result=emergency_off_auxiliary_execution(store=store,transport=transport,
        reason="parent_irrigation_abort",expected_device_id="FERTILIZER-INJECTION-CH1")
    assert result["status"]=="auxiliary_emergency_off_verified"
    assert result["shutdown_verified"] is True
    assert [row["state"] for row in transport.calls]==["OFF"]


class ParentAuxStore:
    def __init__(self, parent, auxiliary):
        self.parent=parent;self.auxiliary=auxiliary;self.rows=[];self.off=[];self.lock=Lock()
    def __call__(self,action,payload):
        if action=="load_active_auxiliary":return self.auxiliary
        if action=="load_auxiliary_off_attempts":return list(self.off)
        if action=="mark_stopping":
            self.parent=dict(payload);self.rows.append((action,payload))
            return {"success":True,"created":True}
        if action == "dispatch_auxiliary_off_edge":
            slot = {key: payload[key] for key in ("execution_id", "attempt")}
            claimed = self("claim_auxiliary_off_attempt", slot)
            if claimed.get("created") is not True:
                return {"accepted_unambiguous": False, "provider_command_attempted": False}
            outcome = payload["dispatch"]()
            self("record_auxiliary_off_outcome", {**slot, "outcome": outcome})
            return {**outcome, "provider_command_attempted": True}
        if action=="claim_auxiliary_off_attempt":
            with self.lock:
                if any(row.get("attempt")==payload["attempt"] for row in self.off):
                    return {"success":True,"created":False}
                self.off.append({"attempt":payload["attempt"]})
                return {"success":True,"created":True}
        if action=="record_auxiliary_off_outcome":
            self.rows.append((action,payload));return {"success":True,"created":True}
        if action=="contain_auxiliary_device":
            self.rows.append((action,payload))
            if payload.get("shutdown_verified") is True:self.auxiliary=None
            return {"success":True,"created":True}
        if action=="claim_notification":
            self.rows.append((action,payload));return {"success":True,"created":True}
        self.rows.append((action,payload));return {"success":True,"created":True}


class ParentAuxTransport:
    def __init__(self, injector_state="ON", accept_injector_off=False,
                 parent_state="ON", parent_authoritative=True,
                 parent_read_raises=False):
        self.injector_state=injector_state
        self.accept_injector_off=accept_injector_off;self.calls=[]
        self.parent_state=parent_state;self.parent_authoritative=parent_authoritative
        self.parent_read_raises=parent_read_raises
    def set_state(self,**kwargs):
        self.calls.append(kwargs)
        injection=kwargs["device_id"]=="100204d497" and kwargs["channel"]==1
        accepted=self.accept_injector_off if injection else True
        if accepted and kwargs["state"]=="OFF":
            if injection:self.injector_state="OFF"
        return {"accepted_unambiguous":accepted}
    def read_output_state(self,**kwargs):
        injection=kwargs["device_id"]=="100204d497" and kwargs["channel"]==1
        if not injection and self.parent_read_raises:raise RuntimeError("provider unavailable")
        return {"authoritative":True,"state":self.injector_state if injection else "ON",
            **({} if injection else {"authoritative":self.parent_authoritative,
                "state":self.parent_state}),
            "evidence_id":"INJECTOR-READ" if injection else "PARENT-READ",
            "retrieved_at":NOW.isoformat()}


def parent_and_injection(*,mismatch=False,state="Active"):
    parent={"execution_id":"PARENT-1","zone_id":"B12345","channel":1,
        "state":state,"job_id":"JOB-1","job_sha256":"a"*64,
        "segment_identity":"SEGMENT-1","zone_execution_id":"PARENT-1",
        "primary_stop_deadline":(NOW-timedelta(seconds=1)).isoformat(),
        "native_fail_stop_deadline":(NOW+timedelta(minutes=1)).isoformat()}
    auxiliary={"execution_id":"INJECTION-BOUND-1",
        "auxiliary_device_id":"FERTILIZER-INJECTION-CH1","device_id":"100204d497",
        "channel":1,"state":"Active","job_id":"OTHER" if mismatch else "JOB-1",
        "job_sha256":"a"*64,"segment_identity":"SEGMENT-1","zone_id":"B12345",
        "zone_execution_id":"PARENT-1","pulse_number":1}
    return parent,auxiliary


@pytest.mark.parametrize("state,deadline_missing",[
    ("Active",False),("claimed_recovery_required",False),("Active",True)])
def test_deadline_abort_and_restart_retain_parent_flow_when_injector_off_unverified(
        state,deadline_missing):
    parent,auxiliary=parent_and_injection(state=state)
    if deadline_missing:parent["primary_stop_deadline"]=None
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False)
    result=_recover_or_observe(parent,store,transport,
        lambda *_:{"success":True,"provider_delivery_confirmed":True,
            "provider_message_id":"MSG-1"},lambda _:None,NOW)
    assert result["status"]=="parent_off_withheld_injector_off_unverified"
    assert result["irrigation_flow_retained"] is None
    assert result["irrigation_flow_state"]=="Unknown"
    assert result["parent_output_authoritative"] is True
    assert result["parent_output_state"]=="ON"
    assert result["parent_off_command_withheld"] is True
    assert result["parent_shutdown_aborted"] is True
    assert not any(call["device_id"]!="100204d497" for call in transport.calls)
    conflict=next(payload for action,payload in store.rows
        if action=="contain_zone" and payload.get("safety_conflict_owner"))
    assert conflict["safety_conflict_owner"]=="rootline_irrigation_coordinator"
    assert conflict["automatic_continuation"]==(
        "reload_stopping_execution_and_reverify_injector_off")
    assert conflict["conflict_deadline"]==parent["native_fail_stop_deadline"]


def test_binding_mismatch_is_explicit_and_parent_flow_stays_on_until_injector_off():
    parent,auxiliary=parent_and_injection(mismatch=True)
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False)
    result=_recover_or_observe(parent,store,transport,
        lambda *_:{"success":False},lambda _:None,NOW)
    assert result["status"]=="parent_off_withheld_injector_off_unverified"
    assert result["parent_binding_mismatch"] is True
    assert all(call["device_id"]=="100204d497" for call in transport.calls)


def test_restart_replay_reads_injector_off_then_allows_exactly_one_parent_off():
    parent,auxiliary=parent_and_injection()
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False)
    first=_recover_or_observe(parent,store,transport,
        lambda *_:{"success":False},lambda _:None,NOW)
    assert first["status"]=="parent_off_withheld_injector_off_unverified"
    assert len(transport.calls)==3
    transport.injector_state="OFF"
    second=_recover_or_observe(store.parent,store,transport,
        lambda *_:{"success":False},lambda _:None,NOW+timedelta(seconds=1))
    parent_off=[call for call in transport.calls if call["device_id"]!="100204d497"]
    assert len(parent_off)==1 and parent_off[0]["state"]=="OFF"
    assert second["status"] in {"shutdown_unverified","segment_stopped_outcome_unconfirmed"}


def test_concurrent_parent_shutdown_recovery_never_bypasses_unverified_injector_off():
    parent,auxiliary=parent_and_injection()
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _index:_recover_or_observe(parent,store,transport,
            lambda *_:{"success":False},lambda _:None,NOW),range(2)))
    assert all(row["status"]=="parent_off_withheld_injector_off_unverified"
        for row in results)
    assert len(transport.calls)==3
    assert all(call["device_id"]=="100204d497" for call in transport.calls)


@pytest.mark.parametrize("parent_state,parent_authoritative",[("Unknown",False),("FAULT",True)])
def test_unavailable_or_contradictory_parent_readback_never_claims_flow(
        parent_state,parent_authoritative):
    parent,auxiliary=parent_and_injection()
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False,
        parent_state=parent_state,parent_authoritative=parent_authoritative)
    result=_recover_or_observe(parent,store,transport,
        lambda *_:{"success":False},lambda _:None,NOW)
    assert result["status"]=="parent_output_unverified_injector_off_unverified"
    assert result["parent_output_authoritative"] is False
    assert result["parent_output_state"]=="Unknown"
    assert result["irrigation_flow_retained"] is None
    assert result["irrigation_flow_state"]=="Unknown"


def test_parent_provider_exception_is_durable_unknown_not_assumed_flow():
    parent,auxiliary=parent_and_injection()
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False,
        parent_read_raises=True)
    result=_recover_or_observe(parent,store,transport,
        lambda *_:{"success":False},lambda _:None,NOW)
    assert result["status"]=="parent_output_unverified_injector_off_unverified"
    assert result["parent_output_state"]=="Unknown"
    conflict=next(payload for action,payload in store.rows
        if action=="contain_zone" and payload.get("safety_conflict_owner"))
    assert conflict["parent_output_evidence"]=={
        "authoritative":False,"state":"Unknown"}


def test_early_authoritative_parent_off_is_immediately_urgent_and_owns_both_final_states():
    parent,auxiliary=parent_and_injection()
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False,
        parent_state="OFF")
    result=_recover_or_observe(parent,store,transport,
        lambda *_:{"success":False},lambda _:None,NOW)
    assert result["status"]=="parent_off_observed_injector_off_unverified"
    assert result["native_deadline_phase"]=="before"
    assert result["urgent_intervention_required"] is True
    assert result["irrigation_flow_state"]=="Unknown"
    assert result["irrigation_flow_retained"] is None
    assert result["parent_off_command_withheld"] is True
    assert not any(call["device_id"]!="100204d497" for call in transport.calls)
    conflict=next(payload for action,payload in store.rows
        if action=="contain_zone" and payload.get("safety_conflict_owner"))
    assert conflict["automatic_continuation"]==(
        "urgent_reverify_injector_and_parent_final_states")
    assert conflict["safety_conflict_owner"]=="rootline_irrigation_coordinator"


def test_exact_native_deadline_equality_is_urgent_and_preserves_unknown_flow():
    parent,auxiliary=parent_and_injection()
    parent["native_fail_stop_deadline"]=NOW.isoformat()
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False,
        parent_state="ON")
    result=_recover_or_observe(parent,store,transport,
        lambda *_:{"success":False},lambda _:None,NOW)
    assert result["status"]=="injector_off_unverified_native_deadline_elapsed"
    assert result["native_deadline_phase"]=="at_or_after"
    assert result["urgent_intervention_required"] is True
    assert result["irrigation_flow_state"]=="Unknown"
    assert result["irrigation_flow_retained"] is None
    assert not any(call["device_id"]!="100204d497" for call in transport.calls)


def test_concurrent_early_parent_off_replay_cannot_downgrade_urgency_or_command_parent():
    parent,auxiliary=parent_and_injection()
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False,
        parent_state="OFF")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _index:_recover_or_observe(parent,store,transport,
            lambda *_:{"success":False},lambda _:None,NOW),range(2)))
    assert all(result["status"]=="parent_off_observed_injector_off_unverified"
        and result["urgent_intervention_required"] is True
        and result["irrigation_flow_state"]=="Unknown" for result in results)
    assert all(call["device_id"]=="100204d497" for call in transport.calls)
    conflicts=[payload for action,payload in store.rows
        if action=="contain_zone" and payload.get("safety_conflict_owner")]
    assert conflicts and all(item["automatic_continuation"]==
        "urgent_reverify_injector_and_parent_final_states" for item in conflicts)


def test_concurrent_deadline_elapsed_replay_stays_urgent_and_never_commands_parent():
    parent,auxiliary=parent_and_injection()
    parent["native_fail_stop_deadline"]=(NOW-timedelta(seconds=1)).isoformat()
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False,
        parent_state="ON")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _index:_recover_or_observe(parent,store,transport,
            lambda *_:{"success":False},lambda _:None,NOW),range(2)))
    assert all(result["status"]=="injector_off_unverified_native_deadline_elapsed"
        and result["urgent_intervention_required"] is True
        and result["irrigation_flow_state"]=="Unknown" for result in results)
    assert all(call["device_id"]=="100204d497" for call in transport.calls)


@pytest.mark.parametrize("state",["Active","claimed_recovery_required","stopping"])
def test_native_deadline_elapsed_escalates_and_never_claims_clean_water(state):
    parent,auxiliary=parent_and_injection(state=state)
    store=ParentAuxStore(parent,auxiliary)
    transport=ParentAuxTransport(injector_state="ON",accept_injector_off=False,
        parent_state="OFF")
    result=_recover_or_observe(parent,store,transport,
        lambda *_:{"success":False},lambda _:None,NOW+timedelta(minutes=2))
    assert result["status"]=="injector_off_unverified_native_deadline_elapsed"
    assert result["native_deadline_phase"]=="at_or_after"
    assert result["urgent_intervention_required"] is True
    assert result["parent_output_state"]=="OFF"
    assert result["irrigation_flow_retained"] is None
    assert not any(call["device_id"]!="100204d497" for call in transport.calls)
    conflict=next(payload for action,payload in store.rows
        if action=="contain_zone" and payload.get("safety_conflict_owner"))
    assert conflict["automatic_continuation"]==(
        "urgent_reverify_injector_and_parent_final_states")


def test_ambiguous_on_never_retries_and_fertilizer_failure_preserves_irrigation():
    store=Store();transport=Transport(on=False,read="OFF")
    result=advance_auxiliary_execution(eligibility=injection_eligibility(),store=store,
        transport=transport,revalidate=lambda _artifact:injection_context(),now=NOW)
    assert [row["state"] for row in transport.calls]==["ON","OFF"]
    assert result["fertilizer_debt"] is True
    assert result["irrigation_may_continue"] is True
    assert result["irrigation_shutdown_authority_unchanged"] is True
    assert result["automatic_on_retry"] is False


def test_injection_edge_revalidates_zone_on_and_flush_window_before_claim():
    for current in (injection_context(job_id="ROOTLINE-IRRIGATION-JOB-"+"C"*24),
            injection_context(job_sha256="c"*64),
            injection_context(segment_identity="ROOTLINE-JOB-SEGMENT-"+"D"*24),
            injection_context(zone_output_evidence={"evidence_id":"OUTPUT-2",
            "zone_execution_id":"ZONE-EXEC-1","observed_at":NOW.isoformat(),"state":"OFF"}),
            injection_context(irrigation_stop_deadline=(NOW+timedelta(seconds=1439)).isoformat())):
        store=Store();transport=Transport()
        result=advance_auxiliary_execution(eligibility=injection_eligibility(),store=store,
            transport=transport,revalidate=lambda _artifact,current=current:current,now=NOW)
        assert result["status"]=="auxiliary_edge_revalidation_failed"
        assert transport.calls==[] and store.consumed==set()


def test_restart_contains_auxiliary_only_with_repeatable_off():
    artifact=injection_eligibility();store=Store();store.active={
        "execution_id":artifact["execution_id"],"state":"claimed_recovery_required",
        "device_id":"100204d497","channel":1,"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"}
    transport=Transport(read="ON",off=False)
    result=advance_auxiliary_execution(eligibility=artifact,store=store,
        transport=transport,now=NOW)
    assert [row["state"] for row in transport.calls]==["OFF","OFF","OFF"]
    assert result["auxiliary_contained"] is True
    assert result["irrigation_may_continue"] is True
    assert result["channels_3_4_authority"] is False


def test_persisted_auxiliary_containment_blocks_new_artifact_without_on():
    store=Store();store.contained=True;transport=Transport()
    result=advance_auxiliary_execution(eligibility=injection_eligibility(),store=store,
        transport=transport,now=NOW)
    assert result["status"]=="auxiliary_device_contained"
    assert transport.calls==[]


def test_artifact_expiry_and_tamper_rejected():
    artifact=injection_eligibility()
    assert validate_auxiliary_eligibility(artifact,now=NOW)==artifact
    assert validate_auxiliary_eligibility(artifact,now=NOW+timedelta(minutes=6)) is None
    artifact["channel"]=3
    assert validate_auxiliary_eligibility(artifact,now=NOW) is None
    artifact=injection_eligibility();artifact["hardware_control"]=False
    assert validate_auxiliary_eligibility(artifact,now=NOW) is None


# Production-shaped late-start regression: a 140-second cycle reached claim
# with only 5.7 seconds remaining. The reserve and claim gates are independent.
@pytest.mark.parametrize("slow_stage", ["revalidation", "safety", "capacity"])
@pytest.mark.parametrize("mandatory", [False, True])
@pytest.mark.parametrize("finished_at", [111.0, 134.3])
def test_auxiliary_actual_cycle_budget_refuses_late_start_before_claim(monkeypatch, slow_stage, mandatory, finished_at):
    from contextlib import nullcontext
    from types import SimpleNamespace
    from modules.telemetry import rootline_cycle_budget as cycle
    from tests.test_rootline_ewelink_request_budget import MemoryBudget
    elapsed = [100.0]
    monkeypatch.setattr(cycle, "time", SimpleNamespace(monotonic=lambda: elapsed[0]))
    client = MemoryBudget()
    client.backend.now = NOW + timedelta(seconds=elapsed[0])
    reserve_calls = []
    def consume():
        elapsed[0] = finished_at
        client.backend.now = NOW + timedelta(seconds=elapsed[0])
    class SlowTransport(Transport):
        def read_safety_configuration(self, **kwargs):
            if slow_stage == "safety": consume()
            return super().read_safety_configuration(**kwargs)
        def prepare_execution_capacity(self, execution):
            reserve_calls.append(execution["execution_id"])
            permit = client.reserve_for_on(execution_id=execution["execution_id"],
                device_id=execution["device_id"], channel=execution["channel"],
                device_type=execution["device_type"], region="eu")
            if slow_stage == "capacity": consume()
            return permit
    def context(_artifact):
        if slow_stage == "revalidation": consume()
        return {"plan_generation": "PLAN-MIX-1", "injection_active": False,
            "verified_mixing_minutes_today": 20, "verified_mixing_sessions_today": 0,
            "reserved_mixing_seconds_today": 1200, "mixing_history_valid": True,
            "mixing_history_complete_through": NOW.isoformat(), "power_suitable": True}
    store, transport = Store(), SlowTransport()
    # Explicitly retain the actual cycle bound, not an enlarged test deadline.
    with cycle.cycle_budget(deadline=140.0):
        with cycle.mandatory_safety() if mandatory else nullcontext():
            result = advance_auxiliary_execution(eligibility=mixer_eligibility(verified_mixing_minutes_today=20),
                store=store, transport=transport, revalidate=context, now=NOW,
                clock=lambda: NOW+timedelta(seconds=elapsed[0]))
            assert cycle.on_deadline() == 140.0
            assert cycle.work_deadline() == (None if mandatory else 140.0)
    assert result["status"] == "auxiliary_start_budget_unavailable"
    assert result["hardware_commands"] == 0 and transport.calls == []
    assert store.rows == [] and store.consumed == set() and store.active is None
    assert len(reserve_calls) == (1 if slow_stage == "capacity" else 0)
    if slow_stage == "capacity":
        identity = reserve_calls[0]
        reserve = client.backend.state["reserves"][identity]
        assert reserve["phase"] == "pre_on"
        assert datetime.fromisoformat(reserve["admit_until"])-datetime.fromisoformat(reserve["reserved_at"]) == timedelta(seconds=30)
        if finished_at < 130.0:
            assert datetime.fromisoformat(reserve["admit_until"]) > client.backend.now
        client.backend.advance(max(0, 130.001-finished_at))
        # The following normal admission executes the real existing cleanup.
        client.reserve_for_on(execution_id="NEXT-NORMAL-ELIGIBILITY", device_id="100204d497",
            channel=2, device_type="fertilizer_mixer", region="eu")
        assert identity not in client.backend.state["reserves"]
        assert all(event["units"] == 0 for event in client.backend.events)
        assert any(identity in event["detail"].get("expired_never_attempted", [])
            for event in client.backend.events)
    else:
        assert client.backend.state is None


@pytest.mark.parametrize("remaining,expected", [(30.001, True), (30.0, False), (5.7, False), (0, False), (-1, False)])
def test_auxiliary_on_start_window_keeps_existing_bound_in_mandatory_safety(monkeypatch, remaining, expected):
    from types import SimpleNamespace
    from modules.telemetry import rootline_cycle_budget as cycle
    monkeypatch.setattr(cycle, "time", SimpleNamespace(monotonic=lambda: 140.0-remaining))
    assert cycle.on_start_window_available() is True  # Existing unbudgeted direct callers.
    with cycle.cycle_budget(deadline=140.0):
        with cycle.mandatory_safety():
            assert cycle.remaining_seconds() == float("inf")
            assert cycle.on_start_window_available() is expected
            with cycle.cycle_budget(deadline=1000.0):
                assert cycle.on_deadline() == 140.0
                assert cycle.on_start_window_available() is expected


def test_expired_start_budget_does_not_abandon_owned_auxiliary_off(monkeypatch):
    from types import SimpleNamespace
    from modules.telemetry import rootline_cycle_budget as cycle
    monkeypatch.setattr(cycle, "time", SimpleNamespace(monotonic=lambda: 141.0))
    store, transport = Store(), Transport(read="ON")
    store.active = {"execution_id": "OWNED-UNSTARTED", "state": "claimed_recovery_required",
        "device_id": "100204d497", "channel": 2, "auxiliary_device_id": "FERTILIZER-MIXER-CH2",
        "claimed_at": (NOW-timedelta(seconds=60)).isoformat(),
        "primary_stop_deadline": (NOW+timedelta(seconds=540)).isoformat()}
    with cycle.cycle_budget(deadline=140.0), cycle.mandatory_safety():
        result = advance_auxiliary_execution(eligibility=None, store=store, transport=transport, now=NOW,
            auxiliary_device_id="FERTILIZER-MIXER-CH2")
    assert result["status"] == "auxiliary_restart_contained"
    assert [call["state"] for call in transport.calls] == ["OFF"]
    held = next(payload for action, payload in store.rows if action == "contain_auxiliary_device")
    assert held["shutdown_verified"] is True and not store.consumed


# Exact canonical receipt from the 2026-11-20 incident: claim then OFF/hold,
# with no dispatch or ON outcome. No provider responses are fabricated here.
_NO_DISPATCH_HISTORY_553987 = json.loads(r'''[
  {
    "action": "record_auxiliary_eligibility",
    "status": "auxiliary_execution_eligible",
    "channel": 2,
    "eligible": true,
    "event_id": "ROOTLINE-EXEC-15C5FA8B81273E9D0DDFECF1B7878F50",
    "on_event": "controller_1_ch2_on",
    "device_id": "100204d497",
    "off_event": "controller_1_ch2_off",
    "stop_mode": "scheduled",
    "expires_at": "2026-11-20T13:08:12.889983+00:00",
    "single_use": true,
    "decision_at": "2026-11-20T13:03:12.889983+00:00",
    "device_type": "fertilizer_mixer",
    "execution_id": "ROOTLINE-AUX-EXECUTION-553987A35A632CAFABFCA9F4",
    "eligibility_id": "ROOTLINE-AUX-ELIGIBILITY-553987A35A632CAFABFCA9F4",
    "consumption_key": "ROOTLINE-AUX-CONSUME-6AF0309D24E8E1149DED591D",
    "plan_generation": "4AC9F6E0D72E5D27",
    "batch_generation": "ROOTLINE-BATCH-9F3FBBA19BC526F5B430A4DF",
    "contract_version": "rootline_auxiliary_eligibility.v2",
    "hardware_control": true,
    "command_authority": true,
    "eligibility_sha256": "553987a35a632cafabfca9f45a9484e36b83d8286c17b13f8e3725efc850a4c4",
    "auxiliary_device_id": "FERTILIZER-MIXER-CH2",
    "provider_output_state": "OFF",
    "device_contract_sha256": "ba0018a4688c2ad6be62f91a8056127b307cec3a294b92c509e4e553541e0b95",
    "maximum_duration_seconds": 600,
    "controller_safety_generation": "ba0018a4688c2ad6be62f91a8056127b307cec3a294b92c509e4e553541e0b95",
    "simultaneous_with_other_auxiliary": true
  },
  {
    "state": "claimed",
    "action": "claim_auxiliary_before_on",
    "job_id": null,
    "channel": 2,
    "zone_id": null,
    "event_id": "ROOTLINE-EXEC-6E29587BBD4871367516EE91E26CB666",
    "device_id": "100204d497",
    "stop_mode": "scheduled",
    "claimed_at": "2026-11-20T13:03:59.057858+00:00",
    "job_sha256": null,
    "device_type": "fertilizer_mixer",
    "on_attempts": 0,
    "execution_id": "ROOTLINE-AUX-EXECUTION-553987A35A632CAFABFCA9F4",
    "off_attempts": 0,
    "phase_number": null,
    "pulse_number": null,
    "eligibility_id": "ROOTLINE-AUX-ELIGIBILITY-553987A35A632CAFABFCA9F4",
    "consumption_key": "ROOTLINE-AUX-CONSUME-6AF0309D24E8E1149DED591D",
    "batch_generation": "ROOTLINE-BATCH-9F3FBBA19BC526F5B430A4DF",
    "segment_identity": null,
    "zone_execution_id": null,
    "eligibility_sha256": "553987a35a632cafabfca9f45a9484e36b83d8286c17b13f8e3725efc850a4c4",
    "auxiliary_device_id": "FERTILIZER-MIXER-CH2",
    "primary_stop_deadline": "2026-11-20T13:13:59.057858+00:00",
    "maximum_duration_seconds": 600,
    "provider_capacity_permit": "20c455b268ad4379a9db73ced5a9ac14"
  },
  {
    "action": "claim_auxiliary_off_attempt",
    "attempt": 1,
    "event_id": "ROOTLINE-EXEC-2E992F99CD7FD1AB1DDF0A97FCC10D5F",
    "execution_id": "ROOTLINE-AUX-EXECUTION-553987A35A632CAFABFCA9F4"
  },
  {
    "action": "record_auxiliary_off_outcome",
    "attempt": 1,
    "outcome": {
      "event": "controller_1_ch2_off",
      "status": "accepted",
      "provider_status": 200,
      "accepted_unambiguous": true
    },
    "event_id": "ROOTLINE-EXEC-F527E93086478AD4000CE7CD799A068A",
    "execution_id": "ROOTLINE-AUX-EXECUTION-553987A35A632CAFABFCA9F4"
  },
  {
    "state": "claimed_recovery_required",
    "action": "contain_auxiliary_device",
    "job_id": null,
    "reason": "restart_or_deadline_ambiguous",
    "channel": 2,
    "zone_id": null,
    "event_id": "ROOTLINE-EXEC-063F332E2B01546B11F081401CCCAC51",
    "device_id": "100204d497",
    "stop_mode": "scheduled",
    "claimed_at": "2026-11-20T13:03:59.057858+00:00",
    "job_sha256": null,
    "device_type": "fertilizer_mixer",
    "on_attempts": 0,
    "execution_id": "ROOTLINE-AUX-EXECUTION-553987A35A632CAFABFCA9F4",
    "off_attempts": 0,
    "phase_number": null,
    "pulse_number": null,
    "eligibility_id": "ROOTLINE-AUX-ELIGIBILITY-553987A35A632CAFABFCA9F4",
    "consumption_key": "ROOTLINE-AUX-CONSUME-6AF0309D24E8E1149DED591D",
    "batch_generation": "ROOTLINE-BATCH-9F3FBBA19BC526F5B430A4DF",
    "segment_identity": null,
    "shutdown_evidence": {
      "state": "OFF",
      "channel": 2,
      "device_id": "100204d497",
      "evidence_id": "09c3784658aff0caac6caef4746afaa2c641fae15419794870ce851d98553a93",
      "retrieved_at": "2026-11-20T13:05:02.287233+00:00",
      "authoritative": true
    },
    "shutdown_verified": true,
    "zone_execution_id": null,
    "eligibility_sha256": "553987a35a632cafabfca9f45a9484e36b83d8286c17b13f8e3725efc850a4c4",
    "auxiliary_device_id": "FERTILIZER-MIXER-CH2",
    "primary_stop_deadline": "2026-11-20T13:13:59.057858+00:00",
    "maximum_duration_seconds": 600,
    "provider_capacity_permit": "20c455b268ad4379a9db73ced5a9ac14"
  }
]''')


def unstarted_incident_history():
    return deepcopy(_NO_DISPATCH_HISTORY_553987)


def unstarted_incident_terminal(monkeypatch):
    import importlib
    store = importlib.import_module("modules.telemetry.rootline_irrigation_execution_store")
    history = unstarted_incident_history()
    claim = history[1]
    held = history[-1]
    started = datetime.fromisoformat(held["shutdown_evidence"]["retrieved_at"])+timedelta(seconds=1)
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None): return started+timedelta(seconds=2)
    monkeypatch.setattr(store, "datetime", Clock)
    receipt = {**claim, "state": "Aborted", "terminal_contract": "rootline_auxiliary_startup_abort.v2",
        "claim_event_id": claim["event_id"], "claim_sha256": store._event_digest(claim),
        "containment_event_id": held["event_id"], "containment_sha256": store._event_digest(held),
        "startup_preimage": "never_dispatched", "dispatch_count": 0,
        "startup_aborted_verified": True, "startup_unstarted_verified": True,
        "reason": "startup_never_dispatched", "provider_on_outcome": "Not dispatched",
        "shutdown_verified": True, "on_attempts": 0, "off_attempts": 1,
        "shutdown_evidence": {**held["shutdown_evidence"], "retrieved_at": (started+timedelta(seconds=.25)).isoformat()},
        "read_started_at": started.isoformat(), "aborted_at": (started+timedelta(seconds=.5)).isoformat(),
        "read_elapsed_seconds": .5, "objective_satisfied": False, "control_completed": False,
        "reservation_preserved": True, "on_authority": False}
    receipt = store._stored_event_body("record_auxiliary_startup_aborted", receipt,
        store._event_id("record_auxiliary_startup_aborted", receipt))
    return store, history, receipt


def test_actual_unstarted_incident_supports_distinct_abort_without_refunding_mixing(monkeypatch):
    from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
    store, history, terminal = unstarted_incident_terminal(monkeypatch)
    preimage = store._auxiliary_startup_abort_preimage(history, history[-1]["event_id"])
    assert preimage is not None and preimage[1] is None
    binding = store._auxiliary_abort_binding(preimage)
    assert binding["startup_preimage"] == "never_dispatched" and binding["dispatch_count"] == 0
    assert "dispatch_event_id" not in binding and "dispatch_sha256" not in binding
    assert store._verified_auxiliary_startup_abort(terminal, history)
    assert store._auxiliary_startup_terminal(history+[terminal]) == terminal
    accounting = mixing_daily_accounting(history+[terminal], now=store.datetime.now(timezone.utc))
    assert accounting["reserved_seconds"] == 600 and accounting["controller_completed_seconds"] == 0
    assert accounting["sessions"] == 1 and accounting["premix_verified"] is False


@pytest.mark.parametrize("missing", ["claim_auxiliary_before_on", "claim_auxiliary_off_attempt", "contain_auxiliary_device"])
def test_unstarted_incident_missing_required_history_cannot_retire(monkeypatch, missing):
    store, history, terminal = unstarted_incident_terminal(monkeypatch)
    history = [row for row in history if row["action"] != missing]
    assert not store._verified_auxiliary_startup_abort(terminal, history)


@pytest.mark.parametrize("action", ["claim_auxiliary_dispatch", "record_auxiliary_on_outcome", "mark_auxiliary_active",
    "record_auxiliary_exception", "record_auxiliary_completed", "unknown_action"])
def test_unstarted_incident_late_or_contradictory_history_invalidates_receipt(monkeypatch, action):
    store, history, terminal = unstarted_incident_terminal(monkeypatch)
    late = {**history[1], "on_outcome": {"accepted_unambiguous": True}}
    late = store._stored_event_body(action, late, store._event_id(action, late))
    assert not store._verified_auxiliary_startup_abort(terminal, history+[late])
    assert store._auxiliary_startup_terminal(history+[terminal, late]) is None


@pytest.mark.parametrize("field,value", [("terminal_contract", "rootline_auxiliary_startup_abort.v1"),
    ("terminal_contract", []),
    ("dispatch_event_id", "invented"), ("dispatch_sha256", "a"*64), ("dispatch_count", True),
    ("on_attempts", 1), ("on_attempts", False), ("startup_unstarted_verified", False),
    ("startup_preimage", "dispatch_outcome_unknown"), ("provider_on_outcome", "Unknown"),
    ("reservation_preserved", False), ("objective_satisfied", True), ("control_completed", True),
    ("on_authority", True), ("read_elapsed_seconds", 8.01), ("read_elapsed_seconds", -1)])
def test_unstarted_receipt_cannot_invent_dispatch_delivery_or_more_read_time(monkeypatch, field, value):
    store, history, terminal = unstarted_incident_terminal(monkeypatch)
    changed = {**terminal, field: value}
    changed["event_id"] = store._event_id("record_auxiliary_startup_aborted", changed)
    assert not store._verified_auxiliary_startup_abort(changed, history)


@pytest.mark.parametrize("field,value", [("authoritative", False), ("state", "ON"), ("channel", 1),
    ("channel", True), ("device_id", "other"), ("evidence_id", ""),
    ("retrieved_at", "2026-11-20T13:05:02+00:00"), ("retrieved_at", "2099-01-01T00:00:00+00:00")])
def test_unstarted_receipt_requires_bracketed_fresh_exact_off(monkeypatch, field, value):
    store, history, terminal = unstarted_incident_terminal(monkeypatch)
    changed = {**terminal, "shutdown_evidence": {**terminal["shutdown_evidence"], field: value}}
    changed["event_id"] = store._event_id("record_auxiliary_startup_aborted", changed)
    assert not store._verified_auxiliary_startup_abort(changed, history)


def test_affordable_auxiliary_start_keeps_normal_claim_and_on(monkeypatch):
    from types import SimpleNamespace
    from modules.telemetry import rootline_cycle_budget as cycle
    monkeypatch.setattr(cycle, "time", SimpleNamespace(monotonic=lambda: 100.0))
    store, transport = Store(), Transport()
    context = {"plan_generation": "PLAN-MIX-1", "verified_mixing_minutes_today": 20,
        "verified_mixing_sessions_today": 0, "reserved_mixing_seconds_today": 1200,
        "mixing_history_valid": True, "mixing_history_complete_through": NOW.isoformat(),
        "power_suitable": True}
    with cycle.cycle_budget(deadline=140.0):
        result = advance_auxiliary_execution(eligibility=mixer_eligibility(verified_mixing_minutes_today=20),
            store=store, transport=transport, revalidate=lambda _: context, now=NOW)
    assert result["status"] == "auxiliary_started"
    assert [call["state"] for call in transport.calls] == ["ON"]
    assert len(store.consumed) == 1



def test_existing_v1_unknown_dispatch_receipt_still_validates_unchanged(monkeypatch):
    store, history, unstarted = unstarted_incident_terminal(monkeypatch)
    claim = history[1]
    dispatch = store._stored_event_body("claim_auxiliary_dispatch", claim,
        store._event_id("claim_auxiliary_dispatch", claim))
    history.insert(2, dispatch)
    previous = {key: value for key, value in unstarted.items()
        if key not in {"startup_preimage", "dispatch_count", "startup_unstarted_verified"}}
    previous.update(terminal_contract="rootline_auxiliary_startup_abort.v1",
        reason="startup_dispatch_outcome_unknown", provider_on_outcome="Unknown", on_attempts=1,
        dispatch_event_id=dispatch["event_id"], dispatch_sha256=store._event_digest(dispatch))
    assert store._verified_auxiliary_startup_abort(previous, history)
    assert store._auxiliary_startup_terminal(history+[previous]) == previous
    assert not store._verified_auxiliary_startup_abort(unstarted, history)
    assert not store._verified_auxiliary_startup_abort(previous,
        [row for row in history if row["action"] != "claim_auxiliary_dispatch"])
