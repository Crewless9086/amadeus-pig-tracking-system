"""Process-safe repository operations and dedicated runner worktree recovery."""

from __future__ import annotations

import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


class RepositoryOperationLock:
    def __init__(self, path, *, stale_seconds=1800):
        self.path = Path(path)
        self.stale_seconds = int(stale_seconds)
        self.owned = False

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in range(2):
            try:
                descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                owner = self._owner()
                age = max(0, time.time() - float(owner.get("created_epoch") or 0))
                if owner.get("pid") and _pid_alive(owner["pid"]) and age < self.stale_seconds:
                    return False, owner
                try:
                    self.path.unlink()
                except OSError:
                    return False, owner
                continue
            payload = {
                "pid": os.getpid(),
                "created_epoch": time.time(),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream)
            self.owned = True
            return True, payload
        return False, self._owner()

    def release(self):
        if not self.owned:
            return
        try:
            owner = self._owner()
            if int(owner.get("pid") or 0) == os.getpid():
                self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.owned = False

    def _owner(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}


def inspect_git_operation_markers(repo_root, *, run_factory=None):
    """Classify Git markers without removing non-empty or unreadable state."""
    run_factory = subprocess.run if run_factory is None else run_factory
    recovered = []
    for marker_name in ("rebase-merge", "rebase-apply"):
        try:
            resolved = run_factory(
                ["git", "rev-parse", "--git-path", marker_name], cwd=repo_root,
                text=True, capture_output=True, timeout=10,
            )
        except Exception as exc:
            return _marker_failure("git_operation_marker_check_failed", marker_name, "", exc)
        if resolved.returncode != 0:
            return {
                "success": False, "status": "git_operation_marker_check_failed",
                "failure_class": "repository_infrastructure", "marker": marker_name,
                "stderr": str(resolved.stderr or "").strip(),
                "recommended_action": "Repair the dedicated runner worktree before restarting CORE.",
            }
        marker = Path(str(resolved.stdout or "").strip())
        if not marker.is_absolute():
            marker = Path(repo_root) / marker
        try:
            exists = marker.exists()
            if not exists:
                continue
            is_dir = marker.is_dir()
            entries = list(marker.iterdir()) if is_dir else [marker]
        except PermissionError as exc:
            return _marker_failure("git_operation_marker_permission_denied", marker_name, marker, exc)
        except OSError as exc:
            return _marker_failure("git_operation_marker_check_failed", marker_name, marker, exc)
        if not is_dir or entries:
            return {
                "success": False, "status": "git_operation_in_progress",
                "failure_class": "repository_infrastructure", "marker": marker_name,
                "marker_path": str(marker),
                "recommended_action": "Inspect and complete or abort the non-empty Git operation before restarting CORE.",
            }
        try:
            marker.rmdir()
        except PermissionError as exc:
            return _marker_failure("git_operation_marker_permission_denied", marker_name, marker, exc)
        except OSError as exc:
            return _marker_failure("git_operation_marker_remove_failed", marker_name, marker, exc)
        recovered.append(str(marker))
    return {"success": True, "status": "empty_git_markers_recovered" if recovered else "no_git_markers", "recovered": recovered}


def repository_lock_path(repo_root):
    root = Path(repo_root).resolve()
    canonical = root.parents[1] if root.parent.name == ".charlie_runner" else root
    return canonical / ".charlie_runner" / "repository-operation.lock"


def _marker_failure(status, marker_name, marker, exc):
    return {
        "success": False,
        "status": status,
        "failure_class": "repository_infrastructure",
        "marker": marker_name,
        "marker_path": str(marker or ""),
        "error_type": exc.__class__.__name__,
        "stderr": f"{exc.__class__.__name__}: {exc}",
        "recoverable_by_supervisor": status in {"git_operation_marker_permission_denied", "git_operation_marker_remove_failed"},
        "recommended_action": "Quarantine and recreate the dedicated CORE runner worktree, then restart the runner.",
    }


def _pid_alive(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False
