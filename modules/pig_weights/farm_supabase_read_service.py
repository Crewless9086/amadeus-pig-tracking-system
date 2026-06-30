import os
from datetime import date, datetime

from services.database_service import DATABASE_URL_ENV


def _database_url():
    return os.getenv(DATABASE_URL_ENV, "").strip()


def farm_supabase_reads_available():
    return bool(_database_url())


def _connect(connect_factory=None):
    if connect_factory is not None:
        return connect_factory(_database_url())
    import psycopg
    return psycopg.connect(_database_url(), connect_timeout=10)


def _fetch_all(sql, params=(), connect_factory=None):
    if not farm_supabase_reads_available() and connect_factory is None:
        raise RuntimeError(f"{DATABASE_URL_ENV} is not configured.")
    with _connect(connect_factory=connect_factory) as connection:
        with connection.cursor() as cursor:
            cursor.execute("set transaction read only")
            cursor.execute(sql, params)
            columns = [column.name for column in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]


def _fetch_one(sql, params=(), connect_factory=None):
    rows = _fetch_all(sql, params=params, connect_factory=connect_factory)
    return rows[0] if rows else None


def _text(value):
    return "" if value is None else str(value).strip()


def _yes_no(value):
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return ""


def _date_text(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return _text(value)


def _float_or_none(value):
    if value is None or value == "":
        return None
    return float(value)


def _age_days(date_of_birth):
    if not isinstance(date_of_birth, date):
        return ""
    return (date.today() - date_of_birth).days


def _weight_band(weight_kg):
    weight = _float_or_none(weight_kg)
    if weight is None:
        return ""
    if weight < 30:
        return "Under 30 kg"
    if weight < 60:
        return "30-<60 kg"
    if weight < 80:
        return "60-<80 kg"
    return "80 kg+"


def _sale_stream_for_exit(row):
    status = _text(row.get("status")).lower()
    exit_reason = _text(row.get("exit_reason")).lower().replace("-", "_").replace(" ", "_")
    if exit_reason in {"meat", "meat_sale", "carcass", "carcass_sale", "pork_sale", "processed_meat_sale"}:
        return "meat"
    if exit_reason in {"slaughter", "slaughtered", "abattoir", "abattoir_sale", "sold_to_abattoir"} or status == "slaughtered":
        return "slaughter"
    if exit_reason in {"sold", "livestock", "livestock_sale", "live_sale"} or status == "sold":
        return "livestock"
    return ""


def _lifecycle_outcome_for_exit(row):
    status = _text(row.get("status")).lower()
    exit_reason = _text(row.get("exit_reason")).lower().replace("-", "_").replace(" ", "_")
    if status == "dead" or exit_reason in {"died", "culled", "lost", "stillborn", "died_after_birth", "crushed_by_sow", "weak_piglet", "unknown"}:
        return "dead"
    if status == "removed" or exit_reason in {"removed", "other"}:
        return "removed"
    if status == "slaughtered" or exit_reason in {"slaughter", "slaughtered", "abattoir", "abattoir_sale", "sold_to_abattoir"}:
        return "slaughtered"
    if status == "sold" or exit_reason in {"sold", "livestock", "livestock_sale", "live_sale", "meat", "meat_sale", "carcass", "carcass_sale", "pork_sale", "processed_meat_sale"}:
        return "sold"
    if exit_reason:
        return "other"
    return ""


def _average(values):
    clean_values = [value for value in values if value is not None]
    if not clean_values:
        return None
    return round(sum(clean_values) / len(clean_values), 2)


def _tag_sort_key(tag_number, pig_id):
    raw = _text(tag_number or pig_id)
    if raw.isdigit():
        return raw.zfill(8)
    return raw.lower()


def _calculated_stage(row):
    animal_type = _text(row.get("animal_type"))
    if animal_type:
        return animal_type
    weight = _float_or_none(row.get("current_weight_kg"))
    if weight is None:
        return ""
    if weight < 15:
        return "Piglet"
    if weight < 35:
        return "Weaner"
    if weight < 60:
        return "Grower"
    return "Finisher"


def _pig_summary(row):
    return {
        "pig_id": _text(row.get("pig_id")),
        "tag_number": _text(row.get("tag_number")),
        "pig_name": _text(row.get("pig_name")),
        "status": _text(row.get("status")),
        "on_farm": _yes_no(row.get("on_farm")),
        "animal_type": _text(row.get("animal_type")),
        "sex": _text(row.get("sex")),
        "date_of_birth": _date_text(row.get("date_of_birth")),
        "age_days": _age_days(row.get("date_of_birth")),
        "litter_id": _text(row.get("litter_id")),
        "purpose": _text(row.get("purpose")),
        "current_weight_kg": _float_or_none(row.get("current_weight_kg")),
        "last_weight_date": _date_text(row.get("last_weight_date")),
        "current_pen_id": _text(row.get("current_pen_id")),
        "current_pen_name": _text(row.get("current_pen_name")),
        "calculated_stage": _calculated_stage(row),
        "weight_band": _weight_band(row.get("current_weight_kg")),
        "is_sale_ready": "",
        "reserved_status": "",
    }


def _pig_summary_card(row):
    return {
        "pig_id": _text(row.get("pig_id")),
        "tag_number": _text(row.get("tag_number")),
        "sex": _text(row.get("sex")),
        "status": _text(row.get("status")),
        "on_farm": _yes_no(row.get("on_farm")),
        "date_of_birth": _date_text(row.get("date_of_birth")),
        "age_days": _age_days(row.get("date_of_birth")),
        "current_weight_kg": _float_or_none(row.get("current_weight_kg")),
        "calculated_stage": _calculated_stage(row),
        "current_pen_id": _text(row.get("current_pen_id")),
        "litter_id": _text(row.get("litter_id")),
    }


def _current_state_rows(connect_factory=None):
    return _fetch_all(
        """
        select
            state.pig_id,
            state.tag_number,
            state.pig_name,
            state.status,
            state.on_farm,
            state.animal_type,
            state.sex,
            state.date_of_birth,
            state.litter_id,
            state.purpose,
            state.current_weight_kg,
            state.last_weight_date,
            state.current_pen_id,
            state.current_pen_name,
            pig.mother_pig_id,
            pig.father_pig_id,
            pig.exit_reason,
            pig.notes
        from public.pig_current_state state
        join public.pigs pig on pig.pig_id = state.pig_id
        order by coalesce(nullif(state.tag_number, ''), state.pig_id)
        """,
        connect_factory=connect_factory,
    )


def _dashboard_rows(connect_factory=None):
    return _fetch_all(
        """
        select
            state.pig_id,
            state.status,
            state.on_farm,
            state.animal_type,
            state.current_weight_kg,
            pig.exit_date,
            pig.exit_reason
        from public.pig_current_state state
        join public.pigs pig on pig.pig_id = state.pig_id
        """,
        connect_factory=connect_factory,
    )


def _reserved_pig_count(connect_factory=None):
    row = _fetch_one(
        """
        select count(distinct pig_id) as reserved_pig_count
        from public.order_lines
        where reserved_status = 'Reserved'
          and nullif(pig_id, '') is not null
          and coalesce(line_status, '') not in ('Cancelled', 'Released')
        """,
        connect_factory=connect_factory,
    )
    return int(row.get("reserved_pig_count") or 0) if row else 0


def get_dashboard_summary(today=None, connect_factory=None):
    today = today or date.today()
    rows = _dashboard_rows(connect_factory=connect_factory)
    reserved_count = _reserved_pig_count(connect_factory=connect_factory)
    animal_counts = {
        "Boar": 0,
        "Sow": 0,
        "Gilt": 0,
        "Piglet": 0,
        "Weaner": 0,
        "Grower": 0,
        "Finisher": 0,
    }
    on_farm_pigs = 0
    available_for_sale_count = 0
    sales_this_month = {
        "livestock": 0,
        "slaughter": 0,
        "meat": 0,
    }
    lifecycle_outcomes_this_month = {
        "sold": 0,
        "slaughtered": 0,
        "dead": 0,
        "removed": 0,
        "other": 0,
    }

    for row in rows:
        status = _text(row.get("status"))
        on_farm = row.get("on_farm") is True
        if on_farm:
            on_farm_pigs += 1
            animal_type = _text(row.get("animal_type"))
            if animal_type in animal_counts:
                animal_counts[animal_type] += 1
            if status == "Active" and (_float_or_none(row.get("current_weight_kg")) or 0) >= 60:
                available_for_sale_count += 1

        exit_date = row.get("exit_date")
        if not isinstance(exit_date, date) or exit_date.year != today.year or exit_date.month != today.month:
            continue

        lifecycle_outcome = _lifecycle_outcome_for_exit(row)
        if lifecycle_outcome:
            lifecycle_outcomes_this_month[lifecycle_outcome] += 1

        sale_stream = _sale_stream_for_exit(row)
        if sale_stream:
            sales_this_month[sale_stream] += 1

    sold_this_month = sum(sales_this_month.values())
    return {
        "on_farm_pigs": on_farm_pigs,
        "boars": animal_counts["Boar"],
        "sows": animal_counts["Sow"],
        "gilts": animal_counts["Gilt"],
        "piglets": animal_counts["Piglet"],
        "weaners": animal_counts["Weaner"],
        "growers": animal_counts["Grower"],
        "finishers": animal_counts["Finisher"],
        "sold_this_month": sold_this_month,
        "livestock_sold_this_month": sales_this_month["livestock"],
        "slaughter_sold_this_month": sales_this_month["slaughter"],
        "meat_sold_this_month": sales_this_month["meat"],
        "pig_exit_sold_this_month": sold_this_month,
        "pig_exit_livestock_sold_this_month": sales_this_month["livestock"],
        "pig_exit_slaughter_sold_this_month": sales_this_month["slaughter"],
        "pig_exit_meat_sold_this_month": sales_this_month["meat"],
        "lifecycle_outcomes_this_month": sum(lifecycle_outcomes_this_month.values()),
        "lifecycle_sold_this_month": lifecycle_outcomes_this_month["sold"],
        "lifecycle_slaughtered_this_month": lifecycle_outcomes_this_month["slaughtered"],
        "lifecycle_dead_this_month": lifecycle_outcomes_this_month["dead"],
        "lifecycle_removed_this_month": lifecycle_outcomes_this_month["removed"],
        "lifecycle_other_this_month": lifecycle_outcomes_this_month["other"],
        "available_for_sale_pigs": available_for_sale_count,
        "reserved_pigs": reserved_count,
        "withdrawal_hold_pigs": 0,
        "source": "supabase_canonical",
    }


def get_active_pigs(connect_factory=None):
    return [
        _pig_summary(row)
        for row in _current_state_rows(connect_factory=connect_factory)
        if _text(row.get("status")).lower() == "active" and row.get("on_farm") is True
    ]


def get_pig_detail(pig_id, connect_factory=None):
    row = _fetch_one(
        """
        select
            state.*,
            pig.mother_pig_id,
            pig.father_pig_id,
            pig.notes,
            mother.tag_number as mother_tag_number,
            father.tag_number as father_tag_number
        from public.pig_current_state state
        join public.pigs pig on pig.pig_id = state.pig_id
        left join public.pigs mother on mother.pig_id = pig.mother_pig_id
        left join public.pigs father on father.pig_id = pig.father_pig_id
        where state.pig_id = %s
        """,
        (pig_id,),
        connect_factory=connect_factory,
    )
    if not row:
        return None
    pig = _pig_summary(row)
    pig.update({
        "mother_pig_id": _text(row.get("mother_pig_id")),
        "mother_tag_number": _text(row.get("mother_tag_number")),
        "father_pig_id": _text(row.get("father_pig_id")),
        "father_tag_number": _text(row.get("father_tag_number")),
        "general_notes": _text(row.get("notes")),
        "last_treatment_date": "",
        "last_product_name": "",
        "current_withdrawal_end_date": "",
        "withdrawal_clear": "",
        "lifecycle": {
            "status": _text(row.get("status")),
            "on_farm": _yes_no(row.get("on_farm")),
            "wean_date": "",
            "wean_weight_kg": None,
            "exit_date": "",
            "exit_reason": "",
            "exit_order_id": "",
            "carcass_weight_kg": None,
        },
        "source": "supabase_canonical",
    })
    return pig


def get_pens(connect_factory=None):
    rows = _fetch_all(
        """
        select pen_id, pen_name, pen_type, capacity, pen_notes
        from public.pens
        where is_active is true
        order by coalesce(nullif(pen_name, ''), pen_id)
        """,
        connect_factory=connect_factory,
    )
    return [{
        "pen_id": _text(row.get("pen_id")),
        "pen_name": _text(row.get("pen_name")),
        "pen_type": _text(row.get("pen_type")),
        "capacity": _float_or_none(row.get("capacity")),
        "pen_notes": _text(row.get("pen_notes")),
    } for row in rows]


def get_products(connect_factory=None):
    rows = _fetch_all(
        """
        select product_id, product_name, product_category, default_dose, dose_unit,
               default_withdrawal_days, supplier
        from public.farm_products
        where is_active is true
        order by coalesce(nullif(product_name, ''), product_id)
        """,
        connect_factory=connect_factory,
    )
    return [{
        "product_id": _text(row.get("product_id")),
        "product_name": _text(row.get("product_name")),
        "product_category": _text(row.get("product_category")),
        "default_dose": _float_or_none(row.get("default_dose")),
        "dose_unit": _text(row.get("dose_unit")),
        "default_withdrawal_days": _float_or_none(row.get("default_withdrawal_days")),
        "supplier": _text(row.get("supplier")),
    } for row in rows]


def get_weight_events_for_date(weight_date, connect_factory=None):
    rows = _fetch_all(
        """
        select weight_event_id, pig_id, weight_date, weight_kg, weighed_by, condition_notes
        from public.pig_weight_events
        where weight_date = %s
        order by pig_id, created_at, weight_event_id
        """,
        (weight_date,),
        connect_factory=connect_factory,
    )
    return [{
        "Weight_Log_ID": _text(row.get("weight_event_id")),
        "Pig_ID": _text(row.get("pig_id")),
        "Weight_Date": _date_text(row.get("weight_date")),
        "Weight_Kg": _float_or_none(row.get("weight_kg")),
        "Weighed_By": _text(row.get("weighed_by")),
        "Condition_Notes": _text(row.get("condition_notes")),
        "source": "supabase_canonical",
    } for row in rows]


def get_parent_options(connect_factory=None):
    rows = _fetch_all(
        """
        select pig_id, tag_number, sex, status, purpose, current_pen_id, current_pen_name
        from public.pig_current_state
        where status = 'Active'
          and purpose = 'Breeding'
          and sex in ('Female', 'Male', 'Castrated_Male')
        order by coalesce(nullif(tag_number, ''), pig_id)
        """,
        connect_factory=connect_factory,
    )
    mother_options = [{
        "pig_id": "Unknown",
        "tag_number": "Unknown",
        "sex": "Female",
        "status": "Active",
        "purpose": "Breeding",
        "current_pen_id": "",
    }]
    father_options = [{
        "pig_id": "Unknown",
        "tag_number": "Unknown",
        "sex": "Male",
        "status": "Active",
        "purpose": "Breeding",
        "current_pen_id": "",
    }]

    for row in rows:
        option = {
            "pig_id": _text(row.get("pig_id")),
            "tag_number": _text(row.get("tag_number")) or _text(row.get("pig_id")),
            "sex": _text(row.get("sex")),
            "status": _text(row.get("status")),
            "purpose": _text(row.get("purpose")),
            "current_pen_id": _text(row.get("current_pen_id")),
            "current_pen_name": _text(row.get("current_pen_name")) or _text(row.get("current_pen_id")),
        }
        if option["sex"] == "Female":
            mother_options.append(option)
        if option["sex"] in ("Male", "Castrated_Male"):
            father_options.append(option)

    return {"mothers": mother_options, "fathers": father_options}


def get_pig_master_rows_by_ids(pig_ids, connect_factory=None):
    clean_ids = [_text(pig_id) for pig_id in (pig_ids or []) if _text(pig_id)]
    if not clean_ids:
        return []
    rows = _fetch_all(
        """
        select
            state.pig_id,
            state.tag_number,
            state.status,
            state.on_farm,
            state.litter_id,
            state.purpose,
            pig.notes
        from public.pig_current_state state
        join public.pigs pig on pig.pig_id = state.pig_id
        where state.pig_id = any(%s)
        """,
        (clean_ids,),
        connect_factory=connect_factory,
    )
    return [{
        "Pig_ID": _text(row.get("pig_id")),
        "Tag_Number": _text(row.get("tag_number")),
        "Litter_ID": _text(row.get("litter_id")),
        "Status": _text(row.get("status")),
        "On_Farm": _yes_no(row.get("on_farm")),
        "Purpose": _text(row.get("purpose")),
        "General_Notes": _text(row.get("notes")),
        "source": "supabase_canonical",
    } for row in rows]


def get_pig_master_rows(connect_factory=None):
    rows = _fetch_all(
        """
        select
            state.pig_id,
            state.tag_number,
            state.status,
            state.on_farm,
            state.litter_id,
            state.sex,
            state.current_weight_kg,
            state.last_weight_date,
            state.current_pen_id,
            pig.pig_name,
            pig.animal_type,
            pig.date_of_birth,
            pig.purpose,
            pig.notes,
            pig.exit_date,
            pig.exit_reason,
            pig.exit_order_id,
            pig.litter_size_born,
            pig.litter_size_weaned,
            pig.wean_date,
            pig.wean_weight_kg,
            pig.earmarked,
            pig.earmark_date
        from public.pig_current_state state
        join public.pigs pig on pig.pig_id = state.pig_id
        order by coalesce(nullif(state.tag_number, ''), state.pig_id)
        """,
        connect_factory=connect_factory,
    )
    return [{
        "Pig_ID": _text(row.get("pig_id")),
        "Tag_Number": _text(row.get("tag_number")),
        "Pig_Name": _text(row.get("pig_name")),
        "Litter_ID": _text(row.get("litter_id")),
        "Status": _text(row.get("status")),
        "On_Farm": _yes_no(row.get("on_farm")),
        "Animal_Type": _text(row.get("animal_type")),
        "Sex": _text(row.get("sex")),
        "Date_Of_Birth": _date_text(row.get("date_of_birth")),
        "Current_Weight_Kg": _float_or_none(row.get("current_weight_kg")),
        "Last_Weight_Date": _date_text(row.get("last_weight_date")),
        "Current_Pen_ID": _text(row.get("current_pen_id")),
        "Purpose": _text(row.get("purpose")),
        "General_Notes": _text(row.get("notes")),
        "Exit_Date": _date_text(row.get("exit_date")),
        "Exit_Reason": _text(row.get("exit_reason")),
        "Exit_Order_ID": _text(row.get("exit_order_id")),
        "Litter_Size_Born": _float_or_none(row.get("litter_size_born")),
        "Litter_Size_Weaned": _float_or_none(row.get("litter_size_weaned")),
        "Wean_Date": _date_text(row.get("wean_date")),
        "Wean_Weight_Kg": _float_or_none(row.get("wean_weight_kg")),
        "Earmarked": _yes_no(row.get("earmarked")),
        "Earmark_Date": _date_text(row.get("earmark_date")),
        "source": "supabase_canonical",
    } for row in rows]


def get_litter_register_rows(connect_factory=None):
    rows = _fetch_all(
        """
        select
            litter_id,
            farrowing_date,
            sow_pig_id,
            boar_pig_id,
            total_born,
            born_alive,
            stillborn_count,
            mummified_count,
            male_count,
            female_count,
            unknown_sex_count,
            weaned_count,
            wean_date,
            litter_status,
            litter_notes
        from public.litters
        order by farrowing_date desc nulls last, litter_id
        """,
        connect_factory=connect_factory,
    )
    return [{
        "Litter_ID": _text(row.get("litter_id")),
        "Farrowing_Date": _date_text(row.get("farrowing_date")),
        "Sow_Pig_ID": _text(row.get("sow_pig_id")),
        "Boar_Pig_ID": _text(row.get("boar_pig_id")),
        "Total_Born": _float_or_none(row.get("total_born")),
        "Born_Alive": _float_or_none(row.get("born_alive")),
        "Stillborn_Count": _float_or_none(row.get("stillborn_count")),
        "Mummified_Count": _float_or_none(row.get("mummified_count")),
        "Male_Count": _float_or_none(row.get("male_count")),
        "Female_Count": _float_or_none(row.get("female_count")),
        "Unknown_Sex_Count": _float_or_none(row.get("unknown_sex_count")),
        "Weaned_Count": _float_or_none(row.get("weaned_count")),
        "Litter_Size_Weaned": _float_or_none(row.get("weaned_count")),
        "Wean_Date": _date_text(row.get("wean_date")),
        "Litter_Status": _text(row.get("litter_status")),
        "Litter_Notes": _text(row.get("litter_notes")),
        "source": "supabase_canonical",
    } for row in rows]


def get_family_tree(pig_id, connect_factory=None):
    rows = _current_state_rows(connect_factory=connect_factory)
    lookup = {_text(row.get("pig_id")): row for row in rows if _text(row.get("pig_id"))}
    current_row = lookup.get(_text(pig_id))
    if not current_row:
        return None

    mother_pig_id = _text(current_row.get("mother_pig_id"))
    father_pig_id = _text(current_row.get("father_pig_id"))
    litter_id = _text(current_row.get("litter_id"))
    mother_row = lookup.get(mother_pig_id) if mother_pig_id else None
    father_row = lookup.get(father_pig_id) if father_pig_id else None
    siblings = []
    if litter_id:
        for row in rows:
            row_pig_id = _text(row.get("pig_id"))
            if _text(row.get("litter_id")) == litter_id and row_pig_id != pig_id:
                siblings.append(_pig_summary_card(row))
    siblings.sort(key=lambda item: (item["tag_number"] or item["pig_id"]).lower())

    return {
        "pig_id": pig_id,
        "current_pig": _pig_summary_card(current_row),
        "mother": _pig_summary_card(mother_row) if mother_row else None,
        "father": _pig_summary_card(father_row) if father_row else None,
        "siblings": siblings,
        "litter_id": litter_id,
        "sibling_count": len(siblings),
        "source": "supabase_canonical",
    }


def _allocation_overview_row(row):
    return {
        "Pig_ID": _text(row.get("pig_id")),
        "Tag_Number": _text(row.get("tag_number")),
        "Animal_Type": _text(row.get("animal_type")),
        "Sex": _text(row.get("sex")),
        "Status": _text(row.get("status")),
        "On_Farm": _yes_no(row.get("on_farm")),
        "Purpose": _text(row.get("purpose")),
        "Current_Pen_ID": _text(row.get("current_pen_id")),
        "Current_Pen_Name": _text(row.get("current_pen_name")),
        "Current_Weight_Kg": _float_or_none(row.get("current_weight_kg")),
        "Last_Weight_Date": _date_text(row.get("last_weight_date")),
        "Date_Of_Birth": _date_text(row.get("date_of_birth")),
        "Age_Days": _age_days(row.get("date_of_birth")),
        "Calculated_Stage": _calculated_stage(row),
        "Weight_Band": _weight_band(row.get("current_weight_kg")),
        "Litter_ID": _text(row.get("litter_id")),
        "Mother_Pig_ID": _text(row.get("mother_pig_id")),
        "Father_Pig_ID": _text(row.get("father_pig_id")),
    }


def get_allocation_input_rows(connect_factory=None):
    current_rows = _current_state_rows(connect_factory=connect_factory)
    weight_rows = _fetch_all(
        """
        select pig_id, weight_date, weight_kg
        from public.pig_weight_events
        order by pig_id, weight_date, created_at, weight_event_id
        """,
        connect_factory=connect_factory,
    )
    litter_rows = _fetch_all(
        """
        select litter_id, sow_pig_id, boar_pig_id, sow_tag_number, boar_tag_number,
               born_alive, weaned_count, litter_status
        from public.litters
        order by litter_id
        """,
        connect_factory=connect_factory,
    )
    pen_rows = _fetch_all(
        """
        select pen_id, pen_name, pen_type
        from public.pens
        where is_active is true
        """,
        connect_factory=connect_factory,
    )
    overview_rows = [_allocation_overview_row(row) for row in current_rows]
    pig_master_rows = [dict(row) for row in overview_rows]
    formatted_weight_rows = [{
        "Pig_ID": _text(row.get("pig_id")),
        "Weight_Date": _date_text(row.get("weight_date")),
        "Weight_Kg": _float_or_none(row.get("weight_kg")),
    } for row in weight_rows]
    formatted_litter_rows = [{
        "Litter_ID": _text(row.get("litter_id")),
        "Sow_Pig_ID": _text(row.get("sow_pig_id")),
        "Sow_Tag_Number": _text(row.get("sow_tag_number")),
        "Boar_Pig_ID": _text(row.get("boar_pig_id")),
        "Boar_Tag_Number": _text(row.get("boar_tag_number")),
        "Born_Alive": _float_or_none(row.get("born_alive")),
        "Weaned_Count": _float_or_none(row.get("weaned_count")),
        "Litter_Status": _text(row.get("litter_status")),
    } for row in litter_rows]
    pen_lookup = {
        _text(row.get("pen_id")): {
            "pen_id": _text(row.get("pen_id")),
            "pen_name": _text(row.get("pen_name")),
            "pen_type": _text(row.get("pen_type")),
        }
        for row in pen_rows
        if _text(row.get("pen_id"))
    }
    return {
        "overview_rows": overview_rows,
        "pig_master_rows": pig_master_rows,
        "weight_rows": formatted_weight_rows,
        "sales_rows": [],
        "litter_rows": formatted_litter_rows,
        "pen_lookup": pen_lookup,
        "source": "supabase_canonical",
    }


def _litter_rows_with_pigs(connect_factory=None):
    litters = _fetch_all(
        """
        select *
        from public.litters
        order by farrowing_date desc nulls last, litter_id
        """,
        connect_factory=connect_factory,
    )
    pigs = _current_state_rows(connect_factory=connect_factory)
    pigs_by_litter = {}
    for pig in pigs:
        litter_id = _text(pig.get("litter_id"))
        if litter_id:
            pigs_by_litter.setdefault(litter_id, []).append(pig)
    return litters, pigs_by_litter


def _empty_litter_lifecycle_outcomes():
    return {
        "total": 0,
        "active": 0,
        "sold": 0,
        "slaughtered": 0,
        "dead": 0,
        "removed": 0,
        "other": 0,
    }


def _litter_lifecycle_outcomes(pigs):
    outcomes = _empty_litter_lifecycle_outcomes()
    for pig in pigs or []:
        outcomes["total"] += 1
        outcome = _lifecycle_outcome_for_exit(pig)
        if outcome:
            outcomes[outcome] += 1
        elif _text(pig.get("status")).lower() == "active" and pig.get("on_farm") is True:
            outcomes["active"] += 1
        else:
            outcomes["other"] += 1
    return outcomes


def _derive_litter_status(litter, reconciliation, lifecycle_outcomes):
    explicit_status = _text(litter.get("litter_status"))
    if explicit_status and explicit_status.lower() != "unknown":
        return explicit_status
    if int(lifecycle_outcomes.get("total") or 0) <= 0:
        return "No piglets recorded"
    if int(lifecycle_outcomes.get("active") or 0) > 0:
        return "Active"
    if (_float_or_none(litter.get("weaned_count")) or 0) > 0:
        return "Weaned"
    terminal_count = sum(int(lifecycle_outcomes.get(key) or 0) for key in ("sold", "slaughtered", "dead", "removed"))
    if terminal_count >= int(lifecycle_outcomes.get("total") or 0):
        return "Completed"
    if int(reconciliation.get("linked_pig_records") or 0) > 0:
        return "Review"
    return "Unknown"


def _litter_reconciliation(litter, pigs):
    born_alive = _float_or_none(litter.get("born_alive"))
    total_born = _float_or_none(litter.get("total_born"))
    stillborn_count = _float_or_none(litter.get("stillborn_count")) or 0
    mummified_count = _float_or_none(litter.get("mummified_count")) or 0
    active = len([
        pig for pig in pigs
        if _text(pig.get("status")).lower() == "active" and pig.get("on_farm") is True
    ])
    exited = len(pigs) - active
    linked = len(pigs)
    non_live_reasons = {"stillborn", "mummified"}
    non_live_history_count = len([
        pig for pig in pigs
        if _text(pig.get("exit_reason")).lower().replace("-", "_").replace(" ", "_") in non_live_reasons
    ])
    stillborn_history_count = len([
        pig for pig in pigs
        if _text(pig.get("exit_reason")).lower().replace("-", "_").replace(" ", "_") == "stillborn"
    ])
    live_linked = linked - non_live_history_count
    non_live_count = int(stillborn_count) + int(mummified_count)
    source_counts_total = int(born_alive) + non_live_count if born_alive is not None else None
    source_counts_consistent = bool(
        total_born is not None
        and source_counts_total is not None
        and int(total_born) == source_counts_total
    )
    live_count_mismatch = bool(born_alive is not None and int(born_alive) != live_linked)
    total_record_mismatch = bool(total_born is not None and int(total_born) != linked)
    mismatch = live_count_mismatch or total_record_mismatch
    suggested_born_alive = live_linked
    if live_count_mismatch:
        recommended_action = "Review litter live-born records before changing Born Alive."
    elif total_record_mismatch:
        recommended_action = "Review missing or extra litter piglet records before changing counts."
    else:
        recommended_action = "No birth-count correction needed."
    return {
        "born_alive": born_alive,
        "total_born": total_born,
        "stillborn_count": stillborn_count,
        "mummified_count": mummified_count,
        "non_live_count": non_live_count,
        "linked_pig_records": linked,
        "live_linked_pig_records": live_linked,
        "active_pig_records": active,
        "exited_pig_records": exited,
        "stillborn_history_count": stillborn_history_count,
        "non_live_history_count": non_live_history_count,
        "suggested_born_alive": suggested_born_alive,
        "mismatch": mismatch,
        "formula_conflict": False,
        "source_counts_consistent": source_counts_consistent,
        "can_reconcile_birth_count": False,
        "delta": (suggested_born_alive - born_alive) if live_count_mismatch and born_alive is not None else 0,
        "rule": "Supabase canonical litter count comparison.",
        "recommended_action": recommended_action,
    }


def list_litter_overview(connect_factory=None):
    litters, pigs_by_litter = _litter_rows_with_pigs(connect_factory=connect_factory)
    result_rows = []
    for litter in litters:
        litter_id = _text(litter.get("litter_id"))
        pigs = pigs_by_litter.get(litter_id, [])
        reconciliation = _litter_reconciliation(litter, pigs)
        lifecycle_outcomes = _litter_lifecycle_outcomes(pigs)
        weights = [
            _float_or_none(pig.get("current_weight_kg"))
            for pig in pigs
            if _float_or_none(pig.get("current_weight_kg")) is not None
        ]
        tagged_count = len([pig for pig in pigs if _text(pig.get("tag_number"))])
        male_count = len([pig for pig in pigs if _text(pig.get("sex")) == "Male"])
        female_count = len([pig for pig in pigs if _text(pig.get("sex")) == "Female"])
        active_count = reconciliation["active_pig_records"]
        needs_attention = "Yes" if reconciliation["mismatch"] else ""
        result_rows.append({
            "litter_id": litter_id,
            "sow_pig_id": _text(litter.get("sow_pig_id")),
            "sow_tag_number": _text(litter.get("sow_tag_number")),
            "boar_pig_id": _text(litter.get("boar_pig_id")),
            "boar_tag_number": _text(litter.get("boar_tag_number")),
            "current_pen_id": "",
            "farrowing_date": _date_text(litter.get("farrowing_date")),
            "wean_date": "",
            "litter_status": _derive_litter_status(litter, reconciliation, lifecycle_outcomes),
            "needs_attention": needs_attention,
            "sheet_needs_attention": "",
            "attention_reason": reconciliation["recommended_action"] if needs_attention == "Yes" else "",
            "born_alive": reconciliation["born_alive"],
            "total_born": reconciliation["total_born"],
            "weaned_count": _float_or_none(litter.get("weaned_count")),
            "linked_pig_records": reconciliation["linked_pig_records"],
            "active_pig_records": active_count,
            "exited_pig_records": reconciliation["exited_pig_records"],
            "tagged_pig_count": tagged_count,
            "untagged_pig_count": max(0, len(pigs) - tagged_count),
            "male_count": male_count,
            "female_count": female_count,
            "average_current_weight_kg": _average(weights),
            "lifecycle_outcomes": lifecycle_outcomes,
            "reconciliation": reconciliation,
        })

    result_rows.sort(key=lambda item: (
        item["needs_attention"] != "Yes",
        item["farrowing_date"] or "9999-12-31",
        item["litter_id"],
    ))
    return {
        "success": True,
        "count": len(result_rows),
        "attention_count": sum(1 for item in result_rows if item["needs_attention"] == "Yes"),
        "mismatch_count": sum(1 for item in result_rows if item["reconciliation"]["mismatch"]),
        "formula_conflict_count": 0,
        "litters": result_rows,
        "source": {
            "reads_from": "supabase_canonical",
            "writes_to_sheets": False,
            "writes_to_supabase": False,
        },
    }


def get_litter_detail(litter_id, connect_factory=None):
    litters, pigs_by_litter = _litter_rows_with_pigs(connect_factory=connect_factory)
    litter = next((row for row in litters if _text(row.get("litter_id")) == _text(litter_id)), None)
    if not litter:
        return None
    pigs = pigs_by_litter.get(_text(litter_id), [])
    reconciliation = _litter_reconciliation(litter, pigs)
    lifecycle_outcomes = _litter_lifecycle_outcomes(pigs)
    piglets = []
    weights = []
    male_count = 0
    female_count = 0
    active_count = 0
    for pig in pigs:
        sex = _text(pig.get("sex"))
        if sex == "Male":
            male_count += 1
        elif sex == "Female":
            female_count += 1
        if _text(pig.get("status")).lower() == "active" and pig.get("on_farm") is True:
            active_count += 1
        weight = _float_or_none(pig.get("current_weight_kg"))
        if weight is not None:
            weights.append(weight)
        piglets.append({
            "pig_id": _text(pig.get("pig_id")),
            "tag_number": _text(pig.get("tag_number")),
            "sex": sex,
            "status": _text(pig.get("status")),
            "on_farm": _yes_no(pig.get("on_farm")),
            "date_of_birth": _date_text(pig.get("date_of_birth")),
            "age_days": _age_days(pig.get("date_of_birth")),
            "current_weight_kg": weight,
            "calculated_stage": _calculated_stage(pig),
            "current_pen_id": _text(pig.get("current_pen_id")),
        })
    piglets.sort(key=lambda item: (item["tag_number"] or item["pig_id"]).lower())
    return {
        "litter_id": _text(litter_id),
        "mother_pig_id": _text(litter.get("sow_pig_id")),
        "mother_tag_number": _text(litter.get("sow_tag_number")),
        "father_pig_id": _text(litter.get("boar_pig_id")),
        "father_tag_number": _text(litter.get("boar_tag_number")),
        "litter_status": _derive_litter_status(litter, reconciliation, lifecycle_outcomes),
        "count": len(piglets),
        "male_count": male_count,
        "female_count": female_count,
        "active_count": active_count,
        "average_weight_kg": _average(weights),
        "piglets": piglets,
        "attention": None,
        "reconciliation": reconciliation,
        "lifecycle_outcomes": lifecycle_outcomes,
        "wean_status": "",
        "wean_date": "",
        "source": "supabase_canonical",
    }


def get_litter_attention_summary(limit=5, connect_factory=None):
    overview = list_litter_overview(connect_factory=connect_factory)
    items = []
    for litter in overview.get("litters", []):
        if litter.get("needs_attention") != "Yes":
            continue
        items.append({
            "litter_id": litter.get("litter_id", ""),
            "sow_tag_number": litter.get("sow_tag_number", ""),
            "farrowing_date": litter.get("farrowing_date", ""),
            "wean_date": litter.get("wean_date", ""),
            "litter_status": litter.get("litter_status", ""),
            "needs_attention": litter.get("needs_attention", ""),
            "reason": litter.get("attention_reason") or "Review litter counts.",
            "action_type": "review_litter_counts",
            "recommended_action": litter.get("reconciliation", {}).get("recommended_action") or "Review litter counts.",
            "active_pig_count": litter.get("active_pig_records", 0),
            "weaned_count": None,
            "youngest_age_days": "",
            "oldest_age_days": "",
            "estimated_wean_date": "",
            "wean_tag_attention_start_date": "",
            "wean_planning_monday": "",
            "days_until_estimated_wean": None,
        })

    return {
        "count": len(items),
        "items": items[:limit],
        "source": "supabase_canonical",
    }


def get_breeding_options(connect_factory=None):
    rows = _current_state_rows(connect_factory=connect_factory)
    sows = []
    boars = []
    for row in rows:
        if _text(row.get("status")) != "Active" or row.get("on_farm") is not True:
            continue
        if _text(row.get("purpose")) != "Breeding":
            continue
        item = {
            "pig_id": _text(row.get("pig_id")),
            "tag_number": _text(row.get("tag_number")) or _text(row.get("pig_id")),
            "current_pen_id": _text(row.get("current_pen_id")),
            "current_pen_name": _text(row.get("current_pen_name")),
        }
        sex = _text(row.get("sex"))
        if sex == "Female":
            sows.append(item)
        if sex in ("Male", "Castrated_Male"):
            boars.append(item)
    sows.sort(key=lambda item: item["tag_number"].lower())
    boars.sort(key=lambda item: item["tag_number"].lower())
    return {"sows": sows, "boars": boars, "source": "supabase_canonical"}


def _mating_status(row):
    pregnancy_result = _text(row.get("pregnancy_check_result")).lower().replace(" ", "_")
    outcome = _text(row.get("outcome")).lower().replace(" ", "_")
    if _text(row.get("related_litter_id")) or row.get("farrowing_date") or outcome == "farrowed":
        return "Farrowed"
    if pregnancy_result == "pregnant" or outcome == "pregnant":
        return "Confirmed_Pregnant"
    if pregnancy_result == "not_pregnant" or outcome in {"not_pregnant", "repeat_required"}:
        return "Repeat_Service"
    return "Open"


def _mating_is_open(row):
    return "Yes" if _mating_status(row) in {"Open", "Confirmed_Pregnant"} else "No"


def _days_since(value):
    if not isinstance(value, date):
        return ""
    return str((date.today() - value).days)


def get_mating_overview(connect_factory=None):
    rows = _fetch_all(
        """
        select *
        from public.mating_events
        order by mating_date desc nulls last, mating_id desc
        """,
        connect_factory=connect_factory,
    )
    state_rows = {row["pig_id"]: row for row in _current_state_rows(connect_factory=connect_factory)}
    records = []
    today = date.today()
    for row in rows:
        sow = state_rows.get(_text(row.get("sow_pig_id")), {})
        boar = state_rows.get(_text(row.get("boar_pig_id")), {})
        status = _mating_status(row)
        is_open = _mating_is_open(row)
        expected_check = row.get("expected_pregnancy_check_date")
        expected_farrowing = row.get("expected_farrowing_date")
        records.append({
            "mating_id": _text(row.get("mating_id")),
            "sow_pig_id": _text(row.get("sow_pig_id")),
            "sow_tag_number": _text(row.get("sow_tag_number")),
            "sow_current_pen_id": _text(sow.get("current_pen_id")),
            "sow_current_pen_name": _text(sow.get("current_pen_name")),
            "boar_pig_id": _text(row.get("boar_pig_id")),
            "boar_tag_number": _text(row.get("boar_tag_number")),
            "boar_current_pen_id": _text(boar.get("current_pen_id")),
            "boar_current_pen_name": _text(boar.get("current_pen_name")),
            "mating_date": _date_text(row.get("mating_date")),
            "mating_method": _text(row.get("mating_method")),
            "exposure_group": _text(row.get("exposure_group")),
            "expected_pregnancy_check_date": _date_text(expected_check),
            "pregnancy_check_date": _date_text(row.get("pregnancy_check_date")),
            "pregnancy_check_result": _text(row.get("pregnancy_check_result")),
            "expected_farrowing_date": _date_text(expected_farrowing),
            "actual_farrowing_date": _date_text(row.get("farrowing_date")),
            "mating_status": status,
            "outcome": _text(row.get("outcome")),
            "linked_litter_id": _text(row.get("related_litter_id")),
            "days_since_mating": _days_since(row.get("mating_date")),
            "is_open": is_open,
            "is_overdue_check": "Yes" if is_open == "Yes" and isinstance(expected_check, date) and expected_check < today and not row.get("pregnancy_check_result") else "No",
            "is_overdue_farrowing": "Yes" if is_open == "Yes" and isinstance(expected_farrowing, date) and expected_farrowing < today and not row.get("farrowing_date") else "No",
            "service_notes": _text(row.get("mating_notes")),
            "created_at": _date_text(row.get("created_at")),
            "updated_at": _date_text(row.get("updated_at")),
        })
    return records


def _blank_breeding_metric(pig_id, tag_number):
    return {
        "pig_id": pig_id,
        "tag_number": tag_number,
        "mating_count": 0,
        "confirmed_pregnant_count": 0,
        "repeat_service_count": 0,
        "farrowed_count": 0,
        "open_count": 0,
        "litter_count": 0,
        "born_alive_total": 0,
        "weaned_total": 0,
        "average_born_alive": None,
        "average_weaned": None,
        "survival_pct": None,
    }


def _metric_for(metrics, pig_id, tag_number):
    if not pig_id:
        return None
    if pig_id not in metrics:
        metrics[pig_id] = _blank_breeding_metric(pig_id, tag_number)
    if tag_number and not metrics[pig_id]["tag_number"]:
        metrics[pig_id]["tag_number"] = tag_number
    return metrics[pig_id]


def _finish_breeding_metrics(metrics):
    rows = []
    for metric in metrics.values():
        litter_count = metric["litter_count"]
        born_alive_total = metric["born_alive_total"]
        weaned_total = metric["weaned_total"]
        if litter_count:
            metric["average_born_alive"] = round(born_alive_total / litter_count, 2)
            metric["average_weaned"] = round(weaned_total / litter_count, 2)
        if born_alive_total:
            metric["survival_pct"] = round((weaned_total / born_alive_total) * 100, 1)
        rows.append(metric)
    return sorted(rows, key=lambda item: (-item["litter_count"], -item["farrowed_count"], str(item["tag_number"] or item["pig_id"]).lower()))


def get_breeding_analytics(connect_factory=None):
    mating_rows = get_mating_overview(connect_factory=connect_factory)
    litter_overview = list_litter_overview(connect_factory=connect_factory)
    sow_metrics = {}
    boar_metrics = {}

    for row in mating_rows:
        targets = [
            _metric_for(sow_metrics, row.get("sow_pig_id", ""), row.get("sow_tag_number", "")),
            _metric_for(boar_metrics, row.get("boar_pig_id", ""), row.get("boar_tag_number", "")),
        ]
        pregnancy_result = _text(row.get("pregnancy_check_result")).lower()
        mating_status = _text(row.get("mating_status")).lower()
        outcome = _text(row.get("outcome")).lower()
        confirmed = pregnancy_result == "pregnant" or mating_status in {"confirmed_pregnant", "farrowed"} or outcome in {"pregnant", "farrowed"}
        repeat_service = pregnancy_result == "not_pregnant" or mating_status == "repeat_service" or outcome == "repeat_required"
        farrowed = bool(row.get("linked_litter_id")) or mating_status == "farrowed" or outcome == "farrowed"
        is_open = row.get("is_open") == "Yes"
        for metric in [metric for metric in targets if metric]:
            metric["mating_count"] += 1
            metric["confirmed_pregnant_count"] += 1 if confirmed else 0
            metric["repeat_service_count"] += 1 if repeat_service else 0
            metric["farrowed_count"] += 1 if farrowed else 0
            metric["open_count"] += 1 if is_open else 0

    for row in litter_overview.get("litters", []):
        targets = [
            _metric_for(sow_metrics, row.get("sow_pig_id", ""), row.get("sow_tag_number", "")),
            _metric_for(boar_metrics, row.get("boar_pig_id", ""), row.get("boar_tag_number", "")),
        ]
        born_alive = _float_or_none(row.get("born_alive")) or 0
        weaned_count = _float_or_none(row.get("weaned_count")) or 0
        for metric in [metric for metric in targets if metric]:
            metric["litter_count"] += 1
            metric["born_alive_total"] += born_alive
            metric["weaned_total"] += weaned_count

    sows = _finish_breeding_metrics(sow_metrics)
    boars = _finish_breeding_metrics(boar_metrics)
    return {
        "success": True,
        "mode": "read_only",
        "summary": {
            "sow_count": len(sows),
            "boar_count": len(boars),
            "mating_count": len(mating_rows),
            "litter_count": litter_overview.get("count", 0),
        },
        "sows": sows,
        "boars": boars,
        "source": {
            "mating_source": "supabase_canonical",
            "litter_source": "supabase_canonical",
            "writes_to_google_sheets": False,
            "writes_to_supabase": False,
        },
    }


def _tag_for_pig(pig_id, connect_factory=None):
    row = _fetch_one("select tag_number from public.pigs where pig_id = %s", (pig_id,), connect_factory=connect_factory)
    return _text(row.get("tag_number")) if row else ""


def get_weight_history_for_pig(pig_id, connect_factory=None):
    rows = _fetch_all(
        """
        select weight_event_id, pig_id, weight_date, weight_kg, weighed_by, condition_notes
        from public.pig_weight_events
        where pig_id = %s
        order by weight_date desc, created_at desc, weight_event_id desc
        """,
        (pig_id,),
        connect_factory=connect_factory,
    )
    tag_number = _tag_for_pig(pig_id, connect_factory=connect_factory)
    history = []
    for row in rows:
        history.append({
            "weight_log_id": _text(row.get("weight_event_id")),
            "pig_id": pig_id,
            "tag_number": tag_number,
            "weight_date": row.get("weight_date"),
            "weight_date_display": _date_text(row.get("weight_date")),
            "weight_kg": _float_or_none(row.get("weight_kg")),
            "weighed_by": _text(row.get("weighed_by")),
            "condition_notes": _text(row.get("condition_notes")),
        })
    for index, entry in enumerate(history):
        previous_entry = history[index + 1] if index + 1 < len(history) else None
        if previous_entry and entry["weight_kg"] is not None and previous_entry["weight_kg"] is not None:
            entry["difference_kg"] = round(entry["weight_kg"] - previous_entry["weight_kg"], 2)
        else:
            entry["difference_kg"] = None
        if previous_entry and entry["weight_date"] and previous_entry["weight_date"]:
            entry["days_since_previous"] = (entry["weight_date"] - previous_entry["weight_date"]).days
        else:
            entry["days_since_previous"] = None
        if entry["difference_kg"] is not None and entry["days_since_previous"] and entry["days_since_previous"] > 0:
            entry["growth_rate_kg_day"] = round(entry["difference_kg"] / entry["days_since_previous"], 3)
        else:
            entry["growth_rate_kg_day"] = None
        entry.pop("weight_date", None)
    return {"pig_id": pig_id, "tag_number": tag_number, "count": len(history), "history": history}


def get_movement_history_for_pig(pig_id, connect_factory=None):
    rows = _fetch_all(
        """
        select
            event.location_event_id,
            event.pig_id,
            event.move_date,
            event.from_pen_id,
            event.to_pen_id,
            from_pen.pen_name as from_pen_name,
            to_pen.pen_name as to_pen_name,
            event.reason_for_move,
            event.moved_by,
            event.move_notes
        from public.pig_location_events event
        left join public.pens from_pen on from_pen.pen_id = event.from_pen_id
        left join public.pens to_pen on to_pen.pen_id = event.to_pen_id
        where event.pig_id = %s
        order by event.move_date desc, event.created_at desc, event.location_event_id desc
        """,
        (pig_id,),
        connect_factory=connect_factory,
    )
    pig = get_pig_detail(pig_id, connect_factory=connect_factory) or {}
    history = [{
        "move_log_id": _text(row.get("location_event_id")),
        "pig_id": pig_id,
        "tag_number": _text(pig.get("tag_number")),
        "move_date_display": _date_text(row.get("move_date")),
        "from_pen_id": _text(row.get("from_pen_id")),
        "to_pen_id": _text(row.get("to_pen_id")),
        "from_pen_name": _text(row.get("from_pen_name")) or _text(row.get("from_pen_id")),
        "to_pen_name": _text(row.get("to_pen_name")) or _text(row.get("to_pen_id")),
        "reason_for_move": _text(row.get("reason_for_move")),
        "moved_by": _text(row.get("moved_by")),
        "move_notes": _text(row.get("move_notes")),
    } for row in rows]
    return {
        "pig_id": pig_id,
        "tag_number": _text(pig.get("tag_number")),
        "current_pen_id": _text(pig.get("current_pen_id")),
        "count": len(history),
        "history": history,
    }


def get_treatment_history_for_pig(pig_id, connect_factory=None):
    rows = _fetch_all(
        """
        select *
        from public.pig_medical_events
        where pig_id = %s
        order by treatment_date desc, created_at desc, medical_event_id desc
        """,
        (pig_id,),
        connect_factory=connect_factory,
    )
    tag_number = _tag_for_pig(pig_id, connect_factory=connect_factory)
    history = [{
        "medical_log_id": _text(row.get("medical_event_id")),
        "pig_id": pig_id,
        "tag_number": tag_number,
        "treatment_date_display": _date_text(row.get("treatment_date")),
        "treatment_type": _text(row.get("treatment_type")),
        "product_id": _text(row.get("product_id")),
        "product_name": _text(row.get("product_name")),
        "dose": _float_or_none(row.get("dose")),
        "dose_unit": _text(row.get("dose_unit")),
        "route": _text(row.get("route")),
        "reason_for_treatment": _text(row.get("reason_for_treatment")),
        "batch_lot_number": _text(row.get("batch_lot_number")),
        "withdrawal_days": _float_or_none(row.get("withdrawal_days")),
        "withdrawal_end_date": _date_text(row.get("withdrawal_end_date")),
        "given_by": _text(row.get("given_by")),
        "follow_up_required": _yes_no(row.get("follow_up_required")),
        "follow_up_date": _date_text(row.get("follow_up_date")),
        "medical_notes": _text(row.get("medical_notes")),
    } for row in rows]
    return {"pig_id": pig_id, "tag_number": tag_number, "count": len(history), "history": history}


def get_latest_weight_for_pig(pig_id, connect_factory=None):
    row = _fetch_one(
        """
        select state.pig_id, state.tag_number, state.current_weight_kg, state.last_weight_date
        from public.pig_current_state state
        where state.pig_id = %s
        """,
        (pig_id,),
        connect_factory=connect_factory,
    )
    if not row:
        return {"pig_id": pig_id, "tag_number": "", "previous_weight_kg": None, "previous_weight_date": ""}
    return {
        "pig_id": pig_id,
        "tag_number": _text(row.get("tag_number")),
        "previous_weight_kg": _float_or_none(row.get("current_weight_kg")),
        "previous_weight_date": _date_text(row.get("last_weight_date")),
    }


def get_weight_entries_by_date(weight_date, connect_factory=None):
    rows = _fetch_all(
        """
        select event.weight_event_id, event.pig_id, pig.tag_number, state.current_pen_id,
               event.weight_date, event.weight_kg, event.weighed_by, event.condition_notes
        from public.pig_weight_events event
        left join public.pigs pig on pig.pig_id = event.pig_id
        left join public.pig_current_state state on state.pig_id = event.pig_id
        where event.weight_date = %s
        order by coalesce(nullif(pig.tag_number, ''), event.pig_id), event.pig_id
        """,
        (weight_date,),
        connect_factory=connect_factory,
    )
    history = [{
        "weight_log_id": _text(row.get("weight_event_id")),
        "pig_id": _text(row.get("pig_id")),
        "tag_number": _text(row.get("tag_number")),
        "current_pen_id": _text(row.get("current_pen_id")),
        "weight_date_display": _date_text(row.get("weight_date")),
        "weight_kg": _float_or_none(row.get("weight_kg")),
        "weighed_by": _text(row.get("weighed_by")),
        "condition_notes": _text(row.get("condition_notes")),
    } for row in rows]
    return {"weight_date": _date_text(weight_date), "count": len(history), "history": history}


def get_weight_report(date_from, date_to, pen_id="", connect_factory=None):
    rows = _fetch_all(
        """
        select
            event.weight_event_id,
            event.pig_id,
            event.weight_date,
            event.weight_kg,
            event.weighed_by,
            event.condition_notes,
            state.tag_number,
            state.status,
            state.on_farm,
            state.current_pen_id,
            state.current_pen_name,
            state.animal_type,
            state.current_weight_kg
        from public.pig_weight_events event
        left join public.pig_current_state state on state.pig_id = event.pig_id
        where event.weight_date <= %s
        order by event.pig_id, event.weight_date, event.created_at, event.weight_event_id
        """,
        (date_to,),
        connect_factory=connect_factory,
    )
    selected_pen_id = _text(pen_id)
    weights_by_pig = {}
    same_day_counts = {}
    for row in rows:
        pig_id = _text(row.get("pig_id"))
        weight_date = row.get("weight_date")
        weight_kg = _float_or_none(row.get("weight_kg"))
        if not pig_id or not weight_date or weight_kg is None:
            continue
        current_pen_id = _text(row.get("current_pen_id"))
        if selected_pen_id and current_pen_id != selected_pen_id:
            continue
        item = {
            "weight_log_id": _text(row.get("weight_event_id")),
            "pig_id": pig_id,
            "weight_date": weight_date,
            "weight_kg": weight_kg,
            "weighed_by": _text(row.get("weighed_by")),
            "condition_notes": _text(row.get("condition_notes")),
            "tag_number": _text(row.get("tag_number")),
            "status": _text(row.get("status")),
            "on_farm": _yes_no(row.get("on_farm")),
            "current_pen_id": current_pen_id,
            "current_pen_name": _text(row.get("current_pen_name")) or current_pen_id,
            "calculated_stage": _calculated_stage(row),
            "weight_band": _weight_band(row.get("current_weight_kg")),
        }
        weights_by_pig.setdefault(pig_id, []).append(item)
        key = (pig_id, weight_date.isoformat())
        same_day_counts[key] = same_day_counts.get(key, 0) + 1

    entries = []
    for pig_id, pig_weights in weights_by_pig.items():
        pig_weights.sort(key=lambda item: item["weight_date"])
        for index, item in enumerate(pig_weights):
            if item["weight_date"] < date_from or item["weight_date"] > date_to:
                continue
            previous_entry = None
            for previous_index in range(index - 1, -1, -1):
                candidate = pig_weights[previous_index]
                if candidate["weight_date"] < item["weight_date"]:
                    previous_entry = candidate
                    break
            difference_kg = None
            days_since_previous = None
            growth_rate_kg_day = None
            if previous_entry:
                difference_kg = round(item["weight_kg"] - previous_entry["weight_kg"], 2)
                days_since_previous = (item["weight_date"] - previous_entry["weight_date"]).days
                if days_since_previous > 0:
                    growth_rate_kg_day = round(difference_kg / days_since_previous, 3)
            duplicate_entry_count = same_day_counts.get((pig_id, item["weight_date"].isoformat()), 0)
            entries.append({
                "weight_log_id": item["weight_log_id"],
                "pig_id": pig_id,
                "tag_number": item["tag_number"],
                "status": item["status"],
                "on_farm": item["on_farm"],
                "active_on_farm": item["status"].lower() == "active" and item["on_farm"].lower() == "yes",
                "weight_date": item["weight_date"].isoformat(),
                "weight_kg": item["weight_kg"],
                "previous_weight_kg": previous_entry["weight_kg"] if previous_entry else None,
                "previous_weight_date": previous_entry["weight_date"].isoformat() if previous_entry else "",
                "difference_kg": difference_kg,
                "days_since_previous": days_since_previous,
                "growth_rate_kg_day": growth_rate_kg_day,
                "current_pen_id": item["current_pen_id"],
                "current_pen_name": item["current_pen_name"],
                "calculated_stage": item["calculated_stage"],
                "weight_band": item["weight_band"],
                "weighed_by": item["weighed_by"],
                "condition_notes": item["condition_notes"],
                "duplicate_same_day": duplicate_entry_count > 1,
                "duplicate_entry_count": duplicate_entry_count,
            })

    entries.sort(key=lambda item: (
        item["current_pen_name"] or item["current_pen_id"],
        _tag_sort_key(item["tag_number"], item["pig_id"]),
        item["pig_id"],
        item["weight_date"],
    ))

    pen_groups = {}
    for entry in entries:
        group_key = entry["current_pen_id"] or "Unknown"
        group = pen_groups.setdefault(group_key, {
            "pen_id": entry["current_pen_id"],
            "pen_name": entry["current_pen_name"],
            "entry_count": 0,
            "pig_ids": set(),
            "weights": [],
            "differences": [],
            "weight_loss_count": 0,
        })
        group["entry_count"] += 1
        group["pig_ids"].add(entry["pig_id"])
        group["weights"].append(entry["weight_kg"])
        group["differences"].append(entry["difference_kg"])
        if entry["difference_kg"] is not None and entry["difference_kg"] < 0:
            group["weight_loss_count"] += 1

    pen_summary = [{
        "pen_id": group["pen_id"],
        "pen_name": group["pen_name"],
        "entry_count": group["entry_count"],
        "unique_pigs": len(group["pig_ids"]),
        "average_weight_kg": _average(group["weights"]),
        "average_difference_kg": _average(group["differences"]),
        "weight_loss_count": group["weight_loss_count"],
    } for group in pen_groups.values()]
    pen_summary.sort(key=lambda item: (item["pen_name"] or item["pen_id"] or ""))

    unique_pig_ids = {entry["pig_id"] for entry in entries}
    differences = [entry["difference_kg"] for entry in entries]
    growth_rates = [entry["growth_rate_kg_day"] for entry in entries]
    loss_flags = [
        entry for entry in entries
        if entry["difference_kg"] is not None and entry["difference_kg"] < 0
    ]

    return {
        "success": True,
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "pen_id": selected_pen_id,
        "summary": {
            "total_entries": len(entries),
            "unique_pigs": len(unique_pig_ids),
            "average_weight_kg": _average([entry["weight_kg"] for entry in entries]),
            "average_difference_kg": _average(differences),
            "average_growth_rate_kg_day": _average(growth_rates),
            "weight_loss_count": len(loss_flags),
            "weight_gain_count": len([
                entry for entry in entries
                if entry["difference_kg"] is not None and entry["difference_kg"] > 0
            ]),
            "no_previous_weight_count": len([
                entry for entry in entries
                if entry["previous_weight_kg"] is None
            ]),
            "duplicate_same_day_count": len([entry for entry in entries if entry["duplicate_same_day"]]),
            "not_active_on_farm_count": len([
                entry for entry in entries
                if not entry["active_on_farm"]
            ]),
        },
        "pen_summary": pen_summary,
        "loss_flags": loss_flags,
        "entries": entries,
        "source": "supabase_canonical",
    }
