import unittest
from datetime import datetime, timedelta
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

    def test_current_rain_does_not_enable_ac_backup_during_sunshine(self):
        wet = evidence()["weather"] | {"rain_rate_mm_h": 0.21}
        plan = self.build(weather=wet, water_demand={"status": "normal"})
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Do Not Run")

    def test_forecast_rain_does_not_enable_ac_backup_during_sunshine(self):
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
        self.assertEqual(self.task(held, "borehole")["recommendation"], "Do Not Run")
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
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Do Not Run")
        self.assertEqual(plan["current_power"]["battery_soc_pct"], 75)

    def test_storage_full_and_urgent_grid_continuity(self):
        full = evidence()["tanks"] | {"storage_reported_count": 5, "storage_state": "FULL"}
        plan = self.build(tanks=full, water_demand={"status": "normal"})
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Do Not Run")

        low_power = evidence()["power"] | {"battery_soc_pct": 45, "solar_power_w": 1499}
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
        self.assertEqual(self.task(plan, "borehole")["recommendation"], "Do Not Run")

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
        self.assertEqual(b_camp["planned_start_at"], "now_after_fresh_execution_revalidation")
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
        self.assertEqual(params, (["B12345", "C12345", "A12345", "E12345"], "PLANNING_EPOCH_STARTED"))
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
    @mock.patch("modules.telemetry.rootline_owner_controls.load_runtime_owner_controls", return_value={})
    def test_canonical_reader_supplies_deployed_adaptive_bc_management(self, *_mocks):
        current, _, _ = read_current_water_energy_evidence(now=NOW)
        adaptive=current["irrigation"]["adaptive_management"]
        self.assertTrue(adaptive["enabled"])
        self.assertEqual([row["zone_id"] for row in adaptive["zones"]],
                         ["B12345", "C12345", "A12345", "E12345"])
        self.assertEqual(adaptive["zones"][-1], {"zone_id": "E12345"})
        self.assertEqual(adaptive["max_execution_minutes"], 60)
        self.assertFalse(adaptive["simultaneous_zones_allowed"])

    @mock.patch("modules.telemetry.rootline_bounded_read_group.run_bounded_read_group")
    def test_current_reader_outer_bound_exceeds_nested_advisor_contract(self, bounded):
        bounded.return_value = {
            "power": ({}, 200), "weather": ({}, 200), "forecast": ({}, 200),
            "advisor": ({"zones": []}, 200), "balances": {}, "history": {},
            "irrigation_history": {}, "tanks": {}, "owner_zone_need": {}, "owner_controls": {},
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


class AllHoursDripEligibilityTests(unittest.TestCase):
    def inputs(self, at):
        from tests.test_rootline_execution_authority import inputs
        _, item, controller = inputs(weather_at=at, water_at=at)
        controller["trusted_receipt_at"] = at.isoformat()
        item["tanks"] = {"observed_at":at.isoformat(),
            "reservoir_state":"FULL","reservoir_reported_count":9}
        item["power"] = {}
        item["irrigation"].update(advisor_generated_at=at.isoformat(),
            advisor_operating_date=at.date().isoformat(),
            zones=[{"zone_id":zone,"live_rain_release_proven":True}
                   for zone in ("B12345","C12345")],
            adaptive_management={"enabled":True,"zones":[
                {"zone_id":zone} for zone in ("B12345","C12345","A12345","E12345")]})
        item["irrigation_history"] = {"status":"Available","zones":{
            zone:{"events":[],"complete_through":at.isoformat()}
            for zone in ("B12345","C12345")}}
        return item, controller

    def eligibility(self, item, controller, at, zone):
        from modules.telemetry.rootline_execution_authority import build_execution_eligibility
        plan = build_water_energy_plan(item, now=at)
        result = build_execution_eligibility(plan=plan, evidence=item,
            controller=controller, now=at, enabled_zone_ids={zone})
        return plan, result

    def test_real_planner_and_authority_allow_every_hour_without_power_or_visual_report(self):
        for month in (1,7,10):
            identities = {}
            for hour in range(24):
                at = NOW.replace(month=month, day=8, hour=hour)
                for zone in ("B12345","C12345"):
                    with self.subTest(month=month,hour=hour,zone=zone):
                        item, controller = self.inputs(at)
                        plan, result = self.eligibility(item,controller,at,zone)
                        self.assertTrue(result["eligible"],result)
                        self.assertEqual(result["zone_id"],zone)
                        self.assertEqual(result["operating_date"],at.date().isoformat())
                        self.assertEqual(result["maximum_duration_seconds"],3599)
                        self.assertEqual(result["expected_segment_count"],2)
                        self.assertEqual(result["governed_executable_duration_seconds"],7198)
                        identities.setdefault(zone,result["job_id"])
                        self.assertEqual(result["job_id"],identities[zone])
                        _, replay = self.eligibility(item,controller,at,zone)
                        self.assertEqual(replay["consumption_key"],result["consumption_key"])
                        tasks = [row for row in plan["candidate_tasks"]
                                 if row["task_id"].startswith("irrigation_")]
                        self.assertEqual({row["task_id"] for row in tasks},
                            {"irrigation_A12345","irrigation_B12345","irrigation_C12345","irrigation_E12345"})
                        a = next(row for row in tasks if row["task_id"] == "irrigation_A12345")
                        self.assertEqual(a["zone_decision"], "Needs Data")
                        self.assertIsNone(a["requested_total_duration_minutes"])
                        for row in tasks:
                            if row["task_id"] in {"irrigation_A12345","irrigation_E12345"}:
                                continue
                            self.assertEqual(row["preferred_window"],"now_after_fresh_execution_revalidation")
                            self.assertFalse(row["simultaneous_with_other_zone"])
                            self.assertFalse(row["command_created"])

    def test_all_hours_preserve_weather_debt_water_shutdown_and_repeat_guards(self):
        for hour in range(24):
            at = NOW.replace(month=1,day=8,hour=hour)
            for case in ("rain","stale_weather","dry_release","unknown_ledger",
                         "water_shortage","shutdown_uncertain","completed_today","sibling_on"):
                with self.subTest(hour=hour,case=case):
                    item, controller = self.inputs(at)
                    if case == "rain": item["weather"]["rain_rate_mm_h"] = 1
                    elif case == "stale_weather": item["weather"]["observed_at"] = (at-timedelta(minutes=31)).isoformat()
                    elif case == "dry_release":
                        for row in item["irrigation"]["zones"]: row["live_rain_release_proven"] = False
                    elif case == "unknown_ledger": item["irrigation_history"] = {}
                    elif case == "water_shortage": item["tanks"]["dry_supply"] = True
                    elif case == "shutdown_uncertain":
                        for row in item["irrigation"]["zones"]:
                            row["latest_segment"] = {"segment_number":1,"state":"Failed","shutdown_verified":False}
                    elif case == "completed_today":
                        for zone, row in item["irrigation_history"]["zones"].items():
                            row["events"] = [{"qualifies_as_completed_watering":True,
                                "event_at_sast":at.isoformat(),"shutdown_verified":True,
                                "objective_satisfied":True,"verified_runtime_minutes":120,
                                "execution_id":zone+"-COMPLETED","provenance":"verified_controller"}]
                    elif case == "sibling_on": controller["channels"][1]["output_state"] = "ON"
                    _, result = self.eligibility(item,controller,at,"B12345")
                    self.assertFalse(result["eligible"],result)
                    self.assertFalse(result["command_authority"])

    def test_midnight_uses_new_local_operating_day_without_reusing_consumption(self):
        keys = []
        for at in (NOW.replace(month=1,day=8,hour=23,minute=59),
                   NOW.replace(month=1,day=9,hour=0,minute=0)):
            item, controller = self.inputs(at)
            _, result = self.eligibility(item,controller,at,"B12345")
            self.assertTrue(result["eligible"],result)
            self.assertEqual(result["operating_date"],at.date().isoformat())
            keys.append(result["consumption_key"])
        self.assertNotEqual(*keys)

    def test_legacy_owner_advice_has_no_fixed_hour_or_power_window(self):
        for hour in range(24):
            with self.subTest(hour=hour):
                at = NOW.replace(month=1,hour=hour)
                item = evidence(power={})
                item["weather"]["observed_at"] = at.isoformat()
                item["tanks"].update(observed_at=at.isoformat(),reservoir_reported_count=9)
                item["irrigation"]["owner_candidate"] = {
                    "zone_id":"B12345","operating_date":at.date().isoformat(),
                    "source":"owner_confirmed_test"}
                plan = build_water_energy_plan(item,now=at)
                rows = {row["task_id"]:row for row in plan["candidate_tasks"]}
                self.assertEqual(rows["irrigation_B12345"]["planned_start_at"],
                    "now_after_fresh_execution_revalidation")
                self.assertTrue(rows["irrigation_B12345"]["actuation_blocked"])
                self.assertIsNone(rows["irrigation_C12345"]["planned_start_at"])
                self.assertEqual(rows["irrigation_C12345"]["preferred_window"],
                    "on_material_evidence_change")


if __name__ == "__main__":
    unittest.main()

# Saved-programme regression coverage: real planner/projection, offline evidence.
def daily_program_facts(now, target=None):
    from copy import deepcopy
    from tests.test_rootline_scheduled_planner import payload
    _, advisor = payload(now)
    target = target or now.date().isoformat()
    zones = deepcopy(advisor['zones'])
    return {'power': {'observed_at': now.isoformat(), 'stale_after_minutes': 15, 'battery_soc_pct': 80,
        'solar_power_w': 0, 'load_power_w': 900, 'grid_power_w': 0},
        'weather': {'observed_at': now.isoformat(), 'stale_after_minutes': 30, 'rain_rate_mm_h': 0, 'rain_today_mm': 0},
        'forecast': {'observed_at': now.isoformat(), 'stale_after_minutes': 360, 'source': {'source_id': 'offline-nightly'},
            'days': [{'forecast_date': target, 'rain_sum_mm': 0, 'rain_probability_max_pct': 0}]},
        'irrigation': {'source': 'rootline_daily_advisor', 'advisor_generated_at': now.isoformat(),
            'advisor_operating_date': target, 'zones': zones,
            'adaptive_management': {'enabled': True, 'zones': [{'zone_id': z['zone_id']} for z in zones]}},
        'irrigation_history': {'status': 'Available', 'zones': {z['zone_id']: {
            'complete_through': now.isoformat(), 'epoch_complete_through': now.isoformat(),
            'planning_epoch_start': (now-timedelta(days=28)).isoformat(), 'events': []} for z in zones}},
        'fertilizer_executions': [], 'fertilizer_history_complete_through': now.isoformat()}


def test_saved_program_night_hold_keeps_tomorrow_objective_and_inert_authority():
    from modules.telemetry import rootline_water_energy_plan as subject
    at = datetime.fromisoformat('2026-12-31T23:30:00+02:00')
    facts = daily_program_facts(at, '2027-01-01')
    facts['weather']['rain_rate_mm_h'] = 5
    plan = subject.build_daily_program(facts, '2027-01-01', now=at)
    irrigation = [t for t in plan['candidate_tasks'] if t['task_id'].startswith('irrigation_')]
    assert len(irrigation) == 4
    assert all(t['requested_total_duration_minutes'] == 120 for t in irrigation)
    assert plan['daily_program']['forecast']['target_date'] == '2027-01-01'
    assert plan['daily_program']['start_at'] == '2027-01-01T00:00:00+02:00'
    assert plan['daily_program']['end_at'] == '2027-01-02T00:00:00+02:00'
    assert all(t['dispatchable'] is False and t['command_created'] is False for t in irrigation)
    assert plan['authority'] == subject.AUTHORITY


def test_saved_program_rejects_wrong_target_forecast_day():
    import pytest
    from modules.telemetry import rootline_water_energy_plan as subject
    facts = daily_program_facts(NOW)
    with pytest.raises(ValueError, match='dated_nightly'):
        subject.build_daily_program(facts, '2026-07-29', now=NOW)


def test_live_projection_never_calls_builder_forecast_or_forecast_reserve():
    from copy import deepcopy
    from modules.telemetry import rootline_water_energy_plan as subject
    at = datetime.fromisoformat('2026-11-20T09:00:00+02:00')
    facts = daily_program_facts(at)
    saved = subject.build_daily_program(facts, at.date().isoformat(), now=at)
    original = deepcopy(saved)
    facts.pop('forecast')
    with mock.patch.object(subject, 'build_water_energy_plan', side_effect=AssertionError('daily rebuild')), \
            mock.patch.object(subject, '_reserve', side_effect=AssertionError('forecast reserve')), \
            mock.patch('modules.telemetry.weather_service.get_weather_forecast', side_effect=AssertionError('forecast read')):
        current = subject.project_saved_program_for_execution(saved, facts, now=at)
    assert current['success'] and saved == original
    before = {t['task_id']: t for t in saved['candidate_tasks']}
    for task in current['candidate_tasks']:
        for key in ('reason', 'rank', 'planned_duration_minutes', 'requested_total_duration_minutes', 'expected_segment_count'):
            assert task.get(key) == before[task['task_id']].get(key)
    assert current['daily_program']['base_tasks'] == saved['candidate_tasks']


def test_live_weather_hold_then_release_preserves_daily_task_identity_and_allowance():
    from copy import deepcopy
    from modules.telemetry import rootline_water_energy_plan as subject
    at = datetime.fromisoformat('2026-11-20T09:00:00+02:00')
    facts = daily_program_facts(at)
    saved = subject.build_daily_program(facts, at.date().isoformat(), now=at)
    wet = deepcopy(facts); wet['weather']['rain_rate_mm_h'] = 5
    for zone in wet['irrigation']['zones']: zone['live_rain_release_proven'] = False
    # The execution authority independently blocks rain even if an advisory
    # classification remains due. The fixed objective survives either state.
    held = subject.project_saved_program_for_execution(saved, wet, now=at)
    released = subject.project_saved_program_for_execution(saved, facts, now=at)
    for plan in (held, released):
        for task in plan['candidate_tasks']:
            base = next(t for t in saved['candidate_tasks'] if t['task_id'] == task['task_id'])
            assert task.get('program_task_id') == base.get('program_task_id')
            assert task.get('requested_total_duration_minutes') == base.get('requested_total_duration_minutes')
    assert released['daily_program']['base_tasks'] == held['daily_program']['base_tasks']
    assert any(t.get('zone_decision') == 'Run now' for t in released['candidate_tasks'])
    assert not any(t.get('zone_decision') == 'Run now' for t in held['candidate_tasks'])


def test_carry_repayment_once_and_recovery_deferral_does_not_double_debt():
    from modules.telemetry import rootline_water_energy_plan as subject
    origin = {'origin_id': 'old-job', 'zone_id': 'B12345', 'operating_date': '2026-09-01',
        'original_minutes': 120, 'remaining_minutes': 120, 'repayments': []}
    task = {'task_id': 'irrigation_B12345', 'carry_allocations': [{'origin_id': 'old-job', 'minutes': 120}]}
    history = {'carry_origins': [origin], 'plans': [{'operating_date': '2026-11-19', 'tasks': [task]}]}
    facts = {'irrigation_history': {'zones': {'B12345': {'deferred_parent_jobs': [{
        'job': {'job_id': 'recovery-job', 'operating_date': '2026-11-19'}, 'remaining_seconds': 7200}],
        'events': []}}}}
    carried = subject._reconcile_carry_origins(history, facts, '2026-11-20')
    assert len(carried) == 1 and carried[0]['remaining_minutes'] == 120
    facts['irrigation_history']['zones']['B12345']['events'] = [{
        'execution_id': 'verified-repayment', 'event_at_sast': '2026-11-19T12:00:00+02:00',
        'qualifies_as_completed_watering': True, 'verified_runtime_minutes': 120}]
    repaid = subject._reconcile_carry_origins(history, facts, '2026-11-20')
    assert repaid[0]['remaining_minutes'] == 0
    history['carry_origins'] = repaid
    assert subject._reconcile_carry_origins(history, facts, '2026-11-21') == repaid


def test_next_day_recovery_stays_inside_normal_allowance():
    from modules.telemetry import rootline_water_energy_plan as subject
    at = datetime.fromisoformat('2026-11-19T23:30:00+02:00')
    facts = daily_program_facts(at, '2026-11-20')
    origins = [{'origin_id': 'older', 'zone_id': 'B12345', 'operating_date': '2026-09-01',
        'original_minutes': 240, 'remaining_minutes': 240, 'repayments': []}]
    saved = subject.build_daily_program(facts, '2026-11-20', now=at,
        history={'status': 'Available', 'unresolved_origins': origins, 'plans': []})
    task = next(t for t in saved['candidate_tasks'] if t['task_id'] == 'irrigation_B12345')
    assert task['requested_total_duration_minutes'] == 120
    assert task['carry_allocations'] == [{'origin_id': 'older', 'minutes': 120}]
    assert saved['daily_program']['carry_origins'][0]['remaining_minutes'] == 240


class MemoryProgrammeDB:
    """Transactional-shape test double; hosted PostgreSQL also covers real locks."""
    def __init__(self):
        from threading import RLock
        self.plans = {}; self.locks = {}; self.guard = RLock(); self.appends = 0
    def connect(self):
        db = self
        class Connection:
            def __init__(self): self.held=[]; self.rows=[]
            def __enter__(self): return self
            def __exit__(self,*_):
                for lock in reversed(self.held): lock.release()
            def cursor(self):
                parent=self
                class Cursor:
                    def __enter__(self): return self
                    def __exit__(self,*_): pass
                    def execute(self,sql,params=None):
                        import json
                        from copy import deepcopy
                        from threading import RLock
                        if 'pg_advisory_xact_lock' in sql:
                            with db.guard: lock=db.locks.setdefault(params[0],RLock())
                            lock.acquire(); parent.held.append(lock); parent.rows=[]
                        elif 'select exists' in sql:
                            parent.rows=[(any(p.get('daily_program') for p in db.plans.values()),)]
                        elif 'rootline_append_water_energy_plan' in sql:
                            plan=json.loads(params[7]); prior=db.plans.get(plan['operating_date'])
                            created=not prior or prior['evidence_sha256'] != plan['evidence_sha256']
                            generation=(prior.get('generation',0) if prior else 0)+(1 if created else 0)
                            if created:
                                db.appends+=1; plan['generation']=generation; db.plans[plan['operating_date']]=deepcopy(plan)
                            parent.rows=[(created,prior.get('generation') if prior else None,generation)]
                        elif 'where i.operating_date=%s' in sql:
                            plan=db.plans.get(str(params[0])); parent.rows=[] if not plan else [(
                                deepcopy(plan),plan['generation'],plan['evidence_sha256'],
                                datetime.fromisoformat(plan['evidence_observed_at']),plan['replacement_reason'])]
                        elif 'order by i.operating_date' in sql:
                            parent.rows=[(deepcopy(p),p['generation']) for d,p in sorted(db.plans.items()) if d<str(params[0])]
                        else: raise AssertionError(sql)
                    def fetchone(self): return parent.rows[0] if parent.rows else None
                    def fetchall(self): return parent.rows
                return Cursor()
        return Connection()


def test_one_initial_program_under_competing_evidence_and_restart_readback():
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from modules.telemetry import rootline_water_energy_plan as subject
    db=MemoryProgrammeDB(); barrier=Barrier(2); calls=[]
    at=datetime.fromisoformat('2026-11-19T23:30:00+02:00')
    def worker(number):
        barrier.wait(timeout=5)
        facts=daily_program_facts(at,'2026-11-20');facts['power']['battery_soc_pct']+=number
        def load(**_): calls.append(number);return facts,'2026-11-20',at
        with db.connect() as connection:
            return subject.ensure_saved_daily_program('2026-11-20',now=at,connection=connection,
                evidence_loader=load,forecast_reader=lambda **_:({'success':True},200))
    with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(worker,[0,1]))
    assert db.appends==1 and len(calls)==1
    assert results[0][0]['evidence_sha256']==results[1][0]['evidence_sha256']
    with db.connect() as connection:
        reread,_=subject.ensure_saved_daily_program('2026-11-20',now=at,connection=connection,
            evidence_loader=lambda **_:(_ for _ in ()).throw(AssertionError('rebuild')),
            forecast_reader=lambda **_:(_ for _ in ()).throw(AssertionError('forecast')))
    assert reread['generation']==1 and db.appends==1


