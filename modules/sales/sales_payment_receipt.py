"""Owner-governed payment-state update for canonical sales transactions."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os

from services.database_service import DATABASE_URL_ENV

PAYMENT_STATUSES = {"Unpaid", "Deposit_Paid", "Part_Paid", "Paid"}
PAYMENT_METHODS = {"Cash", "EFT"}


def preview_sale_payment_state(sale_id, payload=None, database_url=None, *, actor_id=""):
    """Build the exact protected payment effect without changing canonical truth."""
    sale_id = str(sale_id or "").strip(); payload = dict(payload or {})
    proposed, errors = _proposed_payment(sale_id, payload, actor_id)
    if errors:
        return {"success": False, "status": "validation_failed", "errors": errors,
                "writes_to_supabase": False}, 400
    database_url = (database_url if database_url is not None
                    else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "status": "not_configured",
                "writes_to_supabase": False}, 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_SALE_PAYMENT_SELECT, (sale_id,))
                row = cursor.fetchone()
        blocked = _blocked_transition(sale_id, row, proposed)
        if blocked:
            return blocked
        preview = _payment_preview(sale_id, row, proposed)
        if _is_exact_transition(row, proposed):
            return {"success": True, "status": "payment_state_already_recorded",
                    "preview": preview, "preview_digest": _preview_digest(preview),
                    "confirmation_required": False,
                    "writes_to_supabase": False}, 200
        return {"success": True, "status": "payment_state_preview_ready",
                "preview": preview, "preview_digest": _preview_digest(preview),
                "confirmation_required": True, "writes_to_supabase": False}, 200
    except Exception as exc:
        return {"success": False, "status": "payment_state_preview_failed",
                "error_type": exc.__class__.__name__, "writes_to_supabase": False}, 503


def record_sale_payment_state(sale_id, payload=None, database_url=None, *, actor_id=""):
    sale_id = str(sale_id or "").strip(); payload = dict(payload or {})
    proposed, errors = _proposed_payment(sale_id, payload, actor_id)
    confirmed_digest = str(payload.get("confirmed_preview_digest") or "").strip().lower()
    if not confirmed_digest:
        errors.append("confirmed_preview_digest is required.")
    if errors:
        return {"success": False, "status": "validation_failed", "errors": errors,
                "writes_to_supabase": False}, 400
    database_url = (database_url if database_url is not None
                    else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "status": "not_configured",
                "writes_to_supabase": False}, 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(_SALE_PAYMENT_SELECT + " for update", (sale_id,))
                row = cursor.fetchone()
                status, method = proposed["payment_status"], proposed["payment_method"]
                paid_at, target_received = proposed["payment_date"], proposed["received_amount"]
                blocked = _blocked_transition(sale_id, row, proposed)
                if blocked:
                    return blocked
                exact = _is_exact_transition(row, proposed)
                if exact:
                    if f"preview {confirmed_digest}" not in str(row[8] or ""):
                        return {"success": False,
                                "status": "existing_receipt_requires_governed_correction",
                                "writes_to_supabase": False}, 409
                    return {"success": True, "status": "payment_state_replay_noop",
                            "created": False,
                            **_receipt_readback(sale_id, row[0], row[1], row[2],
                                row[3], row[4], row[6] if row[6] is not None else row[5], row[7]),
                            "writes_to_supabase": False}, 200
                preview = _payment_preview(sale_id, row, proposed)
                if confirmed_digest != _preview_digest(preview):
                    return {"success": False, "status": "payment_preview_stale_or_mismatched",
                            "writes_to_supabase": False}, 409
                note = _note(row[8], proposed["actor_id"], status, target_received,
                             method, paid_at, confirmed_digest)
                cursor.execute("""update public.sales_transactions set
                        received_total=%s,payment_status=%s,payment_method=%s,
                        payment_date=%s,notes=%s,updated_at=now()
                    where sale_id=%s returning sale_id,payment_status,payment_method,
                        payment_date,received_total,net_total,net_settlement_payable,
                        sale_channel""",
                    (target_received, status, method if status != "Unpaid" else row[2],
                     paid_at if status != "Unpaid" else None, note, sale_id))
                updated = cursor.fetchone()
        return {"success": True, "status": "payment_state_recorded", "created": True,
            **_receipt_readback(updated[0], row[0], updated[1], updated[2],
                updated[3], updated[4], updated[6] if updated[6] is not None else updated[5], updated[7]),
            "writes_to_supabase": True}, 200
    except Exception as exc:
        return {"success": False, "status": "payment_state_write_failed",
                "error_type": exc.__class__.__name__, "writes_to_supabase": False}, 503


_SALE_PAYMENT_SELECT = """select sale_status,payment_status,payment_method,
        payment_date,received_total,net_total,net_settlement_payable,
        sale_channel,notes,buyer_name,destination,external_reference
    from public.sales_transactions where sale_id=%s"""


def _proposed_payment(sale_id, payload, actor_id):
    status = str(payload.get("payment_status") or "").strip()
    method = str(payload.get("payment_method") or "").strip()
    received = _money(payload.get("received_amount"))
    paid_at = _date(payload.get("payment_date"))
    actor = str(actor_id or "").strip()
    errors = []
    if not sale_id: errors.append("sale_id is required.")
    if status not in PAYMENT_STATUSES: errors.append("payment_status is not supported.")
    if not actor: errors.append("authenticated owner actor is required.")
    if status == "Unpaid":
        if received not in (None, Decimal("0")): errors.append("Unpaid cannot record a received amount.")
        received = None
    else:
        if received is None or received <= 0: errors.append("received_amount must be greater than zero.")
        if method not in PAYMENT_METHODS: errors.append("payment_method must be Cash or EFT.")
        if paid_at is None: errors.append("payment_date is required for received money.")
    return {"payment_status": status, "payment_method": method,
            "received_amount": received, "payment_date": paid_at,
            "actor_id": actor,
            "expected_counterparty": str(payload.get("expected_counterparty") or "").strip(),
            "expected_invoice_reference": str(payload.get("expected_invoice_reference") or "").strip()}, errors


def _blocked_transition(sale_id, row, proposed):
    if not row:
        return {"success": False, "status": "not_found",
                "writes_to_supabase": False}, 404
    if str(row[0]) == "Cancelled":
        return {"success": False, "status": "cancelled_sale",
                "writes_to_supabase": False}, 409
    expected_counterparty = proposed.get("expected_counterparty")
    expected_invoice = proposed.get("expected_invoice_reference")
    if expected_counterparty or expected_invoice:
        if len(row) < 12:
            return {"success": False, "status": "payment_transaction_identity_changed",
                    "writes_to_supabase": False}, 409
        current_counterparty = str(row[9] or row[10] or "").strip()
        if (current_counterparty != expected_counterparty
                or str(row[11] or "").strip() != expected_invoice):
            return {"success": False, "status": "payment_transaction_identity_changed",
                    "writes_to_supabase": False}, 409
    due = Decimal(str(row[6] if row[6] is not None else row[5]))
    received = proposed["received_amount"]
    status = proposed["payment_status"]
    if status == "Unpaid" and row[4] not in (None, 0, Decimal("0")):
        return {"success": False, "status": "received_money_requires_governed_correction",
                "writes_to_supabase": False}, 409
    if status == "Paid" and received != due:
        return {"success": False, "status": "paid_amount_must_equal_amount_due",
                "amount_due": str(due), "writes_to_supabase": False}, 409
    if status in {"Deposit_Paid", "Part_Paid"} and received >= due:
        return {"success": False, "status": "partial_amount_must_be_below_amount_due",
                "amount_due": str(due), "writes_to_supabase": False}, 409
    exact = _is_exact_transition(row, proposed)
    existing = (row[4] not in (None, 0, Decimal("0"))
                or str(row[1] or "") in {"Deposit_Paid", "Part_Paid", "Paid"})
    if existing and not exact:
        current_status = str(row[1] or "")
        current_received = Decimal(str(row[4] or 0))
        forward_partial = (current_status == "Deposit_Paid"
                           and status in {"Deposit_Paid", "Part_Paid"})
        forward_part = current_status == "Part_Paid" and status == "Part_Paid"
        forward_paid = current_status in {"Deposit_Paid", "Part_Paid"} and status == "Paid"
        if not ((forward_partial or forward_part or forward_paid)
                and received is not None and received > current_received):
            return {"success": False, "status": "existing_receipt_requires_governed_correction",
                    "writes_to_supabase": False}, 409
    return None


def _is_exact_transition(row, proposed):
    status = proposed["payment_status"]
    return (str(row[1] or "") == status
            and (None if row[4] is None else Decimal(str(row[4]))) == proposed["received_amount"]
            and str(row[2] or "") == (proposed["payment_method"] if status != "Unpaid" else str(row[2] or ""))
            and _date(row[3]) == (proposed["payment_date"] if status != "Unpaid" else _date(row[3])))


def _payment_preview(sale_id, row, proposed):
    due = Decimal(str(row[6] if row[6] is not None else row[5]))
    received = proposed["received_amount"]
    current_received = Decimal(str(row[4] or 0))
    sale_label = _sale_label(row[7])
    amount = None if received is None else str(received)
    paid_at = proposed["payment_date"].isoformat() if proposed["payment_date"] else None
    preview = {"version": "sale_payment_preview_v1", "sale_id": sale_id,
        "canonical_action_service": "sale_payment_receipt",
        "transaction_label": sale_label,
        "sale_status": str(row[0] or ""),
        "current_payment_status": str(row[1] or ""),
        "current_received_amount": None if row[4] is None else str(Decimal(str(row[4])).quantize(Decimal("0.01"))),
        "payment_status": proposed["payment_status"],
        "received_amount": amount,
        "receipt_amount": None if received is None else str((received - current_received).quantize(Decimal("0.01"))),
        "amount_due": str(due.quantize(Decimal("0.01"))),
        "payment_method": proposed["payment_method"] if proposed["payment_status"] != "Unpaid" else str(row[2] or ""),
        "payment_date": paid_at,
        "sale_channel": str(row[7] or ""), "actor_id": proposed["actor_id"]}
    preview["human_readable"] = (
        f"{sale_label} · {sale_id} · receipt R{preview['receipt_amount'] or '0.00'}; "
        f"total received after this receipt R{amount or '0.00'} of R{preview['amount_due']} "
        f"by {preview['payment_method'] or 'unchanged'} "
        f"on {paid_at or 'unchanged'}. No receipt has been recorded yet.")
    return preview


def _sale_label(sale_channel):
    channel = str(sale_channel or "").strip()
    return "Livestock — Auction" if channel.casefold() == "auction" else (
        f"Livestock — {channel}" if channel else "Livestock — Sale")


def _receipt_readback(sale_id, sale_status, payment_status, payment_method,
                      payment_date, received_amount, amount_due, sale_channel):
    sale_completed = str(sale_status) == "Completed"
    is_auction = str(sale_channel or "").casefold() == "auction"
    settlement_received = str(payment_status) == "Paid"
    return {"sale_id": sale_id, "payment_status": payment_status,
        "payment_method": payment_method,
        "payment_date": payment_date.isoformat() if payment_date else None,
        "received_amount": str(received_amount), "amount_due": str(amount_due),
        "sale_channel": sale_channel, "transaction_label": _sale_label(sale_channel),
        "sale_completed": sale_completed,
        "auction_completed": sale_completed if is_auction else None,
        "settlement_received": settlement_received,
        "fully_reconciled": sale_completed and settlement_received,
        "canonical_action_service": "sale_payment_receipt"}


def _preview_digest(preview):
    return sha256(json.dumps(preview, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _money(value):
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _note(existing, actor, status, received, method, paid_at, preview_digest):
    at = datetime.now(timezone.utc).isoformat()
    line = (f"Payment state recorded by {actor} at {at}; preview {preview_digest}: {status}; "
            f"received {received}; method {method or 'unchanged'}; "
            f"date {paid_at.isoformat() if paid_at else 'unchanged'}.")
    return "\n".join(value for value in (str(existing or "").strip(), line) if value)
