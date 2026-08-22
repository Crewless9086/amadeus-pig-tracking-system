"""Authenticated, read-only Oom Sakkie to BEACON proposal lifecycle."""
from __future__ import annotations

import hashlib
import html
import json
import os
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable, Mapping

from modules.beacon.marketing_proposal import prepare_marketing_proposal
from modules.beacon.media_intake import list_media_intakes
from modules.beacon.opportunity_scanner import build_beacon_opportunity_cards
from modules.beacon.public_livestock_content_policy import (
    POLICY_VERSION,
    assess_public_livestock_content,
    public_livestock_policy_binding, public_livestock_policy_binding_matches,
)
from modules.beacon.content_operations import (
    build_beacon_content_candidate,
    gather_beacon_content_evidence,
)
from modules.pig_weights.farm_supabase_read_service import list_litter_overview
from modules.sales.sam_farm_knowledge import load_sam_farm_knowledge
from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.oom_sakkie.beacon_media_review_runtime import present_private_media_review
from modules.oom_sakkie.protected_action_claims import (
    CALLBACK_PREFIX, canonical_preview_digest, create_claim,
)

CONTRACT_VERSION = "oom_sakkie_beacon_request_v1"
EVENT_SOURCE = "oom_sakkie_beacon_request"
ZERO = {"writes_farm_data": False, "writes_media": False, "publishes": False,
        "spends_money": False, "customer_sends": False,
        "protected_actions_performed": False}
CAMPAIGN_REVIEW_ACTION = "beacon_campaign_review"


def build_scheduled_sale_ready_stock_result(*, opportunity_loader=build_beacon_opportunity_cards,
        media_loader=list_media_intakes, content_evidence_loader=gather_beacon_content_evidence,
        content_candidate_builder=build_beacon_content_candidate,
        litter_loader=list_litter_overview, business_evidence_loader=load_sam_farm_knowledge,
        now=None, target_page_id=None):
    """Compose one governed, stock-neutral livestock enquiry result."""
    opportunities = opportunity_loader()
    media_result = media_loader()
    media_payload = media_result[0] if isinstance(media_result, tuple) else media_result
    evidence_time = _stable_opportunity_time(opportunities, fallback=now)
    # Keep the legacy awareness dependencies injectable for caller compatibility,
    # but a scheduled revenue case must use the sale-ready demand contract.  An
    # awareness/follow packet is never silently upgraded into a messages campaign.
    packet = build_supported_livestock_enquiry_proposal(
        opportunities, business_evidence_loader(), observed_at=evidence_time,
        target_page_id=target_page_id)
    if packet.get("status") == "ready_for_owner_review":
        packet = build_protected_campaign_package(packet, now=evidence_time)
    return {
        "success": True,
        "status": ("beacon_livestock_enquiry_capture_ready" if
            packet.get("protected_campaign_package") else
            "beacon_livestock_offering_evidence_exception"),
        "answer": render_beacon_packet(packet, language="en"),
        "proposal": packet,
        "result_digest": _digest(packet),
        "follow_up_owner": "BEACON",
        "next_trigger": "material canonical offering, policy or owner-decision change",
        **ZERO,
    }


def build_supported_livestock_enquiry_proposal(opportunities, knowledge_result, *, observed_at=None,
        target_page_id=None):
    """Read the shared SAM menu and invite enquiries without claiming stock."""
    if not isinstance(opportunities, Mapping) or opportunities.get("success") is not True:
        raise ValueError("canonical_opportunity_evidence_required")
    required_source_keys = {"version", "status", "public_profile", "product_menu"}
    if (not isinstance(knowledge_result, Mapping) or knowledge_result.get("status") != "ok"
            or knowledge_result.get("configured") is not True
            or not required_source_keys.issubset(set(knowledge_result.get("source_top_level_keys") or []))
            or not re.fullmatch(r"[0-9a-f]{64}", str(knowledge_result.get("source_content_sha256") or ""))):
        return _supported_offering_exception("The configured SAM farm-knowledge source is unavailable or fallback-only.")
    source = knowledge_result.get("source_evidence") if isinstance(
        knowledge_result.get("source_evidence"), Mapping) else {}
    profile = source.get("public_profile") if isinstance(source.get("public_profile"), Mapping) else {}
    menu = source.get("product_menu") if isinstance(source.get("product_menu"), list) else []
    offering = next((item for item in menu if isinstance(item, Mapping)
        and item.get("key") == "live_sales"), None)
    version = str(source.get("version") or "").strip()
    source_status = str(source.get("status") or "").strip()
    summary = str((offering or {}).get("summary") or "").strip()
    required_categories = {"piglets", "weaners", "growers", "finishers"}
    if (not str(knowledge_result.get("path") or "").strip()
            or not version or version.casefold().startswith("fallback")
            or not source_status or source_status.casefold().startswith("fallback")
            or profile.get("farm_name") != "Amadeus Farm"
            or not str((offering or {}).get("label") or "").strip()
            or not required_categories.issubset(set(summary.casefold().replace(",", "").split()))):
        return _supported_offering_exception("The canonical SAM menu does not identify Amadeus Farm live pig enquiries.")
    caption = ("Looking for live pigs? Amadeus Farm handles enquiries for piglets, weaners, "
        "growers and finishers. Message us with the type, number needed, intended use and your area. "
        "SAM will check current farm records before discussing any option; no stock, price, "
        "availability, delivery or reservation is promised.")
    policy = assess_public_livestock_content(caption,
        objective="qualified_livestock_enquiries",
        campaign_lane="live_stock_enquiry_capture")
    policy_version = str(policy.get("policy_version") or "").strip()
    if not policy.get("allowed") or not policy_version:
        return _supported_offering_exception(
            "Public live-animal acquisition solicitation is not authorized; "
            "only awareness, education, husbandry, welfare or farm-story content is eligible.")
    page_id = str(target_page_id if target_page_id is not None
        else os.getenv("BEACON_FACEBOOK_PAGE_ID") or "").strip()
    policy_binding = public_livestock_policy_binding(policy)
    evidence = {"source": "sam_farm_knowledge", "version": version,
        "source_path": str(knowledge_result.get("path") or ""),
        "source_content_sha256": str(knowledge_result["source_content_sha256"]),
        "offering_key": "live_sales", "offering_label": str(offering.get("label") or ""),
        "offering_summary": str(offering.get("summary") or ""),
        "sale_availability_inferred": False,
        "claim_boundary": "Supported enquiry service only; no stock, price, availability, delivery, reservation or outcome claim."}
    packet = {"contract_version":"beacon_livestock_enquiry_capture_proposal_v1",
        "packet_type":"livestock_enquiry_capture_proposal", "status":"ready_for_owner_review",
        "campaign_objective":"qualified_livestock_enquiries",
        "campaign_lane":"live_stock_enquiry_capture",
        "objective":"Invite genuine live pig enquiries for SAM qualification",
        "audience":"Prospective livestock buyers in the Riversdale and Albertinia service area",
        "intended_channel":"Amadeus Farm Facebook Page organic", "draft_caption":caption,
        "target_page_id":page_id, "public_content_policy":policy_binding,
        "call_to_action":"Message Amadeus Farm with the type, number needed, intended use and your area.",
        "media":{"status":"text_only", "reason":"Text-only avoids implying current animals or stock."},
        "business_offering_evidence":evidence,
        "sam_response_contract":{"lane":"live_stock_sales", "supported_response_class":"clarification",
            "qualification_fields":["animal_type","quantity","intended_use","customer_area"],
            "campaign_attribution_required":True, "inbound_only":True,
            "authority_boundary":"SAM may qualify a genuine inbound only; no quote, price, reservation, allocation, delivery promise, order, payment or stock commitment."},
        "decision_options":["approve","correct","decline"], "authority":dict(ZERO)}
    packet["packet_id"] = "BEACON-ENQUIRY-" + _digest(
        {"copy":caption,"evidence":evidence,"sam":packet["sam_response_contract"],
         "target_page_id":page_id,"public_content_policy":policy_binding})[:24].upper()
    return packet


def _supported_offering_exception(reason):
    packet={"contract_version":"beacon_supported_offering_exception_v1",
        "packet_type":"supported_offering_evidence_request", "status":"evidence_blocked",
        "precise_exception":reason,
        "required_evidence":"A configured, non-fallback SAM farm-knowledge record identifying Amadeus Farm's live_sales offering.",
        "authority":dict(ZERO)}
    packet["packet_id"]="BEACON-OFFERING-EXCEPTION-"+_digest(packet)[:24].upper()
    return packet


def _stable_opportunity_time(opportunities, *, fallback=None):
    """Anchor derived packet IDs to canonical evidence, not delivery wall time."""
    observed = []
    if isinstance(opportunities, Mapping):
        for card in opportunities.get("cards") or []:
            if not isinstance(card, Mapping):
                continue
            provenance = card.get("provenance") if isinstance(card.get("provenance"), Mapping) else {}
            value = provenance.get("observed_at")
            if value:
                observed.append(str(value))
    value = max(observed) if observed else fallback
    if value is None and isinstance(opportunities, Mapping):
        value = opportunities.get("generated_at")
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("beacon_opportunity_time_requires_timezone")
    return parsed.astimezone(timezone.utc)