def test_current_day_adoption_exact_once_without_forecast_or_builder():
    from copy import deepcopy
    from modules.telemetry import rootline_water_energy_plan as subject
    at=datetime.fromisoformat('2026-11-20T12:00:00+02:00');db=MemoryProgrammeDB()
    legacy=subject.build_water_energy_plan(daily_program_facts(at),'2026-11-20',now=at)
    legacy.update(generation=208,status='needs_data');db.plans['2026-11-20']=deepcopy(legacy)
    forbidden=lambda **_:(_ for _ in ()).throw(AssertionError('no planning or forecast during adoption'))
    with mock.patch.object(subject,'build_water_energy_plan',side_effect=AssertionError('rebuild')):
        with db.connect() as connection:
            adopted,code=subject.ensure_saved_daily_program('2026-11-20',now=at,connection=connection,
                evidence_loader=forbidden,forecast_reader=forbidden)
    assert code==201 and adopted['candidate_tasks']==legacy['candidate_tasks']
    assert adopted['irrigation_auxiliary_tasks']==legacy['irrigation_auxiliary_tasks']
    assert adopted['daily_program']['legacy_plan']['generation']==208
    assert adopted['daily_program']['provenance']=='legacy_current_day_adoption'
    assert adopted['daily_program']['forecast']['nightly_cycle'] is None
    tomorrow=at+timedelta(days=1)
    other=deepcopy(legacy);other.update(operating_date='2026-11-21',plan_id='ROOTLINE-WEP-20261121')
    db.plans['2026-11-21']=other
    with db.connect() as connection:
        held,_=subject.ensure_saved_daily_program('2026-11-21',now=tomorrow,connection=connection,
            forecast_reader=lambda **_:({'success':False},200))
    assert held['status']=='nightly_forecast_missing_new_starts_held' and db.appends==1


