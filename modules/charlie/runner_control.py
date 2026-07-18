import json
import os
import csv
import signal
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER_DIR = REPO_ROOT / ".charlie_runner"
HEARTBEAT_PATH = RUNNER_DIR / "runner.json"
LOG_PATH = RUNNER_DIR / "runner.log"
SUPERVISOR_PATH = RUNNER_DIR / "supervisor.json"
SUPERVISOR_STOP_PATH = RUNNER_DIR / "supervisor.stop"
STALE_SECONDS = 120


def _python_executable(repo_root=REPO_ROOT):
    candidates = [
        Path(repo_root) / "venv" / "Scripts" / "python.exe",
        Path(repo_root).parents[1] / "venv" / "Scripts" / "python.exe",
    ]
    return str(next((path for path in candidates if path.exists()), Path(sys.executable)))


RUNNER_COMMAND = [
    _python_executable(),
    str(REPO_ROOT / "scripts" / "charlie_mission_pickup.py"),
    "--watch",
    "--continuous",
    "--notify",
    "--execute-codex",
    "--watch-release",
    "--auto-merge-pr",
    "--release-verify-url",
    "https://amadeus-pig-tracking-system.onrender.com/charlie",
    "--interval-seconds",
    "30",
]
SUPERVISOR_COMMAND = [
    _python_executable(),
    str(REPO_ROOT / "scripts" / "charlie_runner_supervisor.py"),
]


def runner_status(heartbeat_path=None, now=None, include_orphans=None, include_git=True, include_ledger=True):
    heartbeat_path = Path(heartbeat_path or HEARTBEAT_PATH)
    if include_orphans is None:
        include_orphans = heartbeat_path == HEARTBEAT_PATH
    payload = _read_json(heartbeat_path)
    now = now or datetime.now(timezone.utc)
    last_seen = _parse_iso(payload.get("last_seen"))
    age_seconds = int((now - last_seen).total_seconds()) if last_seen else None
    process_alive = _pid_alive(payload.get("pid"))
    heartbeat_fresh = age_seconds is not None and age_seconds <= STALE_SECONDS
    runner_source_commit = str(payload.get("runner_source_commit") or "").strip()
    current_source_commit = _current_git_commit() if include_git else ""
    code_stale = bool(runner_source_commit and current_source_commit and runner_source_commit != current_source_commit)
    active = process_alive and heartbeat_fresh and not code_stale
    final_artifact_present = bool(payload.get("final_artifact_present"))
    if not final_artifact_present and _execution_artifact_exists(payload.get("execution_artifact", "")):
        final_artifact_present = True
        if payload.get("last_result_status") == "codex_running":
            payload["last_result_status"] = "codex_final_artifact_seen"
    orphan_processes = [] if payload or not include_orphans else _find_runner_processes()
    supervisor = _read_json(SUPERVISOR_PATH) if heartbeat_path == HEARTBEAT_PATH else {}
    supervisor_alive = _pid_alive(supervisor.get("pid"))
    supervisor_owns_runner = bool(
        supervisor_alive
        and process_alive
        and (
            int(supervisor.get("child_pid") or 0) == int(payload.get("pid") or -1)
            or _pid_descends_from(payload.get("pid"), supervisor.get("child_pid"))
        )
        and str(supervisor.get("generation") or "")
        and str(supervisor.get("generation") or "") == str(payload.get("supervisor_generation") or "")
    )
    if heartbeat_path == HEARTBEAT_PATH:
        active = active and supervisor_owns_runner
    ledger_summary = _read_agent_ledger_summary(payload.get("agent_ledger_path", "")) if include_ledger else {}
    operating_state = _runner_operating_state(payload, ledger_summary, active)
    if code_stale and process_alive and heartbeat_fresh:
        status = "runner_code_stale"
        next_action = "Restart the local CHARLIE runner because main changed after this runner process started."
    elif active:
        status = "runner_active"
        next_action = {
            "running_agent": "CORE is actively executing the displayed agent stage.",
            "between_stages": "CORE is healthy and transitioning between agent stages.",
            "waiting_for_queue": "CORE is healthy and waiting for an approved mission.",
        }.get(operating_state, "CORE is healthy and processing the mission queue.")
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
        "operating_state": operating_state,
        "pid": payload.get("pid"),
        "process_alive": process_alive,
        "heartbeat_fresh": heartbeat_fresh,
        "last_seen": payload.get("last_seen", ""),
        "age_seconds": age_seconds,
        "last_result_status": payload.get("last_result_status", ""),
        "last_mission_id": payload.get("last_mission_id", ""),
        "elapsed_seconds": payload.get("elapsed_seconds"),
        "changed_files_count": payload.get("changed_files_count"),
        "final_artifact_present": final_artifact_present,
        "execution_artifact": payload.get("execution_artifact", ""),
        "agent_runner_version": payload.get("agent_runner_version", ""),
        "runner_source_commit": runner_source_commit,
        "current_source_commit": current_source_commit,
        "runner_code_stale": code_stale,
        "current_agent": payload.get("current_agent", ""),
        "current_action": payload.get("current_action", ""),
        "agent_ledger_path": payload.get("agent_ledger_path", ""),
        "stdout_tail": payload.get("stdout_tail", ""),
        "stderr_tail": payload.get("stderr_tail", ""),
        "notify_failing": bool(payload.get("notify_failing")),
        "notification_level": payload.get("notification_level", ""),
        "notification_title": payload.get("notification_title", ""),
        "agent_ledger": ledger_summary,
        "orphan_processes": orphan_processes,
        "supervisor_active": supervisor_alive,
        "supervisor_owns_runner": supervisor_owns_runner,
        "supervisor_status": supervisor.get("status", ""),
        "supervisor_pid": supervisor.get("pid"),
        "supervisor_child_pid": supervisor.get("child_pid"),
        "supervisor_generation": supervisor.get("generation", ""),
        "owner_process_pid": supervisor.get("pid") if supervisor_owns_runner else None,
        "supervisor_restart_count": int(supervisor.get("restart_count") or 0),
        "supervisor_identical_failure_count": int(supervisor.get("identical_failure_count") or 0),
        "supervisor_latest_failure": supervisor.get("latest_failure") or supervisor.get("failure_detail") or {},
        "supervisor_recommended_action": supervisor.get("recommended_action", ""),
        "log_path": str(LOG_PATH),
        "heartbeat_path": str(heartbeat_path),
        "command": _display_command(),
        "next_action": next_action,
        "can_start_from_web": False,
        "can_stop_from_web": False,
    }


