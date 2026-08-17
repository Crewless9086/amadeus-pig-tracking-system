import pytest
from modules.telemetry.rootline_device_spine import (CanonicalAuthorityResolver,
    manager_stage_projection, validate_device)

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
    with pytest.raises(ValueError,match="standing_authority_evidence_missing"):
        validate_device(_device(device_type="pump",commissioning_stage="standing_active",
          standing_authority=True))

def _evidence():
    return {key:{"source":"canonical","evidence_id":"proof:"+key,
      "observed_at":"2026-08-17T10:00:00+02:00","sha256":"a"*64} for key in ("provider_discovered","readback_proven",
      "bounded_actuation_ready","physical_identity_proven","fail_stop_proven",
      "replay_proven","operational_dependencies_proven","supervised")}

def _resolver():
    value=CanonicalAuthorityResolver(lambda:None)
    value.evidence=lambda ref:{**ref,"current":True}
    value.authority=lambda ref:{**ref,"active":True}
    return value

def test_ordinary_relay_standing_authority_requires_complete_evidence_and_envelope():
    with pytest.raises(ValueError,match="standing_authority_evidence_missing"):
        validate_device(_device(device_type="generic_relay_output",
          commissioning_stage="standing_active",standing_authority=True))
    assert validate_device(_device(device_type="generic_relay_output",
      commissioning_stage="standing_active",standing_authority=True,
      commissioning_evidence=_evidence(),authority_envelope={
        "standing_authority_id":"ROOTLINE-RELAY-1","version":"1","issuer":"owner_policy",
        "policy_sha256":"b"*64,"revoked":False}),
      resolver=_resolver())

def test_strict_device_requires_independent_physical_and_fail_stop_proof():
    row=_device(device_type="pump",commissioning_stage="standing_active",standing_authority=True,
      commissioning_evidence=_evidence(),authority_envelope={
        "standing_authority_id":"ROOTLINE-PUMP-1","version":"1","issuer":"owner_policy",
        "policy_sha256":"b"*64,"revoked":False})
    with pytest.raises(ValueError,match="strict_device_proof_missing"):
        validate_device(row,resolver=_resolver())

def test_standing_authority_cannot_be_self_asserted_without_canonical_resolvers():
    row=_device(device_type="generic_relay_output",commissioning_stage="standing_active",
      standing_authority=True,commissioning_evidence=_evidence(),authority_envelope={
        "standing_authority_id":"ROOTLINE-RELAY-1","version":"1","issuer":"owner_policy",
        "policy_sha256":"b"*64,"revoked":False})
    with pytest.raises(ValueError,match="evidence_unresolved"):
        validate_device(row)

def test_profile_safe_state_and_runtime_bounds_are_enforced():
    with pytest.raises(ValueError,match="safe_state_mismatch"):
        validate_device(_device(safe_state="ON"))
    with pytest.raises(ValueError,match="fail_stop_bound_invalid"):
        validate_device(_device(native_fail_stop_seconds=301))
