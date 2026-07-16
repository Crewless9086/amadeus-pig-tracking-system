from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from services.database_service import DATABASE_URL_ENV
from modules.sales.sam_meat_control_mode import controlled_mode_denial


BEACON_CAMPAIGN_MODE = "beacon_meat_launch_campaign_draft_only"
BEACON_LIVE_STOCK_AWARENESS_MODE = "beacon_live_stock_awareness_campaign_draft_only"
CAMPAIGN_LANES = {"meat_launch", "live_stock_awareness", "live_stock_sales"}
LIVE_STOCK_DIRECT_SALES_TERMS = (
    "buy",
    "sale",
    "available",
    "stock",
    "order",
    "reserve",
    "price",
    "cost",
    "book",
    "special",
    "discount",
    "limited stock",
    "dm to buy",
    "message to buy",
    "for sale",
)

AUTHORITY_FLAGS = {
    "draft_only": True,
    "customer_public_output_enabled": False,
    "sends_customer_message": False,
    "posts_publicly": False,
    "calls_chatwoot": False,
    "calls_meta": False,
    "calls_n8n": False,
    "creates_quote": False,
    "creates_invoice": False,
    "creates_order": False,
    "changes_stock": False,
    "reserves_carcass": False,
    "books_slaughter": False,
    "books_butcher": False,
    "confirms_payment": False,
    "writes_farm_data": False,
}

MANUAL_POST_AUTHORITY_FLAGS = {
    **AUTHORITY_FLAGS,
    "records_evidence": True,
    "boosts_post": False,
    "spends_money": False,
    "reserves_stock": False,
    "dispatch_enabled": False,
    "changes_runtime_now": False,
    "changes_prompt_now": False,
    "physical_controls_enabled": False,
}

PERFORMANCE_AUTHORITY_FLAGS = {
    **MANUAL_POST_AUTHORITY_FLAGS,
    "recommends_boost": False,
    "boost_requires_owner_approval": True,
}

BOOST_RECOMMENDATION_SPEND_CAP = 500
FACEBOOK_POSTING_ENABLED_ENV = "BEACON_FACEBOOK_POSTING_ENABLED"
FACEBOOK_PAGE_ID_ENV = "BEACON_FACEBOOK_PAGE_ID"
FACEBOOK_PAGE_ACCESS_TOKEN_ENV = "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN"
FACEBOOK_GRAPH_VERSION_ENV = "BEACON_FACEBOOK_GRAPH_VERSION"
FACEBOOK_POST_CONFIRMATION_PHRASE = "POST EXACT BEACON PACKET"
MEAT_PUBLIC_OFFER_ENABLED_ENV = "SAM_MEAT_PUBLIC_OFFER_ENABLED"
SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_ROLE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"

FORBIDDEN_ACTIONS = [
    "no_public_post",
    "no_customer_dm",
    "no_chatwoot_send",
    "no_whatsapp_template",
    "no_meta_api_call",
    "no_order_create",
    "no_quote_invoice_create",
    "no_stock_reservation",
    "no_price_promise",
    "no_timing_promise",
    "no_slaughter_booking",
    "no_butcher_booking",
    "no_bank_confirmation",
]

OWNER_REVIEW_CHECKLIST = [
    "Choose which channel goes first: WhatsApp status, WhatsApp channel, Facebook, Instagram, or direct known buyers.",
    "Confirm whether public copy may mention Riversdale delivery routes or should keep the area broad.",
    "Confirm whether public copy may mention a price/kg or should keep price on request until the pilot is proven.",
    "Choose the approved farm photo or video set before any public post is prepared.",
    "Confirm the first pilot target: how many halves/full carcasses should Sam try to fill before pausing demand.",
    "Confirm who handles delivery-day customer updates for the first pilot run.",
]

LIVE_STOCK_OWNER_REVIEW_CHECKLIST = [
    "Confirm the chosen media is farm-life/live-stock awareness, not meat product sales.",
    "Confirm whether the post may mention animal categories such as piglets, weaners, growers, or sows.",
    "Confirm there is no price, reserve, order, delivery, or direct sales wording.",
    "Confirm this is an awareness/story post only before any public channel action.",
]


def normalize_campaign_lane(value):
    lane = _clean_text(value).lower().replace("-", "_").replace(" ", "_")
    if lane in {"meat", "meat_sales", "pork", "pork_launch"}:
        return "meat_launch"
    if lane in {"live", "livestock", "live_stock", "live_pig", "live_pigs", "piglets", "farm_life"}:
        return "live_stock_awareness"
    if lane in {"live_sales", "livestock_sales", "live_pig_sales"}:
        return "live_stock_sales"
    return lane


def invalid_campaign_lane_response(lane):
    return {
        "success": False,
        "status": "campaign_lane_required" if not lane else "invalid_campaign_lane",
        "campaign_lane": lane,
        "allowed_campaign_lanes": sorted(CAMPAIGN_LANES),
        "message": "Choose meat_launch, live_stock_awareness, or live_stock_sales before Beacon builds a draft or publish packet.",
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }


def build_beacon_campaign_selection(payload=None, approved_assets=None):
    payload = payload if isinstance(payload, dict) else {}
    lane = normalize_campaign_lane(payload.get("campaign_lane"))
    if lane == "meat_launch":
        return build_meat_launch_campaign_selection(payload, approved_assets=approved_assets)
    if lane == "live_stock_awareness":
        return build_live_stock_awareness_campaign_selection(payload, approved_assets=approved_assets)
    if lane == "live_stock_sales":
        return build_live_stock_sales_campaign_selection(payload, approved_assets=approved_assets)
    return invalid_campaign_lane_response(lane)


def build_beacon_campaign_publish_packet(payload=None, approved_assets=None):
    payload = payload if isinstance(payload, dict) else {}
    lane = normalize_campaign_lane(payload.get("campaign_lane"))
    if lane == "meat_launch":
        return build_meat_launch_campaign_publish_packet(payload, approved_assets=approved_assets)
    if lane == "live_stock_awareness":
        return build_live_stock_awareness_campaign_publish_packet(payload, approved_assets=approved_assets)
    if lane == "live_stock_sales":
        return build_live_stock_sales_campaign_publish_packet(payload, approved_assets=approved_assets)
    return invalid_campaign_lane_response(lane)


def build_meat_launch_campaign_selection(payload=None, approved_assets=None):
    """Return campaign draft/media pairing recommendations without doing any external action."""
    packet = build_meat_launch_campaign_packet(payload)
    approved_assets = approved_assets if isinstance(approved_assets, list) else []
    ranked_assets = _rank_approved_assets(approved_assets)
    channel_pairings = _channel_asset_pairings(packet.get("channel_drafts", []), ranked_assets)
    story_pairings = _channel_asset_pairings(packet.get("story_updates", []), ranked_assets, fallback_channel="story")
    readiness = meat_launch_readiness(payload)
    return {
        "success": True,
        "mode": "beacon_meat_launch_campaign_media_selection_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign_lane": "meat_launch",
        "campaign": packet.get("campaign", {}),
        "meat_launch_readiness": readiness,
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "approved_media_count": len(ranked_assets),
        "ranked_media_assets": ranked_assets,
        "channel_draft_pairings": channel_pairings,
        "story_update_pairings": story_pairings,
        "owner_review_checklist": [
            "Choose the exact media asset for each draft before any public post is prepared.",
            "Confirm the chosen channel and campaign cap before posting.",
            "Confirm no private customer, address, invoice, or sensitive farm detail is visible in the selected media.",
            "Public posting still happens only through a later owner-approved posting gate.",
        ],
        "next_gate": "owner_selects_media_and_campaign_draft_before_any_public_post",
    }


def build_meat_launch_campaign_publish_packet(payload=None, approved_assets=None):
    """Build the exact owner-review publish packet without posting, scheduling, or persisting approval."""
    payload = payload if isinstance(payload, dict) else {}
    campaign_packet = build_meat_launch_campaign_packet(payload)
    approved_assets = approved_assets if isinstance(approved_assets, list) else []
    ranked_assets = _rank_approved_assets(approved_assets)
    draft_id = _clean_text(payload.get("draft_id"))
    selected_asset_id = _clean_text(payload.get("asset_id"))
    selected_channel = _clean_text(payload.get("channel"))
    pilot_cap = _clean_text(payload.get("pilot_cap"))
    owner_notes = _clean_text(payload.get("owner_notes"))
    draft = _find_draft(campaign_packet, draft_id)
    asset = _find_asset(ranked_assets, selected_asset_id)
    readiness = meat_launch_readiness(payload)
    errors = list(readiness["errors"])
    if not draft:
        errors.append("selected_draft_not_found")
    if selected_asset_id and not asset:
        errors.append("selected_asset_not_approved_or_not_found")
    if not selected_asset_id:
        errors.append("selected_image_asset_required")
    channel = selected_channel or (draft.get("channel") if draft else "")
    exact_text = draft.get("text", "") if draft else ""
    packet_id = _meat_launch_publish_packet_id(
        draft_id, selected_asset_id, channel, pilot_cap, exact_text, readiness["owner_offer_enabled"]
    )
    return {
        "success": not errors,
        "mode": "beacon_campaign_publish_packet_owner_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign_lane": "meat_launch",
        "publish_packet_id": packet_id,
        "campaign": campaign_packet.get("campaign", {}),
        "selected_draft": {
            "draft_id": draft.get("id", "") if draft else draft_id,
            "label": draft.get("label", "") if draft else "",
            "channel": channel,
            "intent": draft.get("intent", "") if draft else "",
            "exact_text": exact_text,
        },
        "selected_asset": asset,
        "pilot_cap": pilot_cap,
        "meat_launch_readiness": readiness,
        "owner_notes": owner_notes,
        "approval_status": "owner_review_required",
        "approval_records_publish": False,
        "approval_sends_or_posts": False,
        "requires_owner_exact_text_confirmation": True,
        "requires_owner_exact_media_confirmation": bool(asset),
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "safety_checks": {
            "draft_is_limited_preorder": _has_preorder_signal(exact_text.lower()) and "limited" in exact_text.lower(),
            "draft_has_no_forbidden_promise": not _has_forbidden_promise(exact_text.lower()),
            "asset_is_owner_approved": bool(
                asset.get("effective_public_use_approved") or asset.get("public_use_approved")
            ) if asset else False,
            "no_public_send_or_post": True,
            "no_meta_call": True,
            "no_signed_url_created": True,
        },
        "errors": errors,
        "owner_review_checklist": [
            "Read the exact text as the customer/public will see it.",
            "Confirm the selected media is approved and safe for public use.",
            "Confirm the pilot cap before posting anywhere.",
            "Confirm the chosen channel before any later public-post action.",
            "Use this packet as review evidence only; no post is sent from this step.",
        ],
        "next_gate": "owner_approves_exact_publish_packet_before_manual_or_gated_public_post",
    }


def build_live_stock_awareness_campaign_selection(payload=None, approved_assets=None):
    """Return live-stock awareness draft/media recommendations without sales authority."""
    packet = build_live_stock_awareness_campaign_packet(payload)
    approved_assets = approved_assets if isinstance(approved_assets, list) else []
    ranked_assets = _rank_approved_assets(approved_assets, campaign_lane="live_stock_awareness")
    channel_pairings = _channel_asset_pairings(packet.get("channel_drafts", []), ranked_assets)
    story_pairings = _channel_asset_pairings(packet.get("story_updates", []), ranked_assets, fallback_channel="story")
    return {
        "success": True,
        "mode": "beacon_live_stock_awareness_campaign_media_selection_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign_lane": "live_stock_awareness",
        "campaign": packet.get("campaign", {}),
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "approved_media_count": len(ranked_assets),
        "ranked_media_assets": ranked_assets,
        "channel_draft_pairings": channel_pairings,
        "story_update_pairings": story_pairings,
        "owner_review_checklist": [
            "Choose the exact awareness media before any public post is prepared.",
            "Confirm this is farm-life/live-stock awareness and not a sales post.",
            "Confirm no price, order, reserve, available-now, or DM-to-buy wording appears.",
            "Public posting still happens only through a later owner-approved posting gate.",
        ],
        "next_gate": "owner_selects_live_stock_awareness_media_and_draft_before_any_public_post",
    }


