"""Forecast provider admission state in the existing telemetry source registry.

No forecast values, scheduler, credentials or hardware authority live here.
A pending lease is an explicit local unknown-outcome recovery policy, never a
claim that a provider's unseen quota reset or Retry-After has elapsed.
"""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import json
import os
from secrets import compare_digest
from uuid import UUID

from modules.telemetry.power_service import INGEST_API_KEY_ENV
from services.database_service import DATABASE_URL_ENV

SOURCES = {"visual_crossing": "visual-crossing-forecast-main",
    "weatherapi": "weatherapi-forecast-main", "open_meteo": "open-meteo-forecast-main"}
LEASE_SECONDS = 900
FAILURES = frozenset({"quota", "network", "http_error", "invalid_data", "deadline", "backend_ingest"})


def _utc(value):
    if not isinstance(value, str):
        raise ValueError("utc_timestamp_required")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("utc_timestamp_required") from None
    if stamp.tzinfo is None or stamp.utcoffset() != timedelta(0):
        raise ValueError("utc_timestamp_required")
    return stamp


def _identity(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError("attempt_id_required") from None


def transition(current, payload, now):
    """Pure locked-row transition; its caller owns server time and persistence."""
    if not isinstance(current, dict) or now.tzinfo is None:
        raise ValueError("provider_health_state_invalid")
    state = deepcopy(current)
    if state:
        if (state.get("version") != 1 or type(state.get("generation")) is not int
                or state["generation"] < 1 or state.get("status") not in {
                    "pending", "fetch_failed", "ingest_failed", "ingested"}):
            raise ValueError("provider_health_state_invalid")
        _identity(state.get("attempt_id"))
        _utc(state.get("claimed_at")); _utc(state.get("lease_until"))
    prior_retry = _utc(state["retry_not_before"]) if state.get("retry_not_before") else None
    attempt = _identity(payload.get("attempt_id"))
    action = payload.get("action")
    if action == "claim":
        if set(payload) - {"action", "provider", "attempt_id"}:
            raise ValueError("provider_health_fields_invalid")
        if prior_retry and now < prior_retry:
            return state, {"success": True, "allowed": False, "status": "provider_cooldown",
                "retry_not_before": prior_retry.isoformat()}, 200, False
        if state.get("attempt_id") == attempt:
            return state, {"success": True, "allowed": False, "status": "attempt_already_claimed"}, 200, False
        if state.get("status") == "pending" and now < _utc(state["lease_until"]):
            return state, {"success": True, "allowed": False, "status": "probe_pending",
                "lease_until": state["lease_until"]}, 200, False
        state = {"version": 1, "generation": state.get("generation", 0)+1,
            "attempt_id": attempt, "status": "pending", "claimed_at": now.isoformat(),
            "lease_until": (now+timedelta(seconds=LEASE_SECONDS)).isoformat(),
            "retry_not_before": prior_retry.isoformat() if prior_retry else None,
            "last_success_at": state.get("last_success_at"),
            "recovered_unknown_outcome": state.get("status") == "pending"}
        return state, {"success": True, "allowed": True, "status": "probe_claimed",
            "attempt_id": attempt, "generation": state["generation"],
            "lease_until": state["lease_until"]}, 200, True
    if action != "result" or set(payload) - {"action", "provider", "attempt_id",
            "generation", "status", "failure_kind", "retry_not_before", "forecast_run_at"}:
        raise ValueError("provider_health_fields_invalid")
    generation = payload.get("generation")
    if type(generation) is not int or generation < 1:
        raise ValueError("provider_health_generation_required")
    status = payload.get("status")
    failure = payload.get("failure_kind")
    if status not in {"fetch_failed", "ingest_failed", "ingested"}:
        raise ValueError("provider_health_status_invalid")
    if (status == "ingested" and failure is not None or status != "ingested" and failure not in FAILURES
            or status == "ingest_failed" and failure != "backend_ingest"
            or status == "fetch_failed" and failure == "backend_ingest"):
        raise ValueError("provider_health_failure_invalid")
    retry = _utc(payload["retry_not_before"]) if payload.get("retry_not_before") else None
    run_at = _utc(payload["forecast_run_at"]) if payload.get("forecast_run_at") else None
    if status == "ingested" and (run_at is None or not timedelta(0) <= now-run_at <= timedelta(hours=6)):
        raise ValueError("provider_health_forecast_time_invalid")
    result = {"status": status, "failure_kind": failure,
        "retry_not_before": retry.isoformat() if retry else None,
        "forecast_run_at": run_at.isoformat() if run_at else None}
    if generation != state.get("generation") or attempt != state.get("attempt_id"):
        return state, {"success": False, "status": "provider_health_generation_conflict"}, 409, False
    if state.get("status") != "pending":
        same = state.get("result") == result
        return state, {"success": same, "replayed": same,
            "status": "provider_result_replayed" if same else "provider_result_conflict"}, 200 if same else 409, False
    bounds = [stamp for stamp in (prior_retry, retry) if stamp is not None]
    state.update(status=status, completed_at=now.isoformat(), result=result,
        retry_not_before=max(bounds).isoformat() if bounds else None)
    if status == "ingested":
        state["last_success_at"] = now.isoformat()
    return state, {"success": True, "status": "provider_result_recorded",
        "retry_not_before": state["retry_not_before"]}, 200, True



def validate_ingest_claim(cursor, payload):
    """Fence snapshot writes using the SAME cursor/transaction as those writes.

    The source row remains locked until the caller's ingest transaction ends.
    Health result fencing alone cannot stop a late worker inserting snapshots.
    """
    provider = payload.get("provider") if isinstance(payload, dict) else None
    if not isinstance(provider, str) or provider not in SOURCES or payload.get("source_id") != SOURCES[provider]:
        raise ValueError("forecast_ingest_provider_invalid")
    claim = payload.get("provider_health_claim")
    if not isinstance(claim, dict) or set(claim) != {"provider", "generation", "attempt_id"}:
        raise ValueError("forecast_ingest_claim_required")
    if claim["provider"] != provider or type(claim["generation"]) is not int or claim["generation"] < 1:
        raise ValueError("forecast_ingest_claim_invalid")
    attempt = _identity(claim["attempt_id"])
    cycle = (payload.get("provenance") or {}).get("nightly_cycle")
    owner_state = _locked_cycle(cursor, cycle)
    cursor.execute("""select metadata,provider,source_type,active from public.telemetry_sources
        where source_id=%s for update""", (SOURCES[provider],))
    row = cursor.fetchone()
    if not row or row[1] != provider or row[2] != "forecast" or row[3] is not True:
        raise ValueError("forecast_source_not_registered")
    state = row[0].get("forecast_provider_health") if isinstance(row[0], dict) else None
    if (not isinstance(state, dict) or state.get("version") != 1
            or type(state.get("generation")) is not int or state.get("status") != "pending"
            or state.get("generation") != claim["generation"] or state.get("attempt_id") != attempt):
        raise ValueError("forecast_ingest_claim_conflict")
    cursor.execute("select clock_timestamp()")
    now = cursor.fetchone()[0].astimezone(timezone.utc)
    if not _utc(state["claimed_at"]) <= now < _utc(state["lease_until"]):
        raise ValueError("forecast_ingest_claim_expired")
    if state.get("retry_not_before") and now < _utc(state["retry_not_before"]):
        raise ValueError("forecast_ingest_provider_cooldown")
    if state.get("nightly_cycle") != cycle:
        raise ValueError("nightly_ingest_cycle_conflict")
    run_at = _utc(payload.get("forecast_run_at"))
    if not _utc(owner_state["claimed_at"]) <= run_at <= now:
        raise ValueError("nightly_ingest_time_invalid")
    admitted = next((a for a in owner_state.get("attempts", []) if
        a["provider"] == provider and a["attempt_id"] == attempt and a["generation"] == claim["generation"]), None)
    if not admitted or admitted.get("status") != "pending":
        raise ValueError("nightly_ingest_attempt_conflict")
    receipt = {"provider": provider, "source_id": SOURCES[provider],
        "attempt_id": attempt, "generation": claim["generation"],
        "forecast_run_at": run_at.isoformat()}
    if owner_state.get("ingest") not in (None, receipt):
        raise ValueError("nightly_ingest_already_bound")
    owner_state["ingest"] = receipt
    # This marker commits with the snapshots, or rolls back with them.
    _save_cycle(cursor, owner_state)
    return {"provider": provider, "source_id": SOURCES[provider], "generation": claim["generation"]}


NIGHTLY_CYCLE_PROVIDER = "visual_crossing"

def nightly_transition(current, payload, now):
    """One acquisition cycle per SAST night, including its bounded fallback."""
    state = deepcopy(current or {})
    attempt = _identity(payload.get("attempt_id"))
    local = now.astimezone(ZoneInfo("Africa/Johannesburg"))
    action = payload.get("action")
    if action == "nightly_claim":
        if set(payload) != {"action", "provider", "attempt_id"}:
            raise ValueError("nightly_cycle_fields_invalid")
        if (local.hour, local.minute) < (23, 30):
            return state, {"success": True, "allowed": False, "status": "nightly_not_due"}, 200, False
        cycle_date = local.date().isoformat()
        if state and str(state.get("cycle_date") or "") >= cycle_date:
            return state, {"success": True, "allowed": False, "status": "nightly_cycle_already_claimed"}, 200, False
        state = {"version": 1, "cycle_date": cycle_date,
            "operating_date": (local.date()+timedelta(days=1)).isoformat(),
            "attempt_id": attempt, "claimed_at": now.isoformat(), "status": "pending"}
        return state, {"success": True, "allowed": True, "status": "nightly_cycle_claimed",
            "cycle": deepcopy(state)}, 200, True
    if action != "nightly_result" or set(payload)-{
            "action", "provider", "attempt_id", "status", "source_id", "forecast_run_at"}:
        raise ValueError("nightly_cycle_fields_invalid")
    if state.get("attempt_id") != attempt:
        return state, {"success": False, "status": "nightly_cycle_conflict"}, 409, False
    status = payload.get("status")
    if status not in {"ingested", "failed"}:
        raise ValueError("nightly_cycle_status_invalid")
    result = {"status": status, "source_id": payload.get("source_id"),
        "forecast_run_at": payload.get("forecast_run_at")}
    if status == "ingested":
        stamp = _utc(result["forecast_run_at"])
        if result["source_id"] not in SOURCES.values() or not _utc(state["claimed_at"]) <= stamp <= now:
            raise ValueError("nightly_cycle_result_invalid")
        ingest = state.get("ingest") or {}
        if (ingest.get("source_id") != result["source_id"] or ingest.get("forecast_run_at") != stamp.isoformat()
                or not any(a.get("attempt_id") == ingest.get("attempt_id") and
                    a.get("generation") == ingest.get("generation") and a.get("status") == "ingested"
                    for a in state.get("attempts", []))):
            raise ValueError("nightly_cycle_ingest_unproven")
    if state.get("status") != "pending":
        same = state.get("result") == result
        return state, {"success": same, "status": "nightly_result_replayed" if same else "nightly_cycle_conflict"}, 200 if same else 409, False
    state.update(status=status, result=result, completed_at=now.isoformat())
    return state, {"success": True, "status": "nightly_result_recorded"}, 200, True


def _locked_cycle(cursor, cycle):
    if not isinstance(cycle, dict) or set(cycle) != {"attempt_id", "cycle_date", "operating_date"}:
        raise ValueError("nightly_cycle_required")
    cursor.execute("""select metadata,provider,source_type,active from public.telemetry_sources
        where source_id=%s for update""", (SOURCES[NIGHTLY_CYCLE_PROVIDER],))
    owner = cursor.fetchone()
    if not owner or owner[1:] != (NIGHTLY_CYCLE_PROVIDER, "forecast", True):
        raise ValueError("nightly_cycle_owner_unregistered")
    saved = (owner[0] or {}).get("forecast_nightly_cycle", {})
    if saved.get("status") != "pending" or any(saved.get(k) != cycle[k] for k in cycle):
        raise ValueError("nightly_cycle_conflict")
    return deepcopy(saved)


def _save_cycle(cursor, state):
    cursor.execute("""update public.telemetry_sources set metadata=jsonb_set(
        coalesce(metadata,'{}'::jsonb),'{forecast_nightly_cycle}',%s::jsonb,true),
        updated_at=clock_timestamp() where source_id=%s""", (json.dumps(state), SOURCES[NIGHTLY_CYCLE_PROVIDER]))


def provider_health(payload, provided_api_key="", database_url=None, *, connect_factory=None):
    from modules.telemetry.rootline_cycle_budget import cycle_budget
    from modules.oom_sakkie.bounded_postgres_read import OWNER_REQUEST_DEADLINE_SECONDS
    import time
    remaining = float(OWNER_REQUEST_DEADLINE_SECONDS)
    if isinstance(payload, dict) and "request_expires_at" in payload:
        try:
            remaining = min(remaining, (_utc(payload["request_expires_at"]) - datetime.now(timezone.utc)).total_seconds())
        except ValueError:
            return {"success": False, "status": "forecast_health_request_deadline_invalid"}, 400
        if remaining <= 0:
            return {"success": False, "status": "forecast_health_request_expired"}, 408
        payload = {key: value for key, value in payload.items() if key != "request_expires_at"}
    with cycle_budget(time.monotonic() + remaining):
        return _provider_health_locked(payload, provided_api_key, database_url, connect_factory=connect_factory)


def _provider_health_locked(payload, provided_api_key="", database_url=None, *, connect_factory=None):
    configured = os.getenv(INGEST_API_KEY_ENV, "").strip()
    if not configured:
        return {"success": False, "status": "ingest_key_not_configured"}, 503
    if not isinstance(provided_api_key, str) or not compare_digest(provided_api_key.strip().encode(), configured.encode()):
        return {"success": False, "status": "unauthorized"}, 401
    if (not isinstance(payload, dict) or not isinstance(payload.get("provider"), str)
            or payload["provider"] not in SOURCES):
        return {"success": False, "status": "forecast_provider_not_allowed"}, 400
    provider = payload["provider"]; source = SOURCES[provider]
    nightly = str(payload.get("action") or "").startswith("nightly_")
    if nightly and provider != NIGHTLY_CYCLE_PROVIDER:
        return {"success": False, "status": "nightly_cycle_owner_invalid"}, 400
    if connect_factory is None:
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_postgres
        url = database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")
        connect_factory = lambda: connect_bounded_postgres(database_url=url,
            read_only=False, enforce_transaction_local=True, connect_deadline_seconds=3)
    try:
        with connect_factory() as connection, connection.cursor() as cursor:
            cycle = payload.get("nightly_cycle")
            owner_state = None if nightly else _locked_cycle(cursor, cycle)
            cursor.execute("""select metadata,provider,source_type,active from public.telemetry_sources
                where source_id=%s for update""", (source,))
            row = cursor.fetchone()
            if not row or row[1] != provider or row[2] != "forecast" or row[3] is not True:
                return {"success": False, "status": "forecast_source_not_registered"}, 409
            metadata = row[0]
            if not isinstance(metadata, dict):
                raise ValueError("provider_health_metadata_invalid")
            cursor.execute("select clock_timestamp()")
            now = cursor.fetchone()[0].astimezone(timezone.utc)
            key = "forecast_nightly_cycle" if nightly else "forecast_provider_health"
            transition_payload = {k: v for k, v in payload.items() if k != "nightly_cycle"}
            previous = metadata.get(key, {})
            if not nightly:
                if payload.get("action") == "claim" and any(a.get("provider") == provider
                        for a in owner_state.get("attempts", [])):
                    return {"success": True, "allowed": False, "status": "nightly_provider_already_attempted",
                        "provider": provider, "source_id": source}, 200
                if payload.get("action") == "result" and previous.get("nightly_cycle") != cycle:
                    raise ValueError("nightly_provider_result_conflict")
            state, result, code, changed = (nightly_transition if nightly else transition)(previous, transition_payload, now)
            if not nightly and changed:
                state["nightly_cycle"] = deepcopy(cycle)
                attempts = owner_state.setdefault("attempts", [])
                if payload.get("action") == "claim":
                    attempts.append({"provider": provider, "attempt_id": state["attempt_id"],
                        "generation": state["generation"], "status": "pending"})
                else:
                    admitted = next((a for a in attempts if a["provider"] == provider
                        and a["attempt_id"] == state["attempt_id"] and a["generation"] == state["generation"]), None)
                    if admitted is None:
                        raise ValueError("nightly_provider_attempt_unproven")
                    if state["status"] == "ingested":
                        ingest = owner_state.get("ingest") or {}
                        if (ingest.get("attempt_id") != state["attempt_id"] or
                                ingest.get("forecast_run_at") != state["result"]["forecast_run_at"]):
                            raise ValueError("nightly_provider_ingest_unproven")
                    admitted["status"] = state["status"]
                _save_cycle(cursor, owner_state)
            if changed:
                cursor.execute("""update public.telemetry_sources set metadata=jsonb_set(
                    coalesce(metadata,'{}'::jsonb),'{forecast_provider_health}',%s::jsonb,true),
                    updated_at=clock_timestamp() where source_id=%s""".replace(
                        "{forecast_provider_health}", "{"+key+"}"), (json.dumps(state), source))
            if changed:
                # Keep the existing connect-sized margin for commit and response;
                # expiry before commit raises inside the owning transaction.
                from modules.telemetry.rootline_cycle_budget import remaining_seconds
                from modules.oom_sakkie.bounded_postgres_read import CONNECT_TIMEOUT_SECONDS
                remaining_seconds(minimum=CONNECT_TIMEOUT_SECONDS)
            return {**result, "provider": provider, "source_id": source}, code
    except ValueError as exc:
        return {"success": False, "status": str(exc)}, 400
    except Exception:
        return {"success": False, "status": "forecast_provider_health_unavailable"}, 503
