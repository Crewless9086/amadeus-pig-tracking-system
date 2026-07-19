import unittest
from unittest.mock import patch

from modules.charlie.domain_observer_readers import (
    observer_readers, read_beacon_opportunities, read_herdmaster_readiness,
    read_ledger_cash_exceptions, read_sam_lead_health,
)


class DomainObserverReaderTests(unittest.TestCase):
    def test_all_observers_have_real_read_adapters(self):
        self.assertEqual(set(observer_readers()), {"sam_lead_health", "ledger_cash_exceptions", "herdmaster_readiness", "beacon_opportunities"})

    @patch("modules.charlie.domain_observer_readers.live_stock_learning_scorecard")
    def test_sam_adapter_uses_learning_truth(self, scorecard):
        scorecard.return_value = ({"scorecard": {"total_events": 8, "owner_edit_events": 2}}, 200)
        result = read_sam_lead_health()
        self.assertEqual(result["facts"][0]["owner_edits"], 2)
        self.assertEqual(result["source_refs"], ["sam_live_stock_learning"])

    @patch("modules.charlie.domain_observer_readers.list_orders")
    def test_ledger_adapter_reports_payment_exceptions_and_known_gap(self, orders):
        orders.return_value = [{"payment_status": "Pending"}, {"payment_status": "Paid"}]
        result = read_ledger_cash_exceptions()
        self.assertEqual(result["facts"][0]["payment_exceptions"], 1)
        self.assertIn("dedicated_cross_order_cash_reconciliation_source_not_available", result["gaps"])

    @patch("modules.charlie.domain_observer_readers.get_sales_availability")
    def test_herdmaster_adapter_uses_availability_truth(self, availability):
        availability.return_value = [{"Readiness": "Ready"}, {"Readiness": "Not ready"}]
        result = read_herdmaster_readiness()
        self.assertEqual(result["facts"][0]["sale_ready"], 1)
        self.assertEqual(result["source_refs"], ["supabase_pig_sales_availability"])

    @patch("modules.charlie.domain_observer_readers.beacon_workforce_scorecard")
    def test_beacon_adapter_uses_workforce_evidence(self, scorecard):
        scorecard.return_value = {"success": True, "scorecard": {"progress_percent": 50, "media_review_backlog": 3}}
        result = read_beacon_opportunities()
        self.assertEqual(result["facts"][0]["review_backlog"], 3)
        self.assertEqual(result["source_refs"], ["beacon_marketing_evidence"])


if __name__ == "__main__":
    unittest.main()
