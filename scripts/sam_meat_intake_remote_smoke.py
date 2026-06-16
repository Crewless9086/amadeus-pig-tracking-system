import json
import os
from pathlib import Path
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request

from dotenv import load_dotenv


DEFAULT_BASE_URL = "http://127.0.0.1:5000"
REMOTE_PATH = "/api/oom-sakkie/channels/chatwoot/sam-meat-intake"


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    base_url = str(os.getenv("SAM_MEAT_INTAKE_SMOKE_BASE_URL", "") or "").strip() or DEFAULT_BASE_URL
    token = str(os.getenv("SAM_MEAT_INTAKE_REMOTE_TOKEN", "") or "").strip()
    create_enabled = _env_truthy(os.getenv("SAM_MEAT_INTAKE_SMOKE_CREATE", ""))

    if not _base_url_is_local_or_tls(base_url):
        print("ERROR: use localhost/127.0.0.1 for HTTP smoke URLs, or HTTPS for remote/private endpoints.")
        return 2
    if len(token) < 32:
        print("SKIP: set SAM_MEAT_INTAKE_REMOTE_TOKEN to a 32+ character value.")
        return 2

    bad_status, bad_payload = _post_json(
        f"{base_url.rstrip('/')}{REMOTE_PATH}",
        build_smoke_payload(),
        "wrong-token-for-auth-negative-check",
    )
    print("bad_token_status:", bad_status)
    print("bad_token_state:", bad_payload.get("status"))
    if bad_status != 403 or bad_payload.get("records_tracking_lead"):
        return 1

    if not create_enabled:
        print("create_status: skipped")
        print("reason: set SAM_MEAT_INTAKE_SMOKE_CREATE=1 to create one tracking-only smoke lead")
        return 2

    status, payload = _post_json(f"{base_url.rstrip('/')}{REMOTE_PATH}", build_smoke_payload(), token)
    print("create_status:", status)
    print("create_state:", payload.get("status"))
    print("lead_id:", payload.get("lead_id"))
    print("mode:", payload.get("mode"))
    remote_ingest = payload.get("remote_ingest") or {}
    print("records_tracking_lead:", remote_ingest.get("records_tracking_lead"))
    print("sends_customer_message:", remote_ingest.get("sends_customer_message"))
    print("calls_chatwoot:", remote_ingest.get("calls_chatwoot"))
    print("calls_n8n:", remote_ingest.get("calls_n8n"))
    print("creates_order:", remote_ingest.get("creates_order"))
    print("changes_stock:", remote_ingest.get("changes_stock"))
    print("financial_action:", remote_ingest.get("financial_action"))

    if status not in {200, 201} or not payload.get("success"):
        return 1
    if _has_forbidden_authority(payload):
        return 1
    if not str(payload.get("lead_id") or "").startswith("OSK-SALES-LEAD-"):
        return 1
    return 0


def build_smoke_payload():
    return {
        "customer_name": "Sam Remote Smoke",
        "conversation_id": "sam-meat-intake-remote-smoke",
        "contact_id": "sam-meat-intake-smoke-contact",
        "channel": "chatwoot_whatsapp",
        "whatsapp_window_state": "open",
        "product_type": "half_carcass",
        "cut_set": "Set A",
        "location": "Riversdale",
        "timing": "next available week",
        "delivery_or_collection": "collection",
        "price_per_kg": "",
        "deposit_rule": "",
        "payment_method": "EFT",
        "notes": "Controlled remote smoke: tracking-only Sam meat intake contract.",
        "status": "interested",
    }


def _post_json(url, payload, token):
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
        with urllib_request.urlopen(req, timeout=20) as response:
            return response.status, _parse_json_response(response.read().decode("utf-8"))
    except urllib_error.HTTPError as err:
        raw = err.read().decode("utf-8") or "{}"
        return err.code, _parse_json_response(raw)


def _parse_json_response(raw):
    try:
        return json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {
            "success": False,
            "status": "non_json_response",
            "raw_preview": (raw or "")[:300],
        }


def _base_url_is_local_or_tls(base_url):
    parsed = urllib_parse.urlparse(base_url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme == "https":
        return True
    if parsed.scheme == "http" and host in {"127.0.0.1", "localhost", "::1"}:
        return True
    return False


def _has_forbidden_authority(payload):
    remote_ingest = payload.get("remote_ingest") or {}
    contract = payload.get("contract") or {}
    authority = contract.get("authority") or {}
    return any([
        payload.get("sends_customer_message"),
        payload.get("calls_chatwoot"),
        payload.get("calls_n8n"),
        payload.get("creates_quote"),
        payload.get("creates_order"),
        payload.get("changes_stock"),
        remote_ingest.get("sends_customer_message"),
        remote_ingest.get("calls_chatwoot"),
        remote_ingest.get("calls_n8n"),
        remote_ingest.get("creates_quote"),
        remote_ingest.get("creates_order"),
        remote_ingest.get("changes_stock"),
        remote_ingest.get("financial_action"),
        authority.get("sends_customer_message"),
        authority.get("calls_chatwoot"),
        authority.get("calls_n8n"),
        authority.get("creates_quote"),
        authority.get("creates_order"),
        authority.get("changes_stock"),
    ])


def _env_truthy(value):
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


if __name__ == "__main__":
    raise SystemExit(main())
