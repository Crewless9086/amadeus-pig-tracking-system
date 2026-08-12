"""Provider-bound continuation for one active Daily Farm Manager question.

The rail stores attributable owner evidence and retires the surfaced question.
It grants no farm, health, customer, payment, or hardware write authority.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority

EVENT_SOURCE = "oom_sakkie_manager_question_reply"
MAX_AGE_SECONDS = 24 * 60 * 60
ZERO = {"writes_farm_data": False, "writes_customer_data": False,
        "writes_payment_data": False, "hardware_commands": 0}


def load_active_manager_question(parsed, *, loader=None):
    owner = str(parsed.get("telegram_user_id") or "").strip()
    chat = str(parsed.get("telegram_chat_id") or "").strip()
    provider_at = _timestamp(parsed.get("provider_timestamp"))
    if not owner or owner != chat or provider_at is None:
        return None
    try:
        rows = (loader or _load_questions)(owner, chat)
    except Exception:
        return None
    reply_to = str(parsed.get("reply_to_message_id") or "").strip()
    candidates = []
    for row in rows or ():
        if not isinstance(row, dict) or not str(row.get("question") or "").strip():
            continue
        presented = _timestamp(row.get("presented_at") or row.get("observed_at"))
        if presented is None:
            continue
        age = (provider_at - presented).total_seconds()
        if age < 0 or age > MAX_AGE_SECONDS:
            continue
        card = str(row.get("telegram_message_id") or "")
        if reply_to and reply_to != card:
            continue
        candidates.append((presented, row))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    newest = candidates[0][0]
    rows = [dict(row) for at, row in candidates if at == newest]
    return rows[0] if len(rows) == 1 else None


def semantic_context_with_manager_question(parsed, *, base_context_loader, question):
    context = dict(base_context_loader(parsed) or {})
    if not question:
        return context
    recent = list(context.get("recent_turns") or [])
    for prior in question.get("partial_replies") or ():
        if isinstance(prior, dict) and str(prior.get("owner_evidence") or "").strip():
            recent.append({"specialist": "OWNER", "task_state": "partial_answer",
                "provider_message_id": str(prior.get("provider_message_id") or "")[:40],
                "provider_timestamp": str(prior.get("provider_timestamp") or "")[:40],
                "semantic_domain": str(prior.get("domain") or "")[:40],
                "semantic_intent": "manager_question_partial_reply",
                "observation": str(prior.get("owner_evidence") or "")[:240]})
    recent.append({"specialist": "OOM_SAKKIE",
        "task_state": "waiting_for_input",
        "card_mission_id": str(question.get("daily_identity") or "")[:80],
        "provider_message_id": "scheduled-manager-question",
        "provider_timestamp": str(question.get("presented_at") or question.get("observed_at") or "")[:40],
        "delivery_provider_timestamp": str(question.get("presented_at") or question.get("observed_at") or "")[:40],
        "telegram_message_id": str(question.get("telegram_message_id") or "")[:40],
        "semantic_domain": str((question.get("question_binding") or {}).get("domain") or "manager_round")[:40],
        "semantic_intent": "manager_question_reply",
        "clarification_question": str(question.get("question") or "")[:240]})
    context["recent_turns"] = recent[-8:]
    return context


def handle_manager_question_reply(parsed, authority, semantic, *, question=None,
                                  question_loader=None, event_store=None):
    if authority is None:
        return {"handled": False, **ZERO}, 200
    active = question or load_active_manager_question(parsed, loader=question_loader)
    if not active:
        return {"handled": False, **ZERO}, 200
    reply_to = str(parsed.get("reply_to_message_id") or "").strip()
    exact_reply = bool(reply_to and reply_to == str(active.get("telegram_message_id") or ""))
    expected_domain = str((active.get("question_binding") or {}).get("domain") or "")
    semantic_domain = str(getattr(semantic, "domain", "") or "")
    compatible = _compatible(expected_domain, semantic_domain)
    semantic_continuation = bool(semantic is not None
        and getattr(semantic, "continuation", False) and compatible)
    if not exact_reply and not semantic_continuation:
        return {"handled": False, **ZERO}, 200
    if exact_reply and semantic is not None and not semantic_continuation:
        return {"handled": False, **ZERO}, 200
    if semantic is None:
        return {"handled": True, "success": False,
            "status": "manager_question_meaning_unavailable",
            "answer": str(active.get("question") or "Could you clarify that answer?")[:240],
            "requires_visible_notification": True, "question_count": 1, **ZERO}, 409
    bound = bind_gateway_owner_authority(authority, "farm_manager_round")
    if bound is None:
        return {"handled": True, "success": False,
            "status": "manager_question_authority_denied",
            "answer": "I could not safely bind that reply to the active farm question.",
            "requires_visible_notification": True, **ZERO}, 403
    provider = str(parsed.get("provider_message_id") or "").strip()
    provider_at = str(parsed.get("provider_timestamp") or "").strip()
    text = str(parsed.get("text") or "").strip()
    if not provider or not provider_at or not text:
        return {"handled": True, "success": False,
            "status": "manager_question_provider_binding_missing",
            "answer": "I retained the active question, but the provider identity for this reply is unavailable.",
            "requires_visible_notification": True, **ZERO}, 409
    dedupe_key = str((active.get("question_binding") or {}).get("dedupe_key") or "").strip()
    partials = [dict(item) for item in (active.get("partial_replies") or ())
                if isinstance(item, dict)]
    generation = len(partials) + 1
    question_identity = "|".join((str(bound.owner_user_id),
        str(parsed.get("telegram_chat_id") or ""), str(active.get("daily_identity") or ""),
        str((active.get("question_binding") or {}).get("task_id") or ""), dedupe_key))
    event_id = "OOM-MANAGER-QUESTION-" + sha256(
        f"{question_identity}|{generation}".encode()).hexdigest()[:24].upper()
    facts = _semantic_facts(semantic)
    clarification = str(getattr(semantic, "clarification_question", "") or "").strip()
    partial = bool(getattr(semantic, "needs_clarification", False) and clarification)
    binding = {"owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "provider_message_id": provider, "provider_timestamp": provider_at,
        "reply_to_message_id": reply_to, "content_sha256": sha256(text.encode()).hexdigest()}
    accumulated = _merge_semantic_facts(
        [item.get("semantic_facts") for item in partials] + [facts])
    record = {"event_id": event_id, "status": "partial" if partial else "recorded",
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "provider_message_id": provider, "provider_timestamp": provider_at,
        "reply_to_message_id": reply_to, "daily_identity": str(active.get("daily_identity") or ""),
        "manager_card_message_id": str(active.get("telegram_message_id") or ""),
        "task_id": str((active.get("question_binding") or {}).get("task_id") or ""),
        "dedupe_key": dedupe_key, "domain": expected_domain,
        "question": str(active.get("question") or ""), "owner_evidence": text,
        "semantic_facts": facts, "accumulated_semantic_facts": accumulated,
        "generation": generation, "provider_binding": binding,
        "content_sha256": binding["content_sha256"]}
    stored = (event_store or manager_question_event_store)(event_id, record)
    if not isinstance(stored, dict) or stored.get("success") is not True:
        return {"handled": True, "success": False,
            "status": "manager_question_receipt_unavailable",
            "answer": "I retained your reply, but could not prove its durable receipt yet.",
            "requires_visible_notification": True, **ZERO}, 503
    if stored.get("created") is False:
        existing = stored.get("record") if isinstance(stored.get("record"), dict) else {}
        if existing.get("provider_binding") == binding:
            return {"handled": True, "success": True,
                "status": "manager_question_reply_replay_suppressed", "answer": "",
                "suppress_owner_delivery": True, **ZERO}, 200
        return {"handled": True, "success": False,
            "status": "manager_question_concurrent_reply_conflict",
            "answer": "I kept the first attributable reply to this farm question; I did not overwrite it.",
            "requires_visible_notification": True, **ZERO}, 409
    if partial:
        answer = clarification
        status = "manager_question_partial_reply_recorded"
    else:
        answer = "Thanks — I recorded that against the active farm question."
        status = "manager_question_reply_recorded"
    return {"handled": True, "success": True, "status": status,
        "answer": answer, "mission_id": str(active.get("daily_identity") or ""),
        "card_mission_id": str(active.get("daily_identity") or ""),
        "requires_visible_notification": True, "question_count": int(bool(clarification)),
        "records_audit_trace": True, "specialist_identity": "HERDMASTER"
        if expected_domain in {"herd", "herd_health", "herd_management"} else "OOM_SAKKIE",
        **ZERO}, 200


def manager_question_event_store(event_id, record):
    from modules.sales.sam_live_stock_launch_control import (
        build_sam_live_stock_review_event, record_sam_live_stock_review_event)
    event = build_sam_live_stock_review_event({"conversation_id": event_id}, {}, {},
        {"score": 0, "safe_to_send": False,
         "recommended_action": "manager_question_reply"}, event_source=EVENT_SOURCE)
    event.update({"review_event_id": event_id,
        "chatwoot_conversation_id": event_id,
        "review_json": {"manager_question_reply": dict(record)},
        "decision_json": {}, "facts_json": {}, "customer_message_excerpt": "",
        "sam_reply_excerpt": ""})
    result, status = record_sam_live_stock_review_event(event)
    created = result.get("created", status < 300)
    existing = record if created else _load_manager_question_record(event_id)
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": created, "record": existing}


def _load_manager_question_record(event_id):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return {}
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'manager_question_reply'
                from public.sam_live_stock_conversation_review_events
                where review_event_id=%s""", (event_id,))
            row = cursor.fetchone()
            return dict(row[0]) if row and isinstance(row[0], dict) else {}


