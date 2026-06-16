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

SALES_LEAD_EVENT_TYPES = {
    "review_note",
    "status_observed",
    "owner_followup_needed",
    "owner_money_path_approved",
    "deposit_followup_needed",
    "linked_order_observed",
    "closed",
}

SALES_LEAD_STATUSES = {
    "new",
    "interested",
    "asked_price",
    "needs_callback",
    "deposit_pending",
    "not_interested",
    "order_ready_for_approval",
    "closed",
}

SALES_CAMPAIGN_SOURCES = {
    "ready_meat_preorder",
    "social_post",
    "direct_known_buyer",
    "inbound_chatwoot",
    "whatsapp_status",
    "manual_owner_note",
    "other",
}

WHATSAPP_WINDOW_STATES = {
    "unknown",
    "open",
    "closed",
    "template_required",
    "manual_owner_only",
}

MEAT_INTAKE_PRODUCT_TYPES = {
    "half_carcass",
    "full_carcass",
    "custom_cut",
    "assisted_slaughter",
    "unknown",
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


def list_sales_send_design_requests(limit=20, database_url=None):
    parsed_limit = _bounded_limit(limit)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _send_design_unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _send_design_unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select send_design_id, draft_id, status, mode, target_transport,
                           design_summary, required_owner_checks_json,
                           source_draft_snapshot_json, created_by,
                           sends_customer_message, calls_chatwoot, calls_n8n,
                           creates_quote, creates_order, changes_stock,
                           dispatch_enabled, changes_runtime_now, changes_prompt_now,
                           physical_controls_enabled, customer_public_output_enabled,
                           writes_farm_data, created_at
                    from public.oom_sakkie_sales_send_design_requests
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
            "status": "sales_send_design_read_failed",
            "error_type": exc.__class__.__name__,
            "mode": "customer_send_design_request_queue",
            "send_design_requests": [],
            **_false_flags(),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "customer_send_design_request_queue",
        "send_design_requests": [_sales_send_design_row(row) for row in rows],
        **_false_flags(),
    }, 200


