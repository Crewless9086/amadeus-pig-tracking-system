import threading
import os
from datetime import datetime, timezone
from unittest.mock import patch

from modules.oom_sakkie.beacon_request_runtime import (
    build_current_beacon_proposal, build_litter_awareness_story_proposal,
    build_live_stock_awareness_proposal,
    build_supported_livestock_enquiry_proposal,
    build_protected_campaign_package, build_sale_ready_demand_proposal,
    build_scheduled_sale_ready_stock_result, handle_beacon_request,
    render_beacon_packet)
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.telegram_gateway import (
    _delivery_disabled_internal_proof, handle_telegram_gateway_message)
from modules.oom_sakkie.semantic_front_door import SemanticInterpretation

os.environ.setdefault("BEACON_FACEBOOK_PAGE_ID", "PAGE-1")


def opportunity(ready=True):
    return {"success": True, "generated_at": "2026-08-17T08:00:00+00:00", "cards": [{
        "card_id": "BEACON-CURRENT", "status": "ready_for_owner_review" if ready else "blocked",
        "lane": "live_stock", "category": "weaner", "unit": "animals",
        "opportunity_reason": "Verified eligible supply and quantified uncommitted demand overlap." if ready else "Evidence is incomplete.",
        "capacity_calculation": {"demand_cap": 3 if ready else 0,
            "eligible_categories": ["weaner"] if ready else []},
        "freshness": {"fresh": True},
        "provenance": {"observed_at": "2026-08-17T08:00:00+00:00"},
        "story_context": {"kind": "litter", "litter_id": "LITTER-7",
            "pig_ids": ["PIG-1", "PIG-2"], "event_id": "EVENT-7"}}]}


def litter_evidence(name="Molly"):
    return {"success": True, "litters": [{"litter_id": "LITTER-7", "sow_name": name}]}


def media(accepted=True, public=False):
    return {"success": True, "items": [{"binary_asset_id": "BEACON-BINARY-1",
        "content_sha256": "a" * 64, "latest_library_event": "library_accepted" if accepted else "",
        "latest_review_event_id": "REVIEW-1", "effective_public_use_approved": public,
        "current_library_accept_event_id": "REVIEW-1", "private_storage_proof_id": "STORAGE-1",
        "thumbnail_url": "/private/thumb", "observation": {"tags": ["live_stock", "weaner"]}}]}


def public_awareness_media(trusted=True):
    return {"success": True, "items": [{"binary_asset_id": "BEACON-BINARY-1",
        "beacon_asset_id": "BEACON-ASSET-1", "content_sha256": ("b" * 64 if trusted else "not-a-hash"),
        "observed_mime_type": "image/jpeg", "latest_library_event": "library_accepted",
        "current_library_accept_event_id": "LIBRARY-ACCEPT-1",
        "current_public_use_event_id": "PUBLIC-USE-1", "effective_public_use_approved": True,
        "private_storage_proof_id": "BEACON-BINARY-1:readback:" + "b" * 64,
        "thumbnail_url": "/private/litter-preview",
        "observation": {"tags": ["live_stock", "piglets", "weaner"],
            "litter_id": "LITTER-7", "pig_ids": ["PIG-1", "PIG-2"],
            "event_id": "EVENT-7", "captured_at": "2026-08-16",
            "source": "Charl Telegram intake"}}]}


def approved_legacy_media(owner_context, *, confidence="evidence_supported"):
    payload = public_awareness_media()
    payload["items"][0]["observation"] = {
        "classification": "private_farm_photo", "owner_context": owner_context}
    payload["items"][0]["owner_explanation"] = owner_context
    payload["items"][0]["observation_confidence"] = confidence
    return payload


def parsed(text="Please prepare the current marketing proposal", language="en"):
    return {"telegram_user_id": "42", "telegram_chat_id": "42", "provider_message_id": "9001",
        "provider_timestamp": "2026-08-14T08:01:00+00:00", "text": text,
        "semantic": {"domain": "beacon", "intent": "current_marketing_proposal", "message_kind": "request",
            "language": language, "needs_clarification": False}}


