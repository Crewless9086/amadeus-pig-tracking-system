from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest

from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
from modules.oom_sakkie.protected_action_claims import (load_active_child_claim,
    load_reassessable_contained_presence_claim)
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.rootline_protected_mixer import (ACTION_KIND,
    PRESENCE_ACTION_KIND, build_preview_payload, create_presence_refresh_notice,
    create_mixer_preview, execute_claimed_mixer, execute_presence_refresh)
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

def test_fresh_preview_requests_only_exact_expired_unbound_presence_handoff(monkeypatch):
    captured = []
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.load_active_presence_claim",
        lambda **_kwargs: None)
    monkeypatch.setattr("modules.oom_sakkie.rootline_protected_mixer.create_claim",
        lambda **kwargs: (captured.append(kwargs) or {"success": True,
            "callback_token": "CURRENT", "preview_digest": canonical_preview_digest(
                kwargs["action_kind"], kwargs["preview_payload"]),
            "expires_at": "2026-08-16T13:40:32+00:00"}))
    result = create_mixer_preview(owner_result={"handled": True,
        "status": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "next_specialist_step": "supervised_fertilizer_mixer_proof",
        "ready_for_supervised_proof": True,
        "authority": {"configuration_write": False, "hardware_control": False,
            "farm_write": False, "telegram_send": False}}, parsed=parsed(),
        gateway_authority=issue_gateway_owner_authority("5721652188", "5721652188"),
        prepare=lambda **_kwargs: {"success": True,
            "status": "commissioning_protected_preview_ready",
            "eligibility": artifact(), "hardware_commands": 0,
            "provider_control_calls": 0}, now=NOW)
    handoff = captured[0]["retire_expired_unbound_predecessor"]
    assert handoff == {"action_kind": PRESENCE_ACTION_KIND,
        "contract_version": "oom_rootline_mixer_presence_refresh.v1",
        "specialist_identity": "ROOTLINE",
        "next_specialist_step": "supervised_fertilizer_mixer_proof"}
    assert result["status"] == "mixer_protected_preview_created"
    assert result["hardware_commands"] == result["provider_control_calls"] == 0

def test_claim_conflict_never_reuses_plain_ready_answer(monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.load_active_presence_claim",
        lambda **_kwargs: None)
    monkeypatch.setattr("modules.oom_sakkie.rootline_protected_mixer.create_claim",
        lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("active conflict")))
    result = create_mixer_preview(owner_result={"handled": True,
        "status": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "next_specialist_step": "supervised_fertilizer_mixer_proof",
        "ready_for_supervised_proof": True,
        "answer": "FERTILIZER CHECK — READY",
        "authority": {"configuration_write": False, "hardware_control": False,
            "farm_write": False, "telegram_send": False}}, parsed=parsed(),
        gateway_authority=issue_gateway_owner_authority("5721652188", "5721652188"),
        prepare=lambda **_kwargs: {"success": True,
            "status": "commissioning_protected_preview_ready",
            "eligibility": artifact(), "hardware_commands": 0,
            "provider_control_calls": 0}, now=NOW)
    assert result["status"] == "mixer_protected_preview_conflict"
    assert "Nothing started" in result["answer"]
    assert "FERTILIZER CHECK" not in result["answer"]
    assert result["hardware_commands"] == result["provider_control_calls"] == 0

def test_preview_requires_exact_canonical_device_registry_record():
    with pytest.raises(ValueError,match="device_registry_missing"):
        build_preview_payload(artifact(),parsed(),device_loader=lambda _key:None)
    baseline=build_preview_payload(artifact(),parsed())["device_record"]
    with pytest.raises(ValueError,match="device_registry_binding_changed"):
        build_preview_payload(artifact(),parsed(),device_loader=lambda _key:{
          "device_record":{**baseline,"registry_generation":2}})

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

def test_canonical_registry_change_blocks_execution_before_runner():
    payload=build_preview_payload(artifact(),parsed());calls=[]
    changed={**payload["device_record"],"registry_generation":2}
    result,status=execute_claimed_mixer(claim(payload),parsed=parsed(),
      runner=lambda **_kwargs:calls.append(1),device_loader=lambda _key:{"device_record":changed})
    assert status==409 and result["status"]=="mixer_protected_binding_mismatch"
    assert calls==[]

def test_expired_presence_notice_has_one_protected_ready_action(monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.rootline_protected_mixer.create_claim",
        lambda **kwargs: {"success": True, "callback_token": "TOKEN", "preview_digest":
            canonical_preview_digest(kwargs["action_kind"], kwargs["preview_payload"]),
            "expires_at": "2026-08-17T13:35:32+00:00"})
    result = create_presence_refresh_notice(owner_result={"specialist_identity": "ROOTLINE",
        "next_specialist_step": "supervised_fertilizer_mixer_proof"}, parsed=parsed())
    assert result["hardware_commands"] == result["provider_control_calls"] == 0
    assert result["reply_markup"]["inline_keyboard"][0][0]["text"] == "I am ready now"
    assert "Nothing started" in result["answer"]

