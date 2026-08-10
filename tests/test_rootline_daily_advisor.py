import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app import app
from modules.telemetry.rootline_daily_advisor import (
    AUTHORITY,
    C12345_CANARY_SHA256,
    build_rootline_daily_advisor,
    canonical_c12345_canary_record,
    canonical_canary_envelope_sha256,
    canonical_canary_sha256,
    classify_canary_evidence_append,
    get_rootline_daily_advisor,
)


def daily_brief(**overrides):
    brief = {
        "success": True,
        "current_conditions": {
            "availability": "Available",
            "freshness": "fresh",
            "last_reading_at": "2026-07-27T14:30:18+00:00",
            "data_age_minutes": 2,
            "temperature_c": 15,
            "rain_rate_mm_h": 0,
            "rain_today_mm": 5.08,
            "wind_speed_kmh": 17,
        },
        "forecast": {
            "availability": "Available",
            "freshness": "fresh",
            "last_forecast_run_at": "2026-07-27T12:00:00+00:00",
        },
        "irrigation": {
            "availability": "Available",
            "current_status": "IDLE",
            "zones": [
                {
                    "zone_id": "B12345",
                    "zone_name": "B - Kamp",
                    "work_state": "planned",
                    "planned_minutes": 120,
                },
                {
                    "zone_id": "C12345",
                    "zone_name": "C - Kamp",
                    "work_state": "completed",
                    "planned_minutes": 120,
                },
            ],
        },
    }
    brief.update(overrides)
    return brief


def active_policy_v2():
    return {
        "proposal_id": "ROOTLINE-POLICY-222222222222222222222222",
        "version": 2,
        "policy": {
            "seasonal_boundaries": "Unknown",
            "zones": {
                zone_id: {
                    "crop_use": crop,
                    "daylight_window": "Unknown",
                    "minimum_useful_runtime_minutes": "Unknown",
                    "maximum_continuous_runtime_minutes": "Unknown",
                }
                for zone_id, crop in (
                    ("B12345", "lucerne"),
                    ("C12345", "vegetables"),
                )
            },
            "forecast_rain": "Unknown",
            "live_rain_hold": {
                "evidence_field": "current_rain_rate_mm_per_hour",
                "threshold_mm_per_hour": 0.2,
                "comparison": "greater_than",
                "release_policy": {
                    "dry_interval_minutes": 30,
                    "dry_rain_rate_mm_per_hour": 0.0,
                    "minimum_fresh_station_readings": 2,
                    "visible_rain_confirmation_required": True,
                    "owner_review_required": True,
                },
            },
            "temperature_limits": "Unknown",
            "crop_need_bands": {"B12345": "Unknown", "C12345": "Unknown"},
            "controller_power_loss": "Unknown",
            "residual_drainage": "Unknown",
        },
    }


def active_policy_v3():
    result = active_policy_v2()
    result["proposal_id"] = "ROOTLINE-POLICY-333333333333333333333333"
    result["version"] = 3
    for zone in result["policy"]["zones"].values():
        zone["daylight_window"] = {
            "start": "08:00",
            "end": "17:00",
            "timezone": "Africa/Johannesburg",
        }
    return result


def complete_dry_release_evidence():
    return {
        "availability": "Available",
        "conflicting": False,
        "continuous_zero_rain_confirmed": True,
        "interval_start_at": "2026-07-27T14:00:18+00:00",
        "interval_end_at": "2026-07-27T14:30:18+00:00",
        "station_readings": [
            {
                "observed_at": "2026-07-27T14:00:18+00:00",
                "rain_rate_mm_h": 0.0,
                "freshness": "fresh",
            },
            {
                "observed_at": "2026-07-27T14:30:18+00:00",
                "rain_rate_mm_h": 0.0,
                "freshness": "fresh",
            },
        ],
        "no_visible_rain_confirmed": True,
        "visible_rain_confirmed_at": "2026-07-27T14:30:18+00:00",
        "owner_review_confirmed": True,
        "owner_reviewed_at": "2026-07-27T14:30:18+00:00",
    }


