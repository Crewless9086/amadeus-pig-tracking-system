"""Existing-scheduler composition for one canonical B/C execution artifact."""
from __future__ import annotations

from datetime import datetime, timezone
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
                                 readback=read_current_device, clock=None):
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
    initial = _current(evidence_loader, readback, token_store, source, database_url, now)
    artifact = initial["artifact"]
    if artifact.get("eligible") is not True:
        return {**_safe(artifact.get("status") or "not_eligible"),
                "execution_eligibility": artifact}
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
            "artifact": build_execution_eligibility(
                plan=plan, evidence=evidence, controller=controller, now=now)}


def _safe(status):
    return {"success": True, "status": status, "hardware_commands": 0,
            "telegram_messages": 0, "writes_farm_data": False,
            "borehole_authority": False, "fertilizer_authority": False}


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
