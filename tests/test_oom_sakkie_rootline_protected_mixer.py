from copy import deepcopy
from datetime import datetime, timezone

from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
from modules.oom_sakkie.rootline_protected_mixer import ACTION_KIND, build_preview_payload, execute_claimed_mixer
from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility

NOW = datetime(2026, 8, 16, 13, 35, 32, tzinfo=timezone.utc)

def artifact():
    safety = {"authoritative": True, "response_digest": "READ-1", "device_id": "100204d497",
        "channel": 2, "output_state": "OFF", "native_inching_enabled": True,
        "native_inching_seconds": 300, "power_restoration_state": "OFF",
        "schedules_enabled": False, "timers_enabled": False, "scenes_enabled": False,
        "interlock_enabled": False, "controller_safety_generation": "BASELINE-1",
        "commissioned": True, "physical_commissioning_generation": "COMMISSION-CH2",
        "observed_at": NOW.isoformat()}
    context = {"plan_generation": "PLAN-3676", "injection_active": False,
        "verified_mixing_minutes_today": 0, "verified_mixing_sessions_today": 0,
        "mixing_history_complete_through": NOW.isoformat(), "power_suitable": True,
        "prior_shutdown_unverified": False}
    return build_auxiliary_eligibility(task={"auxiliary_device_id": "FERTILIZER-MIXER-CH2"},
        safety=safety, context=context, flags={"ROOTLINE_FERTILIZER_MIXING_ENABLED": True}, now=NOW)

def parsed():
    return {"telegram_user_id": "5721652188", "telegram_chat_id": "5721652188",
        "provider_message_id": "3676", "provider_timestamp": NOW.isoformat(),
        "text": "I am at the fertilizer valves and ready for the five-minute Mixer CH2  commissioning test."}

def claim(payload):
    return {"mission_id": payload["mission_id"], "preview_payload": payload,
        "preview_digest": canonical_preview_digest(ACTION_KIND, payload)}

def test_preview_binds_exact_non_actuating_mixer_contract():
    payload = build_preview_payload(artifact(), parsed())
    assert (payload["auxiliary_device_id"], payload["device_id"], payload["channel"]) == (
        "FERTILIZER-MIXER-CH2", "100204d497", 2)
    assert payload["maximum_duration_seconds"] == payload["native_auto_off_seconds"] == 300
    assert payload["emergency_off_required"] and payload["no_on_retry"]
    assert payload["injection_enabled"] is False
    assert payload["physical_observations_required"] == ["normal_recirculation", "pump_stopped"]

def test_exact_claim_delegates_once_to_existing_executor():
    payload = build_preview_payload(artifact(), parsed()); calls = []
    def runner(**kwargs):
        calls.append(kwargs)
        return {"success": True, "status": "auxiliary_started", "hardware_commands": 1,
            "provider_control_calls": 1}
    result, status = execute_claimed_mixer(claim(payload), parsed=parsed(), runner=runner)
    assert status == 200 and result["status"] == "auxiliary_started" and len(calls) == 1

def test_tamper_or_wrong_chat_never_reaches_executor():
    payload = build_preview_payload(artifact(), parsed()); payload = deepcopy(payload); payload["channel"] = 1
    calls = []
    result, status = execute_claimed_mixer(claim(payload), parsed=parsed(),
        runner=lambda **kwargs: calls.append(kwargs))
    assert status == 409 and result["hardware_commands"] == 0 and calls == []
    payload = build_preview_payload(artifact(), parsed()); wrong = parsed(); wrong["telegram_chat_id"] = "OTHER"
    result, status = execute_claimed_mixer(claim(payload), parsed=wrong,
        runner=lambda **kwargs: calls.append(kwargs))
    assert status == 409 and result["provider_control_calls"] == 0 and calls == []
