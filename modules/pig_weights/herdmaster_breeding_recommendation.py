"""Pure evidence-qualified HERDMASTER sow-to-boar recommendation contract.

The evaluator consumes already-authorized canonical evidence.  It performs no
I/O and grants no observation, mating, medical, lifecycle, or delivery authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date


CONTRACT_VERSION = "herdmaster_breeding_recommendation_v1"
ACTIVE_CYCLES = {
    "recently_mated", "post_mating_monitoring", "assumed_pregnant",
    "confirmed_pregnant", "expected_to_farrow", "inconclusive",
}
WEIGHT_FRESH_DAYS = 30


def evaluate_breeding_attention(evidence, *, today=None):
    """Return a deterministic, zero-authority assessment for every female."""
    today = today or date.today()
    if not isinstance(evidence, dict):
        return _unavailable("evidence_not_supplied")
    females = evidence.get("females")
    boars = evidence.get("boars")
    if not isinstance(females, list) or not isinstance(boars, list):
        return _unavailable("complete_female_and_boar_inventories_required")
    female_ids = [_text(row.get("pig_id")) for row in females]
    boar_ids = [_text(row.get("pig_id")) for row in boars]
    if not all(female_ids + boar_ids) or len(set(female_ids + boar_ids)) != len(female_ids + boar_ids):
        return _unavailable("canonical_identity_missing_or_duplicated")
    if any(_norm(row.get("sex")) != "female" for row in females) or any(_norm(row.get("sex")) != "male" for row in boars):
        return _unavailable("inventory_sex_conflicts_with_breeding_role")

    cases = [_female_case(row, boars, evidence, today) for row in females]
    cases.sort(key=lambda row: (row["priority"], row["tag_number"].lower(), row["pig_id"]))
    boar_inventory = sorted((_boar_inventory(row, today) for row in boars), key=lambda row: (row["tag_number"].lower(), row["pig_id"]))
    material = {
        "contract_version": CONTRACT_VERSION,
        "reconciliation_digest": evidence.get("evidence_digest"),
        "cases": cases,
        "boar_inventory": boar_inventory,
    }
    digest = _digest(material)
    oom_packet = _oom_packet(cases, digest)
    return {
        "success": True,
        **material,
        "evidence_generation": evidence.get("evidence_generation"),
        "assessment_id": f"HERD-BREED-{digest[:32].upper()}",
        "material_evidence_digest": digest,
        "female_count": len(cases),
        "boar_count": len(boars),
        "english": _render(cases, "en"),
        "afrikaans": _render(cases, "af"),
        "oom_sakkie_packet": oom_packet,
        "delivery_enabled": False,
        "mating_execution_enabled": False,
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def _female_case(female, boars, evidence, today):
    pig_id = _text(female.get("pig_id"))
    cycle = female.get("current_cycle") if isinstance(female.get("current_cycle"), dict) else {}
    cycle_state = _norm(cycle.get("state") or "missing_evidence")
    welfare = set(evidence.get("active_welfare_pig_ids") or [])
    confirmed, observed, calculated, hypotheses, unknowns = _evidence_buckets(female, cycle, today)
    blockers = []
    state, action, priority = _state_action(female, cycle_state, pig_id in welfare)
    if cycle_state == "assumed_pregnant" and not _valid_assumed_pregnancy(female, cycle, evidence, today):
        state, action, priority = "missing_evidence", "Bind the visual observation to this sow and exact mating before pregnancy planning.", 12

    if state == "eligible_for_mating_review":
        blockers.extend(_female_eligibility_blockers(female, evidence, today))
        if blockers:
            state, action, priority = "missing_evidence", _next_action(blockers), 45
    rankings = [_pairing(female, boar, evidence, today) for boar in boars]
    rankings.sort(key=lambda row: (row["excluded"], -row["score"], row["tag_number"].lower(), row["pig_id"]))
    qualified = [row for row in rankings if not row["excluded"]]
    recommendation = qualified[0] if state == "eligible_for_mating_review" and qualified else None
    reserve = qualified[1] if state == "eligible_for_mating_review" and len(qualified) > 1 else None
    conditional_primary = qualified[0] if state in {"missing_evidence", "recovering"} and qualified else None
    conditional_reserve = qualified[1] if state in {"missing_evidence", "recovering"} and len(qualified) > 1 else None
    if state == "eligible_for_mating_review" and not qualified:
        action = "Resolve the listed pair-specific evidence; no boar is currently evidence-qualified."
    physical_only = bool(blockers) and all(_physical_blocker(item) for item in blockers)
    pairing_assessment = (
        "recommended" if recommendation
        else "possible_but_needs_one_observation" if state == "missing_evidence" and physical_only and qualified
        else "not_eligible"
    )
    question = _smallest_physical_question(female, state) if pairing_assessment == "possible_but_needs_one_observation" else None
    return {
        "pig_id": pig_id,
        "tag_number": _text(female.get("tag_number")) or pig_id,
        "state": state,
        "priority": priority,
        "next_action": action,
        "current_cycle": cycle,
        "confirmed_evidence": confirmed,
        "owner_observations": observed,
        "calculated_facts": calculated,
        "hypotheses": hypotheses,
        "unknowns": sorted(set(unknowns + blockers)),
        "smallest_physical_question": question,
        "pairing_assessment": pairing_assessment,
        "recommended_boar": recommendation,
        "reserve_boar": reserve,
        "conditional_primary_boar": conditional_primary,
        "conditional_reserve_boar": conditional_reserve,
        "owner_choice_required": False,
        "boar_assessments": rankings,
        "mating_action_prohibited": True,
    }


def _state_action(female, cycle_state, welfare_active):
    if welfare_active:
        return "held", "Continue the existing welfare lifecycle; do not open breeding work.", 1
    if _norm(female.get("status")) not in {"active"} or not _truth(female.get("on_farm")) or _norm(female.get("purpose")) != "breeding":
        return "unsuitable", "No breeding action; lifecycle, presence, or purpose excludes review.", 5
    if _norm(female.get("owner_hold")) in {"yes", "true", "hold", "active"}:
        return "held", "Respect the owner hold and reassess only when it is explicitly released.", 8
    if _norm(female.get("medical_status")) not in {"clear", "eligible"} or _norm(female.get("withdrawal_evidence_state")) == "hold":
        return "held", "Resolve the governed health or withdrawal hold before breeding review.", 10
    if cycle_state in ACTIVE_CYCLES:
        labels = {
            "assumed_pregnant": "assumed_pregnant", "confirmed_pregnant": "expected_to_farrow",
            "expected_to_farrow": "expected_to_farrow", "inconclusive": "inconclusive",
        }
        return labels.get(cycle_state, "already_mated"), _cycle_action(cycle_state), 15
    if cycle_state == "nursing":
        return "nursing", "Protect nursing work and reassess after governed weaning.", 20
    if cycle_state in {"post_weaning_recovery", "recovering"}:
        if _truth(female.get("recovery_cleared")):
            return "eligible_for_mating_review", "Review current heat and evidence-qualified boars; mating still requires separate approval.", 35
        return "recovering", "Complete the smallest post-weaning body-condition and soundness inspection.", 22
    if cycle_state in {"no_active_cycle", "eligible_for_mating_review"}:
        return "eligible_for_mating_review", "Review current heat and evidence-qualified boars; mating still requires separate approval.", 35
    return "missing_evidence", "Establish the current reproductive cycle before considering another mating.", 30


def _cycle_action(state):
    return {
        "recently_mated": "Continue post-mating monitoring; do not recommend another mating.",
        "post_mating_monitoring": "Continue post-mating monitoring; do not recommend another mating.",
        "assumed_pregnant": "Continue proportional farrowing preparation; this is not clinical confirmation.",
        "confirmed_pregnant": "Continue pregnancy and farrowing monitoring using the governed result.",
        "expected_to_farrow": "Continue farrowing preparation and monitoring.",
        "inconclusive": "Preserve the unresolved cycle and perform the scheduled reproductive-status reassessment.",
    }[state]


def _female_eligibility_blockers(row, evidence, today):
    blockers = []
    if _norm(row.get("withdrawal_evidence_state")) in {"hold", "active", "restricted"}:
        blockers.append("female has an active withdrawal restriction")
    if _norm(row.get("available_for_breeding")) in {"unavailable", "reserved", "held", "no", "false"}:
        blockers.append("female has an affirmative availability restriction")
    observations = row.get("observations") if isinstance(row.get("observations"), dict) else {}
    observed_age = _date_age(observations.get("observed_at"), today)
    for key, label in (("body_condition", "current body condition"), ("legs_sound", "current legs and movement"), ("visible_concern", "current visible concern check"), ("heat", "current heat observation")):
        if observations.get(key) in {None, "", "Unknown", "unknown"}:
            blockers.append(f"{label} is Unknown")
        elif observed_age is None or not 0 <= observed_age <= (2 if key == "heat" else 30):
            blockers.append(f"{label} is stale")
    if _norm(observations.get("heat")) not in {"observed", "standing", "standing_heat"} and observations.get("heat") not in {None, "", "Unknown", "unknown"}:
        blockers.append("standing heat is not currently observed")
    policy = evidence.get("policy") if isinstance(evidence.get("policy"), dict) else {}
    bcs = observations.get("body_condition")
    low, high = policy.get("breeding_body_condition_min"), policy.get("breeding_body_condition_max")
    if not isinstance(bcs, (int, float)) or not isinstance(low, (int, float)) or not isinstance(high, (int, float)) or not low <= bcs <= high:
        blockers.append("body condition is outside or lacks governed breeding bounds")
    if observations.get("legs_sound") is not True:
        blockers.append("legs and movement are not affirmatively sound")
    if _norm(observations.get("visible_concern")) not in {"none", "none_observed", "no_visible_concern"}:
        blockers.append("a visible concern is present or not safely classified")
    return blockers


def _pairing(female, boar, evidence, today):
    reasons, exclusions, limitations = [], [], []
    boar_id = _text(boar.get("pig_id"))
    if _norm(boar.get("status")) != "active" or not _truth(boar.get("on_farm")):
        exclusions.append("boar is not active and on farm")
    if _norm(boar.get("purpose")) != "breeding": exclusions.append("boar purpose is not Breeding")
    if _norm(boar.get("available_for_breeding")) in {"unavailable", "held", "no", "false"}: exclusions.append("boar has an affirmative availability restriction")
    elif _norm(boar.get("available_for_breeding")) not in {"available", "yes", "true"}: limitations.append("boar breeding availability negative coverage is incomplete")
    if _norm(boar.get("reservation_status")) in {"reserved", "allocated", "sold"}: exclusions.append("boar is reserved or allocated elsewhere")
    elif _norm(boar.get("reservation_status")) not in {"not_reserved", "unreserved", "available", "none"}: limitations.append("boar reservation negative coverage is incomplete")
    if boar.get("age_days") is None: limitations.append("boar age is Unknown")
    if "hold" in _norm(boar.get("medical_status")) or _norm(boar.get("medical_status")) in {"restricted", "unfit"}: exclusions.append("boar has an active health restriction")
    elif _norm(boar.get("medical_status")) not in {"clear", "eligible"}: limitations.append("boar health clearance coverage is incomplete")
    if _norm(boar.get("withdrawal_evidence_state")) in {"hold", "active", "restricted", "conflicting"}: exclusions.append("boar has an active or conflicting withdrawal restriction")
    elif _norm(boar.get("withdrawal_evidence_state")) not in {"cleared", "not_applicable"}: limitations.append("boar withdrawal negative coverage is incomplete")
    age = _weight_age(boar, today)
    if age is None or not 0 <= age <= WEIGHT_FRESH_DAYS: limitations.append("boar weight is missing, future-dated or stale")
    observations = boar.get("observations") if isinstance(boar.get("observations"), dict) else {}
    structure_age = _date_age(observations.get("observed_at"), today)
    if observations.get("legs_sound") is False: exclusions.append("boar legs are recorded unsound")
    elif observations.get("legs_sound") is not True: limitations.append("boar legs have no current affirmative observation")
    if observations.get("feet_sound") is False: exclusions.append("boar feet are recorded unsound")
    elif observations.get("feet_sound") is not True: limitations.append("boar feet have no current affirmative observation")
    if observations.get("build_acceptable") is False: exclusions.append("boar build is recorded unsuitable")
    elif observations.get("build_acceptable") is not True: limitations.append("boar build suitability is Unknown")
    if _norm(observations.get("visible_concern")) not in {"", "unknown", "none", "none_observed", "no_visible_concern"}: exclusions.append("boar has a recorded visible concern")
    elif structure_age is None or not 0 <= structure_age <= 30: limitations.append("boar structural-soundness evidence is stale or absent")
    relation = _relatedness(female, boar, evidence.get("pedigrees") or {})
    if relation["status"] == "conflict": exclusions.append(relation["reason"])
    elif relation["status"] != "clear": limitations.append(relation["reason"])
    else: reasons.append("No attributable ancestor/descendant or shared-ancestor conflict was found in the complete bounded pedigree.")
    service = _service_performance(female, boar, evidence)
    score = 100
    score -= min(service["prior_pairings"] * 8, 24)
    score -= min(int(boar.get("service_count") or 0) * 2, 20)
    score += min(service["surviving_piglets"], 12)
    if service["mean_survival_percent"] is not None: score += round(service["mean_survival_percent"] / 20)
    if service["growth_evidence"] == "positive": score += 5
    elif service["growth_evidence"] == "adverse": score -= 5
    reasons.extend(service["reasons"])
    return {
        "pig_id": boar_id, "tag_number": _text(boar.get("tag_number")) or boar_id,
        "excluded": bool(exclusions), "exclusion_reasons": exclusions,
        "limitations": limitations,
        "score": score if not exclusions else 0, "reasoning": reasons,
        "service_history": service,
    }


def _relatedness(female, boar, pedigrees):
    female_id, boar_id = _text(female.get("pig_id")), _text(boar.get("pig_id"))
    ft, bt = pedigrees.get(female_id, {}), pedigrees.get(boar_id, {})
    if ft.get("cycle_nodes") or bt.get("cycle_nodes"):
        return {"status": "conflict", "reason": "pedigree contains a cycle or identity conflict"}
    fa, ba = set(ft.get("ancestor_ids") or []), set(bt.get("ancestor_ids") or [])
    if boar_id in fa or female_id in ba:
        return {"status": "conflict", "reason": "ancestor/descendant pairing is excluded"}
    shared = sorted(fa & ba)
    if shared:
        return {"status": "conflict", "reason": "shared ancestor(s): " + ", ".join(shared)}
    if ft.get("lineage_status") != "complete" or bt.get("lineage_status") != "complete" or not fa or not ba:
        return {"status": "limited", "reason": "foundation ancestry is incomplete; no known unsafe relationship was found"}
    return {"status": "clear", "reason": "complete bounded pedigrees are disjoint"}


def _service_performance(female, boar, evidence):
    female_id, boar_id = _text(female.get("pig_id")), _text(boar.get("pig_id"))
    pairings = [r for r in evidence.get("pairings", []) if _text(r.get("sow_pig_id")) == female_id and _text(r.get("boar_pig_id")) == boar_id]
    litters = [r for r in evidence.get("litters", []) if _text(r.get("sow_pig_id")) == female_id and _text(r.get("boar_pig_id")) == boar_id]
    born = sum(int(r.get("born_alive") or 0) for r in litters)
    surviving = sum(int(r["surviving_or_weaned"] if r.get("surviving_or_weaned") is not None else r["weaned_count"] if r.get("weaned_count") is not None else 0) for r in litters)
    survival = round(100 * surviving / born, 1) if born else None
    growth = [r.get("offspring_growth") for r in litters if r.get("offspring_growth")]
    growth_state = "unknown" if not growth else "adverse" if "adverse" in growth else "positive" if "positive" in growth else "mixed"
    return {"prior_pairings": len(pairings), "attributable_litters": len(litters), "born_alive": born, "surviving_piglets": surviving, "mean_survival_percent": survival, "growth_evidence": growth_state, "reasons": [f"Previous pairing count: {len(pairings)}.", f"Attributable litter evidence: {len(litters)} litter(s), {born} born alive, {surviving} surviving/weaned.", f"Attributable offspring growth evidence: {growth_state}."]}


def _evidence_buckets(row, cycle, today):
    confirmed = [f"Canonical identity {row.get('pig_id')} ({row.get('tag_number')}).", f"Lifecycle {row.get('status') or 'Unknown'}; purpose {row.get('purpose') or 'Unknown'}; on farm {row.get('on_farm') if row.get('on_farm') is not None else 'Unknown'}."]
    if row.get("latest_weight_kg") is not None: confirmed.append(f"Latest weight {row['latest_weight_kg']} kg on {row.get('latest_weight_date') or 'Unknown'}.")
    observed = list(row.get("owner_observation_evidence") or [])
    observations = row.get("observations") if isinstance(row.get("observations"), dict) else {}
    if observations:
        observed.append({key: observations[key] for key in sorted(observations)})
    calculated = [f"Weight age: {_weight_age(row, today) if _weight_age(row, today) is not None else 'Unknown'} days."]
    if cycle: calculated.append(f"Current reproductive cycle: {cycle.get('state') or 'Unknown'}; evidence date {cycle.get('evidence_date') or 'Unknown'}.")
    hypotheses = list(row.get("hypotheses") or [])
    unknowns = []
    for value, label in ((row.get("current_pen_name"), "current pen"), (row.get("available_for_breeding"), "breeding availability"), (row.get("withdrawal_evidence_state") if _norm(row.get("withdrawal_evidence_state")) not in {"unknown", ""} else None, "withdrawal clearance")):
        if value in {None, ""}: unknowns.append(label + " is Unknown")
    return confirmed, observed, calculated, hypotheses, unknowns


def _valid_assumed_pregnancy(row, cycle, evidence, today):
    current = (evidence.get("current_mating_by_female") or {}).get(_text(row.get("pig_id")), {})
    evidence_age = _date_age(cycle.get("evidence_date"), today)
    mating_age = _date_age(cycle.get("mating_date"), today)
    return bool(
        _text(cycle.get("evidence_reference"))
        and _text(cycle.get("mating_id"))
        and _norm(cycle.get("source")) in {"authenticated_owner_observation", "herdmaster_proactive_management_round_authenticated_owner_evidence", "canonical_pig_observation_event"}
        and _text(cycle.get("subject_pig_id")) == _text(row.get("pig_id"))
        and _text(current.get("mating_id")) == _text(cycle.get("mating_id"))
        and _text(current.get("mating_date")) == _text(cycle.get("mating_date"))
        and evidence_age is not None and 0 <= evidence_age <= 30
        and mating_age is not None and 0 <= mating_age <= 125
        and cycle.get("current_applicability") is True
        and isinstance(cycle.get("observed_signs"), list)
        and any(_text(item) for item in cycle["observed_signs"])
        and cycle.get("clinical_confirmation") is False
    )


def _smallest_physical_question(row, state):
    if state in {"already_mated", "assumed_pregnant", "expected_to_farrow", "inconclusive", "nursing", "held", "unsuitable"}: return None
    observations = row.get("observations") if isinstance(row.get("observations"), dict) else {}
    gaps = [label for key, label in (("body_condition", "body condition"), ("legs_sound", "legs and normal movement"), ("visible_concern", "any visible concern"), ("heat", "heat observed or not observed")) if observations.get(key) in {None, "", "Unknown", "unknown"}]
    return None if not gaps else f"For {row.get('tag_number') or row.get('pig_id')}, please report " + ", ".join(gaps) + " from one current inspection."


def _physical_blocker(value):
    return any(word in value for word in ("body condition", "legs", "visible concern", "heat"))


def _next_action(blockers):
    physical = [b for b in blockers if any(word in b for word in ("body condition", "legs", "visible concern", "heat"))]
    return "Record one current inspection: " + ", ".join(physical) + "." if physical else "Resolve the listed governed evidence before mating review."


def _boar_inventory(row, today):
    return {"pig_id": _text(row.get("pig_id")), "tag_number": _text(row.get("tag_number")) or _text(row.get("pig_id")), "status": row.get("status") or "Unknown", "on_farm": row.get("on_farm") if row.get("on_farm") is not None else "Unknown", "purpose": row.get("purpose") or "Unknown", "pen": row.get("current_pen_name") or "Unknown", "age_days": row.get("age_days") if row.get("age_days") is not None else "Unknown", "weight_kg": row.get("latest_weight_kg") if row.get("latest_weight_kg") is not None else "Unknown", "weight_date": row.get("latest_weight_date") or "Unknown", "weight_age_days": _weight_age(row, today) if _weight_age(row, today) is not None else "Unknown", "medical": row.get("medical_status") or "Unknown", "withdrawal": row.get("withdrawal_evidence_state") or "Unknown", "availability": row.get("available_for_breeding") or "Unknown", "reservation": row.get("reservation_status") or "Unknown", "service_count": row.get("service_count") if row.get("service_count") is not None else "Unknown"}


def _render(cases, language):
    actionable = [r for r in cases if r["state"] == "eligible_for_mating_review" and r["recommended_boar"]]
    attention = [r for r in cases if r not in actionable]
    if language == "af":
        lines = [f"Teelaandag: {len(cases)} sôe/gelte nagegaan. Geen paring word geskep nie."]
        for row in actionable + attention:
            primary = row.get("recommended_boar") or row.get("conditional_primary_boar")
            reserve = row.get("reserve_boar") or row.get("conditional_reserve_boar")
            pairing = (f" Voorlopige bere: {_safe_text(primary['tag_number'])} eerste, {_safe_text(reserve['tag_number'])} reserwe; eers nadat huidige gereedheid bevestig is."
                       if primary and reserve and not row.get("recommended_boar") else
                       f" Bere: {_safe_text(primary['tag_number'])} eerste, {_safe_text(reserve['tag_number'])} reserwe."
                       if primary and reserve else "")
            lines.append(f"{_safe_text(row['tag_number'])}: {_af_state(row['state'])}. Volgende: {_af_action(row)}{pairing}")
    else:
        lines = [f"Breeding round: {len(cases)} sow(s)/gilt(s) assessed. No mating is created."]
        for row in actionable + attention: lines.append(f"{_safe_text(row['tag_number'])}: {_safe_text(row['state'].replace('_', ' '))}. Next: {_safe_text(row['next_action'], 240)}")
    return "\n".join(lines)


def _oom_packet(cases, digest):
    rows = []
    for row in cases:
        rows.append({
            "pig_id": _safe_text(row["pig_id"]), "tag_number": _safe_text(row["tag_number"]),
            "state": row["state"], "pairing_assessment": row["pairing_assessment"], "next_action": _safe_text(row["next_action"], 240),
            "smallest_physical_question": _safe_text(row.get("smallest_physical_question"), 240) or None,
            "recommended_boar": ({"pig_id": _safe_text(row["recommended_boar"]["pig_id"]), "tag_number": _safe_text(row["recommended_boar"]["tag_number"]), "reasoning": [_safe_text(item, 200) for item in row["recommended_boar"]["reasoning"]]} if row.get("recommended_boar") else None),
            "reserve_boar": ({"pig_id": _safe_text(row["reserve_boar"]["pig_id"]), "tag_number": _safe_text(row["reserve_boar"]["tag_number"]), "reasoning": [_safe_text(item, 200) for item in row["reserve_boar"]["reasoning"]]} if row.get("reserve_boar") else None),
            "conditional_primary_boar": ({"pig_id": _safe_text(row["conditional_primary_boar"]["pig_id"]), "tag_number": _safe_text(row["conditional_primary_boar"]["tag_number"]), "limitations": [_safe_text(item, 200) for item in row["conditional_primary_boar"]["limitations"]]} if row.get("conditional_primary_boar") else None),
            "conditional_reserve_boar": ({"pig_id": _safe_text(row["conditional_reserve_boar"]["pig_id"]), "tag_number": _safe_text(row["conditional_reserve_boar"]["tag_number"]), "limitations": [_safe_text(item, 200) for item in row["conditional_reserve_boar"]["limitations"]]} if row.get("conditional_reserve_boar") else None),
            "boar_exclusions": [{"pig_id": _safe_text(item["pig_id"]), "tag_number": _safe_text(item["tag_number"]), "reasons": [_safe_text(reason, 200) for reason in item["exclusion_reasons"]]} for item in row["boar_assessments"] if item["excluded"]],
        })
    return {"contract_version": CONTRACT_VERSION, "assessment_id": f"HERD-BREED-{digest[:32].upper()}", "cases": rows, "writes_performed": False, "mating_execution_enabled": False}


def _af_state(state):
    return {"eligible_for_mating_review":"gereed vir teeloorsig", "held":"op hou", "unsuitable":"nie tans geskik nie", "already_mated":"reeds gepaar", "assumed_pregnant":"waarskynlik dragtig volgens visuele waarneming, nie klinies bevestig nie", "expected_to_farrow":"verwag om te kraam", "inconclusive":"onbeslis", "nursing":"soog tans", "recovering":"herstel ná speen", "missing_evidence":"bewyse ontbreek"}.get(state, "status onbekend")


def _af_action(row):
    state, action = row["state"], row["next_action"]
    if state == "held" and "welfare" in action: return "Gaan voort met die bestaande welsynsgeval; moenie teelwerk dupliseer nie."
    if state == "held" and "owner hold" in action: return "Handhaaf die eienaar se hou en heroorweeg eers ná uitdruklike vrystelling."
    if state == "held": return "Los die beheerde gesondheids- of onttrekkingshou op voor teeloorsig."
    if state == "missing_evidence" and "Bind the visual" in action: return "Bind die visuele waarneming aan hierdie sog en presiese paring voor dragtigheidsbeplanning."
    if state == "missing_evidence" and "Record one current inspection" in action: return "Teken een huidige, gegroepeerde fisiese inspeksie aan."
    return {"unsuitable":"Geen teelaksie nie.", "already_mated":"Hou die bestaande siklus dop; moenie nog 'n paring aanbeveel nie.", "assumed_pregnant":"Gaan voort met proporsionele kraamvoorbereiding; dit is nie kliniese bevestiging nie.", "expected_to_farrow":"Gaan voort met dragtigheids- en kraammonitering.", "inconclusive":"Behou die onopgeloste siklus en doen die beplande herbeoordeling.", "nursing":"Beskerm die soogwerk en heroorweeg ná bevestigde speen.", "recovering":"Voltooi die kleinste liggaamskondisie- en loopinspeksie.", "eligible_for_mating_review":"Hersien huidige hitte en slegs bewys-gekwalifiseerde bere; paring vereis aparte goedkeuring.", "missing_evidence":"Los die gelyste beheerde bewyse op voordat paring oorweeg word."}.get(state, _safe_text(action, 240))


def _safe_text(value, limit=96):
    return " ".join(_text(value).split())[:limit]


def _weight_age(row, today):
    try: return (today - date.fromisoformat(str(row.get("latest_weight_date"))[:10])).days
    except (TypeError, ValueError): return None


def _date_age(value, today):
    try: return (today - date.fromisoformat(str(value)[:10])).days
    except (TypeError, ValueError): return None


def _truth(value): return value is True or _norm(value) in {"yes", "true", "1", "on_farm"}
def _norm(value): return _text(value).lower().replace(" ", "_").replace("-", "_")
def _text(value): return str(value or "").strip()
def _digest(value): return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
def _unavailable(reason): return {"success": False, "contract_version": CONTRACT_VERSION, "reason": reason, "female_count": None, "boar_count": None, "delivery_enabled": False, "mating_execution_enabled": False, "writes_performed": False, "protected_actions_performed": False}
