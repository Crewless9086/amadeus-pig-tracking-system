"""Append-only owner evidence for Riversdale candidate reviews."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from services.database_service import DATABASE_URL_ENV

VERSION = "riversdale_candidate_review_v1"
WITHDRAWAL_STATES = {"not_applicable", "cleared", "hold", "unknown"}
QUALITY_STATES = {"suitable", "hold", "unknown"}
FARM_DATABASE_URL_ENV = "FARM_SUPABASE_DATABASE_URL"
REVIEW_FRESH_HOURS = 72


def _result(ok, status, **extra):
    return {
        "success": ok, "status": status, "review_contract_version": VERSION,
        "creates_cohort": False, "creates_outlet_assignment": False,
        "creates_reservation": False, "books_auction": False, "creates_sale": False,
        "sends_reminder": False, "contacts_customer": False,
        "changes_medical_record": False, "changes_lifecycle": False,
        "changes_purpose": False, "changes_farm_state": False, **extra,
    }


def _resolve_database_url(database_url=None):
    if database_url is not None:
        return str(database_url).strip()
    return (
        os.getenv(FARM_DATABASE_URL_ENV, "").strip()
        or os.getenv(DATABASE_URL_ENV, "").strip()
    )


def _withdrawal_state(rows, *, today):
    if not rows:
        return "unknown"
    active = any(row[2] is not None and row[2] > today for row in rows)
    incomplete = any(row[1] is None and row[2] is None for row in rows)
    ended = any(row[2] is not None and row[2] <= today for row in rows)
    if active:
        return "hold"
    if incomplete:
        return "unknown"
    if ended:
        return "cleared"
    if all(row[1] == 0 for row in rows):
        return "not_applicable"
    return "unknown"


def read_latest_candidate_reviews(
    *, auction_cycle_id, pig_ids, database_url=None, connect_factory=None
):
    ids = sorted({str(value).strip() for value in pig_ids if str(value).strip()})
    if not auction_cycle_id or not ids:
        return {}, 200
    url = _resolve_database_url(database_url)
    if not url and connect_factory is None:
        return {}, 503
    try:
        factory = (
            (lambda: connect_factory(url))
            if connect_factory
            else (lambda: __import__("psycopg").connect(
                url, connect_timeout=3, options="-c statement_timeout=3000"
            ))
        )
        with factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    select
                      pig_id,review_id,withdrawal_state,quality_state,observed_at,
                      observation_event_id,follow_up,recorded_at
                    from public.riversdale_auction_candidate_reviews
                    where auction_cycle_id=%s and pig_id=any(%s)
                    order by pig_id,observed_at desc,recorded_at desc,review_id
                """, (auction_cycle_id, ids))
                rows = cursor.fetchall()
        now = datetime.now(timezone.utc)
        grouped = {}
        for row in rows:
            grouped.setdefault(row[0], []).append(row)
        result = {}
        for pig_id, pig_rows in grouped.items():
            row = pig_rows[0]
            equal_time = [
                item for item in pig_rows if item[4] == row[4]
            ]
            conflicting_head = len({
                (item[2], item[3], item[5]) for item in equal_time
            }) > 1
            result[pig_id] = {
                "review_id": row[1], "withdrawal_state": row[2],
                "quality_state": (
                    "unknown" if conflicting_head else row[3]
                ),
                "observed_at": row[4].isoformat(),
                "observation_event_id": row[5], "follow_up": row[6],
                "recorded_at": row[7].isoformat(),
                "fresh": (
                    not conflicting_head
                    and
                    row[4] <= now
                    and row[4] >= now - timedelta(hours=REVIEW_FRESH_HOURS)
                ),
                "evidence_conflict": conflicting_head,
            }
        return result, 200
    except Exception:
        return {}, 503