def build_protected_campaign_package(packet, *, now=None):
    """Bind the complete exact campaign envelope without granting authority."""
    if not isinstance(packet, Mapping) or not packet.get("packet_id"):
        raise ValueError("beacon_campaign_packet_identity_required")
    observed = now or datetime.now(timezone.utc)
    if observed.tzinfo is None:
        raise ValueError("beacon_campaign_package_time_requires_timezone")
    local = observed.astimezone(ZoneInfo("Africa/Johannesburg"))
    publication = (local + timedelta(days=1)).replace(hour=18, minute=0, second=0, microsecond=0)
    media = packet.get("media") if isinstance(packet.get("media"), Mapping) else {}
    if media.get("status") == "approved_public_media_selected":
        if (not str(media.get("asset_id") or "").strip()
                or not re.fullmatch(r"[0-9a-f]{64}", str(media.get("content_sha256") or "").lower())
                or not str(media.get("storage_readback_proof_id") or "").strip()
                or not str(media.get("library_accept_event_id") or "").strip()
                or not str(media.get("public_use_event_id") or "").strip()):
            raise ValueError("beacon_campaign_public_media_authority_incomplete")
    litter_media = packet.get("litter_media_selection") if isinstance(
        packet.get("litter_media_selection"), list) else []
    text_only = (packet.get("packet_type") in {
        "live_stock_awareness_proposal", "livestock_enquiry_capture_proposal"}
        and media.get("status") == "text_only")
    enquiry_capture = packet.get("packet_type") == "livestock_enquiry_capture_proposal"
    if litter_media:
        story = ((packet.get("sale_stock_evidence") or {}).get("story_context")
            if isinstance(packet.get("sale_stock_evidence"), Mapping) else None)
        expected_pigs = {str(value) for value in (story or {}).get("pig_ids") or []}
        if ((story or {}).get("kind") != "litter" or not (story or {}).get("litter_id")
                or not (story or {}).get("event_id") or not expected_pigs):
            raise ValueError("beacon_campaign_litter_story_binding_incomplete")
        for item in litter_media:
            if (not isinstance(item, Mapping)
                    or not str(item.get("asset_id") or "").strip()
                    or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("content_sha256") or "").lower())
                    or not str(item.get("storage_readback_proof_id") or "").strip()
                    or not str(item.get("library_accept_event_id") or "").strip()
                    or not str(item.get("public_use_event_id") or "").strip()
                    or item.get("public_use_authority") != "approved"):
                raise ValueError("beacon_campaign_litter_media_authority_incomplete")
            if (str(item.get("litter_id") or "") != str(story["litter_id"])
                    or {str(value) for value in item.get("pig_ids") or []} != expected_pigs
                    or str(item.get("event_id") or "") != str(story["event_id"])):
                raise ValueError("beacon_campaign_litter_media_binding_mismatch")
        exact_media = [{key: item.get(key) for key in (
            "asset_id", "content_sha256", "storage_readback_proof_id",
            "library_accept_event_id", "public_use_event_id", "thumbnail_url",
            "capture_date", "source", "litter_id", "pig_ids", "event_id",
            "public_use_authority")} for item in litter_media]
    else:
        exact_media = ({key: media.get(key) for key in (
            "asset_id", "media_type", "content_sha256", "storage_readback_proof_id",
            "library_accept_event_id", "public_use_event_id")}
            if media.get("status") == "approved_public_media_selected" else {"mode": "text_only"})
    exact_copy = str(packet.get("draft_caption") or packet.get("recommended_copy") or "").strip()
    if not exact_copy:
        raise ValueError("beacon_campaign_exact_copy_required")
    objective = str(packet.get("campaign_objective") or
        ("farm_awareness" if text_only else "")).strip()
    cta = str(packet.get("call_to_action") or "").strip()
    stock = packet.get("sale_stock_evidence") if isinstance(
        packet.get("sale_stock_evidence"), Mapping) else {}
    sam = packet.get("sam_response_contract") if isinstance(
        packet.get("sam_response_contract"), Mapping) else {}
    campaign_lane = packet.get("campaign_lane") or (
        "live_stock_awareness" if text_only else "")
    valid_objective = ((objective == "qualified_livestock_enquiries"
        and campaign_lane == "live_stock_enquiry_capture") if enquiry_capture else
        (objective == "farm_awareness" and campaign_lane == "live_stock_awareness"))
    if not valid_objective:
        raise ValueError("beacon_campaign_awareness_objective_required")
    page_id = str(packet.get("target_page_id") or "").strip()
    current_policy = assess_public_livestock_content(exact_copy,
        objective=objective, campaign_lane=campaign_lane,
        media=[] if text_only else exact_media)
    bound_policy = packet.get("public_content_policy") if isinstance(
        packet.get("public_content_policy"), Mapping) else {}
    if (not page_id or current_policy.get("allowed") is not True
            or not public_livestock_policy_binding_matches(bound_policy,
                current_policy, target_page_id=page_id, now=now)):
        raise ValueError("beacon_campaign_public_policy_binding_required")
    if not enquiry_capture and cta:
        raise ValueError("beacon_campaign_awareness_cta_prohibited")
    if enquiry_capture:
        if (not cta or current_policy.get("allowed") is not True
                or not public_livestock_policy_binding_matches(
                    bound_policy, current_policy, target_page_id=page_id, now=now)):
            raise ValueError("beacon_campaign_enquiry_capture_policy_required")
    if not litter_media and not text_only:
        raise ValueError("beacon_campaign_exact_litter_media_required")
    if text_only:
        capacity_source = (packet.get("business_offering_evidence") if enquiry_capture
            else packet.get("capacity_context"))
        capacity = capacity_source if isinstance(capacity_source, Mapping) else {}
        if capacity.get("sale_availability_inferred") is not False:
            raise ValueError("beacon_campaign_text_only_non_availability_required")
        stock = {"source": ("sam_farm_knowledge" if enquiry_capture else "beacon_opportunity_scanner"),
            **dict(capacity), "claim_boundary": str(capacity.get("claim_boundary") or
                "Awareness only; no stock, availability, price or fulfilment claim.")}
        if enquiry_capture:
            if (sam.get("lane") != "live_stock_sales"
                    or sam.get("campaign_attribution_required") is not True
                    or sam.get("inbound_only") is not True):
                raise ValueError("beacon_campaign_sam_response_contract_required")
        else:
            if not str(packet.get("sam_routing") or "").strip():
                raise ValueError("beacon_campaign_sam_response_contract_required")
            sam = {"lane": "live_stock_sales", "campaign_attribution_required": True,
                "inbound_only": True, "authority_boundary": str(packet["sam_routing"])}
    else:
        story = stock.get("story_context") if isinstance(stock.get("story_context"), Mapping) else {}
        sow_name = str(story.get("sow_name") or "").strip()
        if not sow_name or str(story.get("litter_id") or "") in exact_copy:
            raise ValueError("beacon_campaign_public_sow_identity_required")
        if sow_name not in exact_copy:
            raise ValueError("beacon_campaign_public_sow_name_missing")
        if (stock.get("source") != "beacon_opportunity_scanner"
                or not stock.get("fresh") or not stock.get("card_id") or not stock.get("observed_at")):
            raise ValueError("beacon_campaign_canonical_sale_stock_required")
        if (sam.get("lane") != "live_stock_sales"
                or not sam.get("campaign_attribution_required")
                or sam.get("inbound_only") is not True):
            raise ValueError("beacon_campaign_sam_response_contract_required")
    envelope = {
        "contract_version": "beacon_protected_facebook_campaign_package_v1",
        "delivery_due_policy": "same_cycle_on_new_or_changed_evidence",
        "source_packet_id": packet["packet_id"], "exact_post_copy": exact_copy,
        "target_page_id": page_id,
        "public_content_policy": dict(packet.get("public_content_policy") or {}),
        "selected_approved_media": exact_media,
        "media_evidence_exception": ("Explicit text-only publication; no media is selected or implied."
            if text_only else str(packet.get("precise_media_request") or "")),
        "audience": str(packet.get("audience") or "Local people interested in responsible livestock and farm life"),
        "location": "Riversdale and Albertinia, Western Cape, South Africa",
        "publication_time": publication.isoformat(), "publication_timezone": "Africa/Johannesburg",
        "approval_expires_at": publication.isoformat(),
        "boost_objective": "none",
        "campaign_lane": campaign_lane,
        "campaign_objective": objective,
        "call_to_action": cta,
        "sale_stock_evidence": dict(stock),
        "sam_response_contract": dict(sam),
        "budget_cap": {"currency": "ZAR", "total": "0.00", "daily": "0.00"},
        "duration": {"days": 0},
        "stop_conditions": ["public_use_or_campaign_authority_is_revoked",
            "canonical_litter_or_media_evidence_materially_changes",
            "provider_rejects_or_returns_ambiguous_publication_state"],
        "rollback": {
            "on_publication_failure": "do_not_retry; retain provider chronology and stop boost",
            "on_authority_or_evidence_change": "stop before publication and preserve immutable readback"},
        "authority": {"publication_authorized": False, "boost_authorized": False,
            "spend_authorized": False, "customer_send_authorized": False, "approval_required": True}}
    envelope["attribution_identity"] = "BEACON-CAMPAIGN-" + _digest(envelope)[:24].upper()
    envelope["sam_response_contract"]["campaign_attribution_id"] = envelope["attribution_identity"]
    envelope["approval_card"] = {
        "decision": "Approve this exact organic Facebook story before its publication time / Correct / Decline",
        "approval_effect": "authorization only; BEACON must execute and obtain Meta readback",
        "requested_authority": "one organic Facebook publication attempt with zero spend"}
    return {**packet, "protected_campaign_package": envelope}


