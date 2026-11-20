"""Startup recovery uses existing owned read admission; no live requests."""
from copy import deepcopy
from datetime import timedelta
import time
import pytest
from modules.telemetry import rootline_borehole_commissioning as borehole
from modules.telemetry import rootline_ewelink_request_budget as budget
from tests.test_rootline_continuous_borehole import eligibility, provider, NOW, Transport
from tests.test_rootline_borehole_commissioning import BoreholeStore
from tests.test_rootline_ewelink_request_budget import MemoryBudget, snapshot, fail


class PendingStart:
    def __init__(self, elapsed=1080, state="ON"):
        self.client = MemoryBudget(); self.client.backend.now = NOW
        self.execution = {**eligibility(), "state": "claimed_recovery_required",
            "claimed_at": NOW.isoformat(), "primary_stop_deadline": None,
            "native_fail_stop_deadline": None, "on_attempts": 0, "off_attempts": 0}
        permit = self.client.reserve_for_on(execution_id=self.execution["execution_id"],
            device_id="1002851416", channel=1, device_type="borehole_pump_power", region="eu")
        self.client.begin_on(execution_id=self.execution["execution_id"], permit=permit,
            device_id="1002851416", channel=1, claimed_at=NOW.isoformat(), continuous=True)
        self.execution["provider_capacity_permit"] = permit
        self.store = BoreholeStore(); self.store.active = deepcopy(self.execution)
        self.store.events.append(("record_borehole_on_outcome", {**self.execution,
            "on_attempts": 1, "on_outcome": {"status": "accepted", "accepted_unambiguous": True}}))
        self.client.backend.now = NOW+timedelta(seconds=elapsed)
        self.state = state; self.commands = []; self.reads = 0; self.events = []
        self.provider_calls = 0; self.sender = None
        self.client.dispatch = lambda **kw: self.client._dispatch(**kw, deadline=time.monotonic()+20)
    def clock(self): return self.client.backend.now
    def read_output_state(self, **kwargs):
        self.reads += 1; self.events.append("read")
        assert kwargs["device_id"] == "1002851416" and kwargs["channel"] == 1
        def send(timeout):
            self.provider_calls += 1
            return self.sender(timeout) if self.sender else {"ok": True}
        snapshot(self.client, device="1002851416", send=send)
        return provider(self.state, self.clock())
    def set_state(self, **kwargs):
        assert kwargs["state"] == "OFF", "recovery must never replay ON"
        self.events.append("OFF"); self.commands.append(kwargs); self.state = "OFF"
        return {"accepted_unambiguous": True, "status": "accepted"}
    def run(self, **kwargs):
        return borehole.advance_borehole_execution(eligibility={}, store=self.store,
            transport=self, now=self.clock(), clock=self.clock, **kwargs)


@pytest.mark.parametrize("elapsed", [31, 60, 1080, 1799])
def test_pending_start_observes_on_before_routine_due(elapsed):
    rig = PendingStart(elapsed)
    result = rig.run()
    assert result["status"] == "borehole_start_observed"
    assert result["hardware_commands"] == 0 and rig.commands == []
    assert rig.provider_calls == 3
    assert rig.store.active["state"] == "Active"
    assert rig.store.active["execution_id"] == rig.execution["execution_id"]
    assert rig.store.active["primary_stop_deadline"] is None
    assert not any(row["action"] == "optional_observation_suppressed" for row in rig.client.backend.events)


def test_claim_grace_remains_no_read_no_command():
    rig = PendingStart(20)
    assert rig.run()["status"] == "borehole_claim_in_progress"
    assert rig.reads == rig.provider_calls == 0 and not rig.commands


def test_proven_active_on_keeps_routine_pacing():
    rig = PendingStart(1080)
    rig.store.active.update(state="Active", provider_start_evidence=provider("ON", NOW))
    result = rig.run()
    assert result["status"] == "borehole_active" and result["supervision_evidence_pending"] is True
    assert rig.provider_calls == 0 and not rig.commands
    suppressed = [row for row in rig.client.backend.events if row["action"] == "optional_observation_suppressed"]
    assert len(suppressed) == 1
    assert suppressed[0]["detail"]["provider_attempted"] is False
    assert suppressed[0]["detail"]["next_read_at"] == (NOW+timedelta(seconds=1800)).isoformat()


