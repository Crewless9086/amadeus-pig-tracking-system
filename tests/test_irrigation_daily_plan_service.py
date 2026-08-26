import os
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from app import app
from modules.telemetry.irrigation_daily_plan_service import (
    InMemoryDailyPlanLedger,
    canonical_plan_identity,
    project_rootline_specialist_daily_plan,
    generate_or_reuse_daily_plan,
    get_current_daily_plan,
    operating_date,
    prepare_daily_plan,
)


def test_specialist_projection_creates_and_reuses_date_stable_plan_without_authority():
    ledger = InMemoryDailyPlanLedger()
    result = {"success": True, "operating_date": "2026-08-26",
        "result_id": "ROOTLINE-RESULT-1", "generation": "GEN-1",
        "evidence_cutoff": "2026-08-26T05:12:00+00:00", "overall_status": "Run",
        "recommendations": [
            {"subject": "B12345", "status": "Recommend", "reason": "Water deficit.",
             "planned_duration_minutes": 45, "preferred_window": "08:00-09:00"},
            {"subject": "C12345", "status": "Do Not Run", "reason": "Not due."},
        ]}
    first = project_rootline_specialist_daily_plan(result, ledger=ledger)
    replay = project_rootline_specialist_daily_plan(result, ledger=ledger)
    assert first["created"] is True and replay["created"] is False
    assert first["daily_plan"]["daily_plan_id"] == "ROOTLINE-DAILY-PLAN-20260826"
    assert first["daily_plan"]["status"] == "planned"
    assert first["daily_plan"]["zones"][0]["subject"] == "B12345"
    assert first["status"] == "daily_plan_created" and first["readback_bound"] is True
    assert replay["status"] == "daily_plan_reused" and replay["readback_bound"] is True


def test_specialist_projection_rejects_readback_not_bound_to_write_receipt():
    class MismatchLedger(InMemoryDailyPlanLedger):
        def get_current(self, day):
            value = super().get_current(day)
            return {**value, "evidence_sha256": "0" * 64}
    result = {"success": True, "operating_date": "2026-08-26",
        "result_id": "R", "generation": "G",
        "evidence_cutoff": "2026-08-26T05:12:00+00:00",
        "recommendations": []}
    with __import__("pytest").raises(Exception, match="daily_plan_readback_binding_unproven"):
        project_rootline_specialist_daily_plan(result, ledger=MismatchLedger())


def packet(**overrides):
    value = {
        "operating_date": "2026-07-26",
        "status": "planned",
        "evidence_observed_at": "2026-07-26T05:00:00+02:00",
        "replacement_reason": "initial evidence",
        "evidence": {"weather": {"freshness": "fresh"}},
        "zones": [{"zone_id": "B12345", "recommendation": "hold"}],
    }
    value.update(overrides)
    return value


class DailyPlanContractTests(unittest.TestCase):
    def test_stable_identity_and_johannesburg_operating_date(self):
        instant = datetime(2026, 7, 25, 22, 30, tzinfo=timezone.utc)
        self.assertEqual(operating_date(instant).isoformat(), "2026-07-26")
        self.assertEqual(
            canonical_plan_identity(instant), "ROOTLINE-DAILY-PLAN-20260726"
        )
        self.assertEqual(prepare_daily_plan(packet())["operating_timezone"], "Africa/Johannesburg")

    def test_unchanged_evidence_returns_same_generation_without_write(self):
        ledger = InMemoryDailyPlanLedger()
        first = generate_or_reuse_daily_plan(packet(), ledger=ledger)
        replay = generate_or_reuse_daily_plan(
            packet(replacement_reason="rerun with unchanged evidence"), ledger=ledger
        )
        self.assertTrue(first["created"])
        self.assertFalse(replay["created"])
        self.assertEqual(replay["daily_plan"]["generation"], 1)
        self.assertEqual(len(ledger.generations), 1)

    def test_material_evidence_appends_and_supersedes(self):
        ledger = InMemoryDailyPlanLedger()
        generate_or_reuse_daily_plan(packet(), ledger=ledger)
        changed = generate_or_reuse_daily_plan(
            packet(
                replacement_reason="rain evidence changed",
                evidence={"weather": {"freshness": "fresh", "rain_mm": 5}},
            ),
            ledger=ledger,
        )
        self.assertEqual(changed["superseded_generation"], 1)
        self.assertEqual(changed["daily_plan"]["generation"], 2)
        self.assertEqual(len(ledger.generations), 2)
        current, status = get_current_daily_plan("2026-07-26", ledger=ledger)
        self.assertEqual(status, 200)
        self.assertEqual(current["daily_plan"]["generation"], 2)
        self.assertEqual(len(current["superseded_history"]), 1)
        self.assertEqual(current["superseded_history"][0]["history_status"], "superseded")

    def test_explicit_non_schedule_states_are_supported(self):
        for state in ("missed", "stale", "unavailable", "no_irrigation_required"):
            with self.subTest(state=state):
                self.assertEqual(prepare_daily_plan(packet(status=state))["status"], state)

    def test_no_data_is_understandable_and_fail_closed(self):
        body, status = get_current_daily_plan(
            "2026-07-26", ledger=InMemoryDailyPlanLedger()
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["status"], "unavailable")
        self.assertIn("No canonical", body["owner_message"])
        self.assertFalse(body["schedule_enabled"])
        self.assertFalse(body["controls_hardware"])
        self.assertFalse(body["writes_performed"])

    def test_one_dashboard_projection_and_no_generation_list(self):
        template = Path("templates/dashboard.html").read_text(encoding="utf-8")
        javascript = Path("static/js/dashboard.js").read_text(encoding="utf-8")
        self.assertEqual(template.count('id="irrigation_panel"'), 1)
        self.assertEqual(template.count('id="irrigation_b_status"'), 1)
        self.assertEqual(template.count('id="irrigation_c_status"'), 1)
        self.assertEqual(
            javascript.count("/api/telemetry/irrigation/status?date="), 1
        )
        self.assertNotIn("daily_plan_generations", javascript)


class DailyPlanRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.env = mock.patch.dict(
            os.environ,
            {
                "OWNER_ACCESS_ENABLED": "1",
                "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
                "OWNER_SESSION_SECRET": "s" * 40,
                "OWNER_READ_TOKEN": "r" * 40,
                "OWNER_ADMIN_TOKEN": "a" * 40,
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_anonymous_get_is_structured_403_and_route_is_unique(self):
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        path = "/api/telemetry/rootline/daily-irrigation-plan"
        self.assertEqual(routes.count(path), 1)
        response = self.client.get(path, environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "owner_read_access_denied")

    @mock.patch("modules.telemetry.telemetry_routes.get_current_daily_plan")
    def test_owner_read_get_has_no_write_or_hardware_authority(self, get_plan):
        get_plan.return_value = ({
            "success": True, "status": "planned", "daily_plan": {"generation": 1},
            "writes_performed": False, "hardware_control_performed": False,
        }, 200)
        login = self.client.post(
            "/owner/login", data={"owner_token": "r" * 40, "next": "/dashboard"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        self.assertEqual(login.status_code, 302)
        response = self.client.get("/api/telemetry/rootline/daily-irrigation-plan")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.get_json()["writes_performed"])
        self.assertFalse(response.get_json()["hardware_control_performed"])


if __name__ == "__main__":
    unittest.main()
