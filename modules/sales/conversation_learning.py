import hashlib
import json
import os
import re
from difflib import SequenceMatcher
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV


LEARNING_EVENT_TYPES = {
    "sam_inbound_observation",
    "owner_review_note",
    "conversion_observed",
    "loss_observed",
}

CONVERSION_SIGNALS = {
    "unknown",
    "new_interest",
    "qualified_interest",
    "needs_followup",
    "booking_review_requested",
    "deposit_proof_received_unverified",
    "lost_or_not_fit",
}

AUTHORITY_FLAGS = {
    "applies_learning_now": False,
    "changes_prompt_now": False,
    "changes_runtime_now": False,
    "sends_customer_message": False,
    "calls_chatwoot": False,
    "calls_n8n": False,
    "calls_meta": False,
    "creates_quote": False,
    "creates_invoice": False,
    "creates_order": False,
    "changes_stock": False,
    "reserves_stock": False,
    "dispatch_enabled": False,
    "physical_controls_enabled": False,
    "customer_public_output_enabled": False,
    "writes_farm_data": False,
}


def build_learning_event_from_sam_result(sam_result):
    sam_result = sam_result if isinstance(sam_result, dict) else {}
    inbound = sam_result.get("inbound") if isinstance(sam_result.get("inbound"), dict) else {}
    facts = sam_result.get("facts") if isinstance(sam_result.get("facts"), dict) else {}
    decision = sam_result.get("sam_decision") if isinstance(sam_result.get("sam_decision"), dict) else {}
    lead_payload = sam_result.get("lead_payload") if isinstance(sam_result.get("lead_payload"), dict) else {}
    lead_result = sam_result.get("lead_result") if isinstance(sam_result.get("lead_result"), dict) else {}

    lead_id = _clean(decision.get("lead_id") or lead_payload.get("lead_id") or lead_result.get("lead_id"), 120)
    conversation_id = _clean(inbound.get("conversation_id"), 120)
    message = _clean(inbound.get("content"), 1200)
    reply = _clean(decision.get("reply_text"), 1200)
    missing_facts = _missing_facts(facts)
    objections = _objections(message)
    confusion = _confusion_signals(message, facts, reply)
    sam_misses = _sam_misses(message, facts, decision, missing_facts)
    conversion_signal = _conversion_signal(message, facts, decision, missing_facts, sam_result)
    event = {
        "learning_event_id": _learning_event_id({
            "lead_id": lead_id,
            "conversation_id": conversation_id,
            "message": message,
            "reply": reply,
            "last_inbound_at": inbound.get("last_inbound_at") or "",
        }),
        "lead_id": lead_id,
        "chatwoot_conversation_id": conversation_id,
        "channel": _clean(inbound.get("channel") or lead_payload.get("channel") or "chatwoot_whatsapp", 80),
        "source_agent": "sam_meat_backend",
        "event_source": "chatwoot_inbound",
        "event_type": "sam_inbound_observation",
        "customer_message_excerpt": _clip(message, 500),
        "sam_reply_excerpt": _clip(reply, 500),
        "customer_wanted": _customer_wanted(facts),
        "captured_facts": _captured_facts(facts),
        "missing_facts": missing_facts,
        "objections": objections,
        "confusion_signals": confusion,
        "sam_misses": sam_misses,
        "conversion_signal": conversion_signal,
        "improvement_suggestion": _improvement_suggestion(missing_facts, objections, confusion, sam_misses, conversion_signal),
        "campaign_source": _clean(lead_payload.get("campaign_source") or "inbound_chatwoot", 80),
        "recorded_by": "sales_conversation_learning_loop",
        **AUTHORITY_FLAGS,
    }
    return event


