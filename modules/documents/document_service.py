from datetime import date, datetime
import uuid

from services.google_sheets_service import (
    append_row,
    get_all_records,
    update_row_by_first_column_match,
)

SYSTEM_SETTINGS_SHEET = "SYSTEM_SETTINGS"
ORDER_DOCUMENTS_SHEET = "ORDER_DOCUMENTS"

DOCUMENT_TYPE_QUOTE = "Quote"
DOCUMENT_TYPE_INVOICE = "Invoice"

STATUS_GENERATED = "Generated"
STATUS_SENT = "Sent"
STATUS_VOIDED = "Voided"
STATUS_SUPERSEDED = "Superseded"

ORDER_DOCUMENT_COLUMNS = [
    "Document_ID",
    "Order_ID",
    "Document_Type",
    "Document_Ref",
    "Payment_Ref",
    "Version",
    "Document_Status",
    "Payment_Method",
    "VAT_Rate",
    "Subtotal_Ex_VAT",
    "VAT_Amount",
    "Total",
    "Valid_Until",
    "Google_Drive_File_ID",
    "Google_Drive_URL",
    "File_Name",
    "Created_At",
    "Created_By",
    "Sent_At",
    "Sent_By",
    "Notes",
]


def generate_document_id():
    return f"DOC-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def get_document_settings(required_keys=None):
    rows = get_all_records(SYSTEM_SETTINGS_SHEET)
    settings = {}

    for row in rows:
        key = str(row.get("Setting_Key", "")).strip()
        if not key:
            continue
        settings[key] = str(row.get("Setting_Value", "")).strip()

    missing = [
        key for key in (required_keys or [])
        if not settings.get(key, "").strip()
    ]
    if missing:
        raise ValueError(
            "Missing required document setting(s): " + ", ".join(sorted(missing))
        )

    return settings


def get_document_setting(setting_key, default=""):
    settings = get_document_settings()
    return settings.get(setting_key, default)


def get_order_suffix(order_id):
    parts = str(order_id or "").strip().split("-")
    return parts[-1] if parts and parts[-1] else str(order_id or "").strip()


def build_document_ref(order_id, document_type, version=1):
    order_id = str(order_id or "").strip()
    order_suffix = get_order_suffix(order_id)
    year = _year_from_order_id(order_id)
    prefix = "Q" if document_type == DOCUMENT_TYPE_QUOTE else "INV"
    base_ref = f"{prefix}-{year}-{order_suffix}"

    if int(version or 1) > 1:
        return f"{base_ref}-V{int(version)}"

    return base_ref


def build_payment_ref(order_id):
    return get_order_suffix(order_id)


def build_document_file_name(
    document_type,
    generated_date,
    payment_ref,
    version,
    total,
    payment_method,
):
    prefix = "QUO" if document_type == DOCUMENT_TYPE_QUOTE else "INV"
    date_part = _format_filename_date(generated_date)
    version_part = f"V{int(version or 1)}"
    total_part = _format_rand_amount(total)
    payment_method = str(payment_method or "").strip() or "Unknown"

    return (
        f"{prefix}_{date_part}_{payment_ref}_{version_part}_"
        f"({total_part})_{payment_method}.pdf"
    )


def get_order_documents(order_id, document_type=None):
    order_id = str(order_id or "").strip()
    rows = get_all_records(ORDER_DOCUMENTS_SHEET)
    documents = []

    for row in rows:
        if str(row.get("Order_ID", "")).strip() != order_id:
            continue
        if document_type and str(row.get("Document_Type", "")).strip() != document_type:
            continue
        documents.append(row)

    return documents


def get_next_document_version(order_id, document_type):
    documents = get_order_documents(order_id, document_type=document_type)
    versions = []

    for row in documents:
        try:
            versions.append(int(row.get("Version", 0) or 0))
        except (TypeError, ValueError):
            continue

    return (max(versions) if versions else 0) + 1


def get_latest_non_voided_quote(order_id):
    quotes = get_order_documents(order_id, document_type=DOCUMENT_TYPE_QUOTE)
    active_quotes = [
        row for row in quotes
        if str(row.get("Document_Status", "")).strip() != STATUS_VOIDED
    ]

    if not active_quotes:
        return None

    def version_key(row):
        try:
            return int(row.get("Version", 0) or 0)
        except (TypeError, ValueError):
            return 0

    return sorted(active_quotes, key=version_key, reverse=True)[0]


def append_order_document(document_record):
    row_values = [
        document_record.get(column, "")
        for column in ORDER_DOCUMENT_COLUMNS
    ]
    append_row(ORDER_DOCUMENTS_SHEET, row_values)


def mark_document_sent(document_id, sent_by="n8n", sent_at=None):
    rows = get_all_records(ORDER_DOCUMENTS_SHEET)
    document_id = str(document_id or "").strip()
    sent_at = sent_at or datetime.now().strftime("%d %b %Y %H:%M")
    sent_by = str(sent_by or "").strip() or "n8n"

    for row in rows:
        if str(row.get("Document_ID", "")).strip() != document_id:
            continue

        updated = [
            row.get(column, "")
            for column in ORDER_DOCUMENT_COLUMNS
        ]
        field_index = {column: index for index, column in enumerate(ORDER_DOCUMENT_COLUMNS)}
        updated[field_index["Document_Status"]] = STATUS_SENT
        updated[field_index["Sent_At"]] = sent_at
        updated[field_index["Sent_By"]] = sent_by
        update_row_by_first_column_match(ORDER_DOCUMENTS_SHEET, document_id, updated)
        return

    raise ValueError(f"Document '{document_id}' not found.")


def _year_from_order_id(order_id):
    parts = str(order_id or "").strip().split("-")
    if len(parts) >= 3 and parts[1].isdigit():
        return parts[1]
    return str(datetime.now().year)


def _format_filename_date(value):
    if isinstance(value, datetime):
        parsed = value.date()
    elif isinstance(value, date):
        parsed = value
    else:
        text = str(value or "").strip()
        for fmt in ("%Y-%m-%d", "%d %b %Y"):
            try:
                parsed = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                parsed = None
        if parsed is None:
            parsed = datetime.now().date()

    return parsed.strftime("%Y_%m_%d")


def _format_rand_amount(value):
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0

    return f"R{amount:,.2f}"
