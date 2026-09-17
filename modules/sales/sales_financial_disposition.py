"""Protected correction of a completed sale to a zero-consideration disposition."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
import os

from services.database_service import DATABASE_URL_ENV

DISPOSITION = "Charitable_Giveaway"
PAYMENT_STATUS = "Not_Applicable"


def preview_charitable_disposition(sale_id, payload=None, database_url=None, *, actor_id=""):
    return _run(sale_id, payload, database_url, actor_id=actor_id, confirm=False)


def confirm_charitable_disposition(sale_id, payload=None, database_url=None, *, actor_id=""):
    return _run(sale_id, payload, database_url, actor_id=actor_id, confirm=True)


def _run(sale_id, payload, database_url, *, actor_id, confirm):
    sale_id = str(sale_id or "").strip()
    payload = dict(payload or {})
    actor_id = str(actor_id or "").strip()
    reason = str(payload.get("reason") or "").strip()
    correction_reason = str(payload.get("correction_reason") or "").strip()
    errors = []
    if not sale_id:
        errors.append("sale_id is required.")
    if not actor_id:
        errors.append("authenticated owner actor is required.")
    if len(reason) < 8:
        errors.append("reason must describe the charitable purpose.")
    if len(correction_reason) < 8:
        errors.append("correction_reason must explain any prior payment entry.")
    confirmed_digest = str(payload.get("confirmed_preview_digest") or "").strip().lower()
    if confirm and len(confirmed_digest) != 64:
        errors.append("confirmed_preview_digest is required.")
    if errors:
        return {"success": False, "status": "validation_failed", "errors": errors,
                "writes_to_supabase": False}, 400
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "status": "not_configured", "writes_to_supabase": False}, 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_SELECT + (" for update" if confirm else ""), (sale_id,))
                row = cursor.fetchone()
                blocked = _blocked(row)
                if blocked:
                    return blocked
                preview = _preview(sale_id, row, actor_id, reason, correction_reason)
                digest = _digest(preview)
                if not confirm:
                    return {"success": True, "status": "charitable_disposition_preview_ready",
                            "preview": preview, "preview_digest": digest,
                            "confirmation_required": True, "writes_to_supabase": False}, 200
                if confirmed_digest != digest:
                    return {"success": False, "status": "charitable_disposition_preview_stale_or_mismatched",
                            "writes_to_supabase": False}, 409
                evidence = {**preview, "version": "sales_financial_disposition_evidence_v1",
                            "confirmed_preview_digest": confirmed_digest,
                            "recorded_at": datetime.now(timezone.utc).isoformat()}
                evidence_sha = _digest(evidence)
                cursor.execute("""update public.sales_transactions set
                        financial_disposition=%s,receivable_total=0,received_total=0,
                        payment_status=%s,payment_method=null,payment_date=null,
                        payment_received_evidence_json=null,payment_evidence_sha256=null,
                        financial_disposition_evidence_json=%s::jsonb,
                        financial_disposition_evidence_sha256=%s,updated_at=now()
                    where sale_id=%s""",
                    (DISPOSITION, PAYMENT_STATUS, json.dumps(evidence, sort_keys=True),
                     evidence_sha, sale_id))
                if row[12]:
                    cursor.execute("""update public.orders set payment_status=%s,updated_at=now()
                        where order_id=%s""", (PAYMENT_STATUS, row[12]))
                cursor.execute(_SELECT, (sale_id,))
                updated = cursor.fetchone()
        return {"success": True, "status": "charitable_disposition_recorded",
                "sale_id": sale_id, "financial_disposition": updated[9],
                "list_value": str(Decimal(str(updated[4])).quantize(Decimal('0.01'))),
                "receivable_total": str(Decimal(str(updated[10])).quantize(Decimal('0.01'))),
                "payment_status": updated[1], "received_total": str(updated[3]),
                "linked_order_id": updated[12], "fully_reconciled": True,
                "evidence_sha256": evidence_sha, "writes_to_supabase": True}, 200
    except Exception as exc:
        return {"success": False, "status": "charitable_disposition_failed",
                "error_type": exc.__class__.__name__, "writes_to_supabase": False}, 503


_SELECT = """select sale_status,payment_status,payment_method,received_total,
        net_total,payment_date,payment_received_evidence_json,payment_evidence_sha256,
        financial_disposition,financial_disposition,receivable_total,
        financial_disposition_evidence_sha256,linked_order_id,sale_stream
    from public.sales_transactions where sale_id=%s"""


def _blocked(row):
    if not row:
        return {"success": False, "status": "not_found", "writes_to_supabase": False}, 404
    if row[0] != "Completed" or row[13] != "Livestock":
        return {"success": False, "status": "completed_livestock_sale_required",
                "writes_to_supabase": False}, 409
    if row[8] == DISPOSITION:
        return {"success": False, "status": "charitable_disposition_already_recorded",
                "writes_to_supabase": False}, 409
    return None


def _preview(sale_id, row, actor_id, reason, correction_reason):
    previous_evidence = row[6] if isinstance(row[6], dict) else None
    return {"version": "sales_financial_disposition_preview_v1", "sale_id": sale_id,
            "actor_id": actor_id, "financial_disposition": DISPOSITION,
            "list_value": str(Decimal(str(row[4])).quantize(Decimal('0.01'))),
            "receivable_total": "0.00", "payment_status": PAYMENT_STATUS,
            "received_total": "0.00", "reason": reason,
            "correction_reason": correction_reason,
            "prior_payment_state": {"payment_status": row[1],
                "received_total": None if row[3] is None else str(row[3]),
                "payment_method": row[2],
                "payment_date": row[5].isoformat() if row[5] else None,
                "payment_evidence": previous_evidence,
                "payment_evidence_sha256": row[7]},
            "linked_order_id": row[12],
            "human_readable": (f"{sale_id}: keep list value R{Decimal(str(row[4])):.2f}; "
                "record Charitable Giveaway with R0.00 receivable and no payment due. "
                "The prior payment state remains inside correction evidence.")}


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()
