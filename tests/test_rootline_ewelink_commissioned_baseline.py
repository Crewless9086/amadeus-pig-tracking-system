from copy import deepcopy
from datetime import datetime, timezone

import pytest

from modules.telemetry.rootline_ewelink_commissioned_baseline import (
    commissioned_controller_baseline,
    commissioned_registered_device_baseline,
    validate_commissioned_baseline,
)
from modules.telemetry.rootline_ewelink_oauth import normalize_device_readback


NOW = datetime(2026, 8, 8, 18, 0, tzinfo=timezone.utc)


def packet(**changes):
    params = {"fwVersion": "3.8.2",
        "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
        "pulses": [{"outlet": i, "pulse": "on", "width": 3599000} for i in range(4)],
        "configure": [{"outlet": i, "startup": "off"} for i in range(4)],
        "timers": []}
    params.update(changes)
    return {"deviceid": "100204e9bc", "online": True, "params": params}


def normalize(device=None, baseline=None):
    return normalize_device_readback(device=device or packet(), status={"params": {}},
        retrieved_at=NOW, commissioned_baseline=baseline or commissioned_controller_baseline())


def test_exact_commissioned_baseline_closes_only_unexposed_control_paths():
    result = normalize()
    assert result["actuation_safety_complete"] is True
    assert result["actuation_configuration_safe"] is True
    assert result["control_path_evidence_source"] == "commissioned_configuration_baseline"
    assert result["interlock_enabled"] is False and result["scenes_enabled"] is False
    assert result["current_outputs_authoritative"] is True
    assert result["actuation_eligible"] is False


@pytest.mark.parametrize("field,value", [
    ("device_id", "wrong"), ("firmware", "3.8.3"), ("revoked", True),
    ("interlock_enabled", True), ("conflicting_scenes", [{"enabled": True}]),
    ("simultaneous_bc_authority", True),
])
def test_mismatched_revoked_or_conflicting_baseline_fails_closed(field, value):
    baseline = commissioned_controller_baseline()
    baseline[field] = value
    result = normalize(baseline=baseline)
    assert result["actuation_safety_complete"] is False
    assert "conflicting_control_paths" in result["safety_readback_missing"]


def test_detected_provider_control_path_drift_overrides_baseline():
    result = normalize(packet(interlock=1, scenes=[]))
    assert result["actuation_configuration_safe"] is False
    assert result["interlock_enabled"] is True


def test_conflicting_provider_scene_aliases_invalidate_baseline():
    result = normalize(packet(scenes=[], scene=[{"enabled": True}]))
    assert result["scene_evidence_conflict"] is True
    assert result["actuation_safety_complete"] is False
    assert result["scenes_enabled"] is None
    assert "conflicting_control_paths" in result["safety_readback_missing"]


def test_mixed_provider_and_baseline_provenance_is_per_fact():
    result = normalize(packet(interlock=0))
    assert result["interlock_evidence_source"] == "provider_readback"
    assert result["scenes_evidence_source"] == "commissioned_configuration_baseline"
    assert result["control_path_evidence_source"] == "mixed_provider_and_commissioned_baseline"


@pytest.mark.parametrize("changes", [
    {"fwVersion": "3.8.3"},
    {"timers": [{"enabled": True}]},
    {"switches": [{"outlet": 0, "switch": "on"}] +
        [{"outlet": i, "switch": "off"} for i in range(1, 4)]},
    {"pulses": [{"outlet": i, "pulse": "off", "width": 3599000} for i in range(4)]},
])
def test_detected_firmware_timer_output_or_fail_stop_drift_invalidates(changes):
    result = normalize(packet(**changes))
    assert result["actuation_configuration_safe"] is False


def test_baseline_identity_is_deterministic_and_exact():
    first = commissioned_controller_baseline()
    second = commissioned_controller_baseline()
    assert first == second
    validated = validate_commissioned_baseline(first, device_id="100204e9bc", firmware="3.8.2",
        observed_at=NOW)
    assert validated["baseline_id"] == first["baseline_id"]
    assert validated["baseline_fresh"] is True
    forged = deepcopy(first); forged["baseline_sha256"] = "0" * 64
    assert validate_commissioned_baseline(forged, device_id="100204e9bc", firmware="3.8.2",
        observed_at=NOW) is None


def test_fertilizer_configuration_baseline_is_exact_and_device_bound():
    observed = datetime(2026, 8, 10, 10, 0, tzinfo=timezone.utc)
    baseline = commissioned_registered_device_baseline("100204d497")
    assert baseline["device_id"] == "100204d497"
    assert baseline["fertilizer_commissioning_id"] == "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809"
    assert baseline["supervised_commissioning_channels"] == [2]
    assert baseline["accepted_owner_message_sha256"] == (
        "ae5e4b8aee29f4403f5c17c686c357ce395d5cbe0d3fff587d19c44658435dda")
    assert baseline["configuration_readback_sha256"] == (
        "88c8369bf859e941eea7b8cc639ce4d94f1160a01105abd4c8d945450b5f4859")
    assert validate_commissioned_baseline(
        baseline, device_id="100204d497", firmware="3.8.2", observed_at=observed,
    )["baseline_fresh"] is True
    assert validate_commissioned_baseline(
        baseline, device_id="100204e9bc", firmware="3.8.2", observed_at=observed,
    ) is None
    assert commissioned_registered_device_baseline("unknown") is None


def test_expired_commissioned_baseline_blocks_only_unobservable_control_paths():
    expired_at = datetime(2026, 8, 10, 16, 15, 14, tzinfo=timezone.utc)
    result = normalize_device_readback(device=packet(), status={"params": {}},
        retrieved_at=expired_at, commissioned_baseline=commissioned_controller_baseline())
    assert result["current_outputs_authoritative"] is True
    assert result["commissioned_baseline_fresh"] is False
    assert result["actuation_safety_complete"] is False
    assert "conflicting_control_paths" in result["safety_readback_missing"]
