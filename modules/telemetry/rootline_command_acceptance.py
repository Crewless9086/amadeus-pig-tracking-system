"""Owner-approved command acceptance on ROOTLINE's existing execution rail.

These proofs describe commands and route identity, never observed relay state.
No scheduler, storage, device registry or provider client lives here.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os

MODE = "command_accepted"
ROUTE = "rootline_home_assistant_command_route.v1"
RECEIPT = "rootline_home_assistant_command_receipt.v1"
_policy = ContextVar("rootline_command_acceptance", default=None)


def enabled(environ=None):
    if environ is None and _policy.get() is not None:
        return _policy.get()
    source = os.environ if environ is None else environ
    return (source.get("ROOTLINE_SONOFF_TRANSPORT") == "home_assistant"
        and source.get("ROOTLINE_HOME_ASSISTANT_ACCEPTANCE_MODE") == MODE)


@contextmanager
def scope(environ):
    token = _policy.set(enabled(environ))
    try:
        yield
    finally:
        _policy.reset(token)


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def moment(value):
    try:
        at = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return at if at.tzinfo is not None and at.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def route_valid(value, *, device_id, channel, now=None):
    route = value.get("command_route", value) if isinstance(value, dict) else {}
    now = now or datetime.now(timezone.utc)
    checked = moment(route.get("route_checked_at"))
    channels = route.get("channels") or []
    expected = {1} if device_id == "1002851416" else {1, 2, 3, 4}
    return (route.get("contract_version") == ROUTE and route.get("device_id") == device_id
        and device_id in {"1002851416", "100204e9bc", "100204d497"}
        and type(channel) is int and channel in expected
        and route.get("acceptance_mode") == MODE and route.get("command_route_ready") is True
        and route.get("current_outputs_authoritative") is False
        and checked is not None and timedelta(0) <= now-checked <= timedelta(minutes=5)
        and isinstance(channels, list) and len(channels) == len(expected)
        and all(isinstance(row, dict) and type(row.get("channel")) is int
                and row.get("output_state") == "Unknown" and row.get("entity_id") for row in channels)
        and {row["channel"] for row in channels} == expected
        and route.get("response_digest") == digest({k:v for k,v in route.items() if k != "response_digest"}))


def command_execution(value):
    return (isinstance(value, dict) and value.get("acceptance_mode") == MODE
        and value.get("device_id") in {"1002851416", "100204e9bc", "100204d497"}
        and type(value.get("channel")) is int
        and value["channel"] in ({1} if value["device_id"] == "1002851416" else {1,2,3,4})
        and bool(value.get("execution_id")))


def accepted(receipt, execution, state):
    if not isinstance(receipt, dict) or not isinstance(execution, dict):
        return False
    identity = str(execution.get("execution_id") or "")
    key = receipt.get("idempotency_key")
    at = moment(receipt.get("accepted_at"))
    attempted = moment(receipt.get("command_attempted_at"))
    claimed = moment(execution.get("claimed_at"))
    return (bool(identity) and receipt.get("contract_version") == RECEIPT
        and receipt.get("provider") == "home_assistant"
        and receipt.get("accepted_unambiguous") is True
        and receipt.get("provider_command_attempted") is True
        and receipt.get("requested_state") == state
        and receipt.get("device_id") == execution.get("device_id")
        and type(receipt.get("channel")) is int and receipt["channel"] == execution.get("channel")
        and (key == identity+":ON" if state == "ON" else key in {identity+":OFF:"+str(n) for n in range(1,4)})
        and attempted is not None and at is not None and claimed is not None
        and claimed <= attempted <= at
        and bool(receipt.get("entity_id"))
        and receipt.get("receipt_sha256") == digest({k:v for k,v in receipt.items() if k != "receipt_sha256"}))


def duty_closed(value):
    return (command_execution(value) and value.get("command_duty_closed") is True
        and value.get("shutdown_verified") is False
        and accepted(value.get("command_off_receipt"), value, "OFF"))


def active_command(value, *, now=None):
    if not command_execution(value) or value.get("state") != "Active":
        return False
    from modules.telemetry.rootline_camp_confirmation import camp_command, confirmed
    if camp_command(value) and (not confirmed(value)
            or moment(value["controller_confirmation"]["confirmed_at"]) > (now or datetime.now(timezone.utc))):
        return False
    adopted = (value.get("execution_origin") == "ha_reported_external_on"
        and value.get("device_id") == "1002851416" and value.get("channel") == 1
        and value.get("stop_mode") == "conditions" and value.get("on_attempts") == 0
        and value.get("command_on_receipt") is None
        and value.get("original_start_at") is None and value.get("provider_start_evidence") is None
        and moment(value.get("claimed_at")) is not None
        and route_valid(value.get("command_adoption_evidence"), device_id="1002851416", channel=1,
            now=moment(value["claimed_at"]))
        and ((value.get("command_adoption_evidence") or {}).get("command_route") or value.get("command_adoption_evidence") or {}).get("reported_output_state") == "ON")
    if not adopted and (value.get("on_attempts") != 1
            or not accepted(value.get("command_on_receipt"), value, "ON")):
        return False
    deadline = command_stop_deadline(value)
    return value.get("stop_mode") == "conditions" or (deadline is not None and (now or datetime.now(timezone.utc)) < deadline)


def command_seconds(value):
    if not duty_closed(value) or not accepted(value.get("command_on_receipt"), value, "ON"):
        return 0
    from modules.telemetry.rootline_camp_confirmation import camp_command, confirmed
    if camp_command(value) and (not confirmed(value) or value.get("controller_contradiction")):
        return 0
    start = moment(value["command_on_receipt"]["accepted_at"])
    stop = moment(value["command_off_receipt"]["accepted_at"])
    limit = value.get("planned_runtime_seconds", value.get("maximum_duration_seconds"))
    if type(limit) is not int or limit <= 0 or stop < start:
        return 0
    return min(limit, max(0, int((stop-start).total_seconds())))


def terminal(execution, off, *, now=None, reason=None):
    if not command_execution(execution) or not accepted(off, execution, "OFF"):
        raise ValueError("command_off_acceptance_missing")
    value = {**execution, "state": "Completed", "completed_at": (now or datetime.now(timezone.utc)).isoformat(),
        "command_off_receipt": off, "command_duty_closed": True, "shutdown_verified": False,
        "physical_state": "Unverified", "completion_scope": "accepted_commands",
        "objective_satisfied": False, "verified_runtime_seconds": 0,
        "physical_outcome_verified": False, "delivered_volume": "Unavailable"}
    if reason:
        value["reason"] = reason
    from modules.telemetry.rootline_camp_confirmation import camp_command
    if camp_command(value):
        value["controller_confirmation_required"] = True
    value["commanded_runtime_seconds"] = command_seconds(value)
    return value


def terminal_matches_rows(value, rows):
    """Require this receipt to exist on the same canonical claimed duty."""
    if not duty_closed(value):
        return False
    identity = value["execution_id"]
    if value.get("injector_target") is not None and not injector_target_matches_rows(value, rows):
        return False
    rows = [row for row in rows if isinstance(row, dict) and row.get("execution_id") == identity]
    claims = [row for row in rows if row.get("action") in {
        "claim_before_on", "claim_auxiliary_before_on", "claim_borehole_before_on", "mark_borehole_active", "adopt_borehole_observed_on"}]
    if any(row.get("injector_timing_contract") is not None
            and row["injector_timing_contract"] != value.get("injector_timing_contract") for row in claims):
        return False  # A new target claim cannot be relabelled as a legacy pulse.
    immutable = ("device_id", "channel", "claimed_at", "primary_stop_deadline", "job_id", "job_sha256",
        "segment_identity", "zone_id", "auxiliary_device_id")
    if not any(all(row.get(key) == value.get(key) for key in immutable) for row in claims):
        return False
    if not any(row.get("action") in {"record_off_outcome", "record_auxiliary_off_outcome", "record_borehole_off_outcome"}
        and row.get("outcome") == value["command_off_receipt"] for row in rows):
        return False
    on = value.get("command_on_receipt")
    return on is None or (accepted(on, value, "ON") and any(row.get("action") in {
        "record_on_outcome", "record_auxiliary_on_outcome", "record_borehole_on_outcome"}
        and row.get("on_outcome") == on for row in rows))


def active_irrigation_duty(rows, *, now):
    """Read-only proof of one current, canonically recorded ON command duty.

    A mode flag is not a receipt. Sparse notification rows may omit context,
    but no supplied conflicting claim, command or deadline may be repaired by
    borrowing fields from another row. This grants no physical-state proof.
    """
    from modules.telemetry.rootline_device_registry import commissioned_irrigation_contract, IRRIGATION_ZONE_IDS
    rows = [row for row in rows if isinstance(row, dict)]
    if (not rows or any(not isinstance(row.get("execution_id"), str) for row in rows)
            or len({row.get("execution_id") for row in rows}) != 1):
        return None
    candidates = [row for row in rows if row.get("action") == "mark_active"]
    if not candidates:
        return None
    active = candidates[-1]
    if (active.get("zone_id") not in IRRIGATION_ZONE_IDS or active.get("stop_mode") != "scheduled"
            or not active_command(active, now=now)):
        return None
    try:
        binding = commissioned_irrigation_contract(active["zone_id"])
    except ValueError:
        return None
    if (active.get("device_id") != binding["device_id"]
            or active.get("channel") != binding["channel"]):
        return None
    primary = moment(active.get("primary_stop_deadline"))
    claimed = moment(active.get("claimed_at"))
    on = active.get("command_on_receipt")
    accepted_at = moment((on or {}).get("accepted_at"))
    duration = active.get("planned_runtime_seconds")
    if (primary is None or claimed is None or accepted_at is None
            or not claimed <= accepted_at <= now < primary
            or type(duration) is not int or duration <= 0
            or primary != claimed + timedelta(seconds=duration)):
        return None
    immutable = ("zone_id", "device_id", "channel", "claimed_at", "primary_stop_deadline",
        "acceptance_mode", "job_id", "job_sha256", "segment_identity", "stop_mode",
        "planned_runtime_seconds")
    if not any(row.get("action") == "claim_before_on"
            and all(row.get(key) == active.get(key) for key in immutable) for row in rows):
        return None
    if not any(row.get("action") == "record_on_outcome" and row.get("on_outcome") == on
            for row in rows):
        return None
    for row in rows:
        if any(row.get(key) is not None and row[key] != active.get(key) for key in immutable):
            return None
        if row.get("command_on_receipt") is not None and row["command_on_receipt"] != on:
            return None
        if row.get("action") == "record_on_outcome" and row.get("on_outcome") != on:
            return None
        native = row.get("native_fail_stop_deadline")
        if native is not None and (moment(native) is None or moment(native) < primary):
            return None
        if (row.get("action") in {"mark_stopping", "contain_zone", "record_completed",
                "record_claim_recovery", "record_ambiguous_shutdown", "claim_off_attempt", "record_off_outcome"}
                or str(row.get("state") or "").casefold() in {
                    "failed", "ambiguous", "contained", "stopping", "completed", "claimed_recovery_required"}
                or row.get("command_off_receipt") is not None):
            return None
    natives = {row["native_fail_stop_deadline"] for row in rows if row.get("native_fail_stop_deadline") is not None}
    return active if len(natives) <= 1 else None


def irrigation_context(active, auxiliary, *, fertilizer_needed, batch_generation, now):
    """Project canonical accepted-command timing without relay/flow assertions."""
    if not active_command(active, now=now) or active.get("zone_id") not in {"A12345", "B12345", "C12345", "E12345"}:
        return None
    from modules.telemetry.rootline_device_registry import commissioned_irrigation_contract
    from modules.telemetry.rootline_irrigation_lifecycle import auxiliary_shutdown_unverified
    binding = commissioned_irrigation_contract(active["zone_id"])
    if active.get("device_id") != binding["device_id"] or active.get("channel") != binding["channel"]:
        return None
    identity = active["execution_id"]
    pulses = {row.get("execution_id"): row for row in auxiliary
        if row.get("action") == "record_auxiliary_completed"
        and row.get("auxiliary_device_id") == "FERTILIZER-INJECTION-CH1"
        and row.get("zone_execution_id") == identity
        and all(row.get(key) == active.get(key) for key in ("job_id", "job_sha256", "segment_identity"))
        and program_completed(row) and terminal_matches_rows(row, auxiliary)}
    pulses = sorted(pulses.values(), key=lambda row: int(row.get("pulse_number") or 0))
    start = {"observed_at": active["command_on_receipt"]["accepted_at"],
        "zone_execution_id": identity, "command_acceptance": True, "authoritative": False}
    prior = pulses[-1] if pulses else None
    return {"acceptance_mode": MODE, "command_parent_execution": active,
        "plan_generation": str(active.get("evidence_generation") or ""),
        "stop_mode": active.get("stop_mode"), "planned_runtime_seconds": active.get("planned_runtime_seconds"),
        "batch_generation": str(batch_generation or ""), "fertilizer_needed": fertilizer_needed is True,
        **{key: active.get(key) for key in ("job_id", "job_sha256", "segment_identity")},
        "active_zone_ids": [active["zone_id"]], "zone_execution_id": identity,
        "zone_device_id": binding["device_id"], "zone_channel": binding["channel"],
        "zone_start_evidence": start, "zone_output_evidence": {},
        "irrigation_stop_deadline": active.get("primary_stop_deadline"),
        "completed_pulses": len(pulses), "completed_pulse_numbers": [int(row.get("pulse_number") or 0) for row in pulses],
        "prior_pulse_shutdown_evidence": ({"observed_at": prior["command_off_receipt"]["accepted_at"],
            "zone_execution_id": identity, "command_execution": prior, "shutdown_verified": False} if prior else None),
        "mixer_active": False, "prior_shutdown_unverified": auxiliary_shutdown_unverified(
            auxiliary, evidence_cutoff=now)}


def command_parent_ready(context, *, now, require_route=True):
    parent = context.get("command_parent_execution") or {}
    if not enabled() or context.get("acceptance_mode") != MODE or not active_command(parent, now=now):
        return False
    if not all(context.get(key) == parent.get(key) for key in ("job_id", "job_sha256", "segment_identity")):
        return False
    if (context.get("zone_execution_id") != parent.get("execution_id")
            or context.get("zone_device_id") != parent.get("device_id")
            or context.get("zone_channel") != parent.get("channel")
            or context.get("active_zone_ids") != [parent.get("zone_id")]):
        return False
    return not require_route or route_valid(context.get("zone_output_evidence"),
        device_id=parent["device_id"], channel=parent["channel"], now=now)


def prior_pulse_closed(context):
    prior = context.get("prior_pulse_shutdown_evidence") or {}
    execution = prior.get("command_execution") or {}
    return (duty_closed(execution) and execution.get("zone_execution_id") == context.get("zone_execution_id")
        and all(execution.get(key) == context.get(key) for key in ("job_id", "job_sha256", "segment_identity"))
        and prior.get("observed_at") == execution["command_off_receipt"]["accepted_at"])


INJECTOR_TARGET_V1 = "rootline_injector_accepted_on_target.v1"
INJECTOR_TARGET_V2 = "rootline_injector_accepted_on_target.v2"
_INJECTOR_CLAIM_FIELDS = ("execution_id", "eligibility_id", "eligibility_sha256", "consumption_key",
    "auxiliary_device_id", "device_type", "device_id", "channel", "zone_id", "job_id", "job_sha256",
    "segment_identity", "zone_execution_id", "pulse_number", "phase_number", "batch_generation",
    "maximum_duration_seconds", "claimed_at", "primary_stop_deadline", "stop_mode", "acceptance_mode",
    "injector_timing_contract")


def injector_target_claim(value):
    """Future claims opt into the owner's target policy; old claims never do."""
    claimed = moment(value.get("claimed_at")); provisional = moment(value.get("primary_stop_deadline"))
    version = value.get("injector_timing_contract")
    seconds = 120
    if version == INJECTOR_TARGET_V2:
        from modules.telemetry.rootline_owner_auxiliary_policy import valid_injection_policy
        policy = value.get("injection_policy")
        if not valid_injection_policy(policy) or value.get("zone_id") not in policy["zone_ids"]:
            return False
        seconds = policy["pulse_seconds"]
        pulse = value.get("pulse_number")
        if type(pulse) is not int or not 1 <= pulse <= policy["pulses_per_60_minutes"] * 2 or value.get("phase_number") != (pulse - 1) // policy["pulses_per_60_minutes"] + 1:
            return False
    elif version != INJECTOR_TARGET_V1 or value.get("injection_policy") is not None:
        return False
    return (command_execution(value)
        and value.get("auxiliary_device_id") == "FERTILIZER-INJECTION-CH1"
        and value.get("device_type") == "fertilizer_injection_valve"
        and value.get("device_id") == "100204d497" and type(value.get("channel")) is int
        and value["channel"] == 1 and value.get("stop_mode") == "scheduled"
        and type(value.get("maximum_duration_seconds")) is int and value["maximum_duration_seconds"] == seconds
        and claimed is not None and provisional == claimed + timedelta(seconds=seconds)
        and all(isinstance(value.get(key), str) and value[key] for key in (
            "zone_execution_id", "job_id", "job_sha256", "segment_identity", "consumption_key")))


