"""Production-shaped provider redirector and failed-before-starter recovery tests."""
import copy
import hashlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from types import SimpleNamespace

from modules.charlie import runtime_activation as a
from modules.charlie import runtime_staging as staging
from tests import test_charlie_runtime_activation as fixture


class ProviderProcessChainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.execute = str(self.root / "venv" / "Scripts" / "python.exe")
        self.base = str(self.root / "base" / "python.exe")
        self.script = str(self.root / "scripts" / "charlie_runner_task_launcher.py")
        self.task = [{"execute": self.execute, "arguments": f'"{self.script}"',
                      "working_directory": str(self.root)}]
        self.pair = {"execute": self.execute, "base_executable": self.base,
                     "configuration_sha256": "1" * 64, "execute_sha256": "2" * 64,
                     "base_sha256": "3" * 64}
        self.action = {"inspection_complete": True, "pid": 101, "parent_pid": 50,
                       "executable_path": self.execute, "creation_time": "2026-10-12T18:01:28+00:00",
                       "command_line": f'"{self.execute}" "{self.script}"'}
        self.current = {**self.action, "pid": 102, "parent_pid": 101,
                        "executable_path": self.base, "creation_time": "2026-10-12T18:01:29+00:00",
                        "command_line": f'"{self.base}" "{self.script}"'}
        self.provider = {
            "inspection_complete": True, "pid": 50, "creation_time": "provider-created",
            "service_name": "Schedule", "service_state": "Running", "start_name": "LocalSystem",
            "executable_path": "C:/Windows/System32/svchost.exe",
            "service_binary_path": "C:/Windows/System32/svchost.exe -k netsvcs -p",
            "service_dll": "C:/Windows/System32/schedsvc.dll", "system_root": "C:/Windows",
            "engine_pid": 101, "instance_guid": "11111111-1111-1111-1111-111111111111",
            "task_path": "\\CHARLIE CORE Runner Watchdog",
            "provider_identity_verified": True, "current_action": self.execute,
            "action_execute": self.execute, "action_arguments": f'"{self.script}"',
            "action_working_directory": str(self.root)}
    def inspect(self, current=None, action=None, provider=None):
        with patch.object(a, "_configured_provider_pair", return_value=self.pair), \
             patch.object(a, "_inspect_exact_process", return_value=action or self.action):
            return a.inspect_current_provider_chain(
                102, current_identity=lambda: current or self.current,
                provider_identity=lambda: provider or self.provider, expected_task=self.task)
    def test_exact_venv_redirector_chain_and_configured_console_interpreter(self):
        result = self.inspect()
        self.assertTrue(result["inspection_complete"], result)
        with patch.object(a, "_configured_provider_pair", return_value=self.pair):
            decision = a.verify_provider_origin(lambda _: result, expected_task=self.task)
        self.assertTrue(decision["authorized"], decision)
        self.assertEqual((decision["pid"], decision["action_pid"]), (102, 101))
        self.assertEqual([row["pid"] for row in result["ancestry"]], [101, 50])
    def test_scheduler_lookup_uses_proven_action_pid_not_executing_pid(self):
        with patch.object(a, "_configured_provider_pair", return_value=self.pair), \
             patch.object(a, "_inspect_exact_process", return_value=self.action), \
             patch.object(a, "_inspect_windows_task_scheduler_provider", return_value=self.provider) as lookup, \
             patch.object(a, "os", SimpleNamespace(name="nt", getpid=os.getpid)):
            result = a.inspect_current_provider_chain(102, expected_task=self.task,
                current_identity=lambda: self.current)
        self.assertTrue(result["inspection_complete"], result)
        self.assertEqual([call.args[0] for call in lookup.call_args_list], [101, 101])
    def test_wrong_interpreter_action_parent_command_or_chronology_refused(self):
        variants = [
            ({"executable_path": str(self.root / "other" / "python.exe")}, {}),
            ({"parent_pid": 999}, {}),
            ({"command_line": f'"{self.base}" -c "bad"'}, {}),
            ({"command_line": f'"{self.execute}" "{self.script}"'}, {}),
            ({}, {"executable_path": str(self.root / "other" / "python.exe")}),
            ({}, {"command_line": f'"{self.execute}" "{self.script}" --extra'}),
            ({"creation_time": "2026-10-12T18:01:27+00:00"}, {}),
            ({}, {"parent_pid": 77}),
        ]
        for current, action in variants:
            with self.subTest(current=current, action=action):
                result = self.inspect({**self.current, **current}, {**self.action, **action})
                self.assertFalse(result["inspection_complete"], result)
    def test_exact_action_pid_required_by_scheduler(self):
        self.assertFalse(self.inspect(provider={**self.provider, "engine_pid": 102})["inspection_complete"])
    def test_stable_second_read_and_configuration_required(self):
        for field, changed in (("creation_time", "2026-10-12T18:01:30+00:00"),
                               ("command_line", "changed"), ("parent_pid", 51)):
            reads = iter([self.action, self.action, {**self.action, field: changed}])
            with self.subTest(field=field), patch.object(a, "_configured_provider_pair", return_value=self.pair), \
                 patch.object(a, "_inspect_exact_process", side_effect=lambda *args, **kwargs: next(reads)):
                result = a.inspect_current_provider_chain(102, expected_task=self.task,
                    current_identity=lambda: self.current, provider_identity=lambda: self.provider)
                self.assertFalse(result["inspection_complete"])
        with patch.object(a, "_configured_provider_pair", side_effect=[self.pair, {**self.pair, "base_sha256": "4"*64}]), \
             patch.object(a, "_inspect_exact_process", return_value=self.action):
            result = a.inspect_current_provider_chain(102, expected_task=self.task,
                current_identity=lambda: self.current, provider_identity=lambda: self.provider)
        self.assertEqual(result["reason"], "provider_interpreter_configuration_changed")
    def test_protected_or_extra_intermediary_not_collapsed(self):
        result = self.inspect()
        for middle in ("powershell.exe", "other.exe"):
            changed = copy.deepcopy(result)
            changed["ancestry"].insert(1, {"pid": 66, "executable_path": middle})
            with patch.object(a, "_configured_provider_pair", return_value=self.pair):
                self.assertFalse(a.verify_provider_origin(lambda _: changed, expected_task=self.task)["authorized"])
    def test_provider_chronology_normalizes_kernel_filetime_and_utc_cim(self):
        current = {**self.current, "creation_time": str(
            int(datetime.fromisoformat("2026-10-12T18:01:29+00:00").timestamp() * 10000000)
            + 116444736000000000)}
        self.assertEqual(a._provider_chain_chronology(self.action, current), "")
        self.assertTrue(a._provider_chain_chronology(
            {**self.action, "creation_time": "2026-10-12T18:01:30+00:00"}, current))
        commands = []
        result = a._inspect_exact_process(101, creation_time_utc=True,
            runner=lambda command, **kwargs: commands.append(command[-1]) or subprocess.CompletedProcess(
                command, 0, json.dumps({"ProcessId":101,"ParentProcessId":50,"ExecutablePath":self.execute,
                "CreationDate":self.action["creation_time"],"CommandLine":self.action["command_line"]}), ""))
        self.assertIn("ToUniversalTime().ToString('o')", commands[0])
        self.assertEqual(result["creation_time"], self.action["creation_time"])

    def test_config_binding_uses_governed_executable_and_real_pyvenv_configuration(self):
        execute, base = Path(self.execute), Path(self.base)
        execute.parent.mkdir(parents=True); base.parent.mkdir(parents=True)
        execute.write_bytes(b"fixture-redirector"); base.write_bytes(b"fixture-base")
        config = execute.parent.parent / "pyvenv.cfg"
        config.write_text(f"home = {base.parent}\nexecutable = {base}\n")
        with patch.object(a, "governed_runtime_binding", return_value={"interpreter": self.execute}), \
             patch.object(a.sys, "executable", self.execute), patch.object(a.sys, "_base_executable", self.base):
            pair = a._configured_provider_pair(self.task)
            self.assertEqual(pair["base_sha256"], hashlib.sha256(b"fixture-base").hexdigest())
            config.write_text(f"home = {base.parent}\nexecutable = {execute}\n")
            nested = a._configured_provider_pair(self.task)
            self.assertEqual(nested["base_executable"], str(base.resolve()))
            config.write_text(f"home = {base.parent / 'wrong'}\nexecutable = {base}\n")
            with self.assertRaises(a.ActivationError): a._configured_provider_pair(self.task)
    def test_direct_configured_python_exe_and_pythonw_exe_remain_exact(self):
        for name in ("python.exe", "pythonw.exe"):
            row = {**self.task[0], "execute": str(self.root / name)}
            current = {**self.current, "parent_pid": 50, "executable_path": row["execute"],
                       "command_line": f'"{row["execute"]}" {row["arguments"]}',
                       "ancestry": [{**self.provider, "action_execute": row["execute"]}]}
            self.assertTrue(a.verify_provider_origin(lambda _: current, expected_task=[row])["authorized"])


class PreStarterRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeActivationTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.plan, self.controller, _ = self.f._prepared()
        self.state = self.f.state
        (self.state / "supervisor.json").unlink()
        self.launcher = self.f.runtime / "scripts" / "charlie_runner_task_launcher.py"
        self.launcher.parent.mkdir(parents=True, exist_ok=True)
        self.launcher.write_bytes(b"synthetic-exact-source")
        self.packet = json.loads((self.state / "activation-packet.json").read_text())
        self.controller.bind_exact = Mock()
        self.controller.read_completed_instance_engine_pid = Mock(return_value=101)
        self.controller.assert_no_running_instances = Mock()
        self.records = self._startup()
        a.recover_activation(state_root=self.state, task_controller=self.controller,
            activation_id=self.plan["activation_id"],
            failure_evidence={"status": "task_instance_visibility_timeout", "started": False})
    def _startup(self):
        directory = self.state / "activation-ledger" / "startup-evidence" / self.plan["activation_id"]
        directory.mkdir(parents=True)
        records = []
        started = datetime.fromisoformat(self.packet["prepared_at"])
        for index, phase in enumerate(("launcher_entered", "activation_packet_authenticated",
                "environment_loaded", "watchdog_entry_started", "launcher_failed")):
            record = {"version": "charlie_core_startup_evidence_v1",
                      "activation_id": self.plan["activation_id"],
                      "activation_packet_hmac_sha256": self.packet["packet_hmac_sha256"],
                      "recorded_at": (started + timedelta(milliseconds=index)).isoformat(),
                      "phase": phase, "pid": 102, "launcher_path": str(self.launcher),
                      "launcher_sha256": a._sha256(self.launcher),
                      "python_executable": self.f.task[0]["execute"],
                      "working_directory": self.f.task[0]["working_directory"]}
            if phase == "launcher_failed": record.update(exit_code=1, error_type="ActivationError")
            record["record_hmac_sha256"] = a._sign_record(record, self.f.key, "record_hmac_sha256")
            path = directory / f"{index}.json"; path.write_text(json.dumps(record))
            records.append(path)
        return records
    def reconcile(self, **changes):
        values = dict(state_root=self.state, activation_id=self.plan["activation_id"],
            task_reader=lambda: self.f.task, task_controller=self.controller,
            process_presence_reader=lambda _: "absent")
        values.update(changes)
        return a.reconcile_recovered_activation_stop(**values)
    def test_genuine_shape_reconciles_without_supervisor_or_watchdog_and_replays(self):
        self.assertFalse((self.state / "watchdog.json").exists())
        result = self.reconcile()
        self.assertEqual(result["recovery_basis"], "authenticated_pre_consume_failure")
        self.assertEqual(result["supervisor_status"], "not_started")
        self.assertEqual(result["pre_starter_evidence"]["known_process_pids"], [101, 102])
        self.assertFalse((self.state / "supervisor.json").exists())
        self.assertEqual(self.reconcile(), result)
        self.assertTrue((self.state / "activation-ledger" / (self.plan["activation_id"]+"-failure.json")).exists())
    def test_inline_reconciliation_cannot_pass_before_launcher_final_phase_or_exit(self):
        final = self.records[-1].read_bytes()
        self.records[-1].unlink()
        with self.assertRaisesRegex(a.ActivationError, "pre_starter_startup_evidence_incomplete"):
            self.reconcile()
        self.records[-1].write_bytes(final)
        with self.assertRaisesRegex(a.ActivationError, "process_still_live"):
            self.reconcile(process_presence_reader=lambda pid: "live" if int(pid) == 102 else "absent")
        self.assertTrue((self.state / "activation-reconciliation-pending.json").exists())
    def test_consumed_or_partial_supervisor_or_success_state_is_not_no_starter(self):
        for name in (f"activation-consumed-{self.plan['activation_id']}.json",
                     "runner.json", "activation-verification-complete.json"):
            with self.subTest(name=name):
                path = self.state / name; path.write_text("{}")
                with self.assertRaisesRegex(a.ActivationError, "pre_starter_recovery_not_proven"): self.reconcile()
                path.unlink()
    def test_fake_missing_or_changed_signed_startup_evidence_refused(self):
        before = self.records[0].read_bytes()
        record = json.loads(before); record["pid"] = 900
        self.records[0].write_text(json.dumps(record))
        with self.assertRaisesRegex(a.ActivationError, "pre_starter_startup_evidence_incomplete"): self.reconcile()
        self.records[0].write_bytes(before)
        self.launcher.write_bytes(b"changed")
        with self.assertRaisesRegex(a.ActivationError, "pre_starter_startup_evidence_incomplete"): self.reconcile()
    def test_unknown_absence_or_running_instance_refuses(self):
        with self.assertRaisesRegex(a.ActivationError, "process_proof_unavailable"):
            self.reconcile(process_presence_reader=lambda _: "unknown")
        self.controller.assert_no_running_instances.side_effect = a.ActivationError("instance_running")
        with self.assertRaisesRegex(a.ActivationError, "instance_running"): self.reconcile()
    def test_cli_reconcile_does_not_require_watchdog_file(self):
        path = Path(a.__file__).resolve().parents[2] / "scripts" / "charlie_runtime_activation.py"
        spec = importlib.util.spec_from_file_location("activation_cli_fixture", path)
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        with patch.object(cli, "WindowsExactTaskController", return_value=self.controller), \
             patch.object(cli, "reconcile_recovered_activation_stop", side_effect=lambda **kw: self.reconcile()), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["reconcile-stop", "--state-root", str(self.state),
                "--activation-id", self.plan["activation_id"]]), 0)
        self.assertFalse((self.state / "supervisor.json").exists())
    def test_cli_preserves_existing_watchdog_failure_argument(self):
        path = Path(a.__file__).resolve().parents[2] / "scripts" / "charlie_runtime_activation.py"
        spec = importlib.util.spec_from_file_location("activation_cli_fallback", path)
        cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(cli)
        failure = {"status": "historical_supported_failure", "detail": "preserved"}
        (self.state / "watchdog.json").write_text(json.dumps(failure))
        with patch.object(cli, "WindowsExactTaskController", return_value=self.controller), \
             patch.object(cli, "reconcile_recovered_activation_stop", return_value={"success": True}) as reconcile, \
             redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["reconcile-stop", "--state-root", str(self.state),
                "--activation-id", self.plan["activation_id"]]), 0)
        self.assertEqual(reconcile.call_args.kwargs["failure_evidence"], failure)

    def test_completed_event_reader_requires_exact_production_event_shape(self):
        row = {"record_id": 456, "utc": self.packet["prepared_at"],
               "activity": self.packet["expected_instance_guid"], "instance": self.packet["expected_instance_guid"],
               "task": "\\CHARLIE CORE Runner Watchdog", "engine_pid": 101,
               "action": self.f.task[0]["execute"]}
        scripts = []
        def runner(command, **kwargs):
            scripts.append(command[-1])
            return subprocess.CompletedProcess(command, 0, json.dumps([row]), "")
        controller = a.WindowsExactTaskController(runner=runner)
        self.assertEqual(controller.read_completed_instance_engine_pid(self.packet), 101)
        self.assertIn("'\\CHARLIE CORE Runner Watchdog'", scripts[0])
        for field, value in (("activity", "wrong"), ("engine_pid", 0), ("record_id", 1),
                             ("action", "other.exe"), ("task", "\\other")):
            saved = row[field]; row[field] = value
            with self.subTest(field=field), self.assertRaises(a.ActivationError):
                controller.read_completed_instance_engine_pid(self.packet)
            row[field] = saved
    def test_reconciled_no_starter_stage_plan_authenticates_projection(self):
        projection = self.reconcile()
        from tests import test_charlie_runtime_staging as stage_fixture
        stage = stage_fixture.RuntimeStagingTests()
        stage.setUp(); self.addCleanup(stage.tearDown)
        # Use genuine sealed synthetic validation receipt; no mocked receipt verification.
        stage.runtime, stage.execution, stage.state = self.f.runtime, self.f.execution, self.state
        stage.git = stage_fixture.FakeGit(stage.runtime, stage.execution)
        manifest = {"runtime_root": str(stage.runtime), "promoted_commit": stage_fixture.MANIFEST}
        (self.state / "runtime-manifest.json").write_text(json.dumps(manifest))
        (self.state / "validation-receipt.key").write_bytes(stage.receipt_key)
        from modules.charlie.validation_receipt import record_validation_receipt
        receipt = json.loads(stage.receipt.read_text())
        stage.receipt = Path(record_validation_receipt(receipt, self.state)["path"])
        task = lambda: self.f.task
        with patch.object(a, "WindowsExactTaskController", return_value=self.controller), \
             patch.object(a, "_process_presence", return_value="absent"):
            plan = stage._plan(task_reader=task,
                expected_task_sha256=a._payload_sha256(self.f.task))
            self.assertEqual(plan["status"], "runtime_staging_plan_ready")
            self.assertFalse((self.state / "supervisor.json").exists())
            original_projection_bytes = (self.state / "watchdog.json").read_bytes()
            forged = dict(projection, recovery_basis="unproven")
            (self.state / "watchdog.json").write_text(json.dumps(forged))
            with self.assertRaises(Exception): stage._plan(task_reader=task,
                expected_task_sha256=a._payload_sha256(self.f.task))
            (self.state / "watchdog.json").write_bytes(original_projection_bytes)
            staged = stage_fixture.stage_runtime(plan, task_reader=task,
                runner=stage.git, git_safety_checker=stage._safe_git)
            self.assertTrue(staged["success"])
            self.assertFalse(staged["core_started"])
            self.assertFalse((self.state / "supervisor.json").exists())
            self.assertTrue((self.state / "supervisor.stop").exists())
            self.assertEqual(json.loads((self.state / "watchdog.json").read_text()), projection)
            # A new authority binds the newly staged source/receipt. The old
            # recovery projection is preserved and grants no retry authority.
            authority = dict(self.f.authority, activation_id="2" * 32,
                runtime_revision=stage_fixture.SOURCE,
                execution_revision=stage_fixture.SOURCE,
                manifest_sha256=a._sha256(self.state / "runtime-manifest.json"),
                receipt_path=str(stage.receipt.resolve()),
                receipt_sha256=a._sha256(stage.receipt))
            authority["signature_hmac_sha256"] = a._sign_record(
                authority, self.f.key, "signature_hmac_sha256")
            authority_path = self.state.parent / "successor-authority.json"
            authority_path.write_text(json.dumps(authority), encoding="utf-8")
            successor = a.plan_activation(authority_path=authority_path,
                authority_sha256=a._sha256(authority_path), state_root=self.state,
                runtime_root=self.f.runtime, execution_root=self.f.execution,
                task_reader=task, git_runner=stage.git)
            self.assertEqual(successor["status"], "activation_plan_ready")
            self.assertEqual(successor["runtime_revision"], stage_fixture.SOURCE)
            self.assertTrue(successor["zero_effect"])
            self.assertFalse((self.state / "activation.lock").exists())


