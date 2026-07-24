import json
import unittest

from modules.beacon.meta_ads_evidence_import import (
    execute_meta_ads_import_packet,
    incorrect_batch_exclusion_plan,
    prepare_meta_ads_import_packet,
)


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        self.rowcount = 0
        if normalized.startswith("select performance_event_id"):
            logical = set((params or {}).get("logical_keys") or [])
            self.rows = [
                (
                    row["performance_event_id"],
                    row["source_snapshot_key"],
                    row.get("supersedes_event_id"),
                    row.get("metric_evidence") or {},
                    row.get("created_at") or "2026-07-20T00:00:00+00:00",
                )
                for row in self.connection.rows
                if row.get("evidence_source") == "meta_ads_insights"
                and (
                    (
                        (row.get("metric_evidence") or {}).get("spend_amount")
                        or {}
                    ).get("meta_import") or {}
                ).get("logical_snapshot_key") in logical
            ]
        elif normalized.startswith("select count(*)"):
            if "coalesce(evidence_source" in normalized:
                count = sum(
                    row.get("evidence_source", "legacy_unlabelled")
                    != "meta_ads_insights"
                    for row in self.connection.rows
                )
            else:
                count = len(self.connection.rows)
            self.rows = [(count,)]
        elif normalized.startswith("insert into public.beacon_campaign_performance_events"):
            if any(
                row.get("performance_event_id") == params["performance_event_id"]
                for row in self.connection.rows
            ):
                self.rowcount = 0
                return
            evidence = json.loads(params["metric_evidence_json"])
            self.connection.rows.append({
                "performance_event_id": params["performance_event_id"],
                "source_snapshot_key": params["source_snapshot_key"],
                "supersedes_event_id": params.get("supersedes_event_id"),
                "metric_evidence": evidence,
                "evidence_source": "meta_ads_insights",
                "retrieved_at": params["retrieved_at"],
                "created_at": "2026-07-24T12:00:01+00:00",
            })
            self.rowcount = 1
            self.rows = []
        else:
            raise AssertionError(f"unexpected SQL: {normalized[:100]}")

    def fetchall(self):
        return list(self.rows)

    def fetchone(self):
        return self.rows[0]


class FakeConnection:
    def __init__(self, rows=None):
        self.rows = list(rows or [])
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


def preview_event(*, spend=0, reach=None, retrieved_at="2026-07-24T12:00:00+00:00"):
    def metric(name, value):
        return {
            "metric": name,
            "status": "verified" if value is not None else "missing",
            "value": value,
            "source": "meta_ads_insights",
            "source_reference": "meta_ads_insights/ad/AD-1/2026-07-01/2026-07-14",
            "retrieved_at": retrieved_at,
        }

    return {
        "source": "meta_ads_insights",
        "source_reference": "meta_ads_insights/ad/AD-1/2026-07-01/2026-07-14",
        "retrieved_at": retrieved_at,
        "reporting_window": {"start": "2026-07-01", "end": "2026-07-14"},
        "level": "ad",
        "identity": {
            "campaign_id": "CAMPAIGN-1",
            "adset_id": "ADSET-1",
            "ad_id": "AD-1",
        },
        "currency": {"status": "verified", "value": "ZAR"},
        "attribution": {"status": "verified", "setting": "7d_click_1d_view"},
        "metrics": {
            "spend": metric("spend", spend),
            "reach": metric("reach", reach),
            "impressions": metric("impressions", 0),
            "clicks": metric("clicks", 0),
            "inline_link_clicks": metric("inline_link_clicks", 0),
        },
        "actions": {
            "status": "verified",
            "items": [{
                "action_type": "link_click",
                "value": 0,
                "status": "verified",
                "classification": "meta_reported_action_only",
            }],
        },
        "qualified_buyer_leads": {"status": "unsupported", "value": None},
        "orders": {"status": "unsupported", "value": None},
        "sales": {"status": "unsupported", "value": None},
        "revenue": {"status": "unsupported", "value": None},
    }


def preview_builder(event):
    def build(**kwargs):
        return {
            "status": "preview_ready",
            "reporting_window": {
                "start": kwargs["start_date"],
                "end": kwargs["end_date"],
                "level": kwargs["level"],
            },
            "retrieved_at": event["retrieved_at"],
            "account_currency": {"status": "verified", "value": "ZAR"},
            "proposed_append_only_events": [event],
            "blockers": [],
        }, 200
    return build


