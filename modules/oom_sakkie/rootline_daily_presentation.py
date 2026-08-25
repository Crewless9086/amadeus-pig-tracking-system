"""One daily, provider-bound ROOTLINE owner presentation on the existing rail."""

from __future__ import annotations

from datetime import datetime, time, timezone
import html
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo
from modules.oom_sakkie.rootline_material import rootline_material_digest, owner_reason_material
from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority
from modules.telemetry.rootline_irrigation_lifecycle import (
    project_zone_lifecycle, validate_zone_lifecycle,
)

SAST = ZoneInfo("Africa/Johannesburg")
DAILY_PLAN_TIME = time(7, 0)
CONTRACT_VERSION = "oom_sakkie_rootline_daily_presentation.v1"
ZONES = ("B12345", "C12345")


def owner_zone_decision(result: Mapping[str, Any], recommendation: Mapping[str, Any],
                        *, zone: str, language: str = "en") -> str:
    """Project one zone from validated lifecycle truth for any owner surface."""
    af = str(language).casefold().startswith("af")
    lifecycle = (validate_zone_lifecycle(
        (result.get("irrigation_lifecycle") or {}).get(zone), zone_id=zone)
        or project_zone_lifecycle(zone_id=zone, recommendation=recommendation))
    return _lifecycle_decision(lifecycle, recommendation, af, zone=zone)


def owner_reason(value: Any, *, language: str = "en") -> str:
    """Collapse internal reason tokens to the bounded owner presentation."""
    return _short_reason(str(value or ""), str(language).casefold().startswith("af"))


def owner_window(value: Any) -> str:
    return _human_window(value)


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
        retry_authority = issue_delivery_retry_authority(mission_id=identity,
            card_mission_id=identity, text=str(packet.get("answer") or ""),
            proof_identity=f"{identity}-MARK_FAILED-1")
    else:
        retry_authority = None
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
    delivery = deliver(parsed, {"success": True, "status": "rootline_daily_plan",
        "answer": packet["answer"]}, specialist="ROOTLINE", mission_id=identity,
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
    af = str(language).casefold().startswith("af")
    recommendations = {str(row.get("subject") or ""): row for row in result.get("recommendations") or ()
                       if isinstance(row, Mapping)}
    lines = ["<b>ROOTLINE — VANDAG SE WATERPLAN</b>" if af else
             "<b>ROOTLINE — TODAY’S WATER PLAN</b>", ""]
    reasons = []
    for zone, label in (("B12345", "B Kamp" if af else "B Camp"),
                        ("C12345", "C Kamp" if af else "C Camp")):
        row = recommendations.get(zone, {})
        decision = owner_zone_decision(result, row, zone=zone, language=language)
        window = _human_window(row.get("preferred_window"))
        suffix = f" · {html.escape(window)}" if window and window.lower() not in {"unavailable", "unknown"} else ""
        lines.append(f"• <b>{label}:</b> {decision}{suffix}")
        reason = str(row.get("reason") or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    why = _short_reason(reasons[0] if reasons else str(result.get("reason") or ""), af)
    brief = result.get("owner_brief") if isinstance(result.get("owner_brief"), Mapping) else {}
    question = _owner_question(brief.get("family_fact_needed"))
    next_check = _human_reassessment(brief.get("reassess") or _next_reassessment(result), now_hint=result.get("evidence_cutoff"))
    lines.extend(["",
        f"<b>{'Hoekom' if af else 'Why'}:</b> {html.escape(why)}",
        f"<b>{'Wat ek van jou nodig het' if af else 'What I need from you'}:</b> " +
        (html.escape(question) if question else ("Niks" if af else "Nothing")),
        f"<b>{'Volgende outomatiese herbeoordeling' if af else 'Next automatic reassessment'}:</b> " +
        html.escape(next_check or ("Op die volgende 15-minuut siklus" if af else "On the next 15-minute cycle"))])
    if not question:
        lines.extend(["", "Geen aksie word van jou vereis nie." if af else "No action required from you."])
    return "\n".join(lines)


def compose_daily_rootline_manager_item(result: Mapping[str, Any], *, language="en") -> Mapping[str, str]:
    """Plain-text ROOTLINE projection for the shared Charl/Anton manager brief."""
    af = str(language).casefold().startswith("af")
    recommendations = {str(row.get("subject") or ""): row
        for row in result.get("recommendations") or () if isinstance(row, Mapping)}
    decisions = []
    reasons = []
    for zone, label in (("B12345", "B Kamp" if af else "B Camp"),
                        ("C12345", "C Kamp" if af else "C Camp")):
        row = recommendations.get(zone, {})
        decisions.append(f"{label}: {owner_zone_decision(result, row, zone=zone, language=language)}")
        reason = str(row.get("reason") or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    brief = result.get("owner_brief") if isinstance(result.get("owner_brief"), Mapping) else {}
    question = _owner_question(brief.get("family_fact_needed"))
    reassess = _human_reassessment(brief.get("reassess") or _next_reassessment(result),
        now_hint=result.get("evidence_cutoff"))
    return {
        "title": ("Besproeiing: " if af else "Irrigation: ") + "; ".join(decisions),
        "why": _short_reason(reasons[0] if reasons else str(result.get("reason") or ""), af),
        "next_action": (("ROOTLINE heroorweeg outomaties" if af else
                         "ROOTLINE will reassess automatically")
                        + (f" {reassess}" if reassess else "")),
        "question": question,
    }


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
                        af: bool, *, zone: str) -> str:
    state = str(lifecycle.get("state") or "Held")
    if state == "Started":
        return "Loop tans" if af else "Currently running"
    if state == "Authorized":
        return "Gereed — begin veilig" if af else "Ready — starting safely"
    if state == "Eligible":
        reason = str(recommendation.get("reason") or "").casefold()
        if "insufficient" in reason or "not establish enough" in reason:
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
        if lifecycle.get("watering_need_proven_false") is True:
            return ("Loop nie — het nie water nodig nie" if af else
                    "Not running — does not need watering")
        return "Loop nie" if af else "Not running"
    if state == "Failed":
        return ("Veilig teruggehou — probleem word outomaties nagegaan" if af else
                "Held safely — problem under automatic review")
    if state == "Completed":
        if _verified_completion(lifecycle, zone):
            return "Voltooi — af en geverifieer" if af else "Completed — off and verified"
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


def _short_reason(value: str, af: bool) -> str:
    text = " ".join(str(value or "").split())
    if owner_reason_material(text) == "canonical_decision_reason":
        return ("Vars kanonieke bewyse bepaal die huidige besluit." if af else
                "Fresh canonical evidence determines the current decision.")
    if not text:
        return "Vars kanonieke bewyse bepaal die huidige besluit." if af else "Fresh canonical evidence determines the current decision."
    sentence = text.split(". ", 1)[0].rstrip(".") + "."
    return sentence[:300]


def _owner_question(value: Any) -> str:
    text = " ".join(str(value or "").split())
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


def _human_window(value):
    text = " ".join(str(value or "").split())
    if not text or text.casefold() in {"unavailable", "unknown", "on_material_evidence_change"}:
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
    if text in {"refresh_missing_or_stale_evidence", "on_material_evidence_change"}:
        return "when conditions change"
    return text or "on the next automatic check"


def _daily_due(now: datetime) -> datetime:
    return now.replace(hour=7, minute=0, second=0, microsecond=0)


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _safe(status: str, *, success=True) -> dict[str, Any]:
    return {"success": success, "status": status, "telegram_sends": 0, "telegram_edits": 0,
            "hardware_commands": 0, "writes_farm_data": False,
            "automatic_irrigation_authority": False}
