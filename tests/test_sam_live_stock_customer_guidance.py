import unittest

from modules.sales.sam_live_stock_runtime import (
    _prefer_customer_size_guidance,
    build_live_stock_customer_guidance,
    extract_live_stock_facts,
)


class SamLiveStockCustomerGuidanceTests(unittest.TestCase):
    def test_vague_production_shape_prefers_guidance_over_noncommercial_classifier(self):
        self.assertTrue(_prefer_customer_size_guidance(
            customer_guidance={"applicable": True},
            contextual_sales={
                "applicable": False,
                "status": "not_commercial_livestock",
            },
            information_reply={"status": None},
            price_answer_packet={"can_answer_price": False},
            information_scope="",
            sales_lane="live_stock_sales",
        ))

    def test_source_backed_commercial_answer_still_precedes_guidance(self):
        self.assertFalse(_prefer_customer_size_guidance(
            customer_guidance={"applicable": True},
            contextual_sales={
                "applicable": True,
                "status": "commercial_evidence_verified",
            },
            information_reply={"status": None},
            price_answer_packet={"can_answer_price": False},
            information_scope="",
            sales_lane="live_stock_sales",
        ))

    def test_greeting_without_livestock_signal_never_selects_size_guidance(self):
        self.assertFalse(_prefer_customer_size_guidance(
            customer_guidance={"applicable": True},
            contextual_sales={
                "applicable": False,
                "status": "not_commercial_livestock",
            },
            information_reply={"status": None},
            price_answer_packet={"can_answer_price": False},
            information_scope="",
            sales_lane="unclear",
        ))

    def test_vague_pig_enquiry_explains_all_customer_facing_sizes(self):
        packet = build_live_stock_customer_guidance(
            {"customer_name": "Leonello", "content": "How much for one pig?"},
            {"category": "", "quantity": 1, "sex": ""},
        )
        self.assertTrue(packet["applicable"])
        self.assertEqual(len(packet["options"]), 5)
        self.assertIn("Small piglets: approximately 2 to 6 kg", packet["reply_text"])
        self.assertIn("Slaughter-size pigs: approximately 80 kg and above", packet["reply_text"])
        self.assertIn("Which size would suit you", packet["reply_text"])
        self.assertIn("male, female, or either", packet["reply_text"])
        self.assertNotIn("how many do you need", packet["reply_text"])

    def test_vague_piglet_enquiry_explains_only_relevant_piglet_sizes(self):
        packet = build_live_stock_customer_guidance(
            {"content": "Do you sell piglets?"},
            {"category": "piglet", "quantity": 0, "sex": ""},
        )
        self.assertEqual(
            [row["customer_label"] for row in packet["options"]],
            ["Small piglets", "Weaned piglets"],
        )
        self.assertIn("how many do you need", packet["reply_text"])
        self.assertNotIn("Growing pigs", packet["reply_text"])

    def test_unfamiliar_internal_term_receives_plain_language_explanation(self):
        packet = build_live_stock_customer_guidance(
            {"content": "I do not understand what a weaner is"},
            {"category": "weaner", "quantity": 2, "sex": "either"},
        )
        self.assertEqual(packet["options"], [{
            "customer_label": "Weaned piglets",
            "weight_text": "approximately 7 to 19 kg",
        }])
        self.assertNotIn("Weaner Piglets", packet["reply_text"])
        self.assertNotIn("Which size", packet["reply_text"])

    def test_known_size_with_missing_sex_asks_only_for_sex(self):
        packet = build_live_stock_customer_guidance(
            {"content": "I need two growing pigs"},
            {"category": "grower", "weight_range": "20-49 kg", "quantity": 2, "sex": ""},
        )
        self.assertEqual(packet["options"], [])
        self.assertIn("male, female, or either", packet["reply_text"])
        self.assertNotIn("Which size", packet["reply_text"])
        self.assertNotIn("how many", packet["reply_text"])

    def test_exact_conversation_2068_guidance_is_deterministic(self):
        packet = build_live_stock_customer_guidance(
            {"customer_name": "Leonello", "content": "sanitized vague pig enquiry"},
            {"category": "", "quantity": 1, "sex": ""},
        )
        self.assertEqual(
            packet["reply_text"],
            "Hi Leonello, thanks for your message. We offer pigs in different sizes:\n"
            "\n"
            "- Small piglets: approximately 2 to 6 kg\n"
            "- Weaned piglets: approximately 7 to 19 kg\n"
            "- Growing pigs: approximately 20 to 49 kg\n"
            "- Larger pigs: approximately 50 to 79 kg\n"
            "- Slaughter-size pigs: approximately 80 kg and above\n"
            "\n"
            "Which size would suit you, and would you prefer a male, female, or either?\n"
            "Once I know that, I can confirm the available options and price.",
        )

    def test_customer_weight_answers_map_to_canonical_boundaries(self):
        expected = {
            2: "piglet",
            6: "piglet",
            7: "weaner",
            19: "weaner",
            20: "grower",
            49: "grower",
            50: "finisher",
            79: "finisher",
            80: "ready_for_slaughter",
            120: "ready_for_slaughter",
        }
        for weight, category in expected.items():
            with self.subTest(weight=weight):
                facts = extract_live_stock_facts(
                    f"I would like one at about {weight} kg",
                    {"content": f"I would like one at about {weight} kg"},
                )
                self.assertEqual(facts["category"], category)

    def test_customer_facing_reply_never_exposes_unexplained_taxonomy(self):
        packet = build_live_stock_customer_guidance(
            {"content": "one pig"}, {"category": "", "quantity": 1, "sex": ""}
        )
        for internal in (
            "Young Piglets", "Weaner Piglets", "Grower Pigs",
            "Finisher Pigs", "Ready for Slaughter",
        ):
            self.assertNotIn(internal, packet["reply_text"])
        self.assertFalse(packet["availability_claimed"])
        self.assertFalse(packet["price_claimed"])


if __name__ == "__main__":
    unittest.main()
