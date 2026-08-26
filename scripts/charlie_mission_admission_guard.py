#!/usr/bin/env python3
"""Shared fail-closed Mission Admission Guard for Cursor hooks and CI."""

from __future__ import annotations

import argparse
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
    validate_mission_admission_receipt,
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
}
SHELL_MUTATION_EFFECTS = {
    "add": "repository_index_write",
    "commit": "repository_commit",
    "push": "repository_push",
    "rm": "repository_file_delete",
    "mv": "repository_file_write",
    "checkout": "repository_checkout",
    "switch": "repository_checkout",
    "merge": "repository_merge",
    "rebase": "repository_rebase",
    "cherry-pick": "repository_cherry_pick",
}

BOOTSTRAP_BASE_SHA = "087f315b15acd1e683eb4f9b3d0f7c57ceb5e65f"
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


def main(argv=None):
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="mode", required=True)
    hook_parser = subparsers.add_parser("hook")
    hook_parser.add_argument("--audit", action="store_true")
    ci_parser = subparsers.add_parser("ci")
    ci_parser.add_argument("--base", required=True)
    ci_parser.add_argument("--head", required=True)
    ci_parser.add_argument("--bootstrap-generation", default="")
    ci_parser.add_argument("--owner-instruction-sha256", default="")
    ci_parser.add_argument("--admission-packet-sha256", default="")
    args = parser.parse_args(argv)
    if args.mode == "hook":
        return hook_main(audit=args.audit)
    return ci_main(args)


def hook_main(*, audit=False, stdin=None, environ=None):
    environ = os.environ if environ is None else environ
    try:
        packet = json.load(stdin or sys.stdin)
        if not isinstance(packet, dict):
            raise MissionAdmissionError("hook_input_invalid")
        event = str(packet.get("hook_event_name") or "")
        if audit or event == "afterFileEdit":
            _audit_after_file_edit(packet)
            _emit({})
            return 0
        if event == "beforeShellExecution":
            command = str(packet.get("command") or "")
            if _is_read_only_shell(command):
                return _allow("read_only_shell")
            effect = _shell_effect(command)
            _require_admission(packet, effect, environ=environ)
            return _allow("mission_admission_verified")
        if event == "preToolUse":
            tool_name = str(packet.get("tool_name") or "").strip()
            normalized = tool_name.lower()
            if normalized in READ_ONLY_TOOLS:
                return _allow("read_only_tool")
            if normalized == "shell":
                command = str((packet.get("tool_input") or {}).get("command") or "")
                if _is_read_only_shell(command):
                    return _allow("read_only_shell")
                _require_admission(packet, _shell_effect(command), environ=environ)
                return _allow("mission_admission_verified")
            effect = MUTATING_TOOL_EFFECTS.get(normalized)
            if effect:
                _require_admission(packet, effect, environ=environ)
                return _allow("mission_admission_verified")
            raise MissionAdmissionError("unknown_tool_denied")
        raise MissionAdmissionError("unsupported_hook_event_denied")
    except (OSError, ValueError, json.JSONDecodeError, MissionAdmissionError) as exc:
        return _deny(_reason(exc))


def ci_main(args, *, environ=None):
    environ = os.environ if environ is None else environ
    try:
        base = _commit(args.base)
        head = _commit(args.head)
        changed_files = _changed_files(base, head)
        patch = _git_bytes("diff", "--binary", "--full-index", base, head, "--")
        diff_sha256 = canonical_candidate_diff(changed_files, patch)
        if args.bootstrap_generation:
            _validate_bootstrap(args, base, changed_files)
            result = {
                "success": True,
                "status": "bootstrap_admission_verified",
                "generation": BOOTSTRAP_GENERATION,
                "base_sha": base,
                "head_sha": head,
                "changed_files": changed_files,
                "diff_sha256": diff_sha256,
            }
        else:
            receipt, key = _external_receipt(environ)
            identity = validate_mission_admission_receipt(
                receipt,
                key,
                expected_repository=_repository_identity(environ),
                expected_base_sha=base,
                expected_head_sha=head,
                expected_generation=_required_generation(environ),
                expected_changed_files=changed_files,
            )
            _verify_dynamic_bindings(receipt, environ)
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


def _require_admission(packet, effect, *, environ):
    receipt, key = _external_receipt(environ)
    identity = validate_mission_admission_receipt(
        receipt,
        key,
        expected_repository=_repository_identity(environ),
        expected_generation=_required_generation(environ),
    )
    _verify_dynamic_bindings(receipt, environ)
    _verify_governance_reads(receipt, identity["head_sha"])
    current_head = _commit("HEAD")
    if current_head not in {identity["base_sha"], identity["head_sha"]}:
        raise MissionAdmissionError("admission_candidate_changed")
    current_paths = _worktree_changed_files(identity["base_sha"])
    target_path = _tool_target_path(packet)
    if target_path:
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


