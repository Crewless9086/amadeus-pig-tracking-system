from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

from modules.oom_sakkie.build_request_store import list_build_requests
from modules.oom_sakkie.deploy_decision_store import list_deploy_decisions
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
    stock_total = sum(float(item.get("qty_available") or 0) for item in sales_totals)
    ready_now = int(meat_summary.get("ready_now") or 0)
    next_14 = int(meat_summary.get("next_14_days") or 0)
    focus = _business_growth_focus(stock_total, ready_now, next_14)
    summary = (
        "Business advisor brief: "
        f"{focus} Sales stock shows {int(stock_total)} available pig(s). "
        f"Meat planning shows {ready_now} ready now and {next_14} due in the next 14 days."
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
            "sales_summary": sections["sales"].get("summary"),
            "meat_summary": sections["meat"].get("summary"),
            "counts": {
                "available_sales_stock": int(stock_total),
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

    statuses = {
        "build_requests": build_status,
        "patch_proposals": patch_status,
        "deploy_decisions": deploy_status,
    }
    configured = all(
        result.get("configured", True)
        for result in (build_result, patch_result, deploy_result)
        if isinstance(result, dict)
    )
    build_items = build_result.get("build_requests", []) if isinstance(build_result, dict) else []
    patch_items = patch_result.get("patch_proposals", []) if isinstance(patch_result, dict) else []
    deploy_items = deploy_result.get("deploy_decisions", []) if isinstance(deploy_result, dict) else []
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

    if not configured:
        summary = "System work status is not configured in this process. The approval tables may still be available in the running kiosk environment."
        status = "not_configured"
    else:
        summary = (
            "System work status: "
            f"{len(pending_build)} item(s) need Forge Handoff or a Builder plan, "
            f"{len(patch_without_decision)} patch proposal(s) need approve/reject review, "
            f"and {len(deploy_ready_patch)} approved patch proposal(s) need verification plus a deploy decision."
        )
        status = "ok"

    return {
        "success": configured,
        "status": status,
        "summary": summary,
        "links": [{"label": "Oom Sakkie Workbench", "href": "/oom-sakkie"}],
        "stale_warnings": [],
        "safety_notes": ["System work status is read-only. No build, patch, or deploy was run."],
        "llm_context": {
            "kind": "system_work_status",
            "counts": {
                "build_requests": len(build_items),
                "patch_proposals": len(patch_items),
                "deploy_decisions": len(deploy_items),
                "pending_build_requests": len(pending_build),
                "patch_proposals_without_decision": len(patch_without_decision),
                "approved_patch_proposals": len(approved_patch),
                "deploy_ready_patch_proposals": len(deploy_ready_patch),
            },
            "statuses": statuses,
            "next_action": _system_work_next_action(pending_build, patch_without_decision, deploy_ready_patch),
        },
        "raw": {
            "build_requests": build_result,
            "patch_proposals": patch_result,
            "deploy_decisions": deploy_result,
            "statuses": statuses,
        },
}


def _system_work_build_stage(item):
    latest_event = item.get("latest_event") or {}
    event_type = latest_event.get("event_type") or ""
    notes = latest_event.get("notes") or ""
    if event_type == "ignored":
        return "closed"
    if event_type == "review_note" and "patch proposal recorded" in notes.lower():
        return "moved_to_patch"
    return "pending"


def _system_work_next_action(pending_build, patch_without_decision, deploy_ready_patch):
    if pending_build:
        first = pending_build[0]
        return f"Open Forge Handoff for {first.get('build_request_id', 'the oldest build request')}."
    if patch_without_decision:
        first = patch_without_decision[0]
        return f"Review patch proposal {first.get('patch_proposal_id', 'waiting for review')}."
    if deploy_ready_patch:
        first = deploy_ready_patch[0]
        return f"Review/apply the approved patch outside the kiosk, run verification, then record a deploy decision for {first.get('patch_proposal_id', 'the approved patch proposal')}."
    return "No build approval work is waiting in the latest queue snapshot."


def _display_value(value):
    return "--" if value is None or value == "" else value


def _limitation_warnings(result):
    warnings = []
    for value in result.get("limitations", []) if isinstance(result, dict) else []:
        if value:
            warnings.append(str(value))
    return warnings


TOOL_REGISTRY = {
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
