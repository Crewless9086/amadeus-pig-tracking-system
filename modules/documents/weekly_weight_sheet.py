"""Canonical weekly weighing-sheet revision and protected print bindings.

This module is deterministic and non-actuating.  Oom Sakkie's authenticated
gateway supplies the principal and canonical rows; the existing protected
action rail owns confirmation.  The resulting PDF bytes are immutable for one
revision and are never accepted back from a client.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from hashlib import sha256
from io import BytesIO
import json
import re
import uuid

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen.canvas import Canvas

from modules.documents.catalogue import Requester, RequesterRole, require_generator, require_requester
from modules.documents.green_print_adapter import DEFAULTS, PILOT_DOCUMENT, PILOT_GENERATOR
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
PRINT_ACTION_KIND = "documents_green_print"


@dataclass(frozen=True)
class WeeklySheetRevision:
    document_id: str
    version_id: str
    revision: int
    sheet_date: date
    pdf_bytes: bytes
    pdf_sha256: str
    canonical_input_sha256: str


def build_weekly_sheet_revision(*, authenticated_principal_id, requester, sheet_date,
                                rows, revision=1, document_id=None):
    """Build one immutable A4 PDF from canonical, already-authorized row facts."""
    principal = _identity(authenticated_principal_id, "authenticated_principal_id")
    requester = Requester(requester)
    require_requester(PILOT_DOCUMENT, RequesterRole.FARM_MANAGER, requester)
    require_generator(PILOT_DOCUMENT, PILOT_GENERATOR)
    if not isinstance(sheet_date, date) or isinstance(sheet_date, datetime):
        raise ValueError("sheet_date_required")
    if not isinstance(revision, int) or revision < 1:
        raise ValueError("invalid_document_revision")
    normalized = _canonical_rows(rows)
    inputs = {"sheet_date": sheet_date.isoformat(), "rows": normalized}
    input_digest = sha256(_json(inputs)).hexdigest()
    document_id = _identity(document_id or f"WWS-{sheet_date:%Y%m%d}", "document_id")
    version_id = f"{document_id}.r{revision}.{input_digest[:12]}"
    pdf = _render(sheet_date, normalized, version_id)
    return WeeklySheetRevision(document_id, version_id, revision, sheet_date, pdf,
                               sha256(pdf).hexdigest(), input_digest)


def protected_print_preview(*, revision, job_id, green_id, printer_id,
                            cups_queue_id, registry_version, retrieval_url,
                            authorization_expires_at):
    """Return the exact payload to pass to the existing protected-claim rail."""
    if not isinstance(revision, WeeklySheetRevision):
        raise ValueError("weekly_sheet_revision_required")
    payload = {
        "contract_version": "documents_green_print_preview_v1",
        "job_id": _identity(job_id, "job_id"),
        "document_id": revision.document_id,
        "document_version": revision.version_id,
        "document_revision": revision.revision,
        "document_type": PILOT_DOCUMENT,
        "generator_id": PILOT_GENERATOR,
        "pdf_sha256": revision.pdf_sha256,
        "canonical_input_sha256": revision.canonical_input_sha256,
        "retrieval_url": str(retrieval_url),
        "green_id": _identity(green_id, "green_id"),
        "printer_id": _identity(printer_id, "printer_id"),
        "cups_queue_id": _identity(cups_queue_id, "cups_queue_id"),
        "registry_version": _identity(registry_version, "registry_version"),
        "authorization_expires_at": _aware_iso(authorization_expires_at),
        "options": dict(DEFAULTS),
        "physical_completion_required": True,
    }
    return {**payload, "preview_digest": canonical_preview_digest(PRINT_ACTION_KIND, payload)}


def authorized_job_from_claim(claim):
    """Bind one already-claimed confirmation to the exact immutable preview."""
    if claim.get("action_kind") != PRINT_ACTION_KIND:
        raise ValueError("protected_print_action_kind_mismatch")
    payload = claim.get("preview_payload")
    if not isinstance(payload, dict):
        raise ValueError("protected_print_preview_missing")
    expected = canonical_preview_digest(PRINT_ACTION_KIND, payload)
    if claim.get("preview_digest") != expected:
        raise ValueError("protected_print_preview_digest_mismatch")
    if payload.get("contract_version") != "documents_green_print_preview_v1":
        raise ValueError("protected_print_contract_invalid")
    receipt = _identity(claim.get("callback_token"), "authorization_receipt_id")
    return {**payload, "authorization_receipt_id": receipt}


def _canonical_rows(rows):
    if not isinstance(rows, (list, tuple)) or not rows:
        raise ValueError("canonical_weekly_rows_required")
    result = []
    seen = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid_weekly_row")
        pig_id = _identity(row.get("pig_id"), "pig_id")
        if pig_id in seen:
            raise ValueError("duplicate_weekly_pig_id")
        seen.add(pig_id)
        result.append({
            "pig_id": pig_id,
            "tag_number": str(row.get("tag_number") or "Unknown").strip()[:80],
            "pen_id": str(row.get("pen_id") or "Unknown").strip()[:80],
        })
    return sorted(result, key=lambda item: (item["pen_id"], item["tag_number"], item["pig_id"]))


def _render(sheet_date, rows, version_id):
    stream = BytesIO()
    canvas = Canvas(stream, pagesize=A4, pageCompression=1, invariant=1)
    width, height = A4
    canvas.setTitle("Weekly Weight Capture Sheet")
    canvas.setAuthor("Amadeus Farm Documents")
    canvas.setFont("Helvetica-Bold", 16)
    canvas.drawString(36, height - 44, "Weekly Weight Capture Sheet")
    canvas.setFont("Helvetica", 9)
    canvas.drawString(36, height - 60, f"Date: {sheet_date.isoformat()}   Revision: {version_id}")
    y = height - 86
    for heading, x in (("Pen", 36), ("Tag / Name", 130), ("Pig ID", 300), ("Weight kg", 455)):
        canvas.setFont("Helvetica-Bold", 9); canvas.drawString(x, y, heading)
    y -= 14
    for row in rows:
        if y < 45:
            canvas.showPage(); y = height - 45
        canvas.setFont("Helvetica", 8)
        canvas.drawString(36, y, row["pen_id"][:18])
        canvas.drawString(130, y, row["tag_number"][:30])
        canvas.drawString(300, y, row["pig_id"][:28])
        canvas.line(455, y - 2, 550, y - 2)
        y -= 16
    canvas.save()
    return stream.getvalue()


def _identity(value, field):
    value = str(value or "").strip()
    if not _ID.fullmatch(value):
        raise ValueError(f"invalid_{field}")
    return value


def _aware_iso(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("authorization_expiry_required")
    return value.astimezone(timezone.utc).isoformat()


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
