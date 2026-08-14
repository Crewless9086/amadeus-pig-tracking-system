from unittest.mock import patch

from modules.charlie.shadow_control_tower_input import (
    ACTION,
    handle_shadow_control_tower_input,
    shadow_input_runtime_state,
)
from modules.charlie.private_tools import execute_private_tool
from modules.charlie.private_policy import authenticate_private_action_context
from modules.charlie.private_runtime import handle_authenticated_private_action


ENV = {
    "CHARLIE_SHADOW_CONTROL_TOWER_ENABLED": "true",
    "CHARLIE_TELEGRAM_OWNER_USER_ID": "42",
}
AUTH_ENV = {**ENV, "CHARLIE_EXECUTIVE_ENABLED": "true",
    "CHARLIE_TELEGRAM_BOT_TOKEN": "bot-token",
    "CHARLIE_TELEGRAM_WEBHOOK_SECRET": "s" * 32,
    "CHARLIE_TELEGRAM_OWNER_CHAT_ID": "42"}
AUTH_PAYLOAD = {"message": {"from": {"id": 42},
    "chat": {"id": 42, "type": "private"}}}
AUTH_HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "s" * 32}
AUTH = authenticate_private_action_context(
    AUTH_PAYLOAD, AUTH_HEADERS, "CMQ-20260813-05", AUTH_ENV)


def transaction():
    return {
        "feedback_transaction_id": "CTF-001",
        "terminal_identity": "CORE-visible-terminal",
        "terminal_state": "released",
        "deployed_agent_identity": "CORE-durable-runner",
        "existing_mission_id": "CMQ-20260813-05",
        "business_status": "phase_a_observation",
        "evidence": {"documented": ["PR"], "runtime_loaded": [], "provider_verified": [], "physical": []},
        "worktree_classification": "clean_retained",
        "collision_assessment": "none",
        "proposed_next_terminal": "CORE-visible-terminal",
        "proposed_next_action": "WAIT_FOR_INPUT",
        "proposed_continuation_prompt": "Wait for the human Control Tower decision.",
        "expected_owner_visible_result": "One advisory comparison candidate.",
        "confidence": 0.8,
        "reasons": ["bounded evidence"],
    }


def action(record_type="proposal"):
    return {"action": ACTION, "record_type": record_type, "transaction": transaction()}


def mission_reader(mission_id):
    return {"success": True, "mission": {"mission_id": mission_id}}, 200


def test_disabled_readback_and_input_fail_closed_without_effects():
    state = shadow_input_runtime_state(environ={})
    assert state["enabled"] is False
    result, status = handle_shadow_control_tower_input(action(), runtime_context=AUTH, environ={})
    assert status == 403 and result["status"] == "shadow_control_tower_disabled"
    assert result["farm_writes"] == result["provider_messages"] == result["missions_created"] == 0


def test_authentication_and_cross_mission_fail_closed_before_store():
    with patch("modules.charlie.shadow_control_tower_input.record_shadow_proposal") as record:
        denied, status = handle_shadow_control_tower_input(action(), runtime_context={}, environ=ENV, mission_reader=mission_reader)
        assert status == 403 and denied["status"] == "shadow_control_tower_private_authentication_required"
        wrong = action()
        wrong["transaction"]["existing_mission_id"] = "CMQ-OTHER"
        denied, status = handle_shadow_control_tower_input(wrong, runtime_context=AUTH, environ=ENV, mission_reader=mission_reader)
        assert status == 409 and denied["status"] == "shadow_control_tower_cross_mission_record_denied"
        denied, status = handle_shadow_control_tower_input(action(), runtime_context=None, environ=ENV, mission_reader=mission_reader)
        assert status == 403 and denied["status"] == "shadow_control_tower_private_authentication_required"
        record.assert_not_called()


def test_exact_authenticated_proposal_uses_existing_shadow_store_once():
    expected = ({"success": True, "status": "operational_event_appended", "created": True}, 201)
    with patch("modules.charlie.shadow_control_tower_input.record_shadow_proposal", return_value=expected) as record:
        result, status = handle_shadow_control_tower_input(action(), runtime_context=AUTH, environ=ENV, mission_reader=mission_reader)
    assert status == 201 and result["created"] is True
    assert result["proposal"]["existing_mission_id"] == "CMQ-20260813-05"
    record.assert_called_once()
    assert result["dispatches"] == result["prompts_sent"] == result["farm_writes"] == 0


def test_exact_replay_and_conflict_are_preserved_from_shadow_module():
    proposal = transaction() | {"proposal_id": "SCTP-EXACT", "authority": "non_authoritative_shadow_proposal"}
    payload = action("human_decision") | {
        "proposal": proposal,
        "human_decision": {"human_decision_id": "H-1"},
    }
    duplicate = ({"success": True, "status": "operational_event_duplicate", "created": False}, 200)
    with patch("modules.charlie.shadow_control_tower_input.compare_human_decision", return_value=duplicate) as compare:
        result, status = handle_shadow_control_tower_input(payload, runtime_context=AUTH, environ=ENV, mission_reader=mission_reader)
    assert status == 200 and result["created"] is False
    compare.assert_called_once()
    conflict = ({"success": False, "status": "human_decision_replay_conflict"}, 409)
    with patch("modules.charlie.shadow_control_tower_input.compare_human_decision", return_value=conflict):
        result, status = handle_shadow_control_tower_input(payload, runtime_context=AUTH, environ=ENV, mission_reader=mission_reader)
    assert status == 409 and result["status"] == "human_decision_replay_conflict"
    payload["transaction"]["feedback_transaction_id"] = "CTF-DIFFERENT"
    result, status = handle_shadow_control_tower_input(payload, runtime_context=AUTH, environ=ENV, mission_reader=mission_reader)
    assert status == 409 and result["status"] == "shadow_control_tower_cross_mission_record_denied"


