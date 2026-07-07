import unittest
from unittest.mock import patch

from modules.orders import order_intake_service, order_intake_supabase_store


class OrderIntakeServiceTests(unittest.TestCase):
    def test_context_prefers_supabase_store_when_available(self):
        intake = {
            "Intake_ID": "INTAKE-1",
            "ConversationId": "1774",
            "Intake_Status": "Open",
            "Collection_Location": "Riversdale",
            "Customer_Phone": "082",
            "Order_Commitment": "Yes",
        }
        item = {
            "Intake_Item_ID": "ITEM-1",
            "Intake_ID": "INTAKE-1",
            "ConversationId": "1774",
            "Item_Key": "primary",
            "Quantity": 1,
            "Category": "Grower",
            "Weight_Range": "40_to_44_Kg",
            "Sex": "Any",
            "Intent_Type": "primary",
            "Status": "active",
        }

        with patch.object(order_intake_supabase_store, "available", return_value=True), \
             patch.object(order_intake_supabase_store, "find_active_intake_by_conversation", return_value=intake), \
             patch.object(order_intake_supabase_store, "get_items_for_intake", return_value=[item]):
            result = order_intake_service.get_intake_context("1774")

        self.assertTrue(result["success"])
        self.assertEqual(result["lookup_status"], "single_match")
        self.assertEqual(result["intake_id"], "INTAKE-1")
        self.assertEqual(result["items"][0]["item_key"], "primary")

    def test_update_creates_supabase_intake_and_item_without_sheet_append(self):
        cleaned = {
            "conversation_id": "1774",
            "account_id": "1",
            "contact_id": "2",
            "customer_name": "Customer",
            "customer_phone": "082",
            "customer_channel": "WhatsApp",
            "customer_language": "English",
            "updated_by": "Sam",
            "patch": {
                "collection_location": "Riversdale",
                "order_commitment": True,
            },
            "items": [{
                "item_key": "primary",
                "quantity": 1,
                "category": "Grower",
                "weight_range": "40_to_44_Kg",
                "sex": "Any",
                "intent_type": "primary",
                "status": "active",
            }],
        }
        inserted_intake = {}
        inserted_items = []
        state_updates = []

        def fake_insert_intake(row):
            inserted_intake.update(row)

        def fake_insert_item(row):
            inserted_items.append(row)

        def fake_find(conversation_id, statuses):
            return inserted_intake or None

        def fake_items(intake_id):
            return list(inserted_items)

        def fake_update(updates):
            state_updates.append(updates)
            inserted_intake.update(next(iter(updates.values())))
            return 1

        with patch.object(order_intake_supabase_store, "available", return_value=True), \
             patch.object(order_intake_service, "generate_intake_id", return_value="INTAKE-1"), \
             patch.object(order_intake_service, "generate_intake_item_id", return_value="ITEM-1"), \
             patch.object(order_intake_supabase_store, "find_active_intake_by_conversation", side_effect=fake_find), \
             patch.object(order_intake_supabase_store, "get_items_for_intake", side_effect=fake_items), \
             patch.object(order_intake_supabase_store, "insert_intake", side_effect=fake_insert_intake), \
             patch.object(order_intake_supabase_store, "insert_item", side_effect=fake_insert_item), \
             patch.object(order_intake_supabase_store, "update_intakes", side_effect=fake_update), \
             patch.object(order_intake_supabase_store, "update_items", return_value=0), \
             patch.object(order_intake_service, "append_row") as append_row:
            result = order_intake_service.update_intake_state(cleaned)

        append_row.assert_not_called()
        self.assertTrue(result["success"])
        self.assertEqual(result["intake_id"], "INTAKE-1")
        self.assertEqual(result["created_item_count"], 1)
        self.assertTrue(state_updates)

    def test_reset_updates_supabase_intake(self):
        intake = {
            "Intake_ID": "INTAKE-1",
            "ConversationId": "1774",
            "Intake_Status": "Open",
        }
        with patch.object(order_intake_supabase_store, "available", return_value=True), \
             patch.object(order_intake_supabase_store, "find_active_intake_by_conversation", return_value=intake), \
             patch.object(order_intake_supabase_store, "update_intakes", return_value=1) as update_intakes, \
             patch.object(order_intake_service, "batch_update_rows_by_id") as batch_update:
            result = order_intake_service.reset_intake("1774")

        self.assertTrue(result["closed"])
        update_intakes.assert_called_once()
        batch_update.assert_not_called()

    def test_supabase_json_fields_are_adapted_as_json_values(self):
        from psycopg.types.json import Json

        missing = order_intake_supabase_store._normalize_update_value(
            "missing_fields",
            "quantity, timing",
        )
        linked = order_intake_supabase_store._normalize_update_value(
            "linked_order_line_ids",
            "LINE-1, LINE-2",
        )

        self.assertIsInstance(missing, Json)
        self.assertIsInstance(linked, Json)


if __name__ == "__main__":
    unittest.main()
