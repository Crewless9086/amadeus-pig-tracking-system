import hashlib
import json
import os
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from pathlib import Path

from integrations.hermes.charlie_builder.native_executor import (
    ContextBroker, HermesStructuredPatchWorker, NativeAuthorization,
    HermesIndependentReviewer,
    NativeExecutionEngine, NativeExecutionError, NativePackager,
    NativeWorktree, PatchValidator, content_identity, run_argv,
    validate_primary_repository,
)
from integrations.hermes.charlie_builder.protocol import (
    ProtocolError, canonical_candidate_diff as plugin_candidate_diff,
)
from modules.charlie.mission_admission import canonical_candidate_diff as backend_candidate_diff
from integrations.hermes.charlie_builder.schemas import validate_native_response
from modules.charlie.mission_store import prepare_hermes_native_execution
from modules.charlie.mission_store import (
    bind_external_supervisor_candidate, list_resumable_hermes_native_executions,
    record_hermes_native_execution_state, retire_cursor_provider_execution,
)
from tests.test_charlie_mission_store import FakeConnection


ALLOWED = "docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"


def git(cwd, *args):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class Result:
    _sequence = 0
    def __init__(self, parsed, *, task="charlie_native_builder",
                 purpose="charlie.native.builder", schema_name="charlie.native.patch.v1"):
        Result._sequence += 1
        self.parsed = parsed
        self.provider = "test-provider"
        self.model = "test-model"
        self.agent_id = "default"
        self.audit = {"profile": "", "plugin_id": "charlie-builder", "task": task,
                      "purpose": purpose, "schema_name": schema_name}


class Llm:
    def __init__(self, responses): self.responses = list(responses); self.calls = []
    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        return Result(self.responses.pop(0), task=kwargs.get("task", ""),
                      purpose=kwargs.get("purpose", ""), schema_name=kwargs.get("schema_name", ""))


