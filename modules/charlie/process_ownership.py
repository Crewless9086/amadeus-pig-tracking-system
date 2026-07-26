"""Fail-closed process ownership records and termination authorization."""

import hashlib
import json
import os
import subprocess
import time
from pathlib import Path


REQUIRED_IDENTITY_FIELDS = (
    "pid", "creation_time", "executable_path", "command_fingerprint",
    "parent_pid", "runner_generation", "mission_id", "execution_id", "ownership_type",
    "revision", "startup_nonce",
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


def make_ownership_record(
    process,
    runner_generation,
    mission_id,
    execution_id,
    ownership_type,
    revision=None,
    startup_nonce=None,
    process_role=None,
):
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
        "revision": str(revision or runner_generation or ""),
        "startup_nonce": str(startup_nonce or runner_generation or ""),
        "process_role": str(process_role or ownership_type or ""),
    }


def make_process_tree_record(root_record, member_records, runner_generation):
    """Persist one logical launcher/interpreter tree without raw commands."""
    root = dict(root_record) if isinstance(root_record, dict) else {}
    members = [
        dict(item) for item in (member_records or [])
        if isinstance(item, dict) and item.get("pid")
    ]
    if root and not any(item.get("pid") == root.get("pid") for item in members):
        members.insert(0, root)
    return {
        "version": "charlie_process_tree_v1",
        "runner_generation": str(runner_generation or ""),
        "root_pid": root.get("pid"),
        "root": root,
        "members": members,
    }


def validate_process_tree(tree, expected, inspect_process, current_pid=None, require_descendant=False):
    """Validate every identity and bind every interpreter to the launcher."""
    if not isinstance(tree, dict) or tree.get("version") != "charlie_process_tree_v1":
        return _deny("process_tree_metadata_missing")
    root = tree.get("root") if isinstance(tree.get("root"), dict) else {}
    members = tree.get("members") if isinstance(tree.get("members"), list) else []
    if not root or not members:
        return _deny("process_tree_metadata_incomplete")
    root_decision = validate_termination(root, expected, inspect_process, current_pid=current_pid)
    if not root_decision["authorized"]:
        return _deny(f"root_{root_decision['reason']}")
    root_pid = int(root["pid"])
    validated = []
    for member in members:
        decision = validate_termination(member, expected, inspect_process, current_pid=current_pid)
        if not decision["authorized"]:
            return _deny(f"member_{member.get('pid')}_{decision['reason']}")
        current = inspect_process(int(member["pid"]))
        if int(member["pid"]) != root_pid:
            ancestry = current.get("ancestry") if isinstance(current, dict) else []
            ancestor_pids = {
                int(item.get("pid") or -1)
                for item in ancestry or []
                if isinstance(item, dict)
            }
            if root_pid not in ancestor_pids:
                return _deny(f"member_{member.get('pid')}_not_descendant_of_root")
        validated.append(int(member["pid"]))
    if require_descendant and len(set(validated)) < 2:
        return _deny("interpreter_descendant_missing")
    return {
        "authorized": True,
        "reason": "logical_process_tree_identity_match",
        "pid": root_pid,
        "member_pids": sorted(set(validated)),
    }


