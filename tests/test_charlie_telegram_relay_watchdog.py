import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from scripts import charlie_telegram_relay_watchdog as watchdog
from scripts.charlie_telegram_relay import RelayResult


def enabled_config():
    return RelayResult(ok=True, action="config_ok")


class CharlieTelegramRelayWatchdogTests(unittest.TestCase):
    def test_live_lock_is_healthy_and_does_not_start_second_relay(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "relay.lock"
            state = Path(tmp) / "state.json"
            lock.write_text("pid=42\n", encoding="utf-8")
            starts = []
            result = watchdog.watchdog_tick(
                lock_path=lock,
                state_path=state,
                pid_alive=lambda pid: pid == 42,
                popen_factory=lambda *args, **kwargs: starts.append((args, kwargs)),
                config_check=enabled_config,
            )
            self.assertEqual(result["status"], "relay_healthy")
            self.assertEqual(starts, [])
            self.assertTrue(lock.exists())

    @patch("scripts.charlie_telegram_relay_watchdog.load_local_env")
    def test_dead_lock_is_removed_and_one_windowless_relay_starts(self, _load_env):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "relay.lock"
            state = Path(tmp) / "state.json"
            lock.write_text("pid=99\n", encoding="utf-8")
            calls = []
            def fake_popen(command, **kwargs):
                calls.append((command, kwargs))
                return SimpleNamespace(pid=123)
            with patch.object(watchdog, "STDOUT_PATH", Path(tmp) / "out.log"), patch.object(watchdog, "STDERR_PATH", Path(tmp) / "err.log"), patch.object(watchdog, "_windowless_process_kwargs", return_value={"creationflags": 0x08000000}):
                result = watchdog.watchdog_tick(lock_path=lock, state_path=state, pid_alive=lambda _pid: False, popen_factory=fake_popen, config_check=enabled_config)
            self.assertEqual(result["status"], "relay_started")
            self.assertTrue(result["stale_lock_removed"])
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][1]["creationflags"], 0x08000000)
            self.assertFalse(lock.exists())

    def test_platform_launch_flags_are_windowless_only_on_windows(self):
        self.assertEqual(watchdog._windowless_process_kwargs("nt")["creationflags"], 0x08000000)
        self.assertTrue(watchdog._windowless_process_kwargs("posix")["start_new_session"])

    def test_recent_incomplete_lock_is_not_removed_during_startup_race(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock = Path(tmp) / "relay.lock"
            state = Path(tmp) / "state.json"
            lock.write_text("", encoding="utf-8")
            starts = []
            result = watchdog.watchdog_tick(
                lock_path=lock,
                state_path=state,
                pid_alive=lambda _pid: False,
                popen_factory=lambda *args, **kwargs: starts.append((args, kwargs)),
                config_check=enabled_config,
            )
            self.assertEqual(result["status"], "relay_healthy")
            self.assertEqual(starts, [])
            self.assertTrue(lock.exists())

    def test_disabled_configuration_does_not_start_relay(self):
        with tempfile.TemporaryDirectory() as tmp:
            starts = []
            result = watchdog.watchdog_tick(
                lock_path=Path(tmp) / "relay.lock",
                state_path=Path(tmp) / "state.json",
                popen_factory=lambda *args, **kwargs: starts.append((args, kwargs)),
                config_check=lambda: RelayResult(ok=True, action="disabled", reason="relay_disabled"),
            )
            self.assertEqual(result["status"], "relay_disabled")
            self.assertFalse(result["started"])
            self.assertEqual(starts, [])

    def test_webhook_transport_does_not_start_polling_relay(self):
        with tempfile.TemporaryDirectory() as tmp:
            starts = []
            result = watchdog.watchdog_tick(
                lock_path=Path(tmp) / "relay.lock",
                state_path=Path(tmp) / "state.json",
                popen_factory=lambda *args, **kwargs: starts.append((args, kwargs)),
                config_check=lambda: RelayResult(ok=True, action="webhook_managed", reason="local_polling_disabled"),
            )
            self.assertEqual(result["status"], "relay_webhook_managed")
            self.assertEqual(starts, [])

    def test_invalid_configuration_does_not_restart_forever(self):
        with tempfile.TemporaryDirectory() as tmp:
            starts = []
            result = watchdog.watchdog_tick(
                lock_path=Path(tmp) / "relay.lock",
                state_path=Path(tmp) / "state.json",
                popen_factory=lambda *args, **kwargs: starts.append((args, kwargs)),
                config_check=lambda: RelayResult(ok=False, action="config_failed", reason="required env missing"),
            )
            self.assertEqual(result["status"], "relay_config_failed")
            self.assertFalse(result["started"])
            self.assertEqual(starts, [])


if __name__ == "__main__":
    unittest.main()
