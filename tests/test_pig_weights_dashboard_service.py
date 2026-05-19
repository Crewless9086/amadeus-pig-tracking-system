import unittest
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


class LitterAttentionSummaryTests(unittest.TestCase):
    def test_litter_attention_includes_sheet_attention_and_weaned_litters(self):
        rows = [
            {
                "Litter_ID": "LIT-ATTN",
                "Sow_Tag_Number": "Sow 1",
                "Farrowing_Date": "01 May 2026",
                "Wean_Date": "",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
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
                "Litter_ID": "LIT-OK",
                "Litter_Status": "Active",
                "Needs_Attention": "No",
                "Active_Pig_Count": "6",
            },
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=rows):
            result = pig_weights_service.get_litter_attention_summary()

        self.assertEqual(result["count"], 2)
        self.assertEqual([item["litter_id"] for item in result["items"]], ["LIT-ATTN", "LIT-WEANED"])
        self.assertEqual(result["items"][0]["reason"], "Needs attention")
        self.assertEqual(result["items"][1]["reason"], "Weaned - review purpose")
        self.assertEqual(result["items"][1]["wean_date"], "2026-05-19")

    def test_litter_attention_limits_returned_items_but_keeps_total_count(self):
        rows = [
            {
                "Litter_ID": f"LIT-{i}",
                "Litter_Status": "Active",
                "Needs_Attention": "Yes",
                "Active_Pig_Count": "1",
            }
            for i in range(7)
        ]

        with patch.object(pig_weights_service, "get_all_records", return_value=rows):
            result = pig_weights_service.get_litter_attention_summary(limit=3)

        self.assertEqual(result["count"], 7)
        self.assertEqual(len(result["items"]), 3)


if __name__ == "__main__":
    unittest.main()
