"""One daily, provider-bound ROOTLINE owner presentation on the existing rail."""

from __future__ import annotations

from modules.telemetry.rootline_device_registry import IRRIGATION_ZONE_IDS

from datetime import datetime, time, timezone
import html
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo
from modules.oom_sakkie.rootline_material import (
    rootline_material_digest, owner_reason_material, rootline_exception_material,
)
from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority
from modules.telemetry.rootline_irrigation_lifecycle import (
    project_zone_lifecycle, validate_zone_lifecycle, validated_shutdown_exceptions,
)

SAST = ZoneInfo("Africa/Johannesburg")
DAILY_PLAN_TIME = time(6, 30)
CONTRACT_VERSION = "oom_sakkie_rootline_daily_presentation.v1"
ZONES = IRRIGATION_ZONE_IDS


def owner_zone_decision(result: Mapping[str, Any], recommendation: Mapping[str, Any],
                        *, zone: str, language: str = "en", daily_plan: bool = False) -> str:
    """Project one zone from validated lifecycle truth for any owner surface."""
    af = str(language).casefold().startswith("af")
    lifecycle = (validate_zone_lifecycle(
        (result.get("irrigation_lifecycle") or {}).get(zone), zone_id=zone)
        or project_zone_lifecycle(zone_id=zone, recommendation=recommendation))
    return _lifecycle_decision(lifecycle, recommendation, af, zone=zone, daily_plan=daily_plan)


def owner_reason(value: Any, *, language: str = "en") -> str:
    """Collapse internal reason tokens to the bounded owner presentation."""
    return _short_reason(str(value or ""), str(language).casefold().startswith("af"))


def owner_window(value: Any) -> str:
    return _human_window(value)


def owner_notification_required(result: Mapping[str, Any]) -> bool:
    """Notify only for an owner decision or a material execution transition."""
    brief = result.get("owner_brief") if isinstance(result.get("owner_brief"), Mapping) else {}
    if _owner_question(brief.get("family_fact_needed")):
        return True
    lifecycle = result.get("irrigation_lifecycle")
    if not isinstance(lifecycle, Mapping):
        # Legacy callers without typed lifecycle keep their existing delivery
        # contract. The production planner always supplies typed lifecycle.
        return True
    if rootline_exception_material(result):
        return True
    return any(str((lifecycle.get(zone) or {}).get("state") or "") in {
        "Requested", "Started", "Completed", "Failed"
    } for zone in ZONES if isinstance(lifecycle.get(zone), Mapping))