def build_owner_review_learning_event(lead_id, payload=None):
    payload = payload if isinstance(payload, dict) else {}
    notes = _clean(payload.get("notes") or payload.get("owner_note"), 1200)
    event_type = _event_type(payload.get("event_type") or "owner_review_note")
    conversion_signal = _conversion_signal_value(payload.get("conversion_signal") or "unknown")
    event = {
        "learning_event_id": _learning_event_id({
            "lead_id": lead_id,
            "notes": notes,
            "event_type": event_type,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }),
        "lead_id": _clean(lead_id, 120),
        "chatwoot_conversation_id": _clean(payload.get("chatwoot_conversation_id"), 120),
        "channel": _clean(payload.get("channel") or "owner_review", 80),
        "source_agent": _clean(payload.get("source_agent") or "owner", 80),
        "event_source": _clean(payload.get("event_source") or "owner_review", 80),
        "event_type": event_type,
        "customer_message_excerpt": _clip(_clean(payload.get("customer_message_excerpt"), 1200), 500),
        "sam_reply_excerpt": _clip(_clean(payload.get("sam_reply_excerpt"), 1200), 500),
        "customer_wanted": _dict(payload.get("customer_wanted")),
        "captured_facts": _dict(payload.get("captured_facts")),
        "missing_facts": _list(payload.get("missing_facts")),
        "objections": _list(payload.get("objections")),
        "confusion_signals": _list(payload.get("confusion_signals")),
        "sam_misses": _list(payload.get("sam_misses")),
        "conversion_signal": conversion_signal,
        "improvement_suggestion": _clean(payload.get("improvement_suggestion") or notes, 600),
        "campaign_source": _clean(payload.get("campaign_source"), 80),
        "recorded_by": _clean(payload.get("recorded_by") or "owner_review", 80),
        **AUTHORITY_FLAGS,
    }
    return event


def build_live_stock_owner_reply_learning_event(outbound, latest_review_event=None):
    outbound = outbound if isinstance(outbound, dict) else {}
    latest_review_event = latest_review_event if isinstance(latest_review_event, dict) else {}
    conversation_id = _clean(outbound.get("conversation_id") or latest_review_event.get("chatwoot_conversation_id"), 120)
    owner_reply = _clean(outbound.get("content") or outbound.get("owner_reply_text"), 1800)
    sam_draft = _clean(latest_review_event.get("sam_reply_excerpt"), 1800)
    customer_message = _clean(latest_review_event.get("customer_message_excerpt"), 1200)
    facts = _dict(latest_review_event.get("facts_json"))
    decision = _dict(latest_review_event.get("decision_json"))
    review_event_id = _clean(latest_review_event.get("review_event_id"), 120)
    review_created_at = _clean(latest_review_event.get("created_at"), 80)
    outbound_created_at = _clean(outbound.get("created_at") or outbound.get("last_inbound_at"), 80)
    age_seconds = _seconds_between(review_created_at, outbound_created_at)
    stale_review_link = age_seconds is not None and age_seconds > 12 * 60 * 60
    if stale_review_link:
        sam_draft = ""
        review_event_id = ""
    classification = _owner_reply_classification(owner_reply, sam_draft)
    lead_id = _clean(outbound.get("lead_id") or f"SAM-LIVE-CONV-{conversation_id}", 120)
    event = {
        "learning_event_id": _learning_event_id({
            "lead_id": lead_id,
            "conversation_id": conversation_id,
            "review_event_id": review_event_id,
            "owner_reply": owner_reply,
            "message_id": outbound.get("message_id") or "",
        }),
        "lead_id": lead_id,
        "chatwoot_conversation_id": conversation_id,
        "channel": _clean(outbound.get("channel") or latest_review_event.get("channel") or "chatwoot_whatsapp", 80),
        "source_agent": "sam_live_stock_backend",
        "event_source": "chatwoot_outgoing_owner_reply",
        "event_type": "owner_review_note",
        "customer_message_excerpt": _clip(customer_message, 500),
        "sam_reply_excerpt": _clip(sam_draft, 500),
        "customer_wanted": _live_stock_customer_wanted(facts),
        "captured_facts": {
            "learning_kind": "owner_reply_capture",
            "review_event_id": review_event_id,
            "owner_reply_excerpt": _clip(owner_reply, 500),
            "owner_reply_classification": classification,
            "sam_reply_similarity": _reply_similarity(owner_reply, sam_draft),
            "recommended_action": _clean(latest_review_event.get("recommended_action"), 120),
            "review_event_created_at": review_created_at,
            "owner_reply_created_at": outbound_created_at,
            "review_reply_delta_seconds": age_seconds,
            "stale_review_link": stale_review_link,
            "customer_language": _clean(facts.get("customer_language"), 40),
            "conversation_stage": _clean(decision.get("conversation_stage") or (decision.get("conversation_plan") or {}).get("stage"), 80),
            "reply_class": _clean(facts.get("message_intent") or "unclear", 80),
        },
        "missing_facts": _list((latest_review_event.get("decision_json") or {}).get("missing_fields") if isinstance(latest_review_event.get("decision_json"), dict) else []),
        "objections": _objections(owner_reply),
        "confusion_signals": _live_stock_confusion_signals(owner_reply, latest_review_event),
        "sam_misses": _live_stock_owner_reply_misses(classification, owner_reply, sam_draft),
        "conversion_signal": _live_stock_conversion_signal(owner_reply, classification),
        "improvement_suggestion": _live_stock_owner_reply_suggestion(classification, owner_reply),
        "campaign_source": "sam_live_stock_chatwoot",
        "recorded_by": "sam_live_stock_owner_reply_capture",
        **AUTHORITY_FLAGS,
    }
    return event