def awareness_candidate(media_status="media_gap"):
    media_value = ({"status": "approved_media_selected", "asset_id": "PUBLIC-ASSET-1",
        "media_type": "image", "content_sha256": "b" * 64,
        "content_hash_provenance": "server_computed_on_upload", "public_use_approved": True}
        if media_status == "approved" else {"status": "media_gap"})
    return {"success": True, "owner_review_packet": {"packet_id": "SOURCE-PACKET",
        "audience": "People interested in responsible local livestock and farm life",
        "draft_copy": ("A small moment from life at Amadeus Farm. Patient daily care matters.\n\n"
            "Follow the farm journey for more honest moments from behind the scenes."),
        "media": media_value, "public_livestock_policy": {
            "policy_version": "beacon_public_livestock_awareness_only_v2"}}}


def memory_store():
    rows, lock = {}, threading.Lock()
    def store(action, identity, payload):
        with lock:
            if action == "load":
                return rows.get(identity)
            if identity in rows:
                return {"success": True, "created": False}
            rows[identity] = payload
            return {"success": True, "created": True}
    return store, rows


def test_current_proposal_contains_commercial_decision_and_keeps_private_media_private():
    packet = build_current_beacon_proposal(opportunity(), media(public=True))
    assert packet["packet_type"] == "marketing_proposal"
    assert packet["expected_commercial_value"].startswith("Create enquiries for up to 3")
    assert packet["exact_media"][0]["public_use_approved"] is False
    assert packet["authority"]["publishes"] is False
    answer = render_beacon_packet(packet)
    assert "One protected decision" in answer
    assert "public use is not approved" in answer
    assert "Measure later" in answer


def test_missing_media_is_precise_and_afrikaans_rendered():
    packet = build_current_beacon_proposal(opportunity(), media(accepted=False))
    assert packet["packet_type"] == "missing_media_request"
    answer = render_beacon_packet(packet, language="af")
    assert "PRESIESE MEDIA-VERSOEK" in answer
    assert "portretfoto" in answer
    assert "Een besluit" in answer
    assert "Teikengehoor:" in answer and "Bewyse:" in answer
    assert "Aanbevole kanaal/kopie:" in answer and "Meet later:" in answer


def test_scheduled_enquiry_result_binds_approved_media_and_ignores_unclaimed_stock_changes():
    fixed = {"content_evidence_loader": lambda **kwargs: kwargs,
        "content_candidate_builder": lambda evidence, **kwargs: awareness_candidate(),
        "litter_loader": litter_evidence,
        "now": datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)}
    first = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: opportunity(), media_loader=lambda: public_awareness_media(), **fixed)
    changed = opportunity()
    changed["cards"][0]["story_context"]["event_id"] = "EVENT-8"
    changed_stock = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: changed, media_loader=lambda: public_awareness_media(), **fixed)
    assert first["proposal"]["packet_id"]
    assert first["result_digest"] == changed_stock["result_digest"]
    assert first["publishes"] is False and first["customer_sends"] is False
    assert first["proposal"]["packet_type"] == "live_stock_awareness_proposal"
    assert first["proposal"]["media"]["status"] == "approved_public_media_selected"
    assert first["proposal"]["protected_campaign_package"]["selected_approved_media"][0]["asset_id"] == "BEACON-ASSET-1"
    assert first["proposal"]["protected_campaign_package"]["campaign_objective"] == "farm_awareness"


def test_scheduled_enquiry_capture_is_explicitly_text_only():
    result = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: opportunity(),
        media_loader=lambda: media(accepted=False),
        litter_loader=litter_evidence,
        content_evidence_loader=lambda **kwargs: kwargs,
        content_candidate_builder=lambda evidence, **kwargs: awareness_candidate(),
        now=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc))
    assert result["proposal"]["packet_type"] == "live_stock_awareness_proposal"
    assert result["proposal"]["media"]["status"] == "text_only"
    assert result["proposal"]["authority"]["publishes"] is False
    assert result["proposal"]["protected_campaign_package"]["selected_approved_media"] == {"mode": "text_only"}