def build_live_stock_awareness_campaign_publish_packet(payload=None, approved_assets=None):
    """Build owner-review live-stock awareness packet without posting or sales authority."""
    payload = payload if isinstance(payload, dict) else {}
    campaign_packet = build_live_stock_awareness_campaign_packet(payload)
    approved_assets = approved_assets if isinstance(approved_assets, list) else []
    ranked_assets = _rank_approved_assets(approved_assets, campaign_lane="live_stock_awareness")
    draft_id = _clean_text(payload.get("draft_id"))
    selected_asset_ids = _selected_asset_ids(payload)
    selected_channel = _clean_text(payload.get("channel"))
    owner_notes = _clean_text(payload.get("owner_notes"))
    draft = _find_draft(campaign_packet, draft_id)
    assets = [_find_asset(ranked_assets, asset_id) for asset_id in selected_asset_ids]
    missing_asset_ids = [asset_id for asset_id, asset in zip(selected_asset_ids, assets) if not asset]
    assets = [asset for asset in assets if asset]
    asset = assets[0] if assets else None
    errors = []
    if not draft:
        errors.append("selected_draft_not_found")
    if missing_asset_ids:
        errors.append("selected_asset_not_approved_or_not_found")
    exact_text = _clean_caption_text(payload.get("owner_exact_text")) or (draft.get("text", "") if draft else "")
    if _has_live_stock_direct_sales_wording(exact_text):
        errors.append("live_stock_awareness_direct_sales_wording_blocked")
    channel = selected_channel or (draft.get("channel") if draft else "")
    packet_id = _publish_packet_id(draft_id, "|".join(selected_asset_ids), channel, "live_stock_awareness", exact_text)
    return {
        "success": not errors,
        "mode": "beacon_live_stock_awareness_publish_packet_owner_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign_lane": "live_stock_awareness",
        "publish_packet_id": packet_id,
        "campaign": campaign_packet.get("campaign", {}),
        "selected_draft": {
            "draft_id": draft.get("id", "") if draft else draft_id,
            "label": draft.get("label", "") if draft else "",
            "channel": channel,
            "intent": draft.get("intent", "") if draft else "",
            "exact_text": exact_text,
        },
        "selected_asset": asset,
        "selected_assets": assets,
        "asset_ids": selected_asset_ids,
        "owner_notes": owner_notes,
        "approval_status": "owner_review_required",
        "approval_records_publish": False,
        "approval_sends_or_posts": False,
        "requires_owner_exact_text_confirmation": True,
        "requires_owner_exact_media_confirmation": bool(assets),
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "safety_checks": {
            "draft_is_awareness_only": not _has_live_stock_direct_sales_wording(exact_text),
            "draft_has_no_direct_sales_wording": not _has_live_stock_direct_sales_wording(exact_text),
            "assets_are_owner_approved": len(assets) == len(selected_asset_ids) and all(
                item.get("effective_public_use_approved") or item.get("public_use_approved") for item in assets
            ),
            "no_public_send_or_post": True,
            "no_meta_call": True,
            "no_signed_url_created": True,
        },
        "errors": errors,
        "owner_review_checklist": list(LIVE_STOCK_OWNER_REVIEW_CHECKLIST),
        "next_gate": "owner_approves_exact_live_stock_awareness_packet_before_manual_or_gated_public_post",
    }


def meat_launch_readiness(payload=None, environ=None):
    """Return fail-closed, server-owned readiness for the bounded meat Facebook pilot."""
    payload = payload if isinstance(payload, dict) else {}
    source = environ if environ is not None else os.environ
    owner_offer_enabled = _truthy(source.get(MEAT_PUBLIC_OFFER_ENABLED_ENV))
    pilot_cap = _clean_text(payload.get("pilot_cap"))
    pilot_cap_valid = pilot_cap.isdigit() and int(pilot_cap) > 0
    errors = []
    if not owner_offer_enabled:
        errors.append("meat_public_offer_not_owner_enabled")
    if not pilot_cap_valid:
        errors.append("meat_pilot_cap_positive_whole_number_required")
    return {
        "schema_version": "beacon_meat_launch_readiness_v1",
        "owner_offer_enabled": owner_offer_enabled,
        "owner_offer_source": MEAT_PUBLIC_OFFER_ENABLED_ENV,
        "pilot_cap": pilot_cap,
        "pilot_cap_valid": pilot_cap_valid,
        "sam_mode": "interest_capture_only",
        "ready": not errors,
        "errors": errors,
    }


def build_live_stock_sales_campaign_selection(payload=None, approved_assets=None):
    payload = payload if isinstance(payload, dict) else {}
    truth, errors = _live_stock_sales_truth(payload)
    ranked = [asset for asset in _rank_approved_assets(approved_assets or [], campaign_lane="live_stock_sales")
              if asset.get("public_use_approved") and asset.get("content_sha256")]
    drafts = _live_stock_sales_drafts(truth) if not errors else []
    return {
        "success": not errors,
        "mode": "beacon_live_stock_sales_campaign_review_only",
        "campaign_lane": "live_stock_sales",
        "campaign": {"name": "Live-Stock Sales", "status": "owner_review_required", "product_focus": truth.get("product_focus", "")},
        "source_truth": truth,
        "channel_drafts": drafts,
        "channel_draft_pairings": _channel_asset_pairings(drafts, ranked),
        "ranked_media_assets": ranked,
        "approved_media_count": len(ranked),
        "errors": errors,
        "handoff_to_sam": {"sales_lane": "live_stock_sales", "campaign_attribution_id": truth.get("campaign_attribution_id", ""), "negotiates": False, "reserves": False, "creates_order": False},
        "whatsapp_suggestion_only": True,
        "next_gate": "owner_selects_exact_facebook_copy_and_approved_image" if not errors else "restore_current_supabase_and_sheet_lineaged_sales_evidence",
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
    }


def build_live_stock_sales_campaign_publish_packet(payload=None, approved_assets=None):
    payload = payload if isinstance(payload, dict) else {}
    selection = build_live_stock_sales_campaign_selection(payload, approved_assets=approved_assets)
    truth = selection.get("source_truth", {})
    drafts = selection.get("channel_drafts", [])
    draft_id = _clean_text(payload.get("draft_id"))
    asset_id = _clean_text(payload.get("asset_id"))
    draft = next((item for item in drafts if item.get("id") == draft_id), None)
    asset = _find_asset(selection.get("ranked_media_assets", []), asset_id)
    errors = list(selection.get("errors", []))
    if not draft or draft.get("channel") != "Facebook":
        errors.append("facebook_sales_draft_required")
    if not asset_id or not asset:
        errors.append("owner_approved_sales_image_required")
    exact_text = draft.get("text", "") if draft else ""
    binding = {
        "campaign_lane": "live_stock_sales", "channel": "Facebook", "exact_text": exact_text,
        "asset_id": asset.get("asset_id", "") if asset else asset_id,
        "asset_hash": asset.get("content_sha256", "") if asset else "",
        "opportunity_fingerprint": truth.get("opportunity_fingerprint", ""),
        "fulfilment_cap": truth.get("fulfilment_cap", 0), "pricing_id": truth.get("pricing_id", ""),
        "unit_price": truth.get("unit_price"), "price_effective_from": truth.get("price_effective_from", ""),
        "campaign_attribution_id": truth.get("campaign_attribution_id", ""),
    }
    packet_id = "BEACON-LIVE-SALES-" + hashlib.sha256(json.dumps(binding, sort_keys=True, default=str).encode()).hexdigest()[:24].upper()
    return {
        "success": not errors, "mode": "beacon_live_stock_sales_exact_publish_packet_owner_review_only",
        "campaign_lane": "live_stock_sales", "publish_packet_id": packet_id, "packet_binding": binding,
        "selected_draft": {"draft_id": draft_id, "channel": "Facebook", "exact_text": exact_text},
        "selected_asset": asset, "source_truth": truth, "errors": sorted(set(errors)),
        "whatsapp_suggestion": next((item for item in drafts if item.get("channel") == "WhatsApp"), {}),
        "whatsapp_suggestion_only": True, "requires_owner_confirmation": FACEBOOK_POST_CONFIRMATION_PHRASE,
        "approval_status": "owner_review_required", "posts_publicly_now": False,
        "authority": deepcopy(AUTHORITY_FLAGS), "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "next_gate": "owner_confirms_exact_server_revalidated_packet" if not errors else "repair_packet_evidence",
    }


def _live_stock_sales_truth(payload):
    card = payload.get("opportunity_card") if isinstance(payload.get("opportunity_card"), dict) else {}
    pricing = payload.get("pricing") if isinstance(payload.get("pricing"), dict) else {}
    errors = []
    if card.get("lane") != "live_stock" or card.get("status") != "ready_for_owner_review": errors.append("current_sale_eligibility_required")
    if card.get("blockers"): errors.append("sale_eligibility_blocked")
    if not (card.get("freshness") or {}).get("fresh"): errors.append("sale_eligibility_stale")
    cap = card.get("demand_cap")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap <= 0: errors.append("positive_fulfilment_cap_required")
    if pricing.get("source") != "supabase" or not pricing.get("pricing_id"): errors.append("sheet_lineaged_supabase_price_required")
    if pricing.get("unit_price") in (None, ""): errors.append("effective_price_required")
    fingerprint = _clean_text(card.get("fingerprint"))
    if not fingerprint: errors.append("opportunity_revision_required")
    attribution = "BEACON-SAM-LIVE-" + hashlib.sha256(f"{fingerprint}|{pricing.get('pricing_id','')}".encode()).hexdigest()[:16].upper() if fingerprint else ""
    truth = {"product_focus": _clean_text(payload.get("product_focus")) or "live pigs", "fulfilment_cap": cap or 0,
             "fulfilment_unit": "animals", "sale_eligible": not any(e in errors for e in ("current_sale_eligibility_required", "sale_eligibility_blocked", "sale_eligibility_stale")),
             "opportunity_fingerprint": fingerprint, "opportunity_expires_at": (card.get("timing") or {}).get("expires_at", ""),
             "stock_source": "Supabase canonical allocation derived from sheet-backed herd facts", "stock_source_ids": (card.get("provenance") or {}).get("source_ids", []),
             "stock_lineage_approved": card.get("lane") == "live_stock" and bool(fingerprint),
             "pricing_id": pricing.get("pricing_id", ""), "unit_price": pricing.get("unit_price"), "currency": pricing.get("currency", "ZAR"),
             "price_effective_from": pricing.get("effective_from", ""), "price_source": pricing.get("source", ""),
             "price_display": f"{pricing.get('currency', 'ZAR')} {pricing.get('unit_price', '')}", "price_lineage_approved": pricing.get("source") == "supabase" and bool(pricing.get("pricing_id")),
             "blocker": ", ".join(sorted(set(errors))),
             "campaign_attribution_id": attribution}
    return truth, sorted(set(errors))


def _live_stock_sales_drafts(truth):
    product = truth["product_focus"]; cap = truth["fulfilment_cap"]; price = truth["unit_price"]; currency = truth["currency"]
    attribution = truth["campaign_attribution_id"]
    return [
        {"id": "facebook_live_stock_sales", "label": "Facebook sales post", "channel": "Facebook", "intent": "owner-gated live-stock sale",
         "text": f"Amadeus Farm has {product} available near Riversdale. We can safely take enquiries for up to {cap} animals at {currency} {price} each. Message us with the quantity and type you need. Reference: {attribution}."},
        {"id": "whatsapp_live_stock_sales", "label": "WhatsApp suggestion", "channel": "WhatsApp", "intent": "copy suggestion only",
         "text": f"Live-stock update from Amadeus Farm: enquiries are open for up to {cap} {product} at {currency} {price} each. Reply with the quantity and type you need and SAM will help. Reference: {attribution}."},
    ]


def build_beacon_facebook_image_launch_packet(payload=None, approved_assets=None):
    payload = payload if isinstance(payload, dict) else {}
    selection = build_meat_launch_campaign_selection(payload, approved_assets=approved_assets)
    facebook_pairing = next(
        (
            item for item in selection.get("channel_draft_pairings", [])
            if item.get("draft_id") == "facebook_post"
        ),
        {},
    )
    asset_id = _clean_text(payload.get("asset_id") or facebook_pairing.get("recommended_asset_id"))
    publish_packet = build_meat_launch_campaign_publish_packet(
        {
            **payload,
            "draft_id": "facebook_post",
            "channel": "Facebook",
            "asset_id": asset_id,
            "pilot_cap": payload.get("pilot_cap"),
        },
        approved_assets=approved_assets,
    )
    execution_payload = {
        "publish_packet_id": publish_packet.get("publish_packet_id", ""),
        "channel": "Facebook",
        "exact_text": (publish_packet.get("selected_draft") or {}).get("exact_text", ""),
        "asset_id": ((publish_packet.get("selected_asset") or {}).get("asset_id") or ""),
        "owner_confirmation": FACEBOOK_POST_CONFIRMATION_PHRASE,
        "pilot_cap": publish_packet.get("pilot_cap", ""),
    }
    return {
        "success": bool(publish_packet.get("success")) and bool((publish_packet.get("selected_asset") or {}).get("asset_id")),
        "mode": "beacon_facebook_image_launch_packet_owner_review",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "publish_packet": publish_packet,
        "recommended_pairing": facebook_pairing,
        "execution_payload": execution_payload,
        "owner_confirmation_required": FACEBOOK_POST_CONFIRMATION_PHRASE,
        "ready_for_owner_post_approval": bool(publish_packet.get("success")) and bool(execution_payload["asset_id"]),
        "posts_publicly_now": False,
        "calls_meta_now": False,
        "next_gate": "owner_posts_exact_execution_payload_through_facebook_post_executions",
        **AUTHORITY_FLAGS,
    }


def manual_post_evidence_policy():
    return {
        "success": True,
        "mode": "beacon_manual_public_post_evidence_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "purpose": "Record owner-posted campaign evidence after a manual public post.",
        "allowed_inputs": [
            "publish_packet_id",
            "channel",
            "post_url",
            "posted_at",
            "posted_by",
            "campaign_label",
            "evidence_notes",
            "initial manual metrics",
        ],
        "owner_checklist": [
            "Prepare a publish packet and review exact text/media.",
            "Post manually in the chosen public channel.",
            "Paste the post URL or channel evidence back into Beacon.",
            "Record early metrics so Beacon can learn what worked.",
            "Do not boost or spend from this step.",
        ],
        "next_gate": "beacon_performance_tracking_before_boost_recommendation_or_meta_ads_access",
        **MANUAL_POST_AUTHORITY_FLAGS,
    }


