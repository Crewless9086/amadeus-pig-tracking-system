"""Private, bounded Documents API consumed only by the registered Green worker."""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timezone
import hmac
import os
import re
import time

from flask import Blueprint, Response, jsonify, request

from services.database_service import DATABASE_URL_ENV

green_print_api_bp = Blueprint("green_print_api", __name__)
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_LIMITS = defaultdict(deque)
MAX_BODY = 16_384
RATE_WINDOW = 60.0
RATE_LIMIT = 120


def _deny(status, code):
    return jsonify({"success": False, "status": code}), status


def _authenticate():
    expected_token = os.getenv("DOCUMENTS_GREEN_WORKER_TOKEN", "").strip()
    expected_green = os.getenv("DOCUMENTS_GREEN_ID", "").strip()
    auth = request.headers.get("Authorization", "")
    green_id = request.headers.get("X-Amadeus-Green-Id", "").strip()
    if (not expected_token or not expected_green or
            not auth.startswith("Bearer ") or
            not hmac.compare_digest(auth[7:].strip(), expected_token) or
            not hmac.compare_digest(green_id, expected_green)):
        return None, _deny(401, "documents_worker_authentication_required")
    now = time.monotonic(); bucket = _LIMITS[green_id]
    while bucket and bucket[0] <= now - RATE_WINDOW:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT:
        return None, _deny(429, "documents_worker_rate_limited")
    bucket.append(now)
    worker_id = request.headers.get("X-Amadeus-Worker-Id", "").strip()
    if not _ID.fullmatch(worker_id): return None, _deny(401, "documents_worker_identity_required")
    return (green_id, worker_id), None


def _json_body():
    if request.content_length is not None and request.content_length > MAX_BODY:
        raise ValueError("request_too_large")
    value = request.get_json(silent=True)
    if not isinstance(value, dict):
        raise ValueError("json_object_required")
    if "authenticated_principal_id" in value:
        raise ValueError("client_identity_prohibited")
    return value


def _connect():
    import psycopg
    url = os.getenv("DOCUMENTS_GREEN_DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("documents_worker_database_unavailable")
    return psycopg.connect(url, connect_timeout=5,
        options="-c role=documents_green_worker_executor -c statement_timeout=5000 -c lock_timeout=2000")


def _call(function, args=(), *, many=False):
    placeholders = ",".join(["%s"] * len(args))
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"select * from app_private.{function}({placeholders})", args)
            if many:
                columns = [item.name for item in cursor.description]
                return [dict(zip(columns, row)) for row in cursor.fetchall()]
            row = cursor.fetchone()
            if row is None:
                return None
            if len(row) == 1:
                return row[0]
            return dict(zip([item.name for item in cursor.description], row))


def _public_job(row):
    if not row:
        return None
    allowed = ("job_id", "document_id", "document_version", "document_revision",
               "document_type", "generator_id", "pdf_sha256", "retrieval_url",
               "green_id", "printer_id", "cups_queue_id", "registry_version",
               "authorization_receipt_id", "authorization_expires_at", "lease_token",
               "lease_expires_at", "attempt_id", "cups_job_id", "provider_id", "state",
               "command_kind", "command_receipt_id", "command_status", "command_outcome")
    result = {key: row[key] for key in allowed if key in row and row[key] is not None}
    if row.get("options_json") is not None:
        result["options"] = row["options_json"]
    return result


def _bounded_id(value, field):
    value = str(value or "")
    if not _ID.fullmatch(value):
        raise ValueError(f"invalid_{field}")
    return value


@green_print_api_bp.before_request
def _guard():
    worker, error = _authenticate()
    if error:
        return error
    request.documents_green_id, request.documents_worker_id = worker


@green_print_api_bp.post("/documents/print-jobs/claims")
def claim_job():
    body = _json_body()
    if set(body) - {"worker_id", "lease_seconds"}:
        return _deny(400, "claim_fields_invalid")
    worker = _bounded_id(body.get("worker_id"), "worker_id")
    if worker != request.documents_worker_id: return _deny(403, "worker_identity_mismatch")
    rows = _call("claim_document_print_job", (request.documents_green_id, worker,
                 int(body.get("lease_seconds", 300))), many=True)
    job = _public_job(rows[0]) if rows else None
    return jsonify({"job": job, "lease_token": job.get("lease_token") if job else None,
                    "lease_expires_at": job.get("lease_expires_at") if job else None}), 200


