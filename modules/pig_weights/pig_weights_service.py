from datetime import datetime

from services.google_sheets_service import get_all_records, append_row
from modules.pig_weights.pig_weights_config import PIG_WEIGHTS_CONFIG
from modules.pig_weights.pig_weights_utils import (
    to_clean_string,
    to_float,
    parse_sheet_date,
    format_date_for_json,
    format_date_for_sheet,
    generate_weight_log_id,
    generate_medical_log_id,
    generate_move_log_id,
    generate_pig_id,
    generate_product_id,
    generate_pen_id,
    generate_litter_id,
)
from modules.pig_weights.mating_service import link_litter_to_mating


def _build_pig_lookup(rows, columns):
    pig_lookup = {}
    for row in rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id:
            pig_lookup[row_pig_id] = row
    return pig_lookup


def _pig_summary_card(row, columns):
    return {
        "pig_id": to_clean_string(row.get(columns["pig_id"], "")),
        "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
        "sex": to_clean_string(row.get("Sex", "")),
        "status": to_clean_string(row.get(columns["status"], "")),
        "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
        "date_of_birth": format_date_for_json(row.get("Date_Of_Birth", "")),
        "age_days": row.get("Age_Days", ""),
        "current_weight_kg": to_float(row.get(columns["current_weight"], "")),
        "calculated_stage": to_clean_string(row.get("Calculated_Stage", "")),
        "current_pen_id": to_clean_string(row.get("Current_Pen_ID", "")),
        "litter_id": to_clean_string(row.get("Litter_ID", "")),
    }


def get_dashboard_summary():
    columns = PIG_WEIGHTS_CONFIG["columns"]

    pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    sales_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["sales_availability"])

    active_pigs = 0
    on_farm_pigs = 0

    for row in pig_rows:
        status = to_clean_string(row.get(columns["status"], ""))
        on_farm = to_clean_string(row.get(columns["on_farm"], ""))

        if status == "Active":
            active_pigs += 1
        if on_farm == "Yes":
            on_farm_pigs += 1

    sale_ready_count = 0
    available_for_sale_count = 0
    reserved_count = 0
    withdrawal_hold_count = 0

    for row in sales_rows:
        available_for_sale = to_clean_string(row.get(columns["available_for_sale"], ""))
        reserved_status = to_clean_string(row.get(columns["reserved_status"], ""))
        withdrawal_clear = to_clean_string(row.get(columns["withdrawal_clear"], ""))

        if available_for_sale == "Yes":
            available_for_sale_count += 1

        if reserved_status == "Reserved":
            reserved_count += 1

        if withdrawal_clear == "No":
            withdrawal_hold_count += 1

        if available_for_sale == "Yes" and withdrawal_clear == "Yes":
            sale_ready_count += 1

    return {
        "active_pigs": active_pigs,
        "on_farm_pigs": on_farm_pigs,
        "sale_ready_pigs": sale_ready_count,
        "available_for_sale_pigs": available_for_sale_count,
        "reserved_pigs": reserved_count,
        "withdrawal_hold_pigs": withdrawal_hold_count,
    }


def get_sales_stock_summary():
    rows = get_all_records("SALES_STOCK_SUMMARY")
    records = []

    for row in rows:
        sale_category = to_clean_string(row.get("Sale_Category", ""))
        weight_band = to_clean_string(row.get("Weight_Band", ""))

        if not sale_category or not weight_band:
            continue

        records.append({
            "sale_category": sale_category,
            "category_code": to_clean_string(row.get("Category_Code", "")),
            "age_range": to_clean_string(row.get("Age_Range", "")),
            "weight_band": weight_band,
            "qty_available": to_float(row.get("Qty_Available", "")) or 0,
            "male_qty": to_float(row.get("Male_Qty", "")) or 0,
            "female_qty": to_float(row.get("Female_Qty", "")) or 0,
            "castrated_male_qty": to_float(row.get("Castrated_Male_Qty", "")) or 0,
            "price_range": to_clean_string(row.get("Price_Range", "")),
            "status": to_clean_string(row.get("Status", "")),
        })

    return records


def get_sales_stock_totals():
    rows = get_all_records("SALES_STOCK_TOTALS")
    records = []

    for row in rows:
        sale_category = to_clean_string(row.get("Sale_Category", ""))

        if not sale_category:
            continue

        records.append({
            "sale_category": sale_category,
            "category_code": to_clean_string(row.get("Category_Code", "")),
            "age_range": to_clean_string(row.get("Age_Range", "")),
            "weight_range": to_clean_string(row.get("Weight_Range", "")),
            "qty_available": to_float(row.get("Qty_Available", "")) or 0,
            "male_qty": to_float(row.get("Male_Qty", "")) or 0,
            "female_qty": to_float(row.get("Female_Qty", "")) or 0,
            "castrated_male_qty": to_float(row.get("Castrated_Male_Qty", "")) or 0,
            "price_range": to_clean_string(row.get("Price_Range", "")),
            "status": to_clean_string(row.get("Status", "")),
        })

    return records


