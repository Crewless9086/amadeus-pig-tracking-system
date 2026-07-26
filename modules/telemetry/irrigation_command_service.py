"""ROOTLINE plan-only irrigation command and evidence ledger.

This module deliberately has no transport, scheduler, retry, n8n, IFTTT, or
hardware dependency.  It can only validate immutable plan packets and append
review-state evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV
from modules.telemetry.irrigation_daily_plan_service import (
    OPERATING_TIMEZONE,
    canonical_plan_identity,
    operating_date,
)


CURRENT_STATES = frozenset(
    {
        "proposed",
        "awaiting_owner_approval",
        "approved_not_dispatched",
        "expired",
        "cancelled",
        "execution_prohibited",
    }
)
RESERVED_FUTURE_STATES = frozenset(
    {
        "dispatch_pending",
        "dispatched",
        "command_accepted",
        "physical_confirmation_pending",
        "running_confirmed",
        "stopped_confirmed",
        "completed",
        "ambiguous_outcome",
    }
)
TERMINAL_STATES = frozenset({"expired", "cancelled"})
KNOWN_ZONE_INVENTORY = {
    "B12345": {
        "zone_name": "B - Kamp",
        "inventory_classifications": [
            "unsafe_for_control",
            "inventory_partial",
            "actuator_unproven",
        ],
        "physical_platform": "Unavailable",
        "pump_dependency": "Unavailable",
        "tank_dependency": "Unavailable",
        "borehole_dependency": "Unavailable",
        "timeout_conflict": "60/120-minute timeout conflict unresolved",
        "legacy_controller_active": False,
        "legacy_controller_safe_for_activation": False,
    },
    "C12345": {
        "zone_name": "C - Kamp",
        "inventory_classifications": [
            "unsafe_for_control",
            "inventory_partial",
            "actuator_unproven",
        ],
        "physical_platform": "Unavailable",
        "pump_dependency": "Unavailable",
        "tank_dependency": "Unavailable",
        "borehole_dependency": "Unavailable",
        "timeout_conflict": "60/120-minute timeout conflict unresolved",
        "legacy_controller_active": False,
        "legacy_controller_safe_for_activation": False,
    },
}
AUTHORITY = {
    "writes_farm_data": False,
    "writes_telemetry": False,
    "mutates_schedule": False,
    "calls_ifttt": False,
    "calls_n8n": False,
    "controls_hardware": False,
    "dispatchable": False,
    "automatic_retry": False,
}


class CommandValidationError(ValueError):
    pass


class CommandConflictError(ValueError):
    pass


def prepare_command_contract(payload, *, now=None, inventory=None):
    payload = payload if isinstance(payload, dict) else {}
    now = _as_utc(now or datetime.now(timezone.utc))
    inventory = inventory if inventory is not None else KNOWN_ZONE_INVENTORY
    zone_id = str(payload.get("zone_id") or "").strip()
    zone = inventory.get(zone_id)
    if not zone:
        raise CommandValidationError("exact_zone_identity_required")
    supplied_name = str(payload.get("zone_name") or "").strip()
    if supplied_name and supplied_name != zone["zone_name"]:
        raise CommandValidationError("zone_identity_conflict")
    intent = str(payload.get("intent") or "").strip().upper()
    if intent not in {"ON", "OFF"}:
        raise CommandValidationError("intent_must_be_on_or_off")
    generation = _positive_int(payload.get("generation"), "generation_required")
    daily_plan_date = operating_date(payload.get("daily_plan_operating_date"))
    daily_plan_id = str(payload.get("daily_plan_id") or "").strip()
    if daily_plan_id != canonical_plan_identity(daily_plan_date):
        raise CommandValidationError("canonical_daily_plan_identity_required")
    daily_plan_generation = _positive_int(
        payload.get("daily_plan_generation"), "daily_plan_generation_required"
    )
    duration = _positive_int(payload.get("requested_duration_minutes"), "requested_duration_required")
    created_at = _parse_timestamp(payload.get("created_at"), "creation_time_required")
    expires_at = _parse_timestamp(payload.get("expires_at"), "expiry_time_required")
    if created_at > now or expires_at <= created_at:
        raise CommandValidationError("invalid_command_time_window")
    idempotency_key = str(payload.get("idempotency_key") or "").strip()
    if not idempotency_key or len(idempotency_key) > 200:
        raise CommandValidationError("bounded_idempotency_identity_required")

    weather = _object(payload, "weather_evidence")
    power = _object(payload, "power_evidence")
    water = _object(payload, "water_infrastructure_evidence")
    safety = _object(payload, "safety_interlocks")
    blockers = _blockers(zone, weather, power, water, safety, duration, now, expires_at)
    canonical = {
        "generation": generation,
        "daily_plan_id": daily_plan_id,
        "daily_plan_generation": daily_plan_generation,
        "daily_plan_operating_date": daily_plan_date.isoformat(),
        "daily_plan_operating_timezone": OPERATING_TIMEZONE,
        "zone_id": zone_id,
        "zone_name": zone["zone_name"],
        "intent": intent,
        "requested_duration_minutes": duration,
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "weather_evidence": weather,
        "power_evidence": power,
        "water_infrastructure_evidence": water,
        "controller_actuator_inventory": zone,
        "safety_interlocks": safety,
        "paired_off_required": intent == "ON",
        "paired_off_command_id": str(payload.get("paired_off_command_id") or "").strip() or None,
        "idempotency_key": idempotency_key,
        **AUTHORITY,
    }
    if canonical["paired_off_required"] and not canonical["paired_off_command_id"]:
        blockers.append("paired_off_command_unavailable")
    request_sha256 = _sha256(_canonical_json(canonical))
    command_id = "ROOTLINE-CMD-" + _sha256(f"{idempotency_key}:{generation}")[:24].upper()
    initial_state = "expired" if expires_at <= now else (
        "execution_prohibited" if blockers else "awaiting_owner_approval"
    )
    return {
        **canonical,
        "command_id": command_id,
        "request_sha256": request_sha256,
        "state": initial_state,
        "prohibition_reasons": sorted(set(blockers)),
        "owner_approval_identity": "Unavailable",
        "transport_authority": False,
        "writes_performed": False,
        "hardware_control_performed": False,
    }


def create_plan_only_command(payload, recorded_by, *, ledger=None, now=None, inventory=None):
    actor = str(recorded_by or "").strip()
    if not actor:
        return _failure("owner_admin_identity_required", 403)
    try:
        command = prepare_command_contract(payload, now=now, inventory=inventory)
    except CommandValidationError as exc:
        return _failure(str(exc), 400)
    ledger = ledger or PostgresIrrigationCommandLedger()
    try:
        result = ledger.append_command(command, actor)
    except CommandConflictError as exc:
        return _failure(str(exc), 409)
    except LedgerUnavailableError as exc:
        return _failure(str(exc), 503)
    except Exception:
        return _failure("irrigation_command_ledger_write_failed", 500)
    status = "plan_only_command_recorded" if result["created"] else "duplicate_command_suppressed"
    return {
        "success": True,
        "status": status,
        "command": result["command"],
        "events_appended": result["events_appended"],
        **AUTHORITY,
        "writes_performed": bool(result["created"]),
        "hardware_control_performed": False,
    }, 201 if result["created"] else 200


def approve_plan_only_command(command_id, recorded_by, *, ledger=None, now=None):
    actor = str(recorded_by or "").strip()
    if not actor:
        return _failure("owner_admin_identity_required", 403)
    ledger = ledger or PostgresIrrigationCommandLedger()
    try:
        command = ledger.get_command(str(command_id or "").strip())
        if not command:
            return _failure("command_not_found", 404)
        if not ledger.is_current_daily_plan(command):
            raise CommandConflictError("daily_plan_generation_superseded")
        timestamp = _as_utc(now or datetime.now(timezone.utc))
        if _parse_timestamp(command["expires_at"], "expiry_time_required") <= timestamp:
            events = ledger.append_review_states(command, ["expired"], actor, timestamp)
            state = "expired"
        else:
            states = ["approved_not_dispatched"]
            if command.get("prohibition_reasons"):
                states.append("execution_prohibited")
            events = ledger.append_review_states(command, states, actor, timestamp)
            state = states[-1]
    except CommandConflictError as exc:
        return _failure(str(exc), 409)
    except LedgerUnavailableError as exc:
        return _failure(str(exc), 503)
    except Exception:
        return _failure("irrigation_command_ledger_write_failed", 500)
    return {
        "success": True,
        "status": state,
        "command_id": command["command_id"],
        "generation": command["generation"],
        "owner_approval_identity": actor,
        "events_appended": events,
        "approval_dispatches": False,
        **AUTHORITY,
        "writes_performed": bool(events),
        "hardware_control_performed": False,
    }, 200


def cancel_plan_only_command(command_id, recorded_by, *, ledger=None, now=None):
    actor = str(recorded_by or "").strip()
    if not actor:
        return _failure("owner_admin_identity_required", 403)
    ledger = ledger or PostgresIrrigationCommandLedger()
    try:
        command = ledger.get_command(str(command_id or "").strip())
        if not command:
            return _failure("command_not_found", 404)
        events = ledger.append_review_states(
            command, ["cancelled"], actor, _as_utc(now or datetime.now(timezone.utc))
        )
    except CommandConflictError as exc:
        return _failure(str(exc), 409)
    except LedgerUnavailableError as exc:
        return _failure(str(exc), 503)
    except Exception:
        return _failure("irrigation_command_ledger_write_failed", 500)
    return {
        "success": True,
        "status": "cancelled",
        "command_id": command["command_id"],
        "events_appended": events,
        **AUTHORITY,
        "writes_performed": bool(events),
        "hardware_control_performed": False,
    }, 200


def list_plan_only_commands(*, ledger=None, now=None, limit=50):
    ledger = ledger or PostgresIrrigationCommandLedger()
    try:
        commands = ledger.list_commands(max(1, min(int(limit), 100)))
    except (LedgerUnavailableError, ValueError):
        return _failure("irrigation_command_ledger_unavailable", 503)
    timestamp = _as_utc(now or datetime.now(timezone.utc))
    for command in commands:
        if (
            command.get("state") not in TERMINAL_STATES
            and _parse_timestamp(command["expires_at"], "expiry_time_required") <= timestamp
        ):
            command["state"] = "expired"
        command.update(AUTHORITY)
    return {
        "success": True,
        "status": "plan_only_command_ledger",
        "commands": commands,
        "reserved_future_states": sorted(RESERVED_FUTURE_STATES),
        **AUTHORITY,
        "writes_performed": False,
        "hardware_control_performed": False,
    }, 200


@dataclass
class InMemoryIrrigationCommandLedger:
    commands: dict | None = None
    events: list | None = None
    current_daily_plans: dict | None = None

    def __post_init__(self):
        self.commands = {} if self.commands is None else self.commands
        self.events = [] if self.events is None else self.events
        self.current_daily_plans = (
            {} if self.current_daily_plans is None else self.current_daily_plans
        )

    def append_command(self, command, actor):
        for existing in self.commands.values():
            if existing["idempotency_key"] == command["idempotency_key"]:
                if existing["request_sha256"] != command["request_sha256"]:
                    raise CommandConflictError("idempotency_identity_conflict")
                return {"created": False, "command": dict(existing), "events_appended": 0}
            if (
                existing["zone_id"] == command["zone_id"]
                and existing["generation"] == command["generation"]
            ):
                raise CommandConflictError("zone_generation_conflict")
        stored = json.loads(json.dumps(command))
        self.current_daily_plans.setdefault(
            command["daily_plan_id"], command["daily_plan_generation"]
        )
        self.commands[command["command_id"]] = stored
        self.events.append(_event(command, "proposed", actor, command["created_at"]))
        if command["state"] != "proposed":
            self.events.append(_event(command, command["state"], actor, command["created_at"]))
        return {"created": True, "command": dict(stored), "events_appended": 2}

    def get_command(self, command_id):
        value = self.commands.get(command_id)
        return dict(value) if value else None

    def is_current_daily_plan(self, command):
        return self.current_daily_plans.get(command["daily_plan_id"]) == command[
            "daily_plan_generation"
        ]

    def append_review_states(self, command, states, actor, timestamp):
        if any(state not in CURRENT_STATES for state in states):
            raise CommandConflictError("future_execution_state_unreachable")
        existing_states = [
            event["state"] for event in self.events if event["command_id"] == command["command_id"]
        ]
        if existing_states and existing_states[-1] in TERMINAL_STATES:
            raise CommandConflictError("terminal_command_state")
        for state in states:
            self.events.append(_event(command, state, actor, timestamp.isoformat()))
        self.commands[command["command_id"]]["state"] = states[-1]
        if "approved_not_dispatched" in states:
            self.commands[command["command_id"]]["owner_approval_identity"] = actor
        return len(states)

    def list_commands(self, limit):
        return [dict(item) for item in list(self.commands.values())[-limit:]][::-1]


class PostgresIrrigationCommandLedger:
    def __init__(self, database_url=None, connect=None):
        self.database_url = (
            database_url if database_url is not None else os.environ.get(DATABASE_URL_ENV, "")
        )
        self.connect = connect

    def _connection(self):
        if not self.database_url:
            raise LedgerUnavailableError("irrigation_command_ledger_not_configured")
        connect = self.connect
        if connect is None:
            try:
                import psycopg
            except ImportError as exc:
                raise LedgerUnavailableError("irrigation_command_ledger_dependency_missing") from exc
            connect = psycopg.connect
        try:
            return connect(self.database_url, connect_timeout=10)
        except Exception as exc:
            raise LedgerUnavailableError("irrigation_command_ledger_unavailable") from exc

    def append_command(self, command, actor):
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select command_json, request_sha256
                       from public.irrigation_command_plans
                       where idempotency_key = %s""",
                    (command["idempotency_key"],),
                )
                existing = cursor.fetchone()
                if existing:
                    if str(existing[1]) != command["request_sha256"]:
                        raise CommandConflictError("idempotency_identity_conflict")
                    return {
                        "created": False,
                        "command": _json_value(existing[0]),
                        "events_appended": 0,
                    }
                cursor.execute(
                    """select 1 from public.irrigation_command_plans
                       where zone_id = %s and generation = %s limit 1""",
                    (command["zone_id"], command["generation"]),
                )
                if cursor.fetchone():
                    raise CommandConflictError("zone_generation_conflict")
                cursor.execute(
                    """insert into public.irrigation_command_plans
                       (command_id, generation, daily_plan_id, daily_plan_generation,
                        daily_plan_operating_date, zone_id, zone_name, intent,
                        requested_duration_minutes, created_at, expires_at,
                        idempotency_key, request_sha256, paired_off_required,
                        paired_off_command_id, weather_evidence, power_evidence,
                        water_infrastructure_evidence, controller_actuator_inventory,
                        safety_interlocks, prohibition_reasons, command_json, recorded_by)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,
                               %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,
                               %s::jsonb,%s)""",
                    (
                        command["command_id"], command["generation"],
                        command["daily_plan_id"], command["daily_plan_generation"],
                        command["daily_plan_operating_date"], command["zone_id"],
                        command["zone_name"], command["intent"],
                        command["requested_duration_minutes"], command["created_at"],
                        command["expires_at"], command["idempotency_key"],
                        command["request_sha256"], command["paired_off_required"],
                        command["paired_off_command_id"], _canonical_json(command["weather_evidence"]),
                        _canonical_json(command["power_evidence"]),
                        _canonical_json(command["water_infrastructure_evidence"]),
                        _canonical_json(command["controller_actuator_inventory"]),
                        _canonical_json(command["safety_interlocks"]),
                        _canonical_json(command["prohibition_reasons"]),
                        _canonical_json(command), actor,
                    ),
                )
                count = self._append_states(
                    cursor, command, ["proposed", command["state"]], actor,
                    _parse_timestamp(command["created_at"], "creation_time_required"),
                )
        return {"created": True, "command": command, "events_appended": count}

    def get_command(self, command_id):
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select p.command_json,
                              coalesce((select e.state from public.irrigation_command_state_events e
                                        where e.command_id = p.command_id
                                        order by e.event_sequence desc limit 1), 'proposed')
                       from public.irrigation_command_plans p where p.command_id = %s""",
                    (command_id,),
                )
                row = cursor.fetchone()
        if not row:
            return None
        command = _json_value(row[0])
        command["state"] = row[1]
        return command

    def append_review_states(self, command, states, actor, timestamp):
        if any(state not in CURRENT_STATES for state in states):
            raise CommandConflictError("future_execution_state_unreachable")
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select state from public.irrigation_command_state_events
                       where command_id = %s order by event_sequence desc limit 1
                       for update""",
                    (command["command_id"],),
                )
                row = cursor.fetchone()
                if row and row[0] in TERMINAL_STATES:
                    raise CommandConflictError("terminal_command_state")
                return self._append_states(cursor, command, states, actor, timestamp)

    def is_current_daily_plan(self, command):
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select current_generation=%s
                       from public.irrigation_daily_plan_identities
                       where daily_plan_id=%s and operating_date=%s""",
                    (
                        command["daily_plan_generation"],
                        command["daily_plan_id"],
                        command["daily_plan_operating_date"],
                    ),
                )
                row = cursor.fetchone()
        return bool(row and row[0])

    def list_commands(self, limit):
        with self._connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select p.command_json,
                              coalesce((select e.state from public.irrigation_command_state_events e
                                        where e.command_id = p.command_id
                                        order by e.event_sequence desc limit 1), 'proposed'),
                              (select e.owner_approval_identity
                               from public.irrigation_command_state_events e
                               where e.command_id = p.command_id
                                 and e.state = 'approved_not_dispatched'
                               order by e.event_sequence desc limit 1)
                       from public.irrigation_command_plans p
                       order by p.created_at desc, p.command_id desc limit %s""",
                    (limit,),
                )
                rows = cursor.fetchall()
        result = []
        for raw, state, approval in rows:
            command = _json_value(raw)
            command["state"] = state
            command["owner_approval_identity"] = approval or "Unavailable"
            result.append(command)
        return result

    @staticmethod
    def _append_states(cursor, command, states, actor, timestamp):
        appended = 0
        for state in states:
            cursor.execute(
                """insert into public.irrigation_command_state_events
                   (event_id, command_id, generation, state, occurred_at,
                    owner_approval_identity, evidence_json)
                   values (%s,%s,%s,%s,%s,%s,%s::jsonb)
                   on conflict (event_id) do nothing""",
                (
                    _event_id(command["command_id"], state, actor, timestamp, appended),
                    command["command_id"], command["generation"], state,
                    timestamp, actor if state == "approved_not_dispatched" else None,
                    _canonical_json({
                        "prohibition_reasons": command.get("prohibition_reasons", []),
                        **AUTHORITY,
                    }),
                ),
            )
            appended += cursor.rowcount
        return appended


