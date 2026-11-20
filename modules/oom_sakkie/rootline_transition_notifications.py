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
        label = labels.get(kind, "Boorgat se AC-rugsteun" if af else "Borehole AC backup")
    observed = datetime.fromisoformat(execution["notification_observed_at"])
    stamp = observed.astimezone(ZoneInfo("Africa/Johannesburg")).strftime("%d %b %H:%M")
    on = state == "Started"
    edge = ("AAN" if on else "AF") if af else ("ON" if on else "OFF")
    header = "ROOTLINE — TOERUSTING" if af else "ROOTLINE — EQUIPMENT"
    body = f"{label}: {edge} bevestig op {stamp} SAST." if af else f"{label}: {edge} verified at {stamp} SAST."
    if execution.get("action") in {"mark_borehole_active", "record_borehole_completed"}:
        body += (" Die pomp se eie sonkragwerking is nie hierdeur bevestig nie." if af else
            " This does not verify whether the pump is operating on its own solar supply.")
    return f"<b>{header}</b>\n\n{body}"


# Provider notices share the existing minute and family-delivery rails. They
# never enter transition(), which still requires an authoritative switch edge.
def provider_availability_text(availability, *, language="en"):
    from modules.telemetry.rootline_provider_availability import CONTRACT
    af = str(language).casefold().startswith("af")
    if not isinstance(availability, dict) or availability.get("contract") != CONTRACT:
        return ""
    if availability.get("status") in {"unknown", "unobserved"}:
        return ("Die jongste skakelaarstatusdiens kon nie uit die rekords bevestig word nie."
            if af else "The latest switch-status service availability could not be verified from the records.")
    if availability.get("status") == "restored":
        from modules.telemetry.rootline_provider_availability import _time
        times = [_time(row.get("restored_at")) for row in availability.get("scopes", [])
            if isinstance(row, dict) and row.get("state") == "restored"]
        times = [stamp for stamp in times if stamp is not None]
        if not times:
            return ("Huidige skakelaarstatus is onbevestig." if af else "Current switch-status availability is unverified.")
        stamp = max(times).astimezone(ZoneInfo("Africa/Johannesburg")).strftime("%d %b %H:%M SAST")
        return (f"Die laaste volledige herstelkontrole het op {stamp} geslaag. Nuwe werk vereis steeds "
                "vars statusbevestiging; dié rekord bewys nie die huidige toesteltoestand nie." if af else
                f"The last complete recovery check succeeded at {stamp}. New work still requires fresh "
                "status verification; this record does not prove the current device state.")
    if availability.get("status") != "unavailable":
        return ""
    return ("Vars skakelaarstatus is tans nie beskikbaar nie. Nuwe outomatiese beginaksies wat "
        "dié bevestiging vereis, bly teruggehou. Bestaande AF-opdragte word steeds probeer; "
        "AF bly onbevestig totdat 'n geldige lesing dit bewys. ROOTLINE probeer outomaties "
        "weer volgens die diens se wagtyd. Die diens se hersteltyd is onbekend." if af else
        "Fresh switch-status verification is unavailable. New automatic starts that require "
        "that verification remain held. Existing OFF duties are still attempted; OFF remains "
        "unconfirmed until valid readback proves it. ROOTLINE retries automatically under the "
        "provider backoff. The provider's recovery time is unknown.")


