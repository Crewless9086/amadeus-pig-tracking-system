from datetime import datetime
import uuid

from services.google_sheets_service import (
    get_all_records,
    append_row,
    batch_update_rows_by_id,
)
from modules.pig_weights.pig_weights_utils import to_clean_string, to_float


ORDER_INTAKE_STATE_SHEET = "ORDER_INTAKE_STATE"
ORDER_INTAKE_ITEMS_SHEET = "ORDER_INTAKE_ITEMS"

INTAKE_STATE_HEADERS = [
    "Intake_ID",
    "ConversationId",
    "Account_ID",
    "Contact_ID",
    "Customer_Name",
    "Customer_Phone",
    "Customer_Channel",
    "Customer_Language",
    "Draft_Order_ID",
    "Intake_Status",
    "Collection_Location",
    "Collection_Time_Text",
    "Collection_Date",
    "Collection_Time",
    "Payment_Method",
    "Quote_Requested",
    "Order_Commitment",
    "Missing_Fields",
    "Next_Action",
    "Ready_For_Draft",
    "Ready_For_Quote",
    "Last_Customer_Message",
    "Last_Updated_By",
    "Created_At",
    "Updated_At",
    "Closed_At",
    "Closed_Reason",
    "Notes",
]

INTAKE_ITEM_HEADERS = [
    "Intake_Item_ID",
    "Intake_ID",
    "ConversationId",
    "Item_Key",
    "Quantity",
    "Category",
    "Weight_Range",
    "Sex",
    "Intent_Type",
    "Status",
    "Linked_Order_Line_IDs",
    "Last_Match_Status",
    "Matched_Quantity",
    "Replaced_By_Item_Key",
    "Removal_Reason",
    "Notes",
    "Created_At",
    "Updated_At",
    "Removed_At",
]

OPEN_INTAKE_STATUSES = {
    "Open",
    "Ready_For_Draft",
    "Draft_Created",
    "Quote_Requested",
    "Quote_Generated",
    "Sent_For_Approval",
    "Needs_Admin",
}

ALLOWED_COLLECTION_LOCATIONS = {"Riversdale", "Albertinia", "Any"}
ALLOWED_PAYMENT_METHODS = {"Cash", "EFT"}
ALLOWED_CATEGORIES = {"Piglet", "Weaner", "Grower", "Finisher", "Slaughter"}
ALLOWED_WEIGHT_RANGES = {
    "2_to_4_Kg",
    "5_to_6_Kg",
    "7_to_9_Kg",
    "10_to_14_Kg",
    "15_to_19_Kg",
    "20_to_24_Kg",
    "25_to_29_Kg",
    "30_to_34_Kg",
    "35_to_39_Kg",
    "40_to_44_Kg",
    "45_to_49_Kg",
    "50_to_54_Kg",
    "55_to_59_Kg",
    "60_to_64_Kg",
    "65_to_69_Kg",
    "70_to_74_Kg",
    "75_to_79_Kg",
    "80_to_84_Kg",
    "85_to_89_Kg",
    "90_to_94_Kg",
}
ALLOWED_SEXES = {"Male", "Female", "Any"}
ALLOWED_INTENT_TYPES = {"primary", "addon", "nearby_addon", "extractor_slot"}
ALLOWED_ITEM_STATUSES = {"active", "removed", "replaced"}


def generate_intake_id():
    return f"INTAKE-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def generate_intake_item_id():
    return f"INTAKEITEM-{datetime.now().year}-{uuid.uuid4().hex[:6].upper()}"


def get_intake_context(conversation_id: str):
    conversation_id = to_clean_string(conversation_id)
    if not conversation_id:
        raise ValueError("conversation_id is required.")

    intake = _find_active_intake_by_conversation(conversation_id)
    if not intake:
        return {
            "success": True,
            "lookup_status": "no_match",
            "conversation_id": conversation_id,
            "intake": None,
            "items": [],
            "message": "No active intake state was found.",
        }

    items = _get_items_for_intake(to_clean_string(intake.get("Intake_ID", "")))
    return _build_context_response(intake, items, lookup_status="single_match")


