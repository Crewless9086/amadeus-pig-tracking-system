"""Context-first continuation for authenticated owner operational messages.

Active lifecycle, pending clarification, entity and compatible state transition
precede broad keyword routing. This module grants no device command authority.
"""

from __future__ import annotations

import hashlib
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

from modules.oom_sakkie.gateway_authority import (
    issue_owner_operational_outcome_authority,
    validates_gateway_owner_authority,
    validates_owner_operational_outcome_authority,
)

EVENT_SOURCE = "oom_sakkie_owner_operational_continuation"
VERSION = "oom_owner_operational_continuation_v1"
_IMPLICIT_STOP = re.compile(r"^\s*(?:it|this|that|hy|dit)\s+(?:has\s+|is\s+|het\s+)?(?:stopped|off|af|gestop)[.!\s]*$", re.I)
_ROOTLINE = re.compile(r"\b(irrigation|water|rootline|[bc]\s*camp|[bc]\s*kamp)\b", re.I)
_ENTITY = {"C12345": re.compile(r"\bc\s*(?:camp|kamp)\b", re.I),
           "B12345": re.compile(r"\bb\s*(?:camp|kamp)\b", re.I)}
_ENTITY_ASSERTION = re.compile(
    r"\b(?P<entity>[bc])\s*(?:camp|kamp)\b.{0,24}\b"
    r"(?:has\s+|is\s+|het\s+)?(?:physically\s+)?(?:stopped|off|af|gestop)\b", re.I)


