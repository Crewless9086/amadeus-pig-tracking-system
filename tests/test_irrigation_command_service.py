import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from app import app
from modules.telemetry.irrigation_command_service import (
    AUTHORITY,
    InMemoryIrrigationCommandLedger,
    RESERVED_FUTURE_STATES,
    approve_plan_only_command,
    cancel_plan_only_command,
    create_plan_only_command,
    list_plan_only_commands,
    prepare_command_contract,
)


NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def verified_inventory():
    return {
        "B12345": {
            "zone_name": "B - Kamp",
            "inventory_classifications": [],
            "physical_platform": "verified-controller",
            "pump_dependency": "verified",
            "tank_dependency": "verified",
            "borehole_dependency": "verified",
            "timeout_conflict": "",
            "legacy_controller_active": False,
            "legacy_controller_safe_for_activation": True,
            "max_runtime_minutes": 30,
        }
    }


def payload(**overrides):
    result = {
        "generation": 1,
        "daily_plan_id": "ROOTLINE-DAILY-PLAN-20260725",
        "daily_plan_generation": 1,
        "daily_plan_operating_date": "2026-07-25",
        "zone_id": "B12345",
        "zone_name": "B - Kamp",
        "intent": "ON",
        "requested_duration_minutes": 10,
        "created_at": (NOW - timedelta(minutes=1)).isoformat(),
        "expires_at": (NOW + timedelta(minutes=10)).isoformat(),
        "weather_evidence": {
            "availability": "Available",
            "freshness": "fresh",
            "observed_at": NOW.isoformat(),
            "forecast_availability": "Available",
            "forecast_freshness": "fresh",
        },
        "power_evidence": {
            "availability": "Available",
            "freshness": "fresh",
            "confidence": "verified",
            "suspicious": False,
        },
        "water_infrastructure_evidence": {
            "tank": {"availability": "Available", "readiness": "ready"},
            "pump": {"availability": "Available", "readiness": "ready"},
            "borehole": {"availability": "Available", "readiness": "ready"},
        },
        "safety_interlocks": {
            "manual_isolation_verified": True,
            "failure_safe_verified": True,
            "paired_off_ready": True,
            "simultaneous_zone_constraint_verified": True,
            "fertilizer_interlock_verified": True,
            "flow_feedback_available": True,
            "pressure_feedback_available": True,
            "valve_feedback_available": True,
        },
        "paired_off_command_id": "ROOTLINE-OFF-PAIR-1",
        "idempotency_key": "rootline-b12345-on-generation-1",
    }
    result.update(overrides)
    return result


