"""Read-only current-state checks for the existing HERDMASTER weighing case.

Sales and reservations constrain a weighing decision; they never establish a
physical departure or authorize a new weighing. No domain records are changed.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime
import hashlib
import json
import math

CONTRACT = "herdmaster.weighing_reconciliation.v1"
ROW_BOUND = 10000
# Existing order_read review states and order_pricing line states, plus the
# cancelled line predicate used by the canonical allocation reader.
ORDER_STATES = {"draft", "pending_approval", "approved", "cancelled", "completed", "rejected"}
LINE_STATES = {"draft", "reserved", "confirmed", "collected", "cancelled"}


def load_reconciliation_rows(cursor, pigs, analysis_date):
    """Use the caller's bounded, read-only, repeatable-read snapshot."""
    ids = sorted({str(row["pig_id"]) for row in pigs})
    tags = sorted({_text(row.get("tag_number")) for row in pigs
                   if str(row.get("tag_number") or "").strip()})
    queries = {
        "latest_weights": ("""with latest_day as (
            select pig_id,max(weight_date) as weight_date from public.pig_weight_events
            where pig_id=any(%s) and weight_date<=%s group by pig_id)
          select e.weight_event_id,e.pig_id,e.weight_date,e.weight_kg
          from public.pig_weight_events e join latest_day d
            on d.pig_id=e.pig_id and d.weight_date=e.weight_date
          order by e.pig_id,e.weight_event_id limit 10001""", (ids, analysis_date)),
        "sales": ("""select i.sale_item_id,i.sale_id,i.pig_id,i.tag_number,i.order_line_id,
            s.sale_status,s.sale_stream,s.sale_date,s.updated_at as sale_updated_at,
            i.updated_at as item_updated_at
          from public.sales_transaction_items i
          join public.sales_transactions s on s.sale_id=i.sale_id
          where i.pig_id=any(%s) or lower(btrim(i.tag_number))=any(%s)
          order by i.sale_item_id limit 10001""", (ids, tags)),
        "orders": ("""select l.order_line_id,l.order_id,l.pig_id,l.tag_number,
            l.line_status,l.reserved_status,o.order_status,
            l.updated_at as line_updated_at,o.updated_at as order_updated_at
          from public.order_lines l join public.orders o on o.order_id=l.order_id
          where l.pig_id=any(%s) or lower(btrim(l.tag_number))=any(%s)
          order by l.order_line_id limit 10001""", (ids, tags)),
        "outlets": ("""select outlet_assignment_id,pig_id,outlet_type,source_record_id,
            active,created_at,released_at from public.pig_active_outlets
          where pig_id=any(%s) and active
          order by outlet_assignment_id limit 10001""", (ids,)),
    }
    result = {}
    for kind, (sql, params) in queries.items():
        cursor.execute(sql, params)
        names = [column.name for column in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
        if len(rows) > ROW_BOUND:
            raise RuntimeError("herdmaster_weighing_reconciliation_row_bound_exceeded")
        result[kind] = rows
    return result


def reconcile_weighing(pigs, evidence, *, analysis_date):
    """Keep exact source identities and contradictions, without inventing exits."""
    if evidence is None:
        return {"contract": CONTRACT, "state": "unavailable", "rows": [],
                "counts": {}, "digest": "", "authorizes_routine_weighing": False}
    by_id, by_tag = defaultdict(list), defaultdict(set)
    for row in pigs:
        by_id[str(row.get("pig_id") or "")].append(dict(row))
        if _text(row.get("tag_number")) not in {"", "unknown", "onbekend", "n/a"}:
            by_tag[_text(row.get("tag_number"))].add(str(row.get("pig_id") or ""))
    indexes = {}
    for kind in ("latest_weights", "sales", "orders", "outlets"):
        by_source_id, by_source_tag = defaultdict(dict), defaultdict(dict)
        for row in evidence.get(kind, ()):
            row = dict(row)
            digest = _digest(row)
            by_source_id[str(row.get("pig_id") or "")][digest] = row
            if kind in {"sales", "orders"} and _text(row.get("tag_number")):
                by_source_tag[_text(row["tag_number"])][digest] = row
        indexes[kind] = by_source_id, by_source_tag
    results = []
    for pig_id, copies in sorted(by_id.items()):
        pig = sorted(copies, key=_digest)[0]
        tag = _text(pig.get("tag_number"))
        sources = {kind: [row for _, row in sorted({**by_source_id.get(pig_id, {}),
            **by_source_tag.get(tag, {})}.items())]
            for kind, (by_source_id, by_source_tag) in indexes.items()}
        reasons = []
        if not pig_id or len({_digest(row) for row in copies}) != 1 or len(by_tag[tag]) > 1:
            reasons.append("canonical_identity_conflict")
        for kind in ("sales", "orders"):
            # Cancelled lines retain their original tag snapshot as history.
            # They cannot create a current identity task or allocation hold.
            identity_rows = [row for row in sources[kind]
                if kind != "orders" or _text(row.get("line_status")) != "cancelled"]
            if any(str(row.get("pig_id") or "") != pig_id or
                   (_text(row.get("tag_number")) not in {"", "unknown", "onbekend", tag})
                   for row in identity_rows):
                reasons.append(kind + "_identity_unproven")
        status, on_farm = _text(pig.get("status")), pig.get("on_farm")
        if status == "active" and on_farm is True:
            disposition = "current_on_farm"
        elif status in {"sold", "dead", "inactive", "slaughtered", "culled"} and on_farm is False:
            disposition = "off_farm"
        elif (status == "active" and on_farm is False) or (status in {"sold", "dead", "slaughtered", "culled"} and on_farm is True):
            disposition = "unresolved"
            reasons.append("canonical_farm_status_conflict")
        else:
            disposition = "unresolved"
            reasons.append("canonical_farm_status_unknown")
        sales = sources["sales"]
        orders = sources["orders"]
        outlets = sources["outlets"]
        live_sales = [row for row in sales if _text(row.get("sale_status")) != "cancelled"]
        live_orders = [row for row in orders
            if _text(row.get("line_status")) not in {"cancelled", "collected"}
            and _text(row.get("order_status")) not in {"cancelled", "completed", "rejected"}]
        if any(_text(row.get("sale_status")) not in {"draft", "confirmed", "completed", "cancelled"} for row in sales):
            reasons.append("sale_status_unknown")
        if any(_text(row.get("line_status")) not in LINE_STATES or
               _text(row.get("order_status")) not in ORDER_STATES for row in orders):
            reasons.append("order_status_unknown")
        if disposition == "current_on_farm" and any(_text(row.get("sale_status")) == "completed" for row in live_sales):
            reasons.append("completed_sale_but_still_on_farm")
        if len({row.get("order_id") for row in live_orders}) > 1 or len(outlets) > 1:
            reasons.append("multiple_active_allocations")
        if disposition == "off_farm" and (live_orders or outlets or any(
                _text(row.get("sale_status")) in {"draft", "confirmed"} for row in live_sales)):
            reasons.append("off_farm_with_active_allocation")
        for outlet in outlets:
            source = str(outlet.get("source_record_id") or "")
            kind = _text(outlet.get("outlet_type"))
            if not source or kind not in {"customer_sale", "reservation", "riversdale_auction", "meat", "breeding", "health_hold", "keep_growing", "abattoir"}:
                reasons.append("outlet_identity_unproven")
            elif kind == "reservation" and not any(row.get("order_line_id") == source for row in live_orders):
                reasons.append("reservation_source_conflict")
            elif kind in {"customer_sale", "abattoir"} and not any(row.get("sale_id") == source for row in live_sales):
                reasons.append("sale_outlet_source_conflict")
        latest = sources["latest_weights"]
        latest = [row for row in latest if _day(row.get("weight_date")) <= analysis_date]
        last_day = max((_day(row.get("weight_date")) for row in latest), default=None)
        latest = [row for row in latest if _day(row.get("weight_date")) == last_day]
        if latest and (any(not _positive_finite(row.get("weight_kg")) for row in latest) or
                       len({row["weight_kg"] for row in latest}) != 1):
            reasons.append("latest_weight_conflict")
        current_weight = (None if not latest or "latest_weight_conflict" in reasons else
            {"date": last_day.isoformat(), "kg": float(latest[0]["weight_kg"]),
             "event_ids": sorted(str(row["weight_event_id"]) for row in latest)})
        if reasons:
            state = "unresolved"
        elif disposition == "off_farm":
            state = "off_farm"
        elif live_orders or live_sales or outlets:
            state = "allocation_hold"
        else:
            state = disposition
        results.append({"pig_id": pig_id, "tag": pig.get("tag_number"),
            "name": pig.get("pig_name"), "state": state, "reasons": sorted(set(reasons)),
            "latest_weight": current_weight, "canonical": pig,
            "sources": sources, "source_digest": _digest({"pigs": sorted(copies, key=_digest), **sources}),
            "authorizes_routine_weighing": False})
    material = {"contract": CONTRACT, "state": "checked", "rows": results,
                "counts": dict(sorted(Counter(row["state"] for row in results).items())),
                "authorizes_routine_weighing": False}
    return {**material, "digest": _digest(material)}


def _text(value):
    return str(value or "").strip().casefold()


def _positive_finite(value):
    try:
        number = float(value)
        return math.isfinite(number) and number > 0
    except (ValueError, TypeError, OverflowError):
        return False


def _day(value):
    return value.date() if isinstance(value, datetime) else value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest().upper()
