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
PREDECESSOR_PATHS = ['docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md', 'docs/09-vault-brain/CHANGELOG.md', 'modules/oom_sakkie/general_manager_worker.py', 'modules/oom_sakkie/herdmaster_case_disposition.py', 'tests/test_oom_sakkie_mortality_reconciliation.py', 'tests/test_oom_sakkie_mortality_reconciliation_postgres.py']

PRESERVED_PREVIEW_EFFECTS = {'current_recipient_authorized_protected_confirmation_delivery',
    'verified_same_case_mortality_completion_projection'}
PRESENTATION_EFFECTS = {'retained_mortality_single_first_attempt_presentation_window',
    'retained_mortality_source_fenced_atomic_confirmation',
    'canonical_completed_retained_mortality_delivery_recovery'}
CONTINUATION_EFFECT = 'owner_requested_expired_retained_mortality_confirmation_successor'
READ_QUERY_EFFECT = 'herdmaster_canonical_domain_scoped_read_answers'
SUCCESSOR_EFFECTS = {
    'herdmaster_exact_canonical_advisory_case_disposition',
    'herdmaster_stable_sow_litter_identity_reassessment',
    'retained_mortality_original_report_identity_reassessment',
    'retained_mortality_audited_never_attempted_orphan_claim_replacement',
}
FARROWING_REVIEW_EFFECTS = {'herdmaster_exact_retained_farrowing_refresh',
    'retained_farrowing_configured_owner_informational_review'}
FAMILY_STYLE_EFFECTS = {'oom_sakkie_shared_family_message_presentation',
    'authenticated_historical_farrowing_review_reply_protected_preview'}
CONDITION_OBSERVATION_EFFECTS = {'herdmaster_protected_body_condition_observation_intake'}
COHORT_EFFECTS = {'herdmaster_canonical_purpose_cohort_work_advisory'}
PURPOSE_NOTICE_EFFECT = 'herdmaster_ready_purpose_private_owner_notice'
TELEGRAM_EFFECTS = {'herdmaster_consolidated_purpose_overview', 'herdmaster_telegram_exact_purpose_review', 'herdmaster_owner_confirmed_purpose_batch', 'herdmaster_owner_requested_purpose_review_date'}
CONSUMED_MIGRATION_EFFECT = 'supabase_schema_migration:20261004232451_allow_herdmaster_purpose_protected_claims'
PRIOR_COHORT_ACCEPTANCE = 'Share canonical purpose-review work between genuine weighing answers and the existing manager case, preserving day-14 eligibility, qualifying dated weights, cohort identity and current reconciliation. Missing historical coverage alone never establishes current weighing work. List clear weighing members beside held members with exact reasons; unknown, conflicting or unsupported evidence remains held or unavailable, never false no-work. Exclude conclusively sold/off-farm animals. Recorded weights advance the same case to decision only when the complete cohort has no missing or blocked member. Use one bounded read-only repeatable-read snapshot and shared remaining deadline; refuse overflow, query failure or inconsistent source. Detailed purpose reads remain opt-in for weighing. Observation time, day counters, display order and unrendered advice must not churn material evidence or create duplicate cases or attempts. This is an advisory application capability, not farm execution or release-operation authority. Preserve protected condition-observation intake, genuine observation and owner confirmation, hold preservation, all prior effects and the five metadata-write registration. Add no farm writer, claim, schedule, schema, model call, manual send or provider retry. Require a genuine loaded-revision weighing question, exact retained typed/provider binding, canonical cohort readback and later natural same-case reassessment; synthetic tests and prior releases do not prove this owner outcome.'
CONCISE_BRIEF_EFFECTS = {'rootline_proven_no_send_retry_presented_text_binding', 'oom_sakkie_typed_concise_farm_brief_presentation'}
READINESS_EFFECTS = {'herdmaster_delivered_breeding_subject_read_context', 'herdmaster_current_weighing_status_order_reconciliation'}
RETIRED_RENEWAL_EFFECT = 'automatic_once_per_claim_never_attempted_retained_preview_renewal'
# Synthetic candidate identity permits pre-publication qualification only while
# pins are pending. Final qualification uses the real pins, never owner approval.
SYNTHETIC_PINS = {"CANDIDATE_PR": 9991, "HEAD": "b" * 40, "APPROVED_RUNTIME_HEAD": "b" * 40, "TREE": "c" * 40,
    "PATHS": ["modules/oom_sakkie/synthetic_herdmaster_successor.py", "tests/test_synthetic_herdmaster_successor.py"]}


FINAL_CANDIDATE_PINS = {'CANDIDATE_PR': 1388, 'HEAD': 'cf52dc12afb8be007cad0a082a8b73693784a481', 'TREE': '7859284427aab522bc366063ccfb7dcd25e37291', 'APPROVED_RUNTIME_HEAD': 'cf52dc12afb8be007cad0a082a8b73693784a481', 'PATHS': ['.github/workflows/charlie-core-tests.yml', 'docs/09-vault-brain/10-source-map/IMPLEMENTATION_SOURCE_MAP.md', 'docs/09-vault-brain/CHANGELOG.md', 'modules/charlie/__init__.py', 'modules/charlie/executive_runtime.py', 'modules/charlie/executive_store.py', 'modules/charlie/manager_dependency_intake.py', 'modules/charlie/mission_store.py', 'modules/charlie/runner_control.py', 'modules/charlie/runtime_activation.py', 'modules/charlie/runtime_staging.py', 'modules/charlie/validation_receipt.py', 'scripts/charlie_manager_intake_runner.py', 'scripts/charlie_observe_only_runner.py', 'scripts/charlie_runner_supervisor.py', 'scripts/charlie_runner_task_launcher.py', 'scripts/charlie_runner_watchdog.py', 'scripts/charlie_runtime_stage.py', 'tests/charlie_windows_lifecycle_harness.py', 'tests/test_charlie_manager_dependency_intake.py', 'tests/test_charlie_manager_dependency_intake_postgres.py', 'tests/test_charlie_manager_intake_runner.py', 'tests/test_charlie_runner_control.py', 'tests/test_charlie_runner_task_launcher.py']}

def use_synthetic_candidate(test):
    pending = {key: deepcopy(value) for key, value in SYNTHETIC_PINS.items()
               if getattr(adapter, key) is None or getattr(adapter, key) == []}
    if not pending:
        return  # Final qualification exercises the real frozen pins.
    # Import-time release clauses bind the same synthetic pins as the fixture.
    pending["REQUIRED_ACCEPTANCE"] = {
        value.replace(f"PR{adapter.CANDIDATE_PR}", f"PR{pending.get('CANDIDATE_PR', adapter.CANDIDATE_PR)}")
             .replace(f"head {adapter.HEAD}", f"head {pending.get('HEAD', adapter.HEAD)}")
             .replace(f"candidate {adapter.HEAD}", f"candidate {pending.get('HEAD', adapter.HEAD)}")
        for value in adapter.REQUIRED_ACCEPTANCE}
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
        "allowed_effects": ['application_revision_rollback:web:eb1afc7c91701683694d0bb104f02cd2fd0b3a54', 'authenticated_historical_farrowing_review_reply_protected_preview', 'canonical_completed_retained_mortality_delivery_recovery', 'current_recipient_authorized_protected_confirmation_delivery', 'existing_task_register_reconciliation', 'existing_web_application_release', 'herdmaster_attributable_approved_purpose_case_completion', 'herdmaster_canonical_domain_scoped_read_answers', 'herdmaster_canonical_purpose_cohort_work_advisory', 'herdmaster_consolidated_purpose_overview', 'herdmaster_current_weighing_status_order_reconciliation', 'herdmaster_delivered_breeding_subject_read_context', 'herdmaster_exact_canonical_advisory_case_disposition', 'herdmaster_exact_retained_farrowing_refresh', 'herdmaster_legacy_mortality_technical_pending_reconciliation', 'herdmaster_owner_confirmed_purpose_batch', 'herdmaster_owner_requested_purpose_review_date', 'herdmaster_protected_body_condition_observation_intake', 'herdmaster_ready_purpose_private_owner_notice', 'herdmaster_stable_sow_litter_identity_reassessment', 'herdmaster_telegram_exact_purpose_review', 'merge', 'oom_sakkie_shared_family_message_presentation', 'oom_sakkie_typed_concise_farm_brief_presentation', 'owner_requested_expired_retained_mortality_confirmation_successor', 'publication', 'repository_candidate_validation', 'repository_test_fixture_write', 'retained_farrowing_configured_owner_informational_review', 'retained_mortality_audited_never_attempted_orphan_claim_replacement', 'retained_mortality_original_report_identity_reassessment', 'retained_mortality_single_first_attempt_presentation_window', 'retained_mortality_source_fenced_atomic_confirmation', 'rootline_proven_no_send_retry_presented_text_binding', 'rootline_verified_current_plan_delivery_advisory_completion', 'verified_same_case_mortality_completion_projection'],
        "forbidden_effects": ['blanket_task_cleanup', 'cron_deploy', 'customer_message', 'database_migration', 'family_permission_change', 'farm_write', 'hardware_command', 'manual_cron_trigger', 'manufactured_acceptance', 'other_service_deploy', 'runner_activation', 'runtime_source_change_beyond_approved_candidate', 'service_configuration_change', 'transport_publication'],
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
        "head_sha": adapter.HEAD, "tree_sha": adapter.TREE, "changed_files": adapter.PATHS,
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
        with tempfile.TemporaryDirectory(dir=os.getenv("OOM_DESKTOP_REBIND_TEST_TEMP_ROOT")) as directory:
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


