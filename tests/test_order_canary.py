import unittest
from datetime import datetime
from unittest.mock import Mock

from modules.orders.order_canary import (
    DISPOSABLE_INTEGRATION,
    PRODUCTION_READ_ONLY,
    run_order_persistence_canary,
)


def valid_payload(**overrides):
    payload = {
        "order_date": datetime(2026, 7, 23),
        "customer_name": "Canary Customer",
        "customer_phone": "0820000000",
        "customer_channel": "WhatsApp",
        "customer_language": "English",
        "order_source": "Canary",
        "order_stream": "Livestock",
        "requested_category": "Grower",
        "requested_weight_range": "40_to_44_Kg",
        "requested_sex": "Any",
        "requested_quantity": 1,
        "quoted_total": 1500,
        "collection_location": "Riversdale",
        "payment_method": "Cash",
        "notes": "Safe canary only",
        "created_by": "Tester",
    }
    payload.update(overrides)
    return payload


class OrderCanaryTests(unittest.TestCase):
    def test_production_preview_is_validated_and_never_selects_a_writer(self):
        runner = Mock()

        result = run_order_persistence_canary(
            valid_payload(),
            mode=PRODUCTION_READ_ONLY,
            disposable_persistence_runner=runner,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["no_write"])
        self.assertEqual(result["persistence"], "not_attempted")
        self.assertEqual(result["commercial_action"], "none")
        runner.assert_not_called()

    def test_production_persistence_request_fails_closed_before_runner(self):
        runner = Mock()

        result = run_order_persistence_canary(
            valid_payload(),
            mode=PRODUCTION_READ_ONLY,
            persistence_requested=True,
            disposable_persistence_runner=runner,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["persistence"], "rejected_before_write")
        runner.assert_not_called()

    def test_invalid_preview_stays_non_mutating(self):
        result = run_order_persistence_canary(
            valid_payload(order_stream=""), mode=PRODUCTION_READ_ONLY
        )

        self.assertFalse(result["success"])
        self.assertTrue(result["no_write"])
        self.assertIn("Order_Stream must be Livestock, Meat, or Slaughter.", result["validation_errors"])

    def test_disposable_integration_requires_complete_isolation_evidence(self):
        runner = Mock(return_value={"isolated_database": True, "order_persisted": True})

        result = run_order_persistence_canary(
            valid_payload(),
            mode=DISPOSABLE_INTEGRATION,
            persistence_requested=True,
            disposable_persistence_runner=runner,
        )

        self.assertFalse(result["success"])
        self.assertEqual(result["persistence"], "unverified")
        runner.assert_called_once()

    def test_disposable_integration_accepts_order_and_status_log_proof(self):
        runner = Mock(return_value={
            "isolated_database": True,
            "order_persisted": True,
            "status_log_persisted": True,
            "cleanup_completed": True,
        })

        result = run_order_persistence_canary(
            valid_payload(),
            mode=DISPOSABLE_INTEGRATION,
            persistence_requested=True,
            disposable_persistence_runner=runner,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["persistence"], "verified_in_disposable_database")
        self.assertEqual(result["commercial_action"], "none")


if __name__ == "__main__":
    unittest.main()
