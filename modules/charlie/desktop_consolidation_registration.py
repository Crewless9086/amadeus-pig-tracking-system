"""One paused first-registration, never a general mission metadata writer.

This is a maintainer preparation/registration boundary, not owner authentication.
The caller must independently authenticate Charl's exact, manifest-bound approval.
No receipt, admission projection, release approval or dispatch is produced here.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import re

from modules.charlie import mission_store
from modules.charlie.mission_control import (
    apply_event_to_projection, build_mission_control_event,
)

MISSION_ID = "REPOSITORY-CONSOLIDATION-20260918"
TASK_ID = "01a0b9d5-5c55-7e30-a5fc-aea27c93ffd6"
REPOSITORY = "Crewless9086/amadeus-pig-tracking-system"
VERSION = "desktop_consolidation_first_registration_v1"
DECISION = "approve_first_paused_registration_only"
FORBIDDEN_EFFECTS = [
    "admission_issuance", "business_record_write", "customer_send", "deployment",
    "dispatch", "farm_write", "hardware_control", "merge", "payment",
    "permission_change", "protection_change", "provider_publication",
    "release_approval", "reservation", "worker_start",
]
ALLOWED_EFFECTS = [
    "repository_candidate_validation", "repository_commit", "repository_file_write",
    "repository_index_write", "test_execution",
]
IMPLEMENTATION_PATHS = (
    "modules/charlie/desktop_consolidation_registration.py",
    "scripts/register_desktop_consolidation.py",
)
BOOTSTRAP_PATHS = sorted((*IMPLEMENTATION_PATHS,
    ".github/workflows/charlie-core-tests.yml",
    "scripts/charlie_mission_admission_guard.py",
    "tests/test_charlie_mission_admission.py",
    "tests/test_charlie_desktop_consolidation_registration.py"))
_MANIFEST_KEYS = {
    "version", "mission_id", "task_id", "repository", "expected_state",
    "idempotency_key", "generation", "expires_at", "owner_instruction",
    "candidate", "implementation", "required_tests", "test_evidence",
    "review_evidence", "operational_acceptance",
}
_APPROVAL_KEYS = {
    "version", "decision", "approval_id", "manifest_sha256", "owner_principal",
    "task_id", "source_message_id", "evidence_ref", "instruction_text",
    "issued_at", "expires_at",
}


class RegistrationError(ValueError):
    """A failed exact registration boundary; no safe fallback is implied."""


def _json_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def _utc_now():
    return datetime.now(timezone.utc)


def _object(value, keys, label):
    if not isinstance(value, dict) or set(value) != set(keys):
        raise RegistrationError(label + "_fields_invalid")
    return value


def _text(value, label, limit=500):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > limit:
        raise RegistrationError(label + "_invalid")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise RegistrationError(label + "_invalid")
    return value


def _sha(value, label, length=64):
    if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % length, value):
        raise RegistrationError(label + "_invalid")
    return value


def _time(value, label):
    try:
        parsed = datetime.fromisoformat(_text(value, label).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError
        return parsed.astimezone(timezone.utc)
    except ValueError as exc:
        raise RegistrationError(label + "_invalid") from exc


def _strings(value, label, *, paths=False):
    if not isinstance(value, list) or not value or len(value) > 250:
        raise RegistrationError(label + "_invalid")
    result = [_text(item, label) for item in value]
    if result != sorted(set(result)):
        raise RegistrationError(label + "_must_be_sorted_unique")
    if paths and any(
        item.startswith(("/", ".git/")) or "\\" in item or ":" in item
        or any(part in {"", ".", ".."} for part in item.split("/"))
        or any(char in item for char in "*?[]\n\t") for item in result
    ):
        raise RegistrationError(label + "_invalid")
    return result


def _load(raw, expected_digest, label):
    if not isinstance(raw, bytes) or len(raw) > 262144:
        raise RegistrationError(label + "_bytes_invalid")
    if sha256(raw) != _sha(expected_digest, label + "_sha256"):
        raise RegistrationError(label + "_sha256_mismatch")

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise RegistrationError(label + "_duplicate_key")
            result[key] = value
        return result

    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=pairs,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (UnicodeError, ValueError) as exc:
        raise RegistrationError(label + "_json_invalid") from exc


def prepare_registration(manifest_bytes, *, expected_manifest_sha256,
                         approval_bytes, expected_approval_sha256, now=None):
    """Validate an immutable package without reading credentials or a database.

    A successful preparation proves structure and byte binding, not that the
    person represented in the supplied evidence really approved it.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise RegistrationError("timezone_required")
    manifest = _object(_load(manifest_bytes, expected_manifest_sha256, "manifest"),
                       _MANIFEST_KEYS, "manifest")
    approval = _object(_load(approval_bytes, expected_approval_sha256, "approval"),
                       _APPROVAL_KEYS, "approval")
    if (manifest["version"] != VERSION or manifest["mission_id"] != MISSION_ID
            or manifest["task_id"] != TASK_ID or manifest["repository"] != REPOSITORY
            or manifest["expected_state"] != "absent"):
        raise RegistrationError("registration_scope_invalid")
    for key in ("idempotency_key", "generation"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]{7,159}", str(manifest[key])):
            raise RegistrationError(key + "_invalid")
    instruction = _object(manifest["owner_instruction"], {
        "owner_principal", "task_id", "source_message_id", "evidence_ref",
        "text", "text_sha256", "issued_at",
    }, "owner_instruction")
    principal = _text(instruction["owner_principal"], "owner_principal", 180)
    if not principal.startswith("owner:") or instruction["task_id"] != TASK_ID:
        raise RegistrationError("owner_instruction_identity_invalid")
    for key in ("source_message_id", "evidence_ref"):
        _text(instruction[key], "owner_instruction_" + key)
    _text(instruction["text"], "owner_instruction_text", 2000)
    if sha256(instruction["text"].encode("utf-8")) != instruction["text_sha256"]:
        raise RegistrationError("owner_instruction_sha256_mismatch")
    issued = _time(approval["issued_at"], "approval_issued_at")
    expires = _time(manifest["expires_at"], "expires_at")
    if (approval["version"] != VERSION or approval["decision"] != DECISION
            or approval["manifest_sha256"] != expected_manifest_sha256
            or approval["owner_principal"] != principal or approval["task_id"] != TASK_ID
            or _time(approval["expires_at"], "approval_expires_at") != expires):
        raise RegistrationError("approval_binding_invalid")
    if (not _time(instruction["issued_at"], "instruction_issued_at") <= issued <= now < expires
            or expires - issued > timedelta(hours=24)):
        raise RegistrationError("approval_not_current")
    for key in ("approval_id", "source_message_id", "evidence_ref"):
        _text(approval[key], "approval_" + key, 120 if key.endswith("id") else 500)
    _text(approval["instruction_text"], "approval_instruction_text", 2000)
    candidate = _object(manifest["candidate"], {
        "pr_number", "branch", "base_sha", "head_sha", "tree_sha",
        "diff_sha256", "changed_files",
    }, "candidate")
    if type(candidate["pr_number"]) is not int or candidate["pr_number"] <= 0:
        raise RegistrationError("candidate_pr_required")
    if not re.fullmatch(r"codex/[A-Za-z0-9._/-]+", str(candidate["branch"])):
        raise RegistrationError("candidate_branch_invalid")
    for key in ("base_sha", "head_sha", "tree_sha"):
        _sha(candidate[key], "candidate_" + key, 40)
    if candidate["base_sha"] == candidate["head_sha"]:
        raise RegistrationError("candidate_empty")
    _sha(candidate["diff_sha256"], "candidate_diff")
    paths = _strings(candidate["changed_files"], "candidate_paths", paths=True)
    if paths != BOOTSTRAP_PATHS:
        raise RegistrationError("candidate_outside_bootstrap_scope")
    implementation = _object(manifest["implementation"], {"revision", "files"}, "implementation")
    _sha(implementation["revision"], "implementation_revision", 40)
    _object(implementation["files"], IMPLEMENTATION_PATHS, "implementation_files")
    for value in implementation["files"].values():
        _sha(value, "implementation_file")
    for key in ("required_tests", "operational_acceptance"):
        _strings(manifest[key], key)
    for key in ("test_evidence", "review_evidence"):
        if not isinstance(manifest[key], list) or not manifest[key] or len(manifest[key]) > 20:
            raise RegistrationError(key + "_required")
        for evidence in manifest[key]:
            _object(evidence, {"ref", "sha256"}, key)
            _text(evidence["ref"], key + "_ref")
            _sha(evidence["sha256"], key + "_sha256")
    contract = {
        "generation": manifest["generation"], "branch": candidate["branch"],
        "base_sha": candidate["base_sha"], "allowed_files": paths,
        "forbidden_files": ["*"], "allowed_effects": ALLOWED_EFFECTS,
        "forbidden_effects": FORBIDDEN_EFFECTS,
        "required_tests": manifest["required_tests"],
        "operational_acceptance": manifest["operational_acceptance"],
    }
    packet = {
        "repository": REPOSITORY, "pr_number": candidate["pr_number"],
        "branch_name": candidate["branch"], "candidate_revision": candidate["head_sha"],
        "candidate_tree": candidate["tree_sha"],
        "candidate_diff_sha256": candidate["diff_sha256"], "changed_files": paths,
        "test_evidence": manifest["test_evidence"], "review_evidence": manifest["review_evidence"],
    }
    finding = build_mission_control_event(MISSION_ID, {
        "event_type": "finding_recorded", "summary": instruction["text"],
        "idempotency_key": manifest["idempotency_key"] + ":instruction",
        "evidence_refs": [instruction["evidence_ref"], "sha256:" + instruction["text_sha256"]],
    }, recorded_by=principal, now=_time(instruction["issued_at"], "instruction_issued_at"))
    correction = build_mission_control_event(MISSION_ID, {
        "event_type": "owner_correction_recorded", "summary": approval["instruction_text"],
        "corrects_event_id": finding["event_id"],
        "idempotency_key": manifest["idempotency_key"] + ":" + approval["approval_id"],
        "real_life_state": "prepared", "current_worker": "codex_desktop:" + TASK_ID,
        "first_missing_acceptance_gate": "Separate protected-main admission and release verification.",
        "next_automatic_step": "NONE: registration is paused and non-runnable.",
        "owner_action": "NONE: this event grants first registration only.",
        "evidence_refs": [approval["evidence_ref"], "sha256:" + expected_manifest_sha256,
                          "sha256:" + expected_approval_sha256],
    }, recorded_by=principal, now=issued)
    registration = {
        "version": VERSION, "manifest_sha256": expected_manifest_sha256,
        "approval_sha256": expected_approval_sha256, "manifest": manifest,
        "approval": approval, "runnable": False,
    }
    metadata = {
        "desktop_first_registration": registration,
        "external_supervisor": {"principal": "codex_desktop:" + TASK_ID,
                                "transport": "codex_desktop", "task_id": TASK_ID},
        "review_packet": packet, "mission_admission_contract": contract,
        "mission_family": {"root_mission_id": MISSION_ID, "generation": manifest["generation"]},
        # Existing execution selection fails closed for every classified row.
        "portfolio_classification": {"classification": "registration_only", "runnable": False},
    }
    mission = {
        "mission_id": MISSION_ID, "status": "paused", "approval_level": "LEVEL 0",
        "title": "Preserve and integrate the Amadeus repository consolidation",
        "raw_text": instruction["text"], "mission_type": "review", "urgency": "P2",
        "selected_next_step": "Separate protected-main admission; no execution or release authorized.",
        "owner_decision": "first_registration_only", "codex_chat_write_status": "not_requested",
        "metadata": metadata,
    }
    metadata["mission_control_projection"] = apply_event_to_projection(mission, correction)
    params = mission_store._mission_params(mission, {
        "source": "codex_desktop", "message_id": instruction["source_message_id"],
    })
    generated = json.loads(params["metadata_json"])
    # Canonical builders stamp these informational fields with local wall time.
    # Bind them to this immutable registration's approval time for exact replay.
    stamp = issued.isoformat()
    generated["orchestration"]["created_at"] = stamp
    generated["mission_vault"]["project_truth"]["created_at"] = stamp
    generated["charlie_core"]["project_truth"]["created_at"] = stamp
    generated["mission_governance"]["updated_at"] = stamp
    generated["mission_governance"]["frozen_at"] = stamp
    params["metadata_json"] = json.dumps(generated, sort_keys=True)
    if mission_store.mission_runtime_eligible({"metadata": generated}):
        raise RegistrationError("registration_unexpectedly_runnable")
    return {"manifest_sha256": expected_manifest_sha256,
            "approval_sha256": expected_approval_sha256, "params": params,
            "events": [finding, correction], "requires_independent_owner_authentication": True}


