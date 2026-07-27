import subprocess
import sys
import unittest


class CharlieObserveOnlyRunnerTests(unittest.TestCase):
    def test_import_does_not_load_mission_store_execution_or_provider_modules(self):
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                "-c",
                (
                    "import sys; import scripts.charlie_observe_only_runner; "
                    "blocked=('modules.charlie.mission_store',"
                    "'modules.charlie.execution_bridge',"
                    "'modules.charlie.private_runtime'); "
                    "print([name for name in blocked if name in sys.modules])"
                ),
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "[]")


if __name__ == "__main__":
    unittest.main()