def _load_questions(owner, chat):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return []
    import psycopg
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=5) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'daily_farm_manager'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_daily_farm_manager'
                  and review_json->'daily_farm_manager'->>'status'='presented'
                  and review_json->'daily_farm_manager'->>'owner_user_id'=%s
                  and review_json->'daily_farm_manager'->>'chat_id'=%s
                  and coalesce(review_json->'daily_farm_manager'->>'question','')<>''
                  and not exists (
                    select 1 from public.sam_live_stock_conversation_review_events answered
                    where answered.event_source='oom_sakkie_manager_question_reply'
                      and answered.review_json->'manager_question_reply'->>'status'='recorded'
                      and answered.review_json->'manager_question_reply'->>'owner_user_id'=%s
                      and answered.review_json->'manager_question_reply'->>'chat_id'=%s
                      and answered.review_json->'manager_question_reply'->>'task_id'=
                          review_json->'daily_farm_manager'->'question_binding'->>'task_id')
                order by created_at desc, review_event_id desc limit 8""",
                (owner, chat, owner, chat))
            questions = [dict(row[0]) for row in cursor.fetchall()]
            for question in questions:
                cursor.execute("""select review_json->'manager_question_reply'
                    from public.sam_live_stock_conversation_review_events
                    where event_source='oom_sakkie_manager_question_reply'
                      and review_json->'manager_question_reply'->>'status'='partial'
                      and review_json->'manager_question_reply'->>'owner_user_id'=%s
                      and review_json->'manager_question_reply'->>'chat_id'=%s
                      and review_json->'manager_question_reply'->>'task_id'=%s
                    order by created_at, review_event_id""", (owner, chat,
                    str((question.get("question_binding") or {}).get("task_id") or "")))
                question["partial_replies"] = [row[0] for row in cursor.fetchall()]
            return questions


def _compatible(expected, actual):
    groups = ({"herd", "herd_health", "herd_management"},
              {"sales", "sam"}, {"water_energy", "rootline"})
    return expected == actual or any(expected in group and actual in group for group in groups)


def _semantic_facts(semantic):
    if semantic is None:
        return {}
    return {"domain": str(getattr(semantic, "domain", "") or ""),
        "intent": str(getattr(semantic, "intent", "") or ""),
        "observation": str(getattr(semantic, "observation", "") or ""),
        "observation_facts": list(getattr(semantic, "observation_facts", ()) or ()),
        "language": str(getattr(semantic, "language", "") or "")}


def _merge_semantic_facts(rows):
    merged = {"observations": [], "observation_facts": []}
    for row in rows:
        if not isinstance(row, dict):
            continue
        observation = str(row.get("observation") or "").strip()
        if observation and observation not in merged["observations"]:
            merged["observations"].append(observation)
        for fact in row.get("observation_facts") or ():
            if fact not in merged["observation_facts"]:
                merged["observation_facts"].append(fact)
    return merged


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None
