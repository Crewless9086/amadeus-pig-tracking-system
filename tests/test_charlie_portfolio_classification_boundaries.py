import unittest
from unittest.mock import patch

from modules.charlie.execution_bridge import _load_execution_mission, _load_release_mission


def classified(status):
    return {"mission_id": "LEGACY-85", "status": status,
            "metadata": {"portfolio_classification": {"classification": "test_evidence", "runnable": False}}}


class PortfolioClassificationBoundaryTests(unittest.TestCase):
    @patch("modules.charlie.execution_bridge.get_mission")
    def test_direct_execution_and_release_fail_closed(self, get_mission):
        get_mission.return_value = ({"mission": classified("in_progress")}, 200)
        self.assertEqual(_load_execution_mission("LEGACY-85")[2]["status"], "portfolio_classified_mission_ineligible")
        get_mission.return_value = ({"mission": classified("release_approved")}, 200)
        self.assertEqual(_load_release_mission("LEGACY-85")[2]["status"], "portfolio_classified_mission_ineligible")

    @patch("modules.charlie.execution_bridge.list_missions")
    def test_queue_loader_skips_classified_row(self, list_missions):
        eligible = {"mission_id": "CURRENT", "status": "in_progress", "metadata": {}}
        list_missions.return_value = ({"missions": [classified("in_progress"), eligible]}, 200)
        mission, status, _ = _load_execution_mission()
        self.assertEqual((status, mission["mission_id"]), (200, "CURRENT"))


if __name__ == "__main__":
    unittest.main()
