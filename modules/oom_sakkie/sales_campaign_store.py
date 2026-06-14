import hashlib
import json
import os
from datetime import datetime, timezone

from services.database_service import DATABASE_URL_ENV


SALES_CAMPAIGN_EVENT_TYPES = {
    "review_note",
    "approved_for_customer_outreach",
    "rejected",
    "deferred",
}


def record_sales_campaign(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    title = _clean_text(payload.get("campaign_title") or payload.get("title") or "Ledger sales campaign", 160)
    if not title:
        return {"success": False, "status": "campaign_title_required", **_false_flags()}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", configured=True), 500

    params = _sales_campaign_params(payload)
    created_count = 0
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_sales_campaigns (
                        campaign_id,
                        status,
                        mode,
                        source_tool,
                        campaign_title,
                        opportunity_json,
                        draft_json,
                        owner_questions_json,
                        risks_json,
                        next_action,
                        created_by,
                        sends_customer_message,
                        calls_chatwoot,
                        calls_n8n,
                        creates_quote,
                        creates_order,
                        changes_stock,
                        dispatch_enabled,
                        changes_runtime_now,
                        changes_prompt_now,
                        physical_controls_enabled,
                        customer_public_output_enabled,
                        writes_farm_data,
                        created_at
                    )
                    values (
                        %(campaign_id)s,
                        %(status)s,
                        %(mode)s,
                        %(source_tool)s,
                        %(campaign_title)s,
                        %(opportunity_json)s::jsonb,
                        %(draft_json)s::jsonb,
                        %(owner_questions_json)s::jsonb,
                        %(risks_json)s::jsonb,
                        %(next_action)s,
                        %(created_by)s,
                        %(sends_customer_message)s,
                        %(calls_chatwoot)s,
                        %(calls_n8n)s,
                        %(creates_quote)s,
                        %(creates_order)s,
                        %(changes_stock)s,
                        %(dispatch_enabled)s,
                        %(changes_runtime_now)s,
                        %(changes_prompt_now)s,
                        %(physical_controls_enabled)s,
                        %(customer_public_output_enabled)s,
                        %(writes_farm_data)s,
                        now()
                    )
                    on conflict (campaign_id) do nothing
                    returning campaign_id
                    """,
                    params,
                )
                created_count = 1 if cursor.fetchone() else 0
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_campaign_write_failed",
            "error_type": exc.__class__.__name__,
            "created_count": 0,
            "sales_campaigns": [],
            **_false_flags(),
        }, 503

    listed, list_status = list_sales_campaigns(limit=25, database_url=database_url)
    if list_status != 200:
        return listed, list_status
    campaigns = [item for item in listed.get("sales_campaigns", []) if item.get("campaign_id") == params["campaign_id"]]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "owner_review_sales_campaign_queue",
        "created_count": created_count,
        "campaign_id": params["campaign_id"],
        "sales_campaigns": campaigns,
        "next_gate": "owner_approval_before_any_customer_outreach_or_order_write",
        "records_sales_campaign": True,
        **_false_flags(),
    }, 201


def list_sales_campaigns(limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
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
                    select c.campaign_id, c.status, c.mode, c.source_tool,
                           c.campaign_title, c.opportunity_json, c.draft_json,
                           c.owner_questions_json, c.risks_json, c.next_action,
                           c.created_by,
                           c.sends_customer_message, c.calls_chatwoot, c.calls_n8n,
                           c.creates_quote, c.creates_order, c.changes_stock,
                           c.dispatch_enabled, c.changes_runtime_now, c.changes_prompt_now,
                           c.physical_controls_enabled, c.customer_public_output_enabled,
                           c.writes_farm_data, c.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_sales_campaigns c
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_sales_campaign_events e
                        where e.campaign_id = c.campaign_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    order by c.created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_campaign_read_failed",
            "error_type": exc.__class__.__name__,
            "sales_campaigns": [],
            **_false_flags(),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "owner_review_sales_campaign_queue",
        "sales_campaigns": [_sales_campaign_row(row) for row in rows],
        **_false_flags(),
    }, 200


def list_sales_outreach_drafts(limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "mode": "owner_review_customer_outreach_draft_queue",
            "outreach_drafts": [],
            **_false_flags(),
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "mode": "owner_review_customer_outreach_draft_queue",
            "outreach_drafts": [],
            **_false_flags(),
        }, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select draft_id, campaign_id, status, mode, audience_label,
                           draft_text, owner_checks_json, source_campaign_snapshot_json,
                           created_by,
                           sends_customer_message, calls_chatwoot, calls_n8n,
                           creates_quote, creates_order, changes_stock,
                           dispatch_enabled, changes_runtime_now, changes_prompt_now,
                           physical_controls_enabled, customer_public_output_enabled,
                           writes_farm_data, created_at
                    from public.oom_sakkie_sales_outreach_drafts
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_outreach_draft_read_failed",
            "error_type": exc.__class__.__name__,
            "mode": "owner_review_customer_outreach_draft_queue",
            "outreach_drafts": [],
            **_false_flags(),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "owner_review_customer_outreach_draft_queue",
        "outreach_drafts": [_sales_outreach_draft_row(row) for row in rows],
        **_false_flags(),
    }, 200


def record_sales_outreach_draft_from_campaign(campaign_id, payload=None, database_url=None):
    campaign_id = _clean_text(campaign_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    if not campaign_id:
        return {"success": False, "status": "campaign_id_required", "outreach_drafts": [], **_false_flags()}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "outreach_drafts": [],
            **_false_flags(),
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "outreach_drafts": [],
            **_false_flags(),
        }, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                campaign = _fetch_campaign_row(cursor, campaign_id)
                if not campaign:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "campaign_not_found",
                        "outreach_drafts": [],
                        **_false_flags(),
                    }, 404
                campaign_record = _sales_campaign_row(campaign)
                latest_event = campaign_record.get("latest_event") or {}
                if latest_event.get("event_type") != "approved_for_customer_outreach":
                    return {
                        "success": False,
                        "configured": True,
                        "status": "campaign_not_approved_for_customer_outreach",
                        "campaign_id": campaign_id,
                        "latest_event": latest_event,
                        "outreach_drafts": [],
                        **_false_flags(),
                    }, 409
                params = _sales_outreach_draft_params(campaign_record, payload)
                cursor.execute(
                    """
                    insert into public.oom_sakkie_sales_outreach_drafts (
                        draft_id,
                        campaign_id,
                        status,
                        mode,
                        audience_label,
                        draft_text,
                        owner_checks_json,
                        source_campaign_snapshot_json,
                        created_by,
                        sends_customer_message,
                        calls_chatwoot,
                        calls_n8n,
                        creates_quote,
                        creates_order,
                        changes_stock,
                        dispatch_enabled,
                        changes_runtime_now,
                        changes_prompt_now,
                        physical_controls_enabled,
                        customer_public_output_enabled,
                        writes_farm_data,
                        created_at
                    )
                    values (
                        %(draft_id)s,
                        %(campaign_id)s,
                        %(status)s,
                        %(mode)s,
                        %(audience_label)s,
                        %(draft_text)s,
                        %(owner_checks_json)s::jsonb,
                        %(source_campaign_snapshot_json)s::jsonb,
                        %(created_by)s,
                        %(sends_customer_message)s,
                        %(calls_chatwoot)s,
                        %(calls_n8n)s,
                        %(creates_quote)s,
                        %(creates_order)s,
                        %(changes_stock)s,
                        %(dispatch_enabled)s,
                        %(changes_runtime_now)s,
                        %(changes_prompt_now)s,
                        %(physical_controls_enabled)s,
                        %(customer_public_output_enabled)s,
                        %(writes_farm_data)s,
                        now()
                    )
                    on conflict (campaign_id, audience_label) do nothing
                    returning draft_id
                    """,
                    params,
                )
                created_count = 1 if cursor.fetchone() else 0
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_outreach_draft_write_failed",
            "error_type": exc.__class__.__name__,
            "outreach_drafts": [],
            **_false_flags(),
        }, 503

    listed, list_status = list_sales_outreach_drafts(limit=50, database_url=database_url)
    if list_status != 200:
        return listed, list_status
    drafts = [item for item in listed.get("outreach_drafts", []) if item.get("draft_id") == params["draft_id"]]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "owner_review_customer_outreach_draft_queue",
        "created_count": created_count,
        "draft_id": params["draft_id"],
        "campaign_id": campaign_id,
        "outreach_drafts": drafts,
        "next_gate": "owner_review_before_any_customer_send_or_order_write",
        "records_customer_outreach_draft": True,
        **_false_flags(),
    }, 201


def record_sales_campaign_event(campaign_id, payload, database_url=None):
    campaign_id = _clean_text(campaign_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 80)
    if not campaign_id:
        return {"success": False, "status": "campaign_id_required", **_false_flags()}, 400
    if event_type not in SALES_CAMPAIGN_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(SALES_CAMPAIGN_EVENT_TYPES),
            **_false_flags(),
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", **_false_flags()}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", **_false_flags()}, 500

    params = {
        "event_id": _event_id(campaign_id, event_type),
        "campaign_id": campaign_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
        **_false_flags(),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_sales_campaign_events (
                        event_id,
                        campaign_id,
                        event_type,
                        notes,
                        recorded_by,
                        sends_customer_message,
                        calls_chatwoot,
                        calls_n8n,
                        creates_quote,
                        creates_order,
                        changes_stock,
                        dispatch_enabled,
                        changes_runtime_now,
                        changes_prompt_now,
                        physical_controls_enabled,
                        customer_public_output_enabled,
                        writes_farm_data,
                        created_at
                    )
                    values (
                        %(event_id)s,
                        %(campaign_id)s,
                        %(event_type)s,
                        %(notes)s,
                        %(recorded_by)s,
                        %(sends_customer_message)s,
                        %(calls_chatwoot)s,
                        %(calls_n8n)s,
                        %(creates_quote)s,
                        %(creates_order)s,
                        %(changes_stock)s,
                        %(dispatch_enabled)s,
                        %(changes_runtime_now)s,
                        %(changes_prompt_now)s,
                        %(physical_controls_enabled)s,
                        %(customer_public_output_enabled)s,
                        %(writes_farm_data)s,
                        now()
                    )
                    """,
                    params,
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_campaign_event_write_failed",
            "error_type": exc.__class__.__name__,
            **_false_flags(),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "campaign_id": campaign_id,
        "event_type": event_type,
        "next_gate": "future_review_before_any_approved_campaign_is_sent_or_written_to_orders",
        **_false_flags(),
    }, 201


