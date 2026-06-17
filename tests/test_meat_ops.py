import unittest
from unittest.mock import patch

from modules.sales import meat_ops


class MeatOpsTests(unittest.TestCase):
    def test_first_half_reserves_pending_pair(self):
        side, status, block = meat_ops._next_carcass_slot("half_carcass", [])

        self.assertEqual(side, "half_a")
        self.assertEqual(status, "half_reserved_pending_pair")
        self.assertEqual(block, "")

    def test_second_half_commits_full_carcass(self):
        side, status, block = meat_ops._next_carcass_slot("half_carcass", [{
            "pig_id": "PIG-1",
            "carcass_side": "half_a",
            "status": "half_reserved_pending_pair",
        }])

        self.assertEqual(side, "half_b")
        self.assertEqual(status, "full_carcass_committed")
        self.assertEqual(block, "")

    def test_full_carcass_is_blocked_when_half_already_reserved(self):
        side, status, block = meat_ops._next_carcass_slot("full_carcass", [{
            "pig_id": "PIG-1",
            "carcass_side": "half_a",
            "status": "half_reserved_pending_pair",
        }])

        self.assertEqual(side, "")
        self.assertEqual(status, "")
        self.assertEqual(block, "pig_has_half_reservation_already")

    def test_assembly_requires_full_carcass_and_deposit(self):
        reservations = [
            {
                "reservation_id": "RES-1",
                "pig_id": "PIG-1",
                "carcass_side": "half_a",
                "status": "half_reserved_pending_pair",
                "created_at": "2026-06-16T01:00:00",
            },
            {
                "reservation_id": "RES-2",
                "pig_id": "PIG-1",
                "carcass_side": "half_b",
                "status": "full_carcass_committed",
                "created_at": "2026-06-16T02:00:00",
            },
        ]

        pending = meat_ops._assembly_status(reservations, [])
        ready = meat_ops._assembly_status(reservations, [{"event_type": "deposit_confirmed"}])

        self.assertTrue(pending["full_carcass_committed"])
        self.assertFalse(pending["ready_for_instruction_drafts"])
        self.assertTrue(ready["deposit_confirmed"])
        self.assertTrue(ready["ready_for_slaughter_booking"])

    def test_cancelled_reservation_does_not_count_as_active(self):
        reservations = [{
            "reservation_id": "RES-1",
            "pig_id": "PIG-1",
            "carcass_side": "half_a",
            "status": "half_reserved_pending_pair",
            "effective_status": "cancelled",
            "created_at": "2026-06-16T01:00:00",
        }]

        assembly = meat_ops._assembly_status(reservations, [])
        side, status, block = meat_ops._next_carcass_slot("half_carcass", reservations)

        self.assertEqual(assembly["status"], "interest_only")
        self.assertEqual(assembly["active_reservation_count"], 0)
        self.assertEqual(side, "half_a")
        self.assertEqual(status, "half_reserved_pending_pair")
        self.assertEqual(block, "")

    def test_confirmed_deposit_requires_amount_and_reference(self):
        missing_amount, amount_code = meat_ops.record_meat_deposit_event(
            "LEAD-1",
            {"reservation_id": "RES-1", "payment_reference": "EFT-123"},
            database_url="",
        )
        missing_reference, reference_code = meat_ops.record_meat_deposit_event(
            "LEAD-1",
            {"reservation_id": "RES-1", "amount": "1000"},
            database_url="",
        )

        self.assertEqual(amount_code, 400)
        self.assertEqual(missing_amount["status"], "deposit_amount_required")
        self.assertEqual(reference_code, 400)
        self.assertEqual(missing_reference["status"], "deposit_reference_required")

    def test_cancel_reservation_requires_reason(self):
        result, status_code = meat_ops.record_carcass_reservation_event(
            "LEAD-1",
            {"reservation_id": "RES-1", "event_type": "reservation_cancelled"},
            database_url="",
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "reservation_cancel_reason_required")

    def test_instruction_drafts_are_internal_drafts_only(self):
        reservation = {
            "reservation_id": "RES-1",
            "order_id": "ORD-1",
            "pig_id": "PIG-1",
            "tag_number": "TAG-1",
            "cut_set": "Set A",
            "estimated_packed_weight": "25kg packed estimate",
        }

        drafts = meat_ops._instruction_draft_params(
            "LEAD-1",
            reservation,
            [{"event_type": "deposit_confirmed", "payment_reference": "EFT-123"}],
            {},
        )

        self.assertEqual({draft["instruction_type"] for draft in drafts}, {"abattoir_booking", "butcher_cut_sheet"})
        self.assertIn("draft only", drafts[0]["draft_message"].lower())
        self.assertIn("Set A", drafts[1]["draft_message"])

    def test_instruction_effective_status_prefers_sent_and_exception(self):
        self.assertEqual(meat_ops._instruction_effective_status([]), "draft")
        self.assertEqual(meat_ops._instruction_effective_status([
            {"event_type": "approved_to_send", "created_at": "2026-06-16T01:00:00"},
        ]), "approved_to_send")
        self.assertEqual(meat_ops._instruction_effective_status([
            {"event_type": "approved_to_send", "created_at": "2026-06-16T01:00:00"},
            {"event_type": "exception_review_required", "created_at": "2026-06-16T02:00:00"},
        ]), "exception_review_required")
        self.assertEqual(meat_ops._instruction_effective_status([
            {"event_type": "exception_review_required", "created_at": "2026-06-16T02:00:00"},
            {"event_type": "exception_review_resolved", "created_at": "2026-06-16T03:00:00"},
        ]), "draft")
        self.assertEqual(meat_ops._instruction_effective_status([
            {"event_type": "send_failed", "created_at": "2026-06-16T04:00:00"},
        ]), "send_failed")
        self.assertEqual(meat_ops._instruction_effective_status([
            {"event_type": "send_failed", "created_at": "2026-06-16T04:00:00"},
            {"event_type": "sent", "created_at": "2026-06-16T05:00:00"},
        ]), "sent")

    @patch.dict("os.environ", {"MEAT_INSTRUCTION_SEND_ENABLED": "0"}, clear=False)
    def test_instruction_send_is_disabled_before_database_or_network(self):
        result, status_code = meat_ops.send_approved_meat_instruction(
            "LEAD-1",
            "DRAFT-1",
            {"message": "Approved text"},
            database_url="postgres://should-not-be-used",
        )

        self.assertEqual(status_code, 503)
        self.assertFalse(result["sent"])
        self.assertEqual(result["status"], "meat_instruction_send_disabled")

    def test_invalid_exception_event_type_fails_before_database(self):
        result, status_code = meat_ops.record_meat_instruction_exception(
            "LEAD-1",
            "DRAFT-1",
            {"event_type": "send_anyway"},
            database_url="",
        )

        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "invalid_exception_event_type")


if __name__ == "__main__":
    unittest.main()
