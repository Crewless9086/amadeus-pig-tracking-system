"""Canonical, read-only evidence adapter for the Beacon-to-SAM projection."""

import os

from modules.beacon.sam_attribution import build_beacon_sam_attribution
from services.database_service import DATABASE_URL_ENV


def get_beacon_sam_attribution(limit=100, database_url=None):
    """Read canonical evidence and build the deterministic attribution projection.

    This adapter intentionally performs no writes and does not accept browser-supplied
    evidence.  Missing or unavailable canonical sources fail closed.
    """
    try:
        parsed_limit = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        parsed_limit = 100
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
                payload = {
                    "campaign_events": _fetch(cursor, """
                        select performance_event_id, manual_post_event_id, publish_packet_id,
                               channel as campaign_source, created_at as observed_at
                        from public.beacon_campaign_performance_events
                        order by created_at desc, performance_event_id desc limit %s
                    """, (parsed_limit,)),
                    "leads": _fetch(cursor, """
                        select lead_id, campaign_id, campaign_source, status, linked_order_id,
                               created_at, last_inbound_at
                        from public.oom_sakkie_sales_leads
                        order by created_at desc, lead_id desc limit %s
                    """, (parsed_limit,)),
                    "orders": _fetch(cursor, """
                        select order_id, order_status as status
                        from public.orders order by created_at desc, order_id desc limit %s
                    """, (parsed_limit,)),
                    "sales_transactions": _fetch(cursor, """
                        select sale_id, linked_order_id, sale_status, payment_status,
                               net_total, currency
                        from public.sales_transactions
                        order by created_at desc, sale_id desc limit %s
                    """, (parsed_limit,)),
                    "fulfilment_events": _fetch(cursor, """
                        select fulfillment_event_id, lead_id, event_type, created_at as occurred_at
                        from public.oom_sakkie_meat_fulfillment_events
                        order by created_at desc, fulfillment_event_id desc limit %s
                    """, (parsed_limit,)),
                    # Loss reasons have no canonical controlled-code store yet.  The projection
                    # deliberately leaves lost reasons unknown instead of inferring free text.
                    "loss_events": [],
                }
    except Exception as exc:
        return _unavailable("canonical_attribution_read_failed", configured=True, error_type=exc.__class__.__name__), 503

    result = build_beacon_sam_attribution(payload)
    result["source"] = "supabase_canonical_append_only_records"
    result["configured"] = True
    return result, 200 if result.get("success") else 409


def _fetch(cursor, query, params):
    cursor.execute(query, params)
    columns = [column[0] for column in cursor.description]
    return [_json_row(dict(zip(columns, row))) for row in cursor.fetchall()]


def _json_row(row):
    return {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}


def _unavailable(status, configured, error_type=""):
    return {
        "success": False,
        "status": status,
        "configured": configured,
        "mode": "beacon_sam_attribution_read_only",
        "attributions": [],
        "summary": {"attributed": 0, "ambiguous": 0, "unmatched": 0, "qualified": 0, "lost": 0},
        "authority": {"read_only": True, "posts_publicly": False, "spends_money": False, "creates_order": False, "changes_stock": False},
        **({"error_type": error_type} if error_type else {}),
    }
