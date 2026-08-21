"""Home Assistant Green worker for the fixed weekly-sheet pilot.

The canonical service supplies protected envelopes and remains authoritative.
This process keeps only crash-recovery and content-free provider evidence.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import logging
import os
from pathlib import Path
import re
import signal
import socket
import sqlite3
import ssl
import subprocess
import shutil
import time
import ipaddress
from urllib.parse import quote, unquote, urljoin, urlparse
from urllib.request import Request, urlopen
import uuid

PILOT_DOCUMENT = "farm.weekly_weight_sheet.v1"
PILOT_GENERATOR = "web.print_sheets.v1"
CANONICAL_INTAKE_PATH = "/api/documents/print-jobs/claimable"
CA_CERTIFICATE_PATH = "/config/private-ca.crt"
FIXED_OPTIONS = {"media": "A4", "copies": 1, "color": "monochrome", "sides": "one-sided"}
ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
TERMINAL = {"provider_completed", "physically_confirmed", "cancelled", "held", "ambiguous"}
STOP = False


class Hold(RuntimeError):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def iso(value):
    return value.astimezone(timezone.utc).isoformat()


def parse_time(value):
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    if parsed is not None and parsed.tzinfo is None:
        raise Hold("timestamp_timezone_required")
    return parsed


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


class Ledger:
    def __init__(self, path):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
              create table if not exists jobs(
                job_id text primary key,envelope_json text not null,envelope_sha256 text not null,
                state text not null,first_seen_at text not null,retry_deadline text not null,
                lease_owner text,lease_token text,lease_until text,attempt_id text unique,
                cups_job_id text,updated_at text not null,last_error text);
              create table if not exists events(
                sequence integer primary key autoincrement,event_id text unique not null,
                job_id text not null,event_type text not null,event_at text not null,
                metadata_json text not null,exported_at text);
            """)

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("pragma journal_mode=WAL")
        db.execute("pragma synchronous=FULL")
        return db

    def ingest(self, envelope, now):
        material = canonical_json(envelope)
        digest = sha256(material.encode()).hexdigest()
        with self.connect() as db:
            db.execute("begin immediate")
            row = db.execute("select envelope_sha256 from jobs where job_id=?", (envelope["job_id"],)).fetchone()
            if row and row[0] != digest:
                raise Hold("job_identity_envelope_conflict")
            if not row:
                db.execute("insert into jobs values(?,?,?,?,?,?,?,?,?,?,?,?,?)", (
                    envelope["job_id"], material, digest, "pending", iso(now),
                    iso(now + timedelta(hours=48)), None, None, None, None, None, iso(now), None))
                self.event(db, envelope["job_id"], "job_ingested", now,
                           {"envelope_sha256": digest, "pdf_sha256": envelope["pdf_sha256"]})

    def get(self, job_id):
        with self.connect() as db:
            row = db.execute("select * from jobs where job_id=?", (job_id,)).fetchone()
            return dict(row) if row else None

    def recoverable(self):
        """Return local attempts that must be reconciled before new intake."""
        with self.connect() as db:
            rows = db.execute(
                "select * from jobs where attempt_id is not null and state in ('submitting','submitted') "
                "order by first_seen_at,job_id"
            ).fetchall()
            return [dict(row) for row in rows]

    def claim(self, job_id, worker_id, now):
        token = uuid.uuid4().hex
        with self.connect() as db:
            db.execute("begin immediate")
            row = db.execute("select * from jobs where job_id=?", (job_id,)).fetchone()
            if row["state"] in TERMINAL:
                return None
            if parse_time(row["lease_until"]) and parse_time(row["lease_until"]) > now:
                return None
            if now >= parse_time(row["retry_deadline"]):
                self.transition(db, job_id, "held", now, "retry_window_expired")
                return None
            db.execute("update jobs set state='claimed',lease_owner=?,lease_token=?,lease_until=?,updated_at=? where job_id=?",
                       (worker_id, token, iso(now + timedelta(minutes=5)), iso(now), job_id))
            self.event(db, job_id, "lease_claimed", now, {"worker_id": worker_id})
        return token

    def prepare(self, job_id, token, now):
        with self.connect() as db:
            db.execute("begin immediate")
            row = self.fenced(db, job_id, token, now)
            if row["attempt_id"]:
                return row["attempt_id"]
            attempt = "ATTEMPT-" + uuid.uuid4().hex
            db.execute("update jobs set state='submitting',attempt_id=?,updated_at=? where job_id=?", (attempt, iso(now), job_id))
            self.event(db, job_id, "pre_submission_attempt", now, {"attempt_id": attempt})
            return attempt

    def submitted(self, job_id, token, cups_id, now):
        with self.connect() as db:
            db.execute("begin immediate")
            row = self.fenced(db, job_id, token, now)
            if row["cups_job_id"] and row["cups_job_id"] != cups_id:
                raise Hold("cups_job_identity_conflict")
            db.execute("update jobs set state='submitted',cups_job_id=?,updated_at=? where job_id=?", (cups_id, iso(now), job_id))
            self.event(db, job_id, "cups_submission_recorded", now,
                       {"attempt_id": row["attempt_id"], "cups_job_id": cups_id})

    def observed(self, job_id, state, now):
        target = "provider_completed" if state == "completed" else "held" if state in {"aborted", "cancelled"} else "submitted"
        with self.connect() as db:
            db.execute("begin immediate")
            self.transition(db, job_id, target, now, "cups_" + state)
        return target

    def ambiguous(self, job_id, reason, now):
        with self.connect() as db:
            db.execute("begin immediate")
            self.transition(db, job_id, "ambiguous", now, reason)

    def fenced(self, db, job_id, token, now):
        row = db.execute("select * from jobs where job_id=?", (job_id,)).fetchone()
        if not row or row["lease_token"] != token or parse_time(row["lease_until"]) <= now:
            raise Hold("lease_fence_invalid")
        return row

    def transition(self, db, job_id, state, now, reason):
        db.execute("update jobs set state=?,updated_at=?,last_error=? where job_id=?", (state, iso(now), reason, job_id))
        self.event(db, job_id, "state_changed", now, {"state": state, "reason": reason})

    def event(self, db, job_id, kind, now, metadata):
        db.execute("insert into events(event_id,job_id,event_type,event_at,metadata_json) values(?,?,?,?,?)",
                   (uuid.uuid4().hex, job_id, kind, iso(now), canonical_json(metadata)))