def approve_first_waiting_sales_campaign(payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    listed, status_code = list_sales_campaigns(limit=25, database_url=database_url)
    if status_code != 200:
        return listed, status_code
    waiting = [
        item for item in listed.get("sales_campaigns", [])
        if not (item.get("latest_event") or {}).get("event_type")
    ]
    if not waiting:
        return {
            "success": False,
            "status": "no_waiting_sales_campaign",
            "campaign_id": "",
            "event": {},
            "draft": {},
            **_false_flags(),
        }, 404
    campaign = waiting[0]
    event, event_status = record_sales_campaign_event(
        campaign["campaign_id"],
        {
            "event_type": "approved_for_customer_outreach",
            "notes": payload.get("notes", "Owner approved campaign for internal outreach draft preparation."),
            "recorded_by": payload.get("recorded_by", "owner"),
        },
        database_url=database_url,
    )
    if event_status >= 400:
        return event, event_status
    draft, draft_status = record_sales_outreach_draft_from_campaign(
        campaign["campaign_id"],
        {
            "audience_label": payload.get("audience_label") or "known meat buyers",
            "created_by": payload.get("recorded_by", "owner"),
        },
        database_url=database_url,
    )
    return {
        "success": draft_status < 400,
        "configured": True,
        "status": "sales_campaign_approved_and_draft_queued" if draft_status < 400 else "sales_campaign_approved_draft_queue_failed",
        "campaign_id": campaign["campaign_id"],
        "campaign_title": campaign.get("campaign_title", ""),
        "event": event,
        "draft": draft,
        "next_gate": "owner_review_before_any_customer_send_or_order_write",
        **_false_flags(),
    }, 200 if draft_status < 400 else draft_status


def _sales_campaign_params(payload):
    opportunity = payload.get("opportunity") if isinstance(payload.get("opportunity"), dict) else {}
    draft = payload.get("draft") if isinstance(payload.get("draft"), dict) else {}
    owner_questions = payload.get("owner_questions") if isinstance(payload.get("owner_questions"), list) else []
    risks = payload.get("risks") if isinstance(payload.get("risks"), list) else []
    title = _clean_text(payload.get("campaign_title") or payload.get("title") or "Ledger sales campaign", 160)
    seed = json.dumps({
        "title": title,
        "opportunity": opportunity,
        "draft": draft,
    }, sort_keys=True, default=str)
    return {
        "campaign_id": _campaign_id(seed),
        "status": "pending_owner_review",
        "mode": "owner_review_sales_campaign_only",
        "source_tool": _clean_text(payload.get("source_tool") or "ledger_sales_agent", 80),
        "campaign_title": title,
        "opportunity_json": _json(opportunity),
        "draft_json": _json(draft),
        "owner_questions_json": _json([_clean_text(item, 220) for item in owner_questions[:8]]),
        "risks_json": _json([_clean_text(item, 220) for item in risks[:8]]),
        "next_action": _clean_text(payload.get("next_action"), 500),
        "created_by": _clean_text(payload.get("created_by") or "ledger", 80),
        **_false_flags(),
    }


def _sales_campaign_row(row):
    latest_event = None
    if row[24]:
        latest_event = {
            "event_type": row[24],
            "notes": row[25] or "",
            "recorded_by": row[26] or "",
            "created_at": _iso(row[27]),
        }
    return {
        "campaign_id": row[0],
        "status": row[1],
        "mode": row[2],
        "source_tool": row[3],
        "campaign_title": row[4],
        "opportunity": row[5] or {},
        "draft": row[6] or {},
        "owner_questions": row[7] or [],
        "risks": row[8] or [],
        "next_action": row[9] or "",
        "created_by": row[10] or "",
        "sends_customer_message": bool(row[11]),
        "calls_chatwoot": bool(row[12]),
        "calls_n8n": bool(row[13]),
        "creates_quote": bool(row[14]),
        "creates_order": bool(row[15]),
        "changes_stock": bool(row[16]),
        "dispatch_enabled": bool(row[17]),
        "changes_runtime_now": bool(row[18]),
        "changes_prompt_now": bool(row[19]),
        "physical_controls_enabled": bool(row[20]),
        "customer_public_output_enabled": bool(row[21]),
        "writes_farm_data": bool(row[22]),
        "created_at": _iso(row[23]),
        "latest_event": latest_event,
    }


def _sales_outreach_draft_row(row):
    return {
        "draft_id": row[0],
        "campaign_id": row[1],
        "status": row[2],
        "mode": row[3],
        "audience_label": row[4] or "",
        "draft_text": row[5] or "",
        "owner_checks": row[6] or [],
        "source_campaign_snapshot": row[7] or {},
        "created_by": row[8] or "",
        "sends_customer_message": bool(row[9]),
        "calls_chatwoot": bool(row[10]),
        "calls_n8n": bool(row[11]),
        "creates_quote": bool(row[12]),
        "creates_order": bool(row[13]),
        "changes_stock": bool(row[14]),
        "dispatch_enabled": bool(row[15]),
        "changes_runtime_now": bool(row[16]),
        "changes_prompt_now": bool(row[17]),
        "physical_controls_enabled": bool(row[18]),
        "customer_public_output_enabled": bool(row[19]),
        "writes_farm_data": bool(row[20]),
        "created_at": _iso(row[21]),
    }


def _fetch_campaign_row(cursor, campaign_id):
    cursor.execute(
        """
        select c.campaign_id, c.status, c.mode, c.source_tool,
               c.campaign_title, c.opportunity_json, c.draft_json,
               c.owner_questions_json, c.risks_json, c.next_action,
               c.created_by,
               c.sends_customer_message, c.calls_chatwoot, c.calls_n8n,
               c.creates_quote, c.creates_order, c.changes_stock,
               c.dispatch_enabled, c.changes_runtime_now, c.changes_prompt_now,
               c.physical_controls_enabled, c.customer_public_output_enabled,
               c.writes_farm_data, c.created_at,
               ev.event_type, ev.notes, ev.recorded_by, ev.created_at
        from public.oom_sakkie_sales_campaigns c
        left join lateral (
            select event_type, notes, recorded_by, created_at
            from public.oom_sakkie_sales_campaign_events e
            where e.campaign_id = c.campaign_id
            order by created_at desc
            limit 1
        ) ev on true
        where c.campaign_id = %(campaign_id)s
        """,
        {"campaign_id": campaign_id},
    )
    return cursor.fetchone()


def _sales_outreach_draft_params(campaign, payload):
    draft = campaign.get("draft") if isinstance(campaign.get("draft"), dict) else {}
    opportunity = campaign.get("opportunity") if isinstance(campaign.get("opportunity"), dict) else {}
    audience_label = _clean_text(payload.get("audience_label") or opportunity.get("target") or "known meat buyers", 120)
    draft_text = _clean_text(payload.get("draft_text") or draft.get("message"), 1600)
    if not draft_text:
        draft_text = "Hi [Name], I am checking interest before we process the next small batch. I can confirm cuts, timing, and price before anything is booked."
    owner_checks = [
        "Confirm exact buyer name or group before any send.",
        "Confirm price, cuts, timing, collection/delivery, availability, and stock health before any send.",
        "Owner approval is still required before Chatwoot, WhatsApp, Telegram, or customer contact.",
    ]
    snapshot = {
        "campaign_id": campaign.get("campaign_id", ""),
        "campaign_title": campaign.get("campaign_title", ""),
        "opportunity": opportunity,
        "draft": draft,
        "owner_questions": campaign.get("owner_questions") or [],
        "risks": campaign.get("risks") or [],
        "latest_event": campaign.get("latest_event") or {},
        "proposal_text_is_untrusted": True,
    }
    return {
        "draft_id": _draft_id(campaign.get("campaign_id", ""), audience_label),
        "campaign_id": campaign.get("campaign_id", ""),
        "status": "pending_owner_review",
        "mode": "owner_review_customer_outreach_draft_only",
        "audience_label": audience_label,
        "draft_text": draft_text,
        "owner_checks_json": _json(owner_checks),
        "source_campaign_snapshot_json": _json(snapshot),
        "created_by": _clean_text(payload.get("created_by") or "ledger", 80),
        **_false_flags(),
    }


def _false_flags():
    return {
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
        "writes_farm_data": False,
    }


def _unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "owner_review_sales_campaign_queue",
        "sales_campaigns": [],
        **_false_flags(),
    }


def _campaign_id(seed):
    digest = hashlib.sha256(str(seed or "").encode("utf-8")).hexdigest()[:16].upper()
    return f"OSK-SALES-CAMPAIGN-{digest}"


def _event_id(campaign_id, event_type):
    digest = hashlib.sha256(
        f"{campaign_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}".encode("utf-8")
    ).hexdigest()[:16].upper()
    return f"OSK-SALES-CAMPAIGN-EVENT-{digest}"


def _draft_id(campaign_id, audience_label):
    digest = hashlib.sha256(f"{campaign_id}|{audience_label}".encode("utf-8")).hexdigest()[:16].upper()
    return f"OSK-SALES-DRAFT-{digest}"


def _json(value):
    return json.dumps(value if value is not None else {}, default=str, ensure_ascii=True, sort_keys=True)


def _clean_text(value, limit):
    text = " ".join(str(value or "").split())
    return text[:limit]


def _bounded_limit(limit):
    try:
        return max(1, min(100, int(limit)))
    except (TypeError, ValueError):
        return 20


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")
