import unittest
from datetime import datetime
from decimal import Decimal
from unittest import mock

from modules.telemetry.rootline_water_energy_plan import (
    AUTHORITY,
    OPERATING_KNOWLEDGE,
    build_water_energy_plan,
    append_water_energy_plan,
    _normalize_forecast,
    _read_historical_context,
    _read_latest_tank_observation,
    _read_recent_irrigation_history,
    read_current_water_energy_evidence,
)


NOW = datetime.fromisoformat("2026-07-28T12:00:00+02:00")


def evidence(**overrides):
    base = {
        "power": {
            "observed_at": "2026-07-28T11:58:00+02:00",
            "stale_after_minutes": 15,
            "battery_soc_pct": 75,
            "solar_power_w": 3500,
            "load_power_w": 900,
            "grid_power_w": 0,
        },
        "weather": {
            "observed_at": "2026-07-28T11:58:00+02:00",
            "stale_after_minutes": 30,
            "rain_rate_mm_h": 0,
        },
        "forecast": {
            "observed_at": "2026-07-28T10:00:00+02:00",
            "stale_after_minutes": 360,
            "days": [{"rain_sum_mm": 0, "rain_probability_max_pct": 10}],
        },
        "tanks": {
            "storage_reported_count": 4,
            "reservoir_reported_count": 8,
            "storage_state": "OK",
            "reservoir_state": "OK",
            "observed_at": "2026-07-28T10:00:00+02:00",
            "reporter": "owner",
            "source": "owner_dashboard",
        },
        "water_demand": {"status": "needed"},
        "irrigation": {
            "zones": [
                {"zone_id": "B12345", "recommendation": "Needs Data"},
                {"zone_id": "C12345", "recommendation": "Hold"},
            ]
        },
        "history": {"status": "Available", "confidence": "medium"},
    }
    base.update(overrides)
    return base


