import unittest

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


if __name__ == "__main__":
    unittest.main()
