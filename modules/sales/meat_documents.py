import hashlib
import hmac
import json
import mimetypes
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from modules.oom_sakkie.sales_campaign_store import (
    DEFAULT_MEAT_PRICE_BOOK,
    get_active_sales_lead_by_conversation,
    get_sales_lead_preorder_contract,
    list_meat_price_book_entries,
    record_sales_lead_event,
    _resolve_meat_price_rule,
)
from modules.sales.meat_reconciliation import get_meat_reconciliation_status


VAT_NUMBER_ENV = "MEAT_SALES_VAT_NUMBER"
VAT_RATE_ENV = "MEAT_SALES_VAT_RATE"
BANK_ACCOUNT_NAME_ENV = "BANK_ACCOUNT_NAME"
BANK_NAME_ENV = "BANK_NAME"
BANK_ACCOUNT_NUMBER_ENV = "BANK_ACCOUNT_NUMBER"
BANK_BRANCH_CODE_ENV = "BANK_BRANCH_CODE"
BANK_ACCOUNT_TYPE_ENV = "BANK_ACCOUNT_TYPE"
LEGACY_BANK_ACCOUNT_NAME_ENV = "MEAT_SALES_BANK_ACCOUNT_NAME"
LEGACY_BANK_NAME_ENV = "MEAT_SALES_BANK_NAME"
LEGACY_BANK_ACCOUNT_NUMBER_ENV = "MEAT_SALES_BANK_ACCOUNT_NUMBER"
LEGACY_BANK_BRANCH_CODE_ENV = "MEAT_SALES_BANK_BRANCH_CODE"
LEGACY_BANK_ACCOUNT_TYPE_ENV = "MEAT_SALES_BANK_ACCOUNT_TYPE"
DOCUMENT_OUTPUT_DIR_ENV = "MEAT_SALES_DOCUMENT_OUTPUT_DIR"
LOGO_PATH_ENV = "MEAT_SALES_DOCUMENT_LOGO_PATH"
DOCUMENT_AUTOSEND_ENABLED_ENV = "MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED"
QUOTE_READY_TEMPLATE_NAME_ENV = "MEAT_SALES_QUOTE_READY_TEMPLATE_NAME"
QUOTE_READY_TEMPLATE_LANGUAGE_ENV = "MEAT_SALES_QUOTE_READY_TEMPLATE_LANGUAGE"
WHATSAPP_WINDOW_HOURS_ENV = "MEAT_SALES_WHATSAPP_WINDOW_HOURS"
DELIVERY_WEBHOOK_ENABLED_ENV = "MEAT_SALES_DELIVERY_WEBHOOK_ENABLED"
DELIVERY_WEBHOOK_TOKEN_ENV = "MEAT_SALES_DELIVERY_WEBHOOK_TOKEN"

DOCUMENT_TYPE_ESTIMATED_QUOTE = "Estimated Quote"
DOCUMENT_TYPE_DEPOSIT_PRO_FORMA = "Deposit Pro Forma"
DOCUMENT_TYPE_FINAL_INVOICE = "Final Invoice"
DEFAULT_VAT_NUMBER = "4510286224"
DEFAULT_VAT_RATE = 0.15
DEFAULT_OUTPUT_DIR = Path("generated_documents") / "meat_sales"
CHATWOOT_BASE_URL_ENV = "CHATWOOT_BASE_URL"
CHATWOOT_ACCOUNT_ID_ENV = "CHATWOOT_ACCOUNT_ID"
CHATWOOT_API_ACCESS_TOKEN_ENV = "CHATWOOT_API_ACCESS_TOKEN"
CHATWOOT_API_TOKEN_ENV = "CHATWOOT_API_TOKEN"
MIN_DELIVERY_WEBHOOK_TOKEN_CHARS = 32


def meat_document_policy(environ=None):
    source = environ if environ is not None else os.environ
    bank = bank_details(source)
    delivery_policy = meat_document_delivery_webhook_policy(source)
    return {
        "success": True,
        "mode": "meat_sales_document_policy",
        "pilot_payment_method": "EFT",
        "cash_enabled": False,
        "vat_registered": True,
        "vat_number": _vat_number(source),
        "vat_rate": _vat_rate(source),
        "pricing_basis": "vat_inclusive_price_per_kg",
        "document_types": [
            DOCUMENT_TYPE_ESTIMATED_QUOTE,
            DOCUMENT_TYPE_DEPOSIT_PRO_FORMA,
            DOCUMENT_TYPE_FINAL_INVOICE,
        ],
        "bank_details_configured": bank["configured"],
        "document_autosend_enabled": _truthy(source.get(DOCUMENT_AUTOSEND_ENABLED_ENV)),
        "document_autosend_env": DOCUMENT_AUTOSEND_ENABLED_ENV,
        "delivery_webhook_enabled": delivery_policy["enabled"],
        "delivery_webhook_token_configured": delivery_policy["token_configured"],
        "delivery_webhook_enabled_env": DELIVERY_WEBHOOK_ENABLED_ENV,
        "delivery_webhook_token_env": DELIVERY_WEBHOOK_TOKEN_ENV,
        "quote_ready_template_name_configured": bool(_clean(source.get(QUOTE_READY_TEMPLATE_NAME_ENV), 120)),
        "quote_ready_template_name_env": QUOTE_READY_TEMPLATE_NAME_ENV,
        "quote_ready_template_language": _clean(source.get(QUOTE_READY_TEMPLATE_LANGUAGE_ENV), 20) or "en",
        "whatsapp_window_hours": _whatsapp_window_hours(source),
        "bank_detail_envs": [
            BANK_ACCOUNT_NAME_ENV,
            BANK_NAME_ENV,
            BANK_ACCOUNT_NUMBER_ENV,
            BANK_BRANCH_CODE_ENV,
            BANK_ACCOUNT_TYPE_ENV,
        ],
        "legacy_meat_bank_detail_envs_supported": [
            LEGACY_BANK_ACCOUNT_NAME_ENV,
            LEGACY_BANK_NAME_ENV,
            LEGACY_BANK_ACCOUNT_NUMBER_ENV,
            LEGACY_BANK_BRANCH_CODE_ENV,
            LEGACY_BANK_ACCOUNT_TYPE_ENV,
        ],
        "missing_bank_envs": bank["missing_envs"],
        "placeholder_bank_envs": bank["placeholder_envs"],
        **_authority(False, False),
    }


def build_meat_estimated_quote_packet(lead_id, payload=None, environ=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    source = environ if environ is not None else os.environ
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_authority(False, False)}, 400

    contract_result, contract_status = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    if contract_status != 200:
        return contract_result, contract_status
    price_result, price_status = list_meat_price_book_entries(limit=100, database_url=database_url)
    if price_status != 200:
        return price_result, price_status

    packet = build_estimated_quote_packet_from_contract(
        contract_result.get("lead") or {},
        contract_result.get("contract") or {},
        price_result.get("price_entries") or DEFAULT_MEAT_PRICE_BOOK,
        {**payload, "lead_id": lead_id},
        environ=source,
    )
    status_code = 200 if packet.get("quote_safe") else 409
    return packet, status_code


