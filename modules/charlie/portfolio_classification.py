"""Atomic owner-approved classification of the immutable legacy portfolio."""

from __future__ import annotations

import hashlib
import json
from collections import Counter

from modules.charlie.mission_store import _connect, _database_url

CONTROLLING_MISSION_ID = "CMQ-20260813-05"
PORTFOLIO_EPOCH = "CORE-CURRENT-2026-08-14"
CLASSIFICATION_VERSION = "legacy_portfolio_classification_v1"
APPROVED_BASELINE_DIGEST = "b31ac806513d8ebd23350bde9f96984a58bf7dbc09f9ba385a35c268cfff5f8d"
APPROVED_SET_DIGEST = "159db3bf36483cfa9e3a81ad535ef2cf112e9c997fd525312226d651251ccc19"
APPROVED_COUNTS = {"recovery_fragment": 49, "test_evidence": 19, "superseded": 11, "historical": 7}
UNRESOLVED_STATUSES = ("new", "triaged", "planned", "approved", "in_progress", "blocked", "pr_ready", "release_approved", "release_in_progress", "paused")


def classification_set_digest(classifications):
    return hashlib.sha256(json.dumps(classifications, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def classify_legacy_portfolio(classifications, baseline_digest, *, database_url=None, connect_factory=None):
    if not isinstance(classifications, dict) or len(classifications) != 86:
        return {"success": False, "status": "approved_classification_set_required"}, 400
    if str(baseline_digest or "") != APPROVED_BASELINE_DIGEST:
        return {"success": False, "status": "baseline_digest_mismatch"}, 409
    clean = {str(key): str(value) for key, value in classifications.items()}
    if classification_set_digest(clean) != APPROVED_SET_DIGEST or dict(Counter(clean.values())) != APPROVED_COUNTS:
        return {"success": False, "status": "approved_classification_set_mismatch"}, 409
    database_url = _database_url(database_url)
    if not database_url and connect_factory is None:
        return {"success": False, "status": "not_configured"}, 503
    try:
        with _connect(database_url, connect_factory) as connection, connection.cursor() as cursor:
            # The advisory lock is the serialization mechanism. READ COMMITTED
            # deliberately gives a waiting concurrent caller a fresh snapshot
            # after the first classifier commits, so it converges as replay.
            cursor.execute("set transaction isolation level read committed")
            cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s, 0))", ("portfolio-classification:" + PORTFOLIO_EPOCH,))
            cursor.execute("select count(*) from public.charlie_missions where status = any(%s) and mission_id <> %s",
                           (list(UNRESOLVED_STATUSES), CONTROLLING_MISSION_ID))
            if cursor.fetchone()[0] != 86:
                return {"success": False, "status": "baseline_identity_set_mismatch"}, 409
            cursor.execute("""
                select mission_id, status, source, title, updated_at, metadata_json
                from public.charlie_missions
                where status = any(%s) and mission_id = any(%s)
                order by created_at, mission_id for update
            """, (list(UNRESOLVED_STATUSES), list(clean)))
            rows = cursor.fetchall()
            if len(rows) != 86 or {row[0] for row in rows} != set(clean):
                return {"success": False, "status": "baseline_identity_set_mismatch"}, 409
            cursor.execute("""
                select mission_id, event_type, count(*)
                from public.charlie_mission_events
                where mission_id = any(%s) and event_type <> 'portfolio_classified'
                group by mission_id, event_type
            """, (list(clean),))
            event_counts = {}
            for mission_id, event_type, count in cursor.fetchall():
                event_counts.setdefault(mission_id, {})[event_type] = count
            snapshot = [{"mission_id": row[0], "status": row[1], "source": row[2], "title": row[3],
                         "updated_at": str(row[4]), "events": event_counts.get(row[0], {})} for row in rows]
            actual_digest = hashlib.sha256(json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            if actual_digest != APPROVED_BASELINE_DIGEST:
                return {"success": False, "status": "baseline_digest_mismatch", "actual_digest": actual_digest}, 409
            contracts = {}
            for mission_id, _status, _source, _title, _updated_at, metadata in rows:
                existing = (metadata or {}).get("portfolio_classification") if isinstance(metadata, dict) else None
                expected = {"portfolio_epoch": PORTFOLIO_EPOCH, "classification": clean[mission_id],
                            "classification_version": CLASSIFICATION_VERSION, "baseline_digest": APPROVED_BASELINE_DIGEST,
                            "decision_authority": "human_control_tower", "dispatch_authority": "human_control_tower",
                            "admitted": False, "runnable": False}
                if existing is not None and existing != expected:
                    return {"success": False, "status": "classification_replay_conflict", "mission_id": mission_id}, 409
                contracts[mission_id] = (existing, expected)
            changed = 0
            for mission_id, _status, _source, _title, _updated_at, _metadata in rows:
                existing, expected = contracts[mission_id]
                if existing is None:
                    cursor.execute("update public.charlie_missions set metadata_json = coalesce(metadata_json, '{}'::jsonb) || %s::jsonb where mission_id = %s",
                                   (json.dumps({"portfolio_classification": expected}), mission_id))
                    event_id = "CHARLIE-PORTFOLIO-" + hashlib.sha256(f"{APPROVED_SET_DIGEST}|{mission_id}".encode()).hexdigest()[:20].upper()
                    cursor.execute("""insert into public.charlie_mission_events
                        (event_id, mission_id, event_type, notes, metadata_json, created_at)
                        values (%s,%s,'portfolio_classified','Owner-approved legacy portfolio classification.',%s::jsonb,now())
                        on conflict (event_id) do nothing""", (event_id, mission_id, json.dumps(expected)))
                    changed += 1
        return {"success": True, "status": "portfolio_classified" if changed else "portfolio_classification_replayed_noop",
                "changed": changed, "baseline_digest": APPROVED_BASELINE_DIGEST,
                "classification_set_digest": APPROVED_SET_DIGEST, "counts": APPROVED_COUNTS}, 201 if changed else 200
    except Exception as exc:
        return {"success": False, "status": "portfolio_classification_failed", "error_type": exc.__class__.__name__}, 503
