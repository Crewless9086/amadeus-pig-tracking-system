from tests.test_rootline_ifttt_transport import irrigation_output
from copy import deepcopy
from datetime import datetime, timedelta, timezone

import pytest

from modules.telemetry.rootline_auxiliary_management import (
    build_auxiliary_eligibility, build_fertilizer_batch_lifecycle, mixing_daily_accounting)
from modules.telemetry.rootline_energy_policy import managed_energy_decision, eskom_connector_readiness
from modules.telemetry.rootline_execution_runtime import _refresh_active_irrigation_readback
from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context

NOW = datetime(2026, 10, 29, 8, tzinfo=timezone.utc)


def power(**changes):
    return {"observed_at":NOW.isoformat(), "battery_soc_pct":80, "solar_power_w":3000,
        "load_power_w":1200, "grid_power_w":0, "battery_power_w":-1800,
        "battery_state":"charging", **changes}


@pytest.mark.parametrize("soc,grid,solar,battery,state", [
    (29,0,0,500,"ON"),(30,0,0,500,"ON"),(31,0,0,500,"UNCHANGED"),
    (34,0,3000,-1800,"UNCHANGED"),(35,0,3000,-1800,"OFF"),
    (35,1800,0,-1800,"UNCHANGED"),(40,1800,500,-1800,"UNCHANGED")])
def test_owner_grid_hysteresis_requires_actual_solar_charging(soc,grid,solar,battery,state):
    result=managed_energy_decision(power(battery_soc_pct=soc,grid_power_w=grid,
        solar_power_w=solar,battery_power_w=battery),now=NOW)
    assert result["eskom_requested_state"]==state
    assert result["hardware_commands"]==0


def test_stale_power_does_not_request_grid_off_or_enable_material_loads():
    result=managed_energy_decision(power(observed_at=(NOW-timedelta(minutes=16)).isoformat()),now=NOW)
    assert result["eskom_requested_state"]=="UNCHANGED"
    assert not result["mixing_eligible"] and not result["borehole_eligible"]
    assert not eskom_connector_readiness({})["enabled"]


def test_grid_watts_do_not_make_discretionary_mixing_safe():
    assert not managed_energy_decision(power(battery_soc_pct=35,solar_power_w=0,
        grid_power_w=5000),now=NOW)["mixing_eligible"]


def mixer_row(identity="MIX-1", **changes):
    return {"action":"claim_auxiliary_before_on", "execution_id":identity,
        "device_type":"fertilizer_mixer", "auxiliary_device_id":"FERTILIZER-MIXER-CH2",
        "claimed_at":NOW.isoformat(), "maximum_duration_seconds":600, **changes}


def test_mixer_budget_counts_reservations_once_and_never_counts_injector():
    row=mixer_row(); done={**row,"action":"record_auxiliary_completed",
        "control_completed":True,"shutdown_verified":True,"accounted_mixing_seconds":600}
    result=mixing_daily_accounting([row,deepcopy(row),done,
        {**row,"execution_id":"INJECT","device_type":"fertilizer_injection_valve"}],now=NOW)
    assert result["reserved_seconds"]==result["controller_completed_seconds"]==600
    assert result["sessions"]==1


def test_unknown_or_failed_mixing_keeps_budget_without_claiming_time():
    row=mixer_row()
    result=mixing_daily_accounting([row,{**row,"action":"contain_auxiliary_device",
        "shutdown_verified":False}],now=NOW)
    assert result["reserved_seconds"]==600 and result["controller_completed_seconds"]==0
    assert not mixing_daily_accounting([{"execution_id":"OLD","device_type":"fertilizer_mixer",
        "completed_at":NOW.isoformat(),"verified_runtime_seconds":None}],now=NOW)["history_valid"]


def test_mixer_reservation_crossing_sast_midnight_charges_both_days():
    row=mixer_row(claimed_at="2026-10-28T21:55:00+00:00")
    assert mixing_daily_accounting([row],now=NOW)["reserved_seconds"]==300
    assert mixing_daily_accounting([row],now=NOW-timedelta(days=1))["reserved_seconds"]==300


