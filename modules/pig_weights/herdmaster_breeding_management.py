"""Pure proactive management layer over evidence-qualified breeding results."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta

from modules.pig_weights.herdmaster_breeding_evidence import CONTRACT_VERSION as EVIDENCE_CONTRACT_VERSION
from modules.pig_weights.herdmaster_breeding_recommendation import CONTRACT_VERSION as RECOMMENDATION_CONTRACT_VERSION


CONTRACT_VERSION = "herdmaster_breeding_management_v1"


def build_breeding_management_packet(reconciled, assessment, *, today=None):
    """Return at most three useful actions without granting mating authority."""
    today = today or date.today()
    if not isinstance(reconciled, dict) or not reconciled.get("success"):
        return _unavailable("successful canonical reconciliation is required")
    if not isinstance(assessment, dict) or not assessment.get("success"):
        return _unavailable("successful breeding assessment is required")
    if reconciled.get("contract_version") != EVIDENCE_CONTRACT_VERSION:
        return _unavailable("supported canonical reconciliation contract is required")
    if assessment.get("contract_version") != RECOMMENDATION_CONTRACT_VERSION:
        return _unavailable("supported breeding assessment contract is required")
    if any(reconciled.get(key) is not False for key in ("writes_performed", "protected_actions_performed")):
        return _unavailable("canonical reconciliation must carry zero write and protected-action authority")
    if any(assessment.get(key) is not False for key in ("writes_performed", "protected_actions_performed", "delivery_enabled", "mating_execution_enabled")):
        return _unavailable("breeding assessment must carry zero delivery, write and protected-action authority")
    females = reconciled.get("females")
    boars = reconciled.get("boars")
    cases = assessment.get("cases")
    if not isinstance(females, list) or not isinstance(boars, list) or not isinstance(cases, list):
        return _unavailable("complete canonical inventories and assessment cases are required")
    if not all(isinstance(row, dict) for row in females + boars + cases):
        return _unavailable("inventory and assessment rows must be mappings")
    female_ids = [_text(row.get("pig_id")) for row in females]
    boar_ids = [_text(row.get("pig_id")) for row in boars]
    case_ids = [_text(row.get("pig_id")) for row in cases]
    if not all(female_ids + boar_ids + case_ids) or len(female_ids + boar_ids) != len(set(female_ids + boar_ids)) or len(case_ids) != len(set(case_ids)):
        return _unavailable("inventory and case identities must be non-empty and unique")
    if any(_norm(row.get("sex")) != "female" for row in females) or any(_norm(row.get("sex")) != "male" for row in boars):
        return _unavailable("inventory sex conflicts with breeding role")
    reconciliation_digest = _text(reconciled.get("evidence_digest"))
    if not reconciliation_digest or _text(assessment.get("reconciliation_digest")) != reconciliation_digest:
        return _unavailable("breeding assessment is not bound to this canonical reconciliation")
    if assessment.get("evidence_generation") != reconciled.get("evidence_generation"):
        return _unavailable("breeding assessment evidence generation is stale or mismatched")
    assessment_material = {
        "contract_version": RECOMMENDATION_CONTRACT_VERSION,
        "reconciliation_digest": reconciliation_digest,
        "cases": assessment.get("cases"),
        "boar_inventory": assessment.get("boar_inventory"),
    }
    if "whole_round_allocation" in assessment:
        assessment_material["whole_round_allocation"] = assessment.get("whole_round_allocation")
    assessment_digest = _digest(assessment_material)
    if assessment.get("material_evidence_digest") != assessment_digest or assessment.get("assessment_id") != f"HERD-BREED-{assessment_digest[:32].upper()}":
        return _unavailable("breeding assessment material digest is invalid")
    animals = {
        _text(row.get("pig_id")): row
        for row in (reconciled.get("females") or []) + (reconciled.get("boars") or [])
    }
    case_by_id = {_text(row.get("pig_id")): row for row in cases}
    if set(case_by_id) != {_text(row.get("pig_id")) for row in reconciled.get("females") or []}:
        return _unavailable("female inventory and assessment identities differ")

    candidates = []
    candidates.extend(_welfare_actions(cases))
    candidates.extend(_data_quality_actions(reconciled, case_by_id))
    candidates.extend(_farrowing_actions(cases, animals, today))
    candidates.extend(_inconclusive_actions(cases))
    candidates.extend(_post_litter_actions(cases))
    candidates.extend(_cycle_review_actions(cases))
    actions = sorted(candidates, key=lambda row: (row["priority"], row["action_id"]))[:3]
    pedigree = _pedigree_matrix(reconciled, animals)
    missing = [row for row in pedigree if row["missing_parent_links"]]
    recovery = _recovery_packet(missing, reconciled.get("coverage") or {})
    payload = {
        "success": True,
        "internal_only": True,
        "contract_version": CONTRACT_VERSION,
        "evidence_date": today.isoformat(),
        "reconciliation_digest": reconciliation_digest,
        "assessment_id": assessment.get("assessment_id"),
        "pedigree_recovery_matrix": pedigree,
        "recovered_parent_count": sum(bool(row["dam_pig_id"]) + bool(row["sire_pig_id"]) for row in pedigree),
        "remaining_missing_parent_links": sum(len(row["missing_parent_links"]) for row in pedigree),
        "clearance_coverage": reconciled.get("coverage"),
        "actions": actions,
        "english": _render(actions, "en"),
        "afrikaans": _render(actions, "af"),
        "recovery_packet": recovery,
        "safe_fallback_proposal": {
            "status": "owner_review_only_not_implemented",
            "proposal": "If historical parentage is permanently unavailable, keep internal unknown-related pairings blocked and obtain attributable pedigree/DNA evidence or an externally documented unrelated boar before a final pairing recommendation.",
            "prohibited": ["silently treat unknown as unrelated", "approve an internal pairing from pen, breed, appearance, prior service or proximity", "create a mating"],
        },
        "delivery_enabled": False,
        "mating_execution_enabled": False,
        "writes_performed": False,
        "protected_actions_performed": False,
    }
    payload["packet_id"] = "HERD-BREED-MGMT-" + _digest(payload)[:32].upper()
    payload["oom_sakkie_packet"] = _sanitized_packet(payload["packet_id"], actions)
    return payload


def _sanitized_packet(packet_id, actions):
    public_actions = [{
        "action_id": _public_text(row["action_id"], 64),
        "animals": [{"pig_id": _public_text(animal["pig_id"], 80), "tag_number": _public_text(animal["tag_number"], 80), "state": _public_text(animal["state"], 48)} for animal in row["animals"]],
        "recommendation": _public_text(row["recommendation"], 500),
        "smallest_physical_observation": _public_text(row["smallest_physical_observation"], 500),
        "decision_that_could_change": _public_text(row["decision_that_could_change"], 500),
    } for row in actions]
    return {
        "packet_id": _public_text(packet_id, 80),
        "contract_version": CONTRACT_VERSION,
        "actions": public_actions,
        "english": _public_text(_render(public_actions, "en"), 2000),
        "afrikaans": _public_text(_render(public_actions, "af"), 2000),
        "delivery_enabled": False,
        "mating_execution_enabled": False,
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def _welfare_actions(cases):
    rows = [row for row in cases if row.get("state") == "held" and "welfare" in _norm(row.get("next_action"))]
    return [] if not rows else [_action("active-welfare", 1, rows, "Continue the existing welfare lifecycle; breeding work stays suppressed.", "Use only the existing lifecycle's next observation; ask no duplicate question.", "Welfare resolution may permit later breeding reassessment, but never proves readiness.")]


def _data_quality_actions(reconciled, case_by_id):
    rows=[]
    for animal in reconciled.get("females") or []:
        cycle=animal.get("cycle_evidence") or {}
        if cycle.get("status")=="conflicting" and animal.get("pig_id") in case_by_id:
            rows.append(case_by_id[animal["pig_id"]])
    return [] if not rows else [_action("reproductive-data-quality",5,rows,"Resolve the exact conflicting mating/litter chronology before changing reproductive state; continue only independently supported welfare or nursing care.","No new physical observation is requested for a source-record conflict.","A governed supersession or corrected canonical linkage can restore one current cycle; it does not itself prove breeding readiness.")]


def _farrowing_actions(cases, animals, today):
    rows = [row for row in cases if row.get("state") in {"assumed_pregnant", "expected_to_farrow"}]
    if not rows:
        return []
    details=[]
    for row in rows:
        cycle=row.get("current_cycle") or {}; mating=_date(cycle.get("mating_date"))
        details.append({
            "pig_id":row["pig_id"], "tag_number":row["tag_number"], "state":row["state"],
            "mating_id":cycle.get("mating_id"), "mating_date":_date_text(mating),
            "projected_farrowing_range":f"{(mating+timedelta(days=112)).isoformat()} to {(mating+timedelta(days=116)).isoformat()}" if mating else "Unknown",
            "preparation_window":f"{(mating+timedelta(days=98)).isoformat()} to {(mating+timedelta(days=105)).isoformat()}" if mating else "Unknown",
            "clinical_confirmation":bool(cycle.get("clinical_confirmation") is True),
        })
    action=_action("farrowing-preparation", 10, rows, "Continue proportional farrowing preparation and monitoring; Assumed Pregnant is planning evidence, not clinical confirmation.", "At the next normal round, observe belly/udder progression, appetite, movement, discharge and any labour or illness sign once for the grouped sows.", "Clear non-pregnancy evidence, return to heat, illness, abortion signs, early labour or farrowing changes the plan.")
    action["cycle_details"]=details
    return [action]


def _inconclusive_actions(cases):
    rows=[row for row in cases if row.get("state")=="inconclusive"]
    return [] if not rows else [_action("inconclusive-cycle",20,rows,"Preserve the unresolved cycle and perform the scheduled reproductive-status reassessment; do not recommend another mating.","Observe current heat/non-heat and ordinary reproductive changes once at the scheduled reassessment.","A governed Not Pregnant, Assumed Pregnant, confirmed result or return-to-heat observation changes the reproductive path.")]


def _post_litter_actions(cases):
    rows=[row for row in cases if row.get("state") in {"nursing","recovering"}]
    return [] if not rows else [_action("post-litter-care",30,rows,"Protect nursing and post-weaning recovery before any breeding review.","In one grouped round, observe sow body condition, appetite, movement, udder/teats, visible concern and piglet thriving where still nursing.","Governed weaning plus adequate recovery evidence can unlock a later readiness review; it does not authorize mating.")]


def _cycle_review_actions(cases):
    rows=[row for row in cases if row.get("state")=="missing_evidence"]
    return [] if not rows else [_action("reproductive-status-review",40,rows,"Establish current reproductive state without treating missing pedigree as a reason to suppress the supported status review.","For only these females, observe heat/non-heat, body condition, normal movement and visible concerns in one grouped round.","The observation can classify current management attention; final pairing remains blocked by independent pedigree and clearance gates.")]


def _action(action_id, priority, rows, recommendation, observation, unlock):
    return {
        "action_id":action_id, "priority":priority,
        "animals":[{"pig_id":row["pig_id"],"tag_number":row["tag_number"],"state":row["state"]} for row in sorted(rows,key=lambda r:(r["tag_number"].lower(),r["pig_id"]))],
        "current_evidence":[{"pig_id":row["pig_id"],"confirmed":row.get("confirmed_evidence") or [],"calculated":row.get("calculated_facts") or []} for row in sorted(rows,key=lambda r:r["pig_id"])],
        "recommendation":recommendation, "smallest_physical_observation":observation,
        "decision_that_could_change":unlock, "final_pairing_authorized":False,
    }


def _pedigree_matrix(reconciled, animals):
    rows=[]
    for pig_id,parentage in sorted((reconciled.get("parentage") or {}).items(),key=lambda item:(_text(animals.get(item[0],{}).get("tag_number")).lower(),item[0])):
        animal=animals.get(pig_id,{})
        sources=[]
        if parentage.get("direct_dam_pig_id") or parentage.get("direct_sire_pig_id"):
            sources.append({"type":"canonical_pig_master","import_batch_id":animal.get("import_batch_id"),"source_sheet_row":animal.get("source_sheet_row"),"evidence_date":_date_text(animal.get("updated_at") or animal.get("created_at")) or "Unknown"})
        if parentage.get("litter_dam_pig_id") or parentage.get("litter_sire_pig_id"):
            sources.append({"type":"canonical_non_superseded_litter_origin","litter_id":parentage.get("litter_id"),"evidence_date":"Unknown"})
        rows.append({
            "pig_id":pig_id,"tag_number":animal.get("tag_number") or pig_id,
            "dam_pig_id":parentage.get("dam_pig_id"),"sire_pig_id":parentage.get("sire_pig_id"),
            "sources":sources,"confidence":"Proven" if parentage.get("status")=="complete" else "Conflicting" if parentage.get("status")=="conflicting" else "Unknown",
            "conflict_state":parentage.get("status"),"missing_parent_links":list(parentage.get("missing_links") or []),
            "duplicate_cyclic_or_superseded_lineage":list((reconciled.get("pedigrees") or {}).get(pig_id,{}).get("cycle_nodes") or []),
        })
    return rows


def _recovery_packet(missing, coverage):
    return {
        "status":"source_or_owner_evidence_required" if missing else "complete",
        "single_grouped_request":None if not missing else "Please provide one historical breeder register, import sheet, purchase/birth record or other attributable source that names the dam and sire for any listed breeder; if no such source exists, say once that historical parentage is unavailable.",
        "animals":[{"pig_id":row["pig_id"],"tag_number":row["tag_number"],"missing":row["missing_parent_links"]} for row in missing],
        "system_owned_not_owner_questions":[
            {"criterion":"reservation","status":(coverage.get("reservation") or {}).get("reason")},
            {"criterion":"withdrawal","status":(coverage.get("withdrawal") or {}).get("reason")},
        ],
    }


def _render(actions, language):
    if language=="af":
        lead="Teelbestuur: die drie belangrikste huidige aksies. Geen paring word geskep nie."
        return "\n".join([lead]+[f"{i}. {', '.join(a['tag_number'] for a in row['animals'])}: {_af(row['action_id'])}" for i,row in enumerate(actions,1)])
    lead="Breeding management: the three highest-value current actions. No mating is created."
    return "\n".join([lead]+[f"{i}. {', '.join(a['tag_number'] for a in row['animals'])}: {row['recommendation']}" for i,row in enumerate(actions,1)])


def _af(action_id):
    return {
        "active-welfare":"Hou by die bestaande welsynsopvolg; teelwerk bly onderdruk.",
        "reproductive-data-quality":"Los die presiese botsende parings-/werpselchronologie op voordat voortplantingstatus verander; geen nuwe fisiese waarneming word hiervoor gevra nie.",
        "farrowing-preparation":"Gaan voort met proporsionele kraamvoorbereiding en monitering; waarskynlik dragtig is nie kliniese bevestiging nie.",
        "inconclusive-cycle":"Behou die onbesliste siklus en doen die beplande voortplantingstatus-herbeoordeling; moenie weer paring aanbeveel nie.",
        "post-litter-care":"Beskerm soogwerk en herstel ná speen voordat teelgereedheid hersien word.",
        "reproductive-status-review":"Bepaal die huidige voortplantingstatus; finale paring bly afsonderlik deur stamboom en klaring geblokkeer.",
    }.get(action_id,"Geen beskermde aksie nie.")


def _digest(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def _norm(value): return _text(value).lower().replace(" ","_").replace("-","_")
def _text(value): return str(value or "").strip()
def _public_text(value, limit): return " ".join("".join(ch for ch in _text(value) if ch >= " " and ch != "\x7f").split())[:limit]
def _date(value):
    try:return date.fromisoformat(str(value)[:10])
    except (TypeError,ValueError):return None
def _date_text(value):
    parsed=_date(value);return parsed.isoformat() if parsed else ""
def _unavailable(reason): return {"success":False,"contract_version":CONTRACT_VERSION,"reason":reason,"delivery_enabled":False,"mating_execution_enabled":False,"writes_performed":False,"protected_actions_performed":False}
