import subprocess
import sys
import unittest
from unittest.mock import patch

from modules.charlie.process_ownership import process_tree_identity_digest
from scripts import charlie_observe_only_runner as observe_runner


class CharlieObserveOnlyRunnerTests(unittest.TestCase):
    def test_final_supervisor_validation_allows_the_exact_runner_tree(self):
        supervisor_tree = {"version": "charlie_process_tree_v1", "root_pid": 10, "root": {}, "members": []}
        runner_tree = {"version": "charlie_process_tree_v1", "root_pid": 20, "root": {}, "members": []}
        identity = {
            "generation": "generation",
            "supervisor_nonce": "supervisor-nonce",
            "runner_nonce": "runner-nonce",
            "runtime_revision": "revision",
            "execution_revision": "revision",
            "public_key": "public-key",
        }
        acknowledgement = {
            "generation": "generation",
            "supervisor_startup_nonce": "supervisor-nonce",
            "runner_startup_nonce": "runner-nonce",
            "revision": "revision",
            "runner_pid": "20",
            "execution_mode": "observe_only",
            "supervisor_member_pids": [10],
            "runner_member_pids": [20],
            "supervisor_tree_digest": process_tree_identity_digest(supervisor_tree),
            "runner_tree_digest": process_tree_identity_digest(runner_tree),
            "signature": "signature",
        }
        packet = {
            "controller_public_key": "public-key",
            "controller_final_acknowledgement": acknowledgement,
            "supervisor_tree_identity": supervisor_tree,
            "process_tree_identity": runner_tree,
        }
        with patch.object(observe_runner, "_identity", return_value=identity), patch.object(
            observe_runner.os, "getpid", return_value=20
        ), patch.object(
            observe_runner, "verify_controller_acknowledgement", return_value=True
        ), patch.object(
            observe_runner,
            "validate_live_bootstrap_tree",
            side_effect=[
                {"authorized": True, "member_pids": [10]},
                {"authorized": True, "member_pids": [20]},
            ],
        ) as validate:
            result = observe_runner._validate_final(packet)

        self.assertTrue(result["success"])
        self.assertIs(
            validate.call_args_list[0].kwargs["allowed_descendant_tree"],
            runner_tree,
        )

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
