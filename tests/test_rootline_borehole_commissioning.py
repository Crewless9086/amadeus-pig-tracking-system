from datetime import datetime, timezone
from modules.telemetry.rootline_borehole_commissioning import (assess_borehole_commissioning_readiness,
  prepare_borehole_execution_plan, load_registered_borehole_baseline,
  build_borehole_runtime_eligibility, advance_borehole_execution)
from modules.telemetry.rootline_device_registry import get_device_contract
from modules.telemetry.rootline_execution_runtime import prepare_rootline_borehole_cycle
from modules.telemetry.rootline_irrigation_execution_store import _valid_borehole_eligibility

NOW=datetime(2026,8,20,11,0,tzinfo=timezone.utc)
def provider(**changes):
    value={"device_id":"1002851416","device_name":"Boorgat 1 Krag Toevoer","model":"MINIR4","online":True,
      "retrieved_at":NOW.isoformat(),"channels":[{"channel":1,"output_state":"OFF"}],"native_auto_off_enabled":True,
      "native_auto_off_seconds":14400,"power_restoration_state":"OFF","timers_enabled":False,"scenes_enabled":False,"interlock_enabled":False}
    value.update(changes); return value
def canonical(**changes):
    value={"current":True,"device_identity":"BOREHOLE-1-MINI-R4-CH1","device_id":"1002851416","channel":1,
      "commissioning_generation":1,"baseline_sha256":"a"*64,"maximum_routine_runtime_seconds":1800}
    value.update(changes); return value
def physical(**changes):
    value={key:True for key in ("supervised","pump_started","water_flow_observed","native_auto_off_observed","pump_stopped","water_flow_stopped","manual_off_and_isolation_proven")}
    value.update(changes); return value

def test_registry_binds_exact_owner_approved_connector_but_grants_no_authority():
    row=get_device_contract("BOREHOLE-1-MINI-R4-CH1")
    assert (row["device_id"],row["channel"],row["model"])==("1002851416",1,"MINIR4")
    assert row["commissioned"] is False
    assert (row["on_event"],row["off_event"],row["native_fail_stop_seconds"]) == (
        "borehole_1_on","borehole_1_off",14400)
def test_provider_ready_prepares_only_protected_supervised_commissioning():
    value=assess_borehole_commissioning_readiness(provider(),now=NOW)
    assert value["eligible_for_protected_commissioning"] is True
    assert value["blockers"]==["canonical_commissioned_baseline_absent"]
    assert value["hardware_commands"]==value["provider_control_calls"]==0
def test_ambiguity_fails_closed():
    value=assess_borehole_commissioning_readiness(provider(channels=[{"channel":1,"output_state":"Unknown"}],timers_enabled="Unknown"),now=NOW)
    assert "exact_provider_device_channel_off_identity_unproven" in value["blockers"] and value["eligible_for_protected_commissioning"] is False
def test_asserted_complete_baseline_still_requires_registered_validation_and_grants_nothing():
    value=assess_borehole_commissioning_readiness(provider(),canonical=canonical(),physical=physical(),now=NOW)
    assert value["commissioned"] is False and value["standing_authority"] is False and value["eligible_for_routine_execution"] is False
    assert "canonical_baseline_candidate_requires_registered_validator" in value["blockers"]
def test_execution_plan_binds_gates_receipts_off_and_recovery_without_commands():
    plan=prepare_borehole_execution_plan(need={"eligible":True},commissioned_baseline=canonical(),authority={"inside_standing_authority":True},
      provider={"authoritative":True,"state":"OFF"},interlocks={"dry_run_safe":True,"low_water_clear":True,"supply_pressure_safe":True,"full_tank_not_blocking":True},
      energy={"eligible":True},concurrency={"no_conflicting_material_load":True,"borehole_claim_available":True},requested_seconds=900,execution_id="BH-1",now=NOW)
    assert plan["eligible_for_coordinator"] is False and plan["commands_issued"]==0 and plan["on_retry_allowed"] is False
    assert "canonical_validator_and_coordinator_integration_absent" in plan["blockers"]
    assert "final_off_readback" in plan["provider_receipts_required"] and "load_active_claim" in plan["recovery"]["restart"]
