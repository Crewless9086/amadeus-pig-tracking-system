"""Telegram button flow for the CHARLIE Mission Loop.

This module handles the Loop 5 owner flow:
- /next reads NEXT_STEPS.md and sends the top five mission options as buttons.
- a button callback writes the selected mission into CODEX_CHAT.md and confirms.

It does not run Codex, call model APIs, schedule work, merge PRs, or perform
production data writes.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from scripts import build_relay_notify, codex_next_steps


CALLBACK_PREFIX = "charlie_next:"


@dataclass(frozen=True)
class ButtonFlowResult:
    ok: bool
    action: str
    reason: str = ""
    selected_option: int | None = None
    selected_title: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "action": self.action,
            "reason": self.reason,
            "selected_option": self.selected_option,
            "selected_title": self.selected_title,
        }


class TelegramButtonClient:
    def __init__(self, token: str) -> None:
        self.token = token

    def _request(self, method: str, payload: Mapping[str, Any]) -> None:
        data = urllib.parse.urlencode(payload).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{self.token}/{method}",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 400:
                raise RuntimeError(f"Telegram {method} failed with HTTP {response.status}")

    def send_message(self, chat_id: str | int, text: str, reply_markup: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"chat_id": str(chat_id), "text": build_relay_notify.redact_secrets(text)}
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        self._request("sendMessage", payload)

    def answer_callback_query(self, callback_query_id: str, text: str = "") -> None:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = build_relay_notify.redact_secrets(text)
        self._request("answerCallbackQuery", payload)


def _allowed_user_ids(environ: Mapping[str, str]) -> set[str]:
    return set(build_relay_notify._split_chat_ids(environ.get(build_relay_notify.USERS_ENV)))  # type: ignore[attr-defined]


def _is_enabled(environ: Mapping[str, str]) -> bool:
    return build_relay_notify._truthy(environ.get(build_relay_notify.ENABLED_ENV))  # type: ignore[attr-defined]


def _authorized(user_id: object, environ: Mapping[str, str]) -> bool:
    allowed = _allowed_user_ids(environ)
    return bool(allowed and str(user_id) in allowed)


def _keyboard_for_options(options: list[codex_next_steps.MissionOption]) -> dict[str, Any]:
    rows = []
    for option in options:
        rows.append(
            [
                {
                    "text": f"{option.index}. {option.priority} - {option.title[:52]}",
                    "callback_data": f"{CALLBACK_PREFIX}{option.index}",
                }
            ]
        )
    return {"inline_keyboard": rows}


def _options_message(options: list[codex_next_steps.MissionOption]) -> str:
    lines = ["CHARLIE NEXT MISSIONS", "Select one mission to write into CODEX_CHAT."]
    for option in options:
        lines.append(f"{option.index}. [{option.priority}] {option.title}")
    lines.append("")
    lines.append("No Codex run starts from this button. It only prepares the active mission file.")
    return build_relay_notify.redact_secrets("\n".join(lines))


def _client_from_env(environ: Mapping[str, str]) -> TelegramButtonClient:
    token = str(environ.get(build_relay_notify.TOKEN_ENV, "")).strip()
    if not token:
        raise ValueError(f"{build_relay_notify.TOKEN_ENV} is required")
    return TelegramButtonClient(token)


def handle_update(
    update: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
    next_steps_path: Path = codex_next_steps.DEFAULT_NEXT_STEPS,
    codex_chat_path: Path = codex_next_steps.DEFAULT_CODEX_CHAT,
) -> ButtonFlowResult:
    env = dict(os.environ if environ is None else environ)
    if not _is_enabled(env):
        return ButtonFlowResult(ok=True, action="disabled", reason="relay_disabled")

    telegram = client or _client_from_env(env)

    if "message" in update:
        message = dict(update.get("message") or {})
        text = str(message.get("text") or "").strip()
        user_id = ((message.get("from") or {}) or {}).get("id")
        chat_id = ((message.get("chat") or {}) or {}).get("id")
        if not _authorized(user_id, env):
            return ButtonFlowResult(ok=False, action="ignored", reason="unauthorized_user")
        if text.lower().split(maxsplit=1)[0] != "/next":
            return ButtonFlowResult(ok=True, action="ignored", reason="not_next_command")
        options = codex_next_steps.read_options(next_steps_path, limit=5)
        telegram.send_message(chat_id, _options_message(options), reply_markup=_keyboard_for_options(options))
        return ButtonFlowResult(ok=True, action="sent_next_menu")

    if "callback_query" in update:
        callback = dict(update.get("callback_query") or {})
        callback_id = str(callback.get("id") or "")
        data = str(callback.get("data") or "")
        user_id = ((callback.get("from") or {}) or {}).get("id")
        message = dict(callback.get("message") or {})
        chat_id = ((message.get("chat") or {}) or {}).get("id")

        if not _authorized(user_id, env):
            if callback_id:
                telegram.answer_callback_query(callback_id, "Not authorized.")
            return ButtonFlowResult(ok=False, action="ignored", reason="unauthorized_user")
        if not data.startswith(CALLBACK_PREFIX):
            if callback_id:
                telegram.answer_callback_query(callback_id, "Unknown CHARLIE action.")
            return ButtonFlowResult(ok=False, action="ignored", reason="unknown_callback")
        try:
            option_number = int(data[len(CALLBACK_PREFIX) :])
        except ValueError:
            if callback_id:
                telegram.answer_callback_query(callback_id, "Invalid mission option.")
            return ButtonFlowResult(ok=False, action="invalid_callback", reason="invalid_option")

        try:
            option, archive_path = codex_next_steps.write_selected_mission(
                option_number,
                next_steps_path=next_steps_path,
                codex_chat_path=codex_chat_path,
                owner_intent="Selected through CHARLIE Telegram /next.",
            )
        except (FileNotFoundError, ValueError) as exc:
            if callback_id:
                telegram.answer_callback_query(callback_id, "Mission selection failed.")
            return ButtonFlowResult(ok=False, action="selection_failed", reason=str(exc))

        if callback_id:
            telegram.answer_callback_query(callback_id, "Mission written to CODEX_CHAT.")
        archive_line = f"\nArchived previous CODEX_CHAT: {archive_path}" if archive_path else ""
        telegram.send_message(
            chat_id,
            build_relay_notify.redact_secrets(
                f"CHARLIE mission selected\nOption: {option.index}\nPriority: {option.priority}\nMission: {option.title}"
                f"\nCODEX_CHAT updated: {codex_chat_path}{archive_line}"
            ),
        )
        return ButtonFlowResult(
            ok=True,
            action="selected_mission",
            selected_option=option.index,
            selected_title=option.title,
        )

    return ButtonFlowResult(ok=True, action="ignored", reason="unsupported_update")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Handle a CHARLIE Telegram /next update JSON.")
    parser.add_argument("--update-json", type=Path, required=True)
    parser.add_argument("--next-steps", type=Path, default=codex_next_steps.DEFAULT_NEXT_STEPS)
    parser.add_argument("--codex-chat", type=Path, default=codex_next_steps.DEFAULT_CODEX_CHAT)
    args = parser.parse_args(argv)

    result = handle_update(
        json.loads(args.update_json.read_text(encoding="utf-8")),
        next_steps_path=args.next_steps,
        codex_chat_path=args.codex_chat,
    )
    print(json.dumps(result.as_dict(), indent=2))
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
