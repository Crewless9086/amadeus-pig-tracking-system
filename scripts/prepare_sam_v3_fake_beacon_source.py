import argparse
import json
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import request as urllib_request

from dotenv import load_dotenv


DEFAULT_POST_TEXT = (
    "Fresh Amadeus Farm pork freezer orders are opening for a small Riversdale pilot. "
    "Half-carcass and cut-set options are available by enquiry, with final price and timing "
    "confirmed by the farm before any booking."
)
DEFAULT_CALL_TO_ACTION = "Message Sam on WhatsApp for the freezer options."
DEFAULT_CAMPAIGN_ID = "BEACON-FAKE-MEAT-SOURCE-TEST"
DEFAULT_LABELS = ["beacon_meat_launch", "sam_v3_fake_source_test"]


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    parser = argparse.ArgumentParser(
        description="Prepare one Chatwoot conversation with fake Beacon/Facebook source context for Sam v3 live testing."
    )
    parser.add_argument("--conversation-id", required=True, help="Chatwoot conversation ID to tag for the test.")
    parser.add_argument("--apply", action="store_true", help="Write attributes and labels to Chatwoot. Default is dry-run.")
    parser.add_argument("--campaign-id", default=DEFAULT_CAMPAIGN_ID)
    parser.add_argument("--post-text", default=DEFAULT_POST_TEXT)
    parser.add_argument("--call-to-action", default=DEFAULT_CALL_TO_ACTION)
    parser.add_argument("--target-area", default="Riversdale")
    parser.add_argument("--product-focus", default="half carcass Set A pork freezer pilot")
    parser.add_argument("--base-url", default=os.getenv("CHATWOOT_BASE_URL", "https://app.chatwoot.com"))
    parser.add_argument("--account-id", default=os.getenv("CHATWOOT_ACCOUNT_ID", "147387"))
    args = parser.parse_args()

    payload = build_fake_beacon_source_payload(
        campaign_id=args.campaign_id,
        post_text=args.post_text,
        call_to_action=args.call_to_action,
        target_area=args.target_area,
        product_focus=args.product_focus,
    )
    print(json.dumps({
        "mode": "dry_run" if not args.apply else "apply",
        "conversation_id": args.conversation_id,
        "custom_attributes": payload["custom_attributes"],
        "labels": payload["labels"],
        "customer_test_message": customer_test_message(args.target_area),
        "notes": [
            "This creates fake source context only; it does not post to Facebook.",
            "Send the customer_test_message from WhatsApp after the attributes are applied.",
        ],
    }, indent=2, sort_keys=True))

    if not args.apply:
        print("apply_status: skipped")
        print("reason: rerun with --apply to write this fake source context to Chatwoot")
        return 0

    result = apply_fake_beacon_source_to_chatwoot(
        args.conversation_id,
        payload,
        base_url=args.base_url,
        account_id=args.account_id,
        token=os.getenv("CHATWOOT_API_ACCESS_TOKEN") or os.getenv("CHATWOOT_API_TOKEN"),
    )
    print("apply_status:", result["status"])
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["success"] else 1


def build_fake_beacon_source_payload(
    *,
    campaign_id=DEFAULT_CAMPAIGN_ID,
    post_text=DEFAULT_POST_TEXT,
    call_to_action=DEFAULT_CALL_TO_ACTION,
    target_area="Riversdale",
    product_focus="half carcass Set A pork freezer pilot",
):
    return {
        "custom_attributes": {
            "meat_product_type": "",
            "meat_cut_set": "",
            "meat_delivery_mode": "",
            "meat_lead_id": "",
            "meat_payment_state": "",
            "meat_next_gate": "",
            "meat_budget_amount": "",
            "meat_target_packed_kg": "",
            "meat_match_preference": "",
            "source_campaign_id": _clean(campaign_id, 120),
            "meat_source_campaign_id": _clean(campaign_id, 120),
            "beacon_campaign_id": _clean(campaign_id, 120),
            "source_post_text": _clean(post_text, 1600),
            "source_call_to_action": _clean(call_to_action, 240),
            "campaign_source": "fake_beacon_facebook_test",
            "sales_lane": "meat_preorder",
            "meat_product_focus": _clean(product_focus, 180),
            "product_focus": _clean(product_focus, 180),
            "target_area": _clean(target_area, 120),
            "meat_delivery_town": _clean(target_area, 120),
            "sam_v3_test_source": "fake_beacon_facebook_context_no_public_post",
            "sam_v3_test_reset": "cleared_stale_meat_operational_attrs",
        },
        "labels": list(DEFAULT_LABELS),
    }


