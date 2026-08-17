"""Authenticated, read-only Oom Sakkie to BEACON proposal lifecycle."""
from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any, Callable, Mapping

from modules.beacon.marketing_proposal import prepare_marketing_proposal
from modules.beacon.media_intake import list_media_intakes
from modules.beacon.opportunity_scanner import build_beacon_opportunity_cards
from modules.beacon.public_livestock_content_policy import assess_public_livestock_content
from modules.beacon.content_operations import (
    build_beacon_content_candidate,
    gather_beacon_content_evidence,
)
from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.oom_sakkie.beacon_media_review_runtime import present_private_media_review

CONTRACT_VERSION = "oom_sakkie_beacon_request_v1"
EVENT_SOURCE = "oom_sakkie_beacon_request"
ZERO = {"writes_farm_data": False, "writes_media": False, "publishes": False,
        "spends_money": False, "customer_sends": False,
        "protected_actions_performed": False}


def build_scheduled_sale_ready_stock_result(*, opportunity_loader=build_beacon_opportunity_cards,
        media_loader=list_media_intakes, content_evidence_loader=gather_beacon_content_evidence,
        content_candidate_builder=build_beacon_content_candidate, now=None):
    """Compose one internal BEACON result from current canonical evidence."""
    opportunities = opportunity_loader()
    media_result = media_loader()
    media_payload = media_result[0] if isinstance(media_result, tuple) else media_result
    evidence_time = _stable_opportunity_time(opportunities, fallback=now)
    # Keep the legacy awareness dependencies injectable for caller compatibility,
    # but a scheduled revenue case must use the sale-ready demand contract.  An
    # awareness/follow packet is never silently upgraded into a messages campaign.
    packet = build_sale_ready_demand_proposal(opportunities, media_payload,
        observed_at=evidence_time)
    if packet.get("status") == "ready_for_owner_review":
        packet = build_protected_campaign_package(packet, now=evidence_time)
    return {
        "success": True,
        "status": ("beacon_sale_ready_stock_proposal_ready" if
            packet.get("protected_campaign_package") else
            "beacon_sale_ready_stock_evidence_request"),
        "answer": render_beacon_packet(packet, language="en"),
        "proposal": packet,
        "result_digest": _digest(packet),
        "follow_up_owner": "BEACON",
        "next_trigger": "material canonical stock or media evidence change",
        **ZERO,
    }


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
    exact_media = ({key: media.get(key) for key in (
        "asset_id", "media_type", "content_sha256", "storage_readback_proof_id",
        "library_accept_event_id", "public_use_event_id")}
        if media.get("status") == "approved_public_media_selected" else {"mode": "text_only"})
    exact_copy = str(packet.get("draft_caption") or packet.get("recommended_copy") or "").strip()
    if not exact_copy:
        raise ValueError("beacon_campaign_exact_copy_required")
    objective = str(packet.get("campaign_objective") or "").strip()
    cta = str(packet.get("call_to_action") or "").strip()
    stock = packet.get("sale_stock_evidence") if isinstance(
        packet.get("sale_stock_evidence"), Mapping) else {}
    sam = packet.get("sam_response_contract") if isinstance(
        packet.get("sam_response_contract"), Mapping) else {}
    if objective != "facebook_messaging_conversations":
        raise ValueError("beacon_campaign_messages_objective_required")
    qualification_fields = {str(value) for value in sam.get("qualification_fields") or []}
    required_qualification = {"animal_type", "quantity", "intended_use", "customer_area"}
    if (not re.search(r"\bmessage\s+(?:amadeus(?:\s+farm)?|us)\b", cta, re.I)
            or not re.search(r"\b(?:animal|livestock|pig|weaner)\b", cta, re.I)
            or not re.search(r"\b(?:number|quantity|how many)\b", cta, re.I)
            or not re.search(r"\b(?:intended use|need them for|looking for)\b", cta, re.I)
            or not re.search(r"\b(?:area|location|town)\b", cta, re.I)):
        raise ValueError("beacon_campaign_useful_message_cta_required")
    if re.search(r"\bfollow\b", exact_copy, re.I) and not re.search(
            r"\b(?:enquir|looking for|need)\w*\b", exact_copy, re.I):
        raise ValueError("beacon_campaign_awareness_copy_messages_mismatch")
    if (stock.get("source") != "beacon_opportunity_scanner"
            or stock.get("status") != "ready_for_owner_review"
            or int(stock.get("demand_cap") or 0) <= 0
            or not stock.get("card_id") or not stock.get("observed_at")):
        raise ValueError("beacon_campaign_canonical_sale_stock_required")
    if (sam.get("lane") != "live_stock_sales"
            or sam.get("supported_response_class") != "clarification"
            or not sam.get("campaign_attribution_required")
            or qualification_fields != required_qualification):
        raise ValueError("beacon_campaign_sam_response_contract_required")
    envelope = {
        "contract_version": "beacon_protected_facebook_campaign_package_v1",
        "delivery_due_policy": "same_cycle_on_new_or_changed_evidence",
        "source_packet_id": packet["packet_id"], "exact_post_copy": exact_copy,
        "selected_approved_media": exact_media,
        "audience": str(packet.get("audience") or "Local people interested in responsible livestock and farm life"),
        "location": "Riversdale and Albertinia, Western Cape, South Africa",
        "publication_time": publication.isoformat(), "publication_timezone": "Africa/Johannesburg",
        "approval_expires_at": publication.isoformat(),
        "boost_objective": "Facebook messaging conversations",
        "campaign_objective": objective,
        "call_to_action": cta,
        "sale_stock_evidence": dict(stock),
        "sam_response_contract": dict(sam),
        "budget_cap": {"currency": "ZAR", "total": "300.00", "daily": "100.00"},
        "duration": {"days": 3},
        "stop_conditions": ["total_spend_reaches_ZAR_300", "three_day_duration_expires",
            "public_use_or_campaign_authority_is_revoked", "canonical_sale_eligibility_materially_changes",
            "provider_rejects_or_returns_ambiguous_publication_or_spend_state"],
        "rollback": {
            "on_publication_failure": "do_not_retry; retain provider chronology and stop boost",
            "on_boost_failure": "stop the campaign; do not retry spend; retain the organic post only if provider-confirmed",
            "on_authority_or_evidence_change": "pause/stop provider campaign and preserve immutable readback"},
        "authority": {"publication_authorized": False, "boost_authorized": False,
            "spend_authorized": False, "customer_send_authorized": False, "approval_required": True}}
    envelope["attribution_identity"] = "BEACON-CAMPAIGN-" + _digest(envelope)[:24].upper()
    envelope["sam_response_contract"]["campaign_attribution_id"] = envelope["attribution_identity"]
    envelope["approval_card"] = {
        "decision": "Approve this exact Facebook publication and boost envelope before its publication time / Correct / Decline",
        "approval_effect": "authorization only; BEACON must execute and obtain Meta readback",
        "requested_authority": "one publication attempt and one Meta boost capped at ZAR 300 for 3 days"}
    return {**packet, "protected_campaign_package": envelope}


