import json
import unittest
from pathlib import Path


class SamLivestockInboxOperatorWorkflowTests(unittest.TestCase):
    def test_schedule_uses_protected_variables_and_no_telegram(self):
        path = (
            Path(__file__).parents[1]
            / "docs/04-n8n/workflows/SAM Livestock Inbox Operator/workflow.json"
        )
        workflow = json.loads(path.read_text(encoding="utf-8"))
        encoded = json.dumps(workflow)
        self.assertFalse(workflow["active"])
        self.assertIn("scheduleTrigger", encoded)
        self.assertIn("$vars.AMADEUS_BACKEND_URL", encoded)
        self.assertIn("$vars.SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN", encoded)
        self.assertIn("/sam-live-stock/reconcile", encoded)
        self.assertNotIn("telegramTrigger", encoded)
        self.assertNotIn("$env.", encoded)


if __name__ == "__main__":
    unittest.main()
