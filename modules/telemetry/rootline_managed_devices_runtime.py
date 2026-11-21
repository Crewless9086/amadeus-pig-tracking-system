"""Need-driven ROOTLINE device orchestration on the existing execution rails.

The recurring ROOTLINE worker admits B/C after mandatory owned-device safety.
Optional planning then considers each independently eligible device task once.
Source configuration never substitutes for a canonical ``standing_active`` device record.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import os
from time import sleep, monotonic

from modules.telemetry.rootline_cycle_budget import (
    mandatory_safety, remaining_seconds, on_deadline, RootlineCycleDeadlineExceeded,
)
from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
from modules.telemetry.rootline_device_spine import load_device_record
from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
from modules.telemetry.rootline_irrigation_execution_store import (
    RootlineExecutionStoreUnavailable, rootline_irrigation_execution_store,
)

from modules.telemetry.rootline_timed_control import timed_control_call, timed_control_enabled, canonical_timed_authority

DEVICE_KEYS = {
    "FERTILIZER-MIXER-CH2": "ifttt_ewelink:ewelink_owner_account:100204d497:2",
    "FERTILIZER-INJECTION-CH1": "ifttt_ewelink:ewelink_owner_account:100204d497:1",
}


class ManagedDevicePlanningUnavailable(Exception):
    """An optional evidence factory could not assemble its planning packet."""

    def __init__(self, result):
        super().__init__(result["status"])
        self.result = result


@timed_control_call
def run_rootline_managed_device_cycle(*, deadline_wait=None, **kwargs):
    """Supervise owned injector deadlines alongside independent device work.

    Waiting owns no database lock and does not synthesize provider reads. The
    existing work deadline leaves its existing mandatory shutdown reserve.
    """
    clock = kwargs.get("clock") or (lambda: datetime.now(timezone.utc))
    kwargs["clock"] = clock
    if deadline_wait is not None:
        kwargs["deadline_wait"] = deadline_wait
    result = _run_rootline_managed_device_cycle(**kwargs)
    # Only a just-started injector can introduce a new near deadline after the
    # inventory safety pass. Empty/mixer-only cycles retain zero extra reads.
    def started(value):
        if (value.get("status") in {"auxiliary_started", "auxiliary_on_command_accepted"}
                and (value.get("execution") or {}).get("auxiliary_device_id") == "FERTILIZER-INJECTION-CH1"):
            return value["execution"]
        return next((row for child in value.get("outcomes", [])
            if isinstance(child, dict) for row in [started(child)] if row), None)
    active = started(result)
    continuation = (_finish_injector_deadline(
        store=kwargs.get("store", rootline_irrigation_execution_store),
        transport=kwargs["transport"], clock=clock, wait=deadline_wait or sleep,
        active=active, horizon_seconds=120, require_stop=True) if active else None)
    return (_combined([result, continuation], "no_active_managed_device")
        if continuation is not None else result)


def _admit_injector_wait(delay):
    remaining_seconds(minimum=delay)
    # mandatory_safety clears the optional work deadline but deliberately
    # retains this original cycle bound. Waiting must not spend the OFF tail.
    deadline = on_deadline()
    if deadline is not None and deadline-monotonic() <= delay:
        raise RootlineCycleDeadlineExceeded("injector_wait_exceeds_cycle_budget")


def _finish_injector_deadline(*, store, transport, clock, wait, horizon_seconds=None, verify_parent=False, active=None, inventory=None, require_stop=False):
    """Do not return to a minute tick that would miss this owned deadline.

    A conflict with another known stop or exhausted work budget causes early
    OFF with partial programme credit. Native inching remains optional.
    """
    identity = "FERTILIZER-INJECTION-CH1"
    observed_transport = _AttemptedTransport(transport)
    try:
        active = active if active is not None else store("load_active_auxiliary", identity)
        if not active or active.get("stop_mode") != "scheduled":
            return None
        if (active.get("auxiliary_device_id") != identity
                or active.get("device_id") != "100204d497"
                or type(active.get("channel")) is not int or active["channel"] != 1
                or not active.get("execution_id")):
            raise RootlineExecutionStoreUnavailable("injector_deadline_identity_unproven")
        if active.get("state") != "Active":
            return None  # Existing claim/restart recovery owns these states.
        try:
            deadline = _aware(datetime.fromisoformat(str(active.get("primary_stop_deadline") or "").replace("Z", "+00:00")))
        except (ValueError, TypeError):
            return None  # Existing ambiguous-deadline recovery must still run.
        now = _aware(clock())
        delay = (_aware(deadline)-now).total_seconds()
        from modules.oom_sakkie.automatic_reassessment_scheduler import CADENCE_MINUTES
        horizon = CADENCE_MINUTES * 60 if horizon_seconds is None else horizon_seconds
        reason = None
        if delay > horizon:
            if not require_stop:
                return None
            # A newly started pulse cannot escape its same-call stop duty if
            # the wall clock reverses before the epilogue.
            reason = "injector_deadline_clock_unproven"
        if delay > 0 and reason is None:
            try:
                # Inventory and budget precede any provider observation/wait.
                # Do not postpone an earlier known duty just to verify a pulse
                # that must already stop early to preserve that duty.
                _admit_injector_wait(delay)
                others = inventory["aux"] if inventory is not None else store("load_active_auxiliaries", None)
                parent = store("load_active", None)
                borehole = inventory["borehole"] if inventory is not None else store("load_active_borehole", None)
                if inventory is not None and inventory.get("proven") is not True:
                    raise RootlineExecutionStoreUnavailable("deadline_inventory_unproven")
                if not isinstance(others, list) or any(not isinstance(row, dict) for row in others):
                    raise RootlineExecutionStoreUnavailable("deadline_inventory_unproven")
                from modules.telemetry.rootline_borehole_conditions import continuous_borehole
                for row in others + [parent, borehole]:
                    if not row or row.get("execution_id") == active["execution_id"] or continuous_borehole(row):
                        continue
                    other_deadline = datetime.fromisoformat(str(row.get("primary_stop_deadline") or "").replace("Z", "+00:00"))
                    if _aware(other_deadline) <= _aware(deadline):
                        reason = "injector_early_stop_other_owned_deadline"
                        break
            except RootlineCycleDeadlineExceeded:
                reason = "injector_early_stop_worker_budget"
            except Exception:
                reason = "injector_deadline_inventory_unproven"
        if delay > 0 and verify_parent and reason is None:
            # Preserve the existing fresh parent ON supervision before waiting.
            # This replaces the normal initial pass, rather than duplicating it.
            with mandatory_safety():
                current = advance_auxiliary_execution(eligibility={}, store=store,
                    transport=observed_transport, now=now, clock=clock,
                    auxiliary_device_id=identity, expected_execution_id=active["execution_id"],
                    expected_stop_deadline=active["primary_stop_deadline"])
            if current.get("status") not in {"auxiliary_active", "auxiliary_command_duty_active"}:
                return {**current, "managed_device": identity, "managed_device_recovery": True,
                    "blocks_bc": current.get("status") not in {
                        "auxiliary_injection_control_completed", "auxiliary_control_pulse_off_verified", "auxiliary_off_command_accepted",
                        "auxiliary_recovery_already_terminal", "auxiliary_emergency_off_verified"}}
            delay = (_aware(deadline)-_aware(clock())).total_seconds()
        if delay > 0 and reason is None:
            try:
                # Reads may consume time. Never sleep the stale original delay,
                # extend optional work, or loop on a wall-clock reversal.
                delay = max(0.0, (_aware(deadline)-_aware(clock())).total_seconds())
                _admit_injector_wait(delay)
                if delay > horizon:
                    reason = "injector_deadline_clock_unproven"
                elif delay:
                    wait(delay)
                if _aware(clock()) < _aware(deadline):
                    reason = "injector_deadline_clock_unproven"
            except RootlineCycleDeadlineExceeded:
                reason = "injector_early_stop_worker_budget"
            except Exception:
                reason = "injector_deadline_wait_unproven"
        with mandatory_safety():
            result = advance_auxiliary_execution(eligibility={}, store=store,
                transport=observed_transport, now=_aware(clock()), clock=clock,
                auxiliary_device_id=identity, expected_execution_id=active["execution_id"],
                stop_for_deadline=reason, expected_stop_deadline=active["primary_stop_deadline"])
        return {**result, "managed_device": identity, "managed_device_recovery": True,
            "blocks_bc": result.get("status") not in {
                "auxiliary_injection_control_completed", "auxiliary_control_pulse_off_verified", "auxiliary_off_command_accepted",
                "auxiliary_recovery_already_terminal", "auxiliary_emergency_off_verified"}}
    except Exception as exc:
        return {**_safe("injector_deadline_supervision_unproven", blocks_bc=True),
            "success": False, "effects_unknown": True, "managed_device": identity,
            "error_type": type(exc).__name__, "hardware_commands": observed_transport.commands}


def _run_rootline_managed_device_cycle(*, evidence, transport, environ=None,
        store=rootline_irrigation_execution_store, canonical_loader=None,
        connect_factory=None, now=None, evidence_factory=None, allow_new_starts=True,
        allow_borehole_starts=None, energy_reader=None, borehole_safety_reader=None,
        clock=None, after_safety=None, borehole_conditions_reader=None, refresh_after_safety=True,
        deadline_wait=None):
    """Supervise every owned device, then admit independent eligible work.

    The shared transaction locks serialize command edges. They do not reserve
    a global operating slot: only irrigation valves must remain sequential.
    Each auxiliary keeps its own claim, deadline, budget and containment.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _aware(now or clock())
    source = environ if environ is not None else os.environ
    if allow_borehole_starts is None:
        allow_borehole_starts = allow_new_starts
    canonical_loader = canonical_loader or _canonical_loader(connect_factory)
    deferred_no_send = {}
    def defer_no_send(execution):
        deferred_no_send[execution["execution_id"]] = (deepcopy(execution), _aware(clock()))
    safety_args = dict(store=store, transport=transport, energy_reader=energy_reader,
        borehole_safety_reader=borehole_safety_reader, clock=clock,
        borehole_conditions_reader=borehole_conditions_reader,
        defer_no_send_proof=defer_no_send if callable(after_safety) else None,
        deferred_no_send=deferred_no_send, deadline_wait=deadline_wait)
    initial = _supervise_owned_devices(**safety_args)
    outcomes = list(initial["outcomes"])
    active_aux = initial["active_aux"]
    active_borehole = initial["active_borehole"]
    active_ids = {row.get("auxiliary_device_id") for row in active_aux}
    auxiliary_inventory_proven = initial["auxiliary_inventory_proven"]
    borehole_inventory_proven = initial["borehole_inventory_proven"]
    due_this_cycle = list(initial["due_auxiliaries"])
    def refresh_safety():
        nonlocal active_borehole, auxiliary_inventory_proven, borehole_inventory_proven, initial
        current = _supervise_owned_devices(**safety_args,
            previous_borehole=initial["observed_borehole"],
            previous_due_auxiliaries=due_this_cycle)
        due_this_cycle.extend(row for row in current["due_auxiliaries"] if row not in due_this_cycle)
        outcomes.extend(current["outcomes"])
        active_ids.update(row.get("auxiliary_device_id") for row in current["active_aux"])
        active_borehole = active_borehole or current["active_borehole"]
        auxiliary_inventory_proven = auxiliary_inventory_proven and current["auxiliary_inventory_proven"]
        borehole_inventory_proven = borehole_inventory_proven and current["borehole_inventory_proven"]
        initial = current
    optional_proof_started = False
    if after_safety is not None:
        callback_completed = False
        callback_requires_refresh = True
        try:
            callback_requires_refresh = after_safety(
                _combined(outcomes, "no_active_managed_device")) is not False
            callback_completed = True
        finally:
            # A no-op callback can still follow slow mandatory reads. Preserve
            # due/unknown obligations and incomplete inventory before skipping.
            checked_at = _aware(clock())
            owned_deadline_due = any(not _before_deadline(row, checked_at)
                for row in initial["active_aux"])
            if initial["active_borehole"]:
                owned_deadline_due = owned_deadline_due or not _before_deadline(
                    initial["active_borehole"], checked_at)
            if ((refresh_after_safety and callback_requires_refresh)
                    or not callback_completed or owned_deadline_due
                    or not initial["auxiliary_inventory_proven"]
                    or not initial["borehole_inventory_proven"]
                    or any(row.get("success") is not True or row.get("effects_unknown") is True
                        for row in initial["outcomes"])):
                refresh_safety()
        # B/C may take time or overlap another canonical claim. Safety is fresh
        # before optional retirement, and again after actual optional planning.
        for execution_id in tuple(deferred_no_send):
            attempt_started = False
            try:
                remaining_seconds()
                optional_proof_started = attempt_started = True
                current = store("load_active_borehole", None)
                if (not isinstance(current, dict) or current.get("execution_id") != execution_id
                        or current.get("on_not_dispatched") is not True
                        or current.get("device_key") != "ewelink:ewelink_owner_account:1002851416:1"
                        or ("device_id" in current and current["device_id"] != "1002851416")
                        or ("channel" in current and (
                            type(current["channel"]) is not int or current["channel"] != 1))):
                    continue
                from modules.telemetry.rootline_irrigation_coordinator import _prove_unsent_execution
                from modules.telemetry.rootline_ewelink_request_budget import bind_execution_transport
                result = _prove_unsent_execution(current, store,
                    bind_execution_transport(transport, current))
                previous = [row for row in outcomes if row.get("no_send_stage") == "deferred_proof"
                    and (row.get("execution") or {}).get("execution_id") == execution_id]
                outcomes[:] = [row for row in outcomes if row not in previous]
                outcomes.append({**result, "hardware_commands": int(result.get("hardware_commands") or 0)
                    + sum(int(row.get("hardware_commands") or 0) for row in previous),
                    "managed_device": "BOREHOLE-1-MINI-R4-CH1",
                    "managed_device_recovery": True, "blocks_bc": False})
            except RootlineCycleDeadlineExceeded as exc:
                # Exhausting optional budget before any proof work is an honest
                # deferral, not failed mandatory safety or unknown B/C effects.
                outcomes.append({**_safe("no_send_optional_proof_deferred", blocks_bc=False),
                    "success": not attempt_started,
                    **({"effects_unknown": False} if not attempt_started else {}),
                    "no_send_stage": "optional_proof" if attempt_started else "optional_budget",
                    "no_send_reason": "rootline_cycle_deadline_exceeded",
                    "error_type": type(exc).__name__})
            except Exception as exc:
                outcomes.append({**_safe("no_send_optional_proof_deferred", blocks_bc=False),
                    "success": False, "error_type": type(exc).__name__})
    pending = {identity for identity, flag in (
        ("FERTILIZER-MIXER-CH2", "ROOTLINE_FERTILIZER_MIXING_ENABLED"),
        ("FERTILIZER-INJECTION-CH1", "ROOTLINE_FERTILIZER_INJECTION_ENABLED"),
        ("BOREHOLE-1-MINI-R4-CH1", "ROOTLINE_BOREHOLE_ENABLED")) if _enabled(source, flag)}
    pending -= active_ids
    if not allow_new_starts or not auxiliary_inventory_proven:
        pending -= set(DEVICE_KEYS)
    if not allow_borehole_starts or active_borehole or not borehole_inventory_proven:
        pending.discard("BOREHOLE-1-MINI-R4-CH1")

    # An idle managed pass may still owe finalization of an existing two-pulse
    # fertilizer sequence, even when every new device start is disabled. Keep
    # that predecessor path after B/C admission and within the optional budget.
    needs_evidence = bool(pending) or (allow_new_starts and not outcomes)
    planning_failure = None
    planning_started = False
    try:
        if needs_evidence:
            remaining_seconds()
            if evidence_factory is not None:
                planning_started = True
                evidence = evidence_factory(pending_devices=frozenset(pending))
            remaining_seconds()
    except ManagedDevicePlanningUnavailable as exc:
        planning_failure = exc.result
    except RootlineCycleDeadlineExceeded:
        planning_failure = {**_safe("managed_device_cycle_deadline_deferred", blocks_bc=False),
            "success": False, "next_action_owner": "ROOTLINE",
            "next_trigger": "next_authenticated_minute"}
    finally:
        if optional_proof_started or planning_started or (after_safety is None and evidence_factory is not None and needs_evidence):
            # Optional proof or even a failed factory may cross a stop deadline.
            # One final mandatory pass covers both phases, including failures.
            refresh_safety()
    if planning_failure is not None:
        return _combined(outcomes + [planning_failure], "managed_device_evidence_unavailable")
    if not allow_new_starts and not allow_borehole_starts:
        return _combined(outcomes, "no_active_managed_device")
    if (not pending and not needs_evidence
            and type(evidence) is dict and not evidence):
        # Mandatory supervision is complete. This exact empty packet has no
        # optional task or fertilizer-completion persistence left to budget.
        return _combined(outcomes, "no_eligible_managed_device_task")
    try:
        remaining_seconds()
    except RootlineCycleDeadlineExceeded:
        return _combined(outcomes + [{**_safe("managed_device_cycle_deadline_deferred", blocks_bc=False),
            "success": False, "next_action_owner": "ROOTLINE",
            "next_trigger": "next_authenticated_minute"}], "managed_device_evidence_unavailable")
    now = _aware(clock())
    packet = evidence if isinstance(evidence, dict) else {}
    progress = packet.get("fertilizer_control_progress") or {}
    if allow_new_starts and progress.get("completed") is True:
        saved = store("record_fertilizer_sequence_completed", progress)
        if not isinstance(saved, dict) or saved.get("success") is not True:
            outcomes.append({**_safe("fertilizer_sequence_persistence_unproven", blocks_bc=False),
                "success": False})
        elif saved.get("created") is True:
            outcomes.append({**_safe("fertilizer_controller_sequence_completed", blocks_bc=False),
                "writes_farm_data": True, "fertilizer_control_progress": progress})
    if not pending:
        return _combined(outcomes, "no_eligible_managed_device_task")
    tasks = packet.get("irrigation_auxiliary_tasks") or []
    contexts = packet.get("auxiliary_contexts") or {}
    safeties = packet.get("auxiliary_safety") or {}
    ordered = sorted((row for row in tasks if isinstance(row, dict)),
        key=lambda row: 0 if row.get("device_type") == "fertilizer_injection_valve" else 1)
    considered = set(active_ids)
    for task in ordered:
        identity = str(task.get("auxiliary_device_id") or "")
        if (not allow_new_starts or not auxiliary_inventory_proven or task.get("decision") != "Run now"
                or identity not in pending or identity not in DEVICE_KEYS or identity in considered):
            continue
        considered.add(identity)
        canonical = canonical_loader(DEVICE_KEYS[identity])
        if not _standing_active(canonical, identity):
            continue
        context = contexts.get(identity) if isinstance(contexts, dict) else None
        safety = safeties.get(identity) if isinstance(safeties, dict) else None
        artifact = build_auxiliary_eligibility(task=task, safety=safety,
            context=context, flags={
                "ROOTLINE_FERTILIZER_MIXING_ENABLED": _enabled(source, "ROOTLINE_FERTILIZER_MIXING_ENABLED"),
                "ROOTLINE_FERTILIZER_INJECTION_ENABLED": _enabled(source, "ROOTLINE_FERTILIZER_INJECTION_ENABLED")}, now=now)
        if artifact.get("eligible") is not True:
            continue
        if artifact.get("stop_mode")=="scheduled" and (not callable(connect_factory)
                or not canonical_timed_authority(canonical,connect_factory=connect_factory,
                    identity=identity,requested_seconds=artifact["maximum_duration_seconds"])):
            continue
        recorded = store("record_auxiliary_eligibility", artifact)
        if not isinstance(recorded, dict) or recorded.get("success") is not True:
            outcomes.append(_safe("auxiliary_eligibility_persistence_unproven", blocks_bc=False))
            continue
        result = advance_auxiliary_execution(eligibility=artifact, store=store,
            transport=transport, revalidate=lambda _artifact, value=context, selected=identity: (value
                if _artifact.get("stop_mode")!="scheduled" or canonical_timed_authority(
                    canonical_loader(DEVICE_KEYS[selected]),connect_factory=connect_factory,
                    identity=selected,requested_seconds=_artifact["maximum_duration_seconds"]) else {}),
            now=now, auxiliary_device_id=identity, clock=clock)
        outcomes.append({**result, "managed_device": identity,
            "blocks_bc": identity == "FERTILIZER-INJECTION-CH1" and result.get("status") in {"auxiliary_started", "auxiliary_on_command_accepted"}})
        if (identity == "FERTILIZER-INJECTION-CH1"
                and result.get("status") in {"auxiliary_started", "auxiliary_on_command_accepted"}
                and (result.get("execution") or {}).get("stop_mode") == "scheduled"):
            # The public wrapper now owns this pulse through OFF. Do not spend
            # its remaining window on another optional start or provider read.
            return _combined(outcomes, "no_eligible_managed_device_task")

    borehole = packet.get("borehole_execution") or {}
    if ("BOREHOLE-1-MINI-R4-CH1" in pending and allow_borehole_starts
            and borehole_inventory_proven and not active_borehole
            and isinstance(borehole, dict) and borehole.get("eligible") is True
            and _enabled(source, "ROOTLINE_BOREHOLE_ENABLED")):
        try:
            recorded = store("record_borehole_eligibility", borehole)
        except RootlineExecutionStoreUnavailable:
            recorded = None
        if not isinstance(recorded, dict) or recorded.get("success") is not True:
            outcomes.append({**_safe("borehole_eligibility_persistence_unproven", blocks_bc=False),
                "success": False})
        else:
            result = advance_borehole_execution(eligibility=borehole, store=store,
                transport=transport, now=now, clock=clock)
            outcomes.append({**result, "managed_device": "BOREHOLE-1-MINI-R4-CH1", "blocks_bc": False})
    return _combined(outcomes, "no_eligible_managed_device_task")



