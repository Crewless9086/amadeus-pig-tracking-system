import copy
import hashlib
import json
import os
import tempfile
import unittest
from argparse import Namespace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.charlie.mission_admission import (
    MissionAdmissionError,
    canonical_candidate_diff,
    collision_snapshot_digest,
    sign_mission_admission_receipt,
    validate_mission_admission_receipt,
)
from modules.charlie.mission_store import (
    append_mission_admission_event,
    invalidate_mission_admission_for_owner_correction,
    read_mission_admission_events,
)
from scripts.charlie_mission_admission_guard import (
    BOOTSTRAP_BASE_SHA,
    _validate_bootstrap,
    hook_main,
)


ROOT = Path(__file__).resolve().parents[1]
KEY = b"existing-validation-receipt-authority-test-key"
BASE = "a" * 40
HEAD = "b" * 40
GENERATION = "mission-admission-generation-test"
ALLOWED_FILES = sorted([
    ".cursor/hooks.json",
    "modules/charlie/mission_admission.py",
    "tests/test_charlie_mission_admission.py",
])
ALLOWED_EFFECTS = sorted([
    "repository_candidate_validation",
    "repository_commit",
    "repository_file_delete",
    "repository_file_write",
    "repository_index_write",
    "repository_push",
    "test_execution",
])
FORBIDDEN_EFFECTS = sorted([
    "customer_send",
    "deployment",
    "farm_write",
    "hardware_action",
    "production_mutation",
])


