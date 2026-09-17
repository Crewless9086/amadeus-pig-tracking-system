"""Owner-gated preparation of the complete live-stock sales document pack."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from modules.documents.document_service import get_order_documents
from modules.documents.loading_sheet_service import generate_loading_sheet_for_order
from modules.documents.movement_documents_service import (
    generate_health_declaration_for_order,
    generate_removal_certificate_for_order,
)
from modules.documents.quote_service import auto_generate_quote_if_ready
from modules.orders.order_service import get_order_detail


DOCUMENT_TYPES = {
    "loading_sheet": "Loading Sheet",
    "removal_certificate": "Removal Certificate",
    "health_declaration": "Health Declaration",
}


def prepare_live_stock_sales_pack(
    order_id: str,
    payload: Mapping[str, Any] | None = None,
    *,
    order_loader: Callable[[str], Mapping[str, Any] | None] = get_order_detail,
    document_loader: Callable[[str], list[Mapping[str, Any]]] = get_order_documents,
    quote_preparer: Callable[..., Mapping[str, Any]] = auto_generate_quote_if_ready,
    loading_sheet_preparer: Callable[..., Mapping[str, Any]] = generate_loading_sheet_for_order,
    removal_preparer: Callable[..., Mapping[str, Any]] = generate_removal_certificate_for_order,
    health_preparer: Callable[..., Mapping[str, Any]] = generate_health_declaration_for_order,
) -> dict[str, Any]:
    payload = dict(payload or {})
    order_id = clean(order_id, 100)
    if not order_id:
        raise ValueError("order_id is required")
    detail = order_loader(order_id)
    if not detail:
        raise ValueError("Order not found.")
    lines = list(detail.get("lines") or [])
    if not lines:
        raise ValueError("Order has no lines to prepare.")

    created_by = clean(payload.get("created_by") or payload.get("requested_by") or "SAM Live Stock owner", 120)
    force = bool(payload.get("force_regenerate"))
    form_data = payload.get("form_data") if isinstance(payload.get("form_data"), Mapping) else {}
    existing = list(document_loader(order_id) or [])
    results: dict[str, Any] = {}
    errors: list[dict[str, str]] = []

    _run_step(results, errors, "quote", lambda: quote_preparer(order_id, created_by=created_by))
    for key, preparer in (
        ("loading_sheet", lambda: loading_sheet_preparer(order_id, created_by=created_by)),
        ("removal_certificate", lambda: removal_preparer(order_id, form_data=form_data, created_by=created_by)),
        ("health_declaration", lambda: health_preparer(order_id, form_data=form_data, created_by=created_by)),
    ):
        current = None if force else _latest_document(existing, DOCUMENT_TYPES[key])
        if current:
            results[key] = {"success": True, "reused": True, "document": _document_summary(current)}
        else:
            _run_step(results, errors, key, preparer)

    quote = results.get("quote") if isinstance(results.get("quote"), Mapping) else {}
    quote_ready = bool(quote.get("quote_ready"))
    documents_ready = all(bool((results.get(key) or {}).get("success", True)) for key in DOCUMENT_TYPES)
    return {
        "success": not errors and quote_ready and documents_ready,
        "status": "sam_live_stock_sales_pack_ready" if not errors and quote_ready and documents_ready else "sam_live_stock_sales_pack_needs_owner_input",
        "version": "sam_live_stock_sales_pack_v1",
        "order_id": order_id,
        "results": results,
        "errors": errors,
        "missing_fields": list(quote.get("missing_fields") or []),
        "owner_gate_required": True,
        "customer_send_allowed": False,
        "sends_customer_message": False,
        "reserves_stock": False,
        "confirms_payment": False,
        "changes_stock": False,
        "recommended_next": "Review the prepared documents and exact customer reply before any send.",
    }


def _run_step(results, errors, key, callback):
    try:
        value = dict(callback() or {})
        if key == "quote":
            value["success"] = bool(value.get("success", True))
        else:
            value["success"] = bool(value.get("success", True))
        results[key] = value
        if not value.get("success"):
            errors.append({"step": key, "reason": clean(value.get("reason") or value.get("message") or "preparation_failed", 240)})
    except Exception as exc:
        results[key] = {"success": False, "error_type": exc.__class__.__name__}
        errors.append({"step": key, "reason": clean(str(exc), 240)})


def _latest_document(documents, document_type):
    matches = [row for row in documents if clean(row.get("Document_Type"), 80).lower() == document_type.lower() and clean(row.get("Status"), 40).lower() != "void"]
    return matches[-1] if matches else None


def _document_summary(document):
    return {
        "document_id": document.get("Document_ID") or document.get("document_id") or "",
        "document_type": document.get("Document_Type") or document.get("document_type") or "",
        "file_name": document.get("File_Name") or document.get("file_name") or "",
        "status": document.get("Status") or document.get("status") or "",
    }


def clean(value, limit):
    return " ".join(str(value or "").strip().split())[:limit]
