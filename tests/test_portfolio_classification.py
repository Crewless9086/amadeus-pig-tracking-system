import unittest
from unittest.mock import patch

from modules.charlie.mission_store import (
    consume_final_agent_artifact, mission_runtime_eligible,
    record_final_artifact_rejection, record_mission_event, update_mission_workflow_step,
)
from modules.charlie.portfolio_classification import (
    APPROVED_BASELINE_DIGEST, classification_set_digest, classify_legacy_portfolio,
)


class PortfolioClassificationTests(unittest.TestCase):
    def test_classification_digest_is_order_invariant(self):
        self.assertEqual(classification_set_digest({"B": "historical", "A": "superseded"}),
                         classification_set_digest({"A": "superseded", "B": "historical"}))

    def test_wrong_baseline_and_wrong_set_fail_before_database(self):
        result, status = classify_legacy_portfolio({}, APPROVED_BASELINE_DIGEST)
        self.assertEqual((status, result["status"]), (400, "approved_classification_set_required"))
        result, status = classify_legacy_portfolio({str(i): "historical" for i in range(86)}, "wrong")
        self.assertEqual((status, result["status"]), (409, "baseline_digest_mismatch"))
        result, status = classify_legacy_portfolio({str(i): "historical" for i in range(86)}, APPROVED_BASELINE_DIGEST)
        self.assertEqual((status, result["status"]), (409, "approved_classification_set_mismatch"))

    def test_classified_rows_are_not_runtime_eligible(self):
        self.assertTrue(mission_runtime_eligible({"metadata": {}}))
        self.assertFalse(mission_runtime_eligible({"metadata": {"portfolio_classification": {"runnable": True}}}))

    def test_generic_event_api_cannot_forge_classification(self):
        result, status = record_mission_event("LEGACY", "portfolio_classified")
        self.assertEqual((status, result["status"]), (400, "invalid_event_type"))

    def test_late_workflow_callback_fails_before_vault_write(self):
        mission = {"mission_id": "LEGACY", "status": "paused", "metadata": {"portfolio_classification": {}}}
        with patch("modules.charlie.mission_store.get_mission", return_value=({"mission": mission}, 200)), \
             patch("modules.charlie.mission_store.update_mission_vault") as write:
            result, status = update_mission_workflow_step("LEGACY", "builder")
        self.assertEqual((status, result["status"]), (409, "portfolio_classified_mission_ineligible"))
        write.assert_not_called()

    def test_late_artifact_and_rejection_callbacks_perform_no_update(self):
        class Cursor:
            def __init__(self): self.statements = []
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, sql, _params=None): self.statements.append(sql)
            def fetchall(self): return [({"portfolio_classification": {}},)]
        class Connection:
            def __init__(self): self.cursor_value = Cursor()
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def cursor(self): return self.cursor_value
        connections = []
        def factory(_url):
            connection = Connection(); connections.append(connection); return connection
        consumed, consumed_status = consume_final_agent_artifact(
            "LEGACY", "planner", "EXEC", 1, {"summary": "late"}, "a" * 64, connect_factory=factory)
        rejected, rejected_status = record_final_artifact_rejection(
            "LEGACY", "builder", "EXEC", 1, {}, "b" * 64, ["source_revision"], connect_factory=factory)
        self.assertEqual((consumed_status, consumed["status"]), (409, "portfolio_classified_mission_ineligible"))
        self.assertEqual((rejected_status, rejected["status"]), (409, "portfolio_classified_mission_ineligible"))
        self.assertTrue(all(len(connection.cursor_value.statements) == 1 for connection in connections))

if __name__ == "__main__":
    unittest.main()
