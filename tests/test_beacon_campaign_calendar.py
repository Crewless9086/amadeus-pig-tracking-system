import hashlib
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app import app
from modules.beacon.campaign_calendar import (
    RULE_LIFECYCLE_REGISTRY,
    RuleLifecycleRegistry,
    approve_rule_version,
    evaluate_prepared_entry,
    prepare_calendar_entry,
    propose_rule_version,
    revoke_rule_version,
)
from modules.sales import sales_transaction_routes


NOW = datetime(2026, 7, 14, 10, 0, tzinfo=timezone.utc)


def approved_rule():
    proposed = propose_rule_version({
        "rule_id": "RULE-1", "campaign_lane": "meat_launch",
        "allowed_channels": ["facebook", "whatsapp_status"],
        "timezone": "Africa/Johannesburg",
        "window_start": "2026-07-14T11:00:00+02:00",
        "window_end": "2026-07-14T14:00:00+02:00",
        "demand_unit": "carcass_halves",
    }, now=NOW)["rule"]
    return approve_rule_version(proposed, "owner-charl", approved_at=NOW)["rule"]


def valid_payload():
    copy = "Fresh farm pork preorder. Availability subject to confirmation."
    asset_hash = "a" * 64
    return {
        "rule": approved_rule(), "channel": "facebook", "exact_copy": copy,
        "copy_sha256": hashlib.sha256(copy.encode()).hexdigest(), "copy_source_id": "COPY-1",
        "asset": {"asset_id": "ASSET-1", "effective_approval_status": "approved",
                  "effective_public_use_approved": True, "privacy_risk": "low",
                  "content_sha256": asset_hash, "verified_content_sha256": asset_hash,
                  "sale_stream_relevance": ["meat_launch"], "latest_event": {}},
        "demand_evidence": {"unit": "carcass_halves", "recorded_at": NOW.isoformat(),
                            "max_age_seconds": 3600, "source": "supabase_fulfilment",
                            "source_record_ids": ["FUL-1"], "verified_availability": 12,
                            "commitments": 3, "operational_reserve": 2, "safety_buffer": 1},
        "requested_target": 10, "pauses": [],
    }


