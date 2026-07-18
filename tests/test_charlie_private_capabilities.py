import unittest

from modules.charlie.private_capabilities import (
    capability_catalog,
    follow_up_capabilities,
    select_capabilities,
)


class CharliePrivateCapabilityTests(unittest.TestCase):
    def test_catalog_is_typed_and_read_authority_is_explicit(self):
        rows = capability_catalog()
        self.assertGreaterEqual(len(rows), 15)
        self.assertTrue(all(row["source_of_truth"] for row in rows))
        self.assertTrue(all(row["authority_tier"] == "auto" for row in rows))

    def test_cross_domain_question_selects_relevant_authoritative_reads(self):
        selected = select_capabilities("How are livestock sales, orders and the farm doing?", "investigate")
        self.assertIn("read_sam_status", selected)
        self.assertIn("read_orders_status", selected)
        self.assertIn("read_farm_status", selected)

    def test_keyword_matching_does_not_find_pig_inside_happening(self):
        selected = select_capabilities("What is happening with CORE?", "read_core_status")
        self.assertEqual(selected, ["read_core_status", "read_blocked"])

    def test_explicit_evidence_gap_causes_one_bounded_follow_up(self):
        evidence = [{"intent_type": "read_order", "success": True, "result": {"suggested_followups": ["read_farm_status", "read_farm_status"]}}]
        self.assertEqual(follow_up_capabilities(evidence, ["read_order"]), ["read_farm_status"])

    def test_failed_source_does_not_trigger_speculative_follow_up(self):
        evidence = [{"intent_type": "read_order", "success": False, "result": {"suggested_followups": ["read_farm_status"]}}]
        self.assertEqual(follow_up_capabilities(evidence, ["read_order"]), [])


if __name__ == "__main__":
    unittest.main()