class LedgerUnavailableError(RuntimeError):
    pass


def _blockers(zone, weather, power, water, safety, duration, now, expires_at):
    blockers = []
    classifications = set(zone.get("inventory_classifications") or [])
    for item in ("unsafe_for_control", "inventory_partial", "actuator_unproven"):
        if item in classifications:
            blockers.append(item)
    if zone.get("physical_platform") in {None, "", "Unavailable"}:
        blockers.append("physical_platform_unavailable")
    if zone.get("timeout_conflict"):
        blockers.append("timeout_conflict_unresolved")
    for dependency in ("pump_dependency", "tank_dependency", "borehole_dependency"):
        if zone.get(dependency) in {None, "", "Unavailable"}:
            blockers.append(f"{dependency}_unavailable")
    if zone.get("legacy_controller_active"):
        blockers.append("unsafe_legacy_controller_active")
    if zone.get("legacy_controller_safe_for_activation") is not True:
        blockers.append("controller_activation_prohibited")
    if weather.get("availability") != "Available":
        blockers.append("weather_unavailable")
    if weather.get("freshness") != "fresh":
        blockers.append("weather_stale")
    if weather.get("forecast_availability") != "Available":
        blockers.append("forecast_unavailable")
    if weather.get("forecast_freshness") != "fresh":
        blockers.append("forecast_stale")
    if power.get("availability") != "Available":
        blockers.append("power_unavailable")
    if power.get("freshness") != "fresh":
        blockers.append("power_stale")
    if power.get("confidence") != "verified" or power.get("suspicious") is not False:
        blockers.append("power_suspicious_or_unverified")
    for dependency in ("tank", "pump", "borehole"):
        evidence = water.get(dependency)
        if not isinstance(evidence, dict) or evidence.get("availability") != "Available":
            blockers.append(f"{dependency}_evidence_unavailable")
        elif evidence.get("readiness") != "ready":
            blockers.append(f"{dependency}_not_ready")
    required_interlocks = (
        "manual_isolation_verified",
        "failure_safe_verified",
        "paired_off_ready",
        "simultaneous_zone_constraint_verified",
        "fertilizer_interlock_verified",
        "flow_feedback_available",
        "pressure_feedback_available",
        "valve_feedback_available",
    )
    blockers.extend(f"{name}_missing" for name in required_interlocks if safety.get(name) is not True)
    max_runtime = zone.get("max_runtime_minutes")
    if not isinstance(max_runtime, int) or max_runtime <= 0:
        blockers.append("safe_maximum_runtime_unavailable")
    elif duration > max_runtime:
        blockers.append("requested_duration_exceeds_safe_maximum")
    if expires_at <= now:
        blockers.append("command_expired")
    return blockers


