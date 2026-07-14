"""Deterministic, read-only Beacon-to-SAM attribution.

The service consumes snapshots from canonical append-only stores.  It never
creates or changes leads, orders, sales, fulfilment records, or campaign spend.
"""

from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json


ATTRIBUTION_RULE_VERSION = "beacon_sam_attribution_v1"
DEFAULT_WINDOW_DAYS = 30

ATTRIBUTION_AUTHORITY = {
    "read_only": True,
    "records_evidence": False,
    "calls_meta": False,
    "calls_chatwoot": False,
    "calls_n8n": False,
    "posts_publicly": False,
    "sends_customer_message": False,
    "spends_money": False,
    "optimizes_campaign": False,
    "creates_quote": False,
    "creates_order": False,
    "changes_stock": False,
    "reserves_stock": False,
    "writes_farm_data": False,
}

QUALIFIED_STATUSES = {"interested", "asked_price", "needs_callback", "deposit_pending", "order_ready_for_approval", "closed"}
LOST_STATUSES = {"not_interested"}
ALLOWED_LOST_REASONS = {
    "price", "timing", "location", "product_fit", "no_response",
    "stock_unavailable", "fulfilment_risk", "competitor", "other",
}
SUCCESS_FULFILMENT_EVENTS = {"delivery_completed", "collected", "fulfilled", "handover_completed"}
FAILED_FULFILMENT_EVENTS = {"failed", "cancelled", "delivery_failed", "collection_failed"}


def build_beacon_sam_attribution(payload=None):
    """Build a deterministic attribution read model from canonical evidence lists."""
    payload = payload if isinstance(payload, dict) else {}
    window_days = _positive_int(payload.get("attribution_window_days"), DEFAULT_WINDOW_DAYS)
    campaigns = _active_rows(payload.get("campaign_events"), "performance_event_id")
    leads = _rows(payload.get("leads"))
    orders = _index_unique(payload.get("orders"), "order_id")
    sales = _group(payload.get("sales_transactions"), "linked_order_id")
    fulfilment = _group(payload.get("fulfilment_events"), "lead_id")
    loss_events = _group(payload.get("loss_events"), "lead_id")

    results = []
    malformed = []
    for campaign in campaigns:
        campaign_ref = _campaign_ref(campaign)
        event_id = _text(campaign.get("performance_event_id"))
        observed_at = _time(campaign.get("observed_at") or campaign.get("created_at"))
        if not event_id or not campaign_ref or observed_at is None:
            malformed.append(event_id or _fingerprint(campaign))
            continue

        candidates = _lead_candidates(campaign, leads, observed_at, window_days)
        if not candidates:
            results.append(_unresolved(campaign, campaign_ref, "unmatched", candidates))
            continue

        methods = {method for _, method in candidates}
        if methods == {"source_time_window"} and len(candidates) > 1:
            results.append(_unresolved(campaign, campaign_ref, "ambiguous", candidates))
            continue

        for lead, method in candidates:
            results.append(_attributed(campaign, campaign_ref, lead, method, orders, sales, fulfilment, loss_events))

    results.sort(key=lambda row: (row["campaign_ref"], row["performance_event_id"], row.get("lead_id", "")))
    return {
        "success": not malformed,
        "status": "ok" if not malformed else "malformed_evidence",
        "mode": "beacon_sam_attribution_read_only",
        "rule_version": ATTRIBUTION_RULE_VERSION,
        "attribution_window_days": window_days,
        "attributions": results,
        "malformed_evidence_ids": sorted(malformed),
        "summary": _summary(results),
        "authority": deepcopy(ATTRIBUTION_AUTHORITY),
    }


def _lead_candidates(campaign, leads, observed_at, window_days):
    ref = _campaign_ref(campaign)
    exact = []
    timed = []
    source = _text(campaign.get("campaign_source")).lower()
    for lead in leads:
        lead_ref = _text(lead.get("source_campaign_id") or lead.get("campaign_id"))
        if lead_ref and lead_ref == ref:
            exact.append((lead, "exact_campaign_id"))
            continue
        lead_time = _time(lead.get("created_at") or lead.get("last_inbound_at"))
        lead_source = _text(lead.get("campaign_source")).lower()
        if source and lead_source == source and lead_time is not None:
            elapsed = (lead_time - observed_at).total_seconds()
            if 0 <= elapsed <= window_days * 86400:
                timed.append((lead, "source_time_window"))
    return exact if exact else timed


