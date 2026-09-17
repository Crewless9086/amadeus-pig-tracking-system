import unittest

from modules.charlie.private_media import MAX_VOICE_BYTES, normalize_private_media, transcribe_voice


class CharliePrivateMediaTests(unittest.TestCase):
    def test_normalizes_metadata_without_raw_payload(self):
        media = normalize_private_media({"message": {"voice": {"file_id": "V1", "file_size": 10, "duration": 2}, "photo": [{"file_id": "P1", "width": 10, "height": 20}]}})
        self.assertEqual([item["kind"] for item in media], ["voice", "photo"])
        self.assertNotIn("bytes", str(media).lower())

    def test_voice_is_honest_when_disabled_or_oversized(self):
        disabled = transcribe_voice([{"kind": "voice", "file_size": 10}], {"llm_enabled": False})
        self.assertEqual(disabled["status"], "voice_transcription_disabled")
        oversized = transcribe_voice([{"kind": "voice", "file_size": MAX_VOICE_BYTES + 1}], {"llm_enabled": True})
        self.assertEqual(oversized["status"], "voice_too_large")


if __name__ == "__main__":
    unittest.main()