def record_candidate_review(
    payload, *, actor_id, candidate_ids=None, candidate_loader=None,
    database_url=None, connect_factory=None
):
    payload = payload if isinstance(payload, dict) else {}
    actor_id = str(actor_id or "").strip()
    pig_id = str(payload.get("pig_id") or "").strip()
    auction_cycle_id = str(payload.get("auction_cycle_id") or "").strip()
    withdrawal = str(payload.get("withdrawal_state") or "unknown").strip().lower()
    quality = str(payload.get("quality_state") or "unknown").strip().lower()
    observed_at = str(payload.get("observed_at") or "").strip()
    idem = str(payload.get("idempotency_key") or "").strip()
    follow_up = str(payload.get("follow_up") or "").strip()
    factual_note = str(payload.get("physical_observation") or "").strip()
    if not actor_id:
        return _result(False, "owner_identity_required"), 403
    if candidate_loader is None and pig_id not in set(candidate_ids or []):
        return _result(False, "candidate_not_in_current_preview"), 409
    if withdrawal not in WITHDRAWAL_STATES or quality not in QUALITY_STATES:
        return _result(False, "invalid_review_state"), 400
    if not auction_cycle_id or not idem or not observed_at or not factual_note:
        return _result(False, "review_evidence_required"), 400
    try:
        instant = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant > datetime.now(timezone.utc):
            raise ValueError
    except ValueError:
        return _result(False, "invalid_observation_time"), 400
    canonical = {
        "version": VERSION, "pig_id": pig_id,
        "auction_cycle_id": auction_cycle_id,
        "withdrawal_state": withdrawal,
        "quality_state": quality, "observed_at": instant.isoformat(),
        "medical_evidence_refs": [],
        "follow_up": follow_up, "physical_observation": factual_note, "actor_id": actor_id,
    }
    review_id = "RIV-REVIEW-" + uuid.uuid5(uuid.NAMESPACE_URL, idem).hex.upper()
    observation_id = "RIV-OBS-" + uuid.uuid5(uuid.NAMESPACE_URL, idem).hex.upper()
    url = _resolve_database_url(database_url)
    if not url and connect_factory is None:
        return _result(False, "review_store_unavailable"), 503
    try:
        factory = (
            (lambda: connect_factory(url))
            if connect_factory
            else (lambda: __import__("psycopg").connect(
                url, connect_timeout=3, options="-c statement_timeout=3000"
            ))
        )
        with factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select pg_advisory_xact_lock(
                         hashtextextended('riversdale-auction-cycle',0)
                       )"""
                )
                cursor.execute("""lock table
                    public.pigs,public.pig_weight_events,public.pig_medical_events,
                    public.orders,public.order_lines,public.litters,public.pens
                    in share mode""")
                cursor.execute(
                    """select auction_cycle_id from public.riversdale_auction_cycles
                       where operating_confirmed is true
                       order by owner_confirmed_at desc limit 1"""
                )
                cycle = cursor.fetchone()
                if not cycle or cycle[0] != auction_cycle_id:
                    return _result(False, "auction_review_stale_cycle"), 409
                if candidate_loader is not None:
                    current_candidate_ids = set(
                        candidate_loader(connection, auction_cycle_id) or []
                    )
                    if pig_id not in current_candidate_ids:
                        return _result(
                            False, "candidate_not_in_current_preview"
                        ), 409
                cursor.execute(
                    "select pg_advisory_xact_lock(hashtextextended(%s,0))",
                    ("riversdale-candidate-review:" + idem,),
                )
                cursor.execute(
                    """select medical_event_id,withdrawal_days,withdrawal_end_date
                       from public.pig_medical_events
                       where pig_id=%s
                       order by treatment_date desc,created_at desc,medical_event_id""",
                    (pig_id,),
                )
                medical_rows = cursor.fetchall()
                derived_withdrawal = _withdrawal_state(
                    medical_rows, today=datetime.now(timezone.utc).date()
                )
                if withdrawal != derived_withdrawal:
                    return _result(
                        False, "withdrawal_evidence_conflict",
                        authoritative_withdrawal_state=derived_withdrawal,
                    ), 409
                canonical["withdrawal_state"] = derived_withdrawal
                canonical["medical_evidence_refs"] = sorted(
                    str(row[0]) for row in medical_rows if row[0]
                )
                digest = hashlib.sha256(
                    json.dumps(
                        canonical, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest()
                cursor.execute(
                    """select review_id,review_hash
                       from public.riversdale_auction_candidate_reviews
                       where idempotency_key=%s""",
                    (idem,),
                )
                existing = cursor.fetchone()
                if existing:
                    if existing[1] != digest:
                        return _result(
                            False, "review_idempotency_conflict"
                        ), 409
                    return _result(
                        True, "review_replayed_withheld", review_id=existing[0]
                    ), 200
                cursor.execute(
                    """insert into public.pig_observation_events
                       (observation_event_id,pig_id,observed_at,observer_reference,
                        observation_category,severity,factual_note,measurements_json,
                        source_system,source_reference,idempotency_key)
                       values (%s,%s,%s,%s,'body_condition','informational',%s,%s::jsonb,
                               'owner',%s,%s) on conflict (idempotency_key) do nothing""",
                    (observation_id, pig_id, canonical["observed_at"], actor_id, factual_note,
                     json.dumps({"quality_state": quality}), review_id, "observation:" + idem),
                )
                cursor.execute(
                    """insert into public.riversdale_auction_candidate_reviews
                       (review_id,auction_cycle_id,pig_id,withdrawal_state,quality_state,
                        observed_at,observer_reference,observation_event_id,
                        medical_evidence_refs,follow_up,idempotency_key,review_hash)
                       values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       returning review_id""",
                    (review_id, cycle[0], pig_id, derived_withdrawal, quality, canonical["observed_at"], actor_id,
                     observation_id, canonical["medical_evidence_refs"], follow_up, idem, digest),
                )
                cursor.fetchone()
    except Exception as exc:
        return _result(False, "review_store_unavailable", error_type=exc.__class__.__name__), 503
    return _result(True, "review_recorded", review_id=review_id), 201
