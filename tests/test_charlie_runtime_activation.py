import base64
import hashlib
import hmac
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import modules.charlie.runtime_activation as runtime_activation

from modules.charlie.runtime_activation import (
    ACTIVATION_VERSION,
    AUTHORITY_VERSION,
    ActivationError,
    WindowsExactTaskController,
    consume_provider_activation,
    inspect_current_provider_chain,
    plan_activation,
    prepare_activation,
    read_activation_runtime_evidence,
    reconcile_recovered_activation_stop,
    recover_activation,
    verify_or_recover_activation,
    verify_provider_origin,
    _inspect_exact_process,
    _inspect_windows_task_scheduler_provider,
    _local_current_process_identity,
    _durable_replace,
    _validate_packet,
)
from modules.charlie.runtime_staging import _validate_recovery_projection


SOURCE = "e3e3587430f21f05fa49d4a057497ca599bfc17c"


class FakeGit:
    def __init__(self, runtime, execution):
        self.roots = {str(runtime.resolve()), str(execution.resolve())}
        self.dirty = set()

    def __call__(self, command, cwd=None, **_kwargs):
        root = str(Path(cwd).resolve())
        args = command[1:]
        while args[:1] == ["-c"]:
            args = args[2:]
        if root not in self.roots:
            return subprocess.CompletedProcess(command, 1, "", "unknown root")
        if args == ["status", "--porcelain"]:
            output = "dirty\n" if root in self.dirty else ""
        elif args == ["rev-parse", "HEAD"]:
            output = SOURCE + "\n"
        elif args == ["branch", "--show-current"]:
            output = "\n"
        else:
            return subprocess.CompletedProcess(command, 1, "", "unsupported")
        return subprocess.CompletedProcess(command, 0, output, "")


class Controller:
    def __init__(self, fail_start=False):
        self.enabled = []
        self.disabled = []
        self.fail_start = fail_start
        self.audit_state = {"log_name": "Microsoft-Windows-TaskScheduler/Operational",
                            "enabled": False}
        self.audit_prior = None
        self.audit_changed = False
        self.audit_mutation_attempted = False
        self.audit_enabled = []
        self.audit_restored = []
        self.instance_state = "running"

    def read_audit_channel_state(self):
        return dict(self.audit_state)

    def bind_audit_channel_state(self, value):
        self.audit_prior = dict(value)

    def read_audit_event_record_id(self):
        return 455

    def assert_no_running_instances(self):
        return None

    def read_exact_instance_state(self, _instance_guid):
        return self.instance_state

    def ensure_audit_channel_enabled(self):
        changed = not self.audit_state["enabled"]
        self.audit_mutation_attempted = changed
        self.audit_state["enabled"] = True
        self.audit_enabled.append(True)
        self.audit_changed = changed
        return changed

    def restore_audit_channel_state(self):
        changed = self.audit_state != self.audit_prior
        self.audit_state = dict(self.audit_prior)
        self.audit_restored.append(self.audit_state["enabled"])
        return changed

    def reconcile_audit_channel_state(self):
        return self.restore_audit_channel_state()

    def enable_and_trigger_exact(self, digest):
        self.enabled.append(digest)
        if self.fail_start:
            raise ActivationError("provider_start_failed")
        return "11111111-1111-1111-1111-111111111111"

    def disable_exact(self, digest):
        self.disabled.append(digest)


class RuntimeActivationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        canonical = Path(self.temp.name)
        self.state = canonical / "state"
        self.runtime = self.state / "core-runtime-current"
        self.execution = self.state / "core-execution-current"
        self.runtime.mkdir(parents=True)
        self.execution.mkdir()
        self.key = b"control-tower-provider-activation-key-material"
        (self.state / "activation-authority.key").write_bytes(self.key)
        self.receipt = canonical / "receipt.json"
        self.receipt.write_text('{"status":"passed"}', encoding="utf-8")
        self.stop = self.state / "supervisor.stop"
        self.stop.write_text("governed\n", encoding="utf-8")
        self.manifest = self.state / "runtime-manifest.json"
        self.manifest.write_text(json.dumps({
            "promoted_commit": SOURCE,
            "validation_receipt_sha256": self._sha(self.receipt),
        }), encoding="utf-8")
        (self.state / "supervisor.json").write_text(
            json.dumps({"status": "supervisor_stopped", "pid": 987654,
                        "child_pid": 987655}), encoding="utf-8"
        )
        self.git = FakeGit(self.runtime, self.execution)
        self.task = self._task()
        self.authority_path = canonical / "authority.json"
        self.authority = self._authority()
        self._write_authority()

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def _sha(path):
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    @staticmethod
    def _payload_sha(value):
        raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()

    def _task(self):
        canonical = self.state.parent
        watchdog = self.runtime / "scripts" / "charlie_runner_watchdog.py"
        arguments = (
            '-c "from dotenv import load_dotenv; load_dotenv(r\'{0}\', override=True); '
            "import runpy,sys; sys.argv=[r'{1}','--json']; "
            "runpy.run_path(r'{1}', run_name='__main__')\""
        ).format(canonical / ".env", watchdog)
        return [{
            "task_name": "CHARLIE CORE Runner Watchdog", "task_path": "\\", "state": "Disabled",
            "action_count": 1,
            "execute": str(canonical / "venv" / "Scripts" / "pythonw.exe"),
            "arguments": arguments, "working_directory": str(self.runtime),
        }]

    def _authority(self):
        value = {
            "version": AUTHORITY_VERSION,
            "issuer": "control_tower_activation_authority_v1",
            "activation_id": "1" * 32,
            "runtime_revision": SOURCE,
            "execution_revision": SOURCE,
            "manifest_sha256": self._sha(self.manifest),
            "receipt_path": str(self.receipt.resolve()),
            "receipt_sha256": self._sha(self.receipt),
            "stop_marker_sha256": self._sha(self.stop),
            "task_action_sha256": self._payload_sha(self.task),
            "execution_mode": "observe_only",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        }
        value["signature_hmac_sha256"] = hmac.new(
            self.key,
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        return value

    def _write_authority(self):
        self.authority_path.write_text(json.dumps(self.authority), encoding="utf-8")

    def _plan(self):
        return plan_activation(
            authority_path=self.authority_path,
            authority_sha256=self._sha(self.authority_path),
            state_root=self.state, runtime_root=self.runtime,
            execution_root=self.execution, task_reader=lambda: self.task,
            git_runner=self.git,
        )

    def _prepared(self):
        plan = self._plan()
        controller = Controller()
        result = prepare_activation(plan, task_controller=controller,
                                    task_reader=lambda: self.task, git_runner=self.git)
        return plan, controller, result

    def _mark_started(self, packet_status="provider_started_observe_only"):
        packet_path = self.state / "activation-packet.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        pending_hmac = packet["packet_hmac_sha256"]
        if packet_status != "provider_pending":
            packet["status"] = packet_status
            packet["consumed_packet_hmac_sha256"] = pending_hmac
            unsigned = {k: v for k, v in packet.items() if k != "packet_hmac_sha256"}
            packet["packet_hmac_sha256"] = hmac.new(
                self.key, json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256
            ).hexdigest()
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
        consumed = {"version": ACTIVATION_VERSION,
                    "activation_id": packet["activation_id"],
                    "provider_pid": 10, "provider_parent_pid": 20,
                    "provider_instance_guid": packet["expected_instance_guid"],
                    "expected_instance_guid": packet["expected_instance_guid"],
                    "packet_hmac_sha256": pending_hmac}
        consumed["consumed_hmac_sha256"] = hmac.new(
            self.key,
            json.dumps(consumed, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        (self.state / f"activation-consumed-{packet['activation_id']}.json").write_text(
            json.dumps(consumed), encoding="utf-8",
        )
        return packet

    def test_exact_task_action_digest_and_executable_are_required(self):
        for field, value in (("execute", "C:/substituted/pythonw.exe"),
                             ("arguments", "watchdog.py --extra")):
            with self.subTest(field=field):
                original = self.task[0][field]
                self.task[0][field] = value
                with self.assertRaises(ActivationError):
                    self._plan()
                self.task[0][field] = original

    def test_wrong_revision_manifest_receipt_stop_or_mode_fails_closed(self):
        fields = ("runtime_revision", "manifest_sha256", "receipt_sha256",
                  "stop_marker_sha256", "execution_mode")
        for field in fields:
            with self.subTest(field=field):
                saved = self.authority[field]
                self.authority[field] = "ordinary" if field == "execution_mode" else "0" * len(saved)
                unsigned = {k: v for k, v in self.authority.items() if k != "signature_hmac_sha256"}
                self.authority["signature_hmac_sha256"] = hmac.new(
                    self.key, json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256
                ).hexdigest()
                self._write_authority()
                with self.assertRaises(ActivationError):
                    self._plan()
                self.authority[field] = saved
                self.authority = self._authority()
                self._write_authority()

    def test_provider_origin_requires_exact_scheduled_ancestry(self):
        row = self.task[0]
        provider = lambda _pid: {
            "inspection_complete": True, "pid": os.getpid(), "parent_pid": 20,
            "executable_path": row["execute"],
            "command_line": f'"{row["execute"]}" {row["arguments"]}',
            "ancestry": [{"pid": 20, "executable_path": "C:/Windows/System32/svchost.exe",
                          "provider_identity_verified": True,
                          "instance_guid": "11111111-1111-1111-1111-111111111111",
                          "action_execute": row["execute"],
                          "action_arguments": row["arguments"],
                          "action_working_directory": row["working_directory"]}],
        }
        self.assertTrue(verify_provider_origin(provider, expected_task=self.task)["authorized"])

    def test_provider_origin_rejects_exact_parent_with_substituted_command(self):
        row = self.task[0]
        result = verify_provider_origin(lambda _pid: {
            "inspection_complete": True, "pid": 10, "parent_pid": 20,
            "executable_path": row["execute"],
            "command_line": f'"{row["execute"]}" -c "substituted"',
            "ancestry": [{"pid": 20, "executable_path": "svchost.exe",
                          "provider_identity_verified": True,
                          "action_execute": row["execute"],
                          "action_arguments": row["arguments"],
                          "action_working_directory": row["working_directory"]}],
        }, expected_task=self.task)
        self.assertEqual(result["reason"], "provider_task_action_mismatch")

    def test_provider_origin_rejects_substituted_scheduler_action_definition(self):
        row = self.task[0]
        result = verify_provider_origin(lambda _pid: {
            "inspection_complete": True, "pid": 10, "parent_pid": 20,
            "executable_path": row["execute"],
            "command_line": f'"{row["execute"]}" {row["arguments"]}',
            "ancestry": [{"pid": 20, "executable_path": "svchost.exe",
                          "provider_identity_verified": True,
                          "action_execute": row["execute"],
                          "action_arguments": "-c substituted",
                          "action_working_directory": row["working_directory"]}],
        }, expected_task=self.task)
        self.assertEqual(result["reason"], "provider_task_action_mismatch")

    def test_direct_terminal_spawn_and_protected_ancestry_are_rejected(self):
        for executable in ("powershell.exe", "codex.exe", "cmd.exe"):
            result = verify_provider_origin(lambda _pid, executable=executable: {
                "inspection_complete": True, "pid": 10, "parent_pid": 20,
                "executable_path": self.task[0]["execute"],
                "command_line": f'"{self.task[0]["execute"]}" {self.task[0]["arguments"]}',
                "ancestry": [{"pid": 20, "executable_path": f"C:/{executable}"}],
            }, expected_task=self.task)
            self.assertFalse(result["authorized"])

    def test_bounded_provider_inspection_queries_only_exact_ancestry_pids(self):
        calls = []
        rows = {
            50: {"ProcessId": 50, "ParentProcessId": 0, "ExecutablePath": "svchost.exe",
                 "CreationDate": "provider-created", "CommandLine": "svchost.exe -k netsvcs"},
        }
        def runner(command, **_kwargs):
            calls.append(command[-1])
            return subprocess.CompletedProcess(command, 0, json.dumps(rows[50]), "")
        provider = lambda: {
            "inspection_complete": True, "pid": 50, "creation_time": "provider-created",
            "service_name": "Schedule", "service_state": "Running", "start_name": "LocalSystem",
            "executable_path": "C:/Windows/System32/svchost.exe",
            "service_binary_path": "C:/Windows/System32/svchost.exe -k netsvcs -p",
            "service_dll": "C:/Windows/System32/schedsvc.dll", "system_root": "C:/Windows",
            "engine_pid": 100, "instance_guid": "11111111-1111-1111-1111-111111111111",
            "task_path": "\\CHARLIE CORE Runner Watchdog",
            "provider_identity_verified": True, "current_action": "Execute",
            "action_execute": self.task[0]["execute"],
            "action_arguments": self.task[0]["arguments"],
            "action_working_directory": self.task[0]["working_directory"],
        }
        result = inspect_current_provider_chain(100, runner=runner, provider_identity=provider,
                                                current_identity=lambda: {
            "inspection_complete": True, "pid": 100, "parent_pid": 50,
            "executable_path": "pythonw.exe", "creation_time": "child-created",
            "command_line": "pythonw.exe watchdog.py",
        })
        self.assertTrue(result["inspection_complete"])
        self.assertEqual(calls, [])

    def test_scheduled_child_self_cim_denial_uses_local_identity_and_proves_provider(self):
        row = self.task[0]
        calls = []
        parent = {"ProcessId": 50, "ParentProcessId": 0,
                  "ExecutablePath": "C:/Windows/System32/svchost.exe",
                  "CreationDate": "provider-created", "CommandLine": "svchost.exe -k netsvcs"}
        def runner(command, **_kwargs):
            calls.append(command[-1])
            return subprocess.CompletedProcess(command, 0, json.dumps(parent), "")
        provider = lambda: {
            "inspection_complete": True, "pid": 50, "creation_time": "provider-created",
            "service_name": "Schedule", "service_state": "Running", "start_name": "LocalSystem",
            "executable_path": "C:/Windows/System32/svchost.exe",
            "service_binary_path": "C:/Windows/System32/svchost.exe -k netsvcs -p",
            "service_dll": "C:/Windows/System32/schedsvc.dll", "system_root": "C:/Windows",
            "engine_pid": 100, "instance_guid": "11111111-1111-1111-1111-111111111111",
            "task_path": "\\CHARLIE CORE Runner Watchdog",
            "provider_identity_verified": True, "current_action": "Execute",
            "action_execute": row["execute"], "action_arguments": row["arguments"],
            "action_working_directory": row["working_directory"],
        }
        inspected = inspect_current_provider_chain(100, runner=runner, provider_identity=provider,
                                                   current_identity=lambda: {
            "inspection_complete": True, "pid": 100, "parent_pid": 50,
            "executable_path": row["execute"], "creation_time": "child-created",
            "command_line": f'"{row["execute"]}" {row["arguments"]}',
        })
        self.assertTrue(verify_provider_origin(lambda _pid: inspected, expected_task=self.task)["authorized"])
        self.assertEqual(len(calls), 0)
        self.assertTrue(all("ProcessId=100" not in call for call in calls))

    def test_aa3be93a_shape_accepts_scm_identity_when_provider_process_path_is_acl_hidden(self):
        row = self.task[0]
        provider_reads = iter([
            {"inspection_complete": True, "pid": 50, "creation_time": "provider-created",
             "service_name": "Schedule", "service_state": "Running", "start_name": "LocalSystem",
             "executable_path": "C:/Windows/System32/svchost.exe",
             "service_binary_path": "C:/Windows/System32/svchost.exe -k netsvcs -p",
             "service_dll": "C:/Windows/System32/schedsvc.dll", "system_root": "C:/Windows",
             "engine_pid": 100, "instance_guid": "11111111-1111-1111-1111-111111111111",
             "task_path": "\\CHARLIE CORE Runner Watchdog",
             "provider_identity_verified": True, "current_action": "Execute",
             "action_execute": row["execute"], "action_arguments": row["arguments"],
             "action_working_directory": row["working_directory"]},
            {"inspection_complete": True, "pid": 50, "creation_time": "provider-created",
             "service_name": "Schedule", "service_state": "Running", "start_name": "LocalSystem",
             "executable_path": "C:/Windows/System32/svchost.exe",
             "service_binary_path": "C:/Windows/System32/svchost.exe -k netsvcs -p",
             "service_dll": "C:/Windows/System32/schedsvc.dll", "system_root": "C:/Windows",
             "engine_pid": 100, "instance_guid": "11111111-1111-1111-1111-111111111111",
             "task_path": "\\CHARLIE CORE Runner Watchdog",
             "provider_identity_verified": True, "current_action": "Execute",
             "action_execute": row["execute"], "action_arguments": row["arguments"],
             "action_working_directory": row["working_directory"]},
        ])
        inspected = inspect_current_provider_chain(
            100, provider_identity=lambda: next(provider_reads), current_identity=lambda: {
                "inspection_complete": True, "pid": 100, "parent_pid": 50,
                "executable_path": row["execute"], "creation_time": "child-created",
                "command_line": f'"{row["execute"]}" {row["arguments"]}',
            })
        result = verify_provider_origin(lambda _pid: inspected, expected_task=self.task)
        self.assertTrue(result["authorized"])

    def test_scm_provider_identity_fails_closed_on_reuse_reparent_or_configuration_change(self):
        base = {"inspection_complete": True, "pid": 50, "creation_time": "provider-created",
                "service_name": "Schedule", "service_state": "Running", "start_name": "LocalSystem",
                "executable_path": "C:/Windows/System32/svchost.exe",
                "service_binary_path": "C:/Windows/System32/svchost.exe -k netsvcs -p",
                "service_dll": "C:/Windows/System32/schedsvc.dll", "system_root": "C:/Windows",
                "engine_pid": 100, "instance_guid": "11111111-1111-1111-1111-111111111111",
                "task_path": "\\CHARLIE CORE Runner Watchdog",
                "provider_identity_verified": True, "current_action": "Execute",
                "action_execute": self.task[0]["execute"],
                "action_arguments": self.task[0]["arguments"],
                "action_working_directory": self.task[0]["working_directory"]}
        for field, replacement in (("pid", 51), ("creation_time", "reused"),
                                   ("service_binary_path", "C:/evil/svchost.exe -k netsvcs -p"),
                                   ("service_dll", "C:/evil/schedsvc.dll"),
                                   ("start_name", "LocalService")):
            with self.subTest(field=field):
                reads = iter([dict(base), {**base, field: replacement}])
                result = inspect_current_provider_chain(
                    100, provider_identity=lambda: next(reads), current_identity=lambda: {
                        "inspection_complete": True, "pid": 100, "parent_pid": 50,
                        "executable_path": "pythonw.exe", "creation_time": "child-created",
                        "command_line": "pythonw.exe watchdog.py",
                    })
                self.assertFalse(result["inspection_complete"])

    def test_provider_pid_substitution_during_bounded_read_fails_closed(self):
        base = {"inspection_complete": True, "pid": 50, "creation_time": "first",
                "service_name": "Schedule", "service_state": "Running", "start_name": "LocalSystem",
                "executable_path": "C:/Windows/System32/svchost.exe",
                "service_binary_path": "C:/Windows/System32/svchost.exe -k netsvcs -p",
                "service_dll": "C:/Windows/System32/schedsvc.dll", "system_root": "C:/Windows",
                "engine_pid": 100, "instance_guid": "11111111-1111-1111-1111-111111111111",
                "task_path": "\\CHARLIE CORE Runner Watchdog",
                "provider_identity_verified": True, "current_action": "Execute",
                "action_execute": self.task[0]["execute"],
                "action_arguments": self.task[0]["arguments"],
                "action_working_directory": self.task[0]["working_directory"]}
        rows = iter([base, {**base, "creation_time": "replacement"}])
        result = inspect_current_provider_chain(100, provider_identity=lambda: next(rows),
            current_identity=lambda: {
                "inspection_complete": True, "pid": 100, "parent_pid": 50,
                "executable_path": "pythonw.exe", "creation_time": "child-created",
                "command_line": "pythonw.exe watchdog.py",
            })
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "provider_ancestry_changed")

    def test_terminal_above_scheduled_child_remains_rejected(self):
        row = self.task[0]
        inspected = {
            "inspection_complete": True, "pid": 100, "parent_pid": 50,
            "executable_path": row["execute"],
            "command_line": f'"{row["execute"]}" {row["arguments"]}',
            "ancestry": [
                {"pid": 50, "parent_pid": 40, "executable_path": "svchost.exe"},
                {"pid": 40, "parent_pid": 0, "executable_path": "powershell.exe"},
            ],
        }
        result = verify_provider_origin(lambda _pid: inspected, expected_task=self.task)
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "terminal_ancestry_rejected")

    def test_exact_pid_inspector_returns_complete_identity_on_success(self):
        row = {"ProcessId": 42, "ParentProcessId": 7, "ExecutablePath": "pythonw.exe",
               "CreationDate": "20260817120000.000000+120", "CommandLine": "pythonw.exe watchdog.py"}
        result = _inspect_exact_process(
            42, runner=lambda command, **_kwargs: subprocess.CompletedProcess(
                command, 0, json.dumps(row), ""
            )
        )
        self.assertTrue(result["inspection_complete"])
        self.assertEqual((result["pid"], result["parent_pid"]), (42, 7))

    def test_windows_provider_uses_exact_pid_kernel_creation_time_and_exact_action(self):
        row = self.task[0]
        provider_json = {
            "ProcessId": 50, "Name": "Schedule", "State": "Running",
            "StartName": "LocalSystem",
            "PathName": "C:/Windows/System32/svchost.exe -k netsvcs -p",
            "EnginePID": 100, "InstanceGuid": "11111111-1111-1111-1111-111111111111",
            "TaskPath": "\\CHARLIE CORE Runner Watchdog", "CurrentAction": "Execute",
            "ActionExecute": row["execute"], "ActionArguments": row["arguments"],
            "ActionWorkingDirectory": row["working_directory"],
            "ServiceDll": "C:/Windows/System32/schedsvc.dll", "SystemRoot": "C:/Windows",
        }
        creation_calls = []
        result = _inspect_windows_task_scheduler_provider(
            100,
            runner=lambda command, **_kwargs: subprocess.CompletedProcess(
                command, 0, json.dumps(provider_json), ""),
            process_creation_time=lambda pid: creation_calls.append(pid) or "987654321",
        )
        self.assertTrue(result["inspection_complete"])
        self.assertEqual(creation_calls, [50])
        self.assertEqual(result["creation_time"], "987654321")
        self.assertEqual(result["action_arguments"], row["arguments"])

    def test_windows_provider_waits_for_exact_fast_start_instance_visibility(self):
        """The scheduled child may run before GetInstances exposes its EnginePID."""
        row = self.task[0]
        provider_json = {
            "ProcessId": 50, "Name": "Schedule", "State": "Running",
            "StartName": "LocalSystem",
            "PathName": "C:/Windows/System32/svchost.exe -k netsvcs -p",
            "EnginePID": 100, "InstanceGuid": "11111111-1111-1111-1111-111111111111",
            "TaskPath": "\\CHARLIE CORE Runner Watchdog", "CurrentAction": "Execute",
            "ActionExecute": row["execute"], "ActionArguments": row["arguments"],
            "ActionWorkingDirectory": row["working_directory"],
            "ServiceDll": "C:/Windows/System32/schedsvc.dll", "SystemRoot": "C:/Windows",
        }
        result = _inspect_windows_task_scheduler_provider(
            100, runner=lambda _command, **_kwargs: subprocess.CompletedProcess(
                [], 0, json.dumps(provider_json), ""),
            process_creation_time=lambda pid: "987654321" if pid == 50 else "",
        )
        self.assertTrue(result["inspection_complete"])
        self.assertEqual(result["engine_pid"], 100)

    def test_windows_provider_visibility_window_is_bounded_and_fails_closed(self):
        calls = []
        result = _inspect_windows_task_scheduler_provider(
            100,
            runner=lambda command, **_kwargs: (
                calls.append(command) or subprocess.CompletedProcess(command, 6, "", "")
            ),
        )
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "task_instance_visibility_timeout")
        self.assertEqual(len(calls), 1)

    def test_windows_provider_default_uses_one_in_process_visibility_window(self):
        calls = []
        result = _inspect_windows_task_scheduler_provider(
            100,
            runner=lambda command, **_kwargs: (
                calls.append(command) or subprocess.CompletedProcess(command, 6, "", "")
            ),
        )
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "task_instance_visibility_timeout")
        self.assertEqual(len(calls), 1)
        script = calls[0][-1]
        self.assertIn("AddSeconds(5)", script)
        self.assertIn("Start-Sleep -Milliseconds 100", script)

    def test_windows_provider_subprocess_deadline_fails_closed(self):
        def timeout(_command, **kwargs):
            self.assertEqual(kwargs["timeout"], 20)
            raise subprocess.TimeoutExpired(_command, kwargs["timeout"])
        result = _inspect_windows_task_scheduler_provider(100, runner=timeout)
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "provider_inspection_deadline_exceeded")

    def test_windows_provider_subprocess_launch_failure_fails_closed(self):
        def unavailable(_command, **_kwargs):
            raise OSError("powershell unavailable")
        result = _inspect_windows_task_scheduler_provider(100, runner=unavailable)
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "provider_inspector_unavailable")

    def test_windows_provider_does_not_retry_non_visibility_identity_failure(self):
        calls = []
        result = _inspect_windows_task_scheduler_provider(
            100,
            runner=lambda command, **_kwargs: (
                calls.append(command) or subprocess.CompletedProcess(command, 7, "", "")
            ),
        )
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "task_action_identity_invalid")
        self.assertEqual(len(calls), 1)

    def test_windows_provider_does_not_retry_ambiguous_exact_pid_instances(self):
        calls = []
        result = _inspect_windows_task_scheduler_provider(
            100,
            runner=lambda command, **_kwargs: (
                calls.append(command) or subprocess.CompletedProcess(command, 8, "", "")
            ),
        )
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "task_instance_identity_ambiguous")
        self.assertEqual(len(calls), 1)

    def test_windows_provider_event_fallback_is_exact_activation_bound(self):
        row = self.task[0]
        provider_json = {
            "ProcessId": 50, "Name": "Schedule", "State": "Running",
            "StartName": "LocalSystem",
            "PathName": "C:/Windows/System32/svchost.exe -k netsvcs -p",
            "EnginePID": 100, "InstanceGuid": "11111111-1111-1111-1111-111111111111",
            "TaskPath": "\\CHARLIE CORE Runner Watchdog", "CurrentAction": row["execute"],
            "ActionExecute": row["execute"], "ActionArguments": row["arguments"],
            "ActionWorkingDirectory": row["working_directory"],
            "ServiceDll": "C:/Windows/System32/schedsvc.dll", "SystemRoot": "C:/Windows",
            "EvidenceSource": "operational_event", "EventRecordId": 456,
            "EventTime": "2026-08-18T08:00:00.0000000Z",
            "EventActivityId": "11111111-1111-1111-1111-111111111111",
            "EngineCreationTime": "2026-08-18T07:59:59.5000000Z",
            "EventRecordIdLowerBound": 455,
            "ActivationId": "activation-current",
        }
        calls = []
        result = _inspect_windows_task_scheduler_provider(
            100,
            runner=lambda command, **_kwargs: (
                calls.append(command) or subprocess.CompletedProcess(
                    command, 0, json.dumps(provider_json), "")
            ),
            process_creation_time=lambda _pid: "provider-created",
            activation_id="activation-current",
            activation_prepared_at="2026-08-18T07:59:59+00:00",
            event_record_id_lower_bound=455,
        )
        self.assertTrue(result["inspection_complete"])
        self.assertEqual(result["evidence_source"], "operational_event")
        self.assertEqual(result["event_record_id"], 456)
        script = calls[0][-1]
        self.assertIn("Id=200", script)
        self.assertIn("EnginePID-eq100", script)
        self.assertIn("TaskName).Equals('\\CHARLIE CORE Runner Watchdog'", script)
        self.assertIn("TimeCreated.ToUniversalTime()-ge$prepared", script)
        self.assertIn("TimeCreated.ToUniversalTime()-ge$engineCreated", script)
        self.assertIn("TimeCreated.ToUniversalTime()-le$engineCreated.AddSeconds(10)", script)
        self.assertIn("RecordId-gt455", script)
        self.assertIn("CreationDate-is[DateTime]", script)

    def test_event_fallback_rejects_disabled_ambiguous_or_missing_evidence(self):
        expected = {
            6: "task_instance_visibility_timeout",
            9: "task_scheduler_operational_log_disabled",
            10: "task_event_identity_ambiguous",
            11: "task_event_action_mismatch",
            12: "task_engine_process_identity_missing",
        }
        for return_code, reason in expected.items():
            with self.subTest(return_code=return_code):
                result = _inspect_windows_task_scheduler_provider(
                    100,
                    runner=lambda command, **_kwargs: subprocess.CompletedProcess(
                        command, return_code, "", ""),
                    activation_id="activation-current",
                    activation_prepared_at="2026-08-18T07:59:59+00:00",
                )
                self.assertFalse(result["inspection_complete"])
                self.assertEqual(result["reason"], reason)

    def test_provider_origin_preserves_fail_closed_inspector_reason(self):
        result = verify_provider_origin(
            lambda _pid: {"inspection_complete": False,
                          "reason": "task_instance_visibility_timeout"},
            expected_task=self.task,
        )
        self.assertFalse(result["authorized"])
        self.assertEqual(result["reason"], "task_instance_visibility_timeout")

    def test_delayed_instance_visibility_still_rejects_provider_pid_reuse(self):
        row = self.task[0]
        provider_json = {
            "ProcessId": 50, "Name": "Schedule", "State": "Running",
            "StartName": "LocalSystem",
            "PathName": "C:/Windows/System32/svchost.exe -k netsvcs -p",
            "EnginePID": 100, "InstanceGuid": "11111111-1111-1111-1111-111111111111",
            "TaskPath": "\\CHARLIE CORE Runner Watchdog", "CurrentAction": "Execute",
            "ActionExecute": row["execute"], "ActionArguments": row["arguments"],
            "ActionWorkingDirectory": row["working_directory"],
            "ServiceDll": "C:/Windows/System32/schedsvc.dll", "SystemRoot": "C:/Windows",
        }
        responses = iter([
            subprocess.CompletedProcess([], 0, json.dumps(provider_json), ""),
            subprocess.CompletedProcess([], 0, json.dumps(provider_json), ""),
        ])
        creation_times = iter(["provider-created", "provider-reused"])
        provider_reader = lambda: _inspect_windows_task_scheduler_provider(
            100, runner=lambda _command, **_kwargs: next(responses),
            process_creation_time=lambda _pid: next(creation_times),
        )
        result = inspect_current_provider_chain(
            100, provider_identity=provider_reader, current_identity=lambda: {
                "inspection_complete": True, "pid": 100, "parent_pid": 50,
                "executable_path": row["execute"], "creation_time": "short-lived-child",
                "command_line": f'"{row["execute"]}" {row["arguments"]}',
            })
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "provider_ancestry_changed")

    def test_fast_child_exit_during_delayed_instance_visibility_fails_closed(self):
        row = self.task[0]
        provider = {
            "inspection_complete": True, "pid": 50, "creation_time": "provider-created",
            "service_name": "Schedule", "service_state": "Running", "start_name": "LocalSystem",
            "executable_path": "C:/Windows/System32/svchost.exe",
            "service_binary_path": "C:/Windows/System32/svchost.exe -k netsvcs -p",
            "service_dll": "C:/Windows/System32/schedsvc.dll", "system_root": "C:/Windows",
            "engine_pid": 100, "instance_guid": "11111111-1111-1111-1111-111111111111",
            "task_path": "\\CHARLIE CORE Runner Watchdog", "provider_identity_verified": True,
            "current_action": "Execute", "action_execute": row["execute"],
            "action_arguments": row["arguments"],
            "action_working_directory": row["working_directory"],
        }
        provider_reads = iter([provider, dict(provider)])
        current_reads = iter([{
            "inspection_complete": True, "pid": 100, "parent_pid": 50,
            "executable_path": row["execute"], "creation_time": "short-lived-child",
            "command_line": f'"{row["execute"]}" {row["arguments"]}',
        }, {"inspection_complete": False}])
        result = inspect_current_provider_chain(
            100, provider_identity=lambda: next(provider_reads),
            current_identity=lambda: next(current_reads),
        )
        self.assertFalse(result["inspection_complete"])
        self.assertEqual(result["reason"], "provider_child_identity_changed")

    @unittest.skipUnless(os.name == "nt", "Windows kernel identity only")
    def test_local_current_identity_uses_kernel_creation_time_and_native_command_line(self):
        result = _local_current_process_identity()
        self.assertTrue(result["inspection_complete"])
        self.assertEqual(result["pid"], os.getpid())
        self.assertTrue(result["creation_time"].isdigit())
        self.assertTrue(result["command_line"])

    def test_duplicate_and_concurrent_activation_have_one_lane(self):
        plan, controller, _result = self._prepared()
        self.assertEqual(len(controller.enabled), 1)
        with self.assertRaises(ActivationError) as caught:
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertEqual(caught.exception.status, "activation_lane_already_owned")

    def test_prepare_seals_audit_prior_state_and_enables_before_provider_trigger(self):
        plan, controller, result = self._prepared()
        rollback = json.loads(Path(result["rollback_path"]).read_text(encoding="utf-8"))
        self.assertEqual(rollback["task_scheduler_audit_prior"], {
            "log_name": "Microsoft-Windows-TaskScheduler/Operational",
            "enabled": False,
        })
        self.assertEqual(
            rollback["task_scheduler_audit_rollback_command"],
            "wevtutil sl Microsoft-Windows-TaskScheduler/Operational /e:false",
        )
        self.assertEqual(controller.audit_enabled, [True])
        self.assertEqual(controller.enabled, [plan["task_action_sha256"]])

    def test_missing_audit_controller_fails_before_lane_acquisition(self):
        plan = self._plan()
        controller = Mock(spec=[])
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_controller_required"):
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertFalse((self.state / "activation.lock").exists())

    def test_windows_controller_enables_and_restores_exact_audit_channel(self):
        calls = []
        states = iter([False, False, True, True, False])

        def runner(command, **_kwargs):
            calls.append(command)
            if command[0] == "powershell":
                enabled = next(states)
                return subprocess.CompletedProcess(
                    command, 0,
                    json.dumps({
                        "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                        "enabled": enabled,
                    }), "",
                )
            return subprocess.CompletedProcess(command, 0, "", "")

        controller = WindowsExactTaskController(runner=runner)
        prior = controller.read_audit_channel_state()
        controller.bind_audit_channel_state(prior)
        controller.ensure_audit_channel_enabled()
        controller.restore_audit_channel_state()
        mutations = [call for call in calls if call[0] == "wevtutil"]
        self.assertEqual(mutations, [
            ["wevtutil", "sl", "Microsoft-Windows-TaskScheduler/Operational", "/e:true"],
            ["wevtutil", "sl", "Microsoft-Windows-TaskScheduler/Operational", "/e:false"],
        ])

    def test_windows_controller_rejects_audit_state_change_before_mutation(self):
        states = iter([False, True])

        def runner(command, **_kwargs):
            if command[0] == "powershell":
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": next(states),
                }), "")
            self.fail("audit mutation must not run after identity change")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_identity_changed"):
            controller.ensure_audit_channel_enabled()

    def test_windows_controller_already_enabled_does_not_mutate(self):
        calls = []

        def runner(command, **_kwargs):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, json.dumps({
                "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                "enabled": True,
            }), "")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        self.assertFalse(controller.ensure_audit_channel_enabled())
        self.assertFalse(any(call[0] == "wevtutil" for call in calls))

    def test_windows_controller_classifies_audit_access_denied(self):
        states = iter([False, False])

        def runner(command, **_kwargs):
            if command[0] == "powershell":
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": next(states),
                }), "")
            return subprocess.CompletedProcess(command, 5, "", "Access is denied.")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_access_denied"):
            controller.ensure_audit_channel_enabled()
        self.assertTrue(controller.audit_mutation_attempted)

    def test_windows_controller_classifies_audit_provider_error(self):
        states = iter([False, False])

        def runner(command, **_kwargs):
            if command[0] == "powershell":
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": next(states),
                }), "")
            return subprocess.CompletedProcess(command, 15001, "", "provider failure")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_provider_error"):
            controller.ensure_audit_channel_enabled()

    def test_windows_controller_classifies_audit_provider_launch_error(self):
        states = iter([False, False])

        def runner(command, **_kwargs):
            if command[0] == "powershell":
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": next(states),
                }), "")
            raise OSError("wevtutil unavailable")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_provider_error"):
            controller.ensure_audit_channel_enabled()

    def test_windows_controller_classifies_permission_error_as_access_denied(self):
        states = iter([False, False])

        def runner(command, **_kwargs):
            if command[0] == "powershell":
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": next(states),
                }), "")
            error = PermissionError("denied")
            error.winerror = 5
            raise error

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_access_denied"):
            controller.ensure_audit_channel_enabled()

    def test_windows_controller_classifies_hresult_access_denied(self):
        states = iter([False, False])

        def runner(command, **_kwargs):
            if command[0] == "powershell":
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": next(states),
                }), "")
            return subprocess.CompletedProcess(command, -2147024891, "", "denied")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_access_denied"):
            controller.ensure_audit_channel_enabled()

    def test_windows_controller_rejects_audit_readback_mismatch(self):
        states = iter([False, False, False])

        def runner(command, **_kwargs):
            if command[0] == "powershell":
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": next(states),
                }), "")
            return subprocess.CompletedProcess(command, 0, "", "")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_readback_mismatch"):
            controller.ensure_audit_channel_enabled()

    def test_windows_controller_normalizes_audit_readback_provider_error(self):
        reads = 0

        def runner(command, **_kwargs):
            nonlocal reads
            if command[0] == "powershell":
                reads += 1
                if reads == 3:
                    raise subprocess.TimeoutExpired(command, 30)
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": False,
                }), "")
            return subprocess.CompletedProcess(command, 0, "", "")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_provider_error"):
            controller.ensure_audit_channel_enabled()

    def test_windows_controller_reconciles_enabled_channel_to_bound_prior(self):
        calls = []
        states = iter([False, True, True, False])

        def runner(command, **_kwargs):
            calls.append(command)
            if command[0] == "powershell":
                return subprocess.CompletedProcess(command, 0, json.dumps({
                    "log_name": "Microsoft-Windows-TaskScheduler/Operational",
                    "enabled": next(states),
                }), "")
            return subprocess.CompletedProcess(command, 0, "", "")

        controller = WindowsExactTaskController(runner=runner)
        controller.bind_audit_channel_state(controller.read_audit_channel_state())
        self.assertTrue(controller.reconcile_audit_channel_state())
        self.assertIn([
            "wevtutil", "sl", "Microsoft-Windows-TaskScheduler/Operational", "/e:false",
        ], calls)

    def test_prepare_rechecks_reconciliation_lane_after_plan(self):
        plan = self._plan()
        (self.state / "activation-reconciliation.lock").write_text(
            "owned", encoding="utf-8"
        )
        with self.assertRaisesRegex(ActivationError, "activation_reconciliation_lane_active"):
            prepare_activation(plan, task_controller=Controller(),
                               task_reader=lambda: self.task, git_runner=self.git)

    def test_interrupted_prepare_restores_stop_and_disables_exact_task(self):
        plan = self._plan()
        controller = Controller(fail_start=True)
        with self.assertRaises(ActivationError):
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertEqual(self._sha(self.stop), plan["stop_marker_sha256"])
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertEqual(controller.audit_enabled, [True])
        self.assertEqual(controller.audit_restored, [])

    def test_audit_access_denied_contains_before_provider_launch(self):
        class AccessDeniedController(Controller):
            def ensure_audit_channel_enabled(self):
                self.audit_mutation_attempted = True
                raise ActivationError("task_scheduler_audit_access_denied")

        plan = self._plan()
        controller = AccessDeniedController()
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_access_denied"):
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertEqual(controller.enabled, [])
        self.assertEqual(controller.audit_restored, [])
        self.assertTrue(self.stop.exists())

    def test_audit_provider_error_contains_before_provider_launch(self):
        class ProviderErrorController(Controller):
            def ensure_audit_channel_enabled(self):
                self.audit_mutation_attempted = True
                raise ActivationError("task_scheduler_audit_provider_error")

        plan = self._plan()
        controller = ProviderErrorController()
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_provider_error"):
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertEqual(controller.enabled, [])
        self.assertEqual(controller.audit_restored, [])
        self.assertTrue(self.stop.exists())

    def test_post_mutation_readback_failure_contains_without_disabling_audit(self):
        class ReadbackFailureController(Controller):
            def ensure_audit_channel_enabled(self):
                self.audit_mutation_attempted = True
                self.audit_state["enabled"] = True
                raise ActivationError("task_scheduler_audit_readback_mismatch")

        plan = self._plan()
        controller = ReadbackFailureController()
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_readback_mismatch"):
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertEqual(controller.audit_restored, [])
        self.assertEqual(controller.enabled, [])
        self.assertTrue(self.stop.exists())

    def test_post_mutation_readback_provider_error_contains_without_disabling_audit(self):
        class ReadbackProviderErrorController(Controller):
            def ensure_audit_channel_enabled(self):
                self.audit_mutation_attempted = True
                self.audit_state["enabled"] = True
                raise ActivationError("task_scheduler_audit_provider_error")

        plan = self._plan()
        controller = ReadbackProviderErrorController()
        with self.assertRaisesRegex(ActivationError, "task_scheduler_audit_provider_error"):
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertEqual(controller.enabled, [])
        self.assertEqual(controller.audit_restored, [])
        self.assertTrue(controller.audit_state["enabled"])
        self.assertTrue(self.stop.exists())

    def test_provider_start_failure_is_recorded_without_terminal_spawn(self):
        plan, controller, _ = self._prepared()
        inspector = lambda _pid: {
            "inspection_complete": True, "pid": 10, "parent_pid": 20,
            "executable_path": self.task[0]["execute"],
            "command_line": f'"{self.task[0]["execute"]}" {self.task[0]["arguments"]}',
            "ancestry": [{"pid": 20, "executable_path": "svchost.exe",
                          "provider_identity_verified": True,
                          "instance_guid": "11111111-1111-1111-1111-111111111111",
                          "action_execute": self.task[0]["execute"],
                          "action_arguments": self.task[0]["arguments"],
                          "action_working_directory": self.task[0]["working_directory"]}],
        }
        with self.assertRaises(ActivationError) as caught:
            consume_provider_activation(
                state_root=self.state, starter=lambda **_kwargs: ({"status": "failed"}, 503),
                task_reader=lambda: self.task, provider_inspector=inspector, git_runner=self.git,
                task_controller=controller,
            )
        self.assertEqual(caught.exception.status, "provider_start_failed")
        self.assertEqual(controller.enabled, [plan["task_action_sha256"]])
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])

    def test_missing_signed_runner_ack_or_heartbeat_recovers_deterministically(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        with self.assertRaises(ActivationError) as caught:
            verify_or_recover_activation(
                state_root=self.state,
                verification_reader=lambda _packet: {
                    "loaded_revision_exact": True, "execution_mode_observe_only": True,
                    "signed_supervisor_tree": True, "signed_runner_tree": False,
                    "heartbeat_fresh": False, "activation_id_exact": True,
                    "unrelated_processes_absent": True,
                }, task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git,
            )
        self.assertEqual(caught.exception.status, "activation_verification_failed")
        self.assertTrue(self.stop.exists())
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])

    def test_verification_waits_through_stale_and_partial_publication(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        ready = {name: True for name in (
            "loaded_revision_exact", "execution_mode_observe_only",
            "signed_supervisor_tree", "signed_runner_tree", "heartbeat_fresh",
            "activation_id_exact", "unrelated_processes_absent",
        )}
        reads = iter([
            {"publication_status": "stale_publication"},
            {"publication_status": "activation_bound_startup_in_progress"},
            {**ready, "publication_status": "activation_bound_ready"},
        ])
        ticks = iter([value / 100 for value in range(100)])
        result = verify_or_recover_activation(
            state_root=self.state, verification_reader=lambda _packet: next(reads),
            task_controller=controller, task_reader=lambda: self.task,
            git_runner=self.git, readiness_timeout_seconds=1,
            monotonic_fn=lambda: next(ticks), sleep_fn=lambda _seconds: None,
        )
        self.assertEqual(result["status"], "activation_verified")
        self.assertEqual(controller.disabled, [])

    def test_stale_publication_timeout_contains_without_accepting_old_state(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        ticks = iter([0.0, 0.0, 0.2, 0.2, 0.2, 0.2])
        with self.assertRaisesRegex(ActivationError, "activation_verification_failed") as caught:
            verify_or_recover_activation(
                state_root=self.state,
                verification_reader=lambda _packet: {
                    "publication_status": "stale_publication",
                },
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git, readiness_timeout_seconds=0.1,
                monotonic_fn=lambda: next(ticks), sleep_fn=lambda _seconds: None,
            )
        self.assertEqual(caught.exception.evidence["evidence_status"],
                         "activation_readiness_timeout")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])

    def test_provider_exit_during_publication_wait_contains_immediately(self):
        plan, controller, _ = self._prepared()
        self._mark_started(packet_status="provider_pending")
        controller.instance_state = "exited"
        ticks = iter([0.0, 0.0, 0.1, 0.1, 0.1, 0.1])
        with self.assertRaisesRegex(ActivationError, "activation_verification_failed") as caught:
            verify_or_recover_activation(
                state_root=self.state, verification_reader=lambda _packet: {
                    "publication_status": "activation_bound_startup_in_progress",
                },
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git, readiness_timeout_seconds=1,
                monotonic_fn=lambda: next(ticks), sleep_fn=lambda _seconds: None,
            )
        self.assertEqual(caught.exception.evidence["evidence_status"],
                         "activation_provider_exited_before_publication")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])

    def test_ambiguous_concurrent_publication_never_waits_or_passes(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        with self.assertRaisesRegex(ActivationError, "activation_verification_failed"):
            verify_or_recover_activation(
                state_root=self.state,
                verification_reader=lambda _packet: {
                    "publication_status": "activation_evidence_ambiguous",
                },
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git, readiness_timeout_seconds=5,
                sleep_fn=lambda _seconds: self.fail("ambiguous evidence must not wait"),
            )
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])

    def test_second_verifier_cannot_race_active_readiness_owner(self):
        plan, controller, _ = self._prepared()
        self._mark_started(packet_status="provider_pending")
        marker = {
            "version": ACTIVATION_VERSION,
            "activation_id": plan["activation_id"],
            "status": "activation_readiness_pending",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "owner_expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=30)
            ).isoformat(),
        }
        marker["marker_hmac_sha256"] = hmac.new(
            self.key,
            json.dumps(marker, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        (self.state / "activation-verification.lock").write_text(
            json.dumps(marker), encoding="utf-8",
        )
        with runtime_activation._activation_verifier_lock(self.state):
            with self.assertRaisesRegex(ActivationError,
                                        "activation_verification_already_active"):
                verify_or_recover_activation(
                    state_root=self.state, verification_reader=lambda _packet: {},
                    task_controller=controller, task_reader=lambda: self.task,
                    git_runner=self.git,
                )
        self.assertEqual(controller.disabled, [])
        self.assertTrue((self.state / "activation.lock").exists())

    def test_exited_provider_allows_stale_readiness_owner_to_contain(self):
        plan, controller, _ = self._prepared()
        self._mark_started(packet_status="provider_pending")
        controller.instance_state = "exited"
        marker = {
            "version": ACTIVATION_VERSION,
            "activation_id": plan["activation_id"],
            "status": "activation_readiness_pending",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "owner_expires_at": (
                datetime.now(timezone.utc) - timedelta(seconds=1)
            ).isoformat(),
        }
        marker["marker_hmac_sha256"] = hmac.new(
            self.key,
            json.dumps(marker, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        (self.state / "activation-verification.lock").write_text(
            json.dumps(marker), encoding="utf-8",
        )
        with self.assertRaisesRegex(ActivationError,
                                    "activation_verification_failed") as caught:
            verify_or_recover_activation(
                state_root=self.state,
                verification_reader=lambda _packet: {
                    "publication_status": "activation_bound_startup_in_progress",
                },
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git,
            )
        self.assertEqual(caught.exception.evidence["evidence_status"],
                         "activation_provider_exited_before_publication")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertFalse((self.state / "activation-verification.lock").exists())

    def test_verification_marker_is_archived_only_after_completion_exists(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        evidence = {name: True for name in (
            "loaded_revision_exact", "execution_mode_observe_only",
            "signed_supervisor_tree", "signed_runner_tree", "heartbeat_fresh",
            "activation_id_exact", "unrelated_processes_absent",
        )}
        original_replace = runtime_activation._durable_replace

        def assert_completion_before_marker_archive(source, destination, **kwargs):
            if Path(source).name == "activation-verification.lock":
                self.assertTrue(
                    (self.state / "activation-verification-complete.json").exists()
                )
            return original_replace(source, destination, **kwargs)

        with patch.object(
            runtime_activation, "_durable_replace",
            side_effect=assert_completion_before_marker_archive,
        ):
            result = verify_or_recover_activation(
                state_root=self.state,
                verification_reader=lambda _packet: evidence,
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git,
            )
        self.assertEqual(result["status"], "activation_verified")
        self.assertTrue(
            (self.state / "activation-ledger"
             / f"{plan['activation_id']}-verified-activation-verification.lock").exists()
        )

    def test_completion_replay_finishes_interrupted_marker_archive_without_reverify(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        evidence = {name: True for name in (
            "loaded_revision_exact", "execution_mode_observe_only",
            "signed_supervisor_tree", "signed_runner_tree", "heartbeat_fresh",
            "activation_id_exact", "unrelated_processes_absent",
        )}
        original_replace = runtime_activation._durable_replace
        interrupted = {"value": False}

        def interrupt_marker_archive(source, destination, **kwargs):
            if (Path(source).name == "activation-verification.lock"
                    and not interrupted["value"]
                    and (self.state / "activation-verification-complete.json").exists()):
                interrupted["value"] = True
                raise OSError("simulated marker archive interruption")
            return original_replace(source, destination, **kwargs)

        with patch.object(
            runtime_activation, "_durable_replace",
            side_effect=interrupt_marker_archive,
        ):
            with self.assertRaisesRegex(OSError, "simulated marker"):
                verify_or_recover_activation(
                    state_root=self.state,
                    verification_reader=lambda _packet: evidence,
                    task_controller=controller, task_reader=lambda: self.task,
                    git_runner=self.git,
                )
        completion_path = self.state / "activation-verification-complete.json"
        completion_bytes = completion_path.read_bytes()
        result = verify_or_recover_activation(
            state_root=self.state,
            verification_reader=lambda _packet: self.fail(
                "durable completion replay must not reverify live evidence"
            ),
            task_controller=controller, task_reader=lambda: self.task,
            git_runner=self.git,
        )
        self.assertEqual(result["status"], "activation_verified")
        self.assertEqual(completion_path.read_bytes(), completion_bytes)
        self.assertEqual(controller.disabled, [])
        self.assertFalse((self.state / "activation-verification.lock").exists())

    def test_expiry_advances_during_wait_and_contains(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        expires = datetime.fromisoformat(plan["authority"]["expires_at"])
        ticks = iter([0.0, 0.0, 0.0, 0.2, 0.2, 0.2])
        with self.assertRaisesRegex(ActivationError, "activation_verification_failed") as caught:
            verify_or_recover_activation(
                state_root=self.state,
                verification_reader=lambda _packet: {
                    "publication_status": "stale_publication",
                },
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git, now=expires - timedelta(seconds=0.1),
                readiness_timeout_seconds=1,
                monotonic_fn=lambda: next(ticks), sleep_fn=lambda _seconds: None,
            )
        self.assertEqual(caught.exception.evidence["evidence_status"],
                         "activation_authority_expired")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])

    def test_non_finite_readiness_timeout_fails_closed(self):
        plan, controller, _ = self._prepared()
        self._mark_started(packet_status="provider_pending")
        with self.assertRaisesRegex(ActivationError, "activation_verification_failed") as caught:
            verify_or_recover_activation(
                state_root=self.state, verification_reader=lambda _packet: {},
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git, readiness_timeout_seconds=float("inf"),
            )
        self.assertEqual(caught.exception.evidence["evidence_status"],
                         "activation_readiness_configuration_invalid")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])

    def test_real_reader_treats_current_supervisor_with_stale_heartbeat_as_starting(self):
        packet = {"activation_id": "current", "authority": {
            "runtime_revision": SOURCE, "execution_revision": SOURCE,
        }}
        (self.state / "supervisor.json").write_text(json.dumps({
            "status": "starting", "activation_id": "current",
            "intended_runtime_revision": SOURCE,
            "intended_execution_revision": SOURCE,
        }), encoding="utf-8")
        (self.state / "runner.json").write_text(json.dumps({
            "activation_id": "old", "runner_source_commit": "old",
            "last_seen": datetime.now(timezone.utc).isoformat(),
        }), encoding="utf-8")
        evidence = read_activation_runtime_evidence(
            packet, state_root=self.state,
            live_validator=lambda *_args, **_kwargs: {
                "authorized": False, "reason": "not_published",
            },
        )
        self.assertEqual(evidence["publication_status"],
                         "activation_bound_startup_in_progress")

    def test_successful_verification_retires_packet_and_lane(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        evidence = {name: True for name in (
            "loaded_revision_exact", "execution_mode_observe_only",
            "signed_supervisor_tree", "signed_runner_tree", "heartbeat_fresh",
            "activation_id_exact", "unrelated_processes_absent",
        )}
        result = verify_or_recover_activation(
            state_root=self.state, verification_reader=lambda _packet: evidence,
            task_controller=controller, task_reader=lambda: self.task,
            git_runner=self.git,
        )
        self.assertEqual(result["status"], "activation_verified")
        self.assertFalse((self.state / "activation-packet.json").exists())
        self.assertFalse((self.state / "activation.lock").exists())
        replay = verify_or_recover_activation(
            state_root=self.state, verification_reader=lambda _packet: evidence,
            task_controller=controller, task_reader=lambda: self.task,
            git_runner=self.git, activation_id=plan["activation_id"],
        )
        self.assertEqual(replay["status"], "activation_verified")

    def test_verification_resumes_after_lane_archive_crash(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        lane = self.state / "activation.lock"
        archived_lane = (self.state / "activation-ledger"
                         / f"{plan['activation_id']}-lane.json")
        lane.replace(archived_lane)
        evidence = {name: True for name in (
            "loaded_revision_exact", "execution_mode_observe_only",
            "signed_supervisor_tree", "signed_runner_tree", "heartbeat_fresh",
            "activation_id_exact", "unrelated_processes_absent",
        )}

        result = verify_or_recover_activation(
            state_root=self.state, verification_reader=lambda _packet: evidence,
            task_controller=controller, task_reader=lambda: self.task,
            git_runner=self.git,
        )

        self.assertEqual(result["status"], "activation_verified")
        self.assertFalse((self.state / "activation-packet.json").exists())

    def test_verification_failure_after_lane_archive_recovers(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        lane = self.state / "activation.lock"
        archived_lane = (self.state / "activation-ledger"
                         / f"{plan['activation_id']}-lane.json")
        lane.replace(archived_lane)

        with self.assertRaisesRegex(ActivationError, "activation_verification_failed"):
            verify_or_recover_activation(
                state_root=self.state,
                verification_reader=lambda _packet: {},
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git,
            )

        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertTrue(self.stop.exists())

    def test_verification_resumes_after_packet_archive_interruption(self):
        plan, controller, _ = self._prepared()
        self._mark_started()
        evidence = {name: True for name in (
            "loaded_revision_exact", "execution_mode_observe_only",
            "signed_supervisor_tree", "signed_runner_tree", "heartbeat_fresh",
            "activation_id_exact", "unrelated_processes_absent",
        )}
        def interrupt_after_packet(source, target, **kwargs):
            if source.name.startswith("activation-audit-receipt-"):
                raise OSError("simulated verified archival interruption")
            return _durable_replace(source, target, **kwargs)

        with patch("modules.charlie.runtime_activation._durable_replace",
                   side_effect=interrupt_after_packet):
            with self.assertRaisesRegex(OSError, "verified archival interruption"):
                verify_or_recover_activation(
                    state_root=self.state, verification_reader=lambda _packet: evidence,
                    task_controller=controller, task_reader=lambda: self.task,
                    git_runner=self.git,
                )

        result = verify_or_recover_activation(
            state_root=self.state, verification_reader=lambda _packet: evidence,
            task_controller=controller, task_reader=lambda: self.task,
            git_runner=self.git, activation_id=plan["activation_id"],
        )
        self.assertEqual(result["status"], "activation_verified")

    def test_tampered_rollback_fails_closed_and_retains_lane(self):
        plan, controller, _ = self._prepared()
        rollback_path = self.state / "activation-ledger" / f"{plan['activation_id']}-rollback.json"
        rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
        rollback["stop_marker_sha256"] = "0" * 64
        rollback_path.write_text(json.dumps(rollback), encoding="utf-8")
        with self.assertRaises(ActivationError) as caught:
            recover_activation(state_root=self.state, task_controller=controller,
                               activation_id=plan["activation_id"])
        self.assertEqual(caught.exception.status, "activation_rollback_signature_invalid")
        self.assertTrue((self.state / "activation.lock").exists())

    def test_recovery_rejects_pre_runex_seed_after_audit_receipt(self):
        plan, controller, _ = self._prepared()
        (self.state / "activation-ledger"
         / f"{plan['activation_id']}-rollback.json").unlink()
        (self.state / "activation-packet.json").unlink()

        with self.assertRaisesRegex(ActivationError, "activation_recovery_incomplete"):
            recover_activation(
                state_root=self.state, task_controller=controller,
                activation_id=plan["activation_id"],
                failure_evidence={"status": "prepare_durable_write_interrupted"},
            )

        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertTrue(self.stop.exists())
        self.assertFalse((self.state / "activation-packet.json").exists())

    def test_recovery_reconstructs_only_proven_pre_runex_lane_seed(self):
        plan, controller, _ = self._prepared()
        (self.state / "activation-ledger"
         / f"{plan['activation_id']}-rollback.json").unlink()
        (self.state / "activation-packet.json").unlink()
        (self.state / f"activation-audit-intent-{plan['activation_id']}.json").unlink()
        (self.state / f"activation-audit-receipt-{plan['activation_id']}.json").unlink()

        result = recover_activation(
            state_root=self.state, task_controller=controller,
            activation_id=plan["activation_id"],
            failure_evidence={"status": "prepare_durable_write_interrupted"},
        )

        self.assertEqual(result["status"], "activation_recovered")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertTrue(self.stop.exists())

    def test_recovery_reconstructs_post_runex_packet_from_consumed_identity(self):
        plan, controller, _ = self._prepared()
        packet_path = self.state / "activation-packet.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        consumed = {
            "version": ACTIVATION_VERSION,
            "activation_id": plan["activation_id"],
            "provider_pid": 10,
            "provider_parent_pid": 20,
            "provider_instance_guid": packet["expected_instance_guid"],
            "expected_instance_guid": packet["expected_instance_guid"],
            "packet_hmac_sha256": packet["packet_hmac_sha256"],
        }
        unsigned = dict(consumed)
        consumed["consumed_hmac_sha256"] = hmac.new(
            self.key, json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        (self.state / f"activation-consumed-{plan['activation_id']}.json").write_text(
            json.dumps(consumed), encoding="utf-8"
        )
        packet_path.unlink()

        result = recover_activation(
            state_root=self.state, task_controller=controller,
            activation_id=plan["activation_id"],
            failure_evidence={"status": "consumed_pending_interrupted"},
        )

        self.assertEqual(result["status"], "activation_recovered")
        recovered = json.loads((
            self.state / "activation-ledger"
            / f"{plan['activation_id']}-recovered-activation-packet.json"
        ).read_text(encoding="utf-8"))
        self.assertEqual(recovered["expected_instance_guid"], packet["expected_instance_guid"])
        self.assertEqual(recovered["packet_hmac_sha256"], packet["packet_hmac_sha256"])

    def test_pending_packet_with_consumed_identity_requires_recovery(self):
        plan, _controller, _ = self._prepared()
        packet_path = self.state / "activation-packet.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        consumed = {
            "version": ACTIVATION_VERSION,
            "activation_id": plan["activation_id"],
            "provider_pid": 10,
            "provider_parent_pid": 20,
            "provider_instance_guid": packet["expected_instance_guid"],
            "expected_instance_guid": packet["expected_instance_guid"],
            "packet_hmac_sha256": packet["packet_hmac_sha256"],
        }
        consumed["consumed_hmac_sha256"] = hmac.new(
            self.key,
            json.dumps(consumed, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        (self.state / f"activation-consumed-{plan['activation_id']}.json").write_text(
            json.dumps(consumed), encoding="utf-8"
        )

        with self.assertRaisesRegex(ActivationError,
                                    "activation_consumed_pending_recovery_required"):
            _validate_packet(
                packet, self.state, lambda: self.task,
                git_runner=self.git,
            )

    def test_verification_never_replays_completion_over_active_lane(self):
        _plan, controller, _ = self._prepared()
        (self.state / "activation-packet.json").unlink()
        (self.state / "activation-verification-complete.json").write_text(
            json.dumps({"status": "activation_verified"}), encoding="utf-8"
        )

        with self.assertRaisesRegex(ActivationError,
                                    "activation_packet_missing_for_active_lane"):
            verify_or_recover_activation(
                state_root=self.state, verification_reader=lambda _packet: {},
                task_controller=controller, task_reader=lambda: self.task,
                git_runner=self.git,
            )

    def test_rollback_write_failure_retains_signed_lane_for_recovery(self):
        plan = self._plan()
        controller = Controller()
        with patch("modules.charlie.runtime_activation._atomic_json",
                   side_effect=OSError("simulated rollback write failure")):
            with self.assertRaisesRegex(OSError, "rollback write failure"):
                prepare_activation(
                    plan, task_controller=controller,
                    task_reader=lambda: self.task, git_runner=self.git,
                )
        self.assertTrue((self.state / "activation.lock").exists())

        result = recover_activation(
            state_root=self.state, task_controller=controller,
            activation_id=plan["activation_id"],
            failure_evidence={"status": "rollback_write_interrupted"},
        )
        self.assertEqual(result["status"], "activation_recovered")

    def test_prepare_failure_permanently_consumes_activation_identity(self):
        plan = self._plan()
        controller = Controller(fail_start=True)
        with self.assertRaisesRegex(ActivationError, "provider_start_failed"):
            prepare_activation(
                plan, task_controller=controller,
                task_reader=lambda: self.task, git_runner=self.git,
            )
        controller.fail_start = False

        with self.assertRaisesRegex(ActivationError, "activation_identity_already_used"):
            prepare_activation(
                plan, task_controller=controller,
                task_reader=lambda: self.task, git_runner=self.git,
            )

    def test_recovery_disables_only_exact_task_and_restores_exact_stop(self):
        plan, controller, _ = self._prepared()
        result = recover_activation(
            state_root=self.state, task_controller=controller,
            activation_id=plan["activation_id"],
            failure_evidence={"status": "test_activation_failure"},
        )
        self.assertEqual(result["status"], "activation_recovered")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertEqual(self._sha(self.stop), plan["stop_marker_sha256"])
        self.assertEqual(controller.audit_restored, [])

    def test_recovery_retires_pre_intent_crash_after_task_and_stop_containment(self):
        plan, controller, _ = self._prepared()
        (self.state / f"activation-audit-intent-{plan['activation_id']}.json").unlink()
        result = recover_activation(
            state_root=self.state, task_controller=controller,
            activation_id=plan["activation_id"],
            failure_evidence={"status": "audit_intent_write_interrupted"})
        self.assertEqual(result["status"], "activation_recovered")
        self.assertEqual(controller.audit_restored, [])
        self.assertFalse((self.state / "activation.lock").exists())
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertTrue(self.stop.exists())

    def test_recovery_retires_post_mutation_receipt_crash_after_containment(self):
        plan, controller, _ = self._prepared()
        (self.state / f"activation-audit-receipt-{plan['activation_id']}.json").unlink()
        result = recover_activation(
            state_root=self.state, task_controller=controller,
            activation_id=plan["activation_id"],
            failure_evidence={"status": "audit_receipt_write_interrupted"})
        self.assertEqual(result["status"], "activation_recovered")
        self.assertEqual(controller.audit_restored, [])
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertTrue(self.stop.exists())

    def test_recovery_contains_from_signed_rollback_before_rejecting_tampered_packet(self):
        plan, controller, _ = self._prepared()
        packet_path = self.state / "activation-packet.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        packet["task_ownership"][0]["task_name"] = "Unrelated Task"
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        with self.assertRaisesRegex(ActivationError, "activation_recovery_incomplete"):
            recover_activation(state_root=self.state, task_controller=controller,
                               activation_id=plan["activation_id"])
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertEqual(controller.audit_restored, [])
        self.assertTrue(self.stop.exists())

    def test_recovery_resumes_after_audit_artifacts_were_archived(self):
        plan, controller, _ = self._prepared()
        def interrupt_lane_archive(source, target, **kwargs):
            if source.name == "activation.lock":
                raise OSError("simulated lane archive interruption")
            return _durable_replace(source, target, **kwargs)

        with patch("modules.charlie.runtime_activation._durable_replace",
                   side_effect=interrupt_lane_archive):
            with self.assertRaisesRegex(OSError, "lane archive interruption"):
                recover_activation(state_root=self.state, task_controller=controller,
                                   activation_id=plan["activation_id"],
                                   failure_evidence={"status": "test_failure"})
        result = recover_activation(state_root=self.state, task_controller=controller,
                                    activation_id=plan["activation_id"],
                                    failure_evidence={"status": "test_failure"})
        self.assertEqual(result["status"], "activation_recovered")

    def test_authenticated_v1_lane_remains_containable(self):
        plan, controller, _ = self._prepared()
        packet_path = self.state / "activation-packet.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        packet["version"] = "charlie_provider_activation_v1"
        unsigned_packet = {k: v for k, v in packet.items() if k != "packet_hmac_sha256"}
        packet["packet_hmac_sha256"] = hmac.new(
            self.key, json.dumps(unsigned_packet, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
        rollback_path = self.state / "activation-ledger" / f"{plan['activation_id']}-rollback.json"
        rollback = json.loads(rollback_path.read_text(encoding="utf-8"))
        rollback["version"] = "charlie_provider_activation_v1"
        for field in ("task_ownership", "task_scheduler_audit_prior",
                      "task_scheduler_audit_mutation_required",
                      "task_scheduler_audit_rollback_command"):
            rollback.pop(field, None)
        unsigned_rollback = {k: v for k, v in rollback.items()
                             if k != "rollback_hmac_sha256"}
        rollback["rollback_hmac_sha256"] = hmac.new(
            self.key, json.dumps(unsigned_rollback, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        rollback_path.write_text(json.dumps(rollback), encoding="utf-8")
        result = recover_activation(state_root=self.state, task_controller=controller,
                                    activation_id=plan["activation_id"],
                                    failure_evidence={"status": "legacy_test_failure"})
        self.assertEqual(result["status"], "activation_recovered")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertTrue(self.stop.exists())

    def _reconcile(self, plan, **changes):
        values = {
            "state_root": self.state,
            "activation_id": plan["activation_id"],
            "failure_evidence": {"status": "provider_identity_incomplete", "started": False},
            "task_reader": lambda: self.task,
            "process_presence_reader": lambda _pid: "absent",
        }
        values.update(changes)
        return reconcile_recovered_activation_stop(**values)

    def test_authenticated_recovery_projects_governed_stop_and_preserves_failure(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"], failure_evidence={"status": "provider_identity_incomplete"})
        result = self._reconcile(plan)
        self.assertEqual(result["status"], "governed_stop_active")
        failure_path = Path(result["historical_failure_path"])
        self.assertTrue(failure_path.is_file())
        failure = json.loads(failure_path.read_text())
        self.assertEqual(
            json.loads(base64.b64decode(failure["failure_bytes_b64"])),
            {"status": "provider_identity_incomplete"},
        )
        self.assertTrue(Path(result["recovered_packet_path"]).is_file())
        self.assertFalse((self.state / "activation-reconciliation-pending.json").exists())
        _validate_recovery_projection(result, self.state)

    def test_reconciliation_replay_is_no_effect_and_keeps_history(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"], failure_evidence={"status": "provider_identity_incomplete"})
        first = self._reconcile(plan)
        before = Path(first["historical_failure_path"]).read_bytes()
        watchdog_before = (self.state / "watchdog.json").read_bytes()
        second = self._reconcile(plan, failure_evidence=first)
        self.assertEqual(second["status"], "governed_stop_active")
        self.assertEqual(Path(second["historical_failure_path"]).read_bytes(), before)
        self.assertEqual((self.state / "watchdog.json").read_bytes(), watchdog_before)

    def test_reconciliation_resumes_after_pending_archive_before_projection_write(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        original_atomic = __import__(
            "modules.charlie.runtime_activation", fromlist=["_atomic_json"]
        )._atomic_json

        def interrupt_projection(path, payload):
            if Path(path).name == "watchdog.json":
                raise OSError("simulated projection interruption")
            return original_atomic(path, payload)

        with patch("modules.charlie.runtime_activation._atomic_json", interrupt_projection):
            with self.assertRaisesRegex(OSError, "projection interruption"):
                self._reconcile(plan)
        self.assertTrue((self.state / "activation-reconciliation.lock").exists())
        self.assertTrue((self.state / "activation-ledger" /
                         f"{plan['activation_id']}-reconciled.json").exists())
        result = self._reconcile(plan)
        self.assertEqual(result["status"], "governed_stop_active")
        self.assertFalse((self.state / "activation-reconciliation.lock").exists())

    def test_reconciliation_replay_finishes_interrupted_lock_archive(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        def interrupt_lock(source, target, **kwargs):
            if source.name == "activation-reconciliation.lock":
                raise OSError("simulated lock archive interruption")
            return _durable_replace(source, target, **kwargs)

        with patch("modules.charlie.runtime_activation._durable_replace",
                   side_effect=interrupt_lock):
            with self.assertRaisesRegex(OSError, "lock archive interruption"):
                self._reconcile(plan)
        before = (self.state / "watchdog.json").read_bytes()
        result = self._reconcile(plan)
        self.assertEqual(result["status"], "governed_stop_active")
        self.assertEqual((self.state / "watchdog.json").read_bytes(), before)
        self.assertFalse((self.state / "activation-reconciliation.lock").exists())

    def test_reconciliation_replay_binds_reconciled_bytes(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        result = self._reconcile(plan)
        Path(result["reconciled_path"]).write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(ActivationError, "activation_reconciliation_replay_conflict"):
            self._reconcile(plan)

    def test_reconciliation_rejects_recorded_process_that_is_still_live(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        (self.state / "supervisor.json").write_text(
            json.dumps({"status": "supervisor_stopped", "pid": 1234}), encoding="utf-8"
        )
        with self.assertRaisesRegex(ActivationError, "activation_reconciliation_process_still_live"):
            self._reconcile(plan, process_presence_reader=lambda _pid: "live")

    def test_reconciliation_rejects_surviving_process_tree_member(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        (self.state / "supervisor.json").write_text(json.dumps({
            "status": "supervisor_stopped", "pid": 987654, "child_pid": 987655,
            "process_tree_identity": {"members": [{"pid": 1234}]},
        }), encoding="utf-8")
        with self.assertRaisesRegex(ActivationError, "activation_reconciliation_process_still_live"):
            self._reconcile(
                plan,
                process_presence_reader=lambda pid: "live" if int(pid) == 1234 else "absent",
            )

    def test_reconciliation_rejects_surviving_process_tree_root(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        (self.state / "supervisor.json").write_text(json.dumps({
            "status": "supervisor_stopped", "pid": 987654,
            "process_tree_identity": {"root": {"pid": 1234}, "members": []},
        }), encoding="utf-8")
        with self.assertRaisesRegex(ActivationError, "activation_reconciliation_process_still_live"):
            self._reconcile(
                plan,
                process_presence_reader=lambda pid: "live" if int(pid) == 1234 else "absent",
            )

    def test_reconciliation_rejects_missing_or_unreadable_process_proof(self):
        for mode in ("missing", "unknown"):
            with self.subTest(mode=mode):
                if mode == "unknown":
                    self.tearDown(); self.setUp()
                plan, controller, _ = self._prepared()
                recover_activation(state_root=self.state, task_controller=controller,
                                   activation_id=plan["activation_id"],
                                   failure_evidence={"status": "provider_identity_incomplete"})
                if mode == "missing":
                    (self.state / "supervisor.json").write_text(
                        json.dumps({"status": "supervisor_stopped"}), encoding="utf-8"
                    )
                    expected = "activation_reconciliation_process_identity_missing"
                else:
                    expected = "activation_reconciliation_process_proof_unavailable"
                with self.assertRaisesRegex(ActivationError, expected):
                    self._reconcile(
                        plan,
                        process_presence_reader=lambda _pid: (
                            "unknown" if mode == "unknown" else "absent"
                        ),
                    )

    def test_interrupted_owned_reconciliation_resumes_only_after_owner_is_absent(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        lock = self.state / "activation-reconciliation.lock"
        lock.write_text(json.dumps({
            "version": "charlie_activation_recovery_projection_v1",
            "activation_id": plan["activation_id"],
            "status": "activation_reconciliation_owned",
            "owner_pid": 1234,
        }), encoding="utf-8")
        with self.assertRaisesRegex(ActivationError, "activation_reconciliation_lane_active"):
            self._reconcile(plan, process_presence_reader=lambda _pid: "live")
        result = self._reconcile(plan, process_presence_reader=lambda _pid: "absent")
        self.assertEqual(result["status"], "governed_stop_active")

    def test_staging_rejects_missing_recovered_lane_archive(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        result = self._reconcile(plan)
        Path(result["recovered_lane_path"]).unlink()
        with self.assertRaisesRegex(RuntimeError, "watchdog_recovery_projection_archive_mismatch"):
            _validate_recovery_projection(result, self.state)

    def test_historical_completed_recovery_can_be_reconciled_exactly(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"], failure_evidence={"status": "provider_identity_incomplete"})
        (self.state / "activation-reconciliation-pending.json").unlink()
        (self.state / "activation-ledger" / f"{plan['activation_id']}-recovery-completed.json").unlink()
        result = self._reconcile(plan)
        self.assertEqual(result["status"], "governed_stop_active")
        self.assertTrue((self.state / "activation-ledger" /
                         f"{plan['activation_id']}-reconciled.json").is_file())

    def test_partial_rollback_or_substituted_task_stop_packet_is_rejected(self):
        mutations = ("task", "stop", "packet")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                if mutation != mutations[0]:
                    self.tearDown(); self.setUp()
                plan, controller, _ = self._prepared()
                recover_activation(state_root=self.state, task_controller=controller,
                                   activation_id=plan["activation_id"], failure_evidence={"status": "provider_identity_incomplete"})
                task_reader = lambda: self.task
                if mutation == "task":
                    substituted = [dict(self.task[0], arguments="substituted")]
                    task_reader = lambda: substituted
                elif mutation == "stop":
                    self.stop.write_text("substituted", encoding="utf-8")
                else:
                    packet = self.state / "activation-ledger" / f"{plan['activation_id']}-recovered-activation-packet.json"
                    packet.write_text("{}", encoding="utf-8")
                with self.assertRaises(ActivationError):
                    self._reconcile(plan, task_reader=task_reader)
                self.assertFalse((self.state / "watchdog.json").exists())

    def test_reconciliation_rejects_active_lane_and_running_supervisor(self):
        for partial in ("lane", "supervisor"):
            with self.subTest(partial=partial):
                if partial == "supervisor":
                    self.tearDown(); self.setUp()
                plan, controller, _ = self._prepared()
                recover_activation(state_root=self.state, task_controller=controller,
                                   activation_id=plan["activation_id"], failure_evidence={"status": "provider_identity_incomplete"})
                if partial == "lane":
                    (self.state / "release-staging.lock").write_text("owned", encoding="utf-8")
                else:
                    (self.state / "supervisor.json").write_text(
                        json.dumps({"status": "supervisor_running"}), encoding="utf-8")
                with self.assertRaises(ActivationError):
                    self._reconcile(plan)

    def test_reconciliation_rejects_supervisor_lock(self):
        plan, controller, _ = self._prepared()
        recover_activation(state_root=self.state, task_controller=controller,
                           activation_id=plan["activation_id"],
                           failure_evidence={"status": "provider_identity_incomplete"})
        (self.state / "supervisor.lock").write_text("owned", encoding="utf-8")
        with self.assertRaisesRegex(ActivationError, "activation_reconciliation_lane_active"):
            self._reconcile(plan)

    def test_interrupted_archive_recovery_resumes_without_replaying_activation(self):
        plan, controller, _ = self._prepared()
        packet = self.state / "activation-packet.json"
        archive = self.state / "activation-ledger" / f"{plan['activation_id']}-recovered-activation-packet.json"
        def interrupted(*_args):
            packet.replace(archive)
            raise OSError("simulated interruption")
        with patch("modules.charlie.runtime_activation._archive_activation_artifacts", interrupted):
            with self.assertRaises(OSError):
                recover_activation(
                    state_root=self.state, task_controller=controller,
                    activation_id=plan["activation_id"],
                    failure_evidence={"status": "provider_identity_incomplete"},
                )
        self.assertTrue((self.state / "activation.lock").exists())
        result = recover_activation(
            state_root=self.state, task_controller=controller,
            activation_id=plan["activation_id"],
            failure_evidence={"status": "provider_identity_incomplete"},
        )
        self.assertEqual(result["status"], "activation_recovered")

    def test_no_codex_terminal_relay_or_unrelated_targeting_api_exists(self):
        source = Path(__file__).parents[1] / "modules" / "charlie" / "runtime_activation.py"
        text = source.read_text(encoding="utf-8").casefold()
        self.assertNotIn("taskkill", text)
        self.assertNotIn("terminate(", text)
        self.assertNotIn("get-process", text)
        self.assertNotIn("win32_process |", text)


if __name__ == "__main__":
    unittest.main()
