import json
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import load_dotenv


DEFAULT_BASE_URL = "http://127.0.0.1:5000"
GATEWAY_PATH = "/api/oom-sakkie/channels/telegram/message"
PREFLIGHT_PATH = "/api/oom-sakkie/channels/telegram/exposure-preflight"


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    base_url = str(os.getenv("OOM_SAKKIE_TELEGRAM_RELAY_SMOKE_BASE_URL", "") or "").strip() or DEFAULT_BASE_URL
    token = str(os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN", "") or "").strip()
    user_id = str(os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_USER_ID", "") or "").strip() or "local-smoke-user"
    chat_id = str(os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_CHAT_ID", "") or "").strip() or "local-smoke-chat"
    text = str(os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_TEXT", "") or "").strip() or "what needs attention today"

    if len(token) < 32:
        print("SKIP: set OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN to a 32+ character value.")
        return 2

    preflight_status, preflight = _get_json(f"{base_url}{PREFLIGHT_PATH}")
    print("preflight_status:", preflight_status)
    print("preflight_state:", preflight.get("status"))
    print("private_test_ready:", preflight.get("private_test_ready"))
    print("public_exposure_ready:", preflight.get("public_exposure_ready"))
    if preflight_status != 200 or not preflight.get("private_test_ready"):
        return 1
    if _has_authority(preflight):
        return 1

    gateway_status, gateway = _post_json(
        f"{base_url}{GATEWAY_PATH}",
        {
            "message": {
                "text": text,
                "from": {"id": user_id},
                "chat": {"id": chat_id},
            },
        },
        token,
    )
    print("gateway_status:", gateway_status)
    print("gateway_state:", gateway.get("status"))
    print("sends_telegram:", gateway.get("sends_telegram"))
    print("can_trigger_outbound_llm:", gateway.get("can_trigger_outbound_llm"))
    print("writes:", gateway.get("writes"))
    print("records_audit_trace:", gateway.get("records_audit_trace"))
    print("reply_transport:", gateway.get("reply_transport"))
    print("reply_chat_id:", (gateway.get("reply") or {}).get("chat_id"))
    print("answer:", gateway.get("answer"))
    if gateway_status != 200 or not gateway.get("success"):
        return 1
    if _has_authority(gateway):
        return 1
    reply = gateway.get("reply") or {}
    if reply.get("sends_telegram") or not str(reply.get("text") or "").strip():
        return 1
    return 0


def _get_json(url):
    try:
        with urllib_request.urlopen(url, timeout=20) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8") or "{}")


def _post_json(url, payload, token):
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
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib_error.HTTPError as error:
        return error.code, json.loads(error.read().decode("utf-8") or "{}")


def _has_authority(payload):
    return any([
        payload.get("sends_telegram"),
        payload.get("direct_bot_cutover_enabled"),
        payload.get("can_trigger_outbound_llm"),
        payload.get("writes"),
        payload.get("dispatch_enabled"),
        payload.get("changes_runtime_now"),
        payload.get("changes_prompt_now"),
        payload.get("physical_controls_enabled"),
        payload.get("customer_public_output_enabled"),
    ])


if __name__ == "__main__":
    raise SystemExit(main())