def injector_claim_digest(value):
    material = {key: value.get(key) for key in _INJECTOR_CLAIM_FIELDS}
    if value.get("injector_timing_contract") == INJECTOR_TARGET_V2:
        material["injection_policy"] = value.get("injection_policy")
    return digest(material)


def injector_target_binding(value):
    """Validate derived timing without turning a receipt into physical proof.

    Canonical consumers must additionally use injector_target_matches_rows;
    this structural check cannot establish that activation was committed.
    """
    target = value.get("injector_target")
    if not injector_target_claim(value) or not isinstance(target, dict):
        return None
    on = value.get("command_on_receipt")
    if not accepted(on, value, "ON"):
        return None
    claim = moment(value["claimed_at"]); provisional = moment(value["primary_stop_deadline"])
    attempted = moment(on["command_attempted_at"]); anchor = moment(on["accepted_at"])
    activated = moment(target.get("activated_at")); stop = moment(target.get("target_off_at"))
    parent_stop = moment(target.get("parent_stop_deadline"))
    if (target.get("contract_version") != value.get("injector_timing_contract")
            or target.get("claim_sha256") != injector_claim_digest(value)
            or target.get("execution_id") != value["execution_id"]
            or target.get("on_receipt_sha256") != on["receipt_sha256"]
            or target.get("accepted_on_at") != on["accepted_at"]
            or target.get("provisional_stop_deadline") != value["primary_stop_deadline"]
            or type(target.get("target_seconds")) is not int or target["target_seconds"] != value["maximum_duration_seconds"]
            or not timedelta(0) <= attempted-claim <= timedelta(seconds=30)
            or activated is None or not attempted <= anchor <= activated < provisional
            or stop != anchor + timedelta(seconds=value["maximum_duration_seconds"])
            or target.get("parent_execution_id") != value["zone_execution_id"]
            or parent_stop is None or parent_stop < stop + timedelta(seconds=600)
            or not isinstance(target.get("parent_on_receipt_sha256"), str)
            or len(target["parent_on_receipt_sha256"]) != 64
            or target.get("binding_sha256") != digest({k:v for k,v in target.items() if k != "binding_sha256"})):
        return None
    return target