def build_estimated_quote_packet_from_contract(lead, contract, price_entries=None, payload=None, environ=None):
    payload = payload if isinstance(payload, dict) else {}
    source = environ if environ is not None else os.environ
    lead = lead if isinstance(lead, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    summary = contract.get("lead_summary") if isinstance(contract.get("lead_summary"), dict) else {}
    required = contract.get("required_before_money_path") if isinstance(contract.get("required_before_money_path"), dict) else {}

    product_type = _normal_product_type(
        payload.get("product_type")
        or interest.get("product_type")
        or summary.get("product")
        or interest.get("product")
    )
    cut_set = _clean(payload.get("cut_set") or interest.get("cut_set") or summary.get("cut_set"), 80)
    rule = _resolve_meat_price_rule(
        price_entries if isinstance(price_entries, list) and price_entries else DEFAULT_MEAT_PRICE_BOOK,
        product_type,
        cut_set,
    )
    price_per_kg = _number(payload.get("price_per_kg") or rule.get("price_amount"))
    estimated_weight_kg = _estimated_weight_kg(payload, required, product_type)
    deposit_percent = _deposit_percent(payload.get("deposit_rule") or required.get("deposit_amount_or_rule") or rule.get("deposit_rule"), product_type)
    delivery_mode = _clean(required.get("delivery_or_collection") or interest.get("delivery_or_collection"), 80)
    payment_method = _clean(payload.get("payment_method") or required.get("payment_method") or interest.get("payment_method") or "EFT", 80).upper()
    bank = bank_details(source)
    quote_safe, blockers = quote_safe_gate(
        {
            "product_type": product_type,
            "cut_set": cut_set,
            "price_per_kg": price_per_kg,
            "estimated_weight_kg": estimated_weight_kg,
            "deposit_percent": deposit_percent,
            "delivery_mode": delivery_mode,
            "payment_method": payment_method,
        },
        bank,
    )
    totals = calculate_estimated_quote_totals(
        price_per_kg=price_per_kg,
        estimated_weight_kg=estimated_weight_kg,
        deposit_percent=deposit_percent,
        vat_rate=_vat_rate(source),
        delivery_fee=payload.get("delivery_fee"),
    )
    customer = {
        "name": summary.get("buyer_or_contact") or lead.get("contact_label") or lead.get("lead_label") or "Customer",
        "phone": interest.get("customer_phone") or "",
        "channel": lead.get("channel") or "",
        "town": required.get("location") or interest.get("delivery_town") or interest.get("location") or summary.get("location") or "",
        "address": interest.get("delivery_address_line_1") or "",
        "notes": interest.get("delivery_notes") or "",
    }
    document = {
        "document_type": DOCUMENT_TYPE_ESTIMATED_QUOTE,
        "document_ref": _document_ref("MQ", _sale_reference(payload, lead, contract, customer)),
        "document_date": _today(source),
        "valid_until": (datetime.now() + timedelta(days=7)).strftime("%d %b %Y"),
        "payment_reference": _sale_reference(payload, lead, contract, customer),
    }
    return {
        "success": True,
        "status": "quote_safe" if quote_safe else "quote_blocked",
        "mode": "meat_estimated_quote_packet",
        "quote_safe": quote_safe,
        "blockers": blockers,
        "lead_id": payload.get("lead_id") or lead.get("lead_id") or "",
        "document": document,
        "customer": customer,
        "product": {
            "product_type": product_type,
            "product_label": _product_label(product_type),
            "cut_set": cut_set,
            "delivery_or_collection": delivery_mode,
            "delivery_line": _delivery_line(delivery_mode, customer),
            "price_per_kg_vat_inclusive": price_per_kg,
            "estimated_weight_kg": estimated_weight_kg,
            "deposit_percent": deposit_percent,
            "final_weight_rule": "Final invoice uses actual packed weight after butchery.",
        },
        "totals": totals,
        "bank_details": _public_bank_details(bank),
        "vat": {
            "vat_registered": True,
            "vat_number": _vat_number(source),
            "vat_rate": _vat_rate(source),
            "pricing_basis": "VAT-inclusive",
        },
        "sam_preparing_message": "I am preparing your estimated quote now and will send it through shortly.",
        "notes": [
            "Estimated quote only; final amount uses actual packed weight.",
            "Pilot meat sales are EFT only.",
            "POP is not bank confirmation; booking/release moves only once money reflects in the farm account.",
        ],
        **_authority(False, quote_safe),
    }


def generate_meat_estimated_quote_pdf(lead_id, payload=None, environ=None, database_url=None):
    packet, status_code = build_meat_estimated_quote_packet(lead_id, payload, environ=environ, database_url=database_url)
    if status_code >= 400:
        return packet, status_code
    path = render_meat_document_pdf(packet, environ=environ)
    event_result, event_status = record_sales_lead_event(
        lead_id,
        {
            "event_type": "status_observed",
            "status_observed": "estimated_quote_prepared",
            "recorded_by": "backend_meat_documents",
            "notes": json.dumps({
                "kind": "meat_estimated_quote_prepared",
                "document": packet.get("document", {}),
                "totals": packet.get("totals", {}),
                "file_path": str(path),
            }, ensure_ascii=True, sort_keys=True),
        },
        database_url=database_url,
    )
    return {
        **packet,
        "status": "estimated_quote_pdf_generated",
        "file_path": str(path),
        "document_event_status_code": event_status,
        "document_event": event_result if isinstance(event_result, dict) else {},
        **_authority(True, True),
    }, 201


def send_meat_estimated_quote_to_chatwoot(lead_id, payload=None, environ=None, database_url=None, chatwoot_sender=None):
    payload = payload if isinstance(payload, dict) else {}
    source = environ if environ is not None else os.environ
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", "sent": False, **_authority(False, False)}, 400
    if not _truthy(source.get(DOCUMENT_AUTOSEND_ENABLED_ENV)):
        return {
            "success": False,
            "status": "meat_sales_document_autosend_disabled",
            "sent": False,
            "required_env": DOCUMENT_AUTOSEND_ENABLED_ENV,
            **_authority(False, False),
        }, 409

    contract_result, contract_status = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    if contract_status != 200:
        return contract_result, contract_status
    lead = contract_result.get("lead") if isinstance(contract_result.get("lead"), dict) else {}
    conversation_id = _clean(payload.get("conversation_id") or lead.get("chatwoot_conversation_id"), 100)
    if not conversation_id:
        return {
            "success": False,
            "status": "chatwoot_conversation_id_required",
            "sent": False,
            **_authority(False, False),
        }, 409

    quote_packet, quote_status = build_meat_estimated_quote_packet(lead_id, payload, environ=source, database_url=database_url)
    if quote_status != 200 or not quote_packet.get("quote_safe"):
        return {**quote_packet, "sent": False, **_authority(False, False)}, quote_status
    document = quote_packet.get("document") if isinstance(quote_packet.get("document"), dict) else {}
    document_ref = _clean(document.get("document_ref"), 120)
    window = quote_send_window_state(lead, source)
    if window.get("requires_template"):
        template_packet = build_quote_ready_template_packet(lead, quote_packet, window, source)
        _record_document_send_event(
            lead_id,
            "estimated_quote_template_required",
            conversation_id,
            document_ref,
            {"window": window, "template": template_packet.get("template", {})},
            database_url=database_url,
        )
        return {
            **quote_packet,
            "success": False,
            "status": "estimated_quote_template_required",
            "sent": False,
            "chatwoot_accepted": False,
            "delivery_status": "template_required_before_document_send",
            "conversation_id": conversation_id,
            "document_ref": document_ref,
            "whatsapp_window": window,
            "template_required": True,
            "template_packet": template_packet,
            **_authority(False, True),
        }, 409
    if not _truthy(payload.get("force_resend")) and _document_send_already_attempted(lead, document_ref):
        return {
            **quote_packet,
            "success": True,
            "status": "estimated_quote_send_already_recorded",
            "sent": False,
            "chatwoot_accepted": False,
            "delivery_status": "already_recorded_no_duplicate_send",
            "conversation_id": conversation_id,
            "document_ref": document_ref,
            **_authority(False, True),
        }, 200

    pdf_result, pdf_status = generate_meat_estimated_quote_pdf(lead_id, payload, environ=source, database_url=database_url)
    if pdf_status >= 400:
        return {**pdf_result, "sent": False}, pdf_status
    file_path = Path(pdf_result.get("file_path") or "")
    message = _document_send_message(pdf_result)
    sender = chatwoot_sender or send_chatwoot_attachment
    _record_document_send_event(lead_id, "estimated_quote_send_attempted", conversation_id, document_ref, database_url=database_url)
    try:
        send_result = sender(conversation_id, message, file_path, environ=source)
    except Exception as exc:
        failure = {"error_type": exc.__class__.__name__, "error": str(exc)[:200]}
        _record_document_send_event(lead_id, "estimated_quote_send_failed", conversation_id, document_ref, failure, database_url=database_url)
        return {
            **pdf_result,
            "success": False,
            "status": "chatwoot_document_send_failed",
            "sent": False,
            "conversation_id": conversation_id,
            "chatwoot_send": failure,
            **_authority(True, True),
            "calls_chatwoot": True,
        }, 502

    delivery = _delivery_state_from_chatwoot_result(send_result)
    accepted = delivery["chatwoot_accepted"]
    verified = delivery["delivery_confirmed"]
    event_type = "estimated_quote_sent" if verified else "estimated_quote_chatwoot_accepted"
    status = "estimated_quote_sent" if verified else "estimated_quote_chatwoot_accepted_unverified"
    event_result = _record_document_send_event(
        lead_id,
        event_type,
        conversation_id,
        document_ref,
        {"file_path": str(file_path), "chatwoot": send_result, "delivery": delivery},
        database_url=database_url,
    )
    return {
        **pdf_result,
        "status": status,
        "sent": verified,
        "chatwoot_accepted": accepted,
        "delivery_status": delivery["delivery_status"],
        "delivery_confirmed": verified,
        "conversation_id": conversation_id,
        "document_ref": document_ref,
        "message_text": message,
        "chatwoot_send": send_result,
        "send_event": event_result[0] if isinstance(event_result, tuple) else {},
        "send_event_status_code": event_result[1] if isinstance(event_result, tuple) else 0,
        **_authority(True, True),
        "sends_customer_message": True,
        "calls_chatwoot": True,
        "customer_public_output_enabled": verified,
    }, 200


def send_chatwoot_attachment(conversation_id, message, file_path, environ=None):
    source = environ if environ is not None else os.environ
    base_url = _clean(source.get(CHATWOOT_BASE_URL_ENV) or "https://app.chatwoot.com", 200).rstrip("/")
    account_id = _clean(source.get(CHATWOOT_ACCOUNT_ID_ENV) or "147387", 80)
    token = _clean(source.get(CHATWOOT_API_ACCESS_TOKEN_ENV) or source.get(CHATWOOT_API_TOKEN_ENV), 300)
    conversation_id = _clean(conversation_id, 100)
    message = _clean(message, 1600)
    path = Path(file_path)
    if not base_url:
        raise RuntimeError("CHATWOOT_BASE_URL is required")
    if not account_id:
        raise RuntimeError("CHATWOOT_ACCOUNT_ID is required")
    if not token:
        raise RuntimeError("CHATWOOT_API_ACCESS_TOKEN is required")
    if not conversation_id:
        raise RuntimeError("conversation_id is required")
    if not message:
        raise RuntimeError("message is required")
    if not path.exists() or not path.is_file():
        raise RuntimeError("attachment file is required")

    boundary = "----AmadeusMeatDocument" + hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:16]
    body = _multipart_body(
        boundary,
        {
            "content": message,
            "message_type": "outgoing",
            "private": "false",
        },
        "attachments[]",
        path.name,
        mimetypes.guess_type(path.name)[0] or "application/pdf",
        path.read_bytes(),
    )
    req = urllib_request.Request(
        f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}/messages",
        data=body,
        method="POST",
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "api_access_token": token,
        },
    )
    try:
        with urllib_request.urlopen(req, timeout=25) as response:
            parsed = _parse_json_object(response.read().decode("utf-8", errors="replace"))
            return {
                "status_code": getattr(response, "status", 200),
                "message_id": _clean(parsed.get("id"), 100),
                "conversation_id": conversation_id,
                "file_name": path.name,
            }
    except urllib_error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:200]
        raise RuntimeError(f"chatwoot_attachment_http_{exc.code}: {detail}") from exc


