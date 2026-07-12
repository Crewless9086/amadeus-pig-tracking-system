"""Read-only, fail-closed BEACON fulfilment opportunity scanner."""

from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from math import ceil
import re

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


def _normalized_category(value):
    text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "piglet": "piglet", "piglets": "piglet",
        "weaner": "weaner", "weaners": "weaner",
        "grower": "grower", "growers": "grower",
        "finisher": "finisher", "finishers": "finisher",
        "ready_for_slaughter": "finisher", "slaughter_ready": "finisher",
    }
    return aliases.get(text, text)


def _row_demand_items(row):
    items = row.get("items") if isinstance(row.get("items"), list) else []
    if items:
        return [item for item in items if isinstance(item, dict)]
    interest = row.get("interest") if isinstance(row.get("interest"), dict) else {}
    return [{
        "quantity": _quantity(row),
        "category": row.get("category") or interest.get("category"),
        "weight_range": row.get("weight_range") or interest.get("weight_range"),
        "sex": row.get("sex") or row.get("requested_sex") or interest.get("sex") or interest.get("requested_sex"),
    }]


def _weight_bounds(value):
    text = str(value or "").strip().lower().replace("_", " ")
    if not text:
        return None, False
    numbers = [float(number) for number in re.findall(r"\d+(?:\.\d+)?", text)]
    if len(numbers) == 1:
        return (numbers[0], numbers[0]), True
    if len(numbers) != 2 or numbers[0] > numbers[1]:
        return None, True
    return (numbers[0], numbers[1]), True


def _pig_matches_weight(pig, bounds):
    if bounds is None:
        return True
    try:
        weight = float(pig.get("latest_weight_kg"))
    except (TypeError, ValueError):
        return False
    return bounds[0] <= weight <= bounds[1]


def _normalized_sex(value):
    text = str(value or "").strip().lower()
    aliases = {
        "male": "male", "males": "male", "boar": "male", "boars": "male",
        "female": "female", "females": "female", "gilt": "female", "gilts": "female",
        "sow": "female", "sows": "female",
        "any": "any", "any sex": "any", "no preference": "any", "either": "any",
    }
    return aliases.get(text, "")


def _pig_matches_sex(pig, requested_sex):
    pig_sex = _normalized_sex(pig.get("sex"))
    return bool(pig_sex) and (requested_sex == "any" or pig_sex == requested_sex)


