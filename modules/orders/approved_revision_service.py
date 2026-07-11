import hashlib
import json

from modules.documents.document_service import (
    DOCUMENT_TYPE_HEALTH_DECLARATION,
    DOCUMENT_TYPE_LOADING_SHEET,
    DOCUMENT_TYPE_QUOTE,
    DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
    get_order_documents,
)
from modules.documents.loading_sheet_service import (
    generate_loading_sheet_for_order,
    send_loading_sheet_to_owner_telegram,
)
from modules.documents.movement_documents_service import (
    generate_health_declaration_for_order,
    generate_removal_certificate_for_order,
)
from modules.documents.quote_service import auto_generate_quote_if_ready
from modules.orders.order_read import get_order_detail
from modules.orders.order_reservation import reserve_order_lines
from modules.orders.order_write import update_order
from modules.orders.order_line_sync import sync_order_lines_from_request
from modules.pig_weights.pig_weights_controller import (
    apply_purpose_review_queue_decisions,
    create_weight_entry,
)


TERMINAL_ORDER_STATUSES = {"Cancelled", "Completed", "Rejected"}
REVISION_FINGERPRINT_PREFIX = "Revision_Fingerprint:"


def revise_approved_livestock_order(order_id, payload):
    payload = payload or {}
    order_id = str(order_id or "").strip()
    changed_by = _clean(payload.get("changed_by")) or "Oom Sakkie"
    idempotency_key = _clean(payload.get("idempotency_key"))

    if not order_id:
        raise ValueError("order_id is required.")

    detail = get_order_detail(order_id)
    if not detail:
        raise ValueError("Order not found.")

    order = detail.get("order") or {}
    order_status = _clean(order.get("order_status", order.get("Order_Status", "")))
    if order_status != "Approved":
        if order_status in TERMINAL_ORDER_STATUSES:
            raise ValueError(f"Cannot revise terminal order {order_status}.")
        raise ValueError("Only approved orders can use the approved livestock revision action.")

    revision_fingerprint = _revision_fingerprint(order_id, payload)
    if idempotency_key:
        revision_fingerprint = hashlib.sha256(
            f"{revision_fingerprint}|{idempotency_key}".encode("utf-8")
        ).hexdigest()

    operations = {
        "farm_corrections": _apply_farm_corrections(payload, changed_by),
        "order_update": _update_order_header(order_id, payload, changed_by),
        "line_sync": _sync_revision_lines(order_id, payload, changed_by),
    }
    operations["reservation"] = reserve_order_lines(order_id)
    operations["documents"] = _regenerate_documents(order_id, payload, changed_by, revision_fingerprint)
    operations["owner_telegram"] = _send_owner_paperwork(payload, operations["documents"], changed_by)
    operations["customer_quote"] = _customer_quote_step(order_id, payload)

    return {
        "success": True,
        "action": "revise_approved_livestock_order",
        "order_id": order_id,
        "changed_by": changed_by,
        "revision_fingerprint": revision_fingerprint,
        "idempotency_key": idempotency_key,
        "customer_send_gate": "prepared_only_unless_explicit_confirmed_send_payload_present",
        "operations": operations,
        "safety": {
            "normal_draft_sync_guard_preserved": True,
            "approved_revision_mode": True,
            "customer_quote_sent": bool((operations["customer_quote"] or {}).get("sent")),
            "owner_paperwork_send_attempted": bool(operations["owner_telegram"].get("attempted")),
        },
        "message": "Approved livestock order revision completed through the guarded Oom Sakkie workflow.",
    }


