import hashlib
import json
import os
from datetime import datetime, timezone

from modules.oom_sakkie.sales_campaign_store import get_sales_lead_preorder_contract
from modules.sales.meat_match_engine import get_sales_lead_meat_match
from services.database_service import DATABASE_URL_ENV


ACTIVE_RESERVATION_STATUSES = {
    "half_reserved_pending_pair",
    "full_carcass_committed",
    "deposit_pending",
    "ready_for_slaughter_booking",
}


def get_meat_ops_status(lead_id, database_url=None):
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_authority(False)}, 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True), 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                reservations = _fetch_reservations(cursor, lead_id=lead_id)
                deposits = _fetch_deposits(cursor, lead_id=lead_id)
                drafts = _fetch_instruction_drafts(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("meat_ops_status_read_failed", exc), 503
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "meat_ops_append_only_status",
        "lead_id": lead_id,
        "reservations": reservations,
        "deposits": deposits,
        "instruction_drafts": drafts,
        "assembly": _assembly_status(reservations, deposits),
        **_authority(False),
    }, 200


def create_carcass_reservation_from_lead(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    contract_result, contract_status = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    if contract_status != 200:
        return contract_result, contract_status
    match_result, match_status = get_sales_lead_meat_match(lead_id, payload, database_url=database_url)
    if match_status != 200:
        return match_result, match_status
    match = match_result.get("meat_match") if isinstance(match_result.get("meat_match"), dict) else {}
    recommendation = match.get("recommendation") if isinstance(match.get("recommendation"), dict) else {}
    pig_id = _clean(payload.get("pig_id") or recommendation.get("pig_id"), 100)
    if not pig_id:
        return {"success": False, "status": "no_recommended_pig", **_authority(False)}, 409

    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True), 500

    product_type = _product_type(contract_result.get("contract") or {}, payload)
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                existing = _fetch_reservations(cursor, pig_id=pig_id)
                side, status, block = _next_carcass_slot(product_type, existing)
                if block:
                    return {"success": False, "status": block, "pig_id": pig_id, "existing_reservations": existing, **_authority(False)}, 409
                params = _reservation_params(lead_id, product_type, side, status, recommendation, match, payload)
                cursor.execute(
                    """
                    insert into public.oom_sakkie_meat_carcass_reservations (
                        reservation_id, lead_id, order_id, pig_id, tag_number,
                        product_type, carcass_side, cut_set, status,
                        estimated_packed_weight, estimated_total, currency,
                        match_snapshot_json, created_by, created_at
                    )
                    values (
                        %(reservation_id)s, %(lead_id)s, %(order_id)s, %(pig_id)s, %(tag_number)s,
                        %(product_type)s, %(carcass_side)s, %(cut_set)s, %(status)s,
                        %(estimated_packed_weight)s, %(estimated_total)s, 'ZAR',
                        %(match_snapshot_json)s::jsonb, %(created_by)s, now()
                    )
                    """,
                    params,
                )
                reservations = _fetch_reservations(cursor, pig_id=pig_id)
                deposits = _fetch_deposits(cursor, reservation_id=params["reservation_id"])
    except Exception as exc:
        return _failed("carcass_reservation_write_failed", exc), 503

    return {
        "success": True,
        "configured": True,
        "status": status,
        "mode": "butcher_carcass_reservation_append_only",
        "reservation_id": params["reservation_id"],
        "pig_id": pig_id,
        "reservation": params | {"match_snapshot": match},
        "assembly": _assembly_status(reservations, deposits),
        "next_gate": "deposit_confirmation_before_slaughter_booking_or_external_instruction",
        **_authority(True),
    }, 201