def _deduplicated_demand(rows, lane, compatible_categories=None):
    excluded_statuses = {"closed", "not_interested", "cancelled", "fulfilled", "expired"}
    seen = set()
    units = 0
    accepted = []
    unknown_quantity = 0
    incompatible_records = 0
    invalid_weight_records = 0
    invalid_sex_records = 0
    units_by_category = {}
    requirements = []
    compatible_categories = {_normalized_category(value) for value in (compatible_categories or []) if value}
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
        demand_items = _row_demand_items(row)
        if any(not _quantity(item) for item in demand_items):
            unknown_quantity += 1
            continue
        if lane == "live_stock":
            item_categories = {_normalized_category(item.get("category")) for item in demand_items}
            if not item_categories or "" in item_categories or not item_categories.issubset(compatible_categories):
                incompatible_records += 1
                continue
            parsed_items = []
            for item in demand_items:
                bounds, supplied = _weight_bounds(item.get("weight_range"))
                if supplied and bounds is None:
                    invalid_weight_records += 1
                    parsed_items = []
                    break
                item_category = _normalized_category(item.get("category"))
                raw_sex = item.get("sex") or item.get("requested_sex")
                requested_sex = _normalized_sex(raw_sex) if str(raw_sex or "").strip() else "any"
                if not requested_sex:
                    invalid_sex_records += 1
                    parsed_items = []
                    break
                parsed_items.append({"category": item_category, "quantity": _quantity(item), "weight_bounds_kg": bounds, "sex": requested_sex})
            if not parsed_items:
                continue
            for parsed_item in parsed_items:
                item_category = parsed_item["category"]
                units_by_category[item_category] = units_by_category.get(item_category, 0) + parsed_item["quantity"]
                requirements.append(parsed_item)
        units += sum(_quantity(item) for item in demand_items)
        accepted.append(identity)
    return {"qualified_units": units, "qualified_units_by_category": units_by_category, "qualified_records": len(accepted), "unknown_quantity_records": unknown_quantity, "incompatible_records": incompatible_records, "invalid_weight_records": invalid_weight_records, "invalid_sex_records": invalid_sex_records, "requirements": requirements, "source_ids": sorted(accepted)}


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
        "freshness": {"maximum_age_hours": FRESHNESS_HOURS, "fresh": observed_at is not None and observed_at <= now <= observed_at + timedelta(hours=FRESHNESS_HOURS)},
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

    observed_at = _utc(allocation.get("generated_at") or allocation.get("generated_date"))
    source_ok = allocation.get("source") == "supabase_canonical"
    evidence_in_future = observed_at is not None and observed_at > now
    fresh = observed_at is not None and not evidence_in_future and now <= observed_at + timedelta(hours=FRESHNESS_HOURS)
    eligible = []
    for pig in allocation.get("pigs", []) if source_ok else []:
        if _live_stock_sale_eligibility(pig, allocation.get("thresholds", {})).get("eligible"):
            eligible.append(pig)

    cards = []
    categories = sorted({str(pig.get("sale_category") or pig.get("weight_band") or "unclassified") for pig in eligible})
    live_demand = _deduplicated_demand(live_intakes, "live_stock", categories)
    for category in ["live_stock"]:
        demanded_categories = set(live_demand["qualified_units_by_category"])
        pigs = [pig for pig in eligible if _normalized_category(pig.get("sale_category") or pig.get("weight_band")) in demanded_categories]
        supply_by_category = {}
        weight_mismatch_records = 0
        for demanded_category in demanded_categories:
            category_pigs = [pig for pig in pigs if _normalized_category(pig.get("sale_category") or pig.get("weight_band")) == demanded_category]
            category_requirements = [item for item in live_demand["requirements"] if item["category"] == demanded_category]
            matched_ids = set()
            for requirement in category_requirements:
                matches = [pig for pig in category_pigs if _pig_matches_weight(pig, requirement["weight_bounds_kg"]) and _pig_matches_sex(pig, requirement["sex"])]
                if not matches or (len(category_requirements) > 1 and len(matches) < requirement["quantity"]):
                    weight_mismatch_records += 1
                for pig in matches:
                    matched_ids.add(str(pig.get("pig_id")))
            supply_by_category[demanded_category] = len(matched_ids)
        capacity_by_category = {}
        for demanded_category, demanded_units in live_demand["qualified_units_by_category"].items():
            category_verified = supply_by_category.get(demanded_category, 0)
            category_reserve = 1 if category_verified else 0
            category_buffer = ceil(category_verified * 0.10) if category_verified else 0
            category_available = max(0, category_verified - category_reserve - category_buffer)
            capacity_by_category[demanded_category] = {
                "qualified_demand": demanded_units,
                "verified_available": category_verified,
                "operational_reserve": category_reserve,
                "safety_buffer": category_buffer,
                "available_after_buffers": category_available,
                "demand_cap": min(demanded_units, category_available),
            }
        verified = sum(item["verified_available"] for item in capacity_by_category.values())
        operational_reserve = sum(item["operational_reserve"] for item in capacity_by_category.values())
        safety_buffer = sum(item["safety_buffer"] for item in capacity_by_category.values())
        available_after_buffers = sum(item["available_after_buffers"] for item in capacity_by_category.values())
        blockers = []
        if not source_ok:
            blockers.append("supabase_allocation_readiness_unavailable")
        if not fresh:
            blockers.append("stale_or_missing_allocation_evidence")
        if evidence_in_future:
            blockers.append("future_dated_allocation_evidence")
        if live_intakes is None:
            blockers.append("sam_live_stock_demand_unavailable")
        if live_demand["unknown_quantity_records"]:
            blockers.append("unknown_live_stock_demand_quantity")
        if live_demand["incompatible_records"]:
            blockers.append("incompatible_live_stock_demand")
        if live_demand["invalid_weight_records"]:
            blockers.append("invalid_live_stock_weight_requirement")
        if live_demand["invalid_sex_records"]:
            blockers.append("invalid_live_stock_sex_requirement")
        if weight_mismatch_records:
            blockers.append("incompatible_live_stock_weight_requirement")
        if not live_demand["qualified_units"]:
            blockers.append("no_quantified_uncommitted_live_stock_demand")
        cap = sum(item["demand_cap"] for item in capacity_by_category.values()) if not blockers else 0
        capacity = {"verified_available": verified, "eligible_categories": categories, "demanded_categories": sorted(demanded_categories), "capacity_by_category": capacity_by_category, "existing_commitments": 0, "operational_reserve": operational_reserve, "safety_buffer": safety_buffer, "available_after_buffers": available_after_buffers, "demand_cap": cap, "formula": "sum_by_compatible_category(min(qualified_demand, max(0, verified_available - existing_commitments - operational_reserve - safety_buffer)))"}
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
