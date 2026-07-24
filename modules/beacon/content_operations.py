"""Evidence-first Beacon recommendation and owner-review packet orchestration."""

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
import re

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
ACCEPTED_METRIC_STATUSES = {"verified", "owner_correction"}
REJECTED_METRIC_SOURCES = {
    "legacy", "legacy_unlabelled", "inferred", "unavailable", "unknown", "malformed",
}
CLAIM_TYPES = {
    "husbandry_observation",
    "stock",
    "price",
    "availability",
    "location",
    "customer_claim",
    "performance_result",
}
COMMERCIAL_CLAIM_TYPES = {
    "stock", "price", "availability", "location", "customer_claim", "performance_result",
}
AUTHORITATIVE_FACT_ADAPTERS = {
    "canonical_farm_observation": {
        "adapter_id": "farm_observation_v1",
        "allowed_claim_types": {"husbandry_observation"},
        "statement_mode": "bounded_observation_text",
    },
    "canonical_sales_offer": {
        "adapter_id": "sales_offer_v1",
        "allowed_claim_types": {"stock", "price", "availability", "location"},
        "statement_mode": "structured_sales_offer",
    },
    "canonical_customer_feedback": {
        "adapter_id": "customer_feedback_v1",
        "allowed_claim_types": {"customer_claim"},
        "statement_mode": "structured_customer_claim",
    },
    "beacon_campaign_performance": {
        "adapter_id": "campaign_performance_v1",
        "allowed_claim_types": {"performance_result"},
        "statement_mode": "structured_performance_result",
    },
}


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
            "availability": (
                "inaccessible"
                if any(
                    item.get("status") == "timed_out"
                    for item in opportunities.get("dependency_diagnostics", {}).values()
                )
                else "usable" if opportunities.get("success") else "inaccessible"
            ),
            "records": opportunities.get("cards", []),
            "source": "beacon_opportunity_scanner",
            "observed_at": opportunities.get("generated_at", ""),
            "dependency_diagnostics": opportunities.get("dependency_diagnostics", {}),
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
    exact_copy = _draft_copy(selected, facts, selected_asset)
    fact_constraints = _fact_constraints(facts)
    packet_evidence = list(selected["supporting_evidence"])
    if selected_asset:
        packet_evidence.append({
            "source": "beacon_media_assets",
            "source_reference": selected_asset.get("asset_id", ""),
            "observed_at": selected_asset.get("created_at", ""),
            "approval_status": selected_asset.get("effective_approval_status")
            or selected_asset.get("approval_status", ""),
            "content_hash_provenance": selected_asset.get("content_hash_provenance", ""),
            "use": "approved_visual_content_evidence",
        })
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
            "call_to_action": (
                "Message Amadeus Farm with the livestock type, age or weight range, "
                "sex, quantity, and timing you are looking for."
            ),
            "measurable_objective": {
                "metric": "qualified inbound livestock enquiries",
                "measurement_window": "7 days after an owner-approved post",
                "target": "owner_sets_target_before_publication",
            },
            "media": media,
            "recommendation_reason": selected["why"],
            "supporting_evidence": packet_evidence,
            "fact_constraints": fact_constraints,
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
        "capability_status": {
            "evidence_sources_read": {
                name: evidence.get(name, {}).get("availability", "unknown")
                for name in (
                    "historical_posts",
                    "performance_events",
                    "media_assets",
                    "opportunities",
                )
            },
            "packet_generated": True,
            "current_opportunity_read": (
                evidence.get("opportunities", {}).get("availability") == "usable"
            ),
            "writes_performed": False,
            "publishing_performed": False,
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


def _draft_copy(idea, facts, selected_asset=None):
    details = " ".join(fact["statement"].rstrip(".") + "." for fact in facts[:3])
    if details:
        opening = details
    elif selected_asset and selected_asset.get("media_type") == "video":
        opening = "A closer look at the piglets in this approved farm video."
    elif selected_asset:
        opening = "A closer look at the livestock in this approved farm image."
    else:
        opening = "A closer look at the everyday care behind the livestock at Amadeus Farm."
    return (
        f"{opening}\n\n"
        "Good livestock decisions start with real farm evidence and careful observation. "
        "If you are planning livestock needs, message Amadeus Farm with the type, age or weight range, "
        "sex, quantity, and timing you are looking for. We will check current records before confirming "
        "any availability, price, or collection details."
    )


def _verified_facts(value):
    accepted = []
    rejected = []
    for index, fact in enumerate(value if isinstance(value, list) else []):
        fact = fact if isinstance(fact, dict) else {}
        missing = [
            key for key in (
                "statement", "source", "source_reference", "observed_at", "status",
                "claim_types",
            )
            if not str(fact.get(key) or "").strip()
        ]
        observed_at = _iso(fact.get("observed_at"))
        source = str(fact.get("source") or "").strip()
        adapter_id = str(fact.get("adapter_id") or "").strip()
        claim_types = fact.get("claim_types")
        normalized_claim_types = sorted({
            str(item or "").strip().lower()
            for item in claim_types if str(item or "").strip()
        }) if isinstance(claim_types, list) else []
        invalid_claim_types = sorted(set(normalized_claim_types) - CLAIM_TYPES)
        status = str(fact.get("status") or "").strip().lower()
        reason = ""
        if missing:
            reason = "missing_provenance"
        elif status not in VERIFIED_STATUSES:
            reason = "fact_not_verified"
        elif not observed_at:
            reason = "invalid_observed_at"
        source_contract = AUTHORITATIVE_FACT_ADAPTERS.get(source)
        if not reason and (
            source_contract is None
            or adapter_id != source_contract["adapter_id"]
        ):
            reason = "unaccepted_fact_source_adapter"
        if not reason and (not normalized_claim_types or invalid_claim_types):
            reason = "invalid_claim_types"
        if not reason and not set(normalized_claim_types).issubset(source_contract["allowed_claim_types"]):
            reason = "claim_type_not_authorized_for_source"
        statement = " ".join(str(fact.get("statement") or "").split())[:400]
        structured_values = fact.get("structured_values")
        if not reason and source_contract["statement_mode"] == "bounded_observation_text":
            undeclared = _statement_commercial_claim_types(statement) - set(normalized_claim_types)
            if undeclared:
                reason = "statement_claim_type_mismatch"
        if not reason and source_contract["statement_mode"] != "bounded_observation_text":
            statement, structured_reason = _structured_fact_statement(
                source_contract["statement_mode"],
                normalized_claim_types,
                structured_values,
            )
            if structured_reason:
                reason = structured_reason
        if reason:
            rejected.append({
                "index": index,
                "reason": reason,
                "missing": missing,
                "invalid_claim_types": invalid_claim_types,
                "source": source,
                "adapter_id": adapter_id,
            })
            continue
        accepted.append({
            "fact_id": str(fact.get("fact_id") or f"FACT-{index + 1}"),
            "statement": statement,
            "source": source[:120],
            "adapter_id": adapter_id[:120],
            "source_reference": str(fact["source_reference"])[:240],
            "observed_at": observed_at,
            "status": status,
            "claim_types": normalized_claim_types,
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
    evaluations = [_performance_evidence_evaluation(row) for row in performance]
    verified = [evaluation for evaluation in evaluations if evaluation["usable"]]
    return {
        "historical_post_count": len(history),
        "performance_event_count": len(performance),
        "verified_performance_event_count": len(verified),
        "unusable_performance_event_count": len(performance) - len(verified),
        "performance_evidence_evaluations": evaluations,
        "performance_evidence_status": (
            "verified performance evidence is available"
            if verified else
            "performance evidence is unavailable or insufficiently normalized"
        ),
    }


def _performance_evidence_evaluation(row):
    event_id = str(row.get("performance_event_id") or "")
    evidence = row.get("metric_evidence")
    if not isinstance(evidence, dict) or not evidence:
        return {
            "performance_event_id": event_id,
            "usable": False,
            "usable_metric_names": [],
            "reasons": ["metric_evidence_missing_or_malformed"],
        }
    usable = []
    reasons = []
    for name, metric in sorted(evidence.items()):
        prefix = f"{name}:"
        if not isinstance(metric, dict):
            reasons.append(prefix + "metric_evidence_malformed")
            continue
        status = str(metric.get("status") or "").strip().lower()
        source = str(metric.get("source") or "").strip()
        reference = str(metric.get("source_reference") or "").strip()
        retrieved_at = _iso(metric.get("retrieved_at"))
        metric_reasons = []
        if status not in ACCEPTED_METRIC_STATUSES:
            metric_reasons.append("status_unaccepted")
        if not source or source.lower() in REJECTED_METRIC_SOURCES:
            metric_reasons.append("source_unaccepted")
        if not reference:
            metric_reasons.append("source_reference_missing")
        if not retrieved_at:
            metric_reasons.append("retrieved_at_invalid")
        if metric.get("value") is None:
            metric_reasons.append("value_missing")
        if metric_reasons:
            reasons.extend(prefix + reason for reason in metric_reasons)
        else:
            usable.append(name)
    # An event is usable for ranking only when every supplied metric is independently usable.
    return {
        "performance_event_id": event_id,
        "usable": bool(usable) and not reasons,
        "usable_metric_names": usable if not reasons else [],
        "reasons": sorted(set(reasons)),
    }


def _statement_commercial_claim_types(statement):
    text = str(statement or "")
    lowered = text.lower()
    signals = set()
    if re.search(r"(?:\bzar\b|\br\s*\d|\bprice\b|\bcosts?\b|\bper\s+(?:pig|animal|head|kg)\b)", lowered):
        signals.add("price")
    if re.search(r"\b(?:in stock|stock of|stock level|we have \d+|quantity available)\b", lowered):
        signals.add("stock")
    if re.search(r"\b(?:available|availability|ready to collect|ready now)\b", lowered):
        signals.add("availability")
    if re.search(r"\b(?:customer|buyer|client)\s+(?:said|reported|confirmed|reviewed)\b", lowered):
        signals.add("customer_claim")
    if re.search(r"\b(?:reach|impressions|conversion|performed|qualified leads?|sales result)\b", lowered):
        signals.add("performance_result")
    if re.search(r"\b(?:located|location|collection point)\b", lowered) or re.search(
        r"\b(?:in|near|from)\s+[A-Z][A-Za-z-]+", text
    ):
        signals.add("location")
    return signals


def _structured_fact_statement(mode, claim_types, values):
    if not isinstance(values, dict):
        return "", "structured_values_required"
    if mode == "structured_sales_offer":
        subject = _bounded_value(values.get("subject"), 80)
        if not subject:
            return "", "structured_subject_required"
        parts = [subject]
        if "stock" in claim_types:
            quantity = values.get("quantity")
            if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 0:
                return "", "structured_stock_quantity_invalid"
            parts[0] = f"{quantity} {subject}"
        if "availability" in claim_types:
            availability = str(values.get("availability_status") or "").strip().lower()
            if availability not in {"available_for_owner_review", "not_available"}:
                return "", "structured_availability_status_invalid"
            parts.append(
                "are available subject to current-record confirmation"
                if availability == "available_for_owner_review"
                else "are not currently available"
            )
        if "price" in claim_types:
            amount = values.get("price_amount")
            currency = str(values.get("currency") or "").strip().upper()
            if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount < 0 or currency != "ZAR":
                return "", "structured_price_invalid"
            parts.append(f"at ZAR {amount:,.2f}")
        if "location" in claim_types:
            location = _bounded_value(values.get("location"), 80)
            if not location:
                return "", "structured_location_required"
            parts.append(f"in {location}")
        return " ".join(parts) + ".", ""
    if mode == "structured_customer_claim":
        summary = _bounded_value(values.get("owner_verified_summary"), 220)
        if not summary:
            return "", "structured_customer_summary_required"
        return f"Owner-verified customer feedback: {summary}.", ""
    if mode == "structured_performance_result":
        metric = _bounded_value(values.get("metric_name"), 80)
        value = values.get("metric_value")
        window = _bounded_value(values.get("measurement_window"), 80)
        if not metric or value is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not window:
            return "", "structured_performance_values_invalid"
        return f"Verified campaign result: {metric} was {value:g} during {window}.", ""
    return "", "unsupported_fact_statement_mode"


def _bounded_value(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _fact_constraints(facts):
    by_type = {claim_type: [] for claim_type in COMMERCIAL_CLAIM_TYPES}
    for fact in facts:
        for claim_type in fact.get("claim_types", []):
            if claim_type in by_type:
                by_type[claim_type].append({
                    "fact_id": fact["fact_id"],
                    "source": fact["source"],
                    "source_reference": fact["source_reference"],
                    "observed_at": fact["observed_at"],
                    "status": fact["status"],
                })
    return {
        "verified_fact_ids_used": [fact["fact_id"] for fact in facts],
        "claim_provenance": by_type,
        **{
            f"{claim_type}_claimed": bool(by_type[claim_type])
            for claim_type in COMMERCIAL_CLAIM_TYPES
        },
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
