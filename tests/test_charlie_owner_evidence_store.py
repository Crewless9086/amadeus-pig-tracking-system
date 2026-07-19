import unittest
from unittest.mock import MagicMock, patch

from modules.charlie.domain_observer_store import record_observer_feedback
from modules.charlie.executive_store import upsert_executive_goal


class CharlieOwnerEvidenceStoreTests(unittest.TestCase):
    def test_feedback_requires_explicit_boolean_owner_judgment(self):
        result, status = record_observer_feedback("RUN-1", "REC-1", useful="yes")
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "observer_feedback_fields_required")

    @patch("modules.charlie.domain_observer_store._connect")
    def test_feedback_is_upserted_by_recommendation_and_owner(self, connect):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("FB-1",)
        connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        result, status = record_observer_feedback(
            "RUN-1", "REC-1", useful=False, owner_note="Cancelled order is not a payment exception.",
            database_url="postgresql://test",
        )
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertIn("on conflict (recommendation_id,recorded_by) do update", cursor.execute.call_args.args[0])

    def test_goal_requires_explicit_success_metrics(self):
        result, status = upsert_executive_goal({
            "goal_id": "GOAL-1", "title": "Revenue", "objective": "Grow", "business_area": "revenue",
            "success_metrics": [],
        })
        self.assertEqual(status, 400)
        self.assertEqual(result["status"], "executive_goal_fields_required")

    @patch("modules.charlie.executive_store._connect")
    def test_owner_goal_is_recorded_active_without_granting_authority(self, connect):
        cursor = MagicMock()
        cursor.fetchone.return_value = ("GOAL-1",)
        connect.return_value.__enter__.return_value.cursor.return_value.__enter__.return_value = cursor
        result, status = upsert_executive_goal({
            "goal_id": "GOAL-1", "title": "Revenue", "objective": "Grow profitable sales",
            "business_area": "revenue", "priority": 100,
            "success_metrics": [{"metric": "monthly_sales_zar", "target": 100000}],
            "constraints": ["preserve stock and payment accuracy"],
        }, database_url="postgresql://test")
        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        sql = cursor.execute.call_args.args[0]
        self.assertIn("charlie_executive_goals", sql)
        self.assertNotIn("charlie_delegation_policies", sql)


if __name__ == "__main__":
    unittest.main()
