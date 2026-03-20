from modules.pig_weights.pig_weights_utils import parse_sheet_date


def validate_new_mating_payload(payload: dict):
    errors = []

    sow_pig_id = str(payload.get("sow_pig_id", "")).strip()
    boar_pig_id = str(payload.get("boar_pig_id", "")).strip()
    mating_date = payload.get("mating_date", "")
    mating_method = str(payload.get("mating_method", "")).strip()
    exposure_group = str(payload.get("exposure_group", "")).strip()
    service_notes = str(payload.get("service_notes", "")).strip()

    if not sow_pig_id:
        errors.append("Sow_Pig_ID is required.")

    parsed_mating_date = parse_sheet_date(mating_date)
    if not parsed_mating_date:
        errors.append("Mating_Date is required and must be a valid date.")

    if not mating_method:
        errors.append("Mating_Method is required.")

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": {
            "sow_pig_id": sow_pig_id,
            "boar_pig_id": "" if boar_pig_id in ("", "Unknown") else boar_pig_id,
            "mating_date": parsed_mating_date,
            "mating_method": mating_method,
            "exposure_group": exposure_group,
            "service_notes": service_notes,
        }
    }