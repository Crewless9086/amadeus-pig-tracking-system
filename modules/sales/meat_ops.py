import hashlib
import json
import os
from datetime import datetime, timezone
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.sales_campaign_store import get_sales_lead_preorder_contract
from modules.sales.meat_match_engine import get_sales_lead_meat_match
from services.database_service import DATABASE_URL_ENV


ACTIVE_RESERVATION_STATUSES = {
    "half_reserved_pending_pair",
    "full_carcass_committed",
    "deposit_pending",
    "ready_for_slaughter_booking",
}

MEAT_INSTRUCTION_SEND_ENABLED_ENV = "MEAT_INSTRUCTION_SEND_ENABLED"
MEAT_INSTRUCTION_WEBHOOK_URL_ENV = "MEAT_INSTRUCTION_WEBHOOK_URL"
MEAT_INSTRUCTION_WEBHOOK_TOKEN_ENV = "MEAT_INSTRUCTION_WEBHOOK_TOKEN"


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
                reservations = _decorate_reservations(cursor, _fetch_reservations(cursor, lead_id=lead_id))
                deposits = _fetch_deposits(cursor, lead_id=lead_id)
                drafts = _decorate_instruction_drafts(cursor, _fetch_instruction_drafts(cursor, lead_id=lead_id))
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
        "payment_gate": build_meat_payment_gate(reservations, deposits),
        **_authority(False),
    }, 200


def get_meat_payment_gate(lead_id, database_url=None):
    result, status_code = get_meat_ops_status(lead_id, database_url=database_url)
    if status_code != 200:
        return result, status_code
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "meat_payment_state_gate",
        "lead_id": _clean(lead_id, 100),
        "payment_gate": result.get("payment_gate", {}),
        "assembly": result.get("assembly", {}),
        "next_gate": (result.get("payment_gate") or {}).get("next_gate", ""),
        **_authority(False),
    }, 200


def build_meat_payment_gate(reservations, deposits):
    reservations = reservations if isinstance(reservations, list) else []
    deposits = deposits if isinstance(deposits, list) else []
    active = _active_reservations(reservations)
    active_reservation_ids = {item.get("reservation_id") for item in active if item.get("reservation_id")}
    active_deposits = [
        item for item in deposits
        if item.get("reservation_id") in active_reservation_ids
    ]
    latest_pop = _latest_deposit_event(active_deposits, "pop_received_unverified")
    latest_rejection = _latest_deposit_event(active_deposits, "pop_rejected")
    latest_bank = _latest_any_deposit_event(active_deposits, {"deposit_confirmed_in_bank", "deposit_confirmed"})
    latest_balance = _latest_deposit_event(active_deposits, "balance_confirmed")
    pop_is_open = bool(latest_pop) and (
        not latest_rejection
        or latest_rejection.get("created_at", "") < latest_pop.get("created_at", "")
    )
    bank_confirmed = bool(latest_bank)
    balance_confirmed = bool(latest_balance)
    if bank_confirmed:
        state = "deposit_confirmed_in_bank"
        customer_wording = "Deposit is confirmed in the farm account. The booking can move to the next operational gate."
        next_gate = "carcass_assembly_and_instruction_drafts"
    elif pop_is_open:
        state = "pop_received_unverified"
        customer_wording = "Proof of payment was received. The booking only moves forward once the money reflects in the farm account."
        next_gate = "bank_confirmation_required"
    else:
        state = "deposit_not_received"
        customer_wording = "Deposit is still outstanding. POP can be logged, but bank-confirmed money is required before slaughter or fulfilment gates."
        next_gate = "request_or_wait_for_deposit"
    return {
        "state": state,
        "pop_received_unverified": pop_is_open,
        "deposit_confirmed_in_bank": bank_confirmed,
        "balance_confirmed": balance_confirmed,
        "latest_pop": latest_pop,
        "latest_bank_confirmation": latest_bank,
        "latest_balance_confirmation": latest_balance,
        "customer_wording": customer_wording,
        "sam_may_claim_money_received": bank_confirmed,
        "sam_may_claim_pop_received": pop_is_open,
        "unlocks_slaughter_or_delivery": bank_confirmed,
        "next_gate": next_gate,
    }


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
                existing = _decorate_reservations(cursor, existing)
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
                reservations = _decorate_reservations(cursor, _fetch_reservations(cursor, pig_id=pig_id))
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
    event_type = _clean(payload.get("event_type") or "deposit_confirmed_in_bank", 80)
    if event_type not in {
        "deposit_requested_draft",
        "pop_received_unverified",
        "pop_rejected",
        "deposit_confirmed_in_bank",
        "deposit_confirmed",
        "balance_confirmed",
        "payment_note",
    }:
        return {"success": False, "status": "invalid_deposit_event_type", **_authority(False)}, 400
    amount = _number(payload.get("amount"))
    payment_reference = _clean(payload.get("payment_reference"), 160)
    if event_type in {"deposit_confirmed", "deposit_confirmed_in_bank"} and (not amount or amount <= 0):
        return {"success": False, "status": "deposit_amount_required", **_authority(False)}, 400
    if event_type in {"deposit_confirmed", "deposit_confirmed_in_bank"} and not payment_reference:
        return {"success": False, "status": "deposit_reference_required", **_authority(False)}, 400
    if event_type == "pop_received_unverified" and not payment_reference:
        return {"success": False, "status": "pop_reference_required", **_authority(False)}, 400
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
                reservations = _decorate_reservations(cursor, _fetch_reservations(cursor, lead_id=lead_id))
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


