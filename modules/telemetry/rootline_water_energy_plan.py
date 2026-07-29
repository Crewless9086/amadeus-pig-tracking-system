"""Canonical, command-inert ROOTLINE Water & Energy Plan.

The service combines existing read models into owner advice and can append an
immutable advisory generation. It contains no network client, scheduler,
device transport, retry, SmartLife, SONOFF, IFTTT, n8n, or hardware consumer.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from hashlib import sha256
import json
import os
from zoneinfo import ZoneInfo

from services.database_service import DATABASE_URL_ENV


ZA_TZ = ZoneInfo("Africa/Johannesburg")
UNKNOWN = "Unknown"
UNAVAILABLE = "Unavailable"
PLAN_PREFIX = "ROOTLINE-WEP"

AUTHORITY = {
    "writes_performed": False,
    "creates_irrigation_plan": False,
    "creates_command": False,
    "mutates_schedule": False,
    "activates_workflow": False,
    "calls_smartlife": False,
    "calls_sonoff": False,
    "calls_ifttt": False,
    "calls_n8n": False,
    "controls_hardware": False,
    "automatic_retry": False,
}

OPERATING_KNOWLEDGE = {
    "energy": {
        "absolute_discretionary_floor_soc_pct": 40,
        "approximate_inverter_grid_support_soc_pct": 30,
        "provisional_working_reserve_soc_pct": 50,
        "learned_reserve_candidates_pct": {
            "sunny": 63,
            "mixed": 67,
            "poor": 70,
            "uncertain": 70,
        },
        "grid_policy": "minimum_avoidable_cost_not_absolute_prohibition",
        "provisional_tariff": {
            "zar_per_kwh": 9.0,
            "purchase_zar": 2000,
            "estimated_kwh_range": [211, 222],
            "status": "owner_supplied_provisional",
        },
    },
    "water_topology": {
        "storage": {
            "tank_count": 5,
            "litres_each": 5500,
            "sources": ["borehole", "roof_rainwater"],
            "full_sensor_controller": True,
            "borehole_stop_when_full": True,
        },
        "reservoir": {
            "tank_count": 12,
            "litres_each": 5500,
            "source": "solar_transfer_pump_from_storage",
            "overflow_destination": "storage",
        },
        "borehole": {
            "overnight_allowed": True,
            "noise_restriction": False,
            "internal_controller_owns": ["dry_run", "pressure", "protective_shutdown"],
            "rootline_future_boundary": "upstream_smart_plug_only",
            "integration": "SmartLife",
            "protected_device_identity": UNKNOWN,
        },
        "solar_transfer_pump": {"control_identity": UNKNOWN},
    },
    "fertilizer": {
        "manufacturer": "SONOFF",
        "model": "4CHPRO R3",
        "device_id": "100204d497",
        "controller_name": "Controller (1) Right",
        "channels": {
            "1": "Kunsmis In",
            "2": "Kunsmis Meng",
            "3": "unused",
            "4": "unused",
        },
        "product": "owner-produced natural liquid fertilizer",
        "ingredients": ["LAB", "earthworm tea", "leaf mulch", "weeds"],
        "minimum_irrigation_preflow_minutes": 10,
        "maximum_injection_pulse_seconds": 60,
        "minimum_pulse_spacing_minutes": 10,
        "clean_water_flush_required": True,
        "mixing_candidate": "twice_daily_approximately_15_minutes",
        "relay_api_mapping": UNKNOWN,
        "deterministic_off_proven": False,
        "supervised_identity_proven": False,
    },
}


def plan_identity(operating_date):
    compact = str(operating_date).replace("-", "")
    return f"{PLAN_PREFIX}-{compact}"


def build_water_energy_plan(evidence, operating_date=None, now=None):
    now = _as_za(now or datetime.now(timezone.utc))
    selected_date = str(operating_date or now.date().isoformat())[:10]
    evidence = deepcopy(evidence if isinstance(evidence, dict) else {})
    power = _dict(evidence.get("power"))
    forecast = _dict(evidence.get("forecast"))
    weather = _dict(evidence.get("weather"))
    tanks = _dict(evidence.get("tanks"))
    irrigation = _dict(evidence.get("irrigation"))
    history = _dict(evidence.get("history"))
    water_demand = _dict(evidence.get("water_demand"))

    power_state = _freshness(power, now)
    weather_state = _freshness(weather, now)
    forecast_state = _freshness(forecast, now)
    tank_state = _tank_freshness(tanks, now)
    solar_profile, forecast_confidence = _forecast_profile(forecast, forecast_state)
    reserve = _reserve(power, power_state, solar_profile, forecast_confidence)
    rain = _rain_effect(weather, weather_state, forecast, forecast_state)

    tasks = [
        _borehole_task(tanks, tank_state, water_demand, rain, reserve),
        _transfer_task(tanks, tank_state, water_demand, reserve),
        *_irrigation_tasks(irrigation, reserve, rain),
        _fertilizer_injection_task(irrigation),
        _fertilizer_mixing_task(tanks, tank_state, reserve),
    ]
    status = _overall_status(tasks)
    evidence_observed_at = _latest_observed_at(power, weather, forecast, tanks, now)
    canonical_evidence = {
        "power": power,
        "weather": weather,
        "forecast": forecast,
        "tanks": tanks,
        "irrigation": irrigation,
        "history": history,
        "water_demand": water_demand,
    }
    evidence_hash = _canonical_sha(_material_evidence(canonical_evidence, now))
    plan = {
        "success": True,
        "status": status,
        "mode": "owner_only_advisory_command_inert",
        "calculation_version": "rootline_water_energy_plan_v1",
        "plan_id": plan_identity(selected_date),
        "operating_date": selected_date,
        "operating_timezone": "Africa/Johannesburg",
        "generation": None,
        "evidence_generation": evidence_hash[:16].upper(),
        "evidence_sha256": evidence_hash,
        "evidence_observed_at": evidence_observed_at,
        "replacement_reason": "material_evidence_changed",
        "executive_summary": _summary(tasks, reserve, rain),
        "oom_sakkie_summary": _summary(tasks, reserve, rain),
        "current_power": {
            "status": power_state,
            "observed_at": power.get("observed_at"),
            "age_minutes": _age_minutes(power, now),
            "battery_soc_pct": power.get("battery_soc_pct"),
            "solar_power_w": power.get("solar_power_w"),
            "load_power_w": power.get("load_power_w"),
            "grid_power_w": power.get("grid_power_w"),
        },
        "historical_context": history or {
            "status": UNAVAILABLE,
            "limitations": ["Historical context reader unavailable."],
        },
        "forecast": {
            "status": forecast_state,
            "confidence": forecast_confidence,
            "solar_profile": solar_profile,
            "forecast_dependent_optimization": (
                "Available" if forecast_state == "fresh" else UNAVAILABLE
            ),
        },
        "rain_capture": rain,
        "battery_reserve": reserve,
        "tank_evidence": {
            "status": tank_state,
            "storage_reported_count": tanks.get("storage_reported_count"),
            "storage_state": tanks.get("storage_state", UNKNOWN),
            "storage_total_count": 5,
            "reservoir_reported_count": tanks.get("reservoir_reported_count"),
            "reservoir_state": tanks.get("reservoir_state", UNKNOWN),
            "reservoir_total_count": 12,
            "observed_at": tanks.get("observed_at"),
            "reporter": tanks.get("reporter"),
            "source": tanks.get("source"),
            "age_minutes": _age_minutes(tanks, now),
            "litres_inferred": False,
        },
        "water_demand": water_demand or {"status": UNAVAILABLE},
        "candidate_tasks": tasks,
        "outcome_separation": {
            "plan": "advice_only",
            "command_acceptance": "separate_future_evidence",
            "electrical_operation": "separate_observation",
            "physical_water_flow": "separate_observation",
            "delivered_volume": UNAVAILABLE,
        },
        "estimated_grid_exposure": _grid_exposure(tasks, reserve),
        "operating_knowledge": deepcopy(OPERATING_KNOWLEDGE),
        "evidence_gaps": _evidence_gaps(forecast_state, tank_state, tasks),
        "authority": deepcopy(AUTHORITY),
    }
    return plan


def get_current_water_energy_plan(operating_date=None, database_url=None):
    selected = str(operating_date or datetime.now(ZA_TZ).date().isoformat())[:10]
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _unavailable("database_not_configured", selected), 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select g.plan_json, g.generation, g.evidence_sha256,
                           g.evidence_observed_at, g.replacement_reason
                      from public.rootline_water_energy_plan_identities i
                      join public.rootline_water_energy_plan_generations g
                        on g.plan_id=i.plan_id and g.generation=i.current_generation
                     where i.operating_date=%s
                    """,
                    (selected,),
                )
                row = cursor.fetchone()
    except Exception as exc:
        return _unavailable("water_energy_schema_unavailable", selected, exc), 200
    if not row:
        return _unavailable("no_current_water_energy_plan", selected), 200
    plan = dict(row[0])
    plan.update(
        generation=row[1],
        evidence_sha256=row[2],
        evidence_observed_at=row[3].isoformat(),
        replacement_reason=row[4],
    )
    plan["authority"] = deepcopy(AUTHORITY)
    return plan, 200


