"""Synthetic canonical successful-stop lifecycle; no native task/process operations."""
import copy
import json
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from datetime import datetime, timezone

from modules.charlie import runtime_activation as activation
from modules.charlie import runtime_staging as staging
from modules.charlie.process_ownership import (generate_controller_signing_key,
    sign_controller_acknowledgement, process_tree_identity_digest)
from scripts import charlie_runner_watchdog as watchdog
from scripts import charlie_runtime_activation as cli
from tests import test_charlie_runtime_activation as fixtures
from tests import test_charlie_runtime_staging as stage_fixtures


class SuccessfulActivationStopTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.signing_key, cls.public_key = generate_controller_signing_key()

    def setUp(self):
        self.f = fixtures.RuntimeActivationTests(methodName="runTest")
        self.f.setUp()
        self.original_stop_bytes = self.f.stop.read_bytes()
        manifest = json.loads(self.f.manifest.read_bytes())
        manifest["runtime_root"] = str(self.f.runtime)
        self.f.manifest.write_text(json.dumps(manifest))
        self.f.authority = self.f._authority(); self.f._write_authority()
        self.addCleanup(self.f.tearDown)
        self.state = self.f.state
        self.plan, self.controller, _ = self.f._prepared()
        self.packet = self.f._mark_started()
        self.id = self.plan["activation_id"]
        self.ledger = self.state / "activation-ledger"
        supervisor_tree = {"root": {"pid": 100}, "members": [{"pid": 100}]}
        runner_tree = {"root": {"pid": 101}, "members": [{"pid": 101}]}
        final = {"revision": fixtures.SOURCE, "activation_id": self.id,
            "generation": "synthetic-generation", "execution_mode": "observe_only",
            "supervisor_tree_digest": process_tree_identity_digest(supervisor_tree),
            "runner_tree_digest": process_tree_identity_digest(runner_tree)}
        signature = sign_controller_acknowledgement(final, self.signing_key)
        public_key = self.public_key
        self.supervisor = {"status": "operational_authorized", "pid": 100, "child_pid": 101,
            "activation_id": self.id, "generation": "synthetic-generation",
            "execution_mode": "observe_only", "startup_nonce": "supervisor-nonce",
            "runner_startup_nonce": "runner-nonce", "supervisor_tree_identity": supervisor_tree,
            "process_tree_identity": runner_tree, "controller_final_acknowledgement": {
                **final, "signature": signature}, "controller_public_key": public_key,
            "intended_runtime_revision": fixtures.SOURCE, "intended_execution_revision": fixtures.SOURCE}
        self.save_supervisor()
        (self.state / "runner.json").write_text(json.dumps({"activation_id": self.id,
            "runner_source_commit": fixtures.SOURCE, "execution_mode": "observe_only",
            "last_seen": datetime.now(timezone.utc).isoformat()}))
        def live(tree, **_kwargs):
            return {"authorized": True, "member_pids": [m["pid"] for m in tree["members"]]}
        # Only the native live inspection boundary is replaced. Signature, reader,
        # prepare/consume records, verifier, durable archive and stop APIs are real.
        result = activation.verify_or_recover_activation(state_root=self.state,
            verification_reader=lambda packet: activation.read_activation_runtime_evidence(
                packet, state_root=self.state, live_validator=live),
            task_controller=self.controller, task_reader=lambda: self.f.task, git_runner=self.f.git)
        self.assertEqual(result["status"], "activation_verified")
        self.f.task[0]["state"] = "Running"
        def disable(digest):
            self.controller.disabled.append(digest)
            self.f.task[0]["state"] = "Disabled"
        self.controller.disable_exact = disable
        self.presence = Mock(return_value="absent")

    def save_supervisor(self):
        (self.state / "supervisor.json").write_text(json.dumps(self.supervisor))

    def request(self):
        return activation.request_successful_activation_stop(state_root=self.state,
            activation_id=self.id, task_controller=self.controller,
            task_reader=lambda: self.f.task, git_runner=self.f.git)

    def exit_cleanly(self):
        self.supervisor.update(status="supervisor_stopped", return_code=0)
        self.save_supervisor()
        self.controller.instance_state = "exited"

    def complete(self):
        return activation.complete_successful_activation_stop(state_root=self.state,
            activation_id=self.id, task_controller=self.controller,
            task_reader=lambda: self.f.task, process_presence_reader=self.presence)

    def validate(self, projection):
        return activation.validate_successful_stop_projection(projection, self.state,
            task_reader=lambda: self.f.task, task_controller=self.controller,
            process_presence_reader=self.presence)

    def test_real_reader_binds_ownership_and_stop_preserves_success(self):
        marker = (self.state / "activation-verification-complete.json").read_bytes()
        self.assertEqual(self.request()["status"], "activation_stop_requested")
        self.assertEqual(self.f.stop.read_bytes(), self.original_stop_bytes)
        self.assertEqual(self.controller.disabled, [self.plan["task_action_sha256"]])
        self.assertEqual(self.controller.audit_restored, [])
        with self.assertRaisesRegex(activation.ActivationError, "not_cleanly_stopped"):
            self.complete()
        self.exit_cleanly()
        projection = self.complete()
        self.assertEqual(self.validate(projection), projection)
        self.assertEqual((self.state / "activation-verification-complete.json").read_bytes(), marker)
        self.assertEqual({c.args[0] for c in self.presence.call_args_list}, {10, 100, 101})
        self.assertFalse(list(self.ledger.glob("*-failure.json")))
        self.assertFalse(list(self.ledger.glob("*-recovery-completed.json")))
        self.assertFalse((self.state / "activation-reconciliation.lock").exists())

    def test_request_replay_does_not_disable_twice_or_rewrite_marker(self):
        self.request()
        first = {p.name: p.read_bytes() for p in self.ledger.iterdir() if p.is_file()}
        self.request()
        self.assertEqual(self.controller.disabled, [self.plan["task_action_sha256"]])
        self.assertEqual(first, {p.name: p.read_bytes() for p in self.ledger.iterdir() if p.is_file()})

    def test_completion_replay_rechecks_absence_without_rewriting_history(self):
        self.request(); self.exit_cleanly(); first = self.complete()
        bytes_before = {p.name: p.read_bytes() for p in self.ledger.iterdir() if p.is_file()}
        self.assertEqual(self.complete(), first)
        self.assertEqual(bytes_before, {p.name: p.read_bytes() for p in self.ledger.iterdir() if p.is_file()})
        self.presence.return_value = "live"
        with self.assertRaisesRegex(activation.ActivationError, "still_live"):
            self.complete()

    def test_tampered_archive_or_rollback_refuses_before_disable(self):
        for path in (self.ledger / f"{self.id}-rollback.json",
                     self.ledger / f"{self.id}-verified-activation-packet.json",
                     self.state / "activation-verification-complete.json"):
            with self.subTest(path=path.name):
                original = path.read_bytes(); data=json.loads(original)
                data["activation_id"] = "2"*32; path.write_text(json.dumps(data))
                with self.assertRaises(activation.ActivationError): self.request()
                self.assertEqual(self.controller.disabled, [])
                path.write_bytes(original)

    def test_wrong_task_identity_and_conflicting_stop_refuse_before_disable(self):
        self.f.task[0]["arguments"] += " --substituted"
        with self.assertRaises(activation.ActivationError): self.request()
        self.f.task[0]["arguments"] = self.packet["task_ownership"][0]["arguments"]
        self.f.stop.write_text("unrelated marker")
        with self.assertRaisesRegex(activation.ActivationError, "marker_conflict"): self.request()
        self.assertEqual(self.controller.disabled, [])
        self.assertEqual(self.f.stop.read_text(), "unrelated marker")

    def test_signed_but_unbound_rollback_marker_is_rejected(self):
        path=self.ledger/f"{self.id}-rollback.json"; row=json.loads(path.read_bytes())
        row["stop_marker_bytes_b64"]="bm90LW9yaWdpbmFs"
        row["rollback_hmac_sha256"]=activation._sign_record(row,self.f.key,"rollback_hmac_sha256")
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(activation.ActivationError,"original_marker_invalid"): self.request()
        self.assertEqual(self.controller.disabled, [])

    def test_generation_creation_or_pid_drift_refuses(self):
        original=copy.deepcopy(self.supervisor)
        for field,value in (("generation","new"),("pid",102),
                            ("supervisor_tree_identity",{"root":{"pid":100,"creation_time":"changed"}})):
            with self.subTest(field=field):
                self.supervisor=copy.deepcopy(original); self.supervisor[field]=value; self.save_supervisor()
                with self.assertRaisesRegex(activation.ActivationError,"process_identity_changed"): self.request()
                self.assertEqual(self.controller.disabled, [])

    def test_unknown_and_live_processes_never_complete_or_kill(self):
        self.request(); self.exit_cleanly()
        for value in ("live","unknown",None):
            with self.subTest(value=value):
                self.presence.return_value=value
                with self.assertRaises(activation.ActivationError): self.complete()
                self.assertFalse((self.ledger/f"{self.id}-stop-completed.json").exists())
        self.assertEqual(self.f.stop.read_bytes(),self.original_stop_bytes)

    def test_provider_running_unknown_or_other_instance_never_completes(self):
        self.request(); self.exit_cleanly()
        for value in ("running","unknown"):
            with self.subTest(value=value):
                self.controller.instance_state=value
                with self.assertRaisesRegex(activation.ActivationError,"provider_still_running"): self.complete()
        self.controller.instance_state="exited"
        self.controller.assert_no_running_instances=Mock(side_effect=activation.ActivationError("other_instance"))
        with self.assertRaisesRegex(activation.ActivationError,"other_instance"): self.complete()

    def test_child_failure_is_not_successful_stop(self):
        self.request(); self.exit_cleanly()
        for extra in ({"return_code":1},{"failure_status":"intake_child_exited"}):
            saved=copy.deepcopy(self.supervisor); self.supervisor.update(extra); self.save_supervisor()
            with self.assertRaisesRegex(activation.ActivationError,"not_cleanly_stopped"): self.complete()
            self.supervisor=saved

    def test_lane_blocks_activation_staging_recovery_and_concurrent_verifier(self):
        self.request()
        with self.assertRaisesRegex(activation.ActivationError,"reconciliation_lane_active"):
            self.f._plan()
        with self.assertRaisesRegex(activation.ActivationError,"reconciliation_lane_active"):
            activation.prepare_activation(self.plan,task_controller=self.controller,
                task_reader=lambda:self.f.task,git_runner=self.f.git)
        with self.assertRaisesRegex(activation.ActivationError,"successful_stop_genuine_failure_required"):
            activation.recover_activation(state_root=self.state,activation_id=self.id,
                task_controller=self.controller,failure_evidence={"status":"must-not-be-used"})
        with activation._activation_verifier_lock(self.state):
            for operation in (self.request,self.complete):
                with self.assertRaisesRegex(activation.ActivationError,"already_active"): operation()
        self.assertFalse(list(self.ledger.glob("*-failure.json")))

    def test_existing_or_racing_activation_release_lane_prevents_stop_effect(self):
        for name in ("activation.lock","release-staging.lock"):
            with self.subTest(name=name):
                path=self.state/name; path.write_text("other")
                with self.assertRaisesRegex(activation.ActivationError,"conflicting_lane"): self.request()
                path.unlink()
        original=activation._exclusive_json
        def race(path,value):
            original(path,value)
            if Path(path).name=="activation-reconciliation.lock":
                (self.state/"release-staging.lock").write_text("new staging")
        with patch.object(activation,"_exclusive_json",side_effect=race):
            with self.assertRaisesRegex(activation.ActivationError,"conflicting_lane"): self.request()
        self.assertEqual(self.controller.disabled, [])
        self.assertFalse(self.f.stop.exists())

    def test_interrupted_lane_and_disable_resume_without_replaying_activation(self):
        original=activation._exclusive_json
        def crash(path,value):
            if Path(path).name.endswith("-stop-request.json"): raise OSError("synthetic crash")
            return original(path,value)
        with patch.object(activation,"_exclusive_json",side_effect=crash):
            with self.assertRaises(OSError): self.request()
        self.assertTrue((self.state/"activation-reconciliation.lock").exists())
        with patch.object(activation,"_durable_replace",side_effect=OSError("marker crash")):
            with self.assertRaises(OSError): self.request()
        self.assertEqual(self.f.task[0]["state"],"Disabled")
        self.request()
        self.assertEqual(len(self.controller.disabled),1)
        self.assertEqual(len(self.controller.enabled),1)

    def test_completion_interruption_restores_projection_then_archives_lane(self):
        self.request(); self.exit_cleanly()
        original=activation._atomic_json
        def crash(path,value):
            if Path(path).name=="watchdog.json": raise OSError("synthetic crash")
            return original(path,value)
        with patch.object(activation,"_atomic_json",side_effect=crash):
            with self.assertRaises(OSError): self.complete()
        self.assertTrue((self.state/"activation-reconciliation.lock").exists())
        completed=(self.ledger/f"{self.id}-stop-completed.json").read_bytes()
        projection=self.complete()
        self.assertEqual(self.validate(projection),projection)
        self.assertEqual((self.ledger/f"{self.id}-stop-completed.json").read_bytes(),completed)

    def test_real_watchdog_consumer_preserves_and_revalidates_success_projection(self):
        self.request();self.exit_cleanly();projection=self.complete()
        with patch.object(watchdog,"_configure_git_safe_directory"), \
             patch.object(activation,"WindowsExactTaskController",return_value=self.controller), \
             patch.object(activation,"_process_presence",self.presence), \
             patch.object(activation,"read_watchdog_task",return_value=self.f.task):
            # Function defaults retain original reader; explicitly bind only that OS boundary.
            real=activation.validate_successful_stop_projection
            def read(value,root): return real(value,root,task_reader=lambda:self.f.task,
                task_controller=self.controller,process_presence_reader=self.presence)
            with patch.object(watchdog,"validate_successful_stop_projection",side_effect=read):
                result=watchdog.watchdog_tick(state_path=self.state/"watchdog.json",stop_path=self.f.stop,
                    starter=Mock(side_effect=AssertionError("must not start")))
                self.assertEqual(result,projection)
                (self.state/"watchdog.json").write_text(json.dumps({"status":"governed_stop_active"}))
                with self.assertRaises(activation.ActivationError):
                    watchdog.watchdog_tick(state_path=self.state/"watchdog.json",stop_path=self.f.stop)

    def test_cli_routes_request_and_verification_separately(self):
        for action,name in (("request-stop","request_successful_activation_stop"),
                            ("verify-stop","complete_successful_activation_stop")):
            with self.subTest(action=action), patch.object(cli,"WindowsExactTaskController",return_value=self.controller), \
                 patch.object(cli,name,return_value={"status":action}) as operation,patch("builtins.print"):
                self.assertEqual(cli.main([action,"--state-root",str(self.state),"--activation-id",self.id]),0)
                self.assertEqual(operation.call_args.kwargs["activation_id"],self.id)

    def test_completed_request_replay_rechecks_native_boundaries_without_effect(self):
        self.request(); self.exit_cleanly(); projection=self.complete()
        with patch.object(activation,"_process_presence",self.presence):
            self.assertEqual(self.request(),projection)
        self.assertEqual(len(self.controller.disabled),1)

    def test_legacy_verified_completion_has_no_inferred_stop_authority(self):
        path=self.state/"activation-verification-complete.json"
        row=json.loads(path.read_bytes()); row["evidence"].pop("stop_identity")
        row["completion_hmac_sha256"]=activation._sign_record(row,self.f.key,"completion_hmac_sha256")
        path.write_text(json.dumps(row))
        with self.assertRaisesRegex(activation.ActivationError,"verified_identity_missing"): self.request()
        self.assertEqual(self.controller.disabled,[])

    def test_actual_nonzero_child_can_enter_existing_recovery_after_interruption(self):
        self.request(); self.exit_cleanly()
        self.supervisor.update(return_code=1,failure_status="intake_child_exited");self.save_supervisor()
        original=activation._atomic_json
        def crash(path,value):
            if Path(path).name=="activation-reconciliation-pending.json": raise OSError("crash after failure proof")
            return original(path,value)
        args=dict(state_root=self.state,activation_id=self.id,task_controller=self.controller,
                  failure_evidence={"status":"caller value must not supply actual failure"})
        with patch.object(activation,"_atomic_json",side_effect=crash):
            with self.assertRaises(OSError): activation.recover_activation(**args)
        self.assertTrue((self.ledger/f"{self.id}-stop-recovery-handoff.json").exists())
        self.assertEqual(activation.recover_activation(**args)["status"],"activation_recovered")
        result=activation.reconcile_recovered_activation_stop(state_root=self.state,
            activation_id=self.id,failure_evidence={},task_reader=lambda:self.f.task,
            process_presence_reader=self.presence)
        self.assertEqual(result["version"],activation.RECOVERY_PROJECTION_VERSION)
        failure=json.loads((self.ledger/f"{self.id}-failure.json").read_bytes())
        import base64
        self.assertEqual(json.loads(base64.b64decode(failure["failure_bytes_b64"]))["return_code"],1)
        self.assertTrue((self.ledger/f"{self.id}-stop-failed-lane.json").exists())
        self.assertFalse((self.ledger/f"{self.id}-stop-completed.json").exists())

    def test_new_generation_recovery_is_not_blocked_by_old_success_marker(self):
        self.request();self.exit_cleanly();self.complete()
        old_completion=(self.state/"activation-verification-complete.json").read_bytes()
        self.f.authority=self.f._authority();self.f.authority["activation_id"]="2"*32
        self.f.authority["signature_hmac_sha256"]=activation._sign_record(
            self.f.authority,self.f.key,"signature_hmac_sha256")
        self.f._write_authority();plan=self.f._plan()
        activation.prepare_activation(plan,task_controller=self.controller,
            task_reader=lambda:self.f.task,git_runner=self.f.git)
        with self.assertRaisesRegex(activation.ActivationError,"conflicting_lane"): self.complete()
        activation.recover_activation(state_root=self.state,activation_id="2"*32,
            task_controller=self.controller,failure_evidence={"status":"actual_new_start_failure"})
        result=activation.reconcile_recovered_activation_stop(state_root=self.state,
            activation_id="2"*32,failure_evidence={},task_reader=lambda:self.f.task,
            process_presence_reader=self.presence)
        self.assertEqual((self.state/"activation-verification-complete.json").read_bytes(),old_completion)
        def reconcile(**kwargs):
            return activation.reconcile_recovered_activation_stop(**kwargs,
                task_reader=lambda:self.f.task,process_presence_reader=self.presence)
        with patch.object(watchdog,"_configure_git_safe_directory"):
            self.assertEqual(watchdog.watchdog_tick(state_path=self.state/"watchdog.json",
                stop_path=self.f.stop,activation_reconciler=reconcile),result)
        staging._validate_recovery_projection(result,self.state)

    def test_real_staging_plan_authenticates_stop_and_accepts_next_source(self):
        self.request();self.exit_cleanly();projection=self.complete()
        st=stage_fixtures.RuntimeStagingTests(methodName="runTest");st.setUp();self.addCleanup(st.tearDown)
        (self.state/"validation-receipt.key").write_bytes(st.receipt_key)
        from modules.charlie.validation_receipt import record_validation_receipt
        receipt=record_validation_receipt(json.loads(st.receipt.read_bytes()),self.state)
        git=stage_fixtures.FakeGit(self.f.runtime,self.f.execution)
        git.heads={str(self.f.runtime):fixtures.SOURCE,str(self.f.execution):fixtures.SOURCE}
        git.branches={str(self.f.runtime):"",str(self.f.execution):""}
        def plan():
            return staging.plan_runtime_staging(source_ref=stage_fixtures.SOURCE,
                runtime_root=self.f.runtime,execution_root=self.f.execution,state_root=self.state,
                receipt_path=receipt["path"],receipt_sha256=activation._sha256(receipt["path"]),
                expected_runtime_head=fixtures.SOURCE,expected_execution_head=fixtures.SOURCE,
                expected_manifest_commit=fixtures.SOURCE,task_reader=lambda:self.f.task,
                expected_task_sha256=staging._payload_sha256(self.f.task),
                runner=git,git_safety_checker=st._safe_git)
        with patch.object(activation,"WindowsExactTaskController",return_value=self.controller), \
             patch.object(activation,"_process_presence",self.presence):
            self.assertEqual(plan()["status"],"runtime_staging_plan_ready")
            self.presence.return_value="unknown"
            with self.assertRaisesRegex(activation.ActivationError,"proof_unavailable"): plan()
            self.presence.return_value="absent"
            for changed in ({**projection,"stop_hmac_sha256":"0"*64},
                            {"status":"governed_stop_active"},
                            {**projection,"completed_activation_id":"3"*32}):
                (self.state/"watchdog.json").write_text(json.dumps(changed))
                with self.assertRaises(activation.ActivationError): plan()

    def test_actual_nonzero_exit_recovery_keeps_stop_conflict(self):
        self.request(); self.exit_cleanly()
        self.supervisor.update(return_code=1, failure_status="intake_child_exited")
        self.save_supervisor()
        self.f.stop.write_text("Scoped intake exited; explicit recovery required.\n")
        diagnostic_bytes = self.f.stop.read_bytes()
        with self.assertRaisesRegex(activation.ActivationError, "activation_recovery_incomplete") as caught:
            activation.recover_activation(state_root=self.state, activation_id=self.id,
                task_controller=self.controller, failure_evidence={"status":"caller"})
        self.assertIn({"component":"governed_stop", "status":"governed_stop_conflict_during_recovery"}, caught.exception.evidence["errors"])
        handoff = json.loads((self.ledger/f"{self.id}-stop-recovery-handoff.json").read_bytes())
        self.assertEqual(handoff["failure_evidence"]["failure_status"], "intake_child_exited")
        self.assertEqual(handoff["failure_evidence"]["return_code"], 1)
        self.assertEqual(self.f.stop.read_bytes(), diagnostic_bytes)
        self.assertFalse((self.ledger/f"{self.id}-stop-completed.json").exists())
        self.assertFalse((self.ledger/f"{self.id}-recovery-completed.json").exists())
        self.assertTrue((self.state/"activation-reconciliation.lock").exists())

    def test_archived_completion_replay_is_read_only_even_if_new_activation_races(self):
        self.request(); self.exit_cleanly(); projection = self.complete()
        def race(_pid):
            (self.state/"activation.lock").write_text("new generation acquired after absence checks")
            return "absent"
        self.presence.side_effect = race
        with patch.object(activation, "_atomic_json", side_effect=AssertionError("old projection write")), \
             patch.object(activation, "_exclusive_json", side_effect=AssertionError("old completion write")):
            self.assertEqual(self.complete(), projection)
        self.assertEqual(json.loads((self.state/"watchdog.json").read_bytes()), projection)

    def test_archived_lane_cannot_repair_missing_completion_or_projection(self):
        self.request(); self.exit_cleanly(); self.complete()
        path=self.ledger/f"{self.id}-stop-completed.json"; original=path.read_bytes()
        path.unlink()
        with self.assertRaisesRegex(activation.ActivationError,"completion_missing"): self.complete()
        path.write_bytes(original)
        (self.state/"watchdog.json").unlink()
        with self.assertRaises(activation.ActivationError): self.complete()
        self.assertFalse((self.state/"watchdog.json").exists())

    def test_return_code_requires_integer_for_success_and_failed_handoff(self):
        self.request(); self.exit_cleanly()
        for invalid in (False, None, "0", "1"):
            with self.subTest(return_code=invalid):
                self.supervisor["return_code"]=invalid; self.save_supervisor()
                with self.assertRaisesRegex(activation.ActivationError,"not_cleanly_stopped"):
                    self.complete()
                with self.assertRaisesRegex(activation.ActivationError,"genuine_failure_required"):
                    activation.recover_activation(state_root=self.state, activation_id=self.id,
                        task_controller=self.controller, failure_evidence={"status":"caller"})
        self.assertFalse((self.ledger/f"{self.id}-stop-completed.json").exists())
        self.assertFalse((self.ledger/f"{self.id}-stop-recovery-handoff.json").exists())

    def test_unexpected_zero_failure_is_bound_to_intake_mode_only(self):
        self.request(); self.exit_cleanly()
        self.supervisor.update(return_code=0, failure_status="intake_child_exited"); self.save_supervisor()
        with self.assertRaisesRegex(activation.ActivationError, "genuine_failure_required"):
            activation._failed_successful_stop_handoff(self.state, self.id)
        # Isolate the mode predicate with a signed intake binding. The complete
        # archived completion/context validator is covered by the lifecycle tests.
        packet, rollback, binding, original_bytes, key = activation._successful_stop_context(self.state,self.id)
        binding=copy.deepcopy(binding); binding["stop_identity"]["execution_mode"]=activation.INTAKE_EXECUTION_MODE
        self.supervisor["execution_mode"]=activation.INTAKE_EXECUTION_MODE; self.save_supervisor()
        for path,status in ((self.state/"activation-reconciliation.lock","successful_stop_lane_owned"),
                            (self.ledger/f"{self.id}-stop-request.json","activation_stop_requested")):
            row={**binding,"status":status}
            row["stop_hmac_sha256"]=activation._sign_record(row,key,"stop_hmac_sha256")
            path.write_text(json.dumps(row))
        with patch.object(activation,"_successful_stop_context",return_value=(packet,rollback,binding,original_bytes,key)):
            handoff=activation._failed_successful_stop_handoff(self.state,self.id)
        self.assertEqual(handoff["failure_evidence"]["return_code"],0)
        self.assertEqual(handoff["failure_evidence"]["execution_mode"],activation.INTAKE_EXECUTION_MODE)
