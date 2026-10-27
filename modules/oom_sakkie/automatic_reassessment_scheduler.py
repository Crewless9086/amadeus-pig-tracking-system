"""Durable, authority-free ownership for scheduled specialist reassessments."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo

SAST = ZoneInfo("Africa/Johannesburg")
CONTRACT_VERSION = "oom_sakkie_reassessment_schedule.v1"
SCHEDULER_IDENTITY = "ALERT-POWER-BACKEND-DELIVERY:OOM-SAKKIE-REASSESSMENT"
ENABLED_SPECIALISTS = frozenset({"ROOTLINE"})
CADENCE_MINUTES = 1
MAX_CLOCK_DRIFT = timedelta(minutes=5)
MAX_MISSED_RUN_AGE = timedelta(minutes=5)


def run_due_reassessment(*, payload: Mapping[str, Any], invoke: Callable[[], Mapping[str, Any]],
                         store: Callable[[str, str, Any], Any], now: datetime | None = None,
                         recover_delivery: Callable[[], Mapping[str, Any]] | None = None,
                         invoke_not_due: Callable[[], Mapping[str, Any]] | None = None):
    """Claim and run one due bucket. This contract grants no operational authority."""
    now = _aware(now or datetime.now(timezone.utc))
    specialist = str(payload.get("specialist") or "").upper()
    scheduler = str(payload.get("scheduler_identity") or "")
    due = _parse(payload.get("due_at"))
    cutoff = _parse(payload.get("evidence_cutoff"))
    if scheduler != SCHEDULER_IDENTITY or specialist not in ENABLED_SPECIALISTS or not due or not cutoff:
        return _contained("scheduled_reassessment_binding_invalid")
    if (cutoff > now + MAX_CLOCK_DRIFT or due > now + MAX_CLOCK_DRIFT
            or now - due > MAX_MISSED_RUN_AGE):
        return _contained("scheduled_reassessment_not_due")
    bucket = _bucket(due)
    identity = f"OOM-SCHEDULE-{specialist}-{bucket.strftime('%Y%m%dT%H%M%S%z')}"
    digest = hashlib.sha256(
        f"{CONTRACT_VERSION}|{scheduler}|{specialist}|{bucket.isoformat()}".encode()
    ).hexdigest()
    prior_identity = store("load_schedule", identity, None) or {}
    if prior_identity.get("status") in {"completed", "contained"}:
        recovered = (dict(recover_delivery() or {})
            if recover_delivery and prior_identity.get("report_work_due") is not False else {})
        if recovered and recovered.get("status") not in {
                "no_reassessable_mixer_presence", "protected_delivery_terminal_noop"}:
            return {**recovered, "schedule_identity": identity,
                "invocation_receipt": digest, "terminal_outcome": prior_identity["status"]}
        return {**_safe("scheduled_reassessment_replayed_noop"), "schedule_identity": identity,
                "invocation_receipt": digest, "terminal_outcome": prior_identity["status"]}
    latest = store("load_latest_outcome", specialist, None) or {}
    owned_due = _parse(latest.get("next_due_at"))
    reports_due = not (owned_due and now < owned_due
        and not _current_bucket_second_offset(now, owned_due))
    if not reports_due and invoke_not_due is None:
        return {**_safe("scheduled_reassessment_not_yet_due"),
                "next_due_at": owned_due.astimezone(SAST).isoformat()}
    record = {"contract_version": CONTRACT_VERSION, "schedule_identity": identity,
              "scheduler_identity": scheduler, "specialist": specialist,
              "due_at": bucket.isoformat(), "evidence_cutoff": cutoff.isoformat(),
              "invoked_at": now.isoformat(), "invocation_receipt": digest,
              "status": "claimed", "terminal_outcome": "",
              "report_work_due": bool(reports_due)}
    claimed = store("claim_schedule", identity, record)
    if not isinstance(claimed, Mapping) or claimed.get("success") is not True:
        return _contained("scheduled_reassessment_claim_unproven")
    existing = store("load_schedule", identity, None) or record
    if existing.get("invocation_receipt") != digest:
        return _contained("scheduled_reassessment_binding_conflict")
    if claimed.get("created") is False:
        if existing.get("status") in {"completed", "contained"}:
            return {**_safe("scheduled_reassessment_replayed_noop"), "schedule_identity": identity,
                    "invocation_receipt": digest, "terminal_outcome": existing.get("status")}
        recovered = (dict(recover_delivery() or {})
            if recover_delivery and existing.get("report_work_due") is not False else {})
        if recovered:
            return {**recovered, "schedule_identity": identity,
                "invocation_receipt": digest, "terminal_outcome": "claimed"}
        return {**_safe("scheduled_reassessment_claim_interrupted"),
            "success": False, "schedule_identity": identity,
            "invocation_receipt": digest, "terminal_outcome": "claimed"}
    try:
        # The optional callback is a no-new-start safety obligation, admitted
        # by this same minute claim. It must not run report/planning work.
        result = dict((invoke if reports_due else invoke_not_due)() or {})
    except Exception:
        result = _contained("scheduled_reassessment_specialist_failure")
    terminal = "completed" if result.get("success") is True else "contained"
    # A safety-only outcome preserves the reporting due time exactly. The
    # existing minute scheduler can still claim its next safety check without
    # accelerating reports or adding another timer/queue.
    next_due = _next_due(now, result) if reports_due else owned_due.astimezone(SAST)
    safety_next = (_bucket(now.astimezone(SAST)) + timedelta(minutes=CADENCE_MINUTES)).isoformat()
    if invoke_not_due is not None:
        result["supervision_next_due_at"] = safety_next
    outcome = {**record, "status": terminal, "terminal_outcome": str(result.get("status") or terminal),
               "material_digest": str(result.get("material_digest") or ""),
               "execution_status": str(result.get("execution_status") or ""),
               "active_supervision_status": str(result.get("active_supervision_status") or ""),
               "supervision_next_due_at": str(result.get("supervision_next_due_at") or ""),
               "report_work_due": bool(reports_due),
               "active_supervision_write_attempted": result.get("active_supervision_write_attempted") is True,
               "provider_effects_unknown": result.get("provider_effects_unknown") is True,
               "report_effects_unknown": result.get("report_effects_unknown") is True,
               "plan_delivery_status": str(result.get("plan_delivery_status") or ""),
               "fertilizer_commissioning_status": str(
                   result.get("fertilizer_commissioning_status") or ""),
               "next_due_at": next_due.isoformat(), "telegram_sends": int(result.get("telegram_sends") or 0),
               "telegram_edits": int(result.get("telegram_edits") or 0),
               "hardware_commands": int(result.get("hardware_commands") or 0),
               "writes_farm_data": result.get("writes_farm_data", False)}
    try:
        stored = store("record_outcome", identity, outcome)
    except Exception:
        stored = None
    if not isinstance(stored, Mapping) or stored.get("success") is not True:
        # The specialist may already have stopped equipment. Failed outcome
        # persistence must not rewrite those effects as an authority-free noop.
        return {**result, "success": False, "status": "scheduled_reassessment_outcome_unproven",
            "schedule_identity": identity, "invocation_receipt": digest,
            "terminal_outcome": "claimed", "outcome_recorded": False}
    return {**result, "schedule_identity": identity, "invocation_receipt": digest,
            "terminal_outcome": terminal, "next_due_at": next_due.isoformat()}


def _bucket(value: datetime) -> datetime:
    local = value.astimezone(SAST)
    minute = local.minute - local.minute % CADENCE_MINUTES
    return local.replace(minute=minute, second=0, microsecond=0)


def _current_bucket_second_offset(now: datetime, due: datetime) -> bool:
    """Accept scheduler jitter only at the current canonical bucket edge.

    Durable due times can retain seconds from a prior invocation while the
    recurring cron is minute-aligned.  Without this bounded tolerance, a cron
    that consistently arrives a few seconds before the retained timestamp can
    suppress every later invocation.  A due time in any later minute or bucket
    remains strictly future work.
    """
    local_now = _aware(now).astimezone(SAST)
    local_due = _aware(due).astimezone(SAST)
    bucket = _bucket(local_now)
    return (_bucket(local_due) == bucket
            and local_due.minute == bucket.minute)


def _next_due(now: datetime, result: Mapping[str, Any]) -> datetime:
    raw = result.get("next_due_at")
    parsed = _parse(raw) if raw else None
    if parsed and parsed > now:
        return parsed.astimezone(SAST)
    return _bucket(now.astimezone(SAST)) + timedelta(minutes=CADENCE_MINUTES)


def _parse(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return _aware(parsed)
    except (TypeError, ValueError):
        return None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _safe(status):
    return {"success": True, "status": status, "notify_owner": False, "telegram_sends": 0,
            "telegram_edits": 0, "hardware_commands": 0, "writes_farm_data": False,
            "automatic_irrigation_authority": False}


def _contained(status):
    return {**_safe(status), "success": False, "terminal_outcome": "contained"}