def meat_document_delivery_webhook_policy(environ=None):
    source = environ if environ is not None else os.environ
    token = str(source.get(DELIVERY_WEBHOOK_TOKEN_ENV, "") or "").strip()
    return {
        "success": True,
        "mode": "meat_sales_chatwoot_delivery_status_webhook",
        "enabled": _truthy(source.get(DELIVERY_WEBHOOK_ENABLED_ENV)),
        "enabled_env": DELIVERY_WEBHOOK_ENABLED_ENV,
        "token_configured": len(token) >= MIN_DELIVERY_WEBHOOK_TOKEN_CHARS,
        "token_env": DELIVERY_WEBHOOK_TOKEN_ENV,
        "min_token_chars": MIN_DELIVERY_WEBHOOK_TOKEN_CHARS,
        "records_delivery_statuses": ["failed", "undelivered", "bounced", "sent", "delivered", "read"],
        "target_document_type": DOCUMENT_TYPE_ESTIMATED_QUOTE,
        **_authority(False, False),
    }


def authorize_meat_document_delivery_webhook(headers, query_args=None, environ=None):
    source = environ if environ is not None else os.environ
    if not _truthy(source.get(DELIVERY_WEBHOOK_ENABLED_ENV)):
        return False, _delivery_webhook_denied("meat_sales_delivery_webhook_disabled", source)
    expected = str(source.get(DELIVERY_WEBHOOK_TOKEN_ENV, "") or "").strip()
    if not expected:
        return False, _delivery_webhook_denied("meat_sales_delivery_webhook_token_not_configured", source)
    if len(expected) < MIN_DELIVERY_WEBHOOK_TOKEN_CHARS:
        return False, _delivery_webhook_denied("meat_sales_delivery_webhook_token_too_short", source)
    if not _delivery_webhook_token_matches(headers or {}, query_args or {}, expected):
        return False, _delivery_webhook_denied("meat_sales_delivery_webhook_auth_denied", source)
    return True, {}


