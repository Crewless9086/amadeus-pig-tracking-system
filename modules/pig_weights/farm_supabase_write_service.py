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


def _bool_or_none_from_sheet(value):
    clean = to_clean_string(value).lower()
    if clean in {"yes", "true", "1"}:
        return True
    if clean in {"no", "false", "0"}:
        return False
    return None


def _int_or_none(value):
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _append_note(existing_notes, new_note):
    existing = to_clean_string(existing_notes)
    note = to_clean_string(new_note)
    if not note:
        return existing
    return f"{existing}\n{note}" if existing else note


_PIG_UPDATE_FIELD_MAP = {
    "Status": "status",
    "On_Farm": "on_farm",
    "Sex": "sex",
    "Tag_Number": "tag_number",
    "Purpose": "purpose",
    "Litter_Size_Born": "litter_size_born",
    "Litter_Size_Weaned": "litter_size_weaned",
    "Wean_Date": "wean_date",
    "Wean_Weight_Kg": "wean_weight_kg",
    "Exit_Date": "exit_date",
    "Exit_Reason": "exit_reason",
    "Exit_Order_ID": "exit_order_id",
    "Carcass_Weight_Kg": "carcass_weight_kg",
    "General_Notes": "notes",
    "Earmarked": "earmarked",
    "Earmark_Date": "earmark_date",
}


_PIG_UPDATE_CASTS = {
    "on_farm": _bool_or_none_from_sheet,
    "litter_size_born": _int_or_none,
    "litter_size_weaned": _int_or_none,
    "wean_date": _date_or_none,
    "wean_weight_kg": to_float,
    "exit_date": _date_or_none,
    "carcass_weight_kg": to_float,
    "earmarked": _bool_or_none_from_sheet,
    "earmark_date": _date_or_none,
}


_LITTER_UPDATE_FIELD_MAP = {
    "Born_Alive": "born_alive",
    "Stillborn_Count": "stillborn_count",
    "Mummified_Count": "mummified_count",
    "Male_Count": "male_count",
    "Female_Count": "female_count",
    "Unknown_Sex_Count": "unknown_sex_count",
    "Weaned_Count": "weaned_count",
    "Litter_Size_Weaned": "weaned_count",
    "Wean_Date": "wean_date",
    "Litter_Status": "litter_status",
    "Litter_Notes": "litter_notes",
}


_LITTER_UPDATE_CASTS = {
    "born_alive": _int_or_none,
    "stillborn_count": _int_or_none,
    "mummified_count": _int_or_none,
    "male_count": _int_or_none,
    "female_count": _int_or_none,
    "unknown_sex_count": _int_or_none,
    "weaned_count": _int_or_none,
    "wean_date": _date_or_none,
}


def _mapped_updates(updates, field_map, casts):
    mapped = {}
    for source_field, value in (updates or {}).items():
        target_field = field_map.get(source_field)
        if not target_field:
            continue
        caster = casts.get(target_field, to_clean_string)
        mapped[target_field] = caster(value)
    mapped["updated_at"] = datetime.now()
    return mapped


def update_pigs_by_id(updates_by_pig_id, connect_factory=None):
    updates_by_pig_id = updates_by_pig_id or {}
    updated = 0
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            for pig_id, updates in updates_by_pig_id.items():
                pig_id = to_clean_string(pig_id)
                mapped = _mapped_updates(updates, _PIG_UPDATE_FIELD_MAP, _PIG_UPDATE_CASTS)
                if not pig_id or not mapped:
                    continue
                assignments = ", ".join(f"{field} = %({field})s" for field in mapped)
                params = dict(mapped)
                params["pig_id"] = pig_id
                cursor.execute(
                    f"update public.pigs set {assignments} where pig_id = %(pig_id)s",
                    params,
                )
                updated += cursor.rowcount
    return updated


def update_litter_by_id(litter_id, updates, connect_factory=None):
    litter_id = to_clean_string(litter_id)
    mapped = _mapped_updates(updates, _LITTER_UPDATE_FIELD_MAP, _LITTER_UPDATE_CASTS)
    if not litter_id or not mapped:
        return 0
    assignments = ", ".join(f"{field} = %({field})s" for field in mapped)
    params = dict(mapped)
    params["litter_id"] = litter_id
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"update public.litters set {assignments} where litter_id = %(litter_id)s",
                params,
            )
            return cursor.rowcount


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


def _litter_int(value):
    return _int_or_none(value) if value not in (None, "") else None