def get_oom_sakkie_water_energy_summary(operating_date=None, database_url=None):
    """Return the same protected plan as a small read-only practical summary."""
    plan, status = get_current_water_energy_plan(operating_date, database_url)
    if plan.get("success") is not True:
        return plan, status
    return {
        "success": True,
        "plan_id": plan.get("plan_id"),
        "generation": plan.get("generation"),
        "operating_date": plan.get("operating_date"),
        "summary": plan.get("oom_sakkie_summary"),
        "reserve": plan.get("battery_reserve"),
        "rain": plan.get("rain_capture"),
        "tasks": plan.get("candidate_tasks", []),
        "evidence_gaps": plan.get("evidence_gaps", []),
        "authority": deepcopy(AUTHORITY),
    }, 200


def build_current_water_energy_plan(operating_date=None, database_url=None, now=None):
    """Read supported evidence and build an in-memory advisory candidate."""
    evidence, selected, now = read_current_water_energy_evidence(
        operating_date=operating_date,
        database_url=database_url,
        now=now,
    )
    return build_water_energy_plan(evidence, selected, now=now)


def read_current_water_energy_evidence(
    operating_date=None, database_url=None, now=None
):
    """Read canonical ROOTLINE evidence without persisting a plan or observation."""
    from modules.telemetry.power_service import get_current_power_state
    from modules.telemetry.weather_service import (
        get_current_weather_state,
        get_weather_forecast,
    )
    from modules.telemetry.rootline_daily_advisor import get_rootline_daily_advisor

    now = _as_za(now or datetime.now(timezone.utc))
    selected = str(operating_date or now.date().isoformat())[:10]
    power_packet, _ = get_current_power_state(database_url=database_url)
    weather_packet, _ = get_current_weather_state(database_url=database_url)
    forecast_packet, _ = get_weather_forecast(days=3, database_url=database_url)
    advisor, _ = get_rootline_daily_advisor(selected, now=now)
    evidence = {
        "power": _normalize_power(power_packet),
        "weather": _normalize_weather(weather_packet),
        "forecast": _normalize_forecast(forecast_packet),
        "irrigation": {
            "zones": deepcopy(advisor.get("zones", [])),
            "active_zone": None,
            "source": "rootline_daily_advisor",
        },
        "history": _read_historical_context(database_url),
        "tanks": _read_latest_tank_observation(database_url),
        "water_demand": {"status": UNAVAILABLE},
    }
    return evidence, selected, now


