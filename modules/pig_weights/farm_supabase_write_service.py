import os
import sys
from datetime import datetime

from modules.pig_weights.pig_weights_utils import parse_sheet_date, to_clean_string, to_float
from services.database_service import DATABASE_URL_ENV


def farm_supabase_writes_available():
    if "unittest" in sys.modules and os.getenv("ALLOW_SUPABASE_WRITES_IN_TESTS", "") != "1":
        return False
    return bool(os.getenv(DATABASE_URL_ENV, "").strip())


def _connect(connect_factory=None):
    database_url = os.getenv(DATABASE_URL_ENV, "").strip()
    if connect_factory is not None:
        return connect_factory(database_url)
    import psycopg
    return psycopg.connect(database_url, connect_timeout=10)


def _fetch_one(cursor, sql, params=()):
    cursor.execute(sql, params)
    columns = [column.name for column in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None


def _date_or_none(value):
    return parse_sheet_date(value)


def _bool_from_sheet(value):
    return to_clean_string(value).lower() in {"yes", "true", "1"}


def insert_pig(pig_id, cleaned_data, mother_tag_number="", father_tag_number="", connect_factory=None):
    params = {
        "pig_id": to_clean_string(pig_id),
        "tag_number": to_clean_string(cleaned_data.get("tag_number")),
        "pig_name": to_clean_string(cleaned_data.get("pig_name")),
        "status": to_clean_string(cleaned_data.get("status")),
        "on_farm": _bool_from_sheet(cleaned_data.get("on_farm")),
        "animal_type": to_clean_string(cleaned_data.get("animal_type")),
        "sex": to_clean_string(cleaned_data.get("sex")),
        "date_of_birth": _date_or_none(cleaned_data.get("date_of_birth")),
        "birth_month": cleaned_data["date_of_birth"].strftime("%m") if cleaned_data.get("date_of_birth") else "",
        "birth_year": int(cleaned_data["date_of_birth"].strftime("%Y")) if cleaned_data.get("date_of_birth") else None,
        "breed_type": to_clean_string(cleaned_data.get("breed_type")),
        "colour_markings": to_clean_string(cleaned_data.get("colour_markings")),
        "mother_pig_id": to_clean_string(cleaned_data.get("mother_pig_id")) if cleaned_data.get("mother_pig_id") != "Unknown" else None,
        "father_pig_id": to_clean_string(cleaned_data.get("father_pig_id")) if cleaned_data.get("father_pig_id") != "Unknown" else None,
        "litter_id": to_clean_string(cleaned_data.get("litter_id")) if cleaned_data.get("litter_id") != "Unknown" else None,
        "initial_pen_id": to_clean_string(cleaned_data.get("current_pen_id")) or None,
        "purpose": to_clean_string(cleaned_data.get("purpose")),
        "notes": to_clean_string(cleaned_data.get("general_notes")),
        "exit_date": _date_or_none(cleaned_data.get("exit_date")),
        "exit_reason": to_clean_string(cleaned_data.get("exit_reason")) or None,
        "exit_order_id": to_clean_string(cleaned_data.get("exit_order_id")) or None,
        "carcass_weight_kg": to_float(cleaned_data.get("carcass_weight_kg")),
    }
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.pigs (
                    pig_id, tag_number, pig_name, status, on_farm, animal_type, sex,
                    date_of_birth, birth_month, birth_year, breed_type, colour_markings,
                    mother_pig_id, father_pig_id, litter_id, initial_pen_id, purpose,
                    notes, exit_date, exit_reason, exit_order_id, carcass_weight_kg
                )
                values (
                    %(pig_id)s, %(tag_number)s, %(pig_name)s, %(status)s, %(on_farm)s, %(animal_type)s, %(sex)s,
                    %(date_of_birth)s, %(birth_month)s, %(birth_year)s, %(breed_type)s, %(colour_markings)s,
                    %(mother_pig_id)s, %(father_pig_id)s, %(litter_id)s, %(initial_pen_id)s, %(purpose)s,
                    %(notes)s, %(exit_date)s, %(exit_reason)s, %(exit_order_id)s, %(carcass_weight_kg)s
                )
                """,
                params,
            )


def insert_product(product_id, cleaned_data, connect_factory=None):
    params = {
        "product_id": to_clean_string(product_id),
        "product_name": to_clean_string(cleaned_data.get("product_name")),
        "product_category": to_clean_string(cleaned_data.get("product_category")),
        "default_dose": "" if cleaned_data.get("default_dose") is None else str(cleaned_data.get("default_dose")),
        "dose_unit": to_clean_string(cleaned_data.get("dose_unit")),
        "default_withdrawal_days": cleaned_data.get("default_withdrawal_days"),
        "supplier": to_clean_string(cleaned_data.get("supplier")),
        "batch_tracking_required": _bool_from_sheet(cleaned_data.get("batch_tracking_required")),
        "is_active": _bool_from_sheet(cleaned_data.get("is_active")),
        "product_notes": to_clean_string(cleaned_data.get("product_notes")),
    }
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.farm_products (
                    product_id, product_name, product_category, default_dose, dose_unit,
                    default_withdrawal_days, supplier, batch_tracking_required, is_active, product_notes
                )
                values (
                    %(product_id)s, %(product_name)s, %(product_category)s, %(default_dose)s, %(dose_unit)s,
                    %(default_withdrawal_days)s, %(supplier)s, %(batch_tracking_required)s, %(is_active)s, %(product_notes)s
                )
                """,
                params,
            )


