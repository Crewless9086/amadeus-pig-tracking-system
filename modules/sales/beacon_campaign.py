from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from services.database_service import DATABASE_URL_ENV


BEACON_CAMPAIGN_MODE = "beacon_meat_launch_campaign_draft_only"

AUTHORITY_FLAGS = {
    "draft_only": True,
    "customer_public_output_enabled": False,
    "sends_customer_message": False,
    "posts_publicly": False,
    "calls_chatwoot": False,
    "calls_meta": False,
    "calls_n8n": False,
    "creates_quote": False,
    "creates_invoice": False,
    "creates_order": False,
    "changes_stock": False,
    "reserves_carcass": False,
    "books_slaughter": False,
    "books_butcher": False,
    "confirms_payment": False,
    "writes_farm_data": False,
}

MANUAL_POST_AUTHORITY_FLAGS = {
    **AUTHORITY_FLAGS,
    "records_evidence": True,
    "boosts_post": False,
    "spends_money": False,
    "reserves_stock": False,
    "dispatch_enabled": False,
    "changes_runtime_now": False,
    "changes_prompt_now": False,
    "physical_controls_enabled": False,
}

PERFORMANCE_AUTHORITY_FLAGS = {
    **MANUAL_POST_AUTHORITY_FLAGS,
    "recommends_boost": False,
    "boost_requires_owner_approval": True,
}

BOOST_RECOMMENDATION_SPEND_CAP = 500
FACEBOOK_POSTING_ENABLED_ENV = "BEACON_FACEBOOK_POSTING_ENABLED"
FACEBOOK_PAGE_ID_ENV = "BEACON_FACEBOOK_PAGE_ID"
FACEBOOK_PAGE_ACCESS_TOKEN_ENV = "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN"
FACEBOOK_GRAPH_VERSION_ENV = "BEACON_FACEBOOK_GRAPH_VERSION"
FACEBOOK_POST_CONFIRMATION_PHRASE = "POST EXACT BEACON PACKET"
SUPABASE_URL_ENV = "SUPABASE_URL"
SUPABASE_SERVICE_ROLE_KEY_ENV = "SUPABASE_SERVICE_ROLE_KEY"

FORBIDDEN_ACTIONS = [
    "no_public_post",
    "no_customer_dm",
    "no_chatwoot_send",
    "no_whatsapp_template",
    "no_meta_api_call",
    "no_order_create",
    "no_quote_invoice_create",
    "no_stock_reservation",
    "no_price_promise",
    "no_timing_promise",
    "no_slaughter_booking",
    "no_butcher_booking",
    "no_bank_confirmation",
]

OWNER_REVIEW_CHECKLIST = [
    "Choose which channel goes first: WhatsApp status, WhatsApp channel, Facebook, Instagram, or direct known buyers.",
    "Confirm whether public copy may mention Riversdale delivery/collection or should keep the area broad.",
    "Confirm whether public copy may mention a price/kg or should keep price on request until the pilot is proven.",
    "Choose the approved farm photo or video set before any public post is prepared.",
    "Confirm the first pilot target: how many halves/full carcasses should Sam try to fill before pausing demand.",
    "Confirm who handles delivery-day customer updates for the first pilot run.",
]


def build_meat_launch_campaign_selection(payload=None, approved_assets=None):
    """Return campaign draft/media pairing recommendations without doing any external action."""
    packet = build_meat_launch_campaign_packet(payload)
    approved_assets = approved_assets if isinstance(approved_assets, list) else []
    ranked_assets = _rank_approved_assets(approved_assets)
    channel_pairings = _channel_asset_pairings(packet.get("channel_drafts", []), ranked_assets)
    story_pairings = _channel_asset_pairings(packet.get("story_updates", []), ranked_assets, fallback_channel="story")
    return {
        "success": True,
        "mode": "beacon_meat_launch_campaign_media_selection_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign": packet.get("campaign", {}),
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "approved_media_count": len(ranked_assets),
        "ranked_media_assets": ranked_assets,
        "channel_draft_pairings": channel_pairings,
        "story_update_pairings": story_pairings,
        "owner_review_checklist": [
            "Choose the exact media asset for each draft before any public post is prepared.",
            "Confirm the chosen channel and campaign cap before posting.",
            "Confirm no private customer, address, invoice, or sensitive farm detail is visible in the selected media.",
            "Public posting still happens only through a later owner-approved posting gate.",
        ],
        "next_gate": "owner_selects_media_and_campaign_draft_before_any_public_post",
    }


def build_meat_launch_campaign_publish_packet(payload=None, approved_assets=None):
    """Build the exact owner-review publish packet without posting, scheduling, or persisting approval."""
    payload = payload if isinstance(payload, dict) else {}
    campaign_packet = build_meat_launch_campaign_packet(payload)
    approved_assets = approved_assets if isinstance(approved_assets, list) else []
    ranked_assets = _rank_approved_assets(approved_assets)
    draft_id = _clean_text(payload.get("draft_id"))
    selected_asset_id = _clean_text(payload.get("asset_id"))
    selected_channel = _clean_text(payload.get("channel"))
    pilot_cap = _clean_text(payload.get("pilot_cap"))
    owner_notes = _clean_text(payload.get("owner_notes"))
    draft = _find_draft(campaign_packet, draft_id)
    asset = _find_asset(ranked_assets, selected_asset_id)
    errors = []
    if not draft:
        errors.append("selected_draft_not_found")
    if selected_asset_id and not asset:
        errors.append("selected_asset_not_approved_or_not_found")
    channel = selected_channel or (draft.get("channel") if draft else "")
    packet_id = _publish_packet_id(draft_id, selected_asset_id, channel, pilot_cap)
    exact_text = draft.get("text", "") if draft else ""
    return {
        "success": not errors,
        "mode": "beacon_campaign_publish_packet_owner_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "publish_packet_id": packet_id,
        "campaign": campaign_packet.get("campaign", {}),
        "selected_draft": {
            "draft_id": draft.get("id", "") if draft else draft_id,
            "label": draft.get("label", "") if draft else "",
            "channel": channel,
            "intent": draft.get("intent", "") if draft else "",
            "exact_text": exact_text,
        },
        "selected_asset": asset,
        "pilot_cap": pilot_cap,
        "owner_notes": owner_notes,
        "approval_status": "owner_review_required",
        "approval_records_publish": False,
        "approval_sends_or_posts": False,
        "requires_owner_exact_text_confirmation": True,
        "requires_owner_exact_media_confirmation": bool(asset),
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "safety_checks": {
            "draft_is_limited_preorder": _has_preorder_signal(exact_text.lower()) and "limited" in exact_text.lower(),
            "draft_has_no_forbidden_promise": not _has_forbidden_promise(exact_text.lower()),
            "asset_is_owner_approved": bool(asset.get("public_use_approved")) if asset else not selected_asset_id,
            "no_public_send_or_post": True,
            "no_meta_call": True,
            "no_signed_url_created": True,
        },
        "errors": errors,
        "owner_review_checklist": [
            "Read the exact text as the customer/public will see it.",
            "Confirm the selected media is approved and safe for public use.",
            "Confirm the pilot cap before posting anywhere.",
            "Confirm the chosen channel before any later public-post action.",
            "Use this packet as review evidence only; no post is sent from this step.",
        ],
        "next_gate": "owner_approves_exact_publish_packet_before_manual_or_gated_public_post",
    }


def build_beacon_facebook_image_launch_packet(payload=None, approved_assets=None):
    payload = payload if isinstance(payload, dict) else {}
    selection = build_meat_launch_campaign_selection(payload, approved_assets=approved_assets)
    facebook_pairing = next(
        (
            item for item in selection.get("channel_draft_pairings", [])
            if item.get("draft_id") == "facebook_post"
        ),
        {},
    )
    asset_id = _clean_text(payload.get("asset_id") or facebook_pairing.get("recommended_asset_id"))
    publish_packet = build_meat_launch_campaign_publish_packet(
        {
            **payload,
            "draft_id": "facebook_post",
            "channel": "Facebook",
            "asset_id": asset_id,
            "pilot_cap": payload.get("pilot_cap") or "2 halves",
        },
        approved_assets=approved_assets,
    )
    execution_payload = {
        "publish_packet_id": publish_packet.get("publish_packet_id", ""),
        "channel": "Facebook",
        "exact_text": (publish_packet.get("selected_draft") or {}).get("exact_text", ""),
        "asset_id": ((publish_packet.get("selected_asset") or {}).get("asset_id") or ""),
        "owner_confirmation": FACEBOOK_POST_CONFIRMATION_PHRASE,
    }
    return {
        "success": bool(publish_packet.get("success")) and bool((publish_packet.get("selected_asset") or {}).get("asset_id")),
        "mode": "beacon_facebook_image_launch_packet_owner_review",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "publish_packet": publish_packet,
        "recommended_pairing": facebook_pairing,
        "execution_payload": execution_payload,
        "owner_confirmation_required": FACEBOOK_POST_CONFIRMATION_PHRASE,
        "ready_for_owner_post_approval": bool(publish_packet.get("success")) and bool(execution_payload["asset_id"]),
        "posts_publicly_now": False,
        "calls_meta_now": False,
        "next_gate": "owner_posts_exact_execution_payload_through_facebook_post_executions",
        **AUTHORITY_FLAGS,
    }


