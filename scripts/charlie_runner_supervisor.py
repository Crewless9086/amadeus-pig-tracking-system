import json
import os
import signal
import subprocess
import sys
import time
import uuid
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
    generation = uuid.uuid4().hex
    _recover_stale_owned_child()
    restart_count = 0
    cycles = 0
    while not STOP_PATH.exists():
        cycles += 1
        child_env = {**os.environ, "CHARLIE_SUPERVISOR_GENERATION": generation}
        child = popen_factory(RUNNER_COMMAND, cwd=str(REPO_ROOT), env=child_env)
        _write_status("runner_started", child_pid=child.pid, restart_count=restart_count, generation=generation)
        return_code = child.wait()
        if STOP_PATH.exists():
            _write_status("supervisor_stopped", child_pid=child.pid, restart_count=restart_count, return_code=return_code, generation=generation)
            break
        restart_count += 1
        delay = min(5 * (2 ** min(restart_count - 1, 4)), 60)
        _write_status("runner_exited_restart_pending", child_pid=child.pid, restart_count=restart_count, return_code=return_code, restart_delay_seconds=delay, generation=generation)
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep_fn(delay)
    return {"status": "supervisor_stopped", "restart_count": restart_count, "cycles": cycles}


def _recover_stale_owned_child():
    try:
        state = json.loads(SUPERVISOR_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    supervisor_pid = state.get("pid")
    child_pid = state.get("child_pid")
    if not child_pid or _pid_alive(supervisor_pid) or not _pid_alive(child_pid):
        return False
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child_pid), "/T", "/F"], capture_output=True, check=False, timeout=15)
    else:
        os.kill(int(child_pid), signal.SIGTERM)
    return True


def _pid_alive(pid):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        os.kill(pid, 0)
        return True
    except (TypeError, ValueError, OSError):
        return False


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
    try:
        from modules.charlie.execution_bridge import recover_pending_final_agent_artifact
        recovery, recovery_status = recover_pending_final_agent_artifact()
    except Exception as exc:
        recovery, recovery_status = {"status": "final_artifact_recovery_failed", "error_type": exc.__class__.__name__}, 503
    if recovery_status >= 400:
        _write_status("final_artifact_recovery_blocked", recovery=recovery)
        return {"status": "final_artifact_recovery_blocked", "recovery": recovery}
    return supervise_runner()


if __name__ == "__main__":
    raise SystemExit(0 if main().get("status") == "supervisor_stopped" else 1)
