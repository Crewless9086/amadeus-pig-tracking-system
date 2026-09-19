import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("workspace_check", Path(__file__).parents[1] / "scripts/check_workspace.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class WorkspaceCheckTests(unittest.TestCase):
    def setUp(self):
        checkout = Path(__file__).resolve().parents[1]
        common = Path(subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "--path-format=absolute", "--git-common-dir"], text=True).strip())
        fixture_root = common.parent.parent / ".runtime" / "workspace-tests"
        fixture_root.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=fixture_root)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "repo"
        self.root.mkdir()
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Workspace test")
        self.git("config", "user.email", "workspace-test@example.invalid")
        for relative in ["AGENTS.md", "README.md", "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md", "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md"]:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("fixture", encoding="utf-8")
        self.git("add", "--", "AGENTS.md", "README.md", "docs")
        self.git("commit", "-qm", "fixture")
        self.git("update-ref", "refs/remotes/origin/main", "HEAD")

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True, text=True)

    def test_clean_independent_checkout_passes(self):
        self.assertTrue(MODULE.inspect_workspace(self.root, require_clean=True)["passed"])

    def test_ignored_nested_runtime_does_not_pass_as_clean(self):
        (self.root / ".git/info/exclude").write_text(".codex-runtime/\n", encoding="utf-8")
        (self.root / ".codex-runtime").mkdir()
        report = MODULE.inspect_workspace(self.root, require_clean=True)
        self.assertTrue(report["clean"])
        self.assertFalse(report["passed"])

    def test_cache_and_case_variants_are_reported(self):
        (self.root / ".git/info/exclude").write_text(".testtmp/\ntest-results/\n.pytest_cache/\n.CODEX-RUNTIME/\n", encoding="utf-8")
        for name in [".testtmp", "test-results", ".pytest_cache", ".CODEX-RUNTIME"]:
            with self.subTest(name=name):
                candidate = self.root / name
                candidate.mkdir()
                report = MODULE.inspect_workspace(self.root, require_clean=True)
                self.assertTrue(report["clean"])
                self.assertFalse(report["passed"])
                candidate.rmdir()

    def test_hidden_working_evidence_is_reported(self):
        (self.root / ".git/info/exclude").write_text("control-tower-artifacts/\n", encoding="utf-8")
        evidence = self.root / "control-tower-artifacts"
        evidence.mkdir()
        (evidence / "working.txt").write_text("working", encoding="utf-8")
        report = MODULE.inspect_workspace(self.root, require_clean=True)
        self.assertTrue(report["clean"])
        self.assertFalse(report["passed"])

    def test_uncommitted_change_blocks_only_strict_check(self):
        (self.root / "README.md").write_text("changed", encoding="utf-8")
        self.assertTrue(MODULE.inspect_workspace(self.root)["passed"])
        self.assertFalse(MODULE.inspect_workspace(self.root, require_clean=True)["passed"])

    def test_external_object_dependency_is_reported_without_git_operation(self):
        # An empty independent external store is readable but still a portability dependency.
        outside = Path(self.tmp.name) / "objects"
        outside.mkdir()
        alternate = self.root / ".git/objects/info/alternates"
        alternate.write_text(str(outside) + "\n", encoding="utf-8")
        report = MODULE.inspect_workspace(self.root)
        self.assertTrue(any("alternate" in row for row in report["findings"]))

if __name__ == "__main__":
    unittest.main()
