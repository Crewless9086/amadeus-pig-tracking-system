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
            "SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1",
        })

        self.assertTrue(policy["enabled"])
        self.assertTrue(policy["autoreply_explicitly_enabled"])
        self.assertFalse(policy["autoreply_enabled"])
        self.assertFalse(policy["llm_enabled"])
        self.assertFalse(policy["agent_v3_enabled"])
        self.assertTrue(policy["read_only"])
        self.assertFalse(policy["writes_allowed"])
        self.assertFalse(policy["customer_send_allowed"])
        self.assertTrue(policy["intake_write_enabled"])

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
            environ={},
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

    def test_build_live_stock_intake_payload_normalizes_to_backend_contract(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {"missing_fields": []}

        payload = sam_live_stock_runtime.build_live_stock_intake_payload(inbound, facts, decision)
        validation = sam_live_stock_runtime.validate_live_stock_intake_payload(payload)

        self.assertTrue(validation["is_valid"], validation)
        self.assertEqual(payload["conversation_id"], "2401")
        self.assertEqual(payload["patch"]["collection_location"], "Riversdale")
        self.assertEqual(payload["patch"]["collection_time_text"], "next week")
        self.assertEqual(payload["items"][0]["item_key"], "live_stock_primary")
        self.assertEqual(payload["items"][0]["quantity"], 3)
        self.assertEqual(payload["items"][0]["category"], "Weaner")
        self.assertEqual(payload["items"][0]["weight_range"], "10_to_14_Kg")
        self.assertEqual(payload["items"][0]["sex"], "Female")

    def test_intake_write_is_disabled_by_default(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {"sales_lane": "live_stock_sales", "missing_fields": []}
        calls = []

        result = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            inbound,
            facts,
            decision,
            environ={},
            intake_writer=lambda cleaned: calls.append(cleaned),
        )

        self.assertFalse(result["attempted"])
        self.assertEqual(result["status"], "sam_live_stock_intake_write_disabled")
        self.assertEqual(calls, [])

    def test_intake_write_enabled_uses_backend_service_cleaned_payload_only(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        decision = {"sales_lane": "live_stock_sales", "missing_fields": []}
        calls = []

        def writer(cleaned):
            calls.append(cleaned)
            return {
                "success": True,
                "lookup_status": "updated",
                "intake_id": "INTAKE-1",
                "items": [{"item_key": "live_stock_primary"}],
            }

        result = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            inbound,
            facts,
            decision,
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_writer=writer,
        )

        self.assertTrue(result["attempted"])
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_intake_written")
        self.assertEqual(len(calls), 1)
        cleaned = calls[0]
        self.assertEqual(cleaned["conversation_id"], "2401")
        self.assertEqual(cleaned["patch"]["collection_location"], "Riversdale")
        self.assertEqual(cleaned["items"][0]["category"], "Weaner")
        self.assertEqual(cleaned["items"][0]["weight_range"], "10_to_14_Kg")
        self.assertEqual(cleaned["items"][0]["sex"], "Female")

    def test_handle_inbound_with_intake_write_enabled_reports_intake_write_only(self):
        writes = []

        def writer(cleaned):
            writes.append(cleaned)
            return {"success": True, "intake_id": "INTAKE-1", "items": []}

        result, status_code = sam_live_stock_runtime.handle_sam_live_stock_chatwoot_inbound(
            inbound_payload(),
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_context_loader=lambda _conversation_id: {"success": True, "known_fields": {}, "items": []},
            availability_loader=lambda: [],
            intake_writer=writer,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["writes_order_intake"])
        self.assertFalse(result["creates_order"])
        self.assertFalse(result["reserves_stock"])
        self.assertFalse(result["writes_sales_transaction"])
        self.assertFalse(result["sends_customer_message"])
        self.assertEqual(len(writes), 1)
        self.assertEqual(result["sam_decision"]["intake_write"]["status"], "sam_live_stock_intake_written")

    def test_intake_write_blocks_wrong_lane_and_breeding_stock(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(content="I want pork chops."))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        calls = []

        wrong_lane = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            inbound,
            facts,
            {"sales_lane": "meat_sales"},
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_writer=lambda cleaned: calls.append(cleaned),
        )

        self.assertFalse(wrong_lane["attempted"])
        self.assertEqual(wrong_lane["status"], "sam_live_stock_intake_wrong_lane")

        breeding_facts = sam_live_stock_runtime.extract_live_stock_facts("I want two breeding gilts", inbound)
        breeding = sam_live_stock_runtime.write_live_stock_intake_if_enabled(
            inbound,
            breeding_facts,
            {"sales_lane": "live_stock_sales"},
            environ={"SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1"},
            intake_writer=lambda cleaned: calls.append(cleaned),
        )

        self.assertFalse(breeding["attempted"])
        self.assertEqual(breeding["status"], "sam_live_stock_intake_owner_gate_breeding")
        self.assertEqual(calls, [])

    def test_match_and_draft_order_packet_are_owner_reviewable(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
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
                    "sex": "Female",
                    "status": "Active",
                    "on_farm": "Yes",
                    "reserved_status": "",
                    "available_for_sale": "Yes",
                    "sale_category": "Weaner",
                    "current_weight_kg": 13,
                },
                {
                    "pig_id": "PIG-3",
                    "sex": "Female",
                    "status": "Active",
                    "on_farm": "Yes",
                    "reserved_status": "",
                    "available_for_sale": "Yes",
                    "sale_category": "Weaner",
                    "current_weight_kg": 14,
                },
            ],
            facts,
        )

        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)

        self.assertEqual(match["match_status"], "exact_match_available")
        self.assertTrue(match["complete_fulfillment"])
        self.assertTrue(packet["draft_ready"], packet)
        self.assertTrue(packet["owner_review_required"])
        self.assertEqual(packet["order_payload"]["requested_category"], "Weaner")
        self.assertEqual(packet["order_payload"]["requested_weight_range"], "10_to_14_Kg")
        self.assertEqual(packet["order_payload"]["quoted_total"], 1500.0)
        self.assertTrue(packet["pricing"]["found"], packet["pricing"])
        self.assertEqual(packet["pricing"]["sale_category"], "Weaner Piglets")
        self.assertEqual(packet["pricing"]["unit_price"], 500.0)
        self.assertEqual(packet["sync_payload"]["requested_items"][0]["request_item_key"], "live_stock_primary")
        self.assertEqual(packet["sync_payload"]["requested_items"][0]["quantity"], 3)

    def test_draft_order_creation_is_disabled_by_default(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        calls = []

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {"sales_lane": "live_stock_sales"},
            environ={},
            draft_order_creator=lambda order_data, sync_data: calls.append((order_data, sync_data)),
        )

        self.assertFalse(result["attempted"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_create_disabled")
        self.assertEqual(calls, [])

    def test_draft_order_creation_enabled_uses_existing_create_with_lines_contract(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
                {"pig_id": "PIG-1", "sex": "Female", "status": "Active", "on_farm": "Yes", "available_for_sale": "Yes", "sale_category": "Weaner"},
                {"pig_id": "PIG-2", "sex": "Female", "status": "Active", "on_farm": "Yes", "available_for_sale": "Yes", "sale_category": "Weaner"},
                {"pig_id": "PIG-3", "sex": "Female", "status": "Active", "on_farm": "Yes", "available_for_sale": "Yes", "sale_category": "Weaner"},
            ],
            facts,
        )
        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)
        calls = []

        def creator(order_data, sync_data):
            calls.append((order_data, sync_data))
            return {
                "success": True,
                "action": "create_order_with_lines",
                "order_id": "ORD-1",
                "complete_fulfillment": True,
            }

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {"sales_lane": "live_stock_sales", "draft_order_packet": packet, "match_packet": match},
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            draft_order_creator=creator,
        )

        self.assertTrue(result["attempted"])
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_created")
        self.assertEqual(len(calls), 1)
        order_data, sync_data = calls[0]
        self.assertEqual(order_data["customer_name"], "Charl N")
        self.assertEqual(order_data["requested_category"], "Weaner")
        self.assertEqual(sync_data["requested_items"][0]["category"], "Weaner")
        self.assertEqual(sync_data["requested_items"][0]["quantity"], 3)

    def test_draft_order_not_ready_when_stock_does_not_match(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload())
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        match = sam_live_stock_runtime.build_live_stock_match_packet(
            facts,
            {"success": True, "matched_count": 0, "matched_sample": []},
        )
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)
        calls = []

        result = sam_live_stock_runtime.create_live_stock_draft_order_if_enabled(
            inbound,
            facts,
            {"sales_lane": "live_stock_sales", "draft_order_packet": packet, "match_packet": match},
            environ={"SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "1"},
            draft_order_creator=lambda order_data, sync_data: calls.append((order_data, sync_data)),
        )

        self.assertFalse(packet["draft_ready"])
        self.assertTrue(result["attempted"])
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "sam_live_stock_draft_order_not_ready")
        self.assertEqual(calls, [])

    def test_draft_order_not_ready_when_stock_is_only_partial_match(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(
            content="I need 3 female weaners around 10 to 15kg next week in Riversdale.",
        ))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)
        availability = sam_live_stock_runtime.summarize_live_stock_availability(
            [
                {"pig_id": "PIG-1", "sex": "Female", "status": "Active", "on_farm": "Yes", "available_for_sale": "Yes", "sale_category": "Weaner"},
                {"pig_id": "PIG-2", "sex": "Female", "status": "Active", "on_farm": "Yes", "available_for_sale": "Yes", "sale_category": "Weaner"},
            ],
            facts,
        )
        match = sam_live_stock_runtime.build_live_stock_match_packet(facts, availability)
        packet = sam_live_stock_runtime.build_live_stock_draft_order_packet(inbound, facts, match)

        self.assertEqual(match["match_status"], "partial_match_available")
        self.assertFalse(match["complete_fulfillment"])
        self.assertTrue(match["partial_fulfillment"])
        self.assertFalse(packet["draft_ready"], packet)
        self.assertEqual(packet["stock_gate"], "partial_matching_stock")

    def test_reservation_followup_detects_keep_those_and_weekday(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Can you keep those 2 weaners for me until Friday?",
        ))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)

        self.assertEqual(facts["quantity"], 2)
        self.assertEqual(facts["category"], "weaner")
        self.assertEqual(facts["timing"], "friday")
        self.assertTrue(facts["reservation_requested"])

    def test_live_pig_weight_range_infers_grower_category(self):
        inbound = sam_live_stock_runtime.parse_chatwoot_inbound(inbound_payload(
            content="Not meat, I want live pigs to raise, 2 males around 30kg in Albertinia.",
        ))
        facts = sam_live_stock_runtime.extract_live_stock_facts(inbound["content"], inbound)

        self.assertEqual(facts["category"], "grower")
        self.assertEqual(facts["quantity"], 2)
        self.assertEqual(facts["sex"], "male")
        self.assertEqual(facts["location"], "Albertinia")

    def test_owner_action_packet_exposes_routes_without_auto_authority(self):
        packet = sam_live_stock_runtime.build_live_stock_owner_action_packet(
            order_id="ORD-1",
            conversation_id="1774",
            document_id="DOC-1",
        )

        self.assertTrue(packet["owner_gate_required"])
        self.assertFalse(packet["reservation"]["allowed_for_sam_auto"])
        self.assertEqual(packet["reservation"]["route"], "/api/orders/ORD-1/reserve")
        self.assertFalse(packet["quote_send_confirmed"]["allowed_for_sam_auto"])
        self.assertIn("quote/send-latest-confirmed", packet["quote_send_confirmed"]["route"])

    def test_smoke_pack_and_go_live_checklist_expose_launch_gates(self):
        smoke = sam_live_stock_runtime.build_sam_live_stock_smoke_pack()
        checklist = sam_live_stock_runtime.build_sam_live_stock_go_live_checklist(environ={
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_WEBHOOK_TOKEN": "test-sam-live-stock-token-32-chars",
            "SAM_LIVE_STOCK_BACKEND_INTAKE_WRITE_ENABLED": "1",
            "SAM_LIVE_STOCK_BACKEND_DRAFT_ORDER_CREATE_ENABLED": "0",
            "SAM_LIVE_STOCK_BACKEND_AUTOREPLY_ENABLED": "0",
            "SAM_LIVE_STOCK_BACKEND_LLM_ENABLED": "0",
        })

        self.assertEqual(smoke["required_pass_rate"], "100%")
        self.assertGreaterEqual(smoke["scenario_count"], 6)
        self.assertIn("no reservation without owner action", smoke["must_verify"])
        self.assertEqual(checklist["blockers"], [])
        self.assertTrue(checklist["ready_for_controlled_smoke"])
        self.assertFalse(checklist["ready_for_public_launch"])

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
