"""Canonical signed evidence receipts for isolated CORE source validation."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


RECEIPT_VERSION = "charlie_isolated_validation_receipt_v2"
RECEIPT_ISSUER = "control_tower_isolated_validator_v2"
RECEIPT_MAX_AGE_SECONDS = 30 * 60
RECEIPT_CLOCK_SKEW_SECONDS = 5 * 60
_SHA256 = re.compile(r"[0-9a-f]{64}")
_COMMIT = re.compile(r"[0-9a-f]{40}")
_IDENTITY = re.compile(r"[0-9a-f]{32}")
_TOP_LEVEL_FIELDS = frozenset({
    "version", "validation_id", "source_commit", "issuer", "issued_at", "expires_at",
    "status", "suites", "isolation", "evidence_sha256", "signature_hmac_sha256",
})
_SUITE_FIELDS = frozenset({"name", "command_sha256", "passed", "failed", "skipped"})
_REQUIRED_SUITES = frozenset({"focused", "proportional"})
VALIDATION_COMMANDS = {
    "focused": ("python -B -m unittest tests.test_charlie_validation_receipt "
                "tests.test_charlie_isolated_validation_collector tests.test_charlie_runtime_staging"),
    "proportional": ("python -B -m unittest tests.test_vault_alignment "
                     "tests.test_charlie_validation_receipt tests.test_charlie_isolated_validation_collector "
                     "tests.test_charlie_runtime_staging "
                     "tests.test_charlie_runtime_integrity tests.test_charlie_runtime_activation"),
}
_ISOLATION_FIELDS = frozenset({
    "boundary", "host_processes_visible", "outside_boundary_targets", "network_enabled",
    "source_read_only", "capabilities_dropped", "unprivileged",
    "image_manifest_sha256", "image_config_sha256",
    "provider", "provider_actor", "provider_execution_id", "provider_execution_ids",
    "provider_config_sha256",
})


class ValidationReceiptError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def sign_validation_receipt(evidence, signing_key, *, validation_id=None, issued_at=None,
                            expires_at=None):
    """Sign already-collected evidence; never run tests, provision keys, or retry."""
    if not isinstance(evidence, dict):
        raise ValidationReceiptError("validation_evidence_invalid")
    key = _key(signing_key)
    source_commit = str(evidence.get("source_commit") or "").lower()
    suites = evidence.get("suites")
    isolation = evidence.get("isolation")
    if not _COMMIT.fullmatch(source_commit) or not isinstance(suites, list) or not suites:
        raise ValidationReceiptError("validation_evidence_invalid")
    _validate_suites(suites, allow_failures=True)
    _validate_isolation(isolation)
    identity = str(validation_id or uuid.uuid4().hex).lower()
    if not _IDENTITY.fullmatch(identity):
        raise ValidationReceiptError("validation_identity_invalid")
    issued = _parse_timestamp(issued_at or _utc_text(datetime.now(timezone.utc)))
    if issued is None:
        raise ValidationReceiptError("validation_timestamp_invalid")
    expiry = _parse_timestamp(expires_at or _utc_text(
        issued + timedelta(seconds=RECEIPT_MAX_AGE_SECONDS)))
    if expiry is None:
        raise ValidationReceiptError("validation_timestamp_invalid")
    lifetime = (expiry - issued).total_seconds()
    if lifetime <= 0 or lifetime > RECEIPT_MAX_AGE_SECONDS:
        raise ValidationReceiptError("validation_expiry_invalid")
    status = "passed" if all(row["failed"] == 0 and row["passed"] > 0 for row in suites) else "rejected"
    normalized = {"source_commit": source_commit, "suites": suites, "isolation": isolation}
    receipt = {
        "version": RECEIPT_VERSION, "validation_id": identity,
        "source_commit": source_commit, "issuer": RECEIPT_ISSUER,
        "issued_at": _utc_text(issued), "expires_at": _utc_text(expiry),
        "status": status, "suites": suites,
        "isolation": isolation,
        "evidence_sha256": hashlib.sha256(canonical_json(normalized)).hexdigest(),
    }
    receipt["signature_hmac_sha256"] = hmac.new(key, canonical_json(receipt), hashlib.sha256).hexdigest()
    return receipt


def write_validation_receipt(receipt, destination):
    """Persist passed or rejected evidence once; an existing identity is immutable."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json(receipt) + b"\n"
    try:
        descriptor = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise ValidationReceiptError("validation_evidence_already_recorded") from exc
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def record_validation_receipt(receipt, state_root):
    """Atomically retain one signed receipt as its create-once identity record."""
    if not isinstance(receipt, dict) or not _IDENTITY.fullmatch(str(receipt.get("validation_id") or "")):
        raise ValidationReceiptError("validation_identity_invalid")
    status = receipt.get("status")
    if status not in {"passed", "rejected"}:
        raise ValidationReceiptError("validation_status_invalid")
    state_root = Path(state_root).resolve()
    payload = canonical_json(receipt) + b"\n"
    digest = hashlib.sha256(payload).hexdigest()
    identity_path = state_root / "validation-identities" / f"{receipt['validation_id']}.json"
    write_validation_receipt(receipt, identity_path)
    return {"path": str(identity_path), "sha256": digest, "status": status}