def get_parent_options():
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    rows = get_all_records(sheet_name)

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
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        tag_number = to_clean_string(row.get(columns["tag_number"], ""))
        sex = to_clean_string(row.get("Sex", ""))
        status = to_clean_string(row.get(columns["status"], ""))
        purpose = to_clean_string(row.get("Purpose", ""))
        current_pen_id = to_clean_string(row.get(columns["current_pen_id"], ""))

        if not pig_id:
            continue

        option = {
            "pig_id": pig_id,
            "tag_number": tag_number or pig_id,
            "sex": sex,
            "status": status,
            "purpose": purpose,
            "current_pen_id": current_pen_id,
        }

        if sex == "Female" and status == "Active" and purpose == "Breeding":
            mother_options.append(option)

        if sex in ("Male", "Castrated_Male") and status == "Active" and purpose == "Breeding":
            father_options.append(option)

    return {
        "mothers": mother_options,
        "fathers": father_options,
    }


def get_active_pigs():
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    active_pigs = []
    for row in rows:
        if (
            str(row.get(columns["status"], "")).strip() == "Active"
            and str(row.get(columns["on_farm"], "")).strip() == "Yes"
        ):
            active_pigs.append({
                "pig_id": to_clean_string(row.get(columns["pig_id"], "")),
                "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
                "status": to_clean_string(row.get(columns["status"], "")),
                "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
                "current_weight_kg": row.get(columns["current_weight"], ""),
                "last_weight_date": format_date_for_json(row.get(columns["last_weight_date"], "")),
                "current_pen_id": to_clean_string(row.get(columns["current_pen_id"], "")),
            })

    return active_pigs


def get_sales_availability():
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["sales_availability"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)
    sales_rows = []

    for row in rows:
        sales_rows.append({
            "pig_id": to_clean_string(row.get(columns["pig_id"], "")),
            "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
            "sex": to_clean_string(row.get(columns["sex"], "")),
            "date_of_birth": format_date_for_json(row.get("Date_Of_Birth", "")),
            "age_days": row.get(columns["age_days"], ""),
            "current_weight_kg": to_float(row.get(columns["current_weight"], "")),
            "last_weight_date": format_date_for_json(row.get(columns["last_weight_date"], "")),
            "average_daily_gain_kg": to_float(row.get(columns["average_daily_gain"], "")),
            "calculated_stage": to_clean_string(row.get(columns["calculated_stage"], "")),
            "weight_band": to_clean_string(row.get(columns["weight_band"], "")),
            "current_pen_id": to_clean_string(row.get(columns["current_pen_id"], "")),
            "status": to_clean_string(row.get(columns["status"], "")),
            "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
            "withdrawal_clear": to_clean_string(row.get(columns["withdrawal_clear"], "")),
            "reserved_status": to_clean_string(row.get(columns["reserved_status"], "")),
            "reserved_for_order_id": to_clean_string(row.get(columns["reserved_for_order_id"], "")),
            "available_for_sale": to_clean_string(row.get(columns["available_for_sale"], "")),
            "sale_category": to_clean_string(row.get(columns["sale_category"], "")),
            "suggested_price_category": to_clean_string(row.get(columns["suggested_price_category"], "")),
            "sales_notes": to_clean_string(row.get(columns["sales_notes"], "")),
        })

    return sales_rows


def get_family_tree(pig_id: str):
    pig_id = str(pig_id).strip()

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]
    rows = get_all_records(sheet_name)

    pig_lookup = _build_pig_lookup(rows, columns)
    current_row = pig_lookup.get(pig_id)

    if not current_row:
        return None

    current_pig = _pig_summary_card(current_row, columns)

    mother_pig_id = to_clean_string(current_row.get("Mother_Pig_ID", ""))
    father_pig_id = to_clean_string(current_row.get("Father_Pig_ID", ""))
    litter_id = to_clean_string(current_row.get("Litter_ID", ""))

    mother_row = pig_lookup.get(mother_pig_id) if mother_pig_id else None
    father_row = pig_lookup.get(father_pig_id) if father_pig_id else None

    mother = _pig_summary_card(mother_row, columns) if mother_row else None
    father = _pig_summary_card(father_row, columns) if father_row else None

    siblings = []
    if litter_id:
        for row in rows:
            row_litter_id = to_clean_string(row.get("Litter_ID", ""))
            row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
            if row_litter_id == litter_id and row_pig_id != pig_id:
                siblings.append(_pig_summary_card(row, columns))

    siblings = sorted(
        siblings,
        key=lambda x: (x["tag_number"] or x["pig_id"]).lower()
    )

    return {
        "pig_id": pig_id,
        "current_pig": current_pig,
        "mother": mother,
        "father": father,
        "siblings": siblings,
        "litter_id": litter_id,
        "sibling_count": len(siblings),
    }


