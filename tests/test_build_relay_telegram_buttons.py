import tempfile
import unittest
from pathlib import Path

from scripts import build_relay_telegram_buttons


NEXT_STEPS = """
# Next Steps

## P0
- Fix SAM useful livestock replies
- Build CHARLIE mission runner watchdog
- Repair quote PDF delivery

## P1
- Add delivery quote calculator
- Improve loading sheet workflow
"""


class FakeTelegramClient:
    def __init__(self):
        self.messages = []
        self.answers = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})

    def answer_callback_query(self, callback_query_id, text=""):
        self.answers.append({"id": callback_query_id, "text": text})


def enabled_env():
    return {
        "CHARLIE_BUILD_RELAY_ENABLED": "1",
        "CHARLIE_BUILD_RELAY_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyzABCDEF",
        "CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS": "1001",
    }


class BuildRelayTelegramButtonsTests(unittest.TestCase):
    def test_disabled_flow_does_nothing(self):
        client = FakeTelegramClient()

        result = build_relay_telegram_buttons.handle_update(
            {"message": {"text": "/next", "from": {"id": 1001}, "chat": {"id": 1001}}},
            environ={},
            client=client,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "disabled")
        self.assertEqual(client.messages, [])

    def test_next_sends_top_five_buttons_for_authorized_owner(self):
        with tempfile.TemporaryDirectory() as tmp:
            next_steps = Path(tmp) / "NEXT_STEPS.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            client = FakeTelegramClient()

            result = build_relay_telegram_buttons.handle_update(
                {"message": {"text": "/next", "from": {"id": 1001}, "chat": {"id": 1001}}},
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.action, "sent_next_menu")
            self.assertEqual(len(client.messages), 1)
            self.assertIn("CHARLIE NEXT MISSIONS", client.messages[0]["text"])
            keyboard = client.messages[0]["reply_markup"]["inline_keyboard"]
            self.assertEqual(len(keyboard), 5)
            self.assertEqual(keyboard[0][0]["callback_data"], "charlie_next:1")

    def test_unauthorized_next_is_ignored(self):
        client = FakeTelegramClient()

        result = build_relay_telegram_buttons.handle_update(
            {"message": {"text": "/next", "from": {"id": 9999}, "chat": {"id": 9999}}},
            environ=enabled_env(),
            client=client,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "unauthorized_user")
        self.assertEqual(client.messages, [])

    def test_callback_writes_codex_chat_and_confirms(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_steps = root / "NEXT_STEPS.md"
            codex_chat = root / "CODEX_CHAT.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            codex_chat.write_text("old owner note", encoding="utf-8")
            client = FakeTelegramClient()

            result = build_relay_telegram_buttons.handle_update(
                {
                    "callback_query": {
                        "id": "cb1",
                        "data": "charlie_next:2",
                        "from": {"id": 1001},
                        "message": {"chat": {"id": 1001}},
                    }
                },
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.action, "selected_mission")
            self.assertEqual(result.selected_option, 2)
            self.assertIn("Build CHARLIE mission runner watchdog", codex_chat.read_text(encoding="utf-8"))
            self.assertEqual(client.answers[0]["text"], "Mission written to CODEX_CHAT.")
            self.assertIn("CHARLIE mission selected", client.messages[0]["text"])
            archived = list((root / ".archive").glob("*.CODEX_CHAT.md"))
            self.assertEqual(len(archived), 1)
            self.assertIn("old owner note", archived[0].read_text(encoding="utf-8"))

    def test_invalid_callback_does_not_write_codex_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_steps = root / "NEXT_STEPS.md"
            codex_chat = root / "CODEX_CHAT.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            client = FakeTelegramClient()

            result = build_relay_telegram_buttons.handle_update(
                {
                    "callback_query": {
                        "id": "cb1",
                        "data": "charlie_next:99",
                        "from": {"id": 1001},
                        "message": {"chat": {"id": 1001}},
                    }
                },
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.action, "selection_failed")
            self.assertFalse(codex_chat.exists())
            self.assertEqual(client.answers[0]["text"], "Mission selection failed.")

    def test_unknown_callback_is_rejected(self):
        client = FakeTelegramClient()

        result = build_relay_telegram_buttons.handle_update(
            {
                "callback_query": {
                    "id": "cb1",
                    "data": "other:1",
                    "from": {"id": 1001},
                    "message": {"chat": {"id": 1001}},
                }
            },
            environ=enabled_env(),
            client=client,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "unknown_callback")
        self.assertEqual(client.answers[0]["text"], "Unknown CHARLIE action.")


if __name__ == "__main__":
    unittest.main()

