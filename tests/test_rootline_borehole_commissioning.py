from datetime import datetime, timezone

from modules.telemetry.rootline_borehole_commissioning import assess_borehole_commissioning_readiness
from modules.telemetry.rootline_device_registry import get_device_contract, rootline_device_registry

NOW=datetime(2026,8,16,11,0,tzinfo=timezone.utc)


def test_reported_minir4_is_registered_without_command_or_commissioning_authority():
    row=get_device_contract("BOREHOLE-1-MINI-R4-CH1")
    assert row["device_id"]=="1002851416" and row["model"]=="MINIR4"
    assert row["commissioned"] is False and row["on_event"] is None and row["off_event"] is None
    assert row["authority_flag"]=="ROOTLINE_BOREHOLE_ENABLED"
    assert rootline_device_registry()[row["identity"]]["contract_sha256"]==row["contract_sha256"]


def test_current_provider_shape_holds_until_native_fail_off_and_conflicts_are_proven():
    value=assess_borehole_commissioning_readiness({"device_id":"1002851416",
        "device_name":"Boorgat 1 Krag Toevoer","model":"MINIR4","online":True,
        "retrieved_at":NOW.isoformat(),"channels":[{"channel":1,"output_state":"OFF"}],
        "native_auto_off_enabled":False,"native_auto_off_seconds":None,
        "power_restoration_state":"OFF","timers_enabled":"Unknown",
        "scenes_enabled":"Unknown","interlock_enabled":"Unknown"},now=NOW)
    assert value["status"]=="Hold" and value["eligible_for_card"] is False
    assert "native_fail_off_not_configured_or_verified" in value["blockers"]
    assert "conflicting_paths_not_proven_disabled" in value["blockers"]
    assert value["hardware_commands"]==value["provider_control_calls"]==0


def test_fully_proven_readback_prepares_only_a_bounded_physical_preview():
    value=assess_borehole_commissioning_readiness({"device_id":"1002851416",
        "device_name":"Boorgat 1 Krag Toevoer","model":"MINIR4","online":True,
        "retrieved_at":NOW.isoformat(),"channels":[{"channel":1,"output_state":"OFF"}],
        "native_auto_off_enabled":True,"native_auto_off_seconds":30,
        "power_restoration_state":"OFF","timers_enabled":False,
        "scenes_enabled":False,"interlock_enabled":False},now=NOW)
    assert value["status"]=="ready_for_protected_preview" and value["eligible_for_card"] is True
    assert value["maximum_test_seconds"]==30 and value["no_on_retry"] is True
    assert value["commissioned"] is False and value["authority_flag_enabled"] is False
    assert value["hardware_commands"]==value["provider_control_calls"]==0