def manual_post_evidence_policy():
    return {
        "success": True,
        "mode": "beacon_manual_public_post_evidence_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "purpose": "Record owner-posted campaign evidence after a manual public post.",
        "allowed_inputs": [
            "publish_packet_id",
            "channel",
            "post_url",
            "posted_at",
            "posted_by",
            "campaign_label",
            "evidence_notes",
            "initial manual metrics",
        ],
        "owner_checklist": [
            "Prepare a publish packet and review exact text/media.",
            "Post manually in the chosen public channel.",
            "Paste the post URL or channel evidence back into Beacon.",
            "Record early metrics so Beacon can learn what worked.",
            "Do not boost or spend from this step.",
        ],
        "next_gate": "beacon_performance_tracking_before_boost_recommendation_or_meta_ads_access",
        **MANUAL_POST_AUTHORITY_FLAGS,
    }


def record_beacon_manual_post_evidence(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _manual_post_params(payload)
    if not params["publish_packet_id"]:
        return {
            "success": False,
            "status": "publish_packet_id_required",
            "manual_post_event": _public_manual_post_event(params),
            **MANUAL_POST_AUTHORITY_FLAGS,
        }, 400
    if not params["channel"]:
        return {
            "success": False,
            "status": "channel_required",
            "manual_post_event": _public_manual_post_event(params),
            **MANUAL_POST_AUTHORITY_FLAGS,
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _manual_post_unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _manual_post_unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.beacon_manual_post_events (
                        manual_post_event_id, mode, publish_packet_id, channel, post_url,
                        posted_at, posted_by, campaign_label, evidence_notes,
                        initial_metrics_json, records_evidence, sends_customer_message,
                        posts_publicly, calls_chatwoot, calls_meta, calls_n8n,
                        boosts_post, spends_money, creates_quote, creates_invoice,
                        creates_order, changes_stock, reserves_stock, dispatch_enabled,
                        changes_runtime_now, changes_prompt_now, physical_controls_enabled,
                        customer_public_output_enabled, writes_farm_data
                    )
                    values (
                        %(manual_post_event_id)s, %(mode)s, %(publish_packet_id)s,
                        %(channel)s, %(post_url)s, %(posted_at)s, %(posted_by)s,
                        %(campaign_label)s, %(evidence_notes)s,
                        %(initial_metrics_json)s::jsonb, %(records_evidence)s,
                        %(sends_customer_message)s, %(posts_publicly)s,
                        %(calls_chatwoot)s, %(calls_meta)s, %(calls_n8n)s,
                        %(boosts_post)s, %(spends_money)s, %(creates_quote)s,
                        %(creates_invoice)s, %(creates_order)s, %(changes_stock)s,
                        %(reserves_stock)s, %(dispatch_enabled)s,
                        %(changes_runtime_now)s, %(changes_prompt_now)s,
                        %(physical_controls_enabled)s, %(customer_public_output_enabled)s,
                        %(writes_farm_data)s
                    )
                    on conflict (manual_post_event_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_manual_post_evidence_write_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "manual_post_event": _public_manual_post_event(params),
            **MANUAL_POST_AUTHORITY_FLAGS,
        }, 500

    return {
        "success": True,
        "configured": True,
        "status": "beacon_manual_post_evidence_recorded" if created_count else "beacon_manual_post_evidence_already_recorded",
        "created_count": created_count,
        "manual_post_event_id": params["manual_post_event_id"],
        "manual_post_event": _public_manual_post_event(params),
        "next_gate": "beacon_performance_tracking_before_boost_recommendation_or_meta_ads_access",
        **MANUAL_POST_AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def list_beacon_manual_post_evidence(limit=25, publish_packet_id="", database_url=None):
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 25
    publish_packet_id = _clean_text(publish_packet_id)[:120]
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _manual_post_unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _manual_post_unavailable("dependency_missing", configured=True), 500

    where = "where publish_packet_id = %(publish_packet_id)s" if publish_packet_id else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select manual_post_event_id, publish_packet_id, channel, post_url,
                           posted_at, posted_by, campaign_label, evidence_notes,
                           initial_metrics_json, created_at
                    from public.beacon_manual_post_events
                    {where}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {"limit": limit, "publish_packet_id": publish_packet_id},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_manual_post_evidence_read_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "manual_post_events": [],
            **MANUAL_POST_AUTHORITY_FLAGS,
        }, 500

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "beacon_manual_public_post_evidence_only",
        "manual_post_events": [_manual_post_row_to_event(row) for row in rows],
        "policy": manual_post_evidence_policy(),
        "next_gate": "beacon_performance_tracking_before_boost_recommendation_or_meta_ads_access",
        **MANUAL_POST_AUTHORITY_FLAGS,
    }, 200


def record_beacon_campaign_performance_event(payload, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _performance_params(payload)
    if not params["manual_post_event_id"] and not params["publish_packet_id"]:
        return {
            "success": False,
            "status": "manual_post_event_id_or_publish_packet_id_required",
            "performance_event": _public_performance_event(params),
            **PERFORMANCE_AUTHORITY_FLAGS,
        }, 400

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _performance_unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _performance_unavailable("dependency_missing", configured=True), 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.beacon_campaign_performance_events (
                        performance_event_id, mode, manual_post_event_id, publish_packet_id,
                        channel, measurement_window, spend_amount, spend_currency,
                        reach, impressions, reactions, comments, shares, messages_to_sam,
                        qualified_buyer_leads, booking_review_requests, notes,
                        recommended_action, recommendation_reason, recommended_spend_amount,
                        recommended_duration_days, max_spend_cap_amount, cost_per_message,
                        cost_per_qualified_lead, records_evidence, recommends_boost,
                        boost_requires_owner_approval, sends_customer_message, posts_publicly,
                        calls_chatwoot, calls_meta, calls_n8n, boosts_post, spends_money,
                        creates_quote, creates_invoice, creates_order, changes_stock,
                        reserves_stock, dispatch_enabled, changes_runtime_now,
                        changes_prompt_now, physical_controls_enabled,
                        customer_public_output_enabled, writes_farm_data, recorded_by
                    )
                    values (
                        %(performance_event_id)s, %(mode)s, %(manual_post_event_id)s,
                        %(publish_packet_id)s, %(channel)s, %(measurement_window)s,
                        %(spend_amount)s, %(spend_currency)s, %(reach)s, %(impressions)s,
                        %(reactions)s, %(comments)s, %(shares)s, %(messages_to_sam)s,
                        %(qualified_buyer_leads)s, %(booking_review_requests)s, %(notes)s,
                        %(recommended_action)s, %(recommendation_reason)s,
                        %(recommended_spend_amount)s, %(recommended_duration_days)s,
                        %(max_spend_cap_amount)s, %(cost_per_message)s,
                        %(cost_per_qualified_lead)s, %(records_evidence)s,
                        %(recommends_boost)s, %(boost_requires_owner_approval)s,
                        %(sends_customer_message)s, %(posts_publicly)s,
                        %(calls_chatwoot)s, %(calls_meta)s, %(calls_n8n)s,
                        %(boosts_post)s, %(spends_money)s, %(creates_quote)s,
                        %(creates_invoice)s, %(creates_order)s, %(changes_stock)s,
                        %(reserves_stock)s, %(dispatch_enabled)s,
                        %(changes_runtime_now)s, %(changes_prompt_now)s,
                        %(physical_controls_enabled)s, %(customer_public_output_enabled)s,
                        %(writes_farm_data)s, %(recorded_by)s
                    )
                    on conflict (performance_event_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_campaign_performance_write_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "performance_event": _public_performance_event(params),
            **PERFORMANCE_AUTHORITY_FLAGS,
        }, 500

    return {
        "success": True,
        "configured": True,
        "status": "beacon_campaign_performance_event_recorded" if created_count else "beacon_campaign_performance_event_already_recorded",
        "created_count": created_count,
        "performance_event_id": params["performance_event_id"],
        "performance_event": _public_performance_event(params),
        "boost_packet": _boost_packet(params),
        "next_gate": "owner_reviews_boost_recommendation_before_any_meta_or_paid_spend_authority",
        **PERFORMANCE_AUTHORITY_FLAGS,
    }, 201 if created_count else 200


def build_beacon_boost_recommendation_packet(payload=None):
    payload = payload if isinstance(payload, dict) else {}
    params = _performance_params(payload)
    return _boost_packet(params)


def list_beacon_campaign_performance_events(limit=25, publish_packet_id="", manual_post_event_id="", database_url=None):
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 25
    publish_packet_id = _clean_text(publish_packet_id)[:120]
    manual_post_event_id = _clean_text(manual_post_event_id)[:120]
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _performance_unavailable("not_configured", configured=False), 503
    try:
        import psycopg
    except ImportError:
        return _performance_unavailable("dependency_missing", configured=True), 500

    where = ""
    if manual_post_event_id:
        where = "where manual_post_event_id = %(manual_post_event_id)s"
    elif publish_packet_id:
        where = "where publish_packet_id = %(publish_packet_id)s"

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select performance_event_id, manual_post_event_id, publish_packet_id,
                           channel, measurement_window, spend_amount, spend_currency,
                           reach, impressions, reactions, comments, shares,
                           messages_to_sam, qualified_buyer_leads,
                           booking_review_requests, notes, recommended_action,
                           recommendation_reason, recommended_spend_amount,
                           recommended_duration_days, max_spend_cap_amount,
                           cost_per_message, cost_per_qualified_lead,
                           recommends_boost, recorded_by, created_at
                    from public.beacon_campaign_performance_events
                    {where}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {
                        "limit": limit,
                        "publish_packet_id": publish_packet_id,
                        "manual_post_event_id": manual_post_event_id,
                    },
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_campaign_performance_read_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "performance_events": [],
            **PERFORMANCE_AUTHORITY_FLAGS,
        }, 500

    events = [_performance_row_to_event(row) for row in rows]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "beacon_campaign_performance_evidence_only",
        "performance_events": events,
        "latest_boost_packet": _boost_packet(_event_to_performance_params(events[0])) if events else {},
        "next_gate": "owner_reviews_boost_recommendation_before_any_meta_or_paid_spend_authority",
        **PERFORMANCE_AUTHORITY_FLAGS,
    }, 200


