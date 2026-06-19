import os


QUOTE_READY_TEMPLATE_NAME_ENV = "MEAT_SALES_QUOTE_READY_TEMPLATE_NAME"
QUOTE_READY_TEMPLATE_LANGUAGE_ENV = "MEAT_SALES_QUOTE_READY_TEMPLATE_LANGUAGE"
DEPOSIT_FOLLOWUP_TEMPLATE_NAME_ENV = "MEAT_SALES_DEPOSIT_FOLLOWUP_TEMPLATE_NAME"
BOOKING_UPDATE_TEMPLATE_NAME_ENV = "MEAT_SALES_BOOKING_UPDATE_TEMPLATE_NAME"
DELIVERY_UPDATE_TEMPLATE_NAME_ENV = "MEAT_SALES_DELIVERY_UPDATE_TEMPLATE_NAME"
FINAL_INVOICE_TEMPLATE_NAME_ENV = "MEAT_SALES_FINAL_INVOICE_TEMPLATE_NAME"


MEAT_WHATSAPP_TEMPLATE_PACK = [
    {
        "key": "quote_ready",
        "template_name": "amadeus_meat_quote_ready",
        "name_env": QUOTE_READY_TEMPLATE_NAME_ENV,
        "language_env": QUOTE_READY_TEMPLATE_LANGUAGE_ENV,
        "category": "UTILITY",
        "priority": 1,
        "when_used": "Estimated quote PDF is ready but the WhatsApp 24h window is closed.",
        "suggested_body": "Hi {{1}}, your Amadeus Farm pork estimate is ready. Please reply YES and I will send the quote details.",
        "variables": ["customer_first_name"],
    },
    {
        "key": "deposit_followup",
        "template_name": "amadeus_meat_deposit_followup",
        "name_env": DEPOSIT_FOLLOWUP_TEMPLATE_NAME_ENV,
        "language_env": QUOTE_READY_TEMPLATE_LANGUAGE_ENV,
        "category": "UTILITY",
        "priority": 2,
        "when_used": "Deposit/pro-forma was sent earlier and no bank-confirmed payment is logged yet.",
        "suggested_body": "Hi {{1}}, we are holding your Amadeus Farm pork preorder under reference {{2}}. Please reply here if you have made payment or need help.",
        "variables": ["customer_first_name", "payment_reference"],
    },
    {
        "key": "booking_update",
        "template_name": "amadeus_meat_booking_update",
        "name_env": BOOKING_UPDATE_TEMPLATE_NAME_ENV,
        "language_env": QUOTE_READY_TEMPLATE_LANGUAGE_ENV,
        "category": "UTILITY",
        "priority": 3,
        "when_used": "Abattoir/butcher timing is confirmed after the WhatsApp 24h window closes.",
        "suggested_body": "Hi {{1}}, we have an update on your Amadeus Farm pork booking {{2}}. Please reply YES and I will send the details.",
        "variables": ["customer_first_name", "payment_reference"],
    },
    {
        "key": "delivery_update",
        "template_name": "amadeus_meat_delivery_update",
        "name_env": DELIVERY_UPDATE_TEMPLATE_NAME_ENV,
        "language_env": QUOTE_READY_TEMPLATE_LANGUAGE_ENV,
        "category": "UTILITY",
        "priority": 4,
        "when_used": "Delivery route/date update must be sent after the WhatsApp 24h window closes.",
        "suggested_body": "Hi {{1}}, your Amadeus Farm pork delivery update for reference {{2}} is ready. Please reply YES and I will send the latest details.",
        "variables": ["customer_first_name", "payment_reference"],
    },
    {
        "key": "final_invoice_ready",
        "template_name": "amadeus_meat_final_invoice_ready",
        "name_env": FINAL_INVOICE_TEMPLATE_NAME_ENV,
        "language_env": QUOTE_READY_TEMPLATE_LANGUAGE_ENV,
        "category": "UTILITY",
        "priority": 5,
        "when_used": "Final packed weight/final invoice is ready and the WhatsApp 24h window is closed.",
        "suggested_body": "Hi {{1}}, your final Amadeus Farm pork invoice for reference {{2}} is ready. Please reply YES and I will send it through.",
        "variables": ["customer_first_name", "payment_reference"],
    },
]


def meat_whatsapp_template_pack(environ=None):
    source = environ if environ is not None else os.environ
    templates = []
    missing_envs = []
    configured_count = 0
    for item in MEAT_WHATSAPP_TEMPLATE_PACK:
        configured_name = _clean(source.get(item["name_env"]), 120)
        language = _clean(source.get(item["language_env"]), 20) or "en"
        configured = bool(configured_name)
        if configured:
            configured_count += 1
        else:
            missing_envs.append(item["name_env"])
        templates.append({
            **item,
            "configured_name": configured_name,
            "configured": configured,
            "language": language,
            "meta_status": "owner_must_confirm_approved_in_whatsapp_manager",
        })
    return {
        "success": True,
        "mode": "meat_sales_whatsapp_template_pack",
        "pilot_status": "ready_when_meta_templates_are_approved_and_env_names_are_set",
        "configured_count": configured_count,
        "required_count": len(MEAT_WHATSAPP_TEMPLATE_PACK),
        "all_configured": configured_count == len(MEAT_WHATSAPP_TEMPLATE_PACK),
        "missing_envs": missing_envs,
        "templates": templates,
        "next_gate": "create_or_approve_templates_in_meta_then_set_missing_envs",
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_meta": False,
        "creates_quote": False,
        "creates_invoice": False,
        "creates_order": False,
        "changes_stock": False,
        "customer_public_output_enabled": False,
    }


def _clean(value, limit=500):
    return str(value or "").strip()[:limit]
