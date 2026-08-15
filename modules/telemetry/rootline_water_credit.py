"""Append-only measured ROOTLINE irrigation water-credit lifecycle."""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os

CONTRACT = "rootline_water_credit.v1"
ZONES = {"B12345", "C12345"}
METHODS = {"measured_volume", "governed_calibration"}


def build_water_credit(*, execution, physical_acceptance, measurement=None,
                       calibration=None, recorded_at=None):
    execution = dict(execution or {}); acceptance = dict(physical_acceptance or {})
    zone = str(execution.get("zone_id") or "")
    execution_id = str(execution.get("execution_id") or "")
    acceptance_digest = str(acceptance.get("acceptance_sha256") or "")
    if not (_completed(execution) and zone in ZONES and execution_id
            and len(acceptance_digest) == 64 and _accepts(acceptance, execution_id, zone)):
        return _unknown(execution_id, zone, "canonical_execution_or_physical_acceptance_unproven")
    litres = None; method = None; evidence_id = None; calibration_id = None
    measured = dict(measurement or {}); calibrated = dict(calibration or {})
    if _positive(measured.get("measured_volume_litres")) and measured.get("verified") is True:
        litres = float(measured["measured_volume_litres"]); method = "measured_volume"
        evidence_id = str(measured.get("measurement_id") or measured.get("evidence_id") or "")
    elif (_positive(calibrated.get("litres_per_minute")) and calibrated.get("verified") is True
          and str(calibrated.get("zone_id") or "") == zone):
        litres = float(calibrated["litres_per_minute"]) * float(execution["verified_runtime_seconds"]) / 60
        method = "governed_calibration"
        calibration_id = str(calibrated.get("calibration_id") or calibrated.get("evidence_id") or "")
        evidence_id = str(calibrated.get("evidence_digest") or calibrated.get("evidence_sha256") or "")
    if (not litres or not evidence_id or (method == "governed_calibration"
            and (not calibration_id or len(evidence_id) != 64))):
        return _unknown(execution_id, zone, "measured_volume_or_supported_calibration_required")
    material = {"contract_version": CONTRACT, "execution_id": execution_id, "zone_id": zone,
        "verified_runtime_seconds": int(execution["verified_runtime_seconds"]),
        "physical_acceptance_sha256": acceptance_digest, "credit_method": method,
        "measurement_evidence_id": evidence_id, "calibration_id": calibration_id,
        "delivered_volume_litres": round(litres, 3),
        "provider_evidence": {"start_state": "ON", "shutdown_state": "OFF",
            "shutdown_verified": True},
        "owner_observed_evidence": {"normal_flow": True, "normal_stopped_flow": True,
            "physically_off_now": True},
        "recorded_at": _aware(recorded_at or datetime.now(timezone.utc)).isoformat(),
        "writes_irrigation_history": False, "rewrites_debt": False,
        "hardware_control": False, "provider_control": False}
    identity_material = {key: material[key] for key in (
        "contract_version", "execution_id", "zone_id", "physical_acceptance_sha256",
        "credit_method", "measurement_evidence_id", "calibration_id")}
    material["credit_id"] = "ROOTLINE-WATER-CREDIT-" + _digest(identity_material)[:24].upper()
    material["credit_sha256"] = _digest(material)
    return {"status": "Available", **material}


def append_water_credit(value, database_url=None):
    if not validate_water_credit(value):
        return {"success": False, "created": False, "status": "invalid_water_credit"}
    import psycopg
    url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
    with psycopg.connect(url, connect_timeout=8) as connection:
        with connection.cursor() as cursor:
            cursor.execute("select public.rootline_append_water_credit_event(%s,%s,%s,%s,%s,%s::jsonb)",
                (value["credit_id"], value["execution_id"], value["zone_id"],
                 value["physical_acceptance_sha256"], value["credit_sha256"],
                 json.dumps(value, sort_keys=True, separators=(",", ":"))))
            created = bool(cursor.fetchone()[0])
    return {"success": True, "created": created,
        "status": "recorded" if created else "exact_replay", "credit_id": value["credit_id"]}


