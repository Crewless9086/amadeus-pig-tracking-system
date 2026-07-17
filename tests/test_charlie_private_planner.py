import unittest

from modules.charlie.private_planner import plan_owner_intent


class CharliePrivatePlannerTests(unittest.TestCase):
    def test_status_and_brief_are_deterministic(self):
        self.assertEqual(plan_owner_intent("status", {}, environ={})["type"], "read_core_status")
        self.assertEqual(plan_owner_intent("give me the morning brief", {}, environ={})["type"], "executive_brief")

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


if __name__ == "__main__":
    unittest.main()