def dry_brief_at(local_time):
    observed_at = local_time.astimezone(timezone.utc)
    interval_start = observed_at - timedelta(minutes=30)
    brief = daily_brief()
    brief["current_conditions"]["rain_rate_mm_h"] = 0.0
    brief["current_conditions"]["last_reading_at"] = observed_at.isoformat()
    brief["rain_release_evidence"] = {
        "availability": "Available",
        "conflicting": False,
        "continuous_zero_rain_confirmed": True,
        "interval_start_at": interval_start.isoformat(),
        "interval_end_at": observed_at.isoformat(),
        "station_readings": [
            {
                "observed_at": interval_start.isoformat(),
                "rain_rate_mm_h": 0.0,
                "freshness": "fresh",
            },
            {
                "observed_at": observed_at.isoformat(),
                "rain_rate_mm_h": 0.0,
                "freshness": "fresh",
            },
        ],
        "no_visible_rain_confirmed": True,
        "visible_rain_confirmed_at": observed_at.isoformat(),
        "owner_review_confirmed": True,
        "owner_reviewed_at": observed_at.isoformat(),
    }
    return brief


def rehash_canary_record(record):
    record["persistence_provenance"]["operator_observations"] = record["physical"]
    record["persistence_provenance"]["transport_observations"] = record["transport"]
    record["evidence_sha256"] = canonical_canary_sha256(record)
    record["envelope_sha256"] = canonical_canary_envelope_sha256(record)
    return record


