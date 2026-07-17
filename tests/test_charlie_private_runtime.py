import unittest
from unittest.mock import patch

from modules.charlie.private_runtime import handle_private_telegram_webhook


ENV = {
    "CHARLIE_PRIVATE_EXECUTIVE_ENABLED": "1",
    "CHARLIE_PRIVATE_TELEGRAM_BOT_TOKEN": "test-token",
    "CHARLIE_PRIVATE_TELEGRAM_WEBHOOK_SECRET": "s" * 32,
    "CHARLIE_PRIVATE_TELEGRAM_OWNER_USER_ID": "10",
    "CHARLIE_PRIVATE_TELEGRAM_OWNER_CHAT_ID": "10",
}
HEADERS = {"X-Telegram-Bot-Api-Secret-Token": "s" * 32}


class FakeStore:
    def __init__(self):
        self.claimed = set()
        self.messages = []
        self.intents = []
        self.tools = []
        self.bundles = {}

    def claim_update(self, update, callback=""):
        created = update not in self.claimed
        self.claimed.add(update)
        return {"success": True, "created": created, "update_key": "UPDATE-" + update}, 201 if created else 200

    def complete_update(self, *args, **kwargs): return {"success": True}, 200
    def bind_owner(self, user, chat, metadata=None): return {"success": True, "binding_id": "OWNER", "thread_id": "THREAD", "telegram_chat_id": chat}, 200
    def record_message(self, thread, role, content, **kwargs):
        row = {"message_id": f"MSG-{len(self.messages)}", "role": role, "content": content}
        self.messages.append(row)
        return row, 201
    def recent_context(self, thread): return {"messages": self.messages, "open_context": {}}, 200
    def record_intent(self, thread, message, intent):
        self.intents.append(intent)
        return {"intent_id": "INTENT-1"}, 201
    def record_tool_execution(self, *args, **kwargs): self.tools.append((args, kwargs)); return {"success": True}, 201
    def create_approval_bundle(self, thread, title, summary, decisions, recommendation, state_hash):
        self.bundles["BUNDLE-1"] = decisions
        return {"bundle_id": "BUNDLE-1"}, 201
    def decide_bundle(self, bundle, decision): return {"success": True, "status": decision, "bundle_id": bundle}, 200
    def remember_preference(self, key, value, message, approved=False): return {"success": True, "status": "approved"}, 200


def payload(update_id, text="status"):
    return {"update_id": update_id, "message": {"message_id": 4, "from": {"id": 10}, "chat": {"id": 10, "type": "private"}, "text": text}}


class CharliePrivateRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.store = FakeStore()
        self.sent = []
        self.sender = lambda chat, text, **kwargs: (self.sent.append((chat, text, kwargs)) or {"success": True, "status": "sent"}, 200)

    @patch("modules.charlie.private_runtime.execute_private_tool", return_value=({"summary": "CORE is healthy."}, 200))
    def test_duplicate_update_sends_exactly_once(self, _tool):
        first, code = handle_private_telegram_webhook(payload("1"), HEADERS, environ=ENV, sender=self.sender, store=self.store)
        duplicate, duplicate_code = handle_private_telegram_webhook(payload("1"), HEADERS, environ=ENV, sender=self.sender, store=self.store)
        self.assertEqual((code, duplicate_code), (200, 200))
        self.assertEqual(len(self.sent), 1)
        self.assertEqual(duplicate["status"], "duplicate_update_ignored")

    def test_unauthorized_update_sends_nothing(self):
        bad = payload("2")
        bad["message"]["from"]["id"] = 99
        result, code = handle_private_telegram_webhook(bad, HEADERS, environ=ENV, sender=self.sender, store=self.store)
        self.assertEqual(code, 200)
        self.assertEqual(result["status"], "unauthorized_update_ignored")
        self.assertEqual(self.sent, [])

    def test_ambiguous_text_asks_clarification_without_tool(self):
        result, code = handle_private_telegram_webhook(payload("3", "please sort it"), HEADERS, environ=ENV, sender=self.sender, store=self.store)
        self.assertEqual(code, 200)
        self.assertIn("right thing", result["reply"])
        self.assertEqual(self.store.tools, [])

    def test_explicit_preference_is_remembered(self):
        result, code = handle_private_telegram_webhook(payload("5", "Remember that I only want urgent CORE alerts"), HEADERS, environ=ENV, sender=self.sender, store=self.store)
        self.assertEqual(code, 200)
        self.assertIn("saved", result["reply"])

    def test_callback_acknowledged_once_and_duplicate_skipped(self):
        ack = []
        callback = {"update_id": "4", "callback_query": {"id": "CB-1", "from": {"id": 10}, "message": {"chat": {"id": 10, "type": "private"}}, "data": "cp:BUNDLE-1:approve"}}
        answer = lambda callback_id, **kwargs: ack.append(callback_id)
        self.assertEqual(handle_private_telegram_webhook(callback, HEADERS, environ=ENV, sender=self.sender, callback_answerer=answer, store=self.store)[1], 200)
        self.assertEqual(handle_private_telegram_webhook(callback, HEADERS, environ=ENV, sender=self.sender, callback_answerer=answer, store=self.store)[1], 200)
        self.assertEqual(ack, ["CB-1"])
        self.assertEqual(len(self.sent), 1)
        self.assertIn("approved and recorded", self.sent[0][1])


if __name__ == "__main__":
    unittest.main()
