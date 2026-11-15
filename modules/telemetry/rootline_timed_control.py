"""Scheduled-stop policy for ROOTLINE's existing execution rail.

The rollout switch is configured once at deployment. Per-device authority flags
still select which schedules ROOTLINE owns; an existing stop duty survives a
later disabled flag. Controller inching is optional telemetry, not stop proof.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os

STOP_MODE = "scheduled"
MAX_IRRIGATION_SECONDS = 2 * 60 * 60
TIMED_JOB_VERSION = "rootline_irrigation_job.v2"
TIMED_ELIGIBILITY_VERSION = "rootline_execution_eligibility.v6"
_policy = ContextVar("rootline_timed_control", default=None)


def timed_control_enabled(environ=None):
    if environ is None and _policy.get() is not None:
        return _policy.get()
    source = os.environ if environ is None else environ
    return str(source.get("ROOTLINE_TIMED_CONTROL_ENABLED") or "").lower() == "true"


@contextmanager
def timed_control_scope(environ):
    token = _policy.set(timed_control_enabled(environ))
    try:
        yield
    finally:
        _policy.reset(token)


def scheduled_execution(value):
    return isinstance(value, dict) and value.get("stop_mode") == STOP_MODE


def timed_snapshot_safe(snapshot, *, device_id, channel, now=None):
    from datetime import datetime, timezone, timedelta
    if not isinstance(snapshot, dict):
        return False
    rows = [row for row in snapshot.get("channels") or [] if isinstance(row, dict) and row.get("channel") == channel]
    try:
        observed = datetime.fromisoformat(str(snapshot.get("trusted_receipt_at") or snapshot.get("retrieved_at")).replace("Z", "+00:00"))
        current = now or datetime.now(timezone.utc)
        fresh = observed.tzinfo is not None and timedelta(0) <= current-observed <= timedelta(minutes=5)
    except (ValueError, TypeError):
        return False
    if device_id == "100204e9bc":
        # Keep irrigation sequential across owned and external schedules. Only
        # current output states matter; sibling inching/settings are optional.
        outputs = snapshot.get("channels") or []
        if (len(outputs) != 4 or {row.get("channel") for row in outputs} != {1, 2, 3, 4}
                or any(row.get("output_state") != "OFF" for row in outputs)):
            return False
    return (snapshot.get("device_id") == device_id and snapshot.get("online") is True
        and snapshot.get("current_outputs_authoritative") is True and fresh
        and bool(snapshot.get("response_digest")) and len(rows) == 1
        and rows[0].get("output_state") == "OFF")


def timed_control_call(function):
    from functools import wraps
    @wraps(function)
    def wrapped(*args, **kwargs):
        with timed_control_scope(kwargs.get("environ")):
            return function(*args, **kwargs)
    return wrapped


def canonical_timed_authority(loaded, *, connect_factory, identity, requested_seconds):
    """Check live policy scope in addition to the spine's resolved record evidence."""
    from modules.telemetry.rootline_device_registry import get_device_contract
    from modules.telemetry.rootline_device_spine import scheduled_device_profile
    output = get_device_contract(identity)
    record = (loaded or {}).get("device_record") or {}
    if (not output or not scheduled_device_profile(record)
            or record.get("standing_authority") is not True
            or record.get("commissioning_stage") != "standing_active"
            or record.get("device_id") != output["device_id"]
            or record.get("channel") != output["channel"]
            or type(requested_seconds) is not int
            or not 0 < requested_seconds <= record["maximum_runtime_seconds"]):
        return False
    key = f"{output['provider']}:{output['provider_account_binding']}:{output['device_id']}:{output['channel']}"
    if loaded.get("device_key") != key:
        return False
    envelope = record.get("authority_envelope") or {}
    with connect_factory() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select issuer,policy_payload,policy_sha256,active,revoked,
                not exists(select 1 from app_private.rootline_authority_events e where
                  e.standing_authority_id=%s and e.version=%s and e.event_type in ('revoked','superseded'))
                from app_private.rootline_standing_authorities where standing_authority_id=%s and version=%s""",
                (envelope.get("standing_authority_id"), envelope.get("version"),
                 envelope.get("standing_authority_id"), envelope.get("version")))
            row = cursor.fetchone()
    if (not row or str(row[0]) != str(envelope.get("issuer") or "")
            or row[3] is not True or row[4] is True or row[5] is not True
            or row[2] != envelope.get("policy_sha256")):
        return False
    policy = row[1] if isinstance(row[1], dict) else {}
    from hashlib import sha256
    import json
    if sha256(json.dumps(policy, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest() != row[2]:
        return False
    scoped = (identity in (policy.get("zone_ids") or []) if output["collection"] == "irrigation_zones"
        else identity in (policy.get("device_identities") or []))
    return (policy.get("contract_version") == "rootline_timed_standing_authority.v1"
        and policy.get("stop_mode") == STOP_MODE and key in (policy.get("device_keys") or [])
        and scoped and output["channel"] in (policy.get("allowed_channels") or [])
        and policy.get("device_id") == output["device_id"]
        and policy.get("provider") == output["provider"]
        and policy.get("provider_account_binding") == output["provider_account_binding"]
        and type(policy.get("maximum_runtime_seconds")) is int
        and requested_seconds <= policy["maximum_runtime_seconds"] <= record["maximum_runtime_seconds"]
        and policy.get("application_timeout_required") is True
        and policy.get("automatic_on_retry") is False)