def test_adoption_never_creates_a_missing_current_plan_or_adopts_a_future_one():
    from copy import deepcopy
    from modules.telemetry import rootline_water_energy_plan as subject
    at=datetime.fromisoformat('2026-11-20T12:00:00+02:00');db=MemoryProgrammeDB()
    for selected in ('2026-11-20','2026-11-21'):
        if selected.endswith('21'):
            future=subject.build_water_energy_plan(daily_program_facts(at,selected),selected,now=at)
            future['generation']=1;db.plans[selected]=future
        with db.connect() as connection:
            held,_=subject.ensure_saved_daily_program(selected,now=at,connection=connection,
                forecast_reader=lambda **_:({'success':False},200))
        assert held['status']=='nightly_forecast_missing_new_starts_held'
    assert db.appends==0

def test_hourly_forecast_opportunities_create_serial_slots_and_runtime_honors_due_time():
    from modules.telemetry import rootline_water_energy_plan as subject
    at=datetime.fromisoformat('2026-11-19T23:30:00+02:00')
    facts=daily_program_facts(at,'2026-11-20')
    facts['forecast']['days'][0]['planning_hours']=[{
        'start_at':f'2026-11-20T{h:02d}:00:00+02:00','rain_sum_mm':0 if 8<=h<16 else 2,
        'rain_probability_pct':0 if 8<=h<16 else 80,'source':'fcst','local_observation_credit':False} for h in range(24)]
    saved=subject.build_daily_program(facts,'2026-11-20',now=at)
    tasks=sorted((t for t in saved['candidate_tasks'] if t.get('scheduled_order')),key=lambda t:t['scheduled_order'])
    assert [datetime.fromisoformat(t['planned_start_at']).hour for t in tasks]==[8,10,12,14]
    before=datetime.fromisoformat('2026-11-20T07:00:00+02:00')
    live=daily_program_facts(before)
    with mock.patch.object(subject,'build_water_energy_plan',side_effect=AssertionError('rebuild')):
        held=subject.project_saved_program_for_execution(saved,live,now=before)
    assert not any(t.get('zone_decision')=='Run now' for t in held['candidate_tasks'])
    due=before+timedelta(hours=1);live=daily_program_facts(due)
    current=subject.project_saved_program_for_execution(saved,live,now=due)
    assert sum(t.get('zone_decision')=='Run now' for t in current['candidate_tasks'])==1
    delayed=due+timedelta(hours=2,minutes=15)
    moved=subject.project_saved_program_for_execution(saved,daily_program_facts(delayed),now=delayed)
    first=next(t for t in moved['candidate_tasks'] if t.get('scheduled_order')==1)
    assert first['planned_start_at']==delayed.isoformat()
    assert first['requested_total_duration_minutes']==120
    assert moved['daily_program']['base_tasks']==saved['daily_program']['base_tasks']


