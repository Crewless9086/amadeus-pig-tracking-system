"""Fail-closed workspace, file-scope, release, and revision coordination for CORE."""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from modules.charlie.repository_guard import RepositoryOperationLock
from modules.charlie.runner_control import _shared_repository_root


VERSION = "core_concurrency_control_v1"
LEASE_SECONDS = 900
RUNTIME_COORDINATION_PATHS = {
    "planning/CODEX_CHAT.md",
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def normalize_repo_path(value):
    return str(value or "").strip().replace("\\", "/").lstrip("./")


def workspace_inventory(repo_root, *, run_factory=None):
    root = Path(repo_root).resolve()
    canonical = _shared_repository_root(root).resolve()
    runner = run_factory or subprocess.run
    result = runner(
        ["git", "worktree", "list", "--porcelain"], cwd=str(root), capture_output=True,
        text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
    )
    if result.returncode != 0:
        return {"success": False, "status": "worktree_inventory_failed", "workspaces": [], "error_type": "git_error"}
    records, current = [], {}
    for line in str(result.stdout or "").splitlines() + [""]:
        if not line.strip():
            if current:
                records.append(current)
                current = {}
            continue
        key, _, value = line.partition(" ")
        if key == "worktree": current["path"] = value.strip()
        elif key == "HEAD": current["commit"] = value.strip()
        elif key == "branch": current["branch"] = value.strip().removeprefix("refs/heads/")
        elif key == "detached": current["detached"] = True
    workspaces = []
    for item in records:
        path = Path(item.get("path", "")).resolve()
        branch = str(item.get("branch") or "")
        workspaces.append({
            **item,
            "path": str(path),
            "role": workspace_role(path, canonical, branch),
            "is_current": path == root,
            "dirty_files": dirty_files(path, run_factory=runner),
        })
    return {"success": True, "status": "workspace_inventory_ready", "version": VERSION, "canonical_root": str(canonical), "workspaces": workspaces}


def workspace_role(path, canonical, branch=""):
    path, canonical = Path(path).resolve(), Path(canonical).resolve()
    text = str(path).lower().replace("\\", "/")
    if path == canonical:
        return "owner_checkout"
    if text.endswith("/.charlie_runner/core-runtime-current"):
        return "core_runtime"
    if text.endswith("/.charlie_runner/core-execution-current"):
        return "core_execution"
    if branch.startswith("program/") or branch.startswith("feature/") or "/.worktrees/" in text or text.startswith("c:/tmp/"):
        return "interactive_feature"
    return "unclassified_worktree"


def dirty_files(path, *, run_factory=None):
    runner = run_factory or subprocess.run
    result = runner(
        ["git", "status", "--porcelain", "--untracked-files=all"], cwd=str(path),
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30, check=False,
    )
    if result.returncode != 0:
        return []
    files = []
    for line in str(result.stdout or "").splitlines():
        value = line[3:] if len(line) >= 4 else ""
        if " -> " in value:
            value = value.split(" -> ", 1)[1]
        value = normalize_repo_path(value.strip().strip('"'))
        if value:
            files.append(value)
    return sorted(set(files))


def declared_source_files(mission, artifacts=None):
    found = set()
    def walk(value, key=""):
        if isinstance(value, dict):
            for child_key, child in value.items():
                walk(child, str(child_key))
        elif isinstance(value, list):
            for child in value:
                walk(child, key)
        elif key in {
            "changed_files", "files_changed", "files_to_inspect", "affected_files",
            "implementation_sources_used", "required_inspection_paths", "code_paths",
            "tests", "migrations",
        }:
            candidate = normalize_repo_path(value)
            if candidate and not candidate.startswith(("http://", "https://")):
                found.add(candidate)
    walk(mission or {})
    walk(artifacts or {})
    # CODEX_CHAT is runner-owned coordination state. Mission pickup writes it
    # before Builder admission, so treating it as product source guarantees a
    # false overlap with the owner checkout and can deadlock every mission.
    return sorted(path for path in found if path not in RUNTIME_COORDINATION_PATHS)


def paths_overlap(left, right):
    left, right = normalize_repo_path(left), normalize_repo_path(right)
    return bool(left and right and (left == right or left.startswith(right.rstrip("/") + "/") or right.startswith(left.rstrip("/") + "/")))


def build_admission(repo_root, mission_id, declared_files, *, holder="", now_epoch=None, run_factory=None):
    root = Path(repo_root).resolve()
    inventory = workspace_inventory(root, run_factory=run_factory)
    if not inventory["success"]:
        return {**inventory, "allowed": False}
    current = next((item for item in inventory["workspaces"] if item["is_current"]), {})
    if current.get("role") == "owner_checkout" or str(current.get("branch") or "") in {"main", "master"}:
        return {"allowed": False, "status": "owner_main_execution_forbidden", "workspace": current, "conflicts": []}
    scope = sorted({normalize_repo_path(item) for item in declared_files if normalize_repo_path(item)})
    if not scope:
        return {"allowed": False, "status": "builder_source_scope_required", "workspace": current, "conflicts": []}
    conflicts = []
    for workspace in inventory["workspaces"]:
        if workspace.get("is_current"):
            continue
        overlaps = sorted({dirty for dirty in workspace.get("dirty_files", []) if any(paths_overlap(dirty, item) for item in scope)})
        if overlaps:
            conflicts.append({"workspace": workspace.get("path"), "role": workspace.get("role"), "branch": workspace.get("branch", ""), "files": overlaps})
    if conflicts:
        return {"allowed": False, "status": "concurrent_source_overlap", "workspace": current, "declared_files": scope, "conflicts": conflicts}
    lease = acquire_file_lease(inventory["canonical_root"], mission_id, scope, holder=holder, now_epoch=now_epoch)
    return {"allowed": bool(lease.get("acquired")), "status": "build_admitted" if lease.get("acquired") else lease.get("status"), "workspace": current, "canonical_root": inventory["canonical_root"], "declared_files": scope, "conflicts": lease.get("conflicts", []), "lease": lease}


def acquire_file_lease(canonical_root, mission_id, files, *, holder="", now_epoch=None):
    control = Path(canonical_root) / ".charlie_runner"
    path, lock_path = control / "file-leases.json", control / "file-leases.lock"
    lock = RepositoryOperationLock(lock_path, stale_seconds=60)
    acquired, owner = lock.acquire()
    if not acquired:
        return {"acquired": False, "status": "file_lease_registry_locked", "lock_owner": owner, "conflicts": []}
    try:
        now_epoch = float(time.time() if now_epoch is None else now_epoch)
        payload = _read_json(path, {"version": VERSION, "leases": []})
        leases = [item for item in payload.get("leases", []) if float(item.get("expires_epoch") or 0) > now_epoch]
        conflicts = [item for item in leases if item.get("mission_id") != mission_id and any(paths_overlap(left, right) for left in files for right in item.get("files", []))]
        if conflicts:
            return {"acquired": False, "status": "file_scope_leased", "conflicts": conflicts}
        leases = [item for item in leases if item.get("mission_id") != mission_id]
        lease = {"lease_id": "core-files-" + uuid.uuid4().hex[:16], "mission_id": str(mission_id), "holder": holder or f"pid:{os.getpid()}", "files": sorted(set(files)), "acquired_at": utc_now(), "expires_epoch": now_epoch + LEASE_SECONDS, "ttl_seconds": LEASE_SECONDS}
        leases.append(lease)
        _write_json(path, {"version": VERSION, "updated_at": utc_now(), "leases": leases})
        return {"acquired": True, "status": "file_scope_leased", **lease, "conflicts": []}
    finally:
        lock.release()


def release_file_lease(canonical_root, lease_id):
    control = Path(canonical_root) / ".charlie_runner"
    path = control / "file-leases.json"
    lock = RepositoryOperationLock(control / "file-leases.lock", stale_seconds=60)
    acquired, owner = lock.acquire()
    if not acquired:
        return {"released": False, "status": "file_lease_registry_locked", "lock_owner": owner}
    try:
        payload = _read_json(path, {"version": VERSION, "leases": []})
        before = list(payload.get("leases", []))
        after = [item for item in before if item.get("lease_id") != lease_id]
        _write_json(path, {"version": VERSION, "updated_at": utc_now(), "leases": after})
        return {"released": len(after) < len(before), "status": "file_scope_released" if len(after) < len(before) else "file_scope_not_found"}
    finally:
        lock.release()


class ReleaseCoordinator:
    def __init__(self, canonical_root, mission_id, pr_reference=""):
        self.root = Path(canonical_root)
        self.mission_id = str(mission_id)
        self.pr_reference = str(pr_reference)
        self.lock = RepositoryOperationLock(self.root / ".charlie_runner" / "release-coordinator.lock", stale_seconds=3600)
        self.owner = {}

    def acquire(self):
        acquired, owner = self.lock.acquire()
        self.owner = owner
        if acquired:
            self.record("release_coordination_acquired")
        return acquired, owner

    def record(self, status, **fields):
        path = self.root / ".charlie_runner" / "release-ledger.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        packet = {"version": VERSION, "recorded_at": utc_now(), "mission_id": self.mission_id, "pr_reference": self.pr_reference, "status": status, **fields}
        with path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(packet, sort_keys=True) + "\n")
        return packet

    def release(self):
        self.lock.release()