def test_ready_button_mints_current_preview_without_actuation(monkeypatch):
    monkeypatch.setattr("modules.oom_sakkie.rootline_protected_mixer.create_claim",
        lambda **kwargs: {"success": True, "callback_token": "MIXER", "preview_digest":
            canonical_preview_digest(kwargs["action_kind"], kwargs["preview_payload"]),
            "expires_at": "2026-08-16T13:40:32+00:00"})
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.load_active_child_claim",
        lambda **_kwargs: None)
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.load_active_presence_claim",
        lambda **_kwargs: None)
    old = parsed()
    old_payload = {"contract_version": "oom_rootline_mixer_presence_refresh.v1",
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "owner_user_id": "5721652188", "private_chat_id": "5721652188",
        "lost_presence_provider_message_id": "3676",
        "lost_presence_provider_timestamp": old["provider_timestamp"],
        "lost_presence_text_sha256": "a" * 64, "specialist_identity": "ROOTLINE",
        "next_specialist_step": "supervised_fertilizer_mixer_proof"}
    presence_claim = {"callback_token": "PARENT", "preview_payload": old_payload,
        "preview_digest": canonical_preview_digest(PRESENCE_ACTION_KIND, old_payload)}
    callback = parsed(); callback["provider_message_id"] = "CALLBACK-READY"
    def prepare(**kwargs):
        assert kwargs["acceptance_loader"]({}, {}) is True
        return {"success": True, "status": "commissioning_protected_preview_ready",
            "eligibility": artifact(), "hardware_commands": 0, "provider_control_calls": 0}
    result, status = execute_presence_refresh(presence_claim, parsed=callback,
        gateway_authority=issue_gateway_owner_authority("5721652188", "5721652188"),
        prepare=prepare, now=NOW)
    assert status == 200 and result["status"] == "mixer_protected_preview_created"
    assert result["hardware_commands"] == result["provider_control_calls"] == 0

def test_ready_callback_recovers_committed_child_after_parent_crash(monkeypatch):
    child_payload = build_preview_payload(artifact(), parsed())
    child_payload["presence_refresh_claim_token"] = "PARENT"
    child_digest = canonical_preview_digest(ACTION_KIND, child_payload)
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.load_active_child_claim",
        lambda **kwargs: {"success": True, "callback_token": "CHILD",
            "preview_digest": child_digest, "expires_at": "2026-08-16T13:40:32+00:00",
            "preview_payload": child_payload, "preview_card_message_id": ""})
    old_payload = {"contract_version": "oom_rootline_mixer_presence_refresh.v1",
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "owner_user_id": "5721652188", "private_chat_id": "5721652188",
        "lost_presence_provider_message_id": "3676",
        "lost_presence_provider_timestamp": NOW.isoformat(),
        "lost_presence_text_sha256": "a" * 64, "specialist_identity": "ROOTLINE",
        "next_specialist_step": "supervised_fertilizer_mixer_proof"}
    parent = {"callback_token": "PARENT", "preview_payload": old_payload,
        "preview_digest": canonical_preview_digest(PRESENCE_ACTION_KIND, old_payload)}
    result, status = execute_presence_refresh(parent, parsed=parsed(),
        gateway_authority=issue_gateway_owner_authority("5721652188", "5721652188"),
        prepare=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not rebuild")),
        now=NOW)
    assert status == 200 and result["callback_token"] == "CHILD"
    assert result["hardware_commands"] == result["provider_control_calls"] == 0

def test_expired_unbound_child_is_atomically_retired_for_one_fresh_preview():
    statements = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def execute(self, sql, params): statements.append((sql, params))
        def fetchall(self):
            return [("CHILD", "d" * 64, NOW - timedelta(seconds=1), {}, None)]
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return Cursor()
    child = load_active_child_claim(action_kind=ACTION_KIND,
        mission_id="OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        parent_claim_token="PARENT", owner_user_id="5721652188",
        private_chat_id="5721652188", connect_factory=Connection)
    assert child is None
    assert any("set status='expired'" in sql for sql, _params in statements)

def test_retained_inbound_recovers_committed_preview_before_fresh_rebuild(monkeypatch):
    payload = build_preview_payload(artifact(), parsed())
    digest = canonical_preview_digest(ACTION_KIND, payload)
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.load_active_presence_claim",
        lambda **_kwargs: {"success": True, "callback_token": "EXISTING",
            "preview_digest": digest, "expires_at": "2026-08-16T13:40:32+00:00",
            "preview_payload": payload, "preview_card_message_id": ""})
    result = create_mixer_preview(owner_result={"handled": True,
        "status": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "next_specialist_step": "supervised_fertilizer_mixer_proof",
        "ready_for_supervised_proof": True,
        "authority": {"configuration_write": False, "hardware_control": False,
            "farm_write": False, "telegram_send": False}}, parsed=parsed(),
        gateway_authority=issue_gateway_owner_authority("5721652188", "5721652188"),
        prepare=lambda **_kwargs: (_ for _ in ()).throw(AssertionError("must not rebuild")))
    assert result["callback_token"] == "EXISTING"
    assert result["hardware_commands"] == result["provider_control_calls"] == 0