def customer_test_message(target_area="Riversdale"):
    area = _clean(target_area, 80) or "Riversdale"
    return f"Hi, I saw the pork half-carcass post and want more info for {area}."


def apply_fake_beacon_source_to_chatwoot(conversation_id, payload, *, base_url, account_id, token):
    conversation_id = _clean(conversation_id, 100)
    base_url = _clean(base_url, 200).rstrip("/")
    account_id = _clean(account_id, 80)
    token = _clean(token, 300)
    if not conversation_id:
        return {"success": False, "status": "conversation_id_required"}
    if not base_url:
        return {"success": False, "status": "chatwoot_base_url_required"}
    if not account_id:
        return {"success": False, "status": "chatwoot_account_id_required"}
    if not token:
        return {"success": False, "status": "chatwoot_api_token_required"}

    existing = _chatwoot_request("GET", base_url, account_id, conversation_id, token)
    existing_attrs = _extract_custom_attributes(existing)
    existing_labels = _extract_labels(existing)
    merged_attrs = {**existing_attrs, **payload["custom_attributes"]}
    merged_labels = sorted(set(existing_labels) | set(payload["labels"]))
    attr_result = _chatwoot_request(
        "POST",
        base_url,
        account_id,
        conversation_id,
        token,
        suffix="custom_attributes",
        body={"custom_attributes": merged_attrs},
    )
    label_result = _chatwoot_request(
        "POST",
        base_url,
        account_id,
        conversation_id,
        token,
        suffix="labels",
        body={"labels": merged_labels},
    )
    return {
        "success": True,
        "status": "fake_beacon_source_context_applied",
        "conversation_id": conversation_id,
        "custom_attribute_count": len(payload["custom_attributes"]),
        "preserved_attribute_count": len([key for key in existing_attrs if key not in payload["custom_attributes"]]),
        "labels": merged_labels,
        "chatwoot": {
            "custom_attributes": _result_summary(attr_result),
            "labels": _result_summary(label_result),
        },
        "posts_publicly": False,
        "calls_meta": False,
        "sends_customer_message": False,
    }


def _chatwoot_request(method, base_url, account_id, conversation_id, token, *, suffix="", body=None):
    path = f"{base_url}/api/v1/accounts/{account_id}/conversations/{conversation_id}"
    if suffix:
        path = f"{path}/{suffix}"
    data = json.dumps(body or {}, ensure_ascii=True, sort_keys=True).encode("utf-8") if body is not None else None
    headers = {"api_access_token": token}
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib_request.Request(path, data=data, headers=headers, method=method)
    try:
        with urllib_request.urlopen(req, timeout=20) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return {"status_code": getattr(response, "status", 200), "body": _parse_json(raw)}
    except urllib_error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        return {"status_code": exc.code, "body": _parse_json(raw), "error": f"chatwoot_http_{exc.code}"}


def _extract_custom_attributes(result):
    body = result.get("body") if isinstance(result, dict) else {}
    candidates = [
        body.get("custom_attributes"),
        (body.get("conversation") if isinstance(body.get("conversation"), dict) else {}).get("custom_attributes"),
        (body.get("data") if isinstance(body.get("data"), dict) else {}).get("custom_attributes"),
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            return dict(candidate)
    return {}


def _extract_labels(result):
    body = result.get("body") if isinstance(result, dict) else {}
    candidates = [
        body.get("labels"),
        (body.get("conversation") if isinstance(body.get("conversation"), dict) else {}).get("labels"),
        (body.get("data") if isinstance(body.get("data"), dict) else {}).get("labels"),
    ]
    labels = set()
    for candidate in candidates:
        if not isinstance(candidate, list):
            continue
        for item in candidate:
            if isinstance(item, dict):
                label = _clean(item.get("title") or item.get("name"), 80)
            else:
                label = _clean(item, 80)
            if label:
                labels.add(label)
    return labels


def _result_summary(result):
    body = result.get("body") if isinstance(result, dict) else {}
    return {
        "status_code": result.get("status_code"),
        "success": int(result.get("status_code") or 0) < 400,
        "status": body.get("status") or body.get("message") or result.get("error", ""),
    }


def _parse_json(raw):
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"raw_preview": (raw or "")[:300]}


def _clean(value, limit=300):
    text = str(value or "").strip()
    return " ".join(text.split())[:limit]


if __name__ == "__main__":
    raise SystemExit(main())