def _attributed(campaign, campaign_ref, lead, method, orders, sales, fulfilment, loss_events):
    lead_id = _text(lead.get("lead_id"))
    order_id = _text(lead.get("linked_order_id"))
    order = orders.get(order_id)
    sale_rows = sales.get(order_id, []) if order else []
    completed_sales = [row for row in sale_rows if _text(row.get("sale_status")).lower() == "completed"]
    revenue = _revenue(completed_sales)
    status = _text(lead.get("status")).lower()
    lost_reason = _lost_reason(loss_events.get(lead_id, [])) if status in LOST_STATUSES else {"code": "", "status": "not_lost"}
    result = {
        "attribution_id": _fingerprint({"rule": ATTRIBUTION_RULE_VERSION, "event": campaign.get("performance_event_id"), "lead": lead_id}),
        "performance_event_id": _text(campaign.get("performance_event_id")),
        "campaign_ref": campaign_ref,
        "status": "attributed",
        "method": method,
        "lead_id": lead_id,
        "qualification": "lost" if status in LOST_STATUSES else ("qualified" if status in QUALIFIED_STATUSES else "unresolved"),
        "order_id": order_id if order else "",
        "order_status": _text(order.get("status")) if order else ("missing" if order_id else "none"),
        "revenue": revenue,
        "fulfilment": _fulfilment(fulfilment.get(lead_id, [])),
        "lost_reason": lost_reason,
    }
    return result


def _unresolved(campaign, campaign_ref, status, candidates):
    return {
        "performance_event_id": _text(campaign.get("performance_event_id")),
        "campaign_ref": campaign_ref,
        "status": status,
        "candidate_lead_ids": sorted(_text(item[0].get("lead_id")) for item in candidates),
        "qualification": "unresolved",
        "order_id": "",
        "revenue": [],
        "fulfilment": "unknown",
        "lost_reason": {"code": "", "status": "unknown"},
    }


def _active_rows(value, id_key):
    rows = _rows(value)
    by_id = {}
    for row in rows:
        row_id = _text(row.get(id_key))
        if row_id and row_id not in by_id:
            by_id[row_id] = row
    superseded = {_text(row.get("supersedes_event_id")) for row in by_id.values() if _text(row.get("supersedes_event_id"))}
    return [row for row_id, row in by_id.items() if row_id not in superseded]


def _index_unique(value, key):
    result = {}
    duplicates = set()
    for row in _rows(value):
        item_id = _text(row.get(key))
        if not item_id:
            continue
        if item_id in result:
            duplicates.add(item_id)
        else:
            result[item_id] = row
    for item_id in duplicates:
        result.pop(item_id, None)
    return result


def _group(value, key):
    result = {}
    for row in _rows(value):
        item_id = _text(row.get(key))
        if item_id:
            result.setdefault(item_id, []).append(row)
    return result


def _revenue(rows):
    totals = {}
    for row in rows:
        amount = row.get("net_total")
        try:
            value = Decimal(str(amount))
        except (InvalidOperation, TypeError):
            continue
        currency = _text(row.get("currency") or "ZAR").upper()
        totals[currency] = totals.get(currency, Decimal("0")) + value
    return [{"currency": key, "net_total": str(totals[key].quantize(Decimal("0.01")))} for key in sorted(totals)]


def _fulfilment(rows):
    ordered = sorted(rows, key=lambda row: (_time(row.get("occurred_at") or row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc), _text(row.get("fulfillment_event_id"))))
    if not ordered:
        return "unknown"
    event_type = _text(ordered[-1].get("event_type")).lower()
    if event_type in SUCCESS_FULFILMENT_EVENTS:
        return "achieved"
    if event_type in FAILED_FULFILMENT_EVENTS:
        return "failed"
    return "pending"


def _lost_reason(rows):
    valid = [row for row in rows if _text(row.get("reason_code")).lower() in ALLOWED_LOST_REASONS]
    if not valid:
        return {"code": "", "status": "unknown"}
    valid.sort(key=lambda row: (_time(row.get("occurred_at") or row.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc), _text(row.get("event_id"))))
    return {"code": _text(valid[-1].get("reason_code")).lower(), "status": "recorded"}


def _summary(rows):
    return {
        "attributed": sum(row["status"] == "attributed" for row in rows),
        "ambiguous": sum(row["status"] == "ambiguous" for row in rows),
        "unmatched": sum(row["status"] == "unmatched" for row in rows),
        "qualified": sum(row["qualification"] == "qualified" for row in rows),
        "lost": sum(row["qualification"] == "lost" for row in rows),
    }


def _campaign_ref(row):
    return _text(row.get("source_campaign_id") or row.get("campaign_id") or row.get("publish_packet_id") or row.get("manual_post_event_id"))


def _rows(value):
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _text(value):
    return str(value or "").strip()


def _positive_int(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if 0 < parsed <= 365 else default


def _time(value):
    text = _text(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _fingerprint(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "BEACON-SAM-ATTR-" + hashlib.sha256(encoded).hexdigest()[:24].upper()
