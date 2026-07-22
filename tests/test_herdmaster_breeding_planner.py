import copy
import unittest
from unittest.mock import Mock, patch

from modules.agents.herdmaster import run_herdmaster


def tree(pig_id, mother, father):
    return {"pig_id": pig_id, "mother": {"pig_id": mother}, "father": {"pig_id": father}, "source": "supabase_canonical"}


def fixture_readers(matings=None, extra_boars=None):
    pigs = [
        {"Pig_ID": "F1", "Tag_Number": "F1", "Sex": "Female", "Status": "Active", "On_Farm": "Yes", "Purpose": "Breeding", "General_Notes": "good condition"},
        {"Pig_ID": "B1", "Tag_Number": "B1", "Sex": "Male", "Status": "Active", "On_Farm": "Yes", "Purpose": "Breeding", "General_Notes": "good condition"},
    ] + (extra_boars or [])
    trees = {"F1": tree("F1", "M1", "D1"), "B1": tree("B1", "M2", "D2")}
    for row in extra_boars or []:
        trees[row["Pig_ID"]] = tree(row["Pig_ID"], "M3", "D3")
    analytics = {"sows": [{"pig_id": "F1", "mating_count": 1}], "boars": [{"pig_id": row["Pig_ID"], "mating_count": 1} for row in pigs if row["Sex"] == "Male"]}
    return {"pig_rows": lambda: pigs, "mating_overview": lambda: matings or [], "breeding_analytics": lambda: analytics, "family_tree": lambda pig_id: trees.get(pig_id)}