def build_injector_target_active(claim, receipt, parent, *, now):
    """Derive once inside the existing locked canonical activation transition."""
    if (not injector_target_claim(claim) or not accepted(receipt, claim, "ON")
            or moment(now) is None or not active_command(parent, now=now)
            or parent.get("execution_id") != claim.get("zone_execution_id")
            or not all(parent.get(key) == claim.get(key) for key in (
                "job_id", "job_sha256", "segment_identity", "zone_id"))):
        raise ValueError("injector_target_activation_unproven")
    target = {"contract_version": claim["injector_timing_contract"], "execution_id": claim["execution_id"],
        "claim_sha256": injector_claim_digest(claim), "on_receipt_sha256": receipt["receipt_sha256"],
        "provisional_stop_deadline": claim["primary_stop_deadline"],
        "accepted_on_at": receipt["accepted_at"], "target_seconds": claim["maximum_duration_seconds"],
        "target_off_at": (moment(receipt["accepted_at"])+timedelta(seconds=claim["maximum_duration_seconds"])).isoformat(),
        "activated_at": now.isoformat(), "parent_execution_id": parent["execution_id"],
        "parent_stop_deadline": parent["primary_stop_deadline"],
        "parent_on_receipt_sha256": parent["command_on_receipt"]["receipt_sha256"]}
    target["binding_sha256"] = digest(target)
    active = {**claim, "state": "Active", "on_attempts": 1,
        "command_on_receipt": receipt, "physical_state": "Unverified", "injector_target": target}
    if injector_target_binding(active) is None:
        raise ValueError("injector_target_activation_expired_or_invalid")
    return active


