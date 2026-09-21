"""Synthetic qualification only; fixtures never represent Charl's approval."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import base64
import contextlib
import hashlib
import subprocess
import tempfile
from types import SimpleNamespace
import os
from pathlib import Path
import io
import unittest
from unittest.mock import patch

from modules.charlie import desktop_consolidation_registration as registration
from modules.charlie.mission_control import validate_mission_control_event
from modules.charlie import mission_store
from scripts import charlie_mission_admission_guard as guard
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from modules.charlie.mission_store import mission_runtime_eligible
from scripts import register_desktop_consolidation as cli
from modules.charlie.mission_admission import (
    canonical_candidate_diff, collision_snapshot_digest, sign_mission_admission_receipt,
    validate_mission_admission_receipt,
)
from scripts.charlie_mission_admission_guard import (
    _canonical_contract_for_pull, _build_exact_candidate_payload, _validate_paths_and_effects,
)

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
PRINCIPAL = "owner:synthetic-test-principal"


def fixture():
    text = "Synthetic owner fixture: prepare repository consolidation admission repair."
    manifest = {
        "version": registration.VERSION, "mission_id": registration.MISSION_ID,
        "task_id": registration.TASK_ID, "repository": registration.REPOSITORY,
        "expected_state": "absent", "idempotency_key": "synthetic-registration-1",
        "generation": "synthetic-desktop-registration-g1", "expires_at": "2026-09-20T13:00:00Z",
        "owner_instruction": {
            "owner_principal": PRINCIPAL, "task_id": registration.TASK_ID,
            "source_message_id": "synthetic-instruction-1", "evidence_ref": "test-fixture:instruction",
            "text": text, "text_sha256": registration.sha256(text.encode()),
            "issued_at": "2026-09-20T10:00:00Z",
        },
        "candidate": {"pr_number": 123, "branch": "codex/test-only-registration",
                      "base_sha": "a" * 40, "head_sha": "b" * 40, "tree_sha": "c" * 40,
                      "diff_sha256": "d" * 64,
                      "changed_files": list(registration.BOOTSTRAP_PATHS)},
        "implementation": {"revision": "b" * 40,
                           "files": {name: "e" * 64 for name in registration.IMPLEMENTATION_PATHS}},
        "required_tests": ["focused registration qualification", "mission-admission"],
        "test_evidence": [{"ref": "test-fixture:tests", "sha256": "f" * 64}],
        "review_evidence": [{"ref": "test-fixture:review", "sha256": "a" * 64}],
        "operational_acceptance": ["Separate admission and release; no business outcome authorized."],
    }
    approval = {
        "version": registration.VERSION, "decision": registration.DECISION,
        "approval_id": "synthetic-approval-1", "manifest_sha256": "", "owner_principal": PRINCIPAL,
        "task_id": registration.TASK_ID, "source_message_id": "synthetic-approval-message-1",
        "evidence_ref": "test-fixture:approval",
        "instruction_text": "Synthetic approval fixture: register this exact manifest paused only.",
        "issued_at": "2026-09-20T11:00:00Z", "expires_at": manifest["expires_at"],
    }
    return manifest, approval


def arguments(manifest=None, approval=None):
    default_manifest, default_approval = fixture()
    manifest = manifest if manifest is not None else default_manifest
    approval = deepcopy(approval if approval is not None else default_approval)
    raw = json.dumps(manifest, sort_keys=True).encode()
    approval["manifest_sha256"] = registration.sha256(raw)
    owner_raw = json.dumps(approval, sort_keys=True).encode()
    return {"manifest_bytes": raw, "expected_manifest_sha256": registration.sha256(raw),
            "approval_bytes": owner_raw, "expected_approval_sha256": registration.sha256(owner_raw),
            "now": NOW}


class TransactionFixture:
    """Model rollback semantics, explicitly not proof of PostgreSQL behavior."""
    def __init__(self):
        self.mission = None
        self.events = []
        self.operational_events = []
        self.executed = []
        self.commits = self.rollbacks = self.inserts = 0
        self.fail_on_event = ""
        self.corrupt_readback = False

    def __enter__(self):
        self.before = deepcopy((self.mission, self.events, self.operational_events))
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.mission, self.events, self.operational_events = self.before
            self.rollbacks += 1
        else:
            self.commits += 1
        return False

    def cursor(self):
        return CursorFixture(self)


class CursorFixture:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params=None):
        db = self.connection
        db.executed.append(sql)
        self.rows = []
        compact = " ".join(sql.split())
        if compact.startswith("select status,coalesce(metadata_json"):
            self.rows = [(db.mission["status"], deepcopy(db.mission["metadata_json"]), NOW)] if db.mission else []
        elif compact.startswith("select mission_id,status,coalesce(metadata_json"):
            self.rows = [(registration.MISSION_ID, db.mission["status"], deepcopy(db.mission["metadata_json"]), NOW)] if db.mission else []
        elif compact.startswith("select coalesce(metadata_json"):
            self.rows = [(deepcopy(db.mission["metadata_json"]),)] if db.mission else []
        elif "select event_id,metadata_json,recorded_by" in compact or "select event_id,coalesce(metadata_json" in compact:
            events = [event for event in db.events if event[1] == "owner_correction_recorded"]
            events.sort(key=lambda event: (event[3]["recorded_at"], event[0]), reverse=True)
            self.rows = [(events[0][0], deepcopy(events[0][3]), events[0][2])] if events else []
        elif compact.startswith("select metadata_json from public.charlie_mission_events"):
            self.rows = [(deepcopy(event[3]),) for event in db.events if event[0] == params[0]]
        elif compact.startswith("update public.charlie_missions"):
            value = params["metadata"] if isinstance(params, dict) else params[0]
            db.mission["metadata_json"] = json.loads(value)
        elif compact.startswith("insert into public.operational_events"):
            db.operational_events.append(deepcopy(params))
            self.rows = [(params["event_id"],)]
        elif sql.startswith("select ") and "from public.charlie_missions where" in sql:
            if db.mission:
                columns = sql.split(" from ")[0].removeprefix("select ").split(",")
                row = [db.mission[key] for key in columns]
                if db.corrupt_readback:
                    row[columns.index("status")] = "approved"
                self.rows = [tuple(row)]
        elif "select event_id,event_type,recorded_by,metadata_json" in sql:
            self.rows = sorted(deepcopy(db.events))
        elif "insert into public.charlie_missions" in sql:
            if db.mission:
                raise RuntimeError("duplicate primary key")
            db.mission = deepcopy(params)
            db.mission["metadata_json"] = json.loads(params["metadata_json"])
            db.inserts += 1
        elif "insert into public.charlie_mission_events" in sql:
            if params[2] == db.fail_on_event:
                raise RuntimeError("injected event failure")
            db.events.append((params[0], params[2], params[4], json.loads(params[5])))
            db.inserts += 1
        elif not (sql.startswith("set local ") or "pg_advisory_xact_lock" in sql):
            raise AssertionError("Unexpected SQL: " + sql)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return self.rows


class RegistrationTests(unittest.TestCase):
    def apply(self, db, **changes):
        args = arguments()
        args.update(changes)
        args.pop("now", None)
        with patch.object(registration, "verify_registration_source"), \
                patch.object(registration, "_utc_now", return_value=NOW):
            return registration.register_first_mission(**args, dry_run=False,
                authenticated_owner_principal=PRINCIPAL, connect_factory=lambda _: db)

    def test_default_dry_run_never_connects_or_authenticates_owner(self):
        result = registration.register_first_mission(**arguments(),
            connect_factory=lambda _: self.fail("dry-run accessed database"))
        self.assertEqual((result["status"], result["writes"]), ("dry_run", 0))
        self.assertTrue(result["plan"]["requires_independent_owner_authentication"])

    def test_first_create_stays_paused_and_non_runnable(self):
        db = TransactionFixture()
        result = self.apply(db)
        self.assertEqual((result["status"], db.commits, db.inserts), ("registered_paused", 1, 3))
        self.assertEqual(db.mission["status"], "paused")
        self.assertEqual(db.mission["approval_level"], "LEVEL 0")
        self.assertEqual(db.mission["source"], "codex_desktop")
        metadata = db.mission["metadata_json"]
        self.assertFalse(mission_runtime_eligible({"metadata": metadata}))
        self.assertNotIn("mission_admission", metadata)
        self.assertNotIn("dispatch_authorization", metadata)
        self.assertNotIn("hermes_native_execution", metadata)
        self.assertEqual(metadata["external_supervisor"]["task_id"], registration.TASK_ID)
        for event in db.events:
            self.assertEqual(event[2], PRINCIPAL)
            self.assertTrue(validate_mission_control_event(event[3])[0])
        self.assertFalse(any("update " in sql.lower() or "delete " in sql.lower() for sql in db.executed))

    def test_exact_replay_is_no_write(self):
        db = TransactionFixture()
        self.apply(db)
        first = deepcopy((db.mission, db.events))
        self.assertEqual(self.apply(db)["status"], "exact_replay")
        self.assertEqual((db.mission, db.events), first)
        self.assertEqual(db.inserts, 3)

    def test_any_prior_nonidentical_state_conflicts(self):
        for mutation in ("status", "metadata", "event", "extra_event"):
            with self.subTest(mutation=mutation):
                db = TransactionFixture()
                self.apply(db)
                if mutation == "status":
                    db.mission["status"] = "approved"
                elif mutation == "metadata":
                    db.mission["metadata_json"]["unrelated"] = True
                elif mutation == "event":
                    db.events.pop()
                else:
                    db.events.append(("other", "created", "other", {}))
                before = deepcopy((db.mission, db.events))
                with self.assertRaises(registration.RegistrationError):
                    self.apply(db)
                self.assertEqual((db.mission, db.events), before)
                self.assertEqual(db.inserts, 3)

    def test_changed_approval_cannot_replace_existing_registration(self):
        db = TransactionFixture()
        self.apply(db)
        manifest, approval = fixture()
        approval["approval_id"] = "different-synthetic-approval"
        with self.assertRaises(registration.RegistrationError):
            self.apply(db, **arguments(manifest, approval))
        self.assertEqual(db.inserts, 3)

    def test_correction_failure_rolls_back_first_mission_and_instruction(self):
        db = TransactionFixture()
        db.fail_on_event = "owner_correction_recorded"
        with self.assertRaisesRegex(RuntimeError, "event failure"):
            self.apply(db)
        self.assertIsNone(db.mission)
        self.assertEqual((db.events, db.commits, db.rollbacks), ([], 0, 1))

    def test_readback_corruption_rolls_back(self):
        db = TransactionFixture()
        db.corrupt_readback = True
        with self.assertRaises(registration.RegistrationError):
            self.apply(db)
        self.assertIsNone(db.mission)
        self.assertEqual(db.events, [])

    def test_authentication_is_required_before_connection(self):
        args = arguments()
        args.pop("now")
        with self.assertRaisesRegex(registration.RegistrationError, "authenticated_owner"):
            with patch.object(registration, "_utc_now", return_value=NOW):
                registration.register_first_mission(**args, dry_run=False,
                    authenticated_owner_principal="owner:someone-else",
                    connect_factory=lambda _: self.fail("unauthenticated connection"))

    def test_hash_mismatch_rejected_before_connection(self):
        args = arguments()
        args["expected_manifest_sha256"] = "0" * 64
        with self.assertRaisesRegex(registration.RegistrationError, "sha256_mismatch"):
            registration.register_first_mission(**args)

    def test_apply_itself_checks_source_before_database(self):
        args = arguments()
        args.pop("now")
        with patch.object(registration, "verify_registration_source",
                          side_effect=registration.RegistrationError("implementation_changed")) as verify, \
                patch.object(registration, "_utc_now", return_value=NOW):
            with self.assertRaisesRegex(registration.RegistrationError, "implementation_changed"):
                registration.register_first_mission(**args, dry_run=False,
                    authenticated_owner_principal=PRINCIPAL,
                    connect_factory=lambda _: self.fail("unpinned source reached database"))
        verify.assert_called_once()

    def test_apply_rejects_clock_override_and_autocommit(self):
        with self.assertRaisesRegex(registration.RegistrationError, "clock_override"):
            registration.register_first_mission(**arguments(), dry_run=False)
        db = TransactionFixture()
        db.autocommit = True
        with self.assertRaisesRegex(registration.RegistrationError, "transaction_required"):
            self.apply(db)
        self.assertEqual(db.inserts, 0)

    def test_invalid_scope_and_unfilled_template_fail_closed(self):
        for mutation in ("mission", "task", "repository", "expected_state", "pr", "unknown", "path", "tests"):
            with self.subTest(mutation=mutation):
                manifest, approval = fixture()
                if mutation in {"mission", "task", "repository", "expected_state"}:
                    key = {"mission": "mission_id", "task": "task_id"}.get(mutation, mutation)
                    manifest[key] = "unapproved"
                elif mutation == "pr":
                    manifest["candidate"]["pr_number"] = None
                elif mutation == "unknown":
                    manifest["metadata"] = {"mission_admission": {"status": "valid"}}
                elif mutation == "path":
                    manifest["candidate"]["changed_files"] = ["../escape"]
                else:
                    manifest["test_evidence"] = []
                with self.assertRaises(registration.RegistrationError):
                    registration.prepare_registration(**arguments(manifest, approval))

    def test_stale_future_and_long_lived_approval_fail_closed(self):
        for issued, expires in (("2026-09-20T10:30:00Z", "2026-09-20T11:00:00Z"),
                                ("2026-09-20T12:30:00Z", "2026-09-20T13:00:00Z"),
                                ("2026-09-20T11:00:00Z", "2026-09-22T13:00:00Z")):
            manifest, approval = fixture()
            manifest["expires_at"] = approval["expires_at"] = expires
            approval["issued_at"] = issued
            with self.assertRaisesRegex(registration.RegistrationError, "not_current"):
                registration.prepare_registration(**arguments(manifest, approval))

    def test_issuer_resolves_paused_desktop_packet_without_hermes(self):
        plan = registration.prepare_registration(**arguments())
        mission = dict(plan["params"])
        metadata = json.loads(mission.pop("metadata_json"))
        mission["metadata"] = metadata
        candidate = fixture()[0]["candidate"]
        with patch("scripts.charlie_mission_admission_guard.list_missions",
                   return_value=({"success": True, "missions": [mission]}, 200)):
            resolved = _canonical_contract_for_pull(candidate["pr_number"], candidate["base_sha"],
                candidate["head_sha"], candidate["branch"], candidate["diff_sha256"],
                candidate["changed_files"], "fixture-only")
        self.assertEqual(resolved[0]["status"], "paused")
        self.assertEqual(resolved[2], metadata["mission_admission_contract"])
        self.assertNotIn("hermes", json.dumps(metadata["external_supervisor"]))

    def test_cli_has_no_apply_or_database_argument(self):
        with patch("sys.stderr", new_callable=io.StringIO):
            with self.assertRaises(SystemExit) as exited:
                cli.main(["--apply"])
        self.assertEqual(exited.exception.code, 2)

    def test_real_issuer_payload_and_receipt_validator_accept_contract(self):
        plan = registration.prepare_registration(**arguments())
        mission = dict(plan["params"])
        metadata = json.loads(mission.pop("metadata_json"))
        candidate = fixture()[0]["candidate"]
        captured = "2026-09-20T11:00:00Z"
        authority = {"mission_id": registration.MISSION_ID, "root_mission_id": registration.MISSION_ID,
                     "latest_correction_digest": "1" * 64, "collision_observed_at": captured,
                     "active_claims": [], "collision_snapshot_sha256": collision_snapshot_digest(captured, [])}
        contract = metadata["mission_admission_contract"]
        payload = _build_exact_candidate_payload(mission=mission, family=metadata["mission_family"],
            authority=authority, contract=contract, base=candidate["base_sha"], head=candidate["head_sha"],
            branch=candidate["branch"], diff_sha256=candidate["diff_sha256"],
            changed_files=candidate["changed_files"], repository=registration.REPOSITORY,
            governance_reads=[{"path": "docs/example.md", "git_blob": "9" * 40,
                               "filesystem_sha256": "8" * 64, "byte_count": 1,
                               "physical_line_count": 1, "complete_byte_read": True}])
        # Synthetic bytes only; no installed/local/protected signing authority.
        key = b"synthetic-registration-validator-test-key"
        receipt = sign_mission_admission_receipt(payload, key, issued_at=captured,
                                                expires_at="2026-09-20T13:00:00Z")
        validated = validate_mission_admission_receipt(receipt, key,
            expected_mission_id=registration.MISSION_ID, expected_root_mission_id=registration.MISSION_ID,
            expected_generation=contract["generation"], expected_repository=registration.REPOSITORY,
            expected_base_sha=candidate["base_sha"], expected_head_sha=candidate["head_sha"],
            expected_changed_files=candidate["changed_files"], now=NOW)
        self.assertEqual(validated["receipt_id"], receipt["receipt_id"])
        for effect in ("repository_file_write", "repository_candidate_validation"):
            _validate_paths_and_effects(candidate["changed_files"], contract["allowed_files"],
                contract["forbidden_files"], effect, contract["allowed_effects"],
                contract["forbidden_effects"])
        self.assertFalse(payload["operational_acceptance"]["business_outcome_authorized"])

    def test_local_verifier_checks_all_pins(self):
        paths = registration.BOOTSTRAP_PATHS
        patch_bytes = b"synthetic full binary diff"
        source_bytes = b"synthetic implementation bytes"

        def run(case):
            manifest, _ = fixture()
            manifest["candidate"]["diff_sha256"] = canonical_candidate_diff(paths, patch_bytes)
            manifest["implementation"]["files"] = {
                path: registration.sha256(source_bytes) for path in registration.IMPLEMENTATION_PATHS}
            if case == "hash":
                manifest["implementation"]["files"][registration.IMPLEMENTATION_PATHS[0]] = "0" * 64
            if case == "implementation":
                manifest["implementation"]["revision"] = "a" * 40

            def git(*args):
                if args == ("rev-parse", "HEAD"):
                    return (("a" if case == "head" else "b") * 40).encode()
                if args[0] == "status":
                    return b" M modified.py" if case == "dirty" else b""
                if args[0] == "remote":
                    return ("https://github.com/" + ("wrong/repo" if case == "remote"
                            else registration.REPOSITORY) + ".git").encode()
                if args[0] == "rev-parse" and args[1].startswith("refs/heads/"):
                    return (("a" if case == "branch" else "b") * 40).encode()
                if args[0] == "rev-parse" and args[1].endswith("^{commit}"):
                    return args[1][:40].encode()
                if args[0] == "rev-parse" and args[1].endswith("^{tree}"):
                    return (("a" if case == "tree" else "c") * 40).encode()
                if args[:2] == ("diff", "--name-only"):
                    return ("\0".join(paths[:-1] if case == "scope" else paths) + "\0").encode()
                if args[0] == "diff":
                    return b"changed diff" if case == "diff" else patch_bytes
                if args[0] == "show":
                    return (b"changed" if case == "governance" and args[1].startswith("b" * 40)
                            else b"same governance")
                raise AssertionError(args)

            with patch.object(cli, "_git", side_effect=git), \
                    patch.object(Path, "read_bytes", return_value=source_bytes):
                cli.verify_local_candidate(manifest)

        run("valid")
        for case in ("implementation", "head", "dirty", "remote", "hash", "branch", "tree",
                     "scope", "diff", "governance"):
            with self.subTest(case=case), self.assertRaises(registration.RegistrationError):
                run(case)


def first_arguments():
    manifest, approval = fixture()
    manifest["candidate"]["pr_number"] = 1342
    return arguments(manifest, approval)


def apply_first(connect_factory):
    args = first_arguments()
    args.pop("now")
    with patch.object(registration, "verify_registration_source"), patch.object(registration, "_utc_now", return_value=NOW):
        return registration.register_first_mission(**args, dry_run=False,
            authenticated_owner_principal=PRINCIPAL, connect_factory=connect_factory)


def load_mission(connect_factory):
    with connect_factory("") as connection:
        row = connection.execute("select status,approval_level,source,metadata_json,raw_text from public.charlie_missions where mission_id=%s",
                                 (registration.MISSION_ID,)).fetchone() if hasattr(connection, "execute") else None
        if row is None:
            with connection.cursor() as cursor:
                cursor.execute("select status,approval_level,source,metadata_json,raw_text from public.charlie_missions where mission_id=%s", (registration.MISSION_ID,))
                row = cursor.fetchone()
    return {"mission_id": registration.MISSION_ID, "status": row[0], "approval_level": row[1],
            "source": row[2], "metadata": deepcopy(row[3]), "raw_text": row[4]}


def successor_arguments(connect_factory):
    mission = load_mission(connect_factory)
    metadata = mission["metadata"]
    authority, status = mission_store.read_current_mission_admission_authority(
        registration.MISSION_ID, connect_factory=connect_factory)
    assert status == 200
    previous = metadata["mission_admission"]
    manifest, approval = fixture()
    manifest.pop("expected_state")
    manifest.update({"version": registration.SUCCESSION_VERSION,
        "idempotency_key": "synthetic-succession-1", "generation": "synthetic-consolidation-g2",
        "predecessor": {"metadata_sha256": registration.sha256(registration._json_bytes(metadata)),
            "registration_manifest_sha256": metadata["desktop_first_registration"]["manifest_sha256"],
            "registration_approval_sha256": metadata["desktop_first_registration"]["approval_sha256"],
            "correction_event_id": authority["latest_owner_correction_event_id"],
            "correction_sha256": authority["latest_correction_digest"], "pr_number": 1342,
            "admission_status": previous["status"],
            **{key: previous[key] for key in ("generation", "head_sha", "receipt_id", "content_sha256")}},
        "candidate": {"pr_number": 1341, "branch": registration.SUCCESSOR_BRANCH,
            "base_sha": "d" * 40, "head_sha": "c" * 40, "tree_sha": "f" * 40,
            "changed_files": ["README.md"],
            "diff_sha256": canonical_candidate_diff(["README.md"], b"synthetic candidate patch")},
        "implementation": {"revision": "d" * 40,
            "files": {name: "e" * 64 for name in registration.IMPLEMENTATION_PATHS}},
        "merge_evidence": {"repository": registration.REPOSITORY, "pr_number": 1342,
            "head_sha": "b" * 40, "merge_sha": "e" * 40, "main_sha": "d" * 40, "base_ref": "main",
            "merged_at": "2026-09-20T11:20:00Z", "observed_at": "2026-09-20T11:30:00Z",
            "evidence_ref": "test-fixture:merged-pr", "evidence_sha256": "f" * 64}})
    approval.update({"version": registration.SUCCESSION_VERSION, "decision": registration.SUCCESSION_DECISION,
        "approval_id": "synthetic-successor-approval", "issued_at": "2026-09-20T11:45:00Z",
        "instruction_text": "Synthetic approval: retire merged predecessor and bind exact PR1341 paused."})
    return arguments(manifest, approval)


def apply_successor(args, connect_factory, **overrides):
    options = dict(args)
    options.pop("now", None)
    manifest = json.loads(options["manifest_bytes"])
    options.update({"dry_run": False, "authenticated_owner_principal": PRINCIPAL,
        "verified_merge_evidence": dict(manifest["merge_evidence"], checked_at=NOW.isoformat()),
        "connect_factory": connect_factory})
    options.update(overrides)
    with patch.object(registration, "verify_successor_source"), patch.object(registration, "_utc_now", return_value=NOW):
        return registration.bind_successor(**options)


def issue_with_store(test, connect_factory, candidate):
    """Actual resolver, authority reader, signing and store callback; synthetic I/O."""
    seed = hashlib.sha256(b"synthetic-successor-signing-key").digest()
    key = b"synthetic-successor-validation-key"
    public = base64.b64encode(Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    pull = {"state": "open", "merged_at": None, "body": "Synthetic test PR.",
        "base": {"ref": "main", "sha": candidate["base_sha"]},
        "head": {"ref": candidate["branch"], "sha": candidate["head_sha"]}}
    callbacks = []
    def github(_number, _token, body=None):
        if body is not None:
            pull["body"] = body
        return deepcopy(pull)
    def current(_mission, **_kwargs):
        return mission_store.read_current_mission_admission_authority(registration.MISSION_ID, connect_factory=connect_factory)
    def listing(**_kwargs):
        return {"success": True, "missions": [load_mission(connect_factory)]}, 200
    class Response:
        status = 201
        def __enter__(self): return self
        def __exit__(self, *_): return False
    def callback(request, **_kwargs):
        data = json.loads(request.data)
        receipt, _ = guard._validate_external_receipt_envelope(data["envelope"],
            expected_repository=registration.REPOSITORY, expected_base_sha=candidate["base_sha"],
            expected_head_sha=candidate["head_sha"], expected_changed_files=candidate["changed_files"])
        metadata = load_mission(connect_factory)["metadata"]
        guard._require_canonical_review_linkage(metadata, candidate["pr_number"], candidate["head_sha"],
            candidate["branch"], candidate["diff_sha256"], candidate["changed_files"])
        projection = {"receipt_id": receipt["receipt_id"], "content_sha256": receipt["content_sha256"],
            "mission_id": registration.MISSION_ID, "root_mission_id": registration.MISSION_ID,
            "generation": receipt["mission"]["generation"], "base_sha": candidate["base_sha"],
            "head_sha": candidate["head_sha"], "authority_key_sha256": receipt["authority_key_sha256"],
            "latest_correction_digest": receipt["owner_instruction_chain"]["latest_correction_digest"],
            "collision_snapshot_sha256": receipt["collision_snapshot"]["snapshot_sha256"], "signed_receipt": receipt}
        result, status = mission_store.append_mission_admission_event(registration.MISSION_ID, projection,
            authenticated_principal="control_tower_isolated_validator_v2", connect_factory=connect_factory)
        test.assertLess(status, 400, result)
        callbacks.append(receipt)
        return Response()
    output = io.StringIO()
    with patch.object(guard, "_protected_database_url", return_value="synthetic-readonly"), \
         patch.object(guard, "_github_pull_request", side_effect=github), \
         patch.object(guard, "_repository_identity", return_value=registration.REPOSITORY), \
         patch.object(guard, "subprocess") as process, \
         patch.object(guard, "_commit", side_effect=lambda sha: sha), \
         patch.object(guard, "_changed_files", return_value=candidate["changed_files"]), \
         patch.object(guard, "_git_bytes", side_effect=lambda *args: b"g\n" if args[0] == "show" else b"synthetic candidate patch"), \
         patch.object(guard, "_git_text", return_value=candidate["head_sha"]), \
         patch.object(guard, "_governance_read_identities", return_value=[{
             "path": "docs/governance.md", "git_blob": candidate["head_sha"], "filesystem_sha256": hashlib.sha256(b"g\n").hexdigest(),
             "byte_count": 2, "physical_line_count": 1, "complete_byte_read": True}]), \
         patch.object(guard, "list_missions", side_effect=listing), \
         patch.object(guard, "get_mission", side_effect=lambda *_args, **_kwargs: ({"success": True, "mission": load_mission(connect_factory)}, 200)), \
         patch.object(guard, "read_current_mission_admission_authority", side_effect=current), \
         patch.object(guard.url_request, "urlopen", side_effect=callback), \
         patch.object(guard, "EXTERNAL_ADMISSION_PUBLIC_KEY_B64", public), contextlib.redirect_stdout(output):
        code = guard.issue_pr_main(SimpleNamespace(pull_request_number=candidate["pr_number"],
            expected_head_sha=candidate["head_sha"], event_output=None), environ={
                "GITHUB_TOKEN": "synthetic-token", "CHARLIE_CANONICAL_API_URL": "https://canonical.invalid",
                "CHARLIE_VALIDATION_RECEIPT_KEY_B64": base64.b64encode(key).decode(),
                "CHARLIE_ADMISSION_RECEIPT_SIGNING_KEY_B64": base64.b64encode(seed).decode()})
        test.assertEqual(code, 0, output.getvalue())
        test.assertEqual(process.run.call_count, 1)
        # Exercise the real trusted-check path using the just-issued envelope,
        # real canonical readback, and candidate governance byte verification.
        event = {"number": candidate["pr_number"], "repository": {"full_name": registration.REPOSITORY},
                 "pull_request": deepcopy(pull)}
        with tempfile.TemporaryDirectory() as directory:
            event_path = Path(directory) / "trusted-event.json"
            event_path.write_text(json.dumps(event), encoding="utf-8")
            with patch.object(guard, "_app_check_request", return_value={"id": 42}) as publish:
                test.assertEqual(guard.trusted_check_main(SimpleNamespace(event=str(event_path)),
                    environ={"CHARLIE_ADMISSION_APP_TOKEN": "synthetic-app-token"}), 0, output.getvalue())
                test.assertEqual(publish.call_args.args[2]["conclusion"], "success")
        test.assertEqual(process.run.call_count, 2)
        test.assertTrue(all(call.args[0][:2] == ["git", "-c"] for call in process.run.call_args_list))
    metadata = load_mission(connect_factory)["metadata"]
    receipt = metadata["mission_admission"]["signed_receipt"]
    authority, _ = current(registration.MISSION_ID)
    guard._compare_current_authority(receipt, authority, metadata["mission_admission_contract"])
    return receipt, callbacks


def receipt_projection(receipt):
    return {"receipt_id": receipt["receipt_id"], "content_sha256": receipt["content_sha256"],
            "mission_id": receipt["mission"]["mission_id"], "root_mission_id": receipt["mission"]["root_mission_id"],
            "generation": receipt["mission"]["generation"], "base_sha": receipt["repository"]["base_sha"],
            "head_sha": receipt["candidate"]["head_sha"], "authority_key_sha256": receipt["authority_key_sha256"],
            "latest_correction_digest": receipt["owner_instruction_chain"]["latest_correction_digest"],
            "collision_snapshot_sha256": receipt["collision_snapshot"]["snapshot_sha256"], "signed_receipt": receipt}


def append_receipt(receipt, connect):
    return mission_store.append_mission_admission_event(registration.MISSION_ID, receipt_projection(receipt),
        authenticated_principal="control_tower_isolated_validator_v2", connect_factory=connect)


def protected_callback(test, connect, receipt, pr_number, *, stale_mission=None, stale_authority=None):
    """Actual HTTP route, signed envelope and locked store; no provider I/O."""
    from flask import Flask
    from modules.charlie import routes
    key = Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"synthetic-successor-signing-key").digest())
    public = base64.b64encode(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()
    envelope = {"version": "mission_admission_ci_envelope_v1", "receipt": receipt,
                "signature_ed25519": base64.b64encode(key.sign(guard.canonical_json(receipt))).decode()}
    app = Flask(__name__); app.register_blueprint(routes.charlie_bp)
    authority = stale_authority or mission_store.read_current_mission_admission_authority(registration.MISSION_ID, connect_factory=connect)[0]
    with patch.object(guard, "EXTERNAL_ADMISSION_PUBLIC_KEY_B64", public), \
         patch.object(routes, "get_mission", return_value=({"mission": stale_mission or load_mission(connect)}, 200)), \
         patch.object(routes, "read_current_mission_admission_authority", return_value=(authority, 200)), \
         patch.object(routes, "append_mission_admission_event", side_effect=lambda mission, admission, **kwargs:
             mission_store.append_mission_admission_event(mission, admission, connect_factory=connect, **kwargs)), \
         patch.object(routes, "invalidate_external_candidate_admission") as invalidate, \
         patch.object(routes, "bind_external_supervisor_candidate") as bind, \
         patch.object(routes.urllib.request, "urlopen") as provider:
        response = app.test_client().post(f"/charlie/hermes/missions/{registration.MISSION_ID}/protected-admission",
                                          json={"envelope": envelope, "pr_number": pr_number})
    invalidate.assert_not_called(); bind.assert_not_called(); provider.assert_not_called()
    return response


def registered_and_issued(test, connect_factory):
    args = first_arguments()
    manifest, approval = json.loads(args["manifest_bytes"]), json.loads(args["approval_bytes"])
    manifest["candidate"]["diff_sha256"] = canonical_candidate_diff(manifest["candidate"]["changed_files"], b"synthetic candidate patch")
    args = arguments(manifest, approval)
    options = dict(args); options.pop("now")
    with patch.object(registration, "verify_registration_source"), patch.object(registration, "_utc_now", return_value=NOW):
        registration.register_first_mission(**options, dry_run=False,
            authenticated_owner_principal=PRINCIPAL, connect_factory=connect_factory)
    return issue_with_store(test, connect_factory, manifest["candidate"])[0]


class SuccessionTests(unittest.TestCase):
    def setUp(self):
        self.db = TransactionFixture()
        self.connect = lambda _: self.db
        self.old_receipt = registered_and_issued(self, self.connect)
        self.args = successor_arguments(self.connect)

    def test_actual_issuer_chain_and_replay_preserve_history_and_new_receipt(self):
        before = deepcopy(self.db.mission["metadata_json"])
        original_events = deepcopy(self.db.events)
        result = apply_successor(self.args, self.connect)
        self.assertEqual(result["status"], "successor_bound_paused")
        metadata = self.db.mission["metadata_json"]
        self.assertNotIn("mission_admission", metadata)
        self.assertEqual(self.db.events[:2], original_events)
        history = next(event[3] for event in self.db.events if event[1] == "workflow_updated")
        self.assertEqual(history["previous_metadata"], before)
        self.assertEqual(history["retired_admission"]["status"], "consumed")
        self.assertEqual(history["retired_admission"]["consumed_at"], NOW.isoformat())
        with self.assertRaisesRegex(guard.MissionAdmissionError, "admission_consumed"):
            guard._require_exact_admission_projection(
                {"admission": history["retired_admission"], "root_mission_id": registration.MISSION_ID},
                {"mission_id": registration.MISSION_ID}, before["mission_family"], "a" * 40, "b" * 40, "1" * 64)
        candidate = json.loads(self.args["manifest_bytes"])["candidate"]
        new_receipt, callbacks = issue_with_store(self, self.connect, candidate)
        self.assertEqual(len(callbacks), 1)
        self.assertNotEqual(new_receipt["receipt_id"], self.old_receipt["receipt_id"])
        snapshot = deepcopy((self.db.mission, self.db.events, self.db.operational_events))
        self.assertEqual(apply_successor(self.args, self.connect)["status"], "exact_replay")
        self.assertEqual((self.db.mission, self.db.events, self.db.operational_events), snapshot)
        self.assertEqual(issue_with_store(self, self.connect, candidate)[1], [])
        self.assertEqual(self.db.mission["status"], "paused")
        self.assertFalse(mission_runtime_eligible(load_mission(self.connect)))
        authority, _ = mission_store.read_current_mission_admission_authority(registration.MISSION_ID, connect_factory=self.connect)
        with self.assertRaises(guard.MissionAdmissionError):
            guard._compare_current_authority(self.old_receipt, authority, self.db.mission["metadata_json"]["mission_admission_contract"])

    def test_late_callback_store_and_route_cannot_restore_or_invalidate_old_receipt(self):
        stale_mission = load_mission(self.connect)
        stale_authority = mission_store.read_current_mission_admission_authority(registration.MISSION_ID, connect_factory=self.connect)[0]
        apply_successor(self.args, self.connect)
        candidate = json.loads(self.args["manifest_bytes"])["candidate"]
        for issued in (False, True):
            if issued:
                new_receipt, _ = issue_with_store(self, self.connect, candidate)
            snapshot = deepcopy((self.db.mission, self.db.events, self.db.operational_events))
            result, status = append_receipt(self.old_receipt, self.connect)
            self.assertEqual((status, result["status"]), (409, "mission_admission_candidate_mismatch"))
            self.assertEqual(protected_callback(self, self.connect, self.old_receipt, 1342).status_code, 409)
            # Simulate the request having passed all pre-lock checks before succession.
            raced = protected_callback(self, self.connect, self.old_receipt, 1342,
                stale_mission=stale_mission, stale_authority=stale_authority)
            self.assertEqual((raced.status_code, raced.json["status"]), (409, "mission_admission_candidate_mismatch"))
            if issued:
                self.assertEqual(protected_callback(self, self.connect, new_receipt, 1342).status_code, 409)
                self.assertEqual(protected_callback(self, self.connect, new_receipt, 1341).status_code, 200)
            self.assertEqual((self.db.mission, self.db.events, self.db.operational_events), snapshot)

    def test_store_replay_requires_exact_payload_and_cannot_reactivate_consumed_receipt(self):
        original = deepcopy((self.db.mission, self.db.events, self.db.operational_events))
        changed = receipt_projection(self.old_receipt)
        changed["content_sha256"] = "0" * 64
        result, status = mission_store.append_mission_admission_event(registration.MISSION_ID, changed,
            authenticated_principal="control_tower_isolated_validator_v2", connect_factory=self.connect)
        self.assertEqual((status, result["status"]), (409, "mission_admission_conflict"))
        self.assertEqual((self.db.mission, self.db.events, self.db.operational_events), original)
        mission_store.consume_mission_admission(registration.MISSION_ID, self.old_receipt["receipt_id"],
            authenticated_principal="consumer", connect_factory=self.connect)
        consumed = deepcopy((self.db.mission, self.db.events, self.db.operational_events))
        result, status = append_receipt(self.old_receipt, self.connect)
        self.assertEqual((status, result["status"]), (409, "mission_admission_retired"))
        self.assertEqual((self.db.mission, self.db.events, self.db.operational_events), consumed)

    def test_already_consumed_predecessor_can_be_retired_without_reactivation(self):
        result, status = mission_store.consume_mission_admission(registration.MISSION_ID,
            self.old_receipt["receipt_id"], authenticated_principal="synthetic-original-consumer", connect_factory=self.connect)
        self.assertLess(status, 400, result)
        consumed = deepcopy(self.db.mission["metadata_json"]["mission_admission"])
        args = successor_arguments(self.connect)
        self.assertEqual(apply_successor(args, self.connect)["status"], "successor_bound_paused")
        history = next(event[3] for event in self.db.events if event[1] == "workflow_updated")
        self.assertEqual(history["retired_admission"], consumed)
        self.assertNotIn("mission_admission", self.db.mission["metadata_json"])

    def test_predecessor_drift_and_active_effects_fail_without_mutation(self):
        for field in ("status", "receipt", "metadata", "lease", "supervisor"):
            with self.subTest(field=field):
                saved = deepcopy(self.db.mission)
                if field == "status": self.db.mission["status"] = "approved"
                elif field == "receipt": self.db.mission["metadata_json"]["mission_admission"]["receipt_id"] = "MAR-" + "0" * 64
                elif field == "metadata": self.db.mission["metadata_json"]["unrelated"] = "concurrent change"
                elif field == "lease": self.db.mission["metadata_json"]["execution_lease"] = {"lease_id": "active"}
                else: self.db.mission["metadata_json"]["external_supervisor"]["transport"] = "hermes_cursor_cloud_v1"
                before = deepcopy((self.db.mission, self.db.events))
                with self.assertRaises(registration.RegistrationError): apply_successor(self.args, self.connect)
                self.assertEqual((self.db.mission, self.db.events), before)
                self.db.mission = saved

    def test_correction_failure_rolls_back_packet_receipt_and_history(self):
        before = deepcopy((self.db.mission, self.db.events))
        self.db.fail_on_event = "owner_correction_recorded"
        with self.assertRaisesRegex(RuntimeError, "event failure"):
            apply_successor(self.args, self.connect)
        self.assertEqual((self.db.mission, self.db.events), before)

    def test_changed_replay_is_rejected_and_no_second_transition_exists(self):
        apply_successor(self.args, self.connect)
        manifest, approval = json.loads(self.args["manifest_bytes"]), json.loads(self.args["approval_bytes"])
        approval["approval_id"] = "changed-replay"
        with self.assertRaisesRegex(registration.RegistrationError, "replay_conflict"):
            apply_successor(arguments(manifest, approval), self.connect)

    def test_authentication_merge_verification_and_source_pins_precede_connection(self):
        def forbidden(_): self.fail("invalid authority reached database")
        for changes in ({"authenticated_owner_principal": "owner:other"}, {"verified_merge_evidence": {}},
                        {"verified_merge_evidence": dict(json.loads(self.args["manifest_bytes"])["merge_evidence"], checked_at="2026-09-20T11:00:00Z")}):
            with self.subTest(changes=changes), self.assertRaises(registration.RegistrationError):
                apply_successor(self.args, forbidden, **changes)
        options = dict(self.args); options.pop("now")
        with patch.object(registration, "_utc_now", return_value=NOW), \
             patch.object(registration, "verify_successor_source", side_effect=registration.RegistrationError("source_changed")):
            with self.assertRaisesRegex(registration.RegistrationError, "source_changed"):
                registration.bind_successor(**options, dry_run=False, authenticated_owner_principal=PRINCIPAL,
                    verified_merge_evidence=dict(json.loads(options["manifest_bytes"])["merge_evidence"], checked_at=NOW.isoformat()),
                    connect_factory=forbidden)

    def test_dry_run_and_invalid_scope_clock_fail_before_database(self):
        self.assertFalse(registration.bind_successor(**self.args)["database_accessed"])
        for key, value in (("pr_number", 1340), ("branch", "codex/other"), ("base_sha", "a" * 40)):
            manifest, approval = json.loads(self.args["manifest_bytes"]), json.loads(self.args["approval_bytes"])
            manifest["candidate"][key] = value
            with self.subTest(key=key), self.assertRaises(registration.RegistrationError):
                registration.prepare_successor(**arguments(manifest, approval))
        with self.assertRaisesRegex(registration.RegistrationError, "clock_override"):
            registration.bind_successor(**self.args, dry_run=False)
        self.db.autocommit = True
        with self.assertRaisesRegex(registration.RegistrationError, "transaction_required"):
            apply_successor(self.args, self.connect)

    def test_successor_verifier_uses_main_code_and_inert_candidate_with_preserved_ancestry(self):
        manifest = json.loads(self.args["manifest_bytes"])
        source = b"synthetic protected-main implementation"
        manifest["implementation"]["files"] = {path: registration.sha256(source) for path in registration.IMPLEMENTATION_PATHS}
        seen = []
        def run(case):
            def git(*args):
                seen.append(args)
                if args[0] == "status": return b" M dirty.py" if case == "dirty" else b""
                if args[0] == "remote": return ("https://github.com/" + registration.REPOSITORY).encode()
                if args[:2] == ("merge-base", "--is-ancestor"):
                    if case == "ancestry": raise subprocess.CalledProcessError(1, ["git", *args])
                    return b""
                if args[0] == "rev-parse":
                    ref = args[1]
                    if ref in {"HEAD", "refs/remotes/origin/main"}: return (("c" if case == "candidate_execution" else "d") * 40).encode()
                    if ref.startswith("refs/heads/"): return ("c" * 40).encode()
                    if ref.endswith("^{tree}"): return ("f" * 40).encode()
                    return ref[:40].encode()
                if args[:2] == ("diff", "--name-only"):
                    return b"other.py\0" if case == "scope" and args[3] == "d" * 40 else b"README.md\0"
                if args[0] == "diff": return b"changed" if case == "diff" else b"synthetic candidate patch"
                raise AssertionError(args)
            with patch.object(cli, "_git", side_effect=git), patch.object(Path, "read_bytes", return_value=source):
                cli.verify_local_successor(manifest)
        run("valid")
        for case in ("dirty", "ancestry", "candidate_execution", "scope", "diff"):
            with self.subTest(case=case), self.assertRaises(registration.RegistrationError): run(case)
        self.assertTrue(all(args[0] in {"rev-parse", "status", "remote", "merge-base", "diff"} for args in seen))


@unittest.skipUnless(os.environ.get("CHARLIE_DESKTOP_REGISTRATION_TEST_DATABASE_URL"),
                     "isolated desktop_registration_test PostgreSQL URL required")
class RegistrationPostgresTests(unittest.TestCase):
    """Real transaction proof, only in an explicitly supplied disposable DB."""
    @classmethod
    def setUpClass(cls):
        import psycopg
        cls.psycopg = psycopg
        cls.url = os.environ["CHARLIE_DESKTOP_REGISTRATION_TEST_DATABASE_URL"]
        with psycopg.connect(cls.url) as connection:
            name = connection.execute("select current_database()").fetchone()[0]
            if not name.startswith("desktop_registration_test"):
                raise unittest.SkipTest("refusing a non-disposable database name")
            connection.execute("""create table if not exists public.charlie_missions (
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
        with self.psycopg.connect(self.url) as connection:
            connection.execute("alter table public.charlie_mission_events drop constraint if exists reject_correction")
            connection.execute("alter table public.charlie_mission_events drop constraint if exists reject_successor")
            connection.execute("delete from public.operational_events where aggregate_id=%s", (registration.MISSION_ID,))
            connection.execute("delete from public.charlie_mission_events where mission_id=%s", (registration.MISSION_ID,))
            connection.execute("delete from public.charlie_missions where mission_id=%s", (registration.MISSION_ID,))

    def apply(self):
        # DB tests isolate transactional semantics; source-pinning has separate tests.
        args = arguments()
        args.pop("now")
        with patch.object(registration, "verify_registration_source"), \
                patch.object(registration, "_utc_now", return_value=NOW):
            return registration.register_first_mission(**args, dry_run=False,
                authenticated_owner_principal=PRINCIPAL, database_url=self.url)

    def test_real_create_and_exact_replay(self):
        self.assertEqual(self.apply()["status"], "registered_paused")
        self.assertEqual(self.apply()["status"], "exact_replay")
        with self.psycopg.connect(self.url) as connection:
            row = connection.execute("select status,metadata_json from public.charlie_missions where mission_id=%s",
                                     (registration.MISSION_ID,)).fetchone()
            count = connection.execute("select count(*) from public.charlie_mission_events where mission_id=%s",
                                       (registration.MISSION_ID,)).fetchone()[0]
        self.assertEqual((row[0], count), ("paused", 2))
        self.assertNotIn("mission_admission", row[1])
        self.assertFalse(mission_runtime_eligible({"metadata": row[1]}))

    def test_real_event_constraint_failure_rolls_back_every_insert(self):
        with self.psycopg.connect(self.url) as connection:
            connection.execute("alter table public.charlie_mission_events add constraint reject_correction "
                               "check(event_type <> 'owner_correction_recorded')")
        with self.assertRaises(self.psycopg.Error):
            self.apply()
        with self.psycopg.connect(self.url) as connection:
            missions = connection.execute("select count(*) from public.charlie_missions where mission_id=%s",
                                          (registration.MISSION_ID,)).fetchone()[0]
            events = connection.execute("select count(*) from public.charlie_mission_events where mission_id=%s",
                                        (registration.MISSION_ID,)).fetchone()[0]
        self.assertEqual((missions, events), (0, 0))


    def snapshot(self):
        with self.psycopg.connect(self.url) as connection:
            mission = connection.execute("select status,approval_level,metadata_json from public.charlie_missions where mission_id=%s",
                                         (registration.MISSION_ID,)).fetchone()
            events = connection.execute("select event_id,metadata_json from public.charlie_mission_events where mission_id=%s order by event_id",
                                        (registration.MISSION_ID,)).fetchall()
            admissions = connection.execute("select event_id,payload_json from public.operational_events where aggregate_id=%s order by event_id",
                                            (registration.MISSION_ID,)).fetchall()
        return mission, events, admissions

    def test_real_first_registration_issuer_succession_new_issuer_and_replay(self):
        connect = lambda _: self.psycopg.connect(self.url)
        original = registered_and_issued(self, connect)
        args = successor_arguments(connect)
        before = self.snapshot()
        self.assertEqual(apply_successor(args, connect)["status"], "successor_bound_paused")
        self.assertNotIn("mission_admission", load_mission(connect)["metadata"])
        after_transition = self.snapshot()
        result, status = append_receipt(original, connect)
        self.assertEqual((status, result["status"]), (409, "mission_admission_candidate_mismatch"))
        self.assertEqual(protected_callback(self, connect, original, 1342).status_code, 409)
        self.assertEqual(self.snapshot(), after_transition)
        candidate = json.loads(args["manifest_bytes"])["candidate"]
        successor, callbacks = issue_with_store(self, connect, candidate)
        self.assertEqual(len(callbacks), 1)
        self.assertNotEqual(original["receipt_id"], successor["receipt_id"])
        after = self.snapshot()
        self.assertEqual(append_receipt(original, connect)[1], 409)
        self.assertEqual(protected_callback(self, connect, original, 1342).status_code, 409)
        self.assertEqual(protected_callback(self, connect, successor, 1341).status_code, 200)
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(after[0][:2], ("paused", "LEVEL 0"))
        self.assertEqual((len(after[1]), len(after[2])), (4, 2))
        history = next(event[1] for event in after[1] if event[0].startswith("DESKTOP-SUCCESSION-"))
        self.assertEqual(history["previous_metadata"], before[0][2])
        self.assertEqual(history["retired_admission"]["status"], "consumed")
        self.assertEqual(apply_successor(args, connect)["status"], "exact_replay")
        self.assertEqual(self.snapshot(), after)
        self.assertEqual(issue_with_store(self, connect, candidate)[1], [])

    def test_real_successor_event_failure_rolls_back_packet_and_receipt(self):
        connect = lambda _: self.psycopg.connect(self.url)
        registered_and_issued(self, connect)
        args = successor_arguments(connect)
        before = self.snapshot()
        with self.psycopg.connect(self.url) as connection:
            connection.execute("alter table public.charlie_mission_events add constraint reject_successor "
                               "check(event_type <> 'workflow_updated')")
        with self.assertRaises(self.psycopg.Error):
            apply_successor(args, connect)
        self.assertEqual(self.snapshot(), before)

    def test_real_stale_successor_snapshot_conflicts_without_losing_concurrent_change(self):
        connect = lambda _: self.psycopg.connect(self.url)
        registered_and_issued(self, connect)
        args = successor_arguments(connect)
        with self.psycopg.connect(self.url) as connection:
            connection.execute("update public.charlie_missions set metadata_json=metadata_json || %s::jsonb where mission_id=%s",
                               (json.dumps({"unrelated_concurrent_evidence": "retain me"}), registration.MISSION_ID))
        before = self.snapshot()
        with self.assertRaisesRegex(registration.RegistrationError, "predecessor_state_changed"):
            apply_successor(args, connect)
        self.assertEqual(self.snapshot(), before)


if __name__ == "__main__":
    unittest.main()