def update_intake_state(cleaned_data: dict):
    conversation_id = to_clean_string(cleaned_data.get("conversation_id", ""))
    if not conversation_id:
        raise ValueError("conversation_id is required.")

    now_str = _now_string()
    updated_by = to_clean_string(cleaned_data.get("updated_by", "")) or "Sam"
    patch = cleaned_data.get("patch", {})
    item_patches = cleaned_data.get("items", [])

    intake = _find_active_intake_by_conversation(conversation_id)

    if not intake:
        intake = _create_intake_row(conversation_id, cleaned_data, now_str, updated_by)

    intake_id = to_clean_string(intake.get("Intake_ID", ""))
    state_updates = _build_state_updates(intake, patch, cleaned_data, now_str, updated_by)
    items = _merge_item_patches(intake_id, conversation_id, item_patches, now_str)

    current_items = _get_items_for_intake(intake_id)
    if state_updates:
        batch_update_rows_by_id(ORDER_INTAKE_STATE_SHEET, {intake_id: state_updates})
        intake = {**intake, **state_updates}

    if items.get("updates"):
        batch_update_rows_by_id(ORDER_INTAKE_ITEMS_SHEET, items["updates"])

    all_items = _get_items_for_intake(intake_id)
    if not all_items and current_items:
        all_items = current_items

    computed = _compute_intake_state(intake, all_items)
    computed_updates = {
        "Missing_Fields": ", ".join(computed["missing_fields"]),
        "Ready_For_Draft": _bool_to_sheet(computed["ready_for_draft"]),
        "Ready_For_Quote": _bool_to_sheet(computed["ready_for_quote"]),
        "Next_Action": computed["next_action"],
        "Intake_Status": computed["intake_status"],
        "Updated_At": now_str,
    }
    batch_update_rows_by_id(ORDER_INTAKE_STATE_SHEET, {intake_id: computed_updates})
    intake = {**intake, **computed_updates}

    return _build_context_response(
        intake,
        all_items,
        lookup_status="updated",
        extra={
            "created_item_count": items.get("created_count", 0),
            "updated_item_count": len(items.get("updates", {})),
        },
    )


def reset_intake(conversation_id: str, closed_reason: str = "admin_reset", updated_by: str = "App"):
    conversation_id = to_clean_string(conversation_id)
    if not conversation_id:
        raise ValueError("conversation_id is required.")

    intake = _find_active_intake_by_conversation(conversation_id)
    if not intake:
        return {
            "success": True,
            "conversation_id": conversation_id,
            "closed": False,
            "message": "No active intake state was found.",
        }

    intake_id = to_clean_string(intake.get("Intake_ID", ""))
    now_str = _now_string()
    updates = {
        "Intake_Status": "Closed",
        "Next_Action": "reply_only",
        "Closed_At": now_str,
        "Closed_Reason": to_clean_string(closed_reason) or "admin_reset",
        "Last_Updated_By": to_clean_string(updated_by) or "App",
        "Updated_At": now_str,
    }
    batch_update_rows_by_id(ORDER_INTAKE_STATE_SHEET, {intake_id: updates})

    return {
        "success": True,
        "conversation_id": conversation_id,
        "intake_id": intake_id,
        "closed": True,
        "message": "Intake state closed.",
    }


def validate_intake_update_payload(payload: dict):
    errors = []
    cleaned = {
        "conversation_id": to_clean_string(payload.get("conversation_id", "")),
        "account_id": to_clean_string(payload.get("account_id", "")),
        "contact_id": to_clean_string(payload.get("contact_id", "")),
        "customer_name": to_clean_string(payload.get("customer_name", "")),
        "customer_phone": to_clean_string(payload.get("customer_phone", "")),
        "customer_channel": to_clean_string(payload.get("customer_channel", "")),
        "customer_language": to_clean_string(payload.get("customer_language", "")),
        "updated_by": to_clean_string(payload.get("updated_by", "")) or "Sam",
    }

    if not cleaned["conversation_id"]:
        errors.append("conversation_id is required.")

    patch = payload.get("patch", {})
    if patch is None:
        patch = {}
    if not isinstance(patch, dict):
        errors.append("patch must be an object.")
        patch = {}

    cleaned_patch = _validate_state_patch(patch, errors)
    cleaned_items = _validate_item_patches(payload.get("items", []), errors)

    cleaned["patch"] = cleaned_patch
    cleaned["items"] = cleaned_items

    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "cleaned_data": cleaned,
    }