def build_sale_ready_demand_proposal(opportunities, media_payload, *, observed_at=None):
    """Build commercially coherent, claim-bounded demand copy or one exception."""
    if not isinstance(opportunities, Mapping) or opportunities.get("success") is not True:
        raise ValueError("canonical_opportunity_evidence_required")
    cards = [row for row in opportunities.get("cards") or [] if isinstance(row, Mapping)]
    demand_only_blockers = {"sam_live_stock_demand_unavailable",
        "unknown_live_stock_demand_quantity", "incompatible_live_stock_demand",
        "invalid_live_stock_weight_requirement", "invalid_live_stock_sex_requirement",
        "malformed_live_stock_demand_evidence", "incompatible_live_stock_weight_requirement",
        "no_quantified_uncommitted_live_stock_demand"}
    def sale_ready(row):
        capacity = row.get("capacity_calculation") if isinstance(
            row.get("capacity_calculation"), Mapping) else {}
        categories = [str(value).strip() for value in capacity.get("eligible_categories") or []
            if str(value).strip()]
        blockers = {str(value) for value in row.get("blockers") or []}
        freshness = row.get("freshness") if isinstance(row.get("freshness"), Mapping) else {}
        return (row.get("lane") == "live_stock" and categories
            and freshness.get("fresh") is True and not (blockers - demand_only_blockers))
    ready = [row for row in cards if sale_ready(row)]
    if not ready:
        packet = _current_evidence_request(cards, opportunities)
        packet.update({
            "contract_version": "beacon_sale_ready_demand_exception_v1",
            "packet_type": "sale_ready_stock_evidence_request",
            "objective": "Generate qualified livestock enquiries through Facebook messages",
            "precise_exception": "No fresh canonical live-stock opportunity proves any sale-ready stock category without a stock-evidence blocker.",
            "required_evidence": "A fresh BEACON opportunity card backed by canonical sale-eligible stock categories and no availability, freshness or source conflict.",
            "decision_options": ["wait_for_canonical_stock_evidence", "correct"],
            "protected_owner_decision": "None: publication and spend are ineligible until canonical sale-ready stock exists.",
        })
        packet["packet_id"] = "BEACON-DEMAND-EXCEPTION-" + _digest({
            "evidence": packet.get("factual_evidence"),
            "required_evidence": packet["required_evidence"]})[:24].upper()
        return packet
    card = ready[0]
    provenance = card.get("provenance") if isinstance(card.get("provenance"), Mapping) else {}
    capacity = card.get("capacity_calculation") if isinstance(
        card.get("capacity_calculation"), Mapping) else {}
    sale_categories = sorted({str(value).strip() for value in
        capacity.get("eligible_categories") or [] if str(value).strip()})
    story = card.get("story_context") if isinstance(card.get("story_context"), Mapping) else {}
    stock = {
        "source": "beacon_opportunity_scanner",
        "card_id": str(card.get("card_id") or ""),
        "observed_at": str(provenance.get("observed_at") or observed_at or opportunities.get("generated_at") or ""),
        "status": str(card.get("status") or ""),
        "category": str(card.get("category") or "livestock").replace("_", " "),
        "unit": str(card.get("unit") or "animals"),
        "demand_cap": int((card.get("capacity_calculation") or {}).get("demand_cap") or 0),
        "sale_ready_categories": sale_categories,
        "fresh": True,
        "demand_evidence_status": ("not_yet_quantified" if int(
            capacity.get("demand_cap") or 0) == 0 else "quantified"),
        "canonical_evidence_digest": _digest({
            "card_id": card.get("card_id"),
            "status": card.get("status"),
            "lane": card.get("lane"),
            "category": card.get("category"),
            "unit": card.get("unit"),
            "opportunity_reason": card.get("opportunity_reason"),
            "capacity_calculation": card.get("capacity_calculation") or {},
            "demand_summary": card.get("demand_summary") or {},
            "blockers": sorted(card.get("blockers") or []),
            "observed_at": provenance.get("observed_at"),
            "story_context": story,
        }),
        "claim_boundary": "Categories support taking enquiries only; no quantity is advertised and SAM must re-read canonical stock before any offer or commitment.",
        "story_context": dict(story),
    }
    if not stock["card_id"] or not stock["observed_at"]:
        raise ValueError("canonical_sale_stock_identity_required")
    category = stock["category"]
    subjects = [_public_stock_subject(value) for value in sale_categories]
    subject = _natural_list(subjects)
    if story.get("kind") == "litter":
        litter_subject = str(story.get("subject") or f"Litter {story.get('litter_id') or ''}").strip()
        caption = (f"Meet {litter_subject} at Amadeus Farm. We are taking livestock enquiries "
            "about pigs from this litter. Message us with the number needed, intended use and "
            "your area. Our livestock team will check current farm records before any offer or commitment.")
    else:
        caption = (f"Looking for {subject}? Amadeus Farm is currently taking livestock enquiries. "
            "Message Amadeus Farm with the type of animal, number needed, intended use and your area. "
            "Our livestock team will check current farm records before any offer or commitment.")
    cta = ("Message Amadeus Farm with the animal type, number needed, intended use and your area "
        "so our livestock team can qualify your enquiry.")
    media_tags = {token.casefold().replace(" ", "_") for value in sale_categories
        for token in (value, *value.split()) if token}
    media = _public_awareness_media(media_payload, required_tags=media_tags)
    media_plan = media or {
        "status": "text_only",
        "reason": "No current public-use-approved, hash-verified livestock asset is available.",
            "request": (f"Optional governed media request: one portrait photo or short vertical video of {subject} "
            "in their current farm context, with no people, plates, customer locations, illness, prices or sales signage."),
    }
    packet = {
        "contract_version": "beacon_sale_ready_demand_proposal_v1",
        "packet_type": "sale_ready_demand_proposal",
        "status": "ready_for_owner_review",
        "campaign_objective": "facebook_messaging_conversations",
        "objective": f"Generate qualified messages about current {subject}",
        "audience": "Local prospective livestock buyers near Riversdale and Albertinia",
        "intended_channel": "Facebook Page organic plus separately approved messages boost",
        "draft_caption": caption,
        "call_to_action": cta,
        "media": media_plan,
        "sale_stock_evidence": stock,
        "sam_response_contract": {
            "lane": "live_stock_sales",
            "supported_response_class": "clarification",
            "qualification_fields": ["animal_type", "quantity", "intended_use", "customer_area"],
            "campaign_attribution_required": True,
            "authority_boundary": "No quote, price, reservation, allocation, delivery promise, order, payment or stock commitment.",
        },
        "performance_measurement": "Record attributed messages, qualified SAM leads, conversions, completed paid sales and gross profit separately; never infer missing outcomes.",
        "decision_options": ["approve", "correct", "decline"],
        "protected_owner_decision": "Approve this exact copy, media mode, publication and boost envelope; Correct it; or Decline it.",
        "authority": dict(ZERO),
    }
    if story.get("kind") == "litter":
        subject_text = str(story.get("subject") or f"Litter {story.get('litter_id') or ''}").strip()
        choice = build_litter_media_choice(media_payload,
            litter_id=story.get("litter_id"), pig_ids=story.get("pig_ids") or [],
            event_id=story.get("event_id"), subject=subject_text)
        packet["story_subject"] = subject_text
        packet["story_context"] = dict(story)
        if choice["selected"]:
            packet["litter_media_selection"] = choice["selected"]
            first = choice["selected"][0]
            packet["media"] = {"status": "approved_public_media_selected",
                "asset_id": first["asset_id"], "media_type": "farm photograph",
                "content_sha256": first["content_sha256"],
                "storage_readback_proof_id": first["storage_readback_proof_id"],
                "library_accept_event_id": first["library_accept_event_id"],
                "public_use_event_id": first["public_use_event_id"]}
        else:
            packet["precise_media_request"] = choice["request"]
    packet["packet_id"] = "BEACON-DEMAND-" + _digest({
        "stock": stock, "copy": caption, "cta": cta, "media": media_plan,
        "sam": packet["sam_response_contract"]})[:24].upper()
    return packet


