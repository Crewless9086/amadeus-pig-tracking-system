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

from modules.charlie.runtime_activation import (
    ACTIVATION_VERSION,
    AUTHORITY_VERSION,
    ActivationError,
    consume_provider_activation,
    inspect_current_provider_chain,
    plan_activation,
    prepare_activation,
    recover_activation,
    verify_or_recover_activation,
    verify_provider_origin,
)


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

    def enable_and_trigger_exact(self, digest):
        self.enabled.append(digest)
        if self.fail_start:
            raise ActivationError("provider_start_failed")

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
            "task_name": "CHARLIE CORE Runner Watchdog", "state": "Disabled",
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
        provider = lambda _pid: {
            "inspection_complete": True, "pid": os.getpid(), "parent_pid": 20,
            "executable_path": "C:/Python/pythonw.exe",
            "ancestry": [{"pid": 20, "executable_path": "C:/Windows/System32/svchost.exe"}],
        }
        self.assertTrue(verify_provider_origin(provider)["authorized"])

    def test_direct_terminal_spawn_and_protected_ancestry_are_rejected(self):
        for executable in ("powershell.exe", "codex.exe", "cmd.exe"):
            result = verify_provider_origin(lambda _pid, executable=executable: {
                "inspection_complete": True, "pid": 10, "parent_pid": 20,
                "executable_path": "C:/Python/pythonw.exe",
                "ancestry": [{"pid": 20, "executable_path": f"C:/{executable}"}],
            })
            self.assertFalse(result["authorized"])

    def test_bounded_provider_inspection_queries_only_exact_ancestry_pids(self):
        calls = []
        rows = {
            100: {"ProcessId": 100, "ParentProcessId": 50, "ExecutablePath": "pythonw.exe"},
            50: {"ProcessId": 50, "ParentProcessId": 0, "ExecutablePath": "svchost.exe"},
        }
        def runner(command, **_kwargs):
            calls.append(command[-1])
            pid = 100 if "ProcessId=100" in command[-1] else 50
            return subprocess.CompletedProcess(command, 0, json.dumps(rows[pid]), "")
        result = inspect_current_provider_chain(100, runner=runner)
        self.assertTrue(result["inspection_complete"])
        self.assertEqual(len(calls), 2)
        self.assertTrue(all("Get-CimInstance Win32_Process -Filter \"ProcessId=" in call for call in calls))

    def test_duplicate_and_concurrent_activation_have_one_lane(self):
        plan, controller, _result = self._prepared()
        self.assertEqual(len(controller.enabled), 1)
        with self.assertRaises(ActivationError) as caught:
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertEqual(caught.exception.status, "activation_lane_already_owned")

    def test_interrupted_prepare_restores_stop_and_disables_exact_task(self):
        plan = self._plan()
        controller = Controller(fail_start=True)
        with self.assertRaises(ActivationError):
            prepare_activation(plan, task_controller=controller,
                               task_reader=lambda: self.task, git_runner=self.git)
        self.assertEqual(self._sha(self.stop), plan["stop_marker_sha256"])
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])

    def test_provider_start_failure_is_recorded_without_terminal_spawn(self):
        plan, controller, _ = self._prepared()
        inspector = lambda _pid: {
            "inspection_complete": True, "pid": 10, "parent_pid": 20,
            "executable_path": "pythonw.exe",
            "ancestry": [{"pid": 20, "executable_path": "svchost.exe"}],
        }
        with self.assertRaises(ActivationError) as caught:
            consume_provider_activation(
                state_root=self.state, starter=lambda **_kwargs: ({"status": "failed"}, 503),
                task_reader=lambda: self.task, provider_inspector=inspector, git_runner=self.git,
            )
        self.assertEqual(caught.exception.status, "provider_start_failed")
        self.assertEqual(controller.enabled, [plan["task_action_sha256"]])

    def test_missing_signed_runner_ack_or_heartbeat_recovers_deterministically(self):
        plan, controller, _ = self._prepared()
        packet_path = self.state / "activation-packet.json"
        packet = json.loads(packet_path.read_text(encoding="utf-8"))
        packet["status"] = "provider_started_observe_only"
        unsigned = {k: v for k, v in packet.items() if k != "packet_hmac_sha256"}
        packet["packet_hmac_sha256"] = hmac.new(
            self.key, json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256
        ).hexdigest()
        packet_path.write_text(json.dumps(packet), encoding="utf-8")
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

    def test_recovery_disables_only_exact_task_and_restores_exact_stop(self):
        plan, controller, _ = self._prepared()
        result = recover_activation(
            state_root=self.state, task_controller=controller,
            activation_id=plan["activation_id"],
        )
        self.assertEqual(result["status"], "activation_recovered")
        self.assertEqual(controller.disabled, [plan["task_action_sha256"]])
        self.assertEqual(self._sha(self.stop), plan["stop_marker_sha256"])

    def test_no_codex_terminal_relay_or_unrelated_targeting_api_exists(self):
        source = Path(__file__).parents[1] / "modules" / "charlie" / "runtime_activation.py"
        text = source.read_text(encoding="utf-8").casefold()
        self.assertNotIn("taskkill", text)
        self.assertNotIn("terminate(", text)
        self.assertNotIn("get-process", text)
        self.assertNotIn("win32_process |", text)


if __name__ == "__main__":
    unittest.main()
