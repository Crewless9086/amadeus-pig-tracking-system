import argparse
import json
import os
import sys
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.bulk_weight_date_correction import load_local_env


DEFAULT_BASE_URL = "https://amadeus-pig-tracking-system.onrender.com"
INBOUND_PATH = "/api/sales/channels/chatwoot/sam-meat/inbound"


TEST_MESSAGES = [
    "TEST FLOW - owner live pressure test 1. Hi Sam, I saw the Amadeus pork freezer preorder post. What options do you have for a family freezer?",
    "TEST FLOW - owner live pressure test 2. Half carcass Set A in Riversdale, delivery please. EFT is fine. Next available farm run.",
]


def post_json(url, payload, token):
    body = json.dumps(payload).encode("utf-8")
    req = urllib_request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib_request.urlopen(req, timeout=60) as response:
            return response.status, parse_json(response.read().decode("utf-8"))
    except urllib_error.HTTPError as exc:
        return exc.code, parse_json(exc.read().decode("utf-8"))


def parse_json(raw):
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"success": False, "status": "non_json_response", "raw_preview": (raw or "")[:300]}


def build_payload(conversation_id, content, index):
    return {
        "event": "message_created",
        "message_type": "incoming",
        "content": content,
        "id": f"codex-live-pressure-{conversation_id}-{index}",
        "conversation": {
            "id": int(conversation_id) if str(conversation_id).isdigit() else conversation_id,
            "inbox": {"channel_type": "Channel::Whatsapp"},
            "custom_attributes": {
                "sales_lane": "meat_preorder",
                "source_campaign": "beacon_first_pork_preorder_test",
            },
            "labels": ["meat_preorder", "test_flow"],
        },
        "sender": {
            "id": f"codex-live-pressure-contact-{conversation_id}",
            "name": "Charl N",
            "phone_number": "",
        },
        "account": {"id": 147387},
    }


def summarize_response(index, status_code, payload):
    decision = payload.get("sam_decision") if isinstance(payload.get("sam_decision"), dict) else {}
    facts = payload.get("facts") if isinstance(payload.get("facts"), dict) else {}
    lead_result = payload.get("lead_result") if isinstance(payload.get("lead_result"), dict) else {}
    hygiene = payload.get("chatwoot_hygiene") if isinstance(payload.get("chatwoot_hygiene"), dict) else {}
    return {
        "test": index,
        "status_code": status_code,
        "success": payload.get("success"),
        "status": payload.get("status"),
        "lead_id": payload.get("lead_id") or lead_result.get("lead_id") or decision.get("lead_id"),
        "sent": payload.get("sent"),
        "send_status": payload.get("send_status"),
        "reply_source": decision.get("reply_source"),
        "reply_text": decision.get("reply_text", "")[:500],
        "product_type": facts.get("product_type"),
        "cut_set": facts.get("cut_set"),
        "location": facts.get("location"),
        "delivery_or_collection": facts.get("delivery_or_collection"),
        "payment_method": facts.get("payment_method"),
        "agent_decision_status": (payload.get("agent_decision") or {}).get("status") if isinstance(payload.get("agent_decision"), dict) else "",
        "hygiene_status": hygiene.get("status"),
        "forbidden_authority": forbidden_authority(payload),
    }


def forbidden_authority(payload):
    decision = payload.get("sam_decision") if isinstance(payload.get("sam_decision"), dict) else {}
    return any(
        bool(payload.get(key) or decision.get(key))
        for key in [
            "creates_quote",
            "creates_invoice",
            "creates_order",
            "changes_stock",
            "reserves_carcass",
            "books_slaughter",
            "books_butcher",
            "confirms_payment",
        ]
    )


def main():
    parser = argparse.ArgumentParser(description="Run two controlled live SAM meat tests against a real Chatwoot conversation.")
    parser.add_argument("--conversation-id", required=True)
    parser.add_argument("--base-url", default=os.getenv("SAM_MEAT_LIVE_TEST_BASE_URL") or DEFAULT_BASE_URL)
    parser.add_argument("--only", type=int, choices=[1, 2], help="Run only one selected test message.")
    args = parser.parse_args()

    load_local_env()
    token = (os.getenv("SAM_MEAT_BACKEND_WEBHOOK_TOKEN") or "").strip()
    if len(token) < 32:
        print(json.dumps({"success": False, "status": "sam_meat_webhook_token_missing"}))
        return 2

    url = f"{args.base_url.rstrip('/')}{INBOUND_PATH}"
    results = []
    messages = list(enumerate(TEST_MESSAGES, start=1))
    if args.only:
        messages = [item for item in messages if item[0] == args.only]
    for index, message in messages:
        status_code, payload = post_json(url, build_payload(args.conversation_id, message, index), token)
        results.append(summarize_response(index, status_code, payload))

    success = all(
        item["status_code"] == 200
        and item["success"]
        and not item["forbidden_authority"]
        and item["sent"] is True
        for item in results
    )
    print(json.dumps({"success": success, "conversation_id": args.conversation_id, "results": results}, indent=2, sort_keys=True))
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