def _governance_row(path="docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md"):
    content = (ROOT / path).read_bytes()
    import subprocess
    blob = subprocess.run(
        ["git", "hash-object", path],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    return {
        "path": path,
        "git_blob": blob,
        "filesystem_sha256": hashlib.sha256(content).hexdigest(),
        "byte_count": len(content),
        "physical_line_count": content.count(b"\n"),
        "complete_byte_read": True,
    }


def _payload(*, base=BASE, head=HEAD, changed_files=None, generation=GENERATION):
    changed_files = sorted(changed_files or ALLOWED_FILES)
    captured_at = "2026-08-26T15:00:00Z"
    claims = [{
        "claim_id": "PR-1303",
        "owner": "cursor/cloud-continuity-canary-b36c",
        "paths": [".cursor/environment.json"],
        "effects": [],
        "state": "active",
    }]
    correction = "1" * 64
    return {
        "mission": {
            "mission_id": "CMQ-20260813-05",
            "root_mission_id": "CMQ-20260813-05",
            "generation": generation,
        },
        "owner_instruction_chain": {
            "instruction_digests": ["0" * 64, correction],
            "latest_correction_digest": correction,
            "admission_packet_sha256": "2" * 64,
        },
        "repository": {
            "repository": "Crewless9086/amadeus-pig-tracking-system",
            "base_ref": "main",
            "base_sha": base,
        },
        "governance_reads": [_governance_row()],
        "existing_system_trace": {
            "smallest_genuine_gap": "No immutable write-admission receipt binds prompt authority to repository scope.",
            "reused_components": [
                "charlie_missions",
                "operational_events",
                "validation_receipt authority",
                "Vault retrieval",
            ],
            "implementation_sources": sorted([
                "modules/charlie/mission_store.py",
                "modules/charlie/validation_receipt.py",
            ]),
        },
        "scope": {
            "allowed_files": ALLOWED_FILES,
            "forbidden_files": sorted(["app.py", "supabase/migrations/example.sql"]),
            "allowed_effects": ALLOWED_EFFECTS,
            "forbidden_effects": FORBIDDEN_EFFECTS,
        },
        "collision_snapshot": {
            "captured_at": captured_at,
            "active_claims": claims,
            "snapshot_sha256": collision_snapshot_digest(captured_at, claims),
        },
        "required_tests": [
            "python -m unittest tests.test_charlie_mission_admission",
            "git diff --check",
        ],
        "operational_acceptance": {
            "requirements": [
                "Exact candidate CI passes.",
                "Stage 2 separately wires the execution bridge.",
            ],
            "business_outcome_authorized": False,
        },
        "candidate": {
            "candidate_id": "CANDIDATE-TEST-1",
            "branch": "cursor/mission-admission-test",
            "base_sha": base,
            "head_sha": head,
            "diff_sha256": canonical_candidate_diff(changed_files, b"test patch"),
            "changed_files": changed_files,
        },
    }


def _receipt(**kwargs):
    issued = datetime.now(timezone.utc) - timedelta(seconds=1)
    return sign_mission_admission_receipt(
        _payload(**kwargs),
        KEY,
        issued_at=issued.isoformat().replace("+00:00", "Z"),
        expires_at=(issued + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
    )


class AdmissionStoreCursor:
    def __init__(self, metadata=None, *, correction_exists=True, read_rows=None):
        self.metadata = dict(metadata or {})
        self.correction_exists = correction_exists
        self.read_rows = list(read_rows or [])
        self.executed = []
        self.last_sql = ""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.last_sql = " ".join(sql.split())
        self.executed.append((self.last_sql, params or {}))
        if "update public.charlie_missions" in self.last_sql:
            self.metadata = json.loads(params["metadata"])

    def fetchone(self):
        if "from public.charlie_missions" in self.last_sql:
            return (self.metadata,)
        if "from public.charlie_mission_events" in self.last_sql:
            return ("CORRECTION-1",) if self.correction_exists else None
        if "insert into public.operational_events" in self.last_sql:
            return ("EVENT-1",)
        return None

    def fetchall(self):
        return list(self.read_rows)


class AdmissionStoreConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance


class MissionAdmissionReceiptTests(unittest.TestCase):
    def test_canonical_signed_receipt_has_content_addressed_immutable_identity(self):
        receipt = _receipt()
        identity = validate_mission_admission_receipt(
            receipt,
            KEY,
            expected_repository="Crewless9086/amadeus-pig-tracking-system",
            expected_base_sha=BASE,
            expected_head_sha=HEAD,
            expected_generation=GENERATION,
            expected_changed_files=ALLOWED_FILES,
        )
        self.assertEqual(identity["receipt_id"], f"MAR-{receipt['content_sha256'].upper()}")
        self.assertTrue(all(row["complete_byte_read"] for row in receipt["governance_reads"]))
        self.assertNotIn("comprehension", json.dumps(receipt).lower())

    def test_tamper_owner_base_governance_candidate_and_collision_each_invalidates(self):
        mutations = {
            "owner": ("owner_instruction_chain", "latest_correction_digest", "3" * 64),
            "base": ("repository", "base_sha", "c" * 40),
            "governance": ("governance_reads", 0, "filesystem_sha256", "4" * 64),
            "candidate": ("candidate", "head_sha", "d" * 40),
            "collision": ("collision_snapshot", "snapshot_sha256", "5" * 64),
        }
        original = _receipt()
        for name, mutation in mutations.items():
            changed = copy.deepcopy(original)
            if name == "governance":
                changed[mutation[0]][mutation[1]][mutation[2]] = mutation[3]
            else:
                changed[mutation[0]][mutation[1]] = mutation[2]
            with self.subTest(name=name), self.assertRaises(MissionAdmissionError):
                validate_mission_admission_receipt(changed, KEY)

    def test_exact_expected_context_changes_fail_closed(self):
        receipt = _receipt()
        expectations = [
            {"expected_base_sha": "c" * 40},
            {"expected_head_sha": "d" * 40},
            {"expected_generation": "changed-generation"},
            {"expected_changed_files": [".cursor/hooks.json"]},
        ]
        for expected in expectations:
            with self.subTest(expected=expected), self.assertRaises(MissionAdmissionError):
                validate_mission_admission_receipt(receipt, KEY, **expected)

    def test_forbidden_or_out_of_scope_candidate_cannot_be_signed(self):
        for changed in (["app.py"], ["not-admitted.py"]):
            with self.subTest(changed=changed), self.assertRaises(MissionAdmissionError):
                sign_mission_admission_receipt(_payload(changed_files=changed), KEY)

    def test_expired_missing_or_wrong_authority_fails_closed(self):
        receipt = _receipt()
        with self.assertRaisesRegex(MissionAdmissionError, "signature"):
            validate_mission_admission_receipt(receipt, b"wrong-authority-key-material-long-enough")
        with self.assertRaisesRegex(MissionAdmissionError, "expired"):
            validate_mission_admission_receipt(
                receipt,
                KEY,
                now=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            )


class MissionAdmissionGuardTests(unittest.TestCase):
    def _hook(self, packet, environ=None):
        output = tempfile.TemporaryFile(mode="w+")
        import contextlib
        with contextlib.redirect_stdout(output):
            code = hook_main(
                stdin=__import__("io").StringIO(json.dumps(packet)),
                environ=environ or {},
            )
        output.seek(0)
        return code, json.loads(output.read())

    def test_reads_are_allowed_but_missing_receipt_denies_mutation(self):
        _, read = self._hook({
            "hook_event_name": "preToolUse",
            "tool_name": "Read",
            "tool_input": {"path": "README.md"},
        })
        _, write = self._hook({
            "hook_event_name": "preToolUse",
            "tool_name": "Write",
            "tool_input": {"path": "modules/charlie/mission_admission.py"},
        })
        _, shell_read = self._hook({
            "hook_event_name": "beforeShellExecution",
            "command": "git status --short",
        })
        _, shell_write = self._hook({
            "hook_event_name": "beforeShellExecution",
            "command": "touch app.py",
        })
        self.assertEqual(read["permission"], "allow")
        self.assertEqual(shell_read["permission"], "allow")
        self.assertEqual(write["permission"], "deny")
        self.assertEqual(shell_write["permission"], "deny")
        self.assertEqual(write["user_message"], "READMISSION_REQUIRED")

    def test_invalid_input_and_unknown_tool_deny_instead_of_failing_open(self):
        _, unknown = self._hook({
            "hook_event_name": "preToolUse",
            "tool_name": "ArbitraryMutation",
            "tool_input": {},
        })
        self.assertEqual(unknown["permission"], "deny")
        output = tempfile.TemporaryFile(mode="w+")
        import contextlib
        with contextlib.redirect_stdout(output):
            code = hook_main(stdin=__import__("io").StringIO("{broken"), environ={})
        output.seek(0)
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.read())["permission"], "deny")

    def test_hook_configuration_overrides_cursor_fail_open_defaults(self):
        config = json.loads((ROOT / ".cursor/hooks.json").read_text(encoding="utf-8"))
        for event in ("preToolUse", "beforeShellExecution"):
            self.assertTrue(config["hooks"][event])
            for hook in config["hooks"][event]:
                self.assertIs(hook["failClosed"], True)
                self.assertGreater(hook["timeout"], 0)
        self.assertIn("afterFileEdit", config["hooks"])

    def test_pr1306_fixture_is_22_file_scope_drift_despite_green_ci(self):
        fixture = json.loads(
            (ROOT / "tests/fixtures/mission_admission/pr1306_scope_drift.json").read_text()
        )
        self.assertEqual(fixture["base_sha"], BOOTSTRAP_BASE_SHA)
        self.assertTrue(fixture["head_sha"].startswith("bf7ee6a"))
        self.assertEqual(len(fixture["candidate_files"]), 22)
        self.assertTrue(fixture["historical_ci"]["checks_green"])
        self.assertFalse(fixture["historical_ci"]["scope_authority_granted"])
        cases = {row["case"]: row for row in fixture["adversarial_expectations"]}
        self.assertEqual(cases["new_protocol_store"]["result"], "READMISSION_REQUIRED")
        self.assertEqual(cases["farm_route_controller_js_template_rewrite"]["result"], "READMISSION_REQUIRED")
        self.assertEqual(cases["unrelated_litter_loss_recovery"]["result"], "READMISSION_REQUIRED")
        self.assertIn("existing Farm", cases["telegram_adapter_parity_without_existing_farm_trace"]["may_be_readmitted_after"])

    def test_bootstrap_ci_rejects_pr1306_scope_even_with_exact_base(self):
        fixture = json.loads(
            (ROOT / "tests/fixtures/mission_admission/pr1306_scope_drift.json").read_text()
        )
        args = Namespace(
            bootstrap_generation="mission-admission-guard-bootstrap-20260826",
            owner_instruction_sha256="b9d959ee6f8ef1ff6f20e5d7aca6344b17106e9cb6e0723f95096590063a5ef5",
            admission_packet_sha256="e1af16aca874ac24af53371a7bf7384c850d788c986f9c6bcbca45800cc21014",
        )
        with self.assertRaisesRegex(MissionAdmissionError, "bootstrap_scope_drift"):
            _validate_bootstrap(args, fixture["base_sha"], fixture["candidate_files"])


