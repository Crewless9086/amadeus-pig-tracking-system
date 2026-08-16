import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from modules.charlie.runtime_staging import (
    RECEIPT_VERSION,
    RuntimeStagingError,
    plan_runtime_staging,
    stage_runtime,
)


SOURCE = "e31f80e5de21a998293dd44b6a8a6f281f9a9c53"
RUNTIME = "3768cc08" + "0" * 32
EXECUTION = "7cb7ddae" + "0" * 32
MANIFEST = "d84ab1a4" + "0" * 32


class FakeGit:
    def __init__(self, runtime, execution):
        self.heads = {str(runtime): RUNTIME, str(execution): EXECUTION}
        self.dirty = set()
        self.fail_execution_switch = False
        self.execution = str(execution)

    def __call__(self, command, cwd=None, **_kwargs):
        root = str(Path(cwd).resolve())
        args = command[1:]
        stdout, returncode = "", 0
        if args[:2] == ["status", "--porcelain"]:
            stdout = "dirty\n" if root in self.dirty else ""
        elif args[:2] == ["rev-parse", "HEAD"]:
            stdout = self.heads[root] + "\n"
        elif args[:2] == ["branch", "--show-current"]:
            stdout = "main\n"
        elif args[:2] == ["rev-parse", "--verify"]:
            stdout = args[2].removesuffix("^{commit}") + "\n"
        elif args[:2] == ["switch", "--detach"]:
            if root == self.execution and self.fail_execution_switch and args[2] == SOURCE:
                returncode = 1
            else:
                self.heads[root] = args[2]
        else:
            returncode = 1
        return subprocess.CompletedProcess(command, returncode, stdout, "")


class RuntimeStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.runtime = root / "runtime"
        self.execution = root / "execution"
        self.state = root / "state"
        self.runtime.mkdir()
        self.execution.mkdir()
        self.state.mkdir()
        self.git = FakeGit(self.runtime, self.execution)
        self._write("runtime-manifest.json", {"version": "charlie_core_runtime_v1", "promoted_commit": MANIFEST})
        (self.state / "supervisor.stop").write_text("governed\n", encoding="utf-8")
        self._write("supervisor.json", {"status": "supervisor_stopped"})
        self._write("watchdog.json", {"status": "governed_stop_active"})
        self.receipt = root / "receipt.json"
        self.receipt.write_text(json.dumps({
            "version": RECEIPT_VERSION, "source_commit": SOURCE, "status": "passed",
            "focused_passed": 9, "full_suite_passed": 57,
            "isolation": {"boundary": "disposable_process_boundary",
                          "host_processes_visible": False, "outside_boundary_targets": 0},
        }), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def _write(self, name, payload):
        (self.state / name).write_text(json.dumps(payload), encoding="utf-8")

    def _task(self):
        return [{"task_name": "CHARLIE CORE Runner Watchdog", "state": "Ready",
                 "action_count": 1, "execute": "pythonw.exe",
                 "arguments": f'-c "runpy.run_path(r\'{self.runtime}\\scripts\\charlie_runner_watchdog.py\')"',
                 "working_directory": str(self.runtime)}]

    def _plan(self, **changes):
        values = dict(
            source_ref=SOURCE, runtime_root=self.runtime, execution_root=self.execution,
            state_root=self.state, receipt_path=self.receipt,
            receipt_sha256=hashlib.sha256(self.receipt.read_bytes()).hexdigest(),
            expected_runtime_head=RUNTIME, expected_execution_head=EXECUTION,
            expected_manifest_commit=MANIFEST, task_reader=self._task, runner=self.git,
        )
        values.update(changes)
        return plan_runtime_staging(**values)

    def test_plan_is_zero_effect_and_records_exact_rollback(self):
        before = (dict(self.git.heads), (self.state / "runtime-manifest.json").read_bytes())
        plan = self._plan()
        self.assertTrue(plan["zero_effect"])
        self.assertEqual(plan["watchdog_action"], "none")
        self.assertEqual(before, (self.git.heads, (self.state / "runtime-manifest.json").read_bytes()))
        self.assertEqual(plan["rollback"]["runtime"]["head"], RUNTIME)

    def test_plan_rejects_bad_receipt_digest(self):
        with self.assertRaisesRegex(RuntimeStagingError, "sealed_receipt_digest_mismatch"):
            self._plan(receipt_sha256="0" * 64)

    def test_plan_rejects_dirty_or_contradictory_worktree(self):
        self.git.dirty.add(str(self.runtime.resolve()))
        with self.assertRaisesRegex(RuntimeStagingError, "runtime_worktree_dirty"):
            self._plan()
        self.git.dirty.clear()
        with self.assertRaisesRegex(RuntimeStagingError, "current_state_contradicts_expected_rollback"):
            self._plan(expected_runtime_head="1" * 40)

    def test_plan_rejects_ambiguous_or_running_task(self):
        with self.assertRaisesRegex(RuntimeStagingError, "scheduled_task_ownership_ambiguous"):
            self._plan(task_reader=lambda: [])
        task = self._task()
        task[0]["state"] = "Running"
        with self.assertRaisesRegex(RuntimeStagingError, "scheduled_task_ownership_ambiguous"):
            self._plan(task_reader=lambda: task)

    def test_stage_sets_exact_heads_after_rollback_record_and_preserves_stop(self):
        stop = (self.state / "supervisor.stop").read_bytes()
        result = stage_runtime(self._plan(), task_reader=self._task, runner=self.git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], SOURCE)
        self.assertEqual(self.git.heads[str(self.execution.resolve())], SOURCE)
        self.assertEqual(json.loads((self.state / "runtime-manifest.json").read_text())["promoted_commit"], SOURCE)
        self.assertEqual((self.state / "supervisor.stop").read_bytes(), stop)
        self.assertEqual(result["watchdog_action"], "none")
        self.assertFalse(result["core_started"])
        self.assertTrue(Path(result["rollback_path"]).is_file())

    def test_existing_lane_fails_closed_without_effect(self):
        plan = self._plan()
        (self.state / "release-staging.lock").write_text("owned", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeStagingError, "release_lane_already_owned"):
            stage_runtime(plan, task_reader=self._task, runner=self.git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], RUNTIME)

    def test_worktree_drift_after_plan_fails_before_mutation(self):
        plan = self._plan()
        self.git.heads[str(self.runtime.resolve())] = "2" * 40
        with self.assertRaisesRegex(RuntimeStagingError, "worktree_identity_changed_before_staging"):
            stage_runtime(plan, task_reader=self._task, runner=self.git)
        self.assertEqual(self.git.heads[str(self.execution.resolve())], EXECUTION)

    def test_execution_failure_recovers_both_heads_and_manifest(self):
        original_manifest = (self.state / "runtime-manifest.json").read_bytes()
        plan = self._plan()
        self.git.fail_execution_switch = True
        with self.assertRaisesRegex(RuntimeStagingError, "git_staging_failed"):
            stage_runtime(plan, task_reader=self._task, runner=self.git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], RUNTIME)
        self.assertEqual(self.git.heads[str(self.execution.resolve())], EXECUTION)
        self.assertEqual((self.state / "runtime-manifest.json").read_bytes(), original_manifest)

    def test_receipt_changed_after_plan_fails_before_mutation(self):
        plan = self._plan()
        self.receipt.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeStagingError, "sealed_receipt_changed"):
            stage_runtime(plan, task_reader=self._task, runner=self.git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], RUNTIME)


if __name__ == "__main__":
    unittest.main()