def append_water_energy_plan(plan, actor_identity, database_url=None):
    if not actor_identity:
        return {"success": False, "status": "owner_identity_required"}, 403
    if not _safe_plan(plan):
        return {"success": False, "status": "unsafe_or_invalid_plan"}, 400
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"success": False, "status": "database_not_configured"}, 503
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select created, superseded_generation, generation
                      from public.rootline_append_water_energy_plan(
                        %s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s
                      )
                    """,
                    (
                        plan["plan_id"], plan["operating_date"],
                        plan["evidence_sha256"], plan["evidence_observed_at"],
                        plan["replacement_reason"], plan["status"],
                        json.dumps(_plan_evidence(plan), sort_keys=True),
                        json.dumps(plan, sort_keys=True), actor_identity,
                    ),
                )
                created, superseded, generation = cursor.fetchone()
        result = deepcopy(plan)
        result.update(
            generation=generation,
            created=created,
            superseded_generation=superseded,
            writes_performed=bool(created),
        )
        result["authority"] = deepcopy(AUTHORITY)
        return result, 201 if created else 200
    except Exception as exc:
        return {
            "success": False,
            "status": "water_energy_plan_append_failed",
            "error_type": exc.__class__.__name__,
            "authority": deepcopy(AUTHORITY),
        }, 503


def record_tank_observation(payload, actor_identity, database_url=None):
    payload = payload if isinstance(payload, dict) else {}
    if not actor_identity:
        return {"success": False, "status": "owner_identity_required"}, 403
    try:
        storage = _optional_count(payload.get("storage_reported_count"), 5)
        reservoir = _optional_count(payload.get("reservoir_reported_count"), 12)
        storage_state = _tank_state(payload.get("storage_state"))
        reservoir_state = _tank_state(payload.get("reservoir_state"))
        if storage is None and reservoir is None:
            raise ValueError("one_count_required")
        observed = datetime.fromisoformat(str(payload["observed_at"]).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("observed_at_timezone_required")
        if observed.astimezone(timezone.utc) > datetime.now(timezone.utc):
            raise ValueError("future_observation_prohibited")
        source = str(payload.get("source") or "owner_dashboard")
        if source not in {"owner_dashboard", "oom_sakkie_owner"}:
            raise ValueError("invalid_source")
        key = str(payload.get("idempotency_key") or "").strip()
        if not key:
            raise ValueError("idempotency_key_required")
    except (KeyError, TypeError, ValueError) as exc:
        return {"success": False, "status": str(exc)}, 400
    identity = "ROOTLINE-TANK-" + sha256(key.encode()).hexdigest()[:24].upper()
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.rootline_tank_observations (
                      observation_id,idempotency_key,storage_reported_count,
                      reservoir_reported_count,storage_state,reservoir_state,
                      observed_at,reporter_identity,source
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (idempotency_key) do nothing
                    returning observation_id
                    """,
                    (identity, key, storage, reservoir, storage_state,
                     reservoir_state, observed, actor_identity, source),
                )
                created = cursor.fetchone() is not None
                cursor.execute(
                    """select observation_id,storage_reported_count,reservoir_reported_count,
                              storage_state,reservoir_state,observed_at,
                              reporter_identity,source
                         from public.rootline_tank_observations
                        where idempotency_key=%s""",
                    (key,),
                )
                row = cursor.fetchone()
        expected_observed = observed.astimezone(timezone.utc)
        actual_observed = row[5].astimezone(timezone.utc)
        if (
            row[1] != storage or row[2] != reservoir
            or row[3] != storage_state or row[4] != reservoir_state
            or actual_observed != expected_observed
            or row[6] != actor_identity or row[7] != source
        ):
            return {
                "success": False,
                "status": "tank_observation_idempotency_conflict",
                "observation_id": row[0],
                "hardware_control_performed": False,
            }, 409
        return {
            "success": True, "status": "recorded" if created else "exact_replay",
            "created": created, "observation_id": row[0],
            "storage_reported_count": row[1], "reservoir_reported_count": row[2],
            "storage_state": row[3], "reservoir_state": row[4],
            "observed_at": row[5].isoformat(), "reporter": row[6], "source": row[7],
            "litres_inferred": False, "hardware_control_performed": False,
        }, 201 if created else 200
    except Exception as exc:
        return {"success": False, "status": "tank_observation_write_failed",
                "error_type": exc.__class__.__name__}, 503


