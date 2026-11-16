"""Recover verified device notices on ROOTLINE's existing minute and delivery rails."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from hashlib import sha256
from modules.telemetry.rootline_device_registry import get_device_contract

from modules.telemetry.rootline_cycle_budget import remaining_seconds, RootlineCycleDeadlineExceeded
from modules.telemetry.rootline_irrigation_execution_store import rootline_irrigation_execution_store


def transition(row):
    """Only canonical verified edges qualify; receipts and live-state guesses do not."""
    if not isinstance(row, dict):
        return None
    action = row.get("action")
    if action in {"mark_active", "mark_auxiliary_active"}:
        proof, state = row.get("start_evidence"), "Started"
    elif action == "mark_borehole_active":
        proof, state = row.get("provider_start_evidence"), "Started"
    elif action in {"record_completed", "record_auxiliary_completed", "record_auxiliary_control_pulse_stopped"}:
        proof = row.get("shutdown_evidence")
        state = "Stopped" if row.get("state") in {"Stopped", "Paused", "ControlPulseStopped"} else "Completed"
        if row.get("shutdown_verified") is not True:
            return None
    elif action == "record_borehole_completed":
        proof, state = row.get("provider_final_off_evidence"), "Stopped"
        if row.get("shutdown_verified") is not True:
            return None
    elif action == "record_eskom_completed":
        proof = row.get("readback")
        state = {"ON": "Started", "OFF": "Stopped"}.get(row.get("desired_state"))
    else:
        return None
    expected = "ON" if state == "Started" else "OFF"
    if (not state or not isinstance(proof, dict) or proof.get("authoritative") is not True
            or proof.get("state") != expected or not row.get("execution_id") or not row.get("event_id")
            or not isinstance(row.get("device_id"), str) or not row["device_id"].strip()
            or proof.get("device_id") != row.get("device_id")):
        return None
    if action != "record_eskom_completed":
        if type(row.get("channel")) is not int or type(proof.get("channel")) is not int:
            return None
        if action in {"mark_borehole_active", "record_borehole_completed"}:
            identity = "BOREHOLE-1-MINI-R4-CH1"
        elif action in {"mark_active", "record_completed"}:
            identity = row.get("zone_id")
        else:
            identity = row.get("auxiliary_device_id")
            if identity not in {"FERTILIZER-MIXER-CH2", "FERTILIZER-INJECTION-CH1"}:
                return None
        contract = get_device_contract(identity)
        if (not contract or row["device_id"] != contract["device_id"]
                or row["channel"] != contract["channel"] or proof["channel"] != contract["channel"]):
            return None
    stamp = proof.get("retrieved_at") or proof.get("observed_at") or proof.get("received_at")
    try:
        observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return None
    except (ValueError, TypeError):
        return None
    return state, {**row, "notification_identity": f"{row['execution_id']}:{state}",
        "notification_observed_at": observed.isoformat()}


def recover_transition_notifications(*, notify, now=None, store=rootline_irrigation_execution_store):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("aware_time_required")
    result = {"success": True, "status": "rootline_transition_notifications_observed",
        "telegram_sends": 0, "notification_count": 0, "hardware_commands": 0}
    remaining_seconds(minimum=5)
    loaded = store("load_notification_transitions", {})
    if isinstance(loaded, dict) and loaded.get("epoch") is None:
        claimed = store("claim_notification_recovery_epoch", {})
        if not isinstance(claimed, dict) or claimed.get("success") is not True:
            raise ValueError("notification_recovery_epoch_unproven")
        loaded = store("load_notification_transitions", {})
    if not isinstance(loaded, dict) or not loaded.get("epoch") or not isinstance(loaded.get("transitions"), list):
        raise ValueError("notification_transitions_unavailable")
    rows = loaded["transitions"]
    for item in rows:
        try:
            remaining_seconds(minimum=5)
        except RootlineCycleDeadlineExceeded:
            return {**result, "success": False, "status": "rootline_transition_notifications_deferred"}
        event = item.get("transition") or {}
        prior = item.get("notification") or {}
        envelope_id = item.get("review_event_id") or event.get("event_id")
        projected = transition(event)
        if event.get("event_id") != envelope_id:
            projected = None
        if prior.get("delivery_confirmed") is True or prior.get("delivery_ambiguous") is True or prior.get("notification_projection_rejected") is True:
            continue
        if not projected:
            stored = store("record_notification_delivery", {**event,
                "transition_event_id": envelope_id,
                "execution_id": event.get("execution_id") or "ROOTLINE-NOTIFICATION-REJECTED-" + sha256(str(envelope_id).encode()).hexdigest(),
                "delivery_confirmed": False,
                "delivery_ambiguous": False, "notification_projection_rejected": True,
                "notification_rejection_reason": "exact_authoritative_timestamped_switch_edge_unproven",
                "next_action_owner": "ROOTLINE", "delivery_state": "verification_required"})
            result.update(success=False, status="rootline_transition_evidence_unproven")
            if not isinstance(stored, dict) or stored.get("success") is not True:
                return {**result, "status": "rootline_transition_rejection_persistence_unproven"}
            continue
        state, payload = projected
        proof = (str(prior.get("event_id") or "")
            if prior.get("delivery_definitely_not_sent") is True else "")
        # Family delivery owns the atomic attempt, confirmed replay and ambiguity
        # boundary. Never make a new identity to get around its pending attempt.
        delivery = notify(state, payload, retry_proof_identity=proof)
        confirmed = bool(delivery.get("provider_delivery_confirmed") is True and delivery.get("provider_message_id"))
        definitely_not_sent = delivery.get("delivery_definitely_not_sent") is True
        deferred = delivery.get("status") == "family_message_cycle_deadline_deferred"
        if deferred:
            return {**result, "success": False, "status": "rootline_transition_notifications_deferred"}
        ambiguous = not confirmed and not definitely_not_sent
        record = {**payload, "notification_state": state, "transition_event_id": envelope_id,
            "delivery_confirmed": confirmed, "delivery_ambiguous": ambiguous,
            "delivery_definitely_not_sent": definitely_not_sent,
            "provider_message_id": str(delivery.get("provider_message_id") or "")}
        stored = store("record_notification_delivery", record)
        result["telegram_sends"] += int(delivery.get("telegram_sends") or 0)
        result["notification_count"] += int(confirmed)
        if not isinstance(stored, dict) or stored.get("success") is not True or not confirmed:
            result.update(success=False, status="rootline_transition_notification_unconfirmed")
    return result


def compose_transition_notice(state, execution, *, language="en"):
    """Describe the proven switch edge, never water delivery or a whole parent job."""
    af = str(language).casefold().startswith("af")
    kind = execution.get("auxiliary_device_id")
    labels = {"FERTILIZER-MIXER-CH2": "Kunsmismenger" if af else "Fertilizer mixer",
              "FERTILIZER-INJECTION-CH1": "Kunsmisinspuiter" if af else "Fertilizer injector"}
    if execution.get("action") == "record_eskom_completed":
        label = "Eskom-toevoer" if af else "Eskom supply"
    else:
        label = labels.get(kind, "Boorgattoevoer" if af else "Borehole supply")
    observed = datetime.fromisoformat(execution["notification_observed_at"])
    stamp = observed.astimezone(ZoneInfo("Africa/Johannesburg")).strftime("%d %b %H:%M")
    on = state == "Started"
    edge = ("AAN" if on else "AF") if af else ("ON" if on else "OFF")
    header = "ROOTLINE — TOERUSTING" if af else "ROOTLINE — EQUIPMENT"
    body = f"{label}: {edge} bevestig op {stamp} SAST." if af else f"{label}: {edge} verified at {stamp} SAST."
    return f"<b>{header}</b>\n\n{body}"
