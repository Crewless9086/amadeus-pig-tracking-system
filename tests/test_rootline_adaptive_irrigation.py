import unittest
from copy import deepcopy
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from modules.telemetry.rootline_adaptive_irrigation import (
    build_adaptive_irrigation_decisions,
    build_run_outcome_evidence,
    learning_hints,
    notification_projection,
    project_weekly_delivery_obligation,
)
from modules.telemetry.rootline_water_energy_plan import build_water_energy_plan


ZA = ZoneInfo("Africa/Johannesburg")
NOW = datetime(2026, 8, 3, 18, 0, tzinfo=ZA)


def evidence():
    return {
        "policy": {"season": "winter", "target_days_per_week": 4,
                   "governing_reserve_soc_pct": 63, "absolute_floor_soc_pct": 40},
        "power": {"observed_at": NOW.isoformat(), "battery_soc_pct": 80,
                  "solar_power_w": 1000, "load_power_w": 700, "grid_power_w": 0},
        "local_weather": {"observed_at": NOW.isoformat(), "rain_rate_mm_h": 0,
                          "rain_today_mm": 0},
        "forecast": {"observed_at": NOW.isoformat(), "rain_probability_pct": 0,
                     "rain_sum_mm": 0},
        "water": {"observed_at": NOW.isoformat(), "reservoir_available": True},
        "zones": [
            {"zone_id": "B12345", "visible_need": "dry",
             "visible_need_observed_at": NOW.isoformat(), "visible_need_source": "owner_observation",
             "completed_days_last_7_days": 2,
             "completion_ledger_complete_through": NOW.isoformat(),
             "completion_events": []},
            {"zone_id": "C12345", "visible_need": "dry",
             "visible_need_observed_at": NOW.isoformat(), "visible_need_source": "owner_observation",
             "completed_days_last_7_days": 1,
             "completion_ledger_complete_through": NOW.isoformat(),
             "completion_events": []},
        ],
    }


def zones(result):
    return {row["zone_id"]: row for row in result["zones"]}


