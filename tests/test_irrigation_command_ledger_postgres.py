"""Opt-in disposable-Postgres verification for the ROOTLINE B1 ledger.

This test connects only when ROOTLINE_DISPOSABLE_POSTGRES_URL is explicitly
provided. It never falls back to DATABASE_URL or any production database.
"""

import json
import os
import unittest
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

import psycopg

from app import app


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
                    """
                    do $$
                    begin create role anon nologin;
                    exception when duplicate_object then null;
                    end $$;
                    do $$
                    begin create role authenticated nologin;
                    exception when duplicate_object then null;
                    end $$;
                    do $$
                    begin create role service_role nologin bypassrls;
                    exception when duplicate_object then null;
                    end $$;
                    alter default privileges in schema public
                        grant all privileges on tables
                        to public, anon, authenticated, service_role;
                    alter default privileges in schema public
                        grant all privileges on sequences
                        to public, anon, authenticated, service_role;
                    alter default privileges in schema public
                        grant execute on functions
                        to public, anon, authenticated, service_role;
                    """
                )
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
            "writes_farm_data": False,
            "writes_telemetry": False,
            "mutates_schedule": False,
            "calls_ifttt": False,
            "calls_n8n": False,
            "controls_hardware": False,
            "dispatchable": False,
            "automatic_retry": False,
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
                safety_interlocks, prohibition_reasons, command_json, recorded_by,
                writes_farm_data, writes_telemetry, mutates_schedule,
                calls_ifttt, calls_n8n, controls_hardware, dispatchable,
                automatic_retry
            ) values (
                %(command_id)s, %(generation)s, %(zone_id)s, %(zone_name)s, %(intent)s,
                %(requested_duration_minutes)s, %(created_at)s, %(expires_at)s,
                %(idempotency_key)s, %(request_sha256)s, %(paired_off_required)s,
                %(paired_off_command_id)s, %(weather_evidence)s::jsonb,
                %(power_evidence)s::jsonb, %(water_evidence)s::jsonb,
                %(inventory)s::jsonb, %(safety)s::jsonb, %(reasons)s::jsonb,
                %(command_json)s::jsonb, %(recorded_by)s,
                %(writes_farm_data)s, %(writes_telemetry)s, %(mutates_schedule)s,
                %(calls_ifttt)s, %(calls_n8n)s, %(controls_hardware)s,
                %(dispatchable)s, %(automatic_retry)s
            )
            """,
            values,
        )

    def test_production_shaped_roles_are_denied_and_service_role_can_append(self):
        tables = (
            "public.irrigation_command_plans",
            "public.irrigation_command_state_events",
        )
        sequence = (
            "public.irrigation_command_state_events_event_sequence_seq"
        )
        function = "public.irrigation_command_ledger_block_update_delete()"
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated"):
                    for table in tables:
                        for privilege in (
                            "SELECT",
                            "INSERT",
                            "UPDATE",
                            "DELETE",
                            "TRUNCATE",
                            "REFERENCES",
                            "TRIGGER",
                        ):
                            cursor.execute(
                                "select has_table_privilege(%s, %s, %s)",
                                (role, table, privilege),
                            )
                            self.assertFalse(
                                cursor.fetchone()[0],
                                f"{role} retained {privilege} on {table}",
                            )
                    for privilege in ("USAGE", "SELECT", "UPDATE"):
                        cursor.execute(
                            "select has_sequence_privilege(%s, %s, %s)",
                            (role, sequence, privilege),
                        )
                        self.assertFalse(
                            cursor.fetchone()[0],
                            f"{role} retained {privilege} on {sequence}",
                        )
                    cursor.execute(
                        "select has_function_privilege(%s, %s, 'EXECUTE')",
                        (role, function),
                    )
                    self.assertFalse(cursor.fetchone()[0])

                cursor.execute(
                    """
                    select coalesce(bool_or(
                        acl.grantee = 0 and acl.privilege_type = 'EXECUTE'
                    ), false)
                    from pg_proc proc
                    cross join lateral aclexplode(
                        coalesce(proc.proacl, acldefault('f', proc.proowner))
                    ) acl
                    where proc.oid=%s::regprocedure
                    """,
                    (function,),
                )
                self.assertFalse(cursor.fetchone()[0])

                for table in tables:
                    for privilege in ("SELECT", "INSERT"):
                        cursor.execute(
                            "select has_table_privilege('service_role', %s, %s)",
                            (table, privilege),
                        )
                        self.assertTrue(cursor.fetchone()[0])
                    for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                        cursor.execute(
                            "select has_table_privilege('service_role', %s, %s)",
                            (table, privilege),
                        )
                        self.assertFalse(cursor.fetchone()[0])

                cursor.execute("set local role service_role")
                self._insert_plan(cursor)
                cursor.execute(
                    """
                    insert into public.irrigation_command_state_events (
                        event_id, command_id, generation, state, occurred_at,
                        evidence_json
                    ) values (%s,%s,%s,'execution_prohibited',now(),'{}'::jsonb)
                    """,
                    (self.event_id, self.command_id, self.generation),
                )
                cursor.execute(
                    "select count(*) from public.irrigation_command_plans "
                    "where command_id=%s",
                    (self.command_id,),
                )
                self.assertEqual(cursor.fetchone()[0], 1)
            connection.rollback()

        for role in ("anon", "authenticated"):
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"set local role {role}")
                    with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                        cursor.execute(
                            "select * from public.irrigation_command_plans"
                        )
                connection.rollback()

    def test_owner_admin_application_route_persists_plan_only_record(self):
        now = datetime.now(timezone.utc)
        route_payload = {
            "generation": self.generation,
            "zone_id": "B12345",
            "zone_name": "B - Kamp",
            "intent": "ON",
            "requested_duration_minutes": 1,
            "created_at": now.isoformat(),
            "expires_at": (now + timedelta(minutes=5)).isoformat(),
            "weather_evidence": {
                "availability": "Unavailable",
                "freshness": "Unavailable",
            },
            "power_evidence": {
                "availability": "Unavailable",
                "confidence": "unverified",
                "suspicious": True,
            },
            "water_infrastructure_evidence": {
                "tank": {"availability": "Unavailable"},
                "pump": {"availability": "Unavailable"},
                "borehole": {"availability": "Unavailable"},
            },
            "safety_interlocks": {
                "manual_isolation_verified": False,
                "failure_safe_verified": False,
                "paired_off_ready": False,
            },
            "paired_off_command_id": f"ROOTLINE-OFF-{self.identity}",
            "idempotency_key": f"rootline-route-{self.identity}",
        }
        app.config.update(TESTING=True, SECRET_KEY="rootline-postgres-route-test")
        with mock.patch.dict(
            os.environ,
            {
                "DATABASE_URL": self.database_url,
                "OWNER_ACCESS_ENABLED": "1",
                "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
                "OWNER_SESSION_SECRET": "s" * 40,
                "OWNER_READ_TOKEN": "r" * 40,
                "OWNER_ADMIN_TOKEN": "a" * 40,
            },
            clear=False,
        ):
            client = app.test_client()
            login = client.post(
                "/owner/login",
                data={"owner_token": "a" * 40, "next": "/dashboard"},
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
            self.assertEqual(login.status_code, 302)
            response = client.post(
                "/api/telemetry/rootline/irrigation-commands",
                json=route_payload,
            )
        self.assertEqual(response.status_code, 201)
        body = response.get_json()
        self.assertEqual(body["status"], "plan_only_command_recorded")
        self.assertEqual(body["command"]["state"], "execution_prohibited")
        for field in (
            "dispatchable",
            "calls_ifttt",
            "calls_n8n",
            "controls_hardware",
            "mutates_schedule",
            "automatic_retry",
        ):
            self.assertFalse(body[field])
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select count(*) from public.irrigation_command_plans
                    where idempotency_key=%s
                    """,
                    (route_payload["idempotency_key"],),
                )
                self.assertEqual(cursor.fetchone()[0], 1)

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
                event_authority_fields = (
                    "writes_farm_data",
                    "writes_telemetry",
                    "mutates_schedule",
                    "calls_ifttt",
                    "calls_n8n",
                    "controls_hardware",
                    "dispatchable",
                    "automatic_retry",
                )
                for index, field in enumerate(event_authority_fields):
                    cursor.execute("savepoint authority_field")
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        cursor.execute(
                            f"""
                            insert into public.irrigation_command_state_events (
                                event_id, command_id, generation, state,
                                occurred_at, evidence_json, {field}
                            ) values (%s,%s,%s,'proposed',now(),'{{}}'::jsonb,true)
                            """,
                            (
                                f"{self.event_id}-{index}",
                                self.command_id,
                                self.generation,
                            ),
                        )
                    cursor.execute("rollback to savepoint authority_field")

                plan_authority_fields = (
                    "writes_farm_data",
                    "writes_telemetry",
                    "mutates_schedule",
                    "calls_ifttt",
                    "calls_n8n",
                    "controls_hardware",
                    "dispatchable",
                    "automatic_retry",
                )
                for field in plan_authority_fields:
                    cursor.execute("savepoint plan_authority_field")
                    with self.assertRaises(psycopg.errors.CheckViolation):
                        self._insert_plan(
                            cursor,
                            command_id=f"{self.command_id}-{field}",
                            generation=self.generation + 1,
                            idempotency_key=f"{self.identity}-{field}",
                            **{field: True},
                        )
                    cursor.execute("rollback to savepoint plan_authority_field")

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
