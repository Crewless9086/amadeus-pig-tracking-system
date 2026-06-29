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
            pig.notes
        from public.pig_current_state state
        join public.pigs pig on pig.pig_id = state.pig_id
        order by coalesce(nullif(state.tag_number, ''), state.pig_id)
        """,
        connect_factory=connect_factory,
    )


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
