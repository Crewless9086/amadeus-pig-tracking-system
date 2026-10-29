"""Need-driven ROOTLINE device orchestration on the existing execution rails.

The recurring ROOTLINE worker calls this before selecting a new B/C segment.
It recovers an already-claimed auxiliary or borehole execution first, and only
then considers one freshly planned device task.  Source configuration never
substitutes for a canonical ``standing_active`` device record.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os

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
        energy_reader=None, borehole_safety_reader=None):
    """Recover or advance at most one exact managed-device execution.

    ``evidence`` is the current planner/reassessment packet.  Missing task,
    safety, need, canonical authority, or edge-revalidation evidence is a local
    no-command hold and never blocks ordinary B/C irrigation. An optional evidence
    factory is evaluated once only after canonical active recovery is excluded.
    """
    now = _aware(now or datetime.now(timezone.utc))
    source = environ if environ is not None else os.environ
    canonical_loader = canonical_loader or _canonical_loader(connect_factory)
    try:
        active_aux = store("load_active_auxiliary", None)
        active_borehole = store("load_active_borehole", None)
    except RootlineExecutionStoreUnavailable:
        return {**_safe("managed_device_store_unavailable", blocks_bc=True), "success":False}
    recovery = []
    if active_aux:
        stop_for_energy = False
        if active_aux.get("device_type") == "fertilizer_mixer" and energy_reader is not None:
            try:
                energy = energy_reader()
                stop_for_energy = energy.get("mixing_continue_eligible",energy.get("mixing_eligible")) is not True
            except Exception:
                stop_for_energy = True
        result = advance_auxiliary_execution(eligibility={}, store=store,
            transport=transport, now=now, stop_for_energy=stop_for_energy)
        recovery.append({**result, "managed_device_recovery": True, "blocks_bc": True})
    if active_borehole:
        try:
            stop_for_energy = energy_reader is not None and energy_reader().get("borehole_eligible") is not True
            stop_for_protection = borehole_safety_reader is not None and borehole_safety_reader() is not True
        except Exception:
            stop_for_energy = True; stop_for_protection = True
        result = advance_borehole_execution(eligibility={}, store=store,
            transport=transport, now=now, stop_for_energy=stop_for_energy or stop_for_protection)
        recovery.append({**result, "managed_device_recovery": True, "blocks_bc": False})
    injection_opportunity = (not active_aux and active_borehole and allow_new_starts
        and recovery[-1].get("status") == "borehole_active"
        and _enabled(source,"ROOTLINE_FERTILIZER_INJECTION_ENABLED"))
    if len(recovery) == 1 and not injection_opportunity:
        return recovery[0]
    if len(recovery) > 1:
        # Existing obligations must all receive their deadline/energy check.
        # This path cannot open another start, even for an inconsistent pair.
        return {"status":"managed_devices_supervised", "managed_device_recovery":True,
            "success":all(row.get("success") is True for row in recovery),
            "hardware_commands":sum(row.get("hardware_commands",0) for row in recovery),
            "writes_farm_data":any(row.get("writes_farm_data") is True for row in recovery),
            "blocks_bc":any(row["blocks_bc"] for row in recovery), "outcomes":recovery}

    if not allow_new_starts:
        return _safe("no_active_managed_device", blocks_bc=False)

    if evidence_factory is not None:
        try:
            evidence = evidence_factory()
        except ManagedDevicePlanningUnavailable as exc:
            return exc.result
        # Planning can take time. Recheck canonical activity before considering
        # a new start, using the existing dictionary path without another factory.
        return run_rootline_managed_device_cycle(evidence=evidence, transport=transport,
            environ=source, store=store, canonical_loader=canonical_loader,
            connect_factory=connect_factory, now=now, allow_new_starts=allow_new_starts,
            energy_reader=energy_reader, borehole_safety_reader=borehole_safety_reader)

    packet = evidence if isinstance(evidence, dict) else {}
    progress = packet.get("fertilizer_control_progress") or {}
    if progress.get("completed") is True:
        saved = store("record_fertilizer_sequence_completed", progress)
        if not isinstance(saved, dict) or saved.get("success") is not True:
            return {**_safe("fertilizer_sequence_persistence_unproven", blocks_bc=False), "success":False}
        if saved.get("created") is True:
            return {**_safe("fertilizer_controller_sequence_completed", blocks_bc=False),
                "writes_farm_data":True, "fertilizer_control_progress":progress}
    tasks = packet.get("irrigation_auxiliary_tasks") or []
    contexts = packet.get("auxiliary_contexts") or {}
    safeties = packet.get("auxiliary_safety") or {}
    # Injection is meaningful only inside an already-active irrigation segment;
    # mixer is otherwise considered first. Both remain mutually exclusive.
    ordered = sorted((row for row in tasks if isinstance(row, dict)),
        key=lambda row: 0 if row.get("device_type") == "fertilizer_injection_valve" else 1)
    for task in ordered:
        identity = str(task.get("auxiliary_device_id") or "")
        if task.get("decision") != "Run now" or identity not in DEVICE_KEYS:
            continue
        if active_borehole and identity != "FERTILIZER-INJECTION-CH1":
            continue
        canonical = canonical_loader(DEVICE_KEYS[identity])
        if not _standing_active(canonical, identity):
            continue
        context = contexts.get(identity) if isinstance(contexts, dict) else None
        safety = safeties.get(identity) if isinstance(safeties, dict) else None
        artifact = build_auxiliary_eligibility(task=task, safety=safety,
            context=context, flags={
                "ROOTLINE_FERTILIZER_MIXING_ENABLED": _enabled(
                    source, "ROOTLINE_FERTILIZER_MIXING_ENABLED"),
                "ROOTLINE_FERTILIZER_INJECTION_ENABLED": _enabled(
                    source, "ROOTLINE_FERTILIZER_INJECTION_ENABLED")}, now=now)
        if artifact.get("eligible") is not True:
            continue
        recorded = store("record_auxiliary_eligibility", artifact)
        if not isinstance(recorded, dict) or recorded.get("success") is not True:
            return _safe("auxiliary_eligibility_persistence_unproven", blocks_bc=False)
        result = advance_auxiliary_execution(eligibility=artifact, store=store,
            transport=transport,
            revalidate=lambda _artifact, value=context: value, now=now)
        return {**result, "managed_device": identity, "blocks_bc": True}

    borehole = packet.get("borehole_execution") or {}
    if (not active_borehole and isinstance(borehole, dict) and borehole.get("eligible") is True
            and _enabled(source, "ROOTLINE_BOREHOLE_ENABLED")):
        try:
            recorded = store("record_borehole_eligibility", borehole)
        except RootlineExecutionStoreUnavailable:
            recorded = None
        if not isinstance(recorded, dict) or recorded.get("success") is not True:
            return {**_safe("borehole_eligibility_persistence_unproven", blocks_bc=False),
                "success": False}
        result = advance_borehole_execution(eligibility=borehole, store=store,
            transport=transport, now=now)
        return {**result, "managed_device": "BOREHOLE-1-MINI-R4-CH1",
            "blocks_bc": False}
    return recovery[0] if recovery else _safe("no_eligible_managed_device_task", blocks_bc=False)


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
