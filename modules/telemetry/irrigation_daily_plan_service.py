"""Canonical, owner-read-only ROOTLINE daily irrigation plans.

Generation is an internal persistence operation only.  This module has no
scheduler, transport, command, retry, IFTTT, n8n, or hardware dependency.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime
from zoneinfo import ZoneInfo

from services.database_service import DATABASE_URL_ENV


OPERATING_TIMEZONE = "Africa/Johannesburg"
PLAN_STATES = frozenset(
    {"planned", "missed", "stale", "unavailable", "no_irrigation_required"}
)
NO_AUTHORITY = {
    "schedule_enabled": False,
    "command_created": False,
    "dispatchable": False,
    "calls_ifttt": False,
    "calls_n8n": False,
    "controls_hardware": False,
    "writes_performed": False,
    "hardware_control_performed": False,
}


class DailyPlanValidationError(ValueError):
    pass


class DailyPlanUnavailableError(RuntimeError):
    pass


def operating_date(value=None):
    if value in (None, ""):
        return datetime.now(ZoneInfo(OPERATING_TIMEZONE)).date()
    if isinstance(value, datetime):
        return value.astimezone(ZoneInfo(OPERATING_TIMEZONE)).date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise DailyPlanValidationError("invalid_operating_date") from exc


def canonical_plan_identity(day):
    return f"ROOTLINE-DAILY-PLAN-{operating_date(day).strftime('%Y%m%d')}"


def prepare_daily_plan(payload):
    payload = payload if isinstance(payload, dict) else {}
    day = operating_date(payload.get("operating_date"))
    state = str(payload.get("status") or "").strip()
    if state not in PLAN_STATES:
        raise DailyPlanValidationError("explicit_daily_plan_status_required")
    observed = _timestamp(payload.get("evidence_observed_at"))
    reason = str(payload.get("replacement_reason") or "").strip()
    if not reason:
        raise DailyPlanValidationError("replacement_reason_required")
    evidence = payload.get("evidence")
    if not isinstance(evidence, dict):
        raise DailyPlanValidationError("evidence_object_required")
    zones = payload.get("zones")
    if not isinstance(zones, list):
        raise DailyPlanValidationError("zones_array_required")
    canonical = {
        "daily_plan_id": canonical_plan_identity(day),
        "operating_date": day.isoformat(),
        "operating_timezone": OPERATING_TIMEZONE,
        "status": state,
        "evidence_observed_at": observed.isoformat(),
        "replacement_reason": reason,
        "evidence": evidence,
        "zones": zones,
    }
    canonical["evidence_sha256"] = _sha256(
        {"status": state, "evidence": evidence, "zones": zones}
    )
    return canonical


def generate_or_reuse_daily_plan(payload, *, ledger=None):
    """Internal plan persistence contract; deliberately not exposed as a route."""
    plan = prepare_daily_plan(payload)
    ledger = ledger or PostgresDailyPlanLedger()
    return ledger.generate_or_reuse(plan)


def project_rootline_specialist_daily_plan(result, *, ledger=None):
    """Persist the current specialist decision as the date-stable plan ledger.

    This projection grants no scheduling or command authority.  It only closes
    the canonical-plan gap before the separately gated execution runtime is
    allowed to consider a segment.
    """
    current = result if isinstance(result, dict) else {}
    if current.get("success") is not True:
        raise DailyPlanValidationError("successful_rootline_result_required")
    day = operating_date(current.get("operating_date"))
    observed = _timestamp(current.get("evidence_cutoff"))
    zones = []
    for row in current.get("recommendations") or []:
        if not isinstance(row, dict) or row.get("subject") not in {"B12345", "C12345"}:
            continue
        zones.append({key: row.get(key) for key in (
            "subject", "status", "reason", "planned_duration_minutes", "preferred_window"
        )})
    decisions = {str(row.get("status") or "") for row in zones}
    if "Recommend" in decisions:
        state = "planned"
    elif zones and decisions <= {"Do Not Run"}:
        state = "no_irrigation_required"
    elif zones:
        state = "stale"
    else:
        state = "unavailable"
    evidence = {key: current.get(key) for key in (
        "result_id", "generation", "evidence_cutoff", "overall_status"
    )}
    selected_ledger = ledger or PostgresDailyPlanLedger()
    receipt = generate_or_reuse_daily_plan({
        "operating_date": day.isoformat(), "status": state,
        "evidence_observed_at": observed.isoformat(),
        "replacement_reason": "scheduled_rootline_specialist_projection",
        "evidence": evidence, "zones": zones,
    }, ledger=selected_ledger)
    if type(receipt.get("created")) is not bool:
        raise DailyPlanUnavailableError("daily_plan_write_receipt_unproven")
    written = receipt.get("daily_plan")
    required = ("daily_plan_id", "operating_date", "generation", "evidence_sha256")
    if (not isinstance(written, dict)
            or any(written.get(key) in (None, "") for key in required)):
        raise DailyPlanUnavailableError("daily_plan_write_binding_unproven")
    current = selected_ledger.get_current(day)
    if (not isinstance(current, dict)
            or any(str(current.get(key) or "") != str(written.get(key) or "")
                   for key in required)):
        raise DailyPlanUnavailableError("daily_plan_readback_binding_unproven")
    return {**receipt, "success": True,
        "status": ("daily_plan_created" if receipt["created"]
                   else "daily_plan_reused"), "daily_plan": current,
        "readback_bound": True}


def get_current_daily_plan(value=None, *, ledger=None):
    try:
        day = operating_date(value)
        selected_ledger = ledger or PostgresDailyPlanLedger()
        current = selected_ledger.get_current(day)
        history = selected_ledger.get_history(day, exclude_generation=(
            current["generation"] if current else None
        ))
    except DailyPlanValidationError as exc:
        return _failure(str(exc), 400)
    except DailyPlanUnavailableError:
        return _failure("daily_irrigation_plan_unavailable", 503)
    except Exception as exc:
        if "irrigation_daily_plan_identities" in str(exc):
            return {
                "success": True, "status": "no_current_canonical_artifact",
                "operating_date": day.isoformat(),
                "operating_timezone": OPERATING_TIMEZONE,
                "daily_plan": None, "superseded_history": [],
                "owner_message": (
                    "No separate daily-plan ledger is active; current ROOTLINE truth is "
                    "projected from the scheduler, evidence and execution rails."
                ),
                **NO_AUTHORITY,
            }, 200
        return _failure("daily_irrigation_plan_unavailable", 503)
    if current is None:
        return {
            "success": True,
            "status": "unavailable",
            "operating_date": day.isoformat(),
            "operating_timezone": OPERATING_TIMEZONE,
            "daily_plan": None,
            "superseded_history": [],
            "owner_message": "No canonical daily irrigation plan evidence is available.",
            **NO_AUTHORITY,
        }, 200
    return {
        "success": True,
        "status": current["status"],
        "operating_date": day.isoformat(),
        "operating_timezone": OPERATING_TIMEZONE,
        "daily_plan": current,
        "superseded_history": history,
        "owner_message": _owner_message(current),
        **NO_AUTHORITY,
    }, 200


@dataclass
class InMemoryDailyPlanLedger:
    identities: dict | None = None
    generations: dict | None = None

    def __post_init__(self):
        self.identities = {} if self.identities is None else self.identities
        self.generations = {} if self.generations is None else self.generations

    def generate_or_reuse(self, plan):
        identity = self.identities.get(plan["operating_date"])
        if identity:
            current = self.generations[(identity["daily_plan_id"], identity["current_generation"])]
            if current["evidence_sha256"] == plan["evidence_sha256"]:
                return {"created": False, "superseded_generation": None, "daily_plan": dict(current)}
            generation = identity["current_generation"] + 1
            superseded = identity["current_generation"]
        else:
            generation, superseded = 1, None
        row = {**plan, "generation": generation}
        self.generations[(plan["daily_plan_id"], generation)] = row
        self.identities[plan["operating_date"]] = {
            "daily_plan_id": plan["daily_plan_id"], "current_generation": generation
        }
        return {"created": True, "superseded_generation": superseded, "daily_plan": dict(row)}

    def get_current(self, day):
        identity = self.identities.get(day.isoformat())
        if not identity:
            return None
        return dict(self.generations[(identity["daily_plan_id"], identity["current_generation"])])

    def get_history(self, day, *, exclude_generation=None):
        identity = self.identities.get(day.isoformat())
        if not identity:
            return []
        rows = [
            {**value, "history_status": "superseded", "is_current": False}
            for (plan_id, generation), value in self.generations.items()
            if plan_id == identity["daily_plan_id"] and generation != exclude_generation
        ]
        return sorted(rows, key=lambda item: item["generation"], reverse=True)


class PostgresDailyPlanLedger:
    def __init__(self, database_url=None, connect=None):
        self.database_url = (
            database_url if database_url is not None else os.environ.get(DATABASE_URL_ENV, "")
        )
        self.connect = connect

    def _connection(self):
        if not self.database_url:
            raise DailyPlanUnavailableError("daily_plan_ledger_not_configured")
        if self.connect:
            return self.connect(self.database_url)
        try:
            import psycopg
        except ImportError as exc:
            raise DailyPlanUnavailableError("postgres_driver_unavailable") from exc
        return psycopg.connect(self.database_url)

    def generate_or_reuse(self, plan):
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select created, superseded_generation, generation
                       from public.rootline_generate_daily_irrigation_plan(
                         %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)""",
                    (
                        plan["daily_plan_id"], plan["operating_date"],
                        plan["operating_timezone"], plan["status"], plan["evidence_sha256"],
                        plan["evidence_observed_at"], plan["replacement_reason"],
                        _json(plan["evidence"]), _json(plan["zones"]),
                    ),
                )
                created, superseded, generation = cursor.fetchone()
        current = {**plan, "generation": generation}
        return {
            "created": created,
            "superseded_generation": superseded,
            "daily_plan": current,
        }

    def get_current(self, day):
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select g.daily_plan_id,g.generation,g.operating_date,g.status,
                              g.evidence_observed_at,g.replacement_reason,
                              g.evidence_sha256,g.evidence_json,g.zones_json
                       from public.irrigation_daily_plan_identities i
                       join public.irrigation_daily_plan_generations g
                         on g.daily_plan_id=i.daily_plan_id
                        and g.generation=i.current_generation
                       where i.operating_date=%s""",
                    (day,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return {
            "daily_plan_id": row[0], "generation": row[1],
            "operating_date": row[2].isoformat(), "operating_timezone": OPERATING_TIMEZONE,
            "status": row[3], "evidence_observed_at": row[4].isoformat(),
            "replacement_reason": row[5], "evidence_sha256": row[6],
            "evidence": row[7], "zones": row[8],
        }

    def get_history(self, day, *, exclude_generation=None):
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select g.daily_plan_id,g.generation,g.operating_date,g.status,
                              g.evidence_observed_at,g.replacement_reason,
                              g.evidence_sha256,g.evidence_json,g.zones_json
                       from public.irrigation_daily_plan_generations g
                       where g.operating_date=%s and (%s::integer is null or g.generation<>%s)
                       order by g.generation desc limit 31""",
                    (day, exclude_generation, exclude_generation),
                )
                rows = cursor.fetchall()
        return [{
            "daily_plan_id": row[0], "generation": row[1],
            "operating_date": row[2].isoformat(), "operating_timezone": OPERATING_TIMEZONE,
            "status": row[3], "evidence_observed_at": row[4].isoformat(),
            "replacement_reason": row[5], "evidence_sha256": row[6],
            "evidence": row[7], "zones": row[8],
            "history_status": "superseded", "is_current": False,
        } for row in rows]


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError as exc:
        raise DailyPlanValidationError("evidence_time_required") from exc
    if parsed.tzinfo is None:
        raise DailyPlanValidationError("evidence_time_required")
    return parsed


def _sha256(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _owner_message(plan):
    labels = {
        "planned": "Today has one current irrigation plan.",
        "missed": "Today's irrigation plan is marked missed.",
        "stale": "Today's plan evidence is stale and requires review.",
        "unavailable": "Today's plan evidence is unavailable.",
        "no_irrigation_required": "Current evidence says no irrigation is required today.",
    }
    return labels[plan["status"]]


def _failure(status, code):
    return {
        "success": False, "status": status, "daily_plan": None,
        "superseded_history": [], **NO_AUTHORITY,
    }, code
