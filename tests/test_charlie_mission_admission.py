import copy
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from modules.charlie.mission_admission import (
    MissionAdmissionError,
    canonical_candidate_diff,
    collision_snapshot_digest,
    sign_mission_admission_receipt,
    validate_mission_admission_receipt,
)
from modules.charlie.mission_store import (
    _mission_admission_collision_observed_at,
    append_mission_admission_event,
    consume_mission_admission,
    invalidate_mission_admission_for_owner_correction,
    read_current_mission_admission_authority,
    read_mission_admission_events,
    revoke_mission_admission,
)
from modules.charlie.validation_receipt import canonical_json
from scripts.charlie_mission_admission_guard import (
    BOOTSTRAP_ALLOWED_FILES,
    BOOTSTRAP_BASE_SHA,
    BOOTSTRAP_FORBIDDEN_EFFECTS,
    BOOTSTRAP_GENERATION,
    BOOTSTRAP_REQUIRED_TESTS,
    _is_read_only_shell,
    _compare_current_authority,
    _build_exact_candidate_payload,
    _canonical_packet_digest,
    _replace_receipt_marker,
    _require_canonical_review_linkage,
    _protected_database_url,
    _tool_target_path,
    _validate_external_receipt_envelope,
    _validate_paths_and_effects,
    ci_external_main,
    ci_main,
    hook_main,
    issue_pr_main,
    trusted_check_main,
)


ROOT = Path(__file__).resolve().parents[1]
KEY = b"existing-validation-receipt-authority-test-key"
BASE = "a" * 40
HEAD = "b" * 40
GENERATION = "mission-admission-generation-test"
ALLOWED_FILES = sorted(BOOTSTRAP_ALLOWED_FILES)
ALLOWED_EFFECTS = sorted([
    "repository_candidate_validation",
    "repository_commit",
    "repository_file_delete",
    "repository_file_write",
    "repository_index_write",
    "repository_push",
    "test_execution",
])
FORBIDDEN_EFFECTS = sorted(set([
    "customer_send",
    "deployment",
    "farm_write",
    "hardware_action",
    "production_mutation",
] + list(BOOTSTRAP_FORBIDDEN_EFFECTS)))


def _governance_row(path="docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md"):
    import subprocess
    content = subprocess.run(
        ["git", "show", f"HEAD:{path}"],
        cwd=ROOT,
        check=True,
        capture_output=True,
    ).stdout
    blob = subprocess.run(
        ["git", "rev-parse", f"HEAD:{path}"],
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
        "mission_id": "GITHUB-PR-1303",
        "status": "approved",
        "paths": [".cursor/environment.json"],
        "effects": [],
        "lease_id": "",
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
        "required_tests": sorted(BOOTSTRAP_REQUIRED_TESTS),
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


def _admission_projection(**updates):
    value = {
        "receipt_id": "MAR-" + "A" * 64,
        "content_sha256": "a" * 64,
        "mission_id": "CMQ-20260813-05",
        "root_mission_id": "CMQ-20260813-05",
        "generation": GENERATION,
        "base_sha": BASE,
        "head_sha": HEAD,
        "authority_key_sha256": hashlib.sha256(KEY).hexdigest(),
        "latest_correction_digest": "1" * 64,
        "collision_snapshot_sha256": "2" * 64,
    }
    value.update(updates)
    return value


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
        if "insert into public.charlie_mission_events" in self.last_sql:
            return ("CORRECTION-1",)
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
            expected_mission_id="CMQ-20260813-05",
            expected_root_mission_id="CMQ-20260813-05",
            expected_authority_key_sha256=hashlib.sha256(KEY).hexdigest(),
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
            {"expected_mission_id": "OTHER"},
            {"expected_root_mission_id": "OTHER"},
            {"expected_changed_files": [".cursor/hooks.json"]},
        ]
        required = {
            "expected_generation": GENERATION,
            "expected_mission_id": "CMQ-20260813-05",
            "expected_root_mission_id": "CMQ-20260813-05",
        }
        for expected in expectations:
            with self.subTest(expected=expected), self.assertRaises(MissionAdmissionError):
                validate_mission_admission_receipt(
                    receipt, KEY, **{**required, **expected}
                )

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
                expected_generation=GENERATION,
                expected_mission_id="CMQ-20260813-05",
                expected_root_mission_id="CMQ-20260813-05",
                now=(datetime.now(timezone.utc) + timedelta(hours=2)).isoformat().replace("+00:00", "Z"),
            )


