import json
from pathlib import Path
import subprocess

WORKFLOW = Path("docs/04-n8n/workflows/2.0B - Oom Sakkie Backend Read-Only Relay/workflow.json")

def run_validator(payload):
    workflow = json.loads(WORKFLOW.read_text(encoding="utf-8"))
    code = next(node for node in workflow["nodes"] if node["name"] == "Code - Validate Caller-Send Reply")["parameters"]["jsCode"]
    script = "const f=new Function('$json'," + json.dumps(code) + "); process.stdout.write(JSON.stringify(f(" + json.dumps(payload) + ")));"
    completed = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(completed.stdout)[0]["json"]

def base():
    return {"success": True, "status": "waiting_for_input",
        "reply_transport": "backend_handles_owner_task_delivery",
        "delivery": {"success": True, "status": "family_message_delivered"},
        "sends_telegram": True, "direct_bot_cutover_enabled": False,
        "can_trigger_outbound_llm": False, "writes": False, "dispatch_enabled": False,
        "changes_runtime_now": False, "changes_prompt_now": False,
        "physical_controls_enabled": False, "customer_public_output_enabled": False}

def test_confirmed_backend_delivery_completes_without_duplicate_caller_send():
    result = run_validator(base())
    assert result["success"] is True and result["send_allowed"] is False
    assert result["status"] == "relay_backend_delivery_complete"

def test_unconfirmed_or_authority_escalated_backend_delivery_fails_closed():
    missing = run_validator({**base(), "delivery": {"success": False}})
    hardware = run_validator({**base(), "physical_controls_enabled": True})
    assert missing["success"] is hardware["success"] is False
    assert missing["send_allowed"] is hardware["send_allowed"] is False

def test_legacy_caller_send_contract_remains_available_without_backend_send():
    payload = {**base(), "status": "answered", "reply_transport": "caller_handles_telegram_send",
        "sends_telegram": False, "reply": {"chat_id": "42", "text": "Supported answer"}}
    result = run_validator(payload)
    assert result["success"] is True and result["send_allowed"] is True
    assert result["status"] == "relay_reply_ready"
