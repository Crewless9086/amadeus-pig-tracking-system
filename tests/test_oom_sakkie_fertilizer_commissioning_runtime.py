from datetime import datetime, timedelta, timezone

from modules.oom_sakkie.rootline_fertilizer_commissioning_runtime import (
    _evaluation_time, continue_fertilizer_commissioning,
    emergency_off_fertilizer_mixer, execute_protected_fertilizer_commissioning,
    execute_fertilizer_commissioning_under_standing_authority,
    recover_fertilizer_commissioning,
)
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority

NOW = datetime(2026, 8, 10, 6, 51, 14, tzinfo=timezone.utc)


def test_live_evaluation_clock_is_sampled_after_provider_io(monkeypatch):
    after = NOW + timedelta(seconds=61)
    class Clock:
        @staticmethod
        def now(_tz): return after
    monkeypatch.setattr(
        "modules.oom_sakkie.rootline_fertilizer_commissioning_runtime.datetime", Clock)
    assert _evaluation_time(NOW, False) == after
    assert _evaluation_time(NOW, True) == NOW


def owner_result():
    return {"handled": True, "status": "specialist_accepted",
        "specialist_identity": "ROOTLINE",
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "next_specialist_step": "supervised_fertilizer_mixer_proof",
        "ready_for_supervised_proof": True,
        "authority": {"configuration_write": False, "hardware_control": False,
            "farm_write": False, "telegram_send": False}}


def authority():
    return issue_gateway_owner_authority("5721652188", "5721652188")


def parsed(text="Yes, I'm at the fertilizer valve"):
    return {"telegram_user_id": "5721652188", "telegram_chat_id": "5721652188",
        "provider_message_id": "3493", "provider_timestamp": NOW.isoformat(), "text": text}


def safety():
    return {"authoritative": True, "response_digest": "READ-1",
        "device_id": "100204d497", "channel": 2, "output_state": "OFF",
        "native_inching_enabled": True, "native_inching_seconds": 300,
        "power_restoration_state": "OFF", "schedules_enabled": False,
        "timers_enabled": False, "scenes_enabled": False, "interlock_enabled": False,
        "controller_safety_generation": "BASELINE-1",
        "physical_commissioning_generation": "COMMISSION-CH2",
        "commissioned": True, "observed_at": NOW.isoformat()}


class Store:
    def __init__(self): self.active = None; self.events = []; self.claims = set(); self.physical = None
    def __call__(self, action, payload):
        if action == "load_active_auxiliary": return self.active
        if action == "load_auxiliary_history": return []
        if action == "load_auxiliary_physical_outcome": return self.physical
        if action == "load_auxiliary_containment": return {"contained": False}
        if action == "load_auxiliary_off_attempts": return []
        if action in {"claim_auxiliary_before_on", "claim_auxiliary_off_attempt"}:
            key = (action, payload.get("execution_id"), payload.get("attempt"))
            created = key not in self.claims; self.claims.add(key)
            return {"success": True, "created": created}
        self.events.append((action, dict(payload)))
        if action == "record_auxiliary_physical_outcome": self.physical = dict(payload)
        if action == "mark_auxiliary_active": self.active = dict(payload)
        if action in {"record_auxiliary_completed", "contain_auxiliary_device"}: self.active = None
        return {"success": True, "created": True}


class Transport:
    auxiliary_on_authorizer = None
    def __init__(self): self.state = "OFF"; self.commands = []
    def read_safety_configuration(self, **_kwargs):
        return {**safety(), "output_state": self.state}
    def read_output_state(self, **_kwargs):
        return {"authoritative": True, "state": self.state,
                "evidence_id": "OUTPUT-" + self.state, "retrieved_at": NOW.isoformat()}
    def set_state(self, *, device_id, channel, state, idempotency_key):
        if state == "ON" and (not callable(self.auxiliary_on_authorizer)
                or not self.auxiliary_on_authorizer(
                    device_id=device_id, channel=channel, idempotency_key=idempotency_key)):
            return {"accepted_unambiguous": False}
        self.commands.append((state, idempotency_key)); self.state = state
        return {"accepted_unambiguous": True, "status": "accepted"}


def test_emergency_off_wrapper_cannot_target_injection_or_borehole():
    store=Store();transport=Transport();store.active={"execution_id":"MIXER-1",
        "auxiliary_device_id":"FERTILIZER-MIXER-CH2","device_id":"100204d497",
        "channel":2,"state":"Active"}
    result=emergency_off_fertilizer_mixer(store=store,transport=transport,
        reason="commissioning_emergency")
    assert result["status"]=="auxiliary_emergency_off_verified"
    assert result["hardware_commands"]==1
    assert result["injection_enabled"] is False
    assert transport.commands==[("OFF","MIXER-1:OFF:1")]