def build_sale_ready_demand_proposal(opportunities, media_payload, *, observed_at=None):
    """Build commercially coherent, claim-bounded demand copy or one exception."""
    if not isinstance(opportunities, Mapping) or opportunities.get("success") is not True:
        raise ValueError("canonical_opportunity_evidence_required")
    cards = [row for row in opportunities.get("cards") or [] if isinstance(row, Mapping)]
    ready = [row for row in cards if row.get("lane") == "live_stock"
        and row.get("status") == "ready_for_owner_review"
        and not (row.get("blockers") or [])
        and int((row.get("capacity_calculation") or {}).get("demand_cap") or 0) > 0]
    if not ready:
        packet = _current_evidence_request(cards, opportunities)
        packet.update({
            "contract_version": "beacon_sale_ready_demand_exception_v1",
            "packet_type": "sale_ready_stock_evidence_request",
            "objective": "Generate qualified livestock enquiries through Facebook messages",
            "precise_exception": "No current unblocked canonical live-stock opportunity has a positive sale-ready demand cap.",
            "required_evidence": "A fresh BEACON opportunity card backed by canonical sale-eligible stock and a positive fulfilment cap.",
            "decision_options": ["wait_for_canonical_stock_evidence", "correct"],
            "protected_owner_decision": "None: publication and spend are ineligible until canonical sale-ready stock exists.",
        })
        packet["packet_id"] = "BEACON-DEMAND-EXCEPTION-" + _digest({
            "evidence": packet.get("factual_evidence"),
            "required_evidence": packet["required_evidence"]})[:24].upper()
        return packet
    card = ready[0]
    provenance = card.get("provenance") if isinstance(card.get("provenance"), Mapping) else {}
    stock = {
        "source": "beacon_opportunity_scanner",
        "card_id": str(card.get("card_id") or ""),
        "observed_at": str(provenance.get("observed_at") or observed_at or opportunities.get("generated_at") or ""),
        "status": "ready_for_owner_review",
        "category": str(card.get("category") or "livestock").replace("_", " "),
        "unit": str(card.get("unit") or "animals"),
        "demand_cap": int((card.get("capacity_calculation") or {}).get("demand_cap") or 0),
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
        }),
        "claim_boundary": "Supports taking enquiries only; SAM must re-read canonical stock before any offer or commitment.",
    }
    if not stock["card_id"] or not stock["observed_at"]:
        raise ValueError("canonical_sale_stock_identity_required")
    category = stock["category"]
    subject = _public_stock_subject(category)
    caption = (f"Looking for {subject}? Amadeus Farm is currently taking livestock enquiries. "
        "Message Amadeus Farm with the type of animal, number needed, intended use and your area. "
        "Our livestock team will check current farm records before any offer or commitment.")
    cta = ("Message Amadeus Farm with the animal type, number needed, intended use and your area "
        "so our livestock team can qualify your enquiry.")
    media = _public_awareness_media(media_payload, required_tags={category.casefold()})
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
        "objective": f"Generate qualified messages about current {category}",
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
    packet["packet_id"] = "BEACON-DEMAND-" + _digest({
        "stock": stock, "copy": caption, "cta": cta, "media": media_plan,
        "sam": packet["sam_response_contract"]})[:24].upper()
    return packet


