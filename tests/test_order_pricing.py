import unittest
from unittest.mock import patch

from modules.orders import order_pricing


class OrderPricingTests(unittest.TestCase):
    def test_missing_prices_resolve_from_actual_line_classification(self):
        detail = {
            "order": {"order_id": "ORD-1"},
            "lines": [
                {
                    "order_line_id": "OL-1",
                    "pig_id": "PIG-1",
                    "tag_number": "87",
                    "sale_category": "Weaner Piglets",
                    "weight_band": "15_to_19_Kg",
                    "sex": "Female",
                    "unit_price": 0,
                    "line_status": "Reserved",
                },
                {
                    "order_line_id": "OL-2",
                    "pig_id": "PIG-2",
                    "tag_number": "69",
                    "sale_category": "Grower Pigs",
                    "weight_band": "20_to_24_Kg",
                    "sex": "Male",
                    "unit_price": 0,
                    "line_status": "Reserved",
                },
            ],
        }

        def resolver(_category, band, _sex):
            return {
                "found": True,
                "status": "ok",
                "unit_price": 600 if band == "15_to_19_Kg" else 800,
                "pricing_id": f"PRICE-{band}",
                "source": "supabase",
            }

        with patch.object(order_pricing, "get_order_detail", return_value=detail), \
             patch.object(order_pricing.order_supabase_write, "update_order_line_fields", return_value=1) as update:
            result = order_pricing.ensure_order_line_prices("ORD-1", price_resolver=resolver)

        self.assertTrue(result["success"])
        self.assertEqual(result["updated_count"], 2)
        self.assertEqual(result["estimated_total"], 1400)
        self.assertEqual(update.call_count, 2)

    def test_existing_price_is_frozen_unless_reprice_is_explicit(self):
        detail = {
            "order": {"order_id": "ORD-1"},
            "lines": [{
                "order_line_id": "OL-1",
                "pig_id": "PIG-1",
                "unit_price": 700,
                "line_status": "Draft",
            }],
        }
        resolver = unittest.mock.Mock(return_value={"found": True, "unit_price": 800})

        with patch.object(order_pricing, "get_order_detail", return_value=detail), \
             patch.object(order_pricing.order_supabase_write, "update_order_line_fields") as update:
            result = order_pricing.ensure_order_line_prices("ORD-1", price_resolver=resolver)

        self.assertTrue(result["success"])
        self.assertEqual(result["unchanged_count"], 1)
        resolver.assert_not_called()
        update.assert_not_called()

    def test_unresolved_price_reports_exact_line(self):
        detail = {
            "order": {"order_id": "ORD-1"},
            "lines": [{
                "order_line_id": "OL-1",
                "pig_id": "PIG-1",
                "tag_number": "99",
                "sale_category": "Unknown",
                "weight_band": "unknown",
                "sex": "Female",
                "unit_price": 0,
                "line_status": "Reserved",
            }],
        }

        with patch.object(order_pricing, "get_order_detail", return_value=detail):
            result = order_pricing.ensure_order_line_prices(
                "ORD-1",
                price_resolver=lambda *_args: {"found": False, "status": "pricing_not_found"},
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["unresolved"][0]["tag_number"], "99")
        self.assertEqual(result["unresolved"][0]["reason"], "pricing_not_found")
