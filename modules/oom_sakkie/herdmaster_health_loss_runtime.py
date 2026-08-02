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
    r"\b(?:cannot|can't|cant|yes|no|seen alive|last seen|stand|standing|breathe|breathing|"
    r"drink|drinking|water|bleed|bleeding|distress|responsive|unresponsive|"
    r"removed|buried|disposed|cremated|body)\b",
    re.I,
)
UNRELATED_OPERATIONAL_PATTERN = re.compile(
    r"\b(?:reservoir|storage tanks?|borehole|irrigation|valves?|b camp|c camp|"
    r"solar|soc|grid|inverter|power|fertili[sz]er)\b", re.I,
)
ENTITY_PATTERN = re.compile(r"\b(?:pig|tag)\s*([a-z0-9-]+)\b", re.I)
CONFIRMATION_PATTERN = re.compile(r"^CONFIRM HERD-[A-Z0-9-]+$")


class ActiveContextLoadError(RuntimeError):
    pass


def handle_authenticated_health_loss_message(
    parsed: Mapping[str, Any], gateway_authority, *, connect_factory=None, context_store=None
):
    """Return one useful owner response, or ``handled=False`` for other intents."""
    parsed = parsed if isinstance(parsed, Mapping) else {}
    text = str(parsed.get("text") or "").strip()
    provider_message_id = str(parsed.get("provider_message_id") or "").strip()
    provider_timestamp = str(parsed.get("provider_timestamp") or "").strip()
    explicit_health = bool(HEALTH_PATTERN.search(text))
    confirmation_shaped = bool(CONFIRMATION_PATTERN.fullmatch(text))
    plausible_follow_up = bool(
        FOLLOW_UP_PATTERN.search(text)
        and not UNRELATED_OPERATIONAL_PATTERN.search(text)
    )
    # Active-case persistence belongs only to this specialist boundary.  Do
    # not make unrelated read-only gateway traffic depend on its store merely
    # to establish that HERDMASTER is not applicable.
    if not explicit_health and not plausible_follow_up and not confirmation_shaped:
        return {"handled": False, "status": "health_loss_intake_not_applicable"}, 200
    try:
        contexts = _load_active_contexts(
            str(parsed.get("telegram_chat_id") or ""),
            owner_user_id=str(parsed.get("telegram_user_id") or ""),
            context_store=context_store)
    except ActiveContextLoadError:
        return {"handled": True, "success": False, "status": "health_loss_active_context_unavailable",
            "answer": ("⚠️ <b>HERDMASTER FOLLOW-UP CONTAINED</b>\n\n"
                       "I could not safely read the active animal-case chronology. Your message was retained by the authenticated intake, but no new case or farm record was created."),
            "records_audit_trace": False, "writes_farm_data": False,
            "protected_actions_performed": False}, 503
    active, ambiguity, superseded = _resolve_active_context(text, contexts, provider_message_id)
    if ambiguity:
        return {"handled": True, "success": False, "status": "health_loss_active_context_ambiguous",
            "answer": ("⚠️ <b>HERDMASTER FOLLOW-UP NEEDS ONE IDENTITY</b>\n\n"
                       "More than one animal case is active. Name the pig or tag once so I can bind this update safely. Nothing was recorded."),
            "records_audit_trace": False, "writes_farm_data": False,
            "protected_actions_performed": False}, 409
    active_status = str((active or {}).get("status") or "")
    superseded = sorted(set(superseded) | {
        str(value) for value in (active or {}).get("superseded_duplicate_missions") or []
        if str(value or "")
    })
    superseded_bindings = list((active or {}).get("superseded_duplicate_bindings") or [])
    known_binding_ids = {str(value.get("mission_id") or "") for value in superseded_bindings
                         if isinstance(value, Mapping)}
    active_tag = _context_tag(active or {})
    for mission in superseded:
        target = next((row for row in contexts if str(row.get("mission_id") or "") == mission), None)
        if target and mission not in known_binding_ids and active_tag and _context_tag(target) == active_tag:
            superseded_bindings.append({"mission_id": mission,
                "provider_message_id": str(target.get("provider_message_id") or ""),
                "tag_number": active_tag})
    confirmation = bool(active and active_status in {"preview_ready", "completed"}
                        and text == "CONFIRM " + str(active.get("operation_id") or ""))
    follow_up = bool(active and not confirmation and active_status in {"waiting_for_input", "preview_ready"})
    if not explicit_health and not follow_up and not confirmation:
        return {"handled": False, "status": "health_loss_intake_not_applicable"}, 200

    if not provider_message_id or not provider_timestamp:
        return {"handled": True, "success": False, "status": "health_loss_provider_identity_required"}, 409
    if active and not _chronology_allows(active, provider_message_id, provider_timestamp):
        return {"handled": True, "success": False, "status": "health_loss_follow_up_chronology_conflict",
            "answer": ("⚠️ <b>HERDMASTER FOLLOW-UP CONTAINED</b>\n\n"
                       "This update is older than the active animal case or conflicts with its chronology. Nothing was recorded."),
            "mission_id": str(active.get("mission_id") or ""),
            "card_mission_id": str(active.get("mission_id") or ""),
            "records_audit_trace": False, "writes_farm_data": False,
            "protected_actions_performed": False}, 409

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

    active_for_message = active if follow_up else None
    context_text = str((active_for_message or {}).get("combined_text") or "").strip()
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
    mission_id = str((active_for_message or {}).get("mission_id") or "") or "OOM-HERDMASTER-" + hashlib.sha256(
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
        "superseded_duplicate_missions": superseded,
        "superseded_duplicate_bindings": superseded_bindings,
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
        "superseded_duplicate_missions": superseded,
        "superseded_duplicate_bindings": superseded_bindings,
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
        (
            f"{lifecycle.get('chat_id')}|{lifecycle.get('provider_message_id')}|"
            f"{lifecycle.get('mission_id')}"
        ).encode()
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
    contexts = _load_active_contexts(chat_id, context_store=context_store)
    return contexts[0] if contexts else None


def _load_active_contexts(chat_id: str, *, owner_user_id="", context_store=None):
    if not chat_id:
        return []
    if context_store is not None:
        try:
            value = context_store("load", chat_id, None)
        except Exception as exc:
            raise ActiveContextLoadError("active_context_read_failed") from exc
        rows = value if isinstance(value, list) else ([value] if isinstance(value, dict) else [])
        return _dedupe_active_contexts(rows, owner_user_id=owner_user_id)
    database_url = str(os.getenv("DATABASE_URL") or "").strip()
    if not database_url:
        raise ActiveContextLoadError("active_context_store_unavailable")
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                owner_clause = ("and review_json->'herdmaster_health_loss'->>'owner_user_id' = %s"
                                if owner_user_id else "")
                params = ((EVENT_SOURCE, "oom-health-" + chat_id, owner_user_id)
                          if owner_user_id else (EVENT_SOURCE, "oom-health-" + chat_id))
                cursor.execute(
                    f"""
                    select review_json->'herdmaster_health_loss', created_at
                    from public.sam_live_stock_conversation_review_events
                    where event_source = %s
                      and chatwoot_conversation_id = %s
                      {owner_clause}
                    order by created_at desc
                    limit 100
                    """,
                    params,
                )
                rows = cursor.fetchall()
        current = []
        now = datetime.now(timezone.utc)
        for value, created_at in rows:
            if not isinstance(value, dict):
                continue
            if created_at and now - created_at.astimezone(timezone.utc) > CONTEXT_WINDOW:
                continue
            current.append(value)
        return _dedupe_active_contexts(current, owner_user_id=owner_user_id)
    except Exception as exc:
        raise ActiveContextLoadError("active_context_read_failed") from exc


def _dedupe_active_contexts(rows, *, owner_user_id=""):
    latest = {}
    for row in rows:
        status = str(row.get("status") or "")
        mission = str(row.get("mission_id") or "")
        bound_owner = str(row.get("owner_user_id") or "")
        if owner_user_id and bound_owner and bound_owner != owner_user_id:
            continue
        if status not in {"waiting_for_input", "preview_ready", "completed"} or not mission or mission in latest:
            continue
        latest[mission] = row
    superseded = set(); validated_by_source = {mission: [] for mission in latest}
    for source_mission, row in latest.items():
        source_tag = _context_tag(row)
        for binding in row.get("superseded_duplicate_bindings") or []:
            if not isinstance(binding, Mapping):
                continue
            target_mission = str(binding.get("mission_id") or "")
            target = latest.get(target_mission)
            target_provider = str(binding.get("provider_message_id") or "")
            target_tag = str(binding.get("tag_number") or "").casefold()
            if (target and source_tag and target_tag == source_tag
                    and _context_tag(target) == source_tag and target_provider
                    and str(target.get("provider_message_id") or "") == target_provider):
                superseded.add(target_mission)
                validated_by_source[source_mission].append({"mission_id": target_mission,
                    "provider_message_id": target_provider, "tag_number": target_tag})
    return [{**row,
             "superseded_duplicate_missions": sorted(value["mission_id"] for value in validated_by_source[mission]),
             "superseded_duplicate_bindings": validated_by_source[mission]}
            for mission, row in latest.items() if mission not in superseded]


def _context_tag(context):
    preview = context.get("preview") if isinstance(context.get("preview"), Mapping) else {}
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    identity = evaluator.get("identity") if isinstance(evaluator.get("identity"), Mapping) else {}
    return str(identity.get("tag_number") or "").casefold()


def _context_missing(context):
    preview = context.get("preview") if isinstance(context.get("preview"), Mapping) else {}
    evaluator = preview.get("evaluator") if isinstance(preview.get("evaluator"), Mapping) else {}
    return {str(value or "") for value in evaluator.get("missing_evidence") or []}


def _resolve_active_context(text, contexts, provider_message_id=""):
    exact_confirmations = [row for row in contexts
        if text == "CONFIRM " + str(row.get("operation_id") or "")]
    if len(exact_confirmations) == 1:
        return exact_confirmations[0], False, []
    if len(exact_confirmations) > 1:
        return None, True, []
    entity = ENTITY_PATTERN.search(text)
    if entity:
        matches = [row for row in contexts if _context_tag(row) == entity.group(1).casefold()
                   and str(row.get("status") or "") in {"waiting_for_input", "preview_ready"}]
        if len(matches) == 1:
            return matches[0], False, []
        prior = [row for row in matches
                 if str(row.get("provider_message_id") or "") != provider_message_id]
        echoes = [row for row in matches
                  if str(row.get("provider_message_id") or "") == provider_message_id]
        if len(prior) == 1 and echoes:
            return prior[0], False, [str(row.get("mission_id") or "") for row in echoes]
        return None, len(matches) > 1, []
    if UNRELATED_OPERATIONAL_PATTERN.search(text) or not FOLLOW_UP_PATTERN.search(text):
        return None, False, []
    candidates = [row for row in contexts
        if str(row.get("status") or "") in {"waiting_for_input", "preview_ready"}]
    if re.search(r"\b(?:removed|buried|disposed|cremated|body)\b", text, re.I):
        removal = [row for row in candidates
                   if "physical removal/disposal evidence" in _context_missing(row)]
        if len(removal) == 1:
            return removal[0], False, []
    return ((candidates[0], False, []) if len(candidates) == 1
            else (None, len(candidates) > 1, []))


def _chronology_allows(active, provider_message_id, provider_timestamp):
    if (str(active.get("provider_message_id") or "") == provider_message_id
            and str(active.get("provider_timestamp") or "") == provider_timestamp):
        return True
    try:
        incoming = datetime.fromisoformat(provider_timestamp.replace("Z", "+00:00"))
        prior = datetime.fromisoformat(str(active.get("provider_timestamp") or "").replace("Z", "+00:00"))
        return incoming > prior
    except (TypeError, ValueError):
        return False
