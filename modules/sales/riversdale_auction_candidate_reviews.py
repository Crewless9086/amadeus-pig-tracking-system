"""Append-only owner evidence for Riversdale candidate reviews."""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone

VERSION = "riversdale_candidate_review_v1"
WITHDRAWAL_STATES = {"not_applicable", "cleared", "hold", "unknown"}
QUALITY_STATES = {"suitable", "hold", "unknown"}


def _result(ok, status, **extra):
    return {
        "success": ok, "status": status, "review_contract_version": VERSION,
        "creates_cohort": False, "creates_outlet_assignment": False,
        "creates_reservation": False, "books_auction": False, "creates_sale": False,
        "sends_reminder": False, "contacts_customer": False,
        "changes_medical_record": False, "changes_lifecycle": False,
        "changes_purpose": False, "changes_farm_state": False, **extra,
    }


def record_candidate_review(payload, *, actor_id, candidate_ids, database_url=None, connect_factory=None):
    payload = payload if isinstance(payload, dict) else {}
    actor_id = str(actor_id or "").strip()
    pig_id = str(payload.get("pig_id") or "").strip()
    withdrawal = str(payload.get("withdrawal_state") or "unknown").strip().lower()
    quality = str(payload.get("quality_state") or "unknown").strip().lower()
    observed_at = str(payload.get("observed_at") or "").strip()
    idem = str(payload.get("idempotency_key") or "").strip()
    refs = payload.get("medical_evidence_refs", [])
    follow_up = str(payload.get("follow_up") or "").strip()
    factual_note = str(payload.get("physical_observation") or "").strip()
    if not actor_id:
        return _result(False, "owner_identity_required"), 403
    if pig_id not in set(candidate_ids or []):
        return _result(False, "candidate_not_in_current_preview"), 409
    if withdrawal not in WITHDRAWAL_STATES or quality not in QUALITY_STATES:
        return _result(False, "invalid_review_state"), 400
    if not idem or not observed_at or not factual_note or not isinstance(refs, list):
        return _result(False, "review_evidence_required"), 400
    try:
        instant = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant > datetime.now(timezone.utc):
            raise ValueError
    except ValueError:
        return _result(False, "invalid_observation_time"), 400
    canonical = {
        "version": VERSION, "pig_id": pig_id, "withdrawal_state": withdrawal,
        "quality_state": quality, "observed_at": instant.isoformat(),
        "medical_evidence_refs": sorted({str(v).strip() for v in refs if str(v).strip()}),
        "follow_up": follow_up, "physical_observation": factual_note, "actor_id": actor_id,
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    review_id = "RIV-REVIEW-" + uuid.uuid5(uuid.NAMESPACE_URL, idem).hex.upper()
    observation_id = "RIV-OBS-" + uuid.uuid5(uuid.NAMESPACE_URL, idem).hex.upper()
    url = (database_url if database_url is not None else os.getenv("FARM_SUPABASE_DATABASE_URL", "")).strip()
    if not url and connect_factory is None:
        return _result(False, "review_store_unavailable"), 503
    try:
        factory = (lambda: connect_factory(url)) if connect_factory else (lambda: __import__("psycopg").connect(url, connect_timeout=10))
        with factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select auction_cycle_id from public.riversdale_auction_cycles
                       where operating_confirmed is true
                       order by owner_confirmed_at desc limit 1"""
                )
                cycle = cursor.fetchone()
                if not cycle:
                    return _result(False, "confirmed_auction_cycle_required"), 409
                cursor.execute(
                    """select medical_event_id from public.pig_medical_events
                       where pig_id=%s and medical_event_id = any(%s)""",
                    (pig_id, canonical["medical_evidence_refs"]),
                )
                if len(cursor.fetchall()) != len(canonical["medical_evidence_refs"]):
                    return _result(False, "invalid_medical_evidence_reference"), 409
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
                       on conflict (idempotency_key) do nothing returning review_id""",
                    (review_id, cycle[0], pig_id, withdrawal, quality, canonical["observed_at"], actor_id,
                     observation_id, canonical["medical_evidence_refs"], follow_up, idem, digest),
                )
                inserted = cursor.fetchone()
                if not inserted:
                    cursor.execute(
                        "select review_id,review_hash from public.riversdale_auction_candidate_reviews where idempotency_key=%s",
                        (idem,),
                    )
                    existing = cursor.fetchone()
                    if not existing or existing[1] != digest:
                        return _result(False, "review_idempotency_conflict"), 409
                    return _result(True, "review_replayed_withheld", review_id=existing[0]), 200
    except Exception as exc:
        return _result(False, "review_store_unavailable", error_type=exc.__class__.__name__), 503
    return _result(True, "review_recorded", review_id=review_id), 201
