import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv


AUTHORITY_FLAGS = [
    "sends_telegram",
    "direct_bot_cutover_enabled",
    "can_trigger_outbound_llm",
    "writes",
    "dispatch_enabled",
    "changes_runtime_now",
    "changes_prompt_now",
    "physical_controls_enabled",
    "customer_public_output_enabled",
]


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    parser = argparse.ArgumentParser(description="Prepare or validate the n8n 2.0B manual relay test.")
    parser.add_argument("--payload", action="store_true", help="Print a safe manual execution payload for n8n 2.0B.")
    parser.add_argument("--validate-output", metavar="PATH", help="Validate a JSON output copied from a 2.0B manual execution.")
    args = parser.parse_args()

    if args.validate_output:
        errors = validate_relay_output(load_json(Path(args.validate_output)))
        if errors:
            print("relay_manual_output_status: blocked")
            for error in errors:
                print(f"- {error}")
            return 1
        print("relay_manual_output_status: ok")
        return 0

    payload = build_manual_payload()
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def build_manual_payload():
    return {
        "message_text": os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_TEXT", "what needs attention today"),
        "user_id": os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_USER_ID", "REPLACE_WITH_ALLOWED_TELEGRAM_USER_ID"),
        "chat_id": os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_CHAT_ID", "REPLACE_WITH_OWNER_CHAT_ID"),
        "message_id": "manual-2-0b-smoke",
        "user_name": os.getenv("OOM_SAKKIE_TELEGRAM_GATEWAY_SMOKE_USER_NAME", "Charl"),
    }


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_relay_output(raw):
    item = normalize_relay_output(raw)
    errors = []
    if not item:
        return ["output must be a JSON object or a one-item n8n array with json payload"]
    if item.get("success") is not True:
        errors.append("success must be true")
    if item.get("send_allowed") is not True:
        errors.append("send_allowed must be true")
    if item.get("reply_transport") != "caller_handles_telegram_send":
        errors.append("reply_transport must be caller_handles_telegram_send")
    if not str(item.get("chat_id") or "").strip():
        errors.append("chat_id must be present")
    if not str(item.get("telegram_text") or "").strip():
        errors.append("telegram_text must be present")
    for flag in AUTHORITY_FLAGS:
        if item.get(flag):
            errors.append(f"{flag} must be false")
    return errors


def normalize_relay_output(raw):
    if isinstance(raw, list) and raw:
        first = raw[0]
        if isinstance(first, dict) and isinstance(first.get("json"), dict):
            return first["json"]
        if isinstance(first, dict):
            return first
    if isinstance(raw, dict) and isinstance(raw.get("json"), dict):
        return raw["json"]
    if isinstance(raw, dict):
        return raw
    return None


if __name__ == "__main__":
    raise SystemExit(main())
