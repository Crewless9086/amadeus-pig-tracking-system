"""Read-only evidence adapters for the four bounded domain observers."""

from __future__ import annotations

from modules.beacon.workforce import beacon_workforce_scorecard
from modules.orders.order_read import list_orders
from modules.pig_weights.pig_weights_service import get_sales_metrics
from modules.sales.conversation_learning import (
    list_sales_conversation_learning_events,
    live_stock_learning_scorecard,
    summarize_sales_conversation_learning,
)


def observer_readers():
    return {
        "sam_lead_health": read_sam_lead_health,
        "ledger_cash_exceptions": read_ledger_cash_exceptions,
        "herdmaster_readiness": read_herdmaster_readiness,
        "beacon_opportunities": read_beacon_opportunities,
    }


def read_sam_lead_health(_domain="sales"):
    result, status = live_stock_learning_scorecard(limit=500)
    card = result.get("scorecard") if isinstance(result, dict) and isinstance(result.get("scorecard"), dict) else {}
    if status >= 400:
        return _failed("sam_live_stock_learning", result)
    total = int(card.get("total_learning_examples") or card.get("captured_owner_replies") or 0)
    edits = int(card.get("captured_owner_replies") or 0)
    recommendations = []
    events_payload, events_status = list_sales_conversation_learning_events(limit=500)
    learning = summarize_sales_conversation_learning(events_payload.get("learning_events") or []) if events_status < 400 else {}
    misses = learning.get("sam_misses") if isinstance(learning.get("sam_misses"), dict) else {}
    repeated = sorted(misses.items(), key=lambda item: (-int(item[1] or 0), item[0]))
    if repeated:
        label, count = repeated[0]
        recommendations.append({"summary": f"Improve SAM Live Stock replies from conversation evidence: {label.replace('_', ' ')} occurred {count} time(s)."})
    accepted_rate = float(card.get("accepted_or_minor_edit_rate") or 0)
    if edits and accepted_rate < 0.5:
        recommendations.append({"summary": f"Review SAM drafting quality: {edits} captured owner replies but only {accepted_rate:.0%} were accepted or needed minor edits."})
    return _evidence(
        "sam_live_stock_learning",
        {"learning_examples": total, "captured_owner_replies": edits, "accepted_or_minor_edit_rate": accepted_rate, "sam_misses": misses},
        recommendations,
    )


def read_ledger_cash_exceptions(_domain="finance"):
    try:
        orders = list_orders()
    except Exception as exc:
        return _failed("order_service", {"error_type": exc.__class__.__name__})
    orders = [row for row in (orders or []) if isinstance(row, dict)]
    cancelled = [
        row for row in orders
        if str(row.get("Order_Status") or row.get("order_status") or "").strip().lower() in {"cancelled", "canceled"}
    ]
    cancelled_pending = [
        row for row in cancelled
        if str(row.get("Payment_Status") or row.get("payment_status") or "").strip().lower() in {"pending", "partial", "overdue"}
    ]
    unresolved = [
        row for row in orders
        if row not in cancelled
        and str(row.get("Payment_Status") or row.get("payment_status") or "").strip().lower() in {"pending", "partial", "overdue"}
    ]
    recommendations = [{"summary": f"Review {len(unresolved)} order payment exception(s) with Ledger."}] if unresolved else []
    return _evidence(
        "order_service.payment_state",
        {
            "orders_inspected": len(orders),
            "payment_exceptions": len(unresolved),
            "cancelled_payment_exceptions_excluded": len(cancelled_pending),
        },
        recommendations,
        gaps=["dedicated_cross_order_cash_reconciliation_source_not_available"],
    )


def read_herdmaster_readiness(_domain="farm"):
    try:
        metrics = get_sales_metrics()
    except Exception as exc:
        return _failed("sales_dashboard_metrics", {"error_type": exc.__class__.__name__})
    metrics = metrics if isinstance(metrics, dict) else {}
    if metrics.get("status") not in {"ok", "configured"}:
        return _failed("sales_dashboard_metrics", {"error_type": metrics.get("status") or "unavailable"})
    live_ready = int(metrics.get("live_sale_ready") or 0)
    meat_window = int(metrics.get("meat_window") or 0)
    slaughter_ready = int(metrics.get("slaughter_cull_ready") or 0)
    recommendations = [] if live_ready else [{"summary": "Review herd readiness inputs; no live-sale-ready animals were confirmed by the current read."}]
    return _evidence(
        "supabase_sales_dashboard_metrics",
        {
            "live_sale_ready": live_ready,
            "meat_window": meat_window,
            "slaughter_cull_ready": slaughter_ready,
            "breeding_purpose_change_required_before_sale_or_slaughter": True,
        },
        recommendations,
    )


def read_beacon_opportunities(_domain="marketing"):
    result = beacon_workforce_scorecard(limit=500)
    card = result.get("scorecard") if isinstance(result, dict) and isinstance(result.get("scorecard"), dict) else {}
    if not isinstance(result, dict) or not result.get("success"):
        return _failed("beacon_workforce_scorecard", result)
    backlog = int(card.get("media_review_backlog") or 0)
    recommendations = [{"summary": f"Review {backlog} Beacon media item(s) waiting for owner review."}] if backlog else []
    return _evidence("beacon_marketing_evidence", {"readiness_percent": card.get("progress_percent", 0), "review_backlog": backlog, "production_posts": card.get("production_posts_sent", 0)}, recommendations)


def _evidence(source, facts, recommendations, gaps=None):
    return {
        "facts": [facts],
        "freshness": "live",
        "source_refs": [source],
        "gaps": list(gaps or []),
        "recommendations": recommendations,
    }


def _failed(source, result):
    error_type = result.get("error_type") if isinstance(result, dict) else "read_failed"
    return {"facts": [], "freshness": "unknown", "source_refs": [], "gaps": [f"{source}:{error_type or 'read_failed'}"], "recommendations": []}
