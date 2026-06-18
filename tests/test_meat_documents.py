import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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


if __name__ == "__main__":
    unittest.main()