def record_beacon_manual_post_evidence(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _manual_post_params(payload)
    if not params["publish_packet_id"]:
        return {
            "success": False,
            "status": "publish_packet_id_required",
            "manual_post_event": _public_manual_post_event(params),
            **MANUAL_POST_AUTHORITY_FLAGS,
        }, 400
    if not params["channel"]:
        return {
            "success": False,
            "status": "channel_required",
            "manual_post_event": _public_manual_post_event(params),
            **MANUAL_POST_AUTHORITY_FLAGS,
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _manual_post_unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _manual_post_unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.beacon_manual_post_events (
                        manual_post_event_id, mode, publish_packet_id, channel, post_url,
                        posted_at, posted_by, campaign_label, evidence_notes,
                        initial_metrics_json, records_evidence, sends_customer_message,
                        posts_publicly, calls_chatwoot, calls_meta, calls_n8n,
                        boosts_post, spends_money, creates_quote, creates_invoice,
                        creates_order, changes_stock, reserves_stock, dispatch_enabled,
                        changes_runtime_now, changes_prompt_now, physical_controls_enabled,
                        customer_public_output_enabled, writes_farm_data
                    )
                    values (
                        %(manual_post_event_id)s, %(mode)s, %(publish_packet_id)s,
                        %(channel)s, %(post_url)s, %(posted_at)s, %(posted_by)s,
                        %(campaign_label)s, %(evidence_notes)s,
                        %(initial_metrics_json)s::jsonb, %(records_evidence)s,
                        %(sends_customer_message)s, %(posts_publicly)s,
                        %(calls_chatwoot)s, %(calls_meta)s, %(calls_n8n)s,
                        %(boosts_post)s, %(spends_money)s, %(creates_quote)s,
                        %(creates_invoice)s, %(creates_order)s, %(changes_stock)s,
                        %(reserves_stock)s, %(dispatch_enabled)s,
                        %(changes_runtime_now)s, %(changes_prompt_now)s,
                        %(physical_controls_enabled)s, %(customer_public_output_enabled)s,
                        %(writes_farm_data)s
                    )
                    on conflict (manual_post_event_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_manual_post_evidence_write_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "manual_post_event": _public_manual_post_event(params),
            **MANUAL_POST_AUTHORITY_FLAGS,
        }, 500

    return {
        "success": True,
        "configured": True,
        "status": "beacon_manual_post_evidence_recorded" if created_count else "beacon_manual_post_evidence_already_recorded",
        "created_count": created_count,
        "manual_post_event_id": params["manual_post_event_id"],
        "manual_post_event": _public_manual_post_event(params),
        "next_gate": "beacon_performance_tracking_before_boost_recommendation_or_meta_ads_access",
        **MANUAL_POST_AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def list_beacon_manual_post_evidence(limit=25, publish_packet_id="", database_url=None):
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 25
    publish_packet_id = _clean_text(publish_packet_id)[:120]
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _manual_post_unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _manual_post_unavailable("dependency_missing", configured=True), 500

    where = "where publish_packet_id = %(publish_packet_id)s" if publish_packet_id else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select manual_post_event_id, publish_packet_id, channel, post_url,
                           posted_at, posted_by, campaign_label, evidence_notes,
                           initial_metrics_json, created_at
                    from public.beacon_manual_post_events
                    {where}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {"limit": limit, "publish_packet_id": publish_packet_id},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_manual_post_evidence_read_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "manual_post_events": [],
            **MANUAL_POST_AUTHORITY_FLAGS,
        }, 500

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "beacon_manual_public_post_evidence_only",
        "manual_post_events": [_manual_post_row_to_event(row) for row in rows],
        "policy": manual_post_evidence_policy(),
        "next_gate": "beacon_performance_tracking_before_boost_recommendation_or_meta_ads_access",
        **MANUAL_POST_AUTHORITY_FLAGS,
    }, 200


def record_beacon_campaign_performance_event(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _performance_params(payload)
    if not params["manual_post_event_id"] and not params["publish_packet_id"]:
        return {
            "success": False,
            "status": "manual_post_event_id_or_publish_packet_id_required",
            "performance_event": _public_performance_event(params),
            **PERFORMANCE_AUTHORITY_FLAGS,
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _performance_unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _performance_unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.beacon_campaign_performance_events (
                        performance_event_id, mode, manual_post_event_id, publish_packet_id,
                        channel, measurement_window, spend_amount, spend_currency,
                        reach, impressions, reactions, comments, shares, messages_to_sam,
                        qualified_buyer_leads, booking_review_requests, notes,
                        recommended_action, recommendation_reason, recommended_spend_amount,
                        recommended_duration_days, max_spend_cap_amount, cost_per_message,
                        cost_per_qualified_lead, records_evidence, recommends_boost,
                        boost_requires_owner_approval, sends_customer_message, posts_publicly,
                        calls_chatwoot, calls_meta, calls_n8n, boosts_post, spends_money,
                        creates_quote, creates_invoice, creates_order, changes_stock,
                        reserves_stock, dispatch_enabled, changes_runtime_now,
                        changes_prompt_now, physical_controls_enabled,
                        customer_public_output_enabled, writes_farm_data, recorded_by
                        , metric_evidence, evidence_source, source_reference, retrieved_at,
                        source_snapshot_key, supersedes_event_id
                    )
                    values (
                        %(performance_event_id)s, %(mode)s, %(manual_post_event_id)s,
                        %(publish_packet_id)s, %(channel)s, %(measurement_window)s,
                        %(spend_amount)s, %(spend_currency)s, %(reach)s, %(impressions)s,
                        %(reactions)s, %(comments)s, %(shares)s, %(messages_to_sam)s,
                        %(qualified_buyer_leads)s, %(booking_review_requests)s, %(notes)s,
                        %(recommended_action)s, %(recommendation_reason)s,
                        %(recommended_spend_amount)s, %(recommended_duration_days)s,
                        %(max_spend_cap_amount)s, %(cost_per_message)s,
                        %(cost_per_qualified_lead)s, %(records_evidence)s,
                        %(recommends_boost)s, %(boost_requires_owner_approval)s,
                        %(sends_customer_message)s, %(posts_publicly)s,
                        %(calls_chatwoot)s, %(calls_meta)s, %(calls_n8n)s,
                        %(boosts_post)s, %(spends_money)s, %(creates_quote)s,
                        %(creates_invoice)s, %(creates_order)s, %(changes_stock)s,
                        %(reserves_stock)s, %(dispatch_enabled)s,
                        %(changes_runtime_now)s, %(changes_prompt_now)s,
                        %(physical_controls_enabled)s, %(customer_public_output_enabled)s,
                        %(writes_farm_data)s, %(recorded_by)s
                        , %(metric_evidence_json)s::jsonb, %(evidence_source)s, %(source_reference)s,
                        %(retrieved_at)s::timestamptz, %(performance_event_id)s, nullif(%(supersedes_event_id)s, '')
                    )
                    on conflict (performance_event_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_campaign_performance_write_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "performance_event": _public_performance_event(params),
            **PERFORMANCE_AUTHORITY_FLAGS,
        }, 500

    return {
        "success": True,
        "configured": True,
        "status": "beacon_campaign_performance_event_recorded" if created_count else "beacon_campaign_performance_event_already_recorded",
        "created_count": created_count,
        "performance_event_id": params["performance_event_id"],
        "performance_event": _public_performance_event(params),
        "boost_packet": _boost_packet(params),
        "next_gate": "owner_reviews_boost_recommendation_before_any_meta_or_paid_spend_authority",
        **PERFORMANCE_AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def build_beacon_boost_recommendation_packet(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _performance_params(payload)
    return _boost_packet(params)


def list_beacon_campaign_performance_events(limit=25, publish_packet_id="", manual_post_event_id="", database_url=None):
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 25
    publish_packet_id = _clean_text(publish_packet_id)[:120]
    manual_post_event_id = _clean_text(manual_post_event_id)[:120]
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _performance_unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _performance_unavailable("dependency_missing", configured=True), 500

    where = ""
    if manual_post_event_id:
        where = "where manual_post_event_id = %(manual_post_event_id)s"
    elif publish_packet_id:
        where = "where publish_packet_id = %(publish_packet_id)s"

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select performance_event_id, manual_post_event_id, publish_packet_id,
                           channel, measurement_window, spend_amount, spend_currency,
                           reach, impressions, reactions, comments, shares,
                           messages_to_sam, qualified_buyer_leads,
                           booking_review_requests, notes, recommended_action,
                           recommendation_reason, recommended_spend_amount,
                           recommended_duration_days, max_spend_cap_amount,
                           cost_per_message, cost_per_qualified_lead,
                           recommends_boost, recorded_by, created_at,
                           metric_evidence, evidence_source, source_reference, retrieved_at,
                           source_snapshot_key, supersedes_event_id
                    from public.beacon_campaign_performance_events
                    {where}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {
                        "limit": limit,
                        "publish_packet_id": publish_packet_id,
                        "manual_post_event_id": manual_post_event_id,
                    },
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_campaign_performance_read_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "performance_events": [],
            **PERFORMANCE_AUTHORITY_FLAGS,
        }, 500

    events = [_performance_row_to_event(row) for row in rows]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "beacon_campaign_performance_evidence_only",
        "performance_events": events,
        "latest_boost_packet": _boost_packet(_event_to_performance_params(events[0])) if events else {},
        "next_gate": "owner_reviews_boost_recommendation_before_any_meta_or_paid_spend_authority",
        **PERFORMANCE_AUTHORITY_FLAGS,
    }, 200


def build_beacon_weekly_command_brief(events, now=None, stale_after_hours=168, weekly_targets=None):
    """Project append-only performance snapshots into a read-only owner brief."""
    now = now or datetime.now(timezone.utc)
    unique, seen_ids = [], set()
    ordered_events = sorted(events or [], key=lambda item: _event_datetime(item) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    for event in ordered_events:
        event_id = _clean_text(event.get("performance_event_id"))
        if event_id and event_id in seen_ids:
            continue
        if event_id:
            seen_ids.add(event_id)
        unique.append(event)
    authority = {**deepcopy(PERFORMANCE_AUTHORITY_FLAGS), "creates_core_work": False, "approves_campaign": False}
    if not unique:
        unavailable = {"status": "unavailable", "target": None, "actual": None}
        return {"mode": "beacon_weekly_command_brief_read_only", "truth_state": "unavailable",
                "targets": {"spend": {**unavailable, "actual": 0}, "qualified_leads": {**unavailable, "actual": 0},
                            "attributed_revenue": unavailable},
                "comparison": {"status": "insufficient_data", "measurement_window": "", "campaigns": []},
                "recommendations": [], "alerts": [{"code": "missing_evidence", "severity": "blocked"}], "authority": authority}

    latest = unique[0]
    latest_datetime = _event_datetime(latest)
    if latest_datetime:
        latest_week = latest_datetime.isocalendar()[:2]
        unique = [event for event in unique if (_event_datetime(event) or latest_datetime).isocalendar()[:2] == latest_week]
    window = " ".join(_clean_text(latest.get("measurement_window")).lower().split())
    currency = (_clean_text(latest.get("spend_currency")) or "ZAR").upper()
    compatible, seen_campaigns = [], set()
    for event in unique:
        event_window = " ".join(_clean_text(event.get("measurement_window")).lower().split())
        event_currency = (_clean_text(event.get("spend_currency")) or "ZAR").upper()
        campaign_id = _clean_text(event.get("publish_packet_id") or event.get("manual_post_event_id") or event.get("channel"))
        key = (campaign_id, event_window, event_currency)
        if event_window != window or event_currency != currency or key in seen_campaigns:
            continue
        seen_campaigns.add(key)
        compatible.append(event)

    recommendations = [_command_recommendation(event) for event in compatible]
    alerts = []
    latest_at = _event_datetime(latest)
    if not latest_at or (now - latest_at).total_seconds() > stale_after_hours * 3600:
        alerts.append({"code": "stale_evidence", "severity": "warning"})
    alerts.append({"code": "stop_recommendation_waiting" if any(r["classification"] == "STOP" for r in recommendations)
                   else "recommendations_waiting", "severity": "blocked" if any(r["classification"] == "STOP" for r in recommendations) else "review"})
    targets = _weekly_target_contract(weekly_targets, compatible, currency)
    return {"mode": "beacon_weekly_command_brief_read_only", "truth_state": "comparable" if len(compatible) > 1 else "limited",
            "last_updated_at": latest.get("created_at"),
            "targets": targets,
            "comparison": {"status": "compatible" if len(compatible) > 1 else "insufficient_data", "measurement_window": latest.get("measurement_window") or "", "currency": currency, "campaigns": compatible},
            "recommendations": recommendations, "alerts": alerts, "authority": authority}


def prepare_beacon_owner_decision(performance_event, destination):
    """Prepare an owner-review packet without recording or executing the decision."""
    performance_event = performance_event if isinstance(performance_event, dict) else {}
    destination = _clean_text(destination).lower()
    if destination not in {"campaign_decision", "core_work"}:
        return {"success": False, "status": "decision_destination_unavailable", "allowed_destinations": ["campaign_decision", "core_work"], **_decision_authority()}, 400
    source_id = _clean_text(performance_event.get("performance_event_id"))
    if not source_id:
        return {"success": False, "status": "recommendation_source_required", **_decision_authority()}, 400
    recommendation = _command_recommendation(performance_event)
    return {
        "success": True,
        "status": "owner_decision_packet_prepared",
        "mode": "beacon_owner_decision_prepare_only",
        "destination": destination,
        "classification": recommendation["classification"],
        "performance_event_id": source_id,
        "reason": _clean_text(recommendation.get("reason")),
        "supporting_metrics": recommendation.get("supporting_metrics") if isinstance(recommendation.get("supporting_metrics"), dict) else {},
        "owner_gate": "owner_review_required",
        "next_gate": "owner_records_separate_campaign_decision" if destination == "campaign_decision" else "owner_creates_or_approves_separate_core_mission",
        **_decision_authority(),
    }, 200


def _event_datetime(event):
    try:
        value = datetime.fromisoformat(_clean_text(event.get("created_at")).replace("Z", "+00:00"))
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    except (AttributeError, TypeError, ValueError):
        return None


def _weekly_target_contract(weekly_targets, events, currency):
    weekly_targets = weekly_targets if isinstance(weekly_targets, dict) else {}
    actuals = {
        "spend": sum(float(event.get("spend_amount") or 0) for event in events),
        "qualified_leads": sum(int(event.get("qualified_buyer_leads") or 0) for event in events),
    }
    targets = {}
    for key in ("spend", "qualified_leads"):
        source = weekly_targets.get(key) if isinstance(weekly_targets.get(key), dict) else {}
        status = _clean_text(source.get("status")).lower()
        if status not in {"proposed", "owner_approved", "blocked"}:
            status = "unavailable"
        targets[key] = {"status": status, "target": source.get("target") if status != "unavailable" else None, "actual": actuals[key]}
        if key == "spend":
            targets[key]["currency"] = currency
        if status == "blocked":
            targets[key]["blocker"] = _clean_text(source.get("blocker")) or "owner_or_fulfilment_block"
    targets["attributed_revenue"] = {"status": "unavailable", "target": None, "actual": None, "reason": "canonical_paid_completed_sale_join_unproven"}
    return targets


def _decision_authority():
    return {
        "creates_core_work": False, "approves_campaign": False, "posts_publicly": False,
        "sends_customer_message": False, "calls_meta": False, "calls_chatwoot": False,
        "calls_n8n": False, "spends_money": False, "creates_order": False,
        "reserves_stock": False, "changes_stock": False, "writes_farm_data": False,
    }


def _command_recommendation(event):
    spend, leads = float(event.get("spend_amount") or 0), int(event.get("qualified_buyer_leads") or 0)
    cap = float(event.get("max_spend_cap_amount") or BOOST_RECOMMENDATION_SPEND_CAP)
    upstream = _clean_text(event.get("recommended_action")).lower()
    if spend > cap:
        result = ("STOP", "spend_cap_conflict", "blocked")
    elif upstream == "do_not_boost" or (spend > 0 and leads == 0):
        result = ("STOP", "paid_spend_without_qualified_leads", "blocked")
    elif upstream == "light_boost_owner_review" and leads > 0:
        result = ("BOOST", "qualified_leads_support_owner_review", "owner_review_required")
    elif leads > 0 and spend == 0:
        result = ("REUSE", "qualified_leads_without_paid_spend", "owner_review_required")
    else:
        result = ("CHANGE", "insufficient_evidence_or_adjustment_needed", "owner_review_required")
    return {"classification": result[0], "reason": result[1], "truth_state": result[2],
            "performance_event_id": event.get("performance_event_id") or "",
            "supporting_metrics": {"spend_amount": spend, "qualified_buyer_leads": leads, "currency": event.get("spend_currency") or "ZAR"},
            "owner_gate": "prepare_decision_only"}


def facebook_posting_policy(environ=None):
    source = environ if environ is not None else os.environ
    enabled = _truthy(source.get(FACEBOOK_POSTING_ENABLED_ENV))
    page_id = _clean_text(source.get(FACEBOOK_PAGE_ID_ENV))
    token = _clean_text(source.get(FACEBOOK_PAGE_ACCESS_TOKEN_ENV))
    supabase_url = _clean_text(source.get(SUPABASE_URL_ENV))
    supabase_key = _clean_text(source.get(SUPABASE_SERVICE_ROLE_KEY_ENV))
    page_credentials_configured = bool(page_id and token)
    media_storage_configured = bool(supabase_url and supabase_key)
    posting_ready = bool(enabled and page_credentials_configured)
    return {
        "success": True,
        "mode": "beacon_facebook_page_post_execution_gate",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "enabled": enabled,
        "enabled_env": FACEBOOK_POSTING_ENABLED_ENV,
        "page_id_configured": bool(page_id),
        "page_id_env": FACEBOOK_PAGE_ID_ENV,
        "page_access_token_configured": bool(token),
        "page_access_token_env": FACEBOOK_PAGE_ACCESS_TOKEN_ENV,
        "graph_version_env": FACEBOOK_GRAPH_VERSION_ENV,
        "required_owner_confirmation": FACEBOOK_POST_CONFIRMATION_PHRASE,
        "text_posting_configured": page_credentials_configured,
        "media_storage_configured": media_storage_configured,
        "image_posting_configured": bool(page_credentials_configured and media_storage_configured),
        "posts_text_only_now": posting_ready,
        "posts_media_now": bool(posting_ready and media_storage_configured),
        "posts_image_now": bool(posting_ready and media_storage_configured),
        "media_source": "approved_beacon_supabase_image_signed_url",
        "boosts_or_spends_now": False,
        "required_envs": [
            FACEBOOK_POSTING_ENABLED_ENV,
            FACEBOOK_PAGE_ID_ENV,
            FACEBOOK_PAGE_ACCESS_TOKEN_ENV,
        ],
        **_facebook_execution_authority(False),
    }


def execute_beacon_facebook_page_post(payload, database_url=None, poster=None, environ=None, execution_recorder=None,
                                      meat_launch_authorized=False):
    payload = payload if isinstance(payload, dict) else {}
    if normalize_campaign_lane(payload.get("campaign_lane")) == "meat_launch" and not meat_launch_authorized:
        return controlled_mode_denial("publish_meat_campaign")
    policy = facebook_posting_policy(environ=environ)
    params = _facebook_post_params(payload, policy)
    validation_error = _facebook_post_validation_error(params, policy)
    if validation_error:
        params["execution_status"] = validation_error
        _record_facebook_post_execution_event(params, database_url=database_url)
        return {
            "success": False,
            "status": validation_error,
            "policy": policy,
            "execution_event": _public_facebook_post_event(params),
            **_facebook_execution_authority(False),
        }, 400 if validation_error not in {"facebook_posting_disabled", "facebook_page_credentials_missing"} else 503

    recorder = execution_recorder or _record_facebook_post_execution_event
    params["execution_status"] = "record_only_before_send"
    claim_result, claim_status = recorder(params, database_url=database_url)
    if claim_status != 201 or not claim_result.get("created_count"):
        return {
            "success": False,
            "status": "facebook_publish_packet_already_claimed" if claim_status < 400 else "facebook_publish_claim_failed",
            "record_status_code": claim_status,
            "record_result": claim_result,
            "execution_event": _public_facebook_post_event(params),
            "policy": policy,
            **_facebook_execution_authority(False),
        }, 409 if claim_status < 400 else 503

    post_fn = poster or _post_to_facebook_page
    post_result, post_status = post_fn(params, policy)
    execution_status = "facebook_page_post_sent" if post_status < 400 and post_result.get("success") else "facebook_page_post_failed"
    params.update({
        "execution_event_id": f'{params["execution_event_id"]}-RESULT',
        "execution_status": execution_status,
        "facebook_post_id": _clean_text(post_result.get("facebook_post_id") or post_result.get("id"))[:160],
        "facebook_response_json": json.dumps(post_result, sort_keys=True, default=str),
    })
    record_result, record_status = recorder(params, database_url=database_url)
    return {
        "success": execution_status == "facebook_page_post_sent",
        "status": execution_status,
        "post_status_code": post_status,
        "facebook_post_id": params["facebook_post_id"],
        "facebook_result": post_result,
        "record_status_code": record_status,
        "record_result": record_result,
        "execution_event": _public_facebook_post_event(params),
        "policy": policy,
        **_facebook_execution_authority(execution_status == "facebook_page_post_sent"),
    }, 200 if execution_status == "facebook_page_post_sent" else 502


def list_beacon_facebook_post_execution_events(limit=25, publish_packet_id="", database_url=None):
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 25
    publish_packet_id = _clean_text(publish_packet_id)[:120]
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _facebook_post_unavailable("not_configured", False), 503
    try:
        import psycopg
    except ImportError:
        return _facebook_post_unavailable("dependency_missing", True), 500
    where = "where publish_packet_id = %(publish_packet_id)s" if publish_packet_id else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select execution_event_id, publish_packet_id, channel, exact_text,
                           owner_confirmation, execution_status, facebook_post_id,
                           facebook_response_json, created_at
                    from public.beacon_facebook_post_execution_events
                    {where}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {"limit": limit, "publish_packet_id": publish_packet_id},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_facebook_post_execution_read_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "execution_events": [],
            **_facebook_execution_authority(False),
        }, 500
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "beacon_facebook_page_post_execution_gate",
        "execution_events": [_facebook_post_row_to_event(row) for row in rows],
        "policy": facebook_posting_policy(),
        **_facebook_execution_authority(False),
    }, 200


def build_meat_launch_campaign_packet(payload=None):
    """Return Beacon's first meat-launch campaign drafts without doing any external action."""
    payload = payload if isinstance(payload, dict) else {}
    pilot_name = _clean_text(payload.get("pilot_name")) or "First pork freezer preorder pilot"
    farm_name = _clean_text(payload.get("farm_name")) or "Amadeus Farm"
    area = _clean_text(payload.get("area")) or "Riversdale and nearby routes"
    product_focus = _clean_text(payload.get("product_focus")) or "half carcass Set A and full carcass pork freezer options"

    packet = {
        "success": True,
        "mode": BEACON_CAMPAIGN_MODE,
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign": {
            "name": pilot_name,
            "status": "draft_only_owner_review_required",
            "farm_name": farm_name,
            "area": area,
            "product_focus": product_focus,
            "primary_goal": "Generate controlled inbound demand for Sam Meat without overpromising stock, price, timing, or delivery.",
        },
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "campaign_angles": _campaign_angles(farm_name, area, product_focus),
        "channel_drafts": _channel_drafts(farm_name, area, product_focus),
        "story_updates": _story_updates(farm_name, area),
        "owner_review_checklist": list(OWNER_REVIEW_CHECKLIST),
        "handoff_to_sam": {
            "inbound_prompt": "When a buyer replies, Sam should collect product, cut set, town, delivery address or farm name, useful driver notes, timing, payment preference, freezer size or target kg where useful, and final booking-review confirmation.",
            "must_not_say": [
                "Your order is confirmed.",
                "Your price is final.",
                "Your deposit is confirmed.",
                "Your carcass is reserved.",
                "Slaughter or butcher booking is confirmed.",
            ],
        },
        "next_gate": "owner_reviews_campaign_before_any_public_or_customer_send",
    }
    validation = validate_meat_launch_campaign_packet(packet)
    packet["validation"] = validation
    return packet


def build_live_stock_awareness_campaign_packet(payload=None):
    """Return Beacon live-stock awareness drafts without direct sales authority."""
    payload = payload if isinstance(payload, dict) else {}
    campaign_name = _clean_text(payload.get("campaign_name") or payload.get("pilot_name")) or "Live-stock awareness story"
    farm_name = _clean_text(payload.get("farm_name")) or "Amadeus Farm"
    area = _clean_text(payload.get("area")) or "Riversdale farm community"
    subject_focus = _clean_text(payload.get("subject_focus") or payload.get("product_focus")) or "piglets, litters, weaners, and daily farm life"

    packet = {
        "success": True,
        "mode": BEACON_LIVE_STOCK_AWARENESS_MODE,
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign_lane": "live_stock_awareness",
        "campaign": {
            "name": campaign_name,
            "status": "draft_only_owner_review_required",
            "farm_name": farm_name,
            "area": area,
            "subject_focus": subject_focus,
            "primary_goal": "Create warm farm-life awareness and audience trust without selling animals, meat, prices, reservations, or availability.",
        },
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "campaign_angles": _live_stock_awareness_angles(farm_name, area, subject_focus),
        "channel_drafts": _live_stock_awareness_channel_drafts(farm_name, area, subject_focus),
        "story_updates": _live_stock_awareness_story_updates(farm_name),
        "owner_review_checklist": list(LIVE_STOCK_OWNER_REVIEW_CHECKLIST),
        "handoff_to_sam": {
            "inbound_prompt": "If someone asks a buying question, Sam must treat it as an owner-review sales enquiry, not as proof of stock availability.",
            "must_not_say": [
                "Piglets are available now.",
                "You can reserve one.",
                "The price is final.",
                "Delivery is confirmed.",
                "Your order is confirmed.",
            ],
        },
        "next_gate": "owner_reviews_live_stock_awareness_campaign_before_any_public_or_customer_send",
    }
    validation = validate_live_stock_awareness_campaign_packet(packet)
    packet["validation"] = validation
    return packet


def validate_live_stock_awareness_campaign_packet(packet):
    drafts = _all_draft_texts(packet)
    unsafe = []
    missing_awareness_signal = []
    for draft in drafts:
        text = draft["text"].lower()
        if _has_live_stock_direct_sales_wording(text):
            unsafe.append(draft["id"])
        if not any(term in text for term in ("farm", "life", "journey", "grow", "story", "awareness", "new life", "piglet", "litter")):
            missing_awareness_signal.append(draft["id"])

    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    unsafe_flags = [
        name for name, value in authority.items()
        if name != "draft_only" and value is True
    ]
    return {
        "success": not unsafe and not missing_awareness_signal and not unsafe_flags,
        "checked_draft_count": len(drafts),
        "direct_sales_wording_drafts": unsafe,
        "missing_awareness_signal": missing_awareness_signal,
        "unsafe_authority_flags": unsafe_flags,
    }


def validate_meat_launch_campaign_packet(packet):
    drafts = _all_draft_texts(packet)
    unsafe = []
    missing_preorder = []
    missing_limited = []
    for draft in drafts:
        text = draft["text"].lower()
        if not _has_preorder_signal(text):
            missing_preorder.append(draft["id"])
        if "limited" not in text:
            missing_limited.append(draft["id"])
        if _has_forbidden_promise(text):
            unsafe.append(draft["id"])

    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    unsafe_flags = [
        name for name, value in authority.items()
        if name != "draft_only" and value is True
    ]

    return {
        "success": not unsafe and not missing_preorder and not missing_limited and not unsafe_flags,
        "checked_draft_count": len(drafts),
        "missing_preorder_signal": missing_preorder,
        "missing_limited_signal": missing_limited,
        "unsafe_promise_drafts": unsafe,
        "unsafe_authority_flags": unsafe_flags,
    }


def format_meat_launch_campaign_markdown(packet):
    campaign = packet.get("campaign", {})
    lines = [
        "# Meat Launch Campaign Packet",
        "",
        "## Status",
        "",
        f"- Mode: `{packet.get('mode', '')}`",
        f"- Agent: {packet.get('agent', 'Beacon')}",
        f"- Campaign: {campaign.get('name', '')}",
        f"- Status: {campaign.get('status', '')}",
        f"- Next gate: `{packet.get('next_gate', '')}`",
        "",
        "This packet is draft-only. It does not post publicly, send customer messages, create quotes or invoices, create orders, reserve carcasses, change stock, book slaughter, book a butcher slot, or confirm payments.",
        "",
        "## Campaign Goal",
        "",
        campaign.get("primary_goal", ""),
        "",
        "## Campaign Angles",
        "",
    ]
    for angle in packet.get("campaign_angles", []):
        lines.extend([
            f"### {angle.get('title', '')}",
            "",
            angle.get("summary", ""),
            "",
            f"- Best channel: {angle.get('best_channel', '')}",
            f"- Sam handoff: {angle.get('sam_handoff', '')}",
            "",
        ])

    lines.extend(["## Channel Drafts", ""])
    for draft in packet.get("channel_drafts", []):
        lines.extend([
            f"### {draft.get('label', draft.get('id', 'Draft'))}",
            "",
            f"- Channel: {draft.get('channel', '')}",
            f"- Intent: {draft.get('intent', '')}",
            "",
            "```text",
            draft.get("text", ""),
            "```",
            "",
        ])

    lines.extend(["## Story Updates", ""])
    for update in packet.get("story_updates", []):
        lines.extend([
            f"### {update.get('label', update.get('id', 'Story'))}",
            "",
            "```text",
            update.get("text", ""),
            "```",
            "",
        ])

    lines.extend(["## Owner Review Checklist", ""])
    for item in packet.get("owner_review_checklist", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## Authority Boundary",
        "",
    ])
    for name, value in sorted((packet.get("authority") or {}).items()):
        lines.append(f"- `{name}`: `{str(value).lower()}`")

    lines.extend([
        "",
        "## Forbidden Actions",
        "",
    ])
    for item in packet.get("forbidden_actions", []):
        lines.append(f"- `{item}`")

    validation = packet.get("validation", {})
    lines.extend([
        "",
        "## Validation",
        "",
        f"- Success: `{str(validation.get('success')).lower()}`",
        f"- Checked drafts: `{validation.get('checked_draft_count', 0)}`",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _campaign_angles(farm_name, area, product_focus):
    return [
        {
            "id": "controlled_freezer_preorder",
            "title": "Controlled Freezer Preorder",
            "summary": f"Position {farm_name} pork as a limited, pre-booked freezer run for households that want to plan ahead instead of buying anonymous supermarket meat.",
            "best_channel": "WhatsApp status and Facebook",
            "sam_handoff": "Ask whether the buyer wants half carcass, full carcass, or cut-set guidance.",
        },
        {
            "id": "set_a_family_pack",
            "title": "Set A Family Freezer Pack",
            "summary": "Explain Set A as the practical family freezer option while keeping price, timing, and final packed weight for the farm confirmation step.",
            "best_channel": "Facebook and direct known buyers",
            "sam_handoff": "Answer what Set A includes, then collect town, delivery address or farm name, timing, and payment preference.",
        },
        {
            "id": "farm_to_freezer_story",
            "title": "Farm To Freezer Story",
            "summary": f"Show the journey from farm planning to packed pork, with limited availability and pre-booking as part of the story rather than a pressure tactic.",
            "best_channel": "Instagram story and WhatsApp status",
            "sam_handoff": "Invite replies from people who want Sam to check the best fit for their freezer, household size, or target kg.",
        },
        {
            "id": "local_route_pilot",
            "title": "Local Route Pilot",
            "summary": f"Keep the first run focused around {area}, so delivery promises stay controlled while demand is measured.",
            "best_channel": "WhatsApp status and known-buyer share",
            "sam_handoff": "Capture address or shared location when delivery is requested.",
        },
    ]


def _channel_drafts(farm_name, area, product_focus):
    return [
        {
            "id": "whatsapp_status_1",
            "label": "WhatsApp Status 1",
            "channel": "WhatsApp status",
            "intent": "Soft interest check",
            "text": f"{farm_name} is preparing a limited pork freezer preorder run for {area}. Half carcass Set A and full carcass options are pre-booked only; price, timing, and final packed weight are confirmed before booking. Reply if you want Sam to note your interest.",
        },
        {
            "id": "whatsapp_status_2",
            "label": "WhatsApp Status 2",
            "channel": "WhatsApp status",
            "intent": "Explain the offer simply",
            "text": "Limited pork freezer preorders are opening. This is not ready-shelf stock; it is pre-booked farm pork, packed after processing, with final weight confirmed once known. Ask Sam about half carcass Set A, full carcass, or delivery planning.",
        },
        {
            "id": "whatsapp_channel",
            "label": "WhatsApp Channel Draft",
            "channel": "WhatsApp channel or broadcast draft",
            "intent": "First owner-approved announcement",
            "text": f"We are testing a limited {farm_name} pork freezer preorder run. The focus is {product_focus}. Orders are pre-booked, and the farm confirms price, available timing, deposit steps, and final packed weight before anything is booked. Message Sam if you want to be added to the review list.",
        },
        {
            "id": "facebook_post",
            "label": "Facebook Post Draft",
            "channel": "Facebook",
            "intent": "Public demand generation",
            "text": f"{farm_name} is preparing a limited pork freezer preorder pilot for {area}. We are starting small so that every booking can be handled properly. The first focus is {product_focus}. This is pre-booked farm pork, not unlimited shop stock: price, timing, delivery planning, deposit steps, and final packed weight are confirmed before the booking is accepted. If you want pork for your freezer, send us a message and Sam will collect the details.",
        },
        {
            "id": "instagram_caption",
            "label": "Instagram Caption Draft",
            "channel": "Instagram",
            "intent": "Story-led launch caption",
            "text": f"A small farm run, planned properly. {farm_name} is opening limited pork freezer preorders, starting with half carcass Set A and full carcass interest. Every order is pre-booked, with price, timing, deposit steps, and final packed weight confirmed before booking. Message Sam if you want to join the first review list.",
        },
        {
            "id": "customer_education",
            "label": "Customer Education Draft",
            "channel": "Facebook/WhatsApp explainer",
            "intent": "Reduce confusion about final weight",
            "text": "How the freezer preorder works: availability is limited, so interest is captured first. The farm then confirms price/kg, timing, delivery planning, and deposit steps. Packed weight is estimated early, but the final amount is only confirmed after processing, because real carcass and cut yield can vary.",
        },
    ]


def _story_updates(farm_name, area):
    return [
        {
            "id": "story_slide_1",
            "label": "Story Slide 1",
            "text": f"Limited pork freezer preorders are opening soon from {farm_name}. Pre-booked only, starting with the first controlled pilot around {area}.",
        },
        {
            "id": "story_slide_2",
            "label": "Story Slide 2",
            "text": "Half carcass Set A is for families who want practical freezer pork. Limited availability, pre-booked, with final packed weight confirmed after processing.",
        },
        {
            "id": "story_slide_3",
            "label": "Story Slide 3",
            "text": "Sam will collect the details: half or full carcass, town, delivery address or farm name, timing, payment preference, and any freezer-size or target-kg preference. Limited pre-booked run only.",
        },
        {
            "id": "story_slide_4",
            "label": "Story Slide 4",
            "text": "Want to join the limited preorder review list? Reply and Sam will capture your interest. No booking is final until the farm confirms price, timing, and deposit steps.",
        },
    ]


def _live_stock_awareness_angles(farm_name, area, subject_focus):
    return [
        {
            "id": "new_life_on_farm",
            "title": "New Life On The Farm",
            "summary": f"Use {subject_focus} to show the quiet daily moments behind {farm_name}, with no sales promise.",
            "best_channel": "Facebook and Instagram",
            "sam_handoff": "If a buying question arrives, route to owner-review sales handling instead of answering availability.",
        },
        {
            "id": "animal_care_story",
            "title": "Animal Care Story",
            "summary": "Show healthy feeding, growth, and farm care as an awareness story.",
            "best_channel": "Facebook",
            "sam_handoff": "Keep replies warm and factual; do not offer stock, price, delivery, or reservation.",
        },
        {
            "id": "farm_personality",
            "title": "Farm Personality",
            "summary": "Invite comments, names, and engagement around the animals' personalities.",
            "best_channel": "Facebook comments and stories",
            "sam_handoff": "Community engagement can continue, but sales questions need owner review.",
        },
    ]


def _live_stock_awareness_channel_drafts(farm_name, area, subject_focus):
    return [
        {
            "id": "facebook_awareness_post",
            "label": "Facebook Awareness Post",
            "channel": "Facebook",
            "intent": "Warm farm-life awareness",
            "text": f"There is always something beautiful about new life on the farm. At {farm_name}, moments with {subject_focus} remind us why the daily care, patience, and quiet work matter. We will share more of their journey as they grow and explore.",
        },
        {
            "id": "facebook_name_prompt",
            "label": "Facebook Name Prompt",
            "channel": "Facebook",
            "intent": "Community engagement without selling",
            "text": f"The newest little characters at {farm_name} are starting to show their personalities. For now it is warm naps, full bellies, and mom doing her work beautifully. What should we call this little group?",
        },
        {
            "id": "instagram_awareness_caption",
            "label": "Instagram Awareness Caption",
            "channel": "Instagram",
            "intent": "Visual farm story",
            "text": f"A small farm-life moment from {area}: healthy little ones staying close, feeding strong, and growing into their own personalities. This is the kind of everyday story we love sharing from {farm_name}.",
        },
        {
            "id": "whatsapp_status_awareness",
            "label": "WhatsApp Status Awareness",
            "channel": "WhatsApp status",
            "intent": "Owner community update",
            "text": f"New life on the farm today. The little ones are feeding well, staying close, and giving us another reason to smile at {farm_name}.",
        },
    ]


def _live_stock_awareness_story_updates(farm_name):
    return [
        {
            "id": "story_new_life_1",
            "label": "Story Slide 1",
            "text": f"New life at {farm_name}: tiny feet, warm naps, and a strong mom doing her job.",
        },
        {
            "id": "story_new_life_2",
            "label": "Story Slide 2",
            "text": "The little ones are staying close and feeding well. These quiet moments are what farm life is built on.",
        },
        {
            "id": "story_new_life_3",
            "label": "Story Slide 3",
            "text": "We will share more of their journey as they grow, explore, and start showing their personalities.",
        },
    ]


def _rank_approved_assets(assets, campaign_lane="meat_launch"):
    campaign_lane = normalize_campaign_lane(campaign_lane) or "meat_launch"
    ranked = []
    for asset in assets:
        if _asset_status(asset) != "approved":
            continue
        tags = _asset_list(asset.get("subject_tags"))
        relevance = _asset_list(asset.get("sale_stream_relevance"))
        privacy_risk = _clean_text(asset.get("privacy_risk")).lower() or "unknown"
        media_type = _clean_text(asset.get("media_type")).lower() or "unknown"
        quality_score = _safe_int(asset.get("quality_score"), 0)
        score = quality_score
        if media_type == "image":
            score += 20
        if media_type == "video":
            score += 15
        if campaign_lane == "meat_launch" and "meat" in relevance:
            score += 25
        if campaign_lane == "live_stock_awareness" and any(item in relevance for item in ("live", "live_stock", "livestock", "farm_life")):
            score += 30
        if campaign_lane == "live_stock_sales" and any(item in relevance for item in ("live", "live_stock", "livestock", "live_stock_sales")):
            score += 35
        if campaign_lane == "meat_launch" and any(tag in tags for tag in ("pork", "freezer", "set a", "half carcass", "family pack")):
            score += 15
        if campaign_lane == "live_stock_awareness" and any(tag in tags for tag in ("piglet", "piglets", "litter", "weaner", "weaners", "sow", "farm life", "new life")):
            score += 25
        if privacy_risk in ("high", "medium"):
            score -= 40 if privacy_risk == "high" else 20
        ranked.append({
            "asset_id": asset.get("asset_id", ""),
            "title": asset.get("title") or asset.get("original_filename") or asset.get("asset_id", ""),
            "media_type": media_type,
            "storage_bucket": asset.get("storage_bucket", ""),
            "storage_path": asset.get("storage_path", ""),
            "content_sha256": asset.get("content_sha256", ""),
            "subject_tags": tags,
            "sale_stream_relevance": relevance,
            "quality_score": asset.get("quality_score"),
            "privacy_risk": privacy_risk,
            "selection_score": max(0, min(score, 160)),
            "public_use_approved": bool(asset.get("effective_public_use_approved") or asset.get("public_use_approved")),
            "why": _asset_why(tags, relevance, media_type, privacy_risk),
        })
    return sorted(ranked, key=lambda item: (-item["selection_score"], item["asset_id"]))[:12]


def _channel_asset_pairings(drafts, ranked_assets, fallback_channel="campaign"):
    pairings = []
    for draft in drafts:
        best = _best_asset_for_draft(draft, ranked_assets)
        pairings.append({
            "draft_id": draft.get("id", ""),
            "draft_label": draft.get("label") or draft.get("id", ""),
            "channel": draft.get("channel") or fallback_channel,
            "intent": draft.get("intent", ""),
            "recommended_asset_id": best.get("asset_id", "") if best else "",
            "recommended_asset_title": best.get("title", "") if best else "",
            "selection_reason": _selection_reason(draft, best),
            "requires_owner_final_selection": True,
        })
    return pairings


def _best_asset_for_draft(draft, ranked_assets):
    if not ranked_assets:
        return {}
    text = f"{draft.get('channel', '')} {draft.get('intent', '')} {draft.get('text', '')}".lower()
    best_asset = ranked_assets[0]
    best_score = -1
    for asset in ranked_assets:
        score = asset.get("selection_score", 0)
        tags = " ".join(asset.get("subject_tags", [])).lower()
        if "story" in text and asset.get("media_type") in ("image", "video"):
            score += 8
        if "family" in text and "family" in tags:
            score += 10
        if "set a" in text and ("set a" in tags or "freezer" in tags):
            score += 10
        if "facebook" in text and asset.get("media_type") == "image":
            score += 5
        if score > best_score:
            best_asset = asset
            best_score = score
    return best_asset


def _selection_reason(draft, asset):
    if not asset:
        return "No owner-approved media asset is available yet. Draft can stay text-only until media is approved."
    return f"Matches {draft.get('label') or draft.get('id')} because it is approved for public-use review, scored {asset.get('selection_score')}, and is tagged {', '.join(asset.get('subject_tags') or ['general'])}."


def _asset_why(tags, relevance, media_type, privacy_risk):
    parts = [f"{media_type or 'unknown'} media"]
    if relevance:
        parts.append(f"relevant to {', '.join(relevance)}")
    if tags:
        parts.append(f"tagged {', '.join(tags[:4])}")
    parts.append(f"privacy risk {privacy_risk}")
    return "; ".join(parts)


def _asset_status(asset):
    return _clean_text(asset.get("effective_approval_status") or asset.get("approval_status")).lower()


def _asset_list(value):
    if isinstance(value, list):
        return [_clean_text(item).lower() for item in value if _clean_text(item)]
    if isinstance(value, str):
        return [_clean_text(item).lower() for item in value.split(",") if _clean_text(item)]
    return []


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _find_draft(packet, draft_id):
    for group in ("channel_drafts", "story_updates"):
        for draft in packet.get(group, []):
            if draft.get("id") == draft_id:
                return draft
    return {}


def _find_asset(assets, asset_id):
    if not asset_id:
        return {}
    for asset in assets:
        if asset.get("asset_id") == asset_id:
            return asset
    return {}


def _selected_asset_ids(payload, limit=10):
    values = payload.get("asset_ids") if isinstance(payload.get("asset_ids"), list) else []
    if not values and payload.get("asset_id"):
        values = [payload.get("asset_id")]
    result = []
    for value in values:
        asset_id = _clean_text(value)[:120]
        if asset_id and asset_id not in result:
            result.append(asset_id)
        if len(result) >= limit:
            break
    return result


def _publish_packet_id(draft_id, asset_id, channel, pilot_cap, exact_text=""):
    seed = "|".join([draft_id or "draft", asset_id or "text-only", channel or "channel", pilot_cap or "cap", exact_text or "canonical"])
    total = 0
    for char in seed:
        total = (total * 33 + ord(char)) % 0xFFFFFFFF
    return f"BEACON-PUBLISH-PACKET-{total:08X}"


def _meat_launch_publish_packet_id(draft_id, asset_id, channel, pilot_cap, exact_text, owner_offer_enabled):
    snapshot = {
        "schema_version": "beacon_meat_launch_readiness_v1",
        "campaign_lane": "meat_launch",
        "draft_id": draft_id,
        "asset_id": asset_id,
        "channel": channel,
        "pilot_cap": pilot_cap,
        "exact_text": exact_text,
        "owner_offer_enabled": bool(owner_offer_enabled),
    }
    digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode("utf-8")).hexdigest()[:20].upper()
    return f"BEACON-MEAT-PUBLISH-{digest}"


def _manual_post_params(payload):
    metrics = _metrics(payload)
    posted_at = _clean_text(payload.get("posted_at"))[:80]
    params = {
        "manual_post_event_id": _clean_text(payload.get("manual_post_event_id"))[:120],
        "mode": "beacon_manual_public_post_evidence_only",
        "publish_packet_id": _clean_text(payload.get("publish_packet_id"))[:120],
        "channel": _clean_text(payload.get("channel"))[:80],
        "post_url": _clean_text(payload.get("post_url"))[:700],
        "posted_at": posted_at or None,
        "posted_by": _clean_text(payload.get("posted_by") or "owner_manual_post")[:120],
        "campaign_label": _clean_text(payload.get("campaign_label"))[:160],
        "evidence_notes": _clean_text(payload.get("evidence_notes") or payload.get("notes"))[:1200],
        "initial_metrics_json": json.dumps(metrics, sort_keys=True, default=str),
        **MANUAL_POST_AUTHORITY_FLAGS,
    }
    if not params["manual_post_event_id"]:
        params["manual_post_event_id"] = _manual_post_event_id(params)
    return params


def _metrics(payload):
    metrics = {}
    for key in ("reactions", "comments", "shares", "messages", "leads"):
        value = _safe_int(payload.get(key), 0)
        if value:
            metrics[key] = max(0, value)
    return metrics


def _public_manual_post_event(params):
    return {
        "manual_post_event_id": params.get("manual_post_event_id", ""),
        "mode": params.get("mode", "beacon_manual_public_post_evidence_only"),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "post_url": params.get("post_url", ""),
        "posted_at": params.get("posted_at") or "",
        "posted_by": params.get("posted_by", ""),
        "campaign_label": params.get("campaign_label", ""),
        "evidence_notes": params.get("evidence_notes", ""),
        "initial_metrics": _loads(params.get("initial_metrics_json"), {}),
        **MANUAL_POST_AUTHORITY_FLAGS,
    }


def _manual_post_row_to_event(row):
    return {
        "manual_post_event_id": row[0],
        "mode": "beacon_manual_public_post_evidence_only",
        "publish_packet_id": row[1],
        "channel": row[2],
        "post_url": row[3],
        "posted_at": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4] or ""),
        "posted_by": row[5],
        "campaign_label": row[6],
        "evidence_notes": row[7],
        "initial_metrics": row[8] or {},
        "created_at": row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9] or ""),
        **MANUAL_POST_AUTHORITY_FLAGS,
    }