def test_transient_contained_ready_press_reassesses_without_another_owner_action(monkeypatch):
    presence_payload = {"contract_version": "oom_rootline_mixer_presence_refresh.v1",
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "owner_user_id": "5721652188", "private_chat_id": "5721652188",
        "lost_presence_provider_message_id": "3676",
        "lost_presence_provider_timestamp": NOW.isoformat(),
        "lost_presence_text_sha256": "a" * 64, "specialist_identity": "ROOTLINE",
        "next_specialist_step": "supervised_fertilizer_mixer_proof"}
    retained = {"success": True, "callback_token": "PARENT",
        "action_kind": PRESENCE_ACTION_KIND,
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "preview_payload": presence_payload,
        "preview_digest": canonical_preview_digest(PRESENCE_ACTION_KIND, presence_payload),
        "confirmation_provider_message_id": "READY-CALLBACK",
        "confirmation_provider_timestamp": NOW.isoformat()}
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.load_active_presence_claim",
        lambda **_kwargs: None)
    monkeypatch.setattr(
        "modules.oom_sakkie.protected_action_claims.load_reassessable_contained_presence_claim",
        lambda **_kwargs: retained)
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.load_active_child_claim",
        lambda **_kwargs: None)
    monkeypatch.setattr("modules.oom_sakkie.rootline_protected_mixer.create_claim",
        lambda **kwargs: {"success": True, "callback_token": "CHILD",
            "preview_digest": canonical_preview_digest(
                kwargs["action_kind"], kwargs["preview_payload"]),
            "expires_at": "2026-08-16T13:40:32+00:00"})
    completed = []
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.complete_claim",
        lambda token, result, **_kwargs: completed.append((token, result["status"])))
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.contain_claim",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("successful reassessment must be consumed")))
    calls = []
    def prepare(**kwargs):
        calls.append(kwargs["parsed"]["provider_message_id"])
        if len(calls) == 1:
            return {"success": False, "status": "commissioning_presence_expired",
                "hardware_commands": 0, "provider_control_calls": 0}
        return {"success": True, "status": "commissioning_protected_preview_ready",
            "eligibility": artifact(), "hardware_commands": 0,
            "provider_control_calls": 0}
    result = create_mixer_preview(owner_result={"handled": True,
        "status": "specialist_accepted", "specialist_identity": "ROOTLINE",
        "mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "card_mission_id": "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        "next_specialist_step": "supervised_fertilizer_mixer_proof",
        "ready_for_supervised_proof": True,
        "authority": {"configuration_write": False, "hardware_control": False,
            "farm_write": False, "telegram_send": False}}, parsed=parsed(),
        gateway_authority=issue_gateway_owner_authority("5721652188", "5721652188"),
        prepare=prepare, now=NOW)
    assert calls == ["3676", "READY-CALLBACK"]
    assert result["status"] == "mixer_protected_preview_created"
    assert result["callback_token"] == "CHILD"
    assert result["hardware_commands"] == result["provider_control_calls"] == 0
    assert completed == [("PARENT", "mixer_protected_preview_created")]

def test_contained_presence_transition_holds_cursor_lock_through_update():
    statements = []
    hold = {"status": "commissioning_specific_hold",
        "next_reassessment": "next_scheduler_tick", "hardware_commands": 0,
        "provider_control_calls": 0}
    row = ("PARENT", "d" * 64, "GEN", {"contract_version":
        "oom_rootline_mixer_presence_refresh.v1"}, "READY-CALLBACK", NOW,
        hold, NOW + timedelta(hours=1), "contained")
    class Cursor:
        closed = False
        rowcount = 1
        def __enter__(self): return self
        def __exit__(self, *_args): self.closed = True
        def execute(self, sql, params):
            if self.closed: raise AssertionError("execute after cursor close")
            statements.append((sql, params))
        def fetchall(self): return [row]
    class Connection:
        def __init__(self): self.cur = Cursor()
        def __enter__(self): return self
        def __exit__(self, *_args): return False
        def cursor(self): return self.cur
    result = load_reassessable_contained_presence_claim(action_kind=PRESENCE_ACTION_KIND,
        mission_id="OOM-ROOTLINE-FERTILIZER-CONFIG-20260809",
        owner_user_id="5721652188", private_chat_id="5721652188",
        provider_message_id="3676", connect_factory=Connection)
    assert result["callback_token"] == "PARENT"
    assert len(statements) == 2
    assert "for update" in statements[0][0].lower()
    assert "set status='executing'" in statements[1][0]

def test_migration_admits_both_mixer_claim_kinds_and_preserves_existing_spine():
    sql = Path("supabase/migrations/202608160002_allow_rootline_mixer_protected_claims.sql").read_text()
    for kind in ("rootline_fertilizer_mixer_commissioning",
            "rootline_fertilizer_mixer_presence_refresh", "rootline_irrigation_segment",
            "sam_sale_payment", "beacon_media_review"):
        assert f"'{kind}'" in sql
    assert "revoke all on app_private.oom_protected_action_claims" in sql
