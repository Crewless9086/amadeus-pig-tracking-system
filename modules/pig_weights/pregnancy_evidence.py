"""Pure precedence rules for governed pregnancy evidence.

This module reads supplied canonical rows only. It performs no I/O and exposes
no animal identity beyond the row selected by its caller.
"""

from __future__ import annotations

from datetime import date, datetime


CURRENT_PREGNANCY_MAX_DAYS_SINCE_MATING = 125
CURRENT_PREGNANCY_FARROWING_GRACE_DAYS = 14

_POSITIVE = {"pregnant", "confirmed", "confirmed_pregnant", "positive"}
_NEGATIVE = {
    "not_pregnant",
    "notpregnant",
    "negative",
    "open",
    "repeat_required",
}
_PENDING = {"", "unknown", "pending", "not_checked", "not_recorded"}


def resolve_pregnancy_evidence(mating_rows, *, today=None):
    """Resolve current applicability before deriving a pregnancy status."""
    today = today or date.today()
    rows = [row for row in (mating_rows or []) if isinstance(row, dict)]
    rows.sort(
        key=lambda row: (_as_date(row.get("mating_date")) or date.min),
        reverse=True,
    )
    if not rows:
        return _result(
            "no_mating",
            "Unknown",
            "No governed pregnancy result",
            current=False,
            as_of=today,
            missing=["No canonical mating chronology is recorded."],
        )

    latest = rows[0]
    mating_date = _as_date(latest.get("mating_date"))
    if mating_date is not None and mating_date > today:
        return _result(
            "conflicting",
            "Unknown",
            "Pregnancy evidence conflicts with future mating chronology",
            current=False,
            as_of=today,
            mating=latest,
            missing=[
                "The latest mating date is in the future and is not currently applicable."
            ],
        )
    cycle_rows = [
        row
        for row in rows
        if (
            _text(row.get("mating_id"))
            and _text(row.get("mating_id")) == _text(latest.get("mating_id"))
        )
        or (
            mating_date is not None
            and _as_date(row.get("mating_date")) == mating_date
        )
    ]
    governed = []
    for row in cycle_rows:
        category = _category(row.get("pregnancy_check_result"))
        if category in {"pregnant", "not_pregnant"}:
            governed.append((category, row))
        outcome_category = _category(row.get("outcome"))
        if outcome_category in {"pregnant", "not_pregnant"}:
            governed.append((outcome_category, row))
    categories = {category for category, _row in governed}
    if len(categories) > 1:
        return _result(
            "conflicting",
            "Conflicting",
            "Conflicting pregnancy evidence",
            current=False,
            as_of=today,
            mating=latest,
            missing=[
                "Conflicting governed pregnancy results exist for the latest mating."
            ],
        )

    category = next(iter(categories), "")
    evidence_row = governed[0][1] if governed else latest
    result_value = _display_result(
        evidence_row.get("pregnancy_check_result")
        or evidence_row.get("outcome")
    )
    result_date, result_time = _result_datetime(evidence_row)
    method = _first(
        evidence_row,
        "pregnancy_check_method",
        "diagnostic_method",
        "examination_method",
    )
    assessor = _first(
        evidence_row,
        "pregnancy_check_assessor",
        "assessor",
        "checked_by",
    )
    missing_support = []
    if category:
        if result_date is None:
            missing_support.append("Pregnancy result date is Unknown.")
        if not method:
            missing_support.append("Pregnancy-check method is Unknown.")
        if not assessor:
            missing_support.append("Pregnancy-check assessor is Unknown.")
        if not result_time:
            missing_support.append("Pregnancy-check observation time is Unknown.")

    if not category:
        return _result(
            "no_governed_result",
            result_value,
            "Pregnancy evidence pending",
            current=False,
            as_of=today,
            mating=latest,
            result_date=result_date,
            result_time=result_time,
            method=method,
            assessor=assessor,
            missing=["Pregnancy-check result is Unknown."],
        )
    if result_date is None:
        return _result(
            "unattributed",
            result_value,
            "Pregnancy result is provisional or unattributed",
            current=False,
            as_of=today,
            mating=latest,
            result_time=result_time,
            method=method,
            assessor=assessor,
            missing=missing_support,
        )
    if result_date > today:
        return _result(
            "conflicting",
            result_value,
            "Pregnancy evidence is future-dated and not currently applicable",
            current=False,
            as_of=today,
            mating=latest,
            result_date=result_date,
            result_time=result_time,
            method=method,
            assessor=assessor,
            missing=[
                "Pregnancy result date is in the future and is not currently applicable."
            ],
        )
    if mating_date is not None and result_date < mating_date:
        return _result(
            "conflicting",
            result_value,
            "Pregnancy evidence conflicts with mating chronology",
            current=False,
            as_of=today,
            mating=latest,
            result_date=result_date,
            result_time=result_time,
            method=method,
            assessor=assessor,
            missing=[
                "Pregnancy result predates the latest mating and is not currently applicable."
            ],
        )

    actual_farrowing = _as_date(latest.get("actual_farrowing_date"))
    resolved_cycle = bool(
        actual_farrowing
        or _text(latest.get("linked_litter_id"))
        or _norm(latest.get("mating_status")) == "farrowed"
        or _norm(latest.get("outcome")) == "farrowed"
    )
    expected_farrowing = _as_date(latest.get("expected_farrowing_date"))
    days_since_mating = (
        (today - mating_date).days
        if mating_date is not None and today >= mating_date
        else None
    )
    stale = resolved_cycle or (
        expected_farrowing is not None
        and today > expected_farrowing
        and (today - expected_farrowing).days
        > CURRENT_PREGNANCY_FARROWING_GRACE_DAYS
    ) or (
        days_since_mating is not None
        and days_since_mating > CURRENT_PREGNANCY_MAX_DAYS_SINCE_MATING
    )
    if stale:
        return _result(
            "historical",
            result_value,
            "Historical pregnancy result; current status Unknown",
            current=False,
            as_of=today,
            stale=True,
            mating=latest,
            result_date=result_date,
            result_time=result_time,
            method=method,
            assessor=assessor,
            missing=missing_support + [
                "The latest pregnancy result is historical and does not establish current pregnancy status."
            ],
        )

    if category == "pregnant" and expected_farrowing is None:
        missing_support.append("Expected farrowing date is Unknown.")
    return _result(
        category,
        result_value,
        (
            "Confirmed pregnant"
            if category == "pregnant"
            else "Confirmed not pregnant for latest mating"
        ),
        current=True,
        as_of=today,
        mating=latest,
        result_date=result_date,
        result_time=result_time,
        method=method,
        assessor=assessor,
        missing=missing_support,
    )


