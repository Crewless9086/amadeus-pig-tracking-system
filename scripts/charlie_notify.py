import argparse
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from modules.charlie.build_relay import send_charlie_telegram_message


NOTIFY_ATTEMPTS = 3


def main():
    load_dotenv(REPO_ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description="Send an owner-only CHARLIE Build Relay notification.")
    parser.add_argument("--title", default="CHARLIE update")
    parser.add_argument("--message", required=True)
    parser.add_argument("--level", default="info", choices=["info", "success", "warning", "blocked", "done"])
    parser.add_argument("--mission-id", default="", help="Attach a mission-specific Status button.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    text = _format_message(args.level, args.title, args.message)
    reply_markup = _mission_status_keyboard(args.mission_id)
    chat_ids = [
        item.strip()
        for item in str(os.getenv("CHARLIE_BUILD_RELAY_ALLOWED_USER_IDS", "") or "").split(",")
        if item.strip()
    ]
    if not chat_ids:
        print({"success": False, "status": "allowed_user_ids_required"})
        return 2
    if args.dry_run:
        print({"success": True, "status": "dry_run", "recipient_count": len(chat_ids), "text": text, "reply_markup": reply_markup})
        return 0

    deliveries = []
    success = True
    for chat_id in chat_ids:
        result, status_code, attempts = _send_with_retry(chat_id, text, reply_markup)
        deliveries.append({
            "chat_id_set": bool(chat_id),
            "status_code": status_code,
            "success": result.get("success") is True,
            "status": result.get("status"),
            "attempts": attempts,
        })
        success = success and result.get("success") is True
    print({"success": success, "status": "sent" if success else "partial_or_failed", "deliveries": deliveries})
    return 0 if success else 1


def _send_with_retry(chat_id, text, reply_markup=None, attempts=NOTIFY_ATTEMPTS, sleep_fn=time.sleep):
    last_result = {"success": False, "status": "not_attempted"}
    last_status_code = 0
    parsed_attempts = max(int(attempts or 1), 1)
    for attempt in range(1, parsed_attempts + 1):
        last_result, last_status_code = send_charlie_telegram_message(chat_id=chat_id, text=text, reply_markup=reply_markup)
        if last_result.get("success") is True:
            return last_result, last_status_code, attempt
        if attempt < parsed_attempts:
            sleep_fn(min(2 ** (attempt - 1), 8))
    return last_result, last_status_code, parsed_attempts


def _format_message(level, title, message):
    label = {
        "info": "INFO",
        "success": "SUCCESS",
        "warning": "WARNING",
        "blocked": "BLOCKED",
        "done": "DONE",
    }.get(level, "INFO")
    return f"CHARLIE {label}: {title}\n\n{str(message or '').strip()}"


def _mission_status_keyboard(mission_id):
    mission_id = str(mission_id or "").strip()[:120]
    if not mission_id:
        return None
    return {"inline_keyboard": [[{"text": "Status", "callback_data": f"status:{mission_id}"}]]}


if __name__ == "__main__":
    raise SystemExit(main())
