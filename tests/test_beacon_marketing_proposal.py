import unittest

from modules.beacon.marketing_proposal import (
    LIBRARY_ACCEPT,
    ZERO_AUTHORITY,
    prepare_marketing_proposal,
)


HASH_A = "a" * 64
HASH_B = "b" * 64


def objective(mode="single"):
    return {
        "objective_id": "OBJ-1",
        "summary": "Show the farm's careful daily pig care.",
        "business_reason": "Recent verified audience questions favour educational farm stories.",
        "media_mode": mode,
        "media_tags": ["pig_care"],
        "missing_media": {
            "subject": "one pig in a clean pen with the water point visible",
            "angle": "from pig shoulder height, wide enough to show the pen",
            "orientation": "portrait",
            "purpose": "a Facebook and Instagram husbandry story",
        },
        "evidence": [{
            "evidence_id": "E-1",
            "source_id": "family-question-log-2026-W31",
            "observed_at": "2026-07-29T08:00:00+02:00",
            "statement": "Three recent family-page questions asked about daily pig care.",
            "claim_types": ["animal", "audience", "welfare"],
            "supported_assertions": [{
                "assertion_id": "ASSERT-WELFARE-1",
                "text": "A quiet look at the daily care behind the farm.",
                "claim_type": "welfare",
            }],
            "status": "verified",
        }],
    }


def media(asset="A", digest=HASH_A, status=LIBRARY_ACCEPT, **extra):
    value = {
        "asset_id": f"ASSET-{asset}",
        "content_sha256": digest,
        "storage_proof_id": f"STORE-{asset}",
        "review_event_id": f"REVIEW-{asset}",
        "current_review_proof_id": f"CURRENT-{asset}",
        "private_preview_ref": f"beacon-private-preview:{asset}:{digest}",
        "projection_authority": "server_resolved_current_media_v1",
        "review_status": status,
        "private_storage": True,
        "public_use_approved": False,
        "tags": ["pig_care"],
        "purpose": "show clean daily care",
    }
    value.update(extra)
    return value


def draft(claim_type="audience", evidence_ids=None):
    return {
        "audience": "Families interested in responsible farming",
        "channel": "facebook_organic",
        "caption": "A quiet look at the daily care behind the farm.",
        "call_to_action": "What would you like to learn about daily care?",
        "claims": [
            {
                "text": "A quiet look at the daily care behind the farm.",
                "claim_types": [claim_type],
                "classification_authority": "server_claim_classification_v1",
                "classification_proof_id": "CLASS-CAPTION-1",
                "placement": "caption",
                "evidence_ids": ["E-1"] if evidence_ids is None else evidence_ids,
            },
            {
                "text": "What would you like to learn about daily care?",
                "claim_types": ["engagement"],
                "classification_authority": "server_claim_classification_v1",
                "classification_proof_id": "CLASS-CTA-1",
                "placement": "call_to_action",
                "evidence_ids": ["E-1"],
            },
        ],
    }


