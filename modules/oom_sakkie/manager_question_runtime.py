"""Provider-bound continuation for one active Daily Farm Manager question.

The rail stores attributable owner evidence and retires the surfaced question.
It grants no farm, health, customer, payment, or hardware write authority.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
import re

from modules.oom_sakkie.gateway_authority import bind_gateway_owner_authority
from modules.oom_sakkie.bounded_postgres_read import (
    connect_bounded_rootline_postgres,
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
                                  event_loader=None, health_handler=None):
    if authority is None:
        return {"handled": False, **ZERO}, 200
    active = question or load_active_manager_question(parsed, loader=question_loader)
    if not active:
        return {"handled": False, **ZERO}, 200
    presented = _timestamp(active.get("presented_at") or active.get("observed_at"))
    provider_at_value = _timestamp(parsed.get("provider_timestamp"))
    if (presented is None or provider_at_value is None
            or not 0 <= (provider_at_value - presented).total_seconds() <= MAX_AGE_SECONDS):
        return {"handled": False, **ZERO}, 200
    reply_to = str(parsed.get("reply_to_message_id") or "").strip()
    exact_reply = bool(reply_to and reply_to == str(active.get("telegram_message_id") or ""))
    # A protected specialist packet owns its own preview/confirmation lifecycle.
    # Broad manager context must never consume it merely because it is conversational.
    if semantic is not None and (getattr(semantic, "protected_preview_required", False)
            or getattr(semantic, "recording_prohibited", False)
            or bool(getattr(semantic, "breeding_actions", ()) )):
        return {"handled": False, **ZERO}, 200
    expected_domain = str((active.get("question_binding") or {}).get("domain") or "")
    rootline_question = expected_domain in {"rootline", "water_energy"}
    if rootline_question and semantic is not None:
        semantic = _bind_literal_rootline_observation(parsed, semantic)
        parsed = {**parsed, "semantic": semantic.as_hint()}
    semantic_domain = str(getattr(semantic, "domain", "") or "")
    compatible = _compatible(expected_domain, semantic_domain)
    semantic_continuation = bool(semantic is not None
        and getattr(semantic, "continuation", False) and compatible)
    if rootline_question and exact_reply and semantic is not None \
            and not _typed_rootline_fact(semantic, parsed):
        return {"handled": True, "success": False,
            "status": "manager_question_rootline_observation_ambiguous",
            "answer": "Which is full: the reservoir or the storage tanks?",
            "requires_visible_notification": True, "question_count": 1,
            "retry_owner": "same_provider_message_identity", **ZERO}, 409
    if reply_to and not exact_reply:
        return {"handled": False, **ZERO}, 200
    if not exact_reply and not semantic_continuation:
        return {"handled": False, **ZERO}, 200
    if exact_reply and semantic is not None and not semantic_continuation:
        return {"handled": False, **ZERO}, 200
    if semantic is None:
        return {"handled": True, "success": False,
            "status": "manager_question_meaning_unavailable",
            "answer": str(active.get("question") or "Could you clarify that answer?")[:240],
            "requires_visible_notification": True, "question_count": 1, **ZERO}, 409
    if rootline_question and not _typed_rootline_fact(semantic, parsed):
        return {"handled": True, "success": False,
            "status": "manager_question_rootline_observation_ambiguous",
            "answer": "Which is full: the reservoir or the storage tanks?",
            "requires_visible_notification": True, "question_count": 1,
            "retry_owner": "same_provider_message_identity", **ZERO}, 409
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
        retry_failures = []
        for retry_number in range(1, 9):
            retry_identity = f"{event_id}-RETRY-OWNED-{retry_number}"
            failure = ((event_loader)(retry_identity) if event_loader is not None else
                       _load_manager_question_record(retry_identity) if event_store is None else {})
            if not failure:
                break
            retry_failures.append(failure)
        retry_owned = retry_failures[-1] if retry_failures else {}
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
            return {**recovered, "handled": True, "answer": "",
                "suppress_owner_delivery": True, "replay_suppressed": True,
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
    pig_id, pig_binding_state = _bound_question_pig_id(active)
    herd_question = expected_domain in {"herd", "herd_health", "herd_management"}
    dedupe_is_animal_specific = (dedupe_key.startswith("herdmaster:")
        and dedupe_key != "herdmaster:mortality-current-assessment")
    if herd_question and not partial and pig_binding_state != "resolved" \
            and (pig_binding_state == "ambiguous" or dedupe_is_animal_specific):
        return {"handled": True, "success": False,
            "status": "manager_question_welfare_identity_unavailable",
            "answer": ("I kept the welfare question open because its canonical animal binding "
                       "is not exactly one pig. Nothing was recorded or closed."),
            "requires_visible_notification": True, **ZERO}, 409
    if herd_question and pig_id and not partial:
        if health_handler is None:
            from modules.oom_sakkie.herdmaster_health_loss_runtime import (
                handle_authenticated_health_loss_message)
            health_handler = handle_authenticated_health_loss_message
        forwarded = {**parsed, "text": f"Pig {pig_id}: {text}",
            "semantic": {"domain": "herd_health", "continuation": True,
                "entity_refs": [f"pig:{pig_id}"], "observation": text}}
        downstream, downstream_status = health_handler(forwarded, authority)
        if (not isinstance(downstream, dict) or downstream.get("handled") is not True
                or downstream.get("success") is not True):
            return ({**(downstream or {}), "handled": True,
                "status": str((downstream or {}).get("status") or
                              "manager_question_welfare_intake_unavailable")},
                int(downstream_status or 503))
        record.update({"downstream_result": dict(downstream),
                       "downstream_status": int(downstream_status),
                       "canonical_welfare_intake": True, "pig_id": pig_id})
    if rootline_question and semantic_domain == "rootline":
        store = event_store or manager_question_event_store
        if existing and existing.get("status") != "dispatch_claimed":
            if existing.get("provider_binding") != binding:
                return {"handled": True, "success": False,
                    "status": "manager_question_concurrent_reply_conflict",
                    "answer": "I kept the first attributable reply to this farm question; I did not overwrite it.",
                    "requires_visible_notification": True, **ZERO}, 409
            return {"handled": True, "success": True,
                "status": "manager_question_reply_replay_suppressed", "answer": "",
                "suppress_owner_delivery": True, **ZERO}, 200
        elif existing:
            if not retry_owned or retry_owned.get("provider_binding") != binding:
                return {"handled": True, "success": False,
                    "status": "manager_question_rootline_dispatch_in_progress",
                    "answer": "", "suppress_owner_delivery": True,
                    "retry_owner": "same_provider_message_identity", **ZERO}, 202
            if len(retry_failures) >= 8:
                return {"handled": True, "success": False,
                    "status": "manager_question_rootline_retry_exhausted",
                    "answer": ("The ROOTLINE observation is still unproven after eight contained retries. "
                               "It was not recorded; technical recovery owns the exception and no hardware command was issued."),
                    "requires_visible_notification": True,
                    "retry_owner": "rootline_technical_recovery", **ZERO}, 503
            retained = retry_owned.get("downstream_result")
            if isinstance(retained, dict) and _exact_rootline_readback(parsed, retained):
                downstream = dict(retained)
                downstream_status = int(retry_owned.get("downstream_status") or 200)
            else:
                retry_claim_event_id = f"{event_id}-RETRY-CLAIMED-{len(retry_failures)}"
                try:
                    retry_claim = store(retry_claim_event_id, {**record,
                        "event_id": retry_claim_event_id, "status": "retry_claimed",
                        "claim_started_at": datetime.now(timezone.utc).isoformat()})
                except Exception:
                    retry_claim = {}
                if (not isinstance(retry_claim, dict) or retry_claim.get("success") is not True
                        or retry_claim.get("created") is not True):
                    return {"handled": True, "success": False,
                        "status": "manager_question_rootline_retry_in_progress",
                        "answer": "", "suppress_owner_delivery": True,
                        "retry_owner": "same_provider_message_identity", **ZERO}, 202
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
        if downstream is None:
            downstream, downstream_status = handle_operational_specialist_message(
                parsed, authority)
        if not downstream.get("handled"):
            return {"handled": False, **ZERO}, 200
        if not _exact_rootline_readback(parsed, downstream):
            failure_event_id = f"{event_id}-RETRY-OWNED-{len(retry_failures) + 1}"
            failure = {**record, "event_id": failure_event_id,
                "status": "retry_owned", "downstream_result": dict(downstream),
                "downstream_status": int(downstream_status)}
            try:
                retained = store(failure_event_id, failure)
            except Exception:
                retained = {}
            if (not isinstance(retained, dict) or retained.get("success") is not True
                    or retained.get("created") is not True):
                return {"handled": True, "success": False,
                    "status": "manager_question_receipt_unavailable",
                    "answer": ("I could not prove the ROOTLINE observation or durable retry ownership. "
                               "It was not acknowledged as recorded; no hardware command was issued."),
                    "requires_visible_notification": True, **ZERO}, 503
            return {**downstream, "handled": True, "success": False,
                "status": "manager_question_rootline_observation_unproven",
                "answer": ("I could not prove the ROOTLINE observation in exact canonical readback. "
                           "It was not recorded; the same provider message owns the retry."),
                "manager_question_status": "manager_question_rootline_retry_owned",
                "manager_question_event_id": event_id,
                "retry_owner": "same_provider_message_identity",
                "records_audit_trace": True}, downstream_status
        completion = {**record, "event_id": completion_event_id,
            "status": "recorded", "downstream_result": dict(downstream),
            "downstream_status": int(downstream_status)}
        stored = store(completion_event_id, completion)
        if not isinstance(stored, dict) or stored.get("success") is not True:
            failure_event_id = f"{event_id}-RETRY-OWNED-{len(retry_failures) + 1}"
            try:
                retry_retained = store(failure_event_id, {**record, "event_id": failure_event_id,
                    "status": "retry_owned", "downstream_result": dict(downstream),
                    "downstream_status": int(downstream_status)})
            except Exception:
                retry_retained = {}
            if (not isinstance(retry_retained, dict) or retry_retained.get("success") is not True
                    or retry_retained.get("created") is not True):
                return {"handled": True, "success": False,
                    "status": "manager_question_receipt_unavailable",
                    "answer": ("ROOTLINE canonical readback succeeded, but neither the linked manager receipt "
                               "nor durable retry ownership is proven. It was not acknowledged as recorded; "
                               "no hardware command was issued."),
                    "downstream_retention_possible": True,
                    "requires_visible_notification": True, **ZERO}, 503
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
    if downstream is not None:
        return {**downstream, "handled": True,
            "manager_question_status": "manager_question_reply_recorded",
            "manager_question_event_id": event_id,
            "records_audit_trace": True}, downstream_status
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
        connect_factory=lambda: connect_bounded_rootline_postgres(
            read_only=False, connect_deadline_seconds=3))
    created = result.get("created", status < 300)
    existing = record if created else _load_manager_question_record(event_id)
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": created, "record": existing}


def _load_manager_question_record(event_id):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return {}
    with connect_bounded_rootline_postgres(
            read_only=True, connect_deadline_seconds=3) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'manager_question_reply'
                from public.sam_live_stock_conversation_review_events
                where review_event_id=%s""", (event_id,))
            row = cursor.fetchone()
            return dict(row[0]) if row and isinstance(row[0], dict) else {}


