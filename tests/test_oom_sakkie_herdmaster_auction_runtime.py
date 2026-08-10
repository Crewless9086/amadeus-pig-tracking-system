from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_auction_runtime import (
    CONFIRMATION_TOKEN, EVIDENCE_GENERATION, MISSION_ID, OPERATION_ID,
    PREVIEW_HASH, frozen_preview_result, handle_auction_confirmation,
    present_frozen_preview,
)


def parsed(text=CONFIRMATION_TOKEN, message_id="9001"):
    return {"text": text, "telegram_user_id": "5721652188",
        "telegram_chat_id": "5721652188", "telegram_chat_type": "private",
        "provider_message_id": message_id,
        "provider_timestamp": "2026-08-10T12:00:00Z"}


def events(*extra):
    return [{"task_state": "waiting_for_confirmation",
        "preview_hash": PREVIEW_HASH, "operation_id": OPERATION_ID,
        "evidence_generation": EVIDENCE_GENERATION,
        "owner_user_id": "5721652188", "chat_id": "5721652188",
        "delivery_provider_timestamp": "2026-08-10T11:59:00Z",
        "state": "delivered"}, *extra]


def store(rows):
    return lambda action, identity, payload: rows if action == "load" else {"created": True}


def writer_result(*args, **kwargs):
    assert kwargs["authority_verifier"](kwargs["authority"])
    return {"success": True, "status": "auction_sale_recorded",
        "rows_created": 37, "replay": False}, 201


def test_frozen_preview_is_exact_protected_zero_write_contract():
    result = frozen_preview_result()
    assert result["status"] == "waiting_for_confirmation"
    assert result["preview_hash"] == PREVIEW_HASH
    assert result["operation_id"] == OPERATION_ID
    assert result["writes_farm_data"] is False
    assert "R4,470.51" in result["answer"]
    assert "V10/V11 membership: Unknown" in result["answer"]
    assert CONFIRMATION_TOKEN in result["answer"]


def test_exact_authenticated_confirmation_records_once_and_completes_visibly():
    authority = issue_gateway_owner_authority("5721652188", "5721652188")
    result, status = handle_auction_confirmation(parsed(), authority,
        event_store=store(events()), evidence_loader=lambda: {}, writer=writer_result)
    assert status == 201
    assert result["status"] == "completed"
    assert result["writes_farm_data"] is True
    assert result["rows_created"] == 37
    assert result["owner_visible_completion_policy"] == "verified_edit_or_new_message"


def test_replay_is_silent_and_never_calls_writer():
    authority = issue_gateway_owner_authority("5721652188", "5721652188")
    rows = events({"confirmation_provider_message_id": "9001", "task_state": "completed",
                   "state": "notification_delivered", "owner_user_id": "5721652188",
                   "chat_id": "5721652188",
                   "confirmation_provider_timestamp": "2026-08-10T12:00:00Z",
                   "confirmation_text_sha256": __import__("hashlib").sha256(
                       CONFIRMATION_TOKEN.encode()).hexdigest()})
    result, status = handle_auction_confirmation(parsed(), authority,
        event_store=store(rows), writer=lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert status == 200
    assert result["status"] == "auction_confirmation_replayed_zero_effect"
    assert result["suppress_owner_delivery"] is True
    assert result["writes_farm_data"] is False


def test_wrong_preview_missing_parent_and_unauthenticated_fail_closed():
    authority = issue_gateway_owner_authority("5721652188", "5721652188")
    unrelated, _ = handle_auction_confirmation(parsed("What is today's plan?"), authority)
    assert unrelated["handled"] is False
    missing, status = handle_auction_confirmation(parsed(), authority, event_store=store([]))
    assert status == 409 and missing["writes_farm_data"] is False
    denied, status = handle_auction_confirmation(parsed(), None, event_store=store(events()))
    assert status == 403 and denied["writes_farm_data"] is False


def test_stale_or_cross_owner_confirmation_cannot_write():
    authority = issue_gateway_owner_authority("5721652188", "5721652188")
    stale = parsed()
    stale["provider_timestamp"] = "2026-08-10T11:58:00Z"
    result, status = handle_auction_confirmation(stale, authority, event_store=store(events()))
    assert status == 409 and result["status"] == "auction_confirmation_chronology_conflict"
    wrong_owner = events()[0] | {"owner_user_id": "other"}
    result, status = handle_auction_confirmation(parsed(), authority,
        event_store=store([wrong_owner]))
    assert status == 403 and result["writes_farm_data"] is False


def test_superseded_preview_and_ambiguous_completion_recovery_are_safe():
    authority = issue_gateway_owner_authority("5721652188", "5721652188")
    superseded = events({"task_state": "contained", "state": "updated",
                         "owner_user_id": "5721652188", "chat_id": "5721652188"})
    result, status = handle_auction_confirmation(parsed(), authority,
        event_store=store(superseded), writer=lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert status == 409 and result["status"] == "auction_confirmation_active_preview_required"
    ambiguous = events({"task_state": "completed", "state": "contained",
        "confirmation_provider_message_id": "9001", "owner_user_id": "5721652188",
        "chat_id": "5721652188",
        "confirmation_provider_timestamp": "2026-08-10T12:00:00Z",
        "confirmation_text_sha256": __import__("hashlib").sha256(
            CONFIRMATION_TOKEN.encode()).hexdigest()})
    result, status = handle_auction_confirmation(parsed(), authority,
        event_store=store(ambiguous), writer=lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert status == 200 and result["suppress_owner_delivery"] is True
    assert result["writes_farm_data"] is False


def test_authorized_preview_presentation_confirmation_completion_and_replay_journey():
    rows, sends = [], []
    def lifecycle_store(action, identity, payload):
        if action == "load":
            return list(rows)
        if any(row.get("event_id") == identity for row in rows):
            return {"created": False}
        rows.append(dict(payload))
        return {"created": True, "success": True}
    def sender(chat_id, text):
        sends.append((chat_id, text))
        return {"success": True, "telegram_message_id": str(8000 + len(sends)),
                "provider_timestamp": "2026-08-10T11:59:00Z"}
    from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
    authority = issue_gateway_owner_authority("5721652188", "5721652188")
    presented = present_frozen_preview(authority,
        trigger_timestamp="2026-08-10T11:58:00Z",
        family_delivery=lambda p, r, **kw: deliver_family_result(
            p, r, event_store=lifecycle_store, sender=sender, **kw))
    assert presented["telegram_sends"] == 1
    result, status = handle_auction_confirmation(parsed(), authority,
        event_store=lifecycle_store, evidence_loader=lambda: {}, writer=writer_result)
    assert status == 201 and result["status"] == "completed"
    completed = deliver_family_result(parsed(), result, specialist="HERDMASTER",
        mission_id=MISSION_ID, card_mission_id=MISSION_ID,
        event_store=lifecycle_store,
        editor=lambda *a: {"success": True, "telegram_message_id": "8001"}, sender=sender)
    assert completed["telegram_sends"] == 0 and completed["telegram_edits"] == 1
    replay, status = handle_auction_confirmation(parsed(), authority,
        event_store=lifecycle_store, writer=lambda *a, **k: (_ for _ in ()).throw(AssertionError()))
    assert status == 200 and replay["suppress_owner_delivery"] is True
    assert len(sends) == 1