def _runner_operating_state(payload, ledger, active):
    if not active:
        return "stale_or_stopped"
    latest = ledger.get("latest_stage") if isinstance(ledger, dict) and isinstance(ledger.get("latest_stage"), dict) else {}
    current_agent = str(payload.get("current_agent") or latest.get("agent") or "").strip()
    stage_status = str(latest.get("status") or "").strip().lower()
    if current_agent and stage_status in {"running", "in_progress", "active"}:
        return "running_agent"
    if payload.get("last_mission_id") and (current_agent or stage_status in {"complete", "completed", "passed"}):
        return "between_stages"
    return "waiting_for_queue"


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
        "runner_source_commit": _current_git_commit(),
        "runner_source_branch": _current_git_branch(),
        "supervisor_generation": str(os.getenv("CHARLIE_SUPERVISOR_GENERATION") or ""),
    }
    for key in (
        "elapsed_seconds",
        "changed_files_count",
        "final_artifact_present",
        "execution_artifact",
        "agent_runner_version",
        "current_agent",
        "current_action",
        "agent_ledger_path",
        "stdout_tail",
        "stderr_tail",
        "notify_failing",
        "notification_level",
        "notification_title",
        "last_failure",
        "failure_class",
        "error_type",
        "marker_path",
        "recommended_action",
    ):
        if key in result:
            payload[key] = result.get(key)
    heartbeat_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def start_runner(status_override=None):
    status = status_override if isinstance(status_override, dict) else runner_status()
    if status["active"]:
        return {"success": True, "status": "runner_already_active", "runner": status}, 200
    if status.get("orphan_processes"):
        return {"success": False, "status": "runner_orphaned_existing_process", "runner": status}, 409
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    if SUPERVISOR_STOP_PATH.exists():
        SUPERVISOR_STOP_PATH.unlink()
    python_path = SUPERVISOR_COMMAND[0]
    if not Path(python_path).exists():
        python_path = sys.executable
    command = [python_path, *SUPERVISOR_COMMAND[1:]]
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
    RUNNER_DIR.mkdir(parents=True, exist_ok=True)
    SUPERVISOR_STOP_PATH.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    pids = [status.get("pid")]
    pids.append(status.get("supervisor_pid"))
    pids.extend(process.get("pid") for process in status.get("orphan_processes", []))
    pids = [int(pid) for pid in pids if str(pid or "").isdigit()]
    if not pids:
        return {"success": True, "status": "runner_not_started", "runner": status}, 200
    stopped = []
    try:
        for pid in sorted(set(pids)):
            _stop_process_tree(pid)
            stopped.append(pid)
    except OSError:
        if not stopped:
            return {"success": True, "status": "runner_already_stopped", "runner": status}, 200
    return {"success": True, "status": "runner_stop_requested", "pids": stopped}, 200