def injector_target_matches_rows(value, rows):
    """A target is authority only through its immutable canonical activation."""
    target = injector_target_binding(value)
    if target is None:
        return False
    rows = [r for r in rows if isinstance(r, dict) and r.get("execution_id") == value.get("execution_id")]
    claims = [r for r in rows if r.get("action") == "claim_auxiliary_before_on"]
    activations = [r for r in rows if r.get("action") == "mark_auxiliary_active"]
    dispatches = [r for r in rows if r.get("action") == "claim_auxiliary_dispatch"]
    if (len(claims) != 1 or len(activations) != 1 or len(dispatches) != 1
            or any(injector_claim_digest(r) != target["claim_sha256"] for r in claims+activations+dispatches)
            or injector_target_binding(activations[0]) != target
            or activations[0].get("state") != "Active"
            or activations[0].get("command_on_receipt") != value.get("command_on_receipt")):
        return False
    outcomes = [r for r in rows if r.get("action") == "record_auxiliary_on_outcome"]
    if not outcomes or any(r.get("on_outcome") != value["command_on_receipt"] for r in outcomes):
        return False
    # A consumed OFF slot, isolation/containment or recovery precedes activation
    # only on an invalid/replayed history; it cannot acquire a new target.
    activated = rows.index(activations[0])
    if any(r.get("action") in {"claim_auxiliary_off_attempt", "record_auxiliary_off_outcome",
            "contain_auxiliary_device", "record_auxiliary_completed", "record_auxiliary_control_pulse_stopped",
            "record_auxiliary_startup_aborted", "record_execution_not_dispatched"}
            or r.get("manual_isolation_active") is True or r.get("manual_off_active") is True
            for r in rows[:activated]):
        return False
    return (rows.index(claims[0]) < rows.index(dispatches[0]) < activated
        and all(rows.index(dispatches[0]) < rows.index(r) < activated for r in outcomes))