def handle_meat_document_delivery_status_webhook(payload, *, environ=None, database_url=None):
    source = environ if environ is not None else os.environ
    normalized = normalize_meat_document_delivery_status_payload(payload)
    if not normalized["processable"]:
        return {
            "success": True,
            "status": normalized["status"],
            "processed": False,
            "delivery": normalized,
            **_authority(False, False),
        }, 200

    lead_result, lead_status = _resolve_delivery_webhook_lead(normalized, database_url=database_url)
    if lead_status >= 400:
        return {
            "success": False,
            "status": lead_result.get("status", "delivery_status_lead_lookup_failed"),
            "processed": False,
            "delivery": normalized,
            "lead_lookup": lead_result,
            **_authority(False, False),
        }, lead_status

    lead = lead_result.get("lead") if isinstance(lead_result.get("lead"), dict) else {}
    lead_id = _clean(normalized.get("lead_id") or lead.get("lead_id"), 100)
    if not lead_id:
        return {
            "success": False,
            "status": "delivery_status_lead_id_required",
            "processed": False,
            "delivery": normalized,
            **_authority(False, False),
        }, 409

    document_ref = normalized.get("document_ref")
    message_id = normalized.get("message_id")
    delivery_status = normalized.get("delivery_status")
    if _delivery_status_already_recorded(lead, message_id, delivery_status, document_ref):
        return {
            "success": True,
            "status": "delivery_status_already_recorded",
            "processed": False,
            "lead_id": lead_id,
            "delivery": normalized,
            **_authority(False, False),
        }, 200

    event_type = _delivery_webhook_event_type(delivery_status)
    event_result, event_status = _record_document_send_event(
        lead_id,
        event_type,
        normalized.get("conversation_id") or lead.get("chatwoot_conversation_id", ""),
        document_ref,
        {
            "message_id": message_id,
            "delivery_status": delivery_status,
            "delivery_confirmed": normalized.get("delivery_confirmed"),
            "delivery_failed": normalized.get("delivery_failed"),
            "event_name": normalized.get("event_name"),
            "source_payload_keys": normalized.get("source_payload_keys", []),
        },
        database_url=database_url,
    )
    if event_status >= 400:
        return {
            "success": False,
            "status": "delivery_status_event_record_failed",
            "processed": False,
            "lead_id": lead_id,
            "delivery": normalized,
            "event": event_result,
            **_authority(True, False),
        }, event_status

    return {
        "success": True,
        "status": event_type,
        "processed": True,
        "lead_id": lead_id,
        "document_ref": document_ref,
        "message_id": message_id,
        "delivery_status": delivery_status,
        "delivery_confirmed": normalized.get("delivery_confirmed"),
        "delivery_failed": normalized.get("delivery_failed"),
        "event": event_result,
        **_authority(True, False),
    }, 201


def normalize_meat_document_delivery_status_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    message = _first_dict(
        payload.get("message"),
        payload.get("messages"),
        payload.get("message_payload"),
        payload.get("data"),
    )
    conversation = _first_dict(
        payload.get("conversation"),
        message.get("conversation") if isinstance(message, dict) else {},
    )
    attachments = _first_list(
        payload.get("attachments"),
        message.get("attachments") if isinstance(message, dict) else [],
    )
    content = _clean(
        payload.get("content")
        or payload.get("text")
        or message.get("content")
        or message.get("text"),
        2000,
    )
    event_name = _clean(payload.get("event") or payload.get("event_name") or payload.get("webhook_event"), 120).lower()
    raw_status = _clean(
        payload.get("delivery_status")
        or payload.get("message_status")
        or payload.get("status")
        or message.get("delivery_status")
        or message.get("message_status")
        or message.get("status")
        or message.get("source_status"),
        80,
    ).lower()
    delivery_status = _normal_delivery_status(raw_status)
    conversation_id = _clean(
        payload.get("conversation_id")
        or payload.get("chatwoot_conversation_id")
        or conversation.get("id")
        or message.get("conversation_id"),
        100,
    )
    lead_id = _clean(
        payload.get("lead_id")
        or payload.get("sales_lead_id")
        or _nested(payload, "custom_attributes", "lead_id")
        or _nested(conversation, "custom_attributes", "lead_id")
        or _nested(message, "custom_attributes", "lead_id"),
        100,
    )
    message_id = _clean(
        payload.get("message_id")
        or payload.get("id")
        or message.get("message_id")
        or message.get("id")
        or message.get("source_id"),
        100,
    )
    document_ref = _clean(
        payload.get("document_ref")
        or _nested(payload, "custom_attributes", "document_ref")
        or _nested(message, "custom_attributes", "document_ref")
        or _document_ref_from_text(content)
        or _document_ref_from_attachments(attachments),
        120,
    )
    outgoing = _is_outgoing_message(payload, message)
    if not delivery_status:
        return {
            "processable": False,
            "status": "delivery_status_missing",
            "event_name": event_name,
            "source_payload_keys": sorted(payload.keys()),
        }
    if not outgoing and event_name and "message" in event_name:
        return {
            "processable": False,
            "status": "delivery_status_ignored_non_outgoing_message",
            "event_name": event_name,
            "delivery_status": delivery_status,
            "source_payload_keys": sorted(payload.keys()),
        }
    if not lead_id and not conversation_id:
        return {
            "processable": False,
            "status": "delivery_status_missing_lead_or_conversation",
            "event_name": event_name,
            "delivery_status": delivery_status,
            "source_payload_keys": sorted(payload.keys()),
        }
    return {
        "processable": True,
        "status": "delivery_status_processable",
        "event_name": event_name,
        "lead_id": lead_id,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "document_ref": document_ref,
        "delivery_status": delivery_status,
        "delivery_confirmed": delivery_status in {"delivered", "read"},
        "delivery_failed": delivery_status in {"failed", "undelivered", "bounced"},
        "source_payload_keys": sorted(payload.keys()),
    }


def generate_meat_deposit_pro_forma_pdf(lead_id, payload=None, environ=None, database_url=None):
    quote_packet, status_code = build_meat_estimated_quote_packet(lead_id, payload, environ=environ, database_url=database_url)
    if status_code >= 400:
        return quote_packet, status_code
    packet = build_deposit_pro_forma_packet(quote_packet)
    path = render_meat_document_pdf(packet, environ=environ)
    return {
        **packet,
        "status": "deposit_pro_forma_pdf_generated",
        "file_path": str(path),
        **_authority(False, True),
    }, 201


def build_deposit_pro_forma_packet(quote_packet):
    quote_packet = quote_packet if isinstance(quote_packet, dict) else {}
    totals = quote_packet.get("totals") if isinstance(quote_packet.get("totals"), dict) else {}
    document = dict(quote_packet.get("document") or {})
    document["document_type"] = DOCUMENT_TYPE_DEPOSIT_PRO_FORMA
    document["document_ref"] = document.get("document_ref", "").replace("MQ-", "MP-") or _document_ref("MP", document.get("payment_reference"))
    return {
        **quote_packet,
        "mode": "meat_deposit_pro_forma_packet",
        "document": document,
        "totals": {
            **totals,
            "amount_due_now": totals.get("deposit_due"),
            "amount_due_now_label": _money_label(totals.get("deposit_due")),
        },
        "notes": [
            "Deposit confirms the preorder gate only.",
            "POP can be received by Sam, but only bank-confirmed money unlocks slaughter and fulfilment gates.",
        ],
    }


