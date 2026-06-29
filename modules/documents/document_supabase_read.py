import os
from datetime import date, datetime

from services.database_service import DATABASE_URL_ENV


def supabase_document_reads_available():
    return bool(os.getenv(DATABASE_URL_ENV, "").strip())


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _fetch_all(sql, params=(), connect_factory=None):
    if not supabase_document_reads_available() and connect_factory is None:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not configured.")
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set transaction read only")
            cursor.execute(sql, params)
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _text(value):
    return "" if value is None else str(value).strip()


def _date_text(value):
    if isinstance(value, datetime):
        return value.strftime("%d %b %Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d %b %Y")
    return _text(value)


def _number_text(value):
    if value is None:
        return ""
    return str(value)


def _document_record(row):
    return {
        "Document_ID": _text(row.get("document_id")),
        "Order_ID": _text(row.get("order_id")),
        "Document_Type": _text(row.get("document_type")),
        "Document_Ref": _text(row.get("document_ref")),
        "Payment_Ref": _text(row.get("payment_ref")),
        "Version": _number_text(row.get("version")),
        "Document_Status": _text(row.get("document_status")),
        "Payment_Method": _text(row.get("payment_method")),
        "VAT_Rate": _number_text(row.get("vat_rate")),
        "Subtotal_Ex_VAT": _number_text(row.get("subtotal_ex_vat")),
        "VAT_Amount": _number_text(row.get("vat_amount")),
        "Total": _number_text(row.get("total")),
        "Valid_Until": _date_text(row.get("valid_until")),
        "Google_Drive_File_ID": _text(row.get("google_drive_file_id")),
        "Google_Drive_URL": _text(row.get("google_drive_url")),
        "File_Name": _text(row.get("file_name")),
        "Created_At": _date_text(row.get("created_at")),
        "Created_By": _text(row.get("created_by")),
        "Sent_At": _date_text(row.get("sent_at")),
        "Sent_By": _text(row.get("sent_by")),
        "Notes": _text(row.get("notes")),
    }


def get_order_documents(order_id, document_type=None, connect_factory=None):
    order_id = _text(order_id)
    document_type = _text(document_type)
    if not order_id:
        return []

    params = [order_id]
    type_clause = ""
    if document_type:
        type_clause = "and document_type = %s"
        params.append(document_type)

    rows = _fetch_all(
        f"""
        select *
        from public.order_documents
        where order_id = %s
        {type_clause}
        order by version desc, created_at desc, document_id desc
        """,
        tuple(params),
        connect_factory=connect_factory,
    )
    return [_document_record(row) for row in rows]


def get_order_document(document_id, connect_factory=None):
    document_id = _text(document_id)
    if not document_id:
        return None

    rows = _fetch_all(
        """
        select *
        from public.order_documents
        where document_id = %s
        """,
        (document_id,),
        connect_factory=connect_factory,
    )
    return _document_record(rows[0]) if rows else None