def facebook_posting_policy(environ=None):
    source = environ if environ is not None else os.environ
    enabled = _truthy(source.get(FACEBOOK_POSTING_ENABLED_ENV))
    page_id = _clean_text(source.get(FACEBOOK_PAGE_ID_ENV))
    token = _clean_text(source.get(FACEBOOK_PAGE_ACCESS_TOKEN_ENV))
    supabase_url = _clean_text(source.get(SUPABASE_URL_ENV))
    supabase_key = _clean_text(source.get(SUPABASE_SERVICE_ROLE_KEY_ENV))
    page_credentials_configured = bool(page_id and token)
    media_storage_configured = bool(supabase_url and supabase_key)
    posting_ready = bool(enabled and page_credentials_configured)
    return {
        "success": True,
        "mode": "beacon_facebook_page_post_execution_gate",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "enabled": enabled,
        "enabled_env": FACEBOOK_POSTING_ENABLED_ENV,
        "page_id_configured": bool(page_id),
        "page_id_env": FACEBOOK_PAGE_ID_ENV,
        "page_access_token_configured": bool(token),
        "page_access_token_env": FACEBOOK_PAGE_ACCESS_TOKEN_ENV,
        "graph_version_env": FACEBOOK_GRAPH_VERSION_ENV,
        "required_owner_confirmation": FACEBOOK_POST_CONFIRMATION_PHRASE,
        "text_posting_configured": page_credentials_configured,
        "media_storage_configured": media_storage_configured,
        "image_posting_configured": bool(page_credentials_configured and media_storage_configured),
        "posts_text_only_now": posting_ready,
        "posts_media_now": bool(posting_ready and media_storage_configured),
        "posts_image_now": bool(posting_ready and media_storage_configured),
        "media_source": "approved_beacon_supabase_image_signed_url",
        "boosts_or_spends_now": False,
        "required_envs": [
            FACEBOOK_POSTING_ENABLED_ENV,
            FACEBOOK_PAGE_ID_ENV,
            FACEBOOK_PAGE_ACCESS_TOKEN_ENV,
        ],
        **_facebook_execution_authority(False),
    }


def execute_beacon_facebook_page_post(payload, database_url=None, poster=None, environ=None):
    payload = payload if isinstance(payload, dict) else {}
    policy = facebook_posting_policy(environ=environ)
    params = _facebook_post_params(payload, policy)
    validation_error = _facebook_post_validation_error(params, policy)
    if validation_error:
        params["execution_status"] = validation_error
        _record_facebook_post_execution_event(params, database_url=database_url)
        return {
            "success": False,
            "status": validation_error,
            "policy": policy,
            "execution_event": _public_facebook_post_event(params),
            **_facebook_execution_authority(False),
        }, 400 if validation_error not in {"facebook_posting_disabled", "facebook_page_credentials_missing"} else 503

    post_fn = poster or _post_to_facebook_page
    post_result, post_status = post_fn(params, policy)
    execution_status = "facebook_page_post_sent" if post_status < 400 and post_result.get("success") else "facebook_page_post_failed"
    params.update({
        "execution_status": execution_status,
        "facebook_post_id": _clean_text(post_result.get("facebook_post_id") or post_result.get("id"))[:160],
        "facebook_response_json": json.dumps(post_result, sort_keys=True, default=str),
    })
    record_result, record_status = _record_facebook_post_execution_event(params, database_url=database_url)
    return {
        "success": execution_status == "facebook_page_post_sent",
        "status": execution_status,
        "post_status_code": post_status,
        "facebook_post_id": params["facebook_post_id"],
        "facebook_result": post_result,
        "record_status_code": record_status,
        "record_result": record_result,
        "execution_event": _public_facebook_post_event(params),
        "policy": policy,
        **_facebook_execution_authority(execution_status == "facebook_page_post_sent"),
    }, 200 if execution_status == "facebook_page_post_sent" else 502


def list_beacon_facebook_post_execution_events(limit=25, publish_packet_id="", database_url=None):
    try:
        limit = max(1, min(int(limit), 100))
    except (TypeError, ValueError):
        limit = 25
    publish_packet_id = _clean_text(publish_packet_id)[:120]
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _facebook_post_unavailable("not_configured", False), 503
    try:
        import psycopg
    except ImportError:
        return _facebook_post_unavailable("dependency_missing", True), 500
    where = "where publish_packet_id = %(publish_packet_id)s" if publish_packet_id else ""
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select execution_event_id, publish_packet_id, channel, exact_text,
                           owner_confirmation, execution_status, facebook_post_id,
                           facebook_response_json, created_at
                    from public.beacon_facebook_post_execution_events
                    {where}
                    order by created_at desc
                    limit %(limit)s
                    """,
                    {"limit": limit, "publish_packet_id": publish_packet_id},
                )
                rows = cursor.fetchall()
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_facebook_post_execution_read_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "execution_events": [],
            **_facebook_execution_authority(False),
        }, 500
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "beacon_facebook_page_post_execution_gate",
        "execution_events": [_facebook_post_row_to_event(row) for row in rows],
        "policy": facebook_posting_policy(),
        **_facebook_execution_authority(False),
    }, 200


def build_meat_launch_campaign_packet(payload=None):
    """Return Beacon's first meat-launch campaign drafts without doing any external action."""
    payload = payload if isinstance(payload, dict) else {}
    pilot_name = _clean_text(payload.get("pilot_name")) or "First pork freezer preorder pilot"
    farm_name = _clean_text(payload.get("farm_name")) or "Amadeus Farm"
    area = _clean_text(payload.get("area")) or "Riversdale and nearby routes"
    product_focus = _clean_text(payload.get("product_focus")) or "half carcass Set A and full carcass pork freezer options"

    packet = {
        "success": True,
        "mode": BEACON_CAMPAIGN_MODE,
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "campaign": {
            "name": pilot_name,
            "status": "draft_only_owner_review_required",
            "farm_name": farm_name,
            "area": area,
            "product_focus": product_focus,
            "primary_goal": "Generate controlled inbound demand for Sam Meat without overpromising stock, price, timing, or delivery.",
        },
        "authority": deepcopy(AUTHORITY_FLAGS),
        "forbidden_actions": list(FORBIDDEN_ACTIONS),
        "campaign_angles": _campaign_angles(farm_name, area, product_focus),
        "channel_drafts": _channel_drafts(farm_name, area, product_focus),
        "story_updates": _story_updates(farm_name, area),
        "owner_review_checklist": list(OWNER_REVIEW_CHECKLIST),
        "handoff_to_sam": {
            "inbound_prompt": "When a buyer replies, Sam should collect product, cut set, town, delivery/collection, address/location when delivery is requested, timing, payment preference, budget/target kg where useful, and final booking-review confirmation.",
            "must_not_say": [
                "Your order is confirmed.",
                "Your price is final.",
                "Your deposit is confirmed.",
                "Your carcass is reserved.",
                "Slaughter or butcher booking is confirmed.",
            ],
        },
        "next_gate": "owner_reviews_campaign_before_any_public_or_customer_send",
    }
    validation = validate_meat_launch_campaign_packet(packet)
    packet["validation"] = validation
    return packet


