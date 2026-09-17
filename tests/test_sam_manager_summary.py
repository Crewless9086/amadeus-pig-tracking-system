import unittest

from modules.sales.sam_manager_summary import build_sam_manager_summary


def row(index, response_state="none", workflow_state="handled", **extra):
    return {
        "account_id": "147387", "inbox_id": "96568",
        "conversation_id": str(2100 + index),
        "inbound_message_id": str(700000000 + index),
        "livestock_context_verified": True, "new_lead": True,
        "response_state": response_state, "workflow_state": workflow_state, **extra,
    }


class SamManagerSummaryTests(unittest.TestCase):
    def build(self, rows, **kwargs):
        return build_sam_manager_summary(
            rows, period_started_at_utc="2026-07-31T13:49:00+00:00",
            observed_at_utc="2026-08-03T10:00:00+00:00", **kwargs,
        )

    def test_compact_counts_and_zero_authority(self):
        packet = self.build([
            row(1, "provider_confirmed_answer", "awaiting_customer", automatically_admitted=True,
                provider_delivery_confirmed=True, delivery_evidence_id="D1"),
            row(2, "none", "awaiting_customer"),
            row(3, "none", "qualification_in_progress", protected_decision_type="delivery",
                protected_decision_evidence_id="P1"),
            row(4, "delivery_quarantined_do_not_retry",
                automatic_retry_prohibited=True, quarantine_evidence_id="Q1"),
            row(5, "none", "acknowledgement_close_suppressed", automatically_admitted=True),
        ])
        self.assertEqual(packet["leads_received"], 5)
        self.assertEqual(packet["customers_answered"], 1)
        self.assertEqual(packet["unresolved_protected_decisions"], 1)
        self.assertEqual(packet["quarantines"], 1)
        self.assertTrue(packet["lane_continuously_admitting"])
        self.assertTrue(packet["automatic_customer_response_proven"])
        self.assertEqual(packet["protected_decision_types"], {"delivery": 1})
        self.assertFalse(packet["contains_individual_messages"])
        self.assertFalse(packet["customer_send_authorized"])
        self.assertFalse(packet["customer_mutation_authorized"])
        self.assertFalse(packet["farm_mutation_authorized"])

    def test_delivery_and_quarantine_require_exact_evidence(self):
        with self.assertRaisesRegex(ValueError, "delivery_evidence"):
            self.build([row(1, "provider_confirmed_answer")])
        with self.assertRaisesRegex(ValueError, "quarantine_evidence"):
            self.build([row(1, "delivery_quarantined_do_not_retry")])

    def test_exact_identity_is_unique_and_customer_detail_is_rejected(self):
        item = row(1, "awaiting_sam", "new_customer_inbound")
        with self.assertRaisesRegex(ValueError, "exact_unique_identity"):
            self.build([item, dict(item)])
        with self.assertRaisesRegex(ValueError, "customer_detail"):
            self.build([row(2, "awaiting_sam", customer_name="Private")])
        with self.assertRaisesRegex(ValueError, "customer_detail"):
            self.build([row(3, "awaiting_sam", content="private message")])

    def test_systemic_and_conversation_coverage_exceptions_remain_distinct(self):
        packet = self.build([], coverage_exceptions=[
            {"exception_type": "provider_chronology_unavailable", "systemic": True},
            {"exception_type": "closed_window", "systemic": False, "count": 2},
            {"exception_type": "closed_window", "systemic": False},
        ])
        self.assertEqual(packet["status"], "coverage_incomplete")
        self.assertFalse(packet["evidence_complete"])
        self.assertEqual(packet["coverage_exceptions"], [
            {"exception_type": "closed_window", "count": 3, "systemic": False},
            {"exception_type": "provider_chronology_unavailable", "count": 1, "systemic": True},
        ])

    def test_complete_empty_period_is_quiet_not_false_activity(self):
        packet = self.build([])
        self.assertEqual(packet["status"], "quiet_no_new_livestock_activity")
        self.assertEqual(packet["leads_received"], 0)

    def test_acknowledgement_admission_proves_listener_not_customer_send(self):
        packet = self.build([
            row(1, "none", "acknowledgement_close_suppressed", automatically_admitted=True,
                new_lead=False)
        ])
        self.assertTrue(packet["lane_continuously_admitting"])
        self.assertFalse(packet["automatic_customer_response_proven"])
        self.assertEqual(packet["customers_answered"], 0)
        self.assertEqual(packet["leads_received"], 0)

    def test_unrelated_automatic_admission_cannot_prove_automatic_answer(self):
        packet = self.build([
            row(1, "none", "acknowledgement_close_suppressed", automatically_admitted=True),
            row(2, "provider_confirmed_answer", provider_delivery_confirmed=True,
                delivery_evidence_id="D2", automatically_admitted=False),
        ])
        self.assertTrue(packet["lane_continuously_admitting"])
        self.assertFalse(packet["automatic_customer_response_proven"])


if __name__ == "__main__":
    unittest.main()
