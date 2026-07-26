import os
from pathlib import Path
import unittest
import uuid


class SamResponseClassAuthorityPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = (
            os.getenv("SAM_AUTHORITY_TEST_DATABASE_URL", "").strip()
            or os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        )
        if not cls.database_url:
            raise unittest.SkipTest("disposable authority PostgreSQL not configured")
        import psycopg
        cls.psycopg = psycopg
        migration = Path(
            "supabase/migrations/202607260001_create_sam_response_class_authority_events.sql"
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
            insert into public.sam_response_class_authority_events (
              authority_event_id,response_class,evidence_window_id,
              evidence_window_hash,evaluator_version,decision,
              actor_type,actor_id,reason,effective_at,expires_at
            ) values (%s,'greeting',%s,%s,
              'sam_response_class_graduation_v2','candidate',
              'server','test','disposable role proof',
              now(),now()+interval '1 day')
        """

    def _assert_role_denied(self, role):
        suffix = uuid.uuid4().hex
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"set local role {role}")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "select count(*) from public.sam_response_class_authority_events"
                    )
            connection.rollback()
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"set local role {role}")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        self._insert_sql(),
                        (f"SAM-AUTH-{suffix}", f"SAM-WINDOW-{suffix}", suffix),
                    )
            connection.rollback()

    def test_anon_and_authenticated_cannot_read_or_write_directly(self):
        self._assert_role_denied("anon")
        self._assert_role_denied("authenticated")

    def test_public_cannot_execute_authority_function(self):
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select has_function_privilege(
                      'public',
                      'public.prevent_sam_response_class_authority_mutation()',
                      'EXECUTE'
                    )
                    """
                )
                self.assertFalse(cursor.fetchone()[0])

    def test_service_role_can_insert_but_update_and_delete_stay_blocked(self):
        suffix = uuid.uuid4().hex
        event_id = f"SAM-AUTH-{suffix}"
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute(
                    self._insert_sql(),
                    (event_id, f"SAM-WINDOW-{suffix}", suffix),
                )
                cursor.execute("savepoint immutable_update")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        update public.sam_response_class_authority_events
                        set reason='changed' where authority_event_id=%s
                        """,
                        (event_id,),
                    )
                cursor.execute("rollback to savepoint immutable_update")
                cursor.execute("savepoint immutable_delete")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        """
                        delete from public.sam_response_class_authority_events
                        where authority_event_id=%s
                        """,
                        (event_id,),
                    )
                cursor.execute("rollback to savepoint immutable_delete")
            connection.rollback()

    def test_append_only_trigger_blocks_table_owner_update_and_delete(self):
        suffix = uuid.uuid4().hex
        event_id = f"SAM-AUTH-OWNER-{suffix}"
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    self._insert_sql(),
                    (event_id, f"SAM-WINDOW-{suffix}", suffix),
                )
                cursor.execute("savepoint owner_update")
                with self.assertRaises(self.psycopg.errors.RaiseException):
                    cursor.execute(
                        """
                        update public.sam_response_class_authority_events
                        set reason='changed' where authority_event_id=%s
                        """,
                        (event_id,),
                    )
                cursor.execute("rollback to savepoint owner_update")
                cursor.execute("savepoint owner_delete")
                with self.assertRaises(self.psycopg.errors.RaiseException):
                    cursor.execute(
                        """
                        delete from public.sam_response_class_authority_events
                        where authority_event_id=%s
                        """,
                        (event_id,),
                    )
                cursor.execute("rollback to savepoint owner_delete")
            connection.rollback()

    def test_direct_replay_and_conflicting_transition_are_rejected(self):
        suffix = uuid.uuid4().hex
        values = (f"SAM-AUTH-{suffix}", f"SAM-WINDOW-{suffix}", suffix)
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute(self._insert_sql(), values)
                cursor.execute("savepoint duplicate")
                with self.assertRaises(self.psycopg.errors.UniqueViolation):
                    cursor.execute(
                        self._insert_sql(),
                        (values[0] + "-2", values[1], values[2]),
                    )
                cursor.execute("rollback to savepoint duplicate")
            connection.rollback()


if __name__ == "__main__":
    unittest.main()
