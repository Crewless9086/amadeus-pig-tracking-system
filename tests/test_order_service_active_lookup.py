import unittest
from unittest.mock import patch

from modules.orders import order_read


def order_summary(order_id, status="Draft", conversation_id="1774", phone="+27 82 000 0000", date="2026-05-10"):
    return {
        "order_id": order_id,
        "order_date": date,
        "customer_name": "Charl N",
        "order_status": status,
        "approval_status": "Pending",
        "payment_status": "Pending",
        "requested_category": "Grower",
        "requested_weight_range": "40_to_44_Kg",
        "requested_sex": "Any",
        "requested_quantity": 1,
        "active_line_count": 1,
        "active_line_total": 1500,
        "reserved_pig_count": 0,
        "collection_location": "Riversdale",
        "payment_method": "Cash",
        "conversation_id": conversation_id,
        "customer_phone": phone,
    }


def order_detail(order_id="ORD-1", status="Draft"):
    return {
        "order": {
            "order_id": order_id,
            "order_date": "2026-05-10",
            "order_status": status,
            "approval_status": "Pending",
            "payment_status": "Pending",
            "requested_category": "Grower",
            "requested_weight_range": "40_to_44_Kg",
            "requested_sex": "Any",
            "requested_quantity": 2,
            "active_line_count": 2,
            "active_line_total": 3000,
            "cancelled_line_count": 1,
            "collection_location": "Riversdale",
            "payment_method": "Cash",
            "collection_date": "",
            "reserved_pig_count": 0,
            "notes": "Operator note",
        },
        "lines": [
            {
                "order_line_id": "OL-1",
                "sale_category": "Grower Pigs",
                "weight_band": "40_to_44_Kg",
                "sex": "Male",
                "line_status": "Draft",
                "reserved_status": "Not_Reserved",
                "unit_price": 1500,
            },
            {
                "order_line_id": "OL-2",
                "sale_category": "Grower Pigs",
                "weight_band": "40_to_44_Kg",
                "sex": "Male",
                "line_status": "Draft",
                "reserved_status": "Not_Reserved",
                "unit_price": 1500,
            },
            {
                "order_line_id": "OL-3",
                "sale_category": "Grower Pigs",
                "weight_band": "40_to_44_Kg",
                "sex": "Female",
                "line_status": "Cancelled",
                "reserved_status": "Not_Reserved",
                "unit_price": 1500,
            },
        ],
    }