def _reserve(power, power_state, profile, confidence):
    learned = OPERATING_KNOWLEDGE["energy"]["learned_reserve_candidates_pct"]
    candidate = learned.get(profile, 70) if confidence != UNAVAILABLE else 70
    governing = max(50, candidate)
    soc = _number(power.get("battery_soc_pct"))
    return {
        "absolute_floor_soc_pct": 40,
        "provisional_working_reserve_soc_pct": 50,
        "learned_candidate_soc_pct": candidate,
        "governing_reserve_soc_pct": governing,
        "governing_reason": (
            f"{profile or 'uncertain'} forecast profile; protect historical overnight depletion"
        ),
        "current_soc_pct": soc,
        "discretionary_battery_energy_available": (
            soc is not None and power_state == "fresh" and soc > governing
        ),
        "power_evidence_status": power_state,
        "below_absolute_floor": soc is not None and soc < 40,
    }


def _normalize_power(packet):
    if not isinstance(packet, dict) or packet.get("success") is not True:
        return {}
    current = _dict(packet.get("current"))
    source = _dict(packet.get("source"))
    return {
        "observed_at": source.get("last_reading_at"),
        "stale_after_minutes": source.get("stale_after_minutes", 15),
        "battery_soc_pct": current.get("battery_soc_pct"),
        "solar_power_w": current.get("solar_power_w"),
        "load_power_w": current.get("load_power_w"),
        "grid_power_w": current.get("grid_power_w"),
        "grid_state": current.get("grid_state"),
        "status": packet.get("status"),
    }


def _normalize_weather(packet):
    if not isinstance(packet, dict) or packet.get("success") is not True:
        return {}
    current = _dict(packet.get("current"))
    source = _dict(packet.get("source"))
    return {
        "observed_at": source.get("last_reading_at"),
        "stale_after_minutes": source.get("stale_after_minutes", 30),
        "rain_rate_mm_h": current.get("rain_rate_mm_h"),
        "rain_today_mm": current.get("rain_today_mm"),
        "temperature_c": current.get("temperature_c"),
        "wind_speed_kmh": current.get("wind_speed_kmh"),
        "status": packet.get("status"),
    }