class RootlineDailyAdvisorTests(unittest.TestCase):
    def build(self, **overrides):
        return build_rootline_daily_advisor(
            daily_brief(**overrides),
            "2026-07-27",
            active_policy=active_policy_v2(),
        )

    def test_register_contains_only_known_zones_and_owner_baseline(self):
        result = self.build()
        self.assertEqual([zone["zone_id"] for zone in result["zones"]], ["B12345", "C12345"])
        register = result["operating_knowledge"]
        self.assertEqual(register["zones"]["B12345"]["crop_use"], "lucerne")
        self.assertEqual(register["zones"]["C12345"]["crop_use"], "vegetables")
        self.assertFalse(register["zones"]["B12345"]["pump_required"])
        self.assertFalse(register["approved_policy"]["simultaneous_zones"])
        self.assertEqual(register["approved_policy"]["seasonal_boundaries"], "Unknown")
        self.assertEqual(register["approved_policy"]["owner_hold_expiry"], "none_explicit_release_required")
        self.assertEqual(
            register["approved_policy"]["live_rain"],
            "active_versioned_policy_is_authoritative",
        )
        self.assertIn(
            "history_not_runtime_policy",
            register["approved_policy"]["historical_live_rain_baseline"],
        )

    def test_unknown_numeric_policy_suppresses_runtime_and_eligibility(self):
        result = self.build()
        for zone in result["zones"]:
            self.assertEqual(zone["recommendation"], "Hold")
            self.assertEqual(zone["eligibility_today"], "Hold")
            self.assertIsNone(zone["proposed_runtime_minutes"])
            self.assertEqual(zone["proposed_runtime_status"], "Unavailable")
            self.assertIn("maximum_runtime_unknown", zone["runtime_suppressed_by"])

    def test_fresh_live_rain_holds_both_zones(self):
        brief = daily_brief()
        brief["current_conditions"]["rain_rate_mm_h"] = 0.4
        result = build_rootline_daily_advisor(
            brief, "2026-07-27", active_policy=active_policy_v2()
        )
        self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))
        self.assertTrue(all(zone["eligibility_today"] == "Hold" for zone in result["zones"]))

    def test_stale_weather_and_forecast_fail_closed(self):
        brief = daily_brief()
        brief["current_conditions"]["freshness"] = "stale"
        brief["current_conditions"]["rain_rate_mm_h"] = 2
        brief["forecast"]["freshness"] = "stale"
        result = build_rootline_daily_advisor(
            brief, "2026-07-27", active_policy=active_policy_v2()
        )
        for zone in result["zones"]:
            self.assertEqual(zone["recommendation"], "Hold")
            self.assertTrue(any("Fresh current weather" in reason for reason in zone["reasoning"]))
            self.assertTrue(any("fresh forecast" in reason for reason in zone["reasoning"]))

    def test_strict_threshold_and_release_evidence_matrix(self):
        for rain_rate in (0.21, 0.4):
            brief = daily_brief()
            brief["current_conditions"]["rain_rate_mm_h"] = rain_rate
            result = build_rootline_daily_advisor(
                brief, "2026-07-27", active_policy=active_policy_v2()
            )
            self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))

        for rain_rate in (0.2, 0.1, 0.0):
            brief = daily_brief()
            brief["current_conditions"]["rain_rate_mm_h"] = rain_rate
            result = build_rootline_daily_advisor(
                brief, "2026-07-27", active_policy=active_policy_v2()
            )
            self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))
            self.assertTrue(
                all(
                    "threshold is not exceeded" in " ".join(zone["reasoning"])
                    for zone in result["zones"]
                )
            )

        brief = daily_brief()
        brief["current_conditions"]["rain_rate_mm_h"] = 0.0
        brief["rain_release_evidence"] = complete_dry_release_evidence()
        result = build_rootline_daily_advisor(
            brief, "2026-07-27", active_policy=active_policy_v2()
        )
        self.assertTrue(all(zone["recommendation"] == "Needs Data" for zone in result["zones"]))
        self.assertTrue(all(zone["eligibility_today"] == "Needs Data" for zone in result["zones"]))
        self.assertTrue(
            all(zone["proposed_runtime_status"] == "Unavailable" for zone in result["zones"])
        )

        brief["current_conditions"]["rain_rate_mm_h"] = 0.2
        result = build_rootline_daily_advisor(
            brief, "2026-07-27", active_policy=active_policy_v2()
        )
        self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))

    def test_daylight_window_is_start_inclusive_and_end_exclusive_in_sast(self):
        sast = timezone(timedelta(hours=2))
        cases = (
            ("07:59:59", "Hold", "outside"),
            ("08:00:00", "Needs Data", "inside"),
            ("16:59:59", "Needs Data", "inside"),
            ("17:00:00", "Hold", "outside"),
        )
        for clock, expected, phrase in cases:
            with self.subTest(clock=clock):
                local_time = datetime.fromisoformat(
                    f"2026-07-28T{clock}+02:00"
                ).astimezone(sast)
                result = build_rootline_daily_advisor(
                    dry_brief_at(local_time),
                    "2026-07-28",
                    active_policy=active_policy_v3(),
                    now=local_time,
                )
                for zone in result["zones"]:
                    self.assertEqual(zone["recommendation"], expected)
                    self.assertEqual(zone["eligibility_today"], expected)
                    self.assertIn(phrase, " ".join(zone["reasoning"]).lower())
                    self.assertIsNone(zone["proposed_runtime_minutes"])
                    self.assertEqual(
                        zone["proposed_runtime_status"], "Unavailable"
                    )
                    self.assertNotIn(
                        "allowed_window_unknown", zone["runtime_suppressed_by"]
                    )

    def test_missing_malformed_or_conflicting_advice_time_is_needs_data(self):
        local_time = datetime.fromisoformat("2026-07-28T10:00:00+02:00")
        brief = dry_brief_at(local_time)
        for advisor_date, now in (
            ("2026-07-28", "malformed"),
            ("2026-07-29", local_time),
            ("2026-07-28", datetime(2026, 7, 28, 10, 0)),
        ):
            with self.subTest(advisor_date=advisor_date, now=now):
                result = build_rootline_daily_advisor(
                    brief,
                    advisor_date,
                    active_policy=active_policy_v3(),
                    now=now,
                )
                self.assertTrue(
                    all(
                        zone["recommendation"] == "Needs Data"
                        and zone["eligibility_today"] == "Needs Data"
                        for zone in result["zones"]
                    )
                )

    def test_version_3_preserves_rain_release_and_never_invents_runtime(self):
        local_time = datetime.fromisoformat("2026-07-28T10:00:00+02:00")
        brief = dry_brief_at(local_time)
        brief["current_conditions"]["rain_rate_mm_h"] = 0.21
        result = build_rootline_daily_advisor(
            brief,
            "2026-07-28",
            active_policy=active_policy_v3(),
            now=local_time,
        )
        self.assertTrue(
            all(zone["recommendation"] == "Hold" for zone in result["zones"])
        )

        brief = dry_brief_at(local_time)
        result = build_rootline_daily_advisor(
            brief,
            "2026-07-28",
            active_policy=active_policy_v3(),
            now=local_time,
        )
        self.assertTrue(
            all(
                zone["recommendation"] == "Needs Data"
                and zone["proposed_runtime_minutes"] is None
                and zone["proposed_runtime_status"] == "Unavailable"
                for zone in result["zones"]
            )
        )
        self.assertNotIn(
            "exact_daylight_windows_per_zone",
            {
                item["decision"]
                for item in result["unresolved_owner_decisions"]
            },
        )

    def test_incomplete_or_conflicting_release_evidence_retains_hold(self):
        cases = []
        incomplete = complete_dry_release_evidence()
        incomplete["interval_end_at"] = "2026-07-27T14:30:17+00:00"
        cases.append(incomplete)
        one_reading = complete_dry_release_evidence()
        one_reading["station_readings"] = one_reading["station_readings"][:1]
        cases.append(one_reading)
        missing_readings = complete_dry_release_evidence()
        missing_readings["station_readings"] = []
        cases.append(missing_readings)
        stale_readings = complete_dry_release_evidence()
        stale_readings["station_readings"][0]["freshness"] = "stale"
        cases.append(stale_readings)
        nonzero_midpoint = complete_dry_release_evidence()
        nonzero_midpoint["station_readings"].insert(
            1,
            {
                "observed_at": "2026-07-27T14:15:00+00:00",
                "rain_rate_mm_h": 0.4,
                "freshness": "fresh",
            },
        )
        cases.append(nonzero_midpoint)
        boolean_reading = complete_dry_release_evidence()
        boolean_reading["station_readings"][0]["rain_rate_mm_h"] = False
        cases.append(boolean_reading)
        no_visual = complete_dry_release_evidence()
        no_visual["no_visible_rain_confirmed"] = False
        cases.append(no_visual)
        not_continuous = complete_dry_release_evidence()
        not_continuous["continuous_zero_rain_confirmed"] = False
        cases.append(not_continuous)
        no_owner_review = complete_dry_release_evidence()
        no_owner_review["owner_review_confirmed"] = False
        cases.append(no_owner_review)
        conflicting = complete_dry_release_evidence()
        conflicting["conflicting"] = True
        cases.append(conflicting)

        for evidence in cases:
            brief = daily_brief()
            brief["current_conditions"]["rain_rate_mm_h"] = 0.0
            brief["rain_release_evidence"] = evidence
            result = build_rootline_daily_advisor(
                brief, "2026-07-27", active_policy=active_policy_v2()
            )
            self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))

    def test_release_evidence_is_bound_to_current_observation_date_and_time(self):
        brief = daily_brief()
        brief["current_conditions"]["rain_rate_mm_h"] = 0.0
        brief["rain_release_evidence"] = complete_dry_release_evidence()

        wrong_date = build_rootline_daily_advisor(
            brief, "2026-07-28", active_policy=active_policy_v2()
        )
        self.assertTrue(
            all(zone["recommendation"] == "Hold" for zone in wrong_date["zones"])
        )

        future_evidence = build_rootline_daily_advisor(
            brief,
            "2026-07-27",
            active_policy=active_policy_v2(),
            now=datetime(2026, 7, 27, 13, 0, tzinfo=timezone.utc),
        )
        self.assertTrue(
            all(zone["recommendation"] == "Hold" for zone in future_evidence["zones"])
        )

        brief["current_conditions"]["rain_rate_mm_h"] = False
        boolean_current = build_rootline_daily_advisor(
            brief, "2026-07-27", active_policy=active_policy_v2()
        )
        self.assertTrue(
            all(zone["recommendation"] == "Hold" for zone in boolean_current["zones"])
        )

    def test_malformed_active_policy_fails_closed_without_exception(self):
        malformed = active_policy_v2()
        malformed["policy"]["live_rain_hold"] = {
            "evidence_field": "current_rain_rate_mm_per_hour",
            "threshold_mm_per_hour": 99,
            "comparison": "less_than",
            "release_policy": {
                "dry_interval_minutes": 1,
            },
        }
        brief = daily_brief()
        brief["current_conditions"]["rain_rate_mm_h"] = 0.0
        brief["rain_release_evidence"] = complete_dry_release_evidence()
        result = build_rootline_daily_advisor(
            brief, "2026-07-27", active_policy=malformed
        )
        self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))
        self.assertEqual(result["active_advice_policy"]["status"], "Unavailable")

    def test_missing_active_policy_never_falls_back_to_any_positive_rain_rule(self):
        brief = daily_brief()
        brief["current_conditions"]["rain_rate_mm_h"] = 0.1
        result = build_rootline_daily_advisor(brief, "2026-07-27")
        self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))
        self.assertTrue(
            all(
                "active authoritative live-rain policy" in " ".join(zone["reasoning"])
                for zone in result["zones"]
            )
        )

    def test_service_reads_only_the_active_versioned_policy(self):
        result, status = get_rootline_daily_advisor(
            "2026-07-27",
            brief_reader=lambda: (daily_brief(), 200),
            policy_reader=lambda: (
                {
                    "success": True,
                    "active_policy": active_policy_v2(),
                    "proposals": [],
                },
                200,
            ),
        )
        self.assertEqual(status, 200)
        self.assertEqual(result["active_advice_policy"]["version"], 2)
        self.assertEqual(
            result["active_advice_policy"]["proposal_id"],
            "ROOTLINE-POLICY-222222222222222222222222",
        )
        self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))

    def test_missing_daily_brief_remains_understandable_and_fail_closed(self):
        result = build_rootline_daily_advisor(None, "2026-07-27")
        self.assertIn("Evidence still missing", result["executive_summary"])
        self.assertEqual(result["weather"]["current_status"], "Unavailable")
        self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))

    def test_legacy_plans_never_become_verified_watering(self):
        result = self.build()
        c_zone = next(zone for zone in result["zones"] if zone["zone_id"] == "C12345")
        activity = c_zone["previous_activity"]
        self.assertEqual(activity["legacy_planned_minutes"], 120)
        self.assertEqual(activity["legacy_plan_state"], "completed")
        self.assertEqual(activity["observed_runtime_status"], "Unavailable")
        self.assertEqual(activity["measured_water_status"], "Unavailable")
        self.assertEqual(activity["verified_watering"], "Unavailable")
        self.assertFalse(
            result["physical_identity_evidence"]["C12345"]["counts_as_verified_watering"]
        )

    def test_canary_evidence_is_exact_and_separates_observations(self):
        record = canonical_c12345_canary_record()
        self.assertEqual(canonical_canary_sha256(record), C12345_CANARY_SHA256)
        self.assertEqual(record["transport"]["on_http_status"], 200)
        self.assertTrue(record["physical"]["valve_opening_observed"])
        self.assertTrue(record["physical"]["new_water_flow_observed"])
        self.assertTrue(record["physical"]["valve_closure_observed"])
        self.assertEqual(record["physical"]["residual_drainage"], "diminishing")
        self.assertEqual(
            record["physical"]["dripper_decay_seconds_availability"], "Unavailable"
        )
        self.assertEqual(record["physical"]["final_physical_state"], "safe_closed")
        provenance = record["persistence_provenance"]
        self.assertEqual(
            provenance["actor_identity"], "Charl_owner_attested_designated_operator"
        )
        self.assertEqual(provenance["operator_observations"], record["physical"])
        self.assertEqual(provenance["transport_observations"], record["transport"])
        self.assertEqual(
            canonical_canary_envelope_sha256(record), record["envelope_sha256"]
        )

    def test_append_contract_exact_replay_and_conflict_are_inert(self):
        record = canonical_c12345_canary_record()
        self.assertEqual(
            classify_canary_evidence_append(record)["status"], "append_candidate"
        )
        self.assertEqual(
            classify_canary_evidence_append(record, record)["status"], "exact_replay"
        )
        changed = canonical_c12345_canary_record()
        changed["physical"]["residual_drainage"] = "none"
        self.assertEqual(
            classify_canary_evidence_append(changed, record)["status"], "invalid"
        )
        changed["evidence_sha256"] = canonical_canary_sha256(changed)
        changed["persistence_provenance"]["operator_observations"] = changed["physical"]
        changed["envelope_sha256"] = canonical_canary_envelope_sha256(changed)
        self.assertEqual(
            classify_canary_evidence_append(changed, record)["status"],
            "identity_conflict",
        )

    def test_append_contract_rejects_missing_or_unexpected_provenance(self):
        record = canonical_c12345_canary_record()
        for field in (
            "actor_identity",
            "actor_identity_basis",
            "observed_at",
            "operator_observations",
            "transport_observations",
        ):
            candidate = canonical_c12345_canary_record()
            candidate["persistence_provenance"].pop(field)
            candidate["envelope_sha256"] = canonical_canary_envelope_sha256(candidate)
            with self.subTest(field=field):
                self.assertEqual(
                    classify_canary_evidence_append(candidate)["status"], "invalid"
                )
        candidate = canonical_c12345_canary_record()
        candidate["unexpected"] = True
        candidate["envelope_sha256"] = canonical_canary_envelope_sha256(candidate)
        self.assertEqual(
            classify_canary_evidence_append(candidate)["status"], "invalid"
        )

    def test_append_contract_rejects_malformed_actor_time_and_unknown_decay(self):
        for mutate in (
            lambda item: item["persistence_provenance"].update(actor_identity=""),
            lambda item: item["persistence_provenance"].update(observed_at="not-a-time"),
            lambda item: item["physical"].update(
                dripper_decay_seconds=None,
                dripper_decay_seconds_availability="Available",
            ),
        ):
            candidate = canonical_c12345_canary_record()
            mutate(candidate)
            candidate["evidence_sha256"] = canonical_canary_sha256(candidate)
            candidate["persistence_provenance"]["operator_observations"] = candidate[
                "physical"
            ]
            candidate["envelope_sha256"] = canonical_canary_envelope_sha256(candidate)
            self.assertEqual(
                classify_canary_evidence_append(candidate)["status"], "invalid"
            )

    def test_actor_alteration_is_an_identity_conflict_not_a_replay(self):
        record = canonical_c12345_canary_record()
        changed = canonical_c12345_canary_record()
        changed["persistence_provenance"][
            "actor_identity"
        ] = "different_authenticated_owner"
        changed["envelope_sha256"] = canonical_canary_envelope_sha256(changed)
        self.assertEqual(
            classify_canary_evidence_append(changed, record)["status"],
            "identity_conflict",
        )

    def test_append_contract_rejects_malformed_core_fields(self):
        mutations = {
            "schema_version": lambda item: item.update(schema_version="banana"),
            "packet_id": lambda item: item.update(packet_id="x"),
            "zone_id_type": lambda item: item.update(zone_id={"oops": 1}),
            "channel_type": lambda item: item.update(channel="2"),
            "owner_name_type": lambda item: item.update(owner_zone_name=123),
            "crop_empty": lambda item: item.update(crop_use=""),
            "on_event_channel": lambda item: item["transport"].update(
                on_event="irrigation_1_ch1_on"
            ),
            "on_timestamp": lambda item: item["transport"].update(
                on_requested_at="not-a-time"
            ),
            "off_timestamp_naive": lambda item: item["transport"].update(
                off_requested_at="2026-07-27T16:32:37"
            ),
            "http_status_type": lambda item: item["transport"].update(
                on_http_status="200"
            ),
            "acceptance_enum": lambda item: item["transport"].update(
                off_acceptance="probably"
            ),
            "duration_negative": lambda item: item["transport"].update(
                on_to_off_seconds=-1
            ),
            "duration_too_long": lambda item: item["transport"].update(
                on_to_off_seconds=31
            ),
            "retry_type": lambda item: item["transport"].update(retry_count=False),
            "physical_boolean": lambda item: item["physical"].update(
                valve_opening_observed="yes"
            ),
            "drainage_enum": lambda item: item["physical"].update(
                residual_drainage="maybe"
            ),
            "final_state_enum": lambda item: item["physical"].update(
                final_physical_state="fine"
            ),
            "authority_boolean": lambda item: item["authority"].update(retry=0),
        }
        for name, mutate in mutations.items():
            candidate = canonical_c12345_canary_record()
            mutate(candidate)
            rehash_canary_record(candidate)
            with self.subTest(name=name):
                self.assertEqual(
                    classify_canary_evidence_append(candidate)["status"], "invalid"
                )

    def test_zero_authority_is_invariant(self):
        result = self.build()
        self.assertEqual(result["authority"], AUTHORITY)
        self.assertTrue(all(value is False for value in result["authority"].values()))
        contract = result["canary_evidence_persistence"]
        self.assertEqual(contract["status"], "design_only_unapplied")
        self.assertFalse(contract["migration_designed"])
        self.assertFalse(contract["production_row_written"])


class RootlineDailyAdvisorRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()
        self.env = mock.patch.dict(
            os.environ,
            {
                "OWNER_ACCESS_ENABLED": "1",
                "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
                "OWNER_SESSION_SECRET": "s" * 40,
                "OWNER_READ_TOKEN": "r" * 40,
                "OWNER_ADMIN_TOKEN": "a" * 40,
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def test_anonymous_route_is_structured_403_and_unique(self):
        path = "/api/telemetry/rootline/daily-advisor"
        routes = [rule.rule for rule in app.url_map.iter_rules()]
        self.assertEqual(routes.count(path), 1)
        response = self.client.get(path, environ_base={"REMOTE_ADDR": "203.0.113.10"})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "owner_read_access_denied")

    @mock.patch("modules.telemetry.telemetry_routes.get_rootline_daily_advisor")
    def test_owner_read_route_returns_command_inert_payload(self, get_advisor):
        get_advisor.return_value = (
            {
                "success": True,
                "status": "needs_data",
                "authority": AUTHORITY,
            },
            200,
        )
        login = self.client.post(
            "/owner/login",
            data={"owner_token": "r" * 40, "next": "/dashboard"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        self.assertEqual(login.status_code, 302)
        response = self.client.get("/api/telemetry/rootline/daily-advisor")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(all(value is False for value in response.get_json()["authority"].values()))

    def test_existing_dashboard_has_one_panel_and_no_embedded_evidence(self):
        template = Path("templates/dashboard.html").read_text(encoding="utf-8")
        javascript = Path("static/js/dashboard.js").read_text(encoding="utf-8")
        self.assertEqual(template.count('id="irrigation_panel"'), 1)
        self.assertEqual(template.count('id="irrigation_b_status"'), 1)
        self.assertEqual(template.count('id="irrigation_c_status"'), 1)
        self.assertEqual(
            javascript.count("/api/telemetry/irrigation/status?date="), 1
        )
        self.assertNotIn(C12345_CANARY_SHA256, template)
        self.assertNotIn("irrigation_1_ch2_on", template)

    def test_module_has_no_transport_or_credential_import(self):
        source = Path("modules/telemetry/rootline_daily_advisor.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "import requests",
            "from urllib",
            "import socket",
            "load_dotenv",
            "psycopg",
            "gspread",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
