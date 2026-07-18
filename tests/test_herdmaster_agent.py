import unittest
from unittest.mock import patch

from modules.agents import herdmaster
from modules.agents.herdmaster import run_herdmaster


def readers(*, on_farm=6, active=None):
    active = active if active is not None else [
        {"pig_id": "P1", "tag_number": "101", "animal_type": "Sow", "sex": "Female", "current_weight_kg": 90, "current_pen_id": "PEN-A", "current_pen_name": "Breeding"},
        {"pig_id": "P2", "tag_number": "102", "animal_type": "Boar", "sex": "Male", "current_weight_kg": 100, "current_pen_id": "PEN-A", "current_pen_name": "Breeding"},
        {"pig_id": "P3", "tag_number": "103", "animal_type": "Piglet", "sex": "Female", "current_weight_kg": 8, "current_pen_id": "PEN-B", "current_pen_name": "Piglets"},
        {"pig_id": "P4", "tag_number": "104", "animal_type": "Piglet", "sex": "Male", "current_weight_kg": 9, "current_pen_id": "PEN-B", "current_pen_name": "Piglets"},
        {"pig_id": "P5", "tag_number": "105", "animal_type": "Grower", "sex": "Female", "current_weight_kg": 42, "current_pen_id": "PEN-C", "current_pen_name": "Growers"},
        {"pig_id": "P6", "tag_number": "106", "animal_type": "Weaner", "sex": "Male", "current_weight_kg": 20, "current_pen_id": "PEN-C", "current_pen_name": "Growers"},
    ]
    return {
        "dashboard": lambda: {"on_farm_pigs": on_farm, "boars": 1, "sows": 1, "gilts": 0, "piglets": 2, "weaners": 1, "growers": 1, "finishers": 0, "reserved_pigs": 1, "available_for_sale_pigs": 0},
        "active_pigs": lambda: active,
        "pens": lambda: [{"pen_id": "PEN-A", "pen_name": "Breeding", "capacity": 3}, {"pen_id": "PEN-B", "pen_name": "Piglets", "capacity": 12}, {"pen_id": "PEN-C", "pen_name": "Growers", "capacity": 8}],
        "litter_attention": lambda: {"attention_count": 1, "items": [{"litter_id": "L1"}]},
        "pig_detail": lambda pig_id: {"pig_id": pig_id, "tag_number": "104", "status": "Active", "on_farm": "Yes", "sex": "Female", "current_weight_kg": 9, "current_pen_id": "PEN-B", "current_pen_name": "Piglets", "purpose": "Grow_Out"},
    }


class HerdmasterAgentTests(unittest.TestCase):
    def test_real_question_returns_exact_physical_herd_count_and_breakdown(self):
        result = run_herdmaster({"question": "How many pigs do we have on the farm?"}, readers=readers())
        self.assertEqual(result["capability"], "herd_inventory")
        self.assertEqual(result["metrics"]["on_farm_total"], 6)
        self.assertEqual(result["direct_answer"], "There are 6 pigs physically recorded on the farm.")
        self.assertEqual(result["breakdown"]["by_type"]["piglets"], 2)
        self.assertEqual(result["sources"][0]["name"], "pig_current_state")
        self.assertGreaterEqual(result["confidence"], .98)

    def test_lifecycle_mismatch_is_reported_not_hidden(self):
        result = run_herdmaster({"question": "How many pigs are here?"}, readers=readers(on_farm=7))
        mismatch = next(row for row in result["anomalies"] if row["code"] == "on_farm_active_status_mismatch")
        self.assertEqual(mismatch["count"], 1)
        self.assertLess(result["confidence"], .99)

    def test_broad_overview_collects_pen_and_litter_evidence(self):
        result = run_herdmaster({"question": "What needs attention on the farm?"}, readers=readers())
        sources = {row["name"] for row in result["sources"]}
        self.assertIn("pens", sources)
        self.assertIn("litters", sources)
        self.assertIn("on_farm_total", result["metrics"])

    def test_specific_pig_is_owned_by_herdmaster(self):
        result = run_herdmaster({"question": "Tell me about pig 104", "subject": {"pig_id": "P4"}}, readers=readers())
        self.assertEqual(result["capability"], "pig_profile")
        self.assertIn("Pig 104", result["direct_answer"])
        self.assertEqual(result["confidence"], .99)

    def test_live_reader_snapshot_is_reused_for_bounded_freshness_window(self):
        calls = {"pig_rows": 0}
        def pig_rows():
            calls["pig_rows"] += 1
            return [{"Pig_ID": "P1", "Tag_Number": "1", "Status": "Active", "On_Farm": "Yes", "Animal_Type": "Sow", "Sex": "Female", "Current_Weight_Kg": 80, "Current_Pen_ID": "A"}]
        with patch.object(herdmaster, "get_pig_master_rows", side_effect=pig_rows):
            herdmaster._SNAPSHOT_CACHE.clear()
            run_herdmaster({"question": "How many pigs are here?"})
            run_herdmaster({"question": "How many pigs are here?"})
        self.assertEqual(calls, {"pig_rows": 1})

    def test_canonical_master_snapshot_derives_inventory_without_dashboard_query(self):
        result = run_herdmaster({"question": "How many pigs are here?"}, readers={
            "pig_rows": lambda: [
                {"Pig_ID": "P1", "Tag_Number": "1", "Status": "Active", "On_Farm": "Yes", "Animal_Type": "Sow", "Sex": "Female", "Current_Weight_Kg": 80, "Current_Pen_ID": "A"},
                {"Pig_ID": "P2", "Tag_Number": "2", "Status": "Sold", "On_Farm": "No", "Animal_Type": "Grower", "Sex": "Male", "Current_Weight_Kg": 50, "Current_Pen_ID": ""},
            ],
        })
        self.assertEqual(result["metrics"]["on_farm_total"], 1)
        self.assertEqual(result["breakdown"]["by_type"]["sows"], 1)

    def test_prewean_piglets_do_not_create_false_tag_or_weight_anomalies(self):
        result = run_herdmaster({"question": "How many pigs are here?"}, readers={
            "pig_rows": lambda: [
                {"Pig_ID": "P1", "Tag_Number": "", "Status": "Active", "On_Farm": "Yes", "Animal_Type": "Piglet", "Sex": "", "Current_Weight_Kg": None, "Current_Pen_ID": "LITTER-A"},
            ],
        })
        codes = {row["code"] for row in result["anomalies"]}
        self.assertNotIn("active_pig_missing_tag", codes)
        self.assertNotIn("active_pig_missing_weight", codes)


if __name__ == "__main__":
    unittest.main()