def validate_bootstrap_tree(
    tree,
    *,
    generation,
    revision,
    startup_nonce,
    expected_root_parent_pid=None,
    require_interpreter=True,
):
    """Validate a controller-observed startup tree without trusting its child."""
    if not isinstance(tree, dict) or tree.get("version") != "charlie_process_tree_v1":
        return _deny("ownership_identity_incomplete:process_tree")
    root = tree.get("root") if isinstance(tree.get("root"), dict) else {}
    members = tree.get("members") if isinstance(tree.get("members"), list) else []
    if not root:
        return _deny("ownership_identity_incomplete:root")
    if not members:
        return _deny("ownership_identity_incomplete:members")
    for label, record in [("root", root), *[(f"member_{index}", item) for index, item in enumerate(members)]]:
        if not isinstance(record, dict):
            return _deny(f"ownership_identity_incomplete:{label}")
        for field in REQUIRED_IDENTITY_FIELDS:
            if record.get(field) in (None, ""):
                return _deny(f"ownership_identity_incomplete:{label}.{field}")
        if not str(record.get("process_role") or ""):
            return _deny(f"ownership_identity_incomplete:{label}.process_role")
        if str(record.get("runner_generation") or "") != str(generation or ""):
            return _deny(f"stale_generation:{label}")
        if str(record.get("revision") or "") != str(revision or ""):
            return _deny(f"revision_mismatch:{label}")
        if str(record.get("startup_nonce") or "") != str(startup_nonce or ""):
            return _deny(f"startup_nonce_mismatch:{label}")
    try:
        root_pid = int(root["pid"])
        root_parent_pid = int(root["parent_pid"])
    except (TypeError, ValueError):
        return _deny("ownership_identity_incomplete:root.pid")
    if expected_root_parent_pid is not None and root_parent_pid != int(expected_root_parent_pid):
        return _deny("root_parent_pid_mismatch")
    member_pids = {int(item["pid"]) for item in members}
    if len(member_pids) != len(members):
        return _deny("ownership_identity_incomplete:duplicate_pid")
    if root_pid not in member_pids:
        return _deny("ownership_identity_incomplete:root_member")
    descendants = [item for item in members if int(item["pid"]) != root_pid]
    if require_interpreter and not descendants:
        return _deny("ownership_identity_incomplete:interpreter")
    known_pids = set(member_pids)
    for member in descendants:
        if int(member["parent_pid"]) not in known_pids:
            return _deny(f"parentage_mismatch:member_{member['pid']}")
    return {
        "authorized": True,
        "reason": "ownership_bootstrap_identity_complete",
        "pid": root_pid,
        "member_pids": sorted(member_pids),
        "generation": str(generation),
        "revision": str(revision),
        "startup_nonce": str(startup_nonce),
    }


def validate_live_bootstrap_tree(tree, *, generation, revision, startup_nonce):
    """Revalidate a persisted bootstrap tree against current OS identities."""
    structural = validate_bootstrap_tree(
        tree,
        generation=generation,
        revision=revision,
        startup_nonce=startup_nonce,
        require_interpreter=True,
    )
    if not structural["authorized"]:
        return structural
    members = tree.get("members") or []
    root_pid = int((tree.get("root") or {}).get("pid") or -1)
    for index, record in enumerate(members):
        current = inspect_process(record.get("pid"))
        label = f"member_{index}"
        if not isinstance(current, dict) or current.get("inspection_complete") is False:
            return _deny(f"live_identity_inspection_incomplete:{label}")
        checks = {
            "pid": int(current.get("pid") or -1) == int(record.get("pid") or -2),
            "creation_time": str(current.get("creation_time") or "") == str(record.get("creation_time") or ""),
            "executable_path": _normalize_path(current.get("executable_path")) == _normalize_path(record.get("executable_path")),
            "command_fingerprint": normalize_command_fingerprint(
                current.get("command_line") or current.get("command")
            ) == str(record.get("command_fingerprint") or ""),
            "parent_pid": int(current.get("parent_pid") or -1) == int(record.get("parent_pid") or -2),
        }
        mismatch = next((field for field, matches in checks.items() if not matches), "")
        if mismatch:
            return _deny(f"live_identity_{mismatch}_mismatch:{label}")
        if int(record.get("pid") or -1) != root_pid:
            ancestry = current.get("ancestry")
            if not isinstance(ancestry, list) or root_pid not in {
                int(item.get("pid") or -1)
                for item in ancestry
                if isinstance(item, dict)
            }:
                return _deny(f"live_identity_parentage_mismatch:{label}")
    return {
        **structural,
        "reason": "live_ownership_bootstrap_identity_match",
    }


