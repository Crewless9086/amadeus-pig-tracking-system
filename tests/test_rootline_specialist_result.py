import unittest
from datetime import datetime

from modules.telemetry.rootline_specialist_result import (
    FORECAST_RAIN_MAX_DELAY_MINUTES,
    RECOMMENDATION_IDS,
    RESULT_AUTHORITY,
    build_rootline_specialist_result,
    project_water_energy_plan,
    reconsider_rootline_forecast_hold,
)


NOW = datetime.fromisoformat("2026-07-29T12:00:00+02:00")


def evidence(**overrides):
    base = {
        "power": {
            "observed_at": "2026-07-29T11:58:00+02:00",
            "stale_after_minutes": 15,
            "battery_soc_pct": 75,
            "solar_power_w": 3500,
            "load_power_w": 900,
            "grid_power_w": 0,
        },
        "weather": {
            "observed_at": "2026-07-29T11:58:00+02:00",
            "stale_after_minutes": 30,
            "rain_rate_mm_h": 0,
            "rain_today_mm": 0,
            "rain_today_unchanged": True,
            "dry_interval_minutes": 30,
            "fresh_readings_during_dry_interval": 2,
            "temperature_c": 24,
            "wind_speed_kmh": 8,
        },
        "forecast": {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "stale_after_minutes": 360,
            "days": [{"rain_sum_mm": 0, "rain_probability_max_pct": 10}],
        },
        "tanks": {
            "storage_reported_count": 4,
            "reservoir_reported_count": 8,
            "storage_state": "OK",
            "reservoir_state": "OK",
            "observed_at": "2026-07-29T10:00:00+02:00",
            "reporter": "owner:family",
            "source": "oom_sakkie_owner",
        },
        "water_demand": {"status": "needed"},
        "irrigation": {
            "zones": [
                {"zone_id": "B12345", "recommendation": "Recommend"},
                {"zone_id": "C12345", "recommendation": "Hold"},
            ]
        },
        "history": {"status": "Available", "confidence": "medium"},
    }
    base.update(overrides)
    return base


