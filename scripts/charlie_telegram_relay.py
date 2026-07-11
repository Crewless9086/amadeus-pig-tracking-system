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
import json
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from scripts import build_relay_notify, build_relay_telegram_buttons, codex_next_steps


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


def status_text(config: RelayConfig) -> str:
    relay_state = "enabled" if config.enabled else "disabled"
    return "\n".join(
        [
            "CHARLIE relay status",
            f"Relay: {relay_state}",
            f"Allowed owners configured: {len(config.allowed_user_ids)}",
            "Actions: /next prepares CODEX_CHAT only.",
            "No Codex run, shell command, model API, scheduler, or auto-merge is enabled.",
        ]
    )


def handle_relay_update(
    update: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
    next_steps_path: Path = codex_next_steps.DEFAULT_NEXT_STEPS,
    codex_chat_path: Path = codex_next_steps.DEFAULT_CODEX_CHAT,
) -> RelayResult:
    config = load_config(environ)
    validation = validate_config(config)
    if not validation.ok or validation.action == "disabled":
        return validation

    telegram = client or TelegramRelayClient(config.token)
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

    if command == "/start":
        telegram.send_message(
            chat_id,
            "CHARLIE relay is online. Use /next to choose a mission, or /status to inspect relay safety.",
        )
        return RelayResult(ok=True, action="start_sent")
    if command == "/status":
        telegram.send_message(chat_id, status_text(config))
        return RelayResult(ok=True, action="status_sent")
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

    telegram.send_message(chat_id, "Unknown CHARLIE command. Use /next or /status.")
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
) -> RelayResult:
    config = load_config(environ)
    validation = validate_config(config)
    if not validation.ok or validation.action == "disabled":
        return validation
    telegram = client or (DryRunTelegramClient() if dry_run else TelegramRelayClient(config.token))

    offset: int | None = None
    while True:
        updates = telegram.get_updates(offset=offset, timeout=poll_timeout)
        for update in updates:
            if "update_id" in update:
                offset = int(update["update_id"]) + 1
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
            )
        if once:
            return RelayResult(ok=True, action="poll_once_complete")
        time.sleep(1)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local CHARLIE Telegram relay smoke runner.")
    parser.add_argument("--update-json", type=Path, help="Handle one update JSON file instead of polling.")
    parser.add_argument("--next-steps", type=Path, default=codex_next_steps.DEFAULT_NEXT_STEPS)
    parser.add_argument("--codex-chat", type=Path, default=codex_next_steps.DEFAULT_CODEX_CHAT)
    parser.add_argument("--once", action="store_true", help="Poll once and exit.")
    parser.add_argument("--dry-run", action="store_true", help="Do not send real Telegram messages while polling.")
    parser.add_argument("--json", action="store_true", help="Print result as JSON.")
    args = parser.parse_args(argv)

    config = load_config()
    validation = validate_config(config)
    if not validation.ok or validation.action == "disabled":
        payload = validation.as_dict()
        print(json.dumps(payload, indent=2) if args.json else build_relay_notify.redact_secrets(str(payload)))
        return 0 if validation.ok else 2

    if args.update_json:
        update = json.loads(args.update_json.read_text(encoding="utf-8"))
        client = DryRunTelegramClient() if args.dry_run else None
        result = handle_relay_update(
            update,
            client=client,
            next_steps_path=args.next_steps,
            codex_chat_path=args.codex_chat,
        )
    else:
        result = poll_loop(
            next_steps_path=args.next_steps,
            codex_chat_path=args.codex_chat,
            once=args.once,
            dry_run=args.dry_run,
        )

    payload = result.as_dict()
    print(json.dumps(payload, indent=2) if args.json else build_relay_notify.redact_secrets(str(payload)))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

