"""Existing-scheduler composition for one canonical B/C execution artifact."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import math
import os

from modules.telemetry.rootline_execution_authority import build_execution_eligibility
from modules.telemetry.rootline_ewelink_commissioned_baseline import (
    commissioned_controller_baseline, commissioned_registered_device_baseline,
)
from modules.telemetry.rootline_device_registry import (
    commissioned_irrigation_contract, commissioned_irrigation_contracts, rootline_device_registry,
)
from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
from modules.telemetry.rootline_ewelink_readback import read_current_device
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_irrigation_coordinator import advance_irrigation_execution, _digest
from modules.telemetry.rootline_irrigation_execution_store import (
    RootlineExecutionStoreUnavailable, rootline_irrigation_execution_store,
)
from modules.telemetry.rootline_water_energy_plan import (
    ZA_TZ, build_water_energy_plan, read_current_water_energy_evidence,
)


def run_rootline_managed_device_reassessment(*, environ=None, now=None,
        database_url=None, store=rootline_irrigation_execution_store,
        token_store=None, transport=None,
        evidence_loader=read_current_water_energy_evidence, allow_new_starts=True, clock=None):
    """Supervise owned devices and advance independently eligible managed tasks.

    This composes existing planners, canonical device records and coordinators.
    Missing fertilizer-batch, active-irrigation, water-need or interlock evidence
    produces a no-command result local to the managed device.
    """
    source = environ if environ is not None else os.environ
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _aware(now or clock())
    database_url = str(database_url or source.get("DATABASE_URL") or "").strip()
    token_store = token_store or PostgresOAuthTokenStore(database_url)
    transport = transport or RootlineIFTTTTransport(
        token_store=token_store, environ=source)
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry.rootline_borehole_commissioning import (
        build_borehole_runtime_eligibility, load_registered_borehole_baseline,
    )
    from modules.telemetry.rootline_managed_devices_runtime import (
        ManagedDevicePlanningUnavailable, run_rootline_managed_device_cycle,
    )
    from modules.telemetry.rootline_energy_policy import managed_energy_decision
    power_cache = {}
    def current_energy():
        from modules.telemetry.power_service import get_current_power_state
        from modules.telemetry.rootline_water_energy_plan import _normalize_power
        if "value" not in power_cache:
            packet, status = get_current_power_state(database_url=database_url)
            power_cache["value"] = _normalize_power(packet) if status < 400 else {}
        return managed_energy_decision(power_cache["value"], now=_aware(clock()))
    def connect_factory():
        return connect_bounded_rootline_postgres(
            database_url=database_url, read_only=True)
    def current_borehole_safety():
        from modules.telemetry.rootline_water_energy_plan import read_current_borehole_faults
        return read_current_borehole_faults(database_url,now=_aware(clock()),clock=clock)
    def current_decision_time(selected):
        current = _aware(clock())
        if current.astimezone(ZA_TZ).date().isoformat() != str(selected):
            # The next normal cycle must load the new day's history and premix.
            # Supervision has already run; no new evidence cutoff is invented.
            raise ManagedDevicePlanningUnavailable({
                **_safe("managed_device_operating_date_changed"), "blocks_bc": False})
        return current
    def build_evidence():
        try:
            read_at = _aware(clock())
            evidence, selected, _planned_at = evidence_loader(
                database_url=database_url, now=read_at)
            evidence = _refresh_active_irrigation_readback(
                evidence, transport, read_at, clock=clock, only_when_due=True,
                injection_enabled=str(source.get("ROOTLINE_FERTILIZER_INJECTION_ENABLED") or "").lower() == "true")
            decision_at = current_decision_time(selected)
            plan = build_water_energy_plan(evidence, selected, now=decision_at)
        except Exception as exc:
            raise ManagedDevicePlanningUnavailable(
                {**_safe("managed_device_evidence_unavailable"), "blocks_bc": False}) from exc
        packet = {"irrigation_auxiliary_tasks": plan.get("irrigation_auxiliary_tasks") or [],
            "auxiliary_safety": {}, "auxiliary_contexts": {}}
        # Safety reads can consume time too. Assess the unchanged evidence at
        # the current clock; its observed timestamps and read cutoff stay intact.
        decision_at = current_decision_time(selected)
        executions = [row for row in evidence.get("fertilizer_executions") or []
                      if isinstance(row, dict)]
        from modules.telemetry.rootline_auxiliary_management import (
            mixing_daily_accounting, build_fertilizer_batch_lifecycle)
        batch = build_fertilizer_batch_lifecycle(
            observations=evidence.get("fertilizer_batch_observations"),
            executions=executions, now=decision_at)
        mixing = mixing_daily_accounting(executions, now=decision_at, batch=batch)
        packet["auxiliary_contexts"]["FERTILIZER-MIXER-CH2"] = {
            "plan_generation": str(plan.get("generation") or plan.get("evidence_generation") or ""),
            "batch_generation": batch["batch_generation"],
            "reserved_mixing_seconds_today": mixing["reserved_seconds"],
            "mixing_history_valid": mixing["history_valid"],
            "verified_mixing_sessions_today": mixing["sessions"],
            "mixing_history_complete_through": evidence.get("fertilizer_history_complete_through"),
            "power_suitable": managed_energy_decision(evidence.get("power"), now=decision_at)["mixing_eligible"],
        }
        active_irrigation = evidence.get("active_irrigation_context")
        if isinstance(active_irrigation, dict):
            packet["auxiliary_contexts"]["FERTILIZER-INJECTION-CH1"] = active_irrigation
            from modules.telemetry.rootline_auxiliary_management import fertilizer_control_progress
            packet["fertilizer_control_progress"] = fertilizer_control_progress(active_irrigation, now=decision_at)
        from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
        flags = {key: str(source.get(key) or "").lower() == "true" for key in (
            "ROOTLINE_FERTILIZER_MIXING_ENABLED", "ROOTLINE_FERTILIZER_INJECTION_ENABLED")}
        for task in packet["irrigation_auxiliary_tasks"]:
            identity = str(task.get("auxiliary_device_id") or "")
            if task.get("decision") != "Run now" or identity not in packet["auxiliary_contexts"]:
                continue
            preflight = build_auxiliary_eligibility(task=task, safety=None,
                context=packet["auxiliary_contexts"][identity], flags=flags,
                now=current_decision_time(selected), _provider_preflight=True)
            if preflight.get("provider_read_required") is not True:
                continue
            contract = rootline_device_registry()[identity]
            try:
                packet["auxiliary_safety"][identity] = transport.read_safety_configuration(
                    device_id=contract["device_id"], channel=contract["channel"])
            except Exception:
                continue
        borehole_task = next((row for row in plan.get("candidate_tasks") or []
            if row.get("task_id") == "borehole"), {})
        interlocks = evidence.get("borehole_interlocks") or {}
        if (borehole_task.get("recommendation") == "Recommend"
                and str(source.get("ROOTLINE_BOREHOLE_ENABLED") or "").lower() == "true"):
            try:
                baseline = load_registered_borehole_baseline(connect_factory=connect_factory)
                decision_at = current_decision_time(selected)
                if baseline:
                    from modules.telemetry.rootline_borehole_commissioning import prepare_borehole_execution_plan
                    request = dict(need={"eligible": True, "task_id": "borehole",
                            "reason": borehole_task.get("reason")}, commissioned_baseline=baseline,
                        authority={"inside_standing_authority": True}, provider={},
                        interlocks=interlocks,
                        energy={"eligible": managed_energy_decision(evidence.get("power"), now=decision_at)["borehole_eligible"]},
                        concurrency={"borehole_claim_available": True},
                        requested_seconds=min(14400, int(baseline["maximum_routine_runtime_seconds"])),
                        execution_id="PENDING", now=decision_at)
                    preflight = prepare_borehole_execution_plan(**request)
                    if any(not passed for gate, passed in preflight["gates"].items() if gate != "provider_off"):
                        packet["borehole_readiness"] = "borehole_prerequisites_unproven"
                        return packet
                    provider = transport.read_output_state(device_id="1002851416", channel=1)
                    decision_at = current_decision_time(selected)
                    packet["borehole_execution"] = build_borehole_runtime_eligibility(
                        need={"eligible": True, "task_id": "borehole",
                            "reason": borehole_task.get("reason")}, baseline=baseline,
                        authority={"inside_standing_authority": True}, provider=provider,
                        interlocks=interlocks,
                        energy={"eligible": managed_energy_decision(evidence.get("power"), now=decision_at)["borehole_eligible"]},
                        requested_seconds=min(14400,
                            int(baseline["maximum_routine_runtime_seconds"])), now=decision_at)
                else:
                    packet["borehole_readiness"] = "canonical_commissioning_required"
            except Exception:
                packet["borehole_readiness"] = "canonical_protection_evidence_unavailable"
        from modules.telemetry.rootline_energy_policy import eskom_connector_readiness
        packet["eskom_connector"] = eskom_connector_readiness(source)
        # Optional read failures cannot hide a day change from the whole packet.
        current_decision_time(selected)
        return packet

    result = run_rootline_managed_device_cycle(evidence={}, transport=transport,
        environ=source, store=store, connect_factory=connect_factory, now=now,
        evidence_factory=build_evidence, allow_new_starts=allow_new_starts,
        energy_reader=current_energy,borehole_safety_reader=current_borehole_safety,clock=clock)
    if str(source.get("ROOTLINE_ESKOM_ENABLED") or "").lower() != "true":
        return result
    from modules.telemetry.rootline_device_spine import load_device_record
    from modules.telemetry.rootline_eskom_runtime import run_eskom_cycle
    try:
        current_energy()
        canonical = load_device_record("ifttt_smartlife:smartlife_owner_account:"
            +str(source.get("ROOTLINE_ESKOM_DEVICE_ID") or "")+":1", connect_factory=connect_factory)
        grid = run_eskom_cycle(power=power_cache["value"],configuration=source,
            canonical=canonical,store=store,now=_aware(clock()),clock=clock,
            allow_new_commands=allow_new_starts)
    except Exception:
        grid = {"success":False,"status":"eskom_readiness_unavailable","hardware_commands":0}
    # Grid exceptions remain local. They do not suppress gravity irrigation.
    return {**result,"eskom":grid,
        "hardware_commands":result.get("hardware_commands",0)+grid.get("hardware_commands",0),
        "writes_farm_data":result.get("writes_farm_data") is True or grid.get("writes_farm_data") is True,
        "effects_unknown":result.get("effects_unknown") is True or grid.get("effects_unknown") is True}


def _managed_power_suitable(power, now=None):
    from modules.telemetry.rootline_energy_policy import managed_energy_decision
    return managed_energy_decision(power, now=now or datetime.now(timezone.utc))["mixing_eligible"]


def _refresh_active_irrigation_readback(evidence, transport, now, *, clock=None,
                                       only_when_due=False, injection_enabled=True):
    """Refresh only the exact canonical active B/C execution's ON evidence."""
    if not isinstance(evidence, dict):
        return evidence
    context = evidence.get("active_irrigation_context")
    if not isinstance(context, dict):
        return evidence
    # A failed fresh read must not leave historical ON evidence eligible.
    refreshed = dict(evidence); updated = dict(context)
    updated["zone_output_evidence"] = {}
    refreshed["active_irrigation_context"] = updated
    if only_when_due:
        from modules.telemetry.rootline_auxiliary_management import injection_parent_read_due
        # Disabling new pulses does not discard the final flush already owed
        # by a completed two-pulse sequence on this exact active parent.
        if ((not injection_enabled and context.get("completed_pulses") != 2)
                or not injection_parent_read_due(context, now=now)):
            return refreshed
    device_id = str(context.get("zone_device_id") or "")
    channel = context.get("zone_channel")
    if not device_id or type(channel) is not int:
        return refreshed
    try:
        from modules.telemetry.rootline_ewelink_request_budget import execution_duty
        with execution_duty({"execution_id": context.get("zone_execution_id")},
                deadline=context.get("irrigation_stop_deadline")):
            current = transport.read_output_state(device_id=device_id, channel=channel)
    except Exception:
        return refreshed
    # Production passes its independent clock. A read timestamp never advances
    # the clock or widens the future/stale evidence limits.
    checked_at = _aware((clock or (lambda: datetime.now(timezone.utc)))())
    from modules.telemetry.rootline_irrigation_lifecycle import controller_readback_time
    from modules.telemetry.rootline_ifttt_transport import irrigation_dependency_verified
    bound = {"device_id": device_id, "channel": channel,
        "execution_id": context.get("zone_execution_id"), "start_evidence": current}
    observed = controller_readback_time(bound, "start_evidence", "ON")
    if (not isinstance(current, dict) or current.get("authoritative") is not True
            or current.get("state") != "ON" or not (current.get("evidence_id")
                or current.get("response_digest")) or observed is None
            or not irrigation_dependency_verified(current, device_id=device_id,
                channel=channel, now=checked_at)):
        return refreshed
    updated["zone_output_evidence"] = {**current,
        "evidence_id": str(current.get("evidence_id") or current.get("response_digest")),
        "zone_execution_id": str(context.get("zone_execution_id") or ""),
        "observed_at": observed.isoformat()}
    refreshed["active_irrigation_context"] = updated
    return refreshed


