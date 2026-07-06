import unittest

from modules.sales import sam_live_stock_runtime


def inbound_payload(**overrides):
    payload = {
        "event": "message_created",
        "message_type": "incoming",
        "content": "Hi Sam, I need 3 female weaners around 10 to 15kg next week in Riversdale.",
        "conversation": {
            "id": 2401,
            "inbox": {"channel_type": "Channel::Whatsapp"},
        },
        "sender": {
            "id": 99,
            "name": "Charl N",
            "phone_number": "+27820000000",
        },
        "account": {"id": 147387},
    }
    payload.update(overrides)
    return payload


class SamLiveStockRuntimeTests(unittest.TestCase):
    def test_authorize_webhook_is_default_off_and_token_gated(self):
        allowed, denied = sam_live_stock_runtime.authorize_sam_live_stock_webhook({}, environ={})

        self.assertFalse(allowed)
        self.assertEqual(denied["status"], "sam_live_stock_backend_webhook_disabled")
        self.assertFalse(denied["sends_customer_message"])
        self.assertFalse(denied["creates_order"])
        self.assertFalse(denied["reserves_stock"])

        env = {
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN": "test-sam-live-stock-token-32-chars",
        }
        allowed, _denied = sam_live_stock_runtime.authorize_sam_live_stock_webhook(
            {"Authorization": "Bearer test-sam-live-stock-token-32-chars"},
            environ=env,
        )

        self.assertTrue(allowed)

        allowed, _denied = sam_live_stock_runtime.authorize_sam_live_stock_webhook(
            {"X-Amadeus-Sam-Live-Stock-Webhook-Key": "test-sam-live-stock-token-32-chars"},
            environ=env,
        )

        self.assertTrue(allowed)

    def test_policy_stays_read_only_even_if_autoreply_or_llm_envs_enabled(self):
        policy = sam_live_stock_runtime.sam_live_stock_webhook_policy(environ={
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN": "test-sam-live-stock-token-32-chars",
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_AGENT_V3_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_LLM_MODEL": "test-model",
            "OPENAI_API_KEY": "test-key",
        })

        self.assertTrue(policy["enabled"])
        self.assertTrue(policy["autoreply_explicitly_enabled"])
        self.assertFalse(policy["autoreply_enabled"])
        self.assertFalse(policy["llm_enabled"])
        self.assertFalse(policy["agent_v3_enabled"])
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["writes_allowed"])
        self.assertFalse(policy["customer_send_allowed"])

    def test_parse_chatwoot_inbound_ignores_outbound_messages(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(message_type="outgoing"))

        self.assertFalse(inbound["processable"])
        self.assertEqual(inbound["status"], "ignored_non_incoming_message")

    def test_extract_live_stock_facts_from_clear_request(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)

        self.assertEqual(facts["sales_lane"], "live_stock_sales")
        self.assertEqual(facts["category"], "weaner")
        self.assertEqual(facts["quantity"], 3)
        self.assertEqual(facts["sex"], "female")
        self.assertEqual(facts["weight_range"], "10-15 kg")
        self.assertEqual(facts["timing"], "next week")
        self.assertEqual(facts["location"], "Riversdale")
        self.assertFalse(facts["llm_used"])

    def test_merge_prior_context_fills_missing_values_only(self):
        facts = sam_live_stock_runtime.extract_live_stock_facts("I need 2 weaners", {})
        merged = sam_live_stock_runtime.merge_prior_live_stock_context(
            facts,
            {
                "interest": {
                    "sex": "male",
                    "timing": "next week",
                    "location": "Riversdale",
                    "payment_method": "EFT",
                }
            },
        )

        self.assertEqual(merged["quantity"], 2)
        self.assertEqual(merged["category"], "weaner")
        self.assertEqual(merged["sex"], "male")
        self.assertEqual(merged["timing"], "next week")
        self.assertEqual(merged["location"], "Riversdale")

    def test_availability_summary_filters_unsafe_and_matches_category_sex(self):
        rows = [
            {
                "pig_id": "PIG-1",
                "sex": "Female",
                "status": "Active",
                "on_farm": "Yes",
                "reserved_status": "",
                "available_for_sale": "Yes",
                "sale_category": "Weaner",
                "current_weight_kg": 12,
            },
            {
                "pig_id": "PIG-2",
                "sex": "Male",
                "status": "Active",
                "on_farm": "Yes",
                "reserved_status": "Reserved",
                "available_for_sale": "Yes",
                "sale_category": "Weaner",
            },
            {
                "pig_id": "PIG-3",
                "sex": "Female",
                "status": "Sold",
                "on_farm": "No",
                "available_for_sale": "No",
                "sale_category": "Weaner",
            },
        ]

        summary = sam_live_stock_runtime.summarize_live_stock_availability(rows, {"category": "weaner", "sex": "female"})

        self.assertTrue(summary["success"])
        self.assertEqual(summary["total_available_count"], 1)
        self.assertEqual(summary["matched_count"], 1)
        self.assertEqual(summary["matched_sample"][0]["pig_id"], "PIG-1")

    def test_handle_inbound_builds_read_only_decision_without_writes_or_sends(self):
        def intake_loader(_conversation_id):
            return {
                "success": True,
                "lookup_status": "no_match",
                "known_fields": {},
                "items": [],
            }

        def availability_loader():
            return [
                {
                    "pig_id": "PIG-1",
                    "sex": "Female",
                    "status": "Active",
                    "on_farm": "Yes",
                    "reserved_status": "",
                    "available_for_sale": "Yes",
                    "sale_category": "Weaner",
                    "current_weight_kg": 12,
                }
            ]

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            intake_context_loader=intake_loader,
            availability_loader=availability_loader,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["processed"])
        self.assertFalse(result["sent"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])
        self.assertFalse(result["writes_order_intake"])
        decision = result["sam_decision"]
        self.assertEqual(decision["sales_lane"], "live_stock_sales")
        self.assertEqual(decision["availability"]["matched_count"], 1)
        self.assertFalse(decision["customer_send_allowed"])
        self.assertFalse(decision["writes_allowed"])

    def test_non_live_lane_returns_clarification_and_owner_gate(self):
        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(content="I want pork chops and a freezer pack."),
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertEqual(decision["sales_lane"], "meat_sales")
        self.assertTrue(decision["owner_gate_required"])
        self.assertIn("lane_not_live_stock:meat_sales", decision["blockers"])
        self.assertIn("live pigs", decision["suggested_reply_text"])

    def test_context_read_failure_fails_closed_without_write_authority(self):
        def failing_intake(_conversation_id):
            raise RuntimeError("database offline")

        result, _status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            intake_context_loader=failing_intake,
            availability_loader=lambda: [],
        )

        decision = result["sam_decision"]
        self.assertIn("read_context_error", decision["blockers"])
        self.assertTrue(decision["owner_gate_required"])
        self.assertFalse(decision["writes_allowed"])
        self.assertFalse(decision["customer_send_allowed"])


if __name__ == "__main__":
    unittest.main()
