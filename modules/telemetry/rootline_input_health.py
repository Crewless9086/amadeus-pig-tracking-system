"""ROOTLINE input health on canonical telemetry and the existing alert ledger.

No provider I/O, forecast acquisition, control decisions or independent schedule.
The paired ownership flag moves only legacy source-health notices onto the
existing family-delivery rail. It is disabled until the release owner cuts over.
"""
from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import os
import re
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from modules.telemetry.power_service import DEFAULT_POWER_SOURCE_ID
from modules.telemetry.weather_service import DEFAULT_WEATHER_SOURCE_ID
from modules.telemetry.forecast_provider_health import SOURCES, NIGHTLY_CYCLE_PROVIDER, LEASE_SECONDS

CONTRACT = "rootline_input_health.v1"
OWNERSHIP_FLAG = "ROOTLINE_INPUT_HEALTH_ENABLED"
SAST = ZoneInfo("Africa/Johannesburg")
INPUTS = {
    "weather": (DEFAULT_WEATHER_SOURCE_ID, "weather_com_pws"),
    "power": (DEFAULT_POWER_SOURCE_ID, "sunsynk"),
    "forecast": (SOURCES[NIGHTLY_CYCLE_PROVIDER], NIGHTLY_CYCLE_PROVIDER),
}
ALERT_TYPES = {kind: "ROOTLINE_INPUT_" + kind.upper() for kind in INPUTS}
LEGACY_TYPES = {"weather": "STATION_STALE", "power": "POWER_NOT_LOGGING"}


def input_health_enabled(environ=None):
    source = os.environ if environ is None else environ
    return str(source.get(OWNERSHIP_FLAG, "")).strip().lower() == "true"


def apply_legacy_ownership(evaluation, kind):
    """A paired cutover, not retirement of weather/power threshold alerts."""
    if not input_health_enabled() or kind not in LEGACY_TYPES:
        return evaluation
    quiet_types = {LEGACY_TYPES[kind]}
    if kind == "power":
        quiet_types.add("POWER_BATTERY_HIGH")
    owned = [row for row in evaluation["sendable_alerts"]
             if row.get("alert_type") in quiet_types]
    return {**evaluation,
        "sendable_alerts": [row for row in evaluation["sendable_alerts"]
                           if row.get("alert_type") not in quiet_types],
        "suppressed_alerts": [*evaluation["suppressed_alerts"], *[
            {**row, "suppressed_reason": "rootline_input_health_owns_delivery"} for row in owned]]}


def _time(value):
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return stamp.astimezone(timezone.utc) if stamp.tzinfo is not None else None
    except (ValueError, TypeError):
        return None


def _number(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value))
        return number if number.is_finite() else None
    except (InvalidOperation, ValueError):
        return None


def _registered(kind, source):
    return (isinstance(source, dict) and source.get("source_id") == INPUTS[kind][0]
        and source.get("provider") == INPUTS[kind][1] and source.get("source_type") == kind
        and source.get("active") is True and source.get("timezone") == "Africa/Johannesburg")