def _stop_process_tree(pid):
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, text=True, check=False, timeout=15)
        return
    os.kill(pid, signal.SIGTERM)


def cleanup_runner_environment(stop_stale=True, prune_worktrees=True):
    status = runner_status()
    actions = []
    stop_result = {}
    should_stop = (
        bool(stop_stale)
        and status.get("status") in {"runner_orphaned", "runner_code_stale", "runner_stale_or_stopped"}
        and (status.get("process_alive") or status.get("orphan_processes"))
    )
    if status.get("active"):
        actions.append({"action": "stop_runner", "status": "skipped_active_runner"})
    elif should_stop:
        stop_result, stop_status = stop_runner()
        actions.append({"action": "stop_runner", "status_code": stop_status, "result": stop_result})
    else:
        actions.append({"action": "stop_runner", "status": "not_required"})

    prune_result = {"status": "skipped"}
    if prune_worktrees:
        prune_result = _git_worktree_prune()
        actions.append({"action": "git_worktree_prune", "result": prune_result})

    prune_ok = prune_result.get("status") == "ok"
    return {
        "success": not any(
            int(action.get("status_code") or 200) >= 400
            for action in actions
            if isinstance(action, dict)
        ) and prune_ok,
        "status": "cleanup_complete" if prune_ok else "cleanup_partial_failure",
        "runner_before": status,
        "actions": actions,
        "execution_boundary": "Cleanup only stops stale/orphaned/code-stale runner processes and prunes git worktree metadata; it does not delete repo work or active review media.",
    }, 200 if prune_ok else 500


def _display_command(command=None):
    command = command or RUNNER_COMMAND
    return " ".join(command).replace(str(REPO_ROOT) + "\\", "")


