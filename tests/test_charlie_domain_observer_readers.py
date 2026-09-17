import unittest
from unittest.mock import patch

from modules.charlie.domain_observer_readers import (
    observer_readers, read_beacon_opportunities, read_herdmaster_readiness,
    read_ledger_cash_exceptions, read_sam_lead_health,
)


class DomainObserverReaderTests(unittest.TestCase):
    def test_all_observers_have_real_read_adapters(self):
        self.assertEqual(set(observer_readers()), {"sam_lead_health", "ledger_cash_exceptions", "herdmaster_readiness", "beacon_opportunities"})

    @patch("modules.charlie.domain_observer_readers.list_sales_conversation_learning_events")
    @patch("modules.charlie.domain_observer_readers.live_stock_learning_scorecard")
    def test_sam_recommendation_uses_actual_conversation_failures(self, scorecard, events):
        scorecard.return_value = ({"scorecard": {
            "total_learning_examples": 30,
            "captured_owner_replies": 10,
            "accepted_or_minor_edit_rate": 0.1,
        }}, 200)
        events.return_value = ({"learning_events": [
            {"sam_misses": ["sam_draft_replaced_by_owner"]},
            {"sam_misses": ["sam_draft_replaced_by_owner"]},
        ]}, 200)

        evidence = read_sam_lead_health()

        self.assertEqual(evidence["facts"][0]["learning_examples"], 30)
        self.assertIn("occurred 2 time(s)", evidence["recommendations"][0]["summary"])
        self.assertIn("only 10%", evidence["recommendations"][1]["summary"])

    @patch("modules.charlie.domain_observer_readers.list_orders")
    def test_ledger_adapter_reports_payment_exceptions_and_known_gap(self, orders):
        orders.return_value = [
            {"payment_status": "Pending", "order_status": "Completed"},
            {"payment_status": "Pending", "order_status": "Cancelled"},
            {"payment_status": "Paid", "order_status": "Completed"},
        ]
        result = read_ledger_cash_exceptions()
        self.assertEqual(result["facts"][0]["payment_exceptions"], 1)
        self.assertEqual(result["facts"][0]["cancelled_payment_exceptions_excluded"], 1)
        self.assertIn("dedicated_cross_order_cash_reconciliation_source_not_available", result["gaps"])

    @patch("modules.charlie.domain_observer_readers.get_sales_metrics")
    def test_herdmaster_adapter_uses_dashboard_metric_truth(self, metrics):
        metrics.return_value = {
            "status": "ok", "live_sale_ready": 51, "meat_window": 6,
            "slaughter_cull_ready": 15,
        }
        result = read_herdmaster_readiness()
        self.assertEqual(result["facts"][0]["live_sale_ready"], 51)
        self.assertEqual(result["facts"][0]["meat_window"], 6)
        self.assertEqual(result["facts"][0]["slaughter_cull_ready"], 15)
        self.assertEqual(result["recommendations"], [])
        self.assertEqual(result["source_refs"], ["supabase_sales_dashboard_metrics"])

    @patch("modules.charlie.domain_observer_readers.beacon_workforce_scorecard")
    def test_beacon_adapter_uses_workforce_evidence(self, scorecard):
        scorecard.return_value = {"success": True, "scorecard": {"progress_percent": 50, "media_review_backlog": 3}}
        result = read_beacon_opportunities()
        self.assertEqual(result["facts"][0]["review_backlog"], 3)
        self.assertEqual(result["source_refs"], ["beacon_marketing_evidence"])


if __name__ == "__main__":
    unittest.main()
