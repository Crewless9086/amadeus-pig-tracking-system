"""Bounded, read-only truth snapshot for the SAM Meat owner-review packet."""

import os
from datetime import datetime, timezone

from modules.oom_sakkie import sales_campaign_store
from modules.sales import butcher_truth_board, meat_fulfillment, meat_ops, meat_reconciliation


DATABASE_URL_ENV = "SUPABASE_DB_URL"


def load_sam_meat_truth_snapshot(lead_id, *, database_deadline, database_url=None):
    """Load one consistent evidence cut with fixed, set-based query count."""
    lead_id = str(lead_id or "").strip()[:100]
    database_url = (
        database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")
    ).strip()
    if not lead_id or not database_url:
        raise RuntimeError("sam_meat_truth_snapshot_unavailable")

    observed_at = datetime.now(timezone.utc).isoformat()
    with database_deadline.connect(database_url) as connection:
        with connection.cursor() as cursor:
            pricing = _load_pricing(cursor)
            reservations = meat_ops._fetch_reservations(cursor, lead_id=lead_id)
            reservation_events = meat_ops._fetch_reservation_events(cursor, lead_id=lead_id)
            reservations = _decorate_reservations(reservations, reservation_events)
            deposits = meat_ops._fetch_deposits(cursor, lead_id=lead_id)
            drafts = meat_ops._fetch_instruction_drafts(cursor, lead_id=lead_id)
            drafts = meat_ops._decorate_instruction_drafts(cursor, drafts)
            lead = _load_lead(cursor, lead_id)
            fulfilment_events = meat_fulfillment._fetch_fulfillment_events(
                cursor, lead_id=lead_id
            )
            reconciliation_events = meat_reconciliation._fetch_reconciliation_events(
                cursor, lead_id=lead_id
            )
            batches = _load_batches(cursor, [row.get("pig_id") for row in reservations])

    assembly = meat_ops._assembly_status(reservations, deposits)
    ops = {
        "success": True,
        "status": "ok",
        "reservations": reservations,
        "deposits": deposits,
        "instruction_drafts": drafts,
        "assembly": assembly,
        "payment_gate": meat_ops.build_meat_payment_gate(reservations, deposits),
    }
    reconciliation = meat_reconciliation._reconciliation_status(
        reservations, deposits, reconciliation_events
    )
    fulfilment = meat_fulfillment._fulfillment_status(
        ops, fulfilment_events, lead, reconciliation
    )
    match_result = {"meat_match": {"recommendation": _reservation_candidate(reservations)}}
    butcher = butcher_truth_board.build_butcher_truth_board(
        match_result,
        ops,
        {"batches": batches},
        {"reconciliation": reconciliation},
    )
    return {
        "observed_at": observed_at,
        "pricing": pricing,
        "availability": {"assembly": assembly},
        "fulfilment": {
            "fulfillment": fulfilment,
            "timeline": fulfilment_events,
            "lead": lead,
            "reconciliation": reconciliation,
        },
        "butcher": butcher,
        "query_budget": {
            "pricing": 1,
            "availability": 5,
            "fulfilment": 3,
            "butcher": 1,
            "total": 10,
            "connections": 1,
        },
    }


def _load_pricing(cursor):
    cursor.execute(
        """
        select price_entry_id, product_type, cut_set, price_unit,
               price_amount, currency, deposit_rule, balance_rule,
               yield_basis, effective_from, active, notes, created_by, created_at
        from public.oom_sakkie_meat_price_book_entries
        order by effective_from desc, created_at desc
        limit 100
        """
    )
    return [sales_campaign_store._meat_price_book_row(row) for row in cursor.fetchall()]


def _load_lead(cursor, lead_id):
    cursor.execute(
        """
        select l.lead_id, l.campaign_id, l.draft_id, l.send_design_id,
               l.status, l.mode, l.campaign_source, l.lead_label,
               l.contact_label, l.channel, l.chatwoot_conversation_id,
               l.whatsapp_window_state, l.last_inbound_at, l.opt_in_state,
               l.interest_json, l.next_owner_action, l.linked_order_id,
               l.linked_preorder_id, l.created_by,
               l.sends_customer_message, l.calls_chatwoot, l.calls_n8n,
               l.creates_quote, l.creates_order, l.changes_stock,
               l.dispatch_enabled, l.changes_runtime_now, l.changes_prompt_now,
               l.physical_controls_enabled, l.customer_public_output_enabled,
               l.writes_farm_data, l.created_at,
               ev.event_type, ev.notes, ev.recorded_by, ev.created_at
        from public.oom_sakkie_sales_leads l
        left join lateral (
            select event_type, notes, recorded_by, created_at
            from public.oom_sakkie_sales_lead_events e
            where e.lead_id = l.lead_id
            order by created_at desc
            limit 1
        ) ev on true
        where l.lead_id = %(lead_id)s
        """,
        {"lead_id": lead_id},
    )
    row = cursor.fetchone()
    return sales_campaign_store._sales_lead_row(row) if row else {}


def _load_batches(cursor, pig_ids):
    pig_ids = sorted({str(value or "").strip() for value in pig_ids if value})
    if not pig_ids:
        return []
    cursor.execute(
        """
        select b.batch_id, b.status, array_agg(bp.pig_id order by bp.pig_id)
        from public.meat_processing_batch_pigs bp
        join public.meat_processing_batches b on b.batch_id = bp.batch_id
        where bp.pig_id = any(%s)
        group by b.batch_id, b.status
        order by b.batch_id
        """,
        (pig_ids,),
    )
    return [
        {
            "batch_id": row[0],
            "batch_code": "",
            "status": row[1] or "",
            "abattoir_name": "",
            "butcher_name": "",
            "pig_ids": list(row[2] or []),
        }
        for row in cursor.fetchall()
    ]


def _reservation_candidate(reservations):
    active = [
        row
        for row in reservations
        if row.get("effective_status") != "cancelled" and row.get("pig_id")
    ]
    if len(active) != 1:
        return {}
    row = active[0]
    return {
        "pig_id": row.get("pig_id", ""),
        "tag_number": row.get("tag_number", ""),
        "product_type": row.get("product_type", ""),
    }

def _decorate_reservations(reservations, events):
    by_reservation = {}
    for event in events:
        by_reservation.setdefault(event.get("reservation_id"), []).append(event)
    result = []
    for reservation in reservations:
        item = dict(reservation)
        item_events = by_reservation.get(item.get("reservation_id"), [])
        item["events"] = item_events
        item["latest_cancellation"] = meat_ops._latest_reservation_event(item_events, "reservation_cancelled")
        item["latest_reinstatement"] = meat_ops._latest_reservation_event(item_events, "reservation_reinstated")
        item["effective_status"] = meat_ops._reservation_effective_status(item, item_events)
        result.append(item)
    return result
