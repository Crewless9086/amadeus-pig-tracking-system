"""Canonical, command-inert ROOTLINE Water & Energy Plan.

The service combines existing read models into owner advice and can append an
immutable advisory generation. It contains no network client, scheduler,
device transport, retry, SmartLife, SONOFF, IFTTT, n8n, or hardware consumer.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from zoneinfo import ZoneInfo

from services.database_service import DATABASE_URL_ENV
from modules.telemetry.rootline_adaptive_irrigation import (
    build_adaptive_irrigation_decisions,
)
from modules.telemetry.rootline_auxiliary_management import (
    build_auxiliary_tasks, build_fertilizer_batch_lifecycle,
)
from modules.telemetry.rootline_water_balance import read_latest_zone_water_balances


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
    "irrigation": {
        "standing_water_requirement": True,
        "zones": ["B12345", "C12345"],
        "target_days_per_week_each": 4,
        "nominal_runtime_minutes": 120,
        "historical_window": "22:00-00:00 SAST alternating camps",
        "historical_window_is_policy": False,
        "today_owner_candidate": "B12345",
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
        "maximum_injection_pulse_seconds": 120,
        "injection_pulses_per_eligible_segment": 2,
        "minimum_pulse_spacing_minutes": 10,
        "clean_water_flush_required": True,
        "mixing_segment_maximum_minutes": 5,
        "mixing_daily_verified_maximum_minutes": 30,
        "relay_api_mapping": {
            "injection_on": "controller_1_ch1_on",
            "injection_off": "controller_1_ch1_off",
            "mixer_on": "controller_1_ch2_on",
            "mixer_off": "controller_1_ch2_off",
        },
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
    irrigation_history = _dict(evidence.get("irrigation_history"))
    water_demand = _dict(evidence.get("water_demand"))
    water_balance = _dict(evidence.get("water_balance"))
    fertilizer_batch = build_fertilizer_batch_lifecycle(
        observations=evidence.get("fertilizer_batch_observations"),
        executions=evidence.get("fertilizer_executions"), now=now)

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
        *_irrigation_tasks(irrigation, irrigation_history, reserve, rain,
                           weather, forecast, tanks,
                           tank_state, power, power_state, weather_state, now,
                           selected_date),
    ]
    auxiliary = build_auxiliary_tasks(batch=fertilizer_batch, power=power,
        verified_mixing=evidence.get("fertilizer_executions"),
        mixing_history_complete_through=evidence.get(
            "fertilizer_history_complete_through"), now=now)
    status = _overall_status(tasks)
    evidence_observed_at = _latest_observed_at(power, weather, forecast, tanks, now)
    canonical_evidence = {
        "power": power,
        "weather": weather,
        "forecast": forecast,
        "tanks": tanks,
        "irrigation": irrigation,
        "history": history,
        "irrigation_history": irrigation_history,
        "water_demand": water_demand,
        "water_balance":water_balance,
        "fertilizer_batch_observations": evidence.get("fertilizer_batch_observations") or [],
        "fertilizer_executions": evidence.get("fertilizer_executions") or [],
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
        "recent_irrigation_history": irrigation_history or {
            "status": UNAVAILABLE, "zones": {}
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
            "status": tank_state["overall"],
            "storage_reported_count": (tanks.get("storage_fraction") or [tanks.get("storage_reported_count")])[0],
            "storage_state": tanks.get("storage_state", UNKNOWN),
            "storage_total_count": (tanks.get("storage_fraction") or [None,5])[1],
            "storage_fraction": tanks.get("storage_fraction"),
            "reservoir_reported_count": (tanks.get("reservoir_fraction") or [tanks.get("reservoir_reported_count")])[0],
            "reservoir_state": tanks.get("reservoir_state", UNKNOWN),
            "reservoir_total_count": (tanks.get("reservoir_fraction") or [None,12])[1],
            "reservoir_fraction": tanks.get("reservoir_fraction"),
            "storage_observed_at": tanks.get("storage_observed_at"),
            "storage_age_minutes": _age_minutes(
                {"observed_at": tanks.get("storage_observed_at")}, now
            ),
            "storage_freshness": tank_state["storage"],
            "reservoir_observed_at": tanks.get("reservoir_observed_at"),
            "reservoir_age_minutes": _age_minutes(
                {"observed_at": tanks.get("reservoir_observed_at")}, now
            ),
            "reservoir_freshness": tank_state["reservoir"],
            "observed_at": tanks.get("observed_at"),
            "reporter": tanks.get("reporter"),
            "source": tanks.get("source"),
            "storage_reporter": tanks.get("storage_reporter"),
            "storage_source": tanks.get("storage_source"),
            "reservoir_reporter": tanks.get("reservoir_reporter"),
            "reservoir_source": tanks.get("reservoir_source"),
            "age_minutes": _age_minutes(tanks, now),
            "litres_inferred": False,
        },
        "water_demand": water_demand or {"status": "standing_essential"},
        "zone_water_balance":water_balance or {"status":UNAVAILABLE,"zones":{}},
        "candidate_tasks": tasks,
        "irrigation_auxiliary_devices": auxiliary["irrigation_auxiliary_devices"],
        "irrigation_auxiliary_tasks": auxiliary["irrigation_auxiliary_tasks"],
        "fertilizer_batch_lifecycle": fertilizer_batch,
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
        "reassessment": {
            "next_time_or_trigger": _next_reassessment(tasks),
            "triggers": [
                "fresh_or_materially_changed_local_weather",
                "observed_rain",
                "fresh_forecast_generation",
                "new_independent_storage_or_reservoir_observation",
                "completed_or_missed_B_or_C_irrigation_evidence",
                "SOC_crosses_governing_reserve_or_absolute_floor",
            ],
            "automatic_command": False,
        },
        "recovery_handling": (
            "If the B window is missed or interrupted, reconsider the remaining "
            "weekly B target at the next suitable evidence-backed energy and water "
            "window; do not create or replay a command automatically."
        ),
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
    # These sources are independent read models. Loading them serially can add
    # several individually bounded database waits and exceed the enclosing web
    # worker deadline before protected execution reaches its claim boundary.
    # Keep each source's own timeout/fail-closed contract while bounding the
    # aggregate latency to the slowest source instead of their sum.
    from modules.telemetry.rootline_bounded_read_group import run_bounded_read_group
    readers = {
        "power": lambda: get_current_power_state(database_url=database_url),
        "weather": lambda: get_current_weather_state(database_url=database_url),
        "forecast": lambda: get_weather_forecast(days=3, database_url=database_url),
        "advisor": lambda: get_rootline_daily_advisor(selected, now=now),
        "balances": lambda: read_latest_zone_water_balances(database_url, now=now),
        "history": lambda: _read_historical_context(database_url),
        "irrigation_history": lambda: _read_recent_irrigation_history(database_url, now),
        "tanks": lambda: _read_latest_tank_observation(database_url),
        "owner_zone_need": lambda: _read_latest_owner_zone_need(database_url, now),
    }
    loaded = run_bounded_read_group(readers,max_workers=3,deadline_seconds=20)
    power_packet, _ = loaded["power"]
    weather_packet, _ = loaded["weather"]
    forecast_packet, _ = loaded["forecast"]
    advisor, _ = loaded["advisor"]
    balances = loaded["balances"]
    advisor_zones=deepcopy(advisor.get("zones", []))
    for zone in advisor_zones:
        if isinstance(zone,dict):
            zone["water_balance"]=_dict(balances.get("zones")).get(
                str(zone.get("zone_id")),{"status":UNAVAILABLE})
    history = loaded["history"]
    irrigation_history = loaded["irrigation_history"]
    tanks = loaded["tanks"]
    owner_zone_need = loaded["owner_zone_need"]
    if isinstance(owner_zone_need, dict) and owner_zone_need.get("status") == "Available":
        matching = next((zone for zone in advisor_zones
                         if zone.get("zone_id") == owner_zone_need.get("zone_id")), None)
        if matching is not None:
            matching.update({"visible_need": "visible_need",
                "visible_need_observed_at": owner_zone_need["observed_at"],
                "visible_need_source": owner_zone_need["source"]})
    database_failures = [str(packet.get("error_type")) for packet in (
        power_packet, weather_packet, forecast_packet, history, tanks, balances)
        if isinstance(packet, dict) and packet.get("error_type")]
    evidence = {
        "power": _normalize_power(power_packet),
        "weather": _normalize_weather(weather_packet),
        "forecast": _normalize_forecast(forecast_packet),
        "irrigation": {
            "zones": advisor_zones,
            "active_zone": None,
            "source": "rootline_daily_advisor",
            "adaptive_management": {
                "enabled": True,
                "contract_version": "rootline_adaptive_irrigation_v1",
                "zones": [{"zone_id": "B12345"}, {"zone_id": "C12345"}],
                "target_days_per_week": 4,
                "max_execution_minutes": 60,
                "simultaneous_zones_allowed": False,
                "segment_two_requires_fresh_decision": True,
            },
            "owner_candidate": {
                "zone_id": "B12345",
                "operating_date": "2026-08-01",
                "source": "owner_confirmed_ROOTLINE_policy_20260801",
            },
        },
        "history": history,
        "irrigation_history": irrigation_history,
        "tanks": tanks,
        "database_read_failures": database_failures,
        "water_demand": {
            "status": "standing_essential",
            "owner_reclassification_required": False,
        },
        "water_balance":balances,
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
        storage_fraction = _fraction(payload.get("storage_fraction"), "storage_fraction")
        reservoir_fraction = _fraction(payload.get("reservoir_fraction"), "reservoir_fraction")
        storage = None if storage_fraction else _optional_count(payload.get("storage_reported_count"), 5)
        reservoir = None if reservoir_fraction else _optional_count(payload.get("reservoir_reported_count"), 12)
        storage_state = _tank_state(payload.get("storage_state"))
        reservoir_state = _tank_state(payload.get("reservoir_state"))
        if storage is None and reservoir is None and not storage_fraction and not reservoir_fraction:
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
        provider_message_id = str(payload.get("provider_message_id") or "").strip()
        if (storage_fraction or reservoir_fraction) and not provider_message_id:
            raise ValueError("provider_message_id_required_for_fraction")
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
                      observed_at,reporter_identity,source,
                      storage_fraction_numerator,storage_fraction_denominator,
                      reservoir_fraction_numerator,reservoir_fraction_denominator,
                      provider_message_id
                    ) values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on conflict (idempotency_key) do nothing
                    returning observation_id
                    """,
                    (identity, key, storage, reservoir, storage_state,
                     reservoir_state, observed, actor_identity, source,
                     *(storage_fraction or (None,None)),*(reservoir_fraction or (None,None)),
                     provider_message_id or None),
                )
                created = cursor.fetchone() is not None
                cursor.execute(
                    """select observation_id,storage_reported_count,reservoir_reported_count,
                              storage_state,reservoir_state,observed_at,
                              reporter_identity,source,
                              storage_fraction_numerator,storage_fraction_denominator,
                              reservoir_fraction_numerator,reservoir_fraction_denominator,
                              provider_message_id
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
            or (row[8],row[9]) != (storage_fraction or (None,None))
            or (row[10],row[11]) != (reservoir_fraction or (None,None))
            or row[12] != (provider_message_id or None)
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
            "provider_message_id": row[12],
            "storage_fraction": list(row[8:10]) if row[8] is not None else None,
            "reservoir_fraction": list(row[10:12]) if row[10] is not None else None,
            "litres_inferred": False, "hardware_control_performed": False,
        }, 201 if created else 200
    except Exception as exc:
        return {"success": False, "status": "tank_observation_write_failed",
                "error_type": exc.__class__.__name__, "write_outcome": "indeterminate"}, 503


def record_tank_observations_transactional(payloads, actor_identity, database_url=None):
    """Append independent tank observations atomically and prove exact readback."""
    if not actor_identity or not isinstance(payloads, list) or not 1 <= len(payloads) <= 2:
        return {"success": False, "status": "tank_observation_batch_invalid"}, 400
    normalized = []
    try:
        for payload in payloads:
            if not isinstance(payload, dict):
                raise ValueError("tank_observation_batch_invalid")
            storage_fraction = _fraction(payload.get("storage_fraction"), "storage_fraction")
            reservoir_fraction = _fraction(payload.get("reservoir_fraction"), "reservoir_fraction")
            if bool(storage_fraction) == bool(reservoir_fraction):
                raise ValueError("one_independent_tank_required")
            observed = datetime.fromisoformat(str(payload["observed_at"]).replace("Z", "+00:00"))
            if observed.tzinfo is None or observed.astimezone(timezone.utc) > datetime.now(timezone.utc):
                raise ValueError("observed_at_invalid")
            provider_id = str(payload.get("provider_message_id") or "").strip()
            key = str(payload.get("idempotency_key") or "").strip()
            source = str(payload.get("source") or "")
            if not provider_id or not key or source != "oom_sakkie_owner":
                raise ValueError("provider_bound_observation_required")
            kind = "storage" if storage_fraction else "reservoir"
            fraction = storage_fraction or reservoir_fraction
            state = _tank_state(payload.get(f"{kind}_state"))
            normalized.append({"kind": kind, "fraction": fraction, "state": state,
                "observed": observed, "provider_message_id": provider_id, "key": key, "source": source,
                "identity": "ROOTLINE-TANK-" + sha256(key.encode()).hexdigest()[:24].upper()})
        if len({row["kind"] for row in normalized}) != len(normalized):
            raise ValueError("duplicate_independent_tank")
        if len({row["provider_message_id"] for row in normalized}) != 1:
            raise ValueError("shared_provider_message_required")
    except (KeyError, TypeError, ValueError) as exc:
        return {"success": False, "status": str(exc)}, 400
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    try:
        import psycopg
        created_count = 0
        readback = []
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                for row in normalized:
                    storage = row["kind"] == "storage"
                    cursor.execute("""insert into public.rootline_tank_observations (
                        observation_id,idempotency_key,storage_state,reservoir_state,observed_at,
                        reporter_identity,source,storage_fraction_numerator,storage_fraction_denominator,
                        reservoir_fraction_numerator,reservoir_fraction_denominator,provider_message_id)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        on conflict (idempotency_key) do nothing returning observation_id""",
                        (row["identity"], row["key"], row["state"] if storage else UNKNOWN,
                         row["state"] if not storage else UNKNOWN, row["observed"], actor_identity,
                         row["source"], row["fraction"][0] if storage else None,
                         row["fraction"][1] if storage else None, row["fraction"][0] if not storage else None,
                         row["fraction"][1] if not storage else None, row["provider_message_id"]))
                    created_count += int(cursor.fetchone() is not None)
                    cursor.execute("""select observation_id,storage_state,reservoir_state,observed_at,
                        reporter_identity,source,storage_fraction_numerator,storage_fraction_denominator,
                        reservoir_fraction_numerator,reservoir_fraction_denominator,provider_message_id
                        from public.rootline_tank_observations where idempotency_key=%s""", (row["key"],))
                    actual = cursor.fetchone()
                    storage_actual = row["kind"] == "storage"
                    fraction = list(actual[6:8] if storage_actual else actual[8:10])
                    state = actual[1] if storage_actual else actual[2]
                    if (actual[0] != row["identity"] or state != row["state"]
                            or actual[3].astimezone(timezone.utc) != row["observed"].astimezone(timezone.utc)
                            or actual[4] != actor_identity or actual[5] != row["source"]
                            or fraction != list(row["fraction"]) or actual[10] != row["provider_message_id"]):
                        raise ValueError("tank_observation_idempotency_conflict")
                    readback.append({"observation_id": actual[0], "kind": row["kind"],
                        "fraction": fraction, "state": state, "observed_at": actual[3].isoformat(),
                        "provider_message_id": actual[10]})
        generation = sha256(json.dumps(readback, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return {"success": True, "status": "recorded" if created_count else "exact_replay",
            "created_count": created_count, "observation_ids": [row["observation_id"] for row in readback],
            "observation_generation": generation, "readback": readback,
            "hardware_control_performed": False}, 201 if created_count else 200
    except ValueError as exc:
        return {"success": False, "status": str(exc), "write_outcome": "rolled_back"}, 409
    except Exception as exc:
        return {"success": False, "status": "tank_observation_batch_write_failed",
            "error_type": exc.__class__.__name__, "write_outcome": "indeterminate"}, 503


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
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"status": UNAVAILABLE}
    try:
        import psycopg
        with connect_bounded_read(database_url=database_url) as connection:
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


def _read_recent_irrigation_history(database_url, now):
    from modules.telemetry.rootline_irrigation_history import read_canonical_irrigation_history
    return read_canonical_irrigation_history(database_url, now=now)


def _read_latest_tank_observation(database_url):
    """Compose the newest independent storage and reservoir observations."""
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {}
    try:
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
        with connect_bounded_read(database_url=database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select storage_reported_count,reservoir_reported_count,
                           storage_state,reservoir_state,observed_at,
                           reporter_identity,source,
                           storage_fraction_numerator,storage_fraction_denominator,
                           reservoir_fraction_numerator,reservoir_fraction_denominator,
                           provider_message_id
                      from public.rootline_tank_observations
                     where storage_reported_count is not null or storage_fraction_numerator is not null
                     order by observed_at desc,recorded_at desc limit 1
                    """
                )
                storage = cursor.fetchone()
                cursor.execute(
                    """
                    select storage_reported_count,reservoir_reported_count,
                           storage_state,reservoir_state,observed_at,
                           reporter_identity,source,
                           storage_fraction_numerator,storage_fraction_denominator,
                           reservoir_fraction_numerator,reservoir_fraction_denominator,
                           provider_message_id
                      from public.rootline_tank_observations
                     where reservoir_reported_count is not null or reservoir_fraction_numerator is not null
                     order by observed_at desc,recorded_at desc limit 1
                    """
                )
                reservoir = cursor.fetchone()
        if not storage and not reservoir:
            return {}
        newest = max(
            (row for row in (storage, reservoir) if row), key=lambda row: row[4]
        )
        return {
            "storage_reported_count": storage[0] if storage else None,
            "reservoir_reported_count": reservoir[1] if reservoir else None,
            "storage_state": storage[2] if storage else UNKNOWN,
            "reservoir_state": reservoir[3] if reservoir else UNKNOWN,
            "storage_observed_at": storage[4].isoformat() if storage else None,
            "reservoir_observed_at": reservoir[4].isoformat() if reservoir else None,
            "storage_reporter": storage[5] if storage else None,
            "storage_source": storage[6] if storage else None,
            "reservoir_reporter": reservoir[5] if reservoir else None,
            "reservoir_source": reservoir[6] if reservoir else None,
            "storage_fraction": list(storage[7:9]) if storage and len(storage)>8 and storage[7] is not None else None,
            "storage_provider_message_id": storage[11] if storage and len(storage)>11 else None,
            "reservoir_fraction": list(reservoir[9:11]) if reservoir and len(reservoir)>10 and reservoir[9] is not None else None,
            "reservoir_provider_message_id": reservoir[11] if reservoir and len(reservoir)>11 else None,
            "observed_at": newest[4].isoformat(),
            "reporter": newest[5],
            "source": newest[6],
        }
    except Exception as exc:
        return {"status": UNAVAILABLE, "error_type": exc.__class__.__name__}


