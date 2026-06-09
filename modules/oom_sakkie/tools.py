from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

from modules.oom_sakkie.agent_runtime import (
    build_agent_crew_brief,
    build_sentinel_dry_run_review,
    get_agent_activation_plan,
    get_agent_activation_preflight,
    get_agent_authority_matrix,
    get_agent_authority_unlock_readiness,
    get_agent_command_center,
    get_agent_dispatch_decision_rail_blueprint,
    get_agent_operating_contracts,
    get_agent_runtime_review_packet,
    get_agent_runtime_readiness,
    get_agent_runtime_status,
    get_jarvis_product_progress,
    recommend_agent_for_text,
)
from modules.oom_sakkie.agent_dry_run_result_store import list_agent_dry_run_results
from modules.oom_sakkie.agent_dry_run_store import list_agent_dry_run_requests
from modules.oom_sakkie.build_request_store import list_build_requests
from modules.oom_sakkie.deploy_decision_store import list_deploy_decisions
from modules.oom_sakkie.dispatch_decision_store import list_dispatch_requests
from modules.oom_sakkie.patch_proposal_store import list_patch_proposals
from modules.reports.report_service import get_farm_attention_summary
from modules.pig_weights.pig_weights_controller import (
    get_dashboard_data,
    get_sales_dashboard_data,
    get_pig_allocation_readiness_data,
    get_meat_planning_data,
)
from modules.telemetry.power_service import get_current_power_state
from modules.telemetry.power_service import get_recent_power_profile
from modules.telemetry.weather_service import (
    get_current_weather_state,
    get_weather_forecast,
    get_weather_today_summary,
)
from modules.telemetry.irrigation_service import get_irrigation_status


class RiskLevel(IntEnum):
    READ_ONLY = 0
    DRAFT_ONLY = 1
    LOW_RISK_WRITE = 2
    OPERATIONAL_WRITE = 3
    CUSTOMER_OR_PUBLIC = 4
    PHYSICAL_OR_HIGH_RISK = 5


@dataclass(frozen=True)
class OomSakkieTool:
    name: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: RiskLevel
    requires_confirmation: bool
    handler: Callable[[dict[str, Any]], dict[str, Any]]
    description: str = ""


