import unittest
from unittest.mock import patch

from flask import Flask

from modules.orders.livestock_quote_preview import build_livestock_quote_preview
from modules.orders.order_routes import orders_bp
from modules.pig_weights.pig_weights_service import _live_stock_sale_eligibility


class LivestockQuotePreviewTests(unittest.TestCase):
    def test_four_lines_remain_distinct_and_never_allocate(self):
        request = [
            {"request_item_key": "f5", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Female", "quantity": 10},
            {"request_item_key": "m5", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 10},
            {"request_item_key": "f15", "category": "Piglet", "weight_range": "15_to_19_Kg", "sex": "Female", "quantity": 1},
            {"request_item_key": "m15", "category": "Piglet", "weight_range": "15_to_19_Kg", "sex": "Male", "quantity": 1},
        ]
        pigs = [self.pig("P1", "143", "Female", 5.4, purpose="Unknown"), self.pig("P2", "123", "Male", 5.6), self.pig("P3", "98", "Male", 16)]
        result = build_livestock_quote_preview(request, pigs, observed_at="2026-08-17T12:00:00Z", evidence_source="test_snapshot")
        self.assertEqual([row["request_item_key"] for row in result["recommendations"]], ["f5", "m5", "f15", "m15"])
        self.assertEqual([row["status"] for row in result["recommendations"]], ["unavailable", "partial", "unavailable", "confirmed"])
        self.assertTrue(result["recommendations"][0]["candidates"][0]["purpose_review_required"])
        self.assertFalse(result["writes_performed"])
        self.assertEqual(result["reservation_state"], "not_reserved")
        self.assertEqual(result["evidence_source"], "test_snapshot")

    def test_withdrawal_is_disclosed_while_live_transfer_remains_unknown(self):
        pig = self.pig("P151", "151", "Male", 5.5, withdrawal_evidence_state="hold", current_withdrawal_end_date="2026-09-08")
        result = build_livestock_quote_preview([{"request_item_key": "m", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 1}], [pig])
        candidate = result["recommendations"][0]["candidates"][0]
        self.assertTrue(candidate["withdrawal_disclosure"]["required"])
        self.assertIn("Live-transfer support is Unknown", candidate["blocking_restrictions"][0])
        self.assertEqual(result["recommendations"][0]["status"], "unavailable")

    def test_shared_live_eligibility_does_not_treat_withdrawal_as_transfer_clearance(self):
        pig = self.pig("P151", "151", "Male", 5.5, withdrawal_evidence_state="hold", medical_status="Withdrawal hold", hold_status="withdrawal")
        eligible = _live_stock_sale_eligibility(pig)
        self.assertFalse(eligible["eligible"])
        self.assertIn("does not prohibit live transfer", eligible["reason"])
        pig["health_status"] = "Quarantine"
        self.assertFalse(_live_stock_sale_eligibility(pig)["eligible"])

    def test_blocked_candidate_does_not_crowd_out_valid_candidate(self):
        blocked = self.pig("P1", "101", "Male", 5.2, purpose="Breeding")
        valid = self.pig("P2", "102", "Male", 5.8)
        result = build_livestock_quote_preview([
            {"request_item_key": "m", "category": "Piglet", "weight_range": "5_to_6_Kg", "sex": "Male", "quantity": 1}
        ], [blocked, valid])
        line = result["recommendations"][0]
        self.assertEqual(line["status"], "confirmed")
        self.assertEqual(line["candidates"][0]["pig_id"], "P2")

    @staticmethod
    def pig(pig_id, tag, sex, weight, purpose="Sale", **extra):
        return {"pig_id": pig_id, "tag_number": tag, "sex": sex, "latest_weight_kg": weight,
                "latest_weight_date": "2026-08-11", "days_since_weight": 6, "average_daily_gain_kg": .2,
                "status": "Active", "on_farm": "Yes", "purpose": purpose, "animal_type": "Piglet",
                "calculated_stage": "Weaner", "wean_date": "2026-08-10", "reserved_status": "Not_Reserved",
                "allocation_evidence_state": "known_unallocated", "allocation_query_status": "known",
                "medical_status": "Clear", "health_status": "Clear", "withdrawal_evidence_state": "cleared", **extra}


class LivestockQuotePreviewRouteTests(unittest.TestCase):
    def setUp(self):
        app = Flask(__name__)
        app.register_blueprint(orders_bp, url_prefix="/api")
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.payload = {"requested_items": [{
            "request_item_key": "m", "category": "Piglet", "weight_range": "5_to_6_Kg",
            "sex": "Male", "quantity": 1, "intent_type": "primary", "status": "active",
        }]}

    def test_auth_guard_runs_before_evidence_read(self):
        denied = ({"success": False}, 403)
        with patch("modules.orders.order_routes.require_owner_read_access", return_value=denied), patch(
            "modules.orders.order_routes.get_pig_allocation_readiness"
        ) as readiness:
            response = self.client.post("/api/orders/livestock-quote-preview", json=self.payload)
        self.assertEqual(response.status_code, 403)
        readiness.assert_not_called()

    def test_failed_canonical_snapshot_fails_closed_without_internal_detail(self):
        with patch("modules.orders.order_routes.require_owner_read_access", return_value=None), patch(
            "modules.orders.order_routes.get_pig_allocation_readiness",
            return_value={"success": False, "status": "private-provider-detail", "pigs": []},
        ):
            response = self.client.post("/api/orders/livestock-quote-preview", json=self.payload)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json()["errors"], ["Preview evidence is currently unavailable."])
        self.assertFalse(response.get_json()["writes_performed"])

    def test_successful_route_is_explicitly_zero_write(self):
        with patch("modules.orders.order_routes.require_owner_read_access", return_value=None), patch(
            "modules.orders.order_routes.get_pig_allocation_readiness",
            return_value={"success": True, "generated_date": "2026-08-17", "pigs": []},
        ):
            response = self.client.post("/api/orders/livestock-quote-preview", json=self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["writes_performed"])


if __name__ == "__main__": unittest.main()
