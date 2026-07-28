"""Append-only isolated runtime control for SAM Livestock Level 1."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Mapping

from services.database_service import DATABASE_URL_ENV


TABLE = "sam_live_stock_level1_control_events"
CONTROL_VERSION = "sam_live_stock_level1_control_v1"
POLICY_VERSION = "sam_sales_autonomy_level_1_v1"
ALLOWED_STATES = {"enabled", "disabled", "killed"}
MAX_CARRIED_BINDINGS = 25


def build_level1_control_event(
    state,
    *,
    actor_id,
    reason,
    prior_event=None,
    carried_bindings=(),
    intake_write_authorized=False,
    now=None,
    lifetime_days=30,
):
    """Build one content-free, replay-stable owner control event."""
    state = str(state or "").strip().lower()
    actor_id = str(actor_id or "").strip()[:160]
    reason = " ".join(str(reason or "").split())[:500]
    if state not in ALLOWED_STATES:
        raise ValueError("level1_control_state_invalid")
    if not actor_id.startswith("owner-admin:"):
        raise ValueError("server_derived_owner_admin_required")
    if not reason:
        raise ValueError("level1_control_reason_required")
    now = _aware(now or datetime.now(timezone.utc))
    lifetime_days = max(1, min(int(lifetime_days), 30))
    bindings = _validated_bindings(carried_bindings)
    prior_id = _text((prior_event or {}).get("control_event_id"), 120)
    if prior_event and not prior_id:
        raise ValueError("level1_control_prior_event_invalid")
    canonical = {
        "version": CONTROL_VERSION,
        "policy_version": POLICY_VERSION,
        "state": state,
        "prior_event_id": prior_id,
        "actor_id": actor_id,
        "reason": reason,
        "activation_cutoff_utc": now.isoformat(),
        "effective_at": now.isoformat(),
        "expires_at": (now + timedelta(days=lifetime_days)).isoformat(),
        "carried_bindings": bindings,
        "intake_write_authorized": intake_write_authorized is True,
    }
    digest = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest().upper()
    return {
        "control_event_id": f"SAM-LIVE-STOCK-L1-CONTROL-{digest[:24]}",
        **canonical,
        "created_at": now.isoformat(),
        "contains_customer_content": False,
        "sends_customer_message": False,
        "mutates_business_state": False,
    }


def append_level1_control_event(event, *, database_url=None):
    """Persist exactly one append-only transition; conflicts fail closed."""
    row = dict(event or {})
    error = _validate_event(row)
    if error:
        return _result(error), 400
    database_url = database_url or os.getenv(DATABASE_URL_ENV, "")
    if not database_url:
        return _result("level1_control_storage_unavailable"), 503
    try:
        import psycopg

        with psycopg.connect(
            database_url,
            connect_timeout=5,
            options="-c statement_timeout=8000 -c lock_timeout=2000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select control_event_id, state
                    from public.{TABLE}
                    where (
                      nullif(%s, '') is not null
                      and prior_event_id = nullif(%s, '')
                    ) or (
                      nullif(%s, '') is null
                      and prior_event_id is null
                    ) or control_event_id = %s
                    for share
                    """,
                    (
                        row["prior_event_id"],
                        row["prior_event_id"],
                        row["prior_event_id"],
                        row["control_event_id"],
                    ),
                )
                existing = cursor.fetchall()
                conflict = next(
                    (
                        item
                        for item in existing
                        if item[0] != row["control_event_id"]
                        or item[1] != row["state"]
                    ),
                    None,
                )
                if conflict:
                    connection.rollback()
                    return _result("level1_control_transition_conflict"), 409
                cursor.execute(
                    f"""
                    insert into public.{TABLE} (
                      control_event_id, prior_event_id, state, policy_version,
                      activation_cutoff_utc, carried_bindings_json, actor_id,
                      intake_write_authorized, reason, created_at, effective_at, expires_at,
                      contains_customer_content, sends_customer_message,
                      mutates_business_state
                    ) values (
                      %(control_event_id)s, nullif(%(prior_event_id)s, ''),
                      %(state)s, %(policy_version)s,
                      %(activation_cutoff_utc)s::timestamptz,
                      %(carried_bindings_json)s::jsonb, %(actor_id)s,
                      %(intake_write_authorized)s, %(reason)s,
                      %(created_at)s::timestamptz, %(effective_at)s::timestamptz,
                      %(expires_at)s::timestamptz, false, false, false
                    )
                    on conflict (control_event_id) do nothing
                    returning control_event_id
                    """,
                    {
                        **row,
                        "carried_bindings_json": json.dumps(
                            row["carried_bindings"],
                            sort_keys=True,
                            separators=(",", ":"),
                        ),
                    },
                )
                created = cursor.fetchone()
            connection.commit()
        return _result(
            "level1_control_event_recorded"
            if created
            else "level1_control_replay_withheld",
            created=bool(created),
            control_event_id=row["control_event_id"],
        ), 201 if created else 200
    except Exception as exc:
        return _result(
            "level1_control_persistence_failed",
            error_type=exc.__class__.__name__,
        ), 503


