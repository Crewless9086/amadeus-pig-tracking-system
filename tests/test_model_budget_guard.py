import json
import tempfile
import unittest
from pathlib import Path

from scripts import model_budget_guard


class ModelBudgetGuardTests(unittest.TestCase):
    def test_missing_budget_config(self):
        result = model_budget_guard.check_budget(path=Path("does-not-exist.json"))

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "missing_budget_config")

    def test_disabled_no_provider_mode_passes(self):
        result = model_budget_guard.check_budget(
            provider="claude",
            stage="review",
            planned_usd=999,
            config={"policy": {"live_model_api_calls_enabled": False}, "caps": {}},
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "disabled")

    def test_over_budget_blocks(self):
        result = model_budget_guard.check_budget(
            provider="claude",
            stage="review",
            planned_usd=3.0,
            spent_today_usd=4.0,
            config={
                "policy": {"live_model_api_calls_enabled": True},
                "caps": {
                    "daily_limit_usd": 5.0,
                    "mission_limit_usd": 5.0,
                    "provider_limits": {"claude": 5.0},
                    "stage_limits": {"review": 5.0},
                },
            },
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.status, "blocked_budget")
        self.assertEqual(result.reason, "daily_limit_exceeded")

    def test_provider_limit_blocks(self):
        result = model_budget_guard.check_budget(
            provider="claude",
            stage="triage",
            planned_usd=2.0,
            config={
                "policy": {"live_model_api_calls_enabled": True},
                "caps": {
                    "daily_limit_usd": 10.0,
                    "mission_limit_usd": 10.0,
                    "provider_limits": {"claude": 1.0},
                    "stage_limits": {"triage": 10.0},
                },
            },
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "provider_limit_exceeded")

    def test_stage_limit_blocks(self):
        result = model_budget_guard.check_budget(
            provider="cheap",
            stage="triage",
            planned_usd=2.0,
            config={
                "policy": {"live_model_api_calls_enabled": True},
                "caps": {
                    "daily_limit_usd": 10.0,
                    "mission_limit_usd": 10.0,
                    "provider_limits": {"cheap": 10.0},
                    "stage_limits": {"triage": 1.0},
                },
            },
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "stage_limit_exceeded")

    def test_budget_passes_when_inside_caps(self):
        result = model_budget_guard.check_budget(
            provider="cheap",
            stage="triage",
            planned_usd=0.25,
            spent_today_usd=1.0,
            spent_mission_usd=0.5,
            config={
                "policy": {"live_model_api_calls_enabled": True},
                "caps": {
                    "daily_limit_usd": 5.0,
                    "mission_limit_usd": 2.0,
                    "provider_limits": {"cheap": 2.0},
                    "stage_limits": {"triage": 1.0},
                },
            },
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.status, "ok")

    def test_reads_budget_file_without_api_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "budget.json"
            path.write_text(
                json.dumps(
                    {
                        "policy": {"live_model_api_calls_enabled": False},
                        "caps": {"daily_limit_usd": 0, "mission_limit_usd": 0},
                    }
                ),
                encoding="utf-8",
            )

            result = model_budget_guard.check_budget(path=path, provider="glm", stage="triage")

            self.assertTrue(result.ok)
            self.assertEqual(result.status, "disabled")


if __name__ == "__main__":
    unittest.main()

