import json
import subprocess
import unittest
from pathlib import Path


WORKFLOW_ROOT = Path("docs/04-n8n/workflows")
STEWARD_WORKFLOW = WORKFLOW_ROOT / "1.2 - order-steward" / "workflow.json"
SAM_WORKFLOW = WORKFLOW_ROOT / "1.0 - Sam-sales-agent-chatwoot" / "workflow.json"


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


if __name__ == "__main__":
    unittest.main()
