from modules.orders.order_intake_service import _compute_intake_state


def plan_live_stock_next_action(intake_context=None, facts=None, order_state=None):
    intake_context = intake_context if isinstance(intake_context, dict) else {}
    facts = facts if isinstance(facts, dict) else {}
    order_state = order_state if isinstance(order_state, dict) else {}
    intake, items = _planner_inputs(intake_context, facts, order_state)
    computed = _compute_intake_state(intake, items)
    return {
        "version": "sam_live_stock_next_action_plan_v1",
        "goal": _goal_from_items(items, facts),
        "stage": _stage_from_computed(computed),
        "next_action": computed.get("next_action") or "ask_missing_field",
        "missing_fields": list(computed.get("missing_fields") or []),
        "ready_for_draft": bool(computed.get("ready_for_draft")),
        "ready_for_quote": bool(computed.get("ready_for_quote")),
        "intake_status": computed.get("intake_status") or "Open",
        "planner_source": "order_intake_service._compute_intake_state",
        "owner_gate_required": True,
        "order_state": {
            "draft_order_id": _clean(
                order_state.get("draft_order_id")
                or order_state.get("order_id")
                or intake_context.get("draft_order_id")
            ),
        },
    }


def _planner_inputs(intake_context, facts, order_state):
    known = intake_context.get("known_fields") if isinstance(intake_context.get("known_fields"), dict) else {}
    intake = {
        "Collection_Location": known.get("collection_location") or facts.get("location") or "",
        "Collection_Time_Text": known.get("collection_time_text") or known.get("collection_date") or facts.get("timing") or "",
        "Payment_Method": known.get("payment_method") or facts.get("payment_method") or "",
        "Quote_Requested": _bool_sheet(known.get("quote_requested") or facts.get("quote_requested")),
        "Order_Commitment": _bool_sheet(known.get("order_commitment") or facts.get("order_commitment")),
        "Draft_Order_ID": (
            intake_context.get("draft_order_id")
            or known.get("draft_order_id")
            or order_state.get("draft_order_id")
            or order_state.get("order_id")
            or ""
        ),
        "Customer_Phone": facts.get("customer_phone") or "",
        "Contact_ID": facts.get("contact_id") or "",
        "ConversationId": intake_context.get("conversation_id") or facts.get("conversation_id") or "chatwoot",
    }
    items = _active_items_from_context(intake_context)
    if not items:
        items = [_item_from_facts(facts)]
    return intake, [item for item in items if item]


def _active_items_from_context(intake_context):
    items = intake_context.get("items") if isinstance(intake_context.get("items"), list) else []
    normalized = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        status = item.get("status") or item.get("Status") or "active"
        normalized.append({
            "Item_Key": item.get("item_key") or item.get("Item_Key") or f"item_{index}",
            "Quantity": item.get("quantity") or item.get("Quantity") or "",
            "Category": item.get("category") or item.get("Category") or "",
            "Weight_Range": item.get("weight_range") or item.get("Weight_Range") or "",
            "Sex": item.get("sex") or item.get("Sex") or "",
            "Status": status,
        })
    return normalized


def _item_from_facts(facts):
    if not any(facts.get(key) for key in ("quantity", "category", "weight_range", "sex")):
        return {}
    return {
        "Item_Key": "item_1",
        "Quantity": facts.get("quantity") or "",
        "Category": facts.get("category") or "",
        "Weight_Range": facts.get("weight_range") or "",
        "Sex": facts.get("sex") or "",
        "Status": "active",
    }


def _goal_from_items(items, facts):
    quantity = facts.get("quantity") or (items[0].get("Quantity") if items else "")
    category = facts.get("category") or (items[0].get("Category") if items else "")
    weight = facts.get("weight_range") or (items[0].get("Weight_Range") if items else "")
    parts = [str(part).strip() for part in (quantity, category, weight) if str(part or "").strip()]
    return "buy_live_stock" + (": " + " ".join(parts) if parts else "")


def _stage_from_computed(computed):
    action = computed.get("next_action")
    if action == "ask_missing_field":
        return "discovery"
    if action in {"create_draft", "sync_lines"}:
        return "draft_order"
    if action in {"create_draft_then_quote", "update_draft_then_quote", "generate_quote"}:
        return "quote"
    return "qualified"


def _bool_sheet(value):
    return "Yes" if value is True or str(value).strip().lower() in {"1", "true", "yes", "y", "on"} else ""


def _clean(value):
    return " ".join(str(value or "").split())[:120]
