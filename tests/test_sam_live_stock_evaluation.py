import unittest

from modules.sales.sam_live_stock_evaluation import (
    aggregate_scorecard,
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

    def test_twenty_safe_unchanged_replies_become_candidate_not_enabled(self):
        graduation = graduation_by_reply_class([
            {"reply_class": "location_question", "owner_reply_classification": "approved_verbatim"}
            for _ in range(20)
        ])
        row = graduation["classes"]["location_question"]
        self.assertTrue(row["narrow_auto_send_candidate"])
        self.assertFalse(row["auto_send_enabled"])
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
        }]
        scorecard = owner_learning_scorecard(events)
        self.assertEqual(scorecard["captured_owner_replies"], 1)
        self.assertEqual(scorecard["unchanged_rate"], 1.0)
        self.assertFalse(scorecard["auto_send_enabled"])


if __name__ == "__main__":
    unittest.main()
