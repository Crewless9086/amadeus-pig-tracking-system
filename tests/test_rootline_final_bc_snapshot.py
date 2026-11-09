"""Same-final-snapshot admission retains the real planner and coordinator."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta

import pytest

from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_irrigation_coordinator as coordinator
from modules.telemetry import rootline_ewelink_readback as provider
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport, NativeBCFinalCheck
from modules.telemetry.rootline_ewelink_request_budget import bind_execution_transport
from tests.test_rootline_execution_runtime import NOW, Store, controller, evidence, plan


class Journey:
    def __init__(self, monkeypatch, zone="B12345"):
        self.mp, self.zone = monkeypatch, zone
        self.channel = 1 if zone == "B12345" else 2
        self.source = {"ROOTLINE_AUTONOMOUS_BC_ENABLED": "true", "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc"}
        self.tokens, self.store = object(), Store()
        self.calls, self.reads, self.capacities = [], [], []
        self.final_change = lambda value: value
        self.evidence_change = lambda value: value
        self.check_change = lambda value: value
        self.authority_calls = 0
        self.revoke = self.authority_error = False
        self.now = NOW
        self.transport = RootlineIFTTTTransport(token_store=self.tokens, environ=self.source,
            readback=provider.read_current_device)
        def read(**kwargs):
            value = controller("READ-" + str(len(self.reads) + 1))
            value["retrieved_at"] = value["trusted_receipt_at"]
            value["current_outputs_authoritative"] = True
            self.reads.append(deepcopy(value))
            if len(self.reads) == 2:
                self.final_change(value)
            if self.calls:
                value["channels"][self.channel-1]["output_state"] = "ON"
            return value
        monkeypatch.setattr(provider, "_read_bound_device", read)
        monkeypatch.setattr(runtime, "build_water_energy_plan", lambda *_a, **_k: self.plan())
        def capacity(_transport, execution):
            self.capacities.append(execution)
            return True
        monkeypatch.setattr(coordinator, "prepare_execution_capacity", capacity)
        def send(**kwargs):
            self.calls.append(kwargs)
            return {"accepted_unambiguous": True}
        monkeypatch.setattr(self.transport, "set_state", send)
        original = coordinator._valid_native_final_check
        monkeypatch.setattr(coordinator, "_valid_native_final_check",
            lambda final, *args: original(self.check_change(final), *args))

    def plan(self):
        value = plan()
        row = value["candidate_tasks"][0]
        row.update(task_id="irrigation_"+self.zone, zone_id=self.zone)
        return value

    def loader(self, **kwargs):
        value = evidence()
        value["irrigation"]["zones"][0]["zone_id"] = self.zone
        if self.reads:
            self.evidence_change(value)
        return value, "2026-08-08", NOW

    def authority(self, *_):
        self.authority_calls += 1
        if self.authority_calls > 1 and self.authority_error:
            raise RuntimeError("authority unavailable")
        return not (self.authority_calls > 1 and self.revoke)

    def run(self, **changes):
        args = dict(notify=lambda *_: {"success": True, "provider_delivery_confirmed": True,
                    "provider_message_id": "MSG"},
            environ=self.source, now=NOW, store=self.store, token_store=self.tokens,
            transport=self.transport, evidence_loader=self.loader,
            readback=provider.read_current_device, clock=lambda: self.now,
            owner_user_id="42", chat_id="42", observation_store=lambda *_: {"success": True},
            authority_checker=self.authority)
        args.update(changes)
        return runtime.run_rootline_execution_cycle(**args)

    def assert_no_claim(self):
        assert not self.calls and not self.capacities
        assert not any(action == "claim_before_on" for action, _ in self.store.rows)


@pytest.mark.parametrize("zone", ["B12345", "C12345"])
def test_native_final_snapshot_two_preclaim_reads_and_post_on_readback(monkeypatch, zone):
    j = Journey(monkeypatch, zone)
    result = j.run()
    assert result["status"] == "segment_started"
    assert len(j.reads) == 3  # Initial, fresh final, then authoritative ON readback.
    assert len(j.calls) == 1 and j.calls[0]["state"] == "ON"
    assert j.store.active["state"] == "Active"
    assert j.authority_calls == 2


@pytest.mark.parametrize("change", [
    lambda s: s.update(device_id="wrong"),
    lambda s: s.update(channels=None),
    lambda s: s.update(channels={}),
    lambda s: s.update(channels=[None]*4),
    lambda s: s["channels"][0].update(channel=True),
    lambda s: s["channels"][0].update(channel=1.0),
    lambda s: s["channels"].pop(),
    lambda s: s["channels"][1].update(channel=1),
    lambda s: s.update(provider_control_calls=False),
    lambda s: s.update(provider_control_calls=0.0),
    lambda s: s.update(provider_control_calls=1),
    lambda s: s.update(actuation_configuration_safe=False),
    lambda s: s.update(timers_enabled=True),
    lambda s: s.update(interlock_enabled=True),
    lambda s: s.update(scenes_enabled=True),
    lambda s: s["channels"][3].update(output_state="ON"),
    lambda s: s["channels"][0].update(native_auto_off_seconds=3600),
    lambda s: s.update(response_digest=""),
    lambda s: s.update(retrieved_at=(NOW-timedelta(minutes=6)).isoformat()),
    lambda s: s.update(retrieved_at=(NOW+timedelta(seconds=1)).isoformat()),
    lambda s: s.update(retrieved_at=NOW.replace(tzinfo=None).isoformat()),
    lambda s: s.pop("retrieved_at"),
])
def test_changed_final_controller_rejected_before_capacity_claim_on(monkeypatch, change):
    j = Journey(monkeypatch)
    j.final_change = change
    j.run()
    j.assert_no_claim()
    assert len(j.reads) == 2


@pytest.mark.parametrize("case", ["rain", "revoked", "authority_error", "callback_error", "clock_aged"])
def test_final_evidence_authority_and_clock_fail_closed(monkeypatch, case):
    j = Journey(monkeypatch)
    if case == "rain":
        j.evidence_change = lambda e: e["weather"].update(rain_rate_mm_h=5, rain_today_mm=5)
    elif case == "revoked": j.revoke = True
    elif case == "authority_error": j.authority_error = True
    elif case == "callback_error":
        def fail(_): raise RuntimeError("provider unavailable")
        j.final_change = fail
    else:
        original = j.authority
        def aged(*args):
            result = original(*args)
            if j.authority_calls == 2: j.now = NOW + timedelta(minutes=6)
            return result
        j.authority = aged
    j.run()
    j.assert_no_claim()
    assert len(j.reads) <= 2  # Never fall back and re-read after a final failure.


@pytest.mark.parametrize("field,value", [
    ("controller_response_digest", "OTHER"), ("controller_safety_generation", "OTHER"),
    ("provider_output_state", {"1": "OFF"}), ("channel", True), ("zone_id", "C12345"),
])
def test_final_context_binding_rejects_artifact_substitution(monkeypatch, field, value):
    j = Journey(monkeypatch)
    j.check_change = lambda c: replace(c, artifact={**c.artifact, field: value})
    j.run(); j.assert_no_claim()


@pytest.mark.parametrize("field,value", [
    ("response_digest", "OTHER"), ("controller_safety_generation", "OTHER"),
    ("device_id", "OTHER"), ("channel", True), ("observed_at", "OTHER"),
    ("relevant_outputs_off", False),
])
def test_final_context_binding_rejects_safety_substitution(monkeypatch, field, value):
    j = Journey(monkeypatch)
    j.check_change = lambda c: replace(c, safety={**c.safety, field: value})
    j.run(); j.assert_no_claim()


@pytest.mark.parametrize("case", ["custom_readback", "instance_override", "class_override", "subclass",
    "execution_wrapper", "token_mismatch", "source_mismatch", "A", "projector_override"])
def test_capability_declines_custom_or_non_bc_semantics(monkeypatch, case):
    j = Journey(monkeypatch)
    transport, zone, readback, tokens, source = j.transport, j.zone, provider.read_current_device, j.tokens, j.source
    if case == "custom_readback":
        readback = lambda **_: {}
        transport.readback = readback
    elif case == "instance_override": transport.read_safety_configuration = lambda **_: {}
    elif case == "class_override": monkeypatch.setattr(RootlineIFTTTTransport, "read_safety_configuration", lambda **_: {})
    elif case == "subclass":
        class Custom(RootlineIFTTTTransport): pass
        transport = Custom(token_store=tokens, environ=source, readback=readback)
    elif case == "execution_wrapper": transport = bind_execution_transport(transport, {})
    elif case == "token_mismatch": tokens = object()
    elif case == "source_mismatch": source = dict(source)
    elif case == "A": zone = "A12345"
    else: transport.final_bc_check = lambda *_a, **_k: None
    assert runtime._native_bc_final_transport(transport, zone, readback, tokens, source) is None


def test_native_capability_survives_transparent_admission_observer(monkeypatch):
    j = Journey(monkeypatch)
    wrapped = runtime._ObservedAdmissionTransport(j.transport, {"provider_command_attempts": 0})
    assert runtime._native_bc_final_transport(wrapped, j.zone, provider.read_current_device,
        j.tokens, j.source) is j.transport


def test_legacy_injected_safety_override_is_still_called(monkeypatch):
    j = Journey(monkeypatch)
    calls = []
    def safety(**kwargs):
        calls.append(kwargs)
        return {"authoritative": False}
    j.transport.read_safety_configuration = safety
    j.run()
    assert len(calls) == 1 and len(j.reads) == 1
    j.assert_no_claim()


@pytest.mark.parametrize("override", ["instance", "class"])
def test_overridden_snapshot_stays_legacy_and_unsafe_proof_blocks_on(monkeypatch, override):
    j = Journey(monkeypatch)
    calls = []
    def unsafe(*args):
        calls.append(args)
        snapshot = controller()
        snapshot["actuation_configuration_safe"] = False
        return snapshot
    if override == "instance":
        monkeypatch.setattr(j.transport, "_snapshot", unsafe)
    else:
        monkeypatch.setattr(RootlineIFTTTTransport, "_snapshot", unsafe)
    assert runtime._native_bc_final_transport(j.transport, j.zone,
        provider.read_current_device, j.tokens, j.source) is None
    result = j.run()
    assert result["status"] == "provider_safety_readback_unavailable"
    assert len(calls) == 1 and len(j.reads) == 1
    j.assert_no_claim()
