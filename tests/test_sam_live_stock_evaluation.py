import unittest
from datetime import datetime, timezone

from modules.sales.sam_live_stock_evaluation import (
    aggregate_scorecard,
    build_charlie_sam_oversight_packet,
    build_response_class_graduation_event,
    evaluate_response_class_graduation,
    graduation_by_reply_class,
    readiness_decision,
    score_replay_case,
    owner_learning_scorecard,
)


class SamLiveStockEvaluationTests(unittest.TestCase):
    def test_scores_expected_action_language_and_facts(self):
        score = score_replay_case(
            {
                "case_id": "AF-LOCATION",
                "reply_class": "location_question",
                "expected_next_action": "answer_location",
                "expected_language": "afrikaans",
                "expected_facts": {"quantity": 3},
            },
            {
                "facts": {"quantity": 3, "customer_language": "afrikaans"},
                "conversation_plan": {"next_action": "answer_location"},
                "internal_next_action": "answer_location",
                "suggested_reply_text": "Ons is in die Riversdal-omgewing.",
                "conversation_review": {"blocked_reasons": []},
            },
        )
        self.assertTrue(score["facts_correct"])
        self.assertTrue(score["next_action_correct"])
        self.assertTrue(score["language_correct"])
        self.assertTrue(score["human_voice"])

    def test_readiness_cannot_reach_98_without_production_evidence(self):
        scorecard = aggregate_scorecard([
            {
                "facts_correct": True,
                "next_action_correct": True,
                "language_correct": True,
                "relevant_answer": True,
                "human_voice": True,
                "unsafe": False,
                "invented_commitment": False,
            }
        ])
        readiness = readiness_decision(scorecard, {"classes": {}})
        self.assertFalse(readiness["gates"]["production_evidence"])
        self.assertEqual(readiness["confidence_ceiling"], 0.95)
        self.assertFalse(readiness["auto_send_enabled"])

    def test_legacy_twenty_eighty_calculation_cannot_compete(self):
        graduation = graduation_by_reply_class([
            {
                "reply_class": "greeting",
                "owner_reply_classification": "approved_verbatim",
                "provider_confirmed": True,
                "observed_at": "2026-07-25T00:00:00+00:00",
            }
            for _ in range(20)
        ])
        row = graduation["classes"]["greeting"]
        self.assertEqual(row["decision"], "withheld")
        self.assertFalse(row["runtime_enabled"])
        self.assertFalse(graduation["legacy_20_80_calculation_active"])
        self.assertTrue(graduation["owner_activation_required"])

    def test_owner_learning_scorecard_reports_real_acceptance_without_enabling_send(self):
        events = [{
            "source_agent": "sam_live_stock_backend",
            "chatwoot_conversation_id": "1",
            "captured_facts": {
                "learning_kind": "owner_reply_capture",
                "reply_class": "price_question",
                "owner_reply_classification": "approved_verbatim",
            },
        }, {
            "source_agent": "sam_live_stock_backend",
            "chatwoot_conversation_id": "2",
            "captured_facts": {"learning_kind": "owner_reply_historical_example"},
        }]
        scorecard = owner_learning_scorecard(events)
        self.assertEqual(scorecard["captured_owner_replies"], 1)
        self.assertEqual(scorecard["unchanged_rate"], 1.0)
        self.assertEqual(scorecard["historical_owner_reply_examples"], 1)
        self.assertEqual(scorecard["total_learning_examples"], 2)
        self.assertFalse(scorecard["auto_send_enabled"])

    def test_one_low_risk_class_can_candidate_without_enabling_another(self):
        rows = [
            {
                "response_class": "greeting",
                "observed_at": "2026-07-24T12:00:00+00:00",
                "owner_approved": True,
                "provider_confirmed": True,
                "escalation_correct": True,
            }
            for _ in range(30)
        ]
        result = evaluate_response_class_graduation(
            rows, now=datetime(2026, 7, 25, tzinfo=timezone.utc)
        )
        self.assertEqual(result["classes"]["greeting"]["decision"], "candidate")
        self.assertFalse(result["classes"]["greeting"]["runtime_enabled"])
        self.assertEqual(result["classes"]["thanks"]["decision"], "withheld")
        self.assertIsNone(
            result["classes"]["thanks"]["evidence"]["delivery_ambiguity_rate"]
        )
        self.assertFalse(result["runtime_authority_changed"])

    def test_failure_regresses_only_affected_class(self):
        safe = {
            "observed_at": "2026-07-24T12:00:00+00:00",
            "owner_approved": True,
            "provider_confirmed": True,
            "escalation_correct": True,
        }
        rows = [
            {"response_class": "greeting", **safe} for _ in range(30)
        ] + [
            {"response_class": "thanks", **safe} for _ in range(29)
        ] + [
            {
                "response_class": "thanks",
                **safe,
                "unsupported_claim": True,
            }
        ]
        result = evaluate_response_class_graduation(
            rows, now=datetime(2026, 7, 25, tzinfo=timezone.utc)
        )
        self.assertEqual(result["classes"]["greeting"]["decision"], "candidate")
        self.assertEqual(result["classes"]["thanks"]["decision"], "regressed")
        self.assertFalse(result["classes"]["thanks"]["gates"]["unsupported_claim"])

    def test_consequential_class_never_self_authorizes(self):
        result = evaluate_response_class_graduation(
            [
                {
                    "response_class": "quote_order_payment_reservation_protected",
                    "observed_at": "2026-07-25T00:00:00+00:00",
                    "owner_approved": True,
                    "provider_confirmed": True,
                    "escalation_correct": True,
                }
            ],
            now=datetime(2026, 7, 25, tzinfo=timezone.utc),
        )
        row = result["classes"]["quote_order_payment_reservation_protected"]
        self.assertFalse(row["gates"]["self_graduation_allowed"])
        self.assertEqual(row["decision"], "withheld")

    def test_factual_and_specialist_classes_require_verified_truth_and_canary(self):
        common = {
            "observed_at": "2026-07-25T00:00:00+00:00",
            "owner_approved": True,
            "provider_confirmed": True,
            "escalation_correct": True,
        }
        result = evaluate_response_class_graduation(
            [
                {
                    "response_class": "verified_general_factual_answer",
                    **common,
                }
                for _ in range(50)
            ]
            + [
                {
                    "response_class": "livestock_informational_answer",
                    **common,
                    "truth_source_verified": True,
                }
                for _ in range(75)
            ],
            now=datetime(2026, 7, 25, tzinfo=timezone.utc),
        )
        factual = result["classes"]["verified_general_factual_answer"]
        livestock = result["classes"]["livestock_informational_answer"]
        self.assertFalse(factual["gates"]["verified_truth"])
        self.assertFalse(livestock["gates"]["specialist_canary"])
        self.assertEqual(factual["decision"], "withheld")
        self.assertEqual(livestock["decision"], "withheld")

    def test_append_only_event_and_charlie_packet_are_sanitized_and_non_authorizing(self):
        graduation = evaluate_response_class_graduation(
            [], now=datetime(2026, 7, 25, tzinfo=timezone.utc)
        )
        row = graduation["classes"]["greeting"]
        event = build_response_class_graduation_event(
            "greeting", row, observed_at="2026-07-25T12:00:00+00:00"
        )
        self.assertTrue(event["append_only"])
        self.assertFalse(event["contains_customer_content"])
        self.assertFalse(event["runtime_enabled"])
        packet = build_charlie_sam_oversight_packet(
            graduation,
            human_backlog={"WAITING_FOR_OWNER_REPLY": 12},
            delivery_metrics={"confirmation_rate": 1.0},
        )
        self.assertTrue(packet["read_sanitized_evidence"])
        self.assertFalse(packet["may_enable_consequential_authority"])
        self.assertFalse(packet["may_send_customer_message"])


if __name__ == "__main__":
    unittest.main()
