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
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
import unittest
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
        suite = unittest.defaultTestLoader.loadTestsFromName(selector)
        with (root / "test.log").open("x", encoding="utf-8") as log:
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
        env = {k:v for k,v in os.environ.items() if k.upper() in {"PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "RUNNER_TEMP", "GITHUB_ACTIONS", "RUNNER_OS"}}
        env.update({JOB_ENV: name, "TEMP":str(root), "TMP":str(root), "PYTHONDONTWRITEBYTECODE":"1", "PYTHON_DOTENV_DISABLED":"1", "DATABASE_URL":""})
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