@pytest.mark.parametrize("claimed,stopped,expected_reserved,expected_premix",[
    ("2026-10-28T23:30:00+02:00","2026-10-28T23:40:00+02:00",0,False),
    ("2026-10-28T23:50:00+02:00","2026-10-29T00:00:00+02:00",0,False),
    ("2026-10-28T23:55:00+02:00","2026-10-29T00:05:00+02:00",300,True),
    ("2026-10-29T00:00:00+02:00","2026-10-29T00:10:00+02:00",600,True),
    ("2026-10-29T00:00:00+02:00","2026-10-29T00:11:00+02:00",600,False)])
def test_premix_requires_current_sast_day_work_not_rolling_24_hours(
        claimed,stopped,expected_reserved,expected_premix):
    now=datetime.fromisoformat("2026-10-29T00:10:00+02:00")
    row=mixer_row(claimed_at=claimed,batch_generation="BATCH-CURRENT")
    done={**row,"action":"record_auxiliary_completed","control_completed":True,
        "shutdown_verified":True,"accounted_mixing_seconds":600,"completed_at":stopped}
    batch={"batch_generation":"BATCH-CURRENT","mixed_after":"2026-10-28T10:00:00+02:00"}
    result=mixing_daily_accounting([row,done],now=now,batch=batch)
    assert result["reserved_seconds"]==result["controller_completed_seconds"]==expected_reserved
    assert result["premix_verified"] is expected_premix
    assert not mixing_daily_accounting([row,done],now=now,
        batch={**batch,"batch_generation":"OTHER-BATCH"})["premix_verified"]
    assert not mixing_daily_accounting([row,done],now=now,
        batch={**batch,"mixed_after":"2026-10-29T00:11:00+02:00"})["premix_verified"]


def test_batch_identity_does_not_change_when_mixing_finishes_and_unsafe_wins():
    observation={"event_type":"fertilizer_batch_prepared","observed_at":NOW.isoformat()}
    first=build_fertilizer_batch_lifecycle(observations=[observation],now=NOW)
    later=build_fertilizer_batch_lifecycle(observations=[observation],now=NOW+timedelta(minutes=10),
        executions=[{**mixer_row(),"shutdown_verified":True,"completed_at":(NOW+timedelta(minutes=10)).isoformat()}])
    assert first["batch_generation"]==later["batch_generation"]
    blocked=build_fertilizer_batch_lifecycle(observations=[observation,
        {"event_type":"fertilizer_batch_empty","observed_at":(NOW+timedelta(minutes=1)).isoformat()}],now=NOW+timedelta(minutes=2))
    assert blocked["state"]=="batch_unavailable"


class Store:
    def __init__(self): self.active=None; self.rows=[]; self.claims=set(); self.off=set()
    def __call__(self,action,payload):
        if action=="load_active": return active_zone()
        if action=="load_active_auxiliaries": return [self.active] if self.active else []
        if action=="load_active_auxiliary": return self.active
        if action=="load_active_borehole": return None
        if action=="load_auxiliary_containment": return None
        if action=="load_auxiliary_physical_outcome": return None
        if action=="load_auxiliary_off_attempts": return [{"attempt":n} for identity,n in self.off if identity==payload]
        if action=="dispatch_auxiliary_on_edge": return payload["dispatch"]()
        if action=="claim_auxiliary_before_on":
            if payload["consumption_key"] in self.claims: return {"success":True,"created":False}
            self.claims.add(payload["consumption_key"]);self.active=payload
        if action=="claim_auxiliary_off_attempt": self.off.add((payload["execution_id"],payload["attempt"]))
        if action=="mark_auxiliary_active": self.active=payload
        if action in {"record_auxiliary_completed","record_auxiliary_control_pulse_stopped"}: self.active=None
        self.rows.append({"action":action,**deepcopy(payload)})
        return {"success":True,"created":True}


class Transport:
    def __init__(self): self.now=NOW;self.calls=[];self.states={1:"OFF",2:"OFF"}
    def read_safety_configuration(self,*,device_id,channel):
        return {"authoritative":True,"response_digest":"FAKE-SAFE", "device_id":device_id,
            "channel":channel,"output_state":self.states[channel],"native_inching_enabled":True,
            "native_inching_seconds":120 if channel==1 else 1800,"power_restoration_state":"OFF",
            "schedules_enabled":False,"timers_enabled":False,"scenes_enabled":False,"interlock_enabled":False,
            "controller_safety_generation":"SAFE","physical_commissioning_generation":"BOUND",
            "commissioned":True,"observed_at":self.now.isoformat()}
    def read_output_state(self,*,device_id,channel):
        if device_id=="100204e9bc":
            return irrigation_output(self.now,channel=channel)
        return {"authoritative":True,"state":"ON" if device_id=="100204e9bc" else self.states[channel],
            "device_id":device_id,"channel":channel,"evidence_id":"FAKE-"+self.now.isoformat(),
            "retrieved_at":self.now.isoformat()}
    def set_state(self,**kwargs):
        self.calls.append(kwargs);self.states[kwargs["channel"]]=kwargs["state"]
        return {"accepted_unambiguous":True}