def build_litter_awareness_story_proposal(opportunities, litter_result, media_payload,
        *, observed_at=None, target_page_id=None):
    """Build one non-commercial sow/litter story with exact governed media."""
    if not isinstance(opportunities, Mapping) or opportunities.get("success") is not True:
        raise ValueError("canonical_opportunity_evidence_required")
    if not isinstance(litter_result, Mapping) or litter_result.get("success") is not True:
        raise ValueError("canonical_litter_evidence_required")
    cards = [row for row in opportunities.get("cards") or [] if isinstance(row, Mapping)]
    card = next((row for row in cards if isinstance(row.get("story_context"), Mapping)
        and row["story_context"].get("kind") == "litter"), None)
    if not card:
        return _litter_awareness_exception(
            "No current canonical litter event is linked to the BEACON observation.",
            "Choose one current canonical litter before any media or publication review.")
    story = dict(card["story_context"])
    litter = next((row for row in litter_result.get("litters") or []
        if isinstance(row, Mapping)
        and str(row.get("litter_id") or "") == str(story.get("litter_id") or "")), None)
    sow_name = str((litter or {}).get("sow_name") or "").strip()
    if not sow_name or sow_name.casefold() == "unknown":
        return _litter_awareness_exception(
            "The current litter has no canonical sow human name.",
            "Record or confirm the sow's human name on the canonical litter record.")
    story["sow_name"] = sow_name
    choice = build_litter_media_choice(media_payload, litter_id=story.get("litter_id"),
        pig_ids=story.get("pig_ids") or [], event_id=story.get("event_id"),
        subject=f"{sow_name}'s piglets")
    caption = (f"{sow_name} has settled into the steady rhythm of caring for her piglets. "
        "Between feeds, clean bedding and quiet checks, the little family is finding its feet "
        "one ordinary farm day at a time.")
    policy = assess_public_livestock_content(caption, objective="farm_awareness",
        campaign_lane="live_stock_awareness", media=choice["selected"])
    page_id = str(target_page_id if target_page_id is not None
        else os.getenv("BEACON_FACEBOOK_PAGE_ID") or "").strip()
    if not policy["allowed"] or not page_id:
        raise ValueError("awareness_copy_policy_failed")
    packet = {
        "contract_version": "beacon_litter_awareness_story_v1",
        "packet_type": "litter_awareness_story",
        "status": "ready_for_owner_review" if choice["selected"] else "missing_media",
        "campaign_objective": "farm_awareness", "campaign_lane": "live_stock_awareness",
        "objective": f"Share a warm farm-life update about {sow_name} and her litter",
        "story_subject": f"{sow_name} and her piglets", "story_context": story,
        "audience": "People who enjoy honest farm-life stories",
        "intended_channel": "Facebook Page organic", "draft_caption": caption,
        "target_page_id": page_id,
        "public_content_policy": public_livestock_policy_binding(
            policy, target_page_id=page_id),
        "call_to_action": "", "litter_media_selection": choice["selected"],
        "precise_media_request": "" if choice["selected"] else choice["request"],
        "media": ({"status": "exact_litter_public_media_selected"}
            if choice["selected"] else {"status": "missing_exact_litter_media"}),
        "sale_stock_evidence": {"source": "beacon_opportunity_scanner",
            "card_id": str(card.get("card_id") or ""),
            "observed_at": str((card.get("provenance") or {}).get("observed_at")
                or observed_at or opportunities.get("generated_at") or ""),
            "fresh": bool((card.get("freshness") or {}).get("fresh") is True),
            "story_context": story,
            "claim_boundary": "Internal trigger evidence only; no public stock or availability claim."},
        "sam_response_contract": {"lane": "live_stock_sales",
            "campaign_attribution_required": True, "inbound_only": True,
            "authority_boundary": "SAM may act only after genuine independently initiated attributed inbound."},
        "decision_options": ["approve", "correct", "decline"], "authority": dict(ZERO),
    }
    packet["packet_id"] = "BEACON-LITTER-STORY-" + _digest({
        "story": story, "copy": caption, "media": choice["selected"]})[:24].upper()
    return packet


def _litter_awareness_exception(reason, request):
    packet = {"contract_version": "beacon_litter_awareness_exception_v1",
        "packet_type": "litter_awareness_exception", "status": "missing_media",
        "precise_exception": reason, "precise_media_request": request,
        "authority": dict(ZERO)}
    packet["packet_id"] = "BEACON-LITTER-EXCEPTION-" + _digest(packet)[:24].upper()
    return packet


def _public_stock_subject(category):
    """Render canonical scanner categories without inventing product detail."""
    value = str(category or "livestock").strip().replace("_", " ")
    plurals = {"piglet": "piglets", "weaner": "weaners", "grower": "growers",
        "finisher": "finishers", "animal": "livestock", "animals": "livestock"}
    return plurals.get(value.casefold(), value)


def _natural_list(values):
    values = [str(value).strip() for value in values if str(value).strip()]
    if not values:
        return "livestock"
    if len(values) == 1:
        return values[0]
    return ", ".join(values[:-1]) + " or " + values[-1]


def handle_beacon_request(parsed: Mapping[str, Any], authority: Any, *,
        opportunity_loader: Callable = build_beacon_opportunity_cards,
        media_loader: Callable = list_media_intakes,
        content_evidence_loader: Callable = gather_beacon_content_evidence,
        content_candidate_builder: Callable = build_beacon_content_candidate,
        event_store=None):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), Mapping) else {}
    if (semantic.get("domain") != "beacon" or semantic.get("needs_clarification") is True
            or str(semantic.get("message_kind") or "") not in {"question", "request", "command"}):
        return {"handled": False}, 200
    provider_id = str(parsed.get("provider_message_id") or "")
    provider_time = str(parsed.get("provider_timestamp") or "")
    owner, chat = str(parsed.get("telegram_user_id") or ""), str(parsed.get("telegram_chat_id") or "")
    bound = bind_gateway_owner_authority(authority, "farm_manager_round")
    if not provider_id or not provider_time or not bound or bound.owner_user_id != owner or bound.private_chat_id != chat:
        return {"handled": False}, 200
    if str(semantic.get("intent") or "") == "private_media_library_review":
        return present_private_media_review(parsed)
    binding = {"owner": owner, "chat": chat, "provider_message_id": provider_id,
        "provider_timestamp": provider_time, "content_digest": _digest(parsed.get("text") or ""),
        "semantic_domain": "beacon", "semantic_intent": str(semantic.get("intent") or ""),
        "contract_version": CONTRACT_VERSION}
    mission_id = "OOM-BEACON-REQUEST-" + _digest(
        {"owner": owner, "chat": chat, "provider_message_id": provider_id})[:24].upper()
    store = event_store or _event_store
    try:
        prior = store("load", mission_id, None)
    except Exception:
        return {"handled": True, "success": False, "status": "beacon_request_persistence_unavailable",
            "mission_id": mission_id, **ZERO}, 503
    if prior:
        if prior.get("binding") != binding:
            return {"handled": True, "success": False, "status": "beacon_request_provider_binding_conflict",
                "mission_id": mission_id, **ZERO}, 409
        return {**(prior.get("result") or {}), "status": "beacon_request_replay_recovered"}, 200
    try:
        opportunities = opportunity_loader()
        if str(semantic.get("intent") or "") == "live_stock_awareness":
            content_evidence = content_evidence_loader(opportunity_result=opportunities)
            media_result = media_loader()
            media_payload = media_result[0] if isinstance(media_result, tuple) else media_result
            packet = build_live_stock_awareness_proposal(
                opportunities, content_candidate_builder(content_evidence), media_payload,
                language=str(semantic.get("language") or "en"))
        else:
            media_result = media_loader()
            media_payload = media_result[0] if isinstance(media_result, tuple) else media_result
            packet = build_current_beacon_proposal(opportunities, media_payload)
        answer = render_beacon_packet(packet, language=str(semantic.get("language") or "en"))
    except Exception as exc:
        return {"handled": True, "success": False, "status": "beacon_request_evidence_unavailable",
            "mission_id": mission_id, "error_type": exc.__class__.__name__,
            "answer": ("<b>BEACON — EVIDENCE REQUEST</b>\n\nThe current canonical sales opportunity "
                "could not be read, so I did not draft an availability claim or use private media. "
                "Please retry this same marketing request after the Supabase/Herdmaster and SAM evidence read is restored; "
                "no publication, spend, customer commitment or media-use decision is requested."), **ZERO}, 503
    output = {"handled": True, "success": True, "status": "beacon_request_ready",
        "specialist_identity": "BEACON", "mission_id": mission_id, "card_mission_id": mission_id,
        "answer": answer, "binding": binding, "proposal": packet,
        "result_digest": _digest({"binding": binding, "packet_id": packet["packet_id"], "answer": answer}), **ZERO}
    recorded = store("record", mission_id, {"binding": binding, "result": output})
    if not isinstance(recorded, Mapping) or recorded.get("success") is not True:
        return {"handled": True, "success": False, "status": "beacon_request_persistence_unproven",
            "mission_id": mission_id, **ZERO}, 503
    if recorded.get("created") is False:
        winner = store("load", mission_id, None) or {}
        if winner.get("binding") != binding:
            return {"handled": True, "success": False, "status": "beacon_request_provider_binding_conflict",
                "mission_id": mission_id, **ZERO}, 409
        return {**(winner.get("result") or {}), "status": "beacon_request_replay_recovered"}, 200
    return output, 200


