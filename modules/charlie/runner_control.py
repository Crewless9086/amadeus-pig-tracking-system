import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / ".charlie_runner"
HEARTBEAT_PATH = RUNNER_DIR / "runner.json"
LOG_PATH = RUNNER_DIR / "runner.log"
STALE_SECONDS = 120
RUNNER_COMMAND = [
    str(REPO_ROOT / "venv" / "Scripts" / "python.exe"),
    str(REPO_ROOT / "scripts" / "charlie_mission_pickup.py"),
    "--watch",
    "--continuous",
    "--notify",
    "--interval-seconds",
    "30",
]


def runner_status(heartbeat_path=None, now=None, include_orphans=None):
    heartbeat_path = Path(heartbeat_path or HEARTBEAT_PATH)
    if include_orphans is None:
        include_orphans = heartbeat_path == HEARTBEAT_PATH
    payload = _read_json(heartbeat_path)
    now = now or datetime.now(timezone.utc)
    last_seen = _parse_iso(payload.get("last_seen"))
    age_seconds = int((now - last_seen).total_seconds()) if last_seen else None
    process_alive = _pid_alive(payload.get("pid"))
    heartbeat_fresh = age_seconds is not None and age_seconds <= STALE_SECONDS
    active = process_alive and heartbeat_fresh
    orphan_processes = [] if payload or not include_orphans else _find_runner_processes()
    if active:
        status = "runner_active"
        next_action = "Approved missions should be picked up automatically while this runner stays active."
    elif orphan_processes:
        status = "runner_orphaned"
        next_action = "Stop the orphaned local CHARLIE runner, then start it again so runner control owns the heartbeat."
    elif payload:
        status = "runner_stale_or_stopped"
        next_action = "Start the local CHARLIE runner before expecting approved missions to auto-pick up."
    else:
        status = "runner_not_started"
        next_action = "Start the local CHARLIE runner before expecting approved missions to auto-pick up."
    return {
        "success": True,
        "status": status,
        "active": active,
        "pid": payload.get("pid"),
        "process_alive": process_alive,
        "heartbeat_fresh": heartbeat_fresh,
        "last_seen": payload.get("last_seen", ""),
        "age_seconds": age_seconds,
        "last_result_status": payload.get("last_result_status", ""),
        "last_mission_id": payload.get("last_mission_id", ""),
        "orphan_processes": orphan_processes,
        "log_path": str(LOG_PATH),
        "heartbeat_path": str(heartbeat_path),
        "command": _display_command(),
        "next_action": next_action,
        "can_start_from_web": False,
        "can_stop_from_web": False,
    }


def write_runner_heartbeat(result=None, heartbeat_path=None):
    heartbeat_path = Path(heartbeat_path or HEARTBEAT_PATH)
    heartbeat_path.parent.mkdir(parents=True, exist_ok=True)
    result = result if isinstance(result, dict) else {}
    payload = {
        "pid": os.getpid(),
        "last_seen": datetime.now(timezone.utc).isoformat(),
        "last_result_status": str(result.get("status") or ""),
        "last_mission_id": str(result.get("mission_id") or ""),
        "active_status": str(result.get("active_status") or ""),
    }
    heartbeat_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def start_runner():
    status = runner_status()
    if status["active"]:
        return {"success": True, "status": "runner_already_active", "runner": status}, 200
    if status.get("orphan_processes"):
        return {"success": False, "status": "runner_orphaned_existing_process", "runner": status}, 409
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    python_path = RUNNER_COMMAND[0]
    if not Path(python_path).exists():
        python_path = sys.executable
    command = [python_path, *RUNNER_COMMAND[1:]]
    with LOG_PATH.open("ab") as log:
        creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        process = subprocess.Popen(
            command,
            cwd=str(REPO_ROOT),
            stdout=log,
            stderr=log,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    write_runner_heartbeat({"status": "runner_started"}, HEARTBEAT_PATH)
    payload = _read_json(HEARTBEAT_PATH)
    payload["pid"] = process.pid
    HEARTBEAT_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {
        "success": True,
        "status": "runner_started",
        "pid": process.pid,
        "command": _display_command(command),
        "log_path": str(LOG_PATH),
    }, 200


def stop_runner():
    status = runner_status()
    pids = [status.get("pid")]
    pids.extend(process.get("pid") for process in status.get("orphan_processes", []))
    pids = [int(pid) for pid in pids if str(pid or "").isdigit()]
    if not pids:
        return {"success": True, "status": "runner_not_started", "runner": status}, 200
    stopped = []
    try:
        for pid in pids:
            os.kill(pid, signal.SIGTERM)
            stopped.append(pid)
    except OSError:
        if not stopped:
            return {"success": True, "status": "runner_already_stopped", "runner": status}, 200
    return {"success": True, "status": "runner_stop_requested", "pids": stopped}, 200


def _display_command(command=None):
    command = command or RUNNER_COMMAND
    return " ".join(command).replace(str(REPO_ROOT) + "\\", "")


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _parse_iso(value):
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def _pid_alive(pid):
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _pid_alive_windows(pid):
    try:
        import ctypes
        from ctypes import wintypes
    except ImportError:
        return False

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    SYNCHRONIZE = 0x00100000
    WAIT_TIMEOUT = 0x00000102
    STILL_ACTIVE = 259

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        wait_result = kernel32.WaitForSingleObject(handle, 0)
        if wait_result == WAIT_TIMEOUT:
            return True
        exit_code = wintypes.DWORD()
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return exit_code.value == STILL_ACTIVE
        return False
    finally:
        kernel32.CloseHandle(handle)


def _find_runner_processes():
    if os.name == "nt":
        return _find_runner_processes_windows()
    return _find_runner_processes_posix()


def _find_runner_processes_windows():
    script = (
        "Get-CimInstance Win32_Process | "
        "Where-Object { $_.Name -like 'python*' -and "
        "$_.CommandLine -like '*charlie_mission_pickup.py*' -and "
        "$_.CommandLine -like '*--watch*' -and "
        "$_.CommandLine -like '*--continuous*' } | "
        "Select-Object ProcessId,ParentProcessId,CommandLine | "
        "ConvertTo-Json -Depth 4"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    try:
        loaded = json.loads(completed.stdout)
    except ValueError:
        return []
    rows = loaded if isinstance(loaded, list) else [loaded]
    return [
        {
            "pid": row.get("ProcessId"),
            "parent_pid": row.get("ParentProcessId"),
            "command": row.get("CommandLine", ""),
        }
        for row in rows
        if isinstance(row, dict) and row.get("ProcessId") != os.getpid()
    ]


def _find_runner_processes_posix():
    try:
        completed = subprocess.run(
            ["ps", "-eo", "pid=,ppid=,command="],
            capture_output=True,
            check=False,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    processes = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        pid, parent_pid, command = parts
        if (
            pid.isdigit()
            and int(pid) != os.getpid()
            and "charlie_mission_pickup.py" in command
            and "--watch" in command
            and "--continuous" in command
        ):
            processes.append({"pid": int(pid), "parent_pid": int(parent_pid), "command": command})
    return processes
