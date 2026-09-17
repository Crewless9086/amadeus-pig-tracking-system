import copy
import hashlib
import json
import unittest

from scripts.build_sam_review_resolution_manifest import build
from modules.sales.sam_review_obligation_resolution import canonical_sha256
from tests.test_sam_review_obligation_resolution import evidence, represented, review


class ManifestBuilderTests(unittest.TestCase):
    def source(self):
        reviews = [review(i) for i in range(1, 363)]
        for row in reviews:
            row["decision_json_text"] = json.dumps(row["decision_json"], sort_keys=True)
            row["decision_json_sha256"] = hashlib.sha256(
                row["decision_json_text"].encode()
            ).hexdigest()
        return {
            "reviews": reviews,
            "expected_review_count": len(reviews),
            "expected_review_event_ids": sorted(row["review_event_id"] for row in reviews),
            "review_export_sha256": canonical_sha256(
                sorted(reviews, key=lambda row: row["review_event_id"])
            ),
            "evidence_by_review": {
                row["review_event_id"]: evidence(i)
                for i, row in enumerate(reviews, 1)
            },
            "represented_identity": represented(),
        }

    def test_complete_export_is_stable_and_contains_all_dispositions(self):
        source = self.source()
        first = build(source)
        source["reviews"].reverse()
        second = build(copy.deepcopy(source))
        self.assertEqual(first, second)
        self.assertEqual(first["row_count"], 362)
        self.assertEqual(sum(first["disposition_counts"].values()), 362)
        self.assertEqual(sum(first["obligation_counts"].values()), 362)

    def test_partial_or_wrong_identity_export_is_rejected(self):
        source = self.source()
        source["reviews"].pop()
        with self.assertRaisesRegex(ValueError, "complete_expected"):
            build(source)
        source = self.source()
        source["represented_identity"]["represented_pig_id"] = ""
        with self.assertRaisesRegex(ValueError, "exact_represented"):
            build(source)

    def test_second_identity_cohort_uses_same_generic_contract(self):
        source = self.source()
        source["represented_identity"] = represented(
            represented_pig_id="PIG-SECOND-IDENTITY",
            same_animal_mapping_prohibited=False,
            governed_disposition_operation_id="SECOND-DISPOSITION",
        )
        result = build(source)
        self.assertEqual(result["represented_pig_id"], "PIG-SECOND-IDENTITY")
        self.assertTrue(all(row["represented_pig_id"] == "PIG-SECOND-IDENTITY"
                            for row in result["rows"]))
        source = self.source()
        source["expected_review_event_ids"][-1] = "FABRICATED-REVIEW"
        with self.assertRaisesRegex(ValueError, "identity_set"):
            build(source)
        source = self.source()
        source["reviews"][0]["decision_json"]["tampered"] = True
        with self.assertRaisesRegex(ValueError, "decision_semantic"):
            build(source)
        source = self.source()
        del source["reviews"][0]["decision_json_text"]
        with self.assertRaisesRegex(ValueError, "decision_text_and_digest"):
            build(source)


if __name__ == "__main__":
    unittest.main()
