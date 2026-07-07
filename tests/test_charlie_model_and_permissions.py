import unittest
from unittest.mock import patch

from modules.charlie.model_registry import choose_agent_model, choose_model, estimate_model_cost, model_registry_packet
from modules.charlie.tool_permissions import audit_tool_call, check_tool_permission, permission_packet


class CharlieModelAndPermissionTests(unittest.TestCase):
    def test_model_registry_selects_security_model_for_high_risk_security_review(self):
        model = choose_model(task_type="review", risk_level="high", required_use_case="security_review")

        self.assertEqual(model["registry_key"], "security_review")
        self.assertEqual(model["risk_level"], "high")

    def test_cost_estimate_is_structured_even_before_prices_are_configured(self):
        estimate = estimate_model_cost("default_reasoning", input_tokens=1500, output_tokens=500)

        self.assertEqual(estimate["input_tokens"], 1500)
        self.assertEqual(estimate["output_tokens"], 500)
        self.assertEqual(estimate["currency"], "USD")

    def test_model_registry_packet_exposes_manual_safety_note(self):
        packet = model_registry_packet()

        self.assertIn("models", packet)
        self.assertIn("agent_model_map", packet)
        self.assertIn("safety_note", packet)

    def test_agent_model_assignment_records_runtime_note(self):
        model = choose_agent_model("security_reviewer", mission_type="system improvement", risk_level="high")

        self.assertEqual(model["registry_key"], "security_review")
        self.assertEqual(model["agent"], "security_reviewer")
        self.assertIn("runtime_note", model)

    @patch.dict("os.environ", {"CHARLIE_AGENT_MODEL_SECURITY_REVIEWER": "security-model-live"}, clear=False)
    def test_agent_model_assignment_uses_runtime_env_when_configured(self):
        model = choose_agent_model("security_reviewer", mission_type="system improvement", risk_level="high")

        self.assertTrue(model["runtime_configured"])
        self.assertEqual(model["runtime_model"], "security-model-live")

    @patch.dict("os.environ", {"ANTROPIC_API_KEY": "typo-key"}, clear=True)
    def test_agent_model_assignment_activates_claude_review_provider_with_typo_alias(self):
        model = choose_agent_model("security_reviewer", mission_type="system improvement", risk_level="high")

        self.assertEqual(model["runtime_provider"], "anthropic")
        self.assertEqual(model["runtime_model"], "claude-sonnet-5")
        self.assertTrue(model["runtime_configured"])
        self.assertEqual(model["api_key_env"], "ANTROPIC_API_KEY")

    @patch.dict("os.environ", {"ANTHROPIC_API_KEY": "real-key"}, clear=True)
    def test_agent_model_assignment_keeps_builder_on_codex(self):
        model = choose_agent_model("builder", mission_type="system improvement", risk_level="medium")

        self.assertEqual(model["runtime_provider"], "codex_cli")

    def test_tool_permission_blocks_red_zone_without_owner_approval(self):
        result = check_tool_permission("builder", "migration", owner_approved=False)

        self.assertFalse(result["permitted"])
        self.assertEqual(result["decision_reason"], "tool_class_not_allowed_for_agent")

    def test_tool_permission_allows_builder_repo_write_with_owner_approval(self):
        result = check_tool_permission("builder", "repo_write", owner_approved=True)

        self.assertTrue(result["permitted"])
        self.assertEqual(result["decision_reason"], "allowed")

    def test_permission_packet_lists_allowed_and_blocked_tools(self):
        packet = permission_packet("tester")

        self.assertIn("test_run", packet["allowed_tool_classes"])
        self.assertIn("customer_send", packet["blocked_tool_classes"])

    def test_audit_tool_call_records_blocked_status(self):
        audit = audit_tool_call("reviewer", "customer_send", "send customer message", owner_approved=False)

        self.assertEqual(audit["audit_status"], "blocked")
        self.assertFalse(audit["permission"]["permitted"])

    def test_visual_checks_are_allowed_for_tester_without_owner_approval(self):
        result = check_tool_permission("tester", "visual_check", owner_approved=False)

        self.assertTrue(result["permitted"])
        self.assertEqual(result["decision_reason"], "allowed")

    def test_brain_guard_can_write_learning_but_not_repo(self):
        learning = check_tool_permission("brain_guard", "learning_write", owner_approved=False)
        repo = check_tool_permission("brain_guard", "repo_write", owner_approved=True)

        self.assertTrue(learning["permitted"])
        self.assertFalse(repo["permitted"])


if __name__ == "__main__":
    unittest.main()
