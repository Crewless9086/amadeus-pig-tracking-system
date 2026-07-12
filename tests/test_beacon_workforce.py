import unittest
from unittest.mock import patch

from modules.beacon.workforce import beacon_workforce_scorecard


class BeaconWorkforceTests(unittest.TestCase):
    @patch("modules.beacon.workforce.facebook_posting_policy")
    @patch("modules.beacon.workforce.list_beacon_facebook_post_execution_events")
    @patch("modules.beacon.workforce.list_beacon_campaign_performance_events")
    @patch("modules.beacon.workforce.list_beacon_manual_post_evidence")
    @patch("modules.beacon.workforce.list_beacon_media_assets")
    def test_scorecard_excludes_smoke_evidence_from_production_metrics(
        self, media, manual, performance, executions, policy
    ):
        media.return_value = ({
            "assets": [
                {"title": "Approved farm photo", "effective_public_use_approved": True},
                {"title": "Beacon storage smoke test", "effective_public_use_approved": True},
            ],
            "counts": {"needs_review": 2},
        }, 200)
        manual.return_value = ({"manual_post_events": [
            {"campaign_label": "Real livestock campaign"},
            {"campaign_label": "TEST FLOW - delete after test"},
        ]}, 200)
        performance.return_value = ({"performance_events": [
            {"campaign": "Real campaign", "qualified_buyer_leads": 3, "spend_amount": 120},
            {"notes": "smoke test", "qualified_buyer_leads": 99, "spend_amount": 999},
        ]}, 200)
        executions.return_value = ({"execution_events": [
            {"exact_text": "Real campaign", "execution_status": "facebook_page_post_sent"},
            {"exact_text": "TEST DELETE AFTER setup", "execution_status": "facebook_page_post_sent"},
        ]}, 200)
        policy.return_value = {
            "enabled": True,
            "page_id_configured": True,
            "page_access_token_configured": True,
        }

        result = beacon_workforce_scorecard()
        scorecard = result["scorecard"]

        self.assertTrue(result["success"])
        self.assertEqual(scorecard["approved_assets"], 1)
        self.assertEqual(scorecard["production_manual_posts"], 1)
        self.assertEqual(scorecard["production_posts_sent"], 1)
        self.assertEqual(scorecard["production_performance_events"], 1)
        self.assertEqual(scorecard["qualified_buyer_leads"], 3)
        self.assertEqual(scorecard["tracked_spend_zar"], 120)
        self.assertFalse(scorecard["scheduling_enabled"])
        self.assertFalse(scorecard["paid_spend_enabled"])


if __name__ == "__main__":
    unittest.main()