def test_fresh_context_starts_exactly_one_mixer_proof_and_replay_does_not_start_again():
    store = Store(); transport = Transport()
    result = continue_fertilizer_commissioning(owner_result=owner_result(), parsed=parsed(),
        gateway_authority=authority(), now=NOW, store=store, transport=transport,
        power_loader=lambda _now: {"suitable": True, "generation": "POWER-1"},
        acceptance_loader=lambda *_args: True)
    assert result["status"] == "auxiliary_started"
    assert result["question_count"] == 0
    assert [row[0] for row in transport.commands] == ["ON"]
    denied=transport.set_state(device_id="100204d497",channel=2,state="ON",
        idempotency_key=store.active["execution_id"]+":ON")
    assert denied["accepted_unambiguous"] is False
    assert [row[0] for row in transport.commands] == ["ON"]
    replay = continue_fertilizer_commissioning(owner_result=owner_result(), parsed=parsed(),
        gateway_authority=authority(), now=NOW + timedelta(seconds=1), store=store, transport=transport,
        power_loader=lambda _now: {"suitable": True, "generation": "POWER-1"},
        acceptance_loader=lambda *_args: True)
    assert replay["status"] == "auxiliary_active"
    assert [row[0] for row in transport.commands] == ["ON"]


def test_scheduler_recovers_after_native_deadline_and_never_retries_on():
    store = Store(); transport = Transport()
    started = continue_fertilizer_commissioning(owner_result=owner_result(), parsed=parsed(),
        gateway_authority=authority(), now=NOW, store=store, transport=transport,
        power_loader=lambda _now: {"suitable": True, "generation": "POWER-1"},
        acceptance_loader=lambda *_args: True)
    assert started["status"] == "auxiliary_started"
    transport.state = "OFF"  # native provider auto-OFF
    completed = recover_fertilizer_commissioning(now=NOW + timedelta(seconds=301),
        store=store, transport=transport)
    assert completed["status"] == "auxiliary_completed"
    assert [row[0] for row in transport.commands] == ["ON", "OFF"]
    assert completed["mixing_enabled"] is True
    assert completed["injection_enabled"] is False


def test_natural_physical_followup_is_retained_and_enables_only_mixing_after_shutdown():
    store = Store(); transport = Transport()
    continue_fertilizer_commissioning(owner_result=owner_result(), parsed=parsed(),
        gateway_authority=authority(), now=NOW, store=store, transport=transport,
        power_loader=lambda _now: {"suitable": True, "generation": "POWER-1"},
        acceptance_loader=lambda *_args: True)
    followup = parsed("Ja, dit sirkuleer en die pomp werk; die ander uitsette is af")
    followup["provider_message_id"] = "3494"
    followup["semantic"] = {"commissioning_facts": {
        "mixer_recirculating": True, "pump_expected": True, "other_outputs_off": True}}
    retained = continue_fertilizer_commissioning(owner_result=owner_result(), parsed=followup,
        gateway_authority=authority(),
        now=NOW + timedelta(seconds=30), store=store, transport=transport,
        power_loader=lambda _now: {"suitable": True, "generation": "POWER-1"},
        acceptance_loader=lambda *_args: True)
    assert retained["requires_visible_notification"] is True
    transport.state = "OFF"
    completed = recover_fertilizer_commissioning(now=NOW + timedelta(seconds=301),
        store=store, transport=transport)
    assert completed["mixing_enabled"] is True
    assert completed["injection_enabled"] is False


def test_low_power_is_commissioning_specific_hold_with_owned_reassessment():
    result = continue_fertilizer_commissioning(owner_result=owner_result(), parsed=parsed(),
        gateway_authority=authority(), now=NOW, store=Store(), transport=Transport(),
        power_loader=lambda _now: {"suitable": False, "generation": "POWER-LOW"},
        acceptance_loader=lambda *_args: True)
    assert result["status"] == "commissioning_specific_hold"
    assert result["hardware_commands"] == 0
    assert result["next_reassessment"] == "next_scheduler_tick"


