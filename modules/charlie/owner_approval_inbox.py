from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV
from modules.charlie.mission_store import (
    get_mission,
    list_owner_work_missions,
    update_mission_vault,
)


INBOX_VERSION = "owner_approval_inbox_v1"
INBOX_MISSION_STATUSES = (
    "in_progress",
    "pr_ready",
    "blocked",
    "approved",
    "new",
)
ALLOWED_SOURCES = {
    "beacon_post_packet": {
        "agent": "Beacon",
        "lane": "public_post",
        "gate": "owner_approves_exact_publish_packet_before_any_public_post",
    },
    "sam_live_stock_reply": {
        "agent": "SAM Live Stock",
        "lane": "customer_reply",
        "gate": "owner_approved_customer_send_gate",
    },
    "sam_meat_controlled_reply": {
        "agent": "SAM Meat",
        "lane": "customer_reply",
        "gate": "meat_customer_send_or_money_path_gate",
    },
    "butcher_recommendation": {
        "agent": "Butcher",
        "lane": "butcher_fulfillment",
        "gate": "owner_approves_butcher_instruction_or_booking_gate",
    },
    "herdmaster_alert": {
        "agent": "Herdmaster",
        "lane": "farm_alert",
        "gate": "owner_approves_farm_lifecycle_or_purpose_gate",
    },
}
ALLOWED_DECISIONS = {"approve", "edit", "reject", "pause", "send_back"}
ACTION_STATUSES = {
    "approve": "approved",
    "edit": "edited",
    "reject": "rejected",
    "pause": "paused",
    "send_back": "send_back",
}
BLOCKED_AUTHORITY = {
    "approval_executes_action": False,
    "sends_customer_message": False,
    "posts_publicly": False,
    "calls_chatwoot": False,
    "calls_meta": False,
    "creates_quote": False,
    "creates_invoice": False,
    "creates_order": False,
    "confirms_payment": False,
    "reserves_stock": False,
    "books_slaughter": False,
    "books_butcher": False,
    "writes_farm_lifecycle": False,
    "applies_migration": False,
}


def list_owner_approval_inbox(limit_per_status=12, database_url=None, connect_factory=None):
    items = []
    source_statuses = {}
    configured = True
    limit_per_status = _bounded_limit(limit_per_status)
    for status in INBOX_MISSION_STATUSES:
        result, status_code = list_owner_work_missions(
            status,
            limit=limit_per_status,
            database_url=database_url,
            connect_factory=connect_factory,
        )
        source_statuses[status] = status_code
        if status_code == 503 and result.get("configured") is False:
            configured = False
            continue
        if status_code >= 400:
            continue
        for mission in result.get("missions", []):
            items.extend(owner_approval_items_from_mission(mission))
    runtime_result, runtime_status = list_sam_live_stock_runtime_owner_review_items(
        limit=limit_per_status,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    source_statuses["sam_live_stock_conversation_review_events"] = runtime_status
    if runtime_status == 503 and runtime_result.get("configured") is False and not items:
        configured = False
    if runtime_status < 400:
        items.extend(runtime_result.get("items", []))
    meat_result, meat_status = list_sam_meat_learning_owner_review_items(
        limit=limit_per_status,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    source_statuses["meat_sales_conversation_learning_events"] = meat_status
    if meat_status == 503 and meat_result.get("configured") is False and not items:
        configured = False
    if meat_status < 400:
        items.extend(meat_result.get("items", []))
    items = sorted(items, key=_item_sort_key)
    pending_count = sum(1 for item in items if item.get("status") in {"pending", "send_back"})
    return {
        "success": True,
        "configured": configured,
        "status": "ok" if configured else "not_configured",
        "version": INBOX_VERSION,
        "items": items,
        "counts": _inbox_counts(items),
        "pending_count": pending_count,
        "allowed_decisions": sorted(ALLOWED_DECISIONS),
        "allowed_sources": sorted(ALLOWED_SOURCES),
        "authority": dict(BLOCKED_AUTHORITY),
        "source_statuses": source_statuses,
        "execution_boundary": (
            "Owner approval inbox records decisions only. Domain send/post/booking/payment/"
            "reservation/farm-write gates must execute separately after exact owner approval."
        ),
    }, 200


def list_sam_meat_learning_owner_review_items(limit=12, database_url=None, connect_factory=None):
    parsed_limit = _bounded_limit(limit)
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured", "items": []}, 503
    try:
        if connect_factory:
            connection_context = connect_factory(database_url)
        else:
            import psycopg
            connection_context = psycopg.connect(database_url, connect_timeout=5)
        with connection_context as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
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
                        created_at
                    from public.meat_sales_conversation_learning_events
                    where coalesce(customer_message_excerpt, '') <> ''
                       or coalesce(sam_reply_excerpt, '') <> ''
                       or coalesce(improvement_suggestion, '') <> ''
                       or jsonb_array_length(coalesce(missing_facts_json, '[]'::jsonb)) > 0
                       or jsonb_array_length(coalesce(sam_misses_json, '[]'::jsonb)) > 0
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sam_meat_learning_owner_review_items_failed",
            "error_type": exc.__class__.__name__,
            "items": [],
        }, 503
    items = [
        owner_approval_item_from_sam_meat_learning_event(dict(zip(columns, row)))
        for row in rows
    ]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "items": [item for item in items if item.get("approval_id")],
    }, 200