def project_sensor(kind, source, reading, *, now):
    """Project finite exact-source readings; zero and absence stay distinct."""
    if kind not in {"weather", "power"} or _time(now) is None:
        raise ValueError("input_health_projection_invalid")
    now = _time(now)
    reading = reading if isinstance(reading, dict) else {}
    observed = _time(reading.get("reading_at"))
    result = {"kind": kind, "source_id": INPUTS[kind][0], "state": "unavailable",
        "reason": "source_unregistered", "evaluated_at": now.isoformat(),
        "observed_at": observed.isoformat() if observed and observed <= now else None,
        "notify": True, "stale_after_minutes": source.get("stale_after_minutes") if isinstance(source, dict) else None}
    if not _registered(kind, source):
        return result
    if not reading or reading.get("source_id") != result["source_id"]:
        return {**result, "reason": "reading_missing"}
    if observed is None or observed > now:
        return {**result, "reason": "reading_time_invalid"}
    threshold = _number(source.get("stale_after_minutes"))
    if threshold is None or threshold <= 0:
        return {**result, "reason": "freshness_unverified"}
    # Match the existing read models' completed-minute freshness boundary.
    if int((now - observed).total_seconds() // 60) > threshold:
        return {**result, "reason": "reading_stale"}
    flags = reading.get("flags")
    if (not isinstance(flags, dict) or any(flags.get(k) is True for k in (
            "telemetry_conflict", "provider_error", "source_unhealthy"))
            or str(reading.get("summary_status") or "").lower() not in {"ok", "caution", "warning"}):
        return {**result, "reason": "reading_unverified"}
    fields = (("rain_rate_mm_h", "wind_speed_kmh") if kind == "weather" else
              ("battery_soc_pct", "solar_power_w", "load_power_w", "grid_power_w", "battery_power_w"))
    values = {key: _number(reading.get(key)) for key in fields}
    if any(value is None for value in values.values()):
        return {**result, "reason": "reading_incomplete"}
    if (kind == "weather" and any(value < 0 for value in values.values()) or
            kind == "power" and (not 0 <= values["battery_soc_pct"] <= 100 or
                values["solar_power_w"] < 0 or values["load_power_w"] < 0 or
                all(values[key] == 0 for key in ("battery_soc_pct", "solar_power_w", "load_power_w")))):
        return {**result, "reason": "reading_conflicting"}
    return {**result, "state": "available", "reason": "fresh_reading", "notify": False}


def forecast_operating_date(now):
    local = _time(now).astimezone(SAST)
    return (local.date() + timedelta(days=int((local.hour, local.minute) >= (23, 30)))).isoformat()


def project_forecast(sources, snapshot, *, now, operating_date=None):
    """Acquisition truth is date-bound and separate from provider availability."""
    now = _time(now)
    if now is None or not isinstance(sources, dict):
        raise ValueError("forecast_health_projection_invalid")
    operating_date = str(operating_date or forecast_operating_date(now))
    day = date.fromisoformat(operating_date)
    due = datetime.combine(day - timedelta(days=1), time(23, 30), SAST).astimezone(timezone.utc)
    result = {"kind": "forecast", "source_id": INPUTS["forecast"][0],
        "operating_date": operating_date, "evaluated_at": now.isoformat(),
        "observed_at": None, "state": "acquisition_unconfirmed",
        "reason": "nightly_cycle_unproven", "notify": now >= due + timedelta(seconds=LEASE_SECONDS)}
    if now < due:
        return {**result, "state": "not_yet_due", "reason": "nightly_not_due", "notify": False}
    owner = sources.get(INPUTS["forecast"][0])
    if not _registered("forecast", owner):
        return result
    cycle = owner.get("nightly_cycle") if isinstance(owner.get("nightly_cycle"), dict) else {}
    claimed = _time(cycle.get("claimed_at"))
    if (not isinstance(cycle.get("attempts", []), list)
            or any(not isinstance(a, dict) for a in cycle.get("attempts", []))
            or any(not isinstance(cycle.get(key, {}), dict) for key in ("result", "ingest"))):
        return result
    try:
        UUID(str(cycle.get("attempt_id")))
    except (ValueError, TypeError):
        return result
    if (cycle.get("version") != 1 or cycle.get("operating_date") != operating_date
            or cycle.get("cycle_date") != (day - timedelta(days=1)).isoformat()
            or claimed is None or not due <= claimed <= now):
        return result
    result["cycle_attempt_id"] = cycle["attempt_id"]
    if cycle.get("status") == "pending":
        # Reuse the existing admitted provider lease, including a later fallback.
        leases = [claimed + timedelta(seconds=LEASE_SECONDS)]
        for source in sources.values():
            health = source.get("provider_health") if isinstance(source.get("provider_health"), dict) else {}
            if (health.get("nightly_cycle") == {k: cycle[k] for k in ("attempt_id", "cycle_date", "operating_date")}
                    and health.get("status") == "pending" and _time(health.get("lease_until"))
                    and any(a.get("provider") == source.get("provider") and
                        a.get("attempt_id") == health.get("attempt_id") and
                        a.get("generation") == health.get("generation") and a.get("status") == "pending"
                        for a in cycle.get("attempts") or [])):
                start = _time(health.get("claimed_at"))
                end = _time(health["lease_until"])
                if start and claimed <= start <= now and end - start == timedelta(seconds=LEASE_SECONDS):
                    leases.append(end)
        if now < max(leases):
            return {**result, "state": "pending", "reason": "nightly_in_progress", "notify": False}
        return {**result, "notify": True, "reason": "nightly_result_unconfirmed"}
    completed = _time(cycle.get("completed_at"))
    if completed is None or not claimed <= completed <= now:
        return result
    if cycle.get("status") == "failed" and (cycle.get("result") or {}).get("status") == "failed":
        return {**result, "state": "failed", "reason": "nightly_acquisition_failed",
            "observed_at": completed.isoformat(), "notify": True}
    accepted = cycle.get("result") or {}
    ingest = cycle.get("ingest") or {}
    source_id = accepted.get("source_id")
    if not isinstance(source_id, str) or source_id not in SOURCES.values():
        return result
    selected = sources.get(source_id) or {}
    run_at = _time(accepted.get("forecast_run_at"))
    matching_attempt = any(a.get("provider") == selected.get("provider") and
        a.get("attempt_id") == ingest.get("attempt_id") and
        a.get("generation") == ingest.get("generation") and a.get("status") == "ingested"
        for a in cycle.get("attempts") or [])
    if (cycle.get("status") != "ingested" or accepted.get("status") != "ingested"
            or source_id not in SOURCES.values() or selected.get("active") is not True
            or selected.get("source_type") != "forecast" or SOURCES.get(selected.get("provider")) != source_id
            or selected.get("timezone") != "Africa/Johannesburg"
            or run_at is None or not claimed <= run_at <= completed
            or ingest.get("source_id") != source_id or _time(ingest.get("forecast_run_at")) != run_at
            or ingest.get("provider") != selected.get("provider") or not matching_attempt):
        return result
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    if (snapshot.get("source_id") != source_id or _time(snapshot.get("forecast_run_at")) != run_at
            or str(snapshot.get("forecast_date")) != operating_date
            or snapshot.get("timezone") != "Africa/Johannesburg"
            or _time(snapshot.get("ingested_at")) is None
            or not run_at <= _time(snapshot["ingested_at"]) <= completed):
        return result
    for key in ("rain_sum_mm", "rain_probability_max_pct", "wind_max_kmh", "gust_max_kmh", "temp_min_c", "temp_max_c"):
        value = snapshot.get(key)
        number = _number(value)
        if value is not None and (number is None or
                key in {"rain_sum_mm", "wind_max_kmh", "gust_max_kmh"} and number < 0 or
                key == "rain_probability_max_pct" and not 0 <= number <= 100):
            return result
    attempts = cycle.get("attempts") or []
    accepted_index = next(i for i, a in enumerate(attempts) if a.get("attempt_id") == ingest.get("attempt_id")
        and a.get("generation") == ingest.get("generation"))
    fallback = any(a.get("status") in {"fetch_failed", "ingest_failed"} for a in attempts[:accepted_index])
    return {**result, "state": "available_fallback" if fallback else "available",
        "reason": "nightly_ingestion_verified", "observed_at": completed.isoformat(), "notify": False,
        "accepted_source_id": source_id, "forecast_run_at": run_at.isoformat()}


def _read_projection(cursor, now, *, operating_date=None):
    """One source/latest snapshot, then one exact dated forecast snapshot."""
    ids = [INPUTS["weather"][0], INPUTS["power"][0], *SOURCES.values()]
    cursor.execute("""select ts.source_id,ts.source_type,ts.provider,ts.active,
        ts.timezone,ts.stale_after_minutes,
        ts.metadata->'forecast_nightly_cycle',ts.metadata->'forecast_provider_health',
        to_jsonb(w),to_jsonb(p)
        from public.telemetry_sources ts
        left join public.weather_latest_state w on w.source_id=ts.source_id
        left join public.power_latest_state p on p.source_id=ts.source_id
        where ts.source_id=any(%s)""", (ids,))
    sources, readings = {}, {}
    for row in cursor.fetchall():
        sources[row[0]] = dict(zip(("source_id", "source_type", "provider", "active",
            "timezone", "stale_after_minutes", "nightly_cycle", "provider_health"), row[:8]))
        readings[row[0]] = row[8] if row[1] == "weather" else row[9]
    projected = {kind: project_sensor(kind, sources.get(INPUTS[kind][0]),
        readings.get(INPUTS[kind][0]), now=now) for kind in ("weather", "power")}
    owner = sources.get(INPUTS["forecast"][0]) or {}
    accepted = (owner.get("nightly_cycle") if isinstance(owner.get("nightly_cycle"), dict) else {}).get("result") or {}
    accepted = accepted if isinstance(accepted, dict) else {}
    snapshot = None
    if accepted.get("source_id") in SOURCES.values() and _time(accepted.get("forecast_run_at")):
        cursor.execute("""select source_id,forecast_run_at,forecast_date,timezone,ingested_at,
            rain_sum_mm,rain_probability_max_pct,wind_max_kmh,gust_max_kmh,temp_min_c,temp_max_c
            from public.weather_forecast_snapshots
            where source_id=%s and forecast_run_at=%s and forecast_date=%s limit 1""",
            (accepted["source_id"], _time(accepted["forecast_run_at"]),
             operating_date or forecast_operating_date(now)))
        row = cursor.fetchone()
        if row:
            snapshot = dict(zip(("source_id", "forecast_run_at", "forecast_date", "timezone", "ingested_at",
                "rain_sum_mm", "rain_probability_max_pct", "wind_max_kmh", "gust_max_kmh", "temp_min_c", "temp_max_c"), row))
    projected["forecast"] = project_forecast(sources, snapshot, now=now, operating_date=operating_date)
    return projected, sources


def read_input_health(*, database_url=None, now=None, connect=None, operating_date=None, environ=None):
    if not input_health_enabled(environ):
        return {"contract": CONTRACT, "status": "unknown", "reason": "not_enabled", "inputs": {}}
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    now = _time(now or datetime.now(timezone.utc))
    if now is None:
        raise ValueError("input_health_time_invalid")
    connect = connect or connect_bounded_rootline_postgres
    with connect(database_url=database_url) as connection:
        with connection.cursor() as cursor:
            inputs, _ = _read_projection(cursor, now, operating_date=operating_date)
    return {"contract": CONTRACT, "observed_at": now.isoformat(), "inputs": inputs}


def _episode(row, kind):
    if row is None:
        return None
    identity, source_id, status, event_at, resolved_at, details = row
    if (not re.fullmatch(r"ROOTLINE-INPUT-[0-9A-F]{32}", str(identity))
            or not isinstance(details, dict) or details.get("contract") != CONTRACT
            or details.get("kind") != kind or details.get("source_id") != INPUTS[kind][0]
            or details.get("incident_id") != identity
            or source_id not in (None, INPUTS[kind][0])
            or status not in {"Open", "Resolved", "Ignored"} or _time(event_at) is None
            or not isinstance(details.get("outage"), dict)
            or details["outage"].get("source_id") != INPUTS[kind][0]
            or details["outage"].get("kind") != kind
            or _time(details["outage"].get("evaluated_at")) != _time(event_at)
            or (status == "Resolved" and (not isinstance(details.get("recovery"), dict)
                or _time(resolved_at) is None or _time(resolved_at) < _time(event_at)))):
        raise ValueError("input_health_episode_invalid")
    return {**details, "status": status, "outage_started_at": _time(event_at).isoformat(),
        "restored_at": _time(resolved_at).isoformat() if _time(resolved_at) else None}


def _load_episode(cursor, kind):
    # The existing area/event_at index still filters unrelated alert types.
    # LIMIT returns the newest typed record, including old/source-less episodes;
    # it does not bound index work over unrelated history. No rolling N.
    cursor.execute("""select alert_id,source_id,status,event_at,resolved_at,details
        from public.telemetry_alerts where area=%s and alert_type=%s
        order by event_at desc,alert_id desc limit 1""", (kind, ALERT_TYPES[kind]))
    return _episode(cursor.fetchone(), kind)


def reconcile_input_health(*, database_url=None, now=None, connect=None, environ=None):
    """Serialize finite input episodes; errors roll back without fake recovery."""
    if not input_health_enabled(environ):
        return {"contract": CONTRACT, "status": "disabled", "inputs": {}, "episodes": []}
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    from modules.telemetry.rootline_cycle_budget import remaining_seconds
    connect = connect or connect_bounded_rootline_postgres
    episodes = []
    with connect(database_url=database_url, read_only=False, read_committed=True) as connection:
        with connection.cursor() as cursor:
            for kind in sorted(INPUTS):
                lock = int.from_bytes(sha256((CONTRACT + "|" + kind).encode()).digest()[:8], "big", signed=True)
                cursor.execute("select pg_try_advisory_xact_lock(%s)", (lock,))
                if cursor.fetchone() != (True,):
                    raise ValueError("input_health_reconciliation_busy")
            cursor.execute("select clock_timestamp()")
            stamp = _time(cursor.fetchone()[0])
            if stamp is None:
                raise ValueError("input_health_server_time_unproven")
            inputs, sources = _read_projection(cursor, stamp)
            for kind, current in inputs.items():
                prior = _load_episode(cursor, kind)
                if prior and (_time(prior["outage_started_at"]) > stamp or
                        prior.get("restored_at") and _time(prior["restored_at"]) > stamp):
                    raise ValueError("input_health_episode_time_conflict")
                healthy = current["state"] in {"available", "available_primary", "available_fallback"}
                if not healthy and not current["notify"]:
                    # Pending/unproven is never restoration, nor a new alarm.
                    if prior:
                        episodes.append(prior)
                    continue
                if (prior and prior["status"] == "Open" and kind == "forecast" and not healthy
                        and prior.get("operating_date") != current.get("operating_date")):
                    details = {**prior, "superseded_at": stamp.isoformat()}
                    cursor.execute("""update public.telemetry_alerts set status='Ignored',details=%s::jsonb
                        where alert_id=%s and status='Open'""", (json.dumps(details), prior["incident_id"]))
                    prior = None
                if not healthy and (prior is None or prior["status"] != "Open"):
                    identity = "ROOTLINE-INPUT-" + uuid4().hex.upper()
                    details = {"contract": CONTRACT, "kind": kind, "source_id": INPUTS[kind][0],
                        "incident_id": identity, "operating_date": current.get("operating_date"),
                        "outage": deepcopy(current)}
                    cursor.execute("""insert into public.telemetry_alerts
                        (alert_id,source_id,area,alert_type,severity,message,event_at,status,details)
                        values (%s,%s,%s,%s,'warning',%s,%s,'Open',%s::jsonb)
                        returning alert_id,source_id,status,event_at,resolved_at,details""",
                        (identity, INPUTS[kind][0] if INPUTS[kind][0] in sources else None,
                         kind, ALERT_TYPES[kind], "ROOTLINE input unavailable: " + kind, stamp, json.dumps(details)))
                    prior = _episode(cursor.fetchone(), kind)
                    if prior is None or prior["incident_id"] != identity or prior["status"] != "Open" or prior["outage"] != current:
                        raise ValueError("input_health_insert_readback_unproven")
                elif healthy and prior and prior["status"] == "Open":
                    observed = _time(current.get("observed_at"))
                    # A pre-incident or backdated sample cannot close the outage.
                    if observed and observed >= _time(prior["outage_started_at"]):
                        details = {**prior, "recovery": deepcopy(current)}
                        cursor.execute("""update public.telemetry_alerts set status='Resolved',
                            resolved_at=%s,details=%s::jsonb where alert_id=%s and status='Open'
                            returning alert_id,source_id,status,event_at,resolved_at,details""",
                            (stamp, json.dumps(details), prior["incident_id"]))
                        previous_identity = prior["incident_id"]
                        prior = _episode(cursor.fetchone(), kind)
                        if (prior is None or prior["incident_id"] != previous_identity or
                                prior["status"] != "Resolved" or prior.get("recovery") != current):
                            raise ValueError("input_health_recovery_readback_unproven")
                if prior:
                    episodes.append(prior)
            remaining_seconds(minimum=3)
    return {"contract": CONTRACT, "status": "observed", "observed_at": stamp.isoformat(),
        "inputs": inputs, "episodes": episodes}


def read_input_notification_receipt(identity, *, database_url=None, connect=None, environ=None):
    """Use the same bounded execution/notification index as equipment receipts."""
    if not input_health_enabled(environ):
        return {}
    if not re.fullmatch(r"ROOTLINE-INPUT-[0-9A-F]{32}:(?:unavailable|restored):[0-9a-f]{32}", str(identity)):
        raise ValueError("input_health_notification_identity_invalid")
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    connect = connect or connect_bounded_rootline_postgres
    with connect(database_url=database_url) as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'rootline_execution'
                from public.sam_live_stock_conversation_review_events
                where event_source='rootline_irrigation_execution' and chatwoot_conversation_id=%s
                  and review_json->'rootline_execution'->>'action'='record_notification_delivery'
                  and review_json->'rootline_execution'->>'notification_identity'=%s
                order by (coalesce(review_json->'rootline_execution'->>'delivery_confirmed','false')='true') desc,
                    (coalesce(review_json->'rootline_execution'->>'delivery_ambiguous','false')='true') desc,
                    created_at desc,review_event_id desc limit 1""", (identity.partition(":")[0], identity))
            row = cursor.fetchone()
    return row[0] if row else {}



def read_input_notice_state(kind, *, database_url=None, now=None, connect=None, environ=None):
    """Revalidate current canonical health and latest episode before delivery."""
    if not input_health_enabled(environ):
        return {"status": "unknown", "reason": "not_enabled", "episode": None,
            "input": {"kind": kind, "state": "unknown", "reason": "not_enabled", "notify": False}}
    if kind not in INPUTS:
        raise ValueError("input_health_kind_invalid")
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    connect = connect or connect_bounded_rootline_postgres
    now = _time(now or datetime.now(timezone.utc))
    if now is None:
        raise ValueError("input_health_time_invalid")
    with connect(database_url=database_url) as connection:
        with connection.cursor() as cursor:
            inputs, _ = _read_projection(cursor, now)
            episode = _load_episode(cursor, kind)
    return {"input": inputs[kind], "episode": episode}


def power_observation_presentation(power, *, now=None, health=None):
    """Never render undated or future measurements as current power."""
    power = power if isinstance(power, dict) else {}
    observed = _time(power.get("observed_at"))
    now = _time(now or datetime.now(timezone.utc))
    if observed is None or now is None or observed > now:
        return {"show_values": False, "fresh": False, "observed_at": None}
    # Existing plan projection already owns the exact source-specific freshness.
    # A saved result cannot remain fresh indefinitely when rendered again.
    age = (now - observed).total_seconds() / 60
    health = health if isinstance(health, dict) else {}
    threshold = _number(health.get("stale_after_minutes"))
    typed_fresh = (health.get("state") == "available" and
        _time(health.get("observed_at")) == observed and threshold is not None and threshold > 0
        and int(age) <= threshold)
    # Older pure callers lack source metadata: retain the dated observation but
    # do not invent a current freshness threshold.
    fresh = typed_fresh
    return {"show_values": True, "fresh": fresh, "observed_at": observed.isoformat()}
