"""Telegram button flow for the CHARLIE Mission Loop.

This module handles the Loop 5 owner flow:
- /next reads live Supabase CHARLIE missions first, with NEXT_STEPS.md as fallback.
- the current callback writes a manual CODEX_CHAT handoff as a transitional bridge.

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

from scripts import build_relay_notify, charlie_mission_telegram, codex_next_steps


CALLBACK_PREFIX = "charlie_next:"
LIVE_SOURCE = "supabase_charlie_missions"
FALLBACK_SOURCE = "next_steps_fallback"
STATUS_PRIORITY = {
    "blocked": "P0",
    "pr_ready": "P0",
    "release_approved": "P0",
    "release_in_progress": "P0",
    "in_progress": "P0",
    "approved": "P1",
    "new": "P1",
    "paused": "P2",
}


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


@dataclass(frozen=True)
class OptionSource:
    options: list[codex_next_steps.MissionOption]
    source: str
    status: str = "ok"


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


def _keyboard_for_options(options: list[codex_next_steps.MissionOption], source: str = FALLBACK_SOURCE) -> dict[str, Any]:
    rows = []
    for option in options:
        rows.append(
            [
                {
                    "text": f"{option.index}. {option.priority} - {option.title[:52]}",
                    "callback_data": (
                        charlie_mission_telegram.mission_callback(option.source_line, "open")
                        if source == LIVE_SOURCE and option.source_line
                        else f"{CALLBACK_PREFIX}{option.index}"
                    ),
                }
            ]
        )
    return {"inline_keyboard": rows}


def _options_message(options: list[codex_next_steps.MissionOption], source: str = FALLBACK_SOURCE) -> str:
    lines = ["CHARLIE NEXT MISSIONS", "Select a live mission to open its CHARLIE CORE action card."]
    if source == LIVE_SOURCE:
        lines.append("Source: live Supabase CHARLIE mission queue")
    else:
        lines.append("Source: fallback docs menu (Supabase unavailable or empty)")
    for option in options:
        lines.append(f"{option.index}. [{option.priority}] {option.title}")
    lines.append("")
    lines.append("No Codex run starts from this button. Supabase mission state remains authoritative.")
    return build_relay_notify.redact_secrets("\n".join(lines))


def _client_from_env(environ: Mapping[str, str]) -> TelegramButtonClient:
    token = str(environ.get(build_relay_notify.TOKEN_ENV, "")).strip()
    if not token:
        raise ValueError(f"{build_relay_notify.TOKEN_ENV} is required")
    return TelegramButtonClient(token)


def _mission_title(mission: Mapping[str, Any]) -> str:
    title = str(mission.get("title") or "").strip()
    raw_text = str(mission.get("raw_text") or "").strip()
    mission_id = str(mission.get("mission_id") or "").strip()
    status = str(mission.get("status") or "").strip().lower()
    headline = title or raw_text or mission_id or "Untitled mission"
    if len(headline) > 130:
        headline = headline[:127].rstrip() + "..."
    short_id = mission_id[-12:] if len(mission_id) > 12 else mission_id
    prefix = f"{status.upper()}: " if status else ""
    suffix = f" ({short_id})" if short_id else ""
    return f"{prefix}{headline}{suffix}"


def _missions_to_options(missions: list[Mapping[str, Any]], limit: int = 5) -> list[codex_next_steps.MissionOption]:
    options: list[codex_next_steps.MissionOption] = []
    for mission in missions[:limit]:
        status = str(mission.get("status") or "").strip().lower()
        priority = STATUS_PRIORITY.get(status, "P2")
        title = _mission_title(mission)
        options.append(codex_next_steps.MissionOption(len(options) + 1, priority, title, f"{mission.get('mission_id', '')}"))
    return options


def load_next_options(
    *,
    next_steps_path: Path = codex_next_steps.DEFAULT_NEXT_STEPS,
    limit: int = 5,
    mission_loader: Any | None = None,
) -> OptionSource:
    loader = mission_loader
    if loader is None:
        try:
            from modules.charlie import mission_store

            loader = mission_store.list_missions
        except Exception:
            loader = None

    if loader is not None:
        try:
            payload, status_code = loader(status="owner_queue", limit=limit, compact=True)
            missions = list((payload or {}).get("missions") or [])
            if status_code == 200 and missions:
                return OptionSource(_missions_to_options(missions, limit=limit), LIVE_SOURCE, "ok")
        except Exception:
            pass

    return OptionSource(codex_next_steps.read_options(next_steps_path, limit=limit), FALLBACK_SOURCE, "fallback")


def write_manual_codex_handoff(
    option: codex_next_steps.MissionOption,
    *,
    codex_chat_path: Path = codex_next_steps.DEFAULT_CODEX_CHAT,
    owner_intent: str = "",
    archive: bool = True,
) -> Path | None:
    codex_chat_path.parent.mkdir(parents=True, exist_ok=True)
    archive_path = codex_next_steps.archive_existing(codex_chat_path) if archive else None
    codex_chat_path.write_text(
        codex_next_steps.render_code_chat(option, owner_intent=owner_intent),
        encoding="utf-8",
    )
    return archive_path


def handle_update(
    update: Mapping[str, Any],
    *,
    environ: Mapping[str, str] | None = None,
    client: Any | None = None,
    next_steps_path: Path = codex_next_steps.DEFAULT_NEXT_STEPS,
    codex_chat_path: Path = codex_next_steps.DEFAULT_CODEX_CHAT,
    option_source_loader: Any | None = None,
    mission_list_loader: Any | None = None,
    mission_get_loader: Any | None = None,
    mission_status_updater: Any | None = None,
    mission_review_updater: Any | None = None,
    runner_status_loader: Any | None = None,
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
        source = load_next_options(next_steps_path=next_steps_path, limit=5, mission_loader=option_source_loader)
        telegram.send_message(chat_id, _options_message(source.options, source.source), reply_markup=_keyboard_for_options(source.options, source.source))
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
        if data.startswith(charlie_mission_telegram.CALLBACK_PREFIX):
            if callback_id:
                try:
                    telegram.answer_callback_query(callback_id, "Processing CHARLIE action...")
                except Exception:
                    # Telegram callback acknowledgements expire quickly. The mission
                    # action and owner-visible result must still continue safely.
                    pass
            try:
                from modules.charlie import mission_store, runner_control

                result, mission = charlie_mission_telegram.handle_callback(
                    data,
                    list_loader=mission_list_loader or mission_store.list_missions,
                    get_loader=mission_get_loader or mission_store.get_mission,
                    status_updater=mission_status_updater or mission_store.update_mission_status,
                    review_updater=mission_review_updater or mission_store.record_mission_review_decision,
                )
                runner = (runner_status_loader or runner_control.runner_status)(include_git=False, include_ledger=False)
            except Exception as exc:
                telegram.send_message(chat_id, "CHARLIE mission action failed safely. No unconfirmed action was retried.")
                return ButtonFlowResult(False, "mission_action_failed", reason=exc.__class__.__name__)
            if mission:
                telegram.send_message(
                    chat_id,
                    charlie_mission_telegram.mission_card_text(mission, runner),
                    reply_markup=charlie_mission_telegram.mission_keyboard(mission),
                )
            elif not result.ok:
                telegram.send_message(chat_id, f"CHARLIE mission action refused: {result.reason or 'current state does not allow it'}." )
            return ButtonFlowResult(result.ok, result.action, result.reason, selected_title=result.mission_id)

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
            source = load_next_options(next_steps_path=next_steps_path, limit=5, mission_loader=option_source_loader)
            if option_number < 1 or option_number > len(source.options):
                raise ValueError(f"Invalid option {option_number}; expected 1-{len(source.options)}")
            option = source.options[option_number - 1]
            archive_path = write_manual_codex_handoff(
                option,
                codex_chat_path=codex_chat_path,
                owner_intent=f"Manual transitional CODEX_CHAT handoff selected through CHARLIE Telegram /next from {source.source}.",
            )
        except (FileNotFoundError, ValueError) as exc:
            if callback_id:
                telegram.answer_callback_query(callback_id, "Mission selection failed.")
            return ButtonFlowResult(ok=False, action="selection_failed", reason=str(exc))

        if callback_id:
            telegram.answer_callback_query(callback_id, "Manual handoff written.")
        archive_line = f"\nArchived previous CODEX_CHAT: {archive_path}" if archive_path else ""
        telegram.send_message(
            chat_id,
            build_relay_notify.redact_secrets(
                f"CHARLIE mission selected\nOption: {option.index}\nPriority: {option.priority}\nMission: {option.title}"
                f"\nManual CODEX_CHAT handoff updated: {codex_chat_path}{archive_line}"
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