class BeaconMarketingProposalTests(unittest.TestCase):
    def test_library_accept_campaign_publication_and_spend_are_separate(self):
        packet = prepare_marketing_proposal(objective(), [media()], draft())
        self.assertEqual(packet["status"], "ready_for_owner_review")
        self.assertTrue(packet["exact_media"][0]["campaign_selected"])
        self.assertFalse(packet["exact_media"][0]["public_use_approved"])
        self.assertEqual(
            [a["action"] for a in packet["protected_actions_requested"]],
            ["public_use_approval", "publication_approval"],
        )
        self.assertEqual(packet["paid_spend_approval"]["status"], "not_requested")
        self.assertIn("does not approve public use", packet["approval_note"])

    def test_only_explicit_library_accept_media_is_selected(self):
        packet = prepare_marketing_proposal(
            objective(), [media("P", status="pending"), media("A")], draft()
        )
        self.assertEqual(packet["proposed_media_order"], ["ASSET-A"])
        self.assertEqual(
            packet["media_rejections"][0]["reason"], "library_accept_required"
        )

    def test_single_image_is_selected_when_one_is_sufficient(self):
        packet = prepare_marketing_proposal(
            objective("single"), [media("A"), media("B", HASH_B)], draft()
        )
        self.assertEqual(packet["media_strategy"], "one_image_sufficient")
        self.assertEqual(packet["proposed_media_order"], ["ASSET-A"])

    def test_multi_image_set_requires_provenance_for_every_image(self):
        incomplete = media("B", HASH_B)
        incomplete.pop("storage_proof_id")
        packet = prepare_marketing_proposal(
            objective("multi_useful"), [media("A"), incomplete], draft()
        )
        self.assertEqual(packet["proposed_media_order"], ["ASSET-A"])
        self.assertEqual(
            packet["media_rejections"][0]["reason"],
            "per_image_provenance_incomplete",
        )

    def test_multi_image_grouping_is_ordered_and_source_only(self):
        packet = prepare_marketing_proposal(
            objective("multi_useful"), [media("A"), media("B", HASH_B)], draft()
        )
        self.assertEqual(packet["media_strategy"], "multi_image_useful")
        self.assertEqual(packet["proposed_media_order"], ["ASSET-A", "ASSET-B"])
        self.assertTrue(all(not value for value in packet["authority"].values()))

    def test_exact_duplicate_hash_is_not_grouped_twice(self):
        packet = prepare_marketing_proposal(
            objective("multi_useful"), [media("A"), media("B", HASH_A)], draft()
        )
        self.assertEqual(packet["proposed_media_order"], ["ASSET-A"])
        self.assertEqual(packet["media_rejections"][0]["reason"], "duplicate_content")

    def test_missing_media_request_is_precise_and_family_friendly(self):
        packet = prepare_marketing_proposal(objective(), [], draft())
        self.assertEqual(packet["packet_type"], "missing_media_request")
        message = packet["family_message"]
        for phrase in ("pig", "shoulder height", "portrait", "husbandry story"):
            self.assertIn(phrase, message)
        self.assertIn("No marketing wording is needed", message)
        self.assertEqual(packet["request_via"], "oom_sakkie")

    def test_unsupported_protected_claims_are_rejected_individually(self):
        for claim_type in (
            "animal", "availability", "price", "delivery", "welfare",
            "medical", "provenance", "performance",
        ):
            with self.subTest(claim_type=claim_type):
                packet = prepare_marketing_proposal(
                    objective(), [media()], draft(claim_type, [])
                )
                self.assertEqual(packet["status"], "needs_factual_correction")
                self.assertEqual(
                    packet["missing_facts"][0]["reason"],
                    "exact_verified_assertion_required",
                )

    def test_supported_welfare_claim_uses_matching_evidence(self):
        packet = prepare_marketing_proposal(objective(), [media()], draft("welfare", ["E-1"]))
        self.assertEqual(packet["status"], "ready_for_owner_review")
        self.assertEqual(packet["missing_facts"], [])

    def test_unverified_business_evidence_cannot_ground_objective(self):
        value = objective()
        value["evidence"][0]["status"] = "inferred"
        with self.assertRaisesRegex(ValueError, "unverified_business_evidence"):
            prepare_marketing_proposal(value, [media()], draft())

    def test_packet_is_consolidated_deterministic_and_zero_write(self):
        first = prepare_marketing_proposal(objective(), [media()], draft())
        second = prepare_marketing_proposal(objective(), [media()], draft())
        self.assertEqual(first["packet_id"], second["packet_id"])
        for key in (
            "objective", "audience", "intended_channel", "exact_media",
            "draft_caption", "factual_evidence", "missing_facts",
            "call_to_action", "protected_actions_requested", "decision_options",
        ):
            self.assertIn(key, first)
        self.assertEqual(first["authority"], ZERO_AUTHORITY)
        self.assertTrue(all(value is False for value in first["authority"].values()))

    def test_unsafe_claim_hidden_in_caption_is_not_approvable(self):
        value = draft()
        value["caption"] = "Available now at a special price."
        with self.assertRaisesRegex(
            ValueError, "caption_not_composed_from_validated_claims"
        ):
            prepare_marketing_proposal(objective(), [media()], value)

    def test_untrusted_or_stale_review_projection_is_rejected(self):
        stale = media()
        stale["projection_authority"] = "caller_asserted"
        packet = prepare_marketing_proposal(objective(), [stale], draft())
        self.assertEqual(packet["packet_type"], "missing_media_request")
        self.assertEqual(
            packet["media_rejections"][0]["reason"],
            "trusted_current_media_projection_required",
        )

    def test_private_preview_is_bound_into_exact_media_and_packet_identity(self):
        first = prepare_marketing_proposal(objective(), [media()], draft())
        changed = media(private_preview_ref=f"beacon-private-preview:A:{'c' * 64}")
        second = prepare_marketing_proposal(objective(), [changed], draft())
        self.assertIn("private_preview_ref", first["exact_media"][0])
        self.assertNotEqual(first["packet_id"], second["packet_id"])

    def test_caller_cannot_spoof_public_use_state(self):
        packet = prepare_marketing_proposal(
            objective(), [media(public_use_approved=True)], draft()
        )
        self.assertFalse(packet["exact_media"][0]["public_use_approved"])

    def test_displayed_copy_must_be_composed_from_exact_validated_claims(self):
        value = draft()
        value["caption"] = "We have 10 piglets for sale."
        with self.assertRaisesRegex(
            ValueError, "caption_not_composed_from_validated_claims"
        ):
            prepare_marketing_proposal(objective(), [media()], value)

    def test_proposal_and_protected_approvals_are_independently_decidable(self):
        packet = prepare_marketing_proposal(objective(), [media()], draft())
        self.assertEqual(
            packet["decision_options"],
            ["approve_proposal_only", "correct", "decline"],
        )
        self.assertEqual(
            packet["protected_actions_requested"][0]["decision_options"],
            ["approve_public_use", "decline_public_use"],
        )
        self.assertEqual(
            packet["protected_actions_requested"][1]["decision_options"],
            ["approve_publication", "decline_publication"],
        )

    def test_same_type_contradictory_evidence_cannot_support_copy(self):
        value = objective()
        value["evidence"][0]["supported_assertions"] = [{
            "assertion_id": "NO-STOCK",
            "text": "No pigs are currently available.",
            "claim_type": "availability",
        }]
        copy = draft("availability", ["E-1"])
        copy["claims"][0]["text"] = "Piglets are available now."
        copy["caption"] = "Piglets are available now."
        packet = prepare_marketing_proposal(value, [media()], copy)
        self.assertEqual(packet["status"], "needs_factual_correction")
        self.assertEqual(
            packet["missing_facts"][0]["reason"],
            "exact_verified_assertion_required",
        )

    def test_trusted_classification_must_include_detected_protected_types(self):
        copy = draft()
        copy["caption"] = "We have 10 piglets for sale."
        copy["claims"][0]["text"] = copy["caption"]
        copy["claims"][0]["claim_types"] = ["animal"]
        packet = prepare_marketing_proposal(objective(), [media()], copy)
        self.assertEqual(packet["status"], "needs_factual_correction")
        missing_types = {item["claim_type"] for item in packet["missing_facts"]}
        self.assertIn("availability", missing_types)


if __name__ == "__main__":
    unittest.main()