class IrrigationCommandContractTests(unittest.TestCase):
    def test_current_inventory_fails_closed(self):
        contract = prepare_command_contract(payload(), now=NOW)
        self.assertEqual(contract["state"], "execution_prohibited")
        for reason in (
            "unsafe_for_control",
            "inventory_partial",
            "actuator_unproven",
            "physical_platform_unavailable",
            "pump_dependency_unavailable",
            "tank_dependency_unavailable",
            "borehole_dependency_unavailable",
            "timeout_conflict_unresolved",
        ):
            self.assertIn(reason, contract["prohibition_reasons"])
        self.assertFalse(contract["dispatchable"])
        self.assertFalse(contract["calls_ifttt"])
        self.assertFalse(contract["calls_n8n"])
        self.assertFalse(contract["controls_hardware"])

    def test_stale_weather_is_prohibited(self):
        data = payload()
        data["weather_evidence"]["freshness"] = "stale"
        contract = prepare_command_contract(data, now=NOW, inventory=verified_inventory())
        self.assertIn("weather_stale", contract["prohibition_reasons"])
        self.assertEqual(contract["state"], "execution_prohibited")

    def test_suspicious_power_is_prohibited(self):
        data = payload()
        data["power_evidence"]["suspicious"] = True
        contract = prepare_command_contract(data, now=NOW, inventory=verified_inventory())
        self.assertIn("power_suspicious_or_unverified", contract["prohibition_reasons"])

    def test_unavailable_tank_pump_and_borehole_are_each_prohibited(self):
        data = payload()
        for name in ("tank", "pump", "borehole"):
            data["water_infrastructure_evidence"][name] = {"availability": "Unavailable"}
        contract = prepare_command_contract(data, now=NOW, inventory=verified_inventory())
        for name in ("tank", "pump", "borehole"):
            self.assertIn(f"{name}_evidence_unavailable", contract["prohibition_reasons"])

    def test_missing_interlocks_are_explicit(self):
        data = payload()
        data["safety_interlocks"] = {}
        contract = prepare_command_contract(data, now=NOW, inventory=verified_inventory())
        self.assertIn("manual_isolation_verified_missing", contract["prohibition_reasons"])
        self.assertIn("valve_feedback_available_missing", contract["prohibition_reasons"])

    def test_timeout_conflict_is_not_resolved_by_requested_duration(self):
        contract = prepare_command_contract(payload(requested_duration_minutes=1), now=NOW)
        self.assertIn("timeout_conflict_unresolved", contract["prohibition_reasons"])
        self.assertIn("safe_maximum_runtime_unavailable", contract["prohibition_reasons"])

    def test_exact_zone_identity_is_required(self):
        with self.assertRaisesRegex(ValueError, "exact_zone_identity_required"):
            prepare_command_contract(payload(zone_id="B-12345"), now=NOW)
        with self.assertRaisesRegex(ValueError, "zone_identity_conflict"):
            prepare_command_contract(payload(zone_name="C - Kamp"), now=NOW)

    def test_expiry_is_derived_fail_closed(self):
        data = payload(
            created_at=(NOW - timedelta(minutes=20)).isoformat(),
            expires_at=(NOW - timedelta(minutes=1)).isoformat(),
        )
        contract = prepare_command_contract(data, now=NOW, inventory=verified_inventory())
        self.assertEqual(contract["state"], "expired")