def observe_process_tree(
    root_pid,
    *,
    generation,
    revision,
    startup_nonce,
    expected_script="",
    expected_root_executable="",
    process_role_prefix="process",
    timeout_seconds=10,
    poll_seconds=0.1,
    sleep_fn=time.sleep,
):
    """Observe a launcher/interpreter tree externally from its controller."""
    deadline = time.monotonic() + max(0, float(timeout_seconds))
    last_reason = "ownership_identity_incomplete:root"
    while time.monotonic() <= deadline:
        rows = _inspect_process_descendants(root_pid)
        records = [
            make_ownership_record(
                row,
                generation,
                "charlie-control",
                generation,
                "charlie_runner",
                revision=revision,
                startup_nonce=startup_nonce,
                process_role=(
                    f"{process_role_prefix}_launcher"
                    if int(row.get("pid") or -1) == int(root_pid)
                    else f"{process_role_prefix}_interpreter"
                ),
            )
            for row in rows
            if isinstance(row, dict)
        ]
        root = next((item for item in records if int(item.get("pid") or -1) == int(root_pid)), {})
        tree = make_process_tree_record(root, records, generation)
        decision = validate_bootstrap_tree(
            tree,
            generation=generation,
            revision=revision,
            startup_nonce=startup_nonce,
            expected_root_parent_pid=os.getpid(),
            require_interpreter=True,
        )
        if decision["authorized"]:
            if str(root.get("process_role") or "") != f"{process_role_prefix}_launcher":
                last_reason = "root_process_role_mismatch"
                sleep_fn(poll_seconds)
                continue
            if any(
                str(item.get("process_role") or "") != f"{process_role_prefix}_interpreter"
                for item in records
                if int(item.get("pid") or -1) != int(root_pid)
            ):
                last_reason = "interpreter_process_role_mismatch"
                sleep_fn(poll_seconds)
                continue
            root_row = next(
                (row for row in rows if int(row.get("pid") or -1) == int(root_pid)),
                {},
            )
            if expected_root_executable and _normalize_path(
                root_row.get("executable_path")
            ) != _normalize_path(expected_root_executable):
                last_reason = "root_executable_identity_mismatch"
                sleep_fn(poll_seconds)
                continue
            if expected_script:
                missing_role = next(
                    (
                        row for row in rows
                        if str(expected_script).casefold()
                        not in str(row.get("command_line") or "").casefold()
                    ),
                    None,
                )
                if missing_role is not None:
                    last_reason = f"command_role_identity_mismatch:{missing_role.get('pid')}"
                else:
                    return {"success": True, "tree": tree, "validation": decision}
            else:
                return {"success": True, "tree": tree, "validation": decision}
        else:
            last_reason = decision["reason"]
        sleep_fn(poll_seconds)
    return {"success": False, "reason": last_reason, "tree": tree if "tree" in locals() else {}}


def _inspect_process_descendants(root_pid):
    if os.name != "nt":
        root = inspect_process(root_pid)
        if not isinstance(root, dict):
            return []
        rows = [root]
        for proc_dir in Path("/proc").iterdir():
            if not proc_dir.name.isdigit() or int(proc_dir.name) == int(root_pid):
                continue
            try:
                row = inspect_process(int(proc_dir.name))
            except (OSError, ValueError, TypeError):
                continue
            ancestry = row.get("ancestry") if isinstance(row, dict) else []
            if any(int(item.get("pid") or -1) == int(root_pid) for item in ancestry if isinstance(item, dict)):
                rows.append(row)
        return rows
    all_rows = _windows_process_snapshot()
    ids = {int(root_pid)}
    changed = True
    while changed:
        changed = False
        for row in all_rows:
            if (
                int(row.get("parent_pid") or -1) in ids
                and int(row.get("pid") or -1) not in ids
            ):
                ids.add(int(row["pid"]))
                changed = True
    return [row for row in all_rows if int(row.get("pid") or -1) in ids]


def validate_termination(
    record,
    expected,
    inspect_process,
    current_pid=None,
    allow_current_descendant=False,
):
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
    if current.get("inspection_complete") is False:
        return _deny("process_inspection_failed")
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
    if _protected(current):
        return _deny("protected_process_boundary")
    protected_pids = {int(current_pid or os.getpid())}
    for item in current.get("current_process_ancestry", []):
        if isinstance(item, dict) and str(item.get("pid") or "").isdigit():
            protected_pids.add(int(item["pid"]))
    ancestry_pids = {
        int(item.get("pid") or -1)
        for item in ancestry
        if isinstance(item, dict)
    }
    if allow_current_descendant:
        starter_pid = int(current_pid or os.getpid())
        ancestry_before_starter = []
        for item in ancestry:
            if not isinstance(item, dict):
                continue
            if int(item.get("pid") or -1) == starter_pid:
                break
            ancestry_before_starter.append(item)
        if any(_protected(item) for item in ancestry_before_starter):
            return _deny("protected_process_boundary")
    elif any(_protected(item) for item in ancestry if isinstance(item, dict)):
        return _deny("protected_process_boundary")
    if pid in protected_pids:
        return _deny("current_process_ancestry")
    intersects_current = bool(ancestry_pids & protected_pids)
    if intersects_current and not allow_current_descendant:
        return _deny("current_process_ancestry")
    if allow_current_descendant and int(current_pid or os.getpid()) not in ancestry_pids:
        return _deny("not_current_process_descendant")
    if record["ownership_type"] not in {"charlie_runner", "charlie_worker", "charlie_agent"}:
        return _deny("ownership_ambiguous")
    return {"authorized": True, "reason": "identity_match", "pid": pid}