def _normalize_forecast(packet):
    if not isinstance(packet, dict) or packet.get("success") is not True:
        return {}
    source = _dict(packet.get("source"))
    return {
        "observed_at": source.get("last_forecast_run_at")
            or source.get("forecast_run_at") or source.get("last_reading_at"),
        "stale_after_minutes": source.get("stale_after_minutes", 360),
        "days": deepcopy(packet.get("days", [])),
        "status": packet.get("status"),
    }


def _read_historical_context(database_url):
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"status": UNAVAILABLE}
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select count(*)::int, round(avg(coverage_pct),1),
                           round(sum(estimated_grid_import_kwh),2),
                           round(sum(estimated_grid_import_kwh*tariff_zar_per_kwh),2)
                      from public.power_daily_rollups
                     where source_id='sunsynk-main-inverter'
                    """
                )
                days, coverage, grid_kwh, schema_cost = cursor.fetchone()
        return {
            "status": "Available" if days else UNAVAILABLE,
            "daily_rollup_count": days,
            "average_coverage_pct": _number(coverage),
            "estimated_grid_import_kwh": _number(grid_kwh),
            "estimated_grid_cost_at_schema_tariff_zar": _number(schema_cost),
            "owner_provisional_tariff_zar_per_kwh": 9.0,
            "overnight_soc_depletion_median_points": 27,
            "overnight_soc_depletion_p25_p75_points": [22.8, 30.0],
            "solar_surplus_candidate_window": "10:00-15:00 SAST",
            "energy_method": "five_minute_sample_integration_estimated",
            "confidence": "medium",
        }
    except Exception as exc:
        return {"status": UNAVAILABLE, "error_type": exc.__class__.__name__}


def _read_latest_tank_observation(database_url):
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {}
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select storage_reported_count,reservoir_reported_count,
                           storage_state,reservoir_state,observed_at,
                           reporter_identity,source
                      from public.rootline_tank_observations
                     order by observed_at desc,recorded_at desc limit 1
                    """
                )
                row = cursor.fetchone()
        if not row:
            return {}
        return {
            "storage_reported_count": row[0],
            "reservoir_reported_count": row[1],
            "storage_state": row[2],
            "reservoir_state": row[3],
            "observed_at": row[4].isoformat(),
            "reporter": row[5],
            "source": row[6],
        }
    except Exception:
        return {}


def _forecast_profile(forecast, state):
    if state != "fresh":
        return "uncertain", UNAVAILABLE
    days = forecast.get("days") if isinstance(forecast.get("days"), list) else []
    if not days:
        return "uncertain", UNAVAILABLE
    first = _dict(days[0])
    rain = _number(first.get("rain_sum_mm"))
    probability = _number(first.get("rain_probability_max_pct"))
    if rain is None or probability is None:
        return "uncertain", "low"
    if rain >= 5 or probability >= 70:
        return "poor", "medium"
    if rain == 0 and probability <= 20:
        return "sunny", "medium"
    return "mixed", "medium"


def _rain_effect(weather, weather_state, forecast, forecast_state):
    current = _number(weather.get("rain_rate_mm_h"))
    live = weather_state == "fresh" and current is not None and current > 0.2
    days = forecast.get("days") if isinstance(forecast.get("days"), list) else []
    first = _dict(days[0]) if days else {}
    forecast_rain = _number(first.get("rain_sum_mm"))
    probability = _number(first.get("rain_probability_max_pct"))
    credible_forecast_rain = (
        forecast_state == "fresh"
        and forecast_rain is not None and probability is not None
        and (forecast_rain >= 5 or probability >= 70)
    )
    dry_release_proven = (
        weather_state == "fresh" and current == 0
        and weather.get("dry_interval_minutes", 0) >= 30
        and weather.get("fresh_readings_during_dry_interval", 0) >= 2
        and weather.get("no_visible_rain_confirmed") is True
        and weather.get("owner_review_confirmed") is True
    )
    rain_hold_state = (
        "active" if live else "released" if dry_release_proven else UNKNOWN
    )
    return {
        "current_rain_status": "Hold" if live else (
            "no_live_rain_threshold" if weather_state == "fresh" else "Needs Data"
        ),
        "fresh_rain_rate_mm_h": current if weather_state == "fresh" else None,
        "rain_hold_state": rain_hold_state,
        "dry_release_proven": dry_release_proven,
        "forecast_status": forecast_state,
        "forecast_replenishment_effect": (
            "meaningful_rain_candidate" if credible_forecast_rain
            else "no_meaningful_rain_signal" if forecast_state == "fresh"
            else UNAVAILABLE
        ),
        "forecast_rain_sum_mm": forecast_rain if forecast_state == "fresh" else None,
        "forecast_rain_probability_pct": probability if forecast_state == "fresh" else None,
        "borehole_avoidance_signal": live or credible_forecast_rain,
        "roof_capture_volume_litres": UNAVAILABLE,
    }