def record_meat_deposit_event(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    reservation_id = _clean(payload.get("reservation_id"), 100)
    if not reservation_id:
        return {"success": False, "status": "reservation_id_required", **_authority(False)}, 400
    event_type = _clean(payload.get("event_type") or "deposit_confirmed", 80)
    if event_type not in {"deposit_requested_draft", "deposit_confirmed", "balance_confirmed", "payment_note"}:
        return {"success": False, "status": "invalid_deposit_event_type", **_authority(False)}, 400
    amount = _number(payload.get("amount"))
    payment_reference = _clean(payload.get("payment_reference"), 160)
    if event_type == "deposit_confirmed" and (not amount or amount <= 0):
        return {"success": False, "status": "deposit_amount_required", **_authority(False)}, 400
    if event_type == "deposit_confirmed" and not payment_reference:
        return {"success": False, "status": "deposit_reference_required", **_authority(False)}, 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True), 500
    params = {
        "deposit_event_id": _id("OSK-MEAT-DEPOSIT", f"{lead_id}|{reservation_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}"),
        "lead_id": lead_id,
        "reservation_id": reservation_id,
        "order_id": _clean(payload.get("order_id"), 100),
        "event_type": event_type,
        "amount": amount,
        "payment_reference": payment_reference,
        "payment_method": _clean(payload.get("payment_method") or "EFT", 80),
        "notes": _clean(payload.get("notes"), 500),
        "recorded_by": _clean(payload.get("recorded_by") or "Farm App", 80),
    }
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_meat_deposit_events (
                        deposit_event_id, lead_id, reservation_id, order_id,
                        event_type, amount, payment_reference, payment_method,
                        notes, recorded_by, created_at
                    )
                    values (
                        %(deposit_event_id)s, %(lead_id)s, %(reservation_id)s, %(order_id)s,
                        %(event_type)s, %(amount)s, %(payment_reference)s, %(payment_method)s,
                        %(notes)s, %(recorded_by)s, now()
                    )
                    """,
                    params,
                )
                reservations = _fetch_reservations(cursor, lead_id=lead_id)
                deposits = _fetch_deposits(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("meat_deposit_event_write_failed", exc), 503
    return {
        "success": True,
        "configured": True,
        "status": event_type,
        "mode": "meat_deposit_append_only",
        "deposit_event": params,
        "assembly": _assembly_status(reservations, deposits),
        "next_gate": "instruction_drafts_available_when_full_carcass_and_deposit_confirmed",
        **_authority(True),
    }, 201


def build_meat_instruction_drafts(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False), 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True), 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                reservations = _fetch_reservations(cursor, lead_id=lead_id)
                deposits = _fetch_deposits(cursor, lead_id=lead_id)
                assembly = _assembly_status(reservations, deposits)
                if not assembly["ready_for_instruction_drafts"]:
                    return {"success": False, "status": "not_ready_for_instruction_drafts", "assembly": assembly, **_authority(False)}, 409
                reservation = assembly["committed_reservation"]
                drafts = _instruction_draft_params(lead_id, reservation, deposits, payload)
                for draft in drafts:
                    cursor.execute(
                        """
                        insert into public.oom_sakkie_meat_instruction_drafts (
                            instruction_draft_id, lead_id, reservation_id, order_id,
                            instruction_type, status, recipient_label, draft_message,
                            instruction_payload_json, created_by, created_at
                        )
                        values (
                            %(instruction_draft_id)s, %(lead_id)s, %(reservation_id)s, %(order_id)s,
                            %(instruction_type)s, 'draft', %(recipient_label)s, %(draft_message)s,
                            %(instruction_payload_json)s::jsonb, %(created_by)s, now()
                        )
                        on conflict (instruction_draft_id) do nothing
                        """,
                        draft,
                    )
                stored = _fetch_instruction_drafts(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("instruction_draft_write_failed", exc), 503
    return {
        "success": True,
        "configured": True,
        "status": "instruction_drafts_created",
        "mode": "abattoir_butcher_instruction_drafts_only",
        "instruction_drafts": stored,
        "next_gate": "owner_approves_external_send_or_manual_booking",
        **_authority(True),
    }, 201


def _next_carcass_slot(product_type, existing):
    active = [item for item in existing if item.get("status") in ACTIVE_RESERVATION_STATUSES]
    if any(item.get("carcass_side") == "full" for item in active):
        return "", "", "pig_already_full_carcass_committed"
    half_sides = {item.get("carcass_side") for item in active if item.get("carcass_side") in {"half_a", "half_b"}}
    if product_type in {"full_carcass", "custom_cut"}:
        if half_sides:
            return "", "", "pig_has_half_reservation_already"
        return "full", "full_carcass_committed", ""
    if "half_a" not in half_sides:
        return "half_a", "half_reserved_pending_pair", ""
    if "half_b" not in half_sides:
        return "half_b", "full_carcass_committed", ""
    return "", "", "pig_already_has_two_halves"


def _assembly_status(reservations, deposits):
    active = [item for item in reservations if item.get("status") in ACTIVE_RESERVATION_STATUSES]
    by_pig = {}
    for item in active:
        by_pig.setdefault(item["pig_id"], []).append(item)
    committed = {}
    for pig_id, items in by_pig.items():
        sides = {item.get("carcass_side") for item in items}
        if "full" in sides or {"half_a", "half_b"}.issubset(sides):
            committed = sorted(items, key=lambda row: row.get("created_at", ""))[-1]
            break
    deposit_confirmed = any(item.get("event_type") == "deposit_confirmed" for item in deposits)
    return {
        "active_reservation_count": len(active),
        "full_carcass_committed": bool(committed),
        "deposit_confirmed": deposit_confirmed,
        "ready_for_slaughter_booking": bool(committed and deposit_confirmed),
        "ready_for_instruction_drafts": bool(committed and deposit_confirmed),
        "committed_reservation": committed,
        "status": "ready_for_slaughter_booking" if committed and deposit_confirmed else (
            "full_carcass_committed" if committed else (
                "half_reserved_pending_pair" if active else "interest_only"
            )
        ),
    }


def _reservation_params(lead_id, product_type, side, status, recommendation, match, payload):
    pricing = recommendation.get("pricing_estimate") if isinstance(recommendation.get("pricing_estimate"), dict) else {}
    yield_estimate = pricing.get("yield_estimate") if isinstance(pricing.get("yield_estimate"), dict) else {}
    pig_id = _clean(payload.get("pig_id") or recommendation.get("pig_id"), 100)
    return {
        "reservation_id": _id("OSK-MEAT-RES", f"{lead_id}|{pig_id}|{side}|{datetime.now(timezone.utc).isoformat()}"),
        "lead_id": lead_id,
        "order_id": _clean(payload.get("order_id"), 100),
        "pig_id": pig_id,
        "tag_number": _clean(payload.get("tag_number") or recommendation.get("tag_number"), 80),
        "product_type": product_type,
        "carcass_side": side,
        "cut_set": _clean(payload.get("cut_set") or match.get("criteria", {}).get("cut_set"), 80),
        "status": status,
        "estimated_packed_weight": _clean(yield_estimate.get("display"), 160),
        "estimated_total": _number(recommendation.get("estimated_total")),
        "match_snapshot_json": json.dumps(match, default=str, ensure_ascii=True, sort_keys=True),
        "created_by": _clean(payload.get("created_by") or "Butcher", 80),
    }


def _instruction_draft_params(lead_id, reservation, deposits, payload):
    cut_set = reservation.get("cut_set") or "approved cut set"
    tag = reservation.get("tag_number") or reservation.get("pig_id")
    deposit_ref = next((item.get("payment_reference") for item in deposits if item.get("event_type") == "deposit_confirmed"), "")
    base_payload = {
        "lead_id": lead_id,
        "reservation_id": reservation.get("reservation_id", ""),
        "pig_id": reservation.get("pig_id", ""),
        "tag_number": reservation.get("tag_number", ""),
        "cut_set": cut_set,
        "deposit_reference": deposit_ref,
        "estimated_packed_weight": reservation.get("estimated_packed_weight", ""),
    }
    abattoir_message = (
        f"Draft abattoir booking request: please confirm a legal slaughter slot for pig {tag}. "
        f"Deposit reference on file: {deposit_ref or 'pending owner confirmation'}. "
        "This is a draft only until owner approval."
    )
    butcher_message = (
        f"Draft butcher cut sheet: pig {tag}, {cut_set}. "
        f"Estimated packed weight: {reservation.get('estimated_packed_weight') or 'estimate pending'}. "
        "Final pack weights must be recorded after processing."
    )
    return [
        _instruction_param(lead_id, reservation, "abattoir_booking", payload.get("abattoir_label") or "Abattoir", abattoir_message, base_payload),
        _instruction_param(lead_id, reservation, "butcher_cut_sheet", payload.get("butcher_label") or "Butcher", butcher_message, base_payload),
    ]


def _instruction_param(lead_id, reservation, instruction_type, recipient, message, payload):
    seed = f"{lead_id}|{reservation.get('reservation_id')}|{instruction_type}"
    return {
        "instruction_draft_id": _id("OSK-MEAT-INSTRUCTION", seed),
        "lead_id": lead_id,
        "reservation_id": reservation.get("reservation_id", ""),
        "order_id": reservation.get("order_id", ""),
        "instruction_type": instruction_type,
        "recipient_label": _clean(recipient, 120),
        "draft_message": _clean(message, 1200),
        "instruction_payload_json": json.dumps(payload, default=str, ensure_ascii=True, sort_keys=True),
        "created_by": "Butcher",
    }


def _product_type(contract, payload):
    if payload.get("product_type") in {"half_carcass", "full_carcass", "custom_cut"}:
        return payload["product_type"]
    summary = contract.get("lead_summary") if isinstance(contract.get("lead_summary"), dict) else {}
    text = " ".join(str(summary.get(key, "")) for key in ("product", "customer_notes")).lower()
    if "full" in text:
        return "full_carcass"
    if "custom" in text:
        return "custom_cut"
    return "half_carcass"


def _fetch_reservations(cursor, lead_id=None, pig_id=None):
    where = []
    params = {}
    if lead_id:
        where.append("lead_id = %(lead_id)s")
        params["lead_id"] = lead_id
    if pig_id:
        where.append("pig_id = %(pig_id)s")
        params["pig_id"] = pig_id
    cursor.execute(
        f"""
        select reservation_id, lead_id, order_id, pig_id, tag_number, product_type,
               carcass_side, cut_set, status, estimated_packed_weight, estimated_total,
               currency, match_snapshot_json, created_by, created_at
        from public.oom_sakkie_meat_carcass_reservations
        {'where ' + ' and '.join(where) if where else ''}
        order by created_at asc
        """,
        params,
    )
    return [_reservation_row(row) for row in cursor.fetchall()]


def _fetch_deposits(cursor, lead_id=None, reservation_id=None):
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
        select deposit_event_id, lead_id, reservation_id, order_id, event_type,
               amount, payment_reference, payment_method, notes, recorded_by, created_at
        from public.oom_sakkie_meat_deposit_events
        {'where ' + ' and '.join(where) if where else ''}
        order by created_at asc
        """,
        params,
    )
    return [_deposit_row(row) for row in cursor.fetchall()]


