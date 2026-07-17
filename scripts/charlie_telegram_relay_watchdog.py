"""Idempotent windowless watchdog for the owner-only CHARLIE Telegram relay."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.charlie_telegram_relay import (
    DEFAULT_LOCK_FILE,
    _lock_pid,
    _pid_alive,
    load_config,
    load_local_env,
    validate_config,
)

STATE_PATH = REPO_ROOT / ".charlie_runner" / "telegram_relay_watchdog.json"
STDOUT_PATH = REPO_ROOT / ".charlie_runner" / "telegram_relay.out.log"
STDERR_PATH = REPO_ROOT / ".charlie_runner" / "telegram_relay.err.log"


def _windowless_process_kwargs(platform_name=None):
    platform_name = os.name if platform_name is None else platform_name
    if platform_name != "nt":
        return {"start_new_session": True}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}


def watchdog_tick(
    lock_path=DEFAULT_LOCK_FILE,
    state_path=STATE_PATH,
    popen_factory=subprocess.Popen,
    pid_alive=_pid_alive,
    config_check=None,
):
    load_local_env()
    lock_path = Path(lock_path)
    state_path = Path(state_path)
    config_result = config_check() if config_check else validate_config(load_config())
    if config_result.action != "config_ok":
        result = {
            "status": "relay_webhook_managed" if config_result.action == "webhook_managed" else ("relay_disabled" if config_result.action == "disabled" else "relay_config_failed"),
            "started": False,
            "reason": config_result.reason,
        }
        payload = {**result, "checked_at": datetime.now(timezone.utc).isoformat()}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return payload
    pid = _lock_pid(lock_path)
    stale_lock_removed = False
    lock_is_recent_without_pid = False
    if lock_path.exists() and not pid:
        try:
            lock_is_recent_without_pid = time.time() - lock_path.stat().st_mtime < 30
        except FileNotFoundError:
            pass
    if (pid and pid_alive(pid)) or lock_is_recent_without_pid:
        result = {"status": "relay_healthy", "started": False, "relay_pid": pid}
    else:
        if lock_path.exists():
            try:
                lock_path.unlink()
                stale_lock_removed = True
            except FileNotFoundError:
                pass
        state_path.parent.mkdir(parents=True, exist_ok=True)
        stdout_handle = STDOUT_PATH.open("a", encoding="utf-8")
        stderr_handle = STDERR_PATH.open("a", encoding="utf-8")
        try:
            process = popen_factory(
                [sys.executable, "-m", "scripts.charlie_telegram_relay"],
                cwd=str(REPO_ROOT),
                stdin=subprocess.DEVNULL,
                stdout=stdout_handle,
                stderr=stderr_handle,
                close_fds=True,
                **_windowless_process_kwargs(),
            )
        finally:
            stdout_handle.close()
            stderr_handle.close()
        result = {
            "status": "relay_started",
            "started": True,
            "relay_pid": int(process.pid),
            "stale_lock_removed": stale_lock_removed,
        }
    payload = {**result, "checked_at": datetime.now(timezone.utc).isoformat()}
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Check and recover the CHARLIE Telegram relay.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = watchdog_tick()
    if args.json:
        print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