def test_scheduled_generation_rejects_media_without_current_public_use_authority():
    for payload in (
        public_awareness_media(trusted=False),
        media(accepted=False),
        {"success": False, "items": public_awareness_media()["items"]},
    ):
        result = build_scheduled_sale_ready_stock_result(
            opportunity_loader=opportunity,
            media_loader=lambda payload=payload: payload,
            content_evidence_loader=lambda **kwargs: kwargs,
            content_candidate_builder=lambda evidence, **kwargs: awareness_candidate(),
            now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
            target_page_id="PAGE-ONE")
        assert result["proposal"]["media"]["status"] == "text_only"
        assert result["proposal"]["protected_campaign_package"]["selected_approved_media"] == {"mode": "text_only"}
        assert result["publishes"] is False
        assert result["spends_money"] is False


def test_scheduled_approved_media_selection_is_deterministic_and_copy_neutral():
    approved = public_awareness_media()
    duplicate = dict(approved["items"][0])
    duplicate.update({"binary_asset_id": "BIN-2", "content_sha256": "b" * 64})
    approved["items"].append(duplicate)
    fixed = dict(
        opportunity_loader=opportunity,
        media_loader=lambda: approved,
        content_evidence_loader=lambda **kwargs: kwargs,
        content_candidate_builder=lambda evidence, **kwargs: awareness_candidate(),
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
        target_page_id="PAGE-ONE")
    first = build_scheduled_sale_ready_stock_result(**fixed)
    replay = build_scheduled_sale_ready_stock_result(**fixed)

    assert first["result_digest"] == replay["result_digest"]
    assert first["proposal"]["packet_id"] == replay["proposal"]["packet_id"]
    assert first["proposal"]["media"]["asset_id"] == "BEACON-ASSET-1"
    copy = first["proposal"]["draft_caption"].casefold()
    assert "available" not in copy and "for sale" not in copy and "price" not in copy
    assert first["proposal"]["call_to_action"] == ""
    assert first["proposal"]["protected_campaign_package"]["budget_cap"] == {
        "currency": "ZAR", "total": "0.00", "daily": "0.00"}


def test_scheduled_generation_uses_affirmative_structured_semantics_without_mutation():
    for tags in (["live_stock", "piglets"], ["live_stock", "litter"], ["live_stock", "weaner"]):
        payload = approved_legacy_media("Structured semantics are authoritative")
        payload["items"][0]["observation"]["tags"] = tags
        result = build_scheduled_sale_ready_stock_result(
            opportunity_loader=opportunity, media_loader=lambda: payload,
            content_evidence_loader=lambda **kwargs: kwargs,
            content_candidate_builder=lambda evidence, **kwargs: awareness_candidate(),
            now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc), target_page_id="PAGE-ONE")
        selected = result["proposal"]["protected_campaign_package"]["selected_approved_media"]
        assert selected[0]["asset_id"] == "BEACON-ASSET-1"
        assert set(selected[0]["subject_tags"]).intersection({"piglets", "litter", "live_stock"})
        assert payload["items"][0]["observation"]["tags"] == tags


def test_scheduled_generation_does_not_reinterpret_raw_legacy_owner_language():
    for context in (
        "Bella - just delivered 13 little piglets",
        "Bella and her newborn pigs",
        "No piglets are shown; this is an empty barn",
        "This photo was taken before the piglets arrived",
        "Bella het geen varkies nie",
        "Bella met haar pasgebore varkies",
        "Bella with chickens and a new litter",
        "Correction: that is not Bella's litter",
    ):
        payload = approved_legacy_media(context)
        result = build_scheduled_sale_ready_stock_result(
            opportunity_loader=opportunity, media_loader=lambda payload=payload: payload,
            content_evidence_loader=lambda **kwargs: kwargs,
            content_candidate_builder=lambda evidence, **kwargs: awareness_candidate(),
            now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc), target_page_id="PAGE-ONE")
        assert result["proposal"]["media"]["status"] == "text_only"
        assert result["proposal"]["protected_campaign_package"]["selected_approved_media"] == {
            "mode": "text_only"}


