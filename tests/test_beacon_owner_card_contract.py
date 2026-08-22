from datetime import datetime, timezone
from unittest.mock import patch

from modules.oom_sakkie.beacon_request_runtime import (
    build_litter_awareness_story_proposal, build_protected_campaign_package,
    build_sale_ready_demand_proposal, build_live_stock_awareness_proposal,
    build_litter_media_choice, prepare_campaign_owner_card, select_litter_story_media,
)
from modules.oom_sakkie.protected_action_runtime import handle_protected_action_input


def opportunity():
    return {"success": True, "generated_at": "2026-08-17T08:00:00+00:00", "cards": [{
        "card_id": "STOCK-1", "lane": "live_stock", "status": "ready_for_owner_review",
        "category": "livestock", "unit": "animals", "blockers": [],
        "capacity_calculation": {"demand_cap": 3, "eligible_categories": ["Weaner Piglets"]},
        "freshness": {"fresh": True},
        "provenance": {"observed_at": "2026-08-17T08:00:00+00:00"},
        "story_context": {"kind": "litter", "subject": "internal",
            "litter_id": "LITTER-7", "pig_ids": ["PIG-1", "PIG-2"],
            "event_id": "EVENT-7"}}]}


def litters(name="Molly"):
    return {"success": True, "litters": [{"litter_id": "LITTER-7", "sow_name": name}]}


def packet():
    value = build_litter_awareness_story_proposal(
        opportunity(), litters(), {"success": True, "items": [media_item()]})
    return build_protected_campaign_package(value,
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))


def fake_claim(**kwargs):
    return {"callback_token": "opaque-token", "preview_digest": "d" * 64, **kwargs}


def owner_card(value):
    return prepare_campaign_owner_card(value, owner_user_id="42", private_chat_id="42",
        provider_message_id="scheduled:case:G11", packet_generation="G11",
        target_page_id="PAGE-1", claim_creator=fake_claim)


def test_owner_card_is_compact_nonduplicative_and_has_real_callbacks():
    value = owner_card(packet())
    copy = value["campaign_review_preview"]["exact_post_copy"]
    assert len(value["answer"]) < 1800
    assert value["answer"].count(copy) == 1
    assert "Attribution:" not in value["answer"] and "Rollback" not in value["answer"]
    buttons = [b for row in value["reply_markup"]["inline_keyboard"] for b in row]
    assert [b["text"] for b in buttons] == ["Approve", "Correct", "Decline"]
    assert [b["callback_data"] for b in buttons] == [
        "oompa:opaque-token:confirm", "oompa:opaque-token:change",
        "oompa:opaque-token:cancel"]
    preview = value["campaign_review_preview"]
    assert preview["packet_id"] and preview["packet_generation"]
    assert preview["campaign_digest"] and preview["stop_conditions"] and preview["rollback"]
    assert preview["target_page_id"] == "PAGE-1"
    assert "Facebook Page ID:</b> PAGE-1" in value["answer"]
    assert "ZAR 0.00 total" in value["answer"] and "0 days; no boost" in value["answer"]
    assert "no automatic retry" in value["answer"]


