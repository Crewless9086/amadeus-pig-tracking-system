import hashlib
import json
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
    "Animal_Type": "animal_type",
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
                "select current_pen_id from public.current_canonical_pig_state where pig_id = %s",
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


def insert_missing_medical_events_from_sheet_rows(rows, connect_factory=None):
    """Insert a treatment packet through one transaction, skipping exact existing facts."""
    prepared = []
    for row_values in rows or []:
        row_values = list(row_values or []) + [""] * 18
        prepared.append({
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
        })

    created = 0
    skipped = 0
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            for params in prepared:
                cursor.execute(
                    """
                    insert into public.pig_medical_events (
                        medical_event_id, pig_id, treatment_date, treatment_type,
                        product_id, product_name, dose, dose_unit, route,
                        reason_for_treatment, batch_lot_number, withdrawal_days,
                        withdrawal_end_date, given_by, follow_up_required,
                        follow_up_date, medical_notes
                    )
                    select
                        %(medical_event_id)s, %(pig_id)s, %(treatment_date)s, %(treatment_type)s,
                        %(product_id)s, %(product_name)s, %(dose)s, %(dose_unit)s, %(route)s,
                        %(reason_for_treatment)s, %(batch_lot_number)s, %(withdrawal_days)s,
                        %(withdrawal_end_date)s, %(given_by)s, %(follow_up_required)s,
                        %(follow_up_date)s, %(medical_notes)s
                    where not exists (
                        select 1
                        from public.pig_medical_events existing
                        where existing.pig_id = %(pig_id)s
                          and existing.treatment_date = %(treatment_date)s
                          and existing.treatment_type = %(treatment_type)s
                          and existing.product_id is not distinct from %(product_id)s
                          and existing.dose = %(dose)s
                          and existing.dose_unit = %(dose_unit)s
                          and existing.route = %(route)s
                          and existing.batch_lot_number = %(batch_lot_number)s
                    )
                    """,
                    params,
                )
                if cursor.rowcount:
                    created += 1
                else:
                    skipped += 1
    return {"created": created, "skipped": skipped}


def _stable_weaning_event_id(prefix, operation_id, pig_id, discriminator):
    digest = hashlib.sha256(
        f"{operation_id}|{pig_id}|{discriminator}".encode("utf-8")
    ).hexdigest()[:24].upper()
    return f"{prefix}-{digest}"


