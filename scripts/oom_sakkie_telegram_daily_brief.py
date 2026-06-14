import argparse
import json
from pathlib import Path

from dotenv import load_dotenv

from modules.oom_sakkie.telegram_direct import (
    preview_daily_brief_for_allowed_owners,
    send_daily_brief_to_allowed_owners,
)


def main():
    parser = argparse.ArgumentParser(description="Send or preview the Oom Sakkie owner daily Telegram brief.")
    parser.add_argument("--dry-run", action="store_true", help="Build the brief and print readiness without sending Telegram.")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    result, status_code = (
        preview_daily_brief_for_allowed_owners()
        if args.dry_run
        else send_daily_brief_to_allowed_owners()
    )
    print("status:", status_code)
    print("success:", result.get("success"))
    print("daily_brief_status:", result.get("status"))
    print("mode:", result.get("mode"))
    print("delivery_count:", result.get("delivery_count"))
    print("would_send_to_count:", result.get("would_send_to_count"))
    print("sends_telegram:", result.get("sends_telegram"))
    print("can_trigger_outbound_llm:", result.get("can_trigger_outbound_llm"))
    print("writes:", result.get("writes"))
    print("dispatch_enabled:", result.get("dispatch_enabled"))
    if args.dry_run:
        print("telegram_text_preview:")
        print(result.get("telegram_text", ""))
    print("deliveries:", json.dumps([
        {
            "chat_id": item.get("chat_id"),
            "success": item.get("success"),
            "status": item.get("status"),
            "status_code": item.get("status_code"),
        }
        for item in result.get("deliveries", [])
    ]))
    return 0 if status_code == 200 and result.get("success") else 1 if status_code != 503 else 2


if __name__ == "__main__":
    raise SystemExit(main())