def handle_owner_operational_continuation(parsed: Mapping[str, Any], authority, *,
                                          lifecycle_loader=None, context_store=None,
                                          now=None):
    owner = str(parsed.get("telegram_user_id") or "")
    chat = str(parsed.get("telegram_chat_id") or "")
    provider = str(parsed.get("provider_message_id") or "")
    provider_at = _time(parsed.get("provider_timestamp"))
    text = str(parsed.get("text") or "").strip()
    if not (validates_gateway_owner_authority(authority) and owner and owner == chat
            and authority.owner_user_id == owner and authority.private_chat_id == chat
            and provider and provider_at and text):
        return {"handled": False}, 200
    now = _time(now) or datetime.now(timezone.utc)
    if provider_at > now + timedelta(seconds=30):
        return _contained("owner_operational_chronology_invalid"), 409
    load = lifecycle_loader or _load_active_context
    store = context_store or _context_store
    try:
        loaded = load(owner, chat, provider)
        pending, active, exact = loaded if len(loaded) == 3 else (*loaded, [])
    except Exception:
        return _contained("owner_operational_context_unavailable"), 503

    for prior in exact:
        if (str(prior.get("provider_timestamp") or "") != provider_at.isoformat()
                or str(prior.get("text_sha256") or "") != hashlib.sha256(text.encode()).hexdigest()):
            return _contained("owner_operational_replay_binding_conflict"), 409
        if prior.get("state") == "execution_completed":
            return {**_completion_result(prior),
                    "status": "owner_operational_transition_replayed_noop",
                    "writes_operational_outcome": False,
                    "operational_outcome_recorded": True,
                    "outcome_replayed": True}, 200
        if prior.get("state") == "clarification_consumed":
            return _replay(prior, "clarification_replayed_noop"), 200
        if prior.get("state") == "clarification_pending":
            labels = ", ".join(dict.fromkeys(
                "C Camp irrigation" if item.get("entity_id") == "C12345" else
                "B Camp irrigation" if item.get("entity_id") == "B12345" else
                str(item.get("domain") or "farm work")
                for item in prior.get("candidate_bindings") or ()))
            return {"handled": True, "success": True,
                    "status": "owner_clarification_delivery_reconciliation_required",
                    "mission_id": prior.get("mission_id"),
                    "card_mission_id": prior.get("card_mission_id"),
                    "answer": f"<b>OOM SAKKIE - ONE DETAIL NEEDED</b>\n\nIs this about {labels}?",
                    "question_count": 1, **_zero_authority()}, 200

    entity = next((key for key, pattern in _ENTITY.items() if pattern.search(text)), "")
    terminal_state = "Stopped" if _affirmative_stop(text, entity) else ""
    candidates = _compatible(active, entity, terminal_state, parsed)
    if len(candidates) == 1 and terminal_state:
        target = candidates[0]
        resolved_entity = entity or str(target.get("entity_id") or "")
        label = "C Camp" if resolved_entity == "C12345" else "B Camp"
        completion_card = str(target.get("completion_card_mission_id") or
                              (str(target.get("card_mission_id") or target.get("mission_id") or "") + "-COMPLETION"))
        event = _event(parsed, target, "execution_completed", entity=resolved_entity,
                       label=label, terminal_state=terminal_state,
                       completion_card_mission_id=completion_card)
        outcome_authority = issue_owner_operational_outcome_authority(authority,
            mission_id=str(target.get("mission_id") or ""),
            execution_id=str(target.get("execution_id") or ""), provider_message_id=provider,
            provider_timestamp=provider_at.isoformat(), content_sha256=event["text_sha256"])
        if not validates_owner_operational_outcome_authority(outcome_authority):
            return _contained("owner_operational_outcome_authority_denied"), 403
        result = _completion_result(event)
        try:
            recorded = store("record", event["event_id"], event)
        except Exception:
            return _indeterminate("owner_operational_transition_persistence_indeterminate"), 503
        if recorded.get("created") is False:
            return {**result, "status": "owner_operational_transition_replayed_noop",
                    "writes_operational_outcome": False,
                    "operational_outcome_recorded": True,
                    "outcome_replayed": True}, 200
        if recorded.get("success") is not True or recorded.get("created") is not True:
            return _indeterminate("owner_operational_transition_persistence_indeterminate"), 503
        return result, 200
    if len(candidates) > 1:
        mission = "OOM-OWNER-CLARIFY-" + hashlib.sha256(
            f"{owner}|{provider}|{text}".encode()).hexdigest()[:24].upper()
        candidate_domains = sorted({str(item.get("domain") or "") for item in candidates})
        candidate_bindings = [{key: str(item.get(key) or "") for key in
            ("domain", "entity_id", "mission_id", "card_mission_id", "execution_id")}
            for item in candidates]
        event = {"event_id": mission + "-PENDING", "mission_id": mission,
            "card_mission_id": mission, "owner_user_id": owner, "chat_id": chat,
            "provider_message_id": provider, "provider_timestamp": provider_at.isoformat(),
            "state": "clarification_pending", "candidate_domains": candidate_domains,
            "candidate_bindings": candidate_bindings,
            "clarification_provider_timestamp": provider_at.isoformat(),
            "retained_text_sha256": hashlib.sha256(text.encode()).hexdigest()}
        try: recorded = store("record", event["event_id"], event)
        except Exception: return _contained("owner_operational_transition_persistence_failed"), 503
        if recorded.get("created") is False:
            return _replay(event, "owner_clarification_replayed_noop"), 200
        if recorded.get("success") is not True or recorded.get("created") is not True:
            return _contained("owner_operational_transition_persistence_failed"), 503
        labels = ", ".join(dict.fromkeys(
            "C Camp irrigation" if item.get("entity_id") == "C12345" else
            "B Camp irrigation" if item.get("entity_id") == "B12345" else
            str(item.get("domain") or "farm work") for item in candidates))
        return {"handled": True, "success": True, "status": "owner_context_clarification_required",
            "mission_id": mission, "card_mission_id": mission,
            "answer": f"<b>OOM SAKKIE — ONE DETAIL NEEDED</b>\n\nIs this about {labels}?",
            "question_count": 1, **_zero_authority()}, 200
    clarification = _unique_pending(pending, parsed)
    if clarification:
        domain = _domain(text)
        allowed = tuple(clarification.get("candidate_domains") or ())
        bindings = list(clarification.get("candidate_bindings") or ())
        answer_entity = next((key for key, pattern in _ENTITY.items() if pattern.search(text)), "")
        selected = [item for item in bindings if (not domain or item.get("domain") == domain)
                    and (not answer_entity or item.get("entity_id") == answer_entity)]
        historical_domain_only = clarification.get("historical_domain_only") is True
        if domain and domain in allowed and (len(selected) == 1 or historical_domain_only):
            target = selected[0] if len(selected) == 1 else clarification
            event = _event(parsed, clarification, "clarification_consumed", domain=domain,
                resolved_mission_id=str(target.get("mission_id") or clarification.get("target_mission_id") or ""),
                resolved_card_mission_id=str(target.get("card_mission_id") or clarification.get("target_card_mission_id") or ""),
                resolved_execution_id=str(target.get("execution_id") or clarification.get("target_execution_id") or ""))
            try: recorded = store("record", event["event_id"], event)
            except Exception: return _contained("owner_operational_transition_persistence_failed"), 503
            if recorded.get("created") is False:
                return _replay(event, "clarification_replayed_noop"), 200
            if recorded.get("success") is not True or recorded.get("created") is not True:
                return _contained("owner_operational_transition_persistence_failed"), 503
            return {"handled": True, "success": True, "status": "owner_clarification_consumed",
                    "suppress_owner_delivery": True, "domain": domain,
                    "mission_id": target.get("mission_id") or clarification.get("target_mission_id") or clarification.get("mission_id"),
                    "card_mission_id": target.get("card_mission_id") or clarification.get("target_card_mission_id") or clarification.get("card_mission_id"),
                    "execution_id": target.get("execution_id") or clarification.get("target_execution_id"),
                    "telegram_sends": 0, "telegram_edits": 0, **_zero_authority()}, 200
        if domain and domain in allowed:
            return {"handled": True, "success": True,
                    "status": "owner_clarification_still_pending",
                    "suppress_owner_delivery": True,
                    "mission_id": clarification.get("mission_id"),
                    "card_mission_id": clarification.get("card_mission_id"),
                    "question_count": 0, **_zero_authority()}, 200
    return {"handled": False}, 200