def _borehole_task(tanks, tank_state, demand, rain, reserve):
    urgent = demand.get("status") == "urgent"
    storage = tanks.get("storage_reported_count")
    if rain["borehole_avoidance_signal"] and not urgent:
        rec, reason = "Do Not Run", (
            "Fresh live rain; avoid unnecessary borehole pumping."
            if rain["current_rain_status"] == "Hold"
            else "Fresh credible forecast indicates meaningful roof-capture rain."
        )
    elif tank_state == "stale" or storage is None:
        rec, reason = "Needs Data", "Fresh storage count is unavailable."
    elif tanks.get("storage_state") == "FULL" and not urgent:
        rec, reason = "Do Not Run", "Storage was explicitly observed FULL."
    elif rain["rain_hold_state"] == UNKNOWN and not urgent:
        rec, reason = "Hold", "Rain-hold release evidence is incomplete."
    elif urgent:
        rec, reason = "Recommend", "Urgent water continuity can justify grid exposure."
    else:
        rec, reason = "Hold", "Water need is not proven."
    return _task("borehole", rec, reason, "overnight_or_surplus_solar", [
        "fresh_storage_observation", "genuine_water_need",
        "SmartLife_device_binding_unresolved",
    ], reserve)


def _transfer_task(tanks, tank_state, demand, reserve):
    storage = tanks.get("storage_reported_count")
    reservoir = tanks.get("reservoir_reported_count")
    if tank_state == "stale" or storage is None or reservoir is None:
        rec, reason = "Needs Data", "Fresh storage and reservoir counts are required."
    elif tanks.get("reservoir_state") == "FULL":
        rec, reason = "Do Not Run", "Reservoir storage was explicitly observed FULL."
    elif storage <= 0:
        rec, reason = "Hold", "No active storage supply is reported."
    elif demand.get("status") in {"needed", "urgent"}:
        rec, reason = "Recommend", "Reservoir demand exists; prefer direct surplus solar."
    else:
        rec, reason = "Hold", "Transfer demand is not proven."
    return _task("solar_transfer_pump", rec, reason, "10:00-15:00 SAST candidate", [
        "fresh_storage_observation", "fresh_reservoir_observation",
        "control_identity_unresolved",
    ], reserve)


def _irrigation_tasks(irrigation, reserve, rain):
    zones = irrigation.get("zones") if isinstance(irrigation.get("zones"), list) else []
    result = []
    for zone in zones:
        zone = _dict(zone)
        rec = str(zone.get("recommendation") or "Needs Data")
        if rain["rain_hold_state"] != "released":
            rec = "Hold"
        result.append(_task(
            f"irrigation_{zone.get('zone_id') or 'unknown'}", rec,
            "Daily Advisor evidence; runtime remains separate and may be Unavailable.",
            "08:00-17:00 SAST advice window",
            ["one_zone_at_a_time", "runtime_policy", "fresh_weather"], reserve,
        ))
    if not result:
        result.append(_task("irrigation", "Needs Data", "Zone advice unavailable.",
                            "Unavailable", ["daily_advisor"], reserve))
    return result


def _fertilizer_injection_task(irrigation):
    active = irrigation.get("active_zone")
    elapsed = _number(irrigation.get("active_zone_observed_minutes"))
    spacing = _number(irrigation.get("minutes_since_last_injection"))
    flush = irrigation.get("clean_water_flush_supported") is True
    compatibility = irrigation.get("exact_product_zone_compatibility_confirmed") is True
    no_overlap = irrigation.get("no_overlapping_fertilizer_pulse") is True
    flush_minutes = _number(irrigation.get("remaining_clean_water_flush_minutes"))
    if not active:
        rec, reason = "Do Not Run", "No compatible active irrigation zone."
    elif elapsed is None or elapsed < 10:
        rec, reason = "Hold", "At least 10 observed pre-flow minutes are required."
    elif not compatibility or not no_overlap:
        rec, reason = "Hold", "Exact product/zone compatibility or no-overlap evidence is incomplete."
    elif spacing is None or spacing < 10 or not flush or flush_minutes is None:
        rec, reason = "Hold", "Pulse spacing or bounded clean-water flush evidence is incomplete."
    else:
        rec, reason = "Needs Data", "Physical relay mapping and supervised identity remain unproven."
    task = _task("fertilizer_injection_ch1", rec, reason, "during_compatible_irrigation",
                 ["active_zone", "10_min_preflow", "10_min_spacing",
                  "maximum_60_seconds", "clean_water_flush",
                  "exact_product_zone_compatibility", "no_overlapping_pulse",
                  "relay_binding_unresolved"], {})
    task["maximum_duration_seconds"] = 60
    return task


