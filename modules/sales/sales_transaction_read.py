import os
from datetime import date
from decimal import Decimal

from services.database_service import DATABASE_URL_ENV


ALLOWED_SALE_STREAMS = {"Livestock", "Slaughter", "Meat"}
DEFAULT_LIMIT = 50
MAX_LIMIT = 100


def list_sales_transactions(sale_stream="", limit=DEFAULT_LIMIT, database_url=None):
    sale_stream = str(sale_stream or "").strip()
    limit = _clean_limit(limit)

    if sale_stream and sale_stream not in ALLOWED_SALE_STREAMS:
        raise ValueError("sale_stream must be Livestock, Slaughter, or Meat.")

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
            "source": _source_metadata(),
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
            "source": _source_metadata(),
        }, 500

    where_clause = ""
    params = []
    if sale_stream:
        where_clause = "where st.sale_stream = %s"
        params.append(sale_stream)
    params.append(limit)

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                rows = _fetch_all_dicts(
                    cursor,
                    f"""
                    select
                        st.sale_id,
                        st.sale_date,
                        st.sale_stream,
                        st.buyer_name,
                        st.destination,
                        st.linked_order_id,
                        st.pig_count,
                        st.gross_total,
                        st.deductions_total,
                        st.net_total,
                        st.currency,
                        st.payment_status,
                        st.payment_method,
                        st.sale_status,
                        st.created_at,
                        count(sti.sale_item_id)::int as item_count
                    from public.sales_transactions st
                    left join public.sales_transaction_items sti on sti.sale_id = st.sale_id
                    {where_clause}
                    group by st.sale_id
                    order by st.sale_date desc, st.sale_id desc
                    limit %s
                    """,
                    tuple(params),
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_transaction_read_failed",
            "message": "Sales transaction read failed.",
            "error_type": exc.__class__.__name__,
            "source": _source_metadata(),
        }, 503

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "count": len(rows),
        "limit": limit,
        "sale_stream": sale_stream or None,
        "sales_transactions": [_json_safe_row(row) for row in rows],
        "source": _source_metadata(),
    }, 200


def get_monthly_sales_transaction_summary(report_date=None, database_url=None):
    selected_date = _parse_report_date(report_date)
    month_start = selected_date.replace(day=1)
    next_month = date(month_start.year + (month_start.month // 12), (month_start.month % 12) + 1, 1)

    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {
            "success": False,
            "configured": False,
            "status": "not_configured",
            "message": f"{DATABASE_URL_ENV} is not configured.",
            "report_month": month_start.isoformat()[:7],
            "streams": _empty_stream_summary(),
            "totals": _empty_totals(),
            "source": _source_metadata(),
        }, 503

    try:
        import psycopg
    except ImportError:
        return {
            "success": False,
            "configured": True,
            "status": "dependency_missing",
            "message": "Python database dependency is not installed.",
            "report_month": month_start.isoformat()[:7],
            "streams": _empty_stream_summary(),
            "totals": _empty_totals(),
            "source": _source_metadata(),
        }, 500

    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                rows = _fetch_all_dicts(
                    cursor,
                    """
                    with item_counts as (
                        select sale_id, count(*)::int as item_count
                        from public.sales_transaction_items
                        group by sale_id
                    )
                    select
                        st.sale_stream,
                        count(*)::int as transaction_count,
                        coalesce(sum(st.pig_count), 0)::int as pig_count,
                        coalesce(sum(st.gross_total), 0)::numeric(12, 2) as gross_total,
                        coalesce(sum(st.net_total), 0)::numeric(12, 2) as net_total,
                        coalesce(sum(item_counts.item_count), 0)::int as item_count
                    from public.sales_transactions st
                    left join item_counts on item_counts.sale_id = st.sale_id
                    where st.sale_date >= %s
                      and st.sale_date < %s
                      and st.sale_status <> 'Cancelled'
                    group by st.sale_stream
                    """,
                    (month_start, next_month),
                )
    except Exception as exc:
        return {
            "success": False,
            "configured": True,
            "status": "sales_transaction_summary_failed",
            "message": "Monthly sales transaction summary read failed.",
            "error_type": exc.__class__.__name__,
            "report_month": month_start.isoformat()[:7],
            "streams": _empty_stream_summary(),
            "totals": _empty_totals(),
            "source": _source_metadata(),
        }, 503

    streams = _empty_stream_summary()
    for row in rows:
        stream_key = str(row.get("sale_stream", "")).strip().lower()
        if stream_key not in streams:
            continue
        streams[stream_key] = {
            "transaction_count": int(row.get("transaction_count") or 0),
            "pig_count": int(row.get("pig_count") or 0),
            "item_count": int(row.get("item_count") or 0),
            "gross_total": _json_safe_value(row.get("gross_total")) or 0.0,
            "net_total": _json_safe_value(row.get("net_total")) or 0.0,
        }

    totals = {
        "transaction_count": sum(stream["transaction_count"] for stream in streams.values()),
        "pig_count": sum(stream["pig_count"] for stream in streams.values()),
        "item_count": sum(stream["item_count"] for stream in streams.values()),
        "gross_total": round(sum(float(stream["gross_total"] or 0) for stream in streams.values()), 2),
        "net_total": round(sum(float(stream["net_total"] or 0) for stream in streams.values()), 2),
    }

    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "report_month": month_start.isoformat()[:7],
        "streams": streams,
        "totals": totals,
        "source": _source_metadata(),
    }, 200


def _clean_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    if limit < 1:
        return DEFAULT_LIMIT
    return min(limit, MAX_LIMIT)


def _fetch_all_dicts(cursor, query, params):
    cursor.execute(query, params)
    columns = [column[0] for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _json_safe_row(row):
    return {
        key: _json_safe_value(value)
        for key, value in row.items()
    }


def _json_safe_value(value):
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def _parse_report_date(value):
    if not value:
        return date.today()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _empty_stream_summary():
    return {
        "livestock": _empty_stream_values(),
        "slaughter": _empty_stream_values(),
        "meat": _empty_stream_values(),
    }


def _empty_stream_values():
    return {
        "transaction_count": 0,
        "pig_count": 0,
        "item_count": 0,
        "gross_total": 0.0,
        "net_total": 0.0,
    }


def _empty_totals():
    return {
        "transaction_count": 0,
        "pig_count": 0,
        "item_count": 0,
        "gross_total": 0.0,
        "net_total": 0.0,
    }


def _source_metadata():
    return {
        "source": "supabase",
        "writes_to_sheets": False,
        "writes_to_supabase": False,
    }
