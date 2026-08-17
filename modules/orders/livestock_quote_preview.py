"""Pure, zero-write livestock request and HERDMASTER recommendation preview."""

from datetime import date, datetime, timedelta, timezone

CONTRACT_VERSION = "livestock_quote_preview_v2"
WEIGHT_RANGES = {
    "2_to_4_Kg": (2, 4), "5_to_6_Kg": (5, 6), "7_to_9_Kg": (7, 9),
    "10_to_14_Kg": (10, 14), "15_to_19_Kg": (15, 19),
    "20_to_24_Kg": (20, 24), "25_to_29_Kg": (25, 29),
}
MAX_WEIGHT_AGE_DAYS = 14
MAX_PROJECTION_DAYS = 14


def build_livestock_quote_preview(requested_items, herdmaster_packet, observed_at=None,
                                   evidence_source=None):
    """Rank only HERDMASTER-approved candidates; never infer livestock authority."""
    observed_at = observed_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    packet_pigs = list((herdmaster_packet or {}).get("pigs") or [])
    cutoff = _date(herdmaster_packet.get("evidence_cutoff_date")) or date.today()
    used = set()
    recommendations = []
    grouped_review = {}

    for item in requested_items:
        quantity = int(item.get("quantity") or 0)
        sex = str(item.get("sex") or "Any")
        band = str(item.get("weight_range") or "")
        low, high = WEIGHT_RANGES.get(band, (None, None))
        eligible = []
        review = []
        for authority in packet_pigs:
            identity = authority.get("identity") or {}
            current = authority.get("current_state") or {}
            pig_id = str(identity.get("pig_id") or "")
            weight = _number(current.get("latest_weight_kg"))
            if not pig_id or pig_id in used or weight is None or low is None:
                continue
            if sex not in {"", "Any"} and str(current.get("sex") or "") != sex:
                continue
            if not _category_matches(item.get("category"), identity.get("animal_type")):
                continue
            match_state, distance, projected_target_date = _candidate_state(
                weight, low, high, current.get("average_daily_gain_kg"),
                current.get("latest_weight_date"), cutoff,
            )
            if not match_state:
                continue
            rendered = _render_candidate(authority, match_state, projected_target_date)
            row = (_rank(match_state), distance,
                   str(identity.get("tag_number") or pig_id).lower(), rendered)
            if _recommendable(authority) and match_state != "weight_evidence_review":
                eligible.append(row)
            else:
                review.append(row)
                _add_grouped_review(grouped_review, rendered)

        eligible.sort(key=lambda row: row[:3])
        review.sort(key=lambda row: row[:3])
        selected = eligible[:quantity]
        used.update(row[3]["pig_id"] for row in selected)
        rendered = [row[3] for row in selected]
        counts = {state: sum(candidate["match_state"] == state for candidate in rendered)
                  for state in ("exact_match", "near_match", "projected_growth")}
        supported = len(rendered)
        shortfall = max(0, quantity - supported)
        status = ("unavailable" if shortfall == quantity else "partial" if shortfall
                  else "projected" if counts["projected_growth"] else "supported")
        recommendations.append({
            "request_item_key": item.get("request_item_key"),
            "category": item.get("category"), "weight_range": band, "sex": sex,
            "requested_quantity": quantity, "status": status,
            "exact_match_count": counts["exact_match"],
            "near_match_count": counts["near_match"],
            "projected_count": counts["projected_growth"],
            "supported_count": supported, "shortfall_quantity": shortfall,
            "candidates": rendered,
            "purpose_or_evidence_review_count": len(review),
        })

    return {
        "success": True, "contract_version": CONTRACT_VERSION,
        "herdmaster_contract_version": herdmaster_packet.get("contract_version"),
        "herdmaster_packet_digest": herdmaster_packet.get("packet_digest"),
        "evidence_cutoff_date": herdmaster_packet.get("evidence_cutoff_date"),
        "observed_at": observed_at,
        "evidence_source": str(evidence_source or "canonical_repeatable_read"),
        "request_state": "customer_request_captured",
        "recommendation_state": "herdmaster_advisory_only",
        "reservation_state": "not_reserved", "fulfilment_state": "not_fulfilled",
        "requested_items": requested_items, "recommendations": recommendations,
        "purpose_or_evidence_review": list(grouped_review.values()),
        "writes_performed": False, "creates_order": False,
        "creates_order_line": False, "creates_reservation": False,
        "generates_document": False, "creates_buyer_acknowledgement": False,
        "authority_boundary": (
            "No pig is attached, allocated, reserved, promised, re-purposed or sold by this preview."
        ),
    }