def _validate_state_patch(patch: dict, errors: list):
    allowed_keys = {
        "draft_order_id",
        "collection_location",
        "collection_time_text",
        "collection_date",
        "collection_time",
        "payment_method",
        "quote_requested",
        "order_commitment",
        "last_customer_message",
        "notes",
    }
    cleaned = {}

    for key in patch:
        if key not in allowed_keys:
            errors.append(f"patch.{key} is not allowed.")

    for key in allowed_keys:
        if key not in patch:
            continue
        value = patch.get(key)
        if key in ("quote_requested", "order_commitment"):
            cleaned[key] = _to_bool(value)
            continue
        cleaned[key] = to_clean_string(value)

    location = cleaned.get("collection_location", "")
    if location and location not in ALLOWED_COLLECTION_LOCATIONS:
        errors.append("patch.collection_location must be Riversdale, Albertinia, or Any.")

    payment_method = cleaned.get("payment_method", "")
    if payment_method and payment_method not in ALLOWED_PAYMENT_METHODS:
        errors.append("patch.payment_method must be Cash or EFT.")

    return cleaned


def _validate_item_patches(raw_items, errors: list):
    if raw_items in (None, ""):
        return []
    if not isinstance(raw_items, list):
        errors.append("items must be a list.")
        return []

    cleaned_items = []
    for index, item in enumerate(raw_items):
        if not isinstance(item, dict):
            errors.append(f"items[{index}] must be an object.")
            continue

        cleaned = {
            "item_key": to_clean_string(item.get("item_key", item.get("request_item_key", ""))),
            "quantity": item.get("quantity", ""),
            "category": to_clean_string(item.get("category", "")),
            "weight_range": to_clean_string(item.get("weight_range", "")),
            "sex": to_clean_string(item.get("sex", "")),
            "intent_type": to_clean_string(item.get("intent_type", "")) or "primary",
            "status": to_clean_string(item.get("status", "")) or "active",
            "linked_order_line_ids": to_clean_string(item.get("linked_order_line_ids", "")),
            "last_match_status": to_clean_string(item.get("last_match_status", "")),
            "matched_quantity": item.get("matched_quantity", ""),
            "replaced_by_item_key": to_clean_string(item.get("replaced_by_item_key", "")),
            "removal_reason": to_clean_string(item.get("removal_reason", "")),
            "notes": to_clean_string(item.get("notes", "")),
        }

        if not cleaned["item_key"]:
            errors.append(f"items[{index}].item_key is required.")

        quantity = to_float(cleaned["quantity"])
        if cleaned["quantity"] not in ("", None):
            if quantity is None:
                errors.append(f"items[{index}].quantity must be a number.")
            elif quantity <= 0:
                errors.append(f"items[{index}].quantity must be greater than 0.")
            elif int(quantity) != quantity:
                errors.append(f"items[{index}].quantity must be a whole number.")
            else:
                cleaned["quantity"] = int(quantity)

        matched_quantity = to_float(cleaned["matched_quantity"])
        if cleaned["matched_quantity"] not in ("", None):
            if matched_quantity is None or matched_quantity < 0:
                errors.append(f"items[{index}].matched_quantity must be zero or greater.")
            else:
                cleaned["matched_quantity"] = int(matched_quantity)

        if cleaned["category"] and cleaned["category"] not in ALLOWED_CATEGORIES:
            errors.append(f"items[{index}].category must be one of the approved values.")

        if cleaned["weight_range"] and cleaned["weight_range"] not in ALLOWED_WEIGHT_RANGES:
            errors.append(f"items[{index}].weight_range must be one of the approved stored values.")

        if cleaned["sex"] and cleaned["sex"] not in ALLOWED_SEXES:
            errors.append(f"items[{index}].sex must be Male, Female, or Any.")

        if cleaned["intent_type"] not in ALLOWED_INTENT_TYPES:
            errors.append(f"items[{index}].intent_type must be one of the approved values.")

        if cleaned["status"] not in ALLOWED_ITEM_STATUSES:
            errors.append(f"items[{index}].status must be active, removed, or replaced.")

        cleaned_items.append(cleaned)

    return cleaned_items