def validate_meat_launch_campaign_packet(packet):
    drafts = _all_draft_texts(packet)
    unsafe = []
    missing_preorder = []
    missing_limited = []
    for draft in drafts:
        text = draft["text"].lower()
        if not _has_preorder_signal(text):
            missing_preorder.append(draft["id"])
        if "limited" not in text:
            missing_limited.append(draft["id"])
        if _has_forbidden_promise(text):
            unsafe.append(draft["id"])

    authority = packet.get("authority") if isinstance(packet.get("authority"), dict) else {}
    unsafe_flags = [
        name for name, value in authority.items()
        if name != "draft_only" and value is True
    ]

    return {
        "success": not unsafe and not missing_preorder and not missing_limited and not unsafe_flags,
        "checked_draft_count": len(drafts),
        "missing_preorder_signal": missing_preorder,
        "missing_limited_signal": missing_limited,
        "unsafe_promise_drafts": unsafe,
        "unsafe_authority_flags": unsafe_flags,
    }


def format_meat_launch_campaign_markdown(packet):
    campaign = packet.get("campaign", {})
    lines = [
        "# Meat Launch Campaign Packet",
        "",
        "## Status",
        "",
        f"- Mode: `{packet.get('mode', '')}`",
        f"- Agent: {packet.get('agent', 'Beacon')}",
        f"- Campaign: {campaign.get('name', '')}",
        f"- Status: {campaign.get('status', '')}",
        f"- Next gate: `{packet.get('next_gate', '')}`",
        "",
        "This packet is draft-only. It does not post publicly, send customer messages, create quotes or invoices, create orders, reserve carcasses, change stock, book slaughter, book a butcher slot, or confirm payments.",
        "",
        "## Campaign Goal",
        "",
        campaign.get("primary_goal", ""),
        "",
        "## Campaign Angles",
        "",
    ]
    for angle in packet.get("campaign_angles", []):
        lines.extend([
            f"### {angle.get('title', '')}",
            "",
            angle.get("summary", ""),
            "",
            f"- Best channel: {angle.get('best_channel', '')}",
            f"- Sam handoff: {angle.get('sam_handoff', '')}",
            "",
        ])

    lines.extend(["## Channel Drafts", ""])
    for draft in packet.get("channel_drafts", []):
        lines.extend([
            f"### {draft.get('label', draft.get('id', 'Draft'))}",
            "",
            f"- Channel: {draft.get('channel', '')}",
            f"- Intent: {draft.get('intent', '')}",
            "",
            "```text",
            draft.get("text", ""),
            "```",
            "",
        ])

    lines.extend(["## Story Updates", ""])
    for update in packet.get("story_updates", []):
        lines.extend([
            f"### {update.get('label', update.get('id', 'Story'))}",
            "",
            "```text",
            update.get("text", ""),
            "```",
            "",
        ])

    lines.extend(["## Owner Review Checklist", ""])
    for item in packet.get("owner_review_checklist", []):
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## Authority Boundary",
        "",
    ])
    for name, value in sorted((packet.get("authority") or {}).items()):
        lines.append(f"- `{name}`: `{str(value).lower()}`")

    lines.extend([
        "",
        "## Forbidden Actions",
        "",
    ])
    for item in packet.get("forbidden_actions", []):
        lines.append(f"- `{item}`")

    validation = packet.get("validation", {})
    lines.extend([
        "",
        "## Validation",
        "",
        f"- Success: `{str(validation.get('success')).lower()}`",
        f"- Checked drafts: `{validation.get('checked_draft_count', 0)}`",
        "",
    ])
    return "\n".join(lines).rstrip() + "\n"


def _campaign_angles(farm_name, area, product_focus):
    return [
        {
            "id": "controlled_freezer_preorder",
            "title": "Controlled Freezer Preorder",
            "summary": f"Position {farm_name} pork as a limited, pre-booked freezer run for households that want to plan ahead instead of buying anonymous supermarket meat.",
            "best_channel": "WhatsApp status and Facebook",
            "sam_handoff": "Ask whether the buyer wants half carcass, full carcass, or cut-set guidance.",
        },
        {
            "id": "set_a_family_pack",
            "title": "Set A Family Freezer Pack",
            "summary": "Explain Set A as the practical family freezer option while keeping price, timing, and final packed weight for the farm confirmation step.",
            "best_channel": "Facebook and direct known buyers",
            "sam_handoff": "Answer what Set A includes, then collect town, delivery/collection, timing, and payment preference.",
        },
        {
            "id": "farm_to_freezer_story",
            "title": "Farm To Freezer Story",
            "summary": f"Show the journey from farm planning to packed pork, with limited availability and pre-booking as part of the story rather than a pressure tactic.",
            "best_channel": "Instagram story and WhatsApp status",
            "sam_handoff": "Invite replies from people who want Sam to check the best fit for their freezer, budget, or target kg.",
        },
        {
            "id": "local_route_pilot",
            "title": "Local Route Pilot",
            "summary": f"Keep the first run focused around {area}, so delivery and collection promises stay controlled while demand is measured.",
            "best_channel": "WhatsApp status and known-buyer share",
            "sam_handoff": "Capture address or shared location when delivery is requested.",
        },
    ]


def _channel_drafts(farm_name, area, product_focus):
    return [
        {
            "id": "whatsapp_status_1",
            "label": "WhatsApp Status 1",
            "channel": "WhatsApp status",
            "intent": "Soft interest check",
            "text": f"{farm_name} is preparing a limited pork freezer preorder run for {area}. Half carcass Set A and full carcass options are pre-booked only; price, timing, and final packed weight are confirmed before booking. Reply if you want Sam to note your interest.",
        },
        {
            "id": "whatsapp_status_2",
            "label": "WhatsApp Status 2",
            "channel": "WhatsApp status",
            "intent": "Explain the offer simply",
            "text": "Limited pork freezer preorders are opening. This is not ready-shelf stock; it is pre-booked farm pork, packed after processing, with final weight confirmed once known. Ask Sam about half carcass Set A, full carcass, delivery, or collection.",
        },
        {
            "id": "whatsapp_channel",
            "label": "WhatsApp Channel Draft",
            "channel": "WhatsApp channel or broadcast draft",
            "intent": "First owner-approved announcement",
            "text": f"We are testing a limited {farm_name} pork freezer preorder run. The focus is {product_focus}. Orders are pre-booked, and the farm confirms price, available timing, deposit steps, and final packed weight before anything is booked. Message Sam if you want to be added to the review list.",
        },
        {
            "id": "facebook_post",
            "label": "Facebook Post Draft",
            "channel": "Facebook",
            "intent": "Public demand generation",
            "text": f"{farm_name} is preparing a limited pork freezer preorder pilot for {area}. We are starting small so that every booking can be handled properly. The first focus is {product_focus}. This is pre-booked farm pork, not unlimited shop stock: price, timing, delivery/collection, deposit steps, and final packed weight are confirmed before the booking is accepted. If you want pork for your freezer, send us a message and Sam will collect the details.",
        },
        {
            "id": "instagram_caption",
            "label": "Instagram Caption Draft",
            "channel": "Instagram",
            "intent": "Story-led launch caption",
            "text": f"A small farm run, planned properly. {farm_name} is opening limited pork freezer preorders, starting with half carcass Set A and full carcass interest. Every order is pre-booked, with price, timing, deposit steps, and final packed weight confirmed before booking. Message Sam if you want to join the first review list.",
        },
        {
            "id": "customer_education",
            "label": "Customer Education Draft",
            "channel": "Facebook/WhatsApp explainer",
            "intent": "Reduce confusion about final weight",
            "text": "How the freezer preorder works: availability is limited, so interest is captured first. The farm then confirms price/kg, timing, delivery or collection, and deposit steps. Packed weight is estimated early, but the final amount is only confirmed after processing, because real carcass and cut yield can vary.",
        },
    ]


