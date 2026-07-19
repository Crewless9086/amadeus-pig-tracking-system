"""Fail-closed process ownership records and termination authorization."""

import hashlib
import json
import os
import subprocess
from pathlib import Path


REQUIRED_IDENTITY_FIELDS = (
    "pid", "creation_time", "executable_path", "command_fingerprint",
    "parent_pid", "runner_generation", "mission_id", "execution_id", "ownership_type",
)

TERMINATION_ENABLE_ENV = "CHARLIE_PROCESS_TERMINATION_ENABLED"
TERMINATION_ENABLE_VALUE = "I_UNDERSTAND_THIS_CAN_TERMINATE_PROCESSES"
TEST_ISOLATION_ENV = "CHARLIE_TEST_ISOLATION"


def process_termination_enabled(environ=None):
    """Require an explicit capability grant in addition to ownership proof."""
    values = os.environ if environ is None else environ
    if str(values.get(TEST_ISOLATION_ENV) or "") == "1":
        return False
    return str(values.get(TERMINATION_ENABLE_ENV) or "") == TERMINATION_ENABLE_VALUE


def normalize_command_fingerprint(command):
    normalized = " ".join(str(command or "").split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest() if normalized else ""


def make_ownership_record(process, runner_generation, mission_id, execution_id, ownership_type):
    if not isinstance(process, dict):
        return {}
    command = process.get("command_line") or process.get("command")
    return {
        "pid": process.get("pid"),
        "creation_time": str(process.get("creation_time") or ""),
        "executable_path": _normalize_path(process.get("executable_path")),
        "command_fingerprint": normalize_command_fingerprint(command),
        "parent_pid": process.get("parent_pid"),
        "runner_generation": str(runner_generation or ""),
        "mission_id": str(mission_id or ""),
        "execution_id": str(execution_id or ""),
        "ownership_type": str(ownership_type or ""),
    }


def validate_termination(record, expected, inspect_process, current_pid=None):
    """Authorize only a complete, exact, non-interactive disposable identity."""
    if not isinstance(record, dict):
        return _deny("corrupt_metadata")
    if any(field not in record or record.get(field) in (None, "") for field in REQUIRED_IDENTITY_FIELDS):
        return _deny("missing_identity_metadata")
    try:
        pid = int(record["pid"])
        parent_pid = int(record["parent_pid"])
    except (TypeError, ValueError):
        return _deny("corrupt_metadata")
    if pid <= 0 or parent_pid < 0:
        return _deny("corrupt_metadata")
    expected = expected if isinstance(expected, dict) else {}
    for field in ("runner_generation", "mission_id", "execution_id", "ownership_type"):
        if not expected.get(field) or record.get(field) != expected.get(field):
            return _deny(f"{field}_mismatch")
    try:
        current = inspect_process(pid)
    except Exception:
        return _deny("process_inspection_failed")
    if not isinstance(current, dict):
        return _deny("pid_not_found")
    if int(current.get("pid") or -1) != pid:
        return _deny("pid_reused")
    if str(current.get("creation_time") or "") != str(record["creation_time"]):
        return _deny("creation_time_mismatch")
    if _normalize_path(current.get("executable_path")) != _normalize_path(record["executable_path"]):
        return _deny("executable_mismatch")
    if normalize_command_fingerprint(current.get("command_line") or current.get("command")) != record["command_fingerprint"]:
        return _deny("command_fingerprint_mismatch")
    if int(current.get("parent_pid") or -1) != parent_pid:
        return _deny("parent_pid_mismatch")
    ancestry = current.get("ancestry")
    if not isinstance(ancestry, list):
        return _deny("process_inspection_failed")
    if _protected(current) or any(_protected(item) for item in ancestry if isinstance(item, dict)):
        return _deny("protected_process_boundary")
    protected_pids = {int(current_pid or os.getpid())}
    for item in current.get("current_process_ancestry", []):
        if isinstance(item, dict) and str(item.get("pid") or "").isdigit():
            protected_pids.add(int(item["pid"]))
    if pid in protected_pids or any(int(item.get("pid") or -1) in protected_pids for item in ancestry if isinstance(item, dict)):
        return _deny("current_process_ancestry")
    if record["ownership_type"] not in {"charlie_runner", "charlie_worker", "charlie_agent"}:
        return _deny("ownership_ambiguous")
    return {"authorized": True, "reason": "identity_match", "pid": pid}


def inspect_process(pid):
    """Inspect a process and its ancestry. Any partial result is unusable."""
    if os.name != "nt":
        return _inspect_proc(pid)
    script = (
        "$rows=@();$p=Get-CimInstance Win32_Process -Filter 'ProcessId = " + str(int(pid)) + "';"
        "while($p){$rows+=@{pid=$p.ProcessId;parent_pid=$p.ParentProcessId;creation_time=[string]$p.CreationDate;"
        "executable_path=[string]$p.ExecutablePath;command_line=[string]$p.CommandLine;name=[string]$p.Name};"
        "if(!$p.ParentProcessId){break};$p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$p.ParentProcessId)};"
        "$rows|ConvertTo-Json -Compress"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=8, check=False)
    if result.returncode or not result.stdout.strip():
        return None
    rows = json.loads(result.stdout)
    if isinstance(rows, dict):
        rows = [rows]
    target = dict(rows[0])
    target["ancestry"] = rows[1:]
    target["current_process_ancestry"] = _current_ancestry_windows()
    return target


def _inspect_proc(pid):
    target = _proc_row(pid)
    target["ancestry"] = _proc_ancestry(target["parent_pid"])
    target["current_process_ancestry"] = _proc_ancestry(os.getpid(), include_start=True)
    return target


def _current_ancestry_windows():
    script = (
        "$rows=@();$p=Get-CimInstance Win32_Process -Filter 'ProcessId = " + str(os.getpid()) + "';"
        "while($p){$rows+=@{pid=$p.ProcessId;parent_pid=$p.ParentProcessId;name=[string]$p.Name;"
        "executable_path=[string]$p.ExecutablePath;command_line=[string]$p.CommandLine};"
        "if(!$p.ParentProcessId){break};$p=Get-CimInstance Win32_Process -Filter ('ProcessId = '+$p.ParentProcessId)};"
        "$rows|ConvertTo-Json -Compress"
    )
    result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True, timeout=8, check=False)
    if result.returncode or not result.stdout.strip():
        raise OSError("current process ancestry inspection failed")
    rows = json.loads(result.stdout)
    return [rows] if isinstance(rows, dict) else rows