def _manual_post_event_id(params):
    seed = {
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "post_url": params.get("post_url", ""),
        "posted_at": params.get("posted_at", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:18].upper()
    return f"BEACON-MANUAL-POST-{digest}"


def _manual_post_unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "beacon_manual_public_post_evidence_only",
        "manual_post_events": [],
        "policy": manual_post_evidence_policy(),
        **MANUAL_POST_AUTHORITY_FLAGS,
    }


def _performance_params(payload):
    spend_amount = _safe_money(payload.get("spend_amount") or payload.get("spend"))
    evidence = _performance_metric_evidence(payload)
    messages = _verified_metric_value(evidence, "messages_to_sam")
    qualified = _verified_metric_value(evidence, "qualified_buyer_leads")
    recommendation = _recommend_boost(payload, spend_amount, messages, qualified, evidence=evidence)
    cost_per_message = _cost(spend_amount, messages)
    cost_per_qualified_lead = _cost(spend_amount, qualified)
    params = {
        "performance_event_id": _clean_text(payload.get("performance_event_id"))[:120],
        "mode": "beacon_campaign_performance_evidence_only",
        "manual_post_event_id": _clean_text(payload.get("manual_post_event_id"))[:120],
        "publish_packet_id": _clean_text(payload.get("publish_packet_id"))[:120],
        "channel": _clean_text(payload.get("channel") or "Facebook")[:80],
        "measurement_window": _clean_text(payload.get("measurement_window") or "manual_snapshot")[:120],
        "spend_amount": spend_amount,
        "spend_currency": _clean_text(payload.get("spend_currency") or "ZAR")[:12],
        "reach": _safe_int(payload.get("reach"), 0),
        "impressions": _safe_int(payload.get("impressions"), 0),
        "reactions": _safe_int(payload.get("reactions"), 0),
        "comments": _safe_int(payload.get("comments"), 0),
        "shares": _safe_int(payload.get("shares"), 0),
        "messages_to_sam": messages,
        "qualified_buyer_leads": qualified,
        "booking_review_requests": _safe_int(payload.get("booking_review_requests"), 0),
        "notes": _clean_text(payload.get("notes") or payload.get("performance_notes"))[:1200],
        "recommended_action": recommendation["recommended_action"],
        "recommendation_reason": recommendation["recommendation_reason"],
        "recommended_spend_amount": recommendation["recommended_spend_amount"],
        "recommended_duration_days": recommendation["recommended_duration_days"],
        "max_spend_cap_amount": BOOST_RECOMMENDATION_SPEND_CAP,
        "cost_per_message": cost_per_message,
        "cost_per_qualified_lead": cost_per_qualified_lead,
        "recorded_by": _clean_text(payload.get("recorded_by") or "beacon_performance_tracking")[:120],
        "metric_evidence_json": json.dumps(evidence, sort_keys=True, default=str),
        "evidence_source": _clean_text(payload.get("evidence_source") or "owner_manual")[:80],
        "source_reference": _clean_text(payload.get("source_reference") or payload.get("manual_post_event_id") or payload.get("publish_packet_id"))[:240],
        "retrieved_at": _clean_text(payload.get("retrieved_at")) or datetime.now(timezone.utc).isoformat(),
        "supersedes_event_id": _clean_text(payload.get("supersedes_event_id"))[:120],
        **PERFORMANCE_AUTHORITY_FLAGS,
    }
    params["recommends_boost"] = params["recommended_action"] == "light_boost_owner_review"
    if not params["performance_event_id"]:
        params["performance_event_id"] = _performance_event_id(params)
    return params