def _story_updates(farm_name, area):
    return [
        {
            "id": "story_slide_1",
            "label": "Story Slide 1",
            "text": f"Limited pork freezer preorders are opening soon from {farm_name}. Pre-booked only, starting with the first controlled pilot around {area}.",
        },
        {
            "id": "story_slide_2",
            "label": "Story Slide 2",
            "text": "Half carcass Set A is for families who want practical freezer pork. Limited availability, pre-booked, with final packed weight confirmed after processing.",
        },
        {
            "id": "story_slide_3",
            "label": "Story Slide 3",
            "text": "Sam will collect the details: half or full carcass, town, delivery or collection, timing, payment preference, and any budget or freezer-size target. Limited pre-booked run only.",
        },
        {
            "id": "story_slide_4",
            "label": "Story Slide 4",
            "text": "Want to join the limited preorder review list? Reply and Sam will capture your interest. No booking is final until the farm confirms price, timing, and deposit steps.",
        },
    ]


def _rank_approved_assets(assets):
    ranked = []
    for asset in assets:
        if _asset_status(asset) != "approved":
            continue
        tags = _asset_list(asset.get("subject_tags"))
        relevance = _asset_list(asset.get("sale_stream_relevance"))
        privacy_risk = _clean_text(asset.get("privacy_risk")).lower() or "unknown"
        media_type = _clean_text(asset.get("media_type")).lower() or "unknown"
        quality_score = _safe_int(asset.get("quality_score"), 0)
        score = quality_score
        if media_type == "image":
            score += 20
        if media_type == "video":
            score += 15
        if "meat" in relevance:
            score += 25
        if any(tag in tags for tag in ("pork", "freezer", "set a", "half carcass", "family pack")):
            score += 15
        if privacy_risk in ("high", "medium"):
            score -= 40 if privacy_risk == "high" else 20
        ranked.append({
            "asset_id": asset.get("asset_id", ""),
            "title": asset.get("title") or asset.get("original_filename") or asset.get("asset_id", ""),
            "media_type": media_type,
            "storage_bucket": asset.get("storage_bucket", ""),
            "storage_path": asset.get("storage_path", ""),
            "subject_tags": tags,
            "sale_stream_relevance": relevance,
            "quality_score": asset.get("quality_score"),
            "privacy_risk": privacy_risk,
            "selection_score": max(0, min(score, 160)),
            "public_use_approved": bool(asset.get("effective_public_use_approved") or asset.get("public_use_approved")),
            "why": _asset_why(tags, relevance, media_type, privacy_risk),
        })
    return sorted(ranked, key=lambda item: (-item["selection_score"], item["asset_id"]))[:12]


def _channel_asset_pairings(drafts, ranked_assets, fallback_channel="campaign"):
    pairings = []
    for draft in drafts:
        best = _best_asset_for_draft(draft, ranked_assets)
        pairings.append({
            "draft_id": draft.get("id", ""),
            "draft_label": draft.get("label") or draft.get("id", ""),
            "channel": draft.get("channel") or fallback_channel,
            "intent": draft.get("intent", ""),
            "recommended_asset_id": best.get("asset_id", "") if best else "",
            "recommended_asset_title": best.get("title", "") if best else "",
            "selection_reason": _selection_reason(draft, best),
            "requires_owner_final_selection": True,
        })
    return pairings


def _best_asset_for_draft(draft, ranked_assets):
    if not ranked_assets:
        return {}
    text = f"{draft.get('channel', '')} {draft.get('intent', '')} {draft.get('text', '')}".lower()
    best_asset = ranked_assets[0]
    best_score = -1
    for asset in ranked_assets:
        score = asset.get("selection_score", 0)
        tags = " ".join(asset.get("subject_tags", [])).lower()
        if "story" in text and asset.get("media_type") in ("image", "video"):
            score += 8
        if "family" in text and "family" in tags:
            score += 10
        if "set a" in text and ("set a" in tags or "freezer" in tags):
            score += 10
        if "facebook" in text and asset.get("media_type") == "image":
            score += 5
        if score > best_score:
            best_asset = asset
            best_score = score
    return best_asset


def _selection_reason(draft, asset):
    if not asset:
        return "No owner-approved media asset is available yet. Draft can stay text-only until media is approved."
    return f"Matches {draft.get('label') or draft.get('id')} because it is approved for public-use review, scored {asset.get('selection_score')}, and is tagged {', '.join(asset.get('subject_tags') or ['general'])}."


def _asset_why(tags, relevance, media_type, privacy_risk):
    parts = [f"{media_type or 'unknown'} media"]
    if relevance:
        parts.append(f"relevant to {', '.join(relevance)}")
    if tags:
        parts.append(f"tagged {', '.join(tags[:4])}")
    parts.append(f"privacy risk {privacy_risk}")
    return "; ".join(parts)


def _asset_status(asset):
    return _clean_text(asset.get("effective_approval_status") or asset.get("approval_status")).lower()


def _asset_list(value):
    if isinstance(value, list):
        return [_clean_text(item).lower() for item in value if _clean_text(item)]
    if isinstance(value, str):
        return [_clean_text(item).lower() for item in value.split(",") if _clean_text(item)]
    return []


def _safe_int(value, default=0):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _find_draft(packet, draft_id):
    for group in ("channel_drafts", "story_updates"):
        for draft in packet.get(group, []):
            if draft.get("id") == draft_id:
                return draft
    return {}


def _find_asset(assets, asset_id):
    if not asset_id:
        return {}
    for asset in assets:
        if asset.get("asset_id") == asset_id:
            return asset
    return {}


def _publish_packet_id(draft_id, asset_id, channel, pilot_cap):
    seed = "|".join([draft_id or "draft", asset_id or "text-only", channel or "channel", pilot_cap or "cap"])
    total = 0
    for char in seed:
        total = (total * 33 + ord(char)) % 0xFFFFFFFF
    return f"BEACON-PUBLISH-PACKET-{total:08X}"


def _manual_post_params(payload):
    metrics = _metrics(payload)
    posted_at = _clean_text(payload.get("posted_at"))[:80]
    params = {
        "manual_post_event_id": _clean_text(payload.get("manual_post_event_id"))[:120],
        "mode": "beacon_manual_public_post_evidence_only",
        "publish_packet_id": _clean_text(payload.get("publish_packet_id"))[:120],
        "channel": _clean_text(payload.get("channel"))[:80],
        "post_url": _clean_text(payload.get("post_url"))[:700],
        "posted_at": posted_at or None,
        "posted_by": _clean_text(payload.get("posted_by") or "owner_manual_post")[:120],
        "campaign_label": _clean_text(payload.get("campaign_label"))[:160],
        "evidence_notes": _clean_text(payload.get("evidence_notes") or payload.get("notes"))[:1200],
        "initial_metrics_json": json.dumps(metrics, sort_keys=True, default=str),
        **MANUAL_POST_AUTHORITY_FLAGS,
    }
    if not params["manual_post_event_id"]:
        params["manual_post_event_id"] = _manual_post_event_id(params)
    return params


def _metrics(payload):
    metrics = {}
    for key in ("reactions", "comments", "shares", "messages", "leads"):
        value = _safe_int(payload.get(key), 0)
        if value:
            metrics[key] = max(0, value)
    return metrics


def _public_manual_post_event(params):
    return {
        "manual_post_event_id": params.get("manual_post_event_id", ""),
        "mode": params.get("mode", "beacon_manual_public_post_evidence_only"),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "post_url": params.get("post_url", ""),
        "posted_at": params.get("posted_at") or "",
        "posted_by": params.get("posted_by", ""),
        "campaign_label": params.get("campaign_label", ""),
        "evidence_notes": params.get("evidence_notes", ""),
        "initial_metrics": _loads(params.get("initial_metrics_json"), {}),
        **MANUAL_POST_AUTHORITY_FLAGS,
    }


