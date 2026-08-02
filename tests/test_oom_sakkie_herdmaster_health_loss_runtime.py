from unittest.mock import patch

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_runtime import (
    _record_lifecycle_event,
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


def pig_125_evidence():
    packet = evidence()
    packet["evidence_generation"] = "GEN-125"
    packet["animals"] = [{
        "pig_id": "PIG-2026-125A", "name": "", "tag_number": "125",
        "lifecycle_status": "Active", "on_farm": True,
        "availability": "Herd", "pen": "PEN-125",
    }]
    return packet


def memory_store(active=None):
    recorded = []

    def store(action, identity, payload):
        if action == "load":
            return active
        recorded.append(payload)
        return {"success": True, "created": True}

    return store, recorded


def test_recovery_identity_distinguishes_corrected_mission_from_prior_misbound_case():
    identities = []

    def store(action, identity, payload):
        identities.append(identity)
        return {"success": True, "created": True}

    base = {
        "chat_id": "42",
        "provider_message_id": "3179",
        "mission_id": "OOM-HERDMASTER-PIG11-WRONG",
    }
    _record_lifecycle_event(base, context_store=store)
    _record_lifecycle_event(
        {**base, "mission_id": "OOM-HERDMASTER-PIG125-CORRECT"},
        context_store=store,
    )
    _record_lifecycle_event(base, context_store=store)

    assert identities[0] != identities[1]
    assert identities[0] == identities[2]


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


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.confirm_health_loss_preview")
def test_exact_natural_confirmation_records_once_and_reuses_card(confirm):
    confirm.return_value=({"success":True,"status":"health_loss_observation_recorded",
                           "writes_farm_data":True,"rows_created":1},201)
    active={"status":"preview_ready","operation_id":"HERD-1","mission_id":"MISSION-1",
            "preview":{"confirmation_ready":True},"provider_timestamp":"2026-08-02T07:10:00+00:00"}
    store,recorded=memory_store(active)
    result,status=handle_authenticated_health_loss_message(
        parsed("CONFIRM HERD-1","3173"),issue_gateway_owner_authority("42","42"),context_store=store)
    assert status==201 and result["status"]=="completed"
    assert result["card_mission_id"]=="MISSION-1" and result["rows_created"]==1
    assert "No diagnosis or treatment" in result["answer"]
    assert recorded[0]["status"]=="completed"


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


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_new_found_dead_report_does_not_reuse_another_pigs_active_lifecycle(loader):
    loader.return_value = pig_125_evidence()
    active = {"status": "waiting_for_input", "combined_text": "Pig 11 is not eating",
              "mission_id": "OOM-PIG-11", "operation_id": "HERD-11"}
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        parsed("Pig 125 is found dead in the pen.", "3179"),
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["handled"] is True
    assert result["mission_id"] != "OOM-PIG-11"
    assert recorded[0]["provider_message_id"] == "3179"
    assert recorded[0]["combined_text"] == "Pig 125 is found dead in the pen."
    assert recorded[0]["preview"]["writes_farm_data"] is False
    assert "last seen alive" in result["answer"].lower()
    assert "when was the body found" in result["answer"].lower()


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_explicit_loss_report_with_no_conclusion_cannot_become_active_case_follow_up(loader):
    loader.return_value = pig_125_evidence()
    active = {"status": "waiting_for_input", "combined_text": "Pig 11 is not eating",
              "mission_id": "OOM-PIG-11", "operation_id": "HERD-11"}
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        parsed("Pig 125 is found dead in pen. No conclusion on what it might be.", "3179"),
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["handled"] is True
    assert result["mission_id"] != "OOM-PIG-11"
    assert recorded[0]["combined_text"] == "Pig 125 is found dead in pen. No conclusion on what it might be."
    assert "Pig 11" not in recorded[0]["combined_text"]
    assert recorded[0]["preview"]["writes_farm_data"] is False


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_rootline_presence_is_not_misclassified_as_pig11_health_follow_up(loader):
    active = {"status": "waiting_for_input", "combined_text": "Pig 11 is not eating",
              "mission_id": "OOM-PIG-11"}
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        parsed("I am at the B and C valve area now, can observe both camps, and can intervene immediately for supervised commissioning.", "3181"),
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result == {"handled": False, "status": "health_loss_intake_not_applicable"}
    assert recorded == []
    loader.assert_not_called()


@patch("modules.oom_sakkie.telegram_gateway.handle_authenticated_health_loss_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
def test_existing_gateway_delivers_health_reply_through_backend_once(deliver, owner_task, health):
    deliver.return_value = {"success": True, "status": "family_message_delivered",
                            "telegram_sends": 1, "telegram_edits": 0,
                            "telegram_message_id": "4001"}
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
    assert result["reply_transport"] == "backend_handles_owner_task_delivery"
    assert result["sends_telegram"] is True
    deliver.assert_called_once()


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.confirm_health_loss_preview")
def test_completed_context_accepts_only_exact_confirmation_replay(confirm):
    confirm.return_value=({"success":True,"status":"health_loss_replayed_withheld",
                           "writes_farm_data":False,"rows_created":0},200)
    active={"status":"completed","operation_id":"HERD-1","mission_id":"MISSION-1",
            "owner_user_id":"42","preview":{"confirmation_ready":True},
            "provider_timestamp":"2026-08-02T07:10:00+00:00"}
    store,recorded=memory_store(active)
    result,status=handle_authenticated_health_loss_message(
        parsed("CONFIRM HERD-1","3174"),issue_gateway_owner_authority("42","42"),context_store=store)
    assert status==200 and result["status"]=="completed" and result["rows_created"]==0
    assert result["mission_id"]=="MISSION-1" and result["card_mission_id"]=="MISSION-1"
    assert len(recorded)==1
    confirm.assert_called_once()

    unrelated,status=handle_authenticated_health_loss_message(
        parsed("yes she can stand","3175"),issue_gateway_owner_authority("42","42"),context_store=store)
    assert status==200 and unrelated["handled"] is False
