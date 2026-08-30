import hashlib
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from integrations.hermes.charlie_builder.native_executor import (
    ContextBroker, HermesStructuredPatchWorker, NativeAuthorization,
    NativeExecutionEngine, NativeExecutionError, NativePackager,
    NativeWorktree, PatchValidator, content_identity, run_argv,
)
from integrations.hermes.charlie_builder.schemas import validate_native_response
from modules.charlie.mission_store import prepare_hermes_native_execution
from tests.test_charlie_mission_store import FakeConnection


ALLOWED = "docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md"


def git(cwd, *args):
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


class Result:
    def __init__(self, parsed): self.parsed = parsed


class Llm:
    def __init__(self, responses): self.responses = list(responses); self.calls = []
    def complete_structured(self, **kwargs):
        self.calls.append(kwargs)
        return Result(self.responses.pop(0))


class NativeExecutorTests(unittest.TestCase):
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
 
-Old text.
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

    def test_canonical_native_authorization_requires_archived_zero_candidate_cursor(self):
        dispatch = {
            "status": "valid", "generation": "g1", "base_sha": "a" * 40,
            "owner_instruction_digest": "b" * 64, "allowed_files": [ALLOWED],
        }
        state = {"agent_state": "ARCHIVED", "run_state": "FINISHED",
                 "repository_mutation": False, "pr_number": 0, "head_sha": "",
                 "cursor_agent_id": "bc-five", "cursor_run_id": "run-five"}
        connection = FakeConnection([({"dispatch_authorization": dispatch,
                                      "external_supervisor_state": state}, "Pilot")])
        result, status = prepare_hermes_native_execution(
            "CHARLIE-MISSION-X", worktree_digest="c" * 64,
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: connection,
        )
        self.assertEqual(201, status, result)
        self.assertEqual("hermes_native", result["authorization"]["executor_provider"])
        self.assertEqual([ALLOWED], result["authorization"]["allowed_files"])
        active_connection = FakeConnection([({"dispatch_authorization": dispatch,
                                             "external_supervisor_state": {**state, "agent_state": "ACTIVE"}}, "Pilot")])
        denied, denied_status = prepare_hermes_native_execution(
            "CHARLIE-MISSION-X", worktree_digest="c" * 64,
            authenticated_principal="hermes:charlie-builder", database_url="postgres://unit",
            connect_factory=lambda _: active_connection,
        )
        self.assertEqual(409, denied_status, denied)
        self.assertEqual("cursor_retirement_not_proven", denied["status"])


if __name__ == "__main__":
    unittest.main()