def insert_pen(pen_id, cleaned_data, connect_factory=None):
    params = {
        "pen_id": to_clean_string(pen_id),
        "pen_name": to_clean_string(cleaned_data.get("pen_name")),
        "pen_type": to_clean_string(cleaned_data.get("pen_type")),
        "capacity": cleaned_data.get("capacity"),
        "is_active": _bool_from_sheet(cleaned_data.get("is_active")),
        "pen_notes": to_clean_string(cleaned_data.get("pen_notes")),
    }
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.pens (pen_id, pen_name, pen_type, capacity, is_active, pen_notes)
                values (%(pen_id)s, %(pen_name)s, %(pen_type)s, %(capacity)s, %(is_active)s, %(pen_notes)s)
                """,
                params,
            )


def get_weight_event(pig_id, weight_date, connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            return _fetch_one(
                cursor,
                """
                select *
                from public.pig_weight_events
                where pig_id = %s and weight_date = %s
                order by created_at desc
                limit 1
                """,
                (to_clean_string(pig_id), _date_or_none(weight_date)),
            )


def get_current_pen_id(pig_id, connect_factory=None):
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            row = _fetch_one(
                cursor,
                "select current_pen_id from public.pig_current_state where pig_id = %s",
                (to_clean_string(pig_id),),
            )
    return to_clean_string((row or {}).get("current_pen_id"))


def insert_weight_event(weight_event_id, cleaned_data, connect_factory=None):
    params = {
        "weight_event_id": to_clean_string(weight_event_id),
        "pig_id": to_clean_string(cleaned_data.get("pig_id")),
        "weight_date": _date_or_none(cleaned_data.get("weight_date")),
        "weight_kg": to_float(cleaned_data.get("weight_kg")),
        "weighed_by": to_clean_string(cleaned_data.get("weighed_by")),
        "condition_notes": to_clean_string(cleaned_data.get("condition_notes")),
        "source": "app_single_weight",
        "created_at": datetime.now(),
    }
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.pig_weight_events (
                    weight_event_id, pig_id, weight_date, weight_kg, weighed_by,
                    condition_notes, source, created_at
                )
                values (
                    %(weight_event_id)s, %(pig_id)s, %(weight_date)s, %(weight_kg)s, %(weighed_by)s,
                    %(condition_notes)s, %(source)s, %(created_at)s
                )
                """,
                params,
            )


def insert_medical_event(medical_event_id, cleaned_data, product=None, withdrawal_days=None, withdrawal_end_date=None, connect_factory=None):
    product = product or {}
    params = {
        "medical_event_id": to_clean_string(medical_event_id),
        "pig_id": to_clean_string(cleaned_data.get("pig_id")),
        "treatment_date": _date_or_none(cleaned_data.get("treatment_date")),
        "treatment_type": to_clean_string(cleaned_data.get("treatment_type")),
        "product_id": to_clean_string(cleaned_data.get("product_id")) or None,
        "product_name": to_clean_string(product.get("product_name")),
        "dose": "" if cleaned_data.get("dose") is None else str(cleaned_data.get("dose")),
        "dose_unit": to_clean_string(cleaned_data.get("dose_unit")) or to_clean_string(product.get("dose_unit")),
        "route": to_clean_string(cleaned_data.get("route")),
        "reason_for_treatment": to_clean_string(cleaned_data.get("reason_for_treatment")),
        "batch_lot_number": to_clean_string(cleaned_data.get("batch_lot_number")),
        "withdrawal_days": withdrawal_days if withdrawal_days != "" else None,
        "withdrawal_end_date": _date_or_none(withdrawal_end_date),
        "given_by": to_clean_string(cleaned_data.get("given_by")),
        "follow_up_required": _bool_from_sheet(cleaned_data.get("follow_up_required")),
        "follow_up_date": _date_or_none(cleaned_data.get("follow_up_date")),
        "medical_notes": to_clean_string(cleaned_data.get("medical_notes")),
    }
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.pig_medical_events (
                    medical_event_id, pig_id, treatment_date, treatment_type,
                    product_id, product_name, dose, dose_unit, route,
                    reason_for_treatment, batch_lot_number, withdrawal_days,
                    withdrawal_end_date, given_by, follow_up_required,
                    follow_up_date, medical_notes
                )
                values (
                    %(medical_event_id)s, %(pig_id)s, %(treatment_date)s, %(treatment_type)s,
                    %(product_id)s, %(product_name)s, %(dose)s, %(dose_unit)s, %(route)s,
                    %(reason_for_treatment)s, %(batch_lot_number)s, %(withdrawal_days)s,
                    %(withdrawal_end_date)s, %(given_by)s, %(follow_up_required)s,
                    %(follow_up_date)s, %(medical_notes)s
                )
                """,
                params,
            )


def insert_location_event(location_event_id, cleaned_data, connect_factory=None):
    params = {
        "location_event_id": to_clean_string(location_event_id),
        "pig_id": to_clean_string(cleaned_data.get("pig_id")),
        "move_date": _date_or_none(cleaned_data.get("move_date")),
        "from_pen_id": to_clean_string(cleaned_data.get("from_pen_id")) or None,
        "to_pen_id": to_clean_string(cleaned_data.get("to_pen_id")) or None,
        "reason_for_move": to_clean_string(cleaned_data.get("reason_for_move")),
        "moved_by": to_clean_string(cleaned_data.get("moved_by")),
        "move_notes": to_clean_string(cleaned_data.get("move_notes")),
        "source": "app_single_movement",
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