def _apply_farm_corrections(payload, changed_by):
    corrections = payload.get("farm_corrections") if isinstance(payload.get("farm_corrections"), list) else []
    perform = payload.get("perform_farm_corrections") is True
    results = []

    for correction in corrections:
        if not isinstance(correction, dict):
            continue
        pig_id = _clean(correction.get("pig_id"))
        tag_number = _clean(correction.get("tag_number"))
        item = {
            "pig_id": pig_id,
            "tag_number": tag_number,
            "weight": None,
            "purpose": None,
        }

        if correction.get("weight_kg") not in (None, ""):
            weight_payload = {
                "pig_id": pig_id,
                "weight_date": correction.get("weight_date") or payload.get("revision_date") or "",
                "weight_kg": correction.get("weight_kg"),
                "condition_notes": _clean(correction.get("condition_notes")) or "Approved order revision sale-readiness correction.",
                "weighed_by": _clean(correction.get("weighed_by")) or changed_by,
                "allow_duplicate": False,
            }
            if perform:
                weight_result, status_code = create_weight_entry(weight_payload)
                item["weight"] = {"status_code": status_code, **weight_result}
                if weight_result.get("duplicate_weight"):
                    item["weight"]["idempotent_skip"] = True
            else:
                item["weight"] = {
                    "success": True,
                    "dry_run": True,
                    "planned_payload": weight_payload,
                    "writes_to_supabase": False,
                    "writes_to_sheets": False,
                }

        purpose = _clean(correction.get("purpose"))
        if purpose:
            purpose_payload = {
                "decisions": [{
                    "pig_id": pig_id,
                    "purpose": purpose,
                    "reason": _clean(correction.get("purpose_reason")) or "Approved order revision sale-readiness correction.",
                    "note": _clean(correction.get("note")),
                }],
                "changed_by": changed_by,
                "dry_run": not perform,
                "allow_reclassify": True,
            }
            purpose_result, status_code = apply_purpose_review_queue_decisions(purpose_payload)
            item["purpose"] = {"status_code": status_code, **purpose_result}

        results.append(item)

    return {
        "attempted": bool(corrections),
        "performed": perform,
        "count": len(results),
        "results": results,
    }


def _update_order_header(order_id, payload, changed_by):
    updates = payload.get("order_updates") if isinstance(payload.get("order_updates"), dict) else {}
    if not updates:
        return {"skipped": True, "reason": "no_order_updates"}
    cleaned = dict(updates)
    cleaned["changed_by"] = changed_by
    return update_order(order_id, cleaned)


def _sync_revision_lines(order_id, payload, changed_by):
    requested_items = payload.get("requested_items")
    if not isinstance(requested_items, list) or not requested_items:
        return {"skipped": True, "reason": "no_requested_items"}
    return sync_order_lines_from_request(
        order_id,
        {
            "requested_items": requested_items,
            "changed_by": changed_by,
            "allow_approved_revision": True,
        },
    )


def _regenerate_documents(order_id, payload, changed_by, revision_fingerprint):
    form_data = payload.get("movement_form_data") if isinstance(payload.get("movement_form_data"), dict) else {}
    documents = {}
    documents["quote"] = _ensure_document(
        order_id,
        DOCUMENT_TYPE_QUOTE,
        revision_fingerprint,
        lambda: auto_generate_quote_if_ready(
            order_id,
            created_by=changed_by,
            allow_approved_revision=True,
            revision_fingerprint=revision_fingerprint,
        ),
    )
    documents["loading_sheet"] = _ensure_document(
        order_id,
        DOCUMENT_TYPE_LOADING_SHEET,
        revision_fingerprint,
        lambda: generate_loading_sheet_for_order(
            order_id,
            created_by=changed_by,
            revision_fingerprint=revision_fingerprint,
        ),
    )
    documents["removal_certificate"] = _ensure_document(
        order_id,
        DOCUMENT_TYPE_REMOVAL_CERTIFICATE,
        revision_fingerprint,
        lambda: generate_removal_certificate_for_order(
            order_id,
            form_data=form_data,
            created_by=changed_by,
            revision_fingerprint=revision_fingerprint,
        ),
    )
    documents["health_declaration"] = _ensure_document(
        order_id,
        DOCUMENT_TYPE_HEALTH_DECLARATION,
        revision_fingerprint,
        lambda: generate_health_declaration_for_order(
            order_id,
            form_data=form_data,
            created_by=changed_by,
            revision_fingerprint=revision_fingerprint,
        ),
    )
    return documents


