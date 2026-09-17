"""Existing-scheduler composition for one canonical B/C execution artifact."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os

from modules.telemetry.rootline_execution_authority import build_execution_eligibility
from modules.telemetry.rootline_ewelink_commissioned_baseline import (
    commissioned_controller_baseline, commissioned_registered_device_baseline,
)
from modules.telemetry.rootline_device_registry import (
    commissioned_irrigation_contract, rootline_device_registry,
)
from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
from modules.telemetry.rootline_ewelink_readback import read_current_device
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_irrigation_coordinator import advance_irrigation_execution, _digest
from modules.telemetry.rootline_irrigation_execution_store import (
    RootlineExecutionStoreUnavailable, rootline_irrigation_execution_store,
)
from modules.telemetry.rootline_water_energy_plan import (
    build_water_energy_plan, read_current_water_energy_evidence,
)


def run_rootline_managed_device_reassessment(*, environ=None, now=None,
        database_url=None, store=rootline_irrigation_execution_store,
        token_store=None, transport=None,
        evidence_loader=read_current_water_energy_evidence):
    """Advance one need-driven Mixer, Injector, or Borehole task, if proven.

    This composes existing planners, canonical device records and coordinators.
    Missing fertilizer-batch, active-irrigation, water-need or interlock evidence
    produces a no-command result local to the managed device.
    """
    source = environ if environ is not None else os.environ
    now = _aware(now or datetime.now(timezone.utc))
    database_url = str(database_url or source.get("DATABASE_URL") or "").strip()
    token_store = token_store or PostgresOAuthTokenStore(database_url)
    transport = transport or RootlineIFTTTTransport(
        token_store=token_store, environ=source, readback=read_current_device)
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry.rootline_borehole_commissioning import (
        build_borehole_runtime_eligibility, load_registered_borehole_baseline,
    )
    from modules.telemetry.rootline_managed_devices_runtime import (
        run_rootline_managed_device_cycle,
    )
    def connect_factory():
        return connect_bounded_rootline_postgres(
            database_url=database_url, read_only=True)
    try:
        evidence, selected, planned_at = evidence_loader(
            operating_date=now.date().isoformat(), database_url=database_url, now=now)
        evidence = _refresh_active_irrigation_readback(evidence, transport, now)
        plan = build_water_energy_plan(evidence, selected, now=planned_at)
    except Exception:
        return {**_safe("managed_device_evidence_unavailable"), "blocks_bc": False}
    packet = {"irrigation_auxiliary_tasks": plan.get("irrigation_auxiliary_tasks") or [],
        "auxiliary_safety": {}, "auxiliary_contexts": {}}
    for task in packet["irrigation_auxiliary_tasks"]:
        identity = str(task.get("auxiliary_device_id") or "")
        if identity not in {"FERTILIZER-MIXER-CH2", "FERTILIZER-INJECTION-CH1"}:
            continue
        contract = rootline_device_registry()[identity]
        try:
            packet["auxiliary_safety"][identity] = transport.read_safety_configuration(
                device_id=contract["device_id"], channel=contract["channel"])
        except Exception:
            continue
    executions = [row for row in evidence.get("fertilizer_executions") or []
                  if isinstance(row, dict)]
    packet["auxiliary_contexts"]["FERTILIZER-MIXER-CH2"] = {
        "plan_generation": str(plan.get("generation") or plan.get("evidence_generation") or ""),
        "injection_active": any(row.get("device_type") == "fertilizer_injection_valve"
            and row.get("state") == "Active" for row in executions),
        "verified_mixing_minutes_today": sum(float(row.get("verified_runtime_minutes") or 0)
            for row in executions if row.get("device_type") == "fertilizer_mixer"
            and str(row.get("completed_at") or "")[:10] == now.date().isoformat()),
        "verified_mixing_sessions_today": sum(1 for row in executions
            if row.get("device_type") == "fertilizer_mixer"
            and str(row.get("completed_at") or "")[:10] == now.date().isoformat()
            and row.get("shutdown_verified") is True),
        "mixing_history_complete_through": evidence.get("fertilizer_history_complete_through"),
        "power_suitable": _managed_power_suitable(evidence.get("power")),
    }
    active_irrigation = evidence.get("active_irrigation_context")
    if isinstance(active_irrigation, dict):
        packet["auxiliary_contexts"]["FERTILIZER-INJECTION-CH1"] = active_irrigation
    borehole_task = next((row for row in plan.get("candidate_tasks") or []
        if row.get("task_id") == "borehole"), {})
    interlocks = evidence.get("borehole_interlocks")
    if (borehole_task.get("recommendation") == "Recommend"
            and isinstance(interlocks, dict)):
        try:
            baseline = load_registered_borehole_baseline(connect_factory=connect_factory)
            provider = transport.read_output_state(device_id="1002851416", channel=1)
            if baseline:
                packet["borehole_execution"] = build_borehole_runtime_eligibility(
                    need={"eligible": True, "task_id": "borehole",
                        "reason": borehole_task.get("reason")}, baseline=baseline,
                    authority={"inside_standing_authority": True}, provider=provider,
                    interlocks=interlocks,
                    energy={"eligible": _managed_power_suitable(evidence.get("power"))},
                    requested_seconds=min(14400,
                        int(baseline["maximum_routine_runtime_seconds"])), now=now)
        except Exception:
            pass
    return run_rootline_managed_device_cycle(evidence=packet, transport=transport,
        environ=source, store=store, connect_factory=connect_factory, now=now)


def _managed_power_suitable(power):
    value = power if isinstance(power, dict) else {}
    fields = ("battery_soc_pct", "solar_power_w", "grid_power_w")
    if any(value.get(field) is None for field in fields):
        return False
    return (float(value["battery_soc_pct"]) >= 50
        or float(value["solar_power_w"]) >= 1200
        or float(value["grid_power_w"]) > 0)


def _refresh_active_irrigation_readback(evidence, transport, now):
    """Refresh only the exact canonical active B/C execution's ON evidence."""
    if not isinstance(evidence, dict):
        return evidence
    context = evidence.get("active_irrigation_context")
    if not isinstance(context, dict):
        return evidence
    device_id = str(context.get("zone_device_id") or "")
    channel = context.get("zone_channel")
    if not device_id or type(channel) is not int:
        return evidence
    try:
        current = transport.read_output_state(device_id=device_id, channel=channel)
    except Exception:
        return evidence
    if (not isinstance(current, dict) or current.get("authoritative") is not True
            or current.get("state") != "ON" or not (current.get("evidence_id")
                or current.get("response_digest"))):
        return evidence
    refreshed = dict(evidence); updated = dict(context)
    updated["zone_output_evidence"] = {**current,
        "evidence_id": str(current.get("evidence_id") or current.get("response_digest")),
        "zone_execution_id": str(context.get("zone_execution_id") or ""),
        "observed_at": now.isoformat()}
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


