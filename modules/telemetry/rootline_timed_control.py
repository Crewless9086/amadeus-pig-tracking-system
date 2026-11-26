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
    from modules.telemetry.rootline_command_acceptance import scope
    try:
        with scope(environ):
            yield
    finally:
        _policy.reset(token)


def scheduled_execution(value):
    return isinstance(value, dict) and value.get("stop_mode") == STOP_MODE


def timed_snapshot_safe(snapshot, *, device_id, channel, now=None):
    from datetime import datetime, timezone, timedelta
    if not isinstance(snapshot, dict):
        return False
    from modules.telemetry.rootline_command_acceptance import enabled, route_valid
    if enabled() and route_valid(snapshot, device_id=device_id, channel=channel, now=now):
        return True
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


def canonical_timed_authority(loaded, *, connect_factory, identity, requested_seconds, execution=None):
    """Check live policy scope in addition to the spine's resolved record evidence."""
    from modules.telemetry.rootline_device_registry import get_device_contract
    from modules.telemetry.rootline_device_spine import scheduled_device_profile
    output = get_device_contract(identity)
    record = (loaded or {}).get("device_record") or {}
    extension = (identity == "FERTILIZER-INJECTION-CH1"
        and type(requested_seconds) is int and 120 < requested_seconds <= 600)
    # The standing registry remains the original120-second identity/profile.
    # Only a fresh authenticated owner programme can extend a future claim.
    checked_seconds = 120 if extension else requested_seconds
    if extension and not _owner_injector_extension_shape(execution, requested_seconds):
        return False

    if (not output or not scheduled_device_profile(record)
            or record.get("standing_authority") is not True
            or record.get("commissioning_stage") != "standing_active"
            or record.get("device_id") != output["device_id"]
            or record.get("channel") != output["channel"]
            or type(requested_seconds) is not int
            or not 0 < checked_seconds <= record["maximum_runtime_seconds"]):
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
        base_valid = (policy.get("contract_version") == "rootline_timed_standing_authority.v1"
            and policy.get("stop_mode") == STOP_MODE and key in (policy.get("device_keys") or [])
            and scoped and output["channel"] in (policy.get("allowed_channels") or [])
            and policy.get("device_id") == output["device_id"]
            and policy.get("provider") == output["provider"]
            and policy.get("provider_account_binding") == output["provider_account_binding"]
            and type(policy.get("maximum_runtime_seconds")) is int
            and checked_seconds <= policy["maximum_runtime_seconds"] <= record["maximum_runtime_seconds"]
            and policy.get("application_timeout_required") is True
            and policy.get("automatic_on_retry") is False)

        if not base_valid or not extension:
            return base_valid
        if record["maximum_runtime_seconds"] != 120 or policy["maximum_runtime_seconds"] != 120:
            return False
        return _fresh_owner_injector_extension(connection, execution, requested_seconds)


OWNER_INJECTOR_EXTENSION_V1 = "rootline_authenticated_owner_injector_extension.v1"


def _owner_injector_extension_shape(execution, requested_seconds):
    from modules.telemetry.rootline_owner_auxiliary_policy import valid_injection_policy
    from modules.telemetry.rootline_command_acceptance import MODE, INJECTOR_TARGET_V2
    value = execution if isinstance(execution, dict) else {}
    selected = value.get("injection_policy")
    return (valid_injection_policy(selected)
        and value.get("acceptance_mode") == MODE and value.get("stop_mode") == STOP_MODE
        and value.get("injector_timing_contract") in (None, INJECTOR_TARGET_V2)
        and value.get("auxiliary_device_id") == "FERTILIZER-INJECTION-CH1"
        and value.get("device_id") == "100204d497" and type(value.get("channel")) is int
        and value["channel"] == 1 and value.get("zone_id") in selected["zone_ids"]
        and value.get("maximum_duration_seconds") == requested_seconds == selected["pulse_seconds"]
        and type(value.get("pulse_number")) is int and 1 <= value["pulse_number"] <= selected["pulses_per_60_minutes"]*2
        and value.get("phase_number") == (value["pulse_number"]-1)//selected["pulses_per_60_minutes"]+1)


def _fresh_owner_injector_extension(connection, execution, requested_seconds):
    from modules.telemetry.rootline_owner_controls import read_owner_controls, _now, pending_owner_request, owner_request_for_execution
    from modules.telemetry.rootline_owner_auxiliary_policy import owner_injection_policy
    if not _owner_injector_extension_shape(execution, requested_seconds):
        return False
    now = _now(connection)
    controls = read_owner_controls(connection, now=now)
    selected = owner_injection_policy(controls, now=now)
    if selected != execution["injection_policy"]:
        return False
    mode = controls["devices"]["injection"]["mode"]
    if mode == "automatic":
        return True
    request = (owner_request_for_execution(controls, "injection", execution.get("execution_id"), now)
        or pending_owner_request(controls, "injection", now, kind="run"))
    return mode == "manual_today" and request is not None and request["change"]["kind"] == "run"


def locked_owner_injector_authority(connection, execution):
    """Re-read registry, revocation and owner records inside the existing ON lock."""
    from contextlib import nullcontext
    from modules.telemetry.rootline_device_spine import load_device_record
    owned = getattr(connection, "connection", connection)
    factory = lambda: nullcontext(owned)
    key = "ifttt_ewelink:ewelink_owner_account:100204d497:1"
    loaded = load_device_record(key, connect_factory=factory)
    return canonical_timed_authority(loaded, connect_factory=factory,
        identity="FERTILIZER-INJECTION-CH1",
        requested_seconds=execution.get("maximum_duration_seconds"), execution=execution)
