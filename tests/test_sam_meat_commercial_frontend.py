import unittest
from pathlib import Path


class SamMeatCommercialFrontendTests(unittest.TestCase):
    def test_owner_leads_page_exposes_current_commercial_truth(self):
        template = Path("templates/meat-sales-leads.html").read_text(encoding="utf-8")
        self.assertIn("Set A - Amadeus Signature", template)
        self.assertIn("Set B - Amadeus Ember", template)
        self.assertIn("Set C - Amadeus Grand Cut", template)
        self.assertIn("Set D is historical only", template)
        self.assertIn("R130/kg including VAT", template)
        self.assertIn("50% estimated deposit", template)
        self.assertIn("delivery only", template)
        self.assertIn("transport packaging remain unresolved", template)
        self.assertIn("bank-confirmed deposit", template)

    def test_owner_reference_page_uses_authoritative_sources(self):
        template = Path("templates/meat-sales-reference.html").read_text(encoding="utf-8")
        for label in (
            "Set A: Amadeus Signature Collection",
            "Set B: Amadeus Ember Collection",
            "Set C: Amadeus Grand Cut Collection",
            "Set D: historical only",
            "R130/kg including VAT",
            "50% deposit",
            "POP is not payment",
            "external_sources/AMADEUS_HALF_CARCASS_CUTTING_STANDARD_v1.0.md",
            "docs/09-vault-brain/03-business/MEAT_SALES.md",
        ):
            self.assertIn(label, template)
        self.assertIn("both halves may use the same or different collections", template)
        self.assertIn("Balance must clear before delivery", template)

    def test_runtime_menu_is_sourced_from_current_commercial_standard(self):
        runtime = Path("modules/sales/sam_meat_runtime.py").read_text(encoding="utf-8")
        self.assertIn(
            "from modules.sales.sam_meat_commercial_standard import COLLECTIONS",
            runtime,
        )
        self.assertIn("CUT_SET_MENU = {code: collection_description(code) for code in COLLECTIONS}", runtime)
        self.assertNotIn('"Set D": "Slow-Cook', runtime)


if __name__ == "__main__":
    unittest.main()