def validate(envelope, config, now):
    required = ("job_id", "document_id", "document_version", "pdf_sha256", "retrieval_url",
                "green_id", "printer_id", "cups_queue_id", "registry_version",
                "authorization_receipt_id", "authorization_expires_at")
    if any(envelope.get(key) in (None, "") for key in required):
        raise Hold("required_binding_missing")
    if envelope.get("document_type") != PILOT_DOCUMENT or envelope.get("generator_id") != PILOT_GENERATOR:
        raise Hold("document_or_generator_not_allowlisted")
    if envelope.get("options") != FIXED_OPTIONS:
        raise Hold("print_options_not_allowlisted")
    for key in required[:-1]:
        if key not in {"pdf_sha256", "retrieval_url"} and not ID.fullmatch(str(envelope[key])):
            raise Hold("invalid_identity")
    for key in ("green_id", "printer_id", "cups_queue_id", "registry_version"):
        if envelope[key] != config[key]:
            raise Hold("registered_identity_pair_mismatch")
    if not DIGEST.fullmatch(str(envelope["pdf_sha256"]).lower()):
        raise Hold("invalid_pdf_digest")
    expires_at = parse_time(envelope["authorization_expires_at"])
    if expires_at <= now:
        raise Hold("authorization_expired")
    origin = urlparse(config["canonical_api_origin"])
    url = urlparse(envelope["retrieval_url"])
    path = f"/api/documents/{envelope['document_id']}/versions/{envelope['document_version']}/pdf"
    if (url.scheme, url.hostname, url.port) != ("https", origin.hostname, origin.port):
        raise Hold("retrieval_origin_not_allowlisted")
    if url.username or url.password or url.query or url.fragment or unquote(url.path) != path:
        raise Hold("unsafe_or_unbound_retrieval_url")


