import pytest
from modules.telemetry.rootline_device_spine import manager_stage_projection, validate_device

def _device(**changes):
    row={"provider":"ewelink","provider_account_binding":"owner-vault","device_id":"D1",
      "channel":2,"physical_name":"Mixer","device_type":"independent_mixer_valve",
      "adapter_profile":"ewelink_relay","safe_state":"OFF","maximum_runtime_seconds":300,
      "native_fail_stop_seconds":300,"readback":"provider_state","physical_effect":"recirculation",
      "dependencies":["injection_off"],"manual_isolation":"valve","commissioning_stage":"registered",
      "standing_authority":False,"exact_blocker":"physical identity Unknown","next_safe_action":"supervised proof"}
    row.update(changes);return row

def test_projection_never_invents_physical_proof():
    view=manager_stage_projection(_device())
    assert view["working_now"] == "Unknown" and view["execution_authority"] is False
    assert view["physical_proof_invented"] is False
    assert view["exact_blocker"] == "physical identity Unknown"

def test_standing_authority_requires_terminal_stage():
    with pytest.raises(ValueError,match="standing_authority_unproven"):
        validate_device(_device(standing_authority=True))

def test_borehole_profile_is_stricter_than_valve():
    with pytest.raises(ValueError,match="strict_device_proof_missing"):
        validate_device(_device(device_type="pump",commissioning_stage="standing_active",
          standing_authority=True))
