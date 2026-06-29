import os
import sys
from datetime import date, datetime, timedelta

from modules.pig_weights.pig_weights_utils import (
    format_date_for_sheet,
    parse_sheet_date,
    to_clean_string,
)
from services.database_service import DATABASE_URL_ENV


def supabase_mating_writes_available():
    if "unittest" in sys.modules and os.getenv("ALLOW_SUPABASE_WRITES_IN_TESTS", "") != "1":
        return False
    return bool(os.getenv(DATABASE_URL_ENV, "").strip())


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _fetch_all(cursor, sql, params=()):
    cursor.execute(sql, params)
    columns = [column.name for column in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _date_or_none(value):
    return parse_sheet_date(value)


def _date_text(value):
    return format_date_for_sheet(value)


def _mating_status(row):
    pregnancy_result = to_clean_string(row.get("pregnancy_check_result")).lower().replace(" ", "_")
    outcome = to_clean_string(row.get("outcome")).lower().replace(" ", "_")
    if to_clean_string(row.get("related_litter_id")) or row.get("farrowing_date") or outcome == "farrowed":
        return "Farrowed"
    if pregnancy_result == "pregnant" or outcome == "pregnant":
        return "Confirmed_Pregnant"
    if pregnancy_result == "not_pregnant" or outcome in {"not_pregnant", "repeat_required"}:
        return "Repeat_Service"
    return "Open"


def _days_since(value):
    parsed = _date_or_none(value)
    if not parsed:
        return ""
    return str((date.today() - parsed).days)


def _mating_sheet_row(row):
    if not row:
        return None
    status = _mating_status(row)
    return {
        "Mating_ID": to_clean_string(row.get("mating_id")),
        "Sow_Pig_ID": to_clean_string(row.get("sow_pig_id")),
        "Sow_Tag_Number": to_clean_string(row.get("sow_tag_number")),
        "Boar_Pig_ID": to_clean_string(row.get("boar_pig_id")),
        "Boar_Tag_Number": to_clean_string(row.get("boar_tag_number")),
        "Mating_Date": _date_text(row.get("mating_date")),
        "Mating_Method": to_clean_string(row.get("mating_method")),
        "Exposure_Group": to_clean_string(row.get("exposure_group")),
        "Expected_Pregnancy_Check_Date": _date_text(row.get("expected_pregnancy_check_date")),
        "Pregnancy_Check_Date": _date_text(row.get("pregnancy_check_date")),
        "Pregnancy_Check_Result": to_clean_string(row.get("pregnancy_check_result")),
        "Expected_Farrowing_Date": _date_text(row.get("expected_farrowing_date")),
        "Actual_Farrowing_Date": _date_text(row.get("farrowing_date")),
        "Mating_Status": status,
        "Outcome": to_clean_string(row.get("outcome")),
        "Linked_Litter_ID": to_clean_string(row.get("related_litter_id")),
        "Days_Since_Mating": _days_since(row.get("mating_date")),
        "Service_Notes": to_clean_string(row.get("mating_notes")),
        "Created_At": _date_text(row.get("created_at")),
        "Updated_At": _date_text(row.get("updated_at")),
    }


def get_pig_lookup(connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            rows = _fetch_all(
                cursor,
                """
                select pig_id, tag_number, current_pen_id
                from public.pig_current_state
                """,
            )
    return {
        to_clean_string(row.get("pig_id")): {
            "Pig_ID": to_clean_string(row.get("pig_id")),
            "Tag_Number": to_clean_string(row.get("tag_number")),
            "Current_Pen_ID": to_clean_string(row.get("current_pen_id")),
        }
        for row in rows
        if to_clean_string(row.get("pig_id"))
    }


def get_pen_lookup(connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            rows = _fetch_all(
                cursor,
                """
                select pen_id, pen_name, pen_type
                from public.pens
                where is_active is true
                """,
            )
    return {
        to_clean_string(row.get("pen_id")): {
            "pen_id": to_clean_string(row.get("pen_id")),
            "pen_name": to_clean_string(row.get("pen_name")),
            "pen_type": to_clean_string(row.get("pen_type")),
        }
        for row in rows
        if to_clean_string(row.get("pen_id"))
    }


def insert_mating(mating_id, cleaned_data, sow_tag_number="", boar_tag_number="", connect_factory=None):
    mating_date = _date_or_none(cleaned_data["mating_date"])
    expected_check = mating_date + timedelta(days=21) if mating_date else None
    expected_farrowing = mating_date + timedelta(days=114) if mating_date else None
    params = {
        "mating_id": to_clean_string(mating_id),
        "sow_pig_id": to_clean_string(cleaned_data["sow_pig_id"]),
        "sow_tag_number": to_clean_string(sow_tag_number),
        "boar_pig_id": to_clean_string(cleaned_data.get("boar_pig_id", "")) or None,
        "boar_tag_number": to_clean_string(boar_tag_number),
        "mating_date": mating_date,
        "mating_method": to_clean_string(cleaned_data.get("mating_method", "")),
        "exposure_group": to_clean_string(cleaned_data.get("exposure_group", "")),
        "expected_pregnancy_check_date": expected_check,
        "pregnancy_check_result": "Pending",
        "expected_farrowing_date": expected_farrowing,
        "outcome": "Pending",
        "mating_notes": to_clean_string(cleaned_data.get("service_notes", "")),
        "created_at": datetime.now(),
        "updated_at": datetime.now(),
    }
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.mating_events (
                    mating_id, sow_pig_id, sow_tag_number, boar_pig_id, boar_tag_number,
                    mating_date, mating_method, exposure_group,
                    expected_pregnancy_check_date, pregnancy_check_result,
                    expected_farrowing_date, outcome, mating_notes, created_at, updated_at
                )
                values (
                    %(mating_id)s, %(sow_pig_id)s, %(sow_tag_number)s, %(boar_pig_id)s, %(boar_tag_number)s,
                    %(mating_date)s, %(mating_method)s, %(exposure_group)s,
                    %(expected_pregnancy_check_date)s, %(pregnancy_check_result)s,
                    %(expected_farrowing_date)s, %(outcome)s, %(mating_notes)s, %(created_at)s, %(updated_at)s
                )
                """,
                params,
            )


def get_mating_sheet_row(mating_id, connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            rows = _fetch_all(
                cursor,
                "select * from public.mating_events where mating_id = %s",
                (to_clean_string(mating_id),),
            )
    return _mating_sheet_row(rows[0]) if rows else None


def update_mating_fields(mating_id, updates, connect_factory=None):
    field_map = {
        "Linked_Litter_ID": "related_litter_id",
        "Actual_Farrowing_Date": "farrowing_date",
        "Pregnancy_Check_Date": "pregnancy_check_date",
        "Pregnancy_Check_Result": "pregnancy_check_result",
        "Outcome": "outcome",
        "Service_Notes": "mating_notes",
    }
    fields = {}
    for sheet_field, value in updates.items():
        column = field_map.get(sheet_field)
        if not column:
            continue
        if column in {"farrowing_date", "pregnancy_check_date"}:
            fields[column] = _date_or_none(value)
        else:
            fields[column] = to_clean_string(value)
    fields["updated_at"] = datetime.now()
    if not fields:
        return 0
    fields["mating_id"] = to_clean_string(mating_id)
    assignments = ", ".join([f"{column} = %({column})s" for column in fields if column != "mating_id"])
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                update public.mating_events
                set {assignments}
                where mating_id = %(mating_id)s
                """,
                fields,
            )
            return cursor.rowcount


def insert_location_event(location_event_id, pig_id, move_date, from_pen_id, to_pen_id, reason, moved_by, connect_factory=None):
    params = {
        "location_event_id": to_clean_string(location_event_id),
        "pig_id": to_clean_string(pig_id),
        "move_date": _date_or_none(move_date),
        "from_pen_id": to_clean_string(from_pen_id) or None,
        "to_pen_id": to_clean_string(to_pen_id) or None,
        "reason_for_move": to_clean_string(reason),
        "moved_by": to_clean_string(moved_by),
        "move_notes": "",
        "source": "app_mating_workflow",
        "created_at": datetime.now(),
    }
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.pig_location_events (
                    location_event_id, pig_id, move_date, from_pen_id, to_pen_id,
                    reason_for_move, moved_by, move_notes, source, created_at
                )
                values (
                    %(location_event_id)s, %(pig_id)s, %(move_date)s, %(from_pen_id)s, %(to_pen_id)s,
                    %(reason_for_move)s, %(moved_by)s, %(move_notes)s, %(source)s, %(created_at)s
                )
                on conflict do nothing
                """,
                params,
            )
            return cursor.rowcount > 0