def test_standing_authority_rechecks_one_transient_safety_hold_then_starts_once(monkeypatch):
    outcomes = iter([
        {"status": "commissioning_specific_hold", "hold_reason": "auxiliary_safety_unproven",
         "hardware_commands": 0, "provider_control_calls": 0},
        {"success": True, "status": "auxiliary_started", "hardware_commands": 1},
    ])
    calls = []
    def run(**kwargs):
        calls.append(kwargs)
        return next(outcomes)
    monkeypatch.setattr(
        "modules.oom_sakkie.rootline_fertilizer_commissioning_runtime.continue_fertilizer_commissioning",
        run)
    result = execute_fertilizer_commissioning_under_standing_authority(
        owner_result=owner_result(), parsed=parsed(), gateway_authority=authority())
    assert result["status"] == "auxiliary_started"
    assert result["bounded_readiness_recheck"] is True
    assert len(calls) == 2


def test_standing_authority_never_rechecks_low_power_or_effectful_hold(monkeypatch):
    for hold in (
        {"status": "commissioning_specific_hold", "hold_reason": "low_power_mix_deferred",
         "hardware_commands": 0, "provider_control_calls": 0},
        {"status": "commissioning_specific_hold", "hold_reason": "auxiliary_safety_unproven",
         "hardware_commands": 1, "provider_control_calls": 1},
    ):
        calls = []
        def run(**kwargs):
            calls.append(kwargs)
            return hold
        monkeypatch.setattr(
            "modules.oom_sakkie.rootline_fertilizer_commissioning_runtime.continue_fertilizer_commissioning",
            run)
        assert execute_fertilizer_commissioning_under_standing_authority(
            owner_result=owner_result(), parsed=parsed(), gateway_authority=authority()) == hold
        assert len(calls) == 1


def test_unproven_acceptance_cannot_mint_auxiliary_on_authority():
    transport=Transport()
    result=continue_fertilizer_commissioning(owner_result=owner_result(),parsed=parsed(),
        gateway_authority=authority(),now=NOW,store=Store(),transport=transport,
        acceptance_loader=lambda *_args:False)
    assert result["status"]=="commissioning_acceptance_receipt_unproven"
    assert transport.commands==[]


def test_stale_but_proven_request_fails_anti_replay_without_presence_prompt_or_start():
    transport=Transport()
    result=continue_fertilizer_commissioning(owner_result=owner_result(),parsed=parsed(),
        gateway_authority=authority(),now=NOW+timedelta(minutes=6),store=Store(),transport=transport,
        acceptance_loader=lambda *_args:True)
    assert result["status"]=="commissioning_request_expired"
    assert result["question_count"]==0
    assert "presence" not in result["answer"].lower()
    assert transport.commands==[]


def test_transport_override_is_exactly_scoped_and_does_not_enable_other_auxiliary_on():
    allowed = "ROOTLINE-AUX-EXECUTION-1:ON"
    transport = RootlineIFTTTTransport(token_store=object(), environ={
        "ROOTLINE_IFTTT_MAKER_KEY": "key"}, readback=lambda **_kwargs: {},
        http_open=lambda *_args, **_kwargs: None,
        auxiliary_on_authorizer=lambda **edge: edge["idempotency_key"] == allowed)
    denied = transport.set_state(device_id="100204d497", channel=2, state="ON",
        idempotency_key="SOME-OTHER-EXECUTION:ON")
    assert denied["status"] == "auxiliary_authority_disabled"


def test_protected_mixer_never_recovers_an_unrelated_active_auxiliary():
    store = Store(); transport = Transport()
    eligibility = build_auxiliary_eligibility(
        task={"auxiliary_device_id": "FERTILIZER-MIXER-CH2"}, safety=safety(),
        context={"plan_generation": "PLAN", "injection_active": False,
            "verified_mixing_minutes_today": 0, "verified_mixing_sessions_today": 0,
            "mixing_history_complete_through": NOW.isoformat(), "power_suitable": True,
            "prior_shutdown_unverified": False},
        flags={"ROOTLINE_FERTILIZER_MIXING_ENABLED": True}, now=NOW)
    store.active = {"execution_id": "UNRELATED", "consumption_key": "OTHER",
        "auxiliary_device_id": "FERTILIZER-INJECTION-CH1", "device_id": "100204d497",
        "channel": 1}
    result = execute_protected_fertilizer_commissioning(eligibility=eligibility,
        parsed=parsed(), now=NOW, store=store, transport=transport,
        power_loader=lambda _now: {"suitable": True, "generation": "POWER-1"})
    assert result["status"] == "commissioning_active_execution_conflict"
    assert result["hardware_commands"] == 0 and transport.commands == []


