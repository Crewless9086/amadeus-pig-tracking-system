import unittest
from unittest.mock import patch

from app import app
from modules.orders import order_routes


class OrderRoutesTests(unittest.TestCase):
    @patch("modules.orders.order_routes.prepare_live_stock_sales_pack")
    def test_prepare_sales_pack_route_returns_owner_gated_bundle(self, prepare):
        prepare.return_value = {
            "success": True,
            "status": "sam_live_stock_sales_pack_ready",
            "customer_send_allowed": False,
        }
        response = self.client.post("/api/orders/ORD-1/sales-pack/prepare", json={"created_by": "Owner"})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["customer_send_allowed"])
        prepare.assert_called_once_with("ORD-1", {"created_by": "Owner"})
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
            "order_stream": "Livestock",
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

    def test_create_order_rejects_missing_or_invalid_explicit_stream(self):
        base = {
            "order_date": "2026-05-18", "customer_name": "Sam",
            "customer_channel": "Chatwoot", "customer_language": "English",
            "order_source": "WhatsApp",
        }
        for stream in (None, "Auction"):
            payload = dict(base)
            if stream is not None:
                payload["order_stream"] = stream
            response = self.client.post("/api/master/orders", json=payload)
            self.assertEqual(response.status_code, 400)
            self.assertIn("Order_Stream must be Livestock, Meat, or Slaughter.", response.get_json()["errors"])

    def test_shadow_order_compare_route_is_read_only_boundary(self):
        service_result = {
            "success": True,
            "status": "ok",
            "mode": "shadow_compare",
            "source": {
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(order_routes, "compare_shadow_order", return_value=(service_result, 200)) as compare:
            response = self.client.get("/api/shadow/orders/ORD-1/compare")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        compare.assert_called_once()
        self.assertEqual(compare.call_args.args[0], "ORD-1")

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

    def test_update_order_route_accepts_saved_conversation_id(self):
        service_result = {"success": True, "order_id": "ORD-1", "updated_fields": ["conversation_id"]}
        with patch.object(order_routes, "update_order", return_value=service_result) as update:
            response = self.client.patch(
                "/api/master/orders/ORD-1",
                json={"conversation_id": "1871", "changed_by": "Tester"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        self.assertEqual(update.call_args.args[1]["conversation_id"], "1871")

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

    def test_generate_quote_route_uses_readiness_flow_and_reuses_current_quote(self):
        service_result = {
            "success": True,
            "action": "auto_generate_quote_if_ready",
            "quote_ready": True,
            "generated": False,
            "skipped": True,
            "reason": "latest_quote_current",
            "order_id": "ORD-1",
            "document": {"document_id": "DOC-1", "document_ref": "Q-1"},
        }

        with patch.object(order_routes, "auto_generate_quote_if_ready", return_value=service_result) as generate:
            response = self.client.post("/api/orders/ORD-1/quote", json={"created_by": "Tester"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        generate.assert_called_once_with("ORD-1", created_by="Tester")

    def test_generate_quote_route_returns_missing_fields_as_json(self):
        service_result = {
            "success": True,
            "action": "auto_generate_quote_if_ready",
            "quote_ready": False,
            "generated": False,
            "skipped": True,
            "missing_fields": ["payment_method"],
            "order_id": "ORD-1",
        }

        with patch.object(order_routes, "auto_generate_quote_if_ready", return_value=service_result):
            response = self.client.post("/api/orders/ORD-1/quote", json={"created_by": "Tester"})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["missing_fields"], ["payment_method"])

    def test_generate_quote_route_returns_unexpected_errors_as_json(self):
        with patch.object(order_routes, "auto_generate_quote_if_ready", side_effect=RuntimeError("drive offline")):
            response = self.client.post("/api/orders/ORD-1/quote", json={"created_by": "Tester"})

        payload = response.get_json()
        self.assertEqual(response.status_code, 500)
        self.assertFalse(payload["success"])
        self.assertEqual(payload["action"], "generate_quote")
        self.assertIn("RuntimeError: drive offline", payload["errors"][0])

    def test_refresh_order_pricing_route_returns_resolution_result(self):
        service_result = {
            "success": True,
            "status": "order_prices_ready",
            "order_id": "ORD-1",
            "updated_count": 2,
            "estimated_total": 1400,
        }
        with patch.object(order_routes, "ensure_order_line_prices", return_value=service_result) as ensure:
            response = self.client.post("/api/orders/ORD-1/pricing", json={"reprice": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        ensure.assert_called_once_with("ORD-1", reprice=True)

    def test_order_search_route_passes_query_and_returns_400_for_validation_error(self):
        service_result = {
            "success": True,
            "action": "search_orders",
            "lookup_status": "single_match",
            "matches": [{"order_id": "ORD-1"}],
        }

        with patch.object(order_routes, "search_orders", return_value=service_result) as search:
            response = self.client.get(
                "/api/orders/search?customer_name=charl&status_scope=all&limit=3"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        search.assert_called_once_with(
            order_id="",
            customer_phone="",
            customer_name="charl",
            conversation_id="",
            status_scope="all",
            limit="3",
        )

        with patch.object(order_routes, "search_orders", side_effect=ValueError("Provide order_id.")):
            error_response = self.client.get("/api/orders/search")

        self.assertEqual(error_response.status_code, 400)
        self.assertEqual(error_response.get_json(), {
            "success": False,
            "action": "search_orders",
            "errors": ["Provide order_id."],
        })

    def test_operator_summary_route_returns_summary_and_404_for_missing_order(self):
        service_result = {
            "success": True,
            "action": "get_order_operator_summary",
            "order_id": "ORD-1",
            "order_summary": {"order_id": "ORD-1"},
        }

        with patch.object(order_routes, "get_order_operator_summary", return_value=service_result) as summary:
            response = self.client.get("/api/orders/ORD-1/operator-summary")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        summary.assert_called_once_with("ORD-1")

        with patch.object(order_routes, "get_order_operator_summary", return_value=None):
            missing_response = self.client.get("/api/orders/ORD-MISSING/operator-summary")

        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(missing_response.get_json(), {
            "success": False,
            "action": "get_order_operator_summary",
            "lookup_status": "no_match",
            "order_id": "ORD-MISSING",
            "error": "Order not found.",
        })

    def test_prepare_latest_quote_send_route_returns_button_context_without_sending(self):
        detail = {
            "order": {
                "order_id": "ORD-1",
                "customer_name": "Charl N",
                "conversation_id": "1774",
            },
            "lines": [],
        }
        quote = {
            "Document_ID": "DOC-1",
            "Order_ID": "ORD-1",
            "Document_Type": "Quote",
            "Document_Ref": "Q-1",
            "Document_Status": "Generated",
            "Total": 1400,
            "Valid_Until": "2026-05-20",
        }

        with patch.object(order_routes, "get_order_detail", return_value=detail), \
             patch.object(order_routes, "get_latest_non_voided_quote", return_value=quote), \
             patch.object(order_routes, "send_order_document") as send_document:
            response = self.client.post(
                "/api/orders/ORD-1/quote/prepare-send",
                json={"requested_by": "Oom Sakkie"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertTrue(payload["send_ready"])
        self.assertEqual(payload["action"], "prepare_latest_quote_send")
        self.assertEqual(payload["destination"]["conversation_id"], "1774")
        self.assertEqual(payload["destination"]["source"], "order_record")
        self.assertEqual(payload["document"]["document_id"], "DOC-1")
        self.assertEqual(payload["button_context"]["send_label"], "Send quote to customer")
        self.assertIn("quote_send|ORD-1|DOC-1|1774", payload["button_context"]["callback_data"])
        send_document.assert_not_called()

    def test_prepare_latest_quote_send_route_uses_explicit_conversation_id(self):
        detail = {
            "order": {
                "order_id": "ORD-1",
                "customer_name": "Charl N",
                "conversation_id": "1774",
            },
            "lines": [],
        }
        quote = {
            "Document_ID": "DOC-1",
            "Document_Type": "Quote",
            "Document_Ref": "Q-1",
            "Document_Status": "Generated",
            "Total": 1400,
        }

        with patch.object(order_routes, "get_order_detail", return_value=detail), \
             patch.object(order_routes, "get_latest_non_voided_quote", return_value=quote):
            response = self.client.post(
                "/api/orders/ORD-1/quote/prepare-send",
                json={"conversation_id": "9999"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["destination"]["conversation_id"], "9999")
        self.assertEqual(payload["destination"]["source"], "operator_input")

    def test_prepare_latest_quote_send_route_blocks_missing_destination_and_superseded_quote(self):
        detail = {
            "order": {
                "order_id": "ORD-1",
                "customer_name": "Charl N",
                "conversation_id": "",
            },
            "lines": [],
        }

        with patch.object(order_routes, "get_order_detail", return_value=detail):
            missing_destination = self.client.post("/api/orders/ORD-1/quote/prepare-send")

        self.assertEqual(missing_destination.status_code, 400)
        self.assertFalse(missing_destination.get_json()["send_ready"])
        self.assertIn("No confirmed customer conversation", missing_destination.get_json()["errors"][0])

        detail["order"]["conversation_id"] = "1774"
        superseded_quote = {
            "Document_ID": "DOC-1",
            "Document_Type": "Quote",
            "Document_Ref": "Q-1",
            "Document_Status": "Superseded",
        }

        with patch.object(order_routes, "get_order_detail", return_value=detail), \
             patch.object(order_routes, "get_latest_non_voided_quote", return_value=superseded_quote):
            superseded = self.client.post("/api/orders/ORD-1/quote/prepare-send")

        self.assertEqual(superseded.status_code, 400)
        self.assertIn("Superseded quotes cannot be sent", superseded.get_json()["errors"][0])

    def test_prepare_latest_quote_send_route_blocks_terminal_order(self):
        detail = {
            "order": {
                "order_id": "ORD-1",
                "customer_name": "Charl N",
                "conversation_id": "1774",
                "order_status": "Cancelled",
                "approval_status": "Not_Required",
            },
            "lines": [],
        }

        with patch.object(order_routes, "get_order_detail", return_value=detail), \
             patch.object(order_routes, "get_latest_non_voided_quote") as latest_quote, \
             patch.object(order_routes, "send_order_document") as send_document:
            response = self.client.post("/api/orders/ORD-1/quote/prepare-send")

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["send_ready"])
        self.assertIn("order is Cancelled", payload["errors"][0])
        latest_quote.assert_not_called()
        send_document.assert_not_called()

    def test_send_latest_quote_confirmed_route_rechecks_and_sends_matching_latest_quote(self):
        detail = {
            "order": {
                "order_id": "ORD-1",
                "customer_name": "Charl N",
                "conversation_id": "1774",
            },
            "lines": [],
        }
        quote = {
            "Document_ID": "DOC-1",
            "Document_Type": "Quote",
            "Document_Ref": "Q-1",
            "Document_Status": "Generated",
        }
        send_result = {
            "success": True,
            "document_id": "DOC-1",
            "order_id": "ORD-1",
            "conversation_id": "1774",
            "message": "Document sent successfully.",
        }

        with patch.object(order_routes, "get_order_detail", return_value=detail), \
             patch.object(order_routes, "get_latest_non_voided_quote", return_value=quote), \
             patch.object(order_routes, "send_order_document", return_value=send_result) as send_document:
            response = self.client.post(
                "/api/orders/ORD-1/quote/send-latest-confirmed",
                json={
                    "document_id": "DOC-1",
                    "conversation_id": "1774",
                    "sent_by": "Oom Sakkie",
                    "confirmation_source": "telegram_button",
                    "telegram_user_id": "123",
                    "force_resend": True,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "send_latest_quote_confirmed")
        self.assertEqual(payload["confirmation_source"], "telegram_button")
        self.assertEqual(payload["telegram_user_id"], "123")
        send_document.assert_called_once_with(
            "DOC-1",
            conversation_id="1774",
            sent_by="Oom Sakkie",
            account_id="147387",
            force_resend=True,
        )

    def test_send_latest_quote_confirmed_route_blocks_stale_document_selection(self):
        detail = {
            "order": {
                "order_id": "ORD-1",
                "conversation_id": "1774",
            },
            "lines": [],
        }
        newer_quote = {
            "Document_ID": "DOC-2",
            "Document_Type": "Quote",
            "Document_Ref": "Q-2",
            "Document_Status": "Generated",
        }

        with patch.object(order_routes, "get_order_detail", return_value=detail), \
             patch.object(order_routes, "get_latest_non_voided_quote", return_value=newer_quote), \
             patch.object(order_routes, "send_order_document") as send_document:
            response = self.client.post(
                "/api/orders/ORD-1/quote/send-latest-confirmed",
                json={
                    "document_id": "DOC-1",
                    "conversation_id": "1774",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("no longer the latest", response.get_json()["errors"][0])
        send_document.assert_not_called()

    def test_send_latest_quote_confirmed_route_blocks_terminal_order(self):
        detail = {
            "order": {
                "order_id": "ORD-1",
                "conversation_id": "1774",
                "order_status": "Cancelled",
                "approval_status": "Not_Required",
            },
            "lines": [],
        }

        with patch.object(order_routes, "get_order_detail", return_value=detail), \
             patch.object(order_routes, "get_latest_non_voided_quote") as latest_quote, \
             patch.object(order_routes, "send_order_document") as send_document:
            response = self.client.post(
                "/api/orders/ORD-1/quote/send-latest-confirmed",
                json={
                    "document_id": "DOC-1",
                    "conversation_id": "1774",
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn("order is Cancelled", response.get_json()["errors"][0])
        latest_quote.assert_not_called()
        send_document.assert_not_called()

    def test_send_latest_quote_confirmed_route_requires_document_and_conversation(self):
        response = self.client.post(
            "/api/orders/ORD-1/quote/send-latest-confirmed",
            json={"document_id": "DOC-1"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["action"], "send_latest_quote_confirmed")
        self.assertIn("conversation_id is required", response.get_json()["errors"][0])

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

    def test_approved_livestock_revision_route_validates_and_calls_service(self):
        service_result = {
            "success": True,
            "action": "revise_approved_livestock_order",
            "order_id": "ORD-2026-12BCCC",
            "customer_quote_send": {"sent": False, "owner_instruction_required": True},
        }
        payload = {
            "changed_by": "Oom Sakkie",
            "owner_confirmation": "REVISE APPROVED LIVESTOCK ORDER",
            "authorization_source": "telegram_owner_action",
            "requested_items": [{
                "request_item_key": "michaels-piglets",
                "category": "Piglet",
                "weight_range": "7_to_9_Kg",
                "sex": "Any",
                "quantity": 5,
            }],
            "order_updates": {
                "requested_quantity": 5,
                "requested_category": "Piglet",
                "requested_weight_range": "7_to_9_Kg",
                "requested_sex": "Any",
            },
            "sale_readiness_correction": {
                "tag_number": "104",
                "weight_kg": 8.4,
                "purpose": "Sale",
            },
        }

        with patch.object(order_routes, "revise_approved_livestock_order", return_value=service_result) as revise:
            response = self.client.post(
                "/api/orders/ORD-2026-12BCCC/approved-livestock-revision",
                json=payload,
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        revise.assert_called_once()
        self.assertEqual(revise.call_args.args[0], "ORD-2026-12BCCC")
        cleaned = revise.call_args.args[1]
        self.assertEqual(cleaned["requested_items"][0]["quantity"], 5)
        self.assertEqual(cleaned["order_updates"]["requested_quantity"], 5.0)

    def test_approved_livestock_revision_route_requires_owner_authorization_before_service_call(self):
        payload = {
            "changed_by": "Oom Sakkie",
            "requested_items": [{
                "request_item_key": "michaels-piglets",
                "category": "Piglet",
                "weight_range": "7_to_9_Kg",
                "sex": "Any",
                "quantity": 5,
            }],
        }

        with patch.object(order_routes, "revise_approved_livestock_order") as revise:
            response = self.client.post(
                "/api/orders/ORD-2026-12BCCC/approved-livestock-revision",
                json=payload,
            )

        self.assertEqual(response.status_code, 403)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertTrue(payload["owner_authorization_required"])
        self.assertIn("Owner/Oom Sakkie authorization is required", payload["errors"][0])
        revise.assert_not_called()

    def test_approved_livestock_revision_route_returns_400_for_invalid_payload(self):
        response = self.client.post(
            "/api/orders/ORD-2026-12BCCC/approved-livestock-revision",
            json={
                "changed_by": "Oom Sakkie",
                "owner_authorized": True,
                "authorization_source": "telegram_owner_action",
                "requested_items": [],
            },
        )

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertEqual(payload["action"], "revise_approved_livestock_order")
        self.assertIn("requested_items is required", payload["errors"][0])


if __name__ == "__main__":
    unittest.main()
