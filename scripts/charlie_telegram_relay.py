"""Local CHARLIE Telegram relay smoke runner.

Loop 6 local runner for @CharlieCoreBot:
- supports /start, /status, /next, and Loop 5 button callbacks;
- only allows configured owner user IDs;
- can poll Telegram updates when explicitly enabled;
- can run dry-run/update-file checks without sending real Telegram messages.

It does not run Codex, execute shell commands, call model APIs, start a
scheduler, merge PRs, or write production data.
"""

from __future__ import annotations

import argparse
import atexit
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from scripts import build_relay_notify, build_relay_telegram_buttons, codex_next_steps

DEFAULT_LOCK_FILE = Path(".charlie_runner/telegram_relay.lock")
REPO_ROOT = Path(__file__).resolve().parents[1]
LOCAL_ENV_FILE = REPO_ROOT / ".env"


@dataclass(frozen=True)
class RelayConfig:
    enabled: bool
    token: str
    allowed_user_ids: set[str]


@dataclass(frozen=True)
class RelayResult:
    ok: bool
    action: str
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "action": self.action, "reason": self.reason}


@dataclass
class RelayRuntimeState:
    processed_update_ids: set[int]
    processed_callback_ids: set[str]
    next_offset: int | None = None
    duplicates_skipped: int = 0

    @classmethod
    def empty(cls) -> "RelayRuntimeState":
        return cls(processed_update_ids=set(), processed_callback_ids=set())