class MissionAdmissionStoreTests(unittest.TestCase):
    def test_append_uses_existing_event_fabric_and_updates_projection_transactionally(self):
        cursor = AdmissionStoreCursor()
        connection = AdmissionStoreConnection(cursor)
        admission = {
            "receipt_id": "MAR-" + "A" * 64,
            "content_sha256": "a" * 64,
            "generation": GENERATION,
            "base_sha": BASE,
            "head_sha": HEAD,
        }
        result, status = append_mission_admission_event(
            "CMQ-20260813-05",
            admission,
            authenticated_principal="control-tower-validation-authority",
            database_url="postgres://test",
            connect_factory=lambda _: connection,
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["status"], "mission_admission_recorded")
        statements = [sql for sql, _ in cursor.executed]
        self.assertTrue(any("insert into public.operational_events" in sql for sql in statements))
        self.assertTrue(any("update public.charlie_missions" in sql for sql in statements))
        self.assertEqual(cursor.metadata["mission_admission"]["status"], "valid")

    def test_authenticated_owner_correction_changes_generation_and_invalidates_atomically(self):
        current = {
            "receipt_id": "MAR-" + "A" * 64,
            "content_sha256": "a" * 64,
            "generation": GENERATION,
            "base_sha": BASE,
            "head_sha": HEAD,
            "status": "valid",
            "recorded_by": "control-tower-validation-authority",
        }
        cursor = AdmissionStoreCursor({"mission_admission": current})
        connection = AdmissionStoreConnection(cursor)
        result, status = invalidate_mission_admission_for_owner_correction(
            "CMQ-20260813-05",
            "corrected-generation",
            owner_authentication={
                "authenticated": True,
                "principal_type": "owner_admin",
                "principal_id": "owner-charl",
                "correction_event_id": "CORRECTION-1",
                "correction_digest": "f" * 64,
            },
            database_url="postgres://test",
            connect_factory=lambda _: connection,
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["status"], "mission_admission_invalidated")
        self.assertEqual(cursor.metadata["mission_admission"]["status"], "invalidated")
        self.assertEqual(
            cursor.metadata["mission_admission"]["replacement_generation"],
            "corrected-generation",
        )
        self.assertTrue(any(
            "event_type='owner_correction_recorded'" in sql
            for sql, _ in cursor.executed
        ))

    def test_unauthenticated_correction_is_rejected_before_database_access(self):
        result, status = invalidate_mission_admission_for_owner_correction(
            "CMQ-20260813-05",
            "changed",
            owner_authentication={},
            database_url="postgres://test",
            connect_factory=lambda _: self.fail("database must not be accessed"),
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["status"], "authenticated_owner_correction_required")

    def test_read_uses_operational_events_without_new_table(self):
        now = datetime.now(timezone.utc)
        rows = [(
            "EVENT-1",
            "mission_admission_recorded",
            now,
            now,
            {"receipt_id": "MAR-" + "A" * 64},
            {"source_ref": "modules/charlie/mission_store.py"},
            "control_tower",
            "authority",
        )]
        cursor = AdmissionStoreCursor(read_rows=rows)
        result, status = read_mission_admission_events(
            "CMQ-20260813-05",
            database_url="postgres://test",
            connect_factory=lambda _: AdmissionStoreConnection(cursor),
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["events"][0]["event_id"], "EVENT-1")
        self.assertIn("from public.operational_events", cursor.executed[0][0])


if __name__ == "__main__":
    unittest.main()