class CandidatePinTests(unittest.TestCase):
    def test_exact_candidate_and_pending_pin_refusal_before_source_or_database_access(self):
        for name, expected in FINAL_CANDIDATE_PINS.items():
            self.assertEqual(getattr(adapter, name), expected, name)
        self.assertEqual(adapter.QUALIFICATION_TEST_PATHS, [])
        authority=[v for v in adapter.REQUIRED_ACCEPTANCE if v.startswith("Require an independently authenticated attributable owner instruction")]
        self.assertEqual(len(authority),1)
        self.assertIn("exact candidate "+str(adapter.HEAD),authority[0])
        self.assertIn("this exact manager CORE receipt intake, stopped/scoped startup source and existing-web-only release contract scope",authority[0])
        self.assertFalse(any(adapter.PREDECESSOR_HEAD in v for v in adapter.REQUIRED_ACCEPTANCE))
        with patch.object(adapter, "CANDIDATE_PR", None), patch.object(adapter, "verify_source_and_candidate") as verify:
            with self.assertRaisesRegex(adapter.ReconciliationError, "candidate_pins_pending"):
                adapter.reconcile_candidate(manifest_bytes=b"{}", approval_bytes=b"{}",
                    expected_manifest_sha256="0" * 64, expected_approval_sha256="0" * 64,
                    connect_factory=lambda _: self.fail("unexpected connection"))
        verify.assert_not_called()


    def test_windows_qualification_is_exact_candidate_read_only_and_inert_until_bound(self):
        workflow=(adapter.ROOT / '.github/workflows/oom-desktop-rebind-qualification.yml').read_text()
        self.assertEqual(workflow.count('  windows-lifecycle:'),1)
        windows=workflow.split('  windows-lifecycle:',1)[1]
        self.assertIn('runs-on: windows-latest',windows)
        self.assertIn('timeout-minutes: 10',windows)
        self.assertIn('permissions:\n      contents: read',windows)
        self.assertNotIn('secrets.',windows)
        self.assertNotIn('write-all',windows)
        self.assertNotIn('pull_request_target',workflow)
        self.assertNotIn('CHARLIE_SUBPROCESS_TESTS_ENABLED',windows)
        self.assertNotIn('CHARLIE_ALLOW_PROCESS_TERMINATION',windows)
        bound=next(line.split(':',1)[1].strip() for line in windows.splitlines() if 'CHARLIE_WINDOWS_SOURCE_SHA:' in line)
        self.assertEqual(bound,adapter.HEAD)
        self.assertLess(windows.index("-notmatch '^[0-9a-f]{40}$'"),windows.index('uses: actions/checkout@'))
        self.assertIn('ref: ${{ env.CHARLIE_WINDOWS_SOURCE_SHA }}',windows)
        self.assertIn('persist-credentials: false',windows)
        self.assertIn('path: application-candidate',windows)
        self.assertEqual(windows.count('working-directory: application-candidate'),2)
        self.assertIn('$actual -cne $env:CHARLIE_WINDOWS_SOURCE_SHA',windows)
        self.assertIn('tests/charlie_windows_lifecycle_harness.py --source-sha',windows)
        self.assertIn('--report-root "$env:RUNNER_TEMP\\charlie-windows-lifecycle"',windows)
        self.assertIn('if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }',windows)
        self.assertIn('if: ${{ always() }}',windows)


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
        for field in ("pr","boolean_pr","head","tree","scope","parent","source","prohibition","tests"):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            if field=="pr":m["candidate"]["pr_number"]=adapter.CANDIDATE_PR+1
            elif field=="boolean_pr":m["candidate"]["pr_number"]=True
            elif field=="head":m["candidate"]["head_sha"]="0"*40
            elif field=="tree":m["candidate"]["tree_sha"]="0"*40
            elif field=="scope":m["candidate"]["changed_files"].append("app.py")
            elif field=="parent":m["expected_parent_sha256"]="0"*64
            elif field=="source":a["source"]["source_message_id"]="invented"
            elif field=="prohibition":m["contract"]["forbidden_effects"].remove("farm_write")
            elif field=="tests":m["contract"]["required_tests"].remove("mission-admission")
            with self.subTest(field=field),self.assertRaises(adapter.ReconciliationError):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
    def test_pending_candidate_pins_reject_before_source_or_database_access(self):
        for fields in ({"CANDIDATE_PR": None}, {"CANDIDATE_PR": True}, {"HEAD": None}, {"TREE": None},
                       {"APPROVED_RUNTIME_HEAD": None}, {"APPROVED_RUNTIME_HEAD": "a" * 40},
                       {"QUALIFICATION_TEST_PATHS": ["tests/later.py"]}, {"PATHS": None}, {"PATHS": []}, {"PATHS": ["../other.py"]}):
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

    def test_exact_web_only_scope_rejects_provider_scheduler_effects_and_wrong_rollback(self):
        changes = {
            "wrong_web_rollback": ("allowed_effects", "application_revision_rollback:web:"+adapter.WEB_ROLLBACK, "application_revision_rollback:web:"+"0"*40),
            "missing_cron_prohibition": ("forbidden_effects", "cron_deploy", None),
            "old_scheduler_exception": ("forbidden_effects", "cron_deploy", f"cron_deploy_other_than:{adapter.SCHEDULER_SERVICE}"),
            "dropped_config_prohibition": ("forbidden_effects", "service_configuration_change", None),
            "dropped_transport_prohibition": ("forbidden_effects", "transport_publication", None),
            "dropped_hardware_prohibition": ("forbidden_effects", "hardware_command", None),
        }
        for field,(key,previous,replacement) in changes.items():
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            m["contract"][key].remove(previous)
            if replacement is not None:m["contract"][key].append(replacement)
            with self.subTest(field=field),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("existing_web_application_release:srv-synthetic-other","manual_cron_trigger",f"existing_scheduler_application_release:{adapter.SCHEDULER_SERVICE}","existing_scheduler_application_release:crn-synthetic-other",f"application_revision_rollback:scheduler:{adapter.SCHEDULER_SERVICE}:{adapter.SCHEDULER_ROLLBACK}","cron_deploy","application_revision_rollback:web:"+adapter.PREDECESSOR_BASE,*sorted(adapter.REMOVED_EFFECTS)):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            m["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed|effect_scope_conflict"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))


    def test_rootline_notification_contract_refuses_every_evidence_and_lifecycle_weakening(self):
        m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
        clauses=m['contract']['operational_acceptance']
        notification=[v for v in clauses if v.startswith('Close only the existing ROOTLINE current-plan delivery advisory')]
        self.assertEqual(len(notification),1)
        self.assertEqual(len(clauses),102)
        guards=('complete positive canonical observation and provider-confirmed delivery proof',
            'same current private recipient, SAST operating date and canonical plan material',
            'lowercase 64-hex SHA-256 material','exact event/identity/provider-message refs',
            'latest relevant delivery state and current recipient policy',
            'missing, malformed, crossed, stale, uncertain or fingerprint-only evidence stays unresolved',
            'Only this complete same-material notification family',
            'fresh observation/event/result/generation metadata without resetting material digest, case generation or due time',
            'preserve full latest audit refs','Incomplete evidence retains conservative material handling',
            'retained case identity, generation, digest and refs, lease/delegation and concurrent-current-work fences',
            'retain original delivery history','refuse newer ambiguous/failed/pending state',
            'replay is silent and changed material reopens normally',
            'exact final localized retry-text binding and existing zero-send authority',
            'never physical irrigation, welfare or hardware completion',
            'This notification clause grants no mortality or welfare completion authority',
            'Add no farm write, send, replay, retry, model call, schedule, configuration, schema or permission authority',
            'tests/test_oom_sakkie_rootline_notification_followthrough.py',
            'tests/test_oom_sakkie_rootline_notification_followthrough_postgres.py',
            'Prove ROOTLINE notification follow-through without provider effects, zero skips',
            'malformed SHA/ref, recipient, lease and concurrent-current-work refusal',
            'genuine loaded-revision natural same-case completion, no duplicate notice, preserved sibling/physical objectives and later quiet continuity')
        for guard_text in guards:
            changed=deepcopy(m)
            changed['contract']['operational_acceptance']=[v.replace(guard_text,'UNAUTHORIZED') for v in clauses]
            self.assertNotEqual(changed['contract']['operational_acceptance'],clauses,guard_text)
            with self.subTest(guard=guard_text),self.assertRaisesRegex(adapter.ReconciliationError,'approved_scope_delta_changed'):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail('unexpected connection'))
        changed=deepcopy(m);changed['contract']['operational_acceptance'].remove(notification[0])
        with self.assertRaisesRegex(adapter.ReconciliationError,'approved_scope_delta_changed'):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail('unexpected connection'))

    def test_all_active_rollback_acceptance_references_use_current_web_baseline(self):
        clauses=adapter.REQUIRED_ACCEPTANCE
        self.assertFalse(any('cf7df615f645e82c5cacd421ad86f85eb25ad2f9' in v for v in clauses))
        self.assertTrue(any('Roll back application to '+adapter.WEB_ROLLBACK+' if needed' in v for v in clauses))
        self.assertTrue(any('Rollback is limited to web '+adapter.WEB_SERVICE+' revision '+adapter.WEB_ROLLBACK in v for v in clauses))
        m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
        changed=deepcopy(m)
        changed['contract']['operational_acceptance']=[v.replace('Roll back application to '+adapter.WEB_ROLLBACK,'Roll back application to cf7df615f645e82c5cacd421ad86f85eb25ad2f9') for v in m['contract']['operational_acceptance']]
        with self.assertRaisesRegex(adapter.ReconciliationError,'approved_scope_delta_changed'):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail('unexpected connection'))

    def test_only_exact_102_acceptance_clauses_are_allowed_and_other_lists_remain_100(self):
        m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
        self.assertEqual(len(m['contract']['operational_acceptance']),102)
        adapter.prepare_reconciliation(**encode(m,a))
        for kind in ('missing','arbitrary','103rd'):
            changed=deepcopy(m)
            if kind=='missing':changed['contract']['operational_acceptance'].pop()
            elif kind=='arbitrary':changed['contract']['operational_acceptance'][0]='not an approved acceptance clause'
            else:changed['contract']['operational_acceptance'].append('not an approved 103rd clause')
            expected='contract_lists_invalid' if kind=='103rd' else 'approved_scope_delta_changed'
            with self.subTest(kind=kind),self.assertRaisesRegex(adapter.ReconciliationError,expected):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail('unexpected connection'))
        for field in ('forbidden_files','allowed_effects','forbidden_effects','required_tests'):
            changed=deepcopy(m);changed['contract'][field]=['synthetic-'+str(i) for i in range(101)]
            with self.subTest(field=field),self.assertRaisesRegex(adapter.ReconciliationError,'contract_lists_invalid'):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail('unexpected connection'))

    def test_rootline_notification_effect_cannot_grant_physical_completion_or_manual_action(self):
        m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
        effect='rootline_verified_current_plan_delivery_advisory_completion'
        self.assertIn(effect,m['expected_child_record']['metadata_json']['mission_admission_contract']['allowed_effects'])
        self.assertIn(effect,m['contract']['allowed_effects'])
        self.assertEqual(adapter.REMOVED_FORBIDDEN_EFFECTS,set())
        self.assertEqual(adapter.ADDED_FORBIDDEN_EFFECTS,set())
        for replacement in (None,'rootline_physical_objective_completion','rootline_hardware_operation',
                'rootline_unproven_fingerprint_completion','herdmaster_legacy_mortality_resolution',
                'rootline_manual_send','rootline_manual_replay','rootline_retry_without_zero_send_proof',
                'service_configuration_change','transport_publication','cron_deploy'):
            changed=deepcopy(m);changed['contract']['allowed_effects'].remove(effect)
            if replacement is not None:changed['contract']['allowed_effects'].append(replacement)
            with self.subTest(effect=replacement),self.assertRaisesRegex(adapter.ReconciliationError,'approved_scope_delta_changed|effect_scope_conflict'):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail('unexpected connection'))

    def test_exact_completion_eligibility_and_web_rollback_pins_cannot_broaden_scope(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        self.assertIn("existing_web_application_release",m["contract"]["allowed_effects"])
        self.assertIn("application_revision_rollback:web:"+adapter.WEB_ROLLBACK,m["contract"]["allowed_effects"])
        self.assertEqual(adapter.BASE,adapter.WEB_ROLLBACK)
        self.assertTrue({"database_migration","farm_write","service_configuration_change","transport_publication","cron_deploy"}<=set(m["contract"]["forbidden_effects"]))
        guards=("Only conclusively departed extra rows outside immutable obligations leave the unknown-purpose veto", "retained members and ambiguous/conflicting lifecycle evidence never do", "verified English/Afrikaans saved-purpose singular/plural wording", "Prior PR1387 registration and web deployment are consumed history", "preserve the existing provider state without another workflow update or rollback", "Bind the exact current deployment/settings baseline", "uncertain deployment outcomes require readback rather than blind retry", "No manual case completion, owner confirmation, callback replay or provider workflow mutation")
        for value in guards:
            changed=deepcopy(m);changed["contract"]["operational_acceptance"]=[v.replace(value,"UNAUTHORIZED") for v in m["contract"]["operational_acceptance"]]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],m["contract"]["operational_acceptance"],value)
            with self.subTest(pin=value),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in (*sorted(adapter.REMOVED_EFFECTS),"gatekeeper_callback_relay_timeout:any","n8n_workflow_timeout_rollback:any","service_configuration_change","transport_publication","web_deploy","waive_recorded_purpose_obligations","purpose_completion_without_owner_proof","purpose_completion_manual_send"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed|effect_scope_conflict"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

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
        for effect in sorted(PRESENTATION_EFFECTS | PRESERVED_PREVIEW_EFFECTS | {CONTINUATION_EFFECT}):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            m["contract"]["allowed_effects"].remove(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for before,after in (("one finite 30-minute presentation window", "unlimited presentation windows"),
                             ("empty current markers are insufficient", "empty current markers suffice"),
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
        # The acceptance-only bound rejects an appended 103rd clause before scope comparison.
        self.assertEqual(len(m["contract"]["operational_acceptance"]), 103)
        with self.assertRaisesRegex(adapter.ReconciliationError,"contract_lists_invalid"):
            adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_presentation_policy_cannot_drop_history_fencing_or_atomic_completion(self):
        changes = (
            ("at the first admitted attempt", "at each later retry"),
            ("complete durable history and fresh canonical facts", "cached preview alone"),
            ("original private principal, source binding, operation, payload and digest match", "any currently available principal matches"),
            ("exact immutable audited correction chain", "latest cleared marker fields"),
            ("Unknown or mixed history", "Known benign history"),
            ("one authoritative fresh canonical rebuild under the source lock", "a second cached preview outside the source lock"),
            ("stale append predecessors are rejected", "stale append predecessors are accepted"),
            ("in one borrowed transaction", "in separate committed transactions"),
            ("any applicable domain, welfare, source or claim failure rolls the transaction back", "a source failure may leave the farm effect committed"),
            ("Validate the canonical completed winner", "Trust the caller result"),
            ("completed mortality source chronology remains immutable on replay", "completed source chronology may be replaced on replay"),
            ("a missing or mismatched completed event must refuse without recreating a farm effect", "a missing event may be recreated"),
            ("identity, source status, facts, false values and zero counts remain exact", "only convenient facts need match"),
            ("Unsupported facts must raise rather than be stringified", "Unsupported facts may be stringified"),
            ("canonically completed retained-mortality result", "unconfirmed retained-mortality request"),
            ("Keep effect_unresolved excluded", "Include effect_unresolved"),
            ("never automatically execute a pre-domain mortality receipt", "automatically execute any pre-domain receipt"),
            ("including scheduled completed delivery", "excluding scheduled completed delivery"),
            ("operation text alone and caller-supplied confirmation flags are not authority", "caller confirmation flags grant authority"),
            ("explicit successful rollback and context exit", "assumed rollback on any error"),
            ("Never restart the window after a real attempted, ambiguous or delivered effect or a prior window audit", "Restart an expired window after any effect"),
        )
        for before, after in changes:
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            original=m["contract"]["operational_acceptance"]
            changed=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed,original,before)
            m["contract"]["operational_acceptance"]=changed
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_continuation_scope_preserves_predecessor_finality_and_genuine_successor_authority(self):
        changes = (
            ("latest verifiably delivered, expired, never-confirmed", "any unavailable"),
            ("the successor requires its own genuine confirmation", "the expired click confirms the successor"),
            ("old claim, card, token, finite window", "old card text"),
            ("Create the successor claim, immutable predecessor-keyed continuation audit and source append atomically", "Create successor rows independently"),
            ("must never create a new confirmation generation", "may create another generation automatically"),
            ("complete bounded claim, source, family, case and operational chronology", "current empty markers"),
            ("already audited successor from that validated lineage", "arbitrary prior digest"),
            ("unique contiguous generation transitions", "event hash order"),
            ("Quiet owner review must not become a false exception", "Quiet owner review may become a false exception"),
            ("must be reported as uncertain", "may be reported as delivered"),
            ("A broad timeout must not discard independently complete family evidence", "A broad timeout may discard independently complete family evidence"),
            ("unchanged total retained-read budget and cycle/send deadlines", "extended retained-read budget and cycle/send deadlines"),
            ("zero-send first preparation", "send during first preparation"),
            ("Missing, unknown or conflicting lifecycle evidence remains unresolved", "Missing lifecycle evidence means departed"),
            ("Registration approval alone does not grant provider mutation authority", "Registration approval grants plaintext provider mutation authority"),
            ("do not fabricate a hash-specific owner answer", "fabricate a hash-specific owner answer"),
        )
        for before, after in changes:
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            original=m["contract"]["operational_acceptance"]
            changed=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed,original,before)
            m["contract"]["operational_acceptance"]=changed
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        self.assertEqual(adapter.REMOVED_EFFECTS,{'application_revision_rollback:web:eb1afc7c91701683694d0bb104f02cd2fd0b3a54'})
        self.assertEqual(adapter.ADDED_EFFECTS,{'application_revision_rollback:web:cee35f3b3bce38f7022c264d458d20b41823baf0'})
        self.assertFalse(READINESS_EFFECTS & adapter.ADDED_EFFECTS)
        self.assertFalse(CONCISE_BRIEF_EFFECTS & adapter.ADDED_EFFECTS)
        self.assertFalse(FAMILY_STYLE_EFFECTS & adapter.ADDED_EFFECTS)
        self.assertFalse(FARROWING_REVIEW_EFFECTS & adapter.ADDED_EFFECTS)
        self.assertFalse(SUCCESSOR_EFFECTS & adapter.ADDED_EFFECTS)
        self.assertNotIn(READ_QUERY_EFFECT,adapter.ADDED_EFFECTS)
        self.assertNotIn(CONTINUATION_EFFECT,adapter.ADDED_EFFECTS)
        self.assertFalse(PRESENTATION_EFFECTS & adapter.ADDED_EFFECTS)

    def test_farrowing_review_preserves_owner_authority_claims_and_unconfirmed_facts(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertTrue(FARROWING_REVIEW_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(FARROWING_REVIEW_EFFECTS <= set(m["contract"]["allowed_effects"]))
        changes = (
            ("one preserved expired never-attempted recovery claim", "any stale claim"),
            ("Do not replace, renew, rearm or mutate the protected claim", "Automatically renew the protected claim"),
            ("currently configured owner", "first allowlisted recipient"),
            ("owner-role and allowlist authorization", "original claimant authority"),
            ("immediately before existing delivery or edit admission", "only when first collected"),
            ("historical farrowing counts as unconfirmed original report information", "historical farrowing counts as confirmed farm facts"),
            ("no approval buttons, protected callback token or executable farm authority", "a protected confirmation button"),
            ("existing fresh protected preview and genuine confirmation", "historical stale claim confirmation"),
            ("nonterminal disposition only", "terminal case closure"),
            ("Missing, conflicting or unavailable supersession evidence stays unresolved", "Missing supersession evidence means complete"),
        )
        for before,after in changes:
            changed=deepcopy(m)
            original=changed["contract"]["operational_acceptance"]
            changed["contract"]["operational_acceptance"]=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],original,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("farrowing_review_protected_claim_renewal", "farrowing_owner_role_grant",
                       "farrowing_review_unconfirmed_birth_recording"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_family_presentation_and_genuine_review_reply_cannot_grant_farm_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertTrue(FAMILY_STYLE_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(FAMILY_STYLE_EFFECTS <= set(m["contract"]["allowed_effects"]))
        changes = (
            ("safe text escaping", "raw provider markup"),
            ("Preserve exact actions, quantities, dates, dose, route, batch or lot, notes, lifecycle and uncertainty", "Omit detailed facts for brevity"),
            ("Before creating a protected preview claim", "After creating a protected preview claim"),
            ("Distinguish unmarked piglets and different per-animal effects", "Treat unmarked piglets and different per-animal effects as interchangeable"),
            ("refuses preparation before claim creation", "permits preparation before identity validation"),
            ("Presentation-only changes must not create or renew a protected claim", "Presentation-only changes may create a protected claim"),
            ("actual delivered review and an exact reply-to binding or unique current delivered context", "any historical review or caller supplied context"),
            ("under the existing admission locks", "without current admission locks"),
            ("Stale, revoked, cross-recipient, ambiguous, cancelled, superseded or changed context refuses preparation", "Any remembered context permits preparation"),
            ("separately attributable new input", "confirmation of historical input"),
            ("zero birth or other farm writes until its own genuine current confirmation", "immediate birth recording without another confirmation"),
            ("Keep the broader audit stages and the four existing helper qualification suites", "Skip unrelated audit stages and helper qualification suites"),
        )
        for before,after in changes:
            changed=deepcopy(m)
            original=changed["contract"]["operational_acceptance"]
            changed["contract"]["operational_acceptance"]=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],original,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("family_presentation_claim_renewal", "historical_review_automatic_confirmation",
                       "historical_farrowing_report_replay_write"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_concise_brief_and_proven_no_send_retry_preserve_existing_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertTrue(CONCISE_BRIEF_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(FAMILY_STYLE_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(CONCISE_BRIEF_EFFECTS <= set(m["contract"]["allowed_effects"]))
        changes=(
            ("typed canonical brief facts", "parsed opaque prose"),
            ("Preserve exact canonical identity, quantities, dates, coverage counts, provenance and uncertainty", "Invent omitted facts for brevity"),
            ("outside material digests, notification keys, case identities and protected authority", "inside material digests and claim authority"),
            ("preserve its already stored answer and result digest without recomposition", "recompose a previously delivered answer"),
            ("exact final localized presentation text", "raw unformatted stored packet text"),
            ("Preserve the stored packet, material identity and current recipient", "Rewrite the stored packet and recipient"),
            ("Changed text, missing zero-send proof, uncertain or delivered outcomes refuse retry", "Ambiguous and delivered outcomes permit retry"),
            ("no manual retry, message or broader attempt authority is permitted", "manual retry and extra messages are permitted"),
            ("Do not alter protected confirmation lifecycles", "Alter protected confirmation lifecycles"),
            ("tests/test_oom_sakkie_farm_brief_concise.py and tests/test_oom_sakkie_rootline_daily_presentation.py", "optional unrecorded local examples"),
        )
        for before,after in changes:
            changed=deepcopy(m);original=changed["contract"]["operational_acceptance"]
            changed["contract"]["operational_acceptance"]=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],original,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("manual_rootline_retry", "ambiguous_delivery_retry", "concise_brief_farm_write"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_breeding_context_and_weighing_reconciliation_cannot_create_farm_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertTrue(CONCISE_BRIEF_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(READINESS_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(READINESS_EFFECTS <= set(m["contract"]["allowed_effects"]))
        changes=(
            ("only order lines explicitly normalized to cancelled", "any terminal parent order"),
            ("original line, pig ID, historical tag snapshot, parent order and source digest", "only current display values"),
            ("a terminal parent order alone does not retire its lines", "a terminal parent order retires every line"),
            ("Parent-state validation, separate sales, active allocations and outlet conflicts remain unchanged", "other commercial conflicts are ignored"),
            ("subjects actually displayed in a successfully delivered read-only breeding plan", "subjects guessed from any undelivered plan"),
            ("configured private owner and current recipient", "any allowlisted user"),
            ("A read answer or historical plan is not a new observation", "A read answer is a fresh farm observation"),
            ("complete bounded current canonical lifecycle, weight, sale, allocation, outlet and parent-order evidence", "only a previous weekly weight count"),
            ("in one read-only snapshot", "in unrelated writable snapshots"),
            ("never establish physical departure or authorize a new weighing task", "authorize a new weighing task"),
            ("Unsupported, duplicate, crossed, nonfinite, missing or conflicting evidence remains unresolved", "Missing evidence proves the animal departed"),
            ("generation and active-worker lease fences", "unfenced current case state"),
            ("only genuine source changes may alter material evidence", "observation time may alter material evidence"),
            ("truthful cohort totals with bounded detail", "silently truncated cohort totals"),
            ("tests/test_herdmaster_weighing_reconciliation_postgres.py", "optional local examples"),
        )
        for before,after in changes:
            changed=deepcopy(m);original=changed["contract"]["operational_acceptance"]
            changed["contract"]["operational_acceptance"]=[v.replace(before,after) for v in original]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],original,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("manual_weighing_instruction","sale_implies_physical_exit","breeding_read_context_farm_confirmation"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_shared_purpose_cohort_scope_cannot_invent_work_or_farm_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        effect="herdmaster_canonical_purpose_cohort_work_advisory"
        self.assertIn(effect, prior["allowed_effects"])
        self.assertNotIn(effect, adapter.ADDED_EFFECTS)
        self.assertIn(effect, m["contract"]["allowed_effects"])
        self.assertTrue(CONDITION_OBSERVATION_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(CONDITION_OBSERVATION_EFFECTS <= set(m["contract"]["allowed_effects"]))
        for before,after in (
                ("Missing historical coverage alone never establishes current weighing work", "missing coverage authorizes weighing"),
                ("complete cohort has no missing or blocked member", "any subset has recorded weights"),
                ("one bounded read-only repeatable-read snapshot", "independent partial snapshots"),
                ("refuse overflow, query failure or inconsistent source", "Treat missing source as no work"),
                ("unrendered advice must not churn material evidence", "unrendered advice may create new work"),
                ("tests/test_herdmaster_purpose_weighing_postgres.py", "optional database examples"),
                ("all four full helper suites on the exact final helper head with zero skips", "old helper receipts with optional skips"),
                ("advisory application capability, not farm execution or release-operation authority", "farm execution authority from release"),
                ("later natural same-case reassessment", "a manually replayed cycle")):
            changed=deepcopy(m);original=changed["contract"]["operational_acceptance"]
            changed["contract"]["operational_acceptance"]=[v.replace(before,after) for v in original]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],original,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        changed=deepcopy(m);changed["contract"]["allowed_effects"].remove(effect)
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for unauthorized in ("automatic_weighing_execution", "purpose_decision_without_confirmation", "new_weighing_schedule"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(unauthorized)
            with self.subTest(effect=unauthorized),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_ready_purpose_notice_preserves_prior_projection_and_bounded_scope(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertTrue(COHORT_EFFECTS <= set(prior["allowed_effects"]))
        self.assertIn(PURPOSE_NOTICE_EFFECT, prior["allowed_effects"])
        self.assertNotIn(PURPOSE_NOTICE_EFFECT, adapter.ADDED_EFFECTS)
        self.assertEqual(set(m["contract"]["allowed_effects"]),
            (set(prior["allowed_effects"]) - adapter.REMOVED_EFFECTS) | adapter.ADDED_EFFECTS)
        self.assertIn("farm_write", m["contract"]["forbidden_effects"])
        clauses=m["contract"]["operational_acceptance"]
        self.assertEqual(len(clauses),102)
        self.assertTrue(all(0 < len(value) <= 2000 for value in clauses))
        shared=[value for value in clauses if value.startswith(PRIOR_COHORT_ACCEPTANCE)]
        self.assertEqual(len(shared),1)
        self.assertEqual(len(shared[0]),1992)
        self.assertIn("\n\nSeparate scheduled ready-purpose private-owner notice:",shared[0])
        self.assertIn("preceding no-provider-retry rule remains on the read-only weighing projection",shared[0])
        for before,after in (
                ("Separate scheduled ready-purpose private-owner notice", "Any owner or public message"),
                ("one existing opaque retry", "unlimited new retries"),
                ("durable zero-send proof", "uncertain send history"),
                ("exact content, owner and generation", "any content or recipient"),
                ("ambiguous history refuses", "ambiguous history retries"),
                ("unchanged case identity, material, lease and current source", "cached case alone"),
                ("No farm write, model, new schedule, schema or manual trigger", "Allow farm and manual effects"),
                ("Prove same-case delivery and later natural reassessment", "Treat green tests as acceptance"),
                ("tests/test_oom_sakkie_purpose_decision.py", "optional purpose examples"),
                ("prior read-only projection authority alone is insufficient", "prior projection grants all retries")):
            changed=deepcopy(m)
            changed["contract"]["operational_acceptance"]=[value.replace(before,after) for value in clauses]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],clauses,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        changed=deepcopy(m)
        changed["contract"]["operational_acceptance"]=[PRIOR_COHORT_ACCEPTANCE if value==shared[0] else value for value in clauses]
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_purpose_refresh_preserves_prior_qualification_and_exact_budget_scope(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior_qualification = 'Prove tests/test_herdmaster_weighing_reconciliation.py in Run canonical HERDMASTER morning recipient-language gates and tests/test_herdmaster_weighing_reconciliation_postgres.py in Prove weighing reconciliation with isolated PostgreSQL. Prove exact breeding read context through Run canonical conversational follow-up gates, retaining all prior stages and tests with zero skips. Require all four full helper suites on the exact final helper revision before production binding; local focused checks and prior run receipts do not substitute for final hosted proof. Also require tests/test_herdmaster_purpose_work.py and tests/test_oom_sakkie_owner_attention_projection.py in the same morning stage; tests/test_herdmaster_purpose_weighing_postgres.py in the same weighing PostgreSQL stage; tests/test_oom_sakkie_manager_case_sources.py and tests/test_oom_sakkie_herdmaster_case_disposition_postgres.py in Run retained report identity and age recovery gates; and tests/test_oom_sakkie_farm_brief_concise.py in Prove family presentation and historical-review continuation. Require all four full helper suites on the exact final helper head with zero skips. Also require tests/test_oom_sakkie_purpose_decision.py in Prove weighing reconciliation with isolated PostgreSQL, preserving all existing selectors and zero-skip qualification. Prove current typed admission, unchanged case/material, current private owner and lease, durable exact-text retry fencing, one proven-zero-send recovery, ambiguous and delivered refusal, and silent later replay.'
        clauses=m["contract"]["operational_acceptance"]
        qualification=[v for v in clauses if v.startswith(prior_qualification)]
        self.assertEqual(len(qualification),1)
        self.assertEqual(len(clauses),102)
        self.assertTrue(all(0<len(v)<=2000 for v in clauses))
        self.assertIn("tests/test_oom_sakkie_purpose_refresh.py",qualification[0])
        for before,after in (
                ("one canonical purpose snapshot per valid claimed group", "one cached snapshot for any group"),
                ("own refresh batch and shared 80s/30s cutoff", "independent renewed timeout per case"),
                ("Reject late, failed, missing, held or changed evidence without cached fallback", "Use initial facts after any refresh failure"),
                ("default dispatcher/store multi-cycle catch-up", "direct mocked function success"),
                ("mixed-collector isolation", "shared failure across every group"),
                ("fresh urgent priority and duplicate silence", "purpose priority and repeated notices"),
                ("no five-send guarantee or new authority", "guarantee five sends and allow new authority")):
            changed=deepcopy(m)
            changed["contract"]["operational_acceptance"]=[v.replace(before,after) for v in clauses]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],clauses,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        changed=deepcopy(m)
        changed["contract"]["operational_acceptance"]=[prior_qualification if v==qualification[0] else v for v in clauses]
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_purpose_refresh_boundaries_remain_inherited_by_completion_successor(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertIn(PURPOSE_NOTICE_EFFECT,prior["allowed_effects"])
        self.assertEqual(set(m["contract"]["allowed_effects"])-set(prior["allowed_effects"]),adapter.ADDED_EFFECTS)
        self.assertEqual(set(prior["allowed_effects"])-set(m["contract"]["allowed_effects"]),adapter.REMOVED_EFFECTS)
        self.assertEqual(set(m["contract"]["forbidden_effects"]),(set(prior["forbidden_effects"])-adapter.REMOVED_FORBIDDEN_EFFECTS)|adapter.ADDED_FORBIDDEN_EFFECTS)
        for effect in ("purpose_refresh_budget_extension","purpose_stale_snapshot_delivery",
                       "purpose_priority_over_urgent_work","manual_purpose_catchup_trigger","farm_purpose_write"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_purpose_preview_contract_preserves_exact_intent_and_existing_writer_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        clauses=m["contract"]["operational_acceptance"]
        preview=[v for v in clauses if v.startswith("Display the single-pig purpose preview")]
        self.assertEqual(len(preview),1)
        self.assertEqual(len(clauses),102)
        self.assertTrue(all(0<len(v)<=2000 for v in clauses))
        for before,after in (
                ("canonical herdmaster_purpose_correction_v2 decisions/effects contract", "legacy approved/planned_updates"),
                ("one complete matching decision/effect", "any partial matching response"),
                ("current tag and purpose, Active/on-farm identity", "remembered label alone"),
                ("matching digest/confirmation binding/actor", "unsigned client authority"),
                ("nonfuture binding no older than 1800 seconds", "unbounded future or expired binding"),
                ("leave Apply disabled", "enable Apply anyway"),
                ("browser shape checks do not authenticate the server HMAC", "browser shape authenticates the server HMAC"),
                ("including change-away-and-back and late success/failure", "except stale or change-away-and-back responses"),
                ("Recheck intent and expiry before explicit owner confirmation", "reuse prior intent without current confirmation"),
                ("freeze that exact request before awaits", "reread changing inputs after awaits"),
                ("one invocation-owned submit lock through create/approve/execute", "allow parallel duplicate submissions"),
                ("existing authenticated batch writer, canonical reread, idempotency and protected approval", "direct browser farm mutation"),
                ("Cancellation creates no batch", "Cancellation creates a batch"),
                ("without retrying the write", "retry the write after readback failure"),
                ("Preserve adjacent auction evidence panels", "replace adjacent panels"),
                ("tests/purpose_preview_playwright.config.js", "optional unbound browser check"),
                ("desktop/mobile visual evidence for the exact approved source", "unrelated screenshots"),
                ("no decision is required or invented for engineering release", "engineers create a farm decision for release")):
            changed=deepcopy(m)
            changed["contract"]["operational_acceptance"]=[v.replace(before,after) for v in clauses]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],clauses,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("browser_purpose_authority","automatic_purpose_approval","direct_purpose_write","manual_purpose_decision_for_release"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_legacy_mortality_pending_has_exact_preservation_and_no_execution_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        clauses=m["contract"]["operational_acceptance"]
        pending=[v for v in clauses if v.startswith("Reconcile retained HERDMASTER mortality and mortality-cluster advisories")]
        self.assertEqual(len(pending),1)
        self.assertEqual(len(clauses),102)
        for guard_text in (
                "Current work and collector failures take precedence",
                "absence, unknown identity or incomplete evidence never proves welfare completion",
                "full durable row, current private owner, original refs, generation and material, live owned lease",
                "concurrent-current-work fences after reads at admission and persistence",
                "Preserve case, generation, digest, refs, summary and delivery history",
                "waiting_reassessment", "herdmaster_owning_reconciliation_pending",
                "Count reconciliation_pending only after its case event commits",
                "herdmaster.mortality_technical_dependency.v1", "mortality_source_lineage_unproven",
                "stable dependency_id", "exact case/generation/digest/ref hash and owner binding",
                "completion_proven:false and core_acknowledged:false",
                "not CORE intake, dispatch, execution or repair completion",
                "Failed reads remain sanitized exceptions", "manager_reconciliation_persistence_unproven",
                "Fresh current evidence re-enters owning reconciliation",
                "Here add no CORE consumer/activation, farm/provider write, message, replay trigger, schema, schedule, model, permission or security change",
                "tests/test_oom_sakkie_mortality_reconciliation.py",
                "tests/test_oom_sakkie_mortality_reconciliation_postgres.py",
                "Prove legacy mortality technical reconciliation without farm completion",
                "malformed/crossed/stale refs, wrong owner, expired/foreign lease, post-read drift, event-persistence failure and concurrent current evidence"):
            changed=deepcopy(m)
            changed["contract"]["operational_acceptance"]=[v.replace(guard_text,"UNAUTHORIZED WEAKENING") for v in clauses]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],clauses,guard_text)
            with self.subTest(guard=guard_text),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("core_technical_dependency_dispatch","runner_activation","mortality_welfare_completion","farm_write","provider_message_replay"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaises(adapter.ReconciliationError):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_all_102_previous_acceptance_clauses_survive_scoped_receipt_additions(self):
        restored=set(adapter.REQUIRED_ACCEPTANCE)
        additions = ('Manager CORE intake is a durable receipt, not worker selection, pickup, repair execution or welfare completion. Reuse core.manager_dependency_intake with exact enabled expiring policy, explicit receipt-only mission admission and current owner/dependency/event/cycle/source binding; enforce holds, supersession, idle state and lease fences in both transactions under one 10-second budget. Commit the canonical CORE finding before separate committed readback/backlink; crash or changed authority can leave it unlinked and replay creates no duplicate or invented acknowledgement. Preserve manager pending identity, source chronology, false completion flags, siblings and later quiet reassessment. Require tests/test_charlie_manager_dependency_intake.py and tests/test_charlie_manager_dependency_intake_postgres.py in Prove typed receipt, replay, crash, concurrency and inactive defaults, zero skips. Genuine deployed intake, actual governed pickup, engineering result and later owning reconciliation require separate attributable evidence; no receipt or healthy web response proves an owner outcome.', 'Publish stopped initialization and scoped startup source only. Staging remains stopped and uses genuine signed validation, exact revision, manifest, governed path and rollback binding. Receipt-only mode reuses the existing provider/controller and cannot select unrelated work, call models, send outbox/messages or start ordinary repair; preserve ordinary and observe defaults. Failure stops the scoped mode without automatic restart. Release registration remains five metadata writes; web deployment grants no runtime activation, task enable/start, stop clearing, policy write or model-budget change. Separate short-lived exact activation authority and provider/controller readback remain required. Require tests/test_charlie_manager_intake_runner.py and tests/test_charlie_runner_task_launcher.py plus existing staging, activation, controller, supervisor, watchdog and observe regressions in Run isolated CHARLIE modules with hard timeouts; disclose skipped process gates and require their qualified proof before activation.')
        for addition in additions:
            self.assertEqual(sum(addition in v for v in restored), 1)
            restored={v.replace("\n\n"+addition, "") for v in restored}
        replacements = {'Prior PR1387 registration and web deployment are consumed history': 'Prior PR1386 registration and web deployment are consumed history', 'Roll back application to cee35f3b3bce38f7022c264d458d20b41823baf0': 'Roll back application to eb1afc7c91701683694d0bb104f02cd2fd0b3a54', 'Rollback is limited to web srv-d6sijjkhg0os73f7regg revision cee35f3b3bce38f7022c264d458d20b41823baf0': 'Rollback is limited to web srv-d6sijjkhg0os73f7regg revision eb1afc7c91701683694d0bb104f02cd2fd0b3a54', 'PR1388 head cf52dc12afb8be007cad0a082a8b73693784a481': 'PR1387 head 2604348ca98a0df4e351fa20a0c40f2d39da510f', 'exact candidate cf52dc12afb8be007cad0a082a8b73693784a481': 'exact candidate 2604348ca98a0df4e351fa20a0c40f2d39da510f', 'this exact manager CORE receipt intake, stopped/scoped startup source and existing-web-only release contract scope': 'this exact legacy mortality technical-pending reconciliation and existing-web-only release contract scope', 'Here add no CORE consumer/activation, farm/provider write, message, replay trigger, schema, schedule, model, permission or security change.': 'Add no CORE consumer/activation, farm/provider write, message, replay trigger, schema, schedule, model, permission or security change.'}
        for before,after in replacements.items():restored={v.replace(before,after) for v in restored}
        self.assertEqual(len(restored),102)
        self.assertEqual(adapter.digest(adapter.canonical(sorted(restored))),"cb617bb1ab6a95778c03ddce1c24f915a7b9dd236a21aae909e9f6b7f9956669")
        m=json.loads(self.args["manifest_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertIn("herdmaster_legacy_mortality_technical_pending_reconciliation",prior["allowed_effects"])
        self.assertNotIn("herdmaster_legacy_mortality_technical_pending_reconciliation",adapter.ADDED_EFFECTS)
        self.assertEqual(adapter.PREDECESSOR_PR,1387)
        self.assertEqual(adapter.PREDECESSOR_PATHS,PREDECESSOR_PATHS)
        self.assertEqual(adapter.BASE,adapter.WEB_ROLLBACK)

    def test_core_receipt_and_stopped_source_do_not_grant_activation_or_pickup(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        clauses=m["contract"]["operational_acceptance"]
        self.assertEqual(len(clauses),102)
        self.assertTrue(all(0<len(v)<=2000 for v in clauses))
        for guard_text in ('durable receipt, not worker selection, pickup, repair execution or welfare completion', 'exact enabled expiring policy', 'explicit receipt-only mission admission', 'current owner/dependency/event/cycle/source binding', 'holds, supersession, idle state and lease fences in both transactions', 'one 10-second budget', 'Commit the canonical CORE finding before separate committed readback/backlink', 'replay creates no duplicate or invented acknowledgement', 'source chronology, false completion flags', 'no receipt or healthy web response proves an owner outcome', 'Staging remains stopped', 'genuine signed validation, exact revision, manifest, governed path and rollback binding', 'cannot select unrelated work, call models, send outbox/messages or start ordinary repair', 'preserve ordinary and observe defaults', 'Failure stops the scoped mode without automatic restart', 'web deployment grants no runtime activation, task enable/start, stop clearing, policy write or model-budget change', 'Separate short-lived exact activation authority and provider/controller readback', 'disclose skipped process gates and require their qualified proof before activation'):
            changed=deepcopy(m)
            changed["contract"]["operational_acceptance"]=[v.replace(guard_text,"UNAUTHORIZED WEAKENING") for v in clauses]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],clauses,guard_text)
            with self.subTest(guard=guard_text),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        self.assertIn("runner_activation",m["contract"]["forbidden_effects"])
        for effect in ("runner_activation","core_technical_dependency_dispatch","task_enable","task_start","governed_stop_clear","core_policy_write","model_budget_change","receipt_is_worker_pickup","farm_write"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaises(adapter.ReconciliationError):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        changed=deepcopy(m);changed["contract"]["forbidden_effects"].remove("runner_activation")
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_preview_acceptance_coalescing_preserves_condition_observation_clauses(self):
        first='Prepare condition_observation only from a genuine current authenticated owner report naming one exact current canonical animal and its finite nonboolean body-condition score. Preserve explicit observation date and date-only precision or a supplied aware instant; reject missing, future, invalid or conflicting observation dates before claim creation. Date-only normalization is a disclosed storage convention, not an invented physical observation time. Prior read context, a score alone, a pronoun or an old condition question cannot supply missing animal identity, observation facts or confirmation authority.'
        second='Render the exact animal, score, observation date and precision in the existing protected preview. Require the currently authorized private owner and the exact bound current claim, preview digest, card and genuine confirmation before one canonical append. Cancelled, expired, revoked, cross-recipient, changed-identity or changed-preview claims refuse. Preserve original provider evidence, idempotency and atomic transaction boundaries; successful replay records no second observation.'
        self.assertIn(first+"\n\n"+second,adapter.REQUIRED_ACCEPTANCE)
        self.assertEqual(len(adapter.REQUIRED_ACCEPTANCE),102)

    def test_purpose_completion_requires_positive_complete_attributable_fenced_evidence(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        clauses=m["contract"]["operational_acceptance"]
        completion=[value for value in clauses if value.startswith("Complete only the same existing purpose-review case")]
        self.assertEqual(len(completion),1)
        self.assertEqual(len(clauses),102)
        self.assertTrue(all(0<len(value)<=2000 for value in clauses))
        for before,after in (
                ("positive current canonical correction evidence, never collector omission or disappearance", "collector disappearance alone"),
                ("Legacy uncapped 1-11 groups may adopt current-generation proof only", "any truncated retained member list"),
                ("Prospective groups of 12 or more are supported only with full proof", "12 or more prove complete membership"),
                ("Every retained member", "Any one retained member"),
                ("exact canonical litter, tag, Active and on-farm identity", "similar historical display names"),
                ("latest pig.purpose_corrected event", "any old correction event"),
                ("executed owner-approved batch and decision with matching preview and event hashes", "unexecuted proposal or unrelated approval"),
                ("after each original member's retained obligation epoch", "before any older case generation"),
                ("Missing, partial, stale or contradictory obligations and unresolved eligible extras refuse closure", "Partial or unknown cohorts close"),
                ("one read-only snapshot with four set-based reads", "unbounded independent snapshots"),
                ("six-second total deadline", "renewed deadline for every query"),
                ("64 cases and 10000 source rows", "unbounded cases and source rows"),
                ("timeout, failure or overflow refuses without partial success", "overflow is successful truncation"),
                ("exact current generation and material digest", "any older generation and digest"),
                ("lease, delegation and current-work-wins fences", "terminal finding overrides current work and lease"),
                ("Complete once including previously delivered cases; replay is silent", "Complete repeatedly and resend delivered notices"),
                ("new legitimate unresolved material retains normal reopening/history", "completed case forbids future work"),
                ("Owner-attention omission must remain unresolved unless positive completion is proved", "Owner-attention omission proves resolution"),
                ("tests/test_oom_sakkie_purpose_completion.py", "optional completion examples"),
                ("real approved batch writer and default manager store", "mocked producer outputs only"),
                ("grants no farm write, owner deferral, new notice or retry, model, schema or schedule authority", "grants all farm and scheduling authority"),
                ("genuine attributable approved correction, exact loaded-revision same-case completion and later natural quiet follow-up", "green unit tests only")):
            changed=deepcopy(m)
            changed["contract"]["operational_acceptance"]=[value.replace(before,after) for value in clauses]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],clauses,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        changed=deepcopy(m);changed["contract"]["operational_acceptance"].remove(completion[0])
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_purpose_completion_effect_is_retained_without_new_preview_execution_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        effect="herdmaster_attributable_approved_purpose_case_completion"
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertIn(effect,prior["allowed_effects"])
        self.assertTrue({"publication", "repository_test_fixture_write", "existing_task_register_reconciliation"} <= set(prior["allowed_effects"]))
        self.assertEqual(adapter.ADDED_EFFECTS,{'application_revision_rollback:web:cee35f3b3bce38f7022c264d458d20b41823baf0'})
        self.assertEqual(adapter.REMOVED_EFFECTS,{'application_revision_rollback:web:eb1afc7c91701683694d0bb104f02cd2fd0b3a54'})
        self.assertEqual(set(m["contract"]["allowed_effects"]),set(prior["allowed_effects"])-adapter.REMOVED_EFFECTS|adapter.ADDED_EFFECTS)
        self.assertEqual(set(m["contract"]["forbidden_effects"]),(set(prior["forbidden_effects"])-adapter.REMOVED_FORBIDDEN_EFFECTS)|adapter.ADDED_FORBIDDEN_EFFECTS)
        self.assertIn("farm_write",m["contract"]["forbidden_effects"])
        self.assertTrue(COHORT_EFFECTS|CONDITION_OBSERVATION_EFFECTS|{PURPOSE_NOTICE_EFFECT}<=set(prior["allowed_effects"]))
        for replacement in (None,"purpose_completion_on_omission","partial_purpose_completion", "purpose_owner_deferral", "farm_purpose_write", "purpose_completion_manual_send", "purpose_completion_new_schedule"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].remove(effect)
            if replacement:changed["contract"]["allowed_effects"].append(replacement)
            with self.subTest(effect=replacement),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_completion_clause_coalescing_preserves_both_prior_presentation_obligations(self):
        clauses=adapter.REQUIRED_ACCEPTANCE
        prior_first="Mark an overdue recorded exposure removal plan only against the supplied canonical packet's aware farm-date cutoff, never the wall clock. Missing, naive, invalid, future-start or conflicting dates remain explicit uncertainty. An open exposure record does not prove current physical presence, removal, mating or pregnancy and does not authorize physical work."
        prior_second='Preserve the existing displayed task order and question priority. Ask a named current-status and actual-removal-date question only for the supported exposure-only worklist; require the animal name and observation date in a genuine reply. Do not replace a higher-priority condition question, infer a farm fact from a planned date or create new continuation authority.'
        self.assertIn(prior_first+"\n\n"+prior_second,clauses)
        self.assertEqual(len(clauses),102)

    def test_telegram_scope_requires_full_membership_exact_confirmation_and_quiet_followup(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        clauses=m["contract"]["operational_acceptance"]
        self.assertEqual(len(clauses),102)
        self.assertTrue(all(0<len(v)<=2000 for v in clauses))
        guards=("complete immutable full-membership proof", "original per-pig obligation epochs retained across partial successors",
            "capped or unproven legacy groups remain unresolved", "one authenticated private owner",
            "inspect every exact old-to-new effect page", "Atomic exact-parent navigation",
            "current identities, weight/readiness evidence, commercial holds and case generation/membership",
            "No inferred purpose, automatic approval, plain-yes farm write or engineering approval as farm confirmation",
            "recovers the same batch and truthful acknowledgement without another farm effect",
            "fresh read-only remaining-groups overview; it never reuses confirmation authority",
            "newest request supersedes old dates and causes one natural due revisit",
            "Consolidate only new unnotified or due groups", "unavailable siblings, immutable receipts and quiet unchanged cycles",
            "Urgent provider work precedes routine summaries", "unchanged 80-second cycle/30-second reserve",
            "No new queue, schedule, AI polling, manual live trigger or per-case fallback",
            "genuine Telegram choice/confirmation plus canonical/provider readback",
            "tests/test_oom_sakkie_purpose_telegram.py", "tests/test_oom_sakkie_purpose_telegram_postgres.py", "tests/test_oom_sakkie_purpose_membership.py", "tests/test_oom_sakkie_purpose_overview.py")
        for guard_text in guards:
            changed=deepcopy(m)
            changed["contract"]["operational_acceptance"]=[v.replace(guard_text,"UNAUTHORIZED WEAKENING") for v in clauses]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],clauses,guard_text)
            with self.subTest(guard=guard_text),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_inherited_telegram_effects_preserved_and_consumed_migration_retired(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertTrue(TELEGRAM_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(TELEGRAM_EFFECTS <= set(m["contract"]["allowed_effects"]))
        self.assertNotIn(CONSUMED_MIGRATION_EFFECT,prior["allowed_effects"])
        self.assertNotIn(CONSUMED_MIGRATION_EFFECT,m["contract"]["allowed_effects"])
        self.assertEqual(adapter.ADDED_EFFECTS,{'application_revision_rollback:web:cee35f3b3bce38f7022c264d458d20b41823baf0'})
        self.assertEqual(adapter.REMOVED_FORBIDDEN_EFFECTS,set())
        self.assertEqual(adapter.ADDED_FORBIDDEN_EFFECTS,set())
        for effect in sorted(TELEGRAM_EFFECTS | adapter.ADDED_EFFECTS):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].remove(effect)
            with self.subTest(missing=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in (CONSUMED_MIGRATION_EFFECT,"database_migration","supabase_schema_migration:any",
                "automatic_purpose_approval","release_operator_farm_write","unbounded_purpose_reminders","reenable_delivered_url_notices"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            error = "effect_scope_conflict" if effect == "database_migration" else "approved_scope_delta_changed"
            with self.subTest(extra=effect),self.assertRaisesRegex(adapter.ReconciliationError,error):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        changed=deepcopy(m);changed["contract"]["forbidden_effects"].remove("database_migration")
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_overview_continuity_and_consumed_schema_history_cannot_be_weakened(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        clauses=m["contract"]["operational_acceptance"]
        self.assertEqual(len(clauses),102)
        self.assertTrue(all(0<len(v)<=2000 for v in clauses))
        guards=("consumed history and must not be replayed, extended or reversed",
            "Preserve its exact observed 18-kind or 19-kind target",
            "including the presence or absence of herdmaster_record_litter_weaning; never implicitly enable weaning",
            "Existing privileges, records, migration logs and other schema remain preserved",
            "Register exactly five release-metadata writes", "verified encrypted transport",
            "retaining additive schema and legitimate new claim/business history",
            "No unencrypted transport, down-migration, unrelated migration",
            "fresh mission preimages", "qualification-only and is never merged or deployed",
            "this exact manager CORE receipt intake, stopped/scoped startup source and existing-web-only release contract scope",
            "exact available membership, explicit current delivery state and verified dated deferrals",
            "only wholly delivered groups with no due request qualify",
            "New, changed, unnotified or due work retains history verification",
            "Count each bounded failure type and stage once",
            "a completed worker cycle does not prove healthy overview continuity")
        for guard_text in guards:
            changed=deepcopy(m)
            changed["contract"]["operational_acceptance"]=[v.replace(guard_text,"UNAUTHORIZED WEAKENING") for v in clauses]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],clauses,guard_text)
            with self.subTest(guard=guard_text),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        self.assertFalse(any(v.startswith("supabase_schema_migration:") for v in m["contract"]["allowed_effects"]))

    def test_ready_purpose_notice_effect_cannot_be_missing_or_broadened(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        changed=deepcopy(m);changed["contract"]["allowed_effects"].remove(PURPOSE_NOTICE_EFFECT)
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("ambiguous_purpose_notice_retry","manual_purpose_notice_trigger",
                       "automatic_purpose_change","unbounded_provider_retry","new_manager_schedule"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_condition_observation_preserves_fact_date_hold_and_confirmation_boundaries(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        effect="herdmaster_protected_body_condition_observation_intake"
        self.assertIn(effect, prior["allowed_effects"])
        self.assertNotIn(effect, adapter.ADDED_EFFECTS)
        self.assertIn(effect, m["contract"]["allowed_effects"])
        self.assertIn("farm_write", m["contract"]["forbidden_effects"])
        for before,after in (
                ("genuine current authenticated owner report", "synthetic engineering report"),
                ("finite nonboolean body-condition score", "any inferred score"),
                ("explicit observation date and date-only precision", "provider date and invented physical time"),
                ("reject missing, future, invalid or conflicting observation dates before claim creation", "accept any date after claim creation"),
                ("Prior read context, a score alone, a pronoun", "Any prior read context, score or pronoun"),
                ("exact bound current claim, preview digest, card and genuine confirmation", "any old card or release approval"),
                ("successful replay records no second observation", "replay may append another observation"),
                ("recovery_hold_action=not_recorded and no supersession", "recovery_hold_action=cleared and supersession"),
                ("preserve an earlier explicit active hold", "clear an earlier explicit active hold"),
                ("Reject extra protected-effect fields", "Accept extra protected-effect fields"),
                ("Registration remains exactly five canonical release-metadata writes", "Registration may write farm observations"),
                ("PR1373 read replies remain historical evidence", "PR1373 read replies prove the new protected outcome"),
                ("tests/test_herdmaster_breeding_exposure_recovery.py in Run canonical conversational follow-up gates", "optional grouped recovery examples"),
                ("tests/test_oom_sakkie_semantic_front_door.py in Run retained farrowing conversation gates", "optional semantic examples"),
                ("in Run HERDMASTER grouped breeding exposure transaction gates", "in an unqualified new lane"),
                ("tests/test_herdmaster_breeding_exposure_postgres.py with isolated PostgreSQL", "optional PostgreSQL examples")):
            changed=deepcopy(m);original=changed["contract"]["operational_acceptance"]
            changed["contract"]["operational_acceptance"]=[v.replace(before,after) for v in original]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],original,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        changed=deepcopy(m);changed["contract"]["allowed_effects"].remove(effect)
        with self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
            adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for unauthorized in ("implicit_recovery_clearance", "engineering_observation_recording", "condition_report_without_confirmation"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(unauthorized)
            with self.subTest(effect=unauthorized),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_breeding_overdue_followup_cannot_infer_dates_facts_or_question_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        for before,after in (
                ("supplied canonical packet's aware farm-date cutoff, never the wall clock", "the current wall clock"),
                ("Missing, naive, invalid, future-start or conflicting dates remain explicit uncertainty", "Incomplete dates imply overdue physical work"),
                ("does not prove current physical presence, removal, mating or pregnancy", "proves physical presence and pregnancy"),
                ("existing displayed task order and question priority", "new owner task ranking"),
                ("only for the supported exposure-only worklist", "for every worklist"),
                ("Do not replace a higher-priority condition question", "Replace any higher-priority condition question"),
                ("bounded source wording and an explicit omitted count", "invented explanations without source gaps"),
                ("earlier PR1372 replies remain historical evidence", "earlier PR1372 replies prove this release")):
            changed=deepcopy(m);original=changed["contract"]["operational_acceptance"]
            changed["contract"]["operational_acceptance"]=[v.replace(before,after) for v in original]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],original,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_owner_attention_presentation_cannot_invent_work_facts_or_authority(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertEqual(adapter.REMOVED_EFFECTS,{'application_revision_rollback:web:eb1afc7c91701683694d0bb104f02cd2fd0b3a54'})
        self.assertEqual(adapter.ADDED_EFFECTS,{'application_revision_rollback:web:cee35f3b3bce38f7022c264d458d20b41823baf0'})
        self.assertTrue(READINESS_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(READINESS_EFFECTS <= set(m["contract"]["allowed_effects"]))
        for before,after in (
                ("specialist already proves that exact animal due", "old coverage proves an animal due"),
                ("unavailable reconciliation cannot become a weighing instruction", "unavailable reconciliation permits reweighing"),
                ("Label full-register comparisons as full-register records", "Label all compared records as on-farm pigs"),
                ("without parsing specialist prose into new facts", "by parsing prose into inferred facts"),
                ("Recorded exposure does not confirm mating or pregnancy", "Recorded exposure confirms pregnancy"),
                ("owner review is not a missing physical observation", "owner review is a missing observation"),
                ("matching canonical case and current proposal fields", "similar remembered task"),
                ("uniquely displayed canonical subject", "any matching display alias"),
                ("condition questions retain the animal name and observation date requirement", "condition questions omit attribution"),
                ("Do not alter canonical evidence, material digests, stored answers, result hashes", "Rewrite stored answers and result hashes"),
                ("Previously delivered weighing and breeding answers remain historical evidence", "Previously delivered answers establish the new outcome"),
                ("tests/test_oom_sakkie_weighing_presentation.py", "optional weighing examples"),
                ("tests/test_oom_sakkie_breeding_plan_presentation.py", "optional breeding examples")):
            changed=deepcopy(m);original=changed["contract"]["operational_acceptance"]
            changed["contract"]["operational_acceptance"]=[v.replace(before,after) for v in original]
            self.assertNotEqual(changed["contract"]["operational_acceptance"],original,before)
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("presentation_inferred_weighing_instruction", "presentation_breeding_confirmation", "stored_answer_recomposition"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_retired_authority_does_not_leak_into_successor_but_history_is_preserved(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        prior=m["expected_child_record"]["metadata_json"]["mission_admission_contract"]
        self.assertNotIn(RETIRED_RENEWAL_EFFECT,prior["allowed_effects"])
        self.assertTrue(PRESENTATION_EFFECTS <= set(prior["allowed_effects"]))
        self.assertIn(CONTINUATION_EFFECT,prior["allowed_effects"])
        self.assertTrue(SUCCESSOR_EFFECTS <= set(prior["allowed_effects"]))
        self.assertTrue(SUCCESSOR_EFFECTS <= set(m["contract"]["allowed_effects"]))
        self.assertIn(CONTINUATION_EFFECT,m["contract"]["allowed_effects"])
        self.assertNotIn(RETIRED_RENEWAL_EFFECT,m["contract"]["allowed_effects"])
        self.assertTrue(PRESENTATION_EFFECTS <= set(m["contract"]["allowed_effects"]))
        retired_clauses=(
            "non-atomic concurrent source-cancellation fencing",
            "unchanged claim identity/expiry on retry",
            "unattempted expiry renewal remains once-only under existing guards",
            "This application does not recover historical ambiguous claims or grant another automatic expiry renewal.",
            "The qualification-only successor changes exactly the existing audit workflow and manager PostgreSQL tests",
        )
        for clause in retired_clauses:
            self.assertFalse(any(clause in value for value in m["contract"]["operational_acceptance"]))
            changed=deepcopy(m);changed["contract"]["operational_acceptance"].append(clause)
            self.assertEqual(len(changed["contract"]["operational_acceptance"]), 103)
            with self.subTest(retired_clause=clause),self.assertRaisesRegex(adapter.ReconciliationError,"contract_lists_invalid"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in (RETIRED_RENEWAL_EFFECT,"manual_unsent_claim_expiry_extension",
                       "automatic_pre_domain_mortality_execution","generic_future_candidate_release"):
            changed=deepcopy(m);changed["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(changed,a),connect_factory=lambda _:self.fail("unexpected connection"))
        before=self.snapshot(); result=apply(self.args,self.connect)
        self.assertEqual(result["writes"],5)
        event_id=adapter.prepare_reconciliation(**self.args)["event_id"]
        self.assertEqual(self.db.events[event_id][0]["previous_record"],before[0][adapter.MISSION_ID])
        self.assertEqual(self.db.rows[adapter.PARENT_ID],before[0][adapter.PARENT_ID])
        after=self.snapshot();self.assertEqual(apply(self.args,self.connect)["writes"],0)
        self.assertEqual(self.snapshot(),after)

    def test_successor_scope_refuses_missing_effects_and_unbounded_replacement(self):
        for effect in sorted(SUCCESSOR_EFFECTS | FARROWING_REVIEW_EFFECTS | FAMILY_STYLE_EFFECTS | CONCISE_BRIEF_EFFECTS | READINESS_EFFECTS):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            m["contract"]["allowed_effects"].remove(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        for effect in ("automatic_any_expired_claim_replacement", "terminal_farm_write",
                       "advisory_case_closure_from_absence", "unconfirmed_mortality_recording"):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            m["contract"]["allowed_effects"].append(effect)
            with self.subTest(effect=effect),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))

    def test_successor_scope_requires_exact_proof_audit_and_fresh_confirmation(self):
        changes = (
            ("locked case identity, evidence digest and generation", "similar animal label"),
            ("current canonical completion or lifecycle evidence", "missing refreshed candidate"),
            ("stable canonical sow and litter IDs", "matching display names"),
            ("existing original report text and original source time", "new guessed owner text"),
            ("Use no new AI call", "Use paid AI reassessment"),
            ("expired, active and claim_created", "any expired claim"),
            ("every delivery attempt, card, provider result and confirmation marker null", "current attempt marker null"),
            ("no earlier presentation, continuation, replacement, correction or renewal audit", "an earlier delivered card"),
            ("original private principal, original report, canonical pig and found_dead meaning must match", "a similar report is enough"),
            ("complete current canonical preview material must differ", "cached preview may match"),
            ("retained_mortality_orphan_replacement.v1", "unversioned_replacement"),
            ("change only its status to changed", "delete the old claim"),
            ("full old-claim audit plus source before/after evidence", "latest source alone"),
            ("retained_repreview.orphan_predecessor", "arbitrary_source_reference"),
            ("replacement event ID and predecessor claim hash", "a caller flag"),
            ("Retain both material digests without asserting equivalence", "Treat changed material as equivalent authority"),
            ("first orphan replacement preparation sends nothing", "first orphan replacement preparation sends immediately"),
            ("A later normal manager cycle", "A manual cron invocation"),
            ("The successor requires its own genuine confirmation", "The stale claim confirms the successor"),
            ("complete bounded source, claim, case, farm and provider history", "latest source only"),
            ("Cancelled, uncertain, attempted, confirmed, completed, competing or incomplete histories refuse replacement", "Any history permits replacement"),
            ("except the single audited never-attempted legacy orphan replacement defined here", "except any convenient renewal"),
        )
        for before,after in changes:
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            original=m["contract"]["operational_acceptance"]
            changed=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed,original,before)
            m["contract"]["operational_acceptance"]=changed
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,"approved_scope_delta_changed"):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail("unexpected connection"))
        clauses=json.loads(self.args["manifest_bytes"])["contract"]["operational_acceptance"]
        self.assertFalse(any("This read-routing repair" in value for value in clauses))
        self.assertFalse(any("this web-only HERDMASTER read-question routing repair scope" in value for value in clauses))
        self.assertFalse(any("must never create a new confirmation generation or automatically" in value for value in clauses))

    def test_scoped_read_repair_cannot_add_writes_unscoped_briefs_or_spend(self):
        for before,after in (
                ('explicit typed read capabilities','new prose-only write dispatch'),
                ('do not substitute a generic farm brief','substitute a generic farm brief'),
                ('Missing, malformed or unavailable evidence must remain an explicit gap','Unavailable evidence becomes zero'),
                ('Scope genuine HERDMASTER owner questions and supported physical tasks before presentation limits','Apply presentation limits before domain scoping'),
                ('adds no model call, confirmation bypass, direct farm mutation','may add model calls and unconfirmed mutations'),
                ('US$1 SAST-day OpenAI cap','unlimited OpenAI budget'),
                ('tests and hosted qualification alone are not owner acceptance','hosted tests prove all owner acceptance')):
            m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
            original=m['contract']['operational_acceptance']
            changed=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed,original,before)
            m['contract']['operational_acceptance']=changed
            with self.subTest(guard=before),self.assertRaisesRegex(adapter.ReconciliationError,'approved_scope_delta_changed'):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail('unexpected connection'))
        m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
        prior=m['expected_child_record']['metadata_json']['mission_admission_contract']
        self.assertIn(READ_QUERY_EFFECT,prior['allowed_effects'])
        self.assertIn(READ_QUERY_EFFECT,m['contract']['allowed_effects'])
        self.assertTrue(PRESENTATION_EFFECTS | PRESERVED_PREVIEW_EFFECTS | {CONTINUATION_EFFECT} <= set(m['contract']['allowed_effects']))
        self.assertFalse(any('this web-only expired-confirmation continuation scope' in x for x in m['contract']['operational_acceptance']))

    def test_cohort_qualification_cannot_weaken_concurrency_or_add_recovery(self):
        for before, after in (
                ('unique non-BEACON terminal findings', 'any missing finding'),
                ('every duplicate key', 'some duplicate keys'),
                ('30-second send reserve unchanged', 'shorter send reserve'),
                ('late results cannot send', 'late results may send'),
                ('consumed ordinary renewal and manual extension remain consumed',
                 'consumed ordinary renewal and manual extension may repeat')):
            m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
            original=m['contract']['operational_acceptance']
            changed=[value.replace(before,after) for value in original]
            self.assertNotEqual(changed,original)
            m['contract']['operational_acceptance']=changed
            with self.subTest(guard=before),self.assertRaisesRegex(
                    adapter.ReconciliationError,'approved_scope_delta_changed'):
                adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail('unexpected connection'))
        m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
        m['contract']['allowed_effects'].append('manual_unsent_claim_expiry_extension')
        with self.assertRaisesRegex(adapter.ReconciliationError,'approved_scope_delta_changed'):
            adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail('unexpected connection'))

    def test_predecessor_file_scope_is_exact_even_with_recomputed_record_digest(self):
        m,a=json.loads(self.args['manifest_bytes']),json.loads(self.args['approval_bytes'])
        child=m['expected_child_record']
        child['metadata_json']['mission_admission_contract']['allowed_files'].append('app.py')
        m['expected_child_sha256']=adapter.digest(adapter.canonical(child))
        with self.assertRaisesRegex(adapter.ReconciliationError,'predecessor_binding_invalid'):
            adapter.reconcile_candidate(**encode(m,a),connect_factory=lambda _:self.fail('unexpected connection'))

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
            (set(prior["forbidden_effects"]) - adapter.REMOVED_FORBIDDEN_EFFECTS) | adapter.ADDED_FORBIDDEN_EFFECTS)
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
        for field in ("pr", "head", "base", "branch", "paths", "status"):
            m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
            row=m["expected_child_record"];md=row["metadata_json"]
            packet,contract,admission=md["review_packet"],md["mission_admission_contract"],md["mission_admission"]
            if field=="pr":packet["pr_number"]=1343
            elif field=="head":packet["candidate_revision"]=admission["head_sha"]="b"*40
            elif field=="base":contract["base_sha"]=admission["base_sha"]="a"*40
            elif field=="branch":packet["branch_name"]=contract["branch"]="synthetic-other-branch"
            elif field=="paths":contract["allowed_files"]=PREDECESSOR_PATHS[:-1]
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
    def test_exact_candidate_allows_no_qualification_successor_or_path_drift(self):
        m,a=json.loads(self.args["manifest_bytes"]),json.loads(self.args["approval_bytes"])
        m["implementation"]["adapter_sha256"]=adapter.digest(Path(adapter.__file__).read_bytes())
        m["implementation"]["helper_files"]={p:adapter.digest((adapter.ROOT/p).read_bytes()) for p in adapter.HELPERS}
        plan=adapter.prepare_reconciliation(**encode(m,a))
        for name, value in FINAL_CANDIDATE_PINS.items():
            expected = SYNTHETIC_PINS[name] if value is None or value == [] else value
            self.assertEqual(getattr(adapter, name), expected)
        self.assertEqual(adapter.BASE,'cee35f3b3bce38f7022c264d458d20b41823baf0')
        self.assertEqual(adapter.BRANCH,'codex/core-manager-dependency-intake-20261006')
        self.assertEqual(adapter.APPROVED_RUNTIME_HEAD,adapter.HEAD)
        self.assertEqual(adapter.QUALIFICATION_TEST_PATHS,[])
        self.assertEqual(adapter.PREDECESSOR_PR,1387)
        self.assertEqual(adapter.PREDECESSOR_HEAD,'2604348ca98a0df4e351fa20a0c40f2d39da510f')
        self.assertEqual(adapter.PREDECESSOR_BASE,'eb1afc7c91701683694d0bb104f02cd2fd0b3a54')
        self.assertEqual(adapter.PREDECESSOR_BRANCH,'codex/manager-mortality-queue-priority-20261006')
        self.assertEqual(adapter.PREDECESSOR_PATHS,PREDECESSOR_PATHS)
        self.assertEqual(len(adapter.PREDECESSOR_PATHS),6)
        errors={"wrong_ancestor":"approved_runtime_ancestry_changed",
                "runtime_delta":"qualification_only_test_paths_changed",
                "test_delta":"qualification_only_test_paths_changed",
                "wrong_tree":"candidate_tree_changed", "extra_path":"candidate_paths_changed",
                "missing_runtime":"candidate_paths_changed", "wrong_patch":"candidate_diff_changed"}
        for case in ("valid",*errors):
            def git(command,**_):
                args=command[2:]
                if args==["rev-parse","origin/main"]:return (adapter.BASE+"\n").encode()
                if args==["diff","--name-only",adapter.BASE,"--"]:return b""
                if args==["ls-files","--others","--exclude-standard"]:return b""
                if args==["merge-base",adapter.APPROVED_RUNTIME_HEAD,adapter.HEAD]:
                    return (("a"*40 if case=="wrong_ancestor" else adapter.APPROVED_RUNTIME_HEAD)+"\n").encode()
                if args==["diff","--name-only",adapter.APPROVED_RUNTIME_HEAD,adapter.HEAD,"--"]:
                    return {"runtime_delta":b"modules/oom_sakkie/telegram_gateway.py\n",
                            "test_delta":b"tests/later.py\n"}.get(case,b"")
                if args==["rev-parse",adapter.HEAD+"^{tree}"]:
                    return (("a"*40 if case=="wrong_tree" else m["candidate"]["tree_sha"])+"\n").encode()
                if args==["diff","--name-only",adapter.BASE,adapter.HEAD,"--"]:
                    paths=list(adapter.PATHS)
                    if case=="extra_path":paths.append("app.py")
                    elif case=="missing_runtime":paths.pop(0)
                    return ("\n".join(sorted(paths))+"\n").encode()
                if args==["diff","--no-ext-diff","--no-textconv","--binary","--full-index",adapter.BASE,adapter.HEAD,"--"]:
                    return b"unreviewed candidate diff" if case=="wrong_patch" else b"synthetic candidate diff"
                self.fail("unexpected Git inspection: "+repr(args))
            with self.subTest(case=case),patch.object(adapter.subprocess,"check_output",side_effect=git):
                if case=="valid":adapter.verify_source_and_candidate(plan)
                else:
                    with self.assertRaisesRegex(adapter.ReconciliationError,errors[case]):
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
                -- Rebuild only this synthetic owned table so reused disposable
                -- databases cannot retain the formerly incomplete fixture.
                drop table if exists public.operational_events;
                create table if not exists public.operational_events (
                    event_id text primary key,
                    idempotency_key text not null unique,
                    schema_version text not null default '1',
                    event_type text not null,
                    domain text not null check (domain in ('leads','conversations','orders','payments','animals','campaigns','missions','incidents','approvals','outcomes')),
                    aggregate_type text not null,
                    aggregate_id text not null,
                    source_system text not null,
                    source_record_id text not null default '',
                    authority_tier text not null check (authority_tier in ('read','observe','draft','owner_approved','bounded_auto','red_zone')),
                    privacy_class text not null check (privacy_class in ('internal','owner_private','customer_personal','sensitive_business')),
                    actor_type text not null default 'system',
                    actor_id text not null default '',
                    correlation_id text not null default '',
                    causation_id text not null default '',
                    occurred_at timestamptz not null,
                    recorded_at timestamptz not null default now(),
                    freshness_at timestamptz not null,
                    payload_json jsonb not null,
                    provenance_json jsonb not null check (provenance_json ? 'source_ref'),
                    created_at timestamptz not null default now()
                );""")
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