def _recommend_boost(payload, spend_amount, messages, qualified, evidence=None):
    evidence = evidence or _performance_metric_evidence(payload)
    fulfillment_risk = _clean_text(payload.get("fulfillment_risk")).lower()
    safety_risk = _clean_text(payload.get("safety_risk")).lower()
    owner_blocked = str(payload.get("owner_blocked") or "").strip().lower() in {"1", "true", "yes", "on"}
    requested_spend = _safe_money(payload.get("recommended_spend_amount"))
    if owner_blocked or fulfillment_risk in {"high", "blocked"} or safety_risk in {"high", "blocked"}:
        return {
            "recommended_action": "do_not_boost",
            "recommendation_reason": "Do not boost because fulfilment, owner, or safety risk is marked high.",
            "recommended_spend_amount": 0,
            "recommended_duration_days": 0,
        }
    if (evidence.get("messages_to_sam") or {}).get("status") not in {"verified", "owner_correction"} and (evidence.get("qualified_buyer_leads") or {}).get("status") not in {"verified", "owner_correction"}:
        return {"recommended_action": "wait_for_more_data", "recommendation_reason": "Message and qualified-lead evidence is unavailable; no performance conclusion is supported.", "recommended_spend_amount": 0, "recommended_duration_days": 0}
    if requested_spend > BOOST_RECOMMENDATION_SPEND_CAP:
        return {
            "recommended_action": "owner_review_required",
            "recommendation_reason": f"Requested spend exceeds the R{BOOST_RECOMMENDATION_SPEND_CAP} cap and needs owner review before any later paid action.",
            "recommended_spend_amount": BOOST_RECOMMENDATION_SPEND_CAP,
            "recommended_duration_days": _safe_int(payload.get("recommended_duration_days"), 3) or 3,
        }
    if qualified >= 1 or messages >= 2:
        spend = requested_spend or 150
        return {
            "recommended_action": "light_boost_owner_review",
            "recommendation_reason": "Recommend a light owner-reviewed boost because the post has early buyer-message evidence.",
            "recommended_spend_amount": min(spend, BOOST_RECOMMENDATION_SPEND_CAP),
            "recommended_duration_days": _safe_int(payload.get("recommended_duration_days"), 3) or 3,
        }
    if messages == 0 and qualified == 0 and spend_amount > 0:
        return {
            "recommended_action": "do_not_boost",
            "recommendation_reason": "Do not boost further because spend has not produced Sam messages or qualified buyer leads.",
            "recommended_spend_amount": 0,
            "recommended_duration_days": 0,
        }
    return {
        "recommended_action": "wait_for_more_data",
        "recommendation_reason": "Wait for more evidence before recommending paid boost.",
        "recommended_spend_amount": 0,
        "recommended_duration_days": 0,
    }


