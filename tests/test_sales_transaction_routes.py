import unittest
from io import BytesIO
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

    def test_beacon_media_policy_route_returns_storage_policy(self):
        with patch.object(
            sales_transaction_routes,
            "beacon_media_storage_policy",
            return_value={"success": True, "farm_app_standard_upload_enabled": False},
        ) as policy:
            response = self.client.get("/api/beacon/media-policy")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["farm_app_standard_upload_enabled"])
        policy.assert_called_once()

    def test_beacon_media_assets_list_and_register_routes(self):
        service_result = {
            "success": True,
            "status": "ok",
            "assets": [{"asset_id": "BEACON-ASSET-1"}],
        }

        with patch.object(
            sales_transaction_routes,
            "list_beacon_media_assets",
            return_value=(service_result, 200),
        ) as list_assets:
            response = self.client.get("/api/beacon/media-assets?limit=12&approval_status=needs_review&media_type=image")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_assets.assert_called_once_with(limit="12", approval_status="needs_review", media_type="image")

        with patch.object(
            sales_transaction_routes,
            "register_beacon_media_asset",
            return_value=({"success": True, "asset_id": "BEACON-ASSET-2"}, 201),
        ) as register_asset:
            response = self.client.post("/api/beacon/media-assets", json={
                "storage_path": "2026/06/18/test.jpg",
                "media_type": "image",
            })

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["asset_id"], "BEACON-ASSET-2")
        register_asset.assert_called_once_with({"storage_path": "2026/06/18/test.jpg", "media_type": "image"})

    def test_beacon_media_asset_upload_and_event_routes(self):
        with patch.object(
            sales_transaction_routes,
            "upload_beacon_media_asset",
            return_value=({"success": True, "asset_id": "BEACON-ASSET-UPLOAD"}, 201),
        ) as upload_asset:
            response = self.client.post(
                "/api/beacon/media-assets/upload",
                data={"file": (BytesIO(b"fake"), "test.jpg"), "uploader_label": "Charl"},
                content_type="multipart/form-data",
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["asset_id"], "BEACON-ASSET-UPLOAD")
        upload_asset.assert_called_once()

        with patch.object(
            sales_transaction_routes,
            "record_beacon_media_asset_event",
            return_value=({"success": True, "event_id": "BEACON-ASSET-EVENT-1"}, 201),
        ) as record_event:
            response = self.client.post(
                "/api/beacon/media-assets/BEACON-ASSET-1/events",
                json={"event_type": "review_note", "notes": "Good photo."},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["event_id"], "BEACON-ASSET-EVENT-1")
        record_event.assert_called_once_with("BEACON-ASSET-1", {"event_type": "review_note", "notes": "Good photo."})

    def test_beacon_campaign_draft_selection_route_uses_only_approved_media(self):
        assets_result = {
            "success": True,
            "assets": [{"asset_id": "BEACON-ASSET-APPROVED", "effective_approval_status": "approved"}],
        }
        selection_result = {
            "success": True,
            "mode": "beacon_meat_launch_campaign_media_selection_review_only",
            "approved_media_count": 1,
        }

        with patch.object(
            sales_transaction_routes,
            "list_beacon_media_assets",
            return_value=(assets_result, 200),
        ) as list_assets, patch.object(
            sales_transaction_routes,
            "build_meat_launch_campaign_selection",
            return_value=selection_result,
        ) as build_selection:
            response = self.client.get("/api/beacon/campaign-draft-selection?limit=9&media_type=image&area=Riversdale")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), selection_result)
        list_assets.assert_called_once_with(limit="9", approval_status="approved", media_type="image")
        build_selection.assert_called_once()
        self.assertEqual(build_selection.call_args.kwargs["approved_assets"], assets_result["assets"])
        self.assertEqual(build_selection.call_args.args[0]["area"], "Riversdale")

    def test_beacon_campaign_publish_packet_route_validates_against_approved_media(self):
        assets_result = {
            "success": True,
            "assets": [{"asset_id": "BEACON-ASSET-APPROVED", "effective_approval_status": "approved"}],
        }
        publish_result = {
            "success": True,
            "mode": "beacon_campaign_publish_packet_owner_review_only",
            "publish_packet_id": "BEACON-PUBLISH-PACKET-1",
        }

        with patch.object(
            sales_transaction_routes,
            "list_beacon_media_assets",
            return_value=(assets_result, 200),
        ) as list_assets, patch.object(
            sales_transaction_routes,
            "build_meat_launch_campaign_publish_packet",
            return_value=publish_result,
        ) as build_packet:
            response = self.client.post("/api/beacon/campaign-publish-packet", json={
                "draft_id": "facebook_post",
                "asset_id": "BEACON-ASSET-APPROVED",
                "media_type": "image",
            })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), publish_result)
        list_assets.assert_called_once_with(limit=25, approval_status="approved", media_type="image")
        build_packet.assert_called_once()
        self.assertEqual(build_packet.call_args.kwargs["approved_assets"], assets_result["assets"])

    def test_meat_sales_learning_list_route_uses_learning_store(self):
        service_result = {
            "success": True,
            "status": "ok",
            "learning_events": [{"learning_event_id": "MSCL-1"}],
            "summary": {"total_events": 1},
        }

        with patch.object(
            sales_transaction_routes,
            "list_sales_conversation_learning_events",
            return_value=(service_result, 200),
        ) as list_learning:
            response = self.client.get("/api/sales/meat-learning?limit=12&lead_id=OSK-SALES-LEAD-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_learning.assert_called_once_with(limit="12", lead_id="OSK-SALES-LEAD-1")

    def test_meat_price_book_list_route_uses_store(self):
        service_result = {
            "success": True,
            "status": "ok",
            "price_entries": [{"product_type": "half_carcass"}],
        }

        with patch.object(
            sales_transaction_routes,
            "list_meat_price_book_entries",
            return_value=(service_result, 200),
        ) as list_prices:
            response = self.client.get("/api/sales/meat-pricing?limit=12")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_prices.assert_called_once_with(limit="12")

    def test_meat_price_book_create_route_records_entry(self):
        service_result = {
            "success": True,
            "status": "ok",
            "price_entry_id": "OSK-MEAT-PRICE-TEST",
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_price_book_entry",
            return_value=(service_result, 201),
        ) as record_price:
            response = self.client.post(
                "/api/sales/meat-pricing",
                json={"product_type": "half_carcass", "price_amount": 130},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_price.assert_called_once_with({"product_type": "half_carcass", "price_amount": 130})

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

    def test_meat_sales_lead_learning_events_get_and_post_routes(self):
        service_result = {
            "success": True,
            "status": "ok",
            "learning_events": [{"learning_event_id": "MSCL-1"}],
            "summary": {"total_events": 1},
        }

        with patch.object(
            sales_transaction_routes,
            "list_sales_conversation_learning_events",
            return_value=(service_result, 200),
        ) as list_learning:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/learning-events?limit=7")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_learning.assert_called_once_with(limit="7", lead_id="OSK-SALES-LEAD-1")

        with patch.object(
            sales_transaction_routes,
            "build_owner_review_learning_event",
            return_value={"lead_id": "OSK-SALES-LEAD-1", "event_type": "owner_review_note"},
        ) as build_event, patch.object(
            sales_transaction_routes,
            "record_sales_conversation_learning_event",
            return_value=({"success": True, "learning_event_id": "MSCL-OWNER"}, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/learning-events",
                json={"notes": "Customer asked about price."},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json()["learning_event_id"], "MSCL-OWNER")
        build_event.assert_called_once_with("OSK-SALES-LEAD-1", {"notes": "Customer asked about price."})
        record_event.assert_called_once_with({"lead_id": "OSK-SALES-LEAD-1", "event_type": "owner_review_note"})

    def test_meat_sales_lead_pricing_estimate_route_uses_estimator(self):
        service_result = {
            "success": True,
            "status": "ok",
            "pricing_estimate": {"price_label": "R130.00/kg"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_pricing_estimate",
            return_value=(service_result, 200),
        ) as get_estimate:
            response = self.client.get(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/pricing-estimate?selected_pig_live_weight_kg=62"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_estimate.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"selected_pig_live_weight_kg": "62"},
        )

    def test_meat_sales_lead_match_route_uses_butcher_match_engine(self):
        service_result = {
            "success": True,
            "status": "ok",
            "meat_match": {"decision": "recommend"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_sales_lead_meat_match",
            return_value=(service_result, 200),
        ) as get_match:
            response = self.client.get(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/meat-match?preference=heaviest&target_packed_kg=25&budget_amount=3000"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_match.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"preference": "heaviest", "target_packed_kg": "25", "budget_amount": "3000"},
        )

    def test_meat_sales_lead_ops_status_route_reads_gate(self):
        service_result = {
            "success": True,
            "status": "ok",
            "assembly": {"ready_for_instruction_drafts": False},
        }

        with patch.object(
            sales_transaction_routes,
            "get_meat_ops_status",
            return_value=(service_result, 200),
        ) as get_status:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/meat-ops")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_status.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_sales_lead_carcass_reservation_route_writes_reservation(self):
        service_result = {
            "success": True,
            "status": "half_reserved_pending_pair",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "create_carcass_reservation_from_lead",
            return_value=(service_result, 201),
        ) as create_reservation:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/carcass-reservations",
                json={"pig_id": "PIG-1"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        create_reservation.assert_called_once_with("OSK-SALES-LEAD-1", {"pig_id": "PIG-1"})

    def test_meat_sales_lead_reservation_event_route_records_cancellation(self):
        service_result = {
            "success": True,
            "status": "reservation_cancelled",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_carcass_reservation_event",
            return_value=(service_result, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/reservation-events",
                json={"reservation_id": "RES-1", "event_type": "reservation_cancelled", "reason": "Test cleanup"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_event.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"reservation_id": "RES-1", "event_type": "reservation_cancelled", "reason": "Test cleanup"},
        )

    def test_meat_sales_lead_deposit_event_route_records_gate(self):
        service_result = {
            "success": True,
            "status": "deposit_confirmed_in_bank",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_deposit_event",
            return_value=(service_result, 201),
        ) as record_deposit:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/deposit-events",
                json={"reservation_id": "RES-1", "event_type": "deposit_confirmed_in_bank", "amount": "1250"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_deposit.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"reservation_id": "RES-1", "event_type": "deposit_confirmed_in_bank", "amount": "1250"},
        )

    def test_meat_sales_lead_instruction_drafts_route_builds_internal_drafts(self):
        service_result = {
            "success": True,
            "status": "instruction_drafts_created",
            "sends_customer_message": False,
            "calls_chatwoot": False,
        }

        with patch.object(
            sales_transaction_routes,
            "build_meat_instruction_drafts",
            return_value=(service_result, 201),
        ) as build_drafts:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts",
                json={"butcher_label": "Local Butcher"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        build_drafts.assert_called_once_with("OSK-SALES-LEAD-1", {"butcher_label": "Local Butcher"})

    def test_meat_fulfillment_timeline_route_reads_timeline(self):
        service_result = {
            "success": True,
            "status": "ok",
            "fulfillment": {"next_gate": "find_second_half_buyer"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_meat_fulfillment_timeline",
            return_value=(service_result, 200),
        ) as get_timeline:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/fulfillment")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_timeline.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_reconciliation_status_route_reads_status(self):
        service_result = {
            "success": True,
            "status": "ok",
            "reconciliation": {"status": "awaiting_packed_weight"},
        }

        with patch.object(
            sales_transaction_routes,
            "get_meat_reconciliation_status",
            return_value=(service_result, 200),
        ) as get_status:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/reconciliation")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        get_status.assert_called_once_with("OSK-SALES-LEAD-1")

    def test_meat_reconciliation_event_route_records_event(self):
        service_result = {
            "success": True,
            "status": "packed_weight_recorded",
            "records_meat_reconciliation": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_reconciliation_event",
            return_value=(service_result, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/reconciliation-events",
                json={"reservation_id": "RES-1", "actual_packed_weight_kg": "24.8", "price_per_kg": "130"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_event.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"reservation_id": "RES-1", "actual_packed_weight_kg": "24.8", "price_per_kg": "130"},
        )

    def test_meat_dad_booking_packet_route_builds_draft_only_packet(self):
        service_result = {
            "success": True,
            "status": "ok",
            "dad_booking_packet": {"readiness": "ready_for_dad_booking"},
            "calls_abattoir": False,
            "calls_butcher": False,
        }

        with patch.object(
            sales_transaction_routes,
            "build_dad_booking_packet",
            return_value=(service_result, 200),
        ) as build_packet:
            response = self.client.get("/api/sales/meat-leads/OSK-SALES-LEAD-1/dad-booking-packet")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        build_packet.assert_called_once_with("OSK-SALES-LEAD-1", {})

    def test_meat_fulfillment_event_route_records_event(self):
        service_result = {
            "success": True,
            "status": "delivery_scheduled",
            "records_meat_fulfillment": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_fulfillment_event",
            return_value=(service_result, 201),
        ) as record_event:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/fulfillment-events",
                json={"event_type": "delivery_scheduled", "scheduled_date": "2026-06-20"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_event.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"event_type": "delivery_scheduled", "scheduled_date": "2026-06-20"},
        )

    def test_meat_driver_route_calls_route_reader(self):
        service_result = {
            "success": True,
            "status": "ok",
            "stops": [],
        }

        with patch.object(
            sales_transaction_routes,
            "list_meat_driver_route",
            return_value=(service_result, 200),
        ) as list_route:
            response = self.client.get("/api/sales/meat-deliveries/driver-route?driver=Dad&date=2026-06-20")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        list_route.assert_called_once_with(driver_label="Dad", scheduled_date="2026-06-20")

    def test_meat_driver_event_route_records_driver_event(self):
        service_result = {
            "success": True,
            "status": "delivery_on_way",
            "records_meat_fulfillment": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_driver_delivery_event",
            return_value=(service_result, 201),
        ) as record_driver:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/driver-events",
                json={"event_type": "delivery_on_way", "assigned_to": "Dad"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_driver.assert_called_once_with("OSK-SALES-LEAD-1", {"event_type": "delivery_on_way", "assigned_to": "Dad"})

    def test_meat_journey_notification_draft_route_builds_draft(self):
        service_result = {
            "success": True,
            "status": "draft_created",
            "notification_event": {"message": "Customer update"},
        }

        with patch.object(
            sales_transaction_routes,
            "build_meat_journey_notification_draft",
            return_value=(service_result, 201),
        ) as build_draft:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-draft",
                json={"recorded_by": "Farm App"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        build_draft.assert_called_once_with("OSK-SALES-LEAD-1", {"recorded_by": "Farm App"})

    def test_meat_journey_notification_approval_route_records_exact_approval(self):
        service_result = {
            "success": True,
            "status": "approved_to_send",
        }

        with patch.object(
            sales_transaction_routes,
            "approve_meat_journey_notification",
            return_value=(service_result, 201),
        ) as approve:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-approval",
                json={"approved_message": "Customer update"},
            )

        self.assertEqual(response.status_code, 201)
        approve.assert_called_once_with("OSK-SALES-LEAD-1", {"approved_message": "Customer update"})

    def test_meat_journey_notification_send_route_calls_sender(self):
        service_result = {
            "success": False,
            "status": "meat_journey_notification_send_disabled",
            "sent": False,
        }

        with patch.object(
            sales_transaction_routes,
            "send_meat_journey_notification",
            return_value=(service_result, 503),
        ) as send:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/journey-notification-send",
                json={"message": "Customer update"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.get_json(), service_result)
        send.assert_called_once_with("OSK-SALES-LEAD-1", {"message": "Customer update"})

    def test_meat_instruction_approval_route_records_exact_approval(self):
        service_result = {
            "success": True,
            "status": "approved_to_send",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "approve_meat_instruction_draft",
            return_value=(service_result, 201),
        ) as approve_draft:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/approval",
                json={"approved_message": "Exact draft"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        approve_draft.assert_called_once_with("OSK-SALES-LEAD-1", "DRAFT-1", {"approved_message": "Exact draft"})

    def test_meat_instruction_send_route_calls_gated_sender(self):
        service_result = {
            "success": True,
            "status": "sent",
            "sent": True,
            "informs_external_party": True,
        }

        with patch.object(
            sales_transaction_routes,
            "send_approved_meat_instruction",
            return_value=(service_result, 200),
        ) as send_instruction:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/send",
                json={"message": "Exact draft"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        send_instruction.assert_called_once_with("OSK-SALES-LEAD-1", "DRAFT-1", {"message": "Exact draft"})

    def test_meat_instruction_exception_route_records_review_state(self):
        service_result = {
            "success": True,
            "status": "exception_review_required",
            "records_meat_ops": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_meat_instruction_exception",
            return_value=(service_result, 201),
        ) as record_exception:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/instruction-drafts/DRAFT-1/exception",
                json={"reason": "Need abattoir slot date"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_exception.assert_called_once_with("OSK-SALES-LEAD-1", "DRAFT-1", {"reason": "Need abattoir slot date"})

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

    def test_meat_sales_lead_customer_booking_confirmation_route_records_event(self):
        service_result = {
            "success": True,
            "status": "ok",
            "records_customer_booking_confirmation": True,
        }

        with patch.object(
            sales_transaction_routes,
            "record_customer_booking_confirmation",
            return_value=(service_result, 201),
        ) as record_confirmation:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/customer-booking-confirmation",
                json={"customer_confirmation": "Yes, please book it."},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        record_confirmation.assert_called_once_with(
            "OSK-SALES-LEAD-1",
            {"customer_confirmation": "Yes, please book it."},
        )

    def test_meat_sales_lead_draft_order_route_creates_draft_order(self):
        service_result = {
            "success": True,
            "status": "draft_order_created",
            "order_id": "ORD-2026-TEST",
            "creates_order": True,
            "writes_farm_data": True,
        }

        with patch.object(
            sales_transaction_routes,
            "create_draft_order_from_sales_lead",
            return_value=(service_result, 201),
        ) as create_draft_order:
            response = self.client.post(
                "/api/sales/meat-leads/OSK-SALES-LEAD-1/draft-order",
                json={"created_by": "Farm App"},
            )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.get_json(), service_result)
        create_draft_order.assert_called_once_with("OSK-SALES-LEAD-1", {"created_by": "Farm App"})

    def test_sam_meat_backend_policy_route_reports_configuration(self):
        with patch.object(
            sales_transaction_routes,
            "sam_meat_webhook_policy",
            return_value={"enabled": False, "mode": "backend_native_sam_meat_chatwoot"},
        ):
            response = self.client.get("/api/sales/channels/chatwoot/sam-meat/policy")

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["policy"]["mode"], "backend_native_sam_meat_chatwoot")

    def test_sam_meat_backend_inbound_route_requires_auth(self):
        with patch.object(
            sales_transaction_routes,
            "authorize_sam_meat_webhook",
            return_value=(False, {"success": False, "status": "sam_meat_backend_webhook_auth_denied"}),
        ) as authorize:
            response = self.client.post("/api/sales/channels/chatwoot/sam-meat/inbound", json={})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "sam_meat_backend_webhook_auth_denied")
        authorize.assert_called_once()

    def test_sam_meat_backend_inbound_route_calls_runtime_after_auth(self):
        service_result = {
            "success": True,
            "status": "processed",
            "processed": True,
            "sent": False,
        }

        with patch.object(
            sales_transaction_routes,
            "authorize_sam_meat_webhook",
            return_value=(True, {}),
        ), patch.object(
            sales_transaction_routes,
            "handle_sam_meat_chatwoot_inbound",
            return_value=(service_result, 200),
        ) as handle_inbound:
            response = self.client.post(
                "/api/sales/channels/chatwoot/sam-meat/inbound",
                json={"event": "message_created"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        handle_inbound.assert_called_once_with({"event": "message_created"})


if __name__ == "__main__":
    unittest.main()