def compose_provider_notice(state, payload, *, language="en"):
    from modules.telemetry.rootline_provider_availability import CONTRACT, _time
    import html
    af = str(language).casefold().startswith("af")
    observed = _time(payload.get("restored_at") if state == "ProviderRestored" else payload.get("outage_started_at"))
    stamp = observed.astimezone(ZoneInfo("Africa/Johannesburg")).strftime("%d %b %H:%M SAST") if observed else "Unknown"
    if state == "ProviderRestored":
        return (("<b>ROOTLINE — STATUSLESINGS HERSTEL</b>" if af else
            "<b>ROOTLINE — STATUS READINGS RESTORED</b>") + "\n\n" +
            (f"'n Volledige skakelaarstatuskontrole het op {stamp} geslaag. Dit bevestig toegang "
             "tot statuslesings op daardie tydstip, nie die huidige toestand, hervatte besproeiing, gelewerde water of veilige AF vir elke toestel nie. "
             "ROOTLINE herbeoordeel die werk outomaties." if af else
             f"A complete switch-status check succeeded at {stamp}. This confirms access to status "
             "readings at that time, not the current state, resumed irrigation, delivered water or safe OFF for every device. "
             "ROOTLINE reassesses the work automatically."))
    text = provider_availability_text({"contract": CONTRACT, "status": "unavailable"}, language=language)
    if state == "ProviderSafety":
        label = str(payload.get("duty_label") or "Equipment duty")
        if af:
            label = {"Fertilizer mixer": "Kunsmismenger", "Fertilizer injector": "Kunsmisinspuiter",
                "Borehole AC backup": "Boorgat se AC-rugsteun", "Equipment duty": "Toerustingplig"}.get(label, label.replace(" Camp", " Kamp"))
        label = html.escape(label)
        overdue = payload.get("severity") == "off_unverified"
        detail = ((f"{label}: die AF-sperdatum is verby of afskakeling is onseker." if af else
                   f"{label}: the OFF deadline has passed or shutdown is uncertain.") if overdue else
                  (f"{label}: 'n bestaande toerustingplig benodig steeds bevestiging." if af else
                   f"{label}: an existing equipment duty still needs verification."))
        return (("<b>ROOTLINE — DRINGENDE STATUSGAPING</b>" if af else
                 "<b>ROOTLINE — URGENT STATUS GAP</b>") + "\n\n" + detail + " " + text + " " +
                ("Kontroleer die plaaslike toestand slegs indien dit veilig is en meld enige gevaar."
                 if af else "Check the local situation only if it is safe, and report any danger."))
    return (("<b>ROOTLINE — STATUSLESINGS ONBESKIKBAAR</b>" if af else
             "<b>ROOTLINE — STATUS READINGS UNAVAILABLE</b>") + "\n\n" + text + " " +
            (f"Aangeteken sedert {stamp}." if af else f"Recorded since {stamp}."))


def _provider_duties(store, now):
    from modules.telemetry.rootline_provider_availability import _time
    from modules.telemetry.rootline_device_registry import IRRIGATION_ZONE_IDS
    rows = [store("load_active", None), store("load_active_borehole", None)]
    auxiliaries = store("load_active_auxiliaries", None)
    if not isinstance(auxiliaries, list):
        raise ValueError("provider_duty_evidence_unavailable")
    rows.extend(auxiliaries)
    duties = []
    for row in rows:
        if row is None:
            continue
        if not isinstance(row, dict) or not row.get("execution_id"):
            raise ValueError("provider_duty_evidence_invalid")
        # A proven no-send claim is not running equipment.
        if row.get("on_not_dispatched") is True:
            continue
        zone = row.get("zone_id")
        label = (str(zone)[0] + " Camp") if zone in set(IRRIGATION_ZONE_IDS) else {
            "FERTILIZER-MIXER-CH2": "Fertilizer mixer",
            "FERTILIZER-INJECTION-CH1": "Fertilizer injector"}.get(row.get("auxiliary_device_id"), "Borehole AC backup" if
                "borehole" in str(row.get("action") or "") else "Equipment duty")
        deadline = _time(row.get("primary_stop_deadline"))
        severity = "off_unverified" if ((deadline and deadline <= now) or
            row.get("state") in {"Stopping", "ShutdownUncertain", "Ambiguous"}) else "active_duty"
        duties.append({"duty_id": str(row["execution_id"]), "duty_label": label, "severity": severity})
    return sorted(duties, key=lambda row: (row["duty_id"], row["severity"]))


