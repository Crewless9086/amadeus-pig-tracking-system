import unittest
from datetime import datetime
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


class FixedDateTime:
    @classmethod
    def now(cls):
        return datetime(2026, 5, 20)


def dashboard_records(sheet_name):
    data = {
        "PIG_OVERVIEW": [
            {
                "Pig_ID": "PIG-ACTIVE",
                "Status": "Active",
                "On_Farm": "Yes",
                "Animal_Type": "Grower",
                "Reserved_Status": "",
                "Withdrawal_Clear": "Yes",
            },
        ],
        "SALES_AVAILABILITY": [
            {"Available_For_Sale": "Yes"},
        ],
        "PIG_MASTER": [
            {
                "Pig_ID": "PIG-LIVE",
                "Status": "Sold",
                "Exit_Date": "2 May 2026",
                "Exit_Reason": "Sold",
            },
            {
                "Pig_ID": "PIG-ABATTOIR",
                "Status": "Slaughtered",
                "Exit_Date": "3 May 2026",
                "Exit_Reason": "Sold to Abattoir",
            },
            {
                "Pig_ID": "PIG-MEAT",
                "Status": "Sold",
                "Exit_Date": "4 May 2026",
                "Exit_Reason": "Meat Sale",
            },
            {
                "Pig_ID": "PIG-OLD",
                "Status": "Sold",
                "Exit_Date": "29 Apr 2026",
                "Exit_Reason": "Sold",
            },
            {
                "Pig_ID": "PIG-DEAD",
                "Status": "Dead",
                "Exit_Date": "5 May 2026",
                "Exit_Reason": "Died",
            },
            {
                "Pig_ID": "PIG-REMOVED",
                "Status": "Removed",
                "Exit_Date": "6 May 2026",
                "Exit_Reason": "Removed",
            },
        ],
    }
    return data[sheet_name]


class DashboardSummaryServiceTests(unittest.TestCase):
    def test_dashboard_summary_splits_monthly_sales_by_stream(self):
        with patch.object(pig_weights_service, "get_all_records", side_effect=dashboard_records), \
             patch.object(pig_weights_service, "datetime", FixedDateTime), \
             patch.object(pig_weights_service, "get_monthly_sales_transaction_summary", return_value=({
                 "configured": False,
                 "status": "not_configured",
                 "streams": {},
                 "totals": {},
             }, 503)):
            summary = pig_weights_service.get_dashboard_summary()

        self.assertEqual(summary["sold_this_month"], 3)
        self.assertEqual(summary["livestock_sold_this_month"], 1)
        self.assertEqual(summary["slaughter_sold_this_month"], 1)
        self.assertEqual(summary["meat_sold_this_month"], 1)
        self.assertEqual(summary["lifecycle_outcomes_this_month"], 5)
        self.assertEqual(summary["lifecycle_sold_this_month"], 2)
        self.assertEqual(summary["lifecycle_slaughtered_this_month"], 1)
        self.assertEqual(summary["lifecycle_dead_this_month"], 1)
        self.assertEqual(summary["lifecycle_removed_this_month"], 1)
        self.assertEqual(summary["slaughter_sales_this_month"], 0)
        self.assertEqual(summary["slaughter_sales_value_this_month"], 0.0)

    def test_dashboard_summary_includes_supabase_sales_transaction_values(self):
        transaction_summary = {
            "configured": True,
            "status": "ok",
            "streams": {
                "livestock": {"transaction_count": 0, "net_total": 0.0},
                "slaughter": {"transaction_count": 1, "net_total": 2400.0},
                "meat": {"transaction_count": 0, "net_total": 0.0},
            },
            "totals": {"transaction_count": 1, "net_total": 2400.0},
        }

        with patch.object(pig_weights_service, "get_all_records", side_effect=dashboard_records), \
             patch.object(pig_weights_service, "datetime", FixedDateTime), \
             patch.object(pig_weights_service, "get_monthly_sales_transaction_summary", return_value=(transaction_summary, 200)):
            summary = pig_weights_service.get_dashboard_summary()

        self.assertTrue(summary["sales_transaction_summary_configured"])
        self.assertEqual(summary["sales_transaction_summary_status"], "ok")
        self.assertEqual(summary["sales_transaction_count_this_month"], 1)
        self.assertEqual(summary["sales_transaction_value_this_month"], 2400.0)
        self.assertEqual(summary["slaughter_sales_this_month"], 1)
        self.assertEqual(summary["slaughter_sales_value_this_month"], 2400.0)


if __name__ == "__main__":
    unittest.main()
