"""Read-only, fail-closed BEACON fulfilment opportunity scanner."""

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from math import ceil

from modules.oom_sakkie.sales_campaign_store import list_sales_leads
from modules.pig_weights.pig_weights_service import (
    _live_stock_sale_eligibility,
    get_pig_allocation_readiness,
)
from modules.sales.sam_live_stock_launch_control import list_sam_live_stock_open_intakes
from modules.sales.sam_meat_control_mode import sam_meat_control_policy


SCANNER_VERSION = "beacon_opportunity_scanner_v1"
FRESHNESS_HOURS = 24
AUTHORITY = {
    "posts_publicly": False,
    "sends_customer_messages": False,
    "spends_money": False,
    "creates_orders": False,
    "creates_reservations": False,
    "changes_stock": False,
    "writes_farm_lifecycle": False,
}


def _utc(value, *, end_of_day=False):
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.max if end_of_day else time.min)
    else:
        text = str(value or "").strip().replace("Z", "+00:00")
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
        if len(text) == 10:
            parsed = datetime.combine(parsed.date(), time.max if end_of_day else time.min)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _quantity(row):
    for key in ("quantity", "requested_quantity", "pig_quantity", "units"):
        try:
            value = int(row.get(key))
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    interest = row.get("interest") if isinstance(row.get("interest"), dict) else {}
    try:
        value = int(interest.get("quantity"))
        return value if value > 0 else 0
    except (TypeError, ValueError):
        return 0


def _deduplicated_demand(rows, lane):
    excluded_statuses = {"closed", "not_interested", "cancelled", "fulfilled", "expired"}
    seen = set()
    units = 0
    accepted = []
    unknown_quantity = 0
    for row in rows if isinstance(rows, list) else []:
        if str(row.get("status") or row.get("intake_status") or "").strip().lower() in excluded_statuses:
            continue
        interest = row.get("interest") if isinstance(row.get("interest"), dict) else {}
        stated_lane = str(interest.get("sam_intake_lane") or row.get("lane") or "").lower()
        if stated_lane and lane == "live_stock" and "meat" in stated_lane:
            continue
        if stated_lane and lane == "meat" and "live" in stated_lane:
            continue
        identity = str(
            row.get("conversation_id") or row.get("chatwoot_conversation_id")
            or row.get("linked_order_id") or row.get("linked_preorder_id")
            or row.get("intake_id") or row.get("lead_id") or ""
        ).strip()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        quantity = _quantity(row)
        if not quantity:
            unknown_quantity += 1
            continue
        units += quantity
        accepted.append(identity)
    return {"qualified_units": units, "qualified_records": len(accepted), "unknown_quantity_records": unknown_quantity, "source_ids": sorted(accepted)}


def _fingerprint(lane, category, source_ids):
    raw = "|".join([lane, category, *sorted(str(value) for value in source_ids)])
    return sha256(raw.encode("utf-8")).hexdigest()


def _card(*, lane, category, now, observed_at, demand, capacity, blockers, risks, source_ids):
    fingerprint = _fingerprint(lane, category, source_ids)
    expires_at = min(now + timedelta(hours=FRESHNESS_HOURS), observed_at + timedelta(hours=FRESHNESS_HOURS)) if observed_at else now
    status = "ready_for_owner_review" if capacity["demand_cap"] > 0 and not blockers else "blocked"
    return {
        "card_id": f"BEACON-{fingerprint[:16].upper()}",
        "fingerprint": fingerprint,
        "lane": lane,
        "category": category,
        "status": status,
        "title": f"{category.replace('_', ' ').title()} opportunity",
        "opportunity_reason": "Verified eligible supply and quantified uncommitted demand overlap." if status != "blocked" else "Evidence is insufficient for a safe marketing target.",
        "demand_cap": capacity["demand_cap"],
        "unit": "animals" if lane == "live_stock" else "orders",
        "timing": {"generated_at": now.isoformat(), "expires_at": expires_at.isoformat()},
        "demand_summary": demand,
        "capacity_calculation": capacity,
        "provenance": {"source_ids": sorted(source_ids), "observed_at": observed_at.isoformat() if observed_at else ""},
        "freshness": {"maximum_age_hours": FRESHNESS_HOURS, "fresh": observed_at is not None and now <= observed_at + timedelta(hours=FRESHNESS_HOURS)},
        "risks": sorted(set(risks)),
        "blockers": sorted(set(blockers)),
        "confidence": 0.98 if status != "blocked" else 0.0,
        "recommended_next_gate": "owner_reviews_opportunity_before_any_campaign_draft_or_public_action",
        "authority": dict(AUTHORITY),
    }


