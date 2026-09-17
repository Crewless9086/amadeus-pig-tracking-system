"""Durable coordinator for the existing ROOTLINE execution contract.

Effects are supplied by the canonical persistence, provider and Oom Sakkie
adapters. The coordinator never guesses readback and never retries ON.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from modules.telemetry.rootline_irrigation_execution_contract import validate_commissioning
from modules.telemetry.rootline_execution_authority import (
    equivalent_fresh_eligibility, validate_execution_eligibility,
)
from modules.telemetry.rootline_ewelink_commissioned_baseline import validate_commissioned_baseline
from modules.telemetry.rootline_auxiliary_management import (
    revalidate_auxiliary_execution_edge, validate_auxiliary_eligibility,
)
from modules.telemetry.rootline_irrigation_execution_store import (
    RootlineExecutionStoreUnavailable,
)
from modules.telemetry.rootline_device_registry import (
    commissioned_irrigation_contract, get_device_contract,
)

MAX_MINUTES = 60
MAX_OFF_ATTEMPTS = 3
EMERGENCY_OFF_AUXILIARY_DEVICE_ID = "FERTILIZER-MIXER-CH2"
EMERGENCY_OFF_DEVICE_ID = "100204d497"
EMERGENCY_OFF_CHANNEL = "2"


def advance_irrigation_execution(*, decision_id, commissioning_id,
                                 decision_reader, commissioning_reader, store, transport,
                                 notify, outcome_reader=lambda _identity: None,
                                 eligibility_revalidator=lambda _decision: None, now=None,
                                 clock=None):
    now = _aware(now or datetime.now(timezone.utc))
    clock = clock or (lambda: datetime.now(timezone.utc))
    try:
        active = store("load_active", None)
    except RootlineExecutionStoreUnavailable:
        return _result("execution_store_degraded_hold", commands=0, messages=0,
            autonomous_on_enabled=False, durable_execution_truth_loaded=False,
            current_segment_consumed=False, degraded=True)
    if active:
        return _recover_or_observe(active, store, transport, notify, outcome_reader, now)
    decision = decision_reader(decision_id)
    commissioning_packet = commissioning_reader(commissioning_id)
    commissioning = _canonical_commissioning(commissioning_packet, commissioning_id, now)
    if not _eligible(decision, decision_id, commissioning, now):
        return _result("not_eligible", commands=0, messages=0)
    try:
        contained = store("load_zone_containment", decision["zone_id"]) or {}
    except RootlineExecutionStoreUnavailable:
        return _degraded_hold()
    if contained.get("contained") is True:
        if _release_configuration_containment(contained, decision, store, transport):
            return _result("zone_containment_released_reassess", commands=0, messages=0)
        return _result("zone_contained", commands=0, messages=0)
    try:
        output = commissioned_irrigation_contract(decision["zone_id"])
    except ValueError:
        return _result("irrigation_output_not_commissioned", commands=0, messages=0)
    safety = transport.read_safety_configuration(
        device_id=output["device_id"], channel=output["channel"])
    if not _safe_configuration(safety, decision["zone_id"]):
        return _result("provider_safety_readback_unavailable", commands=0, messages=0,
                       autonomous_on_enabled=False)
    # This read-only edge check is intentionally after provider safety and
    # immediately before the durable claim. It prevents a fresh rain Hold or
    # evidence-generation change from racing a previously eligible decision.
    revalidated = eligibility_revalidator(decision)
    preclaim_now = _aware(clock())
    if (not equivalent_fresh_eligibility(
            decision.get("execution_eligibility"), revalidated, now=preclaim_now)
            or revalidated.get("zone_id") != decision.get("zone_id")):
        return _result("execution_eligibility_changed", commands=0, messages=0)
    execution = {
        "execution_id": decision["execution_id"], "eligibility_id": decision["eligibility_id"],
        "eligibility_sha256": decision["execution_eligibility"]["eligibility_sha256"],
        "consumption_key": decision["execution_eligibility"]["consumption_key"],
        "job_id": decision["execution_eligibility"]["job_id"],
        "job_sha256": decision["execution_eligibility"]["job_sha256"],
        "requested_total_duration_seconds": decision["execution_eligibility"][
            "requested_total_duration_seconds"],
        "governed_executable_duration_seconds": decision["execution_eligibility"][
            "governed_executable_duration_seconds"],
        "requested_total_duration_minutes": decision["execution_eligibility"][
            "requested_total_duration_minutes"],
        "expected_segment_count": decision["execution_eligibility"]["expected_segment_count"],
        "current_segment": decision["execution_eligibility"]["current_segment"],
        "segment_number": decision["execution_eligibility"]["current_segment"],
        "segment_identity": decision["execution_eligibility"]["segment_identity"],
        "segment_requested_seconds": decision["execution_eligibility"]["segment_requested_seconds"],
        "controller_safety_generation": decision["execution_eligibility"][
            "controller_safety_generation"],
        "cumulative_verified_runtime_seconds": decision["execution_eligibility"][
            "cumulative_verified_runtime_seconds"],
        "predecessor_off_rearm_verified": decision["execution_eligibility"][
            "predecessor_off_rearm_verified"],
        "operating_date": decision["execution_eligibility"]["operating_date"],
        "evidence_generation": decision["evidence_generation"], "zone_id": decision["zone_id"],
        "device_id": output["device_id"], "channel": output["channel"],
        "planned_runtime_minutes": decision["runtime_minutes"],
        "planned_runtime_seconds": decision["runtime_seconds"],
        "claimed_at": preclaim_now.isoformat(),
        "primary_stop_deadline": (preclaim_now + timedelta(seconds=decision["runtime_seconds"])).isoformat(),
        "native_fail_stop_deadline": (preclaim_now + timedelta(
            seconds=commissioning["native_inching_seconds"])).isoformat(),
        "commissioning_id": commissioning_id,
        "state": "claimed", "on_attempts": 0, "off_attempts": 0,
    }
    try:
        claim = store("claim_before_on", execution)
    except RootlineExecutionStoreUnavailable:
        return _degraded_hold(consumption_unknown=True)
    if claim.get("created") is not True:
        return _result("execution_claim_conflict", commands=0, messages=0)
    accepted = transport.set_state(device_id=execution["device_id"], channel=execution["channel"], state="ON",
                                   idempotency_key=execution["execution_id"] + ":ON")
    store("record_on_outcome", {**execution, "on_attempts": 1, "on_outcome": accepted})
    if accepted.get("accepted_unambiguous") is not True:
        # Never issue another ON. OFF recovery is safe even after ambiguous ON.
        store("contain_zone", {**execution, "state": "ambiguous",
              "shutdown_verified": False, "reason": "ambiguous_on",
              "transport_status": accepted.get("status")})
        recovery = _bounded_off(execution, store, transport)
        try:
            shutdown = transport.read_output_state(device_id=execution["device_id"], channel=execution["channel"])
        except Exception:
            shutdown = {"authoritative": False, "state": "Unknown"}
        verified = shutdown.get("authoritative") is True and shutdown.get("state") == "OFF"
        store("record_ambiguous_shutdown", {**execution, "state": "ambiguous",
              "shutdown_verified": verified, "shutdown_evidence": shutdown})
        delivery = _notify(notify, store, "Intervention", {**execution,
            "reason": "ambiguous_on", "recovery": recovery, "shutdown_verified": verified})
        return _result("ambiguous_on_contained" if verified else "ambiguous_on_shutdown_unverified",
                       commands=1 + recovery["commands"], messages=delivery["confirmed"],
                       notification=delivery)
    started = transport.read_output_state(device_id=execution["device_id"], channel=execution["channel"])
    if started.get("authoritative") is not True or started.get("state") != "ON":
        store("record_start_unverified", {**execution, "on_attempts": 1,
              "provider_acceptance": accepted, "output_readback": started})
        recovery = _bounded_off(execution, store, transport)
        store("contain_zone", {**execution, "state": "ambiguous", "shutdown_verified": False})
        delivery = _notify(notify, store, "Intervention", {**execution,
            "reason": "start_unverified", "recovery": recovery})
        return _result("start_unverified_contained", commands=1 + recovery["commands"],
                       messages=delivery["confirmed"], notification=delivery)
    active_execution = {**execution, "state": "Active", "on_attempts": 1,
                        "start_evidence": started}
    store("mark_active", active_execution)
    delivery = _notify(notify, store, "Started", active_execution)
    return _result("segment_started", commands=1, messages=delivery["confirmed"],
                   execution=active_execution, notification=delivery,
                   autonomous_on_enabled=True, writes_farm_data=True)


def advance_auxiliary_execution(*, eligibility, store, transport, revalidate=None, now=None):
    """Advance one typed irrigation-auxiliary execution on the existing rail.

    This function owns no planner or provider mapping.  It consumes one
    planner-minted artifact, uses caller-supplied canonical effects, and
    contains only the auxiliary device on failure.  B/C shutdown ownership is
    never removed.
    """
    now = _aware(now or datetime.now(timezone.utc))
    active = store("load_active_auxiliary", None)
    if active:
        return _recover_auxiliary(active, store, transport, now)
    artifact = validate_auxiliary_eligibility(eligibility, now=now)
    if not artifact:
        return _aux_result("auxiliary_not_eligible")
    containment=store("load_auxiliary_containment",artifact["auxiliary_device_id"])
    if isinstance(containment,dict) and containment.get("contained") is True:
        return _aux_result("auxiliary_device_contained",fertilizer_debt=True,
            auxiliary_contained=True)
    if not callable(revalidate):
        return _aux_result("auxiliary_edge_revalidation_unavailable")
    current_context=revalidate(artifact)
    try:
        current_safety=transport.read_safety_configuration(
            device_id=artifact["device_id"],channel=artifact["channel"])
    except Exception:
        current_safety={}
    if not revalidate_auxiliary_execution_edge(artifact,current_context=current_context,
            current_safety=current_safety,now=now):
        return _aux_result("auxiliary_edge_revalidation_failed")
    execution = {"execution_id":artifact["execution_id"],
        "eligibility_id":artifact["eligibility_id"],
        "consumption_key":artifact["consumption_key"],
        "auxiliary_device_id":artifact["auxiliary_device_id"],
        "device_type":artifact["device_type"],"device_id":artifact["device_id"],
        "channel":artifact["channel"],"zone_id":artifact.get("zone_id"),
        "job_id":artifact.get("job_id"),"job_sha256":artifact.get("job_sha256"),
        "segment_identity":artifact.get("segment_identity"),
        "zone_execution_id":artifact.get("zone_execution_id"),
        "pulse_number":artifact.get("pulse_number"),
        "maximum_duration_seconds":artifact["maximum_duration_seconds"],
        "claimed_at":now.isoformat(),"primary_stop_deadline":(
            now+timedelta(seconds=artifact["maximum_duration_seconds"])).isoformat(),
        "state":"claimed","on_attempts":0,"off_attempts":0}
    claim=store("claim_auxiliary_before_on",execution)
    if not isinstance(claim,dict) or claim.get("created") is not True:
        return _aux_result("auxiliary_claim_conflict")
    dispatch=lambda:transport.set_state(device_id=execution["device_id"],
        channel=execution["channel"],state="ON",
        idempotency_key=execution["execution_id"]+":ON")
    accepted=(store("dispatch_auxiliary_on_edge",{**execution,"dispatch":dispatch})
        if execution["device_type"]=="fertilizer_injection_valve" else dispatch())
    store("record_auxiliary_on_outcome",{**execution,"on_attempts":1,"on_outcome":accepted})
    if accepted.get("accepted_unambiguous") is not True:
        recovery=_bounded_auxiliary_off(execution,store,transport)
        shutdown=_read_auxiliary_output(execution,transport)
        verified=shutdown.get("authoritative") is True and shutdown.get("state")=="OFF"
        store("contain_auxiliary_device",{**execution,"reason":"ambiguous_on",
            "shutdown_verified":verified,"shutdown_evidence":shutdown})
        store("record_auxiliary_exception",{**execution,"reason":"ambiguous_on",
            "fertilizer_debt":True,"shutdown_verified":verified})
        return _aux_result("auxiliary_ambiguous_on_contained" if verified
            else "auxiliary_shutdown_intervention_required",commands=1+recovery["commands"],
            state="Intervention",fertilizer_debt=True,auxiliary_contained=True)
    started=_read_auxiliary_output(execution,transport)
    if started.get("authoritative") is not True or started.get("state")!="ON":
        recovery=_bounded_auxiliary_off(execution,store,transport)
        store("contain_auxiliary_device",{**execution,"reason":"start_unverified",
            "shutdown_verified":False})
        return _aux_result("auxiliary_start_unverified",commands=1+recovery["commands"],
            state="Intervention",fertilizer_debt=True,auxiliary_contained=True)
    active={**execution,"state":"Active","on_attempts":1,"start_evidence":started}
    store("mark_auxiliary_active",active)
    return _aux_result("auxiliary_started",commands=1,state="Started",execution=active)


def emergency_off_auxiliary_execution(*, store, transport,
                                      reason="emergency_off", expected_device_id=None):
    """Drive one exact active auxiliary output to authoritative OFF.

    Emergency shutdown never grants ON authority and reuses the existing
    execution, OFF-attempt and containment rails. The complete canonical
    binding prevents injection, borehole or unrelated outputs from inheriting
    a Mixer's stop request.
    """
    active = store("load_active_auxiliary", None)
    if not isinstance(active, dict):
        return _aux_result("auxiliary_emergency_off_no_active_execution")
    expected_identity=(expected_device_id or EMERGENCY_OFF_AUXILIARY_DEVICE_ID)
    expected=get_device_contract(expected_identity)
    if (not expected or expected_identity not in {
            "FERTILIZER-MIXER-CH2","FERTILIZER-INJECTION-CH1"}
            or active.get("auxiliary_device_id") != expected_identity
            or active.get("device_id") != expected.get("device_id")
            or active.get("channel") != expected.get("channel")):
        return _aux_result("auxiliary_emergency_off_binding_mismatch",
            state="Intervention", fertilizer_debt=True)
    recovery = _bounded_auxiliary_off(active, store, transport)
    shutdown = _read_auxiliary_output(active, transport)
    verified = (shutdown.get("authoritative") is True
                and shutdown.get("state") == "OFF")
    containment = {**active, "reason": str(reason or "emergency_off"),
        "shutdown_verified": verified, "shutdown_evidence": shutdown}
    store("contain_auxiliary_device", containment)
    if not verified:
        store("record_auxiliary_exception", {**containment,
            "fertilizer_debt": True})
    return _aux_result("auxiliary_emergency_off_verified" if verified
        else "auxiliary_emergency_off_unverified",
        commands=recovery["commands"], state="Intervention",
        fertilizer_debt=not verified, auxiliary_contained=True,
        shutdown_verified=verified, shutdown_evidence=shutdown,
        execution_id=active.get("execution_id"))


def _recover_auxiliary(active,store,transport,now):
    deadline=_timestamp(active.get("primary_stop_deadline"))
    claimed_at=_timestamp(active.get("claimed_at"))
    if (active.get("state")=="claimed" and claimed_at is not None
            and timedelta(0)<=now-claimed_at<=timedelta(seconds=30)):
        return _aux_result("auxiliary_claim_in_progress",execution=active)
    if active.get("state") in {"claimed","claimed_recovery_required"} or deadline is None:
        recovery=_bounded_auxiliary_off(active,store,transport)
        shutdown=_read_auxiliary_output(active,transport)
        verified=shutdown.get("authoritative") is True and shutdown.get("state")=="OFF"
        store("contain_auxiliary_device",{**active,"reason":"restart_or_deadline_ambiguous",
            "shutdown_verified":verified,"shutdown_evidence":shutdown})
        return _aux_result("auxiliary_restart_contained",commands=recovery["commands"],
            state="Intervention",fertilizer_debt=True,auxiliary_contained=True)
    if now<deadline:
        return _aux_result("auxiliary_active",execution=active)
    recovery=_bounded_auxiliary_off(active,store,transport)
    shutdown=_read_auxiliary_output(active,transport)
    if shutdown.get("authoritative") is not True or shutdown.get("state")!="OFF":
        store("contain_auxiliary_device",{**active,"reason":"shutdown_unverified",
            "shutdown_verified":False,"shutdown_evidence":shutdown})
        store("record_auxiliary_exception",{**active,"reason":"shutdown_unverified",
            "fertilizer_debt":True})
        return _aux_result("auxiliary_shutdown_intervention_required",
            commands=recovery["commands"],state="Intervention",fertilizer_debt=True,
            auxiliary_contained=True)
    physical = store("load_auxiliary_physical_outcome", active["execution_id"])
    injection = active.get("auxiliary_device_id") == "FERTILIZER-INJECTION-CH1"
    if injection:
        physical_verified = _injection_delivery_verified(active, physical, shutdown)
    else:
        start = active.get("start_evidence") if isinstance(
            active.get("start_evidence"), dict) else {}
        physical_verified = (active.get("auxiliary_device_id") ==
            "FERTILIZER-MIXER-CH2" and active.get("device_id") == "100204d497"
            and active.get("channel") == 2
            and 1 <= int(active.get("maximum_duration_seconds") or 0) <= 1800
            and start.get("authoritative") is True and start.get("state") == "ON"
            and shutdown.get("authoritative") is True and shutdown.get("state") == "OFF")
    completed={**active,"state":"Completed","shutdown_verified":True,
        "shutdown_evidence":shutdown,"completed_at":now.isoformat(),
        "maximum_runtime_seconds":active["maximum_duration_seconds"],
        "verified_runtime_seconds":None,"physical_outcome":"Unknown",
        "nutrient_dose":"Unknown","concentration":"Unknown",
        "delivered_volume":"Unavailable",
        "physical_outcome_verified":physical_verified,
        "physical_outcome_evidence":({"proof":"provider_app_on_to_off",
            "start_evidence":active.get("start_evidence"),
            "shutdown_evidence":shutdown} if physical_verified and not injection
            else physical if physical_verified else None)}
    # An authoritative OFF readback proves only that the bounded control pulse
    # stopped. It is not fertilizer-delivery evidence. Keep an unverified
    # injection out of completed history so pulse count, real-flow
    # commissioning and owner-facing completion cannot inherit an OFF receipt.
    completion_action = ("record_auxiliary_completed" if physical_verified
        or not injection else "record_auxiliary_control_pulse_stopped")
    if injection and not physical_verified:
        completed.update({"state":"ControlPulseStopped",
            "delivery_state":"Unverified","fertilizer_delivery_verified":False,
            "completion_scope":"control_off_only","fertilizer_debt":True})
    elif injection:
        completed.update({"delivery_state":"Verified",
            "fertilizer_delivery_verified":True,
            "completion_scope":"provider_canonical_physical_pulse_delivery",
            "fertilizer_lifecycle_completed":False,
            "postflow_flush_required":True})
    recorded=store(completion_action,completed)
    if not isinstance(recorded,dict) or recorded.get("success") is not True:
        return _aux_result("auxiliary_completion_persistence_unproven",
            commands=recovery["commands"],state="Intervention",fertilizer_debt=True)
    if injection and not physical_verified:
        return _aux_result("auxiliary_control_pulse_off_verified",
            commands=recovery["commands"],state="Intervention",fertilizer_debt=True,
            execution=completed,physical_delivery_verified=False)
    return _aux_result("auxiliary_injection_delivery_verified" if injection
        else "auxiliary_completed",commands=recovery["commands"],
        state="Completed",execution=completed,
        physical_delivery_verified=physical_verified)


def _injection_delivery_verified(active, physical, shutdown):
    """Require evidence bound to this exact pulse before delivery completion."""
    if not isinstance(physical,dict):
        return False
    immutable=("execution_id","job_id","job_sha256","segment_identity",
        "zone_id","zone_execution_id","pulse_number")
    if any(physical.get(key)!=active.get(key) for key in immutable):
        return False
    return (shutdown.get("authoritative") is True and shutdown.get("state")=="OFF"
        and physical.get("canonical_pulse_recorded") is True
        and physical.get("provider_pulse_on_verified") is True
        and physical.get("provider_pulse_off_verified") is True
        and physical.get("physical_fertilizer_flow_verified") is True
        and physical.get("clean_water_preflow_verified") is True
        and bool(str(physical.get("evidence_id") or "").strip()))


def _bounded_auxiliary_off(execution,store,transport):
    commands=0; outcomes=[]
    prior=store("load_auxiliary_off_attempts",execution["execution_id"]) or []
    used={int(row.get("attempt") or 0) for row in prior if isinstance(row,dict)}
    for attempt in range(1,MAX_OFF_ATTEMPTS+1):
        if attempt in used: continue
        claim=store("claim_auxiliary_off_attempt",{"execution_id":execution["execution_id"],
            "attempt":attempt})
        if not isinstance(claim,dict) or claim.get("created") is not True: continue
        outcome=transport.set_state(device_id=execution["device_id"],channel=execution["channel"],
            state="OFF",idempotency_key=f"{execution['execution_id']}:OFF:{attempt}")
        commands+=1;outcomes.append(outcome)
        store("record_auxiliary_off_outcome",{"execution_id":execution["execution_id"],
            "attempt":attempt,"outcome":outcome})
        if outcome.get("accepted_unambiguous") is True: break
    return {"commands":commands,"outcomes":outcomes}


def _read_auxiliary_output(execution,transport):
    try:return transport.read_output_state(device_id=execution["device_id"],
        channel=execution["channel"])
    except Exception:return {"authoritative":False,"state":"Unknown"}


def _aux_result(status,*,commands=0,state=None,fertilizer_debt=False,
                auxiliary_contained=False,**extra):
    return {"success":True,"status":status,"hardware_commands":commands,
        "notification_state":state,"fertilizer_debt":fertilizer_debt,
        "auxiliary_contained":auxiliary_contained,"irrigation_may_continue":True,
        "irrigation_shutdown_authority_unchanged":True,"borehole_authority":False,
        "channels_3_4_authority":False,"automatic_on_retry":False,**extra}


def _recover_or_observe(active, store, transport, notify, outcome_reader, now):
    if active.get("state") in {"claimed", "claimed_recovery_required"}:
        barrier=store("mark_stopping",{**active,"state":"stopping",
            "reason":"restart_after_pre_on_claim"})
        if not isinstance(barrier,dict) or barrier.get("success") is not True:
            return _stopping_barrier_hold(active,store,notify)
        store("contain_zone", {**active, "state": "ambiguous",
              "shutdown_verified": False, "reason": "restart_after_pre_on_claim"})
        auxiliary_stop = _stop_bound_injection(active,store,transport)
        blocked = _hold_parent_flow_if_injector_off_unverified(
            active,auxiliary_stop,store,transport,notify,now,
            "restart_after_pre_on_claim")
        if blocked:
            return blocked
        recovery = _bounded_off(active, store, transport)
        try:
            shutdown = transport.read_output_state(device_id=_output_binding(active)["device_id"], channel=active["channel"])
        except Exception:
            shutdown = {"authoritative": False, "state": "Unknown"}
        verified = shutdown.get("authoritative") is True and shutdown.get("state") == "OFF"
        store("record_claim_recovery", {**active, "shutdown_verified": verified,
              "shutdown_evidence": shutdown})
        delivery = _notify(notify, store, "Intervention", {**active,
            "reason": "interrupted_start_contained", "shutdown_verified": verified})
        return _result("interrupted_start_contained" if verified else "interrupted_start_shutdown_unverified",
                       commands=recovery["commands"]+auxiliary_stop["hardware_commands"], messages=delivery["confirmed"],
                       notification=delivery)
    primary_deadline = _timestamp(active.get("primary_stop_deadline"))
    native_deadline = _timestamp(active.get("native_fail_stop_deadline"))
    if primary_deadline is None or native_deadline is None or primary_deadline > native_deadline:
        barrier=store("mark_stopping",{**active,"state":"stopping",
            "reason":"fail_stop_deadline_missing"})
        if not isinstance(barrier,dict) or barrier.get("success") is not True:
            return _stopping_barrier_hold(active,store,notify)
        auxiliary_stop = _stop_bound_injection(active,store,transport)
        blocked = _hold_parent_flow_if_injector_off_unverified(
            active,auxiliary_stop,store,transport,notify,now,
            "fail_stop_deadline_missing")
        if blocked:
            return blocked
        recovery = _bounded_off(active, store, transport)
        delivery = _notify(notify, store, "Intervention", {**active,
            "reason": "fail_stop_deadline_missing", "recovery": recovery})
        return _result("active_segment_contained", commands=recovery["commands"]+
                       auxiliary_stop["hardware_commands"],
                       messages=delivery["confirmed"], notification=delivery)
    if now < primary_deadline:
        return _result("active_segment_owned", commands=0, messages=0, execution=active)
    barrier=store("mark_stopping",{**active,"state":"stopping",
        "reason":"primary_deadline_reached"})
    if not isinstance(barrier,dict) or barrier.get("success") is not True:
        return _stopping_barrier_hold(active,store,notify)
    auxiliary_stop = _stop_bound_injection(active,store,transport)
    blocked = _hold_parent_flow_if_injector_off_unverified(
        active,auxiliary_stop,store,transport,notify,now,
        "primary_deadline_reached")
    if blocked:
        return blocked
    recovery = _bounded_off(active, store, transport)
    shutdown = transport.read_output_state(device_id=_output_binding(active)["device_id"], channel=active["channel"])
    if shutdown.get("state") != "OFF" or shutdown.get("authoritative") is not True:
        store("contain_zone", {**active, "state": "ambiguous", "shutdown_verified": False})
        delivery = _notify(notify, store, "Intervention", {**active,
            "reason": "shutdown_unverified"})
        return _result("shutdown_unverified", commands=recovery["commands"]+
                       auxiliary_stop["hardware_commands"],
                       messages=delivery["confirmed"], notification=delivery)
    shutdown_at = _timestamp(shutdown.get("retrieved_at"))
    completion_now = max(now, shutdown_at) if shutdown_at is not None else now
    objective = _canonical_outcome(
        outcome_reader(active["execution_id"]), active, shutdown, completion_now)
    if not objective:
        objective = _provider_bounded_outcome(active, shutdown, completion_now)
    completed = {**active, "state": "Completed", "shutdown_verified": True,
                 "objective_satisfied": objective.get("objective_satisfied") is True,
                 "objective_evidence": objective,
                 "shutdown_evidence": shutdown, "completed_at": completion_now.isoformat()}
    # Preserve the historical execution record shape for pre-job actions.  Job
    # lifecycle fields are authoritative only when the claimed action carried
    # the governed, persisted job identity and duration contract.
    if active.get("job_id"):
        completed["verified_runtime_seconds"] = int(
            (objective.get("verified_runtime_minutes") or 0) * 60)
        # Shutdown readback proves this segment OFF.  A later fresh controller
        # safety readback proves re-arm before another segment gains authority.
        completed["rearm_readback_off"] = False
        completed["cumulative_verified_runtime_seconds"] = int(
            active.get("cumulative_verified_runtime_seconds") or 0
        ) + completed["verified_runtime_seconds"]
        completed["job_completed"] = (
            completed["cumulative_verified_runtime_seconds"] >= int(
                active["governed_executable_duration_seconds"]))
    recorded = store("record_completed", completed)
    if not isinstance(recorded, dict) or recorded.get("success") is not True:
        delivery = _notify(notify, store, "Intervention", {**completed,
            "reason": "canonical_completion_persistence_unproven"})
        return _result("completion_persistence_unproven", commands=recovery["commands"],
                       messages=delivery["confirmed"], execution=completed,
                       notification=delivery, writes_farm_data=False)
    lifecycle = "Completed" if completed["objective_satisfied"] else "Intervention"
    if lifecycle == "Intervention":
        completed["reason"] = "shutdown_verified_outcome_unconfirmed"
    delivery = _notify(notify, store, lifecycle, completed)
    return _result("segment_completed" if completed["objective_satisfied"]
                   else "segment_stopped_outcome_unconfirmed",
                   commands=recovery["commands"]+auxiliary_stop["hardware_commands"],
                   messages=delivery["confirmed"], execution=completed,
                   notification=delivery, writes_farm_data=True)


def _stop_bound_injection(parent,store,transport):
    auxiliary=store("load_active_auxiliary",None)
    if (not isinstance(auxiliary,dict)
            or auxiliary.get("auxiliary_device_id")!="FERTILIZER-INJECTION-CH1"):
        return _aux_result("no_bound_injection")
    bindings=("job_id","job_sha256","segment_identity","zone_id")
    mismatch=any(auxiliary.get(key)!=parent.get(key) for key in bindings)
    result=emergency_off_auxiliary_execution(store=store,transport=transport,
        reason=("parent_binding_mismatch" if mismatch else "parent_irrigation_stopping"),
        expected_device_id="FERTILIZER-INJECTION-CH1")
    return {**result,"parent_binding_mismatch":mismatch}


def _hold_parent_flow_if_injector_off_unverified(parent,auxiliary_stop,store,
                                                  transport,notify,now,stop_reason):
    """Withhold parent OFF without confusing that command fact with water flow."""
    status=str((auxiliary_stop or {}).get("status") or "")
    if status in {"no_bound_injection","auxiliary_emergency_off_no_active_execution"}:
        return None
    if (auxiliary_stop.get("shutdown_verified") is True
            and status=="auxiliary_emergency_off_verified"):
        return None
    native_deadline=_timestamp(parent.get("native_fail_stop_deadline"))
    deadline_phase=("unknown" if native_deadline is None else
        "before" if now<native_deadline else "at_or_after")
    try:
        parent_output=transport.read_output_state(
            device_id=_output_binding(parent)["device_id"],channel=parent["channel"])
    except Exception:
        parent_output={"authoritative":False,"state":"Unknown"}
    parent_state=str(parent_output.get("state") or "Unknown")
    parent_authoritative=(parent_output.get("authoritative") is True
        and parent_state in {"ON","OFF"})
    if deadline_phase=="at_or_after":
        conflict_status="injector_off_unverified_native_deadline_elapsed"
    elif not parent_authoritative:
        conflict_status="parent_output_unverified_injector_off_unverified"
    elif parent_state=="OFF":
        conflict_status="parent_off_observed_injector_off_unverified"
    else:
        conflict_status="parent_off_withheld_injector_off_unverified"
    conflict={**parent,"state":"stopping","reason":
        conflict_status,
        "parent_stop_reason":stop_reason,"shutdown_verified":False,
        "parent_shutdown_aborted":True,"parent_off_command_withheld":True,
        "parent_output_authoritative":parent_authoritative,
        "parent_output_state":parent_state if parent_authoritative else "Unknown",
        "parent_output_evidence":parent_output,
        "irrigation_flow_state":"Unknown","irrigation_flow_retained":None,
        "safety_conflict_owner":"rootline_irrigation_coordinator",
        "automatic_continuation":("urgent_reverify_injector_and_parent_final_states"
            if deadline_phase=="at_or_after" or
            (parent_authoritative and parent_state=="OFF") else
            "reload_stopping_execution_and_reverify_injector_off"),
        "conflict_observed_at":now.isoformat(),
        "conflict_deadline":parent.get("native_fail_stop_deadline"),
        "native_deadline_phase":deadline_phase,
        "urgent_intervention_required":(deadline_phase=="at_or_after" or
            (parent_authoritative and parent_state=="OFF")),
        "parent_binding_mismatch":auxiliary_stop.get("parent_binding_mismatch") is True,
        "injector_stop_status":status,
        "injector_shutdown_evidence":auxiliary_stop.get("shutdown_evidence")}
    store("contain_zone",conflict)
    delivery=_notify(notify,store,"Intervention",conflict)
    return _result(conflict_status,
        commands=int(auxiliary_stop.get("hardware_commands") or 0),
        messages=delivery["confirmed"],notification=delivery,execution=conflict,
        writes_farm_data=False,degraded=True,irrigation_flow_retained=None,
        irrigation_flow_state="Unknown",parent_output_state=conflict["parent_output_state"],
        parent_output_authoritative=parent_authoritative,
        parent_off_command_withheld=True,parent_shutdown_aborted=True,
        native_deadline_phase=deadline_phase,
        urgent_intervention_required=conflict["urgent_intervention_required"],
        parent_binding_mismatch=conflict["parent_binding_mismatch"])


def _stopping_barrier_hold(active,store,notify):
    delivery=_notify(notify,store,"Intervention",{**active,
        "reason":"canonical_stopping_barrier_unproven",
        "owner_action_required":False})
    return _result("canonical_stopping_barrier_unproven",commands=0,
        messages=delivery["confirmed"],notification=delivery,
        execution=active,writes_farm_data=False,degraded=True)


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
        outcome = transport.set_state(device_id=_output_binding(execution)["device_id"], channel=execution["channel"],
                                      state="OFF",
                                      idempotency_key=f"{execution['execution_id']}:OFF:{attempt}")
        commands += 1; outcomes.append(outcome)
        store("record_off_outcome", {"execution_id": execution["execution_id"],
              "attempt": attempt, "outcome": outcome})
        if outcome.get("accepted_unambiguous") is True:
            break
    return {"commands": commands, "outcomes": outcomes}


def _degraded_hold(*, consumption_unknown=False):
    return _result("execution_store_degraded_hold", commands=0, messages=0,
        autonomous_on_enabled=False, durable_execution_truth_loaded=False,
        current_segment_consumed=None if consumption_unknown else False,
        segment_consumption_proven=not consumption_unknown, degraded=True)


def _eligible(decision, decision_id, commissioning, now):
    if not isinstance(decision, dict) or not isinstance(commissioning, dict): return False
    supplied = decision.get("decision_sha256")
    canonical = {key: value for key, value in decision.items() if key != "decision_sha256"}
    zone = decision.get("zone_id")
    try:
        output = commissioned_irrigation_contract(zone)
    except ValueError:
        return False
    assessed = _timestamp(decision.get("assessed_at"))
    artifact = validate_execution_eligibility(decision.get("execution_eligibility"), now=now)
    return (artifact is not None
            and decision.get("decision_id") == decision_id and supplied == _digest(canonical)
            and decision.get("decision") == "Run now"
            and decision.get("standing_authority") is True
            and decision.get("runtime_minutes") in range(1, MAX_MINUTES + 1)
            and assessed is not None and timedelta(0) <= now - assessed <= timedelta(minutes=15)
            and commissioning.get("zone_id") == zone
            and commissioning.get("channel") == output["channel"]
            and commissioning.get("commissioned") is True
            and decision.get("commissioning_id") == commissioning.get("commissioning_id")
            and decision.get("commissioning_generation") == commissioning.get("configuration_generation")
            and 0 < int(commissioning.get("native_inching_seconds") or 0) <= 3600
            and artifact.get("execution_id") == decision.get("execution_id")
            and artifact.get("eligibility_id") == decision.get("eligibility_id")
            and artifact.get("plan_generation") == decision.get("evidence_generation")
            and artifact.get("maximum_duration_seconds") == decision.get("runtime_seconds")
            and artifact.get("channel") == output["channel"])


def _canonical_commissioning(packet, commissioning_id, now):
    if not isinstance(packet, dict) or packet.get("commissioning_id") != commissioning_id:
        return None
    baseline = packet.get("accepted_controller_baseline")
    if isinstance(baseline, dict):
        zone = str(packet.get("zone_id") or "")
        try:
            output = commissioned_irrigation_contract(zone)
        except ValueError:
            return None
        expected = (baseline.get("irrigation_commissioning_ids") or {}).get(zone)
        validated = validate_commissioned_baseline(baseline, device_id=output["device_id"],
            firmware=str(packet.get("firmware") or ""), observed_at=now)
        if (validated and expected == commissioning_id
                and packet.get("channel") == output["channel"]
                and int(packet.get("native_inching_seconds") or 0) in range(1, 3601)):
            return {"commissioning_id": expected, "zone_id": zone,
                    "channel": output["channel"], "commissioned": True,
                    "configuration_generation": baseline["configuration_generation"],
                    "native_inching_seconds": int(packet["native_inching_seconds"])}
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


def _provider_bounded_outcome(execution, shutdown, now):
    """Prove the bounded controller segment, never crop-water delivery.

    Provider-confirmed ON, an armed native deadline, coordinator ownership
    through that deadline, and provider-confirmed OFF after it support the
    control objective.  They do not prove flow, volume, or agronomic response.
    """
    start = execution.get("start_evidence") if isinstance(execution, dict) else None
    start = start if isinstance(start, dict) else {}
    claimed = _timestamp(execution.get("claimed_at"))
    started = _timestamp(start.get("retrieved_at"))
    stopped = _timestamp(shutdown.get("retrieved_at"))
    primary = _timestamp(execution.get("primary_stop_deadline"))
    native = _timestamp(execution.get("native_fail_stop_deadline"))
    runtime_seconds = int(execution.get("planned_runtime_seconds") or 0)
    if (execution.get("state") != "Active" or execution.get("on_attempts") != 1
            or start.get("authoritative") is not True or start.get("state") != "ON"
            or shutdown.get("authoritative") is not True or shutdown.get("state") != "OFF"
            or not start.get("evidence_id") or not shutdown.get("evidence_id")
            or None in {claimed, started, stopped, primary, native}
            or not 0 < runtime_seconds <= 3599 or primary != native
            or primary != claimed + timedelta(seconds=runtime_seconds)
            or not claimed <= started < primary <= stopped <= now):
        return {}
    packet = {
        "execution_id": execution.get("execution_id"),
        "zone_id": execution.get("zone_id"), "channel": execution.get("channel"),
        "eligibility_id": execution.get("eligibility_id"),
        "evidence_generation": execution.get("evidence_generation"),
        "observed_at": stopped.isoformat(), "actual_start": started.isoformat(),
        "actual_stop": stopped.isoformat(),
        "planned_runtime_minutes": execution.get("planned_runtime_minutes"),
        "verified_runtime_minutes": runtime_seconds / 60.0,
        "shutdown_verified": True, "objective_satisfied": True,
        "start_evidence_id": start.get("evidence_id"),
        "shutdown_evidence_id": shutdown.get("evidence_id"),
        "native_fail_stop_deadline": native.isoformat(),
        "physical_flow_confirmation": "Unavailable",
        "delivered_volume": "Unavailable", "flow_rate": "Unavailable",
        "actor": "ROOTLINE_CANONICAL_OUTCOME", "provenance": "canonical_post_segment",
    }
    packet["outcome_sha256"] = _digest(packet)
    return packet


def _safe_configuration(value, zone):
    try:
        output = commissioned_irrigation_contract(zone)
    except ValueError:
        return False
    return (isinstance(value, dict) and value.get("authoritative") is True
            and value.get("zone_id") == zone and value.get("channel") == output["channel"]
            and value.get("native_inching_enabled") is True
            and int(value.get("native_inching_seconds") or 0) == 3599
            and value.get("power_restoration_state") == "OFF"
            and value.get("schedules_enabled") is False
            and value.get("interlock_enabled") is False
            and value.get("scenes_enabled") is False)


def _output_binding(execution):
    output = commissioned_irrigation_contract(execution.get("zone_id"))
    if int(execution.get("channel") or 0) != output["channel"]:
        raise ValueError("rootline_execution_channel_binding_invalid")
    return output


def _release_configuration_containment(contained, decision, store, transport):
    """Release only a proven non-command caused by missing transport config."""
    evidence = contained.get("evidence") if isinstance(contained, dict) else None
    evidence = evidence if isinstance(evidence, dict) else {}
    if (evidence.get("transport_status") != "transport_not_configured"
            or evidence.get("shutdown_verified") is not True):
        return False
    try:
        output = commissioned_irrigation_contract(decision["zone_id"])
        readiness = transport.configuration_status(
            device_id=output["device_id"], channel=output["channel"])
        safety = transport.read_safety_configuration(
            device_id=output["device_id"], channel=output["channel"])
    except Exception:
        return False
    if (not isinstance(readiness, dict) or readiness.get("configured") is not True
            or not _safe_configuration(safety, decision["zone_id"])
            or safety.get("relevant_outputs_off") is not True):
        return False
    released = store("release_zone_containment", {
        "execution_id": evidence.get("execution_id"),
        "zone_id": decision["zone_id"],
        "contained_execution_id": evidence.get("execution_id"),
        "reason": "transport_configuration_restored",
        "shutdown_verified": True,
        "controller_safety_generation": safety.get("controller_safety_generation"),
        "provider_evidence_id": safety.get("response_digest"),
    })
    return isinstance(released, dict) and released.get("success") is True


def _result(status, *, commands, messages, **extra):
    writes_farm_data = bool(extra.pop("writes_farm_data", False))
    return {"success": True, "status": status, "hardware_commands": commands,
            "telegram_messages": messages, "automatic_on_retry": False,
            "simultaneous_zones": False, "borehole_authority": False,
            "fertilizer_authority": False, "writes_farm_data": writes_farm_data,
            **extra}


def _notify(notify, store, state, payload):
    identity = f"{payload.get('execution_id')}:{state}"
    claim = store("claim_notification", {**payload,
        "notification_identity": identity, "notification_state": state})
    if not isinstance(claim, dict) or claim.get("created") is not True:
        return {"confirmed": 0, "ambiguous": False,
                "status": "replayed_noop", "provider_message_id": ""}
    try:
        delivery = notify(state, {**payload, "notification_identity": identity})
    except Exception:
        delivery = {"success": False, "status": "notification_delivery_failed"}
    delivery = delivery if isinstance(delivery, dict) else {}
    confirmed = bool(delivery.get("success") is True
                     and delivery.get("provider_delivery_confirmed") is True
                     and delivery.get("provider_message_id"))
    ambiguous = bool(delivery.get("provider_delivery_ambiguous") is True
                     or "ambiguous" in str(delivery.get("status") or ""))
    record = {**payload, "notification_identity": identity,
              "notification_state": state, "delivery_confirmed": confirmed,
              "delivery_ambiguous": ambiguous,
              "provider_message_id": str(delivery.get("provider_message_id") or "")}
    store("record_notification_delivery", record)
    return {"confirmed": int(confirmed), "ambiguous": ambiguous,
            "status": "confirmed" if confirmed else "ambiguous" if ambiguous else "failed",
            "provider_message_id": record["provider_message_id"]}


def _timestamp(value):
    try: return _aware(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
    except (TypeError, ValueError): return None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                             default=str).encode()).hexdigest()
