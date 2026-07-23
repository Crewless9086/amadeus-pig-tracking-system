"""Herdmaster Operational V1: read-only herd intelligence over canonical farm truth."""

from __future__ import annotations

from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timezone
import hashlib
import json
import re
import threading
import time

from modules.charlie.agent_runtime import AgentDefinition
from modules.pig_weights.farm_supabase_read_service import (
    farm_supabase_reads_available, get_breeding_analytics, get_family_tree, get_litter_attention_summary,
    get_mating_overview, get_open_reservation_counts, get_pens, get_pig_detail, get_pig_master_rows,
)
from modules.pig_weights.pig_weights_service import get_sales_availability


HERDMASTER_DEFINITION = AgentDefinition(
    agent_id="herdmaster",
    name="Herdmaster",
    domain="farm",
    authority_tier="read_only",
    capabilities=("herd_inventory", "herd_overview", "sales_availability", "pen_occupancy", "weight_attention", "breeding_inventory", "breeding_planner", "pig_profile", "litter_attention"),
    source_contract=("Supabase pig_current_state", "Supabase pigs", "Supabase pens", "Supabase litters"),
    handler=lambda request: run_herdmaster(request),
    repair_handler=lambda request, _result, _gaps: run_herdmaster({**request, "capability": "herd_overview"}, force_broad=True),
)

SNAPSHOT_TTL_SECONDS = 30
_SNAPSHOT_CACHE = {}
_SNAPSHOT_LOCK = threading.Lock()


def run_herdmaster(request, *, readers=None, force_broad=False):
    request = request if isinstance(request, dict) else {}
    supplied_readers = readers is not None
    use_cache = readers is None
    readers = readers or {
        "pig_rows": get_pig_master_rows,
        "reservations": get_open_reservation_counts,
        "pens": get_pens,
        "litter_attention": get_litter_attention_summary,
        "pig_detail": get_pig_detail,
        "sales_availability": get_sales_availability,
        "mating_overview": get_mating_overview,
        "breeding_analytics": get_breeding_analytics,
        "family_tree": get_family_tree,
    }
    question = str(request.get("question") or request.get("goal") or "")
    capability = _select_capability(question, request.get("capability"), request.get("subject"))
    if capability == "breeding_planner":
        return _breeding_planner(request, readers, canonical_available=farm_supabase_reads_available() if not supplied_readers else True)
    if capability == "pig_profile":
        return _pig_profile(request, readers)
    if capability == "sales_availability":
        return _sales_availability(question, readers, use_cache)
    names = ["pig_rows"] if "pig_rows" in readers else ["dashboard", "active_pigs"]
    if force_broad or capability in {"herd_overview", "pen_occupancy"}:
        names.append("pens")
    if (force_broad or capability == "herd_overview") and "reservations" in readers:
        names.append("reservations")
    if force_broad or capability in {"herd_overview", "litter_attention"}:
        names.append("litter_attention")
    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        futures = {name: pool.submit(_cached_read, name, readers[name], use_cache) for name in names}
        loaded = {name: future.result() for name, future in futures.items()}
    return _herd_packet(question, capability, loaded)


def _select_capability(question, requested, subject):
    if str((subject or {}).get("pig_id") or "").strip():
        return "pig_profile"
    lower = str(question or "").lower()
    if re.search(r"\b(how many|count|total|number of)\b", lower) and re.search(r"\b(pig|pigs|herd|animals)\b", lower):
        return "herd_inventory"
    if any(word in lower for word in ("pen", "capacity", "overcrowd", "location")):
        return "pen_occupancy"
    if any(word in lower for word in ("weight", "weigh", "growth", "stale")):
        return "weight_attention"
    if requested == "breeding_planner" or any(word in lower for word in ("breeding calendar", "breeding planner", "mating reminder", "match a boar")):
        return "breeding_planner"
    if any(word in lower for word in ("sow", "boar", "gilt", "breed", "breeding")):
        return "breeding_inventory"
    if any(word in lower for word in ("litter", "wean", "piglet")):
        return "litter_attention"
    return str(requested or "herd_overview") if requested in HERDMASTER_DEFINITION.capabilities else "herd_overview"