def prepare_rootline_borehole_cycle(*, need, provider, interlocks, energy,
        requested_seconds, connect_factory, authority, now=None,
        store=rootline_irrigation_execution_store, environ=None, transport=None,
        token_store=None):
    """Advance Borehole 1 only through its exact standing-authority rail."""
    source = environ if environ is not None else os.environ
    if str(source.get("ROOTLINE_BOREHOLE_ENABLED") or "").lower() != "true":
        return {**_safe("borehole_authority_disabled"), "eligible": False}
    from modules.telemetry.rootline_borehole_commissioning import (
        advance_borehole_execution, build_borehole_runtime_eligibility,
        load_registered_borehole_baseline,
    )
    try:
        baseline = load_registered_borehole_baseline(connect_factory=connect_factory)
    except Exception:
        baseline = None
    if not baseline:
        return {**_safe("canonical_borehole_commissioning_unproven"), "eligible": False}
    artifact = build_borehole_runtime_eligibility(need=need, baseline=baseline,
        authority=authority, provider=provider, interlocks=interlocks, energy=energy,
        requested_seconds=requested_seconds, now=now)
    if artifact.get("eligible") is not True:
        return {**_safe("borehole_execution_gates_hold"),
            "execution_eligibility": artifact, "eligible": False}
    try:
        recorded = store("record_borehole_eligibility", artifact)
    except RootlineExecutionStoreUnavailable:
        return _execution_store_hold()
    if not isinstance(recorded, dict) or recorded.get("success") is not True:
        return {**_safe("borehole_eligibility_persistence_unproven"),
            "success": False, "eligible": False}
    transport = transport or RootlineIFTTTTransport(
        token_store=token_store or PostgresOAuthTokenStore(), environ=source)
    return advance_borehole_execution(eligibility=artifact, store=store,
        transport=transport, now=now)


