"""Idle discovery uses real admission logic with synthetic persistence/provider."""
from datetime import timedelta
import pytest
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry.rootline_execution_runtime import _borehole_discovery_binding
from tests.test_rootline_ewelink_request_budget import Backend, MemoryBudget, snapshot, NOW


def discover(client, binding=None):
    with budget.optional_observation("borehole_unowned_discovery", binding=binding or {"eligible": False}):
        return snapshot(client, device="1002851416")


def test_crossworker_restart_and_jitter_share_due_slot():
    backend = Backend()
    discover(MemoryBudget(backend))
    for seconds in (59, 61, 121, 239, 299):
        backend.now = NOW + timedelta(seconds=seconds)
        with pytest.raises(budget.OptionalObservationDeferred):
            discover(MemoryBudget(backend))
    backend.now = NOW + timedelta(seconds=301)
    discover(MemoryBudget(backend))
    assert sum(row["units"] for row in backend.events) == 6


def test_semantic_change_and_return_transition_are_immediate_and_bounded():
    client = MemoryBudget()
    for binding in ({"eligible": False}, {"eligible": True}, {"eligible": False}):
        discover(client, binding)
    assert len(client.backend.state["optional_observations"]) == 1
    assert sum(row["units"] for row in client.backend.events) == 9


def test_retention_after_due_window_does_not_block_discovery():
    client = MemoryBudget()
    discover(client)
    client.backend.advance(86401)
    discover(MemoryBudget(client.backend))
    assert len(client.backend.state["optional_observations"]) == 1


def test_unwrapped_safety_and_postcommand_snapshot_bypass_discovery_gate():
    client = MemoryBudget()
    discover(client)
    snapshot(client, device="1002851416")
    with pytest.raises(budget.OptionalObservationDeferred):
        discover(client)


def test_binding_ignores_observation_churn_but_tracks_owner_and_protection():
    base = {"baseline_sha256": "a"*64, "registry_generation": 1, "stop_mode": "conditions"}
    conditions = {"start_eligible": False, "reason": "forecast_start_deferred",
        "stop_required": False, "opportunity_id": "one"}
    first = _borehole_discovery_binding(base, conditions, {}, {"eligible": True})
    assert first == _borehole_discovery_binding(base,
        {**conditions, "assessed_at": "new", "event_id": "new", "weather": {"observed_at": "new"}},
        {"observed_at": "new"}, {"eligible": True, "observed_at": "new"})
    for key, value in (("start_eligible", True), ("stop_required", True),
                       ("protection_safe", False), ("last_owned_execution_id", "owned"),
                       ("opportunity_id", "two")):
        assert first != _borehole_discovery_binding(base, {**conditions, key: value}, {}, {"eligible": True})
    assert first != _borehole_discovery_binding(base, conditions, {"manual_off_active": True}, {"eligible": True})
    assert first != _borehole_discovery_binding(base, conditions, {}, {"eligible": False})