def _herd_packet(question, capability, loaded):
    dashboard = loaded.get("dashboard") or {}
    pigs = list(loaded.get("active_pigs") or [])
    if "pig_rows" in loaded:
        rows = list(loaded.get("pig_rows") or [])
        on_farm_rows = [row for row in rows if str(row.get("On_Farm") or "").strip().lower() == "yes"]
        pigs = [_master_to_active(row) for row in on_farm_rows if str(row.get("Status") or "").strip().lower() == "active"]
        type_counts = Counter(str(row.get("Animal_Type") or "").strip().lower() for row in on_farm_rows)
        dashboard = {
            "on_farm_pigs": len(on_farm_rows),
            "boars": type_counts["boar"], "sows": type_counts["sow"], "gilts": type_counts["gilt"],
            "piglets": type_counts["piglet"], "weaners": type_counts["weaner"], "growers": type_counts["grower"], "finishers": type_counts["finisher"],
            "available_for_sale_pigs": sum(str(row.get("Status") or "").lower() == "active" and float(row.get("Current_Weight_Kg") or 0) >= 60 for row in on_farm_rows),
            "reserved_pigs": int((loaded.get("reservations") or {}).get("open_reserved_pigs") or 0),
        }
    pens = list(loaded.get("pens") or [])
    on_farm = int(dashboard.get("on_farm_pigs") or 0)
    active_count = len(pigs)
    by_type = {key: int(dashboard.get(key) or 0) for key in ("boars", "sows", "gilts", "piglets", "weaners", "growers", "finishers")}
    by_sex = dict(Counter(_label(row.get("sex"), "Unknown") for row in pigs))
    by_pen = dict(Counter(_label(row.get("current_pen_name") or row.get("current_pen_id"), "No pen recorded") for row in pigs))
    individually_managed = [row for row in pigs if str(row.get("animal_type") or "").strip().lower() != "piglet"]
    missing = {
        # Pre-wean piglets are managed through their litter and may legitimately
        # have no individual tag or weight yet.
        "tag": sum(not str(row.get("tag_number") or "").strip() for row in individually_managed),
        "pen": sum(not str(row.get("current_pen_id") or "").strip() for row in pigs),
        "weight": sum(row.get("current_weight_kg") in (None, "") for row in individually_managed),
    }
    anomalies = []
    if on_farm != active_count:
        anomalies.append({"code": "on_farm_active_status_mismatch", "count": abs(on_farm - active_count), "detail": f"{on_farm} records say on-farm while {active_count} are both Active and on-farm."})
    for field, count in missing.items():
        if count:
            anomalies.append({"code": f"active_pig_missing_{field}", "count": count, "detail": f"{count} active on-farm pig(s) have no {field} recorded."})
    if pens:
        capacities = {str(row.get("pen_name") or row.get("pen_id") or ""): int(row.get("capacity") or 0) for row in pens}
        for pen, count in by_pen.items():
            capacity = capacities.get(pen, 0)
            if capacity and count > capacity:
                anomalies.append({"code": "pen_over_capacity", "count": count - capacity, "detail": f"{pen} has {count} active pigs against capacity {capacity}."})
    direct = _direct_answer(capability, on_farm, by_type, by_sex, by_pen, missing, loaded)
    recommendations = [item["detail"] for item in anomalies[:3]]
    if not recommendations:
        recommendations = ["No immediate herd-record exception was found in the requested view."]
    now = datetime.now(timezone.utc).isoformat()
    return {
        "success": True,
        "status": "herdmaster_evidence_ready",
        "capability": capability,
        "direct_answer": direct,
        "facts": [
            {"name": "pigs_physically_on_farm", "value": on_farm, "definition": "Canonical pigs with on_farm=true."},
            {"name": "active_on_farm_pigs", "value": active_count, "definition": "Canonical pigs with status Active and on_farm=true."},
            {"name": "reserved_pigs", "value": int(dashboard.get("reserved_pigs") or 0)},
        ],
        "metrics": {"on_farm_total": on_farm, "active_on_farm": active_count, "reserved": int(dashboard.get("reserved_pigs") or 0), "available_for_sale": int(dashboard.get("available_for_sale_pigs") or 0)},
        "breakdown": {"by_type": by_type, "by_sex": by_sex, "by_pen": by_pen},
        "anomalies": anomalies,
        "inferences": [],
        "recommendations": recommendations,
        "unresolved_questions": [],
        "sources": [
            {"name": "pig_current_state", "authority": "canonical", "fields": ["status", "on_farm", "animal_type", "sex", "weight", "pen"]},
            {"name": "pigs", "authority": "canonical lifecycle identity"},
            *([{"name": "pens", "authority": "canonical physical location"}] if pens else []),
            *([{"name": "litters", "authority": "canonical litter workflow"}] if loaded.get("litter_attention") is not None else []),
        ],
        "freshness": {"observed_at": now, "mode": "live_read", "source": "supabase_canonical"},
        "confidence": 0.99 if not any(item["code"] == "on_farm_active_status_mismatch" for item in anomalies) else 0.94,
        "summary": str(direct),
        "question": question,
    }


