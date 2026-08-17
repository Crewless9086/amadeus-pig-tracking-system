from datetime import datetime, timezone
from unittest.mock import patch

from modules.oom_sakkie.beacon_request_runtime import (
    build_protected_campaign_package, build_sale_ready_demand_proposal,
    build_litter_media_choice, prepare_campaign_owner_card, select_litter_story_media,
)
from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input


def opportunity():
    return {"success": True, "generated_at": "2026-08-17T08:00:00+00:00", "cards": [{
        "card_id": "STOCK-1", "lane": "live_stock", "status": "ready_for_owner_review",
        "category": "livestock", "unit": "animals", "blockers": [],
        "capacity_calculation": {"demand_cap": 3, "eligible_categories": ["Weaner Piglets"]},
        "freshness": {"fresh": True},
        "provenance": {"observed_at": "2026-08-17T08:00:00+00:00"}}]}


def packet():
    value = build_sale_ready_demand_proposal(opportunity(), {"success": True, "items": []})
    return build_protected_campaign_package(value,
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))


def fake_claim(**kwargs):
    return {"callback_token": "opaque-token", "preview_digest": "d" * 64, **kwargs}


def test_owner_card_is_compact_nonduplicative_and_has_real_callbacks():
    value = prepare_campaign_owner_card(packet(), owner_user_id="42", private_chat_id="42",
        provider_message_id="scheduled:case:G11", packet_generation="G11", claim_creator=fake_claim)
    copy = value["campaign_review_preview"]["exact_post_copy"]
    assert len(value["answer"]) < 1800
    assert value["answer"].count(copy) == 1
    assert "Attribution:" not in value["answer"] and "Rollback" not in value["answer"]
    buttons = [b for row in value["reply_markup"]["inline_keyboard"] for b in row]
    assert [b["text"] for b in buttons] == ["Approve", "Correct", "Decline", "Details"]
    assert [b["callback_data"] for b in buttons] == [
        "oompa:opaque-token:confirm", "oompa:opaque-token:change",
        "oompa:opaque-token:cancel", "oompa:opaque-token:details"]
    preview = value["campaign_review_preview"]
    assert preview["packet_id"] and preview["packet_generation"]
    assert preview["campaign_digest"] and preview["stop_conditions"] and preview["rollback"]