def _current_git_commit():
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _current_git_branch():
    try:
        completed = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _git_worktree_prune():
    try:
        completed = subprocess.run(
            ["git", "worktree", "prune"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(REPO_ROOT),
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"status": "failed", "error_type": exc.__class__.__name__, "error": str(exc)[:500]}
    stderr = completed.stderr or ""
    partial_failure = "permission denied" in stderr.lower() or "failed to delete" in stderr.lower()
    return {
        "status": "partial_failure" if completed.returncode == 0 and partial_failure else "ok" if completed.returncode == 0 else "failed",
        "returncode": completed.returncode,
        "stdout_tail": (completed.stdout or "")[-1000:],
        "stderr_tail": stderr[-1000:],
    }


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return {}


def _execution_artifact_exists(path):
    raw_path = str(path or "").strip()
    if not raw_path:
        return False
    artifact_path = Path(raw_path)
    if not artifact_path.is_absolute():
        artifact_path = REPO_ROOT / artifact_path
    try:
        return artifact_path.exists() and artifact_path.stat().st_size > 0
    except OSError:
        return False


def _read_agent_ledger_summary(path):
    raw_path = str(path or "").strip()
    if not raw_path:
        return {}
    try:
        ledger_path = Path(raw_path).resolve()
        root = REPO_ROOT.resolve()
        if root not in ledger_path.parents and ledger_path != root:
            return {"status": "ledger_path_outside_repo"}
        ledger = _read_json(ledger_path)
    except (OSError, ValueError):
        return {"status": "ledger_unavailable"}
    stages = ledger.get("stages") if isinstance(ledger.get("stages"), list) else []
    latest = stages[-1] if stages else {}
    return {
        "version": ledger.get("version", ""),
        "execution_id": ledger.get("execution_id", ""),
        "status": ledger.get("status", ""),
        "last_progress_at": ledger.get("last_progress_at", ""),
        "blocked_agent": ledger.get("blocked_agent", ""),
        "blocked_reason": ledger.get("blocked_reason", ""),
        "backflow_events": ledger.get("backflow_events", [])[-5:] if isinstance(ledger.get("backflow_events"), list) else [],
        "latest_stage": {
            "agent": latest.get("agent", ""),
            "status": latest.get("status", ""),
            "attempt": latest.get("attempt", 1),
            "current_action": latest.get("current_action", ""),
            "commands_run": latest.get("commands_run", [])[-5:] if isinstance(latest.get("commands_run"), list) else [],
            "files_inspected": latest.get("files_inspected", [])[-8:] if isinstance(latest.get("files_inspected"), list) else [],
            "changed_files": latest.get("changed_files", [])[-8:] if isinstance(latest.get("changed_files"), list) else [],
            "stdout_tail": str(latest.get("stdout_tail", ""))[-800:],
            "stderr_tail": str(latest.get("stderr_tail", ""))[-800:],
            "quality_gate": latest.get("quality_gate", {}) if isinstance(latest.get("quality_gate"), dict) else {},
        },
    }


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
        # Scheduled tasks can run under a different Windows token. OpenProcess
        # may be denied even though the exact PID is alive, so use tasklist as
        # a read-only existence fallback before declaring the runner dead.
        return _pid_exists_windows_tasklist(pid)
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


def _pid_exists_windows_tasklist(pid, runner=subprocess.run):
    try:
        completed = runner(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            return False
        rows = list(csv.reader(str(completed.stdout or "").splitlines()))
        return any(len(row) > 1 and row[1].strip() == str(int(pid)) for row in rows)
    except (OSError, ValueError, subprocess.SubprocessError):
        return False


def _pid_descends_from(pid, ancestor_pid):
    try:
        pid = int(pid)
        ancestor_pid = int(ancestor_pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0 or ancestor_pid <= 0 or pid == ancestor_pid:
        return pid == ancestor_pid and pid > 0
    if os.name == "nt":
        script = (
            f"$current={pid}; $ancestor={ancestor_pid}; $seen=@{{}}; "
            "$rows=Get-CimInstance Win32_Process -ErrorAction SilentlyContinue; $parents=@{}; "
            "foreach($item in $rows){ $parents[[int]$item.ProcessId]=[int]$item.ParentProcessId }; "
            "for($i=0; $i -lt 12; $i++){ "
            "if($seen.ContainsKey($current)){ break }; $seen[$current]=$true; "
            "if(-not $parents.ContainsKey($current)){ break }; $parent=[int]$parents[$current]; "
            "if($parent -eq $ancestor){ Write-Output 'true'; exit 0 }; "
            "if($parent -le 0){ break }; $current=$parent }; Write-Output 'false'"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        return completed.returncode == 0 and completed.stdout.strip().lower().endswith("true")
    current = pid
    for _ in range(12):
        try:
            fields = Path(f"/proc/{current}/stat").read_text(encoding="utf-8").split()
            parent = int(fields[3])
        except (OSError, ValueError, IndexError):
            return False
        if parent == ancestor_pid:
            return True
        if parent <= 1 or parent == current:
            return False
        current = parent
    return False


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