def test_unknown_gate_and_oversize_runtime_block():
    plan=prepare_borehole_execution_plan(need={"eligible":True},commissioned_baseline=canonical(),authority={"inside_standing_authority":True},provider={"authoritative":True,"state":"OFF"},
      interlocks={"dry_run_safe":True,"low_water_clear":True,"supply_pressure_safe":"Unknown","full_tank_not_blocking":True},energy={"eligible":True},
      concurrency={"no_conflicting_material_load":True,"borehole_claim_available":True},requested_seconds=3600,execution_id="BH-2",now=NOW)
    assert set(plan["blockers"])=={"supply_pressure","bounded_runtime","canonical_validator_and_coordinator_integration_absent"}
    assert plan["commands_issued"]==0 and plan["eligible_for_coordinator"] is False

def test_registered_baseline_requires_exact_resolved_standing_active_record(monkeypatch):
    record={"provider":"ewelink","provider_account_binding":"ewelink_owner_account",
      "device_id":"1002851416","channel":1,"device_type":"pump","safe_state":"OFF",
      "physical_effect":"Borehole 1 pump power","commissioning_stage":"standing_active",
      "standing_authority":True,"independent_physical_identity_proven":True,
      "independent_fail_stop_proven":True,"maximum_runtime_seconds":1800,
      "native_fail_stop_seconds":1800,"authority_envelope":{"standing_authority_id":"BH-1"}}
    monkeypatch.setattr("modules.telemetry.rootline_borehole_commissioning.load_device_record",
      lambda *a,**k:{"device_record":record,"registry_generation":7,"evidence_digest":"b"*64})
    value=load_registered_borehole_baseline(connect_factory=lambda:None)
    assert value["registry_generation"]==7 and value["baseline_sha256"]=="b"*64
    record["channel"]=2
    assert load_registered_borehole_baseline(connect_factory=lambda:None) is None

def test_runtime_identity_is_deterministic_and_command_inert():
    args=dict(need={"eligible":True},baseline={**canonical(),"registry_generation":2},
      authority={"inside_standing_authority":True},provider={"authoritative":True,"state":"OFF"},
      interlocks={"dry_run_safe":True,"low_water_clear":True,"supply_pressure_safe":True,
        "full_tank_not_blocking":True},energy={"eligible":True},requested_seconds=900,now=NOW)
    first=build_borehole_runtime_eligibility(**args); second=build_borehole_runtime_eligibility(**args)
    assert first==second and first["eligible"] is True
    assert first["execution_id"].startswith("ROOTLINE-BOREHOLE-")
    assert first["command_authority"] is False and first["hardware_commands"]==0
    assert _valid_borehole_eligibility(first) is True
    assert _valid_borehole_eligibility({**first,"requested_seconds":901}) is False
    assert _valid_borehole_eligibility({**first,"eligible":False}) is False


class BoreholeStore:
    def __init__(self): self.active=None; self.events=[]
    def __call__(self, action, body):
        if action=="load_active_borehole": return self.active
        if action=="load_borehole_off_attempts": return []
        if action in {"claim_borehole_before_on","claim_borehole_off_attempt"}:
            if action=="claim_borehole_before_on": self.active=dict(body)
            self.events.append((action,body)); return {"success":True,"created":True}
        if action=="mark_borehole_active": self.active=dict(body)
        if action=="record_borehole_completed": self.active=None
        self.events.append((action,body)); return {"success":True,"created":True}


class BoreholeTransport:
    def __init__(self, on_accepted=True, on_readback="ON"):
        self.state="OFF"; self.commands=[]; self.on_accepted=on_accepted
        self.on_readback=on_readback
    def set_state(self,**kwargs):
        self.commands.append(kwargs)
        if kwargs["state"]=="ON":
            self.state=self.on_readback
            return {"accepted_unambiguous":self.on_accepted,
                "status":"accepted" if self.on_accepted else "provider_outcome_ambiguous"}
        self.state="OFF"; return {"accepted_unambiguous":True,"status":"accepted"}
    def read_output_state(self,**_kwargs):
        return {"authoritative":True,"state":self.state,
            "evidence_id":"PROVIDER-"+self.state}