def record_learning_event_from_sam_result(sam_result, database_url=None):
    event = build_learning_event_from_sam_result(sam_result)
    if not event.get("lead_id"):
        return {
            "success": False,
            "status": "lead_id_required",
            "learning_event": event,
            **AUTHORITY_FLAGS,
        }, 400
    return record_sales_conversation_learning_event(event, database_url=database_url)


def record_sales_conversation_learning_event(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _event_params(payload)
    if not params["lead_id"]:
        return {"success": False, "status": "lead_id_required", "learning_event": params, **AUTHORITY_FLAGS}, 400
    if not params["learning_event_id"]:
        params["learning_event_id"] = _learning_event_id(params)

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.meat_sales_conversation_learning_events (
                        learning_event_id,
                        lead_id,
                        chatwoot_conversation_id,
                        channel,
                        source_agent,
                        event_source,
                        event_type,
                        customer_message_excerpt,
                        sam_reply_excerpt,
                        customer_wanted_json,
                        captured_facts_json,
                        missing_facts_json,
                        objections_json,
                        confusion_signals_json,
                        sam_misses_json,
                        conversion_signal,
                        improvement_suggestion,
                        campaign_source,
                        recorded_by,
                        applies_learning_now,
                        changes_prompt_now,
                        changes_runtime_now,
                        sends_customer_message,
                        calls_chatwoot,
                        calls_n8n,
                        calls_meta,
                        creates_quote,
                        creates_invoice,
                        creates_order,
                        changes_stock,
                        reserves_stock,
                        dispatch_enabled,
                        physical_controls_enabled,
                        customer_public_output_enabled,
                        writes_farm_data
                    )
                    values (
                        %(learning_event_id)s,
                        %(lead_id)s,
                        %(chatwoot_conversation_id)s,
                        %(channel)s,
                        %(source_agent)s,
                        %(event_source)s,
                        %(event_type)s,
                        %(customer_message_excerpt)s,
                        %(sam_reply_excerpt)s,
                        %(customer_wanted_json)s::jsonb,
                        %(captured_facts_json)s::jsonb,
                        %(missing_facts_json)s::jsonb,
                        %(objections_json)s::jsonb,
                        %(confusion_signals_json)s::jsonb,
                        %(sam_misses_json)s::jsonb,
                        %(conversion_signal)s,
                        %(improvement_suggestion)s,
                        %(campaign_source)s,
                        %(recorded_by)s,
                        %(applies_learning_now)s,
                        %(changes_prompt_now)s,
                        %(changes_runtime_now)s,
                        %(sends_customer_message)s,
                        %(calls_chatwoot)s,
                        %(calls_n8n)s,
                        %(calls_meta)s,
                        %(creates_quote)s,
                        %(creates_invoice)s,
                        %(creates_order)s,
                        %(changes_stock)s,
                        %(reserves_stock)s,
                        %(dispatch_enabled)s,
                        %(physical_controls_enabled)s,
                        %(customer_public_output_enabled)s,
                        %(writes_farm_data)s
                    )
                    on conflict (learning_event_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_conversation_learning_write_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "learning_event": params,
            **AUTHORITY_FLAGS,
        }, 500

    return {
        "success": True,
        "configured": True,
        "status": "sales_conversation_learning_event_recorded" if created_count else "sales_conversation_learning_event_already_recorded",
        "created_count": created_count,
        "learning_event_id": params["learning_event_id"],
        "lead_id": params["lead_id"],
        "learning_event": _public_event(params),
        "next_gate": "atlas_or_owner_review_before_prompt_rule_or_workflow_change",
        **AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def list_sales_conversation_learning_events(limit=50, lead_id="", database_url=None):
    try:
        limit = max(1, min(int(limit), 1000))
    except (TypeError, ValueError):
        limit = 50
    lead_id = _clean(lead_id, 120)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    where = "where lead_id = %(lead_id)s" if lead_id else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select learning_event_id, lead_id, chatwoot_conversation_id, channel,
                           source_agent, event_source, event_type, customer_message_excerpt,
                           sam_reply_excerpt, customer_wanted_json, captured_facts_json,
                           missing_facts_json, objections_json, confusion_signals_json,
                           sam_misses_json, conversion_signal, improvement_suggestion,
                           campaign_source, recorded_by, created_at
                    from public.meat_sales_conversation_learning_events
                    {where}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {"limit": limit, "lead_id": lead_id},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_conversation_learning_read_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "learning_events": [],
            "summary": {},
            **AUTHORITY_FLAGS,
        }, 500

    events = [_row_to_event(row) for row in rows]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "sales_conversation_learning_append_only",
        "learning_events": events,
        "summary": summarize_sales_conversation_learning(events),
        "next_gate": "atlas_or_owner_review_before_prompt_rule_or_workflow_change",
        **AUTHORITY_FLAGS,
    }, 200