class MissionAdmissionGuardTests(unittest.TestCase):
    def _hook(
        self,
        packet,
        environ=None,
        *,
        authority_reader=None,
        repo_root=ROOT,
        os_name=None,
    ):
        output = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(output):
            code = hook_main(
                stdin=io.StringIO(json.dumps(packet)),
                environ=environ or {},
                authority_reader=authority_reader,
                repo_root=repo_root,
                os_name=os_name,
            )
        return code, json.loads(output.getvalue())

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
        output = io.StringIO()
        import contextlib
        with contextlib.redirect_stdout(output):
            code = hook_main(stdin=io.StringIO("{broken"), environ={})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(output.getvalue())["permission"], "deny")

    def test_mcp_subagent_and_unknown_builtin_mutations_are_denied(self):
        for tool_name in (
            "MCP:create_or_update_file",
            "MCP:send_slack_message",
            "Task",
            "Subagent",
            "GenerateImage",
            "ArbitraryMutation",
        ):
            with self.subTest(tool_name=tool_name):
                _, result = self._hook({
                    "hook_event_name": "preToolUse",
                    "tool_name": tool_name,
                    "tool_input": {},
                })
                self.assertEqual(result["permission"], "deny")

    def test_linux_and_windows_shell_bypasses_are_denied(self):
        denied = [
            ("git branch -D main", "posix"),
            ("git remote set-url origin https://attacker.invalid/repo", "posix"),
            ("git hash-object -w --stdin", "posix"),
            ("python -c 'open(\"app.py\",\"w\").write(\"x\")'", "posix"),
            ("node -e \"require('fs').writeFileSync('app.py','x')\"", "posix"),
            ("powershell.exe -Command Set-Content app.py x", "nt"),
            ("pwsh.exe -Command Remove-Item app.py", "nt"),
            ("cmd.exe /c del app.py", "nt"),
        ]
        for command, platform_name in denied:
            with self.subTest(command=command):
                self.assertFalse(
                    _is_read_only_shell(command, os_name=platform_name)
                )
                _, result = self._hook({
                    "hook_event_name": "beforeShellExecution",
                    "command": command,
                }, os_name=platform_name)
                self.assertEqual(result["permission"], "deny")
        for command, platform_name in (
            ("git status --short", "posix"),
            ("git remote get-url origin", "posix"),
            ("git branch --show-current", "posix"),
            ("git status --short", "nt"),
        ):
            with self.subTest(command=command, allowed=True):
                self.assertTrue(
                    _is_read_only_shell(command, os_name=platform_name)
                )

    def test_apply_patch_requires_one_exact_admitted_target(self):
        packet = {
            "hook_event_name": "preToolUse",
            "tool_name": "ApplyPatch",
            "tool_input": {
                "patch": (
                    "*** Begin Patch\n"
                    "*** Update File: tests/test_charlie_mission_admission.py\n"
                    "@@\n-old\n+new\n"
                    "*** End Patch\n"
                )
            },
        }
        self.assertEqual(
            _tool_target_path(packet),
            "tests/test_charlie_mission_admission.py",
        )
        packet["tool_input"]["patch"] = (
            "*** Begin Patch\n"
            "*** Update File: tests/test_charlie_mission_admission.py\n"
            "*** Update File: app.py\n"
            "*** End Patch\n"
        )
        self.assertEqual(_tool_target_path(packet), "")

    def test_caller_paths_are_ignored_and_only_pinned_authority_allows_write(self):
        import subprocess
        current_head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        current_base = current_head
        receipt = _receipt(base=current_base, head=current_head)
        with tempfile.TemporaryDirectory() as directory:
            repo_root = Path(directory)
            state_root = repo_root / ".charlie_runner"
            receipt_dir = state_root / "mission-admission-receipts"
            receipt_dir.mkdir(parents=True)
            receipt_path = receipt_dir / f"{receipt['receipt_id']}.json"
            key_path = state_root / "validation-receipt.key"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            key_path.write_bytes(KEY)
            key_path.chmod(0o600)
            environ = {
                "CHARLIE_MISSION_ADMISSION_RECEIPT_PATH": "/attacker/receipt",
                "CHARLIE_VALIDATION_RECEIPT_KEY_PATH": "/attacker/key",
            }
            admission = {
                "receipt_id": receipt["receipt_id"],
                "content_sha256": receipt["content_sha256"],
                "generation": GENERATION,
                "authority_key_sha256": hashlib.sha256(KEY).hexdigest(),
            }
            authority = {
                "success": True,
                "mission_id": "CMQ-20260813-05",
                "root_mission_id": "CMQ-20260813-05",
                "admission": admission | {"status": "valid"},
                "latest_correction_digest": receipt[
                    "owner_instruction_chain"
                ]["latest_correction_digest"],
                "collision_snapshot_sha256": receipt[
                    "collision_snapshot"
                ]["snapshot_sha256"],
            }
            authority_reader = lambda _mission_id: (authority, 200)
            with patch(
                "scripts.charlie_mission_admission_guard._worktree_changed_files",
                return_value=[],
            ):
                _, allowed = self._hook({
                    "hook_event_name": "preToolUse",
                    "tool_name": "Write",
                    "tool_input": {"path": "tests/test_charlie_mission_admission.py"},
                }, environ=environ, authority_reader=authority_reader, repo_root=repo_root)
                _, denied = self._hook({
                    "hook_event_name": "preToolUse",
                    "tool_name": "Write",
                    "tool_input": {"path": "app.py"},
                }, environ=environ, authority_reader=authority_reader, repo_root=repo_root)
        self.assertEqual(allowed["permission"], "allow", allowed)
        self.assertEqual(denied["permission"], "deny")

    def test_hook_configuration_overrides_cursor_fail_open_defaults(self):
        config = json.loads((ROOT / ".cursor/hooks.json").read_text(encoding="utf-8"))
        for event in ("preToolUse", "beforeShellExecution"):
            self.assertTrue(config["hooks"][event])
            for hook in config["hooks"][event]:
                self.assertIs(hook["failClosed"], True)
                self.assertGreater(hook["timeout"], 0)
        self.assertNotIn("matcher", config["hooks"]["preToolUse"][0])
        self.assertIn("afterFileEdit", config["hooks"])

    def test_host_process_hook_contract_emits_valid_allow_and_deny_json(self):
        script = ROOT / "scripts/charlie_mission_admission_guard.py"
        packets = [
            ({
                "hook_event_name": "preToolUse",
                "tool_name": "Read",
                "tool_input": {"path": "README.md"},
            }, "allow"),
            ({
                "hook_event_name": "beforeShellExecution",
                "command": "python -c \"open('app.py','w').write('x')\"",
            }, "deny"),
        ]
        for packet, expected in packets:
            with self.subTest(expected=expected):
                completed = subprocess.run(
                    [sys.executable, str(script), "hook"],
                    cwd=ROOT,
                    input=json.dumps(packet),
                    text=True,
                    capture_output=True,
                    timeout=10,
                    check=True,
                )
                self.assertEqual(
                    json.loads(completed.stdout)["permission"],
                    expected,
                )

    def test_pr1306_fixture_is_22_file_scope_drift_despite_green_ci(self):
        fixture = json.loads(
            (ROOT / "tests/fixtures/mission_admission/pr1306_scope_drift.json").read_text()
        )
        self.assertEqual(fixture["base_sha"], BOOTSTRAP_BASE_SHA)
        self.assertEqual(
            fixture["head_sha"],
            "bf7ee6a160ead5fb3853662345ae57a459d8d42e",
        )
        self.assertEqual(len(fixture["candidate_files"]), 22)
        self.assertEqual(len(fixture["historical_ci"]["checks"]), 4)
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
        with self.assertRaisesRegex(MissionAdmissionError, "admission_scope_drift"):
            _validate_paths_and_effects(
                fixture["candidate_files"],
                sorted(BOOTSTRAP_ALLOWED_FILES),
                ["modules/pig_weights/herdmaster_first_treatment_protocol.py"],
                "repository_candidate_validation",
                ["repository_candidate_validation"],
                ["farm_write"],
            )

    def test_ci_compares_signed_exact_head_diff_files_and_required_contract(self):
        receipt = _receipt(
            base=BOOTSTRAP_BASE_SHA,
            head=HEAD,
            generation=BOOTSTRAP_GENERATION,
        )
        authority = {
            "success": True,
            "mission_id": "CMQ-20260813-05",
            "root_mission_id": "CMQ-20260813-05",
            "admission": {
                "status": "valid",
                "receipt_id": receipt["receipt_id"],
                "content_sha256": receipt["content_sha256"],
                "generation": BOOTSTRAP_GENERATION,
                "authority_key_sha256": hashlib.sha256(KEY).hexdigest(),
            },
            "latest_correction_digest": receipt[
                "owner_instruction_chain"
            ]["latest_correction_digest"],
            "collision_snapshot_sha256": receipt[
                "collision_snapshot"
            ]["snapshot_sha256"],
        }
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / ".charlie_runner"
            receipts = state / "mission-admission-receipts"
            receipts.mkdir(parents=True)
            (state / "validation-receipt.key").write_bytes(KEY)
            (state / "validation-receipt.key").chmod(0o600)
            (receipts / f"{receipt['receipt_id']}.json").write_text(
                json.dumps(receipt),
                encoding="utf-8",
            )
            output = io.StringIO()
            import contextlib
            with (
                patch(
                    "scripts.charlie_mission_admission_guard._commit",
                    side_effect=[BOOTSTRAP_BASE_SHA, HEAD],
                ),
                patch(
                    "scripts.charlie_mission_admission_guard._changed_files",
                    return_value=ALLOWED_FILES,
                ),
                patch(
                    "scripts.charlie_mission_admission_guard._git_bytes",
                    return_value=b"test patch",
                ),
                patch(
                    "scripts.charlie_mission_admission_guard._verify_governance_reads"
                ),
                patch(
                    "scripts.charlie_mission_admission_guard._repository_identity",
                    return_value="Crewless9086/amadeus-pig-tracking-system",
                ),
                contextlib.redirect_stdout(output),
            ):
                code = ci_main(
                    SimpleNamespace(base=BOOTSTRAP_BASE_SHA, head=HEAD),
                    authority_reader=lambda _mission_id: (authority, 200),
                    repo_root=root,
                )
        self.assertEqual(code, 0, output.getvalue())
        result = json.loads(output.getvalue())
        self.assertEqual(result["head_sha"], HEAD)
        self.assertEqual(
            result["diff_sha256"],
            canonical_candidate_diff(ALLOWED_FILES, b"test patch"),
        )


