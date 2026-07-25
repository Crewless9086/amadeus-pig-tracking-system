"""Opt-in disposable-Postgres verification for the ROOTLINE B1 ledger.

This test connects only when ROOTLINE_DISPOSABLE_POSTGRES_URL is explicitly
provided. It never falls back to DATABASE_URL or any production database.
"""

import json
import os
import unittest
import uuid
from pathlib import Path

import psycopg


class IrrigationCommandLedgerPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest(
                "ROOTLINE_DISPOSABLE_POSTGRES_URL not configured for disposable ledger tests"
            )
        migrations = Path("supabase/migrations")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    (migrations / "202605210001_foundation_migration_log.sql").read_text(
                        encoding="utf-8"
                    )
                )
                cursor.execute(
                    (
                        migrations
                        / "202607250002_create_irrigation_command_ledger.sql"
                    ).read_text(encoding="utf-8")
                )

    def setUp(self):
        self.identity = uuid.uuid4().hex
        self.generation = (int(self.identity[:8], 16) % 2_000_000_000) + 1
        self.command_id = f"ROOTLINE-CMD-{self.identity}"
        self.event_id = f"ROOTLINE-EVENT-{self.identity}"

    def _insert_plan(self, cursor, **overrides):
        values = {
            "command_id": self.command_id,
            "generation": self.generation,
            "zone_id": "B12345",
            "zone_name": "B - Kamp",
            "intent": "ON",
            "requested_duration_minutes": 10,
            "created_at": "2026-07-25T12:00:00+00:00",
            "expires_at": "2026-07-25T12:10:00+00:00",
            "idempotency_key": f"rootline-test-{self.identity}",
            "request_sha256": "a" * 64,
            "paired_off_required": True,
            "paired_off_command_id": f"ROOTLINE-OFF-{self.identity}",
            "weather_evidence": json.dumps({"freshness": "fresh"}),
            "power_evidence": json.dumps({"confidence": "verified"}),
            "water_evidence": json.dumps({"tank": {"availability": "Unavailable"}}),
            "inventory": json.dumps({"inventory_partial": True}),
            "safety": json.dumps({"manual_isolation_verified": False}),
            "reasons": json.dumps(["execution_prohibited"]),
            "command_json": json.dumps({"command_id": self.command_id}),
            "recorded_by": "owner-admin:test",
        }
        values.update(overrides)
        cursor.execute(
            """
            insert into public.irrigation_command_plans (
                command_id, generation, zone_id, zone_name, intent,
                requested_duration_minutes, created_at, expires_at,
                idempotency_key, request_sha256, paired_off_required,
                paired_off_command_id, weather_evidence, power_evidence,
                water_infrastructure_evidence, controller_actuator_inventory,
                safety_interlocks, prohibition_reasons, command_json, recorded_by
            ) values (
                %(command_id)s, %(generation)s, %(zone_id)s, %(zone_name)s, %(intent)s,
                %(requested_duration_minutes)s, %(created_at)s, %(expires_at)s,
                %(idempotency_key)s, %(request_sha256)s, %(paired_off_required)s,
                %(paired_off_command_id)s, %(weather_evidence)s::jsonb,
                %(power_evidence)s::jsonb, %(water_evidence)s::jsonb,
                %(inventory)s::jsonb, %(safety)s::jsonb, %(reasons)s::jsonb,
                %(command_json)s::jsonb, %(recorded_by)s
            )
            """,
            values,
        )

    def test_append_only_constraints_and_current_states(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                self._insert_plan(cursor)
                cursor.execute(
                    """
                    insert into public.irrigation_command_state_events (
                        event_id, command_id, generation, state, occurred_at, evidence_json
                    ) values (%s,%s,%s,'execution_prohibited',now(),%s::jsonb)
                    """,
                    (
                        self.event_id,
                        self.command_id,
                        self.generation,
                        json.dumps({"dispatchable": False}),
                    ),
                )
                connection.commit()
                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        "update public.irrigation_command_plans set zone_name = 'changed' where command_id = %s",
                        (self.command_id,),
                    )
                connection.rollback()
                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        "delete from public.irrigation_command_state_events where event_id = %s",
                        (self.event_id,),
                    )

    def test_future_state_and_authority_true_are_database_rejected(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                self._insert_plan(cursor)
                connection.commit()
                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        """
                        insert into public.irrigation_command_state_events (
                            event_id, command_id, generation, state, occurred_at, evidence_json
                        ) values (%s,%s,%s,'dispatched',now(),'{}'::jsonb)
                        """,
                        (self.event_id, self.command_id, self.generation),
                    )
                connection.rollback()
                with self.assertRaises(psycopg.Error):
                    cursor.execute(
                        """
                        insert into public.irrigation_command_state_events (
                            event_id, command_id, generation, state, occurred_at,
                            evidence_json, controls_hardware
                        ) values (%s,%s,%s,'proposed',now(),'{}'::jsonb,true)
                        """,
                        (self.event_id, self.command_id, self.generation),
                    )

    def test_duplicate_idempotency_and_conflicting_zone_generation_are_rejected(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                self._insert_plan(cursor)
                connection.commit()
                with self.assertRaises(psycopg.Error):
                    self._insert_plan(cursor, command_id=f"{self.command_id}-DUP")
                connection.rollback()
                with self.assertRaises(psycopg.Error):
                    self._insert_plan(
                        cursor,
                        command_id=f"{self.command_id}-OFF",
                        idempotency_key=f"other-{self.identity}",
                        intent="OFF",
                        paired_off_required=False,
                        paired_off_command_id=None,
                    )


if __name__ == "__main__":
    unittest.main()