def get_litter_detail(litter_id: str):
    litter_id = str(litter_id).strip()

    if not litter_id:
        return None

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    pig_lookup = {}
    litter_rows = []

    for row in rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id:
            pig_lookup[row_pig_id] = row

        row_litter_id = to_clean_string(row.get("Litter_ID", ""))
        if row_litter_id == litter_id:
            litter_rows.append(row)

    if not litter_rows:
        litter_rows_sheet = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["litter_register"])
        for row in litter_rows_sheet:
            if to_clean_string(row.get("Litter_ID", "")) == litter_id:
                return {
                    "litter_id": litter_id,
                    "mother_pig_id": to_clean_string(row.get("Sow_Pig_ID", "")),
                    "mother_tag_number": to_clean_string(row.get("Sow_Tag_Number", "")),
                    "father_pig_id": to_clean_string(row.get("Boar_Pig_ID", "")),
                    "father_tag_number": to_clean_string(row.get("Boar_Tag_Number", "")),
                    "count": 0,
                    "male_count": row.get("Male_Count", ""),
                    "female_count": row.get("Female_Count", ""),
                    "active_count": 0,
                    "average_weight_kg": None,
                    "piglets": [],
                }
        return None

    first_row = litter_rows[0]

    mother_pig_id = to_clean_string(first_row.get("Mother_Pig_ID", ""))
    father_pig_id = to_clean_string(first_row.get("Father_Pig_ID", ""))

    mother_row = pig_lookup.get(mother_pig_id) if mother_pig_id else None
    father_row = pig_lookup.get(father_pig_id) if father_pig_id else None

    mother_tag_number = to_clean_string(mother_row.get(columns["tag_number"], "")) if mother_row else ""
    father_tag_number = to_clean_string(father_row.get(columns["tag_number"], "")) if father_row else ""

    piglets = []
    male_count = 0
    female_count = 0
    active_count = 0
    weight_values = []

    for row in litter_rows:
        sex = to_clean_string(row.get("Sex", ""))
        status = to_clean_string(row.get(columns["status"], ""))
        current_weight = to_float(row.get(columns["current_weight"], ""))

        if sex == "Male":
            male_count += 1
        elif sex == "Female":
            female_count += 1

        if status == "Active":
            active_count += 1

        if current_weight is not None:
            weight_values.append(current_weight)

        piglets.append({
            "pig_id": to_clean_string(row.get(columns["pig_id"], "")),
            "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
            "sex": sex,
            "status": status,
            "on_farm": to_clean_string(row.get(columns["on_farm"], "")),
            "date_of_birth": format_date_for_json(row.get("Date_Of_Birth", "")),
            "age_days": row.get("Age_Days", ""),
            "current_weight_kg": current_weight,
            "calculated_stage": to_clean_string(row.get("Calculated_Stage", "")),
            "current_pen_id": to_clean_string(row.get("Current_Pen_ID", "")),
        })

    piglets = sorted(
        piglets,
        key=lambda x: (x["tag_number"] or x["pig_id"]).lower()
    )

    average_weight = round(sum(weight_values) / len(weight_values), 2) if weight_values else None

    return {
        "litter_id": litter_id,
        "mother_pig_id": mother_pig_id,
        "mother_tag_number": mother_tag_number,
        "father_pig_id": father_pig_id,
        "father_tag_number": father_tag_number,
        "count": len(piglets),
        "male_count": male_count,
        "female_count": female_count,
        "active_count": active_count,
        "average_weight_kg": average_weight,
        "piglets": piglets,
    }


def get_pig_detail(pig_id: str):
    pig_id = str(pig_id).strip()

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    pig_lookup = {}
    for row in rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id:
            pig_lookup[row_pig_id] = row

    pig = pig_lookup.get(pig_id)
    if not pig:
        return None

    mother_pig_id = to_clean_string(pig.get("Mother_Pig_ID", ""))
    father_pig_id = to_clean_string(pig.get("Father_Pig_ID", ""))
    litter_id = to_clean_string(pig.get("Litter_ID", ""))

    mother_row = pig_lookup.get(mother_pig_id) if mother_pig_id else None
    father_row = pig_lookup.get(father_pig_id) if father_pig_id else None

    mother_tag_number = to_clean_string(mother_row.get(columns["tag_number"], "")) if mother_row else ""
    father_tag_number = to_clean_string(father_row.get(columns["tag_number"], "")) if father_row else ""

    return {
        "pig_id": to_clean_string(pig.get(columns["pig_id"], "")),
        "tag_number": to_clean_string(pig.get(columns["tag_number"], "")),
        "status": to_clean_string(pig.get(columns["status"], "")),
        "on_farm": to_clean_string(pig.get(columns["on_farm"], "")),
        "animal_type": to_clean_string(pig.get("Animal_Type", "")),
        "sex": to_clean_string(pig.get("Sex", "")),
        "date_of_birth": format_date_for_json(pig.get("Date_Of_Birth", "")),
        "age_days": pig.get("Age_Days", ""),
        "litter_id": litter_id,
        "mother_pig_id": mother_pig_id,
        "mother_tag_number": mother_tag_number,
        "father_pig_id": father_pig_id,
        "father_tag_number": father_tag_number,
        "current_pen_id": to_clean_string(pig.get("Current_Pen_ID", "")),
        "purpose": to_clean_string(pig.get("Purpose", "")),
        "current_weight_kg": pig.get("Current_Weight_Kg", ""),
        "last_weight_date": format_date_for_json(pig.get("Last_Weight_Date", "")),
        "calculated_stage": to_clean_string(pig.get("Calculated_Stage", "")),
        "weight_band": to_clean_string(pig.get("Weight_Band", "")),
        "is_sale_ready": to_clean_string(pig.get("Is_Sale_Ready", "")),
        "reserved_status": to_clean_string(pig.get("Reserved_Status", "")),
        "general_notes": to_clean_string(pig.get("General_Notes", "")),
        "last_treatment_date": format_date_for_json(pig.get("Last_Treatment_Date", "")),
        "last_product_name": to_clean_string(pig.get("Last_Product_Name", "")),
        "current_withdrawal_end_date": format_date_for_json(pig.get("Current_Withdrawal_End_Date", "")),
        "withdrawal_clear": to_clean_string(pig.get("Withdrawal_Clear", "")),
    }