def command_stop_deadline(value):
    """Use only an activated future target; retain every provisional/old duty."""
    target = injector_target_binding(value) if value.get("state") == "Active" else None
    return moment(target["target_off_at"] if target else value.get("primary_stop_deadline"))


def injector_target_timing(value, off=None):
    target = injector_target_binding(value)
    if target is None:
        return None
    on = value["command_on_receipt"]
    result = {"target_seconds": target["target_seconds"], "accepted_on_at": on["accepted_at"],
        "on_attempted_at": on["command_attempted_at"], "target_off_at": target["target_off_at"],
        "on_delivery_delay_seconds": (moment(on["accepted_at"])-moment(on["command_attempted_at"])).total_seconds(),
        "physical_runtime_verified": False, "physical_runtime_seconds": None}
    off = off or value.get("command_off_receipt")
    if accepted(off, value, "OFF"):
        at = moment(target["target_off_at"]); attempted = moment(off["command_attempted_at"]); accepted_at = moment(off["accepted_at"])
        result.update(off_attempted_at=off["command_attempted_at"], off_accepted_at=off["accepted_at"],
            off_request_offset_seconds=(attempted-at).total_seconds(),
            off_acceptance_offset_seconds=(accepted_at-at).total_seconds(),
            off_request_delay_seconds=max(0.0, (attempted-at).total_seconds()),
            off_acceptance_delay_seconds=max(0.0, (accepted_at-at).total_seconds()),
            off_delivery_delay_seconds=(accepted_at-attempted).total_seconds(),
            accepted_command_interval_seconds=(accepted_at-moment(on["accepted_at"])).total_seconds(),
            interrupted_before_target=attempted < at)
    return result