def present_daily_rootline_plan(*, owner_user_id: str, chat_id: str,
                                specialist_loader: Callable[[], Mapping[str, Any]],
                                state_store: Callable[[str, str, Any], Any],
                                deliver: Callable[..., Mapping[str, Any]],
                                now: datetime | None = None, language: str = "en") -> dict[str, Any]:
    now = _aware(now or datetime.now(timezone.utc)).astimezone(SAST)
    if not owner_user_id or owner_user_id != chat_id:
        return _safe("rootline_daily_binding_invalid", success=False)
    if now.timetz().replace(tzinfo=None) < DAILY_PLAN_TIME:
        return {**_safe("rootline_daily_not_due"), "next_due_at": _daily_due(now).isoformat()}
    identity = f"OOM-ROOTLINE-DAILY-{owner_user_id}-{now:%Y%m%d}"
    existing = state_store("load_identity", identity, None) or {}
    if existing.get("delivery_state") == "delivered":
        return {**_safe("rootline_daily_replayed_noop"), "daily_identity": identity,
                "provider_message_id": str(existing.get("provider_message_id") or "")}
    if existing.get("delivery_state") == "ambiguous":
        return {**_safe("rootline_daily_delivery_ambiguous", success=False),
                "daily_identity": identity}
    if existing.get("delivery_state") == "failed":
        attempt = int(existing.get("attempt_count") or 1) + 1
        if attempt > 2:
            return {**_safe("rootline_daily_delivery_failed", success=False),
                    "daily_identity": identity}
        packet = {**existing, "delivery_state": "pending", "attempt_count": attempt}
        claimed = state_store(f"claim_retry_{attempt}", identity, packet)
    else:
        try:
            result = specialist_loader()
        except Exception:
            result = {}
        if not _fresh_result(result, now):
            return {**_safe("rootline_daily_waiting_for_fresh_evidence"),
                    "daily_identity": identity, "retry_on_next_scheduler_tick": True}
        material = rootline_material_digest(result)
        packet = {"contract_version": CONTRACT_VERSION, "identity": identity,
            "owner_user_id": owner_user_id, "chat_id": chat_id,
            "operating_date": now.date().isoformat(), "material_digest": material,
            "evidence_cutoff": str(result.get("evidence_cutoff") or ""),
            "delivery_state": "pending", "attempt_count": 1,
            "answer": compose_daily_rootline_plan(result, language=language)}
        claimed = state_store("claim_pending", identity, packet)
    if not isinstance(claimed, Mapping) or claimed.get("success") is not True:
        return _safe("rootline_daily_claim_unproven", success=False)
    bound = state_store("load_identity", identity, None) or packet
    if any(str(bound.get(key) or "") != str(packet[key])
           for key in ("owner_user_id", "chat_id", "operating_date", "material_digest")):
        return _safe("rootline_daily_claim_conflict", success=False)
    if claimed.get("created") is False:
        return {**_safe("rootline_daily_claim_pending"), "daily_identity": identity}
    parsed = {"telegram_user_id": owner_user_id, "telegram_chat_id": chat_id,
        "provider_message_id": f"scheduled:{identity}", "provider_timestamp": now.isoformat(),
        "semantic": {"domain": "water_energy", "intent": "rootline_daily_plan", "language": language}}
    visible_result = {"success": True, "status": "rootline_daily_plan", "answer": packet["answer"],
        "recipient_render_contract": "specialist_structured_recipient_v1", "recipient_language": language}
    retry_authority = None
    if existing.get("delivery_state") == "failed":
        from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result
        from modules.oom_sakkie.family_presentation import envelope
        localized = localize_recipient_result(parsed, visible_result, "ROOTLINE")
        retry_authority = issue_delivery_retry_authority(mission_id=identity,
            card_mission_id=identity, text=envelope(localized.get("answer")),
            proof_identity=f"{identity}-MARK_FAILED-1")
    delivery = deliver(parsed, visible_result, specialist="ROOTLINE", mission_id=identity,
        card_mission_id=identity, delivery_retry_authority=retry_authority)
    if delivery.get("success") is True and delivery.get("telegram_message_id"):
        proof = {**packet, "delivery_state": "delivered",
            "provider_message_id": str(delivery["telegram_message_id"]),
            "provider_timestamp": str(delivery.get("provider_timestamp") or "")}
        stored = state_store("mark_delivered", identity, proof)
        if not isinstance(stored, Mapping) or stored.get("success") is not True:
            return _safe("rootline_daily_delivery_persistence_unproven", success=False)
        return {**_safe("rootline_daily_delivered"), "daily_identity": identity,
            "material_digest": packet["material_digest"], "telegram_sends": int(delivery.get("telegram_sends") or 1),
            "provider_message_id": proof["provider_message_id"], "answer": packet["answer"]}
    if delivery.get("delivery_definitely_not_sent") is not True:
        state_store("mark_ambiguous", identity, {**packet, "delivery_state": "ambiguous"})
        return {**_safe("rootline_daily_delivery_ambiguous", success=False),
                "daily_identity": identity}
    attempt = int(packet.get("attempt_count") or 1)
    failed = state_store(f"mark_failed_{attempt}", identity,
        {**packet, "delivery_state": "failed", "attempt_count": attempt,
         "failure_status": str(delivery.get("status") or "delivery_failed")})
    if not isinstance(failed, Mapping) or failed.get("success") is not True:
        return {**_safe("rootline_daily_failure_persistence_unproven", success=False),
                "daily_identity": identity}
    return {**_safe("rootline_daily_delivery_failed_retryable" if attempt < 2
                    else "rootline_daily_delivery_failed", success=False),
            "daily_identity": identity, "retry_on_next_scheduler_tick": attempt < 2}


