import os
from pathlib import Path
import unittest
import uuid


class SamLiveStockLevel1ControlPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = (
            os.getenv("SAM_LEVEL1_TEST_DATABASE_URL", "").strip()
            or os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        )
        if not cls.database_url:
            raise unittest.SkipTest("disposable Level 1 PostgreSQL not configured")
        import psycopg

        cls.psycopg = psycopg
        migration = Path(
            "supabase/migrations/"
            "202607280002_create_sam_live_stock_level1_control_events.sql"
        ).read_text(encoding="utf-8")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    do $$ begin create role anon nologin;
                    exception when duplicate_object then null; end $$;
                    do $$ begin create role authenticated nologin;
                    exception when duplicate_object then null; end $$;
                    do $$ begin create role service_role nologin bypassrls;
                    exception when duplicate_object then null; end $$;
                    """
                )
                cursor.execute(migration)
            connection.commit()

    @classmethod
    def _insert_sql(cls):
        return """
          insert into public.sam_live_stock_level1_control_events (
            control_event_id, state, policy_version, activation_cutoff_utc,
            actor_id, reason, effective_at, expires_at
          ) values (
            %s, 'enabled', 'sam_sales_autonomy_level_1_v1', now(),
            'owner-admin:test', 'disposable role proof',
            now(), now() + interval '1 day'
          )
        """

    def _assert_role_denied(self, role):
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"set local role {role}")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "select count(*) from public."
                        "sam_live_stock_level1_control_events"
                    )
            connection.rollback()
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"set local role {role}")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        self._insert_sql(),
                        (f"SAM-L1-{uuid.uuid4().hex}",),
                    )
            connection.rollback()

    def test_client_roles_cannot_read_or_write(self):
        self._assert_role_denied("anon")
        self._assert_role_denied("authenticated")

    def test_public_and_service_role_cannot_execute_guard_function(self):
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for role in ("public", "service_role"):
                    cursor.execute(
                        """
                        select has_function_privilege(
                          %s,
                          'public.prevent_sam_live_stock_level1_control_mutation()',
                          'EXECUTE'
                        )
                        """,
                        (role,),
                    )
                    self.assertFalse(cursor.fetchone()[0])

    def test_service_role_can_append_and_read_but_cannot_mutate(self):
        event_id = f"SAM-L1-{uuid.uuid4().hex}"
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute(self._insert_sql(), (event_id,))
                cursor.execute(
                    """
                    select state from public.sam_live_stock_level1_control_events
                    where control_event_id=%s
                    """,
                    (event_id,),
                )
                self.assertEqual(cursor.fetchone()[0], "enabled")
                for operation in ("update", "delete"):
                    cursor.execute(f"savepoint before_{operation}")
                    with self.assertRaises(
                        self.psycopg.errors.InsufficientPrivilege
                    ):
                        if operation == "update":
                            cursor.execute(
                                """
                                update public.sam_live_stock_level1_control_events
                                set reason='changed' where control_event_id=%s
                                """,
                                (event_id,),
                            )
                        else:
                            cursor.execute(
                                """
                                delete from public.sam_live_stock_level1_control_events
                                where control_event_id=%s
                                """,
                                (event_id,),
                            )
                    cursor.execute(f"rollback to savepoint before_{operation}")
            connection.rollback()

    def test_table_owner_is_blocked_by_append_only_trigger(self):
        event_id = f"SAM-L1-OWNER-{uuid.uuid4().hex}"
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(self._insert_sql(), (event_id,))
                for operation in ("update", "delete"):
                    cursor.execute(f"savepoint owner_{operation}")
                    with self.assertRaises(self.psycopg.errors.RaiseException):
                        if operation == "update":
                            cursor.execute(
                                """
                                update public.sam_live_stock_level1_control_events
                                set reason='changed' where control_event_id=%s
                                """,
                                (event_id,),
                            )
                        else:
                            cursor.execute(
                                """
                                delete from public.sam_live_stock_level1_control_events
                                where control_event_id=%s
                                """,
                                (event_id,),
                            )
                    cursor.execute(f"rollback to savepoint owner_{operation}")
            connection.rollback()

    def test_conflicting_concurrent_root_events_are_rejected(self):
        first_id = f"SAM-L1-ROOT-{uuid.uuid4().hex}"
        second_id = f"SAM-L1-ROOT-{uuid.uuid4().hex}"
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(self._insert_sql(), (first_id,))
                cursor.execute("savepoint conflicting_root")
                with self.assertRaises(self.psycopg.errors.UniqueViolation):
                    cursor.execute(self._insert_sql(), (second_id,))
                cursor.execute("rollback to savepoint conflicting_root")
            connection.rollback()


if __name__ == "__main__":
    unittest.main()
