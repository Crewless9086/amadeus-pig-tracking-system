"""Authenticated natural HERDMASTER health/welfare intake for Oom Sakkie.

This is the operational bridge from the existing private Telegram gateway to
the reviewed zero-I/O HERDMASTER evaluator.  It reads canonical farm evidence
and records only private intake lifecycle evidence; it grants no farm write or
medical authority.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from modules.oom_sakkie.herdmaster_health_loss_preview import prepare_health_loss_owner_preview
from modules.pig_weights.farm_supabase_read_service import (
    get_litter_register_rows,
    get_mating_overview,
    get_pig_master_rows,
)
from modules.pig_weights.herdmaster_health_loss_recording import confirm_health_loss_preview


EVENT_SOURCE = "oom_sakkie_herdmaster_health_loss_runtime"
CONTEXT_WINDOW = timedelta(hours=24)
HEALTH_PATTERN = re.compile(
    r"\b(?:pig|tag)\s*[a-z0-9-]+\b.*\b(?:"
    r"not eating|won't eat|wont eat|laying down|lying down|acting weird|"
    r"sick|ill|injured|limping|bleeding|dead|died|farrowing|stillborn|"
    r"infection|vomit|diarrh|cough|breath|cannot stand|can't stand"
    r")\b|\b(?:sick|injured|dead|died|farrowing|stillborn)\b",
    re.I,
)
FOLLOW_UP_PATTERN = re.compile(
    r"\b(?:can|cannot|can't|cant|yes|no|stand|standing|breathe|breathing|"
    r"drink|drinking|water|bleed|bleeding|distress|responsive|unresponsive)\b",
    re.I,
)


def handle_authenticated_health_loss_message(
    parsed: Mapping[str, Any], gateway_authority, *, connect_factory=None, context_store=None
):
    """Return one useful owner response, or ``handled=False`` for other intents."""
    parsed = parsed if isinstance(parsed, Mapping) else {}
    text = str(parsed.get("text") or "").strip()
    active = _load_active_context(
        str(parsed.get("telegram_chat_id") or ""), context_store=context_store
    )
    explicit_health = bool(HEALTH_PATTERN.search(text))
    follow_up = bool(active and FOLLOW_UP_PATTERN.search(text))
    confirmation = bool(active and str(active.get("status") or "") == "preview_ready"
                        and text == "CONFIRM " + str(active.get("operation_id") or ""))
    if not explicit_health and not follow_up and not confirmation:
        return {"handled": False, "status": "health_loss_intake_not_applicable"}, 200

    provider_message_id = str(parsed.get("provider_message_id") or "").strip()
    provider_timestamp = str(parsed.get("provider_timestamp") or "").strip()
    if not provider_message_id or not provider_timestamp:
        return {"handled": True, "success": False, "status": "health_loss_provider_identity_required"}, 409

    if confirmation:
        recorded, recorded_status = confirm_health_loss_preview(
            active, text, actor_id=str(parsed.get("telegram_user_id") or ""),
            evidence_loader=lambda: load_canonical_health_loss_evidence(connect_factory=connect_factory),
            connect_factory=connect_factory,
        )
        mission_id = str(active.get("mission_id") or "")
        answer = ("✅ <b>HERDMASTER OBSERVATION RECORDED</b>\n\n"
                  "The exact confirmed factual welfare observation was recorded once. "
                  "No diagnosis or treatment was added. HERDMASTER will reassess from the refreshed evidence."
                  if recorded.get("success") else
                  "⚠️ <b>HERDMASTER RECORDING CONTAINED</b>\n\nNothing was written. The exact preview must be refreshed before confirmation.")
        lifecycle = {**dict(active), "provider_message_id": provider_message_id,
            "provider_timestamp": provider_timestamp,
            "status": "completed" if recorded.get("success") else "contained",
            "owner_text": answer, "recording_result": recorded}
        _record_lifecycle_event(lifecycle, context_store=context_store)
        return {"handled": True, "success": recorded.get("success") is True,
            "status": lifecycle["status"], "answer": answer, "mission_id": mission_id,
            "card_mission_id": mission_id, "records_audit_trace": True,
            "writes_farm_data": bool(recorded.get("writes_farm_data")),
            "rows_created": int(recorded.get("rows_created") or 0),
            "protected_actions_performed": bool(recorded.get("writes_farm_data"))}, recorded_status

    context_text = str((active or {}).get("combined_text") or "").strip() if follow_up else ""
    combined_text = f"{context_text} Follow-up: {text}".strip() if context_text else text
    evidence = load_canonical_health_loss_evidence(connect_factory=connect_factory)
    envelope = {
        "gateway_authority": gateway_authority,
        "provider_message_id": provider_message_id,
        "provider_timestamp": provider_timestamp,
        "provider_timezone": "Africa/Johannesburg",
        "text": combined_text,
    }
    preview = prepare_health_loss_owner_preview(envelope, evidence)
    owner_text = _owner_message(preview)
    mission_id = str((active or {}).get("mission_id") or "") or "OOM-HERDMASTER-" + hashlib.sha256(
        f"{parsed.get('telegram_user_id')}|{parsed.get('telegram_chat_id')}|{provider_message_id}".encode()
    ).hexdigest()[:24].upper()
    lifecycle = {
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "provider_message_id": provider_message_id,
        "provider_timestamp": provider_timestamp,
        "combined_text": combined_text,
        "status": "waiting_for_input" if int(preview.get("question_count") or 0) else "preview_ready",
        "operation_id": str((preview.get("confirmation_binding") or {}).get("operation_id") or ""),
        "evidence_generation": str(evidence.get("evidence_generation") or ""),
        "owner_text": owner_text,
        "preview": preview,
        "mission_id": mission_id,
    }
    stored = _record_lifecycle_event(lifecycle, context_store=context_store)
    if stored.get("success") is not True:
        return {"handled": True, "success": False, "status": "health_loss_lifecycle_persistence_failed"}, 503
    return {
        "handled": True,
        "success": True,
        "status": lifecycle["status"],
        "answer": owner_text,
        "tool_used": "herdmaster_health_loss_preview",
        "question_count": int(preview.get("question_count") or 0),
        "operation_id": lifecycle["operation_id"],
        "mission_id": mission_id,
        "card_mission_id": mission_id,
        "records_audit_trace": True,
        "writes_farm_data": False,
        "protected_actions_performed": False,
    }, 200


def load_canonical_health_loss_evidence(*, connect_factory=None):
    animals = []
    for row in get_pig_master_rows(connect_factory=connect_factory):
        animals.append({
            "pig_id": str(row.get("Pig_ID") or ""),
            "name": str(row.get("Pig_Name") or ""),
            "tag_number": str(row.get("Tag_Number") or ""),
            "lifecycle_status": str(row.get("Status") or "Unknown"),
            "on_farm": str(row.get("On_Farm") or "").lower() == "yes",
            "availability": str(row.get("Purpose") or "Unknown"),
            "pen": str(row.get("Current_Pen_ID") or "Unknown"),
        })
    matings = [{
        "mating_id": str(row.get("mating_id") or ""),
        "sow_pig_id": str(row.get("sow_pig_id") or ""),
        "boar_pig_id": str(row.get("boar_pig_id") or ""),
        "date": str(row.get("mating_date") or ""),
        "is_open": str(row.get("is_open") or "").lower() in {"yes", "true", "1"},
    } for row in get_mating_overview(connect_factory=connect_factory)]
    litters = [{
        "litter_id": str(row.get("Litter_ID") or ""),
        "sow_pig_id": str(row.get("Sow_Pig_ID") or ""),
        "farrowing_date": str(row.get("Farrowing_Date") or ""),
    } for row in get_litter_register_rows(connect_factory=connect_factory)]
    material = json.dumps({"animals": animals, "matings": matings, "litters": litters}, sort_keys=True, separators=(",", ":"))
    return {
        "evidence_generation": hashlib.sha256(material.encode()).hexdigest(),
        "as_of_timestamp": datetime.now(timezone.utc).isoformat(),
        "animals": animals,
        "matings": matings,
        "litters": litters,
    }


def _owner_message(preview: Mapping[str, Any]) -> str:
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    identity = evaluator.get("identity") if isinstance(evaluator.get("identity"), Mapping) else {}
    question = str(evaluator.get("smallest_missing_follow_up_question") or preview.get("owner_text") or "").strip()
    if not preview.get("success") and question:
        return f"⚠️ <b>ANIMAL CHECK NEEDED</b>\n\n{question}"
    if int(preview.get("question_count") or 0) > 0:
        label = str(identity.get("tag_number") or identity.get("name") or "the pig")
        action = str((evaluator.get("immediate_welfare_priority") or {}).get("action") or "Please check the animal now.")
        return (
            f"🚨 <b>PIG {label} NEEDS CHECKING</b>\n\n"
            "I’ve matched the report to the herd record and retained what you already told me.\n\n"
            f"<b>Check now:</b> {action}\n\n<b>One update needed:</b> {question}"
        )
    return (
        "✅ <b>HERDMASTER PREVIEW READY</b>\n\n"
        + str(preview.get("owner_text") or "")
    )


def _record_lifecycle_event(lifecycle: Mapping[str, Any], *, context_store=None):
    event_id = "OOM-HERD-HEALTH-" + hashlib.sha256(
        f"{lifecycle.get('chat_id')}|{lifecycle.get('provider_message_id')}".encode()
    ).hexdigest()[:24].upper()
    if context_store is not None:
        return context_store("record", event_id, dict(lifecycle))
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event = build_sam_live_stock_review_event(
        {"conversation_id": "oom-health-" + str(lifecycle.get("chat_id"))}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "herdmaster_health_loss_intake"},
        event_source=EVENT_SOURCE,
    )
    event["review_event_id"] = event_id
    event["review_json"] = {"herdmaster_health_loss": dict(lifecycle)}
    event["decision_json"] = {}
    event["facts_json"] = {}
    event["customer_message_excerpt"] = ""
    event["sam_reply_excerpt"] = ""
    result, status = record_sam_live_stock_review_event(event)
    return {**result, "success": status < 400 and result.get("success") is True}


def _load_active_context(chat_id: str, *, context_store=None):
    if not chat_id:
        return None
    if context_store is not None:
        return context_store("load", chat_id, None)
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        return None
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select review_json->'herdmaster_health_loss', created_at
                    from public.sam_live_stock_conversation_review_events
                    where event_source = %s
                      and chatwoot_conversation_id = %s
                    order by created_at desc
                    limit 1
                    """,
                    (EVENT_SOURCE, "oom-health-" + chat_id),
                )
                row = cursor.fetchone()
        if not row or not isinstance(row[0], dict):
            return None
        created_at = row[1]
        if created_at and datetime.now(timezone.utc) - created_at.astimezone(timezone.utc) > CONTEXT_WINDOW:
            return None
        if str(row[0].get("status") or "") not in {"waiting_for_input", "preview_ready"}:
            return None
        return row[0]
    except Exception:
        return None
