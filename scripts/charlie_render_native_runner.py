#!/usr/bin/env python3
"""Render persistent-disk bootstrap for the standalone native runner."""

from __future__ import annotations

import os
import json
import subprocess
from pathlib import Path

ORIGIN = "https://github.com/Crewless9086/amadeus-pig-tracking-system.git"
DISK = Path("/var/data")
REPOSITORY = DISK / "repository"
WORKTREES = DISK / "worktrees"
PROFILE = DISK / "hermes-profile"


def run(argv, *, cwd=None):
    allowed = ("PATH", "HOME", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP",
               "SYSTEMROOT", "COMSPEC", "PATHEXT", "SSL_CERT_FILE",
               "REQUESTS_CA_BUNDLE", "GIT_SSL_CAINFO")
    child_env = {name: os.environ[name] for name in allowed if os.environ.get(name)}
    return subprocess.run(argv, cwd=cwd, check=True, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          shell=False, env=child_env)


def prepare_repository(*, deployed_sha=None):
    DISK.mkdir(mode=0o700, parents=True, exist_ok=True)
    WORKTREES.mkdir(mode=0o700, parents=True, exist_ok=True)
    PROFILE.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not (REPOSITORY / ".git").exists():
        if REPOSITORY.exists() and any(REPOSITORY.iterdir()):
            raise RuntimeError("render_runner_repository_not_clean")
        run(["git", "clone", "--no-tags", ORIGIN, str(REPOSITORY)])
    origin = run(["git", "remote", "get-url", "origin"], cwd=REPOSITORY).stdout.strip()
    if origin != ORIGIN:
        raise RuntimeError("render_runner_repository_origin_invalid")
    sha = str(deployed_sha or os.environ.get("RENDER_GIT_COMMIT") or "").strip()
    if len(sha) != 40 or any(ch not in "0123456789abcdef" for ch in sha.lower()):
        raise RuntimeError("render_runner_revision_invalid")
    run(["git", "fetch", "--no-tags", "origin", sha], cwd=REPOSITORY)
    run(["git", "checkout", "--detach", "--force", sha], cwd=REPOSITORY)
    actual = run(["git", "rev-parse", "HEAD"], cwd=REPOSITORY).stdout.strip()
    if actual != sha:
        raise RuntimeError("render_runner_revision_mismatch")
    if run(["git", "status", "--porcelain"], cwd=REPOSITORY).stdout.strip():
        raise RuntimeError("render_runner_repository_dirty")
    return actual


def prepare_hermes_profile():
    """Pin auxiliary transient retries without reading profile secrets."""
    PROFILE.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = PROFILE / "config.yaml"
    try:
        current = json.loads(target.read_text(encoding="utf-8")) if target.exists() else {}
    except (ValueError, OSError) as exc:
        raise RuntimeError("render_runner_hermes_config_invalid") from exc
    if current is None:
        current = {}
    if not isinstance(current, dict):
        raise RuntimeError("render_runner_hermes_config_invalid")
    auxiliary = current.setdefault("auxiliary", {})
    if not isinstance(auxiliary, dict):
        raise RuntimeError("render_runner_hermes_config_invalid")
    auxiliary["transient_retries"] = 0
    temporary = target.with_suffix(".tmp")
    # JSON is a strict YAML subset and avoids adding a bootstrap parser before
    # the pinned Hermes runtime is imported.
    temporary.write_text(json.dumps(current, sort_keys=True, indent=2), encoding="utf-8")
    os.replace(temporary, target)


def main():
    prepare_hermes_profile()
    prepare_repository()
    argv = [
        os.environ.get("PYTHON", "python"), "-m", "scripts.charlie_native_runner",
        "--watch", "--poll-seconds", "15", "--configuration-source", "environment",
        "--profile-home", str(PROFILE), "--repository-root", str(REPOSITORY),
        "--worktree-root", str(WORKTREES),
    ]
    os.execvpe(argv[0], argv, os.environ)


if __name__ == "__main__":
    main()
