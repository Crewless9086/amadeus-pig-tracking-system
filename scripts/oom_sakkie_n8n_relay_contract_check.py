import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / "docs" / "04-n8n" / "workflows" / "2.0B - Oom Sakkie Backend Read-Only Relay" / "workflow.json"
README_PATH = WORKFLOW_PATH.with_name("README.md")


def main():
    errors = validate_relay_contract(WORKFLOW_PATH, README_PATH)
    if errors:
        print("relay_contract_status: failed")
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("relay_contract_status: ok")
    print(f"workflow: {WORKFLOW_PATH.relative_to(REPO_ROOT)}")
    print("active: false")
    print("telegram_trigger: absent")
    print("telegram_send_node: absent")
    print("transport_guard: localhost_or_https")
    print("authority_validation: present")
    return 0


def validate_relay_contract(workflow_path=WORKFLOW_PATH, readme_path=README_PATH):
    errors = []
    try:
        workflow = json.loads(Path(workflow_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"workflow_json_unreadable: {exc}"]

    readme = ""
    try:
        readme = Path(readme_path).read_text(encoding="utf-8")
    except OSError as exc:
        errors.append(f"readme_unreadable: {exc}")

    nodes = workflow.get("nodes") if isinstance(workflow, dict) else None
    if not isinstance(nodes, list):
        return ["workflow_nodes_missing"]

    node_types = {str(node.get("type", "")) for node in nodes if isinstance(node, dict)}
    node_names = {str(node.get("name", "")) for node in nodes if isinstance(node, dict)}
    workflow_text = json.dumps(workflow, sort_keys=True)

    if workflow.get("active") is not False:
        errors.append("workflow_must_import_inactive")
    if "n8n-nodes-base.executeWorkflowTrigger" not in node_types:
        errors.append("execute_workflow_trigger_missing")
    if "n8n-nodes-base.telegramTrigger" in node_types:
        errors.append("telegram_trigger_must_be_absent")
    if "n8n-nodes-base.telegram" in node_types:
        errors.append("telegram_send_node_must_be_absent")
    if "HTTP - Call Oom Sakkie Gateway" not in node_names:
        errors.append("backend_gateway_http_node_missing")
    if "IF - Gateway Request Ready" not in node_names:
        errors.append("gateway_request_ready_if_missing")
    if "/api/oom-sakkie/channels/telegram/message" not in workflow_text:
        errors.append("backend_gateway_path_missing")
    if "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN" not in workflow_text:
        errors.append("vars_token_reference_missing")
    if "$env" in workflow_text:
        errors.append("code_node_env_access_must_be_absent")
    if "$vars" not in workflow_text:
        errors.append("n8n_variables_reference_missing")
    if "test-telegram-token" in workflow_text or "5721652188" in workflow_text:
        errors.append("committed_workflow_must_not_contain_test_token_or_owner_chat_id")

    build_node = _node_by_name(nodes, "Code - Build Backend Gateway Request")
    build_js = _node_js(build_node)
    if "baseUrlIsLocalOrTls" not in build_js:
        errors.append("transport_guard_function_missing")
    if 'parsed.protocol === "https:"' not in build_js:
        errors.append("https_allow_rule_missing")
    if '"127.0.0.1", "localhost", "[::1]"' not in build_js:
        errors.append("local_http_allowlist_missing")
    if "workflowVariable" not in build_js:
        errors.append("n8n_variable_reader_missing")
    if "normalizeBaseUrl" not in build_js or "cleanVariable" not in build_js:
        errors.append("base_url_normalizer_missing")
    if "base_url_diagnostic" not in build_js:
        errors.append("base_url_diagnostic_missing")
    if "gateway_token" in build_js:
        errors.append("token_must_not_be_emitted_into_item_json")

    if_node = _node_by_name(nodes, "IF - Gateway Request Ready")
    if_text = json.dumps(if_node, sort_keys=True)
    if "gateway_url" not in if_text or "success === true" not in if_text:
        errors.append("gateway_request_ready_condition_missing")
    build_connections = workflow.get("connections", {}).get("Code - Build Backend Gateway Request", {})
    if "IF - Gateway Request Ready" not in json.dumps(build_connections):
        errors.append("build_node_must_route_to_request_ready_if")

    validate_node = _node_by_name(nodes, "Code - Validate Caller-Send Reply")
    validate_js = _node_js(validate_node)
    for flag in [
        "sends_telegram",
        "direct_bot_cutover_enabled",
        "can_trigger_outbound_llm",
        "writes",
        "dispatch_enabled",
        "changes_runtime_now",
        "changes_prompt_now",
        "physical_controls_enabled",
        "customer_public_output_enabled",
    ]:
        if flag not in validate_js:
            errors.append(f"authority_flag_not_validated:{flag}")
    if "send_allowed: true" not in validate_js or "send_allowed: false" not in validate_js:
        errors.append("send_allowed_success_and_failure_paths_required")

    if "Do not add a Telegram Trigger" not in readme:
        errors.append("readme_single_trigger_warning_missing")
    if "Remote plain HTTP is rejected" not in readme:
        errors.append("readme_transport_guard_missing")
    if "Do not use `$env`" not in readme:
        errors.append("readme_env_access_warning_missing")

    return errors


def _node_by_name(nodes, name):
    for node in nodes:
        if isinstance(node, dict) and node.get("name") == name:
            return node
    return {}


def _node_js(node):
    if not isinstance(node, dict):
        return ""
    params = node.get("parameters")
    if not isinstance(params, dict):
        return ""
    return str(params.get("jsCode", ""))


if __name__ == "__main__":
    raise SystemExit(main())
