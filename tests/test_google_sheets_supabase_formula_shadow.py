import unittest

from scripts import google_sheets_supabase_formula_shadow as shadow


class GoogleSheetsSupabaseFormulaShadowTests(unittest.TestCase):
    def test_summarize_sheet_formulas_counts_formula_outputs(self):
        sheet_rows = {
            "PIG_OVERVIEW": [
                {
                    "Pig_ID": "PIG-1",
                    "Status": "Active",
                    "On_Farm": "Yes",
                    "Animal_Type": "Grower",
                    "Current_Pen_ID": "PEN-1",
                },
                {
                    "Pig_ID": "PIG-2",
                    "Status": "Sold",
                    "On_Farm": "No",
                    "Animal_Type": "Finisher",
                    "Current_Pen_ID": "PEN-2",
                },
            ],
            "SALES_AVAILABILITY": [
                {"Available_For_Sale": "Yes", "Sale_Category": "Meat"},
                {"Available_For_Sale": "No", "Sale_Category": "Hold"},
            ],
            "SALES_STOCK_SUMMARY": [{"Sale_Category": "Meat"}],
            "SALES_STOCK_TOTALS": [{"Sale_Category": "Meat"}],
            "LITTER_OVERVIEW": [
                {"Needs_Attention": "Yes", "Litter_Status": "Active"},
                {"Needs_Attention": "No", "Litter_Status": "Weaned"},
            ],
            "MATING_OVERVIEW": [{"Mating_Status": "Open", "Outcome": ""}],
        }

        summary = shadow.summarize_sheet_formulas(sheet_rows)

        self.assertEqual(summary["pig_overview"]["row_count"], 2)
        self.assertEqual(summary["pig_overview"]["active_on_farm_count"], 1)
        self.assertEqual(summary["pig_overview"]["animal_type_counts"]["Grower"], 1)
        self.assertEqual(summary["sales_availability"]["available_for_sale_count"], 1)
        self.assertEqual(summary["litter_overview"]["needs_attention_count"], 1)

    def test_build_shadow_report_compares_matching_core_counts(self):
        sheet_rows = {
            "PIG_OVERVIEW": [
                {"Status": "Active", "On_Farm": "Yes", "Animal_Type": "Grower", "Current_Pen_ID": "PEN-1"},
            ],
            "SALES_AVAILABILITY": [],
            "SALES_STOCK_SUMMARY": [],
            "SALES_STOCK_TOTALS": [],
            "LITTER_OVERVIEW": [{"Litter_Status": "Active"}],
            "MATING_OVERVIEW": [{"Outcome": "Farrowed"}],
        }
        supabase_summary = {
            "pig_overview_candidate": {
                "row_count": 1,
                "active_on_farm_count": 1,
                "animal_type_counts": {"Grower": 1},
                "status_counts": {"Active": 1},
                "on_farm_counts": {"Yes": 1},
            },
            "litter_overview_candidate": {"row_count": 1},
            "mating_overview_candidate": {"row_count": 1},
        }

        report = shadow.build_shadow_report(sheet_rows, supabase_summary=supabase_summary)

        self.assertTrue(report["success"])
        self.assertFalse(report["writes_to_supabase"])
        self.assertFalse(report["writes_to_sheets"])
        self.assertTrue(report["all_compared_metrics_match"])

    def test_build_shadow_report_marks_mismatch(self):
        sheet_rows = {
            "PIG_OVERVIEW": [{"Status": "Active", "On_Farm": "Yes", "Animal_Type": "Grower"}],
            "SALES_AVAILABILITY": [],
            "SALES_STOCK_SUMMARY": [],
            "SALES_STOCK_TOTALS": [],
            "LITTER_OVERVIEW": [],
            "MATING_OVERVIEW": [],
        }
        supabase_summary = {
            "pig_overview_candidate": {
                "row_count": 0,
                "active_on_farm_count": 0,
                "animal_type_counts": {},
                "status_counts": {},
                "on_farm_counts": {},
            },
            "litter_overview_candidate": {"row_count": 0},
            "mating_overview_candidate": {"row_count": 0},
        }

        report = shadow.build_shadow_report(sheet_rows, supabase_summary=supabase_summary)

        self.assertFalse(report["all_compared_metrics_match"])
        self.assertFalse(report["comparisons"][0]["match"])


if __name__ == "__main__":
    unittest.main()