class WaterEnergyPlanTests(unittest.TestCase):
    def build(self, **changes):
        return build_water_energy_plan(evidence(**changes), "2026-07-28", now=NOW)

    def task(self, plan, task_id):
        return next(item for item in plan["candidate_tasks"] if item["task_id"] == task_id)

    def test_sunny_mixed_poor_and_dynamic_reserve(self):
        sunny = self.build()
        self.assertEqual(sunny["forecast"]["solar_profile"], "sunny")
        self.assertEqual(sunny["battery_reserve"]["governing_reserve_soc_pct"], 63)

        mixed = self.build(forecast={
            "observed_at": "2026-07-28T10:00:00+02:00",
            "stale_after_minutes": 360,
            "days": [{"rain_sum_mm": 2, "rain_probability_max_pct": 45}],
        })
        self.assertEqual(mixed["battery_reserve"]["governing_reserve_soc_pct"], 67)

        poor = self.build(forecast={
            "observed_at": "2026-07-28T10:00:00+02:00",
            "stale_after_minutes": 360,
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}],
        })
        self.assertEqual(poor["battery_reserve"]["governing_reserve_soc_pct"], 70)

    def test_production_forecast_timestamp_contract_is_normalized(self):
        result = _normalize_forecast({
            "success": True,
            "source": {
                "last_forecast_run_at": "2026-07-28T10:00:00+02:00",
                "stale_after_minutes": 360,
            },
            "days": [],
        })
        self.assertEqual(result["observed_at"], "2026-07-28T10:00:00+02:00")

    def test_stale_forecast_only_blocks_forecast_optimization(self):
        plan = self.build(forecast={
            "observed_at": "2026-07-27T10:00:00+02:00",
            "stale_after_minutes": 360,
            "days": [{"rain_sum_mm": 0, "rain_probability_max_pct": 0}],
        })
        self.assertEqual(plan["forecast"]["status"], "stale")
        self.assertEqual(plan["forecast"]["forecast_dependent_optimization"], "Unavailable")
        self.assertEqual(plan["current_power"]["status"], "fresh")
        self.assertTrue(plan["candidate_tasks"])

    def test_current_rain_avoids_unnecessary_borehole(self):
        wet = evidence()["weather"] | {"rain_rate_mm_h": 0.21}
        plan = self.build(weather=wet, water_demand={"status": "normal"})
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Do Not Run")

    def test_forecast_rain_avoids_nonurgent_borehole(self):
        wet_forecast = evidence()["forecast"] | {
            "days": [{"rain_sum_mm": 8, "rain_probability_max_pct": 80}]
        }
        plan = self.build(forecast=wet_forecast, water_demand={"status": "normal"})
        self.assertTrue(plan["rain_capture"]["borehole_avoidance_signal"])
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Do Not Run")

    def test_rain_hold_release_requires_complete_active_policy_evidence(self):
        incomplete = evidence()["weather"] | {"rain_rate_mm_h": 0}
        held = self.build(weather=incomplete, water_demand={"status": "normal"})
        self.assertEqual(held["rain_capture"]["rain_hold_state"], "Unknown")
        self.assertEqual(self.task(held, "borehole")["recommendation"], "Hold")
        recommend_zone = evidence()["irrigation"] | {
            "zones": [{"zone_id": "B12345", "recommendation": "Recommend"}]
        }
        held_zone = self.build(
            weather=incomplete, irrigation=recommend_zone,
            water_demand={"status": "normal"},
        )
        self.assertEqual(
            self.task(held_zone, "irrigation_B12345")["recommendation"], "Hold"
        )
        complete = incomplete | {
            "dry_interval_minutes": 30,
            "fresh_readings_during_dry_interval": 2,
            "source_healthy": True,
            "conflicting": False,
        }
        released = self.build(weather=complete, water_demand={"status": "normal"})
        self.assertTrue(released["rain_capture"]["dry_release_proven"])

    def test_low_soc_and_absolute_floor(self):
        low = evidence()["power"] | {"battery_soc_pct": 39}
        plan = self.build(power=low)
        self.assertTrue(plan["battery_reserve"]["below_absolute_floor"])
        self.assertFalse(plan["battery_reserve"]["discretionary_battery_energy_available"])

    def test_stale_power_never_proves_discretionary_energy(self):
        stale = evidence()["power"] | {"observed_at": "2026-07-27T11:58:00+02:00"}
        plan = self.build(power=stale)
        self.assertEqual(plan["battery_reserve"]["power_evidence_status"], "stale")
        self.assertFalse(plan["battery_reserve"]["discretionary_battery_energy_available"])

    def test_missing_tanks_does_not_erase_power_and_blocks_water_conclusions(self):
        plan = self.build(tanks={})
        self.assertEqual(plan["tank_evidence"]["status"], "Unavailable")
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Needs Data")
        self.assertEqual(plan["current_power"]["battery_soc_pct"], 75)

    def test_storage_full_and_urgent_grid_continuity(self):
        full = evidence()["tanks"] | {"storage_reported_count": 5, "storage_state": "FULL"}
        plan = self.build(tanks=full, water_demand={"status": "normal"})
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Do Not Run")

        low_power = evidence()["power"] | {"battery_soc_pct": 45}
        urgent = self.build(power=low_power, water_demand={"status": "urgent"})
        borehole = self.task(urgent, "borehole")
        self.assertEqual(borehole["recommendation"], "Recommend")
        self.assertTrue(borehole["could_use_grid"])
        self.assertEqual(urgent["estimated_grid_exposure"]["estimated_kwh"], "Unavailable")

    def test_irrigation_hold_remains_hold(self):
        plan = self.build()
        self.assertEqual(self.task(plan, "irrigation_C12345")["recommendation"], "Hold")

    def test_fertilizer_is_typed_only_as_auxiliary_work(self):
        plan=self.build()
        self.assertFalse(any("fertilizer" in row["task_id"]
                             for row in plan["candidate_tasks"]))
        self.assertEqual(plan["irrigation_auxiliary_devices"],
                         ["FERTILIZER-INJECTION-CH1","FERTILIZER-MIXER-CH2"])
        self.assertEqual({row["device_type"] for row in plan["irrigation_auxiliary_tasks"]},
                         {"fertilizer_injection_valve","fertilizer_mixer"})

    def test_unused_channels_and_unproven_binding(self):
        fertilizer = OPERATING_KNOWLEDGE["fertilizer"]
        self.assertEqual(fertilizer["channels"]["3"], "unused")
        self.assertEqual(fertilizer["channels"]["4"], "unused")
        self.assertEqual(fertilizer["maximum_injection_pulse_seconds"], 120)
        self.assertFalse(fertilizer["supervised_identity_proven"])

    def test_stale_manual_observation(self):
        stale = evidence()["tanks"] | {"observed_at": "2026-07-26T10:00:00+02:00"}
        plan = self.build(tanks=stale)
        self.assertEqual(plan["tank_evidence"]["status"], "stale")
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Needs Data")

    def test_conflicting_or_malformed_time_evidence_fails_closed(self):
        plan = self.build(power={"observed_at": "malformed", "battery_soc_pct": 80})
        self.assertEqual(plan["current_power"]["status"], "Unavailable")
        future = self.build(tanks=evidence()["tanks"] | {
            "observed_at": "2026-07-29T10:00:00+02:00"
        })
        self.assertEqual(future["tank_evidence"]["status"], "Unavailable")

    def test_identity_is_stable_and_material_evidence_changes_generation_hash(self):
        first = self.build()
        replay = self.build()
        changed = self.build(power=evidence()["power"] | {"battery_soc_pct": 74})
        self.assertEqual(first["plan_id"], replay["plan_id"])
        self.assertEqual(first["evidence_sha256"], replay["evidence_sha256"])
        self.assertNotEqual(first["evidence_sha256"], changed["evidence_sha256"])

        noise = self.build(power=evidence()["power"] | {
            "solar_power_w": 3510,
            "load_power_w": 910,
            "grid_power_w": 5,
        })
        self.assertEqual(first["evidence_sha256"], noise["evidence_sha256"])
        tank_changed = self.build(tanks=evidence()["tanks"] | {"storage_state": "LOW"})
        self.assertNotEqual(first["evidence_sha256"], tank_changed["evidence_sha256"])

    def test_zero_authority_and_outcome_separation(self):
        plan = self.build()
        self.assertTrue(all(value is False for value in AUTHORITY.values()))
        self.assertEqual(plan["outcome_separation"]["delivered_volume"], "Unavailable")
        for task in plan["candidate_tasks"]:
            self.assertFalse(task["command_created"])
            self.assertFalse(task["dispatchable"])
            self.assertFalse(task["physical_water_flow_confirmed"])

    def test_owner_policy_builds_explicit_b_plan_without_crop_sensor_evidence(self):
        plan = self.build(
            forecast={
                "observed_at": "2026-07-27T10:00:00+02:00",
                "stale_after_minutes": 360,
                "days": [{"rain_sum_mm": 0, "rain_probability_max_pct": 0}],
            },
            water_demand={},
            tanks=evidence()["tanks"] | {"reservoir_reported_count": 9},
            irrigation={
                "owner_candidate": {
                    "zone_id": "B12345",
                    "operating_date": "2026-07-28",
                    "source": "owner_confirmed_test",
                },
                "zones": [
                    {"zone_id": "B12345", "recommendation": "Hold"},
                    {"zone_id": "C12345", "recommendation": "Hold"},
                ]
            },
        )
        b_camp = self.task(plan, "irrigation_B12345")
        self.assertEqual(b_camp["recommendation"], "Recommend")
        self.assertEqual(b_camp["planned_duration_minutes"], 120)
        self.assertEqual(b_camp["planned_start_at"], "12:30 SAST")
        self.assertIn("Crop/soil evidence is unavailable", b_camp["reason"])
        self.assertTrue(b_camp["advisory_plan_supported"])
        self.assertTrue(b_camp["actuation_blocked"])
        self.assertEqual(plan["water_demand"]["status"], "standing_essential")
        self.assertEqual(plan["forecast"]["status"], "stale")

    def test_missing_reservoir_blocks_irrigation_not_storage_borehole_conclusion(self):
        tanks = evidence()["tanks"] | {
            "reservoir_reported_count": None,
            "reservoir_observed_at": None,
            "storage_observed_at": "2026-07-28T10:00:00+02:00",
        }
        plan = self.build(tanks=tanks, water_demand={})
        self.assertEqual(self.task(plan, "irrigation_B12345")["recommendation"], "Hold")
        self.assertNotEqual(self.task(plan, "borehole")["recommendation"], "Needs Data")
        self.assertEqual(plan["tank_evidence"]["storage_freshness"], "fresh")
        self.assertEqual(plan["tank_evidence"]["reservoir_freshness"], "Unavailable")

    def test_fraction_evidence_preserves_half_storage_and_full_reservoir(self):
        tanks=evidence()["tanks"] | {"storage_reported_count":None,"reservoir_reported_count":None,
            "storage_fraction":[2,4],"reservoir_fraction":[4,4],
            "storage_state":"OK","reservoir_state":"FULL"}
        plan=self.build(tanks=tanks)
        self.assertEqual(plan["tank_evidence"]["storage_reported_count"],2)
        self.assertEqual(plan["tank_evidence"]["storage_total_count"],4)
        self.assertEqual(plan["tank_evidence"]["reservoir_reported_count"],4)
        self.assertEqual(plan["tank_evidence"]["reservoir_total_count"],4)
        self.assertEqual(plan["tank_evidence"]["reservoir_state"],"FULL")
        self.assertNotEqual(self.task(plan,"borehole")["recommendation"],"Needs Data")
        self.assertNotEqual(self.task(plan,"solar_transfer_pump")["recommendation"],"Needs Data")

    def test_independent_tank_rows_are_composed_with_exact_timestamps(self):
        connection = mock.MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.side_effect = [
            (3, None, "Unknown", "Unknown",
             datetime.fromisoformat("2026-08-01T13:16:52+02:00"), "storage-owner", "telegram-3150"),
            (None, 9, "Unknown", "Unknown",
             datetime.fromisoformat("2026-08-01T12:01:41+02:00"), "reservoir-owner", "telegram-3146"),
        ]
        with mock.patch("psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            result = _read_latest_tank_observation("postgresql://production-shaped")
        self.assertEqual(result["storage_reported_count"], 3)
        self.assertEqual(result["reservoir_reported_count"], 9)
        self.assertEqual(result["storage_observed_at"], "2026-08-01T13:16:52+02:00")
        self.assertEqual(result["reservoir_observed_at"], "2026-08-01T12:01:41+02:00")
        self.assertEqual(result["storage_reporter"], "storage-owner")
        self.assertEqual(result["storage_source"], "telegram-3150")
        self.assertEqual(result["reservoir_reporter"], "reservoir-owner")
        self.assertEqual(result["reservoir_source"], "telegram-3146")

    def test_recent_history_excludes_stopped_and_future_completion_evidence(self):
        connection = mock.MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (NOW,)
        cursor.fetchall.return_value = []
        with mock.patch("psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            result = _read_recent_irrigation_history(
                "postgresql://production-shaped", NOW
            )
        sql, params = next(call.args for call in cursor.execute.call_args_list
                           if "from public.irrigation_events" in call.args[0])
        self.assertIn("public.irrigation_events", sql)
        self.assertEqual(params, ("PLANNING_EPOCH_STARTED",))
        self.assertTrue(connection.read_only)
        self.assertEqual(result["zones"]["B12345"]["coverage_status"], "Unavailable")

    def test_append_database_failure_returns_fail_closed_response(self):
        plan = self.build()
        with mock.patch("psycopg.connect", side_effect=RuntimeError("offline")):
            result, status = append_water_energy_plan(
                plan, "owner-admin:test", "postgresql://example"
            )
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "water_energy_plan_append_failed")
        self.assertEqual(result["authority"], AUTHORITY)

    def test_postgres_decimal_history_is_json_serializable(self):
        import json
        connection = mock.MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = (
            7, Decimal("96.5"), Decimal("12.34"), Decimal("111.06")
        )
        with mock.patch("psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            history = _read_historical_context("postgresql://production-shaped")
        self.assertEqual(history["average_coverage_pct"], 96.5)
        self.assertEqual(history["estimated_grid_import_kwh"], 12.34)
        self.assertEqual(
            history["estimated_grid_cost_at_schema_tariff_zar"], 111.06
        )
        json.dumps(history)

        cursor.fetchone.return_value = (0, None, None, None)
        with mock.patch("psycopg.connect") as connect:
            connect.return_value.__enter__.return_value = connection
            empty = _read_historical_context("postgresql://production-shaped")
        self.assertIsNone(empty["average_coverage_pct"])
        json.dumps(empty)

    @mock.patch("modules.telemetry.rootline_water_energy_plan._read_latest_tank_observation",
                return_value={})
    @mock.patch("modules.telemetry.rootline_water_energy_plan._read_recent_irrigation_history",
                return_value={})
    @mock.patch("modules.telemetry.rootline_water_energy_plan._read_historical_context",
                return_value={})
    @mock.patch("modules.telemetry.rootline_daily_advisor.get_rootline_daily_advisor",
                return_value=({"zones": []}, 200))
    @mock.patch("modules.telemetry.weather_service.get_weather_forecast",
                return_value=({}, 200))
    @mock.patch("modules.telemetry.weather_service.get_current_weather_state",
                return_value=({}, 200))
    @mock.patch("modules.telemetry.power_service.get_current_power_state",
                return_value=({}, 200))
    def test_canonical_reader_supplies_deployed_adaptive_bc_management(self, *_mocks):
        current, _, _ = read_current_water_energy_evidence(now=NOW)
        adaptive=current["irrigation"]["adaptive_management"]
        self.assertTrue(adaptive["enabled"])
        self.assertEqual([row["zone_id"] for row in adaptive["zones"]],
                         ["B12345", "C12345"])
        self.assertEqual(adaptive["max_execution_minutes"], 60)
        self.assertFalse(adaptive["simultaneous_zones_allowed"])

    @mock.patch("modules.telemetry.rootline_bounded_read_group.run_bounded_read_group")
    def test_current_reader_outer_bound_exceeds_nested_advisor_contract(self, bounded):
        bounded.return_value = {
            "power": ({}, 200), "weather": ({}, 200), "forecast": ({}, 200),
            "advisor": ({"zones": []}, 200), "balances": {}, "history": {},
            "irrigation_history": {}, "tanks": {}, "owner_zone_need": {},
        }
        read_current_water_energy_evidence(now=NOW)
        self.assertEqual(bounded.call_args.kwargs["max_workers"], 4)
        self.assertEqual(bounded.call_args.kwargs["deadline_seconds"], 25)

    def test_authenticated_current_c_need_survives_adaptive_projection_and_ranks_c_first(self):
        item=evidence()
        item["irrigation"]={
            "zones":[{"zone_id":"B12345"},{"zone_id":"C12345",
                "visible_need":"visible_need","visible_need_observed_at":NOW.isoformat(),
                "visible_need_source":"oom_sakkie_authenticated_operational_intake"}],
            "adaptive_management":{"enabled":True,"zones":[
                {"zone_id":"B12345"},{"zone_id":"C12345"}],
                "target_days_per_week":4}}
        item["irrigation_history"]={"status":"Available","zones":{
            zone:{"events":[],"complete_through":NOW.isoformat()} for zone in ("B12345","C12345")}}
        plan=build_water_energy_plan(item,"2026-07-28",now=NOW)
        tasks={row["task_id"]:row for row in plan["candidate_tasks"]}
        self.assertGreater(tasks["irrigation_C12345"]["need_score"],
                           tasks["irrigation_B12345"]["need_score"])
        self.assertEqual(tasks["irrigation_C12345"]["rank"],1)


if __name__ == "__main__":
    unittest.main()