def test_supported_offering_read_rejects_fallback_or_partial_config_evidence():
    for result in (
        {"status":"fallback_default_file_missing", "configured":False, "knowledge":{}},
        {"status":"ok", "configured":True, "source_top_level_keys":["version"],
         "source_content_sha256":"a"*64,
         "knowledge":{"public_profile":{"farm_name":"Amadeus Farm"},
             "product_menu":[{"key":"live_sales","label":"Live pig sales"}]}},
        {"status":"ok", "configured":True,
         "path":"partial.json", "source_top_level_keys":["version","status","public_profile","product_menu"],
         "source_content_sha256":"b"*64,
         "source_evidence":{"version":"fallback","status":"fallback_default",
             "public_profile":{},"product_menu":[{"key":"live_sales"}]},
         "knowledge":{"public_profile":{"farm_name":"Amadeus Farm"},
             "product_menu":[{"key":"live_sales","label":"Live pig sales",
                 "summary":"Piglets, weaners, growers and finishers"}]}},
    ):
        packet=build_supported_livestock_enquiry_proposal(opportunity(), result)
        assert packet["packet_type"] == "supported_offering_evidence_request"
        assert packet["status"] == "evidence_blocked"


def test_messages_objective_rejects_generic_awareness_follow_copy():
    awareness = build_live_stock_awareness_proposal(
        opportunity(), awareness_candidate(), public_awareness_media())
    awareness.update({
        "campaign_objective": "facebook_messaging_conversations",
        "call_to_action": "Follow the farm journey.",
        "sale_stock_evidence": {"source": "beacon_opportunity_scanner",
            "card_id": "BEACON-CURRENT", "observed_at": "2026-08-17T08:00:00+00:00",
            "status": "ready_for_owner_review", "demand_cap": 3},
        "sam_response_contract": {"lane": "live_stock_sales",
            "supported_response_class": "clarification", "campaign_attribution_required": True},
    })
    try:
        build_protected_campaign_package(awareness,
            now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
    except ValueError as exc:
        assert str(exc) == "beacon_campaign_awareness_objective_required"
    else:
        raise AssertionError("awareness copy must not pass a messages objective")


def test_messages_objective_rejects_generic_message_cta_without_qualification_context():
    packet = build_sale_ready_demand_proposal(opportunity(), public_awareness_media())
    packet["call_to_action"] = "Message us."
    try:
        build_protected_campaign_package(packet,
            now=datetime(2026, 8, 17, 8, tzinfo=timezone.utc))
    except ValueError as exc:
        assert str(exc) == "beacon_campaign_awareness_objective_required"
    else:
        raise AssertionError("generic message CTA must not pass")


def test_missing_sale_stock_does_not_block_supported_enquiry_service_copy():
    result = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: opportunity(False),
        media_loader=lambda: public_awareness_media(),
        litter_loader=litter_evidence,
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
    assert result["status"] == "beacon_livestock_awareness_ready"
    assert result["proposal"]["packet_type"] == "live_stock_awareness_proposal"
    assert result["publishes"] is False and result["spends_money"] is False


def test_stock_claim_and_material_generation_bind_to_canonical_card():
    first = build_sale_ready_demand_proposal(opportunity(), public_awareness_media())
    altered = opportunity()
    altered["cards"][0]["card_id"] = "BEACON-NEW-CARD"
    second = build_sale_ready_demand_proposal(altered, public_awareness_media())
    assert first["packet_id"] != second["packet_id"]
    assert first["sale_stock_evidence"]["demand_cap"] == 3
    assert "3" not in first["draft_caption"]
    assert first["sam_response_contract"]["qualification_fields"] == [
        "animal_type", "quantity", "intended_use", "customer_area"]


def test_blocked_positive_cap_stock_returns_precise_exception():
    blocked = opportunity()
    blocked["cards"][0]["blockers"] = ["canonical_sale_eligibility_conflict"]
    packet = build_sale_ready_demand_proposal(blocked, public_awareness_media())
    assert packet["packet_type"] == "sale_ready_stock_evidence_request"
    assert packet["status"] != "ready_for_owner_review"


def test_missing_existing_demand_does_not_block_canonical_sale_ready_categories():
    stock = opportunity()
    stock["cards"][0].pop("story_context")
    stock["cards"][0].update({"status": "blocked", "category": "live_stock",
        "blockers": ["unknown_live_stock_demand_quantity",
            "no_quantified_uncommitted_live_stock_demand"]})
    stock["cards"][0]["capacity_calculation"] = {
        "demand_cap": 0,
        "eligible_categories": ["Finisher Pigs", "Grower Pigs", "Weaner Piglets"]}
    packet = build_sale_ready_demand_proposal(stock, public_awareness_media())
    assert packet["packet_type"] == "sale_ready_demand_proposal"
    assert packet["sale_stock_evidence"]["demand_evidence_status"] == "not_yet_quantified"
    assert packet["sale_stock_evidence"]["sale_ready_categories"] == [
        "Finisher Pigs", "Grower Pigs", "Weaner Piglets"]
    assert "Finisher Pigs, Grower Pigs or Weaner Piglets" in packet["draft_caption"]
    assert "number needed" in packet["draft_caption"]
    assert "demand_cap" not in packet["draft_caption"]
    assert "available" not in packet["draft_caption"].casefold()


def test_public_media_must_match_canonical_stock_category():
    unrelated = public_awareness_media()
    unrelated["items"][0]["observation"].pop("litter_id")
    unrelated["items"][0]["observation"].pop("pig_ids")
    unrelated["items"][0]["observation"].pop("event_id")
    unrelated["items"][0]["observation"]["tags"] = ["farm_life", "chickens"]
    packet = build_sale_ready_demand_proposal(opportunity(), unrelated)
    assert packet["media"]["status"] == "text_only"
    assert packet["media"]["reason"].startswith("No current public-use-approved")


def test_protected_boundary_rejects_incomplete_claimed_public_media_authority():
    packet = build_sale_ready_demand_proposal(opportunity(), public_awareness_media())
    packet["media"]["public_use_event_id"] = ""
    try:
        build_protected_campaign_package(packet,
            now=datetime(2026, 8, 17, 8, tzinfo=timezone.utc))
    except ValueError as exc:
        assert str(exc) == "beacon_campaign_public_media_authority_incomplete"
    else:
        raise AssertionError("incomplete public-media authority must fail closed")


def test_unchanged_evidence_is_stable_across_scheduler_day_rollover():
    first = build_scheduled_sale_ready_stock_result(
        opportunity_loader=opportunity, media_loader=public_awareness_media,
        litter_loader=litter_evidence,
        now=datetime(2026, 8, 17, 12, tzinfo=timezone.utc))
    later = build_scheduled_sale_ready_stock_result(
        opportunity_loader=opportunity, media_loader=public_awareness_media,
        litter_loader=litter_evidence,
        now=datetime(2026, 8, 19, 12, tzinfo=timezone.utc))
    assert first["proposal"]["packet_id"] == later["proposal"]["packet_id"]
    assert first["result_digest"] == later["result_digest"]
    assert first["proposal"]["protected_campaign_package"]["campaign_lane"] == "live_stock_awareness"


def test_scheduled_packet_identity_uses_canonical_observation_not_refresh_time():
    first = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: opportunity(), media_loader=lambda: public_awareness_media(),
        litter_loader=litter_evidence,
        now=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc))
    refreshed = opportunity()
    refreshed["generated_at"] = "2026-08-17T12:01:00+00:00"
    second = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: refreshed, media_loader=lambda: public_awareness_media(),
        litter_loader=litter_evidence,
        now=datetime(2026, 8, 17, 12, 1, tzinfo=timezone.utc))
    assert first["proposal"]["packet_id"] == second["proposal"]["packet_id"]
    assert first["result_digest"] == second["result_digest"]


