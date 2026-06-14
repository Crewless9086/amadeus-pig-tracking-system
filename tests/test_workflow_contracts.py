import json
import subprocess
import unittest
from pathlib import Path

from scripts.oom_sakkie_n8n_relay_manual_test import build_manual_payload, validate_relay_output
from scripts.oom_sakkie_n8n_live_state_check import (
    gatekeeper_message_target,
    validate_gatekeeper,
    validate_relay,
)


WORKFLOW_ROOT = Path("docs/04-n8n/workflows")
STEWARD_WORKFLOW = WORKFLOW_ROOT / "1.2 - order-steward" / "workflow.json"
SAM_WORKFLOW = WORKFLOW_ROOT / "1.0 - Sam-sales-agent-chatwoot" / "workflow.json"
OOM_SAKKIE_WORKFLOW = WORKFLOW_ROOT / "2.0 - OOM SAKKIE - Amadeus Assistant Agent" / "workflow.json"
GATEKEEPER_WORKFLOW = WORKFLOW_ROOT / "2 - The GateKeeper" / "workflow.json"
OOM_SAKKIE_BACKEND_RELAY_WORKFLOW = WORKFLOW_ROOT / "2.0B - Oom Sakkie Backend Read-Only Relay" / "workflow.json"
GATEKEEPER_BACKEND_RELAY_PLAN = WORKFLOW_ROOT / "2 - The GateKeeper" / "BACKEND_RELAY_WIRING_PLAN.md"
WEATHER_WORKFLOW = WORKFLOW_ROOT / "2.1 - Amadeus Weather Sub-Agent" / "workflow.json"
FORECAST_WORKFLOW = WORKFLOW_ROOT / "2.1.1 - Amadeus Forecast Tool" / "workflow.json"
SUNSYNK_WORKFLOW = WORKFLOW_ROOT / "2.2 - Amadeus Sunsynk Sub-Agent" / "workflow.json"
IRRIGATION_STATUS_WORKFLOW = WORKFLOW_ROOT / "2.3.3 - Irrigation Status Tool" / "workflow.json"
WEATHER_ALERT_DELIVERY_WORKFLOW = WORKFLOW_ROOT / "ALERT - Weather Backend Delivery" / "workflow.json"
POWER_ALERT_DELIVERY_WORKFLOW = WORKFLOW_ROOT / "ALERT - Power Backend Delivery" / "workflow.json"
FARM_ATTENTION_DIGEST_WORKFLOW = WORKFLOW_ROOT / "ALERT - Farm Attention Digest" / "workflow.json"


REQUIRED_STEWARD_ACTIONS = {
    "create_order_with_lines",
    "update_order",
    "sync_order_lines_from_request",
    "cancel_order",
    "send_for_approval",
    "generate_quote",
    "send_latest_quote",
    "get_order_context",
    "get_active_customer_order_context",
}


REQUIRED_NORMALIZED_FIELDS = {
    "action",
    "order_id",
    "changed_by",
    "conversation_id",
    "account_id",
    "contact_id",
    "customer_name",
    "customer_phone",
    "customer_channel",
    "customer_language",
    "requested_category",
    "requested_weight_range",
    "requested_sex",
    "requested_quantity",
    "requested_items",
    "collection_location",
    "payment_method",
    "send_quote_if_ready",
    "created_from_intake",
    "intake_id",
}


REQUIRED_SAM_EXECUTE_NODES = {
    "Call 1.2 - Create Draft Order",
    "Call 1.2 - Update Existing Draft",
    "Call 1.2 - Sync Order Lines",
    "Call 1.2 - Cancel Order",
    "Call 1.2 - Send For Approval",
    "Call 1.2 - Generate Quote",
    "Call 1.2 - Send Quote",
    "Call 1.2 - Get Order Context",
    "Call 1.2 - Get Active Customer Order Context",
}


