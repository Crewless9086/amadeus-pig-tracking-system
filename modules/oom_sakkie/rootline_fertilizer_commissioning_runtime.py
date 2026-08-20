"""Governed continuation for the existing fertilizer commissioning lifecycle.

This composes the already deployed provider readback, auxiliary eligibility and
single-use coordinator.  It is not a second command path: the coordinator still
owns the claim, one-shot ON, native fail-stop recovery and terminal evidence.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
from modules.telemetry.rootline_irrigation_execution_store import (
    rootline_irrigation_execution_store,
)

DEVICE_ID = "100204d497"
MIXER_ID = "FERTILIZER-MIXER-CH2"
MISSION_ID = "OOM-ROOTLINE-FERTILIZER-CONFIG-20260809"
CONTRACT_VERSION = "oom_rootline_fertilizer_commissioning_runtime.v1"


def prepare_fertilizer_commissioning(*, owner_result, parsed, gateway_authority=None,
                                     now=None, environ=None, store=None,
                                     token_store=None, transport=None,
                                     power_loader=None, acceptance_loader=None):
    """Build current Mixer eligibility without crossing the controller edge."""
    now = _aware(now or datetime.now(timezone.utc))
    store = store or rootline_irrigation_execution_store
    if not _bound(owner_result, parsed, gateway_authority):
        return _result("commissioning_context_unproven")
    if (acceptance_loader or _load_exact_acceptance)(owner_result, parsed) is not True:
        return _result("commissioning_acceptance_receipt_unproven")
    observed = _time(parsed.get("provider_timestamp"))
    if observed is None or not 0 <= (now - observed).total_seconds() <= 300:
        return _result("commissioning_presence_expired")
    if owner_result.get("ready_for_supervised_proof") is not True:
        return dict(owner_result)
    source = environ if environ is not None else os.environ
    token_store = token_store or PostgresOAuthTokenStore()
    transport = transport or RootlineIFTTTTransport(token_store=token_store, environ=source)
    if store("load_active_auxiliary", None):
        return _result("commissioning_active_execution_conflict")
    try:
        eligibility, context = _current_mixer_eligibility(
            parsed=parsed, now=now, store=store, transport=transport,
            power_loader=power_loader)
    except Exception:
        return _result("commissioning_current_evidence_unavailable")
    if eligibility.get("eligible") is not True:
        return _hold(eligibility.get("status"))
    return {"success": True, "handled": True,
        "status": "commissioning_protected_preview_ready",
        "eligibility": eligibility, "current_context": context,
        "hardware_commands": 0, "provider_control_calls": 0,
        "writes_farm_data": False, "injection_enabled": False,
        "contract_version": CONTRACT_VERSION}


def execute_protected_fertilizer_commissioning(*, eligibility, parsed, now=None,
                                                environ=None, store=None,
                                                token_store=None, transport=None,
                                                power_loader=None):
    """Delegate one confirmed, exactly bound Mixer artifact to the existing spine."""
    from modules.telemetry.rootline_auxiliary_management import validate_auxiliary_eligibility
    now = _aware(now or datetime.now(timezone.utc))
    store = store or rootline_irrigation_execution_store
    try:
        history = store("load_auxiliary_history", MIXER_ID)
    except Exception:
        return _result("commissioning_history_readback_unavailable")
    terminal = _exact_completed_execution(eligibility, history)
    if terminal is not None:
        return _finalize({"success": True, "status": "auxiliary_completed",
            "hardware_commands": 0, "provider_control_calls": 0,
            "execution": terminal}, store)
    artifact = validate_auxiliary_eligibility(eligibility, now=now)
    if (not artifact or artifact.get("auxiliary_device_id") != MIXER_ID
            or artifact.get("device_id") != DEVICE_ID or artifact.get("channel") != 2
            or artifact.get("maximum_duration_seconds") != 300):
        return _result("commissioning_protected_binding_mismatch")
    source = environ if environ is not None else os.environ
    token_store = token_store or PostgresOAuthTokenStore()
    transport = transport or RootlineIFTTTTransport(token_store=token_store, environ=source)
    active = store("load_active_auxiliary", None)
    if active:
        exact_active = (isinstance(active, dict)
            and active.get("execution_id") == artifact.get("execution_id")
            and active.get("consumption_key") == artifact.get("consumption_key")
            and active.get("auxiliary_device_id") == MIXER_ID
            and active.get("device_id") == DEVICE_ID
            and active.get("channel") == 2)
        if not exact_active:
            return _result("commissioning_active_execution_conflict")
        outcome = advance_auxiliary_execution(eligibility={}, store=store,
            transport=transport, revalidate=lambda _artifact: {}, now=now)
        return _finalize(outcome, store)
    try:
        current_safety = transport.read_safety_configuration(device_id=DEVICE_ID, channel=2)
        current_power = (power_loader or _load_power)(now)
        history = store("load_auxiliary_history", MIXER_ID)
    except Exception:
        return _result("commissioning_current_evidence_unavailable")
    if not isinstance(history, list):
        return _result("commissioning_history_readback_unavailable")
    context = _mixer_context(parsed, now, current_safety, current_power, history)

    consumed = {"value": False}
    def authorize_once(**edge):
        approved = (not consumed["value"]
            and edge.get("device_id") == DEVICE_ID and edge.get("channel") == 2
            and edge.get("idempotency_key") == artifact["execution_id"] + ":ON")
        if approved:
            consumed["value"] = True
        return approved
    transport.auxiliary_on_authorizer = authorize_once
    def revalidate(_artifact):
        safety = transport.read_safety_configuration(device_id=DEVICE_ID, channel=2)
        power = (power_loader or _load_power)(now)
        return _mixer_context(parsed, now, safety, power,
            store("load_auxiliary_history", MIXER_ID))
    try:
        outcome = advance_auxiliary_execution(eligibility=artifact, store=store,
            transport=transport, revalidate=revalidate, now=now)
    finally:
        transport.auxiliary_on_authorizer = None
    return _finalize(outcome, store)


def _exact_completed_execution(eligibility, history):
    if not isinstance(eligibility, dict) or not isinstance(history, list):
        return None
    matches = [row for row in history if isinstance(row, dict)
        and row.get("state") == "Completed" and row.get("shutdown_verified") is True
        and row.get("execution_id") == eligibility.get("execution_id")
        and row.get("consumption_key") == eligibility.get("consumption_key")
        and row.get("auxiliary_device_id") == MIXER_ID
        and row.get("device_id") == DEVICE_ID and row.get("channel") == 2
        and row.get("maximum_duration_seconds") == 300]
    return matches[0] if len(matches) == 1 else None


def continue_fertilizer_commissioning(*, owner_result, parsed, gateway_authority=None, now=None,
                                      environ=None, store=None, token_store=None,
                                      transport=None, power_loader=None,
                                      acceptance_loader=None):
    """Advance only a fresh, exactly bound supervised mixer acceptance."""
    deterministic_now = now is not None
    now = _aware(now or datetime.now(timezone.utc))
    source = environ if environ is not None else os.environ
    store = store or rootline_irrigation_execution_store
    if not _bound(owner_result, parsed, gateway_authority):
        return _result("commissioning_context_unproven")
    if (acceptance_loader or _load_exact_acceptance)(owner_result, parsed) is not True:
        return _result("commissioning_acceptance_receipt_unproven")
    observed = _time(parsed.get("provider_timestamp"))
    if observed is None or not 0 <= (now - observed).total_seconds() <= 300:
        return _result("waiting_for_input",
            answer=("<b>FERTILIZER MIXER — READY WHEN YOU ARE</b>\n\n"
                    "Are you at the fertilizer valves now for the five-minute mixer test?"),
            next_reassessment="fresh_owner_presence")
    if owner_result.get("ready_for_supervised_proof") is not True:
        return dict(owner_result)
    token_store = token_store or PostgresOAuthTokenStore()
    transport = transport or RootlineIFTTTTransport(
        token_store=token_store, environ=source)

    # An already claimed proof always recovers/observes through the same rail.
    active = store("load_active_auxiliary", None)
    if active:
        facts = ((parsed.get("semantic") or {}).get("commissioning_facts")
                 if isinstance(parsed.get("semantic"), dict) else None)
        recorded_physical = isinstance(facts, dict) and bool(facts)
        if recorded_physical:
            store("record_auxiliary_physical_outcome", {"execution_id": active["execution_id"],
                "provider_message_id": str(parsed.get("provider_message_id") or ""),
                "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
                **facts})
        outcome = advance_auxiliary_execution(eligibility={}, store=store,
            transport=transport, revalidate=lambda _artifact: {}, now=now)
        presented = _finalize(outcome, store)
        if recorded_physical and outcome.get("status") in {
                "auxiliary_active", "auxiliary_claim_in_progress"}:
            presented.update({"answer": ("<b>FERTILIZER MIXER — OBSERVATION RECORDED</b>\n\n"
                "I retained the recirculation, pump and output observation. The controller still owns "
                "the five-minute auto-OFF; ROOTLINE will verify shutdown automatically."),
                "requires_visible_notification": True, "question_count": 0})
        return presented

    try:
        safety = transport.read_safety_configuration(device_id=DEVICE_ID, channel=2)
        power = (power_loader or _load_power)(now)
        history = store("load_auxiliary_history", MIXER_ID)
    except Exception:
        return _result("commissioning_current_evidence_unavailable",
            answer=("<b>FERTILIZER MIXER — WAITING SAFELY</b>\n\n"
                    "ROOTLINE could not complete the current controller or power check. "
                    "It will reassess automatically; you do not need to repeat the setup."),
            next_reassessment="next_scheduler_tick")
    now = _evaluation_time(now, deterministic_now)
    if not isinstance(history, list):
        return _result("commissioning_history_readback_unavailable")
    today = now.date()
    completed = [row for row in history if _time(row.get("completed_at"))
                 and _time(row.get("completed_at")).date() == today
                 and row.get("shutdown_verified") is True]
    minutes = sum(float(row.get("verified_runtime_seconds") or 0) / 60
                  for row in completed)
    plan_generation = sha256(json.dumps({
        "mission_id": MISSION_ID,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "controller_generation": safety.get("controller_safety_generation"),
        "controller_digest": safety.get("response_digest"),
        "power_generation": power.get("generation"),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    context = {"plan_generation": plan_generation, "injection_active": False,
        "verified_mixing_minutes_today": minutes,
        "verified_mixing_sessions_today": len(completed),
        "mixing_history_complete_through": now.isoformat(),
        "power_suitable": power.get("suitable") is True,
        "prior_shutdown_unverified": False}
    eligibility = build_auxiliary_eligibility(
        task={"auxiliary_device_id": MIXER_ID}, safety=safety, context=context,
        flags={"ROOTLINE_FERTILIZER_MIXING_ENABLED": True}, now=now)
    if eligibility.get("eligible") is not True:
        return _hold(eligibility.get("status"))

    execution_id = eligibility["execution_id"]
    from modules.oom_sakkie.gateway_authority import (
        issue_owner_operational_outcome_authority,
        validates_owner_operational_outcome_authority,
    )
    control_authority = issue_owner_operational_outcome_authority(gateway_authority,
        mission_id=MISSION_ID, execution_id=execution_id,
        provider_message_id=str(parsed.get("provider_message_id") or ""),
        provider_timestamp=str(parsed.get("provider_timestamp") or ""),
        content_sha256=sha256(str(parsed.get("text") or "").encode()).hexdigest())
    consumed = {"value": False}
    def authorize_once(**edge):
        approved = (not consumed["value"]
            and validates_owner_operational_outcome_authority(control_authority)
            and control_authority.execution_id == execution_id
            and control_authority.mission_id == MISSION_ID
            and edge.get("device_id") == DEVICE_ID and edge.get("channel") == 2
            and edge.get("idempotency_key") == execution_id + ":ON")
        if approved:
            consumed["value"] = True
        return approved
    transport.auxiliary_on_authorizer = authorize_once

    def revalidate(_artifact):
        current_safety = transport.read_safety_configuration(device_id=DEVICE_ID, channel=2)
        current_power = (power_loader or _load_power)(now)
        return {**context, "power_suitable": current_power.get("suitable") is True,
                "mixing_history_complete_through": now.isoformat()}

    try:
        outcome = advance_auxiliary_execution(eligibility=eligibility, store=store,
            transport=transport, revalidate=revalidate, now=now)
    finally:
        transport.auxiliary_on_authorizer = None
    return _finalize(outcome, store)


def recover_fertilizer_commissioning(*, now=None, environ=None, store=None,
                                     token_store=None, transport=None):
    """Scheduler-owned recovery/verification for a claimed mixer proof."""
    now = _aware(now or datetime.now(timezone.utc)); store = store or rootline_irrigation_execution_store
    active = store("load_active_auxiliary", None)
    if not active or active.get("auxiliary_device_id") != MIXER_ID:
        return _result("no_active_fertilizer_commissioning")
    source = environ if environ is not None else os.environ
    token_store = token_store or PostgresOAuthTokenStore()
    transport = transport or RootlineIFTTTTransport(token_store=token_store, environ=source)
    return _finalize(advance_auxiliary_execution(eligibility={}, store=store,
        transport=transport, revalidate=lambda _artifact: {}, now=now), store)


def emergency_off_fertilizer_mixer(*, reason="emergency_off", environ=None,
                                   store=None, token_store=None, transport=None):
    """Request deterministic OFF for only the exact active Mixer execution."""
    from modules.telemetry.rootline_irrigation_coordinator import (
        emergency_off_auxiliary_execution,
    )
    source = environ if environ is not None else os.environ
    store = store or rootline_irrigation_execution_store
    token_store = token_store or PostgresOAuthTokenStore()
    transport = transport or RootlineIFTTTTransport(
        token_store=token_store, environ=source)
    return _present(emergency_off_auxiliary_execution(
        store=store, transport=transport, reason=reason))


def _finalize(outcome, store):
    execution = outcome.get("execution") if isinstance(outcome, dict) else None
    if (outcome.get("status") == "auxiliary_completed" and isinstance(execution, dict)
            and execution.get("shutdown_verified") is True
            and execution.get("physical_outcome_verified") is True):
        stored = store("record_mixing_commissioned", {"execution_id": execution["execution_id"],
            "auxiliary_device_id": MIXER_ID, "commissioning_id": MISSION_ID,
            "shutdown_evidence": execution.get("shutdown_evidence"),
            "physical_outcome_evidence": execution.get("physical_outcome_evidence"),
            "mixing_enabled": True, "injection_enabled": False})
        outcome = {**outcome, "mixing_enabled": bool(isinstance(stored, dict)
            and stored.get("success") is True), "injection_enabled": False}
    return _present(outcome)


def _bound(result, parsed, authority):
    from modules.oom_sakkie.gateway_authority import validates_gateway_owner_authority
    observed = _time(parsed.get("provider_timestamp"))
    return (validates_gateway_owner_authority(authority)
        and authority.owner_user_id == str(parsed.get("telegram_user_id") or "")
        and authority.private_chat_id == str(parsed.get("telegram_chat_id") or "")
        and observed is not None
        and str(result.get("status") or "") == "specialist_accepted"
        and result.get("authority") == {"configuration_write": False,
            "hardware_control": False, "farm_write": False, "telegram_send": False}
        and str(result.get("specialist_identity") or "") == "ROOTLINE"
        and str(result.get("mission_id") or "") == MISSION_ID
        and str(result.get("card_mission_id") or "") == MISSION_ID
        and str(result.get("next_specialist_step") or "") == "supervised_fertilizer_mixer_proof"
        and str(parsed.get("telegram_user_id") or "") == "5721652188"
        and str(parsed.get("telegram_chat_id") or "") == "5721652188"
        and bool(str(parsed.get("provider_message_id") or "").strip())
        and _time(parsed.get("provider_timestamp")) is not None)


def _load_power(now):
    # Mixer commissioning reads only the canonical power projection. Tank,
    # irrigation, weather and forecast projections are deliberately out of scope.
    from modules.telemetry.power_service import get_current_power_state
    packet, _status = get_current_power_state(database_url=os.environ.get("DATABASE_URL"))
    power = packet.get("current") if isinstance(packet, dict) else {}
    soc = _number(power.get("battery_soc_pct")); solar = _number(power.get("solar_power_w"))
    grid = _number(power.get("grid_power_w"))
    suitable = None if None in (soc, solar, grid) else not (soc < 50 and solar < 1200 and grid <= 0)
    generation = sha256(json.dumps(power, sort_keys=True, default=str).encode()).hexdigest()
    return {"suitable": suitable, "generation": generation,
        "observed_at": power.get("observed_at")}


def _current_mixer_eligibility(*, parsed, now, store, transport, power_loader=None):
    safety = transport.read_safety_configuration(device_id=DEVICE_ID, channel=2)
    power = (power_loader or _load_power)(now)
    history = store("load_auxiliary_history", MIXER_ID)
    if not isinstance(history, list):
        raise RuntimeError("commissioning_history_readback_unavailable")
    context = _mixer_context(parsed, now, safety, power, history)
    eligibility = build_auxiliary_eligibility(
        task={"auxiliary_device_id": MIXER_ID}, safety=safety, context=context,
        flags={"ROOTLINE_FERTILIZER_MIXING_ENABLED": True}, now=now)
    return eligibility, context


def _mixer_context(parsed, now, safety, power, history):
    completed = [row for row in history if _time(row.get("completed_at"))
        and _time(row.get("completed_at")).date() == now.date()
        and row.get("shutdown_verified") is True]
    minutes = sum(float(row.get("verified_runtime_seconds") or 0) / 60
                  for row in completed)
    generation = sha256(json.dumps({
        "mission_id": MISSION_ID,
        "provider_message_id": str(parsed.get("provider_message_id") or ""),
        "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "controller_generation": safety.get("controller_safety_generation"),
        "controller_digest": safety.get("response_digest"),
        "power_generation": power.get("generation"),
    }, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"plan_generation": generation, "injection_active": False,
        "verified_mixing_minutes_today": minutes,
        "verified_mixing_sessions_today": len(completed),
        "mixing_history_complete_through": now.isoformat(),
        "power_suitable": power.get("suitable") is True,
        "prior_shutdown_unverified": False}


def _evaluation_time(initial, deterministic):
    """Evaluate receipts after live I/O; preserve explicitly injected test clocks."""
    return initial if deterministic else datetime.now(timezone.utc)


def _load_exact_acceptance(result, parsed):
    """Prove the adapter acceptance already committed on the intake audit rail."""
    import psycopg
    mission = str(result.get("mission_id") or "")
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'rootline_operational_intake'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_rootline_operational_intake'
                  and review_json->'rootline_operational_intake'->>'mission_id'=%s
                  and review_json->'rootline_operational_intake'->>'state'=
                      'contextual_followup_completed'
                order by created_at desc""", (mission,))
            rows = [row[0] for row in cursor.fetchall()]
    text_sha = sha256(str(parsed.get("text") or "").encode()).hexdigest()
    matches = []
    expected_authority = {"configuration_write": False, "hardware_control": False,
        "farm_write": False, "telegram_send": False}
    for row in rows:
        context = row.get("context") if isinstance(row, dict) else None
        outcome = row.get("outcome") if isinstance(row, dict) else None
        if (isinstance(context, dict) and isinstance(outcome, dict)
                and context.get("mission_id") == mission
                and context.get("card_mission_id") == mission
                and context.get("owner_user_id") == str(parsed.get("telegram_user_id") or "")
                and context.get("chat_id") == str(parsed.get("telegram_chat_id") or "")
                and context.get("provider_message_id") == str(parsed.get("provider_message_id") or "")
                and _time(context.get("provider_timestamp")) == _time(parsed.get("provider_timestamp"))
                and context.get("text_sha256") == text_sha
                and context.get("contextual_task_kind") == "fertilizer_commissioning"
                and outcome.get("status") == "specialist_accepted"
                and outcome.get("ready_for_supervised_proof") is True
                and outcome.get("response_contract_version") == "contextual_specialist_response_v2"
                and outcome.get("authority") == expected_authority
                and outcome.get("hardware_commands") == 0
                and outcome.get("provider_control_calls") == 0
                and outcome.get("writes_farm_data") is False):
            matches.append(row)
    return len(matches) == 1


