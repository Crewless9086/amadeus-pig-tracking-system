"""Coverage-aware canonical evidence reconciliation for breeding decisions.

This module is deterministic and performs no I/O. Callers supply rows already
read under the existing authenticated, read-only farm evidence boundary.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import hashlib
import json


CONTRACT_VERSION = "herdmaster_breeding_evidence_v1"


def reconcile_breeding_evidence(snapshot, *, today=None):
    today = today or date.today()
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("pigs"), list):
        return _unavailable("complete canonical pig rows are required")
    identified = [dict(row) for row in snapshot["pigs"] if _text(row.get("pig_id"))]
    pig_ids = [_text(row.get("pig_id")) for row in identified]
    if len(pig_ids) != len(set(pig_ids)):
        return _unavailable("canonical pig identity is duplicated")
    pigs = {_text(row.get("pig_id")): row for row in identified}
    breeders = [row for row in pigs.values() if _breeder(row)]
    locations = _latest_valid(snapshot.get("location_events") or [], "pig_id", "move_date", today)
    litter_index, litter_conflicts = _litters(snapshot.get("litters") or [])
    parentage = {pig_id: _parents(row, litter_index, litter_conflicts) for pig_id, row in pigs.items()}
    pedigrees = {row["pig_id"]: _lineage(row["pig_id"], parentage) for row in breeders}
    reservations = _reservations(snapshot, [row["pig_id"] for row in breeders], today)
    withdrawals = _withdrawals(snapshot, [row["pig_id"] for row in breeders], today)
    observations = _observations(snapshot.get("observations") or [], today)
    performance = _performance(snapshot, pigs, litter_index, litter_conflicts, today)
    conflict_sows = {
        _text(row.get("sow_pig_id"))
        for row in (snapshot.get("mating_events") or []) + (snapshot.get("litters") or [])
        if (_text(row.get("mating_id")) in performance["mating_conflicts"] or _text(row.get("litter_id")) in performance["litter_conflicts"])
    }
    cycles = _cycles(snapshot, breeders, performance["pairings"], performance["litters"], conflict_sows, today)
    females, boars, data_quality = [], [], []
    for row in breeders:
        pig_id = row["pig_id"]
        recovered = dict(row)
        pen = _pen(row, locations.get(pig_id))
        born = _date(row.get("date_of_birth"))
        recovered.update({
            "current_pen_id": pen["pen_id"], "current_pen_name": pen["pen_name"],
            "pen_evidence": pen, "reservation_status": reservations[pig_id]["state"],
            "reservation_evidence": reservations[pig_id],
            "withdrawal_evidence_state": withdrawals[pig_id]["state"],
            "withdrawal_evidence": withdrawals[pig_id],
            "observations": observations.get(pig_id, {}),
            "service_count": performance["service_counts"].get(pig_id, 0),
            "age_days": (today - born).days if born and born <= today else None,
            "current_cycle": cycles[pig_id]["cycle"] if _norm(row.get("sex")) == "female" else recovered.get("current_cycle", {}),
            "cycle_evidence": cycles[pig_id] if _norm(row.get("sex")) == "female" else None,
        })
        missing = parentage[pig_id]["missing_links"]
        data_quality.extend({"pig_id": pig_id, "tag_number": row.get("tag_number") or pig_id, "field": field, "status": "genuinely_absent", "recovery_source": "owner/import provenance only; do not infer"} for field in missing)
        if pen["status"] == "conflicting": data_quality.append({"pig_id": pig_id, "tag_number": row.get("tag_number") or pig_id, "field": "current_pen", "status": "conflicting", "recovery_source": "reconcile current state with latest valid movement"})
        if pig_id in conflict_sows: data_quality.append({"pig_id": pig_id, "tag_number": row.get("tag_number") or pig_id, "field": "reproductive_chronology", "status": "conflicting", "recovery_source": "reconcile duplicated mating/litter identity"})
        (females if _norm(row.get("sex")) == "female" else boars).append(recovered)
    pair_relatedness = []
    for female in females:
        for boar in boars:
            pair_relatedness.append(_relationship(female["pig_id"], boar["pig_id"], parentage, pedigrees))
    result = {
        "success": True, "contract_version": CONTRACT_VERSION, "evidence_date": today.isoformat(),
        "females": sorted(females, key=_animal_key), "boars": sorted(boars, key=_animal_key),
        "pedigrees": pedigrees, "parentage": {row["pig_id"]: parentage[row["pig_id"]] for row in breeders},
        "pair_relatedness": sorted(pair_relatedness, key=lambda row: (row["female_pig_id"], row["boar_pig_id"])),
        "pairings": performance["pairings"], "litters": performance["litters"],
        "policy": dict(snapshot.get("policy") or {}),
        "current_mating_by_female": cycles["__current_matings__"],
        "active_welfare_pig_ids": sorted({_text(value) for value in snapshot.get("active_welfare_pig_ids") or [] if _text(value)}),
        "evidence_generation": snapshot.get("evidence_generation"),
        "data_quality_recovery": sorted(data_quality, key=lambda row: (row["tag_number"], row["pig_id"], row["field"])),
        "coverage": {"reservation": reservations["__coverage__"], "withdrawal": withdrawals["__coverage__"]},
        "privacy_boundary": "internal_authorized_evidence_only",
        "writes_performed": False, "protected_actions_performed": False,
    }
    result["evidence_digest"] = hashlib.sha256(json.dumps(result, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
    return result


def _breeder(row):
    if _norm(row.get("status")) != "active" or not _truth(row.get("on_farm")):
        return False
    sex, kind, purpose = _norm(row.get("sex")), _norm(row.get("animal_type")), _norm(row.get("purpose"))
    return (sex == "female" and (kind in {"sow", "gilt"} or purpose == "breeding")) or (sex == "male" and (kind == "boar" or purpose == "breeding"))


def _pen(pig, latest):
    state_id, state_name = _text(pig.get("current_pen_id")), _text(pig.get("current_pen_name"))
    latest = latest or {}
    move_id, move_name = _text(latest.get("to_pen_id")), _text(latest.get("to_pen_name") or latest.get("pen_name"))
    if state_id and move_id and (state_id != move_id or (state_name and move_name and _norm(state_name) != _norm(move_name))):
        return {"status":"conflicting", "pen_id":None, "pen_name":None, "current_state_pen_id":state_id, "latest_movement_pen_id":move_id, "movement_date":_date_text(latest.get("move_date"))}
    if state_id and state_name:
        pen_id, pen_name = state_id, state_name
    elif move_id and move_name:
        pen_id, pen_name = move_id, move_name
    else:
        pen_id, pen_name = "", ""
    return {"status":"recovered" if pen_id else "absent", "pen_id":pen_id or None, "pen_name":pen_name or pen_id or None, "current_state_pen_id":state_id or None, "latest_movement_pen_id":move_id or None, "movement_date":_date_text(latest.get("move_date")) or None}


def _litters(rows):
    grouped = defaultdict(list)
    for row in rows:
        if row.get("is_superseded") is True: continue
        if _text(row.get("litter_id")): grouped[_text(row.get("litter_id"))].append(row)
    index, conflicts = {}, set()
    for litter_id, values in grouped.items():
        pairs={(_text(r.get("sow_pig_id")),_text(r.get("boar_pig_id"))) for r in values}
        normalized={json.dumps(dict(r),sort_keys=True,default=str,separators=(",",":")) for r in values}
        if len(pairs)>1 or len(normalized)>1: conflicts.add(litter_id)
        else: index[litter_id]=values[0]
    chronology=defaultdict(list)
    for litter_id,row in index.items():
        sow_id=_text(row.get("sow_pig_id")); farrowing=_date_text(row.get("farrowing_date"))
        if sow_id and farrowing: chronology[(sow_id,farrowing)].append(litter_id)
    for litter_ids in chronology.values():
        if len(litter_ids)>1: conflicts.update(litter_ids)
    for litter_id in conflicts: index.pop(litter_id,None)
    return index, conflicts


def _parents(row, litters, conflicts):
    litter_id=_text(row.get("litter_id")); litter=litters.get(litter_id,{})
    direct_dam,direct_sire=_text(row.get("mother_pig_id")),_text(row.get("father_pig_id"))
    litter_dam,litter_sire=_text(litter.get("sow_pig_id")),_text(litter.get("boar_pig_id"))
    conflict=litter_id in conflicts or bool(direct_dam and litter_dam and direct_dam!=litter_dam) or bool(direct_sire and litter_sire and direct_sire!=litter_sire)
    dam=None if conflict else direct_dam or litter_dam or None
    sire=None if conflict else direct_sire or litter_sire or None
    missing=[]
    if dam is None: missing.append("mother_pig_id")
    if sire is None: missing.append("father_pig_id")
    return {"status":"conflicting" if conflict else "complete" if dam and sire else "partial", "dam_pig_id":dam, "sire_pig_id":sire, "litter_id":litter_id or None, "direct_dam_pig_id":direct_dam or None, "direct_sire_pig_id":direct_sire or None, "litter_dam_pig_id":litter_dam or None, "litter_sire_pig_id":litter_sire or None, "missing_links":missing}


def _lineage(pig_id, parentage, *, seen=None, depth=0, limit=4):
    seen=set(seen or ())
    if pig_id in seen: return {"lineage_status":"conflicting", "ancestor_ids":[], "cycle_nodes":[pig_id], "missing_links":[]}
    parents=parentage.get(pig_id)
    if not parents: return {"lineage_status":"partial", "ancestor_ids":[], "cycle_nodes":[], "missing_links":[pig_id+":identity"]}
    ancestors=[];cycles=[];missing=[]
    for role,parent in (("dam",parents.get("dam_pig_id")),("sire",parents.get("sire_pig_id"))):
        if not parent: missing.append(pig_id+":"+role)
        else:
            ancestors.append(parent)
            if depth+1<limit:
                sub=_lineage(parent,parentage,seen=seen|{pig_id},depth=depth+1,limit=limit)
                ancestors+=sub["ancestor_ids"];cycles+=sub["cycle_nodes"];missing+=sub["missing_links"]
    status="conflicting" if cycles or parents.get("status")=="conflicting" else "complete" if not missing else "partial"
    return {"lineage_status":status,"ancestor_ids":sorted(set(ancestors)),"cycle_nodes":sorted(set(cycles)),"missing_links":sorted(set(missing))}


def _relationship(female_id, boar_id, parentage, pedigrees):
    ft,bt=pedigrees[female_id],pedigrees[boar_id]
    reason=[];kind="unknown"
    if ft["lineage_status"]=="conflicting" or bt["lineage_status"]=="conflicting": kind,reason="conflicting",["cyclic or conflicting pedigree evidence"]
    elif ft["lineage_status"]!="complete" or bt["lineage_status"]!="complete": kind,reason="unknown",["pair-specific pedigree is partial"]
    else:
        fa,ba=set(ft["ancestor_ids"]),set(bt["ancestor_ids"])
        fp,bp=parentage[female_id],parentage[boar_id]
        if boar_id in fa or female_id in ba: kind,reason="excluded",["direct ancestor/descendant"]
        elif fp.get("dam_pig_id")==bp.get("dam_pig_id") and fp.get("sire_pig_id")==bp.get("sire_pig_id"): kind,reason="excluded",["full sibling"]
        elif {fp.get("dam_pig_id"),fp.get("sire_pig_id")} & {bp.get("dam_pig_id"),bp.get("sire_pig_id")} - {None}: kind,reason="excluded",["half sibling or shared parent"]
        elif fa & ba: kind,reason="excluded",["shared ancestor(s): "+", ".join(sorted(fa&ba))]
        else: kind,reason="clear",["complete bounded pedigrees are disjoint"]
    return {"female_pig_id":female_id,"boar_pig_id":boar_id,"status":kind,"reasons":reason}


def _cycles(snapshot, breeders, pairings, litters, conflict_sows, today):
    """Reconcile supplied governed cycle projections with event chronology."""
    matings=defaultdict(list)
    for row in pairings:
        if _text(row.get("sow_pig_id")): matings[_text(row.get("sow_pig_id"))].append(row)
    litter_rows=defaultdict(list)
    for row in litters:
        if _text(row.get("sow_pig_id")): litter_rows[_text(row.get("sow_pig_id"))].append(row)
    result={}; current={}
    active_states={"recently_mated","post_mating_monitoring","assumed_pregnant","confirmed_pregnant","inconclusive","expected_to_farrow"}
    terminal={"farrowed","not_pregnant","aborted","cancelled","closed"}
    for pig in breeders:
        if _norm(pig.get("sex"))!="female": continue
        pid=pig["pig_id"]
        supplied=dict(pig.get("current_cycle") or {})
        ordered=sorted(matings[pid],key=lambda row:(_date(row.get("mating_date")) or date.min,_text(row.get("mating_id"))))
        unresolved=[row for row in ordered if 0 <= (today-_date(row.get("mating_date"))).days <= 125 and not row.get("farrowing_date") and not row.get("related_litter_id") and _norm(row.get("outcome")) not in terminal]
        latest_mating=unresolved[-1] if unresolved else None
        overdue_positive=[row for row in ordered if _date(row.get("mating_date")) and (today-_date(row.get("mating_date"))).days > 125 and not row.get("farrowing_date") and not row.get("related_litter_id") and (_norm(row.get("pregnancy_check_result")) in {"pregnant","positive"} or _norm(row.get("outcome")) in {"pregnant","positive"})]
        latest_overdue=overdue_positive[-1] if overdue_positive else None
        recent_litters=sorted((row for row in litter_rows[pid] if _date(row.get("farrowing_date")) and _date(row.get("farrowing_date"))<=today),key=lambda row:(_date(row.get("farrowing_date")),row["litter_id"]))
        latest_litter=recent_litters[-1] if recent_litters else None
        conflicts=[]; recovered=False
        if pid in conflict_sows: conflicts.append("mating or litter identity has conflicting canonical rows")
        state=_norm(supplied.get("state") or "missing_evidence")
        if conflicts:
            supplied={"state":"missing_evidence","conflicts":sorted(conflicts)}
        elif latest_litter and not latest_litter.get("wean_date"):
            if state not in {"nursing","expected_to_farrow"}: recovered=True
            supplied={"state":"nursing","last_litter_id":latest_litter["litter_id"],"farrowing_date":latest_litter["farrowing_date"]}
        elif latest_overdue:
            supplied={"state":"unresolved_expected_farrow","mating_id":latest_overdue.get("mating_id"),"mating_date":latest_overdue.get("mating_date"),"pregnancy_check_date":latest_overdue.get("pregnancy_check_date"),"pregnancy_check_result":latest_overdue.get("pregnancy_check_result") or latest_overdue.get("outcome"),"reason":"positive pregnancy lifecycle remains unresolved beyond the current-farrowing applicability boundary"}
            recovered=True
        elif state in active_states:
            if not latest_mating:
                conflicts.append("active cycle has no applicable unresolved mating")
            elif _text(supplied.get("mating_id")) and _text(supplied.get("mating_id"))!=_text(latest_mating.get("mating_id")):
                conflicts.append("cycle mating does not match latest applicable mating")
            elif _date(supplied.get("mating_date")) and _date(supplied.get("mating_date"))!=_date(latest_mating.get("mating_date")):
                conflicts.append("cycle mating date conflicts with canonical mating")
        elif latest_mating:
            supplied={"state":"post_mating_monitoring","mating_id":latest_mating.get("mating_id"),"mating_date":latest_mating.get("mating_date")}
            recovered=True
        if conflicts:
            supplied={"state":"missing_evidence","conflicts":sorted(conflicts)}
        if latest_mating and not conflicts:
            current[pid]={"mating_id":_text(latest_mating.get("mating_id")),"mating_date":_date_text(latest_mating.get("mating_date"))}
        result[pid]={"status":"conflicting" if conflicts else "recovered" if recovered else "confirmed_projection","cycle":supplied,"conflicts":sorted(conflicts)}
    result["__current_matings__"]=dict(sorted(current.items()))
    return result


def _reservations(snapshot, pig_ids, today):
    coverage=_coverage(snapshot.get("reservation_coverage"),pig_ids,today)
    active=defaultdict(list)
    for source in ("active_outlets","order_lines","auction_members","carcass_reservations"):
        for row in snapshot.get(source) or []:
            pid=_text(row.get("pig_id"))
            if pid in pig_ids and _reservation_active(source,row): active[pid].append({"source":source,"reference":_reservation_ref(row)})
    result={}
    for pid in pig_ids:
        state="reserved" if active[pid] else "not_reserved" if coverage["complete"] else "unknown"
        refs=sorted({(row["source"],row["reference"]) for row in active[pid]})
        result[pid]={"state":state,"active_references":[{"source":source,"reference":reference} for source,reference in refs],"coverage_complete":coverage["complete"],"complete_through":coverage["complete_through"]}
    result["__coverage__"]=coverage
    return result


def _withdrawals(snapshot,pig_ids,today):
    coverage=_coverage(snapshot.get("withdrawal_coverage"),pig_ids,today)
    rows=defaultdict(list)
    for row in snapshot.get("medical_events") or []:
        if _text(row.get("pig_id")) in pig_ids: rows[_text(row.get("pig_id"))].append(row)
    result={}
    for pid in pig_ids:
        active=[];conflicts=[];unknown=[];history=[]
        for row in rows[pid]:
            raw_treatment=row.get("treatment_date"); raw_recorded=row.get("withdrawal_end_date")
            treatment=_date(raw_treatment); days=row.get("withdrawal_days"); recorded=_date(raw_recorded)
            malformed=bool(raw_treatment not in {None,""} and treatment is None) or bool(raw_recorded not in {None,""} and recorded is None)
            valid_days=isinstance(days,int) and not isinstance(days,bool) and days>=0
            if days not in {None,""} and not valid_days: malformed=True
            if treatment and treatment>today: malformed=True
            calculated=treatment+timedelta(days=days) if treatment and valid_days else None
            if malformed: conflicts.append(_text(row.get("medical_event_id")))
            if recorded and calculated and recorded!=calculated: conflicts.append(_text(row.get("medical_event_id")))
            end=recorded or calculated
            if end and end>=today: active.append(_text(row.get("medical_event_id")))
            if end is None: unknown.append(_text(row.get("medical_event_id")))
            history.append({"medical_event_id":_text(row.get("medical_event_id")),"withdrawal_end_date":_date_text(end) or None})
        if conflicts: state="conflicting"
        elif active: state="hold"
        elif unknown: state="unknown"
        elif coverage["complete"]: state="cleared" if history else "not_applicable"
        else: state="unknown"
        result[pid]={"state":state,"active_event_ids":sorted(set(active)),"conflicting_event_ids":sorted(set(conflicts)),"unknown_event_ids":sorted(set(unknown)),"history":sorted(history,key=lambda row:row["medical_event_id"]),"coverage_complete":coverage["complete"],"complete_through":coverage["complete_through"]}
    result["__coverage__"]=coverage
    return result


def _coverage(raw,pig_ids,today):
    raw=raw if isinstance(raw,dict) else {}
    through=_date(raw.get("complete_through")); scoped=set(raw.get("pig_ids") or [])
    complete=bool(raw.get("complete") is True and through and through>=today and set(pig_ids)<=scoped)
    return {"complete":complete,"complete_through":_date_text(through) or None,"requested_count":len(pig_ids),"covered_count":len(set(pig_ids)&scoped),"reason":None if complete else "no complete-through coverage for every breeding animal"}


def _observations(rows, today):
    latest=_latest_valid(rows,"pig_id","observed_at",today);out={}
    for pig_id,row in latest.items():
        measurements=row.get("measurements_json") if isinstance(row.get("measurements_json"),dict) else {}
        out[pig_id]={"observed_at":_date_text(row.get("observed_at")),"observation_event_id":_text(row.get("observation_event_id")),**{key:measurements.get(key) for key in ("body_condition","body_condition_score","legs_sound","feet_sound","build_acceptable","visible_concern","heat") if key in measurements}}
        if "body_condition_score" in out[pig_id] and "body_condition" not in out[pig_id]: out[pig_id]["body_condition"]=out[pig_id].pop("body_condition_score")
    return out


def _performance(snapshot,pigs,litters,litter_conflicts,today):
    pairings, mating_conflicts = _unique_events(snapshot.get("mating_events") or [], "mating_id")
    pairings=[row for row in pairings if _date(row.get("mating_date")) and _date(row.get("mating_date"))<=today]
    weights=defaultdict(list)
    for row in snapshot.get("weight_events") or []: weights[_text(row.get("pig_id"))].append(row)
    litter_rows=[]
    for litter_id,row in sorted(litters.items()):
        if litter_id in litter_conflicts: continue
        born=row.get("born_alive"); weaned=row.get("weaned_count")
        if not isinstance(born,int) or isinstance(born,bool) or born<0: continue
        if weaned is not None and (not isinstance(weaned,int) or isinstance(weaned,bool) or not 0<=weaned<=born): continue
        children=[pig for pig in pigs.values() if _text(pig.get("litter_id"))==_text(row.get("litter_id"))]
        live=sum(1 for child in children if _norm(child.get("status"))=="active" and _truth(child.get("on_farm")))
        dead=sum(1 for child in children if _norm(child.get("status")) in {"dead","died"})
        growth=[]
        for child in children:
            ordered=sorted(weights.get(child["pig_id"],[]),key=lambda item:_date(item.get("weight_date")) or date.min)
            if len(ordered)>=2:
                days=(_date(ordered[-1]["weight_date"])-_date(ordered[0]["weight_date"])).days
                if days>0: growth.append(round((float(ordered[-1]["weight_kg"])-float(ordered[0]["weight_kg"]))/days,3))
        litter_rows.append({"litter_id":litter_id,"sow_pig_id":_text(row.get("sow_pig_id")),"boar_pig_id":_text(row.get("boar_pig_id")),"farrowing_date":_date_text(row.get("farrowing_date")),"wean_date":_date_text(row.get("wean_date")) or None,"born_alive":born,"stillborn_count":row.get("stillborn_count"),"weaned_count":weaned,"current_live_children":live,"recorded_dead_children":dead,"offspring_growth":"unknown" if not growth else "measured","mean_daily_gain_kg":round(sum(growth)/len(growth),3) if growth else None})
    counts=defaultdict(int)
    for row in pairings:
        counts[_text(row.get("sow_pig_id"))]+=1;counts[_text(row.get("boar_pig_id"))]+=1
    return {"pairings":sorted(pairings,key=lambda row:(_date_text(row.get("mating_date")),_text(row.get("mating_id")))),"litters":litter_rows,"service_counts":counts,"mating_conflicts":sorted(mating_conflicts),"litter_conflicts":sorted(litter_conflicts)}


def _reservation_active(source,row):
    if source in {"active_outlets","auction_members"}: return row.get("active") is True
    return _norm(row.get("reserved_status") or row.get("status")) in {"reserved","active","held","confirmed"}
def _reservation_ref(row): return next((_text(row.get(k)) for k in ("outlet_assignment_id","order_line_id","auction_cycle_id","reservation_id") if row.get(k)),"Unknown")
def _latest_valid(rows,key,date_field,today):
    out={}
    for row in rows:
        ident=_text(row.get(key)); stamp=_date(row.get(date_field))
        if not ident or stamp is None or stamp>today: continue
        marker=(stamp,_text(row.get("created_at") or row.get("recorded_at")),_text(row.get("location_event_id") or row.get("observation_event_id")))
        existing=out.get(ident)
        existing_marker=(_date(existing.get(date_field)),_text(existing.get("created_at") or existing.get("recorded_at")),_text(existing.get("location_event_id") or existing.get("observation_event_id"))) if existing else None
        if existing is None or marker>existing_marker: out[ident]=row
    return out
def _unique_events(rows,key):
    grouped=defaultdict(list)
    for row in rows:
        if _text(row.get(key)): grouped[_text(row.get(key))].append(dict(row))
    unique=[];conflicts=[]
    for ident,values in grouped.items():
        normalized={json.dumps(value,sort_keys=True,default=str,separators=(",",":")) for value in values}
        if len(normalized)>1: conflicts.append(ident)
        elif values: unique.append(values[0])
    return sorted(unique,key=lambda row:_text(row.get(key))),conflicts
def _animal_key(row): return (_text(row.get("tag_number")).lower(),_text(row.get("pig_id")))
def _truth(value): return value is True or _norm(value) in {"yes","true","1"}
def _norm(value): return _text(value).lower().replace(" ","_").replace("-","_")
def _text(value): return str(value or "").strip()
def _date(value):
    try:return date.fromisoformat(str(value)[:10])
    except (TypeError,ValueError):return None
def _date_text(value):
    parsed=_date(value);return parsed.isoformat() if parsed else ""
def _unavailable(reason): return {"success":False,"contract_version":CONTRACT_VERSION,"reason":reason,"writes_performed":False,"protected_actions_performed":False}