class CanonicalClient:
    def __init__(self, config):
        self.config = config
        self.ssl = ssl.create_default_context(cafile=config["ca_certificate_path"])

    def request(self, method, path, body=None):
        origin = self.config["canonical_api_origin"].rstrip("/") + "/"
        url = urljoin(origin, path.lstrip("/"))
        if urlparse(url).scheme != "https" or urlparse(url).netloc != urlparse(origin).netloc:
            raise Hold("canonical_url_escape")
        payload = canonical_json(body).encode() if body is not None else None
        headers = {"Authorization": "Bearer " + self.config["canonical_bearer_token"], "Accept": "application/json"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        assert_private_resolution(urlparse(url).hostname)
        with urlopen(Request(url, data=payload, headers=headers, method=method), context=self.ssl, timeout=20) as response:
            assert_exact_response_url(response.geturl(), url)
            data = response.read(1024 * 1024)
        return json.loads(data) if data else None

    def next_job(self):
        value = self.request("GET", CANONICAL_INTAKE_PATH + "?limit=1")
        jobs = value.get("jobs", []) if isinstance(value, dict) else []
        if len(jobs) > 1:
            raise Hold("canonical_intake_ambiguous")
        return jobs[0] if jobs else None

    def pdf(self, url):
        parsed = urlparse(url)
        origin = urlparse(self.config["canonical_api_origin"])
        if (parsed.scheme, parsed.hostname, parsed.port) != ("https", origin.hostname, origin.port):
            raise Hold("pdf_origin_mismatch")
        assert_private_resolution(parsed.hostname)
        request = Request(url, headers={"Authorization": "Bearer " + self.config["canonical_bearer_token"]})
        with urlopen(request, context=self.ssl, timeout=30) as response:
            assert_exact_response_url(response.geturl(), url)
            content_type = response.headers.get_content_type()
            if content_type != "application/pdf":
                raise Hold("pdf_content_type_invalid")
            return response.read(25 * 1024 * 1024 + 1)

    def evidence(self, job_id, body):
        return self.request("POST", "/api/documents/print-jobs/" + quote(job_id, safe="") + "/events", body)


class Cups:
    def __init__(self, queue):
        self.queue = queue

    def submit(self, path):
        result = subprocess.run(["lp", "-d", self.queue, "-n", "1", "-o", "media=A4",
                                 "-o", "ColorModel=Gray", "-o", "sides=one-sided", path],
                                check=True, capture_output=True, text=True, timeout=30)
        match = re.search(r"request id is ([A-Za-z0-9._-]+)", result.stdout)
        if not match:
            raise Hold("cups_submission_receipt_missing")
        return match.group(1)

    def observe(self, cups_id):
        result = subprocess.run(["lpstat", "-W", "all", "-o", self.queue], capture_output=True, text=True, timeout=15)
        if cups_id in cups_job_ids(result.stdout):
            return "pending"
        completed = subprocess.run(["lpstat", "-W", "completed", "-o", self.queue], capture_output=True, text=True, timeout=15)
        return "completed" if cups_id in cups_job_ids(completed.stdout) else "unknown"


def cups_job_ids(output):
    return {line.split()[0] for line in output.splitlines() if line.split()}


def assert_private_resolution(hostname):
    try:
        addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(hostname, None)}
    except (OSError, ValueError, TypeError):
        raise Hold("private_endpoint_resolution_failed")
    if not addresses or any(not (address.is_private or address.is_link_local) for address in addresses):
        raise Hold("public_endpoint_forbidden")


def assert_exact_response_url(actual, expected):
    if actual != expected:
        raise Hold("https_redirect_forbidden")


def write_health(status, worker_id, result, next_poll):
    value = {"contract_version": "green_print_health_v1", "status": status, "worker_id": worker_id,
             "heartbeat_at": iso(utcnow()), "last_result": result, "next_poll_at": iso(next_poll),
             "authority_mode": "fixed_weekly_sheet_only", "terminal_participated": False}
    target = Path("/data/health.json")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(canonical_json(value), encoding="utf-8")
    os.replace(temporary, target)


def load_config(path="/data/options.json"):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    required = ("canonical_api_origin", "canonical_bearer_token", "green_id", "printer_id",
                "cups_queue_id", "registry_version", "printer_uri", "poll_seconds")
    if any(value.get(key) in (None, "") for key in required):
        raise Hold("runtime_option_missing")
    origin = urlparse(value["canonical_api_origin"])
    if origin.scheme != "https" or origin.username or origin.password or origin.query or origin.fragment:
        raise Hold("canonical_origin_must_be_private_https")
    printer = urlparse(value["printer_uri"])
    if printer.scheme != "ipps" or not printer.hostname or printer.username or printer.password or printer.query or printer.fragment:
        raise Hold("printer_uri_must_be_credential_free_ipps")
    for hostname in (origin.hostname, printer.hostname):
        assert_private_resolution(hostname)
    value["ca_certificate_path"] = CA_CERTIFICATE_PATH
    value["canonical_intake_path"] = CANONICAL_INTAKE_PATH
    if not Path(value["ca_certificate_path"]).is_file():
        raise Hold("private_ca_missing")
    if not all(ID.fullmatch(str(value[key])) for key in ("green_id", "printer_id", "cups_queue_id", "registry_version")):
        raise Hold("invalid_registered_option")
    return value


