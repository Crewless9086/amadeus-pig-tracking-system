import unittest

from modules.sales.butcher_truth_board import AUTHORITY, build_butcher_truth_board


class ButcherTruthBoardTests(unittest.TestCase):
    def test_open_half_cut_promise_and_pop_remain_blocked(self):
        result = build_butcher_truth_board(
            {"meat_match": {"recommendation": {"pig_id": "P1"}, "criteria": {"cut_set": "Set A"}}},
            {"reservations": [{"reservation_id": "R1", "pig_id": "P1", "carcass_side": "half_a", "cut_set": "Set A", "status": "half_reserved_pending_pair"}], "assembly": {"pop_received_unverified": True, "deposit_confirmed": False}},
            {"batches": []}, {"reconciliation": {}},
        )
        self.assertEqual(result["truth_status"], "awaiting_bank_confirmation")
        self.assertEqual(result["commitments"][0]["cut_set"], "Set A")
        self.assertFalse(result["payment"]["money_cleared_for_next_operation"])
        for key, value in AUTHORITY.items():
            self.assertEqual(result[key], value)

    def test_duplicate_half_commitment_fails_closed(self):
        reservations = [
            {"reservation_id": "R1", "pig_id": "P1", "carcass_side": "half_a"},
            {"reservation_id": "R2", "pig_id": "P1", "carcass_side": "half_a"},
        ]
        result = build_butcher_truth_board(
            {"meat_match": {"recommendation": {"pig_id": "P1"}}},
            {"reservations": reservations, "assembly": {"deposit_confirmed": True}},
            {"batches": []}, {"reconciliation": {}},
        )
        self.assertEqual(result["truth_status"], "blocked_conflict")

    def test_packed_weight_reconciliation_sets_balance_gate(self):
        result = build_butcher_truth_board(
            {"meat_match": {"recommendation": {"pig_id": "P1"}}},
            {"reservations": [{"reservation_id": "R1", "pig_id": "P1", "carcass_side": "full", "cut_set": "Set B"}], "assembly": {"deposit_confirmed": True}},
            {"batches": [{"batch_id": "B1", "pig_ids": ["P1"], "status": "Packed"}]},
            {"reconciliation": {"actual_packed_weight_kg": 42.5, "ready_for_delivery_release": False}},
        )
        self.assertEqual(result["truth_status"], "awaiting_balance_confirmation")
        self.assertEqual(result["packed_weight_reconciliation"]["actual_packed_weight_kg"], 42.5)


if __name__ == "__main__":
    unittest.main()