def create_litter_with_generated_piglets(litter_id, cleaned_data, mother_tag="", father_tag="", pig_ids=None, connect_factory=None):
    pig_ids = list(pig_ids or [])
    litter_id = to_clean_string(litter_id)
    if not litter_id:
        return {"litter_created": False, "pig_rows_created": 0}

    total_born = _litter_int(cleaned_data.get("total_born"))
    born_alive = _litter_int(cleaned_data.get("born_alive"))
    stillborn_count = _litter_int(cleaned_data.get("stillborn_count")) or 0
    if total_born is None:
        total_born = 0
    if born_alive is None:
        born_alive = max(total_born - stillborn_count, 0)
    if born_alive > total_born:
        born_alive = total_born
    if born_alive + stillborn_count > total_born:
        stillborn_count = max(total_born - born_alive, 0)

    expected_piglet_count = max(born_alive, 0) + max(stillborn_count, 0)
    if len(pig_ids) < expected_piglet_count:
        raise ValueError("Not enough generated pig IDs were provided for litter creation.")

    now = datetime.now()
    farrowing_date = _date_or_none(cleaned_data.get("farrowing_date"))
    birth_month = farrowing_date.strftime("%m") if farrowing_date else ""
    birth_year = int(farrowing_date.strftime("%Y")) if farrowing_date else None

    litter_params = {
        "litter_id": litter_id,
        "farrowing_date": farrowing_date,
        "sow_pig_id": to_clean_string(cleaned_data.get("mother_pig_id")) or None,
        "boar_pig_id": to_clean_string(cleaned_data.get("father_pig_id")) or None,
        "sow_tag_number": to_clean_string(mother_tag),
        "boar_tag_number": to_clean_string(father_tag),
        "total_born": total_born,
        "born_alive": born_alive,
        "stillborn_count": stillborn_count,
        "mummified_count": _litter_int(cleaned_data.get("mummified_count")),
        "male_count": _litter_int(cleaned_data.get("male_count")),
        "female_count": _litter_int(cleaned_data.get("female_count")),
        "unknown_sex_count": None,
        "weaned_count": _litter_int(cleaned_data.get("weaned_count")),
        "wean_date": _date_or_none(cleaned_data.get("wean_date")),
        "litter_status": "Active",
        "litter_notes": to_clean_string(cleaned_data.get("notes")),
        "created_at": now,
        "updated_at": now,
    }

    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                insert into public.litters (
                    litter_id, farrowing_date, sow_pig_id, boar_pig_id,
                    sow_tag_number, boar_tag_number, total_born, born_alive,
                    stillborn_count, mummified_count, male_count, female_count,
                    unknown_sex_count, weaned_count, wean_date, litter_status,
                    litter_notes, created_at, updated_at
                )
                values (
                    %(litter_id)s, %(farrowing_date)s, %(sow_pig_id)s, %(boar_pig_id)s,
                    %(sow_tag_number)s, %(boar_tag_number)s, %(total_born)s, %(born_alive)s,
                    %(stillborn_count)s, %(mummified_count)s, %(male_count)s, %(female_count)s,
                    %(unknown_sex_count)s, %(weaned_count)s, %(wean_date)s, %(litter_status)s,
                    %(litter_notes)s, %(created_at)s, %(updated_at)s
                )
                """,
                litter_params,
            )

            created = 0

            def _insert_piglet(pig_id, status, on_farm, exit_date=None, exit_reason="", notes=""):
                nonlocal created
                cursor.execute(
                    """
                    insert into public.pigs (
                        pig_id, status, on_farm, animal_type, sex, date_of_birth,
                        birth_month, birth_year, litter_id, litter_size_born,
                        mother_pig_id, father_pig_id, initial_pen_id, purpose,
                        notes, exit_date, exit_reason, source_sheet_row,
                        created_at, updated_at
                    )
                    values (
                        %(pig_id)s, %(status)s, %(on_farm)s, 'Piglet', '',
                        %(date_of_birth)s, %(birth_month)s, %(birth_year)s,
                        %(litter_id)s, %(litter_size_born)s, %(mother_pig_id)s,
                        %(father_pig_id)s, %(initial_pen_id)s, 'Unknown',
                        %(notes)s, %(exit_date)s, %(exit_reason)s, null,
                        %(created_at)s, %(updated_at)s
                    )
                    """,
                    {
                        "pig_id": to_clean_string(pig_id),
                        "status": status,
                        "on_farm": on_farm,
                        "date_of_birth": farrowing_date,
                        "birth_month": birth_month,
                        "birth_year": birth_year,
                        "litter_id": litter_id,
                        "litter_size_born": total_born,
                        "mother_pig_id": to_clean_string(cleaned_data.get("mother_pig_id")) or None,
                        "father_pig_id": to_clean_string(cleaned_data.get("father_pig_id")) or None,
                        "initial_pen_id": to_clean_string(cleaned_data.get("current_pen_id")) or None,
                        "notes": notes,
                        "exit_date": exit_date,
                        "exit_reason": exit_reason or None,
                        "created_at": now,
                        "updated_at": now,
                    },
                )
                created += cursor.rowcount

            for index in range(born_alive):
                _insert_piglet(pig_ids[index], "Active", True)
            for index in range(stillborn_count):
                _insert_piglet(
                    pig_ids[born_alive + index],
                    "Dead",
                    False,
                    exit_date=farrowing_date,
                    exit_reason="Stillborn",
                    notes="Stillborn recorded at litter creation.",
                )

    return {"litter_created": True, "pig_rows_created": created}


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


def insert_medical_event_from_sheet_row(row_values, connect_factory=None):
    row_values = list(row_values or []) + [""] * 18
    params = {
        "medical_event_id": to_clean_string(row_values[0]),
        "pig_id": to_clean_string(row_values[1]),
        "treatment_date": _date_or_none(row_values[2]),
        "treatment_type": to_clean_string(row_values[3]),
        "product_id": to_clean_string(row_values[4]) or None,
        "product_name": to_clean_string(row_values[5]),
        "dose": "" if row_values[6] is None else str(row_values[6]),
        "dose_unit": to_clean_string(row_values[7]),
        "route": to_clean_string(row_values[8]),
        "reason_for_treatment": to_clean_string(row_values[9]),
        "batch_lot_number": to_clean_string(row_values[10]),
        "withdrawal_days": _int_or_none(row_values[11]),
        "withdrawal_end_date": _date_or_none(row_values[12]),
        "given_by": to_clean_string(row_values[13]),
        "follow_up_required": _bool_or_none_from_sheet(row_values[14]) is True,
        "follow_up_date": _date_or_none(row_values[15]),
        "medical_notes": to_clean_string(row_values[16]),
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