def _proc_row(pid):
    pid = int(pid)
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode().strip()
    return {"pid": pid, "parent_pid": int(stat[3]), "creation_time": stat[21],
            "executable_path": str(Path(f"/proc/{pid}/exe").resolve()), "command_line": command,
            "name": Path(f"/proc/{pid}/comm").read_text().strip()}


def _proc_ancestry(pid, include_start=False):
    rows, seen = [], set()
    current = int(pid)
    while current > 0 and current not in seen:
        seen.add(current)
        row = _proc_row(current)
        if include_start or current != int(pid):
            rows.append(row)
        elif not include_start:
            rows.append(row)
        current = int(row.get("parent_pid") or 0)
    return rows


def _protected(process):
    name = Path(str(process.get("name") or process.get("executable_path") or "")).name.casefold()
    command = str(process.get("command_line") or process.get("command") or "").casefold()
    if name == "cursor.exe" or "cursor" in command:
        return True
    if name in {"conhost.exe", "windowsterminal.exe"}:
        return True
    if name in {"powershell.exe", "pwsh.exe", "cmd.exe"}:
        return not any(flag in command for flag in ("-noninteractive", "-file"))
    if name in {"codex.exe", "codex.cmd"}:
        return "exec" not in command or "--json" not in command
    return False


def _normalize_path(value):
    return os.path.normcase(os.path.normpath(str(value or "").strip())) if value else ""


def _deny(reason):
    return {"authorized": False, "reason": reason}