def test_litter_card_asks_use_these_photos_with_review_change_and_no_media_controls():
    value_packet = packet()
    value_packet["litter_media_selection"] = select_litter_story_media(
        {"success": True, "items": [media_item()]}, litter_id="LITTER-7",
        pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7")
    value = prepare_campaign_owner_card(value_packet, owner_user_id="42", private_chat_id="42",
        provider_message_id="scheduled:case:G11", packet_generation="G11", claim_creator=fake_claim)
    assert "Use these photos?" in value["answer"]
    assert "ASSET-1" in value["answer"] and "2026-08-16" in value["answer"]
    labels = [b["text"] for row in value["reply_markup"]["inline_keyboard"] for b in row]
    assert "Review photos" in labels and "Select/change" in labels and "No media" in labels


def test_litter_story_queries_library_and_wires_media_into_real_packet():
    stock = opportunity()
    stock["cards"][0]["story_context"] = {"kind": "litter", "subject": "Litter 7 first week",
        "litter_id": "LITTER-7", "pig_ids": ["PIG-1", "PIG-2"], "event_id": "EVENT-7"}
    value = build_sale_ready_demand_proposal(stock, {"success": True, "items": [media_item()]})
    assert value["story_subject"] == "Litter 7 first week"
    assert value["litter_media_selection"][0]["asset_id"] == "ASSET-1"
    protected = build_protected_campaign_package(value,
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
    assert [item["asset_id"] for item in protected["protected_campaign_package"]["selected_approved_media"]] == ["ASSET-1"]
    card = prepare_campaign_owner_card(protected, owner_user_id="42", private_chat_id="42",
        provider_message_id="scheduled:case:G11", packet_generation="G11", claim_creator=fake_claim)
    assert "<b>Story:</b> Litter 7 first week" in card["answer"]
    assert "Use these photos?" in card["answer"]


def test_litter_story_without_eligible_media_delivers_one_precise_request():
    stock = opportunity()
    stock["cards"][0]["story_context"] = {"kind": "litter", "subject": "Litter 7 first week",
        "litter_id": "LITTER-7", "pig_ids": ["PIG-1", "PIG-2"], "event_id": "EVENT-7"}
    value = build_sale_ready_demand_proposal(stock, {"success": True, "items": [media_item(public=None)]})
    assert value["precise_media_request"].startswith("Please send one current portrait photo")
    protected = build_protected_campaign_package(value,
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
    card = prepare_campaign_owner_card(protected, owner_user_id="42", private_chat_id="42",
        provider_message_id="scheduled:case:G11", packet_generation="G11", claim_creator=fake_claim)
    assert card["answer"].count("Please send one current portrait photo") == 1


def media_item(public=True, linked=True):
    return {"binary_asset_id": "ASSET-1", "thumbnail_url": "https://private/thumb/1",
        "content_sha256": "a" * 64, "latest_library_event": "library_accepted",
        "effective_public_use_approved": public,
        "current_library_accept_event_id": "LIB-1", "current_public_use_event_id": "PUB-1",
        "private_storage_proof_id": "STORE-1", "source": "telegram_private_intake",
        "observation": {"litter_id": "LITTER-7" if linked else "LITTER-X",
            "pig_ids": ["PIG-1", "PIG-2"], "event_id": "EVENT-7",
            "captured_at": "2026-08-16", "source": "Charl Telegram intake"}}


def test_litter_media_requires_exact_linkage_and_positive_public_use():
    payload = {"success": True, "items": [media_item(), media_item(linked=False), media_item(public=None)]}
    selected = select_litter_story_media(payload, litter_id="LITTER-7",
        pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7")
    assert len(selected) == 1
    assert selected[0]["asset_id"] == "ASSET-1"
    assert selected[0]["capture_date"] == "2026-08-16"
    assert selected[0]["public_use_authority"] == "approved"


def test_litter_media_no_eligible_result_supports_one_precise_request():
    choice = build_litter_media_choice({"success": True, "items": [media_item(public=None)]},
        litter_id="LITTER-7", pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7",
        subject="the Litter 7 piglets")
    assert choice["selected"] == [] and choice["status"] == "precise_media_request"
    assert choice["request"].startswith("Please send one current portrait photo")


def test_litter_media_rejects_extra_or_missing_pig_linkage_and_missing_asset_identity():
    extra = media_item(); extra["observation"]["pig_ids"].append("PIG-3")
    missing_id = media_item(); missing_id["binary_asset_id"] = ""
    assert select_litter_story_media({"success": True, "items": [extra, missing_id]},
        litter_id="LITTER-7", pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7") == []


def parsed(owner="42", card="900"):
    return {"telegram_user_id": owner, "telegram_chat_id": owner,
        "provider_message_id": "CB-1", "provider_timestamp": "2026-08-17T12:00:00+00:00",
        "reply_to_message_id": card, "callback_data": "oompa:opaque-token:confirm"}


@patch("modules.oom_sakkie.protected_action_runtime.validates_gateway_owner_authority", return_value=True)
@patch("modules.oom_sakkie.protected_action_runtime.claim_callback")
def test_forged_stale_expired_wrong_owner_are_rejected_without_effect(claim, _authority):
    for status in ("protected_callback_invalid", "protected_callback_stale",
                   "protected_callback_expired", "protected_callback_unauthorized"):
        claim.return_value = ({"success": False, "status": status}, 409)
        result, code = handle_protected_action_input(parsed(), object())
        assert code == 409 and result["status"] == status
        assert result["writes_farm_data"] is False


@patch("modules.oom_sakkie.protected_action_runtime.validates_gateway_owner_authority", return_value=True)
@patch("modules.oom_sakkie.protected_action_runtime.claim_callback")
def test_completed_callback_replay_is_silent(claim, _authority):
    claim.return_value = ({"success": True, "status": "protected_callback_replayed_noop",
        "telegram_sends": 0, "telegram_edits": 0}, 200)
    result, code = handle_protected_action_input(parsed(), object())
    assert code == 200 and result["suppress_owner_delivery"] is True
    assert result["telegram_sends"] == 0


@patch("modules.oom_sakkie.protected_action_runtime.validates_gateway_owner_authority", return_value=True)
@patch("modules.oom_sakkie.protected_action_runtime.complete_claim")
@patch("modules.oom_sakkie.protected_action_runtime.claim_callback")
def test_concurrent_recovered_approval_loser_is_silent(claim, complete, _authority):
    preview = prepare_campaign_owner_card(packet(), owner_user_id="42", private_chat_id="42",
        provider_message_id="scheduled:case:G11", packet_generation="G11",
        claim_creator=fake_claim)["campaign_review_preview"]
    claim.return_value = ({"success": True, "status": "protected_callback_recovered",
        "callback_token": "opaque-token", "action_kind": "beacon_campaign_review",
        "mission_id": "M", "preview_digest": "d" * 64,
        "evidence_generation": preview["campaign_digest"], "preview_payload": preview}, 200)
    complete.return_value = {"completed": False, "replayed": True,
        "result": {"status": "beacon_campaign_review_approved"}}
    result, code = handle_protected_action_input(parsed(), object())
    assert code == 200 and result["status"] == "protected_callback_replayed_noop"
    assert result["suppress_owner_delivery"] is True and result["telegram_sends"] == 0
