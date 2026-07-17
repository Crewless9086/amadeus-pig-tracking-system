import unittest

from modules.charlie.private_planner import plan_owner_intent


class CharliePrivatePlannerTests(unittest.TestCase):
    def test_status_and_brief_are_deterministic(self):
        self.assertEqual(plan_owner_intent("status", {}, environ={})["type"], "read_core_status")
        self.assertEqual(plan_owner_intent("give me the morning brief", {}, environ={})["type"], "executive_brief")
        self.assertEqual(plan_owner_intent("/next", {}, environ={})["type"], "read_queue")
        self.assertEqual(plan_owner_intent("/review", {}, environ={})["type"], "read_decisions")
        self.assertEqual(plan_owner_intent("What is happening with CORE?", {}, environ={})["type"], "read_core_status")
        self.assertEqual(plan_owner_intent("What mission is running now?", {}, environ={})["type"], "read_core_status")
        self.assertEqual(plan_owner_intent("What is the active mission now?", {}, environ={})["type"], "read_core_status")

    def test_plain_words_are_not_mission_ids(self):
        result = plan_owner_intent("You do not need my permission for this", {}, environ={})
        self.assertNotEqual(result.get("args", {}).get("mission_id"), "PERMISSION")

    def test_business_department_reads_are_typed(self):
        expected = {
            "/business": "read_business_status", "/sam": "read_sam_status",
            "/beacon": "read_beacon_status", "/orders": "read_orders_status",
            "/farm": "read_farm_status",
        }
        for command, intent_type in expected.items():
            with self.subTest(command=command):
                self.assertEqual(plan_owner_intent(command, {}, environ={})["type"], intent_type)

    def test_explicit_create_and_action(self):
        create = plan_owner_intent("Create a mission to improve the loading sheet", {}, environ={})
        self.assertEqual(create["type"], "create_mission")
        self.assertTrue(create["explicit_owner_command"])
        approve = plan_owner_intent("Approve CEA5089051B2", {}, environ={})
        self.assertEqual(approve["type"], "approve_mission")

    def test_ambiguous_text_clarifies(self):
        plan = plan_owner_intent("please sort it", {}, environ={})
        self.assertEqual(plan["type"], "clarify")
        self.assertLess(plan["confidence"], .5)

    def test_explicit_remember_command_is_typed(self):
        plan = plan_owner_intent("Remember that I prefer morning briefs at 06:30", {}, environ={})
        self.assertEqual(plan["type"], "remember_preference")
        self.assertTrue(plan["explicit_owner_command"])

    def test_red_zone_request_becomes_protected_intent(self):
        plan = plan_owner_intent("Send the quote to the customer", {}, environ={})
        self.assertEqual(plan["type"], "protected_business_action")
        self.assertEqual(plan["risk_flags"], ["customer_send"])

    def test_business_preparation_and_follow_up_intents_are_typed(self):
        order = plan_owner_intent("Prepare all documents for ORD-2026-12BCCC", {}, environ={})
        self.assertEqual(order["type"], "prepare_order_pack")
        self.assertTrue(order["explicit_owner_command"])
        beacon = plan_owner_intent("Draft a Beacon post about our litter growing well", {}, environ={})
        self.assertEqual(beacon["type"], "prepare_beacon_draft")
        self.assertEqual(beacon["args"]["campaign_lane"], "live_stock_awareness")
        follow_up = plan_owner_intent("Check CORE again in 20 minutes", {}, environ={})
        self.assertEqual(follow_up["type"], "schedule_follow_up")
        self.assertEqual(follow_up["args"]["delay_minutes"], 20)

    def test_order_read_is_automatic(self):
        plan = plan_owner_intent("What is happening with ORD-2026-12BCCC?", {}, environ={})
        self.assertEqual(plan["type"], "read_order")
        self.assertFalse(plan["explicit_owner_command"])
        conversation = plan_owner_intent("What is happening with conversation 1871?", {}, environ={})
        self.assertEqual(conversation["type"], "read_sam_conversation")
        self.assertEqual(conversation["args"]["conversation_id"], "1871")


if __name__ == "__main__":
    unittest.main()
