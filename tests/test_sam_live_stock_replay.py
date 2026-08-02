import unittest

from modules.agents.ledger import run_ledger
from scripts.sam_live_stock_replay import run_replay


class SamLiveStockReplayTests(unittest.TestCase):
    def test_replay_scores_without_customer_send_or_production_evidence_claim(self):
        cases = [{
            "case_id": "LOCATION-EN",
            "conversation_group": "GENERAL-1",
            "reply_class": "location_question",
            "expected_language": "english",
            "payload": {
                "event": "message_created",
                "message_type": "incoming",
                "content": "Where are you guys?",
                "conversation": {"id": 1},
                "sender": {"name": "Test"},
            },
        }]
        report = run_replay(cases)
        self.assertEqual(report["scorecard"]["evaluated_turns"], 1)
        self.assertFalse(report["scorecard"]["production_evidence_complete"])
        self.assertFalse(report["readiness"]["ready_for_narrow_auto_send_owner_decision"])
        self.assertFalse(report["readiness"]["auto_send_enabled"])

    def test_sanitized_vertical_slice_unversioned_rows_fail_closed_without_private_output(self):
        cases = [{
            "case_id": "SANITIZED-LIVE-STOCK-01",
            "conversation_group": "SANITIZED-CONVERSATION-01",
            "reply_class": "quote_preparation",
            "expected_language": "mixed_afrikaans_english",
            "expected_facts": {"sales_lane": "live_stock_sales", "quantity": 2, "category": "weaner", "sex": "female"},
            "payload": {
                "event": "message_created", "message_type": "incoming",
                "content": "I need 2 female weaners around 12kg next week in Riversdale. Can you prepare a quote?",
                "conversation": {"id": "SAN-01"}, "sender": {"name": "Sanitized Buyer"},
            },
            "intake_context": {"success": True, "known_fields": {}, "items": []},
            "availability_rows": [
                {"pig_id": "SAN-W-01", "sex": "Female", "status": "Active", "on_farm": "Yes", "reserved_status": "", "available_for_sale": "Yes", "purpose": "Sale", "live_stock_sale_eligible": True, "sale_category": "Weaner", "current_weight_kg": 12},
                {"pig_id": "SAN-W-02", "sex": "Female", "status": "Active", "on_farm": "Yes", "reserved_status": "", "available_for_sale": "Yes", "purpose": "Sale", "live_stock_sale_eligible": True, "sale_category": "Weaner", "current_weight_kg": 12},
            ],
            "herdmaster_evidence": {"provenance": "sanitized_herdmaster_snapshot", "freshness": "sanitized_fixture", "summary": {"sale_ready_pigs": 51, "meat_window_pigs": 6, "breeding_animals_excluded": 15}},
            "ledger_price_rule": {"found": True, "unit_price": 450, "currency": "ZAR", "source": "sanitized_sales_pricing_snapshot"},
            "order_warning_review": [
                {"warning": "completed_order", "classification": "useful_for_owner_review"},
                {"warning": "cancelled_order", "classification": "false_positive_not_blocking"},
            ],
        }]
        report = run_replay(cases)
        entry = report["trace"][0]

        self.assertEqual(entry["evidence_used"]["herdmaster"]["summary"]["sale_ready_pigs"], 51)
        self.assertEqual(entry["evidence_used"]["herdmaster"]["provenance"], "sanitized_herdmaster_snapshot")
        self.assertEqual(entry["evidence_used"]["ledger"]["payment"]["status"], "unknown")
        self.assertEqual(entry["evidence_used"]["matched_candidate_evidence"], [])
        self.assertFalse(entry["quote_order_preparation"]["draft_order_ready"])
        self.assertEqual(entry["quote_order_preparation"]["stock_preselection"]["selected_pig_ids"], [])
        self.assertEqual(entry["quote_order_preparation"]["stock_preselection"]["quantity_shortfall"], 2)
        self.assertEqual(entry["evidence_used"]["supplied_order_warning_review"][1]["classification"], "false_positive_not_blocking")
        self.assertTrue(entry["response_proposal"])
        response = entry["response_proposal"].casefold()
        for private_value in ("san-w-01", "san-w-02", "pig_id", "tag_number", "current_pen", "medical_status", "withdrawal_end", "reserved_for_order", "allocation_evidence", "order_id"):
            self.assertNotIn(private_value, response)
        self.assertTrue(entry["quote_order_preparation"]["owner_gate_required"])
        self.assertFalse(entry["authority_decision"]["writes_or_sends_attempted"])
        self.assertFalse(report["owner_review_packet"]["customer_send_or_write_attempted"])

    def test_versioned_affirmative_rows_remain_eligible_and_proposal_only(self):
        contract = {
            "sex": "Female", "status": "Active", "on_farm": "Yes", "purpose": "Sale",
            "available_for_sale": "Yes", "live_stock_sale_eligible": True,
            "exact_animal_eligibility_contract_version": "herdmaster_exact_animal_eligibility_v1",
            "evidence_complete": True, "eligibility_observed_at": "2026-07-24",
            "allocation_query_status": "known", "allocation_evidence_state": "known_unallocated",
            "reserved_status": "Not_Reserved", "withdrawal_evidence_state": "not_applicable",
            "withdrawal_clear": "Yes", "medical_status": "Clear", "calculated_stage": "Weaner",
            "sale_category": "Weaner", "current_weight_kg": 12, "latest_weight_date": "2026-07-24",
            "days_since_weight": 0,
        }
        cases = [{
            "case_id": "SANITIZED-VERSIONED-01",
            "conversation_group": "SANITIZED-CONVERSATION-VERSIONED",
            "reply_class": "quote_preparation",
            "payload": {
                "event": "message_created", "message_type": "incoming",
                "content": "I need 2 female weaners around 12kg next week in Riversdale. Can you prepare a quote?",
                "conversation": {"id": "SAN-V1"}, "sender": {"name": "Sanitized Buyer"},
            },
            "availability_rows": [
                dict(contract, pig_id="SAN-V-01"),
                dict(contract, pig_id="SAN-V-02"),
            ],
            "ledger_price_rule": {"found": True, "unit_price": 450, "currency": "ZAR", "source": "sanitized_sales_pricing_snapshot"},
        }]
        entry = run_replay(cases)["trace"][0]
        selected = entry["quote_order_preparation"]["stock_preselection"]
        self.assertEqual(len(entry["evidence_used"]["matched_candidate_evidence"]), 2)
        self.assertEqual(selected["selected_pig_ids"], ["SAN-V-01", "SAN-V-02"])
        self.assertEqual(selected["quantity_shortfall"], 0)
        self.assertTrue(selected["proposal_only"])
        self.assertFalse(entry["authority_decision"]["writes_or_sends_attempted"])

    def test_missing_or_non_sale_purpose_cannot_support_quote_preparation(self):
        base = {
            "sex": "Female", "status": "Active", "on_farm": "Yes", "reserved_status": "",
            "available_for_sale": "Yes", "live_stock_sale_eligible": True,
            "sale_category": "Weaner", "current_weight_kg": 12,
        }
        cases = [{
            "case_id": "SANITIZED-NON-SALE-01",
            "conversation_group": "SANITIZED-CONVERSATION-02",
            "reply_class": "quote_preparation",
            "payload": {"event": "message_created", "message_type": "incoming", "content": "I need 2 female weaners around 12kg next week in Riversdale. Can you prepare a quote?", "conversation": {"id": "SAN-02"}, "sender": {"name": "Sanitized Buyer"}},
            "availability_rows": [dict(base, pig_id="SAN-MISSING"), dict(base, pig_id="SAN-BREEDING", purpose="Breeding")],
            "ledger_price_rule": {"found": True, "unit_price": 450, "currency": "ZAR", "source": "sanitized_sales_pricing_snapshot"},
        }]
        entry = run_replay(cases)["trace"][0]
        self.assertEqual(entry["evidence_used"]["matched_candidate_evidence"], [])
        self.assertFalse(entry["quote_order_preparation"]["draft_order_ready"])

    def test_ledger_defaults_payment_to_unknown_without_canonical_evidence(self):
        evidence = run_ledger({"known_context": {"pricing": {"found": True, "unit_price": 450, "currency": "ZAR"}}})
        self.assertEqual(evidence["payment"]["status"], "unknown")
        self.assertFalse(evidence["payment"]["payment_confirmation_allowed"])

    def test_ledger_verified_status_never_grants_payment_confirmation_authority(self):
        evidence = run_ledger({
            "known_context": {
                "pricing": {"found": True, "unit_price": 450, "currency": "ZAR"},
                "payment": {"status": "verified"},
            }
        })
        self.assertEqual(evidence["payment"]["status"], "verified")
        self.assertFalse(evidence["payment"]["payment_confirmation_allowed"])
        self.assertIn("never authorizes payment confirmation", evidence["payment"]["authority_note"])

    def test_ledger_preserves_missing_price_as_an_explicit_unknown(self):
        evidence = run_ledger({"known_context": {"pricing": {"found": False}}})
        self.assertFalse(evidence["facts"][0]["value"])
        self.assertIn("Active price rule is missing.", evidence["unresolved_questions"])


if __name__ == "__main__":
    unittest.main()