def build_live_stock_awareness_proposal(opportunities, candidate, media_payload=None, *, language="en",
        target_page_id=None):
    """Normalize the existing awareness builder for the Oom Sakkie owner lane."""
    if not isinstance(opportunities, Mapping) or opportunities.get("success") is not True:
        raise ValueError("canonical_opportunity_evidence_required")
    if not isinstance(candidate, Mapping) or candidate.get("success") is not True:
        raise ValueError("awareness_candidate_required")
    review = candidate.get("owner_review_packet") or {}
    policy = review.get("public_livestock_policy") or {}
    if not review.get("draft_copy") or policy.get("policy_version") != POLICY_VERSION:
        raise ValueError("awareness_policy_proof_required")
    media_plan = _public_awareness_media(media_payload)
    if not media_plan:
        media_plan = {"status": "text_only",
            "reason": "No current public-use-approved, hash-verified farm asset was selected.",
            "request": "Optional: one portrait photo or short vertical video of piglets during a calm daily-care moment, with no people, vehicle plates, customer locations, illness or sales signage."}
    capacity = _awareness_capacity_context(opportunities)
    caption = str(review["draft_copy"])
    if str(language).casefold().startswith("af"):
        caption = ("'n Klein oomblik uit die lewe op Amadeus Farm. Geduldige daaglikse versorging "
            "vorm die alledaagse plaaslewe.\n\nVolg die plaas se reis vir meer eerlike oomblikke agter die skerms.")
    policy = assess_public_livestock_content(caption, objective="farm_awareness",
        campaign_lane="live_stock_awareness", media=([] if media_plan.get("status") == "text_only"
            else media_plan))
    page_id = str(target_page_id if target_page_id is not None
        else os.getenv("BEACON_FACEBOOK_PAGE_ID") or "").strip()
    if not policy["allowed"] or not page_id:
        raise ValueError("awareness_copy_policy_failed")
    af = str(language).casefold().startswith("af")
    packet = {"contract_version": "beacon_live_stock_awareness_proposal_v1",
        "packet_type": "live_stock_awareness_proposal", "status": "ready_for_owner_review",
        "objective": "Build familiarity and trust through a non-availability Amadeus Farm story",
        "audience": ("Mense wat belangstel in verantwoordelike plaaslike veeboerdery en plaaslewe" if af else
            str(review.get("audience") or "People interested in responsible local livestock and farm life")),
        "awareness_angle": ("Geduldige daaglikse versorging en eerlike plaaslewe agter die skerms" if af else
            "Patient daily care and honest behind-the-scenes farm life"),
        "intended_channel": "Facebook Page organic", "draft_caption": caption,
        "target_page_id": page_id,
        "public_content_policy": public_livestock_policy_binding(
            policy, target_page_id=page_id),
        "media": media_plan, "capacity_context": capacity,
        "sam_routing": ("Skryf antwoorde aan hierdie veldtog toe en roeteer koopnavrae as nuwe navrae na SAM Lewendehawe. SAM moet vraag, verkoopsbevoegdheid en lewering onafhanklik verifieer voor enige aanbod of verbintenis." if af else
            "Attribute replies to this campaign packet; route buying enquiries to SAM Live Stock as new enquiries. SAM must independently verify demand, sale eligibility and fulfilment before any offer or commitment."),
        "performance_measurement": ("Teken Facebook-bereik en betrokkenheid aan; tel veldtog-toegeskrewe gekwalifiseerde SAM-leidrade, omskakelings, voltooide verkope en toeskryfbare bruto wins afsonderlik. Onbekende waardes bly Onbekend en geen resultaat word afgelei nie." if af else
            "Record Facebook reach and engagement; count campaign-attributed qualified SAM leads, conversions, completed sales and attributable gross profit separately. Unknown values remain Unknown and no result is inferred."),
        "decision_options": ["approve", "correct", "decline"],
        "protected_owner_decision": "Approve this exact draft and selected media (if any) for the later protected publication step, Correct it, or Decline it.",
        "authority": dict(ZERO)}
    packet["packet_id"] = "BEACON-AWARENESS-" + _digest({"source_packet": review.get("packet_id"),
        "copy": packet["draft_caption"], "media": media_plan, "capacity": capacity})[:24].upper()
    return packet


def _awareness_capacity_context(opportunities):
    card = next((row for row in opportunities.get("cards") or []
        if isinstance(row, Mapping) and row.get("lane") == "live_stock"), None)
    if not card:
        return {"herdmaster_safe_fulfilment_capacity": "Unknown",
            "sam_quantified_buyer_demand": "Unknown", "sale_availability_inferred": False}
    blockers = set(card.get("blockers") or [])
    demand = card.get("demand_summary") or {}
    demand_unknown = bool(blockers.intersection({"sam_live_stock_demand_unavailable",
        "unknown_live_stock_demand_quantity", "incompatible_live_stock_demand",
        "invalid_live_stock_weight_requirement", "invalid_live_stock_sex_requirement",
        "malformed_live_stock_demand_evidence"}))
    return {"herdmaster_safe_fulfilment_capacity": "Unknown",
        "sam_quantified_buyer_demand": ("Unknown" if demand_unknown else int(demand.get("qualified_units") or 0)),
        "sale_availability_inferred": False,
        "explanation": "Herd capacity and buyer demand are independent signals. Neither animal counts nor this awareness proposal establish sale availability."}


def _public_awareness_media(payload, *, required_tags=None):
    rows = payload.get("items") if isinstance(payload, Mapping) and payload.get("success") is True else []
    for row in rows or []:
        digest = str(row.get("content_sha256") or "").lower()
        observation = row.get("observation") if isinstance(row.get("observation"), Mapping) else {}
        tags = {str(tag).casefold() for tag in
            (observation.get("tags") or observation.get("subject_tags") or [])}
        relevant = (bool(tags.intersection({str(tag).casefold() for tag in required_tags}))
            if required_tags else bool(tags.intersection(
                {"live_stock", "livestock", "piglet", "piglets", "litter", "weaner", "farm_life"})))
        if (row.get("latest_library_event") == "library_accepted"
                and (row.get("beacon_asset_id") or row.get("binary_asset_id"))
                and row.get("effective_public_use_approved") is True
                and row.get("current_library_accept_event_id")
                and row.get("current_public_use_event_id")
                and row.get("private_storage_proof_id")
                and re.fullmatch(r"[0-9a-f]{64}", digest)
                and relevant):
            return {"status": "approved_public_media_selected",
                "asset_id": str(row.get("beacon_asset_id") or row.get("binary_asset_id") or ""),
                "media_type": str(row.get("observed_mime_type") or "farm media"),
                "content_sha256": digest,
                "storage_readback_proof_id": str(row["private_storage_proof_id"]),
                "library_accept_event_id": str(row["current_library_accept_event_id"]),
                "public_use_event_id": str(row["current_public_use_event_id"])}
    return None


