import unittest

from modules.beacon.content_operations import build_beacon_content_candidate


class BeaconContentOperationsTests(unittest.TestCase):
    def evidence(self, assets=None, opportunity_status="blocked"):
        return {
            "historical_posts": {"records": [
                {
                    "manual_post_event_id": "POST-1",
                    "posted_at": "2025-11-10T12:47:32Z",
                    "evidence_notes": "Exact text: Farm update",
                },
                {
                    "manual_post_event_id": "POST-2",
                    "posted_at": "2026-07-14T22:00:00Z",
                    "evidence_notes": "Exact text: Piglet update",
                },
            ]},
            "performance_events": {"records": [
                {
                    "performance_event_id": "PERF-LEGACY",
                    "evidence_source": "legacy_unlabelled",
                    "metric_evidence": {},
                    "source_reference": "",
                    "retrieved_at": "",
                    "reach": 999999,
                },
            ]},
            "media_assets": {"records": assets or []},
            "opportunities": {"records": [
                {
                    "card_id": "OPP-1",
                    "status": opportunity_status,
                    "freshness": {"fresh": opportunity_status == "ready_for_owner_review"},
                }
            ]},
        }

    def facts(self):
        return [{
            "fact_id": "LITTER-OBS-1",
            "statement": "Today’s livestock check recorded a settled litter",
            "source": "canonical_farm_observation",
            "source_reference": "observation/LITTER-OBS-1",
            "observed_at": "2026-07-24T08:00:00Z",
            "status": "canonical_read",
        }]

    def test_ranks_small_set_and_explains_sources_and_dates(self):
        result = build_beacon_content_candidate(
            self.evidence(), current_facts=self.facts(), now="2026-07-24T10:00:00Z"
        )

        self.assertEqual(len(result["ranked_ideas"]), 3)
        self.assertEqual(result["ranked_ideas"][0]["idea_id"], "livestock_care_story")
        history = result["ranked_ideas"][0]["supporting_evidence"][0]
        self.assertEqual(history["date_coverage"]["from"], "2025-11-10T12:47:32Z")
        self.assertEqual(history["date_coverage"]["to"], "2026-07-14T22:00:00Z")
        self.assertEqual(
            result["evidence_quality"]["verified_performance_event_count"], 0
        )
        self.assertIn("insufficiently normalized", result["ranked_ideas"][0]["why"])

    def test_prepares_exact_owner_review_packet_without_public_authority(self):
        result = build_beacon_content_candidate(
            self.evidence(), current_facts=self.facts(), now="2026-07-24T10:00:00Z"
        )
        packet = result["owner_review_packet"]

        self.assertEqual(packet["review_status"], "awaiting_owner_review")
        self.assertIn("settled litter", packet["draft_copy"])
        self.assertEqual(packet["channel"], "Facebook Page")
        self.assertIn("qualified inbound", packet["measurable_objective"]["metric"])
        self.assertEqual(packet["media"]["status"], "media_gap")
        self.assertTrue(packet["authority"]["owner_exact_packet_approval_required"])
        for flag in (
            "posts_publicly", "sends_customer_messages", "calls_meta",
            "creates_ads", "boosts_posts", "spends_money", "changes_stock",
            "writes_farm_data",
        ):
            self.assertFalse(packet["authority"][flag])

    def test_selects_only_hash_verified_effectively_approved_media(self):
        unsafe = {
            "asset_id": "UNSAFE", "approval_status": "approved",
            "public_use_approved": True, "content_sha256": "",
            "content_hash_provenance": "",
        }
        safe = {
            "asset_id": "SAFE", "title": "Approved litter photo",
            "media_type": "image", "effective_approval_status": "approved",
            "effective_public_use_approved": True, "content_sha256": "a" * 64,
            "content_hash_provenance": "server_computed_on_upload",
        }
        result = build_beacon_content_candidate(
            self.evidence([unsafe, safe]), current_facts=self.facts()
        )

        self.assertEqual(result["owner_review_packet"]["media"]["asset_id"], "SAFE")
        self.assertNotIn("UNSAFE", str(result["owner_review_packet"]["media"]))

    def test_rejects_unverified_facts_and_never_converts_legacy_metrics_to_claims(self):
        result = build_beacon_content_candidate(
            self.evidence(),
            current_facts=[{
                "statement": "Ten pigs are available for R1200 in Riversdale",
                "status": "inferred",
            }],
        )
        packet = result["owner_review_packet"]

        self.assertEqual(result["rejected_current_facts"][0]["reason"], "missing_provenance")
        self.assertNotIn("R1200", packet["draft_copy"])
        self.assertNotIn("Riversdale", packet["draft_copy"])
        self.assertNotIn("999999", packet["draft_copy"])
        self.assertFalse(packet["fact_constraints"]["stock_claimed"])
        self.assertFalse(packet["fact_constraints"]["performance_result_claimed"])

    def test_fresh_opportunity_can_rank_first_but_does_not_claim_stock(self):
        result = build_beacon_content_candidate(
            self.evidence(opportunity_status="ready_for_owner_review"),
            current_facts=self.facts(),
        )

        self.assertEqual(
            result["ranked_ideas"][0]["idea_id"], "current_livestock_opportunity"
        )
        self.assertFalse(
            result["owner_review_packet"]["fact_constraints"]["availability_claimed"]
        )


if __name__ == "__main__":
    unittest.main()