def _fertilizer_mixing_task(tanks, tank_state, reserve):
    return _task(
        "fertilizer_mixing_ch2", "Needs Data",
        "Twice-daily 15-minute mixing is a candidate only; relay identity is unproven.",
        "surplus_solar_candidate", ["mixing_need", "relay_binding_unresolved"],
        reserve,
    )


def _task(identity, recommendation, reason, window, dependencies, reserve):
    return {
        "task_id": identity,
        "recommendation": recommendation,
        "reason": reason,
        "preferred_window": window,
        "dependencies": dependencies,
        "command_created": False,
        "dispatchable": False,
        "electrical_operation_confirmed": False,
        "physical_water_flow_confirmed": False,
        "delivered_volume": UNAVAILABLE,
        "could_use_grid": recommendation == "Recommend"
            and reserve.get("discretionary_battery_energy_available") is not True,
    }


def _grid_exposure(tasks, reserve):
    candidates = [t["task_id"] for t in tasks if t.get("could_use_grid")]
    return {
        "status": "possible_unquantified" if candidates else "not_estimated",
        "candidate_tasks": candidates,
        "estimated_kwh": UNAVAILABLE,
        "estimated_cost_zar": UNAVAILABLE,
        "tariff_zar_per_kwh": 9.0,
        "tariff_status": "owner_supplied_provisional",
        "reason": "Device wattage and duration are not authoritatively bound."
            if candidates else "No supported grid-required task.",
    }


def _freshness(packet, now):
    if packet and packet.get("conflicting") is True:
        return "conflicting"
    if not packet or not packet.get("observed_at"):
        return UNAVAILABLE
    age = _age_minutes(packet, now)
    threshold = _number(packet.get("stale_after_minutes"))
    if age is None or threshold is None:
        return UNAVAILABLE
    return "fresh" if age <= threshold else "stale"


def _tank_freshness(packet, now):
    if not packet or not packet.get("observed_at"):
        return UNAVAILABLE
    age = _age_minutes(packet, now)
    if age is None:
        return UNAVAILABLE
    return "fresh" if age <= 360 else "aging" if age <= 1440 else "stale"


def _age_minutes(packet, now):
    try:
        observed = datetime.fromisoformat(str(packet["observed_at"]).replace("Z", "+00:00"))
        if observed.tzinfo is None:
            return None
        delta = (now.astimezone(timezone.utc)-observed.astimezone(timezone.utc)).total_seconds()/60
        if delta < -1:
            return None
        return round(max(0, delta), 1)
    except (KeyError, TypeError, ValueError):
        return None


def _latest_observed_at(*items):
    now = items[-1]
    values = []
    for item in items[:-1]:
        if isinstance(item, dict) and item.get("observed_at"):
            try:
                values.append(datetime.fromisoformat(str(item["observed_at"]).replace("Z", "+00:00")))
            except ValueError:
                pass
    return max(values).isoformat() if values else now.isoformat()


def _safe_plan(plan):
    expected_id = plan_identity(plan.get("operating_date", ""))
    return (
        isinstance(plan, dict)
        and plan.get("success") is True
        and plan.get("plan_id") == expected_id
        and plan.get("authority") == AUTHORITY
        and plan.get("status") in {"recommend", "hold", "needs_data"}
        and all(
            task.get("command_created") is False
            and task.get("dispatchable") is False
            and task.get("electrical_operation_confirmed") is False
            and task.get("physical_water_flow_confirmed") is False
            for task in plan.get("candidate_tasks", [])
        )
    )


def _tank_state(value):
    normalized = str(value or UNKNOWN).strip().upper()
    if normalized not in {"LOW", "OK", "FULL", "UNKNOWN"}:
        raise ValueError("invalid_tank_state")
    return UNKNOWN if normalized == "UNKNOWN" else normalized