class HerdmasterBreedingPlannerTests(unittest.TestCase):
    def test_complete_canonical_female_gets_ranked_safe_boar_and_stable_fingerprint(self):
        readers = fixture_readers()
        first = run_herdmaster({"capability": "breeding_planner"}, readers=readers)
        second = run_herdmaster({"capability": "breeding_planner"}, readers=readers)
        female = first["females"][0]
        self.assertEqual(first["status"], "breeding_planner_advisory_ready")
        self.assertEqual(female["state"], "No Active Mating")
        self.assertEqual(female["safe_matches"][0]["pig_id"], "B1")
        self.assertEqual(first["response_fingerprint"], second["response_fingerprint"])
        self.assertTrue(first["read_only"])

    def test_incomplete_parentage_condition_or_performance_fails_closed(self):
        readers = fixture_readers()
        readers["family_tree"] = lambda pig_id: None if pig_id == "F1" else tree(pig_id, "M2", "D2")
        readers["breeding_analytics"] = lambda: {"sows": [], "boars": [{"pig_id": "B1", "mating_count": 1}]}
        result = run_herdmaster({"capability": "breeding_planner"}, readers=readers)
        self.assertEqual(result["confidence"], 0.0)
        self.assertEqual(result["females"][0]["safe_matches"], [])
        self.assertIn("parentage", result["females"][0]["missing_facts"])
        self.assertIn("performance", result["females"][0]["missing_facts"])

    def test_parent_child_sibling_castrated_and_unavailable_boars_are_excluded(self):
        excluded = [
            {"Pig_ID": "B_PARENT", "Tag_Number": "BP", "Sex": "Male", "Status": "Active", "On_Farm": "Yes", "Purpose": "Breeding", "General_Notes": "ok"},
            {"Pig_ID": "B_SIBLING", "Tag_Number": "BS", "Sex": "Male", "Status": "Active", "On_Farm": "Yes", "Purpose": "Breeding", "General_Notes": "ok"},
            {"Pig_ID": "B_CAST", "Tag_Number": "BC", "Sex": "Castrated_Male", "Status": "Active", "On_Farm": "Yes", "Purpose": "Breeding", "General_Notes": "ok"},
            {"Pig_ID": "B_OFF", "Tag_Number": "BO", "Sex": "Male", "Status": "Active", "On_Farm": "No", "Purpose": "Breeding", "General_Notes": "ok"},
            {"Pig_ID": "B_EXIT", "Tag_Number": "BE", "Sex": "Male", "Status": "Exited", "On_Farm": "No", "Purpose": "Breeding", "General_Notes": "ok"},
            {"Pig_ID": "B_NONBREED", "Tag_Number": "BN", "Sex": "Male", "Status": "Active", "On_Farm": "Yes", "Purpose": "Sale", "General_Notes": "ok"},
            {"Pig_ID": "B_NOCONDITION", "Tag_Number": "NC", "Sex": "Male", "Status": "Active", "On_Farm": "Yes", "Purpose": "Breeding", "General_Notes": ""},
        ]
        readers = fixture_readers(extra_boars=excluded)
        readers["family_tree"] = lambda pig_id: ({"pig_id": "F1", "mother": {"pig_id": "B_PARENT"}, "father": {"pig_id": "D1"}} if pig_id == "F1" else tree(pig_id, "M1", "D1") if pig_id == "B_SIBLING" else tree(pig_id, "M2", "D2"))
        result = run_herdmaster({"capability": "breeding_planner"}, readers=readers)
        female = result["females"][0]
        self.assertEqual([row["pig_id"] for row in female["safe_matches"]], ["B1"])
        excluded_reasons = {row["pig_id"]: row["reason"] for row in female["excluded_matches"]}
        self.assertEqual(excluded_reasons["B_PARENT"], "parent_child")
        self.assertEqual(excluded_reasons["B_SIBLING"], "known_sibling")
        self.assertEqual(excluded_reasons["B_CAST"], "castrated_male")
        self.assertEqual(excluded_reasons["B_OFF"], "off_farm")
        self.assertEqual(excluded_reasons["B_EXIT"], "not_active")
        self.assertEqual(excluded_reasons["B_NONBREED"], "non_breeding_purpose")
        self.assertEqual(excluded_reasons["B_NOCONDITION"], "condition_missing")

    def test_mating_facts_classify_active_and_overdue_without_inference(self):
        for expected, row in [("Active Mating", {"mating_id": "M1", "sow_pig_id": "F1", "is_open": "Yes"}), ("Overdue Check", {"mating_id": "M1", "sow_pig_id": "F1", "is_open": "Yes", "is_overdue_check": "Yes"}), ("Overdue Farrowing", {"mating_id": "M1", "sow_pig_id": "F1", "is_open": "Yes", "is_overdue_farrowing": "Yes"})]:
            result = run_herdmaster({"capability": "breeding_planner"}, readers=fixture_readers([row]))
            self.assertEqual(result["females"][0]["state"], expected)
            self.assertEqual(result["females"][0]["safe_matches"], [])

    def test_inputs_remain_unchanged_and_no_writer_or_legacy_service_is_called(self):
        readers = fixture_readers()
        original = copy.deepcopy(readers["pig_rows"]())
        forbidden = Mock(side_effect=AssertionError("forbidden call"))
        with patch("modules.agents.herdmaster.get_sales_availability", forbidden):
            result = run_herdmaster({"capability": "breeding_planner"}, readers=readers)
        self.assertTrue(result["read_only"])
        self.assertEqual(readers["pig_rows"](), original)

    def test_authority_boundary_never_calls_mating_writer_or_scheduler(self):
        readers = fixture_readers()
        forbidden = Mock(side_effect=AssertionError("write or delivery was attempted"))
        with patch("modules.pig_weights.mating_service.save_new_mating", forbidden), \
             patch("modules.pig_weights.mating_service.assume_pregnant", forbidden), \
             patch("modules.pig_weights.mating_service.mark_not_pregnant", forbidden):
            result = run_herdmaster({"capability": "breeding_planner"}, readers=readers)
        self.assertTrue(result["advisory_only"])
        self.assertEqual(forbidden.call_count, 0)

    def test_unavailable_canonical_read_fails_closed_without_legacy_fallback(self):
        with patch("modules.agents.herdmaster.farm_supabase_reads_available", return_value=False):
            result = run_herdmaster({"capability": "breeding_planner"})
        self.assertEqual(result["status"], "breeding_planner_needs_data")
        self.assertIn("no legacy fallback", result["direct_answer"])

    def test_canonical_family_reader_failure_fails_closed(self):
        readers = fixture_readers()
        readers["family_tree"] = Mock(side_effect=RuntimeError("reader unavailable"))
        result = run_herdmaster({"capability": "breeding_planner"}, readers=readers)
        self.assertEqual(result["status"], "breeding_planner_needs_data")
        self.assertEqual(result["females"], [])


if __name__ == "__main__":
    unittest.main()