def validate_validation_receipt(receipt, source_commit, signing_key, *, now=None):
    """Strictly validate a canonical passed receipt and return its identity."""
    if not isinstance(receipt, dict) or set(receipt) != _TOP_LEVEL_FIELDS:
        raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
    if receipt.get("version") != RECEIPT_VERSION or receipt.get("issuer") != RECEIPT_ISSUER:
        raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
    if not _IDENTITY.fullmatch(str(receipt.get("validation_id") or "")):
        raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
    if receipt.get("source_commit") != source_commit or not _COMMIT.fullmatch(str(source_commit or "")):
        raise ValidationReceiptError("isolated_validation_receipt_source_mismatch")
    issued = _parse_timestamp(receipt.get("issued_at"))
    expiry = _parse_timestamp(receipt.get("expires_at"))
    clock = _parse_clock(now)
    if issued is None or expiry is None:
        raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
    lifetime = (expiry - issued).total_seconds()
    if lifetime <= 0 or lifetime > RECEIPT_MAX_AGE_SECONDS:
        raise ValidationReceiptError("isolated_validation_receipt_expiry_invalid")
    if issued > clock + timedelta(seconds=RECEIPT_CLOCK_SKEW_SECONDS):
        raise ValidationReceiptError("isolated_validation_receipt_not_yet_valid")
    if clock >= expiry:
        raise ValidationReceiptError("isolated_validation_receipt_expired")
    _validate_suites(receipt.get("suites"), allow_failures=False)
    _validate_isolation(receipt.get("isolation"))
    evidence = {"source_commit": source_commit, "suites": receipt["suites"], "isolation": receipt["isolation"]}
    if receipt.get("evidence_sha256") != hashlib.sha256(canonical_json(evidence)).hexdigest():
        raise ValidationReceiptError("isolated_validation_receipt_evidence_invalid")
    signature = str(receipt.get("signature_hmac_sha256") or "")
    unsigned = {key: value for key, value in receipt.items() if key != "signature_hmac_sha256"}
    expected = hmac.new(_key(signing_key), canonical_json(unsigned), hashlib.sha256).hexdigest()
    if not _SHA256.fullmatch(signature) or not hmac.compare_digest(signature, expected):
        raise ValidationReceiptError("isolated_validation_receipt_signature_invalid")
    if receipt.get("status") != "passed":
        raise ValidationReceiptError("isolated_validation_receipt_rejected")
    return {"validation_id": receipt["validation_id"], "evidence_sha256": receipt["evidence_sha256"]}


def _validate_suites(suites, *, allow_failures):
    if not isinstance(suites, list) or not suites:
        raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
    names = set()
    for row in suites:
        if not isinstance(row, dict) or set(row) != _SUITE_FIELDS:
            raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
        name = row.get("name")
        if not isinstance(name, str) or not name or name in names:
            raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
        names.add(name)
        expected_command = hashlib.sha256(VALIDATION_COMMANDS.get(name, "").encode("utf-8")).hexdigest()
        if row.get("command_sha256") != expected_command:
            raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
        for field in ("passed", "failed", "skipped"):
            value = row.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
        if not allow_failures and (row["passed"] <= 0 or row["failed"] != 0):
            raise ValidationReceiptError("isolated_validation_receipt_rejected")
    if names != _REQUIRED_SUITES:
        raise ValidationReceiptError("isolated_validation_receipt_required_suites_invalid")


def _validate_isolation(isolation):
    if not isinstance(isolation, dict) or set(isolation) != _ISOLATION_FIELDS:
        raise ValidationReceiptError("isolated_validation_receipt_schema_invalid")
    expected = {
        "boundary": "disposable_process_boundary", "host_processes_visible": False,
        "outside_boundary_targets": 0, "network_enabled": False, "source_read_only": True,
        "capabilities_dropped": True, "unprivileged": True,
        "provider": "docker_engine",
        "provider_actor": "control_tower_isolated_validator_v2",
    }
    if any(isolation.get(key) != value for key, value in expected.items()):
        raise ValidationReceiptError("isolated_validation_receipt_isolation_invalid")
    for field in ("image_manifest_sha256", "image_config_sha256"):
        if not _SHA256.fullmatch(str(isolation.get(field) or "")):
            raise ValidationReceiptError("isolated_validation_receipt_isolation_invalid")
    if not _SHA256.fullmatch(str(isolation.get("provider_execution_id") or "")):
        raise ValidationReceiptError("isolated_validation_receipt_isolation_invalid")
    executions = isolation.get("provider_execution_ids")
    if (not isinstance(executions, list) or len(executions) != 2
            or len(set(executions)) != 2
            or any(not _SHA256.fullmatch(str(value or "")) for value in executions)):
        raise ValidationReceiptError("isolated_validation_receipt_isolation_invalid")
    if isolation["provider_execution_id"] != hashlib.sha256(canonical_json(executions)).hexdigest():
        raise ValidationReceiptError("isolated_validation_receipt_isolation_invalid")
    if not _SHA256.fullmatch(str(isolation.get("provider_config_sha256") or "")):
        raise ValidationReceiptError("isolated_validation_receipt_isolation_invalid")
    provider_config = {
        "provider": isolation["provider"], "network": "none",
        "rootfs_read_only": True, "source_read_only": isolation["source_read_only"],
        "cap_drop": ["ALL"], "no_new_privileges": True,
        "user": "65532:65532", "pid_mode": "private", "pids_limit": 256,
        "image_manifest_sha256": isolation["image_manifest_sha256"],
        "image_config_sha256": isolation["image_config_sha256"],
    }
    if isolation["provider_config_sha256"] != hashlib.sha256(
            canonical_json(provider_config)).hexdigest():
        raise ValidationReceiptError("isolated_validation_receipt_isolation_invalid")


def _key(value):
    if not isinstance(value, (bytes, bytearray)) or len(value) < 32:
        raise ValidationReceiptError("validation_receipt_authority_invalid")
    return bytes(value)


def _parse_timestamp(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        return None
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        return None
    return parsed.astimezone(timezone.utc)


def _parse_clock(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        if value.tzinfo is None:
            raise ValidationReceiptError("validation_clock_invalid")
        return value.astimezone(timezone.utc)
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise ValidationReceiptError("validation_clock_invalid")
    return parsed


def _utc_text(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