def test_unstarted_saved_work_is_carried_once_and_old_origin_survives_context_window():
    from modules.telemetry import rootline_water_energy_plan as subject
    task={'task_id':'irrigation_B12345','program_task_id':'PROGRAM-OLD:B',
        'requested_total_duration_minutes':120,'zone_decision':'Hold',
        'slot_status':'carry_next_operating_date',
        'weekly_obligation':{'status':'available','delivery_debt_days':1},'carry_allocations':[]}
    history={'plans':[{'plan_id':'PROGRAM-OLD','operating_date':'2026-09-01','tasks':[task]}]}
    facts={'irrigation_history':{'zones':{'B12345':{'events':[]}}}}
    first=subject._reconcile_carry_origins(history,facts,'2026-11-20')
    assert first[0]['origin_id']=='PROGRAM-OLD:B' and first[0]['remaining_minutes']==120
    history['carry_origins']=first
    assert subject._reconcile_carry_origins(history,facts,'2026-11-21')==first


def test_midnight_crossing_completion_pays_original_operating_date_once():
    from modules.telemetry import rootline_water_energy_plan as subject
    origin={'origin_id':'debt','zone_id':'B12345','operating_date':'2026-11-01',
        'original_minutes':120,'remaining_minutes':120,'repayments':[]}
    history={'carry_origins':[origin],'plans':[{'operating_date':'2026-11-19','tasks':[{
        'task_id':'irrigation_B12345','carry_allocations':[{'origin_id':'debt','minutes':120}]}]}]}
    facts={'irrigation_history':{'zones':{'B12345':{'events':[{'execution_id':'overnight',
        'operating_date':'2026-11-19','event_at_sast':'2026-11-20T00:20:00+02:00',
        'qualifies_as_completed_watering':True,'verified_runtime_minutes':120}]}}}}
    repaid=subject._reconcile_carry_origins(history,facts,'2026-11-20')
    assert repaid[0]['remaining_minutes']==0 and len(repaid[0]['repayments'])==1
    history['carry_origins']=repaid
    assert subject._reconcile_carry_origins(history,facts,'2026-11-21')==repaid


