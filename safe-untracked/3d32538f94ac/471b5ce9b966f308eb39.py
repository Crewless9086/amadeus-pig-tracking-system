from datetime import datetime, timezone
from modules.telemetry.rootline_borehole_contract import build_borehole_contract, build_borehole_preview, classify_borehole_outcome

NOW=datetime(2026,8,12,tzinfo=timezone.utc)

def test_missing_private_bindings_fail_closed_without_exposing_values():
    value=build_borehole_contract({})
    assert value["configured"] is False and value["authority_enabled"] is False
    assert value["command_authority"] is False and value["hardware_control"] is False
    assert set(value["missing_protected_bindings"])=={"ROOTLINE_BOREHOLE1_DEVICE_ID","ROOTLINE_BOREHOLE1_IFTTT_ON_EVENT","ROOTLINE_BOREHOLE1_IFTTT_OFF_EVENT","ROOTLINE_BOREHOLE1_PROVIDER_ACCOUNT_ID"}

def test_runtime_binding_does_not_grant_authority_or_commissioning():
    value=build_borehole_contract({name:"bound" for name in ("ROOTLINE_BOREHOLE1_DEVICE_ID","ROOTLINE_BOREHOLE1_IFTTT_ON_EVENT","ROOTLINE_BOREHOLE1_IFTTT_OFF_EVENT","ROOTLINE_BOREHOLE1_PROVIDER_ACCOUNT_ID")})
    assert value["configured"] is True and value["authority_enabled"] is False
    assert value["independent_fail_stop"]==value["provider_readback"]=="Unknown"

def test_preview_requires_safety_evidence_and_never_dispatches():
    preview=build_borehole_preview(contract=build_borehole_contract({}),requested_action="ON",maximum_runtime_seconds=3600,evidence={},now=NOW)
    assert preview["visible_state"]=="Intervention"
    assert "independent_fail_stop_unproven" in preview["errors"]
    assert preview["command_authority"] is False and preview["hardware_control"] is False

def test_plug_on_never_proves_water_or_objective():
    value=classify_borehole_outcome(provider_state="ON")
    assert value["water_movement"]=="Unknown" and value["objective_satisfied"] is False
    assert value["shutdown_verified"] is False

def test_off_requires_supported_evidence_and_never_infers_objective():
    value=classify_borehole_outcome(provider_state="OFF",energy="motor_load_absent")
    assert value["shutdown_verified"] is True and value["lifecycle_state"]=="Completed"
    assert value["objective_satisfied"] is False
