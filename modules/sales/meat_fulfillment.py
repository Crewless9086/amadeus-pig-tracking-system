import hashlib
import json
import os
from datetime import datetime, timezone
from urllib import error as urllib_error
from urllib import request as urllib_request

from modules.oom_sakkie.sales_campaign_store import get_sales_lead_preorder_contract, _send_chatwoot_message
from modules.sales.meat_ops import get_meat_ops_status
from modules.sales.meat_reconciliation import get_meat_reconciliation_status
from services.database_service import DATABASE_URL_ENV


FULFILLMENT_EVENT_TYPES = {
    "customer_waiting_half_pair",
    "customer_window_open",
    "customer_template_required",
    "customer_journey_update_planned",
    "customer_journey_update_sent",
    "abattoir_slot_requested",
    "abattoir_slot_confirmed",
    "butcher_slot_requested",
    "butcher_slot_confirmed",
    "delivery_required",
    "delivery_address_requested",
    "delivery_address_captured",
    "delivery_scheduled",
    "delivery_driver_assigned",
    "delivery_on_way",
    "delivery_arrived",
    "delivery_completed",
    "delivery_failed",
    "exception_review_required",
    "exception_review_resolved",
}

JOURNEY_NOTIFICATION_SEND_ENABLED_ENV = "MEAT_JOURNEY_NOTIFICATION_SEND_ENABLED"
JOURNEY_NOTIFICATION_WEBHOOK_URL_ENV = "MEAT_JOURNEY_NOTIFICATION_WEBHOOK_URL"
JOURNEY_NOTIFICATION_WEBHOOK_TOKEN_ENV = "MEAT_JOURNEY_NOTIFICATION_WEBHOOK_TOKEN"
JOURNEY_NOTIFICATION_TRANSPORT_ENV = "MEAT_JOURNEY_NOTIFICATION_TRANSPORT"

DRIVER_EVENT_TYPES = {
    "delivery_on_way",
    "delivery_arrived",
    "delivery_completed",
    "delivery_failed",
}


def get_meat_fulfillment_timeline(lead_id, database_url=None):
    lead_id = _clean(lead_id, 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_authority(False)}, 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False), 503
    ops_result, ops_status = get_meat_ops_status(lead_id, database_url=database_url)
    if ops_status != 200:
        return ops_result, ops_status
    contract_result, contract_status = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    lead = contract_result.get("lead") if contract_status == 200 and isinstance(contract_result.get("lead"), dict) else {}
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True), 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                events = _fetch_fulfillment_events(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("meat_fulfillment_read_failed", exc), 503
    reconciliation_result, reconciliation_status = get_meat_reconciliation_status(lead_id, database_url=database_url)
    reconciliation = (
        reconciliation_result.get("reconciliation")
        if reconciliation_status == 200 and isinstance(reconciliation_result.get("reconciliation"), dict)
        else {}
    )
    status = _fulfillment_status(ops_result, events, lead, reconciliation)
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "meat_fulfillment_timeline_append_only",
        "lead_id": lead_id,
        "lead": lead,
        "timeline": events,
        "fulfillment": status,
        "journey_plan": _journey_plan(status, lead, events, reconciliation),
        "reconciliation": reconciliation,
        "meat_ops": {
            "assembly": ops_result.get("assembly") or {},
            "reservations": ops_result.get("reservations") or [],
            "deposits": ops_result.get("deposits") or [],
        },
        **_authority(False),
    }, 200


def build_dad_booking_packet(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    timeline_result, status_code = get_meat_fulfillment_timeline(lead_id, database_url=database_url)
    if status_code != 200:
        return timeline_result, status_code
    lead = timeline_result.get("lead") if isinstance(timeline_result.get("lead"), dict) else {}
    ops = timeline_result.get("meat_ops") if isinstance(timeline_result.get("meat_ops"), dict) else {}
    assembly = ops.get("assembly") if isinstance(ops.get("assembly"), dict) else {}
    reservations = ops.get("reservations") if isinstance(ops.get("reservations"), list) else []
    deposits = ops.get("deposits") if isinstance(ops.get("deposits"), list) else []
    fulfillment = timeline_result.get("fulfillment") if isinstance(timeline_result.get("fulfillment"), dict) else {}
    packet = _dad_booking_packet(
        _clean(lead_id, 100),
        lead,
        assembly,
        reservations,
        deposits,
        fulfillment,
        payload,
    )
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "dad_booking_packet_draft_only",
        "lead_id": _clean(lead_id, 100),
        "dad_booking_packet": packet,
        "next_gate": "dad_books_abattoir_and_butcher_then_owner_logs_confirmed_slots",
        **_authority(False),
    }, 200