def revision_truth(repo_root, *, render_deployed_commit=""):
    current_root = Path(repo_root).resolve()
    canonical = _shared_repository_root(current_root)
    manifest = _read_json(canonical / ".charlie_runner" / "runtime-manifest.json", {})
    heartbeat = _read_json(canonical / ".charlie_runner" / "runner.json", {})
    accepted = _git_output(canonical, ["git", "rev-parse", "origin/main"])
    owner = _git_output(canonical, ["git", "rev-parse", "HEAD"])
    current = _git_output(current_root, ["git", "rev-parse", "HEAD"])
    current_branch = _git_output(current_root, ["git", "branch", "--show-current"])
    promoted = str(manifest.get("promoted_commit") or "")
    runner = str(heartbeat.get("runner_source_commit") or "")
    deployed = str(render_deployed_commit or "")
    compared = [value for value in (accepted, promoted, runner, deployed) if value]
    return {"version": VERSION, "status": "revision_truth_ready", "current_workspace_root": str(current_root), "current_workspace_branch": current_branch, "current_workspace_commit": current, "owner_checkout_commit": owner, "github_accepted_commit": accepted, "accepted_commit": accepted, "promoted_commit": promoted, "runner_commit": runner, "render_deployed_commit": deployed, "deployed_commit": deployed, "accepted_promoted_match": bool(accepted and accepted == promoted), "promoted_runner_match": bool(promoted and promoted == runner), "all_observed_match": bool(compared and len(set(compared)) == 1)}


def activation_readiness(repo_root, *, render_deployed_commit="", containment_active=True, scheduler_enabled=False, active_process_count=0):
    inventory = workspace_inventory(repo_root)
    truth = revision_truth(repo_root, render_deployed_commit=render_deployed_commit)
    blockers = []
    if not inventory.get("success"): blockers.append("workspace_inventory_failed")
    if not truth.get("all_observed_match"): blockers.append("revision_truth_not_converged")
    if not containment_active: blockers.append("containment_not_active_during_preflight")
    if scheduler_enabled: blockers.append("scheduler_enabled_during_preflight")
    if int(active_process_count or 0): blockers.append("charlie_processes_active_during_preflight")
    return {"ready": not blockers, "status": "activation_preflight_ready" if not blockers else "activation_preflight_blocked",
            "blockers": blockers, "workspace": inventory, "revision_truth": truth}


def _git_output(cwd, command):
    try:
        result = subprocess.run(command, cwd=str(cwd), capture_output=True, text=True, timeout=20, check=False)
        return str(result.stdout or "").strip() if result.returncode == 0 else ""
    except OSError:
        return ""


def _read_json(path, default):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else default
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)
