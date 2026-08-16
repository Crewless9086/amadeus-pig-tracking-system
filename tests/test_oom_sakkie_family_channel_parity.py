import json
from unittest.mock import patch

from modules.oom_sakkie.telegram_direct import handle_telegram_direct_webhook
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message


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
