import os
import unittest
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


def rehash_canary_record(record):
    record["persistence_provenance"]["operator_observations"] = record["physical"]
    record["persistence_provenance"]["transport_observations"] = record["transport"]
    record["evidence_sha256"] = canonical_canary_sha256(record)
    record["envelope_sha256"] = canonical_canary_envelope_sha256(record)
    return record


class RootlineDailyAdvisorTests(unittest.TestCase):
    def build(self, **overrides):
        return build_rootline_daily_advisor(
            daily_brief(**overrides), "2026-07-27"
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

    def test_unknown_numeric_policy_suppresses_runtime_and_eligibility(self):
        result = self.build()
        for zone in result["zones"]:
            self.assertEqual(zone["recommendation"], "Needs Data")
            self.assertEqual(zone["eligibility_today"], "Needs Data")
            self.assertIsNone(zone["proposed_runtime_minutes"])
            self.assertEqual(zone["proposed_runtime_status"], "Unavailable")
            self.assertIn("maximum_runtime_unknown", zone["runtime_suppressed_by"])

    def test_fresh_live_rain_holds_both_zones(self):
        brief = daily_brief()
        brief["current_conditions"]["rain_rate_mm_h"] = 0.4
        result = build_rootline_daily_advisor(brief, "2026-07-27")
        self.assertTrue(all(zone["recommendation"] == "Hold" for zone in result["zones"]))
        self.assertTrue(all(zone["eligibility_today"] == "Hold" for zone in result["zones"]))

    def test_stale_weather_and_forecast_fail_closed(self):
        brief = daily_brief()
        brief["current_conditions"]["freshness"] = "stale"
        brief["current_conditions"]["rain_rate_mm_h"] = 2
        brief["forecast"]["freshness"] = "stale"
        result = build_rootline_daily_advisor(brief, "2026-07-27")
        for zone in result["zones"]:
            self.assertEqual(zone["recommendation"], "Needs Data")
            self.assertTrue(any("Fresh current weather" in reason for reason in zone["reasoning"]))
            self.assertTrue(any("fresh forecast" in reason for reason in zone["reasoning"]))

    def test_missing_daily_brief_remains_understandable_and_fail_closed(self):
        result = build_rootline_daily_advisor(None, "2026-07-27")
        self.assertIn("Evidence still missing", result["executive_summary"])
        self.assertEqual(result["weather"]["current_status"], "Unavailable")
        self.assertTrue(all(zone["recommendation"] == "Needs Data" for zone in result["zones"]))

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
        self.assertEqual(template.count('id="rootline_panel"'), 1)
        self.assertEqual(template.count('id="rootline_advisor_zones"'), 1)
        self.assertEqual(
            javascript.count("/api/telemetry/rootline/daily-advisor?date="), 1
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
