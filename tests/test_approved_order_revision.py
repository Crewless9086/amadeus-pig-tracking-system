import unittest
from unittest.mock import Mock, patch

from modules.orders import approved_order_revision


def approved_detail(line_count=4):
    lines = []
    for index in range(line_count):
        lines.append({
            "order_line_id": f"OL-{index}",
            "order_id": "ORD-2026-12BCCC",
            "pig_id": f"PIG-{index}",
            "sale_category": "Young Piglets",
            "weight_band": "7_to_9_Kg",
            "sex": "Any",
            "line_status": "Reserved",
            "reserved_status": "Reserved",
            "request_item_key": "michaels-piglets",
        })
    return {
        "order": {
            "order_id": "ORD-2026-12BCCC",
            "customer_name": "Michaels",
            "order_status": "Approved",
            "approval_status": "Approved",
            "payment_method": "Cash",
            "collection_location": "Riversdale",
            "conversation_id": "2401",
        },
        "lines": lines,
    }


def revision_payload(quantity=5):
    return {
        "changed_by": "Oom Sakkie",
        "requested_items": [{
            "request_item_key": "michaels-piglets",
            "category": "Piglet",
            "weight_range": "7_to_9_Kg",
            "sex": "Any",
            "quantity": quantity,
            "notes": "Michaels changed order to 5 piglets.",
        }],
        "order_updates": {
            "requested_quantity": quantity,
            "requested_category": "Piglet",
            "requested_weight_range": "7_to_9_Kg",
            "requested_sex": "Any",
        },
        "sale_readiness_correction": {
            "pig_id": "PIG-104",
            "tag_number": "104",
            "weight_kg": 8.4,
            "purpose": "Sale",
            "notes": "Fresh owner correction made tag 104 sale-ready.",
        },
        "send_owner_telegram": True,
        "prepare_customer_quote": True,
    }


class ApprovedOrderRevisionTests(unittest.TestCase):
    def test_revision_updates_lines_reserves_documents_and_prepares_quote_without_customer_send(self):
        generators = {
            "quote_generator": lambda order_id, created_by: {
                "success": True,
                "document": {"document_id": "DOC-Q", "document_ref": "Q-2026-12BCCC-V2"},
            },
            "loading_sheet_generator": lambda order_id, created_by: {
                "success": True,
                "document_id": "DOC-L",
                "document_ref": "LOAD-2026-12BCCC-V2",
            },
            "removal_certificate_generator": lambda order_id, form_data, created_by: {
                "success": True,
                "document_id": "DOC-R",
                "document_ref": "REM-2026-12BCCC-V2",
            },
            "health_declaration_generator": lambda order_id, form_data, created_by: {
                "success": True,
                "document_id": "DOC-H",
                "document_ref": "HEALTH-2026-12BCCC-V2",
            },
            "quote_send_preparer": lambda order_id, conversation_id, requested_by: {
                "success": True,
                "send_ready": True,
                "document": {"document_id": "DOC-Q"},
            },
            "document_lookup": lambda order_id: [],
        }
        with patch.object(approved_order_revision, "get_order_detail", side_effect=[approved_detail(4), approved_detail(4)]), \
             patch.object(approved_order_revision, "update_order", return_value={"success": True}) as update_order, \
             patch.object(approved_order_revision, "sync_order_lines_from_request", return_value={"success": True, "fulfillment_status": "complete"}) as sync_lines, \
             patch.object(approved_order_revision, "reserve_order_lines", return_value={"success": True, "reserved_pig_count": 5}) as reserve, \
             patch.object(approved_order_revision, "send_loading_sheet_to_owner_telegram", return_value={"success": True}) as send_owner, \
             patch.object(approved_order_revision, "write_order_status_log") as status_log, \
             patch.object(approved_order_revision, "_revision_fingerprint_already_logged", return_value=False):
            result = approved_order_revision.revise_approved_livestock_order(
                "ORD-2026-12BCCC",
                revision_payload(5),
                **generators,
            )

        self.assertTrue(result["success"])
        self.assertFalse(result["customer_quote_send"]["sent"])
        self.assertTrue(result["customer_quote_send"]["owner_instruction_required"])
        self.assertEqual(result["sale_readiness_correction"]["tag_number"], "104")
        self.assertEqual(result["sale_readiness_correction"]["weight_kg"], 8.4)
        update_order.assert_called_once()
        sync_lines.assert_called_once()
        self.assertEqual(sync_lines.call_args.args[1]["allowed_order_statuses"], ("Approved",))
        reserve.assert_called_once_with("ORD-2026-12BCCC")
        self.assertEqual(send_owner.call_count, 4)
        status_log.assert_called_once()

    def test_repeated_revision_skips_matching_line_sync_and_documents(self):
        generators = {
            "quote_generator": Mock(),
            "loading_sheet_generator": Mock(),
            "removal_certificate_generator": Mock(),
            "health_declaration_generator": Mock(),
            "quote_send_preparer": lambda order_id, conversation_id, requested_by: {"success": True},
            "document_lookup": lambda order_id: [],
        }
        with patch.object(approved_order_revision, "get_order_detail", side_effect=[approved_detail(5), approved_detail(5)]), \
             patch.object(approved_order_revision, "update_order", return_value={"success": True}), \
             patch.object(approved_order_revision, "sync_order_lines_from_request") as sync_lines, \
             patch.object(approved_order_revision, "reserve_order_lines", return_value={"success": True, "reserved_pig_count": 5}), \
             patch.object(approved_order_revision, "send_loading_sheet_to_owner_telegram") as send_owner, \
             patch.object(approved_order_revision, "write_order_status_log"), \
             patch.object(approved_order_revision, "_revision_fingerprint_already_logged", return_value=True):
            result = approved_order_revision.revise_approved_livestock_order(
                "ORD-2026-12BCCC",
                revision_payload(5),
                **generators,
            )

        self.assertTrue(result["already_applied"])
        sync_lines.assert_not_called()
        generators["quote_generator"].assert_not_called()
        generators["loading_sheet_generator"].assert_not_called()
        send_owner.assert_not_called()
        self.assertTrue(all(item["skipped"] for item in result["documents"]))


if __name__ == "__main__":
    unittest.main()
