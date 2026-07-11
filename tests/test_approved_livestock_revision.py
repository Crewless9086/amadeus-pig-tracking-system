import unittest
from unittest.mock import patch

from app import app
from modules.documents import quote_service
from modules.orders import approved_revision_service, order_routes
from modules.oom_sakkie import routes as oom_routes


def approved_detail():
    return {
        "order": {
            "order_id": "ORD-2026-12BCCC",
            "order_status": "Approved",
            "approval_status": "Approved",
            "customer_name": "Michaels",
            "payment_method": "Cash",
            "collection_location": "Albertinia",
            "requested_quantity": 5,
            "conversation_id": "1774",
        },
        "lines": [
            {
                "order_line_id": f"OL-{idx}",
                "pig_id": f"PIG-{idx}",
                "sale_category": "Young Piglets",
                "weight_band": "7_to_9_Kg",
                "sex": "Male",
                "unit_price": 500,
                "line_status": "Reserved",
            }
            for idx in range(1, 6)
        ],
    }


def revision_payload():
    return {
        "idempotency_key": "michaels-5-piglets-tag-104",
        "changed_by": "Oom Sakkie",
        "revision_date": "2026-07-11",
        "perform_farm_corrections": True,
        "order_updates": {
            "requested_quantity": 5,
            "requested_category": "Piglet",
            "requested_weight_range": "7_to_9_Kg",
            "requested_sex": "Any",
            "collection_location": "Albertinia",
            "notes": "Michaels changed approved order to 5 piglets. Tag 104 weighed 8.4kg and was corrected to Sale.",
        },
        "requested_items": [{
            "request_item_key": "primary_1",
            "category": "Piglet",
            "weight_range": "7_to_9_Kg",
            "sex": "Any",
            "quantity": 5,
            "notes": "Michaels approved-order revision.",
        }],
        "farm_corrections": [{
            "pig_id": "PIG-104",
            "tag_number": "104",
            "weight_date": "2026-07-11",
            "weight_kg": 8.4,
            "purpose": "Sale",
            "purpose_reason": "Selected for approved Michaels order.",
        }],
        "movement_form_data": {"movement_reason": "Sale / transfer"},
        "conversation_id": "1774",
    }


class ApprovedLivestockRevisionTests(unittest.TestCase):
    def setUp(self):
        app.testing = True
        self.client = app.test_client()

    def test_quote_readiness_can_be_explicitly_allowed_for_approved_revision(self):
        with patch.object(quote_service, "_get_quote_order_detail", return_value=approved_detail()):
            normal = quote_service.get_quote_readiness("ORD-2026-12BCCC")
            revision = quote_service.get_quote_readiness(
                "ORD-2026-12BCCC",
                allow_approved_revision=True,
            )

        self.assertIn("draft_status", normal["missing_fields"])
        self.assertTrue(revision["quote_ready"])
        self.assertNotIn("draft_status", revision["missing_fields"])

    def test_revision_orchestrates_lines_reservation_documents_owner_paperwork_and_quote_prepare(self):
        payload = revision_payload()

        with patch.object(approved_revision_service, "get_order_detail", return_value=approved_detail()), \
             patch.object(approved_revision_service, "create_weight_entry", return_value=({"success": True, "saved": {"pig_id": "PIG-104"}}, 201)) as weight, \
             patch.object(approved_revision_service, "apply_purpose_review_queue_decisions", return_value=({"success": True, "approved_count": 1}, 200)) as purpose, \
             patch.object(approved_revision_service, "update_order", return_value={"success": True, "updated_fields": ["requested_quantity"]}) as update, \
             patch.object(approved_revision_service, "sync_order_lines_from_request", return_value={"success": True, "matched_total": 5}) as sync, \
             patch.object(approved_revision_service, "reserve_order_lines", return_value={"success": True, "reserved_pig_count": 5}) as reserve, \
             patch.object(approved_revision_service, "get_order_documents", return_value=[]), \
             patch.object(approved_revision_service, "auto_generate_quote_if_ready", return_value={"success": True, "generated": True, "document": {"document_id": "DOC-Q"}}) as quote, \
             patch.object(approved_revision_service, "generate_loading_sheet_for_order", return_value={"success": True, "document_id": "DOC-L"}) as load, \
             patch.object(approved_revision_service, "generate_removal_certificate_for_order", return_value={"success": True, "document_id": "DOC-R"}) as removal, \
             patch.object(approved_revision_service, "generate_health_declaration_for_order", return_value={"success": True, "document_id": "DOC-H"}) as health, \
             patch.object(approved_revision_service, "send_loading_sheet_to_owner_telegram", return_value={"success": True}) as telegram, \
             patch("modules.orders.order_routes._prepare_latest_quote_send_context", return_value={"success": True, "send_ready": True}):
            result = approved_revision_service.revise_approved_livestock_order("ORD-2026-12BCCC", payload)

        self.assertTrue(result["success"])
        self.assertFalse(result["operations"]["customer_quote"]["sent"])
        self.assertEqual(result["operations"]["reservation"]["reserved_pig_count"], 5)
        self.assertEqual(telegram.call_count, 3)
        weight.assert_called_once()
        purpose.assert_called_once()
        update.assert_called_once()
        reserve.assert_called_once_with("ORD-2026-12BCCC")
        sync_payload = sync.call_args.args[1]
        self.assertTrue(sync_payload["allow_approved_revision"])
        revision_fingerprint = result["revision_fingerprint"]
        quote.assert_called_once_with(
            "ORD-2026-12BCCC",
            created_by="Oom Sakkie",
            allow_approved_revision=True,
            revision_fingerprint=revision_fingerprint,
        )
        load.assert_called_once_with("ORD-2026-12BCCC", created_by="Oom Sakkie", revision_fingerprint=revision_fingerprint)
        removal.assert_called_once()
        health.assert_called_once()

    def test_revision_reuses_existing_revision_documents_instead_of_generating_duplicates(self):
        existing = [{
            "Document_ID": "DOC-LATEST",
            "Document_Type": "Loading Sheet",
            "Document_Status": "Generated",
            "Version": "4",
            "Notes": '{"revision_fingerprint":"abc123"}',
        }]

        with patch.object(approved_revision_service, "get_order_documents", return_value=existing), \
             patch.object(approved_revision_service, "generate_loading_sheet_for_order") as generate:
            result = approved_revision_service._ensure_document(
                "ORD-2026-12BCCC",
                "Loading Sheet",
                "abc123",
                generate,
            )

        self.assertTrue(result["skipped"])
        self.assertEqual(result["reason"], "latest_revision_document_current")
        generate.assert_not_called()

    def test_order_route_exposes_approved_revision_action(self):
        service_result = {"success": True, "action": "revise_approved_livestock_order"}
        with patch.object(order_routes, "revise_approved_livestock_order", return_value=service_result) as service:
            response = self.client.post(
                "/api/orders/ORD-2026-12BCCC/approved-livestock-revision",
                json=revision_payload(),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), service_result)
        service.assert_called_once()

    def test_oom_sakkie_route_exposes_action_alias_without_customer_send(self):
        service_result = {"success": True, "action": "revise_approved_livestock_order"}
        with patch.object(oom_routes, "is_review_request_allowed", return_value=True), \
             patch.object(oom_routes, "revise_approved_livestock_order", return_value=service_result) as service:
            response = self.client.post(
                "/api/oom-sakkie/orders/ORD-2026-12BCCC/approved-livestock-revision",
                json=revision_payload(),
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertTrue(payload["oom_sakkie_action"])
        service.assert_called_once()


if __name__ == "__main__":
    unittest.main()
