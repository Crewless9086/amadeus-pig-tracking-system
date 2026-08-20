"""Non-actuating schema/binding contract for the weekly-sheet pilot.

Inputs must already be verified by authenticated registry, protected-action,
canonical Documents, and trusted CUPS-observer services. These checks grant no
authority and establish neither provider nor physical truth.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
import re
from urllib.parse import unquote, urlparse

PILOT_DOCUMENT = "farm.weekly_weight_sheet.v1"
PILOT_GENERATOR = "web.print_sheets.v1"
DEFAULTS = {"media": "A4", "copies": 1, "color": "monochrome", "sides": "one-sided"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

class ContractError(ValueError): pass

@dataclass(frozen=True)
class RegisteredPair:
    green_id: str; printer_id: str; cups_queue_id: str; registry_version: str

@dataclass(frozen=True)
class AuthorizedJob:
    job_id: str; document_id: str; document_version: str; pdf_sha256: str
    retrieval_url: str; green_id: str; printer_id: str; cups_queue_id: str
    authorization_receipt_id: str; authorization_expires_at: datetime
    registry_version: str; document_type: str; generator_id: str; options: dict

def validate_authorized_job(value, *, allowed_origin, registered_pair, now):
    """Validate already-trusted envelope bindings; do not infer provenance."""
    required = ("job_id","document_id","document_version","pdf_sha256","retrieval_url","green_id",
                "printer_id","cups_queue_id","authorization_receipt_id","authorization_expires_at")
    if now.tzinfo is None or any(value.get(k) in (None, "") for k in required):
        raise ContractError("required_binding_missing")
    if value.get("document_type") != PILOT_DOCUMENT or value.get("generator_id") != PILOT_GENERATOR:
        raise ContractError("document_or_generator_not_allowlisted")
    if value.get("options") != DEFAULTS: raise ContractError("print_options_not_allowlisted")
    for key in ("job_id","document_id","document_version","green_id","printer_id","cups_queue_id","authorization_receipt_id"):
        if not isinstance(value[key], str) or not _ID.fullmatch(value[key]): raise ContractError("invalid_identity")
    actual = (value["green_id"], value["printer_id"], value["cups_queue_id"])
    expected = (registered_pair.green_id, registered_pair.printer_id, registered_pair.cups_queue_id)
    if actual != expected or not registered_pair.registry_version: raise ContractError("registered_identity_pair_mismatch")
    digest = str(value["pdf_sha256"]).lower()
    if not _SHA256.fullmatch(digest): raise ContractError("invalid_pdf_digest")
    expiry = value["authorization_expires_at"]
    if not isinstance(expiry, datetime) or expiry.tzinfo is None or expiry.astimezone(timezone.utc) <= now.astimezone(timezone.utc):
        raise ContractError("authorization_expired")
    url, origin = urlparse(value["retrieval_url"]), urlparse(allowed_origin)
    expected_path = f"/api/documents/{value['document_id']}/versions/{value['document_version']}/pdf"
    if (url.scheme,url.hostname,url.port) != ("https",origin.hostname,origin.port): raise ContractError("retrieval_origin_not_allowlisted")
    if url.username or url.password or url.fragment or url.query or unquote(url.path) != expected_path:
        raise ContractError("unsafe_or_unbound_retrieval_url")
    return AuthorizedJob(value["job_id"],value["document_id"],value["document_version"],digest,value["retrieval_url"],
                         value["green_id"],value["printer_id"],value["cups_queue_id"],value["authorization_receipt_id"],expiry,
                         registered_pair.registry_version,value["document_type"],value["generator_id"],dict(DEFAULTS))

def validate_cups_evidence(value, *, job, observer_id):
    """Validate a trusted observer envelope's bindings; not physical proof."""
    required=("observer_id","job_id","document_id","document_version","pdf_sha256","printer_id","cups_queue_id",
              "submission_attempt_id","cups_job_id","cups_state","observed_at")
    if any(value.get(k) in (None,"") for k in required): raise ContractError("cups_evidence_binding_missing")
    actual=(value["job_id"],value["document_id"],value["document_version"],value["pdf_sha256"],value["printer_id"],value["cups_queue_id"])
    expected=(job.job_id,job.document_id,job.document_version,job.pdf_sha256,job.printer_id,job.cups_queue_id)
    if value["observer_id"] != observer_id or actual != expected: raise ContractError("cups_evidence_binding_mismatch")
    if value["cups_state"] not in {"pending","processing","completed","aborted","cancelled","unknown"}: raise ContractError("invalid_cups_state")
    if not all(_ID.fullmatch(str(value[k])) for k in ("observer_id","submission_attempt_id","cups_job_id")): raise ContractError("invalid_cups_identity")
    if not isinstance(value["observed_at"],datetime) or value["observed_at"].tzinfo is None: raise ContractError("invalid_cups_observation_time")
    return {key: value[key] for key in required}