def test_malformed_action_and_missing_existing_mission_fail_closed():
    malformed, status = handle_shadow_control_tower_input({}, runtime_context=AUTH, environ=ENV, mission_reader=mission_reader)
    assert status == 400 and malformed["status"] == "shadow_control_tower_action_invalid"
    missing, status = handle_shadow_control_tower_input(action(), runtime_context=AUTH, environ=ENV,
        mission_reader=lambda _mid: ({"success": False}, 404))
    assert status == 404 and missing["status"] == "shadow_control_tower_existing_mission_not_found"


def test_non_runnable_bootstrap_admission_cannot_enter_shadow_scoring():
    reader = lambda mission_id: ({"mission": {"mission_id": mission_id,
        "status": "paused", "metadata": {"portfolio_admission": {
            "portfolio_epoch": "CORE-CURRENT-2026-08-14",
            "classification": "current", "lifecycle_state": "WORKING",
            "runnable": False}}}}, 200)
    with patch("modules.charlie.shadow_control_tower_input.record_shadow_proposal") as record:
        result, status = handle_shadow_control_tower_input(action(), runtime_context=AUTH,
            environ=ENV, mission_reader=reader)
    assert status == 409 and result["status"] == "shadow_control_tower_mission_not_runnable"
    assert result["dispatches"] == result["missions_created"] == result["farm_writes"] == 0
    record.assert_not_called()


def test_malformed_or_forged_runnable_admission_cannot_enter_shadow_scoring():
    for value in ("corrupt", {"runnable": True}, {"runnable": False}):
        reader = lambda mission_id, value=value: ({"mission": {"mission_id": mission_id,
            "metadata": {"portfolio_admission": value}}}, 200)
        with patch("modules.charlie.shadow_control_tower_input.record_shadow_proposal") as record:
            result, status = handle_shadow_control_tower_input(action(), runtime_context=AUTH,
                environ=ENV, mission_reader=reader)
        assert status == 409 and result["status"] == "shadow_control_tower_mission_not_runnable"
        record.assert_not_called()


def test_existing_private_tool_spine_requires_authenticated_runtime_context():
    result, status = execute_private_tool("observe_shadow_control_tower", action(), {})
    assert status == 403 and result["status"] == "shadow_control_tower_disabled"
    with patch.dict("os.environ", ENV, clear=True), \
         patch("modules.charlie.shadow_control_tower_input.get_mission") as reader, \
         patch("modules.charlie.shadow_control_tower_input.record_shadow_proposal") as record:
        reader.return_value = ({"mission": {"mission_id": "CMQ-20260813-05"}}, 200)
        record.return_value = ({"success": True, "created": True}, 201)
        result, status = execute_private_tool("observe_shadow_control_tower", action(), AUTH)
    assert status == 201 and result["created"] is True
    assert result["dispatches"] == result["farm_writes"] == 0


def test_real_private_authentication_boundary_reaches_action_without_delivery():
    with patch.dict("os.environ", AUTH_ENV, clear=True), \
         patch("modules.charlie.shadow_control_tower_input.get_mission") as reader, \
         patch("modules.charlie.shadow_control_tower_input.record_shadow_proposal") as record:
        reader.return_value = ({"mission": {"mission_id": "CMQ-20260813-05"}}, 200)
        record.return_value = ({"success": True, "created": True}, 201)
        result, status = handle_authenticated_private_action(
            action(), AUTH_PAYLOAD, AUTH_HEADERS, existing_mission_id="CMQ-20260813-05",
            environ=AUTH_ENV)
    assert status == 201 and result["created"] is True
    assert result["prompts_sent"] == result["provider_messages"] == 0


def test_forged_auth_result_and_malformed_structured_actions_are_rejected():
    forged = {"allowed": True, "reason": "owner_authenticated",
        "actor": {"id": 42}, "chat": {"id": 42}}
    assert authenticate_private_action_context(
        forged, {}, "CMQ-20260813-05", AUTH_ENV) is None
    for malformed in (["bad"], "bad", 7):
        result, status = handle_authenticated_private_action(
            malformed, AUTH_PAYLOAD, AUTH_HEADERS,
            existing_mission_id="CMQ-20260813-05", environ=AUTH_ENV)
        assert status == 400 and result["status"] == "private_action_mapping_required"
    for malformed_payload in (["bad"], "bad", 7):
        result, status = handle_authenticated_private_action(
            action(), malformed_payload, AUTH_HEADERS,
            existing_mission_id="CMQ-20260813-05", environ=AUTH_ENV)
        assert status == 403 and result["status"] == "private_action_authentication_or_mission_binding_denied"
    for malformed_headers in (["bad"], "bad", 7):
        result, status = handle_authenticated_private_action(
            action(), AUTH_PAYLOAD, malformed_headers,
            existing_mission_id="CMQ-20260813-05", environ=AUTH_ENV)
        assert status == 403 and result["status"] == "private_action_authentication_or_mission_binding_denied"
