import unittest
from unittest.mock import patch

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

    def test_driver_event_type_is_restricted_before_database(self):
        result, status_code = meat_fulfillment.record_meat_driver_delivery_event(
            "LEAD-1",
            {"event_type": "delivery_scheduled"},
            database_url="",
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "invalid_driver_event_type")

    def test_journey_message_uses_stage_template_or_custom_message(self):
        default_message = meat_fulfillment._journey_message(
            {"stage": "driver_assigned"},
            {},
            {},
        )
        custom_message = meat_fulfillment._journey_message(
            {"stage": "driver_assigned"},
            {},
            {"message": "Custom update"},
        )

        self.assertIn("route", default_message)
        self.assertEqual(custom_message, "Custom update")

    def test_journey_message_includes_confirmed_abattoir_slot_context(self):
        status = meat_fulfillment._fulfillment_status(
            {"assembly": {"status": "ready_for_slaughter_booking", "full_carcass_committed": True, "deposit_confirmed": True}},
            [{
                "event_type": "abattoir_slot_confirmed",
                "scheduled_date": "2026-06-20",
                "scheduled_window": "08:00-10:00",
                "location_label": "Riversdale Abattoir",
                "created_at": "2026-06-17T01:00:00",
            }],
            {"whatsapp_window_state": "open"},
        )
        journey = meat_fulfillment._journey_plan(status, {}, [{
            "event_type": "abattoir_slot_confirmed",
            "scheduled_date": "2026-06-20",
            "scheduled_window": "08:00-10:00",
            "location_label": "Riversdale Abattoir",
            "created_at": "2026-06-17T01:00:00",
        }])
        message = meat_fulfillment._journey_message(journey, status, {})

        self.assertEqual(journey["stage"], "abattoir_confirmed")
        self.assertIn("2026-06-20", message)
        self.assertIn("08:00-10:00", message)
        self.assertIn("Riversdale Abattoir", message)

    def test_journey_message_includes_confirmed_butcher_slot_context(self):
        events = [
            {
                "event_type": "abattoir_slot_confirmed",
                "scheduled_date": "2026-06-20",
                "scheduled_window": "08:00-10:00",
                "location_label": "Riversdale Abattoir",
                "created_at": "2026-06-17T01:00:00",
            },
            {
                "event_type": "butcher_slot_confirmed",
                "scheduled_date": "2026-06-21",
                "scheduled_window": "09:00-12:00",
                "location_label": "Butcher",
                "created_at": "2026-06-17T02:00:00",
            },
        ]
        status = meat_fulfillment._fulfillment_status(
            {"assembly": {"status": "ready_for_slaughter_booking", "full_carcass_committed": True, "deposit_confirmed": True}},
            events,
            {"whatsapp_window_state": "open"},
        )
        journey = meat_fulfillment._journey_plan(status, {}, events)
        message = meat_fulfillment._journey_message(journey, status, {})

        self.assertEqual(journey["stage"], "butcher_confirmed")
        self.assertIn("2026-06-21", message)
        self.assertIn("09:00-12:00", message)
        self.assertIn("Final packed weight", message)

    def test_dad_booking_packet_requires_full_carcass_and_bank_confirmed(self):
        packet = meat_fulfillment._dad_booking_packet(
            "LEAD-1",
            {"contact_label": "Charl N", "interest": {"cut_set": "Set A", "timing": "next available farm run"}},
            {"status": "half_reserved_pending_pair", "full_carcass_committed": False, "deposit_confirmed": False},
            [{"reservation_id": "RES-1", "pig_id": "PIG-1", "tag_number": "402", "carcass_side": "half_a"}],
            [],
            {"next_gate": "find_second_half_buyer"},
            {},
        )

        self.assertEqual(packet["readiness"], "not_ready_for_dad_booking")
        self.assertIn("full_carcass_commitment", packet["missing_before_booking"])
        self.assertIn("money_confirmed_in_bank", packet["missing_before_booking"])
        self.assertIn("Do not book", packet["dad_message"])
        self.assertFalse(packet["calls_abattoir"])
        self.assertFalse(packet["calls_butcher"])

    def test_dad_booking_packet_formats_manual_booking_message_when_ready(self):
        packet = meat_fulfillment._dad_booking_packet(
            "LEAD-1",
            {
                "contact_label": "Charl N",
                "interest": {
                    "product": "Half Carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                    "delivery_or_collection": "delivery",
                    "timing": "next available farm run",
                },
            },
            {"status": "ready_for_slaughter_booking", "full_carcass_committed": True, "deposit_confirmed": True},
            [{
                "reservation_id": "RES-1",
                "pig_id": "PIG-1",
                "tag_number": "402",
                "carcass_side": "half_b",
                "estimated_packed_weight": "19-21kg",
            }],
            [{"event_type": "deposit_confirmed_in_bank", "payment_reference": "AMAD-MEAT-1234"}],
            {"next_gate": "confirm_abattoir_slot"},
            {},
        )

        self.assertEqual(packet["readiness"], "ready_for_dad_booking")
        self.assertEqual(packet["missing_before_booking"], [])
        self.assertIn("Pig/tag: 402", packet["dad_message"])
        self.assertIn("confirm abattoir slaughter slot", packet["dad_message"])
        self.assertEqual(packet["facts"]["deposit_state"], "confirmed in bank")

    @patch.dict("os.environ", {"MEAT_JOURNEY_NOTIFICATION_SEND_ENABLED": "0"}, clear=False)
    def test_journey_notification_send_is_disabled_before_database_or_network(self):
        result, status_code = meat_fulfillment.send_meat_journey_notification(
            "LEAD-1",
            {"message": "Approved text"},
            database_url="postgres://should-not-be-used",
        )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["sent"])
        self.assertEqual(result["status"], "meat_journey_notification_send_disabled")

    @patch("modules.sales.meat_fulfillment._send_chatwoot_message")
    def test_journey_notification_chatwoot_sender_uses_lead_conversation(self, mock_send):
        mock_send.return_value = {"message_id": "msg-1", "conversation_id": "1808"}

        result = meat_fulfillment._send_journey_notification_chatwoot(
            "LEAD-1",
            "Approved journey update",
            {"stage": "delivery_scheduled"},
            {"chatwoot_conversation_id": "1808"},
        )

        mock_send.assert_called_once_with("1808", "Approved journey update")
        self.assertEqual(result["transport"], "chatwoot")
        self.assertEqual(result["message_id"], "msg-1")

    def test_journey_notification_chatwoot_sender_requires_conversation_id(self):
        with self.assertRaises(RuntimeError) as context:
            meat_fulfillment._send_journey_notification_chatwoot(
                "LEAD-1",
                "Approved journey update",
                {"stage": "delivery_scheduled"},
                {},
            )

        self.assertEqual(str(context.exception), "lead_chatwoot_conversation_id_required")


if __name__ == "__main__":
    unittest.main()
