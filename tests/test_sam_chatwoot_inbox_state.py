import unittest

from modules.sales.sam_chatwoot_inbox_state import (
    build_chatwoot_inbox_state_plan,
    build_new_inbound_reactivation_plan,
)


class SamChatwootInboxStateTests(unittest.TestCase):
    def inbound(self, **changes):
        packet = {
            "account_id": "147387",
            "inbox_id": "96568",
            "conversation_id": "2102",
            "contact_id": "987120708",
            "message_id": "766408519",
        }
        packet.update(changes)
        return packet

    def decision(self, **changes):
        packet = {
            "sales_lane": "live_stock_sales",
            "specialist_lane_selected": True,
            "missing_fields": ["quantity"],
        }
        packet.update(changes)
        return packet

    def test_confirmed_delivery_marks_exact_inbound_seen_and_awaiting(self):
        plan = build_chatwoot_inbox_state_plan(
            inbound=self.inbound(),
            decision=self.decision(),
            provider_state="provider_delivered",
            authoritative_latest_inbound_id="766408519",
        )
        self.assertTrue(plan["mark_exact_inbound_seen"])
        self.assertEqual(
            plan["update_last_seen_request"]["bound_inbound_message_id"],
            "766408519",
        )
        self.assertEqual(
            plan["replace_sam_state_labels"],
            ["awaiting_customer", "qualification_in_progress"],
        )
        self.assertTrue(plan["preserve_assignment"])
        self.assertTrue(plan["preserve_status"])
        self.assertFalse(plan["close_or_resolve"])

    def test_ambiguous_delivery_is_quarantined_and_not_marked_seen(self):
        plan = build_chatwoot_inbox_state_plan(
            inbound=self.inbound(),
            decision=self.decision(),
            provider_state="provider_outcome_ambiguous",
            authoritative_latest_inbound_id="766408519",
        )
        self.assertFalse(plan["mark_exact_inbound_seen"])
        self.assertEqual(
            plan["replace_sam_state_labels"],
            ["delivery_quarantined_do_not_retry"],
        )
        self.assertTrue(plan["automatic_retry_prohibited"])
        self.assertFalse(plan["broad_cleanup"])

    def test_accepted_unverified_does_not_mark_handled(self):
        plan = build_chatwoot_inbox_state_plan(
            inbound=self.inbound(),
            decision=self.decision(),
            provider_state="chatwoot_accepted_unverified",
            authoritative_latest_inbound_id="766408519",
        )
        self.assertFalse(plan["mark_exact_inbound_seen"])

    def test_non_livestock_lane_is_untouched(self):
        plan = build_chatwoot_inbox_state_plan(
            inbound=self.inbound(),
            decision=self.decision(
                sales_lane="meat_sales",
                specialist_lane_selected=False,
            ),
            provider_state="provider_delivered",
            authoritative_latest_inbound_id="766408519",
        )
        self.assertFalse(plan["allowed"])
        self.assertFalse(plan["mark_exact_inbound_seen"])
        self.assertEqual(plan["replace_sam_state_labels"], [])

    def test_new_inbound_reactivates_without_marking_seen(self):
        plan = build_new_inbound_reactivation_plan(
            inbound=self.inbound(message_id="766500000"),
            prior_labels=[
                "vip",
                "awaiting_customer",
                "qualification_in_progress",
            ],
        )
        self.assertTrue(plan["allowed"])
        self.assertEqual(plan["replace_sam_state_labels"], ["vip"])
        self.assertFalse(plan["mark_seen"])
        self.assertTrue(plan["preserve_assignment"])

    def test_incomplete_identity_cannot_mutate(self):
        plan = build_chatwoot_inbox_state_plan(
            inbound=self.inbound(contact_id=""),
            decision=self.decision(),
            provider_state="provider_delivered",
        )
        self.assertFalse(plan["allowed"])
        self.assertFalse(plan["mark_exact_inbound_seen"])

    def test_protected_work_is_labeled_without_promising_it(self):
        plan = build_chatwoot_inbox_state_plan(
            inbound=self.inbound(),
            decision=self.decision(owner_gate_required=True),
            provider_state="provider_read",
            authoritative_latest_inbound_id="766408519",
        )
        self.assertIn(
            "owner_decision_required",
            plan["replace_sam_state_labels"],
        )
        self.assertFalse(plan["close_or_resolve"])

    def test_newer_inbound_blocks_conversation_level_last_seen_update(self):
        plan = build_chatwoot_inbox_state_plan(
            inbound=self.inbound(),
            decision=self.decision(),
            provider_state="provider_delivered",
            authoritative_latest_inbound_id="766500000",
        )
        self.assertFalse(plan["allowed"])
        self.assertFalse(plan["mark_exact_inbound_seen"])
        self.assertIn(
            "authoritative_latest_inbound_matches",
            plan["blockers"],
        )


if __name__ == "__main__":
    unittest.main()
