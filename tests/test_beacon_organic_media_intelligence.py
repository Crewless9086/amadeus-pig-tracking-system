import json
import unittest
from pathlib import Path
from unittest.mock import patch

from modules.beacon.organic_media_intelligence import (
    append_learning_event,
    build_organic_learning_report,
    evaluate_graduation,
)


CAPTION = "Exact first paragraph.\n\nExact Unicode: Waki’s attention."
POST = "920598737794159_122145593991122163"


def media(asset_hash="a" * 64):
    return [{"asset_id": "ASSET-1", "content_sha256": asset_hash}]


def publication(asset_hash="a" * 64):
    from hashlib import sha256
    payload = [{"asset_id": "ASSET-1", "content_sha256": asset_hash}]
    canonical = lambda value: sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    return {
        "facebook_post_id": POST,
        "packet_id": "PACKET-1",
        "caption": CAPTION,
        "caption_sha256": sha256(CAPTION.encode()).hexdigest(),
        "media_order_sha256": canonical(["ASSET-1"]),
        "media_payload_sha256": canonical(payload),
        "channel": "Facebook",
        "objective": "farm_awareness",
        "confirmed": True,
        "policy_passed": True,
    }


def observation(asset_hash="a" * 64):
    return [{
        "asset_id": "ASSET-1",
        "asset_sha256": asset_hash,
        "evidence_state": "qualified_visual_observation",
        "provenance": {
            "source_type": "model_visual_review",
            "observer_identity": "visual-model",
            "observer_version": "v1",
            "observed_at": "2026-07-26T10:00:00Z",
            "confidence": "medium",
        },
        "observation": {
            "visible_subject": "One pig is visible.",
            "setting": "A farm pen is visible.",
            "supports": ["one visible pig"],
            "does_not_support": ["identity", "availability"],
        },
    }]


def persisted(event_kind, post, identity, payload, window=""):
    from modules.beacon.organic_media_intelligence import _canonical_event_payload, _hash
    row = {
        "event_id": f"event-{event_kind}-{identity}",
        "event_kind": event_kind,
        "facebook_post_id": post,
        "channel": "Facebook",
        "objective": "farm_awareness",
        "measurement_window": window,
        "evidence_key": f"evidence/{event_kind}/{identity}",
        "payload": payload,
    }
    row["payload"] = _canonical_event_payload(row)
    row["payload_sha256"] = _hash(row["payload"])
    row["payload_json"] = row["payload"]
    return row


def graduate(rows):
    with patch(
        "modules.beacon.organic_media_intelligence._load_persisted_events",
        return_value=(rows, True),
    ):
        return evaluate_graduation()


def graduation_events(count=3, policy_failure=False):
    rows = []
    for number in range(count):
        post = f"post-{number}"
        rows.extend([
            persisted("confirmed_publication", post, str(number),
                      {"delivery_verified": True}),
            persisted("policy_evaluation", post, str(number),
                      {"policy_passed": not (policy_failure and number == 0)}),
            persisted("performance_snapshot", post, str(number),
                      {"metrics": {"reach": {"status": "verified", "value": number}}},
                      "72_hours"),
            persisted("owner_usefulness_rating", post, str(number),
                      {"rating_id": f"rating-{number}"}),
            persisted("publication_reliability", post, str(number),
                      {"publication_run_id": f"run-{number}", "reliable": True}),
        ])
    return rows