def owner_approval_item_from_sam_meat_learning_event(event):
    event = event if isinstance(event, dict) else {}
    reply = _clean(event.get("sam_reply_excerpt"), 2500)
    message = _clean(event.get("customer_message_excerpt"), 500)
    suggestion = _clean(event.get("improvement_suggestion"), 500)
    title_parts = ["SAM Meat conversation review"]
    lead_id = _clean(event.get("lead_id"), 80)
    if lead_id:
        title_parts.append(lead_id)
    item = normalize_owner_approval_item({
        "approval_id": event.get("learning_event_id"),
        "source_type": "sam_meat_controlled_reply",
        "source_agent": event.get("source_agent") or "SAM Meat",
        "title": " - ".join(title_parts),
        "status": "pending",
        "action_label": suggestion or "Review SAM Meat learning evidence",
        "exact_action": (
            "Review the saved SAM Meat conversation learning evidence. This inbox card is "
            "read-only; use the meat sales owner/customer send and money-path gates for any "
            "customer reply, quote, payment, reservation, fulfilment, or rule change."
        ),
        "exact_text": reply,
        "editable_text": reply,
        "target_label": lead_id or event.get("chatwoot_conversation_id"),
        "source_ref": event.get("chatwoot_conversation_id") or lead_id,
        "conversation_id": event.get("chatwoot_conversation_id"),
        "risk_flags": _sam_meat_learning_risk_flags(event, message),
        "forbidden_actions": [
            "Inbox review does not send the customer message.",
            "No quote, invoice, payment confirmation, reservation, stock, Chatwoot, prompt, rule, or farm lifecycle write from this card.",
        ],
        "created_at": _iso(event.get("created_at")),
        "updated_at": _iso(event.get("created_at")),
    }, {
        "mission_id": "",
        "status": "runtime_review",
        "title": "SAM Meat conversation learning",
    })
    item.update({
        "mission_id": "",
        "mission_title": "SAM Meat conversation learning",
        "mission_status": "runtime_review",
        "decision_supported": False,
        "runtime_source": "meat_sales_conversation_learning_events",
        "learning_event_id": _clean(event.get("learning_event_id"), 120),
        "lead_id": lead_id,
        "customer_message_excerpt": message,
        "conversion_signal": _clean(event.get("conversion_signal"), 80),
        "improvement_suggestion": suggestion,
    })
    return item


def list_sam_live_stock_runtime_owner_review_items(limit=12, database_url=None, connect_factory=None):
    parsed_limit = _bounded_limit(limit)
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "configured": False, "status": "not_configured", "items": []}, 503
    try:
        if connect_factory:
            connection_context = connect_factory(database_url)
        else:
            import psycopg
            connection_context = psycopg.connect(database_url, connect_timeout=5)
        with connection_context as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        review_event_id,
                        chatwoot_conversation_id,
                        chatwoot_message_id,
                        customer_name,
                        channel,
                        source_agent,
                        customer_message_excerpt,
                        sam_reply_excerpt,
                        score,
                        confidence_target,
                        safe_to_send,
                        owner_send_required,
                        no_reply_recommended,
                        escalation_required,
                        conversation_mode_recommendation,
                        recommended_action,
                        review_json,
                        facts_json,
                        decision_json,
                        created_at
                    from public.sam_live_stock_conversation_review_events
                    where owner_send_required = true
                       or safe_to_send = true
                       or coalesce(sam_reply_excerpt, '') <> ''
                       or coalesce(recommended_action, '') <> ''
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sam_live_stock_runtime_owner_review_items_failed",
            "error_type": exc.__class__.__name__,
            "items": [],
        }, 503
    items = [
        owner_approval_item_from_sam_live_stock_review_event(dict(zip(columns, row)))
        for row in rows
    ]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "items": [item for item in items if item.get("approval_id")],
    }, 200


