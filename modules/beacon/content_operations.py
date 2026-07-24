"""Evidence-first Beacon recommendation and owner-review packet orchestration."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

from modules.beacon.media_library import list_beacon_media_assets
from modules.beacon.opportunity_scanner import build_beacon_opportunity_cards
from modules.sales.beacon_campaign import (
    list_beacon_campaign_performance_events,
    list_beacon_manual_post_evidence,
)


MODE = "beacon_content_recommendation_owner_review_only"
AUTHORITY = {
    "posts_publicly": False,
    "sends_customer_messages": False,
    "calls_meta": False,
    "creates_ads": False,
    "boosts_posts": False,
    "spends_money": False,
    "creates_orders": False,
    "reserves_stock": False,
    "changes_stock": False,
    "writes_farm_data": False,
    "owner_exact_packet_approval_required": True,
}
VERIFIED_STATUSES = {"verified", "owner_confirmed", "canonical_read"}


def gather_beacon_content_evidence(*, database_url=None, now=None, allocation=None,
                                   live_intakes=None, meat_leads=None,
                                   opportunity_result=None):
    """Run existing read paths and return their availability separately."""
    history, history_status = list_beacon_manual_post_evidence(
        limit=100, database_url=database_url
    )
    performance, performance_status = list_beacon_campaign_performance_events(
        limit=100, database_url=database_url
    )
    media, media_status = list_beacon_media_assets(
        limit=100, database_url=database_url
    )
    opportunities = (
        opportunity_result
        if isinstance(opportunity_result, dict)
        else build_beacon_opportunity_cards(
            allocation=allocation,
            live_intakes=live_intakes,
            meat_leads=meat_leads,
            now=now,
        )
    )
    return {
        "mode": MODE,
        "gathered_at": _iso(now) or datetime.now(timezone.utc).isoformat(),
        "historical_posts": _source_result(
            history_status, history, "manual_post_events", "manual_posts"
        ),
        "performance_events": _source_result(
            performance_status, performance, "performance_events", "performance_events"
        ),
        "media_assets": _source_result(
            media_status, media, "assets", "media_assets"
        ),
        "opportunities": {
            "availability": "usable" if opportunities.get("success") else "inaccessible",
            "records": opportunities.get("cards", []),
            "source": "beacon_opportunity_scanner",
            "observed_at": opportunities.get("generated_at", ""),
        },
        "authority": deepcopy(AUTHORITY),
    }


def build_beacon_content_candidate(evidence=None, *, current_facts=None, now=None,
                                   max_ideas=3):
    """Rank bounded ideas and prepare one exact, non-executing review packet."""
    evidence = evidence if isinstance(evidence, dict) else {}
    generated_at = _iso(now) or datetime.now(timezone.utc).isoformat()
    history = _records(evidence.get("historical_posts"))
    performance = _records(evidence.get("performance_events"))
    opportunities = _records(evidence.get("opportunities"))
    assets = _records(evidence.get("media_assets"))
    facts, rejected_facts = _verified_facts(current_facts)
    approved_assets = [asset for asset in assets if _approved_asset(asset)]
    history_quality = _history_quality(history, performance)

    ideas = _ranked_ideas(
        history=history,
        opportunities=opportunities,
        facts=facts,
        approved_assets=approved_assets,
        history_quality=history_quality,
        generated_at=generated_at,
    )[:max(1, min(int(max_ideas or 3), 5))]
    selected = ideas[0]
    selected_asset = approved_assets[0] if approved_assets else None
    exact_copy = _draft_copy(selected, facts)
    packet_seed = json.dumps(
        {
            "idea": selected["idea_id"],
            "copy": exact_copy,
            "asset": (selected_asset or {}).get("asset_id", ""),
            "generated_at": generated_at,
        },
        sort_keys=True,
    )
    packet_id = "BEACON-REVIEW-" + sha256(packet_seed.encode("utf-8")).hexdigest()[:18].upper()
    media = (
        {
            "status": "approved_media_selected",
            "asset_id": selected_asset.get("asset_id", ""),
            "title": selected_asset.get("title", ""),
            "media_type": selected_asset.get("media_type", ""),
            "content_sha256": selected_asset.get("content_sha256", ""),
            "content_hash_provenance": selected_asset.get("content_hash_provenance", ""),
            "approval_status": selected_asset.get("effective_approval_status")
            or selected_asset.get("approval_status", ""),
            "public_use_approved": True,
        }
        if selected_asset
        else {
            "status": "media_gap",
            "reason": "No integrity-verified asset with effective approved-public-use status was found.",
            "required_next_step": "Owner reviews and approves one hash-verified livestock asset.",
        }
    )
    return {
        "success": True,
        "status": "owner_review_packet_ready_with_media_gap"
        if not selected_asset else "owner_review_packet_ready",
        "mode": MODE,
        "generated_at": generated_at,
        "evidence_quality": history_quality,
        "rejected_current_facts": rejected_facts,
        "ranked_ideas": ideas,
        "owner_review_packet": {
            "packet_id": packet_id,
            "review_status": "awaiting_owner_review",
            "idea_id": selected["idea_id"],
            "channel": "Facebook Page",
            "audience": "People interested in responsible local livestock and farm life",
            "timing": {
                "recommendation": "Use the next owner-selected Facebook publishing window.",
                "rationale": "No verified hour-by-hour performance evidence is available; timing is intentionally not presented as optimized.",
            },
            "draft_copy": exact_copy,
            "call_to_action": "Follow Amadeus Farm for more livestock and farm-life updates.",
            "measurable_objective": {
                "metric": "qualified inbound livestock enquiries",
                "measurement_window": "7 days after an owner-approved post",
                "target": "owner_sets_target_before_publication",
            },
            "media": media,
            "recommendation_reason": selected["why"],
            "supporting_evidence": selected["supporting_evidence"],
            "fact_constraints": {
                "verified_fact_ids_used": [fact["fact_id"] for fact in facts],
                "stock_claimed": False,
                "price_claimed": False,
                "availability_claimed": False,
                "location_claimed": False,
                "customer_claim_claimed": False,
                "performance_result_claimed": False,
            },
            "next_gate": "owner_approves_the_exact_final_copy_media_channel_and_timing_through_the_existing_protected_publish_rail",
            "authority": deepcopy(AUTHORITY),
        },
        "learning_capture": {
            "mode": "append_only_evidence_events",
            "writes_performed": False,
            "accepted_inputs": [
                "manual_post_evidence",
                "campaign_performance_event_with_metric_provenance",
                "owner_correction_event",
            ],
            "rule": "Unknown, inferred, stale, or unreferenced outcomes remain unknown and cannot support positive performance claims.",
        },
        "authority": deepcopy(AUTHORITY),
    }


def _ranked_ideas(*, history, opportunities, facts, approved_assets,
                  history_quality, generated_at):
    source_dates = sorted(
        {
            value
            for row in history
            for value in (str(row.get("posted_at") or ""),)
            if value
        }
    )
    history_ref = {
        "source": "beacon_manual_post_events",
        "date_coverage": {
            "from": source_dates[0] if source_dates else "",
            "to": source_dates[-1] if source_dates else "",
        },
        "record_count": len(history),
        "use": "style_and_topic_evidence_only",
    }
    fact_refs = [
        {
            "source": fact["source"],
            "source_reference": fact["source_reference"],
            "observed_at": fact["observed_at"],
            "fact_id": fact["fact_id"],
        }
        for fact in facts
    ]
    usable_opportunities = [
        card for card in opportunities
        if card.get("status") == "ready_for_owner_review"
        and card.get("freshness", {}).get("fresh")
    ]
    common = [history_ref, *fact_refs]
    media_note = (
        "approved provenance-safe livestock media is available"
        if approved_assets else
        "media remains blocked pending owner approval of a hash-verified asset"
    )
    candidates = [
        {
            "idea_id": "livestock_care_story",
            "title": "The care behind the livestock",
            "angle": "A warm, specific farm-life story using only the supplied verified facts.",
            "score": 82 + min(len(facts), 3) * 4 + (4 if approved_assets else 0),
            "why": (
                f"Historical posts provide {len(history)} style/topic examples, but "
                f"{history_quality['performance_evidence_status']}; {media_note}."
            ),
            "supporting_evidence": common,
            "risk_flags": [] if facts else ["no_specific_current_fact_available"],
        },
        {
            "idea_id": "livestock_education",
            "title": "One practical livestock-care insight",
            "angle": "Explain one verified husbandry observation without sales or outcome claims.",
            "score": 76 + min(len(facts), 3) * 3,
            "why": "Educational awareness remains safe when availability and commercial facts are not verified.",
            "supporting_evidence": common,
            "risk_flags": [] if facts else ["no_specific_current_fact_available"],
        },
        {
            "idea_id": "current_livestock_opportunity",
            "title": "Current livestock opportunity",
            "angle": "Prepare demand-aware copy only after current supply, demand, and fulfilment evidence pass.",
            "score": 90 if usable_opportunities else 35,
            "why": (
                "A fresh scanner card supports owner review."
                if usable_opportunities else
                "No fresh ready-for-owner-review livestock opportunity card is available, so sales claims are blocked."
            ),
            "supporting_evidence": [
                *common,
                {
                    "source": "beacon_opportunity_scanner",
                    "observed_at": generated_at,
                    "ready_card_count": len(usable_opportunities),
                },
            ],
            "risk_flags": [] if usable_opportunities else ["current_opportunity_not_proven"],
        },
    ]
    return sorted(candidates, key=lambda item: (-item["score"], item["idea_id"]))


def _draft_copy(idea, facts):
    details = " ".join(fact["statement"].rstrip(".") + "." for fact in facts[:3])
    if details:
        opening = details
    else:
        opening = "A closer look at the everyday care behind the livestock at Amadeus Farm."
    return (
        f"{opening}\n\n"
        "Good livestock stories start with real farm evidence, careful observation, and no shortcuts. "
        "We will share more once each detail and image is ready for public use.\n\n"
        "Follow Amadeus Farm for more livestock and farm-life updates."
    )


def _verified_facts(value):
    accepted = []
    rejected = []
    for index, fact in enumerate(value if isinstance(value, list) else []):
        fact = fact if isinstance(fact, dict) else {}
        missing = [
            key for key in ("statement", "source", "source_reference", "observed_at", "status")
            if not str(fact.get(key) or "").strip()
        ]
        if missing or str(fact.get("status") or "").strip().lower() not in VERIFIED_STATUSES:
            rejected.append({
                "index": index,
                "reason": "missing_provenance" if missing else "fact_not_verified",
                "missing": missing,
            })
            continue
        accepted.append({
            "fact_id": str(fact.get("fact_id") or f"FACT-{index + 1}"),
            "statement": " ".join(str(fact["statement"]).split())[:400],
            "source": str(fact["source"])[:120],
            "source_reference": str(fact["source_reference"])[:240],
            "observed_at": _iso(fact["observed_at"]) or str(fact["observed_at"])[:80],
            "status": str(fact["status"]).lower(),
        })
    return accepted, rejected


def _approved_asset(asset):
    effective = asset.get("effective_public_use_approved")
    if effective is None:
        effective = asset.get("public_use_approved")
    approval = str(
        asset.get("effective_approval_status") or asset.get("approval_status") or ""
    ).lower()
    return (
        bool(effective)
        and approval in {"approved", "approved_public_use"}
        and bool(str(asset.get("content_sha256") or "").strip())
        and asset.get("content_hash_provenance") == "server_computed_on_upload"
    )


def _history_quality(history, performance):
    verified = [
        row for row in performance
        if isinstance(row.get("metric_evidence"), dict)
        and row.get("metric_evidence")
        and row.get("source_reference")
        and row.get("retrieved_at")
    ]
    return {
        "historical_post_count": len(history),
        "performance_event_count": len(performance),
        "verified_performance_event_count": len(verified),
        "performance_evidence_status": (
            "verified performance evidence is available"
            if verified else
            "performance evidence is unavailable or insufficiently normalized"
        ),
    }


def _source_result(status, payload, key, source):
    records = payload.get(key, []) if isinstance(payload, dict) else []
    availability = "usable" if status == 200 else (
        "no_data" if status == 200 and not records else "inaccessible"
    )
    if status == 200 and not records:
        availability = "no_data"
    return {
        "availability": availability,
        "records": records if isinstance(records, list) else [],
        "source": source,
        "read_status": status,
    }


def _records(source):
    if isinstance(source, list):
        return [row for row in source if isinstance(row, dict)]
    if isinstance(source, dict):
        rows = source.get("records", [])
        return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return []


def _iso(value):
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return ""
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()
