"""Durable coordinator for the existing ROOTLINE execution contract.

Effects are supplied by the canonical persistence, provider and Oom Sakkie
adapters. The coordinator never guesses readback and never retries ON.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from modules.telemetry.rootline_irrigation_execution_contract import validate_commissioning

MAX_MINUTES = 60
MAX_OFF_ATTEMPTS = 3
ZONES = {"B12345": 1, "C12345": 2}


def advance_irrigation_execution(*, decision_id, commissioning_id,
                                 decision_reader, commissioning_reader, store, transport,
                                 notify, outcome_reader=lambda _identity: None,
                                 eligibility_revalidator=lambda _decision: None, now=None):
    now = _aware(now or datetime.now(timezone.utc))
    active = store("load_active", None)
    if active:
        return _recover_or_observe(active, store, transport, notify, outcome_reader, now)
    decision = decision_reader(decision_id)
    commissioning_packet = commissioning_reader(commissioning_id)
    commissioning = _canonical_commissioning(commissioning_packet, commissioning_id, now)
    if not _eligible(decision, decision_id, commissioning, now):
        return _result("not_eligible", commands=0, messages=0)
    contained = store("load_zone_containment", decision["zone_id"]) or {}
    if contained.get("contained") is True:
        return _result("zone_contained", commands=0, messages=0)
    safety = transport.read_safety_configuration(
        device_id="100204e9bc", channel=ZONES[decision["zone_id"]])
    if not _safe_configuration(safety, decision["zone_id"]):
        return _result("provider_safety_readback_unavailable", commands=0, messages=0,
                       autonomous_on_enabled=False)
    # This read-only edge check is intentionally after provider safety and
    # immediately before the durable claim. It prevents a fresh rain Hold or
    # evidence-generation change from racing a previously eligible decision.
    revalidated = eligibility_revalidator(decision)
    if (not isinstance(revalidated, dict) or revalidated.get("eligible") is not True
            or revalidated.get("observed_rain") is not False
            or revalidated.get("decision_id") != decision.get("decision_id")
            or revalidated.get("evidence_generation") != decision.get("evidence_generation")):
        return _result("execution_eligibility_changed", commands=0, messages=0)
    execution = {
        "execution_id": decision["execution_id"], "eligibility_id": decision["eligibility_id"],
        "evidence_generation": decision["evidence_generation"], "zone_id": decision["zone_id"],
        "channel": ZONES[decision["zone_id"]], "planned_runtime_minutes": decision["runtime_minutes"],
        "claimed_at": now.isoformat(),
        "primary_stop_deadline": (now + timedelta(minutes=decision["runtime_minutes"])).isoformat(),
        "native_fail_stop_deadline": (now + timedelta(minutes=60)).isoformat(),
        "commissioning_id": commissioning_id,
        "state": "claimed", "on_attempts": 0, "off_attempts": 0,
    }
    claim = store("claim_before_on", execution)
    if claim.get("created") is not True:
        return _result("execution_claim_conflict", commands=0, messages=0)
    accepted = transport.set_state(device_id="100204e9bc", channel=execution["channel"], state="ON",
                                   idempotency_key=execution["execution_id"] + ":ON")
    store("record_on_outcome", {**execution, "on_attempts": 1, "on_outcome": accepted})
    if accepted.get("accepted_unambiguous") is not True:
        # Never issue another ON. OFF recovery is safe even after ambiguous ON.
        store("contain_zone", {**execution, "state": "ambiguous",
              "shutdown_verified": False, "reason": "ambiguous_on"})
        recovery = _bounded_off(execution, store, transport)
        try:
            shutdown = transport.read_output_state(device_id="100204e9bc", channel=execution["channel"])
        except Exception:
            shutdown = {"authoritative": False, "state": "Unknown"}
        verified = shutdown.get("authoritative") is True and shutdown.get("state") == "OFF"
        store("record_ambiguous_shutdown", {**execution, "state": "ambiguous",
              "shutdown_verified": verified, "shutdown_evidence": shutdown})
        notify("Exception", {**execution, "reason": "ambiguous_on", "recovery": recovery,
                              "shutdown_verified": verified})
        return _result("ambiguous_on_contained" if verified else "ambiguous_on_shutdown_unverified",
                       commands=1 + recovery["commands"], messages=1)
    started = transport.read_output_state(device_id="100204e9bc", channel=execution["channel"])
    if started.get("authoritative") is not True or started.get("state") != "ON":
        store("record_start_unverified", {**execution, "on_attempts": 1,
              "provider_acceptance": accepted, "output_readback": started})
        recovery = _bounded_off(execution, store, transport)
        store("contain_zone", {**execution, "state": "ambiguous", "shutdown_verified": False})
        notify("Exception", {**execution, "reason": "start_unverified", "recovery": recovery})
        return _result("start_unverified_contained", commands=1 + recovery["commands"], messages=1)
    active_execution = {**execution, "state": "Active", "on_attempts": 1,
                        "start_evidence": started}
    store("mark_active", active_execution)
    notify("Active", active_execution)
    return _result("segment_started", commands=1, messages=1, execution=active_execution,
                   autonomous_on_enabled=True)


def _recover_or_observe(active, store, transport, notify, outcome_reader, now):
    if active.get("state") in {"claimed", "claimed_recovery_required"}:
        store("contain_zone", {**active, "state": "ambiguous",
              "shutdown_verified": False, "reason": "restart_after_pre_on_claim"})
        recovery = _bounded_off(active, store, transport)
        try:
            shutdown = transport.read_output_state(device_id="100204e9bc", channel=active["channel"])
        except Exception:
            shutdown = {"authoritative": False, "state": "Unknown"}
        verified = shutdown.get("authoritative") is True and shutdown.get("state") == "OFF"
        store("record_claim_recovery", {**active, "shutdown_verified": verified,
              "shutdown_evidence": shutdown})
        notify("Exception", {**active, "reason": "interrupted_start_contained",
                              "shutdown_verified": verified})
        return _result("interrupted_start_contained" if verified else "interrupted_start_shutdown_unverified",
                       commands=recovery["commands"], messages=1)
    primary_deadline = _timestamp(active.get("primary_stop_deadline"))
    native_deadline = _timestamp(active.get("native_fail_stop_deadline"))
    if primary_deadline is None or native_deadline is None or primary_deadline > native_deadline:
        recovery = _bounded_off(active, store, transport)
        notify("Exception", {**active, "reason": "fail_stop_deadline_missing", "recovery": recovery})
        return _result("active_segment_contained", commands=recovery["commands"], messages=1)
    if now < primary_deadline:
        return _result("active_segment_owned", commands=0, messages=0, execution=active)
    recovery = _bounded_off(active, store, transport)
    shutdown = transport.read_output_state(device_id="100204e9bc", channel=active["channel"])
    if shutdown.get("state") != "OFF" or shutdown.get("authoritative") is not True:
        store("contain_zone", {**active, "state": "ambiguous", "shutdown_verified": False})
        notify("Exception", {**active, "reason": "shutdown_unverified"})
        return _result("shutdown_unverified", commands=recovery["commands"], messages=1)
    objective = _canonical_outcome(
        outcome_reader(active["execution_id"]), active, shutdown, now)
    completed = {**active, "state": "Completed", "shutdown_verified": True,
                 "objective_satisfied": objective.get("objective_satisfied") is True,
                 "objective_evidence": objective,
                 "shutdown_evidence": shutdown, "completed_at": now.isoformat()}
    store("record_completed", completed)
    notify("Completed", completed)
    return _result("segment_completed", commands=recovery["commands"], messages=1,
                   execution=completed)


def _bounded_off(execution, store, transport):
    commands = 0; outcomes = []
    prior = store("load_off_attempts", execution["execution_id"]) or []
    used = {int(item.get("attempt")) for item in prior if isinstance(item, dict)
            and str(item.get("attempt") or "").isdigit()}
    for attempt in range(1, MAX_OFF_ATTEMPTS + 1):
        if attempt in used:
            continue
        claim = store("claim_off_attempt", {"execution_id": execution["execution_id"],
                      "attempt": attempt, "idempotency_key": f"{execution['execution_id']}:OFF:{attempt}"})
        if not isinstance(claim, dict) or claim.get("created") is not True:
            continue
        outcome = transport.set_state(device_id="100204e9bc", channel=execution["channel"],
                                      state="OFF",
                                      idempotency_key=f"{execution['execution_id']}:OFF:{attempt}")
        commands += 1; outcomes.append(outcome)
        store("record_off_outcome", {"execution_id": execution["execution_id"],
              "attempt": attempt, "outcome": outcome})
        if outcome.get("accepted_unambiguous") is True:
            break
    return {"commands": commands, "outcomes": outcomes}


def _eligible(decision, decision_id, commissioning, now):
    if not isinstance(decision, dict) or not isinstance(commissioning, dict): return False
    supplied = decision.get("decision_sha256")
    canonical = {key: value for key, value in decision.items() if key != "decision_sha256"}
    zone = decision.get("zone_id")
    assessed = _timestamp(decision.get("assessed_at"))
    return (decision.get("decision_id") == decision_id and supplied == _digest(canonical)
            and zone in ZONES and decision.get("decision") == "Run now"
            and decision.get("standing_authority") is True
            and decision.get("runtime_minutes") in range(1, MAX_MINUTES + 1)
            and assessed is not None and timedelta(0) <= now - assessed <= timedelta(minutes=15)
            and commissioning.get("zone_id") == zone
            and commissioning.get("channel") == ZONES[zone]
            and commissioning.get("commissioned") is True
            and decision.get("commissioning_id") == commissioning.get("commissioning_id")
            and decision.get("commissioning_generation") == commissioning.get("configuration_generation")
            and commissioning.get("native_inching_seconds") == 3600)


def _canonical_commissioning(packet, commissioning_id, now):
    if not isinstance(packet, dict) or packet.get("commissioning_id") != commissioning_id:
        return None
    try:
        evidence = packet.get("evidence") or {}
        validated = validate_commissioning(str(evidence.get("zone_id") or ""), evidence, now=now)
    except Exception:
        return None
    if validated.get("commissioning_id") != commissioning_id:
        return None
    return {**validated, "native_inching_seconds": validated["native_fail_stop_minutes"] * 60}


def _canonical_outcome(packet, execution, shutdown, now):
    if not isinstance(packet, dict): return {}
    supplied = packet.get("outcome_sha256")
    material = {key: value for key,value in packet.items() if key != "outcome_sha256"}
    observed = _timestamp(packet.get("observed_at"))
    claimed = _timestamp(execution.get("claimed_at"))
    primary_stop = _timestamp(execution.get("primary_stop_deadline"))
    if (packet.get("execution_id") != execution.get("execution_id")
            or supplied != _digest(material) or observed is None or claimed is None
            or primary_stop is None or observed < primary_stop or observed > now
            or packet.get("zone_id") != execution.get("zone_id")
            or packet.get("channel") != execution.get("channel")
            or packet.get("eligibility_id") != execution.get("eligibility_id")
            or packet.get("evidence_generation") != execution.get("evidence_generation")
            or packet.get("shutdown_evidence_id") != shutdown.get("evidence_id")
            or packet.get("actor") != "ROOTLINE_CANONICAL_OUTCOME"
            or packet.get("provenance") not in {"canonical_post_segment", "authenticated_owner_outcome"}):
        return {}
    return packet


def _safe_configuration(value, zone):
    return (isinstance(value, dict) and value.get("authoritative") is True
            and value.get("zone_id") == zone and value.get("channel") == ZONES[zone]
            and value.get("native_inching_enabled") is True
            and 0 < int(value.get("native_inching_seconds") or 0) <= 3600
            and value.get("power_restoration_state") == "OFF"
            and value.get("schedules_enabled") is False
            and value.get("interlock_enabled") is False
            and value.get("scenes_enabled") is False)


def _result(status, *, commands, messages, **extra):
    return {"success": True, "status": status, "hardware_commands": commands,
            "telegram_messages": messages, "automatic_on_retry": False,
            "simultaneous_zones": False, "borehole_authority": False,
            "fertilizer_authority": False, **extra}


def _timestamp(value):
    try: return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError): return None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             default=str).encode()).hexdigest()
