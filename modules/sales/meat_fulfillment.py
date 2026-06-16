import hashlib
import json
import os
from datetime import datetime, timezone

from modules.oom_sakkie.sales_campaign_store import get_sales_lead_preorder_contract
from modules.sales.meat_ops import get_meat_ops_status
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
    status = _fulfillment_status(ops_result, events, lead)
    return {
        "success": True,
        "configured": True,
        "status": "ok",
        "mode": "meat_fulfillment_timeline_append_only",
        "lead_id": lead_id,
        "timeline": events,
        "fulfillment": status,
        "journey_plan": _journey_plan(status, lead),
        "meat_ops": {
            "assembly": ops_result.get("assembly") or {},
            "reservations": ops_result.get("reservations") or [],
            "deposits": ops_result.get("deposits") or [],
        },
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
        "journey_plan": _journey_plan(status, lead),
        "next_gate": status.get("next_gate", ""),
        **_authority(True),
    }, 201


def _fulfillment_status(ops, events, lead=None):
    assembly = ops.get("assembly") if isinstance(ops.get("assembly"), dict) else {}
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
    exception_open = bool(latest_exception and (
        not exception_resolved
        or exception_resolved.get("created_at", "") < latest_exception.get("created_at", "")
    ))
    next_gate = "find_second_half_buyer" if half_waiting else (
        "confirm_deposit" if full_committed and not deposit_confirmed else (
            "confirm_abattoir_slot" if deposit_confirmed and not abattoir_confirmed else (
                "confirm_butcher_slot" if abattoir_confirmed and not butcher_confirmed else (
                    "capture_delivery_address" if butcher_confirmed and not delivery_address else (
                        "schedule_delivery" if delivery_address and not delivery_scheduled else (
                            "assign_driver" if delivery_scheduled and not driver_assigned else (
                                "complete_delivery" if driver_assigned and not delivered else "complete"
                            )
                        )
                    )
                )
            )
        )
    )
    if exception_open:
        next_gate = "resolve_exception_review"
    return {
        "half_waiting_for_pair": half_waiting,
        "full_carcass_committed": full_committed,
        "deposit_confirmed": deposit_confirmed,
        "whatsapp_window_state": whatsapp_window or "unknown",
        "requires_template": requires_template,
        "abattoir_slot_confirmed": bool(abattoir_confirmed),
        "butcher_slot_confirmed": bool(butcher_confirmed),
        "delivery_address_captured": bool(delivery_address),
        "delivery_scheduled": bool(delivery_scheduled),
        "driver_assigned": bool(driver_assigned),
        "delivered": delivered,
        "exception_open": exception_open,
        "next_gate": next_gate,
        "status": "exception_review" if exception_open else (
            "delivered" if delivered else (
                "delivery_in_progress" if driver_assigned else (
                    "delivery_planning" if butcher_confirmed else (
                        "capacity_booking" if deposit_confirmed else (
                            "waiting_for_second_half" if half_waiting else assembly.get("status", "interest_only")
                        )
                    )
                )
            )
        ),
    }


def _journey_plan(status, lead=None):
    if status.get("exception_open"):
        return _journey("exception_review", "Hold customer updates until the owner resolves the exception.", status)
    if status.get("half_waiting_for_pair"):
        return _journey(
            "half_reserved_waiting_pair",
            "Tell the customer their half is reserved and the farm is pairing the other half before slaughter is booked.",
            status,
        )
    if status.get("full_carcass_committed") and not status.get("abattoir_slot_confirmed"):
        return _journey("carcass_committed", "Tell the customer the full carcass is committed and timing is being confirmed.", status)
    if status.get("abattoir_slot_confirmed") and not status.get("butcher_slot_confirmed"):
        return _journey("abattoir_confirmed", "Tell the customer slaughter timing is confirmed and butchery timing is next.", status)
    if status.get("butcher_slot_confirmed") and not status.get("delivery_scheduled"):
        return _journey("butcher_confirmed", "Ask for or confirm delivery details and explain final packed weight comes after processing.", status)
    if status.get("delivery_scheduled") and not status.get("driver_assigned"):
        return _journey("delivery_scheduled", "Tell the customer the delivery window once final balance and route are ready.", status)
    if status.get("driver_assigned") and not status.get("delivered"):
        return _journey("driver_assigned", "Driver can update when on the way or arrived; avoid excessive messages.", status)
    if status.get("delivered"):
        return _journey("delivered", "Send a thank-you and story-led follow-up later, not immediately as spam.", status)
    return _journey("intake", "Keep gathering missing fulfilment facts before making timing promises.", status)


def _journey(stage, summary, status):
    return {
        "stage": stage,
        "summary": summary,
        "customer_message_state": "template_required" if status.get("requires_template") else "service_window_reply_allowed",
        "requires_template": bool(status.get("requires_template")),
        "next_gate": status.get("next_gate", ""),
        "sends_now": False,
    }


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


def _iso(value):
    return value.isoformat() if hasattr(value, "isoformat") else (str(value) if value else "")
