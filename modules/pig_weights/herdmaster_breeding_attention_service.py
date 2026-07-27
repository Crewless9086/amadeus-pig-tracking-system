"""Pure, owner-only Breeding Attention Phase 1 aggregation."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timezone
from time import monotonic

CONTRACT_VERSION = "herdmaster_breeding_attention_v1"
FILTERS = (
    "Ready for review",
    "Needs observation",
    "Hold",
    "Recently mated",
    "Pregnancy evidence",
    "Post-litter recovery",
    "Needs Data",
)
DEFAULT_LINEAGE_MAX_DEPTH = 3
DEFAULT_LINEAGE_MAX_NODES = 256
DEFAULT_LINEAGE_MAX_QUERIES = 1
DEFAULT_LINEAGE_DEADLINE_SECONDS = 2.0


def build_bounded_family_evidence(
    master_rows,
    pig_ids,
    *,
    max_depth=DEFAULT_LINEAGE_MAX_DEPTH,
    max_nodes=DEFAULT_LINEAGE_MAX_NODES,
    max_query_count=DEFAULT_LINEAGE_MAX_QUERIES,
    deadline_seconds=DEFAULT_LINEAGE_DEADLINE_SECONDS,
    now_fn=monotonic,
):
    """Project deterministic lineage from one already-batched canonical read."""
    started = now_fn()
    if not isinstance(master_rows, list) or max_query_count < 1:
        return _family_unavailable("Canonical family inventory is unavailable.", 0)
    lookup = {}
    malformed_ids = set()
    for row in master_rows:
        if not isinstance(row, dict):
            continue
        pig_id = str(row.get("Pig_ID") or "").strip()
        if not pig_id or pig_id in lookup:
            if pig_id:
                malformed_ids.add(pig_id)
            continue
        lookup[pig_id] = row
    requested = sorted({str(value or "").strip() for value in pig_ids if str(value or "").strip()})
    by_pig = {}
    exhausted = False
    for root_id in requested:
        if now_fn() - started > deadline_seconds:
            exhausted = True
            by_pig[root_id] = _partial_tree(root_id, "lineage_deadline_exhausted")
            continue
        root = lookup.get(root_id)
        if root is None or root_id in malformed_ids:
            by_pig[root_id] = _partial_tree(root_id, "current_animal_link_missing_or_malformed")
            continue
        queue = [(root_id, 0, ())]
        visited = set()
        missing, cycles, malformed = set(), set(), set()
        while queue:
            current_id, depth, path = queue.pop(0)
            if now_fn() - started > deadline_seconds:
                exhausted = True
                missing.add("lineage_deadline_exhausted")
                break
            if current_id in path:
                cycles.add(current_id)
                continue
            if current_id in visited:
                continue
            if len(visited) >= max_nodes:
                missing.add("lineage_node_limit_exhausted")
                break
            visited.add(current_id)
            current = lookup.get(current_id)
            if current is None:
                missing.add(current_id)
                continue
            if depth >= max_depth:
                continue
            for field in ("Mother_Pig_ID", "Father_Pig_ID"):
                parent_id = str(current.get(field) or "").strip()
                if not parent_id:
                    missing.add(f"{current_id}:{field}")
                elif parent_id == current_id or parent_id in path:
                    cycles.add(parent_id)
                elif parent_id not in lookup:
                    missing.add(parent_id)
                elif parent_id in malformed_ids:
                    malformed.add(parent_id)
                else:
                    queue.append((parent_id, depth + 1, path + (current_id,)))
        mother_id = str(root.get("Mother_Pig_ID") or "").strip()
        father_id = str(root.get("Father_Pig_ID") or "").strip()
        reasons = []
        if missing:
            reasons.append("incomplete_lineage")
        if cycles:
            reasons.append("lineage_cycle")
        if malformed:
            reasons.append("malformed_lineage_link")
        by_pig[root_id] = {
            "pig_id": root_id,
            "mother": {"pig_id": mother_id} if mother_id and mother_id in lookup else None,
            "father": {"pig_id": father_id} if father_id and father_id in lookup else None,
            "lineage_status": "complete" if not reasons else "partial",
            "lineage_depth_limit": max_depth,
            "lineage_node_count": len(visited),
            "missing_links": sorted(missing),
            "cycle_nodes": sorted(cycles),
            "malformed_links": sorted(malformed),
            "reasons": reasons,
        }
    partial_count = sum(item["lineage_status"] != "complete" for item in by_pig.values())
    return {
        "success": True,
        "status": "partial" if partial_count or exhausted else "complete",
        "by_pig": by_pig,
        "requested_count": len(requested),
        "complete_count": len(requested) - partial_count,
        "partial_count": partial_count,
        "query_count": 1,
        "limits": {
            "max_depth": max_depth,
            "max_nodes": max_nodes,
            "max_query_count": max_query_count,
            "deadline_seconds": deadline_seconds,
        },
    }


def build_breeding_attention(
    readiness,
    *,
    matings=None,
    litters=None,
    analytics=None,
    family_trees=None,
    observations=None,
    generated_at=None,
    today=None,
):
    now = generated_at or datetime.now(timezone.utc).isoformat()
    today = today or date.today()
    envelope = readiness if isinstance(readiness, dict) else {}
    rows = envelope.get("pigs")
    if envelope.get("success") is not True or not isinstance(rows, list):
        return _unavailable(now, "Canonical readiness envelope is unavailable or malformed.")
    if not _available_envelope(matings, "records") or not _available_envelope(litters, "litters"):
        return _unavailable(now, "Canonical mating or litter evidence is unavailable or malformed.")
    if not isinstance(analytics, dict) or analytics.get("success") is not True:
        return _unavailable(now, "Canonical breeding analytics are unavailable or malformed.")
    matings = _rows(matings, "records")
    litters = _rows(litters, "litters")
    if not _map_envelope(family_trees) or not _map_envelope(observations):
        return _unavailable(now, "Canonical family-tree or observation evidence is unavailable.")
    family_source = family_trees
    observation_source = observations
    family_trees = family_source["by_pig"]
    observations = observation_source["by_pig"]
    mating_by_sow = _latest_by(matings, "sow_pig_id", ("mating_date", "recorded_at"))
    litter_by_sow = _latest_by(litters, "sow_pig_id", ("farrowing_date", "birth_date", "recorded_at"))
    metrics = {str(row.get("pig_id") or ""): row for row in analytics.get("sows", []) if isinstance(row, dict)}
    females = []
    for row in rows:
        if not _current_female(row):
            continue
        pig_id = str(row.get("pig_id") or "").strip()
        females.append(
            _attention_row(
                row,
                mating_by_sow.get(pig_id),
                litter_by_sow.get(pig_id),
                metrics.get(pig_id),
                family_trees.get(pig_id),
                observations.get(pig_id),
                today,
                envelope.get("observation_timestamp") or envelope.get("observed_at") or envelope.get("generated_date"),
            )
        )
    females.sort(key=lambda item: (item["attention_rank"], item["tag_number"], item["pig_id"]))
    counts = Counter(item["filter_state"] for item in females)
    return {
        "success": True,
        "contract_version": CONTRACT_VERSION,
        "generated_at": now,
        "source": envelope.get("source") or "canonical_readiness",
        "observation_timestamp": envelope.get("observation_timestamp") or envelope.get("observed_at") or envelope.get("generated_date"),
        "source_status": "Available" if _freshness(envelope.get("generated_date") or envelope.get("observation_timestamp"), today) != "Unavailable" else "Unavailable",
        "evidence_sources": {
            "readiness": "Available",
            "matings": "Available",
            "litters": "Available",
            "family_tree": "Available" if family_source.get("status") == "complete" else "Partial",
            "observations": "Available",
        },
        "lineage_summary": {
            "status": family_source.get("status", "partial"),
            "requested_count": family_source.get("requested_count", len(females)),
            "complete_count": family_source.get("complete_count"),
            "partial_count": family_source.get("partial_count"),
            "query_count": family_source.get("query_count"),
            "limits": family_source.get("limits", {}),
        },
        "allocation_read_progress": envelope.get("source_read_progress", {
            "status": "not_exposed",
            "shared_snapshot": False,
        }),
        "filters": list(FILTERS),
        "counts": {name: counts.get(name, 0) for name in FILTERS},
        "female_count": len(females),
        "inventory_status": "complete",
        "evidence_status": "partial" if any(item["missing_facts"] or item["conflicting_facts"] for item in females) else "complete",
        "counts_reconcile": sum(counts.values()) == len(females),
        "animals": females,
        "limitations": [
            "Advisory attention only; no mating, pregnancy, heat, health or body-condition fact is inferred.",
            "Missing or conflicting evidence is Needs Data.",
        ],
        "owner_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def _attention_row(row, mating, litter, metric, tree, observation, today, observed_at):
    missing = []
    conflicts = []
    medical = _norm(row.get("medical_status") or row.get("health_status"))
    withdrawal = _norm(row.get("withdrawal_evidence_state"))
    availability = _norm(row.get("available_for_breeding"))
    observation = observation if isinstance(observation, dict) else {}
    heat = _norm(observation.get("heat_state"))
    pregnancy = _norm((mating or {}).get("pregnancy_check_result") or (mating or {}).get("mating_status"))
    body_condition = observation.get("body_condition_score")
    if medical not in {"clear", "eligible"}:
        (missing if not medical or medical in {"unknown", "unavailable"} else conflicts).append("medical status")
    if withdrawal not in {"cleared", "not_applicable"}:
        (missing if withdrawal in {"", "unknown", "unavailable"} else conflicts).append("withdrawal evidence")
    if availability not in {"available", "yes", "true"}:
        (missing if availability in {"", "unknown", "unavailable"} else conflicts).append("availability")
    if heat not in {"observed", "standing"}:
        missing.append("current heat observation")
    if body_condition in (None, ""):
        missing.append("body condition")
    if not isinstance(tree, dict) or not tree.get("mother") or not tree.get("father"):
        missing.append("family-tree constraints")
    elif tree.get("lineage_status") not in (None, "complete"):
        missing.append("incomplete family-tree expansion")
    if _norm(row.get("purpose")) != "breeding":
        conflicts.append("purpose is not affirmatively Breeding")
    mating_date = _date((mating or {}).get("mating_date"))
    litter_date = _date((litter or {}).get("farrowing_date") or (litter or {}).get("birth_date"))
    if pregnancy in {"pregnant", "confirmed", "confirmed_pregnant"} and not mating_date:
        conflicts.append("pregnancy evidence has no mating chronology")

    state, action, rank = "Needs Data", "verify mating history", 70
    if medical in {"hold", "medical_hold"} or withdrawal == "hold" or availability in {"hold", "unavailable"}:
        state, action, rank = "Hold", "veterinary/medical review required", 10
    elif conflicts:
        state, action, rank = "Needs Data", "owner decision required", 15
    elif _norm((mating or {}).get("is_overdue_farrowing")) == "yes":
        state, action, rank = "Expected to farrow — overdue evidence review", "owner decision required", 22
    elif _norm((mating or {}).get("is_overdue_check")) == "yes":
        state, action, rank = "Pregnancy check overdue", "verify mating history", 24
    elif pregnancy in {"pregnant", "confirmed", "confirmed_pregnant"}:
        state, action, rank = "Pregnancy evidence", "no action currently required", 30
    elif mating_date and (today - mating_date).days <= 35:
        state, action, rank = "Recently mated", "verify mating history", 35
    elif litter_date and (today - litter_date).days <= 56:
        state, action, rank = "Post-litter recovery", "review post-litter recovery", 40
    elif missing:
        state, action, rank = "Needs observation", "observe for standing heat", 50
        if any(item in missing for item in (
            "medical status", "withdrawal evidence", "availability",
            "family-tree constraints", "incomplete family-tree expansion",
        )):
            state, action, rank = "Needs Data", "owner decision required", 20
    else:
        state, action, rank = "Ready for review", "confirm body condition manually", 60
    return {
        "pig_id": str(row.get("pig_id") or ""),
        "tag_number": str(row.get("tag_number") or ""),
        "animal_href": f"/pig/{str(row.get('pig_id') or '')}",
        "current_state": state,
        "filter_state": _filter_for_state(state),
        "recommended_human_action": action,
        "attention_rank": rank,
        "evidence_dates": {
            "observed_at": observed_at,
            "latest_mating": mating_date.isoformat() if mating_date else None,
            "latest_litter": litter_date.isoformat() if litter_date else None,
        },
        "freshness": _freshness(observed_at, today),
        "confidence": "High" if not missing and not conflicts else ("Low" if conflicts else "Limited"),
        "missing_facts": sorted(set(missing)),
        "conflicting_facts": sorted(set(conflicts)),
        "advisory_only": True,
    }


def _current_female(row):
    return (
        isinstance(row, dict)
        and _norm(row.get("sex")) == "female"
        and _norm(row.get("animal_type")) in {"sow", "gilt"}
        and _norm(row.get("status")) == "active"
        and _norm(row.get("on_farm")) in {"yes", "true", "1"}
    )


def _rows(value, key):
    if isinstance(value, list):
        return [row for row in value if isinstance(row, dict)]
    if isinstance(value, dict) and isinstance(value.get(key), list):
        return [row for row in value[key] if isinstance(row, dict)]
    return []


def _available_envelope(value, key):
    if isinstance(value, list):
        return True
    return isinstance(value, dict) and value.get("success") is True and isinstance(value.get(key), list)


def _map_envelope(value):
    return isinstance(value, dict) and value.get("success") is True and isinstance(value.get("by_pig"), dict)


def _filter_for_state(state):
    if state in FILTERS:
        return state
    if state in {"Pregnancy check overdue", "Expected to farrow — overdue evidence review"}:
        return "Pregnancy evidence"
    return "Needs Data"


def _latest_by(rows, key, dates):
    result = {}
    for row in rows:
        identity = str(row.get(key) or "")
        if not identity:
            continue
        current = result.get(identity)
        stamp = next((str(row.get(name) or "") for name in dates if row.get(name)), "")
        old = next((str(current.get(name) or "") for name in dates if current and current.get(name)), "")
        if current is None or stamp > old:
            result[identity] = row
    return result


def _date(value):
    try:
        return date.fromisoformat(str(value or "")[:10])
    except ValueError:
        return None


def _norm(value):
    return str(value or "").strip().lower().replace(" ", "_")


def _freshness(value, today):
    parsed = _date(value)
    if not parsed:
        return "Unavailable"
    age = (today - parsed).days
    return "Fresh" if 0 <= age <= 1 else "Stale"


def _unavailable(now, reason):
    return {
        "success": False,
        "contract_version": CONTRACT_VERSION,
        "generated_at": now,
        "source_status": "Unavailable",
        "counts": {name: None for name in FILTERS},
        "female_count": None,
        "inventory_status": "unavailable",
        "evidence_status": "unavailable",
        "counts_reconcile": None,
        "animals": [],
        "limitations": [reason],
        "owner_only": True,
        "writes_performed": False,
        "protected_actions_performed": False,
    }


def _partial_tree(pig_id, reason):
    return {
        "pig_id": pig_id,
        "mother": None,
        "father": None,
        "lineage_status": "partial",
        "lineage_depth_limit": 0,
        "lineage_node_count": 0,
        "missing_links": [reason],
        "cycle_nodes": [],
        "malformed_links": [],
        "reasons": [reason],
    }


def _family_unavailable(reason, query_count):
    return {
        "success": False,
        "status": "unavailable",
        "by_pig": {},
        "requested_count": None,
        "complete_count": None,
        "partial_count": None,
        "query_count": query_count,
        "limitations": [reason],
    }