def list_live_stock_owner_reply_examples(conversation_id="", limit=3, database_url=None, customer_message="", customer_language="", conversation_stage="", reply_class=""):
    try:
        limit = max(1, min(int(limit), 10))
    except (TypeError, ValueError):
        limit = 3
    conversation_id = _clean(conversation_id, 120)
    customer_message = _clean(customer_message, 1200)
    customer_language = _clean(customer_language, 40)
    conversation_stage = _clean(conversation_stage, 80)
    reply_class = _clean(reply_class, 80)
    candidate_limit = min(max(limit * 6, limit), 30)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    params = {"conversation_id": conversation_id, "limit": candidate_limit}
    same_conversation_where = "and chatwoot_conversation_id = %(conversation_id)s" if conversation_id else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select customer_message_excerpt, sam_reply_excerpt, captured_facts_json, created_at
                    from public.meat_sales_conversation_learning_events
                    where source_agent = 'sam_live_stock_backend'
                      and captured_facts_json->>'learning_kind' in ('owner_reply_capture', 'owner_reply_historical_example')
                      and captured_facts_json->>'owner_reply_classification' in ('owner_edited', 'owner_replaced', 'owner_reply_no_sam_draft')
                      {same_conversation_where}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    params,
                )
                rows = cursor.fetchall()
                if len(rows) < limit:
                    cursor.execute(
                        """
                        select customer_message_excerpt, sam_reply_excerpt, captured_facts_json, created_at
                        from public.meat_sales_conversation_learning_events
                        where source_agent = 'sam_live_stock_backend'
                          and captured_facts_json->>'learning_kind' in ('owner_reply_capture', 'owner_reply_historical_example')
                          and captured_facts_json->>'owner_reply_classification' in ('owner_edited', 'owner_replaced', 'owner_reply_no_sam_draft')
                        order by created_at desc
                        limit %(limit)s
                        """,
                        params,
                    )
                    seen = {_example_key(row) for row in rows}
                    for row in cursor.fetchall():
                        key = _example_key(row)
                        if key not in seen:
                            rows.append(row)
                            seen.add(key)
                        if len(rows) >= candidate_limit:
                            break
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_conversation_learning_read_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "examples": [],
            **AUTHORITY_FLAGS,
        }, 500

    ranked_rows = _rank_owner_reply_example_rows(
        rows,
        current_customer_message=customer_message,
        current_conversation_id=conversation_id,
        customer_language=customer_language,
        conversation_stage=conversation_stage,
        reply_class=reply_class,
    )
    return {
        "success": True,
        "configured": True,
        "status": "sam_live_stock_owner_reply_examples_loaded",
        "examples": [_owner_reply_example_from_row(row) for row in ranked_rows[:limit]],
        "ranking": {
            "current_message_used": bool(customer_message),
            "candidate_count": len(rows),
            "top_relevance_score": ranked_rows[0][4] if ranked_rows and len(ranked_rows[0]) > 4 else 0.0,
        },
        **AUTHORITY_FLAGS,
    }, 200


def summarize_sales_conversation_learning(events):
    events = events if isinstance(events, list) else []
    summary = {
        "total_events": len(events),
        "conversion_signals": {},
        "missing_facts": {},
        "objections": {},
        "confusion_signals": {},
        "sam_misses": {},
        "top_improvement_suggestions": [],
    }
    suggestions = []
    for event in events:
        signal = _clean(event.get("conversion_signal") or "unknown", 80)
        summary["conversion_signals"][signal] = summary["conversion_signals"].get(signal, 0) + 1
        for key in ("missing_facts", "objections", "confusion_signals", "sam_misses"):
            for item in _list(event.get(key)):
                item = _clean(item, 120)
                if item:
                    summary[key][item] = summary[key].get(item, 0) + 1
        suggestion = _clean(event.get("improvement_suggestion"), 300)
        if suggestion:
            suggestions.append(suggestion)
    summary["top_improvement_suggestions"] = _top_values(suggestions, limit=5)
    return summary


