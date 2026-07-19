"""Read-only evidence adapters for the four bounded domain observers."""

from __future__ import annotations

from modules.beacon.workforce import beacon_workforce_scorecard
from modules.orders.order_read import list_orders
from modules.pig_weights.pig_weights_service import get_sales_availability
from modules.sales.conversation_learning import live_stock_learning_scorecard


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
    total = int(card.get("total_events") or card.get("events") or 0)
    edits = int(card.get("owner_edit_events") or card.get("edited_replies") or 0)
    recommendations = []
    if edits:
        recommendations.append({"summary": f"Review {edits} owner-edited SAM reply event(s) for recurring lead-health corrections."})
    return _evidence("sam_live_stock_learning", {"captured_events": total, "owner_edits": edits}, recommendations)


def read_ledger_cash_exceptions(_domain="finance"):
    try:
        orders = list_orders()
    except Exception as exc:
        return _failed("order_service", {"error_type": exc.__class__.__name__})
    orders = [row for row in (orders or []) if isinstance(row, dict)]
    unresolved = [row for row in orders if str(row.get("Payment_Status") or row.get("payment_status") or "").strip().lower() in {"pending", "partial", "overdue"}]
    recommendations = [{"summary": f"Review {len(unresolved)} order payment exception(s) with Ledger."}] if unresolved else []
    return _evidence(
        "order_service.payment_state",
        {"orders_inspected": len(orders), "payment_exceptions": len(unresolved)},
        recommendations,
        gaps=["dedicated_cross_order_cash_reconciliation_source_not_available"],
    )


def read_herdmaster_readiness(_domain="farm"):
    try:
        rows = get_sales_availability()
    except Exception as exc:
        return _failed("pig_sales_availability", {"error_type": exc.__class__.__name__})
    rows = [row for row in (rows or []) if isinstance(row, dict)]
    ready = [row for row in rows if str(row.get("Readiness") or row.get("readiness") or row.get("Availability") or "").lower() in {"ready", "available", "yes"}]
    recommendations = [] if ready else [{"summary": "Review herd readiness inputs; no sale-ready animals were confirmed by the current read."}]
    return _evidence("supabase_pig_sales_availability", {"animals_inspected": len(rows), "sale_ready": len(ready)}, recommendations)


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
