"""Append-only factual human observations for Breeding Attention."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from services.database_service import DATABASE_URL_ENV

CONTRACT_VERSION = "herdmaster_breeding_observation_v1"
FARM_DATABASE_URL_ENV = "FARM_SUPABASE_DATABASE_URL"
HEAT_FRESH_HOURS = 48
BODY_CONDITION_FRESH_DAYS = 30
MAX_PIG_ID_LENGTH = 128
MAX_IDEMPOTENCY_LENGTH = 200
MAX_NOTE_LENGTH = 1000
MAX_FOLLOW_UP_LENGTH = 500
VISIBLE_BUILD = {"not_recorded", "even", "lean", "heavy", "concern"}
FEET_LEGS = {"not_recorded", "no_visible_concern", "concern"}
INJURY = {"not_recorded", "none_observed", "concern"}
HEAT = {"not_recorded", "observed", "not_observed"}
TEMPERAMENT = {"not_recorded", "calm", "watchful", "difficult", "concern"}
SUITABILITY = {"not_recorded", "none_observed", "concern"}


def observation_event_id(idempotency_key):
    return "HERD-OBS-" + uuid.uuid5(
        uuid.NAMESPACE_URL, str(idempotency_key or "")
    ).hex.upper()


def _result(success, status, **extra):
    return {
        "success": success,
        "status": status,
        "contract_version": CONTRACT_VERSION,
        "append_only": True,
        "advisory_only": True,
        "creates_mating": False,
        "asserts_pregnancy": False,
        "asserts_heat": False,
        "changes_medical": False,
        "changes_lifecycle": False,
        "changes_purpose": False,
        "changes_movement": False,
        "changes_availability": False,
        "changes_retirement": False,
        "schedules_core_work": False,
        "contacts_customer": False,
        "changes_farm_state": False,
        **extra,
    }


def _database_url(explicit=None):
    return str(explicit or "").strip() or (
        os.getenv(FARM_DATABASE_URL_ENV, "").strip()
        or os.getenv(DATABASE_URL_ENV, "").strip()
    )


def _connection(database_url=None, connect_factory=None):
    url = _database_url(database_url)
    if connect_factory:
        return connect_factory(url)
    if not url:
        raise RuntimeError("observation store unavailable")
    import psycopg
    return psycopg.connect(
        url,
        connect_timeout=3,
        options="-c statement_timeout=3000",
    )


def _instant(value, now):
    try:
        parsed = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
        if parsed.tzinfo is None or parsed > now:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def validate_observation(payload, *, now=None):
    payload = payload if isinstance(payload, dict) else {}
    now = now or datetime.now(timezone.utc)
    observed_at = _instant(payload.get("observed_at"), now)
    note = str(payload.get("factual_note") or "").strip()
    follow_up = str(payload.get("follow_up") or "").strip()
    idem = str(payload.get("idempotency_key") or "").strip()
    pig_id = str(payload.get("pig_id") or "").strip()
    supersedes = str(payload.get("supersedes_observation_event_id") or "").strip()
    if (
        len(pig_id) > MAX_PIG_ID_LENGTH
        or len(idem) > MAX_IDEMPOTENCY_LENGTH
        or len(note) > MAX_NOTE_LENGTH
        or len(follow_up) > MAX_FOLLOW_UP_LENGTH
        or len(supersedes) > MAX_PIG_ID_LENGTH
    ):
        return None, "observation_evidence_too_long"
    measurements = {
        "contract_version": CONTRACT_VERSION,
        "visible_build": str(payload.get("visible_build") or "not_recorded").strip().lower(),
        "feet_legs_movement": str(payload.get("feet_legs_movement") or "not_recorded").strip().lower(),
        "visible_injury": str(payload.get("visible_injury") or "not_recorded").strip().lower(),
        "standing_heat": str(payload.get("standing_heat") or "not_recorded").strip().lower(),
        "temperament": str(payload.get("temperament") or "not_recorded").strip().lower(),
        "suitability_concern": str(payload.get("suitability_concern") or "not_recorded").strip().lower(),
        "follow_up": follow_up,
    }
    score = payload.get("body_condition_score")
    if score not in (None, ""):
        if isinstance(score, bool):
            score = None
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = None
        if score is None or not 1 <= score <= 5:
            return None, "invalid_body_condition_score"
        measurements["body_condition_score"] = score
    allowed = (
        (measurements["visible_build"], VISIBLE_BUILD),
        (measurements["feet_legs_movement"], FEET_LEGS),
        (measurements["visible_injury"], INJURY),
        (measurements["standing_heat"], HEAT),
        (measurements["temperament"], TEMPERAMENT),
        (measurements["suitability_concern"], SUITABILITY),
    )
    if any(value not in vocabulary for value, vocabulary in allowed):
        return None, "invalid_observation_value"
    if not pig_id or not idem or not note or observed_at is None:
        return None, "observation_evidence_required"
    if (
        "body_condition_score" not in measurements
        and all(measurements[key] == "not_recorded" for key in (
            "visible_build", "feet_legs_movement", "visible_injury",
            "standing_heat", "temperament", "suitability_concern",
        ))
    ):
        return None, "factual_measurement_required"
    return {
        "pig_id": pig_id,
        "observed_at": observed_at,
        "factual_note": note,
        "follow_up": follow_up,
        "idempotency_key": idem,
        "supersedes_observation_event_id": supersedes or None,
        "measurements": measurements,
    }, ""


def _advisory_preview(clean, authoritative_attention, hypothetical_attention):
    required = (
        "current_state", "filter_state", "recommended_human_action",
        "missing_facts", "conflicting_facts",
    )
    def bounded(row):
        if (
            not isinstance(row, dict)
            or str(row.get("pig_id") or "") != clean["pig_id"]
            or any(key not in row for key in required)
            or not isinstance(row["missing_facts"], list)
            or not isinstance(row["conflicting_facts"], list)
        ):
            return None
        return {
            "state": str(row["current_state"]),
            "filter_state": str(row["filter_state"]),
            "recommended_human_action": str(row["recommended_human_action"]),
            "missing_facts": sorted({str(item) for item in row["missing_facts"]}),
            "conflicting_facts": sorted({
                str(item) for item in row["conflicting_facts"]
            }),
        }
    before = bounded(authoritative_attention)
    after = bounded(hypothetical_attention)
    return (
        {"before": before, "after_if_recorded": after}
        if before is not None and after is not None else None
    )


def preview_observation(
    payload, *, authoritative_attention=None, hypothetical_attention=None,
    now=None,
):
    now = now or datetime.now(timezone.utc)
    clean, error = validate_observation(payload, now=now)
    if error:
        return _result(False, error), 400
    advisory_change = _advisory_preview(
        clean, authoritative_attention, hypothetical_attention
    )
    if advisory_change is None:
        return _result(False, "current_attention_evidence_unavailable"), 503
    effects = []
    heat_fresh = clean["observed_at"] >= now - timedelta(hours=HEAT_FRESH_HOURS)
    body_condition_fresh = clean["observed_at"] >= now - timedelta(
        days=BODY_CONDITION_FRESH_DAYS
    )
    if body_condition_fresh and "body_condition_score" in clean["measurements"]:
        effects.append("Body-condition evidence becomes current.")
    if heat_fresh and clean["measurements"]["standing_heat"] == "observed":
        effects.append("A time-bound standing-heat sign is shown as observed evidence.")
    if not effects:
        effects.append("The factual history is extended; no current readiness fact changes.")
    return _result(
        True,
        "observation_preview",
        observed={
            "observation_time": clean["observed_at"].isoformat(),
            "measurements": clean["measurements"],
            "factual_note": clean["factual_note"],
        },
        owner_interpretation="Not recorded by this operation.",
        system_recommendation={
            "effect": effects,
            "advisory_change": advisory_change,
            "freshness": {
                "body_condition": (
                    "Fresh" if "body_condition_score" in clean["measurements"]
                    and body_condition_fresh else
                    "Stale" if "body_condition_score" in clean["measurements"]
                    else "Unknown"
                ),
                "standing_heat": (
                    "Fresh" if clean["measurements"]["standing_heat"] != "not_recorded"
                    and heat_fresh else
                    "Stale" if clean["measurements"]["standing_heat"] != "not_recorded"
                    else "Unknown"
                ),
            },
            "proposal_only": True,
            "attention_recalculation_required": False,
        },
    ), 200


def list_observations(pig_id, *, database_url=None, connect_factory=None, now=None):
    pig_id = str(pig_id or "").strip()
    if not pig_id:
        return _result(False, "pig_id_required"), 400
    try:
        with _connection(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select observation_event_id, observed_at, recorded_at,
                           observation_category, severity, factual_note,
                           measurements_json, source_reference,
                           supersedes_observation_event_id
                    from public.pig_observation_events
                    where pig_id=%s
                      and measurements_json->>'contract_version'=%s
                    order by observed_at desc, recorded_at desc, observation_event_id
                """, (pig_id, CONTRACT_VERSION))
                rows = cursor.fetchall()
    except Exception:
        return _result(False, "observation_store_unavailable"), 503
    now = now or datetime.now(timezone.utc)
    superseded = {row[8] for row in rows if row[8]}
    history = [{
        "observation_event_id": row[0],
        "observed_at": row[1].isoformat(),
        "recorded_at": row[2].isoformat(),
        "category": row[3],
        "severity": row[4],
        "factual_note": row[5],
        "measurements": row[6] if isinstance(row[6], dict) else {},
        "source_reference": row[7],
        "supersedes_observation_event_id": row[8],
        "superseded": row[0] in superseded,
        "freshness": {
            "body_condition": (
                "Fresh" if "body_condition_score" in (
                    row[6] if isinstance(row[6], dict) else {}
                ) and row[1] >= now - timedelta(days=BODY_CONDITION_FRESH_DAYS)
                else "Stale" if "body_condition_score" in (
                    row[6] if isinstance(row[6], dict) else {}
                ) else "Unknown"
            ),
            "standing_heat": (
                "Fresh" if (
                    row[6] if isinstance(row[6], dict) else {}
                ).get("standing_heat") in {"observed", "not_observed"}
                and row[1] >= now - timedelta(hours=HEAT_FRESH_HOURS)
                else "Stale" if (
                    row[6] if isinstance(row[6], dict) else {}
                ).get("standing_heat") in {"observed", "not_observed"}
                else "Unknown"
            ),
        },
    } for row in rows]
    return _result(True, "observations_available", pig_id=pig_id, history=history), 200


