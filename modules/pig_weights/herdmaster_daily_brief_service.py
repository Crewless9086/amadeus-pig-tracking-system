"""Pure read-only aggregation for the owner Herdmaster daily operating brief."""

from __future__ import annotations

from collections import Counter
from datetime import date
import re


CONTRACT_VERSION = "herdmaster_daily_operating_brief_v1"
EXACT_ANIMAL_CONTRACT_VERSION = "herdmaster_exact_animal_eligibility_v1"
DEFAULT_STALE_WEIGHT_DAYS = 30


def build_herdmaster_daily_brief(
    *,
    allocation_envelope=None,
    sales_envelope=None,
    litter_envelope=None,
    breeding_envelope=None,
    today=None,
):
    """Aggregate injected authoritative envelopes without performing I/O."""

    today = today or date.today()
    allocation = _envelope(allocation_envelope)
    sales = _envelope(sales_envelope)
    litters = _envelope(litter_envelope)
    breeding = _envelope(breeding_envelope)

    allocation_rows = _rows(allocation, "pigs")
    sales_rows = _rows(sales, "pigs")
    litter_rows = _rows(litters, "litters")
    sow_rows = _rows(breeding, "sows")
    boar_rows = _rows(breeding, "boars")
    allocation_available = allocation is not None and allocation_rows is not None
    sales_available = sales is not None and sales_rows is not None
    litter_available = litters is not None and litter_rows is not None
    breeding_available = breeding is not None and sow_rows is not None and boar_rows is not None

    allocation_rows = allocation_rows or []
    sales_rows = sales_rows or []
    litter_rows = litter_rows or []
    sow_rows = sow_rows or []
    boar_rows = boar_rows or []

    allocation_state = _allocation_query_state(allocation, sales, allocation_rows, sales_rows)
    current_rows = [
        row for row in allocation_rows
        if _norm(row.get("status")) == "active" and _yes(row.get("on_farm"))
    ]
    terminal_rows = [row for row in allocation_rows if _is_terminal(row)]
    stale_days = _stale_weight_days(allocation)

    herd_overview = _herd_overview(
        allocation_rows,
        current_rows,
        terminal_rows,
        available=allocation_available,
    )
    evidence_queue = _evidence_queue(
        allocation_rows,
        current_rows,
        stale_days=stale_days,
        available=allocation_available,
    )
    litter_summary = _litter_summary(litter_rows, available=litter_available)
    breeding_summary = _breeding_summary(
        sow_rows,
        boar_rows,
        available=breeding_available,
    )
    growth_summary = _growth_summary(current_rows, available=allocation_available)
    sales_readiness = _sales_readiness(
        sales_rows,
        allocation_state=allocation_state,
        available=sales_available,
    )
    worklist = _owner_worklist(
        evidence_queue=evidence_queue,
        litter_summary=litter_summary,
        breeding_summary=breeding_summary,
        growth_summary=growth_summary,
        allocation_available=allocation_available,
        sales_available=sales_available,
    )

    source_status = {
        "allocation": _source_status(
            allocation,
            rows=allocation_rows,
            available=allocation_available,
            default_source_key="source",
            timestamp_keys=("generated_at", "generated_date", "observation_timestamp"),
        ),
        "sales": _source_status(
            sales,
            rows=sales_rows,
            available=sales_available,
            default_source_key="source",
            timestamp_keys=("generated_at", "generated_date", "observation_timestamp"),
            row_timestamp_key="eligibility_observed_at",
            row_source_key="source",
        ),
        "litters": _source_status(
            litters,
            rows=litter_rows,
            available=litter_available,
            default_source_key="source",
            timestamp_keys=("generated_at", "generated_date", "observation_timestamp"),
        ),
        "breeding": _source_status(
            breeding,
            rows=sow_rows + boar_rows,
            available=breeding_available,
            default_source_key="source",
            timestamp_keys=("generated_at", "generated_date", "observation_timestamp"),
        ),
        "allocation_query": allocation_state,
    }
    blockers = [
        name
        for name, available in (
            ("allocation_envelope_unavailable", allocation_available),
            ("sales_envelope_unavailable", sales_available),
            ("litter_envelope_unavailable", litter_available),
            ("breeding_envelope_unavailable", breeding_available),
        )
        if not available
    ]
    if allocation_state["state"] == "Unavailable":
        blockers.append("allocation_query_state_unavailable")

    return {
        "version": CONTRACT_VERSION,
        "brief_date": today.isoformat(),
        "status": "complete" if not blockers else "evidence_incomplete",
        "sanitized_executive_summary": _executive_summary(
            herd_overview,
            evidence_queue,
            litter_summary,
            breeding_summary,
            growth_summary,
            sales_readiness,
        ),
        "source_status": source_status,
        "herd_overview": herd_overview,
        "evidence_work_queue": evidence_queue,
        "litter_management": litter_summary,
        "breeding_review": breeding_summary,
        "growth_cohorts": growth_summary,
        "sales_readiness": sales_readiness,
        "owner_worklist": worklist,
        "evidence_blockers": blockers,
        "privacy": {
            "owner_only": True,
            "contains_pig_ids": False,
            "contains_tags": False,
            "contains_pens": False,
            "contains_private_medical_details": False,
            "customer_visible": False,
        },
        "authority": {
            "read_only": True,
            "proposal_only": True,
            "writes_performed": False,
            "protected_actions_performed": False,
            "creates_order": False,
            "reserves_or_allocates_stock": False,
            "changes_farm_data": False,
            "sends_customer_message": False,
            "sends_telegram": False,
        },
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def _herd_overview(all_rows, current_rows, terminal_rows, *, available):
    if not available:
        return {
            "status": "Unavailable",
            "total_records": None,
            "active_on_farm": None,
            "terminal": None,
            "sex_distribution": {},
            "purpose_distribution": {},
            "lifecycle_distribution": {},
        }
    return {
        "status": "available",
        "total_records": len(all_rows),
        "active_on_farm": len(current_rows),
        "terminal": len(terminal_rows),
        "sex_distribution": dict(_ordered_counter(_sex(row) for row in current_rows)),
        "purpose_distribution": dict(_ordered_counter(_purpose(row) for row in current_rows)),
        "lifecycle_distribution": dict(_ordered_counter(_lifecycle(row) for row in current_rows)),
    }


def _evidence_queue(all_rows, current_rows, *, stale_days, available):
    if not available:
        return {
            "status": "Unavailable",
            "stale_weight_days": stale_days,
            **{key: None for key in (
                "missing_current_weight",
                "stale_weight",
                "missing_sex",
                "unknown_purpose",
                "missing_or_unknown_withdrawal",
                "medical_or_follow_up_holds",
                "lifecycle_on_farm_conflicts",
                "missing_allocation_proof",
                "missing_reservation_proof",
                "needs_classification",
            )},
        }

    missing_weight = sum(row.get("latest_weight_kg") in (None, "") for row in current_rows)
    stale_weight = sum(
        _number(row.get("days_since_weight")) is not None
        and _number(row.get("days_since_weight")) > stale_days
        for row in current_rows
    )
    return {
        "status": "available",
        "stale_weight_days": stale_days,
        "missing_current_weight": missing_weight,
        "stale_weight": stale_weight,
        "missing_sex": sum(_sex(row) == "Unknown" for row in current_rows),
        "unknown_purpose": sum(_purpose(row) == "Unknown" for row in current_rows),
        "missing_or_unknown_withdrawal": sum(
            _norm(row.get("withdrawal_evidence_state"))
            not in {"not_applicable", "cleared", "hold"}
            for row in current_rows
        ),
        "medical_or_follow_up_holds": sum(_is_medical_hold(row) for row in current_rows),
        "lifecycle_on_farm_conflicts": sum(
            (_norm(row.get("status")) == "active") != _yes(row.get("on_farm"))
            for row in all_rows
        ),
        "missing_allocation_proof": sum(
            _norm(row.get("allocation_query_status")) != "known"
            or _norm(row.get("allocation_evidence_state"))
            not in {"known_unallocated", "allocated"}
            for row in current_rows
        ),
        "missing_reservation_proof": sum(
            _norm(row.get("reserved_status"))
            not in {"not_reserved", "reserved", "allocated"}
            for row in current_rows
        ),
        "needs_classification": sum(
            _purpose(row) == "Unknown"
            or _lifecycle(row) == "Unknown"
            or _text(row.get("readiness_bucket")) in {"Needs Classification", "Needs Data"}
            for row in current_rows
        ),
    }


def _litter_summary(rows, *, available):
    if not available:
        return {
            "status": "Unavailable",
            "total_litters": None,
            "approaching_weaning_7_days": None,
            "overdue_weaning_evidence": None,
            "litter_count_conflicts": None,
            "historical_loss_totals": {},
            "recent_loss_assessment": {
                "status": "Unavailable",
                "reason": "Date-bounded loss evidence was not provided.",
            },
        }
    outcomes = Counter()
    for row in rows:
        lifecycle = row.get("lifecycle_outcomes")
        if not isinstance(lifecycle, dict):
            continue
        for key in ("dead", "removed", "slaughtered", "sold", "other"):
            value = _integer(lifecycle.get(key))
            outcomes[key] += value if value is not None else 0
    return {
        "status": "available",
        "total_litters": len(rows),
        "approaching_weaning_7_days": sum(
            not _litter_terminal(row)
            and isinstance(row.get("days_until_estimated_wean"), int)
            and 0 <= row["days_until_estimated_wean"] <= 7
            for row in rows
        ),
        "overdue_weaning_evidence": sum(
            not _litter_terminal(row)
            and isinstance(row.get("days_until_estimated_wean"), int)
            and row["days_until_estimated_wean"] < 0
            for row in rows
        ),
        "litter_count_conflicts": sum(
            isinstance(row.get("reconciliation"), dict)
            and row["reconciliation"].get("mismatch") is True
            for row in rows
        ),
        "historical_loss_totals": dict(_ordered_counter_from_mapping(outcomes)),
        "recent_loss_assessment": {
            "status": "Unavailable",
            "reason": "Historical totals have no date-bounded loss evidence.",
        },
    }


def _breeding_summary(sows, boars, *, available):
    advisory = (
        "Advisory review only; this evidence does not establish current heat, "
        "pregnancy, body condition, or relatedness suitability."
    )
    if not available:
        return {
            "status": "Unavailable",
            "sows_with_history": None,
            "boars_with_history": None,
            "open_sows": None,
            "repeat_service_sows": None,
            "low_recorded_pregnancy_rate_sows": None,
            "advisory_only": True,
            "qualification": advisory,
        }
    return {
        "status": "available",
        "sows_with_history": len(sows),
        "boars_with_history": len(boars),
        "open_sows": sum((_integer(row.get("open_count")) or 0) > 0 for row in sows),
        "repeat_service_sows": sum(
            (_integer(row.get("repeat_service_count")) or 0) > 0 for row in sows
        ),
        "low_recorded_pregnancy_rate_sows": sum(
            (_integer(row.get("mating_count")) or 0) > 0
            and _number(row.get("pregnancy_rate")) is not None
            and _number(row.get("pregnancy_rate")) < 0.75
            for row in sows
        ),
        "advisory_only": True,
        "qualification": advisory,
    }


def _growth_summary(rows, *, available):
    if not available:
        return {
            "status": "Unavailable",
            "cohorts": {},
            "slow_or_extremely_slow": None,
            "interpretation": "Unavailable",
        }
    cohorts = Counter(_growth_class(row) for row in rows)
    slow = cohorts.get("Slow", 0) + cohorts.get("Extremely Slow", 0)
    return {
        "status": "available",
        "cohorts": dict(_ordered_counter_from_mapping(cohorts)),
        "slow_or_extremely_slow": slow,
        "interpretation": (
            "Cohort-level review is required before treating classifications "
            "as individual welfare incidents."
        ),
    }


def _sales_readiness(rows, *, allocation_state, available):
    state_known = allocation_state["state"] == "known"
    if not available:
        return _unavailable_sales(allocation_state, "Sales envelope is unavailable.")

    eligible_rows = [
        row for row in rows
        if state_known
        and row.get("live_stock_sale_eligible") is True
        and row.get("evidence_complete") is True
        and _text(row.get("exact_animal_eligibility_contract_version"))
        == EXACT_ANIMAL_CONTRACT_VERSION
        and _norm(row.get("allocation_query_status")) == "known"
    ]
    categories = Counter()
    for row in eligible_rows:
        key = f"{_sale_category(row)} | {_sex(row)}"
        categories[key] += 1
    exclusion_counts = Counter()
    for row in rows:
        if row in eligible_rows:
            continue
        reasons = row.get("exclusion_reasons")
        reasons = reasons if isinstance(reasons, list) else [row.get("live_stock_sale_reason")]
        for reason in reasons:
            exclusion_counts[_sanitized_exclusion_reason(reason)] += 1

    if not state_known:
        return {
            **_unavailable_sales(
                allocation_state,
                "Allocation-query state is unavailable; eligible counts are withheld.",
            ),
            "considered": len(rows),
            "overlapping_exclusion_counts": dict(
                _ordered_counter_from_mapping(exclusion_counts)
            ),
        }

    return {
        "status": "available",
        "contract_version": EXACT_ANIMAL_CONTRACT_VERSION,
        "allocation_query_state": allocation_state,
        "considered": len(rows),
        "affirmatively_eligible": len(eligible_rows),
        "known_zero": len(eligible_rows) == 0,
        "eligible_by_category_and_sex": dict(
            _ordered_counter_from_mapping(categories)
        ),
        "eligible_weight_bands": dict(_ordered_counter(
            format_weight_band_label(row.get("weight_band")) for row in eligible_rows
        )),
        "eligible_weight_bands_plain_text": _weight_band_summary(eligible_rows),
        "overlapping_exclusion_counts": dict(
            _ordered_counter_from_mapping(exclusion_counts)
        ),
        "tested_enquiry_shortfalls": {
            "one_male_grower_25_29_kg": _enquiry(eligible_rows, 1, 25, 29),
            "two_male_growers_25_29_kg": _enquiry(eligible_rows, 2, 25, 29),
            "three_male_growers_around_30_kg": _enquiry(eligible_rows, 3, 27, 33),
        },
        "proposal_only": True,
        "customer_private_details_visible": False,
    }


def _unavailable_sales(allocation_state, reason):
    return {
        "status": "Unavailable",
        "reason": reason,
        "contract_version": EXACT_ANIMAL_CONTRACT_VERSION,
        "allocation_query_state": allocation_state,
        "considered": None,
        "affirmatively_eligible": None,
        "known_zero": False,
        "eligible_by_category_and_sex": {},
        "eligible_weight_bands": {},
        "eligible_weight_bands_plain_text": "Unavailable",
        "overlapping_exclusion_counts": {},
        "tested_enquiry_shortfalls": {
            name: {
                "status": "evidence_unavailable",
                "eligible": None,
                "selected": 0,
                "shortfall": quantity,
            }
            for name, quantity in (
                ("one_male_grower_25_29_kg", 1),
                ("two_male_growers_25_29_kg", 2),
                ("three_male_growers_around_30_kg", 3),
            )
        },
        "proposal_only": True,
        "customer_private_details_visible": False,
    }


def _owner_worklist(
    *,
    evidence_queue,
    litter_summary,
    breeding_summary,
    growth_summary,
    allocation_available,
    sales_available,
):
    today = []
    next_three = []
    next_seven = []

    if not allocation_available or not sales_available:
        today.append(_work_item(
            "restore_authoritative_evidence",
            None,
            "data_dependency",
            "Restore unavailable authoritative envelopes before operational interpretation.",
            "Prevents missing evidence from becoming false zero or clearance.",
        ))
    _append_if_positive(today, evidence_queue.get("medical_or_follow_up_holds"), _work_item(
        "medical_follow_up",
        evidence_queue.get("medical_or_follow_up_holds"),
        "physical_farm_check",
        "Physically review held animals and their treatment/withdrawal evidence.",
        "Prevents unsafe allocation or sale.",
    ))
    _append_if_positive(today, litter_summary.get("overdue_weaning_evidence"), _work_item(
        "overdue_weaning",
        litter_summary.get("overdue_weaning_evidence"),
        "physical_farm_check",
        "Confirm overdue litter status before any later lifecycle correction.",
        "Restores trustworthy weaning evidence.",
    ))
    weight_count = _sum_known(
        evidence_queue.get("missing_current_weight"),
        evidence_queue.get("stale_weight"),
    )
    _append_if_positive(today, weight_count, _work_item(
        "weight_evidence",
        weight_count,
        "physical_farm_check",
        "Weigh animals with missing or stale current evidence.",
        "Improves growth, readiness and valuation decisions.",
    ))

    _append_if_positive(next_three, evidence_queue.get("unknown_purpose"), _work_item(
        "purpose_review",
        evidence_queue.get("unknown_purpose"),
        "data_review",
        "Review unknown purposes through the owner purpose-review process.",
        "Reduces classification and allocation uncertainty.",
    ))
    breeding_count = _sum_known(
        breeding_summary.get("open_sows"),
        breeding_summary.get("repeat_service_sows"),
    )
    _append_if_positive(next_three, breeding_count, _work_item(
        "breeding_review",
        breeding_count,
        "physical_farm_check",
        "Review breeding-history opportunities against current physical evidence.",
        "Supports owner breeding decisions without claiming readiness.",
    ))
    _append_if_positive(next_seven, growth_summary.get("slow_or_extremely_slow"), _work_item(
        "growth_cohort_review",
        growth_summary.get("slow_or_extremely_slow"),
        "physical_and_data_review",
        "Triage slow-growth evidence by pen, feed and weighing cohort.",
        "Converts a large animal queue into manageable cohort actions.",
    ))
    next_seven.append(_work_item(
        "recent_loss_evidence",
        None,
        "data_dependency",
        "Add date-bounded evidence before assessing recent welfare losses.",
        "Prevents historical totals from being reported as a current incident.",
    ))
    return {
        "today": today,
        "next_3_days": next_three,
        "next_7_days": next_seven,
        "deterministic_order": True,
    }


def _executive_summary(herd, queue, litters, breeding, growth, sales):
    if herd["status"] != "available":
        return {
            "status": "evidence_incomplete",
            "headline": "Herd overview is unavailable; no zero-stock or clearance claim is made.",
            "owner_focus": "Restore authoritative evidence before acting.",
        }
    return {
        "status": "owner_review_required",
        "headline": (
            f"{herd['active_on_farm']} active/on-farm animals; "
            f"{herd['terminal']} terminal records."
        ),
        "owner_focus": (
            f"{queue['medical_or_follow_up_holds']} medical/follow-up holds, "
            f"{queue['stale_weight']} stale weights, "
            f"{queue['unknown_purpose']} purpose reviews, and "
            f"{litters['overdue_weaning_evidence']} overdue weaning evidence items."
        ),
        "management_context": (
            f"{breeding['open_sows']} open-sow history signals and "
            f"{growth['slow_or_extremely_slow']} slow-growth classifications "
            "require advisory owner review."
        ),
        "sales_context": (
            f"{sales['affirmatively_eligible']} affirmatively eligible animals."
            if sales["status"] == "available"
            else "Exact sales readiness is unavailable."
        ),
        "sales_weight_bands": sales.get(
            "eligible_weight_bands_plain_text",
            "Unavailable",
        ),
    }


def _allocation_query_state(allocation, sales, allocation_rows, sales_rows):
    explicit = []
    exposed_at = []
    for envelope, label in ((allocation, "allocation_envelope"), (sales, "sales_envelope")):
        if envelope and "allocation_query_status" in envelope:
            value = _allocation_value(envelope.get("allocation_query_status"))
            if value:
                explicit.append(value)
                exposed_at.append(label)
    for rows, label in ((allocation_rows, "allocation_rows"), (sales_rows, "sales_rows")):
        row_values = {
            value
            for value in (
                _allocation_value(row.get("allocation_query_status"))
                for row in rows
                if isinstance(row, dict) and "allocation_query_status" in row
            )
            if value
        }
        if len(row_values) == 1:
            explicit.extend(row_values)
            exposed_at.append(label)
        elif len(row_values) > 1:
            return {
                "state": "Unavailable",
                "exposure": "Conflicting explicit values",
                "known_zero": False,
            }
    if not explicit:
        return {
            "state": "Unavailable",
            "exposure": "Not exposed",
            "known_zero": False,
        }
    if len(set(explicit)) != 1:
        return {
            "state": "Unavailable",
            "exposure": "Conflicting explicit values",
            "known_zero": False,
        }
    return {
        "state": explicit[0],
        "exposure": ", ".join(dict.fromkeys(exposed_at)),
        "known_zero": False,
    }


def _source_status(
    envelope,
    *,
    rows,
    available,
    default_source_key,
    timestamp_keys,
    row_timestamp_key="",
    row_source_key="",
):
    if not available:
        return {
            "status": "Unavailable",
            "source": "Unavailable",
            "observation_timestamp": "Unavailable",
        }
    source = envelope.get(default_source_key)
    if isinstance(source, dict):
        source = ", ".join(
            f"{key}={value}"
            for key, value in sorted(source.items())
            if not key.startswith("writes_")
        )
    source = _text(source)
    if not source and row_source_key:
        source_values = sorted({
            _text(row.get(row_source_key))
            for row in rows
            if _text(row.get(row_source_key))
        })
        source = ", ".join(source_values)
    timestamp = next(
        (_text(envelope.get(key)) for key in timestamp_keys if _text(envelope.get(key))),
        "",
    )
    if not timestamp and row_timestamp_key:
        timestamp_values = sorted({
            _text(row.get(row_timestamp_key))
            for row in rows
            if _text(row.get(row_timestamp_key))
        })
        timestamp = ", ".join(timestamp_values)
    return {
        "status": "available",
        "source": source or "Not exposed",
        "observation_timestamp": timestamp or "Not exposed",
    }


def _enquiry(rows, quantity, low, high):
    matches = [
        row for row in rows
        if _sex(row) == "Male"
        and "grower" in _norm(row.get("sale_category") or row.get("calculated_stage"))
        and _number(row.get("current_weight_kg")) is not None
        and low <= _number(row.get("current_weight_kg")) <= high
        and bool(_text(row.get("latest_weight_date")))
    ]
    return {
        "status": "known",
        "eligible": len(matches),
        "selected": min(quantity, len(matches)),
        "shortfall": max(quantity - len(matches), 0),
    }


def _sanitized_exclusion_reason(value):
    reason = _norm(value)
    checks = (
        ("inactive_or_off_farm", ("not_active", "not active", "not_on_farm", "not on farm")),
        ("purpose_not_sale", ("purpose", "not_sale")),
        ("sex_unknown_or_mismatch", ("sex",)),
        ("stage_or_category_unknown", ("stage", "category")),
        ("weight_missing_or_stale", ("weight",)),
        ("medical_not_clear", ("medical", "health", "hold")),
        ("withdrawal_unknown_or_active", ("withdrawal",)),
        ("allocation_unavailable_or_allocated", ("allocation", "order")),
        ("reservation_unknown_or_reserved", ("reservation", "reserved")),
    )
    for label, fragments in checks:
        if any(fragment in reason for fragment in fragments):
            return label
    return "other_or_unspecified"


def format_weight_band_label(value):
    """Return an unambiguous display label for a supported weight band."""

    if isinstance(value, bool):
        return "Unknown"
    if isinstance(value, (int, float)):
        return f"{_display_number(value)} kg"

    label = _text(value)
    if not label:
        return "Unknown"
    number = r"(\d+(?:\.\d+)?)"
    range_match = re.fullmatch(
        rf"\s*{number}\s*(?:_to_|to|[-–—])\s*{number}\s*(?:_?kg)?\s*",
        label,
        flags=re.IGNORECASE,
    )
    if range_match:
        low = _display_number(range_match.group(1))
        high = _display_number(range_match.group(2))
        if _number(low) is None or _number(high) is None or _number(low) >= _number(high):
            return "Unknown"
        return f"{low}–{high} kg"

    exact_match = re.fullmatch(
        rf"\s*{number}\s*(?:_?kg)?\s*",
        label,
        flags=re.IGNORECASE,
    )
    if exact_match:
        return f"{_display_number(exact_match.group(1))} kg"

    plus_match = re.fullmatch(
        rf"\s*{number}\s*(?:(?:_?kg)?\s*\+|_plus_kg)\s*",
        label,
        flags=re.IGNORECASE,
    )
    if plus_match:
        return f"{_display_number(plus_match.group(1))} kg+"
    return "Unknown"


def _weight_band_summary(rows):
    counts = Counter(format_weight_band_label(row.get("weight_band")) for row in rows)
    if not counts:
        return "Known zero eligible weight bands."
    return ", ".join(
        f"{label}: {count}"
        for label, count in _ordered_counter_from_mapping(counts)
    )


def _display_number(value):
    number = _number(value)
    if number is None:
        return ""
    return str(int(number)) if number.is_integer() else f"{number:g}"


def _work_item(category, count, action_type, action, benefit):
    return {
        "category": category,
        "count": count,
        "action_type": action_type,
        "action": action,
        "expected_operational_benefit": benefit,
    }


def _append_if_positive(target, count, item):
    if isinstance(count, int) and count > 0:
        target.append(item)


def _sum_known(*values):
    known = [value for value in values if isinstance(value, int)]
    return sum(known) if known else None


def _rows(envelope, key):
    if envelope is None:
        return None
    value = envelope.get(key)
    return value if isinstance(value, list) else None


def _envelope(value):
    return value if isinstance(value, dict) else None


def _stale_weight_days(envelope):
    thresholds = envelope.get("thresholds") if envelope else {}
    value = _integer(thresholds.get("stale_weight_days")) if isinstance(thresholds, dict) else None
    return value if value is not None and value >= 0 else DEFAULT_STALE_WEIGHT_DAYS


def _allocation_value(value):
    value = _norm(value)
    if value in {"known", "success", "available"}:
        return "known"
    if value in {"unavailable", "unknown", "failed", "error"}:
        return "Unavailable"
    return ""


def _is_terminal(row):
    status = _norm(row.get("status"))
    return status in {
        "sold", "dead", "deceased", "slaughtered", "removed", "culled", "exited",
    } or (status != "active" and not _yes(row.get("on_farm")))


def _litter_terminal(row):
    return _norm(row.get("litter_status")) in {"weaned", "completed"}


def _is_medical_hold(row):
    withdrawal = _norm(row.get("withdrawal_evidence_state"))
    medical = _norm(row.get("medical_status"))
    health = _norm(row.get("health_status"))
    hold = _norm(row.get("hold_status"))
    return (
        withdrawal == "hold"
        or medical not in {"", "clear"}
        or any(value in health for value in ("hold", "injur", "ill", "follow_up", "treat"))
        or hold in {"hold", "active", "yes", "true"}
    )


def _sex(row):
    value = _norm(row.get("sex"))
    if value == "male":
        return "Male"
    if value == "female":
        return "Female"
    if value == "castrated_male":
        return "Castrated Male"
    return "Unknown"


def _purpose(row):
    value = _norm(row.get("purpose"))
    if value == "sale":
        return "Sale"
    if value == "breeding":
        return "Breeding"
    if value in {"grow_out", "growout"}:
        return "Grow_Out"
    return "Unknown"


def _lifecycle(row):
    return _text(
        row.get("calculated_stage")
        or row.get("animal_type")
        or row.get("readiness_bucket")
        or "Unknown"
    )


def _growth_class(row):
    value = _text(row.get("growth_class"))
    return value if value else "Unknown"


def _sale_category(row):
    return _text(
        row.get("sale_category")
        or row.get("calculated_stage")
        or "Unknown"
    )


def _ordered_counter(values):
    return sorted(Counter(values).items(), key=lambda item: item[0])


def _ordered_counter_from_mapping(mapping):
    return sorted(mapping.items(), key=lambda item: item[0])


def _number(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _integer(value):
    number = _number(value)
    return int(number) if number is not None else None


def _yes(value):
    return value is True or _norm(value) in {"yes", "true", "1", "on_farm"}


def _text(value):
    return str(value or "").strip()


def _norm(value):
    return _text(value).casefold().replace("-", "_").replace(" ", "_")
