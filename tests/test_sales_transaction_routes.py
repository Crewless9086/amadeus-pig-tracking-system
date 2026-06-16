import unittest
from unittest.mock import patch

from app import app
from modules.sales import sales_transaction_routes


class SalesTransactionRoutesTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_sales_transaction_list_route_is_read_only(self):
        service_result = {
            "success": True,
            "status": "ok",
            "count": 0,
            "sales_transactions": [],
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "list_sales_transactions",
            return_value=(service_result, 200),
        ) as list_transactions:
            response = self.client.get("/api/sales-transactions?sale_stream=Slaughter&limit=10")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_transactions.assert_called_once_with(sale_stream="Slaughter", limit="10")

    def test_sales_transaction_list_route_returns_400_for_invalid_stream(self):
        with patch.object(
            sales_transaction_routes,
            "list_sales_transactions",
            side_effect=ValueError("sale_stream must be Livestock, Slaughter, or Meat."),
        ):
            response = self.client.get("/api/sales-transactions?sale_stream=Auction")

        self.assertEqual(response.status_code, 400)
        payload = response.get_json()
        self.assertFalse(payload["success"])
        self.assertIn("sale_stream must be Livestock", payload["errors"][0])
        self.assertFalse(payload["source"]["writes_to_sheets"])
        self.assertFalse(payload["source"]["writes_to_supabase"])

    def test_sales_transaction_dry_run_route_never_writes(self):
        service_result = {
            "success": True,
            "status": "ok",
            "mode": "dry_run",
            "source": {
                "source": "validation_only",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "dry_run_sales_transaction",
            return_value=(service_result, 200),
        ) as dry_run:
            response = self.client.post("/api/sales-transactions/dry-run", json={
                "sale_stream": "Slaughter",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        dry_run.assert_called_once()

    def test_sales_transaction_create_route_calls_create_service(self):
        service_result = {
            "success": True,
            "status": "created",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": True,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "create_sales_transaction",
            return_value=(service_result, 201),
        ) as create_transaction:
            response = self.client.post("/api/sales-transactions", json={
                "sale_stream": "Slaughter",
            })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        create_transaction.assert_called_once()

    def test_sales_transaction_detail_route_calls_read_service(self):
        service_result = {
            "success": True,
            "status": "ok",
            "sales_transaction": {"sale_id": "SALE-1"},
            "items": [],
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_transaction",
            return_value=(service_result, 200),
        ) as get_transaction:
            response = self.client.get("/api/sales-transactions/SALE-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_transaction.assert_called_once_with("SALE-1")

    def test_sales_transaction_cancel_route_calls_cancel_service(self):
        service_result = {
            "success": True,
            "status": "cancelled",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": True,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "cancel_sales_transaction",
            return_value=(service_result, 200),
        ) as cancel_transaction:
            response = self.client.post("/api/sales-transactions/SALE-1/cancel", json={
                "cancelled_by": "Charl",
                "cancel_reason": "Test complete",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        cancel_transaction.assert_called_once()

    def test_sales_transaction_payment_update_route_calls_update_service(self):
        service_result = {
            "success": True,
            "status": "updated",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase",
                "writes_to_sheets": False,
                "writes_to_supabase": True,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "update_slaughter_sale_payment",
            return_value=(service_result, 200),
        ) as update_transaction:
            response = self.client.patch("/api/sales-transactions/SALE-1/payment", json={
                "updated_by": "Charl",
                "line_total": 1500,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        update_transaction.assert_called_once()

    def test_sales_transaction_confirm_pig_exits_route_calls_lifecycle_service(self):
        service_result = {
            "success": True,
            "status": "pig_exits_confirmed",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase_sales_transaction_to_google_sheets_pig_master",
                "writes_to_sheets": True,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "confirm_slaughter_pig_exits",
            return_value=(service_result, 200),
        ) as confirm_exits:
            response = self.client.post("/api/sales-transactions/SALE-1/confirm-pig-exits", json={
                "changed_by": "Charl",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        confirm_exits.assert_called_once()

    def test_sales_transaction_reconcile_pig_exits_route_calls_lifecycle_service(self):
        service_result = {
            "success": True,
            "status": "pig_exits_reconcile_preview",
            "sale_id": "SALE-1",
            "source": {
                "source": "supabase_sales_transaction_to_google_sheets_pig_master",
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "reconcile_closed_slaughter_pig_exits",
            return_value=(service_result, 200),
        ) as reconcile_exits:
            response = self.client.post("/api/sales-transactions/SALE-1/reconcile-pig-exits", json={
                "dry_run": True,
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        reconcile_exits.assert_called_once()

    def test_meat_sales_leads_list_route_uses_sales_lead_store(self):
        service_result = {
            "success": True,
            "status": "ok",
            "sales_leads": [{"lead_id": "OSK-SALES-LEAD-1"}],
            "source": {
                "writes_to_sheets": False,
                "writes_to_supabase": False,
            },
        }

        with patch.object(
            sales_transaction_routes,
            "list_sales_leads",
            return_value=(service_result, 200),
        ) as list_leads:
            response = self.client.get("/api/sales/meat-leads?limit=12&status=launch_test")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_leads.assert_called_once_with(limit="12", status_filter="launch_test")

    def test_meat_sales_lead_contract_route_uses_preorder_contract(self):
        service_result = {
            "success": True,
            "status": "ok",
            "lead_id": "OSK-SALES-LEAD-1",
            "contract": {"contract_status": "owner_money_path_ready"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_preorder_contract",
            return_value=(service_result, 200),
        ) as get_contract:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/contract")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_contract.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_sales_lead_owner_approval_route_records_event(self):
        service_result = {
            "success": True,
            "status": "ok",
            "records_owner_money_path_approval": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_owner_money_path_approval",
            return_value=(service_result, 201),
        ) as record_approval:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/owner-money-path-approval",
                json={"price_per_kg": "R100.00"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_approval.assert_called_once_with("OSK-SALES-LEAD-1", {"price_per_kg": "R100.00"})

    def test_meat_sales_lead_followup_draft_route_reads_draft(self):
        service_result = {
            "success": True,
            "status": "ok",
            "customer_followup_draft": {"message": "Hi Charl"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_customer_followup_draft",
            return_value=(service_result, 200),
        ) as get_draft:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-draft")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_draft.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_sales_lead_send_approval_route_records_exact_message_approval(self):
        service_result = {
            "success": True,
            "status": "ok",
            "records_customer_followup_send_approval": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_customer_followup_send_approval",
            return_value=(service_result, 201),
        ) as record_send_approval:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-send-approval",
                json={"message": "Approved text"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_send_approval.assert_called_once_with("OSK-SALES-LEAD-1", {"message": "Approved text"})

    def test_meat_sales_lead_send_route_requires_env_unlock(self):
        with patch.dict("os.environ", {"OOM_SAKKIE_MEAT_FOLLOWUP_SEND_ENABLED": "0"}):
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-send",
                json={"message": "Approved text"},
            )

        payload = response.get_json()
        self.assertEqual(response.status_code, 503)
        self.assertFalse(payload["sent"])
        self.assertEqual(payload["status"], "meat_followup_send_disabled")
        self.assertFalse(payload["creates_order"])
        self.assertFalse(payload["changes_stock"])

    def test_meat_sales_lead_send_route_calls_chatwoot_sender_when_enabled(self):
        service_result = {
            "success": True,
            "status": "sent",
            "sent": True,
            "sends_customer_message": True,
            "calls_chatwoot": True,
            "creates_quote": False,
            "creates_order": False,
            "changes_stock": False,
        }

        with patch.dict("os.environ", {"OOM_SAKKIE_MEAT_FOLLOWUP_SEND_ENABLED": "1"}), patch.object(
            sales_transaction_routes,
            "send_customer_followup_to_chatwoot",
            return_value=(service_result, 200),
        ) as send_followup:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-followup-send",
                json={"message": "Approved text"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        send_followup.assert_called_once_with("OSK-SALES-LEAD-1", {"message": "Approved text"})


if __name__ == "__main__":
    unittest.main()
