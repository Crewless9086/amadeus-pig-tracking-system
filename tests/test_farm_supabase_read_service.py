from datetime import date
import unittest
from unittest.mock import patch

from modules.pig_weights import farm_supabase_read_service
from modules.pig_weights import pig_weights_service


class FarmSupabaseReadServiceTests(unittest.TestCase):
    def test_pig_summary_maps_current_state_to_existing_frontend_shape(self):
        row = {
            "pig_id": "PIG-1",
            "tag_number": "101",
            "pig_name": "Pig One",
            "status": "Active",
            "on_farm": True,
            "animal_type": "Grower",
            "sex": "Female",
            "date_of_birth": date(2026, 1, 1),
            "litter_id": "LIT-1",
            "purpose": "Grow_Out",
            "current_weight_kg": 61.5,
            "last_weight_date": date(2026, 6, 22),
            "current_pen_id": "PEN-1",
            "current_pen_name": "Grower Pen",
        }

        summary = farm_supabase_read_service._pig_summary(row)

        self.assertEqual(summary["pig_id"], "PIG-1")
        self.assertEqual(summary["tag_number"], "101")
        self.assertEqual(summary["on_farm"], "Yes")
        self.assertEqual(summary["current_weight_kg"], 61.5)
        self.assertEqual(summary["last_weight_date"], "2026-06-22")
        self.assertEqual(summary["current_pen_name"], "Grower Pen")
        self.assertEqual(summary["weight_band"], "60-<80 kg")

    def test_weight_history_calculates_differences_from_supabase_rows(self):
        rows_by_sql = []

        def fake_fetch_all(sql, params=(), connect_factory=None):
            rows_by_sql.append(sql)
            if "from public.pig_weight_events" in sql:
                return [
                    {
                        "weight_event_id": "WGT-2",
                        "pig_id": "PIG-1",
                        "weight_date": date(2026, 6, 22),
                        "weight_kg": 62.0,
                        "weighed_by": "Owner",
                        "condition_notes": "",
                    },
                    {
                        "weight_event_id": "WGT-1",
                        "pig_id": "PIG-1",
                        "weight_date": date(2026, 6, 15),
                        "weight_kg": 60.0,
                        "weighed_by": "Owner",
                        "condition_notes": "",
                    },
                ]
            if "select tag_number" in sql:
                return [{"tag_number": "101"}]
            return []

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            result = farm_supabase_read_service.get_weight_history_for_pig("PIG-1")

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["tag_number"], "101")
        self.assertEqual(result["history"][0]["difference_kg"], 2.0)
        self.assertEqual(result["history"][0]["days_since_previous"], 7)
        self.assertEqual(result["history"][0]["growth_rate_kg_day"], 0.286)

    def test_pig_detail_maps_supabase_current_state_with_parent_tags(self):
        def fake_fetch_one(sql, params=(), connect_factory=None):
            self.assertEqual(params, ("PIG-1",))
            return {
                "pig_id": "PIG-1",
                "tag_number": "101",
                "pig_name": "Pig One",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Grower",
                "sex": "Female",
                "date_of_birth": date(2026, 1, 1),
                "litter_id": "LIT-1",
                "purpose": "Grow_Out",
                "current_weight_kg": 61.5,
                "last_weight_date": date(2026, 6, 22),
                "current_pen_id": "PEN-1",
                "current_pen_name": "Grower Pen",
                "mother_pig_id": "SOW-1",
                "mother_tag_number": "M1",
                "father_pig_id": "BOAR-1",
                "father_tag_number": "F1",
                "notes": "Healthy",
            }

        with patch.object(farm_supabase_read_service, "_fetch_one", side_effect=fake_fetch_one):
            detail = farm_supabase_read_service.get_pig_detail("PIG-1")

        self.assertEqual(detail["pig_id"], "PIG-1")
        self.assertEqual(detail["current_pen_name"], "Grower Pen")
        self.assertEqual(detail["mother_tag_number"], "M1")
        self.assertEqual(detail["father_tag_number"], "F1")
        self.assertEqual(detail["general_notes"], "Healthy")
        self.assertEqual(detail["source"], "supabase_canonical")

    def test_movement_history_maps_pen_names_and_current_pen(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            self.assertEqual(params, ("PIG-1",))
            return [{
                "location_event_id": "MOVE-1",
                "pig_id": "PIG-1",
                "move_date": date(2026, 6, 22),
                "from_pen_id": "PEN-1",
                "to_pen_id": "PEN-2",
                "from_pen_name": "Old Pen",
                "to_pen_name": "New Pen",
                "reason_for_move": "Growth",
                "moved_by": "Owner",
                "move_notes": "Moved after weighing",
            }]

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all), \
             patch.object(farm_supabase_read_service, "get_pig_detail", return_value={
                 "tag_number": "101",
                 "current_pen_id": "PEN-2",
             }):
            result = farm_supabase_read_service.get_movement_history_for_pig("PIG-1")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["current_pen_id"], "PEN-2")
        self.assertEqual(result["history"][0]["to_pen_name"], "New Pen")
        self.assertEqual(result["history"][0]["move_date_display"], "2026-06-22")

    def test_treatment_history_maps_supabase_medical_events(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            if "from public.pig_medical_events" in sql:
                return [{
                    "medical_event_id": "MED-1",
                    "pig_id": "PIG-1",
                    "treatment_date": date(2026, 6, 22),
                    "treatment_type": "Deworming",
                    "product_id": "PRD-1",
                    "product_name": "Dewormer",
                    "dose": 2,
                    "dose_unit": "ml",
                    "route": "Oral",
                    "reason_for_treatment": "Routine",
                    "batch_lot_number": "B1",
                    "withdrawal_days": 7,
                    "withdrawal_end_date": date(2026, 6, 29),
                    "given_by": "Owner",
                    "follow_up_required": False,
                    "follow_up_date": None,
                    "medical_notes": "No issue",
                }]
            return [{"tag_number": "101"}]

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            result = farm_supabase_read_service.get_treatment_history_for_pig("PIG-1")

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["history"][0]["treatment_type"], "Deworming")
        self.assertEqual(result["history"][0]["withdrawal_end_date"], "2026-06-29")
        self.assertEqual(result["history"][0]["follow_up_required"], "No")

    def test_latest_weight_and_weights_by_date_map_supabase_rows(self):
        def fake_fetch_one(sql, params=(), connect_factory=None):
            return {
                "pig_id": "PIG-1",
                "tag_number": "101",
                "current_weight_kg": 62,
                "last_weight_date": date(2026, 6, 22),
            }

        def fake_fetch_all(sql, params=(), connect_factory=None):
            return [{
                "weight_event_id": "WGT-1",
                "pig_id": "PIG-1",
                "tag_number": "101",
                "current_pen_id": "PEN-1",
                "weight_date": date(2026, 6, 22),
                "weight_kg": 62,
                "weighed_by": "Owner",
                "condition_notes": "",
            }]

        with patch.object(farm_supabase_read_service, "_fetch_one", side_effect=fake_fetch_one):
            latest = farm_supabase_read_service.get_latest_weight_for_pig("PIG-1")
        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            entries = farm_supabase_read_service.get_weight_entries_by_date(date(2026, 6, 22))

        self.assertEqual(latest["previous_weight_kg"], 62.0)
        self.assertEqual(latest["previous_weight_date"], "2026-06-22")
        self.assertEqual(entries["count"], 1)
        self.assertEqual(entries["history"][0]["current_pen_id"], "PEN-1")

    def test_parent_options_maps_breeding_pigs_from_supabase(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            return [
                {
                    "pig_id": "SOW-1",
                    "tag_number": "M1",
                    "sex": "Female",
                    "status": "Active",
                    "purpose": "Breeding",
                    "current_pen_id": "PEN-1",
                    "current_pen_name": "Sow Pen",
                },
                {
                    "pig_id": "BOAR-1",
                    "tag_number": "F1",
                    "sex": "Male",
                    "status": "Active",
                    "purpose": "Breeding",
                    "current_pen_id": "PEN-2",
                    "current_pen_name": "Boar Pen",
                },
            ]

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            options = farm_supabase_read_service.get_parent_options()

        self.assertEqual(options["mothers"][0]["pig_id"], "Unknown")
        self.assertEqual(options["fathers"][0]["pig_id"], "Unknown")
        self.assertEqual(options["mothers"][1]["pig_id"], "SOW-1")
        self.assertEqual(options["mothers"][1]["current_pen_name"], "Sow Pen")
        self.assertEqual(options["fathers"][1]["pig_id"], "BOAR-1")

    def test_weight_report_maps_supabase_events_and_summary(self):
        def fake_fetch_all(sql, params=(), connect_factory=None):
            self.assertEqual(params, (date(2026, 5, 20),))
            return [
                {
                    "weight_event_id": "WGT-OLD",
                    "pig_id": "PIG-1",
                    "weight_date": date(2026, 5, 18),
                    "weight_kg": 40,
                    "weighed_by": "Tester",
                    "condition_notes": "",
                    "tag_number": "001",
                    "status": "Active",
                    "on_farm": True,
                    "current_pen_id": "PEN-1",
                    "current_pen_name": "Camp 1",
                    "animal_type": "Grower",
                    "current_weight_kg": 42,
                },
                {
                    "weight_event_id": "WGT-1",
                    "pig_id": "PIG-1",
                    "weight_date": date(2026, 5, 20),
                    "weight_kg": 42,
                    "weighed_by": "Tester",
                    "condition_notes": "Good",
                    "tag_number": "001",
                    "status": "Active",
                    "on_farm": True,
                    "current_pen_id": "PEN-1",
                    "current_pen_name": "Camp 1",
                    "animal_type": "Grower",
                    "current_weight_kg": 42,
                },
                {
                    "weight_event_id": "WGT-2-OLD",
                    "pig_id": "PIG-2",
                    "weight_date": date(2026, 5, 18),
                    "weight_kg": 36,
                    "weighed_by": "Tester",
                    "condition_notes": "",
                    "tag_number": "002",
                    "status": "Active",
                    "on_farm": True,
                    "current_pen_id": "PEN-2",
                    "current_pen_name": "Camp 2",
                    "animal_type": "Grower",
                    "current_weight_kg": 35,
                },
                {
                    "weight_event_id": "WGT-2",
                    "pig_id": "PIG-2",
                    "weight_date": date(2026, 5, 20),
                    "weight_kg": 35,
                    "weighed_by": "Tester",
                    "condition_notes": "",
                    "tag_number": "002",
                    "status": "Active",
                    "on_farm": True,
                    "current_pen_id": "PEN-2",
                    "current_pen_name": "Camp 2",
                    "animal_type": "Grower",
                    "current_weight_kg": 35,
                },
            ]

        with patch.object(farm_supabase_read_service, "_fetch_all", side_effect=fake_fetch_all):
            report = farm_supabase_read_service.get_weight_report(date(2026, 5, 20), date(2026, 5, 20))

        self.assertTrue(report["success"])
        self.assertEqual(report["source"], "supabase_canonical")
        self.assertEqual(report["summary"]["total_entries"], 2)
        self.assertEqual(report["summary"]["average_difference_kg"], 0.5)
        self.assertEqual(report["summary"]["weight_loss_count"], 1)
        self.assertEqual(report["loss_flags"][0]["pig_id"], "PIG-2")

    def test_family_tree_maps_current_pig_parents_and_siblings(self):
        rows = [
            {
                "pig_id": "PIG-1",
                "tag_number": "101",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Grower",
                "sex": "Female",
                "date_of_birth": date(2026, 1, 1),
                "litter_id": "LIT-1",
                "purpose": "Grow_Out",
                "current_weight_kg": 61.5,
                "last_weight_date": date(2026, 6, 22),
                "current_pen_id": "PEN-1",
                "current_pen_name": "Grower Pen",
                "mother_pig_id": "SOW-1",
                "father_pig_id": "BOAR-1",
            },
            {
                "pig_id": "PIG-2",
                "tag_number": "102",
                "status": "Active",
                "on_farm": True,
                "animal_type": "Grower",
                "sex": "Male",
                "date_of_birth": date(2026, 1, 1),
                "litter_id": "LIT-1",
                "current_weight_kg": 60.0,
                "current_pen_id": "PEN-1",
            },
            {
                "pig_id": "SOW-1",
                "tag_number": "M1",
                "status": "Active",
                "on_farm": True,
                "sex": "Female",
                "purpose": "Breeding",
            },
            {
                "pig_id": "BOAR-1",
                "tag_number": "F1",
                "status": "Active",
                "on_farm": True,
                "sex": "Male",
                "purpose": "Breeding",
            },
        ]

        with patch.object(farm_supabase_read_service, "_current_state_rows", return_value=rows):
            tree = farm_supabase_read_service.get_family_tree("PIG-1")

        self.assertEqual(tree["pig_id"], "PIG-1")
        self.assertEqual(tree["current_pig"]["tag_number"], "101")
        self.assertEqual(tree["mother"]["pig_id"], "SOW-1")
        self.assertEqual(tree["father"]["pig_id"], "BOAR-1")
        self.assertEqual(tree["sibling_count"], 1)
        self.assertEqual(tree["siblings"][0]["pig_id"], "PIG-2")
        self.assertEqual(tree["source"], "supabase_canonical")

    def test_pig_weights_service_prefers_supabase_when_available(self):
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(farm_supabase_read_service, "get_pens", return_value=[{"pen_id": "PEN-1"}]):
            self.assertEqual(pig_weights_service.get_pens(), [{"pen_id": "PEN-1"}])

    def test_pig_weights_service_prefers_supabase_parent_options_when_available(self):
        expected = {"mothers": [{"pig_id": "SOW-1"}], "fathers": [{"pig_id": "BOAR-1"}]}
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=True), \
             patch.object(farm_supabase_read_service, "get_parent_options", return_value=expected):
            self.assertEqual(pig_weights_service.get_parent_options(), expected)

    def test_pig_weights_service_falls_back_when_supabase_unavailable(self):
        with patch.object(farm_supabase_read_service, "farm_supabase_reads_available", return_value=False), \
             patch.object(pig_weights_service, "get_all_records", return_value=[
                 {"Pen_ID": "PEN-1", "Pen_Name": "Grower", "Pen_Type": "Grower", "Capacity": "10", "Is_Active": "Yes"}
             ]):
            result = pig_weights_service.get_pens()

        self.assertEqual(result[0]["pen_id"], "PEN-1")
        self.assertEqual(result[0]["pen_name"], "Grower")


if __name__ == "__main__":
    unittest.main()
