from services.google_sheets_service import get_all_records
from modules.pig_weights.pig_weights_config import PIG_WEIGHTS_CONFIG


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
                "pig_id": row.get(columns["pig_id"], ""),
                "tag_number": row.get(columns["tag_number"], ""),
                "status": row.get(columns["status"], ""),
                "on_farm": row.get(columns["on_farm"], ""),
                "current_weight_kg": row.get(columns["current_weight"], ""),
                "last_weight_date": row.get(columns["last_weight_date"], ""),
            })

    return active_pigs