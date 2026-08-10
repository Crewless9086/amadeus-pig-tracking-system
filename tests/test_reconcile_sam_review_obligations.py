import tempfile
import unittest
from pathlib import Path

from modules.sales.sam_review_resolution_checkpoint import ResolutionCheckpoint
from scripts.reconcile_sam_review_obligations import capture, canonical_message_type


class FakeSource:
    def __init__(self):
        self.review_ids = ["R1", "R2", "R3"]
        self.conversation_ids = ["C1", "C2"]
        self.review_calls = []
        self.conversation_calls = {"C1": 0, "C2": 0}
        self.change_on_verify = set()

    def population(self):
        return list(self.review_ids), list(self.conversation_ids)

    def review_page(self, review_ids):
        self.review_calls.append(list(review_ids))
        mapping = {"R1": "C1", "R2": "C1", "R3": "C2"}
        return [{"review_event_id": value, "conversation_id": mapping[value]}
                for value in review_ids]

    def conversation_at_cutoff(self, conversation_id, cutoff_at):
        from modules.sales.sam_review_obligation_resolution import canonical_sha256
        self.conversation_calls[conversation_id] += 1
        message_id = f"I-{conversation_id}"
        if conversation_id in self.change_on_verify and self.conversation_calls[conversation_id] == 2:
            message_id += "-CHANGED"
        chronology = [{"message_id": message_id,
                       "provider_observed_at": "2026-08-10T11:00:00+00:00"}]
        return {
            "conversation_id": conversation_id,
            "cutoff_at": cutoff_at,
            "public_chronology": chronology,
            "chronology_sha256": canonical_sha256(chronology),
        }


class ReconcileSamReviewObligationsTests(unittest.TestCase):
    def test_chatwoot_numeric_message_types_preserve_incoming_zero(self):
        self.assertEqual(canonical_message_type(0), "incoming")
        self.assertEqual(canonical_message_type("0"), "incoming")
        self.assertEqual(canonical_message_type(1), "outgoing")
        self.assertEqual(canonical_message_type("1"), "outgoing")
        self.assertEqual(canonical_message_type(None), "")

    def test_capture_is_paginated_resumable_and_double_verified(self):
        source = FakeSource()
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = ResolutionCheckpoint(Path(directory))
            complete = capture(source, checkpoint, page_size=2, expected_reviews=3, expected_conversations=2)
            self.assertEqual(source.review_calls, [["R1", "R2"], ["R3"], ["R1", "R2"], ["R3"]])
            self.assertEqual(source.conversation_calls, {"C1": 2, "C2": 2})
            self.assertEqual(len(complete["reviews"]), 3)
            source.review_calls.clear()
            capture(source, checkpoint, page_size=2, expected_reviews=3, expected_conversations=2)
            self.assertEqual(source.review_calls, [])
            self.assertEqual(source.conversation_calls, {"C1": 2, "C2": 2})

    def test_changed_provider_prefix_fails_closed(self):
        source = FakeSource()
        source.change_on_verify.add("C2")
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = ResolutionCheckpoint(Path(directory))
            with self.assertRaisesRegex(ValueError, "conversation_changed_during_snapshot:C2"):
                capture(source, checkpoint, page_size=2, expected_reviews=3, expected_conversations=2)

    def test_population_change_rejects_resume(self):
        source = FakeSource()
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = ResolutionCheckpoint(Path(directory))
            capture(source, checkpoint, page_size=2, expected_reviews=3, expected_conversations=2)
            source.review_ids.append("R4")
            with self.assertRaisesRegex(RuntimeError, "checkpoint_population_became_stale"):
                capture(source, checkpoint, page_size=2, expected_reviews=3, expected_conversations=2)

    def test_incomplete_review_page_is_not_checkpointed(self):
        source = FakeSource()
        source.review_page = lambda values: []
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = ResolutionCheckpoint(Path(directory))
            with self.assertRaisesRegex(ValueError, "review_checkpoint_missing:R1"):
                capture(source, checkpoint, page_size=2, expected_reviews=3, expected_conversations=2)


if __name__ == "__main__":
    unittest.main()