def _boost_packet(params):
    if not params:
        return {}
    return {
        "success": True,
        "mode": "beacon_boost_recommendation_owner_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "performance_event_id": params.get("performance_event_id", ""),
        "manual_post_event_id": params.get("manual_post_event_id", ""),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "recommended_action": params.get("recommended_action", "wait_for_more_data"),
        "recommendation_reason": params.get("recommendation_reason", ""),
        "recommended_spend_amount": params.get("recommended_spend_amount", 0),
        "recommended_duration_days": params.get("recommended_duration_days", 0),
        "max_spend_cap_amount": params.get("max_spend_cap_amount", BOOST_RECOMMENDATION_SPEND_CAP),
        "currency": params.get("spend_currency", "ZAR"),
        "primary_metrics": {
            "messages_to_sam": params.get("messages_to_sam", 0),
            "qualified_buyer_leads": params.get("qualified_buyer_leads", 0),
            "cost_per_message": params.get("cost_per_message"),
            "cost_per_qualified_lead": params.get("cost_per_qualified_lead"),
        },
        "approval_status": "owner_review_required" if params.get("recommended_action") in {"light_boost_owner_review", "owner_review_required"} else "no_paid_action_requested",
        "approval_executes_boost": False,
        "calls_meta_now": False,
        "spends_money_now": False,
        "owner_review_checklist": [
            "Check that Sam can handle more messages from this post.",
            "Check that meat stock, carcass reservations, delivery, and fulfilment capacity can absorb the extra demand.",
            "Confirm the spend amount stays within the R500 test cap.",
            "Use this as recommendation evidence only; no Facebook/Meta boost is executed here.",
        ],
        "next_gate": "owner_approves_boost_packet_before_any_future_meta_ads_execution",
        **PERFORMANCE_AUTHORITY_FLAGS,
        "recommends_boost": params.get("recommended_action") == "light_boost_owner_review",
    }