def _supervise_owned_devices(*, store, transport, energy_reader,
        borehole_safety_reader, clock, previous_borehole=None, previous_due_auxiliaries=(),
        borehole_conditions_reader=None,
        defer_no_send_proof=None, deferred_no_send=None, deadline_wait=None):
    # Inventory, due OFF, and durable final proof remain mandatory even when
    # the shared optional-work deadline expired. ON keeps its original fence.
    with mandatory_safety():
        return _supervise_owned_devices_unbounded(store=store, transport=transport,
            energy_reader=energy_reader, borehole_safety_reader=borehole_safety_reader,
            clock=clock, previous_borehole=previous_borehole,
            borehole_conditions_reader=borehole_conditions_reader,
            previous_due_auxiliaries=previous_due_auxiliaries,
            defer_no_send_proof=defer_no_send_proof, deferred_no_send=deferred_no_send,
            deadline_wait=deadline_wait)


def _supervise_owned_devices_unbounded(*, store, transport, energy_reader,
        borehole_safety_reader, clock, previous_borehole, previous_due_auxiliaries,
        borehole_conditions_reader=None,
        defer_no_send_proof=None, deferred_no_send=None, deadline_wait=None):
    outcomes = []
    auxiliary_inventory_proven = borehole_inventory_proven = True
    try:
        active_aux = store("load_active_auxiliaries", None)
        if (not isinstance(active_aux, list)
                or any(not isinstance(row, dict) for row in active_aux)):
            raise RootlineExecutionStoreUnavailable("active_auxiliary_inventory_unproven")
    except Exception:
        active_aux = []
        auxiliary_inventory_proven = False
        outcomes.append({**_safe("auxiliary_inventory_unproven", blocks_bc=True), "success": False})
    try:
        active_borehole = store("load_active_borehole", None)
    except Exception:
        active_borehole = None
        borehole_inventory_proven = False
        outcomes.append({**_safe("borehole_inventory_unproven", blocks_bc=False), "success": False})
    # Capture every obligation first. Failure of one device never skips another
    # device's deadline or permits a new claim for the failed device.
    due_auxiliaries = []
    deadline_results = {}
    # Reuse this mandatory inventory. An owned short injector precedes slow
    # broader provider supervision, while earlier known duties force partial
    # OFF instead of a wait. No new registry read is added to an idle cycle.
    for active in active_aux:
        if (active.get("auxiliary_device_id") == "FERTILIZER-INJECTION-CH1"
                and active.get("stop_mode") == "scheduled" and active.get("state") == "Active"
                and active not in previous_due_auxiliaries):
            # Wait admission uses the original cycle bound retained by the
            # ON deadline even inside mandatory safety.
            result = _finish_injector_deadline(store=store, transport=transport,
                clock=clock, wait=deadline_wait or sleep, horizon_seconds=120,
                verify_parent=True, active=active,
                inventory={"aux": active_aux, "borehole": active_borehole,
                    "proven": auxiliary_inventory_proven and borehole_inventory_proven})
            if result is not None:
                deadline_results[active.get("execution_id")] = result
                due_auxiliaries.append(deepcopy(active))
    for active in active_aux:
        identity = active.get("auxiliary_device_id")
        if active.get("execution_id") in deadline_results:
            outcomes.append(deadline_results[active["execution_id"]])
            continue
        observed_transport = _AttemptedTransport(transport)
        now = _aware(clock())
        try:
            if identity not in DEVICE_KEYS or not active.get("execution_id"):
                auxiliary_inventory_proven = False
                raise RootlineExecutionStoreUnavailable("auxiliary_recovery_identity_unproven")
            if active in previous_due_auxiliaries:
                # The unchanged overdue duty already received its bounded OFF
                # attempt in this pass. Keep its original failure/uncertainty;
                # another attempt belongs to the next genuine scheduler tick.
                continue
            if not _before_deadline(active, now):
                due_auxiliaries.append(deepcopy(active))
            stop_for_energy = False
            if (active.get("device_type") == "fertilizer_mixer" and energy_reader is not None
                    and _before_deadline(active, now)):
                try:
                    energy = energy_reader()
                    stop_for_energy = energy.get("mixing_continue_eligible",
                        energy.get("mixing_eligible")) is not True
                except Exception:
                    stop_for_energy = True
            result = advance_auxiliary_execution(eligibility={}, store=store,
                transport=observed_transport, now=now, stop_for_energy=stop_for_energy,
                auxiliary_device_id=identity, expected_execution_id=active.get("execution_id"), clock=clock)
        except Exception as exc:
            result = {**_safe("auxiliary_supervision_unproven", blocks_bc=True),
                "success": False, "effects_unknown": True, "error_type": type(exc).__name__,
                "hardware_commands": observed_transport.commands}
        injector_open = (identity not in DEVICE_KEYS or
            identity == "FERTILIZER-INJECTION-CH1" and result.get("status") not in {
            "auxiliary_injection_control_completed", "auxiliary_control_pulse_off_verified", "auxiliary_off_command_accepted",
            "auxiliary_recovery_already_terminal", "auxiliary_emergency_off_verified"})
        outcomes.append({**result, "managed_device": identity,
            "managed_device_recovery": True, "blocks_bc": injector_open})
    observed_borehole = None
    if active_borehole:
        observed_transport = _AttemptedTransport(transport)
        now = _aware(clock())
        try:
            continuing = _before_deadline(active_borehole, now)
            stop_for_energy = stop_for_protection = False
            from modules.telemetry.rootline_borehole_conditions import continuous_borehole
            continuous = continuous_borehole(active_borehole)
            energy_reason = "energy_stop"
            energy = {}; protection = None; protection_evidence = None
            evidence_pending = False
            try:
                energy = energy_reader() if continuing and energy_reader is not None else {}
                known = (energy.get("continuous_borehole_fresh", energy.get("borehole_fresh", energy.get("fresh")))
                    if continuous else energy.get("borehole_fresh", energy.get("fresh")))
                eligible = (energy.get("continuous_borehole_eligible", energy.get("borehole_eligible"))
                    if continuous else energy.get("borehole_eligible"))
                energy_reason = (energy.get("continuous_borehole_reason", energy.get("borehole_reason"))
                    if continuous else energy.get("borehole_reason")) or "energy_stop"
                stop_for_energy = known is True and eligible is False
                evidence_pending = continuing and energy_reader is not None and known is not True
            except Exception:
                evidence_pending = True
            try:
                protection = (borehole_safety_reader()
                    if continuing and borehole_safety_reader is not None else True)
                if isinstance(protection, dict):
                    protection_evidence = protection
                    protection = protection_evidence.get("safe")
                stop_for_protection = protection is False
                evidence_pending = evidence_pending or protection is None
            except Exception:
                evidence_pending = True
            from modules.telemetry.rootline_borehole_conditions import continuous_borehole
            condition_result = {}
            if continuous_borehole(active_borehole):
                try:
                    # Reuse only this pass's fault packet; callbacks and planning
                    # are followed by a new supervision pass and a fresh read.
                    condition_result = (borehole_conditions_reader(
                        **({"protection": protection_evidence} if protection_evidence is not None else {}))
                        if callable(borehole_conditions_reader) else {})
                    stop_for_protection = stop_for_protection or condition_result.get("stop_required") is True
                    evidence_pending = evidence_pending or condition_result.get("success") is not True
                except Exception:
                    evidence_pending = True
            # A completed observation is local to this invocation, not provider
            # evidence for another command. Still check current canonical ownership,
            # adverse evidence and the clock after those reads before omitting a
            # duplicate provider observation of the same healthy active obligation.
            already_observed = (previous_borehole is not None
                and active_borehole == previous_borehole
                and _before_deadline(active_borehole, _aware(clock()))
                and not stop_for_energy and not stop_for_protection and not evidence_pending)
            deferred = (deferred_no_send or {}).get(active_borehole.get("execution_id"))
            already_deferred = (callable(defer_no_send_proof)
                and active_borehole.get("on_not_dispatched") is True
                and isinstance(deferred, tuple) and len(deferred) == 2
                and deferred[0] == active_borehole
                and not stop_for_energy and not stop_for_protection and not evidence_pending
                and not (_before_deadline(active_borehole, deferred[1])
                    and not _before_deadline(active_borehole, _aware(clock()))))
            if already_observed or already_deferred:
                result = None
            else:
                result = advance_borehole_execution(eligibility={}, store=store,
                    transport=observed_transport, now=now,
                    stop_for_energy=stop_for_energy or stop_for_protection, clock=clock,
                    **({"stop_reason": (condition_result.get("reason") if condition_result.get("stop_required") is True
                        else energy_reason if stop_for_energy
                        else "explicit_protection_or_manual_stop"),
                        "stop_trigger": {"assessed_at": _aware(clock()).isoformat(),
                            "condition_event_id": condition_result.get("event_id"),
                            "condition_reason": condition_result.get("reason"),
                            "condition_assessed_at": condition_result.get("assessed_at"),
                            "energy_stop": stop_for_energy,
                            "energy_reason": energy_reason if stop_for_energy else None,
                            "energy_context": energy.get("borehole_energy_context"),
                            "protection_reader_safe": protection,
                            "condition_stop_required": condition_result.get("stop_required")}}
                        if stop_for_energy or stop_for_protection else {}),
                    **({"defer_no_send_proof": defer_no_send_proof} if callable(defer_no_send_proof) else {}))
                if evidence_pending:
                    result = {**result, "supervision_evidence_pending": True}
                if (result.get("status") in {"borehole_active", "borehole_command_duty_active"}
                        and result.get("success") is True
                        and result.get("supervision_evidence_pending") is not True):
                    observed_borehole = deepcopy(active_borehole)
        except Exception as exc:
            result = {**_safe("borehole_supervision_unproven", blocks_bc=False),
                "success": False, "effects_unknown": True, "error_type": type(exc).__name__,
                "hardware_commands": observed_transport.commands}
        if result is not None:
            outcomes.append({**result, "managed_device": "BOREHOLE-1-MINI-R4-CH1",
                "managed_device_recovery": True, "blocks_bc": False})
    return {"outcomes": outcomes, "active_aux": active_aux, "due_auxiliaries": due_auxiliaries,
        "active_borehole": active_borehole, "observed_borehole": observed_borehole,
        "auxiliary_inventory_proven": auxiliary_inventory_proven,
        "borehole_inventory_proven": borehole_inventory_proven}


