import unittest

from modules.beacon.post_composer import build_beacon_caption_suggestions, caption_safety_issues
from modules.sales.beacon_campaign import build_live_stock_awareness_campaign_publish_packet


HISTORY = [{
    "evidence_notes": "Owner-confirmed Facebook post. Exact text: 🐷 A warm farm update.\n\nTwelve piglets are growing beautifully. 💛",
}]


class BeaconPostComposerTests(unittest.TestCase):
    def test_llm_uses_history_and_returns_safe_suggestions(self):
        captured = {}

        def requester(body):
            captured.update(body)
            return {"suggestions": ["Strong piglets and full bellies.\n\nWe love watching them grow."]}

        result, status = build_beacon_caption_suggestions(
            {"brief": "Our litter of 12 is strong and growing well", "campaign_lane": "live_stock_awareness"},
            historical_events=HISTORY,
            environ={
                "BEACON_BACKEND_LLM_ENABLED": "1",
                "BEACON_BACKEND_LLM_MODEL": "test-model",
                "OPENAI_API_KEY": "not-used-by-fake",
            },
            requester=requester,
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["suggestion_source"], "beacon_llm_with_historical_examples")
        self.assertEqual(result["historical_example_count"], 1)
        self.assertIn("PAST POST 1", captured["messages"][1]["content"])
        self.assertIn("\n\n", result["suggestions"][0])

    def test_unsafe_livestock_sales_copy_is_blocked(self):
        issues = caption_safety_issues("Piglets available now for sale. Price R450.", "live_stock_awareness")
        self.assertIn("direct_sales_wording:available", issues)
        self.assertIn("direct_sales_wording:sale", issues)
        self.assertIn("livestock_price_wording_blocked", issues)

    def test_local_fallback_remains_awareness_only(self):
        result, status = build_beacon_caption_suggestions(
            {"brief": "Our litter of 12 is strong, active and growing well", "campaign_lane": "live_stock_awareness"},
            historical_events=HISTORY,
            environ={},
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(result["suggestions"]), 3)
        self.assertTrue(all(not caption_safety_issues(text) for text in result["suggestions"]))

    def test_brief_is_required(self):
        result, status = build_beacon_caption_suggestions({}, historical_events=[])
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "post_brief_required")

    def test_owner_caption_is_bound_into_awareness_packet(self):
        assets = [{
            "asset_id": "ASSET-1", "effective_approval_status": "approved",
            "effective_public_use_approved": True, "media_type": "image",
            "content_sha256": "abc", "sale_stream_relevance": ["live_stock_awareness"],
        }]
        payload = {
            "campaign_lane": "live_stock_awareness", "draft_id": "facebook_awareness_post",
            "asset_ids": ["ASSET-1"], "channel": "Facebook",
            "owner_exact_text": "A strong litter growing beautifully on the farm.\n\nFollow their journey.",
        }
        first = build_live_stock_awareness_campaign_publish_packet(payload, approved_assets=assets)
        changed = build_live_stock_awareness_campaign_publish_packet(
            {**payload, "owner_exact_text": "A different approved farm story."}, approved_assets=assets
        )
        self.assertTrue(first["success"])
        self.assertEqual(first["selected_draft"]["exact_text"], payload["owner_exact_text"])
        self.assertIn("\n\n", first["selected_draft"]["exact_text"])
        self.assertNotEqual(first["publish_packet_id"], changed["publish_packet_id"])


if __name__ == "__main__":
    unittest.main()
