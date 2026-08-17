"""Pure, zero-write livestock request and HERDMASTER recommendation preview."""

from datetime import datetime, timezone

CONTRACT_VERSION = "livestock_quote_preview_v1"
WEIGHT_RANGES = {"2_to_4_Kg": (2, 4), "5_to_6_Kg": (5, 6), "7_to_9_Kg": (7, 9), "10_to_14_Kg": (10, 14), "15_to_19_Kg": (15, 19), "20_to_24_Kg": (20, 24), "25_to_29_Kg": (25, 29)}


def build_livestock_quote_preview(requested_items, pigs, observed_at=None, evidence_source=None):
    observed_at = observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    used, recommendations = set(), []
    for item in requested_items:
        quantity = int(item.get("quantity") or 0)
        sex, band = str(item.get("sex") or "Any"), str(item.get("weight_range") or "")
        low, high = WEIGHT_RANGES.get(band, (None, None))
        candidates = []
        for pig in pigs or []:
            pig_id = str(pig.get("pig_id") or pig.get("Pig_ID") or "")
            weight = _number(pig.get("latest_weight_kg", pig.get("current_weight_kg", pig.get("Current_Weight_Kg"))))
            if not pig_id or pig_id in used or weight is None or low is None:
                continue
            if sex not in {"", "Any"} and str(pig.get("sex") or pig.get("Sex") or "") != sex:
                continue
            state, distance = _candidate_state(pig, weight, low, high)
            if state:
                preview = _render_candidate(pig, state, weight)
                candidates.append((
                    0 if preview["recommendable"] and not preview["purpose_review_required"] else 1,
                    _rank(state), distance, str(pig.get("tag_number") or pig_id), pig, preview,
                ))
        candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3].lower()))
        selected = candidates[:quantity]
        used.update(str(row[4].get("pig_id") or row[4].get("Pig_ID")) for row in selected)
        rendered = [row[5] for row in selected]
        usable = [row for row in rendered if row["recommendable"] and not row["purpose_review_required"]]
        exact = sum(row["match_state"] == "exact_match" for row in usable)
        projected = sum(row["match_state"] == "projected_growth" for row in usable)
        shortfall = max(0, quantity - len(usable))
        status = "unavailable" if shortfall == quantity else "partial" if shortfall else "projected" if projected else "confirmed"
        recommendations.append({
            "request_item_key": item.get("request_item_key"), "category": item.get("category"),
            "weight_range": band, "sex": sex, "requested_quantity": quantity,
            "status": status, "exact_match_count": exact, "projected_count": projected,
            "shortfall_quantity": shortfall, "candidates": rendered,
        })
    return {
        "success": True, "contract_version": CONTRACT_VERSION, "observed_at": observed_at,
        "evidence_source": str(evidence_source or "bounded_allocation_snapshot"),
        "request_state": "customer_request_captured", "recommendation_state": "herdmaster_advisory_only",
        "reservation_state": "not_reserved", "fulfilment_state": "not_fulfilled",
        "requested_items": requested_items, "recommendations": recommendations, "writes_performed": False,
        "authority_boundary": "No pig is attached, allocated, reserved, promised, re-purposed or sold by this preview.",
    }


def _candidate_state(pig, weight, low, high):
    if str(pig.get("status") or pig.get("Status") or "").lower() != "active": return None, 999
    if str(pig.get("on_farm") or pig.get("On_Farm") or "").lower() not in {"yes", "true", "1", "on farm"}: return None, 999
    if str(pig.get("reserved_status") or pig.get("Reserved_Status") or "").lower() in {"reserved", "allocated"} or pig.get("reserved_for_order_id"): return None, 999
    if low <= weight <= high: return "exact_match", 0
    distance = low - weight if weight < low else weight - high
    if 0 < distance <= 2:
        if weight < low and (_number(pig.get("average_daily_gain_kg")) or 0) > 0: return "projected_growth", distance
        return "near_match", distance
    return None, distance


def _render_candidate(pig, state, weight):
    purpose = str(pig.get("purpose") or pig.get("Purpose") or "Unknown") or "Unknown"
    withdrawal = str(pig.get("withdrawal_evidence_state") or "unknown").lower()
    health = str(pig.get("health_status") or "").lower()
    hold = str(pig.get("hold_status") or pig.get("sale_hold_status") or "").lower()
    blockers = []
    if any(token in health for token in ("sick", "injured", "quarantine", "hold")): blockers.append("Current health or quarantine evidence blocks live transfer.")
    if hold in {"hold", "held", "yes", "true", "medical", "health", "sale", "movement", "quarantine"}: blockers.append("A current explicit live-sale, welfare, movement or quarantine hold blocks transfer.")
    warnings = []
    if purpose.lower() != "sale": warnings.append("Purpose review required; current purpose is not Sale.")
    if withdrawal not in {"not_applicable", "cleared", ""}:
        warnings.append("Food-chain withdrawal must be disclosed; it does not alone prohibit live transfer.")
        blockers.append("Live-transfer support is Unknown until current transport, quarantine, disease, welfare and movement evidence is attributable and clear.")
    return {
        "pig_id": str(pig.get("pig_id") or pig.get("Pig_ID") or ""), "tag_number": str(pig.get("tag_number") or pig.get("Tag_Number") or ""),
        "sex": str(pig.get("sex") or pig.get("Sex") or ""), "current_weight_kg": weight,
        "weight_date": str(pig.get("latest_weight_date") or pig.get("last_weight_date") or ""), "match_state": state,
        "purpose": purpose, "purpose_review_required": purpose.lower() != "sale", "warnings": warnings,
        "blocking_restrictions": blockers, "recommendable": not blockers,
        "withdrawal_disclosure": {"required": withdrawal not in {"not_applicable", "cleared", ""}, "food_chain_state": withdrawal or "unknown", "withdrawal_end_date": str(pig.get("current_withdrawal_end_date") or ""), "wording": "Food-chain withdrawal applies. Do not slaughter or enter the animal into the food chain during the governed period. Withdrawal alone neither approves nor prohibits live transfer and does not certify transport, veterinary, welfare, disease, quarantine or movement clearance."},
    }


def _rank(state): return {"exact_match": 0, "near_match": 1, "projected_growth": 2}.get(state, 9)
def _number(value):
    try: return float(value)
    except (TypeError, ValueError): return None