def record_sales_lead(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _sales_lead_params(payload)
    if not params["lead_label"]:
        return {"success": False, "status": "lead_label_required", "sales_leads": [], **_false_flags()}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _sales_leads_unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _sales_leads_unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_sales_leads (
                        lead_id,
                        campaign_id,
                        draft_id,
                        send_design_id,
                        status,
                        mode,
                        campaign_source,
                        lead_label,
                        contact_label,
                        channel,
                        chatwoot_conversation_id,
                        whatsapp_window_state,
                        last_inbound_at,
                        opt_in_state,
                        interest_json,
                        next_owner_action,
                        linked_order_id,
                        linked_preorder_id,
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
                        %(lead_id)s,
                        %(campaign_id)s,
                        %(draft_id)s,
                        %(send_design_id)s,
                        %(status)s,
                        %(mode)s,
                        %(campaign_source)s,
                        %(lead_label)s,
                        %(contact_label)s,
                        %(channel)s,
                        %(chatwoot_conversation_id)s,
                        %(whatsapp_window_state)s,
                        %(last_inbound_at)s,
                        %(opt_in_state)s,
                        %(interest_json)s::jsonb,
                        %(next_owner_action)s,
                        %(linked_order_id)s,
                        %(linked_preorder_id)s,
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
                    on conflict (lead_id) do nothing
                    returning lead_id
                    """,
                    params,
                )
                created_count = 1 if cursor.fetchone() else 0
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_lead_write_failed",
            "error_type": exc.__class__.__name__,
            "sales_leads": [],
            **_false_flags(),
        }, 503

    listed, list_status = list_sales_leads(limit=50, database_url=database_url)
    if list_status != 200:
        return listed, list_status
    leads = [item for item in listed.get("sales_leads", []) if item.get("lead_id") == params["lead_id"]]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "sales_lead_tracking_queue",
        "created_count": created_count,
        "lead_id": params["lead_id"],
        "sales_leads": leads,
        "next_gate": "owner_or_sam_review_before_any_customer_send_quote_order_or_stock_write",
        "records_sales_lead": True,
        **_false_flags(),
    }, 201


def record_sam_meat_intake_lead(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_payload, contract = build_sam_meat_intake_lead_payload(payload)
    if contract["missing_core_fields"]:
        return {
            "success": False,
            "configured": bool((database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()),
            "status": "sam_meat_intake_missing_core_fields",
            "mode": "sam_meat_intake_tracking_only",
            "contract": contract,
            "sales_leads": [],
            **_false_flags(),
        }, 400

    result, status_code = record_sales_lead(lead_payload, database_url=database_url)
    event_result = {}
    event_status_code = None
    if status_code == 201 and isinstance(result, dict) and result.get("success"):
        event_result, event_status_code = record_sales_lead_event(
            result.get("lead_id", ""),
            _sam_meat_intake_event_payload(lead_payload, contract),
            database_url=database_url,
        )
    if isinstance(result, dict):
        result = {
            **result,
            "mode": "sam_meat_intake_tracking_only",
            "contract": contract,
            "fact_event": event_result if isinstance(event_result, dict) else {},
            "fact_event_status_code": event_status_code,
            "next_gate": "owner_review_before_preorder_deposit_order_stock_or_customer_send",
            **_false_flags(),
        }
    return result, status_code


def build_sam_meat_intake_lead_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    customer_name = _clean_text(payload.get("customer_name") or payload.get("contact_label"), 160)
    product_type = _clean_text(payload.get("product_type") or "unknown", 80)
    if product_type not in MEAT_INTAKE_PRODUCT_TYPES:
        product_type = "unknown"
    cut_set = _clean_text(payload.get("cut_set"), 80)
    location = _clean_text(payload.get("location") or payload.get("delivery_area"), 160)
    timing = _clean_text(payload.get("timing") or payload.get("available_week"), 160)
    delivery_or_collection = _clean_text(payload.get("delivery_or_collection"), 160)
    price_per_kg = _clean_text(payload.get("price_per_kg"), 80)
    deposit_rule = _clean_text(payload.get("deposit_rule") or payload.get("deposit_amount"), 160)
    payment_method = _clean_text(payload.get("payment_method"), 80)
    notes = _clean_text(payload.get("notes") or payload.get("customer_message"), 700)
    conversation_id = _clean_text(payload.get("conversation_id") or payload.get("chatwoot_conversation_id"), 100)
    contact_id = _clean_text(payload.get("contact_id"), 100)
    whatsapp_state = _clean_text(payload.get("whatsapp_window_state") or "unknown", 80)
    if whatsapp_state not in WHATSAPP_WINDOW_STATES:
        whatsapp_state = "unknown"
    status = _status_or_default(payload.get("status"), default="interested")

    missing_core = [
        key for key, value in {
            "customer_name": customer_name,
            "product_type": product_type if product_type != "unknown" else "",
            "location": location,
        }.items()
        if not value
    ]
    missing_before_money_path = [
        key for key, value in {
            "cut_set": cut_set,
            "timing": timing,
            "delivery_or_collection": delivery_or_collection,
            "price_per_kg": price_per_kg,
            "deposit_rule": deposit_rule,
            "payment_method": payment_method,
            "owner_final_approval": "",
        }.items()
        if not value
    ]
    product_label = product_type.replace("_", " ").title() if product_type != "unknown" else "Meat preorder"
    lead_label = _clean_text(
        payload.get("lead_label") or f"{customer_name or 'Customer'} - {product_label} interest",
        160,
    )
    next_owner_action = _clean_text(payload.get("next_owner_action"), 700)
    if not next_owner_action:
        next_owner_action = (
            "Owner to confirm " + ", ".join(missing_before_money_path[:4])
            if missing_before_money_path else
            "Owner to review meat preorder intake before any deposit/order/customer-send step."
        )
    interest = {
        "product": product_label,
        "product_type": product_type,
        "cut_set": cut_set,
        "location": location,
        "timing": timing,
        "delivery_or_collection": delivery_or_collection,
        "price_per_kg": price_per_kg,
        "deposit_rule": deposit_rule,
        "payment_method": payment_method,
        "notes": notes,
        "conversation_id": conversation_id,
        "contact_id": contact_id,
        "sam_intake_lane": "meat_preorder",
    }
    contract = {
        "lane": "meat_preorder",
        "customer_name": customer_name,
        "conversation_id": conversation_id,
        "contact_id": contact_id,
        "product_type": product_type,
        "missing_core_fields": missing_core,
        "missing_before_money_path": missing_before_money_path,
        "next_owner_action": next_owner_action,
        "sam_next_question": _sam_meat_next_question(missing_core, missing_before_money_path),
        "authority": {
            "records_tracking_lead": True,
            **_false_flags(),
        },
    }
    lead_payload = {
        "lead_label": lead_label,
        "contact_label": customer_name,
        "campaign_source": "inbound_chatwoot",
        "status": status,
        "channel": _clean_text(payload.get("channel") or "chatwoot_whatsapp", 80),
        "chatwoot_conversation_id": conversation_id,
        "whatsapp_window_state": whatsapp_state,
        "last_inbound_at": _clean_text(payload.get("last_inbound_at"), 80),
        "opt_in_state": _clean_text(payload.get("opt_in_state") or "unknown", 80),
        "interest": interest,
        "next_owner_action": next_owner_action,
        "created_by": "sam_meat_intake",
    }
    return lead_payload, contract


def list_sales_leads(limit=20, status_filter=None, database_url=None):
    parsed_limit = _bounded_limit(limit)
    status_filter = _sales_lead_status_filter(status_filter)
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _sales_leads_unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _sales_leads_unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select l.lead_id, l.campaign_id, l.draft_id, l.send_design_id,
                           l.status, l.mode, l.campaign_source, l.lead_label,
                           l.contact_label, l.channel, l.chatwoot_conversation_id,
                           l.whatsapp_window_state, l.last_inbound_at, l.opt_in_state,
                           l.interest_json, l.next_owner_action, l.linked_order_id,
                           l.linked_preorder_id, l.created_by,
                           l.sends_customer_message, l.calls_chatwoot, l.calls_n8n,
                           l.creates_quote, l.creates_order, l.changes_stock,
                           l.dispatch_enabled, l.changes_runtime_now, l.changes_prompt_now,
                           l.physical_controls_enabled, l.customer_public_output_enabled,
                           l.writes_farm_data, l.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_sales_leads l
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_sales_lead_events e
                        where e.lead_id = l.lead_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    where (
                        %(status_filter)s = ''
                        or (%(status_filter)s = 'launch_test' and l.status in ('new', 'interested', 'asked_price', 'needs_callback', 'deposit_pending', 'order_ready_for_approval'))
                        or l.status = %(status_filter)s
                    )
                    order by l.created_at desc
                    limit %(limit)s
                    """,
                    {"limit": parsed_limit, "status_filter": status_filter},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_lead_read_failed",
            "error_type": exc.__class__.__name__,
            "mode": "sales_lead_tracking_queue",
            "sales_leads": [],
            **_false_flags(),
        }, 503

    leads = [_sales_lead_row(row) for row in rows]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "sales_lead_tracking_queue",
        "sales_leads": leads,
        "counts": _sales_lead_counts(leads),
        "filter": status_filter or "all",
        **_false_flags(),
    }, 200


