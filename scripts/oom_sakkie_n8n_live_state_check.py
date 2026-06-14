import json
import os
from pathlib import Path
from urllib import request

from dotenv import load_dotenv


GATEKEEPER_NAME = "2 - The GateKeeper"
BACKEND_RELAY_NAME = "2.0B - Oom Sakkie Backend Read-Only Relay"


def main():
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    base_url = str(os.getenv("N8N_BASE_URL", "") or "").rstrip("/")
    api_key = str(os.getenv("N8N_API_KEY", "") or "")
    if not base_url or not api_key:
        print("n8n_live_state_status: skipped")
        print("reason: N8N_BASE_URL and N8N_API_KEY are required")
        return 2

    workflows = list_workflows(base_url, api_key)
    by_name = {workflow.get("name"): workflow for workflow in workflows}
    errors = []

    gatekeeper = by_name.get(GATEKEEPER_NAME)
    relay = by_name.get(BACKEND_RELAY_NAME)
    if not gatekeeper:
        errors.append("GateKeeper workflow not found")
    if not relay:
        errors.append("2.0B backend relay workflow not found")

    gatekeeper_detail = get_workflow(base_url, api_key, gatekeeper["id"]) if gatekeeper else None
    relay_detail = get_workflow(base_url, api_key, relay["id"]) if relay else None
    if gatekeeper_detail:
        errors.extend(validate_gatekeeper(gatekeeper_detail))
    if relay_detail:
        errors.extend(validate_relay(relay_detail))

    print("n8n_live_state_status:", "ok" if not errors else "blocked")
    if gatekeeper:
        print("gatekeeper_id:", gatekeeper.get("id"))
        print("gatekeeper_active:", gatekeeper.get("active"))
    if relay:
        print("backend_relay_id:", relay.get("id"))
        print("backend_relay_active:", relay.get("active"))
    if gatekeeper_detail:
        print("gatekeeper_message_target:", gatekeeper_message_target(gatekeeper_detail))
    if relay_detail:
        print("backend_relay_telegram_trigger:", has_node_type(relay_detail, "n8n-nodes-base.telegramTrigger"))
        print("backend_relay_telegram_send:", has_node_type(relay_detail, "n8n-nodes-base.telegram"))
    for error in errors:
        print(f"- {error}")
    return 1 if errors else 0


def list_workflows(base_url, api_key):
    req = request.Request(
        f"{base_url}/api/v1/workflows?limit=100",
        headers={"X-N8N-API-KEY": api_key},
    )
    with request.urlopen(req, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    data = payload.get("data", payload if isinstance(payload, list) else [])
    return data if isinstance(data, list) else []


def get_workflow(base_url, api_key, workflow_id):
    req = request.Request(
        f"{base_url}/api/v1/workflows/{workflow_id}",
        headers={"X-N8N-API-KEY": api_key},
    )
    with request.urlopen(req, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_gatekeeper(workflow):
    errors = []
    nodes = workflow.get("nodes", [])
    telegram_triggers = [node for node in nodes if node.get("type") == "n8n-nodes-base.telegramTrigger"]
    if workflow.get("active") is not True:
        errors.append("GateKeeper should be active")
    if len(telegram_triggers) != 1:
        errors.append("GateKeeper must have exactly one Telegram Trigger")
    names = {node.get("name") for node in nodes}
    for name in ["Security Check", "Switch - Telegram Update Type", "Switch - Route Telegram Callback Type"]:
        if name not in names:
            errors.append(f"GateKeeper missing {name}")
    return errors


def validate_relay(workflow):
    errors = []
    if has_node_type(workflow, "n8n-nodes-base.telegramTrigger"):
        errors.append("2.0B must not have a Telegram Trigger")
    if has_node_type(workflow, "n8n-nodes-base.telegram"):
        errors.append("2.0B must not have a Telegram send node")
    text = json.dumps(workflow)
    for required in [
        "/api/oom-sakkie/channels/telegram/message",
        "caller_handles_telegram_send",
        "can_trigger_outbound_llm",
        "writes",
        "send_allowed",
    ]:
        if required not in text:
            errors.append(f"2.0B missing {required}")
    return errors


def gatekeeper_message_target(workflow):
    text = json.dumps(workflow)
    if BACKEND_RELAY_NAME in text:
        return "2.0B_backend_relay"
    if "2.0 - OOM SAKKIE - Amadeus Assistant Agent" in text:
        return "2.0_legacy_assistant"
    return "unknown"


def has_node_type(workflow, node_type):
    return any(node.get("type") == node_type for node in workflow.get("nodes", []))


if __name__ == "__main__":
    raise SystemExit(main())
