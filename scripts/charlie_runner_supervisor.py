import json
import csv
import os
import signal
import subprocess
import sys
import time
import uuid
import ctypes
from urllib.parse import urlsplit, urlunsplit
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
RUNNER_DIR = REPO_ROOT / ".charlie_runner"
SUPERVISOR_PATH = RUNNER_DIR / "supervisor.json"
STOP_PATH = RUNNER_DIR / "supervisor.stop"
LOCK_PATH = RUNNER_DIR / "supervisor.lock"
RUNNER_HEARTBEAT_PATH = RUNNER_DIR / "runner.json"
INFRASTRUCTURE_FAILURE_LIMIT = 3
NON_RETRYABLE_RUNNER_STATUSES = {
    "base_branch_checkout_failed",
    "base_branch_current_failed",
    "base_branch_switch_failed",
    "base_branch_verify_failed",
    "git_operation_in_progress",
    "git_operation_marker_check_failed",
    "runner_preflight_failed",
}


class SupervisorInstanceLock:
    """Atomic, process-owned guard against duplicate local supervisors."""

    def __init__(self, path=LOCK_PATH):
        self.path = Path(path)
        self.owned = False

    def acquire(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        for _attempt in range(2):
            try:
                descriptor = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                owner_pid = _lock_owner_pid(self.path)
                if owner_pid and _pid_alive(owner_pid):
                    return False, owner_pid
                try:
                    self.path.unlink()
                except FileNotFoundError:
                    pass
                except OSError:
                    return False, owner_pid
                continue
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump({"pid": os.getpid(), "created_at": datetime.now(timezone.utc).isoformat()}, stream)
            self.owned = True
            return True, os.getpid()
        return False, _lock_owner_pid(self.path)

    def release(self):
        if not self.owned:
            return
        try:
            if _lock_owner_pid(self.path) == os.getpid():
                self.path.unlink()
        except FileNotFoundError:
            pass
        finally:
            self.owned = False


def _lock_owner_pid(path=LOCK_PATH):
    try:
        return int(json.loads(Path(path).read_text(encoding="utf-8")).get("pid") or 0)
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def _transaction_pool_url(value):
    """Use Supabase's transaction pool for long-lived local runner processes."""
    raw = str(value or "").strip()
    if not raw:
        return raw
    try:
        parsed = urlsplit(raw)
        if not parsed.hostname or not parsed.hostname.endswith(".pooler.supabase.com") or parsed.port != 5432:
            return raw
        if not parsed.netloc.endswith(":5432"):
            return raw
        netloc = f"{parsed.netloc[:-5]}:6543"
        return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    except (ValueError, TypeError):
        return raw


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


def supervise_runner(popen_factory=subprocess.Popen, sleep_fn=time.sleep, max_cycles=None, notifier=None):
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    generation = uuid.uuid4().hex
    _recover_stale_owned_child()
    restart_count = 0
    cycles = 0
    repeated_failure = ""
    repeated_failure_count = 0
    while not STOP_PATH.exists():
        cycles += 1
        child_env = {
            **os.environ,
            "CHARLIE_SUPERVISOR_GENERATION": generation,
            "GIT_CONFIG_GLOBAL": os.environ.get("GIT_CONFIG_GLOBAL", ""),
        }
        child_env["DATABASE_URL"] = _transaction_pool_url(child_env.get("DATABASE_URL"))
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
        failure = _runner_failure_signature()
        if failure and failure == repeated_failure:
            repeated_failure_count += 1
        elif failure:
            repeated_failure = failure
            repeated_failure_count = 1
        else:
            repeated_failure = ""
            repeated_failure_count = 0
        if failure and repeated_failure_count >= INFRASTRUCTURE_FAILURE_LIMIT:
            payload = _write_status(
                "infrastructure_hold",
                child_pid=child.pid,
                restart_count=restart_count,
                return_code=return_code,
                failure_status=failure,
                identical_failure_count=repeated_failure_count,
                generation=generation,
                recommended_action="Resolve the recorded infrastructure failure, then explicitly restart CORE.",
            )
            if notifier:
                notifier(payload)
            return {"status": "infrastructure_hold", "restart_count": restart_count, "cycles": cycles, "failure_status": failure}
        delay = min(5 * (2 ** min(restart_count - 1, 4)), 60)
        _write_status("runner_exited_restart_pending", child_pid=child.pid, restart_count=restart_count, return_code=return_code, restart_delay_seconds=delay, generation=generation)
        if max_cycles is not None and cycles >= max_cycles:
            break
        sleep_fn(delay)
    return {"status": "supervisor_stopped", "restart_count": restart_count, "cycles": cycles}


def _runner_failure_signature(path=None):
    path = RUNNER_HEARTBEAT_PATH if path is None else path
    try:
        status = str(json.loads(Path(path).read_text(encoding="utf-8")).get("last_result_status") or "").strip()
    except (OSError, ValueError, TypeError, AttributeError):
        return ""
    return status if status in NON_RETRYABLE_RUNNER_STATUSES else ""


def _notify_infrastructure_hold(payload):
    failure = str((payload or {}).get("failure_status") or "unknown_infrastructure_failure")
    message = (
        f"CORE stopped after {INFRASTRUCTURE_FAILURE_LIMIT} identical infrastructure failures: {failure}. "
        "The watchdog will not restart it until the recorded hold is resolved and CORE is explicitly restarted."
    )
    try:
        completed = subprocess.run(
            [
                _python_executable(),
                str(REPO_ROOT / "scripts" / "charlie_notify.py"),
                "--level", "blocked",
                "--title", "CORE infrastructure hold",
                "--message", message,
            ],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except Exception as exc:
        return {"success": False, "status": "notification_failed", "error_type": exc.__class__.__name__}
    return {"success": completed.returncode == 0, "status": "sent" if completed.returncode == 0 else "notification_failed"}


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


def _pid_alive(pid, runner=subprocess.run):
    try:
        pid = int(pid)
        if pid <= 0:
            return False
        if os.name == "nt":
            completed = runner(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if completed.returncode != 0:
                return False
            rows = list(csv.reader(str(completed.stdout or "").splitlines()))
            return any(len(row) > 1 and row[1].strip() == str(pid) for row in rows)
        os.kill(pid, 0)
        return True
    except (TypeError, ValueError, OSError, SystemError, subprocess.SubprocessError):
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
    instance_lock = SupervisorInstanceLock()
    acquired, owner_pid = instance_lock.acquire()
    if not acquired:
        _write_status("duplicate_supervisor_refused", existing_supervisor_pid=owner_pid)
        return {"status": "duplicate_supervisor_refused", "existing_supervisor_pid": owner_pid}
    try:
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
        return supervise_runner(notifier=_notify_infrastructure_hold)
    finally:
        instance_lock.release()


if __name__ == "__main__":
    result = main()
    raise SystemExit(0 if result.get("status") in {"supervisor_stopped", "duplicate_supervisor_refused"} else 1)