def get_products():
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["product_register"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    products = []
    for row in rows:
        if str(row.get(columns["is_active"], "")).strip() != "Yes":
            continue

        products.append({
            "product_id": to_clean_string(row.get(columns["product_id"], "")),
            "product_name": to_clean_string(row.get(columns["product_name"], "")),
            "product_category": to_clean_string(row.get(columns["product_category"], "")),
            "default_dose": to_float(row.get(columns["default_dose"], "")),
            "dose_unit": to_clean_string(row.get(columns["dose_unit"], "")),
            "default_withdrawal_days": to_float(row.get(columns["default_withdrawal_days"], "")),
            "supplier": to_clean_string(row.get(columns["supplier"], "")),
        })

    return sorted(products, key=lambda x: x["product_name"].lower())


def get_product_by_id(product_id: str):
    product_id = str(product_id).strip()
    products = get_products()

    for product in products:
        if product["product_id"] == product_id:
            return product

    return None


def get_pens():
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pen_register"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    rows = get_all_records(sheet_name)

    pens = []
    for row in rows:
        if str(row.get(columns["is_active"], "")).strip() != "Yes":
            continue

        pens.append({
            "pen_id": to_clean_string(row.get(columns["pen_id"], "")),
            "pen_name": to_clean_string(row.get(columns["pen_name"], "")),
            "pen_type": to_clean_string(row.get(columns["pen_type"], "")),
            "capacity": to_float(row.get(columns["capacity"], "")),
            "pen_notes": to_clean_string(row.get(columns["pen_notes"], "")),
        })

    return sorted(pens, key=lambda x: x["pen_name"].lower())


def get_pen_by_id(pen_id: str):
    pen_id = str(pen_id).strip()
    pens = get_pens()

    for pen in pens:
        if pen["pen_id"] == pen_id:
            return pen

    return None


def get_treatment_history_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()

    medical_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"]
    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    tag_number = ""
    overview_rows = get_all_records(overview_sheet)
    for row in overview_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            tag_number = to_clean_string(row.get(columns["tag_number"], ""))
            break

    treatment_rows = get_all_records(medical_log_sheet)

    history = []
    for row in treatment_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id != pig_id:
            continue

        treatment_date = parse_sheet_date(row.get(columns["treatment_date"], ""))
        history.append({
            "medical_log_id": to_clean_string(row.get(columns["medical_log_id"], "")),
            "pig_id": pig_id,
            "tag_number": tag_number,
            "treatment_date": treatment_date,
            "treatment_date_display": format_date_for_json(row.get(columns["treatment_date"], "")),
            "treatment_type": to_clean_string(row.get(columns["treatment_type"], "")),
            "product_id": to_clean_string(row.get(columns["product_id"], "")),
            "product_name": to_clean_string(row.get(columns["product_name"], "")),
            "dose": to_float(row.get(columns["dose"], "")),
            "dose_unit": to_clean_string(row.get(columns["dose_unit"], "")),
            "route": to_clean_string(row.get(columns["route"], "")),
            "reason_for_treatment": to_clean_string(row.get(columns["reason_for_treatment"], "")),
            "batch_lot_number": to_clean_string(row.get(columns["batch_lot_number"], "")),
            "withdrawal_days": to_float(row.get(columns["withdrawal_days"], "")),
            "withdrawal_end_date": format_date_for_json(row.get(columns["withdrawal_end_date"], "")),
            "given_by": to_clean_string(row.get(columns["given_by"], "")),
            "follow_up_required": to_clean_string(row.get(columns["follow_up_required"], "")),
            "follow_up_date": format_date_for_json(row.get(columns["follow_up_date"], "")),
            "medical_notes": to_clean_string(row.get(columns["medical_notes"], "")),
        })

    history = sorted(
        history,
        key=lambda x: x["treatment_date"] if x["treatment_date"] else parse_sheet_date("1900-01-01"),
        reverse=True
    )

    for entry in history:
        entry.pop("treatment_date", None)

    return {
        "pig_id": pig_id,
        "tag_number": tag_number,
        "count": len(history),
        "history": history,
    }


def get_movement_history_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()

    location_history_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["location_history"]
    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    tag_number = ""
    current_pen_id = ""

    overview_rows = get_all_records(overview_sheet)
    for row in overview_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            tag_number = to_clean_string(row.get(columns["tag_number"], ""))
            current_pen_id = to_clean_string(row.get("Current_Pen_ID", ""))
            break

    movement_rows = get_all_records(location_history_sheet)
    history = []

    for row in movement_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id != pig_id:
            continue

        move_date = parse_sheet_date(row.get(columns["move_date"], ""))
        from_pen_id = to_clean_string(row.get(columns["from_pen_id"], ""))
        to_pen_id = to_clean_string(row.get(columns["to_pen_id"], ""))

        from_pen = get_pen_by_id(from_pen_id)
        to_pen = get_pen_by_id(to_pen_id)

        history.append({
            "move_log_id": to_clean_string(row.get(columns["move_log_id"], "")),
            "pig_id": pig_id,
            "tag_number": tag_number,
            "move_date": move_date,
            "move_date_display": format_date_for_json(row.get(columns["move_date"], "")),
            "from_pen_id": from_pen_id,
            "to_pen_id": to_pen_id,
            "from_pen_name": from_pen["pen_name"] if from_pen else from_pen_id,
            "to_pen_name": to_pen["pen_name"] if to_pen else to_pen_id,
            "reason_for_move": to_clean_string(row.get(columns["reason_for_move"], "")),
            "moved_by": to_clean_string(row.get(columns["moved_by"], "")),
            "move_notes": to_clean_string(row.get(columns["move_notes"], "")),
        })

    history = sorted(
        history,
        key=lambda x: x["move_date"] if x["move_date"] else parse_sheet_date("1900-01-01"),
        reverse=True
    )

    for entry in history:
        entry.pop("move_date", None)

    return {
        "pig_id": pig_id,
        "tag_number": tag_number,
        "current_pen_id": current_pen_id,
        "count": len(history),
        "history": history,
    }


def get_weight_history_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()

    weight_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]
    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    tag_number = ""
    overview_rows = get_all_records(overview_sheet)
    for row in overview_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            tag_number = to_clean_string(row.get(columns["tag_number"], ""))
            break

    weight_rows = get_all_records(weight_log_sheet)

    history = []
    for row in weight_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id != pig_id:
            continue

        weight_date = parse_sheet_date(row.get(columns["weight_date"], ""))
        weight_kg = to_float(row.get(columns["weight_kg"], ""))

        history.append({
            "weight_log_id": to_clean_string(row.get(columns["weight_log_id"], "")),
            "pig_id": pig_id,
            "tag_number": tag_number,
            "weight_date": weight_date,
            "weight_date_display": format_date_for_json(row.get(columns["weight_date"], "")),
            "weight_kg": weight_kg,
            "weighed_by": to_clean_string(row.get(columns["weighed_by"], "")),
            "condition_notes": to_clean_string(row.get(columns["condition_notes"], "")),
        })

    history = sorted(
        history,
        key=lambda x: x["weight_date"] if x["weight_date"] else parse_sheet_date("1900-01-01"),
        reverse=True
    )

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

        if (
            entry["difference_kg"] is not None
            and entry["days_since_previous"] is not None
            and entry["days_since_previous"] > 0
        ):
            entry["growth_rate_kg_day"] = round(entry["difference_kg"] / entry["days_since_previous"], 3)
        else:
            entry["growth_rate_kg_day"] = None

        entry.pop("weight_date", None)

    return {
        "pig_id": pig_id,
        "tag_number": tag_number,
        "count": len(history),
        "history": history,
    }

