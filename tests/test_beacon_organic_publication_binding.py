import copy
import unittest

from modules.beacon.organic_publication_binding import (
    _decision_mismatch,
    _execution_packet_mismatch,
    _media_order_hash,
    _runtime_mismatch,
)
from modules.beacon.weekly_owner_review import build_post_one_owner_review
from modules.sales.beacon_campaign import build_beacon_campaign_publish_packet
from tests.test_beacon_weekly_owner_review_decisions import eligible_assets


class OrganicPublicationBindingTests(unittest.TestCase):
    def setUp(self):
        self.assets = eligible_assets()
        self.weekly = build_post_one_owner_review(self.assets)
        order = self.weekly["media"]["exact_order"]
        self.execution = build_beacon_campaign_publish_packet(
            {
                "campaign_lane": "live_stock_awareness",
                "draft_id": "facebook_awareness_post",
                "asset_id": order[0],
                "asset_ids": order,
                "channel": "Facebook",
                "owner_exact_text": self.weekly["caption"],
            },
            approved_assets=self.assets,
        )

    def test_exact_weekly_execution_content_contract_matches(self):
        self.assertTrue(self.execution["success"])
        self.assertEqual(
            _execution_packet_mismatch(self.weekly, self.execution), ""
        )

    def test_caption_media_order_and_execution_packet_drift_fail_closed(self):
        changed = copy.deepcopy(self.execution)
        changed["selected_draft"]["exact_text"] += " changed"
        self.assertEqual(
            _execution_packet_mismatch(self.weekly, changed),
            "publication_binding_caption_mismatch",
        )
        changed = copy.deepcopy(self.execution)
        changed["selected_assets"].reverse()
        self.assertEqual(
            _execution_packet_mismatch(self.weekly, changed),
            "publication_binding_media_order_mismatch",
        )
        changed = copy.deepcopy(self.execution)
        changed["publish_packet_id"] = ""
        self.assertEqual(
            _execution_packet_mismatch(self.weekly, changed),
            "publication_binding_execution_packet_required",
        )

    def test_decision_hash_subject_and_channel_drift_fail_closed(self):
        decision = {
            "canonical_sha256": self.weekly["canonical_sha256"],
            "caption_sha256": self.weekly["caption_sha256"],
            "exact_caption": self.weekly["caption"],
            "exact_media_order": self.weekly["media"]["exact_order"],
            "owner_confirmed_subject": "Ms. Piggy and her litter",
            "channel": "Facebook Page",
        }
        self.assertEqual(_decision_mismatch(decision, self.weekly), "")
        for field, status in (
            ("canonical_sha256", "publication_binding_canonical_hash_mismatch"),
            ("caption_sha256", "publication_binding_caption_hash_mismatch"),
            ("owner_confirmed_subject", "publication_binding_subject_mismatch"),
            ("channel", "publication_binding_channel_mismatch"),
        ):
            changed = dict(decision)
            changed[field] = "changed"
            self.assertEqual(_decision_mismatch(changed, self.weekly), status)

    def test_runtime_target_caption_media_and_hash_drift_fail_closed(self):
        order = self.weekly["media"]["exact_order"]
        binding = {
            "canonical_sha256": self.weekly["canonical_sha256"],
            "caption_sha256": self.weekly["caption_sha256"],
            "media_order_sha256": _media_order_hash(order),
            "exact_media_order": order,
            "target_page_id": "page-1",
        }
        decision = {
            "decision_status": "owner_approved",
            "canonical_sha256": self.weekly["canonical_sha256"],
            "caption_sha256": self.weekly["caption_sha256"],
        }
        params = {
            "exact_text": self.weekly["caption"],
            "channel": "Facebook",
            "selected_assets": [
                {"asset_id": asset_id} for asset_id in order
            ],
        }
        self.assertEqual(
            _runtime_mismatch(binding, decision, params, "page-1"), ""
        )
        self.assertEqual(
            _runtime_mismatch(binding, decision, params, "page-2"),
            "organic_publication_target_drift",
        )
        changed = copy.deepcopy(params)
        changed["selected_assets"].reverse()
        self.assertEqual(
            _runtime_mismatch(binding, decision, changed, "page-1"),
            "organic_publication_media_order_drift",
        )
        changed = copy.deepcopy(params)
        changed["exact_text"] += " changed"
        self.assertEqual(
            _runtime_mismatch(binding, decision, changed, "page-1"),
            "organic_publication_caption_drift",
        )


if __name__ == "__main__":
    unittest.main()