def live_stock_learning_scorecard(database_url=None, limit=500):
    from modules.sales.sam_live_stock_evaluation import owner_learning_scorecard

    payload, status_code = list_sales_conversation_learning_events(limit=limit, database_url=database_url)
    if status_code >= 400:
        return payload, status_code
    return {
        "success": True,
        "status": "sam_live_stock_learning_scorecard_ready",
        "scorecard": owner_learning_scorecard(payload.get("learning_events") or []),
        **AUTHORITY_FLAGS,
    }, 200


def _event_params(payload):
    event_type = _event_type(payload.get("event_type") or "sam_inbound_observation")
    params = {
        "learning_event_id": _clean(payload.get("learning_event_id"), 120),
        "lead_id": _clean(payload.get("lead_id"), 120),
        "chatwoot_conversation_id": _clean(payload.get("chatwoot_conversation_id") or payload.get("conversation_id"), 120),
        "channel": _clean(payload.get("channel") or "chatwoot_whatsapp", 80),
        "source_agent": _clean(payload.get("source_agent") or "sam_meat_backend", 80),
        "event_source": _clean(payload.get("event_source") or "chatwoot_inbound", 80),
        "event_type": event_type,
        "customer_message_excerpt": _clip(_clean(payload.get("customer_message_excerpt") or payload.get("customer_message"), 1200), 500),
        "sam_reply_excerpt": _clip(_clean(payload.get("sam_reply_excerpt") or payload.get("sam_reply"), 1200), 500),
        "customer_wanted_json": _json(_dict(payload.get("customer_wanted"))),
        "captured_facts_json": _json(_dict(payload.get("captured_facts"))),
        "missing_facts_json": _json(_list(payload.get("missing_facts"))),
        "objections_json": _json(_list(payload.get("objections"))),
        "confusion_signals_json": _json(_list(payload.get("confusion_signals"))),
        "sam_misses_json": _json(_list(payload.get("sam_misses"))),
        "conversion_signal": _conversion_signal_value(payload.get("conversion_signal") or "unknown"),
        "improvement_suggestion": _clean(payload.get("improvement_suggestion"), 600),
        "campaign_source": _clean(payload.get("campaign_source"), 80),
        "recorded_by": _clean(payload.get("recorded_by") or "sales_conversation_learning_loop", 80),
        **AUTHORITY_FLAGS,
    }
    return params


def _public_event(params):
    return {
        "learning_event_id": params.get("learning_event_id", ""),
        "lead_id": params.get("lead_id", ""),
        "chatwoot_conversation_id": params.get("chatwoot_conversation_id", ""),
        "channel": params.get("channel", ""),
        "source_agent": params.get("source_agent", ""),
        "event_source": params.get("event_source", ""),
        "event_type": params.get("event_type", ""),
        "customer_message_excerpt": params.get("customer_message_excerpt", ""),
        "sam_reply_excerpt": params.get("sam_reply_excerpt", ""),
        "customer_wanted": _loads(params.get("customer_wanted_json"), {}),
        "captured_facts": _loads(params.get("captured_facts_json"), {}),
        "missing_facts": _loads(params.get("missing_facts_json"), []),
        "objections": _loads(params.get("objections_json"), []),
        "confusion_signals": _loads(params.get("confusion_signals_json"), []),
        "sam_misses": _loads(params.get("sam_misses_json"), []),
        "conversion_signal": params.get("conversion_signal", ""),
        "improvement_suggestion": params.get("improvement_suggestion", ""),
        "campaign_source": params.get("campaign_source", ""),
        "recorded_by": params.get("recorded_by", ""),
        **AUTHORITY_FLAGS,
    }


def _row_to_event(row):
    return {
        "learning_event_id": row[0],
        "lead_id": row[1],
        "chatwoot_conversation_id": row[2],
        "channel": row[3],
        "source_agent": row[4],
        "event_source": row[5],
        "event_type": row[6],
        "customer_message_excerpt": row[7],
        "sam_reply_excerpt": row[8],
        "customer_wanted": row[9] or {},
        "captured_facts": row[10] or {},
        "missing_facts": row[11] or [],
        "objections": row[12] or [],
        "confusion_signals": row[13] or [],
        "sam_misses": row[14] or [],
        "conversion_signal": row[15],
        "improvement_suggestion": row[16],
        "campaign_source": row[17],
        "recorded_by": row[18],
        "created_at": row[19].isoformat() if hasattr(row[19], "isoformat") else str(row[19] or ""),
        **AUTHORITY_FLAGS,
    }