def _create_intake_row(conversation_id: str, cleaned_data: dict, now_str: str, updated_by: str):
    intake_id = generate_intake_id()
    row = {
        "Intake_ID": intake_id,
        "ConversationId": conversation_id,
        "Account_ID": cleaned_data.get("account_id", ""),
        "Contact_ID": cleaned_data.get("contact_id", ""),
        "Customer_Name": cleaned_data.get("customer_name", ""),
        "Customer_Phone": cleaned_data.get("customer_phone", ""),
        "Customer_Channel": cleaned_data.get("customer_channel", ""),
        "Customer_Language": cleaned_data.get("customer_language", ""),
        "Draft_Order_ID": "",
        "Intake_Status": "Open",
        "Collection_Location": "",
        "Collection_Time_Text": "",
        "Collection_Date": "",
        "Collection_Time": "",
        "Payment_Method": "",
        "Quote_Requested": "No",
        "Order_Commitment": "No",
        "Missing_Fields": "",
        "Next_Action": "ask_missing_field",
        "Ready_For_Draft": "No",
        "Ready_For_Quote": "No",
        "Last_Customer_Message": "",
        "Last_Updated_By": updated_by,
        "Created_At": now_str,
        "Updated_At": now_str,
        "Closed_At": "",
        "Closed_Reason": "",
        "Notes": "",
    }

    append_row(ORDER_INTAKE_STATE_SHEET, [row.get(header, "") for header in INTAKE_STATE_HEADERS])
    return row


def _build_state_updates(intake: dict, patch: dict, cleaned_data: dict, now_str: str, updated_by: str):
    updates = {}
    field_map = {
        "draft_order_id": "Draft_Order_ID",
        "collection_location": "Collection_Location",
        "collection_time_text": "Collection_Time_Text",
        "collection_date": "Collection_Date",
        "collection_time": "Collection_Time",
        "payment_method": "Payment_Method",
        "last_customer_message": "Last_Customer_Message",
        "notes": "Notes",
    }

    identity_map = {
        "account_id": "Account_ID",
        "contact_id": "Contact_ID",
        "customer_name": "Customer_Name",
        "customer_phone": "Customer_Phone",
        "customer_channel": "Customer_Channel",
        "customer_language": "Customer_Language",
    }

    for key, header in identity_map.items():
        value = to_clean_string(cleaned_data.get(key, ""))
        if value and value != to_clean_string(intake.get(header, "")):
            updates[header] = value

    for key, header in field_map.items():
        if key not in patch:
            continue
        value = patch.get(key)
        if value == "" or value is None:
            continue
        if to_clean_string(value) != to_clean_string(intake.get(header, "")):
            updates[header] = value

    if "quote_requested" in patch:
        updates["Quote_Requested"] = _bool_to_sheet(patch.get("quote_requested"))

    if "order_commitment" in patch:
        updates["Order_Commitment"] = _bool_to_sheet(patch.get("order_commitment"))

    if updates:
        updates["Last_Updated_By"] = updated_by
        updates["Updated_At"] = now_str

    return updates


def _merge_item_patches(intake_id: str, conversation_id: str, item_patches: list, now_str: str):
    if not item_patches:
        return {"created_count": 0, "updates": {}}

    existing_items = _get_items_for_intake(intake_id)
    existing_by_key = {
        to_clean_string(item.get("Item_Key", "")): item
        for item in existing_items
        if to_clean_string(item.get("Item_Key", ""))
    }

    updates = {}
    created_count = 0

    for item in item_patches:
        item_key = to_clean_string(item.get("item_key", ""))
        existing = existing_by_key.get(item_key)
        if not existing:
            _append_intake_item(intake_id, conversation_id, item, now_str)
            created_count += 1
            continue

        item_updates = _build_item_updates(existing, item, now_str)
        if item_updates:
            updates[to_clean_string(existing.get("Intake_Item_ID", ""))] = item_updates

    return {"created_count": created_count, "updates": updates}


def _append_intake_item(intake_id: str, conversation_id: str, item: dict, now_str: str):
    status = to_clean_string(item.get("status", "")) or "active"
    row = {
        "Intake_Item_ID": generate_intake_item_id(),
        "Intake_ID": intake_id,
        "ConversationId": conversation_id,
        "Item_Key": to_clean_string(item.get("item_key", "")),
        "Quantity": item.get("quantity", ""),
        "Category": to_clean_string(item.get("category", "")),
        "Weight_Range": to_clean_string(item.get("weight_range", "")),
        "Sex": to_clean_string(item.get("sex", "")) or "Any",
        "Intent_Type": to_clean_string(item.get("intent_type", "")) or "primary",
        "Status": status,
        "Linked_Order_Line_IDs": to_clean_string(item.get("linked_order_line_ids", "")),
        "Last_Match_Status": to_clean_string(item.get("last_match_status", "")),
        "Matched_Quantity": item.get("matched_quantity", ""),
        "Replaced_By_Item_Key": to_clean_string(item.get("replaced_by_item_key", "")),
        "Removal_Reason": to_clean_string(item.get("removal_reason", "")),
        "Notes": to_clean_string(item.get("notes", "")),
        "Created_At": now_str,
        "Updated_At": now_str,
        "Removed_At": now_str if status in ("removed", "replaced") else "",
    }
    append_row(ORDER_INTAKE_ITEMS_SHEET, [row.get(header, "") for header in INTAKE_ITEM_HEADERS])