def _read_latest_owner_zone_need(database_url, now):
    """Load one fresh provider-bound need without turning free text into authority."""
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return {"status": UNAVAILABLE}
    try:
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_read
        with connect_bounded_read(database_url=database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select review_json->'rootline_operational_intake'->'outcome'
                      from public.sam_live_stock_conversation_review_events
                     where event_source='oom_sakkie_rootline_operational_intake'
                       and review_json->'rootline_operational_intake'->>'state'='completed'
                       and review_json->'rootline_operational_intake'->'outcome'->>'visible_irrigation_need_zone'
                           in ('B12345','C12345')
                       and (review_json->'rootline_operational_intake'->'outcome'->>'writes_farm_data')::boolean is true
                     order by created_at desc,review_event_id desc limit 1
                """)
                row = cursor.fetchone()
        outcome = row[0] if row and isinstance(row[0], dict) else {}
        try:
            observed = datetime.fromisoformat(
                str(outcome.get("provider_timestamp") or "").replace("Z", "+00:00"))
            if observed.tzinfo is None:
                observed = None
        except (TypeError, ValueError):
            observed = None
        provider_id = str(outcome.get("provider_message_id") or "").strip()
        zone = str(outcome.get("visible_irrigation_need_zone") or "")
        current = _as_za(now or datetime.now(timezone.utc))
        if (zone not in {"B12345", "C12345"} or not provider_id or observed is None
                or observed > current or current - observed > timedelta(hours=24)):
            return {"status": UNAVAILABLE}
        return {"status": "Available", "zone_id": zone,
                "observed_at": observed.isoformat(),
                "source": "oom_sakkie_authenticated_operational_intake",
                "provider_message_id": provider_id}
    except Exception as exc:
        return {"status": UNAVAILABLE, "error_type": exc.__class__.__name__}


def read_tank_observation(observation_id, database_url=None):
    database_url = str(database_url or os.getenv(DATABASE_URL_ENV, "")).strip()
    try:
        import psycopg
        with psycopg.connect(database_url, connect_timeout=10) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("""select observation_id,storage_reported_count,reservoir_reported_count,
                    storage_state,reservoir_state,observed_at,reporter_identity,source,
                    storage_fraction_numerator,storage_fraction_denominator,
                    reservoir_fraction_numerator,reservoir_fraction_denominator,provider_message_id
                    from public.rootline_tank_observations where observation_id=%s""",(str(observation_id),))
                row=cursor.fetchone()
        if not row: return {}
        return {"observation_id":row[0],"storage_reported_count":row[1],"reservoir_reported_count":row[2],
            "storage_state":row[3],"reservoir_state":row[4],"observed_at":row[5].isoformat(),
            "reporter":row[6],"source":row[7],
            "storage_fraction":list(row[8:10]) if row[8] is not None else None,
            "reservoir_fraction":list(row[10:12]) if row[10] is not None else None,
            "provider_message_id":row[12]}
    except Exception:
        return {}


def _fraction(value, field):
    if value in (None, ""):
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(field + "_invalid")
    numerator, denominator = value
    if (type(numerator) is not int or type(denominator) is not int
            or denominator < 1 or numerator < 0 or numerator > denominator):
        raise ValueError(field + "_invalid")
    return numerator, denominator




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
    storage = _tank_amount(tanks, "storage")
    if rain["borehole_avoidance_signal"] and not urgent:
        rec, reason = "Do Not Run", (
            "Fresh live rain; avoid unnecessary borehole pumping."
            if rain["current_rain_status"] == "Hold"
            else "Fresh credible forecast indicates meaningful roof-capture rain."
        )
    elif tank_state["storage"] in {"stale", UNAVAILABLE} or storage is None:
        rec, reason = "Needs Data", "Fresh storage count is unavailable."
    elif tanks.get("storage_state") == "FULL" and not urgent:
        rec, reason = "Do Not Run", "Storage was explicitly observed FULL."
    elif urgent:
        rec, reason = "Recommend", "Urgent water continuity can justify grid exposure."
    else:
        rec, reason = "Hold", (
            "Standing water continuity is protected; current storage evidence does "
            "not support borehole catch-up before the next reassessment."
        )
    return _task("borehole", rec, reason, "overnight_or_surplus_solar", [
        "fresh_storage_observation", "genuine_water_need",
        "SmartLife_device_binding_unresolved",
    ], reserve)


def _transfer_task(tanks, tank_state, demand, reserve):
    storage = _tank_amount(tanks, "storage")
    reservoir = _tank_amount(tanks, "reservoir")
    if (tank_state["storage"] in {"stale", UNAVAILABLE}
            or tank_state["reservoir"] in {"stale", UNAVAILABLE}
            or storage is None or reservoir is None):
        rec, reason = "Needs Data", "Fresh storage and reservoir counts are required."
    elif tanks.get("reservoir_state") == "FULL":
        rec, reason = "Do Not Run", "Reservoir storage was explicitly observed FULL."
    elif storage <= 0:
        rec, reason = "Hold", "No active storage supply is reported."
    elif demand.get("status") in {"standing_essential", "needed", "urgent"}:
        rec, reason = "Hold", "Adequate reservoir is reported; passive solar transfer remains monitor-only."
    else:
        rec, reason = "Hold", "Transfer demand is not proven."
    return _task("solar_transfer_pump", rec, reason, "10:00-15:00 SAST candidate", [
        "fresh_storage_observation", "fresh_reservoir_observation",
        "control_identity_unresolved",
    ], reserve)


def _irrigation_tasks(irrigation, irrigation_history, reserve, rain,
                      weather, forecast, tanks,
                      tank_state, power, power_state, weather_state, now,
                      operating_date):
    adaptive = _dict(irrigation.get("adaptive_management"))
    if adaptive.get("enabled") is True:
        reservoir_amount = _tank_amount(tanks, "reservoir")
        allowed_zone_fields = {
            "zone_id", "visible_need", "visible_need_observed_at",
            "visible_need_source", "completion_events",
            "completed_days_last_7_days", "latest_segment", "owner_correction",
            "water_balance",
        }
        history_zones = _dict(irrigation_history.get("zones"))
        evidence_zones = {
            str(item.get("zone_id")): item
            for item in irrigation.get("zones", [])
            if isinstance(item, dict) and item.get("zone_id")
        }
        canonical_zones = []
        for item in adaptive.get("zones", []):
            if not isinstance(item, dict):
                continue
            zone = {key: deepcopy(value) for key, value in item.items()
                    if key in allowed_zone_fields}
            # The canonical evidence reader attaches the independently current
            # balance to irrigation.zones.  Adaptive-management metadata stays
            # policy-only, so compose that read projection here rather than
            # silently dropping the balance before the governed planner.
            evidence_zone = _dict(evidence_zones.get(str(item.get("zone_id") or "")))
            for key in allowed_zone_fields - {"zone_id", "completion_events"}:
                if key in evidence_zone:
                    zone[key] = deepcopy(evidence_zone[key])
            canonical = _dict(history_zones.get(str(item.get("zone_id") or "")))
            zone["completion_events"] = [{
                "completed_at": event.get("event_at_sast"), "state": "Completed",
                "shutdown_verified": event.get("shutdown_verified") is True,
                "objective_satisfied": event.get("objective_satisfied") is True,
                "verified_runtime_minutes": event.get("verified_runtime_minutes"),
                "outcome_id": event.get("execution_id"),
                "source": event.get("provenance"),
            } for event in canonical.get("events", [])
                if event.get("qualifies_as_completed_watering") is True]
            zone["completion_ledger_complete_through"] = canonical.get("complete_through")
            canonical_zones.append(zone)
        payload = {
            "zones": canonical_zones,
            "power": deepcopy(power),
            "local_weather": deepcopy(weather),
            "forecast": deepcopy(forecast),
            "water": ({
                "observed_at": (
                    tanks.get("reservoir_observed_at")
                    or (tanks.get("observed_at")
                        if reservoir_amount is not None
                        else None)
                ),
                "reservoir_available": (
                    tank_state.get("reservoir") in {"fresh", "aging"}
                    and (_number(reservoir_amount) or 0) > 0
                ),
            } if reservoir_amount is not None else {}),
            "policy": {
                "season": _irrigation_season(now),
                "target_days_per_week": 4,
                "governing_reserve_soc_pct": reserve["governing_reserve_soc_pct"],
                "absolute_floor_soc_pct": reserve["absolute_floor_soc_pct"],
            },
        }
        decisions = build_adaptive_irrigation_decisions(payload, now=now)
        tasks = []
        recommendation_map = {
            "Run now": "Recommend", "Run later": "Recommend", "Hold": "Hold",
            "Needs Data": "Needs Data", "Completed": "Hold",
            "Reassess after segment one": "Hold",
            "recovery required": "Do Not Run",
        }
        for decision in decisions["zones"]:
            task = _task(
                f"irrigation_{decision['zone_id']}",
                recommendation_map[decision["decision"]], decision["reason"],
                decision["preferred_window"], decision["evidence_gaps"], reserve,
            )
            task.update({
                "zone_decision": decision["decision"],
                "need_score": decision["need_score"],
                "confidence": decision["confidence"],
                "rank": decision["rank"],
                "weekly_obligation": deepcopy(decision["weekly_obligation"]),
                "planned_duration_minutes": decision["proposed_segment_minutes"],
                "requested_total_duration_minutes": decision[
                    "requested_total_duration_minutes"],
                "expected_segment_count": decision["expected_segment_count"],
                "max_execution_minutes": 60,
                "fresh_decision_before_second_segment": True,
                "simultaneous_with_other_zone": False,
                "advisory_plan_supported": decision["decision"] in {"Run now", "Run later"},
                "actuation_blocked": True,
                "command_created": False,
            })
            tasks.append(task)
        return tasks
    zones = irrigation.get("zones") if isinstance(irrigation.get("zones"), list) else []
    result = []
    for zone in zones:
        zone = _dict(zone)
        zone_id = zone.get("zone_id") or "unknown"
        owner_candidate = _dict(irrigation.get("owner_candidate"))
        is_candidate = (
            zone_id == owner_candidate.get("zone_id")
            and operating_date == owner_candidate.get("operating_date")
            and bool(owner_candidate.get("source"))
        )
        zone_history = _dict(_dict(irrigation_history.get("zones")).get(zone_id))
        completed_days = zone_history.get("completed_last_7_days")
        adequate_reservoir = (
            tank_state["reservoir"] in {"fresh", "aging"}
            and (tanks.get("reservoir_state") == "FULL"
                 or _fraction_full(tanks.get("reservoir_fraction"))
                 or (tanks.get("reservoir_reported_count") is not None
                     and tanks.get("reservoir_reported_count") >= 9))
        )
        observed_rain = rain["current_rain_status"] == "Hold"
        rec = "Recommend" if (
            is_candidate and adequate_reservoir and weather_state == "fresh"
            and not observed_rain
        ) else "Hold"
        reason = (
            "B Camp is today's owner-identified candidate; the nominal two-hour "
            "drip target is supported proportionally by adequate reservoir evidence "
            "and fresh dry local weather. Crop/soil evidence is unavailable."
            if rec == "Recommend" else
            "Not selected for today's proportional B-Camp plan; retain the four-day "
            "weekly target and reassess from completed-irrigation evidence."
        )
        start = _adaptive_irrigation_start(now, power, power_state, reserve)
        result.append(_task(
            f"irrigation_{zone_id}", rec, reason, start,
            ["recent_completed_irrigation_unavailable", "crop_soil_need_unavailable",
             "exact_device_binding_required_for_actuation"], reserve,
        ))
        result[-1]["planned_start_at"] = start if rec == "Recommend" else None
        result[-1]["planned_duration_minutes"] = 120 if rec == "Recommend" else None
        result[-1]["advisory_plan_supported"] = rec == "Recommend"
        result[-1]["actuation_blocked"] = True
        result[-1]["recommendation_source"] = (
            owner_candidate.get("source") if is_candidate
            else "adaptive_daily_plan_not_selected"
        )
        result[-1]["weekly_cadence"] = {
            "target_days_per_week": 4,
            "completed_days_last_7_days": completed_days,
            "completion_evidence_status": (
                "Available" if completed_days is not None else UNAVAILABLE
            ),
            "today_eligibility_basis": (
                "bounded_dated_owner_candidate_with_nominal_target"
                if is_candidate else "not_selected_today"
            ),
            "may_not_be_reused_as_tomorrow_eligibility": True,
        }
    if not result:
        result.append(_task("irrigation", "Needs Data", "Zone advice unavailable.",
                            "Unavailable", ["daily_advisor"], reserve))
    return result


def _tank_amount(tanks, name):
    fraction=tanks.get(name+"_fraction")
    return fraction[0] if isinstance(fraction,(list,tuple)) and len(fraction)==2 else tanks.get(name+"_reported_count")


def _fraction_full(value):
    return isinstance(value,(list,tuple)) and len(value)==2 and value[1]>0 and value[0]==value[1]


def _adaptive_irrigation_start(now, power, power_state, reserve):
    surplus = (_number(power.get("solar_power_w")) or 0) > (_number(power.get("load_power_w")) or 0)
    soc = _number(power.get("battery_soc_pct"))
    if (power_state == "fresh" and surplus and soc is not None
            and soc >= reserve["governing_reserve_soc_pct"] and now.hour < 15):
        minute = 30 if now.minute < 30 else 0
        hour = now.hour if minute == 30 else now.hour + 1
        return f"{hour:02d}:{minute:02d} SAST"
    return "22:00 SAST"


def _irrigation_season(now):
    if now.month in {12, 1, 2}:
        return "summer"
    if now.month in {6, 7, 8}:
        return "winter"
    return "shoulder"


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
    def one(field, kind):
        observed_at = packet.get(field)
        if not observed_at and _tank_amount(packet, kind) is not None:
            observed_at = packet.get("observed_at")
        age = _age_minutes({
            "observed_at": observed_at
        }, now)
        if age is None:
            return UNAVAILABLE
        return "fresh" if age <= 360 else "aging" if age <= 1440 else "stale"
    storage = one("storage_observed_at", "storage")
    reservoir = one("reservoir_observed_at", "reservoir")
    states = {storage, reservoir}
    overall = "stale" if "stale" in states else (
        UNAVAILABLE if UNAVAILABLE in states else "aging" if "aging" in states else "fresh"
    )
    return {"overall": overall, "storage": storage, "reservoir": reservoir}


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
            "storage_observed_at": tanks.get("storage_observed_at"),
            "reservoir_observed_at": tanks.get("reservoir_observed_at"),
            "storage_reporter": tanks.get("storage_reporter"),
            "storage_source": tanks.get("storage_source"),
            "reservoir_reporter": tanks.get("reservoir_reporter"),
            "reservoir_source": tanks.get("reservoir_source"),
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
            "owner_candidate": irrigation.get("owner_candidate"),
        },
        "water_demand": evidence.get("water_demand"),
        "history": evidence.get("history"),
        "irrigation_history": evidence.get("irrigation_history"),
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


def _next_reassessment(tasks):
    for task in tasks:
        if task.get("task_id") == "irrigation_B12345" and task.get("planned_start_at"):
            return task["planned_start_at"]
    return "on_material_evidence_change"


def _evidence_gaps(forecast_state, tank_state, tasks):
    gaps = []
    if forecast_state != "fresh":
        gaps.append("fresh_forecast")
    if tank_state["storage"] not in {"fresh", "aging"}:
        gaps.append("fresh_storage_observation")
    if tank_state["reservoir"] not in {"fresh", "aging"}:
        gaps.append("fresh_reservoir_observation")
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
