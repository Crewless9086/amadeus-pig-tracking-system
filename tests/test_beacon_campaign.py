import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from modules.sales.beacon_campaign import (
    BEACON_CAMPAIGN_MODE,
    BEACON_LIVE_STOCK_AWARENESS_MODE,
    build_beacon_campaign_publish_packet,
    build_beacon_campaign_selection,
    build_beacon_boost_recommendation_packet,
    build_beacon_weekly_command_brief,
    build_beacon_follow_up_suggestions,
    beacon_follow_up_mission,
    build_live_stock_awareness_campaign_packet,
    build_live_stock_awareness_campaign_publish_packet,
    build_live_stock_awareness_campaign_selection,
    build_meat_launch_campaign_packet,
    build_meat_launch_campaign_publish_packet,
    build_meat_launch_campaign_selection,
    execute_beacon_facebook_page_post,
    facebook_posting_policy,
    format_meat_launch_campaign_markdown,
    manual_post_evidence_policy,
    prepare_beacon_owner_decision,
    record_beacon_campaign_performance_event,
    record_beacon_manual_post_evidence,
    validate_meat_launch_campaign_packet,
    _performance_params,
)


class BeaconLiveStockSalesCampaignTests(unittest.TestCase):
    def evidence(self):
        return {
            "campaign_lane": "live_stock_sales", "product_focus": "Grower pigs",
            "opportunity_card": {"lane": "live_stock", "status": "ready_for_owner_review", "blockers": [], "demand_cap": 3,
                "fingerprint": "opportunity-revision-1", "freshness": {"fresh": True}, "timing": {"expires_at": "2026-07-15T00:00:00+00:00"},
                "provenance": {"source_ids": ["PIG-1", "PIG-2", "PIG-3"]}},
            "pricing": {"source": "supabase", "pricing_id": "PRICE-1", "unit_price": 1500, "currency": "ZAR", "effective_from": "2026-07-01"},
        }

    def assets(self):
        return [{"asset_id": "ASSET-1", "effective_approval_status": "approved", "effective_public_use_approved": True,
                 "media_type": "image", "content_sha256": "abc123", "sale_stream_relevance": ["live_stock_sales"], "privacy_risk": "low"}]

    def test_sales_lane_builds_distinct_facebook_and_whatsapp_suggestions(self):
        from modules.sales.beacon_campaign import build_beacon_campaign_selection
        result = build_beacon_campaign_selection(self.evidence(), approved_assets=self.assets())
        self.assertTrue(result["success"])
        self.assertEqual([d["channel"] for d in result["channel_drafts"]], ["Facebook", "WhatsApp"])
        self.assertTrue(result["whatsapp_suggestion_only"])
        self.assertEqual(result["source_truth"]["fulfilment_cap"], 3)
        self.assertEqual(result["source_truth"]["price_source"], "supabase")

    def test_sales_lane_fails_closed_for_stale_zero_cap_or_non_supabase_price(self):
        from modules.sales.beacon_campaign import build_beacon_campaign_selection
        payload = self.evidence()
        payload["opportunity_card"]["freshness"]["fresh"] = False
        payload["opportunity_card"]["demand_cap"] = 0
        payload["pricing"]["source"] = "code_defaults"
        result = build_beacon_campaign_selection(payload, approved_assets=self.assets())
        self.assertFalse(result["success"])
        self.assertIn("sale_eligibility_stale", result["errors"])
        self.assertIn("positive_fulfilment_cap_required", result["errors"])
        self.assertIn("sheet_lineaged_supabase_price_required", result["errors"])
        self.assertEqual(result["channel_drafts"], [])

    def test_exact_packet_binds_copy_media_source_revisions_cap_price_and_attribution(self):
        from modules.sales.beacon_campaign import build_beacon_campaign_publish_packet
        payload = {**self.evidence(), "draft_id": "facebook_live_stock_sales", "asset_id": "ASSET-1", "channel": "Facebook"}
        first = build_beacon_campaign_publish_packet(payload, approved_assets=self.assets())
        second = build_beacon_campaign_publish_packet(payload, approved_assets=self.assets())
        self.assertTrue(first["success"])
        self.assertEqual(first["publish_packet_id"], second["publish_packet_id"])
        binding = first["packet_binding"]
        self.assertEqual(binding["asset_hash"], "abc123")
        self.assertEqual(binding["opportunity_fingerprint"], "opportunity-revision-1")
        self.assertEqual(binding["fulfilment_cap"], 3)
        self.assertEqual(binding["pricing_id"], "PRICE-1")
        self.assertTrue(binding["campaign_attribution_id"].startswith("BEACON-SAM-LIVE-"))

    def test_sales_packet_requires_owner_approved_image(self):
        from modules.sales.beacon_campaign import build_beacon_campaign_publish_packet
        payload = {**self.evidence(), "draft_id": "facebook_live_stock_sales", "asset_id": "REJECTED", "channel": "Facebook"}
        result = build_beacon_campaign_publish_packet(payload, approved_assets=[])
        self.assertFalse(result["success"])
        self.assertIn("owner_approved_sales_image_required", result["errors"])