class NativeExecutorTests(unittest.TestCase):
    def test_isolated_candidate_diff_protocol_matches_backend(self):
        cases = [
            (["docs/a.md"], b"diff --git a/docs/a.md b/docs/a.md\n"),
            (["tests/b.py", "docs/a.md"], "unicode: vark\u2713\n"),
            (["docs/a.md"], "line one\r\nline two\r\n"),
            (["docs/a.md"], "line one\nline two\n"),
        ]
        for files, patch_bytes in cases:
            normalized = sorted(files)
            self.assertEqual(
                backend_candidate_diff(normalized, patch_bytes),
                plugin_candidate_diff(files, patch_bytes),
            )
        with self.assertRaises(ProtocolError):
            plugin_candidate_diff([], b"")
        with self.assertRaises(ProtocolError):
            plugin_candidate_diff(["../secret"], b"")

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "repo"
        self.root.mkdir()
        git(self.root, "init")
        git(self.root, "config", "user.email", "charlie@example.invalid")
        git(self.root, "config", "user.name", "CHARLIE Tests")
        git(self.root, "remote", "add", "origin", "https://github.com/Crewless9086/amadeus-pig-tracking-system.git")
        target = self.root / ALLOWED
        target.parent.mkdir(parents=True)
        target.write_text("# Bridge\n\nOld text.\n", encoding="utf-8")
        git(self.root, "add", ALLOWED)
        git(self.root, "commit", "-m", "base")
        git(self.root, "branch", "-M", "main")
        self.base = git(self.root, "rev-parse", "HEAD")
        self.worktree = Path(self.temp.name) / "worktrees" / "mission" / "g1" / "native-1"
        self.execution_id, self.branch = content_identity("CHARLIE-MISSION-X", "g1")
        self.authorization = NativeAuthorization.from_mapping({
            "mission_id": "CHARLIE-MISSION-X", "generation": "g1",
            "native_execution_id": self.execution_id, "native_attempt": 1,
            "repository": "Crewless9086/amadeus-pig-tracking-system",
            "starting_main_sha": self.base, "branch": self.branch,
            "worktree_digest": hashlib.sha256(str(self.worktree.resolve()).encode()).hexdigest(),
            "owner_instruction_digest": "a" * 64, "allowed_files": [ALLOWED],
            "allowed_commands": ["git status", "git diff", "git diff --check"],
            "allowed_effects": ["edit_allowed_files", "open_draft_pull_request"],
            "forbidden_effects": ["merge", "deploy"], "status": "valid",
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
        })

    def tearDown(self):
        self.temp.cleanup()

    def test_identity_and_worktree_are_deterministic_and_isolated(self):
        first = NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        self.assertEqual(self.worktree, first)
        self.assertEqual(self.branch, git(first, "branch", "--show-current"))
        self.assertEqual(self.base, git(first, "rev-parse", "HEAD"))
        self.assertEqual(first, NativeWorktree(self.root, self.worktree, self.authorization).ensure())

    def test_commissioned_repository_identity_is_verified_before_execution(self):
        root, base, head = validate_primary_repository(self.root, self.worktree.parent)
        self.assertEqual(self.root.resolve(), root)
        self.assertEqual(self.worktree.parent.resolve(), base)
        self.assertEqual(self.base, head)

    def test_missing_or_wrong_repository_fails_closed(self):
        with self.assertRaisesRegex(NativeExecutionError, "native_repository_missing"):
            validate_primary_repository(self.root / "obsolete", self.worktree.parent)
        git(self.root, "remote", "set-url", "origin", "https://github.com/example/wrong.git")
        with self.assertRaisesRegex(NativeExecutionError, "native_repository_identity_invalid"):
            validate_primary_repository(self.root, self.worktree.parent)

    def test_restart_reuses_same_dirty_and_committed_worktree(self):
        first = NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        (first / ALLOWED).write_text("# Bridge\n\nBounded edit.\n", encoding="utf-8")
        self.assertEqual(first, NativeWorktree(self.root, self.worktree, self.authorization).ensure())
        git(first, "add", ALLOWED)
        git(first, "commit", "-m", "docs: bounded edit")
        self.assertEqual(first, NativeWorktree(self.root, self.worktree, self.authorization).ensure())

    def test_restart_rejects_out_of_scope_dirty_file(self):
        first = NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        (first / "unexpected.txt").write_text("drift", encoding="utf-8")
        with self.assertRaisesRegex(NativeExecutionError, "native_worktree_recovery_conflict"):
            NativeWorktree(self.root, self.worktree, self.authorization).ensure()

    def test_model_has_no_tools_or_credentials_and_patch_is_bounded(self):
        NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        patch = """diff --git a/docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md b/docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md
--- a/docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md
+++ b/docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md
@@ -1,3 +1,3 @@
 # Bridge
""" + " \n" + """-Old text.
+Hermes supervises development but cannot merge or deploy.
"""
        llm = Llm([{"state": "PATCH_READY", "context_paths": [], "unified_diff": patch,
                    "test_proposal": ["git diff --check"], "reason": ""}])
        result = NativeExecutionEngine(
            HermesStructuredPatchWorker(llm), self.root, self.worktree, self.authorization,
        ).build_patch("Clarify the boundary")
        self.assertEqual([ALLOWED], result["changed_files"])
        call = llm.calls[0]
        self.assertNotIn("tools", call)
        packet = json.loads(call["input"][0]["text"])
        self.assertNotIn("environment", packet)
        self.assertNotIn("credentials", packet)
        self.assertTrue(result["worker_identity"].startswith("HNW-"))
        self.assertEqual("default", result["worker_agent_id"])

    def test_independent_role_reviewers_receive_fresh_bounded_packets(self):
        llm = Llm([
            {"verdict": "SEND_BACK", "findings": ["Clarify the no-deploy boundary."]},
            {"verdict": "APPROVE", "findings": []},
        ])
        reviewer = HermesIndependentReviewer(llm)
        packet = {"candidate": {"pr_number": 9, "base_sha": "b" * 40,
            "head_sha": "a" * 40, "candidate_diff_sha256": "c" * 64,
            "changed_files": [ALLOWED], "diff": "bounded"}}
        security = reviewer.review("SECURITY", packet)
        functional = reviewer.review("FUNCTIONAL", packet)
        self.assertEqual("SEND_BACK", security["verdict"])
        self.assertEqual("APPROVE", functional["verdict"])
        self.assertNotEqual(security["reviewer_identity"], functional["reviewer_identity"])
        self.assertEqual("default", security["reviewer_agent_id"])
        self.assertEqual("default", functional["reviewer_agent_id"])
        self.assertEqual(packet["candidate"]["head_sha"],
                         security["candidate_binding"]["head_sha"])
        self.assertTrue(all("tools" not in call for call in llm.calls))
        self.assertEqual(["charlie_native_security_reviewer", "charlie_native_functional_reviewer"],
                         [call["task"] for call in llm.calls])

    def test_host_role_audit_identity_fails_closed_on_wrong_contract(self):
        packet = {"candidate": {"pr_number": 9, "base_sha": "b" * 40,
            "head_sha": "a" * 40, "candidate_diff_sha256": "c" * 64,
            "changed_files": [ALLOWED], "diff": "bounded"}}
        for field, value in (
            ("task", "charlie_native_builder"), ("task", ""),
            ("plugin_id", "other-plugin"), ("purpose", "wrong"),
            ("schema_name", "wrong.schema"),
        ):
            class BadLlm:
                def complete_structured(self, **kwargs):
                    result = Result({"verdict": "APPROVE", "findings": []},
                                    task=kwargs["task"], purpose=kwargs["purpose"],
                                    schema_name=kwargs["schema_name"])
                    result.audit[field] = value
                    return result
            with self.subTest(field=field, value=value), self.assertRaisesRegex(
                    NativeExecutionError, "native_runtime_role_audit_invalid"):
                HermesIndependentReviewer(BadLlm()).review("SECURITY", packet)

    def test_context_and_patch_security_fail_closed(self):
        NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        with self.assertRaisesRegex(NativeExecutionError, "native_context_path_forbidden"):
            ContextBroker(self.worktree, [ALLOWED]).read([".env"])
        for bad in (
            "--- a/.github/workflows/x.yml\n+++ b/.github/workflows/x.yml\n@@ -0,0 +1 @@\n+x\n",
            "GIT binary patch\n",
            "--- a/../escape\n+++ b/../escape\n@@ -0,0 +1 @@\n+x\n",
        ):
            with self.assertRaises(NativeExecutionError):
                PatchValidator(self.worktree, [ALLOWED]).validate(bad)

    def test_real_symlink_context_is_rejected_before_resolution(self):
        NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        secret = Path(self.temp.name) / "outside.txt"
        secret.write_text("outside", encoding="utf-8")
        link = self.worktree / "linked.txt"
        try:
            link.symlink_to(secret)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        git(self.worktree, "add", "linked.txt")
        with self.assertRaisesRegex(NativeExecutionError, "native_context_file_invalid"):
            ContextBroker(self.worktree, [ALLOWED]).read(["linked.txt"])

    def test_symlinked_worktree_path_is_rejected_before_resolution(self):
        real_parent = Path(self.temp.name) / "real-worktrees"
        real_parent.mkdir()
        linked_parent = Path(self.temp.name) / "linked-worktrees"
        try:
            linked_parent.symlink_to(real_parent, target_is_directory=True)
        except OSError as exc:
            self.skipTest(f"symlinks unavailable: {exc}")
        requested = linked_parent / "mission" / "g1" / "native-1"
        mapping = {**self.authorization.__dict__,
                   "worktree_digest": hashlib.sha256(str(requested.resolve()).encode()).hexdigest()}
        with self.assertRaisesRegex(NativeExecutionError, "native_worktree_symlink_rejected"):
            NativeWorktree(self.root, requested, mapping)

    def test_context_limits_are_cumulative_across_rounds(self):
        NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        broker = ContextBroker(self.worktree, [ALLOWED], max_bytes=10)
        with self.assertRaisesRegex(NativeExecutionError, "native_context_size_limit"):
            broker.read([ALLOWED])

    def test_protocol_limits_context_and_blocked_shapes(self):
        self.assertEqual("BLOCKED", validate_native_response({
            "state": "BLOCKED", "context_paths": [], "unified_diff": "",
            "test_proposal": [], "reason": "insufficient evidence",
        })["state"])
        with self.assertRaises(ValueError):
            validate_native_response({"state": "PATCH_READY", "context_paths": [],
                                      "unified_diff": "", "test_proposal": [], "reason": ""})

    def test_run_argv_never_uses_shell_or_inherits_secret_environment(self):
        result = run_argv(["git", "status", "--short"], cwd=self.root)
        self.assertEqual(0, result.returncode)

    def test_packager_requires_protected_parent_token(self):
        NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        with self.assertRaisesRegex(NativeExecutionError, "github_packager_token_required"):
            NativePackager(self.worktree, self.authorization, "")

    def test_parent_packager_commits_and_binds_complete_candidate_without_token_in_argv(self):
        root = NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        (root / ALLOWED).write_text("# Bridge\n\nPackaged.\n", encoding="utf-8")
        packager = NativePackager(root, self.authorization, "protected-token")
        observed_argv = []
        def push():
            observed_argv.append(["git", "push", "-u", "origin", self.branch])
        packager._push_with_ephemeral_askpass = push
        packager._find_pull = lambda _branch: None
        def github(_method, _path, _payload=None):
            return {"number": 7, "draft": True, "html_url": "https://example.invalid/7",
                    "head": {"sha": git(root, "rev-parse", "HEAD")}}
        packager._github = github
        result = packager.package("docs: clarify boundary", "bounded")
        self.assertEqual([ALLOWED], result["changed_files"])
        self.assertEqual(64, len(result["candidate_diff_sha256"]))
        self.assertNotIn("protected-token", json.dumps(observed_argv))

    def test_parent_packager_recovers_allowed_patch_already_staged_before_crash(self):
        root = NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        (root / ALLOWED).write_text("# Bridge\n\nStaged recovery.\n", encoding="utf-8")
        git(root, "add", ALLOWED)
        packager = NativePackager(root, self.authorization, "protected-token")
        packager._push_with_ephemeral_askpass = lambda: None
        packager._find_pull = lambda _branch: None
        packager._github = lambda *_args: {"number": 7, "draft": True,
            "html_url": "https://example.invalid/7",
            "head": {"sha": git(root, "rev-parse", "HEAD")}}
        result = packager.package("docs: recover staged correction", "bounded")
        self.assertEqual([ALLOWED], result["changed_files"])
        self.assertNotEqual(self.base, result["commit_sha"])

    def test_packager_token_is_not_in_child_environment_or_persisted_after_failure(self):
        root = NativeWorktree(self.root, self.worktree, self.authorization).ensure()
        packager = NativePackager(root, self.authorization, "protected-token")
        observed = {}
        def fail_push(argv, **kwargs):
            observed.update({"argv": argv, "env": kwargs.get("env") or {}})
            return subprocess.CompletedProcess(argv, 1, "", "bounded failure")
        with patch("integrations.hermes.charlie_builder.native_executor.run_argv", side_effect=fail_push):
            with self.assertRaisesRegex(NativeExecutionError, "native_packaging_push_failed") as caught:
                packager._push_with_ephemeral_askpass()
        serialized = json.dumps(observed, sort_keys=True)
        self.assertNotIn("protected-token", serialized)
        self.assertNotIn("protected-token", str(caught.exception))
        helper = Path(observed["env"]["GIT_ASKPASS"])
        self.assertFalse(helper.exists())
        self.assertFalse(helper.parent.exists())

    def test_canonical_native_authorization_requires_archived_zero_candidate_cursor(self):
        problem = "Pilot"
        dispatch = {
            "version": "charlie_pre_dispatch_authorization_v2", "status": "valid",
            "mission_id": "CHARLIE-MISSION-X", "generation": "g1", "execution_attempt": 5,
            "repository": "Crewless9086/amadeus-pig-tracking-system",
            "base_sha": "d" * 40, "authorization_id": "PDA-" + "A" * 64,
            "expires_at": (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            "owner_instruction_digest": hashlib.sha256(problem.encode()).hexdigest(),
            "allowed_files": [ALLOWED],
            "allowed_effects": ["create_feature_branch", "edit_allowed_documentation", "run_tests",
                "commit_feature_branch", "push_feature_branch", "open_or_update_draft_pr",
                "request_independent_review"],
        }
        state = {"agent_state": "ARCHIVED", "run_state": "FINISHED",
                 "repository_mutation": False, "pr_number": 0, "head_sha": "",
                 "remote_branch_created": False, "exact_candidate": "absent",
                 "cursor_agent_id": "bc-five", "cursor_run_id": "run-five"}
        retirement = {"provider_status": "UNSUITABLE_FOR_CURRENT_BUILDER_CONTRACT",
            "agent_state": "ARCHIVED", "repository_mutation": False,
            "remote_branch_created": False, "pr_number": 0, "head_sha": "",
            "exact_candidate": "absent"}
        metadata = {"dispatch_authorization": dispatch, "external_supervisor_state": state,
                    "cursor_provider_retirement": retirement,
                    "mission_vault": {"problem_statement": problem}}
        connection = FakeConnection([(metadata, problem)])
        result, status = prepare_hermes_native_execution(
            "CHARLIE-MISSION-X", worktree_digest="c" * 64,
            starting_main_sha="d" * 40,
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: connection,
        )
        self.assertEqual(201, status, result)
        self.assertEqual("hermes_native", result["authorization"]["executor_provider"])
        self.assertEqual("d" * 40, result["authorization"]["starting_main_sha"])
        self.assertEqual("d" * 40, result["authorization"]["prior_cursor_authorization_base_sha"])
        self.assertEqual(dispatch["authorization_id"], result["authorization"]["dispatch_authorization_id"])
        self.assertEqual([ALLOWED], result["authorization"]["allowed_files"])
        written = [params for sql, params in connection.cursor_instance.executed
                   if "update public.charlie_missions" in sql][0]
        retirement = json.loads(written["metadata"])["cursor_provider_retirement"]
        self.assertEqual("ARCHIVED", retirement["agent_state"])
        self.assertEqual("FINISHED", retirement["run_state"])
        self.assertEqual("UNSUITABLE_FOR_CURRENT_BUILDER_CONTRACT", retirement["provider_status"])
        self.assertFalse(retirement["remote_branch_created"])
        self.assertEqual(0, retirement["pr_number"])
        self.assertEqual("", retirement["head_sha"])
        self.assertEqual("absent", retirement["exact_candidate"])
        self.assertFalse(retirement["valid_mission_admission"])
        self.assertEqual("cursor_provider_retired", retirement["event"])
        active_connection = FakeConnection([({**metadata,
            "external_supervisor_state": {**state, "agent_state": "ACTIVE"}}, problem)])
        denied, denied_status = prepare_hermes_native_execution(
            "CHARLIE-MISSION-X", worktree_digest="c" * 64,
            starting_main_sha="d" * 40,
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: active_connection,
        )
        self.assertEqual(409, denied_status, denied)
        self.assertEqual("cursor_retirement_not_proven", denied["status"])
        for invalid_dispatch in (
            {**dispatch, "expires_at": (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()},
            {**dispatch, "base_sha": "e" * 40},
        ):
            invalid_connection = FakeConnection([({**metadata,
                "dispatch_authorization": invalid_dispatch}, problem)])
            rejected, rejected_status = prepare_hermes_native_execution(
                "CHARLIE-MISSION-X", worktree_digest="c" * 64,
                starting_main_sha="d" * 40,
                authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
                connect_factory=lambda _, connection=invalid_connection: connection,
            )
            self.assertEqual(409, rejected_status, rejected)
            self.assertEqual("native_execution_authority_unavailable", rejected["status"])
            self.assertFalse(any("update public.charlie_missions" in sql
                                 for sql, _params in invalid_connection.cursor_instance.executed))

    def test_active_running_attempt_five_retires_once_after_verified_evidence(self):
        dispatch = {"status": "valid", "generation": "g1", "base_sha": "a" * 40,
                    "owner_instruction_digest": "b" * 64, "allowed_files": [ALLOWED]}
        current = {"generation": "g1", "execution_attempt": 5,
                   "cursor_agent_id": "bc-five", "cursor_run_id": "run-five",
                   "branch": "cursor/charlie-mission-setup-fb0a",
                   "agent_state": "ACTIVE", "run_state": "RUNNING",
                   "repository_mutation": False, "pr_number": 0, "head_sha": "",
                   "event": "cursor_implementation_started"}
        evidence = {"generation": "g1", "cursor_agent_id": "bc-five",
                    "cursor_run_id": "run-five", "execution_attempt": 5,
                    "provider_agent_state": "ARCHIVED", "provider_run_state": "FINISHED",
                    "branch": "cursor/charlie-mission-setup-fb0a",
                    "repository_mutation": False, "remote_branch_created": False,
                    "pr_number": 0, "head_sha": "", "exact_candidate": "absent"}
        connection = FakeConnection([({"dispatch_authorization": dispatch,
                                      "external_supervisor_state": current},)])
        result, status = retire_cursor_provider_execution(
            "CHARLIE-MISSION-X", evidence, authenticated_principal="hermes:charlie-builder",
            database_url="postgres://unit", connect_factory=lambda _: connection)
        self.assertEqual(201, status, result)
        self.assertEqual("cursor_provider_retired", result["status"])
        written = [params for sql, params in connection.cursor_instance.executed
                   if "update public.charlie_missions" in sql][0]
        metadata = json.loads(written["metadata"])
        self.assertEqual("ARCHIVED", metadata["external_supervisor_state"]["agent_state"])
        self.assertFalse(metadata["external_supervisor_state"]["remote_branch_created"])
        self.assertEqual("UNSUITABLE_FOR_CURRENT_BUILDER_CONTRACT",
                         metadata["cursor_provider_retirement"]["provider_status"])
        replay_connection = FakeConnection([(metadata,)])
        replay, replay_status = retire_cursor_provider_execution(
            "CHARLIE-MISSION-X", evidence, authenticated_principal="hermes:charlie-builder",
            database_url="postgres://unit", connect_factory=lambda _: replay_connection)
        self.assertEqual(200, replay_status, replay)
        self.assertEqual("exact_replay", replay["status"])
        conflict, conflict_status = retire_cursor_provider_execution(
            "CHARLIE-MISSION-X", {**evidence, "cursor_run_id": "run-other"},
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: FakeConnection([(metadata,)]))
        self.assertEqual(409, conflict_status, conflict)
        for conflict_metadata in (
            {"external_supervisor_state": {**current, "branch": "cursor/other"},
             "dispatch_authorization": dispatch},
            {"external_supervisor_state": {**current, "remote_branch_created": True},
             "dispatch_authorization": dispatch},
            {"external_supervisor_state": current, "dispatch_authorization": dispatch,
             "review_packet": {"candidate_revision": "d" * 40}},
        ):
            denied, denied_status = retire_cursor_provider_execution(
                "CHARLIE-MISSION-X", evidence, authenticated_principal="hermes:charlie-builder",
                database_url="postgres://unit",
                connect_factory=lambda _, row=conflict_metadata: FakeConnection([(row,)]))
            self.assertEqual(409, denied_status, denied)

    def test_gateway_restart_recovers_only_unfinished_canonical_native_execution(self):
        rows = [
            ("CMQ-A", "in_progress", {"hermes_native_execution": {"status": "valid",
                "native_execution_id": "HNX-A", "execution_status": "SUPERVISING"},
                "external_supervisor_state": {"slack_channel_id": "C1", "slack_thread_ts": "1.0"}}),
            ("CMQ-B", "in_progress", {"hermes_native_execution": {"status": "valid",
                "native_execution_id": "HNX-B", "execution_status": "OWNER_DECISION_REQUIRED"}}),
        ]
        result, status = list_resumable_hermes_native_executions(
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: FakeConnection(rows))
        self.assertEqual(200, status, result)
        self.assertEqual(["CMQ-A"], [item["mission_id"] for item in result["executions"]])

    def test_gateway_restart_discovers_one_pending_cursor_retirement(self):
        metadata = {
            "external_supervisor_state": {
                "execution_attempt": 5, "cursor_agent_id": "bc-five",
                "cursor_run_id": "run-five", "branch": "cursor/pilot",
                "slack_channel_id": "C1", "slack_thread_ts": "1.0",
                "repository_mutation": False, "pr_number": 0, "head_sha": "",
            },
            "dispatch_authorization": {"status": "valid"},
        }
        result, status = list_resumable_hermes_native_executions(
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: FakeConnection([("CMQ-PILOT", "in_progress", metadata)]))
        self.assertEqual(200, status, result)
        self.assertEqual(["cursor_retirement_pending"],
                         [item["resume_kind"] for item in result["executions"]])

        metadata["review_packet"] = {"candidate_revision": "a" * 40}
        denied, _ = list_resumable_hermes_native_executions(
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: FakeConnection([("CMQ-PILOT", "in_progress", metadata)]))
        self.assertEqual([], denied["executions"])

    def test_native_candidate_binding_uses_native_not_cursor_branch_authority(self):
        native = {
            "status": "valid", "generation": "g1", "starting_main_sha": "a" * 40,
            "branch": self.branch, "allowed_files": [ALLOWED],
            "allowed_effects": ["edit_allowed_files"], "forbidden_effects": ["merge", "deploy"],
        }
        binding = {
            "pr_number": 7, "branch_name": self.branch, "base_sha": "a" * 40,
            "head_sha": "b" * 40, "candidate_diff_sha256": "c" * 64,
            "changed_files": [ALLOWED], "generation": "g1", "allowed_files": [ALLOWED],
            "forbidden_files": ["*"], "allowed_effects": ["edit_allowed_files"],
            "forbidden_effects": ["merge", "deploy"], "required_tests": ["mission-admission"],
            "operational_acceptance": ["no merge"],
        }
        connection = FakeConnection([("in_progress", {"hermes_native_execution": native})])
        result, status = bind_external_supervisor_candidate(
            "CHARLIE-MISSION-X", binding, authenticated_principal="hermes:charlie-builder",
            database_url="postgres://unit", connect_factory=lambda _: connection)
        self.assertEqual(201, status, result)
        self.assertEqual("external_candidate_bound", result["status"])

    def test_canonical_writer_claim_rejects_another_live_process(self):
        current = {"native_execution_id": self.execution_id, "status": "valid",
                   "worker_claim_id": "HNC-first",
                   "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
        connection = FakeConnection([({"hermes_native_execution": current},)])
        result, status = record_hermes_native_execution_state(
            "CHARLIE-MISSION-X", {"native_execution_id": self.execution_id,
                "execution_status": "RUNNING", "worker_claim_id": "HNC-second",
                "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat(),
                "event": "native_writer_claimed"},
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: connection)
        self.assertEqual(409, status, result)
        self.assertEqual("native_writer_claim_conflict", result["status"])

    def test_canonical_recovery_progress_requires_and_accepts_matching_writer_claim(self):
        current = {"native_execution_id": self.execution_id, "status": "valid",
                   "worker_claim_id": "HNC-recovery",
                   "claim_expires_at": (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()}
        accepted, accepted_status = record_hermes_native_execution_state(
            "CHARLIE-MISSION-X", {"native_execution_id": self.execution_id,
                "execution_status": "CORRECTION_PACKAGED", "head_sha": "d" * 40,
                "worker_claim_id": "HNC-recovery", "event": "native_correction_packaged_recovered"},
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: FakeConnection([({"hermes_native_execution": current},)]))
        self.assertEqual(201, accepted_status, accepted)
        denied, denied_status = record_hermes_native_execution_state(
            "CHARLIE-MISSION-X", {"native_execution_id": self.execution_id,
                "execution_status": "CORRECTION_PACKAGED", "head_sha": "d" * 40,
                "event": "native_correction_packaged_recovered"},
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: FakeConnection([({"hermes_native_execution": current},)]))
        self.assertEqual(409, denied_status, denied)
        self.assertEqual("native_writer_claim_required", denied["status"])


if __name__ == "__main__":
    unittest.main()