def _load_questions(owner, chat):
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return []
    with connect_bounded_rootline_postgres(
            read_only=True, connect_deadline_seconds=3) as connection:
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


def _bound_question_pig_id(question):
    """Recover only canonical typed bindings; never infer from display prose."""
    binding = question.get("question_binding") if isinstance(
        question.get("question_binding"), dict) else {}
    candidates = []
    for value in (binding.get("pig_id"), *(binding.get("pig_ids") or ())):
        value = str(value or "").strip()
        if re.fullmatch(r"PIG-[A-Z0-9-]{4,64}", value):
            candidates.append(value)
    for value in binding.get("source_refs") or ():
        match = re.fullmatch(r"pig:(PIG-[A-Z0-9-]{4,64})", str(value or "").strip())
        if match:
            candidates.append(match.group(1))
    match = re.fullmatch(r"herdmaster:(PIG-[A-Z0-9-]{4,64})",
                         str(binding.get("dedupe_key") or "").strip())
    if match:
        candidates.append(match.group(1))
    values = sorted(set(candidates))
    return (values[0], "resolved") if len(values) == 1 else \
        ("", "ambiguous" if len(values) > 1 else "unavailable")


_LITERAL_TANK_STATE = re.compile(
    r"^\s*(reservoir|storage(?:\s+tanks?)?)\s+(?:is|are)\s+(full|low|ok)\s*[.!]?\s*$",
    re.IGNORECASE,
)