class MissionAdmissionExternalCiTests(unittest.TestCase):
    @staticmethod
    def _test_public_key_b64():
        seed = hashlib.sha256(
            b"charlie-mission-admission-ci-ed25519-v1\0" + KEY
        ).digest()
        return base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            )
        ).decode("ascii")

    @staticmethod
    def _canonical_binding(envelope, *, observed_at=None):
        receipt = envelope["receipt"]
        return {
            "mission_id": receipt["mission"]["mission_id"],
            "root_mission_id": receipt["mission"]["root_mission_id"],
            "generation": receipt["mission"]["generation"],
            "authority_key_sha256": receipt["authority_key_sha256"],
            "latest_correction_digest": receipt["owner_instruction_chain"][
                "latest_correction_digest"
            ],
            "collision_snapshot_sha256": receipt["collision_snapshot"][
                "snapshot_sha256"
            ],
            "canonical_observed_at": observed_at or receipt["issued_at"],
        }

    def test_workflow_external_receipt_heredoc_is_shell_aligned(self):
        workflow = (ROOT / ".github/workflows/charlie-core-tests.yml").read_text(
            encoding="utf-8"
        ).splitlines()
        opener = next(line for line in workflow if "python - <<'PY'" in line)
        terminator = next(line for line in workflow if line.strip() == "PY")
        first_python = next(line for line in workflow if line.strip() == "import base64")
        indent = lambda line: len(line) - len(line.lstrip())
        self.assertEqual(indent(opener), indent(terminator))
        self.assertEqual(indent(opener), indent(first_python))
        self.assertTrue(any(
            "Mission-Admission-Receipt-B64:" in line and r"\r?$" in line
            for line in workflow
        ))
        joined = "\n".join(workflow)
        self.assertNotIn("CHARLIE_VALIDATION_RECEIPT_KEY_B64", joined)
        self.assertNotIn("validation-receipt.key", joined)

    def test_trusted_workflow_is_base_only_and_environment_isolated(self):
        workflow = (ROOT / ".github/workflows/mission-admission-trusted.yml").read_text(
            encoding="utf-8"
        )
        candidate = (ROOT / ".github/workflows/charlie-core-tests.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("pull_request_target:", workflow)
        for activity in ("opened", "reopened", "synchronize", "edited", "ready_for_review"):
            self.assertIn(activity, workflow)
        self.assertIn("environment: charlie-admission-validator", workflow)
        self.assertIn("ref: ${{ github.event.pull_request.base.sha }}", workflow)
        self.assertNotIn("github.event.pull_request.head", workflow)
        self.assertIn("trusted-check", workflow)
        self.assertIn("CHARLIE_ADMISSION_READ_DATABASE_URL", workflow)
        self.assertNotIn("CHARLIE_ADMISSION_CANONICAL_BINDING_B64", workflow)
        self.assertIn("mission-admission-candidate-diagnostic:", candidate)
        self.assertNotIn("\n  mission-admission:\n", candidate)
        issuer = (ROOT / ".github/workflows/mission-admission-issuer.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("workflow_dispatch:", issuer)
        self.assertIn("environment: charlie-admission-validator", issuer)
        self.assertNotIn("pull_request_target:", issuer)
        self.assertNotIn("pull_request:", issuer)
        self.assertIn("ref: ${{ github.sha }}", issuer)
        self.assertIn("github.ref == 'refs/heads/main'", issuer)
        guard = (ROOT / "scripts/charlie_mission_admission_guard.py").read_text(encoding="utf-8")
        for option in ("--no-ext-diff", "--no-textconv", "--binary", "--full-index"):
            self.assertIn(option, guard)
        self.assertNotIn("checkout", "\n".join(line for line in issuer.splitlines() if "github.event.pull_request.head" in line))

    def _run(self, *, receipt, patch_bytes=b"external patch", head=HEAD):
        import contextlib

        seed = hashlib.sha256(
            b"charlie-mission-admission-ci-ed25519-v1\0" + KEY
        ).digest()
        public_key_b64 = base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            )
        ).decode("ascii")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
            output = io.StringIO()
            with (
                patch(
                    "scripts.charlie_mission_admission_guard._commit",
                    side_effect=[BASE, head],
                ),
                patch(
                    "scripts.charlie_mission_admission_guard._changed_files",
                    return_value=ALLOWED_FILES,
                ),
                patch(
                    "scripts.charlie_mission_admission_guard._git_bytes",
                    return_value=patch_bytes,
                ),
                patch(
                    "scripts.charlie_mission_admission_guard._verify_governance_reads"
                ),
                patch(
                    "scripts.charlie_mission_admission_guard._repository_identity",
                    return_value="Crewless9086/amadeus-pig-tracking-system",
                ),
                patch(
                    "scripts.charlie_mission_admission_guard.EXTERNAL_ADMISSION_PUBLIC_KEY_B64",
                    public_key_b64,
                ),
                contextlib.redirect_stdout(output),
            ):
                code = ci_external_main(
                    SimpleNamespace(base=BASE, head=head, receipt=str(receipt_path)),
                    repo_root=root,
                )
        return code, json.loads(output.getvalue())

    def _signed(self, *, patch_bytes=b"external patch", head=HEAD):
        payload = _payload(base=BASE, head=head)
        payload["candidate"]["diff_sha256"] = canonical_candidate_diff(
            ALLOWED_FILES, patch_bytes
        )
        issued = datetime.now(timezone.utc) - timedelta(seconds=1)
        captured_at = issued.isoformat().replace("+00:00", "Z")
        payload["collision_snapshot"]["captured_at"] = captured_at
        payload["collision_snapshot"]["snapshot_sha256"] = collision_snapshot_digest(
            captured_at, payload["collision_snapshot"]["active_claims"]
        )
        receipt = sign_mission_admission_receipt(
            payload,
            KEY,
            issued_at=issued.isoformat().replace("+00:00", "Z"),
            expires_at=(issued + timedelta(hours=1)).isoformat().replace("+00:00", "Z"),
        )
        seed = hashlib.sha256(
            b"charlie-mission-admission-ci-ed25519-v1\0" + KEY
        ).digest()
        signature = Ed25519PrivateKey.from_private_bytes(seed).sign(
            canonical_json(receipt)
        )
        return {
            "version": "mission_admission_ci_envelope_v1",
            "receipt": receipt,
            "signature_ed25519": base64.b64encode(signature).decode("ascii"),
        }

    def test_valid_external_receipt_accepts_exact_candidate(self):
        code, result = self._run(receipt=self._signed())
        self.assertEqual(code, 0, result)
        self.assertTrue(result["success"])
        self.assertEqual(result["head_sha"], HEAD)

    def test_external_receipt_rejects_changed_candidate_diff(self):
        code, result = self._run(
            receipt=self._signed(patch_bytes=b"original patch"),
            patch_bytes=b"changed patch",
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "READMISSION_REQUIRED")
        self.assertEqual(result["reason_code"], "admission_candidate_changed")

    def test_external_receipt_rejects_altered_signature(self):
        envelope = self._signed()
        envelope["signature_ed25519"] = base64.b64encode(b"0" * 64).decode("ascii")
        code, result = self._run(receipt=envelope)
        self.assertEqual(code, 2)
        self.assertEqual(result["reason_code"], "external_admission_signature_invalid")

    def test_canonical_binding_rejects_every_changed_authority_identity(self):
        envelope = self._signed()
        binding = self._canonical_binding(envelope)
        for field in binding:
            if field == "canonical_observed_at":
                continue
            changed = dict(binding)
            changed[field] = "different"
            with self.subTest(field=field):
                with (
                    patch(
                        "scripts.charlie_mission_admission_guard.EXTERNAL_ADMISSION_PUBLIC_KEY_B64",
                        self._test_public_key_b64(),
                    ),
                    self.assertRaisesRegex(
                        MissionAdmissionError, "canonical_admission_authority_changed"
                    ),
                ):
                    _validate_external_receipt_envelope(
                        envelope,
                        expected_repository="Crewless9086/amadeus-pig-tracking-system",
                        expected_base_sha=BASE,
                        expected_head_sha=HEAD,
                        expected_changed_files=ALLOWED_FILES,
                        expected_canonical_binding=changed,
                    )

    def test_trusted_path_rejects_stale_canonical_observation(self):
        envelope = self._signed()
        receipt = envelope["receipt"]
        issued = datetime.fromisoformat(receipt["issued_at"].replace("Z", "+00:00"))
        stale = (issued - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        with (
            patch(
                "scripts.charlie_mission_admission_guard.EXTERNAL_ADMISSION_PUBLIC_KEY_B64",
                self._test_public_key_b64(),
            ),
            self.assertRaisesRegex(
                MissionAdmissionError, "canonical_admission_observation_stale"
            ),
        ):
            _validate_external_receipt_envelope(
                envelope,
                expected_repository="Crewless9086/amadeus-pig-tracking-system",
                expected_base_sha=BASE,
                expected_head_sha=HEAD,
                expected_changed_files=ALLOWED_FILES,
                expected_canonical_binding=self._canonical_binding(
                    envelope, observed_at=stale
                ),
            )

    def test_trusted_check_publishes_success_for_exact_event_without_candidate_execution(self):
        envelope = self._signed()
        marker = base64.b64encode(canonical_json(envelope)).decode("ascii")
        event = {
            "number": 1310,
            "repository": {"full_name": "Crewless9086/amadeus-pig-tracking-system"},
            "pull_request": {
                "body": f"Mission-Admission-Receipt-B64: {marker}\r\n",
                "base": {"ref": "main", "sha": BASE},
                "head": {"ref": "cursor/mission-admission-test", "sha": HEAD},
            },
        }
        calls = []
        def publish(method, token, payload, check_id=None):
            calls.append((method, token, payload, check_id))
            return {"id": 42} if method == "POST" else {"id": 42}
        import contextlib
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text(json.dumps(event), encoding="utf-8")
            output = io.StringIO()
            seed = hashlib.sha256(
                b"charlie-mission-admission-ci-ed25519-v1\0" + KEY
            ).digest()
            public_key_b64 = base64.b64encode(
                Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
                    Encoding.Raw, PublicFormat.Raw
                )
            ).decode("ascii")
            with (
                patch("scripts.charlie_mission_admission_guard._protected_database_url", return_value="postgres://readonly?sslmode=require"),
                patch("scripts.charlie_mission_admission_guard._app_check_request", side_effect=publish),
                patch("scripts.charlie_mission_admission_guard.subprocess.run"),
                patch("scripts.charlie_mission_admission_guard._commit", side_effect=[BASE, HEAD]),
                patch("scripts.charlie_mission_admission_guard._changed_files", return_value=ALLOWED_FILES),
                patch("scripts.charlie_mission_admission_guard._git_bytes", return_value=b"external patch"),
                patch("scripts.charlie_mission_admission_guard._verify_governance_reads"),
                patch("scripts.charlie_mission_admission_guard.EXTERNAL_ADMISSION_PUBLIC_KEY_B64", public_key_b64),
                patch("scripts.charlie_mission_admission_guard.get_mission", return_value=({
                    "success": True,
                    "mission": {"metadata": {
                        "mission_family": {"generation": GENERATION},
                        "review_packet": {
                            "pr_number": 1310,
                            "candidate_revision": HEAD,
                            "branch_name": "cursor/mission-admission-test",
                            "candidate_diff_sha256": canonical_candidate_diff(ALLOWED_FILES, b"external patch"),
                            "changed_files": ALLOWED_FILES,
                        },
                        "mission_admission_contract": {
                            "allowed_files": ALLOWED_FILES,
                            "forbidden_files": envelope["receipt"]["scope"]["forbidden_files"],
                            "allowed_effects": ALLOWED_EFFECTS,
                            "forbidden_effects": FORBIDDEN_EFFECTS,
                            "required_tests": sorted(BOOTSTRAP_REQUIRED_TESTS),
                            "operational_acceptance": envelope["receipt"]["operational_acceptance"]["requirements"],
                        },
                    }},
                }, 200)),
                patch("scripts.charlie_mission_admission_guard.read_current_mission_admission_authority", return_value=({
                    "success": True,
                    "mission_id": "CMQ-20260813-05",
                    "root_mission_id": "CMQ-20260813-05",
                    "admission": {
                        "status": "valid", "mission_id": "CMQ-20260813-05",
                        "root_mission_id": "CMQ-20260813-05", "generation": GENERATION,
                        "base_sha": BASE, "head_sha": HEAD,
                        "authority_key_sha256": envelope["receipt"]["authority_key_sha256"],
                        "latest_correction_digest": envelope["receipt"]["owner_instruction_chain"]["latest_correction_digest"],
                        "collision_snapshot_sha256": envelope["receipt"]["collision_snapshot"]["snapshot_sha256"],
                        "receipt_id": envelope["receipt"]["receipt_id"],
                        "content_sha256": envelope["receipt"]["content_sha256"],
                    },
                    "latest_correction_digest": envelope["receipt"]["owner_instruction_chain"]["latest_correction_digest"],
                    "collision_snapshot_sha256": envelope["receipt"]["collision_snapshot"]["snapshot_sha256"],
                }, 200)),
                patch("scripts.charlie_mission_admission_guard._canonical_packet_digest", return_value=envelope["receipt"]["owner_instruction_chain"]["admission_packet_sha256"]),
                contextlib.redirect_stdout(output),
            ):
                code = trusted_check_main(
                    SimpleNamespace(event=str(path)),
                    environ={
                        "CHARLIE_ADMISSION_APP_TOKEN": "installation-token",
                        "CHARLIE_ADMISSION_READ_DATABASE_URL": "protected",
                    },
                )
        self.assertEqual(code, 0, output.getvalue())
        self.assertEqual(calls[0][0], "POST")
        self.assertEqual(calls[-1][2]["conclusion"], "success")

    def test_trusted_check_fails_closed_without_dynamic_canonical_database(self):
        import contextlib
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "event.json"
            path.write_text("{}", encoding="utf-8")
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = trusted_check_main(
                    SimpleNamespace(event=str(path)),
                    environ={"CHARLIE_ADMISSION_APP_TOKEN": "installation-token"},
                )
        self.assertEqual(code, 2)
        self.assertEqual(
            json.loads(output.getvalue())["reason_code"],
            "CANONICAL_AUTHORITY_UNAVAILABLE",
        )

    def test_dynamic_authority_invalidates_owner_collision_and_lifecycle_changes(self):
        receipt = self._signed()["receipt"]
        contract = {
            "allowed_files": receipt["scope"]["allowed_files"],
            "forbidden_files": receipt["scope"]["forbidden_files"],
            "allowed_effects": receipt["scope"]["allowed_effects"],
            "forbidden_effects": receipt["scope"]["forbidden_effects"],
            "required_tests": receipt["required_tests"],
            "operational_acceptance": receipt["operational_acceptance"]["requirements"],
        }
        authority = {
            "mission_id": receipt["mission"]["mission_id"],
            "root_mission_id": receipt["mission"]["root_mission_id"],
            "admission": {
                "status": "valid",
                "mission_id": receipt["mission"]["mission_id"],
                "root_mission_id": receipt["mission"]["root_mission_id"],
                "generation": receipt["mission"]["generation"],
                "base_sha": receipt["repository"]["base_sha"],
                "head_sha": receipt["candidate"]["head_sha"],
                "authority_key_sha256": receipt["authority_key_sha256"],
                "latest_correction_digest": receipt["owner_instruction_chain"]["latest_correction_digest"],
                "collision_snapshot_sha256": receipt["collision_snapshot"]["snapshot_sha256"],
                "receipt_id": receipt["receipt_id"],
                "content_sha256": receipt["content_sha256"],
            },
            "latest_correction_digest": receipt["owner_instruction_chain"]["latest_correction_digest"],
            "collision_snapshot_sha256": receipt["collision_snapshot"]["snapshot_sha256"],
        }
        receipt["owner_instruction_chain"]["admission_packet_sha256"] = _canonical_packet_digest(authority, contract)
        _compare_current_authority(receipt, authority, contract)
        cases = (
            ("latest_correction_digest", "0" * 64, "owner_correction_changed"),
            ("collision_snapshot_sha256", "0" * 64, "collision_snapshot_changed"),
        )
        for key, value, reason in cases:
            changed = copy.deepcopy(authority)
            changed[key] = value
            with self.subTest(reason=reason), self.assertRaisesRegex(MissionAdmissionError, reason):
                _compare_current_authority(receipt, changed, contract)
        for status in ("revoked", "consumed"):
            changed = copy.deepcopy(authority)
            changed["admission"]["status"] = status
            with self.subTest(status=status), self.assertRaisesRegex(MissionAdmissionError, f"admission_{status}"):
                _compare_current_authority(receipt, changed, contract)

    def test_issuer_uses_exact_canonical_linkage_preserves_body_and_is_idempotent(self):
        seed = hashlib.sha256(b"issuer-test-seed").digest()
        public = base64.b64encode(
            Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes(
                Encoding.Raw, PublicFormat.Raw
            )
        ).decode()
        captured_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        claims = []
        contract = {
            "base_sha": BASE,
            "branch": "cursor/mission-admission-test",
            "allowed_files": ALLOWED_FILES,
            "forbidden_files": ["app.py"],
            "allowed_effects": ALLOWED_EFFECTS,
            "forbidden_effects": FORBIDDEN_EFFECTS,
            "required_tests": sorted(BOOTSTRAP_REQUIRED_TESTS),
            "operational_acceptance": ["Exact candidate CI passes."],
        }
        mission = {"mission_id": "CMQ-20260813-05", "raw_text": "owner instruction"}
        family = {"generation": GENERATION}
        correction = "1" * 64
        collision = collision_snapshot_digest(captured_at, claims)
        authority = {
            "success": True,
            "mission_id": mission["mission_id"],
            "root_mission_id": mission["mission_id"],
            "latest_correction_digest": correction,
            "collision_observed_at": captured_at,
            "collision_snapshot_sha256": collision,
            "active_claims": claims,
            "admission": {
                "status": "valid", "mission_id": mission["mission_id"],
                "root_mission_id": mission["mission_id"], "generation": GENERATION,
                "base_sha": BASE, "head_sha": HEAD,
                "authority_key_sha256": hashlib.sha256(KEY).hexdigest(),
                "latest_correction_digest": correction,
                "collision_snapshot_sha256": collision,
                "receipt_id": "MAR-" + "A" * 64, "content_sha256": "a" * 64,
            },
        }
        governance = [_governance_row()]
        canonical_payload = _build_exact_candidate_payload(
            mission=mission, family=family, authority=authority, contract=contract,
            base=BASE, head=HEAD, branch=contract["branch"],
            diff_sha256=canonical_candidate_diff(ALLOWED_FILES, b"external patch"),
            changed_files=ALLOWED_FILES, governance_reads=governance,
            repository="Crewless9086/amadeus-pig-tracking-system",
        )
        canonical_receipt = sign_mission_admission_receipt(canonical_payload, KEY)
        authority["admission"].update({
            "receipt_id": canonical_receipt["receipt_id"],
            "content_sha256": canonical_receipt["content_sha256"],
            "signed_receipt": canonical_receipt,
        })
        pull = {
            "state": "open", "merged_at": None, "body": "Preserve this text.\n",
            "base": {"ref": "main", "sha": BASE},
            "head": {"ref": contract["branch"], "sha": HEAD},
        }
        calls = []
        def github(_number, _token, body=None):
            if body is None:
                return copy.deepcopy(pull)
            calls.append(body)
            pull["body"] = body
            return copy.deepcopy(pull)
        environ = {
            "GITHUB_TOKEN": "not-logged",
            "CHARLIE_VALIDATION_RECEIPT_KEY_B64": base64.b64encode(KEY).decode(),
            "CHARLIE_ADMISSION_RECEIPT_SIGNING_KEY_B64": base64.b64encode(seed).decode(),
        }
        args = SimpleNamespace(pull_request_number=1312, expected_head_sha=HEAD, event_output=None)
        import contextlib
        for iteration, expected_writes in enumerate((1, 1)):
            output = io.StringIO()
            with (
                patch("scripts.charlie_mission_admission_guard._protected_database_url", return_value="postgres://readonly?sslmode=require"),
                patch("scripts.charlie_mission_admission_guard._github_pull_request", side_effect=github),
                patch("scripts.charlie_mission_admission_guard.subprocess.run"),
                patch("scripts.charlie_mission_admission_guard._commit", side_effect=[BASE, HEAD]),
                patch("scripts.charlie_mission_admission_guard._changed_files", return_value=ALLOWED_FILES),
                patch("scripts.charlie_mission_admission_guard._git_bytes", return_value=b"external patch"),
                patch("scripts.charlie_mission_admission_guard._canonical_contract_for_pull", return_value=(mission, {}, contract, family)),
                patch("scripts.charlie_mission_admission_guard.read_current_mission_admission_authority", return_value=(authority, 200)),
                patch("scripts.charlie_mission_admission_guard._governance_read_identities", return_value=governance),
                patch("scripts.charlie_mission_admission_guard._repository_identity", return_value="Crewless9086/amadeus-pig-tracking-system"),
                patch("scripts.charlie_mission_admission_guard.EXTERNAL_ADMISSION_PUBLIC_KEY_B64", public),
                contextlib.redirect_stdout(output),
            ):
                self.assertEqual(issue_pr_main(args, environ=environ), 0, output.getvalue())
            self.assertEqual(len(calls), expected_writes)
        self.assertTrue(calls[0].startswith("Preserve this text."))
        self.assertEqual(calls[0].count("Mission-Admission-Receipt-B64:"), 1)
        self.assertNotIn("not-logged", output.getvalue())
        self.assertNotIn(base64.b64encode(seed).decode(), output.getvalue())

    def test_recording_and_issuer_share_deterministic_payload_and_receipt_identity(self):
        captured_at = "2026-08-28T09:00:00Z"
        contract = {
            "allowed_files": ALLOWED_FILES, "forbidden_files": ["app.py"],
            "allowed_effects": ALLOWED_EFFECTS, "forbidden_effects": FORBIDDEN_EFFECTS,
            "required_tests": sorted(BOOTSTRAP_REQUIRED_TESTS),
            "operational_acceptance": ["Exact candidate CI passes."],
        }
        authority = {
            "root_mission_id": "CMQ-20260813-05", "latest_correction_digest": "1" * 64,
            "collision_observed_at": captured_at, "active_claims": [],
            "collision_snapshot_sha256": collision_snapshot_digest(captured_at, []),
            "admission": {"status": "valid", "mission_id": "CMQ-20260813-05",
                          "root_mission_id": "CMQ-20260813-05", "generation": GENERATION,
                          "base_sha": BASE, "head_sha": HEAD,
                          "authority_key_sha256": hashlib.sha256(KEY).hexdigest(),
                          "latest_correction_digest": "1" * 64,
                          "collision_snapshot_sha256": collision_snapshot_digest(captured_at, [])},
        }
        kwargs = dict(
            mission={"mission_id": "CMQ-20260813-05", "raw_text": "owner"},
            family={"generation": GENERATION}, authority=authority, contract=contract,
            base=BASE, head=HEAD, branch="cursor/mission-admission-test",
            diff_sha256="2" * 64, changed_files=ALLOWED_FILES,
            governance_reads=[_governance_row()],
            repository="Crewless9086/amadeus-pig-tracking-system",
        )
        recorded_payload = _build_exact_candidate_payload(**kwargs)
        issued_payload = _build_exact_candidate_payload(**copy.deepcopy(kwargs))
        self.assertEqual(recorded_payload, issued_payload)
        issued_at = "2026-08-28T09:00:00Z"
        expires_at = "2026-08-29T09:00:00Z"
        recorded = sign_mission_admission_receipt(recorded_payload, KEY, issued_at=issued_at, expires_at=expires_at)
        issued = sign_mission_admission_receipt(issued_payload, KEY, issued_at=issued_at, expires_at=expires_at)
        self.assertEqual(recorded["receipt_id"], issued["receipt_id"])
        self.assertEqual(recorded["content_sha256"], issued["content_sha256"])

    def test_current_authority_reports_field_specific_mismatch_reasons(self):
        receipt = self._signed()["receipt"]
        contract = {
            "allowed_files": receipt["scope"]["allowed_files"],
            "forbidden_files": receipt["scope"]["forbidden_files"],
            "allowed_effects": receipt["scope"]["allowed_effects"],
            "forbidden_effects": receipt["scope"]["forbidden_effects"],
            "required_tests": receipt["required_tests"],
            "operational_acceptance": receipt["operational_acceptance"]["requirements"],
        }
        authority = {
            "mission_id": receipt["mission"]["mission_id"],
            "root_mission_id": receipt["mission"]["root_mission_id"],
            "latest_correction_digest": receipt["owner_instruction_chain"]["latest_correction_digest"],
            "collision_snapshot_sha256": receipt["collision_snapshot"]["snapshot_sha256"],
            "admission": {
                "status": "valid", "mission_id": receipt["mission"]["mission_id"],
                "root_mission_id": receipt["mission"]["root_mission_id"],
                "generation": receipt["mission"]["generation"],
                "base_sha": receipt["repository"]["base_sha"],
                "head_sha": receipt["candidate"]["head_sha"],
                "authority_key_sha256": receipt["authority_key_sha256"],
                "latest_correction_digest": receipt["owner_instruction_chain"]["latest_correction_digest"],
                "collision_snapshot_sha256": receipt["collision_snapshot"]["snapshot_sha256"],
                "receipt_id": receipt["receipt_id"], "content_sha256": receipt["content_sha256"],
            },
        }
        receipt["owner_instruction_chain"]["admission_packet_sha256"] = _canonical_packet_digest(authority, contract)
        cases = (
            ("receipt_content_mismatch", lambda r, a, c: a["admission"].update(receipt_id="MAR-" + "0" * 64)),
            ("admission_packet_mismatch", lambda r, a, c: r["owner_instruction_chain"].update(admission_packet_sha256="0" * 64)),
            ("scope_mismatch", lambda r, a, c: c.update(allowed_files=["other.py"])),
            ("required_test_mismatch", lambda r, a, c: c.update(required_tests=["other"])),
            ("operational_acceptance_mismatch", lambda r, a, c: c.update(operational_acceptance=["other"])),
        )
        for reason, mutate in cases:
            candidate, current, expected = copy.deepcopy(receipt), copy.deepcopy(authority), copy.deepcopy(contract)
            mutate(candidate, current, expected)
            with self.subTest(reason=reason), self.assertRaisesRegex(MissionAdmissionError, reason):
                _compare_current_authority(candidate, current, expected)

    def test_issuer_rejects_wrong_head_closed_pr_and_duplicate_markers(self):
        cases = (
            ({"state": "closed", "merged_at": None, "base": {}, "head": {}}, HEAD, "issuer_target_not_open"),
            ({"state": "open", "merged_at": None, "base": {"ref": "main", "sha": BASE}, "head": {"ref": "x", "sha": "c" * 40}}, HEAD, "admission_candidate_changed"),
        )
        import contextlib
        for pull, expected, reason in cases:
            output = io.StringIO()
            with (
                patch("scripts.charlie_mission_admission_guard._protected_database_url", return_value="postgres://readonly?sslmode=require"),
                patch("scripts.charlie_mission_admission_guard._github_pull_request", return_value=pull),
                contextlib.redirect_stdout(output),
            ):
                code = issue_pr_main(SimpleNamespace(pull_request_number=1, expected_head_sha=expected, event_output=None), environ={"GITHUB_TOKEN": "token"})
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())["reason_code"], reason)
        with self.assertRaisesRegex(MissionAdmissionError, "duplicate_external_admission_receipts"):
            _replace_receipt_marker(
                "Mission-Admission-Receipt-B64: one\nMission-Admission-Receipt-B64: two\n",
                "three",
            )

    def test_canonical_review_linkage_rejects_pr_branch_head_diff_and_files_transplant(self):
        metadata = {"review_packet": {
            "pr_number": 1312, "candidate_revision": HEAD,
            "branch_name": "cursor/mission-admission-test",
            "candidate_diff_sha256": "d" * 64, "changed_files": ALLOWED_FILES,
        }}
        _require_canonical_review_linkage(metadata, 1312, HEAD, "cursor/mission-admission-test", "d" * 64, ALLOWED_FILES)
        cases = (
            (1313, HEAD, "cursor/mission-admission-test", "d" * 64, ALLOWED_FILES),
            (1312, HEAD, "other", "d" * 64, ALLOWED_FILES),
            (1312, "c" * 40, "cursor/mission-admission-test", "d" * 64, ALLOWED_FILES),
            (1312, HEAD, "cursor/mission-admission-test", "e" * 64, ALLOWED_FILES),
            (1312, HEAD, "cursor/mission-admission-test", "d" * 64, ["other.py"]),
        )
        for args in cases:
            with self.subTest(args=args), self.assertRaisesRegex(MissionAdmissionError, "canonical_candidate_linkage_changed"):
                _require_canonical_review_linkage(metadata, *args)

    def test_protected_database_rejects_timeout_and_admin_privilege(self):
        class Cursor:
            def __init__(self, mode): self.mode, self.sql = mode, ""
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def execute(self, sql, params=None): self.sql = sql.lower()
            def fetchone(self):
                if "transaction_read_only" in self.sql: return ("on",)
                if "statement_timeout" in self.sql: return (("0" if self.mode == "timeout" else "10s"),)
                if "lock_timeout" in self.sql: return ("3s",)
                if "idle_in_transaction" in self.sql: return ("10s",)
                if "from pg_roles" in self.sql: return ((True, False, False, False, False) if self.mode == "admin" else (False,) * 5)
                if "has_database_privilege" in self.sql: return (False, False)
                if "has_table_privilege" in self.sql: return (True, False)
                raise AssertionError(self.sql)
        class Connection:
            def __init__(self, mode): self.mode = mode
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def cursor(self): return Cursor(self.mode)
        for mode, reason in (("timeout", "canonical_database_timeout_invalid"), ("admin", "canonical_database_privilege_invalid")):
            fake = SimpleNamespace(connect=lambda *_args, **_kwargs: Connection(mode))
            with self.subTest(mode=mode), patch.dict(sys.modules, {"psycopg": fake}), self.assertRaisesRegex(MissionAdmissionError, reason):
                _protected_database_url({"CHARLIE_ADMISSION_READ_DATABASE_URL": "postgres://redacted?sslmode=require"})


