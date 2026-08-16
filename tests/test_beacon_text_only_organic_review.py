import copy
from datetime import datetime, timezone
import unittest

from modules.beacon.text_only_organic_review import (
    AUTHORITY, PACKET_CLASS, UNKNOWN_MEASURES,
    build_text_only_execution_packet, build_text_only_owner_review,
    validate_text_only_owner_review,
)


def result():
    return {
        "result_digest": "a" * 64,
        "binding": {"owner": "100", "chat": "200", "provider_message_id": "300"},
        "proposal": {
            "proposal_id": "BMQ04-AWARENESS-1",
            "recommended_copy": "A quiet look at daily care on Amadeus Farm. Follow the farm journey.",
            "language": "en-ZA",
            "audience": "Local followers interested in responsible farming",
            "campaign_purpose": "Farm awareness without an availability claim",
            "channel": "Facebook Page organic",
            "timing": "owner_selection_required",
            "evidence": {"farm_identity": "Amadeus Farm", "safe_sale_capacity": "Unknown"},
            "evidence_boundary": "Awareness only; no price, stock, availability, reservation or sale claim.",
            "sale_availability_inferred": False,
            "sam_routing": "Attribute buying enquiries to this campaign and route them to SAM for independent qualification.",
            "media": [],
            "selected_media": [],
        },
    }


class TextOnlyOrganicReviewTests(unittest.TestCase):
    def build(self):
        return build_text_only_owner_review(
            result(), page_id="12345", page_name="Amadeus Farm",
            now=datetime(2099, 1, 1, tzinfo=timezone.utc),
        )

    def test_builds_explicit_immutable_text_only_class(self):
        packet = self.build()
        self.assertEqual(packet["packet_class"], PACKET_CLASS)
        self.assertEqual(packet["media"], {"exact_order": [], "assets": []})
        self.assertEqual(packet["owner_confirmed_subject"], "")
        self.assertEqual(packet["authority"], AUTHORITY)
        self.assertEqual(packet["performance"], UNKNOWN_MEASURES)
        self.assertEqual(validate_text_only_owner_review(packet), "")

    def test_caption_or_page_drift_invalidates_digest(self):
        for field, value in (("caption", "changed"), ("page_id", "wrong")):
            packet = self.build()
            packet[field] = value
            self.assertTrue(validate_text_only_owner_review(packet))

    def test_media_is_never_treated_as_missing_approved_media(self):
        supplied = result()
        supplied["proposal"]["media"] = [{"asset_id": "PRIVATE"}]
        packet = build_text_only_owner_review(supplied, page_id="1", page_name="Farm")
        self.assertEqual(packet["status"], "text_only_media_forbidden")
        drifted = self.build()
        drifted["media"]["assets"].append({"asset_id": "PUBLIC"})
        self.assertEqual(validate_text_only_owner_review(drifted), "text_only_media_forbidden")

    def test_missing_or_non_unknown_evidence_is_withheld(self):
        supplied = result()
        supplied["proposal"]["evidence"] = {"farm_identity": "Amadeus Farm"}
        self.assertEqual(
            build_text_only_owner_review(supplied, page_id="1", page_name="Farm")["status"],
            "text_only_evidence_not_explicit",
        )

    def test_wrong_channel_schedule_or_availability_is_withheld(self):
        for field, value, status in (
            ("channel", "Instagram", "text_only_channel_unsupported"),
            ("timing", "scheduled", "text_only_scheduling_forbidden"),
            ("sale_availability_inferred", True, "text_only_non_availability_boundary_required"),
        ):
            supplied = result(); supplied["proposal"][field] = value
            self.assertEqual(build_text_only_owner_review(supplied, page_id="1", page_name="Farm")["status"], status)

    def test_expired_review_cannot_translate_to_execution(self):
        packet = build_text_only_owner_review(
            result(), page_id="12345", page_name="Amadeus Farm",
            now=datetime(2020, 1, 1, tzinfo=timezone.utc),
        )
        result_packet = build_text_only_execution_packet(packet, publish_packet_id="P1")
        self.assertEqual(result_packet["status"], "text_only_review_expired")
        self.assertFalse(result_packet["execution_authorized"] if "execution_authorized" in result_packet else False)

    def test_translation_matches_existing_execution_shape_but_grants_nothing(self):
        packet = self.build()
        execution = build_text_only_execution_packet(packet, publish_packet_id="P1")
        self.assertTrue(execution["success"])
        self.assertEqual(execution["selected_assets"], [])
        self.assertEqual(execution["selected_draft"]["exact_text"], packet["caption"])
        self.assertFalse(execution["execution_authorized"])
        for key, value in AUTHORITY.items():
            self.assertEqual(execution[key], value)

    def test_correction_is_new_digest_not_mutation(self):
        first = self.build()
        changed = result(); changed["proposal"]["recommended_copy"] += " New version."
        second = build_text_only_owner_review(changed, page_id="12345", page_name="Amadeus Farm", now=datetime(2099,1,1,tzinfo=timezone.utc))
        self.assertNotEqual(first["packet_id"], second["packet_id"])
        self.assertNotEqual(first["canonical_sha256"], second["canonical_sha256"])
        self.assertEqual(validate_text_only_owner_review(first), "")


if __name__ == "__main__":
    unittest.main()
