import hashlib
import json
import subprocess
import unittest
from pathlib import Path


WORKFLOW_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "04-n8n"
    / "workflows"
    / "2.0B - Oom Sakkie Backend Read-Only Relay"
    / "workflow.json"
)
PROVEN_LIVE_BASELINE_BUILD_SHA256 = (
    "663d72e6956928235c0e3f7d5418adad5ed3574aab331187e33cbb7f02d0a87a"
)
SECURITY_REVIEWED_BUILD_SHA256 = (
    "732d38a80dc777f634bc189a949b5f318a37bf308f9c57cfeb55e36e3c8372a1"
)


def build_node_source():
    workflow = json.loads(WORKFLOW_PATH.read_text(encoding="utf-8"))
    node = next(
        item
        for item in workflow["nodes"]
        if item["name"] == "Code - Build Backend Gateway Request"
    )
    return node["parameters"]["jsCode"]


def run_in_n8n_style_sandbox(base_url, token="t" * 32, item=None):
    source = build_node_source()
    harness = r"""
const vm = require("vm");
const source = JSON.parse(process.argv[1]);
const input = JSON.parse(process.argv[2]);
const vars = JSON.parse(process.argv[3]);
const wrapped = `(function () { "use strict"; ${source} })()`;
const sandbox = {
  $json: input,
  $vars: vars,
  Set,
  String,
};
const result = vm.runInNewContext(wrapped, sandbox, {
  filename: "Code - Build Backend Gateway Request",
});
process.stdout.write(JSON.stringify(result));
"""
    completed = subprocess.run(
        [
            "node",
            "-e",
            harness,
            json.dumps(source),
            json.dumps(item or {"success": True, "send_allowed": False}),
            json.dumps(
                {
                    "OOM_SAKKIE_GATEWAY_BASE_URL": base_url,
                    "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": token,
                }
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(completed.stdout)[0]["json"]


class OomSakkieN8nSandboxUrlParserTests(unittest.TestCase):
    def test_committed_build_node_preserves_live_baseline_without_url_global(self):
        source = build_node_source()
        source_hash = hashlib.sha256(source.encode()).hexdigest()
        self.assertEqual(source_hash, SECURITY_REVIEWED_BUILD_SHA256)
        self.assertNotEqual(source_hash, PROVEN_LIVE_BASELINE_BUILD_SHA256)
        self.assertNotIn("new URL(", source)

    def test_approved_https_origin_runs_without_url_global(self):
        result = run_in_n8n_style_sandbox(
            "https://amadeus-pig-tracking-system.onrender.com"
        )
        self.assertEqual(
            result["gateway_url"],
            "https://amadeus-pig-tracking-system.onrender.com"
            "/api/oom-sakkie/channels/telegram/message",
        )
        self.assertNotIn("gateway_token", result)

    def test_local_http_policy_accepts_only_loopback_hosts(self):
        for origin in (
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://[::1]:5000",
        ):
            with self.subTest(origin=origin):
                self.assertIn(
                    "/api/oom-sakkie/channels/telegram/message",
                    run_in_n8n_style_sandbox(origin)["gateway_url"],
                )

        for origin in (
            "http://example.com",
            "http://localhost.example.com",
            "http://127.0.0.2",
            "ftp://localhost",
            "https://example.com/path",
            "https://example.com",
            "https://amadeus-pig-tracking-system.onrender.com.evil.test",
            "https://sub.amadeus-pig-tracking-system.onrender.com",
            "https://amadeus-pig-tracking-system.onrender.com:443",
            "HTTPS://AMADEUS-PIG-TRACKING-SYSTEM.ONRENDER.COM",
            "https://amadeus-pig-tracking-system.onrender.com.",
            "https://example.com?token=SECRET",
            "https://example.com#fragment",
            "https://user:secret@example.com",
            "https://example.com:0",
            "https://example.com:65536",
            "https://[::::]",
            "prefix https://example.com suffix",
        ):
            with self.subTest(origin=origin):
                self.assert_safe_failure(origin)

    def test_malformed_and_unsafe_origins_fail_closed(self):
        for origin in (
            "",
            "amadeus-pig-tracking-system.onrender.com",
            "javascript:alert(1)",
            "https:/example.com",
            "http://",
            "https://example.com:bad-port",
            "https://?bad",
        ):
            with self.subTest(origin=origin):
                self.assert_safe_failure(origin)

    def test_missing_or_short_credentials_fail_without_send_or_write(self):
        for token in ("", "short"):
            with self.subTest(token=token):
                result = run_in_n8n_style_sandbox(
                    "https://amadeus-pig-tracking-system.onrender.com",
                    token=token,
                )
                self.assertEqual(result["status"], "relay_env_not_ready")
                self.assertFalse(result["send_allowed"])
                self.assertFalse(result["sends_telegram"])
                self.assertFalse(result["writes"])
                self.assertFalse(result["can_trigger_outbound_llm"])
                self.assertFalse(result["records_audit_trace"])
                self.assertNotIn("gateway_url", result)
                self.assertNotIn("gateway_token", result)

    def test_failure_diagnostics_never_repeat_configured_secrets(self):
        for secret_origin in (
            "https://user:secret@example.com",
            "https://example.com?token=SECRET",
            "prefix https://example.com/SECRET suffix",
        ):
            with self.subTest(secret_origin=secret_origin):
                result = run_in_n8n_style_sandbox(secret_origin)
                serialized = json.dumps(result)
                self.assertNotIn("secret", serialized.lower())
                self.assertNotIn("preview", result["base_url_diagnostic"])

    def assert_safe_failure(self, origin):
        result = run_in_n8n_style_sandbox(origin)
        self.assertEqual(result["status"], "relay_env_not_ready")
        self.assertFalse(result["send_allowed"])
        self.assertFalse(result["sends_telegram"])
        self.assertFalse(result["writes"])
        self.assertFalse(result["can_trigger_outbound_llm"])
        self.assertFalse(result["records_audit_trace"])
        self.assertNotIn("gateway_url", result)
        self.assertNotIn("gateway_token", result)


if __name__ == "__main__":
    unittest.main()
