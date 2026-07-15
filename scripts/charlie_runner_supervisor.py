import json
import os
import signal
import subprocess
import sys
import time
import uuid
import ctypes
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RUNNER_DIR = REPO_ROOT / ".charlie_runner"
SUPERVISOR_PATH = RUNNER_DIR / "supervisor.json"
STOP_PATH = RUNNER_DIR / "supervisor.stop"


def _python_executable(repo_root=REPO_ROOT):
    candidates = [
        Path(repo_root) / "venv" / "Scripts" / "python.exe",
        Path(repo_root).parents[1] / "venv" / "Scripts" / "python.exe",
    ]
    return str(next((path for path in candidates if path.exists()), Path(sys.executable)))


RUNNER_COMMAND = [
    _python_executable(),
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
        child_env = {
            **os.environ,
            "CHARLIE_SUPERVISOR_GENERATION": generation,
            "GIT_CONFIG_GLOBAL": os.environ.get("GIT_CONFIG_GLOBAL", ""),
        }
        child = popen_factory(RUNNER_COMMAND, cwd=str(REPO_ROOT), env=child_env)
        child_identity = _process_identity(child.pid)
        _write_status(
            "runner_started", child_pid=child.pid, child_identity=child_identity,
            restart_count=restart_count, generation=generation,
        )
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
    recorded_identity = state.get("child_identity")
    current_identity = _process_identity(child_pid)
    if not _same_process_identity(recorded_identity, current_identity):
        return False
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(child_pid), "/T", "/F"], capture_output=True, check=False, timeout=15)
    else:
        os.kill(int(child_pid), signal.SIGTERM)
    return True


def _same_process_identity(recorded, current):
    required = ("created", "executable", "command")
    if not isinstance(recorded, dict) or not isinstance(current, dict):
        return False
    return all(recorded.get(key) and recorded.get(key) == current.get(key) for key in required)


def _process_identity(pid):
    """Return non-reusable process evidence, or None when ownership cannot be proven."""
    try:
        pid = int(pid)
        if os.name == "nt":
            return _windows_process_identity(pid)
        stat_parts = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
        executable = str(Path(f"/proc/{pid}/exe").resolve())
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8").strip()
        return {"created": stat_parts[21], "executable": executable, "command": command}
    except (OSError, ValueError, IndexError, UnicodeError, subprocess.SubprocessError):
        return None


def _windows_process_identity(pid):
    process_query_limited_information = 0x1000
    handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        return None
    try:
        creation = ctypes.c_ulonglong()
        exit_time = ctypes.c_ulonglong()
        kernel = ctypes.c_ulonglong()
        user = ctypes.c_ulonglong()
        if not ctypes.windll.kernel32.GetProcessTimes(
            handle, ctypes.byref(creation), ctypes.byref(exit_time),
            ctypes.byref(kernel), ctypes.byref(user),
        ):
            return None
        size = ctypes.c_ulong(32768)
        image = ctypes.create_unicode_buffer(size.value)
        if not ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, image, ctypes.byref(size)):
            return None
        command = _windows_process_command(pid)
        if not command:
            return None
        return {"created": str(creation.value), "executable": image.value, "command": command}
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def _windows_process_command(pid):
    script = (
        "$p=Get-CimInstance Win32_Process -Filter \"ProcessId = " + str(pid) + "\"; "
        "if($p){[Console]::Out.Write($p.CommandLine)}"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, check=False, timeout=5,
        )
    except subprocess.SubprocessError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


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
    for path in (REPO_ROOT / ".env", REPO_ROOT.parents[1] / ".env"):
        if path.exists():
            load_dotenv(path, override=False)
            break
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