def _manual_post_row_to_event(row):
    return {
        "manual_post_event_id": row[0],
        "mode": "beacon_manual_public_post_evidence_only",
        "publish_packet_id": row[1],
        "channel": row[2],
        "post_url": row[3],
        "posted_at": row[4].isoformat() if hasattr(row[4], "isoformat") else str(row[4] or ""),
        "posted_by": row[5],
        "campaign_label": row[6],
        "evidence_notes": row[7],
        "initial_metrics": row[8] or {},
        "created_at": row[9].isoformat() if hasattr(row[9], "isoformat") else str(row[9] or ""),
        **MANUAL_POST_AUTHORITY_FLAGS,
    }


def _manual_post_event_id(params):
    seed = {
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "post_url": params.get("post_url", ""),
        "posted_at": params.get("posted_at", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:18].upper()
    return f"BEACON-MANUAL-POST-{digest}"


def _manual_post_unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "beacon_manual_public_post_evidence_only",
        "manual_post_events": [],
        "policy": manual_post_evidence_policy(),
        **MANUAL_POST_AUTHORITY_FLAGS,
    }


def _performance_params(payload):
    spend_amount = _safe_money(payload.get("spend_amount") or payload.get("spend"))
    messages = _safe_int(payload.get("messages_to_sam") or payload.get("messages"), 0)
    qualified = _safe_int(payload.get("qualified_buyer_leads") or payload.get("qualified_leads"), 0)
    recommendation = _recommend_boost(payload, spend_amount, messages, qualified)
    cost_per_message = _cost(spend_amount, messages)
    cost_per_qualified_lead = _cost(spend_amount, qualified)
    params = {
        "performance_event_id": _clean_text(payload.get("performance_event_id"))[:120],
        "mode": "beacon_campaign_performance_evidence_only",
        "manual_post_event_id": _clean_text(payload.get("manual_post_event_id"))[:120],
        "publish_packet_id": _clean_text(payload.get("publish_packet_id"))[:120],
        "channel": _clean_text(payload.get("channel") or "Facebook")[:80],
        "measurement_window": _clean_text(payload.get("measurement_window") or "manual_snapshot")[:120],
        "spend_amount": spend_amount,
        "spend_currency": _clean_text(payload.get("spend_currency") or "ZAR")[:12],
        "reach": _safe_int(payload.get("reach"), 0),
        "impressions": _safe_int(payload.get("impressions"), 0),
        "reactions": _safe_int(payload.get("reactions"), 0),
        "comments": _safe_int(payload.get("comments"), 0),
        "shares": _safe_int(payload.get("shares"), 0),
        "messages_to_sam": messages,
        "qualified_buyer_leads": qualified,
        "booking_review_requests": _safe_int(payload.get("booking_review_requests"), 0),
        "notes": _clean_text(payload.get("notes") or payload.get("performance_notes"))[:1200],
        "recommended_action": recommendation["recommended_action"],
        "recommendation_reason": recommendation["recommendation_reason"],
        "recommended_spend_amount": recommendation["recommended_spend_amount"],
        "recommended_duration_days": recommendation["recommended_duration_days"],
        "max_spend_cap_amount": BOOST_RECOMMENDATION_SPEND_CAP,
        "cost_per_message": cost_per_message,
        "cost_per_qualified_lead": cost_per_qualified_lead,
        "recorded_by": _clean_text(payload.get("recorded_by") or "beacon_performance_tracking")[:120],
        **PERFORMANCE_AUTHORITY_FLAGS,
    }
    params["recommends_boost"] = params["recommended_action"] == "light_boost_owner_review"
    if not params["performance_event_id"]:
        params["performance_event_id"] = _performance_event_id(params)
    return params


def _recommend_boost(payload, spend_amount, messages, qualified):
    fulfillment_risk = _clean_text(payload.get("fulfillment_risk")).lower()
    safety_risk = _clean_text(payload.get("safety_risk")).lower()
    owner_blocked = str(payload.get("owner_blocked") or "").strip().lower() in {"1", "true", "yes", "on"}
    requested_spend = _safe_money(payload.get("recommended_spend_amount"))
    if owner_blocked or fulfillment_risk in {"high", "blocked"} or safety_risk in {"high", "blocked"}:
        return {
            "recommended_action": "do_not_boost",
            "recommendation_reason": "Do not boost because fulfilment, owner, or safety risk is marked high.",
            "recommended_spend_amount": 0,
            "recommended_duration_days": 0,
        }
    if requested_spend > BOOST_RECOMMENDATION_SPEND_CAP:
        return {
            "recommended_action": "owner_review_required",
            "recommendation_reason": f"Requested spend exceeds the R{BOOST_RECOMMENDATION_SPEND_CAP} cap and needs owner review before any later paid action.",
            "recommended_spend_amount": BOOST_RECOMMENDATION_SPEND_CAP,
            "recommended_duration_days": _safe_int(payload.get("recommended_duration_days"), 3) or 3,
        }
    if qualified >= 1 or messages >= 2:
        spend = requested_spend or 150
        return {
            "recommended_action": "light_boost_owner_review",
            "recommendation_reason": "Recommend a light owner-reviewed boost because the post has early buyer-message evidence.",
            "recommended_spend_amount": min(spend, BOOST_RECOMMENDATION_SPEND_CAP),
            "recommended_duration_days": _safe_int(payload.get("recommended_duration_days"), 3) or 3,
        }
    if messages == 0 and qualified == 0 and spend_amount > 0:
        return {
            "recommended_action": "do_not_boost",
            "recommendation_reason": "Do not boost further because spend has not produced Sam messages or qualified buyer leads.",
            "recommended_spend_amount": 0,
            "recommended_duration_days": 0,
        }
    return {
        "recommended_action": "wait_for_more_data",
        "recommendation_reason": "Wait for more evidence before recommending paid boost.",
        "recommended_spend_amount": 0,
        "recommended_duration_days": 0,
    }


def _boost_packet(params):
    if not params:
        return {}
    return {
        "success": True,
        "mode": "beacon_boost_recommendation_owner_review_only",
        "agent": "Beacon",
        "alias": "Prisma/Beacon",
        "performance_event_id": params.get("performance_event_id", ""),
        "manual_post_event_id": params.get("manual_post_event_id", ""),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "recommended_action": params.get("recommended_action", "wait_for_more_data"),
        "recommendation_reason": params.get("recommendation_reason", ""),
        "recommended_spend_amount": params.get("recommended_spend_amount", 0),
        "recommended_duration_days": params.get("recommended_duration_days", 0),
        "max_spend_cap_amount": params.get("max_spend_cap_amount", BOOST_RECOMMENDATION_SPEND_CAP),
        "currency": params.get("spend_currency", "ZAR"),
        "primary_metrics": {
            "messages_to_sam": params.get("messages_to_sam", 0),
            "qualified_buyer_leads": params.get("qualified_buyer_leads", 0),
            "cost_per_message": params.get("cost_per_message"),
            "cost_per_qualified_lead": params.get("cost_per_qualified_lead"),
        },
        "approval_status": "owner_review_required" if params.get("recommended_action") in {"light_boost_owner_review", "owner_review_required"} else "no_paid_action_requested",
        "approval_executes_boost": False,
        "calls_meta_now": False,
        "spends_money_now": False,
        "owner_review_checklist": [
            "Check that Sam can handle more messages from this post.",
            "Check that meat stock, carcass reservations, delivery, and fulfilment capacity can absorb the extra demand.",
            "Confirm the spend amount stays within the R500 test cap.",
            "Use this as recommendation evidence only; no Facebook/Meta boost is executed here.",
        ],
        "next_gate": "owner_approves_boost_packet_before_any_future_meta_ads_execution",
        **PERFORMANCE_AUTHORITY_FLAGS,
        "recommends_boost": params.get("recommended_action") == "light_boost_owner_review",
    }


