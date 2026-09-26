"""Synthetic maintainer qualification. No fixture represents actual owner approval."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import base64
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from scripts import reconcile_oom_desktop_candidate as adapter
from modules.charlie import mission_store as store
from modules.charlie.mission_control import build_mission_control_event
from modules.charlie.mission_admission import canonical_candidate_diff
from scripts import charlie_mission_admission_guard as guard
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

NOW = datetime.now(timezone.utc)
OWNER = "owner:synthetic-test-owner"
PRINCIPAL = "codex_desktop:" + adapter.TASK_ID
PREDECESSOR_PATHS = ['.github/workflows/oom-sakkie-audit-rails.yml', 'docs/09-vault-brain/02-agents/farm/OOM_SAKKIE.md', 'modules/beacon/post_composer.py', 'modules/charlie/private_executive.py', 'modules/charlie/private_media.py', 'modules/charlie/private_planner.py', 'modules/charlie/private_runtime.py', 'modules/charlie/private_voice.py', 'modules/oom_sakkie/daily_farm_manager.py', 'modules/oom_sakkie/family_message_lifecycle.py', 'modules/oom_sakkie/farm_manager_loop.py', 'modules/oom_sakkie/farm_manager_runtime.py', 'modules/oom_sakkie/herdmaster_daily_manager_adapter.py', 'modules/oom_sakkie/learning_llm.py', 'modules/oom_sakkie/ledger_agent.py', 'modules/oom_sakkie/llm_answer.py', 'modules/oom_sakkie/llm_router.py', 'modules/oom_sakkie/model_budget.py', 'modules/oom_sakkie/morning_runtime.py', 'modules/oom_sakkie/rootline_daily_presentation.py', 'modules/oom_sakkie/semantic_front_door.py', 'modules/oom_sakkie/sentinel_single_shot_runner.py', 'modules/oom_sakkie/service.py', 'modules/oom_sakkie/telegram_direct.py', 'modules/oom_sakkie/telegram_gateway.py', 'modules/oom_sakkie/telegram_voice.py', 'modules/oom_sakkie/voice_stt.py', 'modules/sales/sam_live_stock_media.py', 'modules/sales/sam_live_stock_runtime.py', 'modules/sales/sam_meat_runtime.py', 'static/assets/agents/oom-sakkie/agent.md', 'tests/farm_model_test_support.py', 'tests/test_beacon_post_composer.py', 'tests/test_charlie_private_executive.py', 'tests/test_charlie_private_media.py', 'tests/test_charlie_private_voice.py', 'tests/test_farm_openai_budget.py', 'tests/test_oom_sakkie_conversation_followup.py', 'tests/test_oom_sakkie_daily_farm_manager.py', 'tests/test_oom_sakkie_daily_farm_manager_postgres.py', 'tests/test_oom_sakkie_herd_morning_language.py', 'tests/test_oom_sakkie_irrigation_dialogue.py', 'tests/test_oom_sakkie_irrigation_dialogue_postgres.py', 'tests/test_oom_sakkie_model_budget_denials.py', 'tests/test_oom_sakkie_morning_runtime.py', 'tests/test_oom_sakkie_plan_dialogue_postgres.py', 'tests/test_oom_sakkie_rootline_daily_presentation.py', 'tests/test_oom_sakkie_semantic_front_door.py', 'tests/test_oom_sakkie_service.py', 'tests/test_sam_live_stock_runtime.py', 'tests/test_sam_meat_runtime.py', 'tests/test_telegram_voice.py', 'tests/test_telegram_voice_ingress_postgres.py']
PRESERVED_PREVIEW_EFFECTS = {'automatic_once_per_claim_never_attempted_retained_preview_renewal',
    'current_recipient_authorized_protected_confirmation_delivery',
    'verified_same_case_mortality_completion_projection'}
# Synthetic candidate identity permits qualification while production pins remain
# visibly pending. These values never represent an actual PR or owner approval.
SYNTHETIC_PINS = {"CANDIDATE_PR": 9991, "HEAD": "b" * 40, "APPROVED_RUNTIME_HEAD": "b" * 40,
    "PATHS": ["scripts/oom_sakkie_morning_scheduler.py", "tests/test_oom_sakkie_morning_scheduler.py"]}


def use_synthetic_candidate(test):
    pending = {key: deepcopy(value) for key, value in SYNTHETIC_PINS.items()
               if getattr(adapter, key) is None or getattr(adapter, key) == []}
    if not pending:
        return  # Final qualification exercises the real frozen pins.
    pins = patch.multiple(adapter, **pending)
    pins.start()
    test.addCleanup(pins.stop)


def fixtures():
    correction = build_mission_control_event(adapter.MISSION_ID, {
        "event_type": "owner_correction_recorded", "summary": "Synthetic prior fixture only.",
        "corrects_event_id": "synthetic-predecessor", "idempotency_key": "synthetic-old-correction"},
        recorded_by=OWNER, now=NOW - timedelta(hours=2))
    prior_contract = {"generation": "synthetic-old-generation", "base_sha": adapter.PREDECESSOR_BASE,
        "branch": adapter.PREDECESSOR_BRANCH, "allowed_files": PREDECESSOR_PATHS, "forbidden_files": ["*"],
        "allowed_effects": sorted(adapter.REMOVED_EFFECTS | PRESERVED_PREVIEW_EFFECTS | {"repository_candidate_validation", "merge", "existing_web_application_release"}),
        "forbidden_effects": ["cron_deploy", "farm_write", "hardware_command", "database_migration", "service_configuration_change"],
        "required_tests": sorted(adapter.REQUIRED_TESTS), "operational_acceptance": ["old fixture only"]}
    prior_receipt = {"status": "valid", "receipt_id": "MAR-" + "A" * 64, "content_sha256": "a" * 64,
        "mission_id": adapter.MISSION_ID, "root_mission_id": adapter.PARENT_ID,
        "generation": prior_contract["generation"], "base_sha": adapter.PREDECESSOR_BASE, "head_sha": adapter.PREDECESSOR_HEAD,
        "authority_key_sha256": "c" * 64, "latest_correction_digest": "d" * 64,
        "collision_snapshot_sha256": "e" * 64, "signed_receipt": {"synthetic_immutable": True}}
    metadata = {"mission_family": {"root_mission_id": adapter.PARENT_ID,
        "parent_mission_id": adapter.PARENT_ID, "generation": prior_contract["generation"], "retained_context": "retain"},
        "review_packet": {"pr_number": adapter.PREDECESSOR_PR, "candidate_revision": adapter.PREDECESSOR_HEAD, "branch_name": adapter.PREDECESSOR_BRANCH},
        "mission_admission_contract": prior_contract, "mission_admission": prior_receipt,
        "external_supervisor": {"principal": "historical-supervisor", "transport": "historical"},
        "unrelated": {"delivery_history": ["retain"]}}
    def row(mid, md):
        return {"mission_id": mid, "status": "in_progress", "source": "historical",
            "approval_level": "LEVEL 0", "title": "Synthetic fixture", "raw_text": "Synthetic test only.",
            "metadata_json": md, "updated_at": (NOW-timedelta(hours=2)).isoformat()}
    child = row(adapter.MISSION_ID, metadata)
    parent = row(adapter.PARENT_ID, {"review_packet": {"pr_number": 1334},
        "mission_family": {"root_mission_id": adapter.PARENT_ID, "generation": "synthetic-parent"},
        "mission_admission": {"status": "valid", "receipt_id": "parent-preserved"}})
    return child, parent, correction


def arguments(child=None, parent=None, correction=None):
    default_child, default_parent, default_correction = fixtures()
    child, parent, correction = child or default_child, parent or default_parent, correction or default_correction
    candidate = {"pr_number": adapter.CANDIDATE_PR, "branch": adapter.BRANCH, "base_sha": adapter.BASE,
        "head_sha": adapter.HEAD, "tree_sha": "f" * 40, "changed_files": adapter.PATHS,
        "diff_sha256": canonical_candidate_diff(adapter.PATHS, b"synthetic candidate diff")}
    prior_contract = child["metadata_json"]["mission_admission_contract"]
    manifest = {"version": adapter.VERSION, "mission_id": adapter.MISSION_ID, "parent_mission_id": adapter.PARENT_ID,
        "candidate": candidate, "generation": "synthetic-new-generation", "idempotency_key": "synthetic-conversation-followup-rebind",
        "desktop": {"task_id": adapter.TASK_ID, "principal": PRINCIPAL, "transport": "codex_desktop"},
        "expected_child_record": child, "expected_child_sha256": adapter.digest(adapter.canonical(child)),
        "expected_parent_record": parent, "expected_parent_sha256": adapter.digest(adapter.canonical(parent)),
        "expected_correction": {"event_id": correction["event_id"], "metadata": correction, "recorded_by": correction["recorded_by"]},
        "contract": {**prior_contract, "generation": "synthetic-new-generation", "branch": adapter.BRANCH,
            "base_sha": adapter.BASE, "allowed_files": adapter.PATHS,
            "allowed_effects": sorted(set(prior_contract["allowed_effects"]) - adapter.REMOVED_EFFECTS | adapter.ADDED_EFFECTS),
            "forbidden_effects": sorted(set(prior_contract["forbidden_effects"]) - adapter.REMOVED_FORBIDDEN_EFFECTS | adapter.ADDED_FORBIDDEN_EFFECTS),
            "operational_acceptance": sorted(adapter.REQUIRED_ACCEPTANCE)},
        "implementation": {"base_revision": adapter.BASE, "adapter_sha256": "0" * 64,
            "helper_files": {p: "1" * 64 for p in adapter.HELPERS}}, "expires_at": (NOW+timedelta(hours=1)).isoformat()}
    source = {"kind": "current_conversation_transcript", "task_id": adapter.TASK_ID,
        "request_text": "SYNTHETIC qualification proposal, not a real request.",
        "answer_text": "SYNTHETIC approval fixture only.", "observed_at": (NOW-timedelta(minutes=1)).isoformat(),
        "source_message_id": None}
    source["transcript_sha256"] = adapter.digest(adapter.canonical({k: source[k] for k in ("task_id", "request_text", "answer_text")}))
    approval = {"version": adapter.VERSION, "decision": adapter.DECISION, "approval_id": "synthetic-approval",
        "manifest_sha256": "", "owner_principal": OWNER, "desktop_task_id": adapter.TASK_ID, "source": source,
        "evidence_ref": "synthetic:test", "instruction_text": "Synthetic owner fixture for exact reconciliation only.",
        "issued_at": NOW.isoformat(), "expires_at": manifest["expires_at"]}
    return encode(manifest, approval)


def encode(manifest, approval):
    raw = adapter.canonical(manifest); approval = deepcopy(approval)
    approval["manifest_sha256"] = adapter.digest(raw); auth = adapter.canonical(approval)
    return {"manifest_bytes": raw, "approval_bytes": auth, "expected_manifest_sha256": adapter.digest(raw),
            "expected_approval_sha256": adapter.digest(auth)}


def apply(args, connect):
    with patch.object(adapter, "verify_source_and_candidate"):
        return adapter.reconcile_candidate(**args, authenticated_owner_principal=OWNER,
            authenticated_desktop_principal=PRINCIPAL, dry_run=False, connect_factory=connect)


class MemoryDB:
    autocommit = False
    def __init__(self):
        child, parent, correction = fixtures()
        self.rows = {adapter.MISSION_ID: child, adapter.PARENT_ID: parent}
        self.events = {correction["event_id"]: (correction, OWNER, "owner_correction_recorded")}
        self.ops = {}; self.commits = self.rollbacks = 0; self.fail = ""
    def __enter__(self):
        self.before = deepcopy((self.rows, self.events, self.ops)); return self
    def __exit__(self, kind, *_):
        if kind:
            self.rows, self.events, self.ops = self.before; self.rollbacks += 1
        else: self.commits += 1
        return False
    def cursor(self): return MemoryCursor(self)


class MemoryCursor:
    def __init__(self, db): self.db, self.results = db, []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, sql, params=None):
        q = " ".join(sql.split()); db = self.db; self.results = []
        if q.startswith("set local "): return
        if q.startswith("select to_jsonb(m)"):
            row = deepcopy(db.rows[params[0]])
            if db.fail == "readback" and any(e[2] == "workflow_updated" for e in db.events.values()):
                row["title"] = "corrupted readback"
            self.results = [(row,)]
        elif q.startswith("select event_id,metadata_json,recorded_by") or q.startswith("select event_id,coalesce(metadata_json"):
            rows = [(k, v[0], v[1]) for k, v in db.events.items() if v[2] == "owner_correction_recorded"]
            self.results = sorted(rows, key=lambda r: (r[1]["recorded_at"],r[0]), reverse=True)[:1]
        elif q.startswith("select metadata_json,recorded_by,event_type"):
            if params[1] in db.events: self.results = [deepcopy(db.events[params[1]])]
        elif q.startswith("select status,coalesce(metadata_json"):
            row=db.rows[params["mission_id"]]
            self.results=[(row["status"],deepcopy(row["metadata_json"]),row["updated_at"])]
        elif q.startswith("select mission_id,status,coalesce(metadata_json"):
            self.results=[(key,row["status"],deepcopy(row["metadata_json"]),row["updated_at"]) for key,row in db.rows.items()]
        elif q.startswith("select coalesce(metadata_json"):
            self.results = [(deepcopy(db.rows[params["mission_id"]]["metadata_json"]),)]
        elif q.startswith("insert into public.charlie_mission_events"):
            if isinstance(params, dict):
                if db.fail == "correction": raise RuntimeError("injected correction failure")
                eid = params["event_id"]
                if eid not in db.events:
                    db.events[eid] = (json.loads(params["metadata"]), params["principal"], "owner_correction_recorded")
                    if db.fail == "correction_readback":
                        db.events[eid][0]["summary"] = "altered correction"
                    self.results = [(eid,)]
            else:
                if db.fail == "history": raise RuntimeError("injected history failure")
                db.events[params[0]] = (json.loads(params[4]), params[3], "workflow_updated")
        elif q.startswith("insert into public.operational_events"):
            db.ops[params["idempotency_key"]] = deepcopy(params); self.results = [(params["event_id"],)]
        elif q.startswith("update public.charlie_missions"):
            if isinstance(params, dict):
                db.rows[params["mission_id"]]["metadata_json"] = json.loads(params["metadata"])
            else:
                if db.fail == "binding": raise RuntimeError("injected binding failure")
                if db.rows[params[1]] == json.loads(params[2]):
                    db.rows[params[1]]["metadata_json"] = json.loads(params[0]); self.results = [(params[1],)]
            db.rows[adapter.MISSION_ID]["updated_at"] = datetime.now(timezone.utc).isoformat()
        else: raise AssertionError(q)
    def fetchone(self): return deepcopy(self.results[0]) if self.results else None
    def fetchall(self): return deepcopy(self.results)


def read_records(connect):
    with connect("") as connection,connection.cursor() as cursor:
        return {mid:adapter._read_record(cursor,mid) for mid in (adapter.MISSION_ID,adapter.PARENT_ID)}


def mission(connect):
    row=read_records(connect)[adapter.MISSION_ID]
    return {**row,"metadata":row["metadata_json"]}


def authority(connect):
    return store.read_current_mission_admission_authority(adapter.MISSION_ID,connect_factory=connect)


def callback(test,connect,receipt,pr_number,*,stale_mission=None,stale_authority=None):
    from flask import Flask
    from modules.charlie import routes
    key=Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"synthetic-oom-key").digest())
    public=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
    envelope={"version":"mission_admission_ci_envelope_v1","receipt":receipt,
        "signature_ed25519":base64.b64encode(key.sign(guard.canonical_json(receipt))).decode()}
    app=Flask(__name__);app.register_blueprint(routes.charlie_bp)
    with patch.object(guard,"EXTERNAL_ADMISSION_PUBLIC_KEY_B64",public), \
         patch.object(routes,"get_mission",return_value=({"mission":stale_mission or mission(connect)},200)), \
         patch.object(routes,"read_current_mission_admission_authority",return_value=(stale_authority or authority(connect)[0],200)), \
         patch.object(routes,"append_mission_admission_event",side_effect=lambda mid,admission,**kwargs:
            store.append_mission_admission_event(mid,admission,connect_factory=connect,**kwargs)), \
         patch.object(routes,"invalidate_external_candidate_admission") as invalidator, \
         patch.object(routes,"bind_external_supervisor_candidate") as hermes:
        response=app.test_client().post(f"/charlie/hermes/missions/{adapter.MISSION_ID}/protected-admission",
            json={"envelope":envelope,"pr_number":pr_number})
    invalidator.assert_not_called();hermes.assert_not_called()
    return response


def issue_candidate(test,connect,candidate):
    seed=hashlib.sha256(b"synthetic-oom-key").digest()
    key=Ed25519PrivateKey.from_private_bytes(seed)
    public=base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()
    pull={"state":"open","merged_at":None,"body":"Synthetic PR fixture.",
        "base":{"ref":"main","sha":candidate["base_sha"]},
        "head":{"ref":candidate["branch"],"sha":candidate["head_sha"]}}
    def github(_number,_token,*,body=None):
        if body is not None:pull["body"]=body
        return deepcopy(pull)
    class Response:
        status=201
        def __enter__(self):return self
        def __exit__(self,*_):return False
    def post(request,**_kwargs):
        data=json.loads(request.data)
        result=callback(test,connect,data["envelope"]["receipt"],data["pr_number"])
        test.assertLess(result.status_code,400,result.json)
        return Response()
    output=io.StringIO()
    with patch.object(guard,"_protected_database_url",return_value="synthetic-readonly"), \
         patch.object(guard,"_github_pull_request",side_effect=github), \
         patch.object(guard,"_repository_identity",return_value="Crewless9086/amadeus-pig-tracking-system"), \
         patch.object(guard,"subprocess"),patch.object(guard,"_commit",side_effect=lambda sha:sha), \
         patch.object(guard,"_changed_files",return_value=candidate["changed_files"]), \
         patch.object(guard,"_git_bytes",side_effect=lambda *args:b"g\n" if args[0]=="show" else b"synthetic candidate diff"), \
         patch.object(guard,"_git_text",return_value=candidate["head_sha"]), \
         patch.object(guard,"_governance_read_identities",return_value=[{"path":"docs/governance.md",
            "git_blob":candidate["head_sha"],"filesystem_sha256":hashlib.sha256(b"g\n").hexdigest(),
            "byte_count":2,"physical_line_count":1,"complete_byte_read":True}]), \
         patch.object(guard,"list_missions",side_effect=lambda **_:({"success":True,"missions":[mission(connect)]},200)), \
         patch.object(guard,"get_mission",side_effect=lambda *a,**_:({"success":True,"mission":mission(connect)},200)), \
         patch.object(guard,"read_current_mission_admission_authority",side_effect=lambda *a,**_:authority(connect)), \
         patch.object(guard.url_request,"urlopen",side_effect=post), \
         patch.object(guard,"EXTERNAL_ADMISSION_PUBLIC_KEY_B64",public),contextlib.redirect_stdout(output):
        code=guard.issue_pr_main(SimpleNamespace(pull_request_number=candidate["pr_number"],expected_head_sha=candidate["head_sha"],event_output=None),
            environ={"GITHUB_TOKEN":"synthetic","CHARLIE_CANONICAL_API_URL":"https://canonical.invalid",
                "CHARLIE_VALIDATION_RECEIPT_KEY_B64":base64.b64encode(hashlib.sha256(b"synthetic-validation-key").digest()).decode(),
                "CHARLIE_ADMISSION_RECEIPT_SIGNING_KEY_B64":base64.b64encode(seed).decode()})
        test.assertEqual(code,0,output.getvalue())
        with tempfile.TemporaryDirectory() as directory:
            event=Path(directory)/"synthetic-event.json"
            event.write_text(json.dumps({"number":candidate["pr_number"],"repository":{"full_name":"Crewless9086/amadeus-pig-tracking-system"},"pull_request":pull}))
            with patch.object(guard,"_app_check_request",return_value={"id":1}) as publish:
                test.assertEqual(guard.trusted_check_main(SimpleNamespace(event=str(event)),environ={"CHARLIE_ADMISSION_APP_TOKEN":"synthetic"}),0,output.getvalue())
                test.assertEqual(publish.call_args.args[2]["conclusion"],"success")
    return mission(connect)["metadata"]["mission_admission"]["signed_receipt"]


def issued_predecessor(test,connect):
    rows=read_records(connect);metadata=rows[adapter.MISSION_ID]["metadata_json"]
    metadata.pop("mission_admission")
    prior={"pr_number":adapter.PREDECESSOR_PR,"branch":adapter.PREDECESSOR_BRANCH,
        "base_sha":adapter.PREDECESSOR_BASE,"head_sha":adapter.PREDECESSOR_HEAD,
        "changed_files":PREDECESSOR_PATHS,"diff_sha256":canonical_candidate_diff(PREDECESSOR_PATHS,b"synthetic candidate diff")}
    metadata["review_packet"].update(candidate_diff_sha256=prior["diff_sha256"],changed_files=PREDECESSOR_PATHS)
    with connect("") as db,db.cursor() as cursor:
        cursor.execute("update public.charlie_missions set metadata_json=%(metadata)s::jsonb where mission_id=%(mission_id)s",
            {"metadata":json.dumps(metadata),"mission_id":adapter.MISSION_ID})
    receipt=issue_candidate(test,connect,prior)
    rows=read_records(connect)
    with connect("") as db,db.cursor() as cursor:correction=adapter._latest_correction(cursor)[1]
    return receipt,arguments(rows[adapter.MISSION_ID],rows[adapter.PARENT_ID],correction)


def issuer_chain(test,connect,snapshot):
    old,args=issued_predecessor(test,connect)
    stale_mission,stale_authority=mission(connect),authority(connect)[0]
    apply(args,connect);before=snapshot()
    test.assertEqual(callback(test,connect,old,adapter.PREDECESSOR_PR).status_code,409)
    raced=callback(test,connect,old,adapter.PREDECESSOR_PR,stale_mission=stale_mission,stale_authority=stale_authority)
    test.assertEqual((raced.status_code,raced.json["status"]),(409,"mission_admission_candidate_mismatch"))
    test.assertEqual(snapshot(),before)
    receipt=issue_candidate(test,connect,json.loads(args["manifest_bytes"])["candidate"])
    test.assertNotEqual(receipt["receipt_id"],old["receipt_id"])
    before=snapshot();test.assertEqual(apply(args,connect)["status"],"exact_replay")
    test.assertEqual(callback(test,connect,old,adapter.PREDECESSOR_PR).status_code,409)
    test.assertEqual(snapshot(),before)


class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        use_synthetic_candidate(self)
        self.db = MemoryDB(); self.args = arguments(); self.connect = lambda _: self.db
    def snapshot(self): return deepcopy((self.db.rows,self.db.events,self.db.ops))
    def test_preparation_never_connects_and_does_not_infer_authentication(self):
        result = adapter.reconcile_candidate(**self.args, connect_factory=lambda _: self.fail("unexpected connection"))
        self.assertEqual((result["status"],result["writes"]),("prepared",0))
        with self.assertRaisesRegex(adapter.ReconciliationError,"independent_authentication"):
            adapter.reconcile_candidate(**self.args,dry_run=False,connect_factory=lambda _: self.fail("unexpected connection"))
    def test_atomic_success_preserves_parent_family_source_and_old_signed_receipt(self):
        before = self.snapshot(); result = apply(self.args,self.connect)
        self.assertEqual(result["status"],"candidate_reconciled"); self.assertEqual(self.db.commits,1)
        child = self.db.rows[adapter.MISSION_ID]; md = child["metadata_json"]
        self.assertEqual(self.db.rows[adapter.PARENT_ID],before[0][adapter.PARENT_ID])
        self.assertTrue(adapter._same_scalar_record(child,before[0][adapter.MISSION_ID]))
        self.assertEqual(md["mission_admission"]["signed_receipt"],before[0][adapter.MISSION_ID]["metadata_json"]["mission_admission"]["signed_receipt"])
        self.assertEqual(md["mission_admission"]["status"],"invalidated")
        self.assertEqual(md["mission_family"]["retained_context"],"retain")
        self.assertEqual(md["external_supervisor"]["transport"],"codex_desktop")
        self.assertEqual((len(self.db.events),len(self.db.ops)),(3,1))
        after = self.snapshot(); self.assertEqual(apply(self.args,self.connect)["status"],"exact_replay")
        self.assertEqual(self.snapshot(),after)
    def test_replay_after_new_admission_preserves_receipt_and_later_evidence(self):
        apply(self.args,self.connect); md = self.db.rows[adapter.MISSION_ID]["metadata_json"]
        md["mission_admission"] = {"mission_id":adapter.MISSION_ID,"root_mission_id":adapter.PARENT_ID,
            "generation":"synthetic-new-generation","base_sha":adapter.BASE,"head_sha":adapter.HEAD,
            "status":"valid","signed_receipt":{"new_synthetic_receipt":True}}
        md["later_evidence"] = ["preserve"]
        before = self.snapshot(); self.assertEqual(apply(self.args,self.connect)["writes"],0)
        self.assertEqual(self.snapshot(),before)
    def test_any_failure_rolls_back_owner_invalidation_and_history(self):
        for stage in ("correction","correction_readback","binding","history","readback"):
            with self.subTest(stage=stage):
                db = MemoryDB(); db.fail = stage; before=deepcopy((db.rows,db.events,db.ops))
                with self.assertRaises((adapter.ReconciliationError,RuntimeError)):
                    apply(self.args,lambda _:db)
                self.assertEqual((db.rows,db.events,db.ops),before); self.assertEqual(db.commits,0)
    def test_changed_expected_record_or_latest_correction_is_rejected(self):
        for target in (adapter.MISSION_ID,adapter.PARENT_ID):
            db=MemoryDB();db.rows[target]["title"]="concurrent change";before=deepcopy(db.rows)
            with self.assertRaises(adapter.ReconciliationError):apply(self.args,lambda _:db)
            self.assertEqual(db.rows,before)
        db=MemoryDB(); next(iter(db.events.values()))[0]["summary"]="changed correction"
        with self.assertRaisesRegex(adapter.ReconciliationError,"predecessor_correction_changed"):
            apply(self.args,lambda _:db)
    def test_changed_replay_approval_is_rejected_without_writes(self):
        apply(self.args,self.connect);before=self.snapshot()
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        a["instruction_text"]="Different synthetic approval"
        with self.assertRaisesRegex(adapter.ReconciliationError,"replay_history_conflict"):apply(encode(m,a),self.connect)
        self.assertEqual(self.snapshot(),before)
    def test_wrong_candidate_scope_and_fabricated_provenance_fail_before_connection(self):
        for field in ("head","scope","parent","source","prohibition","tests"):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            if field=="head":m["candidate"]["head_sha"]="0"*40
            elif field=="scope":m["candidate"]["changed_files"].append("app.py")
            elif field=="parent":m["expected_parent_sha256"]="0"*64
            elif field=="source":a["source"]["source_message_id"]="invented"
            elif field=="prohibition":m["contract"]["forbidden_effects"].remove("farm_write")
            elif field=="tests":m["contract"]["required_tests"].remove("mission-admission")
            with self.subTest(field=field),self.assertRaises(adapter.ReconciliationError):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
    def test_pending_candidate_pins_reject_before_source_or_database_access(self):
        for fields in ({"CANDIDATE_PR": None}, {"CANDIDATE_PR": True}, {"HEAD": None},
                       {"APPROVED_RUNTIME_HEAD": None}, {"PATHS": []}, {"PATHS": ["../other.py"]}):
            with self.subTest(fields=fields), patch.multiple(adapter, **fields), \
                 patch.object(adapter, "verify_source_and_candidate") as source, \
                 patch.object(store, "_connect") as connect:
                with self.assertRaisesRegex(adapter.ReconciliationError, "candidate_pins_pending"):
                    adapter.reconcile_candidate(**self.args, dry_run=False,
                        authenticated_owner_principal=OWNER, authenticated_desktop_principal=PRINCIPAL,
                        connect_factory=lambda _: self.fail("unexpected connection"))
                source.assert_not_called(); connect.assert_not_called()
        with patch.object(adapter, "HEAD", None), patch.object(adapter.subprocess, "check_output") as git:
            with self.assertRaisesRegex(adapter.ReconciliationError, "candidate_pins_pending"):
                adapter.verify_source_and_candidate({})
            git.assert_not_called()

    def test_exact_web_only_scope_rejects_scheduler_effects_and_wrong_rollback(self):
        changes = {
            "wrong_web_rollback": ("allowed_effects", f"application_revision_rollback:web:{adapter.WEB_ROLLBACK}",
                                   f"application_revision_rollback:web:{adapter.PREDECESSOR_BASE}"),
            "missing_cron_prohibition": ("forbidden_effects", "cron_deploy", None),
            "old_scheduler_exception": ("forbidden_effects", "cron_deploy",
                                        f"cron_deploy_other_than:{adapter.SCHEDULER_SERVICE}"),
            "dropped_config_prohibition": ("forbidden_effects", "service_configuration_change", None),
            "dropped_hardware_prohibition": ("forbidden_effects", "hardware_command", None),
        }
        for field, (key, previous, replacement) in changes.items():
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            contract=m["contract"]
            contract[key].remove(previous)
            if replacement is not None: contract[key].append(replacement)
            with self.subTest(field=field),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("existing_web_application_release:srv-synthetic-other", "manual_cron_trigger",
                       f"existing_scheduler_application_release:{adapter.SCHEDULER_SERVICE}",
                       "existing_scheduler_application_release:crn-synthetic-other",
                       f"application_revision_rollback:scheduler:{adapter.SCHEDULER_SERVICE}:{adapter.SCHEDULER_ROLLBACK}",
                       "cron_deploy", "application_revision_rollback:web:" + adapter.PREDECESSOR_BASE):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            m["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed|effect_scope_conflict"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_exact_service_acceptance_cannot_broaden_or_drop_rollback_bindings(self):
        for before, after in ((adapter.WEB_SERVICE, "srv-synthetic-other"),
                              (adapter.WEB_ROLLBACK, "0" * 40),
                              (adapter.HEAD, "1" * 40)):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            m["contract"]["operational_acceptance"] = [value.replace(before, after)
                for value in m["contract"]["operational_acceptance"]]
            with self.subTest(before=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_retained_preview_authority_cannot_drop_or_broaden_a_guard(self):
        for effect in ("automatic_once_per_claim_never_attempted_retained_preview_renewal",
                       "current_recipient_authorized_protected_confirmation_delivery",
                       "verified_same_case_mortality_completion_projection"):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            m["contract"]["allowed_effects"].remove(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for before,after in (("once only", "without limit"),
                             ("every send, attempt, acceptance, ambiguity, confirmation, result and card marker is absent", "card marker is absent"),
                             ("immediately before sending", "only at initial intake"),
                             ("A genuine authorized confirmation remains mandatory", "No confirmation is needed"),
                             ("non-superseded current canonical operation and welfare readback", "a sent card")):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            original=m["contract"]["operational_acceptance"]
            changed=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed,original)
            m["contract"]["operational_acceptance"]=changed
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        m["contract"]["operational_acceptance"].append("No new protected-preview activation authority.")
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_conversation_scope_preserves_read_only_principal_and_exact_evidence_guards(self):
        for before, after in (("read-only repeatable-read snapshot", "unbounded mutable snapshot"),
                              ("an unrelated pending farrowing question must not capture", "an unrelated pending farrowing question may capture"),
                              ("contain ambiguous or missing identity", "guess ambiguous or missing identity"),
                              ("scope evidence before limits", "limit before scoping evidence"),
                              ("must not create farm facts", "may create farm facts"),
                              ("borrow another recipient's context", "borrow context freely"),
                              ("later natural manager-cycle continuity", "a terminal-triggered cycle")):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            original=m["contract"]["operational_acceptance"]
            changed=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed,original)
            m["contract"]["operational_acceptance"]=changed
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        plan=adapter.prepare_reconciliation(**self.args)
        self.assertTrue(PRESERVED_PREVIEW_EFFECTS <= set(plan["manifest"]["contract"]["allowed_effects"]))
        self.assertFalse(PRESERVED_PREVIEW_EFFECTS & adapter.ADDED_EFFECTS)

    def test_blanket_cron_prohibition_and_prior_delivery_history_are_preserved(self):
        before=self.snapshot()
        prior=self.db.rows[adapter.MISSION_ID]["metadata_json"]["mission_admission_contract"]
        prior["forbidden_effects"].append("synthetic_future_prohibition")
        args=arguments(self.db.rows[adapter.MISSION_ID],self.db.rows[adapter.PARENT_ID])
        apply(args,self.connect)
        current=self.db.rows[adapter.MISSION_ID]["metadata_json"]["mission_admission_contract"]
        self.assertEqual(set(current["forbidden_effects"]),
            (set(prior["forbidden_effects"]) - adapter.REMOVED_FORBIDDEN_EFFECTS) | {"cron_deploy"})
        self.assertIn("cron_deploy", current["forbidden_effects"])
        self.assertIn("synthetic_future_prohibition", current["forbidden_effects"])
        self.assertEqual(self.db.rows[adapter.PARENT_ID], before[0][adapter.PARENT_ID])
        self.assertEqual(current["forbidden_files"], prior["forbidden_files"])
        plan=adapter.prepare_reconciliation(**args)
        history=self.db.events[plan["event_id"]][0]
        self.assertIn("cron_deploy", history["previous_record"]["metadata_json"]["mission_admission_contract"]["forbidden_effects"])
        after=self.snapshot(); self.assertEqual(apply(args,self.connect)["writes"],0)
        self.assertEqual(self.snapshot(),after)

    def test_consistently_rebound_but_wrong_predecessor_fails_before_connection(self):
        for field in ("pr", "head", "base", "branch", "status"):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            row=m["expected_child_record"];md=row["metadata_json"]
            packet,contract,admission=md["review_packet"],md["mission_admission_contract"],md["mission_admission"]
            if field=="pr":packet["pr_number"]=1343
            elif field=="head":packet["candidate_revision"]=admission["head_sha"]="b"*40
            elif field=="base":contract["base_sha"]=admission["base_sha"]="a"*40
            elif field=="branch":packet["branch_name"]=contract["branch"]="synthetic-other-branch"
            else:admission["status"]="consumed"
            m["expected_child_sha256"]=adapter.digest(adapter.canonical(row))
            with self.subTest(field=field),self.assertRaisesRegex(adapter.ReconciliationError,"predecessor_binding_invalid"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
    def test_prior_reconciliation_history_survives_the_next_transition(self):
        old_binding={"version":adapter.VERSION,"event_id":"synthetic-pr1344-rebind",
            "manifest_sha256":"5"*64,"approval_sha256":"6"*64}
        md=self.db.rows[adapter.MISSION_ID]["metadata_json"]
        md["desktop_candidate_reconciliation"]=deepcopy(old_binding)
        old_history=({"bindings":{"desktop_candidate_reconciliation":deepcopy(old_binding)},
            "previous_record":{"historical_pr1343":"retained"}},OWNER,"workflow_updated")
        self.db.events[old_binding["event_id"]]=deepcopy(old_history)
        args=arguments(self.db.rows[adapter.MISSION_ID],self.db.rows[adapter.PARENT_ID])
        before=deepcopy(self.db.rows[adapter.MISSION_ID])
        apply(args,self.connect)
        self.assertEqual(self.db.events[old_binding["event_id"]],old_history)
        event_id=adapter.prepare_reconciliation(**args)["event_id"]
        self.assertEqual(self.db.events[event_id][0]["previous_record"],before)
        current=self.db.rows[adapter.MISSION_ID]["metadata_json"]
        self.assertIn("cron_deploy",current["mission_admission_contract"]["forbidden_effects"])
        self.assertTrue(adapter.ADDED_FORBIDDEN_EFFECTS <= set(current["mission_admission_contract"]["forbidden_effects"]))
        self.assertFalse(adapter.REMOVED_EFFECTS & set(current["mission_admission_contract"]["allowed_effects"]))
        snapshot=self.snapshot();self.assertEqual(apply(args,self.connect)["writes"],0)
        self.assertEqual(self.snapshot(),snapshot)
    def test_apply_source_pins_precede_database_and_autocommit_is_rejected(self):
        with patch.object(adapter,"verify_source_and_candidate",side_effect=adapter.ReconciliationError("source_changed")):
            with self.assertRaisesRegex(adapter.ReconciliationError,"source_changed"):
                adapter.reconcile_candidate(**self.args,dry_run=False,authenticated_owner_principal=OWNER,
                    authenticated_desktop_principal=PRINCIPAL,connect_factory=lambda _:self.fail("unexpected connection"))
        self.db.autocommit=True
        with self.assertRaisesRegex(adapter.ReconciliationError,"transaction_required"):apply(self.args,self.connect)
    def test_explicit_connection_is_required_before_source_or_database_access(self):
        with patch.object(adapter,"verify_source_and_candidate") as source, patch.object(store,"_connect") as connect:
            for value in (None,""," "):
                with self.subTest(database_url=value),self.assertRaisesRegex(adapter.ReconciliationError,"explicit_database_connection_required"):
                    adapter.reconcile_candidate(**self.args,dry_run=False,authenticated_owner_principal=OWNER,
                        authenticated_desktop_principal=PRINCIPAL,database_url=value)
            source.assert_not_called();connect.assert_not_called()
    def test_noncanonical_family_is_rejected_even_with_matching_record_digest(self):
        for field in ("root_mission_id","parent_mission_id"):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            row=m["expected_child_record"];row["metadata_json"]["mission_family"][field]="OTHER-MISSION"
            m["expected_child_sha256"]=adapter.digest(adapter.canonical(row))
            with self.subTest(field=field),self.assertRaisesRegex(adapter.ReconciliationError,"predecessor_binding_invalid"):
                adapter.prepare_reconciliation(**encode(m,a))
    def test_source_pin_covers_tracked_and_untracked_dependencies_outside_modules(self):
        plan=adapter.prepare_reconciliation(**self.args)
        for changed,untracked,reason in ((b"services/database_service.py\n",b"","trusted_checkout_changed"),
                (b"",b"services/extra_dependency.py\n","untracked_trusted_dependency")):
            def git(command,**_):
                args=command[2:]
                if args==["rev-parse","origin/main"]:return (adapter.BASE+"\n").encode()
                if args==["diff","--name-only",adapter.BASE,"--"]:return changed
                if args==["ls-files","--others","--exclude-standard"]:return untracked
                self.fail("source verification reached candidate before rejecting checkout drift")
            with self.subTest(reason=reason),patch.object(adapter.subprocess,"check_output",side_effect=git):
                with self.assertRaisesRegex(adapter.ReconciliationError,reason):adapter.verify_source_and_candidate(plan)
    def test_exact_candidate_requires_approved_ancestry_and_exact_qualification_delta(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        m["implementation"]["adapter_sha256"]=adapter.digest(Path(adapter.__file__).read_bytes())
        m["implementation"]["helper_files"]={p:adapter.digest((adapter.ROOT/p).read_bytes()) for p in adapter.HELPERS}
        plan=adapter.prepare_reconciliation(**encode(m,a))
        self.assertEqual(adapter.APPROVED_RUNTIME_HEAD, "fb3d90d61b2a0a75998930f9428db7f28b30be93")
        self.assertEqual(adapter.APPROVED_RUNTIME_HEAD, adapter.HEAD)
        self.assertEqual(adapter.QUALIFICATION_TEST_PATHS, [])
        cases=("valid", "wrong_ancestor", "runtime_change", "extra_test", "wrong_test")
        for case in cases:
            qualification_paths=list(adapter.QUALIFICATION_TEST_PATHS)
            if case=="runtime_change":qualification_paths.append("modules/oom_sakkie/telegram_gateway.py")
            elif case=="extra_test":qualification_paths.append("tests/unapproved_test.py")
            elif case=="wrong_test":qualification_paths=["tests/unapproved_test.py"]
            def git(command,**_):
                args=command[2:]
                if args==["rev-parse","origin/main"]:return (adapter.BASE+"\n").encode()
                if args==["diff","--name-only",adapter.BASE,"--"]:return b""
                if args==["ls-files","--others","--exclude-standard"]:return b""
                if args==["merge-base",adapter.APPROVED_RUNTIME_HEAD,adapter.HEAD]:
                    return (("a"*40 if case=="wrong_ancestor" else adapter.APPROVED_RUNTIME_HEAD)+"\n").encode()
                if args==["diff","--name-only",adapter.APPROVED_RUNTIME_HEAD,adapter.HEAD,"--"]:
                    return ("".join(path+"\n" for path in qualification_paths)).encode()
                if args==["rev-parse",adapter.HEAD+"^{tree}"]:return (m["candidate"]["tree_sha"]+"\n").encode()
                if args==["diff","--name-only",adapter.BASE,adapter.HEAD,"--"]:
                    return ("\n".join(adapter.PATHS)+"\n").encode()
                if args==["diff","--no-ext-diff","--no-textconv","--binary","--full-index",adapter.BASE,adapter.HEAD,"--"]:
                    return b"synthetic candidate diff"
                self.fail("unexpected Git inspection: "+repr(args))
            with self.subTest(case=case),patch.object(adapter.subprocess,"check_output",side_effect=git):
                if case=="valid":adapter.verify_source_and_candidate(plan)
                else:
                    reason="approved_runtime_ancestry_changed" if case=="wrong_ancestor" else "qualification_only_test_paths_changed"
                    with self.assertRaisesRegex(adapter.ReconciliationError,reason):
                        adapter.verify_source_and_candidate(plan)
    def test_real_protected_issuer_callback_verifier_and_late_callback_chain(self):
        issuer_chain(self,self.connect,self.snapshot)
    def test_cli_is_preparation_only(self):
        source=Path(adapter.__file__).read_text()
        self.assertNotIn('add_argument("--apply',source)
        self.assertNotIn('add_argument("--database',source)


@unittest.skipUnless(os.getenv("OOM_DESKTOP_REBIND_TEST_DATABASE_URL"),"explicit disposable rebind database URL required")
class ReconciliationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.pg=psycopg;cls.url=os.environ["OOM_DESKTOP_REBIND_TEST_DATABASE_URL"]
        with cls.pg.connect(cls.url) as db:
            name=db.execute("select current_database()").fetchone()[0]
            if not name.startswith("oom_desktop_rebind_test"):
                raise unittest.SkipTest("refusing non-disposable database name")
            db.execute("""create table if not exists public.charlie_missions (
                mission_id text primary key,status text not null,source text not null,
                source_message_id text,telegram_user_id text,telegram_chat_id text,
                raw_text text not null,title text not null,urgency text not null,
                mission_type text not null,approval_level text not null,selected_next_step text,
                owner_decision text,codex_chat_write_status text,metadata_json jsonb not null,
                created_at timestamptz default now(),updated_at timestamptz default now());
                create table if not exists public.charlie_mission_events (
                event_id text primary key,mission_id text references public.charlie_missions(mission_id),
                event_type text,notes text,recorded_by text,metadata_json jsonb,
                created_at timestamptz default now());
                create table if not exists public.operational_events (
                event_id text primary key,idempotency_key text unique,schema_version text,event_type text,domain text,
                aggregate_type text,aggregate_id text,source_system text,source_record_id text,authority_tier text,
                privacy_class text,actor_type text,actor_id text,correlation_id text,causation_id text,
                occurred_at timestamptz,recorded_at timestamptz,freshness_at timestamptz,
                payload_json jsonb,provenance_json jsonb);""")
    def setUp(self):
        use_synthetic_candidate(self)
        child,parent,correction=fixtures()
        with self.pg.connect(self.url) as db:
            db.execute("alter table public.charlie_mission_events drop constraint if exists reject_oom_rebind_history")
            db.execute("delete from public.operational_events where aggregate_id=%s",(adapter.MISSION_ID,))
            db.execute("delete from public.charlie_mission_events where mission_id=any(%s)",([adapter.MISSION_ID,adapter.PARENT_ID],))
            db.execute("delete from public.charlie_missions where mission_id=any(%s)",([adapter.MISSION_ID,adapter.PARENT_ID],))
            for row in (parent,child):
                db.execute("""insert into public.charlie_missions(mission_id,status,source,raw_text,title,
                    urgency,mission_type,approval_level,metadata_json) values(%s,%s,%s,%s,%s,'P2','review',%s,%s::jsonb)""",
                    (row["mission_id"],row["status"],row["source"],row["raw_text"],row["title"],row["approval_level"],json.dumps(row["metadata_json"])))
            db.execute("""insert into public.charlie_mission_events(event_id,mission_id,event_type,recorded_by,metadata_json,created_at)
                values(%s,%s,'owner_correction_recorded',%s,%s::jsonb,%s)""",
                (correction["event_id"],adapter.MISSION_ID,OWNER,json.dumps(correction),correction["recorded_at"]))
            child=db.execute("select to_jsonb(m) from public.charlie_missions m where mission_id=%s",(adapter.MISSION_ID,)).fetchone()[0]
            parent=db.execute("select to_jsonb(m) from public.charlie_missions m where mission_id=%s",(adapter.PARENT_ID,)).fetchone()[0]
        self.args=arguments(child,parent,correction);self.connect=lambda _:self.pg.connect(self.url)
    def snapshot(self):
        with self.pg.connect(self.url) as db:
            return (db.execute("select to_jsonb(m) from public.charlie_missions m order by mission_id").fetchall(),
                db.execute("select to_jsonb(e) from public.charlie_mission_events e order by event_id").fetchall(),
                db.execute("select to_jsonb(e) from public.operational_events e order by event_id").fetchall())
    def test_real_postgres_protected_issuer_and_replay_chain(self):
        issuer_chain(self,self.connect,self.snapshot)
    def test_real_success_and_zero_write_replay(self):
        self.assertEqual(apply(self.args,self.connect)["status"],"candidate_reconciled")
        before=self.snapshot();self.assertEqual(apply(self.args,self.connect)["status"],"exact_replay")
        self.assertEqual(self.snapshot(),before)
    def test_real_history_failure_rolls_back_real_owner_invalidation(self):
        with self.pg.connect(self.url) as db:
            db.execute("alter table public.charlie_mission_events add constraint reject_oom_rebind_history check(event_type<>'workflow_updated')")
        before=self.snapshot()
        with self.assertRaises(self.pg.Error):apply(self.args,self.connect)
        self.assertEqual(self.snapshot(),before)
    def test_real_concurrent_replays_serialize_to_one_transition(self):
        with patch.object(adapter,"verify_source_and_candidate"),ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:adapter.reconcile_candidate(**self.args,dry_run=False,
                authenticated_owner_principal=OWNER,authenticated_desktop_principal=PRINCIPAL,connect_factory=self.connect),range(2)))
        self.assertEqual(sorted(r["status"] for r in results),["candidate_reconciled","exact_replay"])
        with self.pg.connect(self.url) as db:
            self.assertEqual(db.execute("select count(*) from public.operational_events").fetchone()[0],1)
    def test_real_stale_record_conflict_preserves_concurrent_writer(self):
        with self.pg.connect(self.url) as db:
            db.execute("update public.charlie_missions set title='concurrent title' where mission_id=%s",(adapter.MISSION_ID,))
        before=self.snapshot()
        with self.assertRaisesRegex(adapter.ReconciliationError,"predecessor_state_changed"):apply(self.args,self.connect)
        self.assertEqual(self.snapshot(),before)


if __name__ == "__main__":
    unittest.main()