def test_unknown_read_preserves_claim_without_on_retry_or_invented_start():
    rig = PendingStart(state="Unknown")
    result = rig.run()
    assert result["status"] == "borehole_start_observation_pending" and result["effects_unknown"] is True
    assert rig.provider_calls == 3 and not rig.commands
    assert rig.store.active == rig.execution
    assert not any(action == "mark_borehole_active" for action, _ in rig.store.events)


def test_failure_hold_is_not_bypassed_and_diagnostics_survive():
    rig = PendingStart(); rig.sender = fail(code=412)
    first = rig.run()
    assert first["status"] == "borehole_start_observation_pending"
    assert rig.provider_calls == 1 and not rig.commands
    units = sum(row["units"] for row in rig.client.backend.events)
    second = rig.run()
    assert second["status"] == "borehole_start_observation_pending"
    assert rig.provider_calls == 1 and sum(row["units"] for row in rig.client.backend.events) == units
    assert second.get("current_failure")


def test_exhausted_owned_reserve_is_not_expanded():
    rig = PendingStart()
    reserve = rig.client.backend.state["reserves"][rig.execution["execution_id"]]
    reserve.update(remaining=0, recovery_due_at=(rig.clock()+timedelta(hours=1)).isoformat())
    result = rig.run()
    assert result["status"] == "borehole_start_observation_pending"
    assert rig.provider_calls == 0 and not rig.commands
    assert rig.client.backend.state["reserves"][rig.execution["execution_id"]]["remaining"] == 0


def test_explicit_stop_precedes_start_confirmation_read():
    rig = PendingStart()
    result = rig.run(stop_for_energy=True, stop_reason="observed_rain")
    assert rig.events[0] == "OFF"
    assert 1 <= len(rig.commands) <= 3 and all(row["state"] == "OFF" for row in rig.commands)
    assert result["status"] == "borehole_start_failure_contained"
    assert result["execution"]["shutdown_verified"] is True


def test_observed_off_contains_start_without_completion_credit():
    rig = PendingStart(state="OFF")
    result = rig.run()
    assert result["status"] == "borehole_start_failure_contained"
    assert result["execution"]["shutdown_verified"] is True
    assert not any(action == "record_borehole_completed" for action, _ in rig.store.events)
    assert all(row["state"] == "OFF" for row in rig.commands)


def test_initial_accepted_on_immediately_calls_unpaced_read():
    store = BoreholeStore()
    class Observed(Transport):
        def __init__(self):
            super().__init__(on_readback="Unknown"); self.purposes = []
        def read_output_state(self, **kwargs):
            self.purposes.append(deepcopy(budget._optional_observation.get()))
            return super().read_output_state(**kwargs)
    transport = Observed()
    result = borehole.advance_borehole_execution(eligibility=eligibility(), store=store,
        transport=transport, now=NOW, clock=lambda: NOW)
    assert result["status"] == "borehole_start_observation_pending"
    assert [row["state"] for row in transport.commands] == ["ON"]
    assert transport.purposes == [None, None]
    outcome = next(body for action, body in store.events if action == "record_borehole_on_outcome")
    assert outcome["on_outcome"]["accepted_unambiguous"] is True
    assert not any(action == "mark_borehole_active" for action, _ in store.events)



def test_prior_unknown_request_keeps_charge_and_original_cooldown():
    rig = PendingStart()
    state = deepcopy(rig.client.backend.state)
    state["pending_attempt"] = {"id": "unresolved-original-read",
        "recorded_at": rig.clock().isoformat()}
    rig.client._append(state, action="request_attempt_reserved", attempt_units=1,
        detail={"attempt_id": "unresolved-original-read",
            "scope": budget.scope_digest(rig.client.environ, "eu"), "region": "eu",
            "execution_id": rig.execution["execution_id"], "endpoint": "/v2/family"})
    rig.client.backend.advance(30)
    pending = rig.run()
    assert pending["status"] == "borehole_start_observation_pending"
    assert rig.provider_calls == 0 and sum(row["units"] for row in rig.client.backend.events) == 1
    assert rig.client.backend.state["pending_attempt"]["id"] == "unresolved-original-read"
    rig.client.backend.advance(31)
    recovered = rig.run()
    assert recovered["status"] == "borehole_start_observed"
    assert rig.provider_calls == 3 and sum(row["units"] for row in rig.client.backend.events) == 4
    assert not any(row["action"] == "request_completed"
        and row["detail"].get("attempt_id") == "unresolved-original-read"
        for row in rig.client.backend.events)
    assert not rig.commands
