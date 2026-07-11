import tempfile
import unittest
import inspect
from pathlib import Path

from scripts import charlie_telegram_relay


NEXT_STEPS = """
# Next Steps

## P0
- Fix SAM livestock reply usefulness
- Build CHARLIE runner recovery

## P1
- Improve quote sending workflow
"""


class FakeRelayClient:
    def __init__(self, updates=None):
        self.messages = []
        self.answers = []
        self.updates = list(updates or [])
        self.offsets = []

    def send_message(self, chat_id, text, reply_markup=None):
        self.messages.append({"chat_id": str(chat_id), "text": text, "reply_markup": reply_markup})

    def answer_callback_query(self, callback_query_id, text=""):
        self.answers.append({"id": callback_query_id, "text": text})

    def get_updates(self, offset=None, timeout=30):
        self.offsets.append(offset)
        updates = self.updates
        self.updates = []
        return updates


class FailingPollClient(FakeRelayClient):
    def get_updates(self, offset=None, timeout=30):
        raise TimeoutError("temporary Telegram timeout")


def enabled_env():
    return {
        "CHARLIE_BUILD_RELAY_ENABLED": "1",
        "CHARLIE_BUILD_RELAY_BOT_TOKEN": "123456:abcdefghijklmnopqrstuvwxyzABCDEF",
        "CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS": "1001",
    }


class CharlieTelegramRelayTests(unittest.TestCase):
    def test_disabled_relay_does_nothing_safely(self):
        client = FakeRelayClient()

        result = charlie_telegram_relay.handle_relay_update(
            {"message": {"text": "/next", "from": {"id": 1001}, "chat": {"id": 1001}}},
            environ={},
            client=client,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "disabled")
        self.assertEqual(client.messages, [])

    def test_enabled_missing_env_fails_safely(self):
        result = charlie_telegram_relay.validate_config(
            charlie_telegram_relay.load_config({"CHARLIE_BUILD_RELAY_ENABLED": "1"})
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.action, "config_failed")
        self.assertIn("required", result.reason)

    def test_allowed_user_can_call_next(self):
        with tempfile.TemporaryDirectory() as tmp:
            next_steps = Path(tmp) / "NEXT_STEPS.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            client = FakeRelayClient()

            result = charlie_telegram_relay.handle_relay_update(
                {"message": {"text": "/next", "from": {"id": 1001}, "chat": {"id": 1001}}},
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.action, "sent_next_menu")
            self.assertEqual(len(client.messages), 1)
            self.assertIn("CHARLIE NEXT MISSIONS", client.messages[0]["text"])

    def test_unauthorized_user_cannot_call_next(self):
        client = FakeRelayClient()

        result = charlie_telegram_relay.handle_relay_update(
            {"message": {"text": "/next", "from": {"id": 999}, "chat": {"id": 999}}},
            environ=enabled_env(),
            client=client,
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.reason, "unauthorized_user")
        self.assertEqual(client.messages, [])

    def test_status_works(self):
        client = FakeRelayClient()

        result = charlie_telegram_relay.handle_relay_update(
            {"message": {"text": "/status", "from": {"id": 1001}, "chat": {"id": 1001}}},
            environ=enabled_env(),
            client=client,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "status_sent")
        self.assertIn("reads live Supabase CHARLIE missions first", client.messages[0]["text"])
        self.assertIn("No Codex run", client.messages[0]["text"])

    def test_start_works(self):
        client = FakeRelayClient()

        result = charlie_telegram_relay.handle_relay_update(
            {"message": {"text": "/start", "from": {"id": 1001}, "chat": {"id": 1001}}},
            environ=enabled_env(),
            client=client,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "start_sent")
        self.assertIn("/next", client.messages[0]["text"])

    def test_callback_selection_writes_codex_chat_in_temp_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_steps = root / "NEXT_STEPS.md"
            codex_chat = root / "CODEX_CHAT.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            client = FakeRelayClient()

            result = charlie_telegram_relay.handle_relay_update(
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
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.action, "selected_mission")
            self.assertIn("Fix SAM livestock reply usefulness", codex_chat.read_text(encoding="utf-8"))
            self.assertEqual(client.answers[0]["text"], "Manual handoff written.")

    def test_invalid_callback_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            next_steps = Path(tmp) / "NEXT_STEPS.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            client = FakeRelayClient()

            result = charlie_telegram_relay.handle_relay_update(
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
            )

            self.assertFalse(result.ok)
            self.assertEqual(result.action, "selection_failed")
            self.assertEqual(client.answers[0]["text"], "Mission selection failed.")

    def test_token_is_redacted_from_status_output(self):
        text = charlie_telegram_relay.status_text(
            charlie_telegram_relay.load_config(enabled_env())
        )
        self.assertNotIn(enabled_env()["CHARLIE_BUILD_RELAY_BOT_TOKEN"], text)
        self.assertIn("Allowed owners configured: 1", text)

    def test_relay_does_not_import_shell_or_model_api_surfaces(self):
        source = inspect.getsource(charlie_telegram_relay)

        self.assertNotIn("subprocess", source)
        self.assertNotIn("os.system", source)
        self.assertNotIn("openai", source.lower())
        self.assertNotIn("anthropic", source.lower())
        self.assertNotIn("openrouter", source.lower())

    def test_poll_once_dry_run_uses_injected_client(self):
        client = FakeRelayClient(
            updates=[
                {
                    "update_id": 1,
                    "message": {"text": "/status", "from": {"id": 1001}, "chat": {"id": 1001}},
                }
            ]
        )

        result = charlie_telegram_relay.poll_loop(
            environ=enabled_env(),
            client=client,
            once=True,
            dry_run=True,
            poll_timeout=1,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.action, "poll_once_complete")
        self.assertIn("CHARLIE relay status", client.messages[0]["text"])

    def test_poll_error_is_contained_and_reported_without_secret(self):
        result = charlie_telegram_relay.poll_loop(
            environ=enabled_env(),
            client=FailingPollClient(),
            once=True,
            poll_timeout=1,
        )
        self.assertFalse(result.ok)
        self.assertEqual(result.action, "poll_failed")
        self.assertEqual(result.reason, "TimeoutError")
        self.assertNotIn(enabled_env()["CHARLIE_BUILD_RELAY_BOT_TOKEN"], result.reason)

    def test_same_update_id_processed_twice_sends_once(self):
        client = FakeRelayClient()
        state = charlie_telegram_relay.RelayRuntimeState.empty()
        update = {
            "update_id": 10,
            "message": {"text": "/status", "from": {"id": 1001}, "chat": {"id": 1001}},
        }

        first = charlie_telegram_relay.handle_relay_update(update, environ=enabled_env(), client=client, state=state)
        second = charlie_telegram_relay.handle_relay_update(update, environ=enabled_env(), client=client, state=state)

        self.assertEqual(first.action, "status_sent")
        self.assertEqual(second.action, "duplicate_skipped")
        self.assertEqual(second.reason, "duplicate_update_id")
        self.assertEqual(len(client.messages), 1)
        self.assertEqual(state.duplicates_skipped, 1)

    def test_same_callback_id_processed_twice_sends_once_and_ack_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_steps = root / "NEXT_STEPS.md"
            codex_chat = root / "CODEX_CHAT.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            client = FakeRelayClient()
            state = charlie_telegram_relay.RelayRuntimeState.empty()
            update = {
                "update_id": 20,
                "callback_query": {
                    "id": "cb-repeat",
                    "data": "charlie_next:1",
                    "from": {"id": 1001},
                    "message": {"chat": {"id": 1001}},
                },
            }
            repeated_with_new_update_id = {**update, "update_id": 21}

            first = charlie_telegram_relay.handle_relay_update(
                update,
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
                state=state,
            )
            second = charlie_telegram_relay.handle_relay_update(
                repeated_with_new_update_id,
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
                state=state,
            )

            self.assertEqual(first.action, "selected_mission")
            self.assertEqual(second.action, "duplicate_skipped")
            self.assertEqual(second.reason, "duplicate_callback_id")
            self.assertEqual(len(client.answers), 1)
            self.assertEqual(len(client.messages), 1)

    def test_polling_offset_advances_to_max_update_id_plus_one(self):
        client = FakeRelayClient(
            updates=[
                {"update_id": 30, "message": {"text": "/status", "from": {"id": 1001}, "chat": {"id": 1001}}},
                {"update_id": 32, "message": {"text": "/status", "from": {"id": 1001}, "chat": {"id": 1001}}},
                {"update_id": 32, "message": {"text": "/status", "from": {"id": 1001}, "chat": {"id": 1001}}},
            ]
        )
        state = charlie_telegram_relay.RelayRuntimeState.empty()

        result = charlie_telegram_relay.poll_loop(
            environ=enabled_env(),
            client=client,
            once=True,
            poll_timeout=1,
            state=state,
        )

        self.assertTrue(result.ok)
        self.assertEqual(state.next_offset, 33)
        self.assertEqual(client.offsets, [None])
        self.assertEqual(len(client.messages), 2)
        self.assertEqual(state.duplicates_skipped, 1)

    def test_duplicate_callback_does_not_rewrite_codex_chat_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_steps = root / "NEXT_STEPS.md"
            codex_chat = root / "CODEX_CHAT.md"
            next_steps.write_text(NEXT_STEPS, encoding="utf-8")
            client = FakeRelayClient()
            state = charlie_telegram_relay.RelayRuntimeState.empty()
            update = {
                "update_id": 40,
                "callback_query": {
                    "id": "cb-once",
                    "data": "charlie_next:1",
                    "from": {"id": 1001},
                    "message": {"chat": {"id": 1001}},
                },
            }

            charlie_telegram_relay.handle_relay_update(
                update,
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
                state=state,
            )
            first_content = codex_chat.read_text(encoding="utf-8")
            charlie_telegram_relay.handle_relay_update(
                {**update, "update_id": 41},
                environ=enabled_env(),
                client=client,
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
                state=state,
            )

            self.assertEqual(codex_chat.read_text(encoding="utf-8"), first_content)
            self.assertEqual(len(client.messages), 1)

    def test_unauthorized_duplicate_update_does_not_spam(self):
        client = FakeRelayClient()
        state = charlie_telegram_relay.RelayRuntimeState.empty()
        update = {
            "update_id": 50,
            "callback_query": {
                "id": "bad-owner",
                "data": "charlie_next:1",
                "from": {"id": 999},
                "message": {"chat": {"id": 999}},
            },
        }

        first = charlie_telegram_relay.handle_relay_update(update, environ=enabled_env(), client=client, state=state)
        second = charlie_telegram_relay.handle_relay_update(update, environ=enabled_env(), client=client, state=state)

        self.assertFalse(first.ok)
        self.assertEqual(second.action, "duplicate_skipped")
        self.assertEqual(len(client.answers), 1)
        self.assertEqual(client.messages, [])

    def test_instance_lock_blocks_second_relay_and_releases_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "relay.lock"
            first = charlie_telegram_relay.RelayInstanceLock(lock_path)
            second = charlie_telegram_relay.RelayInstanceLock(lock_path)

            acquired = first.acquire()
            blocked = second.acquire()
            first.release()

            self.assertTrue(acquired.ok)
            self.assertFalse(blocked.ok)
            self.assertEqual(blocked.action, "lock_active")
            self.assertFalse(lock_path.exists())

    def test_load_local_env_uses_dotenv_without_overriding_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = Path(tmp) / ".env"
            env_path.write_text("DATABASE_URL=postgresql://example\n", encoding="utf-8")
            calls = []

            def fake_load_dotenv(path, override=False):
                calls.append((path, override))
                return True

            loaded = charlie_telegram_relay.load_local_env(env_path, load_dotenv_func=fake_load_dotenv)

            self.assertTrue(loaded)
            self.assertEqual(calls, [(env_path, False)])


if __name__ == "__main__":
    unittest.main()
