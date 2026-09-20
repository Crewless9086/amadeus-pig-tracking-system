"""Synthetic qualification only; fixtures never represent Charl's approval."""
from copy import deepcopy
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import io
import unittest
from unittest.mock import patch

from modules.charlie import desktop_consolidation_registration as registration
from modules.charlie.mission_control import validate_mission_control_event
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
        self.executed = []
        self.commits = self.rollbacks = self.inserts = 0
        self.fail_on_event = ""
        self.corrupt_readback = False

    def __enter__(self):
        self.before = deepcopy((self.mission, self.events))
        return self

    def __exit__(self, exc_type, *_):
        if exc_type:
            self.mission, self.events = self.before
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
        if sql.startswith("select ") and "from public.charlie_missions where" in sql:
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
                created_at timestamptz default now());""")

    def setUp(self):
        with self.psycopg.connect(self.url) as connection:
            connection.execute("alter table public.charlie_mission_events drop constraint if exists reject_correction")
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


if __name__ == "__main__":
    unittest.main()
