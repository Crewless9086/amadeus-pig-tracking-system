"""Content-addressed, signed admission receipts for repository mutation."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime, timedelta, timezone

from modules.charlie.validation_receipt import RECEIPT_ISSUER, canonical_json


RECEIPT_VERSION = "mission_admission_receipt_v1"
ADMISSION_AUTHORITY = RECEIPT_ISSUER
RECEIPT_MAX_AGE_SECONDS = 24 * 60 * 60
RECEIPT_CLOCK_SKEW_SECONDS = 5 * 60

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_BLOB = re.compile(r"^[0-9a-f]{40}$")
_RECEIPT_ID = re.compile(r"^MAR-[0-9A-F]{64}$")
_TOP_LEVEL_FIELDS = frozenset({
    "version",
    "receipt_id",
    "authority",
    "issued_at",
    "expires_at",
    "mission",
    "owner_instruction_chain",
    "repository",
    "governance_reads",
    "existing_system_trace",
    "scope",
    "collision_snapshot",
    "required_tests",
    "operational_acceptance",
    "candidate",
    "content_sha256",
    "signature_hmac_sha256",
})
_MISSION_FIELDS = frozenset({"mission_id", "root_mission_id", "generation"})
_OWNER_CHAIN_FIELDS = frozenset({
    "instruction_digests",
    "latest_correction_digest",
    "admission_packet_sha256",
})
_REPOSITORY_FIELDS = frozenset({"repository", "base_ref", "base_sha"})
_GOVERNANCE_FIELDS = frozenset({
    "path",
    "git_blob",
    "filesystem_sha256",
    "byte_count",
    "physical_line_count",
    "complete_byte_read",
})
_TRACE_FIELDS = frozenset({"smallest_genuine_gap", "reused_components", "implementation_sources"})
_SCOPE_FIELDS = frozenset({
    "allowed_files",
    "forbidden_files",
    "allowed_effects",
    "forbidden_effects",
})
_COLLISION_FIELDS = frozenset({"captured_at", "active_claims", "snapshot_sha256"})
_CLAIM_FIELDS = frozenset({"claim_id", "owner", "paths", "effects", "state"})
_ACCEPTANCE_FIELDS = frozenset({"requirements", "business_outcome_authorized"})
_CANDIDATE_FIELDS = frozenset({
    "candidate_id",
    "branch",
    "base_sha",
    "head_sha",
    "diff_sha256",
    "changed_files",
})


class MissionAdmissionError(ValueError):
    """A stable fail-closed admission reason code."""


def sign_mission_admission_receipt(payload, signing_key, *, issued_at=None, expires_at=None):
    """Create one deterministic receipt using the existing validation authority."""
    if not isinstance(payload, dict):
        raise MissionAdmissionError("admission_payload_invalid")
    key = _key(signing_key)
    issued = _parse_timestamp(issued_at or _utc_text(datetime.now(timezone.utc)))
    if issued is None:
        raise MissionAdmissionError("admission_timestamp_invalid")
    expiry = _parse_timestamp(
        expires_at or _utc_text(issued + timedelta(seconds=RECEIPT_MAX_AGE_SECONDS))
    )
    if expiry is None:
        raise MissionAdmissionError("admission_timestamp_invalid")
    _validate_lifetime(issued, expiry)

    body = {
        "version": RECEIPT_VERSION,
        "authority": ADMISSION_AUTHORITY,
        "issued_at": _utc_text(issued),
        "expires_at": _utc_text(expiry),
        **payload,
    }
    if set(body) != _TOP_LEVEL_FIELDS - {
        "receipt_id",
        "content_sha256",
        "signature_hmac_sha256",
    }:
        raise MissionAdmissionError("admission_receipt_schema_invalid")
    _validate_body(body)
    content_digest = hashlib.sha256(canonical_json(body)).hexdigest()
    receipt = {
        **body,
        "receipt_id": f"MAR-{content_digest.upper()}",
        "content_sha256": content_digest,
    }
    receipt["signature_hmac_sha256"] = hmac.new(
        key, canonical_json(receipt), hashlib.sha256
    ).hexdigest()
    return receipt


def validate_mission_admission_receipt(
    receipt,
    signing_key,
    *,
    expected_repository="",
    expected_base_sha="",
    expected_head_sha="",
    expected_generation="",
    expected_changed_files=None,
    now=None,
):
    """Strictly verify signature, immutable content, freshness, and exact context."""
    if not isinstance(receipt, dict) or set(receipt) != _TOP_LEVEL_FIELDS:
        raise MissionAdmissionError("admission_receipt_schema_invalid")
    if receipt.get("version") != RECEIPT_VERSION or receipt.get("authority") != ADMISSION_AUTHORITY:
        raise MissionAdmissionError("admission_receipt_schema_invalid")
    body = {
        key: value
        for key, value in receipt.items()
        if key not in {"receipt_id", "content_sha256", "signature_hmac_sha256"}
    }
    _validate_body(body)

    content_digest = hashlib.sha256(canonical_json(body)).hexdigest()
    if receipt.get("content_sha256") != content_digest:
        raise MissionAdmissionError("admission_content_digest_invalid")
    expected_id = f"MAR-{content_digest.upper()}"
    if receipt.get("receipt_id") != expected_id or not _RECEIPT_ID.fullmatch(str(receipt.get("receipt_id") or "")):
        raise MissionAdmissionError("admission_identity_invalid")

    signature = str(receipt.get("signature_hmac_sha256") or "")
    unsigned = {
        key: value for key, value in receipt.items() if key != "signature_hmac_sha256"
    }
    expected_signature = hmac.new(
        _key(signing_key), canonical_json(unsigned), hashlib.sha256
    ).hexdigest()
    if not _SHA256.fullmatch(signature) or not hmac.compare_digest(signature, expected_signature):
        raise MissionAdmissionError("admission_signature_invalid")

    issued = _parse_timestamp(receipt["issued_at"])
    expiry = _parse_timestamp(receipt["expires_at"])
    _validate_lifetime(issued, expiry)
    clock = _parse_clock(now)
    if issued > clock + timedelta(seconds=RECEIPT_CLOCK_SKEW_SECONDS):
        raise MissionAdmissionError("admission_not_yet_valid")
    if clock >= expiry:
        raise MissionAdmissionError("admission_expired")

    repository = receipt["repository"]
    candidate = receipt["candidate"]
    mission = receipt["mission"]
    if expected_repository and repository["repository"] != expected_repository:
        raise MissionAdmissionError("admission_repository_changed")
    if expected_base_sha and repository["base_sha"] != expected_base_sha:
        raise MissionAdmissionError("admission_base_changed")
    if expected_head_sha and candidate["head_sha"] != expected_head_sha:
        raise MissionAdmissionError("admission_candidate_changed")
    if expected_generation and mission["generation"] != expected_generation:
        raise MissionAdmissionError("admission_generation_changed")
    if expected_changed_files is not None:
        changed = _paths(expected_changed_files, "admission_candidate_paths_invalid")
        if changed != candidate["changed_files"]:
            raise MissionAdmissionError("admission_candidate_changed")
    return {
        "receipt_id": receipt["receipt_id"],
        "content_sha256": content_digest,
        "mission_id": mission["mission_id"],
        "root_mission_id": mission["root_mission_id"],
        "generation": mission["generation"],
        "base_sha": repository["base_sha"],
        "head_sha": candidate["head_sha"],
        "allowed_files": list(receipt["scope"]["allowed_files"]),
        "forbidden_files": list(receipt["scope"]["forbidden_files"]),
        "allowed_effects": list(receipt["scope"]["allowed_effects"]),
        "forbidden_effects": list(receipt["scope"]["forbidden_effects"]),
        "changed_files": list(candidate["changed_files"]),
    }


def canonical_candidate_diff(changed_files, patch_bytes):
    """Bind a candidate path set and complete base-to-head patch bytes."""
    paths = _paths(changed_files, "admission_candidate_paths_invalid")
    patch = patch_bytes if isinstance(patch_bytes, bytes) else str(patch_bytes).encode("utf-8")
    return hashlib.sha256(canonical_json({
        "changed_files": paths,
        "patch_sha256": hashlib.sha256(patch).hexdigest(),
    })).hexdigest()


def collision_snapshot_digest(captured_at, active_claims):
    claims = active_claims if isinstance(active_claims, list) else []
    return hashlib.sha256(canonical_json({
        "captured_at": captured_at,
        "active_claims": claims,
    })).hexdigest()


def _validate_body(body):
    if body.get("version") != RECEIPT_VERSION or body.get("authority") != ADMISSION_AUTHORITY:
        raise MissionAdmissionError("admission_receipt_schema_invalid")
    issued = _parse_timestamp(body.get("issued_at"))
    expiry = _parse_timestamp(body.get("expires_at"))
    _validate_lifetime(issued, expiry)

    mission = _object(body.get("mission"), _MISSION_FIELDS)
    if not all(_text(mission.get(key), 200) for key in _MISSION_FIELDS):
        raise MissionAdmissionError("admission_mission_identity_invalid")

    owner = _object(body.get("owner_instruction_chain"), _OWNER_CHAIN_FIELDS)
    digests = owner.get("instruction_digests")
    if (
        not isinstance(digests, list)
        or not digests
        or len(set(digests)) != len(digests)
        or any(not _SHA256.fullmatch(str(item or "")) for item in digests)
        or not _SHA256.fullmatch(str(owner.get("latest_correction_digest") or ""))
        or owner["latest_correction_digest"] != digests[-1]
        or not _SHA256.fullmatch(str(owner.get("admission_packet_sha256") or ""))
    ):
        raise MissionAdmissionError("admission_owner_instruction_chain_invalid")

    repository = _object(body.get("repository"), _REPOSITORY_FIELDS)
    if (
        not _text(repository.get("repository"), 300)
        or not _text(repository.get("base_ref"), 200)
        or not _COMMIT.fullmatch(str(repository.get("base_sha") or ""))
    ):
        raise MissionAdmissionError("admission_repository_identity_invalid")

    governance = body.get("governance_reads")
    if not isinstance(governance, list) or not governance:
        raise MissionAdmissionError("admission_governance_reads_invalid")
    governance_paths = []
    for row in governance:
        item = _object(row, _GOVERNANCE_FIELDS)
        path = _path(item.get("path"))
        if (
            not path
            or not _BLOB.fullmatch(str(item.get("git_blob") or ""))
            or not _SHA256.fullmatch(str(item.get("filesystem_sha256") or ""))
            or isinstance(item.get("byte_count"), bool)
            or not isinstance(item.get("byte_count"), int)
            or item["byte_count"] <= 0
            or isinstance(item.get("physical_line_count"), bool)
            or not isinstance(item.get("physical_line_count"), int)
            or item["physical_line_count"] <= 0
            or item.get("complete_byte_read") is not True
        ):
            raise MissionAdmissionError("admission_governance_reads_invalid")
        governance_paths.append(path)
    if governance_paths != sorted(set(governance_paths)):
        raise MissionAdmissionError("admission_governance_reads_invalid")

    trace = _object(body.get("existing_system_trace"), _TRACE_FIELDS)
    if (
        not _text(trace.get("smallest_genuine_gap"), 4000)
        or not _nonempty_text_list(trace.get("reused_components"))
        or not _paths(trace.get("implementation_sources"), "admission_source_trace_invalid")
    ):
        raise MissionAdmissionError("admission_source_trace_invalid")

    scope = _object(body.get("scope"), _SCOPE_FIELDS)
    allowed_files = _paths(scope.get("allowed_files"), "admission_scope_invalid")
    forbidden_files = _paths(scope.get("forbidden_files"), "admission_scope_invalid")
    if set(allowed_files).intersection(forbidden_files):
        raise MissionAdmissionError("admission_scope_conflict")
    if not _nonempty_text_list(scope.get("allowed_effects")) or not _nonempty_text_list(scope.get("forbidden_effects")):
        raise MissionAdmissionError("admission_scope_invalid")

    collision = _object(body.get("collision_snapshot"), _COLLISION_FIELDS)
    if _parse_timestamp(collision.get("captured_at")) is None or not isinstance(collision.get("active_claims"), list):
        raise MissionAdmissionError("admission_collision_snapshot_invalid")
    for claim in collision["active_claims"]:
        item = _object(claim, _CLAIM_FIELDS)
        claim_paths = _paths(
            item.get("paths"),
            "admission_collision_snapshot_invalid",
            allow_empty=True,
        )
        claim_effects_valid = _nonempty_text_list(item.get("effects"), allow_empty=True)
        if (
            not _text(item.get("claim_id"), 300)
            or not _text(item.get("owner"), 300)
            or not claim_effects_valid
            or not (claim_paths or item.get("effects"))
            or item.get("state") not in {"active", "waiting", "released", "historical"}
        ):
            raise MissionAdmissionError("admission_collision_snapshot_invalid")
    expected_snapshot = collision_snapshot_digest(
        collision["captured_at"], collision["active_claims"]
    )
    if collision.get("snapshot_sha256") != expected_snapshot:
        raise MissionAdmissionError("admission_collision_snapshot_changed")

    tests = body.get("required_tests")
    if not _nonempty_text_list(tests):
        raise MissionAdmissionError("admission_required_tests_invalid")
    acceptance = _object(body.get("operational_acceptance"), _ACCEPTANCE_FIELDS)
    if not _nonempty_text_list(acceptance.get("requirements")):
        raise MissionAdmissionError("admission_operational_acceptance_invalid")
    if acceptance.get("business_outcome_authorized") is not False:
        raise MissionAdmissionError("admission_business_outcome_authority_invalid")

    candidate = _object(body.get("candidate"), _CANDIDATE_FIELDS)
    changed_files = _paths(candidate.get("changed_files"), "admission_candidate_invalid")
    if (
        not _text(candidate.get("candidate_id"), 300)
        or not _text(candidate.get("branch"), 300)
        or candidate.get("base_sha") != repository["base_sha"]
        or not _COMMIT.fullmatch(str(candidate.get("head_sha") or ""))
        or not _SHA256.fullmatch(str(candidate.get("diff_sha256") or ""))
        or not set(changed_files).issubset(allowed_files)
        or set(changed_files).intersection(forbidden_files)
    ):
        raise MissionAdmissionError("admission_candidate_invalid")


def _object(value, fields):
    if not isinstance(value, dict) or set(value) != fields:
        raise MissionAdmissionError("admission_receipt_schema_invalid")
    return value


def _path(value):
    text = str(value or "").strip().replace("\\", "/")
    if not text or text.startswith("/") or text.startswith("../") or "/../" in text or text == "..":
        return ""
    return text


def _paths(values, reason, *, allow_empty=False):
    if not isinstance(values, list):
        raise MissionAdmissionError(reason)
    normalized = [_path(value) for value in values]
    if (
        (not allow_empty and not normalized)
        or any(not value for value in normalized)
        or normalized != sorted(set(normalized))
    ):
        raise MissionAdmissionError(reason)
    return normalized


def _nonempty_text_list(values, *, allow_empty=False):
    return (
        isinstance(values, list)
        and (allow_empty or bool(values))
        and all(isinstance(value, str) and value.strip() for value in values)
        and len(values) == len(set(values))
    )


def _key(value):
    if not isinstance(value, (bytes, bytearray)) or len(value) < 32:
        raise MissionAdmissionError("admission_validation_authority_invalid")
    return bytes(value)


def _text(value, maximum):
    text = str(value or "").strip()
    return text[:maximum] if text else ""


def _validate_lifetime(issued, expiry):
    if issued is None or expiry is None:
        raise MissionAdmissionError("admission_timestamp_invalid")
    lifetime = (expiry - issued).total_seconds()
    if lifetime <= 0 or lifetime > RECEIPT_MAX_AGE_SECONDS:
        raise MissionAdmissionError("admission_expiry_invalid")


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
            raise MissionAdmissionError("admission_clock_invalid")
        return value.astimezone(timezone.utc)
    parsed = _parse_timestamp(value)
    if parsed is None:
        raise MissionAdmissionError("admission_clock_invalid")
    return parsed


def _utc_text(value):
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