def read_active_irrigation_weather(*, database_url, now, deadline_seconds=5):
    """Bounded canonical weather/policy reads; no provider or full-plan work."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry.rootline_bounded_read_group import run_bounded_read_group
    from modules.telemetry.rootline_operating_policy import PostgresPolicyStore, list_policy_review
    from modules.telemetry.weather_service import get_weather_control_snapshot

    def policy():
        store = PostgresPolicyStore(database_url=database_url,
            connect_factory=lambda url: connect_bounded_rootline_postgres(
                database_url=url, read_only=True))
        return list_policy_review(store=store)

    values = run_bounded_read_group({
        "weather": lambda: get_weather_control_snapshot(database_url=database_url, now=now),
        "policy": policy}, max_workers=2, deadline_seconds=deadline_seconds)
    weather, weather_status = values["weather"]
    policy, policy_status = values["policy"]
    return {"weather_snapshot": weather if weather_status < 400 else {},
            "policy_snapshot": policy if policy_status < 400 else {}}


def assess_active_irrigation_weather(packet, *, now, read_started_at=None):
    """Reassess original observation times against current versioned policy.

    This can retain or stop an already-owned execution. It never grants ON,
    replaces the admission dry interval, or treats forecast rain as current.
    """
    from modules.telemetry.rootline_daily_advisor import _active_policy_snapshot
    from modules.telemetry.weather_service import DEFAULT_WEATHER_SOURCE_ID
    now = _aware(now)
    packet = packet if isinstance(packet, dict) else {}
    snapshot = packet.get("weather_snapshot") or {}
    policy_packet = packet.get("policy_snapshot") or {}
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    policy_packet = policy_packet if isinstance(policy_packet, dict) else {}
    active_policy = policy_packet.get("active_policy")
    active_policy = active_policy if isinstance(active_policy, dict) else {}
    policy = _active_policy_snapshot(active_policy)
    current = snapshot.get("weather_current") or {}
    current = current if isinstance(current, dict) else {}
    source = current.get("source") or {}
    source = source if isinstance(source, dict) else {}
    values = current.get("current") or {}
    values = values if isinstance(values, dict) else {}
    release = snapshot.get("rain_release") or {}
    release = release if isinstance(release, dict) else {}
    flags = current.get("flags") or {}
    flags = flags if isinstance(flags, dict) else {}
    summary = current.get("summary") or {}
    summary = summary if isinstance(summary, dict) else {}
    observed = _active_weather_time(source.get("last_reading_at"))
    cutoff = _active_weather_time(snapshot.get("snapshot_cutoff"))
    activation = active_policy.get("activation") or {}
    activation = activation if isinstance(activation, dict) else {}
    effective = _active_weather_time(activation.get("effective_at"))
    rain = _active_weather_number(values.get("rain_rate_mm_h"))
    stale_minutes = _active_weather_number(source.get("stale_after_minutes"))
    live_rule = policy.get("live_rain_hold") if isinstance(policy, dict) else None
    live_rule = live_rule if isinstance(live_rule, dict) else {}
    threshold = _active_weather_number(live_rule.get("threshold_mm_per_hour"))
    proposal_digest = str(active_policy.get("proposal_sha256") or "")
    digest_valid = len(proposal_digest) == 64 and all(char in "0123456789abcdef" for char in proposal_digest)
    reason = "active_weather_dry"
    if (policy_packet.get("success") is not True or not policy or threshold is None or threshold < 0
            or not digest_valid or active_policy.get("proposal_id") != "ROOTLINE-POLICY-" + proposal_digest[:24].upper()
            or not str(activation.get("actor_identity") or "").strip()
            or type(active_policy.get("version")) is not int or active_policy["version"] < 1
            or effective is None or effective > now):
        reason = "active_weather_policy_unavailable"
    elif (snapshot.get("success") is not True or current.get("success") is not True
            or source.get("source_id") != DEFAULT_WEATHER_SOURCE_ID
            or release.get("source_id") != DEFAULT_WEATHER_SOURCE_ID
            or release.get("source") != "governed_local_weather_station"
            or observed is None or cutoff is None or not observed <= cutoff <= now
            or _active_weather_time(release.get("interval_end_at")) != observed
            or rain is None or rain < 0 or stale_minutes is None or stale_minutes <= 0):
        reason = "active_weather_unavailable"
    elif now-observed > timedelta(minutes=min(30, stale_minutes)):
        reason = "active_weather_stale"
    elif (release.get("availability") != "Available" or release.get("source_healthy") is not True
            or release.get("conflicting") is not False
            or str(summary.get("status") or "").lower() in {"offline", "error", "critical", "unavailable", "stale"}
            or any(flags.get(key) is True for key in (
                "station_stale", "telemetry_conflict", "provider_error", "source_unhealthy"))):
        reason = "active_weather_unhealthy_or_conflicting"
    elif rain > threshold:
        reason = "active_weather_rain_hold"
    material = {"contract_version": "rootline_active_weather.v1",
        "stop_required": reason != "active_weather_dry", "reason": reason,
        "assessed_at": now.isoformat(), "read_started_at": _aware(read_started_at or now).isoformat(),
        "observed_at": observed.isoformat() if observed else None,
        "snapshot_cutoff": cutoff.isoformat() if cutoff else None,
        "source_id": source.get("source_id"), "rain_rate_mm_h": rain,
        "policy_proposal_id": active_policy.get("proposal_id"),
        "policy_version": active_policy.get("version"),
        "policy_sha256": active_policy.get("proposal_sha256"),
        "threshold_mm_per_hour": threshold,
        "snapshot_sha256": _digest(packet)}
    return {**material, "evidence_sha256": _digest(material)}


def _active_weather_time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _active_weather_number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _active_weather_revalidator(reader, database_url, clock):
    def revalidate(active):
        started = _aware(clock())
        deadline = _active_weather_time(active.get("primary_stop_deadline"))
        if deadline is not None and started >= deadline:
            # The coordinator checks its clock again; due OFF never waits for IO.
            return {"stop_required": False}
        seconds = min(5.0, (deadline-started).total_seconds()) if deadline else 5.0
        try:
            packet = (reader or read_active_irrigation_weather)(
                database_url=database_url, now=started, deadline_seconds=seconds)
        except Exception:
            packet = {}
        return assess_active_irrigation_weather(packet, now=_aware(clock()), read_started_at=started)
    return revalidate


def supervise_rootline_active_execution(*, notify, environ=None, now=None,
        database_url=None, store=rootline_irrigation_execution_store,
        token_store=None, transport=None, outcome_reader=lambda _identity: None,
        readback=None, owner_user_id="", chat_id="", active_weather_reader=None, clock=None):
    """Supervise a previously claimed B/C obligation; never authorize a new ON.

    Disabling new autonomous starts does not abandon canonical shutdown duties.
    The coordinator reads the active identity once, and its active-only barrier
    cannot fall through to eligibility, claiming or a new segment.
    """
    source = environ if environ is not None else os.environ
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _aware(now or clock())
    canonical_url = str(database_url or source.get("DATABASE_URL") or "").strip()
    weather_revalidator = _active_weather_revalidator(active_weather_reader, canonical_url, clock)
    if not owner_user_id or owner_user_id != chat_id:
        return {**_safe("active_supervision_owner_binding_invalid"), "success": False,
                "active_execution_found": None}
    effects = {"hardware_commands": 0, "telegram_sends": 0,
               "active_supervision_write_attempted": False}
    def current_transport():
        nonlocal transport
        if transport is None:
            canonical_url = str(database_url or source.get("DATABASE_URL") or "").strip()
            transport = RootlineIFTTTTransport(
                token_store=token_store or PostgresOAuthTokenStore(canonical_url),
                environ=source, readback=readback)
        return transport

    class StopOnlyTransport:
        def set_state(self, **kwargs):
            if kwargs.get("state") != "OFF":
                raise ValueError("active_supervision_forbids_on")
            adapter = current_transport()
            effects["hardware_commands"] += 1
            return adapter.set_state(**kwargs)

        def read_output_state(self, **kwargs):
            return current_transport().read_output_state(**kwargs)

    active_found = None
    def tracked_store(action, payload):
        nonlocal active_found
        if not action.startswith("load_"):
            effects["active_supervision_write_attempted"] = True
        result = store(action, payload)
        if action == "load_active":
            active_found = bool(result)
        return result

    def tracked_notify(state, execution):
        delivery = notify(state, execution)
        if isinstance(delivery, dict):
            effects["telegram_sends"] += int(delivery.get("telegram_sends") or
                (delivery.get("provider_delivery_confirmed") is True))
        return delivery

    try:
        result = advance_irrigation_execution(decision_id="", commissioning_id="",
            decision_reader=lambda _identity: {}, commissioning_reader=lambda _identity: {},
            store=tracked_store, transport=StopOnlyTransport(), notify=tracked_notify,
            outcome_reader=outcome_reader, now=now, active_only=True, clock=clock,
            active_weather_revalidator=weather_revalidator)
    except Exception as exc:
        # OFF or a durable write may already have happened. Preserve attempted
        # effects and uncertainty; never report a clean zero-effect failure.
        return {**_safe("active_irrigation_supervision_unproven"), "success": False,
            "error_type": type(exc).__name__, "active_execution_found": active_found,
            **effects, "writes_farm_data": None if effects["active_supervision_write_attempted"] else False,
            "write_state": "unknown" if effects["active_supervision_write_attempted"] else "none",
            "provider_effects_unknown": effects["hardware_commands"] > 0,
            "recovery_required": True}
    return {**result, "active_execution_found": active_found,
        "success": result.get("success") is True and result.get("status") in {
            "no_active_irrigation", "active_segment_owned", "segment_completed",
            "segment_stopped_outcome_unconfirmed", "segment_stopped_for_weather",
            "active_execution_already_terminal", "interrupted_start_contained"},
        "hardware_commands": max(int(result.get("hardware_commands") or 0), effects["hardware_commands"]),
        "telegram_sends": max(int(result.get("telegram_messages") or 0), effects["telegram_sends"]),
        "active_supervision_write_attempted": effects["active_supervision_write_attempted"]}


def run_rootline_execution_cycle(*, notify, environ=None, now=None, database_url=None,
                                 store=rootline_irrigation_execution_store,
                                 token_store=None, transport=None,
                                 outcome_reader=lambda _identity: None,
                                 evidence_loader=read_current_water_energy_evidence,
                                 readback=read_current_device, clock=None,
                                 owner_user_id="", chat_id="", next_reassessment_at="",
                                 observation_store=None, expected_artifact=None,
                                 authority_checker=None, active_weather_reader=None):
    source = environ if environ is not None else os.environ
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _aware(now or clock())
    if str(source.get("ROOTLINE_AUTONOMOUS_BC_ENABLED") or "").lower() != "true":
        return _safe("autonomous_bc_disabled")
    token_store = token_store or PostgresOAuthTokenStore(database_url)
    transport = transport or RootlineIFTTTTransport(
        token_store=token_store, environ=source, readback=readback)
    try:
        active = store("load_active", None)
    except RootlineExecutionStoreUnavailable:
        return _execution_store_hold()
    if active:
        return advance_irrigation_execution(decision_id="", commissioning_id="",
            decision_reader=lambda _identity: {}, commissioning_reader=lambda _identity: {},
            store=store, transport=transport, notify=notify,
            outcome_reader=outcome_reader, now=now, clock=clock, active_only=True,
            active_weather_revalidator=_active_weather_revalidator(active_weather_reader,
                str(database_url or source.get("DATABASE_URL") or "").strip(), clock))
    if not owner_user_id or owner_user_id != chat_id:
        return _safe("canonical_observation_binding_invalid")
    initial = _current(evidence_loader, readback, token_store, source, database_url, now, store,
        require_enabled=True, clock=clock)
    observation = _planning_observation(initial, owner_user_id, chat_id,
                                        next_reassessment_at)
    if observation_store is None:
        from modules.oom_sakkie.rootline_reassessment_store import rootline_reassessment_state_store
        observation_store = rootline_reassessment_state_store
    recorded = observation_store("record_observation", observation["identity"], observation)
    if not isinstance(recorded, dict) or recorded.get("success") is not True:
        return {**_safe("canonical_observation_persistence_unproven"), "success": False}
    artifact = initial["artifact"]
    if expected_artifact is not None and not _same_delegated_execution(
            expected_artifact, artifact):
        return _safe("delegated_execution_eligibility_changed")
    if artifact.get("eligible") is not True:
        blocked = _technical_block_alert(initial, artifact, store, notify,
                                         next_reassessment_at)
        return {**_safe(artifact.get("status") or "not_eligible"),
                "execution_eligibility": artifact, **blocked}
    canonical_database_url = str(database_url or source.get("DATABASE_URL") or "").strip()
    authority_checker = authority_checker or _canonical_standing_authority_proven
    if not authority_checker(canonical_database_url, artifact):
        return {**_safe("canonical_standing_authority_unproven"),
                "execution_eligibility": {**artifact, "eligible": False,
                    "command_authority": False, "hardware_control": False}}
    try:
        stored = store("record_eligibility", artifact)
    except RootlineExecutionStoreUnavailable:
        return _execution_store_hold()
    if not isinstance(stored, dict) or stored.get("success") is not True:
        return {**_safe("eligibility_persistence_unproven"), "success": False}
    zone = artifact["zone_id"]
    output, baseline, commissioning_id = _commissioned_output(zone)
    decision = {"decision_id": "ROOTLINE-DECISION-" + artifact["eligibility_sha256"][:24].upper(),
        "decision": "Run now", "standing_authority": True, "zone_id": zone,
        "runtime_minutes": max(1, (artifact["maximum_duration_seconds"] + 59) // 60),
        "runtime_seconds": artifact["maximum_duration_seconds"],
        "execution_id": artifact["execution_id"], "eligibility_id": artifact["eligibility_id"],
        "evidence_generation": artifact["plan_generation"],
        "assessed_at": artifact["decision_at"], "commissioning_id": commissioning_id,
        "commissioning_generation": baseline["configuration_generation"],
        "execution_eligibility": artifact}
    decision["decision_sha256"] = _digest(decision)
    selected = next(row for row in initial["controller"]["channels"]
                    if row["channel"] == artifact["channel"])
    commissioning = {"commissioning_id": commissioning_id, "zone_id": zone,
        "channel": artifact["channel"], "firmware": initial["controller"]["firmware"],
        "native_inching_seconds": selected["native_auto_off_seconds"],
        "accepted_controller_baseline": baseline}
    def revalidate(_decision):
        current_now = _aware(clock())
        return _current(evidence_loader, readback, token_store, source,
                        database_url, current_now, store, require_enabled=True, clock=clock)["artifact"]
    return advance_irrigation_execution(decision_id=decision["decision_id"],
        commissioning_id=commissioning_id, decision_reader=lambda _identity: decision,
        commissioning_reader=lambda _identity: commissioning, store=store,
        transport=transport, notify=notify, outcome_reader=outcome_reader,
        eligibility_revalidator=revalidate, now=_aware(clock()), clock=clock)


def _same_delegated_execution(expected, current):
    """Bind a delegated caller to the exact freshly rebuilt segment authority."""
    keys = ("contract_version", "authority_source", "job_id", "job_sha256",
        "zone_id", "channel", "segment_identity", "current_segment",
        "segment_requested_seconds", "requested_total_duration_seconds",
        "governed_executable_duration_seconds", "expected_segment_count",
        "plan_generation", "source_plan_generation", "consumption_key")
    return (isinstance(expected, dict) and isinstance(current, dict)
        and expected.get("eligible") is True and current.get("eligible") is True
        and all(expected.get(key) == current.get(key) for key in keys))


def run_protected_rootline_segment(*, expected_artifact, notify, environ=None,
        now=None, database_url=None, store=rootline_irrigation_execution_store,
        token_store=None, transport=None, outcome_reader=lambda _identity: None,
        evidence_loader=read_current_water_energy_evidence, readback=read_current_device,
        clock=None, owner_user_id="", chat_id="", active_weather_reader=None):
    """Execute one owner-confirmed segment through the existing coordinator.

    This is not standing autonomy: the protected claim is the sole authority and
    the complete eligibility artifact must be rebuilt immediately before claim.
    """
    source=environ if environ is not None else os.environ
    clock=clock or (lambda: datetime.now(timezone.utc)); now=_aware(now or clock())
    if not owner_user_id or owner_user_id!=chat_id:
        return _safe("protected_owner_binding_invalid")
    try:
        expected_output = commissioned_irrigation_contract(expected_artifact.get("zone_id"))
    except ValueError:
        return _safe("protected_irrigation_boundary_invalid")
    if (expected_artifact.get("channel") != expected_output["channel"]
        or int(expected_artifact.get("current_segment") or 0) < 1
        or int(expected_artifact.get("segment_requested_seconds") or 0) not in range(1, 3600)
        or int(expected_artifact.get("requested_total_duration_seconds") or 0) < 1
        or int(expected_artifact.get("governed_executable_duration_seconds") or 0) < 1
        or int(expected_artifact.get("expected_segment_count") or 0) < 1):
        return _safe("protected_irrigation_boundary_invalid")
    token_store=token_store or PostgresOAuthTokenStore(database_url)
    try:
        active=store("load_active",None)
    except RootlineExecutionStoreUnavailable:
        return _execution_store_hold()
    if active:
        active_binding={
          "job_id":active.get("job_id"),"job_sha256":active.get("job_sha256"),
          "zone_id":active.get("zone_id"),"channel":active.get("channel"),
          "segment_identity":active.get("segment_identity"),
          "current_segment":active.get("current_segment"),
          "segment_requested_seconds":active.get("segment_requested_seconds"),
          "requested_total_duration_seconds":active.get("requested_total_duration_seconds"),
          "governed_executable_duration_seconds":active.get("governed_executable_duration_seconds"),
          "plan_generation":active.get("evidence_generation"),
          "controller_safety_generation":active.get("controller_safety_generation")}
        if any(active_binding.get(k)!=expected_artifact.get(k) for k in active_binding):
            return _safe("active_execution_conflicts_with_protected_claim")
        transport=transport or RootlineIFTTTTransport(token_store=token_store,environ=source,readback=readback)
        return advance_irrigation_execution(decision_id="",commissioning_id="",
          decision_reader=lambda _identity:{},commissioning_reader=lambda _identity:{},
          store=store,transport=transport,notify=notify,outcome_reader=outcome_reader,
          now=now,clock=clock,active_only=True,
          active_weather_revalidator=_active_weather_revalidator(active_weather_reader,
              str(database_url or source.get("DATABASE_URL") or "").strip(),clock))
    try:
        current=_current(evidence_loader,readback,token_store,source,database_url,now,store,clock=clock)
    except RootlineExecutionStoreUnavailable:
        return _execution_store_hold()
    artifact=current["artifact"]
    # A mandatory fresh provider read produces a new response/eligibility digest.
    # Bind the immutable governed job and segment here; the fresh artifact itself
    # remains fully validated and becomes the sole coordinator authority below.
    bound_keys=("job_id","job_sha256","zone_id","channel","segment_identity",
      "current_segment","segment_requested_seconds","requested_total_duration_seconds",
      "governed_executable_duration_seconds","plan_generation",
      "controller_safety_generation")
    if (artifact.get("eligible") is not True or artifact.get("current_segment")!=1
            or any(artifact.get(k)!=expected_artifact.get(k) for k in bound_keys)):
        return _safe("protected_irrigation_eligibility_changed")
    try:
        stored=store("record_eligibility",artifact)
    except RootlineExecutionStoreUnavailable:
        return _execution_store_hold()
    if not isinstance(stored,dict) or stored.get("success") is not True:
        return {**_safe("eligibility_persistence_unproven"),"success":False}
    zone=artifact["zone_id"]
    _output,baseline,commissioning_id=_commissioned_output(zone)
    decision={"decision_id":"ROOTLINE-DECISION-"+artifact["eligibility_sha256"][:24].upper(),
      "decision":"Run now","standing_authority":True,"zone_id":zone,
      "runtime_minutes":60,"runtime_seconds":artifact["maximum_duration_seconds"],
      "execution_id":artifact["execution_id"],"eligibility_id":artifact["eligibility_id"],
      "evidence_generation":artifact["plan_generation"],"assessed_at":artifact["decision_at"],
      "commissioning_id":commissioning_id,"commissioning_generation":baseline["configuration_generation"],
      "execution_eligibility":artifact}
    decision["decision_sha256"]=_digest(decision)
    selected=next(row for row in current["controller"]["channels"] if row["channel"]==artifact["channel"])
    commissioning={"commissioning_id":commissioning_id,"zone_id":zone,"channel":artifact["channel"],
      "firmware":current["controller"]["firmware"],"native_inching_seconds":selected["native_auto_off_seconds"],
      "accepted_controller_baseline":baseline}
    transport=transport or RootlineIFTTTTransport(token_store=token_store,environ=source,readback=readback)
    def revalidate(_decision):
        return _current(evidence_loader,readback,token_store,source,database_url,
          _aware(clock()),store,clock=clock)["artifact"]
    return advance_irrigation_execution(decision_id=decision["decision_id"],
      commissioning_id=commissioning_id,decision_reader=lambda _identity:decision,
      commissioning_reader=lambda _identity:commissioning,store=store,transport=transport,
      notify=notify,outcome_reader=outcome_reader,eligibility_revalidator=revalidate,
      now=_aware(clock()),clock=clock)


def _current(evidence_loader, readback, token_store, source, database_url, now,
             store=rootline_irrigation_execution_store, *, require_enabled=False, clock=None):
    try:
        from modules.telemetry.rootline_bounded_read_group import (
            RootlineReadGroupDeadlineExceeded,
        )
        evidence, operating_date, generated_at = evidence_loader(
            database_url=database_url,now=now)
    except Exception as exc:
        if isinstance(exc, RootlineReadGroupDeadlineExceeded):
            raise RootlineExecutionStoreUnavailable(
                "load_current_water_energy_evidence") from exc
        raise
    history = evidence.get("irrigation_history") if isinstance(evidence, dict) else None
    if ((isinstance(history, dict) and history.get("status") == "Unavailable")
            or (isinstance(evidence, dict) and evidence.get("database_read_failures"))):
        raise RootlineExecutionStoreUnavailable("load_canonical_irrigation_history")
    plan = build_water_energy_plan(evidence, operating_date, now=generated_at)
    _persist_stale_parent_resolutions(plan, store)
    eligibility_args = dict(plan=plan, evidence=evidence,
        job_event_reader=lambda job_id: store("load_job_events", job_id),
        zone_containment_reader=lambda zone_id: store("load_zone_containment", zone_id),
        enabled_zone_ids=commissioned_irrigation_contracts(environ=source) if require_enabled else None)
    artifact = build_execution_eligibility(**eligibility_args, controller=None,
        now=now, _provider_preflight=True)
    controller = {}
    if artifact.get("provider_read_required") is True:
        controller = readback(token_store=token_store, environ=source, now=now)
        # Evaluate original evidence at the independent post-I/O clock. Never
        # refresh a weather/history timestamp merely because a request finished.
        checked_at = _aware((clock or (lambda: datetime.now(timezone.utc)))())
        artifact = build_execution_eligibility(**eligibility_args,
            controller=controller, now=checked_at)
    resolution = artifact.get("job_resolution") if isinstance(artifact, dict) else None
    if isinstance(resolution, dict):
        recorded = store("record_job_resolution", resolution)
        if not isinstance(recorded, dict) or recorded.get("success") is not True:
            raise RootlineExecutionStoreUnavailable("record_job_resolution")
    return {"evidence": evidence, "plan": plan, "controller": controller,
            "operating_date": str(operating_date), "generated_at": generated_at,
            "artifact": artifact}


def _persist_stale_parent_resolutions(plan, store):
    for task in (plan.get("candidate_tasks") or []):
        if not isinstance(task, dict):
            continue
        deferred = [*((parent, True) for parent in
            (task.get("stale_incomplete_parent_jobs") or [])),
            *((parent, False) for parent in (task.get("contained_parent_jobs") or []))]
        for parent, terminal in deferred:
            job = parent.get("job") if isinstance(parent, dict) else None
            projection = parent.get("projection") if isinstance(parent, dict) else None
            if not isinstance(job, dict) or not isinstance(projection, dict):
                raise RootlineExecutionStoreUnavailable("stale_parent_job_invalid")
            material = {"contract_version": "rootline_irrigation_job_resolution.v1",
                "resolution": "Deferred", "job_id": job.get("job_id"),
                "job_sha256": job.get("job_sha256"), "zone_id": job.get("zone_id"),
                "operating_date": job.get("operating_date"),
                "current_segment": projection.get("current_segment"),
                "expected_segment_count": job.get("expected_segment_count"),
                "cumulative_verified_runtime_seconds": projection.get(
                    "cumulative_verified_runtime_seconds"),
                "remaining_seconds": parent.get("remaining_seconds"),
                "reason": str(parent.get("resolution_reason") or
                    "parent_operating_date_elapsed_before_remaining_objective_completed")}
            if terminal:
                material["terminal"] = True
            else:
                material["source_plan_generation"] = plan.get("evidence_generation")
            digest = _digest(material)
            result = store("record_job_resolution", {**material,
                "resolution_sha256": digest,
                "execution_id": "ROOTLINE-JOB-RESOLUTION-" + digest[:24].upper()})
            if not isinstance(result, dict) or result.get("success") is not True:
                raise RootlineExecutionStoreUnavailable("record_stale_job_resolution")


def _commissioned_output(zone):
    output = commissioned_irrigation_contract(zone)
    baseline = commissioned_registered_device_baseline(output["device_id"])
    identities = ((baseline or {}).get("irrigation_commissioning_ids") or {})
    commissioning_id = identities.get(zone)
    if (not baseline or baseline.get("revoked") is not False
            or commissioning_id != output.get("commissioning_id")
            or baseline.get("configuration_generation") !=
               output.get("commissioning_generation")):
        raise ValueError("rootline_irrigation_commissioning_binding_invalid")
    return output, baseline, commissioning_id


def _canonical_standing_authority_proven(database_url, artifact):
    """Resolve the complete B/C evidence and explicit policy contract, or fail closed."""
    if not str(database_url or "").strip():
        return False
    try:
        import psycopg
        from modules.telemetry.rootline_device_spine import load_device_record
        def connect():
            return psycopg.connect(database_url, connect_timeout=10,
                options="-c default_transaction_read_only=on")
        keys = (
            "ifttt_ewelink:ewelink_owner_account:100204e9bc:1",
            "ifttt_ewelink:ewelink_owner_account:100204e9bc:2",
        )
        records = [load_device_record(key, connect_factory=connect)["device_record"]
                   for key in keys]
        if any(record.get("standing_authority") is not True or
               record.get("commissioning_stage") != "standing_active"
               for record in records):
            return False
        selected_zone = str((artifact or {}).get("zone_id") or "")
        selected_channel = (artifact or {}).get("channel")
        expected = {"B12345": 1, "C12345": 2}
        selected = next((record for record in records
            if record.get("channel") == expected.get(selected_zone)), None)
        if (selected is None or selected_channel != expected.get(selected_zone)
                or selected.get("provider") != "ifttt_ewelink"
                or selected.get("provider_account_binding") != "ewelink_owner_account"
                or selected.get("device_id") != "100204e9bc"
                or selected.get("physical_effect") != selected_zone + " irrigation water flow"
                or selected.get("native_fail_stop_seconds") != 3599
                or selected.get("maximum_runtime_seconds") != 3599):
            return False
        envelopes = [record.get("authority_envelope") or {} for record in records]
        if len({(item.get("standing_authority_id"), item.get("version"))
                for item in envelopes}) != 1:
            return False
        with connect() as connection:
            with connection.cursor() as cursor:
                envelope = envelopes[0]
                cursor.execute("""select issuer,policy_payload,policy_sha256,active,revoked,
                    not exists(select 1 from app_private.rootline_authority_events e where
                      e.standing_authority_id=%s and e.version=%s and
                      e.event_type in ('revoked','superseded')) from
                    app_private.rootline_standing_authorities where
                    standing_authority_id=%s and version=%s""",
                    (envelope.get("standing_authority_id"), envelope.get("version"),
                     envelope.get("standing_authority_id"), envelope.get("version")))
                row = cursor.fetchone()
        if (not row or str(row[0]) != str(envelope.get("issuer") or "")
                or row[3] is not True or row[4] is True or row[5] is not True
                or str(row[2]) != str(envelope.get("policy_sha256") or "")):
            return False
        policy = row[1] if isinstance(row[1], dict) else {}
        return _bc_authority_policy_proven(policy, artifact, keys)
    except Exception:
        return False


def _bc_authority_policy_proven(policy, artifact, keys):
    """Validate the exact, scope-preserving B/C standing-authority policy."""
    return (policy.get("contract_version") == "rootline_bc_standing_authority.v2"
            and set(policy.get("device_keys") or ()) == set(keys)
            and set(policy.get("zone_ids") or ()) == {"B12345", "C12345"}
            and set(policy.get("allowed_channels") or ()) == {1, 2}
            and policy.get("provider") == "ifttt_ewelink"
            and policy.get("provider_account_binding") == "ewelink_owner_account"
            and policy.get("device_id") == "100204e9bc"
            and type(policy.get("maximum_runtime_seconds")) is int
            and 0 < policy["maximum_runtime_seconds"] <= 3599
            and type((artifact or {}).get("maximum_duration_seconds")) is int
            and 0 < artifact["maximum_duration_seconds"] <= policy["maximum_runtime_seconds"]
            and policy.get("simultaneous_outputs_allowed") is False
            and policy.get("mutual_exclusion_required") is True
            and policy.get("missing_or_stale_reservoir_observation_is_hold") is False
            and policy.get("fresh_adverse_reservoir_evidence_is_hold") is True
            and policy.get("unproven_reservoir_water_credit_litres") == 0
            and policy.get("fresh_weather_and_rain_hold_required") is True
            and policy.get("current_plan_identity_required") is True
            and policy.get("application_timeout_required") is True
            and policy.get("provider_on_off_readback_required") is True
            and set(policy.get("explicit_exclusions") or ()) == {
                "fertilizer_injection", "fertilizer_mixing", "borehole_pump"}
            and bool(str(policy.get("emergency_off_owner") or "").strip())
            and bool(str(policy.get("emergency_off_procedure") or "").strip())
            and policy.get("provider_fail_stop_proven") is True
            and policy.get("physical_fail_safe_proven") is True
            and policy.get("power_restoration_off_proven") is True
            and policy.get("automatic_on_retry") is False)


def _safe(status):
    return {"success": True, "status": status, "hardware_commands": 0,
            "telegram_messages": 0, "writes_farm_data": False,
            "borehole_authority": False, "fertilizer_authority": False}


def _execution_store_hold():
    return {**_safe("execution_store_degraded_hold"),
            "autonomous_on_enabled": False,
            "durable_execution_truth_loaded": False,
            "current_segment_consumed": False,
            "degraded": True}


def _planning_observation(initial, owner, chat, next_due):
    if not owner or owner != chat:
        return None
    plan, evidence = initial["plan"], initial["evidence"]
    operating_date = str(initial.get("operating_date") or evidence.get("operating_date")
                         or plan.get("operating_date") or "")
    generation = str(plan.get("evidence_generation") or "")
    cutoff = str((evidence.get("weather") or {}).get("observed_at") or "")
    tasks = {str(row.get("task_id") or "").removeprefix("irrigation_"): row
             for row in plan.get("candidate_tasks") or [] if isinstance(row, dict)}
    from modules.telemetry.rootline_irrigation_lifecycle import project_zone_lifecycle
    history = evidence.get("irrigation_history") or {}
    histories = history.get("zones") or {}
    zones = []
    zone_ids = sorted(identity for identity, row in rootline_device_registry().items()
        if row.get("collection")=="irrigation_zones"
        and row.get("commissioned") is True)
    for zone in zone_ids:
        task = tasks.get(zone, {})
        raw = str(task.get("zone_decision") or "Needs Data")
        decision = ("Not Due" if raw == "Completed" else raw
                    if raw in {"Run now", "Run later", "Hold", "Needs Data", "Not Due"}
                    else "Needs Data")
        artifact = initial["artifact"]
        per_zone = (artifact.get("zone_eligibility_reasons")
                    if isinstance(artifact.get("zone_eligibility_reasons"), dict) else {})
        if artifact.get("eligible") is True and artifact.get("zone_id") == zone:
            blocker = ""
        elif artifact.get("status") == "durable_parent_job_deferred" and decision == "Run now":
            blocker = str(per_zone.get(zone) or "run_projection_eligibility_invariant_failed")
            if blocker == "eligible_candidate":
                blocker = "run_projection_eligibility_invariant_failed"
        else:
            blocker = str(per_zone.get(zone) or artifact.get("status") or "")
        zones.append({"zone_id": zone, "decision": "Run" if decision == "Run now" else decision,
            "zone_decision": raw,
            "reason": str(task.get("reason") or artifact.get("status") or
                          "No canonical zone task is available."),
            "planned_duration_minutes": task.get("planned_duration_minutes"),
            "feasible_window": task.get("preferred_window"),
            "eligibility_blocker": blocker,
            "lifecycle": project_zone_lifecycle(zone_id=zone, recommendation=task,
                history=histories.get(zone),
                execution=(histories.get(zone) or {}).get("latest_execution"),
                eligibility=artifact if artifact.get("zone_id") == zone else {},
                evidence_cutoff=history.get("snapshot_cutoff"))})
    material = {"operating_date": operating_date, "generation": generation,
                "evidence_cutoff": cutoff, "zones": zones}
    digest = _digest(material)
    identity_material = f"{owner}|{chat}|{operating_date}|{generation}|{cutoff}|{digest}"
    identity = "OOM-ROOTLINE-OBS-" + hashlib.sha256(identity_material.encode()).hexdigest()[:24].upper()
    return {"identity": identity, "owner_user_id": owner, "chat_id": chat,
        "operating_date": operating_date, "material_digest": digest,
        "result_id": str(plan.get("plan_identity") or generation),
        "evidence_generation": generation, "evidence_cutoff": cutoff,
        "next_reassessment_at": str(next_due or ""), "zones": zones,
        "delivery_state": "observation_only"}


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _technical_block_alert(initial, artifact, store, notify, next_due):
    blocker = str(artifact.get("status") or "")
    technical = {"controller_safety_not_dispatchable"}
    candidates = [row for row in initial["plan"].get("candidate_tasks") or []
                  if isinstance(row, dict) and row.get("zone_decision") == "Run now"]
    if blocker not in technical or not candidates:
        return {"telegram_messages": 0}
    task = min(candidates, key=lambda row: (int(row.get("rank") or 999), str(row.get("task_id") or "")))
    zone = str(task.get("task_id") or "").removeprefix("irrigation_")
    identity = "ROOTLINE-BLOCKED-" + _digest({"zone": zone, "blocker": blocker,
        "generation": initial["plan"].get("evidence_generation")})[:24].upper()
    payload = {"execution_id": identity, "zone_id": zone,
        "notification_state": "Blocked", "blocker": blocker,
        "owner_action_required": False, "next_reassessment_at": str(next_due or "")}
    claim = store("claim_notification", payload)
    if not isinstance(claim, dict) or claim.get("success") is not True or claim.get("created") is False:
        return {"telegram_messages": 0, "blocked_notification_identity": identity}
    try:
        delivery = notify("Blocked", payload)
        delivery = delivery if isinstance(delivery, dict) else {}
        provider_id = str(delivery.get("provider_message_id") or "")
        confirmed = delivery.get("provider_delivery_confirmed") is True and bool(provider_id)
        ambiguous = delivery.get("provider_delivery_ambiguous") is True
        outcome = "confirmed" if confirmed else "ambiguous" if ambiguous else "failed"
    except Exception:
        delivery = {}; confirmed = False; ambiguous = False; outcome = "failed"
    persisted = store("record_notification_delivery", {**payload, "delivery_confirmed": confirmed,
        "delivery_ambiguous": ambiguous, "delivery_outcome": outcome,
        "provider_message_id": str(delivery.get("provider_message_id") or "")})
    if not isinstance(persisted, dict) or persisted.get("success") is not True:
        return {"telegram_messages": 0, "blocked_notification_identity": identity,
                "success": False, "blocked_notification_confirmed": False,
                "blocked_notification_outcome": "persistence_unproven",
                "status": "blocked_notification_persistence_unproven"}
    return {"telegram_messages": int(confirmed), "blocked_notification_identity": identity,
            "blocked_notification_confirmed": confirmed,
            "blocked_notification_outcome": outcome}
