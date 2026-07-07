import unittest
from unittest.mock import patch

from app import app
from modules.charlie.owner_approval_inbox import (
    list_owner_approval_inbox,
    normalize_owner_approval_item,
    record_owner_approval_decision,
)


class CharlieOwnerApprovalInboxTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()

    def test_normalizes_named_agent_sources_without_runtime_authority(self):
        item = normalize_owner_approval_item(
            {
                "approval_id": "BEACON-PACKET-1",
                "source_type": "beacon_publish_packet",
                "exact_text": "Limited pork freezer run. Message SAM to enquire.",
                "approval_status": "owner_review_required",
            },
            {"mission_id": "MISSION-1", "status": "pr_ready", "title": "Beacon launch"},
        )

        self.assertEqual(item["source_type"], "beacon_post_packet")
        self.assertEqual(item["source_agent"], "Beacon")
        self.assertEqual(item["status"], "pending")
        self.assertFalse(item["authority"]["posts_publicly"])
        self.assertFalse(item["authority"]["sends_customer_message"])
        self.assertFalse(item["authority"]["writes_farm_lifecycle"])

    @patch("modules.charlie.owner_approval_inbox.list_owner_work_missions")
    def test_lists_items_from_existing_mission_metadata(self, list_owner_work_missions):
        def fake_list(status, limit=12, database_url=None, connect_factory=None):
            if status != "pr_ready":
                return {"success": True, "configured": True, "status": "ok", "missions": []}, 200
            return {
                "success": True,
                "configured": True,
                "status": "ok",
                "missions": [{
                    "mission_id": "MISSION-1",
                    "status": "pr_ready",
                    "title": "SAM owner review",
                    "metadata": {
                        "owner_approval_inbox": {
                            "items": [{
                                "approval_id": "SAM-REPLY-1",
                                "source_type": "sam_live_stock_reply",
                                "suggested_reply_text": "I can help with two weaners. Are you collecting in Riversdale?",
                            }],
                        },
                    },
                }],
            }, 200

        list_owner_work_missions.side_effect = fake_list

        result, status_code = list_owner_approval_inbox()

        self.assertEqual(status_code, 200)
        self.assertEqual(result["items"][0]["approval_id"], "SAM-REPLY-1")
        self.assertEqual(result["items"][0]["source_agent"], "SAM Live Stock")
        self.assertEqual(result["pending_count"], 1)
        self.assertFalse(result["authority"]["approval_executes_action"])

    @patch("modules.charlie.owner_approval_inbox.update_mission_vault")
    @patch("modules.charlie.owner_approval_inbox.get_mission")
    def test_records_edit_decision_back_to_mission_metadata_only(self, get_mission, update_mission_vault):
        get_mission.return_value = ({
            "success": True,
            "status": "ok",
            "mission": {
                "mission_id": "MISSION-1",
                "status": "pr_ready",
                "metadata": {
                    "owner_approval_inbox": {
                        "items": [{
                            "approval_id": "MEAT-REPLY-1",
                            "source_type": "sam_meat_controlled_reply",
                            "exact_text": "Should I note Set A for you?",
                        }],
                    },
                },
            },
        }, 200)
        update_mission_vault.return_value = ({"success": True, "status": "ok"}, 200)

        result, status_code = record_owner_approval_decision(
            "MISSION-1",
            "MEAT-REPLY-1",
            "edit",
            comments="Make it shorter.",
            edited_text="Should I note Set A?",
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["item_status"], "edited")
        self.assertFalse(result["authority"]["sends_customer_message"])
        update_mission_vault.assert_called_once()
        inbox = update_mission_vault.call_args.args[1]["owner_approval_inbox"]
        self.assertEqual(inbox["items"][0]["status"], "edited")
        self.assertEqual(inbox["items"][0]["edited_text"], "Should I note Set A?")
        self.assertFalse(inbox["decisions"][0]["approval_executes_action"])

    @patch("modules.charlie.routes.require_owner_read_access", return_value=None)
    @patch("modules.charlie.routes.list_owner_approval_inbox")
    def test_owner_approval_inbox_route_returns_record_only_packet(self, list_owner_approval_inbox_mock, _owner_access):
        list_owner_approval_inbox_mock.return_value = ({
            "success": True,
            "status": "ok",
            "items": [],
            "authority": {"approval_executes_action": False},
        }, 200)

        response = self.client.get("/api/charlie/owner-approval-inbox")
        data = response.get_json()

        self.assertEqual(response.status_code, 200)
        self.assertFalse(data["authority"]["approval_executes_action"])


if __name__ == "__main__":
    unittest.main()
