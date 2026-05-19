import unittest
from datetime import date
from unittest.mock import patch

from modules.pig_weights import pig_weights_service


PIG_MASTER_HEADERS = [
    "Pig_ID",
    "Tag_Number",
    "Pig_Name",
    "Status",
    "On_Farm",
    "Animal_Type",
    "Sex",
    "Date_Of_Birth",
    "Birth_Month",
    "Birth_Year",
    "Breed_Type",
    "Colour_Markings",
    "Litter_ID",
    "Litter_Size_Born",
    "Litter_Size_Weaned",
    "Mother_Pig_ID",
    "Father_Pig_ID",
    "Mother_Tag_Number",
    "Father_Tag_Number",
    "Maternal_Line",
    "Paternal_Line",
    "Purpose",
    "Current_Stage",
    "Current_Pen_ID",
    "Source",
    "Acquisition_Date",
    "Birth_Weight_Kg",
    "Wean_Date",
    "Wean_Weight_Kg",
    "Exit_Date",
    "Exit_Reason",
    "Exit_Order_ID",
    "Carcass_Weight_Kg",
    "General_Notes",
    "Created_At",
    "Updated_At",
]


class LitterPigletCreationTests(unittest.TestCase):
    def test_litter_generated_piglets_default_purpose_unknown(self):
        with patch.object(pig_weights_service, "get_all_records", return_value=[]), \
             patch.object(pig_weights_service, "generate_pig_id", side_effect=["PIG-1", "PIG-2"]), \
             patch.object(pig_weights_service, "append_row") as append_row:

            created_count = pig_weights_service._create_pig_rows_for_litter(
                litter_id="LIT-1",
                mother_pig_id="PIG-MOTHER",
                father_pig_id="PIG-FATHER",
                mother_tag="M1",
                father_tag="B1",
                farrowing_date=date(2026, 5, 19),
                total_born=2,
                current_pen_id="PEN-001",
            )

        self.assertEqual(created_count, 2)
        self.assertEqual(append_row.call_count, 2)

        first_row = append_row.call_args_list[0].args[1]
        by_header = dict(zip(PIG_MASTER_HEADERS, first_row))
        self.assertEqual(by_header["Purpose"], "Unknown")
        self.assertEqual(by_header["Animal_Type"], "Piglet")
        self.assertEqual(by_header["Status"], "Active")
        self.assertEqual(by_header["On_Farm"], "Yes")
        self.assertEqual(by_header["Source"], "Born_on_Farm")

    def test_litter_generated_piglets_are_not_duplicated_for_existing_litter(self):
        existing_rows = [{"Litter_ID": "LIT-1"}]

        with patch.object(pig_weights_service, "get_all_records", return_value=existing_rows), \
             patch.object(pig_weights_service, "append_row") as append_row:

            created_count = pig_weights_service._create_pig_rows_for_litter(
                litter_id="LIT-1",
                mother_pig_id="PIG-MOTHER",
                father_pig_id="PIG-FATHER",
                mother_tag="M1",
                father_tag="B1",
                farrowing_date=date(2026, 5, 19),
                total_born=2,
                current_pen_id="PEN-001",
            )

        self.assertEqual(created_count, 0)
        append_row.assert_not_called()


if __name__ == "__main__":
    unittest.main()