def _owner_reply_example_from_row(row):
    captured = row[2] or {}
    if isinstance(captured, str):
        captured = _loads(captured, {})
    return {
        "customer_message_excerpt": _clip(row[0] or "", 300),
        "rejected_sam_draft": _clip(row[1] or "", 500),
        "owner_reply_excerpt": _clip(captured.get("owner_reply_excerpt") or "", 500),
        "classification": _clean(captured.get("owner_reply_classification"), 80),
        "created_at": row[3].isoformat() if hasattr(row[3], "isoformat") else str(row[3] or ""),
        "example_relevance_score": row[4] if len(row) > 4 else 0.0,
    }


def _rank_owner_reply_example_rows(rows, current_customer_message="", current_conversation_id="", customer_language="", conversation_stage="", reply_class=""):
    current_customer_message = _normal_reply(current_customer_message)
    current_conversation_id = _clean(current_conversation_id, 120)
    ranked = []
    for index, row in enumerate(rows or []):
        row = tuple(row)
        candidate_message = row[0] if len(row) > 0 else ""
        score = _reply_similarity(current_customer_message, candidate_message) if current_customer_message else 0.0
        captured = row[2] if len(row) > 2 else {}
        if isinstance(captured, str):
            captured = _loads(captured, {})
        row_conversation_id = _clean(captured.get("chatwoot_conversation_id") or captured.get("conversation_id"), 120)
        same_conversation = bool(current_conversation_id and row_conversation_id == current_conversation_id)
        if customer_language and _clean(captured.get("customer_language"), 40) == customer_language:
            score += 0.12
        if conversation_stage and _clean(captured.get("conversation_stage"), 80) == conversation_stage:
            score += 0.10
        if reply_class and _clean(captured.get("reply_class"), 80) == reply_class:
            score += 0.18
        score = round(min(score, 1.0), 3)
        ranked.append((score, same_conversation, -index, row + (score,)))
    ranked.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
    return [item[3] for item in ranked]


def _example_key(row):
    captured = row[2] or {}
    if isinstance(captured, str):
        captured = _loads(captured, {})
    return "|".join([
        _clean(row[0], 120),
        _clean(row[1], 120),
        _clean(captured.get("owner_reply_excerpt"), 120),
    ])


def _customer_wanted(facts):
    wanted = {}
    for key in ("product_type", "cut_set", "location", "delivery_or_collection", "timing", "payment_method", "budget_amount", "target_packed_kg", "match_preference"):
        if facts.get(key):
            wanted[key] = facts.get(key)
    return wanted


def _captured_facts(facts):
    allowed = (
        "product_type", "cut_set", "location", "timing", "delivery_or_collection",
        "delivery_address_line_1", "delivery_town", "delivery_area", "delivery_notes",
        "delivery_place_name", "delivery_location_latitude", "delivery_location_longitude",
        "payment_method", "budget_amount", "target_packed_kg", "match_preference",
        "llm_used",
    )
    captured = {}
    for key in allowed:
        value = facts.get(key)
        if value in {"", None} or value == []:
            continue
        captured[key] = value
    return captured


def _live_stock_customer_wanted(facts):
    wanted = {}
    for key in ("sales_lane", "category", "quantity", "sex", "weight_range", "timing", "location", "payment_method"):
        if facts.get(key):
            wanted[key] = facts.get(key)
    return wanted


def _missing_facts(facts):
    missing = []
    product_type = facts.get("product_type") or "unknown"
    if product_type == "unknown":
        missing.append("product_type")
    if product_type in {"half_carcass", "full_carcass", "custom_cut"} and not facts.get("cut_set"):
        missing.append("cut_set")
    if not facts.get("location"):
        missing.append("location")
    if not facts.get("delivery_or_collection"):
        missing.append("delivery_or_collection")
    if facts.get("delivery_or_collection") == "delivery" and not facts.get("delivery_address_line_1"):
        missing.append("delivery_address")
    if not facts.get("timing"):
        missing.append("timing")
    if not facts.get("payment_method"):
        missing.append("payment_method")
    return missing