class OrganicMediaIntelligenceTests(unittest.TestCase):
    def test_generic_report_binds_canonical_identities_and_provenance(self):
        report = build_organic_learning_report(
            publication(), media(), observation(), case_label="Fixture only"
        )
        self.assertTrue(report["success"])
        self.assertEqual(report["case_label"], "Fixture only")
        self.assertEqual(report["publication"]["exact_media_order"], ["ASSET-1"])
        self.assertEqual(
            report["media_understanding"]["packets"][0]["provenance"]["observer_version"],
            "v1",
        )

    def test_unseen_media_without_observation_is_unavailable(self):
        report = build_organic_learning_report(publication(), media(), [])
        self.assertEqual(
            report["media_understanding"]["status"],
            "media_understanding_unavailable",
        )
        self.assertEqual(report["media_understanding"]["packets"], [])

    def test_different_asset_hash_cannot_inherit_observation(self):
        report = build_organic_learning_report(
            publication("b" * 64), media("b" * 64), observation("a" * 64)
        )
        self.assertTrue(report["success"])
        self.assertEqual(
            report["media_understanding"]["status"],
            "media_understanding_unavailable",
        )

    def test_three_records_for_one_post_do_not_satisfy_threshold(self):
        rows = graduation_events(1) * 3
        result = graduate(rows)
        self.assertEqual(result["observed"]["distinct_confirmed_posts"], 1)
        self.assertFalse(result["eligible_for_owner_review_candidate"])

    def test_unpersisted_caller_records_cannot_graduate(self):
        self.assertEqual(
            evaluate_graduation(database_url="")["observed"]["distinct_confirmed_posts"],
            0,
        )

    def test_reliable_runs_for_one_post_do_not_cover_three_posts(self):
        rows = graduation_events()
        reliability = [
            persisted("publication_reliability", "post-0", f"extra-{number}",
                      {"publication_run_id": f"extra-run-{number}", "reliable": True})
            for number in range(3)
        ]
        rows = [row for row in rows if row["event_kind"] != "publication_reliability"]
        self.assertFalse(
            graduate(rows + reliability)["eligible_for_owner_review_candidate"]
        )

    def test_missing_ratings_or_windows_blocks(self):
        rows = [
            row for row in graduation_events()
            if row["event_kind"] not in {"owner_usefulness_rating", "performance_snapshot"}
        ]
        self.assertFalse(graduate(rows)["eligible_for_owner_review_candidate"])

    def test_single_policy_failure_blocks_graduation(self):
        result = graduate(graduation_events(policy_failure=True))
        self.assertEqual(result["observed"]["policy_failure_count"], 1)
        self.assertFalse(result["eligible_for_owner_review_candidate"])

    def test_distinct_persisted_evidence_only_creates_owner_review_candidate(self):
        result = graduate(graduation_events())
        self.assertTrue(result["eligible_for_owner_review_candidate"])
        self.assertEqual(result["observed"]["policy_pass_rate"], 1.0)
        self.assertFalse(result["automatic_authority_granted"])

    def test_equivalent_event_replay_and_conflict(self):
        event = {
            "event_id": "LEARN-1", "event_kind": "post_understanding",
            "facebook_post_id": POST, "channel": "Facebook",
            "objective": "farm_awareness", "evidence_key": "post/v1",
            "payload": {"status": "ready"},
        }
        result, status = append_learning_event(event, database_url="")
        self.assertEqual(status, 503)
        self.assertEqual(result["status"], "organic_learning_persistence_unavailable")

    def test_strict_authority_and_window_validation(self):
        event = {
            "event_id": "LEARN-2", "event_kind": "performance_snapshot",
            "facebook_post_id": POST, "channel": "Facebook",
            "objective": "farm_awareness", "evidence_key": "snapshot/v1",
            "measurement_window": "two_hours",
            "payload": {"metrics": {"reach": {"status": "missing", "value": None}}},
        }
        result, status = append_learning_event(event, database_url="configured")
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "organic_learning_window_incompatible")
        event["measurement_window"] = "72_hours"
        event["publish"] = True
        result, status = append_learning_event(event, database_url="configured")
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "organic_learning_authority_prohibited")

    def test_first_case_is_data_fixture_not_engine_constant(self):
        source = Path("modules/beacon/organic_media_intelligence.py").read_text()
        fixture = json.loads(Path(
            "modules/beacon/fixtures/first_production_learning_case.json"
        ).read_text(encoding="utf-8"))
        self.assertNotIn(fixture["publication"]["facebook_post_id"], source)
        self.assertEqual(fixture["case_label"], "First production learning case")

    def test_migration_privileges_append_only_and_no_action(self):
        sql = Path(
            "supabase/migrations/202607260008_create_beacon_organic_media_learning.sql"
        ).read_text(encoding="utf-8").lower()
        self.assertIn("enable row level security", sql)
        self.assertIn("from public, anon, authenticated, service_role", sql)
        self.assertNotIn("grant execute on function", sql)
        self.assertIn("grant select, insert", sql)
        self.assertIn("before update", sql)
        self.assertIn("before delete", sql)
        for column in ("publish", "retry", "schedule", "meta_write",
                       "boost", "advertise", "spend", "send"):
            self.assertIn(f"{column} boolean not null default false", sql)


if __name__ == "__main__":
    unittest.main()
