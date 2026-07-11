import tempfile
import unittest
import inspect
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


def live_loader(status="", limit=5, compact=True):
    return {
        "success": True,
        "status": "ok",
        "missions": [
            {
                "mission_id": "CHARLIE-MISSION-BLOCKED-001",
                "status": "blocked",
                "title": "Fix SAM live stock useful replies",
                "raw_text": "",
            },
            {
                "mission_id": "CHARLIE-MISSION-READY-002",
                "status": "pr_ready",
                "title": "Review loading sheet release",
                "raw_text": "",
            },
        ],
    }, 200


def empty_live_loader(status="", limit=5, compact=True):
    return {"success": True, "status": "ok", "missions": []}, 200


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
            self.assertIn("Source: fallback docs menu", client.messages[0]["text"])
            keyboard = client.messages[0]["reply_markup"]["inline_keyboard"]
            self.assertEqual(len(keyboard), 5)
            self.assertEqual(keyboard[0][0]["callback_data"], "charlie_next:1")

    def test_next_prefers_live_supabase_mission_queue(self):
        client = FakeTelegramClient()

        result = build_relay_telegram_buttons.handle_update(
            {"message": {"text": "/next", "from": {"id": 1001}, "chat": {"id": 1001}}},
            environ=enabled_env(),
            client=client,
            option_source_loader=live_loader,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "sent_next_menu")
        text = client.messages[0]["text"]
        self.assertIn("Source: live Supabase CHARLIE mission queue", text)
        self.assertIn("[P0] BLOCKED: Fix SAM live stock useful replies", text)
        self.assertIn("[P0] PR_READY: Review loading sheet release", text)
        self.assertNotIn("Fix SAM useful livestock replies", text)
        keyboard = client.messages[0]["reply_markup"]["inline_keyboard"]
        self.assertEqual(len(keyboard), 2)

    def test_next_falls_back_to_docs_when_live_queue_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            next_steps = Path(tmp) / "NEXT_STEPS.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            client = FakeTelegramClient()

            result = build_relay_telegram_buttons.handle_update(
                {"message": {"text": "/next", "from": {"id": 1001}, "chat": {"id": 1001}}},
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
                option_source_loader=empty_live_loader,
            )

            self.assertTrue(result.ok)
            self.assertIn("Source: fallback docs menu", client.messages[0]["text"])
            self.assertIn("Fix SAM useful livestock replies", client.messages[0]["text"])

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
                option_source_loader=empty_live_loader,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.action, "selected_mission")
            self.assertEqual(result.selected_option, 2)
            self.assertIn("Build CHARLIE mission runner watchdog", codex_chat.read_text(encoding="utf-8"))
            self.assertEqual(client.answers[0]["text"], "Manual handoff written.")
            self.assertIn("CHARLIE mission selected", client.messages[0]["text"])
            self.assertIn("Manual CODEX_CHAT handoff updated", client.messages[0]["text"])
            archived = list((root / ".archive").glob("*.CODEX_CHAT.md"))
            self.assertEqual(len(archived), 1)
            self.assertIn("old owner note", archived[0].read_text(encoding="utf-8"))

    def test_callback_writes_live_mission_to_codex_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            codex_chat = root / "CODEX_CHAT.md"
            client = FakeTelegramClient()

            result = build_relay_telegram_buttons.handle_update(
                {
                    "callback_query": {
                        "id": "cb1",
                        "data": "charlie_next:1",
                        "from": {"id": 1001},
                        "message": {"chat": {"id": 1001}},
                    }
                },
                environ=enabled_env(),
                client=client,
                codex_chat_path=codex_chat,
                option_source_loader=live_loader,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.action, "selected_mission")
            written = codex_chat.read_text(encoding="utf-8")
            self.assertIn("BLOCKED: Fix SAM live stock useful replies", written)
            self.assertIn("Manual transitional CODEX_CHAT handoff selected through CHARLIE Telegram /next from supabase_charlie_missions.", written)
            self.assertIn("Manual CODEX_CHAT handoff updated", client.messages[0]["text"])

    def test_loop_6_5_docs_mark_supabase_primary_and_gpt_5_6_disabled(self):
        contract = Path("docs/06-operations/MISSION_LOOP_CONTRACT.md").read_text(encoding="utf-8")
        build_relay = Path("docs/06-operations/BUILD_RELAY.md").read_text(encoding="utf-8")
        workflow = Path("docs/06-operations/CODEX_CHAT_WORKFLOW.md").read_text(encoding="utf-8")
        combined = "\n".join([contract, build_relay, workflow])

        self.assertIn("Supabase `charlie_missions`", combined)
        self.assertIn("CODEX_CHAT.md` is manual", combined)
        self.assertIn("Loop 7A", combined)
        self.assertIn("GPT-5.6 Sol", combined)
        self.assertIn("GPT-5.6 Terra", combined)
        self.assertIn("GPT-5.6 Luna", combined)
        self.assertIn("GPT-5.6 routing is planned but disabled", combined)
        self.assertIn("no live model calls are allowed", combined)

    def test_button_flow_has_no_shell_or_model_api_surfaces(self):
        source = inspect.getsource(build_relay_telegram_buttons)

        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)
        for provider in ["openai", "anthropic", "claude", "fable", "glm", "openrouter"]:
            self.assertNotIn(provider, source.lower())

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
                option_source_loader=empty_live_loader,
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
