import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.charlie.concurrency_control import (
    ReleaseCoordinator,
    acquire_file_lease,
    build_admission,
    declared_source_files,
    paths_overlap,
    release_file_lease,
    revision_truth,
    workspace_role,
    activation_readiness,
)


class SequenceRunner:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def __call__(self, *_args, **_kwargs):
        return SimpleNamespace(returncode=0, stdout=next(self.outputs), stderr="")


class CoreConcurrencyControlTests(unittest.TestCase):
    def test_activation_readiness_requires_containment_quiet_scheduler_and_revision_convergence(self):
        with patch("modules.charlie.concurrency_control.workspace_inventory", return_value={"success": True}), patch(
            "modules.charlie.concurrency_control.revision_truth", return_value={"all_observed_match": True}
        ):
            self.assertTrue(activation_readiness(".")["ready"])
            blocked = activation_readiness(".", containment_active=False, scheduler_enabled=True, active_process_count=1)
        self.assertEqual(set(blocked["blockers"]), {"containment_not_active_during_preflight", "scheduler_enabled_during_preflight", "charlie_processes_active_during_preflight"})
    def test_workspace_roles_keep_owner_and_core_execution_distinct(self):
        root = Path("C:/repo")
        self.assertEqual(workspace_role(root, root, "main"), "owner_checkout")
        self.assertEqual(workspace_role(root / ".charlie_runner/core-execution-current", root, "charlie-core-execution-base"), "core_execution")
        self.assertEqual(workspace_role(Path("C:/tmp/phase2"), root, "program/phase2"), "interactive_feature")

    def test_declared_source_files_collects_nested_agent_scope(self):
        files = declared_source_files(
            {"metadata": {"review_packet": {"changed_files": ["modules/a.py"]}}},
            {"architect": {"files_to_inspect": ["modules/b.py", "https://example.com"]}},
        )
        self.assertEqual(files, ["modules/a.py", "modules/b.py"])

    def test_declared_source_files_excludes_runner_owned_codex_chat(self):
        files = declared_source_files({
            "metadata": {"review_packet": {"changed_files": [
                "planning/CODEX_CHAT.md",
                "modules/beacon/autonomy_readiness.py",
            ]}},
        })
        self.assertEqual(files, ["modules/beacon/autonomy_readiness.py"])

    def test_overlap_detects_exact_and_directory_scope(self):
        self.assertTrue(paths_overlap("modules/a.py", "modules/a.py"))
        self.assertTrue(paths_overlap("modules/charlie", "modules/charlie/routes.py"))
        self.assertFalse(paths_overlap("modules/a.py", "tests/a.py"))

    def test_file_lease_blocks_other_mission_and_releases(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = acquire_file_lease(tmp, "MISSION-1", ["modules/a.py"], now_epoch=100)
            blocked = acquire_file_lease(tmp, "MISSION-2", ["modules/a.py"], now_epoch=101)
            released = release_file_lease(tmp, first["lease_id"])
            second = acquire_file_lease(tmp, "MISSION-2", ["modules/a.py"], now_epoch=102)
            self.assertTrue(first["acquired"])
            self.assertEqual(blocked["status"], "file_scope_leased")
            self.assertTrue(released["released"])
            self.assertTrue(second["acquired"])

    def test_stale_file_lease_expires(self):
        with tempfile.TemporaryDirectory() as tmp:
            acquire_file_lease(tmp, "MISSION-1", ["modules/a.py"], now_epoch=100)
            second = acquire_file_lease(tmp, "MISSION-2", ["modules/a.py"], now_epoch=2000)
            self.assertTrue(second["acquired"])

    def test_owner_main_is_never_admitted_as_builder_workspace(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runner = SequenceRunner([
                f"worktree {root}\nHEAD abc\nbranch refs/heads/main\n\n",
                "",
            ])
            result = build_admission(root, "MISSION-1", ["modules/a.py"], run_factory=runner)
            self.assertFalse(result["allowed"])
            self.assertEqual(result["status"], "owner_main_execution_forbidden")

    def test_other_workspace_overlap_blocks_before_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / "repo"
            execution = canonical / ".charlie_runner" / "core-execution-current"
            interactive = Path(tmp) / "interactive"
            (canonical / ".git" / "worktrees" / "core").mkdir(parents=True)
            execution.mkdir(parents=True)
            interactive.mkdir()
            (execution / ".git").write_text(f"gitdir: {canonical / '.git/worktrees/core'}\n", encoding="utf-8")
            runner = SequenceRunner([
                f"worktree {canonical}\nHEAD aaa\nbranch refs/heads/main\n\nworktree {execution}\nHEAD bbb\nbranch refs/heads/charlie-core-execution-base\n\nworktree {interactive}\nHEAD ccc\nbranch refs/heads/program/other\n\n",
                "",
                "",
                " M modules/a.py\n",
            ])
            result = build_admission(execution, "MISSION-1", ["modules/a.py"], run_factory=runner)
            self.assertFalse(result["allowed"])
            self.assertEqual(result["status"], "concurrent_source_overlap")
            self.assertEqual(result["conflicts"][0]["files"], ["modules/a.py"])

    def test_release_coordinator_allows_only_one_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = ReleaseCoordinator(tmp, "MISSION-1", "297")
            second = ReleaseCoordinator(tmp, "MISSION-2", "298")
            with patch("modules.charlie.repository_guard._pid_alive", return_value=True):
                self.assertTrue(first.acquire()[0])
                self.assertFalse(second.acquire()[0])
                first.record("merged", source_commit="abc", merged_commit="def")
                first.release()
                self.assertTrue(second.acquire()[0])
                second.release()
            rows = (Path(tmp) / ".charlie_runner/release-ledger.jsonl").read_text(encoding="utf-8").splitlines()
            self.assertTrue(any(json.loads(row)["status"] == "merged" for row in rows))

    def test_revision_truth_reports_exact_convergence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".charlie_runner").mkdir()
            (root / ".charlie_runner/runtime-manifest.json").write_text(json.dumps({"promoted_commit": "same"}), encoding="utf-8")
            (root / ".charlie_runner/runner.json").write_text(json.dumps({"runner_source_commit": "same"}), encoding="utf-8")
            with patch("modules.charlie.concurrency_control._git_output", side_effect=["same", "owner", "feature", "program/phases-2-7"]):
                result = revision_truth(root, render_deployed_commit="same")
            self.assertTrue(result["all_observed_match"])
            self.assertEqual(result["owner_checkout_commit"], "owner")
            self.assertEqual(result["github_accepted_commit"], "same")
            self.assertEqual(result["current_workspace_commit"], "feature")
            self.assertEqual(result["current_workspace_branch"], "program/phases-2-7")


if __name__ == "__main__":
    unittest.main()
