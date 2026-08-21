import hashlib
import hmac
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from scripts import charlie_runner_task_launcher as launcher
from modules.charlie.runtime_activation import read_startup_evidence


class CharlieRunnerTaskLauncherTests(unittest.TestCase):
    def test_phase_record_is_bounded_signed_and_secret_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = b"k" * 32
            key_path = root / "key"
            key_path.write_bytes(key)
            evidence_root = root / "evidence"
            with patch.object(launcher, "KEY_PATH", key_path), patch.object(
                launcher, "EVIDENCE_ROOT", evidence_root
            ), patch.dict(os.environ, {"DATABASE_URL": "postgresql://owner:secret@db/main"}):
                self.assertTrue(launcher._append_phase(
                    "launcher_failed", activation_id="a" * 32, exit_code=1,
                    activation_packet_hmac_sha256="1" * 64,
                    stderr_tail="DATABASE_URL=postgresql://owner:secret@db/main " + "x" * 9000,
                ))
            raw = next((evidence_root / ("a" * 32)).glob("*.json")).read_bytes()
            self.assertLessEqual(len(raw), launcher.MAX_RECORD_BYTES)
            self.assertNotIn(b"secret", raw)
            self.assertNotIn(b"owner:", raw)
            record = json.loads(raw)
            signature = record.pop("record_hmac_sha256")
            expected = hmac.new(key, launcher._canonical(record), hashlib.sha256).hexdigest()
            self.assertEqual(signature, expected)

    def test_main_records_pre_import_phases_and_sanitized_failure(self):
        phases = []
        with patch.object(
            launcher, "_append_phase",
            side_effect=lambda phase, **kw: phases.append((phase, kw)) or True,
        ), patch.object(launcher, "_activation_binding", return_value=("b" * 32, "1" * 64)), patch.dict(
            "sys.modules", {"dotenv": None}
        ):
            result = launcher.main()
        self.assertEqual(result, 1)
        self.assertEqual([item[0] for item in phases[:2]], [
            "launcher_entered", "activation_packet_authenticated",
        ])
        self.assertEqual(phases[-1][0], "launcher_failed")
        self.assertEqual(phases[-1][1]["error_type"], "ModuleNotFoundError")

    def test_invalid_activation_never_loads_environment_or_watchdog(self):
        phases = []
        with patch.object(launcher, "_activation_binding", return_value=("Unknown", "")), \
                patch.object(launcher, "_append_phase", side_effect=lambda phase, **kw: phases.append(phase) or True), \
                patch("runpy.run_path") as run_path:
            self.assertEqual(launcher.main(), 1)
        run_path.assert_not_called()
        self.assertEqual(phases, ["launcher_entered", "activation_packet_unavailable_or_invalid"])

    def test_live_stderr_is_sanitized_before_forwarding(self):
        prior = io.StringIO()
        with patch.dict(os.environ, {"API_TOKEN": "top-secret-token"}):
            stream = launcher._BoundedStderr(prior)
            stream.write("Bearer abc.")
            stream.write("def top-secret-")
            stream.write("token")
            stream.flush()
        self.assertEqual(prior.getvalue(), "")
        self.assertIn("top-secret-token", stream.tail)

    def test_action_identity_does_not_record_environment_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key_path = root / "key"
            key_path.write_bytes(b"z" * 32)
            evidence_root = root / "evidence"
            with patch.object(launcher, "KEY_PATH", key_path), patch.object(
                launcher, "EVIDENCE_ROOT", evidence_root
            ), patch.dict(os.environ, {"API_TOKEN": "top-secret-token"}):
                launcher._append_phase("launcher_entered")
            record = json.loads(next((evidence_root / "unbound").glob("*.json")).read_text(encoding="utf-8"))
            self.assertIn("launcher_sha256", record)
            self.assertIn("action_arguments_sha256", record)
            self.assertNotIn("top-secret-token", json.dumps(record))

    def test_activation_identity_requires_signed_packet_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = b"p" * 32
            key_path = root / "key"
            key_path.write_bytes(key)
            activation_id = "e" * 32
            packet = {
                "version": launcher.ACTIVATION_VERSION,
                "status": "provider_pending",
                "activation_id": activation_id,
                "expected_instance_guid": "{11111111-1111-1111-1111-111111111111}",
                "authority": {
                    "version": launcher.AUTHORITY_VERSION,
                    "activation_id": activation_id,
                    "execution_mode": "observe_only",
                    "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
                },
            }
            packet["authority"]["signature_hmac_sha256"] = hmac.new(
                key, launcher._canonical(packet["authority"]), hashlib.sha256
            ).hexdigest()
            packet["packet_hmac_sha256"] = hmac.new(
                key, launcher._canonical(packet), hashlib.sha256
            ).hexdigest()
            packet_path = root / "activation-packet.json"
            packet_path.write_text(json.dumps(packet), encoding="utf-8")
            with patch.object(launcher, "KEY_PATH", key_path), patch.object(
                launcher, "PACKET_PATH", packet_path
            ):
                self.assertEqual(launcher._activation_id(), activation_id)
                packet["authority"]["activation_id"] = "f" * 32
                packet_path.write_text(json.dumps(packet), encoding="utf-8")
                self.assertEqual(launcher._activation_id(), "Unknown")

    def test_reader_ignores_tampered_and_other_activation_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = b"q" * 32
            (root / "activation-authority.key").write_bytes(key)
            packet = {"activation_id": "c" * 32, "status": "provider_pending"}
            packet["packet_hmac_sha256"] = hmac.new(
                key, launcher._canonical(packet), hashlib.sha256).hexdigest()
            (root / "activation-packet.json").write_text(json.dumps(packet), encoding="utf-8")
            evidence_dir = root / "activation-ledger" / "startup-evidence" / ("c" * 32)
            evidence_dir.mkdir(parents=True)
            valid = {
                "version": launcher.VERSION,
                "activation_id": "c" * 32,
                "activation_packet_hmac_sha256": packet["packet_hmac_sha256"],
                "phase": "environment_loaded",
            }
            valid["record_hmac_sha256"] = hmac.new(
                key, launcher._canonical(valid), hashlib.sha256
            ).hexdigest()
            tampered = {**valid, "phase": "watchdog_entry_exited"}
            other = {**valid, "activation_id": "d" * 32}
            wrong_packet = {**valid, "activation_packet_hmac_sha256": "2" * 64}
            wrong_packet["record_hmac_sha256"] = hmac.new(
                key, launcher._canonical({k: v for k, v in wrong_packet.items()
                                          if k != "record_hmac_sha256"}), hashlib.sha256
            ).hexdigest()
            for index, item in enumerate((valid, tampered, other, wrong_packet)):
                (evidence_dir / f"{index}.json").write_text(json.dumps(item), encoding="utf-8")
            result = read_startup_evidence(root, "c" * 32)
        self.assertEqual(result["status"], "startup_evidence_authenticated")
        self.assertEqual([row["phase"] for row in result["records"]], ["environment_loaded"])
        self.assertEqual(result["invalid_or_unbound_records_ignored"], 3)
        self.assertRegex(result["evidence_sha256"], r"^[0-9a-f]{64}$")

    def test_reader_accepts_original_hmac_from_authenticated_transitioned_packet(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); key = b"r" * 32; activation_id = "a" * 32
            (root / "activation-authority.key").write_bytes(key)
            pending_hmac = "3" * 64
            packet = {"activation_id": activation_id,
                "consumed_packet_hmac_sha256": pending_hmac, "status": "provider_started"}
            packet["packet_hmac_sha256"] = hmac.new(
                key, launcher._canonical(packet), hashlib.sha256).hexdigest()
            (root / "activation-packet.json").write_text(json.dumps(packet), encoding="utf-8")
            evidence = root / "activation-ledger" / "startup-evidence" / activation_id
            evidence.mkdir(parents=True)
            record = {"version": launcher.VERSION, "activation_id": activation_id,
                "activation_packet_hmac_sha256": pending_hmac, "phase": "environment_loaded"}
            record["record_hmac_sha256"] = hmac.new(
                key, launcher._canonical(record), hashlib.sha256).hexdigest()
            (evidence / "1.json").write_text(json.dumps(record), encoding="utf-8")
            result = read_startup_evidence(root, activation_id)
        self.assertEqual(result["status"], "startup_evidence_authenticated")


if __name__ == "__main__":
    unittest.main()
