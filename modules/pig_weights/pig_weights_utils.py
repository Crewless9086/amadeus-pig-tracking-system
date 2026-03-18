from datetime import datetime, date
import uuid


def to_clean_string(value):
    if value is None:
        return ""

    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return str(value)

    return str(value).strip()


def to_float(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_sheet_date(value):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    value = str(value).strip()

    formats = [
        "%d %b %Y",
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%m/%d/%Y",
    ]

    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    return None


def format_date_for_json(value):
    parsed = parse_sheet_date(value)
    if not parsed:
        return ""
    return parsed.isoformat()


def format_date_for_sheet(value):
    if not value:
        return ""
    if isinstance(value, (datetime, date)):
        return value.strftime("%d %b %Y")
    parsed = parse_sheet_date(value)
    if not parsed:
        return ""
    return parsed.strftime("%d %b %Y")


def generate_weight_log_id():
    return f"WGT-{uuid.uuid4().hex[:8].upper()}"


def generate_medical_log_id():
    return f"MED-{uuid.uuid4().hex[:8].upper()}"


def generate_move_log_id():
    return f"MOV-{uuid.uuid4().hex[:8].upper()}"