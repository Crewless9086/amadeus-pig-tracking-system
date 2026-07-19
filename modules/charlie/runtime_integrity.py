"""Authoritative runtime identity and cold-start readiness for CHARLIE CORE."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from modules.charlie.process_policy import background_run_kwargs

MANIFEST_VERSION = "charlie_core_runtime_v1"
DEFAULT_MANIFEST_NAME = "runtime-manifest.json"


def runtime_manifest_path(repo_root, runtime_dir=None):
    root = Path(repo_root).resolve()
    directory = Path(runtime_dir).resolve() if runtime_dir else root / ".charlie_runner"
    return directory / DEFAULT_MANIFEST_NAME


def git_revision(repo_root, runner=subprocess.run):
    return _command_value(["git", "rev-parse", "HEAD"], repo_root, runner)


def git_branch(repo_root, runner=subprocess.run):
    return _command_value(["git", "branch", "--show-current"], repo_root, runner)


def bootstrap_github_token(repo_root, runner=subprocess.run, environ=None):
    """Load an existing Git credential into process memory for gh; never persist or return it."""
    environ = os.environ if environ is None else environ
    if str(environ.get("GH_TOKEN") or "").strip():
        return {"ready": True, "status": "github_token_already_present"}
    try:
        completed = runner(
            ["git", "credential", "fill"], cwd=str(repo_root),
            input="protocol=https\nhost=github.com\n\n", capture_output=True, text=True,
            timeout=15, check=False, **background_run_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ready": False, "status": "github_credential_probe_failed", "error_type": exc.__class__.__name__}
    password = ""
    for line in str(completed.stdout or "").splitlines():
        if line.startswith("password="):
            password = line.split("=", 1)[1].strip()
            break
    if completed.returncode != 0 or not password:
        return {"ready": False, "status": "github_credential_unavailable"}
    environ["GH_TOKEN"] = password
    return {"ready": True, "status": "github_token_bootstrapped_from_git_credential"}


def github_auth_health(repo_root, runner=subprocess.run, environ=None):
    environ = os.environ if environ is None else environ
    bootstrap = bootstrap_github_token(repo_root, runner, environ)
    try:
        completed = runner(
            ["gh", "repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner"], cwd=str(repo_root),
            capture_output=True, text=True, timeout=15, check=False, env=dict(environ), **background_run_kwargs(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ready": False, "status": "github_auth_probe_failed", "error_type": exc.__class__.__name__}
    return {
        "ready": completed.returncode == 0,
        "status": "github_repo_access_ready" if completed.returncode == 0 else "github_repo_access_invalid",
        "detail": _safe_tail(completed.stderr or completed.stdout),
        "bootstrap_status": bootstrap.get("status"),
    }


def communication_plane_health(environ=None):
    environ = os.environ if environ is None else environ
    transport = str(environ.get("CHARLIE_TELEGRAM_TRANSPORT") or "webhook").strip().lower()
    if transport not in {"webhook", "polling", "disabled"}:
        return {"ready": False, "status": "telegram_transport_invalid", "transport": transport}
    return {
        "ready": transport in {"webhook", "polling"}, "status": f"telegram_{transport}",
        "transport": transport, "local_polling_allowed": transport == "polling",
    }


def write_runtime_manifest(repo_root, runtime_dir=None, runner=subprocess.run, source="promotion"):
    root = Path(repo_root).resolve()
    revision = git_revision(root, runner)
    branch = git_branch(root, runner)
    if not revision:
        return {"success": False, "status": "runtime_revision_unavailable"}
    path = runtime_manifest_path(root, runtime_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": MANIFEST_VERSION, "promoted_commit": revision, "promoted_branch": branch,
        "runtime_root": str(root), "promoted_at": datetime.now(timezone.utc).isoformat(), "source": source,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"success": True, "status": "runtime_manifest_written", "path": str(path), "manifest": payload}


def runtime_integrity(repo_root, runtime_dir=None, runner=subprocess.run, require_manifest=True):
    root = Path(repo_root).resolve()
    path = runtime_manifest_path(root, runtime_dir)
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {"ready": not require_manifest, "status": "runtime_manifest_missing", "manifest_path": str(path), "runtime_root": str(root)}
    except (OSError, ValueError, TypeError):
        return {"ready": False, "status": "runtime_manifest_invalid", "manifest_path": str(path)}
    current = git_revision(root, runner)
    expected_root = str(Path(str(manifest.get("runtime_root") or "")).resolve()) if manifest.get("runtime_root") else ""
    root_matches = expected_root.lower() == str(root).lower()
    commit_matches = bool(current) and current == str(manifest.get("promoted_commit") or "")
    ready = manifest.get("version") == MANIFEST_VERSION and root_matches and commit_matches
    return {
        "ready": ready, "status": "runtime_integrity_ready" if ready else "runtime_drift_detected",
        "manifest_path": str(path), "runtime_root": str(root), "expected_root": expected_root,
        "current_commit": current, "promoted_commit": str(manifest.get("promoted_commit") or ""),
        "root_matches": root_matches, "commit_matches": commit_matches, "manifest_version": manifest.get("version"),
    }


def cold_start_readiness(repo_root, runtime_dir=None, runner=subprocess.run, environ=None, require_manifest=True, require_github=True):
    integrity = runtime_integrity(repo_root, runtime_dir, runner, require_manifest=require_manifest)
    github = github_auth_health(repo_root, runner, environ) if require_github else {"ready": True, "status": "github_auth_not_required"}
    communication = communication_plane_health(environ)
    blockers = [item["status"] for item in (integrity, github, communication) if not item.get("ready")]
    return {
        "ready": not blockers, "status": "core_cold_start_ready" if not blockers else "core_cold_start_blocked",
        "blockers": blockers, "runtime": integrity, "github": github, "communication": communication,
    }


def _command_value(command, repo_root, runner):
    try:
        completed = runner(command, cwd=str(repo_root), capture_output=True, text=True, timeout=15, check=False, **background_run_kwargs())
    except (OSError, subprocess.SubprocessError):
        return ""
    return str(completed.stdout or "").strip() if completed.returncode == 0 else ""


def _safe_tail(value, limit=500):
    return str(value or "").replace("\r", " ").replace("\n", " ").strip()[-limit:]
