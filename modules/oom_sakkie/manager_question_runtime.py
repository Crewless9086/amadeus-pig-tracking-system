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
from modules.oom_sakkie.bounded_postgres_read import (
    connect_bounded_postgres, connect_bounded_read,
)

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
    except Exception as exc:
        return {"load_unavailable": True,
                "load_failure_class": exc.__class__.__name__}
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
                                  question_loader=None, event_store=None,
                                  event_loader=None):
    if authority is None:
        return {"handled": False, **ZERO}, 200
    active = question or load_active_manager_question(parsed, loader=question_loader)
    if not active:
        return {"handled": False, **ZERO}, 200
    # A protected specialist packet owns its own preview/confirmation lifecycle.
    # Broad manager context must never consume it merely because it is conversational.
    if semantic is not None and (getattr(semantic, "protected_preview_required", False)
            or getattr(semantic, "recording_prohibited", False)
            or bool(getattr(semantic, "breeding_actions", ()) )):
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
    if (bound is None or str(bound.owner_user_id) != str(parsed.get("telegram_user_id") or "")
            or str(bound.private_chat_id) != str(parsed.get("telegram_chat_id") or "")):
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
    completion_event_id = event_id + "-COMPLETED"
    facts = _semantic_facts(semantic)
    clarification = str(getattr(semantic, "clarification_question", "") or "").strip()
    partial = bool(getattr(semantic, "needs_clarification", False) and clarification)
    binding = {"owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "provider_message_id": provider, "provider_timestamp": provider_at,
        "reply_to_message_id": reply_to, "content_sha256": sha256(text.encode()).hexdigest()}
    try:
        existing = ((event_loader)(event_id) if event_loader is not None else
                    _load_manager_question_record(event_id) if event_store is None else {})
        completed = ((event_loader)(completion_event_id) if event_loader is not None else
                    _load_manager_question_record(completion_event_id) if event_store is None else {})
    except Exception as exc:
        return {"handled": True, "success": False,
            "status": "manager_question_receipt_lookup_unavailable",
            "failure_class": exc.__class__.__name__,
            "answer": ("I received the reply, but could not safely check its durable receipt. "
                       "Nothing was applied; exact recovery remains available."),
            "requires_visible_notification": True, **ZERO}, 503
    terminal = completed or (existing if existing.get("status") != "dispatch_claimed" else {})
    if terminal:
        if terminal.get("provider_binding") != binding:
            return {"handled": True, "success": False,
                "status": "manager_question_concurrent_reply_conflict",
                "answer": "I kept the first attributable reply to this farm question; I did not overwrite it.",
                "requires_visible_notification": True, **ZERO}, 409
        recovered = (terminal.get("downstream_result")
            if isinstance(terminal.get("downstream_result"), dict) else None)
        if recovered:
            return {**recovered, "handled": True,
                "manager_question_status": "manager_question_reply_replay_recovered",
                "manager_question_event_id": event_id,
                "records_audit_trace": True}, int(terminal.get("downstream_status") or 200)
        return {"handled": True, "success": True,
            "status": "manager_question_reply_replay_suppressed", "answer": "",
            "suppress_owner_delivery": True, **ZERO}, 200
    for prior in partials:
        prior_binding = prior.get("provider_binding") if isinstance(
            prior.get("provider_binding"), dict) else {}
        if prior_binding == binding:
            return {"handled": True, "success": True,
                "status": "manager_question_reply_replay_suppressed", "answer": "",
                "suppress_owner_delivery": True, **ZERO}, 200
        if (prior_binding.get("provider_message_id") == provider
                and prior_binding.get("owner_user_id") == binding["owner_user_id"]
                and prior_binding.get("chat_id") == binding["chat_id"]):
            return {"handled": True, "success": False,
                "status": "manager_question_provider_binding_conflict",
                "answer": "I retained the original attributable reply and did not overwrite it.",
                "requires_visible_notification": True, **ZERO}, 409
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
    downstream = None
    downstream_status = 200
    if expected_domain == "rootline" and semantic_domain == "rootline":
        store = event_store or manager_question_event_store
        if existing:
            if existing.get("provider_binding") != binding:
                return {"handled": True, "success": False,
                    "status": "manager_question_concurrent_reply_conflict",
                    "answer": "I kept the first attributable reply to this farm question; I did not overwrite it.",
                    "requires_visible_notification": True, **ZERO}, 409
            return {"handled": True, "success": True,
                "status": "manager_question_reply_replay_suppressed", "answer": "",
                "suppress_owner_delivery": True, **ZERO}, 200
        else:
            claim = {**record, "status": "dispatch_claimed",
                "claim_started_at": datetime.now(timezone.utc).isoformat()}
            claimed = store(event_id, claim)
            if not isinstance(claimed, dict) or claimed.get("success") is not True:
                return {"handled": True, "success": False,
                    "status": "manager_question_receipt_unavailable",
                    "answer": ("I received the reply, but could not durably claim it. "
                               "Nothing was applied; exact recovery remains available."),
                    "requires_visible_notification": True, **ZERO}, 503
            if claimed.get("created") is False:
                prior = claimed.get("record") if isinstance(claimed.get("record"), dict) else {}
                if prior.get("provider_binding") != binding:
                    return {"handled": True, "success": False,
                        "status": "manager_question_concurrent_reply_conflict",
                        "answer": "I kept the first attributable reply to this farm question; I did not overwrite it.",
                        "requires_visible_notification": True, **ZERO}, 409
                return {"handled": True, "success": True,
                    "status": "manager_question_reply_replay_suppressed", "answer": "",
                    "suppress_owner_delivery": True, **ZERO}, 200
        from modules.oom_sakkie.operational_specialist_intake import (
            handle_operational_specialist_message,
        )
        downstream, downstream_status = handle_operational_specialist_message(
            parsed, authority)
        if not downstream.get("handled"):
            return {"handled": False, **ZERO}, 200
        completion = {**record, "event_id": completion_event_id,
            "status": "recorded", "downstream_result": dict(downstream),
            "downstream_status": int(downstream_status)}
        stored = store(completion_event_id, completion)
        if not isinstance(stored, dict) or stored.get("success") is not True:
            retained_identity = {key: downstream.get(key) for key in
                ("specialist_identity", "mission_id", "card_mission_id",
                 "provider_message_id", "provider_timestamp")
                if downstream.get(key) is not None}
            return {"handled": True, "success": False,
                "status": "manager_question_receipt_unavailable",
                "answer": ("ROOTLINE retained the attributable update, but the linked manager receipt "
                           "is not yet proven. Exact recovery will reconcile this same provider identity; "
                           "no hardware command was issued."),
                "downstream_retention_possible": True,
                "requires_visible_notification": True, **retained_identity, **ZERO}, 503
        return {**downstream, "handled": True,
            "manager_question_status": "manager_question_reply_recorded",
            "manager_question_event_id": event_id,
            "records_audit_trace": True}, downstream_status
    stored = (event_store or manager_question_event_store)(event_id, record)
    if not isinstance(stored, dict) or stored.get("success") is not True:
        downstream_applied = downstream is not None
        retained_identity = ({key: downstream.get(key) for key in
            ("specialist_identity", "mission_id", "card_mission_id",
             "provider_message_id", "provider_timestamp")
            if downstream is not None and downstream.get(key) is not None})
        return {"handled": True, "success": False,
            "status": "manager_question_receipt_unavailable",
            "answer": (("ROOTLINE retained the attributable update, but the linked manager receipt "
                        "is not yet proven. Exact recovery will reconcile this same provider identity; "
                        "no hardware command was issued.") if downstream_applied else
                       ("I received the reply, but could not prove its durable receipt. "
                        "Nothing was applied; recovery must use this same provider message identity.")),
            "downstream_retention_possible": downstream_applied,
            "requires_visible_notification": True, **retained_identity, **ZERO}, 503
    if stored.get("created") is False:
        existing = stored.get("record") if isinstance(stored.get("record"), dict) else {}
        if existing.get("provider_binding") == binding:
            recovered = (existing.get("downstream_result")
                if isinstance(existing.get("downstream_result"), dict) else None)
            if recovered:
                return {**recovered, "handled": True,
                    "manager_question_status": "manager_question_reply_replay_recovered",
                    "manager_question_event_id": event_id,
                    "records_audit_trace": True}, int(existing.get("downstream_status") or 200)
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
    result, status = record_sam_live_stock_review_event(event,
        connect_factory=lambda: connect_bounded_postgres(
            read_only=False, connect_deadline_seconds=3))
    created = result.get("created", status < 300)
    existing = record if created else _load_manager_question_record(event_id)
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": created, "record": existing}


