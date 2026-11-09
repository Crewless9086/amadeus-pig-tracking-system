"""Need-driven ROOTLINE device orchestration on the existing execution rails.

The recurring ROOTLINE worker admits B/C after mandatory owned-device safety.
Optional planning then considers each independently eligible device task once.
Source configuration never substitutes for a canonical ``standing_active`` device record.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import os

from modules.telemetry.rootline_cycle_budget import (
    mandatory_safety, remaining_seconds, RootlineCycleDeadlineExceeded,
)
from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution
from modules.telemetry.rootline_device_spine import load_device_record
from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
from modules.telemetry.rootline_irrigation_execution_store import (
    RootlineExecutionStoreUnavailable, rootline_irrigation_execution_store,
)

DEVICE_KEYS = {
    "FERTILIZER-MIXER-CH2": "ifttt_ewelink:ewelink_owner_account:100204d497:2",
    "FERTILIZER-INJECTION-CH1": "ifttt_ewelink:ewelink_owner_account:100204d497:1",
}


class ManagedDevicePlanningUnavailable(Exception):
    """An optional evidence factory could not assemble its planning packet."""

    def __init__(self, result):
        super().__init__(result["status"])
        self.result = result


def run_rootline_managed_device_cycle(*, evidence, transport, environ=None,
        store=rootline_irrigation_execution_store, canonical_loader=None,
        connect_factory=None, now=None, evidence_factory=None, allow_new_starts=True,
        allow_borehole_starts=None, energy_reader=None, borehole_safety_reader=None,
        clock=None, after_safety=None):
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
    safety_args = dict(store=store, transport=transport, energy_reader=energy_reader,
        borehole_safety_reader=borehole_safety_reader, clock=clock)
    initial = _supervise_owned_devices(**safety_args)
    outcomes = list(initial["outcomes"])
    active_aux = initial["active_aux"]
    active_borehole = initial["active_borehole"]
    active_ids = {row.get("auxiliary_device_id") for row in active_aux}
    auxiliary_inventory_proven = initial["auxiliary_inventory_proven"]
    borehole_inventory_proven = initial["borehole_inventory_proven"]
    if after_safety is not None:
        after_safety(_combined(outcomes, "no_active_managed_device"))
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
    try:
        if needs_evidence:
            remaining_seconds()
            if evidence_factory is not None:
                evidence = evidence_factory()
            remaining_seconds()
    except ManagedDevicePlanningUnavailable as exc:
        planning_failure = exc.result
    except RootlineCycleDeadlineExceeded:
        planning_failure = {**_safe("managed_device_cycle_deadline_deferred", blocks_bc=False),
            "success": False, "next_action_owner": "ROOTLINE",
            "next_trigger": "next_authenticated_minute"}
    finally:
        if after_safety is not None or (evidence_factory is not None and needs_evidence):
            # B/C admission and optional planning can overlap another minute's
            # claims or cross a stop deadline. Re-read ownership and supervise
            # changed/new/due duties, without recursively running the planner.
            current = _supervise_owned_devices(**safety_args,
                previous_borehole=initial["observed_borehole"],
                previous_due_auxiliaries=initial["due_auxiliaries"])
            outcomes.extend(current["outcomes"])
            active_ids.update(row.get("auxiliary_device_id") for row in current["active_aux"])
            active_borehole = active_borehole or current["active_borehole"]
            auxiliary_inventory_proven = auxiliary_inventory_proven and current["auxiliary_inventory_proven"]
            borehole_inventory_proven = borehole_inventory_proven and current["borehole_inventory_proven"]
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
        recorded = store("record_auxiliary_eligibility", artifact)
        if not isinstance(recorded, dict) or recorded.get("success") is not True:
            outcomes.append(_safe("auxiliary_eligibility_persistence_unproven", blocks_bc=False))
            continue
        result = advance_auxiliary_execution(eligibility=artifact, store=store,
            transport=transport, revalidate=lambda _artifact, value=context: value,
            now=now, auxiliary_device_id=identity, clock=clock)
        outcomes.append({**result, "managed_device": identity,
            "blocks_bc": identity == "FERTILIZER-INJECTION-CH1" and result.get("status") == "auxiliary_started"})

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
        borehole_safety_reader, clock, previous_borehole=None, previous_due_auxiliaries=()):
    # Inventory, due OFF, and durable final proof remain mandatory even when
    # the shared optional-work deadline expired. ON keeps its original fence.
    with mandatory_safety():
        return _supervise_owned_devices_unbounded(store=store, transport=transport,
            energy_reader=energy_reader, borehole_safety_reader=borehole_safety_reader,
            clock=clock, previous_borehole=previous_borehole,
            previous_due_auxiliaries=previous_due_auxiliaries)


def _supervise_owned_devices_unbounded(*, store, transport, energy_reader,
        borehole_safety_reader, clock, previous_borehole, previous_due_auxiliaries):
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
    for active in active_aux:
        identity = active.get("auxiliary_device_id")
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
            "auxiliary_injection_control_completed", "auxiliary_control_pulse_off_verified",
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
            evidence_pending = False
            try:
                energy = energy_reader() if continuing and energy_reader is not None else {}
                stop_for_energy = (energy.get("fresh") is True
                    and energy.get("borehole_eligible") is False)
                evidence_pending = continuing and energy_reader is not None and energy.get("fresh") is not True
            except Exception:
                evidence_pending = True
            try:
                protection = (borehole_safety_reader()
                    if continuing and borehole_safety_reader is not None else True)
                stop_for_protection = protection is False
                evidence_pending = evidence_pending or protection is None
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
            if already_observed:
                result = None
            else:
                result = advance_borehole_execution(eligibility={}, store=store,
                    transport=observed_transport, now=now,
                    stop_for_energy=stop_for_energy or stop_for_protection, clock=clock)
                if evidence_pending:
                    result = {**result, "supervision_evidence_pending": True}
                if (result.get("status") == "borehole_active"
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