def _ensure_document(order_id, document_type, revision_fingerprint, generate_fn):
    latest = _latest_document_with_revision(order_id, document_type, revision_fingerprint)
    if latest:
        return {
            "success": True,
            "generated": False,
            "skipped": True,
            "reason": "latest_revision_document_current",
            "document": _document_summary(latest),
        }
    result = generate_fn()
    if isinstance(result, dict) and result.get("document"):
        return result
    if isinstance(result, dict):
        result.setdefault("generated", bool(result.get("success")))
    return result


def _send_owner_paperwork(payload, documents, changed_by):
    if payload.get("send_owner_paperwork") is False:
        return {"attempted": False, "skipped": True, "reason": "send_owner_paperwork_false"}

    chat_id = _clean(payload.get("owner_telegram_chat_id"))
    results = []
    for key in ("loading_sheet", "removal_certificate", "health_declaration"):
        document_id = _document_id_from_result(documents.get(key) or {})
        if not document_id:
            results.append({"document_key": key, "success": False, "skipped": True, "reason": "document_id_missing"})
            continue
        send_result = send_loading_sheet_to_owner_telegram(document_id, sent_by=changed_by, chat_id=chat_id)
        results.append({"document_key": key, **send_result})

    return {
        "attempted": True,
        "results": results,
        "success": all(item.get("success") for item in results) if results else False,
    }


def _customer_quote_step(order_id, payload):
    confirm = payload.get("customer_quote_send_confirmation")
    if isinstance(confirm, dict) and confirm.get("confirmed") is True:
        from modules.orders.order_routes import _send_latest_quote_confirmed

        result = _send_latest_quote_confirmed(
            order_id,
            document_id=confirm.get("document_id", ""),
            conversation_id=confirm.get("conversation_id", ""),
            sent_by=confirm.get("sent_by", "Oom Sakkie"),
            account_id=confirm.get("account_id", "147387"),
            confirmation_source=confirm.get("confirmation_source", "approved_revision"),
            telegram_user_id=confirm.get("telegram_user_id", ""),
            force_resend=confirm.get("force_resend") is True,
        )
        result["sent"] = bool(result.get("success"))
        return result

    from modules.orders.order_routes import _prepare_latest_quote_send_context

    prepared = _prepare_latest_quote_send_context(
        order_id,
        conversation_id=payload.get("conversation_id", ""),
        requested_by=payload.get("changed_by", "Oom Sakkie"),
    )
    prepared["sent"] = False
    return prepared


def _latest_document_with_revision(order_id, document_type, revision_fingerprint):
    documents = get_order_documents(order_id, document_type=document_type)
    matching = [
        item for item in documents
        if _document_has_revision(item, revision_fingerprint)
        and _clean(item.get("Document_Status")) not in {"Voided", "Superseded"}
    ]
    if not matching:
        return None
    return sorted(matching, key=_document_version, reverse=True)[0]


def _document_has_revision(document, revision_fingerprint):
    notes = _clean(document.get("Notes"))
    revision_fingerprint = _clean(revision_fingerprint)
    return (
        f"{REVISION_FINGERPRINT_PREFIX} {revision_fingerprint}" in notes
        or f'"revision_fingerprint":"{revision_fingerprint}"' in notes
    )


def _document_id_from_result(result):
    document = result.get("document") if isinstance(result.get("document"), dict) else {}
    return _clean(result.get("document_id")) or _clean(document.get("document_id"))


def _document_summary(document):
    return {
        "document_id": _clean(document.get("Document_ID")),
        "document_type": _clean(document.get("Document_Type")),
        "document_ref": _clean(document.get("Document_Ref")),
        "document_status": _clean(document.get("Document_Status")),
        "version": document.get("Version", ""),
        "google_drive_url": _clean(document.get("Google_Drive_URL")),
    }


def _document_version(document):
    try:
        return int(document.get("Version", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _revision_fingerprint(order_id, payload):
    stable = {
        "order_id": _clean(order_id),
        "order_updates": payload.get("order_updates") or {},
        "requested_items": payload.get("requested_items") or [],
        "farm_corrections": payload.get("farm_corrections") or [],
        "movement_form_data": payload.get("movement_form_data") or {},
    }
    encoded = json.dumps(stable, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clean(value):
    return str(value or "").strip()