def get_weight_entries_by_date(weight_date: str):
    parsed_target_date = parse_sheet_date(weight_date)

    if not parsed_target_date:
        return {
            "weight_date": "",
            "count": 0,
            "history": [],
        }

    weight_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]
    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    overview_rows = get_all_records(overview_sheet)
    pig_lookup = {}

    for row in overview_rows:
        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if not pig_id:
            continue

        pig_lookup[pig_id] = {
            "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
            "current_pen_id": to_clean_string(row.get(columns["current_pen_id"], "")),
        }

    weight_rows = get_all_records(weight_log_sheet)

    history = []
    for row in weight_rows:
        row_date = parse_sheet_date(row.get(columns["weight_date"], ""))
        if row_date != parsed_target_date:
            continue

        pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        pig_meta = pig_lookup.get(pig_id, {})

        history.append({
            "weight_log_id": to_clean_string(row.get(columns["weight_log_id"], "")),
            "pig_id": pig_id,
            "tag_number": pig_meta.get("tag_number", ""),
            "current_pen_id": pig_meta.get("current_pen_id", ""),
            "weight_date_display": format_date_for_json(row.get(columns["weight_date"], "")),
            "weight_kg": to_float(row.get(columns["weight_kg"], "")),
            "weighed_by": to_clean_string(row.get(columns["weighed_by"], "")),
            "condition_notes": to_clean_string(row.get(columns["condition_notes"], "")),
        })

    history = sorted(
        history,
        key=lambda x: ((x["tag_number"] or x["pig_id"]).lower(), x["pig_id"].lower())
    )

    return {
        "weight_date": parsed_target_date.isoformat(),
        "count": len(history),
        "history": history,
    }

def get_latest_weight_for_pig(pig_id: str):
    pig_id = str(pig_id).strip()

    overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
    weight_log_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]
    columns = PIG_WEIGHTS_CONFIG["columns"]

    overview_rows = get_all_records(overview_sheet)

    for row in overview_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            return {
                "pig_id": pig_id,
                "tag_number": to_clean_string(row.get(columns["tag_number"], "")),
                "previous_weight_kg": to_float(row.get(columns["current_weight"], "")),
                "previous_weight_date": format_date_for_json(row.get(columns["last_weight_date"], "")),
            }

    weight_rows = get_all_records(weight_log_sheet)

    matching_rows = []
    for row in weight_rows:
        row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
        if row_pig_id == pig_id:
            weight_date = parse_sheet_date(row.get(columns["weight_date"], ""))
            weight_kg = to_float(row.get(columns["weight_kg"], ""))
            if weight_date and weight_kg is not None:
                matching_rows.append({
                    "pig_id": pig_id,
                    "tag_number": "",
                    "previous_weight_kg": weight_kg,
                    "previous_weight_date": weight_date,
                })

    if not matching_rows:
        return {
            "pig_id": pig_id,
            "tag_number": "",
            "previous_weight_kg": None,
            "previous_weight_date": "",
        }

    latest_row = sorted(
        matching_rows,
        key=lambda x: x["previous_weight_date"],
        reverse=True
    )[0]

    return {
        "pig_id": latest_row["pig_id"],
        "tag_number": latest_row["tag_number"],
        "previous_weight_kg": latest_row["previous_weight_kg"],
        "previous_weight_date": latest_row["previous_weight_date"].isoformat(),
    }