class RelayInstanceLock:
    def __init__(self, path: Path = DEFAULT_LOCK_FILE) -> None:
        self.path = path
        self._fd: int | None = None

    def acquire(self) -> RelayResult:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = f"pid={os.getpid()}\nstarted_at={int(time.time())}\n"
            os.write(self._fd, payload.encode("utf-8"))
            atexit.register(self.release)
            return RelayResult(ok=True, action="lock_acquired")
        except FileExistsError:
            return RelayResult(
                ok=False,
                action="lock_active",
                reason=f"Another relay appears active via {self.path}. Stop it or remove stale lock after confirming no relay is running.",
            )

    def release(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass


class TelegramRelayClient(build_relay_telegram_buttons.TelegramButtonClient):
    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": str(timeout)}
        if offset is not None:
            payload["offset"] = str(offset)
        data = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/getUpdates",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout + 10) as response:
            body = response.read().decode("utf-8")
        parsed = json.loads(body)
        if not parsed.get("ok"):
            raise RuntimeError("Telegram getUpdates returned not ok")
        return list(parsed.get("result") or [])


class DryRunTelegramClient:
    def __init__(self) -> None:
        self.messages: list[dict[str, Any]] = []
        self.answers: list[dict[str, Any]] = []

    def send_message(self, chat_id: str | int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        self.messages.append(
            {
                "chat_id": str(chat_id),
                "text": build_relay_notify.redact_secrets(text),
                "reply_markup": reply_markup,
            }
        )

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        self.answers.append({"id": callback_query_id, "text": build_relay_notify.redact_secrets(text)})

    def get_updates(self, offset: int | None = None, timeout: int = 30) -> list[dict[str, Any]]:
        return []


def load_local_env(path: Path = LOCAL_ENV_FILE, load_dotenv_func: Any | None = None) -> bool:
    """Load local relay env without overriding explicit shell variables."""
    if not path.exists():
        return False
    if load_dotenv_func is None:
        try:
            from dotenv import load_dotenv as load_dotenv_func
        except Exception:
            return False
    return bool(load_dotenv_func(path, override=False))


def load_config(environ: Mapping[str, str] | None = None) -> RelayConfig:
    env = dict(os.environ if environ is None else environ)
    enabled = build_relay_notify._truthy(env.get(build_relay_notify.ENABLED_ENV))  # type: ignore[attr-defined]
    token = str(env.get(build_relay_notify.TOKEN_ENV) or "").strip()
    allowed = set(build_relay_notify._split_chat_ids(env.get(build_relay_notify.USERS_ENV)))  # type: ignore[attr-defined]
    return RelayConfig(enabled=enabled, token=token, allowed_user_ids=allowed)


def validate_config(config: RelayConfig) -> RelayResult:
    if not config.enabled:
        return RelayResult(ok=True, action="disabled", reason="relay_disabled")
    if not config.token or not config.allowed_user_ids:
        return RelayResult(
            ok=False,
            action="config_failed",
            reason=f"{build_relay_notify.TOKEN_ENV} and {build_relay_notify.USERS_ENV} are required",
        )
    return RelayResult(ok=True, action="config_ok")


def _user_id_from_update(update: Mapping[str, Any]) -> object:
    if "callback_query" in update:
        return (((update.get("callback_query") or {}).get("from") or {}) or {}).get("id")
    return (((update.get("message") or {}).get("from") or {}) or {}).get("id")


def _chat_id_from_update(update: Mapping[str, Any]) -> object:
    if "callback_query" in update:
        message = ((update.get("callback_query") or {}).get("message") or {}) or {}
        return ((message.get("chat") or {}) or {}).get("id")
    return (((update.get("message") or {}).get("chat") or {}) or {}).get("id")


def _message_text(update: Mapping[str, Any]) -> str:
    return str(((update.get("message") or {}).get("text") or "")).strip()


def _is_authorized(update: Mapping[str, Any], config: RelayConfig) -> bool:
    return str(_user_id_from_update(update)) in config.allowed_user_ids


def _callback_id_from_update(update: Mapping[str, Any]) -> str:
    if "callback_query" not in update:
        return ""
    return str(((update.get("callback_query") or {}).get("id") or ""))


def _update_id_from_update(update: Mapping[str, Any]) -> int | None:
    if "update_id" not in update:
        return None
    try:
        return int(update["update_id"])
    except (TypeError, ValueError):
        return None


def _mark_or_skip_duplicate(update: Mapping[str, Any], state: RelayRuntimeState | None) -> RelayResult | None:
    if state is None:
        return None
    update_id = _update_id_from_update(update)
    callback_id = _callback_id_from_update(update)
    if update_id is not None and update_id in state.processed_update_ids:
        state.duplicates_skipped += 1
        print(f"CHARLIE relay duplicate update skipped: update_id={update_id}", file=sys.stderr)
        return RelayResult(ok=True, action="duplicate_skipped", reason="duplicate_update_id")
    if callback_id and callback_id in state.processed_callback_ids:
        state.duplicates_skipped += 1
        print("CHARLIE relay duplicate callback skipped", file=sys.stderr)
        return RelayResult(ok=True, action="duplicate_skipped", reason="duplicate_callback_id")
    if update_id is not None:
        state.processed_update_ids.add(update_id)
        state.next_offset = max(state.next_offset or 0, update_id + 1)
    if callback_id:
        state.processed_callback_ids.add(callback_id)
    return None


def status_text(config: RelayConfig, runner: Mapping[str, Any] | None = None, counts: Mapping[str, int] | None = None) -> str:
    relay_state = "enabled" if config.enabled else "disabled"
    lines = [
            "CHARLIE relay status",
            f"Relay: {relay_state}",
            f"Allowed owners configured: {len(config.allowed_user_ids)}",
            "Actions: /next reads live Supabase CHARLIE missions first.",
            "No Codex run, shell command, model API, scheduler, or auto-merge is enabled.",
        ]
    if runner:
        lines.extend([
            f"Runner: {runner.get('status', 'unknown')}",
            f"Heartbeat age: {runner.get('age_seconds') if runner.get('age_seconds') is not None else 'unknown'}s",
            f"Active mission: {runner.get('last_mission_id') or 'none'}",
            f"Current agent: {runner.get('current_agent') or 'none'}",
        ])
    if counts:
        lines.append("Queue: " + ", ".join(f"{key}={value}" for key, value in sorted(counts.items())))
    return "\n".join(lines)


def _queue_snapshot(mission_loader: Any) -> tuple[dict[str, int], list[dict[str, Any]]]:
    payload, status_code = mission_loader(status="owner_queue", limit=100, compact=True)
    missions = list((payload or {}).get("missions") or []) if status_code < 400 else []
    counts: dict[str, int] = {}
    for mission in missions:
        status = str((mission or {}).get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return counts, missions


def handle_relay_update(
    update: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
    next_steps_path: Path = codex_next_steps.DEFAULT_NEXT_STEPS,
    codex_chat_path: Path = codex_next_steps.DEFAULT_CODEX_CHAT,
    state: RelayRuntimeState | None = None,
    mission_loader: Any | None = None,
    runner_status_loader: Any | None = None,
) -> RelayResult:
    config = load_config(environ)
    validation = validate_config(config)
    if not validation.ok or validation.action == "disabled":
        return validation

    telegram = client or TelegramRelayClient(config.token)
    duplicate = _mark_or_skip_duplicate(update, state)
    if duplicate is not None:
        return duplicate

    if not _is_authorized(update, config):
        if "callback_query" in update:
            callback_id = str(((update.get("callback_query") or {}).get("id") or ""))
            if callback_id:
                telegram.answer_callback_query(callback_id, "Not authorized.")
        return RelayResult(ok=False, action="ignored", reason="unauthorized_user")

    if "callback_query" in update:
        result = build_relay_telegram_buttons.handle_update(
            update,
            environ={
                build_relay_notify.ENABLED_ENV: "1",
                build_relay_notify.TOKEN_ENV: config.token,
                build_relay_notify.USERS_ENV: ",".join(sorted(config.allowed_user_ids)),
            },
            client=telegram,
            next_steps_path=next_steps_path,
            codex_chat_path=codex_chat_path,
        )
        return RelayResult(ok=result.ok, action=result.action, reason=result.reason)

    text = _message_text(update)
    chat_id = _chat_id_from_update(update)
    command = text.lower().split(maxsplit=1)[0] if text else ""
    if mission_loader is None or runner_status_loader is None:
        from modules.charlie import mission_store, runner_control

        mission_loader = mission_loader or mission_store.list_missions
        runner_status_loader = runner_status_loader or runner_control.runner_status

    if command == "/start":
        telegram.send_message(
            chat_id,
            "CHARLIE relay is online. Use /next to choose a mission, or /status to inspect relay safety.",
        )
        return RelayResult(ok=True, action="start_sent")
    if command == "/status":
        counts, _missions = _queue_snapshot(mission_loader)
        runner = runner_status_loader(include_git=False, include_ledger=False)
        telegram.send_message(chat_id, status_text(config, runner, counts))
        return RelayResult(ok=True, action="status_sent")
    if command in {"/queue", "/blocked"}:
        counts, missions = _queue_snapshot(mission_loader)
        if command == "/blocked":
            missions = [mission for mission in missions if str(mission.get("status") or "") == "blocked"]
        lines = ["CHARLIE QUEUE", ", ".join(f"{key}={value}" for key, value in sorted(counts.items())) or "Queue empty"]
        for mission in missions[:10]:
            lines.append(f"- {mission.get('status')}: {mission.get('title') or mission.get('mission_id')} [{mission.get('mission_id')}]")
        telegram.send_message(chat_id, "\n".join(lines))
        return RelayResult(ok=True, action="queue_sent")
    if command == "/next":
        result = build_relay_telegram_buttons.handle_update(
            update,
            environ={
                build_relay_notify.ENABLED_ENV: "1",
                build_relay_notify.TOKEN_ENV: config.token,
                build_relay_notify.USERS_ENV: ",".join(sorted(config.allowed_user_ids)),
            },
            client=telegram,
            next_steps_path=next_steps_path,
            codex_chat_path=codex_chat_path,
        )
        return RelayResult(ok=result.ok, action=result.action, reason=result.reason)

    telegram.send_message(chat_id, "Unknown CHARLIE command. Use /next, /status, /queue, or /blocked.")
    return RelayResult(ok=True, action="unknown_command")


def poll_loop(
    *,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
    next_steps_path: Path = codex_next_steps.DEFAULT_NEXT_STEPS,
    codex_chat_path: Path = codex_next_steps.DEFAULT_CODEX_CHAT,
    once: bool = False,
    dry_run: bool = False,
    poll_timeout: int = 30,
    state: RelayRuntimeState | None = None,
) -> RelayResult:
    config = load_config(environ)
    validation = validate_config(config)
    if not validation.ok or validation.action == "disabled":
        return validation
    telegram = client or (DryRunTelegramClient() if dry_run else TelegramRelayClient(config.token))

    runtime_state = state or RelayRuntimeState.empty()
    while True:
        updates = telegram.get_updates(offset=runtime_state.next_offset, timeout=poll_timeout)
        max_update_id: int | None = None
        for update in updates:
            update_id = _update_id_from_update(update)
            if update_id is not None:
                max_update_id = max(max_update_id or update_id, update_id)
            handle_relay_update(
                update,
                environ={
                    build_relay_notify.ENABLED_ENV: "1",
                    build_relay_notify.TOKEN_ENV: config.token,
                    build_relay_notify.USERS_ENV: ",".join(sorted(config.allowed_user_ids)),
                },
                client=telegram,
                next_steps_path=next_steps_path,
                codex_chat_path=codex_chat_path,
                state=runtime_state,
            )
        if max_update_id is not None:
            runtime_state.next_offset = max(runtime_state.next_offset or 0, max_update_id + 1)
        if once:
            return RelayResult(ok=True, action="poll_once_complete")
        time.sleep(1)


def main(argv: list[str] | None = None) -> int:
    load_local_env()

    parser = argparse.ArgumentParser(description="Run the local CHARLIE Telegram relay smoke runner.")
    parser.add_argument("--update-json", type=Path, help="Handle one update JSON file instead of polling.")
    parser.add_argument("--next-steps", type=Path, default=codex_next_steps.DEFAULT_NEXT_STEPS)
    parser.add_argument("--codex-chat", type=Path, default=codex_next_steps.DEFAULT_CODEX_CHAT)
    parser.add_argument("--once", action="store_true", help="Poll once and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Do not send real Telegram messages while polling.")
    parser.add_argument("--no-lock", action="store_true", help="Skip the single-instance lock guard.")
    parser.add_argument("--lock-file", type=Path, default=DEFAULT_LOCK_FILE)
    parser.add_argument("--json", action="store_true", help="Print result as JSON.")
    args = parser.parse_args(argv)

    config = load_config()
    validation = validate_config(config)
    if not validation.ok or validation.action == "disabled":
        payload = validation.as_dict()
        print(json.dumps(payload, indent=2) if args.json else build_relay_notify.redact_secrets(str(payload)))
        return 0 if validation.ok else 2

    instance_lock: RelayInstanceLock | None = None
    if not args.no_lock:
        instance_lock = RelayInstanceLock(args.lock_file)
        lock_result = instance_lock.acquire()
        if not lock_result.ok:
            payload = lock_result.as_dict()
            print(json.dumps(payload, indent=2) if args.json else build_relay_notify.redact_secrets(str(payload)))
            return 2

    try:
        state = RelayRuntimeState.empty()
        if args.update_json:
            update = json.loads(args.update_json.read_text(encoding="utf-8"))
            client = DryRunTelegramClient() if args.dry_run else None
            result = handle_relay_update(
                update,
                client=client,
                next_steps_path=args.next_steps,
                codex_chat_path=args.codex_chat,
                state=state,
            )
        else:
            result = poll_loop(
                next_steps_path=args.next_steps,
                codex_chat_path=args.codex_chat,
                once=args.once,
                dry_run=args.dry_run,
                state=state,
            )
    except KeyboardInterrupt:
        result = RelayResult(ok=True, action="stopped", reason="keyboard_interrupt")
    finally:
        if instance_lock is not None:
            instance_lock.release()

    payload = result.as_dict()
    print(json.dumps(payload, indent=2) if args.json else build_relay_notify.redact_secrets(str(payload)))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
