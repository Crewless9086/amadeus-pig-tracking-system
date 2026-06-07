from dataclasses import dataclass
from enum import IntEnum
from typing import Any, Callable

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


def _display_value(value):
    return "--" if value is None or value == "" else value


def _limitation_warnings(result):
    warnings = []
    for value in result.get("limitations", []) if isinstance(result, dict) else []:
        if value:
            warnings.append(str(value))
    return warnings


TOOL_REGISTRY = {
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
