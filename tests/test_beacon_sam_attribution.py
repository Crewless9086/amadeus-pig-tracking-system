import unittest

from modules.beacon.sam_attribution import build_beacon_sam_attribution


class BeaconSamAttributionTests(unittest.TestCase):
    def base(self):
        return {
            "campaign_events": [{"performance_event_id": "PERF-1", "campaign_id": "CAM-1", "campaign_source": "social_post", "observed_at": "2026-07-01T10:00:00Z"}],
            "leads": [{"lead_id": "LEAD-1", "campaign_id": "CAM-1", "campaign_source": "social_post", "status": "order_ready_for_approval", "linked_order_id": "ORDER-1", "created_at": "2026-07-02T10:00:00Z"}],
            "orders": [{"order_id": "ORDER-1", "status": "Completed"}],
            "sales_transactions": [{"sale_id": "SALE-1", "linked_order_id": "ORDER-1", "sale_status": "Completed", "net_total": "1234.50", "currency": "ZAR"}],
            "fulfilment_events": [{"fulfillment_event_id": "FUL-1", "lead_id": "LEAD-1", "event_type": "delivered", "occurred_at": "2026-07-10T10:00:00Z"}],
            "loss_events": [],
        }

    def test_exact_attribution_links_qualified_order_revenue_and_fulfilment(self):
        result = build_beacon_sam_attribution(self.base())
        row = result["attributions"][0]
        self.assertTrue(result["success"])
        self.assertEqual(row["method"], "exact_campaign_id")
        self.assertEqual(row["qualification"], "qualified")
        self.assertEqual(row["order_id"], "ORDER-1")
        self.assertEqual(row["revenue"], [{"currency": "ZAR", "net_total": "1234.50"}])
        self.assertEqual(row["fulfilment"], "achieved")
        self.assertFalse(result["authority"]["spends_money"])
        self.assertFalse(result["authority"]["optimizes_campaign"])
        self.assertFalse(result["authority"]["writes_farm_data"])

    def test_source_window_match_is_deterministic_and_expired_is_unmatched(self):
        payload = self.base()
        payload["leads"][0]["campaign_id"] = ""
        matched = build_beacon_sam_attribution(payload)["attributions"][0]
        self.assertEqual(matched["method"], "source_time_window")
        payload["leads"][0]["created_at"] = "2026-09-01T10:00:00Z"
        self.assertEqual(build_beacon_sam_attribution(payload)["attributions"][0]["status"], "unmatched")

    def test_ambiguous_source_window_fails_closed(self):
        payload = self.base()
        payload["leads"][0]["campaign_id"] = ""
        payload["leads"].append({**payload["leads"][0], "lead_id": "LEAD-2"})
        row = build_beacon_sam_attribution(payload)["attributions"][0]
        self.assertEqual(row["status"], "ambiguous")
        self.assertEqual(row["candidate_lead_ids"], ["LEAD-1", "LEAD-2"])
        self.assertEqual(row["revenue"], [])

    def test_duplicate_event_is_idempotent_and_correction_supersedes(self):
        payload = self.base()
        payload["campaign_events"].append(dict(payload["campaign_events"][0]))
        first = build_beacon_sam_attribution(payload)
        self.assertEqual(len(first["attributions"]), 1)
        payload["campaign_events"].append({"performance_event_id": "PERF-2", "supersedes_event_id": "PERF-1", "campaign_id": "CAM-1", "observed_at": "2026-07-01T11:00:00Z"})
        corrected = build_beacon_sam_attribution(payload)
        self.assertEqual([row["performance_event_id"] for row in corrected["attributions"]], ["PERF-2"])

    def test_missing_order_and_non_completed_sale_do_not_report_revenue(self):
        payload = self.base()
        payload["orders"] = []
        row = build_beacon_sam_attribution(payload)["attributions"][0]
        self.assertEqual(row["order_status"], "missing")
        self.assertEqual(row["revenue"], [])
        payload = self.base()
        payload["sales_transactions"][0]["sale_status"] = "Confirmed"
        self.assertEqual(build_beacon_sam_attribution(payload)["attributions"][0]["revenue"], [])

    def test_revenue_keeps_currencies_separate(self):
        payload = self.base()
        payload["sales_transactions"].append({"sale_id": "SALE-2", "linked_order_id": "ORDER-1", "sale_status": "Completed", "net_total": "10", "currency": "USD"})
        row = build_beacon_sam_attribution(payload)["attributions"][0]
        self.assertEqual(row["revenue"], [{"currency": "USD", "net_total": "10.00"}, {"currency": "ZAR", "net_total": "1234.50"}])

    def test_lost_reason_requires_controlled_code_and_failed_fulfilment_is_visible(self):
        payload = self.base()
        payload["leads"][0]["status"] = "not_interested"
        payload["fulfilment_events"][0]["event_type"] = "delivery_failed"
        payload["loss_events"] = [{"event_id": "LOSS-1", "lead_id": "LEAD-1", "reason_code": "free text only", "occurred_at": "2026-07-03T10:00:00Z"}]
        row = build_beacon_sam_attribution(payload)["attributions"][0]
        self.assertEqual(row["qualification"], "lost")
        self.assertEqual(row["lost_reason"]["status"], "unknown")
        self.assertEqual(row["fulfilment"], "failed")
        payload["loss_events"].append({"event_id": "LOSS-2", "lead_id": "LEAD-1", "reason_code": "price", "occurred_at": "2026-07-04T10:00:00Z"})
        self.assertEqual(build_beacon_sam_attribution(payload)["attributions"][0]["lost_reason"], {"code": "price", "status": "recorded"})

    def test_malformed_campaign_evidence_is_reported_not_attributed(self):
        result = build_beacon_sam_attribution({"campaign_events": [{"performance_event_id": "PERF-BAD"}]})
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "malformed_evidence")
        self.assertEqual(result["malformed_evidence_ids"], ["PERF-BAD"])
        self.assertEqual(result["attributions"], [])


if __name__ == "__main__":
    unittest.main()
