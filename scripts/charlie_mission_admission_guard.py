#!/usr/bin/env python3
"""Shared fail-closed Mission Admission Guard for Cursor hooks and CI."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import shlex
import subprocess
import sys
from urllib import request as url_request
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.mission_admission import (  # noqa: E402
    MissionAdmissionError,
    canonical_candidate_diff,
    collision_snapshot_digest,
    sign_mission_admission_receipt,
    validate_mission_admission_receipt,
)
from modules.charlie.mission_admission import (  # noqa: E402
    RECEIPT_CLOCK_SKEW_SECONDS,
    _TOP_LEVEL_FIELDS,
    _parse_timestamp,
    _validate_body,
    _validate_lifetime,
)
from modules.charlie.validation_receipt import canonical_json  # noqa: E402
from modules.charlie.mission_store import (  # noqa: E402
    append_mission_admission_event,
    read_current_mission_admission_authority,
)


READ_ONLY_TOOLS = {
    "read",
    "readfile",
    "grep",
    "rg",
    "glob",
    "search",
    "websearch",
    "webfetch",
    "todos",
    "todowrite",
}
MUTATING_TOOL_EFFECTS = {
    "write": "repository_file_write",
    "delete": "repository_file_delete",
    "applypatch": "repository_file_write",
    "editnotebook": "repository_file_write",
}
READ_ONLY_COMMANDS = {
    "pwd",
    "ls",
    "rg",
    "wc",
    "sha256sum",
    "stat",
    "file",
    "which",
    "type",
}
READ_ONLY_GIT_SUBCOMMANDS = {
    "status",
    "diff",
    "show",
    "log",
    "rev-parse",
    "merge-base",
    "name-rev",
    "branch",
    "ls-files",
    "hash-object",
    "cat-file",
    "remote",
    "config",
}
DELEGATING_TOOLS = {"task", "subagent", "agent", "runagent"}
WINDOWS_INTERPRETERS = {
    "cmd", "powershell", "pwsh", "wscript", "cscript", "mshta",
}
INTERPRETERS = {
    "python", "python3", "py", "node", "ruby", "perl", "php",
    "bash", "sh", "zsh", "fish",
} | WINDOWS_INTERPRETERS

EXTERNAL_ADMISSION_PUBLIC_KEY_B64 = "ZAY5VaAnbWY2hrgxXivez5eLaNX4RjiRxjqYmPkoG9o="
EXTERNAL_CANONICAL_BINDING_ENV = "CHARLIE_ADMISSION_CANONICAL_BINDING_B64"
EXTERNAL_COLLISION_MAX_AGE_SECONDS = 900

BOOTSTRAP_BASE_SHA = "087f315b15acd1e683eb4f9b3d0f7c57ceb5e65f"
BOOTSTRAP_MISSION_ID = "CMQ-20260813-05"
BOOTSTRAP_ROOT_MISSION_ID = "CMQ-20260813-05"
BOOTSTRAP_GENERATION = "mission-admission-guard-bootstrap-20260826"
BOOTSTRAP_OWNER_INSTRUCTION_SHA256 = "b9d959ee6f8ef1ff6f20e5d7aca6344b17106e9cb6e0723f95096590063a5ef5"
BOOTSTRAP_PACKET_SHA256 = "e1af16aca874ac24af53371a7bf7384c850d788c986f9c6bcbca45800cc21014"
BOOTSTRAP_ALLOWED_FILES = frozenset({
    ".cursor/hooks.json",
    ".github/workflows/charlie-core-tests.yml",
    "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
    "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
    "docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md",
    "docs/09-vault-brain/CHANGELOG.md",
    "modules/charlie/mission_admission.py",
    "modules/charlie/mission_store.py",
    "scripts/charlie_mission_admission_guard.py",
    "tests/fixtures/mission_admission/pr1306_scope_drift.json",
    "tests/test_charlie_mission_admission.py",
})
BOOTSTRAP_FORBIDDEN_EFFECTS = frozenset({
    "branch_protection_change",
    "customer_send",
    "deployment",
    "farm_write",
    "hardware_action",
    "merge",
    "payment",
    "production_mutation",
    "public_send",
    "secret_write",
})
BOOTSTRAP_REQUIRED_TESTS = frozenset({
    "python -m unittest tests.test_charlie_mission_admission -q",
    "python -m unittest tests.test_charlie_mission_store tests.test_charlie_validation_receipt tests.test_charlie_vault_retrieval tests.test_vault_alignment -q",
    "python -m unittest tests.test_charlie_mission_admission.MissionAdmissionPostgresTests -q",
    "python modules/charlie/vault_alignment.py",
    "git diff --check",
})
STAGE2_BASE_SHA = "7c603cfff58c984409e6b40100009166cc9c8062"
STAGE2_MISSION_ID = "CMQ-20260813-05-STAGE2-ADMISSION"
STAGE2_ROOT_MISSION_ID = "CMQ-20260813-05"
STAGE2_GENERATION = "7379c0b621b7e53aa03aa03e"
STAGE2_OWNER_INSTRUCTION_SHA256 = "4c8824fc68ed15522c6ca85b6bd4b8d85e8f31a76e1fe7f52d1f68d7042014e0"
STAGE2_PACKET_SHA256 = "7a5ae24b827e83d633317fa48bb1fd97b0e56b71910e27b68732f2a681c0d1c8"
STAGE2_ALLOWED_FILES = frozenset({
    ".github/workflows/charlie-core-tests.yml",
    "docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md",
    "docs/09-vault-brain/CHANGELOG.md",
    "modules/charlie/execution_bridge.py",
    "modules/charlie/mission_admission_delivery.py",
    "scripts/charlie_mission_admission_guard.py",
    "scripts/charlie_codex_execution_bridge.py",
    "scripts/charlie_mission_pickup.py",
    "tests/test_charlie_mission_admission_delivery.py",
    "tests/test_charlie_mission_admission.py",
})
STAGE2_REQUIRED_TESTS = frozenset({
    "python -m unittest tests.test_charlie_mission_admission_delivery -q",
    "python -m unittest tests.test_charlie_mission_admission -q",
    "python -m unittest tests.test_charlie_execution_bridge -q",
    "python -m modules.charlie.vault_alignment",
    "git diff --check",
})
BOOTSTRAP_GOVERNANCE_PATHS = tuple(sorted({
    "docs/01-architecture/AGENTIC_FARM_RUNTIME_PROGRAMME.md",
    "docs/06-operations/CONTROL_TOWER_FEEDBACK_HANDOVER_TEMPLATE.md",
    "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md",
    "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
    "docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md",
    "docs/09-vault-brain/00-governance/DOCUMENT_LIFECYCLE_AND_LEGACY_RETIREMENT_STANDARD.md",
    "docs/09-vault-brain/00-governance/SOURCE_OF_TRUTH_RULES.md",
    "docs/09-vault-brain/01-identity/CHARLIE_CORE.md",
    "docs/09-vault-brain/02-agents/AGENT_REGISTRY.md",
    "docs/09-vault-brain/02-agents/owner-command/CHARLIE.md",
    "docs/09-vault-brain/04-workflows/CHARLIE_MISSION_WORKFLOW.md",
    "docs/09-vault-brain/07-standards/DEPLOYMENT_STANDARD.md",
    "docs/09-vault-brain/07-standards/EVIDENCE_AND_REVIEW_STANDARD.md",
    "docs/09-vault-brain/07-standards/TESTING_STANDARD.md",
    "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md",
    "docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md",
}))


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    hook_parser = subparsers.add_parser("hook")
    hook_parser.add_argument("--audit", action="store_true")
    ci_parser = subparsers.add_parser("ci")
    ci_parser.add_argument("--base", required=True)
    ci_parser.add_argument("--head", required=True)
    external_parser = subparsers.add_parser("ci-external")
    external_parser.add_argument("--base", required=True)
    external_parser.add_argument("--head", required=True)
    external_parser.add_argument("--receipt", required=True)
    trusted_parser = subparsers.add_parser("trusted-check")
    trusted_parser.add_argument("--event", required=True)
    issue_parser = subparsers.add_parser("issue-bootstrap")
    issue_parser.add_argument("--base", required=True)
    issue_parser.add_argument("--head", required=True)
    stage2_parser = subparsers.add_parser("issue-stage2")
    stage2_parser.add_argument("--base", required=True)
    stage2_parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    if args.mode == "hook":
        return hook_main(audit=args.audit)
    if args.mode in {"issue-bootstrap", "issue-stage2"}:
        return issue_bootstrap_main(args)
    if args.mode == "ci-external":
        return ci_external_main(args)
    if args.mode == "trusted-check":
        return trusted_check_main(args)
    return ci_main(args)


def hook_main(
    *,
    audit=False,
    stdin=None,
    environ=None,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    environ = os.environ if environ is None else environ
    try:
        packet = json.load(stdin or sys.stdin)
        if not isinstance(packet, dict):
            raise MissionAdmissionError("hook_input_invalid")
        if environ.get("CHARLIE_MISSION_ADMISSION_GUARD_URL"):
            _emit(_remote_authorization(packet, environ))
            return 0
        event = str(packet.get("hook_event_name") or "")
        if audit or event == "afterFileEdit":
            _audit_after_file_edit(
                packet,
                environ=environ,
                authority_reader=authority_reader,
                repo_root=repo_root,
                os_name=os_name,
            )
            _emit({})
            return 0
        if event == "beforeShellExecution":
            command = str(packet.get("command") or "")
            if _references_trusted_authority(command, environ):
                raise MissionAdmissionError("trusted_admission_read_denied")
            if _is_read_only_shell(command, os_name=os_name):
                return _allow("read_only_shell")
            raise MissionAdmissionError("stage1_shell_mutation_denied")
        if event == "preToolUse":
            tool_name = str(packet.get("tool_name") or "").strip()
            normalized = tool_name.lower()
            if normalized in READ_ONLY_TOOLS:
                if _references_trusted_authority(packet, environ):
                    raise MissionAdmissionError("trusted_admission_read_denied")
                return _allow("read_only_tool")
            if normalized == "shell":
                command = str((packet.get("tool_input") or {}).get("command") or "")
                if _references_trusted_authority(command, environ):
                    raise MissionAdmissionError("trusted_admission_read_denied")
                if _is_read_only_shell(command, os_name=os_name):
                    return _allow("read_only_shell")
                raise MissionAdmissionError("stage1_shell_mutation_denied")
            if normalized in DELEGATING_TOOLS:
                raise MissionAdmissionError("stage1_delegation_denied")
            if normalized.startswith("mcp:"):
                raise MissionAdmissionError("stage1_mcp_execution_denied")
            effect = MUTATING_TOOL_EFFECTS.get(normalized)
            if effect:
                _require_admission(
                    packet,
                    effect,
                    environ=environ,
                    authority_reader=authority_reader,
                    repo_root=repo_root,
                    os_name=os_name,
                )
                return _allow("mission_admission_verified")
            raise MissionAdmissionError("unknown_tool_denied")
        raise MissionAdmissionError("unsupported_hook_event_denied")
    except (OSError, ValueError, json.JSONDecodeError, MissionAdmissionError) as exc:
        return _deny(_reason(exc))


def ci_main(
    args,
    *,
    environ=None,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    try:
        base = _commit(args.base)
        head = _commit(args.head)
        changed_files = _changed_files(base, head)
        patch = _git_bytes(
            "diff", "--no-ext-diff", "--no-textconv", "--binary",
            "--full-index", base, head, "--",
        )
        diff_sha256 = canonical_candidate_diff(changed_files, patch)
        receipt, identity, _authority = _validated_trusted_identity(
            authority_reader=authority_reader,
            repo_root=repo_root,
            os_name=os_name,
            expected_base_sha=base,
            expected_head_sha=head,
            expected_changed_files=changed_files,
        )
        _verify_governance_reads(receipt, head)
        if receipt["candidate"]["diff_sha256"] != diff_sha256:
            raise MissionAdmissionError("admission_candidate_changed")
        if identity["generation"] == BOOTSTRAP_GENERATION:
            contract_base = BOOTSTRAP_BASE_SHA
            contract_files = BOOTSTRAP_ALLOWED_FILES
            contract_tests = BOOTSTRAP_REQUIRED_TESTS
        elif identity["generation"] == STAGE2_GENERATION:
            contract_base = STAGE2_BASE_SHA
            contract_files = STAGE2_ALLOWED_FILES
            contract_tests = STAGE2_REQUIRED_TESTS
        else:
            raise MissionAdmissionError("candidate_admission_contract_unknown")
        if (
            base != contract_base
            or set(changed_files) != contract_files
            or set(identity["allowed_files"]) != contract_files
            or not BOOTSTRAP_FORBIDDEN_EFFECTS.issubset(
                set(identity["forbidden_effects"])
            )
            or not contract_tests.issubset(
                set(receipt["required_tests"])
            )
        ):
            raise MissionAdmissionError("bootstrap_exact_contract_changed")
        _validate_paths_and_effects(
            changed_files,
            identity["allowed_files"],
            identity["forbidden_files"],
            "repository_candidate_validation",
            identity["allowed_effects"],
            identity["forbidden_effects"],
        )
        result = {
            "success": True,
            "status": "mission_admission_verified",
            "receipt_id": identity["receipt_id"],
            "generation": identity["generation"],
            "base_sha": base,
            "head_sha": head,
            "changed_files": changed_files,
            "diff_sha256": diff_sha256,
        }
        print(json.dumps(result, sort_keys=True))
        return 0
    except (OSError, ValueError, MissionAdmissionError, subprocess.SubprocessError) as exc:
        print(json.dumps({
            "success": False,
            "status": "READMISSION_REQUIRED",
            "reason_code": _reason(exc),
        }, sort_keys=True))
        return 2


def ci_external_main(args, *, repo_root=REPO_ROOT, os_name=None):
    """Verify an externally issued exact-candidate receipt without DB access."""
    try:
        base = _commit(args.base)
        head = _commit(args.head)
        changed_files = _changed_files(base, head)
        patch = _git_bytes("diff", "--binary", "--full-index", base, head, "--")
        diff_sha256 = canonical_candidate_diff(changed_files, patch)

        receipt_path = Path(args.receipt)
        if receipt_path.is_symlink() or not receipt_path.is_file():
            raise MissionAdmissionError("external_admission_receipt_unavailable")
        envelope = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt, identity = _validate_external_receipt_envelope(
            envelope,
            expected_repository=_repository_identity(),
            expected_base_sha=base,
            expected_head_sha=head,
            expected_changed_files=changed_files,
        )
        _verify_governance_reads(receipt, head)
        if receipt["candidate"]["diff_sha256"] != diff_sha256:
            raise MissionAdmissionError("admission_candidate_changed")
        if receipt["repository"]["base_sha"] != receipt["candidate"]["base_sha"]:
            raise MissionAdmissionError("admission_base_changed")
        if not receipt.get("required_tests"):
            raise MissionAdmissionError("admission_required_tests_invalid")
        if receipt.get("operational_acceptance", {}).get("business_outcome_authorized") is not False:
            raise MissionAdmissionError("admission_business_outcome_authority_invalid")
        _validate_paths_and_effects(
            changed_files,
            identity["allowed_files"],
            identity["forbidden_files"],
            "repository_candidate_validation",
            identity["allowed_effects"],
            identity["forbidden_effects"],
        )
        print(json.dumps({
            "success": True,
            "status": "mission_admission_verified",
            "receipt_id": identity["receipt_id"],
            "generation": identity["generation"],
            "base_sha": base,
            "head_sha": head,
            "changed_files": changed_files,
            "diff_sha256": diff_sha256,
        }, sort_keys=True))
        return 0
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        MissionAdmissionError,
        subprocess.SubprocessError,
    ) as exc:
        print(json.dumps({
            "success": False,
            "status": "READMISSION_REQUIRED",
            "reason_code": _reason(exc),
        }, sort_keys=True))
        return 2


def _validate_external_receipt_envelope(
    envelope,
    *,
    expected_repository,
    expected_base_sha,
    expected_head_sha,
    expected_changed_files,
    expected_canonical_binding=None,
    now=None,
):
    if not isinstance(envelope, dict) or set(envelope) != {
        "version", "receipt", "signature_ed25519"
    } or envelope.get("version") != "mission_admission_ci_envelope_v1":
        raise MissionAdmissionError("external_admission_envelope_invalid")
    receipt = envelope.get("receipt")
    try:
        signature = base64.b64decode(envelope["signature_ed25519"], validate=True)
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(EXTERNAL_ADMISSION_PUBLIC_KEY_B64, validate=True)
        )
        public_key.verify(signature, canonical_json(receipt))
    except (KeyError, TypeError, ValueError, InvalidSignature) as exc:
        raise MissionAdmissionError("external_admission_signature_invalid") from exc
    if not isinstance(receipt, dict) or set(receipt) != _TOP_LEVEL_FIELDS:
        raise MissionAdmissionError("admission_receipt_schema_invalid")
    body = {
        key: value for key, value in receipt.items()
        if key not in {"receipt_id", "content_sha256", "signature_hmac_sha256"}
    }
    _validate_body(body)
    content_sha256 = hashlib.sha256(canonical_json(body)).hexdigest()
    if (
        receipt.get("content_sha256") != content_sha256
        or receipt.get("receipt_id") != f"MAR-{content_sha256.upper()}"
        or not __import__("re").fullmatch(
            r"[0-9a-f]{64}", str(receipt.get("signature_hmac_sha256") or "")
        )
    ):
        raise MissionAdmissionError("admission_content_digest_invalid")
    issued = _parse_timestamp(receipt["issued_at"])
    expiry = _parse_timestamp(receipt["expires_at"])
    _validate_lifetime(issued, expiry)
    clock = _parse_timestamp(now) if now else __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    )
    if issued > clock + __import__("datetime").timedelta(
        seconds=RECEIPT_CLOCK_SKEW_SECONDS
    ):
        raise MissionAdmissionError("admission_not_yet_valid")
    if clock >= expiry:
        raise MissionAdmissionError("admission_expired")
    mission = receipt["mission"]
    repository = receipt["repository"]
    candidate = receipt["candidate"]
    changed_files = sorted(expected_changed_files)
    if expected_canonical_binding is not None:
        expected = {
            "mission_id": mission["mission_id"],
            "root_mission_id": mission["root_mission_id"],
            "generation": mission["generation"],
            "authority_key_sha256": receipt["authority_key_sha256"],
            "latest_correction_digest": receipt["owner_instruction_chain"][
                "latest_correction_digest"
            ],
            "collision_snapshot_sha256": receipt["collision_snapshot"][
                "snapshot_sha256"
            ],
        }
        if expected_canonical_binding != expected:
            raise MissionAdmissionError("canonical_admission_authority_changed")
        captured = _parse_timestamp(receipt["collision_snapshot"]["captured_at"])
        if captured > issued + __import__("datetime").timedelta(
            seconds=RECEIPT_CLOCK_SKEW_SECONDS
        ) or issued - captured > __import__("datetime").timedelta(
            seconds=EXTERNAL_COLLISION_MAX_AGE_SECONDS
        ):
            raise MissionAdmissionError("canonical_collision_snapshot_stale")
    if repository["repository"] != expected_repository:
        raise MissionAdmissionError("admission_repository_changed")
    if repository["base_sha"] != expected_base_sha:
        raise MissionAdmissionError("admission_base_changed")
    if candidate["head_sha"] != expected_head_sha:
        raise MissionAdmissionError("admission_candidate_changed")
    if candidate["changed_files"] != changed_files:
        raise MissionAdmissionError("admission_candidate_changed")
    return receipt, {
        "receipt_id": receipt["receipt_id"],
        "content_sha256": content_sha256,
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


def trusted_check_main(args, *, environ=None):
    """Publish the exact check using only protected-base code and an App token."""
    environ = os.environ if environ is None else environ
    check_id = None
    head = ""
    token = str(environ.get("CHARLIE_ADMISSION_APP_TOKEN") or "")
    try:
        event_path = Path(args.event)
        if event_path.is_symlink() or not event_path.is_file() or not token:
            raise MissionAdmissionError("trusted_check_runtime_unavailable")
        event = json.loads(event_path.read_text(encoding="utf-8"))
        try:
            canonical_binding = json.loads(base64.b64decode(
                str(environ.get(EXTERNAL_CANONICAL_BINDING_ENV) or ""),
                validate=True,
            ))
        except Exception as exc:
            raise MissionAdmissionError(
                "canonical_admission_binding_unavailable"
            ) from exc
        if not isinstance(canonical_binding, dict) or set(canonical_binding) != {
            "mission_id", "root_mission_id", "generation",
            "authority_key_sha256", "latest_correction_digest",
            "collision_snapshot_sha256",
        }:
            raise MissionAdmissionError("canonical_admission_binding_invalid")
        pull = event.get("pull_request") if isinstance(event, dict) else {}
        repository = event.get("repository") if isinstance(event, dict) else {}
        base_row = pull.get("base") if isinstance(pull, dict) else {}
        head_row = pull.get("head") if isinstance(pull, dict) else {}
        number = event.get("number")
        base = str((base_row or {}).get("sha") or "")
        head = str((head_row or {}).get("sha") or "")
        if (
            repository.get("full_name") != "Crewless9086/amadeus-pig-tracking-system"
            or (base_row or {}).get("ref") != "main"
            or not isinstance(number, int)
            or number <= 0
            or not __import__("re").fullmatch(r"[0-9a-f]{40}", base)
            or not __import__("re").fullmatch(r"[0-9a-f]{40}", head)
        ):
            raise MissionAdmissionError("trusted_check_event_invalid")
        pending = _app_check_request(
            "POST", token, {
                "name": "mission-admission",
                "head_sha": head,
                "status": "in_progress",
                "output": {
                    "title": "Mission Admission verification running",
                    "summary": f"Verifying exact candidate {head}.",
                },
            },
        )
        check_id = pending.get("id")
        if not isinstance(check_id, int):
            raise MissionAdmissionError("trusted_check_publish_failed")
        subprocess.run(
            [
                "git", "-c", "core.hooksPath=/dev/null",
                "-c", "protocol.file.allow=never", "fetch", "--no-tags",
                "--no-recurse-submodules", "origin", head,
            ],
            cwd=REPO_ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        base = _commit(base)
        head = _commit(head)
        changed_files = _changed_files(base, head)
        patch = _git_bytes(
            "diff", "--no-ext-diff", "--no-textconv", "--binary",
            "--full-index", base, head, "--",
        )
        diff_sha256 = canonical_candidate_diff(changed_files, patch)
        matches = __import__("re").findall(
            r"(?m)^Mission-Admission-Receipt-B64: ([A-Za-z0-9+/]+={0,2})\r?$",
            str(pull.get("body") or ""),
        )
        if len(matches) != 1:
            raise MissionAdmissionError("exactly_one_external_admission_receipt_required")
        try:
            envelope = json.loads(base64.b64decode(matches[0], validate=True))
        except Exception as exc:
            raise MissionAdmissionError("external_admission_receipt_invalid") from exc
        receipt, identity = _validate_external_receipt_envelope(
            envelope,
            expected_repository=repository["full_name"],
            expected_base_sha=base,
            expected_head_sha=head,
            expected_changed_files=changed_files,
            expected_canonical_binding=canonical_binding,
        )
        _verify_governance_reads(receipt, head)
        if receipt["candidate"]["diff_sha256"] != diff_sha256:
            raise MissionAdmissionError("admission_candidate_changed")
        _validate_paths_and_effects(
            changed_files,
            identity["allowed_files"],
            identity["forbidden_files"],
            "repository_candidate_validation",
            identity["allowed_effects"],
            identity["forbidden_effects"],
        )
        _app_check_request("PATCH", token, {
            "status": "completed",
            "conclusion": "success",
            "output": {
                "title": "Mission Admission verified",
                "summary": (
                    f"Receipt {identity['receipt_id']} verified for exact head {head}."
                ),
            },
        }, check_id=check_id)
        print(json.dumps({
            "success": True, "receipt_id": identity["receipt_id"], "head_sha": head
        }, sort_keys=True))
        return 0
    except Exception as exc:
        reason = _reason(exc)
        if check_id is not None:
            try:
                _app_check_request("PATCH", token, {
                    "status": "completed",
                    "conclusion": "failure",
                    "output": {
                        "title": "Mission Admission rejected",
                        "summary": f"Exact head {head}: {reason}",
                    },
                }, check_id=check_id)
            except Exception:
                pass
        print(json.dumps({
            "success": False, "status": "READMISSION_REQUIRED", "reason_code": reason
        }, sort_keys=True))
        return 2


def _app_check_request(method, token, payload, *, check_id=None):
    suffix = f"/{check_id}" if check_id is not None else ""
    request = url_request.Request(
        "https://api.github.com/repos/Crewless9086/amadeus-pig-tracking-system/check-runs" + suffix,
        data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "CHARLIE-Admission-Guard",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method=method,
    )
    with url_request.urlopen(request, timeout=15) as response:
        return json.loads(response.read(131072))


def issue_bootstrap_main(
    args,
    *,
    environ=None,
    authority_reader=None,
    admission_writer=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    """Trusted CI issuer for the one immutable bootstrap candidate."""
    environ = os.environ if environ is None else environ
    try:
        stage2 = getattr(args, "mode", "") == "issue-stage2"
        contract = {
            "base_sha": STAGE2_BASE_SHA if stage2 else BOOTSTRAP_BASE_SHA,
            "mission_id": STAGE2_MISSION_ID if stage2 else BOOTSTRAP_MISSION_ID,
            "root_mission_id": STAGE2_ROOT_MISSION_ID if stage2 else BOOTSTRAP_ROOT_MISSION_ID,
            "generation": STAGE2_GENERATION if stage2 else BOOTSTRAP_GENERATION,
            "owner_instruction_sha256": STAGE2_OWNER_INSTRUCTION_SHA256 if stage2 else BOOTSTRAP_OWNER_INSTRUCTION_SHA256,
            "packet_sha256": STAGE2_PACKET_SHA256 if stage2 else BOOTSTRAP_PACKET_SHA256,
            "allowed_files": STAGE2_ALLOWED_FILES if stage2 else BOOTSTRAP_ALLOWED_FILES,
            "required_tests": STAGE2_REQUIRED_TESTS if stage2 else BOOTSTRAP_REQUIRED_TESTS,
            "branch": "cursor/mission-admission-stage2-20260827" if stage2 else "cursor/mission-admission-guard-80dd",
        }
        if str(environ.get("CI") or "").lower() != "true":
            raise MissionAdmissionError("bootstrap_issuer_ci_only")
        base = _commit(args.base)
        head = _commit(args.head)
        if stage2 and str(environ.get("CHARLIE_STAGE2_ADMITTED_HEAD") or "") != head:
            raise MissionAdmissionError("stage2_external_head_admission_required")
        changed_files = _changed_files(base, head)
        if (
            base != contract["base_sha"]
            or set(changed_files) != contract["allowed_files"]
        ):
            raise MissionAdmissionError("bootstrap_exact_contract_changed")
        authority_reader = (
            authority_reader or read_current_mission_admission_authority
        )
        authority, status = authority_reader(contract["mission_id"])
        if status >= 400 or not authority.get("success"):
            raise MissionAdmissionError("canonical_admission_authority_unavailable")
        if (
            authority.get("mission_id") != contract["mission_id"]
            or authority.get("root_mission_id") != contract["root_mission_id"]
            or not __import__("re").fullmatch(
                r"[0-9a-f]{64}",
                str(authority.get("latest_correction_digest") or ""),
            )
        ):
            raise MissionAdmissionError("canonical_owner_correction_unavailable")
        state_root = _trusted_state_root(repo_root, os_name=os_name)
        key_path = state_root / "validation-receipt.key"
        if key_path.is_symlink():
            raise MissionAdmissionError("validation_authority_symlink_denied")
        key = key_path.read_bytes()
        if (os_name or os.name) != "nt" and key_path.stat().st_mode & 0o077:
            raise MissionAdmissionError("validation_authority_permissions_invalid")
        patch = _git_bytes(
            "diff", "--binary", "--full-index", base, head, "--"
        )
        diff_sha256 = canonical_candidate_diff(changed_files, patch)
        governance_reads = _governance_read_identities(head)
        collision_time = str(authority.get("collision_observed_at") or "")
        active_claims = list(authority.get("active_claims") or [])
        if (
            collision_snapshot_digest(collision_time, active_claims)
            != authority.get("collision_snapshot_sha256")
        ):
            raise MissionAdmissionError("canonical_collision_snapshot_invalid")
        payload = {
            "mission": {
                "mission_id": contract["mission_id"],
                "root_mission_id": contract["root_mission_id"],
                "generation": contract["generation"],
            },
            "owner_instruction_chain": {
                "instruction_digests": [
                    contract["owner_instruction_sha256"],
                    authority["latest_correction_digest"],
                ],
                "latest_correction_digest": authority[
                    "latest_correction_digest"
                ],
                "admission_packet_sha256": contract["packet_sha256"],
            },
            "repository": {
                "repository": _repository_identity(),
                "base_ref": "main",
                "base_sha": base,
            },
            "governance_reads": governance_reads,
            "existing_system_trace": {
                "smallest_genuine_gap": (
                    "Cursor mutation lacked a trusted, mission-bound, "
                    "content-addressed admission decision."
                ),
                "reused_components": [
                    "charlie_missions",
                    "charlie_mission_events",
                    "operational_events",
                    "validation_receipt authority",
                    "Vault retrieval and alignment",
                ],
                "implementation_sources": sorted([
                    "modules/charlie/mission_store.py",
                    "modules/charlie/runtime_staging.py",
                    "modules/charlie/validation_receipt.py",
                ]),
            },
            "scope": {
                "allowed_files": sorted(contract["allowed_files"]),
                "forbidden_files": sorted({
                    ".cursor/environment.json",
                    "AGENTS.md",
                    "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md",
                    "docs/09-vault-brain/00-governance/CONTROL_TOWER_ASSESSMENT_AND_DISPATCH_PROTOCOL.md",
                    "modules/charlie/runner_control.py",
                    "package-lock.json",
                    "tests/test_charlie_runner_control.py",
                }),
                "allowed_effects": [
                    "repository_candidate_validation",
                    "repository_file_delete",
                    "repository_file_write",
                ],
                "forbidden_effects": sorted(BOOTSTRAP_FORBIDDEN_EFFECTS),
            },
            "collision_snapshot": {
                "captured_at": collision_time,
                "active_claims": active_claims,
                "snapshot_sha256": authority[
                    "collision_snapshot_sha256"
                ],
            },
            "required_tests": sorted(contract["required_tests"]),
            "operational_acceptance": {
                "requirements": [
                    "Hosted exact-head admission and CHARLIE checks pass.",
                    "A fresh independent reviewer accepts the corrected source.",
                    "Stage 2 separately integrates a deployed receipt supplier.",
                ],
                "business_outcome_authorized": False,
            },
            "candidate": {
                "candidate_id": (
                    f"{contract['mission_id']}:{contract['generation']}:{head}"
                ),
                "branch": contract["branch"],
                "base_sha": base,
                "head_sha": head,
                "diff_sha256": diff_sha256,
                "changed_files": changed_files,
            },
        }
        receipt = sign_mission_admission_receipt(payload, key)
        receipt_dir = state_root / "mission-admission-receipts"
        receipt_dir.mkdir(parents=True, exist_ok=True)
        receipt_path = receipt_dir / f"{receipt['receipt_id']}.json"
        encoded = json.dumps(
            receipt, sort_keys=True, separators=(",", ":")
        ).encode("utf-8") + b"\n"
        if receipt_path.exists():
            if receipt_path.read_bytes() != encoded:
                raise MissionAdmissionError("bootstrap_receipt_replay_conflict")
        else:
            descriptor = os.open(
                receipt_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600
            )
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
        admission = {
            "receipt_id": receipt["receipt_id"],
            "content_sha256": receipt["content_sha256"],
            "mission_id": contract["mission_id"],
            "root_mission_id": contract["root_mission_id"],
            "generation": contract["generation"],
            "base_sha": base,
            "head_sha": head,
            "authority_key_sha256": receipt["authority_key_sha256"],
            "latest_correction_digest": authority[
                "latest_correction_digest"
            ],
            "collision_snapshot_sha256": authority[
                "collision_snapshot_sha256"
            ],
        }
        writer = admission_writer or append_mission_admission_event
        written, write_status = writer(
            contract["mission_id"],
            admission,
            authenticated_principal="control_tower_isolated_validator_v2",
        )
        if write_status >= 400 or not written.get("success"):
            raise MissionAdmissionError(
                written.get("status") or "bootstrap_admission_write_failed"
            )
        print(json.dumps({
            "success": True,
            "status": "bootstrap_admission_issued",
            "receipt_id": receipt["receipt_id"],
            "head_sha": head,
            "diff_sha256": diff_sha256,
        }, sort_keys=True))
        return 0
    except (OSError, ValueError, MissionAdmissionError, subprocess.SubprocessError) as exc:
        print(json.dumps({
            "success": False,
            "status": "READMISSION_REQUIRED",
            "reason_code": _reason(exc),
        }, sort_keys=True))
        return 2


def _require_admission(
    packet,
    effect,
    *,
    environ=None,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    receipt, identity, _authority = _validated_trusted_identity(
        authority_reader=authority_reader,
        repo_root=repo_root,
        os_name=os_name,
        environ=environ,
    )
    _verify_governance_reads(receipt, identity["head_sha"])
    current_head = _commit("HEAD")
    if current_head not in {identity["base_sha"], identity["head_sha"]}:
        raise MissionAdmissionError("admission_candidate_changed")
    current_paths = _worktree_changed_files(identity["base_sha"])
    target_path = _tool_target_path(packet)
    if not target_path:
        raise MissionAdmissionError("mutation_target_path_required")
    current_paths = sorted(set(current_paths + [target_path]))
    _validate_paths_and_effects(
        current_paths,
        identity["allowed_files"],
        identity["forbidden_files"],
        effect,
        identity["allowed_effects"],
        identity["forbidden_effects"],
    )
    return identity


def _validated_trusted_identity(
    *,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
    expected_base_sha="",
    expected_head_sha="",
    expected_changed_files=None,
    environ=None,
):
    environ = os.environ if environ is None else environ
    delivered_root = str(environ.get("CHARLIE_MISSION_ADMISSION_STATE_ROOT") or "").strip()
    delivered_mission = str(environ.get("CHARLIE_MISSION_ADMISSION_MISSION_ID") or "").strip()
    if bool(delivered_root) != bool(delivered_mission):
        raise MissionAdmissionError("trusted_admission_delivery_incomplete")
    mission_id = delivered_mission or BOOTSTRAP_MISSION_ID
    authority_reader = authority_reader or read_current_mission_admission_authority
    authority_result, authority_status = authority_reader(mission_id)
    if authority_status >= 400 or not authority_result.get("success"):
        raise MissionAdmissionError("canonical_admission_authority_unavailable")
    authority = authority_result
    current = (
        authority.get("admission")
        if isinstance(authority.get("admission"), dict)
        else {}
    )
    if current.get("status") != "valid":
        raise MissionAdmissionError("canonical_admission_not_active")
    receipt, key, key_sha256 = _trusted_receipt(
        current,
        repo_root=repo_root,
        os_name=os_name,
        environ=environ,
    )
    identity = validate_mission_admission_receipt(
        receipt,
        key,
        expected_repository=_repository_identity(),
        expected_base_sha=expected_base_sha,
        expected_head_sha=expected_head_sha,
        expected_generation=str(current.get("generation") or ""),
        expected_mission_id=mission_id,
        expected_root_mission_id=str(authority.get("root_mission_id") or ""),
        expected_authority_key_sha256=key_sha256,
        expected_changed_files=expected_changed_files,
    )
    if (
        authority.get("mission_id") != mission_id
        or identity["root_mission_id"] != authority.get("root_mission_id")
        or identity["receipt_id"] != current.get("receipt_id")
        or identity["content_sha256"] != current.get("content_sha256")
        or receipt["owner_instruction_chain"]["latest_correction_digest"]
        != authority.get("latest_correction_digest")
        or receipt["collision_snapshot"]["snapshot_sha256"]
        != authority.get("collision_snapshot_sha256")
    ):
        raise MissionAdmissionError("canonical_admission_authority_changed")
    return receipt, identity, authority


def _trusted_receipt(current, *, repo_root=REPO_ROOT, os_name=None, environ=None):
    state_root = _trusted_state_root(repo_root, os_name=os_name, environ=environ)
    receipt_id = str(current.get("receipt_id") or "")
    if not __import__("re").fullmatch(r"MAR-[0-9A-F]{64}", receipt_id):
        raise MissionAdmissionError("canonical_admission_identity_invalid")
    receipt_file = state_root / "mission-admission-receipts" / f"{receipt_id}.json"
    key_file = state_root / "validation-receipt.key"
    if receipt_file.is_symlink() or key_file.is_symlink():
        raise MissionAdmissionError("validation_authority_symlink_denied")
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        key = key_file.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise MissionAdmissionError("trusted_validation_authority_unavailable") from exc
    key_sha256 = hashlib.sha256(key).hexdigest()
    if (
        current.get("authority_key_sha256") != key_sha256
        or receipt.get("receipt_id") != receipt_id
    ):
        raise MissionAdmissionError("validation_authority_identity_changed")
    if (os_name or os.name) != "nt" and key_file.stat().st_mode & 0o077:
        raise MissionAdmissionError("validation_authority_permissions_invalid")
    return receipt, key, key_sha256


def _trusted_state_root(repo_root=REPO_ROOT, *, os_name=None, environ=None):
    environ = os.environ if environ is None else environ
    delivered = str(environ.get("CHARLIE_MISSION_ADMISSION_STATE_ROOT") or "").strip()
    if delivered:
        candidate = Path(delivered)
        if not candidate.is_absolute() or candidate.is_symlink():
            raise MissionAdmissionError("trusted_state_root_invalid")
        return candidate.resolve()
    root = Path(repo_root).resolve()
    if root.parent.name == ".charlie_runner":
        return root.parent
    return root / ".charlie_runner"


def _references_trusted_authority(value, environ=None):
    """Deny model-visible reads of the externally staged signing authority."""

    environ = os.environ if environ is None else environ
    serialized = json.dumps(value, default=str).replace("\\", "/").lower()
    protected = {
        "validation-receipt.key",
        "mission-admission-receipts",
    }
    delivered = str(environ.get("CHARLIE_MISSION_ADMISSION_STATE_ROOT") or "").strip()
    if delivered:
        protected.add(str(Path(delivered).resolve()).replace("\\", "/").lower())
    return any(item and item in serialized for item in protected)


def _remote_authorization(packet, environ):
    endpoint = str(environ.get("CHARLIE_MISSION_ADMISSION_GUARD_URL") or "").strip()
    capability = str(environ.get("CHARLIE_MISSION_ADMISSION_CAPABILITY") or "").strip()
    if not endpoint.startswith("http://127.0.0.1:") or not capability:
        raise MissionAdmissionError("trusted_guard_endpoint_invalid")
    request = url_request.Request(
        endpoint,
        data=json.dumps(packet).encode("utf-8"),
        headers={
            "Authorization": f"Charlie {capability}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with url_request.urlopen(request, timeout=5) as response:
            result = json.loads(response.read(131072))
    except Exception as exc:
        raise MissionAdmissionError("trusted_guard_unavailable") from exc
    if not isinstance(result, dict) or result.get("permission") not in {"allow", "deny"}:
        raise MissionAdmissionError("trusted_guard_response_invalid")
    return result


def _verify_governance_reads(receipt, candidate_head):
    for expected in receipt["governance_reads"]:
        path = expected["path"]
        try:
            blob = _git_text("rev-parse", f"{candidate_head}:{path}")
            content = _git_bytes("show", f"{candidate_head}:{path}")
        except subprocess.SubprocessError as exc:
            raise MissionAdmissionError("admission_governance_changed") from exc
        actual = {
            "git_blob": blob,
            "filesystem_sha256": __import__("hashlib").sha256(content).hexdigest(),
            "byte_count": len(content),
            "physical_line_count": content.count(b"\n"),
        }
        if any(expected.get(key) != value for key, value in actual.items()):
            raise MissionAdmissionError("admission_governance_changed")


def _governance_read_identities(candidate_head):
    rows = []
    for path in BOOTSTRAP_GOVERNANCE_PATHS:
        content = _git_bytes("show", f"{candidate_head}:{path}")
        rows.append({
            "path": path,
            "git_blob": _git_text("rev-parse", f"{candidate_head}:{path}"),
            "filesystem_sha256": hashlib.sha256(content).hexdigest(),
            "byte_count": len(content),
            "physical_line_count": content.count(b"\n"),
            "complete_byte_read": True,
        })
    return rows


def _repository_identity():
    remote = _git_text("config", "--get", "remote.origin.url")
    remote = remote.removesuffix(".git").replace("\\", "/")
    if "github.com/" in remote:
        return remote.split("github.com/", 1)[1]
    if remote.startswith("git@github.com:"):
        return remote.split(":", 1)[1]
    raise MissionAdmissionError("admission_repository_identity_unavailable")


def _validate_paths_and_effects(
    paths, allowed_files, forbidden_files, effect, allowed_effects, forbidden_effects
):
    normalized = {_relative_path(path) for path in paths}
    if "" in normalized:
        raise MissionAdmissionError("admission_path_invalid")
    if not normalized.issubset(set(allowed_files)):
        raise MissionAdmissionError("admission_scope_drift")
    if normalized.intersection(forbidden_files):
        raise MissionAdmissionError("admission_forbidden_path")
    if effect in set(forbidden_effects):
        raise MissionAdmissionError("admission_forbidden_effect")
    if effect not in set(allowed_effects):
        raise MissionAdmissionError("admission_effect_not_allowed")


def _is_read_only_shell(command, *, os_name=None):
    command = str(command or "").strip()
    if not command or any(
        token in command
        for token in (
            "\n", "\r", ">", "<", "|", ";", "&&", "||", "`", "$(",
            "2>", "&>", "\x00",
        )
    ):
        return False
    try:
        words = shlex.split(command, posix=(os_name or os.name) != "nt")
    except ValueError:
        return False
    if not words:
        return False
    words = [word.strip("\"'") for word in words]
    if "=" in words[0] and not words[0].startswith(("./", "/", "\\")):
        return False
    executable = _executable_name(words[0])
    if executable in INTERPRETERS:
        return False
    if executable in READ_ONLY_COMMANDS:
        if executable == "rg" and any(
            item == "--pre" or item.startswith("--pre=")
            or item == "--pre-glob" or item.startswith("--pre-glob=")
            for item in words[1:]
        ):
            return False
        return True
    if executable == "git" and len(words) >= 2:
        subcommand = words[1].lower()
        args = words[2:]
        if subcommand not in READ_ONLY_GIT_SUBCOMMANDS:
            return False
        if any(
            item == "--output" or item.startswith("--output=")
            or item in {"--ext-diff", "--textconv", "--exec"}
            for item in args
        ):
            return False
        if subcommand == "branch":
            mutation_flags = {
                "-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move",
                "--copy", "--edit-description", "--set-upstream-to",
                "--unset-upstream",
            }
            if any(item in mutation_flags for item in args):
                return False
            return not any(
                not item.startswith("-")
                for item in args
            )
        if subcommand == "remote":
            return not args or args[0] in {"-v", "--verbose", "show", "get-url"}
        if subcommand == "hash-object":
            return "-w" not in args and "--write" not in args
        if subcommand == "config":
            return bool(args) and args[0] in {
                "--get", "--get-all", "--get-regexp", "--list",
                "--show-origin", "--show-scope",
            }
        if subcommand == "cat-file" and any(
            item == "--filters" or item.startswith("--filters=")
            for item in args
        ):
            return False
        return True
    return False


def _executable_name(value):
    name = str(value or "").replace("\\", "/").rsplit("/", 1)[-1].lower()
    return name[:-4] if name.endswith(".exe") else name


def _tool_target_path(packet):
    event = str(packet.get("hook_event_name") or "")
    if event == "afterFileEdit":
        return _relative_path(packet.get("file_path"))
    tool_input = packet.get("tool_input") if isinstance(packet.get("tool_input"), dict) else {}
    for key in ("path", "file_path", "target_file", "target_notebook"):
        if tool_input.get(key):
            return _relative_path(tool_input[key])
    if str(packet.get("tool_name") or "").strip().lower() == "applypatch":
        patch = next(
            (
                value
                for key, value in tool_input.items()
                if key in {"patch", "input", "content"}
                and isinstance(value, str)
            ),
            "",
        )
        targets = __import__("re").findall(
            r"^\*\*\* (?:Add|Update) File: (.+)$",
            patch,
            flags=__import__("re").MULTILINE,
        )
        normalized = sorted({_relative_path(path) for path in targets})
        if len(normalized) == 1 and normalized[0]:
            return normalized[0]
    return ""


def _audit_after_file_edit(
    packet,
    *,
    environ=None,
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    path = _tool_target_path(packet)
    if not path:
        raise MissionAdmissionError("after_file_edit_path_missing")
    _require_admission(
        {
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": path},
        },
        "repository_file_write",
        environ=environ,
        authority_reader=authority_reader,
        repo_root=repo_root,
        os_name=os_name,
    )


def _changed_files(base, head):
    output = _git_text(
        "diff", "--no-ext-diff", "--no-textconv", "--name-only",
        "--diff-filter=ACMRDTUXB", base, head, "--",
    )
    return sorted({line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()})


def _worktree_changed_files(base):
    tracked = {
        line.strip().replace("\\", "/")
        for line in _git_text("diff", "--name-only", base, "--").splitlines()
        if line.strip()
    }
    status = _git_bytes(
        "status", "--porcelain=v1", "--untracked-files=all"
    ).decode("utf-8", errors="strict")
    for line in status.splitlines():
        candidate = line[3:] if len(line) > 3 else ""
        if " -> " in candidate:
            candidate = candidate.split(" -> ", 1)[1]
        candidate = candidate.strip().strip('"').replace("\\", "/")
        if candidate:
            tracked.add(candidate)
    return sorted(tracked)


def _commit(value):
    commit = _git_text("rev-parse", f"{value}^{{commit}}")
    if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
        raise MissionAdmissionError("admission_commit_identity_invalid")
    return commit


def _relative_path(value):
    text = str(value or "").strip().replace("\\", "/")
    if not text:
        return ""
    path = Path(text)
    if path.is_absolute():
        try:
            text = str(path.resolve().relative_to(REPO_ROOT)).replace("\\", "/")
        except ValueError:
            return ""
    if text.startswith("../") or "/../" in text or text == "..":
        return ""
    return text


def _git_text(*args):
    return _git_bytes(*args).decode("utf-8", errors="strict").strip()


def _git_bytes(*args):
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout


def _allow(reason):
    _emit({"permission": "allow", "agent_message": reason})
    return 0


def _deny(reason):
    _emit({
        "permission": "deny",
        "user_message": "READMISSION_REQUIRED",
        "agent_message": f"READMISSION_REQUIRED: {reason}",
    })
    return 0


def _emit(value):
    print(json.dumps(value, sort_keys=True))


def _reason(exc):
    text = str(exc).strip()
    return text or exc.__class__.__name__


if __name__ == "__main__":
    raise SystemExit(main())
