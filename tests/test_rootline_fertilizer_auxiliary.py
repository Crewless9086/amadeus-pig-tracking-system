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
from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution

NOW=datetime(2026,8,9,8,0,tzinfo=timezone.utc)


def resign(row):
    row.pop("contract_sha256",None)
    row["contract_sha256"]=sha256(json.dumps(row,sort_keys=True,
        separators=(",",":"),default=str).encode()).hexdigest()


def safety(device="injection",**changes):
    channel=1 if device=="injection" else 2
    value={"authoritative":True,"response_digest":"READ-SAFETY-1",
        "device_id":"100204d497","channel":channel,"output_state":"OFF",
        "native_inching_enabled":True,"native_inching_seconds":120 if channel==1 else 300,
        "power_restoration_state":"OFF","schedules_enabled":False,"timers_enabled":False,
        "scenes_enabled":False,"interlock_enabled":False,
        "controller_safety_generation":"SAFETY-1",
        "physical_commissioning_generation":"COMMISSION-1","commissioned":True,
        "observed_at":NOW.isoformat()}
    value.update(changes);return value


def injection_context(**changes):
    value={"plan_generation":"PLAN-1","batch_generation":"BATCH-1",
        "active_zone_ids":["B12345"],"zone_execution_id":"ZONE-EXEC-1",
        "zone_start_evidence":{"evidence_id":"START-1","zone_execution_id":"ZONE-EXEC-1",
            "observed_at":(NOW-timedelta(seconds=600)).isoformat()},
        "zone_output_evidence":{"evidence_id":"OUTPUT-1","zone_execution_id":"ZONE-EXEC-1",
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
        "mixing_history_complete_through":NOW.isoformat(),"power_suitable":True}
    context.update(context_changes)
    return build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-MIXER-CH2"},
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


def test_mixer_preview_is_five_minutes_and_never_applies_configuration():
    preview=mixer_configuration_preview()
    assert preview["after"]["native_inching_seconds"]==300
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
        ({"mixer_active":True},"mixer_must_be_off"),
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


def test_mixing_five_minute_fail_stop_daily_cap_and_low_power_deferral():
    assert mixer_eligibility()["maximum_duration_seconds"]==300
    assert mixer_eligibility(verified_mixing_minutes_today=25)["eligible"]
    assert mixer_eligibility(verified_mixing_minutes_today=26)["status"]=="daily_mixing_cap_reached"
    assert mixer_eligibility(verified_mixing_sessions_today=6)["status"]=="daily_mixing_session_cap_reached"
    assert mixer_eligibility(power_suitable=False)["status"]=="low_power_mix_deferred"
    assert mixer_eligibility(injection_active=True)["status"]=="injection_must_be_off"


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
    batch=build_fertilizer_batch_lifecycle(now=NOW)
    incomplete=build_auxiliary_tasks(batch=batch,power={"battery_soc_pct":90,
        "solar_power_w":2000,"grid_power_w":0},now=NOW)
    assert incomplete["irrigation_auxiliary_tasks"][0]["decision"]=="Needs Data"
    assert incomplete["irrigation_auxiliary_tasks"][0]["reason"]=="mixing_history_incomplete"
    missing=build_auxiliary_tasks(batch=batch,power={},
        mixing_history_complete_through=NOW.isoformat(),now=NOW)
    assert missing["irrigation_auxiliary_tasks"][0]["decision"]=="Needs Data"
    low=build_auxiliary_tasks(batch=batch,power={"battery_soc_pct":20,
        "solar_power_w":0,"grid_power_w":0},
        mixing_history_complete_through=NOW.isoformat(),now=NOW)
    assert low["irrigation_zones"]==[] and low["zone_delivery_debt_changes"]==0
    tasks={row["device_type"]:row for row in low["irrigation_auxiliary_tasks"]}
    assert tasks["fertilizer_mixer"]["decision"]=="Run later"
    assert tasks["fertilizer_injection_valve"]["does_not_block_bc_irrigation"] is True
    capped=build_auxiliary_tasks(batch=batch,verified_mixing=[{
        "shutdown_verified":True,"verified_runtime_minutes":30,
        "completed_at":"2026-08-09T07:00:00+02:00"}],
        mixing_history_complete_through=NOW.isoformat(),now=NOW)
    mixer=next(row for row in capped["irrigation_auxiliary_tasks"]
               if row["device_type"]=="fertilizer_mixer")
    assert mixer["decision"]=="Completed" and mixer["planned_seconds"]==0


class Store:
    def __init__(self):
        self.active=None;self.rows=[];self.consumed=set();self.off=[];self.lock=Lock()
        self.contained=False
    def __call__(self,action,payload):
        if action=="load_active_auxiliary":return self.active
        if action=="load_auxiliary_containment":return {"contained":self.contained}
        if action=="load_auxiliary_off_attempts":return list(self.off)
        if action=="claim_auxiliary_before_on":
            with self.lock:
                key=payload["consumption_key"]
                if key in self.consumed:return {"success":True,"created":False}
                self.consumed.add(key);self.active=payload;self.rows.append((action,payload))
                return {"success":True,"created":True}
        if action=="claim_auxiliary_off_attempt":
            row={"attempt":payload["attempt"]};self.off.append(row);return {"created":True,"success":True}
        self.rows.append((action,payload))
        if action=="mark_auxiliary_active":self.active=payload
        if action in {"record_auxiliary_completed","contain_auxiliary_device"}:self.active=None
        return {"success":True,"created":True}


class Transport:
    def __init__(self,on=True,read="ON",off=True):self.on=on;self.read=read;self.off=off;self.calls=[]
    def set_state(self,**kwargs):
        self.calls.append(kwargs)
        accepted=self.on if kwargs["state"]=="ON" else self.off
        if kwargs["state"]=="OFF" and accepted:self.read="OFF"
        return {"accepted_unambiguous":accepted}
    def read_output_state(self,**_kwargs):return {"authoritative":True,"state":self.read,
        "evidence_id":"READ-1"}
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
    assert completed["status"]=="auxiliary_completed"
    assert duplicate["status"]=="auxiliary_claim_conflict"
    assert [row["state"] for row in transport.calls]==["ON","OFF"]
    assert completed["execution"]["nutrient_dose"]=="Unknown"
    assert completed["execution"]["verified_runtime_seconds"] is None
    assert completed["execution"]["maximum_runtime_seconds"]==120


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
    for current in (injection_context(zone_output_evidence={"evidence_id":"OUTPUT-2",
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
