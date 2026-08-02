import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

from app import app
from modules.telemetry.rootline_operating_policy import (
    AUTHORITY,
    InMemoryPolicyStore,
    PolicyConflictError,
    PolicyValidationError,
    activate_policy,
    normalize_policy_snapshot,
    policy_review_contract,
    prepare_policy_proposal,
    preview_policy_effect,
    propose_policy,
    review_policy,
)


NOW = datetime(2026, 7, 27, 16, 0, tzinfo=timezone.utc)
OWNER_ENV = {
    "OWNER_ACCESS_ENABLED": "1",
    "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
    "OWNER_READ_TOKEN": "r" * 40,
    "OWNER_ADMIN_TOKEN": "a" * 40,
    "OWNER_SESSION_SECRET": "rootline-policy-test-secret",
}


def unknown_policy():
    return {
        "seasonal_boundaries": "Unknown",
        "zones": {
            zone_id: {
                "daylight_window": "Unknown",
                "minimum_useful_runtime_minutes": "Unknown",
                "maximum_continuous_runtime_minutes": "Unknown",
            }
            for zone_id in ("B12345", "C12345")
        },
        "forecast_rain": "Unknown",
        "live_rain_hold": "Unknown",
        "temperature_limits": "Unknown",
        "crop_need_bands": {"B12345": "Unknown", "C12345": "Unknown"},
        "controller_power_loss": "Unknown",
        "residual_drainage": "Unknown",
    }


def proposal_payload(key="proposal-1", policy=None):
    return {
        "idempotency_key": key,
        "evidence": {"owner_note": "Deliberate initial Unknown baseline"},
        "policy": policy or unknown_policy(),
    }


def approved_dry_release():
    return {
        "dry_interval_minutes": 30,
        "dry_rain_rate_mm_per_hour": 0.0,
        "minimum_fresh_station_readings": 2,
        "visible_rain_confirmation_required": True,
        "owner_review_required": True,
    }


