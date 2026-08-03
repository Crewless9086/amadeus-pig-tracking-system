"""Pure, zero-authority mortality intelligence for HERDMASTER.

The caller owns canonical reads and delivery.  This module performs no I/O and
must never be used as a mortality, lifecycle, medical, or messaging writer.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any


CONFIRMED = "confirmed"


def _day(value: Any) -> date | None:
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest().upper()


def build_mortality_intelligence(evidence: dict[str, Any], *, analysis_end: date) -> dict[str, Any]:
    """Return a deterministic, read-only mortality assessment.

    ``mortality_events`` must contain attributable event identities. Confirmed,
    dated, current-canonical events are counted. Superseded, duplicate,
    conflicting, unconfirmed and undated representations remain visible but do
    not silently alter rolling counts.
    """
    raw = list(evidence.get("mortality_events") or [])
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in sorted(raw, key=lambda x: (str(x.get("effective_date") or ""), str(x.get("event_id") or ""))):
        event = dict(item)
        event_id = str(event.get("event_id") or "")
        event_day = _day(event.get("effective_date"))
        reasons = []
        if not event_id:
            reasons.append("missing event identity")
        elif event_id in seen or event.get("duplicate_of"):
            reasons.append("duplicate representation")
        if event_id:
            seen.add(event_id)
        if event.get("canonical_status") == "superseded":
            reasons.append("superseded history")
        if event.get("confirmation") != CONFIRMED:
            reasons.append(str(event.get("confirmation") or "unconfirmed") + " evidence")
        if not event_day:
            reasons.append("effective date Unknown")
        elif event_day > analysis_end:
            reasons.append("future-dated event")
        event["effective_date"] = event_day.isoformat() if event_day else None
        if reasons:
            event["exclusion_reasons"] = reasons
            excluded.append(event)
        else:
            included.append(event)

    windows = {}
    for days in (7, 30, 90):
        start = analysis_end - timedelta(days=days - 1)
        events = [e for e in included if _day(e["effective_date"]) >= start]
        windows[str(days)] = {
            "start": start.isoformat(),
            "end": analysis_end.isoformat(),
            "total": len(events),
            "by_kind": dict(sorted(Counter(str(e.get("event_kind") or "unknown") for e in events).items())),
        }

    quality = evidence.get("recording_quality") or {}
    coverage_start = _day(quality.get("complete_from"))
    baseline_reasons = list(quality.get("limitations") or [])
    if coverage_start is None:
        baseline_reasons.append("complete recording start is Unknown")
    elif coverage_start > analysis_end - timedelta(days=179):
        baseline_reasons.append("fewer than 180 complete days are available")
    if any(e["exclusion_reasons"] for e in excluded):
        baseline_reasons.append("undated, duplicate, superseded, conflicting or unconfirmed records exist")
    baseline = {
        "reliable": not baseline_reasons,
        "method": "prior non-overlapping 90 days" if not baseline_reasons else None,
        "limitations": sorted(set(baseline_reasons)),
    }

    recent = [e for e in included if _day(e["effective_date"]) >= analysis_end - timedelta(days=89)]
    patterns: list[dict[str, Any]] = []
    for field, kind in (("litter_id", "litter_cluster"), ("pen_id", "pen_cluster")):
        groups: dict[str, list[str]] = defaultdict(list)
        for event in recent:
            if event.get(field):
                groups[str(event[field])].append(str(event["event_id"]))
        for identity, ids in sorted(groups.items()):
            if len(ids) >= 2:
                patterns.append({"pattern": kind, "identity": identity, "event_ids": ids, "count": len(ids), "causality": "not established"})

    deaths_by_pig = {str(e.get("pig_id")): e for e in recent if e.get("pig_id")}
    weak_growth = []
    for pig_id, series in sorted((evidence.get("weights") or {}).items()):
        dated = sorted(((_day(x.get("date")), x.get("kg")) for x in series if _day(x.get("date"))), key=lambda x: x[0])
        before = [x for x in dated if pig_id in deaths_by_pig and x[0] <= _day(deaths_by_pig[pig_id]["effective_date"])]
        if len(before) >= 2 and before[-1][1] is not None and before[-2][1] is not None and float(before[-1][1]) <= float(before[-2][1]):
            weak_growth.append(pig_id)
    if weak_growth:
        patterns.append({"pattern": "weak_growth_association", "pig_ids": weak_growth, "count": len(weak_growth), "causality": "not established"})

    observed_weather = list(evidence.get("rootline_observations") or [])
    forecasts = list(evidence.get("rootline_forecasts") or [])
    cold_links = []
    for event in recent:
        event_day = _day(event["effective_date"])
        overlap = [w for w in observed_weather if _day(w.get("date")) and abs((_day(w.get("date")) - event_day).days) <= 2 and w.get("temperature_min_c") is not None and float(w["temperature_min_c"]) < 10 and float(w.get("coverage_pct") or 0) >= 80]
        if overlap:
            cold_links.append(str(event["event_id"]))
    if cold_links:
        patterns.append({"pattern": "observed_cold_weather_overlap", "event_ids": cold_links, "count": len(cold_links), "causality": "not established"})

    hypotheses = []
    labels = {
        "litter_cluster": "A shared litter or early-life exposure may warrant investigation.",
        "pen_cluster": "A shared pen exposure may warrant investigation.",
        "weak_growth_association": "Poor or declining growth may identify vulnerable animals.",
        "observed_cold_weather_overlap": "Cold exposure may have coincided with some losses.",
    }
    for pattern in patterns:
        hypotheses.append({
            "hypothesis": labels[pattern["pattern"]],
            "confidence": "moderate" if pattern["count"] >= 3 else "low",
            "supporting_evidence": pattern,
            "contradicting_evidence": "No causal diagnosis or controlled comparison is present.",
        })

    unknowns = []
    for key, label in (("feed_observations", "attributable feed change/access observations"), ("water_observations", "attributable drinking and water-continuity observations"), ("surviving_controls", "comparable surviving littermates or penmates")):
        if not evidence.get(key):
            unknowns.append(label)
    if forecasts:
        unknowns.append("forecasts are retained separately and do not prove observed exposure")

    evidence_digest = _digest(evidence)
    review_identity = f"HERDMASTER-MORTALITY-{analysis_end.isoformat()}"
    question = (
        "Please check the surviving littermates and penmates once: are they eating, drinking, moving and breathing normally, "
        "and was there any feed or water interruption?"
        if unknowns else None
    )
    assessment = (
        f"From {windows['90']['start']} to {analysis_end.isoformat()}, {windows['90']['total']} confirmed dated losses are countable. "
        + (f"The strongest reproducible signals are {', '.join(p['pattern'].replace('_', ' ') for p in patterns[:3])}. " if patterns else "No reliable shared pattern is proven. ")
        + "These are associations, not diagnoses. Check surviving penmates and littermates and escalate promptly if serious signs or further losses appear."
    )
    return {
        "contract_version": "HERDMASTER_MORTALITY_INTELLIGENCE_V1",
        "analysis_period": {"start": windows["90"]["start"], "end": analysis_end.isoformat()},
        "included_events": included,
        "excluded_events": excluded,
        "rolling_counts": windows,
        "historical_baseline": baseline,
        "detected_patterns": patterns,
        "hypotheses": hypotheses,
        "unknown_or_missing": unknowns,
        "smallest_grouped_question": question,
        "recommendations": [
            "Observe surviving affected penmates and littermates for appetite, drinking, movement and breathing.",
            "Verify feed and water continuity for the attributable exposure period.",
            "Seek veterinary assessment for serious signs, repeated losses or a worsening cluster; no treatment is inferred here.",
        ],
        "automatic_reassessment_trigger": "new or materially changed mortality, health, weight, movement, feed, water, treatment, or observed ROOTLINE evidence",
        "family_assessment_en": assessment,
        "review_identity": review_identity,
        "evidence_digest": evidence_digest,
        "deduplication_key": f"{review_identity}:{evidence_digest}",
        "unchanged_replay_action": "suppress_duplicate_alert",
        "forecast_evidence": forecasts,
        "authority": {"io": False, "writes": False, "medical": False, "lifecycle": False, "messaging": False},
    }
