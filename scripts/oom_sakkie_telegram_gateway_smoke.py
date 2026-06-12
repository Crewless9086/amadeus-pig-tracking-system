import json
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import load_dotenv


DEFAULT_URL = "http://127.0.0.1:5000/api/oom-sakkie/channels/telegram/message"


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    enabled = str(os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED", "") or "").strip().lower() in {"1", "true", "yes", "on"}
    token = str(os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN", "") or "").strip()
    allowed_user_ids = str(os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "") or "").strip()
    url = str(os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_URL", "") or "").strip() or DEFAULT_URL
    if not enabled or not token or len(token) < 32 or not allowed_user_ids:
        print("SKIP: set OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED=1, a 32+ character OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN, and OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS in .env.")
        return 2

    payload = {
        "message": {
            "text": os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_TEXT", "what needs attention today"),
            "from": {"id": os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_USER_ID", "local-smoke-user")},
            "chat": {"id": os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_CHAT_ID", "local-smoke-chat")},
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=20) as response:
            response_body = json.loads(response.read().decode("utf-8"))
            status_code = response.status
    except urllib_error.HTTPError as error:
        response_body = json.loads(error.read().decode("utf-8") or "{}")
        status_code = error.code
    except OSError as error:
        print("ERROR: gateway smoke could not reach local Oom Sakkie:", error)
        return 1

    print("status:", status_code)
    print("success:", response_body.get("success"))
    print("gateway_status:", response_body.get("status"))
    print("sends_telegram:", response_body.get("sends_telegram"))
    print("can_trigger_outbound_llm:", response_body.get("can_trigger_outbound_llm"))
    print("writes:", response_body.get("writes"))
    print("records_audit_trace:", response_body.get("records_audit_trace"))
    print("dispatch_enabled:", response_body.get("dispatch_enabled"))
    print("tool:", (response_body.get("message") or {}).get("tool_used"))
    print("answer:", response_body.get("answer"))
    if status_code != 200 or not response_body.get("success"):
        return 1
    if response_body.get("sends_telegram") or response_body.get("can_trigger_outbound_llm") or response_body.get("writes") or response_body.get("dispatch_enabled"):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
