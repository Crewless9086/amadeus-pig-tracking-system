"""Bounded, proposal-only observer loops for Agentic Business OS domains."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone


OBSERVERS = {
    "sam_lead_health": {"domain": "sales", "interval_seconds": 900, "authority": "observe", "owner": "SAM"},
    "ledger_cash_exceptions": {"domain": "finance", "interval_seconds": 1800, "authority": "observe", "owner": "Ledger"},
    "herdmaster_readiness": {"domain": "farm", "interval_seconds": 1800, "authority": "observe", "owner": "Herdmaster"},
    "beacon_opportunities": {"domain": "marketing", "interval_seconds": 3600, "authority": "observe", "owner": "Beacon"},
}


def due_observers(last_runs=None, *, now=None, event_domains=None):
    now = now or datetime.now(timezone.utc)
    last_runs = last_runs or {}
    event_domains = set(event_domains or ())
    due = []
    for key, spec in OBSERVERS.items():
        last = _datetime(last_runs.get(key))
        scheduled = last is None or now >= last + timedelta(seconds=spec["interval_seconds"])
        event_driven = spec["domain"] in event_domains
        if scheduled or event_driven:
            due.append({"observer_key": key, "trigger": "event" if event_driven else "schedule", **spec})
    return due


def run_observer(observer_key, evidence_reader, *, trigger="schedule", now=None):
    spec = OBSERVERS.get(str(observer_key or ""))
    if not spec:
        return {"success": False, "status": "observer_unknown"}
    now = now or datetime.now(timezone.utc)
    try:
        evidence = evidence_reader(spec["domain"])
    except Exception as exc:
        return _result(spec, observer_key, trigger, now, "failed", gaps=[exc.__class__.__name__])
    evidence = evidence if isinstance(evidence, dict) else {}
    facts = evidence.get("facts") if isinstance(evidence.get("facts"), list) else []
    freshness = str(evidence.get("freshness") or "unknown")
    source_refs = [str(item) for item in evidence.get("source_refs", []) if str(item)]
    gaps = [str(item) for item in evidence.get("gaps", []) if str(item)]
    recommendations = [dict(item) for item in evidence.get("recommendations", []) if isinstance(item, dict)]
    for item in recommendations:
        item.update({"proposal_only": True, "execution_authorized": False, "authority_tier": "observe"})
    status = "observed" if source_refs and freshness != "unknown" else "evidence_incomplete"
    return _result(spec, observer_key, trigger, now, status, facts=facts, source_refs=source_refs, freshness=freshness, gaps=gaps, recommendations=recommendations)


def observer_quality(runs, labels=None):
    runs = list(runs or [])
    labels = labels or {}
    successful = [item for item in runs if item.get("status") == "observed"]
    recommendations = [recommendation for item in successful for recommendation in item.get("recommendations", [])]
    labelled = [item for item in recommendations if item.get("recommendation_id") in labels]
    false_positive = [item for item in labelled if labels[item["recommendation_id"]] is False]
    return {
        "run_count": len(runs),
        "successful_run_count": len(successful),
        "recommendation_count": len(recommendations),
        "labelled_count": len(labelled),
        "false_positive_count": len(false_positive),
        "false_positive_rate": (len(false_positive) / len(labelled)) if labelled else None,
    }


def _result(spec, key, trigger, now, status, **fields):
    identity = hashlib.sha256(json.dumps({"key": key, "trigger": trigger, "at": now.isoformat()}, sort_keys=True).encode()).hexdigest()[:20]
    recommendations = fields.get("recommendations") or []
    for index, item in enumerate(recommendations):
        item.setdefault("recommendation_id", f"REC-{identity.upper()}-{index + 1}")
    return {
        "success": status in {"observed", "evidence_incomplete"},
        "status": status,
        "run_id": f"OBS-{identity.upper()}",
        "observer_key": key,
        "domain": spec["domain"],
        "owner": spec["owner"],
        "trigger": trigger,
        "authority_tier": "observe",
        "writes_authorized": False,
        "sends_authorized": False,
        "ran_at": now.isoformat(),
        **fields,
    }


def _datetime(value):
    if isinstance(value, datetime):
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