def program_completed(value):
    from modules.telemetry.rootline_camp_confirmation import camp_command, confirmed
    if camp_command(value) and (not confirmed(value) or value.get("controller_contradiction")):
        return False
    if not duty_closed(value) or not accepted(value.get("command_on_receipt"), value, "ON"):
        return False
    if value.get("injector_timing_contract") is not None:
        target = injector_target_binding(value)
        return (target is not None and value.get("command_program_completed") is True
            and value.get("reason") == "primary_deadline_reached"
            and moment(value["command_off_receipt"]["command_attempted_at"]) >= moment(target["target_off_at"]))
    seconds = value.get("planned_runtime_seconds", value.get("maximum_duration_seconds"))
    claimed = moment(value.get("claimed_at")); deadline = moment(value.get("primary_stop_deadline"))
    off = moment(value["command_off_receipt"]["accepted_at"])
    return (type(seconds) is int and 0 < seconds <= 7200 and claimed is not None
        and deadline == claimed + timedelta(seconds=seconds) and off >= deadline
        and value.get("reason") == "primary_deadline_reached"
        and value.get("command_program_completed") is True)


def job_completed(value):
    return (program_completed(value) and value.get("stop_mode") == "scheduled"
        and value.get("command_job_completed") is True
        and value.get("expected_segment_count") == value.get("segment_number") == 1
        and value.get("governed_executable_duration_seconds") == value.get("planned_runtime_seconds"))