def record_water_credit(*, execution_id, physical_acceptance_sha256, volume_evidence_id,
                        database_url=None, recorded_at=None):
    """Load immutable canonical evidence before attempting one append."""
    from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
    url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
    try:
        with connect_bounded_rootline_postgres(database_url=url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select review_json->'rootline_execution'
                  from public.sam_live_stock_conversation_review_events
                 where event_source='rootline_irrigation_execution'
                   and review_json->'rootline_execution'->>'execution_id'=%s
                   and review_json->'rootline_execution'->>'action'='record_completed'
                 order by created_at desc limit 1""", (execution_id,))
                row = cursor.fetchone(); execution = row[0] if row else None
                cursor.execute("""select review_json->'rootline_physical_acceptance'
                  from public.sam_live_stock_conversation_review_events
                 where event_source='rootline_physical_acceptance'
                   and review_json->'rootline_physical_acceptance'->>'acceptance_sha256'=%s
                   and review_json->'rootline_physical_acceptance'->>'action'='record_acceptance'
                 order by created_at desc limit 1""", (physical_acceptance_sha256,))
                row = cursor.fetchone(); acceptance = row[0] if row else None
                cursor.execute("""select evidence_json from public.irrigation_water_volume_evidence
                    where evidence_id=%s limit 1""", (volume_evidence_id,))
                row = cursor.fetchone(); volume_evidence = row[0] if row else None
    except Exception as exc:
        return {"success": False, "created": False, "status": "canonical_evidence_unavailable",
            "reason": exc.__class__.__name__, "hardware_commands": 0, "provider_control_calls": 0}
    evidence = dict(volume_evidence or {})
    value = build_water_credit(execution=execution, physical_acceptance=acceptance,
        measurement=evidence if evidence.get("evidence_type") == "measured_volume" else None,
        calibration=evidence if evidence.get("evidence_type") == "governed_calibration" else None,
        recorded_at=recorded_at)
    if value.get("status") != "Available":
        return {"success": False, "created": False, **value,
            "hardware_commands": 0, "provider_control_calls": 0}
    return {**append_water_credit(value, url), "water_credit": value,
        "hardware_commands": 0, "provider_control_calls": 0}


def read_water_credits(database_url=None, *, connect=None):
    if connect is None:
        from modules.oom_sakkie.bounded_postgres_read import connect_bounded_rootline_postgres
        url = str(database_url or os.getenv("DATABASE_URL") or "").strip()
        connect = lambda: connect_bounded_rootline_postgres(database_url=url)
    try:
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select credit_json from public.irrigation_water_credit_events
                    order by created_at, credit_id""")
                rows = [dict(row[0]) for row in cursor.fetchall()]
        return project_water_credits(rows)
    except Exception as exc:
        return {"status": "Unavailable", "contract_version": CONTRACT,
            "reason": exc.__class__.__name__, "credits": [], "by_execution": {}}


def project_water_credits(rows):
    valid = [dict(row) for row in rows or [] if validate_water_credit(row)]
    by_execution = {row["execution_id"]: row for row in valid}
    return {"status": "Available", "contract_version": CONTRACT,
        "credits": valid, "by_execution": by_execution,
        "total_delivered_volume_litres": round(sum(row["delivered_volume_litres"] for row in valid), 3),
        "unknown_until_supported_evidence": True}


def water_balance_outcomes(projection):
    """Measured credit adapter for the existing water-balance calculator."""
    return [{"execution_id": row["execution_id"], "zone_id": row["zone_id"],
        "completed_at": row["recorded_at"], "shutdown_verified": True,
        "verified_runtime_minutes": row["verified_runtime_seconds"] / 60,
        "measured_volume_l": row["delivered_volume_litres"]}
        for row in (projection or {}).get("credits", []) if validate_water_credit(row)]


def validate_water_credit(value):
    if not isinstance(value, dict) or value.get("contract_version") != CONTRACT:
        return False
    supplied = value.get("credit_sha256")
    material = {key: item for key, item in value.items() if key not in {"status", "credit_sha256"}}
    identity = {key: material.get(key) for key in (
        "contract_version", "execution_id", "zone_id", "physical_acceptance_sha256",
        "credit_method", "measurement_evidence_id", "calibration_id")}
    return (material.get("zone_id") in ZONES and material.get("credit_method") in METHODS
        and _positive(material.get("delivered_volume_litres"))
        and material.get("credit_id") == "ROOTLINE-WATER-CREDIT-" + _digest(identity)[:24].upper()
        and supplied == _digest(material))


def _completed(row):
    return (row.get("state") == "Completed" and row.get("shutdown_verified") is True
        and int(row.get("verified_runtime_seconds") or 0) > 0
        and (row.get("start_evidence") or {}).get("state") == "ON"
        and (row.get("shutdown_evidence") or {}).get("state") == "OFF")


def _accepts(row, execution_id, zone):
    return any(item.get("execution_id") == execution_id and item.get("zone_id") == zone
        and item.get("water_flow") == "normal" and item.get("stopped_flow") == "normal"
        and item.get("physically_off_now") is True for item in row.get("observations") or [])


def _unknown(execution_id, zone, reason):
    return {"status": "Unknown", "contract_version": CONTRACT, "execution_id": execution_id or None,
        "zone_id": zone or None, "delivered_volume_litres": "Unknown", "reason": reason,
        "hardware_control": False, "provider_control": False, "writes_farm_data": False}


def _positive(value):
    try: return float(value) > 0
    except (TypeError, ValueError): return False


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _aware(value):
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
