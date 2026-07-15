import hashlib
import json
import os
from datetime import datetime, timezone

from modules.sales.meat_ops import get_meat_ops_status
from services.database_service import DATABASE_URL_ENV


RECONCILIATION_EVENT_TYPES = {
    "packed_weight_recorded",
    "final_balance_draft",
    "balance_requested",
    "balance_confirmed_in_bank",
    "balance_note",
}


def get_meat_reconciliation_status(lead_id, database_url=None):
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_authority(False)}, 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False), 503
    ops_result, ops_status = get_meat_ops_status(lead_id, database_url=database_url)
    if ops_status != 200:
        return ops_result, ops_status
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True), 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                events = _fetch_reconciliation_events(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("meat_reconciliation_read_failed", exc), 503
    reconciliation = _reconciliation_status(
        ops_result.get("reservations") or [],
        ops_result.get("deposits") or [],
        events,
    )
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "meat_final_reconciliation_append_only",
        "lead_id": lead_id,
        "reconciliation_events": events,
        "reconciliation": reconciliation,
        "meat_ops": {
            "assembly": ops_result.get("assembly") or {},
            "reservations": ops_result.get("reservations") or [],
            "deposits": ops_result.get("deposits") or [],
        },
        **_authority(False),
    }, 200


def record_meat_reconciliation_event(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_authority(False)}, 400
    event_type = _clean(payload.get("event_type") or "packed_weight_recorded", 100)
    if event_type not in RECONCILIATION_EVENT_TYPES:
        return {"success": False, "status": "invalid_reconciliation_event_type", **_authority(False)}, 400
    reservation_id = _clean(payload.get("reservation_id"), 100)
    if not reservation_id:
        return {"success": False, "status": "reservation_id_required", **_authority(False)}, 400
    if event_type == "packed_weight_recorded":
        if not _number(payload.get("actual_packed_weight_kg")):
            return {"success": False, "status": "actual_packed_weight_required", **_authority(False)}, 400
        if not _number(payload.get("price_per_kg")):
            return {"success": False, "status": "price_per_kg_required", **_authority(False)}, 400
    if event_type == "balance_confirmed_in_bank":
        if not _number(payload.get("balance_confirmed_amount")) and not _number(payload.get("amount")):
            return {"success": False, "status": "balance_confirmed_amount_required", **_authority(False)}, 400
        if not _clean(payload.get("payment_reference"), 160):
            return {"success": False, "status": "balance_reference_required", **_authority(False)}, 400

    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False), 503
    ops_result, ops_status = get_meat_ops_status(lead_id, database_url=database_url)
    if ops_status != 200:
        return ops_result, ops_status
    reservation = _reservation_by_id(ops_result.get("reservations") or [], reservation_id)
    if not reservation:
        return {"success": False, "status": "reservation_not_found", **_authority(False)}, 404

    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True), 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                existing_events = _fetch_reconciliation_events(cursor, lead_id=lead_id)
                event = _event_params(lead_id, reservation, payload, ops_result.get("deposits") or [], existing_events)
                _insert_reconciliation_event(cursor, event)
                events = _fetch_reconciliation_events(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("meat_reconciliation_write_failed", exc), 503
    reconciliation = _reconciliation_status(
        ops_result.get("reservations") or [],
        ops_result.get("deposits") or [],
        events,
    )
    return {
        "success": True,
        "configured": True,
        "status": event_type,
        "mode": "meat_final_reconciliation_append_only",
        "reconciliation_event": event,
        "reconciliation_events": events,
        "reconciliation": reconciliation,
        "next_gate": reconciliation.get("next_gate", ""),
        **_authority(True),
    }, 201


def build_final_balance_message(reconciliation):
    packed_weight = _number(reconciliation.get("actual_packed_weight_kg"))
    final_amount = _number(reconciliation.get("final_amount"))
    deposit_amount = _number(reconciliation.get("deposit_confirmed_amount")) or 0
    balance_due = _number(reconciliation.get("balance_due")) or 0
    reference = _clean(reconciliation.get("payment_reference"), 160)
    if not packed_weight or final_amount is None:
        return ""
    parts = [
        f"Your pork is packed. Final packed weight: {packed_weight:.2f}kg.",
        f"Final amount: R{final_amount:.2f}. Deposit confirmed in bank: R{deposit_amount:.2f}.",
    ]
    if balance_due > 0:
        ref_text = f" using reference {reference}" if reference else ""
        parts.append(f"Balance due before delivery/collection: R{balance_due:.2f}{ref_text}.")
    else:
        parts.append("No balance is due before delivery/collection.")
    return " ".join(parts)


def _event_params(lead_id, reservation, payload, deposits, existing_events):
    event_type = _clean(payload.get("event_type") or "packed_weight_recorded", 100)
    latest_packed = _latest_event(existing_events, "packed_weight_recorded")
    actual_weight = _number(payload.get("actual_packed_weight_kg")) or _number(latest_packed.get("actual_packed_weight_kg"))
    price_per_kg = _number(payload.get("price_per_kg")) or _number(latest_packed.get("price_per_kg"))
    final_amount = _money(actual_weight * price_per_kg) if actual_weight and price_per_kg else _number(latest_packed.get("final_amount"))
    deposit_confirmed = _confirmed_deposit_amount(deposits, reservation.get("reservation_id", ""))
    balance_due = _money(max(0, (final_amount or 0) - deposit_confirmed)) if final_amount is not None else None
    balance_confirmed = _number(payload.get("balance_confirmed_amount")) or _number(payload.get("amount"))
    if event_type == "packed_weight_recorded" and balance_confirmed is None:
        balance_confirmed = 0
    if event_type != "balance_confirmed_in_bank":
        previous_balance = _latest_event(existing_events, "balance_confirmed_in_bank")
        balance_confirmed = _number(previous_balance.get("balance_confirmed_amount")) or balance_confirmed
    base = {
        "actual_packed_weight_kg": actual_weight,
        "price_per_kg": price_per_kg,
        "final_amount": final_amount,
        "deposit_confirmed_amount": deposit_confirmed,
        "balance_due": balance_due,
        "balance_confirmed_amount": balance_confirmed,
        "payment_reference": _clean(payload.get("payment_reference") or _latest_event(existing_events, "packed_weight_recorded").get("payment_reference"), 160),
    }
    message = _clean(payload.get("message"), 2000) or build_final_balance_message(base)
    return {
        "reconciliation_event_id": _id("OSK-MEAT-RECON", f"{lead_id}|{reservation.get('reservation_id')}|{event_type}|{datetime.now(timezone.utc).isoformat()}"),
        "lead_id": lead_id,
        "reservation_id": reservation.get("reservation_id", ""),
        "order_id": _clean(payload.get("order_id") or reservation.get("order_id"), 100),
        "event_type": event_type,
        **base,
        "message": message,
        "notes_json": json.dumps({
            "notes": _clean(payload.get("notes"), 500),
            "tag_number": reservation.get("tag_number", ""),
            "pig_id": reservation.get("pig_id", ""),
            "cut_set": reservation.get("cut_set", ""),
            "product_type": reservation.get("product_type", ""),
        }, ensure_ascii=True, sort_keys=True),
        "recorded_by": _clean(payload.get("recorded_by") or "Farm App", 80),
    }


def _reconciliation_status(reservations, deposits, events):
    reservation = _latest_reservation(reservations)
    reservation_id = reservation.get("reservation_id", "")
    latest_packed = _latest_event(events, "packed_weight_recorded")
    latest_balance = _latest_event(events, "balance_confirmed_in_bank")
    deposit_amount = _confirmed_deposit_amount(deposits, reservation_id)
    actual_weight = _number(latest_packed.get("actual_packed_weight_kg"))
    price_per_kg = _number(latest_packed.get("price_per_kg"))
    final_amount = _number(latest_packed.get("final_amount"))
    if final_amount is None and actual_weight and price_per_kg:
        final_amount = _money(actual_weight * price_per_kg)
    balance_due = _number(latest_packed.get("balance_due"))
    if balance_due is None and final_amount is not None:
        balance_due = _money(max(0, final_amount - deposit_amount))
    confirmed_balance = _number(latest_balance.get("balance_confirmed_amount")) or 0
    ready = bool(actual_weight and final_amount is not None and (balance_due or 0) <= confirmed_balance)
    status = "ready_for_delivery_release" if ready else "awaiting_packed_weight"
    if actual_weight and not ready:
        status = "awaiting_balance_confirmation"
    next_gate = "record_actual_packed_weight"
    if actual_weight and not ready:
        next_gate = "confirm_final_balance_in_bank"
    if ready:
        next_gate = "delivery_release_allowed"
    return {
        "status": status,
        "next_gate": next_gate,
        "reservation_id": reservation_id,
        "order_id": reservation.get("order_id", ""),
        "actual_packed_weight_kg": actual_weight,
        "price_per_kg": price_per_kg,
        "final_amount": final_amount,
        "deposit_confirmed_amount": deposit_amount,
        "balance_due": balance_due,
        "balance_confirmed_amount": confirmed_balance,
        "balance_confirmed": ready,
        "ready_for_delivery_release": ready,
        "payment_reference": latest_balance.get("payment_reference") or latest_packed.get("payment_reference") or "",
        "customer_balance_message": build_final_balance_message({
            "actual_packed_weight_kg": actual_weight,
            "final_amount": final_amount,
            "deposit_confirmed_amount": deposit_amount,
            "balance_due": balance_due,
            "payment_reference": latest_packed.get("payment_reference") or latest_balance.get("payment_reference") or "",
        }),
    }


def _fetch_reconciliation_events(cursor, lead_id=None, reservation_id=None):
    where = []
    params = {}
    if lead_id:
        where.append("lead_id = %(lead_id)s")
        params["lead_id"] = lead_id
    if reservation_id:
        where.append("reservation_id = %(reservation_id)s")
        params["reservation_id"] = reservation_id
    cursor.execute(
        f"""
        select reconciliation_event_id, lead_id, reservation_id, order_id, event_type,
               actual_packed_weight_kg, price_per_kg, final_amount,
               deposit_confirmed_amount, balance_due, balance_confirmed_amount,
               payment_reference, message, notes_json, recorded_by, created_at
        from public.oom_sakkie_meat_reconciliation_events
        {'where ' + ' and '.join(where) if where else ''}
        order by created_at asc
        """,
        params,
    )
    return [_event_row(row) for row in cursor.fetchall()]


def _insert_reconciliation_event(cursor, event):
    cursor.execute(
        """
        insert into public.oom_sakkie_meat_reconciliation_events (
            reconciliation_event_id, lead_id, reservation_id, order_id, event_type,
            actual_packed_weight_kg, price_per_kg, final_amount,
            deposit_confirmed_amount, balance_due, balance_confirmed_amount,
            payment_reference, message, notes_json, recorded_by, created_at
        )
        values (
            %(reconciliation_event_id)s, %(lead_id)s, %(reservation_id)s, %(order_id)s, %(event_type)s,
            %(actual_packed_weight_kg)s, %(price_per_kg)s, %(final_amount)s,
            %(deposit_confirmed_amount)s, %(balance_due)s, %(balance_confirmed_amount)s,
            %(payment_reference)s, %(message)s, %(notes_json)s::jsonb, %(recorded_by)s, now()
        )
        """,
        event,
    )


def _event_row(row):
    return {
        "reconciliation_event_id": row[0],
        "lead_id": row[1],
        "reservation_id": row[2],
        "order_id": row[3] or "",
        "event_type": row[4],
        "actual_packed_weight_kg": _number(row[5]),
        "price_per_kg": _number(row[6]),
        "final_amount": _number(row[7]),
        "deposit_confirmed_amount": _number(row[8]),
        "balance_due": _number(row[9]),
        "balance_confirmed_amount": _number(row[10]),
        "payment_reference": row[11] or "",
        "message": row[12] or "",
        "notes": row[13] if isinstance(row[13], dict) else {},
        "recorded_by": row[14] or "",
        "created_at": _iso(row[15]),
    }


def _confirmed_deposit_amount(deposits, reservation_id):
    total = 0
    for deposit in deposits or []:
        if deposit.get("reservation_id") != reservation_id:
            continue
        if deposit.get("event_type") != "deposit_confirmed_in_bank":
            continue
        total += _number(deposit.get("amount")) or 0
    return _money(total)


def _reservation_by_id(reservations, reservation_id):
    for reservation in reservations or []:
        if reservation.get("reservation_id") == reservation_id and reservation.get("effective_status") != "cancelled":
            return reservation
    return {}


def _latest_reservation(reservations):
    active = [item for item in reservations or [] if item.get("effective_status") != "cancelled"]
    return active[-1] if active else {}


def _latest_event(events, event_type):
    for event in sorted(events or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if event.get("event_type") == event_type:
            return event
    return {}


def _db_url(database_url):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _unavailable(status, configured):
    return {"success": False, "configured": configured, "status": status, **_authority(False)}


def _failed(status, exc):
    return {"success": False, "configured": True, "status": status, "error_type": exc.__class__.__name__, **_authority(False)}


def _authority(writes):
    return {
        "records_meat_reconciliation": bool(writes),
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "writes_farm_data": bool(writes),
        "dispatch_enabled": False,
        "changes_runtime_now": False,
        "changes_prompt_now": False,
        "physical_controls_enabled": False,
        "customer_public_output_enabled": False,
    }


def _id(prefix, seed):
    digest = hashlib.sha256(str(seed or "").encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}-{digest}"


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _number(value):
    if value is None or value == "":
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _money(value):
    return round(float(value or 0), 2)


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")