def inspect_process(pid):
    """Inspect a process and its ancestry. Any partial result is unusable."""
    if os.name != "nt":
        return _inspect_proc(pid)
    try:
        rows = _windows_process_snapshot()
        by_pid = {int(row["pid"]): row for row in rows if row.get("pid")}
        target = dict(by_pid.get(int(pid)) or {})
        if not target:
            return None
        target["ancestry"] = _snapshot_ancestry(by_pid, target.get("parent_pid"))
        target["current_process_ancestry"] = _snapshot_ancestry(
            by_pid, os.getpid(), include_start=True
        )
        if not target["current_process_ancestry"]:
            return None
        target["inspection_complete"] = True
        return target
    except (OSError, subprocess.SubprocessError, ValueError, TypeError, json.JSONDecodeError):
        # Process inspection is a safety aid, never a reason to terminate the
        # supervisor.  Returning no identity keeps termination fail-closed:
        # make_ownership_record produces an unusable record and every later
        # kill authorization is refused until a complete inspection succeeds.
        return None


def _windows_process_snapshot():
    script = (
        "Get-CimInstance Win32_Process|ForEach-Object{"
        "[pscustomobject]@{pid=[int]$_.ProcessId;parent_pid=[int]$_.ParentProcessId;"
        "creation_time=[string]$_.CreationDate;executable_path=[string]$_.ExecutablePath;"
        "command_line=[string]$_.CommandLine;name=[string]$_.Name}}|"
        "ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=8, check=False,
    )
    if result.returncode or not str(result.stdout or "").strip():
        return []
    rows = json.loads(result.stdout)
    rows = [rows] if isinstance(rows, dict) else rows
    return rows if isinstance(rows, list) else []


def _snapshot_ancestry(by_pid, start_pid, include_start=False):
    result = []
    current = int(start_pid or 0)
    seen = set()
    first = True
    while current > 0 and current not in seen:
        seen.add(current)
        row = by_pid.get(current)
        if not isinstance(row, dict):
            break
        if include_start or not first:
            result.append(dict(row))
        elif not include_start:
            result.append(dict(row))
        current = int(row.get("parent_pid") or 0)
        first = False
    return result


def _inspect_proc(pid):
    target = _proc_row(pid)
    ancestry, ancestry_complete = _proc_ancestry(target["parent_pid"])
    current_ancestry, current_complete = _proc_ancestry(os.getpid(), include_start=True)
    target["ancestry"] = ancestry
    target["current_process_ancestry"] = current_ancestry
    target["inspection_complete"] = bool(
        target.pop("row_complete", True) and ancestry_complete and current_complete
    )
    return target


def _current_ancestry_windows():
    rows = _windows_process_snapshot()
    by_pid = {int(row["pid"]): row for row in rows if row.get("pid")}
    ancestry = _snapshot_ancestry(by_pid, os.getpid(), include_start=True)
    if not ancestry:
        raise OSError("current process ancestry inspection failed")
    return ancestry


def _proc_row(pid):
    pid = int(pid)
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    row_complete = True
    try:
        command = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode().strip()
    except OSError:
        command = ""
        row_complete = False
    try:
        executable_path = str(Path(f"/proc/{pid}/exe").resolve(strict=True))
    except OSError:
        executable_path = ""
        row_complete = False
    try:
        name = Path(f"/proc/{pid}/comm").read_text(encoding="utf-8").strip()
    except OSError:
        name = ""
        row_complete = False
    return {"pid": pid, "parent_pid": int(stat[3]), "creation_time": stat[21],
            "executable_path": executable_path, "command_line": command,
            "name": name, "row_complete": row_complete}


def _proc_ancestry(pid, include_start=False):
    rows, seen, complete = [], set(), True
    current = int(pid)
    while current > 0 and current not in seen:
        seen.add(current)
        try:
            row = _proc_row(current)
        except OSError:
            complete = False
            break
        if not row.pop("row_complete", True):
            complete = False
        if include_start or current != int(pid):
            rows.append(row)
        elif not include_start:
            rows.append(row)
        current = int(row.get("parent_pid") or 0)
    return rows, complete


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
