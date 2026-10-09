"""Four opt-in lifecycle tests in disposable hosted Windows jobs, never production."""
from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
from ctypes import wintypes
import functools
import json
import os
from pathlib import Path, PureWindowsPath
import re
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch
import uuid

SELECTORS = (
    "tests.test_charlie_runner_control.CharlieRunnerControlTests.test_windows_exited_launcher_still_contains_unobserved_child",
    "tests.test_charlie_runner_control.CharlieRunnerControlTests.test_windows_failed_start_leaves_zero_observed_processes",
    "tests.test_charlie_runner_control.CharlieRunnerControlTests.test_windows_governed_start_refuses_protected_ancestry_stop",
    "tests.test_charlie_runner_supervisor.CharlieRunnerSupervisorTests.test_supervisor_script_loads_standalone_outside_repo_cwd",
)
JOB_ENV = "CHARLIE_WINDOWS_TEST_JOB_NAME"
KILL_ON_CLOSE = 0x2000
BREAKAWAY = 0x800 | 0x1000
TEST_TIMEOUT_SECONDS = 180
BASE_PLATFORM_ENV = frozenset({"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "RUNNER_TEMP", "GITHUB_ACTIONS", "RUNNER_OS"})
NATIVE_PLATFORM_ENV = frozenset({"USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "SYSTEMDRIVE", "PROGRAMFILES"})

PLATFORM_GROUPS = {
    "identity": frozenset({"USERNAME", "USERDOMAIN", "USERDOMAIN_ROAMINGPROFILE", "COMPUTERNAME",
        "HOMEDRIVE", "HOMEPATH", "ALLUSERSPROFILE", "PUBLIC"}),
    "architecture": frozenset({"OS", "PROCESSOR_ARCHITECTURE", "PROCESSOR_ARCHITEW6432", "NUMBER_OF_PROCESSORS"}),
    "installation": frozenset({"PROGRAMFILES(X86)", "PROGRAMW6432", "COMMONPROGRAMFILES",
        "COMMONPROGRAMFILES(X86)", "COMMONPROGRAMW6432"}),
}
EXPANDED_PLATFORM_ENV = frozenset().union(*PLATFORM_GROUPS.values())


def worker_environment(source, root, job_name):
    env = {k: v for k, v in source.items() if k.upper() in BASE_PLATFORM_ENV | NATIVE_PLATFORM_ENV | EXPANDED_PLATFORM_ENV}
    system_root = next((v for k, v in env.items() if k.upper() == "SYSTEMROOT"), None)
    if not system_root:
        raise RuntimeError("system_root_required")
    # Seed built-in Windows modules; do not inherit parent PS7/user module entries.
    env["PSModulePath"] = str(PureWindowsPath(system_root) / "System32/WindowsPowerShell/v1.0/Modules")
    env.update({JOB_ENV: job_name, "TEMP": str(root), "TMP": str(root), "PYTHONDONTWRITEBYTECODE": "1", "PYTHON_DOTENV_DISABLED": "1", "DATABASE_URL": ""})
    return env


OMISSION_CATALOG = frozenset(('CI', 'CLIENTNAME', 'GITHUB_ACTION', 'GITHUB_ACTION_PATH', 'GITHUB_ACTION_REPOSITORY', 'GITHUB_ACTOR', 'GITHUB_ACTOR_ID', 'GITHUB_BASE_REF', 'GITHUB_ENV', 'GITHUB_EVENT_NAME', 'GITHUB_EVENT_PATH', 'GITHUB_HEAD_REF', 'GITHUB_JOB', 'GITHUB_OUTPUT', 'GITHUB_PATH', 'GITHUB_REF', 'GITHUB_REF_NAME', 'GITHUB_REF_PROTECTED', 'GITHUB_REF_TYPE', 'GITHUB_REPOSITORY', 'GITHUB_REPOSITORY_ID', 'GITHUB_REPOSITORY_OWNER', 'GITHUB_REPOSITORY_OWNER_ID', 'GITHUB_RETENTION_DAYS', 'GITHUB_RUN_ATTEMPT', 'GITHUB_RUN_ID', 'GITHUB_RUN_NUMBER', 'GITHUB_SHA', 'GITHUB_STATE', 'GITHUB_STEP_SUMMARY', 'GITHUB_TRIGGERING_ACTOR', 'GITHUB_WORKFLOW', 'GITHUB_WORKFLOW_REF', 'GITHUB_WORKFLOW_SHA', 'GITHUB_WORKSPACE', 'HOME', 'IMAGEOS', 'IMAGEVERSION', 'LANG', 'LC_ALL', 'LC_CTYPE', 'LOGONSERVER', 'PROCESSOR_IDENTIFIER', 'PROCESSOR_LEVEL', 'PROCESSOR_REVISION', 'PROMPT', 'RUNNER_ARCH', 'RUNNER_DEBUG', 'RUNNER_ENVIRONMENT', 'RUNNER_NAME', 'RUNNER_TOOL_CACHE', 'RUNNER_WORKSPACE', 'SESSIONNAME', 'TERM', 'TERM_PROGRAM'))
PRESENCE_ONLY_NAMES = ('ALL_PROXY', 'CORECLR_ENABLE_PROFILING', 'CORECLR_PROFILER', 'CORECLR_PROFILER_PATH', 'COR_ENABLE_PROFILING', 'COR_PROFILER', 'COR_PROFILER_PATH', 'DOTNET_MULTILEVEL_LOOKUP', 'DOTNET_ROLL_FORWARD', 'DOTNET_ROOT', 'DOTNET_ROOT_X64', 'DOTNET_STARTUP_HOOKS', 'HTTPS_PROXY', 'HTTP_PROXY', 'NO_PROXY', 'POWERSHELL_DIAGNOSTICS_OPTOUT', 'POWERSHELL_DISTRIBUTION_CHANNEL', 'POWERSHELL_TELEMETRY_OPTOUT', 'POWERSHELL_UPDATECHECK', 'PSDISABLEMODULEANALYSISCACHECLEANUP', 'PSEXECUTIONPOLICYPREFERENCE', 'PSMODULEANALYSISCACHEPATH', 'PSMODULEPATH', 'WINPSMODULEPATH', '__PSLOCKDOWNPOLICY')
PRESENCE_ONLY_PREFIXES = ('COMPLUS_', 'DOTNET_', 'COR_', 'CORECLR_')
MAX_PARENT_PROBES = 18
MAX_SPLIT_PROBES = 12
MAX_DIAGNOSTIC_BYTES = 24000


def diagnose_environment_omissions(expanded, root, ambient):
    """Bounded parent-only removal experiment; it never selects a worker profile."""
    _report_root(str(root))
    ambient = dict(ambient)
    ambient_names = {k.upper() for k in ambient}
    worker_names = {k.upper() for k in expanded}
    if len(ambient_names) != len(ambient) or len(worker_names) != len(expanded):
        raise RuntimeError("duplicate_environment_names")
    fixed_names = {"PSMODULEPATH", "TEMP", "TMP", JOB_ENV,
        "PYTHONDONTWRITEBYTECODE", "PYTHON_DOTENV_DISABLED", "DATABASE_URL"}
    fixed = {k: v for k, v in expanded.items() if k.upper() in fixed_names}
    if {k.upper() for k in fixed} != fixed_names:
        raise RuntimeError("fixed_override_family_required")
    without = lambda source, names: {k: v for k, v in source.items() if k.upper() not in names}
    combined = {**without(ambient, fixed_names), **fixed}
    omitted = ambient_names - worker_names
    eligible = sorted(omitted & OMISSION_CATALOG)
    if len(eligible) > 64:
        raise RuntimeError("omission_catalog_bound_exceeded")
    report = {"status": "not_classified", "eligible_names": eligible,
        "inventory": {"ambient_name_count": len(ambient_names), "worker_name_count": len(worker_names),
            "omitted_name_count": len(omitted), "eligible_omitted_name_count": len(eligible),
            "outside_catalog_omitted_name_count": len(omitted - OMISSION_CATALOG),
            "fixed_presence": {name: {"ambient": name in ambient_names, "worker": name in worker_names}
                for name in PRESENCE_ONLY_NAMES},
            "prefix_counts": {prefix: {"ambient": sum(k.startswith(prefix) for k in ambient_names),
                "worker": sum(k.startswith(prefix) for k in worker_names)} for prefix in PRESENCE_ONLY_PREFIXES}},
        "probes": [], "split_probes": 0, "maximum_calls": MAX_PARENT_PROBES,
        "maximum_query_seconds": MAX_PARENT_PROBES * 8}
    def finish(status):
        report["status"] = status
        report["calls"] = len(report["probes"])
        if len(json.dumps(report).encode("utf-8")) > MAX_DIAGNOSTIC_BYTES:
            raise RuntimeError("omission_report_size_exceeded")
        return report
    def probe(label, environment, removed=()):
        if len(report["probes"]) >= MAX_PARENT_PROBES:
            raise RuntimeError("parent_probe_budget_exhausted")
        result = probe_cim_module_context(environment)
        report["probes"].append({"label": label, "removed_names": list(removed), "result": result})
        return result
    def failed_as_before(result):
        item = result.get("automatic", {})
        return (item.get("success") is False and item.get("exited_zero") is False
            and item.get("error_type") == "TimeoutExpired" and item.get("output_valid") is True
            and item.get("markers") == [{"stage": "started", "count": 0}])
    baseline = probe("ambient_reference", ambient)
    all_fixed = probe("ambient_all_fixed_overrides", combined)
    constructed = probe("constructed_reference", expanded)
    if not owned_automatic_cim_passed(baseline):
        return finish("invalid_ambient_control")
    if not owned_automatic_cim_passed(all_fixed):
        return finish("combined_override_failure")
    if not failed_as_before(constructed):
        return finish("constructed_failure_not_reproduced")
    if not eligible:
        return finish("empty_reviewed_catalog")
    current = eligible
    removed = probe("remove_all_eligible", without(combined, set(current)), current)
    if not failed_as_before(removed):
        return finish("no_reproduction_in_reviewed_catalog" if owned_automatic_cim_passed(removed)
            else "inconclusive_catalog_failure")
    reason = "single_candidate"
    while len(current) > 1:
        if report["split_probes"] >= MAX_SPLIT_PROBES:
            reason = "budget_exhausted_subset"; break
        middle = len(current) // 2
        halves = (current[:middle], current[middle:])
        reduced = False
        for half in halves:
            if report["split_probes"] >= MAX_SPLIT_PROBES:
                reason = "budget_exhausted_subset"; break
            report["split_probes"] += 1
            result = probe("split_" + str(report["split_probes"]), without(combined, set(half)), half)
            if failed_as_before(result):
                current = half; reduced = True; break
            if not owned_automatic_cim_passed(result):
                reason = "inconclusive_split"; break
        else:
            reason = "interacting_subset"
        if not reduced:
            break
    report["failing_subset"] = current
    report["search_stop"] = reason
    repeated = probe("repeat_candidate_removal", without(combined, set(current)), current)
    restored = probe("restored_combined_control", combined)
    report["removal_reproduced"] = failed_as_before(repeated)
    report["restored_control_passed"] = owned_automatic_cim_passed(restored)
    if not report["removal_reproduced"] or not report["restored_control_passed"]:
        return finish("reversal_not_confirmed")
    return finish("observed_single_name_removal_dependency" if len(current) == 1 else reason)


def process_policy_context(source, worker):
    """Classify an existing parent policy without forwarding or changing its value."""
    values = [v for k, v in source.items() if k.upper() == "PSEXECUTIONPOLICYPREFERENCE"]
    known = {v.lower(): v for v in ("AllSigned", "Bypass", "Default", "RemoteSigned", "Restricted", "Undefined", "Unrestricted")}
    value = values[0] if len(values) == 1 else None
    label = known.get(value.lower(), "unrecognized") if isinstance(value, str) else "unrecognized"
    return {"ambient_present": bool(values), "ambient_label": label if values else None,
        "worker_inherits": any(k.upper() == "PSEXECUTIONPOLICYPREFERENCE" for k in worker)}


def cim_module_specs():
    """Automatic module loading and narrow local CIM, identical in every bounded parent comparison."""
    prefix = (
        "$ErrorActionPreference='Stop';"
        "function Emit([string]$stage,[long]$count){"
        "[Console]::Out.WriteLine('CHARLIE_PHASE|'+$stage+'|'+$count);[Console]::Out.Flush()};"
        "Emit 'started' 0;"
    )
    query = (
        "$rows=@(Get-CimInstance Win32_Process -Filter ('ProcessId='+$PID));"
        "Emit 'acquired' $rows.Count;Emit 'completed' 0;"
    )
    automatic = prefix + (
        "$command=@(Get-Command -Name Get-CimInstance -CommandType Cmdlet -ErrorAction Stop);"
        "if($command.Count -ne 1 -or $command[0].ModuleName -ne 'CimCmdlets'){throw 'unexpected_cim_command'};"
        "Emit 'command_resolved' 1;"
    ) + query
    return (("automatic", automatic, ("started", "command_resolved", "acquired", "completed")),)


def parse_phase_markers(output, expected):
    """Reject unexpected/oversized data without retaining it, including timeout output."""
    if not isinstance(output, (str, bytes)) or len(output) > 4096:
        return [], False
    if isinstance(output, bytes):
        try:
            output = output.decode("ascii")
        except UnicodeDecodeError:
            return [], False
    markers = []
    for line in output.splitlines():
        match = re.fullmatch(r"CHARLIE_PHASE\|([a-z_]+)\|([0-9]{1,10})", line)
        if not match or len(markers) >= len(expected) or match[1] != expected[len(markers)]:
            return [], False
        count = int(match[2])
        if count > 1_000_000_000 or (match[1] in {"started", "completed"} and count != 0):
            return [], False
        markers.append({"stage": match[1], "count": count})
    return markers, True


def probe_cim_module_context(environment):
    """One single-attempt read-only probe; None inherits only the parent's environment."""
    report = {}
    for label, script, expected in cim_module_specs():
        started = time.monotonic()
        item = {"success": False, "exited_zero": False, "error_type": None}
        output = ""
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=8, check=False, env=environment,
            )
            output = result.stdout
            item["exited_zero"] = result.returncode == 0
            if result.returncode:
                item["error_type"] = "NonzeroExit"
        except subprocess.TimeoutExpired as exc:
            output = exc.stdout or ""
            item["error_type"] = "TimeoutExpired"
        except Exception as exc:
            kind = type(exc).__name__
            item["error_type"] = kind if kind in {"OSError", "ValueError"} else "UnexpectedError"
        markers, valid = parse_phase_markers(output, expected)
        item["markers"] = markers
        item["output_valid"] = valid
        item["success"] = (item["exited_zero"] and valid and len(markers) == len(expected)
            and markers[1]["count"] == 1 and markers[2]["count"] == 1)
        item["elapsed_ms"] = round((time.monotonic() - started) * 1000)
        report[label] = item
    return report


def owned_automatic_cim_passed(report):
    # References/explicit import provide evidence, never replace the owned automatic path.
    return report.get("automatic", {}).get("success") is True


def qualify_actual_snapshot(inspector):
    """Use the actual inspector; retain counts and proof of this worker, never rows."""
    started = time.monotonic()
    report = {"success": False, "row_count": 0, "own_process_proven": False, "error_type": None}
    try:
        rows = inspector()
        report["row_count"] = len(rows) if isinstance(rows, list) else 0
        report["own_process_proven"] = isinstance(rows, list) and any(
            isinstance(row, dict) and type(row.get("pid")) is int and row["pid"] == os.getpid()
            and all(isinstance(row.get(key), str) and bool(row[key].strip())
                for key in ("creation_time", "executable_path", "command_line")) for row in rows)
        report["success"] = report["row_count"] > 0 and report["own_process_proven"]
        del rows
    except Exception as exc:
        kind = type(exc).__name__
        report["error_type"] = kind if kind in {"TimeoutExpired", "OSError", "ValueError", "JSONDecodeError"} else "UnexpectedError"
    report["elapsed_ms"] = round((time.monotonic() - started) * 1000)
    return report


class BasicLimits(ctypes.Structure):
    _fields_ = [("process_time", ctypes.c_int64), ("job_time", ctypes.c_int64),
        ("flags", wintypes.DWORD), ("minimum", ctypes.c_size_t), ("maximum", ctypes.c_size_t),
        ("active_limit", wintypes.DWORD), ("affinity", ctypes.c_size_t),
        ("priority", wintypes.DWORD), ("scheduling", wintypes.DWORD)]


class IoCounters(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in
        ("read_ops", "write_ops", "other_ops", "read_bytes", "write_bytes", "other_bytes")]


class ExtendedLimits(ctypes.Structure):
    _fields_ = [("basic", BasicLimits), ("io", IoCounters),
        ("process_memory", ctypes.c_size_t), ("job_memory", ctypes.c_size_t),
        ("peak_process", ctypes.c_size_t), ("peak_job", ctypes.c_size_t)]


class Accounting(ctypes.Structure):
    _fields_ = [(name, ctypes.c_int64) for name in ("user", "kernel", "period_user", "period_kernel")] + [
        (name, wintypes.DWORD) for name in ("faults", "total", "active", "terminated")]


def _kernel():
    if os.name != "nt":
        raise RuntimeError("windows_required")
    api = ctypes.WinDLL("kernel32", use_last_error=True)
    signatures = {
        "CreateJobObjectW": ([ctypes.c_void_p, wintypes.LPCWSTR], wintypes.HANDLE),
        "OpenJobObjectW": ([wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR], wintypes.HANDLE),
        "SetInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD], wintypes.BOOL),
        "QueryInformationJobObject": ([wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD, ctypes.c_void_p], wintypes.BOOL),
        "AssignProcessToJobObject": ([wintypes.HANDLE, wintypes.HANDLE], wintypes.BOOL),
        "IsProcessInJob": ([wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)], wintypes.BOOL),
        "GetCurrentProcess": ([], wintypes.HANDLE),
        "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
        "TerminateJobObject": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "TerminateProcess": ([wintypes.HANDLE, wintypes.UINT], wintypes.BOOL),
        "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
        "ResumeThread": ([wintypes.HANDLE], wintypes.DWORD),
        "GetExitCodeProcess": ([wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
        "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
    }
    for name, (args, result) in signatures.items():
        fn = getattr(api, name); fn.argtypes = args; fn.restype = result
    return api


def _checked(ok, operation):
    if not ok:
        raise RuntimeError(operation + "_failed:" + str(ctypes.get_last_error()))


def _member(api, process, job):
    present = wintypes.BOOL()
    _checked(api.IsProcessInJob(process, job, ctypes.byref(present)), "job_membership")
    return bool(present.value)


@contextlib.contextmanager
def windows_job_guard():
    """Require real job ownership and fence any production taskkill to that job."""
    name = os.environ.get(JOB_ENV, "")
    if not re.fullmatch(r"charlie-test-[a-f0-9]{32}", name):
        raise RuntimeError("explicit_windows_test_job_required")
    api = _kernel(); job = api.OpenJobObjectW(0x4, False, name)
    _checked(job, "open_test_job")
    original_run = subprocess.run
    try:
        limits = ExtendedLimits()
        _checked(api.QueryInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits), None), "read_test_job_limits")
        if not limits.basic.flags & KILL_ON_CLOSE or limits.basic.flags & BREAKAWAY or not _member(api, api.GetCurrentProcess(), job):
            raise RuntimeError("test_job_ownership_or_limits_invalid")
        def guarded_run(command, *args, **kwargs):
            if isinstance(command, (list, tuple)) and command and Path(str(command[0])).name.lower() in {"taskkill", "taskkill.exe"}:
                if len(command) != 5 or command[1] != "/PID" or list(command[3:]) != ["/T", "/F"]:
                    raise RuntimeError("unbounded_test_termination_refused")
                target = int(command[2])
                handle = api.OpenProcess(0x1000, False, target)
                _checked(handle, "open_test_target")
                try:
                    if not _member(api, handle, job):
                        raise RuntimeError("termination_outside_test_job_refused")
                    # Keep the exact process object open across the PID-based command.
                    return original_run(command, *args, **kwargs)
                finally:
                    api.CloseHandle(handle)
            return original_run(command, *args, **kwargs)
        subprocess.run = guarded_run
        yield
    finally:
        subprocess.run = original_run
        api.CloseHandle(job)


def job_owned_test(function):
    @functools.wraps(function)
    def wrapped(*args, **kwargs):
        with windows_job_guard():
            return function(*args, **kwargs)
    return wrapped



def owned_powershell_child(script, variable="child"):
    """CreateProcess-style child inheritance; never ShellExecute/breakaway."""
    if not re.fullmatch(r"[a-z]+", variable):
        raise ValueError("invalid_test_variable")
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    return ("$i=[Diagnostics.ProcessStartInfo]::new();$i.FileName='powershell.exe';"
        f"$i.Arguments='-NoProfile -NonInteractive -EncodedCommand {encoded}';"
        "$i.UseShellExecute=$false;$i.CreateNoWindow=$true;"
        f"${variable}=[Diagnostics.Process]::Start($i);")


def exited_launcher_command():
    """A stdlib-only launcher exits immediately; its sleeping child stays in our job."""
    script = "\n".join((
        "import os, subprocess, sys",
        "subprocess.Popen([sys.executable, '-I', '-S', '-c', 'import time; time.sleep(120)'],",
        "    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,",
        "    close_fds=True, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))",
        "os._exit(0)",
    ))
    return [sys.executable, "-I", "-S", "-c", script]


def current_job_active_count():
    api = _kernel(); job = api.OpenJobObjectW(0x4, False, os.environ[JOB_ENV])
    _checked(job, "open_test_job")
    try:
        result = Accounting()
        _checked(api.QueryInformationJobObject(job, 1, ctypes.byref(result), ctypes.sizeof(result), None), "test_job_accounting")
        return int(result.active)
    finally:
        api.CloseHandle(job)


def close_retained_test_process(process):
    """Only a live, retained Popen handle; orphan cleanup belongs to the outer job."""
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait(timeout=5)


def _report_root(value):
    base = Path(os.environ.get("RUNNER_TEMP", "")).resolve()
    root = Path(value)
    if not os.environ.get("RUNNER_TEMP") or not root.is_absolute() or root.resolve() != root or root == base or base not in root.parents:
        raise RuntimeError("report_root_must_be_below_runner_temp")
    return root


def _worker(selector, root):
    if selector not in SELECTORS:
        raise RuntimeError("test_selector_refused")
    # Snapshot the inherited allowlist before test bootstrap adjusts test-only controls.
    probe_environment = dict(os.environ) if selector == SELECTORS[1] else None
    import tempfile
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    tempfile.tempdir = str(root)
    os.environ.update(CHARLIE_TEST_CONTROL_ROOT=str(root / "control"), CHARLIE_TEST_ISOLATION="1", PYTHON_DOTENV_DISABLED="1")
    import tests  # establish existing isolation before the captured opt-in decorator
    os.environ["CHARLIE_SUBPROCESS_TESTS_ENABLED"] = "1"
    os.environ.pop("CHARLIE_PROCESS_TERMINATION_ENABLED", None)
    def deny_network(*_args, **_kwargs):
        raise RuntimeError("lifecycle_test_network_forbidden")
    socket.socket.connect = deny_network
    with windows_job_guard():
        qualification = None
        if selector == SELECTORS[1]:
            phases = probe_cim_module_context(probe_environment)
            actual = {"success": False, "status": "not_run"}
            if owned_automatic_cim_passed(phases):
                from modules.charlie import process_ownership
                actual = qualify_actual_snapshot(process_ownership._windows_process_snapshot)
            qualification = {"automatic_probe": phases, "actual_snapshot": actual}
            with (root / "cim-platform-qualification.json").open("x", encoding="utf-8") as stream:
                json.dump(qualification, stream, indent=2)
        with (root / "test.log").open("x", encoding="utf-8") as log:
            if qualification is not None:
                log.write("CIM_PLATFORM_QUALIFICATION=" + json.dumps(qualification, sort_keys=True) + "\n")
                if not owned_automatic_cim_passed(qualification["automatic_probe"]) or qualification["actual_snapshot"].get("success") is not True:
                    report = {"selector": selector, "tests_run": 0, "failures": 0, "errors": 1, "skips": 0}
                    with (root / "result.json").open("x", encoding="utf-8") as stream:
                        json.dump(report, stream, indent=2)
                    return 1
            suite = unittest.defaultTestLoader.loadTestsFromName(selector)
            result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
        report = {"selector": selector, "tests_run": result.testsRun, "failures": len(result.failures),
            "errors": len(result.errors), "skips": len(result.skipped)}
        with (root / "result.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        return 0 if result.testsRun == 1 and result.wasSuccessful() and not result.skipped else 1


def _run_owned_worker(selector, root):
    import _winapi
    api = _kernel(); name = "charlie-test-" + uuid.uuid4().hex
    job = api.CreateJobObjectW(None, name); _checked(job, "create_test_job")
    if ctypes.get_last_error() == 183:
        api.CloseHandle(job)
        raise RuntimeError("test_job_already_exists")
    process = thread = None
    unassigned_cleanup_verified = True
    report = {"selector": selector, "cleanup_verified": False, "timed_out": False}
    try:
        limits = ExtendedLimits(); limits.basic.flags = KILL_ON_CLOSE
        _checked(api.SetInformationJobObject(job, 9, ctypes.byref(limits), ctypes.sizeof(limits)), "set_test_job_limits")
        env = worker_environment(os.environ, root, name)
        if selector == SELECTORS[1]:
            # Read-only references extend the parent preflight, never lifecycle/termination.
            # Ambient variants remain parent-only; no parent credentials enter the worker.
            report["process_policy_context"] = process_policy_context(os.environ, env)
            report["environment_omission"] = diagnose_environment_omissions(env, root, os.environ)
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "--worker", selector, "--report-root", str(root)]
        process, thread, _pid, _tid = _winapi.CreateProcess(sys.executable, subprocess.list2cmdline(command), None, None, False,
            0x4 | 0x08000000 | 0x400, env, str(Path(__file__).resolve().parents[1]), subprocess.STARTUPINFO())
        try:
            _checked(api.AssignProcessToJobObject(job, int(process)), "assign_suspended_test_worker")
        except BaseException:
            unassigned_cleanup_verified = bool(api.TerminateProcess(int(process), 1)) and api.WaitForSingleObject(int(process), 5000) == 0
            raise
        if api.ResumeThread(int(thread)) == 0xFFFFFFFF:
            raise RuntimeError("resume_test_worker_failed")
        wait = api.WaitForSingleObject(int(process), TEST_TIMEOUT_SECONDS * 1000)
        report["timed_out"] = wait == 258
        if wait not in {0, 258}:
            raise RuntimeError("test_worker_wait_failed")
        if not report["timed_out"]:
            code = wintypes.DWORD(); _checked(api.GetExitCodeProcess(int(process), ctypes.byref(code)), "test_exit_code")
            report["exit_code"] = code.value
            result_path = root / "result.json"
            if result_path.is_file() and result_path.stat().st_size < 16384:
                report["result"] = json.loads(result_path.read_text())
    except BaseException as exc:
        report["error_type"] = type(exc).__name__
    finally:
        # Always empty the exact owned job, including orphan descendants and timeout paths.
        terminated = bool(api.TerminateJobObject(job, 1))
        deadline = time.monotonic() + 10
        while terminated and time.monotonic() < deadline:
            account = Accounting()
            if not api.QueryInformationJobObject(job, 1, ctypes.byref(account), ctypes.sizeof(account), None):
                break
            if account.active == 0:
                report["cleanup_verified"] = unassigned_cleanup_verified
                break
            time.sleep(0.05)
        for handle in (thread, process, job):
            if handle: api.CloseHandle(int(handle))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report-root", required=True)
    parser.add_argument("--source-sha")
    parser.add_argument("--worker", choices=SELECTORS)
    args = parser.parse_args()
    if os.name != "nt" or os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_OS") != "Windows":
        raise RuntimeError("disposable_hosted_windows_required")
    root = _report_root(args.report_root)
    if args.worker:
        return _worker(args.worker, root)
    if not re.fullmatch(r"[a-f0-9]{40}", args.source_sha or ""):
        raise RuntimeError("exact_source_sha_required")
    source = Path(__file__).resolve().parents[1]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source, text=True, timeout=10).strip()
    if head != args.source_sha or subprocess.check_output(["git", "status", "--porcelain"], cwd=source, text=True, timeout=10).strip():
        raise RuntimeError("source_revision_or_cleanliness_mismatch")
    root.mkdir(parents=True, exist_ok=False)
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if not powershell.is_file():
        raise RuntimeError("powershell_required")
    probe = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command",
        f"$ErrorActionPreference='Stop';$p=Get-CimInstance Win32_Process -Filter 'ProcessId={os.getpid()}';if(!$p.CreationDate -or !$p.ExecutablePath -or !$p.CommandLine){{exit 1}}"],
        capture_output=True, timeout=15, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
    if probe.returncode:
        raise RuntimeError("current_process_cim_preflight_failed")
    reports = []
    for index, selector in enumerate(SELECTORS):
        case_root = root / str(index); case_root.mkdir()
        report = _run_owned_worker(selector, case_root); reports.append(report)
        with (case_root / "parent-result.json").open("x", encoding="utf-8") as stream:
            json.dump(report, stream, indent=2)
        if report.get("exit_code") != 0 or not report["cleanup_verified"]:
            break
    passed = len(reports) == 4 and all(r.get("exit_code") == 0 and r["cleanup_verified"] and
        r.get("result") == {"selector":r["selector"], "tests_run":1, "failures":0, "errors":0, "skips":0} for r in reports)
    with (root / "summary.json").open("x", encoding="utf-8") as stream:
        json.dump({"source_sha":head, "passed":passed, "tests_run":sum(r.get("result",{}).get("tests_run",0) for r in reports), "reports":reports}, stream, indent=2)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
