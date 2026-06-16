import re

from modules.oom_sakkie.sales_campaign_store import (
    DEFAULT_MEAT_PRICE_BOOK,
    build_meat_pricing_estimate_from_contract,
    get_sales_lead_preorder_contract,
    list_meat_price_book_entries,
)
from modules.pig_weights.pig_weights_service import get_meat_planning_summary


def get_sales_lead_meat_match(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    contract_result, contract_status = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    if contract_status != 200:
        return contract_result, contract_status

    price_result, price_status = list_meat_price_book_entries(limit=100, database_url=database_url)
    if price_status != 200:
        return price_result, price_status

    planning = get_meat_planning_summary()
    if not planning.get("success"):
        return {
            "success": False,
            "status": "meat_planning_unavailable",
            "lead_id": lead_id,
            "planning_status": planning.get("status", ""),
            **_authority_flags(),
        }, 503

    match = build_butcher_meat_match(
        contract_result.get("lead") or {},
        contract_result.get("contract") or {},
        planning.get("pigs") or [],
        price_result.get("price_entries") or DEFAULT_MEAT_PRICE_BOOK,
        payload,
    )
    return {
        "success": True,
        "status": "ok",
        "mode": "butcher_meat_match_recommendation_only",
        "lead_id": lead_id,
        "lead": contract_result.get("lead") or {},
        "contract": contract_result.get("contract") or {},
        "meat_match": match,
        "next_gate": "owner_reviews_match_before_any_reservation_allocation_or_booking",
        **_authority_flags(),
    }, 200


def build_butcher_meat_match(lead, contract, candidates, price_entries=None, payload=None):
    lead = lead if isinstance(lead, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    payload = payload if isinstance(payload, dict) else {}
    price_entries = price_entries if isinstance(price_entries, list) and price_entries else DEFAULT_MEAT_PRICE_BOOK
    criteria = _match_criteria(lead, contract, payload)
    rows = []
    for candidate in candidates if isinstance(candidates, list) else []:
        row = _candidate_match_row(candidate, lead, contract, price_entries, criteria)
        if row:
            rows.append(row)

    rows.sort(key=lambda item: item["score"])
    recommendation = rows[0] if rows else {}
    alternatives = rows[1:3]
    return {
        "agent": "butcher",
        "decision": "recommend" if recommendation else "no_safe_match",
        "criteria": criteria,
        "recommendation": recommendation,
        "alternatives": alternatives,
        "customer_safe_summary": _customer_safe_summary(recommendation, criteria),
        "blocked_actions": [
            "No pig reservation was made.",
            "No stock or allocation record was changed.",
            "No slaughter booking was created.",
            "No deposit request was sent.",
            "Owner review is still required before customer follow-up or reservation.",
        ],
        **_authority_flags(),
    }


def _candidate_match_row(candidate, lead, contract, price_entries, criteria):
    if not isinstance(candidate, dict):
        return {}
    live_weight = _as_float(candidate.get("latest_weight_kg"))
    if live_weight is None:
        return {}
    estimate = build_meat_pricing_estimate_from_contract(
        lead,
        contract,
        price_entries,
        {"selected_pig_live_weight_kg": str(live_weight)},
    )
    yield_estimate = estimate.get("yield_estimate") if isinstance(estimate.get("yield_estimate"), dict) else {}
    midpoint = _as_float(yield_estimate.get("midpoint_packed_kg"))
    total = _as_float(estimate.get("estimated_total"))
    score, reasons = _candidate_score(candidate, live_weight, midpoint, total, criteria)
    return {
        "pig_id": candidate.get("pig_id", ""),
        "tag_number": candidate.get("tag_number", ""),
        "planning_bucket": candidate.get("planning_bucket", ""),
        "latest_weight_kg": live_weight,
        "latest_weight_date": candidate.get("latest_weight_date", ""),
        "meat_window_status": candidate.get("meat_window_status", ""),
        "days_until_meat_ready": candidate.get("days_until_meat_ready"),
        "current_pen_name": candidate.get("current_pen_name", ""),
        "pricing_estimate": estimate,
        "estimated_packed_midpoint_kg": midpoint,
        "estimated_total": total,
        "estimated_total_label": estimate.get("estimated_total_label", ""),
        "score": score,
        "match_reasons": reasons,
    }


def _candidate_score(candidate, live_weight, packed_midpoint, estimated_total, criteria):
    bucket_penalty = {
        "ready_now": 0,
        "next_14_days": 20,
        "next_30_days": 40,
        "future": 80,
        "fallback_abattoir": 120,
    }.get(candidate.get("planning_bucket"), 100)
    score = bucket_penalty
    reasons = [f"{candidate.get('planning_bucket') or 'unknown'} planning bucket"]
    if criteria["preference"] == "heaviest":
        score += max(0, 200 - live_weight)
        reasons.append("heaviest suitable candidate requested")
    if criteria["target_packed_kg"] is not None and packed_midpoint is not None:
        delta = abs(packed_midpoint - criteria["target_packed_kg"])
        score += delta * 8
        reasons.append(f"{delta:.1f}kg away from target packed weight")
    if criteria["budget_amount"] is not None and estimated_total is not None:
        delta = estimated_total - criteria["budget_amount"]
        if delta <= 0:
            score += abs(delta) / 20
            reasons.append("inside stated budget")
        else:
            score += 250 + delta / 10
            reasons.append("above stated budget")
    if criteria["preference"] == "soonest":
        days = candidate.get("days_until_meat_ready")
        score += max(0, int(days)) if isinstance(days, (int, float)) else 100
        reasons.append("soonest availability requested")
    return round(score, 2), reasons


def _match_criteria(lead, contract, payload):
    summary = contract.get("lead_summary") if isinstance(contract.get("lead_summary"), dict) else {}
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    text = " ".join(str(value or "") for value in [
        payload.get("customer_request"),
        payload.get("notes"),
        interest.get("notes"),
        summary.get("customer_notes"),
    ]).lower()
    target_packed_kg = _as_float(payload.get("target_packed_kg")) or _packed_kg_from_text(text)
    budget_amount = _as_float(payload.get("budget_amount")) or _budget_from_text(text)
    preference = str(payload.get("preference") or "").strip().lower()
    if not preference:
        if "heaviest" in text or "biggest" in text or "largest" in text:
            preference = "heaviest"
        elif "soon" in text or "available" in text or "quick" in text:
            preference = "soonest"
        elif target_packed_kg is not None:
            preference = "closest_weight"
        elif budget_amount is not None:
            preference = "budget_fit"
        else:
            preference = "best_ready_fit"
    return {
        "preference": preference,
        "target_packed_kg": target_packed_kg,
        "budget_amount": budget_amount,
        "product": summary.get("product") or interest.get("product") or interest.get("product_type") or "",
        "cut_set": summary.get("cut_set") or interest.get("cut_set") or "",
        "location": summary.get("location") or interest.get("location") or "",
    }


def _packed_kg_from_text(text):
    match = re.search(r"\b(\d+(?:[.,]\d+)?)\s*kg\b", text or "", re.I)
    return _as_float(match.group(1)) if match else None


def _budget_from_text(text):
    match = re.search(r"(?:r|zar|budget\s*(?:is|of)?\s*)\s*(\d+(?:[.,]\d+)?)", text or "", re.I)
    return _as_float(match.group(1)) if match else None


def _customer_safe_summary(recommendation, criteria):
    if not recommendation:
        return "I do not have a safe pig match yet. The farm needs to review availability before promising a size or booking."
    tag = recommendation.get("tag_number") or recommendation.get("pig_id") or "the best current candidate"
    weight = recommendation.get("pricing_estimate", {}).get("yield_estimate", {}).get("display", "an estimated packed weight")
    total = recommendation.get("estimated_total_label") or "an estimated total"
    return (
        f"The closest current match is {tag}, with {weight} and {total}. "
        "This is an estimate only; the farm must confirm availability and final packed weight before booking or payment."
    )


def _as_float(value):
    if value is None or value == "":
        return None
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _authority_flags():
    return {
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "writes_farm_data": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }
