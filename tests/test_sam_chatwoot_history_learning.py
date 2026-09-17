import json
import unittest
from datetime import datetime, timezone

from modules.sales.chatwoot_history_learning import recover_chatwoot_learning


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class SamChatwootHistoryLearningTests(unittest.TestCase):
    def setUp(self):
        self.environ = {
            "CHATWOOT_BASE_URL": "https://chatwoot.example",
            "CHATWOOT_ACCOUNT_ID": "123",
            "CHATWOOT_API_ACCESS_TOKEN": "secret",
        }
        self.now = datetime(2026, 7, 19, 12, tzinfo=timezone.utc)

    def test_preview_pairs_customer_messages_with_real_owner_reply_without_writes(self):
        calls = []

        def opener(request, timeout=0):
            calls.append((request.full_url, request.method, timeout))
            if request.full_url.endswith("page=1"):
                return _Response({"data": {"payload": [{"id": 77, "last_activity_at": 1784460000}]}})
            if "/conversations/77/messages" in request.full_url:
                return _Response({"payload": [
                    {"id": 1, "message_type": 0, "content": "Do you have pigs?", "created_at": 1784450000},
                    {"id": 2, "message_type": 0, "content": "What price?", "created_at": 1784450100},
                    {"id": 3, "message_type": 1, "content": "Yes, what weight do you need?", "created_at": 1784450200},
                ]})
            return _Response({"data": {"payload": []}})

        def forbidden_recorder(_event):
            raise AssertionError("dry-run must not write")

        result = recover_chatwoot_learning(
            days=14, dry_run=True, environ=self.environ, now=self.now,
            opener=opener, recorder=forbidden_recorder,
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["candidate_count"], 1)
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["sample"][0]["incoming_message_count"], 2)
        self.assertTrue(all(method == "GET" for _, method, _ in calls))
        self.assertTrue(all("secret" not in url for url, _, _ in calls))
        self.assertFalse(any(result["authority"].values()))

    def test_apply_is_append_only_and_reports_duplicates(self):
        recorded = []

        def opener(request, timeout=0):
            if request.full_url.endswith("page=1"):
                return _Response({"data": {"payload": [{"id": 88, "last_activity_at": 1784460000}]}})
            if "/conversations/88/messages" in request.full_url:
                return _Response({"payload": [
                    {"id": 10, "message_type": 0, "content": "Where are you?", "created_at": 1784450000},
                    {"id": 11, "message_type": 1, "content": "Near Magaliesburg.", "created_at": 1784450100},
                    {"id": 12, "message_type": 1, "content": "Automated", "created_at": 1784450200,
                     "content_attributes": {"sam_live_stock_generated": True}},
                ]})
            return _Response({"data": {"payload": []}})

        def recorder(event):
            recorded.append(event)
            return ({"success": True, "status": "sales_conversation_learning_event_already_recorded", "created_count": 0}, 200)

        result = recover_chatwoot_learning(
            days=14, dry_run=False, environ=self.environ, now=self.now,
            opener=opener, recorder=recorder,
        )

        self.assertEqual(len(recorded), 1)
        self.assertEqual(result["duplicate_count"], 1)
        self.assertEqual(recorded[0]["captured_facts"]["learning_kind"], "owner_reply_historical_example")
        self.assertEqual(recorded[0]["sam_reply_excerpt"], "")
        self.assertFalse(recorded[0]["applies_learning_now"])

    def test_existing_live_capture_is_removed_from_import_candidates(self):
        def opener(request, timeout=0):
            if request.full_url.endswith("page=1"):
                return _Response({"data": {"payload": [{"id": 99, "last_activity_at": 1784460000}]}})
            if "/conversations/99/messages" in request.full_url:
                return _Response({"payload": [
                    {"id": 20, "message_type": 0, "content": "Price?", "created_at": 1784450000},
                    {"id": 21, "message_type": 1, "content": "R40 per kg", "created_at": 1784450100},
                ]})
            return _Response({"data": {"payload": []}})

        result = recover_chatwoot_learning(
            days=14, dry_run=True, environ=self.environ, now=self.now, opener=opener,
            existing_key_loader=lambda _url: {"99|r40 per kg"},
        )

        self.assertEqual(result["candidate_count"], 0)
        self.assertEqual(result["already_captured_count"], 1)


if __name__ == "__main__":
    unittest.main()
