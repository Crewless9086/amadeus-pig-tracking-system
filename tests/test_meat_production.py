import os
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.sales.meat_production import (
    calculate_batch_metrics,
    create_meat_processing_batch,
    record_meat_processing_cost,
    record_meat_processing_event,
    record_meat_processing_output,
)


ROOT = Path(__file__).resolve().parents[1]


class MeatProductionTests(unittest.TestCase):
    def test_first_pilot_dressing_yield_and_cost(self):
        metrics = calculate_batch_metrics(
            [{"live_weight_kg": 63.0, "carcass_weight_kg": 46.8}],
            [{"cost_type": "Abattoir", "amount": 250}],
            [],
        )

        self.assertEqual(metrics["live_weight_kg"], 63.0)
        self.assertEqual(metrics["carcass_weight_kg"], 46.8)
        self.assertEqual(metrics["dressing_yield_pct"], 74.3)
        self.assertEqual(metrics["total_cost"], 250.0)
        self.assertEqual(metrics["cost_per_carcass_kg"], 5.34)
        self.assertIsNone(metrics["cost_per_packed_kg"])
        self.assertIsNone(metrics["packed_yield_live_pct"])
        self.assertIsNone(metrics["packed_yield_carcass_pct"])
        self.assertEqual(metrics["revenue"], 0.0)

    def test_outputs_calculate_packed_yield_and_exclude_waste(self):
        metrics = calculate_batch_metrics(
            [{"live_weight_kg": 63.0, "carcass_weight_kg": 46.8}],
            [
                {"cost_type": "Abattoir", "amount": 250},
                {"cost_type": "Butchery", "amount": 500},
            ],
            [
                {"weight_kg": 30.0, "counts_toward_packed_yield": True},
                {"weight_kg": 4.0, "counts_toward_packed_yield": False},
            ],
        )

        self.assertEqual(metrics["packed_weight_kg"], 30.0)
        self.assertEqual(metrics["total_output_weight_kg"], 34.0)
        self.assertEqual(metrics["packed_yield_live_pct"], 47.6)
        self.assertEqual(metrics["packed_yield_carcass_pct"], 64.1)
        self.assertEqual(metrics["cost_per_packed_kg"], 25.0)
        self.assertEqual(metrics["cost_breakdown"], {"Abattoir": 250.0, "Butchery": 500.0})

    def test_batch_create_validates_before_database(self):
        result, status_code = create_meat_processing_batch({"batch_code": "PILOT"}, database_url="unused")
        self.assertEqual(status_code, 400)
        self.assertEqual(result["status"], "batch_code_created_by_and_pigs_required")
        self.assertFalse(result["creates_sale"])
        self.assertFalse(result["changes_pig_lifecycle"])

    def test_event_cost_and_output_validate_before_database(self):
        event, event_code = record_meat_processing_event("B1", {"event_type": "wrong"}, database_url="unused")
        cost, cost_code = record_meat_processing_cost("B1", {"cost_type": "wrong"}, database_url="unused")
        output, output_code = record_meat_processing_output("B1", {"output_type": "Cut"}, database_url="unused")
        self.assertEqual((event_code, cost_code, output_code), (400, 400, 400))
        self.assertFalse(event["sends_customer_message"])
        self.assertFalse(cost["records_revenue"])
        self.assertFalse(output["reserves_stock"])

    def test_missing_database_url_fails_closed(self):
        payload = {
            "batch_code": "MEAT-PILOT-TEST",
            "created_by": "Tester",
            "pigs": [{"pig_id": "PIG-1"}],
        }
        with patch.dict(os.environ, {}, clear=True):
            result, status_code = create_meat_processing_batch(payload)
        self.assertEqual(status_code, 503)
        self.assertEqual(result["status"], "not_configured")

    def test_migration_is_internal_production_not_sales_revenue(self):
        migration = (ROOT / "supabase" / "migrations" / "202607130001_create_meat_processing_batches.sql").read_text(encoding="utf-8")
        for table in (
            "meat_processing_batches",
            "meat_processing_batch_pigs",
            "meat_processing_batch_events",
            "meat_processing_batch_costs",
            "meat_processing_batch_outputs",
        ):
            self.assertIn(f"public.{table}", migration)
        self.assertIn("enable row level security", migration)
        self.assertNotIn("insert into public.sales_transactions", migration)

    def test_owner_page_and_api_routes_are_registered(self):
        app_source = (ROOT / "app.py").read_text(encoding="utf-8")
        route_source = (ROOT / "modules" / "sales" / "sales_transaction_routes.py").read_text(encoding="utf-8")
        self.assertIn('@app.route("/sales/meat-production")', app_source)
        self.assertIn('require_owner_page_access()', app_source)
        self.assertIn('"/sales/meat-production/batches"', route_source)
        self.assertIn("require_owner_admin_access()", route_source)

    def test_owner_batch_capture_routes_use_the_page_owner_session(self):
        route_source = (ROOT / "modules" / "sales" / "sales_transaction_routes.py").read_text(encoding="utf-8")
        route_block = route_source[
            route_source.index('@sales_bp.route("/sales/meat-production/batches"'):
            route_source.index("@sales_bp.route('/sales/beacon/opportunities'")
        ]

        self.assertEqual(route_block.count("require_owner_admin_access()"), 4)
        self.assertIn("require_owner_read_access", route_block)


if __name__ == "__main__":
    unittest.main()