def test_protected_callback_recovers_durable_completion_after_claim_write_crash():
    store = Store(); transport = Transport()
    eligibility = build_auxiliary_eligibility(
        task={"auxiliary_device_id": "FERTILIZER-MIXER-CH2"}, safety=safety(),
        context={"plan_generation": "PLAN", "injection_active": False,
            "verified_mixing_minutes_today": 0, "verified_mixing_sessions_today": 0,
            "mixing_history_complete_through": NOW.isoformat(), "power_suitable": True,
            "prior_shutdown_unverified": False},
        flags={"ROOTLINE_FERTILIZER_MIXING_ENABLED": True}, now=NOW)
    completed = {"state": "Completed", "shutdown_verified": True,
        "execution_id": eligibility["execution_id"],
        "consumption_key": eligibility["consumption_key"],
        "auxiliary_device_id": "FERTILIZER-MIXER-CH2", "device_id": "100204d497",
        "channel": 2, "maximum_duration_seconds": 300,
        "physical_outcome_verified": False}
    original = store.__call__
    def terminal_store(action, payload):
        if action == "load_auxiliary_history": return [completed]
        return original(action, payload)
    result = execute_protected_fertilizer_commissioning(eligibility=eligibility,
        parsed=parsed(), now=NOW + timedelta(minutes=6), store=terminal_store,
        transport=transport)
    assert result["status"] == "auxiliary_completed"
    assert result["hardware_commands"] == 0 and transport.commands == []


def test_afrikaans_and_short_affirmatives_use_same_typed_context_not_phrase_rules():
    for text in ("Yes, I'm still here", "I am ready", "Ek is by die kunsmiskleppe", "Ja"):
        store = Store(); transport = Transport()
        result = continue_fertilizer_commissioning(owner_result=owner_result(),
            parsed=parsed(text), gateway_authority=authority(), now=NOW, store=store, transport=transport,
            power_loader=lambda _now: {"suitable": True, "generation": "POWER-1"},
            acceptance_loader=lambda *_args: True)
        assert result["status"] == "auxiliary_started"
        assert len(transport.commands) == 1


def test_default_transport_reads_the_exact_registered_fertilizer_controller(monkeypatch):
    observed = []
    def exact(device_id, *, token_store, environ):
        observed.append((device_id, token_store, environ))
        return {"actuation_configuration_safe": True, "actuation_safety_complete": True,
            "device_id": device_id,
            "channels": [{"channel": number, "output_state": "OFF",
                "native_auto_off_enabled": True,
                "native_auto_off_seconds": 300 if number == 2 else 120,
                "power_restoration_state": "OFF"} for number in (1, 2, 3, 4)],
            "timers_enabled": False, "interlock_enabled": False, "scenes_enabled": False,
            "commissioned_baseline_id": "FERTILIZER-BASELINE",
            "commissioned_supervised_channels": [2],
            "response_digest": "READBACK", "retrieved_at": NOW.isoformat(),
            "provider_control_calls": 0, "current_outputs_authoritative": True}
    monkeypatch.setattr("modules.telemetry.rootline_ewelink_readback.read_registered_device", exact)
    transport = RootlineIFTTTTransport(token_store="TOKEN", environ={})
    result = transport.read_safety_configuration(device_id="100204d497", channel=2)
    assert observed == [("100204d497", "TOKEN", {})]
    assert result["authoritative"] is True and result["commissioned"] is True
    injection = transport.read_safety_configuration(device_id="100204d497", channel=1)
    assert injection["authoritative"] is True
    assert injection["controller_safety_generation"] == "FERTILIZER-BASELINE"
    assert injection["physical_commissioning_generation"] is None
    assert injection["commissioned"] is False
    denied = build_auxiliary_eligibility(
        task={"auxiliary_device_id": "FERTILIZER-INJECTION-CH1"}, safety=injection,
        context={"plan_generation": "PLAN", "batch_generation": "BATCH",
            "active_zone_ids": ["B12345"], "zone_execution_id": "ZONE",
            "zone_start_evidence": {}, "zone_output_evidence": {},
            "irrigation_stop_deadline": (NOW + timedelta(minutes=30)).isoformat(),
            "completed_pulses": 0, "mixer_active": False,
            "prior_shutdown_unverified": False},
        flags={"ROOTLINE_FERTILIZER_INJECTION_ENABLED": True}, now=NOW)
    assert denied["status"] == "auxiliary_safety_unproven"