def _public_performance_event(params):
    return {
        "performance_event_id": params.get("performance_event_id", ""),
        "mode": params.get("mode", "beacon_campaign_performance_evidence_only"),
        "manual_post_event_id": params.get("manual_post_event_id", ""),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "measurement_window": params.get("measurement_window", ""),
        "spend_amount": params.get("spend_amount", 0),
        "spend_currency": params.get("spend_currency", "ZAR"),
        "reach": params.get("reach", 0),
        "impressions": params.get("impressions", 0),
        "reactions": params.get("reactions", 0),
        "comments": params.get("comments", 0),
        "shares": params.get("shares", 0),
        "messages_to_sam": params.get("messages_to_sam", 0),
        "qualified_buyer_leads": params.get("qualified_buyer_leads", 0),
        "booking_review_requests": params.get("booking_review_requests", 0),
        "notes": params.get("notes", ""),
        "recommended_action": params.get("recommended_action", ""),
        "recommendation_reason": params.get("recommendation_reason", ""),
        "recommended_spend_amount": params.get("recommended_spend_amount", 0),
        "recommended_duration_days": params.get("recommended_duration_days", 0),
        "max_spend_cap_amount": params.get("max_spend_cap_amount", BOOST_RECOMMENDATION_SPEND_CAP),
        "cost_per_message": params.get("cost_per_message"),
        "cost_per_qualified_lead": params.get("cost_per_qualified_lead"),
        "recorded_by": params.get("recorded_by", ""),
        **PERFORMANCE_AUTHORITY_FLAGS,
        "recommends_boost": params.get("recommended_action") == "light_boost_owner_review",
    }


def _performance_row_to_event(row):
    return {
        "performance_event_id": row[0],
        "mode": "beacon_campaign_performance_evidence_only",
        "manual_post_event_id": row[1],
        "publish_packet_id": row[2],
        "channel": row[3],
        "measurement_window": row[4],
        "spend_amount": float(row[5] or 0),
        "spend_currency": row[6],
        "reach": row[7],
        "impressions": row[8],
        "reactions": row[9],
        "comments": row[10],
        "shares": row[11],
        "messages_to_sam": row[12],
        "qualified_buyer_leads": row[13],
        "booking_review_requests": row[14],
        "notes": row[15],
        "recommended_action": row[16],
        "recommendation_reason": row[17],
        "recommended_spend_amount": float(row[18] or 0),
        "recommended_duration_days": row[19],
        "max_spend_cap_amount": float(row[20] or BOOST_RECOMMENDATION_SPEND_CAP),
        "cost_per_message": float(row[21]) if row[21] is not None else None,
        "cost_per_qualified_lead": float(row[22]) if row[22] is not None else None,
        "recommends_boost": bool(row[23]),
        "recorded_by": row[24],
        "created_at": row[25].isoformat() if hasattr(row[25], "isoformat") else str(row[25] or ""),
        **PERFORMANCE_AUTHORITY_FLAGS,
    }


def _event_to_performance_params(event):
    event = event if isinstance(event, dict) else {}
    params = dict(event)
    params.setdefault("max_spend_cap_amount", BOOST_RECOMMENDATION_SPEND_CAP)
    params.setdefault("spend_currency", "ZAR")
    params.setdefault("recommended_action", "wait_for_more_data")
    params.setdefault("recommendation_reason", "")
    params.setdefault("recommended_spend_amount", 0)
    params.setdefault("recommended_duration_days", 0)
    return params


def _performance_event_id(params):
    seed = {
        "manual_post_event_id": params.get("manual_post_event_id", ""),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "measurement_window": params.get("measurement_window", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:18].upper()
    return f"BEACON-PERF-{digest}"


def _performance_unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "beacon_campaign_performance_evidence_only",
        "performance_events": [],
        **PERFORMANCE_AUTHORITY_FLAGS,
    }


def _facebook_execution_authority(executed):
    return {
        **PERFORMANCE_AUTHORITY_FLAGS,
        "draft_only": False,
        "posts_publicly": bool(executed),
        "calls_meta": bool(executed),
        "customer_public_output_enabled": bool(executed),
        "boosts_post": False,
        "spends_money": False,
        "sends_customer_message": False,
    }


def _facebook_post_params(payload, policy):
    selected_asset = payload.get("selected_asset") if isinstance(payload.get("selected_asset"), dict) else {}
    params = {
        "execution_event_id": _clean_text(payload.get("execution_event_id"))[:120],
        "mode": "beacon_facebook_page_post_execution_gate",
        "publish_packet_id": _clean_text(payload.get("publish_packet_id"))[:120],
        "channel": _clean_text(payload.get("channel") or "Facebook")[:80],
        "exact_text": _clean_text(payload.get("exact_text") or payload.get("message"))[:5000],
        "asset_id": _clean_text(payload.get("asset_id") or selected_asset.get("asset_id"))[:120],
        "selected_asset": selected_asset,
        "selected_media_json": "{}",
        "post_kind": "photo" if _clean_text(payload.get("asset_id") or selected_asset.get("asset_id")) else "feed",
        "owner_confirmation": _clean_text(payload.get("owner_confirmation"))[:120],
        "execution_status": "not_attempted",
        "facebook_post_id": "",
        "facebook_response_json": "{}",
        "recorded_by": _clean_text(payload.get("recorded_by") or "beacon_facebook_post_execution_gate")[:120],
        "policy_enabled": bool(policy.get("enabled")),
        "page_id_configured": bool(policy.get("page_id_configured")),
        "page_access_token_configured": bool(policy.get("page_access_token_configured")),
    }
    if params["asset_id"]:
        params["selected_media_json"] = json.dumps(_facebook_selected_media(params), sort_keys=True, default=str)
    if not params["execution_event_id"]:
        params["execution_event_id"] = _facebook_post_execution_id(params)
    return params


def _facebook_post_validation_error(params, policy):
    if not params.get("publish_packet_id"):
        return "publish_packet_id_required"
    if not params.get("exact_text"):
        return "exact_text_required"
    if params.get("asset_id"):
        asset = params.get("selected_asset") if isinstance(params.get("selected_asset"), dict) else {}
        if not asset:
            return "selected_image_asset_required"
        if asset.get("media_type") != "image":
            return "selected_asset_must_be_image"
        if not (asset.get("effective_public_use_approved") or asset.get("public_use_approved")):
            return "selected_image_asset_not_public_use_approved"
        if not asset.get("storage_bucket") or not asset.get("storage_path"):
            return "selected_image_asset_storage_missing"
        if not policy.get("media_storage_configured"):
            return "facebook_image_posting_storage_not_configured"
    if params.get("owner_confirmation") != FACEBOOK_POST_CONFIRMATION_PHRASE:
        return "owner_confirmation_required"
    if "facebook" not in params.get("channel", "").lower():
        return "channel_not_facebook"
    if not policy.get("enabled"):
        return "facebook_posting_disabled"
    if not policy.get("page_id_configured") or not policy.get("page_access_token_configured"):
        return "facebook_page_credentials_missing"
    return ""


def _post_to_facebook_page(params, policy, environ=None):
    if params.get("asset_id"):
        return _post_to_facebook_page_photos(params, policy, environ=environ)
    return _post_to_facebook_page_feed(params, policy, environ=environ)


def _post_to_facebook_page_feed(params, policy, environ=None):
    source = environ if environ is not None else os.environ
    page_id = _clean_text(source.get(FACEBOOK_PAGE_ID_ENV))
    token = _clean_text(source.get(FACEBOOK_PAGE_ACCESS_TOKEN_ENV))
    version = _clean_text(source.get(FACEBOOK_GRAPH_VERSION_ENV)) or "v23.0"
    if not page_id or not token:
        return {"success": False, "status": "facebook_page_credentials_missing"}, 503
    endpoint = f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/{urllib_parse.quote(page_id, safe='')}/feed"
    body = urllib_parse.urlencode({
        "message": params.get("exact_text", ""),
        "access_token": token,
    }).encode("utf-8")
    req = urllib_request.Request(endpoint, data=body, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=25) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw or "{}")
            return {"success": True, **payload}, response.status
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status": "facebook_http_error",
            "http_status": exc.code,
            "error": raw[:500],
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "status": "facebook_post_request_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
        }, 502


def _post_to_facebook_page_photos(params, policy, environ=None):
    source = environ if environ is not None else os.environ
    page_id = _clean_text(source.get(FACEBOOK_PAGE_ID_ENV))
    token = _clean_text(source.get(FACEBOOK_PAGE_ACCESS_TOKEN_ENV))
    version = _clean_text(source.get(FACEBOOK_GRAPH_VERSION_ENV)) or "v23.0"
    if not page_id or not token:
        return {"success": False, "status": "facebook_page_credentials_missing"}, 503
    signed_url_result, signed_url_status = _signed_supabase_media_url(params, environ=source)
    if signed_url_status >= 400:
        return signed_url_result, signed_url_status
    endpoint = f"https://graph.facebook.com/{urllib_parse.quote(version, safe='')}/{urllib_parse.quote(page_id, safe='')}/photos"
    body = urllib_parse.urlencode({
        "caption": params.get("exact_text", ""),
        "url": signed_url_result.get("signed_url", ""),
        "access_token": token,
    }).encode("utf-8")
    req = urllib_request.Request(endpoint, data=body, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=35) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw or "{}")
            return {
                "success": True,
                "post_kind": "photo",
                "selected_media": _facebook_selected_media(params),
                **payload,
            }, response.status
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status": "facebook_http_error",
            "http_status": exc.code,
            "post_kind": "photo",
            "selected_media": _facebook_selected_media(params),
            "error": raw[:500],
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "status": "facebook_photo_post_request_failed",
            "post_kind": "photo",
            "selected_media": _facebook_selected_media(params),
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
        }, 502