class IrrigationCommandLedgerTests(unittest.TestCase):
    def setUp(self):
        self.ledger = InMemoryIrrigationCommandLedger()

    def test_duplicate_command_is_suppressed(self):
        first, first_status = create_plan_only_command(
            payload(), "owner-admin:test", ledger=self.ledger, now=NOW
        )
        second, second_status = create_plan_only_command(
            payload(), "owner-admin:test", ledger=self.ledger, now=NOW
        )
        self.assertEqual((first_status, second_status), (201, 200))
        self.assertEqual(second["status"], "duplicate_command_suppressed")
        self.assertEqual(len(self.ledger.commands), 1)
        self.assertEqual(len(self.ledger.events), 2)

    def test_same_idempotency_with_changed_packet_is_rejected(self):
        create_plan_only_command(payload(), "owner-admin:test", ledger=self.ledger, now=NOW)
        changed = payload(requested_duration_minutes=9)
        result, status = create_plan_only_command(
            changed, "owner-admin:test", ledger=self.ledger, now=NOW
        )
        self.assertEqual((status, result["status"]), (409, "idempotency_identity_conflict"))

    def test_conflicting_command_same_zone_generation_is_rejected(self):
        create_plan_only_command(payload(), "owner-admin:test", ledger=self.ledger, now=NOW)
        conflict = payload(
            intent="OFF",
            paired_off_command_id=None,
            idempotency_key="rootline-b12345-off-generation-1",
        )
        result, status = create_plan_only_command(
            conflict, "owner-admin:test", ledger=self.ledger, now=NOW
        )
        self.assertEqual((status, result["status"]), (409, "zone_generation_conflict"))

    def test_same_intent_with_different_identity_conflicts_on_generation(self):
        create_plan_only_command(payload(), "owner-admin:test", ledger=self.ledger, now=NOW)
        conflict = payload(idempotency_key="different-key-same-generation")
        result, status = create_plan_only_command(
            conflict, "owner-admin:test", ledger=self.ledger, now=NOW
        )
        self.assertEqual((status, result["status"]), (409, "zone_generation_conflict"))

    def test_superseded_daily_plan_cannot_be_approved(self):
        ledger = InMemoryIrrigationCommandLedger()
        result, status = create_plan_only_command(
            payload(), "owner-admin:test", ledger=ledger, now=NOW
        )
        self.assertEqual(status, 201)
        ledger.current_daily_plans[result["command"]["daily_plan_id"]] = 2
        approval, approval_status = approve_plan_only_command(
            result["command"]["command_id"], "owner-admin:test", ledger=ledger, now=NOW
        )
        self.assertEqual(approval_status, 409)
        self.assertEqual(approval["status"], "daily_plan_generation_superseded")

    def test_owner_approval_never_dispatches(self):
        result, status = create_plan_only_command(
            payload(), "owner-admin:test", ledger=self.ledger, now=NOW,
            inventory=verified_inventory(),
        )
        self.assertEqual((status, result["command"]["state"]), (201, "awaiting_owner_approval"))
        approved, approved_status = approve_plan_only_command(
            result["command"]["command_id"], "owner-admin:test", ledger=self.ledger, now=NOW
        )
        self.assertEqual((approved_status, approved["status"]), (200, "approved_not_dispatched"))
        self.assertFalse(approved["approval_dispatches"])
        for key, value in AUTHORITY.items():
            self.assertEqual(approved[key], value)
        self.assertEqual(len(self.ledger.events), 3)

    def test_current_prohibited_command_remains_prohibited_after_approval_record(self):
        result, _ = create_plan_only_command(
            payload(), "owner-admin:test", ledger=self.ledger, now=NOW
        )
        approved, _ = approve_plan_only_command(
            result["command"]["command_id"], "owner-admin:test", ledger=self.ledger, now=NOW
        )
        self.assertEqual(approved["status"], "execution_prohibited")
        states = [event["state"] for event in self.ledger.events]
        self.assertEqual(
            states,
            ["proposed", "execution_prohibited", "approved_not_dispatched", "execution_prohibited"],
        )

    def test_listing_marks_expired_without_writing(self):
        result, _ = create_plan_only_command(
            payload(), "owner-admin:test", ledger=self.ledger, now=NOW,
            inventory=verified_inventory(),
        )
        event_count = len(self.ledger.events)
        listing, status = list_plan_only_commands(
            ledger=self.ledger, now=NOW + timedelta(hours=1)
        )
        self.assertEqual((status, listing["commands"][0]["state"]), (200, "expired"))
        self.assertEqual(len(self.ledger.events), event_count)
        self.assertFalse(listing["writes_performed"])

    def test_cancellation_is_append_only_and_terminal(self):
        result, _ = create_plan_only_command(
            payload(), "owner-admin:test", ledger=self.ledger, now=NOW
        )
        cancelled, status = cancel_plan_only_command(
            result["command"]["command_id"], "owner-admin:test",
            ledger=self.ledger, now=NOW,
        )
        self.assertEqual((status, cancelled["status"]), (200, "cancelled"))
        approved, approved_status = approve_plan_only_command(
            result["command"]["command_id"], "owner-admin:test",
            ledger=self.ledger, now=NOW,
        )
        self.assertEqual((approved_status, approved["status"]), (409, "terminal_command_state"))

    def test_future_execution_states_are_reserved_and_unreachable(self):
        self.assertIn("dispatched", RESERVED_FUTURE_STATES)
        result, _ = create_plan_only_command(
            payload(), "owner-admin:test", ledger=self.ledger, now=NOW
        )
        command = result["command"]
        with self.assertRaisesRegex(ValueError, "future_execution_state_unreachable"):
            self.ledger.append_review_states(
                command, ["dispatched"], "owner-admin:test", NOW
            )

    def test_zero_transport_calls_and_zero_retry_surface(self):
        with mock.patch("urllib.request.urlopen") as urlopen:
            result, _ = create_plan_only_command(
                payload(), "owner-admin:test", ledger=self.ledger, now=NOW
            )
            approve_plan_only_command(
                result["command"]["command_id"], "owner-admin:test",
                ledger=self.ledger, now=NOW,
            )
        urlopen.assert_not_called()
        self.assertFalse(result["automatic_retry"])
        self.assertFalse(result["calls_ifttt"])
        self.assertFalse(result["calls_n8n"])
        self.assertFalse(result["controls_hardware"])


class IrrigationCommandRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True, SECRET_KEY="rootline-route-test")
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

    def test_anonymous_review_api_returns_structured_403(self):
        response = self.client.get("/api/telemetry/rootline/irrigation-commands")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "owner_read_access_denied")

    def test_read_session_cannot_create_command(self):
        with self.client.session_transaction() as session:
            session["owner_access"] = {
                "role": "read",
                "principal_id": "owner-read:test",
                "created_at": NOW.isoformat(),
            }
        response = self.client.post(
            "/api/telemetry/rootline/irrigation-commands", json=payload()
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.get_json()["status"], "owner_admin_access_denied")

    def test_read_session_cannot_approve_or_cancel_command(self):
        with self.client.session_transaction() as session:
            session["owner_access"] = {
                "role": "read",
                "principal_id": "owner-read:test",
                "created_at": NOW.isoformat(),
            }
        for action in ("approve", "cancel"):
            response = self.client.post(
                f"/api/telemetry/rootline/irrigation-commands/ROOTLINE-CMD-test/{action}"
            )
            self.assertEqual(response.status_code, 403)
            self.assertEqual(
                response.get_json()["status"], "owner_admin_access_denied"
            )

    @mock.patch("modules.telemetry.telemetry_routes.create_plan_only_command")
    def test_admin_route_preserves_no_authority_contract(self, create):
        create.return_value = ({
            "success": True,
            "status": "plan_only_command_recorded",
            **AUTHORITY,
            "writes_performed": True,
            "hardware_control_performed": False,
        }, 201)
        login = self.client.post(
            "/owner/login",
            data={"owner_token": "a" * 40, "next": "/dashboard"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )
        self.assertEqual(login.status_code, 302)
        response = self.client.post(
            "/api/telemetry/rootline/irrigation-commands", json=payload()
        )
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertFalse(body["dispatchable"])
        self.assertFalse(body["calls_ifttt"])
        self.assertFalse(body["calls_n8n"])
        self.assertFalse(body["hardware_control_performed"])


class IrrigationCommandMigrationContractTests(unittest.TestCase):
    def test_migration_is_append_only_and_forbids_execution_authority(self):
        migration = Path(
            "supabase/migrations/202607250002_create_irrigation_command_ledger.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("irrigation_command_ledger_block_update_delete", migration)
        self.assertIn("before update or delete", migration)
        self.assertIn("unique (zone_id, generation)", migration)
        self.assertIn(
            "from public, anon, authenticated",
            migration,
        )
        self.assertIn(
            "on sequence public.irrigation_command_state_events_event_sequence_seq",
            migration,
        )
        self.assertIn(
            "on function public.irrigation_command_ledger_block_update_delete()",
            migration,
        )
        self.assertIn("grant select, insert", migration)
        for field in (
            "calls_ifttt",
            "calls_n8n",
            "controls_hardware",
            "dispatchable",
            "automatic_retry",
        ):
            self.assertIn(f"check ({field} = false)", migration)
        for forbidden_state in RESERVED_FUTURE_STATES:
            self.assertNotIn(f"'{forbidden_state}'", migration)

    def test_disposable_postgres_job_runs_rootline_migration_test(self):
        workflow = Path(".github/workflows/oom-sakkie-audit-rails.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("ROOTLINE_DISPOSABLE_POSTGRES_URL=\"$DATABASE_URL\"", workflow)
        self.assertIn("tests.test_irrigation_command_ledger_postgres", workflow)


if __name__ == "__main__":
    unittest.main()
