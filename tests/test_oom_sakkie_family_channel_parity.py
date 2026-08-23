import json
from unittest.mock import patch
import pytest

from modules.oom_sakkie.telegram_direct import handle_telegram_direct_webhook
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
from modules.oom_sakkie.telegram_gateway import parse_telegram_gateway_payload


OWNER = "9001"
ANTON = "9002"
SECRET = "family-direct-secret-value-32-characters"
TOKEN = "family-gateway-token-value-32-characters"


def binding():
    return {"telegram_user_id": ANTON, "role": "farm_manager", "family_key": "dad",
        "permissions": ["explicit_summary", "farm_observation", "active_follow_up",
            "irrigation_start", "irrigation_continue"],
        "summary_domains": ["water", "weather", "irrigation", "herd", "welfare"],
        "language": "af", "authorization_id": "AUTH-ANTON",
        "authorized_by_user_id": OWNER, "authorized_at": "2026-08-15T08:00:00+02:00"}


def env():
    return {"OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": OWNER,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": f"{OWNER},{ANTON}",
        "OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON": json.dumps([binding()]),
        "OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_BOT_TOKEN": "123456789:" + "x" * 40,
        "OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET": SECRET,
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": TOKEN}


def payload(text="Hoe lyk die weer?"):
    return {"update_id": 7001, "message": {"message_id": 7002,
        "date": 1786880000, "text": text, "from": {"id": int(ANTON)},
        "chat": {"id": int(ANTON), "type": "private"}}}


def callback(data):
    return {"update_id": 7100, "callback_query": {"id": "CB-1", "data": data,
        "from": {"id": int(ANTON)}, "message": {"message_id": 7101,
            "chat": {"id": int(ANTON), "type": "private"}}}}


@patch("modules.oom_sakkie.telegram_direct.deliver_family_result")
@patch("modules.oom_sakkie.telegram_direct.load_family_summary")
def test_direct_text_preserves_farm_manager_principal_and_matches_gateway_authorization(summary, deliver):
    summary.return_value = {"available": True, "summary_lines": ["Weerbewyse: fresh"]}
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    direct, direct_status = handle_telegram_direct_webhook(payload(),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert direct_status == 200 and direct["family_role"] == "farm_manager"
    assert direct["language"] == "af" and direct["message"]["capability"] == "explicit_summary"
    assert direct["message"]["summary_domain"] == "weather"
    assert direct["authorization_id"] == "AUTH-ANTON"
    assert direct["writes"] is False and direct["hardware_commands"] == 0
    assert deliver.call_count == 1


@patch("modules.oom_sakkie.telegram_direct.deliver_family_result")
def test_direct_unclassified_manager_text_asks_precise_question_without_owner_fallback(deliver):
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    with patch("modules.oom_sakkie.telegram_direct.handle_owner_task_input") as owner_handler, \
            patch("modules.oom_sakkie.telegram_direct.handle_message") as generic:
        result, status = handle_telegram_direct_webhook(payload("Wat kort my aandag?"),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 200 and result["status"] == "family_clarification_required"
    assert result["answer"].count("?") == 1 and result["language"] == "af"
    assert result["records_audit_trace"] is False
    owner_handler.assert_not_called(); generic.assert_not_called()


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.load_family_summary")
def test_gateway_and_direct_select_same_role_capability_domain(summary, deliver):
    summary.return_value = {"available": True, "summary_lines": ["Weerbewyse: fresh"]}
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    gateway, status = handle_telegram_gateway_message(payload(),
        headers={"Authorization": "Bearer " + TOKEN}, environ=env())
    assert status == 200
    assert gateway["message"]["family_role"] == "farm_manager"
    assert gateway["message"]["capability"] == "explicit_summary"
    assert gateway["message"]["summary_domain"] == "weather"
    assert gateway["message"]["authorization_id"] == "AUTH-ANTON"


@patch("modules.oom_sakkie.telegram_gateway.handle_family_runtime_message")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_authenticated_health_loss_message")
def test_gateway_routes_manager_afrikaans_mortality_through_shared_operational_lifecycle(
        health, deliver, family_runtime):
    health.return_value = ({"handled": True, "success": True,
        "status": "waiting_for_input", "answer": "Een vraag: Op watter datum?",
        "records_audit_trace": True, "writes_farm_data": False}, 200)
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    result, status = handle_telegram_gateway_message(
        payload("Vark 126 is dood, ons het hom verwyder en begrawe."),
        headers={"Authorization": "Bearer " + TOKEN}, environ=env())
    assert status == 200 and result["message"]["status"] == "waiting_for_input"
    inbound = health.call_args.args[0]
    assert inbound["output_language"] == "af"
    assert inbound["text"].startswith("Vark 126 is dood")
    family_runtime.assert_not_called()


@patch("modules.oom_sakkie.telegram_gateway.handle_family_runtime_message")
@patch("modules.oom_sakkie.telegram_gateway.herdmaster_family_observation")
@patch("modules.oom_sakkie.telegram_gateway.handle_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_authenticated_health_loss_message")
def test_manager_can_never_fall_back_to_legacy_observation_only_mortality_branch(
        health, deliver, owner_task, generic_core_or_charlie, legacy_observation, family_runtime):
    health.return_value = ({"handled": False, "status": "health_loss_intake_not_applicable"}, 200)
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0}
    def invoke_selected_adapter(parsed, principal, *, observation_adapter, **_kwargs):
        return observation_adapter(parsed=parsed, principal=principal,
            capability="found_dead_observation", replay_identity="manager-fallback"), 200
    family_runtime.side_effect = invoke_selected_adapter
    manager_env = env()
    manager_binding = binding()
    manager_binding["permissions"] += ["found_dead_observation", "mortality_confirmation"]
    manager_env["OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON"] = json.dumps([manager_binding])
    result, status = handle_telegram_gateway_message(
        payload("Vark 126 is dood, ons het hom verwyder en begrawe."),
        headers={"Authorization": "Bearer " + TOKEN}, environ=manager_env)
    assert status == 200
    assert result["message"]["status"] == "farm_manager_operational_clarification_required"
    assert result["message"]["legacy_observation_path_used"] is False
    assert "Charl se afsonderlike bevestiging" not in result["answer"]
    legacy_observation.assert_not_called()
    generic_core_or_charlie.assert_not_called()
    owner_task.assert_not_called()


@pytest.mark.parametrize("request_text", [
    "CORE, verander die produksiekode en ontplooi dit nou.",
    "CHARLIE, begin 'n ontwikkelingstaak en stuur dit aan die agent.",
])
@patch("modules.oom_sakkie.telegram_gateway.handle_family_runtime_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
def test_manager_core_and_charlie_requests_have_zero_dispatch_or_owner_task_effects(
        deliver, owner_task, generic, family_runtime, request_text):
    family_runtime.return_value = ({"success": False,
        "status": "family_private_capability_denied", "answer": "",
        "writes_farm_data": False, "hardware_commands": 0}, 403)
    result, status = handle_telegram_gateway_message(payload(request_text),
        headers={"Authorization": "Bearer " + TOKEN}, environ=env())
    assert status == 403
    assert result["writes"] is False and result["hardware_commands"] == 0
    assert result["sends_telegram"] is False
    owner_task.assert_not_called()
    generic.assert_not_called()
    deliver.assert_not_called()


def test_family_principals_cannot_enter_sam_owner_callbacks_or_owner_media():
    with patch("modules.oom_sakkie.telegram_direct.process_owner_attention_callback") as attention, \
            patch("modules.oom_sakkie.telegram_direct.process_sam_live_stock_owner_callback") as sam:
        result, status = handle_telegram_direct_webhook(callback("sam_live_owner_decision:x"),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 403 and result["status"] == "telegram_user_not_allowed"
    attention.assert_not_called(); sam.assert_not_called()
    media = payload("")
    media["message"].pop("text")
    media["message"]["photo"] = [{"file_id": "FILE", "file_unique_id": "UNIQUE",
                                    "width": 10, "height": 10}]
    with patch("modules.oom_sakkie.telegram_direct.handle_telegram_media_intake") as intake:
        result, status = handle_telegram_direct_webhook(media,
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 403 and result["status"] == "telegram_user_not_allowed"
    intake.assert_not_called()


def test_sam_callback_requires_exact_private_owner_chat():
    owner_env = env(); owner_env["OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS"] = f"{OWNER},{ANTON}"
    item = callback("sam_live_owner_decision:x")
    item["callback_query"]["from"]["id"] = int(OWNER)
    item["callback_query"]["message"]["chat"]["id"] = 9999
    with patch("modules.oom_sakkie.telegram_direct.process_owner_attention_callback") as attention:
        result, status = handle_telegram_direct_webhook(item,
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=owner_env)
    assert status == 403 and result["status"] == "telegram_user_not_allowed"
    attention.assert_not_called()


def test_owner_text_requires_exact_private_chat_before_owner_handlers():
    owner_env = env()
    for chat_id, chat_type in ((9999, "private"), (int(OWNER), "group")):
        item = payload("Wat kort aandag?")
        item["message"]["from"]["id"] = int(OWNER)
        item["message"]["chat"] = {"id": chat_id, "type": chat_type}
        with patch("modules.oom_sakkie.telegram_direct.handle_owner_task_input") as owner_handler, \
                patch("modules.oom_sakkie.telegram_direct.handle_message") as generic:
            result, status = handle_telegram_direct_webhook(item,
                headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=owner_env)
        assert status == 403 and result["status"] == "telegram_family_identity_not_authorized"
        owner_handler.assert_not_called(); generic.assert_not_called()


@patch("modules.oom_sakkie.telegram_direct.acknowledge_telegram_callback")
@patch("modules.oom_sakkie.telegram_direct.handle_family_rootline_callback")
def test_direct_delegated_callback_resolves_anton_and_acknowledges_once(handler, acknowledge):
    handler.return_value = ({"success": True, "status": "delegated_callback_retained",
        "answer": "", "hardware_commands": 0, "suppress_family_delivery": True}, 200)
    acknowledge.return_value = ({"success": True, "status": "telegram_callback_acknowledged"}, 200)
    result, status = handle_telegram_direct_webhook(callback("oomfm:TOKEN:confirm"),
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 200 and result["status"] == "delegated_callback_retained"
    assert handler.call_count == 1 and handler.call_args.args[1].role.value == "farm_manager"
    acknowledge.assert_called_once()


@patch("modules.oom_sakkie.telegram_direct.acknowledge_telegram_callback")
@patch("modules.oom_sakkie.telegram_direct.handle_family_rootline_callback")
def test_family_callback_wrong_chat_or_antoinette_never_reaches_contract(handler, acknowledge):
    acknowledge.return_value = ({"success": True}, 200)
    bad = callback("oomfm:TOKEN:confirm")
    bad["callback_query"]["message"]["chat"]["id"] = 9999
    result, status = handle_telegram_direct_webhook(bad,
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 403 and result["status"] == "family_rootline_callback_unauthorized"
    handler.assert_not_called(); acknowledge.assert_called_once()


@patch("modules.oom_sakkie.family_rootline_callback.bind_claim_card", return_value=True)
@patch("modules.oom_sakkie.telegram_direct.deliver_family_result")
def test_direct_webhook_derives_zero_effect_rootline_preview_and_binds_card(deliver, _bind):
    from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
    auth = {"active": True, "revoked_at": None, "owner_authority": False,
        "principal_id": ANTON, "private_chat_id": ANTON, "role": "farm_manager",
        "capabilities": ["routine_irrigation_execute"], "zones": ["B"],
        "commissioned_paths": ["PATH-B"], "authorization_digest": "a" * 64}
    eligibility = {"status": "execution_eligible", "zone_id": "B",
        "commissioned_path_id": "PATH-B", "maximum_duration_seconds": 300,
        "plan_generation": "GEN-1", "job_id": "JOB-1", "job_sha256": "b" * 64,
        "segment_identity": "SEG-1", "current_segment": 1, "execution_id": "EX-1",
        "eligibility_sha256": "c" * 64, "consumption_key": "CONSUME-1"}
    deliver.return_value = {"success": True, "telegram_sends": 1, "telegram_edits": 0,
                            "provider_message_id": "CARD-1"}
    def claim(**kwargs):
        return {"success": True, "callback_token": "TOKEN",
            "preview_digest": canonical_preview_digest("rootline_delegated_family",
                                                        kwargs["preview_payload"])}
    with patch("modules.telemetry.rootline_delegated_principal.load_delegated_authorization",
               return_value=auth), \
            patch("modules.oom_sakkie.family_specialist_adapters._load_rootline_eligibility",
                  return_value=eligibility), \
            patch("modules.telemetry.rootline_execution_authority.validate_execution_eligibility",
                  return_value=eligibility), \
            patch("modules.oom_sakkie.family_rootline_callback.create_claim", side_effect=claim), \
            patch("modules.oom_sakkie.telegram_direct.family_replay_store",
                  return_value={"success": True, "created": True}):
        result, status = handle_telegram_direct_webhook(payload("Begin besproeiing"),
            headers={"X-Telegram-Bot-Api-Secret-Token": SECRET}, environ=env())
    assert status == 200 and result["message"]["status"] == "family_rootline_preview_ready"
    assert result["preview_card_bound"] is True
    assert result["hardware_commands"] == 0 and result["writes"] is False


def test_gateway_callback_uses_authenticated_receipt_time_not_old_card_time():
    item = callback("oomfm:TOKEN:confirm")
    item["callback_query"]["message"]["date"] = 1_700_000_000
    parsed = parse_telegram_gateway_payload(item)
    assert parsed["source_card_timestamp"].startswith("2023-")
    assert parsed["provider_timestamp"] != parsed["source_card_timestamp"]
    assert parsed["provider_message_id"] == "CB-1"
    assert parsed["reply_to_message_id"] == "7101"
    assert parsed["callback_query_id"] == "CB-1"