class RootlineSpecialistResultTests(unittest.TestCase):
    def build(self, now=NOW, **changes):
        return build_rootline_specialist_result(
            evidence(**changes), "2026-07-29", now=now
        )

    def recommendation(self, result, subject):
        return next(
            item for item in result["recommendations"]
            if item["subject"] == subject
        )

    def test_contract_identity_freshness_provenance_and_complete_subjects(self):
        result = self.build()
        self.assertTrue(result["result_id"].startswith("ROOTLINE-RESULT-20260729-"))
        self.assertEqual(result["evidence"]["freshness"]["power"], "fresh")
        self.assertEqual(
            result["evidence"]["provenance"]["forecast"],
            "caller_supplied_canonical_shaped_forecast_read_model",
        )
        self.assertEqual(
            tuple(item["subject"] for item in result["recommendations"]),
            RECOMMENDATION_IDS,
        )
        self.assertNotEqual(result["current_local_weather"], result["forecast"])
        self.assertFalse(result["current_local_weather"]["is_forecast"])
        self.assertFalse(result["forecast"]["is_current_local_weather"])

    def test_actual_builder_prefers_current_execution_over_historical_completion(self):
        history = {"zones": {"B12345": {"events": [{
            "qualifies_as_completed_watering": True, "shutdown_verified": True,
            "verified_runtime_minutes": 59.9833}], "latest_execution": {
                "action": "mark_active", "state": "Active",
                "execution_id": "ROOTLINE-EXECUTION-CURRENT"}},
            "C12345": {"events": []}}}
        result = self.build(irrigation_history=history)
        self.assertEqual(result["irrigation_lifecycle"]["B12345"]["state"], "Started")
        text = __import__("modules.oom_sakkie.rootline_daily_presentation", fromlist=[
            "compose_daily_rootline_plan"]).compose_daily_rootline_plan(result)
        self.assertIn("Lifecycle: Started", text)
        self.assertNotIn("59.9833 minutes", text)

    def test_plan_projection_retains_timing_cadence_and_recovery(self):
        plan = {
            "success": True,
            "operating_date": "2026-08-01",
            "evidence_generation": "ABC123",
            "evidence_observed_at": "2026-08-01T12:40:00+00:00",
            "current_power": {"status": "fresh"},
            "forecast": {"status": "stale"},
            "tank_evidence": {"status": "fresh"},
            "candidate_tasks": [{
                "task_id": "irrigation_B12345",
                "recommendation": "Recommend",
                "reason": "Dated owner candidate.",
                "preferred_window": "15:00 SAST",
                "planned_start_at": "15:00 SAST",
                "planned_duration_minutes": 120,
                "weekly_cadence": {
                    "target_days_per_week": 4,
                    "completed_days_last_7_days": None,
                },
                "recommendation_source": "owner_confirmed_ROOTLINE_policy_20260801",
                "advisory_plan_supported": True,
                "actuation_blocked": True,
            }],
            "reassessment": {
                "next_time_or_trigger": "15:00 SAST",
                "triggers": ["observed_rain"],
            },
            "recovery_handling": "Reconsider at the next suitable window; no command replay.",
        }
        result = project_water_energy_plan(plan, now=NOW)
        b_camp = self.recommendation(result, "B12345")
        self.assertEqual(b_camp["planned_start_at"], "15:00 SAST")
        self.assertEqual(b_camp["planned_duration_minutes"], 120)
        self.assertEqual(b_camp["weekly_cadence"]["target_days_per_week"], 4)
        self.assertTrue(b_camp["actuation_blocked"])
        self.assertEqual(result["next_reassessment"]["at"], "15:00 SAST")
        self.assertIn("no command replay", result["next_reassessment"]["recovery_if_window_is_missed"])

    def test_fresh_and_stale_power_and_conflict_are_localized(self):
        fresh = self.build()
        self.assertEqual(fresh["current_power"]["status"], "fresh")
        stale = self.build(power=evidence()["power"] | {
            "observed_at": "2026-07-29T10:00:00+02:00"
        })
        self.assertEqual(stale["current_power"]["status"], "stale")
        self.assertTrue(stale["recommendations"])
        conflict = self.build(power=evidence()["power"] | {"conflicting": True})
        self.assertEqual(conflict["current_power"]["status"], "conflicting")
        self.assertTrue(conflict["recommendations"])

    def test_weather_and_forecast_remain_separate_and_missing_is_local(self):
        result = self.build(forecast={})
        self.assertEqual(result["forecast"]["status"], "Unavailable")
        self.assertEqual(result["current_local_weather"]["status"], "fresh")
        self.assertEqual(
            self.recommendation(result, "B12345")["status"], "Recommend"
        )

    def test_forecast_rain_only_creates_bounded_hold(self):
        wet = evidence()["forecast"] | {
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}]
        }
        result = self.build(forecast=wet)
        borehole = self.recommendation(result, "borehole")
        self.assertEqual(borehole["status"], "Hold")
        self.assertEqual(
            result["next_reassessment"]["maximum_delay_minutes"],
            FORECAST_RAIN_MAX_DELAY_MINUTES,
        )
        self.assertIn(
            "not observed rain", result["forecast"]["uncertainty"].lower()
        )

    def test_b_plan_window_does_not_mask_bounded_borehole_forecast_reassessment(self):
        wet = evidence()["forecast"] | {
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}]
        }
        irrigation = evidence()["irrigation"] | {
            "owner_candidate": {
                "zone_id": "B12345",
                "operating_date": "2026-07-29",
                "source": "owner_confirmed_test",
            }
        }
        tanks = evidence()["tanks"] | {"reservoir_reported_count": 9}
        result = self.build(forecast=wet, irrigation=irrigation, tanks=tanks)
        self.assertEqual(
            result["next_reassessment"]["trigger"],
            "bounded_forecast_rain_check",
        )
        self.assertEqual(
            result["next_reassessment"]["maximum_delay_minutes"],
            FORECAST_RAIN_MAX_DELAY_MINUTES,
        )
        self.assertIn(
            "reconsider supported water work",
            result["next_reassessment"]["recovery_if_rain_does_not_occur"],
        )

    def test_forecast_rain_not_materialized_releases_suppression(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T08:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        result = self.build(forecast=wet)
        borehole = self.recommendation(result, "borehole")
        self.assertEqual(borehole["status"], "Recommend")
        self.assertIn("delay expired", borehole["reason"])

    def test_adaptive_follow_up_reconsiders_hold_on_bounded_timeline(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        initial = self.build(forecast=wet, tanks={})
        self.assertEqual(
            self.recommendation(initial, "borehole")["status"],
            "Hold",
        )
        self.assertEqual(
            initial["next_reassessment"]["at"],
            "2026-07-29T13:00:00+02:00",
        )
        before_deadline = reconsider_rootline_forecast_hold(
            initial,
            evidence(
                forecast=wet,
                tanks={},
                weather=evidence()["weather"] | {
                    "observed_at": "2026-07-29T12:59:00+02:00",
                },
            ),
            now=datetime.fromisoformat("2026-07-29T12:59:00+02:00"),
        )
        self.assertEqual(
            self.recommendation(before_deadline, "borehole")["status"],
            "Hold",
        )
        self.assertEqual(
            before_deadline["next_reassessment"]["at"],
            "2026-07-29T13:00:00+02:00",
        )
        after_deadline = reconsider_rootline_forecast_hold(
            initial,
            evidence(
                forecast=wet,
                tanks={},
                weather=evidence()["weather"] | {
                    "observed_at": "2026-07-29T13:01:00+02:00",
                    "rain_rate_mm_h": 0,
                    "rain_today_mm": 0,
                },
            ),
            now=datetime.fromisoformat("2026-07-29T13:01:00+02:00"),
        )
        borehole = self.recommendation(after_deadline, "borehole")
        self.assertEqual(borehole["status"], "Recommend")
        self.assertIn("water-continuity", borehole["reason"])
        self.assertIn("Grid may be used only", borehole["reason"])
        self.assertEqual(
            after_deadline["follow_up"]["outcome"],
            "released_no_observed_rain",
        )
        self.assertFalse(
            after_deadline["follow_up"]["observed_rain_materialized"]
        )
        self.assertEqual(
            after_deadline["water_observations"]["status"],
            "Unavailable",
        )
        self.assertNotEqual(
            after_deadline["next_reassessment"]["trigger"],
            "bounded_forecast_rain_check",
        )
        self.assertIn(
            "local_weather_change",
            after_deadline["next_reassessment"]["also_on"],
        )
        self.assertEqual(
            after_deadline["battery_policy"]["absolute_floor_soc_pct"],
            40,
        )
        self.assertEqual(
            after_deadline["battery_policy"][
                "provisional_working_reserve_soc_pct"
            ],
            50,
        )
        self.assertGreater(
            after_deadline["battery_policy"]["governing_reserve_soc_pct"],
            50,
        )
        self.assertLessEqual(len(after_deadline["owner_questions"]), 1)

    def test_follow_up_cannot_restart_expired_hold_with_new_forecast(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        initial = self.build(forecast=wet)
        refreshed_wet = wet | {
            "observed_at": "2026-07-29T12:58:00+02:00",
        }
        follow_up = reconsider_rootline_forecast_hold(
            initial,
            evidence(
                forecast=refreshed_wet,
                weather=evidence()["weather"] | {
                    "observed_at": "2026-07-29T13:01:00+02:00",
                    "rain_rate_mm_h": 0,
                    "rain_today_mm": 0,
                },
            ),
            now=datetime.fromisoformat("2026-07-29T13:01:00+02:00"),
        )
        self.assertEqual(
            self.recommendation(follow_up, "borehole")["status"],
            "Recommend",
        )
        self.assertEqual(
            follow_up["follow_up"]["outcome"],
            "released_no_observed_rain",
        )
        self.assertNotEqual(
            follow_up["next_reassessment"]["trigger"],
            "bounded_forecast_rain_check",
        )

    def test_follow_up_requires_fresh_unconflicted_local_no_rain(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        initial = self.build(forecast=wet)
        cases = (
            {},
            evidence()["weather"] | {
                "observed_at": "2026-07-29T11:00:00+02:00",
            },
            evidence()["weather"] | {
                "observed_at": "2026-07-29T13:01:00+02:00",
                "conflicting": True,
            },
        )
        for weather in cases:
            with self.subTest(weather=weather):
                follow_up = reconsider_rootline_forecast_hold(
                    initial,
                    evidence(forecast=wet, weather=weather),
                    now=datetime.fromisoformat(
                        "2026-07-29T13:01:00+02:00"
                    ),
                )
                borehole = self.recommendation(follow_up, "borehole")
                self.assertEqual(borehole["status"], "Hold")
                self.assertIn("fresh current local weather", borehole["reason"])
                self.assertEqual(
                    follow_up["follow_up"]["outcome"],
                    "reconsidered_current_weather_unavailable",
                )
                self.assertNotEqual(
                    follow_up["next_reassessment"]["trigger"],
                    "bounded_forecast_rain_check",
                )

    def test_weather_wait_preserves_original_deadline_across_follow_ups(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        initial = self.build(forecast=wet)
        waiting_for_weather = reconsider_rootline_forecast_hold(
            initial,
            evidence(forecast=wet, weather={}),
            now=datetime.fromisoformat("2026-07-29T13:01:00+02:00"),
        )
        self.assertEqual(
            waiting_for_weather["follow_up"]["forecast_hold_deadline"],
            "2026-07-29T13:00:00+02:00",
        )
        refreshed_wet = wet | {
            "observed_at": "2026-07-29T13:09:00+02:00",
        }
        released = reconsider_rootline_forecast_hold(
            waiting_for_weather,
            evidence(
                forecast=refreshed_wet,
                weather=evidence()["weather"] | {
                    "observed_at": "2026-07-29T13:10:00+02:00",
                    "rain_rate_mm_h": 0,
                    "rain_today_mm": 0,
                },
            ),
            now=datetime.fromisoformat("2026-07-29T13:10:00+02:00"),
        )
        self.assertEqual(
            self.recommendation(released, "borehole")["status"],
            "Recommend",
        )
        self.assertEqual(
            released["follow_up"]["forecast_hold_deadline"],
            "2026-07-29T13:00:00+02:00",
        )
        self.assertEqual(
            released["follow_up"]["outcome"],
            "released_no_observed_rain",
        )

    def test_adaptive_follow_up_keeps_observed_rain_separate_from_forecast(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        initial = self.build(forecast=wet)
        follow_up = reconsider_rootline_forecast_hold(
            initial,
            evidence(
                forecast=wet,
                weather=evidence()["weather"] | {
                    "observed_at": "2026-07-29T13:01:00+02:00",
                    "rain_rate_mm_h": 1.2,
                    "rain_today_mm": 2.4,
                },
            ),
            now=datetime.fromisoformat("2026-07-29T13:01:00+02:00"),
        )
        self.assertTrue(follow_up["follow_up"]["observed_rain_materialized"])
        self.assertEqual(
            follow_up["follow_up"]["outcome"],
            "continued_with_observed_rain",
        )
        self.assertFalse(follow_up["current_local_weather"]["is_forecast"])
        self.assertFalse(follow_up["forecast"]["is_current_local_weather"])

    def test_follow_up_returns_one_concise_zero_authority_specialist_result(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        initial = self.build(forecast=wet)
        result = reconsider_rootline_forecast_hold(
            initial,
            evidence(
                forecast=wet,
                tanks={},
                weather=evidence()["weather"] | {
                    "observed_at": "2026-07-29T13:01:00+02:00",
                },
            ),
            now=datetime.fromisoformat("2026-07-29T13:01:00+02:00"),
        )
        self.assertTrue(result["success"])
        self.assertIn("recommend_now", result["owner_brief"])
        self.assertIn("later current local weather", result["owner_brief"]["what_changed"])
        self.assertIn("reassess", result["owner_brief"])
        self.assertLessEqual(len(result["owner_questions"]), 1)
        self.assertTrue(all(value is False for value in result["authority"].values()))
        self.assertEqual(
            self.recommendation(result, "solar_transfer_dependency")[
                "hardware_control"
            ],
            False,
        )

    def test_battery_reserve_bands_and_absolute_floor(self):
        sunny = self.build()
        self.assertEqual(sunny["battery_policy"]["governing_reserve_soc_pct"], 63)
        poor = self.build(forecast=evidence()["forecast"] | {
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}]
        })
        self.assertEqual(poor["battery_policy"]["governing_reserve_soc_pct"], 70)
        low = self.build(power=evidence()["power"] | {"battery_soc_pct": 39})
        self.assertTrue(low["battery_policy"]["below_absolute_floor"])
        self.assertEqual(low["battery_policy"]["absolute_floor_soc_pct"], 40)
        self.assertEqual(
            low["battery_policy"]["provisional_working_reserve_soc_pct"], 50
        )

    def test_unknown_tanks_do_not_globally_block_supported_results(self):
        result = self.build(tanks={})
        self.assertEqual(result["water_observations"]["status"], "Unavailable")
        self.assertEqual(
            self.recommendation(result, "borehole")["status"], "Needs Data"
        )
        self.assertTrue(result["current_power"]["battery_soc_pct"])
        self.assertEqual(len(result["owner_questions"]), 1)
        self.assertFalse(result["owner_questions"][0]["required_now"])

    def test_transfer_pump_is_dependency_never_controllable(self):
        transfer = self.recommendation(self.build(), "solar_transfer_dependency")
        self.assertIn("not controllable", transfer["reason"])
        self.assertNotEqual(transfer["status"], "Recommend")
        self.assertNotIn(
            "solar_transfer_dependency", self.build()["owner_brief"]["recommend_now"]
        )
        self.assertFalse(transfer["command_authority"])
        self.assertFalse(transfer["hardware_control"])

    def test_fresh_dry_weather_preserves_supported_zone_recommendation(self):
        result = self.build()
        zone = self.recommendation(result, "B12345")
        self.assertEqual(zone["status"], "Recommend")
        self.assertIn("fresh current local weather", zone["reason"])

    def test_identity_is_stable_when_only_read_time_changes(self):
        first = self.build(now=NOW)
        second = self.build(
            now=datetime.fromisoformat("2026-07-29T12:01:00+02:00")
        )
        self.assertEqual(first["generation"], second["generation"])
        self.assertEqual(first["result_id"], second["result_id"])

    def test_water_emergency_outranks_grid_avoidance(self):
        result = self.build(
            power=evidence()["power"] | {"battery_soc_pct": 42},
            water_demand={"status": "urgent"},
        )
        borehole = self.recommendation(result, "borehole")
        self.assertEqual(borehole["status"], "Recommend")
        self.assertIn("continuity", borehole["reason"].lower())

    def test_nonurgent_water_near_reserve_with_adequate_tanks_holds(self):
        stale_forecast = evidence()["forecast"] | {
            "observed_at": "2026-07-29T04:00:00+02:00",
        }
        result = self.build(
            power=evidence()["power"] | {"battery_soc_pct": 73},
            forecast=stale_forecast,
            tanks=evidence()["tanks"] | {
                "storage_reported_count": 3.75,
                "reservoir_reported_count": 9,
                "storage_state": "OK",
                "reservoir_state": "OK",
            },
            water_demand={"status": "needed", "urgency": "not_urgent"},
        )
        self.assertEqual(result["battery_policy"]["governing_reserve_soc_pct"], 70)
        self.assertEqual(
            self.recommendation(result, "borehole")["status"],
            "Hold",
        )
        self.assertEqual(result["forecast"]["status"], "stale")

    def test_urgent_water_can_recommend_grid_despite_rain_forecast(self):
        wet = evidence()["forecast"] | {
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        result = self.build(
            forecast=wet,
            tanks={},
            water_demand={"status": "urgent"},
        )
        borehole = self.recommendation(result, "borehole")
        self.assertEqual(borehole["status"], "Recommend")
        self.assertIn("grid may be used", borehole["reason"].lower())

    def test_stale_forecast_cannot_create_forecast_rain_hold(self):
        stale_wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T04:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        result = self.build(forecast=stale_wet)
        self.assertEqual(result["forecast"]["status"], "stale")
        self.assertNotEqual(
            result["next_reassessment"]["trigger"],
            "bounded_forecast_rain_check",
        )

    def test_visible_confirmation_requires_canonical_trusted_boundary(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        initial = self.build(forecast=wet)
        uncertain_weather = {
            "observed_at": "2026-07-29T13:01:00+02:00",
            "stale_after_minutes": 30,
            "rain_rate_mm_h": 0,
            "conflicting": True,
            "no_visible_rain_confirmed": True,
            "visible_rain_actor_authenticated": True,
            "visible_rain_observer": "owner:charl",
            "visible_rain_source": "authenticated_owner_observation",
            "visible_rain_confirmed_at": "2026-07-29T13:01:00+02:00",
        }
        result = reconsider_rootline_forecast_hold(
            initial,
            evidence(forecast=wet, weather=uncertain_weather),
            now=datetime.fromisoformat("2026-07-29T13:01:00+02:00"),
        )
        self.assertEqual(self.recommendation(result, "borehole")["status"], "Hold")
        self.assertEqual(
            result["follow_up"]["visible_confirmation"],
            "required_from_canonical_authenticated_observation",
        )

    def test_visible_fallback_rejects_forged_or_stale_confirmation(self):
        wet = evidence()["forecast"] | {
            "observed_at": "2026-07-29T11:00:00+02:00",
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        }
        initial = self.build(forecast=wet)
        base = {
            "observed_at": "2026-07-29T13:01:00+02:00",
            "stale_after_minutes": 30,
            "rain_rate_mm_h": 0,
            "conflicting": True,
            "no_visible_rain_confirmed": True,
        }
        cases = (
            base,
            base | {
                "visible_rain_actor_authenticated": True,
                "visible_rain_observer": "owner:charl",
                "visible_rain_source": "authenticated_owner_observation",
                "visible_rain_confirmed_at": "2026-07-29T13:01:00+02:00",
            },
            base | {
                "visible_rain_actor_authenticated": True,
                "visible_rain_source": "authenticated_owner_observation",
                "visible_rain_confirmed_at": "2026-07-29T13:01:00+02:00",
            },
            base | {
                "visible_rain_actor_authenticated": True,
                "visible_rain_observer": "owner:charl",
                "visible_rain_source": "authenticated_owner_observation",
                "visible_rain_confirmed_at": "2026-07-29T12:00:00+02:00",
            },
            base | {
                "visible_rain_actor_authenticated": True,
                "visible_rain_observer": "owner:charl",
                "visible_rain_source": "arbitrary_client",
                "visible_rain_confirmed_at": "2026-07-29T13:01:00+02:00",
            },
        )
        for weather in cases:
            with self.subTest(weather=weather):
                result = reconsider_rootline_forecast_hold(
                    initial,
                    evidence(forecast=wet, weather=weather),
                    now=datetime.fromisoformat(
                        "2026-07-29T13:01:00+02:00"
                    ),
                )
                self.assertEqual(
                    self.recommendation(result, "borehole")["status"],
                    "Hold",
                )
                self.assertTrue(
                    all(
                        value is False
                        for value in result["authority"].values()
                    )
                )

    def test_zero_hardware_authority_and_physical_claims(self):
        result = self.build()
        self.assertTrue(all(value is False for value in RESULT_AUTHORITY.values()))
        self.assertEqual(result["outcome_separation"]["water_flow"], "Unavailable")
        self.assertEqual(
            result["outcome_separation"]["delivered_volume"], "Unavailable"
        )
        for recommendation in result["recommendations"]:
            self.assertFalse(recommendation["command_authority"])
            self.assertFalse(recommendation["hardware_control"])
            self.assertFalse(recommendation["schedule_mutation"])
            self.assertFalse(recommendation["workflow_activation"])

    def test_owner_brief_has_action_reason_reassessment_and_one_fact(self):
        result = self.build(tanks={})
        brief = result["owner_brief"]
        self.assertIn("recommend_now", brief)
        self.assertTrue(brief["why"])
        self.assertIn(" at ", brief["reassess"])
        self.assertIn("LOW, OK or FULL", brief["family_fact_needed"])


if __name__ == "__main__":
    unittest.main()
