import unittest
import threading
from pathlib import Path
from unittest.mock import patch

from app import app
from modules.telemetry.rootline_daily_brief import build_rootline_daily_brief,get_rootline_daily_brief


def evidence(**overrides):
    base = {
        "weather_current": {"success": True, "source": {"is_stale": False, "data_age_minutes": 4}, "current": {"temperature_c": 24, "humidity_pct": 55, "rain_rate_mm_h": 0, "rain_today_mm": 0, "wind_speed_kmh": 8, "wind_gust_kmh": 12, "pressure_hpa": 1014}},
        "weather_today": {"success": True, "window": {"coverage_pct": 98}, "rain": {"total_mm": 0}, "wind": {"max_speed_kmh": 12}, "flags": {"irrigation_caution": False}},
        "forecast": {"success": True, "source": {"is_stale": False}, "window": {"returned_days": 3}, "days": [{"forecast_date": "2026-07-25", "rain_sum_mm": 0, "wind_max_kmh": 12}]},
        "power": {"success": True, "source": {"is_stale": False}, "flags": {}, "summary": {"status": "ok"}},
        "irrigation": {"success": True, "current": {"status": "IDLE"}, "today": {"total_plan_rows": 2, "done_count": 1, "skipped_count": 0, "paused_count": 0, "total_planned_minutes": 60, "completed_minutes": 30, "next_zone_mismatch": False, "plan": [{"zone_id": "DRIP", "zone_name": "North Drip", "status": "DONE", "planned_minutes": 30, "water_score": 2}, {"zone_id": "SPR", "zone_name": "South Sprinkler", "status": "PLANNED", "planned_minutes": 30, "water_score": 5}]}},
        "rollups": {"success": True, "comparison": {"weather": {"sample_count_match": True}}},
        "tank": {"success": True, "status": "ready"},
        "pump": {"success": True, "status": "ready"},
        "borehole": {"success": True, "status": "ready"},
    }
    base.update(overrides)
    return base


