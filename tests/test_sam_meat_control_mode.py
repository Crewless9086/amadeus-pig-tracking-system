import unittest
from unittest.mock import Mock

from modules.sales.beacon_campaign import execute_beacon_facebook_page_post
from modules.sales.meat_documents import (
    generate_meat_deposit_pro_forma_pdf,
    generate_meat_estimated_quote_pdf,
    generate_meat_final_invoice_pdf,
    send_meat_estimated_quote_to_chatwoot,
)
from modules.sales.meat_fulfillment import record_meat_fulfillment_event, send_meat_journey_notification
from modules.sales.meat_ops import (
    approve_meat_instruction_draft,
    build_meat_instruction_drafts,
    create_carcass_reservation_from_lead,
    record_carcass_reservation_event,
    record_meat_deposit_event,
    send_approved_meat_instruction,
)
from modules.sales.sam_meat_control_mode import sam_meat_control_policy


class SamMeatControlModeTests(unittest.TestCase):
    def test_policy_is_fail_closed(self):
        policy = sam_meat_control_policy()
        self.assertEqual(policy["mode"], "interest_capture_only")
        self.assertFalse(policy["butcher_loop_proven"])
        self.assertFalse(policy["customer_public_output_enabled"])
        self.assertEqual(policy["blockers"], ["butcher_loop_not_proven"])

    def test_direct_service_bypasses_are_denied(self):
        sender = Mock()
        calls = [
            send_meat_estimated_quote_to_chatwoot("lead", environ={"MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED": "1"}, chatwoot_sender=sender),
            generate_meat_estimated_quote_pdf("lead", database_url="postgresql://unused"),
            generate_meat_deposit_pro_forma_pdf("lead", database_url="postgresql://unused"),
            generate_meat_final_invoice_pdf("lead", database_url="postgresql://unused"),
            create_carcass_reservation_from_lead("lead", {"pig_id": "pig"}, database_url="postgresql://unused"),
            record_carcass_reservation_event("lead", {"event_type": "reservation_cancelled"}, database_url="postgresql://unused"),
            record_meat_deposit_event("lead", {"reservation_id": "r"}, database_url="postgresql://unused"),
            build_meat_instruction_drafts("lead", database_url="postgresql://unused"),
            approve_meat_instruction_draft("lead", "draft", database_url="postgresql://unused"),
            send_approved_meat_instruction("lead", "draft", database_url="postgresql://unused", sender=sender),
            record_meat_fulfillment_event("lead", {"event_type": "packed"}, database_url="postgresql://unused"),
            send_meat_journey_notification("lead", {"message": "ready"}, database_url="postgresql://unused", sender=sender),
            execute_beacon_facebook_page_post({"campaign_lane": "meat_launch"}, poster=sender),
        ]
        for body, status in calls:
            self.assertEqual(status, 409)
            self.assertEqual(body["status"], "sam_meat_controlled_mode_blocked")
            self.assertFalse(body["sent"])
        sender.assert_not_called()


if __name__ == "__main__":
    unittest.main()