def test_revision_cas_reloads_newer_generation_and_preserves_base():
    from modules.telemetry import rootline_water_energy_plan as subject
    from copy import deepcopy
    at=datetime.fromisoformat('2026-11-20T09:00:00+02:00')
    saved=subject.build_daily_program(daily_program_facts(at),'2026-11-20',now=at)
    saved['generation']=1;db=MemoryProgrammeDB();db.plans['2026-11-20']=deepcopy(saved)
    with db.connect() as connection:
        revised,status=subject.revise_program_remainder(saved,daily_program_facts(at),now=at,connection=connection)
    assert status==201 and revised['generation']==2
    assert revised['daily_program']['base_tasks']==saved['daily_program']['base_tasks']
    with db.connect() as connection:
        raced,status=subject.revise_program_remainder(saved,daily_program_facts(at+timedelta(minutes=1)),
            now=at+timedelta(minutes=1),connection=connection)
    assert raced['generation']==2 and db.appends==1


def test_adoption_bootstraps_old_canonical_deferred_origin_without_rolling_expiry():
    from modules.telemetry import rootline_water_energy_plan as subject
    at=datetime.fromisoformat('2026-11-20T12:00:00+02:00')
    legacy=subject.build_water_energy_plan(daily_program_facts(at),'2026-11-20',now=at)
    legacy['recent_irrigation_history']['zones']['B12345']['deferred_parent_jobs']=[{
        'job':{'job_id':'old-unresolved','operating_date':'2026-08-01'},'remaining_seconds':7200}]
    adopted=subject._adopt_current_day_program(legacy,at)
    assert adopted['daily_program']['carry_origins'][0]['origin_id']=='old-unresolved'
    assert adopted['daily_program']['carry_origins'][0]['remaining_minutes']==120


