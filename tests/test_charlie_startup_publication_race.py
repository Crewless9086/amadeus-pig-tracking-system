"""Synthetic provider races through the real activation/recovery boundaries."""

import json
import threading
import unittest
from contextlib import contextmanager
from datetime import timedelta
from pathlib import Path
from unittest.mock import Mock, patch

from modules.charlie import runtime_activation as a
from tests import test_charlie_runtime_activation as fixture


class StartupPublicationRaceTests(unittest.TestCase):
    def setUp(self):
        self.f = fixture.RuntimeActivationTests()
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.plan, self.controller, _ = self.f._prepared()
        self.state = self.f.state
        (self.state / "supervisor.json").unlink()
        self.packet = json.loads((self.state / "activation-packet.json").read_text())
        self.activation_id = self.packet["activation_id"]

    def origin(self, _pid):
        row = self.f.task[0]
        return {
            "inspection_complete": True, "pid": 102, "parent_pid": 101,
            "executable_path": row["execute"],
            "command_line": f'"{row["execute"]}" {row["arguments"]}',
            "ancestry": [{"pid": 101, "executable_path": "svchost.exe",
                "provider_identity_verified": True,
                "instance_guid": self.packet["expected_instance_guid"],
                "action_execute": row["execute"], "action_arguments": row["arguments"],
                "action_working_directory": row["working_directory"]}],
        }

    def consume(self, starter, inspector=None):
        return a.consume_provider_activation(state_root=self.state, starter=starter,
            task_controller=self.controller, task_reader=lambda: self.f.task,
            provider_inspector=inspector or self.origin, git_runner=self.f.git)

    def recover(self):
        return a.recover_activation(state_root=self.state, task_controller=self.controller,
            activation_id=self.activation_id,
            failure_evidence={"status": "synthetic_verification_failure"})

    def assert_unconsumed(self):
        self.assertFalse((self.state / f"activation-consumed-{self.activation_id}.json").exists())

    def test_initial_absence_is_pending_not_ready(self):
        evidence = a.read_activation_runtime_evidence(self.packet, state_root=self.state)
        self.assertEqual(evidence, {"publication_status": "activation_bound_startup_in_progress"})
        self.assert_unconsumed()

    def test_malformed_present_publication_remains_terminal(self):
        for filename in ("supervisor.json", "runner.json"):
            with self.subTest(filename=filename):
                path = self.state / filename
                path.write_text("invalid json")
                with self.assertRaises(a.ActivationError):
                    a.read_activation_runtime_evidence(self.packet, state_root=self.state)
                path.unlink()

    def test_present_bound_failure_is_not_hidden_by_missing_peer(self):
        for filename, status in (("supervisor.json", "start_failed"),
                                 ("runner.json", "failed")):
            with self.subTest(filename=filename):
                path = self.state / filename
                path.write_text(json.dumps({"activation_id": self.activation_id, "status": status}))
                self.assertEqual(a.read_activation_runtime_evidence(
                    self.packet, state_root=self.state)["publication_status"], "activation_bound_failed")
                path.unlink()

    def test_actual_absent_reader_waits_and_provider_can_publish_under_verifier(self):
        ticks = [0.0]
        reads = []
        ready = {key: True for key in (
            "loaded_revision_exact", "execution_mode_observe_only", "signed_supervisor_tree",
            "signed_runner_tree", "heartbeat_fresh", "activation_id_exact", "unrelated_processes_absent")}
        starter = Mock(return_value=({"status": "started"}, 200))
        def reader(packet):
            reads.append(packet["status"])
            if packet["status"] == "provider_pending":
                return a.read_activation_runtime_evidence(packet, state_root=self.state)
            return {**ready, "publication_status": "activation_bound_ready"}
        def advance(_seconds):
            ticks[0] += 0.01
            self.consume(starter)
        result = a.verify_or_recover_activation(state_root=self.state,
            verification_reader=reader, task_controller=self.controller,
            task_reader=lambda: self.f.task, git_runner=self.f.git,
            monotonic_fn=lambda: ticks[0], sleep_fn=advance)
        self.assertEqual(result["status"], "activation_verified")
        self.assertEqual(reads, ["provider_pending", "provider_started_observe_only"])
        starter.assert_called_once()
        self.assertEqual(self.controller.disabled, [])

    def test_initial_absence_requires_exact_running_provider(self):
        self.controller.instance_state = "exited"
        with self.assertRaises(a.ActivationError) as caught:
            a.verify_or_recover_activation(state_root=self.state,
                task_controller=self.controller, task_reader=lambda: self.f.task,
                git_runner=self.f.git)
        self.assertEqual(caught.exception.evidence["evidence_status"],
                         "activation_provider_exited_before_publication")
        self.assertTrue(self.f.stop.exists())

    def test_initial_absence_timeout_contains_instead_of_accepting(self):
        with self.assertRaises(a.ActivationError) as caught:
            a.verify_or_recover_activation(state_root=self.state,
                task_controller=self.controller, task_reader=lambda: self.f.task,
                git_runner=self.f.git, readiness_timeout_seconds=0)
        self.assertEqual(caught.exception.evidence["evidence_status"], "activation_readiness_timeout")
        self.assertTrue(self.f.stop.exists())

    def test_recovery_during_slow_provider_query_prevents_late_consumption(self):
        starter = Mock()
        def late_origin(pid):
            result = self.origin(pid)
            self.recover()
            return result
        with self.assertRaisesRegex(a.ActivationError, "activation_closed_before_provider_publication"):
            self.consume(starter, late_origin)
        starter.assert_not_called()
        self.assert_unconsumed()
        self.assertFalse((self.state / "activation-packet.json").exists())
        self.assertTrue((self.state / "activation-ledger" /
                         f"{self.activation_id}-recovery-completed.json").exists())

    def test_changed_packet_during_provider_query_is_not_consumed(self):
        starter = Mock()
        def origin(pid):
            result = self.origin(pid)
            packet = dict(self.packet, expected_instance_guid="22222222-2222-2222-2222-222222222222")
            packet["packet_hmac_sha256"] = a._sign_packet(packet, self.f.key)
            (self.state / "activation-packet.json").write_text(json.dumps(packet))
            return result
        with self.assertRaisesRegex(a.ActivationError, "activation_packet_changed_before_provider_publication"):
            self.consume(starter, origin)
        starter.assert_not_called()
        self.assert_unconsumed()

    def test_changed_task_after_provider_inspection_fails_final_validation(self):
        starter = Mock()
        def origin(pid):
            result = self.origin(pid)
            self.f.task[0]["arguments"] += " --changed"
            return result
        with self.assertRaisesRegex(a.ActivationError, "activation_task_action_sha256_mismatch"):
            self.consume(starter, origin)
        starter.assert_not_called()
        self.assert_unconsumed()

    def test_recovery_restores_stop_without_archiving_while_producer_owns_lock(self):
        with a._activation_publication_lock(self.state):
            with self.assertRaisesRegex(a.ActivationError, "activation_publication_in_progress"):
                self.recover()
            self.assertTrue(self.f.stop.exists())
            self.assertEqual(len(self.controller.disabled), 1)
            self.assertTrue((self.state / "activation-packet.json").exists())
            self.assertTrue((self.state / "activation.lock").exists())
            self.assertFalse((self.state / "activation-ledger" /
                              f"{self.activation_id}-recovery-completed.json").exists())
        self.assertEqual(self.recover()["status"], "activation_recovered")

    def test_recovery_archives_strongest_packet_after_lock_acquisition(self):
        original = a._activation_publication_lock
        @contextmanager
        def acquire(state):
            with original(state):
                self.f._mark_started()
                yield
        with patch.object(a, "_activation_publication_lock", acquire):
            self.recover()
        archived = json.loads((self.state / "activation-ledger" /
            f"{self.activation_id}-recovered-activation-packet.json").read_text())
        self.assertEqual(archived["status"], "provider_started_observe_only")

    def test_containment_during_starter_preserves_actual_refusal_and_releases_before_recovery(self):
        refused = {"success": False, "status": "governed_stop_active", "stop_marker": str(self.f.stop)}
        def starter(**_kwargs):
            with self.assertRaisesRegex(a.ActivationError, "activation_publication_in_progress"):
                self.recover()
            return refused, 423
        with self.assertRaisesRegex(a.ActivationError, "provider_start_failed"):
            self.consume(starter)
        archived = json.loads((self.state / "activation-ledger" /
            f"{self.activation_id}-recovered-activation-packet.json").read_text())
        self.assertEqual(archived["start_result"], refused)
        self.assertFalse((self.state / "activation-packet.json").exists())

    def test_stop_during_success_does_not_fabricate_a_starter_refusal(self):
        actual = {"success": True, "status": "started"}
        def starter(**_kwargs):
            with self.assertRaises(a.ActivationError):
                self.recover()
            return actual, 200
        with self.assertRaisesRegex(a.ActivationError, "provider_start_failed"):
            self.consume(starter)
        archived = json.loads((self.state / "activation-ledger" /
            f"{self.activation_id}-recovered-activation-packet.json").read_text())
        self.assertEqual(archived["status"], "provider_start_failed")
        self.assertEqual(archived["start_result"], actual)

    def test_verifier_cannot_archive_ready_runtime_before_starter_returns(self):
        ready_event, finish = threading.Event(), threading.Event()
        errors = []
        def starter(**_kwargs):
            ready_event.set()
            if not finish.wait(5):
                raise AssertionError("synthetic starter barrier timed out")
            return {"success": True, "status": "started"}, 200
        def consume():
            try:
                self.consume(starter)
            except BaseException as exc:
                errors.append(exc)
        worker = threading.Thread(target=consume)
        worker.start()
        self.addCleanup(lambda: (finish.set(), worker.join(5)))
        self.assertTrue(ready_event.wait(5))
        ready = {key: True for key in (
            "loaded_revision_exact", "execution_mode_observe_only", "signed_supervisor_tree",
            "signed_runner_tree", "heartbeat_fresh", "activation_id_exact", "unrelated_processes_absent")}
        observations = []
        def reader(packet):
            observations.append(packet["status"])
            return {**ready, "publication_status": "activation_bound_ready"}
        def advance(_seconds):
            self.assertTrue((self.state / "activation.lock").exists())
            self.assertTrue((self.state / "activation-packet.json").exists())
            self.assertFalse((self.state / "activation-verification-complete.json").exists())
            finish.set(); worker.join(5)
            self.assertFalse(worker.is_alive())
        result = a.verify_or_recover_activation(state_root=self.state,
            verification_reader=reader, task_controller=self.controller,
            task_reader=lambda: self.f.task, git_runner=self.f.git, sleep_fn=advance)
        self.assertEqual(errors, [])
        self.assertEqual(observations, ["provider_pending", "provider_started_observe_only"])
        self.assertEqual(result["status"], "activation_verified")

    def test_expiry_in_initial_or_final_validation_cannot_be_omitted_from_clock(self):
        # Each case has an independent synthetic activation and complete history.
        for slow_call in (1, 3):
            with self.subTest(slow_call=slow_call):
                if slow_call == 3:
                    self.f.tearDown(); self.setUp()
                self.f._mark_started()
                ticks, calls = [0.0], [0]
                original = a._validate_packet
                def validate(*args, **kwargs):
                    result = original(*args, **kwargs)
                    calls[0] += 1
                    if calls[0] == slow_call:
                        ticks[0] += 2
                    return result
                ready = {key: True for key in (
                    "loaded_revision_exact", "execution_mode_observe_only", "signed_supervisor_tree",
                    "signed_runner_tree", "heartbeat_fresh", "activation_id_exact", "unrelated_processes_absent")}
                reader = Mock(return_value={**ready, "publication_status": "activation_bound_ready"})
                now = a._parse_time(self.packet["authority"]["expires_at"]) - timedelta(seconds=1)
                with patch.object(a, "_validate_packet", validate):
                    with self.assertRaises(a.ActivationError) as caught:
                        a.verify_or_recover_activation(state_root=self.state,
                            verification_reader=reader, task_controller=self.controller,
                            task_reader=lambda: self.f.task, git_runner=self.f.git,
                            now=now, monotonic_fn=lambda: ticks[0])
                self.assertEqual(caught.exception.evidence["evidence_status"], "activation_authority_expired")
                if slow_call == 1:
                    reader.assert_not_called()
                self.assertFalse((self.state / "activation-verification-complete.json").exists())
                self.assertTrue(self.f.stop.exists())

    def test_success_commit_waits_for_publication_lock_even_after_started_packet(self):
        published, release = threading.Event(), threading.Event()
        errors = []
        original = a._atomic_json
        def publish(path, value):
            original(path, value)
            if (Path(path).name == "activation-packet.json"
                    and value.get("status") == "provider_started_observe_only"):
                published.set()
                if not release.wait(5):
                    raise AssertionError("synthetic publication barrier timed out")
        def consume():
            try:
                self.consume(lambda **_: ({"success": True, "status": "started"}, 200))
            except BaseException as exc:
                errors.append(exc)
        ready = {key: True for key in (
            "loaded_revision_exact", "execution_mode_observe_only", "signed_supervisor_tree",
            "signed_runner_tree", "heartbeat_fresh", "activation_id_exact", "unrelated_processes_absent")}
        waits = []
        worker = threading.Thread(target=consume)
        def advance(_seconds):
            waits.append(True)
            self.assertTrue((self.state / "activation-packet.json").exists())
            self.assertFalse((self.state / "activation-verification-complete.json").exists())
            release.set(); worker.join(5)
        with patch.object(a, "_atomic_json", publish):
            worker.start()
            self.addCleanup(lambda: (release.set(), worker.join(5)))
            self.assertTrue(published.wait(5))
            result = a.verify_or_recover_activation(state_root=self.state,
                verification_reader=lambda _: {**ready, "publication_status": "activation_bound_ready"},
                task_controller=self.controller, task_reader=lambda: self.f.task,
                git_runner=self.f.git, sleep_fn=advance)
        self.assertEqual(errors, [])
        self.assertEqual(waits, [True])
        self.assertEqual(result["status"], "activation_verified")

    def test_partial_successful_archive_keeps_existing_resume_instead_of_recovery(self):
        self.f._mark_started()
        ready = {key: True for key in (
            "loaded_revision_exact", "execution_mode_observe_only", "signed_supervisor_tree",
            "signed_runner_tree", "heartbeat_fresh", "activation_id_exact", "unrelated_processes_absent")}
        original = a._durable_replace
        def fail_packet(source, target, **kwargs):
            if Path(source).name == "activation-packet.json":
                raise OSError("synthetic archival interruption")
            return original(source, target, **kwargs)
        options = dict(state_root=self.state, verification_reader=lambda _: ready,
            task_controller=self.controller, task_reader=lambda: self.f.task, git_runner=self.f.git)
        with patch.object(a, "_durable_replace", fail_packet):
            with self.assertRaisesRegex(OSError, "synthetic archival interruption"):
                a.verify_or_recover_activation(**options)
        self.assertFalse(self.f.stop.exists())
        self.assertEqual(self.controller.disabled, [])
        self.assertFalse((self.state / "activation-ledger" / f"{self.activation_id}-failure.json").exists())
        marker = json.loads((self.state / "activation-verification.lock").read_text())
        self.assertEqual(marker["status"], "activation_verification_archival_pending")
        self.assertEqual(a.verify_or_recover_activation(**options)["status"], "activation_verified")


if __name__ == "__main__":
    unittest.main()
