import unittest
from datetime import date
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


class LitterAttentionSummaryTests(unittest.TestCase):
    def test_litter_attention_includes_sheet_attention_and_weaned_litters(self):
        overview_rows = [
            {
                "Litter_ID": "LIT-ATTN",
                "Sow_Tag_Number": "Sow 1",
                "Farrowing_Date": "01 May 2026",
                "Wean_Date": "",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Born alive count missing",
                "Active_Pig_Count": "8",
                "Weaned_Count": "",
                "Youngest_Age_Days": "18",
                "Oldest_Age_Days": "18",
            },
            {
                "Litter_ID": "LIT-WEANED",
                "Sow_Tag_Number": "Sow 2",
                "Farrowing_Date": "01 Apr 2026",
                "Wean_Date": "19 May 2026",
                "Litter_Status": "Weaned",
                "Needs_Attention": "No",
                "Active_Pig_Count": "7",
                "Weaned_Count": "7",
                "Youngest_Age_Days": "48",
                "Oldest_Age_Days": "48",
            },
            {
                "Litter_ID": "LIT-WEANED-DONE",
                "Litter_Status": "Weaned",
                "Needs_Attention": "No",
                "Active_Pig_Count": "6",
            },
        ]
        pig_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-WEANED",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Unknown",
            },
            {
                "Pig_ID": "PIG-2",
                "Litter_ID": "LIT-WEANED-DONE",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Sale",
            },
        ]

        with patch.object(pig_weights_service, "get_all_records", side_effect=[overview_rows, pig_rows, [], [], []]):
            result = pig_weights_service.get_litter_attention_summary()

        self.assertEqual(result["count"], 2)
        self.assertEqual([item["litter_id"] for item in result["items"]], ["LIT-ATTN", "LIT-WEANED"])
        self.assertEqual(result["items"][0]["reason"], "Born alive count missing")
        self.assertEqual(result["items"][1]["reason"], "Weaned - review purpose")
        self.assertEqual(result["items"][1]["wean_date"], "2026-05-19")

    def test_litter_attention_reason_falls_back_to_litter_counts(self):
        overview_rows = [
            {
                "Litter_ID": "LIT-MISSING-PIGS",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Total_Born": "7",
                "Born_Alive": "6",
                "Pig_Master_Row_Count": "5",
                "Tagged_Pig_Count": "5",
                "Active_Pig_Count": "5",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", side_effect=[overview_rows, [], [], [], []]):
            result = pig_weights_service.get_litter_attention_summary()

        self.assertEqual(result["items"][0]["reason"], "Linked pig records do not match born alive count")

    def test_litter_attention_actions_match_attention_reason(self):
        record_mismatch = pig_weights_service._build_litter_attention({
            "Litter_Status": "Weaned",
            "Needs_Attention": "Yes",
            "Attention_Reason": "Linked pig records do not match born alive count",
            "Active_Pig_Count": "5",
        })
        missing_tags = pig_weights_service._build_litter_attention({
            "Litter_Status": "Active",
            "Needs_Attention": "Yes",
            "Attention_Reason": "Piglets need tag numbers",
            "Active_Pig_Count": "6",
        })
        ready_to_wean = pig_weights_service._build_litter_attention({
            "Litter_ID": "LIT-ACTIVE",
            "Litter_Status": "Active",
            "Needs_Attention": "",
            "Active_Pig_Count": "6",
        })

        self.assertEqual(record_mismatch["action_type"], "reconcile_litter_records")
        self.assertIn("Reconcile Born Alive", record_mismatch["recommended_action"])
        self.assertEqual(missing_tags["action_type"], "assign_tag_numbers")
        self.assertIn("Assign tag numbers", missing_tags["recommended_action"])
        self.assertEqual(ready_to_wean["action_type"], "mark_weaned")

    def test_newborn_health_attention_takes_priority_before_tag_numbers(self):
        overview_rows = [
            {
                "Litter_ID": "LIT-NEWBORN",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Piglets need tag numbers",
                "Active_Pig_Count": "2",
            }
        ]
        pig_master_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-NEWBORN",
                "Status": "Active",
                "On_Farm": "Yes",
                "Earmarked": "",
                "Earmark_Date": "",
            }
        ]
        product_rows = [
            {
                "Product_ID": "PRD-001",
                "Product_Name": "Ecomectin 1%",
                "Product_Category": "Antiparasitic",
                "Is_Active": "Yes",
            },
            {
                "Product_ID": "PRD-002",
                "Product_Name": "Panacur 4%",
                "Product_Category": "Dewormer",
                "Is_Active": "Yes",
            },
        ]

        with patch.object(pig_weights_service, "get_all_records", side_effect=[overview_rows, [], pig_master_rows, [], product_rows]):
            result = pig_weights_service.get_litter_attention_summary()

        self.assertEqual(result["items"][0]["reason"], "Piglets need newborn health records")
        self.assertEqual(result["items"][0]["action_type"], "record_litter_newborn_health")

    def test_newborn_health_attention_does_not_require_earmarks(self):
        overview_rows = [
            {
                "Litter_ID": "LIT-TREATED",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Piglets need tag numbers",
                "Active_Pig_Count": "1",
                "Farrowing_Date": "01 May 2026",
            }
        ]
        pig_master_rows = [
            {
                "Pig_ID": "PIG-1",
                "Litter_ID": "LIT-TREATED",
                "Status": "Active",
                "On_Farm": "Yes",
                "Earmarked": "",
                "Earmark_Date": "",
            }
        ]
        medical_rows = [
            {"Pig_ID": "PIG-1", "Product_ID": "PRD-001"},
            {"Pig_ID": "PIG-1", "Product_ID": "PRD-002"},
        ]
        product_rows = [
            {
                "Product_ID": "PRD-001",
                "Product_Name": "Ecomectin 1%",
                "Product_Category": "Antiparasitic",
                "Is_Active": "Yes",
            },
            {
                "Product_ID": "PRD-002",
                "Product_Name": "Panacur 4%",
                "Product_Category": "Dewormer",
                "Is_Active": "Yes",
            },
        ]

        with patch.object(pig_weights_service, "get_all_records", side_effect=[overview_rows, [], pig_master_rows, medical_rows, product_rows]):
            result = pig_weights_service.get_litter_attention_summary(today=date(2026, 5, 2))

        self.assertEqual(result["count"], 0)

    def test_tag_number_attention_is_suppressed_until_wean_window(self):
        overview_rows = [
            {
                "Litter_ID": "LIT-EARLY",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Piglets need tag numbers",
                "Active_Pig_Count": "8",
                "Farrowing_Date": "01 May 2026",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", side_effect=[overview_rows, [], [], [], []]):
            result = pig_weights_service.get_litter_attention_summary(today=date(2026, 5, 20))

        self.assertEqual(result["count"], 0)

    def test_tag_number_attention_shows_from_three_days_before_estimated_wean(self):
        overview_rows = [
            {
                "Litter_ID": "LIT-DUE",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Attention_Reason": "Piglets need tag numbers",
                "Active_Pig_Count": "8",
                "Farrowing_Date": "01 May 2026",
            }
        ]

        with patch.object(pig_weights_service, "get_all_records", side_effect=[overview_rows, [], [], [], []]):
            result = pig_weights_service.get_litter_attention_summary(today=date(2026, 6, 2))

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["items"][0]["action_type"], "")
        self.assertEqual(result["items"][0]["reason"], "Piglets need tag numbers")
        self.assertEqual(result["items"][0]["estimated_wean_date"], "2026-06-05")
        self.assertEqual(result["items"][0]["wean_tag_attention_start_date"], "2026-06-02")

    def test_weaned_litter_only_reviews_purpose_when_active_piglets_have_unknown_purpose(self):
        pig_rows = [
            {
                "Pig_ID": "PIG-UNKNOWN",
                "Litter_ID": "LIT-UNKNOWN",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Unknown",
            },
            {
                "Pig_ID": "PIG-SALE",
                "Litter_ID": "LIT-DONE",
                "Status": "Active",
                "On_Farm": "Yes",
                "Purpose": "Sale",
            },
        ]

        self.assertTrue(pig_weights_service._litter_needs_purpose_review("LIT-UNKNOWN", pig_rows))
        self.assertFalse(pig_weights_service._litter_needs_purpose_review("LIT-DONE", pig_rows))

    def test_litter_attention_limits_returned_items_but_keeps_total_count(self):
        overview_rows = [
            {
                "Litter_ID": f"LIT-{i}",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Active_Pig_Count": "1",
            }
            for i in range(7)
        ]

        with patch.object(pig_weights_service, "get_all_records", side_effect=[overview_rows, [], [], [], []]):
            result = pig_weights_service.get_litter_attention_summary(limit=3)

        self.assertEqual(result["count"], 7)
        self.assertEqual(len(result["items"]), 3)


if __name__ == "__main__":
    unittest.main()
