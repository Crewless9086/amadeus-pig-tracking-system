import os
import re

from modules.oom_sakkie.sales_campaign_store import (
    DEFAULT_MEAT_PRICE_BOOK,
    build_meat_pricing_estimate_from_contract,
    get_sales_lead_preorder_contract,
    list_meat_price_book_entries,
)
from modules.pig_weights.pig_weights_service import get_meat_planning_summary
from services.database_service import DATABASE_URL_ENV


ACTIVE_RESERVATION_STATUSES = {
    "half_reserved_pending_pair",
    "full_carcass_committed",
    "deposit_pending",
    "ready_for_slaughter_booking",
}


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

    active_reservations = _fetch_active_carcass_reservations(
        [item.get("pig_id") for item in planning.get("pigs") or []],
        database_url=database_url,
    )
    if active_reservations is None:
        return {
            "success": False,
            "status": "carcass_reservation_source_unavailable",
            "lead_id": lead_id,
            **_authority_flags(),
        }, 503
    match = build_butcher_meat_match(
        contract_result.get("lead") or {},
        contract_result.get("contract") or {},
        planning.get("pigs") or [],
        price_result.get("price_entries") or DEFAULT_MEAT_PRICE_BOOK,
        {"active_reservations": active_reservations, **payload},
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
    reservations_by_pig = _reservations_by_pig(payload.get("active_reservations") or [])
    rows = []
    for candidate in candidates if isinstance(candidates, list) else []:
        row = _candidate_match_row(candidate, lead, contract, price_entries, criteria, reservations_by_pig)
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


def _candidate_match_row(candidate, lead, contract, price_entries, criteria, reservations_by_pig=None):
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
    reservation_state = _carcass_reservation_state(candidate.get("pig_id"), reservations_by_pig or {})
    if reservation_state.get("blocked"):
        return {}
    score, reasons = _candidate_score(candidate, live_weight, midpoint, total, criteria, reservation_state)
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
        "carcass_reservation_state": reservation_state,
    }


def _candidate_score(candidate, live_weight, packed_midpoint, estimated_total, criteria, reservation_state=None):
    reservation_state = reservation_state if isinstance(reservation_state, dict) else {}
    bucket_penalty = {
        "ready_now": 0,
        "next_14_days": 20,
        "next_30_days": 40,
        "future": 80,
        "fallback_abattoir": 120,
    }.get(candidate.get("planning_bucket"), 100)
    score = bucket_penalty
    reasons = [f"{candidate.get('planning_bucket') or 'unknown'} planning bucket"]
    if criteria.get("product_type") == "half_carcass" and reservation_state.get("open_half_available"):
        score -= 75
        reasons.append("existing half reserved; matching open half is preferred")
    elif criteria.get("product_type") == "half_carcass" and reservation_state.get("active_reservation_count"):
        score += 50
        reasons.append("pig already has active carcass reservation")
    elif criteria.get("product_type") in {"full_carcass", "custom_cut"} and reservation_state.get("active_reservation_count"):
        score += 300
        reasons.append("full/custom order should avoid pigs with an active half reservation")
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
        "product_type": _product_type(summary.get("product") or interest.get("product_type") or interest.get("product") or ""),
        "cut_set": summary.get("cut_set") or interest.get("cut_set") or "",
        "location": summary.get("location") or interest.get("location") or "",
    }


def _product_type(value):
    text = str(value or "").lower()
    if "half" in text:
        return "half_carcass"
    if "full" in text or "whole" in text:
        return "full_carcass"
    if "custom" in text:
        return "custom_cut"
    return ""


def _fetch_active_carcass_reservations(pig_ids, database_url=None):
    pig_ids = sorted({str(item or "").strip() for item in pig_ids or [] if str(item or "").strip()})
    if not pig_ids:
        return []
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return None
    try:
        import psycopg
    except ImportError:
        return None
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select reservation_id, lead_id, pig_id, tag_number, product_type,
                           carcass_side, cut_set, status, created_at
                    from public.oom_sakkie_meat_carcass_reservations
                    where pig_id = any(%(pig_ids)s)
                      and status in ('half_reserved_pending_pair', 'full_carcass_committed', 'deposit_pending', 'ready_for_slaughter_booking')
                    order by created_at asc
                    """,
                    {"pig_ids": pig_ids},
                )
                rows = cursor.fetchall()
    except Exception:
        return []
    return [_reservation_row(row) for row in rows]


def _reservation_row(row):
    return {
        "reservation_id": row[0] or "",
        "lead_id": row[1] or "",
        "pig_id": row[2] or "",
        "tag_number": row[3] or "",
        "product_type": row[4] or "",
        "carcass_side": row[5] or "",
        "cut_set": row[6] or "",
        "status": row[7] or "",
        "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8] or ""),
    }


def _reservations_by_pig(reservations):
    by_pig = {}
    for item in reservations if isinstance(reservations, list) else []:
        if not isinstance(item, dict):
            continue
        if item.get("status") not in ACTIVE_RESERVATION_STATUSES:
            continue
        pig_id = str(item.get("pig_id") or "").strip()
        if not pig_id:
            continue
        by_pig.setdefault(pig_id, []).append(item)
    return by_pig


def _carcass_reservation_state(pig_id, reservations_by_pig):
    active = reservations_by_pig.get(str(pig_id or "").strip(), [])
    sides = {item.get("carcass_side") for item in active}
    full_committed = "full" in sides or {"half_a", "half_b"}.issubset(sides)
    open_half_available = bool(len(sides.intersection({"half_a", "half_b"})) == 1 and not full_committed)
    open_side = ""
    if open_half_available:
        open_side = "half_b" if "half_a" in sides else "half_a"
    return {
        "active_reservation_count": len(active),
        "reserved_sides": sorted(side for side in sides if side),
        "open_half_available": open_half_available,
        "open_side": open_side,
        "full_carcass_committed": full_committed,
        "blocked": full_committed,
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