def save_new_pig(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]

    mother_pig_id = "" if cleaned_data["mother_pig_id"] == "Unknown" else cleaned_data["mother_pig_id"]
    father_pig_id = "" if cleaned_data["father_pig_id"] == "Unknown" else cleaned_data["father_pig_id"]
    litter_id = "" if cleaned_data["litter_id"] == "Unknown" else cleaned_data["litter_id"]

    parent_options = get_parent_options()
    mother_lookup = {row["pig_id"]: row["tag_number"] for row in parent_options["mothers"]}
    father_lookup = {row["pig_id"]: row["tag_number"] for row in parent_options["fathers"]}

    mother_tag_number = mother_lookup.get(cleaned_data["mother_pig_id"], "") if mother_pig_id else ""
    father_tag_number = father_lookup.get(cleaned_data["father_pig_id"], "") if father_pig_id else ""

    birth_month = cleaned_data["date_of_birth"].strftime("%m") if cleaned_data["date_of_birth"] else ""
    birth_year = cleaned_data["date_of_birth"].strftime("%Y") if cleaned_data["date_of_birth"] else ""

    today_str = datetime.now().strftime("%d %b %Y")

    row_values = [
        generate_pig_id(),
        cleaned_data["tag_number"],
        cleaned_data["pig_name"],
        cleaned_data["status"],
        cleaned_data["on_farm"],
        cleaned_data["animal_type"],
        cleaned_data["sex"],
        format_date_for_sheet(cleaned_data["date_of_birth"]),
        birth_month,
        birth_year,
        cleaned_data["breed_type"],
        cleaned_data["colour_markings"],
        litter_id,
        cleaned_data["litter_size_born"] if cleaned_data["litter_size_born"] is not None else "",
        cleaned_data["litter_size_weaned"] if cleaned_data["litter_size_weaned"] is not None else "",
        mother_pig_id,
        father_pig_id,
        mother_tag_number,
        father_tag_number,
        "",
        "",
        cleaned_data["purpose"],
        "",
        cleaned_data["current_pen_id"],
        cleaned_data["source"],
        format_date_for_sheet(cleaned_data["acquisition_date"]),
        cleaned_data["birth_weight_kg"] if cleaned_data["birth_weight_kg"] is not None else "",
        format_date_for_sheet(cleaned_data["wean_date"]),
        cleaned_data["wean_weight_kg"] if cleaned_data["wean_weight_kg"] is not None else "",
        format_date_for_sheet(cleaned_data["exit_date"]),
        cleaned_data["exit_reason"],
        cleaned_data["exit_order_id"],
        cleaned_data["carcass_weight_kg"] if cleaned_data["carcass_weight_kg"] is not None else "",
        cleaned_data["general_notes"],
        today_str,
        today_str,
    ]

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Pig created successfully."
    }


def save_new_product(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["product_register"]

    row_values = [
        generate_product_id(),
        cleaned_data["product_name"],
        cleaned_data["product_category"],
        cleaned_data["default_dose"] if cleaned_data["default_dose"] is not None else "",
        cleaned_data["dose_unit"],
        cleaned_data["default_withdrawal_days"] if cleaned_data["default_withdrawal_days"] is not None else "",
        cleaned_data["supplier"],
        cleaned_data["batch_tracking_required"],
        cleaned_data["is_active"],
        cleaned_data["product_notes"],
    ]

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Product created successfully."
    }


def save_new_pen(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["pen_register"]

    row_values = [
        generate_pen_id(),
        cleaned_data["pen_name"],
        cleaned_data["pen_type"],
        cleaned_data["capacity"] if cleaned_data["capacity"] is not None else "",
        cleaned_data["is_active"],
        cleaned_data["pen_notes"],
    ]

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Pen created successfully."
    }

def _create_pig_rows_for_litter(
    litter_id: str,
    mother_pig_id: str,
    father_pig_id: str,
    mother_tag: str,
    father_tag: str,
    farrowing_date,
    total_born,
    current_pen_id: str,
):
    if not litter_id or not mother_pig_id or not farrowing_date or total_born in (None, "", 0):
        return 0

    try:
        total_born_int = int(total_born)
    except (TypeError, ValueError):
        return 0

    if total_born_int <= 0:
        return 0

    pig_master_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_master"]
    existing_rows = get_all_records(pig_master_sheet)

    existing_for_litter = 0
    for row in existing_rows:
        if to_clean_string(row.get("Litter_ID", "")) == litter_id:
            existing_for_litter += 1

    if existing_for_litter > 0:
        return 0

    today_str = datetime.now().strftime("%d %b %Y")
    birth_month = farrowing_date.strftime("%m") if farrowing_date else ""
    birth_year = farrowing_date.strftime("%Y") if farrowing_date else ""

    created_count = 0

    for _ in range(total_born_int):
        row_values = [
            generate_pig_id(),                                 # Pig_ID
            "",                                                # Tag_Number
            "",                                                # Pig_Name
            "Active",                                          # Status
            "Yes",                                             # On_Farm
            "Piglet",                                          # Animal_Type
            "",                                                # Sex
            format_date_for_sheet(farrowing_date),             # Date_Of_Birth
            birth_month,                                       # Birth_Month
            birth_year,                                        # Birth_Year
            "",                                                # Breed_Type
            "",                                                # Colour_Markings
            litter_id,                                         # Litter_ID
            total_born_int,                                    # Litter_Size_Born
            "",                                                # Litter_Size_Weaned
            mother_pig_id,                                     # Mother_Pig_ID
            father_pig_id,                                     # Father_Pig_ID
            mother_tag,                                        # Mother_Tag_Number
            father_tag,                                        # Father_Tag_Number
            "",                                                # Maternal_Line
            "",                                                # Paternal_Line
            "",                                                # Purpose
            "",                                                # Current_Stage
            current_pen_id,                                    # Current_Pen_ID
            "Born_on_Farm",                                    # Source
            "",                                                # Acquisition_Date
            "",                                                # Birth_Weight_Kg
            "",                                                # Wean_Date
            "",                                                # Wean_Weight_Kg
            "",                                                # Exit_Date
            "",                                                # Exit_Reason
            "",                                                # Exit_Order_ID
            "",                                                # Carcass_Weight_Kg
            "",                                                # General_Notes
            today_str,                                         # Created_At
            today_str,                                         # Updated_At
        ]

        append_row(pig_master_sheet, row_values)
        created_count += 1

    return created_count

