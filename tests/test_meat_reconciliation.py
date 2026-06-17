import unittest

from modules.sales.meat_reconciliation import build_final_balance_message
from modules.sales import meat_reconciliation


class MeatReconciliationTest(unittest.TestCase):
    def test_balance_message_uses_actual_packed_weight_and_deposit(self):
        message = build_final_balance_message({
            "actual_packed_weight_kg": 24.8,
            "final_amount": 3224,
            "deposit_confirmed_amount": 1600,
            "balance_due": 1624,
            "payment_reference": "PORK-TEST",
        })

        self.assertIn("24.80kg", message)
        self.assertIn("R3224.00", message)
        self.assertIn("R1600.00", message)
        self.assertIn("R1624.00", message)
        self.assertIn("PORK-TEST", message)

    def test_reconciliation_status_requires_bank_confirmed_balance(self):
        reservations = [{
            "reservation_id": "RES-1",
            "order_id": "ORD-1",
            "effective_status": "full_carcass_committed",
        }]
        deposits = [{
            "reservation_id": "RES-1",
            "event_type": "deposit_confirmed_in_bank",
            "amount": 1600,
        }]
        events = [{
            "event_type": "packed_weight_recorded",
            "reservation_id": "RES-1",
            "actual_packed_weight_kg": 24.8,
            "price_per_kg": 130,
            "final_amount": 3224,
            "balance_due": 1624,
            "created_at": "2026-06-17T01:00:00+00:00",
        }]

        status = meat_reconciliation._reconciliation_status(reservations, deposits, events)

        self.assertEqual(status["status"], "awaiting_balance_confirmation")
        self.assertFalse(status["ready_for_delivery_release"])

        events.append({
            "event_type": "balance_confirmed_in_bank",
            "reservation_id": "RES-1",
            "balance_confirmed_amount": 1624,
            "payment_reference": "BANK-1",
            "created_at": "2026-06-17T02:00:00+00:00",
        })
        status = meat_reconciliation._reconciliation_status(reservations, deposits, events)

        self.assertEqual(status["status"], "ready_for_delivery_release")
        self.assertTrue(status["ready_for_delivery_release"])

    def test_pop_does_not_count_as_confirmed_deposit(self):
        deposits = [
            {"reservation_id": "RES-1", "event_type": "pop_received_unverified", "amount": 1600},
            {"reservation_id": "RES-1", "event_type": "deposit_confirmed_in_bank", "amount": 500},
        ]

        self.assertEqual(meat_reconciliation._confirmed_deposit_amount(deposits, "RES-1"), 500)


if __name__ == "__main__":
    unittest.main()
