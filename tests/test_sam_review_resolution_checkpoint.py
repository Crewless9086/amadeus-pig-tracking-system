import tempfile
import unittest
from pathlib import Path

from modules.sales.sam_review_obligation_resolution import canonical_sha256
from modules.sales.sam_review_resolution_checkpoint import ResolutionCheckpoint


class ResolutionCheckpointTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.checkpoint = ResolutionCheckpoint(self.root)
        self.metadata = self.checkpoint.initialize(
            represented_pig_id="PIG-X", cutoff_at="2026-08-10T12:00:00+00:00",
            review_ids=["R2", "R1"], conversation_ids=["C2", "C1"],
        )

    def tearDown(self):
        self.temporary.cleanup()

    def conversation(self, conversation_id):
        chronology = [{"message_id": f"I-{conversation_id}",
                       "provider_observed_at": "2026-08-10T11:00:00+00:00"}]
        return {
            "conversation_id": conversation_id,
            "cutoff_at": self.metadata["cutoff_at"],
            "public_chronology": chronology,
            "chronology_sha256": canonical_sha256(chronology),
        }

    def test_resume_is_idempotent_and_complete_verification_passes(self):
        for review_id, conversation_id in (("R1", "C1"), ("R2", "C2")):
            packet = {"review_event_id": review_id, "conversation_id": conversation_id}
            self.assertTrue(self.checkpoint.store_review(packet))
            self.assertFalse(self.checkpoint.store_review(packet))
            self.assertTrue(self.checkpoint.store_review(packet, verification=True))
            evidence = self.conversation(conversation_id)
            self.assertTrue(self.checkpoint.store_conversation(conversation_id, evidence))
            self.assertTrue(self.checkpoint.store_conversation(conversation_id, evidence, verification=True))
        result = self.checkpoint.validate_complete(
            expected_review_count=2, expected_conversation_count=2)
        self.assertEqual(len(result["reviews"]), 2)
        self.assertEqual(len(result["conversations"]), 2)

    def test_changed_chronology_fails_closed(self):
        for review_id in ("R1", "R2"):
            self.checkpoint.store_review({"review_event_id": review_id})
            self.checkpoint.store_review({"review_event_id": review_id}, verification=True)
        first = self.conversation("C1")
        changed = self.conversation("C1")
        changed["public_chronology"][0]["message_id"] = "CHANGED"
        changed["chronology_sha256"] = canonical_sha256(changed["public_chronology"])
        self.checkpoint.store_conversation("C1", first)
        self.checkpoint.store_conversation("C1", changed, verification=True)
        both = self.conversation("C2")
        self.checkpoint.store_conversation("C2", both)
        self.checkpoint.store_conversation("C2", both, verification=True)
        with self.assertRaisesRegex(ValueError, "conversation_changed_during_snapshot:C1"):
            self.checkpoint.validate_complete(expected_review_count=2, expected_conversation_count=2)

    def test_incomplete_pages_and_identity_conflicts_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "review_outside_allowlist"):
            self.checkpoint.store_review({"review_event_id": "R3"})
        with self.assertRaisesRegex(ValueError, "complete_public_chronology_required"):
            self.checkpoint.store_conversation("C1", {
                "conversation_id": "C1", "cutoff_at": self.metadata["cutoff_at"],
                "public_chronology": [], "chronology_sha256": canonical_sha256([]),
            })
        with self.assertRaisesRegex(ValueError, "review_checkpoint_missing:R1"):
            self.checkpoint.validate_complete(expected_review_count=2, expected_conversation_count=2)

    def test_checkpoint_identity_cannot_be_reused_for_another_cutoff(self):
        with self.assertRaisesRegex(ValueError, "checkpoint_identity_conflict"):
            self.checkpoint.initialize(
                represented_pig_id="PIG-X", cutoff_at="2026-08-10T13:00:00+00:00",
                review_ids=["R1", "R2"], conversation_ids=["C1", "C2"],
            )

    def test_pagination_shape_may_change_when_cutoff_prefix_is_identical(self):
        for review_id in ("R1", "R2"):
            packet = {"review_event_id": review_id}
            self.checkpoint.store_review(packet)
            self.checkpoint.store_review(packet, verification=True)
        for conversation_id in ("C1", "C2"):
            first = self.conversation(conversation_id)
            verified = self.conversation(conversation_id)
            first["page_count"] = 2
            verified["page_count"] = 3
            self.checkpoint.store_conversation(conversation_id, first)
            self.checkpoint.store_conversation(conversation_id, verified, verification=True)
        self.checkpoint.validate_complete(expected_review_count=2, expected_conversation_count=2)


if __name__ == "__main__":
    unittest.main()