class _AttemptedTransport:
    def __init__(self, transport):
        self.transport = transport
        self.commands = 0

    def set_state(self, **kwargs):
        self.commands += 1
        return self.transport.set_state(**kwargs)

    def __getattr__(self, name):
        return getattr(self.transport, name)


def _before_deadline(active, now):
    from modules.telemetry.rootline_borehole_conditions import continuous_borehole
    if continuous_borehole(active):
        return True
    try:
        deadline = datetime.fromisoformat(str(active.get("primary_stop_deadline") or "").replace("Z", "+00:00"))
        return now < _aware(deadline)
    except (ValueError, TypeError):
        return False

def _combined(outcomes, empty_status):
    if len(outcomes) > 1:
        outcomes = [row for row in outcomes if row.get("status") not in {
            "no_eligible_managed_device_task", "no_active_managed_device"}]
    if not outcomes:
        return _safe(empty_status, blocks_bc=False)
    if len(outcomes) == 1:
        return outcomes[0]
    return {"status": "managed_devices_advanced", "outcomes": outcomes,
        "success": all(row.get("success") is True for row in outcomes),
        "managed_device_recovery": any(row.get("managed_device_recovery") is True for row in outcomes),
        "hardware_commands": sum(int(row.get("hardware_commands") or 0) for row in outcomes),
        "writes_farm_data": any(row.get("writes_farm_data") is True for row in outcomes),
        "effects_unknown": any(row.get("effects_unknown") is True for row in outcomes),
        "blocks_bc": any(row.get("blocks_bc") is True for row in outcomes)}


def _canonical_loader(connect_factory):
    if not callable(connect_factory):
        return lambda _key: None
    def load(key):
        try:
            return load_device_record(key, connect_factory=connect_factory)
        except Exception:
            return None
    return load


def _standing_active(value, identity):
    record = value.get("device_record") if isinstance(value, dict) else None
    expected = {"FERTILIZER-MIXER-CH2": ("100204d497", 2, "independent_mixer_valve"),
        "FERTILIZER-INJECTION-CH1": ("100204d497", 1, "flow_dependent_injection_valve")}
    device_id, channel, device_type = expected[identity]
    return (isinstance(record, dict) and record.get("commissioning_stage") == "standing_active"
        and record.get("standing_authority") is True
        and record.get("device_id") == device_id and record.get("channel") == channel
        and record.get("device_type") == device_type)


def _enabled(source, key):
    return str(source.get(key) or "").strip().lower() == "true"


def _safe(status, *, blocks_bc):
    return {"success": True, "status": status, "blocks_bc": blocks_bc,
        "hardware_commands": 0, "writes_farm_data": False,
        "notify_owner": False, "managed_device_recovery": False}


def _aware(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("aware_time_required")
    return value.astimezone(timezone.utc)