def build_beacon_opportunity_cards(*, allocation=None, live_intakes=None, meat_leads=None, now=None):
    """Compose canonical reads into expiring advisory cards; never write state."""
    now = _utc(now) or datetime.now(timezone.utc)
    allocation = allocation if isinstance(allocation, dict) else get_pig_allocation_readiness(today=now.date(), allow_sheet_fallback=False)
    if live_intakes is None:
        result, status = list_sam_live_stock_open_intakes(limit=100)
        live_intakes = result.get("open_intakes", []) if status == 200 and result.get("success") else None
    if meat_leads is None:
        result, status = list_sales_leads(limit=100, status_filter="launch_test")
        meat_leads = result.get("sales_leads", []) if status == 200 and result.get("success") else None

    observed_at = _utc(allocation.get("generated_at") or allocation.get("generated_date"), end_of_day=True)
    source_ok = allocation.get("source") == "supabase_canonical"
    fresh = observed_at is not None and now <= observed_at + timedelta(hours=FRESHNESS_HOURS)
    eligible = []
    for pig in allocation.get("pigs", []) if source_ok else []:
        if _live_stock_sale_eligibility(pig, allocation.get("thresholds", {})).get("eligible"):
            eligible.append(pig)

    cards = []
    live_demand = _deduplicated_demand(live_intakes, "live_stock")
    categories = sorted({str(pig.get("sale_category") or pig.get("weight_band") or "unclassified") for pig in eligible})
    for category in ["live_stock"]:
        pigs = eligible
        verified = len(pigs)
        operational_reserve = 1 if verified else 0
        safety_buffer = ceil(verified * 0.10) if verified else 0
        available_after_buffers = max(0, verified - operational_reserve - safety_buffer)
        blockers = []
        if not source_ok:
            blockers.append("supabase_allocation_readiness_unavailable")
        if not fresh:
            blockers.append("stale_or_missing_allocation_evidence")
        if live_intakes is None:
            blockers.append("sam_live_stock_demand_unavailable")
        if not live_demand["qualified_units"]:
            blockers.append("no_quantified_uncommitted_live_stock_demand")
        cap = min(live_demand["qualified_units"], available_after_buffers) if not blockers else 0
        capacity = {"verified_available": verified, "eligible_categories": categories, "existing_commitments": 0, "operational_reserve": operational_reserve, "safety_buffer": safety_buffer, "available_after_buffers": available_after_buffers, "demand_cap": cap, "formula": "min(qualified_demand, max(0, verified_available - existing_commitments - operational_reserve - safety_buffer))"}
        source_ids = [str(pig.get("pig_id")) for pig in pigs if pig.get("pig_id")] + live_demand["source_ids"]
        cards.append(_card(lane="live_stock", category=category, now=now, observed_at=observed_at, demand=live_demand, capacity=capacity, blockers=blockers, risks=["owner_review_required", "availability_can_change_before_reservation"], source_ids=source_ids))

    meat_demand = _deduplicated_demand(meat_leads, "meat")
    meat_blockers = ["butcher_loop_not_proven"]
    if meat_leads is None:
        meat_blockers.append("sam_meat_demand_unavailable")
    policy = sam_meat_control_policy()
    meat_capacity = {"verified_available": 0, "existing_commitments": 0, "operational_reserve": 0, "safety_buffer": 0, "available_after_buffers": 0, "demand_cap": 0, "formula": "forced_zero_while_sam_meat_is_interest_capture_only", "control_mode": policy["mode"]}
    cards.append(_card(lane="meat", category="meat_preorder", now=now, observed_at=observed_at, demand=meat_demand, capacity=meat_capacity, blockers=meat_blockers, risks=["butcher_capacity_unproven", "owner_review_required"], source_ids=meat_demand["source_ids"]))
    return {"success": True, "scanner_version": SCANNER_VERSION, "status": "owner_review_only", "generated_at": now.isoformat(), "cards": cards, "authority": dict(AUTHORITY), "writes_to_supabase": False}