def _external_receipt(environ):
    receipt_path = str(environ.get("CHARLIE_MISSION_ADMISSION_RECEIPT_PATH") or "").strip()
    key_path = str(environ.get("CHARLIE_VALIDATION_RECEIPT_KEY_PATH") or "").strip()
    if not receipt_path or not key_path:
        raise MissionAdmissionError("admission_external_binding_missing")
    receipt_file = Path(receipt_path).resolve()
    key_file = Path(key_path).resolve()
    try:
        receipt = json.loads(receipt_file.read_text(encoding="utf-8"))
        key = key_file.read_bytes()
    except (OSError, json.JSONDecodeError) as exc:
        raise MissionAdmissionError("admission_external_binding_unavailable") from exc
    return receipt, key


def _required_generation(environ):
    generation = str(environ.get("CHARLIE_MISSION_ADMISSION_GENERATION") or "").strip()
    if not generation:
        raise MissionAdmissionError("admission_generation_binding_missing")
    return generation


def _verify_dynamic_bindings(receipt, environ):
    latest_correction = str(
        environ.get("CHARLIE_MISSION_ADMISSION_OWNER_CORRECTION_SHA256") or ""
    ).strip()
    collision_digest = str(
        environ.get("CHARLIE_MISSION_ADMISSION_COLLISION_SHA256") or ""
    ).strip()
    if not latest_correction or not collision_digest:
        raise MissionAdmissionError("admission_dynamic_binding_missing")
    if (
        latest_correction
        != receipt["owner_instruction_chain"]["latest_correction_digest"]
    ):
        raise MissionAdmissionError("admission_owner_correction_changed")
    if collision_digest != receipt["collision_snapshot"]["snapshot_sha256"]:
        raise MissionAdmissionError("admission_collision_snapshot_changed")


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


def _repository_identity(environ):
    configured = str(environ.get("CHARLIE_MISSION_ADMISSION_REPOSITORY") or "").strip()
    if configured:
        return configured
    remote = _git_text("config", "--get", "remote.origin.url")
    remote = remote.removesuffix(".git").replace("\\", "/")
    if "github.com/" in remote:
        return remote.split("github.com/", 1)[1]
    if remote.startswith("git@github.com:"):
        return remote.split(":", 1)[1]
    raise MissionAdmissionError("admission_repository_identity_unavailable")


def _validate_bootstrap(args, base, changed_files):
    if (
        args.bootstrap_generation != BOOTSTRAP_GENERATION
        or args.owner_instruction_sha256 != BOOTSTRAP_OWNER_INSTRUCTION_SHA256
        or args.admission_packet_sha256 != BOOTSTRAP_PACKET_SHA256
        or base != BOOTSTRAP_BASE_SHA
    ):
        raise MissionAdmissionError("bootstrap_admission_identity_changed")
    if not set(changed_files).issubset(BOOTSTRAP_ALLOWED_FILES):
        raise MissionAdmissionError("bootstrap_scope_drift")


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


def _is_read_only_shell(command):
    command = str(command or "").strip()
    if not command or any(token in command for token in ("\n", "\r", ">", "<", "|", ";", "&&", "||", "`", "$(")):
        return False
    try:
        words = shlex.split(command)
    except ValueError:
        return False
    while words and "=" in words[0] and not words[0].startswith(("./", "/")):
        name = words[0].split("=", 1)[0]
        if not name.replace("_", "").isalnum():
            return False
        words.pop(0)
    if not words:
        return False
    executable = Path(words[0]).name
    if executable in READ_ONLY_COMMANDS:
        return True
    if executable == "git" and len(words) >= 2:
        return words[1] in READ_ONLY_GIT_SUBCOMMANDS
    return False


def _shell_effect(command):
    try:
        words = shlex.split(str(command or ""))
    except ValueError:
        return "shell_execution"
    while words and "=" in words[0]:
        words.pop(0)
    if words and Path(words[0]).name == "git" and len(words) > 1:
        return SHELL_MUTATION_EFFECTS.get(words[1], "unclassified_shell_mutation")
    if words and Path(words[0]).name in {
        "python",
        "python3",
        "pytest",
        "unittest",
        "node",
        "npm",
        "npx",
    }:
        return "test_execution"
    return "unclassified_shell_mutation"


def _tool_target_path(packet):
    event = str(packet.get("hook_event_name") or "")
    if event == "afterFileEdit":
        return _relative_path(packet.get("file_path"))
    tool_input = packet.get("tool_input") if isinstance(packet.get("tool_input"), dict) else {}
    for key in ("path", "file_path", "target_file", "target_notebook"):
        if tool_input.get(key):
            return _relative_path(tool_input[key])
    return ""


def _audit_after_file_edit(packet):
    path = _tool_target_path(packet)
    if not path:
        raise MissionAdmissionError("after_file_edit_path_missing")
    if path not in BOOTSTRAP_ALLOWED_FILES and not os.getenv("CHARLIE_MISSION_ADMISSION_RECEIPT_PATH"):
        raise MissionAdmissionError("after_file_edit_unadmitted_path")


def _changed_files(base, head):
    output = _git_text("diff", "--name-only", "--diff-filter=ACMRDTUXB", base, head, "--")
    return sorted({line.strip().replace("\\", "/") for line in output.splitlines() if line.strip()})


def _worktree_changed_files(base):
    tracked = {
        line.strip().replace("\\", "/")
        for line in _git_text("diff", "--name-only", base, "--").splitlines()
        if line.strip()
    }
    status = _git_text("status", "--porcelain=v1", "--untracked-files=all")
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
