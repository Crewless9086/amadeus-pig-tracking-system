"""Stopped initialization and exact provider-intake boundaries, with fake providers."""
import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from copy import deepcopy
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from modules.charlie import INTAKE_EXECUTION_MODE, governed_runtime_binding
from modules.charlie import runtime_staging as staging, runtime_activation as activation
from modules.charlie import executive_runtime as executive, mission_store as missions
from modules.charlie import runner_control as control
from modules.charlie import process_ownership
from scripts import charlie_manager_intake_runner as child
from scripts import charlie_runner_supervisor as supervisor
from scripts import charlie_runner_watchdog as watchdog


def scope(root):
    return dict(policy_id="POLICY-SYNTHETIC", scope_sha256="a"*64,
        environment_path=str(root / ".env"), environment_sha256="b"*64,
        database_host="db.invalid", database_port=5432, database_name="test",
        database_user="test", ca_path=str(root / "ca.pem"), ca_sha256="c"*64)


def containment_grant(authority):
    return {"capability": activation.INTAKE_CONTAINMENT_CAPABILITY,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        **{key: authority[key] for key in ("activation_id", "execution_mode",
            "runtime_revision", "execution_revision", "expires_at")}}


class InterpreterLookupTests(unittest.TestCase):
    def test_shallow_source_and_filesystem_root_fall_back_without_ancestor_lookup(self):
        anchor = Path(Path.cwd().anchor)
        for module in (control, supervisor):
            for root in (anchor / "source", anchor):
                with self.subTest(module=module.__name__, root=str(root)), \
                     patch.object(module, "governed_runtime_binding", return_value=None), \
                     patch.object(module, "os", SimpleNamespace(name="posix")), \
                     patch.object(Path, "exists", autospec=True, return_value=False) as exists:
                    self.assertEqual(module._python_executable(root), str(Path(module.sys.executable)))
                    self.assertEqual([call.args[0] for call in exists.call_args_list],
                        [root / "venv" / "Scripts" / "python.exe"])

    def test_normal_depth_preserves_local_then_shared_then_current_interpreter(self):
        root = Path(Path.cwd().anchor) / "synthetic" / "nested" / "repo"
        local = root / "venv" / "Scripts" / "python.exe"
        shared = root.parents[1] / "venv" / "Scripts" / "python.exe"
        for module in (control, supervisor):
            for present, expected in (({local, shared}, local), ({shared}, shared),
                                      (set(), Path(module.sys.executable))):
                with self.subTest(module=module.__name__, present=sorted(map(str, present))), \
                     patch.object(module, "governed_runtime_binding", return_value=None), \
                     patch.object(module, "os", SimpleNamespace(name="posix")), \
                     patch.object(Path, "exists", autospec=True, side_effect=lambda path: path in present):
                    self.assertEqual(module._python_executable(root), str(expected))

    def test_governed_and_windows_base_interpreters_keep_precedence(self):
        for module in (control, supervisor):
            with self.subTest(module=module.__name__), \
                 patch.object(module, "governed_runtime_binding", return_value={"interpreter": "bound-python"}), \
                 patch.object(Path, "exists", side_effect=AssertionError("fallback consulted")):
                self.assertEqual(module._python_executable(module.REPO_ROOT), "bound-python")
            with self.subTest(module=module.__name__), \
                 patch.object(module, "governed_runtime_binding", return_value=None), \
                 patch.object(module, "os", SimpleNamespace(name="nt")), \
                 patch.object(module.sys, "_base_executable", "base-python", create=True), \
                 patch.object(Path, "exists", side_effect=AssertionError("fallback consulted")):
                self.assertEqual(module._python_executable(module.REPO_ROOT), str(Path("base-python")))


class StoppedInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        base=Path(self.temp.name); self.canonical=base/"repo"; (self.canonical/".git").mkdir(parents=True)
        self.assigned=base/".runtime"/"test-mission"; self.assigned.mkdir(parents=True)
        self.state=self.assigned/"state"; self.python=base/"pythonw.exe"; self.python.write_bytes(b"synthetic interpreter")
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
                "runtime_revision":"d"*40,"execution_revision":"d"*40,
                "execution_mode":INTAKE_EXECUTION_MODE,"manager_dependency_intake":scope(Path(tmp))}
            packet["process_containment"] = containment_grant(packet)
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
    def test_scoped_cooperative_stop_is_clean_but_unrequested_exit_is_failure(self):
        for code, requested in ((0, True), (0, False), (1, True)):
            with self.subTest(return_code=code, requested=requested), tempfile.TemporaryDirectory() as tmp:
                root=Path(tmp); process=Mock(pid=101)
                def wait():
                    if requested: (root/"stop").write_text("original governed stop")
                    return code
                process.wait.side_effect=wait
                with patch.object(supervisor,"RUNNER_DIR",root), \
                     patch.object(supervisor,"SUPERVISOR_PATH",root/"supervisor.json"), \
                     patch.object(supervisor,"RUNNER_HEARTBEAT_PATH",root/"runner.json"), \
                     patch.object(supervisor,"STOP_PATH",root/"stop"), \
                     patch.object(supervisor,"read_intake_activation",return_value={}), \
                     patch.object(supervisor,"_git_revision",return_value="a"*40), \
                     patch.object(supervisor,"_runner_failure_packet",side_effect=AssertionError("repair")), \
                     patch.dict(os.environ,{"CHARLIE_CORE_EXECUTION_MODE":INTAKE_EXECUTION_MODE}):
                    result=supervisor.supervise_runner(popen_factory=Mock(return_value=process),max_cycles=1,
                        prepare_fn=Mock(side_effect=AssertionError("prepare")),
                        recovery_fn=Mock(side_effect=AssertionError("recovery")),
                        acknowledgement_fn=supervisor._test_acknowledgement,generation="test-generation")
                stored=json.loads((root/"supervisor.json").read_text())
                if code==0 and requested:
                    self.assertEqual(result["stop_reason"],"cooperative_governed_stop")
                    self.assertNotIn("failure_status",stored)
                else:
                    self.assertEqual(stored["failure_status"],"intake_child_exited")
                self.assertEqual(result["restart_count"],0)

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
             patch.dict(os.environ,{"CHARLIE_CORE_EXECUTION_MODE":INTAKE_EXECUTION_MODE,
                process_ownership.TERMINATION_ENABLE_ENV:process_ownership.TERMINATION_ENABLE_VALUE,
                "DATABASE_URL":"secret","OPENAI_API_KEY":"secret"}):
            result=supervisor.supervise_runner(popen_factory=popen,max_cycles=1,
                prepare_fn=Mock(side_effect=AssertionError("prepare")),
                recovery_fn=Mock(side_effect=AssertionError("recovery")),
                acknowledgement_fn=supervisor._test_acknowledgement,generation="test-generation")
        command=popen.call_args.args[0];env=popen.call_args.kwargs["env"]
        self.assertTrue(command[-1].endswith("charlie_manager_intake_runner.py")); self.assertEqual(len(command),2)
        self.assertNotIn("DATABASE_URL",env);self.assertNotIn("OPENAI_API_KEY",env)
        self.assertEqual(env[process_ownership.TERMINATION_ENABLE_ENV],
                         process_ownership.TERMINATION_ENABLE_VALUE)
        self.assertEqual(result["restart_count"],0)

    def test_intake_supervisor_main_keeps_inherited_grant_without_loading_dotenv(self):
        lock=Mock();lock.acquire.return_value=(True,None)
        def supervise(**kwargs):
            self.assertEqual(os.environ[process_ownership.TERMINATION_ENABLE_ENV],
                             process_ownership.TERMINATION_ENABLE_VALUE)
            self.assertIsNone(kwargs["notifier"])
            return {"status":"supervisor_stopped"}
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{
                "CHARLIE_CORE_EXECUTION_MODE":INTAKE_EXECUTION_MODE,
                process_ownership.TERMINATION_ENABLE_ENV:process_ownership.TERMINATION_ENABLE_VALUE}), \
             patch.object(supervisor,"STOP_PATH",Path(tmp)/"absent-stop"), \
             patch.object(supervisor,"SupervisorInstanceLock",return_value=lock), \
             patch.object(supervisor,"load_dotenv",side_effect=AssertionError("ambient configuration")), \
             patch.object(supervisor,"supervise_runner",side_effect=supervise):
            self.assertEqual(supervisor.main()["status"],"supervisor_stopped")
        lock.release.assert_called_once()


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
        self.authority["process_containment"] = containment_grant(self.authority)
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


