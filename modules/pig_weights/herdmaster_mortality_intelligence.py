"""Pure, zero-authority mortality intelligence for HERDMASTER.

The caller owns canonical reads and delivery.  This module performs no I/O and
must never be used as a mortality, lifecycle, medical, or messaging writer.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
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


def _canonicalize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _canonicalize(value[key]) for key in sorted(value)}
    if isinstance(value, list):
        items = [_canonicalize(item) for item in value]
        return sorted(items, key=lambda item: json.dumps(item, sort_keys=True, default=str))
    return value


def _public_event(event: dict[str, Any]) -> dict[str, Any]:
    allowed = ("event_id", "pig_id", "effective_date", "event_kind", "confirmation", "canonical_status", "litter_id", "pen_id", "exclusion_reasons")
    return {key: event.get(key) for key in allowed if event.get(key) is not None}


def _authenticated_owner_receipt(report: dict[str, Any]) -> bool:
    receipt = report.get("authentication_receipt")
    if not isinstance(receipt, dict) or not report.get("report_identity") or not report.get("pig_id"):
        return False
    principal = str(receipt.get("principal_id") or "")
    chat = str(receipt.get("private_chat_id") or "")
    digest = str(receipt.get("receipt_digest") or "")
    try:
        datetime.fromisoformat(str(report.get("provider_timestamp") or "").replace("Z", "+00:00"))
    except ValueError:
        return False
    return bool(
        receipt.get("verified_by") == "oom_sakkie_authenticated_gateway"
        and receipt.get("authority_scope") == "private_owner_health_loss"
        and principal
        and chat
        and receipt.get("bound_principal_id") == principal
        and receipt.get("bound_private_chat_id") == chat
        and len(digest) == 64
        and all(character in "0123456789abcdefABCDEF" for character in digest)
        and report.get("provider_message_id")
    )


def _validate_accounting(evidence: dict[str, Any]) -> list[dict[str, Any]]:
    allowed = {"attributable_dated_loss", "legitimate_undated_historical_loss", "duplicate_superseded_representation", "conflicting", "insufficient_evidence"}
    rows = []
    seen = set()
    for raw in evidence.get("undated_identity_accounting") or []:
        pig_id = str(raw.get("pig_id") or "")
        classification = str(raw.get("classification") or "")
        if not pig_id or pig_id in seen or classification not in allowed or raw.get("effective_date") is not None:
            raise ValueError("undated identity accounting must be unique, classified, and biologically undated")
        seen.add(pig_id)
        rows.append({"pig_id": pig_id, "classification": classification, "effective_date": None})
    for cohort in evidence.get("cohort_reconciliations") or []:
        expected = int(cohort["born_alive"]) - int(cohort["weaned_count"])
        represented = int(cohort["undated_loss_rows"]) + int(cohort["dated_later_deaths"])
        expected_outcome = "supported" if represented == expected else "conflicting"
        if cohort.get("outcome") != expected_outcome:
            raise ValueError("cohort loss arithmetic does not support the declared outcome")
    return rows


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
    labels_af = {
        "litter_cluster": "werpselgroep",
        "pen_cluster": "hokgroep",
        "weak_growth_association": "verband met swak groei",
        "observed_cold_weather_overlap": "oorvleueling met waargenome koue weer",
    }
    controls=list(evidence.get("surviving_controls") or [])
    for pattern in patterns:
        comparable=[{"pig_id":row.get("pig_id"),"observed_outcome":row.get("observed_outcome")}
                    for row in controls if _healthy_control(row) and (
                        (pattern["pattern"]=="litter_cluster" and row.get("litter_id")==pattern.get("identity"))
                        or (pattern["pattern"]=="pen_cluster" and row.get("pen_id")==pattern.get("identity")))]
        hypotheses.append({
            "hypothesis": labels[pattern["pattern"]],
            "confidence": "moderate" if pattern["count"] >= 3 else "low",
            "supporting_evidence": pattern,
            "counterevidence": comparable or "Unknown: no attributable surviving-control comparison is present.",
            "causal_limitations": "No causal diagnosis or controlled comparison establishes a cause.",
        })

    unknowns = []
    for key, label in (("feed_observations", "attributable feed change/access observations"), ("water_observations", "attributable drinking and water-continuity observations"), ("surviving_controls", "comparable surviving littermates or penmates")):
        if not evidence.get(key):
            unknowns.append(label)
    if forecasts:
        unknowns.append("forecasts are retained separately and do not prove observed exposure")

    accounting = _validate_accounting(evidence)
    material_evidence = {key: value for key, value in evidence.items()
                         if key not in {"evidence_cutoff", "analysis_start"}}
    evidence_digest = _digest(_canonicalize(material_evidence))
    # One durable management lifecycle is refreshed by a changed evidence
    # digest; calendar rollover must not create notification/card noise.
    review_identity = "HERDMASTER-MORTALITY-CURRENT"
    question = (
        "Please check the surviving littermates and penmates once: are they eating, drinking, moving and breathing normally, "
        "and was there any feed or water interruption?"
        if unknowns else None
    )
    af_question = (
        "Kontroleer asseblief die oorlewende werpsel- en hokmaats een keer: eet, drink, beweeg en haal hulle normaal asem, "
        "en was daar enige onderbreking in voer of water?"
        if unknowns else None
    )
    assessment = (
        f"From {windows['90']['start']} to {analysis_end.isoformat()}, {windows['90']['total']} confirmed dated losses are countable. "
        + (f"The strongest reproducible signals are {', '.join(p['pattern'].replace('_', ' ') for p in patterns[:3])}. " if patterns else "No reliable shared pattern is proven. ")
        + "These are associations, not diagnoses. Check surviving penmates and littermates and escalate promptly if serious signs or further losses appear."
    )
    af_assessment = (
        f"Van {windows['90']['start']} tot {analysis_end.isoformat()} kan {windows['90']['total']} bevestigde, gedateerde verliese getel word. "
        + (f"Die sterkste herhaalbare seine is {', '.join(labels_af[p['pattern']] for p in patterns[:3])}. " if patterns else "Geen betroubare gedeelde patroon is bewys nie. ")
        + "Dit is verbande, nie diagnoses of bewese oorsake nie. Kontroleer die oorlewende hok- en werpselmaats en kry veeartsenyhulp indien ernstige tekens of verdere verliese voorkom."
    )
    owner_reported = []
    for report in evidence.get("owner_reported_events") or []:
        authenticated = _authenticated_owner_receipt(report)
        owner_reported.append({
            "report_identity": report.get("report_identity"),
            "pig_id": report.get("pig_id"),
            "reported_at": report.get("reported_at"),
            "reported_facts": list(report.get("reported_facts") or []),
            "canonical_mortality": False,
            "provider_message_id": report.get("provider_message_id"),
            "provider_timestamp": report.get("provider_timestamp"),
            "authenticated_private_owner": authenticated,
            "status": "authenticated_owner_report_pending_governed_lifecycle" if authenticated else "unverified_report_excluded_from_owner_handoff",
        })
    actions = [
        "Observe surviving affected penmates and littermates for appetite, drinking, movement and breathing.",
        "Verify feed and water continuity for the attributable exposure period.",
        "Seek veterinary assessment for serious signs, repeated losses or a worsening cluster; no treatment is inferred here.",
    ]
    actions_af = [
        "Kyk of die betrokke oorlewende hok- en werpselmaats normaal eet, drink, beweeg en asemhaal.",
        "Bevestig dat voer en water gedurende die betrokke tyd beskikbaar en ononderbroke was.",
        "Kry veeartsenyhulp vir ernstige tekens, herhaalde verliese of 'n verslegtende groep; geen behandeling word hier afgelei nie.",
    ]
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
        "undated_identity_accounting": accounting,
        "owner_reported_not_canonical": owner_reported,
        "herd_at_risk_denominator": evidence.get("herd_at_risk_denominator") or {
            "reconstructable": False,
            "minimum_requirement": "immutable dated entered/on-farm and exited/off-farm lifecycle intervals for every canonical animal, with lifecycle stage effective dates",
        },
        "smallest_grouped_question": question,
        "smallest_grouped_question_af": af_question,
        "recommendations": actions,
        "recommendations_af": actions_af,
        "automatic_reassessment_trigger": "new or materially changed mortality, health, weight, movement, feed, water, treatment, or observed ROOTLINE evidence",
        "family_assessment_en": assessment,
        "family_assessment_af": af_assessment,
        "review_identity": review_identity,
        "evidence_digest": evidence_digest,
        "deduplication_key": f"{review_identity}:{evidence_digest}",
        "unchanged_replay_action": "suppress_duplicate_alert",
        "forecast_evidence": forecasts,
        "authority": {"io": False, "writes": False, "medical": False, "lifecycle": False, "messaging": False},
    }


def _healthy_control(row: dict[str, Any]) -> bool:
    if row.get("healthy") is True:
        return True
    outcome=str(row.get("observed_outcome") or "").strip().casefold().replace(" ","_")
    return outcome in {"healthy","normal","alive_healthy","unaffected","no_signs","no_abnormal_signs"}


def build_oom_sakkie_mortality_packet(evidence: dict[str, Any], *, analysis_end: date) -> dict[str, Any]:
    """Shape the typed result for the existing Oom Sakkie consumption boundary."""
    result = build_mortality_intelligence(evidence, analysis_end=analysis_end)
    if any(not report["authenticated_private_owner"] for report in result["owner_reported_not_canonical"]):
        raise ValueError("owner-reported mortality requires authenticated private-owner provenance")
    classifications = Counter(row["classification"] for row in result["undated_identity_accounting"])
    owner_pending = bool(result["owner_reported_not_canonical"])
    counts = result["rolling_counts"]
    patterns = result["detected_patterns"]
    signal = ", ".join(p["pattern"].replace("_", " ") for p in patterns[:3]) or "no reliable shared pattern"
    signal_af = ", ".join({"litter_cluster":"werpselgroep","pen_cluster":"hokgroep",
        "weak_growth_association":"verband met swak groei",
        "observed_cold_weather_overlap":"oorvleueling met waargenome koue weer"}[p["pattern"]]
        for p in patterns[:3]) or "geen betroubare gedeelde patroon"
    english = (
        f"We can confirm {counts['90']['total']} dated losses in 90 days, {counts['30']['total']} in 30 days and {counts['7']['total']} in seven days. "
        f"Among older undated records, {classifications['legitimate_undated_historical_loss']} are supported historical losses, "
        f"{classifications['conflicting']} conflict with cohort or dated evidence, and {classifications['insufficient_evidence']} remain insufficient. "
        f"The reproducible signals are {signal}; these are associations, not proven causes."
        + (" Pig 127's authenticated owner report remains separate until its governed lifecycle completes." if owner_pending else "")
    )
    afrikaans = (
        f"Ons kan {counts['90']['total']} gedateerde verliese in 90 dae bevestig, {counts['30']['total']} in 30 dae en {counts['7']['total']} in sewe dae. "
        f"Onder ouer ongedateerde rekords word {classifications['legitimate_undated_historical_loss']} as historiese verliese ondersteun, "
        f"{classifications['conflicting']} bots met kohort- of gedateerde bewyse, en {classifications['insufficient_evidence']} bly onvoldoende. "
        f"Die herhaalbare seine is {signal_af}; dit is verbande, nie bewese oorsake nie."
        + (" Pig 127 se geverifieerde eienaarsverslag bly apart totdat die beheerde lewensiklus voltooi is." if owner_pending else "")
    )
    return {
        "packet_type": "herdmaster.mortality_intelligence.v1",
        "review_identity": result["review_identity"],
        "evidence_digest": result["evidence_digest"],
        "deduplication_key": result["deduplication_key"],
        "analysis_period": result["analysis_period"],
        "rolling_counts": result["rolling_counts"],
        "baseline": result["historical_baseline"],
        "proven_facts": [_public_event(event) for event in result["included_events"]],
        "excluded_dated_or_superseded": [_public_event(event) for event in result["excluded_events"]],
        "undated_identity_accounting": result["undated_identity_accounting"],
        "owner_reported_not_canonical": result["owner_reported_not_canonical"],
        "patterns": result["detected_patterns"],
        "hypotheses": result["hypotheses"],
        "unknowns": result["unknown_or_missing"],
        "question": result["smallest_grouped_question"],
        "question_af": result["smallest_grouped_question_af"],
        "actions": result["recommendations"][:3],
        "actions_af": result["recommendations_af"][:3],
        "reassessment_trigger": result["automatic_reassessment_trigger"],
        "english": english,
        "afrikaans": afrikaans,
        "unchanged_replay_action": result["unchanged_replay_action"],
        "authority": result["authority"],
    }