def _provider_receipt(identity, incident, receipt):
    if not receipt:
        return {}
    if (not isinstance(receipt, dict) or receipt.get("notification_identity") != identity
            or receipt.get("execution_id") != incident):
        raise ValueError("provider_notification_receipt_binding_invalid")
    payload = receipt.get("provider_notice")
    if (not isinstance(payload, dict) or payload.get("notification_identity") != identity
            or payload.get("incident_id") != incident):
        raise ValueError("provider_notification_payload_binding_invalid")
    return receipt


def recover_provider_notifications(*, notify, now=None, store=rootline_irrigation_execution_store,
        loader=None, receipt_loader=None, clock=None):
    """Notify once per episode/severity through existing atomic family delivery."""
    from modules.telemetry.rootline_provider_availability import (
        read_provider_availability, read_notification_receipt, _time, CONTRACT)
    clock = clock or (lambda: datetime.now(timezone.utc))
    now = _time(now or clock())
    current_time = _time(clock())
    if now is None or current_time is None:
        raise ValueError("aware_time_required")
    # Safety may have just recorded a failure after the scheduled evidence cutoff.
    now = max(now, current_time)
    loader = loader or read_provider_availability
    receipt_loader = receipt_loader or read_notification_receipt
    result = {"success": True, "status": "rootline_provider_notifications_observed",
        "telegram_sends": 0, "notification_count": 0, "hardware_commands": 0}
    remaining_seconds(minimum=5)
    availability = loader(now=now)
    if not isinstance(availability, dict) or availability.get("contract") != CONTRACT:
        raise ValueError("provider_availability_contract_invalid")
    try:
        duties = _provider_duties(store, now) if availability.get("status") == "unavailable" else []
    except Exception:
        # Failure to read duties must not suppress the known provider outage.
        duties = []
        result.update(success=False, status="rootline_provider_safety_evidence_unavailable")
    for scope in availability.get("scopes") or []:
        incident = scope["incident_id"]
        outage_identity = incident + ":unavailable"
        candidates = []
        if scope["state"] == "unavailable":
            candidates.append(("ProviderUnavailable", {**scope, "notification_identity": outage_identity}))
            for duty in duties:
                suffix = sha256((duty["duty_id"] + "|" + duty["severity"]).encode()).hexdigest()[:24]
                candidates.append(("ProviderSafety", {**scope, **duty,
                    "notification_identity": incident + ":safety:" + suffix}))
        elif scope["state"] == "restored":
            # No unsolicited retrospective recovery for an outage never told to
            # this owner. A confirmed outage receipt is the announcement fence.
            prior_outage = _provider_receipt(outage_identity, incident, receipt_loader(outage_identity))
            if prior_outage.get("delivery_confirmed") is True and prior_outage.get("provider_message_id"):
                candidates.append(("ProviderRestored", {**scope,
                    "notification_identity": incident + ":restored"}))
        for state, payload in candidates:
            remaining_seconds(minimum=5)
            identity = payload["notification_identity"]
            prior = _provider_receipt(identity, incident, receipt_loader(identity))
            if prior.get("delivery_confirmed") is True and prior.get("provider_message_id"):
                continue
            if prior.get("delivery_ambiguous") is True:
                result.update(success=False, status="rootline_provider_delivery_ambiguous")
                continue
            # Recheck current canonical state immediately before notification;
            # a later failure invalidates an earlier restoration candidate.
            fresh = loader(now=clock())
            current = next((item for item in fresh.get("scopes", [])
                if item.get("scope") == scope["scope"]), None)
            if (not current or current.get("incident_id") != incident
                    or current.get("state") != scope["state"]
                    or (state == "ProviderRestored" and
                        current.get("restoration_event_id") != scope.get("restoration_event_id"))):
                result.update(success=False, status="rootline_provider_notice_superseded")
                continue
            # The first attempted content is immutable across hourly retries.
            if prior.get("provider_notice"):
                saved_payload = prior["provider_notice"]
                if (prior.get("notification_state") != state or any(saved_payload.get(key) != payload.get(key)
                        for key in ("scope", "failure_event_id", "restoration_event_id", "duty_id", "severity"))):
                    raise ValueError("provider_notification_evidence_binding_invalid")
                payload = saved_payload
            proof = str(prior.get("event_id") or "") if prior.get("delivery_definitely_not_sent") is True else ""
            delivery = notify(state, payload, retry_proof_identity=proof)
            confirmed = delivery.get("provider_delivery_confirmed") is True and bool(delivery.get("provider_message_id"))
            not_sent = delivery.get("delivery_definitely_not_sent") is True
            result["telegram_sends"] += int(delivery.get("telegram_sends") or 0)
            if delivery.get("status") == "family_message_cycle_deadline_deferred":
                return {**result, "success": False, "status": "rootline_provider_notifications_deferred"}
            record = {"execution_id": incident, "notification_identity": identity,
                "transition_event_id": scope.get("restoration_event_id") if state == "ProviderRestored" else scope["failure_event_id"],
                "notification_state": state, "provider_notice": payload,
                "delivery_confirmed": confirmed, "delivery_ambiguous": not confirmed and not not_sent,
                "delivery_definitely_not_sent": not_sent,
                "provider_message_id": str(delivery.get("provider_message_id") or "")}
            saved = store("record_notification_delivery", record)
            result["notification_count"] += int(confirmed)
            if not isinstance(saved, dict) or saved.get("success") is not True or not confirmed:
                result.update(success=False, status="rootline_provider_notification_unconfirmed")
    return result