def _signed_supabase_media_url(params, environ=None):
    source = environ if environ is not None else os.environ
    url = _clean_text(source.get(SUPABASE_URL_ENV)).rstrip("/")
    key = _clean_text(source.get(SUPABASE_SERVICE_ROLE_KEY_ENV))
    asset = params.get("selected_asset") if isinstance(params.get("selected_asset"), dict) else {}
    bucket = _clean_text(asset.get("storage_bucket"))
    storage_path = str(asset.get("storage_path") or "").strip().replace("\\", "/")
    if not url or not key:
        return {"success": False, "status": "supabase_storage_not_configured_for_facebook_image"}, 503
    if not bucket or not storage_path:
        return {"success": False, "status": "selected_image_asset_storage_missing"}, 400
    endpoint = f"{url}/storage/v1/object/sign/{urllib_parse.quote(bucket, safe='')}/{urllib_parse.quote(storage_path, safe='/')}"
    body = json.dumps({"expiresIn": 3600}).encode("utf-8")
    req = urllib_request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {key}",
            "apikey": key,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8")
            payload = json.loads(raw or "{}")
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {
            "success": False,
            "status": "supabase_signed_url_failed",
            "http_status": exc.code,
            "error": raw[:500],
        }, exc.code
    except (urllib_error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "status": "supabase_signed_url_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
        }, 503
    signed = payload.get("signedURL") or payload.get("signedUrl") or payload.get("signed_url") or ""
    if signed and signed.startswith("/"):
        signed = f"{url}{signed}"
    return {
        "success": bool(signed),
        "status": "supabase_signed_url_created" if signed else "supabase_signed_url_missing",
        "signed_url": signed,
        "selected_media": _facebook_selected_media(params),
    }, 200 if signed else 502


def _record_facebook_post_execution_event(params, database_url=None):
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _facebook_post_unavailable("not_configured", False), 503
    try:
        import psycopg
    except ImportError:
        return _facebook_post_unavailable("dependency_missing", True), 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.beacon_facebook_post_execution_events (
                        execution_event_id, mode, publish_packet_id, channel, exact_text,
                        owner_confirmation, execution_status, facebook_post_id,
                        facebook_response_json, records_evidence,
                        owner_exact_confirmation_required, sends_customer_message,
                        posts_publicly, calls_chatwoot, calls_meta, calls_n8n,
                        boosts_post, spends_money, creates_quote, creates_invoice,
                        creates_order, changes_stock, reserves_stock, dispatch_enabled,
                        changes_runtime_now, changes_prompt_now, physical_controls_enabled,
                        customer_public_output_enabled, writes_farm_data, recorded_by
                    )
                    values (
                        %(execution_event_id)s, %(mode)s, %(publish_packet_id)s,
                        %(channel)s, %(exact_text)s, %(owner_confirmation)s,
                        %(execution_status)s, %(facebook_post_id)s,
                        %(facebook_response_json)s::jsonb, true, true, false,
                        true, false, true, false, false, false, false, false,
                        false, false, false, false, false, false, false,
                        true, false, %(recorded_by)s
                    )
                    on conflict (execution_event_id) do nothing
                    """,
                    params,
                )
                created_count = cursor.rowcount
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "beacon_facebook_post_execution_write_failed",
            "error_type": exc.__class__.__name__,
            "error": str(exc)[:240],
            "execution_event": _public_facebook_post_event(params),
            **_facebook_execution_authority(False),
        }, 500
    return {
        "success": True,
        "configured": True,
        "status": "beacon_facebook_post_execution_recorded" if created_count else "beacon_facebook_post_execution_already_recorded",
        "created_count": created_count,
        "execution_event_id": params["execution_event_id"],
        "execution_event": _public_facebook_post_event(params),
        **_facebook_execution_authority(False),
    }, 201 if created_count else 200


def _public_facebook_post_event(params):
    return {
        "execution_event_id": params.get("execution_event_id", ""),
        "mode": params.get("mode", "beacon_facebook_page_post_execution_gate"),
        "publish_packet_id": params.get("publish_packet_id", ""),
        "channel": params.get("channel", ""),
        "exact_text": params.get("exact_text", ""),
        "owner_confirmation": params.get("owner_confirmation", ""),
        "execution_status": params.get("execution_status", ""),
        "facebook_post_id": params.get("facebook_post_id", ""),
        "facebook_response": _loads(params.get("facebook_response_json"), {}),
        "post_kind": params.get("post_kind", "feed"),
        "selected_media": _loads(params.get("selected_media_json"), {}),
        **_facebook_execution_authority(params.get("execution_status") == "facebook_page_post_sent"),
    }


def _facebook_post_row_to_event(row):
    return {
        "execution_event_id": row[0],
        "mode": "beacon_facebook_page_post_execution_gate",
        "publish_packet_id": row[1],
        "channel": row[2],
        "exact_text": row[3],
        "owner_confirmation": row[4],
        "execution_status": row[5],
        "facebook_post_id": row[6],
        "facebook_response": row[7] or {},
        "post_kind": (row[7] or {}).get("post_kind", "feed") if isinstance(row[7], dict) else "feed",
        "selected_media": (row[7] or {}).get("selected_media", {}) if isinstance(row[7], dict) else {},
        "created_at": row[8].isoformat() if hasattr(row[8], "isoformat") else str(row[8] or ""),
        **_facebook_execution_authority(row[5] == "facebook_page_post_sent"),
    }


def _facebook_post_execution_id(params):
    seed = {
        "publish_packet_id": params.get("publish_packet_id", ""),
        "exact_text": params.get("exact_text", ""),
        "asset_id": params.get("asset_id", ""),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    digest = hashlib.sha256(json.dumps(seed, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:18].upper()
    return f"BEACON-FB-POST-{digest}"


def _facebook_post_unavailable(status, configured):
    return {
        "success": False,
        "configured": configured,
        "status": status,
        "mode": "beacon_facebook_page_post_execution_gate",
        "execution_events": [],
        **_facebook_execution_authority(False),
    }


def _facebook_selected_media(params):
    asset = params.get("selected_asset") if isinstance(params.get("selected_asset"), dict) else {}
    if not asset and not params.get("asset_id"):
        return {}
    return {
        "asset_id": params.get("asset_id") or asset.get("asset_id", ""),
        "title": asset.get("title", ""),
        "media_type": asset.get("media_type", ""),
        "mime_type": asset.get("mime_type", ""),
        "storage_bucket": asset.get("storage_bucket", ""),
        "storage_path": asset.get("storage_path", ""),
        "privacy_risk": asset.get("privacy_risk", ""),
        "quality_score": asset.get("quality_score"),
        "public_use_approved": bool(asset.get("effective_public_use_approved") or asset.get("public_use_approved")),
    }


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _safe_money(value, default=0):
    try:
        return round(max(0, float(value)), 2)
    except (TypeError, ValueError):
        return default


def _cost(spend, count):
    if not count:
        return None
    return round(float(spend or 0) / int(count), 2)


def _loads(value, fallback):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _all_draft_texts(packet):
    drafts = []
    for group in ("channel_drafts", "story_updates"):
        for draft in packet.get(group, []):
            drafts.append({"id": draft.get("id", ""), "text": draft.get("text", "")})
    return drafts


def _has_preorder_signal(text):
    return "preorder" in text or "pre-book" in text or "pre booked" in text


def _has_forbidden_promise(text):
    forbidden = [
        "available now",
        "order confirmed",
        "booking confirmed",
        "guaranteed",
        "deposit confirmed",
        "payment confirmed",
        "slaughter booked",
        "butcher booked",
        "free delivery",
        "final price",
        "fixed delivery date",
    ]
    return any(term in text for term in forbidden)


def _clean_text(value):
    return " ".join(str(value or "").strip().split())