def _load_manager_question_record(event_id):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return {}
    with connect_bounded_read() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'manager_question_reply'
                from public.sam_live_stock_conversation_review_events
                where review_event_id=%s""", (event_id,))
            row = cursor.fetchone()
            return dict(row[0]) if row and isinstance(row[0], dict) else {}


def _load_questions(owner, chat):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return []
    with connect_bounded_read() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select q.body, coalesce(p.partials, '[]'::jsonb)
                from (select daily.review_json->'daily_farm_manager' as body,
                             daily.created_at, daily.review_event_id
                    from public.sam_live_stock_conversation_review_events daily
                    where daily.event_source='oom_sakkie_daily_farm_manager'
                      and daily.review_json->'daily_farm_manager'->>'status'='presented'
                      and daily.review_json->'daily_farm_manager'->>'owner_user_id'=%s
                      and daily.review_json->'daily_farm_manager'->>'chat_id'=%s
                      and coalesce(daily.review_json->'daily_farm_manager'->>'question','')<>''
                      and not exists (select 1
                        from public.sam_live_stock_conversation_review_events answered
                        where answered.event_source='oom_sakkie_manager_question_reply'
                          and answered.review_json->'manager_question_reply'->>'status'='recorded'
                          and answered.review_json->'manager_question_reply'->>'owner_user_id'=%s
                          and answered.review_json->'manager_question_reply'->>'chat_id'=%s
                           and answered.review_json->'manager_question_reply'->>'task_id'=
                               daily.review_json->'daily_farm_manager'->'question_binding'->>'task_id'
                           and answered.review_json->'manager_question_reply'->>'daily_identity'=
                               daily.review_json->'daily_farm_manager'->>'daily_identity'
                           and answered.review_json->'manager_question_reply'->>'dedupe_key'=
                               daily.review_json->'daily_farm_manager'->'question_binding'->>'dedupe_key')
                    order by created_at desc, review_event_id desc limit 8) q
                left join lateral (select jsonb_agg(
                        partial.review_json->'manager_question_reply'
                        order by partial.created_at, partial.review_event_id) as partials
                    from public.sam_live_stock_conversation_review_events partial
                    where partial.event_source='oom_sakkie_manager_question_reply'
                      and partial.review_json->'manager_question_reply'->>'status'='partial'
                      and partial.review_json->'manager_question_reply'->>'owner_user_id'=%s
                      and partial.review_json->'manager_question_reply'->>'chat_id'=%s
                      and partial.review_json->'manager_question_reply'->>'task_id'=
                          q.body->'question_binding'->>'task_id'
                      and partial.review_json->'manager_question_reply'->>'daily_identity'=
                          q.body->>'daily_identity') p on true
                order by q.created_at desc, q.review_event_id desc""",
                (owner, chat, owner, chat, owner, chat))
            questions = []
            for body, partials in cursor.fetchall():
                question = dict(body)
                question["partial_replies"] = list(partials or [])
                questions.append(question)
            if questions:
                return questions
            # A provider-confirmed morning card can outlive an ambiguous daily
            # outcome receipt when the post-send database read stalls. Preserve
            # that immutable discrepancy and recover only the card's bounded
            # contextual continuation; do not manufacture a stale question.
            cursor.execute("""select f.body, f.created_at
                from (select review_json->'family_message_lifecycle' as body,
                             created_at, review_event_id
                      from public.sam_live_stock_conversation_review_events cards
                      where cards.event_source='oom_sakkie_family_message_lifecycle'
                        and cards.review_json->'family_message_lifecycle'->>'state'='delivered'
                        and cards.review_json->'family_message_lifecycle'->>'owner_user_id'=%s
                        and cards.review_json->'family_message_lifecycle'->>'chat_id'=%s
                        and cards.review_json->'family_message_lifecycle'->>'card_mission_id'
                            ~ '^OOM-DAILY-FARM-MANAGER-[0-9]{4}-[0-9]{2}-[0-9]{2}$'
                        and not exists (select 1
                            from public.sam_live_stock_conversation_review_events answered
                            where answered.event_source='oom_sakkie_manager_question_reply'
                              and answered.review_json->'manager_question_reply'->>'status'='recorded'
                              and answered.review_json->'manager_question_reply'->>'owner_user_id'=%s
                              and answered.review_json->'manager_question_reply'->>'chat_id'=%s
                               and answered.review_json->'manager_question_reply'->>'task_id'=
                                   cards.review_json->'family_message_lifecycle'->>'card_mission_id'
                                       || ':contextual-update'
                               and answered.review_json->'manager_question_reply'->>'daily_identity'=
                                   cards.review_json->'family_message_lifecycle'->>'card_mission_id'
                               and answered.review_json->'manager_question_reply'->>'dedupe_key'=
                                   cards.review_json->'family_message_lifecycle'->>'card_mission_id'
                                       || ':contextual-update')
                      order by created_at desc, review_event_id desc limit 1) f""",
                (owner, chat, owner, chat))
            row = cursor.fetchone()
            if not row:
                return []
            body, created_at = dict(row[0] or {}), row[1]
            return [{"daily_identity": str(body.get("card_mission_id") or ""),
                "telegram_message_id": str(body.get("telegram_message_id") or ""),
                "presented_at": str(body.get("delivery_provider_timestamp")
                    or created_at.isoformat()),
                "question": "Contextual update to the delivered morning farm plan",
                "question_binding": {
                    "task_id": str(body.get("card_mission_id") or "") + ":contextual-update",
                    "dedupe_key": str(body.get("card_mission_id") or "") + ":contextual-update",
                    "domain": "rootline", "contextual_card_recovery": True}}]


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