class AdaptiveIrrigationTests(unittest.TestCase):
    def test_recently_irrigated_b_and_dry_c(self):
        item = evidence()
        item["zones"][0]["completion_events"] = [
            {"completed_at": (NOW - timedelta(hours=6)).isoformat(),
             "verified_runtime_minutes": 60, "state": "Completed",
             "shutdown_verified": True, "outcome_id": "B-OUTCOME-1",
             "source": "owner_confirmed", "objective_satisfied": True}
        ]
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))
        self.assertEqual(result["B12345"]["decision"], "Completed")
        self.assertEqual(result["C12345"]["decision"], "Run now")
        self.assertEqual(result["C12345"]["rank"], 1)

    def test_both_camps_may_rank_same_day_but_never_simultaneously(self):
        result = build_adaptive_irrigation_decisions(evidence(), now=NOW)
        selected = zones(result)
        self.assertEqual({row["decision"] for row in selected.values()}, {"Run now"})
        self.assertEqual(sorted(row["rank"] for row in selected.values()), [1, 2])
        self.assertTrue(result["same_day_multiple_zones_allowed"])
        self.assertFalse(result["simultaneous_zones_allowed"])
        self.assertTrue(all(row["simultaneous_with_other_zone"] is False for row in selected.values()))

    def test_fresh_observed_rain_holds_while_forecast_stays_separate(self):
        item = evidence()
        item["local_weather"].update(rain_rate_mm_h=2.0, rain_today_mm=4.0)
        item["forecast"].update(rain_probability_pct=0, rain_sum_mm=0)
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))
        self.assertTrue(all(row["decision"] == "Hold" for row in result.values()))
        self.assertTrue(all("Fresh local evidence records rain" in row["reason"] for row in result.values()))

    def test_low_soc_urgent_water_can_justify_grid_exposure(self):
        item = evidence()
        item["power"].update(battery_soc_pct=35, solar_power_w=0, load_power_w=900)
        item["zones"][1]["visible_need"] = "urgent"
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))["C12345"]
        self.assertEqual(result["decision"], "Run now")
        self.assertFalse(result["grid_exposure_may_be_justified"])
        self.assertFalse(result["command_authority"])

    def test_gravity_fed_bc_ignores_missing_power_for_decision_and_confidence(self):
        item = evidence(); item["power"] = {}
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))["B12345"]
        self.assertEqual(result["decision"], "Run now")
        self.assertNotIn("power_unavailable", result["evidence_gaps"])
        self.assertFalse(result["grid_exposure_may_be_justified"])

    def test_adequate_solar_with_stale_water_blocks_only_execution(self):
        item = evidence()
        item["water"]["observed_at"] = (NOW - timedelta(days=3)).isoformat()
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))
        self.assertTrue(all(row["decision"] == "Needs Data" for row in result.values()))
        self.assertTrue(all(row["proposed_segment_minutes"] is None for row in result.values()))
        self.assertTrue(all(row["confidence"] in {"low", "medium"} for row in result.values()))

    def test_summer_prefers_evening_and_winter_can_prefer_daylight(self):
        summer = evidence()
        summer["policy"]["season"] = "summer"
        noon = NOW.replace(hour=12)
        for key in ("power", "local_weather", "forecast", "water"):
            summer[key]["observed_at"] = noon.isoformat()
        summer_result = zones(build_adaptive_irrigation_decisions(summer, now=noon))
        self.assertTrue(all(row["decision"] == "Run later" for row in summer_result.values()))
        self.assertTrue(all(row["preferred_window"] == "next_evening_or_night_window"
                            for row in summer_result.values()))
        winter = evidence()
        for key in ("power", "local_weather", "forecast", "water"):
            winter[key]["observed_at"] = noon.isoformat()
        winter_result = zones(build_adaptive_irrigation_decisions(winter, now=noon))
        self.assertTrue(all(row["decision"] == "Run now" for row in winter_result.values()))

    def test_segment_one_requires_fresh_reassessment_before_segment_two(self):
        item = evidence()
        item["zones"][1]["latest_segment"] = {
            "segment_number": 1, "state": "Completed", "shutdown_verified": True,
            "objective_remaining": True,
        }
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))["C12345"]
        self.assertEqual(result["decision"], "Reassess after segment one")
        self.assertTrue(result["fresh_decision_before_second_segment"])
        self.assertIsNone(result["proposed_segment_minutes"])

    def test_unchanged_decision_suppresses_duplicate_notification(self):
        result = build_adaptive_irrigation_decisions(evidence(), now=NOW)
        first = notification_projection(result)
        replay = notification_projection(result, result["decision_sha256"])
        self.assertTrue(first["emit_daily_recommendation"])
        self.assertFalse(replay["emit_daily_recommendation"])
        self.assertTrue(replay["suppress_unchanged_hold"])
        self.assertFalse(replay["workflow_authority"])

    def test_owner_correction_changes_next_recommendation(self):
        before = zones(build_adaptive_irrigation_decisions(evidence(), now=NOW))["C12345"]
        item = evidence()
        item["zones"][1]["owner_correction"] = {
            "visible_need": "wet", "observed_at": NOW.isoformat(),
            "source": "authenticated_owner",
        }
        after = zones(build_adaptive_irrigation_decisions(item, now=NOW))["C12345"]
        self.assertEqual(before["decision"], "Run now")
        self.assertEqual(after["decision"], "Hold")
        self.assertLess(after["need_score"], before["need_score"])

    def test_unverified_completion_does_not_suppress_need(self):
        item = evidence()
        item["zones"][0]["completion_events"] = [
            {"completed_at": NOW.isoformat(), "verified_runtime_minutes": 60,
             "state": "Stopped", "shutdown_verified": False,
             "outcome_id": "UNVERIFIED", "source": "transport"},
        ]
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))["B12345"]
        self.assertEqual(result["decision"], "Run now")
        self.assertIsNone(result["last_completed_at"])

    def test_fresh_ok_observation_overrides_cadence_pressure(self):
        item = evidence()
        item["zones"][1].update(visible_need="OK", completed_days_last_7_days=0)
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))["C12345"]
        self.assertEqual(result["decision"], "Hold")
        self.assertIn("weekly cadence is guidance only", result["reason"])

    def test_missing_visible_need_does_not_erase_authoritatively_covered_debt(self):
        item = evidence()
        for zone in item["zones"]:
            zone.pop("visible_need")
            zone.pop("visible_need_observed_at")
            zone.pop("visible_need_source")
            zone.pop("completed_days_last_7_days")
            zone["completion_events"] = []
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))
        for decision in result.values():
            self.assertEqual(decision["decision"], "Run now")
            self.assertGreater(decision["weekly_obligation"]["delivery_debt_days"], 0)
            self.assertIn("current_visible_need_unavailable", decision["evidence_gaps"])
            self.assertIn("verified_completion_history_unavailable", decision["evidence_gaps"])

    def test_missing_ledger_coverage_is_not_asserted_as_zero_delivery(self):
        item = evidence()
        for zone in item["zones"]:
            zone.pop("completion_ledger_complete_through")
            zone.pop("visible_need")
            zone.pop("visible_need_observed_at")
            zone.pop("visible_need_source")
            zone.pop("completed_days_last_7_days")
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))
        for decision in result.values():
            self.assertEqual(decision["decision"], "Hold")
            self.assertEqual(decision["weekly_obligation"]["status"], "Unavailable")
            self.assertIsNone(decision["weekly_obligation"]["delivery_debt_days"])

    def test_weekly_obligation_counts_only_verified_completed_zone_outcomes(self):
        zone = evidence()["zones"][0]
        zone["completion_events"] = [
            {"completed_at": (NOW - timedelta(hours=2)).isoformat(),
             "verified_runtime_minutes": 60, "state": "Completed",
             "shutdown_verified": True, "outcome_id": "B-OK", "source": "ledger"},
            {"completed_at": NOW.isoformat(), "verified_runtime_minutes": 60,
             "state": "command_accepted", "shutdown_verified": False,
             "outcome_id": "B-ON", "source": "provider"},
        ]
        zone["completion_events"][0]["objective_satisfied"] = True
        debt = project_weekly_delivery_obligation(zone, now=NOW)
        self.assertEqual(debt["completed_days"], 1)
        self.assertEqual(debt["verified_runtime_minutes"], 60)
        self.assertEqual(debt["verified_outcome_ids"], ["B-OK"])
        self.assertEqual(debt["on_receipts_counted"], 0)

    def test_verified_completion_reduces_only_its_zone_debt(self):
        item = evidence()
        item["zones"][0]["completion_events"] = [{
            "completed_at": (NOW - timedelta(hours=2)).isoformat(),
            "verified_runtime_minutes": 60, "state": "Completed",
            "shutdown_verified": True, "objective_satisfied": True,
            "outcome_id": "B-ONLY", "source": "ledger"}]
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))
        self.assertLess(result["B12345"]["weekly_obligation"]["delivery_debt_days"],
                        result["C12345"]["weekly_obligation"]["delivery_debt_days"])

    def test_short_completed_segment_does_not_discharge_sufficient_day(self):
        zone = evidence()["zones"][0]
        zone["completion_events"] = [{
            "completed_at": NOW.isoformat(), "verified_runtime_minutes": 1,
            "state": "Completed", "shutdown_verified": True,
            "objective_satisfied": False, "outcome_id": "B-PULSE", "source": "ledger"}]
        debt = project_weekly_delivery_obligation(zone, now=NOW)
        self.assertEqual(debt["verified_runtime_minutes"], 1)
        self.assertEqual(debt["completed_days"], 0)
        decision = zones(build_adaptive_irrigation_decisions(
            {**evidence(), "zones": [zone, evidence()["zones"][1]]}, now=NOW))["B12345"]
        self.assertEqual(decision["decision"], "Reassess after segment one")

    def test_exact_replay_is_deduplicated_and_conflicting_replay_fails_closed(self):
        zone = evidence()["zones"][0]
        outcome = {"completed_at": NOW.isoformat(), "verified_runtime_minutes": 60,
                   "state": "Completed", "shutdown_verified": True,
                   "objective_satisfied": True, "outcome_id": "B-ONE", "source": "ledger"}
        zone["completion_events"] = [outcome, dict(outcome)]
        exact = project_weekly_delivery_obligation(zone, now=NOW)
        self.assertEqual(exact["status"], "available")
        self.assertEqual(exact["verified_runtime_minutes"], 60)
        zone["completion_events"][1] = {**outcome, "completed_at": (NOW - timedelta(hours=1)).isoformat()}
        conflict = project_weekly_delivery_obligation(zone, now=NOW)
        self.assertEqual(conflict["status"], "conflicting")
        self.assertIsNone(conflict["delivery_debt_days"])
        zone["completion_events"] = [outcome, {
            **outcome, "state": "Failed", "shutdown_verified": False}]
        invalid_conflict = project_weekly_delivery_obligation(zone, now=NOW)
        self.assertEqual(invalid_conflict["status"], "conflicting")
        self.assertIsNone(invalid_conflict["delivery_debt_days"])
        item = evidence()
        item["zones"][0] = zone
        decision = zones(build_adaptive_irrigation_decisions(item, now=NOW))["B12345"]
        self.assertEqual(decision["decision"], "Needs Data")
        item["local_weather"].update(rain_rate_mm_h=3, rain_today_mm=5)
        rain_decision = zones(build_adaptive_irrigation_decisions(item, now=NOW))["B12345"]
        self.assertEqual(rain_decision["decision"], "Needs Data")
        self.assertIn("verified_completion_outcome_conflict", rain_decision["evidence_gaps"])

    def test_owner_corrected_sufficient_completion_is_consistent(self):
        item = evidence()
        item["zones"][0]["owner_correction"] = {
            "last_completed_at": NOW.isoformat(), "verified_runtime_minutes": 60,
            "outcome_id": "B-OWNER", "source": "authenticated_owner",
            "objective_satisfied": True, "another_segment_needed": False}
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))["B12345"]
        self.assertEqual(result["decision"], "Completed")
        self.assertEqual(result["weekly_obligation"]["completed_days"], 1)

    def test_unqualified_weekly_summary_cannot_create_debt_when_coverage_unknown(self):
        item = evidence()
        for zone in item["zones"]:
            zone.pop("completion_ledger_complete_through")
            zone.pop("visible_need")
            zone.pop("visible_need_observed_at")
            zone.pop("visible_need_source")
            zone["completed_days_last_7_days"] = 0
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))
        self.assertTrue(all(row["decision"] == "Hold" for row in result.values()))

    def test_uncertain_shutdown_contains_only_zone_and_requires_recovery(self):
        item = evidence()
        item["zones"][0]["latest_segment"] = {
            "segment_number": 1, "state": "Active", "shutdown_verified": False}
        result = zones(build_adaptive_irrigation_decisions(item, now=NOW))
        self.assertEqual(result["B12345"]["decision"], "recovery required")
        self.assertEqual(result["C12345"]["decision"], "Run now")
        self.assertFalse(result["B12345"]["automatic_on_retry"])

    def test_outcome_learning_preserves_unknown_volume_and_policy(self):
        outcome = build_run_outcome_evidence({
            "zone_id": "C12345", "planned_runtime_minutes": 60,
            "verified_runtime_minutes": 60, "shutdown_verified": True,
            "physical_flow_confirmation": "owner_observed",
            "weather_after": {"rain_mm": 3}, "another_segment_needed": False,
            "owner_correction": "crop looked sufficiently watered",
        }, now=NOW)
        hints = learning_hints([outcome])
        self.assertEqual(outcome["delivered_volume"], "Unavailable")
        self.assertEqual(outcome["flow_rate"], "Unavailable")
        self.assertFalse(hints["policy_changed"])
        self.assertIn("reassess_post_irrigation_rain_before_next_segment", hints["hints"])
        self.assertIn("apply_owner_correction_to_next_decision_evidence", hints["hints"])

    def test_canonical_plan_uses_adaptive_component_without_authority(self):
        adaptive = evidence()
        plan_evidence = {
            "power": adaptive["power"], "weather": adaptive["local_weather"],
            "forecast": {**adaptive["forecast"], "days": []},
            "tanks": {"reservoir_observed_at": NOW.isoformat(),
                      "reservoir_reported_count": 9},
            "irrigation": {"adaptive_management": {**adaptive, "enabled": True}},
            "irrigation_history": {}, "water_demand": {"status": "standing_essential"},
        }
        plan = build_water_energy_plan(plan_evidence, now=NOW)
        tasks = {row["task_id"]: row for row in plan["candidate_tasks"]}
        self.assertEqual(tasks["irrigation_B12345"]["zone_decision"], "Run now")
        self.assertEqual(tasks["irrigation_C12345"]["max_execution_minutes"], 60)
        self.assertFalse(tasks["irrigation_C12345"]["command_created"])
        self.assertFalse(plan["authority"]["controls_hardware"])

    def test_combined_canonical_tank_timestamp_reaches_adaptive_water_check(self):
        adaptive = evidence()
        plan_evidence = {
            "power": adaptive["power"], "weather": adaptive["local_weather"],
            "forecast": {**adaptive["forecast"], "days": []},
            "tanks": {
                "observed_at": NOW.isoformat(),
                "reservoir_observed_at": None,
                "reservoir_fraction": [4, 4],
            },
            "irrigation": {"adaptive_management": {**adaptive, "enabled": True}},
            "irrigation_history": {}, "water_demand": {"status": "standing_essential"},
        }
        tasks = {row["task_id"]: row for row in
                 build_water_energy_plan(plan_evidence, now=NOW)["candidate_tasks"]}
        self.assertEqual(tasks["irrigation_C12345"]["zone_decision"], "Run now")
        self.assertNotIn(
            "water_observation_stale", tasks["irrigation_C12345"]["dependencies"])

    def test_storage_only_combined_timestamp_is_not_reservoir_provenance(self):
        adaptive = evidence()
        plan_evidence = {
            "power": adaptive["power"], "weather": adaptive["local_weather"],
            "forecast": {**adaptive["forecast"], "days": []},
            "tanks": {
                "observed_at": NOW.isoformat(),
                "storage_fraction": [2, 4],
                "reservoir_observed_at": None,
                "reservoir_reported_count": None,
            },
            "irrigation": {"adaptive_management": {**adaptive, "enabled": True}},
            "irrigation_history": {}, "water_demand": {"status": "standing_essential"},
        }
        plan = build_water_energy_plan(plan_evidence, now=NOW)
        tasks = {row["task_id"]: row for row in plan["candidate_tasks"]}
        self.assertEqual(plan["tank_evidence"]["reservoir_freshness"], "Unavailable")
        self.assertEqual(tasks["irrigation_C12345"]["zone_decision"], "Needs Data")
        self.assertIn(
            "water_observation_unavailable",
            tasks["irrigation_C12345"]["dependencies"],
        )

    def test_canonical_weather_water_and_reserve_override_nested_adaptive_claims(self):
        adaptive = evidence()
        adaptive["power"].update(battery_soc_pct=99, solar_power_w=5000, load_power_w=100)
        adaptive["local_weather"].update(rain_rate_mm_h=0, rain_today_mm=0)
        adaptive["water"].update(reservoir_available=True)
        adaptive["policy"].update(governing_reserve_soc_pct=10)
        canonical = {
            "power": {"observed_at": NOW.isoformat(), "battery_soc_pct": 50,
                      "solar_power_w": 0, "load_power_w": 900, "grid_power_w": 0},
            "weather": {"observed_at": NOW.isoformat(), "rain_rate_mm_h": 2,
                        "rain_today_mm": 3},
            "forecast": {"observed_at": NOW.isoformat(), "days": []},
            "tanks": {"reservoir_observed_at": NOW.isoformat(), "reservoir_fraction": [4, 4]},
            "irrigation": {"adaptive_management": {**adaptive, "enabled": True}},
            "irrigation_history": {}, "water_demand": {"status": "standing_essential"},
        }
        tasks = {row["task_id"]: row for row in
                 build_water_energy_plan(canonical, now=NOW)["candidate_tasks"]}
        self.assertEqual(tasks["irrigation_C12345"]["zone_decision"], "Hold")
        self.assertIn("Fresh local evidence records rain", tasks["irrigation_C12345"]["reason"])

        canonical["weather"].update(rain_rate_mm_h=0, rain_today_mm=0)
        canonical["tanks"]["reservoir_observed_at"] = (NOW - timedelta(days=3)).isoformat()
        tasks = {row["task_id"]: row for row in
                 build_water_energy_plan(canonical, now=NOW)["candidate_tasks"]}
        self.assertEqual(tasks["irrigation_C12345"]["zone_decision"], "Needs Data")

    def test_satisfied_water_balance_holds_without_rewriting_schedule_debt(self):
        item=evidence()
        item["zones"][0]["water_balance"]={"status":"Available",
            "ledger_current":True,
            "obligation_effect":"satisfied","partial_obligation_credit":1.0,
            "remaining_water_need_mm":0,"schedule_debt_rewritten":False}
        result=zones(build_adaptive_irrigation_decisions(item,now=NOW))["B12345"]
        self.assertEqual(result["decision"],"Hold")
        self.assertEqual(result["weekly_obligation"]["delivery_debt_days"],1)
        self.assertFalse(result["water_balance"]["schedule_debt_rewritten"])

    def test_canonical_zone_balance_reaches_adaptive_planner(self):
        adaptive = evidence()
        plan_evidence = {
            "power": adaptive["power"],
            "weather": adaptive["local_weather"],
            "forecast": {**adaptive["forecast"], "days": []},
            "tanks": {"reservoir_observed_at": NOW.isoformat(),
                      "reservoir_fraction": [4, 4]},
            # This is the canonical reader shape: balances are on the evidence
            # zones while adaptive_management contains governed policy zones.
            "irrigation": {
                "zones": [
                    {"zone_id": "B12345", "water_balance": {
                        "status": "Available", "ledger_current": True,
                        "obligation_effect": "satisfied",
                        "partial_obligation_credit": 1.0,
                        "remaining_water_need_mm": 0,
                        "schedule_debt_rewritten": False,
                    }},
                    {"zone_id": "C12345", "water_balance": {
                        "status": "Available", "ledger_current": True,
                        "obligation_effect": "no credit",
                        "partial_obligation_credit": 0.0,
                        "remaining_water_need_mm": 14.0,
                        "schedule_debt_rewritten": False,
                    }},
                ],
                "adaptive_management": {
                    "enabled": True,
                    "zones": [
                        {"zone_id": "B12345", "visible_need": "dry",
                         "visible_need_observed_at": NOW.isoformat(),
                         "visible_need_source": "owner_observation"},
                        {"zone_id": "C12345", "visible_need": "dry",
                         "visible_need_observed_at": NOW.isoformat(),
                         "visible_need_source": "owner_observation"},
                    ],
                    "target_days_per_week": 4,
                },
            },
            "irrigation_history": {},
            "water_demand": {"status": "standing_essential"},
        }
        tasks = {row["task_id"]: row for row in
                 build_water_energy_plan(plan_evidence, now=NOW)["candidate_tasks"]}
        self.assertEqual(tasks["irrigation_B12345"]["zone_decision"], "Hold")
        self.assertEqual(tasks["irrigation_C12345"]["zone_decision"], "Run now")
        self.assertIn(
            "effective rainfall provisionally satisfied",
            tasks["irrigation_B12345"]["reason"],
        )

    def test_partial_water_balance_reduces_need_but_preserves_remaining_work(self):
        item=evidence()
        item["zones"][1]["water_balance"]={"status":"Available",
            "ledger_current":True,
            "obligation_effect":"partial credit","partial_obligation_credit":0.5,
            "remaining_water_need_mm":7.0,"schedule_debt_rewritten":False}
        result=zones(build_adaptive_irrigation_decisions(item,now=NOW))["C12345"]
        self.assertIn(result["decision"],{"Run now","Run later","Hold"})
        self.assertEqual(result["water_balance"]["remaining_water_need_mm"],7.0)

    def test_trace_rain_balance_holds_without_schedule_credit(self):
        item=evidence()
        item["zones"][0]["water_balance"]={"status":"Available",
            "ledger_current":True,
            "obligation_effect":"Hold with no credit","partial_obligation_credit":0,
            "remaining_water_need_mm":14.0,"schedule_debt_rewritten":False}
        result=zones(build_adaptive_irrigation_decisions(item,now=NOW))["B12345"]
        self.assertEqual(result["decision"],"Hold")
        self.assertIn("earns no water",result["reason"])
        self.assertEqual(result["weekly_obligation"]["delivery_debt_days"],1)


if __name__ == "__main__":
    unittest.main()