def record_meat_fulfillment_event(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    event_type = _clean(payload.get("event_type"), 100)
    if not lead_id:
        return {"success": False, "status": "lead_id_required", **_authority(False)}, 400
    if event_type not in FULFILLMENT_EVENT_TYPES:
        return {"success": False, "status": "invalid_fulfillment_event_type", **_authority(False)}, 400
    validation = _validate_event_payload(event_type, payload)
    if validation:
        return {"success": False, "status": validation, **_authority(False)}, 400
    database_url = _db_url(database_url)
    if not database_url:
        return _unavailable("not_configured", False), 503
    ops_result, ops_status = get_meat_ops_status(lead_id, database_url=database_url)
    if ops_status != 200:
        return ops_result, ops_status
    contract_result, contract_status = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    lead = contract_result.get("lead") if contract_status == 200 and isinstance(contract_result.get("lead"), dict) else {}
    params = _event_params(lead_id, payload, ops_result, lead)
    try:
        import psycopg
    except ImportError:
        return _unavailable("dependency_missing", True), 500
    try:
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                _insert_fulfillment_event(cursor, params)
                events = _fetch_fulfillment_events(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("meat_fulfillment_write_failed", exc), 503
    status = _fulfillment_status(ops_result, events, lead)
    return {
        "success": True,
        "configured": True,
        "status": event_type,
        "mode": "meat_fulfillment_event_append_only",
        "fulfillment_event": params,
        "timeline": events,
        "fulfillment": status,
        "journey_plan": _journey_plan(status, lead, events),
        "next_gate": status.get("next_gate", ""),
        **_authority(True),
    }, 201


def list_meat_driver_route(driver_label="", scheduled_date="", database_url=None):
    driver_label = _clean(driver_label, 120)
    scheduled_date = _clean(scheduled_date, 80)
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
                lead_ids = _driver_lead_ids(cursor, driver_label, scheduled_date)
                stops = []
                for lead_id in lead_ids:
                    events = _fetch_fulfillment_events(cursor, lead_id=lead_id)
                    stops.append(_driver_stop_from_events(lead_id, events))
    except Exception as exc:
        return _failed("meat_driver_route_read_failed", exc), 503
    stops = [stop for stop in stops if stop]
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "meat_driver_route_read_only",
        "driver_label": driver_label,
        "scheduled_date": scheduled_date,
        "stops": stops,
        "count": len(stops),
        **_authority(False),
    }, 200


def record_meat_driver_delivery_event(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    event_type = _clean(payload.get("event_type"), 100)
    if event_type not in DRIVER_EVENT_TYPES:
        return {"success": False, "status": "invalid_driver_event_type", **_authority(False)}, 400
    payload = {
        **payload,
        "actor_role": "driver",
        "actor_label": payload.get("actor_label") or payload.get("assigned_to") or "Driver",
    }
    return record_meat_fulfillment_event(lead_id, payload, database_url=database_url)


def build_meat_journey_notification_draft(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    timeline_result, status_code = get_meat_fulfillment_timeline(lead_id, database_url=database_url)
    if status_code != 200:
        return timeline_result, status_code
    journey = timeline_result.get("journey_plan") if isinstance(timeline_result.get("journey_plan"), dict) else {}
    fulfillment = timeline_result.get("fulfillment") if isinstance(timeline_result.get("fulfillment"), dict) else {}
    message = _journey_message(journey, fulfillment, payload)
    if not message:
        return {"success": False, "status": "journey_message_not_available", **_authority(False)}, 409
    event = _notification_event_params(
        _clean(lead_id, 100),
        journey.get("stage", ""),
        "draft_created",
        message,
        journey,
        payload,
    )
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
                _insert_notification_event(cursor, event)
                notifications = _fetch_notification_events(cursor, lead_id=_clean(lead_id, 100))
    except Exception as exc:
        return _failed("meat_journey_notification_draft_failed", exc), 503
    return {
        "success": True,
        "configured": True,
        "status": "draft_created",
        "mode": "meat_journey_notification_draft_only",
        "notification_event": event,
        "notifications": notifications,
        "next_gate": "owner_exact_message_approval_before_customer_send",
        **_authority(True),
    }, 201


def approve_meat_journey_notification(lead_id, payload=None, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    message = _clean(payload.get("message") or payload.get("approved_message"), 1600)
    if not message:
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
                notifications = _fetch_notification_events(cursor, lead_id=lead_id)
                draft = _latest_notification(notifications, "draft_created")
                if not draft:
                    return {"success": False, "status": "journey_notification_draft_required", **_authority(False)}, 409
                if draft.get("message_hash") != _message_hash(message):
                    return {
                        "success": False,
                        "status": "approved_message_mismatch",
                        "expected_hash": draft.get("message_hash", ""),
                        "provided_hash": _message_hash(message),
                        **_authority(False),
                    }, 409
                event = _notification_event_params(
                    lead_id,
                    draft.get("stage", ""),
                    "approved_to_send",
                    message,
                    {"requires_template": draft.get("requires_template")},
                    payload,
                )
                _insert_notification_event(cursor, event)
                notifications = _fetch_notification_events(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("meat_journey_notification_approval_failed", exc), 503
    return {
        "success": True,
        "configured": True,
        "status": "approved_to_send",
        "mode": "meat_journey_notification_exact_approval",
        "notification_event": event,
        "notifications": notifications,
        "next_gate": "env_gated_customer_journey_send",
        **_authority(True),
    }, 201


def send_meat_journey_notification(lead_id, payload=None, database_url=None, sender=None):
    payload = payload if isinstance(payload, dict) else {}
    lead_id = _clean(lead_id, 100)
    message = _clean(payload.get("message"), 1600)
    if not _env_truthy(os.getenv(JOURNEY_NOTIFICATION_SEND_ENABLED_ENV)):
        return {"success": False, "status": "meat_journey_notification_send_disabled", "sent": False, **_authority(False)}, 503
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
                notifications = _fetch_notification_events(cursor, lead_id=lead_id)
                approval = _latest_notification(notifications, "approved_to_send")
                if approval.get("message_hash") != _message_hash(message):
                    return {
                        "success": False,
                        "status": "journey_notification_send_not_approved",
                        "sent": False,
                        "message_hash": _message_hash(message),
                        **_authority(False),
                    }, 409
                if any(item.get("event_type") == "sent" and item.get("message_hash") == _message_hash(message) for item in notifications):
                    return {"success": True, "status": "already_sent", "sent": False, "skipped": True, **_authority(False)}, 200
                attempted = _notification_event_params(lead_id, approval.get("stage", ""), "send_attempted", message, approval, payload)
                _insert_notification_event(cursor, attempted)
                try:
                    lead = _notification_lead(lead_id, database_url)
                    send_result = (sender or _send_journey_notification)(lead_id, message, approval, payload, lead)
                except Exception as exc:
                    failed = _notification_event_params(
                        lead_id,
                        approval.get("stage", ""),
                        "send_failed",
                        message,
                        approval,
                        payload | {"error_type": exc.__class__.__name__},
                    )
                    _insert_notification_event(cursor, failed)
                    return {"success": False, "status": "journey_notification_send_failed", "sent": False, "error_type": exc.__class__.__name__, **_authority(True)}, 502
                sent = _notification_event_params(
                    lead_id,
                    approval.get("stage", ""),
                    "sent",
                    message,
                    approval,
                    payload | {"send_result": send_result},
                )
                _insert_notification_event(cursor, sent)
                notifications = _fetch_notification_events(cursor, lead_id=lead_id)
    except Exception as exc:
        return _failed("meat_journey_notification_send_failed", exc) | {"sent": False}, 503
    return {
        "success": True,
        "configured": True,
        "status": "sent",
        "sent": True,
        "mode": "meat_journey_notification_customer_send",
        "notification_event": sent,
        "notifications": notifications,
        "send_result": send_result,
        "sends_customer_message": True,
        **{key: value for key, value in _authority(True).items() if key != "sends_customer_message"},
    }, 200


def _fulfillment_status(ops, events, lead=None, reconciliation=None):
    assembly = ops.get("assembly") if isinstance(ops.get("assembly"), dict) else {}
    reconciliation = reconciliation if isinstance(reconciliation, dict) else {}
    latest = _latest_by_type(events)
    latest_exception = _latest_event(events, "exception_review_required")
    exception_resolved = _latest_event(events, "exception_review_resolved")
    full_committed = bool(assembly.get("full_carcass_committed"))
    deposit_confirmed = bool(assembly.get("deposit_confirmed"))
    half_waiting = assembly.get("status") == "half_reserved_pending_pair"
    whatsapp_window = _clean((lead or {}).get("whatsapp_window_state") or latest.get("customer_window_open", {}).get("whatsapp_window_state"), 80)
    requires_template = whatsapp_window != "open"
    if latest.get("customer_template_required"):
        requires_template = True
    delivery_address = latest.get("delivery_address_captured", {})
    abattoir_confirmed = latest.get("abattoir_slot_confirmed", {})
    butcher_confirmed = latest.get("butcher_slot_confirmed", {})
    delivery_scheduled = latest.get("delivery_scheduled", {})
    driver_assigned = latest.get("delivery_driver_assigned", {})
    delivered = bool(latest.get("delivery_completed"))
    enforce_final_balance = bool(reconciliation)
    final_balance_ready = bool(reconciliation.get("ready_for_delivery_release")) if enforce_final_balance else True
    packed_weight_recorded = bool(reconciliation.get("actual_packed_weight_kg")) if enforce_final_balance else False
    exception_open = bool(latest_exception and (
        not exception_resolved
        or exception_resolved.get("created_at", "") < latest_exception.get("created_at", "")
    ))
    next_gate = _next_fulfillment_gate(
        half_waiting=half_waiting,
        full_committed=full_committed,
        deposit_confirmed=deposit_confirmed,
        abattoir_confirmed=bool(abattoir_confirmed),
        butcher_confirmed=bool(butcher_confirmed),
        delivery_address=bool(delivery_address),
        final_balance_ready=final_balance_ready,
        delivery_scheduled=bool(delivery_scheduled),
        driver_assigned=bool(driver_assigned),
        delivered=delivered,
    )
    if exception_open:
        next_gate = "resolve_exception_review"
    status_label = _fulfillment_status_label(
        assembly,
        half_waiting,
        deposit_confirmed,
        bool(butcher_confirmed),
        enforce_final_balance,
        final_balance_ready,
        bool(driver_assigned),
        delivered,
        exception_open,
    )
    return {
        "half_waiting_for_pair": half_waiting,
        "full_carcass_committed": full_committed,
        "deposit_confirmed": deposit_confirmed,
        "whatsapp_window_state": whatsapp_window or "unknown",
        "requires_template": requires_template,
        "abattoir_slot_confirmed": bool(abattoir_confirmed),
        "butcher_slot_confirmed": bool(butcher_confirmed),
        "delivery_address_captured": bool(delivery_address),
        "packed_weight_recorded": packed_weight_recorded,
        "final_balance_ready": final_balance_ready,
        "final_balance_status": reconciliation.get("status", ""),
        "balance_due": reconciliation.get("balance_due"),
        "customer_balance_message": reconciliation.get("customer_balance_message", ""),
        "delivery_scheduled": bool(delivery_scheduled),
        "driver_assigned": bool(driver_assigned),
        "delivered": delivered,
        "exception_open": exception_open,
        "next_gate": next_gate,
        "status": status_label,
    }


def _next_fulfillment_gate(
    half_waiting=False,
    full_committed=False,
    deposit_confirmed=False,
    abattoir_confirmed=False,
    butcher_confirmed=False,
    delivery_address=False,
    final_balance_ready=True,
    delivery_scheduled=False,
    driver_assigned=False,
    delivered=False,
):
    if half_waiting:
        return "find_second_half_buyer"
    if full_committed and not deposit_confirmed:
        return "confirm_deposit"
    if deposit_confirmed and not abattoir_confirmed:
        return "confirm_abattoir_slot"
    if abattoir_confirmed and not butcher_confirmed:
        return "confirm_butcher_slot"
    if butcher_confirmed and not delivery_address:
        return "capture_delivery_address"
    if delivery_address and not final_balance_ready:
        return "confirm_final_balance"
    if delivery_address and not delivery_scheduled:
        return "schedule_delivery"
    if delivery_scheduled and not driver_assigned:
        return "assign_driver"
    if driver_assigned and not delivered:
        return "complete_delivery"
    return "complete"


def _fulfillment_status_label(
    assembly,
    half_waiting,
    deposit_confirmed,
    butcher_confirmed,
    enforce_final_balance,
    final_balance_ready,
    driver_assigned,
    delivered,
    exception_open,
):
    if exception_open:
        return "exception_review"
    if delivered:
        return "delivered"
    if driver_assigned:
        return "delivery_in_progress"
    if butcher_confirmed and enforce_final_balance and not final_balance_ready:
        return "final_balance"
    if butcher_confirmed:
        return "delivery_planning"
    if deposit_confirmed:
        return "capacity_booking"
    if half_waiting:
        return "waiting_for_second_half"
    return assembly.get("status", "interest_only")


def _journey_plan(status, lead=None, events=None, reconciliation=None):
    latest = _latest_by_type(events or [])
    reconciliation = reconciliation if isinstance(reconciliation, dict) else {}
    if status.get("exception_open"):
        return _journey("exception_review", "Hold customer updates until the owner resolves the exception.", status, latest)
    if status.get("half_waiting_for_pair"):
        return _journey(
            "half_reserved_waiting_pair",
            "Tell the customer their half is reserved and the farm is pairing the other half before slaughter is booked.",
            status,
            latest,
        )
    if status.get("full_carcass_committed") and not status.get("abattoir_slot_confirmed"):
        return _journey("carcass_committed", "Tell the customer the full carcass is committed and timing is being confirmed.", status, latest)
    if status.get("abattoir_slot_confirmed") and not status.get("butcher_slot_confirmed"):
        return _journey("abattoir_confirmed", "Tell the customer slaughter timing is confirmed and butchery timing is next.", status, latest)
    if status.get("butcher_slot_confirmed") and not status.get("delivery_scheduled"):
        if reconciliation and not status.get("final_balance_ready"):
            if status.get("packed_weight_recorded"):
                return _journey("final_balance_due", "Tell the customer the packed weight and balance due before delivery.", status, latest, reconciliation)
            return _journey("packed_weight_pending", "Tell the customer processing is underway and final packed weight comes before delivery.", status, latest, reconciliation)
        if reconciliation and status.get("final_balance_ready"):
            return _journey("final_balance_confirmed", "Tell the customer final balance is confirmed and delivery scheduling is next.", status, latest, reconciliation)
        return _journey("butcher_confirmed", "Ask for or confirm delivery details and explain final packed weight comes after processing.", status, latest)
    if status.get("delivery_scheduled") and not status.get("driver_assigned"):
        return _journey("delivery_scheduled", "Tell the customer the delivery window once final balance and route are ready.", status, latest)
    if status.get("driver_assigned") and not status.get("delivered"):
        return _journey("driver_assigned", "Driver can update when on the way or arrived; avoid excessive messages.", status, latest)
    if status.get("delivered"):
        return _journey("delivered", "Send a thank-you and story-led follow-up later, not immediately as spam.", status, latest)
    return _journey("intake", "Keep gathering missing fulfilment facts before making timing promises.", status, latest)


def _journey(stage, summary, status, latest=None, reconciliation=None):
    latest = latest if isinstance(latest, dict) else {}
    reconciliation = reconciliation if isinstance(reconciliation, dict) else {}
    slot_context = _journey_slot_context(latest)
    return {
        "stage": stage,
        "summary": summary,
        "customer_message_state": "template_required" if status.get("requires_template") else "service_window_reply_allowed",
        "requires_template": bool(status.get("requires_template")),
        "next_gate": status.get("next_gate", ""),
        "slot_context": slot_context,
        "reconciliation": reconciliation,
        "sends_now": False,
    }


def _journey_message(journey, fulfillment, payload):
    stage = _clean((payload or {}).get("stage") or journey.get("stage"), 100)
    custom_message = _clean((payload or {}).get("message"), 1600)
    if custom_message:
        return custom_message
    slot = journey.get("slot_context") if isinstance(journey.get("slot_context"), dict) else {}
    abattoir = slot.get("abattoir") if isinstance(slot.get("abattoir"), dict) else {}
    butcher = slot.get("butcher") if isinstance(slot.get("butcher"), dict) else {}
    delivery = slot.get("delivery") if isinstance(slot.get("delivery"), dict) else {}
    reconciliation = journey.get("reconciliation") if isinstance(journey.get("reconciliation"), dict) else {}
    balance_message = _clean(reconciliation.get("customer_balance_message"), 1600)
    templates = {
        "half_reserved_waiting_pair": "Thanks, your half carcass is reserved. We are pairing the other half before we book slaughter timing.",
        "carcass_committed": "Good news, the full carcass is now committed. We are confirming abattoir and butcher timing before we promise delivery.",
        "abattoir_confirmed": (
            f"Your pork is moving forward: the abattoir slot is confirmed for {_slot_when(abattoir)}. "
            "We are confirming the butcher slot next before we promise delivery timing."
        ),
        "butcher_confirmed": (
            f"The butcher slot is confirmed for {_slot_when(butcher)}. "
            "Final packed weight and balance are confirmed after processing, then we schedule delivery."
        ),
        "packed_weight_pending": (
            "Your pork is through the confirmed processing step. We are waiting for the final packed weight, "
            "then we will confirm the exact balance before delivery."
        ),
        "final_balance_due": balance_message or "Your pork is packed. We are confirming the final balance before delivery.",
        "final_balance_confirmed": "Final balance is confirmed. We are scheduling the delivery window and will keep the next update practical.",
        "delivery_scheduled": f"Your delivery is scheduled for {_slot_when(delivery)}. We will keep updates practical and avoid unnecessary messages.",
        "driver_assigned": "Your delivery is on the route. The driver will update only when useful, such as on the way or arrived.",
        "delivered": "Delivered. Thank you for supporting the farm and being part of the Amadeus pork journey.",
        "exception_review": "There is a timing issue we are checking before we give you the next firm update.",
        "intake": "Thanks, we are checking the remaining details before confirming the next step.",
    }
    return templates.get(stage) or templates.get("intake")


def _journey_slot_context(latest):
    return {
        "abattoir": _slot_event_context(latest.get("abattoir_slot_confirmed") or latest.get("abattoir_slot_requested")),
        "butcher": _slot_event_context(latest.get("butcher_slot_confirmed") or latest.get("butcher_slot_requested")),
        "delivery": _slot_event_context(latest.get("delivery_scheduled")),
    }


def _slot_event_context(event):
    event = event if isinstance(event, dict) else {}
    return {
        "date": _clean(event.get("scheduled_date"), 80),
        "window": _clean(event.get("scheduled_window"), 120),
        "location": _clean(event.get("location_label"), 160),
        "notes": event.get("notes") if isinstance(event.get("notes"), dict) else {},
    }


def _slot_when(slot):
    slot = slot if isinstance(slot, dict) else {}
    parts = [slot.get("date"), slot.get("window"), slot.get("location")]
    return _clean(" ".join(str(item or "") for item in parts).strip() or "the confirmed slot", 240)


def _dad_booking_packet(lead_id, lead, assembly, reservations, deposits, fulfillment, payload):
    interest = lead.get("interest") if isinstance(lead.get("interest"), dict) else {}
    reservation = _latest_reservation(reservations)
    deposit = _latest_deposit(deposits)
    buyer = _clean(lead.get("contact_label") or lead.get("lead_label") or interest.get("customer_name"), 160)
    product = _clean(interest.get("product") or interest.get("product_type") or reservation.get("product_type"), 120)
    cut_set = _clean(interest.get("cut_set") or reservation.get("cut_set"), 80)
    town = _clean(interest.get("delivery_town") or interest.get("location"), 120)
    delivery_mode = _clean(interest.get("delivery_or_collection"), 80)
    desired_timing = _clean(interest.get("timing") or payload.get("desired_timing"), 160)
    tag = _clean(reservation.get("tag_number") or reservation.get("pig_id"), 120)
    packed_weight = _clean(reservation.get("estimated_packed_weight"), 160)
    deposit_state = "confirmed in bank" if assembly.get("deposit_confirmed") else (
        "POP received, not bank-confirmed" if assembly.get("pop_received_unverified") else "not confirmed"
    )
    facts = {
        "lead_id": lead_id,
        "buyer": buyer,
        "product": product,
        "cut_set": cut_set,
        "town": town,
        "delivery_or_collection": delivery_mode,
        "desired_timing": desired_timing,
        "pig_or_tag": tag,
        "reservation_id": reservation.get("reservation_id", ""),
        "carcass_side": reservation.get("carcass_side", ""),
        "carcass_status": assembly.get("status", ""),
        "full_carcass_committed": bool(assembly.get("full_carcass_committed")),
        "deposit_state": deposit_state,
        "deposit_reference": deposit.get("payment_reference", ""),
        "estimated_packed_weight": packed_weight,
        "next_gate": fulfillment.get("next_gate", ""),
    }
    missing = [
        label for label, value in {
            "pig_or_tag": tag,
            "cut_set": cut_set,
            "desired_timing": desired_timing,
        }.items()
        if not value
    ]
    if not facts["full_carcass_committed"]:
        missing.append("full_carcass_commitment")
    if not assembly.get("deposit_confirmed"):
        missing.append("money_confirmed_in_bank")
    readiness = "ready_for_dad_booking" if not missing else "not_ready_for_dad_booking"
    message = _dad_booking_message(facts, missing)
    return {
        "readiness": readiness,
        "missing_before_booking": missing,
        "facts": facts,
        "dad_message": message,
        "dad_action": (
            "Dad can request/confirm abattoir and butcher slots, then Charl/Dad logs confirmed dates in Farm App."
            if readiness == "ready_for_dad_booking"
            else "Do not book yet; resolve missing gates first."
        ),
        "records_only": True,
        "sends_now": False,
        "calls_abattoir": False,
        "calls_butcher": False,
    }


def _dad_booking_message(facts, missing):
    if missing:
        return _clean(
            "Booking packet not ready yet. Missing: "
            + ", ".join(missing)
            + ". Do not book abattoir or butcher until these are resolved.",
            1600,
        )
    return _clean(
        "Please help confirm the pork booking slots. "
        f"Pig/tag: {facts.get('pig_or_tag')}. "
        f"Product: {facts.get('product')} {facts.get('cut_set')}. "
        f"Customer/town: {facts.get('buyer') or 'customer'} / {facts.get('town') or 'town pending'}. "
        f"Delivery/collection: {facts.get('delivery_or_collection') or 'pending'}. "
        f"Timing wanted: {facts.get('desired_timing') or 'next available farm run'}. "
        f"Estimated packed weight: {facts.get('estimated_packed_weight') or 'estimate pending'}. "
        f"Deposit: {facts.get('deposit_state')} {facts.get('deposit_reference') or ''}. "
        "Please confirm abattoir slaughter slot and butcher processing slot, then we will log the confirmed dates.",
        1600,
    )


def _latest_deposit(deposits):
    preferred = {"deposit_confirmed_in_bank", "deposit_confirmed", "pop_received_unverified"}
    for event in sorted(deposits or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if event.get("event_type") in preferred:
            return event
    return {}


def _driver_lead_ids(cursor, driver_label, scheduled_date):
    where = ["event_type in ('delivery_scheduled', 'delivery_driver_assigned', 'delivery_on_way', 'delivery_arrived')"]
    params = {}
    if driver_label:
        where.append("(assigned_to = %(driver_label)s or actor_label = %(driver_label)s)")
        params["driver_label"] = driver_label
    if scheduled_date:
        where.append("scheduled_date = %(scheduled_date)s")
        params["scheduled_date"] = scheduled_date
    cursor.execute(
        f"""
        select distinct lead_id
        from public.oom_sakkie_meat_fulfillment_events
        where {' and '.join(where)}
        order by lead_id asc
        limit 100
        """,
        params,
    )
    return [row[0] for row in cursor.fetchall()]


def _driver_stop_from_events(lead_id, events):
    latest = _latest_by_type(events)
    if latest.get("delivery_completed"):
        state = "delivered"
    elif latest.get("delivery_arrived"):
        state = "arrived"
    elif latest.get("delivery_on_way"):
        state = "on_way"
    elif latest.get("delivery_driver_assigned"):
        state = "assigned"
    elif latest.get("delivery_scheduled"):
        state = "scheduled"
    else:
        state = "planned"
    delivery = latest.get("delivery_scheduled") or latest.get("delivery_driver_assigned") or latest.get("delivery_address_captured") or {}
    address = (latest.get("delivery_address_captured") or delivery).get("address") or {}
    return {
        "lead_id": lead_id,
        "state": state,
        "scheduled_date": delivery.get("scheduled_date", ""),
        "scheduled_window": delivery.get("scheduled_window", ""),
        "location_label": delivery.get("location_label", ""),
        "assigned_to": (latest.get("delivery_driver_assigned") or {}).get("assigned_to", "") or delivery.get("assigned_to", ""),
        "address": address,
        "notes": delivery.get("notes", {}),
        "latest_event": events[-1] if events else {},
    }


def _notification_event_params(lead_id, stage, event_type, message, journey, payload):
    payload = payload if isinstance(payload, dict) else {}
    journey = journey if isinstance(journey, dict) else {}
    message = _clean(message, 1600)
    return {
        "notification_event_id": _id("OSK-MEAT-JOURNEY", f"{lead_id}|{stage}|{event_type}|{datetime.now(timezone.utc).isoformat()}"),
        "lead_id": lead_id,
        "fulfillment_event_id": _clean(payload.get("fulfillment_event_id"), 120),
        "stage": _clean(stage, 100),
        "event_type": event_type,
        "message_hash": _message_hash(message),
        "message": message,
        "target_channel": _clean(payload.get("target_channel") or "chatwoot_whatsapp", 80),
        "requires_template": bool(journey.get("requires_template")) or bool(payload.get("requires_template")),
        "transport_result_json": json.dumps(payload.get("send_result") if isinstance(payload.get("send_result"), dict) else {}, default=str, ensure_ascii=True, sort_keys=True),
        "notes_json": json.dumps({
            "summary": _clean(journey.get("summary"), 800),
            "customer_message_state": _clean(journey.get("customer_message_state"), 120),
            "error_type": _clean(payload.get("error_type"), 120),
            "notes": _clean(payload.get("notes"), 800),
        }, default=str, ensure_ascii=True, sort_keys=True),
        "recorded_by": _clean(payload.get("recorded_by") or payload.get("approved_by") or "Farm App", 80),
    }


def _insert_notification_event(cursor, params):
    cursor.execute(
        """
        insert into public.oom_sakkie_meat_journey_notification_events (
            notification_event_id, lead_id, fulfillment_event_id, stage,
            event_type, message_hash, message, target_channel, requires_template,
            transport_result_json, notes_json, recorded_by, created_at
        )
        values (
            %(notification_event_id)s, %(lead_id)s, %(fulfillment_event_id)s, %(stage)s,
            %(event_type)s, %(message_hash)s, %(message)s, %(target_channel)s, %(requires_template)s,
            %(transport_result_json)s::jsonb, %(notes_json)s::jsonb, %(recorded_by)s, now()
        )
        """,
        params,
    )


def _fetch_notification_events(cursor, lead_id):
    cursor.execute(
        """
        select notification_event_id, lead_id, fulfillment_event_id, stage,
               event_type, message_hash, message, target_channel, requires_template,
               transport_result_json, notes_json, recorded_by, created_at
        from public.oom_sakkie_meat_journey_notification_events
        where lead_id = %(lead_id)s
        order by created_at asc
        """,
        {"lead_id": lead_id},
    )
    return [_notification_row(row) for row in cursor.fetchall()]


def _notification_row(row):
    return {
        "notification_event_id": row[0],
        "lead_id": row[1],
        "fulfillment_event_id": row[2] or "",
        "stage": row[3] or "",
        "event_type": row[4],
        "message_hash": row[5] or "",
        "message": row[6] or "",
        "target_channel": row[7] or "",
        "requires_template": bool(row[8]),
        "transport_result": row[9] if isinstance(row[9], dict) else {},
        "notes": row[10] if isinstance(row[10], dict) else {},
        "recorded_by": row[11] or "",
        "created_at": _iso(row[12]),
    }


def _latest_notification(events, event_type):
    for event in sorted(events or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if event.get("event_type") == event_type:
            return event
    return {}


def _notification_lead(lead_id, database_url):
    result, status_code = get_sales_lead_preorder_contract(lead_id, database_url=database_url)
    if status_code != 200 or not isinstance(result, dict):
        return {}
    return result.get("lead") if isinstance(result.get("lead"), dict) else {}


def _send_journey_notification(lead_id, message, approval, payload, lead=None):
    transport = _clean(os.getenv(JOURNEY_NOTIFICATION_TRANSPORT_ENV) or "", 80).lower()
    webhook_url = os.getenv(JOURNEY_NOTIFICATION_WEBHOOK_URL_ENV, "").strip()
    if transport == "webhook" or (webhook_url and transport != "chatwoot"):
        return _send_journey_notification_webhook(lead_id, message, approval, payload)
    return _send_journey_notification_chatwoot(lead_id, message, approval, lead or {})


def _send_journey_notification_chatwoot(lead_id, message, approval, lead):
    conversation_id = _clean(
        lead.get("chatwoot_conversation_id")
        or (lead.get("interest") if isinstance(lead.get("interest"), dict) else {}).get("conversation_id"),
        100,
    )
    if not conversation_id:
        raise RuntimeError("lead_chatwoot_conversation_id_required")
    result = _send_chatwoot_message(conversation_id, message)
    return {
        **(result if isinstance(result, dict) else {}),
        "transport": "chatwoot",
        "lead_id": lead_id,
        "stage": approval.get("stage", ""),
    }


def _send_journey_notification_webhook(lead_id, message, approval, payload):
    url = os.getenv(JOURNEY_NOTIFICATION_WEBHOOK_URL_ENV, "").strip()
    token = os.getenv(JOURNEY_NOTIFICATION_WEBHOOK_TOKEN_ENV, "").strip()
    if not url:
        raise RuntimeError("MEAT_JOURNEY_NOTIFICATION_WEBHOOK_URL is required")
    body = json.dumps({
        "source": "amadeus_farm_app",
        "kind": "meat_customer_journey_notification",
        "lead_id": lead_id,
        "stage": approval.get("stage", ""),
        "message": message,
        "message_hash": _message_hash(message),
        "target_channel": approval.get("target_channel") or "chatwoot_whatsapp",
        "requires_template": bool(approval.get("requires_template")),
    }, default=str, ensure_ascii=True, sort_keys=True).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Amadeus-Meat-Journey-Key"] = token
    req = urllib_request.Request(url, data=body, method="POST", headers=headers)
    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {"status_code": getattr(response, "status", 200), "body": raw[:500]}
    except urllib_error.HTTPError as exc:
        raise RuntimeError(f"journey_notification_http_{exc.code}") from exc


def _event_params(lead_id, payload, ops, lead):
    event_type = _clean(payload.get("event_type"), 100)
    reservation = _latest_reservation(ops.get("reservations") or [])
    return {
        "fulfillment_event_id": _id("OSK-MEAT-FULFILL", f"{lead_id}|{event_type}|{datetime.now(timezone.utc).isoformat()}"),
        "lead_id": lead_id,
        "reservation_id": _clean(payload.get("reservation_id") or reservation.get("reservation_id"), 120),
        "order_id": _clean(payload.get("order_id") or reservation.get("order_id"), 120),
        "event_type": event_type,
        "actor_role": _clean(payload.get("actor_role") or _default_actor(event_type), 80),
        "actor_label": _clean(payload.get("actor_label") or payload.get("assigned_to") or "Farm App", 120),
        "customer_channel": _clean(payload.get("customer_channel") or (lead or {}).get("channel") or "chatwoot_whatsapp", 80),
        "whatsapp_window_state": _clean(payload.get("whatsapp_window_state") or (lead or {}).get("whatsapp_window_state"), 80),
        "requires_template": bool(payload.get("requires_template")) or event_type == "customer_template_required",
        "scheduled_date": _clean(payload.get("scheduled_date") or payload.get("date"), 80),
        "scheduled_window": _clean(payload.get("scheduled_window") or payload.get("window"), 120),
        "location_label": _clean(payload.get("location_label") or payload.get("town") or payload.get("area"), 160),
        "delivery_zone": _clean(payload.get("delivery_zone"), 80),
        "assigned_to": _clean(payload.get("assigned_to"), 120),
        "customer_message_state": _clean(payload.get("customer_message_state"), 120),
        "address_json": json.dumps(_address_payload(payload), default=str, ensure_ascii=True, sort_keys=True),
        "notes_json": json.dumps({
            "reason": _clean(payload.get("reason"), 600),
            "notes": _clean(payload.get("notes"), 1000),
            "journey_story_note": _clean(payload.get("journey_story_note"), 1000),
            "contact_name": _clean(payload.get("contact_name"), 160),
            "contact_phone": _clean(payload.get("contact_phone"), 80),
        }, default=str, ensure_ascii=True, sort_keys=True),
    }


def _validate_event_payload(event_type, payload):
    if event_type in {"abattoir_slot_confirmed", "butcher_slot_confirmed", "delivery_scheduled"}:
        if not _clean(payload.get("scheduled_date") or payload.get("date"), 80):
            return "scheduled_date_required"
    if event_type == "delivery_address_captured":
        address = _address_payload(payload)
        if not address.get("address_line_1") or not address.get("town"):
            return "delivery_address_required"
    if event_type == "delivery_driver_assigned" and not _clean(payload.get("assigned_to"), 120):
        return "assigned_driver_required"
    if event_type in {"exception_review_required", "delivery_failed"} and not _clean(payload.get("reason") or payload.get("notes"), 600):
        return "reason_required"
    return ""


def _fetch_fulfillment_events(cursor, lead_id=None, reservation_id=None):
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
        select fulfillment_event_id, lead_id, reservation_id, order_id, event_type,
               actor_role, actor_label, customer_channel, whatsapp_window_state,
               requires_template, scheduled_date, scheduled_window, location_label,
               delivery_zone, assigned_to, customer_message_state, address_json,
               notes_json, created_at
        from public.oom_sakkie_meat_fulfillment_events
        {'where ' + ' and '.join(where) if where else ''}
        order by created_at asc
        """,
        params,
    )
    return [_event_row(row) for row in cursor.fetchall()]


def _insert_fulfillment_event(cursor, params):
    cursor.execute(
        """
        insert into public.oom_sakkie_meat_fulfillment_events (
            fulfillment_event_id, lead_id, reservation_id, order_id, event_type,
            actor_role, actor_label, customer_channel, whatsapp_window_state,
            requires_template, scheduled_date, scheduled_window, location_label,
            delivery_zone, assigned_to, customer_message_state, address_json,
            notes_json, created_at
        )
        values (
            %(fulfillment_event_id)s, %(lead_id)s, %(reservation_id)s, %(order_id)s, %(event_type)s,
            %(actor_role)s, %(actor_label)s, %(customer_channel)s, %(whatsapp_window_state)s,
            %(requires_template)s, %(scheduled_date)s, %(scheduled_window)s, %(location_label)s,
            %(delivery_zone)s, %(assigned_to)s, %(customer_message_state)s, %(address_json)s::jsonb,
            %(notes_json)s::jsonb, now()
        )
        """,
        params,
    )


def _event_row(row):
    return {
        "fulfillment_event_id": row[0],
        "lead_id": row[1],
        "reservation_id": row[2] or "",
        "order_id": row[3] or "",
        "event_type": row[4],
        "actor_role": row[5] or "",
        "actor_label": row[6] or "",
        "customer_channel": row[7] or "",
        "whatsapp_window_state": row[8] or "",
        "requires_template": bool(row[9]),
        "scheduled_date": row[10] or "",
        "scheduled_window": row[11] or "",
        "location_label": row[12] or "",
        "delivery_zone": row[13] or "",
        "assigned_to": row[14] or "",
        "customer_message_state": row[15] or "",
        "address": row[16] if isinstance(row[16], dict) else {},
        "notes": row[17] if isinstance(row[17], dict) else {},
        "created_at": _iso(row[18]),
    }


def _latest_by_type(events):
    latest = {}
    for event in events or []:
        latest[event.get("event_type")] = event
    return latest


def _latest_event(events, event_type):
    for event in sorted(events or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if event.get("event_type") == event_type:
            return event
    return {}


def _latest_reservation(reservations):
    for item in sorted(reservations or [], key=lambda row: row.get("created_at", ""), reverse=True):
        if item.get("reservation_id"):
            return item
    return {}


def _address_payload(payload):
    return {
        "address_line_1": _clean(payload.get("address_line_1") or payload.get("address"), 240),
        "address_line_2": _clean(payload.get("address_line_2"), 240),
        "town": _clean(payload.get("town"), 120),
        "area": _clean(payload.get("area"), 120),
        "province": _clean(payload.get("province"), 120),
        "postal_code": _clean(payload.get("postal_code"), 40),
        "maps_link": _clean(payload.get("maps_link"), 500),
        "delivery_notes": _clean(payload.get("delivery_notes"), 600),
    }


def _default_actor(event_type):
    if event_type.startswith("customer_"):
        return "sam"
    if event_type.startswith("abattoir_"):
        return "abattoir"
    if event_type.startswith("butcher_"):
        return "butcher"
    if event_type.startswith("delivery_"):
        return "driver"
    return "ops"


def _authority(writes):
    return {
        "records_meat_fulfillment": bool(writes),
        "sends_customer_message": False,
        "calls_chatwoot": False,
        "calls_n8n": False,
        "informs_external_party": False,
        "creates_quote": False,
        "creates_order": False,
        "changes_stock": False,
        "writes_farm_data": bool(writes),
        "dispatch_enabled": False,
        "customer_public_output_enabled": False,
    }


def _db_url(database_url):
    return (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()


def _unavailable(status, configured):
    return {"success": False, "configured": configured, "status": status, **_authority(False)}


def _failed(status, exc):
    return {"success": False, "configured": True, "status": status, "error_type": exc.__class__.__name__, **_authority(False)}


def _id(prefix, seed):
    digest = hashlib.sha256(str(seed or "").encode("utf-8")).hexdigest()[:16].upper()
    return f"{prefix}-{digest}"


def _clean(value, limit):
    return " ".join(str(value or "").split())[:limit]


def _message_hash(message):
    return hashlib.sha256(_clean(message, 2000).encode("utf-8")).hexdigest()[:16].upper()


def _env_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")
