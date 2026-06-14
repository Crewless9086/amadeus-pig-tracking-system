import json
from pathlib import Path

from dotenv import load_dotenv

from modules.oom_sakkie.telegram_direct import send_daily_brief_to_allowed_owners


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    result, status_code = send_daily_brief_to_allowed_owners()
    print("status:", status_code)
    print("success:", result.get("success"))
    print("daily_brief_status:", result.get("status"))
    print("delivery_count:", result.get("delivery_count"))
    print("sends_telegram:", result.get("sends_telegram"))
    print("can_trigger_outbound_llm:", result.get("can_trigger_outbound_llm"))
    print("writes:", result.get("writes"))
    print("dispatch_enabled:", result.get("dispatch_enabled"))
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