def _public_stock_subject(category):
    """Render canonical scanner categories without inventing product detail."""
    value = str(category or "livestock").strip().replace("_", " ")
    plurals = {"piglet": "piglets", "weaner": "weaners", "grower": "growers",
        "finisher": "finishers", "animal": "livestock", "animals": "livestock"}
    return plurals.get(value.casefold(), value)


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


def build_live_stock_awareness_proposal(opportunities, candidate, media_payload=None, *, language="en"):
    """Normalize the existing awareness builder for the Oom Sakkie owner lane."""
    if not isinstance(opportunities, Mapping) or opportunities.get("success") is not True:
        raise ValueError("canonical_opportunity_evidence_required")
    if not isinstance(candidate, Mapping) or candidate.get("success") is not True:
        raise ValueError("awareness_candidate_required")
    review = candidate.get("owner_review_packet") or {}
    policy = review.get("public_livestock_policy") or {}
    if not review.get("draft_copy") or policy.get("policy_version") != "beacon_public_livestock_awareness_only_v1":
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
    if not assess_public_livestock_content(caption, objective="farm_awareness",
            campaign_lane="live_stock_awareness")["allowed"]:
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
    if packet.get("packet_type") == "sale_ready_demand_proposal":
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
            lines.extend(("", "<b>EXACT PROTECTED FACEBOOK CAMPAIGN</b>",
                f"<b>Post:</b> {html.escape(str(campaign.get('exact_post_copy') or ''))}",
                f"<b>Media:</b> {html.escape(str(selected.get('asset_id') or selected.get('mode') or 'none'))}",
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
            lines.extend(("", "<b>EXACT PROTECTED FACEBOOK CAMPAIGN</b>",
                f"<b>Post:</b> {html.escape(str(campaign.get('exact_post_copy') or ''))}",
                f"<b>Media:</b> {html.escape(str(selected.get('asset_id') or selected.get('mode') or 'none'))}",
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