def test_one_on_then_bounded_off_and_restart_recovery_use_same_execution():
    baseline={**canonical(maximum_routine_runtime_seconds=14400),"registry_generation":2}
    artifact=build_borehole_runtime_eligibility(need={"eligible":True},baseline=baseline,
      authority={"inside_standing_authority":True},provider={"authoritative":True,"state":"OFF"},
      interlocks={"dry_run_safe":True,"low_water_clear":True,"supply_pressure_safe":True,
        "full_tank_not_blocking":True},energy={"eligible":True},requested_seconds=60,now=NOW)
    store=BoreholeStore(); transport=BoreholeTransport()
    started=advance_borehole_execution(eligibility=artifact,store=store,
      transport=transport,now=NOW)
    assert started["status"]=="borehole_started"
    assert [row["state"] for row in transport.commands]==["ON"]
    completed=advance_borehole_execution(eligibility=artifact,store=store,
      transport=transport,now=NOW.replace(minute=2))
    assert completed["status"]=="borehole_completed"
    assert [row["state"] for row in transport.commands]==["ON","OFF"]
    assert completed["execution"]["operational_proof"]=="provider_app_on_to_off"


def test_ambiguous_or_unverified_start_is_off_contained_never_completed():
    baseline={**canonical(maximum_routine_runtime_seconds=14400),"registry_generation":2}
    artifact=build_borehole_runtime_eligibility(need={"eligible":True},baseline=baseline,
      authority={"inside_standing_authority":True},provider={"authoritative":True,"state":"OFF"},
      interlocks={"dry_run_safe":True,"low_water_clear":True,"supply_pressure_safe":True,
        "full_tank_not_blocking":True},energy={"eligible":True},requested_seconds=60,now=NOW)
    for transport in (BoreholeTransport(on_accepted=False),
                      BoreholeTransport(on_readback="Unknown")):
        store=BoreholeStore()
        result=advance_borehole_execution(eligibility=artifact,store=store,
          transport=transport,now=NOW)
        assert result["success"] is False
        assert result["status"]=="borehole_start_failure_contained"
        assert [row["state"] for row in transport.commands]==["ON","OFF"]
        assert not any(action=="record_borehole_completed" for action,_ in store.events)
        replay=advance_borehole_execution(eligibility=artifact,store=store,
          transport=transport,now=NOW.replace(minute=2))
        assert replay["success"] is False
        assert replay["status"]=="borehole_start_failure_contained"
        assert not any(action=="record_borehole_completed" for action,_ in store.events)

def test_existing_runtime_is_disabled_then_advances_with_injected_transport(monkeypatch):
    common=dict(need={"eligible":True},provider={"authoritative":True,"state":"OFF"},
      interlocks={"dry_run_safe":True,"low_water_clear":True,"supply_pressure_safe":True,
        "full_tank_not_blocking":True},energy={"eligible":True},requested_seconds=900,
      authority={"inside_standing_authority":True},connect_factory=lambda:None,now=NOW)
    assert prepare_rootline_borehole_cycle(**common,environ={})["status"]=="borehole_authority_disabled"
    baseline={**canonical(),"registry_generation":2}
    monkeypatch.setattr("modules.telemetry.rootline_borehole_commissioning.load_registered_borehole_baseline",
      lambda **kwargs:baseline)
    store=BoreholeStore(); transport=BoreholeTransport()
    result=prepare_rootline_borehole_cycle(**common,environ={"ROOTLINE_BOREHOLE_ENABLED":"true"},
      store=store,transport=transport)
    assert result["status"]=="borehole_started"
    assert [row["state"] for row in transport.commands]==["ON"]
