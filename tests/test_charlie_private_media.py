import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from modules.charlie.private_media import MAX_VOICE_BYTES, normalize_private_media, transcribe_voice


class CharliePrivateMediaTests(unittest.TestCase):
    def test_normalizes_metadata_without_raw_payload(self):
        media = normalize_private_media({"message": {"voice": {"file_id": "V1", "file_size": 10, "duration": 2}, "photo": [{"file_id": "P1", "width": 10, "height": 20}]}})
        self.assertEqual([item["kind"] for item in media], ["voice", "photo"])
        self.assertNotIn("bytes", str(media).lower())

    def test_unpriced_voice_never_calls_openai_and_gives_af_text_guidance(self):
        client = Mock()
        client.get.side_effect = [SimpleNamespace(raise_for_status=lambda: None,
            json=lambda: {"result": {"file_path": "voice/synthetic.ogg"}}),
            SimpleNamespace(raise_for_status=lambda: None, content=b"synthetic")]
        result = transcribe_voice([{"kind": "voice", "file_id": "synthetic", "file_size": 9}],
            {"transcription_enabled": True, "transcription_model": "whisper-1", "token": "synthetic"},
            environ={"OPENAI_API_KEY": "synthetic", "OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE": "af"},
            http_client=client)
        self.assertEqual(result["status"], "farm_model_budget_endpoint_unpriced")
        self.assertEqual(result["text"], "")
        self.assertTrue(result["text_only"] and result["model_budget_denied"])
        self.assertIn("Tik asseblief", result["answer"])
        self.assertNotIn("Stuur", result["answer"])
        self.assertEqual(client.get.call_count, 2)
        client.post.assert_not_called()

    def test_voice_is_honest_when_disabled_or_oversized(self):
        disabled = transcribe_voice([{"kind": "voice", "file_size": 10}], {"llm_enabled": False})
        self.assertEqual(disabled["status"], "voice_transcription_disabled")
        oversized = transcribe_voice([{"kind": "voice", "file_size": MAX_VOICE_BYTES + 1}], {"llm_enabled": True})
        self.assertEqual(oversized["status"], "voice_too_large")


if __name__ == "__main__":
    unittest.main()
