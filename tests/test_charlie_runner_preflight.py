import tempfile
import unittest
from pathlib import Path

from modules.charlie.runner_preflight import python_test_command, resolve_python_executable


class CharlieRunnerPreflightTests(unittest.TestCase):
    def test_resolves_parent_root_venv_for_clean_worktree(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            parent_venv_python = root / "venv" / "Scripts" / "python.exe"
            parent_venv_python.parent.mkdir(parents=True)
            parent_venv_python.write_text("", encoding="utf-8")
            worktree = root / ".worktrees" / "clean-runner"
            worktree.mkdir(parents=True)

            self.assertEqual(resolve_python_executable(worktree), str(parent_venv_python))

    def test_python_test_command_uses_resolved_python(self):
        command = python_test_command("-m unittest tests.test_charlie_mission_quality")

        self.assertIn("-m unittest tests.test_charlie_mission_quality", command)
        self.assertTrue(command.lower().endswith("tests.test_charlie_mission_quality"))


if __name__ == "__main__":
    unittest.main()