def run_rootline_execution_cycle(*, notify, environ=None, now=None, database_url=None,
                                 store=rootline_irrigation_execution_store,
                                 token_store=None, transport=None,
                                 outcome_reader=lambda _identity: None,
                                 evidence_loader=read_current_water_energy_evidence,
                                 readback=read_current_device, clock=None,
                                 owner_user_id="", chat_id="", next_reassessment_at="",
                                 observation_store=None, expected_artifact=None,
                                 authority_checker=None):
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
            outcome_reader=outcome_reader, now=now, clock=clock)
    if not owner_user_id or owner_user_id != chat_id:
        return _safe("canonical_observation_binding_invalid")
    initial = _current(evidence_loader, readback, token_store, source, database_url, now, store)
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
                        database_url, current_now, store)["artifact"]
    return advance_irrigation_execution(decision_id=decision["decision_id"],
        commissioning_id=commissioning_id, decision_reader=lambda _identity: decision,
        commissioning_reader=lambda _identity: commissioning, store=store,
        transport=transport, notify=notify, outcome_reader=outcome_reader,
        eligibility_revalidator=revalidate, now=now, clock=clock)


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
        clock=None, owner_user_id="", chat_id=""):
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
          now=now,clock=clock)
    try:
        current=_current(evidence_loader,readback,token_store,source,database_url,now,store)
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
          _aware(clock()),store)["artifact"]
    return advance_irrigation_execution(decision_id=decision["decision_id"],
      commissioning_id=commissioning_id,decision_reader=lambda _identity:decision,
      commissioning_reader=lambda _identity:commissioning,store=store,transport=transport,
      notify=notify,outcome_reader=outcome_reader,eligibility_revalidator=revalidate,
      now=now,clock=clock)


def _current(evidence_loader, readback, token_store, source, database_url, now,
             store=rootline_irrigation_execution_store):
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
    controller = readback(token_store=token_store, environ=source, now=now)
    artifact = build_execution_eligibility(
        plan=plan, evidence=evidence, controller=controller, now=now,
        job_event_reader=lambda job_id: store("load_job_events", job_id),
        zone_containment_reader=lambda zone_id: store("load_zone_containment", zone_id))
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
    zones = []
    zone_ids = sorted(identity for identity, row in rootline_device_registry().items()
        if row.get("collection")=="irrigation_zones"
        and row.get("commissioned") is True)
    for zone in zone_ids:
        task = tasks.get(zone, {})
        raw = str(task.get("zone_decision") or "Needs Data")
        decision = raw if raw in {"Run now", "Run later", "Hold", "Needs Data", "Not Due"} else "Needs Data"
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
            "reason": str(task.get("reason") or artifact.get("status") or
                          "No canonical zone task is available."),
            "planned_duration_minutes": task.get("planned_duration_minutes"),
            "feasible_window": task.get("preferred_window"),
            "eligibility_blocker": blocker})
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