class IntakeContainmentGrantTests(unittest.TestCase):
    """Real signed provider consumption and starter; only OS boundaries are fake."""

    def setUp(self):
        self.fixture = SignedIntakeStartupTests(methodName="runTest")
        self.fixture.setUp(); self.addCleanup(self.fixture.doCleanups)
        f = self.fixture; self.state = f.state; self.authority = f.authority
        self.activation_id = f.activation_id; self.key = f.key
        (self.state / ("activation-consumed-" + f.activation_id + ".json")).unlink()
        (self.state / "activation-packet.json").unlink()
        self.stop = self.state / "supervisor.stop"; self.stop.write_text("synthetic original stop")
        canonical = f.fixture.canonical
        environment = canonical / ".env"; environment.write_text("DATABASE_URL=synthetic-not-used\n")
        ca = canonical / "ca.pem"; ca.write_text("synthetic public CA")
        self.authority["manager_dependency_intake"].update(
            environment_sha256=activation._sha256(environment), ca_sha256=activation._sha256(ca))
        self.task = deepcopy(f.fixture.task)
        self.task[0].update(arguments='"'+str(f.runtime/"scripts/charlie_runner_task_launcher.py")+'"',
                            working_directory=str(f.runtime))
        self.authority.update(stop_marker_sha256=activation._sha256(self.stop),
                              task_action_sha256=activation._task_action_sha256(self.task))
        self.authority_path = canonical / "synthetic-activation.json"
        self.write_authority()
        self.controller = __import__("tests.test_charlie_runtime_activation", fromlist=["Controller"]).Controller()
        self.env = self.enter(patch.dict(os.environ, {}, clear=False))
        os.environ.pop(process_ownership.TERMINATION_ENABLE_ENV, None)
        os.environ.pop("CHARLIE_ACTIVATION_ID", None)

    def enter(self, context):
        result = context.__enter__(); self.addCleanup(context.__exit__, None, None, None)
        return result

    def write_authority(self):
        self.authority["signature_hmac_sha256"] = activation._sign_record(
            self.authority, self.key, "signature_hmac_sha256")
        self.authority_path.write_text(json.dumps(self.authority))

    def git(self, command, **_):
        return subprocess.CompletedProcess(command, 0,
            self.fixture.fixture.source if command[-2:] == ["rev-parse", "HEAD"] else "", "")

    def prepare(self):
        plan = activation.plan_activation(authority_path=self.authority_path,
            authority_sha256=activation._sha256(self.authority_path), state_root=self.state,
            runtime_root=self.fixture.runtime, execution_root=self.fixture.execution,
            task_reader=lambda:self.task, git_runner=self.git)
        return activation.prepare_activation(plan, task_controller=self.controller,
            task_reader=lambda:self.task, git_runner=self.git)

    def provider(self, _pid):
        return {"inspection_complete":True,"pid":10,"parent_pid":20,
            "executable_path":self.task[0]["execute"],
            "command_line":f'"{self.task[0]["execute"]}" {self.task[0]["arguments"]}',
            "ancestry":[{"pid":20,"executable_path":"svchost.exe",
                "provider_identity_verified":True,
                "instance_guid":"11111111-1111-1111-1111-111111111111",
                "action_execute":self.task[0]["execute"],
                "action_arguments":self.task[0]["arguments"],
                "action_working_directory":self.task[0]["working_directory"]}]}

    def consume(self, starter, **kwargs):
        return activation.consume_provider_activation(state_root=self.state, starter=starter,
            task_controller=self.controller, task_reader=lambda:self.task,
            provider_inspector=self.provider, git_runner=self.git, **kwargs)

    def starter_context(self, *, raises=False, acknowledge=True):
        from tests.test_charlie_runner_control import successful_bootstrap_observation
        stack = ExitStack(); self.addCleanup(stack.close)
        for name,value in {"REPO_ROOT":self.fixture.runtime,"RUNNER_DIR":self.state,
                "LOG_PATH":self.state/"runner.log","SUPERVISOR_PATH":self.state/"supervisor.json",
                "SUPERVISOR_STOP_PATH":self.stop,"HEARTBEAT_PATH":self.state/"runner.json"}.items():
            stack.enter_context(patch.object(control,name,value))
        stack.enter_context(patch.object(control,"_pid_alive",return_value=False))
        stack.enter_context(patch.object(control,"_current_git_commit",return_value=self.fixture.fixture.source))
        # Keep process-wide test termination isolation enabled. Exercise the real
        # production predicate on a copied environment; never enable real killing.
        def enabled():
            self.assertEqual(os.environ.get("CHARLIE_TEST_ISOLATION"),"1")
            values={k:v for k,v in os.environ.items() if k!="CHARLIE_TEST_ISOLATION"}
            return process_ownership.process_termination_enabled(values)
        stack.enter_context(patch.object(control,"process_termination_enabled",side_effect=enabled))
        popen=stack.enter_context(patch.object(control.subprocess,"Popen",
            side_effect=OSError("synthetic spawn refusal") if raises else None,
            return_value=Mock(pid=700001)))
        stack.enter_context(patch.object(control,"observe_process_tree",side_effect=successful_bootstrap_observation))
        stack.enter_context(patch.object(control,"_wait_for_supervisor_ack",return_value={
            "success":acknowledge,"reason":"synthetic handshake result"}))
        stack.enter_context(patch.object(control,"stop_runner",return_value=({"success":True},200)))
        def contain(*_):
            self.assertTrue(enabled())
            return {"success":True,"reason":"synthetic exact-owned-tree stop"}
        stack.enter_context(patch.object(control,"_contain_spawned_process",side_effect=contain))
        def start(**kwargs):
            return control.start_runner(status_override={"active":False,"orphan_processes":[]},**kwargs)
        return start,popen

    def successful_start(self, prior=None):
        if prior is not None: os.environ[process_ownership.TERMINATION_ENABLE_ENV]=prior
        os.environ["CHARLIE_ACTIVATION_ID"]="prior-parent-identity"
        self.prepare(); starter,popen=self.starter_context()
        result=self.consume(starter)
        self.assertEqual(result["status"],"provider_started_"+INTAKE_EXECUTION_MODE)
        self.assertEqual(result["start_result"]["status"],"runner_started")
        child_env=popen.call_args.kwargs["env"]
        self.assertEqual(child_env[process_ownership.TERMINATION_ENABLE_ENV],process_ownership.TERMINATION_ENABLE_VALUE)
        self.assertEqual(child_env["CHARLIE_ACTIVATION_ID"],self.activation_id)
        self.assertEqual(child_env["CHARLIE_CORE_EXECUTION_MODE"],INTAKE_EXECUTION_MODE)
        self.assertNotIn("DATABASE_URL",child_env)
        self.assertEqual(os.environ.get(process_ownership.TERMINATION_ENABLE_ENV),prior)
        self.assertEqual(os.environ["CHARLIE_ACTIVATION_ID"],"prior-parent-identity")
        with self.assertRaises(activation.ActivationError):self.consume(starter)
        self.assertEqual(popen.call_count,1)

    def test_real_starter_receives_explicit_grant_with_host_sentinel_absent(self):
        self.successful_start()

    def test_parent_disabled_value_is_restored(self):
        self.successful_start("disabled")

    def test_parent_enabled_value_is_restored(self):
        self.successful_start(process_ownership.TERMINATION_ENABLE_VALUE)

    def test_spawn_exception_restores_environment_before_recovery(self):
        self.prepare(); starter,popen=self.starter_context(raises=True)
        original=activation.recover_activation
        def recover(**kwargs):
            self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)
            self.assertNotIn("CHARLIE_ACTIVATION_ID",os.environ)
            return original(**kwargs)
        with patch.object(activation,"recover_activation",side_effect=recover), self.assertRaisesRegex(
                activation.ActivationError,"provider_start_failed"):
            self.consume(starter)
        self.assertEqual(popen.call_count,1);self.assertTrue(self.stop.exists())
        self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)

    def test_failed_handshake_has_grant_for_existing_exact_containment_then_restores(self):
        self.prepare(); starter,popen=self.starter_context(acknowledge=False)
        # The starter writes a fresh stop on refusal. Existing recovery refuses
        # to overwrite that changed marker with the older signed stop preimage.
        with self.assertRaisesRegex(activation.ActivationError,"activation_recovery_incomplete"):
            self.consume(starter)
        self.assertEqual(popen.call_count,1)
        self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)

    def test_missing_unknown_substituted_or_bad_time_grants_fail_before_prepare(self):
        pristine=deepcopy(self.authority)
        changes={"missing":None,"unknown_capability":{"capability":"all_processes"},
            "extra":{"broad_kill":True},"identity":{"activation_id":"b"*32},
            "mode":{"execution_mode":"ordinary"},"source":{"runtime_revision":"e"*40},
            "malformed_source":{"runtime_revision":"unknown"},
            "expiry":{"expires_at":"2000-01-01T00:00:00+00:00"},
            "naive":{"issued_at":"2026-01-01T00:00:00"},
            "future":{"issued_at":(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()},
            "too_long":{"issued_at":(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}}
        for name,change in changes.items():
            with self.subTest(case=name):
                self.authority=deepcopy(pristine)
                if change is None:self.authority.pop("process_containment")
                else:self.authority["process_containment"].update(change)
                self.write_authority()
                with self.assertRaises(activation.ActivationError):self.prepare()
                self.assertFalse((self.state/"activation.lock").exists())
                self.assertTrue(self.stop.exists())
                self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)

    def test_unsigned_or_wrong_mode_authority_cannot_project_grant(self):
        pristine=deepcopy(self.authority)
        for mode in ("observe_only","ordinary","manager_dependency_intake_only"):
            with self.subTest(mode=mode):
                self.authority=deepcopy(pristine);self.authority["execution_mode"]=mode
                self.write_authority()
                if mode==INTAKE_EXECUTION_MODE:
                    self.authority["process_containment"]["issued_at"]="2000-01-01T00:00:00+00:00"
                    self.authority_path.write_text(json.dumps(self.authority))
                with self.assertRaises(activation.ActivationError):self.prepare()
                self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)

    def test_invalid_provider_never_calls_starter_or_projects_grant(self):
        self.prepare();starter=Mock(side_effect=AssertionError("starter"))
        self.provider=lambda _:{"inspection_complete":False}
        with self.assertRaises(activation.ActivationError):self.consume(starter)
        starter.assert_not_called();self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)

    def test_observe_only_authority_does_not_gain_new_containment_permission(self):
        self.authority["execution_mode"]="observe_only"
        self.authority.pop("process_containment");self.write_authority();self.prepare()
        def start(**kwargs):
            self.assertEqual(kwargs["execution_mode"],"observe_only")
            self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)
            return {"status":"synthetic observe-only result"},200
        self.assertEqual(self.consume(start)["status"],"provider_started_observe_only")
        self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)

    def test_expiry_during_provider_validation_refuses_at_starter_boundary(self):
        self.prepare();starter=Mock(side_effect=AssertionError("starter"))
        real=activation._validate_intake_containment;calls=[]
        def elapsed(authority,**kwargs):
            calls.append(True)
            if len(calls)==2:kwargs["now"]=datetime.fromisoformat(authority["expires_at"])
            return real(authority,**kwargs)
        with patch.object(activation,"_validate_intake_containment",side_effect=elapsed),self.assertRaises(
                activation.ActivationError):self.consume(starter)
        starter.assert_not_called();self.assertNotIn(process_ownership.TERMINATION_ENABLE_ENV,os.environ)


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