def _public_performance_event(params):
    return {
        "performance_event_id": params.get("performance_event_id", ""),
        "mode": params.get("mode", "beacon_campaign_performance_evidence_only"),
        "manual_post_event_id": params.get("manual_post_event_id", ""),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "measurement_window": params.get("measurement_window", ""),
        "spend_amount": params.get("spend_amount", 0),
        "spend_currency": params.get("spend_currency", "ZAR"),
        "reach": params.get("reach", 0),
        "impressions": params.get("impressions", 0),
        "reactions": params.get("reactions", 0),
        "comments": params.get("comments", 0),
        "shares": params.get("shares", 0),
        "messages_to_sam": params.get("messages_to_sam", 0),
        "qualified_buyer_leads": params.get("qualified_buyer_leads", 0),
        "booking_review_requests": params.get("booking_review_requests", 0),
        "notes": params.get("notes", ""),
        "recommended_action": params.get("recommended_action", ""),
        "recommendation_reason": params.get("recommendation_reason", ""),
        "recommended_spend_amount": params.get("recommended_spend_amount", 0),
        "recommended_duration_days": params.get("recommended_duration_days", 0),
        "max_spend_cap_amount": params.get("max_spend_cap_amount", BOOST_RECOMMENDATION_SPEND_CAP),
        "cost_per_message": params.get("cost_per_message"),
        "cost_per_qualified_lead": params.get("cost_per_qualified_lead"),
        "recorded_by": params.get("recorded_by", ""),
        "metric_evidence": _loads(params.get("metric_evidence_json"), {}),
        "evidence_source": params.get("evidence_source", ""),
        "source_reference": params.get("source_reference", ""),
        "retrieved_at": params.get("retrieved_at", ""),
        "source_snapshot_key": params.get("performance_event_id", ""),
        "supersedes_event_id": params.get("supersedes_event_id", ""),
        **PERFORMANCE_AUTHORITY_FLAGS,
        "recommends_boost": params.get("recommended_action") == "light_boost_owner_review",
    }


def _performance_row_to_event(row):
    return {
        "performance_event_id": row[0],
        "mode": "beacon_campaign_performance_evidence_only",
        "manual_post_event_id": row[1],
        "publish_packet_id": row[2],
        "channel": row[3],
        "measurement_window": row[4],
        "spend_amount": float(row[5] or 0),
        "spend_currency": row[6],
        "reach": row[7],
        "impressions": row[8],
        "reactions": row[9],
        "comments": row[10],
        "shares": row[11],
        "messages_to_sam": row[12],
        "qualified_buyer_leads": row[13],
        "booking_review_requests": row[14],
        "notes": row[15],
        "recommended_action": row[16],
        "recommendation_reason": row[17],
        "recommended_spend_amount": float(row[18] or 0),
        "recommended_duration_days": row[19],
        "max_spend_cap_amount": float(row[20] or BOOST_RECOMMENDATION_SPEND_CAP),
        "cost_per_message": float(row[21]) if row[21] is not None else None,
        "cost_per_qualified_lead": float(row[22]) if row[22] is not None else None,
        "recommends_boost": bool(row[23]),
        "recorded_by": row[24],
        "created_at": row[25].isoformat() if hasattr(row[25], "isoformat") else str(row[25] or ""),
        "metric_evidence": row[26] or {},
        "evidence_source": row[27] or "",
        "source_reference": row[28] or "",
        "retrieved_at": row[29].isoformat() if hasattr(row[29], "isoformat") else str(row[29] or ""),
        "source_snapshot_key": row[30] or "",
        "supersedes_event_id": row[31] or "",
        **PERFORMANCE_AUTHORITY_FLAGS,
    }


def _event_to_performance_params(event):
    event = event if isinstance(event, dict) else {}
    params = dict(event)
    params.setdefault("max_spend_cap_amount", BOOST_RECOMMENDATION_SPEND_CAP)
    params.setdefault("spend_currency", "ZAR")
    params.setdefault("recommended_action", "wait_for_more_data")
    params.setdefault("recommendation_reason", "")
    params.setdefault("recommended_spend_amount", 0)
    params.setdefault("recommended_duration_days", 0)
    return params


def _performance_event_id(params):
    evidence = _loads(params.get("metric_evidence_json"), {})
    canonical_evidence = {name: {key: value for key, value in item.items() if key != "retrieved_at"} for name, item in evidence.items()}
    seed = {
        "manual_post_event_id": params.get("manual_post_event_id", ""),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "measurement_window": params.get("measurement_window", ""),
        "source_reference": params.get("source_reference", ""),
        "metric_evidence": canonical_evidence,
        "supersedes_event_id": params.get("supersedes_event_id", ""),
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:18].upper()
    return f"BEACON-PERF-{digest}"


def _performance_metric_evidence(payload):
    supplied = payload.get("metric_evidence") if isinstance(payload.get("metric_evidence"), dict) else {}
    source = _clean_text(payload.get("evidence_source") or "owner_manual")[:80]
    reference = _clean_text(payload.get("source_reference") or payload.get("manual_post_event_id") or payload.get("publish_packet_id"))[:240]
    retrieved = _clean_text(payload.get("retrieved_at")) or datetime.now(timezone.utc).isoformat()
    aliases = {"messages_to_sam": "messages", "qualified_buyer_leads": "qualified_leads"}
    result = {}
    for name in ("spend_amount", "reach", "impressions", "reactions", "comments", "shares", "messages_to_sam", "qualified_buyer_leads", "booking_review_requests", "sales", "revenue"):
        item = supplied.get(name) if isinstance(supplied.get(name), dict) else None
        if item:
            status = _clean_text(item.get("status"))
            value = item.get("value")
        else:
            key = name if name in payload else aliases.get(name)
            raw = payload.get(key) if key else None
            status, value = ("verified", raw) if raw not in (None, "") else ("missing", None)
        if status in {"verified", "owner_correction"}:
            try:
                value = float(value) if name in {"spend_amount", "revenue"} else int(value)
                if value < 0: raise ValueError
            except (TypeError, ValueError):
                status, value = "malformed", None
        elif status not in {"missing", "unsupported", "malformed", "provider_error", "owner_correction"}:
            status, value = "malformed", None
        result[name] = {"value": value, "status": status, "source": _clean_text((item or {}).get("source") or source), "source_reference": _clean_text((item or {}).get("source_reference") or reference), "retrieved_at": _clean_text((item or {}).get("retrieved_at") or retrieved)}
    return result


def _verified_metric_value(evidence, name):
    item = evidence.get(name) or {}
    return item.get("value") if item.get("status") in {"verified", "owner_correction"} else 0


def _performance_unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "beacon_campaign_performance_evidence_only",
        "performance_events": [],
        **PERFORMANCE_AUTHORITY_FLAGS,
    }


def _facebook_execution_authority(executed):
    return {
        **PERFORMANCE_AUTHORITY_FLAGS,
        "draft_only": False,
        "posts_publicly": bool(executed),
        "calls_meta": bool(executed),
        "customer_public_output_enabled": bool(executed),
        "boosts_post": False,
        "spends_money": False,
        "sends_customer_message": False,
    }


def _facebook_post_params(payload, policy):
    selected_asset = payload.get("selected_asset") if isinstance(payload.get("selected_asset"), dict) else {}
    selected_assets = payload.get("selected_assets") if isinstance(payload.get("selected_assets"), list) else []
    selected_assets = [item for item in selected_assets if isinstance(item, dict)][:10]
    if not selected_assets and selected_asset:
        selected_assets = [selected_asset]
    media_types = [str(item.get("media_type") or "").lower() for item in selected_assets]
    if not selected_assets:
        post_kind = "feed"
    elif len(selected_assets) == 1:
        post_kind = "video" if media_types[0] == "video" else "photo"
    elif all(value == "image" for value in media_types):
        post_kind = "multi_photo"
    else:
        post_kind = "mixed_media_manual"
    params = {
        "execution_event_id": "",
        "mode": "beacon_facebook_page_post_execution_gate",
        "publish_packet_id": _clean_text(payload.get("publish_packet_id"))[:120],
        "channel": _clean_text(payload.get("channel") or "Facebook")[:80],
        "exact_text": _clean_text(payload.get("exact_text") or payload.get("message"))[:5000],
        "asset_id": _clean_text(payload.get("asset_id") or selected_asset.get("asset_id"))[:120],
        "selected_asset": selected_asset,
        "selected_assets": selected_assets,
        "selected_media_json": "{}",
        "post_kind": post_kind,
        "owner_confirmation": _clean_text(payload.get("owner_confirmation"))[:120],
        "execution_status": "not_attempted",
        "facebook_post_id": "",
        "facebook_response_json": "{}",
        "recorded_by": _clean_text(payload.get("recorded_by") or "beacon_facebook_post_execution_gate")[:120],
        "policy_enabled": bool(policy.get("enabled")),
        "page_id_configured": bool(policy.get("page_id_configured")),
        "page_access_token_configured": bool(policy.get("page_access_token_configured")),
    }
    if selected_assets:
        params["selected_media_json"] = json.dumps(_facebook_selected_media(params), sort_keys=True, default=str)
    params["execution_event_id"] = _facebook_post_execution_id(params)
    return params


def _facebook_post_validation_error(params, policy):
    if not params.get("publish_packet_id"):
        return "publish_packet_id_required"
    if not params.get("exact_text"):
        return "exact_text_required"
    assets = params.get("selected_assets") if isinstance(params.get("selected_assets"), list) else []
    if assets:
        if params.get("post_kind") == "mixed_media_manual":
            return "facebook_mixed_media_requires_manual_composer"
        for asset in assets:
            if asset.get("media_type") not in {"image", "video"}:
                return "selected_media_type_not_supported"
            if not (asset.get("effective_public_use_approved") or asset.get("public_use_approved")):
                return "selected_media_asset_not_public_use_approved"
            if not asset.get("storage_bucket") or not asset.get("storage_path"):
                return "selected_media_asset_storage_missing"
        if not policy.get("media_storage_configured"):
            return "facebook_media_posting_storage_not_configured"
    if params.get("owner_confirmation") != FACEBOOK_POST_CONFIRMATION_PHRASE:
        return "owner_confirmation_required"
    if "facebook" not in params.get("channel", "").lower():
        return "channel_not_facebook"
    if not policy.get("enabled"):
        return "facebook_posting_disabled"
    if not policy.get("page_id_configured") or not policy.get("page_access_token_configured"):
        return "facebook_page_credentials_missing"
    return ""


def _post_to_facebook_page(params, policy, environ=None):
    if params.get("post_kind") == "multi_photo":
        return _post_to_facebook_page_multi_photo(params, policy, environ=environ)
    if params.get("post_kind") == "video":
        return _post_to_facebook_page_video(params, policy, environ=environ)
    if params.get("asset_id"):
        return _post_to_facebook_page_photos(params, policy, environ=environ)
    return _post_to_facebook_page_feed(params, policy, environ=environ)


