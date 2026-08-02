from unittest.mock import patch

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_runtime import (
    handle_authenticated_health_loss_message,
)
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message


def parsed(text, message_id="3169"):
    return {
        "text": text,
        "telegram_user_id": "42",
        "telegram_chat_id": "42",
        "provider_message_id": message_id,
        "provider_timestamp": "2026-08-02T07:07:57+00:00",
    }


def evidence():
    return {
        "evidence_generation": "GEN-11",
        "as_of_timestamp": "2026-08-02T07:08:00+00:00",
        "animals": [{
            "pig_id": "PIG-2026-E88A", "name": "", "tag_number": "11",
            "lifecycle_status": "Active", "on_farm": True,
            "availability": "Sale", "pen": "PEN-016",
        }],
        "matings": [],
        "litters": [],
    }


def memory_store(active=None):
    recorded = []

    def store(action, identity, payload):
        if action == "load":
            return active
        recorded.append(payload)
        return {"success": True, "created": True}

    return store, recorded


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_pig_11_report_is_acknowledged_and_asks_only_current_welfare_question(loader):
    loader.return_value = evidence()
    store, recorded = memory_store()
    result, status = handle_authenticated_health_loss_message(
        parsed("Pig 11 is not eating, just laying down"),
        issue_gateway_owner_authority("42", "42"),
        context_store=store,
    )
    assert status == 200
    assert result["status"] == "waiting_for_input"
    assert result["tool_used"] == "herdmaster_health_loss_preview"
    assert "PIG 11 NEEDS CHECKING" in result["answer"]
    assert "able to stand, breathe normally and drink water" in result["answer"]
    assert result["writes_farm_data"] is False
    assert recorded[0]["provider_message_id"] == "3169"


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_follow_up_reuses_open_context_without_repeating_known_report(loader):
    loader.return_value = evidence()
    active = {
        "status": "waiting_for_input",
        "combined_text": "Pig 11 is not eating, just laying down",
    }
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        parsed("She can stand, is breathing normally and is drinking water", "3170"),
        issue_gateway_owner_authority("42", "42"),
        context_store=store,
    )
    assert status == 200
    assert result["status"] == "preview_ready"
    assert result["question_count"] == 0
    assert "HERDMASTER PREVIEW READY" in result["answer"]
    assert "not eating" in recorded[0]["combined_text"]
    assert "drinking water" in recorded[0]["combined_text"]


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_unrelated_owner_message_is_not_claimed(loader):
    store, _recorded = memory_store()
    result, status = handle_authenticated_health_loss_message(
        parsed("Reservoir is three quarters"),
        issue_gateway_owner_authority("42", "42"),
        context_store=store,
    )
    assert status == 200
    assert result["handled"] is False
    loader.assert_not_called()


@patch("modules.oom_sakkie.telegram_gateway.handle_authenticated_health_loss_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
def test_existing_gateway_returns_health_reply_through_caller_transport(owner_task, health):
    owner_task.return_value = ({"handled": False}, 200)
    health.return_value = ({
        "handled": True, "success": True, "status": "waiting_for_input",
        "answer": "🚨 <b>PIG 11 NEEDS CHECKING</b>",
        "records_audit_trace": True,
    }, 200)
    env = {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x" * 40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42",
    }
    payload = {"message": {
        "message_id": 3169, "date": 1785654477,
        "text": "Pig 11 is not eating, just laying down",
        "from": {"id": 42}, "chat": {"id": 42, "type": "private"},
    }}
    result, status = handle_telegram_gateway_message(
        payload, headers={"Authorization": "Bearer " + "x" * 40}, environ=env,
    )
    assert status == 200
    assert result["answer"].startswith("🚨")
    assert result["reply"]["text"] == result["answer"]
    assert result["reply"]["parse_mode"] == "HTML"
    assert result["reply_transport"] == "caller_handles_telegram_send"