def _bind_literal_rootline_observation(parsed, semantic):
    """Recover only an explicit named tank state; never resolve pronouns here."""
    match = _LITERAL_TANK_STATE.fullmatch(str(parsed.get("text") or ""))
    if not match:
        return semantic
    subject = "reservoir" if match.group(1).lower() == "reservoir" else "storage_tanks"
    return replace(semantic, domain="rootline", intent="water_levels_observed",
        message_kind="observation", continuation=True,
        observation=str(parsed.get("text") or "").strip(),
        observation_facts=({"subject": subject, "state": match.group(2).upper()},),
        needs_clarification=False, clarification_question="")


_LITERAL_TANK_FRACTION = re.compile(
    r"\b(reservoir|storage(?:\s+tanks?)?)\s+(?:(?:is|are)\s+)?\d+\s*/\s*\d+\b",
    re.IGNORECASE,
)


def _typed_rootline_fact(semantic, parsed=None):
    facts = tuple(getattr(semantic, "observation_facts", ()) or ())
    typed = bool(facts) and all(isinstance(fact, dict)
        and fact.get("subject") in {"reservoir", "storage_tanks", "storage"}
        for fact in facts)
    text = str((parsed or {}).get("text") or "")
    return bool(_LITERAL_TANK_STATE.fullmatch(text) or _LITERAL_TANK_FRACTION.search(text)) and typed