def _post_to_facebook_page_feed(params, policy, environ=None):
    source = environ if environ is not None else os.environ
    page_id = _clean_text(source.get(FACEBOOK_PAGE_ID_ENV))
    token = _clean_text(source.get(FACEBOOK_PAGE_ACCESS_TOKEN_ENV))
    version = _clean_text(source.get(FACEBOOK_GRAPH_VERSION_ENV)) or "v23.0"
    if not page_id or not token:
        return {"success": False, "status": "facebook_page_credentials_missing"}, 503
    endpoint = f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/{urllib_parse.quote(page_id, safe='')}/feed"
    body = urllib_parse.urlencode({
        "message": params.get("exact_text", ""),
        "access_token": token,
    }).encode("utf-8")
    req = urllib_request.Request(endpoint, data=body, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw or "{}")
            return {"success": True, **payload}, response.status
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status": "facebook_http_error",
            "http_status": exc.code,
            "error": raw[:500],
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "status": "facebook_post_request_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
        }, 502


def _post_to_facebook_page_photos(params, policy, environ=None):
    source = environ if environ is not None else os.environ
    page_id = _clean_text(source.get(FACEBOOK_PAGE_ID_ENV))
    token = _clean_text(source.get(FACEBOOK_PAGE_ACCESS_TOKEN_ENV))
    version = _clean_text(source.get(FACEBOOK_GRAPH_VERSION_ENV)) or "v23.0"
    if not page_id or not token:
        return {"success": False, "status": "facebook_page_credentials_missing"}, 503
    signed_url_result, signed_url_status = _signed_supabase_media_url(params, environ=source)
    if signed_url_status >= 400:
        return signed_url_result, signed_url_status
    endpoint = f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/{urllib_parse.quote(page_id, safe='')}/photos"
    body = urllib_parse.urlencode({
        "caption": params.get("exact_text", ""),
        "url": signed_url_result.get("signed_url", ""),
        "access_token": token,
    }).encode("utf-8")
    req = urllib_request.Request(endpoint, data=body, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=35) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw or "{}")
            return {
                "success": True,
                "post_kind": "photo",
                "selected_media": _facebook_selected_media(params),
                **payload,
            }, response.status
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status": "facebook_http_error",
            "http_status": exc.code,
            "post_kind": "photo",
            "selected_media": _facebook_selected_media(params),
            "error": raw[:500],
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "status": "facebook_photo_post_request_failed",
            "post_kind": "photo",
            "selected_media": _facebook_selected_media(params),
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
        }, 502


def _post_to_facebook_page_multi_photo(params, policy, environ=None):
    source = environ if environ is not None else os.environ
    page_id = _clean_text(source.get(FACEBOOK_PAGE_ID_ENV))
    token = _clean_text(source.get(FACEBOOK_PAGE_ACCESS_TOKEN_ENV))
    version = _clean_text(source.get(FACEBOOK_GRAPH_VERSION_ENV)) or "v23.0"
    if not page_id or not token:
        return {"success": False, "status": "facebook_page_credentials_missing"}, 503
    media_ids = []
    for asset in params.get("selected_assets", []):
        signed, signed_status = _signed_supabase_media_url(params, environ=source, asset=asset)
        if signed_status >= 400:
            return {**signed, "status": "facebook_multi_photo_sign_failed", "uploaded_media_ids": media_ids}, signed_status
        endpoint = f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/{urllib_parse.quote(page_id, safe='')}/photos"
        body = urllib_parse.urlencode({
            "url": signed.get("signed_url", ""),
            "published": "false",
            "access_token": token,
        }).encode("utf-8")
        result, status = _facebook_form_request(endpoint, body, "facebook_multi_photo_upload_failed", timeout=35)
        if status >= 400 or not result.get("id"):
            return {**result, "uploaded_media_ids": media_ids}, status
        media_ids.append(str(result["id"]))
    endpoint = f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/{urllib_parse.quote(page_id, safe='')}/feed"
    fields = {
        "message": params.get("exact_text", ""),
        "access_token": token,
    }
    for index, media_id in enumerate(media_ids):
        fields[f"attached_media[{index}]"] = json.dumps({"media_fbid": media_id})
    result, status = _facebook_form_request(
        endpoint,
        urllib_parse.urlencode(fields).encode("utf-8"),
        "facebook_multi_photo_post_failed",
        timeout=35,
    )
    return {
        **result,
        "post_kind": "multi_photo",
        "uploaded_media_ids": media_ids,
        "selected_media": _facebook_selected_media(params),
    }, status


def _post_to_facebook_page_video(params, policy, environ=None):
    source = environ if environ is not None else os.environ
    page_id = _clean_text(source.get(FACEBOOK_PAGE_ID_ENV))
    token = _clean_text(source.get(FACEBOOK_PAGE_ACCESS_TOKEN_ENV))
    version = _clean_text(source.get(FACEBOOK_GRAPH_VERSION_ENV)) or "v23.0"
    if not page_id or not token:
        return {"success": False, "status": "facebook_page_credentials_missing"}, 503
    asset = params.get("selected_assets", [{}])[0]
    signed, signed_status = _signed_supabase_media_url(params, environ=source, asset=asset)
    if signed_status >= 400:
        return signed, signed_status
    endpoint = f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/{urllib_parse.quote(page_id, safe='')}/videos"
    body = urllib_parse.urlencode({
        "file_url": signed.get("signed_url", ""),
        "description": params.get("exact_text", ""),
        "access_token": token,
    }).encode("utf-8")
    result, status = _facebook_form_request(endpoint, body, "facebook_video_post_failed", timeout=60)
    return {**result, "post_kind": "video", "selected_media": _facebook_selected_media(params)}, status


def _facebook_form_request(endpoint, body, failure_status, timeout=35):
    req = urllib_request.Request(endpoint, data=body, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8") or "{}")
            return {"success": True, **payload}, response.status
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {"success": False, "status": failure_status, "http_status": exc.code, "error": raw[:500]}, exc.code
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"success": False, "status": failure_status, "error_type": exc.__class__.__name__, "error": str(exc)[:240]}, 502


def _signed_supabase_media_url(params, environ=None, asset=None):
    source = environ if environ is not None else os.environ
    url = _clean_text(source.get(SUPABASE_URL_ENV)).rstrip("/")
    key = _clean_text(source.get(SUPABASE_SERVICE_ROLE_KEY_ENV))
    asset = asset if isinstance(asset, dict) else params.get("selected_asset") if isinstance(params.get("selected_asset"), dict) else {}
    bucket = _clean_text(asset.get("storage_bucket"))
    storage_path = str(asset.get("storage_path") or "").strip().replace("\\", "/")
    if not url or not key:
        return {"success": False, "status": "supabase_storage_not_configured_for_facebook_image"}, 503
    if not bucket or not storage_path:
        return {"success": False, "status": "selected_image_asset_storage_missing"}, 400
    endpoint = f"{url}/storage/v1/object/sign/{urllib_parse.quote(bucket, safe='')}/{urllib_parse.quote(storage_path, safe='/')}"
    body = json.dumps({"expiresIn": 3600}).encode("utf-8")
    req = urllib_request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw or "{}")
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status": "supabase_signed_url_failed",
            "http_status": exc.code,
            "error": raw[:500],
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "status": "supabase_signed_url_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
        }, 503
    signed = payload.get("signedURL") or payload.get("signedUrl") or payload.get("signed_url") or ""
    if signed and signed.startswith("/"):
        signed = f"{url}{signed}"
    return {
        "success": bool(signed),
        "status": "supabase_signed_url_created" if signed else "supabase_signed_url_missing",
        "signed_url": signed,
        "selected_media": _facebook_selected_media(params),
    }, 200 if signed else 502


def _record_facebook_post_execution_event(params, database_url=None):
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _facebook_post_unavailable("not_configured", False), 503
    try:
        import psycopg
    except ImportError:
        return _facebook_post_unavailable("dependency_missing", True), 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.beacon_facebook_post_execution_events (
                        execution_event_id, mode, publish_packet_id, channel, exact_text,
                        owner_confirmation, execution_status, facebook_post_id,
                        facebook_response_json, records_evidence,
                        owner_exact_confirmation_required, sends_customer_message,
                        posts_publicly, calls_chatwoot, calls_meta, calls_n8n,
                        boosts_post, spends_money, creates_quote, creates_invoice,
                        creates_order, changes_stock, reserves_stock, dispatch_enabled,
                        changes_runtime_now, changes_prompt_now, physical_controls_enabled,
                        customer_public_output_enabled, writes_farm_data, recorded_by
                    )
                    values (
                        %(execution_event_id)s, %(mode)s, %(publish_packet_id)s,
                        %(channel)s, %(exact_text)s, %(owner_confirmation)s,
                        %(execution_status)s, %(facebook_post_id)s,
                        %(facebook_response_json)s::jsonb, true, true, false,
                        true, false, true, false, false, false, false, false,
                        false, false, false, false, false, false, false,
                        true, false, %(recorded_by)s
                    )
                    on conflict (execution_event_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_facebook_post_execution_write_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "execution_event": _public_facebook_post_event(params),
            **_facebook_execution_authority(False),
        }, 500
    return {
        "success": True,
        "configured": True,
        "status": "beacon_facebook_post_execution_recorded" if created_count else "beacon_facebook_post_execution_already_recorded",
        "created_count": created_count,
        "execution_event_id": params["execution_event_id"],
        "execution_event": _public_facebook_post_event(params),
        **_facebook_execution_authority(False),
    }, 201 if created_count else 200


def _public_facebook_post_event(params):
    return {
        "execution_event_id": params.get("execution_event_id", ""),
        "mode": params.get("mode", "beacon_facebook_page_post_execution_gate"),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "exact_text": params.get("exact_text", ""),
        "owner_confirmation": params.get("owner_confirmation", ""),
        "execution_status": params.get("execution_status", ""),
        "facebook_post_id": params.get("facebook_post_id", ""),
        "facebook_response": _loads(params.get("facebook_response_json"), {}),
        "post_kind": params.get("post_kind", "feed"),
        "selected_media": _loads(params.get("selected_media_json"), {}),
        **_facebook_execution_authority(params.get("execution_status") == "facebook_page_post_sent"),
    }


def _facebook_post_row_to_event(row):
    return {
        "execution_event_id": row[0],
        "mode": "beacon_facebook_page_post_execution_gate",
        "publish_packet_id": row[1],
        "channel": row[2],
        "exact_text": row[3],
        "owner_confirmation": row[4],
        "execution_status": row[5],
        "facebook_post_id": row[6],
        "facebook_response": row[7] or {},
        "post_kind": (row[7] or {}).get("post_kind", "feed") if isinstance(row[7], dict) else "feed",
        "selected_media": (row[7] or {}).get("selected_media", {}) if isinstance(row[7], dict) else {},
        "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8] or ""),
        **_facebook_execution_authority(row[5] == "facebook_page_post_sent"),
    }


def _facebook_post_execution_id(params):
    seed = {
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:18].upper()
    return f"BEACON-FB-POST-{digest}"


def _facebook_post_unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "beacon_facebook_page_post_execution_gate",
        "execution_events": [],
        **_facebook_execution_authority(False),
    }


def _facebook_selected_media(params):
    assets = params.get("selected_assets") if isinstance(params.get("selected_assets"), list) else []
    assets = [asset for asset in assets if isinstance(asset, dict)]
    if not assets:
        asset = params.get("selected_asset") if isinstance(params.get("selected_asset"), dict) else {}
        if asset:
            assets = [asset]
    if not assets and not params.get("asset_id"):
        return {}
    selected = [{
        "asset_id": asset.get("asset_id", ""),
        "title": asset.get("title", ""),
        "media_type": asset.get("media_type", ""),
        "mime_type": asset.get("mime_type", ""),
        "storage_bucket": asset.get("storage_bucket", ""),
        "storage_path": asset.get("storage_path", ""),
        "privacy_risk": asset.get("privacy_risk", ""),
        "quality_score": asset.get("quality_score"),
        "public_use_approved": bool(asset.get("effective_public_use_approved") or asset.get("public_use_approved")),
    } for asset in assets]
    if len(selected) == 1:
        return selected[0]
    return {"asset_count": len(selected), "post_kind": params.get("post_kind", ""), "assets": selected}


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_money(value, default=0):
    try:
        return round(max(0, float(value)), 2)
    except (TypeError, ValueError):
        return default


def _cost(spend, count):
    if not count:
        return None
    return round(float(spend or 0) / int(count), 2)


def _loads(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _all_draft_texts(packet):
    drafts = []
    for group in ("channel_drafts", "story_updates"):
        for draft in packet.get(group, []):
            drafts.append({"id": draft.get("id", ""), "text": draft.get("text", "")})
    return drafts


def _has_preorder_signal(text):
    return "preorder" in text or "pre-book" in text or "pre booked" in text


def _has_forbidden_promise(text):
    forbidden = [
        "available now",
        "order confirmed",
        "booking confirmed",
        "guaranteed",
        "deposit confirmed",
        "payment confirmed",
        "slaughter booked",
        "butcher booked",
        "free delivery",
        "final price",
        "fixed delivery date",
    ]
    return any(term in text for term in forbidden)


def _has_live_stock_direct_sales_wording(text):
    clean = str(text or "").lower()
    return any(re.search(rf"(?<!\w){re.escape(term)}(?!\w)", clean) for term in LIVE_STOCK_DIRECT_SALES_TERMS)


def _clean_text(value):
    return " ".join(str(value or "").strip().split())


def _clean_caption_text(value, limit=2200):
    lines = [" ".join(line.split()) for line in str(value or "").replace("\x00", " ").splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()[:limit]
