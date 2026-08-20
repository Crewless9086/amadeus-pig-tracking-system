from datetime import datetime, timezone
from modules.telemetry.rootline_borehole_commissioning import assess_borehole_commissioning_readiness, prepare_borehole_execution_plan
from modules.telemetry.rootline_device_registry import get_device_contract

NOW=datetime(2026,8,20,11,0,tzinfo=timezone.utc)
def provider(**changes):
    value={"device_id":"1002851416","device_name":"Boorgat 1 Krag Toevoer","model":"MINIR4","online":True,
      "retrieved_at":NOW.isoformat(),"channels":[{"channel":1,"output_state":"OFF"}],"native_auto_off_enabled":True,
      "native_auto_off_seconds":30,"power_restoration_state":"OFF","timers_enabled":False,"scenes_enabled":False,"interlock_enabled":False}
    value.update(changes); return value
def canonical(**changes):
    value={"current":True,"device_identity":"BOREHOLE-1-MINI-R4-CH1","device_id":"1002851416","channel":1,
      "commissioning_generation":1,"baseline_sha256":"a"*64,"maximum_routine_runtime_seconds":1800}
    value.update(changes); return value
def physical(**changes):
    value={key:True for key in ("supervised","pump_started","water_flow_observed","native_auto_off_observed","pump_stopped","water_flow_stopped","manual_off_and_isolation_proven")}
    value.update(changes); return value

def test_registry_is_identity_only_and_grants_no_authority():
    row=get_device_contract("BOREHOLE-1-MINI-R4-CH1")
    assert (row["device_id"],row["channel"],row["model"])==("1002851416",1,"MINIR4")
    assert row["commissioned"] is False and row["on_event"] is row["off_event"] is None
def test_provider_ready_prepares_only_protected_supervised_commissioning():
    value=assess_borehole_commissioning_readiness(provider(),now=NOW)
    assert value["eligible_for_protected_commissioning"] is True
    assert value["blockers"]==["canonical_commissioned_baseline_absent","supervised_physical_baseline_absent"]
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