@green_print_api_bp.post("/documents/print-jobs/commands/claim")
def claim_command():
    body = _json_body()
    if set(body) - {"worker_id", "lease_seconds"}:
        return _deny(400, "command_claim_fields_invalid")
    worker = _bounded_id(body.get("worker_id"), "worker_id")
    if worker != request.documents_worker_id: return _deny(403, "worker_identity_mismatch")
    rows = _call("claim_document_print_command", (request.documents_green_id, worker,
                 int(body.get("lease_seconds", 300))), many=True)
    job = _public_job(rows[0]) if rows else None
    return jsonify({"job": job, "lease_token": job.get("lease_token") if job else None,
                    "command_receipt_id": job.get("command_receipt_id") if job else None,
                    "command": job.get("command_kind") if job else None}), 200


def _bound_job_call(job_id, function, fields):
    body = _json_body(); _bounded_id(job_id, "job_id")
    if set(body) != set(fields):
        return _deny(400, "transition_binding_fields_invalid")
    args = [job_id] + [body[name] for name in fields]
    value = _call(function, tuple(args))
    return jsonify(_public_job(value) if isinstance(value, dict) else value), 200


@green_print_api_bp.post("/documents/print-jobs/<job_id>/transition")
def transition(job_id):
    body = _json_body(); _bounded_id(job_id, "job_id")
    base = ("lease_token", "document_version", "pdf_sha256", "authorization_receipt_id",
            "target_state", "event_id")
    if any(name not in body for name in base): return _deny(400, "transition_binding_fields_invalid")
    metadata = {key: value for key, value in body.items() if key not in base}
    value = _call("transition_document_print_job", tuple([job_id] + [body[k] for k in base] + [metadata]))
    return jsonify(_public_job(value)), 200


@green_print_api_bp.post("/documents/print-jobs/<job_id>/commands/transition")
def transition_command(job_id):
    return _bound_job_call(job_id, "transition_document_print_command",
        ("lease_token", "document_version", "pdf_sha256", "authorization_receipt_id",
         "command_receipt_id", "command_kind", "target_state"))


@green_print_api_bp.post("/documents/print-jobs/<job_id>/lease/renew")
def renew(job_id):
    body = _json_body()
    if body.get("worker_id") != request.documents_worker_id: return _deny(403, "worker_identity_mismatch")
    fields = ("lease_token", "worker_id", "lease_seconds", "document_version",
              "pdf_sha256", "authorization_receipt_id")
    if set(body) != set(fields): return _deny(400, "lease_binding_fields_invalid")
    value = _call("renew_document_print_job_lease", tuple([job_id] + [body[k] for k in fields]))
    return jsonify(_public_job(value)), 200


@green_print_api_bp.post("/documents/print-jobs/<job_id>/lease/recover")
def recover(job_id):
    body = _json_body()
    if body.get("worker_id") != request.documents_worker_id: return _deny(403, "worker_identity_mismatch")
    fields = ("worker_id", "lease_seconds", "document_version", "pdf_sha256",
              "authorization_receipt_id")
    if set(body) != set(fields): return _deny(400, "recovery_binding_fields_invalid")
    value = _call("recover_document_print_job_lease", tuple([job_id] + [body[k] for k in fields]))
    return jsonify(_public_job(value)), 200


@green_print_api_bp.post("/documents/print-jobs/<job_id>/reconcile")
def reconcile(job_id):
    body = _json_body()
    if set(body) != {"lease_token"}: return _deny(400, "reconcile_binding_fields_invalid")
    value = _call("read_document_print_job", (job_id, body["lease_token"], request.documents_green_id, request.documents_worker_id))
    return jsonify(_public_job(value)), 200


@green_print_api_bp.get("/documents/<document_id>/versions/<version_id>/pdf")
def pdf(document_id, version_id):
    value = _call("read_document_print_pdf", (document_id, version_id, request.documents_green_id, request.documents_worker_id))
    if not value: return _deny(404, "document_version_not_found")
    return Response(bytes(value), 200, {"Content-Type": "application/pdf", "Cache-Control": "no-store",
                                       "Content-Length": str(len(value))})


@green_print_api_bp.errorhandler(ValueError)
def _bad_request(error):
    return _deny(413 if str(error) == "request_too_large" else 400, str(error))


@green_print_api_bp.errorhandler(Exception)
def _failed(_error):
    return _deny(503, "documents_boundary_unavailable")