def cycle(ledger, client, cups, config, worker_id):
    recoverable = ledger.recoverable()
    if recoverable:
        current = recoverable[0]
        now = utcnow()
        if not current["cups_job_id"]:
            ledger.ambiguous(current["job_id"], "submission_outcome_unknown_reconcile_before_retry", now)
            client.evidence(current["job_id"], {"event_type": "submission_ambiguous", "observed_at": iso(now)})
            return "ambiguous"
        state = cups.observe(current["cups_job_id"])
        result = ledger.observed(current["job_id"], state, now)
        client.evidence(current["job_id"], {"event_type": "cups_observed", "cups_job_id": current["cups_job_id"],
                                            "cups_state": state, "observed_at": iso(now)})
        return result
    envelope = client.next_job()
    if not envelope:
        return "event_waiting"
    now = utcnow()
    validate(envelope, config, now)
    ledger.ingest(envelope, now)
    current = ledger.get(envelope["job_id"])
    if current["attempt_id"]:
        if not current["cups_job_id"]:
            ledger.ambiguous(envelope["job_id"], "submission_outcome_unknown_reconcile_before_retry", now)
            return "ambiguous"
        state = cups.observe(current["cups_job_id"])
        result = ledger.observed(envelope["job_id"], state, now)
        client.evidence(envelope["job_id"], {"event_type": "cups_observed", "cups_job_id": current["cups_job_id"],
                                             "cups_state": state, "observed_at": iso(now)})
        return result
    token = ledger.claim(envelope["job_id"], worker_id, now)
    if not token:
        return ledger.get(envelope["job_id"])["state"]
    path = Path("/tmp/green-spool") / (envelope["job_id"] + "." + uuid.uuid4().hex + ".pdf")
    try:
        pdf = client.pdf(envelope["retrieval_url"])
        if len(pdf) > 25 * 1024 * 1024 or sha256(pdf).hexdigest() != envelope["pdf_sha256"]:
            ledger.ambiguous(envelope["job_id"], "pdf_digest_mismatch", now)
            return "ambiguous"
        path.write_bytes(pdf)
        ledger.prepare(envelope["job_id"], token, now)
        cups_id = cups.submit(str(path))
        ledger.submitted(envelope["job_id"], token, cups_id, now)
        client.evidence(envelope["job_id"], {"event_type": "cups_submitted", "cups_job_id": cups_id, "observed_at": iso(now)})
        return "submitted"
    except Exception:
        if ledger.get(envelope["job_id"])["attempt_id"]:
            ledger.ambiguous(envelope["job_id"], "cups_submission_exception", now)
            return "ambiguous"
        raise
    finally:
        path.unlink(missing_ok=True)


def main():
    os.umask(0o077)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    config = load_config()
    shutil.copyfile(config["ca_certificate_path"], "/usr/local/share/ca-certificates/amadeus-private-ca.crt")
    subprocess.run(["update-ca-certificates"], check=True, capture_output=True, timeout=30)
    worker_id = "green-worker-" + uuid.uuid4().hex
    ledger = Ledger("/data/green-print-ledger.sqlite3")
    client = CanonicalClient(config)
    subprocess.Popen(["cupsd", "-f"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1)
    subprocess.run(["lpadmin", "-p", config["cups_queue_id"], "-E", "-v", config["printer_uri"], "-m", "everywhere"],
                   check=True, capture_output=True, timeout=30)
    cups = Cups(config["cups_queue_id"])
    while not STOP:
        next_poll = utcnow() + timedelta(seconds=int(config["poll_seconds"]))
        try:
            result = cycle(ledger, client, cups, config, worker_id)
            write_health("event_waiting" if result == "event_waiting" else "working", worker_id, result, next_poll)
            logging.info("cycle status=%s", result)
        except Exception as exc:
            reason = exc.args[0] if isinstance(exc, Hold) and exc.args else type(exc).__name__
            write_health("held", worker_id, str(reason)[:120], next_poll)
            logging.error("cycle held reason=%s", str(reason)[:120])
        time.sleep(max(1, int(config["poll_seconds"])))


def stop(_signal, _frame):
    global STOP
    STOP = True


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    main()
