import unittest
from datetime import datetime, timedelta, timezone

from modules.beacon.publication_execution_identity import (
    ASSET_ID, ASSET_SHA256, PROPOSAL_ID, PUBLISH_NOW_AUTHORITY_ID, PUBLISH_NOW_EXECUTION_ID,
    SUCCESSOR_EXECUTION_ID,
    TERMINAL_EXECUTION_IDS,
    validate_successor_execution,
)


class PublicationExecutionIdentityTests(unittest.TestCase):
    def payload(self, now):
        return {
            "publish_packet_id": PROPOSAL_ID,
            "publication_execution_identity": SUCCESSOR_EXECUTION_ID,
            "asset_id": ASSET_ID,
            "selected_asset": {"asset_id": ASSET_ID, "media_type": "image",
                               "storage_readback_sha256": ASSET_SHA256},
            "exact_text": bytes.fromhex(
                "42656c6c6120656e2068616172203133206b6c65696e207661726b69657320"
                "e2809420736f6d6d657220e280996e206d6f6f69206f6f6d626c696b206f6d"
                "207465206465656c2e20f09f90b7"
            ).decode("utf-8"),
            "channel": "facebook_organic",
            "zero_spend": True,
            "timing_authorization_id": "OOMAQ-TIME-NEW",
            "timing_start": (now - timedelta(minutes=1)).isoformat(),
            "timing_end": (now + timedelta(minutes=1)).isoformat(),
        }

    def test_exact_successor_with_fresh_timing_is_valid(self):
        now = datetime.now(timezone.utc)
        self.assertEqual(validate_successor_execution(self.payload(now), now=now), "")

    def test_publish_now_remains_actionable_without_a_schedule_window(self):
        item = self.payload(datetime.now(timezone.utc))
        item.update({
            "publication_execution_identity": PUBLISH_NOW_EXECUTION_ID,
            "publication_authority_mode": "publish_now",
            "publication_authority_id": PUBLISH_NOW_AUTHORITY_ID,
            "publication_authority_state": "active",
            "timing_authorization_id": "",
            "timing_start": "",
            "timing_end": "",
        })
        self.assertEqual(validate_successor_execution(item), "")

    def test_scheduled_exact_still_requires_current_window(self):
        item = self.payload(datetime.now(timezone.utc))
        item["publication_authority_mode"] = "scheduled_exact"
        item["timing_start"] = "2026-01-01T00:00:00+00:00"
        item["timing_end"] = "2026-01-01T01:00:00+00:00"
        self.assertEqual(validate_successor_execution(item),
                         "successor_publication_timing_window_invalid")

    def test_publish_now_stops_on_each_durable_terminal_condition(self):
        for state in ("owner_cancelled", "evidence_invalidated",
                      "provider_ambiguous", "provider_confirmed"):
            item = self.payload(datetime.now(timezone.utc))
            item.update({
                "publication_execution_identity": PUBLISH_NOW_EXECUTION_ID,
                "publication_authority_mode": "publish_now",
                "publication_authority_id": PUBLISH_NOW_AUTHORITY_ID,
                "publication_authority_state": state,
            })
            with self.subTest(state=state):
                self.assertEqual(validate_successor_execution(item),
                                 "successor_publish_now_authority_not_actionable")

    def test_publish_now_rejects_caller_invented_authority(self):
        item = self.payload(datetime.now(timezone.utc))
        item.update({"publication_execution_identity": PUBLISH_NOW_EXECUTION_ID,
                     "publication_authority_mode": "publish_now",
                     "publication_authority_id": "CALLER-INVENTED",
                     "publication_authority_state": "active"})
        self.assertEqual(validate_successor_execution(item),
                         "successor_publish_now_authority_mismatch")

    def test_terminal_claim_and_result_are_permanently_non_reusable(self):
        now = datetime.now(timezone.utc)
        for terminal in TERMINAL_EXECUTION_IDS:
            with self.subTest(terminal=terminal):
                item = self.payload(now)
                item["execution_event_id"] = terminal
                self.assertEqual(validate_successor_execution(item, now=now),
                                 "terminal_publication_execution_non_reusable")
                self.assertEqual(validate_successor_execution({
                    "publish_packet_id": terminal,
                }, now=now), "terminal_publication_execution_non_reusable")

    def test_expired_or_missing_timing_reauthorization_fails_closed(self):
        now = datetime.now(timezone.utc)
        expired = self.payload(now)
        expired["timing_start"] = (now - timedelta(hours=2)).isoformat()
        expired["timing_end"] = (now - timedelta(hours=1)).isoformat()
        self.assertEqual(validate_successor_execution(expired, now=now),
                         "successor_publication_timing_window_invalid")
        missing = self.payload(now)
        missing["timing_authorization_id"] = ""
        self.assertEqual(validate_successor_execution(missing, now=now),
                         "successor_publication_timing_authorization_required")
        valid = self.payload(now)
        self.assertEqual(validate_successor_execution(
            valid, now=now, authoritative_timing_authorization_id="OTHER-AUTH"
        ), "successor_publication_timing_authorization_mismatch")

    def test_preserved_content_channel_and_zero_spend_cannot_change(self):
        now = datetime.now(timezone.utc)
        cases = (
            ("asset_id", "OTHER", "successor_publication_asset_mismatch"),
            ("exact_text", "changed", "successor_publication_caption_mismatch"),
            ("channel", "Instagram organic", "successor_publication_channel_mismatch"),
            ("zero_spend", False, "successor_publication_zero_spend_required"),
        )
        for key, value, expected in cases:
            with self.subTest(key=key):
                item = self.payload(now)
                item[key] = value
                self.assertEqual(validate_successor_execution(item, now=now), expected)

    def test_missing_changed_or_extra_selected_media_fails_closed(self):
        now = datetime.now(timezone.utc)
        missing = self.payload(now); missing.pop("selected_asset")
        changed = self.payload(now); changed["selected_asset"]["asset_id"] = "OTHER"
        extra = self.payload(now); extra["selected_assets"] = [
            {"asset_id": ASSET_ID, "media_type": "image"},
            {"asset_id": "OTHER", "media_type": "image"},
        ]
        for item in (missing, changed, extra):
            self.assertEqual(validate_successor_execution(item, now=now),
                             "successor_publication_media_order_mismatch")

    def test_changed_server_readback_hash_fails_closed(self):
        item = self.payload(datetime.now(timezone.utc))
        item["selected_asset"]["storage_readback_sha256"] = "forged"
        self.assertEqual(validate_successor_execution(item),
                         "successor_publication_asset_hash_mismatch")


if __name__ == "__main__":
    unittest.main()
