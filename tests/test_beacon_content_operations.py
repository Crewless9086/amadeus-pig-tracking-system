import unittest

from modules.beacon.content_operations import build_beacon_content_candidate


class BeaconContentOperationsTests(unittest.TestCase):
    def test_featured_weekly_packet_uses_only_exact_eligible_media(self):
        assets = []
        specs = (
            ("BEACON-ASSET-3D9A65053184D8181A", 4873496, "2026-07-24T17:29:01.555089+00:00"),
            ("BEACON-ASSET-983952CB4A95A0BEBB", 5493225, "2026-07-24T17:28:53.392664+00:00"),
            ("BEACON-ASSET-13F7A5168AE3BFF676", 3453322, "2026-07-24T17:28:43.815487+00:00"),
        )
        for asset_id, file_size_bytes, created_at in specs:
            assets.append({
                "asset_id": asset_id,
                "media_type": "image",
                "mime_type": "image/jpeg",
                "file_size_bytes": file_size_bytes,
                "created_at": created_at,
                "effective_approval_status": "approved",
                "effective_public_use_approved": True,
                "content_hash_provenance": "server_computed_on_upload",
                "content_sha256": "b" * 64,
            })
        result = build_beacon_content_candidate({
            "media_assets": {"records": assets},
        })
        packet = result["featured_owner_review_packet"]
        self.assertEqual(packet["packet_id"], "BEACON-WEEK-2026-07-25-P1-S1")
        self.assertEqual(len(packet["media"]["assets"]), 3)
        self.assertFalse(packet["authority"]["publish"])
        self.assertFalse(packet["authority"]["Meta_call"])
        history = result["historical_owner_review_packets"]
        self.assertEqual(history[0]["packet_id"], "BEACON-WEEK-2026-07-25-P1")
        self.assertFalse(history[0]["current_reviewable"])
        learning = result["organic_media_learning"]
        self.assertEqual(
            learning["publication"]["facebook_post_id"],
            "920598737794159_122145593991122163",
        )
        self.assertFalse(
            learning["graduation"]["eligible_for_owner_review_candidate"]
        )
        self.assertEqual(
            learning["media_understanding"]["status"],
            "media_understanding_unavailable",
        )
        self.assertFalse(learning["authority"]["publish"])

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
            "adapter_id": "farm_observation_v1",
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
        self.assertIn("patient daily care", packet["draft_copy"])
        self.assertEqual(packet["channel"], "Facebook Page")
        self.assertIn("farm-awareness", packet["measurable_objective"]["metric"])
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
        self.assertIn("patient daily care", result["owner_review_packet"]["draft_copy"])
        self.assertEqual(
            result["owner_review_packet"]["supporting_evidence"][-1]["source_reference"],
            "SAFE",
        )

    def test_prefers_approved_piglet_video_and_prepares_three_natural_options(self):
        image = {
            "asset_id": "IMAGE", "title": "Waki piglets", "media_type": "image",
            "effective_approval_status": "approved",
            "effective_public_use_approved": True, "content_sha256": "a" * 64,
            "content_hash_provenance": "server_computed_on_upload",
        }
        video = {
            **image, "asset_id": "VIDEO", "title": "Waki (12) Piglets Vid",
            "media_type": "video", "content_sha256": "b" * 64,
        }

        result = build_beacon_content_candidate(
            self.evidence([image, video]), current_facts=[]
        )
        packet = result["owner_review_packet"]

        self.assertEqual(packet["media"]["asset_id"], "VIDEO")
        self.assertEqual(
            [option["style"] for option in packet["draft_options"]],
            ["warm_farm_story", "responsible_piglet_care", "short_non_commercial_engagement"],
        )
        for option in packet["draft_options"]:
            copy = option["draft_copy"]
            for phrase in (
                "quantity", "male or female", "when you need them",
            ):
                self.assertNotIn(phrase, copy)
            self.assertNotIn("in stock", copy.lower())
            self.assertNotIn("for sale", copy.lower())

    def test_evidence_summary_distinguishes_missing_metrics_and_media_eligibility(self):
        unsafe = {
            "asset_id": "VISIBLE", "approval_status": "approved",
            "public_use_approved": True, "content_sha256": "",
            "content_hash_provenance": "",
        }
        safe = {
            **unsafe, "asset_id": "ELIGIBLE", "content_sha256": "c" * 64,
            "content_hash_provenance": "server_computed_on_upload",
        }

        result = build_beacon_content_candidate(
            self.evidence([unsafe, safe]), current_facts=[]
        )

        self.assertEqual(
            result["evidence_quality"]["metric_summary"]["spend_amount"]["display"],
            "Not imported",
        )
        self.assertEqual(
            result["evidence_quality"]["metric_summary"]["qualified_buyer_leads"]["verified_zero_event_count"],
            0,
        )
        self.assertEqual(result["media_summary"]["visible_count"], 2)
        self.assertEqual(result["media_summary"]["eligible_selection_count"], 1)
        self.assertIn(
            "cannot claim stock, price or availability",
            result["owner_explanations"]["current_facts"],
        )

    def test_verified_zero_is_distinct_from_missing(self):
        evidence = self.evidence()
        evidence["performance_events"]["records"] = [{
            "performance_event_id": "PERF-ZERO",
            "metric_evidence": {
                "spend_amount": {
                    "value": 0, "status": "verified", "source": "meta_ads_insights",
                    "source_reference": "insights/1", "retrieved_at": "2026-07-24T08:00:00Z",
                }
            },
        }]

        result = build_beacon_content_candidate(evidence, current_facts=[])
        metric = result["evidence_quality"]["metric_summary"]["spend_amount"]

        self.assertEqual(metric["display"], "1 verified")
        self.assertEqual(metric["verified_zero_event_count"], 1)

    def test_explicit_unsupported_outcomes_do_not_invalidate_verified_meta_metrics(self):
        evidence = self.evidence()
        provenance = {
            "source": "meta_ads_insights",
            "source_reference": "insights/ad/1/2026-07-01/2026-07-14",
            "retrieved_at": "2026-07-24T08:00:00Z",
        }
        evidence["performance_events"]["records"] = [{
            "performance_event_id": "PERF-META",
            "metric_evidence": {
                "spend_amount": {
                    **provenance, "value": 0, "status": "verified",
                },
                "reach": {
                    **provenance, "value": 100, "status": "verified",
                },
                "qualified_buyer_leads": {
                    **provenance, "value": None, "status": "unsupported",
                },
                "sales": {
                    **provenance, "value": None, "status": "unsupported",
                },
                "revenue": {
                    **provenance, "value": None, "status": "unsupported",
                },
            },
        }]

        result = build_beacon_content_candidate(evidence, current_facts=[])
        evaluation = result[
            "evidence_quality"
        ]["performance_evidence_evaluations"][0]

        self.assertTrue(evaluation["usable"])
        self.assertEqual(
            evaluation["usable_metric_names"], ["reach", "spend_amount"]
        )
        self.assertEqual(
            result["evidence_quality"]["metric_summary"][
                "qualified_buyer_leads"
            ]["status_counts"],
            {"unsupported": 1},
        )

    def test_compatibility_zero_is_not_ranked_or_aggregated_as_evidence(self):
        evidence = self.evidence()
        provenance = {
            "source": "meta_ads_insights",
            "source_reference": "insights/ad/1/2026-07-01/2026-07-14",
            "retrieved_at": "2026-07-24T08:00:00Z",
        }
        placeholder = {
            "scalar_column": "reactions",
            "stored_value": 0,
            "evidentiary": False,
            "reason": "database_not_null_compatibility_only",
        }
        evidence["performance_events"]["records"] = [{
            "performance_event_id": "PERF-COMPATIBILITY-ZERO",
            "reactions": 0,
            "metric_evidence": {
                "spend_amount": {
                    **provenance, "value": 0, "status": "verified",
                },
                "reach": {
                    **provenance, "value": 100, "status": "verified",
                },
                "impressions": {
                    **provenance, "value": 120, "status": "verified",
                },
                "reactions": {
                    **provenance,
                    "value": None,
                    "status": "missing",
                    "compatibility_placeholder": placeholder,
                },
            },
        }]

        result = build_beacon_content_candidate(evidence, current_facts=[])
        evaluation = result[
            "evidence_quality"
        ]["performance_evidence_evaluations"][0]
        reactions = result[
            "evidence_quality"
        ]["metric_summary"]["reactions"]

        self.assertTrue(evaluation["usable"])
        self.assertNotIn("reactions", evaluation["usable_metric_names"])
        self.assertEqual(reactions["verified_event_count"], 0)
        self.assertEqual(reactions["verified_zero_event_count"], 0)
        self.assertEqual(reactions["display"], "Not verified")
        self.assertEqual(reactions["status_counts"], {"unverified": 1})

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

    def test_fresh_opportunity_cannot_become_public_sales_objective(self):
        result = build_beacon_content_candidate(
            self.evidence(opportunity_status="ready_for_owner_review"),
            current_facts=self.facts(),
        )

        self.assertNotIn(
            "current_livestock_opportunity",
            [idea["idea_id"] for idea in result["ranked_ideas"]],
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
            "statement": "caller text is ignored for commercial claims",
            "source": "canonical_sales_offer",
            "adapter_id": "sales_offer_v1",
            "source_reference": "offer/OFFER-1",
            "observed_at": "2026-07-24T08:00:00Z",
            "status": "canonical_read",
            "claim_types": ["stock", "availability", "location", "price"],
            "structured_values": {
                "subject": "growers",
                "quantity": 3,
                "availability_status": "available_for_owner_review",
                "price_amount": 1200,
                "currency": "ZAR",
                "location": "Riversdale",
            },
        }

        result = build_beacon_content_candidate(self.evidence(), current_facts=[fact])
        packet = result["owner_review_packet"]
        constraints = packet["fact_constraints"]

        self.assertNotIn("ZAR 1,200.00", packet["draft_copy"])
        self.assertNotIn("Riversdale", packet["draft_copy"])
        self.assertNotIn("caller text", packet["draft_copy"])
        for claim_type in ("stock", "availability", "location", "price"):
            self.assertFalse(constraints[f"{claim_type}_claimed"])

    def test_final_copy_and_fact_constraints_are_consistent(self):
        result = build_beacon_content_candidate(
            self.evidence(), current_facts=self.facts()
        )
        packet = result["owner_review_packet"]

        self.assertIn("patient daily care", packet["draft_copy"])
        self.assertEqual(packet["fact_constraints"]["verified_fact_ids_used"], [])
        self.assertFalse(any(
            packet["fact_constraints"][f"{claim_type}_claimed"]
            for claim_type in (
                "stock", "price", "availability", "location",
                "customer_claim", "performance_result",
            )
        ))

    def test_invented_source_is_rejected_even_with_canonical_status(self):
        fact = self.facts()[0]
        fact["source"] = "canonical_totally_invented_source"

        result = build_beacon_content_candidate(self.evidence(), current_facts=[fact])

        self.assertEqual(
            result["rejected_current_facts"][0]["reason"],
            "unaccepted_fact_source_adapter",
        )
        self.assertNotIn("settled litter", result["owner_review_packet"]["draft_copy"])

    def test_price_statement_cannot_hide_as_husbandry_observation(self):
        fact = self.facts()[0]
        fact["statement"] = "Healthy growers cost R1200 each"

        result = build_beacon_content_candidate(self.evidence(), current_facts=[fact])

        self.assertEqual(
            result["rejected_current_facts"][0]["reason"],
            "statement_claim_type_mismatch",
        )
        self.assertNotIn("R1200", result["owner_review_packet"]["draft_copy"])

    def test_source_cannot_supply_unauthorized_claim_type(self):
        fact = self.facts()[0]
        fact["claim_types"] = ["price"]

        result = build_beacon_content_candidate(self.evidence(), current_facts=[fact])

        self.assertEqual(
            result["rejected_current_facts"][0]["reason"],
            "claim_type_not_authorized_for_source",
        )

    def test_authoritative_adapter_with_compatible_claim_is_accepted(self):
        fact = self.facts()[0]

        result = build_beacon_content_candidate(self.evidence(), current_facts=[fact])

        self.assertEqual(result["rejected_current_facts"], [])
        self.assertEqual(
            result["owner_review_packet"]["fact_constraints"]["verified_fact_ids_used"],
            [],
        )


if __name__ == "__main__":
    unittest.main()