class BeaconCampaignCalendarTests(unittest.TestCase):
    def setUp(self):
        RULE_LIFECYCLE_REGISTRY.clear()

    def test_approval_is_evidence_only_and_approved_version_is_content_bound(self):
        proposed = propose_rule_version({
            "rule_id": "R", "campaign_lane": "meat_launch", "allowed_channels": ["facebook"],
            "timezone": "Africa/Johannesburg", "window_start": "2026-07-14T11:00:00+02:00",
            "window_end": "2026-07-14T12:00:00+02:00", "demand_unit": "halves",
        }, now=NOW)["rule"]
        result = approve_rule_version(proposed, "owner", approved_at=NOW)
        self.assertTrue(result["success"])
        self.assertEqual(result["calendar_entries"], [])
        self.assertFalse(result["authority"]["dispatch_enabled"])
        tampered = result["rule"].copy(); tampered["allowed_channels"] = ["instagram"]
        blocked = prepare_calendar_entry({**valid_payload(), "rule": tampered}, now=NOW)
        self.assertIn("rule_content_hash_mismatch", blocked["errors"])

    def test_change_creates_new_proposed_version_requiring_fresh_approval(self):
        first = approved_rule()
        changed = propose_rule_version({**first, "allowed_channels": ["instagram"]}, previous_version=first, now=NOW)["rule"]
        self.assertEqual(changed["version"], 2)
        self.assertEqual(changed["status"], "proposed")
        self.assertEqual(changed["supersedes_version"], 1)
        self.assertIn("rule_proposed", prepare_calendar_entry({**valid_payload(), "rule": changed}, now=NOW)["errors"])
        self.assertIn("rule_superseded", prepare_calendar_entry({**valid_payload(), "rule": first}, now=NOW)["errors"])

    def test_forged_approval_fields_are_not_authoritative(self):
        forged = approved_rule()
        RULE_LIFECYCLE_REGISTRY.clear()
        payload = valid_payload()
        RULE_LIFECYCLE_REGISTRY.clear()
        payload["rule"] = forged
        result = prepare_calendar_entry(payload, now=NOW)
        self.assertFalse(result["success"])
        self.assertIn("owner_approval_not_authoritative", result["errors"])

    def test_inactive_rule_states_cannot_prepare(self):
        for status in ("proposed", "revoked", "expired", "superseded"):
            payload = valid_payload(); payload["rule"]["status"] = status
            result = prepare_calendar_entry(payload, now=NOW)
            self.assertFalse(result["success"], status)

    def test_happy_path_snapshots_lineage_and_clamps_cap(self):
        result = prepare_calendar_entry(valid_payload(), now=NOW)
        self.assertTrue(result["success"], result["errors"])
        entry = result["calendar_entry"]
        self.assertEqual(entry["calculated_cap"], 6)
        self.assertEqual(entry["approval"]["approved_by"], "owner-charl")
        self.assertEqual(entry["copy"]["source_id"], "COPY-1")
        self.assertFalse(entry["authority"]["posts_publicly"])
        original = entry["copy"]["exact"]
        payload = valid_payload(); payload["exact_copy"] = "changed"
        self.assertEqual(entry["copy"]["exact"], original)

    def test_assets_fail_closed(self):
        cases = [
            ("effective_approval_status", "rejected", "asset_not_effectively_approved"),
            ("effective_public_use_approved", False, "asset_public_use_not_approved"),
            ("archived", True, "asset_archived"),
            ("privacy_risk", "blocked", "asset_privacy_blocked"),
            ("verified_content_sha256", "b" * 64, "asset_integrity_unverified"),
            ("sale_stream_relevance", ["live_stock_awareness"], "asset_campaign_lane_incompatible"),
        ]
        for key, value, error in cases:
            payload = valid_payload(); payload["asset"][key] = value
            self.assertIn(error, prepare_calendar_entry(payload, now=NOW)["errors"])

    def test_channel_window_and_copy_fail_closed(self):
        payload = valid_payload(); payload["channel"] = "unknown"
        self.assertIn("channel_not_allowed", prepare_calendar_entry(payload, now=NOW)["errors"])
        payload = valid_payload(); payload["copy_sha256"] = "tampered"
        self.assertIn("exact_copy_source_hash_mismatch", prepare_calendar_entry(payload, now=NOW)["errors"])
        payload = valid_payload(); payload["rule"]["timezone"] = "Mars/Olympus"
        self.assertIn("invalid_iana_timezone", prepare_calendar_entry(payload, now=NOW)["errors"])
        payload = valid_payload()
        self.assertIn("outside_campaign_window", prepare_calendar_entry(payload, now=datetime(2026, 7, 14, 12, 0, tzinfo=timezone.utc))["errors"])

    def test_dst_gap_and_ambiguous_local_windows_fail_closed(self):
        payload = valid_payload(); payload["rule"].update({
            "timezone": "America/New_York", "window_start": "2026-03-08T02:30:00-05:00",
            "window_end": "2026-03-08T04:00:00-04:00"})
        self.assertIn("window_timezone_offset_invalid", prepare_calendar_entry(payload, now=NOW)["errors"])
        payload = valid_payload(); payload["rule"].update({
            "timezone": "America/New_York", "window_start": "2026-11-01T01:15:00-04:00",
            "window_end": "2026-11-01T02:30:00-05:00"})
        self.assertIn("window_dst_ambiguous", prepare_calendar_entry(payload, now=NOW)["errors"])

    def test_demand_failures_and_cap_floor(self):
        for mutation, expected in [
            ({"unit": "kg"}, "demand_unit_mismatch"),
            ({"recorded_at": "2020-01-01T00:00:00+00:00"}, "demand_evidence_stale"),
            ({"source_record_ids": []}, "demand_provenance_required"),
            ({"verified_availability": 2, "commitments": 3}, "demand_capacity_zero"),
        ]:
            payload = valid_payload(); payload["demand_evidence"].update(mutation)
            result = prepare_calendar_entry(payload, now=NOW)
            self.assertIn(expected, result["errors"])
            if expected == "demand_capacity_zero": self.assertEqual(result["calculated_cap"], 0)

    def test_all_pause_scopes_block_with_machine_reasons(self):
        targets = {"global": "*", "rule": "RULE-1", "channel": "facebook",
                   "campaign": "meat_launch", "asset": "ASSET-1", "fulfilment": "carcass_halves"}
        payload = valid_payload()
        payload["pauses"] = [{"scope": scope, "target": target, "active": True, "reason_code": "owner_hold"}
                              for scope, target in targets.items()]
        result = prepare_calendar_entry(payload, now=NOW)
        self.assertEqual(len(result["pause_reasons"]), 6)
        self.assertTrue(all(reason.startswith("pause_") for reason in result["pause_reasons"]))

    def test_revocation_blocks_current_use_without_rewriting_entry(self):
        payload = valid_payload()
        entry = prepare_calendar_entry(payload, now=NOW)["calendar_entry"]
        snapshot = entry["snapshot_sha256"]
        result = revoke_rule_version("RULE-1", 1, "owner-charl", revoked_at=NOW)
        self.assertTrue(result["success"])
        self.assertEqual(result["calendar_entries"], [])
        self.assertIn("rule_revoked", prepare_calendar_entry(payload, now=NOW)["errors"])
        evaluated = evaluate_prepared_entry(entry)
        self.assertTrue(evaluated["currently_blocked"])
        self.assertIn("rule_revoked", evaluated["reasons"])
        self.assertEqual(evaluated["entry"]["snapshot_sha256"], snapshot)

    def test_lifecycle_authority_survives_registry_restart_and_is_shared(self):
        path = RULE_LIFECYCLE_REGISTRY.database_path
        approved = approved_rule()
        restarted = RuleLifecycleRegistry(path)
        self.assertEqual(restarted.approved_rule("RULE-1", 1)["approval_id"], approved["approval_id"])
        revoke_rule_version("RULE-1", 1, "owner-charl", revoked_at=NOW, registry=restarted)
        self.assertEqual(RULE_LIFECYCLE_REGISTRY.latest_rule("RULE-1")["status"], "revoked")

    def test_routes_are_owner_guarded_and_never_execute_external_actions(self):
        app.testing = True
        client = app.test_client()
        denial = ({"success": False, "status": "owner_admin_required"}, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=denial):
            for route in ("rules/propose", "rules/approve", "rules/revoke", "prepare"):
                response = client.post("/api/beacon/campaign-calendar/" + route, json={})
                self.assertEqual(response.status_code, 403)
        with patch.object(sales_transaction_routes, "require_owner_admin_access", return_value=None), \
             patch.object(sales_transaction_routes, "prepare_calendar_entry", return_value={"success": True, "status": "prepared"}) as prepare:
            response = client.post("/api/beacon/campaign-calendar/prepare", json=valid_payload())
            self.assertEqual(response.status_code, 200)
            prepare.assert_called_once()


if __name__ == "__main__":
    unittest.main()
