import unittest

from modules.sales import sam_live_stock_runtime as runtime


class SamLiveStockExactAnimalPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.rows = [
            {"pig_id": "PIG-027", "tag_number": "TAG-SECRET", "sex": "Male", "status": "Active", "on_farm": "Yes", "purpose": "Sale", "available_for_sale": "Yes", "live_stock_sale_eligible": True, "exact_animal_eligibility_contract_version": "herdmaster_exact_animal_eligibility_v1", "evidence_complete": True, "allocation_query_status": "known", "allocation_evidence_state": "known_unallocated", "reserved_status": "Not_Reserved", "withdrawal_evidence_state": "not_applicable", "sale_category": "Grower", "current_weight_kg": 27, "latest_weight_date": "2026-07-24", "days_since_weight": 0, "current_pen_id": "PEN-SECRET", "current_pen_name": "Internal Grower Pen", "health_status": "Clear", "medical_status": "Clear", "withdrawal_clear": "Yes"},
            {"pig_id": "PIG-028", "tag_number": "TAG-HELD", "sex": "Male", "status": "Active", "on_farm": "Yes", "purpose": "Sale", "available_for_sale": "No", "live_stock_sale_eligible": False, "sale_category": "Grower", "current_weight_kg": 28, "latest_weight_date": "2026-07-24", "current_pen_id": "PEN-HOLD", "medical_status": "Withdrawal hold", "current_withdrawal_end_date": "2026-08-01", "reserved_status": "Allocated", "reserved_for_order_id": "ORD-SECRET", "live_stock_sale_reason": "allocated"},
        ]
        self.facts = {"quantity": 1, "category": "grower", "sex": "male", "weight_range": "25-29 kg"}

    def eligible(self, **overrides):
        row = dict(self.rows[0])
        row.update({
            "exact_animal_eligibility_contract_version": "herdmaster_exact_animal_eligibility_v1",
            "evidence_complete": True,
            "eligibility_observed_at": "2026-07-24T19:00:00+02:00",
            "allocation_query_status": "known",
            "allocation_evidence_state": "known_unallocated",
            "reserved_status": "Not_Reserved",
            "withdrawal_evidence_state": "not_applicable",
        })
        row.update(overrides)
        return row

    def test_exact_evidence_exists_only_in_owner_proposal_not_write_payload(self):
        availability = runtime.summarize_live_stock_availability(self.rows, self.facts)
        match = runtime.build_live_stock_match_packet(self.facts, availability)
        draft = runtime.build_live_stock_draft_order_packet({"conversation_id": "test"}, self.facts, match)
        owner = runtime.build_live_stock_prepared_owner_action_bundle({"conversation_id": "test"}, self.facts, {}, draft, runtime.build_live_stock_price_answer_packet(self.facts, match), match)
        internal = str(owner["stock_preselection"])
        self.assertIn("PIG-027", internal)
        self.assertIn("PEN-SECRET", internal)
        self.assertIn("ORD-SECRET", internal)
        self.assertNotIn("pig_id", draft["sync_payload"]["requested_items"][0])
        self.assertTrue(all(line["proposal_only"] for line in draft["proposed_order_lines"]))
        self.assertTrue(draft["owner_review_required"])
        self.assertFalse(draft["exact_animal_assignment_written"])

    def test_llm_reply_that_leaks_internal_animal_evidence_is_rejected(self):
        inbound = {"content": "I need one male grower at 25 to 29 kg", "conversation_id": "test", "customer_name": "Test"}
        facts = {**self.facts, "sales_lane": "live_stock_sales", "lane_confidence": 0.99, "message_intent": "buying_intent"}
        context = {"availability": runtime.summarize_live_stock_availability(self.rows, facts), "intake_context": {}, "context_errors": []}
        decision = runtime.build_sam_live_stock_decision(
            inbound, facts, context,
            environ={runtime.LLM_ENABLED_ENV: "1", runtime.LLM_MODEL_ENV: "test", runtime.OPENAI_API_KEY_ENV: "secret"},
            llm_drafter=lambda *_: {"reply_text": "I selected PIG-027 in PEN-SECRET and excluded ORD-SECRET.", "confidence": 0.99},
        )
        reply = decision["suggested_reply_text"]
        self.assertEqual(decision["llm_draft"]["status"], "llm_reply_internal_animal_evidence_blocked")
        for secret in ("PIG-027", "TAG-SECRET", "PEN-SECRET", "ORD-SECRET", "2026-08-01"):
            self.assertNotIn(secret, reply)
        self.assertFalse(decision["creates_order"])
        self.assertFalse(decision["reserves_stock"])
        self.assertFalse(decision["changes_stock"])

    def test_exact_contract_regression_matrix_fails_closed(self):
        cases = {
            "male_request_only_female": [self.eligible(sex="Female")],
            "weight_date_without_weight": [self.eligible(current_weight_kg=None)],
            "blank_reservation": [self.eligible(reserved_status="")],
            "blank_withdrawal": [self.eligible(withdrawal_evidence_state="")],
            "unknown_purpose": [self.eligible(purpose="Unknown")],
            "active_draft_line": [self.eligible(allocation_evidence_state="allocated", allocation_order_status="Draft", allocation_line_status="Assigned")],
            "active_pending_line": [self.eligible(allocation_evidence_state="allocated", allocation_order_status="Pending Approval", allocation_line_status="Assigned")],
            "active_approved_line": [self.eligible(allocation_evidence_state="allocated", allocation_order_status="Approved", allocation_line_status="Reserved")],
            "conflicting_lifecycle": [self.eligible(status="Active", on_farm="No")],
            "raw_intermediate_without_contract": [{
                "pig_id": "RAW-1", "sex": "Male", "status": "Active", "on_farm": "Yes",
                "purpose": "Sale", "sale_category": "Grower", "current_weight_kg": 27,
            }],
        }
        for name, rows in cases.items():
            with self.subTest(name=name):
                summary = runtime.summarize_live_stock_availability(rows, self.facts)
                self.assertEqual(summary["matched_count"], 0)

    def test_three_female_bypass_shape_is_rejected_for_male_request(self):
        rows = [
            self.eligible(pig_id=f"FEMALE-{index}", sex="Female", current_weight_kg=30, sale_category="Grower")
            for index in range(1, 4)
        ]
        facts = {"quantity": 3, "category": "grower", "sex": "male", "weight_range": "30 kg"}
        match = runtime.build_live_stock_match_packet(facts, runtime.summarize_live_stock_availability(rows, facts))
        self.assertEqual(match["selected_pig_ids"], [])
        self.assertEqual(match["quantity_shortfall"], 3)
        self.assertTrue(match["proposal_only"])

    def test_correctly_eligible_animal_and_insufficient_quantity_are_explicit(self):
        facts = {"quantity": 2, "category": "grower", "sex": "male", "weight_range": "25-29 kg"}
        match = runtime.build_live_stock_match_packet(
            facts,
            runtime.summarize_live_stock_availability([self.eligible()], facts),
        )
        self.assertEqual(match["selected_pig_ids"], ["PIG-027"])
        self.assertEqual(match["quantity_shortfall"], 1)
        self.assertEqual(match["allocation_query_status"], "known")
        self.assertTrue(match["evidence_complete"])
        self.assertEqual(match["ranking"][0]["rank"], 1)
        self.assertTrue(match["proposal_only"])


if __name__ == "__main__":
    unittest.main()