def _objections(message):
    text = message.lower()
    objections = []
    if re.search(r"\b(expensive|too much|price|cost|cheaper|discount|budget)\b", text):
        objections.append("price_or_budget")
    if re.search(r"\b(when|today|tomorrow|urgent|soon|available now|next week)\b", text):
        objections.append("timing_or_availability")
    if re.search(r"\b(delivery|deliver|far|address|location|where)\b", text):
        objections.append("delivery_or_location")
    if re.search(r"\b(deposit|pop|proof of payment|paid|eft|cash|bank)\b", text):
        objections.append("payment_or_deposit")
    if re.search(r"\b(what.*include|set a|set b|cuts|chops|mince|ribs)\b", text):
        objections.append("cut_set_clarity")
    return objections


def _confusion_signals(message, facts, reply):
    text = message.lower()
    reply_text = reply.lower()
    signals = []
    if re.search(r"\b(live pig|piglet|weaner|boar|sow)\b", text) and facts.get("product_type") != "unknown":
        signals.append("live_vs_meat_confusion")
    if re.search(r"\b(beef|lamb|chicken|goat)\b", text):
        signals.append("non_pork_request")
    if "half" in text and "full" in reply_text and facts.get("product_type") == "unknown":
        signals.append("product_extraction_unclear")
    if re.search(r"\b(confused|don't understand|not sure|what do you mean)\b", text):
        signals.append("customer_confusion")
    if re.search(r"\b(angry|ridiculous|stupid|frustrated|fuck)\b", text):
        signals.append("customer_frustration")
    if re.search(r"\b(no personality|human factor|too robotic|robot|rigid|cold)\b", text):
        signals.append("robotic_tone")
    return signals


def _live_stock_confusion_signals(message, latest_review_event):
    signals = []
    text = _clean(message, 1200).lower()
    if re.search(r"\b(job|work|hiring|employment|cv)\b", text):
        signals.append("not_sales_job_request")
    if re.search(r"\b(where|location|province|far|transport|deliver|delivery)\b", text):
        signals.append("location_or_transport_question")
    if re.search(r"\b(price|how much|cost|r\s?\d+)\b", text):
        signals.append("price_question")
    review = latest_review_event.get("review_json") if isinstance(latest_review_event.get("review_json"), dict) else {}
    if review.get("escalation_required"):
        signals.append("sam_escalated_before_owner_reply")
    return signals


def _live_stock_owner_reply_misses(classification, owner_reply, sam_draft):
    misses = []
    if classification == "owner_replaced":
        misses.append("sam_draft_replaced_by_owner")
    elif classification == "owner_edited":
        misses.append("sam_draft_needed_owner_edit")
    if sam_draft and _reply_similarity(owner_reply, sam_draft) < 0.35:
        misses.append("sam_draft_low_similarity_to_owner_reply")
    return misses


def _live_stock_conversion_signal(owner_reply, classification):
    text = _clean(owner_reply, 1200).lower()
    if re.search(r"\b(not now|no thanks|too far|too expensive|leave it|bye)\b", text):
        return "lost_or_not_fit"
    if re.search(r"\b(price|how much|location|transport|deliver|available|stock|pics|pictures|photo)\b", text):
        return "needs_followup"
    if classification in {"approved_verbatim", "owner_edited", "owner_replaced"}:
        return "qualified_interest"
    return "unknown"


def _live_stock_owner_reply_suggestion(classification, owner_reply):
    if classification == "approved_verbatim":
        return "Owner approved SAM live-stock wording without changes; keep as positive reply example."
    if classification == "owner_edited":
        return "Owner edited SAM live-stock draft; compare wording and feed the corrected style into future draft examples."
    if classification == "owner_replaced":
        return "Owner replaced SAM live-stock draft; treat this as high-value correction for the next drafting prompt."
    if _clean(owner_reply, 1200):
        return "Owner replied without a matching SAM draft; use as live-stock conversation evidence."
    return "No owner reply text captured."


def _owner_reply_classification(owner_reply, sam_draft):
    owner_reply = _normal_reply(owner_reply)
    sam_draft = _normal_reply(sam_draft)
    if not owner_reply:
        return "empty_owner_reply"
    if not sam_draft:
        return "owner_reply_no_sam_draft"
    if owner_reply == sam_draft:
        return "approved_verbatim"
    similarity = _reply_similarity(owner_reply, sam_draft)
    if similarity >= 0.6:
        return "owner_edited"
    return "owner_replaced"