def _event(command, state, actor, timestamp):
    return {
        "event_id": _event_id(command["command_id"], state, actor, timestamp, 0),
        "command_id": command["command_id"],
        "generation": command["generation"],
        "state": state,
        "occurred_at": str(timestamp),
        "owner_approval_identity": actor if state == "approved_not_dispatched" else None,
        **AUTHORITY,
    }


def _event_id(command_id, state, actor, timestamp, sequence):
    return "ROOTLINE-EVENT-" + _sha256(
        f"{command_id}:{state}:{actor}:{timestamp}:{sequence}"
    )[:24].upper()


def _object(payload, key):
    value = payload.get(key)
    if not isinstance(value, dict):
        raise CommandValidationError(f"{key}_object_required")
    return json.loads(json.dumps(value))


def _positive_int(value, error):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise CommandValidationError(error)
    if result <= 0:
        raise CommandValidationError(error)
    return result


def _parse_timestamp(value, error):
    if isinstance(value, datetime):
        return _as_utc(value)
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except ValueError:
        raise CommandValidationError(error)
    if parsed.tzinfo is None:
        raise CommandValidationError(error)
    return _as_utc(parsed)


def _as_utc(value):
    return value.astimezone(timezone.utc)


def _canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256(value):
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _json_value(value):
    if isinstance(value, dict):
        return json.loads(json.dumps(value))
    return json.loads(value)


def _failure(status, status_code):
    return {
        "success": False,
        "status": status,
        **AUTHORITY,
        "writes_performed": False,
        "hardware_control_performed": False,
    }, status_code
