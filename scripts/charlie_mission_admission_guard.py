#!/usr/bin/env python3
"""Shared fail-closed Mission Admission Guard for Cursor hooks and CI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

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
    issue_parser = subparsers.add_parser("issue-bootstrap")
    issue_parser.add_argument("--base", required=True)
    issue_parser.add_argument("--head", required=True)
    args = parser.parse_args(argv)
    if args.mode == "hook":
        return hook_main(audit=args.audit)
    if args.mode == "issue-bootstrap":
        return issue_bootstrap_main(args)
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
        event = str(packet.get("hook_event_name") or "")
        if audit or event == "afterFileEdit":
            _audit_after_file_edit(
                packet,
                authority_reader=authority_reader,
                repo_root=repo_root,
                os_name=os_name,
            )
            _emit({})
            return 0
        if event == "beforeShellExecution":
            command = str(packet.get("command") or "")
            if _is_read_only_shell(command, os_name=os_name):
                return _allow("read_only_shell")
            raise MissionAdmissionError("stage1_shell_mutation_denied")
        if event == "preToolUse":
            tool_name = str(packet.get("tool_name") or "").strip()
            normalized = tool_name.lower()
            if normalized in READ_ONLY_TOOLS:
                return _allow("read_only_tool")
            if normalized == "shell":
                command = str((packet.get("tool_input") or {}).get("command") or "")
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
        patch = _git_bytes("diff", "--binary", "--full-index", base, head, "--")
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
        if (
            base != BOOTSTRAP_BASE_SHA
            or identity["generation"] != BOOTSTRAP_GENERATION
            or set(changed_files) != BOOTSTRAP_ALLOWED_FILES
            or set(identity["allowed_files"]) != BOOTSTRAP_ALLOWED_FILES
            or not BOOTSTRAP_FORBIDDEN_EFFECTS.issubset(
                set(identity["forbidden_effects"])
            )
            or not BOOTSTRAP_REQUIRED_TESTS.issubset(
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
        if str(environ.get("CI") or "").lower() != "true":
            raise MissionAdmissionError("bootstrap_issuer_ci_only")
        base = _commit(args.base)
        head = _commit(args.head)
        changed_files = _changed_files(base, head)
        if (
            base != BOOTSTRAP_BASE_SHA
            or set(changed_files) != BOOTSTRAP_ALLOWED_FILES
        ):
            raise MissionAdmissionError("bootstrap_exact_contract_changed")
        authority_reader = (
            authority_reader or read_current_mission_admission_authority
        )
        authority, status = authority_reader(BOOTSTRAP_MISSION_ID)
        if status >= 400 or not authority.get("success"):
            raise MissionAdmissionError("canonical_admission_authority_unavailable")
        if (
            authority.get("mission_id") != BOOTSTRAP_MISSION_ID
            or authority.get("root_mission_id") != BOOTSTRAP_ROOT_MISSION_ID
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
                "mission_id": BOOTSTRAP_MISSION_ID,
                "root_mission_id": BOOTSTRAP_ROOT_MISSION_ID,
                "generation": BOOTSTRAP_GENERATION,
            },
            "owner_instruction_chain": {
                "instruction_digests": [
                    BOOTSTRAP_OWNER_INSTRUCTION_SHA256,
                    authority["latest_correction_digest"],
                ],
                "latest_correction_digest": authority[
                    "latest_correction_digest"
                ],
                "admission_packet_sha256": BOOTSTRAP_PACKET_SHA256,
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
                "allowed_files": sorted(BOOTSTRAP_ALLOWED_FILES),
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
            "required_tests": sorted(BOOTSTRAP_REQUIRED_TESTS),
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
                    f"{BOOTSTRAP_MISSION_ID}:{BOOTSTRAP_GENERATION}:{head}"
                ),
                "branch": "cursor/mission-admission-guard-80dd",
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
            "mission_id": BOOTSTRAP_MISSION_ID,
            "root_mission_id": BOOTSTRAP_ROOT_MISSION_ID,
            "generation": BOOTSTRAP_GENERATION,
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
            BOOTSTRAP_MISSION_ID,
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
    authority_reader=None,
    repo_root=REPO_ROOT,
    os_name=None,
):
    receipt, identity, _authority = _validated_trusted_identity(
        authority_reader=authority_reader,
        repo_root=repo_root,
        os_name=os_name,
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
):
    authority_reader = authority_reader or read_current_mission_admission_authority
    authority_result, authority_status = authority_reader(BOOTSTRAP_MISSION_ID)
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
    )
    identity = validate_mission_admission_receipt(
        receipt,
        key,
        expected_repository=_repository_identity(),
        expected_base_sha=expected_base_sha,
        expected_head_sha=expected_head_sha,
        expected_generation=str(current.get("generation") or ""),
        expected_mission_id=BOOTSTRAP_MISSION_ID,
        expected_root_mission_id=BOOTSTRAP_ROOT_MISSION_ID,
        expected_authority_key_sha256=key_sha256,
        expected_changed_files=expected_changed_files,
    )
    if (
        authority.get("mission_id") != BOOTSTRAP_MISSION_ID
        or authority.get("root_mission_id") != BOOTSTRAP_ROOT_MISSION_ID
        or identity["receipt_id"] != current.get("receipt_id")
        or identity["content_sha256"] != current.get("content_sha256")
        or receipt["owner_instruction_chain"]["latest_correction_digest"]
        != authority.get("latest_correction_digest")
        or receipt["collision_snapshot"]["snapshot_sha256"]
        != authority.get("collision_snapshot_sha256")
    ):
        raise MissionAdmissionError("canonical_admission_authority_changed")
    return receipt, identity, authority


def _trusted_receipt(current, *, repo_root=REPO_ROOT, os_name=None):
    state_root = _trusted_state_root(repo_root, os_name=os_name)
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


def _trusted_state_root(repo_root=REPO_ROOT, *, os_name=None):
    root = Path(repo_root).resolve()
    if root.parent.name == ".charlie_runner":
        return root.parent
    return root / ".charlie_runner"


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
        authority_reader=authority_reader,
        repo_root=repo_root,
        os_name=os_name,
    )


def _changed_files(base, head):
    output = _git_text("diff", "--name-only", "--diff-filter=ACMRDTUXB", base, head, "--")
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