class RootlineDailyBriefTests(unittest.TestCase):
    def test_independent_readers_start_concurrently(self):
        barrier=threading.Barrier(4);threads=set();guard=threading.Lock()
        def reader():
            with guard: threads.add(threading.get_ident())
            barrier.wait(timeout=1)
            return {"success":False}
        packet,status=get_rootline_daily_brief("2026-08-15",readers={
            name:reader for name in ("weather_current","weather_today","forecast",
                "power","irrigation","rollups")})
        self.assertEqual(status,200)
        self.assertEqual(len(threads),4)
        self.assertTrue(packet["authority"]["hardware_control_performed"] is False)

    def build(self, **overrides):
        return build_rootline_daily_brief(evidence(**overrides), "2026-07-25")

    def test_fresh_complete_evidence_is_natural_and_read_only(self):
        result = self.build()
        self.assertIn("2 planned zone(s)", result["executive_summary"])
        self.assertEqual(result["irrigation"]["zones"][1]["recommendation"], "proceed")
        self.assertEqual(result["next_safe_window"]["date"], "2026-07-25")
        self.assertFalse(result["authority"]["writes_performed"])
        self.assertFalse(result["authority"]["hardware_control_performed"])

    def test_stale_weather_fails_closed(self):
        current = evidence()["weather_current"]
        current["source"]["is_stale"] = True
        result = self.build(weather_current=current)
        self.assertEqual(result["current_conditions"]["freshness"], "stale")
        self.assertEqual(result["irrigation"]["zones"][1]["recommendation"], "review")

    def test_missing_forecast_stays_unavailable(self):
        result = self.build(forecast=None)
        self.assertEqual(result["forecast"]["availability"], "Unavailable")
        self.assertEqual(result["next_safe_window"]["status"], "Unavailable")

    def test_rain_caution_holds_planned_zone(self):
        today = evidence()["weather_today"]
        today["rain"]["total_mm"] = 2
        today["flags"]["irrigation_caution"] = True
        result = self.build(weather_today=today)
        self.assertTrue(result["holds"]["rain_caution"])
        self.assertEqual(result["irrigation"]["zones"][1]["recommendation"], "hold")

    def test_high_wind_only_holds_sprinkler(self):
        today = evidence()["weather_today"]
        today["wind"]["max_speed_kmh"] = 40
        result = self.build(weather_today=today)
        self.assertTrue(result["holds"]["wind_sprinkler_caution"])
        self.assertEqual(result["irrigation"]["zones"][1]["recommendation"], "hold")

    def test_power_hold(self):
        power = evidence()["power"]
        power["flags"]["grid_down"] = True
        result = self.build(power=power)
        self.assertTrue(result["holds"]["power_hold"])
        self.assertEqual(result["irrigation"]["zones"][1]["recommendation"], "hold")

    def test_tank_and_pump_are_never_invented(self):
        result = self.build(tank=None, pump=None, borehole=None)
        self.assertEqual(result["holds"]["tank"], "Unavailable")
        self.assertEqual(result["holds"]["pump"], "Unavailable")
        self.assertEqual(result["irrigation"]["zones"][1]["recommendation"], "review")

    def test_all_zero_power_is_suspicious_not_physical_truth(self):
        power = evidence()["power"]
        power["summary"] = {"status": "warning", "headline": "Battery is low."}
        power["current"] = {
            "battery_soc_pct": 0, "solar_power_w": 0, "load_power_w": 0,
            "grid_power_w": 0, "generator_power_w": 0,
        }
        result = self.build(power=power)
        self.assertTrue(result["holds"]["power_hold"])
        self.assertIn("Suspicious/unverified", result["power"]["interpretation"])
        self.assertTrue(any("not proof" in item for item in result["unresolved_evidence"]))

    def test_missed_zone_reprioritization_uses_water_score(self):
        irrigation = evidence()["irrigation"]
        irrigation["today"]["plan"] = [
            {"zone_id": "A", "status": "MISSED", "water_score": 1},
            {"zone_id": "B", "status": "SKIPPED", "water_score": 9},
        ]
        result = self.build(irrigation=irrigation)
        self.assertEqual(result["irrigation"]["missed_reprioritization"][0]["zone_id"], "B")

    def test_conflicting_evidence_requires_review(self):
        irrigation = evidence()["irrigation"]
        irrigation["today"]["next_zone_mismatch"] = True
        result = self.build(irrigation=irrigation)
        self.assertEqual(result["irrigation"]["zones"][1]["recommendation"], "review")
        self.assertTrue(any("authoritative" in item for item in result["owner_decisions_needed"]))

    def test_no_data_fails_closed_without_writes(self):
        result = build_rootline_daily_brief({}, "2026-07-25")
        self.assertEqual(result["current_conditions"]["availability"], "Unavailable")
        self.assertEqual(result["irrigation"]["availability"], "Unavailable")
        self.assertFalse(result["authority"]["writes_performed"])
        self.assertFalse(result["authority"]["alert_send_performed"])

    def test_owner_only_route_and_no_duplicate_route(self):
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        self.assertEqual(routes.count("/api/telemetry/rootline/daily-brief"), 1)
        owner_env = {
            "OWNER_ACCESS_ENABLED": "1",
            "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
            "OWNER_READ_TOKEN": "read-owner-token-1234567890abcdef",
            "OWNER_ADMIN_TOKEN": "admin-owner-token-1234567890abcdef",
            "OWNER_SESSION_SECRET": "owner-session-secret-1234567890abcdef",
        }
        with app.test_client() as client, patch.dict("os.environ", owner_env, clear=False):
            response = client.get(
                "/api/telemetry/rootline/daily-brief",
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
        self.assertEqual(response.status_code, 403)

    def test_no_duplicate_alert_or_dashboard_contract(self):
        result = self.build()
        self.assertFalse(result["authority"]["alert_send_performed"])
        self.assertTrue(result["source"]["composed_from_existing_readers"])
        template = Path("templates/dashboard.html").read_text(encoding="utf-8")
        self.assertEqual(template.count('id="rootline_panel"'), 1)
        self.assertNotIn(result["executive_summary"], template)


if __name__ == "__main__":
    unittest.main()
