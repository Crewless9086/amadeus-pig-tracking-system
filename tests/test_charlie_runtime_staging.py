import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from modules.charlie.runtime_staging import (
    RECEIPT_VERSION,
    RuntimeStagingError,
    inspect_git_checkout_safety,
    plan_runtime_staging,
    read_staging_state,
    recover_runtime_staging,
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
        self.fail_runtime_restore = False
        self.partial_runtime_failure = False
        self.execution = str(execution)

    def __call__(self, command, cwd=None, **_kwargs):
        root = str(Path(cwd).resolve())
        args = command[1:]
        while args[:1] == ["-c"]:
            args = args[2:]
        stdout, returncode = "", 0
        if args[:2] == ["status", "--porcelain"]:
            stdout = "dirty\n" if root in self.dirty else ""
        elif args[:2] == ["rev-parse", "HEAD"]:
            stdout = self.heads[root] + "\n"
        elif args[:2] == ["branch", "--show-current"]:
            stdout = "main\n"
        elif args[:2] == ["rev-parse", "--verify"]:
            stdout = args[2].removesuffix("^{commit}") + "\n"
        elif args[0] == "rev-parse" and args[1].startswith("refs/heads/"):
            stdout = (RUNTIME if root != self.execution else EXECUTION) + "\n"
        elif args[:2] == ["switch", "--detach"]:
            if root != self.execution and self.partial_runtime_failure and args[2] == SOURCE:
                self.heads[root] = SOURCE
                returncode = 1
            elif root == self.execution and self.fail_execution_switch and args[2] == SOURCE:
                returncode = 1
            else:
                self.heads[root] = args[2]
        elif args[:1] == ["switch"]:
            if root != self.execution and self.fail_runtime_restore:
                returncode = 1
            else:
                self.heads[root] = RUNTIME if root != self.execution else EXECUTION
        else:
            returncode = 1
        return subprocess.CompletedProcess(command, returncode, stdout, "")


class RuntimeStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.state = root / "state"
        self.runtime = self.state / "core-runtime-current"
        self.execution = self.state / "core-execution-current"
        self.runtime.mkdir(parents=True)
        self.execution.mkdir()
        self.state.mkdir(exist_ok=True)
        self.git = FakeGit(self.runtime, self.execution)
        self._write("runtime-manifest.json", {"version": "charlie_core_runtime_v1", "promoted_commit": MANIFEST,
                                               "runtime_root": str(self.runtime.resolve())})
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
        canonical = self.state.parent
        return [{"task_name": "CHARLIE CORE Runner Watchdog", "state": "Ready",
                 "action_count": 1, "execute": str(canonical / "venv" / "Scripts" / "pythonw.exe"),
                 "arguments": ('-c "from dotenv import load_dotenv; '
                    f"load_dotenv(r'{canonical / '.env'}', override=True); import runpy,sys; "
                    f"sys.argv=[r'{self.runtime / 'scripts' / 'charlie_runner_watchdog.py'}','--json']; "
                    f"runpy.run_path(r'{self.runtime / 'scripts' / 'charlie_runner_watchdog.py'}', run_name='__main__')\""),
                 "working_directory": str(self.runtime)}]

    @staticmethod
    def _safe_git(_root, _runner):
        return {"extensions": "none", "post_checkout_hook": "absent"}

    def _plan(self, **changes):
        values = dict(
            source_ref=SOURCE, runtime_root=self.runtime, execution_root=self.execution,
            state_root=self.state, receipt_path=self.receipt,
            receipt_sha256=hashlib.sha256(self.receipt.read_bytes()).hexdigest(),
            expected_runtime_head=RUNTIME, expected_execution_head=EXECUTION,
            expected_manifest_commit=MANIFEST, task_reader=self._task, runner=self.git,
            expected_task_sha256=hashlib.sha256(json.dumps(
                self._task(), sort_keys=True, separators=(",", ":")
            ).encode()).hexdigest(), git_safety_checker=self._safe_git,
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

    def test_plan_rejects_task_action_substitution_and_wrong_digest(self):
        task = self._task()
        task[0]["arguments"] += "; malicious.exe"
        with self.assertRaisesRegex(RuntimeStagingError, "scheduled_task_ownership_ambiguous"):
            self._plan(task_reader=lambda: task)
        with self.assertRaisesRegex(RuntimeStagingError, "scheduled_task_digest_mismatch"):
            self._plan(expected_task_sha256="0" * 64)
        task = self._task()
        task[0]["execute"] = str(self.state.parent / "other" / "pythonw.exe")
        with self.assertRaisesRegex(RuntimeStagingError, "scheduled_task_ownership_ambiguous"):
            self._plan(task_reader=lambda: task)

    def test_executable_git_checkout_extension_fails_closed(self):
        def configured(command, **_kwargs):
            return subprocess.CompletedProcess(command, 0, "file:C:/config filter.bad.process evil.exe\n", "")
        with self.assertRaisesRegex(RuntimeStagingError, "git_executable_checkout_extension_present"):
            inspect_git_checkout_safety(self.runtime, configured)

    def test_plan_rejects_substituted_or_overlapping_roots(self):
        with self.assertRaisesRegex(RuntimeStagingError, "non_authoritative_staging_roots"):
            self._plan(execution_root=self.state / "substituted")
        with self.assertRaisesRegex(RuntimeStagingError, "runtime_execution_roots_overlap"):
            self._plan(execution_root=self.runtime)

    def test_stage_sets_exact_heads_after_rollback_record_and_preserves_stop(self):
        stop = (self.state / "supervisor.stop").read_bytes()
        result = stage_runtime(self._plan(), task_reader=self._task, runner=self.git,
                               git_safety_checker=self._safe_git)
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
            stage_runtime(plan, task_reader=self._task, runner=self.git,
                          git_safety_checker=self._safe_git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], RUNTIME)

    def test_worktree_drift_after_plan_fails_before_mutation(self):
        plan = self._plan()
        self.git.heads[str(self.runtime.resolve())] = "2" * 40
        with self.assertRaisesRegex(RuntimeStagingError, "worktree_identity_changed_before_staging"):
            stage_runtime(plan, task_reader=self._task, runner=self.git,
                          git_safety_checker=self._safe_git)
        self.assertEqual(self.git.heads[str(self.execution.resolve())], EXECUTION)

    def test_manifest_drift_after_plan_fails_before_mutation(self):
        plan = self._plan()
        self._write("runtime-manifest.json", {"version": "changed", "promoted_commit": MANIFEST,
                                               "runtime_root": str(self.runtime.resolve())})
        with self.assertRaisesRegex(RuntimeStagingError, "runtime_manifest_changed_before_staging"):
            stage_runtime(plan, task_reader=self._task, runner=self.git,
                          git_safety_checker=self._safe_git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], RUNTIME)

    def test_modified_plan_digest_fails_before_lane_acquisition(self):
        plan = self._plan()
        plan["source_ref"] = "3" * 40
        with self.assertRaisesRegex(RuntimeStagingError, "staging_plan_digest_mismatch"):
            stage_runtime(plan, task_reader=self._task, runner=self.git,
                          git_safety_checker=self._safe_git)
        self.assertFalse((self.state / "release-staging.lock").exists())

    def test_execution_failure_recovers_both_heads_and_manifest(self):
        original_manifest = (self.state / "runtime-manifest.json").read_bytes()
        plan = self._plan()
        self.git.fail_execution_switch = True
        with self.assertRaisesRegex(RuntimeStagingError, "git_staging_failed"):
            stage_runtime(plan, task_reader=self._task, runner=self.git,
                          git_safety_checker=self._safe_git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], RUNTIME)
        self.assertEqual(self.git.heads[str(self.execution.resolve())], EXECUTION)
        self.assertEqual((self.state / "runtime-manifest.json").read_bytes(), original_manifest)

    def test_partial_runtime_switch_failure_is_recovered(self):
        plan = self._plan()
        self.git.partial_runtime_failure = True
        with self.assertRaisesRegex(RuntimeStagingError, "git_staging_failed"):
            stage_runtime(plan, task_reader=self._task, runner=self.git,
                          git_safety_checker=self._safe_git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], RUNTIME)

    def test_failed_recovery_retains_lane_then_explicit_recovery_clears_it(self):
        plan = self._plan()
        self.git.fail_execution_switch = True
        self.git.fail_runtime_restore = True
        with self.assertRaisesRegex(RuntimeStagingError, "git_staging_failed"):
            stage_runtime(plan, task_reader=self._task, runner=self.git,
                          git_safety_checker=self._safe_git)
        state = read_staging_state(self.state)
        self.assertEqual(state["status"], "release_lane_recovery_required")
        self.git.fail_execution_switch = False
        self.git.fail_runtime_restore = False
        recovered = recover_runtime_staging(
            state_root=self.state, lane_id=state["lane"]["lane_id"],
            rollback_sha256=state["rollback_sha256"], task_reader=self._task,
            runner=self.git, git_safety_checker=self._safe_git,
        )
        self.assertEqual(recovered["status"], "runtime_staging_recovered")
        self.assertEqual(read_staging_state(self.state)["status"], "no_active_release_lane")

    def test_receipt_changed_after_plan_fails_before_mutation(self):
        plan = self._plan()
        self.receipt.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeStagingError, "sealed_receipt_changed"):
            stage_runtime(plan, task_reader=self._task, runner=self.git,
                          git_safety_checker=self._safe_git)
        self.assertEqual(self.git.heads[str(self.runtime.resolve())], RUNTIME)


if __name__ == "__main__":
    unittest.main()
