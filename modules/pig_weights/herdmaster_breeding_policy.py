"""Shared HERDMASTER breeding thresholds and canonical completion evidence."""

from datetime import date, datetime

from modules.pig_weights.herdmaster_daily_brief_service import _litter_terminal

BREEDING_BODY_CONDITION_MIN = 3.0
BREEDING_BODY_CONDITION_MAX = 5.0


def governed_weaning_evidence(litter, *, today):
    """A planned date is not the governed completion needed for a placement clock."""
    litter = litter or {}
    birth = _day(litter.get("farrowing_date") or litter.get("birth_date"))
    recorded = _day(litter.get("wean_date"))
    terminal = _litter_terminal(litter)
    result = {"state": "not_completed", "litter_id": str(litter.get("litter_id") or ""),
        "litter_status": str(litter.get("litter_status") or ""),
        "weaned_count": litter.get("weaned_count"),
        "recorded_wean_date": recorded.isoformat() if recorded else None,
        "planned_wean_date": recorded.isoformat() if recorded and not terminal else None,
        "completed_wean_date": None}
    if litter and (not birth or birth > today):
        result.update(state="unresolved", reason="The attributable birth date is missing, invalid or future-dated.")
    elif terminal:
        if str(litter.get("litter_id") or "").strip() and recorded and birth and birth <= recorded <= today:
            result.update(state="completed", completed_wean_date=recorded.isoformat())
        else:
            result.update(state="unresolved", reason="Litter completion is recorded but its attributable identity or actual weaning date is missing or contradictory.")
    elif litter.get("wean_date") and not recorded:
        result.update(state="unresolved", reason="The recorded weaning date is invalid; completion is unproven.")
    return result


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value or ""))
    except ValueError:
        return None