def test_stock_neutral_packet_ignores_production_allocation_observation_churn():
    first_opportunity = opportunity()
    refreshed_opportunity = opportunity()
    first_opportunity["cards"][0]["provenance"]["observed_at"] = \
        "2026-08-22T18:10:25.874264+00:00"
    refreshed_opportunity["cards"][0]["provenance"]["observed_at"] = \
        "2026-08-22T18:11:17.850251+00:00"

    first = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: first_opportunity,
        media_loader=public_awareness_media, litter_loader=litter_evidence,
        now=datetime(2026, 8, 22, 18, 10, 25, tzinfo=timezone.utc),
        target_page_id="PAGE-ONE")
    refreshed = build_scheduled_sale_ready_stock_result(
        opportunity_loader=lambda: refreshed_opportunity,
        media_loader=public_awareness_media, litter_loader=litter_evidence,
        now=datetime(2026, 8, 22, 18, 11, 17, tzinfo=timezone.utc),
        target_page_id="PAGE-ONE")

    assert first["proposal"]["packet_id"] == refreshed["proposal"]["packet_id"]
    assert first["result_digest"] == refreshed["result_digest"]
    assert first["proposal"]["protected_campaign_package"]["campaign_lane"] == "live_stock_awareness"


def test_scheduled_generation_binds_configured_facebook_page_identity():
    fixed = {"opportunity_loader": opportunity,
        "media_loader": public_awareness_media,
        "litter_loader": litter_evidence,
        "now": datetime(2026, 8, 17, 12, tzinfo=timezone.utc)}
    with patch.dict("os.environ", {"BEACON_FACEBOOK_PAGE_ID": "PAGE-ONE"}):
        first = build_scheduled_sale_ready_stock_result(**fixed)
        replay = build_scheduled_sale_ready_stock_result(**fixed)
    with patch.dict("os.environ", {"BEACON_FACEBOOK_PAGE_ID": "PAGE-TWO"}):
        successor = build_scheduled_sale_ready_stock_result(**fixed)

    assert first["result_digest"] == replay["result_digest"]
    assert first["proposal"]["packet_id"] == replay["proposal"]["packet_id"]
    assert first["result_digest"] != successor["result_digest"]
    assert first["proposal"]["target_page_id"] == "PAGE-ONE"
    assert successor["proposal"]["target_page_id"] == "PAGE-TWO"


