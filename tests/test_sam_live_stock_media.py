import unittest

from modules.sales import sam_live_stock_media


class SamLiveStockMediaTests(unittest.TestCase):
    def test_media_is_disabled_without_explicit_flags(self):
        policy = sam_live_stock_media.media_policy({"OPENAI_API_KEY": "key"})
        self.assertFalse(policy["voice_enabled"])
        self.assertFalse(policy["image_enabled"])
        self.assertFalse(policy["stores_media"])
        self.assertFalse(policy["facts_from_images_trusted"])

    def test_voice_disabled_does_not_download_or_call_provider(self):
        result = sam_live_stock_media.transcribe_chatwoot_voice(
            {"url": "https://example.test/private.ogg"},
            environ={},
        )
        self.assertEqual(result["status"], "voice_transcription_disabled")
        self.assertEqual(result["transcript"], "")

    def test_image_disabled_remains_unknown_and_untrusted(self):
        result = sam_live_stock_media.classify_chatwoot_image(
            {"url": "https://example.test/private.jpg"},
            environ={},
        )
        self.assertEqual(result["classification"], "unknown_image")
        self.assertFalse(result["facts_from_images_trusted"])


if __name__ == "__main__":
    unittest.main()