def _direct_answer(capability, on_farm, by_type, by_sex, by_pen, missing, loaded):
    if capability == "herd_inventory":
        return f"There are {on_farm} pigs physically recorded on the farm."
    if capability == "breeding_inventory":
        return f"The on-farm breeding inventory records {by_type['sows']} sows, {by_type['gilts']} gilts and {by_type['boars']} boars."
    if capability == "pen_occupancy":
        busiest = sorted(by_pen.items(), key=lambda row: (-row[1], row[0]))[:3]
        return "The largest active pen groups are " + (", ".join(f"{name}: {count}" for name, count in busiest) if busiest else "not currently recorded") + "."
    if capability == "weight_attention":
        return f"{missing['weight']} of the active on-farm pigs have no current weight in the canonical read model."
    if capability == "litter_attention":
        attention = loaded.get("litter_attention") or {}
        count = int(attention.get("attention_count") or len(attention.get("litters") or attention.get("items") or [])) if isinstance(attention, dict) else len(attention or [])
        return f"Herdmaster found {count} litter attention item(s) in the current canonical view."
    return f"The farm currently records {on_farm} pigs on-farm, including {by_type['piglets']} piglets, {by_type['weaners']} weaners, {by_type['growers']} growers and {by_type['finishers']} finishers."


def _pig_profile(request, readers):
    pig_id = str((request.get("subject") or {}).get("pig_id") or "").strip().upper()
    detail = readers["pig_detail"](pig_id) if pig_id else None
    if not detail:
        return {"success": False, "status": "pig_not_found", "direct_answer": "", "sources": [], "freshness": {}, "confidence": 0, "unresolved_questions": [f"Pig {pig_id or 'ID'} was not found."]}
    return {
        "success": True, "status": "herdmaster_pig_profile_ready", "capability": "pig_profile",
        "direct_answer": f"Pig {detail.get('tag_number') or pig_id} is {detail.get('status') or 'status unknown'}, {detail.get('sex') or 'sex unknown'}, in {detail.get('current_pen_name') or detail.get('current_pen_id') or 'no recorded pen'}.",
        "facts": [{"name": key, "value": detail.get(key)} for key in ("pig_id", "tag_number", "status", "on_farm", "sex", "current_weight_kg", "current_pen_id", "purpose")],
        "metrics": {}, "breakdown": {}, "anomalies": [], "inferences": [], "recommendations": [], "unresolved_questions": [],
        "sources": [{"name": "pig_current_state", "authority": "canonical"}, {"name": "pigs", "authority": "canonical lifecycle identity"}],
        "freshness": {"observed_at": datetime.now(timezone.utc).isoformat(), "mode": "live_read", "source": "supabase_canonical"}, "confidence": 0.99,
        "summary": f"Herdmaster verified pig {detail.get('tag_number') or pig_id}.", "detail": detail,
    }


def _sales_availability(question, readers, use_cache=False):
    rows = list(_cached_read("sales_availability", readers["sales_availability"], use_cache) or [])
    eligible = [row for row in rows if str(row.get("availability_status") or row.get("status") or "").strip().lower() in {"available", "ready", "available_for_sale"} or row.get("available_for_sale") is True]
    # The canonical service already excludes unsafe candidates; preserve its
    # rows and provenance for SAM instead of reimplementing eligibility here.
    effective = eligible if eligible else rows
    return {
        "success": True, "status": "herdmaster_sales_availability_ready", "capability": "sales_availability",
        "direct_answer": f"Herdmaster found {len(effective)} canonical live-stock sale candidate(s) for SAM to evaluate.",
        "facts": [{"name": "live_stock_candidate_count", "value": len(effective)}],
        "metrics": {"candidate_count": len(effective)}, "breakdown": {}, "anomalies": [], "inferences": [],
        "recommendations": ["SAM must match customer requirements before preparing an offer."], "unresolved_questions": [],
        "sources": [{"name": "sales_availability", "authority": "Herdmaster/Pig Allocation canonical read model"}],
        "freshness": {"observed_at": datetime.now(timezone.utc).isoformat(), "mode": "live_read", "source": "supabase_canonical"},
        "confidence": 0.99, "summary": f"Herdmaster supplied {len(effective)} governed live-stock candidate(s).",
        "availability_rows": effective, "question": question,
    }


