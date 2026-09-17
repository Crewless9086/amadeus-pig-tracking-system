import json
import tempfile
import unittest
from pathlib import Path

from modules.charlie.secret_redaction import (
    assert_serialized_payload_safe,
    redact_file_in_place,
    redact_payload,
    redact_secrets,
    redact_tree_in_place,
    restricted_agent_environment,
)


class CharlieSecretRedactionTests(unittest.TestCase):
    def setUp(self):
        self.secret = "correct-horse-battery-staple"
        self.environ = {
            "PATH": "safe-path",
            "DATABASE_URL": f"postgresql://owner:{self.secret}@db.example.test/main",
            "CORE_RELAY_BOT_TOKEN": "123456:telegram-secret-value",
            "SERVICE_API_KEY": "service-key-value",
        }

    def test_agent_environment_excludes_credentials_but_keeps_safe_runtime(self):
        self.assertEqual(restricted_agent_environment(self.environ), {"PATH": "safe-path"})

    def test_redacts_full_values_assignments_and_credential_urls(self):
        text = " ".join([
            self.environ["DATABASE_URL"],
            f"password={self.secret}",
            f"postgresql://other:{self.secret}@db.example.test/main",
        ])
        result = redact_secrets(text, self.environ)
        self.assertNotIn(self.secret, result)
        self.assertNotIn("owner:", result)
        self.assertGreaterEqual(result.count("[REDACTED]"), 2)

    def test_nested_payload_is_safe_before_serialization(self):
        payload = {"stderr_tail": self.environ["DATABASE_URL"], "nested": [self.environ["SERVICE_API_KEY"]]}
        result = redact_payload(payload, self.environ)
        self.assertTrue(assert_serialized_payload_safe(result, self.environ))
        self.assertNotIn(self.secret, json.dumps(result))

    def test_persisted_execution_stream_is_redacted_in_place(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "builder.stderr.txt"
            path.write_text(f"diagnostic {self.environ['DATABASE_URL']}", encoding="utf-8")
            self.assertTrue(redact_file_in_place(path, self.environ))
            self.assertNotIn(self.secret, path.read_text(encoding="utf-8"))

    def test_restart_scrub_redacts_interrupted_execution_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "nested").mkdir()
            affected = root / "nested" / "builder.stderr.txt"
            safe = root / "safe.log"
            ignored = root / "binary.bin"
            affected.write_text(self.environ["DATABASE_URL"], encoding="utf-8")
            safe.write_text("safe", encoding="utf-8")
            ignored.write_bytes(self.environ["DATABASE_URL"].encode("utf-8"))
            result = redact_tree_in_place(root, self.environ)
            self.assertEqual(result["files_checked"], 2)
            self.assertEqual(result["files_redacted"], 1)
            self.assertEqual(result["errors"], [])
            self.assertNotIn(self.secret, affected.read_text(encoding="utf-8"))
            self.assertIn(self.secret, ignored.read_bytes().decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
