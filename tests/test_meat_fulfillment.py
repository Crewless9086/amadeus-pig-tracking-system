import unittest

from modules.sales import meat_fulfillment


class MeatFulfillmentTests(unittest.TestCase):
    def test_half_reserved_stays_waiting_for_second_half(self):
        status = meat_fulfillment._fulfillment_status(
            {"assembly": {"status": "half_reserved_pending_pair", "full_carcass_committed": False}},
            [],
            {"whatsapp_window_state": "open"},
        )
        journey = meat_fulfillment._journey_plan(status, {})

        self.assertTrue(status["half_waiting_for_pair"])
        self.assertEqual(status["next_gate"], "find_second_half_buyer")
        self.assertEqual(status["status"], "waiting_for_second_half")
        self.assertEqual(journey["stage"], "half_reserved_waiting_pair")
        self.assertFalse(journey["requires_template"])

    def test_closed_whatsapp_window_requires_template(self):
        status = meat_fulfillment._fulfillment_status(
            {"assembly": {"status": "half_reserved_pending_pair"}},
            [{"event_type": "customer_template_required", "created_at": "2026-06-16T01:00:00"}],
            {"whatsapp_window_state": "closed"},
        )
        journey = meat_fulfillment._journey_plan(status, {})

        self.assertTrue(status["requires_template"])
        self.assertEqual(journey["customer_message_state"], "template_required")

    def test_capacity_and_delivery_gates_progress_in_order(self):
        ops = {"assembly": {"status": "ready_for_slaughter_booking", "full_carcass_committed": True, "deposit_confirmed": True}}
        self.assertEqual(meat_fulfillment._fulfillment_status(ops, [], {})["next_gate"], "confirm_abattoir_slot")
        self.assertEqual(meat_fulfillment._fulfillment_status(ops, [
            {"event_type": "abattoir_slot_confirmed", "created_at": "2026-06-16T01:00:00"},
        ], {})["next_gate"], "confirm_butcher_slot")
        self.assertEqual(meat_fulfillment._fulfillment_status(ops, [
            {"event_type": "abattoir_slot_confirmed", "created_at": "2026-06-16T01:00:00"},
            {"event_type": "butcher_slot_confirmed", "created_at": "2026-06-16T02:00:00"},
        ], {})["next_gate"], "capture_delivery_address")
        self.assertEqual(meat_fulfillment._fulfillment_status(ops, [
            {"event_type": "abattoir_slot_confirmed", "created_at": "2026-06-16T01:00:00"},
            {"event_type": "butcher_slot_confirmed", "created_at": "2026-06-16T02:00:00"},
            {"event_type": "delivery_address_captured", "created_at": "2026-06-16T03:00:00"},
        ], {})["next_gate"], "schedule_delivery")

    def test_event_validation_blocks_missing_operational_facts(self):
        self.assertEqual(
            meat_fulfillment._validate_event_payload("abattoir_slot_confirmed", {}),
            "scheduled_date_required",
        )
        self.assertEqual(
            meat_fulfillment._validate_event_payload("delivery_address_captured", {"address_line_1": "1 Farm Road"}),
            "delivery_address_required",
        )
        self.assertEqual(
            meat_fulfillment._validate_event_payload("delivery_driver_assigned", {}),
            "assigned_driver_required",
        )
        self.assertEqual(
            meat_fulfillment._validate_event_payload("exception_review_required", {}),
            "reason_required",
        )

    def test_newer_exception_stays_open_until_newer_resolution(self):
        ops = {"assembly": {"status": "ready_for_slaughter_booking", "full_carcass_committed": True, "deposit_confirmed": True}}
        open_status = meat_fulfillment._fulfillment_status(ops, [
            {"event_type": "exception_review_resolved", "created_at": "2026-06-16T01:00:00"},
            {"event_type": "exception_review_required", "created_at": "2026-06-16T02:00:00"},
        ], {})
        resolved_status = meat_fulfillment._fulfillment_status(ops, [
            {"event_type": "exception_review_required", "created_at": "2026-06-16T02:00:00"},
            {"event_type": "exception_review_resolved", "created_at": "2026-06-16T03:00:00"},
        ], {})

        self.assertTrue(open_status["exception_open"])
        self.assertEqual(open_status["next_gate"], "resolve_exception_review")
        self.assertFalse(resolved_status["exception_open"])


if __name__ == "__main__":
    unittest.main()
