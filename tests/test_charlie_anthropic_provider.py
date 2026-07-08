import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from modules.charlie.anthropic_provider import run_anthropic_prompt


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class CharlieAnthropicProviderTests(unittest.TestCase):
    @patch.dict("os.environ", {"ANTROPIC_API_KEY": "typo-key"}, clear=True)
    def test_run_anthropic_prompt_accepts_typo_alias_and_extracts_text(self):
        captured = {}

        def fake_open(request, timeout=0):
            captured["headers"] = dict(request.header_items())
            captured["timeout"] = timeout
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({
                "id": "msg_1",
                "content": [{"type": "text", "text": "{\"summary\":\"ok\"}"}],
                "usage": {"input_tokens": 10, "output_tokens": 3},
                "stop_reason": "end_turn",
            })

        result, status_code = run_anthropic_prompt("hello", model="claude-test", opener=fake_open)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["text"], "{\"summary\":\"ok\"}")
        self.assertIn(("X-api-key", "typo-key"), captured["headers"].items())
        self.assertEqual(captured["body"]["max_tokens"], 8192)

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "real-key", "CHARLIE_ANTHROPIC_MAX_TOKENS": "12000"}, clear=True)
    def test_run_anthropic_prompt_uses_configured_max_tokens(self):
        captured = {}

        def fake_open(request, timeout=0):
            captured["body"] = json.loads(request.data.decode("utf-8"))
            return FakeResponse({
                "id": "msg_1",
                "content": [{"type": "text", "text": "{\"summary\":\"ok\"}"}],
            })

        result, status_code = run_anthropic_prompt("hello", model="claude-test", opener=fake_open)

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(captured["body"]["max_tokens"], 12000)

    @patch.dict("os.environ", {}, clear=True)
    def test_run_anthropic_prompt_blocks_without_key(self):
        result, status_code = run_anthropic_prompt("hello", model="claude-test")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "anthropic_api_key_missing")

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "real-key"}, clear=True)
    def test_run_anthropic_prompt_retries_retryable_http_error(self):
        calls = {"count": 0}

        def fake_open(_request, timeout=0):
            calls["count"] += 1
            if calls["count"] == 1:
                raise HTTPError("https://api.anthropic.com/v1/messages", 529, "overloaded", {}, None)
            return FakeResponse({
                "id": "msg_2",
                "content": [{"type": "text", "text": "{\"summary\":\"retry ok\"}"}],
            })

        result, status_code = run_anthropic_prompt(
            "hello",
            model="claude-test",
            opener=fake_open,
            sleep_fn=lambda _seconds: None,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(calls["count"], 2)
        self.assertEqual(result["text"], "{\"summary\":\"retry ok\"}")


if __name__ == "__main__":
    unittest.main()