def _plan_evidence(plan):
    return {
        "evidence_generation": plan["evidence_generation"],
        "current_power": plan["current_power"],
        "forecast": plan["forecast"],
        "rain_capture": plan["rain_capture"],
        "tank_evidence": plan["tank_evidence"],
        "water_demand": plan["water_demand"],
    }


def _material_evidence(evidence, now):
    """Remove sampling noise while retaining safety-meaningful changes."""
    power = _dict(evidence.get("power"))
    weather = _dict(evidence.get("weather"))
    forecast = _dict(evidence.get("forecast"))
    tanks = _dict(evidence.get("tanks"))
    irrigation = _dict(evidence.get("irrigation"))
    return {
        "power": {
            "freshness": _freshness(power, now),
            "battery_soc_pct": _rounded(power.get("battery_soc_pct"), 1),
            "solar_power_band_w": _rounded(power.get("solar_power_w"), 250),
            "load_power_band_w": _rounded(power.get("load_power_w"), 250),
            "grid_power_band_w": _rounded(power.get("grid_power_w"), 250),
            "grid_state": power.get("grid_state"),
        },
        "weather": {
            "freshness": _freshness(weather, now),
            "rain_rate_mm_h": _rounded(weather.get("rain_rate_mm_h"), 0.01),
            "rain_today_mm": _rounded(weather.get("rain_today_mm"), 0.1),
            "temperature_c": _rounded(weather.get("temperature_c"), 1),
            "wind_speed_kmh": _rounded(weather.get("wind_speed_kmh"), 1),
        },
        "forecast": {
            "freshness": _freshness(forecast, now),
            "forecast_run_at": forecast.get("observed_at"),
            "days": forecast.get("days"),
        },
        "tanks": {
            "freshness": _tank_freshness(tanks, now),
            "storage_reported_count": tanks.get("storage_reported_count"),
            "reservoir_reported_count": tanks.get("reservoir_reported_count"),
            "storage_state": tanks.get("storage_state"),
            "reservoir_state": tanks.get("reservoir_state"),
            "observed_at": tanks.get("observed_at"),
        },
        "irrigation": {
            "zones": [
                {
                    "zone_id": zone.get("zone_id"),
                    "recommendation": zone.get("recommendation"),
                    "eligibility_today": zone.get("eligibility_today"),
                    "proposed_runtime_status": zone.get("proposed_runtime_status"),
                }
                for zone in irrigation.get("zones", [])
                if isinstance(zone, dict)
            ],
            "active_zone": irrigation.get("active_zone"),
            "active_zone_observed_minutes": irrigation.get("active_zone_observed_minutes"),
            "minutes_since_last_injection": irrigation.get("minutes_since_last_injection"),
            "clean_water_flush_supported": irrigation.get("clean_water_flush_supported"),
        },
        "water_demand": evidence.get("water_demand"),
        "history": evidence.get("history"),
        "calculation_version": "rootline_water_energy_plan_v1",
    }


def _canonical_sha(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _rounded(value, quantum):
    number = _number(value)
    if number is None:
        return None
    return round(number / quantum) * quantum


def _as_za(value):
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZA_TZ)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _number(value):
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _optional_count(value, maximum):
    if value in (None, ""):
        return None
    number = int(value)
    if number < 0 or number > maximum:
        raise ValueError("count_out_of_range")
    return number


def _overall_status(tasks):
    recommendations = {task["recommendation"] for task in tasks}
    if "Hold" in recommendations:
        return "hold"
    if "Needs Data" in recommendations:
        return "needs_data"
    return "recommend"


def _summary(tasks, reserve, rain):
    recommended = [t["task_id"] for t in tasks if t["recommendation"] == "Recommend"]
    return (
        f"Reserve {reserve['governing_reserve_soc_pct']:.0f}% governs. "
        f"Rain: {rain['current_rain_status']}. "
        + (f"Recommended candidates: {', '.join(recommended)}."
           if recommended else "No task is presently supported for execution.")
    )


def _evidence_gaps(forecast_state, tank_state, tasks):
    gaps = []
    if forecast_state != "fresh":
        gaps.append("fresh_forecast")
    if tank_state not in {"fresh", "aging"}:
        gaps.append("fresh_manual_tank_counts")
    for task in tasks:
        gaps.extend(d for d in task.get("dependencies", []) if "unresolved" in d)
    return sorted(set(gaps))


def _unavailable(status, selected, exc=None):
    result = {
        "success": False,
        "status": status,
        "operating_date": selected,
        "owner_message": "Current Water & Energy Plan is Unavailable.",
        "authority": deepcopy(AUTHORITY),
    }
    if exc:
        result["error_type"] = exc.__class__.__name__
    return result
