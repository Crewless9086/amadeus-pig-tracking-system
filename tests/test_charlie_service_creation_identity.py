"""Schedule service identity uses exact-PID CIM, never privileged kernel fallback."""
import copy
import json
import subprocess
from unittest.mock import Mock, patch

import unittest

from modules.charlie import runtime_activation as a


SERVICE_PID = 50
ENGINE_PID = 100
STAMP = "2026-10-08T00:00:13.5608400Z"


def service_row():
    return {
        "ProcessId": SERVICE_PID, "Name": "Schedule", "State": "Running",
        "StartName": "LocalSystem",
        "PathName": "C:/Windows/System32/svchost.exe -k netsvcs -p",
        "EnginePID": ENGINE_PID, "InstanceGuid": "11111111-1111-1111-1111-111111111111",
        "TaskPath": "\\CHARLIE CORE Runner Watchdog", "CurrentAction": "C:/farm/venv/Scripts/python.exe",
        "ActionExecute": "C:/farm/venv/Scripts/python.exe",
        "ActionArguments": '"C:/farm/scripts/charlie_runner_task_launcher.py"',
        "ActionWorkingDirectory": "C:/farm",
        "ServiceDll": "C:/Windows/System32/schedsvc.dll", "SystemRoot": "C:/Windows",
    }


def cim_row(**changes):
    # Protected Schedule service does not expose image/command through CIM.
    return dict({"ProcessId": SERVICE_PID, "ParentProcessId": 7, "ExecutablePath": None,
                 "CreationDate": STAMP, "CommandLine": None}, **changes)


def native_shape_runner(cim=None, provider=None):
    calls = []
    def runner(command, **kwargs):
        script = command[-1]
        calls.append((script, kwargs))
        if "sc.exe queryex Schedule" in script:
            row = service_row() if provider is None else provider
        else:
            assert 'Get-CimInstance Win32_Process -Filter "ProcessId=50"' in script
            assert "$_.CreationDate.ToUniversalTime().ToString('o')" in script
            row = cim_row() if cim is None else cim
        return subprocess.CompletedProcess(command, 0, json.dumps(row), "")
    return runner, calls