def _expected_rootline_readback(parsed):
    semantic = parsed.get("semantic") if isinstance(parsed.get("semantic"), dict) else {}
    expected = []
    for fact in semantic.get("observation_facts") or ():
        if not isinstance(fact, dict):
            return []
        subject = fact.get("subject")
        kind = "storage" if subject in {"storage", "storage_tanks"} else "reservoir" if subject == "reservoir" else ""
        state = str(fact.get("state") or "").upper()
        if state in {"LOW", "OK", "FULL"}:
            fraction = {"LOW": [0, 1], "OK": [1, 2], "FULL": [1, 1]}[state]
        elif (type(fact.get("numerator")) is int and type(fact.get("denominator")) is int):
            fraction = [fact["numerator"], fact["denominator"]]
            state = "LOW" if fraction[0] == 0 else "FULL" if fraction[0] == fraction[1] else "OK"
        else:
            return []
        expected.append({"kind": kind, "fraction": fraction, "state": state,
            "provider_message_id": str(parsed.get("provider_message_id") or ""),
            "observed_at": _normalized_instant(parsed.get("provider_timestamp"))})
    return expected


def _exact_rootline_readback(parsed, downstream):
    if (downstream.get("success") is not True
            or downstream.get("writes_farm_data") not in {True, False}):
        return False
    canonical = downstream.get("canonical_observation")
    if not isinstance(canonical, dict) or canonical.get("success") is not True:
        return False
    expected = _expected_rootline_readback(parsed)
    actual = [{**{key: row.get(key) for key in
        ("kind", "fraction", "state", "provider_message_id")},
        "observed_at": _normalized_instant(row.get("observed_at"))}
        for row in canonical.get("readback") or () if isinstance(row, dict)]
    key = lambda row: str(row.get("kind") or "")
    return bool(expected) and sorted(actual, key=key) == sorted(expected, key=key)


def _normalized_instant(value):
    parsed = _timestamp(value)
    return parsed.isoformat() if parsed is not None else ""


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