def owner_approval_item_from_sam_live_stock_review_event(event):
    event = event if isinstance(event, dict) else {}
    review = _json_dict(event.get("review_json"))
    facts = _json_dict(event.get("facts_json"))
    decision = _json_dict(event.get("decision_json"))
    reply = _clean(
        event.get("sam_reply_excerpt")
        or decision.get("suggested_reply_text")
        or review.get("suggested_reply_text"),
        2500,
    )
    message = _clean(event.get("customer_message_excerpt"), 500)
    action = _clean(event.get("recommended_action") or review.get("recommended_action"), 160)
    title_parts = ["SAM Live Stock owner review"]
    customer = _clean(event.get("customer_name"), 80)
    if customer:
        title_parts.append(customer)
    item = normalize_owner_approval_item({
        "approval_id": event.get("review_event_id"),
        "source_type": "sam_live_stock_reply",
        "source_agent": event.get("source_agent") or "SAM Live Stock",
        "title": " - ".join(title_parts),
        "status": "pending",
        "action_label": action or "Review SAM Live Stock reply",
        "exact_action": (
            "Review the saved SAM Live Stock reply candidate. This inbox card is read-only; "
            "use the SAM owner review Telegram callback/send gate for any customer reply."
        ),
        "exact_text": reply,
        "editable_text": reply,
        "target_label": customer or event.get("chatwoot_conversation_id"),
        "source_ref": event.get("chatwoot_conversation_id"),
        "conversation_id": event.get("chatwoot_conversation_id"),
        "review_event_id": event.get("review_event_id"),
        "risk_flags": _sam_live_stock_review_risk_flags(event, facts, message),
        "forbidden_actions": [
            "Inbox approval does not send the customer message.",
            "No reservation, payment, order, stock, Chatwoot, Telegram, or farm lifecycle write from this card.",
        ],
        "created_at": _iso(event.get("created_at")),
        "updated_at": _iso(event.get("created_at")),
    }, {
        "mission_id": "",
        "status": "runtime_review",
        "title": "SAM Live Stock runtime review",
    })
    item.update({
        "mission_id": "",
        "mission_title": "SAM Live Stock runtime review",
        "mission_status": "runtime_review",
        "decision_supported": False,
        "runtime_source": "sam_live_stock_conversation_review_events",
        "review_event_id": _clean(event.get("review_event_id"), 120),
        "customer_message_excerpt": message,
        "score": event.get("score"),
        "confidence_target": event.get("confidence_target"),
        "safe_to_send": bool(event.get("safe_to_send")),
        "owner_send_required": bool(event.get("owner_send_required")),
    })
    return item


def owner_approval_items_from_mission(mission):
    mission = mission if isinstance(mission, dict) else {}
    metadata = mission.get("metadata") if isinstance(mission.get("metadata"), dict) else {}
    inbox = metadata.get("owner_approval_inbox") if isinstance(metadata.get("owner_approval_inbox"), dict) else {}
    raw_items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
    decisions = inbox.get("decisions") if isinstance(inbox.get("decisions"), list) else []
    latest_by_item = {}
    for decision in decisions:
        decision = decision if isinstance(decision, dict) else {}
        item_id = _clean(decision.get("approval_id"), 120)
        if item_id:
            latest_by_item[item_id] = decision
    items = []
    for raw_item in raw_items:
        item = normalize_owner_approval_item(raw_item, mission)
        if not item.get("approval_id"):
            continue
        latest = latest_by_item.get(item["approval_id"]) or {}
        if latest:
            item["latest_decision"] = latest
            item["status"] = _clean(latest.get("item_status"), 40) or item["status"]
            item["updated_at"] = latest.get("recorded_at") or item.get("updated_at", "")
        items.append(item)
    return items


