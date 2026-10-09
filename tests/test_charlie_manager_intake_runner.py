"""Stopped initialization and exact provider-intake boundaries, with fake providers."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from modules.charlie import INTAKE_EXECUTION_MODE, governed_runtime_binding
from modules.charlie import runtime_staging as staging, runtime_activation as activation
from modules.charlie import executive_runtime as executive, mission_store as missions
from modules.charlie import runner_control as control
from scripts import charlie_manager_intake_runner as child
from scripts import charlie_runner_supervisor as supervisor
from scripts import charlie_runner_watchdog as watchdog


def scope(root):
    return dict(policy_id="POLICY-SYNTHETIC", scope_sha256="a"*64,
        environment_path=str(root / ".env"), environment_sha256="b"*64,
        database_host="db.invalid", database_port=5432, database_name="test",
        database_user="test", ca_path=str(root / "ca.pem"), ca_sha256="c"*64)


class StoppedInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name); self.canonical=base/"repo"; (self.canonical/".git").mkdir(parents=True)
        self.assigned=base/".runtime"/"test-mission"; self.assigned.mkdir(parents=True)
        self.state=self.assigned/"state"; self.python=base/"python.exe"; self.python.write_bytes(b"synthetic interpreter")
        self.task=[dict(task_name=staging.TASK_NAME,task_path="\\",state="Disabled",action_count=1,
            execute=str(self.python),arguments="historical",working_directory="historical")]
        self.source="d"*40; self.now=datetime.now(timezone.utc)
        self.git=Mock(return_value=subprocess.CompletedProcess([],0,self.source+"\n",""))
        self.args=dict(canonical_root=self.canonical,assigned_root=self.assigned,state_root=self.state,
            source_ref=self.source,mission_id="OMQ-SYNTHETIC",interpreter=self.python,
            expected_task_sha256=staging._payload_sha256(self.task),task_reader=lambda:deepcopy(self.task),
            runner=self.git,now=self.now)
    def initialize(self):
        plan=staging.plan_runtime_initialization(**self.args)
        result=staging.initialize_runtime_stopped(plan,task_reader=self.args["task_reader"],runner=self.git,now=self.now)
        return plan,result
    def roots(self):
        for name in ("core-runtime-current","core-execution-current"):
            root=self.state/name; root.mkdir()
            (root/".git").write_text("gitdir: "+str(self.canonical/".git"/"worktrees"/name))
        return self.state/"core-runtime-current",self.state/"core-execution-current"
    def test_honest_stopped_shell_and_exact_replay(self):
        plan,result=self.initialize()
        self.assertFalse(result["validation_proven"]); self.assertFalse(result["core_started"])
        self.assertFalse((self.state/"runtime-manifest.json").exists())
        self.assertFalse((self.state/"supervisor.json").exists())
        self.assertFalse((self.state/"watchdog.json").exists())
        before={str(p.relative_to(self.state)):p.read_bytes() for p in self.state.rglob("*") if p.is_file()}
        replay=staging.initialize_runtime_stopped(plan,task_reader=self.args["task_reader"],runner=self.git,now=self.now)
        self.assertTrue(replay["replayed"])
        self.assertEqual(before,{str(p.relative_to(self.state)):p.read_bytes() for p in self.state.rglob("*") if p.is_file()})
        runtime,_=self.roots(); self.assertEqual(governed_runtime_binding(runtime)["predecessor"],"absent")
    def test_initialized_runtime_cannot_override_explicit_test_state(self):
        self.initialize(); runtime, _ = self.roots()
        self.assertEqual(governed_runtime_binding(runtime)["state_root"], str(self.state))
        before = {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob("*") if p.is_file()}
        test_root = self.assigned / "isolated-tests"
        isolated = {"CHARLIE_TEST_ISOLATION": "1", "CHARLIE_TEST_CONTROL_ROOT": str(test_root)}
        with patch.object(control, "governed_state_root", side_effect=AssertionError("production binding consulted")):
            selected = control._runner_directory(runtime, isolated)
        self.assertEqual(selected, test_root / ".charlie_runner")
        with patch.object(control, "HEARTBEAT_PATH", selected / "runner.json"), \
             patch.object(control, "_current_git_commit", return_value=self.source), \
             patch.object(control, "_current_git_branch", return_value="synthetic"), \
             patch.dict(os.environ, {"CHARLIE_SUPERVISOR_GENERATION": ""}):
            control.write_runner_heartbeat({"status": "test"})
        self.assertTrue((selected / "runner.json").is_file())
        self.assertEqual(before, {str(p.relative_to(self.state)): p.read_bytes() for p in self.state.rglob("*") if p.is_file()})
        with self.assertRaisesRegex(RuntimeError, "requires CHARLIE_TEST_CONTROL_ROOT"):
            control._runner_directory(runtime, {"CHARLIE_TEST_ISOLATION": "1"})
        self.assertEqual(control._runner_directory(runtime, {}), self.state)

    def test_task_drift_prevents_all_state_creation(self):
        plan=staging.plan_runtime_initialization(**self.args); self.task[0]["arguments"]="changed"
        with self.assertRaisesRegex(staging.RuntimeStagingError,"preimage_changed"):
            staging.initialize_runtime_stopped(plan,task_reader=self.args["task_reader"],runner=self.git,now=self.now)
        self.assertFalse(self.state.exists())
    def test_expired_plan_does_not_acquire_lane(self):
        plan=staging.plan_runtime_initialization(**self.args)
        with self.assertRaisesRegex(staging.RuntimeStagingError,"expired"):
            staging.initialize_runtime_stopped(plan,now=self.now+timedelta(hours=1))
        self.assertFalse(self.state.exists())
        self.assertFalse((self.assigned/"state-initialization.lock").exists())
    def test_existing_state_and_escape_fail_before_git(self):
        for state in (self.canonical/"state",self.assigned/".."/"escape"):
            with self.subTest(state=state), self.assertRaises(staging.RuntimeStagingError):
                staging.plan_runtime_initialization(**{**self.args,"state_root":state})
        self.state.mkdir()
        with self.assertRaisesRegex(staging.RuntimeStagingError,"absent_state"):
            staging.plan_runtime_initialization(**self.args)
    def test_binding_tamper_and_interpreter_drift_refused(self):
        self.initialize(); runtime,_=self.roots()
        self.python.write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeError,"binding_invalid"): governed_runtime_binding(runtime)
    def test_replaced_validation_key_refuses_runtime_binding(self):
        self.initialize(); runtime,_=self.roots()
        (self.state/"validation-receipt.key").write_bytes(b"replacement"*4)
        with self.assertRaisesRegex(RuntimeError,"binding_invalid"): governed_runtime_binding(runtime)
    def test_partial_initialization_cannot_replay_as_success(self):
        plan=staging.plan_runtime_initialization(**self.args); original=staging._exclusive_json
        def fail(path,value):
            if Path(path).name=="initialization-plan.json": raise OSError("synthetic failure")
            return original(path,value)
        with patch.object(staging,"_exclusive_json",side_effect=fail),self.assertRaises(OSError):
            staging.initialize_runtime_stopped(plan,task_reader=self.args["task_reader"],runner=self.git,now=self.now)
        self.assertTrue((self.state/"supervisor.stop").is_file())
        runtime,_=self.roots()
        with self.assertRaisesRegex(RuntimeError,"binding_invalid"): governed_runtime_binding(runtime)
        with self.assertRaisesRegex(staging.RuntimeStagingError,"partial_initialization"):
            staging.initialize_runtime_stopped(plan,now=self.now)
    def test_initial_staging_requires_real_validation_and_never_invents_supervisor(self):
        self.initialize(); runtime,execution=self.roots()
        self.task[0].update(arguments='"'+str(runtime/"scripts/charlie_runner_task_launcher.py")+'"',working_directory=str(runtime))
        def git(command,cwd=None,**kwargs):
            args=command[1:]
            output=self.source if args==["rev-parse","HEAD"] else ""
            if args==["worktree","list","--porcelain"]: output="worktree "+str(self.canonical)+"\nworktree "+str(runtime)+"\nworktree "+str(execution)
            return subprocess.CompletedProcess(command,0,output,"")
        invalid=self.state/"invalid.json"; invalid.write_text('{"success":true}')
        with patch.object(staging,"inspect_git_checkout_safety",return_value={}),self.assertRaises(staging.RuntimeStagingError):
            staging.stage_initialized_runtime(state_root=self.state,receipt_path=invalid,
                receipt_sha256=staging._sha256(invalid),expected_task_sha256=staging._payload_sha256(self.task),
                task_reader=self.args["task_reader"],runner=git,now=self.now)
        self.assertFalse((self.state/"runtime-manifest.json").exists())
        self.assertFalse((self.state/"supervisor.json").exists())
        self.assertTrue((self.state/"release-staging.lock").exists())

    def stage_fixture(self):
        from tests import test_charlie_runtime_staging as prior
        from modules.charlie.validation_receipt import sign_validation_receipt, record_validation_receipt
        self.initialize(); runtime,execution=self.roots()
        self.task[0].update(arguments='"'+str(runtime/"scripts/charlie_runner_task_launcher.py")+'"',working_directory=str(runtime))
        old=prior.RuntimeStagingTests(methodName="runTest"); old.setUp(); self.addCleanup(old.tearDown)
        receipt=json.loads(old.receipt.read_text()); receipt["source_commit"]=self.source
        for key in ("signature_hmac_sha256","validation_id","issued_at","expires_at","version","issuer"):
            receipt.pop(key,None)
        signed=sign_validation_receipt(receipt,(self.state/"validation-receipt.key").read_bytes(),validation_id="9"*32)
        path=Path(record_validation_receipt(signed,self.state)["path"])
        def git(command,cwd=None,**kwargs):
            args=command[1:]
            output=self.source if args==["rev-parse","HEAD"] or args[:2]==["rev-parse","--verify"] else ""
            if args==["worktree","list","--porcelain"]: output="worktree "+str(self.canonical)+"\nworktree "+str(runtime)+"\nworktree "+str(execution)
            return subprocess.CompletedProcess(command,0,output,"")
        return dict(state_root=self.state,receipt_path=path,receipt_sha256=staging._sha256(path),
            expected_task_sha256=staging._payload_sha256(self.task),task_reader=self.args["task_reader"],runner=git)
    def test_validated_initial_stage_has_truthful_absence_and_can_plan_future_promotion(self):
        args=self.stage_fixture()
        with patch.object(staging,"inspect_git_checkout_safety",return_value={}):
            result=staging.stage_initialized_runtime(**args)
            self.assertEqual(result["predecessor"],"absent");self.assertFalse(result["core_started"])
            self.assertTrue((self.state/"supervisor.stop").exists())
            self.assertFalse((self.state/"supervisor.json").exists())
            # A genuine unused receipt is still required for later promotion.
            with self.assertRaisesRegex(staging.RuntimeStagingError,"replay_rejected"):
                staging.plan_runtime_staging(source_ref=self.source,runtime_root=self.state/"core-runtime-current",
                    execution_root=self.state/"core-execution-current",expected_runtime_head=self.source,
                    expected_execution_head=self.source,expected_manifest_commit=self.source,**args)
    def test_initial_manifest_publication_failure_rolls_back_to_absence_without_reusing_receipt(self):
        args=self.stage_fixture(); original=staging._exclusive_json
        def fail(path,value):
            if Path(path).name.endswith("-result.json"): raise OSError("synthetic result write failure")
            return original(path,value)
        with patch.object(staging,"inspect_git_checkout_safety",return_value={}),patch.object(staging,"_exclusive_json",side_effect=fail),self.assertRaises(OSError):
            staging.stage_initialized_runtime(**args)
        self.assertFalse((self.state/"runtime-manifest.json").exists())
        self.assertTrue((self.state/"supervisor.stop").exists())
        self.assertTrue((self.state/"release-staging.lock").exists())
        self.assertEqual(len(list((self.state/"validation-consumptions").glob("*.json"))),1)
    def test_initial_staging_worktree_limit_blocks_before_receipt_consumption(self):
        args=self.stage_fixture(); run=args["runner"]
        def extra(command,**kwargs):
            result=run(command,**kwargs)
            if command[1:]==["worktree","list","--porcelain"]: result.stdout += "\nworktree extra"
            return result
        with patch.object(staging,"inspect_git_checkout_safety",return_value={}),self.assertRaisesRegex(staging.RuntimeStagingError,"worktree_bound"):
            staging.stage_initialized_runtime(**{**args,"runner":extra})
        self.assertFalse((self.state/"validation-consumptions").exists())


class IntakeBoundaryTests(unittest.TestCase):
    def test_all_present_admissions_are_excluded_from_ordinary_runtime(self):
        for value in (None,False,True,[],"invalid",{}, {"receipt_only":True}):
            with self.subTest(value=value):
                self.assertFalse(missions.mission_runtime_eligible({"metadata":{"manager_dependency_intake":value}}))
        self.assertTrue(missions.mission_runtime_eligible({"metadata":{}}))
    def test_scoped_entry_never_calls_broad_executive(self):
        policy={"policy_id":"POLICY-SYNTHETIC","scope":{"test":"exact"}}
        digest=hashlib.sha256(json.dumps(policy["scope"],sort_keys=True,separators=(",",":")).encode()).hexdigest()
        with patch.object(executive,"load_manager_dependency_policy",return_value=({"policies":[policy]},200)), \
             patch.object(executive,"_load_executive_missions",side_effect=AssertionError("broad queue")), \
             patch.object(executive,"load_executive_context",side_effect=AssertionError("broad context")), \
             patch.object(executive,"build_executive_cycle",side_effect=AssertionError("broad executive")), \
             patch.object(executive,"consume_manager_dependencies",return_value={"status":"manager_dependency_intake_checked","failures":0}) as consume:
            result,status=executive.run_manager_dependency_intake_cycle(policy_id=policy["policy_id"],scope_sha256=digest)
            self.assertEqual(status,200); self.assertFalse(result["mission_pickup_attempted"])
            self.assertEqual(consume.call_args.kwargs["policies"],[policy])
            _,status=executive.run_manager_dependency_intake_cycle(policy_id=policy["policy_id"],scope_sha256="f"*64)
            self.assertEqual(status,409); self.assertEqual(consume.call_count,1)
    def test_global_active_setting_cannot_enter_broad_loop_from_scoped_process(self):
        with patch.dict(os.environ,{"CHARLIE_CORE_EXECUTION_MODE":INTAKE_EXECUTION_MODE,"CHARLIE_EXECUTIVE_MODE":"active"}), \
             patch.object(executive,"_load_executive_missions",side_effect=AssertionError("queue")):
            self.assertEqual(executive.run_executive_cycle()[1],403)
    def test_environment_allowlist_excludes_all_credentials(self):
        actual=activation.intake_process_environment({"PATH":"safe","DATABASE_URL":"secret",
            "OPENAI_API_KEY":"secret","TELEGRAM_BOT_TOKEN":"secret","CHARLIE_CORE_EXECUTION_MODE":INTAKE_EXECUTION_MODE})
        self.assertEqual(set(actual),{"PATH","CHARLIE_CORE_EXECUTION_MODE"})
    def test_scoped_authority_malformed_scope_never_validates(self):
        with tempfile.TemporaryDirectory() as tmp:
            packet={"version":activation.AUTHORITY_VERSION,"issuer":"control_tower_activation_authority_v1",
                "activation_id":"a"*32,"expires_at":(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat(),
                "execution_mode":INTAKE_EXECUTION_MODE,"manager_dependency_intake":scope(Path(tmp))}
            for mutation in ("valid","unknown_key","missing_hash","boolean_port","expired"):
                value=deepcopy(packet)
                if mutation=="unknown_key": value["manager_dependency_intake"]["all_missions"]=True
                if mutation=="missing_hash": value["manager_dependency_intake"].pop("scope_sha256")
                if mutation=="boolean_port": value["manager_dependency_intake"]["database_port"]=True
                if mutation=="expired": value["expires_at"]="2000-01-01T00:00:00+00:00"
                value["signature_hmac_sha256"]=activation._sign_record(value,b"k"*32,"signature_hmac_sha256")
                with self.subTest(mutation=mutation):
                    if mutation=="valid": activation._validate_authority(value,b"k"*32)
                    else:
                        with self.assertRaises(activation.ActivationError): activation._validate_authority(value,b"k"*32)

    def test_tls_requires_explicit_signed_target_password_and_ca(self):
        import psycopg
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); ca=root/"ca.pem"; ca.write_bytes(b"synthetic CA")
            authority={"manager_dependency_intake":scope(root)}
            authority["manager_dependency_intake"]["ca_sha256"]=hashlib.sha256(ca.read_bytes()).hexdigest()
            with patch.object(psycopg,"connect") as connect:
                for url in ("postgresql://test@db.invalid/test", "postgresql://test:pw@wrong.invalid/test", "postgresql://test:pw@db.invalid/test?service=other"):
                    with self.subTest(url=url), self.assertRaises(activation.ActivationError):
                        activation.intake_database_connection(authority,url)
                connect.assert_not_called()
                connection=Mock();connection.pgconn.ssl_in_use=True;connect.return_value=connection
                self.assertIs(activation.intake_database_connection(authority,"postgresql://test:pw@db.invalid/test?sslmode=disable"),connection)
                self.assertEqual(connect.call_args.kwargs["sslmode"],"verify-full")
                self.assertEqual(connect.call_args.kwargs["sslrootcert"],str(ca))
                connection.pgconn.ssl_in_use=False
                with self.assertRaises(activation.ActivationError):
                    activation.intake_database_connection(authority,"postgresql://test:pw@db.invalid/test")
                connection.close.assert_called_once()
    def test_failed_startup_never_opens_intake(self):
        with patch.object(child,"_validate_runner_start",return_value={"success":False}), \
             patch.object(child,"write_runner_heartbeat"), patch.object(child,"run_intake_cycle") as cycle:
            self.assertEqual(child.main(),1); cycle.assert_not_called()
    def test_caller_checks_final_controller_before_environment_or_database(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(child,"SUPERVISOR_STOP_PATH",Path(tmp)/"stop"), \
             patch.object(child,"_read_json",return_value={"status":"operational_authorized","runner_state":"operational_authorized"}), \
             patch.object(child,"_validate_final",return_value={"success":False}),patch.object(child,"load_intake_environment") as env:
            with self.assertRaises(activation.ActivationError): child.run_intake_cycle()
            env.assert_not_called()
    def test_watchdog_never_falls_back_to_general_start_when_scoped_packet_absent(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{"CHARLIE_CORE_EXECUTION_MODE":INTAKE_EXECUTION_MODE}), \
             patch.object(watchdog,"_configure_git_safe_directory"),patch.object(watchdog,"_fast_runner_status",side_effect=AssertionError("queue")):
            starter=Mock(side_effect=AssertionError("ordinary start"))
            result=watchdog.watchdog_tick(state_path=Path(tmp)/"watchdog.json",starter=starter)
            self.assertFalse(result["started"]); starter.assert_not_called()
    def test_supervisor_intake_spawn_excludes_prepare_scrub_recovery_and_credentials(self):
        process=Mock(pid=101);process.wait.return_value=0;popen=Mock(return_value=process)
        with tempfile.TemporaryDirectory() as tmp,patch.object(supervisor,"RUNNER_DIR",Path(tmp)), \
             patch.object(supervisor,"SUPERVISOR_PATH",Path(tmp)/"supervisor.json"), \
             patch.object(supervisor,"RUNNER_HEARTBEAT_PATH",Path(tmp)/"runner.json"), \
             patch.object(supervisor,"STOP_PATH",Path(tmp)/"stop"), \
             patch.object(supervisor,"read_intake_activation",return_value={}), \
             patch.object(supervisor,"redact_tree_in_place",side_effect=AssertionError("scrub")), \
             patch.object(supervisor,"_runner_failure_packet",side_effect=AssertionError("old failure log")), \
             patch.object(supervisor,"_recreate_damaged_runner_worktree",side_effect=AssertionError("repair")), \
             patch.dict(os.environ,{"CHARLIE_CORE_EXECUTION_MODE":INTAKE_EXECUTION_MODE,"DATABASE_URL":"secret","OPENAI_API_KEY":"secret"}):
            result=supervisor.supervise_runner(popen_factory=popen,max_cycles=1,
                prepare_fn=Mock(side_effect=AssertionError("prepare")),
                recovery_fn=Mock(side_effect=AssertionError("recovery")),
                acknowledgement_fn=supervisor._test_acknowledgement,generation="test-generation")
        command=popen.call_args.args[0];env=popen.call_args.kwargs["env"]
        self.assertTrue(command[-1].endswith("charlie_manager_intake_runner.py")); self.assertEqual(len(command),2)
        self.assertNotIn("DATABASE_URL",env);self.assertNotIn("OPENAI_API_KEY",env)
        self.assertEqual(result["restart_count"],0)


class SignedIntakeStartupTests(unittest.TestCase):
    def setUp(self):
        self.fixture = StoppedInitializationTests(methodName="runTest")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        f = self.fixture
        f.initialize(); self.runtime, self.execution = f.roots()
        self.state = f.state
        (self.state / "supervisor.stop").unlink()
        self.key = (self.state / "activation-authority.key").read_bytes()
        self.activation_id = "a" * 32
        self.receipt = self.state / "synthetic-receipt.json"
        self.receipt.write_text('{"synthetic":true}')
        manifest = {"promoted_commit": f.source,
            "initialization_sha256": activation._sha256(self.state / "initialization.json"),
            "validation_receipt_sha256": activation._sha256(self.receipt)}
        (self.state / "runtime-manifest.json").write_text(json.dumps(manifest))
        self.authority = {"version": activation.AUTHORITY_VERSION,
            "issuer": "control_tower_activation_authority_v1", "activation_id": self.activation_id,
            "execution_mode": INTAKE_EXECUTION_MODE,
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
            "manager_dependency_intake": scope(f.canonical),
            "manifest_sha256": activation._sha256(self.state / "runtime-manifest.json"),
            "runtime_revision": f.source, "execution_revision": f.source,
            "receipt_path": str(self.receipt), "receipt_sha256": activation._sha256(self.receipt)}
        self.packet = {"version": activation.ACTIVATION_VERSION, "status": "provider_pending",
            "activation_id": self.activation_id, "authority": self.authority,
            "runtime_root": str(self.runtime), "execution_root": str(self.execution),
            "expected_instance_guid": "11111111-1111-1111-1111-111111111111"}
        self.save_packet()
        self.consumed = {"activation_id": self.activation_id,
            "expected_instance_guid": self.packet["expected_instance_guid"],
            "provider_instance_guid": self.packet["expected_instance_guid"],
            "packet_hmac_sha256": self.packet["packet_hmac_sha256"]}
        self.save_consumed()
    def save_packet(self):
        self.authority["signature_hmac_sha256"] = activation._sign_record(
            self.authority, self.key, "signature_hmac_sha256")
        self.packet["packet_hmac_sha256"] = activation._sign_packet(self.packet, self.key)
        (self.state / "activation-packet.json").write_text(json.dumps(self.packet))
    def save_consumed(self):
        self.consumed["consumed_hmac_sha256"] = activation._sign_record(
            self.consumed, self.key, "consumed_hmac_sha256")
        (self.state / ("activation-consumed-" + self.activation_id + ".json")).write_text(json.dumps(self.consumed))
    def read(self):
        return activation.read_intake_activation(self.state, self.activation_id)
    def test_signed_consumed_packet_and_verified_archive(self):
        self.assertEqual(self.read(), self.authority)
        pending = self.packet["packet_hmac_sha256"]
        self.packet.update(status="provider_started_" + INTAKE_EXECUTION_MODE,
            consumed_packet_hmac_sha256=pending)
        self.save_packet()
        self.assertEqual(self.read(), self.authority)
        ledger = self.state / "activation-ledger"; ledger.mkdir()
        for name in ("activation-packet.json", "activation-consumed-" + self.activation_id + ".json"):
            (self.state / name).rename(ledger / (self.activation_id + "-verified-" + name))
        self.assertEqual(self.read(), self.authority)
    def test_signed_wrong_revision_path_expiry_and_scope_are_rejected(self):
        pristine = deepcopy(self.authority)
        for field, value in (("runtime_revision", "f"*40), ("execution_revision", "e"*40),
                ("expires_at", "2000-01-01T00:00:00+00:00"), ("execution_mode", "ordinary")):
            with self.subTest(field=field):
                self.authority.clear(); self.authority.update(deepcopy(pristine)); self.authority[field] = value
                self.save_packet()
                with self.assertRaises(activation.ActivationError): self.read()
        self.authority.clear(); self.authority.update(pristine)
        self.packet["execution_root"] = str(self.execution.parent / "other")
        self.save_packet()
        with self.assertRaises(activation.ActivationError): self.read()
    def test_missing_or_substituted_consumption_and_closed_activation_refuse(self):
        consumed_path = self.state / ("activation-consumed-" + self.activation_id + ".json")
        consumed_path.unlink()
        with self.assertRaises(activation.ActivationError): self.read()
        self.consumed["provider_instance_guid"] = "different"
        self.save_consumed()
        with self.assertRaises(activation.ActivationError): self.read()
        self.consumed["provider_instance_guid"] = self.packet["expected_instance_guid"]
        self.save_consumed()
        ledger = self.state / "activation-ledger"; ledger.mkdir()
        (ledger / (self.activation_id + "-failure.json")).write_text("{}")
        with self.assertRaisesRegex(activation.ActivationError, "closed"): self.read()
    def test_stop_receipt_and_manifest_drift_refuse_before_configuration(self):
        pristine = self.receipt.read_bytes()
        self.receipt.write_bytes(b"drift")
        with self.assertRaises(activation.ActivationError): self.read()
        self.receipt.write_bytes(pristine)
        manifest = self.state / "runtime-manifest.json"; manifest.write_text("{}")
        with self.assertRaises(activation.ActivationError): self.read()
        (self.state / "supervisor.stop").write_text("stop")
        with self.assertRaisesRegex(activation.ActivationError, "stop"): self.read()
    def test_local_configuration_hash_and_escape_checked_before_activation(self):
        env = self.fixture.canonical / ".env"; env.write_text("DATABASE_URL=synthetic")
        ca = self.fixture.canonical / "ca.pem"; ca.write_text("synthetic")
        selected = self.authority["manager_dependency_intake"]
        selected.update(environment_sha256=activation._sha256(env), ca_sha256=activation._sha256(ca))
        activation._validate_intake_local_binding(self.authority, self.state, self.runtime)
        env.write_text("changed")
        with self.assertRaisesRegex(activation.ActivationError, "configuration_changed"):
            activation._validate_intake_local_binding(self.authority, self.state, self.runtime)
        selected["environment_path"] = str(self.state / ".env")
        with self.assertRaisesRegex(activation.ActivationError, "path_invalid"):
            activation._validate_intake_local_binding(self.authority, self.state, self.runtime)
    def test_exact_child_entry_restores_environment_after_receipt_service(self):
        expected = {"DATABASE_URL": "synthetic", "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": "synthetic-owner"}
        def service(**kwargs):
            self.assertEqual(kwargs["policy_id"], self.authority["manager_dependency_intake"]["policy_id"])
            self.assertEqual(kwargs["scope_sha256"], self.authority["manager_dependency_intake"]["scope_sha256"])
            self.assertEqual(os.environ["DATABASE_URL"], "synthetic")
            self.assertNotIn("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", os.environ)
            return {"status": "manager_dependency_intake_checked"}, 200
        with patch.object(child, "SUPERVISOR_STOP_PATH", self.state / "supervisor.stop"), \
             patch.object(child, "_read_json", return_value={"status":"operational_authorized", "runner_state":"operational_authorized"}), \
             patch.object(child, "_validate_final", return_value={"success":True}), \
             patch.object(child, "read_intake_activation", return_value=self.authority), \
             patch.object(child, "load_intake_environment", return_value=expected), \
             patch.object(executive, "run_manager_dependency_intake_cycle", side_effect=service), \
             patch.dict(os.environ, {"DATABASE_URL":"prior", "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"prior"}):
            self.assertEqual(child.run_intake_cycle()[1], 200)
            self.assertEqual(os.environ["DATABASE_URL"], "prior")
            self.assertEqual(os.environ["OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS"], "prior")


class IntakeHeartbeatReviewTests(unittest.TestCase):
    def outcome(self):
        receipt = {"status": "intake_linked", "finding_received": True, "link_created": True,
            "command_id": "CMD-" + "A"*20, "event_id": "CORE-MISSION-CONTROL-" + "B"*24,
            "manager_link_event_id": "OOM-CORE-INTAKE-" + "C"*32,
            "policy": {"secret": "must-not-persist"}, "owner_user_id": "private-owner"}
        return {"status": "scoped_intake_cycle_complete", "manager_dependency_intake": {
            "status": "manager_dependency_intake_checked", "failures": 0, "results": [receipt]}}
    def test_real_child_heartbeat_keeps_receipt_then_contains_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); heartbeat = root / "runner.json"
            with patch.object(control, "HEARTBEAT_PATH", heartbeat), \
                 patch.object(control, "_current_git_commit", return_value="synthetic"), \
                 patch.object(control, "_current_git_branch", return_value="synthetic"), \
                 patch.object(control, "_pid_alive", return_value=True), \
                 patch.object(child, "SUPERVISOR_STOP_PATH", root / "stop"), \
                 patch.object(child, "_validate_runner_start", return_value={"success": True}), \
                 patch.object(child, "_read_json", return_value={"status":"operational_authorized", "runner_state":"operational_authorized"}), \
                 patch.object(child, "run_intake_cycle", return_value=(self.outcome(),200)) as cycle, \
                 patch.dict(os.environ, {"CHARLIE_CORE_EXECUTION_MODE":INTAKE_EXECUTION_MODE, "CHARLIE_SUPERVISOR_GENERATION":""}):
                self.assertEqual(child.main(max_cycles=1),0)
                written = json.loads(heartbeat.read_text())
                self.assertEqual(written["intake"]["failures"],0)
                self.assertEqual(written["checks"],1)
                self.assertEqual(written["intake"]["results"][0]["command_id"],"CMD-"+"A"*20)
                self.assertNotIn("must-not-persist",heartbeat.read_text())
                self.assertNotIn("private-owner",heartbeat.read_text())
                # Custom heartbeat read uses the injected live PID only, not a host process probe.
                with patch.object(control,"HEARTBEAT_PATH",root/"other.json"):
                    status=control.runner_status(heartbeat,include_git=False)
                self.assertEqual(status["operating_state"],"receipt_only_intake")
                self.assertEqual(status["intake"],written["intake"])
                self.assertIn("Worker pickup and repair are not enabled",status["next_action"])
                cycle.side_effect=RuntimeError("private exception must-not-persist")
                self.assertEqual(child.main(max_cycles=1),1)
                written=json.loads(heartbeat.read_text())
                self.assertEqual(written["intake"]["status"],"intake_cycle_contained")
                self.assertEqual(written["intake"]["error_type"],"RuntimeError")
                self.assertEqual(written["intake"]["results"],[])
                self.assertNotIn("private exception",heartbeat.read_text())
                with patch.object(control,"HEARTBEAT_PATH",root/"other.json"),patch.object(control,"_pid_alive",return_value=False):
                    status=control.runner_status(heartbeat,include_git=False)
                self.assertIn("Receipt-only intake is not running",status["next_action"])
                self.assertNotIn("auto-pick",status["next_action"])
    def test_summary_bounds_and_malformed_fields_never_copy_free_text(self):
        raw={"status": ["secret"], "error_type": {"secret":"value"}, "policies":["secret"],
            "manager_dependency_intake":{"failures":True,"results":[{
                "status":"manager_dependency_intake_refused", "reason":"raw secret exception",
                "command_id":"credential-url", "failure_kind":["secret"],
                "event_id":"CORE-MISSION-CONTROL-"+"B"*24}] * 100}}
        summary=control._intake_heartbeat_summary(raw)
        self.assertEqual(summary["status"],"intake_outcome_unrecognized")
        self.assertIsNone(summary["failures"])
        self.assertEqual(len(summary["results"]),8)
        self.assertTrue(summary["results_truncated"])
        self.assertLess(len(json.dumps(summary)),2200)
        self.assertNotIn("secret",json.dumps(summary))
        self.assertNotIn("credential",json.dumps(summary))
        self.assertEqual(summary,control._intake_heartbeat_summary(summary))
    def test_ordinary_and_observe_telemetry_do_not_adopt_intake_results(self):
        for mode,expected in (("ordinary","waiting_for_queue"),("observe_only","observe_only")):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as tmp, \
                 patch.object(control,"_current_git_commit",return_value="synthetic"), \
                 patch.object(control,"_current_git_branch",return_value="synthetic"), \
                 patch.dict(os.environ,{"CHARLIE_CORE_EXECUTION_MODE":mode,"CHARLIE_SUPERVISOR_GENERATION":""}):
                path=Path(tmp)/"runner.json"
                record=control.write_runner_heartbeat({"status":"watch_started","intake":self.outcome()},path)
                self.assertNotIn("intake",record)
                self.assertEqual(control._runner_operating_state(record,{},True),expected)
