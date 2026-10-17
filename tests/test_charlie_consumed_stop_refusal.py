"""Canonical consumed-stop refusal proof; synthetic keys/state, no production I/O."""
import hashlib, importlib.util, json, unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch
from tests import test_charlie_runtime_activation as fixture

from modules.charlie import runtime_activation as a

class ConsumedStopRefusalTests(unittest.TestCase):
    def setUp(self):
        self.f=fixture.RuntimeActivationTests(); self.f.setUp(); self.addCleanup(self.f.tearDown)
        self.plan,self.controller,_=self.f._prepared(); self.state=self.f.state
        (self.state/"supervisor.json").unlink()
        self.id=self.plan["activation_id"]; self.ledger=self.state/"activation-ledger"
        self.packet=json.loads((self.state/"activation-packet.json").read_text())
        self.launcher=self.f.runtime/"scripts"/"charlie_runner_task_launcher.py"
        self.launcher.parent.mkdir(parents=True,exist_ok=True); self.launcher.write_bytes(b"synthetic launcher")
        self.controller.bind_exact=Mock(); self.controller.read_completed_instance_engine_pid=Mock(return_value=101)
        self.controller.assert_no_running_instances=Mock()
        a.recover_activation(state_root=self.state,task_controller=self.controller,activation_id=self.id,
            failure_evidence={"status":"activation_verification_failed","evidence_status":"supervisor_state_invalid"})
        self.old={p.name:p.read_bytes() for p in self.ledger.glob("*.json")}
        completion=json.loads((self.ledger/f"{self.id}-recovery-completed.json").read_text())
        self.consumed_at=datetime.fromisoformat(completion["completed_at"])+timedelta(seconds=1)
        self.refused_at=self.consumed_at+timedelta(seconds=1)
        self.consumed={"version":a.ACTIVATION_VERSION,"activation_id":self.id,
            "provider_pid":102,"provider_parent_pid":101,"provider_instance_guid":self.packet["expected_instance_guid"],
            "expected_instance_guid":self.packet["expected_instance_guid"],"packet_hmac_sha256":self.packet["packet_hmac_sha256"],
            "consumed_at":self.consumed_at.isoformat()}
        self.consumed_path=self.state/f"activation-consumed-{self.id}.json"
        self._write_consumed()
        self.refused={**self.packet,"status":"provider_start_failed", "provider":{
            "authorized":True,"reason":"scheduled_provider_origin_verified","pid":102,"parent_pid":101,
            "action_pid":101,"parent_executable":"svchost.exe","provider_instance_guid":self.packet["expected_instance_guid"]},
            "start_result":{"success":False,"status":"governed_stop_active","stop_marker":str(self.f.stop)},
            "provider_started_at":self.refused_at.isoformat(),"consumed_packet_hmac_sha256":self.packet["packet_hmac_sha256"]}
        self._write_refused(); self._startup()
    def _write_consumed(self):
        self.consumed["consumed_hmac_sha256"]=a._sign_record(self.consumed,self.f.key,"consumed_hmac_sha256")
        self.consumed_path.write_text(json.dumps(self.consumed))
    def _write_refused(self):
        self.refused["packet_hmac_sha256"]=a._sign_packet(self.refused,self.f.key)
        (self.state/"activation-packet.json").write_text(json.dumps(self.refused))
    def _startup(self):
        self.records=[]; directory=self.ledger/"startup-evidence"/self.id; directory.mkdir(parents=True)
        prepared=datetime.fromisoformat(self.packet["prepared_at"])
        for i,phase in enumerate(("launcher_entered","activation_packet_authenticated","environment_loaded","watchdog_entry_started","launcher_failed")):
            stamp=prepared+timedelta(milliseconds=i) if i<4 else self.refused_at+timedelta(seconds=1)
            record={"version":"charlie_core_startup_evidence_v1","activation_id":self.id,
                "activation_packet_hmac_sha256":self.packet["packet_hmac_sha256"],"recorded_at":stamp.isoformat(),
                "phase":phase,"pid":102,"launcher_path":str(self.launcher),"launcher_sha256":a._sha256(self.launcher),
                "python_executable":self.f.task[0]["execute"],"working_directory":self.f.task[0]["working_directory"]}
            if i==4: record.update(exit_code=1,error_type="ActivationError")
            record["record_hmac_sha256"]=a._sign_record(record,self.f.key,"record_hmac_sha256")
            path=directory/f"{i}.json"; path.write_text(json.dumps(record)); self.records.append(path)
    def reconcile(self,**kwargs):
        return a.reconcile_recovered_activation_stop(state_root=self.state,activation_id=self.id,
            task_reader=lambda:self.f.task,task_controller=self.controller,
            process_presence_reader=kwargs.get("presence",lambda _:"absent"))
    def unchanged(self):
        for name,raw in self.old.items(): self.assertEqual((self.ledger/name).read_bytes(),raw)
    def test_actual_late_shape_reconciles_additively_and_replays(self):
        result=self.reconcile()
        self.assertEqual(result["recovery_basis"],"authenticated_consumed_stop_refusal")
        self.assertEqual(result["supervisor_status"],"not_started"); self.assertIs(result["started"],False)
        self.assertEqual(result["pre_starter_evidence"]["known_process_pids"], [101, 102])
        self.assertFalse((self.state/"activation-packet.json").exists()); self.assertFalse(self.consumed_path.exists())
        self.assertFalse((self.state/"supervisor.json").exists()); self.assertFalse((self.state/"runner.json").exists())
        self.unchanged(); self.assertEqual(self.reconcile(),result); self.unchanged()
    def test_refusal_must_be_actual_exact_starter_return(self):
        for changed in ({"success":True,"status":"started"},{"success":False,"status":"intake_activation_refused"},
                        {"success":False,"status":"governed_stop_active","stop_marker":"wrong"}):
            with self.subTest(result=changed):
                self.refused["start_result"]=changed; self._write_refused()
                with self.assertRaisesRegex(a.ActivationError,"consumed_stop_refusal_not_proven"):self.reconcile()
                self.unchanged()
    def test_signed_late_packet_cannot_change_original_authority_or_identity(self):
        for field,value in (("authority_sha256","0"*64),("expected_instance_guid","wrong"),("prepared_at","2020-01-01T00:00:00+00:00")):
            with self.subTest(field=field):
                old=self.refused[field]; self.refused[field]=value; self._write_refused()
                with self.assertRaisesRegex(a.ActivationError,"packet_binding_invalid"):self.reconcile()
                self.refused[field]=old; self._write_refused(); self.unchanged()
    def test_consumed_signature_and_packet_binding_required(self):
        for field,value in (("packet_hmac_sha256","0"*64),("expected_instance_guid","wrong"),("provider_instance_guid","wrong")):
            with self.subTest(field=field):
                old=self.consumed[field]; self.consumed[field]=value; self._write_consumed()
                with self.assertRaisesRegex(a.ActivationError,"activation_consumed_identity_invalid"):self.reconcile()
                self.consumed[field]=old; self._write_consumed(); self.unchanged()
    def test_consumed_or_late_packet_duplicate_refused(self):
        for source,name in ((self.consumed_path,f"{self.id}-late-refused-{self.consumed_path.name}"),
                            (self.state/"activation-packet.json",f"{self.id}-late-refused-activation-packet.json")):
            with self.subTest(name=name):
                other=self.ledger/name; other.write_bytes(source.read_bytes())
                with self.assertRaises(a.ActivationError):self.reconcile()
                other.unlink(); self.unchanged()
    def test_partial_additive_archive_can_resume_without_rewriting_history(self):
        a._durable_replace(self.state/"activation-packet.json",self.ledger/f"{self.id}-late-refused-activation-packet.json")
        self.assertEqual(self.reconcile()["supervisor_status"],"not_started"); self.unchanged()
    def test_partial_runtime_or_success_never_uses_refusal_basis(self):
        for name in ("runner.json","supervisor.lock","activation-verification-complete.json"):
            with self.subTest(name=name):
                p=self.state/name;p.write_text("{}")
                with self.assertRaises(a.ActivationError):self.reconcile()
                p.unlink();self.unchanged()
    def test_unknown_or_live_process_refuses_without_archiving_late_packet(self):
        for state in ("unknown","live"):
            with self.subTest(state=state):
                with self.assertRaises(a.ActivationError):self.reconcile(presence=lambda _:state)
                self.assertTrue((self.state/"activation-packet.json").exists()); self.unchanged()
    def test_running_instance_or_changed_task_refuses(self):
        self.controller.assert_no_running_instances.side_effect=a.ActivationError("instance_running")
        with self.assertRaisesRegex(a.ActivationError,"instance_running"):self.reconcile()
        self.controller.assert_no_running_instances.side_effect=None
        self.f.task[0]["state"]="Ready"
        with self.assertRaises(a.ActivationError):self.reconcile()
        self.unchanged()
    def test_unfinished_or_earlier_launcher_failure_is_not_exit_proof(self):
        last=self.records[-1]; raw=last.read_bytes(); last.unlink()
        with self.assertRaises(a.ActivationError):self.reconcile()
        last.write_bytes(raw); row=json.loads(raw);row["recorded_at"]=self.consumed_at.isoformat()
        row["record_hmac_sha256"]=a._sign_record(row,self.f.key,"record_hmac_sha256");last.write_text(json.dumps(row))
        with self.assertRaises(a.ActivationError):self.reconcile()
        self.unchanged()
    def test_naive_inverted_or_expired_refusal_chronology_refuses(self):
        original=self.refused["provider_started_at"]
        for value in (self.refused_at.replace(tzinfo=None).isoformat(),(self.consumed_at-timedelta(seconds=1)).isoformat(),
                      (datetime.fromisoformat(self.packet["authority"]["expires_at"])+timedelta(seconds=1)).isoformat()):
            with self.subTest(value=value):
                self.refused["provider_started_at"]=value;self._write_refused()
                with self.assertRaisesRegex(a.ActivationError,"chronology_invalid"):self.reconcile()
                self.unchanged()
        self.refused["provider_started_at"]=original;self._write_refused()
    def test_ordinary_refusal_recovery_uses_same_truthful_proof(self):
        # Separate synthetic instance: remove old immutable fixture history by
        # creating a fresh fixture, never modifying history in a live lineage.
        self.f.tearDown(); self.f=fixture.RuntimeActivationTests();self.f.setUp();self.addCleanup(self.f.tearDown)
        self.plan,self.controller,_=self.f._prepared();self.state=self.f.state;self.id=self.plan["activation_id"]
        self.ledger=self.state/"activation-ledger";(self.state/"supervisor.json").unlink()
        self.packet=json.loads((self.state/"activation-packet.json").read_text())
        self.launcher=self.f.runtime/"scripts"/"charlie_runner_task_launcher.py";self.launcher.parent.mkdir(parents=True);self.launcher.write_bytes(b"synthetic launcher")
        self.consumed_at=datetime.fromisoformat(self.packet["prepared_at"])+timedelta(seconds=1);self.refused_at=self.consumed_at+timedelta(seconds=1)
        self.consumed={**self.consumed,"packet_hmac_sha256":self.packet["packet_hmac_sha256"],"consumed_at":self.consumed_at.isoformat()}
        self.consumed_path=self.state/f"activation-consumed-{self.id}.json";self._write_consumed()
        self.refused={**self.packet,"status":"provider_start_failed","provider":self.refused["provider"],
            "start_result":{"success":False,"status":"governed_stop_active","stop_marker":str(self.f.stop)},
            "provider_started_at":self.refused_at.isoformat(),"consumed_packet_hmac_sha256":self.packet["packet_hmac_sha256"]}
        self._write_refused();self._startup()
        a.recover_activation(state_root=self.state,task_controller=self.controller,activation_id=self.id,failure_evidence={"status":"provider_start_failed","start_result":self.refused["start_result"]},now=self.refused_at+timedelta(seconds=1))
        self.controller.bind_exact=Mock();self.controller.read_completed_instance_engine_pid=Mock(return_value=101);self.controller.assert_no_running_instances=Mock()
        self.assertEqual(self.reconcile()["recovery_basis"],"authenticated_consumed_stop_refusal")

    def test_numeric_zero_is_not_boolean_false_refusal(self):
        self.refused["start_result"]["success"]=0;self._write_refused()
        with self.assertRaisesRegex(a.ActivationError,"consumed_stop_refusal_not_proven"):self.reconcile()
        self.unchanged()
    def test_completed_action_pid_must_match_signed_provider(self):
        self.controller.read_completed_instance_engine_pid.return_value=103
        with self.assertRaisesRegex(a.ActivationError,"action_identity_mismatch"):self.reconcile()
        self.unchanged()
    def test_consumption_cannot_precede_authenticated_watchdog_entry(self):
        path=self.records[3]; row=json.loads(path.read_text())
        row["recorded_at"]=(self.consumed_at+timedelta(milliseconds=500)).isoformat()
        row["record_hmac_sha256"]=a._sign_record(row,self.f.key,"record_hmac_sha256");path.write_text(json.dumps(row))
        with self.assertRaisesRegex(a.ActivationError,"chronology_invalid"):self.reconcile()
        self.unchanged()
    def test_unknown_alternate_consumed_archive_refuses(self):
        (self.ledger/f"{self.id}-other-activation-consumed-{self.id}.json").write_bytes(self.consumed_path.read_bytes())
        with self.assertRaisesRegex(a.ActivationError,"activation_consumed_identity_ambiguous"):self.reconcile()
        self.unchanged()

    def _staging_fixture(self):
        from tests import test_charlie_runtime_staging as stage_fixture
        from modules.charlie.validation_receipt import record_validation_receipt
        stage = stage_fixture.RuntimeStagingTests()
        stage.setUp()
        self.addCleanup(stage.tearDown)
        stage.runtime, stage.execution, stage.state = self.f.runtime, self.f.execution, self.state
        stage.git = stage_fixture.FakeGit(stage.runtime, stage.execution)
        (self.state / "runtime-manifest.json").write_text(json.dumps({
            "runtime_root": str(stage.runtime), "promoted_commit": stage_fixture.MANIFEST}))
        (self.state / "validation-receipt.key").write_bytes(stage.receipt_key)
        stage.receipt = Path(record_validation_receipt(
            json.loads(stage.receipt.read_text()), self.state)["path"])
        return stage, stage_fixture

    def test_consumed_refusal_actual_staging_path_preserves_stop_and_no_supervisor(self):
        projection = self.reconcile()
        stage, stage_fixture = self._staging_fixture()
        with patch.object(a, "WindowsExactTaskController", return_value=self.controller), \
             patch.object(a, "_process_presence", return_value="absent"):
            plan = stage._plan(task_reader=lambda: self.f.task,
                expected_task_sha256=a._payload_sha256(self.f.task))
            self.assertEqual(plan["status"], "runtime_staging_plan_ready")
            result = stage_fixture.stage_runtime(plan, task_reader=lambda: self.f.task,
                runner=stage.git, git_safety_checker=stage._safe_git)
        self.assertTrue(result["success"])
        self.assertFalse(result["core_started"])
        self.assertTrue(self.f.stop.exists())
        self.assertFalse((self.state / "supervisor.json").exists())
        self.assertFalse((self.state / "activation.lock").exists())
        self.assertEqual(json.loads((self.state / "watchdog.json").read_text()), projection)
        self.unchanged()

    def test_staging_revalidates_exact_additive_evidence_after_plan(self):
        self.reconcile()
        stage, stage_fixture = self._staging_fixture()
        with patch.object(a, "WindowsExactTaskController", return_value=self.controller), \
             patch.object(a, "_process_presence", return_value="absent"):
            plan = stage._plan(task_reader=lambda: self.f.task,
                expected_task_sha256=a._payload_sha256(self.f.task))
            before_heads = dict(stage.git.heads)
            path = self.ledger / f"{self.id}-late-refused-activation-packet.json"
            value = json.loads(path.read_text())
            value["provider_started_at"] = (self.refused_at + timedelta(milliseconds=1)).isoformat()
            value["packet_hmac_sha256"] = a._sign_packet(value, self.f.key)
            path.write_text(json.dumps(value))
            with self.assertRaises(Exception):
                stage_fixture.stage_runtime(plan, task_reader=lambda: self.f.task,
                    runner=stage.git, git_safety_checker=stage._safe_git)
            self.assertEqual(stage.git.heads, before_heads)
        self.assertTrue(self.f.stop.exists())
        self.assertFalse((self.state / "supervisor.json").exists())
        self.unchanged()

if __name__=="__main__":unittest.main()