def _reply_similarity(left, right):
    left = _normal_reply(left)
    right = _normal_reply(right)
    if not left or not right:
        return 0.0
    return round(SequenceMatcher(None, left, right).ratio(), 3)


def _normal_reply(value):
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _seconds_between(start, end):
    start_dt = _parse_datetime(start)
    end_dt = _parse_datetime(end)
    if not start_dt or not end_dt:
        return None
    return max(0, int((end_dt - start_dt).total_seconds()))


def _parse_datetime(value):
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _sam_misses(message, facts, decision, missing_facts):
    misses = []
    reply = (decision.get("reply_text") or "").lower()
    text = message.lower()
    if decision.get("should_reply") is False:
        if re.fullmatch(r"\s*(hi|hello|hey|hallo|good morning|good afternoon|good evening|morning|afternoon|evening|hi sam|hello sam|hey sam)[.! ]*\s*", text):
            misses.append("suppressed_opening_greeting")
        elif text.strip():
            misses.append("sam_no_reply")
    if "delivery" in text and "delivery_or_collection" in missing_facts:
        misses.append("missed_delivery_intent")
    if re.search(r"\b(r\s?\d+|budget|about r)\b", text) and not facts.get("budget_amount"):
        misses.append("missed_budget")
    if re.search(r"\b\d+\s?kg\b", text) and not facts.get("target_packed_kg"):
        misses.append("missed_target_weight")
    if "what does set" in text and "set a is" not in reply:
        misses.append("missed_cut_set_question")
    if "fuck" in text and "sorry" not in reply and "understand" not in reply:
        misses.append("missed_frustration_acknowledgement")
    if re.search(r"\b(already paid|paid the deposit|sent pop|pop sent|proof sent|how long does that take)\b", text) and "eft" in reply and "money reflects" not in reply:
        misses.append("repeated_payment_method_after_payment_context")
    if re.search(r"\b(no personality|human factor|too robotic|robot|rigid|cold)\b", text) and "amadeus farm" not in reply:
        misses.append("missed_brand_voice")
    return misses


def _conversion_signal(message, facts, decision, missing_facts, sam_result):
    text = message.lower()
    if sam_result.get("pop_capture", {}).get("recorded") or sam_result.get("pop_capture", {}).get("detected"):
        return "deposit_proof_received_unverified"
    if re.search(r"\b(final booking review|proceed|go ahead|book|confirm)\b", text):
        return "booking_review_requested"
    if re.search(r"\b(not interested|leave it|too expensive|no thanks)\b", text):
        return "lost_or_not_fit"
    if missing_facts:
        return "needs_followup"
    if facts.get("product_type") and facts.get("product_type") != "unknown":
        return "qualified_interest"
    return "new_interest"


def _improvement_suggestion(missing_facts, objections, confusion, sam_misses, conversion_signal):
    if sam_misses:
        return "Review Sam extraction or wording for: " + ", ".join(sam_misses[:3]) + "."
    if confusion:
        return "Improve customer guidance for: " + ", ".join(confusion[:3]) + "."
    if objections:
        return "Track recurring buyer objection: " + ", ".join(objections[:3]) + "."
    if missing_facts:
        return "Sam should keep collecting missing facts before owner review: " + ", ".join(missing_facts[:4]) + "."
    if conversion_signal == "qualified_interest":
        return "Qualified interest captured; compare campaign/source quality after outcome is known."
    if conversion_signal == "booking_review_requested":
        return "Booking-review intent captured; check whether the money/reservation path converts cleanly."
    return "Keep as learning evidence; no immediate change recommended."


def _event_type(value):
    value = _clean(value, 80)
    return value if value in LEARNING_EVENT_TYPES else "sam_inbound_observation"


def _conversion_signal_value(value):
    value = _clean(value, 80)
    return value if value in CONVERSION_SIGNALS else "unknown"


def _learning_event_id(seed):
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:18].upper()
    return f"MSCL-{digest}"


def _unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "sales_conversation_learning_append_only",
        "learning_events": [],
        "summary": {},
        **AUTHORITY_FLAGS,
    }


def _top_values(values, limit=5):
    counts = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    return [
        {"value": value, "count": count}
        for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    if isinstance(value, list):
        return [str(item)[:120] for item in value if str(item or "").strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()[:120]]
    return []


def _json(value):
    return json.dumps(value, sort_keys=True, default=str)


def _loads(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _clean(value, max_len=300):
    return " ".join(str(value or "").strip().split())[:max_len]


def _clip(value, max_len):
    value = str(value or "")
    return value[:max_len]