class BeaconCampaignTests(unittest.TestCase):
    def performance_evidence(self, spend, leads, spend_status="verified", lead_status="verified"):
        return {
            "spend_amount": {"status": spend_status, "value": spend},
            "qualified_buyer_leads": {"status": lead_status, "value": leads},
        }

    def recurring_events(self):
        events = [
            {"performance_event_id": "e2", "publish_packet_id": "p2", "measurement_window": "7 days", "spend_currency": "ZAR", "spend_amount": 100, "qualified_buyer_leads": 0, "created_at": "2026-07-16T08:00:00+00:00"},
            {"performance_event_id": "e1", "publish_packet_id": "p1", "measurement_window": " 7 DAYS ", "spend_currency": "zar", "spend_amount": 50, "qualified_buyer_leads": 0, "created_at": "2026-07-16T07:00:00+00:00"},
        ]
        for event in events:
            event["metric_evidence"] = {
                "spend_amount": {"status": "verified", "value": event["spend_amount"]},
                "qualified_buyer_leads": {"status": "verified", "value": event["qualified_buyer_leads"]},
            }
        return events

    def test_recurring_weakness_suggestion_is_deterministic_complete_and_safe(self):
        now = datetime(2026, 7, 16, 9, tzinfo=timezone.utc)
        first = build_beacon_follow_up_suggestions(self.recurring_events(), now=now)
        second = build_beacon_follow_up_suggestions(list(reversed(self.recurring_events())), now=now)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "recurring_weaknesses_found")
        suggestion = first["suggestions"][0]
        self.assertEqual(suggestion["recurrence_count"], 2)
        self.assertEqual(len(suggestion["evidence_lineage"]), 2)
        self.assertEqual(suggestion["expected_value"]["status"], "estimated")
        self.assertIn("not guaranteed", suggestion["expected_value"]["uncertainty"])
        self.assertIn(suggestion["safety_level"], {"low", "medium", "high"})
        self.assertTrue(suggestion["scope"] and suggestion["non_goals"] and suggestion["proposed_tests"])
        self.assertTrue(all(value is False for value in suggestion["authority"].values()))
        mission = beacon_follow_up_mission(suggestion)
        self.assertEqual(mission["status"], "new")
        self.assertEqual(mission["owner_decision"], "")
        self.assertTrue(mission["metadata"]["owner_approval_required"])

    def test_recurring_weakness_rejects_single_duplicate_stale_superseded_and_incompatible_evidence(self):
        now = datetime(2026, 7, 16, 9, tzinfo=timezone.utc)
        cases = {
            "single": self.recurring_events()[:1],
            "same_campaign": [self.recurring_events()[0], {**self.recurring_events()[1], "publish_packet_id": "p2"}],
            "incompatible_window": [self.recurring_events()[0], {**self.recurring_events()[1], "measurement_window": "24 hours"}],
            "incompatible_currency": [self.recurring_events()[0], {**self.recurring_events()[1], "spend_currency": "USD"}],
            "stale": [{**item, "created_at": "2026-06-01T00:00:00+00:00"} for item in self.recurring_events()],
            "missing_metric": [{**self.recurring_events()[0]}, {key: value for key, value in self.recurring_events()[1].items() if key != "qualified_buyer_leads"}],
            "missing_evidence": [{**self.recurring_events()[0]}, {**self.recurring_events()[1], "metric_evidence": {}}],
            "provider_error": [{**self.recurring_events()[0]}, {**self.recurring_events()[1], "metric_evidence": {
                "spend_amount": {"status": "verified", "value": 50},
                "qualified_buyer_leads": {"status": "provider_error", "value": None},
            }}],
            "incompatible_definition": [{**self.recurring_events()[0]}, {**self.recurring_events()[1], "metric_evidence": {
                "spend_amount": {"status": "verified", "value": 50, "metric_definition": "cents_v1"},
                "qualified_buyer_leads": {"status": "verified", "value": 0},
            }}],
            "mismatched_value": [{**self.recurring_events()[0]}, {**self.recurring_events()[1], "metric_evidence": {
                "spend_amount": {"status": "verified", "value": 999},
                "qualified_buyer_leads": {"status": "verified", "value": 0},
            }}],
            "superseded": [self.recurring_events()[0], {**self.recurring_events()[1], "supersedes_event_id": "e2"}],
        }
        for label, events in cases.items():
            with self.subTest(label=label):
                result = build_beacon_follow_up_suggestions(events, now=now)
                self.assertEqual(result["status"], "insufficient_evidence")
                self.assertEqual(result["suggestions"], [])

    def test_weekly_command_brief_compares_compatible_latest_snapshots_only(self):
        events = [
            {"performance_event_id": "e2", "publish_packet_id": "p2", "channel": "Instagram", "measurement_window": "7 days", "spend_currency": "ZAR", "spend_amount": 0, "qualified_buyer_leads": 3, "metric_evidence": self.performance_evidence(0, 3), "created_at": "2026-07-14T08:00:00+00:00"},
            {"performance_event_id": "e1", "publish_packet_id": "p1", "channel": "Facebook", "measurement_window": " 7   DAYS ", "spend_currency": "ZAR", "spend_amount": 100, "qualified_buyer_leads": 2, "metric_evidence": self.performance_evidence(100, 2), "recommended_action": "light_boost_owner_review", "created_at": "2026-07-14T07:00:00+00:00"},
            {"performance_event_id": "old", "publish_packet_id": "p1", "channel": "Facebook", "measurement_window": "7 days", "spend_currency": "ZAR", "spend_amount": 80, "qualified_buyer_leads": 1, "created_at": "2026-07-13T07:00:00+00:00"},
            {"performance_event_id": "other", "publish_packet_id": "p3", "channel": "Facebook", "measurement_window": "24 hours", "spend_currency": "ZAR", "spend_amount": 20, "qualified_buyer_leads": 1, "created_at": "2026-07-14T06:00:00+00:00"},
        ]
        brief = build_beacon_weekly_command_brief(events, now=datetime(2026, 7, 14, 9, tzinfo=timezone.utc))
        self.assertEqual(brief["comparison"]["status"], "compatible")
        self.assertEqual(len(brief["comparison"]["campaigns"]), 2)
        self.assertEqual(brief["targets"]["spend"]["actual"], 100)
        self.assertEqual(brief["targets"]["qualified_leads"]["actual"], 5)
        self.assertEqual([item["classification"] for item in brief["recommendations"]], ["REUSE", "BOOST"])
        self.assertEqual(brief["targets"]["attributed_revenue"]["status"], "unavailable")

    def test_weekly_command_brief_stale_stop_and_authority_fail_closed(self):
        event = {
            "performance_event_id": "e1", "publish_packet_id": "p1", "measurement_window": "7 days",
            "spend_currency": "ZAR", "spend_amount": 50, "qualified_buyer_leads": 0,
            "metric_evidence": self.performance_evidence(50, 0), "created_at": "2026-07-01T00:00:00+00:00",
        }
        brief = build_beacon_weekly_command_brief([event, dict(event)], now=datetime(2026, 7, 14, tzinfo=timezone.utc))
        self.assertEqual(brief["recommendations"][0]["classification"], "STOP")
        self.assertEqual({alert["code"] for alert in brief["alerts"]}, {"stale_evidence", "stop_recommendation_waiting"})
        self.assertEqual(len(brief["comparison"]["campaigns"]), 1)
        for flag in ("posts_publicly", "sends_customer_message", "calls_meta", "calls_chatwoot", "calls_n8n", "spends_money", "creates_order", "changes_stock", "writes_farm_data", "creates_core_work", "approves_campaign"):
            self.assertFalse(brief["authority"][flag], flag)

    def test_weekly_command_brief_uses_latest_calendar_week_and_explicit_target_truth(self):
        events = [
            {"performance_event_id": "current", "publish_packet_id": "p1", "measurement_window": "7 days", "spend_amount": 25, "qualified_buyer_leads": 1, "created_at": "2026-07-14T08:00:00+00:00"},
            {"performance_event_id": "prior-week", "publish_packet_id": "p2", "measurement_window": "7 days", "spend_amount": 900, "qualified_buyer_leads": 9, "created_at": "2026-07-12T08:00:00+00:00"},
        ]
        targets = {
            "spend": {"status": "owner_approved", "target": 200},
            "qualified_leads": {"status": "blocked", "target": 5, "blocker": "fulfilment_capacity_unavailable"},
        }
        brief = build_beacon_weekly_command_brief(events, weekly_targets=targets, now=datetime(2026, 7, 14, 9, tzinfo=timezone.utc))
        self.assertEqual(brief["targets"]["spend"]["actual"], 25)
        self.assertEqual(brief["targets"]["spend"]["status"], "owner_approved")
        self.assertEqual(brief["targets"]["qualified_leads"]["status"], "blocked")
        self.assertEqual(brief["targets"]["qualified_leads"]["blocker"], "fulfilment_capacity_unavailable")
        self.assertEqual([item["performance_event_id"] for item in brief["recommendations"]], ["current"])

    def test_weekly_targets_never_infer_proposed_status_and_decision_is_prepare_only(self):
        event = {"performance_event_id": "e1", "publish_packet_id": "p1", "measurement_window": "7 days", "spend_amount": 0, "qualified_buyer_leads": 1, "created_at": "2026-07-14T08:00:00+00:00"}
        brief = build_beacon_weekly_command_brief([event], weekly_targets={"spend": {"target": 100}})
        self.assertEqual(brief["targets"]["spend"]["status"], "unavailable")
        packet, status = prepare_beacon_owner_decision(event, "core_work")
        self.assertEqual(status, 200)
        self.assertEqual(packet["status"], "owner_decision_packet_prepared")
        for flag in ("creates_core_work", "approves_campaign", "posts_publicly", "calls_meta", "calls_n8n", "spends_money", "creates_order", "reserves_stock", "writes_farm_data"):
            self.assertFalse(packet[flag], flag)
        unavailable, unavailable_status = prepare_beacon_owner_decision(event, "execute_now")
        self.assertEqual(unavailable_status, 400)
        self.assertEqual(unavailable["status"], "decision_destination_unavailable")

    def test_owner_decision_recomputes_recommendation_from_source_event(self):
        event = {"performance_event_id": "e1", "spend_amount": 75, "qualified_buyer_leads": 0, "metric_evidence": self.performance_evidence(75, 0)}
        event.update({"classification": "BOOST", "reason": "client_tampering", "supporting_metrics": {"spend_amount": 0}})
        packet, status = prepare_beacon_owner_decision(event, "campaign_decision")
        self.assertEqual(status, 200)
        self.assertEqual(packet["classification"], "STOP")
        self.assertEqual(packet["reason"], "paid_spend_without_qualified_leads")
        self.assertEqual(packet["supporting_metrics"]["spend_amount"], 75)

    def test_recommendation_fails_closed_when_metric_evidence_is_unavailable(self):
        event = {
            "performance_event_id": "missing-evidence",
            "spend_amount": 0,
            "qualified_buyer_leads": 0,
            "metric_evidence": self.performance_evidence(None, None, "missing", "provider_error"),
        }
        packet, status = prepare_beacon_owner_decision(event, "campaign_decision")
        self.assertEqual(status, 200)
        self.assertEqual(packet["classification"], "CHANGE")
        self.assertEqual(packet["reason"], "spend_or_qualified_lead_evidence_unavailable")
        self.assertIsNone(packet["supporting_metrics"]["spend_amount"])
        self.assertIsNone(packet["supporting_metrics"]["qualified_buyer_leads"])
        self.assertEqual(packet["supporting_metrics"]["metric_evidence_status"], {"spend_amount": "missing", "qualified_buyer_leads": "provider_error"})

    def test_packet_is_draft_only_and_has_no_external_authority(self):
        packet = build_meat_launch_campaign_packet()

        self.assertTrue(packet["success"])
        self.assertEqual(packet["mode"], BEACON_CAMPAIGN_MODE)
        self.assertEqual(packet["agent"], "Beacon")
        self.assertEqual(packet["next_gate"], "owner_reviews_campaign_before_any_public_or_customer_send")
        self.assertTrue(packet["authority"]["draft_only"])

        for name, value in packet["authority"].items():
            if name == "draft_only":
                continue
            self.assertFalse(value, name)

        self.assertIn("no_public_post", packet["forbidden_actions"])
        self.assertIn("no_customer_dm", packet["forbidden_actions"])
        self.assertIn("no_chatwoot_send", packet["forbidden_actions"])
        self.assertIn("no_order_create", packet["forbidden_actions"])
        self.assertIn("no_stock_reservation", packet["forbidden_actions"])

    def test_channel_drafts_cover_launch_surfaces(self):
        packet = build_meat_launch_campaign_packet()
        drafts = packet["channel_drafts"]
        channels = {draft["channel"] for draft in drafts}

        self.assertIn("WhatsApp status", channels)
        self.assertIn("WhatsApp channel or broadcast draft", channels)
        self.assertIn("Facebook", channels)
        self.assertIn("Instagram", channels)
        self.assertGreaterEqual(len(packet["story_updates"]), 4)
        self.assertGreaterEqual(len(packet["campaign_angles"]), 4)

    def test_every_public_draft_is_limited_preorder_and_safe(self):
        packet = build_meat_launch_campaign_packet()
        validation = validate_meat_launch_campaign_packet(packet)

        self.assertTrue(validation["success"], validation)
        self.assertEqual(validation["missing_preorder_signal"], [])
        self.assertEqual(validation["missing_limited_signal"], [])
        self.assertEqual(validation["unsafe_promise_drafts"], [])
        self.assertGreaterEqual(validation["checked_draft_count"], 10)

    def test_packet_can_be_customized_without_changing_authority(self):
        packet = build_meat_launch_campaign_packet({
            "farm_name": "Amadeus Farm",
            "area": "Riversdale",
            "product_focus": "half carcass Set A",
        })

        self.assertEqual(packet["campaign"]["area"], "Riversdale")
        self.assertIn("half carcass Set A", packet["campaign"]["product_focus"])
        self.assertFalse(packet["authority"]["posts_publicly"])
        self.assertFalse(packet["authority"]["calls_chatwoot"])
        self.assertTrue(packet["validation"]["success"])

    def test_markdown_packet_keeps_authority_boundary_visible(self):
        packet = build_meat_launch_campaign_packet()
        markdown = format_meat_launch_campaign_markdown(packet)

        self.assertIn("# Meat Launch Campaign Packet", markdown)
        self.assertIn("This packet is draft-only.", markdown)
        self.assertIn("## Channel Drafts", markdown)
        self.assertIn("## Authority Boundary", markdown)
        self.assertIn("`posts_publicly`: `false`", markdown)
        self.assertIn("`creates_order`: `false`", markdown)
        self.assertIn("`changes_stock`: `false`", markdown)
        self.assertIn("owner_reviews_campaign_before_any_public_or_customer_send", markdown)

    def test_campaign_selection_pairs_approved_media_without_posting_authority(self):
        selection = build_meat_launch_campaign_selection(approved_assets=[
            {
                "asset_id": "BEACON-ASSET-APPROVED",
                "title": "Set A freezer pack photo",
                "media_type": "image",
                "subject_tags": ["set a", "freezer", "pork"],
                "sale_stream_relevance": ["meat"],
                "quality_score": 85,
                "privacy_risk": "low",
                "effective_approval_status": "approved",
                "effective_public_use_approved": True,
                "storage_bucket": "beacon-raw-intake",
                "storage_path": "2026/06/18/photo.jpg",
            },
            {
                "asset_id": "BEACON-ASSET-PENDING",
                "title": "Unreviewed photo",
                "media_type": "image",
                "effective_approval_status": "needs_review",
            },
        ])

        self.assertTrue(selection["success"])
        self.assertEqual(selection["mode"], "beacon_meat_launch_campaign_media_selection_review_only")
        self.assertEqual(selection["approved_media_count"], 1)
        self.assertEqual(selection["ranked_media_assets"][0]["asset_id"], "BEACON-ASSET-APPROVED")
        self.assertGreaterEqual(len(selection["channel_draft_pairings"]), 6)
        self.assertTrue(selection["channel_draft_pairings"][0]["requires_owner_final_selection"])
        self.assertFalse(selection["authority"]["posts_publicly"])
        self.assertFalse(selection["authority"]["calls_meta"])
        self.assertEqual(selection["next_gate"], "owner_selects_media_and_campaign_draft_before_any_public_post")

    def test_campaign_selection_requires_explicit_lane(self):
        selection = build_beacon_campaign_selection(approved_assets=[])

        self.assertFalse(selection["success"])
        self.assertEqual(selection["status"], "campaign_lane_required")
        self.assertIn("live_stock_awareness", selection["allowed_campaign_lanes"])
        self.assertIn("meat_launch", selection["allowed_campaign_lanes"])

    def test_live_stock_awareness_packet_is_not_meat_sales_copy(self):
        packet = build_live_stock_awareness_campaign_packet({
            "farm_name": "Amadeus Farm",
            "subject_focus": "12 piglets and their mom",
        })

        self.assertTrue(packet["success"], packet)
        self.assertEqual(packet["mode"], BEACON_LIVE_STOCK_AWARENESS_MODE)
        self.assertEqual(packet["campaign_lane"], "live_stock_awareness")
        self.assertTrue(packet["validation"]["success"], packet["validation"])
        all_text = " ".join(draft["text"] for draft in packet["channel_drafts"] + packet["story_updates"]).lower()
        for forbidden in ("available now", "order", "reserve", "price", "limited stock", "dm to buy"):
            self.assertNotIn(forbidden, all_text)
        self.assertIn("new life", all_text)
        self.assertFalse(packet["authority"]["posts_publicly"])
        self.assertFalse(packet["authority"]["creates_order"])

    def test_live_stock_awareness_selection_ranks_piglet_media(self):
        selection = build_live_stock_awareness_campaign_selection({
            "campaign_lane": "live_stock_awareness",
        }, approved_assets=[
            {
                "asset_id": "BEACON-PIGLETS",
                "title": "New litter of piglets",
                "media_type": "image",
                "subject_tags": ["piglets", "litter", "new life"],
                "sale_stream_relevance": ["live_stock_awareness"],
                "quality_score": 86,
                "privacy_risk": "low",
                "effective_approval_status": "approved",
                "effective_public_use_approved": True,
            },
            {
                "asset_id": "BEACON-MEAT",
                "title": "Freezer pork pack",
                "media_type": "image",
                "subject_tags": ["pork", "freezer"],
                "sale_stream_relevance": ["meat"],
                "quality_score": 90,
                "privacy_risk": "low",
                "effective_approval_status": "approved",
                "effective_public_use_approved": True,
            },
        ])

        self.assertTrue(selection["success"], selection)
        self.assertEqual(selection["campaign_lane"], "live_stock_awareness")
        self.assertEqual(selection["ranked_media_assets"][0]["asset_id"], "BEACON-PIGLETS")
        self.assertEqual(selection["mode"], "beacon_live_stock_awareness_campaign_media_selection_review_only")

    def test_live_stock_awareness_publish_packet_blocks_direct_sales_wording(self):
        packet = build_live_stock_awareness_campaign_publish_packet({
            "draft_id": "facebook_awareness_post",
            "channel": "Facebook",
        }, approved_assets=[])

        self.assertTrue(packet["success"], packet)
        self.assertTrue(packet["safety_checks"]["draft_has_no_direct_sales_wording"])
        self.assertEqual(packet["campaign_lane"], "live_stock_awareness")
        self.assertFalse(packet["approval_sends_or_posts"])
        self.assertFalse(packet["authority"]["posts_publicly"])

    def test_live_stock_awareness_packet_binds_ordered_approved_media(self):
        assets = [
            {"asset_id": "PHOTO-1", "media_type": "image", "public_use_approved": True,
             "effective_public_use_approved": True, "effective_approval_status": "approved",
             "sale_stream_relevance": ["live_stock_awareness"]},
            {"asset_id": "VIDEO-1", "media_type": "video", "public_use_approved": True,
             "effective_public_use_approved": True, "effective_approval_status": "approved",
             "sale_stream_relevance": ["live_stock_awareness"]},
        ]
        packet = build_live_stock_awareness_campaign_publish_packet({
            "draft_id": "facebook_awareness_post",
            "asset_ids": ["PHOTO-1", "VIDEO-1"],
            "channel": "Facebook",
        }, approved_assets=assets)

        self.assertTrue(packet["success"], packet)
        self.assertEqual(packet["asset_ids"], ["PHOTO-1", "VIDEO-1"])
        self.assertEqual([item["asset_id"] for item in packet["selected_assets"]], ["PHOTO-1", "VIDEO-1"])
        self.assertTrue(packet["safety_checks"]["assets_are_owner_approved"])

    def test_dispatcher_preserves_meat_launch_when_lane_is_explicit(self):
        selection = build_beacon_campaign_selection({
            "campaign_lane": "meat_launch",
        }, approved_assets=[])
        publish = build_beacon_campaign_publish_packet({
            "campaign_lane": "meat_launch",
            "draft_id": "facebook_post",
        }, approved_assets=[])

        self.assertTrue(selection["success"], selection)
        self.assertEqual(selection["mode"], "beacon_meat_launch_campaign_media_selection_review_only")
        self.assertFalse(publish["success"], publish)
        self.assertIn("meat_public_offer_not_owner_enabled", publish["errors"])
        self.assertIn("meat_pilot_cap_positive_whole_number_required", publish["errors"])
        self.assertIn("selected_image_asset_required", publish["errors"])
        self.assertIn("limited", publish["selected_draft"]["exact_text"].lower())

    @patch.dict("os.environ", {"SAM_MEAT_PUBLIC_OFFER_ENABLED": "1"})
    def test_publish_packet_binds_exact_draft_and_approved_asset_without_posting(self):
        packet = build_meat_launch_campaign_publish_packet({
            "draft_id": "facebook_post",
            "asset_id": "BEACON-ASSET-APPROVED",
            "channel": "Facebook",
            "pilot_cap": "2",
            "owner_notes": "Owner will post manually.",
        }, approved_assets=[
            {
                "asset_id": "BEACON-ASSET-APPROVED",
                "title": "Approved freezer pork image",
                "media_type": "image",
                "subject_tags": ["pork", "freezer"],
                "sale_stream_relevance": ["meat"],
                "quality_score": 90,
                "privacy_risk": "low",
                "effective_approval_status": "approved",
                "effective_public_use_approved": True,
            },
        ])

        self.assertTrue(packet["success"], packet)
        self.assertEqual(packet["mode"], "beacon_campaign_publish_packet_owner_review_only")
        self.assertEqual(packet["selected_draft"]["draft_id"], "facebook_post")
        self.assertIn("limited", packet["selected_draft"]["exact_text"].lower())
        self.assertEqual(packet["selected_asset"]["asset_id"], "BEACON-ASSET-APPROVED")
        self.assertEqual(packet["approval_status"], "owner_review_required")
        self.assertFalse(packet["approval_sends_or_posts"])
        self.assertFalse(packet["authority"]["posts_publicly"])
        self.assertTrue(packet["safety_checks"]["no_public_send_or_post"])
        self.assertEqual(packet["next_gate"], "owner_approves_exact_publish_packet_before_manual_or_gated_public_post")

    def test_publish_packet_rejects_unapproved_asset_selection(self):
        packet = build_meat_launch_campaign_publish_packet({
            "draft_id": "facebook_post",
            "asset_id": "BEACON-ASSET-PENDING",
        }, approved_assets=[])

        self.assertFalse(packet["success"])
        self.assertIn("selected_asset_not_approved_or_not_found", packet["errors"])
        self.assertFalse(packet["authority"]["calls_meta"])

    def test_manual_post_evidence_policy_allows_evidence_not_boost_or_spend(self):
        policy = manual_post_evidence_policy()

        self.assertTrue(policy["success"])
        self.assertEqual(policy["mode"], "beacon_manual_public_post_evidence_only")
        self.assertTrue(policy["records_evidence"])
        self.assertFalse(policy["posts_publicly"])
        self.assertFalse(policy["calls_meta"])
        self.assertFalse(policy["boosts_post"])
        self.assertFalse(policy["spends_money"])
        self.assertEqual(policy["next_gate"], "beacon_performance_tracking_before_boost_recommendation_or_meta_ads_access")

    def test_manual_post_evidence_requires_packet_and_channel_before_db(self):
        missing_packet, missing_packet_status = record_beacon_manual_post_evidence({
            "channel": "Facebook",
        }, database_url="")
        self.assertEqual(missing_packet_status, 400)
        self.assertEqual(missing_packet["status"], "publish_packet_id_required")
        self.assertFalse(missing_packet["calls_meta"])
        self.assertFalse(missing_packet["spends_money"])

        missing_channel, missing_channel_status = record_beacon_manual_post_evidence({
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
        }, database_url="")
        self.assertEqual(missing_channel_status, 400)
        self.assertEqual(missing_channel["status"], "channel_required")

    def test_manual_post_evidence_missing_database_is_safe_unavailable(self):
        result, status = record_beacon_manual_post_evidence({
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "post_url": "https://example.test/post",
            "reactions": "4",
            "messages": "2",
        }, database_url="")

        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["mode"], "beacon_manual_public_post_evidence_only")
        self.assertTrue(result["records_evidence"])
        self.assertFalse(result["posts_publicly"])
        self.assertFalse(result["boosts_post"])
        self.assertFalse(result["spends_money"])

    def test_campaign_performance_recommends_light_boost_without_spend_authority(self):
        packet = build_beacon_boost_recommendation_packet({
            "manual_post_event_id": "BEACON-MANUAL-POST-1",
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "messages_to_sam": 3,
            "qualified_buyer_leads": 1,
            "recommended_spend_amount": 150,
            "recommended_duration_days": 3,
        })

        self.assertEqual(packet["mode"], "beacon_boost_recommendation_owner_review_only")
        self.assertEqual(packet["recommended_action"], "light_boost_owner_review")
        self.assertEqual(packet["recommended_spend_amount"], 150)
        self.assertEqual(packet["max_spend_cap_amount"], 500)
        self.assertTrue(packet["recommends_boost"])
        self.assertFalse(packet["calls_meta"])
        self.assertFalse(packet["boosts_post"])
        self.assertFalse(packet["spends_money"])

        preview, preview_status = record_beacon_campaign_performance_event({
            "manual_post_event_id": "",
            "publish_packet_id": "",
        }, database_url="")
        self.assertEqual(preview_status, 400)
        self.assertEqual(preview["status"], "manual_post_event_id_or_publish_packet_id_required")
        self.assertFalse(preview["calls_meta"])
        self.assertFalse(preview["spends_money"])

    def test_campaign_performance_builds_boost_packet_rules_before_db_when_missing_config(self):
        result, status = record_beacon_campaign_performance_event({
            "manual_post_event_id": "BEACON-MANUAL-POST-1",
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "messages_to_sam": 3,
            "qualified_buyer_leads": 1,
            "recommended_spend_amount": 150,
            "recommended_duration_days": 3,
        }, database_url="")

        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "not_configured")
        self.assertTrue(result["records_evidence"])
        self.assertFalse(result["posts_publicly"])
        self.assertFalse(result["calls_meta"])
        self.assertFalse(result["boosts_post"])
        self.assertFalse(result["spends_money"])

    def test_campaign_performance_caps_requested_boost_and_blocks_high_risk(self):
        high_risk = build_beacon_boost_recommendation_packet({
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "fulfillment_risk": "high",
        })
        self.assertEqual(high_risk["recommended_action"], "do_not_boost")
        self.assertEqual(high_risk["recommended_spend_amount"], 0)
        self.assertFalse(high_risk["spends_money"])

        over_cap = build_beacon_boost_recommendation_packet({
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "messages_to_sam": 5,
            "recommended_spend_amount": 900,
        })
        self.assertEqual(over_cap["recommended_action"], "owner_review_required")
        self.assertEqual(over_cap["recommended_spend_amount"], 500)
        self.assertFalse(over_cap["calls_meta"])

    def test_facebook_posting_policy_is_default_locked(self):
        policy = facebook_posting_policy(environ={})

        self.assertFalse(policy["enabled"])
        self.assertFalse(policy["page_id_configured"])
        self.assertFalse(policy["page_access_token_configured"])
        self.assertEqual(policy["required_owner_confirmation"], "POST EXACT BEACON PACKET")
        self.assertFalse(policy["text_posting_configured"])
        self.assertFalse(policy["media_storage_configured"])
        self.assertFalse(policy["image_posting_configured"])
        self.assertFalse(policy["posts_text_only_now"])
        self.assertFalse(policy["posts_media_now"])
        self.assertFalse(policy["posts_image_now"])
        self.assertFalse(policy["boosts_post"])
        self.assertFalse(policy["spends_money"])

    def test_facebook_posting_policy_reports_readiness_only_when_enabled(self):
        disabled_policy = facebook_posting_policy(environ={
            "BEACON_FACEBOOK_PAGE_ID": "123",
            "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        })

        self.assertFalse(disabled_policy["enabled"])
        self.assertTrue(disabled_policy["text_posting_configured"])
        self.assertTrue(disabled_policy["media_storage_configured"])
        self.assertTrue(disabled_policy["image_posting_configured"])
        self.assertFalse(disabled_policy["posts_text_only_now"])
        self.assertFalse(disabled_policy["posts_media_now"])
        self.assertFalse(disabled_policy["posts_image_now"])

        enabled_policy = facebook_posting_policy(environ={
            "BEACON_FACEBOOK_POSTING_ENABLED": "1",
            "BEACON_FACEBOOK_PAGE_ID": "123",
            "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        })

        self.assertTrue(enabled_policy["posts_text_only_now"])
        self.assertTrue(enabled_policy["posts_media_now"])
        self.assertTrue(enabled_policy["posts_image_now"])

    def test_facebook_post_execution_requires_exact_owner_confirmation(self):
        result, status = execute_beacon_facebook_page_post({
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "exact_text": "Limited preorder test post.",
            "owner_confirmation": "post it",
        }, database_url="", environ={
            "BEACON_FACEBOOK_POSTING_ENABLED": "1",
            "BEACON_FACEBOOK_PAGE_ID": "123",
            "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
        })

        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "owner_confirmation_required")
        self.assertFalse(result["posts_publicly"])
        self.assertFalse(result["calls_meta"])
        self.assertFalse(result["spends_money"])

    def test_facebook_mixed_media_requires_manual_composer_before_meta(self):
        called = []
        assets = [
            {"asset_id": "PHOTO-1", "media_type": "image", "public_use_approved": True,
             "storage_bucket": "beacon-raw-intake", "storage_path": "photo.jpg"},
            {"asset_id": "VIDEO-1", "media_type": "video", "public_use_approved": True,
             "storage_bucket": "beacon-raw-intake", "storage_path": "video.mp4"},
        ]
        result, status = execute_beacon_facebook_page_post({
            "campaign_lane": "live_stock_awareness",
            "publish_packet_id": "PACKET-MIXED",
            "channel": "Facebook",
            "exact_text": "A day with the piglets on the farm.",
            "asset_ids": ["PHOTO-1", "VIDEO-1"],
            "selected_assets": assets,
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }, poster=lambda *_: called.append(True), environ={
            "BEACON_FACEBOOK_POSTING_ENABLED": "1",
            "BEACON_FACEBOOK_PAGE_ID": "page",
            "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        })

        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "facebook_mixed_media_requires_manual_composer")
        self.assertEqual(called, [])

    def test_facebook_post_execution_can_call_mock_poster_when_enabled(self):
        recorded = []

        def fake_recorder(params, database_url=None):
            recorded.append(dict(params))
            return {"success": True, "created_count": 1}, 201

        def fake_poster(params, policy):
            return {"success": True, "facebook_post_id": "123_456", "id": "123_456"}, 200

        result, status = execute_beacon_facebook_page_post({
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "exact_text": "Limited preorder test post.",
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }, database_url="", poster=fake_poster, execution_recorder=fake_recorder, environ={
            "BEACON_FACEBOOK_POSTING_ENABLED": "1",
            "BEACON_FACEBOOK_PAGE_ID": "123",
            "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "facebook_page_post_sent")
        self.assertEqual(result["facebook_post_id"], "123_456")
        self.assertTrue(result["posts_publicly"])
        self.assertTrue(result["calls_meta"])
        self.assertFalse(result["boosts_post"])
        self.assertFalse(result["spends_money"])
        self.assertEqual([event["execution_status"] for event in recorded], ["record_only_before_send", "facebook_page_post_sent"])
        self.assertTrue(recorded[1]["execution_event_id"].endswith("-RESULT"))

    def test_facebook_post_execution_retry_is_blocked_before_meta(self):
        calls = []
        recorded_ids = set()

        def durable_recorder(params, database_url=None):
            event_id = params["execution_event_id"]
            if event_id in recorded_ids:
                return {"success": True, "created_count": 0, "status": "beacon_facebook_post_execution_already_recorded"}, 200
            recorded_ids.add(event_id)
            return {"success": True, "created_count": 1}, 201

        def fake_poster(params, policy):
            calls.append(params)
            return {"success": True, "facebook_post_id": "must-not-send"}, 200

        payload = {
            "publish_packet_id": "BEACON-PUBLISH-PACKET-RETRY",
            "channel": "Facebook",
            "exact_text": "Exact packet retry test.",
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }
        first, first_status = execute_beacon_facebook_page_post(
            {**payload, "execution_event_id": "CALLER-CANNOT-CONTROL-CLAIM"},
            poster=fake_poster, execution_recorder=durable_recorder, environ={
                "BEACON_FACEBOOK_POSTING_ENABLED": "1",
                "BEACON_FACEBOOK_PAGE_ID": "123",
                "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            },
        )
        result, status = execute_beacon_facebook_page_post(
            payload, poster=fake_poster, execution_recorder=durable_recorder, environ={
                "BEACON_FACEBOOK_POSTING_ENABLED": "1",
                "BEACON_FACEBOOK_PAGE_ID": "123",
                "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            },
        )

        self.assertEqual(first_status, 200)
        self.assertEqual(first["facebook_post_id"], "must-not-send")
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "facebook_publish_packet_already_claimed")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("CALLER-CANNOT-CONTROL-CLAIM", recorded_ids)
        self.assertFalse(result["calls_meta"])

    def test_facebook_media_post_execution_rejects_unsupported_media_type(self):
        result, status = execute_beacon_facebook_page_post({
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "exact_text": "Limited preorder image test post.",
            "asset_id": "BEACON-ASSET-1",
            "selected_asset": {
                "asset_id": "BEACON-ASSET-1",
                "media_type": "document",
                "effective_public_use_approved": True,
                "storage_bucket": "beacon-raw-intake",
                "storage_path": "2026/06/18/video.mp4",
            },
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }, database_url="", environ={
            "BEACON_FACEBOOK_POSTING_ENABLED": "1",
            "BEACON_FACEBOOK_PAGE_ID": "123",
            "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        })

        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "selected_media_type_not_supported")
        self.assertFalse(result["posts_publicly"])
        self.assertFalse(result["calls_meta"])

    def test_facebook_image_post_execution_can_call_mock_poster_when_enabled(self):
        def fake_recorder(params, database_url=None):
            return {"success": True, "created_count": 1}, 201

        def fake_poster(params, policy):
            self.assertEqual(params["post_kind"], "photo")
            self.assertEqual(params["asset_id"], "BEACON-ASSET-APPROVED")
            self.assertTrue(policy["posts_media_now"])
            return {
                "success": True,
                "id": "123_photo_456",
                "post_kind": "photo",
                "selected_media": {
                    "asset_id": params["asset_id"],
                    "media_type": "image",
                },
            }, 200

        result, status = execute_beacon_facebook_page_post({
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
            "channel": "Facebook",
            "exact_text": "Limited preorder image test post.",
            "asset_id": "BEACON-ASSET-APPROVED",
            "selected_asset": {
                "asset_id": "BEACON-ASSET-APPROVED",
                "title": "Approved farm image",
                "media_type": "image",
                "mime_type": "image/jpeg",
                "effective_public_use_approved": True,
                "storage_bucket": "beacon-raw-intake",
                "storage_path": "2026/06/18/photo.jpg",
            },
            "owner_confirmation": "POST EXACT BEACON PACKET",
        }, database_url="", poster=fake_poster, execution_recorder=fake_recorder, environ={
            "BEACON_FACEBOOK_POSTING_ENABLED": "1",
            "BEACON_FACEBOOK_PAGE_ID": "123",
            "BEACON_FACEBOOK_PAGE_ACCESS_TOKEN": "token",
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_ROLE_KEY": "service-key",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "facebook_page_post_sent")
        self.assertEqual(result["execution_event"]["post_kind"], "photo")
        self.assertEqual(result["execution_event"]["selected_media"]["asset_id"], "BEACON-ASSET-APPROVED")
        self.assertTrue(result["posts_publicly"])
        self.assertTrue(result["calls_meta"])
        self.assertFalse(result["spends_money"])


class BeaconMetricEvidenceTests(unittest.TestCase):
    def test_snapshot_identity_is_deterministic_and_changes_with_provider_values(self):
        base = {"manual_post_event_id": "M1", "source_reference": "POST1", "reactions": 0}
        first = _performance_params({**base, "retrieved_at": "2026-07-16T08:00:00Z"})
        retry = _performance_params({**base, "retrieved_at": "2026-07-16T09:00:00Z"})
        changed = _performance_params({**base, "reactions": 1, "retrieved_at": "2026-07-16T09:00:00Z"})
        self.assertEqual(first["performance_event_id"], retry["performance_event_id"])
        self.assertNotEqual(first["performance_event_id"], changed["performance_event_id"])

    def test_unavailable_metrics_do_not_create_cost_or_positive_recommendation(self):
        params = _performance_params({"manual_post_event_id": "M1", "spend_amount": 100})
        evidence = __import__("json").loads(params["metric_evidence_json"])
        self.assertEqual(evidence["qualified_buyer_leads"]["status"], "missing")
        self.assertIsNone(evidence["qualified_buyer_leads"]["value"])
        self.assertIsNone(params["cost_per_qualified_lead"])
        self.assertNotEqual(params["recommended_action"], "light_boost_owner_review")

    def test_owner_correction_has_explicit_lineage_and_new_identity(self):
        original = _performance_params({"manual_post_event_id": "M1", "source_reference": "POST1"})
        correction = _performance_params({"manual_post_event_id": "M1", "source_reference": "CRM-7", "supersedes_event_id": original["performance_event_id"], "metric_evidence": {"qualified_buyer_leads": {"status": "owner_correction", "value": 2}}})
        self.assertEqual(correction["supersedes_event_id"], original["performance_event_id"])
        self.assertNotEqual(correction["performance_event_id"], original["performance_event_id"])

    def test_invalid_owner_correction_fails_closed(self):
        for value in (-1, "not-a-number"):
            with self.subTest(value=value):
                params = _performance_params({
                    "manual_post_event_id": "M1",
                    "metric_evidence": {
                        "qualified_buyer_leads": {
                            "status": "owner_correction",
                            "value": value,
                        }
                    },
                })
                evidence = __import__("json").loads(params["metric_evidence_json"])
                self.assertEqual(evidence["qualified_buyer_leads"]["status"], "malformed")
                self.assertIsNone(evidence["qualified_buyer_leads"]["value"])
                self.assertEqual(params["recommended_action"], "wait_for_more_data")


if __name__ == "__main__":
    unittest.main()
