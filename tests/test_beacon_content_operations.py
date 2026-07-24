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
            "claim_types": ["husbandry_observation"],
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
            "created_at": "2026-07-24T08:00:00Z",
        }
        result = build_beacon_content_candidate(
            self.evidence([unsafe, safe]), current_facts=[]
        )

        self.assertEqual(result["owner_review_packet"]["media"]["asset_id"], "SAFE")
        self.assertNotIn("UNSAFE", str(result["owner_review_packet"]["media"]))
        self.assertIn(
            "approved farm image", result["owner_review_packet"]["draft_copy"]
        )
        self.assertEqual(
            result["owner_review_packet"]["supporting_evidence"][-1]["source_reference"],
            "SAFE",
        )

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

    def test_non_empty_but_unverified_metric_evidence_is_not_usable(self):
        evidence = self.evidence()
        evidence["performance_events"]["records"] = [{
            "performance_event_id": "PERF-INFERRED",
            "metric_evidence": {
                "reach": {
                    "value": 1234,
                    "status": "inferred",
                    "source": "meta_insights",
                    "source_reference": "post/1",
                    "retrieved_at": "2026-07-24T08:00:00Z",
                }
            },
            "source_reference": "event-level-reference",
            "retrieved_at": "2026-07-24T08:00:00Z",
        }]

        result = build_beacon_content_candidate(evidence, current_facts=self.facts())

        self.assertEqual(result["evidence_quality"]["verified_performance_event_count"], 0)
        evaluation = result["evidence_quality"]["performance_evidence_evaluations"][0]
        self.assertFalse(evaluation["usable"])
        self.assertIn("reach:status_unaccepted", evaluation["reasons"])

    def test_partially_verified_metric_event_is_not_usable_for_ranking(self):
        evidence = self.evidence()
        evidence["performance_events"]["records"] = [{
            "performance_event_id": "PERF-PARTIAL",
            "metric_evidence": {
                "reach": {
                    "value": 500,
                    "status": "verified",
                    "source": "meta_insights",
                    "source_reference": "post/2/reach",
                    "retrieved_at": "2026-07-24T08:00:00Z",
                },
                "qualified_buyer_leads": {
                    "value": 4,
                    "status": "verified",
                    "source": "",
                    "source_reference": "",
                    "retrieved_at": "not-a-date",
                },
            },
        }]

        result = build_beacon_content_candidate(evidence, current_facts=self.facts())

        evaluation = result["evidence_quality"]["performance_evidence_evaluations"][0]
        self.assertFalse(evaluation["usable"])
        self.assertEqual(evaluation["usable_metric_names"], [])
        self.assertIn("qualified_buyer_leads:source_unaccepted", evaluation["reasons"])
        self.assertIn("qualified_buyer_leads:retrieved_at_invalid", evaluation["reasons"])

    def test_invalid_observed_at_rejects_otherwise_verified_fact(self):
        fact = self.facts()[0]
        fact["observed_at"] = "today-ish"

        result = build_beacon_content_candidate(self.evidence(), current_facts=[fact])

        self.assertEqual(result["rejected_current_facts"][0]["reason"], "invalid_observed_at")
        self.assertNotIn("settled litter", result["owner_review_packet"]["draft_copy"])

    def test_verified_commercial_fact_sets_structured_claim_constraints(self):
        fact = {
            "fact_id": "OFFER-1",
            "statement": "Verified growers are available in Riversdale at R1 200 each",
            "source": "canonical_sales_offer",
            "source_reference": "offer/OFFER-1",
            "observed_at": "2026-07-24T08:00:00Z",
            "status": "canonical_read",
            "claim_types": ["stock", "availability", "location", "price"],
        }

        result = build_beacon_content_candidate(self.evidence(), current_facts=[fact])
        packet = result["owner_review_packet"]
        constraints = packet["fact_constraints"]

        self.assertIn("R1 200", packet["draft_copy"])
        self.assertIn("Riversdale", packet["draft_copy"])
        for claim_type in ("stock", "availability", "location", "price"):
            self.assertTrue(constraints[f"{claim_type}_claimed"])
            self.assertEqual(
                constraints["claim_provenance"][claim_type][0]["fact_id"], "OFFER-1"
            )

    def test_final_copy_and_fact_constraints_are_consistent(self):
        result = build_beacon_content_candidate(
            self.evidence(), current_facts=self.facts()
        )
        packet = result["owner_review_packet"]

        self.assertIn("settled litter", packet["draft_copy"])
        self.assertEqual(packet["fact_constraints"]["verified_fact_ids_used"], ["LITTER-OBS-1"])
        self.assertFalse(any(
            packet["fact_constraints"][f"{claim_type}_claimed"]
            for claim_type in (
                "stock", "price", "availability", "location",
                "customer_claim", "performance_result",
            )
        ))


if __name__ == "__main__":
    unittest.main()
