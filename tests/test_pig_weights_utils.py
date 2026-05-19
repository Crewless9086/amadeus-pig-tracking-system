import unittest

from modules.pig_weights.pig_weights_utils import format_date_for_json


class PigWeightsUtilsTests(unittest.TestCase):
    def test_format_date_for_json_accepts_sheet_datetime_values(self):
        self.assertEqual(format_date_for_json("19 May 2026 04:20"), "2026-05-19")
        self.assertEqual(format_date_for_json("2026-05-19 04:20:00"), "2026-05-19")

    def test_format_date_for_json_accepts_full_month_names_from_sheet_formulas(self):
        self.assertEqual(format_date_for_json("9 June 2026"), "2026-06-09")
        self.assertEqual(format_date_for_json("10 September 2026"), "2026-09-10")


if __name__ == "__main__":
    unittest.main()