def observation_by_idempotency(idempotency_key, *, database_url=None,
                               connect_factory=None):
    """Read the exact committed event needed to replay a lost response."""
    key = str(idempotency_key or "").strip()
    if not key:
        return None, 400
    try:
        with _connection(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""select observation_event_id,pig_id,
                          supersedes_observation_event_id,observed_at
                    from public.pig_observation_events where idempotency_key=%s""", (key,))
                row = cursor.fetchone()
    except Exception:
        return None, 503
    return (None, 404) if not row else ({"observation_event_id": row[0],
        "pig_id": row[1], "supersedes_observation_event_id": row[2],
        "observed_at": row[3].isoformat()}, 200)


def record_observation(
    payload, *, actor_id, database_url=None, connect_factory=None, now=None
):
    actor_id = str(actor_id or "").strip()
    if not actor_id:
        return _result(False, "owner_identity_required"), 403
    now = now or datetime.now(timezone.utc)
    clean, error = validate_observation(payload, now=now)
    if error:
        return _result(False, error), 400
    canonical = {
        "version": CONTRACT_VERSION,
        "pig_id": clean["pig_id"],
        "observed_at": clean["observed_at"].isoformat(),
        "factual_note": clean["factual_note"],
        "measurements": clean["measurements"],
        "actor_id": actor_id,
        "supersedes_observation_event_id": clean["supersedes_observation_event_id"],
    }
    digest = hashlib.sha256(json.dumps(
        canonical, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    event_id = observation_event_id(clean["idempotency_key"])
    try:
        with _connection(database_url, connect_factory) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("herdmaster-breeding-observation-pig:" + clean["pig_id"],),
                )
                cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("herdmaster-breeding-observation:" + clean["idempotency_key"],),
                )
                cursor.execute("""
                    select pig.pig_id
                    from public.pigs pig
                    where pig.pig_id=%s and pig.status='Active'
                      and pig.on_farm is true and pig.sex='Female'
                      and pig.animal_type in ('Sow','Gilt')
                      and exists (
                        select 1 from public.current_canonical_pigs current_pig
                        where current_pig.pig_id=pig.pig_id
                      )
                    for share of pig
                """, (clean["pig_id"],))
                if not cursor.fetchone():
                    return _result(False, "current_sow_or_gilt_required"), 409
                cursor.execute("""
                    select observation_event_id, pig_id, observed_at,
                           observer_reference, factual_note, measurements_json,
                           supersedes_observation_event_id
                    from public.pig_observation_events
                    where idempotency_key=%s
                """, (clean["idempotency_key"],))
                existing = cursor.fetchone()
                if existing:
                    existing_canonical = {
                        "version": CONTRACT_VERSION, "pig_id": existing[1],
                        "observed_at": existing[2].isoformat(),
                        "factual_note": existing[4],
                        "measurements": existing[5],
                        "actor_id": existing[3],
                        "supersedes_observation_event_id": existing[6],
                    }
                    existing_digest = hashlib.sha256(json.dumps(
                        existing_canonical, sort_keys=True, separators=(",", ":")
                    ).encode()).hexdigest()
                    if existing_digest != digest:
                        return _result(False, "observation_idempotency_conflict"), 409
                    return _result(
                        True, "observation_replayed_withheld",
                        observation_event_id=existing[0],
                    ), 200
                if clean["supersedes_observation_event_id"]:
                    cursor.execute("""
                        select 1 from public.pig_observation_events prior
                        where prior.observation_event_id=%s and prior.pig_id=%s
                          and prior.measurements_json->>'contract_version'=%s
                          and not exists (
                            select 1 from public.pig_observation_events correction
                            where correction.supersedes_observation_event_id =
                                  prior.observation_event_id
                          )
                    """, (
                        clean["supersedes_observation_event_id"],
                        clean["pig_id"],
                        CONTRACT_VERSION,
                    ))
                    if not cursor.fetchone():
                        return _result(False, "invalid_supersession"), 409
                cursor.execute("""
                    insert into public.pig_observation_events(
                        observation_event_id,pig_id,observed_at,
                        observer_reference,observation_category,severity,
                        factual_note,measurements_json,source_system,
                        source_reference,idempotency_key,
                        supersedes_observation_event_id
                    ) values (%s,%s,%s,%s,'other','informational',%s,%s::jsonb,
                              'owner',%s,%s,%s)
                    returning observation_event_id
                """, (
                    event_id, clean["pig_id"], clean["observed_at"], actor_id,
                    clean["factual_note"], json.dumps(clean["measurements"]),
                    digest, clean["idempotency_key"],
                    clean["supersedes_observation_event_id"],
                ))
                cursor.fetchone()
    except Exception:
        return _result(False, "observation_store_unavailable"), 503
    return _result(
        True, "observation_recorded", observation_event_id=event_id
    ), 201