class BeaconMetaAdsEvidenceImportTests(unittest.TestCase):
    def setUp(self):
        self.connection = FakeConnection([
            {
                "performance_event_id": f"LEGACY-{index}",
                "evidence_source": "legacy_unlabelled",
                "source_snapshot_key": None,
            }
            for index in range(64)
        ])
        self.connect = lambda _url: self.connection

    def prepare(self, event=None, now="2026-07-24T12:00:00+00:00"):
        return prepare_meta_ads_import_packet(
            start_date="2026-07-01",
            end_date="2026-07-14",
            level="ad",
            preview_builder=preview_builder(event or preview_event()),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now=now,
        )

    def approval(self, prepared):
        return {
            "owner_approved": True,
            "packet": prepared["packet"],
            "packet_hash": prepared["packet_hash"],
            "approved_packet_hash": prepared["packet_hash"],
            "approval_signature": prepared["approval_signature"],
        }

    def test_packet_hash_binds_exact_packet_and_credentials_are_absent(self):
        prepared, status = self.prepare()
        self.assertEqual(status, 200)
        self.assertEqual(prepared["proposed_insert_count"], 1)
        serialized = json.dumps(prepared, sort_keys=True)
        self.assertNotIn("access_token", serialized.lower())
        self.assertNotIn("BEACON_META_AD_ACCOUNT_ID", serialized)
        changed = self.approval(prepared)
        changed["packet"]["reporting_window"]["end"] = "2026-07-15"
        rejected, status = execute_meta_ads_import_packet(
            changed, database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:01:00+00:00",
        )
        self.assertEqual(status, 409)
        self.assertEqual(rejected["status"], "packet_hash_mismatch")
        self.assertEqual(len(self.connection.rows), 64)

    def test_expired_and_unapproved_packets_are_rejected(self):
        prepared, _ = self.prepare()
        unapproved = self.approval(prepared)
        unapproved["owner_approved"] = False
        result, status = execute_meta_ads_import_packet(unapproved)
        self.assertEqual((status, result["status"]), (403, "owner_exact_packet_approval_required"))
        result, status = execute_meta_ads_import_packet(
            self.approval(prepared),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:11:00+00:00",
        )
        self.assertEqual((status, result["status"]), (409, "packet_expired"))
        self.assertEqual(len(self.connection.rows), 64)

    def test_append_only_insert_preserves_verified_zero_and_missing(self):
        prepared, _ = self.prepare(preview_event(spend=0, reach=None))
        item = prepared["packet"]["items"][0]
        self.assertEqual(item["evidence"]["metrics"]["spend"]["status"], "verified")
        self.assertEqual(item["evidence"]["metrics"]["spend"]["value"], 0)
        self.assertEqual(item["evidence"]["metrics"]["reach"]["status"], "missing")
        self.assertIsNone(item["evidence"]["metrics"]["reach"]["value"])
        result, status = execute_meta_ads_import_packet(
            self.approval(prepared),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:01:00+00:00",
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["created_count"], 1)
        self.assertTrue(result["legacy_rows_untouched"])
        self.assertEqual(len(self.connection.rows), 65)
        imported = self.connection.rows[-1]["metric_evidence"]
        self.assertEqual(imported["spend_amount"]["value"], 0)
        self.assertIsNone(imported["reach"]["value"])
        self.assertEqual(
            imported["spend_amount"]["meta_reported_actions"]["items"][0][
                "classification"
            ],
            "meta_reported_action_only",
        )
        self.assertEqual(
            imported["qualified_buyer_leads"]["status"], "unsupported"
        )

    def test_duplicate_is_withheld_idempotently(self):
        prepared, _ = self.prepare()
        first, _ = execute_meta_ads_import_packet(
            self.approval(prepared),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:01:00+00:00",
        )
        self.assertEqual(first["created_count"], 1)
        duplicate, _ = self.prepare(
            preview_event(retrieved_at="2026-07-24T12:02:00+00:00"),
            now="2026-07-24T12:02:00+00:00",
        )
        self.assertEqual(duplicate["existing_duplicate_count"], 1)
        self.assertEqual(duplicate["proposed_insert_count"], 0)
        result, status = execute_meta_ads_import_packet(
            self.approval(duplicate),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:03:00+00:00",
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["created_count"], 0)
        self.assertEqual(result["duplicate_withheld_count"], 1)
        self.assertEqual(len(self.connection.rows), 65)

    def test_changed_evidence_appends_traceable_correction(self):
        original, _ = self.prepare(preview_event(spend=1))
        execute_meta_ads_import_packet(
            self.approval(original),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:01:00+00:00",
        )
        original_id = self.connection.rows[-1]["performance_event_id"]
        correction, _ = self.prepare(
            preview_event(spend=2, retrieved_at="2026-07-24T12:02:00+00:00"),
            now="2026-07-24T12:02:00+00:00",
        )
        self.assertEqual(correction["correction_supersession_count"], 1)
        item = correction["packet"]["items"][0]
        self.assertEqual(item["disposition"], "correction")
        self.assertEqual(item["supersedes_event_id"], original_id)
        result, status = execute_meta_ads_import_packet(
            self.approval(correction),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:03:00+00:00",
        )
        self.assertEqual(status, 201)
        self.assertEqual(self.connection.rows[-1]["supersedes_event_id"], original_id)
        self.assertEqual(len(self.connection.rows), 66)

    def test_changed_attribution_appends_correction_not_unrelated_snapshot(self):
        original, _ = self.prepare()
        execute_meta_ads_import_packet(
            self.approval(original),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:01:00+00:00",
        )
        original_id = self.connection.rows[-1]["performance_event_id"]
        changed = preview_event(retrieved_at="2026-07-24T12:02:00+00:00")
        changed["attribution"]["setting"] = "1d_click"
        correction, _ = self.prepare(
            changed, now="2026-07-24T12:02:00+00:00"
        )
        item = correction["packet"]["items"][0]
        self.assertEqual(item["disposition"], "correction")
        self.assertEqual(item["supersedes_event_id"], original_id)

    def test_database_state_change_after_prepare_rejects_packet(self):
        prepared, _ = self.prepare()
        item = prepared["packet"]["items"][0]
        self.connection.rows.append({
            "performance_event_id": item["performance_event_id"],
            "source_snapshot_key": item["source_snapshot_key"],
            "supersedes_event_id": None,
            "metric_evidence": {
                "spend_amount": {
                    "meta_import": {
                        "logical_snapshot_key": item["logical_snapshot_key"],
                    }
                }
            },
            "evidence_source": "meta_ads_insights",
        })
        result, status = execute_meta_ads_import_packet(
            self.approval(prepared),
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:01:00+00:00",
        )
        self.assertEqual((status, result["status"]), (409, "packet_database_state_changed"))
        self.assertTrue(self.connection.rolled_back)

    def test_authority_and_exclusion_rollback_contract(self):
        prepared, _ = self.prepare()
        for name in (
            "automatic_import", "calls_meta_write",
            "creates_or_updates_campaigns", "creates_or_updates_ads",
            "publishes_content", "sends_customer_messages", "spends_money",
            "changes_budget_or_payment", "writes_business_or_farm_data",
            "updates_existing_evidence", "deletes_existing_evidence",
        ):
            self.assertFalse(prepared[name])
        self.assertTrue(prepared["owner_approved_evidence_append_only"])
        self.assertEqual(
            prepared["packet"]["database_snapshot"]["legacy_row_count"], 64
        )
        plan = incorrect_batch_exclusion_plan("BATCH-1", ["E1", "E2"])
        self.assertFalse(plan["updates_allowed"])
        self.assertFalse(plan["deletes_allowed"])
        self.assertFalse(plan["automatic_exclusion"])
        self.assertEqual(plan["affected_event_count"], 2)
        self.assertIn("supersedes_event_id", " ".join(plan["procedure"]))

    def test_proven_seventeen_event_dry_run_packet_is_insert_only(self):
        events = []
        for index in range(17):
            event = preview_event(spend=0, reach=0)
            event["identity"] = {
                "campaign_id": f"CAMPAIGN-{index}",
                "adset_id": f"ADSET-{index}",
                "ad_id": f"AD-{index}",
            }
            reference = (
                f"meta_ads_insights/ad/AD-{index}/"
                "2026-07-01/2026-07-14"
            )
            event["source_reference"] = reference
            for metric in event["metrics"].values():
                metric["source_reference"] = reference
            events.append(event)

        def builder(**kwargs):
            return {
                "status": "preview_ready",
                "reporting_window": {
                    "start": kwargs["start_date"],
                    "end": kwargs["end_date"],
                    "level": kwargs["level"],
                },
                "retrieved_at": "2026-07-24T12:00:00+00:00",
                "account_currency": {"status": "verified", "value": "ZAR"},
                "proposed_append_only_events": events,
                "blockers": [],
            }, 200

        prepared, status = prepare_meta_ads_import_packet(
            start_date="2026-07-01",
            end_date="2026-07-14",
            level="ad",
            preview_builder=builder,
            database_url="postgresql://fake",
            connect_factory=self.connect,
            now="2026-07-24T12:00:00+00:00",
        )
        self.assertEqual(status, 200)
        self.assertEqual(prepared["proposed_insert_count"], 17)
        self.assertEqual(prepared["existing_duplicate_count"], 0)
        self.assertEqual(prepared["correction_supersession_count"], 0)
        self.assertEqual(prepared["excluded_count"], 0)
        self.assertEqual(len(prepared["packet"]["items"]), 17)


if __name__ == "__main__":
    unittest.main()