_BREEDING_FORBIDDEN_ACTIONS = [
    "create or change a mating, pregnancy, litter, lifecycle, purpose, or farm record",
    "send a reminder, customer communication, public post, payment, reservation, or stock promise",
    "write to Supabase, Google Sheets, a scheduler, or a notification service",
]


def _breeding_planner(request, readers, *, canonical_available):
    """Return canonical, calculated advisory facts only; never use mating_service fallback."""
    if not canonical_available:
        return _breeding_needs_data("Canonical Supabase farm reads are unavailable; no legacy fallback was used.")
    required = ("pig_rows", "mating_overview", "breeding_analytics", "family_tree")
    if any(name not in readers for name in required):
        return _breeding_needs_data("Canonical breeding reader contract is incomplete.")
    try:
        pigs, matings = list(readers["pig_rows"]() or []), list(readers["mating_overview"]() or [])
        analytics = readers["breeding_analytics"]() or {}
        metrics = {str(row.get("pig_id") or ""): row for group in (analytics.get("sows", []), analytics.get("boars", [])) for row in group}
    except (AttributeError, KeyError, RuntimeError, TypeError, ValueError, OSError):
        return _breeding_needs_data("Canonical Supabase breeding read failed; no legacy fallback was used.")
    females = [row for row in pigs if _is_breeding_female(row)]
    potential_boars = [row for row in pigs if str(row.get("Sex") or "") in {"Male", "Castrated_Male"}]
    packets = []
    for female in females:
        female_id = str(female.get("Pig_ID") or "")
        try:
            female_tree = readers["family_tree"](female_id)
            state, reminders = _female_lifecycle(female_id, matings)
            missing = _missing_breeding_facts(female, female_tree, metrics.get(female_id))
            matches, excluded = [], []
            if not missing and state == "No Active Mating":
                for boar in potential_boars:
                    boar_id = str(boar.get("Pig_ID") or "")
                    reason = _boar_exclusion(female, boar, female_tree, readers["family_tree"](boar_id), metrics.get(boar_id))
                    if reason:
                        excluded.append({"pig_id": boar_id, "reason": reason})
                    else:
                        matches.append({"pig_id": boar_id, "tag_number": str(boar.get("Tag_Number") or boar_id), "rank": 1, "basis": ["active", "on_farm", "breeding_purpose", "known_non_kinship", "condition_present", "performance_present"]})
            packets.append({"pig_id": female_id, "tag_number": str(female.get("Tag_Number") or female_id), "state": state, "missing_facts": missing, "safe_matches": matches, "excluded_matches": excluded, "advisory_calendar": reminders, "advisory_only": True, "owner_action": "Review the cited canonical facts and decide whether to use an approved mating workflow."})
        except (AttributeError, KeyError, RuntimeError, TypeError, ValueError, OSError):
            return _breeding_needs_data("Canonical Supabase breeding read failed; no legacy fallback was used.")
    fingerprint = hashlib.sha256(json.dumps({"pigs": pigs, "matings": matings, "analytics": analytics}, sort_keys=True, default=str).encode()).hexdigest()[:20]
    missing_any = any(item["missing_facts"] for item in packets)
    return {"success": True, "status": "breeding_planner_advisory_ready", "capability": "breeding_planner", "direct_answer": "Herdmaster prepared a read-only breeding advisory packet; it does not create matches or reminders.", "read_only": True, "advisory_only": True, "response_fingerprint": fingerprint, "freshness": {"observed_at": datetime.now(timezone.utc).isoformat(), "mode": "live_read", "source": "supabase_canonical"}, "confidence": 0.96 if packets and not missing_any else 0.0, "females": packets, "missing_facts": sorted({fact for item in packets for fact in item["missing_facts"]}), "owner_action": "Owner review is required before any mating or lifecycle action.", "forbidden_actions": _BREEDING_FORBIDDEN_ACTIONS, "sources": [{"name": "pigs", "authority": "canonical"}, {"name": "mating_events", "authority": "canonical"}, {"name": "breeding_analytics", "authority": "canonical"}, {"name": "family_tree", "authority": "canonical"}]}


