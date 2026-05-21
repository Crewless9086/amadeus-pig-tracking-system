import os
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


def _source_metadata():
    return {
        "source": "supabase",
        "writes_to_sheets": False,
        "writes_to_supabase": False,
    }
