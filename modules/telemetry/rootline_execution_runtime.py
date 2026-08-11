"""Existing-scheduler composition for one canonical B/C execution artifact."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os

from modules.telemetry.rootline_execution_authority import build_execution_eligibility
from modules.telemetry.rootline_ewelink_commissioned_baseline import commissioned_controller_baseline
from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
from modules.telemetry.rootline_ewelink_readback import read_current_device
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_irrigation_coordinator import advance_irrigation_execution, _digest
from modules.telemetry.rootline_irrigation_execution_store import rootline_irrigation_execution_store
from modules.telemetry.rootline_water_energy_plan import (
    build_water_energy_plan, read_current_water_energy_evidence,
)


def run_rootline_execution_cycle(*, notify, environ=None, now=None, database_url=None,
                                 store=rootline_irrigation_execution_store,
                                 token_store=None, transport=None,
                                 outcome_reader=lambda _identity: None,
                                 evidence_loader=read_current_water_energy_evidence,
                                 readback=read_current_device, clock=None,
                                 owner_user_id="", chat_id="", next_reassessment_at="",
                                 observation_store=None):
    source = environ if environ is not None else os.environ
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _aware(now or clock())
    if str(source.get("ROOTLINE_AUTONOMOUS_BC_ENABLED") or "").lower() != "true":
        return _safe("autonomous_bc_disabled")
    token_store = token_store or PostgresOAuthTokenStore(database_url)
    transport = transport or RootlineIFTTTTransport(
        token_store=token_store, environ=source, readback=readback)
    active = store("load_active", None)
    if active:
        return advance_irrigation_execution(decision_id="", commissioning_id="",
            decision_reader=lambda _identity: {}, commissioning_reader=lambda _identity: {},
            store=store, transport=transport, notify=notify,
            outcome_reader=outcome_reader, now=now, clock=clock)
    if not owner_user_id or owner_user_id != chat_id:
        return _safe("canonical_observation_binding_invalid")
    initial = _current(evidence_loader, readback, token_store, source, database_url, now)
    observation = _planning_observation(initial, owner_user_id, chat_id,
                                        next_reassessment_at)
    if observation_store is None:
        from modules.oom_sakkie.rootline_reassessment_store import rootline_reassessment_state_store
        observation_store = rootline_reassessment_state_store
    recorded = observation_store("record_observation", observation["identity"], observation)
    if not isinstance(recorded, dict) or recorded.get("success") is not True:
        return {**_safe("canonical_observation_persistence_unproven"), "success": False}
    artifact = initial["artifact"]
    if artifact.get("eligible") is not True:
        blocked = _technical_block_alert(initial, artifact, store, notify,
                                         next_reassessment_at)
        return {**_safe(artifact.get("status") or "not_eligible"),
                "execution_eligibility": artifact, **blocked}
    stored = store("record_eligibility", artifact)
    if not isinstance(stored, dict) or stored.get("success") is not True:
        return {**_safe("eligibility_persistence_unproven"), "success": False}
    baseline = commissioned_controller_baseline()
    zone = artifact["zone_id"]
    commissioning_id = (baseline["b_commissioning_id"] if zone == "B12345"
                        else baseline["c_commissioning_id"])
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
                        database_url, current_now)["artifact"]
    return advance_irrigation_execution(decision_id=decision["decision_id"],
        commissioning_id=commissioning_id, decision_reader=lambda _identity: decision,
        commissioning_reader=lambda _identity: commissioning, store=store,
        transport=transport, notify=notify, outcome_reader=outcome_reader,
        eligibility_revalidator=revalidate, now=now, clock=clock)


def _current(evidence_loader, readback, token_store, source, database_url, now):
    evidence, operating_date, generated_at = evidence_loader(
        database_url=database_url, now=now)
    plan = build_water_energy_plan(evidence, operating_date, now=generated_at)
    controller = readback(token_store=token_store, environ=source, now=now)
    return {"evidence": evidence, "plan": plan, "controller": controller,
            "operating_date": str(operating_date), "generated_at": generated_at,
            "artifact": build_execution_eligibility(
                plan=plan, evidence=evidence, controller=controller, now=now)}


def _safe(status):
    return {"success": True, "status": status, "hardware_commands": 0,
            "telegram_messages": 0, "writes_farm_data": False,
            "borehole_authority": False, "fertilizer_authority": False}


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
    for zone in ("B12345", "C12345"):
        task = tasks.get(zone, {})
        raw = str(task.get("zone_decision") or "Needs Data")
        decision = raw if raw in {"Run now", "Run later", "Hold", "Needs Data", "Not Due"} else "Needs Data"
        zones.append({"zone_id": zone, "decision": "Run" if decision == "Run now" else decision,
            "reason": str(task.get("reason") or initial["artifact"].get("status") or
                          "No canonical zone task is available."),
            "planned_duration_minutes": task.get("planned_duration_minutes"),
            "feasible_window": task.get("preferred_window"),
            "eligibility_blocker": "" if initial["artifact"].get("eligible") is True
                                  and initial["artifact"].get("zone_id") == zone
                                  else str(initial["artifact"].get("status") or "")})
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
