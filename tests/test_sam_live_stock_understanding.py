import unittest

from modules.sales.sam_live_stock_understanding import (
    classify_message_intent,
    is_order_commitment_confirmation,
    detect_language,
    understand_live_stock_inbound,
)


class SamLiveStockUnderstandingTests(unittest.TestCase):
    def test_bounded_english_and_afrikaans_commitment_confirmations(self):
        confirmations = (
            "I am ready to proceed.",
            "Yes, proceed.",
            "I want to go ahead.",
            "Ek is gereed om voort te gaan.",
            "Ja, gaan voort.",
            "Ek wil daarmee voortgaan.",
        )
        for text in confirmations:
            with self.subTest(text=text):
                self.assertTrue(is_order_commitment_confirmation(text))
                self.assertEqual(classify_message_intent(text), "order_commitment")

        for text in ("Yes.", "Ja.", "I want a price.", "Kan ons later voortgaan?"):
            with self.subTest(text=text):
                self.assertFalse(is_order_commitment_confirmation(text))

    def test_detects_afrikaans_and_mixed_language(self):
        self.assertEqual(detect_language("Waar is julle en hoeveel kos die varkies"), "afrikaans")
        self.assertEqual(detect_language("Waar is julle and what is the price"), "mixed_afrikaans_english")

    def test_classifies_general_and_sales_actions(self):
        self.assertEqual(classify_message_intent("Where are you guys?"), "location_question")
        self.assertEqual(classify_message_intent("Can you send photos of the bigger pigs?"), "picture_request")
        self.assertEqual(classify_message_intent("Can you deliver to Cape Town?"), "delivery_question")
        self.assertEqual(classify_message_intent("👍"), "social_acknowledgement")

    def test_voice_transcript_becomes_effective_text_without_storing_audio(self):
        packet = understand_live_stock_inbound(
            {"content": ""},
            {
                "attachments": [{"file_type": "audio", "data_url": "https://example.test/voice.ogg"}],
                "content_attributes": {"voice_transcript": "Ek soek drie varkies vir Vrydag"},
            },
        )
        self.assertEqual(packet["voice"]["status"], "transcript_supplied")
        self.assertIn("drie varkies", packet["effective_text"])
        self.assertFalse(packet["voice"]["stores_audio"])

    def test_unknown_image_requires_review_and_creates_no_facts(self):
        packet = understand_live_stock_inbound(
            {"content": ""},
            {"attachments": [{"file_type": "image", "data_url": "https://example.test/photo.jpg"}]},
        )
        self.assertTrue(packet["requires_media_review"])
        self.assertEqual(packet["images"][0]["classification"], "unknown_image")
        self.assertFalse(packet["images"][0]["facts_trusted"])


if __name__ == "__main__":
    unittest.main()