def test_program_history_bounds_context_but_keeps_old_carry_and_allocation_identity():
    from modules.telemetry import rootline_water_energy_plan as subject
    from copy import deepcopy
    db = MemoryProgrammeDB()
    old_origin = {"origin_id": "old-unfinished", "zone_id": "B12345",
        "operating_date": "2026-08-01", "original_minutes": 60,
        "remaining_minutes": 30, "repayments": [{"execution_id": "already", "minutes": 30}]}
    resolved = {"origin_id": "resolved", "zone_id": "B12345",
        "operating_date": "2026-07-01", "remaining_minutes": 0,
        "repayments": [{"execution_id": "resolved-once", "minutes": 40}]}
    for day in ("2026-08-10", "2026-09-01", "2026-11-19"):
        db.plans[day] = {"plan_id": "plan-"+day, "generation": 1,
            "operating_date": day, "daily_program": {"version": subject.DAILY_PROGRAM_VERSION,
            "carry_origins": [deepcopy(old_origin), deepcopy(resolved)],
            "base_tasks": [{"task_id": "irrigation_B12345", "large_context": "old-full-context",
                "carry_allocations": ([{"origin_id": "old-unfinished", "minutes": 30}]
                    if day == "2026-08-10" else [])}]}}
    with db.connect() as connection:
        result = subject.read_program_history("2026-11-20", connection=connection)
    assert [p["operating_date"] for p in result["plans"]] == ["2026-11-19"]
    assert [p["operating_date"] for p in result["allocation_plans"]] == ["2026-08-10"]
    assert result["allocation_plans"][0]["tasks"] == [{"task_id": "irrigation_B12345",
        "carry_allocations": [{"origin_id": "old-unfinished", "minutes": 30}]}]
    assert result["carry_origins"] == [old_origin, resolved]
    assert result["unresolved_origins"] == [old_origin]
    facts = {"irrigation_history": {"zones": {"B12345": {"events": [{
        "execution_id": "late-confirmed", "operating_date": "2026-08-10",
        "qualifies_as_completed_watering": True, "verified_runtime_minutes": 30}]}}}}
    repaid = subject._reconcile_carry_origins(result, facts, "2026-11-20", include_unstarted=False)
    assert repaid[0]["remaining_minutes"] == 0
    result["carry_origins"] = repaid
    assert subject._reconcile_carry_origins(result, facts, "2026-11-21", include_unstarted=False) == repaid


def test_new_program_binding_holds_if_canonical_carry_history_unavailable(monkeypatch):
    from modules.telemetry import rootline_water_energy_plan as subject
    db=MemoryProgrammeDB()
    at=datetime.fromisoformat('2026-11-19T23:30:00+02:00')
    monkeypatch.setattr(subject,'read_program_history',lambda *a,**kw:{
        'status':subject.UNAVAILABLE,'plans':[],'unresolved_origins':[],'error_type':'TimeoutError'})
    monkeypatch.setattr(subject,'build_daily_program',lambda *a,**kw:(_ for _ in ()).throw(
        AssertionError('must not overwrite canonical carry with empty history')))
    with db.connect() as connection:
        result,status=subject.ensure_saved_daily_program('2026-11-20',now=at,connection=connection,
            evidence_loader=lambda **_: (daily_program_facts(at,'2026-11-20'),'2026-11-20',at),
            forecast_reader=lambda **_: ({'success':True},200))
    assert status==503 and db.appends==0
    assert result['status']=='canonical_program_history_unavailable_new_starts_held'


