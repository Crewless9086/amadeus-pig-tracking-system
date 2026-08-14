"""HERDMASTER-owned, read-only evidence for Oom Sakkie's daily manager.

The producer owns cohort eligibility and mortality materiality.  Channel and
manager composers may present this contract, but must not reconstruct biology
from a broad active-pig list.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import hashlib
import json
import os

from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read

PACKET_TYPE = "herdmaster.daily_manager_evidence.v1"
ELIGIBILITY_VERSION = "HERDMASTER_WEEKLY_WEIGHT_ELIGIBILITY_V1"
MORTALITY_IDENTITY = "HERDMASTER-MORTALITY-CURRENT"
YOUNG_STAGES = {"piglet", "weaner", "grower"}
BREEDING_STAGES = {"sow", "boar"}


def build_daily_manager_evidence(*, pigs, window_weights, prior_weights,
                                 lifecycle_events=(), mortality_packet=None,
                                 prior_mortality_digest="", analysis_date):
    """Build one deterministic zero-I/O specialist contract."""
    analysis_date = _day(analysis_date)
    window_start = analysis_date - timedelta(days=analysis_date.weekday())
    window_end = window_start + timedelta(days=1)
    scheduled = {str(row.get("pig_id") or "") for row in lifecycle_events
                 if "weigh" in str(row.get("event_type") or "").casefold()
                 and window_start <= _day(row.get("effective_at")) <= window_end}
    groups = defaultdict(list)
    pig_by_id = {}
    for raw in pigs or ():
        row = dict(raw); pig_id = str(row.get("pig_id") or "")
        if not pig_id:
            continue
        pig_by_id[pig_id] = row
        status = str(row.get("status") or "").strip().casefold()
        on_farm = row.get("on_farm")
        stage = str(row.get("animal_type") or "").strip().casefold()
        purpose = str(row.get("purpose") or "").strip().casefold()
        item = _identity(row)
        if not status or on_farm is None or not stage:
            item["reason"] = "current eligibility evidence is incomplete"
            groups["unknown"].append(item)
        elif status != "active" or on_farm is not True:
            item["reason"] = "canonical pig is not both Active and on-farm"
            groups["inactive_off_farm"].append(item)
        elif stage in BREEDING_STAGES or purpose == "breeding":
            if pig_id in scheduled:
                item["reason"] = "canonical individual weighing schedule exists"
                groups["eligible"].append(item)
            else:
                item["reason"] = "breeding animal without an individual weighing schedule"
                groups["breeding_excluded"].append(item)
        elif stage not in YOUNG_STAGES:
            item["reason"] = "supported young/growing stage is not established"
            groups["unknown"].append(item)
        elif not _usable_tag(row.get("tag_number")):
            item["reason"] = "usable visible tag is absent or Unknown"
            groups["untagged"].append(item)
        else:
            item["reason"] = "Active, on-farm, young/growing and visibly tagged"
            groups["eligible"].append(item)

    by_pig = defaultdict(list)
    for raw in window_weights or ():
        row = dict(raw)
        if window_start <= _day(row.get("weight_date")) <= window_end:
            by_pig[str(row.get("pig_id") or "")].append(row)
    eligible_ids = {row["pig_id"] for row in groups["eligible"]}
    conflicts = []
    covered = set()
    governed_current = {}
    for pig_id in eligible_ids:
        rows = by_pig.get(pig_id, ())
        daily = defaultdict(list)
        for row in rows:
            daily[_day(row.get("weight_date"))].append(row)
        conflict_days = [day for day, values in daily.items()
                         if len({value.get("weight_kg") for value in values}) > 1]
        if conflict_days:
            conflicts.append({**_identity(pig_by_id[pig_id]),
                              "dates": [day.isoformat() for day in sorted(conflict_days)]})
        elif rows:
            covered.add(pig_id)
            governed_current[pig_id] = sorted(
                rows, key=lambda row: (_day(row.get("weight_date")),
                                       str(row.get("weight_event_id") or "")))[-1]

    prior_by_pig = defaultdict(list)
    for raw in prior_weights or ():
        row = dict(raw)
        if _day(row.get("weight_date")) < window_start:
            prior_by_pig[str(row.get("pig_id") or "")].append(row)
    findings = []
    for pig_id, current in governed_current.items():
        prior = _latest_unconflicted(prior_by_pig.get(pig_id, ()))
        if prior is None or prior.get("weight_kg") in (None, 0) or current.get("weight_kg") is None:
            continue
        change = float(current["weight_kg"]) - float(prior["weight_kg"])
        pct = 100 * change / float(prior["weight_kg"])
        if abs(pct) >= 10:
            findings.append({**_identity(pig_by_id[pig_id]),
                "prior_date": _day(prior["weight_date"]).isoformat(),
                "prior_kg": float(prior["weight_kg"]),
                "current_date": _day(current["weight_date"]).isoformat(),
                "current_kg": float(current["weight_kg"]),
                "change_kg": round(change, 3), "change_pct": round(pct, 2),
                "interpretation": "descriptive recorded change only; cause or abnormality is not established"})

    missing = sorted((row for row in groups["eligible"] if row["pig_id"] not in covered),
                     key=lambda row: (str(row.get("tag") or ""), row["pig_id"]))
    denominator = len(eligible_ids)
    weight = {
        "eligibility_rule_version": ELIGIBILITY_VERSION,
        "window": {"start": window_start.isoformat(), "end": window_end.isoformat(),
                   "timezone": "Africa/Johannesburg"},
        "historical_eligible_denominator": None,
        "historical_completion_percentage": None,
        "historical_status": "Unknown: current pig state cannot reconstruct historical eligibility",
        "current_snapshot": {"eligible_tagged": denominator, "covered": len(covered),
            "coverage_percentage": round(100 * len(covered) / denominator, 2) if denominator else None,
            "status": "conflicting" if conflicts else "complete" if denominator and not missing
                      else "unknown" if not denominator and groups["unknown"] else "partial"},
        "missing_eligible_tagged": missing,
        "breeding_excluded": groups["breeding_excluded"],
        "untagged_excluded": groups["untagged"],
        "inactive_off_farm": groups["inactive_off_farm"],
        "unknown_eligibility": groups["unknown"],
        "conflicting_weight_evidence": conflicts,
        "material_weight_findings": sorted(findings,
            key=lambda row: (-abs(row["change_pct"]), row["pig_id"])),
    }
    mortality_packet = dict(mortality_packet or {})
    mortality_digest = str(mortality_packet.get("evidence_digest") or "")
    mortality = {
        "review_identity": MORTALITY_IDENTITY,
        "evidence_digest": mortality_digest,
        "previous_consumed_digest": str(prior_mortality_digest or ""),
        "digest_changed": bool(mortality_digest and mortality_digest != prior_mortality_digest),
        "rolling_counts": mortality_packet.get("rolling_counts") or {},
        "candidate_deaths": list(mortality_packet.get("proven_facts") or []),
        "association_boundary": "associations are not diagnoses or proof of causation",
    }
    material = {"weight": weight, "mortality": mortality}
    return {"packet_type": PACKET_TYPE, "contract_version": PACKET_TYPE,
            "observed_at": datetime.now().astimezone().isoformat(),
            "material_digest": _digest(material), "weight": weight,
            "mortality": mortality,
            # Typed HERDMASTER packet retained for the existing durable Oom
            # Sakkie consumption rail; the composer never interprets it.
            "specialist_mortality_packet": mortality_packet,
            "authority": {"read_only": True, "writes_farm_data": False,
                          "hardware_commands": 0, "sends_messages": False}}


def load_daily_manager_evidence(*, analysis_date, database_url=None):
    """Load canonical Supabase truth through bounded read-only sessions."""
    analysis_date = _day(analysis_date)
    window_start = analysis_date - timedelta(days=analysis_date.weekday())
    window_end = window_start + timedelta(days=1)
    with connect_bounded_read(
            database_url=database_url or os.environ.get("DATABASE_URL")) as connection:
        with connection.cursor() as cursor:
            pigs = _rows(cursor, """select pig_id,tag_number,pig_name,status,on_farm,animal_type,purpose
                from public.current_canonical_pigs order by pig_id""")
            weights = _rows(cursor, """select weight_event_id,pig_id,weight_date,weight_kg
                from public.pig_weight_events where weight_date<=%s
                order by pig_id,weight_date,weight_event_id""", (window_end,))
            lifecycle = _rows(cursor, """select pig_id,lifecycle_event_type as event_type,effective_at
                from public.pig_lifecycle_events where effective_at::date between %s and %s
                order by effective_at,lifecycle_event_id""", (window_start, window_end))
            cursor.execute("""select review_json->'mortality_consumption'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_herdmaster_mortality_consumption'
                  and review_json->'mortality_consumption'->>'review_identity'=%s
                order by created_at desc,review_event_id desc limit 1""", (MORTALITY_IDENTITY,))
            row = cursor.fetchone()
            prior_digest = str(((row[0] if row else {}) or {}).get("evidence_digest") or "")
    from modules.pig_weights.herdmaster_mortality_evidence import load_current_mortality_evidence
    from modules.pig_weights.herdmaster_mortality_intelligence import build_oom_sakkie_mortality_packet
    mortality = build_oom_sakkie_mortality_packet(
        load_current_mortality_evidence(analysis_end=analysis_date,
                                        database_url=database_url or os.environ.get("DATABASE_URL")),
        analysis_end=analysis_date)
    return build_daily_manager_evidence(pigs=pigs,
        window_weights=[row for row in weights if _day(row["weight_date"]) >= window_start],
        prior_weights=[row for row in weights if _day(row["weight_date"]) < window_start],
        lifecycle_events=lifecycle, mortality_packet=mortality,
        prior_mortality_digest=prior_digest, analysis_date=analysis_date)


def _rows(cursor, sql, params=()):
    cursor.execute(sql, params)
    names = [column.name for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def _identity(row):
    tag = str(row.get("tag_number") or "").strip()
    return {"pig_id": str(row.get("pig_id") or ""), "tag": tag or None,
            "name": str(row.get("pig_name") or tag or "Unknown")}


def _usable_tag(value):
    return str(value or "").strip().casefold() not in {"", "unknown", "onbekend", "n/a", "na", "none", "null"}


def _latest_unconflicted(rows):
    if not rows:
        return None
    latest_day = max(_day(row.get("weight_date")) for row in rows)
    latest = [row for row in rows if _day(row.get("weight_date")) == latest_day]
    if len({row.get("weight_kg") for row in latest}) != 1:
        return None
    return sorted(latest, key=lambda row: str(row.get("weight_event_id") or ""))[-1]


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
        default=str).encode()).hexdigest().upper()
