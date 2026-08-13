import unittest

from modules.pig_weights.herdmaster_piglet_observation_action import (
    normalize_application, normalize_typed_oom_sakkie, normalize_telegram,
    normalize_voice, preview_action,
)
from modules.pig_weights.herdmaster_breeding_evidence import _observations
from datetime import date


def payload(**changes):
    value = {
        "litter_id": "LIT-1", "observed_on": "2026-08-11",
        "source_context": "historical_weaning", "source_reference": "paper-note",
        "idempotency_key": "owner-note-11-aug",
        "observations": [
            {"pig_id": "PIG-1", "traits": ["good_build", "strong_legs"],
             "sentiment": "positive", "factual_note": "Strong legs and good build.", "watch_flag": True},
            {"pig_id": "PIG-2", "traits": ["concern"], "sentiment": "concerning",
             "factual_note": "Left hind leg looked weak."},
        ],
    }
    value.update(changes)
    return value


class PigletObservationActionTests(unittest.TestCase):
    def test_all_channels_normalize_to_exact_same_canonical_action(self):
        actions = [normalizer(payload())[0] for normalizer in (
            normalize_application, normalize_typed_oom_sakkie,
            normalize_telegram, normalize_voice,
        )]
        semantic = [{key: value for key, value in action.items() if key != "input_provenance"} for action in actions]
        self.assertTrue(all(action == semantic[0] for action in semantic))
        self.assertEqual({action["input_provenance"] for action in actions}, {"application", "typed_oom_sakkie", "telegram", "voice"})

    def test_positive_concerning_and_multiple_piglets_preview_once(self):
        result, status = preview_action(payload(), identity_rows=[
            {"pig_id": "PIG-1", "litter_id": "LIT-1", "tag_number": "101"},
            {"pig_id": "PIG-2", "litter_id": "LIT-1", "tag_number": "102"},
        ])
        self.assertEqual((status, result["observation_count"]), (200, 2))
        self.assertEqual([row["sentiment"] for row in result["observation_effects"]], ["positive", "concerning"])
        for forbidden in ("changes_litter", "changes_lifecycle", "changes_medical", "changes_movement", "changes_purpose", "selects_breeding_pig"):
            self.assertFalse(result[forbidden])

    def test_unknown_or_partial_group_identity_fails_closed(self):
        result, status = preview_action(payload(), identity_rows=[
            {"pig_id": "PIG-1", "litter_id": "LIT-1", "tag_number": "101"},
        ])
        self.assertEqual(status, 409)
        self.assertIn("exact_litter_pig_identity_required", result["errors"])

    def test_same_pig_correction_is_preserved_in_canonical_contract(self):
        corrected = payload(observations=[{
            "pig_id": "PIG-1", "traits": ["good_build"], "sentiment": "positive",
            "factual_note": "Correction: build was good; legs not assessed.",
            "supersedes_observation_event_id": "OBS-OLD",
        }])
        result, status = preview_action(corrected, identity_rows=[
            {"pig_id": "PIG-1", "litter_id": "LIT-1", "tag_number": "101"},
        ])
        self.assertEqual(status, 200)
        self.assertEqual(result["action"]["observations"][0]["supersedes_observation_event_id"], "OBS-OLD")

    def test_unknown_observation_date_is_not_inferred(self):
        invalid = payload(observed_on="")
        result, status = preview_action(invalid, identity_rows=[])
        self.assertEqual(status, 409)
        self.assertIn("complete_observation_action_required", result["errors"])

    def test_later_herdmaster_evidence_cites_observation_without_selecting_pig(self):
        evidence = _observations([{
            "pig_id": "PIG-1", "observation_event_id": "OBS-1",
            "observed_at": "2026-08-11T12:00:00+00:00", "recorded_at": "2026-08-13T09:00:00+00:00",
            "factual_note": "Strong legs and good build.",
            "measurements_json": {"contract_version": "herdmaster_piglet_observation_v1",
                                  "traits": ["strong_legs", "potential_breeding_review"],
                                  "sentiment": "positive", "watch_flag": True},
        }], date(2026, 8, 13))["PIG-1"]
        self.assertEqual(evidence["observation_event_id"], "OBS-1")
        self.assertTrue(evidence["future_review_watch"])
        self.assertIn("does not assign purpose", evidence["weaning_observation_limitations"])


if __name__ == "__main__":
    unittest.main()