class ActiveCustomerLookupTests(unittest.TestCase):
    def test_lookup_requires_at_least_one_identifier(self):
        with self.assertRaisesRegex(ValueError, "Provide order_id"):
            order_read.get_active_customer_order_context()

    def test_exact_order_id_returns_single_active_context(self):
        with patch.object(order_read, "get_order_detail", return_value=order_detail("ORD-1")):
            result = order_read.get_active_customer_order_context(order_id="ORD-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["lookup_status"], "single_match")
        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["order_id"], "ORD-1")
        self.assertEqual(result["matches"], [])
        context = result["order_context"]
        self.assertEqual(context["order"]["order_id"], "ORD-1")
        self.assertEqual(context["cancelled_line_count"], 1)
        self.assertEqual(len(context["line_groups"]), 1)
        self.assertEqual(context["line_groups"][0]["quantity"], 2)
        self.assertEqual(context["line_groups"][0]["total"], 3000)

    def test_exact_order_id_returns_terminal_order_without_context(self):
        with patch.object(order_read, "get_order_detail", return_value=order_detail("ORD-1", status="Completed")):
            result = order_read.get_active_customer_order_context(order_id="ORD-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["lookup_status"], "terminal_order")
        self.assertEqual(result["match_count"], 0)
        self.assertIsNone(result["order_context"])
        self.assertEqual(result["matches"][0]["order_id"], "ORD-1")
        self.assertEqual(result["matches"][0]["order_status"], "Completed")

    def test_exact_order_id_missing_returns_no_match(self):
        with patch.object(order_read, "get_order_detail", return_value=None):
            result = order_read.get_active_customer_order_context(order_id="ORD-MISSING")

        self.assertTrue(result["success"])
        self.assertEqual(result["lookup_status"], "no_match")
        self.assertEqual(result["message"], "No order was found for that order reference.")

    def test_conversation_id_single_match_loads_matching_detail(self):
        records = [
            order_summary("ORD-OLD", status="Completed", conversation_id="1774", date="2026-05-09"),
            order_summary("ORD-1", status="Approved", conversation_id="1774", date="2026-05-10"),
            order_summary("ORD-OTHER", status="Draft", conversation_id="9999", date="2026-05-11"),
        ]

        with patch.object(order_read, "list_orders", return_value=records), \
             patch.object(order_read, "get_order_detail", return_value=order_detail("ORD-1", status="Approved")) as get_detail:
            result = order_read.get_active_customer_order_context(conversation_id="1774")

        self.assertEqual(result["lookup_status"], "single_match")
        self.assertEqual(result["order_id"], "ORD-1")
        get_detail.assert_called_once_with("ORD-1")

    def test_conversation_id_multiple_matches_returns_safe_summaries_only(self):
        records = [
            order_summary("ORD-OLD", status="Draft", conversation_id="1774", date="2026-05-09"),
            order_summary("ORD-NEW", status="Approved", conversation_id="1774", date="2026-05-11"),
        ]

        with patch.object(order_read, "list_orders", return_value=records), \
             patch.object(order_read, "get_order_detail") as get_detail:
            result = order_read.get_active_customer_order_context(conversation_id="1774")

        self.assertEqual(result["lookup_status"], "multiple_matches")
        self.assertEqual(result["match_count"], 2)
        self.assertIsNone(result["order_context"])
        self.assertEqual([match["order_id"] for match in result["matches"]], ["ORD-NEW", "ORD-OLD"])
        get_detail.assert_not_called()

    def test_customer_phone_lookup_normalizes_digits_and_excludes_terminal_orders(self):
        records = [
            order_summary("ORD-COMPLETE", status="Completed", phone="+27 82 111 2222"),
            order_summary("ORD-ACTIVE", status="Draft", phone="082 111 2222"),
        ]

        with patch.object(order_read, "list_orders", return_value=records), \
             patch.object(order_read, "get_order_detail", return_value=order_detail("ORD-ACTIVE")):
            result = order_read.get_active_customer_order_context(customer_phone="082-111-2222")

        self.assertEqual(result["lookup_status"], "single_match")
        self.assertEqual(result["order_id"], "ORD-ACTIVE")

    def test_lookup_returns_no_match_when_only_terminal_records_exist(self):
        records = [
            order_summary("ORD-CANCELLED", status="Cancelled", conversation_id="1774"),
            order_summary("ORD-COMPLETE", status="Completed", conversation_id="1774"),
        ]

        with patch.object(order_read, "list_orders", return_value=records):
            result = order_read.get_active_customer_order_context(conversation_id="1774")

        self.assertEqual(result["lookup_status"], "no_match")
        self.assertEqual(result["match_count"], 0)
        self.assertEqual(result["message"], "No active customer order was found.")


class OperatorOrderLookupTests(unittest.TestCase):
    def test_search_requires_identifier_and_valid_status_scope(self):
        with self.assertRaisesRegex(ValueError, "Provide order_id"):
            order_read.search_orders()

        with self.assertRaisesRegex(ValueError, "status_scope"):
            order_read.search_orders(customer_name="charl", status_scope="invalid")

    def test_search_by_name_returns_compact_multiple_matches_with_document_status(self):
        records = [
            order_summary("ORD-OLD", status="Draft", date="2026-05-09"),
            order_summary("ORD-NEW", status="Approved", date="2026-05-11"),
            order_summary("ORD-CLOSED", status="Completed", date="2026-05-12"),
        ]
        documents = [
            {
                "Document_ID": "DOC-1",
                "Document_Type": "Quote",
                "Document_Ref": "Q-2026-NEW",
                "Document_Status": "Generated",
                "Version": "1",
                "Total": 1500,
            }
        ]

        with patch.object(order_read, "list_orders", return_value=records), \
             patch.object(order_read, "get_order_documents_for_summary", return_value=documents):
            result = order_read.search_orders(customer_name="charl", status_scope="active")

        self.assertTrue(result["success"])
        self.assertEqual(result["lookup_status"], "multiple_matches")
        self.assertEqual(result["match_count"], 2)
        self.assertEqual([match["order_id"] for match in result["matches"]], ["ORD-NEW", "ORD-OLD"])
        self.assertEqual(result["matches"][0]["latest_quote_ref"], "Q-2026-NEW")
        self.assertNotIn("google_drive_url", result["matches"][0])

    def test_search_exact_order_id_reports_terminal_when_outside_active_scope(self):
        with patch.object(order_read, "get_order_detail", return_value=order_detail("ORD-1", status="Completed")), \
             patch.object(order_read, "get_order_documents_for_summary", return_value=[]):
            result = order_read.search_orders(order_id="ORD-1", status_scope="active")

        self.assertEqual(result["lookup_status"], "terminal_order")
        self.assertEqual(result["match_count"], 1)
        self.assertEqual(result["matches"][0]["order_status"], "Completed")

    def test_operator_summary_groups_active_lines_and_hides_drive_urls(self):
        documents = [
            {
                "Document_ID": "DOC-1",
                "Document_Type": "Quote",
                "Document_Ref": "Q-2026-1",
                "Document_Status": "Generated",
                "Payment_Method": "Cash",
                "Version": "1",
                "Total": 3000,
                "Google_Drive_URL": "https://drive.example/secret",
            }
        ]

        with patch.object(order_read, "get_order_detail", return_value=order_detail("ORD-1")), \
             patch.object(order_read, "get_order_documents_for_summary", return_value=documents):
            result = order_read.get_order_operator_summary("ORD-1")

        self.assertTrue(result["success"])
        self.assertEqual(result["order_summary"]["order_id"], "ORD-1")
        self.assertEqual(result["order_summary"]["notes"], "Operator note")
        self.assertEqual(len(result["line_summary"]), 1)
        self.assertEqual(result["line_summary"][0]["quantity"], 2)
        self.assertEqual(result["line_summary"][0]["total"], 3000)
        self.assertEqual(result["document_summary"][0]["document_ref"], "Q-2026-1")
        self.assertNotIn("google_drive_url", result["document_summary"][0])
        self.assertEqual(result["safe_document_actions"][0]["action"], "view_document_record")
        self.assertEqual(result["outstanding_actions"][0]["code"], "send_for_approval_when_ready")

    def test_operator_summary_returns_none_when_order_missing(self):
        with patch.object(order_read, "get_order_detail", return_value=None):
            result = order_read.get_order_operator_summary("ORD-MISSING")

        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