def save_new_litter(cleaned_data: dict):
    pig_rows = get_all_records(PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"])
    columns = PIG_WEIGHTS_CONFIG["columns"]
    pig_lookup = _build_pig_lookup(pig_rows, columns)

    mother_row = pig_lookup.get(cleaned_data["mother_pig_id"])
    father_row = pig_lookup.get(cleaned_data["father_pig_id"]) if cleaned_data["father_pig_id"] else None

    mother_tag = to_clean_string(mother_row.get(columns["tag_number"], "")) if mother_row else ""
    father_tag = to_clean_string(father_row.get(columns["tag_number"], "")) if father_row else ""

    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["litter_register"]
    litter_id = generate_litter_id()

    row_values = [
        litter_id,
        format_date_for_sheet(cleaned_data["farrowing_date"]),
        cleaned_data["mother_pig_id"],
        cleaned_data["father_pig_id"],
        mother_tag,
        father_tag,
        cleaned_data["total_born"] if cleaned_data["total_born"] is not None else "",
        cleaned_data["born_alive"] if cleaned_data["born_alive"] is not None else "",
        cleaned_data["stillborn_count"] if cleaned_data["stillborn_count"] is not None else "",
        cleaned_data["mummified_count"] if cleaned_data["mummified_count"] is not None else "",
        cleaned_data["male_count"] if cleaned_data["male_count"] is not None else "",
        cleaned_data["female_count"] if cleaned_data["female_count"] is not None else "",
        cleaned_data["fostered_in_count"] if cleaned_data["fostered_in_count"] is not None else "",
        cleaned_data["fostered_out_count"] if cleaned_data["fostered_out_count"] is not None else "",
        cleaned_data["weaned_count"] if cleaned_data["weaned_count"] is not None else "",
        format_date_for_sheet(cleaned_data["wean_date"]),
        cleaned_data["average_wean_weight_kg"] if cleaned_data["average_wean_weight_kg"] is not None else "",
        cleaned_data["notes"],
        datetime.now().strftime("%d %b %Y"),
        cleaned_data["current_pen_id"],
    ]

    append_row(sheet_name, row_values)

    pig_rows_created = _create_pig_rows_for_litter(
        litter_id=litter_id,
        mother_pig_id=cleaned_data["mother_pig_id"],
        father_pig_id=cleaned_data["father_pig_id"],
        mother_tag=mother_tag,
        father_tag=father_tag,
        farrowing_date=cleaned_data["farrowing_date"],
        total_born=cleaned_data["total_born"],
        current_pen_id=cleaned_data["current_pen_id"],
    )

    mating_id = str(cleaned_data.get("mating_id", "")).strip()
    if mating_id:
        link_litter_to_mating(
            mating_id=mating_id,
            litter_id=litter_id,
            actual_farrowing_date=cleaned_data["farrowing_date"]
        )

    return {
        "success": True,
        "message": "Litter created successfully.",
        "litter_id": litter_id,
        "pig_rows_created": pig_rows_created,
    }


def save_weight_entry(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["weight_log"]

    row_values = [
        generate_weight_log_id(),
        cleaned_data["pig_id"],
        format_date_for_sheet(cleaned_data["weight_date"]),
        cleaned_data["weight_kg"],
        cleaned_data["weighed_by"],
        "",
        cleaned_data["condition_notes"],
        "",
        format_date_for_sheet(cleaned_data["weight_date"]),
    ]

    append_row(sheet_name, row_values)

    latest_info = get_latest_weight_for_pig(cleaned_data["pig_id"])

    return {
        "success": True,
        "message": "Weight entry saved successfully.",
        "saved": {
            "pig_id": cleaned_data["pig_id"],
            "weight_date": format_date_for_json(cleaned_data["weight_date"]),
            "weight_kg": cleaned_data["weight_kg"],
            "condition_notes": cleaned_data["condition_notes"],
            "weighed_by": cleaned_data["weighed_by"],
        },
        "latest": latest_info
    }

def save_weight_entry_with_optional_move(cleaned_data: dict):
    weight_result = save_weight_entry({
        "pig_id": cleaned_data["pig_id"],
        "weight_date": cleaned_data["weight_date"],
        "weight_kg": cleaned_data["weight_kg"],
        "condition_notes": cleaned_data["condition_notes"],
        "weighed_by": cleaned_data["weighed_by"],
    })

    moved_to_pen_id = to_clean_string(cleaned_data.get("moved_to_pen_id", ""))
    movement_logged = False
    movement_result = None

    if moved_to_pen_id:
        overview_sheet = PIG_WEIGHTS_CONFIG["sheet_names"]["pig_overview"]
        columns = PIG_WEIGHTS_CONFIG["columns"]
        overview_rows = get_all_records(overview_sheet)

        current_pen_id = ""
        for row in overview_rows:
            row_pig_id = to_clean_string(row.get(columns["pig_id"], ""))
            if row_pig_id == cleaned_data["pig_id"]:
                current_pen_id = to_clean_string(row.get(columns["current_pen_id"], ""))
                break

        if moved_to_pen_id != current_pen_id:
            movement_result = save_movement_entry({
                "pig_id": cleaned_data["pig_id"],
                "move_date": cleaned_data["weight_date"],
                "from_pen_id": current_pen_id,
                "to_pen_id": moved_to_pen_id,
                "reason_for_move": "Moved during weight capture",
                "moved_by": "WebApp",
                "move_notes": "",
            })
            movement_logged = True

    return {
        "success": True,
        "message": "Weight entry saved successfully.",
        "saved": weight_result.get("saved", {}),
        "latest": weight_result.get("latest", {}),
        "movement_logged": movement_logged,
        "movement": movement_result.get("saved", {}) if movement_result else None,
    }

def save_treatment_entry(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["medical_log"]
    product = get_product_by_id(cleaned_data["product_id"])

    product_name = product["product_name"] if product else ""
    default_dose_unit = product["dose_unit"] if product else ""
    withdrawal_days = product["default_withdrawal_days"] if product else None

    dose_unit = cleaned_data["dose_unit"] or default_dose_unit
    withdrawal_days_int = int(withdrawal_days) if withdrawal_days not in (None, "") else ""
    withdrawal_end_date = ""

    if cleaned_data["treatment_date"] and withdrawal_days_int != "":
        withdrawal_end_date = cleaned_data["treatment_date"].fromordinal(
            cleaned_data["treatment_date"].toordinal() + withdrawal_days_int
        )

    row_values = [
        generate_medical_log_id(),
        cleaned_data["pig_id"],
        format_date_for_sheet(cleaned_data["treatment_date"]),
        cleaned_data["treatment_type"],
        cleaned_data["product_id"],
        product_name,
        cleaned_data["dose"] if cleaned_data["dose"] is not None else "",
        dose_unit,
        cleaned_data["route"],
        cleaned_data["reason_for_treatment"],
        cleaned_data["batch_lot_number"],
        withdrawal_days_int,
        format_date_for_sheet(withdrawal_end_date),
        cleaned_data["given_by"],
        cleaned_data["follow_up_required"],
        format_date_for_sheet(cleaned_data["follow_up_date"]),
        cleaned_data["medical_notes"],
        format_date_for_sheet(cleaned_data["treatment_date"]),
    ]

    append_row(sheet_name, row_values)

    return {
        "success": True,
        "message": "Treatment entry saved successfully.",
        "saved": {
            "pig_id": cleaned_data["pig_id"],
            "treatment_date": format_date_for_json(cleaned_data["treatment_date"]),
            "treatment_type": cleaned_data["treatment_type"],
            "product_id": cleaned_data["product_id"],
            "product_name": product_name,
            "dose": cleaned_data["dose"],
            "dose_unit": dose_unit,
            "route": cleaned_data["route"],
            "reason_for_treatment": cleaned_data["reason_for_treatment"],
            "withdrawal_days": withdrawal_days_int,
            "withdrawal_end_date": format_date_for_json(withdrawal_end_date),
            "given_by": cleaned_data["given_by"],
            "follow_up_required": cleaned_data["follow_up_required"],
            "follow_up_date": format_date_for_json(cleaned_data["follow_up_date"]),
            "medical_notes": cleaned_data["medical_notes"],
        }
    }


def save_movement_entry(cleaned_data: dict):
    sheet_name = PIG_WEIGHTS_CONFIG["sheet_names"]["location_history"]

    row_values = [
        generate_move_log_id(),
        cleaned_data["pig_id"],
        format_date_for_sheet(cleaned_data["move_date"]),
        cleaned_data["from_pen_id"],
        cleaned_data["to_pen_id"],
        cleaned_data["reason_for_move"],
        cleaned_data["moved_by"],
        "",
        cleaned_data["move_notes"],
        format_date_for_sheet(cleaned_data["move_date"]),
    ]

    append_row(sheet_name, row_values)

    from_pen = get_pen_by_id(cleaned_data["from_pen_id"])
    to_pen = get_pen_by_id(cleaned_data["to_pen_id"])

    return {
        "success": True,
        "message": "Movement entry saved successfully.",
        "saved": {
            "pig_id": cleaned_data["pig_id"],
            "move_date": format_date_for_json(cleaned_data["move_date"]),
            "from_pen_id": cleaned_data["from_pen_id"],
            "from_pen_name": from_pen["pen_name"] if from_pen else cleaned_data["from_pen_id"],
            "to_pen_id": cleaned_data["to_pen_id"],
            "to_pen_name": to_pen["pen_name"] if to_pen else cleaned_data["to_pen_id"],
            "reason_for_move": cleaned_data["reason_for_move"],
            "moved_by": cleaned_data["moved_by"],
            "move_notes": cleaned_data["move_notes"],
        }
    }