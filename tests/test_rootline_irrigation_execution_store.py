from modules.telemetry.rootline_irrigation_execution_store import _event_id


def test_on_claim_identity_is_atomic_and_stable_across_replay():
    first = _event_id("claim_before_on", {"execution_id": "EXEC-1", "zone_id": "B12345"})
    replay = _event_id("claim_before_on", {"execution_id": "EXEC-1", "zone_id": "B12345",
                                            "untrusted_extra": "ignored"})
    other = _event_id("claim_before_on", {"execution_id": "EXEC-2", "zone_id": "B12345"})
    assert first == replay and first != other


def test_off_attempt_claims_are_unique_per_execution_and_attempt():
    identities = {_event_id("claim_off_attempt", {"execution_id": "EXEC-1", "attempt": n})
                  for n in (1, 2, 3)}
    assert len(identities) == 3
    assert _event_id("claim_off_attempt", {"execution_id": "EXEC-1", "attempt": 1}) in identities