class MissionAdmissionStoreTests(unittest.TestCase):
    def test_collision_snapshot_time_is_stable_across_projection_updates(self):
        correction = {"recorded_at": "2026-08-28T09:00:00Z"}
        self.assertEqual(
            _mission_admission_collision_observed_at(
                correction, "2026-08-28T09:01:00+00:00"
            ),
            "2026-08-28T09:00:00Z",
        )
        self.assertEqual(
            _mission_admission_collision_observed_at(
                correction, "2026-08-28T10:01:00+00:00"
            ),
            "2026-08-28T09:00:00Z",
        )

    def test_append_uses_existing_event_fabric_and_updates_projection_transactionally(self):
        cursor = AdmissionStoreCursor()
        connection = AdmissionStoreConnection(cursor)
        admission = _admission_projection()
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
            **_admission_projection(),
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
            },
            correction_payload={
                "event_type": "owner_correction_recorded",
                "summary": "Correct the rejected candidate.",
                "corrects_event_id": "PR1307-REJECTED",
                "idempotency_key": "PR1307-SEND-BACK",
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
            "insert into public.charlie_mission_events" in sql
            for sql, _ in cursor.executed
        ))

    def test_unauthenticated_correction_is_rejected_before_database_access(self):
        result, status = invalidate_mission_admission_for_owner_correction(
            "CMQ-20260813-05",
            "changed",
            owner_authentication={},
            correction_payload={},
            database_url="postgres://test",
            connect_factory=lambda _: self.fail("database must not be accessed"),
        )
        self.assertEqual(status, 403)
        self.assertEqual(result["status"], "authenticated_owner_correction_required")

    def test_consume_revoke_and_replay_are_explicit(self):
        current = {
            **_admission_projection(),
            "status": "valid",
            "recorded_by": "authority",
        }
        consume_cursor = AdmissionStoreCursor({"mission_admission": current})
        connection = AdmissionStoreConnection(consume_cursor)
        consumed, status = consume_mission_admission(
            "CMQ-20260813-05",
            current["receipt_id"],
            authenticated_principal="execution-bridge",
            database_url="postgres://test",
            connect_factory=lambda _: connection,
        )
        self.assertEqual(status, 201)
        self.assertEqual(consumed["admission"]["status"], "consumed")
        replay, replay_status = consume_mission_admission(
            "CMQ-20260813-05",
            current["receipt_id"],
            authenticated_principal="execution-bridge",
            database_url="postgres://test",
            connect_factory=lambda _: connection,
        )
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "exact_replay")

        revoke_cursor = AdmissionStoreCursor({"mission_admission": current})
        revoked, revoked_status = revoke_mission_admission(
            "CMQ-20260813-05",
            current["receipt_id"],
            owner_authentication={
                "authenticated": True,
                "principal_type": "owner_admin",
                "principal_id": "owner-charl",
            },
            database_url="postgres://test",
            connect_factory=lambda _: AdmissionStoreConnection(revoke_cursor),
        )
        self.assertEqual(revoked_status, 201)
        self.assertEqual(revoked["admission"]["status"], "revoked")

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