def test_late_origin_completion_settles_canonical_operating_day_once_without_double_recovery():
    from modules.telemetry import rootline_water_energy_plan as subject
    from copy import deepcopy
    original={'origin_id':'plan20261120:B','zone_id':'B12345','operating_date':'2026-11-20',
        'original_minutes':120,'remaining_minutes':120,'repayments':[],
        'basis':'saved_supported_unfulfilled_objective'}
    history={'carry_origins':[original],'plans':[{'operating_date':'2026-11-21','tasks':[{
        'task_id':'irrigation_B12345','carry_allocations':[{'origin_id':original['origin_id'],'minutes':120}]}]}]}
    facts={'irrigation_history':{'zones':{'B12345':{'events':[{
        'execution_id':'original-late','operating_date':'2026-11-20',
        'event_at_sast':'2026-11-21T00:00:02+02:00',
        'qualifies_as_completed_watering':True,'verified_runtime_minutes':120}]}}}}
    resolved=subject._reconcile_carry_origins(history,facts,'2026-11-22',include_unstarted=False)
    assert resolved[0]['remaining_minutes']==0
    assert resolved[0]['fulfillments']==[{'execution_id':'original-late','minutes':120}]
    history['carry_origins']=resolved
    facts['irrigation_history']['zones']['B12345']['events'].append({
        'execution_id':'next-day-recovery','operating_date':'2026-11-21',
        'qualifies_as_completed_watering':True,'verified_runtime_minutes':120})
    assert subject._reconcile_carry_origins(history,facts,'2026-11-23',include_unstarted=False)==resolved
    unproven=deepcopy(facts)
    for event in unproven['irrigation_history']['zones']['B12345']['events']:
        event['qualifies_as_completed_watering']=False
    history['carry_origins']=[original]
    assert subject._reconcile_carry_origins(history,unproven,'2026-11-23',include_unstarted=False)[0]['remaining_minutes']==120


def test_late_deferred_parent_binds_existing_saved_task_obligation_without_duplication():
    from modules.telemetry import rootline_water_energy_plan as subject
    original={'origin_id':'saved:B','zone_id':'B12345','operating_date':'2026-11-20',
        'original_minutes':120,'remaining_minutes':120,'repayments':[],
        'basis':'saved_supported_unfulfilled_objective'}
    history={'carry_origins':[original],'plans':[]}
    facts={'irrigation_history':{'zones':{'B12345':{'deferred_parent_jobs':[{
        'job':{'job_id':'canonical-job','operating_date':'2026-11-20'},'remaining_seconds':7200}],
        'events':[]}}}}
    result=subject._reconcile_carry_origins(history,facts,'2026-11-21',include_unstarted=False)
    assert len(result)==1 and result[0]['remaining_minutes']==120
    assert result[0]['canonical_job_ids']==['canonical-job']
    history['carry_origins']=result
    assert subject._reconcile_carry_origins(history,facts,'2026-11-22',include_unstarted=False)==result
    facts['irrigation_history']['zones']['B12345']['deferred_parent_jobs'][0]['remaining_seconds']=3600
    reduced=subject._reconcile_carry_origins(history,facts,'2026-11-22',include_unstarted=False)
    assert len(reduced)==1 and reduced[0]['remaining_minutes']==60


def test_unscheduled_nightly_irrigation_cannot_become_executable_from_live_readiness():
    from modules.telemetry import rootline_water_energy_plan as subject
    at=datetime.fromisoformat('2026-11-20T08:00:00+02:00')
    for reason in ('allowed_operating_window_unavailable','normal_objectives_do_not_fit_operating_date'):
        task={'task_id':'irrigation_B12345','zone_decision':'Run now','recommendation':'Recommend',
            'slot_status':reason,'planned_duration_minutes':120}
        plan={'daily_program':{'end_at':'2026-11-21T00:00:00+02:00'},'candidate_tasks':[task]}
        subject._adjust_live_slots(plan,{},at)
        assert task['zone_decision']=='Hold' and task['recommendation']=='Hold'
        assert task['live_adjustment_reason']=='saved_permitted_operating_slot_unavailable'
    task={'task_id':'irrigation_B12345','zone_decision':'Run now','recommendation':'Recommend'}
    plan={'daily_program':{'provenance':'legacy_current_day_adoption'},'candidate_tasks':[task]}
    subject._adjust_live_slots(plan,{},at)
    assert task['zone_decision']=='Run now'