def _build_item_updates(existing: dict, item: dict, now_str: str):
    field_map = {
        "quantity": "Quantity",
        "category": "Category",
        "weight_range": "Weight_Range",
        "sex": "Sex",
        "intent_type": "Intent_Type",
        "status": "Status",
        "linked_order_line_ids": "Linked_Order_Line_IDs",
        "last_match_status": "Last_Match_Status",
        "matched_quantity": "Matched_Quantity",
        "replaced_by_item_key": "Replaced_By_Item_Key",
        "removal_reason": "Removal_Reason",
        "notes": "Notes",
    }
    updates = {}

    for key, header in field_map.items():
        if key not in item:
            continue
        value = item.get(key)
        if value == "" or value is None:
            continue
        if to_clean_string(value) != to_clean_string(existing.get(header, "")):
            updates[header] = value

    if updates:
        updates["Updated_At"] = now_str
        status = to_clean_string(updates.get("Status", existing.get("Status", "")))
        if status in ("removed", "replaced") and not to_clean_string(existing.get("Removed_At", "")):
            updates["Removed_At"] = now_str

    return updates


def _compute_intake_state(intake: dict, items: list):
    active_items = [
        item for item in items
        if to_clean_string(item.get("Status", "")) == "active"
    ]
    missing = []

    if not active_items:
        missing.append("requested_items")
    else:
        for item in active_items:
            item_key = to_clean_string(item.get("Item_Key", "")) or "item"
            if not to_clean_string(item.get("Quantity", "")):
                missing.append(f"{item_key}.quantity")
            if not to_clean_string(item.get("Category", "")):
                missing.append(f"{item_key}.category")
            if not to_clean_string(item.get("Weight_Range", "")):
                missing.append(f"{item_key}.weight_range")

    if not to_clean_string(intake.get("Collection_Location", "")):
        missing.append("collection_location")

    has_contact = any(
        to_clean_string(intake.get(header, ""))
        for header in ("Customer_Phone", "Contact_ID", "ConversationId")
    )
    if not has_contact:
        missing.append("customer_contact")

    order_commitment = _sheet_bool(intake.get("Order_Commitment", ""))
    if not order_commitment:
        missing.append("order_commitment")

    draft_missing = list(missing)
    ready_for_draft = len(draft_missing) == 0

    quote_missing = list(draft_missing)
    if not to_clean_string(intake.get("Payment_Method", "")):
        quote_missing.append("payment_method")
    if not to_clean_string(intake.get("Draft_Order_ID", "")):
        quote_missing.append("draft_order_id")

    ready_for_quote = len(quote_missing) == 0
    quote_requested = _sheet_bool(intake.get("Quote_Requested", ""))
    draft_order_id = to_clean_string(intake.get("Draft_Order_ID", ""))

    if quote_requested and ready_for_quote:
        next_action = "generate_quote"
        intake_status = "Quote_Requested"
    elif quote_requested and ready_for_draft and not draft_order_id:
        next_action = "create_draft_then_quote"
        intake_status = "Quote_Requested"
        missing = quote_missing
    elif quote_requested and ready_for_draft and draft_order_id:
        next_action = "update_draft_then_quote"
        intake_status = "Quote_Requested"
        missing = quote_missing
    elif ready_for_draft and draft_order_id:
        next_action = "sync_lines"
        intake_status = "Draft_Created"
    elif ready_for_draft:
        next_action = "create_draft"
        intake_status = "Ready_For_Draft"
    else:
        next_action = "ask_missing_field"
        intake_status = "Open"

    return {
        "missing_fields": missing,
        "ready_for_draft": ready_for_draft,
        "ready_for_quote": ready_for_quote,
        "next_action": next_action,
        "intake_status": intake_status,
    }


