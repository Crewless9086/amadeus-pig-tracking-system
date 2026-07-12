import unittest
from unittest.mock import patch

from app import app
from modules.beacon.marketing_operating_contract import AUTHORITY, build_beacon_marketing_operating_contract, build_fulfilment_target, calculate_kpi


class BeaconMarketingOperatingContractTests(unittest.TestCase):
    def test_contract_is_review_only_and_proposals_are_not_approved(self):
        contract = build_beacon_marketing_operating_contract(now="2026-07-12T12:00:00Z")
        self.assertEqual(contract["approval_status"], "owner_review_required")
        self.assertEqual(contract["brand_kit"]["status"], "proposed_owner_decision_required")
        self.assertEqual(contract["campaign_target"]["status"], "blocked")
        self.assertEqual(contract["campaign_target"]["demand_ceiling"], 0)
        self.assertEqual(contract["authority"], AUTHORITY)
        self.assertTrue(all(value is False for value in contract["authority"].values()))

    def test_fulfilment_target_calculates_conservative_ceiling(self):
        target = build_fulfilment_target({"source_id": "fulfilment-1", "observed_at": "2026-07-12T10:00:00Z", "unit": "halves", "verified_available": 12, "existing_commitments": 3, "operational_reserve": 2, "safety_buffer": 1}, now="2026-07-12T12:00:00Z")
        self.assertEqual(target["status"], "ready_for_owner_review")
        self.assertEqual(target["demand_ceiling"], 6)

    def test_missing_stale_and_zero_capacity_fail_closed(self):
        missing = build_fulfilment_target({}, now="2026-07-12T12:00:00Z")
        stale = build_fulfilment_target({"source_id": "old", "observed_at": "2026-07-10T00:00:00Z", "unit": "pigs", "verified_available": 10, "existing_commitments": 0, "operational_reserve": 0, "safety_buffer": 0}, now="2026-07-12T12:00:00Z")
        zero = build_fulfilment_target({"source_id": "fresh", "observed_at": "2026-07-12T10:00:00Z", "unit": "pigs", "verified_available": 2, "existing_commitments": 1, "operational_reserve": 1, "safety_buffer": 1}, now="2026-07-12T12:00:00Z")
        for target in (missing, stale, zero):
            self.assertEqual(target["status"], "blocked")
            self.assertEqual(target["demand_ceiling"], 0)
        self.assertIn("stale_fulfilment_evidence", stale["errors"])

    def test_non_finite_numeric_evidence_fails_closed(self):
        base = {"source_id": "fresh", "observed_at": "2026-07-12T10:00:00Z", "unit": "pigs", "verified_available": 10, "existing_commitments": 0, "operational_reserve": 0, "safety_buffer": 0}
        for value in ("nan", "inf", "-inf"):
            target = build_fulfilment_target(dict(base, verified_available=value), now="2026-07-12T12:00:00Z")
            self.assertEqual(target["status"], "blocked")
            self.assertEqual(target["demand_ceiling"], 0)
            self.assertIn("invalid_verified_available", target["errors"])

    def test_whitespace_only_source_and_unit_fail_closed(self):
        target = build_fulfilment_target({"source_id": "  ", "observed_at": "2026-07-12T10:00:00Z", "unit": "\t", "verified_available": 10, "existing_commitments": 0, "operational_reserve": 0, "safety_buffer": 0}, now="2026-07-12T12:00:00Z")
        self.assertEqual(target["status"], "blocked")
        self.assertEqual(target["demand_ceiling"], 0)
        self.assertIn("missing_source_id", target["errors"])
        self.assertIn("missing_unit", target["errors"])

    def test_allowlist_unknown_stream_and_kpi_math(self):
        contract = build_beacon_marketing_operating_contract("live_stock")
        self.assertFalse(contract["channel_policy"]["unknown_channels_allowed"])
        self.assertFalse(contract["channel_policy"]["paid_channels_allowed"])
        with self.assertRaisesRegex(ValueError, "unsupported_sale_stream"):
            build_beacon_marketing_operating_contract("tiktok")
        self.assertEqual(calculate_kpi(3, 12), {"status": "calculated", "value": 0.25})
        self.assertEqual(calculate_kpi(3, 0), {"status": "not_available_zero_denominator", "value": None})

    @patch("modules.sales.sales_transaction_routes.require_owner_read_access", return_value=None)
    def test_get_route_is_owner_guarded_and_read_only(self, guard):
        client = app.test_client()
        response = client.get("/api/beacon/marketing-operating-contract?sale_stream=meat")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()["mode"], "beacon_marketing_operating_contract_owner_review_only")
        guard.assert_called_once_with()
        self.assertEqual(client.post("/api/beacon/marketing-operating-contract").status_code, 405)

    @patch("modules.sales.sales_transaction_routes.require_owner_read_access", return_value=({"success": False, "status": "denied"}, 403))
    def test_route_stops_immediately_when_owner_guard_denies(self, guard):
        response = app.test_client().get("/api/beacon/marketing-operating-contract")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "denied")
        guard.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
