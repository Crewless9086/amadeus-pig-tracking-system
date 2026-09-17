"""Canonical live-stock order pricing from the active SAM price list."""

from modules.orders.order_read import get_order_detail
from modules.orders import order_supabase_write
from modules.sales.sam_pricing import resolve_live_stock_price_rule


ACTIVE_LINE_STATUSES = {"Draft", "Reserved", "Confirmed", "Collected"}


def ensure_order_line_prices(order_id, *, reprice=False, price_resolver=None):
    order_id = str(order_id or "").strip()
    detail = get_order_detail(order_id)
    if not detail:
        return {
            "success": False,
            "status": "order_not_found",
            "order_id": order_id,
            "quote_ready": False,
            "updated_count": 0,
            "unresolved": [],
        }

    resolver = price_resolver or resolve_live_stock_price_rule
    updated = []
    unchanged = []
    unresolved = []
    for line in detail.get("lines") or []:
        line_status = str(line.get("line_status") or "").strip()
        if line_status not in ACTIVE_LINE_STATUSES:
            continue
        current_price = _positive_number(line.get("unit_price"))
        if current_price is not None and not reprice:
            unchanged.append(_line_result(line, current_price, "existing_order_price"))
            continue

        rule = resolver(
            line.get("sale_category"),
            line.get("weight_band"),
            line.get("sex"),
        )
        price = _positive_number(rule.get("unit_price") if isinstance(rule, dict) else None)
        if not isinstance(rule, dict) or not rule.get("found") or price is None:
            unresolved.append({
                "order_line_id": line.get("order_line_id"),
                "pig_id": line.get("pig_id"),
                "tag_number": line.get("tag_number"),
                "sale_category": line.get("sale_category"),
                "weight_band": line.get("weight_band"),
                "sex": line.get("sex"),
                "reason": (rule or {}).get("status") if isinstance(rule, dict) else "pricing_rule_not_found",
            })
            continue

        changed = order_supabase_write.update_order_line_fields(
            line.get("order_line_id"),
            {"Unit_Price": price, "Updated_At": ""},
        )
        if not changed:
            unresolved.append({
                "order_line_id": line.get("order_line_id"),
                "pig_id": line.get("pig_id"),
                "tag_number": line.get("tag_number"),
                "reason": "order_line_update_failed",
            })
            continue
        updated.append({
            **_line_result(line, price, rule.get("source") or "pricing_rule"),
            "pricing_id": rule.get("pricing_id") or "",
        })

    priced_lines = [*unchanged, *updated]
    return {
        "success": not unresolved,
        "status": "order_prices_ready" if not unresolved else "order_prices_need_attention",
        "order_id": order_id,
        "reprice": bool(reprice),
        "updated_count": len(updated),
        "unchanged_count": len(unchanged),
        "priced_count": len(priced_lines),
        "estimated_total": round(sum(float(row["unit_price"]) for row in priced_lines), 2),
        "updated": updated,
        "unresolved": unresolved,
    }


def _line_result(line, price, source):
    return {
        "order_line_id": line.get("order_line_id"),
        "pig_id": line.get("pig_id"),
        "tag_number": line.get("tag_number"),
        "sale_category": line.get("sale_category"),
        "weight_band": line.get("weight_band"),
        "sex": line.get("sex"),
        "unit_price": float(price),
        "price_source": source,
    }


def _positive_number(value):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