def normalize_owner_approval_item(raw_item, mission=None):
    raw_item = raw_item if isinstance(raw_item, dict) else {}
    mission = mission if isinstance(mission, dict) else {}
    source_type = _normalize_source_type(raw_item.get("source_type") or raw_item.get("type"))
    source_defaults = ALLOWED_SOURCES.get(source_type, {})
    approval_id = _clean(
        raw_item.get("approval_id")
        or raw_item.get("item_id")
        or raw_item.get("id")
        or raw_item.get("publish_packet_id")
        or raw_item.get("review_event_id"),
        120,
    )
    exact_text = _clean(
        raw_item.get("exact_text")
        or raw_item.get("suggested_reply_text")
        or raw_item.get("reply_text")
        or raw_item.get("message")
        or raw_item.get("alert_text"),
        2500,
    )
    status = _clean(raw_item.get("status") or raw_item.get("approval_status") or "pending", 40)
    if status in {"owner_review_required", "ready_for_owner_review", "review_required"}:
        status = "pending"
    return {
        "approval_id": approval_id,
        "mission_id": _clean(mission.get("mission_id"), 120),
        "mission_title": _clean(mission.get("title") or mission.get("raw_text"), 180),
        "mission_status": _clean(mission.get("status"), 40),
        "source_type": source_type,
        "source_agent": _clean(raw_item.get("source_agent") or raw_item.get("agent") or source_defaults.get("agent"), 80),
        "lane": _clean(raw_item.get("lane") or source_defaults.get("lane"), 80),
        "title": _clean(raw_item.get("title") or raw_item.get("summary") or _default_title(source_type), 180),
        "status": status or "pending",
        "action_label": _clean(raw_item.get("action_label") or raw_item.get("recommended_action") or "Review exact action", 120),
        "exact_action": _clean(raw_item.get("exact_action") or raw_item.get("action") or raw_item.get("next_action"), 500),
        "exact_text": exact_text,
        "editable_text": _clean(raw_item.get("editable_text") or exact_text, 2500),
        "target_label": _clean(raw_item.get("target_label") or raw_item.get("customer_name") or raw_item.get("channel"), 160),
        "source_ref": _clean(raw_item.get("source_ref") or raw_item.get("source_reference") or raw_item.get("conversation_id"), 180),
        "next_gate": _clean(raw_item.get("next_gate") or source_defaults.get("gate"), 180),
        "risk_flags": _clean_list(raw_item.get("risk_flags") or raw_item.get("blockers")),
        "forbidden_actions": _clean_list(raw_item.get("forbidden_actions")),
        "created_at": _clean(raw_item.get("created_at"), 80),
        "updated_at": _clean(raw_item.get("updated_at"), 80),
        "authority": dict(BLOCKED_AUTHORITY),
    }


def record_owner_approval_decision(
    mission_id,
    approval_id,
    decision,
    comments="",
    edited_text="",
    database_url=None,
    connect_factory=None,
):
    mission_id = _clean(mission_id, 120)
    approval_id = _clean(approval_id, 120)
    decision = _clean(decision, 40)
    comments = _clean(comments, 2000)
    edited_text = _clean(edited_text, 2500)
    if not mission_id:
        return {"success": False, "status": "mission_id_required"}, 400
    if not approval_id:
        return {"success": False, "status": "approval_id_required"}, 400
    if decision not in ALLOWED_DECISIONS:
        return {"success": False, "status": "invalid_owner_approval_decision", "allowed_decisions": sorted(ALLOWED_DECISIONS)}, 400
    if decision == "edit" and not edited_text:
        return {"success": False, "status": "edited_text_required"}, 400

    loaded, load_status = get_mission(
        mission_id,
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if load_status >= 400:
        return loaded, load_status
    mission = loaded.get("mission") or {}
    metadata = dict(mission.get("metadata") or {})
    inbox = dict(metadata.get("owner_approval_inbox") or {})
    raw_items = inbox.get("items") if isinstance(inbox.get("items"), list) else []
    decisions = inbox.get("decisions") if isinstance(inbox.get("decisions"), list) else []
    updated_items = []
    matched_item = None
    now = datetime.now(timezone.utc).isoformat()
    for raw_item in raw_items:
        item = dict(raw_item if isinstance(raw_item, dict) else {})
        normalized = normalize_owner_approval_item(item, mission)
        if normalized.get("approval_id") == approval_id:
            matched_item = normalized
            item["status"] = ACTION_STATUSES[decision]
            item["updated_at"] = now
            if decision == "edit":
                item["edited_text"] = edited_text
        updated_items.append(item)
    if not matched_item:
        return {"success": False, "status": "approval_item_not_found", "mission_id": mission_id, "approval_id": approval_id}, 404

    decision_record = {
        "approval_id": approval_id,
        "decision": decision,
        "item_status": ACTION_STATUSES[decision],
        "comments": comments,
        "edited_text": edited_text if decision == "edit" else "",
        "source_type": matched_item.get("source_type", ""),
        "source_agent": matched_item.get("source_agent", ""),
        "recorded_at": now,
        **BLOCKED_AUTHORITY,
    }
    inbox.update({
        "version": INBOX_VERSION,
        "items": updated_items,
        "decisions": (list(decisions) + [decision_record])[-100:],
        "updated_at": now,
        "execution_boundary": (
            "Decision recorded only; domain-specific gates must handle any later action."
        ),
    })
    result, status_code = update_mission_vault(
        mission_id,
        {"owner_approval_inbox": inbox},
        notes=f"Owner approval inbox decision recorded: {approval_id} -> {decision}.",
        database_url=database_url,
        connect_factory=connect_factory,
    )
    if status_code >= 400:
        return result, status_code
    return {
        "success": True,
        "status": "owner_approval_decision_recorded",
        "mission_id": mission_id,
        "approval_id": approval_id,
        "decision": decision,
        "item_status": ACTION_STATUSES[decision],
        "decision_record": decision_record,
        "authority": dict(BLOCKED_AUTHORITY),
    }, 200


def _normalize_source_type(value):
    text = _clean(value, 80).lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "beacon": "beacon_post_packet",
        "beacon_publish_packet": "beacon_post_packet",
        "sam_live_stock": "sam_live_stock_reply",
        "sam_live_stock_owner_review": "sam_live_stock_reply",
        "sam_meat": "sam_meat_controlled_reply",
        "sam_meat_reply": "sam_meat_controlled_reply",
        "butcher": "butcher_recommendation",
        "meat_butcher": "butcher_recommendation",
        "herdmaster": "herdmaster_alert",
        "pig_allocation_alert": "herdmaster_alert",
    }
    return aliases.get(text, text if text in ALLOWED_SOURCES else "agent_suggestion")


