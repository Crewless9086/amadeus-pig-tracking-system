import unittest

from modules.sales.sam_meat_stress import (
    STRESS_SCENARIOS,
    format_stress_summary,
    run_sam_meat_stress_pack,
)


class SamMeatStressTests(unittest.TestCase):
    def test_stress_pack_has_required_launch_coverage(self):
        self.assertGreaterEqual(len(STRESS_SCENARIOS), 30)
        categories = {scenario["category"] for scenario in STRESS_SCENARIOS}
        required = {
            "vague_interest",
            "budget",
            "price_objection",
            "delivery",
            "location_pin",
            "payment",
            "wrong_product",
            "cut_set_question",
            "whatsapp_window",
            "frustration",
            "ignore",
            "channel",
        }

        self.assertTrue(required.issubset(categories))
        for scenario in STRESS_SCENARIOS:
            with self.subTest(scenario=scenario["id"]):
                self.assertIn("id", scenario)
                self.assertIn("category", scenario)
                self.assertTrue("expected_facts" in scenario or scenario.get("expect_processed") is False)
                if scenario.get("expect_processed", True):
                    self.assertIn("expected_labels", scenario)
                    self.assertIn("expected_attrs", scenario)

    def test_stress_pack_passes_launch_blocking_assertions(self):
        summary = run_sam_meat_stress_pack()

        self.assertTrue(summary["success"], summary)
        self.assertEqual(summary["scenario_count"], len(STRESS_SCENARIOS))
        self.assertEqual(summary["failed_count"], 0)
        self.assertGreaterEqual(summary["known_gap_count"], 1)
        recommendations = {item["gap"] for item in summary["recommendations"]}
        self.assertTrue(any("Afrikaans" in item for item in recommendations))
        self.assertFalse(any("Budget amount" in item for item in recommendations))

    def test_stress_summary_is_operator_readable(self):
        summary = run_sam_meat_stress_pack()
        text = format_stress_summary(summary)

        self.assertIn("Sam Meat Sales Stress-Test Run", text)
        self.assertIn("Scenarios: 40", text)
        self.assertIn("No launch-blocking stress assertions failed", text)
        self.assertIn("Plain-text Google Maps", text)


if __name__ == "__main__":
    unittest.main()