def _build_context_response(intake: dict, items: list, lookup_status: str, extra: dict = None):
    computed = _compute_intake_state(intake, items)
    response = {
        "success": True,
        "lookup_status": lookup_status,
        "conversation_id": to_clean_string(intake.get("ConversationId", "")),
        "intake_id": to_clean_string(intake.get("Intake_ID", "")),
        "intake_status": to_clean_string(intake.get("Intake_Status", "")) or computed["intake_status"],
        "draft_order_id": to_clean_string(intake.get("Draft_Order_ID", "")),
        "known_fields": {
            "collection_location": to_clean_string(intake.get("Collection_Location", "")),
            "collection_time_text": to_clean_string(intake.get("Collection_Time_Text", "")),
            "collection_date": to_clean_string(intake.get("Collection_Date", "")),
            "collection_time": to_clean_string(intake.get("Collection_Time", "")),
            "payment_method": to_clean_string(intake.get("Payment_Method", "")),
            "quote_requested": _sheet_bool(intake.get("Quote_Requested", "")),
            "order_commitment": _sheet_bool(intake.get("Order_Commitment", "")),
        },
        "items": [_serialize_item(item) for item in items],
        "missing_fields": computed["missing_fields"],
        "ready_for_draft": computed["ready_for_draft"],
        "ready_for_quote": computed["ready_for_quote"],
        "next_action": computed["next_action"],
        "safe_reply_facts": _safe_reply_facts(intake, items),
    }
    if extra:
        response.update(extra)
    return response


def _safe_reply_facts(intake: dict, items: list):
    facts = []
    for item in items:
        if to_clean_string(item.get("Status", "")) != "active":
            continue
        quantity = to_clean_string(item.get("Quantity", ""))
        sex = to_clean_string(item.get("Sex", ""))
        category = to_clean_string(item.get("Category", ""))
        weight_range = to_clean_string(item.get("Weight_Range", "")).replace("_to_", "-").replace("_Kg", " kg")
        facts.append(" ".join(part for part in (quantity, sex, category, weight_range) if part))

    for header in ("Collection_Location", "Collection_Time_Text", "Payment_Method"):
        value = to_clean_string(intake.get(header, ""))
        if value:
            facts.append(value)

    return facts


def _serialize_item(item: dict):
    return {
        "intake_item_id": to_clean_string(item.get("Intake_Item_ID", "")),
        "intake_id": to_clean_string(item.get("Intake_ID", "")),
        "conversation_id": to_clean_string(item.get("ConversationId", "")),
        "item_key": to_clean_string(item.get("Item_Key", "")),
        "quantity": to_float(item.get("Quantity", "")),
        "category": to_clean_string(item.get("Category", "")),
        "weight_range": to_clean_string(item.get("Weight_Range", "")),
        "sex": to_clean_string(item.get("Sex", "")),
        "intent_type": to_clean_string(item.get("Intent_Type", "")),
        "status": to_clean_string(item.get("Status", "")),
        "linked_order_line_ids": to_clean_string(item.get("Linked_Order_Line_IDs", "")),
        "last_match_status": to_clean_string(item.get("Last_Match_Status", "")),
        "matched_quantity": to_float(item.get("Matched_Quantity", "")),
        "replaced_by_item_key": to_clean_string(item.get("Replaced_By_Item_Key", "")),
        "removal_reason": to_clean_string(item.get("Removal_Reason", "")),
        "notes": to_clean_string(item.get("Notes", "")),
    }


def _find_active_intake_by_conversation(conversation_id: str):
    rows = get_all_records(ORDER_INTAKE_STATE_SHEET)
    matches = [
        row for row in rows
        if to_clean_string(row.get("ConversationId", "")) == conversation_id
        and to_clean_string(row.get("Intake_Status", "")) in OPEN_INTAKE_STATUSES
    ]
    if not matches:
        return None
    return sorted(matches, key=lambda row: to_clean_string(row.get("Updated_At", "")), reverse=True)[0]


def _get_items_for_intake(intake_id: str):
    rows = get_all_records(ORDER_INTAKE_ITEMS_SHEET)
    return [
        row for row in rows
        if to_clean_string(row.get("Intake_ID", "")) == intake_id
    ]


def _now_string():
    return datetime.now().strftime("%d %b %Y %H:%M")


def _to_bool(value):
    if isinstance(value, bool):
        return value
    value = to_clean_string(value).lower()
    return value in ("yes", "true", "1", "y")


def _bool_to_sheet(value):
    return "Yes" if _to_bool(value) else "No"


def _sheet_bool(value):
    return _to_bool(value)