def _default_title(source_type):
    if source_type == "beacon_post_packet":
        return "Beacon post packet"
    if source_type == "sam_live_stock_reply":
        return "SAM Live Stock reply suggestion"
    if source_type == "sam_meat_controlled_reply":
        return "SAM Meat controlled reply"
    if source_type == "butcher_recommendation":
        return "Butcher recommendation"
    if source_type == "herdmaster_alert":
        return "Herdmaster alert"
    return "Agent suggestion"


def _inbox_counts(items):
    counts = {status: 0 for status in ["pending", "approved", "edited", "rejected", "paused", "send_back"]}
    by_source = {}
    for item in items:
        status = item.get("status") or "pending"
        counts[status] = counts.get(status, 0) + 1
        source = item.get("source_type") or "agent_suggestion"
        by_source[source] = by_source.get(source, 0) + 1
    counts["total"] = len(items)
    counts["by_source"] = by_source
    return counts


def _sam_live_stock_review_risk_flags(event, facts, message):
    flags = []
    if event.get("owner_send_required"):
        flags.append("owner_send_required")
    if event.get("safe_to_send"):
        flags.append("safe_to_send_claim_requires_owner_gate")
    if event.get("escalation_required"):
        flags.append("escalation_required")
    if event.get("no_reply_recommended"):
        flags.append("no_reply_recommended")
    if facts.get("category"):
        flags.append(f"category:{_clean(facts.get('category'), 80)}")
    if message:
        flags.append("customer_message_captured")
    return flags


def _sam_meat_learning_risk_flags(event, message):
    flags = []
    if message:
        flags.append("customer_message_captured")
    for key, prefix in (
        ("missing_facts_json", "missing"),
        ("objections_json", "objection"),
        ("confusion_signals_json", "confusion"),
        ("sam_misses_json", "sam_miss"),
    ):
        for value in _json_list(event.get(key))[:4]:
            flags.append(f"{prefix}:{_clean(value, 80)}")
    signal = _clean(event.get("conversion_signal"), 80)
    if signal:
        flags.append(f"conversion:{signal}")
    return flags


def _json_dict(value):
    if isinstance(value, dict):
        return value
    return {}


def _json_list(value):
    if isinstance(value, list):
        return value
    return []


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else _clean(value, 80)


def _database_url(database_url):
    import os
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _bounded_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = 12
    return max(1, min(parsed, 50))


def _item_sort_key(item):
    status_rank = {
        "pending": 0,
        "send_back": 1,
        "paused": 2,
        "edited": 3,
        "approved": 4,
        "rejected": 5,
    }
    return (
        status_rank.get(item.get("status"), 9),
        item.get("updated_at") or item.get("created_at") or "",
        item.get("approval_id") or "",
    )


def _clean(value, limit=500):
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit]


def _clean_list(value, limit=12):
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value[:limit]:
        text = _clean(item, 180)
        if text:
            cleaned.append(text)
    return cleaned