def active_zone():
    return {"state":"Active","action":"mark_active","execution_id":"ZONE-1",
        "zone_id":"B12345","device_id":"100204e9bc","channel":1,
        "evidence_generation":"PLAN-1","job_id":"ROOTLINE-IRRIGATION-JOB-"+"A"*24,
        "job_sha256":"a"*64,"segment_identity":"ROOTLINE-JOB-SEGMENT-"+"B"*24,
        "primary_stop_deadline":(NOW+timedelta(seconds=3599)).isoformat(),
        "start_evidence":{"authoritative":True,"state":"ON","evidence_id":"START",
            "retrieved_at":NOW.isoformat(),"device_id":"100204e9bc","channel":1}}


def test_real_controller_pulses_advance_twice_without_flow_sensor_and_preserve_flush_window():
    store=Store(); transport=Transport(); active=active_zone()
    for seconds,expected_pulse in [(600,1),(1320,2)]:
        transport.now=NOW+timedelta(seconds=seconds)
        context=_active_irrigation_context(active,store.rows,True,"BATCH-1")
        context["premix_verified"]=True
        context["fertilizer_history_complete_through"]=transport.now.isoformat()
        context=_refresh_active_irrigation_readback({"active_irrigation_context":context},transport,transport.now)["active_irrigation_context"]
        artifact=build_auxiliary_eligibility(task={"auxiliary_device_id":"FERTILIZER-INJECTION-CH1"},
            safety=transport.read_safety_configuration(device_id="100204d497",channel=1),context=context,
            flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED":True},now=transport.now)
        assert artifact["eligible"] and artifact["pulse_number"]==expected_pulse
        started=advance_auxiliary_execution(eligibility=artifact,store=store,transport=transport,
            revalidate=lambda _:context,now=transport.now,clock=lambda:transport.now)
        assert started["status"]=="auxiliary_started"
        transport.now+=timedelta(seconds=120)
        stopped=advance_auxiliary_execution(eligibility={},store=store,transport=transport,now=transport.now,clock=lambda:transport.now)
        assert stopped["status"]=="auxiliary_injection_control_completed"
        assert stopped["physical_delivery_verified"] is False
    context=_active_irrigation_context(active,store.rows,True,"BATCH-1")
    assert context["completed_pulses"]==2
    assert context["prior_pulse_shutdown_evidence"]["shutdown_verified"] is True
    assert datetime.fromisoformat(active["primary_stop_deadline"])-transport.now>=timedelta(seconds=600)
    assert [row["state"] for row in transport.calls]==["ON","OFF","ON","OFF"]
    from modules.telemetry.rootline_auxiliary_management import fertilizer_control_progress
    from modules.telemetry.rootline_irrigation_execution_store import _event_id
    assert not fertilizer_control_progress(context,now=transport.now)["completed"]
    transport.now+=timedelta(seconds=600)
    context=_refresh_active_irrigation_readback({"active_irrigation_context":context},transport,transport.now)["active_irrigation_context"]
    progress=fertilizer_control_progress(context,now=transport.now)
    assert progress["completed"] and not progress["physical_flow_verified"]
    later={**progress,"flush_control_evidence":{**progress["flush_control_evidence"],"observed_at":"later"}}
    assert _event_id("record_fertilizer_sequence_completed",progress)==_event_id("record_fertilizer_sequence_completed",later)


def test_conflicting_provider_timestamps_cannot_unlock_injection():
    active=active_zone();active["start_evidence"]["observed_at"]=(NOW+timedelta(seconds=1)).isoformat()
    assert _active_irrigation_context(active,[],True,"BATCH-1") is None


def test_active_mixer_is_stopped_on_low_power_even_when_new_starts_disabled():
    store=Store();transport=Transport()
    store.active={**mixer_row(),"device_id":"100204d497","channel":2,"state":"Active",
        "primary_stop_deadline":(NOW+timedelta(seconds=600)).isoformat(),"on_attempts":1,
        "start_evidence":{"authoritative":True,"state":"ON","retrieved_at":NOW.isoformat()}}
    transport.states[2]="ON";transport.now=NOW+timedelta(seconds=60)
    result=run_rootline_managed_device_cycle(evidence={},transport=transport,store=store,
        now=transport.now,clock=lambda:transport.now,allow_new_starts=False,energy_reader=lambda:{"mixing_eligible":False})
    assert result["status"]=="mixing_paused_for_energy"
    assert [row["state"] for row in transport.calls]==["OFF"]
    assert mixing_daily_accounting(store.rows,now=transport.now)["reserved_seconds"]==600


def test_a_and_e_mapping_is_ready_but_cannot_inherit_bc_authority():
    from modules.telemetry.rootline_device_registry import get_device_contract, commissioned_irrigation_contract
    for zone,channel in [("A12345",4),("E12345",3)]:
        row=get_device_contract(zone)
        assert row["channel"]==channel and not row["plumbing_ready"] and not row["commissioned"]
        with pytest.raises(ValueError): commissioned_irrigation_contract(zone)


def test_installed_protections_are_explicit_and_unsafe_facts_override():
    from modules.telemetry.rootline_borehole_commissioning import borehole_protection_assessment, DEVICE_KEY
    baseline={"current":True,"device_key":DEVICE_KEY,"installed_protection_profile":{
        "device_key":DEVICE_KEY,"canonical_reference_resolved":True,
        "reference":{"observed_at":NOW.isoformat()},"manual_isolation_proven":True,
        "pump_controller_internal_protection":True,"covered_risks":["dry_run","low_water","supply_pressure"],
        "full_tank_cutoff_installed":True}}
    assert all(borehole_protection_assessment(baseline,{},now=NOW).values())
    assert all(borehole_protection_assessment(baseline,{"full_tank_not_blocking":False},now=NOW).values())
    assert not borehole_protection_assessment(baseline,{"dry_run_safe":False},now=NOW)["dry_run"]
    assert not any(borehole_protection_assessment(baseline,{"manual_isolation_active":True},now=NOW).values())
    baseline["installed_protection_profile"]["canonical_reference_resolved"]=False
    assert not any(borehole_protection_assessment(baseline,{},now=NOW).values())


def test_latest_faults_do_not_expire_or_clear_by_omission_or_out_of_order_arrival():
    from modules.telemetry.rootline_water_energy_plan import _project_borehole_interlocks
    old=(NOW-timedelta(hours=2)).isoformat();new=(NOW-timedelta(hours=1)).isoformat()
    rows=[{"observed_at":new,"manual_isolation_active":True,"evidence_id":"ISOLATED"},
        {"observed_at":NOW.isoformat(),"dry_run_safe":True,"evidence_id":"OTHER"},
        {"observed_at":old,"manual_isolation_active":False,"evidence_id":"OLDER-CLEAR"}]
    assert _project_borehole_interlocks(rows,NOW)["manual_isolation_active"] is True
    rows.append({"observed_at":NOW.isoformat(),"manual_isolation_active":False,"evidence_id":"EXPLICIT-CLEAR"})
    assert _project_borehole_interlocks(rows,NOW)["manual_isolation_active"] is False


def test_active_mixer_uses_existing_load_not_double_added_start_allowance():
    result=managed_energy_decision(power(battery_soc_pct=60,solar_power_w=2000,load_power_w=1800),now=NOW)
    assert result["mixing_continue_eligible"] and not result["mixing_eligible"]


def test_borehole_energy_shutdown_precedes_its_four_hour_deadline():
    from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
    active={"execution_id":"BOREHOLE-FAKE","state":"Active","primary_stop_deadline":
        (NOW+timedelta(hours=3)).isoformat(),"provider_start_evidence":{"authoritative":True,"state":"ON"}}
    rows=[]
    def store(action,payload):
        if action=="load_active_borehole":return active
        if action=="load_borehole_off_attempts":return []
        rows.append((action,payload));return {"success":True,"created":True}
    transport=Transport()
    result=advance_borehole_execution(eligibility={},store=store,transport=transport,now=NOW,stop_for_energy=True)
    assert result["status"]=="borehole_completed" and [row["state"] for row in transport.calls]==["OFF"]
    assert result["execution"]["energy_stop"] and "physical_flow_verified" not in result["execution"]