def record_carcass_reservation_event(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    reservation_id = _clean(payload.get("reservation_id"), 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_authority(False)}, 400
    if not reservation_id:
        return {"success": False, "status": "reservation_id_required", **_authority(False)}, 400
    event_type = _clean(payload.get("event_type") or "reservation_cancelled", 80)
    if event_type not in {"reservation_cancelled", "reservation_reinstated", "reservation_note"}:
        return {"success": False, "status": "invalid_reservation_event_type", **_authority(False)}, 400
    if event_type == "reservation_cancelled" and not _clean(payload.get("reason"), 500):
        return {"success": False, "status": "reservation_cancel_reason_required", **_authority(False)}, 400
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
                reservation = _fetch_reservation(cursor, lead_id, reservation_id)
                if not reservation:
                    return {"success": False, "status": "reservation_not_found", **_authority(False)}, 404
                event = _reservation_event_params(lead_id, reservation_id, event_type, payload)
                cursor.execute(
                    """
                    insert into public.oom_sakkie_meat_reservation_events (
                        reservation_event_id, lead_id, reservation_id,
                        event_type, reason, notes_json, recorded_by, created_at
                    )
                    values (
                        %(reservation_event_id)s, %(lead_id)s, %(reservation_id)s,
                        %(event_type)s, %(reason)s, %(notes_json)s::jsonb, %(recorded_by)s, now()
                    )
                    """,
                    event,
                )
                reservations = _decorate_reservations(cursor, _fetch_reservations(cursor, lead_id=lead_id))
                deposits = _fetch_deposits(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("reservation_event_write_failed", exc), 503
    return {
        "success": True,
        "configured": True,
        "status": event_type,
        "mode": "meat_reservation_event_append_only",
        "reservation_event": event,
        "reservations": reservations,
        "assembly": _assembly_status(reservations, deposits),
        "next_gate": "reservation_reinstatement_or_new_match_if_cancelled",
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
                stored = _decorate_instruction_drafts(cursor, _fetch_instruction_drafts(cursor, lead_id=lead_id))
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


def approve_meat_instruction_draft(lead_id, instruction_draft_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    instruction_draft_id = _clean(instruction_draft_id, 120)
    approved_message = _clean(payload.get("approved_message") or payload.get("message"), 1200)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_authority(False)}, 400
    if not instruction_draft_id:
        return {"success": False, "status": "instruction_draft_id_required", **_authority(False)}, 400
    if not approved_message:
        return {"success": False, "status": "approved_message_required", **_authority(False)}, 400
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
                draft = _fetch_instruction_draft(cursor, lead_id, instruction_draft_id)
                if not draft:
                    return {"success": False, "status": "instruction_draft_not_found", **_authority(False)}, 404
                expected_message = _clean(draft.get("draft_message"), 1200)
                if approved_message != expected_message:
                    return {
                        "success": False,
                        "status": "approved_message_mismatch",
                        "expected_hash": _message_hash(expected_message),
                        "provided_hash": _message_hash(approved_message),
                        **_authority(False),
                    }, 409
                event = _instruction_event_params(
                    lead_id,
                    draft,
                    "approved_to_send",
                    approved_message,
                    payload,
                )
                _insert_instruction_event(cursor, event)
                drafts = _decorate_instruction_drafts(cursor, _fetch_instruction_drafts(cursor, lead_id=lead_id))
    except Exception as exc:
        return _failed("instruction_approval_write_failed", exc), 503
    return {
        "success": True,
        "configured": True,
        "status": "approved_to_send",
        "mode": "meat_instruction_exact_message_approval",
        "instruction_event": event,
        "instruction_drafts": drafts,
        "next_gate": "env_gated_instruction_send",
        **_authority(True),
    }, 201


def send_approved_meat_instruction(lead_id, instruction_draft_id, payload=None, database_url=None, sender=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    instruction_draft_id = _clean(instruction_draft_id, 120)
    message = _clean(payload.get("message") or payload.get("approved_message"), 1200)
    if not _env_truthy(os.getenv(MEAT_INSTRUCTION_SEND_ENABLED_ENV)):
        return {"success": False, "status": "meat_instruction_send_disabled", "sent": False, **_authority(False)}, 503
    if not message:
        return {"success": False, "status": "message_required", "sent": False, **_authority(False)}, 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False) | {"sent": False}, 503
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True) | {"sent": False}, 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                draft = _fetch_instruction_draft(cursor, lead_id, instruction_draft_id)
                if not draft:
                    return {"success": False, "status": "instruction_draft_not_found", "sent": False, **_authority(False)}, 404
                expected_message = _clean(draft.get("draft_message"), 1200)
                if message != expected_message:
                    return {
                        "success": False,
                        "status": "message_mismatch",
                        "sent": False,
                        "expected_hash": _message_hash(expected_message),
                        "provided_hash": _message_hash(message),
                        **_authority(False),
                    }, 409
                events = _fetch_instruction_events(cursor, instruction_draft_id=instruction_draft_id)
                if any(item.get("event_type") == "sent" and item.get("message_hash") == _message_hash(message) for item in events):
                    return {
                        "success": True,
                        "status": "already_sent",
                        "sent": False,
                        "skipped": True,
                        "instruction_draft_id": instruction_draft_id,
                        **_authority(False),
                    }, 200
                approval = _latest_instruction_event(events, "approved_to_send")
                if approval.get("message_hash") != _message_hash(message):
                    return {
                        "success": False,
                        "status": "instruction_send_not_approved",
                        "sent": False,
                        "message_hash": _message_hash(message),
                        **_authority(False),
                    }, 409
                attempted = _instruction_event_params(lead_id, draft, "send_attempted", message, payload)
                _insert_instruction_event(cursor, attempted)
                try:
                    send_result = (sender or _send_instruction_webhook)(draft, message, payload)
                except Exception as exc:
                    failed = _instruction_event_params(
                        lead_id,
                        draft,
                        "send_failed",
                        message,
                        payload | {"error_type": exc.__class__.__name__},
                    )
                    _insert_instruction_event(cursor, failed)
                    return {
                        "success": False,
                        "status": "instruction_send_failed",
                        "sent": False,
                        "error_type": exc.__class__.__name__,
                        "instruction_event": failed,
                        **_authority(True),
                    }, 502
                sent_event = _instruction_event_params(
                    lead_id,
                    draft,
                    "sent",
                    message,
                    payload | {"send_result": send_result},
                )
                _insert_instruction_event(cursor, sent_event)
                drafts = _decorate_instruction_drafts(cursor, _fetch_instruction_drafts(cursor, lead_id=lead_id))
    except Exception as exc:
        return _failed("instruction_send_write_failed", exc) | {"sent": False}, 503
    return {
        "success": True,
        "configured": True,
        "status": "sent",
        "sent": True,
        "mode": "owner_approved_meat_instruction_send",
        "instruction_event": sent_event,
        "send_result": send_result,
        "instruction_drafts": drafts,
        "informs_external_party": True,
        **_authority(True),
    }, 200


def record_meat_instruction_exception(lead_id, instruction_draft_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    instruction_draft_id = _clean(instruction_draft_id, 120)
    event_type = _clean(payload.get("event_type") or "exception_review_required", 80)
    if event_type not in {"exception_review_required", "exception_review_resolved"}:
        return {"success": False, "status": "invalid_exception_event_type", **_authority(False)}, 400
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
                draft = _fetch_instruction_draft(cursor, lead_id, instruction_draft_id)
                if not draft:
                    return {"success": False, "status": "instruction_draft_not_found", **_authority(False)}, 404
                event = _instruction_event_params(lead_id, draft, event_type, draft.get("draft_message", ""), payload)
                _insert_instruction_event(cursor, event)
                drafts = _decorate_instruction_drafts(cursor, _fetch_instruction_drafts(cursor, lead_id=lead_id))
    except Exception as exc:
        return _failed("instruction_exception_write_failed", exc), 503
    return {
        "success": True,
        "configured": True,
        "status": event_type,
        "mode": "meat_instruction_exception_review_append_only",
        "instruction_event": event,
        "instruction_drafts": drafts,
        "next_gate": "owner_resolves_exception_before_auto_send",
        **_authority(True),
    }, 201


def _next_carcass_slot(product_type, existing):
    active = _active_reservations(existing)
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
    active = _active_reservations(reservations)
    active_reservation_ids = {item.get("reservation_id") for item in active if item.get("reservation_id")}
    active_deposits = [
        item for item in deposits or []
        if item.get("reservation_id") in active_reservation_ids
    ]
    by_pig = {}
    for item in active:
        by_pig.setdefault(item["pig_id"], []).append(item)
    committed = {}
    for pig_id, items in by_pig.items():
        sides = {item.get("carcass_side") for item in items}
        if "full" in sides or {"half_a", "half_b"}.issubset(sides):
            committed = sorted(items, key=lambda row: row.get("created_at", ""))[-1]
            break
    latest_pop = _latest_deposit_event(active_deposits, "pop_received_unverified")
    latest_rejection = _latest_deposit_event(active_deposits, "pop_rejected")
    deposit_confirmed = any(
        item.get("event_type") in {"deposit_confirmed", "deposit_confirmed_in_bank"}
        for item in active_deposits
    )
    pop_received_unverified = bool(latest_pop) and (
        not latest_rejection
        or latest_rejection.get("created_at", "") < latest_pop.get("created_at", "")
    )
    return {
        "active_reservation_count": len(active),
        "full_carcass_committed": bool(committed),
        "deposit_confirmed": deposit_confirmed,
        "pop_received_unverified": pop_received_unverified,
        "payment_review_status": "confirmed_in_bank" if deposit_confirmed else (
            "pop_received_unverified" if pop_received_unverified else "not_received"
        ),
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


def _reservation_event_params(lead_id, reservation_id, event_type, payload):
    payload = payload if isinstance(payload, dict) else {}
    notes = payload.get("notes") if isinstance(payload.get("notes"), dict) else {
        "notes": _clean(payload.get("notes"), 800),
    }
    return {
        "reservation_event_id": _id(
            "OSK-MEAT-RES-EVENT",
            f"{lead_id}|{reservation_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}",
        ),
        "lead_id": lead_id,
        "reservation_id": reservation_id,
        "event_type": event_type,
        "reason": _clean(payload.get("reason"), 500),
        "notes_json": json.dumps(notes, default=str, ensure_ascii=True, sort_keys=True),
        "recorded_by": _clean(payload.get("recorded_by") or "Farm App", 80),
    }


def _active_reservations(reservations):
    return [
        item for item in reservations or []
        if item.get("status") in ACTIVE_RESERVATION_STATUSES
        and item.get("effective_status", item.get("status")) in ACTIVE_RESERVATION_STATUSES
    ]


def _instruction_draft_params(lead_id, reservation, deposits, payload):
    cut_set = reservation.get("cut_set") or "approved cut set"
    tag = reservation.get("tag_number") or reservation.get("pig_id")
    deposit_ref = next((
        item.get("payment_reference")
        for item in deposits
        if item.get("event_type") in {"deposit_confirmed", "deposit_confirmed_in_bank"}
    ), "")
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


def _instruction_event_params(lead_id, draft, event_type, message, payload):
    payload = payload if isinstance(payload, dict) else {}
    message = _clean(message, 1200)
    return {
        "instruction_event_id": _id("OSK-MEAT-INSTRUCTION-EVENT", f"{lead_id}|{draft.get('instruction_draft_id')}|{event_type}|{datetime.now(timezone.utc).isoformat()}"),
        "lead_id": lead_id,
        "instruction_draft_id": draft.get("instruction_draft_id", ""),
        "reservation_id": draft.get("reservation_id", ""),
        "event_type": event_type,
        "message_hash": _message_hash(message),
        "approved_message": message if event_type == "approved_to_send" else "",
        "target_channel": _clean(payload.get("target_channel") or payload.get("channel") or "webhook", 80),
        "recipient_label": _clean(payload.get("recipient_label") or draft.get("recipient_label"), 120),
        "notes_json": json.dumps({
            "instruction_type": draft.get("instruction_type", ""),
            "reason": _clean(payload.get("reason"), 500),
            "notes": _clean(payload.get("notes"), 800),
            "send_result": payload.get("send_result") if isinstance(payload.get("send_result"), dict) else {},
            "error_type": _clean(payload.get("error_type"), 120),
        }, default=str, ensure_ascii=True, sort_keys=True),
        "recorded_by": _clean(payload.get("recorded_by") or payload.get("approved_by") or "Farm App", 80),
    }


def _insert_instruction_event(cursor, event):
    cursor.execute(
        """
        insert into public.oom_sakkie_meat_instruction_events (
            instruction_event_id, lead_id, instruction_draft_id, reservation_id,
            event_type, message_hash, approved_message, target_channel,
            recipient_label, notes_json, recorded_by, created_at
        )
        values (
            %(instruction_event_id)s, %(lead_id)s, %(instruction_draft_id)s, %(reservation_id)s,
            %(event_type)s, %(message_hash)s, %(approved_message)s, %(target_channel)s,
            %(recipient_label)s, %(notes_json)s::jsonb, %(recorded_by)s, now()
        )
        """,
        event,
    )


def _decorate_instruction_drafts(cursor, drafts):
    if not drafts:
        return []
    events = _fetch_instruction_events(cursor, lead_id=drafts[0].get("lead_id", ""))
    by_draft = {}
    for event in events:
        by_draft.setdefault(event.get("instruction_draft_id"), []).append(event)
    decorated = []
    for draft in drafts:
        draft_events = by_draft.get(draft.get("instruction_draft_id"), [])
        item = dict(draft)
        item["events"] = draft_events
        item["effective_status"] = _instruction_effective_status(draft_events)
        item["latest_exception"] = _latest_instruction_event(draft_events, "exception_review_required")
        item["latest_approval"] = _latest_instruction_event(draft_events, "approved_to_send")
        item["latest_send"] = _latest_instruction_event(draft_events, "sent")
        decorated.append(item)
    return decorated


def _instruction_effective_status(events):
    if _latest_instruction_event(events, "sent"):
        return "sent"
    if _latest_instruction_event(events, "send_failed"):
        return "send_failed"
    exception = _latest_instruction_event(events, "exception_review_required")
    resolved = _latest_instruction_event(events, "exception_review_resolved")
    if exception and not resolved:
        return "exception_review_required"
    if _latest_instruction_event(events, "approved_to_send"):
        return "approved_to_send"
    return "draft"


def _latest_instruction_event(events, event_type):
    for event in sorted(events or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if event.get("event_type") == event_type:
            return event
    return {}


def _latest_deposit_event(events, event_type):
    for event in sorted(events or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if event.get("event_type") == event_type:
            return event
    return {}


def _latest_any_deposit_event(events, event_types):
    event_types = set(event_types or [])
    for event in sorted(events or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if event.get("event_type") in event_types:
            return event
    return {}


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


def _fetch_reservation(cursor, lead_id, reservation_id):
    cursor.execute(
        """
        select reservation_id, lead_id, order_id, pig_id, tag_number, product_type,
               carcass_side, cut_set, status, estimated_packed_weight, estimated_total,
               currency, match_snapshot_json, created_by, created_at
        from public.oom_sakkie_meat_carcass_reservations
        where lead_id = %(lead_id)s
          and reservation_id = %(reservation_id)s
        """,
        {"lead_id": lead_id, "reservation_id": reservation_id},
    )
    row = cursor.fetchone()
    return _reservation_row(row) if row else {}


def _fetch_reservation_events(cursor, lead_id=None, reservation_id=None):
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
        select reservation_event_id, lead_id, reservation_id, event_type,
               reason, notes_json, recorded_by, created_at
        from public.oom_sakkie_meat_reservation_events
        {'where ' + ' and '.join(where) if where else ''}
        order by created_at asc
        """,
        params,
    )
    return [_reservation_event_row(row) for row in cursor.fetchall()]


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


def _fetch_instruction_draft(cursor, lead_id, instruction_draft_id):
    cursor.execute(
        """
        select instruction_draft_id, lead_id, reservation_id, order_id, instruction_type,
               status, recipient_label, draft_message, instruction_payload_json,
               created_by, created_at
        from public.oom_sakkie_meat_instruction_drafts
        where lead_id = %(lead_id)s
          and instruction_draft_id = %(instruction_draft_id)s
        """,
        {"lead_id": lead_id, "instruction_draft_id": instruction_draft_id},
    )
    row = cursor.fetchone()
    return _instruction_row(row) if row else {}


def _fetch_instruction_events(cursor, lead_id=None, instruction_draft_id=None):
    where = []
    params = {}
    if lead_id:
        where.append("lead_id = %(lead_id)s")
        params["lead_id"] = lead_id
    if instruction_draft_id:
        where.append("instruction_draft_id = %(instruction_draft_id)s")
        params["instruction_draft_id"] = instruction_draft_id
    cursor.execute(
        f"""
        select instruction_event_id, lead_id, instruction_draft_id, reservation_id,
               event_type, message_hash, approved_message, target_channel,
               recipient_label, notes_json, recorded_by, created_at
        from public.oom_sakkie_meat_instruction_events
        {'where ' + ' and '.join(where) if where else ''}
        order by created_at asc
        """,
        params,
    )
    return [_instruction_event_row(row) for row in cursor.fetchall()]


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


def _reservation_event_row(row):
    return {
        "reservation_event_id": row[0],
        "lead_id": row[1],
        "reservation_id": row[2],
        "event_type": row[3],
        "reason": row[4] or "",
        "notes": row[5] if isinstance(row[5], dict) else {},
        "recorded_by": row[6] or "",
        "created_at": _iso(row[7]),
    }


def _decorate_reservations(cursor, reservations):
    if not reservations:
        return []
    events = _fetch_reservation_events(cursor)
    by_reservation = {}
    for event in events:
        by_reservation.setdefault(event.get("reservation_id"), []).append(event)
    decorated = []
    for reservation in reservations:
        item = dict(reservation)
        item_events = by_reservation.get(item.get("reservation_id"), [])
        item["events"] = item_events
        item["latest_cancellation"] = _latest_reservation_event(item_events, "reservation_cancelled")
        item["latest_reinstatement"] = _latest_reservation_event(item_events, "reservation_reinstated")
        item["effective_status"] = _reservation_effective_status(item, item_events)
        decorated.append(item)
    return decorated


def _reservation_effective_status(reservation, events):
    cancellation = _latest_reservation_event(events, "reservation_cancelled")
    reinstatement = _latest_reservation_event(events, "reservation_reinstated")
    if cancellation and (
        not reinstatement
        or reinstatement.get("created_at", "") < cancellation.get("created_at", "")
    ):
        return "cancelled"
    return reservation.get("status", "")


def _latest_reservation_event(events, event_type):
    for event in sorted(events or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if event.get("event_type") == event_type:
            return event
    return {}


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


def _instruction_event_row(row):
    return {
        "instruction_event_id": row[0],
        "lead_id": row[1],
        "instruction_draft_id": row[2],
        "reservation_id": row[3] or "",
        "event_type": row[4],
        "message_hash": row[5] or "",
        "approved_message": row[6] or "",
        "target_channel": row[7] or "",
        "recipient_label": row[8] or "",
        "notes": row[9] if isinstance(row[9], dict) else {},
        "recorded_by": row[10] or "",
        "created_at": _iso(row[11]),
    }


def _send_instruction_webhook(draft, message, payload):
    url = os.getenv(MEAT_INSTRUCTION_WEBHOOK_URL_ENV, "").strip()
    token = os.getenv(MEAT_INSTRUCTION_WEBHOOK_TOKEN_ENV, "").strip()
    if not url:
        raise RuntimeError("MEAT_INSTRUCTION_WEBHOOK_URL is required")
    body = json.dumps({
        "source": "amadeus_farm_app",
        "kind": "meat_instruction",
        "instruction_draft_id": draft.get("instruction_draft_id", ""),
        "lead_id": draft.get("lead_id", ""),
        "reservation_id": draft.get("reservation_id", ""),
        "instruction_type": draft.get("instruction_type", ""),
        "recipient_label": draft.get("recipient_label", ""),
        "message": message,
        "message_hash": _message_hash(message),
        "target_channel": _clean(payload.get("target_channel") or payload.get("channel") or "webhook", 80),
    }, default=str, ensure_ascii=True, sort_keys=True).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Amadeus-Meat-Instruction-Key"] = token
    req = urllib_request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {
                "status_code": getattr(response, "status", 200),
                "body": raw[:500],
            }
    except urllib_error.HTTPError as exc:
        raise RuntimeError(f"instruction_webhook_http_{exc.code}") from exc


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


def _message_hash(message):
    return hashlib.sha256(_clean(message, 2000).encode("utf-8")).hexdigest()[:16].upper()


def _env_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")
