import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from modules.charlie.mission_admission import MissionAdmissionError
from modules.charlie.mission_admission_delivery import (
    RUNTIME_STATE_ENV,
    RUNTIME_MISSION_ENV,
    admitted_agent_environment,
    provision_mission_admission_runtime,
    start_admission_guard_server,
    stop_admission_guard_server,
    _stage_directory_atomically,
)
from modules.charlie.execution_bridge import _runner_with_admission
from scripts.charlie_mission_admission_guard import (
    STAGE2_ALLOWED_FILES,
    STAGE2_BASE_SHA,
    STAGE2_GENERATION,
    STAGE2_MISSION_ID,
    _references_trusted_authority,
    _trusted_state_root,
    _validated_trusted_identity,
    hook_main,
    issue_bootstrap_main,
)


class MissionAdmissionDeliveryTests(unittest.TestCase):
    def authority(self):
        return {
            "success": True,
            "root_mission_id": "ROOT-1",
            "latest_correction_digest": "c" * 64,
            "collision_snapshot_sha256": "d" * 64,
            "admission": {
                "status": "valid",
                "generation": "generation-1",
                "receipt_id": "MAR-" + "A" * 64,
                "content_sha256": "b" * 64,
                "authority_key_sha256": "e" * 64,
            },
        }

    def identity(self):
        return {
            "mission_id": "MISSION-1",
            "root_mission_id": "ROOT-1",
            "generation": "generation-1",
            "receipt_id": "MAR-" + "A" * 64,
            "content_sha256": "b" * 64,
        }

    @patch("modules.charlie.mission_admission_delivery.hashlib.sha256")
    @patch("modules.charlie.mission_admission_delivery.validate_mission_admission_receipt")
    @patch("modules.charlie.mission_admission_delivery.read_current_mission_admission_authority")
    def test_stages_exact_canonical_receipt_without_returning_secret(self, authority_reader, validate, digest):
        key = b"k" * 40
        digest.return_value.hexdigest.return_value = "e" * 64
        validate.return_value = self.identity()
        authority_reader.return_value = self.authority(), 200
        receipt = {
            "owner_instruction_chain": {"latest_correction_digest": "c" * 64},
            "collision_snapshot": {"snapshot_sha256": "d" * 64},
        }
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "staged"
            runtime = provision_mission_admission_runtime(
                "MISSION-1", receipt, key, target,
            )
            self.assertNotIn(key.decode(), json.dumps(runtime))
            self.assertEqual((target / "validation-receipt.key").read_bytes(), key)
            receipt_path = target / "mission-admission-receipts" / f"{runtime['receipt_id']}.json"
            self.assertTrue(receipt_path.is_file())

    def test_agent_environment_is_secret_stripped_and_path_only(self):
        runtime = {"validated": True, "state_root": "runtime-state", "mission_id": "MISSION-1"}
        environment = admitted_agent_environment(runtime, {
            "PATH": "safe", "DATABASE_URL": "secret", "SLACK_TOKEN": "secret",
        })
        self.assertEqual(environment["PATH"], "safe")
        self.assertIn(RUNTIME_STATE_ENV, environment)
        self.assertEqual(environment[RUNTIME_MISSION_ENV], "MISSION-1")
        self.assertNotIn("DATABASE_URL", environment)
        self.assertNotIn("SLACK_TOKEN", environment)

    def test_unvalidated_runtime_is_rejected(self):
        with self.assertRaisesRegex(MissionAdmissionError, "admission_delivery_not_validated"):
            admitted_agent_environment({"state_root": "runtime-state"}, {})

    def test_directory_staging_is_atomic_on_receipt_failure(self):
        import modules.charlie.mission_admission_delivery as delivery
        original = delivery._write_once
        calls = []

        def fail_second(path, content):
            calls.append(str(path))
            if len(calls) == 2:
                raise OSError("injected receipt failure")
            return original(path, content)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "runtime"
            with patch.object(delivery, "_write_once", side_effect=fail_second):
                with self.assertRaises(OSError):
                    _stage_directory_atomically(target, "MAR-" + "A" * 64, b"k" * 40, b"{}\n")
            self.assertFalse(target.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_loopback_guard_keeps_database_out_of_child_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = {"validated": True, "state_root": directory, "mission_id": "MISSION-1"}
            server, thread, launch = start_admission_guard_server(
                runtime, repo_root=Path.cwd(), connect_factory=lambda: None,
            )
            try:
                environment = admitted_agent_environment(launch, {"DATABASE_URL": "secret"})
                output = io.StringIO()
                packet = {"hook_event_name": "preToolUse", "tool_name": "Read", "tool_input": {"path": "README.md"}}
                with contextlib.redirect_stdout(output):
                    hook_main(stdin=io.StringIO(json.dumps(packet)), environ=environment)
                self.assertEqual(json.loads(output.getvalue())["permission"], "allow")
                self.assertNotIn("DATABASE_URL", environment)
            finally:
                stop_admission_guard_server(server, thread)

    def test_runner_contract_reaches_writer_without_entering_prompt(self):
        captured = {}

        def runner(command, **kwargs):
            captured.update(kwargs)
            return command

        runtime = {"validated": True, "state_root": "runtime-state", "mission_id": "MISSION-1"}
        result = _runner_with_admission(runner, runtime)(["codex"], input="prompt")
        self.assertEqual(result, ["codex"])
        self.assertEqual(captured["input"], "prompt")
        self.assertIs(captured["admission_runtime"], runtime)
        self.assertNotIn("runtime-state", captured["input"])

    def test_guard_uses_absolute_delivered_root_but_rejects_relative_root(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(
                _trusted_state_root(environ={RUNTIME_STATE_ENV: directory}),
                Path(directory).resolve(),
            )
        with self.assertRaisesRegex(MissionAdmissionError, "trusted_state_root_invalid"):
            _trusted_state_root(environ={RUNTIME_STATE_ENV: "relative-state"})

    @patch("scripts.charlie_mission_admission_guard.validate_mission_admission_receipt")
    @patch("scripts.charlie_mission_admission_guard._trusted_receipt")
    def test_guard_resolves_delivered_mission_through_canonical_authority(self, trusted, validate):
        receipt = {
            "owner_instruction_chain": {"latest_correction_digest": "c" * 64},
            "collision_snapshot": {"snapshot_sha256": "d" * 64},
        }
        trusted.return_value = (receipt, b"k" * 40, "e" * 64)
        validate.return_value = self.identity()
        authority = self.authority()
        authority["mission_id"] = "MISSION-1"
        seen = []

        def reader(mission_id):
            seen.append(mission_id)
            return authority, 200

        _validated_trusted_identity(
            authority_reader=reader,
            environ={
                RUNTIME_STATE_ENV: str(Path.cwd().resolve()),
                RUNTIME_MISSION_ENV: "MISSION-1",
            },
        )
        self.assertEqual(seen, ["MISSION-1"])
        self.assertEqual(validate.call_args.kwargs["expected_mission_id"], "MISSION-1")

    def test_supported_reads_cannot_target_staged_authority(self):
        environment = {RUNTIME_STATE_ENV: str(Path.cwd() / "private-state")}
        self.assertTrue(_references_trusted_authority(
            {"tool_input": {"path": str(Path.cwd() / "private-state" / "validation-receipt.key")}},
            environment,
        ))
        self.assertTrue(_references_trusted_authority(
            "Get-Content private-state/mission-admission-receipts/receipt.json",
            environment,
        ))
        self.assertFalse(_references_trusted_authority("git status --short", environment))
        for packet in (
            {"hook_event_name": "preToolUse", "tool_name": "Read", "tool_input": {"path": "private-state/validation-receipt.key"}},
            {"hook_event_name": "beforeShellExecution", "command": "Get-Content private-state/validation-receipt.key"},
        ):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                hook_main(stdin=io.StringIO(json.dumps(packet)), environ=environment)
            self.assertEqual(json.loads(output.getvalue())["permission"], "deny")

    @patch("scripts.charlie_mission_admission_guard._governance_read_identities", return_value=[{
        "path": "docs/09-vault-brain/00-governance/AGENTIC_OPERATING_MISSION_STANDARD.md",
        "git_blob": "1" * 40,
        "filesystem_sha256": "2" * 64,
        "byte_count": 1,
        "physical_line_count": 1,
        "complete_byte_read": True,
    }])
    @patch("scripts.charlie_mission_admission_guard._repository_identity", return_value="Crewless9086/amadeus-pig-tracking-system")
    @patch("scripts.charlie_mission_admission_guard._git_bytes", return_value=b"stage2 patch")
    @patch("scripts.charlie_mission_admission_guard._changed_files", return_value=sorted(STAGE2_ALLOWED_FILES))
    @patch("scripts.charlie_mission_admission_guard._commit")
    def test_stage2_issuer_uses_exact_child_contract(self, commit, _changed, _git, _repo, _governance):
        commit.side_effect = [STAGE2_BASE_SHA, "a" * 40]
        authority = {
            "success": True,
            "mission_id": STAGE2_MISSION_ID,
            "root_mission_id": "CMQ-20260813-05",
            "latest_correction_digest": "c" * 64,
            "collision_observed_at": "2026-08-27T10:00:00Z",
            "active_claims": [],
        }
        from modules.charlie.mission_admission import collision_snapshot_digest
        authority["collision_snapshot_sha256"] = collision_snapshot_digest(
            authority["collision_observed_at"], []
        )
        written = {}

        def writer(mission_id, admission, **_kwargs):
            written.update({"mission_id": mission_id, "admission": admission})
            return {"success": True}, 200

        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory) / ".charlie_runner"
            state.mkdir()
            (state / "validation-receipt.key").write_bytes(b"k" * 40)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = issue_bootstrap_main(
                    SimpleNamespace(mode="issue-stage2", base=STAGE2_BASE_SHA, head="a" * 40),
                    environ={"CI": "true", "CHARLIE_STAGE2_ADMITTED_HEAD": "a" * 40},
                    authority_reader=lambda _mission_id: (authority, 200),
                    admission_writer=writer,
                    repo_root=Path(directory),
                    os_name="nt",
                )
        self.assertEqual(code, 0, output.getvalue())
        self.assertEqual(written["mission_id"], STAGE2_MISSION_ID)
        self.assertEqual(written["admission"]["generation"], STAGE2_GENERATION)
