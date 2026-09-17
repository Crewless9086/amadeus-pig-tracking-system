"""Crash-safe private Green adapter ledger and non-actuating orchestration.

The caller injects retrieval, CUPS submission and CUPS observation functions.
No network, CUPS, scheduler or credential implementation lives here. SQLite is
execution recovery state only; canonical job truth remains in Documents.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sqlite3
import uuid

from modules.documents.green_print_adapter import validate_authorized_job, validate_cups_evidence

RETRY_WINDOW = timedelta(hours=48)
LEASE = timedelta(minutes=5)
TERMINAL = {"completed", "cancelled"}


class AdapterHold(RuntimeError):
    pass


class GreenAdapterLedger:
    def __init__(self, path):
        self.path = str(path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("pragma journal_mode=WAL")
        db.execute("pragma synchronous=FULL")
        return db

    def _initialize(self):
        with self._connect() as db:
            db.executescript("""
            create table if not exists jobs(
              job_id text primary key, envelope_json text not null,
              envelope_sha256 text not null, state text not null,
              first_seen_at text not null, retry_deadline text not null,
              lease_owner text, lease_token text, lease_until text,
              attempt_id text unique, cups_job_id text,
              updated_at text not null, last_error text);
            create table if not exists events(
              sequence integer primary key autoincrement, event_id text unique not null,
              job_id text not null, event_type text not null, event_at text not null,
              metadata_json text not null);
            """)

    def ingest(self, envelope, *, now):
        material = _json(envelope); digest = sha256(material.encode()).hexdigest()
        with self._connect() as db:
            db.execute("begin immediate")
            row = db.execute("select envelope_sha256 from jobs where job_id=?", (envelope["job_id"],)).fetchone()
            if row and row[0] != digest:
                raise AdapterHold("job_identity_envelope_conflict")
            if not row:
                db.execute("insert into jobs values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    envelope["job_id"], material, digest, "pending", _iso(now),
                    _iso(now + RETRY_WINDOW), None, None, None, None, None, _iso(now), None))
                self._event(db, envelope["job_id"], "job_ingested", now,
                            {"envelope_sha256": digest, "pdf_sha256": envelope["pdf_sha256"]})
        return self.get(envelope["job_id"])

    def claim(self, job_id, *, worker_id, now):
        token = uuid.uuid4().hex
        with self._connect() as db:
            db.execute("begin immediate")
            row = db.execute("select * from jobs where job_id=?", (job_id,)).fetchone()
            if not row:
                raise AdapterHold("job_unknown")
            if row["state"] in TERMINAL or row["state"] in {"ambiguous", "held"}:
                return None
            lease_until = _time(row["lease_until"])
            if lease_until and lease_until > now and row["lease_owner"] != worker_id:
                return None
            if now >= _time(row["retry_deadline"]):
                self._transition(db, job_id, "held", now, "retry_window_expired")
                return None
            db.execute("update jobs set state='claimed',lease_owner=?,lease_token=?,lease_until=?,updated_at=? where job_id=?",
                       (worker_id, token, _iso(now + LEASE), _iso(now), job_id))
            self._event(db, job_id, "lease_claimed", now, {"worker_id": worker_id, "lease_token": token})
        return token

    def prepare_attempt(self, job_id, *, lease_token, now):
        with self._connect() as db:
            db.execute("begin immediate")
            row = self._fenced(db, job_id, lease_token, now)
            if row["attempt_id"]:
                return row["attempt_id"]
            attempt = f"ATTEMPT-{uuid.uuid4().hex}"
            db.execute("update jobs set state='submitting',attempt_id=?,updated_at=? where job_id=?",
                       (attempt, _iso(now), job_id))
            self._event(db, job_id, "pre_submission_attempt", now, {"attempt_id": attempt})
            return attempt

    def record_submission(self, job_id, *, lease_token, cups_job_id, now):
        with self._connect() as db:
            db.execute("begin immediate")
            row = self._fenced(db, job_id, lease_token, now)
            if not row["attempt_id"]:
                raise AdapterHold("pre_submission_attempt_required")
            if row["cups_job_id"] and row["cups_job_id"] != cups_job_id:
                raise AdapterHold("cups_job_identity_conflict")
            db.execute("update jobs set state='submitted',cups_job_id=?,updated_at=? where job_id=?",
                       (cups_job_id, _iso(now), job_id))
            self._event(db, job_id, "cups_submission_recorded", now,
                        {"attempt_id": row["attempt_id"], "cups_job_id": cups_job_id})

    def reconcile(self, job_id, *, evidence, now):
        state = evidence["cups_state"]
        with self._connect() as db:
            db.execute("begin immediate")
            current = db.execute("select * from jobs where job_id=?", (job_id,)).fetchone()
            if str(current["cups_job_id"] or "") != str(evidence["cups_job_id"]):
                raise AdapterHold("cups_reconciliation_identity_mismatch")
            target = "provider_completed" if state == "completed" else "held" if state in {"aborted", "cancelled"} else "submitted"
            self._transition(db, job_id, target, now, f"cups_{state}")
            self._event(db, job_id, "cups_observed", now, {k: str(v) for k, v in evidence.items()})
        return target

    def mark_ambiguous(self, job_id, *, now, reason):
        with self._connect() as db:
            db.execute("begin immediate"); self._transition(db, job_id, "ambiguous", now, reason)

    def continue_held(self, job_id, *, continued_envelope, now):
        with self._connect() as db:
            db.execute("begin immediate")
            row = db.execute("select state,envelope_json from jobs where job_id=?", (job_id,)).fetchone()
            if not row or row["state"] != "held": raise AdapterHold("job_not_held")
            prior = json.loads(row["envelope_json"])
            candidate = dict(continued_envelope)
            if candidate.get("job_id") != job_id:
                raise AdapterHold("continue_job_identity_mismatch")
            mutable = {"authorization_receipt_id", "authorization_expires_at"}
            if any(prior.get(key) != candidate.get(key) for key in set(prior) | set(candidate) if key not in mutable):
                raise AdapterHold("continue_immutable_binding_changed")
            receipt = str(candidate.get("authorization_receipt_id") or "")
            if not receipt or receipt == prior.get("authorization_receipt_id"):
                raise AdapterHold("fresh_continue_authorization_required")
            material = _json(candidate); digest = sha256(material.encode()).hexdigest()
            db.execute("update jobs set envelope_json=?,envelope_sha256=?,state='pending',retry_deadline=?,lease_owner=null,lease_token=null,lease_until=null,attempt_id=null,cups_job_id=null,updated_at=? where job_id=?",
                       (material, digest, _iso(now + RETRY_WINDOW), _iso(now), job_id))
            self._event(db, job_id, "held_continue", now, {"authorization_receipt_id": receipt})

    def cancel(self, job_id, *, authorization_receipt_id, now):
        with self._connect() as db:
            db.execute("begin immediate")
            row = db.execute("select envelope_json,state from jobs where job_id=?", (job_id,)).fetchone()
            if not row: raise AdapterHold("job_unknown")
            if json.loads(row["envelope_json"])["authorization_receipt_id"] != authorization_receipt_id:
                raise AdapterHold("cancel_authorization_mismatch")
            if row["state"] != "cancelled":
                self._transition(db, job_id, "cancelled", now, "protected_cancel")

    def get(self, job_id):
        with self._connect() as db:
            row = db.execute("select * from jobs where job_id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def events(self, job_id):
        with self._connect() as db:
            return [dict(row) for row in db.execute("select * from events where job_id=? order by sequence", (job_id,))]

    def _fenced(self, db, job_id, token, now):
        row = db.execute("select * from jobs where job_id=?", (job_id,)).fetchone()
        if not row or row["lease_token"] != token or _time(row["lease_until"]) <= now:
            raise AdapterHold("lease_fence_invalid")
        return row

    def _transition(self, db, job_id, state, now, reason):
        db.execute("update jobs set state=?,updated_at=?,last_error=? where job_id=?", (state, _iso(now), reason, job_id))
        self._event(db, job_id, "state_changed", now, {"state": state, "reason": reason})

    def _event(self, db, job_id, event_type, now, metadata):
        db.execute("insert into events(event_id,job_id,event_type,event_at,metadata_json) values(?,?,?,?,?)",
                   (uuid.uuid4().hex, job_id, event_type, _iso(now), _json(metadata)))


def run_cycle(*, ledger, envelope, registered_pair, allowed_origin, worker_id,
              observer_id, retrieve_pdf, submit_cups, observe_cups, temp_dir, now):
    """Execute at most one provider submission, reconciling uncertainty first."""
    job = validate_authorized_job(envelope, allowed_origin=allowed_origin,
                                  registered_pair=registered_pair, now=now)
    stored = {**envelope, "authorization_expires_at": envelope["authorization_expires_at"].isoformat()}
    ledger.ingest(stored, now=now)
    current = ledger.get(job.job_id)
    if current["attempt_id"]:
        if not current["cups_job_id"]:
            ledger.mark_ambiguous(job.job_id, now=now, reason="submission_outcome_unknown_reconcile_before_retry")
            return {"status": "ambiguous", "submitted": False}
        evidence = observe_cups(current["cups_job_id"])
        validate_cups_evidence(evidence, job=job, observer_id=observer_id)
        return {"status": ledger.reconcile(job.job_id, evidence=evidence, now=now), "submitted": False}
    token = ledger.claim(job.job_id, worker_id=worker_id, now=now)
    if not token: return {"status": ledger.get(job.job_id)["state"], "submitted": False}
    path = Path(temp_dir) / f"{job.job_id}.{uuid.uuid4().hex}.pdf"
    try:
        pdf = retrieve_pdf(job.retrieval_url)
        if not isinstance(pdf, bytes) or sha256(pdf).hexdigest() != job.pdf_sha256:
            ledger.mark_ambiguous(job.job_id, now=now, reason="pdf_digest_mismatch")
            return {"status": "ambiguous", "submitted": False}
        path.write_bytes(pdf)
        attempt = ledger.prepare_attempt(job.job_id, lease_token=token, now=now)
        cups_id = submit_cups(str(path), job.cups_queue_id, dict(job.options), attempt)
        if not cups_id:
            ledger.mark_ambiguous(job.job_id, now=now, reason="cups_submission_receipt_missing")
            return {"status": "ambiguous", "submitted": False}
        ledger.record_submission(job.job_id, lease_token=token, cups_job_id=str(cups_id), now=now)
        return {"status": "submitted", "submitted": True, "attempt_id": attempt, "cups_job_id": str(cups_id)}
    except AdapterHold:
        raise
    except Exception:
        # Once the pre-submission attempt exists, absence of a provider identity
        # is ambiguous and must never auto-retry.
        if ledger.get(job.job_id)["attempt_id"]:
            ledger.mark_ambiguous(job.job_id, now=now, reason="cups_submission_exception")
            return {"status": "ambiguous", "submitted": False}
        raise
    finally:
        try: path.unlink(missing_ok=True)
        except OSError: pass


def _json(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
def _iso(value): return value.astimezone(timezone.utc).isoformat()
def _time(value): return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
