import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER_DIR = REPO_ROOT / ".charlie_runner"
SUPERVISOR_PATH = RUNNER_DIR / "supervisor.json"
STOP_PATH = RUNNER_DIR / "supervisor.stop"
RUNNER_COMMAND = [
    str(REPO_ROOT / "venv" / "Scripts" / "python.exe"),
    str(REPO_ROOT / "scripts" / "charlie_mission_pickup.py"),
    "--watch", "--continuous", "--notify", "--execute-codex", "--watch-release",
    "--auto-merge-pr", "--release-verify-url",
    "https://amadeus-pig-tracking-system.onrender.com/charlie", "--interval-seconds", "30",
]


def supervise_runner(popen_factory=subprocess.Popen, sleep_fn=time.sleep, max_cycles=None):
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    restart_count = 0
    cycles = 0
    while not STOP_PATH.exists():
        cycles += 1
        child = popen_factory(RUNNER_COMMAND, cwd=str(REPO_ROOT))
        _write_status("runner_started", child_pid=child.pid, restart_count=restart_count)
        return_code = child.wait()
        if STOP_PATH.exists():
            _write_status("supervisor_stopped", child_pid=child.pid, restart_count=restart_count, return_code=return_code)
            break
        restart_count += 1
        delay = min(5 * (2 ** min(restart_count - 1, 4)), 60)
        _write_status("runner_exited_restart_pending", child_pid=child.pid, restart_count=restart_count, return_code=return_code, restart_delay_seconds=delay)
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep_fn(delay)
    return {"status": "supervisor_stopped", "restart_count": restart_count, "cycles": cycles}


def _write_status(status, **extra):
    payload = {
        "pid": os.getpid(),
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **extra,
    }
    SUPERVISOR_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def main():
    load_dotenv(REPO_ROOT / ".env", override=False)
    if STOP_PATH.exists():
        STOP_PATH.unlink()
    return supervise_runner()


if __name__ == "__main__":
    raise SystemExit(0 if main().get("status") == "supervisor_stopped" else 1)