def input_health_text(health, *, language="en"):
    """A compact informational summary, with no device authority or questions."""
    from modules.telemetry.rootline_input_health import CONTRACT
    if not isinstance(health, dict) or health.get("contract") != CONTRACT:
        return ""
    af = str(language).casefold().startswith("af")
    if health.get("status") == "unknown":
        return ("Die jongste weer-, krag- en voorspellingslesings kon nie bevestig word nie."
            if af else "The latest weather, power and forecast inputs could not be verified.")
    lines = []
    for kind, item in (health.get("inputs") or {}).items():
        state = item.get("state")
        if kind == "weather" and state != "available":
            lines.append("Huidige plaasweerlesings is nie beskikbaar nie." if af else
                "Current local weather readings are unavailable.")
        elif kind == "power" and state != "available":
            lines.append("Huidige battery-, sonkrag- en netwerktoestande is nie beskikbaar nie." if af else
                "Current battery, solar and grid conditions are unavailable.")
        elif kind == "forecast":
            day = item.get("operating_date") or ""
            try:
                from datetime import date
                day = date.fromisoformat(day).strftime("%d %b")
            except (ValueError, TypeError):
                day = "onbekende datum" if af else "unknown date"
            if state == "available_fallback":
                lines.append((f"Die voorspelling vir {day} is deur die rugsteunbron beskikbaar." if af else
                    f"The forecast for {day} is available from the backup source."))
            elif state == "failed":
                lines.append((f"Die nagtelike voorspellingsverkryging vir {day} het misluk; ou data is nie vars nie." if af else
                    f"The nightly forecast acquisition for {day} failed; older data is not fresh."))
            elif state == "acquisition_unconfirmed":
                lines.append((f"Die nagtelike voorspelling vir {day} is nog onbevestig." if af else
                    f"The nightly forecast for {day} is unconfirmed."))
            elif state == "pending":
                lines.append((f"Die nagtelike voorspelling vir {day} word nog verkry." if af else
                    f"The nightly forecast for {day} is still being acquired."))
    return " ".join(lines)


