"""Append-only owner-confirmed livestock availability observation evidence."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
import re
from typing import Any, Mapping


CONTRACT_VERSION = "sam_live_stock_availability_observation_v1"
EVALUATOR_VERSION = "sam_live_stock_availability_evaluator_v1"
DATABASE_URL_ENV = "DATABASE_URL"
DEFAULT_MAX_AGE_HOURS = 24
MAX_MAX_AGE_HOURS = 48
CATEGORIES = (
    "Young Piglets",
    "Weaner Piglets",
    "Grower Pigs",
    "Finisher Pigs",
    "Ready for Slaughter",
)
AUTHORITY_FLAGS = {
    "sends_customer_message": False,
    "customer_send_allowed": False,
    "calls_telegram": False,
    "changes_ownership": False,
    "creates_quote": False,
    "creates_order": False,
    "reserves_stock": False,
    "allocates_stock": False,
    "changes_stock": False,
    "writes_farm_data": False,
    "mutates_business_state": False,
}


def build_availability_observation_preview(
    rows: list[Mapping[str, Any]],
    *,
    proposed_observed_at: str,
    max_age_hours: int = DEFAULT_MAX_AGE_HOURS,
) -> dict[str, Any]:
    """Build a privacy-safe exact cohort snapshot; this never records evidence."""
    observed_at = _parse_timestamp(proposed_observed_at)
    max_age = _bounded_max_age(max_age_hours)
    if observed_at is None:
        return _failure("authoritative_observed_at_required", 400)
    lineage = []
    totals = _empty_totals()
    exclusions: dict[str, int] = {}
    unresolved = 0
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping):
            unresolved += 1
            continue
        item = _lineage_item(row)
        lineage.append(item)
        if item["state"] == "eligible":
            bucket = totals[item["category"]]
            bucket["all"] += 1
            bucket[item["sex"] if item["sex"] in {"female", "male"} else "unknown"] += 1
        else:
            for reason in item["reasons"]:
                exclusions[reason] = exclusions.get(reason, 0) + 1
            if item["state"] == "unresolved":
                unresolved += 1
    lineage.sort(key=lambda item: item["animal_key_hash"])
    snapshot = {
        "contract_version": CONTRACT_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "observed_at_utc": observed_at.isoformat(),
        "expires_at_utc": (observed_at + timedelta(hours=max_age)).isoformat(),
        "max_age_hours": max_age,
        "lineage": lineage,
    }
    cohort_hash = _digest(snapshot)
    return {
        "success": True,
        "status": "availability_observation_preview_ready",
        "contract_version": CONTRACT_VERSION,
        "cohort_hash": cohort_hash,
        "observed_at_utc": snapshot["observed_at_utc"],
        "expires_at_utc": snapshot["expires_at_utc"],
        "max_age_hours": max_age,
        "row_count": len(lineage),
        "eligible_totals": totals,
        "exclusions": dict(sorted(exclusions.items())),
        "unresolved_count": unresolved,
        "confirmation_required": True,
        "contains_pig_ids": False,
        "_lineage": lineage,
        **AUTHORITY_FLAGS,
    }


def append_availability_observation(
    rows: list[Mapping[str, Any]],
    payload: Mapping[str, Any],
    *,
    actor_id: str,
    database_url: str | None = None,
) -> tuple[dict[str, Any], int]:
    """Append one exact owner-confirmed observation, withholding replay/conflict."""
    payload = dict(payload or {})
    actor_id = str(actor_id or "").strip()
    if not actor_id:
        return _failure("server_derived_owner_required", 403), 403
    preview = build_availability_observation_preview(
        rows,
        proposed_observed_at=payload.get("observed_at") or "",
        max_age_hours=payload.get("max_age_hours", DEFAULT_MAX_AGE_HOURS),
    )
    if not preview.get("success"):
        return preview, 400
    expected_hash = str(payload.get("cohort_hash") or "").strip()
    if not expected_hash or expected_hash != preview["cohort_hash"]:
        return _failure("availability_cohort_changed", 409), 409
    if payload.get("owner_confirmed") is not True:
        return _failure("explicit_owner_confirmation_required", 400), 400
    source = str(payload.get("source") or "").strip()
    if source not in {"owner_weighing_review", "owner_physical_stock_review"}:
        return _failure("authoritative_source_required", 400), 400
    event_id = _event_id(preview["cohort_hash"], preview["observed_at_utc"], actor_id)
    record = {
        "observation_event_id": event_id,
        "cohort_hash": preview["cohort_hash"],
        "contract_version": CONTRACT_VERSION,
        "evaluator_version": EVALUATOR_VERSION,
        "observed_at": preview["observed_at_utc"],
        "expires_at": preview["expires_at_utc"],
        "observer_principal": actor_id,
        "source": source,
        "row_count": preview["row_count"],
        "eligible_totals_json": preview["eligible_totals"],
        "exclusions_json": preview["exclusions"],
        "unresolved_count": preview["unresolved_count"],
        "lineage_json": preview["_lineage"],
    }
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return _failure("availability_observation_storage_unavailable", 503), 503
    try:
        import psycopg
        from psycopg.types.json import Jsonb

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select observation_event_id, cohort_hash
                    from public.sam_live_stock_availability_observation_events
                    where observation_event_id = %(event_id)s
                       or (observed_at = %(observed_at)s::timestamptz
                           and observer_principal = %(actor)s)
                    for update
                    """,
                    {
                        "event_id": event_id,
                        "observed_at": record["observed_at"],
                        "actor": actor_id,
                    },
                )
                existing = cursor.fetchone()
                if existing:
                    if existing[0] == event_id and existing[1] == preview["cohort_hash"]:
                        connection.rollback()
                        return _success_result(record, "availability_observation_replay_withheld"), 200
                    connection.rollback()
                    return _failure("availability_observation_conflict", 409), 409
                cursor.execute(
                    """
                    insert into public.sam_live_stock_availability_observation_events (
                        observation_event_id, cohort_hash, contract_version,
                        evaluator_version, observed_at, expires_at,
                        observer_principal, source, row_count,
                        eligible_totals_json, exclusions_json, unresolved_count,
                        lineage_json
                    ) values (
                        %(observation_event_id)s, %(cohort_hash)s,
                        %(contract_version)s, %(evaluator_version)s,
                        %(observed_at)s::timestamptz, %(expires_at)s::timestamptz,
                        %(observer_principal)s, %(source)s, %(row_count)s,
                        %(eligible_totals_json)s, %(exclusions_json)s,
                        %(unresolved_count)s, %(lineage_json)s
                    )
                    """,
                    {
                        **record,
                        "eligible_totals_json": Jsonb(record["eligible_totals_json"]),
                        "exclusions_json": Jsonb(record["exclusions_json"]),
                        "lineage_json": Jsonb(record["lineage_json"]),
                    },
                )
            connection.commit()
    except Exception as exc:
        return {
            **_failure("availability_observation_persistence_failed", 503),
            "error_type": exc.__class__.__name__,
        }, 503
    return _success_result(record, "availability_observation_recorded"), 201