def test_scheduled_generation_cannot_restore_retired_enquiry_policy_by_patch():
    fixed = {"opportunity_loader": opportunity,
        "media_loader": public_awareness_media,
        "litter_loader": litter_evidence,
        "now": datetime(2026, 8, 17, 12, tzinfo=timezone.utc),
        "target_page_id": "PAGE-ONE"}
    first = build_scheduled_sale_ready_stock_result(**fixed)
    replay = build_scheduled_sale_ready_stock_result(**fixed)
    successor = build_scheduled_sale_ready_stock_result(**fixed)

    assert first["proposal"]["status"] == "ready_for_owner_review"
    assert first["proposal"]["campaign_objective"] == "farm_awareness"
    assert first["proposal"]["campaign_lane"] == "live_stock_awareness"
    assert first["proposal"]["call_to_action"] == ""
    assert first["proposal"]["protected_campaign_package"]["campaign_objective"] == "farm_awareness"
    assert first["result_digest"] == replay["result_digest"]
    assert first["proposal"]["packet_id"] == replay["proposal"]["packet_id"]
    assert first["result_digest"] == successor["result_digest"]


def test_content_packet_identity_does_not_treat_observation_time_as_new_campaign():
    from modules.beacon.content_operations import build_beacon_content_candidate
    evidence = {"opportunities": {"availability": "usable", "records": []}}
    first = build_beacon_content_candidate(
        evidence, now=datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc))
    second = build_beacon_content_candidate(
        evidence, now=datetime(2026, 8, 17, 12, 5, tzinfo=timezone.utc))
    assert first["generated_at"] != second["generated_at"]
    assert first["owner_review_packet"]["packet_id"] == second["owner_review_packet"]["packet_id"]


