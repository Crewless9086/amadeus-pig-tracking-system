import unittest
from datetime import date, datetime
from unittest.mock import patch

from modules.pig_weights import pig_weights_service
from modules.pig_weights import farm_supabase_read_service


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
    def test_supabase_dashboard_summary_counts_current_state_and_monthly_exits(self):
        rows = [
            {
                "pig_id": "PIG-ACTIVE",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Grower",
                "current_weight_kg": 61,
                "exit_date": None,
                "exit_reason": "",
            },
            {
                "pig_id": "PIG-LIVE",
                "status": "Sold",
                "on_farm": False,
                "animal_type": "Finisher",
                "current_weight_kg": 82,
                "exit_date": date(2026, 5, 2),
                "exit_reason": "Sold",
            },
            {
                "pig_id": "PIG-ABATTOIR",
                "status": "Slaughtered",
                "on_farm": False,
                "animal_type": "Finisher",
                "current_weight_kg": 90,
                "exit_date": date(2026, 5, 3),
                "exit_reason": "Sold to Abattoir",
            },
            {
                "pig_id": "PIG-MEAT",
                "status": "Sold",
                "on_farm": False,
                "animal_type": "Finisher",
                "current_weight_kg": 78,
                "exit_date": date(2026, 5, 4),
                "exit_reason": "Meat Sale",
            },
            {
                "pig_id": "PIG-DEAD",
                "status": "Dead",
                "on_farm": False,
                "animal_type": "Piglet",
                "current_weight_kg": None,
                "exit_date": date(2026, 5, 5),
                "exit_reason": "Died",
            },
        ]

        with patch.object(farm_supabase_read_service, "_dashboard_rows", return_value=rows), \
             patch.object(farm_supabase_read_service, "_reserved_pig_count", return_value=2):
            summary = farm_supabase_read_service.get_dashboard_summary(today=date(2026, 5, 20))

        self.assertEqual(summary["source"], "supabase_canonical")
        self.assertEqual(summary["on_farm_pigs"], 1)
        self.assertEqual(summary["growers"], 1)
        self.assertEqual(summary["available_for_sale_pigs"], 1)
        self.assertEqual(summary["reserved_pigs"], 2)
        self.assertEqual(summary["sold_this_month"], 3)
        self.assertEqual(summary["livestock_sold_this_month"], 1)
        self.assertEqual(summary["slaughter_sold_this_month"], 1)
        self.assertEqual(summary["meat_sold_this_month"], 1)
        self.assertEqual(summary["lifecycle_outcomes_this_month"], 4)
        self.assertEqual(summary["lifecycle_dead_this_month"], 1)

    def test_dashboard_summary_prefers_supabase_and_does_not_read_sheets(self):
        transaction_summary = {
            "configured": True,
            "status": "ok",
            "streams": {"livestock": {"transaction_count": 1, "net_total": 1200.0}},
            "totals": {"transaction_count": 1, "net_total": 1200.0},
        }
        supabase_summary = {
            "source": "supabase_canonical",
            "on_farm_pigs": 1,
            "boars": 0,
            "sows": 0,
            "gilts": 0,
            "piglets": 0,
            "weaners": 0,
            "growers": 1,
            "finishers": 0,
            "sold_this_month": 0,
            "livestock_sold_this_month": 0,
            "slaughter_sold_this_month": 0,
            "meat_sold_this_month": 0,
            "pig_exit_sold_this_month": 0,
            "pig_exit_livestock_sold_this_month": 0,
            "pig_exit_slaughter_sold_this_month": 0,
            "pig_exit_meat_sold_this_month": 0,
            "lifecycle_outcomes_this_month": 0,
            "lifecycle_sold_this_month": 0,
            "lifecycle_slaughtered_this_month": 0,
            "lifecycle_dead_this_month": 0,
            "lifecycle_removed_this_month": 0,
            "lifecycle_other_this_month": 0,
            "available_for_sale_pigs": 1,
            "reserved_pigs": 0,
            "withdrawal_hold_pigs": 0,
        }

        with patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(pig_weights_service.farm_supabase_read_service, "get_dashboard_summary", return_value=supabase_summary), \
             patch.object(pig_weights_service, "get_all_records", side_effect=AssertionError("Sheets should not be read")), \
             patch.object(pig_weights_service, "datetime", FixedDateTime), \
             patch.object(pig_weights_service, "get_monthly_sales_transaction_summary", return_value=(transaction_summary, 200)):
            summary = pig_weights_service.get_dashboard_summary()

        self.assertEqual(summary["source"], "supabase_canonical")
        self.assertEqual(summary["on_farm_pigs"], 1)
        self.assertEqual(summary["sales_transaction_summary_status"], "ok")
        self.assertEqual(summary["sales_transaction_count_this_month"], 1)

    def test_dashboard_summary_splits_monthly_sales_by_stream(self):
        with patch.object(pig_weights_service, "get_all_records", side_effect=dashboard_records), \
             patch.object(pig_weights_service.farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
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