def _empty_object_schema():
    return {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def _tool_output_schema():
    return {
        "type": "object",
        "required": ["success", "status", "summary", "links", "stale_warnings", "safety_notes", "raw"],
        "properties": {
            "success": {"type": "boolean"},
            "status": {"type": "string"},
            "summary": {"type": "string"},
            "links": {"type": "array"},
            "stale_warnings": {"type": "array"},
            "safety_notes": {"type": "array"},
            "raw": {"type": "object"},
        },
    }


def farm_attention_summary_handler(_args):
    result = get_farm_attention_summary(limit=5)
    counts = result.get("counts", {})
    digest_lines = result.get("digest_lines") or []
    total = counts.get("attention_total", 0)
    if total:
        summary = "Farm attention has {} item(s). {}".format(
            total,
            " ".join(digest_lines[:4]),
        )
    else:
        summary = "No current farm attention items are showing."

    links = [{"label": "Dashboard", "href": "/"}]
    for item in result.get("sections", {}).get("litter_attention", [])[:3]:
        litter_id = item.get("litter_id")
        if litter_id:
            links.append({"label": str(litter_id), "href": f"/litter/{litter_id}"})

    return {
        "success": bool(result.get("success", False)),
        "status": str(result.get("status") or "ok"),
        "summary": summary,
        "links": links,
        "stale_warnings": [],
        "safety_notes": [],
        "raw": result,
    }


def farm_operating_brief_handler(_args):
    sections = {
        "attention": farm_attention_summary_handler({}),
        "power": power_current_handler({}),
        "weather": weather_today_handler({}),
        "irrigation": irrigation_status_handler({}),
    }
    stale_warnings = []
    safety_notes = []
    links = [{"label": "Farm Dashboard", "href": "/"}]
    for section in sections.values():
        stale_warnings.extend(section.get("stale_warnings") or [])
        safety_notes.extend(section.get("safety_notes") or [])
        links.extend(section.get("links") or [])

    unique_links = []
    seen_hrefs = set()
    for link in links:
        href = link.get("href")
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        unique_links.append(link)

    failed = [name for name, section in sections.items() if not section.get("success")]
    status = "partial" if failed else "ok"
    brief_sections = {
        name: {
            "status": section.get("status"),
            "summary": section.get("summary"),
            "stale_warnings": list(section.get("stale_warnings") or [])[:3],
            "safety_notes": list(section.get("safety_notes") or [])[:3],
        }
        for name, section in sections.items()
    }
    summary = (
        "Operating brief loaded. "
        f"Attention: {sections['attention'].get('summary', 'unavailable')} "
        f"Power: {sections['power'].get('summary', 'unavailable')} "
        f"Weather: {sections['weather'].get('summary', 'unavailable')} "
        f"Irrigation: {sections['irrigation'].get('summary', 'unavailable')}"
    )
    if failed:
        stale_warnings.append("Operating brief has unavailable section(s): {}.".format(", ".join(failed)))

    return {
        "success": not bool(failed),
        "status": status,
        "summary": summary,
        "links": unique_links[:8],
        "stale_warnings": stale_warnings[:6],
        "safety_notes": safety_notes[:6],
        "llm_context": {
            "kind": "farm_operating_brief",
            "required_sections": ["attention", "power", "weather", "irrigation"],
            "sections": brief_sections,
            "failed_sections": failed,
        },
        "raw": {
            "kind": "farm_operating_brief",
            "sections": sections,
            "failed_sections": failed,
        },
    }


def business_growth_brief_handler(_args):
    sections = {
        "sales": sales_dashboard_handler({}),
        "meat": meat_planning_handler({}),
    }
    stale_warnings = []
    safety_notes = [
        "Business growth brief is read-only advice. No customer message, post, quote, sale, or stock change was made."
    ]
    links = [{"label": "Sales Dashboard", "href": "/sales-dashboard"}]
    for section in sections.values():
        stale_warnings.extend(section.get("stale_warnings") or [])
        safety_notes.extend(section.get("safety_notes") or [])
        links.extend(section.get("links") or [])

    sales_raw = sections["sales"].get("raw") or {}
    meat_raw = sections["meat"].get("raw") or {}
    sales_totals = sales_raw.get("totals", []) if isinstance(sales_raw, dict) else []
    meat_summary = meat_raw.get("summary", {}) if isinstance(meat_raw, dict) else {}
    meat_pigs = meat_raw.get("pigs", []) if isinstance(meat_raw, dict) else []
    stock_total = sum(float(item.get("qty_available") or 0) for item in sales_totals)
    marketable_stock = _business_marketable_stock(sales_totals)
    young_stock = _business_young_stock(sales_totals)
    ready_now = int(meat_summary.get("ready_now") or 0)
    next_14 = int(meat_summary.get("next_14_days") or 0)
    ready_candidates = _business_ready_candidates(meat_pigs)
    focus = _business_growth_focus(marketable_stock["total"], ready_now, next_14)
    owner_question = _business_owner_question(marketable_stock, ready_candidates, ready_now, next_14)
    offer_outline = _business_offer_brief_outline(
        focus=focus,
        marketable_stock=marketable_stock,
        ready_candidates=ready_candidates,
        ready_now=ready_now,
        next_14=next_14,
    )
    marketable_label = _business_category_label(marketable_stock["categories"])
    ready_label = _business_ready_label(ready_candidates)
    summary = (
        "Business advisor brief: "
        f"{focus} Marketable listed stock is {marketable_stock['total']} pig(s)"
        f"{' across ' + marketable_label if marketable_label else ''}. "
        f"Young/not-ready stock is {young_stock['total']} pig(s). "
        f"Meat planning has {ready_now} ready now"
        f"{' (' + ready_label + ')' if ready_label else ''} and {next_14} due in the next 14 days. "
        f"Question: {owner_question}"
    )

    unique_links = []
    seen_hrefs = set()
    for link in links:
        href = link.get("href")
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        unique_links.append(link)

    failed = [name for name, section in sections.items() if not section.get("success")]
    return {
        "success": not failed,
        "status": "partial" if failed else "ok",
        "summary": summary,
        "links": unique_links[:6],
        "stale_warnings": stale_warnings,
        "safety_notes": safety_notes,
        "llm_context": {
            "kind": "business_growth_brief",
            "commercial_focus": focus,
            "owner_question": owner_question,
            "sales_summary": sections["sales"].get("summary"),
            "meat_summary": sections["meat"].get("summary"),
            "marketable_stock": marketable_stock,
            "young_or_not_ready_stock": young_stock,
            "ready_meat_candidates": ready_candidates,
            "offer_brief_outline": offer_outline,
            "counts": {
                "available_sales_stock": int(stock_total),
                "marketable_sales_stock": marketable_stock["total"],
                "young_or_not_ready_stock": young_stock["total"],
                "meat_ready_now": ready_now,
                "meat_next_14_days": next_14,
            },
            "next_action": focus,
        },
        "raw": {
            "sections": sections,
            "failed_sections": failed,
        },
    }


def jarvis_daily_command_brief_handler(_args):
    sections = {
        "farm": farm_operating_brief_handler({}),
        "business": business_growth_brief_handler({}),
        "command_center": agent_command_center_handler({}),
    }
    stale_warnings = []
    safety_notes = [
        "Daily command brief is read-only. No specialist was dispatched, no specialist LLM/tool execution ran, no farm data was written, no customer/public output was created, no patch/deploy/Telegram/control action occurred."
    ]
    links = [{"label": "Oom Sakkie", "href": "/oom-sakkie"}]
    for label, section in sections.items():
        if not section.get("success"):
            stale_warnings.append(f"Daily command brief section unavailable or partial: {label}.")
        stale_warnings.extend(section.get("stale_warnings") or [])
        safety_notes.extend(section.get("safety_notes") or [])
        links.extend(section.get("links") or [])

    unique_links = []
    seen_hrefs = set()
    for link in links:
        href = link.get("href")
        if href in seen_hrefs:
            continue
        seen_hrefs.add(href)
        unique_links.append(link)

    failed = [name for name, section in sections.items() if not section.get("success")]
    status = "partial" if failed else "ok"
    next_actions = _daily_command_next_actions(sections, failed)
    summary = (
        "Daily command brief loaded. "
        f"Farm: {sections['farm'].get('summary', 'unavailable')} "
        f"Business: {sections['business'].get('summary', 'unavailable')} "
        f"Command center: {sections['command_center'].get('summary', 'unavailable')} "
        f"Next: {next_actions[0] if next_actions else 'Keep monitoring the read-only command center.'}"
    )
    section_context = {
        name: {
            "status": section.get("status"),
            "summary": section.get("summary"),
            "stale_warnings": list(section.get("stale_warnings") or [])[:3],
            "safety_notes": list(section.get("safety_notes") or [])[:3],
            "llm_context": section.get("llm_context", {}),
        }
        for name, section in sections.items()
    }
    return {
        "success": not bool(failed),
        "status": status,
        "summary": summary,
        "links": unique_links[:10],
        "stale_warnings": stale_warnings[:10],
        "safety_notes": safety_notes[:10],
        "llm_context": {
            "kind": "jarvis_daily_command_brief",
            "sections": section_context,
            "failed_sections": failed,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
            "next_actions": next_actions,
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
        "raw": {
            "kind": "jarvis_daily_command_brief",
            "sections": sections,
            "failed_sections": failed,
        },
    }


def _daily_command_next_actions(sections, failed):
    actions = []
    command_context = (sections.get("command_center") or {}).get("llm_context") or {}
    queue_snapshots = command_context.get("queue_snapshots") or {}
    work_counts = ((queue_snapshots.get("system_work_status") or {}).get("counts") or {})
    pending_work = sum(
        int(work_counts.get(key) or 0)
        for key in (
            "pending_build_requests",
            "pending_patch_reviews",
            "pending_dispatch_design_requests",
        )
    )
    if pending_work:
        actions.append(f"Review {pending_work} pending approval/design item(s) in the Oom Sakkie workbench.")

    business_context = (sections.get("business") or {}).get("llm_context") or {}
    owner_question = business_context.get("owner_question")
    if owner_question:
        actions.append(str(owner_question))

    farm_context = (sections.get("farm") or {}).get("llm_context") or {}
    farm_failed = failed or farm_context.get("failed_sections") or []
    if farm_failed:
        actions.append("Review the unavailable command brief section(s): {}.".format(", ".join(farm_failed)))

    if not actions:
        actions.append("Use the farm, business, or command-center section that matters most today; no action was taken automatically.")
    return actions[:3]


def _business_marketable_stock(sales_totals):
    categories = []
    total = 0
    for item in sales_totals:
        qty = int(float(item.get("qty_available") or 0))
        if qty <= 0:
            continue
        status = str(item.get("status") or "")
        if status.lower() in {"not for sale", "out of stock"}:
            continue
        category = str(item.get("sale_category") or "Unknown")
        categories.append({
            "category": category,
            "qty": qty,
            "status": status,
            "price_range": str(item.get("price_range") or ""),
        })
        total += qty
    return {"total": total, "categories": categories[:6]}


def _business_young_stock(sales_totals):
    categories = []
    total = 0
    for item in sales_totals:
        qty = int(float(item.get("qty_available") or 0))
        if qty <= 0:
            continue
        status = str(item.get("status") or "")
        category = str(item.get("sale_category") or "Unknown")
        if status.lower() == "not for sale" or category.lower() in {"newborn", "young piglets"}:
            categories.append({
                "category": category,
                "qty": qty,
                "status": status,
            })
            total += qty
    return {"total": total, "categories": categories[:6]}


def _business_ready_candidates(meat_pigs):
    candidates = []
    for pig in meat_pigs:
        if pig.get("planning_bucket") != "ready_now":
            continue
        candidates.append({
            "pig_id": pig.get("pig_id"),
            "tag_number": pig.get("tag_number"),
            "pen": pig.get("current_pen_name") or pig.get("current_pen_id"),
            "weight_kg": pig.get("latest_weight_kg"),
            "action": pig.get("recommended_action"),
            "readiness": pig.get("marketing_readiness"),
        })
    return candidates[:5]


def _business_category_label(categories):
    return ", ".join(
        f"{item['category']} {item['qty']}"
        for item in categories[:4]
        if item.get("category")
    )


def _business_ready_label(candidates):
    return ", ".join(
        "tag {} in {} at {} kg".format(
            _display_value(item.get("tag_number")),
            _display_value(item.get("pen")),
            _display_value(item.get("weight_kg")),
        )
        for item in candidates[:3]
    )


def _business_growth_focus(stock_total, ready_now, next_14):
    if stock_total > 0 and ready_now > 0:
        return "Prioritize converting ready meat stock into paid orders before adding new offers."
    if ready_now > 0:
        return "Prioritize lining up buyers for pigs that are ready now."
    if next_14 > 0:
        return "Start warming up buyers for the next 14-day meat pipeline."
    if stock_total > 0:
        return "Prioritize moving available listed stock and checking whether the offer wording is clear."
    return "No immediate commercial push is obvious from the read-only sales and meat signals."


def _business_owner_question(marketable_stock, ready_candidates, ready_now, next_14):
    if ready_candidates:
        return "Should I help prepare a draft offer brief for the ready meat candidates for your approval?"
    if marketable_stock["total"] > 0:
        return "Which buyer segment should we target first for the listed stock?"
    if next_14 > 0:
        return "Do you want a buyer warm-up plan for the pigs due in the next 14 days?"
    return "Do you want me to check orders and customer demand next before suggesting an offer?"


def _business_offer_brief_outline(*, focus, marketable_stock, ready_candidates, ready_now, next_14):
    if ready_candidates:
        basis_items = [
            "tag {} in {} at {} kg".format(
                _display_value(item.get("tag_number")),
                _display_value(item.get("pen")),
                _display_value(item.get("weight_kg")),
            )
            for item in ready_candidates[:3]
        ]
        title = "Ready meat preorder opportunity"
        target = "Existing meat buyers or known customers who can confirm interest before processing."
        evidence = "{} ready now; {} due in the next 14 days.".format(ready_now, next_14)
        next_step = "Approve a future draft-only customer offer brief after checking price, cut set, collection/delivery, and availability."
    elif marketable_stock["total"] > 0:
        basis_items = [
            "{}: {} available".format(item.get("category"), item.get("qty"))
            for item in marketable_stock["categories"][:3]
            if item.get("category")
        ]
        title = "Listed-stock sales push"
        target = "Buyer segment to be chosen by the owner before any customer-facing wording."
        evidence = "{} marketable listed pig(s).".format(marketable_stock["total"])
        next_step = "Choose the buyer segment first, then approve a future draft-only offer brief."
    else:
        basis_items = []
        title = "Demand discovery before selling"
        target = "No customer-facing target yet."
        evidence = "No immediate marketable stock or ready meat opportunity is clear from the current read-only signals."
        next_step = "Review orders and customer demand before preparing any offer brief."

    return {
        "mode": "internal_outline_only",
        "title": title,
        "commercial_focus": focus,
        "target": target,
        "stock_basis": basis_items,
        "evidence": evidence,
        "approval_needed": "Owner approval is required before any customer-facing draft, public post, quote, reservation, sale, or stock change.",
        "next_step": next_step,
        "not_done": [
            "No customer message drafted.",
            "No public post drafted.",
            "No quote created.",
            "No sale, reservation, or stock change made.",
        ],
    }



def power_current_handler(_args):
    result, status_code = get_current_power_state()
    source = result.get("source", {}) if isinstance(result, dict) else {}
    current = result.get("current", {}) if isinstance(result, dict) else {}
    summary_data = result.get("summary", {}) if isinstance(result, dict) else {}
    stale_warnings = []
    if source.get("is_stale"):
        stale_warnings.append(
            "Power data is stale: {} minutes old.".format(source.get("data_age_minutes", "unknown"))
        )

    if result.get("success"):
        battery = current.get("battery_soc_pct")
        solar = current.get("solar_power_w")
        load = current.get("load_power_w")
        grid = current.get("grid_power_w")
        battery_state = str(current.get("battery_state") or "unknown").replace("_", " ")
        grid_state = str(current.get("grid_state") or "unknown").replace("_", " ")
        data_age = source.get("data_age_minutes")
        headline = summary_data.get("headline") or "Power state loaded."
        summary = "{} Battery: {}% and {}. Solar: {} W. Load: {} W. Grid: {} W ({}). Data age: {} minute(s).".format(
            headline,
            _display_value(battery),
            battery_state,
            _display_value(solar),
            _display_value(load),
            _display_value(grid),
            grid_state,
            _display_value(data_age),
        )
    else:
        summary = result.get("message") or "Power data is unavailable."

    return {
        "success": bool(result.get("success", False)),
        "status": str(result.get("status") or status_code),
        "summary": summary,
        "links": [{"label": "Dashboard Power", "href": "/#power_panel"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [],
        "raw": result,
    }


def power_recent_handler(_args):
    result, status_code = get_recent_power_profile(hours=24)
    window = result.get("window", {}) if isinstance(result, dict) else {}
    battery = result.get("battery", {}) if isinstance(result, dict) else {}
    power = result.get("power", {}) if isinstance(result, dict) else {}
    activity = result.get("activity", {}) if isinstance(result, dict) else {}
    summary_data = result.get("summary", {}) if isinstance(result, dict) else {}
    stale_warnings = _limitation_warnings(result)
    coverage = window.get("coverage_pct")
    if coverage is not None and coverage < 75:
        stale_warnings.append(f"Power profile coverage is limited: {coverage}% of expected samples.")

    if result.get("success"):
        headline = summary_data.get("headline") or "Recent power profile loaded."
        summary = (
            f"{headline} Battery ranged from {_display_value(battery.get('min_soc_pct'))}% "
            f"to {_display_value(battery.get('max_soc_pct'))}%. "
            f"Max solar: {_display_value(power.get('max_solar_power_w'))} W. "
            f"Grid active approx: {_display_value(activity.get('grid_active_approx_minutes'))} minutes."
        )
    else:
        summary = result.get("message") or "Recent power profile is unavailable."

    return {
        "success": bool(result.get("success", False)),
        "status": str(result.get("status") or status_code),
        "summary": summary,
        "links": [{"label": "Dashboard Power", "href": "/#power_panel"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [],
        "raw": result,
    }


def weather_now_handler(_args):
    result, status_code = get_current_weather_state()
    source = result.get("source", {}) if isinstance(result, dict) else {}
    current = result.get("current", {}) if isinstance(result, dict) else {}
    summary_data = result.get("summary", {}) if isinstance(result, dict) else {}
    stale_warnings = []
    if source.get("is_stale"):
        stale_warnings.append(
            "Weather data is stale: {} minutes old.".format(source.get("data_age_minutes", "unknown"))
        )

    if result.get("success"):
        headline = summary_data.get("headline") or "Current weather loaded."
        summary = (
            f"{headline} Temperature: {_display_value(current.get('temperature_c'))} C. "
            f"Humidity: {_display_value(current.get('humidity_pct'))}%. "
            f"Wind: {_display_value(current.get('wind_speed_kmh'))} km/h. "
            f"Rain now: {_display_value(current.get('rain_rate_mm_h'))} mm/h."
        )
    else:
        summary = result.get("message") or "Current weather is unavailable."

    return {
        "success": bool(result.get("success", False)),
        "status": str(result.get("status") or status_code),
        "summary": summary,
        "links": [{"label": "Dashboard Weather", "href": "/#weather_panel"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [],
        "raw": result,
    }


def weather_today_handler(_args):
    result, status_code = get_weather_today_summary()
    source = result.get("source", {}) if isinstance(result, dict) else {}
    summary_data = result.get("summary", {}) if isinstance(result, dict) else {}
    window = result.get("window", {}) if isinstance(result, dict) else {}
    rain = result.get("rain", {}) if isinstance(result, dict) else {}
    temperature = result.get("temperature", {}) if isinstance(result, dict) else {}

    stale_warnings = []
    if source.get("is_stale"):
        stale_warnings.append("Weather data is stale.")
    coverage = window.get("coverage_pct")
    if coverage is not None and coverage < 50:
        stale_warnings.append(f"Weather sample coverage is low today: {coverage}%.")

    if result.get("success"):
        headline = summary_data.get("headline") or "Weather summary loaded."
        summary = "{} Rain today: {} mm. Temperature range: {} to {} C.".format(
            headline,
            _display_value(rain.get("total_mm")),
            _display_value(temperature.get("min_c")),
            _display_value(temperature.get("max_c")),
        )
    else:
        summary = result.get("message") or "Weather data is unavailable."

    return {
        "success": bool(result.get("success", False)),
        "status": str(result.get("status") or status_code),
        "summary": summary,
        "links": [{"label": "Dashboard Weather", "href": "/#weather_panel"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [],
        "raw": result,
    }


def weather_forecast_handler(_args):
    result, status_code = get_weather_forecast(days=3)
    source = result.get("source", {}) if isinstance(result, dict) else {}
    window = result.get("window", {}) if isinstance(result, dict) else {}
    summary_data = result.get("summary", {}) if isinstance(result, dict) else {}
    days = result.get("days", []) if isinstance(result, dict) else []
    stale_warnings = []
    if source.get("is_stale"):
        stale_warnings.append(
            "Weather forecast is stale: {} minutes old.".format(source.get("data_age_minutes", "unknown"))
        )
    if window.get("returned_days", 0) < window.get("requested_days", 3):
        stale_warnings.append("Weather forecast returned fewer days than requested.")

    if result.get("success"):
        headline = summary_data.get("headline") or "Weather forecast loaded."
        first = days[0] if days else {}
        summary = (
            f"{headline} Next forecast day: {first.get('forecast_date', 'unknown')}. "
            f"Rain: {_display_value(first.get('rain_sum_mm'))} mm, "
            f"probability {_display_value(first.get('rain_probability_max_pct'))}%. "
            f"Wind max: {_display_value(first.get('wind_max_kmh'))} km/h."
        )
    else:
        summary = result.get("message") or "Weather forecast is unavailable."

    return {
        "success": bool(result.get("success", False)),
        "status": str(result.get("status") or status_code),
        "summary": summary,
        "links": [{"label": "Dashboard Weather", "href": "/#weather_panel"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [],
        "raw": result,
    }


def irrigation_status_handler(_args):
    result, status_code = get_irrigation_status()
    safety = result.get("safety", {}) if isinstance(result, dict) else {}
    current = result.get("current", {}) if isinstance(result, dict) else {}
    today = result.get("today", {}) if isinstance(result, dict) else {}
    operator_summary = result.get("operator_summary", {}) if isinstance(result, dict) else {}
    stale_warnings = []
    safety_notes = []
    if not safety.get("can_control", False):
        safety_notes.append("Irrigation is read-only here. No start/stop command was sent.")
    for note in operator_summary.get("notes", [])[:2]:
        if note:
            safety_notes.append(str(note))

    if result.get("success"):
        headline = operator_summary.get("headline") or "Irrigation status loaded."
        summary = (
            f"{headline} Current status: {_display_value(current.get('status'))}. "
            f"Current zone: {_display_value(current.get('zone_name') or current.get('zone_id'))}. "
            f"Done today: {_display_value(today.get('done_count'))}. "
            f"Next zone: {_display_value(today.get('next_zone_name') or today.get('next_zone_id'))}."
        )
    else:
        summary = result.get("message") or "Irrigation status is unavailable."

    return {
        "success": bool(result.get("success", False)),
        "status": str(result.get("status") or status_code),
        "summary": summary,
        "links": [{"label": "Farm Dashboard", "href": "/#irrigation_panel"}],
        "stale_warnings": stale_warnings,
        "safety_notes": safety_notes,
        "raw": result,
    }


def dashboard_summary_handler(_args):
    result = get_dashboard_data()
    summary_data = result.get("summary", {}) if isinstance(result, dict) else {}
    monthly_sales = (
        summary_data.get("sales_transaction_count_this_month")
        or summary_data.get("sold_this_month")
        or 0
    )
    on_farm = summary_data.get("on_farm_pigs") or 0
    reserved = summary_data.get("reserved_pigs") or 0
    attention = result.get("litter_attention", {}) if isinstance(result, dict) else {}
    attention_count = attention.get("count", 0)

    summary = (
        f"Farm overview: {on_farm} pigs on farm, {reserved} reserved, "
        f"{monthly_sales} sales exits this month, and {attention_count} litter attention item(s)."
    )
    return {
        "success": bool(result.get("success", False)),
        "status": "ok" if result.get("success") else "unavailable",
        "summary": summary,
        "links": [{"label": "Farm Dashboard", "href": "/"}],
        "stale_warnings": [],
        "safety_notes": [],
        "raw": result,
    }


def pig_allocation_readiness_handler(_args):
    result = get_pig_allocation_readiness_data()
    summary_data = result.get("summary", {}) if isinstance(result, dict) else {}
    buckets = summary_data.get("buckets", {}) if isinstance(summary_data, dict) else {}
    total = summary_data.get("total", 0)
    summary = (
        f"Pig allocation has {total} pigs in the read-only view. "
        f"Meat candidates: {buckets.get('Meat Candidate', 0)}. "
        f"Livestock candidates: {buckets.get('Livestock Candidate', 0)}. "
        f"Breeding review: {buckets.get('Retain / Breeding Candidate', 0)}."
    )
    return {
        "success": bool(result.get("success", False)),
        "status": "ok" if result.get("success") else "unavailable",
        "summary": summary,
        "links": [{"label": "Pig Allocation", "href": "/pig-allocation"}],
        "stale_warnings": _limitation_warnings(result),
        "safety_notes": ["This is read-only planning from pig allocation readiness. Nothing was saved."],
        "raw": result,
    }


def meat_planning_handler(_args):
    result = get_meat_planning_data()
    summary_data = result.get("summary", {}) if isinstance(result, dict) else {}
    summary = (
        f"Meat planning: {summary_data.get('ready_now', 0)} ready now, "
        f"{summary_data.get('next_14_days', 0)} in the next 14 days, "
        f"{summary_data.get('next_30_days', 0)} in the next 30 days, "
        f"and {summary_data.get('fallback_abattoir', 0)} fallback abattoir candidate(s)."
    )
    return {
        "success": bool(result.get("success", False)),
        "status": "ok" if result.get("success") else "unavailable",
        "summary": summary,
        "links": [{"label": "Meat Planning", "href": "/meat-planning"}],
        "stale_warnings": _limitation_warnings(result),
        "safety_notes": ["This is read-only planning from meat planning. Nothing was saved."],
        "raw": result,
    }


def sales_dashboard_handler(_args):
    result = get_sales_dashboard_data()
    totals = result.get("totals", []) if isinstance(result, dict) else []
    stock_total = sum(float(item.get("qty_available") or 0) for item in totals)
    categories = [
        f"{item.get('sale_category')}: {int(float(item.get('qty_available') or 0))}"
        for item in totals[:4]
        if item.get("sale_category")
    ]
    detail = ", ".join(categories) if categories else "No stock category totals returned."
    summary = f"Sales dashboard stock availability shows {int(stock_total)} available pig(s). {detail}."
    return {
        "success": bool(result.get("success", False)),
        "status": "ok" if result.get("success") else "unavailable",
        "summary": summary,
        "links": [{"label": "Sales Dashboard", "href": "/sales-dashboard"}],
        "stale_warnings": [],
        "safety_notes": [],
        "raw": result,
    }


def system_work_status_handler(_args):
    build_result, build_status = list_build_requests(limit=5)
    patch_result, patch_status = list_patch_proposals(limit=5)
    deploy_result, deploy_status = list_deploy_decisions(limit=5)
    dispatch_result, dispatch_status = list_dispatch_requests(limit=5)

    statuses = {
        "build_requests": build_status,
        "patch_proposals": patch_status,
        "deploy_decisions": deploy_status,
        "dispatch_requests": dispatch_status,
    }
    store_warnings = _system_work_store_warnings(statuses)
    configured = all(
        result.get("configured", True)
        for result in (build_result, patch_result, deploy_result, dispatch_result)
        if isinstance(result, dict)
    )
    build_items = build_result.get("build_requests", []) if isinstance(build_result, dict) else []
    patch_items = patch_result.get("patch_proposals", []) if isinstance(patch_result, dict) else []
    deploy_items = deploy_result.get("deploy_decisions", []) if isinstance(deploy_result, dict) else []
    dispatch_items = dispatch_result.get("dispatch_requests", []) if isinstance(dispatch_result, dict) else []
    pending_build = [
        item for item in build_items
        if _system_work_build_stage(item) == "pending"
    ]
    patch_without_decision = [
        item for item in patch_items
        if not (item.get("latest_event") or {}).get("event_type")
    ]
    approved_patch = [
        item for item in patch_items
        if (item.get("latest_event") or {}).get("event_type") == "approved_for_patch"
    ]
    deploy_decided_patch_ids = {
        item.get("patch_proposal_id")
        for item in deploy_items
        if item.get("patch_proposal_id")
    }
    deploy_ready_patch = [
        item for item in approved_patch
        if item.get("patch_proposal_id") not in deploy_decided_patch_ids
    ]
    pending_dispatch_design = _dispatch_requests_without_decision(dispatch_items)

    if store_warnings:
        base_summary = (
            f"{len(pending_build)} item(s) need Forge Handoff or a Builder plan, "
            f"{len(patch_without_decision)} patch proposal(s) need approve/reject review, "
            f"{len(deploy_ready_patch)} approved patch proposal(s) need verification plus a deploy decision, "
            f"and {len(pending_dispatch_design)} dispatch design request(s) need owner/Claude review from the stores I could read."
        )
        if not configured:
            summary = "System work status is incomplete because one or more approval stores are not configured. " + base_summary
            status = "not_configured"
        else:
            summary = "System work status is incomplete because one or more approval stores could not be read. " + base_summary
            status = "degraded"
    elif not configured:
        summary = "System work status is not configured in this process. The approval tables may still be available in the running kiosk environment."
        status = "not_configured"
    else:
        summary = (
            "System work status: "
            f"{len(pending_build)} item(s) need Forge Handoff or a Builder plan, "
            f"{len(patch_without_decision)} patch proposal(s) need approve/reject review, "
            f"{len(deploy_ready_patch)} approved patch proposal(s) need verification plus a deploy decision, "
            f"and {len(pending_dispatch_design)} dispatch design request(s) need owner/Claude review."
        )
        status = "ok"

    return {
        "success": configured and not store_warnings,
        "status": status,
        "summary": summary,
        "links": [{"label": "Oom Sakkie Workbench", "href": "/oom-sakkie"}],
        "stale_warnings": store_warnings,
        "safety_notes": ["System work status is read-only. No build, patch, deploy, specialist dispatch, specialist LLM/tool execution, or runtime change was run."],
        "llm_context": {
            "kind": "system_work_status",
            "counts": {
                "build_requests": len(build_items),
                "patch_proposals": len(patch_items),
                "deploy_decisions": len(deploy_items),
                "dispatch_requests": len(dispatch_items),
                "pending_build_requests": len(pending_build),
                "patch_proposals_without_decision": len(patch_without_decision),
                "approved_patch_proposals": len(approved_patch),
                "deploy_ready_patch_proposals": len(deploy_ready_patch),
                "pending_dispatch_design_requests": len(pending_dispatch_design),
            },
            "statuses": statuses,
            "next_action": _system_work_next_action(
                pending_build,
                patch_without_decision,
                deploy_ready_patch,
                pending_dispatch_design,
            ),
        },
        "raw": {
            "build_requests": build_result,
            "patch_proposals": patch_result,
            "deploy_decisions": deploy_result,
            "dispatch_requests": dispatch_result,
            "statuses": statuses,
        },
}


def dispatch_decision_status_handler(_args):
    result, status_code = list_dispatch_requests(limit=8)
    dispatch_items = result.get("dispatch_requests", []) if isinstance(result, dict) else []
    pending = _dispatch_requests_without_decision(dispatch_items)
    counts = _dispatch_decision_counts(dispatch_items)
    configured = bool(result.get("configured", True)) if isinstance(result, dict) else False
    stale_warnings = []
    if status_code != 200:
        stale_warnings.append(f"Dispatch design status is incomplete: dispatch_requests unavailable (status {status_code}).")

    if status_code == 200:
        summary = (
            "Dispatch design status: "
            f"{len(pending)} request(s) need owner/Claude design review, "
            f"{counts.get('approved_for_design_review', 0)} approved for design review, "
            f"{counts.get('rejected', 0)} rejected, and {counts.get('deferred', 0)} deferred. "
            "No specialist dispatch is enabled."
        )
        status = "ok"
    elif not configured:
        summary = "Dispatch design status is not configured in this process. No specialist dispatch is enabled."
        status = "not_configured"
    else:
        summary = "Dispatch design status is degraded because the dispatch request store could not be read. No specialist dispatch is enabled."
        status = "degraded"

    return {
        "success": status_code == 200,
        "status": status,
        "summary": summary,
        "links": [{"label": "Dispatch Requests", "href": "/api/oom-sakkie/dispatch-requests"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [
            "Dispatch design status is read-only. No specialist was dispatched, no specialist LLM/tool ran, no runtime flag changed, and no farm data was written."
        ],
        "llm_context": {
            "kind": "dispatch_decision_status",
            "counts": {
                "dispatch_requests": len(dispatch_items),
                "pending_design_review": len(pending),
                **counts,
            },
            "next_action": _dispatch_decision_next_action(pending),
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
        },
        "raw": result,
    }


def _system_work_store_warnings(statuses):
    warnings = []
    for name, status_code in statuses.items():
        if status_code != 200:
            warnings.append(
                f"System work status is incomplete: {name} unavailable (status {status_code})."
            )
    return warnings


def agent_crew_status_handler(args):
    status = get_agent_runtime_status()
    recommendation = recommend_agent_for_text((args or {}).get("user_text") or "")
    selected = recommendation.get("selected_agent") or {}
    agents = status.get("agents") or []
    agent_names = ", ".join(agent.get("name", agent.get("slug", "")) for agent in agents[:6])
    if len(agents) > 6:
        agent_names = f"{agent_names}, and {len(agents) - 6} more"
    summary = (
        f"Agent crew foundation has {status.get('agent_count', 0)} planned agent(s): {agent_names}. "
        f"For this question, I would route to {selected.get('name', 'Gatekeeper')} because {recommendation.get('reason', 'fallback')}. "
        "This is a recommendation only; no specialist agent was run."
    )
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Oom Sakkie Agents", "href": "/api/oom-sakkie/agents"}],
        "stale_warnings": [],
        "safety_notes": [
            "Agent crew status is advisory only. No specialist was dispatched, no tool was executed by a specialist, and no write was performed."
        ],
        "llm_context": {
            "kind": "agent_crew_status",
            "runtime": {
                "runtime_enabled": status.get("runtime_enabled"),
                "dispatch_enabled": status.get("dispatch_enabled"),
                "autonomous_loops_enabled": status.get("autonomous_loops_enabled"),
                "writes_enabled": status.get("writes_enabled"),
            },
            "selected_agent": selected,
            "recommendation": {
                "mode": recommendation.get("mode"),
                "reason": recommendation.get("reason"),
                "runs_agent": recommendation.get("runs_agent"),
                "writes": recommendation.get("writes"),
                "next_gate": recommendation.get("next_gate"),
            },
            "agent_count": status.get("agent_count", 0),
        },
        "raw": {
            "agent_runtime": status,
            "recommendation": recommendation,
        },
    }


def agent_crew_brief_handler(args):
    brief = build_agent_crew_brief((args or {}).get("user_text") or "")
    names = [item.get("name") for item in brief.get("sequence", [])[:4] if item.get("name")]
    summary = (
        "Crew brief prepared: Oom Sakkie would coordinate {} for this request. "
        "This is a plan only; no specialist was dispatched and no action was taken."
    ).format(", ".join(names) if names else "the planned specialist crew")
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Oom Sakkie Agents", "href": "/api/oom-sakkie/agents"}],
        "stale_warnings": [],
        "safety_notes": [
            "Crew brief is plan-only. No specialist was dispatched, no specialist LLM ran, no tool was executed by a specialist, and no write was performed."
        ],
        "llm_context": {
            "kind": "agent_crew_brief",
            "crew_brief": brief,
            "selected_agent": (brief.get("sequence") or [{}])[0],
        },
        "raw": brief,
    }


def agent_activation_plan_handler(_args):
    plan = get_agent_activation_plan()
    candidate = plan.get("recommended_first_candidate") or {}
    learning = accepted_agent_learning_snapshot(limit=20)
    accepted_count = learning["accepted_count"]
    specialist_summary = _accepted_learning_specialist_summary(learning.get("accepted_by_specialist", {}))
    learning_line = (
        f"Accepted learning evidence: {accepted_count} accepted agent result(s) can guide planning"
        f"{specialist_summary}, but runtime stays locked. "
        if accepted_count
        else "No accepted agent learning evidence is available yet. "
    )
    summary = (
        "Agent activation plan: foundation is visible now; next safe stage is a read-only dry-run. "
        f"{learning_line}"
        "Recommended first candidate is {} because {} "
        "Nothing is enabled yet; owner approval and audit gates are still required."
    ).format(candidate.get("name", "Sentinel"), candidate.get("reason", "it has the smallest safe surface."))
    stale_warnings = []
    if learning["status_code"] != 200:
        stale_warnings.append(
            f"Accepted agent learning evidence is unavailable (status {learning['status_code']})."
        )
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Oom Sakkie Agents", "href": "/api/oom-sakkie/agents"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [
            "Agent activation plan is read-only. Accepted evidence may guide future planning only; no specialist was dispatched, no runtime flag was enabled, and no write was performed."
        ],
        "llm_context": {
            "kind": "agent_activation_plan",
            "activation_plan": plan,
            "selected_agent": candidate,
            "accepted_learning": learning["evidence"],
            "accepted_learning_count": accepted_count,
            "accepted_by_specialist": learning.get("accepted_by_specialist", {}),
        },
        "raw": {
            "activation_plan": plan,
            "accepted_learning": learning,
        },
    }


def agent_runtime_readiness_handler(_args):
    readiness = get_agent_runtime_readiness()
    ready_count = len(readiness.get("ready_gates", []))
    manual_count = len(readiness.get("manual_gates", []))
    locked_count = len(readiness.get("locked_gates", []))
    summary = (
        "Agent runtime readiness: {} gate(s) ready, {} manual check(s) required, and {} live-authority gate(s) still locked. "
        "Next safe action: {}"
    ).format(
        ready_count,
        manual_count,
        locked_count,
        readiness.get("next_safe_action", "continue read-only review"),
    )
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [
            {
                "label": "Browser Behavior Checklist",
                "href": "docs/06-operations/OOM_SAKKIE_BROWSER_BEHAVIOR_CHECKLIST.md",
            }
        ],
        "stale_warnings": [],
        "safety_notes": [
            "Agent runtime readiness is read-only. It does not run specialists, dispatch agents, call specialist LLMs, execute specialist tools, write farm data, create public output, apply patches, deploy, cut over Telegram, or control hardware."
        ],
        "llm_context": {
            "kind": "agent_runtime_readiness",
            "readiness": readiness,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": readiness,
    }


def jarvis_product_progress_handler(_args):
    progress = get_jarvis_product_progress()
    summary = (
        "Jarvis product progress: overall {}% {}. "
        "Foundation is strong, but live specialist execution and public/customer selling stay locked. "
        "Next milestone: {}."
    ).format(
        progress.get("overall_percent", 0),
        progress.get("overall_bar", ""),
        (progress.get("next_milestone") or {}).get("name", "Read-only Agent Command Center"),
    )
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Next Steps", "href": "docs/00-start-here/NEXT_STEPS.md"}],
        "stale_warnings": [],
        "safety_notes": [
            "Jarvis product progress is read-only planning status. It does not run specialists, enable dispatch, call specialist LLMs/tools, write farm data, create public output, apply patches, deploy, cut over Telegram, or control hardware."
        ],
        "llm_context": {
            "kind": "jarvis_product_progress",
            "progress": progress,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": progress,
    }


def agent_command_center_handler(_args):
    center = get_agent_command_center()
    work_status = system_work_status_handler({})
    dry_run_status = agent_dry_run_status_handler({})
    dispatch_status = dispatch_decision_status_handler({})
    stale_warnings = []
    for label, result in (
        ("system work status", work_status),
        ("agent dry-run status", dry_run_status),
        ("dispatch decision status", dispatch_status),
    ):
        if result.get("status") not in {"ok", "not_configured"}:
            stale_warnings.append(f"Agent command center snapshot is incomplete: {label} returned {result.get('status')}.")
        stale_warnings.extend(result.get("stale_warnings") or [])

    summary = (
        "Agent command center: {} lane(s) are visible in read-only mode, overall Jarvis progress is {}% {}, "
        "and live authority remains locked. Next action: {}"
    ).format(
        len(center.get("lanes", [])),
        center.get("overall_percent", 0),
        center.get("overall_bar", ""),
        center.get("next_action", "continue read-only owner review"),
    )
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [
            {"label": "Runtime Review Packet", "href": "/api/oom-sakkie/agents/runtime-review-packet"},
            {"label": "Authority Matrix", "href": "/api/oom-sakkie/agents/authority-matrix"},
        ],
        "stale_warnings": stale_warnings,
        "safety_notes": [
            "Agent command center is read-only visibility. It does not run specialists, enable dispatch, call specialist LLMs/tools, write farm data, create public/customer output, apply patches, deploy, cut over Telegram, or control hardware."
        ],
        "llm_context": {
            "kind": "agent_command_center",
            "command_center": center,
            "queue_snapshots": {
                "system_work_status": work_status.get("llm_context", {}),
                "agent_dry_run_status": dry_run_status.get("llm_context", {}),
                "dispatch_decision_status": dispatch_status.get("llm_context", {}),
            },
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": {
            "command_center": center,
            "system_work_status": work_status,
            "agent_dry_run_status": dry_run_status,
            "dispatch_decision_status": dispatch_status,
        },
    }


def agent_operating_contracts_handler(_args):
    contracts = get_agent_operating_contracts()
    contract_count = contracts.get("contract_count", 0)
    dry_run_allowed = contracts.get("dry_run_allowed") or []
    locked_out = contracts.get("locked_out_of_dry_run") or []
    locked_text = ", ".join(locked_out) if locked_out else "none"
    summary = (
        "Agent operating contracts: {} planned contract(s) documented, {} specialist(s) allowed for dry-run request records, "
        "and {} locked out of dry-run requests. These are planning contracts only, not runtime authority."
    ).format(contract_count, len(dry_run_allowed), locked_text)
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Agent Roadmap", "href": "/api/oom-sakkie/agents/activation-plan"}],
        "stale_warnings": [],
        "safety_notes": [
            "Agent operating contracts are read-only planning records. No specialist was dispatched, no specialist LLM ran, no specialist tool executed, no runtime flag changed, and no write/public/control action occurred."
        ],
        "llm_context": {
            "kind": "agent_operating_contracts",
            "contracts": contracts,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": contracts,
    }


def agent_activation_preflight_handler(_args):
    preflight = get_agent_activation_preflight()
    summary = (
        "Agent activation preflight: not ready for live dispatch. "
        "{} check(s) pass, {} manual check(s) are still required, and {} live-authority gate(s) remain locked. "
        "Next safe action: {}"
    ).format(
        preflight.get("ready_count", 0),
        preflight.get("manual_check_count", 0),
        preflight.get("locked_count", 0),
        preflight.get("recommended_next_safe_action", "continue no-execution review"),
    )
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [
            {
                "label": "Claude Review Handoff",
                "href": "docs/00-start-here/CLAUDE_REVIEW_HANDOFF.md",
            }
        ],
        "stale_warnings": [],
        "safety_notes": [
            "Agent activation preflight is read-only. It does not run specialists, dispatch agents, call specialist LLMs, execute specialist tools, write farm data, create public output, apply patches, deploy, cut over Telegram, or control hardware."
        ],
        "llm_context": {
            "kind": "agent_activation_preflight",
            "preflight": preflight,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": preflight,
    }


def agent_authority_matrix_handler(_args):
    matrix = get_agent_authority_matrix()
    summary = (
        "Agent authority matrix: {} authority area(s) are locked and {} are enabled. "
        "Highest locked risk level is {}. No live authority is active."
    ).format(
        matrix.get("locked_count", 0),
        matrix.get("enabled_count", 0),
        matrix.get("max_locked_risk_level", 0),
    )
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Agent Preflight", "href": "/api/oom-sakkie/agents/preflight"}],
        "stale_warnings": [],
        "safety_notes": [
            "Agent authority matrix is read-only. It does not enable dispatch, specialist LLMs, specialist tools, writes, customer/public output, Builder/Forge, deploys, Telegram cutover, or physical controls."
        ],
        "llm_context": {
            "kind": "agent_authority_matrix",
            "authority_matrix": matrix,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": matrix,
    }


def agent_authority_unlock_readiness_handler(_args):
    readiness = get_agent_authority_unlock_readiness()
    candidates = readiness.get("lowest_risk_candidates") or []
    labels = ", ".join(item["label"] for item in candidates) if candidates else "none"
    summary = (
        "Agent authority unlock readiness: no unlock is recommended. "
        "Lowest-risk planning candidate(s): {}. "
        "{} high-risk authority area(s) stay hard-no for now."
    ).format(labels, len(readiness.get("hard_no_authorities") or []))
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Agent Authority Matrix", "href": "/api/oom-sakkie/agents/authority-matrix"}],
        "stale_warnings": [],
        "safety_notes": [
            "Agent authority unlock readiness is planning-only. It does not unlock authority, dispatch agents, run specialist LLMs/tools, write farm data, create public output, apply patches, deploy, cut over Telegram, or control hardware."
        ],
        "llm_context": {
            "kind": "agent_authority_unlock_readiness",
            "unlock_readiness": readiness,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": readiness,
    }


def agent_dispatch_decision_rail_blueprint_handler(_args):
    blueprint = get_agent_dispatch_decision_rail_blueprint()
    summary = (
        "Dispatch decision rail blueprint is ready for review only. "
        "It proposes {} append-only table(s), {} endpoint shape(s), and {} required test(s), but dispatch stays off."
    ).format(
        len(blueprint.get("proposed_tables") or []),
        len(blueprint.get("required_endpoints") or []),
        len(blueprint.get("required_tests") or []),
    )
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Dispatch Rail Blueprint", "href": "/api/oom-sakkie/agents/dispatch-rail-blueprint"}],
        "stale_warnings": [],
        "safety_notes": [
            "Dispatch decision rail blueprint is read-only. It does not run specialists, enable dispatch, call specialist LLMs/tools, write farm data, apply runtime changes, or create public output."
        ],
        "llm_context": {
            "kind": "agent_dispatch_decision_rail_blueprint",
            "dispatch_blueprint": blueprint,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": blueprint,
    }


def agent_runtime_review_packet_handler(_args):
    packet = get_agent_runtime_review_packet()
    summary = (
        "Agent runtime review packet is ready for bulk Claude review. "
        "It bundles {} read-only source payload(s), but live dispatch stays off."
    ).format(len(packet.get("source_modes") or {}))
    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Agent Runtime Review Packet", "href": "/api/oom-sakkie/agents/runtime-review-packet"}],
        "stale_warnings": [],
        "safety_notes": [
            "Agent runtime review packet is read-only. It does not run specialists, enable dispatch, call specialist LLMs/tools, write farm data, apply runtime changes, create public output, or deploy."
        ],
        "llm_context": {
            "kind": "agent_runtime_review_packet",
            "review_packet": packet,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": packet,
    }


def dispatch_runtime_review_packet_handler(_args):
    packet = get_agent_runtime_review_packet()
    dispatch_status = dispatch_decision_status_handler({})
    status_counts = (dispatch_status.get("llm_context") or {}).get("counts") or {}
    summary = (
        "Dispatch runtime review packet is ready for owner and Claude review. "
        "It combines the locked runtime review packet with dispatch design status: "
        f"{status_counts.get('pending_design_review', 0)} pending design-review request(s), "
        f"{status_counts.get('approved_for_design_review', 0)} approved for design review. "
        "This still does not enable dispatch."
    )
    return {
        "success": bool(packet.get("success")) and bool(dispatch_status.get("success")),
        "status": _combined_status("ok" if packet.get("success") else "unavailable", dispatch_status.get("status")),
        "summary": summary,
        "links": [
            {"label": "Runtime Review Packet", "href": "/api/oom-sakkie/agents/runtime-review-packet"},
            {"label": "Dispatch Requests", "href": "/api/oom-sakkie/dispatch-requests"},
        ],
        "stale_warnings": list(dispatch_status.get("stale_warnings") or []),
        "safety_notes": [
            "Dispatch runtime review packet is read-only. It does not run specialists, enable dispatch, call specialist LLMs/tools, write farm data, apply runtime changes, create public output, patch, deploy, cut over Telegram, or control hardware."
        ],
        "llm_context": {
            "kind": "dispatch_runtime_review_packet",
            "review_packet": packet,
            "dispatch_status": dispatch_status,
            "next_gate": "owner_and_claude_review_before_any_code_consumes_dispatch_decisions",
            "dispatch_enabled": False,
            "runs_specialist_llm": False,
            "runs_specialist_tools": False,
            "writes": False,
            "applies_runtime_change": False,
            "selected_agent": {
                "slug": "gatekeeper",
                "name": "Gatekeeper",
            },
        },
        "raw": {
            "review_packet": packet,
            "dispatch_status": dispatch_status,
        },
    }


def sentinel_dry_run_review_handler(_args):
    catalog = [
        {
            "name": tool.name,
            "risk_level": int(tool.risk_level),
            "requires_confirmation": bool(tool.requires_confirmation),
        }
        for tool in TOOL_REGISTRY.values()
    ]
    review = build_sentinel_dry_run_review(catalog)
    tool_audit = review.get("tool_audit") or {}
    summary = (
        "Sentinel dry-run review: advisory-only rehearsal is allowed, but live specialist dispatch remains locked. "
        "{} read-only tool(s) are visible; {} non-read-only tool(s) and {} confirmation-required tool(s) are outside authority. "
        "Next gate: {}."
    ).format(
        len(tool_audit.get("read_only_tools") or []),
        len(tool_audit.get("non_read_only_tools") or []),
        len(tool_audit.get("requires_confirmation_tools") or []),
        review.get("next_gate", "owner approval"),
    )
    stale_warnings = []
    if tool_audit.get("non_read_only_tools"):
        stale_warnings.append("Sentinel dry-run found non-read-only tools in the catalog; they remain blocked.")
    if tool_audit.get("requires_confirmation_tools"):
        stale_warnings.append("Sentinel dry-run found confirmation-required tools in the catalog; they remain blocked.")

    return {
        "success": True,
        "status": "ok",
        "summary": summary,
        "links": [{"label": "Oom Sakkie Agents", "href": "/api/oom-sakkie/agents"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [
            "Sentinel dry-run review is advisory-only. No specialist was dispatched, no specialist LLM ran, no specialist tool executed, and no write was performed."
        ],
        "llm_context": {
            "kind": "sentinel_dry_run_review",
            "sentinel_review": review,
            "selected_agent": review.get("selected_agent"),
            "runtime_flags": review.get("runtime_flags"),
            "tool_audit": review.get("tool_audit"),
        },
        "raw": review,
    }


def agent_dry_run_status_handler(_args):
    result, status_code = list_agent_dry_run_requests(limit=5)
    requests = result.get("dry_run_requests", []) if isinstance(result, dict) else []
    results_result, results_status_code = list_agent_dry_run_results(limit=5)
    dry_run_results = results_result.get("dry_run_results", []) if isinstance(results_result, dict) else []
    stale_warnings = []
    if status_code != 200:
        stale_warnings.append(f"Agent dry-run request queue is unavailable (status {status_code}).")
    if results_status_code != 200:
        stale_warnings.append(f"Agent dry-run result queue is unavailable (status {results_status_code}).")
    waiting = [
        item for item in requests
        if not (item.get("latest_event") or {}).get("event_type")
    ]
    cancelled = [
        item for item in requests
        if (item.get("latest_event") or {}).get("event_type") == "cancelled"
    ]
    result_waiting = [
        item for item in dry_run_results
        if not (item.get("latest_event") or {}).get("event_type")
    ]
    result_accepted = [
        item for item in dry_run_results
        if (item.get("latest_event") or {}).get("event_type") == "accepted_for_learning"
    ]
    specialist_counts = _agent_dry_run_counts_by_specialist(requests, dry_run_results)
    active_specialists = [
        f"{slug}: {counts['requests']} request(s), {counts['results']} result(s)"
        for slug, counts in sorted(specialist_counts.items())
        if counts["requests"] or counts["results"]
    ]
    summary = (
        "Agent dry-run queue: {} request(s) loaded, {} waiting for manual review, {} cancelled. "
        "{} result(s) loaded, {} waiting for owner review, {} accepted for learning. "
        "{} This is queue status only; no specialist was dispatched."
    ).format(
        len(requests),
        len(waiting),
        len(cancelled),
        len(dry_run_results),
        len(result_waiting),
        len(result_accepted),
        "Specialists in view: {}.".format("; ".join(active_specialists[:6])) if active_specialists else "No specialist-specific queue items are loaded.",
    )
    if status_code != 200 or results_status_code != 200:
        summary = "Agent dry-run queue is unavailable. " + summary

    return {
        "success": status_code == 200 and results_status_code == 200,
        "status": _combined_status(
            result.get("status", "unavailable") if isinstance(result, dict) else "unavailable",
            results_result.get("status", "unavailable") if isinstance(results_result, dict) else "unavailable",
        ),
        "summary": summary,
        "links": [{"label": "Oom Sakkie Agents", "href": "/api/oom-sakkie/agents"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [
            "Agent dry-run status is read-only. No specialist was dispatched, no specialist LLM ran, no specialist tool executed, no runtime change was applied, and no write was performed."
        ],
        "llm_context": {
            "kind": "agent_dry_run_status",
            "counts": {
                "dry_run_requests": len(requests),
                "waiting_for_review": len(waiting),
                "cancelled": len(cancelled),
                "dry_run_results": len(dry_run_results),
                "results_waiting_for_owner_review": len(result_waiting),
                "results_accepted_for_learning": len(result_accepted),
            },
            "specialist_counts": specialist_counts,
            "requests": requests,
            "results": dry_run_results,
            "runtime_flags": {
                "dry_run_enabled": False,
                "dispatch_enabled": False,
                "runs_specialist_llm": False,
                "runs_specialist_tools": False,
                "writes": False,
                "applies_runtime_change": False,
            },
        },
        "raw": {
            "requests": result if isinstance(result, dict) else {},
            "results": results_result if isinstance(results_result, dict) else {},
        },
    }


def _agent_dry_run_counts_by_specialist(requests, dry_run_results):
    counts = {}
    for item in list(requests or []):
        slug = str(item.get("specialist_slug") or "unknown").strip().lower() or "unknown"
        counts.setdefault(slug, {
            "requests": 0,
            "requests_waiting": 0,
            "results": 0,
            "results_waiting": 0,
            "accepted_for_learning": 0,
        })
        counts[slug]["requests"] += 1
        if not (item.get("latest_event") or {}).get("event_type"):
            counts[slug]["requests_waiting"] += 1
    for item in list(dry_run_results or []):
        slug = str(item.get("specialist_slug") or "unknown").strip().lower() or "unknown"
        counts.setdefault(slug, {
            "requests": 0,
            "requests_waiting": 0,
            "results": 0,
            "results_waiting": 0,
            "accepted_for_learning": 0,
        })
        counts[slug]["results"] += 1
        event_type = (item.get("latest_event") or {}).get("event_type")
        if not event_type:
            counts[slug]["results_waiting"] += 1
        if event_type == "accepted_for_learning":
            counts[slug]["accepted_for_learning"] += 1
    return counts


def agent_learning_evidence_handler(_args):
    learning = accepted_agent_learning_snapshot(limit=20)
    status_code = learning["status_code"]
    accepted_count = learning["accepted_count"]
    specialist_summary = _accepted_learning_specialist_summary(learning.get("accepted_by_specialist", {}))
    stale_warnings = []
    if status_code != 200:
        stale_warnings.append(f"Agent learning evidence is unavailable (status {status_code}).")

    if accepted_count:
        first = learning["accepted_results"][0]
        summary = (
            "Agent learning evidence: {} accepted agent result(s) are available{}. "
            "Most recent: {}. This can guide future planning, but no specialist was run and no runtime changed."
        ).format(
            accepted_count,
            specialist_summary,
            (first.get("result_text") or first.get("dry_run_result_id") or "accepted result")[:180],
        )
    elif status_code == 200:
        summary = (
            "Agent learning evidence: no accepted agent dry-run results are available yet. "
            "Accept a result first if you want it to become planning evidence."
        )
    else:
        summary = "Agent learning evidence is unavailable. No specialist was run and no runtime changed."

    return {
        "success": status_code == 200,
        "status": learning["status"],
        "summary": summary,
        "links": [{"label": "Agent Result Queue", "href": "/api/oom-sakkie/agent-dry-run-results"}],
        "stale_warnings": stale_warnings,
        "safety_notes": [
            "Agent learning evidence is read-only. It reads accepted review events only; no specialist was dispatched, no specialist LLM ran, no specialist tool executed, no runtime change was applied, and no write was performed."
        ],
        "llm_context": {
            "kind": "agent_learning_evidence",
            "accepted_count": accepted_count,
            "evidence": learning["evidence"],
            "accepted_by_specialist": learning.get("accepted_by_specialist", {}),
            "runtime_flags": {
                "dry_run_enabled": False,
                "dispatch_enabled": False,
                "runs_specialist_llm": False,
                "runs_specialist_tools": False,
                "writes": False,
                "applies_runtime_change": False,
            },
        },
        "raw": {
            "mode": "accepted_agent_learning_evidence",
            "accepted_results": learning["evidence"],
            "accepted_by_specialist": learning.get("accepted_by_specialist", {}),
            "all_results_count": learning["all_results_count"],
        },
    }


def accepted_agent_learning_snapshot(limit=20):
    results_result, status_code = list_agent_dry_run_results(limit=limit)
    dry_run_results = results_result.get("dry_run_results", []) if isinstance(results_result, dict) else []
    accepted = [
        item for item in dry_run_results
        if (item.get("latest_event") or {}).get("event_type") == "accepted_for_learning"
    ]
    accepted_by_specialist = {}
    for item in accepted:
        slug = str(item.get("specialist_slug") or "unknown").strip().lower() or "unknown"
        accepted_by_specialist[slug] = accepted_by_specialist.get(slug, 0) + 1
    evidence = []
    for item in accepted[:8]:
        latest_event = item.get("latest_event") or {}
        evidence.append({
            "dry_run_result_id": item.get("dry_run_result_id", ""),
            "dry_run_request_id": item.get("dry_run_request_id", ""),
            "specialist_slug": item.get("specialist_slug", ""),
            "result_text": str(item.get("result_text", ""))[:700],
            "findings": list(item.get("findings") or [])[:8],
            "accepted_at": latest_event.get("created_at", ""),
            "accepted_note": latest_event.get("notes", ""),
        })
    return {
        "status_code": status_code,
        "status": results_result.get("status", "unavailable") if isinstance(results_result, dict) else "unavailable",
        "accepted_count": len(accepted),
        "accepted_by_specialist": accepted_by_specialist,
        "accepted_results": accepted,
        "evidence": evidence,
        "all_results_count": len(dry_run_results),
    }


def _accepted_learning_specialist_summary(counts):
    if not counts:
        return ""
    parts = [
        f"{slug}: {count}"
        for slug, count in sorted(counts.items())
        if count
    ]
    return f" ({', '.join(parts)})" if parts else ""


def _system_work_build_stage(item):
    latest_event = item.get("latest_event") or {}
    event_type = latest_event.get("event_type") or ""
    notes = latest_event.get("notes") or ""
    if event_type == "ignored":
        return "closed"
    if event_type == "review_note" and "patch proposal recorded" in notes.lower():
        return "moved_to_patch"
    return "pending"


def _system_work_next_action(pending_build, patch_without_decision, deploy_ready_patch, pending_dispatch_design=None):
    if pending_build:
        first = pending_build[0]
        return f"Open Forge Handoff for {first.get('build_request_id', 'the oldest build request')}."
    if patch_without_decision:
        first = patch_without_decision[0]
        return f"Review patch proposal {first.get('patch_proposal_id', 'waiting for review')}."
    if deploy_ready_patch:
        first = deploy_ready_patch[0]
        return f"Review/apply the approved patch outside the kiosk, run verification, then record a deploy decision for {first.get('patch_proposal_id', 'the approved patch proposal')}."
    if pending_dispatch_design:
        first = pending_dispatch_design[0]
        return f"Review dispatch design request {first.get('dispatch_request_id', 'waiting for review')} with Claude before any runtime code."
    return "No build approval work is waiting in the latest queue snapshot."


def _dispatch_requests_without_decision(dispatch_items):
    return [
        item for item in dispatch_items
        if not (item.get("latest_decision") or {}).get("decision_type")
    ]


def _dispatch_decision_counts(dispatch_items):
    counts = {
        "approved_for_design_review": 0,
        "rejected": 0,
        "deferred": 0,
        "review_note": 0,
    }
    for item in dispatch_items:
        decision_type = (item.get("latest_decision") or {}).get("decision_type")
        if decision_type in counts:
            counts[decision_type] += 1
    return counts


def _dispatch_decision_next_action(pending):
    if pending:
        first = pending[0]
        return f"Review dispatch design request {first.get('dispatch_request_id', 'waiting for review')} with Claude before any runtime code."
    return "No dispatch design request is waiting in the latest queue snapshot."


def _combined_status(*statuses):
    clean = [str(item or "").strip() for item in statuses if str(item or "").strip()]
    if not clean:
        return "unavailable"
    if all(item == "ok" for item in clean):
        return "ok"
    if any(item == "not_configured" for item in clean):
        return "not_configured"
    return "degraded"


def _display_value(value):
    return "--" if value is None or value == "" else value


def _limitation_warnings(result):
    warnings = []
    for value in result.get("limitations", []) if isinstance(result, dict) else []:
        if value:
            warnings.append(str(value))
    return warnings


TOOL_REGISTRY = {
    "sentinel_dry_run_review": OomSakkieTool(
        name="sentinel_dry_run_review",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=sentinel_dry_run_review_handler,
        description="Read-only Sentinel specialist dry-run readiness review. Never dispatches specialists or enables runtime flags.",
    ),
    "agent_dry_run_status": OomSakkieTool(
        name="agent_dry_run_status",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_dry_run_status_handler,
        description="Read-only status of approved specialist dry-run requests. Never dispatches agents.",
    ),
    "agent_learning_evidence": OomSakkieTool(
        name="agent_learning_evidence",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_learning_evidence_handler,
        description="Read-only accepted agent learning evidence. Never applies runtime changes or dispatches agents.",
    ),
    "agent_runtime_readiness": OomSakkieTool(
        name="agent_runtime_readiness",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_runtime_readiness_handler,
        description="Read-only agent runtime readiness checklist. Never enables dispatch, writes, public output, patches, deploys, Telegram, or controls.",
    ),
    "jarvis_product_progress": OomSakkieTool(
        name="jarvis_product_progress",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=jarvis_product_progress_handler,
        description="Read-only product progress report for the Oom Sakkie/Jarvis build. Never enables authority.",
    ),
    "agent_command_center": OomSakkieTool(
        name="agent_command_center",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_command_center_handler,
        description="Read-only Agent Command Center status. Shows lanes, queues, and locked gates without dispatching agents or enabling authority.",
    ),
    "jarvis_daily_command_brief": OomSakkieTool(
        name="jarvis_daily_command_brief",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=jarvis_daily_command_brief_handler,
        description="Read-only daily command brief across farm operations, business growth, and the agent command center. Never dispatches agents or performs actions.",
    ),
    "agent_operating_contracts": OomSakkieTool(
        name="agent_operating_contracts",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_operating_contracts_handler,
        description="Read-only planned-agent operating contracts. Lists focus, allowed read-only tools, must-not-do rules, and owner gates without dispatching agents.",
    ),
    "agent_activation_preflight": OomSakkieTool(
        name="agent_activation_preflight",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_activation_preflight_handler,
        description="Read-only activation preflight for planned Oom Sakkie agents. Summarizes pass/manual/locked gates without enabling runtime authority.",
    ),
    "agent_authority_matrix": OomSakkieTool(
        name="agent_authority_matrix",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_authority_matrix_handler,
        description="Read-only matrix of future agent authority areas, locked status, risk levels, and required gates. Never enables authority.",
    ),
    "agent_authority_unlock_readiness": OomSakkieTool(
        name="agent_authority_unlock_readiness",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_authority_unlock_readiness_handler,
        description="Read-only planning report for which locked authority area would be lowest-risk to design later. Never unlocks authority.",
    ),
    "agent_dispatch_decision_rail_blueprint": OomSakkieTool(
        name="agent_dispatch_decision_rail_blueprint",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_dispatch_decision_rail_blueprint_handler,
        description="Read-only blueprint for a future append-only specialist dispatch decision rail. Never enables dispatch or runs agents.",
    ),
    "dispatch_decision_status": OomSakkieTool(
        name="dispatch_decision_status",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=dispatch_decision_status_handler,
        description="Read-only status of append-only dispatch design requests and decisions. Never dispatches specialists or enables runtime flags.",
    ),
    "agent_runtime_review_packet": OomSakkieTool(
        name="agent_runtime_review_packet",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_runtime_review_packet_handler,
        description="Read-only bulk review packet for the agent runtime foundation. Bundles inspection surfaces without enabling authority.",
    ),
    "dispatch_runtime_review_packet": OomSakkieTool(
        name="dispatch_runtime_review_packet",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=dispatch_runtime_review_packet_handler,
        description="Read-only owner/Claude review packet combining locked runtime review with dispatch design status. Never consumes dispatch decisions to enable runtime.",
    ),
    "agent_activation_plan": OomSakkieTool(
        name="agent_activation_plan",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_activation_plan_handler,
        description="Read-only activation ladder for planned Oom Sakkie agents. Never enables dispatch.",
    ),
    "agent_crew_brief": OomSakkieTool(
        name="agent_crew_brief",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_crew_brief_handler,
        description="Read-only multi-agent crew plan. Shows which planned specialists would work together; never dispatches agents.",
    ),
    "agent_crew_status": OomSakkieTool(
        name="agent_crew_status",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=agent_crew_status_handler,
        description="Read-only agent crew status and recommendation-only specialist routing. Never dispatches agents.",
    ),
    "system_work_status": OomSakkieTool(
        name="system_work_status",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=system_work_status_handler,
        description="Read-only status of Oom Sakkie build, patch, and deploy approval queues.",
    ),
    "farm_operating_brief": OomSakkieTool(
        name="farm_operating_brief",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=farm_operating_brief_handler,
        description="Read-only combined operating brief across attention, power, weather, and irrigation.",
    ),
    "business_growth_brief": OomSakkieTool(
        name="business_growth_brief",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=business_growth_brief_handler,
        description="Read-only business growth brief across sales stock and meat pipeline. Never drafts, posts, sells, or sends messages.",
    ),
    "farm_attention_summary": OomSakkieTool(
        name="farm_attention_summary",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=farm_attention_summary_handler,
        description="Read-only farm attention summary.",
    ),
    "power_current": OomSakkieTool(
        name="power_current",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=power_current_handler,
        description="Read-only current power state.",
    ),
    "power_recent": OomSakkieTool(
        name="power_recent",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=power_recent_handler,
        description="Read-only recent 24-hour power profile.",
    ),
    "weather_now": OomSakkieTool(
        name="weather_now",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=weather_now_handler,
        description="Read-only current weather state.",
    ),
    "weather_today": OomSakkieTool(
        name="weather_today",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=weather_today_handler,
        description="Read-only weather summary for today.",
    ),
    "weather_forecast": OomSakkieTool(
        name="weather_forecast",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=weather_forecast_handler,
        description="Read-only weather forecast.",
    ),
    "irrigation_status": OomSakkieTool(
        name="irrigation_status",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=irrigation_status_handler,
        description="Read-only irrigation status. Never starts or stops irrigation.",
    ),
    "dashboard_summary": OomSakkieTool(
        name="dashboard_summary",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=dashboard_summary_handler,
        description="Read-only farm dashboard overview.",
    ),
    "pig_allocation_readiness": OomSakkieTool(
        name="pig_allocation_readiness",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=pig_allocation_readiness_handler,
        description="Read-only pig allocation and outlet readiness.",
    ),
    "meat_planning": OomSakkieTool(
        name="meat_planning",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=meat_planning_handler,
        description="Read-only meat pipeline planning.",
    ),
    "sales_dashboard": OomSakkieTool(
        name="sales_dashboard",
        input_schema=_empty_object_schema(),
        output_schema=_tool_output_schema(),
        risk_level=RiskLevel.READ_ONLY,
        requires_confirmation=False,
        handler=sales_dashboard_handler,
        description="Read-only sales stock dashboard.",
    ),
}


def get_tool(name):
    return TOOL_REGISTRY.get(str(name or "").strip())


def list_tool_catalog():
    catalog = []
    for tool in TOOL_REGISTRY.values():
        catalog.append({
            "name": tool.name,
            "description": tool.description,
            "risk_level": int(tool.risk_level),
            "risk_label": tool.risk_level.name,
            "requires_confirmation": bool(tool.requires_confirmation),
            "input_schema": tool.input_schema,
            "output_schema": tool.output_schema,
        })
    return catalog