def pregnancy_recommendation(evidence):
    state = _text((evidence or {}).get("state"))
    if state == "pregnant":
        return "monitor pregnancy and farrowing milestones"
    if state == "not_pregnant":
        return "review return-to-heat or repeat-service evidence"
    if state == "conflicting":
        if "future" in _text((evidence or {}).get("derived_status")).casefold():
            return "review and correct the future-dated reproductive chronology"
        return "reconcile conflicting pregnancy results for the latest mating"
    if state in {"historical", "unattributed"}:
        return "review current reproductive status before a breeding decision"
    if state == "no_governed_result":
        days = (evidence or {}).get("days_since_mating")
        if isinstance(days, int) and days >= 28:
            return "pregnancy check due"
        return "monitor next pregnancy-check milestone"
    return ""


def _result(
    state,
    result,
    derived_status,
    *,
    current,
    as_of=None,
    stale=False,
    mating=None,
    result_date=None,
    result_time="",
    method="",
    assessor="",
    missing=None,
):
    mating = mating or {}
    mating_date = _as_date(mating.get("mating_date"))
    today = as_of or date.today()
    return {
        "state": state,
        "governed_result": result,
        "result_date": result_date.isoformat() if result_date else "Unknown",
        "result_time": result_time or "Unknown",
        "method": method or "Unknown",
        "assessor": assessor or "Unknown",
        "freshness": "stale" if stale else "current" if current else "unresolved",
        "currently_applicable": bool(current),
        "derived_status": derived_status,
        "mating_date": mating_date.isoformat() if mating_date else "Unknown",
        "days_since_mating": (
            (today - mating_date).days
            if mating_date is not None and today >= mating_date
            else None
        ),
        "missing_supporting_evidence": list(missing or []),
    }


def _result_datetime(row):
    checked_at = row.get("pregnancy_checked_at")
    if isinstance(checked_at, datetime):
        return checked_at.date(), checked_at.time().isoformat()
    text = _text(checked_at)
    if text:
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
            return parsed.date(), parsed.time().isoformat()
        except ValueError:
            pass
    return (
        _as_date(row.get("pregnancy_check_date")),
        _text(row.get("pregnancy_check_time")),
    )


def _category(value):
    normalized = _norm(value)
    if normalized in _POSITIVE:
        return "pregnant"
    if normalized in _NEGATIVE:
        return "not_pregnant"
    if normalized in _PENDING:
        return ""
    return ""


def _display_result(value):
    normalized = _category(value)
    if normalized == "pregnant":
        return "Pregnant"
    if normalized == "not_pregnant":
        return "Not pregnant"
    return _text(value) or "Unknown"


def _first(row, *keys):
    for key in keys:
        value = _text(row.get(key))
        if value:
            return value
    return ""


def _norm(value):
    return _text(value).casefold().replace(" ", "_").replace("-", "_")


def _text(value):
    return str(value or "").strip()


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(_text(value)[:10])
    except ValueError:
        return None
