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
        ],
    }
    return data[sheet_name]


class DashboardSummaryServiceTests(unittest.TestCase):
    def test_dashboard_summary_splits_monthly_sales_by_stream(self):
        with patch.object(pig_weights_service, "get_all_records", side_effect=dashboard_records), \
             patch.object(pig_weights_service, "datetime", FixedDateTime):
            summary = pig_weights_service.get_dashboard_summary()

        self.assertEqual(summary["sold_this_month"], 3)
        self.assertEqual(summary["livestock_sold_this_month"], 1)
        self.assertEqual(summary["slaughter_sold_this_month"], 1)
        self.assertEqual(summary["meat_sold_this_month"], 1)


if __name__ == "__main__":
    unittest.main()