def select_litter_story_media(payload, *, litter_id, pig_ids, event_id):
    """Return only public-use media with exact canonical litter/pig/event linkage."""
    rows = payload.get("items") if isinstance(payload, Mapping) and payload.get("success") is True else []
    expected_pigs = {str(value) for value in pig_ids or [] if str(value).strip()}
    selected = []
    for row in rows or []:
        observation = row.get("observation") if isinstance(row.get("observation"), Mapping) else {}
        linked_pigs = {str(value) for value in observation.get("pig_ids") or [] if str(value).strip()}
        public_use = row.get("effective_public_use_approved")
        digest = str(row.get("content_sha256") or "").lower()
        asset_id = str(row.get("beacon_asset_id") or row.get("binary_asset_id") or "")
        if (str(observation.get("litter_id") or "") != str(litter_id)
                or str(observation.get("event_id") or "") != str(event_id)
                or not expected_pigs or expected_pigs != linked_pigs or not asset_id
                or row.get("latest_library_event") != "library_accepted"
                or public_use is not True
                or not row.get("current_library_accept_event_id")
                or not row.get("current_public_use_event_id")
                or not row.get("private_storage_proof_id")
                or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            continue
        selected.append({
            "asset_id": asset_id,
            "thumbnail_url": str(row.get("thumbnail_url") or ""),
            "capture_date": str(observation.get("captured_at") or row.get("observed_at") or ""),
            "source": str(observation.get("source") or row.get("source") or "canonical BEACON media library"),
            "litter_id": str(litter_id), "pig_ids": sorted(expected_pigs), "event_id": str(event_id),
            "content_sha256": digest,
            "library_accept_event_id": str(row["current_library_accept_event_id"]),
            "public_use_event_id": str(row["current_public_use_event_id"]),
            "storage_readback_proof_id": str(row["private_storage_proof_id"]),
            "public_use_authority": "approved",
        })
    return sorted(selected, key=lambda item: (
        item["asset_id"], item["content_sha256"], item["library_accept_event_id"],
        item["public_use_event_id"]))


def prepare_campaign_owner_card(packet, *, owner_user_id, private_chat_id,
        provider_message_id, packet_generation, target_page_id=None,
        claim_creator=create_claim):
    """Create the compact Telegram card and its exact single-use decision claim."""
    campaign = packet.get("protected_campaign_package") if isinstance(packet, Mapping) else None
    if not isinstance(campaign, Mapping):
        raise ValueError("beacon_protected_campaign_package_required")
    litter_media = packet.get("litter_media_selection") if isinstance(
        packet.get("litter_media_selection"), list) else []
    media = litter_media or campaign.get("selected_approved_media") or {"mode": "text_only"}
    bound_page_id = str(campaign.get("target_page_id")
        or packet.get("target_page_id") or "").strip()
    configured_page_id = str(target_page_id if target_page_id is not None
        else os.getenv("BEACON_FACEBOOK_PAGE_ID") or "").strip()
    if bound_page_id and configured_page_id and bound_page_id != configured_page_id:
        raise ValueError("beacon_campaign_target_page_changed")
    preview = {
        "contract_version": "beacon_campaign_owner_card_v1",
        "packet_id": str(packet.get("packet_id") or ""),
        "packet_generation": str(packet_generation or ""),
        "target_page_id": bound_page_id or configured_page_id,
        "exact_post_copy": str(campaign.get("exact_post_copy") or ""),
        "campaign_lane": str(campaign.get("campaign_lane") or ""),
        "campaign_objective": str(campaign.get("campaign_objective") or ""),
        "public_content_policy": dict(campaign.get("public_content_policy") or {}),
        "selected_media": media,
        "media_evidence_exception": str(campaign.get("media_evidence_exception") or ""),
        "audience": str(campaign.get("audience") or ""),
        "location": str(campaign.get("location") or ""),
        "publication_time": str(campaign.get("publication_time") or ""),
        "publication_timezone": "Africa/Johannesburg",
        "budget_cap": campaign.get("budget_cap") or {},
        "duration": campaign.get("duration") or {},
        "attribution_identity": str(campaign.get("attribution_identity") or ""),
        "story_context": dict((campaign.get("sale_stock_evidence") or {}).get("story_context") or {}),
        "stock_boundary": str((campaign.get("sale_stock_evidence") or {}).get("claim_boundary") or ""),
        "sam_boundary": str((campaign.get("sam_response_contract") or {}).get("authority_boundary") or ""),
        "stop_conditions": campaign.get("stop_conditions") or [],
        "rollback": campaign.get("rollback") or {},
        "approval_expires_at": str(campaign.get("approval_expires_at") or ""),
    }
    if not preview["packet_generation"]:
        raise ValueError("beacon_campaign_packet_generation_required")
    if not preview["target_page_id"]:
        raise ValueError("beacon_campaign_target_page_required")
    policy = assess_public_livestock_content(preview["exact_post_copy"],
        objective=preview["campaign_objective"], campaign_lane=preview["campaign_lane"],
        media=[] if media == {"mode": "text_only"} else media)
    if (not policy.get("allowed") or not public_livestock_policy_binding_matches(
            preview["public_content_policy"], policy,
            target_page_id=preview["target_page_id"])):
        raise ValueError("beacon_campaign_public_policy_binding_required")
    preview["campaign_digest"] = canonical_preview_digest(CAMPAIGN_REVIEW_ACTION, preview)
    claim = claim_creator(action_kind=CAMPAIGN_REVIEW_ACTION,
        owner_user_id=str(owner_user_id), private_chat_id=str(private_chat_id),
        mission_id=str(packet["packet_id"]), provider_message_id=str(provider_message_id),
        evidence_generation=preview["campaign_digest"], preview_payload=preview,
        expires_at=preview["approval_expires_at"])
    token = claim["callback_token"]
    budget = preview["budget_cap"]
    duration = preview["duration"]
    if litter_media:
        media_summary = "; ".join(
            f"{item['asset_id']} — {item.get('capture_date') or 'date Unknown'}, "
            f"{item.get('source') or 'source Unknown'}, Public Use approved"
            for item in litter_media)
    else:
        media_summary = (f"{media.get('asset_id')} (public-use approved)"
            if isinstance(media, Mapping) and media.get("asset_id") else "Text only")
    answer = "\n".join([
        "<b>BEACON — Facebook story</b>",
        (f"<b>Business objective:</b> {html.escape(str(packet.get('objective') or 'Qualified livestock enquiries'))}"
            if preview["campaign_lane"] == "live_stock_enquiry_capture" else
            f"<b>Story:</b> {html.escape(str(packet.get('story_subject') or packet.get('objective') or 'Farm life'))}"),
        f"<b>Post:</b> {html.escape(preview['exact_post_copy'])}",
        f"<b>Pictures:</b> {html.escape(media_summary)}",
        f"<b>Facebook Page ID:</b> {html.escape(preview['target_page_id'])} (bound from BEACON_FACEBOOK_PAGE_ID and re-read before Meta)",
        f"<b>Publish by:</b> {html.escape(preview['publication_time'])}",
        f"<b>Spend/duration:</b> ZAR {html.escape(str(budget.get('total') or '0.00'))} total; ZAR {html.escape(str(budget.get('daily') or '0.00'))} daily; {html.escape(str(duration.get('days') if duration.get('days') is not None else 0))} days; no boost.",
        ("<b>Boundary:</b> Organic enquiry capture only. SAM qualification follows genuine inbound; no stock, price, availability, delivery, reservation, outcome or spend promise."
            if preview["campaign_lane"] == "live_stock_enquiry_capture" else
            "<b>Boundary:</b> Organic awareness only. No sales claim, call to action, spend or customer send."),
        "<b>Meta proof:</b> Success requires exact provider readback of the created post ID, bound Page and exact copy. Missing, mismatched or ambiguous readback is terminally contained with no automatic retry.",
    ])
    rows = [[
        {"text": "Approve", "callback_data": f"{CALLBACK_PREFIX}{token}:confirm"},
        {"text": "Correct", "callback_data": f"{CALLBACK_PREFIX}{token}:change"},
        {"text": "Decline", "callback_data": f"{CALLBACK_PREFIX}{token}:cancel"},
    ]]
    if not litter_media and preview["media_evidence_exception"]:
        answer += "\n<b>Media evidence exception:</b> " + html.escape(
            preview["media_evidence_exception"])
    markup = {"inline_keyboard": rows}
    return {"answer": answer, "reply_markup": markup, "callback_token": token,
        "preview_digest": claim.get("preview_digest") or preview["campaign_digest"],
        "action_kind": CAMPAIGN_REVIEW_ACTION,
        "card_mission_id": packet["packet_id"], "campaign_review_preview": preview}


def build_litter_media_choice(payload, *, litter_id, pig_ids, event_id, subject):
    selected = select_litter_story_media(payload, litter_id=litter_id,
        pig_ids=pig_ids, event_id=event_id)
    if selected:
        return {"status": "eligible_litter_media", "selected": selected,
            "question": "Use these photos?"}
    return {"status": "precise_media_request", "selected": [],
        "request": (f"Please send one current portrait photo of {subject}, linked to litter "
            f"{litter_id} and event {event_id}, with capture date/source and explicit Public Use approval; "
            "exclude people, plates, customer locations, illness, prices and sales signage.")}


def build_current_beacon_proposal(opportunities, media_payload):
    if not isinstance(opportunities, Mapping) or opportunities.get("success") is not True:
        raise ValueError("canonical_opportunity_evidence_required")
    cards = [row for row in opportunities.get("cards") or [] if isinstance(row, Mapping)]
    all_cards = cards
    cards = [row for row in cards if row.get("status") == "ready_for_owner_review"]
    if not cards:
        return _current_evidence_request(all_cards, opportunities)
    card = cards[0]
    cap = int((card.get("capacity_calculation") or {}).get("demand_cap") or 0)
    evidence_id = str(card.get("card_id") or "")
    ready = cap > 0
    assertion = (f"{cap} evidence-qualified {card.get('unit') or 'units'} can be promoted without exceeding the current demand cap."
                 if ready else "Current evidence does not support a public availability claim.")
    evidence = [{"evidence_id": evidence_id, "source_id": "beacon_opportunity_scanner",
        "observed_at": str((card.get("provenance") or {}).get("observed_at") or opportunities.get("generated_at") or ""),
        "statement": str(card.get("opportunity_reason") or ""), "claim_types": ["availability"],
        "supported_assertions": ([{"assertion_id": evidence_id + ":cap", "claim_type": "availability",
            "text": assertion}] if ready else []), "status": "verified"}]
    category = str(card.get("category") or "farm offer").replace("_", " ")
    objective = {"objective_id": evidence_id, "summary": f"Generate qualified enquiries for {category}",
        "business_reason": str(card.get("opportunity_reason") or "Reconcile current supply and demand before marketing."),
        "expected_commercial_value": (f"Create enquiries for up to {cap} currently supportable {card.get('unit') or 'units'}; no sale is assumed."
            if ready else "Avoid unsupported promotion while obtaining one useful campaign asset."),
        "performance_measurement": "After any separately approved publication, record reach, qualified enquiries, conversions and attributable gross sales; do not infer results.",
        "evidence": evidence, "media_mode": "single",
        "media_tags": [str(card.get("lane") or ""), str(card.get("category") or "")],
        "missing_media": {"subject": category, "angle": "clearly showing the product in its current farm context",
            "orientation": "portrait", "purpose": f"an organic {category} enquiry campaign"}}
    draft = {"audience": "Local buyers actively considering Amadeus Farm products",
        "channel": "facebook_organic", "caption": assertion,
        "call_to_action": "Message us to discuss what you need; availability will be confirmed before any commitment.",
        "claims": [{"text": assertion, "claim_types": ["availability"], "evidence_ids": [evidence_id],
            "classification_authority": "server_claim_classification_v1", "classification_proof_id": evidence_id + ":classification",
            "placement": "caption"}, {"text": "Message us to discuss what you need; availability will be confirmed before any commitment.",
            "claim_types": ["audience_action"], "evidence_ids": [], "classification_authority": "server_claim_classification_v1",
            "classification_proof_id": evidence_id + ":cta", "placement": "call_to_action"}]}
    return prepare_marketing_proposal(objective, _project_media(media_payload, objective["media_tags"]), draft)


def _current_evidence_request(cards, opportunities):
    blockers = sorted({str(item) for card in cards for item in card.get("blockers") or []})
    evidence = [{"card_id": str(card.get("card_id") or ""),
        "category": str(card.get("category") or ""), "status": str(card.get("status") or ""),
        "observed_at": str((card.get("provenance") or {}).get("observed_at") or ""),
        "demand_cap": int((card.get("capacity_calculation") or {}).get("demand_cap") or 0),
        "blockers": list(card.get("blockers") or [])} for card in cards]
    packet = {"contract_version": "beacon_marketing_evidence_request_v1",
        "packet_type": "marketing_evidence_request", "status": "needs_current_commercial_evidence",
        "objective": "Choose the next profitable, supportable farm marketing campaign",
        "audience": "Unknown until quantified current buyer demand or an owner-selected awareness objective exists",
        "factual_evidence": evidence, "available_media": "Not evaluated because no supportable commercial objective exists",
        "missing_media": "No media request is justified until the commercial objective is supported",
        "intended_channel": "No channel recommended yet", "recommended_copy": "Withheld: no supported availability or demand claim",
        "expected_commercial_value": "Avoid spending owner attention or public trust on an offer with zero evidenced demand cap",
        "performance_measurement": "After a supported campaign exists, record reach, qualified enquiries, conversions and attributable gross sales",
        "missing_evidence": blockers,
        "decision_options": ["wait_for_quantified_demand", "prepare_non_availability_awareness_campaign"],
        "protected_owner_decision": "Wait for quantified buyer demand, or choose a non-availability farm-awareness objective",
        "authority": dict(ZERO)}
    packet["packet_id"] = "BEACON-EVIDENCE-" + _digest({"evidence": evidence})[:24].upper()
    return packet


def _project_media(payload, tags):
    items = payload.get("items") if isinstance(payload, Mapping) and payload.get("success") is True else []
    projected = []
    for row in items or []:
        if (row.get("latest_library_event") != "library_accepted" or not row.get("binary_asset_id")
                or not row.get("current_library_accept_event_id")
                or not row.get("private_storage_proof_id") or not row.get("thumbnail_url")):
            continue
        observed = row.get("observation") if isinstance(row.get("observation"), Mapping) else {}
        row_tags = list(observed.get("tags") or observed.get("subject_tags") or [])
        if not set(row_tags).intersection(tags):
            continue
        projected.append({"asset_id": str(row["binary_asset_id"]), "content_sha256": str(row.get("content_sha256") or ""),
            "storage_proof_id": str(row["private_storage_proof_id"]),
            "review_event_id": str(row["current_library_accept_event_id"]),
            "current_review_proof_id": str(row["current_library_accept_event_id"]),
            "private_preview_ref": str(row["thumbnail_url"]),
            "private_storage": True, "projection_authority": "server_resolved_current_media_v1",
            "review_status": "library_accepted", "tags": row_tags, "purpose": "private proposal review only"})
    return projected


def render_beacon_packet(packet, *, language="en"):
    af = str(language).casefold().startswith("af")
    if packet.get("packet_type") == "litter_awareness_story":
        media = packet.get("litter_media_selection") or []
        if not media:
            lines = ["<b>BEACON — ONE MEDIA EXCEPTION</b>", "",
                "No exact litter-linked image with current Public Use authority is available.",
                "<b>Smallest governed decision:</b> " + html.escape(
                    str(packet.get("precise_media_request") or "")),
                "No approval card was created and nothing can be published."]
        else:
            lines = ["<b>BEACON — FACEBOOK STORY</b>", "",
                f"<b>Story:</b> {html.escape(str(packet.get('story_subject') or ''))}",
                f"<b>Post:</b> {html.escape(str(packet.get('draft_caption') or ''))}",
                "<b>Pictures:</b> " + html.escape("; ".join(
                    f"{item.get('asset_id')} — preview {item.get('thumbnail_url') or 'unavailable'}"
                    for item in media)),
                "<b>Boundary:</b> Organic awareness only; no availability, sale, price, booking, urgency, contact invitation, spend or customer send.",
                "<b>Choose:</b> Approve / Correct / Decline."]
    elif packet.get("packet_type") == "litter_awareness_exception":
        lines = ["<b>BEACON — ONE MEDIA EXCEPTION</b>", "",
            html.escape(str(packet.get("precise_exception") or "")),
            "<b>Smallest governed decision:</b> " + html.escape(
                str(packet.get("precise_media_request") or "")),
            "No card was created and nothing can be published."]
    elif packet.get("packet_type") == "livestock_enquiry_capture_proposal":
        evidence = packet.get("business_offering_evidence") or {}
        sam = packet.get("sam_response_contract") or {}
        campaign = packet.get("protected_campaign_package") or {}
        lines = ["<b>BEACON — LIVESTOCK ENQUIRY POST</b>", "",
            f"<b>Business objective:</b> {html.escape(str(packet.get('objective') or ''))}",
            f"<b>Audience:</b> {html.escape(str(packet.get('audience') or ''))}",
            f"<b>Supported offering:</b> {html.escape(str(evidence.get('offering_label') or ''))} — enquiries only; availability is not inferred.",
            f"<b>Exact copy:</b>\n{html.escape(str(packet.get('draft_caption') or ''))}",
            "<b>Media:</b> Text only.",
            f"<b>SAM handoff:</b> campaign {html.escape(str(campaign.get('attribution_identity') or ''))}; qualify {html.escape(', '.join(sam.get('qualification_fields') or []))}.",
            f"<b>Boundary:</b> {html.escape(str(sam.get('authority_boundary') or ''))}",
            "<b>Distribution:</b> Organic Facebook only; no boost, spend or duration.",
            "<b>Choose:</b> Approve / Correct / Decline. Approval authorizes one protected attempt only."]
    elif packet.get("packet_type") == "sale_ready_demand_proposal":
        media = packet.get("media") or {}
        stock = packet.get("sale_stock_evidence") or {}
        sam = packet.get("sam_response_contract") or {}
        media_text = ("Public-use-approved, hash-verified livestock media selected."
            if media.get("status") == "approved_public_media_selected" else
            "Governed text-only campaign; no private-media authority is inferred. " +
            str(media.get("request") or ""))
        lines = ["<b>BEACON — SALE-READY DEMAND PROPOSAL</b>", "",
            f"<b>Objective:</b> {html.escape(str(packet.get('objective') or ''))}",
            f"<b>Audience:</b> {html.escape(str(packet.get('audience') or ''))}",
            f"<b>Current canonical proposition:</b> {html.escape(str(stock.get('category') or ''))} enquiries; evidence card {html.escape(str(stock.get('card_id') or ''))}, observed {html.escape(str(stock.get('observed_at') or ''))}. The evidence cap is retained internally and no quantity is promised in public copy.",
            f"<b>Exact copy:</b>\n{html.escape(str(packet.get('draft_caption') or ''))}",
            f"<b>CTA:</b> {html.escape(str(packet.get('call_to_action') or ''))}",
            f"<b>Media:</b> {html.escape(media_text)}",
            f"<b>SAM handoff:</b> {html.escape(str(sam.get('lane') or ''))} / {html.escape(str(sam.get('supported_response_class') or ''))}; qualify {html.escape(', '.join(sam.get('qualification_fields') or []))}.",
            f"<b>Authority boundary:</b> {html.escape(str(sam.get('authority_boundary') or ''))}",
            f"<b>Measure:</b> {html.escape(str(packet.get('performance_measurement') or ''))}",
            "<b>Choose:</b> Approve / Correct / Decline. Nothing is published or spent by this decision response."]
        campaign = packet.get("protected_campaign_package") or {}
        if campaign:
            budget = campaign.get("budget_cap") or {}
            selected = campaign.get("selected_approved_media") or {}
            selected_summary = (", ".join(str(item.get("asset_id") or "") for item in selected)
                if isinstance(selected, list) else str(selected.get("asset_id") or selected.get("mode") or "none"))
            lines.extend(("", "<b>EXACT PROTECTED FACEBOOK CAMPAIGN</b>",
                f"<b>Post:</b> {html.escape(str(campaign.get('exact_post_copy') or ''))}",
                f"<b>Media:</b> {html.escape(selected_summary)}",
                f"<b>Audience/location:</b> {html.escape(str(campaign.get('audience') or ''))}; {html.escape(str(campaign.get('location') or ''))}",
                f"<b>Publish:</b> {html.escape(str(campaign.get('publication_time') or ''))}",
                f"<b>Boost:</b> {html.escape(str(campaign.get('boost_objective') or ''))}; ZAR {html.escape(str(budget.get('total') or '0'))} total / ZAR {html.escape(str(budget.get('daily') or '0'))} daily; 3 days",
                f"<b>Attribution:</b> {html.escape(str(campaign.get('attribution_identity') or ''))}",
                "<b>Stop:</b> spend cap, duration, revoked authority/evidence change, or ambiguous/provider failure.",
                "<b>Rollback:</b> no automatic publication or spend retry; stop boost and preserve provider chronology.",
                "<b>Protected decision:</b> Approve this exact publication and boost envelope / Correct / Decline. Approval authorizes BEACON—not this message—to execute and obtain Meta readback."))
    elif packet.get("packet_type") == "sale_ready_stock_evidence_request":
        lines = ["<b>BEACON — PRECISE SALE-STOCK EVIDENCE REQUEST</b>", "",
            f"<b>Objective:</b> {html.escape(str(packet.get('objective') or ''))}",
            f"<b>Exception:</b> {html.escape(str(packet.get('precise_exception') or ''))}",
            f"<b>Required evidence:</b> {html.escape(str(packet.get('required_evidence') or ''))}",
            "<b>Media/copy:</b> Not selected or drafted because no supportable sale-stock proposition exists.",
            "<b>Protected decision:</b> None. Publication and spend remain blocked."]
    elif packet.get("packet_type") == "live_stock_awareness_proposal":
        media = packet.get("media") or {}
        media_text = (("'n Goedgekeurde plaasfoto is gekies; openbare-gebruiktoestemming en lêerintegriteit is bevestig."
                if af else "An approved farm photo is selected; public-use authority and file integrity are verified.")
            if media.get("status") == "approved_public_media_selected" else
            (("Teks alleen is geskik. Opsioneel: een portretfoto of kort vertikale video van varkies tydens 'n rustige daaglikse versorgingsoomblik; geen mense, nommerplate, kliëntliggings, siekte of verkoopstekens nie."
                if af else f"Text-only is suitable. {media.get('request') or ''}")))
        capacity = packet.get("capacity_context") or {}
        lines = ["<b>BEACON — PLAASBEWUSTHEIDSVOORSTEL</b>" if af else "<b>BEACON — FARM-AWARENESS PROPOSAL</b>", "",
            f"<b>{'Teikengehoor' if af else 'Audience'}:</b> {html.escape(str(packet.get('audience') or ''))}",
            f"<b>{'Storiehoek' if af else 'Story angle'}:</b> {html.escape(str(packet.get('awareness_angle') or ''))}",
            f"<b>{'Kanaal' if af else 'Channel'}:</b> {html.escape(str(packet.get('intended_channel') or ''))}",
            f"<b>{'Veilige konsepkopie' if af else 'Safe draft copy'}:</b>\n{html.escape(str(packet.get('draft_caption') or ''))}",
            f"<b>Media:</b> {html.escape(media_text)}",
            (f"<b>Bewysgrens:</b> Veilige leweringskapasiteit: {html.escape(str(capacity.get('herdmaster_safe_fulfilment_capacity')))}; gekwantifiseerde SAM-vraag: {html.escape(str(capacity.get('sam_quantified_buyer_demand')))}. Geen verkoopsbeskikbaarheid word afgelei nie." if af else
             f"<b>Evidence boundary:</b> Safe fulfilment capacity: {html.escape(str(capacity.get('herdmaster_safe_fulfilment_capacity')))}; quantified SAM demand: {html.escape(str(capacity.get('sam_quantified_buyer_demand')))}. No sale availability is inferred."),
            f"<b>{'SAM-toeskrywing/roetering' if af else 'SAM attribution/routing'}:</b> {html.escape(str(packet.get('sam_routing') or ''))}",
            f"<b>{'Meting' if af else 'Measure'}:</b> {html.escape(str(packet.get('performance_measurement') or ''))}",
            ("<b>Kies:</b> Keur goed / Korrigeer / Wys af. Niks word deur hierdie besluit gepubliseer of bestee nie." if af else
             "<b>Choose:</b> Approve / Correct / Decline. Nothing is published or spent by this decision response.")]
        campaign = packet.get("protected_campaign_package") or {}
        if campaign:
            budget = campaign.get("budget_cap") or {}
            selected = campaign.get("selected_approved_media") or {}
            selected_summary = (", ".join(str(item.get("asset_id") or "") for item in selected)
                if isinstance(selected, list) else str(selected.get("asset_id") or selected.get("mode") or "none"))
            lines.extend(("", "<b>EXACT PROTECTED FACEBOOK CAMPAIGN</b>",
                f"<b>Post:</b> {html.escape(str(campaign.get('exact_post_copy') or ''))}",
                f"<b>Media:</b> {html.escape(selected_summary)}",
                f"<b>Audience/location:</b> {html.escape(str(campaign.get('audience') or ''))}; {html.escape(str(campaign.get('location') or ''))}",
                f"<b>Publish:</b> {html.escape(str(campaign.get('publication_time') or ''))}",
                f"<b>Boost:</b> {html.escape(str(campaign.get('boost_objective') or ''))}; ZAR {html.escape(str(budget.get('total') or '0'))} total / ZAR {html.escape(str(budget.get('daily') or '0'))} daily; 3 days",
                f"<b>Attribution:</b> {html.escape(str(campaign.get('attribution_identity') or ''))}",
                "<b>Stop:</b> spend cap, duration, revoked authority/evidence change, or ambiguous/provider failure.",
                "<b>Rollback:</b> no automatic publication or spend retry; stop boost and preserve provider chronology.",
                "<b>Protected decision:</b> Approve this exact publication and boost envelope / Correct / Decline. Approval authorizes BEACON—not this message—to execute and obtain Meta readback."))
    elif packet.get("packet_type") == "marketing_evidence_request":
        blockers = ", ".join(packet.get("missing_evidence") or [])
        lines = ["<b>BEACON — CURRENT EVIDENCE REQUEST</b>", "",
            f"<b>Objective:</b> {html.escape(str(packet.get('objective') or ''))}",
            f"<b>Audience:</b> {html.escape(str(packet.get('audience') or ''))}",
            "<b>Supported current evidence:</b> Current sales evidence does not support an availability campaign.",
            "<b>Missing evidence:</b> A quantified current buyer need matched to independently verified safe fulfilment capacity.",
            f"<b>Media:</b> {html.escape(str(packet.get('available_media') or ''))}; {html.escape(str(packet.get('missing_media') or ''))}",
            f"<b>Channel/copy:</b> {html.escape(str(packet.get('intended_channel') or ''))}; {html.escape(str(packet.get('recommended_copy') or ''))}",
            f"<b>Expected value:</b> {html.escape(str(packet.get('expected_commercial_value') or ''))}",
            f"<b>Measure later:</b> {html.escape(str(packet.get('performance_measurement') or ''))}",
            f"<b>One protected decision:</b> {html.escape(str(packet.get('protected_owner_decision') or ''))}."]
    elif packet.get("packet_type") == "missing_media_request":
        shot = (packet.get("shot_list") or [{}])[0]
        lines = ["<b>BEACON — PRESIESE MEDIA-VERSOEK</b>" if af else "<b>BEACON — PRECISE MEDIA REQUEST</b>", "",
            f"<b>{'Doel' if af else 'Objective'}:</b> {html.escape(str(packet.get('objective') or ''))}",
            ((f"Neem asseblief een portretfoto van {html.escape(str(shot.get('subject') or ''))}, {html.escape(str(shot.get('angle') or ''))}." if af else
              f"Please take one portrait photo of {html.escape(str(shot.get('subject') or ''))}, {html.escape(str(shot.get('angle') or ''))}.")),
            (("<b>Teikengehoor:</b> Plaaslike kopers wat Amadeus Farm-produkte oorweeg." if af else "<b>Audience:</b> Local buyers actively considering Amadeus Farm products.")),
            f"<b>{'Bewyse' if af else 'Evidence'}:</b> {html.escape('; '.join(str(e.get('statement') or '') for e in packet.get('evidence') or []))}",
            (("<b>Media:</b> Geen huidige Biblioteek-Aanvaarde bate het volledige private stoor-, huidige hersiening- en private voorskoubewys vir hierdie doel nie." if af else "<b>Media:</b> No current Library Accepted asset has complete private-storage, current-review and private-preview proof for this objective.")),
            f"<b>{'Aanbevole kanaal/kopie' if af else 'Recommended channel/copy'}:</b> Facebook organic — {html.escape(str(packet.get('recommended_copy_after_media') or ''))}",
            f"<b>{'Verwagte waarde' if af else 'Expected value'}:</b> {html.escape(str(packet.get('expected_commercial_value') or ''))}",
            f"<b>{'Meet later' if af else 'Measure later'}:</b> {html.escape(str(packet.get('performance_measurement') or ''))}",
            ("<b>Een besluit:</b> Stuur dié foto, of sê ‘ander veldtog’." if af else
             "<b>One decision:</b> Send that photo, or say ‘different campaign’.")]
    else:
        evidence = "; ".join(str(e.get("statement") or "") for e in packet.get("factual_evidence") or [])
        asset_ids = ", ".join(str(row.get("asset_id") or "") for row in packet.get("exact_media") or [])
        lines = ["<b>BEACON — BEMARKINGSVOORSTEL</b>" if af else "<b>BEACON — MARKETING PROPOSAL</b>", "",
            f"<b>{'Doel' if af else 'Objective'}:</b> {html.escape(str(packet.get('objective') or ''))}",
            f"<b>{'Teikengehoor' if af else 'Audience'}:</b> {html.escape(str(packet.get('audience') or ''))}", f"<b>{'Bewyse' if af else 'Evidence'}:</b> {html.escape(evidence)}",
            f"<b>Media:</b> {html.escape(asset_ids)} — private Library Accepted; public use is not approved.",
            f"<b>{'Kanaal' if af else 'Channel'}:</b> {html.escape(str(packet.get('intended_channel') or ''))}",
            f"<b>{'Kopie' if af else 'Copy'}:</b> {html.escape(str(packet.get('draft_caption') or ''))}",
            f"<b>CTA:</b> {html.escape(str(packet.get('call_to_action') or ''))}",
            f"<b>Expected value:</b> {html.escape(str(packet.get('expected_commercial_value') or ''))}",
            f"<b>Measure later:</b> {html.escape(str(packet.get('performance_measurement') or ''))}",
            "<b>One protected decision:</b> Approve this exact organic campaign (including this asset's public use and the exact post) / Correct / Decline. No spend or customer commitment is included, and nothing is published by this request."]
    answer = "\n".join(lines)
    if len(answer) > 3900:
        raise ValueError("beacon_request_render_budget_exceeded")
    return answer


def _event_store(action, identity, payload):
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    if action == "load":
        import os, psycopg
        with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'beacon_request' from public.sam_live_stock_conversation_review_events
                    where event_source=%s and review_event_id=%s limit 1""", (EVENT_SOURCE, identity))
                row = cursor.fetchone(); return row[0] if row else None
    event = build_sam_live_stock_review_event({"conversation_id": identity}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "beacon_request"}, event_source=EVENT_SOURCE)
    event.update({"review_event_id": identity, "chatwoot_conversation_id": identity,
        "review_json": {"beacon_request": payload}, "decision_json": {}, "facts_json": {},
        "customer_message_excerpt": "", "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event)
    return {**result, "success": status < 400 and result.get("success") is True,
        "created": result.get("created", status < 300)}


def _digest(value):
    raw = value if isinstance(value, str) else json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()