def test_legacy_incomplete_parent_uses_verified_remaining_not_full_unstarted_objective():
    from modules.telemetry import rootline_water_energy_plan as subject
    task={'task_id':'irrigation_B12345','program_task_id':'saved:B',
        'requested_total_duration_minutes':120,'weekly_obligation':{'status':'available','delivery_debt_days':1}}
    history={'plans':[{'plan_id':'saved','operating_date':'2026-11-20','tasks':[task]}]}
    facts={'irrigation_history':{'zones':{'B12345':{
        'incomplete_parent_job':{'job':{'job_id':'legacy-parent','operating_date':'2026-11-20'},
            'remaining_seconds':3600,'completed_segment_count':1},'events':[]}}}}
    result=subject._reconcile_carry_origins(history,facts,'2026-11-21')
    assert len(result)==1 and result[0]['remaining_minutes']==60
    assert result[0]['origin_id']=='legacy-parent'
    history['carry_origins']=result
    facts['irrigation_history']['zones']['B12345'].pop('incomplete_parent_job')
    facts['irrigation_history']['zones']['B12345']['events']=[{
        'execution_id':'legacy-final-segment','operating_date':'2026-11-20',
        'event_at_sast':'2026-11-21T00:00:02+02:00',
        'qualifies_as_completed_watering':True,'verified_runtime_minutes':60}]
    resolved=subject._reconcile_carry_origins(history,facts,'2026-11-22')
    assert len(resolved)==1 and resolved[0]['remaining_minutes']==0


def test_failed_history_read_recovers_next_night_without_losing_prior_debt(monkeypatch):
    from modules.telemetry import rootline_water_energy_plan as subject
    db=MemoryProgrammeDB()
    origin={'origin_id':'old','zone_id':'B12345','operating_date':'2026-09-01',
        'remaining_minutes':30,'repayments':[{'execution_id':'paid','minutes':10}]}
    db.plans['2026-11-19']={'plan_id':'prior','generation':1,'operating_date':'2026-11-19',
        'daily_program':{'version':subject.DAILY_PROGRAM_VERSION,'carry_origins':[origin],'base_tasks':[]}}
    at=datetime.fromisoformat('2026-11-19T23:30:00+02:00')
    def ensure():
        with db.connect() as connection:
            return subject.ensure_saved_daily_program('2026-11-20',now=at,connection=connection,
                evidence_loader=lambda **_: (daily_program_facts(at,'2026-11-20'),'2026-11-20',at),
                forecast_reader=lambda **_: ({'success':True},200))
    with monkeypatch.context() as scoped:
        scoped.setattr(subject,'read_program_history',lambda *a,**k:{'status':subject.UNAVAILABLE})
        assert ensure()[1]==503 and db.appends==0
    recovered,status=ensure()
    assert status<400 and db.appends==1
    assert recovered['daily_program']['carry_origins']==[origin]


def test_extended_outage_keeps_last_unmaterialized_supported_origin_without_full_old_context():
    from modules.telemetry import rootline_water_energy_plan as subject
    db=MemoryProgrammeDB()
    db.plans['2026-09-01']={'plan_id':'old-program','generation':1,'operating_date':'2026-09-01',
        'daily_program':{'version':subject.DAILY_PROGRAM_VERSION,'carry_origins':[],
            'base_tasks':[{'task_id':'irrigation_B12345','program_task_id':'old-program:B',
                'zone_decision':'Hold','weekly_obligation':{'status':'available','delivery_debt_days':1},
                'requested_total_duration_minutes':120,'irrelevant_full_context':'must not propagate'}]}}
    with db.connect() as connection:
        history=subject.read_program_history('2026-11-20',connection=connection)
    assert history['plans']==[] and history['allocation_plans']==[]
    candidate=history['origin_candidate_plans'][0]['tasks'][0]
    assert 'irrelevant_full_context' not in candidate
    facts={'irrigation_history':{'zones':{'B12345':{'events':[]}}}}
    carried=subject._reconcile_carry_origins(history,facts,'2026-11-20')
    assert len(carried)==1 and carried[0]['origin_id']=='old-program:B'
    assert carried[0]['remaining_minutes']==120
    history['carry_origins']=carried
    assert subject._reconcile_carry_origins(history,facts,'2026-11-21')==carried


def test_same_operating_day_late_epoch_counts_day_without_changing_freshness_or_epoch_filter():
    from modules.telemetry.rootline_adaptive_irrigation import project_weekly_delivery_obligation
    at=datetime.fromisoformat('2026-11-20T23:30:00+02:00')
    epoch=at.replace(hour=22,minute=0)
    zone={'planning_epoch_start':epoch.isoformat(),
        'completion_ledger_complete_through':at.isoformat(),'completion_events':[]}
    explicit=project_weekly_delivery_obligation(zone,now=at,operating_date='2026-11-20')
    current=project_weekly_delivery_obligation(zone,now=at)
    assert explicit==current
    assert explicit['status']=='available' and explicit['expected_days_by_now']==1
    assert explicit['delivery_debt_days']==1
    assert explicit['remaining_weekly_obligation_days']==2
    future=project_weekly_delivery_obligation(zone,now=at,operating_date='2026-11-21')
    assert future['status']=='available' and future['expected_days_by_now']==2
    stale=project_weekly_delivery_obligation({**zone,
        'completion_ledger_complete_through':(at-timedelta(minutes=16)).isoformat()},
        now=at,operating_date='2026-11-21')
    assert stale['status']=='Unavailable' and stale['delivery_debt_days'] is None
    before=project_weekly_delivery_obligation(zone,now=at,operating_date='2026-11-19')
    assert before['expected_days_by_now']==0
    event={'outcome_id':'before-epoch','completed_at':(epoch-timedelta(minutes=1)).isoformat(),
        'operating_date':'2026-11-20','verified_runtime_minutes':120,
        'state':'Completed','shutdown_verified':True,'source':'canonical',
        'objective_satisfied':True}
    filtered=project_weekly_delivery_obligation({**zone,'completion_events':[event]},
        now=at,operating_date='2026-11-20')
    assert filtered['completed_days']==0 and filtered['verified_runtime_minutes']==0
