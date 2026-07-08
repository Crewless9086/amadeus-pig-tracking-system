import argparse
import json
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from dotenv import load_dotenv


WEBHOOK_PATH = "/api/oom-sakkie/channels/telegram/direct-webhook"


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    parser = argparse.ArgumentParser(description="Set, inspect, or delete the Oom Sakkie direct Telegram webhook.")
    parser.add_argument("action", choices=["info", "set", "delete"])
    parser.add_argument("--base-url", default=os.getenv("OOM_SAKKIE_TELEGRAM_DIRECT_BASE_URL", ""))
    args = parser.parse_args()

    token = str(os.getenv("OOM_SAKKIE_TELEGRAM_BOT_TOKEN", "") or "").strip()
    secret = str(os.getenv("OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET", "") or "").strip()
    if not token:
        print("SKIP: set OOM_SAKKIE_TELEGRAM_BOT_TOKEN.")
        return 2
    if args.action == "set" and len(secret) < 32:
        print("SKIP: set a 32+ character OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET before setting the webhook.")
        return 2

    if args.action == "info":
        payload = {}
        method = "getWebhookInfo"
    elif args.action == "delete":
        payload = {"drop_pending_updates": False}
        method = "deleteWebhook"
    else:
        base_url = str(args.base_url or "").strip().rstrip("/")
        if not _is_https_url(base_url):
            print("SKIP: --base-url or OOM_SAKKIE_TELEGRAM_DIRECT_BASE_URL must be an https:// URL.")
            return 2
        payload = {
            "url": f"{base_url}{WEBHOOK_PATH}",
            "secret_token": secret,
            "drop_pending_updates": False,
            "allowed_updates": ["message", "edited_message", "callback_query"],
        }
        method = "setWebhook"

    response_body, status_code = _telegram_api(token, method, payload)
    print("status:", status_code)
    print("ok:", response_body.get("ok"))
    print("method:", method)
    if args.action == "info":
        result = response_body.get("result") or {}
        print("webhook_url_configured:", bool(result.get("url")))
        print("pending_update_count:", result.get("pending_update_count"))
        print("last_error_date:", result.get("last_error_date"))
        print("last_error_message:", result.get("last_error_message"))
    else:
        print("description:", response_body.get("description"))
    return 0 if status_code == 200 and response_body.get("ok") is True else 1


def _telegram_api(token, method, payload):
    body = json.dumps(payload).encode("utf-8")
    request = urllib_request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib_request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8") or "{}"), response.status
    except urllib_error.HTTPError as error:
        try:
            return json.loads(error.read().decode("utf-8") or "{}"), error.code
        except ValueError:
            return {"ok": False, "description": "Non-JSON Telegram API error."}, error.code
    except OSError as error:
        return {"ok": False, "description": str(error)}, 0


def _is_https_url(value):
    parsed = urllib_parse.urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)


if __name__ == "__main__":
    raise SystemExit(main())