def compose_daily_rootline_plan(result: Mapping[str, Any], *, language="en") -> str:
    """Compact daily plan/result using the same typed lifecycle and delivery identity."""
    from modules.oom_sakkie.rootline_activity_presentation import IRRIGATION_URL
    from modules.oom_sakkie.rootline_transition_notifications import input_health_text, provider_availability_text
    from modules.telemetry.rootline_command_acceptance import enabled
    af = str(language).casefold().startswith("af")
    recommendations = {str(row.get("subject") or ""): row for row in result.get("recommendations") or ()
                       if isinstance(row, Mapping)}
    decisions = {zone: owner_zone_decision(result, recommendations.get(zone, {}), zone=zone, language=language, daily_plan=True)
                 for zone in IRRIGATION_ZONE_IDS}
    complete = all(value == ("Program voltooi" if af else "Programme completed") for value in decisions.values())
    heading = ("Vandag se kampresultate" if af else "Today's camp results") if complete else ("Vandag se plan" if af else "Today's plan")
    day = str(result.get("operating_date") or "")
    dated = _daily_date(day, af)
    lines = [f"<b>🌿 ROOTLINE · {heading}</b>"]
    if dated: lines.append(html.escape(dated))
    lines.append("")
    if not enabled():
        availability = provider_availability_text(result.get("provider_availability"), language=language)
        if availability: lines.extend([html.escape(availability), ""])
    summary = input_health_text(result.get("input_health"), language=language)
    credit = _forecast_credit(result, language=language, html_link=True)
    weather_line = html.escape(summary)
    fallback_source = "die rugsteunbron" if af else "the backup source"
    credit_prefix = "Weervoorspelling deur " if af else "Forecast by "
    if credit and fallback_source in weather_line:
        linked_provider = credit.removeprefix(credit_prefix).removesuffix(".")
        weather_line = weather_line.replace(fallback_source,
            linked_provider + (" (rugsteun)" if af else " (backup)"), 1)
    elif credit:
        weather_line = " ".join(part for part in (weather_line, credit) if part)
    if weather_line: lines.extend([weather_line, ""])
    if result.get("control_observation") in {"deadline_deferred", "unverified"}:
        lines.extend(["⏳ Die jongste toerustingkontrole is nog onbevestig; ROOTLINE kontroleer weer outomaties." if af else
            "⏳ The latest equipment check is unconfirmed; ROOTLINE will check again automatically.", ""])
    # Only publish an order when every scheduled camp has a canonical start time.
    planned = [row for row in recommendations.values() if row.get("subject") in IRRIGATION_ZONE_IDS
        and row.get("planned_duration_minutes")]
    def planned_time(row):
        try:
            value = datetime.fromisoformat(str(row.get("planned_start_at")).replace("Z", "+00:00"))
            return value if value.tzinfo is not None else None
        except (ValueError, TypeError):
            return None
    if planned and all(planned_time(row) is not None for row in planned):
        planned.sort(key=planned_time)
        lines.append(("Volgorde: " if af else "Order: ")+" → ".join(html.escape(row["subject"][0]) for row in planned))
    ordered_zones = [row["subject"] for row in sorted(planned, key=lambda row: (planned_time(row) is None, planned_time(row) or datetime.max.replace(tzinfo=timezone.utc)))]
    ordered_zones += [zone for zone in IRRIGATION_ZONE_IDS if zone not in ordered_zones]
    for zone in ordered_zones:
        row = recommendations.get(zone, {})
        label = zone[0]+(" Kamp" if af else " Camp")
        decision = decisions[zone]
        icon = "✅" if decision in {"Programme completed", "Program voltooi"} else "•"
        window = _planned_window(row)
        suffix = f" · {html.escape(window)}" if window else ""
        minutes = row.get("planned_duration_minutes")
        if isinstance(minutes, (int, float)) and not isinstance(minutes, bool) and minutes > 0:
            suffix += f" · {minutes:g} min"
        lines.append(f"{icon} <b>{label}:</b> {html.escape(decision)}{suffix}")
    for identity, label in (("fertilizer_mixing", "Menger" if af else "Mixer"),
            ("fertilizer_injection", "Inspuiting" if af else "Injection"), ("borehole", "Borehole")):
        row = recommendations.get(identity)
        # Advisory auxiliary eligibility is not an actual device state.
        # Run/stop results arrive through the canonical activity-notice rail.
        if row and row.get("status") == "Hold" and row.get("owner_action_required") is True:
            lines.append(f"⚠️ <b>{label}:</b> {html.escape(_short_reason(str(row.get('reason') or ''), af))}")
    reasons = [str(row.get("reason") or "") for row in recommendations.values() if row.get("subject") in IRRIGATION_ZONE_IDS]
    generic = "Current irrigation need and dry observed weather support the scheduled irrigation run."
    useful_reasons = [reason for reason in reasons if " ".join(reason.split()) != generic]
    fallback = str(result.get("reason") or "")
    raw_reason = next((reason for reason in useful_reasons if reason), fallback if " ".join(fallback.split()) != generic else "")
    why = _short_reason(raw_reason, af) if raw_reason else ""
    if why: lines.extend(["", html.escape(why)])
    brief = result.get("owner_brief") if isinstance(result.get("owner_brief"), Mapping) else {}
    question = _localized_owner_question(result, brief, af)
    next_check = _human_reassessment(brief.get("reassess") or _next_reassessment(result))
    if next_check.startswith("around "):
        lines.append(("Volgende kontrole: " if af else "Next check: ")+(next_check.replace("around ", "omtrent ") if af else next_check))
    if question: lines.extend(["", "❓ "+html.escape(question)])
    lines.extend(["", f'<a href="{IRRIGATION_URL}">'+("Volledige plan, instellings en geskiedenis" if af else "Full plan, settings and history")+"</a>"])
    return "\n".join(lines)



