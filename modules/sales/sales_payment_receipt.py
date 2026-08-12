"""Owner-governed payment-state update for canonical sales transactions."""
from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import os

from services.database_service import DATABASE_URL_ENV

PAYMENT_STATUSES = {"Unpaid", "Deposit_Paid", "Part_Paid", "Paid"}
PAYMENT_METHODS = {"Cash", "EFT"}


def record_sale_payment_state(sale_id, payload=None, database_url=None):
    sale_id = str(sale_id or "").strip(); payload = dict(payload or {})
    status = str(payload.get("payment_status") or "").strip()
    method = str(payload.get("payment_method") or "").strip()
    received = _money(payload.get("received_amount"))
    paid_at = _date(payload.get("payment_date"))
    actor = str(payload.get("updated_by") or "").strip()
    errors = []
    if not sale_id: errors.append("sale_id is required.")
    if status not in PAYMENT_STATUSES: errors.append("payment_status is not supported.")
    if not actor: errors.append("updated_by is required.")
    if status == "Unpaid":
        if received not in (None, Decimal("0")): errors.append("Unpaid cannot record a received amount.")
    else:
        if received is None or received <= 0: errors.append("received_amount must be greater than zero.")
        if method not in PAYMENT_METHODS: errors.append("payment_method must be Cash or EFT.")
        if paid_at is None: errors.append("payment_date is required for received money.")
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
                cursor.execute("""select sale_status,payment_status,payment_method,
                        payment_date,received_total,net_total,net_settlement_payable,
                        sale_channel,notes
                    from public.sales_transactions where sale_id=%s for update""",
                    (sale_id,))
                row = cursor.fetchone()
                if not row:
                    return {"success": False, "status": "not_found",
                            "writes_to_supabase": False}, 404
                if str(row[0]) == "Cancelled":
                    return {"success": False, "status": "cancelled_sale",
                            "writes_to_supabase": False}, 409
                due = Decimal(str(row[6] if row[6] is not None else row[5]))
                if status == "Unpaid" and row[4] not in (None, 0, Decimal("0")):
                    return {"success": False,
                            "status": "received_money_requires_governed_correction",
                            "writes_to_supabase": False}, 409
                target_received = None if status == "Unpaid" else received
                if status == "Paid" and target_received != due:
                    return {"success": False, "status": "paid_amount_must_equal_amount_due",
                            "amount_due": str(due), "writes_to_supabase": False}, 409
                if status in {"Deposit_Paid", "Part_Paid"} and target_received >= due:
                    return {"success": False, "status": "partial_amount_must_be_below_amount_due",
                            "amount_due": str(due), "writes_to_supabase": False}, 409
                exact = (str(row[1] or "") == status
                         and (None if row[4] is None else Decimal(str(row[4]))) == target_received
                         and str(row[2] or "") == (method if status != "Unpaid" else str(row[2] or ""))
                         and _date(row[3]) == (paid_at if status != "Unpaid" else _date(row[3])))
                if exact:
                    return {"success": True, "status": "payment_state_replay_noop",
                            "created": False, "sale_id": sale_id,
                            "writes_to_supabase": False}, 200
                note = _note(row[8], actor, status, target_received, method, paid_at)
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
            "sale_id": updated[0], "payment_status": updated[1],
            "payment_method": updated[2], "payment_date": updated[3].isoformat()
                if updated[3] else None, "received_amount": str(updated[4]),
            "amount_due": str(updated[6] if updated[6] is not None else updated[5]),
            "sale_channel": updated[7], "writes_to_supabase": True}, 200
    except Exception as exc:
        return {"success": False, "status": "payment_state_write_failed",
                "error_type": exc.__class__.__name__, "writes_to_supabase": False}, 503


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


def _note(existing, actor, status, received, method, paid_at):
    at = datetime.now(timezone.utc).isoformat()
    line = (f"Payment state recorded by {actor} at {at}: {status}; "
            f"received {received}; method {method or 'unchanged'}; "
            f"date {paid_at.isoformat() if paid_at else 'unchanged'}.")
    return "\n".join(value for value in (str(existing or "").strip(), line) if value)