def _fetch_instruction_drafts(cursor, lead_id=None, reservation_id=None):
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
        select instruction_draft_id, lead_id, reservation_id, order_id, instruction_type,
               status, recipient_label, draft_message, instruction_payload_json,
               created_by, created_at
        from public.oom_sakkie_meat_instruction_drafts
        {'where ' + ' and '.join(where) if where else ''}
        order by created_at asc
        """,
        params,
    )
    return [_instruction_row(row) for row in cursor.fetchall()]


def _reservation_row(row):
    return {
        "reservation_id": row[0],
        "lead_id": row[1],
        "order_id": row[2] or "",
        "pig_id": row[3],
        "tag_number": row[4] or "",
        "product_type": row[5],
        "carcass_side": row[6],
        "cut_set": row[7] or "",
        "status": row[8],
        "estimated_packed_weight": row[9] or "",
        "estimated_total": _number(row[10]),
        "currency": row[11],
        "match_snapshot": row[12] if isinstance(row[12], dict) else {},
        "created_by": row[13] or "",
        "created_at": _iso(row[14]),
    }


def _deposit_row(row):
    return {
        "deposit_event_id": row[0],
        "lead_id": row[1],
        "reservation_id": row[2],
        "order_id": row[3] or "",
        "event_type": row[4],
        "amount": _number(row[5]),
        "payment_reference": row[6] or "",
        "payment_method": row[7] or "",
        "notes": row[8] or "",
        "recorded_by": row[9] or "",
        "created_at": _iso(row[10]),
    }


def _instruction_row(row):
    return {
        "instruction_draft_id": row[0],
        "lead_id": row[1],
        "reservation_id": row[2],
        "order_id": row[3] or "",
        "instruction_type": row[4],
        "status": row[5],
        "recipient_label": row[6] or "",
        "draft_message": row[7] or "",
        "instruction_payload": row[8] if isinstance(row[8], dict) else {},
        "created_by": row[9] or "",
        "created_at": _iso(row[10]),
    }


def _db_url(database_url):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _unavailable(status, configured):
    return {"success": False, "configured": configured, "status": status, **_authority(False)}


def _failed(status, exc):
    return {"success": False, "configured": True, "status": status, "error_type": exc.__class__.__name__, **_authority(False)}


def _authority(writes):
    return {
        "records_meat_ops": bool(writes),
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


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")