def compose_input_notice(state, payload, *, language="en"):
    from modules.telemetry.rootline_input_health import _time
    af = str(language).casefold().startswith("af")
    kind = payload["kind"]
    label = ({"weather": "Plaasweerlesings", "power": "Kraglesings", "forecast": "Nagtelike voorspelling"} if af else
        {"weather": "Local weather readings", "power": "Power readings", "forecast": "Nightly forecast"})[kind]
    recovered = state == "InputRestored"
    proof = payload.get("recovery") if recovered else payload.get("outage")
    observed = _time((proof or {}).get("observed_at") if recovered else payload.get("outage_started_at"))
    if observed is None:
        raise ValueError("input_notice_time_unproven")
    stamp = observed.astimezone(ZoneInfo("Africa/Johannesburg")).strftime("%d %b %H:%M SAST")
    if recovered:
        message = (f"{label} is weer bevestig op {stamp}. ROOTLINE herbeoordeel die betrokke werk outomaties."
            if af else f"{label} were verified again at {stamp}. ROOTLINE reassesses the affected work automatically.")
        if kind == "forecast":
            from datetime import date
            day = date.fromisoformat(proof["operating_date"]).strftime("%d %b")
            message += (f" Dit is die voorspelling vir {day}." if af else f" This is the forecast for {day}.")
        return ("<b>ROOTLINE — LESINGS HERSTEL</b>" if af else "<b>ROOTLINE — INPUTS RESTORED</b>") + "\n\n" + message
    from modules.telemetry.rootline_input_health import CONTRACT
    body = input_health_text({"contract": CONTRACT, "inputs": {kind: proof}}, language=language)
    message = (f"Aangeteken op {stamp}. " if af else f"Recorded at {stamp}. ") + body
    if kind == "power":
        message += (" Dit bevestig nie 'n kragonderbreking nie; onafhanklike besproeiing en bestaande stoppligte bly apart."
            if af else " This does not prove a power outage; independent irrigation and existing stop duties remain separate.")
    elif kind == "weather":
        message += (" ROOTLINE behou bestaande stoppligte en kontroleer weer outomaties." if af else
            " ROOTLINE retains existing stop duties and checks again automatically.")
    else:
        message += (" ROOTLINE behou bestaande stoppligte. Die volgende voorspelling volg die nagtelike siklus." if af else
            " ROOTLINE retains existing stop duties. The next forecast follows the nightly cycle.")
    return ("<b>ROOTLINE — LESINGS ONBESKIKBAAR</b>" if af else "<b>ROOTLINE — INPUTS UNAVAILABLE</b>") + "\n\n" + message


def _input_receipt(identity, incident, recipient_key, receipt):
    if not receipt:
        return {}
    payload = receipt.get("input_notice") if isinstance(receipt, dict) else None
    if (not isinstance(payload, dict) or receipt.get("notification_identity") != identity
            or receipt.get("execution_id") != incident or payload.get("incident_id") != incident
            or payload.get("notification_identity") != identity or payload.get("recipient_key") != recipient_key
            or receipt.get("notification_state") != ("InputRestored" if ":restored:" in identity else "InputUnavailable")
            or payload.get("contract") != "rootline_input_health.v1"
            or payload.get("kind") not in {"weather", "power", "forecast"}):
        raise ValueError("input_notification_receipt_binding_invalid")
    return receipt