def _hold(reason):
    human = {
        "low_power_mix_deferred": "Current energy conditions do not support the five-minute mixer test.",
        "auxiliary_safety_unproven": "The controller safety readback is not currently complete.",
        "auxiliary_device_contained": "The mixer control is safely contained pending a verified shutdown review.",
    }.get(str(reason), "A current mixer-specific safety condition is not yet proven.")
    return _result("commissioning_specific_hold",
        answer=("<b>FERTILIZER MIXER — TEMPORARY HOLD</b>\n\n"
                f"{human}\n\nROOTLINE will reassess on the next automatic check; "
                "you do not need to repeat the setup."), next_reassessment="next_scheduler_tick")


def _present(outcome):
    status = str(outcome.get("status") or "")
    if status == "auxiliary_started":
        answer = ("<b>🟢 FERTILIZER MIXER — STARTED</b>\n\n"
                  "The five-minute Kunsmis Meng test has started. CH1 and unrelated outputs "
                  "remain outside this test, and the controller owns the 300-second auto-OFF.\n\n"
                  "Is the tank recirculating normally, is the pressure-switched pump behaving "
                  "as expected, and are the other outputs still off?")
    elif status == "auxiliary_completed":
        enabled = outcome.get("mixing_enabled") is True
        answer = ("<b>✅ FERTILIZER MIXER — COMPLETED</b>\n\n"
                  "Provider and physical shutdown are verified. Fertilizer mixing is now commissioned; "
                  "injection stays disabled until an eligible irrigation segment."
                  if enabled else
                  "<b>✅ FERTILIZER MIXER — STOPPED</b>\n\n"
                  "Provider shutdown is verified and the five-minute test is closed. Mixing remains "
                  "pending the physical recirculation and pump observation; fertilizer injection stays disabled.")
    elif status in {"auxiliary_active", "auxiliary_claim_in_progress"}:
        answer = ""
    elif "intervention" in status or "contained" in status or "unverified" in status:
        answer = ("<b>⚠️ FERTILIZER MIXER — INTERVENTION</b>\n\n"
                  "The mixer proof was contained and no ON retry was made. ROOTLINE is retaining shutdown ownership.")
    else:
        answer = ""
    return {"success": outcome.get("success") is True, "handled": True,
        "status": status, "answer": answer,
        "requires_visible_notification": bool(answer),
        "question_count": 1 if status == "auxiliary_started" else 0,
        "hardware_commands": int(outcome.get("hardware_commands") or 0),
        "mixing_enabled": outcome.get("mixing_enabled") is True,
        "injection_enabled": False,
        "writes_farm_data": False, "commissioning_outcome": outcome,
        "contract_version": CONTRACT_VERSION}


def _result(status, answer="", next_reassessment=None):
    return {"success": status in {"no_active_fertilizer_commissioning"}, "handled": True,
        "status": status, "answer": answer, "requires_visible_notification": bool(answer),
        "question_count": 1 if status == "waiting_for_input" else 0,
        "hardware_commands": 0, "mixing_enabled": False,
        "injection_enabled": False, "writes_farm_data": False,
        "next_reassessment": next_reassessment, "contract_version": CONTRACT_VERSION}


def _time(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(
            str(value).replace("Z", "+00:00"))
        return _aware(parsed)
    except (TypeError, ValueError):
        return None


def _number(value):
    try: return float(value)
    except (TypeError, ValueError): return None


def _aware(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
