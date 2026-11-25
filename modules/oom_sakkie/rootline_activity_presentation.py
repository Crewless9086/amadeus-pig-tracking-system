"""Short owner notices from existing canonical controller records; no I/O."""
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

IRRIGATION_URL = "https://amadeus-pig-tracking-system.onrender.com/irrigation"

def activity_notice(state, execution, *, language="en"):
    from modules.telemetry.rootline_command_acceptance import command_execution, accepted, duty_closed, program_completed, job_completed
    af = str(language).casefold().startswith("af")
    zone = str(execution.get("zone_id") or "")
    device = execution.get("auxiliary_device_id")
    if device:
        zone = ""  # Auxiliary rows may carry their parent irrigation zone.
    label = ({"FERTILIZER-MIXER-CH2": "Menger" if af else "Mixer",
        "FERTILIZER-INJECTION-CH1": "Inspuiting" if af else "Injection"}.get(device)
        or ((zone[0]+(" Kamp" if af else " Camp")) if zone else
        "Eskom" if execution.get("action") == "record_eskom_completed" else ("Boorgat se AC-rugsteun" if af else "Borehole AC backup")))
    command = command_execution(execution)
    on = state == "Started"
    receipt = execution.get("command_on_receipt" if on else "command_off_receipt") or {}
    proof = (execution.get("start_evidence" if on else "shutdown_evidence")
        or execution.get("provider_start_evidence" if on else "provider_final_off_evidence")
        or execution.get("readback") or {})
    stamp = execution.get("notification_observed_at") or receipt.get("accepted_at") or proof.get("retrieved_at") or proof.get("observed_at")
    try:
        observed = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        stamp = observed.astimezone(ZoneInfo("Africa/Johannesburg")).strftime("%d %b %H:%M SAST") if observed.tzinfo else ""
    except (TypeError, ValueError):
        stamp = ""
    edge_proven = (proof.get("authoritative") is True and proof.get("state") == ("ON" if on else "OFF")
        and proof.get("device_id") == execution.get("device_id") and bool(execution.get("device_id")))
    closed = duty_closed(execution) if command else edge_proven and (execution.get("shutdown_verified") is True
        or execution.get("action") == "record_eskom_completed")
    complete = closed and (job_completed(execution) if zone and command else
        program_completed(execution) if command and device else
        execution.get("job_completed") is True if zone else execution.get("control_completed") is True)
    interrupted = bool(zone or device) and closed and not complete
    title = (("Begin" if af else "Started") if on else
        ("Program voltooi" if af else "Programme completed") if complete else
        ("Program onvoltooid" if af else "Programme unfinished") if interrupted else ("Gestop" if af else "Stopped"))
    icon = "▶️" if on else "✅" if complete else "⏸️" if interrupted else "⏹️"
    if (command and not accepted(receipt, execution, "ON" if on else "OFF") or not command and not edge_proven) and state != "Adopted":
        title = "Uitkoms onbevestig" if af else "Outcome unconfirmed"
        icon = "⚠️"
    if state == "Adopted":
        title = "Toesig hervat" if af else "Supervision resumed"
        icon = "🔄"
    lines = [f"<b>{icon} ROOTLINE · {escape(label)} · {title}</b>"]
    if stamp: lines.append(stamp)
    if state == "Adopted":
        lines += ["", "ROOTLINE hou outomaties toesig oor hierdie bestaande lopie." if af else "ROOTLINE has resumed supervision of this existing run."]
    elif command:
        proven = accepted(receipt, execution, "ON" if on else "OFF")
        lines += ["", ("Die "+("AAN" if on else "AF")+"-opdrag is aanvaar." if af else
            ("ON" if on else "OFF")+" command accepted.") if proven else
            ("Die opdraguitkoms is onbevestig." if af else "Command outcome unconfirmed.")]
    else:
        lines += ["", ("Die beheerder is AAN bevestig." if af else "Controller ON confirmed.") if on and edge_proven else
            ("Die beheerder is AF bevestig." if af else "Controller OFF confirmed.") if closed else
            ("Die afskakeling is onbevestig." if af else "Shutdown unconfirmed.")]
    duration = execution.get("planned_runtime_seconds", execution.get("maximum_duration_seconds"))
    if on and type(duration) is int and duration > 0:
        lines.append(("Beplande lopie: " if af else "Planned run: ")+f"{duration/60:g} min.")
    reason = str(execution.get("reason") or execution.get("stop_reason") or "")
    reasons = {
        "energy_stop": ("Die kragvoorwaardes laat verdere werking nie toe nie.", "Power conditions no longer allow the run."),
        "owner_requested_stop": ("Gestop op jou versoek.", "Stopped at your request."),
        "active_weather_rain_hold": ("Gestop weens reën.", "Stopped because of rain."),
        "primary_deadline_reached": ("Die beplande looptyd is bereik.", "The scheduled run time was reached."),
    }
    if reason in reasons: lines.append(reasons[reason][0 if af else 1])
    if device == "FERTILIZER-INJECTION-CH1" and command and closed:
        from modules.telemetry.rootline_command_acceptance import injector_target_timing
        timing = injector_target_timing(execution)
        if timing:
            lines.append("Teiken: 120 s vanaf aanvaarde AAN." if af else "Target: 120 s from accepted ON.")
        if timing and timing.get("off_acceptance_offset_seconds", 0) > 0:
            late = timing["off_acceptance_offset_seconds"]
            lines.append((f"⚠️ AF-opdrag {late:g} s na die teiken aanvaar." if af else
                f"⚠️ OFF command accepted {late:g} s after the target."))
    if interrupted:
        elapsed = execution.get("commanded_runtime_seconds") if command else execution.get("verified_runtime_seconds")
        if type(elapsed) is int and elapsed >= 0 and type(duration) is int and duration > 0:
            lines.append(("Hierdie lopie: " if af else "This run: ")+f"{round(elapsed/60,1):g} / {duration/60:g} min.")
        lines.append("Program nog onvoltooid; ROOTLINE heroorweeg die oorblywende werk." if af else
            "Programme unfinished; ROOTLINE will reassess the remaining work.")
    if on:
        lines.append("ROOTLINE hanteer die afskakeling outomaties." if af else "ROOTLINE manages the stop automatically.")
    lines += ["", f'<a href="{IRRIGATION_URL}">'+("Plan en geskiedenis" if af else "Plan and history")+"</a>"]
    return "\n".join(lines)