def recover_input_notifications(*, notify, recipient, now=None, environ=None,
        reconcile=None, state_loader=None, receipt_loader=None,
        store=rootline_irrigation_execution_store, clock=None):
    """No independent sender: family delivery owns atomic claims and retries."""
    from modules.telemetry.rootline_input_health import (
        input_health_enabled, reconcile_input_health, read_input_notice_state,
        read_input_notification_receipt, CONTRACT, _time)
    result = {"success": True, "status": "rootline_input_notifications_disabled",
        "telegram_sends": 0, "notification_count": 0, "hardware_commands": 0}
    if not input_health_enabled(environ):
        return result
    user, chat = str(recipient.get("owner_user_id") or ""), str(recipient.get("chat_id") or "")
    if not user or user != chat:
        raise ValueError("input_notification_recipient_invalid")
    language = "af" if str(recipient.get("language")).casefold().startswith("af") else "en"
    recipient_key = sha256((user + "|" + chat).encode()).hexdigest()[:32]
    reconcile = reconcile or reconcile_input_health
    state_loader = state_loader or read_input_notice_state
    receipt_loader = receipt_loader or read_input_notification_receipt
    clock = clock or (lambda: datetime.now(timezone.utc))
    remaining_seconds(minimum=5)
    health = reconcile(now=now, environ=environ)
    if not isinstance(health, dict) or health.get("contract") != CONTRACT or health.get("status") != "observed":
        raise ValueError("input_health_reconciliation_unproven")
    result["status"] = "rootline_input_notifications_observed"
    for episode in health.get("episodes") or []:
        incident = episode["incident_id"]
        suffix = ":" + recipient_key
        outage_identity = incident + ":unavailable" + suffix
        if episode["status"] == "Open":
            state, identity = "InputUnavailable", outage_identity
        elif episode["status"] == "Resolved":
            outage = _input_receipt(outage_identity, incident, recipient_key, receipt_loader(outage_identity))
            if not (outage.get("delivery_confirmed") is True and outage.get("provider_message_id")):
                continue
            state, identity = "InputRestored", incident + ":restored" + suffix
        else:
            continue
        remaining_seconds(minimum=5)
        prior = _input_receipt(identity, incident, recipient_key, receipt_loader(identity))
        if prior.get("delivery_confirmed") is True and prior.get("provider_message_id"):
            continue
        if prior.get("delivery_ambiguous") is True:
            result.update(success=False, status="rootline_input_delivery_ambiguous")
            continue
        latest = state_loader(episode["kind"], now=clock())
        current, latest_episode = latest.get("input") or {}, latest.get("episode") or {}
        healthy = current.get("state") in {"available", "available_primary", "available_fallback"}
        if (latest_episode.get("incident_id") != incident or latest_episode.get("status") != episode["status"]
                or (state == "InputRestored" and (not healthy or latest_episode.get("recovery") != episode.get("recovery")))
                or (state == "InputUnavailable" and (healthy or not current.get("notify")))
                or (episode["kind"] == "forecast" and state == "InputUnavailable"
                    and current.get("operating_date") != episode.get("operating_date"))):
            result.update(success=False, status="rootline_input_notice_superseded")
            continue
        payload = {**episode, "notification_identity": identity, "recipient_key": recipient_key,
            "recipient_language": language}
        if prior.get("input_notice"):
            saved = prior["input_notice"]
            if (prior.get("notification_state") != state or any(saved.get(key) != payload.get(key) for key in (
                    "kind", "source_id", "outage", "recovery", "recipient_language"))):
                raise ValueError("input_notification_content_conflict")
            payload = saved
        proof = str(prior.get("event_id") or "") if prior.get("delivery_definitely_not_sent") is True else ""
        delivery = notify(state, payload, retry_proof_identity=proof)
        result["telegram_sends"] += int(delivery.get("telegram_sends") or 0)
        if delivery.get("status") == "family_message_cycle_deadline_deferred":
            return {**result, "success": False, "status": "rootline_input_notifications_deferred"}
        confirmed = delivery.get("provider_delivery_confirmed") is True and bool(delivery.get("provider_message_id"))
        unsent = delivery.get("delivery_definitely_not_sent") is True
        saved = store("record_notification_delivery", {
            "execution_id": incident, "notification_identity": identity,
            "transition_event_id": identity, "notification_state": state, "input_notice": payload,
            "delivery_confirmed": confirmed, "delivery_ambiguous": not confirmed and not unsent,
            "delivery_definitely_not_sent": unsent, "provider_message_id": str(delivery.get("provider_message_id") or "")})
        result["notification_count"] += int(confirmed)
        if not isinstance(saved, dict) or saved.get("success") is not True or not confirmed:
            result.update(success=False, status="rootline_input_notification_unconfirmed")
    return result