class ServiceCreationIdentityTests(unittest.TestCase):
    def test_provider_default_uses_exact_cim_pid_and_preserves_timestamp_precision(self):
        runner, calls = native_shape_runner()
        with patch.object(a, "_windows_process_creation_time", side_effect=AssertionError("kernel fallback forbidden")):
            result = a._inspect_windows_task_scheduler_provider(ENGINE_PID, runner=runner)
        assert result["inspection_complete"] is True and a._valid_task_scheduler_provider(result)
        assert result["pid"] == SERVICE_PID and result["creation_time"] == STAMP
        assert result["executable_path"] == "C:/Windows/System32/svchost.exe"
        assert len(calls) == 2 and calls[1][1]["timeout"] == 10

    def test_malformed_wrong_pid_or_non_utc_cim_refuses_provider_identity(self):
        cases = [
            {"ProcessId": 51}, {"CreationDate": None}, {"CreationDate": ""},
            {"CreationDate": "not-a-date"}, {"CreationDate": "2026-10-08T00:00:13"},
            {"CreationDate": "10/08/2026 00:00:13"},
            {"CreationDate": "134361000000000000"},
            {"CreationDate": "2026-10-08T02:00:13+02:00"},
            {"CreationDate": "2026-02-30T00:00:13Z"},
        ]
        for changes in cases:
            with self.subTest(changes=changes):
                runner, _ = native_shape_runner(cim=cim_row(**changes))
                with patch.object(a, "_windows_process_creation_time", side_effect=AssertionError("kernel fallback forbidden")):
                    result = a._inspect_windows_task_scheduler_provider(ENGINE_PID, runner=runner)
                assert result["inspection_complete"] is False

    def test_service_creation_reader_refuses_incomplete_or_wrong_identity(self):
        cases = [
            {}, {"inspection_complete": False, "pid": SERVICE_PID, "creation_time": STAMP},
            {"inspection_complete": True, "pid": 51, "creation_time": STAMP},
            {"inspection_complete": True, "pid": SERVICE_PID, "creation_time": ""},
            None,
        ]
        for result in cases:
            with self.subTest(result=result):
                with patch.object(a, "_inspect_exact_process", return_value=result) as inspect:
                    assert a._task_scheduler_service_creation_time(SERVICE_PID) == ""
                inspect.assert_called_once_with(SERVICE_PID, runner=subprocess.run, creation_time_utc=True)

    def test_service_creation_read_failure_has_no_kernel_fallback(self):
        cases = [
            OSError("unavailable"), subprocess.TimeoutExpired("read-only CIM", 10),
            subprocess.CalledProcessError(1, "read-only CIM"),
        ]
        for exc in cases:
            with self.subTest(exc=exc):
                with patch.object(a, "_inspect_exact_process", side_effect=exc), \
                     patch.object(a, "_windows_process_creation_time", side_effect=AssertionError("kernel fallback forbidden")):
                    assert a._task_scheduler_service_creation_time(SERVICE_PID) == ""

    def test_existing_explicit_creation_time_injection_is_preserved(self):
        runner, calls = native_shape_runner()
        injected = Mock(return_value="explicit-existing-test-identity")
        with patch.object(a, "_task_scheduler_service_creation_time", side_effect=AssertionError("unexpected default")):
            result = a._inspect_windows_task_scheduler_provider(ENGINE_PID, runner=runner, process_creation_time=injected)
        injected.assert_called_once_with(SERVICE_PID)
        assert result["creation_time"] == "explicit-existing-test-identity" and len(calls) == 1

    def test_full_provider_chain_rereads_same_cim_source_and_rejects_pid_reuse(self):
        cases = [(STAMP, True), ("2026-10-08T00:00:14.5608400Z", False)]
        for second_stamp, expected in cases:
            with self.subTest(second_stamp=second_stamp, expected=expected):
                stamps = iter([STAMP, second_stamp])
                queries = []
                def runner(command, **kwargs):
                    script = command[-1]
                    if "sc.exe queryex Schedule" in script:
                        row = service_row()
                    else:
                        queries.append(script)
                        assert 'ProcessId=50' in script
                        row = cim_row(CreationDate=next(stamps))
                    return subprocess.CompletedProcess(command, 0, json.dumps(row), "")
                provider = lambda: a._inspect_windows_task_scheduler_provider(ENGINE_PID, runner=runner)
                current = {"inspection_complete": True, "pid": ENGINE_PID, "parent_pid": SERVICE_PID,
                           "executable_path": "C:/farm/venv/Scripts/python.exe",
                           "creation_time": "2026-10-13T04:52:04.000000Z",
                           "command_line": 'C:/farm/venv/Scripts/python.exe "C:/farm/scripts/charlie_runner_task_launcher.py"'}
                with patch.object(a, "_windows_process_creation_time", side_effect=AssertionError("kernel fallback forbidden")):
                    result = a.inspect_current_provider_chain(
                        ENGINE_PID, current_identity=lambda: copy.deepcopy(current), provider_identity=provider)
                assert result["inspection_complete"] is expected
                assert len(queries) == 2
                if expected:
                    assert result["ancestry"][0]["creation_time"] == STAMP
                else:
                    assert result["reason"] == "provider_ancestry_changed"

    def test_cim_timestamp_does_not_replace_scm_or_exact_action_validation(self):
        cases = [{"Name": "Other"}, {"ActionExecute": ""}, {"ServiceDll": "C:/unrelated.dll"}, {"EnginePID": 101}]
        for changed in cases:
            with self.subTest(changed=changed):
                row = service_row(); row.update(changed)
                runner, _ = native_shape_runner(provider=row)
                current = {"inspection_complete": True, "pid": ENGINE_PID, "parent_pid": SERVICE_PID,
                           "executable_path": "C:/farm/venv/Scripts/python.exe",
                           "creation_time": "2026-10-13T04:52:04Z", "command_line": "synthetic action"}
                result = a.inspect_current_provider_chain(ENGINE_PID,
                    current_identity=lambda: current,
                    provider_identity=lambda: a._inspect_windows_task_scheduler_provider(ENGINE_PID, runner=runner))
                assert result["inspection_complete"] is False


if __name__ == "__main__":
    unittest.main()
