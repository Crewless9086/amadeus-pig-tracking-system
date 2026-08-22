import unittest
from pathlib import Path

from modules.beacon.public_livestock_content_policy import (
    RISK_STATUS,
    assess_public_livestock_content,
    assess_public_livestock_enquiry_capture,
    public_livestock_policy_binding,
    public_livestock_policy_binding_matches,
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

    def test_declined_card_3714_copy_is_rejected_by_common_evaluator(self):
        text = ("Looking for live pigs? Amadeus Farm handles enquiries for piglets, "
            "weaners, growers and finishers. Message us with the type, number needed, "
            "intended use and your area. SAM will check current farm records before "
            "discussing any option; no stock, price, availability, delivery or "
            "reservation is promised.")
        result = assess_public_livestock_content(text,
            objective="qualified_livestock_enquiries",
            campaign_lane="live_stock_enquiry_capture")
        self.assertFalse(result["allowed"])
        self.assertTrue(result["livestock_context"])
        for reason in (
            "public_livestock_objective_not_allowlisted",
            "implied_livestock_acquisition_meaning",
            "livestock_acquisition_detail_solicitation",
            "ambiguous_or_commercial_livestock_contact_cta",
        ):
            self.assertIn(reason, result["reasons"])
        self.assertRegex(result["evaluation_digest"], r"^[0-9a-f]{64}$")
        self.assertRegex(result["policy_authority"]["source_digest"], r"^[0-9a-f]{64}$")

    def test_plural_semantic_and_afrikaans_acquisition_variants_fail(self):
        variants = (
            "Looking for live pigs? Message us with how many piglets you need.",
            "Weaners for your growing herd. Inbox the farm with quantity and area.",
            "Op soek na lewende varke? Stuur die aantal, soort en wanneer jy dit nodig het.",
            "Varkies vir jou plaas. Kontak ons met hoeveelheid en geslag.",
        )
        for text in variants:
            result = self.assess(text, campaign_lane="live_stock_enquiry_capture")
            self.assertFalse(result["allowed"], text)
            self.assertTrue(result["livestock_context"], text)

    def test_disclaimer_cannot_revive_retired_enquiry_capture(self):
        result = assess_public_livestock_enquiry_capture(
            "Looking for live pigs? Message us with quantity. No stock, price, "
            "availability, delivery or reservation is promised.",
            campaign_lane="live_stock_enquiry_capture")
        self.assertFalse(result["allowed"])
        self.assertIn("public_livestock_enquiry_capture_exception_retired",
            result["reasons"])

    def test_missing_stale_or_mismatched_authority_binding_fails_closed(self):
        assessment = self.assess("Molly and her piglets enjoy a quiet farm morning.")
        bound = public_livestock_policy_binding(assessment, target_page_id="PAGE-1")
        self.assertTrue(public_livestock_policy_binding_matches(bound, assessment,
            target_page_id="PAGE-1"))
        self.assertFalse(public_livestock_policy_binding_matches({}, assessment,
            target_page_id="PAGE-1"))
        stale = dict(bound)
        stale["policy_authority"] = dict(bound["policy_authority"],
            source_digest="0" * 64)
        self.assertFalse(public_livestock_policy_binding_matches(stale, assessment,
            target_page_id="PAGE-1"))

    def test_active_doctrine_retires_enquiry_capture_exception(self):
        root = Path(__file__).resolve().parents[1]
        for relative in (
            "docs/09-vault-brain/08-business-rules/MARKETING_RULES.md",
            "docs/09-vault-brain/04-workflows/BEACON_CAMPAIGN_WORKFLOW.md",
            "docs/09-vault-brain/02-agents/marketing/BEACON.md",
            "docs/09-vault-brain/00-governance/BRAIN_GUARD.md",
        ):
            text = (root / relative).read_text(encoding="utf-8")
            self.assertIn("retired", text.casefold(), relative)
            self.assertNotIn("lane may state the stable", text.casefold(), relative)


if __name__ == "__main__":
    unittest.main()