def _compatible(active, entity, terminal_state, parsed):
    result = []
    for item in active or ():
        if str(item.get("state") or "") not in {"Active", "active", "StoppedAwaitingVerification", "StoppedUnverifiedContained"}:
            continue
        if terminal_state and str(item.get("domain") or "").lower() != "irrigation":
            continue
        target_entity = str(item.get("entity_id") or "")
        if entity and target_entity and entity != target_entity:
            continue
        if entity and not target_entity and entity not in str(item.get("card_mission_id") or ""):
            continue
        reply = str(parsed.get("reply_to_message_id") or "")
        exact_reply = bool(reply and reply == str(item.get("telegram_message_id") or ""))
        if not entity and not exact_reply and not _IMPLICIT_STOP.fullmatch(str(parsed.get("text") or "")):
            continue
        started = _time(item.get("execution_started_at"))
        observed = _time(parsed.get("provider_timestamp"))
        if not started or not observed or observed < started:
            continue
        result.append(item)
    return result


def _unique_pending(pending, parsed):
    reply = str(parsed.get("reply_to_message_id") or "")
    matches = ([item for item in pending or () if str(item.get("telegram_message_id") or "") == reply]
               if reply else list(pending or ()))
    if len(matches) != 1:
        return None
    item = matches[0]
    asked = _time(item.get("clarification_delivered_at"))
    answered = _time(parsed.get("provider_timestamp"))
    return item if asked and answered and asked < answered <= asked + timedelta(minutes=5) else None


def _affirmative_stop(text, entity):
    lower = str(text or "").lower()
    if re.search(r"\b(?:not|isn't|isnt|nie)\s+(?:physically\s+)?(?:off|stopped|af|gestop)\b", lower):
        return False
    if entity:
        match = _ENTITY_ASSERTION.search(str(text or ""))
        return bool(match and ((match.group("entity").lower() == "c") == (entity == "C12345")))
    return bool(_IMPLICIT_STOP.fullmatch(str(text or "")))


def _domain(text):
    return "irrigation" if _ROOTLINE.search(text) else ""


def _event(parsed, target, state, **extra):
    provider = str(parsed.get("provider_message_id") or "")
    mission = str(target.get("mission_id") or "")
    return {"event_id": mission + "-OWNER-" + provider + "-" + state.upper(),
        "mission_id": mission, "card_mission_id": str(target.get("card_mission_id") or mission),
        "execution_id": str(target.get("execution_id") or ""),
        "owner_user_id": str(parsed.get("telegram_user_id") or ""),
        "chat_id": str(parsed.get("telegram_chat_id") or ""),
        "provider_message_id": provider, "provider_timestamp": str(parsed.get("provider_timestamp") or ""),
        "text_sha256": hashlib.sha256(str(parsed.get("text") or "").encode()).hexdigest(),
        "state": state, **extra}


def _replay(event, status):
    return {"handled": True, "success": True, "status": status,
        "mission_id": event.get("mission_id"), "suppress_owner_delivery": True,
        "telegram_sends": 0, "telegram_edits": 0, **_zero_authority()}


def _contained(status):
    return {"handled": True, "success": False, "status": status, **_zero_authority()}


def _indeterminate(status):
    return {**_contained(status), "writes_operational_outcome": None,
            "writes_operational_outcome_unknown": True}


def _zero_authority():
    return {"writes_farm_data": False, "hardware_commands": 0,
        "writes_operational_outcome": False,
        "protected_actions_performed": False, "automatic_second_segment": False,
        "telegram_sends": 0, "telegram_edits": 0}