def test_missing_commercial_evidence_returns_precise_decision_packet_not_error():
    packet = build_current_beacon_proposal(opportunity(ready=False), media())
    assert packet["packet_type"] == "marketing_evidence_request"
    assert "no_quantified" not in " ".join(packet["missing_evidence"]) or packet["missing_evidence"]
    answer = render_beacon_packet(packet)
    assert "CURRENT EVIDENCE REQUEST" in answer
    assert "One protected decision" in answer
    assert packet["authority"]["publishes"] is False


def test_blocked_evidence_identity_ignores_scheduler_observation_time():
    first = opportunity(ready=False)
    later = {**opportunity(ready=False), "generated_at":"2026-08-14T09:00:00+00:00"}
    assert build_current_beacon_proposal(first, media())["packet_id"] == \
        build_current_beacon_proposal(later, media())["packet_id"]


def test_exact_failed_awareness_instruction_survives_semantics_and_zero_demand():
    exact_failed_instruction = "Prepare a non-availability farm-awareness campaign."
    request = parsed(exact_failed_instruction)
    request["semantic"]["intent"] = "live_stock_awareness"
    store, _ = memory_store()
    result, status = handle_beacon_request(request, issue_gateway_owner_authority("42", "42"),
        opportunity_loader=lambda: opportunity(ready=False),
        content_evidence_loader=lambda **kwargs: {"canonical": kwargs["opportunity_result"]},
        content_candidate_builder=lambda evidence: awareness_candidate(), event_store=store)
    assert status == 200
    assert result["proposal"]["packet_type"] == "live_stock_awareness_proposal"
    assert result["proposal"]["capacity_context"]["sam_quantified_buyer_demand"] == 0
    assert result["proposal"]["capacity_context"]["sale_availability_inferred"] is False
    assert "Safe draft copy" in result["answer"]
    assert "Approve / Correct / Decline" in result["answer"]
    assert "no_quantified_uncommitted_live_stock_demand" not in result["answer"]
    assert "{" not in result["answer"]


def test_awareness_selects_only_public_hash_verified_media_or_text_only():
    approved = build_live_stock_awareness_proposal(
        opportunity(ready=False), awareness_candidate("approved"), public_awareness_media())
    assert approved["media"]["status"] == "approved_public_media_selected"
    assert approved["media"]["content_sha256"] == "b" * 64
    text_only = build_live_stock_awareness_proposal(opportunity(ready=False), awareness_candidate(), media())
    assert text_only["media"]["status"] == "text_only"
    assert "portrait photo or short vertical video" in text_only["media"]["request"]
    assert text_only["authority"]["publishes"] is False


def test_awareness_afrikaans_response_is_natural_and_hides_internal_media_ids():
    packet = build_live_stock_awareness_proposal(opportunity(False), awareness_candidate(),
        public_awareness_media(), language="af")
    answer = render_beacon_packet(packet, language="af")
    assert "PLAASBEWUSTHEIDSVOORSTEL" in answer
    assert "Teikengehoor" in answer and "Veilige konsepkopie" in answer
    assert "Keur goed / Korrigeer / Wys af" in answer
    assert "Volg die plaas se reis" in answer
    assert "BEACON-ASSET-1" not in answer and "SHA-256" not in answer


def test_invalid_public_media_lineage_falls_back_to_safe_text_only():
    packet = build_live_stock_awareness_proposal(
        opportunity(False), awareness_candidate("approved"), public_awareness_media(trusted=False))
    assert packet["media"]["status"] == "text_only"


def test_incomplete_demand_and_demand_shaped_capacity_preserve_unknown():
    evidence = opportunity(False)
    evidence["cards"][0]["capacity_calculation"].update({"available_after_buffers": 7})
    evidence["cards"][0]["demand_summary"] = {"qualified_units": 0, "unknown_quantity_records": 1}
    evidence["cards"][0]["blockers"] = ["unknown_live_stock_demand_quantity"]
    packet = build_live_stock_awareness_proposal(evidence, awareness_candidate(), media())
    assert packet["capacity_context"]["herdmaster_safe_fulfilment_capacity"] == "Unknown"
    assert packet["capacity_context"]["sam_quantified_buyer_demand"] == "Unknown"


