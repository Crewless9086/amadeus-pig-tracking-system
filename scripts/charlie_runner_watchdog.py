"""Idempotent outer watchdog for the local CHARLIE runner supervisor."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
os.environ.setdefault("GIT_CONFIG_COUNT", "1")
os.environ.setdefault("GIT_CONFIG_KEY_0", "safe.directory")
os.environ.setdefault("GIT_CONFIG_VALUE_0", str(REPO_ROOT))

from modules.charlie.runner_control import RUNNER_DIR, runner_status, start_runner


STATE_PATH = RUNNER_DIR / "watchdog.json"
GIT_CONFIG_PATH = RUNNER_DIR / "task-gitconfig"


def _configure_git_safe_directory(config_path=GIT_CONFIG_PATH):
    config_path = Path(config_path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path = str(REPO_ROOT).replace("\\", "/")
    config_path.write_text(f'[safe]\n\tdirectory = "{safe_path}"\n', encoding="utf-8")
    os.environ["GIT_CONFIG_GLOBAL"] = str(config_path)
    return config_path


def _fast_runner_status():
    return runner_status(include_orphans=False, include_git=False, include_ledger=False)


def watchdog_tick(status_reader=_fast_runner_status, starter=start_runner, state_path=STATE_PATH):
    _configure_git_safe_directory(Path(state_path).with_name("task-gitconfig"))
    status = status_reader()
    if status.get("active"):
        result = {"status": "runner_healthy", "started": False}
    elif status.get("orphan_processes"):
        result = {"status": "orphan_requires_cleanup", "started": False}
    else:
        started, status_code = starter(status_override=status) if starter is start_runner else starter()
        result = {
            "status": str(started.get("status") or "runner_start_failed"),
            "started": status_code < 300 and started.get("status") == "runner_started",
            "status_code": status_code,
        }
    payload = {
        **result,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "runner_status_before": str(status.get("status") or "unknown"),
    }
    state_path = Path(state_path)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    parser = argparse.ArgumentParser(description="Check and recover the local CHARLIE runner.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    result = watchdog_tick()
    print(json.dumps(result) if args.json else f"CHARLIE watchdog: {result['status']}")
    return 0 if result["status"] not in {"runner_start_failed", "orphan_requires_cleanup"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
