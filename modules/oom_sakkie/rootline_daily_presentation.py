"""One daily, provider-bound ROOTLINE owner presentation on the existing rail."""

from __future__ import annotations

from datetime import datetime, time, timezone
import html
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo
from modules.oom_sakkie.rootline_material import rootline_material_digest
from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority

SAST = ZoneInfo("Africa/Johannesburg")
DAILY_PLAN_TIME = time(7, 0)
CONTRACT_VERSION = "oom_sakkie_rootline_daily_presentation.v1"
ZONES = ("B12345", "C12345")


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
        decision = _decision(row.get("status") or row.get("recommendation"), af)
        window = _human_window(row.get("preferred_window"))
        suffix = f" · {html.escape(window)}" if window and window.lower() not in {"unavailable", "unknown"} else ""
        prefix = "Aanbeveling: " if af else "Recommendation: "
        lines.append(f"• <b>{label}:</b> {prefix}{decision}{suffix}")
        reason = str(row.get("reason") or "").strip()
        if reason and reason not in reasons:
            reasons.append(reason)
    why = _short_reason(reasons[0] if reasons else str(result.get("reason") or ""), af)
    brief = result.get("owner_brief") if isinstance(result.get("owner_brief"), Mapping) else {}
    question = str(brief.get("family_fact_needed") or "").strip()
    next_check = _human_reassessment(brief.get("reassess") or _next_reassessment(result), now_hint=result.get("evidence_cutoff"))
    execution = ("<b>Uitvoering:</b> Nog nie gemagtig of begin nie; ROOTLINE toets "
                 "varsheid, veiligheidsgrense en staande magtiging voor enige AAN-opdrag."
                 if af else "<b>Execution:</b> Not yet authorized or started; ROOTLINE checks "
                 "freshness, safety gates and standing authority before any ON command.")
    lifecycle = ("<b>Lewensiklus:</b> Aanbeveling aangeteken · Gemagtig: wag · Begin: nee "
                 "· Voltooi: nee · Gehou: veiligheidshekke · Misluk: nee" if af else
                 "<b>Lifecycle:</b> Recommendation recorded · Authorized: pending · Started: no "
                 "· Completed: no · Held: safety gates · Failed: no")
    lines.extend(["", execution, lifecycle,
        f"<b>{'Hoekom' if af else 'Why'}:</b> {html.escape(why)}",
        f"<b>{'Wat ek van jou nodig het' if af else 'What I need from you'}:</b> " +
        (html.escape(question) if question else ("Niks" if af else "Nothing")),
        f"<b>{'Volgende outomatiese herbeoordeling' if af else 'Next automatic reassessment'}:</b> " +
        html.escape(next_check or ("Op die volgende 15-minuut siklus" if af else "On the next 15-minute cycle"))])
    if not question:
        lines.extend(["", "Geen aksie word van jou vereis nie." if af else "No action required from you."])
    return "\n".join(lines)


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
        return "Run"
    if text in {"hold", "do not run", "do_not_run", "completed"}:
        return "Hou" if af else "Hold"
    return "Data nodig" if af else "Needs Data"


def _short_reason(value: str, af: bool) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return "Vars kanonieke bewyse bepaal die huidige besluit." if af else "Fresh canonical evidence determines the current decision."
    sentence = text.split(". ", 1)[0].rstrip(".") + "."
    return sentence[:300]


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
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(SAST)
        return f"around {parsed:%H:%M}"
    except (TypeError, ValueError):
        pass
    import re
    match = re.search(r"\bat\s+(\d{4}-\d{2}-\d{2}T\d{2}:\d{2})", text)
    if match:
        try:
            parsed = datetime.fromisoformat(match.group(1)).astimezone(SAST)
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
