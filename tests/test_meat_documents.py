import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from modules.sales import meat_documents


class MeatDocumentTests(unittest.TestCase):
    def setUp(self):
        self.env = {
            "MEAT_SALES_VAT_NUMBER": "4510286224",
            "MEAT_SALES_VAT_RATE": "0.15",
            "BANK_ACCOUNT_NAME": "Amadeus Farm",
            "BANK_NAME": "Test Bank",
            "BANK_ACCOUNT_NUMBER": "1234567890",
            "BANK_BRANCH_CODE": "250655",
            "BANK_ACCOUNT_TYPE": "Business account",
        }

    def test_vat_inclusive_estimate_splits_vat_and_deposit(self):
        totals = meat_documents.calculate_estimated_quote_totals(
            price_per_kg=130,
            estimated_weight_kg=25,
            deposit_percent=50,
            vat_rate=0.15,
        )

        self.assertEqual(totals["total_including_vat"], 3250.00)
        self.assertEqual(totals["subtotal_ex_vat"], 2826.09)
        self.assertEqual(totals["vat_amount"], 423.91)
        self.assertEqual(totals["deposit_due"], 1625.00)
        self.assertEqual(totals["estimated_balance_before_delivery"], 1625.00)
        self.assertEqual(totals["delivery_fee_label"], "To be confirmed")

    def test_final_invoice_uses_actual_weight_and_bank_confirmed_deposit(self):
        totals = meat_documents.calculate_final_invoice_totals(
            price_per_kg=130,
            actual_weight_kg=24.8,
            deposit_confirmed=1625,
            vat_rate=0.15,
        )

        self.assertEqual(totals["final_meat_total"], 3224.00)
        self.assertEqual(totals["subtotal_ex_vat"], 2803.48)
        self.assertEqual(totals["vat_amount"], 420.52)
        self.assertEqual(totals["balance_due"], 1599.00)

    def test_quote_safe_gate_blocks_cash_and_placeholder_bank_details(self):
        bank = meat_documents.bank_details({
            "BANK_ACCOUNT_NAME": "Amadeus Farm",
            "BANK_NAME": "Bank",
            "BANK_ACCOUNT_NUMBER": "[Account Number]",
            "BANK_BRANCH_CODE": "250655",
        })
        safe, blockers = meat_documents.quote_safe_gate(
            {
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "price_per_kg": 130,
                "estimated_weight_kg": 25,
                "deposit_percent": 50,
                "delivery_mode": "delivery",
                "payment_method": "CASH",
            },
            bank,
        )

        self.assertFalse(safe)
        self.assertIn("pilot_is_eft_only", blockers)
        self.assertIn("bank_details_required", blockers)
        self.assertIn("bank_details_placeholder_values", blockers)

    def test_estimated_quote_packet_is_quote_safe_with_complete_eft_facts(self):
        lead = {
            "lead_id": "OSK-SALES-LEAD-TEST",
            "lead_label": "Charl Test",
            "contact_label": "Charl Test",
            "channel": "chatwoot_whatsapp",
            "interest": {
                "product_type": "half_carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
                "delivery_town": "Riversdale",
                "delivery_or_collection": "delivery",
                "delivery_address_line_1": "12 Test Street",
                "payment_method": "EFT",
            },
        }
        contract = {
            "contract_status": "owner_money_path_ready",
            "lead_summary": {
                "buyer_or_contact": "Charl Test",
                "product": "Half Carcass",
                "cut_set": "Set A",
                "location": "Riversdale",
            },
            "required_before_money_path": {
                "delivery_or_collection": "delivery",
                "payment_method": "EFT",
                "estimated_weight_or_size": "25kg",
                "deposit_amount_or_rule": "50% deposit to confirm",
            },
        }

        packet = meat_documents.build_estimated_quote_packet_from_contract(
            lead,
            contract,
            meat_documents.DEFAULT_MEAT_PRICE_BOOK,
            {"lead_id": "OSK-SALES-LEAD-TEST"},
            environ=self.env,
        )

        self.assertTrue(packet["quote_safe"])
        self.assertEqual(packet["status"], "quote_safe")
        self.assertEqual(packet["product"]["price_per_kg_vat_inclusive"], 130)
        self.assertEqual(packet["totals"]["deposit_due"], 1625.00)
        self.assertEqual(packet["vat"]["vat_number"], "4510286224")
        self.assertEqual(packet["document"]["payment_reference"], "TEST")
        self.assertIn("preparing your estimated quote", packet["sam_preparing_message"])

    def test_payment_reference_uses_last_six_order_suffix_characters(self):
        self.assertEqual(meat_documents.payment_reference("ORD-2026-A99273"), "A99273")
        self.assertEqual(meat_documents.payment_reference("MEAT-2026-1234567"), "234567")
        self.assertEqual(meat_documents.payment_reference("OSK-SALES-LEAD-D583E2649366146A"), "66146A")

    def test_render_estimated_quote_pdf_creates_file(self):
        packet = meat_documents.build_estimated_quote_packet_from_contract(
            {
                "lead_id": "OSK-SALES-LEAD-TEST",
                "lead_label": "Charl Test",
                "channel": "chatwoot_whatsapp",
                "interest": {"product_type": "half_carcass", "cut_set": "Set A", "payment_method": "EFT"},
            },
            {
                "lead_summary": {"buyer_or_contact": "Charl Test", "cut_set": "Set A", "location": "Riversdale"},
                "required_before_money_path": {
                    "delivery_or_collection": "delivery",
                    "payment_method": "EFT",
                    "estimated_weight_or_size": "25kg",
                    "deposit_amount_or_rule": "50%",
                },
            },
            meat_documents.DEFAULT_MEAT_PRICE_BOOK,
            {"lead_id": "OSK-SALES-LEAD-TEST"},
            environ=self.env,
        )
        with tempfile.TemporaryDirectory() as tmp_dir:
            output = Path(tmp_dir) / "estimated_quote.pdf"
            rendered = meat_documents.render_meat_document_pdf(packet, output_path=output, environ=self.env)

            self.assertTrue(rendered.exists())
            self.assertGreater(rendered.stat().st_size, 1000)

    def test_deposit_pro_forma_packet_renders_from_quote_packet(self):
        quote_packet = meat_documents.build_estimated_quote_packet_from_contract(
            {
                "lead_id": "OSK-SALES-LEAD-TEST",
                "lead_label": "Charl Test",
                "interest": {"product_type": "half_carcass", "cut_set": "Set A", "payment_method": "EFT"},
            },
            {
                "lead_summary": {"buyer_or_contact": "Charl Test", "cut_set": "Set A", "location": "Riversdale"},
                "required_before_money_path": {
                    "delivery_or_collection": "delivery",
                    "payment_method": "EFT",
                    "estimated_weight_or_size": "25kg",
                    "deposit_amount_or_rule": "50%",
                },
            },
            meat_documents.DEFAULT_MEAT_PRICE_BOOK,
            {"lead_id": "OSK-SALES-LEAD-TEST"},
            environ=self.env,
        )
        packet = meat_documents.build_deposit_pro_forma_packet(quote_packet)

        self.assertEqual(packet["document"]["document_type"], "Deposit Pro Forma")
        self.assertEqual(packet["totals"]["amount_due_now"], 1625.00)

        with tempfile.TemporaryDirectory() as tmp_dir:
            rendered = meat_documents.render_meat_document_pdf(
                packet,
                output_path=Path(tmp_dir) / "deposit_pro_forma.pdf",
                environ=self.env,
            )
            self.assertTrue(rendered.exists())
            self.assertGreater(rendered.stat().st_size, 1000)

    def test_final_invoice_packet_builds_from_reconciliation(self):
        with patch.object(meat_documents, "get_meat_reconciliation_status") as reconciliation:
            reconciliation.return_value = ({
                "success": True,
                "reconciliation": {
                    "actual_packed_weight_kg": 24.8,
                    "price_per_kg": 130,
                    "deposit_confirmed_amount": 1625,
                    "payment_reference": "A99273",
                },
            }, 200)

            packet, status = meat_documents.build_final_invoice_packet_from_reconciliation(
                "OSK-SALES-LEAD-TEST",
                environ=self.env,
            )

        self.assertEqual(status, 200)
        self.assertEqual(packet["document"]["document_type"], "Final Invoice")
        self.assertEqual(packet["totals"]["balance_due"], 1599.00)

    def test_route_builder_returns_blocked_when_bank_envs_are_placeholders(self):
        with patch.object(meat_documents, "get_sales_lead_preorder_contract") as contract, \
             patch.object(meat_documents, "list_meat_price_book_entries") as prices:
            contract.return_value = ({
                "success": True,
                "lead": {
                    "lead_id": "OSK-SALES-LEAD-TEST",
                    "interest": {
                        "product_type": "half_carcass",
                        "cut_set": "Set A",
                        "delivery_or_collection": "delivery",
                        "payment_method": "EFT",
                    },
                },
                "contract": {
                    "lead_summary": {"buyer_or_contact": "Charl Test", "cut_set": "Set A", "location": "Riversdale"},
                    "required_before_money_path": {
                        "delivery_or_collection": "delivery",
                        "payment_method": "EFT",
                        "estimated_weight_or_size": "25kg",
                        "deposit_amount_or_rule": "50%",
                    },
                },
            }, 200)
            prices.return_value = ({
                "success": True,
                "price_entries": meat_documents.DEFAULT_MEAT_PRICE_BOOK,
            }, 200)
            env = dict(self.env)
            env["BANK_ACCOUNT_NUMBER"] = "[Account Number]"

            packet, status = meat_documents.build_meat_estimated_quote_packet(
                "OSK-SALES-LEAD-TEST",
                environ=env,
            )

        self.assertEqual(status, 409)
        self.assertFalse(packet["quote_safe"])
        self.assertIn("bank_details_placeholder_values", packet["blockers"])

    def test_send_estimated_quote_requires_autosend_enabled(self):
        packet, status = meat_documents.send_meat_estimated_quote_to_chatwoot(
            "OSK-SALES-LEAD-TEST",
            environ=self.env,
        )

        self.assertEqual(status, 409)
        self.assertFalse(packet["sent"])
        self.assertEqual(packet["status"], "meat_sales_document_autosend_disabled")

    def test_send_estimated_quote_to_chatwoot_generates_pdf_and_calls_sender(self):
        env = dict(self.env)
        env["MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED"] = "1"
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch.object(meat_documents, "get_sales_lead_preorder_contract") as contract, \
             patch.object(meat_documents, "list_meat_price_book_entries") as prices, \
             patch.object(meat_documents, "record_sales_lead_event") as record_event:
            env["MEAT_SALES_DOCUMENT_OUTPUT_DIR"] = tmp_dir
            contract.return_value = (self._contract_fixture(), 200)
            prices.return_value = ({"success": True, "price_entries": meat_documents.DEFAULT_MEAT_PRICE_BOOK}, 200)
            record_event.return_value = ({"success": True, "event_id": "E1"}, 201)
            sender = Mock(return_value={"status_code": 200, "message_id": "M1", "conversation_id": "1808"})

            result, status = meat_documents.send_meat_estimated_quote_to_chatwoot(
                "OSK-SALES-LEAD-TEST",
                environ=env,
                chatwoot_sender=sender,
            )
            file_exists = Path(result["file_path"]).exists()

        self.assertEqual(status, 200)
        self.assertFalse(result["sent"])
        self.assertTrue(result["chatwoot_accepted"])
        self.assertEqual(result["delivery_status"], "chatwoot_accepted_unverified")
        self.assertEqual(result["status"], "estimated_quote_chatwoot_accepted_unverified")
        self.assertTrue(file_exists)
        sender.assert_called_once()
        self.assertEqual(sender.call_args.args[0], "1808")
        self.assertIn("estimated pork quote", sender.call_args.args[1])
        self.assertEqual(sender.call_args.args[2], Path(result["file_path"]))
        self.assertTrue(result["sends_customer_message"])
        self.assertTrue(result["calls_chatwoot"])
        event_types = [call.args[1]["event_type"] for call in record_event.call_args_list]
        self.assertIn("estimated_quote_send_attempted", event_types)
        self.assertIn("estimated_quote_chatwoot_accepted", event_types)

    def test_send_estimated_quote_marks_sent_only_when_delivery_confirmed(self):
        env = dict(self.env)
        env["MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED"] = "1"
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch.object(meat_documents, "get_sales_lead_preorder_contract") as contract, \
             patch.object(meat_documents, "list_meat_price_book_entries") as prices, \
             patch.object(meat_documents, "record_sales_lead_event") as record_event:
            env["MEAT_SALES_DOCUMENT_OUTPUT_DIR"] = tmp_dir
            contract.return_value = (self._contract_fixture(), 200)
            prices.return_value = ({"success": True, "price_entries": meat_documents.DEFAULT_MEAT_PRICE_BOOK}, 200)
            record_event.return_value = ({"success": True, "event_id": "E1"}, 201)
            sender = Mock(return_value={
                "status_code": 200,
                "message_id": "M1",
                "conversation_id": "1808",
                "delivery_status": "delivered",
            })

            result, status = meat_documents.send_meat_estimated_quote_to_chatwoot(
                "OSK-SALES-LEAD-TEST",
                environ=env,
                chatwoot_sender=sender,
            )

        self.assertEqual(status, 200)
        self.assertTrue(result["sent"])
        self.assertEqual(result["delivery_status"], "delivered")
        self.assertTrue(result["delivery_confirmed"])
        event_types = [call.args[1]["event_type"] for call in record_event.call_args_list]
        self.assertIn("estimated_quote_sent", event_types)

    def test_send_estimated_quote_requires_template_when_whatsapp_window_is_stale(self):
        env = dict(self.env)
        env["MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED"] = "1"
        env["MEAT_SALES_QUOTE_READY_TEMPLATE_NAME"] = "amadeus_quote_ready"
        fixture = self._contract_fixture()
        fixture["lead"]["last_inbound_at"] = "2020-01-01T01:07:06+00:00"
        with patch.object(meat_documents, "get_sales_lead_preorder_contract") as contract, \
             patch.object(meat_documents, "list_meat_price_book_entries") as prices, \
             patch.object(meat_documents, "record_sales_lead_event") as record_event:
            contract.return_value = (fixture, 200)
            prices.return_value = ({"success": True, "price_entries": meat_documents.DEFAULT_MEAT_PRICE_BOOK}, 200)
            record_event.return_value = ({"success": True, "event_id": "E1"}, 201)
            sender = Mock()

            result, status = meat_documents.send_meat_estimated_quote_to_chatwoot(
                "OSK-SALES-LEAD-TEST",
                environ=env,
                chatwoot_sender=sender,
            )

        self.assertEqual(status, 409)
        self.assertFalse(result["sent"])
        self.assertEqual(result["status"], "estimated_quote_template_required")
        self.assertTrue(result["template_required"])
        self.assertEqual(result["template_packet"]["template"]["name"], "amadeus_quote_ready")
        sender.assert_not_called()
        event_types = [call.args[1]["event_type"] for call in record_event.call_args_list]
        self.assertIn("estimated_quote_template_required", event_types)

    def test_send_estimated_quote_uses_recent_sam_fact_event_for_whatsapp_window(self):
        env = dict(self.env)
        env["MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED"] = "1"
        fixture = self._contract_fixture()
        fixture["lead"]["last_inbound_at"] = "2020-01-01T01:07:06+00:00"
        fixture["lead"]["events"] = [{
            "event_type": "status_observed",
            "recorded_by": "sam_meat_intake",
            "created_at": "2099-06-19T01:00:00+00:00",
            "notes": '{"source":"sam_meat_intake","kind":"fact_snapshot"}',
        }]
        with tempfile.TemporaryDirectory() as tmp_dir, \
             patch.object(meat_documents, "get_sales_lead_preorder_contract") as contract, \
             patch.object(meat_documents, "list_meat_price_book_entries") as prices, \
             patch.object(meat_documents, "record_sales_lead_event") as record_event:
            env["MEAT_SALES_DOCUMENT_OUTPUT_DIR"] = tmp_dir
            contract.return_value = (fixture, 200)
            prices.return_value = ({"success": True, "price_entries": meat_documents.DEFAULT_MEAT_PRICE_BOOK}, 200)
            record_event.return_value = ({"success": True, "event_id": "E1"}, 201)
            sender = Mock(return_value={"status_code": 200, "message_id": "M1", "conversation_id": "1808"})

            result, status = meat_documents.send_meat_estimated_quote_to_chatwoot(
                "OSK-SALES-LEAD-TEST",
                environ=env,
                chatwoot_sender=sender,
            )

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "estimated_quote_chatwoot_accepted_unverified")
        sender.assert_called_once()

    def test_send_estimated_quote_blocks_duplicate_without_force_resend(self):
        env = dict(self.env)
        env["MEAT_SALES_DOCUMENT_AUTOSEND_ENABLED"] = "1"
        sent_ref = meat_documents._document_ref("MQ", "TEST")
        fixture = self._contract_fixture()
        fixture["lead"]["events"] = [{
            "event_type": "estimated_quote_sent",
            "notes": '{"document_ref":"' + sent_ref + '"}',
        }]
        with patch.object(meat_documents, "get_sales_lead_preorder_contract") as contract, \
             patch.object(meat_documents, "list_meat_price_book_entries") as prices:
            contract.return_value = (fixture, 200)
            prices.return_value = ({"success": True, "price_entries": meat_documents.DEFAULT_MEAT_PRICE_BOOK}, 200)

            result, status = meat_documents.send_meat_estimated_quote_to_chatwoot(
                "OSK-SALES-LEAD-TEST",
                environ=env,
            )

        self.assertEqual(status, 200)
        self.assertFalse(result["sent"])
        self.assertEqual(result["status"], "estimated_quote_send_already_recorded")

    def test_delivery_webhook_authorization_requires_enabled_long_token(self):
        allowed, denied = meat_documents.authorize_meat_document_delivery_webhook(
            {"Authorization": "Bearer abc"},
            {},
            environ={"MEAT_SALES_DELIVERY_WEBHOOK_ENABLED": "1", "MEAT_SALES_DELIVERY_WEBHOOK_TOKEN": "short"},
        )

        self.assertFalse(allowed)
        self.assertEqual(denied["status"], "meat_sales_delivery_webhook_token_too_short")

    def test_delivery_webhook_normalizes_nested_delivered_payload(self):
        payload = {
            "event": "message_updated",
            "message": {
                "id": 123,
                "message_type": "outgoing",
                "status": "delivered",
                "content": "Here is your estimated pork quote MQ-2026-A99273",
                "conversation": {"id": 1808},
            },
        }

        normalized = meat_documents.normalize_meat_document_delivery_status_payload(payload)

        self.assertTrue(normalized["processable"])
        self.assertEqual(normalized["conversation_id"], "1808")
        self.assertEqual(normalized["message_id"], "123")
        self.assertEqual(normalized["document_ref"], "MQ-2026-A99273")
        self.assertEqual(normalized["delivery_status"], "delivered")
        self.assertTrue(normalized["delivery_confirmed"])

    def test_delivery_webhook_records_failed_event_for_explicit_lead(self):
        with patch.object(meat_documents, "get_sales_lead_preorder_contract") as contract, \
             patch.object(meat_documents, "record_sales_lead_event") as record_event:
            contract.return_value = (self._contract_fixture(), 200)
            record_event.return_value = ({"success": True, "event_id": "E1"}, 201)

            result, status = meat_documents.handle_meat_document_delivery_status_webhook({
                "lead_id": "OSK-SALES-LEAD-TEST",
                "conversation_id": "1808",
                "message_id": "M1",
                "document_ref": "MQ-2026-A99273",
                "status": "failed",
                "message_type": "outgoing",
            })

        self.assertEqual(status, 201)
        self.assertTrue(result["processed"])
        self.assertEqual(result["status"], "estimated_quote_delivery_failed")
        self.assertTrue(result["delivery_failed"])
        record_event.assert_called_once()
        self.assertEqual(record_event.call_args.args[1]["event_type"], "estimated_quote_delivery_failed")

    def test_delivery_webhook_maps_conversation_to_active_lead(self):
        fixture = self._contract_fixture()
        with patch.object(meat_documents, "get_active_sales_lead_by_conversation") as active_lead, \
             patch.object(meat_documents, "record_sales_lead_event") as record_event:
            active_lead.return_value = ({"success": True, "lead": fixture["lead"]}, 200)
            record_event.return_value = ({"success": True, "event_id": "E1"}, 201)

            result, status = meat_documents.handle_meat_document_delivery_status_webhook({
                "conversation": {"id": "1808"},
                "message": {"id": "M1", "message_status": "read", "message_type": "outgoing"},
                "document_ref": "MQ-2026-A99273",
            })

        self.assertEqual(status, 201)
        self.assertEqual(result["lead_id"], "OSK-SALES-LEAD-TEST")
        self.assertEqual(result["status"], "estimated_quote_delivery_read")
        active_lead.assert_called_once_with("1808", database_url=None)

    def test_delivery_webhook_deduplicates_same_message_status(self):
        fixture = self._contract_fixture()
        fixture["lead"]["events"] = [{
            "event_type": "estimated_quote_delivery_delivered",
            "notes": '{"delivery_status":"delivered","document_ref":"MQ-2026-A99273","message_id":"M1"}',
        }]
        with patch.object(meat_documents, "get_sales_lead_preorder_contract") as contract, \
             patch.object(meat_documents, "record_sales_lead_event") as record_event:
            contract.return_value = (fixture, 200)

            result, status = meat_documents.handle_meat_document_delivery_status_webhook({
                "lead_id": "OSK-SALES-LEAD-TEST",
                "conversation_id": "1808",
                "message_id": "M1",
                "document_ref": "MQ-2026-A99273",
                "delivery_status": "delivered",
                "message_type": "outgoing",
            })

        self.assertEqual(status, 200)
        self.assertFalse(result["processed"])
        self.assertEqual(result["status"], "delivery_status_already_recorded")
        record_event.assert_not_called()

    def _contract_fixture(self):
        return {
            "success": True,
            "lead": {
                "lead_id": "OSK-SALES-LEAD-TEST",
                "lead_label": "Charl Test",
                "contact_label": "Charl Test",
                "channel": "chatwoot_whatsapp",
                "chatwoot_conversation_id": "1808",
                "whatsapp_window_state": "open",
                "last_inbound_at": "2099-06-19T01:00:00+00:00",
                "interest": {
                    "product_type": "half_carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                    "delivery_town": "Riversdale",
                    "delivery_or_collection": "delivery",
                    "delivery_address_line_1": "12 Test Street",
                    "payment_method": "EFT",
                },
            },
            "contract": {
                "contract_status": "owner_money_path_ready",
                "lead_summary": {
                    "buyer_or_contact": "Charl Test",
                    "product": "Half Carcass",
                    "cut_set": "Set A",
                    "location": "Riversdale",
                },
                "required_before_money_path": {
                    "delivery_or_collection": "delivery",
                    "payment_method": "EFT",
                    "estimated_weight_or_size": "25kg",
                    "deposit_amount_or_rule": "50% deposit to confirm",
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
