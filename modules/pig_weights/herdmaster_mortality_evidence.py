"""Canonical read-only evidence loader for HERDMASTER mortality intelligence."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
import os
from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read


def load_current_mortality_evidence(*, analysis_end: date, database_url=None):
    start = analysis_end - timedelta(days=179)
    url = database_url or os.environ["DATABASE_URL"]
    with connect_bounded_read(database_url=url) as db:
        deaths = _rows(db.execute("""select pig_id,exit_date,exit_reason,litter_id,initial_pen_id,status
            from public.current_canonical_pigs
            where lower(coalesce(status,'')) in ('dead','died','deceased')
               or lower(coalesce(exit_reason,'')) in
                  ('died','dead','deceased','lost','stillborn','died_after_birth','crushed_by_sow','weak_piglet','unknown')
            order by pig_id"""))
        historical_deaths = _rows(db.execute("""select pig_id,exit_date,exit_reason,litter_id,initial_pen_id,status
            from public.pigs where lower(coalesce(status,'')) in ('dead','died','deceased')
               or lower(coalesce(exit_reason,'')) in
                  ('died','dead','deceased','lost','stillborn','died_after_birth','crushed_by_sow','weak_piglet','unknown')
            order by pig_id"""))
        litters = _rows(db.execute("""select litter_id,farrowing_date,sow_pig_id,boar_pig_id,born_alive,weaned_count
            from public.current_canonical_litters order by litter_id"""))
        affected = sorted({str(row["pig_id"]) for row in deaths+historical_deaths})
        weights = (_rows(db.execute("""select weight_event_id,pig_id,weight_date,weight_kg
            from public.pig_weight_events where pig_id=any(%s)
            order by pig_id,weight_date,weight_event_id""", (affected,))) if affected else [])
        weather = _rows(db.execute("""select rollup_date,temperature_min_c,coverage_pct
            from public.weather_daily_rollups where rollup_date between %s and %s
            order by rollup_date""", (analysis_end-timedelta(days=89), analysis_end)))
    return normalize_current_mortality_evidence(deaths=deaths, historical_deaths=historical_deaths,
        litters=litters, weights=weights, weather=weather, analysis_end=analysis_end)


def normalize_current_mortality_evidence(*, deaths, historical_deaths, litters, weights,
                                         weather, analysis_end: date):
    """Normalize query rows without granting write or causal authority."""
    start = analysis_end - timedelta(days=179)
    undated = defaultdict(list)
    for row in historical_deaths:
        if not row.get("exit_date"):
            undated[str(row.get("litter_id") or "")].append(str(row["pig_id"]))
    representations=defaultdict(list)
    for row in litters:
        signature=(str(row.get("sow_pig_id") or ""),str(row.get("boar_pig_id") or ""),
                   str(row.get("farrowing_date") or ""))
        if all(signature):representations[signature].append(str(row.get("litter_id") or ""))
    unresolved_duplicate_litters={identity for values in representations.values() if len(values)>1
                                  for identity in values}
    # Without effective-dated lifecycle-stage boundaries, a raw undated death
    # cannot be promoted to a supported historical loss or subtracted from a
    # cohort. Preserve its identity while failing closed on that conclusion.
    accounting = []
    for litter_id, pig_ids in sorted(undated.items()):
        accounting.extend({"pig_id": pig_id, "classification": "insufficient_evidence",
                           "effective_date": None} for pig_id in pig_ids)
    events = [{"event_id": "LOSS-"+str(row["pig_id"]), "pig_id": str(row["pig_id"]),
        "effective_date": _value(row.get("exit_date")), "event_kind": _kind(row.get("exit_reason")),
        "confirmation": ("conflicting" if str(row.get("litter_id") or "") in unresolved_duplicate_litters
                         else "confirmed"), "canonical_status": "current",
        "litter_id": row.get("litter_id"), "initial_pen_id": row.get("initial_pen_id")}
        for row in deaths if row.get("exit_date")]
    current_ids={str(row["pig_id"]) for row in deaths}
    events.extend({"event_id":"HISTORY-"+str(row["pig_id"]),"pig_id":str(row["pig_id"]),
        "effective_date":_value(row.get("exit_date")),"event_kind":_kind(row.get("exit_reason")),
        "confirmation":"confirmed","canonical_status":"superseded",
        "litter_id":row.get("litter_id"),"initial_pen_id":row.get("initial_pen_id")}
        for row in historical_deaths if str(row["pig_id"]) not in current_ids and row.get("exit_date"))
    weight_map = defaultdict(list)
    for row in weights:
        weight_map[str(row["pig_id"])].append({"date": _value(row.get("weight_date")),
                                                "kg": _value(row.get("weight_kg"))})
    return {"mortality_events": events, "undated_identity_accounting": accounting,
        "cohort_reconciliations": [], "weights": dict(weight_map),
        "rootline_observations": [{"date": _value(row.get("rollup_date")),
            "temperature_min_c": _value(row.get("temperature_min_c")),
            "coverage_pct": _value(row.get("coverage_pct"))} for row in weather],
        "rootline_forecasts": [], "owner_reported_events": [],
        "recording_quality": {"complete_from": "2026-07-21",
            "limitations": ["historical effective-dated lifecycle coverage is incomplete"]},
        "feed_observations": [], "water_observations": [], "surviving_controls": [],
        "herd_at_risk_denominator": {"reconstructable": False,
            "minimum_requirement": "immutable dated entered/on-farm and exited/off-farm lifecycle intervals for every canonical animal, with lifecycle stage effective dates"},
        "evidence_cutoff": analysis_end.isoformat(), "analysis_start": start.isoformat()}


def _rows(cursor):
    names=[column.name for column in cursor.description]
    return [{name:_value(value) for name,value in zip(names,row)} for row in cursor.fetchall()]


def _value(value):
    if isinstance(value,(date,datetime)): return value.isoformat()
    if isinstance(value,Decimal): return float(value)
    return value


def _kind(reason):
    value=str(reason or "").casefold()
    if "stillborn" in value: return "stillbirth"
    if "crush" in value: return "crushed_death"
    if "after_birth" in value: return "piglet_later_death"
    return "individual_death"
