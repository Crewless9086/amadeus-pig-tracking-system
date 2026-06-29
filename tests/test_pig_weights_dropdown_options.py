import unittest
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


PIG_ROWS = [
    {
        "Pig_ID": "PIG-SOW",
        "Tag_Number": "S5",
        "Sex": "Female",
        "Status": "Active",
        "On_Farm": "Yes",
        "Purpose": "Breeding",
        "Current_Pen_ID": "PEN-001",
    },
    {
        "Pig_ID": "PIG-BOAR",
        "Tag_Number": "B1",
        "Sex": "Male",
        "Status": "Active",
        "On_Farm": "Yes",
        "Purpose": "Breeding",
        "Current_Pen_ID": "PEN-002",
    },
]

PEN_ROWS = [
    {"Pen_ID": "PEN-001", "Pen_Name": "Kraam Saal 01", "Pen_Type": "Farrowing"},
    {"Pen_ID": "PEN-002", "Pen_Name": "Boar Camp", "Pen_Type": "Boar"},
]


def fake_get_all_records(sheet_name):
    if sheet_name == "PIG_OVERVIEW":
        return PIG_ROWS
    if sheet_name == "PEN_REGISTER":
        return PEN_ROWS
    return []


class PigDropdownOptionTests(unittest.TestCase):
    def setUp(self):
        self.supabase_availability_patch = patch.object(
            pig_weights_service.farm_supabase_read_service,
            "farm_supabase_reads_available",
            return_value=False,
        )
        self.supabase_availability_patch.start()

    def tearDown(self):
        self.supabase_availability_patch.stop()

    def test_parent_options_include_current_pen_name(self):
        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            options = pig_weights_service.get_parent_options()

        sow = next(item for item in options["mothers"] if item["pig_id"] == "PIG-SOW")
        boar = next(item for item in options["fathers"] if item["pig_id"] == "PIG-BOAR")

        self.assertEqual(sow["current_pen_name"], "Kraam Saal 01")
        self.assertEqual(boar["current_pen_name"], "Boar Camp")

    def test_active_pigs_include_current_pen_name(self):
        with patch.object(pig_weights_service, "get_all_records", side_effect=fake_get_all_records):
            pigs = pig_weights_service.get_active_pigs()

        by_id = {pig["pig_id"]: pig for pig in pigs}

        self.assertEqual(by_id["PIG-SOW"]["current_pen_name"], "Kraam Saal 01")
        self.assertEqual(by_id["PIG-BOAR"]["current_pen_name"], "Boar Camp")


if __name__ == "__main__":
    unittest.main()
