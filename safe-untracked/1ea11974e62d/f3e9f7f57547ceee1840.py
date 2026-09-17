"""Bounded, actual-content review evidence read from the retained worktree."""
import hashlib
import json
import subprocess
from pathlib import Path

from .candidate_contract import binding_from_authority
from .execution import (MAX_CONTEXT_BYTES, REMOTE, ContextBroker, NativeExecutionError,
                        _safe_env, normalize_repo_path, run_argv)
from .protocol import canonical_candidate_diff


def _git(root, *args):
    result = subprocess.run(["git", *args], cwd=str(root), env=_safe_env(),
                            capture_output=True, check=False, shell=False, timeout=30)
    if result.returncode:
        raise NativeExecutionError("native_review_git_unavailable")
    if len(result.stdout) > MAX_CONTEXT_BYTES:
        raise NativeExecutionError("native_review_content_limit")
    try:
        return result.stdout.decode("utf-8")
    except UnicodeError as exc:
        raise NativeExecutionError("native_review_content_not_text") from exc


def verification_snapshot(root, base_sha):
    patch = _git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index", base_sha, "--")
    paths = sorted(filter(None, _git(root, "diff", "--no-ext-diff", "--no-textconv", "--name-only", base_sha, "--").splitlines()))
    return {"base_sha": base_sha, "changed_files": paths,
            "candidate_diff_sha256": canonical_candidate_diff(paths, patch.encode("utf-8"))}


def _digest(packet):
    return hashlib.sha256(json.dumps({k: v for k, v in packet.items() if k != "packet_sha256"},
                                    sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_review_packet(packet):
    if not isinstance(packet, dict) or packet.get("packet_sha256") != _digest(packet):
        raise NativeExecutionError("native_review_content_required")
    candidate = packet.get("candidate") or {}
    required = {"pr_number", "base_sha", "head_sha", "candidate_diff_sha256", "changed_files"}
    content = packet.get("content") or {}
    if (not required.issubset(candidate) or not isinstance(content.get("diff"), str)
            or not content["diff"] or not isinstance(content.get("files"), list)
            or [f.get("path") for f in content["files"]] != candidate["changed_files"]
            or any(not isinstance(f.get(k), str) for f in content["files"] for k in ("before", "after"))
            or canonical_candidate_diff(candidate["changed_files"], content["diff"].encode()) != candidate["candidate_diff_sha256"]
            or not packet.get("verification") or not packet.get("contract") or not packet.get("instruction")):
        raise NativeExecutionError("native_review_content_required")
    if len(json.dumps(packet).encode()) > MAX_CONTEXT_BYTES:
        raise NativeExecutionError("native_review_content_limit")
    return packet


def build_review_packet(worktree, mission, native, evidence, *, verification_plan=None):
    binding = binding_from_authority(mission, native)
    root = Path(worktree).resolve(strict=True)
    if (_git(root, "rev-parse", "HEAD").strip() != binding["head_sha"]
            or _git(root, "branch", "--show-current").strip() != binding["branch_name"]
            or _git(root, "remote", "get-url", "origin").strip() != REMOTE
            or _git(root, "status", "--porcelain").strip()
            or run_argv(["git", "merge-base", "--is-ancestor", binding["base_sha"], binding["head_sha"]], cwd=root).returncode):
        raise NativeExecutionError("native_review_worktree_identity_mismatch")
    patch = _git(root, "diff", "--no-ext-diff", "--no-textconv", "--binary", "--full-index",
                 binding["base_sha"], binding["head_sha"], "--")
    paths = sorted(filter(None, _git(root, "diff", "--no-ext-diff", "--no-textconv", "--name-only",
                                    binding["base_sha"], binding["head_sha"], "--").splitlines()))
    if paths != binding["changed_files"] or canonical_candidate_diff(paths, patch.encode()) != binding["candidate_diff_sha256"]:
        raise NativeExecutionError("native_review_candidate_mismatch")
    # Apply the existing context path/secret restrictions before reading blobs.
    ContextBroker(root, binding["allowed_files"]).read(paths)
    files = []
    for path in paths:
        path = normalize_repo_path(path)
        files.append({"path": path,
                      "before": _git(root, "show", binding["base_sha"] + ":" + path),
                      "after": _git(root, "show", binding["head_sha"] + ":" + path)})
    expected = {k: binding[k] for k in ("base_sha", "changed_files", "candidate_diff_sha256")}
    expected_commands = list(native.get("allowed_commands") or [])
    if verification_plan is not None:
        if (not isinstance(verification_plan, list) or not verification_plan
                or sorted(r.get("name", "") for r in verification_plan) != sorted(binding["required_tests"])):
            raise NativeExecutionError("native_review_verification_plan_unbound")
        expected_commands += [r["name"] for r in verification_plan]
        if (not isinstance(evidence, list) or len(evidence) != len(expected_commands)
                or any(row.get("argv") != recipe.get("argv") for row,recipe in
                       zip(evidence[len(native.get("allowed_commands") or []):], verification_plan))):
            raise NativeExecutionError("native_review_verification_plan_unbound")
    if (not isinstance(evidence, list) or not evidence
            or [r.get("command") for r in evidence] != expected_commands
            or any(type(r.get("returncode")) is not int or r["returncode"] != 0 or any(r.get(k) != v for k, v in expected.items())
                   or any(not isinstance(r.get(k), str) for k in ("stdout", "stderr")) for r in evidence)):
        raise NativeExecutionError("native_review_verification_unbound")
    vault = mission.get("vault") or (mission.get("metadata") or {}).get("mission_vault") or {}
    instruction = vault.get("problem_statement")
    if (not isinstance(instruction, str) or not instruction.strip()
            or hashlib.sha256(instruction.encode()).hexdigest() != native.get("owner_instruction_digest")):
        raise NativeExecutionError("native_review_instruction_unbound")
    packet = {"version": "charlie_native_review_content_v1", "mission_id": mission["mission_id"],
              "native_execution_id": native["native_execution_id"], "generation": native["generation"],
              "candidate": {k: binding[k] for k in ("pr_number", "base_sha", "head_sha", "candidate_diff_sha256", "changed_files")},
              "contract": binding, "instruction": instruction, "content": {"diff": patch, "files": files},
              "verification": evidence, "executable_verification_plan": verification_plan,
              "verification_limit": "These are only the commands actually run; required tests and operational acceptance remain separate gates."}
    packet["packet_sha256"] = _digest(packet)
    return validate_review_packet(packet)