REQUIRED_SAM_SLIM_CONTEXT_FIELDS = {
    "sam_order_state_slim",
    "sam_steward_result_compact",
    "active_order_summary",
    "active_order_line_groups",
    "active_order_matches",
    "auto_quote",
    "generated_document",
    "quote_send",
    "quote_send_document_ref",
    "quote_send_document_status",
    "delivery_webhook_sent",
}


REQUIRED_EXISTING_ORDER_CONTEXT_FIELDS = {
    "existing_order_context",
    "order_id",
    "order_status",
    "approval_status",
    "payment_status",
    "requested_category",
    "requested_weight_range",
    "requested_sex",
    "requested_quantity",
    "collection_location",
    "active_line_count",
    "payment_method",
    "order_line_id",
    "pig_id",
    "sale_category",
    "weight_band",
    "line_status",
}


REQUIRED_CHATWOOT_ATTRIBUTE_FIELDS = {
    "order_id",
    "order_status",
    "conversation_mode",
    "pending_action",
    "payment_method",
}


EXPECTED_CHATWOOT_ATTRIBUTE_WRITERS = {
    "HTTP - Set Conversation Human Mode",
    "HTTP - Set Conversation Order Context",
    "HTTP - Set Conversation Context After Update",
    "HTTP - Clear Pending After Cancel",
    "HTTP - Set Pending Cancel Action",
    "HTTP - Clear Pending Action",
    "HTTP - Set Chatwoot After Send Approval",
    "HTTP - Clear Pending After Send Quote",
    "HTTP - Set Pending Send Quote After Sync",
    "HTTP - Set Pending Send Quote After Generate",
}


CHATWOOT_ATTRIBUTE_FIELD_ORDER = [
    "order_id",
    "order_status",
    "conversation_mode",
    "pending_action",
    "payment_method",
]


WORKFLOW_EXPORTS = {
    "sam": SAM_WORKFLOW,
    "steward": STEWARD_WORKFLOW,
    "oom_sakkie": OOM_SAKKIE_WORKFLOW,
    "gatekeeper": GATEKEEPER_WORKFLOW,
    "oom_sakkie_backend_relay": OOM_SAKKIE_BACKEND_RELAY_WORKFLOW,
    "weather": WEATHER_WORKFLOW,
    "forecast": FORECAST_WORKFLOW,
    "sunsynk": SUNSYNK_WORKFLOW,
    "irrigation_status": IRRIGATION_STATUS_WORKFLOW,
    "weather_alert_delivery": WEATHER_ALERT_DELIVERY_WORKFLOW,
    "farm_attention_digest": FARM_ATTENTION_DIGEST_WORKFLOW,
}