def _daily_date(value, af=False):
    """Render the actual operating date without locale or unsupported HTML tags."""
    try:
        from datetime import date
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        return ""
    weekdays = ("Ma", "Di", "Wo", "Do", "Vr", "Sa", "So") if af else ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
    months = ("Jan", "Feb", "Mrt", "Apr", "Mei", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Des") if af else ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
    suffix = ("ˢᵗᵉ" if day.day in {1, 8} or day.day >= 20 else "ᵈᵉ") if af else (
        "ᵗʰ" if 11 <= day.day % 100 <= 13 else {1: "ˢᵗ", 2: "ⁿᵈ", 3: "ʳᵈ"}.get(day.day % 10, "ᵗʰ"))
    return f"{weekdays[day.weekday()]} {day.day}{suffix}, {months[day.month-1]} {day.year}"


def compose_daily_rootline_manager_item(result: Mapping[str, Any], *, language="en") -> Mapping[str, str]:
    """Plain-text ROOTLINE projection for the shared Charl/Anton manager brief."""
    af = str(language).casefold().startswith("af")
    recommendations = {str(row.get("subject") or ""): row
        for row in result.get("recommendations") or () if isinstance(row, Mapping)}
    decisions = []
    reasons = []
    for zone in IRRIGATION_ZONE_IDS:
        label = zone[0] + (" Kamp" if af else " Camp")
        row = recommendations.get(zone, {})
        decisions.append(f"{label}: {owner_zone_decision(result, row, zone=zone, language=language)}")
        reason = str(row.get("reason") or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    brief = result.get("owner_brief") if isinstance(result.get("owner_brief"), Mapping) else {}
    question = _localized_owner_question(result, brief, af)
    reassess = _human_reassessment(brief.get("reassess") or _next_reassessment(result),
        now_hint=result.get("evidence_cutoff"))
    return {
        "title": ("Besproeiing: " if af else "Irrigation: ") + "; ".join(decisions),
        "why": " ".join(filter(None, (
            _short_reason(reasons[0] if reasons else str(result.get("reason") or ""), af),
            _forecast_credit(result, language=language)))),
        "next_action": (("ROOTLINE heroorweeg outomaties" if af else
                         "ROOTLINE will reassess automatically")
                        + (" wanneer vars lesings of veranderde toestande beskikbaar is." if af else
                           " when fresh readings or changed conditions are available.")),
        "question": question,
        "notification_decision_identity": _owner_question_identity(result, brief),
    }


def _forecast_credit(result: Mapping[str, Any], *, language="en", html_link=False) -> str:
    """Credit the selected forecast provider without trusting payload markup."""
    from modules.telemetry.weather_service import forecast_attribution
    forecast = result.get("forecast")
    source = forecast.get("source") if isinstance(forecast, Mapping) else None
    credit = forecast_attribution(source.get("provider")) if isinstance(source, Mapping) else {}
    if not credit:
        return ""
    prefix = "Weervoorspelling deur" if str(language).casefold().startswith("af") else "Forecast by"
    name = html.escape(credit["name"]) if html_link else credit["name"]
    if html_link:
        name = f'<a href="{html.escape(credit["url"], quote=True)}">{name}</a>'
    return f"{prefix} {name}."


def manager_brief_facts(result: Mapping[str, Any]) -> dict[str, Any]:
    """Display-only facts; the existing textual/material projection is intact."""
    recommendations = {str(row.get("subject") or ""): row
        for row in result.get("recommendations") or () if isinstance(row, Mapping)}
    return {"kind": "irrigation_status",
        **({"provider_availability": result["provider_availability"]}
           if isinstance(result.get("provider_availability"), Mapping) else {}),
        "zones": [{"zone": zone,
        "status": owner_zone_decision(result, recommendations.get(zone, {}), zone=zone, language="en"),
        "recommendation": str(recommendations.get(zone, {}).get("status") or
                              recommendations.get(zone, {}).get("recommendation") or ""),
        "reason": str(recommendations.get(zone, {}).get("reason") or result.get("reason") or "").strip()}
        for zone in ZONES]}


def _fresh_result(result: Any, now: datetime) -> bool:
    if not isinstance(result, Mapping) or result.get("success") is not True:
        return False
    try:
        cutoff = datetime.fromisoformat(str(result.get("evidence_cutoff") or "").replace("Z", "+00:00"))
        cutoff = _aware(cutoff).astimezone(SAST)
    except (TypeError, ValueError):
        return False
    return cutoff <= now and (now - cutoff).total_seconds() <= 30 * 60


def _decision(value: Any, af: bool) -> str:
    text = str(value or "").casefold()
    if text in {"recommend", "run", "proceed", "eligible"} or text.startswith("run "):
        return "Aanbeveling - besproei" if af else "Recommendation - irrigate"
    if text in {"hold", "do not run", "do_not_run"}:
        return "Hou" if af else "Hold"
    if text == "completed":
        return "Voltooi" if af else "Completed"
    return "Data nodig" if af else "Needs Data"


def _lifecycle_decision(lifecycle: Mapping[str, Any], recommendation: Mapping[str, Any],
                        af: bool, *, zone: str, daily_plan: bool = False) -> str:
    exceptions = validated_shutdown_exceptions(lifecycle, zone_id=zone)
    if exceptions:
        if any(row["controller_off_verified"] is False for row in exceptions):
            return ("Afskakeling van 'n aangetekende lopie is onbevestig — ROOTLINE kontroleer dit" if af else
                    "A recorded run has unverified shutdown — ROOTLINE is checking")
        # A later OFF observation does not establish an overrun. Retain that
        # historical diagnostic in the ledger; current decisions use current
        # state once shutdown is verified, rather than repeating an old alarm.
    state = str(lifecycle.get("state") or "Held")
    if state == "Requested":
        return "Aangevra — wag vir beheerder" if af else "Requested — awaiting controller"
    if state == "Started":
        if lifecycle.get("acceptance_mode") == "command_accepted":
            return "Program loop — AAN-opdrag aanvaar" if af else "Programme running — ON accepted"
        return "Loop tans" if af else "Currently running"
    if state == "Authorized":
        return "Gereed — begin veilig" if af else "Ready — starting safely"
    if state == "Eligible":
        reason = str(recommendation.get("reason") or "").casefold()
        held_recommendation = any(str(recommendation.get(key) or "").casefold() in {
            "hold", "held", "defer", "deferred", "do not run", "do_not_run"}
            for key in ("status", "recommendation"))
        if held_recommendation or "insufficient" in reason or "not establish enough" in reason:
            # Conflicting readiness and watering-need evidence is not a ready
            # instruction. Keep it on ROOTLINE's automatic safe revalidation
            # path until one coherent canonical result exists.
            return "Kontroleer veiligheid" if af else "Checking safely"
        return ("Gereed na die finale veiligheidskontrole" if af else
                "Ready after the final safety check")
    if state == "Revalidating":
        return "Kontroleer veiligheid" if af else "Checking safely"
    if state == "Recommended":
        return "Moet natgemaak word" if af else "Needs watering"
    if state == "Held":
        # Shared manager facts retain their established status vocabulary.
        # Only the daily plan uses advisory wording; evidence rules stay shared.
        if not daily_plan:
            if lifecycle.get("watering_need_proven_false") is True:
                return "Loop nie — het nie water nodig nie" if af else "Not running — does not need watering"
            return "Loop nie" if af else "Not running"
        if lifecycle.get("watering_need_proven_false") is True:
            return ("Nie beplan nie — het nie water nodig nie" if af else
                    "Not planned — does not need watering")
        return "Plan wag" if af else "Plan on hold"
    if state == "Failed":
        return ("Lopie se uitkoms onbevestig — ROOTLINE ondersoek dit" if af else
                "Run outcome unconfirmed — ROOTLINE is reviewing")
    if state == "Completed":
        if (lifecycle.get("completion_evidence") or {}).get("command_job_completed") is True:
            return "Program voltooi" if af else "Programme completed"
        if _verified_completion(lifecycle, zone):
            return "Beheerder AF geverifieer" if af else "Controller OFF verified"
        if daily_plan:
            return "Voltooiing onbevestig" if af else "Completion unconfirmed"
        return "Loop nie" if af else "Not running"
    return "Data nodig" if af else "Needs Data"


def _verified_completion(lifecycle: Mapping[str, Any], zone: str) -> bool:
    evidence = lifecycle.get("completion_evidence")
    if not isinstance(evidence, Mapping) or str(evidence.get("zone_id") or "") != zone:
        return False
    shutdown = evidence.get("shutdown_evidence")
    return (evidence.get("shutdown_verified") is True
            and (evidence.get("objective_satisfied") is True
                 or evidence.get("qualifies_as_completed_watering") is True)
            and isinstance(shutdown, Mapping)
            and shutdown.get("authoritative") is True
            and str(shutdown.get("state") or "").upper() == "OFF")


# These are exact outputs of ROOTLINE's typed deterministic need classifier.
# Unknown prose is not translated by guessing or trusted by a render flag.
_AF_CLASSIFIER_REASONS = {
    "Weekly irrigation demand, water and dry observed weather support one bounded gravity-fed segment.":
        "Die week se besproeiingsbehoefte, beskikbare water en droë waargenome weer ondersteun een begrensde swaartekragbesproeiingsegment.",
    "Urgent water need supports one bounded gravity-fed segment with the native fail-stop.":
        "Dringende waterbehoefte ondersteun een begrensde swaartekragbesproeiingsegment met die ingeboude veiligheidsafskakeling.",
    "Urgent water continuity outweighs strict grid avoidance; retain the bounded native fail-stop.":
        "Dringende watervoorsiening weeg swaarder as die vermyding van netwerkkrag; behou die begrensde veiligheidsafskakeling.",
    "Available evidence does not establish enough current deficit for irrigation.":
        "Die beskikbare bewyse toon nie genoeg huidige watertekort om besproeiing te regverdig nie.",
    "Summer evaporation favours an evening or night window.":
        "Somerverdamping bevoordeel besproeiing in die aand of nag.",
    "Water need is supported but fresh power evidence is required at execution time.":
        "Die waterbehoefte is bewys, maar vars kraglesings is nodig voordat uitvoering begin.",
    "Winter daylight, surplus solar and reserve margin support a bounded daytime segment.":
        "Winterdaglig, oortollige sonkrag en die beskikbare reserwe ondersteun een begrensde dagsegment.",
    "Current need and battery margin support one bounded segment.":
        "Die huidige behoefte en batteryreserwe ondersteun een begrensde segment.",
    "Need is supported, but wait for reserve recovery or an explicitly justified water-continuity grid decision.":
        "Die behoefte is bewys, maar wag vir die herstel van die reserwe of 'n uitdruklik gemotiveerde netwerkkragbesluit vir watervoorsiening.",
}


def _owner_question_identity(result, brief):
    question = _owner_question(brief.get("family_fact_needed"))
    matching = [row for row in result.get("owner_questions") or ()
                if isinstance(row, Mapping) and str(row.get("question") or "").strip() == question
                and str(row.get("fact") or "").strip()]
    facts = {str(row["fact"]).strip() for row in matching}
    return "rootline-fact:" + next(iter(facts)) if question and len(facts) == 1 else ""


def _localized_owner_question(result, brief, af):
    question = _owner_question(brief.get("family_fact_needed"))
    if not af or not question:
        return question
    typed = next((row for row in result.get("owner_questions") or ()
                  if isinstance(row, Mapping) and str(row.get("question") or "").strip() == question), {})
    translations = {
        ("water_continuity_need", "Is there a genuine water-continuity need today: normal, needed or urgent?"):
            "Is daar vandag 'n werklike behoefte aan watervoorsiening: normaal, nodig of dringend?",
        ("current_tank_observation", "If convenient, are the tanks LOW, OK or FULL, and when was that observed?"):
            "As dit gerieflik is, is die tenks LAAG, REG of VOL, en wanneer is dit waargeneem?",
    }
    return translations.get((str(typed.get("fact") or ""), question), question)


def _short_reason(value: str, af: bool) -> str:
    text = " ".join(str(value or "").split())
    if af and text in _AF_CLASSIFIER_REASONS:
        return _AF_CLASSIFIER_REASONS[text]
    if af and text.casefold().startswith("fresh local evidence records rain"):
        return "Vars plaaslike bewyse toon reën; ROOTLINE kontroleer weer of besproeiing nodig is."
    if "durable parent objective" in text.casefold() or "_" in text:
        return ("ROOTLINE heroorweeg die plan outomaties." if af else
                "ROOTLINE is reassessing the plan automatically.")
    if owner_reason_material(text) == "canonical_decision_reason":
        return ("Vars kanonieke bewyse bepaal die huidige besluit." if af else
                "Fresh canonical evidence determines the current decision.")
    if not text:
        return "Vars kanonieke bewyse bepaal die huidige besluit." if af else "Fresh canonical evidence determines the current decision."
    sentence = text.split(". ", 1)[0].rstrip(".") + "."
    return sentence[:300]


def _owner_question(value: Any) -> str:
    text = " ".join(str(value or "").split())
    if text == "If convenient, are the tanks LOW, OK or FULL, and when was that observed?":
        return ""
    if text.casefold().rstrip(".") in {
            "no owner fact is required now", "no owner action is required now",
            "none", "nothing", "n/a"}:
        return ""
    return text


def _next_reassessment(result: Mapping[str, Any]) -> str:
    value = result.get("next_reassessment")
    if not isinstance(value, Mapping):
        return ""
    return str(value.get("at") or value.get("reason") or value.get("trigger") or "")


def _planned_window(row):
    """Both local endpoints come from the saved plan, never inferred duration."""
    try:
        start = datetime.fromisoformat(str(row.get("planned_start_at")).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(row.get("planned_end_at")).replace("Z", "+00:00"))
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            return ""
        start, end = start.astimezone(SAST), end.astimezone(SAST)
        if start.date() != end.date():
            return f"{start:%d %b %Hh%M}–{end:%d %b %Hh%M}"
        return f"{start:%Hh%M}–{end:%Hh%M}"
    except (TypeError, ValueError):
        return ""


def _human_window(value):
    text = " ".join(str(value or "").split())
    folded = text.casefold()
    if (not text or folded in {"unavailable", "unknown", "on_material_evidence_change"}
            or "_" in text or "durable parent objective" in folded):
        return ""
    return text


def _human_reassessment(value, now_hint=None):
    text = " ".join(str(value or "").split())
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        parsed = parsed.replace(tzinfo=SAST) if parsed.tzinfo is None else parsed.astimezone(SAST)
        return f"around {parsed:%H:%M}"
    except (TypeError, ValueError):
        pass
    import re
    match = re.search(r"\bat\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})", text)
    if match:
        try:
            parsed = datetime.fromisoformat(match.group(1)).replace(tzinfo=SAST)
            return f"around {parsed:%H:%M}"
        except ValueError:
            pass
    if "_" in text or text in {"refresh_missing_or_stale_evidence", "on_material_evidence_change"}:
        return "when conditions change"
    return text or "on the next automatic check"


def _daily_due(now: datetime) -> datetime:
    return now.replace(hour=DAILY_PLAN_TIME.hour, minute=DAILY_PLAN_TIME.minute, second=0, microsecond=0)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _safe(status: str, *, success=True) -> dict[str, Any]:
    return {"success": success, "status": status, "telegram_sends": 0, "telegram_edits": 0,
            "hardware_commands": 0, "writes_farm_data": False,
            "automatic_irrigation_authority": False}
