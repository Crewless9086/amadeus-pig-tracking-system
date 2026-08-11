"""Pure, zero-I/O intelligence for one completed canonical weighing batch."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from statistics import median

CONTRACT_VERSION = "herdmaster_weighing_batch_intelligence_v1"


def build_weighing_batch_intelligence(*, batch, batch_rows, weight_history,
        expected_animals=(), contexts=(), correction_lineage=None):
    """Return a deterministic analysis packet without reading or writing state."""
    batch = dict(batch or {})
    if str(batch.get("status", "")).lower() != "complete" or not batch.get("batch_id"):
        return _unavailable("completed_canonical_batch_required")
    batch_date = _date(batch.get("weight_date"))
    if not batch_date:
        return _unavailable("valid_batch_weight_date_required")

    accepted = [dict(row) for row in (batch_rows or [])
        if str(row.get("status", "")).lower() == "success" and row.get("pig_id")
        and row.get("weight_kg") is not None]
    accepted.sort(key=lambda row: (str(row.get("pig_id")), str(row.get("row_id") or row.get("weight_event_id") or "")))
    history_by_pig = {}
    for row in weight_history or ():
        pig_id = str(row.get("pig_id") or "").strip()
        observed = _date(row.get("weight_date"))
        weight = _number(row.get("weight_kg"))
        if pig_id and observed and weight is not None:
            history_by_pig.setdefault(pig_id, []).append({**row, "weight_date": observed, "weight_kg": weight})
    for rows in history_by_pig.values():
        rows.sort(key=lambda row: (row["weight_date"], str(row.get("weight_event_id") or "")))

    same_day = {}
    for row in accepted:
        same_day[row["pig_id"]] = same_day.get(row["pig_id"], 0) + 1
    analysed, unique_pigs = [], set()
    for row in accepted:
        pig_id = str(row["pig_id"])
        current = _number(row.get("weight_kg"))
        prior = [item for item in history_by_pig.get(pig_id, []) if item["weight_date"] < batch_date]
        previous = prior[-1] if prior else None
        elapsed = (batch_date - previous["weight_date"]).days if previous else None
        change = round(current - previous["weight_kg"], 2) if previous else None
        rate = round(change / elapsed, 3) if change is not None and elapsed and elapsed > 0 else None
        implausible = current is None or current <= 0 or current > 500 or same_day[pig_id] > 1
        expected_rate = _number(row.get("expected_growth_min_kg_day"))
        classification = "reweigh" if implausible else (
            "no_comparison" if change is None else
            "slow_growth" if expected_rate is not None and rate is not None and 0 <= rate < expected_rate else
            "gain" if change > 0 else "loss" if change < 0 else "unchanged")
        prior_changes = [round(prior[i]["weight_kg"] - prior[i - 1]["weight_kg"], 2) for i in range(1, len(prior))]
        repeated_decline = change is not None and change < 0 and bool(prior_changes) and prior_changes[-1] < 0
        analysed.append({
            "pig_id": pig_id, "name": row.get("pig_name") or row.get("tag_number") or pig_id,
            "tag_number": row.get("tag_number") or "", "pen_id": row.get("pen_id") or row.get("from_pen_id") or "",
            "pen_name": row.get("pen_name") or row.get("from_pen_name") or row.get("from_pen_id") or "Unknown",
            "cohort_id": row.get("cohort_id") or row.get("litter_id") or "",
            "lifecycle_state": row.get("lifecycle_state") or row.get("status") or "Unknown",
            "reproductive_state": row.get("reproductive_state") or "Unknown",
            "weight_date": batch_date.isoformat(), "weight_kg": current,
            "previous_weight_date": previous["weight_date"].isoformat() if previous else None,
            "previous_weight_kg": previous["weight_kg"] if previous else None,
            "elapsed_days": elapsed, "change_kg": change, "growth_rate_kg_day": rate,
            "classification": classification, "expected_growth_min_kg_day": expected_rate,
            "same_day_duplicate_count": same_day[pig_id],
            "repeated_decline": repeated_decline, "reweigh_required": implausible,
        })
        unique_pigs.add(pig_id)

    expected = {str(row.get("pig_id")) for row in expected_animals or ()
        if row.get("pig_id") and row.get("expected_for_batch", True)}
    missing_ids = sorted(expected - unique_pigs)
    expected_lookup = {str(row.get("pig_id")): row for row in expected_animals or () if row.get("pig_id")}
    missing = [{"pig_id": pig_id, "name": expected_lookup[pig_id].get("name") or expected_lookup[pig_id].get("tag_number") or pig_id,
        "pen_name": expected_lookup[pig_id].get("pen_name") or "Unknown", "weight_kg": None,
        "classification": "not_weighed"} for pig_id in missing_ids]

    comparable = [row for row in analysed if row["change_kg"] is not None and not row["reweigh_required"]]
    valid_current = [row["weight_kg"] for row in analysed if not row["reweigh_required"]]
    pen_patterns = _group_patterns(analysed, "pen_name")
    cohort_patterns = _group_patterns([row for row in analysed if row["cohort_id"]], "cohort_id")
    interval_start = min((_date(row.get("weight_date")) for row in weight_history or ()
        if _date(row.get("weight_date")) and _date(row.get("weight_date")) < batch_date), default=None)
    context_rows = _contexts(contexts, interval_start, batch_date)
    findings = _findings(analysed, pen_patterns, missing)
    question = _grouped_question(findings, context_rows)
    evidence = {"batch": batch, "rows": _canonical_rows(accepted),
        "history": _canonical_rows(weight_history or []),
        "expected": _canonical_rows(expected_animals or []), "contexts": _canonical_rows(context_rows),
        "correction_lineage": correction_lineage or {}}
    digest = hashlib.sha256(json.dumps(evidence, sort_keys=True, default=str,
        separators=(",", ":")).encode()).hexdigest()
    analysis_id = f"HERD-WEIGH-{digest[:32].upper()}"
    metrics = {
        "accepted_entries": len(accepted), "unique_pigs_weighed": len(unique_pigs),
        "expected_pigs": len(expected) if expected else None,
        "coverage_pct": round(len(unique_pigs & expected) * 100 / len(expected), 1) if expected else None,
        "average_weight_kg": _average(valid_current), "median_weight_kg": _median(valid_current),
        "average_supported_change_kg": _average([row["change_kg"] for row in comparable]),
        "median_supported_change_kg": _median([row["change_kg"] for row in comparable]),
        "average_supported_growth_kg_day": _average([row["growth_rate_kg_day"] for row in comparable]),
        "gain_count": _count(analysed, "gain"), "slow_growth_count": _count(analysed, "slow_growth"),
        "loss_count": _count(analysed, "loss"),
        "unchanged_count": _count(analysed, "unchanged"), "no_comparison_count": _count(analysed, "no_comparison"),
        "reweigh_count": _count(analysed, "reweigh"), "repeated_decline_count": sum(row["repeated_decline"] for row in analysed),
        "missing_expected_count": len(missing),
    }
    return {"success": True, "contract_version": CONTRACT_VERSION, "analysis_id": analysis_id,
        "batch_id": str(batch["batch_id"]), "batch_date": batch_date.isoformat(),
        "evidence_digest": digest, "correction_lineage": correction_lineage or {},
        "replay_identity": f"{analysis_id}:{digest}", "delivery_deduplication_key": f"oom:{analysis_id}",
        "metrics": metrics, "animals": analysed, "missing_expected_animals": missing,
        "pen_patterns": pen_patterns, "cohort_patterns": cohort_patterns,
        "context": context_rows, "findings": findings[:3], "grouped_question": question,
        "owner_summary_af": _summary_af(metrics, findings[:3], context_rows, question),
        "labels": {"facts": "Measured", "context": "Associated", "missing": "Unknown", "action": "Next action"},
        "writes_performed": False, "telegram_delivery_enabled": False, "protected_actions_performed": False}


def _contexts(rows, start, end):
    result = []
    for row in rows or ():
        observed = _date(row.get("observed_at") or row.get("event_date"))
        if observed and ((start and observed < start) or observed > end):
            continue
        result.append({"context_type": row.get("context_type") or "other",
            "summary": row.get("summary") or "Recorded contextual evidence",
            "source": row.get("source") or "Unknown", "source_id": row.get("source_id") or "",
            "observed_at": observed.isoformat() if observed else None, "classification": "Associated"})
    return sorted(result, key=lambda row: (row["observed_at"] or "", row["context_type"], row["source_id"]))


def _group_patterns(rows, key):
    groups = {}
    for row in rows:
        group = groups.setdefault(row.get(key) or "Unknown", {"group": row.get(key) or "Unknown", "weighed": 0,
            "gains": 0, "losses": 0, "reweigh": 0, "changes": []})
        group["weighed"] += 1
        group["gains"] += row["classification"] == "gain"
        group["losses"] += row["classification"] == "loss"
        group["reweigh"] += row["classification"] == "reweigh"
        if row["change_kg"] is not None and not row["reweigh_required"]:
            group["changes"].append(row["change_kg"])
    result = []
    for row in sorted(groups.values(), key=lambda item: item["group"]):
        changes = row.pop("changes")
        result.append({**row, "average_supported_change_kg": _average(changes)})
    return result


def _findings(rows, pen_patterns, missing):
    findings = []
    declines = [row for row in rows if row["repeated_decline"]]
    reweigh = [row for row in rows if row["reweigh_required"]]
    loss_pens = [row for row in pen_patterns if row["losses"] >= 2]
    if reweigh:
        findings.append({"classification": "Measured", "finding": f"{len(reweigh)} measurement(s) need reweigh before interpretation.",
            "next_action": "Reweigh only the flagged animals under the same scale conditions."})
    if declines:
        findings.append({"classification": "Measured", "finding": f"{len(declines)} animal(s) have repeated recorded decline.",
            "next_action": "Inspect the affected animals and review welfare/feeding evidence."})
    if loss_pens:
        findings.append({"classification": "Associated", "finding": f"Losses cluster in {', '.join(row['group'] for row in loss_pens)}.",
            "next_action": "Review the shared pen interval without treating location as cause."})
    if missing:
        findings.append({"classification": "Unknown", "finding": f"{len(missing)} expected animal(s) were not weighed; no zero was imputed.",
            "next_action": "Confirm whether they were intentionally omitted or need a targeted weigh."})
    if not findings:
        findings.append({"classification": "Measured", "finding": "No material loss, duplicate or coverage pattern was detected.",
            "next_action": "Continue the normal weighing interval."})
    return findings


def _grouped_question(findings, contexts):
    material = any(row["classification"] in {"Associated", "Unknown"} for row in findings)
    has_feed = any(row["context_type"] == "feed" for row in contexts)
    if material and not has_feed:
        return "Het die voer, hoeveelheid of voertye vir die betrokke groep sedert die vorige weging verander?"
    return None


def _summary_af(metrics, findings, contexts, question):
    coverage = (f"{metrics['unique_pigs_weighed']} geweeg; {metrics['coverage_pct']}% dekking"
        if metrics["coverage_pct"] is not None else f"{metrics['unique_pigs_weighed']} unieke varke geweeg; verwagte groep onbekend")
    change = metrics["average_supported_change_kg"]
    lines = ["HERDMASTER — WEEKLIKSE GEWIGSOPSOMMING", coverage,
        f"Gemiddelde ondersteunde verandering: {change:+.2f} kg" if change is not None else "Gemiddelde verandering: Onbekend — geen vergelykbare vorige gewigte nie."]
    lines += [f"- {row['classification']}: {row['finding']} Next action: {row['next_action']}" for row in findings]
    lines.append(f"Relevante konteks: {len(contexts)} toegeskrewe rekord(s); verband is nie oorsaak nie." if contexts
        else "Relevante konteks: Onbekend — geen toegeskrewe konteks vir die interval nie.")
    if question:
        lines.append(f"Een vraag: {question}")
    return "\n".join(lines)


def _count(rows, value):
    return sum(row["classification"] == value for row in rows)


def _canonical_rows(rows):
    normalized = [dict(row) for row in rows]
    return sorted(normalized, key=lambda row: json.dumps(
        row, sort_keys=True, default=str, separators=(",", ":")))


def _average(values):
    values = [value for value in values if value is not None]
    return round(sum(values) / len(values), 3) if values else None


def _median(values):
    values = [value for value in values if value is not None]
    return round(median(values), 3) if values else None


def _number(value):
    try:
        return float(value) if value is not None and value != "" else None
    except (TypeError, ValueError):
        return None


def _date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _unavailable(reason):
    return {"success": False, "contract_version": CONTRACT_VERSION, "reason": reason,
        "writes_performed": False, "telegram_delivery_enabled": False, "protected_actions_performed": False}