def resolve_authoritative_availability(
    rows: list[Mapping[str, Any]],
    summary: Mapping[str, Any],
    *,
    database_url: str | None = None,
    now: datetime | None = None,
    expected_observation_event_id: str = "",
    expected_cohort_hash: str = "",
    expected_observed_at: str = "",
    expected_expires_at: str = "",
) -> dict[str, Any]:
    """Apply the latest exact cohort evidence without overriding newer conflicts."""
    result = dict(summary or {})
    database_url = (database_url if database_url is not None else os.getenv(DATABASE_URL_ENV, "")).strip()
    if not database_url:
        return result
    now = _aware(now or datetime.now(timezone.utc))
    try:
        row = _load_latest_observation(database_url)
    except Exception:
        return result
    if not row:
        return result
    expected = {
        "event_id": str(expected_observation_event_id or "").strip(),
        "cohort_hash": str(expected_cohort_hash or "").strip(),
        "observed_at": _parse_timestamp(expected_observed_at) if expected_observed_at else None,
        "expires_at": _parse_timestamp(expected_expires_at) if expected_expires_at else None,
    }
    observed_at = _parse_timestamp(row[2])
    expires_at = _parse_timestamp(row[3])
    if any((
        expected["event_id"] and expected["event_id"] != row[0],
        expected["cohort_hash"] and expected["cohort_hash"] != row[1],
        expected_observed_at and expected["observed_at"] != observed_at,
        expected_expires_at and expected["expires_at"] != expires_at,
    )):
        return _unavailable_result(result, row[0], "conflicting")
    if observed_at is None or expires_at is None or now > expires_at:
        return _unavailable_result(result, row[0], "stale")
    current = build_availability_observation_preview(
        rows,
        proposed_observed_at=observed_at.isoformat(),
        max_age_hours=max(1, int((expires_at - observed_at).total_seconds() // 3600)),
    )
    if not current.get("success") or current.get("cohort_hash") != row[1]:
        return _unavailable_result(result, row[0], "conflicting")
    if any((
        row[4] != current["eligible_totals"],
        row[5] != current["exclusions"],
        int(row[6] or 0) != current["unresolved_count"],
        int(row[7] or 0) != current["row_count"],
        row[8] != current["_lineage"],
    )):
        return _unavailable_result(result, row[0], "conflicting")
    return {
        **result,
        "observation_timestamp": observed_at.isoformat(),
        "observation_evidence_state": "fresh",
        "cohort_observation_event_id": row[0],
        "cohort_hash": row[1],
        "cohort_expires_at_utc": expires_at.isoformat(),
        "customer_category_counts": current["eligible_totals"],
        "customer_category_counts_complete": current["unresolved_count"] == 0,
        "cohort_exclusions": current["exclusions"],
        "evidence_complete": bool(result.get("matched_count")) and current["unresolved_count"] == 0,
    }


def _load_latest_observation(database_url: str):
    import psycopg

    with psycopg.connect(database_url, connect_timeout=10) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                select observation_event_id, cohort_hash, observed_at,
                       expires_at, eligible_totals_json, exclusions_json,
                       unresolved_count, row_count, lineage_json
                from public.sam_live_stock_availability_observation_events
                order by observed_at desc, created_at desc
                limit 1
                """
            )
            return cursor.fetchone()


def _unavailable_result(
    result: Mapping[str, Any], event_id: str, state: str
) -> dict[str, Any]:
    return {
        **result,
        "observation_evidence_state": state,
        "observation_timestamp": "",
        "evidence_complete": False,
        "customer_category_counts_complete": False,
        "cohort_observation_event_id": event_id,
    }


def _lineage_item(row: Mapping[str, Any]) -> dict[str, Any]:
    identity = str(row.get("pig_id") or "").strip()
    category = _category(row)
    sex = _sex(row.get("sex"))
    reasons = _exclusion_reasons(row, category)
    state = "eligible" if not reasons else "unresolved" if "identity_or_category_unavailable" in reasons else "excluded"
    stable = {
        "animal_key_hash": _animal_hash(identity),
        "category": category,
        "sex": sex,
        "state": state,
        "reasons": sorted(reasons),
        "individual_observed_at": _canonical_optional_timestamp(
            row.get("eligibility_observed_at")
        ),
    }
    stable["row_fingerprint"] = _digest(stable)
    return stable


def _exclusion_reasons(row: Mapping[str, Any], category: str) -> list[str]:
    reasons = []
    if not str(row.get("pig_id") or "").strip() or not category:
        reasons.append("identity_or_category_unavailable")
    if row.get("live_stock_sale_eligible") is not True:
        reasons.append("not_sale_eligible")
    if row.get("evidence_complete") is not True:
        reasons.append("eligibility_evidence_incomplete")
    if _normal(row.get("purpose")) != "sale":
        reasons.append("purpose_not_sale")
    if _normal(row.get("allocation_evidence_state")) != "known unallocated":
        reasons.append("allocation_unavailable_or_conflicting")
    if _normal(row.get("reserved_status")) != "not reserved":
        reasons.append("reserved_or_reservation_unknown")
    if _normal(row.get("medical_status")) != "clear":
        reasons.append("medical_clearance_unavailable")
    if _normal(row.get("withdrawal_evidence_state")) not in {"not applicable", "cleared"}:
        reasons.append("withdrawal_clearance_unavailable")
    if _normal(row.get("status")) in {"sold", "exited", "dead", "terminal"}:
        reasons.append("sale_or_movement_state_excluded")
    if _normal(row.get("on_farm")) not in {"", "yes", "true", "1", "on farm"}:
        reasons.append("not_confirmed_on_farm")
    return sorted(set(reasons))


def _category(row: Mapping[str, Any]) -> str:
    for key in ("sale_category", "suggested_price_category", "calculated_stage", "weight_band"):
        text = _normal(row.get(key))
        if "weaner" in text:
            return "Weaner Piglets"
        if "young" in text or ("piglet" in text and "weaner" not in text):
            return "Young Piglets"
        if "grower" in text:
            return "Grower Pigs"
        if "finisher" in text:
            return "Finisher Pigs"
        if "slaughter" in text:
            return "Ready for Slaughter"
    return ""


def _sex(value: Any) -> str:
    text = _normal(value)
    if text in {"female", "gilt", "sow"}:
        return "female"
    if text in {"male", "boar"}:
        return "male"
    return "unknown"


def _empty_totals() -> dict[str, dict[str, int]]:
    return {
        category: {"all": 0, "female": 0, "male": 0, "unknown": 0}
        for category in CATEGORIES
    }


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return None
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.astimezone(timezone.utc)


def _canonical_optional_timestamp(value: Any) -> str:
    parsed = _parse_timestamp(value)
    return parsed.isoformat() if parsed else ""


def _aware(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone_aware_now_required")
    return value.astimezone(timezone.utc)


def _normal(value: Any) -> str:
    return " ".join(str(value or "").replace("_", " ").strip().casefold().split())


def _bounded_max_age(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_AGE_HOURS
    return min(max(parsed, 1), MAX_MAX_AGE_HOURS)


def _animal_hash(identity: str) -> str:
    if not identity:
        return ""
    return hashlib.sha256(f"sam-live-stock-animal-v1:{identity}".encode()).hexdigest()


def _digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode()).hexdigest()


def _event_id(cohort_hash: str, observed_at: str, actor_id: str) -> str:
    token = _digest(
        {
            "domain": "sam-live-stock-availability-observation-event-v1",
            "cohort_hash": cohort_hash,
            "observed_at": observed_at,
            "actor_id": actor_id,
        }
    )
    return f"SAM-LIVE-STOCK-AVAIL-{token[:24].upper()}"


def _success_result(record: Mapping[str, Any], status: str) -> dict[str, Any]:
    return {
        "success": True,
        "status": status,
        "observation_event_id": record["observation_event_id"],
        "cohort_hash": record["cohort_hash"],
        "observed_at_utc": record["observed_at"],
        "expires_at_utc": record["expires_at"],
        "eligible_totals": record["eligible_totals_json"],
        "exclusions": record["exclusions_json"],
        "unresolved_count": record["unresolved_count"],
        "contains_pig_ids": False,
        **AUTHORITY_FLAGS,
    }


def _failure(status: str, _code: int) -> dict[str, Any]:
    return {
        "success": False,
        "status": status,
        "contains_pig_ids": False,
        **AUTHORITY_FLAGS,
    }
