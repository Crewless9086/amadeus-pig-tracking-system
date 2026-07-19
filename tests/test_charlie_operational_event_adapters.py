import unittest

from modules.charlie.operational_event_adapters import DOMAIN_DEFAULTS, adapt_source_record, reconcile_source_records


class OperationalEventAdapterTests(unittest.TestCase):
    def test_every_required_domain_has_a_non_destructive_adapter(self):
        for domain, (_aggregate, id_field, _event, _privacy) in DOMAIN_DEFAULTS.items():
            result = adapt_source_record(
                domain,
                {id_field: f"{domain}-1", "updated_at": "2026-07-19T12:00:00+00:00"},
                source_system=f"existing_{domain}",
                observed_at="2026-07-19T12:01:00+00:00",
            )
            self.assertTrue(result["accepted"], domain)
            self.assertEqual(result["event"]["authority_tier"], "observe")
            self.assertTrue(result["event"]["provenance"]["non_destructive"])

    def test_reconciliation_is_stable_and_never_changes_sources(self):
        records = [{"order_id": "ORD-1", "updated_at": "2026-07-19T12:00:00+00:00", "status": "Approved"}]
        first = reconcile_source_records("orders", records, source_system="orders", observed_at="2026-07-19T12:01:00+00:00")
        second = reconcile_source_records("orders", records, source_system="orders", observed_at="2026-07-19T12:01:00+00:00")
        self.assertEqual(first["events"][0]["idempotency_key"], second["events"][0]["idempotency_key"])
        self.assertFalse(first["source_records_changed"])

    def test_missing_source_id_is_quarantined(self):
        result = reconcile_source_records("payments", [{"amount": 10}], source_system="payments")
        self.assertEqual(result["events"], [])
        self.assertEqual(result["rejected"][0]["status"], "source_record_id_required")


if __name__ == "__main__":
    unittest.main()
