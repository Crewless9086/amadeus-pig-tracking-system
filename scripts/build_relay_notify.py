"""Safe CHARLIE Build Relay notification stub.

This module formats mission-loop notifications and optionally sends them to
Telegram only when the relay is explicitly enabled and configured.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping

from modules.charlie.environment import alias_environment


STATUSES = {
    "RUNNING",
    "DONE",
    "PR_READY",
    "DEPLOYED_NEEDS_TEST",
    "FAILED_TESTS",
    "HARD_STOP",
    "NEEDS_OWNER_APPROVAL",
    "BUDGET_STOP",
}

TOKEN_ENV = "CORE_RELAY_BOT_TOKEN"
USERS_ENV = "CORE_RELAY_ALLOWED_USER_IDS"
ENABLED_ENV = "CORE_RELAY_ENABLED"


@dataclass(frozen=True)
class NotifyResult:
    ok: bool
    status: str
    sent: int = 0
    reason: str = ""
    message: str = ""

    def as_dict(self) -> dict:
        return {
            "ok": self.ok,
            "status": self.status,
            "sent": self.sent,
            "reason": self.reason,
            "message": self.message,
        }


def _truthy(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _split_chat_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in re.split(r"[,\s]+", value) if part.strip()]


def redact_secrets(text: str) -> str:
    """Redact common token/API-key shapes from a notification body."""

    redacted = str(text or "")
    patterns = [
        r"\b\d{6,}:[A-Za-z0-9_-]{20,}\b",  # Telegram bot token
        r"\bsk-[A-Za-z0-9_-]{12,}\b",
        r"\b(?:api[_-]?key|token|secret|password)\s*[:=]\s*[^\s,;]+",
        r"\b[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{20,}\b",
    ]
    for pattern in patterns:
        redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)
    return redacted


def build_message(
    status: str,
    *,
    mission_id: str = "",
    title: str = "",
    detail: str = "",
    url: str = "",
) -> str:
    normalized = status.strip().upper()
    if normalized not in STATUSES:
        raise ValueError(f"Unsupported notification status: {status}")

    lines = [f"CHARLIE {normalized}"]
    if mission_id:
        lines.append(f"Mission: {mission_id}")
    if title:
        lines.append(f"Title: {title}")
    if detail:
        lines.append(f"Detail: {detail}")
    if url:
        lines.append(f"Link: {url}")
    return redact_secrets("\n".join(lines))


def _telegram_sender(token: str) -> Callable[[str, str], None]:
    def send(chat_id: str, text: str) -> None:
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": text}).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status >= 400:
                raise RuntimeError(f"Telegram send failed with HTTP {response.status}")

    return send


def notify(
    status: str,
    *,
    mission_id: str = "",
    title: str = "",
    detail: str = "",
    url: str = "",
    environ: Mapping[str, str] | None = None,
    sender: Callable[[str, str], None] | None = None,
) -> NotifyResult:
    env = alias_environment(os.environ if environ is None else environ)
    message = build_message(status, mission_id=mission_id, title=title, detail=detail, url=url)

    if not _truthy(env.get(ENABLED_ENV)):
        return NotifyResult(ok=True, status="disabled", sent=0, reason="relay_disabled", message=message)

    token = env.get(TOKEN_ENV, "").strip()
    chat_ids = _split_chat_ids(env.get(USERS_ENV))
    if not token or not chat_ids:
        return NotifyResult(
            ok=False,
            status="missing_env",
            sent=0,
            reason=f"{TOKEN_ENV} and {USERS_ENV} are required when relay is enabled",
            message=message,
        )

    send = sender or _telegram_sender(token)
    sent = 0
    for chat_id in chat_ids:
        send(chat_id, message)
        sent += 1
    return NotifyResult(ok=True, status="sent", sent=sent, message=message)


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Send a safe CHARLIE Build Relay notification.")
    parser.add_argument("status", choices=sorted(STATUSES))
    parser.add_argument("--mission-id", default="")
    parser.add_argument("--title", default="")
    parser.add_argument("--detail", default="")
    parser.add_argument("--url", default="")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    result = notify(
        args.status,
        mission_id=args.mission_id,
        title=args.title,
        detail=args.detail,
        url=args.url,
    )
    if args.json:
        print(json.dumps(result.as_dict(), indent=2))
    else:
        print(result.message)
        print(f"status={result.status} sent={result.sent} ok={result.ok}")
        if result.reason:
            print(f"reason={result.reason}")
    return 0 if result.ok else 2


if __name__ == "__main__":
    raise SystemExit(main())