def load_workflow(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def node_by_name(workflow, name):
    for node in workflow.get("nodes", []):
        if node.get("name") == name:
            return node
    return None


class WorkflowContractTests(unittest.TestCase):
    def test_workflow_exports_parse_and_have_expected_top_level_shape(self):
        for workflow_name, path in WORKFLOW_EXPORTS.items():
            with self.subTest(workflow=workflow_name):
                workflow = load_workflow(path)
                self.assertIsInstance(workflow.get("nodes"), list)
                self.assertIsInstance(workflow.get("connections"), dict)
                self.assertGreater(len(workflow["nodes"]), 0)

    def test_workflow_connections_reference_existing_nodes(self):
        for workflow_name, path in WORKFLOW_EXPORTS.items():
            workflow = load_workflow(path)
            node_names = {node.get("name") for node in workflow.get("nodes", [])}

            with self.subTest(workflow=workflow_name, area="sources"):
                self.assertTrue(set(workflow.get("connections", {})).issubset(node_names))

            for source_name, source_connections in workflow.get("connections", {}).items():
                for output_group in source_connections.values():
                    for output_index, targets in enumerate(output_group):
                        for target in targets:
                            target_name = target.get("node")
                            with self.subTest(
                                workflow=workflow_name,
                                source=source_name,
                                output_index=output_index,
                                target=target_name,
                            ):
                                self.assertIn(target_name, node_names)

    def test_code_nodes_have_valid_javascript_syntax(self):
        for workflow_name, path in WORKFLOW_EXPORTS.items():
            workflow = load_workflow(path)

            for node in workflow.get("nodes", []):
                code = node.get("parameters", {}).get("jsCode")
                if not code:
                    continue

                node_name = node.get("name")
                wrapped_code = f"(async function() {{\n{code}\n}});"
                result = subprocess.run(
                    ["node", "--check", "-"],
                    input=wrapped_code,
                    text=True,
                    encoding="utf-8",
                    capture_output=True,
                    check=False,
                )

                with self.subTest(workflow=workflow_name, node_name=node_name):
                    self.assertEqual(
                        result.returncode,
                        0,
                        msg=(result.stderr or result.stdout).strip(),
                    )

    def test_steward_switch_supports_phase_7_1b_actions(self):
        workflow = load_workflow(STEWARD_WORKFLOW)
        switch = node_by_name(workflow, "Switch - Route by Action")

        self.assertIsNotNone(switch)
        switch_text = json.dumps(switch)

        for action in sorted(REQUIRED_STEWARD_ACTIONS):
            with self.subTest(action=action):
                self.assertIn(action, switch_text)

    def test_steward_normalizes_shared_handoff_fields(self):
        workflow = load_workflow(STEWARD_WORKFLOW)
        node = node_by_name(workflow, "Code - Normalize Order Payload")

        self.assertIsNotNone(node)
        code = node.get("parameters", {}).get("jsCode", "")

        for field in sorted(REQUIRED_NORMALIZED_FIELDS):
            with self.subTest(field=field):
                self.assertIn(field, code)

    def test_sam_workflow_keeps_expected_steward_execute_nodes(self):
        workflow = load_workflow(SAM_WORKFLOW)
        names = {node.get("name") for node in workflow.get("nodes", [])}

        for node_name in sorted(REQUIRED_SAM_EXECUTE_NODES):
            with self.subTest(node_name=node_name):
                self.assertIn(node_name, names)

    def test_sam_slim_context_keeps_phase_7_1c_compact_fields(self):
        workflow = load_workflow(SAM_WORKFLOW)
        node = node_by_name(workflow, "Code - Slim Sales Agent User Context")

        self.assertIsNotNone(node)
        code = node.get("parameters", {}).get("jsCode", "")

        for field in sorted(REQUIRED_SAM_SLIM_CONTEXT_FIELDS):
            with self.subTest(field=field):
                self.assertIn(field, code)

    def test_steward_order_context_formatter_keeps_slim_context_fields(self):
        workflow = load_workflow(STEWARD_WORKFLOW)
        node = node_by_name(workflow, "Code - Format Get Order Context Result")

        self.assertIsNotNone(node)
        code = node.get("parameters", {}).get("jsCode", "")

        for field in sorted(REQUIRED_EXISTING_ORDER_CONTEXT_FIELDS):
            with self.subTest(field=field):
                self.assertIn(field, code)

    def test_chatwoot_attribute_writes_preserve_lightweight_order_fields(self):
        workflow = load_workflow(SAM_WORKFLOW)
        attribute_writers = []

        for node in workflow.get("nodes", []):
            parameters = node.get("parameters", {})
            text = json.dumps(parameters)
            if "/custom_attributes" in text and "custom_attributes" in text:
                attribute_writers.append(node)

        self.assertGreater(len(attribute_writers), 0)
        writer_names = {node.get("name") for node in attribute_writers}
        self.assertEqual(EXPECTED_CHATWOOT_ATTRIBUTE_WRITERS, writer_names)

        for node in attribute_writers:
            node_name = node.get("name")
            text = json.dumps(node.get("parameters", {}))
            for field in sorted(REQUIRED_CHATWOOT_ATTRIBUTE_FIELDS):
                with self.subTest(node_name=node_name, field=field):
                    self.assertIn(field, text)

    def test_chatwoot_attribute_writes_use_standard_field_order(self):
        workflow = load_workflow(SAM_WORKFLOW)

        for node_name in sorted(EXPECTED_CHATWOOT_ATTRIBUTE_WRITERS):
            node = node_by_name(workflow, node_name)
            self.assertIsNotNone(node)
            body = node.get("parameters", {}).get("jsonBody", "")
            previous_position = -1

            for field in CHATWOOT_ATTRIBUTE_FIELD_ORDER:
                position = body.find(field)
                with self.subTest(node_name=node_name, field=field):
                    self.assertGreater(position, previous_position)
                previous_position = position

    def test_oom_sakkie_weather_tool_uses_ai_supplied_input(self):
        workflow = load_workflow(OOM_SAKKIE_WORKFLOW)
        node = node_by_name(workflow, "Weather_Info_Tool")

        self.assertIsNotNone(node)
        workflow_inputs = node.get("parameters", {}).get("workflowInputs", {})
        input_expression = workflow_inputs.get("value", {}).get("input", "")

        self.assertIn("$fromAI", input_expression)
        self.assertIn("weather_question", input_expression)
        self.assertIn("current weather at the farm", input_expression)
        self.assertLess(input_expression.index("$json.message_text"), input_expression.index("$fromAI"))

    def test_gatekeeper_remains_single_telegram_owner_before_backend_relay_wiring(self):
        workflow = load_workflow(GATEKEEPER_WORKFLOW)
        workflow_text = json.dumps(workflow)
        nodes = workflow.get("nodes", [])
        node_names = {node.get("name") for node in nodes}
        telegram_triggers = [node for node in nodes if node.get("type") == "n8n-nodes-base.telegramTrigger"]

        self.assertTrue(workflow.get("active"))
        self.assertEqual(len(telegram_triggers), 1)
        self.assertIn("Telegram Trigger", node_names)
        self.assertIn("Security Check", node_names)
        self.assertIn("Switch - Telegram Update Type", node_names)
        self.assertIn("Switch - Route Telegram Callback Type", node_names)
        self.assertIn("Call '2.0 - OOM SAKKIE - Amadeus Assistant Agent'", node_names)
        self.assertIn("Call 2.4 - Approval Callback Worker", node_names)
        self.assertIn("Call 2.4.5 - Document Send Callback Worker", node_names)
        self.assertNotIn("2.0B - Oom Sakkie Backend Read-Only Relay", workflow_text)

    def test_backend_relay_workflow_is_import_inactive_and_has_no_telegram_authority(self):
        workflow = load_workflow(OOM_SAKKIE_BACKEND_RELAY_WORKFLOW)
        workflow_text = json.dumps(workflow)
        node_types = {node.get("type") for node in workflow.get("nodes", [])}

        self.assertFalse(workflow.get("active"))
        self.assertIn("n8n-nodes-base.executeWorkflowTrigger", node_types)
        self.assertIn("n8n-nodes-base.if", node_types)
        self.assertNotIn("n8n-nodes-base.telegramTrigger", node_types)
        self.assertNotIn("n8n-nodes-base.telegram", node_types)
        self.assertIn("/api/oom-sakkie/channels/telegram/message", workflow_text)
        self.assertIn("baseUrlIsLocalOrTls", workflow_text)
        self.assertIn("normalizeBaseUrl", workflow_text)
        self.assertIn("base_url_diagnostic", workflow_text)
        self.assertIn("IF - Gateway Request Ready", workflow_text)
        self.assertIn("gateway_url", workflow_text)
        self.assertIn("OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN", workflow_text)
        self.assertIn("$vars", workflow_text)
        self.assertNotIn("$env", workflow_text)
        self.assertNotIn("gateway_token", workflow_text)
        self.assertIn("send_allowed", workflow_text)
        self.assertIn("caller_handles_telegram_send", workflow_text)
        self.assertIn("can_trigger_outbound_llm", workflow_text)
        self.assertIn("direct_bot_cutover_enabled", workflow_text)
        self.assertNotIn("5721652188", workflow_text)

    def test_gatekeeper_backend_relay_wiring_plan_is_owner_only_and_reversible(self):
        plan = GATEKEEPER_BACKEND_RELAY_PLAN.read_text(encoding="utf-8")

        self.assertIn("Upload this workflow first", plan)
        self.assertIn("2.0B - Oom Sakkie Backend Read-Only Relay", plan)
        self.assertIn("Import it inactive", plan)
        self.assertIn("Do not upload or replace `2 - The GateKeeper`", plan)
        self.assertIn("Export/download a backup", plan)
        self.assertIn("Keep the existing `Telegram Trigger`", plan)
        self.assertIn("replace the current call to `2.0 - OOM SAKKIE - Amadeus Assistant Agent`", plan)
        self.assertIn("reply_transport === \"caller_handles_telegram_send\"", plan)
        self.assertIn("sends_telegram === false", plan)
        self.assertIn("can_trigger_outbound_llm === false", plan)
        self.assertIn("writes === false", plan)
        self.assertIn("dispatch_enabled === false", plan)
        self.assertIn("GateKeeper sends exactly one reply", plan)
        self.assertIn("No second Telegram Trigger", plan)
        self.assertIn("restore the exported GateKeeper backup", plan)

    def test_backend_relay_manual_test_helper_builds_safe_payload_and_validates_output(self):
        payload = build_manual_payload()

        self.assertEqual(payload["message_text"], "what needs attention today")
        self.assertIn("user_id", payload)
        self.assertIn("chat_id", payload)
        self.assertIn("message_id", payload)
        self.assertNotIn("token", json.dumps(payload).lower())

        good_output = [{
            "json": {
                "success": True,
                "send_allowed": True,
                "chat_id": "123",
                "telegram_text": "Read-only answer.",
                "reply_transport": "caller_handles_telegram_send",
                "sends_telegram": False,
                "direct_bot_cutover_enabled": False,
                "can_trigger_outbound_llm": False,
                "writes": False,
                "dispatch_enabled": False,
                "changes_runtime_now": False,
                "changes_prompt_now": False,
                "physical_controls_enabled": False,
                "customer_public_output_enabled": False,
            }
        }]
        self.assertEqual(validate_relay_output(good_output), [])

        blocked_output = [{
            "json": {
                **good_output[0]["json"],
                "writes": True,
            }
        }]
        self.assertIn("writes must be false", validate_relay_output(blocked_output))

    def test_n8n_live_state_validator_keeps_gatekeeper_and_relay_boundaries(self):
        gatekeeper = load_workflow(GATEKEEPER_WORKFLOW)
        relay = load_workflow(OOM_SAKKIE_BACKEND_RELAY_WORKFLOW)

        self.assertEqual(validate_gatekeeper(gatekeeper), [])
        self.assertEqual(gatekeeper_message_target(gatekeeper), "2.0_legacy_assistant")
        self.assertEqual(validate_relay(relay), [])

        unsafe_relay = {
            **relay,
            "nodes": relay.get("nodes", []) + [{"name": "Telegram Send", "type": "n8n-nodes-base.telegram"}],
        }
        self.assertIn("2.0B must not have a Telegram send node", validate_relay(unsafe_relay))

    def test_weather_workflow_uses_backend_weather_endpoints(self):
        workflow = load_workflow(WEATHER_WORKFLOW)
        route_node = node_by_name(workflow, "Code - Route Weather Question")
        http_node = node_by_name(workflow, "HTTP - Get Weather Data")
        format_node = node_by_name(workflow, "Code - Format Weather Answer")

        self.assertIsNotNone(route_node)
        self.assertIsNotNone(http_node)
        self.assertIsNotNone(format_node)
        self.assertNotIn("chatgpt-4o-latest", json.dumps(workflow))
        self.assertNotIn("Weather Router (JSON Plan)", json.dumps(workflow))
        self.assertNotIn("Weather Answer LLM (JSON only)", json.dumps(workflow))
        self.assertNotIn("Precheck - Latest Station Row", json.dumps(workflow))
        self.assertNotIn("Read Forecast_10Day_Current", json.dumps(workflow))
        self.assertNotIn("Read Daily_Pivot", json.dumps(workflow))

        route_content = route_node.get("parameters", {}).get("jsCode", "")
        format_content = format_node.get("parameters", {}).get("jsCode", "")
        parameters = http_node.get("parameters", {})

        self.assertEqual(parameters.get("url"), "={{ $json.request_url }}")
        self.assertIn("/api/telemetry/weather/current", route_content)
        self.assertIn("/api/telemetry/weather/today", route_content)
        self.assertIn("/api/telemetry/weather/forecast?days=3", route_content)
        self.assertIn("inputItem.chatInput", route_content)
        self.assertIn("what happened", route_content)
        self.assertIn("current weather at the farm", route_content)
        self.assertIn("backend_supabase_current_weather", format_content)
        self.assertIn("backend_supabase_weather_today", format_content)
        self.assertIn("backend_supabase_weather_forecast", format_content)

    def test_oom_sakkie_sunsynk_tool_uses_ai_supplied_input(self):
        workflow = load_workflow(OOM_SAKKIE_WORKFLOW)
        node = node_by_name(workflow, "Sunsynk_Info_Tool")

        self.assertIsNotNone(node)
        workflow_inputs = node.get("parameters", {}).get("workflowInputs", {})
        input_expression = workflow_inputs.get("value", {}).get("input", "")

        self.assertIn("$fromAI", input_expression)
        self.assertIn("sunsynk_question", input_expression)
        self.assertIn("current power status at the farm", input_expression)

    def test_sunsynk_tool_uses_backend_power_endpoints(self):
        workflow = load_workflow(SUNSYNK_WORKFLOW)
        route_node = node_by_name(workflow, "Code - Route Power Question")
        http_node = node_by_name(workflow, "HTTP - Get Power Data")
        format_node = node_by_name(workflow, "Code - Format Power Answer")

        self.assertIsNotNone(route_node)
        self.assertIsNotNone(http_node)
        self.assertIsNotNone(format_node)
        route_content = route_node.get("parameters", {}).get("jsCode", "")
        format_content = format_node.get("parameters", {}).get("jsCode", "")
        parameters = http_node.get("parameters", {})

        self.assertEqual(parameters.get("url"), "={{ $json.request_url }}")
        self.assertIn("/api/telemetry/power/current", route_content)
        self.assertIn("/api/telemetry/power/recent?hours=24", route_content)
        self.assertIn("asks_energy_total", route_content)
        self.assertIn("sample-based", format_content)
        self.assertIn("cannot confirm kWh", format_content)

        node_names = {node.get("name") for node in workflow.get("nodes", [])}
        self.assertNotIn("AI Sunsynk Agent", node_names)
        self.assertNotIn("OpenAI Chat Model", node_names)
        self.assertNotIn("Sunsynk Current Overview", node_names)

    def test_oom_sakkie_irrigation_tool_uses_ai_supplied_input(self):
        workflow = load_workflow(OOM_SAKKIE_WORKFLOW)
        node = node_by_name(workflow, "Irrigation_Info_Tool")
        agent = node_by_name(workflow, "AI Assistant Agent")

        self.assertIsNotNone(node)
        self.assertIsNotNone(agent)
        workflow_inputs = node.get("parameters", {}).get("workflowInputs", {})
        input_expression = workflow_inputs.get("value", {}).get("input", "")
        system_message = agent.get("parameters", {}).get("options", {}).get("systemMessage", "")

        self.assertIn("$fromAI", input_expression)
        self.assertIn("irrigation_question", input_expression)
        self.assertIn("irrigation status at the farm", input_expression)
        self.assertIn("Irrigation_Info_Tool", system_message)
        self.assertIn("read-only", system_message)
        self.assertIn("cannot start, stop, pause, resume, rebuild, or change irrigation", system_message)

    def test_irrigation_status_tool_is_backend_read_only(self):
        workflow = load_workflow(IRRIGATION_STATUS_WORKFLOW)
        workflow_text = json.dumps(workflow)
        route_node = node_by_name(workflow, "Code - Route Irrigation Question")
        http_node = node_by_name(workflow, "HTTP - Get Irrigation Status")
        format_node = node_by_name(workflow, "Code - Format Irrigation Answer")
        node_names = {node.get("name") for node in workflow.get("nodes", [])}

        self.assertIsNotNone(route_node)
        self.assertIsNotNone(http_node)
        self.assertIsNotNone(format_node)
        self.assertIn("/api/telemetry/irrigation/status", route_node.get("parameters", {}).get("jsCode", ""))
        self.assertEqual(http_node.get("parameters", {}).get("url"), "={{ $json.request_url }}")
        self.assertIn("next_zone_mismatch", format_node.get("parameters", {}).get("jsCode", ""))
        self.assertIn("read-only status", format_node.get("parameters", {}).get("jsCode", ""))

        self.assertNotIn("Telegram Trigger", node_names)
        self.assertNotIn("n8n-nodes-base.googleSheets", workflow_text)
        self.assertNotIn("ifttt.com", workflow_text.lower())
        self.assertNotIn("/start", workflow_text)
        self.assertNotIn("/stop", workflow_text)
        self.assertNotIn("/pause", workflow_text)
        self.assertNotIn("/resume", workflow_text)

    def test_forecast_tool_keeps_safe_blank_defaults_for_optional_offsets(self):
        workflow = load_workflow(FORECAST_WORKFLOW)
        node = node_by_name(workflow, "Set Forecast Inputs")

        self.assertIsNotNone(node)
        assignments = node.get("parameters", {}).get("assignments", {}).get("assignments", [])
        assignment_by_name = {assignment.get("name"): assignment for assignment in assignments}

        for field in ("offsetDays", "startOffsetDays", "endOffsetDays"):
            with self.subTest(field=field):
                self.assertIn(field, assignment_by_name)
                self.assertIn("?? \"\"", assignment_by_name[field].get("value", ""))

    def test_weather_alert_delivery_workflow_is_backend_only_and_filters_test_alerts(self):
        workflow = load_workflow(WEATHER_ALERT_DELIVERY_WORKFLOW)
        workflow_text = json.dumps(workflow)
        extract_node = node_by_name(workflow, "Code - Extract Sendable Alerts")
        node_names = {node.get("name") for node in workflow.get("nodes", [])}

        self.assertFalse(workflow.get("active"))
        self.assertIn("HTTP - Evaluate Weather Alerts", node_names)
        self.assertIn("Code - Extract Sendable Alerts", node_names)
        self.assertIn("Telegram - Send Weather Alert", node_names)
        self.assertNotIn("n8n-nodes-base.googleSheets", workflow_text)
        self.assertNotIn("Weather_Alert_Log", workflow_text)
        self.assertIn("/api/telemetry/weather/alerts/evaluate", workflow_text)
        self.assertIn("X-Amadeus-Telemetry-Key", workflow_text)
        self.assertIn("TELEMETRY_INGEST_API_KEY", workflow_text)
        self.assertIn("BACKEND_AUDIT_TEST", workflow_text)
        self.assertIn("details.test", workflow_text)
        self.assertIn("5721652188", workflow_text)
        self.assertIsNotNone(extract_node)
        extract_code = extract_node.get("parameters", {}).get("jsCode", "")
        self.assertIn('response.mode !== "apply"', extract_code)
        self.assertIn('alert.alert_type === "BACKEND_AUDIT_TEST"', extract_code)
        self.assertIn("details.test === true", extract_code)

    def test_power_alert_delivery_workflow_is_backend_only_and_filters_test_alerts(self):
        workflow = load_workflow(POWER_ALERT_DELIVERY_WORKFLOW)
        workflow_text = json.dumps(workflow)
        extract_node = node_by_name(workflow, "Code - Extract Sendable Alerts")
        node_names = {node.get("name") for node in workflow.get("nodes", [])}

        self.assertFalse(workflow.get("active"))
        self.assertIn("HTTP - Evaluate Power Alerts", node_names)
        self.assertIn("Code - Extract Sendable Alerts", node_names)
        self.assertIn("Telegram - Send Power Alert", node_names)
        self.assertNotIn("n8n-nodes-base.googleSheets", workflow_text)
        self.assertNotIn("Sunsynk_Alert_Log", workflow_text)
        self.assertIn("/api/telemetry/power/alerts/evaluate", workflow_text)
        self.assertIn("X-Amadeus-Telemetry-Key", workflow_text)
        self.assertIn("TELEMETRY_INGEST_API_KEY", workflow_text)
        self.assertIn("POWER_BACKEND_AUDIT_TEST", workflow_text)
        self.assertIn("details.test", workflow_text)
        self.assertIn("5721652188", workflow_text)
        self.assertIsNotNone(extract_node)
        extract_code = extract_node.get("parameters", {}).get("jsCode", "")
        self.assertIn('response.mode !== "apply"', extract_code)
        self.assertIn('alert.alert_type === "POWER_BACKEND_AUDIT_TEST"', extract_code)
        self.assertIn("details.test === true", extract_code)

    def test_farm_attention_digest_workflow_is_backend_only_and_throttled(self):
        workflow = load_workflow(FARM_ATTENTION_DIGEST_WORKFLOW)
        workflow_text = json.dumps(workflow)
        extract_node = node_by_name(workflow, "Code - Extract Sendable Digest")
        node_names = {node.get("name") for node in workflow.get("nodes", [])}

        self.assertFalse(workflow.get("active"))
        self.assertIn("HTTP - Get Farm Attention Summary", node_names)
        self.assertIn("Code - Extract Sendable Digest", node_names)
        self.assertIn("Telegram - Send Farm Attention Digest", node_names)
        self.assertIn("Code - Record Sent Digest", node_names)
        self.assertNotIn("n8n-nodes-base.googleSheets", workflow_text)
        self.assertNotIn("ORDER_OVERVIEW", workflow_text)
        self.assertNotIn("LITTER_OVERVIEW", workflow_text)
        self.assertIn("/api/reports/farm-attention-summary", workflow_text)
        self.assertIn("5721652188", workflow_text)
        self.assertIsNotNone(extract_node)
        extract_code = extract_node.get("parameters", {}).get("jsCode", "")
        self.assertIn("const dryRun = true", extract_code)
        self.assertIn('response.mode !== "read_only"', extract_code)
        self.assertIn("source.writes_to_supabase === true", extract_code)
        self.assertIn("source.writes_to_sheets === true", extract_code)
        self.assertIn("source.sends_telegram === true", extract_code)
        self.assertIn("attentionTotal <= 0", extract_code)
        self.assertIn("$getWorkflowStaticData", extract_code)
        self.assertIn("lastSentHash", extract_code)
        self.assertIn("minHoursBetweenSends", extract_code)
        record_node = node_by_name(workflow, "Code - Record Sent Digest")
        self.assertIsNotNone(record_node)
        record_code = record_node.get("parameters", {}).get("jsCode", "")
        self.assertIn("$getWorkflowStaticData", record_code)
        self.assertIn("lastSentAt", record_code)
        self.assertIn("lastSentHash", record_code)
        self.assertIn("after Telegram delivery succeeds", record_code)


if __name__ == "__main__":
    unittest.main()
