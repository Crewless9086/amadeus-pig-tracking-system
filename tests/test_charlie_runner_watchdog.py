import json
import tempfile
import unittest
from pathlib import Path

from scripts.charlie_runner_watchdog import _configure_git_safe_directory, watchdog_tick


class CharlieRunnerWatchdogTests(unittest.TestCase):
    def test_failed_activation_returns_signed_reconciliation_without_rewriting_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "activation-packet.json").write_text(
                json.dumps({"activation_id": "1" * 32}), encoding="utf-8"
            )
            (root / "activation.lock").write_text("owned", encoding="utf-8")
            projection = {
                "version": "charlie_activation_recovery_projection_v1",
                "status": "governed_stop_active",
                "checked_at": "signed-value",
                "projection_hmac_sha256": "signed-digest",
            }
            def recover(**_kwargs):
                (root / "activation-reconciliation-pending.json").write_text(
                    json.dumps({"activation_id": "1" * 32}), encoding="utf-8"
                )
                return {"success": True}
            result = watchdog_tick(
                starter=lambda **_kwargs: None,
                state_path=root / "watchdog.json",
                stop_path=root / "supervisor.stop",
                activation_consumer=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("failed")),
                activation_recoverer=recover,
                activation_reconciler=lambda **_kwargs: projection,
            )
        self.assertEqual(result, projection)
    def test_provider_packet_is_consumed_before_any_ordinary_recovery_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "activation-packet.json").write_text("{}", encoding="utf-8")
            calls = []
            def consume(**kwargs):
                calls.append(("provider", kwargs["state_root"], kwargs["starter"]))
                return {"success": True, "status": "provider_started_observe_only", "started": True}
            starter = lambda **_kwargs: calls.append("direct_start")
            result = watchdog_tick(
                status_reader=lambda: calls.append("status"), starter=starter,
                state_path=root / "watchdog.json", stop_path=root / "supervisor.stop",
                activation_consumer=consume,
            )
        self.assertEqual(result["status"], "provider_started_observe_only")
        self.assertEqual(calls, [("provider", root, starter)])

    def test_observe_only_state_disables_watchdog_without_queue_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            result = watchdog_tick(
                status_reader=lambda: calls.append("status"),
                starter=lambda: calls.append("start"),
                supervisor_state_reader=lambda: {"execution_mode": "observe_only"},
                state_path=Path(tmp) / "watchdog.json",
                stop_path=Path(tmp) / "supervisor.stop",
            )
        self.assertEqual(result["status"], "observe_only_watchdog_recovery_disabled")
        self.assertEqual(calls, [])
    def test_governed_stop_marker_prevents_watchdog_tick_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop = Path(tmp) / "supervisor.stop"
            stop.write_text("owner governed stop", encoding="utf-8")
            calls = []
            result = watchdog_tick(
                status_reader=lambda: calls.append("status"),
                starter=lambda: calls.append("start"),
                state_path=Path(tmp) / "watchdog.json",
                stop_path=stop,
            )
        self.assertEqual(result["status"], "governed_stop_active")
        self.assertFalse(result["started"])
        self.assertEqual(calls, [])

    def test_stop_marker_appearing_during_recovery_prevents_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop = Path(tmp) / "supervisor.stop"
            calls = []

            def readiness():
                stop.write_text("stop during recovery", encoding="utf-8")
                return {"ready": True, "blockers": []}

            result = watchdog_tick(
                status_reader=lambda: {
                    "active": False,
                    "status": "runner_stale_or_stopped",
                    "orphan_processes": [],
                },
                starter=lambda: calls.append("start"),
                state_path=Path(tmp) / "watchdog.json",
                stop_path=stop,
                supervisor_lock_reader=lambda: 0,
                readiness_reader=readiness,
            )
        self.assertEqual(result["status"], "governed_stop_active")
        self.assertEqual(calls, [])

    def test_repeated_watchdog_cycles_remain_contained_with_stale_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            stop = Path(tmp) / "supervisor.stop"
            stop.write_text("persistent stop", encoding="utf-8")
            calls = []
            for _ in range(3):
                result = watchdog_tick(
                    status_reader=lambda: {
                        "active": False,
                        "status": "runner_stale_or_stopped",
                        "orphan_processes": [],
                    },
                    starter=lambda: calls.append("start"),
                    state_path=Path(tmp) / "watchdog.json",
                    stop_path=stop,
                    supervisor_lock_reader=lambda: 0,
                    supervisor_state_reader=lambda: {
                        "status": "runner_started",
                        "pid": 208684,
                        "child_pid": 209164,
                    },
                )
                self.assertEqual(result["status"], "governed_stop_active")
        self.assertEqual(calls, [])

    def test_windows_task_trusts_only_designated_runner_worktree(self):
        script = (Path(__file__).parents[1] / "scripts" / "charlie_runner_watchdog_task.ps1").read_text(encoding="utf-8")
        self.assertIn("safe.directory $repo", script)
        self.assertNotIn("safe.directory '*'", script)
        self.assertIn("charlie_runner_watchdog.py", script)
        self.assertIn("charlie-runner-core-live-base", script)

    def test_installed_watchdog_runs_hidden(self):
        script = (Path(__file__).parents[1] / "scripts" / "install_charlie_runner_watchdog.ps1").read_text(encoding="utf-8")
        self.assertIn("pythonw.exe", script)
        self.assertNotIn("powershell.exe", script.lower())
        self.assertIn("charlie-runner-core-live-base", script)

    def test_healthy_runner_is_not_started_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            result = watchdog_tick(
                status_reader=lambda: {"active": True, "status": "runner_active"},
                starter=lambda: calls.append(True),
                state_path=Path(tmp) / "watchdog.json",
                supervisor_lock_reader=lambda: 0,
            )
        self.assertEqual(result["status"], "runner_healthy")
        self.assertFalse(result["started"])
        self.assertEqual(calls, [])

    def test_live_process_with_deadlocked_queue_is_not_reported_healthy(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": True, "status": "runner_active", "queue_health": {
                    "deadlocked": True, "approved_count": 5, "runnable_count": 0,
                    "dependency_blocked_ids": ["M-1", "M-2"],
                }},
                starter=lambda: self.fail("must not restart a live runner"),
                state_path=Path(tmp) / "watchdog.json",
                supervisor_lock_reader=lambda: 0,
            )
        self.assertEqual(result["status"], "runner_queue_deadlocked")
        self.assertEqual(result["approved_count"], 5)
        self.assertEqual(result["runnable_count"], 0)

    def test_stopped_runner_starts_supervisor(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": False, "status": "runner_stale_or_stopped", "orphan_processes": []},
                starter=lambda: ({"status": "runner_started"}, 200),
                state_path=Path(tmp) / "watchdog.json",
                supervisor_lock_reader=lambda: 0,
                readiness_reader=lambda: {"ready": True, "blockers": []},
            )
        self.assertEqual(result["status"], "runner_started")
        self.assertTrue(result["started"])

    def test_cold_start_blockers_prevent_supervisor_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": False, "status": "runner_stale_or_stopped", "orphan_processes": []},
                starter=lambda: self.fail("must not start before cold-start gates pass"),
                state_path=Path(tmp) / "watchdog.json",
                supervisor_lock_reader=lambda: 0,
                readiness_reader=lambda: {"ready": False, "blockers": ["github_auth_invalid"]},
            )
        self.assertEqual(result["status"], "cold_start_preflight_blocked")
        self.assertEqual(result["blockers"], ["github_auth_invalid"])

    def test_tick_writes_process_scoped_safe_git_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "watchdog.json"
            watchdog_tick(
                status_reader=lambda: {"active": True, "status": "runner_active"},
                starter=lambda: self.fail("must not start"),
                state_path=state,
                supervisor_lock_reader=lambda: 0,
            )
            config = state.with_name("task-gitconfig")
            self.assertTrue(config.exists())
            self.assertIn("safe", config.read_text(encoding="utf-8"))

    def test_safe_git_config_includes_separate_execution_worktree(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / "task-gitconfig"
            _configure_git_safe_directory(config)
            content = config.read_text(encoding="utf-8")
            execution_root = str(Path(tmp) / "core-execution-current").replace("\\", "/")
            self.assertIn(f'directory = "{execution_root}"', content)
            self.assertEqual(content.count("directory ="), 2)

    def test_orphan_is_not_duplicated(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": False, "status": "runner_orphaned", "orphan_processes": [{"pid": 5}]},
                starter=lambda: self.fail("must not start over an orphan"),
                state_path=Path(tmp) / "watchdog.json",
                supervisor_lock_reader=lambda: 0,
            )
        self.assertEqual(result["status"], "orphan_requires_cleanup")

    def test_live_supervisor_lock_prevents_duplicate_start_during_heartbeat_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": False, "status": "runner_stale_or_stopped", "orphan_processes": []},
                starter=lambda: self.fail("must not start over live supervisor"),
                state_path=Path(tmp) / "watchdog.json",
                supervisor_lock_reader=lambda: 4321,
            )
        self.assertEqual(result["status"], "supervisor_healthy_runner_starting")
        self.assertEqual(result["supervisor_pid"], 4321)

    def test_infrastructure_hold_prevents_watchdog_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": False, "status": "runner_stale_or_stopped", "orphan_processes": []},
                starter=lambda: self.fail("must not restart an infrastructure hold"),
                state_path=Path(tmp) / "watchdog.json",
                supervisor_lock_reader=lambda: 0,
                hold_reader=lambda: {"status": "infrastructure_hold", "failure_status": "base_branch_checkout_failed", "identical_failure_count": 3},
            )
        self.assertEqual(result["status"], "infrastructure_hold")
        self.assertFalse(result["started"])
        self.assertEqual(result["identical_failure_count"], 3)

    def test_restart_pending_is_not_reported_as_healthy_startup(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = watchdog_tick(
                status_reader=lambda: {"active": False, "status": "runner_stale_or_stopped", "orphan_processes": []},
                starter=lambda: self.fail("must not start over live supervisor"),
                state_path=Path(tmp) / "watchdog.json",
                supervisor_lock_reader=lambda: 4321,
                supervisor_state_reader=lambda: {"status": "runner_exited_restart_pending", "restart_count": 7, "identical_failure_count": 2, "latest_failure": {"status": "child_process_exited"}},
            )
        self.assertEqual(result["status"], "supervisor_child_crash_restarting")
        self.assertEqual(result["restart_count"], 7)


if __name__ == "__main__":
    unittest.main()