def verify_registration_source(manifest):
    """Recheck pins on every apply, even when preparation was bypassed."""
    from scripts.register_desktop_consolidation import verify_local_candidate
    verify_local_candidate(manifest)


def register_first_mission(manifest_bytes, *, expected_manifest_sha256,
                          approval_bytes, expected_approval_sha256,
                          authenticated_owner_principal="", database_url=None,
                          connect_factory=None, dry_run=True, now=None):
    """First-create the exact paused mission and two canonical events atomically.

    Direct callers are trusted maintainer code, never public request handlers.
    They must authenticate approval evidence separately. The CLI intentionally
    exposes preparation only; it cannot connect to production or apply a plan.
    """
    if not dry_run and now is not None:
        raise RegistrationError("apply_clock_override_forbidden")
    plan = prepare_registration(
        manifest_bytes, expected_manifest_sha256=expected_manifest_sha256,
        approval_bytes=approval_bytes, expected_approval_sha256=expected_approval_sha256,
        now=now if dry_run else _utc_now())
    if dry_run:
        return {"status": "dry_run", "database_accessed": False, "writes": 0, "plan": plan}
    principal = plan["events"][1]["recorded_by"]
    if authenticated_owner_principal != principal:
        raise RegistrationError("independently_authenticated_owner_required")
    manifest = json.loads(plan["params"]["metadata_json"])["desktop_first_registration"]["manifest"]
    verify_registration_source(manifest)
    if not database_url and connect_factory is None:
        raise RegistrationError("explicit_database_connection_required")
    params = plan["params"]
    columns = tuple(params)
    expected = [params[key] for key in columns]
    metadata_index = columns.index("metadata_json")
    expected[metadata_index] = json.loads(expected[metadata_index])

    def readback(cursor):
        cursor.execute("select " + ",".join(columns) +
                       " from public.charlie_missions where mission_id=%s for update", (MISSION_ID,))
        row = cursor.fetchone()
        if row is None:
            return None
        if list(row) != expected:
            raise RegistrationError("existing_mission_conflicts_with_exact_registration")
        cursor.execute("select event_id,event_type,recorded_by,metadata_json from "
                       "public.charlie_mission_events where mission_id=%s order by event_id", (MISSION_ID,))
        expected_events = sorted((event["event_id"], event["event_type"],
                                  principal, event) for event in plan["events"])
        if list(cursor.fetchall()) != expected_events:
            raise RegistrationError("registration_event_readback_mismatch")
        return row

    # Advisory lock serializes this helper. The primary key plus plain INSERT
    # contains a concurrent insertion by other canonical writers without update.
    with mission_store._connect(database_url or "", connect_factory) as connection:
        if getattr(connection, "autocommit", False):
            raise RegistrationError("transaction_required")
        with connection.cursor() as cursor:
            cursor.execute("set local lock_timeout='3s'")
            cursor.execute("set local statement_timeout='10s'")
            cursor.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))", (VERSION + ":" + MISSION_ID,))
            if _utc_now() >= _time(manifest["expires_at"], "expires_at"):
                raise RegistrationError("approval_not_current")
            if readback(cursor) is not None:
                return {"status": "exact_replay", "mission_id": MISSION_ID, "writes": 0}
            cursor.execute("insert into public.charlie_missions (" + ",".join(columns) +
                           ") values (" + ",".join("%(" + key + ")s" +
                           ("::jsonb" if key == "metadata_json" else "") for key in columns) + ")", params)
            for event in plan["events"]:
                cursor.execute("""insert into public.charlie_mission_events
                    (event_id,mission_id,event_type,notes,recorded_by,metadata_json,created_at)
                    values (%s,%s,%s,%s,%s,%s::jsonb,%s)""", (
                    event["event_id"], MISSION_ID, event["event_type"], event["summary"],
                    principal, json.dumps(event, sort_keys=True), event["recorded_at"]))
            if readback(cursor) is None:
                raise RegistrationError("registration_readback_missing")
    return {"status": "registered_paused", "mission_id": MISSION_ID,
            "manifest_sha256": expected_manifest_sha256, "writes": 3,
            "admission_issued": False, "runnable": False}