@unittest.skipUnless(
    os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip(),
    "CHARLIE_DISPOSABLE_POSTGRES_URL is required",
)
class MissionAdmissionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg

        cls.psycopg = psycopg
        cls.url = os.environ["CHARLIE_DISPOSABLE_POSTGRES_URL"].strip()
        with psycopg.connect(cls.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select current_database()")
                database_name = cursor.fetchone()[0]
                if "mission_admission_test" not in database_name:
                    raise unittest.SkipTest(
                        "refusing non-disposable PostgreSQL database"
                    )
                cursor.execute("""
                    drop table if exists public.operational_events cascade;
                    drop table if exists public.charlie_mission_events cascade;
                    drop table if exists public.charlie_missions cascade;
                    create table public.charlie_missions (
                        mission_id text primary key,
                        status text not null,
                        metadata_json jsonb not null default '{}'::jsonb,
                        updated_at timestamptz not null default now()
                    );
                    create table public.charlie_mission_events (
                        event_id text primary key,
                        mission_id text not null,
                        event_type text not null,
                        notes text,
                        recorded_by text,
                        metadata_json jsonb not null default '{}'::jsonb,
                        created_at timestamptz not null default now()
                    );
                    create table public.operational_events (
                        event_id text primary key,
                        idempotency_key text unique not null,
                        schema_version text not null,
                        event_type text not null,
                        domain text not null,
                        aggregate_type text not null,
                        aggregate_id text not null,
                        source_system text not null,
                        source_record_id text,
                        authority_tier text not null,
                        privacy_class text not null,
                        actor_type text not null,
                        actor_id text,
                        correlation_id text,
                        causation_id text,
                        occurred_at timestamptz not null,
                        recorded_at timestamptz not null,
                        freshness_at timestamptz not null,
                        payload_json jsonb not null,
                        provenance_json jsonb not null
                    );
                """)

    def setUp(self):
        with self.psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    drop trigger if exists reject_admission_projection
                        on public.charlie_missions;
                    drop function if exists public.reject_admission_projection();
                    truncate public.operational_events,
                             public.charlie_mission_events,
                             public.charlie_missions;
                    insert into public.charlie_missions
                        (mission_id,status,metadata_json)
                    values (
                        'CMQ-20260813-05',
                        'paused',
                        '{"mission_family":{"root_mission_id":"CMQ-20260813-05"}}'
                    );
                """)

    def _record(self):
        result, status = append_mission_admission_event(
            "CMQ-20260813-05",
            _admission_projection(),
            authenticated_principal="control_tower_isolated_validator_v2",
            database_url=self.url,
        )
        self.assertEqual(status, 201, result)
        return result["admission"]

    def _correction(self, suffix="one"):
        return {
            "event_type": "owner_correction_recorded",
            "summary": f"Correct rejected candidate {suffix}.",
            "corrects_event_id": "PR1307-REJECTED-E358306B",
            "idempotency_key": f"PR1307-SEND-BACK-{suffix}",
        }

    def test_mission_bound_append_consume_revoke_and_replay(self):
        admission = self._record()
        with self.psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select count(*) from public.operational_events
                       where aggregate_id='CMQ-20260813-05'
                         and event_type='mission_admission_recorded'"""
                )
                self.assertEqual(cursor.fetchone()[0], 1)
                cursor.execute(
                    """select metadata_json->'mission_admission'->>'receipt_id'
                       from public.charlie_missions
                       where mission_id='CMQ-20260813-05'"""
                )
                self.assertEqual(cursor.fetchone()[0], admission["receipt_id"])
        replay, replay_status = append_mission_admission_event(
            "CMQ-20260813-05",
            _admission_projection(),
            authenticated_principal="control_tower_isolated_validator_v2",
            database_url=self.url,
        )
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "exact_replay")

        consumed, consumed_status = consume_mission_admission(
            "CMQ-20260813-05",
            admission["receipt_id"],
            authenticated_principal="execution-bridge",
            database_url=self.url,
        )
        self.assertEqual(consumed_status, 201, consumed)
        duplicate, duplicate_status = consume_mission_admission(
            "CMQ-20260813-05",
            admission["receipt_id"],
            authenticated_principal="execution-bridge",
            database_url=self.url,
        )
        self.assertEqual(duplicate_status, 200)
        self.assertEqual(duplicate["status"], "exact_replay")

        with self.psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """update public.charlie_missions
                       set metadata_json=jsonb_set(
                           metadata_json,
                           '{mission_admission,status}',
                           '"valid"'::jsonb
                       )"""
                )
        revoked, revoked_status = revoke_mission_admission(
            "CMQ-20260813-05",
            admission["receipt_id"],
            owner_authentication={
                "authenticated": True,
                "principal_type": "owner_admin",
                "principal_id": "owner-charl",
            },
            database_url=self.url,
        )
        self.assertEqual(revoked_status, 201, revoked)
        self.assertEqual(revoked["admission"]["status"], "revoked")

    def test_owner_correction_and_invalidation_commit_atomically(self):
        self._record()
        result, status = invalidate_mission_admission_for_owner_correction(
            "CMQ-20260813-05",
            "corrected-generation",
            owner_authentication={
                "authenticated": True,
                "principal_type": "owner_admin",
                "principal_id": "owner-charl",
            },
            correction_payload=self._correction(),
            database_url=self.url,
        )
        self.assertEqual(status, 201, result)
        replay, replay_status = invalidate_mission_admission_for_owner_correction(
            "CMQ-20260813-05",
            "corrected-generation",
            owner_authentication={
                "authenticated": True,
                "principal_type": "owner_admin",
                "principal_id": "owner-charl",
            },
            correction_payload=self._correction(),
            database_url=self.url,
        )
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "exact_replay")
        authority, authority_status = read_current_mission_admission_authority(
            "CMQ-20260813-05",
            database_url=self.url,
        )
        self.assertEqual(authority_status, 200, authority)
        self.assertEqual(
            authority["latest_correction_digest"],
            result["correction_digest"],
        )
        self.assertEqual(
            authority["root_mission_id"],
            "CMQ-20260813-05",
        )
        with self.psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select
                           metadata_json->'mission_admission'->>'status',
                           metadata_json->'mission_admission'
                             ->>'replacement_generation'
                       from public.charlie_missions
                       where mission_id='CMQ-20260813-05'"""
                )
                self.assertEqual(
                    cursor.fetchone(),
                    ("invalidated", "corrected-generation"),
                )
                cursor.execute(
                    """select count(*) from public.charlie_mission_events
                       where event_type='owner_correction_recorded'"""
                )
                self.assertEqual(cursor.fetchone()[0], 1)
                cursor.execute(
                    """select count(*) from public.operational_events
                       where event_type='mission_admission_invalidated'"""
                )
                self.assertEqual(cursor.fetchone()[0], 1)

    def test_projection_failure_rolls_back_correction_and_invalidation_events(self):
        self._record()
        with self.psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("""
                    create function public.reject_admission_projection()
                    returns trigger language plpgsql as $$
                    begin
                        if new.metadata_json->'mission_admission'->>'status'
                           = 'invalidated' then
                            raise exception 'injected projection failure';
                        end if;
                        return new;
                    end $$;
                    create trigger reject_admission_projection
                    before update on public.charlie_missions
                    for each row execute function
                        public.reject_admission_projection();
                """)
        result, status = invalidate_mission_admission_for_owner_correction(
            "CMQ-20260813-05",
            "rollback-generation",
            owner_authentication={
                "authenticated": True,
                "principal_type": "owner_admin",
                "principal_id": "owner-charl",
            },
            correction_payload=self._correction("rollback"),
            database_url=self.url,
        )
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "mission_admission_invalidation_failed")
        with self.psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """select metadata_json->'mission_admission'->>'status'
                       from public.charlie_missions"""
                )
                self.assertEqual(cursor.fetchone()[0], "valid")
                cursor.execute(
                    """select count(*) from public.charlie_mission_events
                       where event_type='owner_correction_recorded'"""
                )
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute(
                    """select count(*) from public.operational_events
                       where event_type='mission_admission_invalidated'"""
                )
                self.assertEqual(cursor.fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