def build_final_invoice_packet_from_reconciliation(lead_id, payload=None, environ=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    source = environ if environ is not None else os.environ
    result, status_code = get_meat_reconciliation_status(lead_id, database_url=database_url)
    if status_code != 200:
        return result, status_code
    reconciliation = result.get("reconciliation") if isinstance(result.get("reconciliation"), dict) else {}
    actual_weight = _number(payload.get("actual_packed_weight_kg") or reconciliation.get("actual_packed_weight_kg"))
    price_per_kg = _number(payload.get("price_per_kg") or reconciliation.get("price_per_kg"))
    deposit_confirmed = _number(reconciliation.get("deposit_confirmed_amount")) or 0
    if actual_weight is None or price_per_kg is None:
        return {"success": False, "status": "actual_weight_and_price_required", **_authority(False, False)}, 409
    totals = calculate_final_invoice_totals(
        price_per_kg=price_per_kg,
        actual_weight_kg=actual_weight,
        deposit_confirmed=deposit_confirmed,
        vat_rate=_vat_rate(source),
        delivery_fee=payload.get("delivery_fee"),
    )
    pay_ref = reconciliation.get("payment_reference") or payment_reference(lead_id)
    return {
        "success": True,
        "status": "final_invoice_packet_ready",
        "mode": "meat_final_invoice_packet",
        "lead_id": lead_id,
        "document": {
            "document_type": DOCUMENT_TYPE_FINAL_INVOICE,
            "document_ref": _document_ref("MI", pay_ref),
            "document_date": _today(source),
            "payment_reference": pay_ref,
        },
        "product": {
            "actual_weight_kg": actual_weight,
            "price_per_kg_vat_inclusive": price_per_kg,
        },
        "totals": totals,
        "vat": {
            "vat_registered": True,
            "vat_number": _vat_number(source),
            "vat_rate": _vat_rate(source),
            "pricing_basis": "VAT-inclusive",
        },
        "bank_details": _public_bank_details(bank_details(source)),
        "notes": [
            "Final invoice uses actual packed weight.",
            "Delivery/release remains blocked until the final balance reflects in the farm account.",
        ],
        **_authority(False, True),
    }, 200


def generate_meat_final_invoice_pdf(lead_id, payload=None, environ=None, database_url=None):
    packet, status_code = build_final_invoice_packet_from_reconciliation(lead_id, payload, environ=environ, database_url=database_url)
    if status_code >= 400:
        return packet, status_code
    path = render_meat_document_pdf(packet, environ=environ)
    return {
        **packet,
        "status": "final_invoice_pdf_generated",
        "file_path": str(path),
        **_authority(False, True),
    }, 201


def calculate_estimated_quote_totals(price_per_kg, estimated_weight_kg, deposit_percent=50, vat_rate=DEFAULT_VAT_RATE, delivery_fee=None):
    price = _number(price_per_kg)
    weight = _number(estimated_weight_kg)
    percent = _number(deposit_percent) or 50
    delivery = _number(delivery_fee)
    meat_total = _money((price or 0) * (weight or 0))
    total_incl = _money(meat_total + (delivery or 0))
    vat_split = split_vat_inclusive(total_incl, vat_rate)
    deposit_due = _money(total_incl * (percent / 100))
    return {
        "estimated_meat_total": meat_total,
        "delivery_fee": delivery,
        "delivery_fee_label": _money_label(delivery) if delivery is not None else "To be confirmed",
        "total_including_vat": total_incl,
        "subtotal_ex_vat": vat_split["subtotal_ex_vat"],
        "vat_amount": vat_split["vat_amount"],
        "vat_rate": vat_split["vat_rate"],
        "deposit_percent": percent,
        "deposit_due": deposit_due,
        "estimated_balance_before_delivery": _money(max(0, total_incl - deposit_due)),
    }


def calculate_final_invoice_totals(price_per_kg, actual_weight_kg, deposit_confirmed=0, vat_rate=DEFAULT_VAT_RATE, delivery_fee=None):
    price = _number(price_per_kg)
    weight = _number(actual_weight_kg)
    deposit = _number(deposit_confirmed) or 0
    delivery = _number(delivery_fee)
    meat_total = _money((price or 0) * (weight or 0))
    total_incl = _money(meat_total + (delivery or 0))
    vat_split = split_vat_inclusive(total_incl, vat_rate)
    return {
        "final_meat_total": meat_total,
        "delivery_fee": delivery,
        "delivery_fee_label": _money_label(delivery) if delivery is not None else "To be confirmed",
        "total_including_vat": total_incl,
        "subtotal_ex_vat": vat_split["subtotal_ex_vat"],
        "vat_amount": vat_split["vat_amount"],
        "vat_rate": vat_split["vat_rate"],
        "deposit_confirmed": _money(deposit),
        "balance_due": _money(max(0, total_incl - deposit)),
    }


def split_vat_inclusive(total_including_vat, vat_rate=DEFAULT_VAT_RATE):
    total = _money(total_including_vat)
    rate = _number(vat_rate)
    if rate is None or rate < 0:
        rate = DEFAULT_VAT_RATE
    subtotal = _money(total / (1 + rate)) if rate else total
    vat = _money(total - subtotal)
    return {
        "total_including_vat": total,
        "subtotal_ex_vat": subtotal,
        "vat_amount": vat,
        "vat_rate": rate,
    }


def quote_safe_gate(values, bank):
    blockers = []
    if values.get("product_type") not in {"half_carcass", "full_carcass", "custom_cut"}:
        blockers.append("supported_meat_product_required")
    if values.get("product_type") in {"half_carcass", "full_carcass", "custom_cut"} and not values.get("cut_set"):
        blockers.append("cut_set_required")
    if _number(values.get("price_per_kg")) is None or _number(values.get("price_per_kg")) <= 0:
        blockers.append("active_price_per_kg_required")
    if _number(values.get("estimated_weight_kg")) is None or _number(values.get("estimated_weight_kg")) <= 0:
        blockers.append("estimated_weight_required")
    if _number(values.get("deposit_percent")) is None or _number(values.get("deposit_percent")) <= 0:
        blockers.append("deposit_rule_required")
    if values.get("payment_method") != "EFT":
        blockers.append("pilot_is_eft_only")
    if not values.get("delivery_mode"):
        blockers.append("delivery_or_collection_required")
    if not bank.get("configured"):
        blockers.append("bank_details_required")
    if bank.get("placeholder_envs"):
        blockers.append("bank_details_placeholder_values")
    return not blockers, blockers


def render_meat_document_pdf(packet, output_path=None, environ=None):
    source = environ if environ is not None else os.environ
    document = packet.get("document") if isinstance(packet.get("document"), dict) else {}
    totals = packet.get("totals") if isinstance(packet.get("totals"), dict) else {}
    product = packet.get("product") if isinstance(packet.get("product"), dict) else {}
    output = Path(output_path) if output_path else _default_output_path(document, source)
    output.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(str(output), pagesize=A4, rightMargin=14 * mm, leftMargin=14 * mm, topMargin=12 * mm, bottomMargin=12 * mm)
    styles = getSampleStyleSheet()
    normal = styles["Normal"]
    small = ParagraphStyle("Small", parent=normal, fontSize=8, leading=10)
    title = ParagraphStyle("Title", parent=normal, fontSize=22, leading=26, textColor=colors.HexColor("#213f2b"), alignment=2)
    label = ParagraphStyle("Label", parent=normal, fontSize=9, leading=11, textColor=colors.HexColor("#5b675f"))
    bold = ParagraphStyle("Bold", parent=normal, fontName="Helvetica-Bold")

    story = []
    logo = _logo_path(source)
    header_left = []
    if logo and logo.exists():
        header_left.append(Image(str(logo), width=24 * mm, height=18 * mm, kind="proportional"))
    header_left.extend([
        Paragraph("<b>AMADEUS FARM</b>", ParagraphStyle("Brand", parent=normal, fontSize=16, leading=19, textColor=colors.HexColor("#213f2b"))),
        Paragraph("Sustainable Piglets & Produce", small),
        Paragraph("Riversdale | Western Cape", small),
        Paragraph(f"VAT: {_vat_number(source)}", small),
    ])
    header_right = [
        Paragraph(f"<b>{document.get('document_type', DOCUMENT_TYPE_ESTIMATED_QUOTE).upper()}</b>", title),
        Paragraph(f"<b>{document.get('document_ref', '')}</b>", normal),
        Paragraph(f"Date: {document.get('document_date', '')}", normal),
    ]
    story.append(Table([[header_left, header_right]], colWidths=[105 * mm, 77 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP"), ("ALIGN", (1, 0), (1, 0), "RIGHT")]))
    story.append(Spacer(1, 7 * mm))
    story.append(Table([
        [Paragraph("<b>CUSTOMER</b>", bold), Paragraph("<b>MEAT PREORDER</b>", bold)],
        [_customer_block(packet, normal), _product_block(product, normal)],
    ], colWidths=[89 * mm, 89 * mm], style=_box_style()))
    story.append(Spacer(1, 8 * mm))
    rows = [[Paragraph("<b>Description</b>", normal), Paragraph("<b>Qty/Weight</b>", normal), Paragraph("<b>Rate</b>", normal), Paragraph("<b>Amount</b>", normal)]]
    rows.append([
        Paragraph(f"<b>{product.get('product_label', 'Pork')} - {product.get('cut_set', '')}</b><br/>Estimated only. Final amount uses actual packed weight.", normal),
        Paragraph(f"{product.get('estimated_weight_kg') or product.get('actual_weight_kg') or ''} kg", normal),
        Paragraph(_money_label(product.get('price_per_kg_vat_inclusive')), normal),
        Paragraph(_money_label(totals.get("estimated_meat_total") or totals.get("final_meat_total")), normal),
    ])
    rows.append([
        Paragraph("Delivery", normal),
        Paragraph(product.get("delivery_or_collection") or "", normal),
        Paragraph("", normal),
        Paragraph(totals.get("delivery_fee_label", "To be confirmed"), normal),
    ])
    table = Table(rows, colWidths=[94 * mm, 28 * mm, 28 * mm, 32 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#24482f")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c6b6")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6ded4")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 0), (3, -1), "RIGHT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 7 * mm))
    story.append(_totals_table(totals, normal))
    story.append(Spacer(1, 8 * mm))
    story.append(Table([
        [_bank_block(packet, normal), _note_block(packet, normal)],
    ], colWidths=[89 * mm, 89 * mm], style=[("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(Spacer(1, 8 * mm))
    story.append(Paragraph("Thank you for supporting a small farm system: traceable, planned, and handled with care.", label))
    doc.build(story)
    return output


def bank_details(environ=None):
    source = environ if environ is not None else os.environ
    values = {
        "account_name": _bank_env(source, BANK_ACCOUNT_NAME_ENV, LEGACY_BANK_ACCOUNT_NAME_ENV, 160),
        "bank_name": _bank_env(source, BANK_NAME_ENV, LEGACY_BANK_NAME_ENV, 120),
        "account_number": _bank_env(source, BANK_ACCOUNT_NUMBER_ENV, LEGACY_BANK_ACCOUNT_NUMBER_ENV, 80),
        "branch_code": _bank_env(source, BANK_BRANCH_CODE_ENV, LEGACY_BANK_BRANCH_CODE_ENV, 80),
        "account_type": _bank_env(source, BANK_ACCOUNT_TYPE_ENV, LEGACY_BANK_ACCOUNT_TYPE_ENV, 80) or "Business account",
    }
    required = {
        BANK_ACCOUNT_NAME_ENV: values["account_name"],
        BANK_NAME_ENV: values["bank_name"],
        BANK_ACCOUNT_NUMBER_ENV: values["account_number"],
        BANK_BRANCH_CODE_ENV: values["branch_code"],
    }
    missing = [key for key, value in required.items() if not value]
    placeholders = [key for key, value in required.items() if _looks_placeholder(value)]
    return {**values, "configured": not missing and not placeholders, "missing_envs": missing, "placeholder_envs": placeholders}


def payment_reference(lead_id, environ=None):
    return _short_reference(lead_id)


def quote_send_window_state(lead, environ=None, now=None):
    source = environ if environ is not None else os.environ
    lead = lead if isinstance(lead, dict) else {}
    state = _clean(lead.get("whatsapp_window_state"), 80) or "unknown"
    last_inbound = _parse_datetime(lead.get("last_inbound_at"))
    current = now or datetime.now(timezone.utc)
    age_hours = None
    stale = True
    if last_inbound:
        age_hours = round((current - last_inbound).total_seconds() / 3600, 2)
        stale = age_hours > _whatsapp_window_hours(source)
    open_state = state == "open" and not stale
    return {
        "whatsapp_window_state": state,
        "last_inbound_at": _clean(lead.get("last_inbound_at"), 80),
        "age_hours": age_hours,
        "window_hours": _whatsapp_window_hours(source),
        "service_window_open": open_state,
        "requires_template": not open_state,
        "reason": "service_window_open" if open_state else ("last_inbound_too_old" if last_inbound else "last_inbound_unknown"),
    }


def build_quote_ready_template_packet(lead, quote_packet, window, environ=None):
    source = environ if environ is not None else os.environ
    lead = lead if isinstance(lead, dict) else {}
    document = quote_packet.get("document") if isinstance(quote_packet.get("document"), dict) else {}
    customer = quote_packet.get("customer") if isinstance(quote_packet.get("customer"), dict) else {}
    totals = quote_packet.get("totals") if isinstance(quote_packet.get("totals"), dict) else {}
    template_name = _clean(source.get(QUOTE_READY_TEMPLATE_NAME_ENV), 120)
    template_language = _clean(source.get(QUOTE_READY_TEMPLATE_LANGUAGE_ENV), 20) or "en"
    return {
        "mode": "quote_ready_whatsapp_template_required",
        "template_configured": bool(template_name),
        "template_required": True,
        "template": {
            "name": template_name,
            "language": template_language,
            "required_env": QUOTE_READY_TEMPLATE_NAME_ENV,
            "approval_required_in_whatsapp_manager": True,
            "category_suggestion": "UTILITY",
            "purpose": "Reopen the WhatsApp service window so Sam can send the estimated quote PDF.",
            "suggested_body": "Hi {{1}}, your Amadeus Farm pork estimate is ready. Please reply YES and I will send the quote details.",
            "parameters": [
                customer.get("name") or lead.get("contact_label") or "there",
                document.get("document_ref", ""),
                _money_label(totals.get("total_including_vat")),
            ],
        },
        "whatsapp_window": window,
        "next_action": (
            "Configure an approved WhatsApp template name before automatic recovery can send."
            if not template_name
            else "Send the approved WhatsApp template, then wait for the customer reply before sending the PDF."
        ),
        "sends_document_now": False,
    }


def _document_send_message(packet):
    document = packet.get("document") if isinstance(packet.get("document"), dict) else {}
    totals = packet.get("totals") if isinstance(packet.get("totals"), dict) else {}
    ref = document.get("payment_reference") or ""
    total = _money_label(totals.get("total_including_vat"))
    deposit = _money_label(totals.get("deposit_due"))
    return (
        f"Here is your estimated pork quote. The estimate is {total} incl VAT, "
        f"with a deposit of {deposit}. Please use reference {ref} for EFT. "
        "Final amount is confirmed after actual packed weight."
    )


def _document_send_already_attempted(lead, document_ref):
    events = lead.get("events") if isinstance(lead.get("events"), list) else []
    for event in events:
        if not isinstance(event, dict):
            continue
        if event.get("event_type") not in {"estimated_quote_chatwoot_accepted", "estimated_quote_sent"}:
            continue
        notes = _parse_json_object(event.get("notes", ""))
        if _clean(notes.get("document_ref"), 120) == document_ref:
            return True
    return False


def _record_document_send_event(lead_id, event_type, conversation_id, document_ref, extra=None, database_url=None):
    notes = {
        "source": "backend_meat_documents",
        "kind": event_type,
        "conversation_id": conversation_id,
        "document_ref": document_ref,
        **(extra if isinstance(extra, dict) else {}),
    }
    return record_sales_lead_event(
        lead_id,
        {
            "event_type": event_type,
            "status_observed": event_type,
            "recorded_by": "backend_meat_documents",
            "notes": json.dumps(notes, ensure_ascii=True, sort_keys=True),
        },
        database_url=database_url,
    )


def _delivery_state_from_chatwoot_result(result):
    result = result if isinstance(result, dict) else {}
    raw_status = _clean(
        result.get("delivery_status")
        or result.get("status")
        or result.get("message_status")
        or result.get("source_status"),
        80,
    ).lower()
    http_status = _number(result.get("status_code"))
    accepted = bool(http_status and 200 <= http_status < 300)
    if raw_status in {"delivered", "read"}:
        return {
            "chatwoot_accepted": accepted,
            "delivery_status": raw_status,
            "delivery_confirmed": True,
            "delivery_failed": False,
        }
    if raw_status in {"sent"}:
        return {
            "chatwoot_accepted": accepted,
            "delivery_status": "sent_unverified",
            "delivery_confirmed": False,
            "delivery_failed": False,
        }
    if raw_status in {"failed", "undelivered", "bounced"}:
        return {
            "chatwoot_accepted": accepted,
            "delivery_status": raw_status,
            "delivery_confirmed": False,
            "delivery_failed": True,
        }
    return {
        "chatwoot_accepted": accepted,
        "delivery_status": "chatwoot_accepted_unverified" if accepted else "chatwoot_not_accepted",
        "delivery_confirmed": False,
        "delivery_failed": not accepted,
    }


def _resolve_delivery_webhook_lead(normalized, database_url=None):
    lead_id = _clean(normalized.get("lead_id"), 100)
    if lead_id:
        return get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    conversation_id = _clean(normalized.get("conversation_id"), 100)
    if not conversation_id:
        return {"success": False, "status": "conversation_id_required", **_authority(False, False)}, 400
    return get_active_sales_lead_by_conversation(conversation_id, database_url=database_url)


def _delivery_webhook_event_type(delivery_status):
    if delivery_status in {"delivered", "read"}:
        return "estimated_quote_delivery_read" if delivery_status == "read" else "estimated_quote_delivery_delivered"
    if delivery_status in {"failed", "undelivered", "bounced"}:
        return "estimated_quote_delivery_failed"
    return "estimated_quote_delivery_status_observed"


def _delivery_status_already_recorded(lead, message_id, delivery_status, document_ref):
    events = lead.get("events") if isinstance(lead.get("events"), list) else []
    event_type = _delivery_webhook_event_type(delivery_status)
    message_id = _clean(message_id, 100)
    document_ref = _clean(document_ref, 120)
    for event in events:
        if not isinstance(event, dict) or event.get("event_type") != event_type:
            continue
        notes = _parse_json_object(event.get("notes", ""))
        if _clean(notes.get("delivery_status"), 80) != delivery_status:
            continue
        same_message = message_id and _clean(notes.get("message_id"), 100) == message_id
        same_document = document_ref and _clean(notes.get("document_ref"), 120) == document_ref
        if same_message or same_document:
            return True
    return False


def _normal_delivery_status(value):
    status = _clean(value, 80).lower().replace(" ", "_")
    if status in {"delivered", "read", "sent", "failed", "undelivered", "bounced"}:
        return status
    if status in {"delivery_failed", "send_failed", "error", "errored"}:
        return "failed"
    if status in {"seen"}:
        return "read"
    if status in {"queued", "created", "accepted", "processed"}:
        return "sent"
    return ""


def _is_outgoing_message(payload, message):
    candidates = [
        payload.get("message_type"),
        payload.get("direction"),
        payload.get("source"),
        message.get("message_type") if isinstance(message, dict) else "",
        message.get("direction") if isinstance(message, dict) else "",
        message.get("source") if isinstance(message, dict) else "",
    ]
    text = " ".join(_clean(item, 40).lower() for item in candidates if item)
    if "incoming" in text or "inbound" in text:
        return False
    return True


def _document_ref_from_text(text):
    match = re.search(r"\bM[QPF]-20\d{2}-[A-Z0-9]{3,10}\b", str(text or "").upper())
    return match.group(0) if match else ""


def _document_ref_from_attachments(attachments):
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        candidate = _document_ref_from_text(
            attachment.get("file_name")
            or attachment.get("filename")
            or attachment.get("data_url")
            or attachment.get("download_url")
            or attachment.get("url")
        )
        if candidate:
            return candidate
    return ""


def _first_dict(*values):
    for value in values:
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    return item
    return {}


def _first_list(*values):
    for value in values:
        if isinstance(value, list):
            return value
    return []


def _nested(source, *keys):
    current = source if isinstance(source, dict) else {}
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return current


def _delivery_webhook_token_matches(headers, query_args, expected):
    authorization = str(headers.get("Authorization", "") or "").strip()
    if authorization.startswith("Bearer "):
        return hmac.compare_digest(authorization[len("Bearer "):].strip(), expected)
    provided = str(headers.get("X-Amadeus-Meat-Delivery-Webhook-Key", "") or "").strip()
    if provided:
        return hmac.compare_digest(provided, expected)
    provided = str(query_args.get("token") or query_args.get("delivery_token") or "").strip()
    return hmac.compare_digest(provided, expected)


def _delivery_webhook_denied(status, source):
    return {
        "success": False,
        "status": status,
        "processed": False,
        "policy": meat_document_delivery_webhook_policy(source),
        **_authority(False, False),
    }


def _customer_block(packet, style):
    customer = packet.get("customer") if isinstance(packet.get("customer"), dict) else {}
    lines = [
        customer.get("name", "Customer"),
        customer.get("town", ""),
        customer.get("address", ""),
        customer.get("channel", ""),
    ]
    return Paragraph("<br/>".join(_clean(line, 240) for line in lines if line), style)


def _product_block(product, style):
    rows = [
        f"Product: <b>{product.get('product_label', '')}</b>",
        f"Cut set: <b>{product.get('cut_set', '')}</b>",
        f"Delivery: <b>{product.get('delivery_line', product.get('delivery_or_collection', ''))}</b>",
        "Payment: <b>EFT only</b>",
    ]
    return Paragraph("<br/>".join(rows), style)


def _bank_block(packet, style):
    bank = packet.get("bank_details") if isinstance(packet.get("bank_details"), dict) else {}
    doc = packet.get("document") if isinstance(packet.get("document"), dict) else {}
    lines = [
        "<b>EFT DETAILS</b>",
        f"Account name: {bank.get('account_name', '')}",
        f"Bank: {bank.get('bank_name', '')}",
        f"Account: {bank.get('account_number', '')}",
        f"Branch: {bank.get('branch_code', '')}",
        f"Reference: {doc.get('payment_reference', '')}",
    ]
    return Paragraph("<br/>".join(lines), style)


def _note_block(packet, style):
    notes = packet.get("notes") if isinstance(packet.get("notes"), list) else []
    return Paragraph("<b>IMPORTANT NOTE</b><br/>" + "<br/>".join(_clean(note, 300) for note in notes), style)


def _totals_table(totals, style):
    rows = [
        ["Subtotal ex VAT", _money_label(totals.get("subtotal_ex_vat"))],
        [f"VAT ({int((totals.get('vat_rate') or 0) * 100)}%)", _money_label(totals.get("vat_amount"))],
        ["Total incl VAT", _money_label(totals.get("total_including_vat"))],
    ]
    if totals.get("deposit_due") is not None:
        rows.append([f"Deposit due ({totals.get('deposit_percent'):g}%)", _money_label(totals.get("deposit_due"))])
        rows.append(["Estimated balance", _money_label(totals.get("estimated_balance_before_delivery"))])
    if totals.get("balance_due") is not None:
        rows.append(["Deposit confirmed", "-" + _money_label(totals.get("deposit_confirmed"))])
        rows.append(["Balance due", _money_label(totals.get("balance_due"))])
    table = Table(rows, colWidths=[135 * mm, 43 * mm])
    table.setStyle(TableStyle([
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 0.5, colors.HexColor("#24482f")),
    ]))
    return table


def _box_style():
    return [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3ee")),
        ("BOX", (0, 0), (-1, -1), 0.25, colors.HexColor("#b8c6b6")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#d6ded4")),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]


def _estimated_weight_kg(payload, required, product_type):
    explicit = _number(payload.get("estimated_weight_kg") or payload.get("estimated_weight_or_size") or required.get("estimated_weight_or_size"))
    if explicit is not None:
        return explicit
    if product_type == "full_carcass":
        return 40.0
    return 20.0


def _deposit_percent(value, product_type):
    parsed = _number(value)
    if parsed is not None:
        return parsed
    return 70.0 if product_type == "custom_cut" else 50.0


def _delivery_line(mode, customer):
    if mode == "delivery":
        town = customer.get("town") or "delivery town"
        return f"Delivery to {town}; fee to be confirmed"
    if mode == "collection":
        return "Collection"
    return "To be confirmed"


def _public_bank_details(bank):
    return {key: bank.get(key, "") for key in ("account_name", "bank_name", "account_number", "branch_code", "account_type")}


def _default_output_path(document, source):
    root = Path(source.get(DOCUMENT_OUTPUT_DIR_ENV) or DEFAULT_OUTPUT_DIR)
    ref = _clean(document.get("document_ref") or "meat-document", 120).replace("/", "-")
    return root / f"{ref}.pdf"


def _logo_path(source):
    explicit = _clean(source.get(LOGO_PATH_ENV), 300)
    if explicit:
        return Path(explicit)
    candidate = Path("static") / "document-assets" / "amadeus-logo.png"
    return candidate if candidate.exists() else None


def _document_ref(prefix, seed):
    return f"{prefix}-{datetime.now().year}-{_short_reference(seed)}"


def _sale_reference(payload, lead, contract, customer):
    payload = payload if isinstance(payload, dict) else {}
    lead = lead if isinstance(lead, dict) else {}
    contract = contract if isinstance(contract, dict) else {}
    customer = customer if isinstance(customer, dict) else {}
    required = contract.get("required_before_money_path") if isinstance(contract.get("required_before_money_path"), dict) else {}
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    candidates = [
        payload.get("payment_reference"),
        payload.get("sale_ref"),
        payload.get("order_id"),
        required.get("payment_reference"),
        required.get("order_id"),
        interest.get("payment_reference"),
        interest.get("order_id"),
        lead.get("linked_order_id"),
        lead.get("linked_preorder_id"),
        payload.get("lead_id"),
        lead.get("lead_id"),
        lead.get("id"),
        customer.get("name"),
    ]
    for candidate in candidates:
        reference = _short_reference(candidate)
        if reference:
            return reference
    return _short_reference(datetime.now().isoformat())


def _short_reference(value):
    text = str(value or "").strip().upper()
    if not text:
        return ""
    last_token = text.split("-")[-1]
    compact = "".join(ch for ch in last_token if ch.isalnum())
    if not compact:
        compact = "".join(ch for ch in text if ch.isalnum())
    if len(compact) <= 6 and compact:
        return compact
    if compact:
        return compact[-6:]
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:6].upper()
    return digest


def _bank_env(source, shared_key, legacy_key, limit):
    shared = _clean(source.get(shared_key), limit)
    if shared:
        return shared
    return _clean(source.get(legacy_key), limit)


def _today(source):
    value = _clean(source.get("MEAT_SALES_DOCUMENT_DATE"), 40)
    if value:
        return value
    return datetime.now().strftime("%d %b %Y")


def _vat_number(source):
    return _clean(source.get(VAT_NUMBER_ENV) or DEFAULT_VAT_NUMBER, 40)


def _vat_rate(source):
    parsed = _number(source.get(VAT_RATE_ENV))
    if parsed is None:
        return DEFAULT_VAT_RATE
    if parsed > 1:
        parsed = parsed / 100
    return parsed


def _whatsapp_window_hours(source):
    parsed = _number(source.get(WHATSAPP_WINDOW_HOURS_ENV))
    if parsed is None or parsed <= 0:
        return 23.5
    return min(parsed, 24)


def _parse_datetime(value):
    text = _clean(value, 80)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normal_product_type(value):
    text = str(value or "").strip().lower().replace(" ", "_")
    if text in {"half_carcass", "full_carcass", "custom_cut"}:
        return text
    if "full" in text or "whole" in text:
        return "full_carcass"
    if "custom" in text:
        return "custom_cut"
    return "half_carcass"


def _product_label(product_type):
    return {
        "half_carcass": "Half carcass pork",
        "full_carcass": "Full carcass pork",
        "custom_cut": "Custom cut pork",
    }.get(product_type, "Pork")


def _looks_placeholder(value):
    text = str(value or "").strip().lower()
    return not text or any(marker in text for marker in ("[", "]", "placeholder", "todo", "tbc", "xxx", "account number"))


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _money_label(value):
    amount = _number(value)
    if amount is None:
        return "To be confirmed"
    return f"R{amount:,.2f}"


def _number(value):
    if value is None or value == "":
        return None
    try:
        if isinstance(value, str):
            value = value.replace("R", "").replace("r", "").replace(",", "").replace("kg", "").replace("%", "").strip()
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _money(value):
    return round(float(value or 0), 2)


def _multipart_body(boundary, fields, file_field, filename, content_type, file_bytes):
    lines = []
    for name, value in fields.items():
        lines.extend([
            f"--{boundary}\r\n".encode("utf-8"),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode("utf-8"),
            str(value).encode("utf-8"),
            b"\r\n",
        ])
    lines.extend([
        f"--{boundary}\r\n".encode("utf-8"),
        f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'.encode("utf-8"),
        f"Content-Type: {content_type}\r\n\r\n".encode("utf-8"),
        file_bytes,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ])
    return b"".join(lines)


def _parse_json_object(value):
    try:
        parsed = json.loads(value or "{}")
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _authority(writes_farm_data, creates_quote):
    return {
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": bool(creates_quote),
        "creates_invoice": False,
        "creates_order": False,
        "changes_stock": False,
        "writes_farm_data": bool(writes_farm_data),
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }
