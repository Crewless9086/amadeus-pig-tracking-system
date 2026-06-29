import os
import sys
from datetime import date, datetime

from services.database_service import DATABASE_URL_ENV


DOCUMENT_FIELD_MAP = {
    "Document_ID": "document_id",
    "Order_ID": "order_id",
    "Document_Type": "document_type",
    "Document_Ref": "document_ref",
    "Payment_Ref": "payment_ref",
    "Version": "version",
    "Document_Status": "document_status",
    "Payment_Method": "payment_method",
    "VAT_Rate": "vat_rate",
    "Subtotal_Ex_VAT": "subtotal_ex_vat",
    "VAT_Amount": "vat_amount",
    "Total": "total",
    "Valid_Until": "valid_until",
    "Google_Drive_File_ID": "google_drive_file_id",
    "Google_Drive_URL": "google_drive_url",
    "File_Name": "file_name",
    "Created_At": "created_at",
    "Created_By": "created_by",
    "Sent_At": "sent_at",
    "Sent_By": "sent_by",
    "Notes": "notes",
}

NUMERIC_FIELDS = {"VAT_Rate", "Subtotal_Ex_VAT", "VAT_Amount", "Total"}
INTEGER_FIELDS = {"Version"}
DATE_FIELDS = {"Valid_Until"}
TIMESTAMP_FIELDS = {"Created_At", "Sent_At"}


def supabase_document_writes_available():
    if "unittest" in sys.modules and os.getenv("ALLOW_SUPABASE_WRITES_IN_TESTS", "") != "1":
        return False
    return bool(os.getenv(DATABASE_URL_ENV, "").strip())


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _clean(value):
    return "" if value is None else str(value).strip()


def _date_or_none(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _timestamp_or_none(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, datetime.min.time())
    text = _clean(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%d %b %Y %H:%M", "%d %B %Y %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _number_or_none(value):
    text = _clean(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _int_or_default(value, default=1):
    try:
        return int(value or default)
    except (TypeError, ValueError):
        return default


def _document_params(document_record):
    params = {}
    for sheet_key, column in DOCUMENT_FIELD_MAP.items():
        value = document_record.get(sheet_key, "")
        if sheet_key in NUMERIC_FIELDS:
            value = _number_or_none(value)
        elif sheet_key in INTEGER_FIELDS:
            value = _int_or_default(value)
        elif sheet_key in DATE_FIELDS:
            value = _date_or_none(value)
        elif sheet_key in TIMESTAMP_FIELDS:
            value = _timestamp_or_none(value)
        else:
            value = _clean(value)
        params[column] = value

    params["document_id"] = _clean(params.get("document_id"))
    params["order_id"] = _clean(params.get("order_id"))
    params["document_type"] = _clean(params.get("document_type"))
    params["document_ref"] = _clean(params.get("document_ref"))
    params["document_status"] = _clean(params.get("document_status")) or "Generated"
    params["version"] = params.get("version") or 1
    params["created_at"] = params.get("created_at") or datetime.now()
    return params


def get_document_settings(connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select setting_key, setting_value
                from public.app_settings
                order by setting_key
                """
            )
            return {
                _clean(setting_key): _clean(setting_value)
                for setting_key, setting_value in cursor.fetchall()
                if _clean(setting_key)
            }


def insert_order_document(document_record, connect_factory=None):
    params = _document_params(document_record)
    required = ("document_id", "order_id", "document_type", "document_ref")
    missing = [field for field in required if not params.get(field)]
    if missing:
        raise ValueError("Missing required document field(s): " + ", ".join(missing))

    columns = ", ".join(params.keys())
    placeholders = ", ".join([f"%({key})s" for key in params.keys()])
    updates = ", ".join([
        f"{column} = excluded.{column}"
        for column in params.keys()
        if column != "document_id"
    ])
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                insert into public.order_documents ({columns})
                values ({placeholders})
                on conflict (document_id) do update set {updates}
                """,
                params,
            )


def mark_document_sent(document_id, sent_by="n8n", sent_at=None, connect_factory=None):
    document_id = _clean(document_id)
    if not document_id:
        raise ValueError("document_id is required.")
    sent_at = _timestamp_or_none(sent_at) or datetime.now()
    sent_by = _clean(sent_by) or "n8n"

    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                update public.order_documents
                set document_status = 'Sent',
                    sent_at = %s,
                    sent_by = %s
                where document_id = %s
                """,
                (sent_at, sent_by, document_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Document '{document_id}' not found.")