def load_current_level1_control(*, database_url=None):
    """Load the sole latest control state in a read-only transaction."""
    database_url = database_url or os.getenv(DATABASE_URL_ENV, "")
    if not database_url:
        return _result("level1_control_storage_unavailable", event={}), 503
    try:
        import psycopg

        with psycopg.connect(
            database_url,
            connect_timeout=5,
            options="-c default_transaction_read_only=on -c statement_timeout=8000",
        ) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select control_event_id, prior_event_id, state,
                           policy_version, activation_cutoff_utc,
                           carried_bindings_json, actor_id,
                           intake_write_authorized, reason,
                           created_at, effective_at, expires_at
                    from public.{TABLE}
                    order by effective_at desc, created_at desc,
                             control_event_id desc
                    limit 1
                    """
                )
                row = cursor.fetchone()
        if not row:
            return _result("level1_control_not_configured", event={}), 200
        event = {
            "control_event_id": row[0],
            "prior_event_id": row[1] or "",
            "state": row[2],
            "policy_version": row[3],
            "activation_cutoff_utc": _iso(row[4]),
            "carried_bindings": row[5] if isinstance(row[5], list) else [],
            "actor_id": row[6],
            "intake_write_authorized": row[7] is True,
            "reason": row[8],
            "created_at": _iso(row[9]),
            "effective_at": _iso(row[10]),
            "expires_at": _iso(row[11]),
        }
        error = _validate_event({
            **event,
            "contains_customer_content": False,
            "sends_customer_message": False,
            "mutates_business_state": False,
        })
        if error:
            return _result("level1_control_persisted_event_invalid", event={}), 503
        return _result("level1_control_loaded", event=event), 200
    except Exception as exc:
        return _result(
            "level1_control_storage_unavailable",
            event={},
            error_type=exc.__class__.__name__,
        ), 503


def resolve_level1_runtime_control(inbound, *, loaded=None, now=None):
    """Authorize only a current/new exact inbound under the latest safe state."""
    inbound = dict(inbound or {})
    loaded = dict(loaded or {})
    event = (
        dict(loaded.get("event") or {})
        if isinstance(loaded.get("event"), Mapping)
        else {}
    )
    now = _aware(now or datetime.now(timezone.utc))
    identity = {
        key: _text(inbound.get(key), 120)
        for key in ("account_id", "conversation_id", "contact_id", "inbox_id")
    }
    inbound_id = _text(
        inbound.get("message_id") or inbound.get("inbound_message_id"),
        120,
    )
    observed = _parse_time(inbound.get("latest_observed_at"))
    cutoff = _parse_time(event.get("activation_cutoff_utc"))
    effective = _parse_time(event.get("effective_at"))
    expires = _parse_time(event.get("expires_at"))
    binding = {
        "conversation_id": identity["conversation_id"],
        "inbound_message_id": inbound_id,
    }
    carried = binding in list(event.get("carried_bindings") or [])
    blockers = []
    if loaded.get("status") != "level1_control_loaded":
        blockers.append("isolated_control_unavailable")
    if event.get("policy_version") != POLICY_VERSION:
        blockers.append("policy_version_mismatch")
    if event.get("state") != "enabled":
        blockers.append("kill_switch_or_control_disabled")
    if not event.get("control_event_id"):
        blockers.append("control_event_identity_missing")
    if not inbound_id or not all(identity.values()):
        blockers.append("authoritative_identity_incomplete")
    if observed is None:
        blockers.append("canonical_observation_time_unavailable")
    if cutoff is None or effective is None or expires is None:
        blockers.append("control_time_evidence_invalid")
    elif not (effective <= now < expires):
        blockers.append("control_not_current")
    if observed is not None and cutoff is not None and observed < cutoff and not carried:
        blockers.append("historical_event_not_authorized")
    return {
        "version": CONTROL_VERSION,
        "allowed": not blockers,
        "blockers": blockers,
        "control_event_id": event.get("control_event_id", ""),
        "new_event": bool(
            observed is not None and cutoff is not None and observed >= cutoff
        ),
        "carried_followup": carried,
        "legacy_fallback_permitted": (
            loaded.get("status") == "level1_control_not_configured"
        ),
        "intake_write_authorized": bool(
            not blockers and event.get("intake_write_authorized") is True
        ),
        "contains_identity_values": False,
        "automatic_retry_authorized": False,
        "protected_actions_authorized": False,
    }


def _validated_bindings(values):
    values = list(values or [])
    if len(values) > MAX_CARRIED_BINDINGS:
        raise ValueError("level1_control_carried_bindings_exceed_bound")
    bindings = []
    for item in values:
        if not isinstance(item, Mapping):
            raise ValueError("level1_control_binding_invalid")
        binding = {
            "conversation_id": _text(item.get("conversation_id"), 120),
            "inbound_message_id": _text(item.get("inbound_message_id"), 120),
        }
        if not all(binding.values()):
            raise ValueError("level1_control_binding_invalid")
        bindings.append(binding)
    if len({tuple(item.values()) for item in bindings}) != len(bindings):
        raise ValueError("level1_control_binding_duplicate")
    return sorted(bindings, key=lambda item: tuple(item.values()))


def _validate_event(row):
    required = (
        "control_event_id",
        "state",
        "policy_version",
        "actor_id",
        "reason",
        "activation_cutoff_utc",
        "created_at",
        "effective_at",
        "expires_at",
    )
    if any(not _text(row.get(key), 500) for key in required):
        return "level1_control_event_incomplete"
    if row.get("state") not in ALLOWED_STATES:
        return "level1_control_state_invalid"
    if row.get("policy_version") != POLICY_VERSION:
        return "level1_control_policy_version_invalid"
    if not isinstance(row.get("intake_write_authorized"), bool):
        return "level1_control_intake_authority_invalid"
    if not str(row.get("actor_id")).startswith("owner-admin:"):
        return "server_derived_owner_admin_required"
    try:
        _validated_bindings(row.get("carried_bindings") or [])
    except ValueError as exc:
        return str(exc)
    created = _parse_time(row.get("created_at"))
    effective = _parse_time(row.get("effective_at"))
    expires = _parse_time(row.get("expires_at"))
    cutoff = _parse_time(row.get("activation_cutoff_utc"))
    if not all((created, effective, expires, cutoff)):
        return "level1_control_time_evidence_invalid"
    if effective < created - timedelta(minutes=5) or expires <= effective:
        return "level1_control_time_order_invalid"
    if any(
        row.get(key) is not False
        for key in (
            "contains_customer_content",
            "sends_customer_message",
            "mutates_business_state",
        )
    ):
        return "level1_control_authority_scope_invalid"
    return ""


def _parse_time(value):
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("timezone_aware_datetime_required")
    return value.astimezone(timezone.utc)


def _iso(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        return ""
    return value.astimezone(timezone.utc).isoformat()


def _text(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _result(status, **extra):
    return {
        "success": status in {
            "level1_control_loaded",
            "level1_control_not_configured",
            "level1_control_event_recorded",
            "level1_control_replay_withheld",
        },
        "status": status,
        **extra,
        "contains_customer_content": False,
        "sends_customer_message": False,
        "mutates_business_state": False,
    }
