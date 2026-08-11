"""Pure lifetime genetic-merit evidence and pair-profile contracts.

Inputs are already-authorized canonical rows.  This module performs no I/O,
creates no recommendation delivery, and grants no mating or farm authority.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import date

CONTRACT_VERSION = "herdmaster_lifetime_genetic_merit_v1"
GROWTH_WINDOWS = (30, 60, 90)
TERMINAL_FAILURES = {"not_pregnant", "failed", "aborted", "repeat_required"}


def build_lifetime_outcome_packet(evidence, *, cutoff):
    """Build exact-pair, sow and boar outcome evidence at one cutoff."""
    if not isinstance(cutoff, date) or not isinstance(evidence, dict):
        return _unavailable("valid_evidence_and_cutoff_required")
    required = ("matings", "litters", "pigs", "weight_events")
    if any(not isinstance(evidence.get(key), list) for key in required):
        return _unavailable("canonical_mating_litter_pig_and_weight_rows_required")
    pigs = _unique(evidence["pigs"], "pig_id")
    litters = _unique(evidence["litters"], "litter_id")
    matings = _unique(evidence["matings"], "mating_id")
    if pigs is None or litters is None or matings is None:
        return _unavailable("canonical_identity_missing_or_duplicated")

    superseded_litters = set(map(str, evidence.get("superseded_litter_ids") or ()))
    superseded_pigs = set(map(str, evidence.get("superseded_pig_ids") or ()))
    current_litters = {key: row for key, row in litters.items() if key not in superseded_litters}
    current_pigs = {key: row for key, row in pigs.items() if key not in superseded_pigs}
    children_by_litter = defaultdict(list)
    for pig_id, row in current_pigs.items():
        litter_id = _text(row.get("litter_id"))
        if litter_id in current_litters:
            children_by_litter[litter_id].append({**row, "pig_id": pig_id})
    weights = defaultdict(list)
    for row in evidence["weight_events"]:
        pig_id, observed = _text(row.get("pig_id")), _date(row.get("weight_date"))
        weight = _number(row.get("weight_kg"))
        if pig_id in current_pigs and observed and observed <= cutoff and weight is not None and weight > 0:
            weights[pig_id].append({**row, "weight_date": observed, "weight_kg": weight})
    for rows in weights.values():
        rows.sort(key=lambda row: (row["weight_date"], _text(row.get("weight_event_id"))))

    mating_by_id = dict(matings)
    cohorts, gaps = [], []
    for litter_id, litter in sorted(current_litters.items()):
        farrowing = _date(litter.get("farrowing_date"))
        if farrowing and farrowing > cutoff:
            continue
        sow_id, boar_id = _text(litter.get("sow_pig_id")), _text(litter.get("boar_pig_id"))
        mating_id = _text(litter.get("mating_id") or litter.get("related_mating_id"))
        mating = mating_by_id.get(mating_id, {})
        if not sow_id or not boar_id:
            gaps.append(_gap("litter_parent_attribution", litter_id, "exact sow and boar identity"))
        if mating_id and (not mating or _text(mating.get("sow_pig_id")) != sow_id
                          or _text(mating.get("boar_pig_id")) != boar_id
                          or not _supports_farrowing(mating, farrowing)):
            gaps.append(_gap("mating_litter_link", litter_id, "non-conflicting exact mating, sow, boar and chronology"))
            mating_id, mating = "", {}
        elif not mating_id:
            candidates = [row for row in matings.values() if _text(row.get("sow_pig_id")) == sow_id
                          and _text(row.get("boar_pig_id")) == boar_id and _supports_farrowing(row, farrowing)]
            if len(candidates) == 1:
                mating = candidates[0]
                mating_id = _text(mating.get("mating_id"))
            else:
                gaps.append(_gap("mating_litter_link", litter_id, "one attributable mating/exposure"))
        children = sorted(children_by_litter[litter_id], key=lambda row: row["pig_id"])
        cohort = _cohort(litter_id, litter, mating_id, mating, children, weights, evidence, cutoff)
        cohorts.append(cohort)
        gaps.extend(cohort.pop("gaps"))

    opportunities = _opportunities(matings.values(), cohorts, cutoff)
    pair_keys = sorted({(row["sow_pig_id"], row["boar_pig_id"]) for row in cohorts if row["sow_pig_id"] and row["boar_pig_id"]}
                       | {(row["sow_pig_id"], row["boar_pig_id"]) for row in opportunities if row["sow_pig_id"] and row["boar_pig_id"]})
    pair_profiles = [_aggregate("pair", sow, boar, cohorts, opportunities) for sow, boar in pair_keys]
    sow_profiles = [_aggregate("sow", sow, None, cohorts, opportunities)
                    for sow in sorted({row["sow_pig_id"] for row in cohorts + opportunities if row["sow_pig_id"]})]
    boar_profiles = [_aggregate("boar", None, boar, cohorts, opportunities)
                     for boar in sorted({row["boar_pig_id"] for row in cohorts + opportunities if row["boar_pig_id"]})]
    material = {"cutoff": cutoff.isoformat(), "cohorts": cohorts, "opportunities": opportunities,
                "pair_profiles": pair_profiles, "sow_profiles": sow_profiles, "boar_profiles": boar_profiles,
                "attribution_gaps": sorted(gaps, key=lambda row: (row["source_family"], row["identity"]))}
    digest = _digest(material)
    return {"success": True, "contract_version": CONTRACT_VERSION,
            "packet_id": f"HERD-LIFETIME-{digest[:32].upper()}", "evidence_digest": digest,
            **material, "writes_performed": False, "delivery_enabled": False,
            "mating_execution_enabled": False, "protected_actions_performed": False}


def build_explainable_pair_profiles(packet, *, females, boars, relationships=(), controlled_trial_capacity=1):
    """Apply lifetime evidence to eligible candidates without creating a mating."""
    if not isinstance(packet, dict) or packet.get("success") is not True:
        return _unavailable("lifetime_packet_required")
    female_rows, boar_rows = _unique(females, "pig_id"), _unique(boars, "pig_id")
    if female_rows is None or boar_rows is None:
        return _unavailable("unique_candidate_identity_required")
    pair_evidence = {(row["sow_pig_id"], row["boar_pig_id"]): row for row in packet["pair_profiles"]}
    sow_evidence = {row["sow_pig_id"]: row for row in packet["sow_profiles"]}
    boar_evidence = {row["boar_pig_id"]: row for row in packet["boar_profiles"]}
    relation = {(_text(row.get("sow_pig_id")), _text(row.get("boar_pig_id"))): row for row in relationships}
    profiles = []
    for sow_id, female in sorted(female_rows.items()):
        for boar_id, boar in sorted(boar_rows.items()):
            exact = pair_evidence.get((sow_id, boar_id), _empty_aggregate("pair", sow_id, boar_id))
            sow = sow_evidence.get(sow_id, _empty_aggregate("sow", sow_id, None))
            across = boar_evidence.get(boar_id, _empty_aggregate("boar", None, boar_id))
            rel = relation.get((sow_id, boar_id), {})
            exclusions = _pair_exclusions(female, boar, rel)
            evidence_class = _evidence_class(exact, sow, across, boar, exclusions)
            profiles.append({"sow_pig_id": sow_id, "sow_name": _name(female),
                             "boar_pig_id": boar_id, "boar_name": _name(boar),
                             "classification": evidence_class,
                             "excluded": bool(exclusions), "exclusion_reasons": exclusions,
                             "axes": _axes(exact), "exact_pair": exact,
                             "sow_evidence": sow, "boar_across_sows": across,
                             "reasons": _reasons(exact, sow, across, evidence_class),
                             "unknowns": _profile_unknowns(exact), "mating_action_prohibited": True})
    rankings = _rank_by_female(profiles)
    allocations = _allocate_trials(profiles, female_rows, boar_rows, controlled_trial_capacity)
    material = {"lifetime_packet_id": packet["packet_id"], "profiles": profiles,
                "female_rankings": rankings, "controlled_trials": allocations}
    digest = _digest(material)
    return {"success": True, "contract_version": CONTRACT_VERSION,
            "profile_packet_id": f"HERD-PAIR-{digest[:32].upper()}", **material,
            "writes_performed": False, "delivery_enabled": False,
            "mating_execution_enabled": False, "protected_actions_performed": False}


def _cohort(litter_id, litter, mating_id, mating, children, weights, evidence, cutoff):
    born_alive = _integer(litter.get("born_alive")); weaned = _integer(litter.get("weaned_count"))
    total_born = _integer(litter.get("total_born")); gaps = []
    if born_alive is None: gaps.append(_gap("litter_outcome", litter_id, "born-alive count"))
    if weaned is None: gaps.append(_gap("weaning_outcome", litter_id, "governed weaned count"))
    wean_weights = [float(row["wean_weight_kg"]) for row in children if _number(row.get("wean_weight_kg")) is not None]
    expected_wean_weights = weaned if weaned is not None else sum(bool(_date(row.get("wean_date"))) for row in children)
    growth = {window: [] for window in GROWTH_WINDOWS}
    count_conflict = bool(total_born is not None and born_alive is not None and born_alive > total_born)
    count_conflict = count_conflict or bool(born_alive is not None and weaned is not None and weaned > born_alive)
    if count_conflict: gaps.append(_gap("litter_count_chronology", litter_id, "non-conflicting total-born, born-alive and weaned counts"))
    deaths = {"stillborn": 0, "pre_weaning": 0, "post_weaning": 0, "undated": 0}
    destinations = defaultdict(int)
    for child in children:
        wean_date = _date(child.get("wean_date"))
        for window in GROWTH_WINDOWS:
            rate = _growth_at_window(child, weights.get(child["pig_id"], []), wean_date, window)
            if rate is not None: growth[window].append(rate)
        exit_date = _date(child.get("exit_date")); reason = _norm(child.get("exit_reason"))
        if reason == "stillborn":
            deaths["stillborn"] += 1
        elif reason in {"died", "death", "dead", "crushed"}:
            if not exit_date: deaths["undated"] += 1
            elif wean_date and exit_date >= wean_date: deaths["post_weaning"] += 1
            else: deaths["pre_weaning"] += 1
        destinations[_destination(child)] += 1
    money = _financial(litter_id, children, evidence)
    survival = round(weaned * 100 / born_alive, 1) if born_alive and weaned is not None and not count_conflict else None
    return {"litter_id": litter_id, "mating_id": mating_id or None,
            "sow_pig_id": _text(litter.get("sow_pig_id")), "boar_pig_id": _text(litter.get("boar_pig_id")),
            "mating_date": _date_text(mating.get("mating_date")), "farrowing_date": _date_text(litter.get("farrowing_date")),
            "conception_outcome": "supported_by_attributable_farrowing" if mating_id else "Unknown",
            "total_born": total_born, "born_alive": born_alive, "weaned_count": weaned,
            "count_conflict": count_conflict,
            "survival_to_weaning_pct": survival, "child_count": len(children),
            "weaning_weight": _distribution(wean_weights, expected_wean_weights),
            "post_weaning_growth": {str(window): _distribution(values, expected_wean_weights) for window, values in growth.items()},
            "mortality": deaths, "destinations": dict(sorted(destinations.items())),
            "financial": money, "gaps": gaps}


def _opportunities(matings, cohorts, cutoff):
    litter_matings = {row["mating_id"] for row in cohorts if row["mating_id"]}
    rows = []
    for mating in sorted(matings, key=lambda row: (_date(row.get("mating_date")) or date.min, _text(row.get("mating_id")))):
        mating_date = _date(mating.get("mating_date"))
        if not mating_date or mating_date > cutoff: continue
        mating_id = _text(mating.get("mating_id")); outcome = _norm(mating.get("outcome"))
        if mating_id in litter_matings: state = "supported_conception"
        elif outcome in TERMINAL_FAILURES: state = "recorded_non_conception"
        else: state = "Unknown"
        rows.append({"mating_id": mating_id, "sow_pig_id": _text(mating.get("sow_pig_id")),
                     "boar_pig_id": _text(mating.get("boar_pig_id")), "mating_date": mating_date.isoformat(),
                     "outcome_state": state, "complete_through": bool(mating.get("outcome_complete"))})
    return rows


def _aggregate(kind, sow_id, boar_id, cohorts, opportunities):
    matched = [row for row in cohorts if (sow_id is None or row["sow_pig_id"] == sow_id)
               and (boar_id is None or row["boar_pig_id"] == boar_id)]
    opp = [row for row in opportunities if (sow_id is None or row["sow_pig_id"] == sow_id)
           and (boar_id is None or row["boar_pig_id"] == boar_id)]
    born = sum(row["born_alive"] for row in matched if row["born_alive"] is not None)
    weaned = sum(row["weaned_count"] for row in matched if row["weaned_count"] is not None)
    survival_complete = bool(matched) and all(row["born_alive"] is not None and row["weaned_count"] is not None for row in matched)
    conception_complete = bool(opp) and all(row["outcome_state"] != "Unknown" and row["complete_through"] for row in opp)
    return {"profile_kind": kind, "sow_pig_id": sow_id, "boar_pig_id": boar_id,
            "opportunity_count": len(opp), "attributable_litter_count": len(matched),
            "conception_supported_count": sum(row["outcome_state"] == "supported_conception" for row in opp),
            "conception_rate_pct": round(sum(row["outcome_state"] == "supported_conception" for row in opp) * 100 / len(opp), 1) if conception_complete else None,
            "born_alive": born if matched else None, "weaned_count": weaned if matched else None,
            "survival_to_weaning_pct": round(weaned * 100 / born, 1) if survival_complete and born else None,
            "weaning_weight_coverage": sum(row["weaning_weight"]["covered"] for row in matched),
            "growth_coverage_60d": sum(row["post_weaning_growth"]["60"]["covered"] for row in matched),
            "post_weaning_deaths": sum(row["mortality"]["post_weaning"] for row in matched),
            "financial_individual_value": round(sum(row["financial"]["attributable_individual_value"] for row in matched), 2),
            "financial_lot_value_unallocated": round(sum(row["financial"]["lot_value_unallocated"] for row in matched), 2),
            "coverage": {"conception_complete": conception_complete, "survival_complete": survival_complete,
                         "financial_cost_complete": bool(matched) and all(row["financial"]["cost_coverage_complete"] for row in matched)}}


def _financial(litter_id, children, evidence):
    child_ids = {row["pig_id"] for row in children}; items = evidence.get("sales_items") or []
    sales = {_text(row.get("sale_id")): row for row in evidence.get("sales_transactions") or []}
    individual = 0.0; sale_ids = set()
    for item in items:
        if _text(item.get("pig_id")) in child_ids:
            sale_ids.add(_text(item.get("sale_id")))
            if _number(item.get("line_total")) is not None: individual += _number(item.get("line_total"))
    attributable_lot_ids, external_lot_ids = [], []
    for sale_id in sorted(sale_ids):
        pig_items = [item for item in items if _text(item.get("sale_id")) == sale_id and _text(item.get("pig_id"))]
        if pig_items and all(_text(item.get("pig_id")) in child_ids for item in pig_items):
            attributable_lot_ids.append(sale_id)
        else:
            external_lot_ids.append(sale_id)
    lot_unallocated = sum(_number(sales[sale_id].get("net_total")) or 0 for sale_id in attributable_lot_ids
                          if sale_id in sales and not any(_text(item.get("sale_id")) == sale_id and _number(item.get("line_total")) is not None for item in items))
    costs = [row for row in evidence.get("attributable_costs") or [] if _text(row.get("litter_id")) == litter_id]
    transaction_evidence = [_financial_truth(sales[sale_id]) for sale_id in sorted(sale_ids) if sale_id in sales]
    return {"attributable_individual_value": round(individual, 2), "lot_value_unallocated": round(lot_unallocated, 2),
            "cost_total": round(sum(_number(row.get("amount")) or 0 for row in costs), 2) if costs else None,
            "cost_coverage_complete": bool(costs) and all(row.get("coverage_complete") is True for row in costs),
            "profit_or_margin": None, "attributable_lot_ids": attributable_lot_ids,
            "mixed_or_external_lot_ids": external_lot_ids, "transaction_evidence": transaction_evidence,
            "provenance": "individual sale items only; lot totals retained without invented allocation"}


def _growth_at_window(child, events, wean_date, window):
    baseline = _number(child.get("wean_weight_kg"))
    if not wean_date or baseline is None: return None
    candidates = [(abs((row["weight_date"] - wean_date).days - window), row) for row in events
                  if window - 7 <= (row["weight_date"] - wean_date).days <= window + 7]
    if not candidates: return None
    _, row = min(candidates, key=lambda item: (item[0], item[1]["weight_date"], _text(item[1].get("weight_event_id"))))
    elapsed = (row["weight_date"] - wean_date).days
    return round((row["weight_kg"] - baseline) / elapsed, 3) if elapsed > 0 else None


def _pair_exclusions(female, boar, relation):
    reasons = []
    if female.get("eligible") is not True: reasons.append(_text(female.get("hold_reason")) or "female not currently eligible")
    if boar.get("available") is not True: reasons.append(_text(boar.get("hold_reason")) or "boar unavailable")
    if _norm(relation.get("status")) in {"excluded", "conflicting", "unsafe"}: reasons.extend(relation.get("reasons") or ["known relationship conflict"])
    return sorted(set(reasons))


def _evidence_class(exact, sow, across, boar, exclusions):
    if exclusions: return "Held/excluded"
    if exact["attributable_litter_count"] >= 2 and exact["coverage"]["survival_complete"]: return "Proven repeat"
    if exact["attributable_litter_count"] >= 1: return "Supported cross"
    if across["attributable_litter_count"] == 0 and boar.get("controlled_trial_eligible") is True and sow["attributable_litter_count"] >= 1: return "Controlled trial"
    if sow["attributable_litter_count"] and across["attributable_litter_count"]: return "Corrective cross"
    return "Limited evidence"


def _axes(row):
    return {"reproductive_reliability": _axis(row["conception_rate_pct"], row["coverage"]["conception_complete"]),
            "litter_productivity": _axis(row["born_alive"], row["attributable_litter_count"] > 0),
            "survival_robustness": _axis(row["survival_to_weaning_pct"], row["coverage"]["survival_complete"]),
            "weaning_quality": _axis(row["weaning_weight_coverage"], row["weaning_weight_coverage"] > 0),
            "post_weaning_growth": _axis(row["growth_coverage_60d"], row["growth_coverage_60d"] > 0),
            "later_mortality": _axis(row["post_weaning_deaths"], row["attributable_litter_count"] > 0),
            "financial_outcome": _axis(row["financial_individual_value"], row["coverage"]["financial_cost_complete"])}


def _allocate_trials(profiles, females, boars, capacity):
    if not isinstance(capacity, int) or capacity < 0: capacity = 0
    candidates = [row for row in profiles if row["classification"] == "Controlled trial" and not row["excluded"]]
    candidates.sort(key=lambda row: (-row["sow_evidence"]["attributable_litter_count"],
                                     -row["sow_evidence"]["weaned_count"] if row["sow_evidence"]["weaned_count"] is not None else 0,
                                     row["sow_name"], row["boar_name"]))
    return [{"sow_pig_id": row["sow_pig_id"], "sow_name": row["sow_name"],
             "boar_pig_id": row["boar_pig_id"], "boar_name": row["boar_name"],
             "classification": "Controlled trial",
             "reason": "Well-documented maternal history makes the unproven boar's future fertility, litter, survival, weaning and growth contribution interpretable.",
             "future_evidence": ["supported conception", "born alive", "survival to weaning", "weaning weight", "comparable post-weaning growth"]}
            for row in candidates[:capacity]]


def _rank_by_female(profiles):
    class_order = {"Proven repeat": 0, "Supported cross": 1, "Corrective cross": 2,
                   "Limited evidence": 3, "Controlled trial": 4, "Held/excluded": 9}
    grouped = defaultdict(list)
    for row in profiles:
        grouped[row["sow_pig_id"]].append(row)
    result = []
    for sow_id, rows in sorted(grouped.items()):
        eligible = [row for row in rows if not row["excluded"] and row["classification"] != "Controlled trial"]
        eligible.sort(key=lambda row: (
            class_order[row["classification"]],
            -row["exact_pair"]["attributable_litter_count"],
            -(row["exact_pair"]["survival_to_weaning_pct"] or -1),
            -row["boar_across_sows"]["attributable_litter_count"],
            row["boar_name"], row["boar_pig_id"],
        ))
        result.append({"sow_pig_id": sow_id,
                       "primary_boar_pig_id": eligible[0]["boar_pig_id"] if eligible else None,
                       "reserve_boar_pig_id": eligible[1]["boar_pig_id"] if len(eligible) > 1 else None,
                       "ranked_boar_ids": [row["boar_pig_id"] for row in eligible],
                       "ranking_rule": "evidence class, exact-pair sample and survival, then boar evidence across sows; workload is not genetic merit"})
    return result


def _financial_truth(row):
    fields = ("sale_id", "sale_date", "sale_stream", "sale_channel", "gross_total", "output_vat",
              "gross_including_vat", "commission_ex_vat", "commission_input_vat",
              "commission_including_vat", "other_deductions", "net_total",
              "net_settlement_payable", "received_total", "payment_status", "payment_date")
    return {field: row.get(field) for field in fields if row.get(field) is not None}


def _reasons(exact, sow, across, classification):
    reasons = [f"{exact['attributable_litter_count']} attributable exact-pair litter(s)."]
    if exact["survival_to_weaning_pct"] is not None: reasons.append(f"Exact-pair survival to weaning {exact['survival_to_weaning_pct']}%.")
    if classification == "Controlled trial": reasons.append("Boar has no attributable litter outcome; limited evidence is not an exclusion.")
    if exact["financial_lot_value_unallocated"]: reasons.append("Lot-level value is retained without inventing individual proceeds.")
    return reasons


def _profile_unknowns(row):
    unknowns = []
    if not row["coverage"]["conception_complete"]: unknowns.append("complete-through conception opportunity coverage")
    if not row["coverage"]["survival_complete"]: unknowns.append("complete litter survival/weaning coverage")
    if not row["weaning_weight_coverage"]: unknowns.append("attributable weaning weights")
    if not row["growth_coverage_60d"]: unknowns.append("comparable 60-day post-weaning growth")
    if not row["coverage"]["financial_cost_complete"]: unknowns.append("attributable cost coverage")
    return unknowns


def _distribution(values, expected):
    values = sorted(round(float(value), 3) for value in values)
    return {"covered": len(values), "missing": max(expected - len(values), 0),
            "mean": round(sum(values) / len(values), 3) if values else None,
            "median": values[len(values)//2] if len(values) % 2 else round((values[len(values)//2-1]+values[len(values)//2])/2, 3) if values else None,
            "minimum": values[0] if values else None, "maximum": values[-1] if values else None}


def _destination(child):
    status, reason, purpose = _norm(child.get("status")), _norm(child.get("exit_reason")), _norm(child.get("purpose"))
    if status == "sold" and "auction" in reason: return "auction"
    if status == "sold": return "livestock_sale"
    if status in {"slaughtered", "processed"}: return "slaughter_or_meat"
    if status in {"dead", "died"}: return "death"
    if purpose == "breeding" and status == "active": return "breeding_retention"
    if status == "active": return "active_growing"
    return "Unknown"


def _supports_farrowing(mating, farrowing):
    mating_date = _date(mating.get("mating_date"))
    return bool(mating_date and farrowing and 100 <= (farrowing - mating_date).days <= 130)


def _empty_aggregate(kind, sow, boar):
    return _aggregate(kind, sow, boar, [], [])


def _axis(value, complete): return {"value": value if complete else None, "coverage_complete": complete, "status": "Measured" if complete else "Unknown"}
def _gap(family, identity, missing): return {"source_family": family, "identity": identity, "missing": missing, "status": "Unknown"}
def _name(row): return _text(row.get("name") or row.get("pig_name") or row.get("tag_number") or row.get("pig_id"))
def _text(value): return "" if value is None else str(value).strip()
def _norm(value): return _text(value).lower().replace(" ", "_")
def _date(value):
    if isinstance(value, date): return value
    try: return date.fromisoformat(_text(value)[:10])
    except ValueError: return None
def _date_text(value):
    parsed = _date(value); return parsed.isoformat() if parsed else None
def _number(value):
    try: return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError): return None
def _integer(value):
    number = _number(value); return int(number) if number is not None and number >= 0 and number.is_integer() else None
def _unique(rows, key):
    result = {}
    for row in rows:
        identity = _text(row.get(key))
        if not identity or identity in result: return None
        result[identity] = dict(row)
    return result
def _digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()
def _unavailable(reason): return {"success": False, "reason": reason, "contract_version": CONTRACT_VERSION,
                                  "writes_performed": False, "delivery_enabled": False,
                                  "mating_execution_enabled": False, "protected_actions_performed": False}
