import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from modules.charlie.process_policy import background_process_kwargs, background_run_kwargs
from modules.charlie.runtime_integrity import (
    MANIFEST_VERSION,
    cold_start_readiness,
    communication_plane_health,
    runtime_integrity,
    write_runtime_manifest,
)


class CharlieRuntimeIntegrityTests(unittest.TestCase):
    @staticmethod
    def runner_for(revision="abc123", branch="runtime-base", gh_ok=True):
        def run(command, **_kwargs):
            if command[:3] == ["git", "rev-parse", "HEAD"]:
                return SimpleNamespace(returncode=0, stdout=revision + "\n", stderr="")
            if command[:3] == ["git", "branch", "--show-current"]:
                return SimpleNamespace(returncode=0, stdout=branch + "\n", stderr="")
            if command[:3] == ["gh", "repo", "view"]:
                return SimpleNamespace(returncode=0 if gh_ok else 1, stdout="", stderr="" if gh_ok else "invalid token")
            if command[:3] == ["git", "credential", "fill"]:
                return SimpleNamespace(returncode=0, stdout="protocol=https\nhost=github.com\npassword=test-token\n", stderr="")
            return SimpleNamespace(returncode=1, stdout="", stderr="unexpected")
        return run

    def test_promotion_manifest_and_exact_revision_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            state = Path(tmp) / "state"
            root.mkdir()
            promoted = write_runtime_manifest(root, state, runner=self.runner_for())
            checked = runtime_integrity(root, state, runner=self.runner_for())
        self.assertTrue(promoted["success"])
        self.assertTrue(checked["ready"])
        self.assertEqual(checked["manifest_version"], MANIFEST_VERSION)

    def test_revision_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            state = Path(tmp) / "state"
            root.mkdir()
            write_runtime_manifest(root, state, runner=self.runner_for("old"))
            checked = runtime_integrity(root, state, runner=self.runner_for("new"))
        self.assertFalse(checked["ready"])
        self.assertEqual(checked["status"], "runtime_drift_detected")

    def test_invalid_github_auth_blocks_cold_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "runtime"
            state = Path(tmp) / "state"
            root.mkdir()
            write_runtime_manifest(root, state, runner=self.runner_for())
            checked = cold_start_readiness(
                root, state, runner=self.runner_for(gh_ok=False),
                environ={"CHARLIE_TELEGRAM_TRANSPORT": "webhook"},
            )
        self.assertFalse(checked["ready"])
        self.assertIn("github_repo_access_invalid", checked["blockers"])

    def test_git_credential_bootstrap_never_exposes_token_in_health(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            environment = {"CHARLIE_TELEGRAM_TRANSPORT": "webhook"}
            from modules.charlie.runtime_integrity import github_auth_health
            health = github_auth_health(root, runner=self.runner_for(), environ=environment)
        self.assertTrue(health["ready"])
        self.assertEqual(environment["GH_TOKEN"], "test-token")
        self.assertNotIn("test-token", json.dumps(health))

    def test_transport_is_single_explicit_plane(self):
        self.assertEqual(communication_plane_health({"CHARLIE_TELEGRAM_TRANSPORT": "webhook"})["local_polling_allowed"], False)
        self.assertEqual(communication_plane_health({"CHARLIE_TELEGRAM_TRANSPORT": "polling"})["local_polling_allowed"], True)
        self.assertFalse(communication_plane_health({"CHARLIE_TELEGRAM_TRANSPORT": "both"})["ready"])

    def test_background_children_are_windowless_on_windows(self):
        self.assertEqual(background_process_kwargs("nt"), {"creationflags": 0x08000000})
        self.assertEqual(background_run_kwargs("nt"), {"creationflags": 0x08000000})

    def test_promotion_script_is_manifest_gated_and_refuses_dirty_runtime(self):
        source = (Path(__file__).parents[1] / "scripts" / "promote_charlie_runtime.ps1").read_text(encoding="utf-8")
        self.assertIn("status --porcelain", source)
        self.assertIn("--git-common-dir", source)
        self.assertIn("$sourceRoot", source)
        self.assertIn("charlie_runtime_audit.py", source)
        self.assertIn("pythonw.exe", source)
        self.assertNotIn("git reset --hard", source)


if __name__ == "__main__":
    unittest.main()