def test_litter_card_shows_exact_photos_with_only_protected_decision_controls():
    value_packet = packet()
    value_packet["litter_media_selection"] = select_litter_story_media(
        {"success": True, "items": [media_item()]}, litter_id="LITTER-7",
        pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7")
    value = owner_card(value_packet)
    assert "Pictures:" in value["answer"]
    assert "ASSET-1" in value["answer"] and "2026-08-16" in value["answer"]
    labels = [b["text"] for row in value["reply_markup"]["inline_keyboard"] for b in row]
    assert labels == ["Approve", "Correct", "Decline"]


def test_litter_story_queries_library_and_wires_media_into_real_packet():
    value = build_litter_awareness_story_proposal(
        opportunity(), litters(), {"success": True, "items": [media_item()]})
    assert value["story_subject"] == "Molly and her piglets"
    assert "LITTER-7" not in value["draft_caption"]
    assert value["litter_media_selection"][0]["asset_id"] == "ASSET-1"
    protected = build_protected_campaign_package(value,
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
    assert [item["asset_id"] for item in protected["protected_campaign_package"]["selected_approved_media"]] == ["ASSET-1"]
    card = owner_card(protected)
    assert "<b>Story:</b> Molly and her piglets" in card["answer"]
    assert "Pictures:" in card["answer"]


def test_litter_story_without_eligible_media_delivers_one_precise_request():
    value = build_litter_awareness_story_proposal(
        opportunity(), litters(), {"success": True, "items": [media_item(public=None)]})
    assert value["precise_media_request"].startswith("Please send one current portrait photo")
    try:
        build_protected_campaign_package(value,
            now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
    except ValueError as exc:
        assert str(exc) == "beacon_campaign_exact_litter_media_required"
    else:
        raise AssertionError("missing exact media must not create a protected card")


def test_explicit_generic_awareness_can_use_bound_text_only_publication():
    candidate={"success":True,"owner_review_packet":{
        "packet_id":"CONTENT-1","draft_copy":"A quiet farm-life update from Amadeus Farm.",
        "audience":"People interested in responsible local farm life",
        "public_livestock_policy":{"policy_version":"beacon_public_livestock_awareness_only_v1"}}}
    proposal=build_live_stock_awareness_proposal(
        {"success":True,"cards":[]}, candidate, {"success":True,"items":[]})
    protected=build_protected_campaign_package(proposal,
        now=datetime(2026,8,17,12,tzinfo=timezone.utc))
    campaign=protected["protected_campaign_package"]
    assert campaign["selected_approved_media"] == {"mode":"text_only"}
    assert campaign["budget_cap"]["total"] == "0.00"
    assert campaign["sam_response_contract"]["inbound_only"] is True
    card=owner_card(protected)
    assert card["campaign_review_preview"]["target_page_id"] == "PAGE-1"


def test_litter_story_copy_and_stock_digest_bind_exact_litter_context():
    stock = opportunity()
    stock["cards"][0]["story_context"] = {"kind": "litter", "subject": "Litter 7",
        "litter_id": "LITTER-7", "pig_ids": ["PIG-1", "PIG-2"],
        "event_id": "sale-eligibility:abc", "claim_boundary": "SAM recheck required"}
    value = build_sale_ready_demand_proposal(stock, {"success": True, "items": []})
    assert value["draft_caption"].startswith("Meet Litter 7 at Amadeus Farm.")
    assert value["sale_stock_evidence"]["story_context"]["litter_id"] == "LITTER-7"
    changed = opportunity()
    changed["cards"][0]["story_context"] = {**stock["cards"][0]["story_context"],
        "litter_id": "LITTER-8", "subject": "Litter 8"}
    other = build_sale_ready_demand_proposal(changed, {"success": True, "items": []})
    assert value["packet_id"] != other["packet_id"]
    assert (value["sale_stock_evidence"]["canonical_evidence_digest"] !=
            other["sale_stock_evidence"]["canonical_evidence_digest"])


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


def test_litter_media_order_is_stable_across_provider_permutations():
    second = media_item()
    second["binary_asset_id"] = "ASSET-2"
    second["content_sha256"] = "b" * 64
    forward = select_litter_story_media({"success": True, "items": [second, media_item()]},
        litter_id="LITTER-7", pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7")
    reverse = select_litter_story_media({"success": True, "items": [media_item(), second]},
        litter_id="LITTER-7", pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7")
    assert forward == reverse
    assert [item["asset_id"] for item in forward] == ["ASSET-1", "ASSET-2"]


def test_protected_package_rejects_incomplete_litter_media_authority():
    value = packet()
    value["sale_stock_evidence"]["story_context"] = {"kind": "litter",
        "subject": "Litter 7", "litter_id": "LITTER-7",
        "pig_ids": ["PIG-1", "PIG-2"], "event_id": "EVENT-7"}
    item = select_litter_story_media({"success": True, "items": [media_item()]},
        litter_id="LITTER-7", pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7")[0]
    for field in ("content_sha256", "storage_readback_proof_id", "library_accept_event_id",
                  "public_use_event_id", "public_use_authority"):
        broken = dict(item)
        broken[field] = ""
        value["litter_media_selection"] = [broken]
        try:
            build_protected_campaign_package(value,
                now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
        except ValueError as exc:
            assert str(exc) == "beacon_campaign_litter_media_authority_incomplete"
        else:
            raise AssertionError(f"missing {field} must fail closed")


def test_protected_package_rejects_litter_media_linkage_mismatch():
    story = {"kind": "litter", "subject": "Litter 7", "litter_id": "LITTER-7",
        "pig_ids": ["PIG-1", "PIG-2"], "event_id": "EVENT-7"}
    for field, value in (("litter_id", "OTHER-LITTER"),
                         ("pig_ids", ["PIG-1", "PIG-3"]),
                         ("event_id", "OTHER-EVENT")):
        value_packet = packet()
        value_packet["sale_stock_evidence"]["story_context"] = story
        item = select_litter_story_media({"success": True, "items": [media_item()]},
            litter_id="LITTER-7", pig_ids=["PIG-1", "PIG-2"], event_id="EVENT-7")[0]
        item[field] = value
        value_packet["litter_media_selection"] = [item]
        try:
            build_protected_campaign_package(value_packet,
                now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
        except ValueError as exc:
            assert str(exc) == "beacon_campaign_litter_media_binding_mismatch"
        else:
            raise AssertionError(f"mismatched {field} must fail closed")


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
    preview = owner_card(packet())["campaign_review_preview"]
    claim.return_value = ({"success": True, "status": "protected_callback_recovered",
        "callback_token": "opaque-token", "action_kind": "beacon_campaign_review",
        "mission_id": "M", "preview_digest": "d" * 64,
        "evidence_generation": preview["campaign_digest"], "preview_payload": preview}, 200)
    complete.return_value = {"completed": False, "replayed": True,
        "result": {"status": "beacon_campaign_review_approved"}}
    result, code = handle_protected_action_input(parsed(), object())
    assert code == 200 and result["status"] == "protected_callback_replayed_noop"
    assert result["suppress_owner_delivery"] is True and result["telegram_sends"] == 0
