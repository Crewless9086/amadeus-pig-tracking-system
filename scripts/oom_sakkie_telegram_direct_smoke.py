import json
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from dotenv import load_dotenv


DEFAULT_URL = "http://127.0.0.1:5000/api/oom-sakkie/channels/telegram/direct-webhook"


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    enabled = _truthy(os.getenv("OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED"))
    send_enabled = _truthy(os.getenv("OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED"))
    secret = str(os.getenv("OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET", "") or "").strip()
    allowed_user_ids = str(os.getenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "") or "").strip()
    url = str(os.getenv("OOM_SAKKIE_TELEGRAM_DIRECT_SMOKE_URL", "") or "").strip() or DEFAULT_URL
    smoke_user_id = str(os.getenv("OOM_SAKKIE_TELEGRAM_DIRECT_SMOKE_USER_ID", "") or "").strip() or _first_allowed_user_id(allowed_user_ids)
    smoke_chat_id = str(os.getenv("OOM_SAKKIE_TELEGRAM_DIRECT_SMOKE_CHAT_ID", "") or "").strip() or smoke_user_id
    if not enabled or not send_enabled or len(secret) < 32 or not allowed_user_ids:
        print("SKIP: set OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED=1, OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED=1, a 32+ character OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET, and OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS.")
        return 2
    if not _url_is_local_or_tls(url):
        print("ERROR: use localhost/127.0.0.1 for HTTP smoke URLs, or HTTPS for remote/private endpoints.")
        return 2

    payload = {
        "message": {
            "message_id": 1,
            "text": os.getenv("OOM_SAKKIE_TELEGRAM_DIRECT_SMOKE_TEXT", "what needs attention today"),
            "from": {"id": smoke_user_id, "first_name": "OomSakkieSmoke"},
            "chat": {"id": smoke_chat_id, "type": "private"},
        },
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        url,
        data=body,
        headers={
            "X-Telegram-Bot-Api-Secret-Token": secret,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=25) as response:
            response_body = json.loads(response.read().decode("utf-8") or "{}")
            status_code = response.status
    except urllib_error.HTTPError as error:
        response_body = json.loads(error.read().decode("utf-8") or "{}")
        status_code = error.code
    except OSError as error:
        print("ERROR: direct Telegram smoke could not reach Oom Sakkie:", error)
        return 1

    print("status:", status_code)
    print("success:", response_body.get("success"))
    print("direct_status:", response_body.get("status"))
    print("sends_telegram:", response_body.get("sends_telegram"))
    print("can_trigger_outbound_llm:", response_body.get("can_trigger_outbound_llm"))
    print("writes:", response_body.get("writes"))
    print("records_audit_trace:", response_body.get("records_audit_trace"))
    print("dispatch_enabled:", response_body.get("dispatch_enabled"))
    print("tool:", (response_body.get("message") or {}).get("tool_used"))
    print("answer:", response_body.get("answer"))
    if status_code != 200 or not response_body.get("success"):
        return 1
    if not response_body.get("sends_telegram") or response_body.get("can_trigger_outbound_llm") or response_body.get("writes") or response_body.get("dispatch_enabled"):
        return 1
    return 0


def _first_allowed_user_id(value):
    for candidate in str(value or "").replace(";", ",").split(","):
        candidate = candidate.strip()
        if candidate:
            return candidate
    return "local-smoke-user"


def _url_is_local_or_tls(url):
    parsed = urllib_parse.urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https":
        return True
    if parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}:
        return True
    return False


def _truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