def get_sales_lead_preorder_contract(lead_id, database_url=None):
    lead_id = _clean_text(lead_id, 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_false_flags()}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "configured": False, "status": "not_configured", **_false_flags()}, 503

    try:
        import psycopg
    except ImportError:
        return {"success": False, "configured": True, "status": "dependency_missing", **_false_flags()}, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select l.lead_id, l.campaign_id, l.draft_id, l.send_design_id,
                           l.status, l.mode, l.campaign_source, l.lead_label,
                           l.contact_label, l.channel, l.chatwoot_conversation_id,
                           l.whatsapp_window_state, l.last_inbound_at, l.opt_in_state,
                           l.interest_json, l.next_owner_action, l.linked_order_id,
                           l.linked_preorder_id, l.created_by,
                           l.sends_customer_message, l.calls_chatwoot, l.calls_n8n,
                           l.creates_quote, l.creates_order, l.changes_stock,
                           l.dispatch_enabled, l.changes_runtime_now, l.changes_prompt_now,
                           l.physical_controls_enabled, l.customer_public_output_enabled,
                           l.writes_farm_data, l.created_at,
                           ev.event_type, ev.notes, ev.recorded_by, ev.created_at
                    from public.oom_sakkie_sales_leads l
                    left join lateral (
                        select event_type, notes, recorded_by, created_at
                        from public.oom_sakkie_sales_lead_events e
                        where e.lead_id = l.lead_id
                        order by created_at desc
                        limit 1
                    ) ev on true
                    where l.lead_id = %(lead_id)s
                    """,
                    {"lead_id": lead_id},
                )
                row = cursor.fetchone()
                event_rows = []
                if row:
                    cursor.execute(
                        """
                        select event_type, notes, recorded_by, status_observed, created_at
                        from public.oom_sakkie_sales_lead_events
                        where lead_id = %(lead_id)s
                        order by created_at asc
                        limit 50
                        """,
                        {"lead_id": lead_id},
                    )
                    event_rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_lead_contract_read_failed",
            "error_type": exc.__class__.__name__,
            **_false_flags(),
        }, 503

    if not row:
        return {"success": False, "configured": True, "status": "sales_lead_not_found", **_false_flags()}, 404

    lead = _sales_lead_row(row)
    lead["events"] = [_sales_lead_event_row(event_row) for event_row in event_rows]
    contract = build_preorder_deposit_contract_from_lead(lead)
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "preorder_deposit_contract_review_only",
        "lead_id": lead_id,
        "lead": lead,
        "contract": contract,
        "next_gate": "owner_confirms_missing_fields_before_any_preorder_deposit_order_or_customer_send",
        **_false_flags(),
    }, 200


def get_sales_lead_customer_followup_draft(lead_id, database_url=None):
    result, status_code = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    if status_code != 200:
        return result, status_code

    contract = result.get("contract") if isinstance(result.get("contract"), dict) else {}
    if contract.get("contract_status") != "owner_money_path_ready":
        return {
            "success": False,
            "configured": result.get("configured", True),
            "status": "owner_money_path_not_ready",
            "lead_id": result.get("lead_id") or _clean_text(lead_id, 100),
            "contract_status": contract.get("contract_status", ""),
            "missing_fields": contract.get("missing_fields") or [],
            "missing_core_context": contract.get("missing_core_context") or [],
            "next_gate": "record_owner_money_path_approval_before_customer_followup_draft",
            **_false_flags(),
        }, 409

    draft = build_customer_followup_draft_from_contract(contract)
    return {
        "success": True,
        "configured": result.get("configured", True),
        "status": "ok",
        "mode": "owner_review_customer_followup_draft_only",
        "lead_id": result.get("lead_id") or _clean_text(lead_id, 100),
        "lead": result.get("lead") or {},
        "contract": contract,
        "customer_followup_draft": draft,
        "next_gate": "owner_review_before_any_sam_chatwoot_customer_send_or_order_write",
        **_false_flags(),
    }, 200


def build_customer_followup_draft_from_contract(contract):
    contract = contract if isinstance(contract, dict) else {}
    summary = contract.get("lead_summary") if isinstance(contract.get("lead_summary"), dict) else {}
    required = contract.get("required_before_money_path") if isinstance(contract.get("required_before_money_path"), dict) else {}

    buyer = summary.get("buyer_or_contact") or "there"
    product = summary.get("product") or "pork preorder"
    cut_set = summary.get("cut_set") or "selected cut set"
    location = summary.get("location") or "your selected collection area"
    price = required.get("price_per_kg") or "the approved price/kg"
    week = required.get("available_week") or "the approved week"
    size = required.get("estimated_weight_or_size") or "final weight to be confirmed"
    deposit = required.get("deposit_amount_or_rule") or "the approved deposit rule"
    payment = required.get("payment_method") or "your selected payment method"
    delivery = required.get("delivery_or_collection") or "collection/delivery to be confirmed"

    message = (
        f"Hi {buyer}, I checked with the farm. For the {product} {cut_set} in {location}, "
        f"the current approved price is {price}. The available timing is {week}, with {size}. "
        f"The deposit rule is {deposit}. I have your preference as {delivery} and {payment}. "
        "Would you like me to send this through for final booking review?"
    )
    return {
        "draft_type": "sam_chatwoot_meat_preorder_followup",
        "mode": "owner_review_customer_followup_draft_only",
        "message": _clean_text(message, 1600),
        "owner_checks": [
            "Owner must review this draft before Sam or Chatwoot sends anything.",
            "This draft must not be treated as a formal quote PDF, order, preorder, stock reservation, or deposit request.",
            "If the customer accepts, the next build must still create a separate owner-reviewed booking/order/deposit rail.",
        ],
        "target_transport": "sam_chatwoot_whatsapp_review",
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "writes_farm_data": False,
    }


def build_preorder_deposit_contract_from_lead(lead):
    lead = lead if isinstance(lead, dict) else {}
    interest = _merged_sales_lead_interest(lead)
    owner_approval = _latest_owner_money_path_approval(lead)

    present = {
        "lead_id": lead.get("lead_id", ""),
        "buyer_or_contact": lead.get("contact_label") or lead.get("lead_label") or "",
        "source": lead.get("campaign_source", ""),
        "lead_status": lead.get("status", ""),
        "whatsapp_window_state": lead.get("whatsapp_window_state", ""),
        "product": interest.get("product") or interest.get("summary") or "",
        "cut_set": interest.get("cut_set") or "",
        "location": interest.get("location") or "",
        "customer_notes": interest.get("notes") or interest.get("summary") or "",
        "next_owner_action": lead.get("next_owner_action", ""),
    }
    required_before_money_path = {
        "price_per_kg": owner_approval.get("price_per_kg") or interest.get("price_per_kg") or "",
        "available_week": owner_approval.get("available_week") or interest.get("available_week") or interest.get("timing") or "",
        "estimated_weight_or_size": owner_approval.get("estimated_weight_or_size") or interest.get("estimated_weight") or interest.get("size") or "",
        "deposit_amount_or_rule": owner_approval.get("deposit_amount_or_rule") or interest.get("deposit_amount") or interest.get("deposit_rule") or "",
        "payment_method": owner_approval.get("payment_method") or interest.get("payment_method") or "",
        "delivery_or_collection": owner_approval.get("delivery_or_collection") or interest.get("delivery_or_collection") or interest.get("collection") or "",
        "owner_final_approval": owner_approval.get("owner_final_approval") or "",
    }
    missing_fields = [
        key for key, value in required_before_money_path.items()
        if not _clean_text(value, 200)
    ]
    missing_core_context = [
        key for key in ("buyer_or_contact", "product", "cut_set", "location")
        if not _clean_text(present.get(key), 200)
    ]
    can_prepare_manual_followup = not missing_core_context
    status = "ready_for_owner_followup" if can_prepare_manual_followup else "needs_core_lead_context"
    if missing_fields:
        status = "needs_owner_confirmation"
    elif owner_approval:
        status = "owner_money_path_ready"
    owner_questions = [
        "What price/kg should Charl quote for this lead?",
        "Which available week or slaughter window can Charl offer?",
        "What estimated half-carcass size/range should be discussed?",
        "What deposit rule should apply before any slaughter booking?",
        "Will this be collection or delivery, and where?",
    ]
    return {
        "contract_status": status,
        "lead_summary": present,
        "required_before_money_path": required_before_money_path,
        "owner_money_path_approval": owner_approval,
        "missing_fields": missing_fields,
        "missing_core_context": missing_core_context,
        "owner_questions": owner_questions,
        "manual_followup_prompt": _manual_preorder_followup_prompt(present, missing_fields),
        "safety_notes": [
            "This is a review contract only.",
            "It does not send a customer message, request a deposit, create a preorder, create an order, reserve stock, or update allocation.",
            "Charl must confirm the missing fields before any Sam/Chatwoot handoff or deposit request is built.",
        ],
        **_false_flags(),
    }


def build_owner_money_path_approval_event_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    approval = {
        "source": "ledger_owner_review",
        "kind": "owner_money_path_approval",
        "price_per_kg": _clean_text(payload.get("price_per_kg"), 80),
        "available_week": _clean_text(payload.get("available_week"), 120),
        "estimated_weight_or_size": _clean_text(
            payload.get("estimated_weight_or_size") or payload.get("estimated_weight"), 120
        ),
        "deposit_amount_or_rule": _clean_text(
            payload.get("deposit_amount_or_rule") or payload.get("deposit_rule"), 160
        ),
        "payment_method": _clean_text(payload.get("payment_method"), 80),
        "delivery_or_collection": _clean_text(payload.get("delivery_or_collection"), 80),
        "owner_final_approval": _clean_text(payload.get("owner_final_approval") or payload.get("approval"), 120),
        "owner_notes": _clean_text(payload.get("owner_notes") or payload.get("notes"), 500),
    }
    missing = [
        key for key in (
            "price_per_kg",
            "available_week",
            "estimated_weight_or_size",
            "deposit_amount_or_rule",
            "payment_method",
            "delivery_or_collection",
            "owner_final_approval",
        )
        if not approval.get(key)
    ]
    if missing:
        return None, {
            "success": False,
            "status": "owner_money_path_approval_missing_fields",
            "missing_fields": missing,
            **_false_flags(),
        }
    return {
        "event_type": "owner_money_path_approved",
        "status_observed": "order_ready_for_approval",
        "recorded_by": _clean_text(payload.get("recorded_by") or "owner", 80),
        "notes": _json(approval),
    }, None


def record_owner_money_path_approval(lead_id, payload, database_url=None):
    event_payload, error = build_owner_money_path_approval_event_payload(payload)
    if error:
        return error, 400
    result, status_code = record_sales_lead_event(lead_id, event_payload, database_url=database_url)
    if status_code != 201:
        return result, status_code
    result.update({
        "mode": "owner_money_path_approval_event_only",
        "approval": _parse_json_object(event_payload["notes"]),
        "next_gate": "manual_owner_review_before_any_customer_send_quote_order_or_stock_write",
        "records_owner_money_path_approval": True,
    })
    return result, status_code


def _sam_meat_intake_event_payload(lead_payload, contract):
    lead_payload = lead_payload if isinstance(lead_payload, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    interest = lead_payload.get("interest") if isinstance(lead_payload.get("interest"), dict) else {}
    fact_snapshot = {
        "source": "sam_meat_intake",
        "kind": "fact_snapshot",
        "lane": "meat_preorder",
        "interest": {
            "product": interest.get("product", ""),
            "product_type": interest.get("product_type", ""),
            "cut_set": interest.get("cut_set", ""),
            "location": interest.get("location", ""),
            "timing": interest.get("timing", ""),
            "delivery_or_collection": interest.get("delivery_or_collection", ""),
            "price_per_kg": interest.get("price_per_kg", ""),
            "deposit_rule": interest.get("deposit_rule", ""),
            "payment_method": interest.get("payment_method", ""),
            "notes": _clean_text(interest.get("notes", ""), 180),
            "conversation_id": interest.get("conversation_id", ""),
            "contact_id": interest.get("contact_id", ""),
            "sam_intake_lane": interest.get("sam_intake_lane", ""),
        },
        "contract": {
            "missing_core_fields": contract.get("missing_core_fields") or [],
            "missing_before_money_path": contract.get("missing_before_money_path") or [],
        },
        "authority": {
            "records_tracking_lead": True,
            "sends_customer_message": False,
            "creates_order": False,
            "changes_stock": False,
        },
    }
    return {
        "event_type": "status_observed",
        "status_observed": lead_payload.get("status") or "interested",
        "recorded_by": "sam_meat_intake",
        "notes": _json(fact_snapshot),
    }


def _merged_sales_lead_interest(lead):
    base = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    merged = dict(base)
    events = lead.get("events") if isinstance(lead.get("events"), list) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("recorded_by") != "sam_meat_intake":
            continue
        snapshot = _parse_json_object(event.get("notes", ""))
        if snapshot.get("source") != "sam_meat_intake":
            continue
        event_interest = snapshot.get("interest") if isinstance(snapshot.get("interest"), dict) else {}
        for key, value in event_interest.items():
            cleaned = _clean_text(value, 700)
            if cleaned:
                merged[key] = cleaned
    return merged


def _latest_owner_money_path_approval(lead):
    events = lead.get("events") if isinstance(lead.get("events"), list) else []
    approval = {}
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") != "owner_money_path_approved":
            continue
        snapshot = _parse_json_object(event.get("notes", ""))
        if snapshot.get("source") != "ledger_owner_review":
            continue
        if snapshot.get("kind") != "owner_money_path_approval":
            continue
        approval = {
            key: _clean_text(snapshot.get(key), 700)
            for key in (
                "price_per_kg",
                "available_week",
                "estimated_weight_or_size",
                "deposit_amount_or_rule",
                "payment_method",
                "delivery_or_collection",
                "owner_final_approval",
                "owner_notes",
            )
            if _clean_text(snapshot.get(key), 700)
        }
    return approval


def record_sales_lead_event(lead_id, payload, database_url=None):
    lead_id = _clean_text(lead_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean_text(payload.get("event_type", ""), 80)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_false_flags()}, 400
    if event_type not in SALES_LEAD_EVENT_TYPES:
        return {
            "success": False,
            "status": "invalid_event_type",
            "allowed_event_types": sorted(SALES_LEAD_EVENT_TYPES),
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
        "event_id": _lead_event_id(lead_id, event_type),
        "lead_id": lead_id,
        "event_type": event_type,
        "notes": _clean_text(payload.get("notes", ""), 1200),
        "recorded_by": _clean_text(payload.get("recorded_by", "owner"), 80),
        "status_observed": _status_or_default(payload.get("status_observed"), default=""),
        **_false_flags(),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_sales_lead_events (
                        event_id,
                        lead_id,
                        event_type,
                        notes,
                        recorded_by,
                        status_observed,
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
                        %(lead_id)s,
                        %(event_type)s,
                        %(notes)s,
                        %(recorded_by)s,
                        %(status_observed)s,
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
            "status": "sales_lead_event_write_failed",
            "error_type": exc.__class__.__name__,
            **_false_flags(),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "event_id": params["event_id"],
        "lead_id": lead_id,
        "event_type": event_type,
        "next_gate": "review_tracking_only_before_any_customer_send_quote_order_or_stock_write",
        **_false_flags(),
    }, 201


def record_sales_send_design_request_from_draft(draft_id, payload=None, database_url=None):
    draft_id = _clean_text(draft_id, 100)
    payload = payload if isinstance(payload, dict) else {}
    if not draft_id:
        return {"success": False, "status": "draft_id_required", "send_design_requests": [], **_false_flags()}, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _send_design_unavailable("not_configured", configured=False), 503

    try:
        import psycopg
    except ImportError:
        return _send_design_unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                draft = _fetch_outreach_draft_row(cursor, draft_id)
                if not draft:
                    return {
                        "success": False,
                        "configured": True,
                        "status": "outreach_draft_not_found",
                        "send_design_requests": [],
                        **_false_flags(),
                    }, 404
                draft_record = _sales_outreach_draft_row(draft)
                params = _sales_send_design_params(draft_record, payload)
                cursor.execute(
                    """
                    insert into public.oom_sakkie_sales_send_design_requests (
                        send_design_id,
                        draft_id,
                        status,
                        mode,
                        target_transport,
                        design_summary,
                        required_owner_checks_json,
                        source_draft_snapshot_json,
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
                        %(send_design_id)s,
                        %(draft_id)s,
                        %(status)s,
                        %(mode)s,
                        %(target_transport)s,
                        %(design_summary)s,
                        %(required_owner_checks_json)s::jsonb,
                        %(source_draft_snapshot_json)s::jsonb,
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
                    on conflict (draft_id, target_transport) do nothing
                    returning send_design_id
                    """,
                    params,
                )
                created_count = 1 if cursor.fetchone() else 0
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_send_design_write_failed",
            "error_type": exc.__class__.__name__,
            "send_design_requests": [],
            **_false_flags(),
        }, 503

    listed, list_status = list_sales_send_design_requests(limit=50, database_url=database_url)
    if list_status != 200:
        return listed, list_status
    requests = [item for item in listed.get("send_design_requests", []) if item.get("send_design_id") == params["send_design_id"]]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "customer_send_design_request_queue",
        "created_count": created_count,
        "send_design_id": params["send_design_id"],
        "draft_id": draft_id,
        "send_design_requests": requests,
        "next_gate": "owner_and_claude_review_before_any_customer_send_or_order_intake_consumer",
        "records_send_design_request": True,
        **_false_flags(),
    }, 201


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


def _sales_send_design_row(row):
    return {
        "send_design_id": row[0],
        "draft_id": row[1],
        "status": row[2],
        "mode": row[3],
        "target_transport": row[4],
        "design_summary": row[5] or "",
        "required_owner_checks": row[6] or [],
        "source_draft_snapshot": row[7] or {},
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


def _sales_lead_row(row):
    latest_event = None
    if row[32]:
        latest_event = {
            "event_type": row[32],
            "notes": row[33] or "",
            "recorded_by": row[34] or "",
            "created_at": _iso(row[35]),
        }
    return {
        "lead_id": row[0],
        "campaign_id": row[1] or "",
        "draft_id": row[2] or "",
        "send_design_id": row[3] or "",
        "status": row[4],
        "mode": row[5],
        "campaign_source": row[6],
        "lead_label": row[7],
        "contact_label": row[8] or "",
        "channel": row[9] or "",
        "chatwoot_conversation_id": row[10] or "",
        "whatsapp_window_state": row[11],
        "last_inbound_at": _iso(row[12]),
        "opt_in_state": row[13] or "",
        "interest": row[14] or {},
        "next_owner_action": row[15] or "",
        "linked_order_id": row[16] or "",
        "linked_preorder_id": row[17] or "",
        "created_by": row[18] or "",
        "sends_customer_message": bool(row[19]),
        "calls_chatwoot": bool(row[20]),
        "calls_n8n": bool(row[21]),
        "creates_quote": bool(row[22]),
        "creates_order": bool(row[23]),
        "changes_stock": bool(row[24]),
        "dispatch_enabled": bool(row[25]),
        "changes_runtime_now": bool(row[26]),
        "changes_prompt_now": bool(row[27]),
        "physical_controls_enabled": bool(row[28]),
        "customer_public_output_enabled": bool(row[29]),
        "writes_farm_data": bool(row[30]),
        "created_at": _iso(row[31]),
        "latest_event": latest_event,
    }


def _sales_lead_event_row(row):
    return {
        "event_type": row[0] or "",
        "notes": row[1] or "",
        "recorded_by": row[2] or "",
        "status_observed": row[3] or "",
        "created_at": _iso(row[4]),
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


def _fetch_outreach_draft_row(cursor, draft_id):
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
        where draft_id = %(draft_id)s
        """,
        {"draft_id": draft_id},
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


def _sales_send_design_params(draft, payload):
    target_transport = _clean_text(payload.get("target_transport") or "sam_chatwoot_whatsapp_review", 80)
    if target_transport not in {"sam_chatwoot_whatsapp_review", "manual_owner_send_review"}:
        target_transport = "sam_chatwoot_whatsapp_review"
    checks = [
        "Owner and Claude must review before any consumer can call Chatwoot, n8n, WhatsApp, or Telegram customer channels.",
        "Owner must confirm recipient, price, cuts, timing, delivery/collection, and stock health before any customer send.",
        "Future implementation must keep quote/order/stock writes behind separate owner approval.",
    ]
    snapshot = {
        "draft_id": draft.get("draft_id", ""),
        "campaign_id": draft.get("campaign_id", ""),
        "audience_label": draft.get("audience_label", ""),
        "draft_text": draft.get("draft_text", ""),
        "owner_checks": draft.get("owner_checks") or [],
        "proposal_text_is_untrusted": True,
    }
    return {
        "send_design_id": _send_design_id(draft.get("draft_id", ""), target_transport),
        "draft_id": draft.get("draft_id", ""),
        "status": "pending_owner_review",
        "mode": "customer_send_design_request_only",
        "target_transport": target_transport,
        "design_summary": _clean_text(
            payload.get("design_summary")
            or "Design a future owner-approved Sam/Chatwoot handoff for this draft. Do not send now.",
            700,
        ),
        "required_owner_checks_json": _json(checks),
        "source_draft_snapshot_json": _json(snapshot),
        "created_by": _clean_text(payload.get("created_by") or "owner", 80),
        **_false_flags(),
    }


def _sales_lead_params(payload):
    interest = payload.get("interest") if isinstance(payload.get("interest"), dict) else {}
    campaign_id = _clean_text(payload.get("campaign_id"), 100) or None
    draft_id = _clean_text(payload.get("draft_id"), 100) or None
    send_design_id = _clean_text(payload.get("send_design_id"), 100) or None
    lead_label = _clean_text(
        payload.get("lead_label")
        or payload.get("contact_label")
        or interest.get("customer_name")
        or interest.get("name")
        or "Buyer lead",
        160,
    )
    campaign_source = _clean_text(payload.get("campaign_source") or "inbound_chatwoot", 80)
    if campaign_source not in SALES_CAMPAIGN_SOURCES:
        campaign_source = "other"
    whatsapp_state = _clean_text(payload.get("whatsapp_window_state") or "unknown", 80)
    if whatsapp_state not in WHATSAPP_WINDOW_STATES:
        whatsapp_state = "unknown"
    seed = json.dumps({
        "campaign_id": campaign_id,
        "draft_id": draft_id,
        "send_design_id": send_design_id,
        "lead_label": lead_label,
        "contact_label": _clean_text(payload.get("contact_label"), 160),
        "channel": _clean_text(payload.get("channel") or "chatwoot_whatsapp", 80),
        "chatwoot_conversation_id": _clean_text(payload.get("chatwoot_conversation_id"), 100),
        "campaign_source": campaign_source,
    }, sort_keys=True, default=str)
    return {
        "lead_id": _lead_id(seed),
        "campaign_id": campaign_id,
        "draft_id": draft_id,
        "send_design_id": send_design_id,
        "status": _status_or_default(payload.get("status"), default="new"),
        "mode": "sales_lead_tracking_only",
        "campaign_source": campaign_source,
        "lead_label": lead_label,
        "contact_label": _clean_text(payload.get("contact_label"), 160),
        "channel": _clean_text(payload.get("channel") or "chatwoot_whatsapp", 80),
        "chatwoot_conversation_id": _clean_text(payload.get("chatwoot_conversation_id"), 100),
        "whatsapp_window_state": whatsapp_state,
        "last_inbound_at": _clean_text(payload.get("last_inbound_at"), 80) or None,
        "opt_in_state": _clean_text(payload.get("opt_in_state") or "unknown", 80),
        "interest_json": _json(interest),
        "next_owner_action": _clean_text(payload.get("next_owner_action"), 700),
        "linked_order_id": _clean_text(payload.get("linked_order_id"), 100),
        "linked_preorder_id": _clean_text(payload.get("linked_preorder_id"), 100),
        "created_by": _clean_text(payload.get("created_by") or "sam_or_owner_review", 80),
        **_false_flags(),
    }


def _sales_lead_counts(leads):
    by_status = {}
    whatsapp_window = {}
    for item in leads:
        status = item.get("status") or "unknown"
        by_status[status] = by_status.get(status, 0) + 1
        window = item.get("whatsapp_window_state") or "unknown"
        whatsapp_window[window] = whatsapp_window.get(window, 0) + 1
    return {
        "total": len(leads),
        "by_status": by_status,
        "whatsapp_window": whatsapp_window,
        "deposit_pending": by_status.get("deposit_pending", 0),
        "launch_test_open": (
            by_status.get("new", 0)
            + by_status.get("interested", 0)
            + by_status.get("asked_price", 0)
            + by_status.get("needs_callback", 0)
            + by_status.get("deposit_pending", 0)
            + by_status.get("order_ready_for_approval", 0)
        ),
        "closed_or_not_interested": by_status.get("closed", 0) + by_status.get("not_interested", 0),
        "owner_followup_needed": (
            by_status.get("new", 0)
            + by_status.get("interested", 0)
            + by_status.get("asked_price", 0)
            + by_status.get("needs_callback", 0)
            + by_status.get("order_ready_for_approval", 0)
        ),
        "template_required": whatsapp_window.get("template_required", 0),
    }


def _sales_lead_status_filter(value):
    status = _clean_text(value, 80)
    if not status or status == "all":
        return ""
    if status == "launch_test":
        return status
    return status if status in SALES_LEAD_STATUSES else ""


def _manual_preorder_followup_prompt(present, missing_fields):
    buyer = present.get("buyer_or_contact") or "the buyer"
    product = present.get("product") or "the pork option"
    cut_set = present.get("cut_set") or "the cut set"
    location = present.get("location") or "their area"
    if missing_fields:
        missing = ", ".join(missing_fields)
        return (
            f"Before replying to {buyer}, confirm: {missing}. "
            f"The recorded interest is {product}, {cut_set}, {location}."
        )
    return (
        f"Charl can manually follow up with {buyer} about {product}, {cut_set}, {location}. "
        "No system customer message has been sent."
    )


def _sam_meat_next_question(missing_core, missing_before_money_path):
    question_map = {
        "customer_name": "Who should I put this interest under?",
        "product_type": "Are you interested in a half carcass, full carcass, custom cuts, or assisted slaughter?",
        "location": "Where would this need to be delivered or collected?",
        "cut_set": "Which cut set are you interested in: Set A, Set B, Set C, or Set D?",
        "timing": "When would you ideally want this pork?",
        "delivery_or_collection": "Would you prefer collection or delivery?",
        "price_per_kg": "I need to confirm the current price with the farm before quoting.",
        "deposit_rule": "I need to confirm the deposit rule with the farm before booking anything.",
        "payment_method": "Would you prefer EFT or cash once the farm confirms availability?",
        "owner_final_approval": "I need the farm owner to approve this before any deposit or booking step.",
    }
    for field in list(missing_core or []) + list(missing_before_money_path or []):
        if field in question_map:
            return question_map[field]
    return "I have the intake details. I will ask the farm owner to review before any deposit, booking, or order step."


def _status_or_default(value, default):
    status = _clean_text(value, 80)
    if not status:
        return default
    return status if status in SALES_LEAD_STATUSES else default


def _send_design_id(draft_id, target_transport):
    digest = hashlib.sha256(f"{draft_id}|{target_transport}".encode("utf-8")).hexdigest()[:16].upper()
    return f"OSK-SALES-SEND-DESIGN-{digest}"


def _lead_id(seed):
    digest = hashlib.sha256(str(seed or "").encode("utf-8")).hexdigest()[:16].upper()
    return f"OSK-SALES-LEAD-{digest}"


def _lead_event_id(lead_id, event_type):
    digest = hashlib.sha256(
        f"{lead_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}".encode("utf-8")
    ).hexdigest()[:16].upper()
    return f"OSK-SALES-LEAD-EVENT-{digest}"


def _send_design_unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "customer_send_design_request_queue",
        "send_design_requests": [],
        **_false_flags(),
    }


def _sales_leads_unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "sales_lead_tracking_queue",
        "sales_leads": [],
        **_false_flags(),
    }


def _json(value):
    return json.dumps(value if value is not None else {}, default=str, ensure_ascii=True, sort_keys=True)


def _parse_json_object(value):
    try:
        parsed = json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


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
