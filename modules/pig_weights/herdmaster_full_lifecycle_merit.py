"""Read-only full-lifecycle genetic-merit evidence projection.

This module reports attributable associations.  It never asserts genetic
causation and never writes farm state.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from statistics import median
from urllib.parse import quote, unquote, urlencode


CONTRACT_VERSION = "herdmaster_full_lifecycle_merit_v1"
CONFIDENCE_RULE_ID = "herdmaster_merit_confidence_v1"


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


def _safe_internal_path(path):
    value = _text(path)
    if (not value.startswith("/") or value.startswith("//") or "\\" in value
            or any(ord(character) < 32 or ord(character) == 127 for character in value)):
        return None
    return value


def _safe_route_segment(value):
    raw = _text(value)
    if not raw:
        return None
    decoded = raw
    for _ in range(3):
        next_value = unquote(decoded)
        if next_value == decoded:
            break
        decoded = next_value
    if (decoded in {".", ".."} or "/" in decoded or "\\" in decoded
            or any(ord(character) < 32 or ord(character) == 127 for character in decoded)):
        return None
    return raw


def _destination(route_identity, path, accessible_label, *, return_path=None):
    safe_path = _safe_internal_path(path)
    safe_return = _safe_internal_path(return_path) if return_path else None
    if return_path is not None and safe_return is None:
        safe_path = None
    if safe_path and safe_return:
        safe_path = safe_path + "?" + urlencode({
            "return_to": safe_return,
            "return_label": "Back to animal analytics",
        })
    return {
        "route_identity": route_identity,
        "href": safe_path,
        "accessible_label": accessible_label,
        "available": safe_path is not None,
        "unavailable_reason": None if safe_path else "validated_internal_destination_unavailable",
    }


def _identity(row=None, *, pig_id=None, role=None, canonical_resolved=True):
    row = row or {}
    pig_id = _text(row.get("pig_id") or pig_id)
    name = _text(row.get("name") or row.get("pig_name"))
    tag = _text(row.get("tag_number"))
    primary = name or tag or "Unknown"
    presentation_state = "named" if name else ("tag_fallback" if tag else "unknown")
    animal_type = _text(row.get("animal_type")) or None
    resolved_role = _text(role) or animal_type or None
    route_segment = _safe_route_segment(pig_id)
    destination = _destination(
        "breeding_animal_detail",
        f"/breeding-analytics/{quote(route_segment, safe='')}"
        if route_segment and canonical_resolved else "",
        f"Open {primary} animal analytics",
    )
    if pig_id and not canonical_resolved:
        destination["unavailable_reason"] = "canonical_animal_identity_unresolved"
    elif pig_id and not route_segment:
        destination["unavailable_reason"] = "unsafe_route_identity"
    return {
        "name": name or None,
        "tag_number": tag or None,
        "pig_id": pig_id,
        "display_name": primary,
        "secondary_identity": tag if name and tag else None,
        "presentation_state": presentation_state,
        "technical_identity": {"pig_id": pig_id or None},
        "role": resolved_role,
        "animal_type": animal_type,
        "canonical_identity_resolved": bool(canonical_resolved),
        "destination": destination,
    }


def _effective(rows, id_key, supersedes_key):
    superseded = {_text(row.get(supersedes_key)) for row in rows if row.get(supersedes_key)}
    current = [row for row in rows if _text(row.get(id_key)) not in superseded]
    return current, {
        "event_count": len(rows),
        "superseded_event_ids": sorted(superseded),
        "events": rows,
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
    if cutoff:
        litters_all = [r for r in litters_raw if _date(r.get("farrowing_date")) and _date(r.get("farrowing_date")) <= cutoff]
        observations_all = [r for r in observations_raw if _date(r.get("observed_at")) and _date(r.get("observed_at")) <= cutoff]
        lifecycle_all = [r for r in lifecycle_raw if _date(r.get("effective_at")) and _date(r.get("effective_at")) <= cutoff]
        matings_all = [r for r in matings_all if _date(r.get("mating_date")) and _date(r.get("mating_date")) <= cutoff]
        weights_all = [r for r in weights_all if _date(r.get("weight_date")) and _date(r.get("weight_date")) <= cutoff]
        medical_all = [r for r in medical_all if _date(r.get("treatment_date")) and _date(r.get("treatment_date")) <= cutoff]
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
    pigs_by_id = {_text(row.get("pig_id")): row for row in pigs if _text(row.get("pig_id"))}
    for child in pigs:
        if child.get("litter_id"):
            offspring_by_litter[_text(child["litter_id"])].append(child)

    def resolved_identity(resolved_pig_id, *, role=None):
        canonical = pigs_by_id.get(_text(resolved_pig_id))
        return _identity(
            canonical,
            pig_id=resolved_pig_id,
            role=role,
            canonical_resolved=canonical is not None,
        )

    def resolved_litter_identity(litter, *, return_pig_id):
        litter_id = _text(litter.get("litter_id"))
        litter_segment = _safe_route_segment(litter_id)
        return_segment = _safe_route_segment(return_pig_id)
        sow_identity = resolved_identity(litter.get("sow_pig_id"), role="sow")
        destination = _destination(
            "litter_detail",
            f"/litter/{quote(litter_segment, safe='')}" if litter_segment else "",
            f"Open litter {litter_id}" if litter_id else "Litter detail unavailable",
            return_path=(
                f"/breeding-analytics/{quote(return_segment, safe='')}"
                if return_segment else ("" if return_pig_id is not None else None)
            ),
        )
        return {
            "litter_id": litter_id or None,
            "display_name": litter_id or "Unknown",
            "presentation_state": "identified" if litter_id else "unknown",
            "technical_identity": {"litter_id": litter_id or None},
            "sow_identity": sow_identity,
            "destination": destination,
        }

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
        pid = _text(parent.get("pig_id"))
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
        identity = _identity(parent, role=role)
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
        weights = [r for r in weights_all if _text(r.get("pig_id")) in {_text(c.get("pig_id")) for c in offspring} and _number(r.get("weight_kg")) is not None]
        partner_key = "boar_pig_id" if key == "sow_pig_id" else "sow_pig_id"
        pairings = []
        for partner in partners:
            pair_cohorts = [r for r in cohorts if _text(r.get(partner_key)) == partner]
            pair_eligible = [governed_litter_outcome(r) for r in pair_cohorts]
            pair_eligible = [(r["born_alive"], r["weaned_count"]) for r in pair_eligible if r["eligible"]]
            pair_born = sum(b for b, _ in pair_eligible) if pair_eligible else None
            pair_weaned = sum(w for _, w in pair_eligible) if pair_eligible else None
            partner_identity = resolved_identity(
                partner, role="boar" if key == "sow_pig_id" else "sow")
            pairings.append({
                "partner_pig_id": partner, "observed_litter_count": len(pair_cohorts),
                "eligible_litter_count": len(pair_eligible),
                "survival_rate": pair_weaned / pair_born if pair_born else None,
                "partner_identity": partner_identity,
                "destination": partner_identity["destination"],
            })
        trend = []
        for litter in cohorts:
            litter_identity = resolved_litter_identity(litter, return_pig_id=pid)
            trend.append({
                "period": _date(litter.get("farrowing_date")).isoformat() if _date(litter.get("farrowing_date")) else None,
                "litter_id": _text(litter.get("litter_id")),
                "litter_identity": litter_identity,
                "sow_identity": litter_identity["sow_identity"],
                "destination": litter_identity["destination"],
                "survival_rate": governed_litter_outcome(litter)["survival_rate"],
            })
        offspring_identities = sorted(
            (resolved_identity(child.get("pig_id"), role="offspring") for child in offspring),
            key=lambda item: (item["display_name"].lower(), item["pig_id"]),
        )
        dam_identity = resolved_identity(
            parent.get("mother_pig_id") or parent.get("dam_pig_id"), role="dam")
        sire_identity = resolved_identity(
            parent.get("father_pig_id") or parent.get("sire_pig_id"), role="sire")
        return {
            "identity": identity,
            "breeding_role": role,
            "detail_href": identity["destination"]["href"],
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
                "identities": offspring_identities,
            },
            "offspring_growth": {"observed_weight_count": len(weights), "median_weight_kg": None, "comparable_window": None, "limitation": "Comparable-age or days-since-weaning binding is not yet supported by complete evidence."},
            "partner_pig_ids": partners,
            "partner_comparisons": pairings,
            "family_relationships": {
                "dam_pig_id": _text(parent.get("mother_pig_id") or parent.get("dam_pig_id")) or None,
                "sire_pig_id": _text(parent.get("father_pig_id") or parent.get("sire_pig_id")) or None,
                "offspring_pig_ids": sorted(_text(c.get("pig_id")) for c in offspring),
                "dam_identity": dam_identity,
                "sire_identity": sire_identity,
                "offspring_identities": offspring_identities,
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
        "identity_contract_version": "herdmaster_human_identity_v1",
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
