import unittest
from dataclasses import FrozenInstanceError

from modules.documents.catalogue import (
    CATALOGUE, Requester, RequesterRole, Support, get_document,
    governed_print_extension_candidates, require_delivery_support,
    require_generator, require_requester,
)


class DocumentCatalogueTests(unittest.TestCase):
    def test_identities_are_unique_and_mapping_is_immutable(self):
        self.assertEqual(len(CATALOGUE), len(set(CATALOGUE)))
        with self.assertRaises(TypeError):
            CATALOGUE["duplicate"] = next(iter(CATALOGUE.values()))
        with self.assertRaises(FrozenInstanceError):
            get_document("farm.weekly_weight_sheet.v1").generator_id = "other"

    def test_required_inputs_and_roles_are_explicit(self):
        for document in CATALOGUE.values():
            self.assertTrue(document.requester_roles)
            self.assertTrue(document.requesters)
            self.assertTrue(all(field.name and field.description for field in document.required_inputs))
            self.assertTrue(document.audit_fields)
            self.assertTrue(document.idempotency_key_fields)
            mandatory = {"authenticated_principal_id", "requester", "document_id", "canonical_input_ids", "generator_id", "channel", "requested_revision"}
            self.assertTrue(mandatory.issubset(document.idempotency_key_fields))
            if document.telegram_delivery is Support.SUPPORTED:
                self.assertIn("recipient_binding", document.idempotency_key_fields)
                self.assertTrue(document.telegram_recipient_binding_required)
        self.assertIn(RequesterRole.FARM_MANAGER, get_document("farm.weekly_weight_sheet.v1").requester_roles)
        self.assertNotIn(RequesterRole.FARM_MANAGER, get_document("sales.quote.v1").requester_roles)
        require_requester("farm.weekly_weight_sheet.v1", RequesterRole.FARM_MANAGER, Requester.OOM_SAKKIE)
        with self.assertRaises(PermissionError):
            require_requester("sales.quote.v1", RequesterRole.FARM_MANAGER, Requester.OOM_SAKKIE)

    def test_unsupported_and_unknown_delivery_fail_closed(self):
        with self.assertRaises(PermissionError):
            require_delivery_support("farm.weekly_weight_sheet.v1", "telegram")
        with self.assertRaises(PermissionError):
            require_delivery_support("sales.loading_sheet.v1", "direct_print")
        with self.assertRaises(PermissionError):
            require_delivery_support("sales.loading_sheet.v1", "carrier_pigeon")

    def test_green_weekly_print_is_supported_and_other_pdfs_reuse_extension_inventory(self):
        require_delivery_support("farm.weekly_weight_sheet.v1", "direct_print")
        candidates={document.document_id for document in governed_print_extension_candidates()}
        self.assertEqual(candidates,{"sales.loading_sheet.v1",
            "sales.removal_transport.v1","sales.health_declaration.v1",
            "sales.quote.v1"})

    def test_catalogue_has_no_effect_capability(self):
        forbidden = {"generate", "send", "deliver", "print", "write", "execute"}
        for document in CATALOGUE.values():
            self.assertFalse(any(callable(getattr(document, name, None)) for name in forbidden))
            self.assertIsInstance(document.generator_id, str)

    def test_adapter_cannot_silently_change_generator(self):
        document = get_document("sales.loading_sheet.v1")
        self.assertEqual(document.generator_id, require_generator(document.document_id, document.generator_id))
        with self.assertRaises(PermissionError):
            require_generator(document.document_id, "modules.other.generate")

    def test_unknown_facts_remain_unknown(self):
        loading = get_document("sales.loading_sheet.v1")
        health = get_document("sales.health_declaration.v1")
        self.assertIs(loading.preview.support, Support.UNKNOWN)
        self.assertIs(loading.direct_print, Support.UNKNOWN)
        self.assertEqual(loading.preview.support.value, "Unknown")
        self.assertIn("Unknown", health.evidence_source)
        self.assertEqual(health.optional_filters, ())


if __name__ == "__main__":
    unittest.main()
