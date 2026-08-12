"""Resolve typed owner breeding facts into HERDMASTER's canonical action packet."""
from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import os


def resolve_breeding_actions(facts, *, provider_timestamp, entity_loader=None):
    try:
        observed = datetime.fromisoformat(str(provider_timestamp or "").replace("Z", "+00:00"))
    except ValueError:
        observed = None
    if observed is None or observed.tzinfo is None:
        return {"success": False, "status": "breeding_provider_chronology_required"}
    if not isinstance(facts, (list, tuple)) or not facts:
        return {"success": False, "status": "complete_breeding_group_required"}
    entities = (entity_loader or load_current_breeding_entities)()
    lookup = _lookup(entities)
    actions, seen = [], set()
    for fact in facts:
        if not isinstance(fact, dict):
            return {"success": False, "status": "complete_breeding_group_required"}
        sow, conflict = _one(lookup, fact.get("sow"), sex="Female")
        if conflict:
            return {"success": False, "status": conflict, "entity": str(fact.get("sow") or "")}
        if sow["pig_id"] in seen:
            return {"success": False, "status": "duplicate_sow_in_group", "entity": str(fact.get("sow") or "")}
        seen.add(sow["pig_id"])
        kind = str(fact.get("kind") or "")
        row = {"pig_id": sow["pig_id"], "label": sow.get("name") or sow.get("tag_number") or sow["pig_id"],
               "action": kind}
        if kind == "exposure":
            boar, conflict = _one(lookup, fact.get("boar"), sex="Male")
            if conflict:
                return {"success": False, "status": conflict, "entity": str(fact.get("boar") or "")}
            try:
                started = date.fromisoformat(str(fact.get("exposure_started_on") or ""))
                days = int(fact.get("planned_days"))
            except (TypeError, ValueError):
                return {"success": False, "status": "exact_exposure_chronology_required"}
            if not 1 <= days <= 60:
                return {"success": False, "status": "exact_exposure_chronology_required"}
            row.update(boar_pig_id=boar["pig_id"], exposure_started_on=started.isoformat(),
                       planned_removal_on=(started + timedelta(days=days)).isoformat())
        elif kind == "recovery_hold":
            score = fact.get("body_condition_score")
            if not isinstance(score, (int, float)) or isinstance(score, bool):
                return {"success": False, "status": "body_condition_score_required"}
            row.update(body_condition_score=float(score), observed_at=observed.isoformat(),
                       factual_note=str(fact.get("factual_note") or
                           "Owner reports body condition and directs recovery hold."))
        elif kind == "near_farrowing":
            if fact.get("prior_mating_known") is not False or fact.get("father_known") is not False:
                return {"success": False, "status": "near_farrowing_unknowns_not_preserved"}
            row.update(observed_at=observed.isoformat(), factual_note=str(fact.get("factual_note") or
                "Owner reports she appears close to farrowing; prior mating date and father are unknown."))
        else:
            return {"success": False, "status": "supported_breeding_action_required"}
        actions.append(row)
    generation = _digest({"entities": sorted((_entity_generation(row) for row in entities),
                                               key=lambda row: row["pig_id"]),
                          "provider_timestamp": observed.isoformat()})
    return {"success": True, "status": "breeding_actions_resolved",
            "breeding_actions": actions, "row_count": len(actions),
            "evidence_generation": generation}


def load_current_breeding_entities():
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select pig_id,tag_number,name,sex,status,on_farm
                from public.current_canonical_pig_state
                where status='Active' and on_farm is true""")
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _lookup(entities):
    result = {}
    for row in entities if isinstance(entities, list) else ():
        if not isinstance(row, dict) or not str(row.get("pig_id") or ""):
            continue
        for label in (row.get("name"), row.get("tag_number"), row.get("pig_id")):
            key = str(label or "").strip().casefold()
            if key:
                bucket = result.setdefault(key, [])
                if not any(item["pig_id"] == row["pig_id"] for item in bucket):
                    bucket.append(row)
    return result


def _one(lookup, label, *, sex):
    rows = lookup.get(str(label or "").strip().casefold(), [])
    eligible = [row for row in rows if str(row.get("sex") or "").casefold() == sex.casefold()
                and str(row.get("status") or "").casefold() == "active" and row.get("on_farm") is True]
    if not eligible:
        return None, "canonical_breeding_entity_not_found"
    if len(eligible) != 1:
        return None, "canonical_breeding_entity_ambiguous"
    return eligible[0], ""


def _entity_generation(row):
    return {key: str(row.get(key) or "") for key in
            ("pig_id", "tag_number", "name", "sex", "status", "on_farm")}


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
