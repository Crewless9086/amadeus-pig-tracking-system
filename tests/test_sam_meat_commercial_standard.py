import unittest

from modules.sales.sam_meat_commercial_standard import (
    COLLECTIONS, build_estimated_quote_preview, commercial_authority,
)
from modules.sales.sam_meat_launch_readiness import build_sam_meat_launch_packet
from modules.sales.sam_meat_runtime import CUT_SET_MENU


def truth_reader(name, data=None):
    return lambda **_: {"usable": True, "status": "verified", "freshness": "current", "data": data or {}}


class SamMeatCommercialStandardTests(unittest.TestCase):
    def test_only_three_current_collections_are_exposed(self):
        self.assertEqual(list(COLLECTIONS), ["Set A", "Set B", "Set C"])
        self.assertEqual(set(CUT_SET_MENU), set(COLLECTIONS))
        self.assertIn("Amadeus Grand Cut Collection", CUT_SET_MENU["Set C"])
        self.assertNotIn("Set D", CUT_SET_MENU)

    def test_estimate_requires_bound_packed_weight_evidence(self):
        blocked = build_estimated_quote_preview(packed_weight_kg=42, weight_evidence_id="")
        self.assertEqual(blocked["status"], "Unavailable")
        self.assertIsNone(blocked["estimated_total"])
        ready = build_estimated_quote_preview(packed_weight_kg=42, weight_evidence_id="BATCH-42")
        self.assertEqual(ready["estimated_total"], 5460.0)
        self.assertEqual(ready["estimated_deposit"], 2730.0)
        self.assertIsNone(ready["final_total"])
        self.assertFalse(ready["binding_quote_created"])

    def test_maggy_production_shaped_packet_is_prepare_only(self):
        readers = {
            "catalogue": truth_reader("catalogue", {"products": ["full carcass"], "packs": ["Set A", "Set B", "Set C"]}),
            "pricing": truth_reader("pricing", {"entries": [{"product_type": "full_carcass", "cut_set": "Set C", "price_amount": 130, "price_unit": "kg", "status": "active", "effective_from": "2026-07-01T00:00:00Z", "price_book_id": "PRICE-BOOK-FULL", "yield_basis": "Estimated packed full-carcass weight: 38-42kg"}]}),
            "availability": truth_reader("availability"),
            "fulfilment": truth_reader("fulfilment"),
            "butcher": truth_reader("butcher"),
        }
        packet = build_sam_meat_launch_packet(
            [{"message_id": "MAGGY-0", "content": "I am interested in a full carcass"}, {"message_id": "MAGGY-1", "content": "Amadeus Grand cut collection What is the price"}],
            conversation_ref="2033", truth_readers=readers, now="2026-07-27T12:00:00Z",
        )
        self.assertEqual(packet["facts"]["cut_set"], "Set C")
        self.assertEqual(packet["commercial_offer"]["price_per_kg_including_vat"], 130.0)
        self.assertFalse(packet["commercial_offer"]["collection_offered"])
        self.assertEqual(packet["estimated_quote_preview"]["estimated_total_range"], [4940.0, 5460.0])
        self.assertEqual(packet["next_missing_field"], "full_carcass_choices_and_town")
        self.assertIn("R130/kg including VAT", packet["prepared_reply"])
        self.assertIn("R4,940-R5,460", packet["prepared_reply"])
        self.assertIn("both halves", packet["prepared_reply"])
        self.assertIn("Delivery fee and timing still need confirmation", packet["prepared_reply"])
        self.assertTrue(all(value is False for value in commercial_authority().values()))

    def test_full_carcass_halves_and_afrikaans_spelling_are_retained(self):
        readers = {name: truth_reader(name, {"products": ["full carcass"]} if name == "catalogue" else {}) for name in ("catalogue", "pricing", "availability", "fulfilment", "butcher")}
        packet = build_sam_meat_launch_packet([
            {"message_id": "A1", "content": "Ek wil 'n hele karkas, Grand Kut."},
            {"message_id": "A2", "content": "Helfte een Stel A en helfte twee Stel C."},
        ], conversation_ref="AF-1", truth_readers=readers)
        self.assertEqual(packet["language"], "af")
        self.assertEqual(packet["facts"]["cut_set"], "Set C")
        self.assertEqual(packet["facts"]["cut_set_half_1"], "Set A")
        self.assertEqual(packet["facts"]["cut_set_half_2"], "Set C")
        self.assertNotIn("full_carcass_half_choices", packet["missing_facts"])

    def test_range_estimate_uses_bound_evidence_without_final_total(self):
        preview = build_estimated_quote_preview(packed_weight_kg="38-42kg", weight_evidence_id="PRICE-BOOK-FULL")
        self.assertEqual(preview["estimated_total_range"], [4940.0, 5460.0])
        self.assertEqual(preview["estimated_deposit_range"], [2470.0, 2730.0])
        self.assertIsNone(preview["final_total"])
    def test_live_weight_reference_is_not_misread_as_packed_weight(self):
        preview = build_estimated_quote_preview(
            packed_weight_kg=(
                "Estimated packed full-carcass weight from 60kg live pig: "
                "38-42kg; final amount uses actual packed weight."
            ),
            weight_evidence_id="PRICE-BOOK-FULL",
        )
        self.assertEqual(preview["packed_weight_range_kg"], [38.0, 42.0])
        self.assertEqual(preview["estimated_total_range"], [4940.0, 5460.0])

    def test_unlabelled_multiple_numbers_do_not_create_an_estimate(self):
        preview = build_estimated_quote_preview(
            packed_weight_kg="60 live, expected 38 and 42 packed",
            weight_evidence_id="PRICE-BOOK-FULL",
        )
        self.assertEqual(preview["status"], "Unavailable")
        self.assertIsNone(preview["estimated_total"])
    def test_missing_weight_never_becomes_zero_quote(self):
        readers = {name: truth_reader(name, {"products": ["full carcass"]} if name == "catalogue" else {}) for name in ("catalogue", "pricing", "availability", "fulfilment", "butcher")}
        packet = build_sam_meat_launch_packet([{"message_id": "M-1", "content": "I want a full carcass Set C"}], conversation_ref="2033", truth_readers=readers)
        self.assertEqual(packet["estimated_quote_preview"]["status"], "Unavailable")
        self.assertIsNone(packet["estimated_quote_preview"]["estimated_total"])


if __name__ == "__main__":
    unittest.main()