class RootlineOperatingPolicyTests(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryPolicyStore()

    def test_contract_is_three_stage_and_command_inert(self):
        contract = policy_review_contract()
        self.assertEqual(
            contract["lifecycle"], ["proposed", "owner_reviewed", "active_for_advice"]
        )
        self.assertFalse(contract["canary_runtime_is_policy_input"])
        self.assertFalse(contract["measured_water_inferred"])
        self.assertTrue(all(value is False for value in AUTHORITY.values()))

    def test_unknown_is_a_valid_deliberate_value(self):
        result = normalize_policy_snapshot(unknown_policy())
        self.assertEqual(result["seasonal_boundaries"], "Unknown")
        self.assertEqual(result["zones"]["B12345"]["daylight_window"], "Unknown")
        self.assertEqual(result["crop_need_bands"]["C12345"], "Unknown")
        self.assertEqual(result["live_rain_hold"], "Unknown")

    def test_confirmed_live_rain_hold_is_valid_with_every_other_rule_unknown(self):
        payload = unknown_policy()
        payload["live_rain_hold"] = {
            "evidence_field": "current_rain_rate_mm_per_hour",
            "threshold_mm_per_hour": 0.2,
            "comparison": "greater_than",
            "release_policy": "Unknown",
        }
        normalized = normalize_policy_snapshot(payload)
        self.assertEqual(normalized["live_rain_hold"]["threshold_mm_per_hour"], 0.2)
        self.assertEqual(normalized["live_rain_hold"]["comparison"], "greater_than")
        self.assertEqual(normalized["live_rain_hold"]["release_policy"], "Unknown")
        self.assertEqual(normalized["forecast_rain"], "Unknown")
        preview, status = preview_policy_effect(payload, {"status": "needs_data"})
        self.assertEqual(status, 200)
        self.assertTrue(preview["proposal_can_be_recorded"])
        self.assertEqual(preview["eligibility_after_preview"], "Needs Data")

    def test_exact_threshold_does_not_mean_greater_than(self):
        payload = unknown_policy()
        payload["live_rain_hold"] = {
            "evidence_field": "current_rain_rate_mm_per_hour",
            "threshold_mm_per_hour": 0.2,
            "comparison": "greater_than",
            "release_policy": "Unknown",
        }
        rule = normalize_policy_snapshot(payload)["live_rain_hold"]
        self.assertFalse(0.2 > rule["threshold_mm_per_hour"])
        self.assertTrue(0.21 > rule["threshold_mm_per_hour"])

    def test_owner_confirmed_dry_release_contract_is_exact(self):
        payload = unknown_policy()
        payload["live_rain_hold"] = {
            "evidence_field": "current_rain_rate_mm_per_hour",
            "threshold_mm_per_hour": 0.2,
            "comparison": "greater_than",
            "release_policy": approved_dry_release(),
        }
        normalized = normalize_policy_snapshot(payload)
        self.assertEqual(
            normalized["live_rain_hold"]["release_policy"],
            approved_dry_release(),
        )
        preview, status = preview_policy_effect(payload, {"status": "hold"})
        self.assertEqual(status, 200)
        self.assertTrue(preview["proposal_can_be_recorded"])
        self.assertIn("live_rain_hold", preview["resolved_policy_inputs"])
        self.assertEqual(preview["eligibility_after_preview"], "Needs Data")

    def test_dry_release_contract_variants_fail_closed(self):
        mutations = (
            ("dry_interval_minutes", 29),
            ("dry_rain_rate_mm_per_hour", 0.1),
            ("minimum_fresh_station_readings", 1),
            ("visible_rain_confirmation_required", False),
            ("owner_review_required", False),
        )
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                release = approved_dry_release()
                release[key] = value
                payload = unknown_policy()
                payload["live_rain_hold"] = {
                    "evidence_field": "current_rain_rate_mm_per_hour",
                    "threshold_mm_per_hour": 0.2,
                    "comparison": "greater_than",
                    "release_policy": release,
                }
                with self.assertRaises(PolicyValidationError):
                    normalize_policy_snapshot(payload)

    def test_unconfirmed_live_rain_thresholds_are_rejected(self):
        for threshold in (0, 0.19, 0.21, 0.3, 100):
            with self.subTest(threshold=threshold):
                payload = unknown_policy()
                payload["live_rain_hold"] = {
                    "evidence_field": "current_rain_rate_mm_per_hour",
                    "threshold_mm_per_hour": threshold,
                    "comparison": "greater_than",
                    "release_policy": "Unknown",
                }
                with self.assertRaisesRegex(
                    PolicyValidationError, "not_owner_confirmed"
                ):
                    normalize_policy_snapshot(payload)

    def test_exact_zone_identity_is_required(self):
        payload = unknown_policy()
        payload["zones"].pop("C12345")
        with self.assertRaisesRegex(PolicyValidationError, "exact_zone"):
            normalize_policy_snapshot(payload)

    def test_units_ranges_and_time_windows_are_validated(self):
        payload = unknown_policy()
        payload["zones"]["B12345"] = {
            "daylight_window": {"start": "18:00", "end": "06:00"},
            "minimum_useful_runtime_minutes": 10,
            "maximum_continuous_runtime_minutes": 20,
        }
        with self.assertRaisesRegex(PolicyConflictError, "must_not_cross_midnight"):
            normalize_policy_snapshot(payload)
        payload["zones"]["B12345"]["daylight_window"] = {
            "start": "06:00",
            "end": "18:00",
        }
        payload["forecast_rain"] = {
            "amount_mm": 5,
            "probability_pct": 101,
            "horizon_hours": 24,
        }
        with self.assertRaisesRegex(PolicyValidationError, "probability"):
            normalize_policy_snapshot(payload)

    def test_conflicting_runtime_and_crop_bands_are_rejected(self):
        payload = unknown_policy()
        payload["zones"]["C12345"] = {
            "daylight_window": "Unknown",
            "minimum_useful_runtime_minutes": 40,
            "maximum_continuous_runtime_minutes": 20,
        }
        with self.assertRaisesRegex(PolicyConflictError, "minimum_runtime"):
            normalize_policy_snapshot(payload)
        payload = unknown_policy()
        payload["crop_need_bands"]["B12345"] = {
            "low_mm_per_day": 5,
            "medium_mm_per_day": 4,
            "high_mm_per_day": 8,
        }
        with self.assertRaisesRegex(PolicyConflictError, "must_increase"):
            normalize_policy_snapshot(payload)

    def test_power_loss_desire_is_not_accepted_as_physical_evidence(self):
        payload = unknown_policy()
        payload["controller_power_loss"] = {
            "observed_state": "desired_fail_closed",
            "evidence_note": "Desired only",
        }
        with self.assertRaisesRegex(PolicyValidationError, "unverified"):
            normalize_policy_snapshot(payload)

    def test_canary_runtime_and_measured_water_never_enter_proposal(self):
        proposal = prepare_policy_proposal(
            proposal_payload(), "owner-admin:test", now=NOW
        )
        self.assertFalse(proposal["canary_runtime_used"])
        self.assertFalse(proposal["measured_water_inferred"])
        self.assertFalse(proposal["successful_routine_irrigation_inferred"])
        self.assertNotIn("canary", proposal["policy"])

    def test_proposal_replay_creates_nothing(self):
        first, first_status = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW + timedelta(seconds=2)
        )
        replay, replay_status = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW
        )
        self.assertEqual(first_status, 201)
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "proposal_replay")
        self.assertEqual(len(self.store.proposals), 1)
        self.assertEqual(len(self.store.events), 1)

    def test_transition_replay_is_bound_to_actor_evidence_and_effective_time(self):
        proposal, _ = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW
        )
        proposal_id = proposal["proposal"]["proposal_id"]
        review_payload = {"idempotency_key": "review-bound", "evidence": {"owner_note": "Reviewed"}}
        review_policy(proposal_id, review_payload, "owner-admin:test", store=self.store, now=NOW)
        conflict, status = review_policy(
            proposal_id,
            {"idempotency_key": "review-bound", "evidence": {"owner_note": "Changed"}},
            "owner-admin:test",
            store=self.store,
            now=NOW + timedelta(seconds=1),
        )
        self.assertEqual(status, 409)
        self.assertEqual(conflict["status"], "transition_idempotency_conflict")

    def test_future_activation_is_not_active_before_effective_time(self):
        proposal, _ = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW
        )
        proposal_id = proposal["proposal"]["proposal_id"]
        review_policy(
            proposal_id,
            {"idempotency_key": "review-future", "evidence": {"owner_note": "Reviewed"}},
            "owner-admin:test", store=self.store, now=NOW,
        )
        future = NOW + timedelta(hours=1)
        activate_policy(
            proposal_id,
            {
                "idempotency_key": "activate-future",
                "evidence": {"owner_note": "Future activation"},
                "effective_at": future.isoformat(),
            },
            "owner-admin:test", store=self.store, now=NOW,
        )
        self.assertIsNone(self.store.snapshot(now=NOW)["active_policy"])
        self.assertIsNotNone(self.store.snapshot(now=future)["active_policy"])

    def test_exact_activation_replay_remains_valid_after_effective_time(self):
        proposal, _ = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW
        )
        proposal_id = proposal["proposal"]["proposal_id"]
        review_policy(
            proposal_id,
            {"idempotency_key": "review-scheduled", "evidence": {"owner_note": "Reviewed"}},
            "owner-admin:test", store=self.store, now=NOW,
        )
        effective = NOW + timedelta(hours=1)
        payload = {
            "idempotency_key": "activate-scheduled",
            "evidence": {"owner_note": "Scheduled"},
            "effective_at": effective.isoformat(),
        }
        first, _ = activate_policy(
            proposal_id, payload, "owner-admin:test", store=self.store, now=NOW
        )
        replay, status = activate_policy(
            proposal_id, payload, "owner-admin:test",
            store=self.store, now=NOW + timedelta(hours=2),
        )
        self.assertEqual(first["status"], "active_for_advice")
        self.assertEqual(status, 200)
        self.assertEqual(replay["status"], "active_for_advice_replay")
        self.assertEqual(replay["effective_at"], effective.isoformat())

    def test_exact_transition_replay_precedes_stale_version_check(self):
        first, _ = propose_policy(
            proposal_payload("proposal-first"), "owner-admin:test",
            store=self.store, now=NOW,
        )
        proposal_id = first["proposal"]["proposal_id"]
        payload = {"idempotency_key": "review-first", "evidence": {"owner_note": "Reviewed"}}
        review_policy(proposal_id, payload, "owner-admin:test", store=self.store, now=NOW)
        propose_policy(
            proposal_payload("proposal-newer"), "owner-admin:test",
            store=self.store, now=NOW,
        )
        replay, status = review_policy(
            proposal_id, payload, "owner-admin:test",
            store=self.store, now=NOW + timedelta(minutes=1),
        )
        self.assertEqual(status, 200)
        self.assertEqual(replay["status"], "owner_reviewed_replay")

    def test_idempotency_conflict_is_rejected(self):
        propose_policy(proposal_payload(), "owner-admin:test", store=self.store, now=NOW)
        changed = unknown_policy()
        changed["forecast_rain"] = {
            "amount_mm": 5,
            "probability_pct": 70,
            "horizon_hours": 24,
        }
        result, status = propose_policy(
            proposal_payload(policy=changed),
            "owner-admin:test",
            store=self.store,
            now=NOW,
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "proposal_idempotency_conflict")

    def test_proposal_does_not_become_active(self):
        result, _ = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW
        )
        self.assertEqual(result["proposal"]["lifecycle_state"], "proposed")
        self.assertIsNone(self.store.snapshot()["active_policy"])

    def test_review_does_not_activate(self):
        proposal, _ = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW
        )
        reviewed, status = review_policy(
            proposal["proposal"]["proposal_id"],
            {"idempotency_key": "review-1", "evidence": {"owner_note": "Reviewed"}},
            "owner-admin:test",
            store=self.store,
            now=NOW,
        )
        self.assertEqual(status, 201)
        self.assertEqual(reviewed["status"], "owner_reviewed")
        self.assertIsNone(self.store.snapshot()["active_policy"])

    def test_activation_requires_exact_reviewed_version_and_effective_time(self):
        proposal, _ = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW
        )
        proposal_id = proposal["proposal"]["proposal_id"]
        blocked, blocked_status = activate_policy(
            proposal_id,
            {
                "idempotency_key": "activate-1",
                "evidence": {"owner_note": "Activate"},
                "effective_at": NOW.isoformat(),
            },
            "owner-admin:test",
            store=self.store,
            now=NOW,
        )
        self.assertEqual(blocked_status, 409)
        self.assertEqual(blocked["status"], "owner_reviewed_state_required")
        review_policy(
            proposal_id,
            {"idempotency_key": "review-1", "evidence": {"owner_note": "Reviewed"}},
            "owner-admin:test",
            store=self.store,
            now=NOW,
        )
        missing, missing_status = activate_policy(
            proposal_id,
            {"idempotency_key": "activate-2", "evidence": {"owner_note": "Activate"}},
            "owner-admin:test",
            store=self.store,
            now=NOW,
        )
        self.assertEqual(missing_status, 400)
        active, active_status = activate_policy(
            proposal_id,
            {
                "idempotency_key": "activate-3",
                "evidence": {"owner_note": "Explicit activation"},
                "effective_at": NOW.isoformat(),
            },
            "owner-admin:test",
            store=self.store,
            now=NOW,
        )
        self.assertEqual(active_status, 201)
        self.assertEqual(active["status"], "active_for_advice")
        self.assertFalse(active["activation_generates_plan"])
        self.assertIsNotNone(self.store.snapshot()["active_policy"])

    def test_stale_predecessor_cannot_be_reviewed_or_activated(self):
        first, _ = propose_policy(
            proposal_payload("proposal-1"), "owner-admin:test", store=self.store, now=NOW
        )
        propose_policy(
            proposal_payload("proposal-2"), "owner-admin:test", store=self.store, now=NOW
        )
        result, status = review_policy(
            first["proposal"]["proposal_id"],
            {"idempotency_key": "stale-review", "evidence": {"owner_note": "Too late"}},
            "owner-admin:test",
            store=self.store,
            now=NOW,
        )
        self.assertEqual(status, 409)
        self.assertEqual(result["status"], "stale_policy_version")

    def test_conflicting_and_replayed_review_are_distinct(self):
        proposal, _ = propose_policy(
            proposal_payload(), "owner-admin:test", store=self.store, now=NOW
        )
        proposal_id = proposal["proposal"]["proposal_id"]
        payload = {"idempotency_key": "review-1", "evidence": {"owner_note": "Reviewed"}}
        first, _ = review_policy(
            proposal_id, payload, "owner-admin:test", store=self.store, now=NOW
        )
        replay, replay_status = review_policy(
            proposal_id, payload, "owner-admin:test", store=self.store, now=NOW
        )
        self.assertEqual(first["status"], "owner_reviewed")
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["status"], "owner_reviewed_replay")
        conflict, conflict_status = review_policy(
            proposal_id,
            {"idempotency_key": "review-2", "evidence": {"owner_note": "Again"}},
            "owner-admin:test",
            store=self.store,
            now=NOW,
        )
        self.assertEqual(conflict_status, 409)
        self.assertEqual(conflict["status"], "conflicting_transition")

    def test_preview_is_read_only_and_keeps_runtime_unavailable(self):
        preview, status = preview_policy_effect(
            unknown_policy(), {"status": "needs_data"}
        )
        self.assertEqual(status, 200)
        self.assertEqual(preview["eligibility_after_preview"], "Needs Data")
        self.assertIsNone(preview["runtime_after_preview"])
        self.assertFalse(preview["preview_becomes_active"])
        self.assertFalse(preview["preview_generates_plan"])
        self.assertTrue(all(preview[key] is False for key in AUTHORITY))


class RootlineOperatingPolicyRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.env = mock.patch.dict(os.environ, OWNER_ENV, clear=False)
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def login(self, role):
        token = OWNER_ENV["OWNER_ADMIN_TOKEN" if role == "admin" else "OWNER_READ_TOKEN"]
        response = self.client.post(
            "/owner/login", data={"owner_token": token, "next": "/"}, follow_redirects=False
        )
        self.assertEqual(response.status_code, 302)

    def test_anonymous_routes_are_denied(self):
        read = self.client.get("/api/telemetry/rootline/operating-policy")
        propose = self.client.post(
            "/api/telemetry/rootline/operating-policy/proposals", json={}
        )
        self.assertEqual(read.status_code, 403)
        self.assertEqual(propose.status_code, 403)
        self.assertEqual(read.get_json()["status"], "owner_read_access_denied")

    def test_owner_read_can_view_and_preview_but_not_mutate(self):
        self.login("read")
        with mock.patch(
            "modules.telemetry.telemetry_routes.list_policy_review",
            return_value=({"success": True, "status": "ready", "proposals": []}, 200),
        ), mock.patch(
            "modules.telemetry.telemetry_routes.preview_policy_effect",
            return_value=({"success": True, **AUTHORITY}, 200),
        ):
            self.assertEqual(
                self.client.get("/api/telemetry/rootline/operating-policy").status_code,
                200,
            )
            self.assertEqual(
                self.client.post(
                    "/api/telemetry/rootline/operating-policy/preview",
                    json={"policy": unknown_policy()},
                ).status_code,
                200,
            )
        denied = self.client.post(
            "/api/telemetry/rootline/operating-policy/proposals",
            json=proposal_payload(),
        )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(denied.get_json()["status"], "owner_admin_access_denied")

    def test_owner_admin_uses_server_derived_principal(self):
        self.login("admin")
        with mock.patch(
            "modules.telemetry.telemetry_routes.propose_policy",
            return_value=({"success": True, **AUTHORITY}, 201),
        ) as propose:
            response = self.client.post(
                "/api/telemetry/rootline/operating-policy/proposals",
                json=proposal_payload(),
            )
        self.assertEqual(response.status_code, 201)
        actor = propose.call_args.args[1]
        self.assertTrue(actor.startswith("owner-admin:"))
        self.assertNotIn("actor", propose.call_args.args[0])

    def test_owner_admin_can_record_one_live_rain_value_with_other_rules_unknown(self):
        self.login("admin")
        policy = unknown_policy()
        policy["live_rain_hold"] = {
            "evidence_field": "current_rain_rate_mm_per_hour",
            "threshold_mm_per_hour": 0.2,
            "comparison": "greater_than",
            "release_policy": "Unknown",
        }
        payload = {
            "idempotency_key": "charl-live-rain-hold-v1",
            "evidence": {"owner_note": "Charl confirmed the live-rain threshold."},
            "policy": policy,
        }
        with mock.patch(
            "modules.telemetry.telemetry_routes.propose_policy",
            return_value=(
                {
                    "success": True,
                    "status": "proposal_recorded",
                    "writes_performed": True,
                    **AUTHORITY,
                },
                201,
            ),
        ) as propose:
            response = self.client.post(
                "/api/telemetry/rootline/operating-policy/proposals",
                json=payload,
            )
        self.assertEqual(response.status_code, 201)
        submitted, actor = propose.call_args.args
        self.assertEqual(submitted["policy"]["live_rain_hold"]["threshold_mm_per_hour"], 0.2)
        self.assertEqual(submitted["policy"]["forecast_rain"], "Unknown")
        self.assertEqual(submitted["policy"]["zones"]["B12345"]["daylight_window"], "Unknown")
        self.assertTrue(actor.startswith("owner-admin:"))

    def test_dashboard_shell_links_to_strict_owner_page_without_payload(self):
        response = self.client.get("/")
        html = response.get_data(as_text=True)
        self.assertEqual(response.status_code, 200)
        self.assertIn('/rootline/policy-review', html)
        self.assertNotIn('id="policy_form"', html)
        self.assertNotIn("ROOTLINE-POLICY-", html)
        self.assertNotIn("owner-admin:", html)

    def test_policy_page_is_owner_only(self):
        self.assertEqual(self.client.get("/rootline/policy-review").status_code, 403)
        self.login("read")
        response = self.client.get("/rootline/policy-review")
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="policy_form"', response.get_data(as_text=True))

    def test_disabled_owner_access_never_admits_remote_policy_mutation(self):
        with mock.patch.dict(
            os.environ,
            {"OWNER_ACCESS_ENABLED": "0", "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0"},
            clear=False,
        ), mock.patch(
            "modules.telemetry.telemetry_routes.propose_policy"
        ) as propose:
            response = self.client.post(
                "/api/telemetry/rootline/operating-policy/proposals",
                json=proposal_payload(),
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
        self.assertEqual(response.status_code, 403)
        propose.assert_not_called()


if __name__ == "__main__":
    unittest.main()
