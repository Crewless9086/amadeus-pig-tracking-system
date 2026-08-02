import unittest

from modules.beacon.public_livestock_content_policy import (
    RISK_STATUS,
    assess_public_livestock_content,
)


class BeaconPublicLivestockContentPolicyTests(unittest.TestCase):
    def assess(self, text, **kwargs):
        return assess_public_livestock_content(
            text,
            objective=kwargs.pop("objective", "farm_awareness"),
            campaign_lane=kwargs.pop("campaign_lane", "live_stock_awareness"),
            **kwargs,
        )

    def test_safe_awareness_and_education_ctas_pass(self):
        for text in (
            "Follow the farm journey for more behind-the-scenes piglet care.",
            "Ask an educational question about responsible animal care.",
            "Watter deel van verantwoordelike diereversorging wil jy volgende sien?",
        ):
            self.assertTrue(self.assess(text)["allowed"], text)

    def test_english_direct_and_indirect_commerce_is_withheld(self):
        blocked = (
            "Piglets for sale. Message us for availability.",
            "Planning livestock for your farm? Tell us what you need.",
            "Message us with your livestock requirements.",
            "These little ones are ready for a new home.",
            "Let us know the type, quantity, sex, age, weight and timing you require.",
            "Send your details and we will check price, availability or collection.",
        )
        for text in blocked:
            result = self.assess(text)
            self.assertFalse(result["allowed"], text)
            self.assertEqual(result["status"], RISK_STATUS)

    def test_afrikaans_indirect_commerce_is_withheld(self):
        result = self.assess(
            "Beplan jy varkies? Stuur vir ons die hoeveelheid, geslag, gewig en wanneer jy dit nodig het."
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["status"], RISK_STATUS)

    def test_structured_commercial_objective_blocks_neutral_copy(self):
        result = self.assess(
            "A quiet morning with the piglets.",
            objective="qualified_buyer_enquiry",
        )
        self.assertFalse(result["allowed"])
        self.assertIn("public_livestock_objective_not_allowlisted", result["reasons"])

    def test_qualified_livestock_enquiries_are_not_a_public_objective(self):
        result = self.assess(
            "Follow the piglets as they grow.",
            objective="qualified_livestock_enquiries",
        )
        self.assertFalse(result["allowed"])
        self.assertEqual(result["status"], RISK_STATUS)

    def test_combined_media_and_copy_meaning_is_assessed(self):
        result = self.assess(
            "Follow the farm journey.",
            media={"title": "Piglets ready for a new home", "campaign_lane": "live_stock_sales"},
        )
        self.assertFalse(result["allowed"])
        self.assertIn("combined_media_copy_commercial_meaning", result["reasons"])

    def test_ambiguous_contact_cta_fails_closed_and_sam_is_unchanged(self):
        result = self.assess("Piglet update: message the farm to discuss your needs.")
        self.assertFalse(result["allowed"])
        self.assertEqual(result["status"], RISK_STATUS)
        self.assertTrue(result["private_sam_livestock_sales_unchanged"])


if __name__ == "__main__":
    unittest.main()
