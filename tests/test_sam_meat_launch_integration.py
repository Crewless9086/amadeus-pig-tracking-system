import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from modules.sales import conversation_learning, sam_command_state, sam_meat_runtime
from modules.sales.sam_meat_launch_readiness import build_sam_meat_launch_packet


def truth_readers():
    price = {"product_type": "half_carcass", "cut_set": "Set A", "price_unit": "per_kg", "price_amount": 130,
             "effective_from": "2026-07-01T00:00:00+00:00", "effective_to": "2026-08-31T00:00:00+00:00", "status": "active"}
    return {
        "catalogue": lambda **_: {"usable": True, "status": "verified_catalogue", "data": {"products": ["half carcass"], "units": ["half_carcass"], "packs": ["Set A"]}},
        "pricing": lambda **_: {"usable": True, "status": "verified_pricing", "data": {"entries": [price]}},
        "availability": lambda **_: {"usable": False, "blockers": ["capacity_unavailable"]},
        "fulfilment": lambda **_: {"usable": True, "status": "verified_fulfilment", "data": {"mode": "delivery", "areas": ["Riversdale"]}},
        "butcher": lambda **_: {"usable": False, "blockers": ["butcher_loop_unproven"]},
    }


def inbound_payload():
    return {
        "id": "msg-102", "event": "message_created", "message_type": "incoming",
        "content": "Actually make that 2 half carcasses, collection in Riversdale next week. EFT.",
        "conversation": {"id": 1808, "inbox": {"channel_type": "Channel::Whatsapp"}, "messages": [
            {"id": "msg-101", "message_type": "incoming", "content": "I want 1 half carcass Set A."},
        ]},
        "sender": {"id": 99, "name": "Test Buyer"}, "account": {"id": 1},
    }


class SamMeatLaunchIntegrationTests(unittest.TestCase):
    @patch.object(sam_meat_runtime, "record_learning_event_from_sam_result", return_value=({"success": True, "status": "ok", "learning_event_id": "BASE"}, 200))
    @patch.object(sam_meat_runtime, "record_sam_meat_intake_lead")
    @patch.object(sam_meat_runtime, "get_sales_lead_preorder_contract")
    @patch.object(sam_meat_runtime, "_conversation_lead_context", return_value={})
    @patch.object(sam_meat_runtime, "_conversation_live_stock_context", return_value={"active": False})
    def test_real_inbound_runtime_invokes_packet_with_retained_messages(
        self, _live_stock, _lead_context, contract, record, _learning
    ):
        contract.return_value = ({"success": True, "contract": {"contract_status": "needs_owner_confirmation"}}, 200)
        record.return_value = ({"success": True, "status": "ok", "lead_id": "LEAD-1", "contract": {}}, 201)
        recorder = Mock(return_value=({"success": True, "status": "sam_meat_launch_evidence_persisted", "persisted": True}, 200))

        result, status = sam_meat_runtime.handle_sam_meat_chatwoot_inbound(
            inbound_payload(), environ={"SAM_MEAT_BACKEND_AUTOREPLY_ENABLED": "0"},
            launch_evidence_recorder=recorder, launch_truth_readers=truth_readers(),
        )

        self.assertEqual(status, 200)
        packet = result["sam_meat_launch_packet"]
        self.assertEqual(packet["facts"]["quantity"], 2)
        self.assertEqual(packet["facts"]["quantity_unit"], "half_carcass")
        self.assertEqual(packet["facts"]["product_type"], "half_carcass")
        self.assertEqual(packet["facts"]["delivery_mode"], "collection")
        self.assertTrue(packet["review_event"]["persisted"])
        self.assertEqual(packet["availability"]["status"], "Unavailable")
        self.assertFalse(result["sent"])
        self.assertFalse(any(packet["authority"].values()))
        recorder.assert_called_once()

    def test_existing_append_only_rail_deduplicates_stable_review_and_appends_correction(self):
        packet = build_sam_meat_launch_packet(
            [{"message_id": "m1", "message_type": "incoming", "content": "1 half carcass Set A."},
             {"message_id": "m2", "message_type": "incoming", "content": "Actually 2 half carcasses."}],
            conversation_ref="c1", inbound_event_id="m2", lead_id="LEAD-1", truth_readers=truth_readers(),
        )
        calls = []
        def store(payload, database_url=None):
            calls.append(payload)
            return ({"success": True, "status": "sales_conversation_learning_event_recorded", "created_count": 1,
                     "learning_event_id": payload["learning_event_id"]}, 200)
        with patch.object(conversation_learning, "record_sales_conversation_learning_event", side_effect=store):
            first, first_status = conversation_learning.record_sam_meat_launch_review_packet(packet, "LEAD-1")
            second, second_status = conversation_learning.record_sam_meat_launch_review_packet(packet, "LEAD-1")
        self.assertEqual((first_status, second_status), (200, 200))
        self.assertTrue(first["persisted"] and second["persisted"])
        self.assertEqual(calls[0]["learning_event_id"], calls[2]["learning_event_id"])
        self.assertNotEqual(calls[0]["learning_event_id"], calls[1]["learning_event_id"])
        self.assertTrue(all(not call["sends_customer_message"] and not call["creates_order"] and not call["changes_stock"] for call in calls))

    def test_command_state_projects_persisted_owner_packet(self):
        event = {"learning_event_id": "SAM-MEAT-REVIEW-1", "event_source": "sam_meat_launch_packet", "event_type": "owner_review_note",
                 "sam_reply_excerpt": "Prepared reply", "missing_facts": ["delivery_address"],
                 "captured_facts": {"packet_version": "v2", "facts": {"quantity": 2}, "fact_evidence": {}, "corrections": [],
                    "catalogue_match": {"status": "matched"}, "quantity": {"value": 2, "unit": "half_carcass"},
                    "price_basis": {"status": "current_verified_rule"}, "availability": {"status": "Unavailable"},
                    "fulfilment": {"status": "verified_fulfilment"}, "butcher_loop": {"status": "Unavailable"},
                    "protected_decision": {"required": False}, "diagnostics": {"contains_sensitive_values": False}, "authority": {"sends_customer_message": False}}}
        result = sam_command_state._launch_review_packet({"learning_events": [event]})
        self.assertTrue(result["persisted"])
        self.assertEqual(result["prepared_reply"], "Prepared reply")
        self.assertEqual(result["missing_facts"], ["delivery_address"])
        self.assertEqual(result["availability"]["status"], "Unavailable")
        self.assertFalse(result["sends_customer_message"])
        self.assertFalse(result["creates_order"])

    def test_existing_command_room_displays_packet_without_send_control(self):
        template = Path("templates/meat-sales-leads.html").read_text(encoding="utf-8")
        script = Path("static/js/meatSalesLeads.js").read_text(encoding="utf-8")
        self.assertIn("SAM Meat Prepared Review", template)
        self.assertIn("No send performed. Owner review only.", template)
        self.assertIn("/command-state`)", script)
        self.assertIn("launch_review_packet", script)
        self.assertIn("renderLaunchReview", script)
        self.assertIn("textContent", script)
        self.assertNotIn("sam_meat_launch_send", template)

    def test_diagnostics_and_command_projection_do_not_expose_address(self):
        packet = build_sam_meat_launch_packet(
            ["Deliver to 10 Private Road, Riversdale. 1 half carcass Set A."],
            conversation_ref="c", inbound_event_id="m", truth_readers=truth_readers(),
        )
        self.assertNotIn("10 Private Road", str(packet["diagnostics"]))
        self.assertFalse(packet["diagnostics"]["contains_sensitive_values"])


if __name__ == "__main__":
    unittest.main()
