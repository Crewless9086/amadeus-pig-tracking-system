import json
import unittest
from unittest.mock import patch

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

    @patch.dict("os.environ", {}, clear=True)
    def test_run_anthropic_prompt_blocks_without_key(self):
        result, status_code = run_anthropic_prompt("hello", model="claude-test")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "anthropic_api_key_missing")


if __name__ == "__main__":
    unittest.main()