def _time(value):
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def _load_active_context(owner, chat, provider=""):
    import psycopg
    if not str(os.environ.get("DATABASE_URL") or "").strip():
        return [], []
    with psycopg.connect(os.environ["DATABASE_URL"], connect_timeout=10) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'owner_operational_context'
                from public.sam_live_stock_conversation_review_events
                where event_source=%s and review_json->'owner_operational_context'->>'owner_user_id'=%s
                  and review_json->'owner_operational_context'->>'chat_id'=%s order by created_at""",
                (EVENT_SOURCE, owner, chat))
            own = [row[0] for row in cursor.fetchall()]
            cursor.execute("""select review_json->'family_message_lifecycle'
                from public.sam_live_stock_conversation_review_events
                where event_source='oom_sakkie_family_message_lifecycle'
                  and review_json->'family_message_lifecycle'->>'owner_user_id'=%s
                  and review_json->'family_message_lifecycle'->>'chat_id'=%s
                  and created_at > now()-interval '2 days' order by created_at""", (owner, chat))
            family = [row[0] for row in cursor.fetchall()]
    delivered_questions = {str(item.get("card_mission_id") or ""): item for item in family
                           if item.get("state") == "delivered"
                           and str(item.get("delivery_provider_timestamp") or "")}
    pending = [{**item,
                "telegram_message_id": delivered_questions[str(item.get("card_mission_id") or "")].get("telegram_message_id"),
                "clarification_delivered_at": delivered_questions[str(item.get("card_mission_id") or "")].get("delivery_provider_timestamp")}
               for item in own if item.get("state") == "clarification_pending"
               and str(item.get("card_mission_id") or "") in delivered_questions
               and not any(later.get("mission_id") == item.get("mission_id") and
                           later.get("state") == "clarification_consumed" for later in own)]
    latest = {}
    for item in family:
        card = str(item.get("card_mission_id") or "")
        if card:
            latest[card] = item
    active = []
    bindings = {str(item.get("card_mission_id") or ""): item for item in own
                if item.get("state") == "active_lifecycle_bound"}
    completed = {str(item.get("card_mission_id") or "") for item in own
                 if item.get("state") == "execution_completed"}
    for card, item in latest.items():
        if card in completed:
            continue
        task = str(item.get("task_state") or "")
        if item.get("specialist_identity") == "ROOTLINE" and task in {"Active", "Stopped", "Failed"}:
            binding = bindings.get(card, {})
            entity = "C12345" if "C-SEGMENT" in card else ("B12345" if "B-SEGMENT" in card else "")
            active.append({"mission_id": item.get("mission_id"), "card_mission_id": card,
                "execution_id": binding.get("execution_id") or item.get("execution_id"), "domain": "irrigation",
                "entity_id": binding.get("entity_id") or entity,
                "state": binding.get("execution_state") or task,
                "execution_started_at": binding.get("execution_started_at"),
                "telegram_message_id": item.get("telegram_message_id"),
                "completion_card_mission_id": card + "-COMPLETION"})
    exact = [item for item in own if str(item.get("provider_message_id") or "") == provider]
    return pending, active, exact


def _completion_result(event):
    entity = str(event.get("entity") or event.get("entity_id") or "")
    label = str(event.get("label") or ("C Camp" if entity == "C12345" else "B Camp"))
    mission = str(event.get("mission_id") or "")
    return {"handled": True, "success": True, "status": "Completed",
        "specialist_identity": "ROOTLINE", "mission_id": mission,
        "card_mission_id": str(event.get("completion_card_mission_id") or
                                (str(event.get("card_mission_id") or mission) + "-COMPLETION")),
        "execution_id": str(event.get("execution_id") or ""),
        "observation": {"state": "Stopped", "entity_id": entity,
            "provider_message_id": str(event.get("provider_message_id") or ""),
            "observed_at": str(event.get("provider_timestamp") or ""),
            "owner_reported": True, "continuous_flow": "Unknown",
            "delivered_volume": "Unknown", "exact_runtime": "Unknown"},
        "answer": (f"<b>IRRIGATION COMPLETE - {label.upper()}</b>\n\n"
                   f"{label} is physically stopped. I closed this irrigation segment from your "
                   "timestamped observation. No second segment was started."),
        **_zero_authority(), "writes_operational_outcome": True}


def _context_store(action, identity, payload):
    if action != "record":
        raise ValueError("unsupported_context_store_action")
    from modules.sales.sam_live_stock_launch_control import build_sam_live_stock_review_event, record_sam_live_stock_review_event
    event = build_sam_live_stock_review_event({"conversation_id": payload["mission_id"]}, {}, {},
        {"score": 0, "safe_to_send": False, "recommended_action": "owner_operational_continuation"},
        event_source=EVENT_SOURCE)
    event["review_event_id"] = identity
    event["chatwoot_conversation_id"] = payload["mission_id"]
    event["review_json"] = {"owner_operational_context": dict(payload)}
    event["decision_json"] = {}; event["facts_json"] = {}
    event["customer_message_excerpt"] = ""; event["sam_reply_excerpt"] = ""
    result, status = record_sam_live_stock_review_event(event)
    return {**result, "success": status < 400 and result.get("success") is True,
            "created": status == 201 and result.get("created") is True}