def _recommendable(authority):
    order_state = (authority.get("current_order_eligibility") or {}).get("state")
    duplicate_state = (authority.get("order_line_duplication_protection") or {}).get("state")
    return (
        (authority.get("livestock_transfer_eligibility") or {}).get("state")
        == "eligible_on_current_evidence"
        and (authority.get("current_purpose_eligibility") or {}).get("state") == "eligible"
        and (authority.get("active_on_farm_eligibility") or {}).get("state") == "eligible"
        and order_state in {"candidate_not_added", "included_draft_unreserved"}
        and duplicate_state not in {"conflicting_duplicate_lines", "existing_line_blocks_duplicate"}
    )


def _render_candidate(authority, match_state, projected_target_date=None):
    identity = authority.get("identity") or {}
    current = authority.get("current_state") or {}
    axes = {
        name: authority.get(name) for name in (
            "livestock_transfer_eligibility", "food_chain_eligibility",
            "fit_for_transport", "quarantine", "notifiable_or_infectious_disease",
            "veterinary_movement_stop", "serious_health_or_welfare_hold",
            "treatment_evidence_completeness", "treatment_evidence_conflicts",
            "medical_ambiguity", "current_purpose_eligibility",
            "active_on_farm_eligibility", "current_order_eligibility",
            "order_line_duplication_protection", "price_band_compatibility",
            "canonical_dependency_evidence", "canonical_treatment_events",
        )
    }
    if match_state == "weight_evidence_review":
        axes["weight_evidence"] = {
            "state": "blocked",
            "reason": "Latest weight evidence is missing, future-dated, or older than 14 days at the packet cutoff.",
            "evidence_ids": [str(current.get("latest_weight_date") or "missing_weight_date")],
        }
    return {
        "pig_id": str(identity.get("pig_id") or ""),
        "tag_number": str(identity.get("tag_number") or ""),
        "sex": str(current.get("sex") or ""),
        "current_weight_kg": _number(current.get("latest_weight_kg")),
        "weight_date": current.get("latest_weight_date"), "match_state": match_state,
        "projected_target_date": projected_target_date,
        "purpose": current.get("purpose"),
        "recommendable": _recommendable(authority) and match_state != "weight_evidence_review",
        "treatment_disclosure": authority.get("treatment_disclosure"),
        "authority_axes": axes,
    }


def _add_grouped_review(groups, candidate):
    for axis_name, axis in candidate["authority_axes"].items():
        if not isinstance(axis, dict) or axis.get("state") in {
            None, "eligible", "eligible_on_current_evidence", "candidate_not_added",
            "included_draft_unreserved", "no_existing_line", "clear", "compatible",
        }:
            continue
        reason = str(axis.get("reason") or axis.get("state"))
        key = f"{axis_name}:{axis.get('state')}:{reason}"
        group = groups.setdefault(key, {
            "blocking_axis": axis_name, "state": axis.get("state"), "reason": reason,
            "evidence_ids": list(axis.get("evidence_ids") or []), "candidates": [],
        })
        group["evidence_ids"] = sorted(set(group["evidence_ids"]) | set(axis.get("evidence_ids") or []))
        if not any(row["pig_id"] == candidate["pig_id"] for row in group["candidates"]):
            group["candidates"].append(candidate)


def _candidate_state(weight, low, high, average_daily_gain, latest_weight_date, cutoff):
    measured = _date(latest_weight_date)
    if not measured or not 0 <= (cutoff - measured).days <= MAX_WEIGHT_AGE_DAYS:
        distance = 0 if low <= weight <= high else low - weight if weight < low else weight - high
        return "weight_evidence_review", distance, None
    if low <= weight <= high:
        return "exact_match", 0, None
    distance = low - weight if weight < low else weight - high
    if 0 < distance <= 2:
        gain = _number(average_daily_gain) or 0
        if weight < low and gain > 0:
            projection_days = int(-(-distance // gain))
            if projection_days <= MAX_PROJECTION_DAYS:
                return "projected_growth", distance, (cutoff + timedelta(days=projection_days)).isoformat()
        return "near_match", distance, None
    return None, distance, None


def _category_matches(requested, animal_type):
    requested = str(requested or "").strip().lower()
    animal_type = str(animal_type or "").strip().lower()
    if not requested:
        return True
    if requested == "piglet":
        return animal_type in {"piglet", "weaner", "young piglet", "young piglets"}
    return requested == animal_type


def _date(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _rank(state):
    return {"exact_match": 0, "near_match": 1, "projected_growth": 2}.get(state, 9)


def _number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