def _breeding_needs_data(reason):
    return {"success": False, "status": "breeding_planner_needs_data", "capability": "breeding_planner", "direct_answer": reason, "read_only": True, "advisory_only": True, "confidence": 0.0, "females": [], "missing_facts": [reason], "owner_action": "Restore canonical read availability or capture the missing canonical facts; do not use legacy data.", "forbidden_actions": _BREEDING_FORBIDDEN_ACTIONS, "sources": [], "freshness": {"mode": "unavailable", "source": "supabase_canonical"}}


def _is_breeding_female(row):
    return str(row.get("Sex") or "") == "Female" and str(row.get("Status") or "") == "Active" and str(row.get("On_Farm") or "") == "Yes" and str(row.get("Purpose") or "") == "Breeding"


def _is_breeding_boor_candidate(row):
    return str(row.get("Sex") or "") == "Male" and str(row.get("Status") or "") == "Active" and str(row.get("On_Farm") or "") == "Yes" and str(row.get("Purpose") or "") == "Breeding"


def _female_lifecycle(female_id, matings):
    active = [row for row in matings if str(row.get("sow_pig_id") or "") == female_id and str(row.get("is_open") or "") == "Yes"]
    if not active:
        return "No Active Mating", []
    row = active[0]
    if str(row.get("is_overdue_farrowing") or "") == "Yes":
        return "Overdue Farrowing", [{"kind": "overdue_farrowing", "mating_id": row.get("mating_id"), "due_date": row.get("expected_farrowing_date")}]
    if str(row.get("is_overdue_check") or "") == "Yes":
        return "Overdue Check", [{"kind": "overdue_check", "mating_id": row.get("mating_id"), "due_date": row.get("expected_pregnancy_check_date")}]
    return "Active Mating", [{"kind": "active_mating", "mating_id": row.get("mating_id"), "due_date": row.get("expected_pregnancy_check_date") or row.get("expected_farrowing_date")}]


def _missing_breeding_facts(row, tree, metric):
    missing = []
    if not tree or not tree.get("mother") or not tree.get("father"):
        missing.append("parentage")
    if not str(row.get("General_Notes") or "").strip():
        missing.append("condition")
    if not metric or not int(metric.get("mating_count") or 0):
        missing.append("performance")
    return missing


def _boar_exclusion(female, boar, female_tree, boar_tree, metric):
    if str(boar.get("Sex") or "") == "Castrated_Male":
        return "castrated_male"
    if str(boar.get("Sex") or "") != "Male":
        return "not_male"
    if str(boar.get("Status") or "") != "Active":
        return "not_active"
    if str(boar.get("On_Farm") or "") != "Yes":
        return "off_farm"
    if str(boar.get("Purpose") or "") != "Breeding":
        return "non_breeding_purpose"
    if not str(boar.get("General_Notes") or "").strip():
        return "condition_missing"
    if not boar_tree or not boar_tree.get("mother") or not boar_tree.get("father") or not metric or not int(metric.get("mating_count") or 0):
        return "unknown_or_incomplete"
    female_id, boar_id = str(female.get("Pig_ID") or ""), str(boar.get("Pig_ID") or "")
    female_parents = {str((female_tree.get(key) or {}).get("pig_id") or "") for key in ("mother", "father")} - {""}
    boar_parents = {str((boar_tree.get(key) or {}).get("pig_id") or "") for key in ("mother", "father")} - {""}
    if boar_id in female_parents or female_id in boar_parents:
        return "parent_child"
    return "known_sibling" if female_parents & boar_parents else ""


def _label(value, fallback):
    return str(value or "").strip() or fallback


def _master_to_active(row):
    return {
        "pig_id": row.get("Pig_ID"), "tag_number": row.get("Tag_Number"), "status": row.get("Status"),
        "on_farm": row.get("On_Farm"), "animal_type": row.get("Animal_Type"), "sex": row.get("Sex"),
        "current_weight_kg": row.get("Current_Weight_Kg"), "last_weight_date": row.get("Last_Weight_Date"),
        "current_pen_id": row.get("Current_Pen_ID"), "current_pen_name": row.get("Current_Pen_ID"),
    }


def _cached_read(name, reader, enabled):
    if not enabled:
        return reader()
    now = time.monotonic()
    with _SNAPSHOT_LOCK:
        cached = _SNAPSHOT_CACHE.get(name)
        if cached and now < cached[0]:
            return cached[1]
    value = reader()
    with _SNAPSHOT_LOCK:
        _SNAPSHOT_CACHE[name] = (time.monotonic() + SNAPSHOT_TTL_SECONDS, value)
    return value