def apply_litter_weaning_day_packet(packet, connect_factory=None):
    """Apply one canonical Weaning Day packet in one bounded transaction."""
    packet = packet if isinstance(packet, dict) else {}
    litter_id = to_clean_string(packet.get("litter_id"))
    wean_date = _date_or_none(packet.get("wean_date"))
    changed_by = to_clean_string(packet.get("changed_by")) or "web_app"
    piglets = sorted(
        [row for row in packet.get("piglets", []) if isinstance(row, dict)],
        key=lambda row: to_clean_string(row.get("pig_id")),
    )
    treatments = [
        list(row or []) + [""] * 18
        for row in packet.get("treatment_rows", [])
    ]
    if not litter_id or not wean_date or not piglets:
        raise ValueError("complete_weaning_packet_required")
    pig_ids = [to_clean_string(row.get("pig_id")) for row in piglets]
    if not all(pig_ids) or len(set(pig_ids)) != len(pig_ids):
        raise ValueError("unique_weaning_pig_ids_required")
    identity_packet = {
        "version": "herdmaster_weaning_day_v1",
        "litter_id": litter_id,
        "wean_date": wean_date.isoformat(),
        "changed_by": changed_by,
        "piglets": [{
            "pig_id": to_clean_string(row.get("pig_id")),
            "tag_number": to_clean_string(row.get("tag_number")),
            "weight_kg": to_float(row.get("weight_kg")),
            "from_pen_id": to_clean_string(row.get("from_pen_id")),
            "to_pen_id": to_clean_string(row.get("to_pen_id")),
            "notes": to_clean_string(row.get("notes")),
        } for row in piglets],
        "treatments": sorted([{
            "pig_id": to_clean_string(row[1]),
            "date": str(_date_or_none(row[2]) or ""),
            "type": to_clean_string(row[3]),
            "product_id": to_clean_string(row[4]),
            "product_name": to_clean_string(row[5]),
            "dose": "" if row[6] is None else str(row[6]),
            "dose_unit": to_clean_string(row[7]),
            "route": to_clean_string(row[8]),
            "reason": to_clean_string(row[9]),
            "batch": to_clean_string(row[10]),
            "withdrawal_days": _int_or_none(row[11]),
            "withdrawal_end": str(_date_or_none(row[12]) or ""),
            "given_by": to_clean_string(row[13]),
            "follow_up": _bool_or_none_from_sheet(row[14]) is True,
            "follow_up_date": str(_date_or_none(row[15]) or ""),
            "notes": to_clean_string(row[16]),
        } for row in treatments], key=lambda row: (
            row["pig_id"], row["date"], row["type"], row["product_id"],
            row["product_name"], row["dose"], row["dose_unit"], row["route"],
            row["reason"], row["batch"], row["withdrawal_days"] or -1,
            row["withdrawal_end"], row["given_by"], row["follow_up"],
            row["follow_up_date"], row["notes"],
        )),
    }
    operation_id = "WEAN-" + hashlib.sha256(json.dumps(
        identity_packet, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()[:32].upper()
    counts = {
        "tags_created": 0, "treatments_created": 0,
        "weights_created": 0, "movements_created": 0,
        "piglets_updated": 0, "litter_updated": 0,
    }
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set transaction isolation level serializable")
            cursor.execute("set local statement_timeout = '15s'")
            cursor.execute(
                "select pg_advisory_xact_lock(hashtextextended(%s,0))",
                ("herdmaster-weaning-day:" + litter_id,),
            )
            cursor.execute(
                """
                select litter_id, wean_date, weaned_count, litter_status
                from public.litters where litter_id=%s for update
                """,
                (litter_id,),
            )
            litter = cursor.fetchone()
            if not litter:
                raise ValueError("litter_not_found")
            cursor.execute(
                """
                select pig_id, tag_number, status, on_farm, animal_type,
                       wean_date, wean_weight_kg, litter_size_weaned
                from public.pigs
                where litter_id=%s and pig_id=any(%s)
                order by pig_id for update
                """,
                (litter_id, pig_ids),
            )
            current_rows = cursor.fetchall()
            if len(current_rows) != len(piglets):
                raise ValueError("canonical_litter_pig_identity_conflict")
            current = {row[0]: row for row in current_rows}
            exact_complete = (
                litter[1] == wean_date
                and litter[2] == len(piglets)
                and litter[3] == "Weaned"
            )
            if litter[1] not in (None, wean_date):
                raise ValueError("conflicting_litter_wean_date")
            if litter[2] not in (None, 0, len(piglets)):
                raise ValueError("conflicting_litter_weaned_count")
            if litter[3] not in ("Active", "Weaned"):
                raise ValueError("conflicting_litter_status")

            for item in piglets:
                pig_id = to_clean_string(item.get("pig_id"))
                tag_number = to_clean_string(item.get("tag_number"))
                weight = to_float(item.get("weight_kg"))
                item_notes = to_clean_string(item.get("notes"))
                row = current[pig_id]
                if row[2] != "Active" or row[3] is not True:
                    raise ValueError("current_active_on_farm_piglet_required")
                if row[5] not in (None, wean_date):
                    raise ValueError("conflicting_piglet_wean_date")
                if row[6] is not None and float(row[6]) != weight:
                    raise ValueError("conflicting_piglet_wean_weight")
                if tag_number:
                    if to_clean_string(row[1]) not in ("", tag_number):
                        raise ValueError("conflicting_piglet_tag")
                    cursor.execute(
                        "select pig_id from public.pigs where tag_number=%s and pig_id<>%s",
                        (tag_number, pig_id),
                    )
                    if cursor.fetchone():
                        raise ValueError("duplicate_tag_number")
                    if not to_clean_string(row[1]):
                        cursor.execute(
                            """
                            update public.pigs set tag_number=%s, earmarked=true,
                                earmark_date=%s, updated_at=now()
                            where pig_id=%s
                            """,
                            (tag_number, wean_date, pig_id),
                        )
                        counts["tags_created"] += 1

                cursor.execute(
                    """
                    select weight_kg,coalesce(weighed_by,''),
                           coalesce(condition_notes,''),coalesce(source,'')
                    from public.pig_weight_events
                    where pig_id=%s and weight_date=%s
                    """,
                    (pig_id, wean_date),
                )
                weight_rows = cursor.fetchall()
                weights = [float(value[0]) for value in weight_rows]
                if len(weights) > 1:
                    raise ValueError("duplicate_weaning_weight_fact")
                if weights and any(value != weight for value in weights):
                    raise ValueError("conflicting_weaning_weight_fact")
                expected_weight_evidence = (
                    changed_by, item_notes or "Weaning day weight.",
                    "litter_weaning_day",
                )
                if weight_rows and any(
                    tuple(value[1:]) != expected_weight_evidence
                    for value in weight_rows
                ):
                    raise ValueError("conflicting_weaning_weight_evidence")
                if not weights:
                    cursor.execute(
                        """
                        insert into public.pig_weight_events(
                            weight_event_id,pig_id,weight_date,weight_kg,
                            weighed_by,condition_notes,source,created_at
                        ) values(%s,%s,%s,%s,%s,%s,'litter_weaning_day',now())
                        """,
                        (
                            _stable_weaning_event_id(
                                "WGT", operation_id, pig_id, wean_date
                            ),
                            pig_id, wean_date, weight, changed_by,
                                item_notes or "Weaning day weight.",
                        ),
                    )
                    counts["weights_created"] += 1

                from_pen = to_clean_string(item.get("from_pen_id"))
                to_pen = to_clean_string(item.get("to_pen_id"))
                cursor.execute(
                    """
                    select current_pen_id
                    from public.current_canonical_pig_state where pig_id=%s
                    """,
                    (pig_id,),
                )
                pen_row = cursor.fetchone()
                current_pen = to_clean_string(pen_row[0] if pen_row else "")
                if current_pen not in {from_pen, to_pen}:
                    raise ValueError("conflicting_current_pen")
                if to_pen and from_pen != to_pen:
                    cursor.execute(
                        """
                        select location_event_id,coalesce(moved_by,''),
                               coalesce(move_notes,''),coalesce(source,'')
                        from public.pig_location_events
                        where pig_id=%s and move_date=%s
                          and from_pen_id is not distinct from %s
                          and to_pen_id=%s and reason_for_move='Weaning day move'
                        """,
                        (pig_id, wean_date, from_pen or None, to_pen),
                    )
                    matching_movements = cursor.fetchall()
                    if len(matching_movements) > 1:
                        raise ValueError("duplicate_weaning_movement_fact")
                    expected_movement_evidence = (
                        changed_by,
                        item_notes
                        or "Moved during litter weaning day workflow.",
                        "litter_weaning_day",
                    )
                    if matching_movements and any(
                        tuple(value[1:]) != expected_movement_evidence
                        for value in matching_movements
                    ):
                        raise ValueError(
                            "conflicting_weaning_movement_evidence"
                        )
                    if current_pen == to_pen and not matching_movements:
                        raise ValueError(
                            "target_pen_without_weaning_movement_fact"
                        )
                    if current_pen != to_pen:
                        if current_pen != from_pen:
                            raise ValueError("stale_movement_source_pen")
                        if matching_movements:
                            raise ValueError(
                                "movement_fact_conflicts_with_current_pen"
                            )
                        cursor.execute(
                            """
                            insert into public.pig_location_events(
                                location_event_id,pig_id,move_date,from_pen_id,
                                to_pen_id,reason_for_move,moved_by,move_notes,
                                source,created_at
                            ) values(%s,%s,%s,%s,%s,'Weaning day move',%s,%s,
                                     'litter_weaning_day',now())
                            """,
                            (
                                _stable_weaning_event_id(
                                    "MOV", operation_id, pig_id,
                                    f"{from_pen}|{to_pen}|{wean_date}",
                                ),
                                pig_id, wean_date, current_pen or None, to_pen,
                                changed_by,
                                    item_notes
                                    or "Moved during litter weaning day workflow.",
                            ),
                        )
                        counts["movements_created"] += 1
                if (
                    row[4] != "Weaner"
                    or row[5] != wean_date
                    or row[6] is None
                    or float(row[6]) != weight
                    or row[7] != len(piglets)
                ):
                    cursor.execute(
                        """
                        update public.pigs
                        set animal_type='Weaner', litter_size_weaned=%s,
                            wean_date=%s, wean_weight_kg=%s, updated_at=now()
                        where pig_id=%s
                        """,
                        (len(piglets), wean_date, weight, pig_id),
                    )
                    counts["piglets_updated"] += cursor.rowcount

            for raw in treatments:
                pig_id = to_clean_string(raw[1])
                if pig_id not in current:
                    raise ValueError("treatment_pig_not_in_litter_packet")
                params = {
                    "pig_id": pig_id,
                    "treatment_date": _date_or_none(raw[2]),
                    "treatment_type": to_clean_string(raw[3]),
                    "product_id": to_clean_string(raw[4]) or None,
                    "product_name": to_clean_string(raw[5]),
                    "dose": "" if raw[6] is None else str(raw[6]),
                    "dose_unit": to_clean_string(raw[7]),
                    "route": to_clean_string(raw[8]),
                    "reason": to_clean_string(raw[9]),
                    "batch": to_clean_string(raw[10]),
                    "withdrawal_days": _int_or_none(raw[11]),
                    "withdrawal_end": _date_or_none(raw[12]),
                    "given_by": to_clean_string(raw[13]),
                    "follow_up": _bool_or_none_from_sheet(raw[14]) is True,
                    "follow_up_date": _date_or_none(raw[15]),
                    "notes": to_clean_string(raw[16]),
                }
                cursor.execute(
                    """
                    select coalesce(product_name,''),coalesce(dose,''),
                           coalesce(dose_unit,''),coalesce(route,''),
                           coalesce(reason_for_treatment,''),
                           coalesce(batch_lot_number,''),withdrawal_days,
                           withdrawal_end_date,coalesce(given_by,''),
                           follow_up_required,follow_up_date,
                           coalesce(medical_notes,'')
                    from public.pig_medical_events
                    where pig_id=%(pig_id)s
                      and treatment_date=%(treatment_date)s
                      and treatment_type=%(treatment_type)s
                      and product_id is not distinct from %(product_id)s
                    """,
                    params,
                )
                existing = cursor.fetchall()
                if len(existing) > 1:
                    raise ValueError("duplicate_treatment_fact")
                expected = (
                    params["product_name"], params["dose"],
                    params["dose_unit"], params["route"], params["reason"],
                    params["batch"], params["withdrawal_days"],
                    params["withdrawal_end"], params["given_by"],
                    params["follow_up"], params["follow_up_date"],
                    params["notes"],
                )
                if existing and any(tuple(row) != expected for row in existing):
                    raise ValueError("conflicting_treatment_fact")
                if existing:
                    continue
                event_id = _stable_weaning_event_id(
                    "MED", operation_id, pig_id,
                    f"{params['treatment_type']}|{params['product_id']}",
                )
                cursor.execute(
                    """
                    insert into public.pig_medical_events(
                        medical_event_id,pig_id,treatment_date,treatment_type,
                        product_id,product_name,dose,dose_unit,route,
                        reason_for_treatment,batch_lot_number,withdrawal_days,
                        withdrawal_end_date,given_by,follow_up_required,
                        follow_up_date,medical_notes
                    ) values(
                        %(event_id)s,%(pig_id)s,%(treatment_date)s,
                        %(treatment_type)s,%(product_id)s,%(product_name)s,
                        %(dose)s,%(dose_unit)s,%(route)s,%(reason)s,%(batch)s,
                        %(withdrawal_days)s,%(withdrawal_end)s,%(given_by)s,
                        %(follow_up)s,%(follow_up_date)s,%(notes)s
                    )
                    """,
                    {**params, "event_id": event_id},
                )
                counts["treatments_created"] += 1

            if not exact_complete:
                cursor.execute(
                    """
                    update public.litters
                    set weaned_count=%s,wean_date=%s,litter_status='Weaned',
                        updated_at=now()
                    where litter_id=%s
                    """,
                    (len(piglets), wean_date, litter_id),
                )
                counts["litter_updated"] = cursor.rowcount
    return {
        "success": True,
        "status": "weaning_day_replayed_withheld"
        if exact_complete and not any(counts.values())
        else "weaning_day_committed",
        "operation_id": operation_id,
        **counts,
    }


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
