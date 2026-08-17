"""Read-only full-lifecycle genetic-merit evidence projection.

This module reports attributable associations.  It never asserts genetic
causation and never writes farm state.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from statistics import median


CONTRACT_VERSION = "herdmaster_full_lifecycle_merit_v1"
CONFIDENCE_RULE_ID = "herdmaster_merit_confidence_v1"
OFFSPRING_DISPOSITION_RULE_ID = "herdmaster_offspring_disposition_v1"
OFFSPRING_DISPOSITIONS = (
    "on_farm", "livestock_sale", "auction_sale", "slaughter_pig_sale",
    "meat_processed", "deceased", "other_unresolved",
)


def _text(value):
    return "" if value is None else str(value).strip()


def _number(value):
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        return None


def _identity(row):
    pig_id = _text(row.get("pig_id"))
    name = _text(row.get("name") or row.get("pig_name"))
    tag = _text(row.get("tag_number"))
    primary = name or tag or pig_id or "Unknown"
    return {
        "name": name or None,
        "tag_number": tag or None,
        "pig_id": pig_id,
        "display_name": primary,
        "secondary_identity": tag if name and tag else (pig_id if primary != pig_id else None),
    }


def _effective(rows, id_key, supersedes_key):
    superseded = {_text(row.get(supersedes_key)) for row in rows if row.get(supersedes_key)}
    current = [row for row in rows if _text(row.get(id_key)) not in superseded]
    return current, {
        "event_count": len(rows),
        "superseded_event_ids": sorted(superseded),
        "events": rows,
    }


def _normalized(value):
    return _text(value).lower().replace("-", "_").replace(" ", "_")


def _payload(row):
    value = row.get("event_payload")
    return value if isinstance(value, dict) else {}


def _offspring_disposition(child, *, sales, processing, lifecycle):
    """Classify one child from completed canonical facts; ambiguity fails closed."""
    pig_id = _text(child.get("pig_id"))
    candidates = defaultdict(list)
    conflicts = []

    for sale in sales:
        if _text(sale.get("pig_id")) != pig_id or _normalized(sale.get("sale_status")) != "completed":
            continue
        stream = _normalized(sale.get("sale_stream"))
        channel = _normalized(sale.get("sale_channel"))
        category = (
            "auction_sale" if stream == "livestock" and channel == "auction" else
            "livestock_sale" if stream == "livestock" else
            "slaughter_pig_sale" if stream == "slaughter" else None
        )
        if category:
            candidates[category].append({
                "source": "sales_transaction_item",
                "sale_id": _text(sale.get("sale_id")) or None,
                "sale_item_id": _text(sale.get("sale_item_id")) or None,
                "sale_stream": _text(sale.get("sale_stream")) or None,
                "sale_channel": _text(sale.get("sale_channel")) or None,
                "sale_status": _text(sale.get("sale_status")) or None,
                "sale_date": sale.get("sale_date"),
                "rule_id": OFFSPRING_DISPOSITION_RULE_ID,
            })

    for item in processing:
        if _text(item.get("pig_id")) != pig_id:
            continue
        batch_status = _normalized(item.get("batch_status"))
        event_type = _normalized(item.get("event_type"))
        completed = batch_status == "completed" or event_type == "completed"
        processing_evidence = {
            "source": "meat_processing_batch",
            "batch_id": _text(item.get("batch_id")) or None,
            "batch_pig_id": _text(item.get("batch_pig_id")) or None,
            "batch_status": _text(item.get("batch_status")) or None,
            "batch_status_at": item.get("batch_status_at"),
            "completion_event_id": _text(item.get("completion_event_id")) or None,
            "completion_event_type": _text(item.get("event_type")) or None,
            "completion_event_date": item.get("completion_event_date"),
            "rule_id": OFFSPRING_DISPOSITION_RULE_ID,
        }
        if batch_status == "cancelled" and event_type == "completed":
            candidates["meat_processed"].append(processing_evidence)
            conflicts.append("cancelled_batch_has_completion_event")
            continue
        if completed:
            candidates["meat_processed"].append(processing_evidence)

    for event in lifecycle:
        if _text(event.get("pig_id")) != pig_id:
            continue
        payload = _payload(event)
        lifecycle_type = _normalized(event.get("lifecycle_event_type"))
        structured_values = {
            _normalized(payload.get("exit_reason")),
            _normalized(payload.get("resulting_status")),
            _normalized(payload.get("status")),
        }
        matched_values = sorted(structured_values & {"dead", "died", "deceased", "died_after_birth"})
        if lifecycle_type in {"exited_farm", "lifecycle_correction", "status_changed"} and matched_values:
            candidates["deceased"].append({
                "source": "pig_lifecycle_event",
                "lifecycle_event_id": _text(event.get("lifecycle_event_id")) or None,
                "lifecycle_event_type": _text(event.get("lifecycle_event_type")) or None,
                "effective_at": event.get("effective_at"),
                "matched_structured_facts": matched_values,
                "rule_id": OFFSPRING_DISPOSITION_RULE_ID,
            })

    if child.get("on_farm") is True:
        candidates["on_farm"].append({
            "source": "current_canonical_pig",
            "pig_id": pig_id,
            "on_farm": True,
            "rule_id": OFFSPRING_DISPOSITION_RULE_ID,
        })

    categories = sorted(candidates)
    disposition = categories[0] if len(categories) == 1 and not conflicts else "other_unresolved"
    evidence = [item for category in categories for item in candidates[category]]
    evidence.sort(key=lambda item: tuple(_text(item.get(key)) for key in (
        "source", "sale_id", "sale_item_id", "batch_id", "batch_pig_id",
        "completion_event_id", "lifecycle_event_id", "pig_id",
    )))
    return {
        "primary_disposition": disposition,
        "rule_id": OFFSPRING_DISPOSITION_RULE_ID,
        "evidence_state": "supported" if len(categories) == 1 and not conflicts else ("conflicting" if categories or conflicts else "unknown"),
        "candidate_dispositions": categories,
        "conflicts": sorted(set(conflicts)),
        "evidence": evidence,
    }


def _confidence(cohorts, outcome_eligible, outcome_total, context_present, context_total,
                *, comparability="comparable", stale=False, unresolved=False):
    outcome_coverage = None if not outcome_total or not outcome_eligible else outcome_eligible / outcome_total
    context_coverage = None if not context_total else context_present / context_total
    inputs = {
        "cohort_count": cohorts,
        "outcome_coverage": outcome_coverage,
        "context_coverage": context_coverage,
        "comparability": comparability,
        "stale_or_materially_unresolved": stale or unresolved,
    }
    if outcome_coverage is None or context_coverage is None:
        label = "Unknown"
    elif stale or unresolved or comparability == "material_unresolved" or cohorts <= 1 or outcome_coverage < .60 or context_coverage < .60:
        label = "Limited"
    elif cohorts >= 3 and outcome_coverage >= .80 and context_coverage >= .80 and comparability == "comparable":
        label = "High"
    else:
        label = "Moderate"
    return {"label": label, "confidence_rule_id": CONFIDENCE_RULE_ID, "inputs": inputs}


def _interpretation(identity, survival, confidence):
    n = survival["eligible_litter_count"]
    rate = survival["rate"]
    going = (
        f"{identity['display_name']} has {n} eligible litter outcome(s); survival is {rate:.1%}."
        if rate is not None else
        f"No supported survival result is available for {identity['display_name']}."
    )
    return {
        "going_well": going,
        "needs_attention": "Review associations alongside management, health, season, feed and environment; this is not a genetic-causation claim.",
        "missing_evidence": None if survival["missing_litter_count"] == 0 else f"{survival['missing_litter_count']} litter outcome(s) lack an eligible born-alive or weaned value.",
        "next_review": "Review again when a new attributable litter outcome, comparable growth record, correction or health observation becomes effective.",
        "confidence": confidence,
    }


def compose_full_lifecycle_merit(snapshot, *, pig_id=None):
    """Compose byte-stable semantics from one already-bounded evidence snapshot."""
    cutoff = _date(snapshot.get("cutoff"))
    pigs = [dict(row) for row in snapshot.get("pigs", [])]
    litters_raw = [dict(row) for row in snapshot.get("litters", [])]
    observations_raw = [dict(row) for row in snapshot.get("observations", [])]
    lifecycle_raw = [dict(row) for row in snapshot.get("lifecycle", [])]
    matings_all = [dict(row) for row in snapshot.get("matings", [])]
    weights_all = [dict(row) for row in snapshot.get("weights", [])]
    medical_all = [dict(row) for row in snapshot.get("medical", [])]
    sales_all = [dict(row) for row in snapshot.get("sales", [])]
    processing_all = [dict(row) for row in snapshot.get("meat_processing", [])]
    if cutoff:
        litters_all = [r for r in litters_raw if _date(r.get("farrowing_date")) and _date(r.get("farrowing_date")) <= cutoff]
        observations_all = [r for r in observations_raw if _date(r.get("observed_at")) and _date(r.get("observed_at")) <= cutoff]
        lifecycle_all = [r for r in lifecycle_raw if _date(r.get("effective_at")) and _date(r.get("effective_at")) <= cutoff]
        matings_all = [r for r in matings_all if _date(r.get("mating_date")) and _date(r.get("mating_date")) <= cutoff]
        weights_all = [r for r in weights_all if _date(r.get("weight_date")) and _date(r.get("weight_date")) <= cutoff]
        medical_all = [r for r in medical_all if _date(r.get("treatment_date")) and _date(r.get("treatment_date")) <= cutoff]
        sales_all = [r for r in sales_all if _date(r.get("sale_date")) and _date(r.get("sale_date")) <= cutoff]
        processing_all = [r for r in processing_all if (
            (_normalized(r.get("event_type")) == "completed"
             and _date(r.get("completion_event_date"))
             and _date(r.get("completion_event_date")) <= cutoff)
            or (_normalized(r.get("event_type")) != "completed"
                and _normalized(r.get("batch_status")) == "completed"
                and _date(r.get("batch_status_at"))
                and _date(r.get("batch_status_at")) <= cutoff)
        )]
    else:
        litters_all, observations_all, lifecycle_all = litters_raw, observations_raw, lifecycle_raw
    litters, litter_lineage = _effective(litters_all, "litter_id", "supersedes_litter_id")
    litter_lineage["events"] = [dict(row) for row in snapshot.get("litter_history", litters_raw)]
    historical_superseded = {
        _text(row.get("litter_id")) for row in litter_lineage["events"]
        if row.get("is_superseded") is True
    }
    explicit_superseded = {
        _text(row.get("supersedes_litter_id")) for row in litters_raw
        if row.get("supersedes_litter_id")
    }
    litter_lineage["superseded_event_ids"] = sorted(historical_superseded | explicit_superseded)
    observations, observation_lineage = _effective(
        observations_all, "observation_event_id", "supersedes_observation_event_id")
    lifecycle, lifecycle_lineage = _effective(
        lifecycle_all, "lifecycle_event_id", "supersedes_lifecycle_event_id")

    offspring_by_litter = defaultdict(list)
    for child in pigs:
        if child.get("litter_id"):
            offspring_by_litter[_text(child["litter_id"])].append(child)

    def governed_litter_outcome(litter):
        born = _number(litter.get("born_alive"))
        weaned = _number(litter.get("weaned_count"))
        children = offspring_by_litter[_text(litter.get("litter_id"))]
        status_actual = _text(litter.get("litter_status")).lower() in {"weaned", "completed"}
        child_actual = any(
            (_date(child.get("wean_date")) and (not cutoff or _date(child.get("wean_date")) <= cutoff))
            or _number(child.get("wean_weight_kg")) is not None
            or _text(child.get("animal_type")).lower() == "weaner"
            for child in children
        )
        dated_count_actual = bool(
            _date(litter.get("wean_date")) and (not cutoff or _date(litter.get("wean_date")) <= cutoff)
            and weaned is not None and weaned > 0
        )
        valid_counts = bool(
            born is not None and weaned is not None and born > 0
            and born.is_integer() and weaned.is_integer() and 0 <= weaned <= born
        )
        eligible = bool((status_actual or child_actual or dated_count_actual) and valid_counts)
        return {
            "eligible": eligible, "born_alive": born if eligible else None,
            "weaned_count": weaned if eligible else None,
            "survival_rate": weaned / born if eligible else None,
        }

    def row_for(parent):
        identity = _identity(parent)
        pid = identity["pig_id"]
        sex = _text(parent.get("sex")).lower()
        sow_participation = any(_text(r.get("sow_pig_id")) == pid for r in litters + matings_all)
        boar_participation = any(_text(r.get("boar_pig_id")) == pid for r in litters + matings_all)
        governed_type = _text(parent.get("animal_type")).lower()
        if sow_participation and boar_participation:
            key, role = None, "Unknown-conflicting"
        elif sow_participation and not boar_participation:
            key, role = "sow_pig_id", "sow"
        elif boar_participation and not sow_participation:
            key, role = "boar_pig_id", "boar"
        elif governed_type == "sow" or sex in {"female", "sow"}:
            key, role = "sow_pig_id", "sow"
        elif governed_type == "boar" or sex in {"male", "boar"}:
            key, role = "boar_pig_id", "boar"
        else:
            key, role = None, "Unknown"
        cohorts = [r for r in litters if key and _text(r.get(key)) == pid]
        opportunities = [r for r in matings_all if key and _text(r.get(key)) == pid]
        complete_opportunities = [r for r in opportunities if _text(r.get("pregnancy_status") or r.get("status")).lower() in {
            "confirmed_pregnant", "not_pregnant", "repeat_service", "farrowed", "completed"
        } or any(_text(l.get("mating_id")) == _text(r.get("mating_id")) for l in cohorts)]
        eligible = []
        missing = 0
        for litter in cohorts:
            outcome = governed_litter_outcome(litter)
            if not outcome["eligible"]:
                missing += 1
            else:
                eligible.append((outcome["born_alive"], outcome["weaned_count"]))
        born_total = sum(x[0] for x in eligible) if eligible else None
        weaned_total = sum(x[1] for x in eligible) if eligible else None
        rate = (weaned_total / born_total) if born_total else None
        survival = {
            "rate": rate,
            "weaned_numerator": weaned_total,
            "born_alive_denominator": born_total,
            "eligible_litter_count": len(eligible),
            "observed_litter_count": len(cohorts),
            "missing_litter_count": missing,
        }
        context_fields = ("management_context", "season_context", "environment_context", "feed_context", "health_context")
        context_total = len(cohorts) * len(context_fields)
        context_present = sum(bool(_text(r.get(field))) for r in cohorts for field in context_fields)
        context_comparable = all(
            len({_text(r.get(field)).lower() for r in cohorts if _text(r.get(field))}) <= 1
            for field in context_fields
        )
        confidence = _confidence(
            len(cohorts), len(eligible), len(cohorts), context_present, context_total,
            comparability="comparable" if context_comparable else "material_unresolved",
        )
        partners = sorted({_text(r.get("boar_pig_id" if key == "sow_pig_id" else "sow_pig_id")) for r in cohorts if r.get("boar_pig_id" if key == "sow_pig_id" else "sow_pig_id")})
        offspring = [child for litter in cohorts for child in offspring_by_litter[_text(litter.get("litter_id"))]]
        offspring_dispositions = []
        for child in sorted(offspring, key=lambda item: _text(item.get("pig_id"))):
            classified = _offspring_disposition(
                child, sales=sales_all, processing=processing_all, lifecycle=lifecycle)
            offspring_dispositions.append({"identity": _identity(child), **classified})
        disposition_summary = {category: 0 for category in OFFSPRING_DISPOSITIONS}
        for item in offspring_dispositions:
            disposition_summary[item["primary_disposition"]] += 1
        disposition_summary.update({
            "total_recorded": len(offspring_dispositions),
            "classified_count": len(offspring_dispositions),
            "reconciles_to_total": sum(disposition_summary.values()) == len(offspring_dispositions),
            "rule_id": OFFSPRING_DISPOSITION_RULE_ID,
        })
        weights = [r for r in weights_all if _text(r.get("pig_id")) in {_text(c.get("pig_id")) for c in offspring} and _number(r.get("weight_kg")) is not None]
        partner_key = "boar_pig_id" if key == "sow_pig_id" else "sow_pig_id"
        pairings = []
        for partner in partners:
            pair_cohorts = [r for r in cohorts if _text(r.get(partner_key)) == partner]
            pair_eligible = [governed_litter_outcome(r) for r in pair_cohorts]
            pair_eligible = [(r["born_alive"], r["weaned_count"]) for r in pair_eligible if r["eligible"]]
            pair_born = sum(b for b, _ in pair_eligible) if pair_eligible else None
            pair_weaned = sum(w for _, w in pair_eligible) if pair_eligible else None
            pairings.append({
                "partner_pig_id": partner, "observed_litter_count": len(pair_cohorts),
                "eligible_litter_count": len(pair_eligible),
                "survival_rate": pair_weaned / pair_born if pair_born else None,
            })
        trend = [{
            "period": _date(r.get("farrowing_date")).isoformat() if _date(r.get("farrowing_date")) else None,
            "litter_id": _text(r.get("litter_id")),
            "survival_rate": governed_litter_outcome(r)["survival_rate"],
        } for r in cohorts]
        return {
            "identity": identity,
            "breeding_role": role,
            "detail_href": f"/breeding-analytics/{pid}" if pid else None,
            "litter_outcomes": survival,
            "breeding_opportunities": {
                "observed_count": len(opportunities),
                "eligible_complete_through_count": len(complete_opportunities),
                "missing_outcome_count": len(opportunities) - len(complete_opportunities),
            },
            "time_trend": trend,
            "offspring": {
                "sample_size": len(offspring),
                "pig_ids": sorted(_text(c.get("pig_id")) for c in offspring),
                "dispositions": offspring_dispositions,
                "disposition_summary": disposition_summary,
            },
            "offspring_growth": {"observed_weight_count": len(weights), "median_weight_kg": None, "comparable_window": None, "limitation": "Comparable-age or days-since-weaning binding is not yet supported by complete evidence."},
            "partner_pig_ids": partners,
            "partner_comparisons": pairings,
            "family_relationships": {
                "dam_pig_id": _text(parent.get("mother_pig_id") or parent.get("dam_pig_id")) or None,
                "sire_pig_id": _text(parent.get("father_pig_id") or parent.get("sire_pig_id")) or None,
                "offspring_pig_ids": sorted(_text(c.get("pig_id")) for c in offspring),
            },
            "health_observation_context": {
                "observations": [r for r in observations if _text(r.get("pig_id")) == pid],
                "medical_events": [r for r in medical_all if _text(r.get("pig_id")) == pid],
            },
            "financial_outcomes": {"gross_attributable": None, "net_settlement_attributable": None, "margin": None, "limitation": "No exact item-to-animal attribution composed in v1."},
            "confidence": confidence,
            "interpretation": _interpretation(identity, survival, confidence),
            "evidence_lineage": {
                "litter_ids": sorted(_text(r.get("litter_id")) for r in cohorts),
                "observation_event_ids": sorted(_text(r.get("observation_event_id")) for r in observations if _text(r.get("pig_id")) == pid),
                "lifecycle_event_ids": sorted(_text(r.get("lifecycle_event_id")) for r in lifecycle if _text(r.get("pig_id")) == pid),
            },
        }

    parent_ids = {
        _text(row.get(field)) for row in litters + matings_all
        for field in ("sow_pig_id", "boar_pig_id") if row.get(field)
    }
    breeding = [p for p in pigs if (
        _text(p.get("pig_id")) in parent_ids
        or _text(p.get("animal_type")).lower() in {"sow", "boar"}
        or _text(p.get("purpose")).lower() == "breeding"
    )]
    all_rows = sorted((row_for(p) for p in breeding), key=lambda r: (r["identity"]["display_name"].lower(), r["identity"]["pig_id"]))
    rates = [r["litter_outcomes"]["rate"] for r in all_rows if r["litter_outcomes"]["rate"] is not None]
    benchmark = {
        "survival_rate_median": median(rates) if rates else None,
        "eligible_parent_count": len(rates),
        "displayed_parent_count": len(all_rows),
        "missing_parent_count": len(all_rows) - len(rates),
    }
    for row in all_rows:
        row["herd_benchmark"] = benchmark
    rows = all_rows
    if pig_id is not None:
        rows = [row for row in rows if row["identity"]["pig_id"] == _text(pig_id)]
        if not rows:
            return {"success": False, "contract_version": CONTRACT_VERSION, "reason": "unknown_pig_id", "writes_performed": False}
        attributable_pigs = {rows[0]["identity"]["pig_id"], *rows[0]["offspring"]["pig_ids"]}
        attributable_litters = set(rows[0]["evidence_lineage"]["litter_ids"])
        attributable_superseded = {
            _text(r.get("supersedes_litter_id")) for r in litters_raw
            if _text(r.get("litter_id")) in attributable_litters and r.get("supersedes_litter_id")
        }
        litter_lineage["events"] = [r for r in litter_lineage["events"] if (
            _text(r.get("litter_id")) in attributable_litters | attributable_superseded
            or _text(r.get("retained_litter_id")) in attributable_litters
        )]
        litter_lineage["superseded_event_ids"] = sorted(attributable_superseded | {
            _text(r.get("litter_id")) for r in litter_lineage["events"]
            if r.get("is_superseded") is True
        })
        observation_lineage["events"] = [r for r in observation_lineage["events"] if _text(r.get("pig_id")) in attributable_pigs]
        lifecycle_lineage["events"] = [r for r in lifecycle_lineage["events"] if _text(r.get("pig_id")) in attributable_pigs]
        observation_lineage["superseded_event_ids"] = sorted({_text(r.get("supersedes_observation_event_id")) for r in observation_lineage["events"] if r.get("supersedes_observation_event_id")})
        lifecycle_lineage["superseded_event_ids"] = sorted({_text(r.get("supersedes_lifecycle_event_id")) for r in lifecycle_lineage["events"] if r.get("supersedes_lifecycle_event_id")})
    return {
        "success": True,
        "contract_version": CONTRACT_VERSION,
        "evidence_cutoff": cutoff.isoformat() if cutoff else None,
        "scope": "named_animal" if pig_id is not None else "herd",
        "rows": rows,
        "row_count": len(rows),
        "herd_benchmarks": benchmark,
        "lineage": {"litters": litter_lineage, "observations": observation_lineage, "lifecycle": lifecycle_lineage},
        "data_quality": {
            "undated_litter_rows": sum(not _date(r.get("farrowing_date")) for r in litters_raw),
            "undated_observation_rows": sum(not _date(r.get("observed_at")) for r in observations_raw),
            "undated_lifecycle_rows": sum(not _date(r.get("effective_at")) for r in lifecycle_raw),
        },
        "association_boundary": "Parent-associated outcomes are associations qualified by management, health, season, feed, environment and evidence gaps; they do not prove genetic causation.",
        "writes_performed": False,
    }
