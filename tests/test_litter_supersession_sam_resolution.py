import json
import unittest

from modules.pig_weights.litter_supersession_service import (
    _sam_review_history_references,
)


class _Cursor:
    def __init__(self, row=None, rows=None):
        self.row, self.rows = row, rows or []
    def fetchone(self):
        return self.row
    def fetchall(self):
        return self.rows


class _Connection:
    def __init__(self, resolution=None):
        self.resolution = resolution
    def execute(self, query, params=None):
        normalized = " ".join(str(query).split())
        if "select count(*) from" in normalized:
            return _Cursor((0,))
        if "from pg_catalog.pg_trigger" in normalized:
            body = "begin raise exception 'sam_live_stock_conversation_review_events is append-only'; end;"
            return _Cursor(rows=[
                ("prevent_sam_live_stock_review_update", "O", 19, "public",
                 "prevent_sam_live_stock_review_mutation", "update trigger", body,
                 "update function", False, None),
                ("prevent_sam_live_stock_review_delete", "O", 11, "public",
                 "prevent_sam_live_stock_review_mutation", "delete trigger", body,
                 "delete function", False, None),
            ])
        if "join public.current_sam_review_obligation_resolutions" in normalized:
            decision = {"agent_evidence": {"herdmaster": {"availability_rows": [
                {"pig_id": "PIG-SUPERSEDED"}
            ]}}}
            return _Cursor(rows=[(
                "REVIEW-1", json.dumps(decision, separators=(",", ":")),
                True, False, False, False, False, False, False, False,
                False, False, False, True, False, False, "owner_decision",
                "SALE", "shadow_review", "{}",
            )])
        if "from public.current_sam_review_obligation_resolutions" in normalized:
            return _Cursor(self.resolution)
        raise AssertionError(normalized)


def _resolution(**changes):
    values = [
        "SAM-REVIEW-RESOLUTION-ABC", "PIG-SUPERSEDED", "superseded",
        True, None, "GOVERNED-DISPOSITION-1",
        "protected_owner_action_required", "protected", "a" * 64,
    ]
    positions = {
        "represented_identity_status": 2,
        "same_animal_mapping_prohibited": 3,
        "canonical_same_animal_pig_id": 4,
        "customer_obligation_status": 6,
        "resolution_action": 7,
    }
    for key, value in changes.items():
        values[positions[key]] = value
    return tuple(values)


class LitterSupersessionSamResolutionTests(unittest.TestCase):
    def test_action_bearing_review_is_preserved_with_governed_resolution(self):
        rows, guards = _sam_review_history_references(
            _Connection(_resolution()), ["PIG-SUPERSEDED"],
            ["decision_json", "review_json", "recommended_action"],
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(len(guards), 2)
        self.assertEqual(
            rows[0]["classification"],
            "immutable_review_with_governed_current_obligation",
        )
        self.assertEqual(
            rows[0]["current_resolution"]["customer_obligation_status"],
            "protected_owner_action_required",
        )

    def test_missing_or_unsafe_resolution_fails_closed(self):
        for resolution in (
            None,
            _resolution(canonical_same_animal_pig_id="PIG-CANONICAL"),
            _resolution(same_animal_mapping_prohibited=False),
            _resolution(customer_obligation_status="unknown_fail_closed"),
            _resolution(resolution_action="indeterminate"),
        ):
            with self.subTest(resolution=resolution):
                with self.assertRaisesRegex(
                    RuntimeError, "current governed SAM obligation resolution required"
                ):
                    _sam_review_history_references(
                        _Connection(resolution), ["PIG-SUPERSEDED"],
                        ["decision_json", "review_json", "recommended_action"],
                    )


if __name__ == "__main__":
    unittest.main()
