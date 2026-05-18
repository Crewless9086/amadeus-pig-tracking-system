import unittest
from unittest.mock import patch

from app import app
from modules.orders import order_routes


class OrderRoutesTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_create_order_route_validates_payload_and_returns_created(self):
        service_result = {
            "success": True,
            "order_id": "ORD-1",
            "order_status": "Draft",
        }
        payload = {
            "order_date": "2026-05-18",
            "customer_name": "Sam",
            "customer_phone": "0720000000",
            "customer_channel": "Chatwoot",
            "customer_language": "English",
            "order_source": "WhatsApp",
            "requested_category": "Grower",
            "requested_weight_range": "35_to_39_Kg",
            "requested_sex": "Female",
            "requested_quantity": 1,
            "quoted_total": 1500,
            "collection_location": "Riversdale",
            "payment_method": "Cash",
            "notes": "Route smoke",
            "created_by": "Tester",
            "conversation_id": "1774",
        }

        with patch.object(order_routes, "create_order", return_value=service_result) as create:
            response = self.client.post("/api/master/orders", json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        create.assert_called_once()
        cleaned = create.call_args.args[0]
        self.assertEqual(cleaned["customer_name"], "Sam")
        self.assertEqual(cleaned["requested_quantity"], 1.0)
        self.assertEqual(cleaned["created_by"], "Tester")

    def test_create_order_route_returns_400_for_validation_errors(self):
        response = self.client.post("/api/master/orders", json={"customer_name": "Sam"})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("Order_Date is required", payload["errors"][0])

    def test_update_order_route_passes_cleaned_payload_and_attaches_auto_quote(self):
        service_result = {
            "success": True,
            "order_id": "ORD-1",
            "order_status": "Draft",
        }
        payload = {
            "requested_quantity": 2,
            "collection_location": "Albertinia",
            "payment_method": "EFT",
            "changed_by": "Tester",
        }

        with patch.object(order_routes, "update_order", return_value=service_result) as update, \
             patch.object(order_routes, "_attach_auto_quote_result") as attach_quote:
            response = self.client.patch("/api/master/orders/ORD-1", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        update.assert_called_once()
        self.assertEqual(update.call_args.args[0], "ORD-1")
        self.assertEqual(update.call_args.args[1]["requested_quantity"], 2.0)
        self.assertEqual(update.call_args.args[1]["changed_by"], "Tester")
        attach_quote.assert_called_once_with(service_result, "ORD-1", changed_by="Tester")

    def test_update_order_route_returns_400_for_service_guard_failure(self):
        with patch.object(order_routes, "update_order", side_effect=ValueError("Terminal orders cannot be updated.")):
            response = self.client.patch("/api/master/orders/ORD-1", json={"notes": "Updated"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {
            "success": False,
            "errors": ["Terminal orders cannot be updated."],
        })

    def test_create_order_line_route_validates_payload_and_returns_created(self):
        service_result = {
            "success": True,
            "order_line_id": "OL-1",
            "order_id": "ORD-1",
        }
        payload = {
            "order_id": "ORD-1",
            "pig_id": "PIG-1",
            "unit_price": 1500,
            "notes": "Route smoke",
            "request_item_key": "primary_1",
        }

        with patch.object(order_routes, "create_order_line", return_value=service_result) as create_line:
            response = self.client.post("/api/master/order-lines", json=payload)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        create_line.assert_called_once()
        cleaned = create_line.call_args.args[0]
        self.assertEqual(cleaned["order_id"], "ORD-1")
        self.assertEqual(cleaned["pig_id"], "PIG-1")
        self.assertEqual(cleaned["unit_price"], 1500.0)

    def test_create_order_line_route_returns_400_for_validation_errors(self):
        response = self.client.post("/api/master/order-lines", json={"order_id": "ORD-1"})

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("Pig_ID is required.", payload["errors"])

    def test_update_order_line_route_passes_cleaned_payload(self):
        service_result = {
            "success": True,
            "order_line_id": "OL-1",
            "line_status": "Allocated",
        }

        with patch.object(order_routes, "update_order_line", return_value=service_result) as update_line:
            response = self.client.patch(
                "/api/master/order-lines/OL-1",
                json={"unit_price": 1550, "notes": "Updated"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        update_line.assert_called_once_with("OL-1", {
            "unit_price": 1550.0,
            "notes": "Updated",
        })

    def test_delete_order_line_route_returns_success_and_guard_failure(self):
        service_result = {
            "success": True,
            "order_line_id": "OL-1",
            "line_status": "Cancelled",
        }

        with patch.object(order_routes, "delete_order_line", return_value=service_result) as delete_line:
            response = self.client.delete("/api/master/order-lines/OL-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        delete_line.assert_called_once_with("OL-1")

        with patch.object(order_routes, "delete_order_line", side_effect=ValueError("Reserved lines must be released first.")):
            guard_response = self.client.delete("/api/master/order-lines/OL-1")

        self.assertEqual(guard_response.status_code, 400)
        self.assertEqual(guard_response.get_json(), {
            "success": False,
            "errors": ["Reserved lines must be released first."],
        })

    def test_reserve_route_returns_200_for_successful_service_result(self):
        service_result = {
            "success": True,
            "order_id": "ORD-1",
            "changed_count": 1,
        }

        with patch.object(order_routes, "reserve_order_lines", return_value=service_result) as reserve:
            response = self.client.post("/api/orders/ORD-1/reserve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        reserve.assert_called_once_with("ORD-1")

    def test_reserve_route_returns_422_when_service_reports_no_eligible_lines(self):
        service_result = {
            "success": False,
            "order_id": "ORD-1",
            "errors": ["No eligible lines to reserve."],
        }

        with patch.object(order_routes, "reserve_order_lines", return_value=service_result):
            response = self.client.post("/api/orders/ORD-1/reserve")

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.get_json()["errors"], ["No eligible lines to reserve."])

    def test_release_route_returns_400_for_service_guard_failure(self):
        with patch.object(order_routes, "release_order_lines", side_effect=ValueError("Order not found.")):
            response = self.client.post("/api/orders/ORD-MISSING/release")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json(), {
            "success": False,
            "errors": ["Order not found."],
        })

    def test_send_for_approval_route_passes_changed_by_and_returns_success(self):
        service_result = {
            "success": True,
            "order_id": "ORD-1",
            "order_status": "Pending_Approval",
        }

        with patch.object(order_routes, "send_order_for_approval", return_value=service_result) as send:
            response = self.client.post(
                "/api/orders/ORD-1/send-for-approval",
                json={"changed_by": "Tester"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        send.assert_called_once_with("ORD-1", changed_by="Tester")

    def test_lifecycle_routes_return_400_for_guard_failures(self):
        route_cases = [
            ("/api/orders/ORD-1/approve", "approve_order", "Only Pending_Approval orders can be approved."),
            ("/api/orders/ORD-1/reject", "reject_order", "Completed orders cannot be rejected."),
            ("/api/orders/ORD-1/cancel", "cancel_order", "Completed orders cannot be cancelled."),
            ("/api/orders/ORD-1/complete", "complete_order", "Only Approved orders can be completed."),
        ]

        for url, function_name, message in route_cases:
            with self.subTest(url=url), patch.object(
                order_routes,
                function_name,
                side_effect=ValueError(message),
            ):
                response = self.client.post(url, json={"changed_by": "Tester", "reason": "Customer changed mind"})

            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.get_json(), {
                "success": False,
                "errors": [message],
            })

    def test_cancel_route_passes_reason_and_changed_by(self):
        service_result = {
            "success": True,
            "order_id": "ORD-1",
            "order_status": "Cancelled",
        }

        with patch.object(order_routes, "cancel_order", return_value=service_result) as cancel:
            response = self.client.post(
                "/api/orders/ORD-1/cancel",
                json={"changed_by": "Tester", "reason": "Customer changed mind"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        cancel.assert_called_once_with(
            "ORD-1",
            changed_by="Tester",
            reason="Customer changed mind",
        )

    def test_order_detail_route_returns_documents_and_404_for_missing_order(self):
        detail = {
            "order": {"order_id": "ORD-1"},
            "lines": [{"order_line_id": "OL-1"}],
        }
        documents = [
            {
                "Document_ID": "DOC-1",
                "Order_ID": "ORD-1",
                "Document_Type": "Quote",
                "Document_Status": "Generated",
                "Version": "1",
            }
        ]

        with patch.object(order_routes, "get_order_detail", return_value=detail), \
             patch.object(order_routes, "get_order_documents", return_value=documents):
            response = self.client.get("/api/orders/ORD-1")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["order"]["order_id"], "ORD-1")
        self.assertEqual(payload["documents"][0]["document_id"], "DOC-1")

        with patch.object(order_routes, "get_order_detail", return_value=None):
            missing_response = self.client.get("/api/orders/ORD-MISSING")

        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(missing_response.get_json(), {
            "success": False,
            "error": "Order not found.",
        })

    def test_sync_lines_route_validates_payload_and_attaches_auto_quote_on_success(self):
        service_result = {
            "success": True,
            "order_id": "ORD-1",
            "complete_fulfillment": True,
        }
        payload = {
            "changed_by": "Tester",
            "requested_items": [
                {
                    "request_item_key": "primary_1",
                    "category": "Grower",
                    "weight_range": "40_to_44_Kg",
                    "sex": "Any",
                    "quantity": 1,
                }
            ],
        }

        with patch.object(order_routes, "sync_order_lines_from_request", return_value=service_result) as sync, \
             patch.object(order_routes, "_attach_auto_quote_result") as attach_quote:
            response = self.client.post("/api/master/orders/ORD-1/sync-lines", json=payload)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        sync.assert_called_once()
        self.assertEqual(sync.call_args.args[0], "ORD-1")
        self.assertEqual(sync.call_args.args[1]["changed_by"], "Tester")
        attach_quote.assert_called_once_with(service_result, "ORD-1", changed_by="Tester")

    def test_sync_lines_route_returns_400_for_validation_errors(self):
        response = self.client.post(
            "/api/master/orders/ORD-1/sync-lines",
            json={"requested_items": []},
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("requested_items is required", payload["errors"][0])


if __name__ == "__main__":
    unittest.main()