class NativeProviderRedirectorTests(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows venv redirector only")
    def test_native_disposable_venv_chain_with_synthetic_scheduler_boundary(self):
        """Real redirector, interpreter, image and ancestry; no installed task."""
        import venv
        with tempfile.TemporaryDirectory(prefix="native-provider-chain-") as directory:
            root = Path(directory)
            venv.EnvBuilder(with_pip=False).create(root / "venv")
            configured = root / "venv" / "Scripts" / "python.exe"
            script = root / "provider_fixture.py"
            source_root = Path(a.__file__).resolve().parents[2]
            script.write_text(
                "import sys,os,json,threading\n"
                "from pathlib import Path\n"
                "from unittest.mock import patch\n"
                "threading.Timer(40, lambda: os._exit(97)).start()\n"
                f"sys.path.insert(0,{str(source_root)!r})\n"
                "from modules.charlie import runtime_activation as a\n"
                "row={'execute':sys.executable,'arguments':'\"'+str(Path(__file__).resolve())+'\"','working_directory':str(Path.cwd())}\n"
                "current=a._local_current_process_identity()\n"
                "action=a._inspect_exact_process(current['parent_pid'])\n"
                "provider={'inspection_complete':True,'pid':action['parent_pid'],'creation_time':'fixture-service',"
                "'service_name':'Schedule','service_state':'Running','start_name':'LocalSystem',"
                "'executable_path':'C:/Windows/System32/svchost.exe',"
                "'service_binary_path':'C:/Windows/System32/svchost.exe -k netsvcs -p',"
                "'service_dll':'C:/Windows/System32/schedsvc.dll','system_root':'C:/Windows',"
                "'engine_pid':action['pid'],'instance_guid':'11111111-1111-1111-1111-111111111111',"
                "'task_path':'\\\\CHARLIE CORE Runner Watchdog','provider_identity_verified':True,"
                "'current_action':row['execute'],'action_execute':row['execute'],"
                "'action_arguments':row['arguments'],'action_working_directory':row['working_directory']}\n"
                "with patch.object(a,'governed_runtime_binding',return_value={'interpreter':sys.executable}):\n"
                " inspected=a.inspect_current_provider_chain(expected_task=[row],provider_identity=lambda:provider)\n"
                " decision=a.verify_provider_origin(lambda _:inspected,expected_task=[row])\n"
                " value={'inspection':inspected,'decision':decision,'logical_executable':sys.executable,'base_executable':sys._base_executable,'executing_pid':os.getpid(),'action_pid':action['pid'],'current_identity':current,'action_identity':action}\n"
                " print(json.dumps(value),flush=True)\n"
                "os._exit(0 if decision['authorized'] else 1)\n",
                encoding="utf-8")
            child = subprocess.Popen([str(configured), str(script)], cwd=str(root),
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW)
            # The fixture exits itself within forty seconds even if a native query hangs.
            output, error = child.communicate(timeout=50)
            self.assertEqual(error, "")
            value = json.loads(output)
            self.assertEqual(a._process_presence(value["executing_pid"]), "absent")
            self.assertEqual(a._process_presence(child.pid), "absent")
            self.assertEqual(child.returncode, 0, value)
            self.assertTrue(value["decision"]["authorized"], value)
            self.assertEqual(value["decision"]["action_pid"], child.pid)
            executing_pid = value["inspection"]["pid"]
            self.assertNotEqual(executing_pid, child.pid)
            self.assertEqual(value["inspection"]["parent_pid"], child.pid)
            self.assertEqual(a._canonical_windows_path(value["inspection"]["executable_path"]),
                             a._canonical_windows_path(value["base_executable"]))
            self.assertEqual(a._canonical_windows_path(value["logical_executable"]),
                             a._canonical_windows_path(configured))
            self.assertEqual(a._process_presence(executing_pid), "absent")
            self.assertEqual(a._process_presence(child.pid), "absent")


if __name__ == "__main__":
    unittest.main()