def test_provider_replay_is_returned_without_second_owner_delivery():
    store, rows = memory_store()
    authority = issue_gateway_owner_authority("42", "42")
    first, first_status = handle_beacon_request(parsed(), authority,
        opportunity_loader=opportunity, media_loader=media, event_store=store)
    second, second_status = handle_beacon_request(parsed(), authority,
        opportunity_loader=lambda: (_ for _ in ()).throw(AssertionError("must not reload")),
        media_loader=lambda: (_ for _ in ()).throw(AssertionError("must not reload")), event_store=store)
    assert first_status == second_status == 200
    assert first["status"] == "beacon_request_ready"
    assert second["status"] == "beacon_request_replay_recovered"
    assert second.get("suppress_owner_delivery") is not True
    assert len(rows) == 1


def test_provider_identity_conflict_fails_closed():
    store, _ = memory_store()
    authority = issue_gateway_owner_authority("42", "42")
    handle_beacon_request(parsed("English request"), authority,
        opportunity_loader=opportunity, media_loader=media, event_store=store)
    conflict, status = handle_beacon_request(parsed("Afrikaanse ander inhoud"), authority,
        opportunity_loader=opportunity, media_loader=media, event_store=store)
    assert status == 409
    assert conflict["status"] == "beacon_request_provider_binding_conflict"
    assert conflict["publishes"] is False


def test_semantic_paraphrase_not_keywords_controls_dispatch():
    p = parsed("Kan Oom Sakkie vandag iets winsgewend vir ons bemarking voorstel?", "af")
    store, _ = memory_store()
    result, status = handle_beacon_request(p, issue_gateway_owner_authority("42", "42"),
        opportunity_loader=opportunity, media_loader=media, event_store=store)
    assert status == 200
    assert result["specialist_identity"] == "BEACON"
    assert "BEMARKINGSVOORSTEL" in result["answer"]


def test_concurrent_duplicate_requests_create_one_result_and_both_reach_delivery_lifecycle():
    store, rows = memory_store()
    authority = issue_gateway_owner_authority("42", "42")
    results = []
    def run():
        results.append(handle_beacon_request(parsed(), authority,
            opportunity_loader=opportunity, media_loader=media, event_store=store)[0])
    threads = [threading.Thread(target=run) for _ in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join()
    assert len(rows) == 1
    assert all(result.get("suppress_owner_delivery") is not True for result in results)
    assert {result["status"] for result in results} <= {"beacon_request_ready", "beacon_request_replay_recovered"}


def test_delivery_disabled_proof_requires_both_authenticated_mode_shape_and_bmq_identity():
    headers = {"X-Oom-Sakkie-Delivery-Mode": "disabled-internal-proof"}
    assert _delivery_disabled_internal_proof({"internal_proof_identity": "BMQ-20260813-04-PROOF"}, headers)
    assert not _delivery_disabled_internal_proof({}, headers)
    assert not _delivery_disabled_internal_proof({"internal_proof_identity": "BMQ-20260813-04-PROOF"}, {})


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.interpret_owner_message")
def test_delivery_disabled_proof_contains_unresolved_semantics_before_any_delivery(interpret, deliver):
    interpret.return_value = SemanticInterpretation(domain="general", intent="unclear",
        message_kind="request", needs_clarification=True)
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "g" * 40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42",
        "OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"}
    payload = {"internal_proof_identity": "BMQ-20260813-04-PROOF",
        "message": {"message_id": 99, "date": 1785790000, "text": "marketing",
            "from": {"id": 42}, "chat": {"id": 42, "type": "private"}}}
    with patch.dict("os.environ", env, clear=True), patch(
            "modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay", return_value=None):
        result, status = handle_telegram_gateway_message(payload,
            headers={"Authorization": "Bearer " + "g" * 40,
                "X-Oom-Sakkie-Delivery-Mode": "disabled-internal-proof"})
    assert status == 422 and result["delivery"]["telegram_sends"] == 0
    deliver.assert_not_called()
