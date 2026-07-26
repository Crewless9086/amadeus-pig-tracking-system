import os
from pathlib import Path
import unittest
import uuid


class SamOwnerWorkQueuePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = (
            os.getenv("SAM_OWNER_QUEUE_TEST_DATABASE_URL", "").strip()
            or os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        )
        if not cls.database_url:
            raise unittest.SkipTest("disposable owner queue PostgreSQL not configured")
        import psycopg
        cls.psycopg = psycopg
        migration = Path(
            "supabase/migrations/202607260002_create_sam_owner_work_items.sql"
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
                    alter default privileges in schema public
                      grant all privileges on tables to service_role;
                    alter default privileges in schema public
                      grant execute on functions to service_role;
                    """
                )
                cursor.execute(migration)
            connection.commit()

    @classmethod
    def _insert_sql(cls):
        return """
            insert into public.sam_owner_work_item_events (
              work_event_id, work_item_id, account_id, conversation_id,
              contact_id, inbox_id, ownership_mode, latest_message_id,
              chronology_hash, observation_hash, unanswered_count, classification,
              missed_message_classification, lane, actionable, event_type,
              source, reconciliation_actor_id, observed_at
            ) values (
              %s,%s,'147387','2025','699428938','96568','HUMAN','101',
              %s,%s,1,'WAITING_FOR_OWNER_REPLY','single_unanswered_inbound',
              'GENERAL',true,'actionable','postgres_contract',
              'owner-admin:server-derived-test',now()
            )
        """

    def test_client_roles_have_no_direct_read_or_write(self):
        for role in ("anon", "authenticated"):
            with self.psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(f"set local role {role}")
                    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                        cursor.execute("select count(*) from public.sam_owner_work_item_events")
                connection.rollback()

    def test_public_and_service_role_cannot_execute_trigger_function(self):
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for role in ("public", "service_role"):
                    cursor.execute(
                        """
                        select has_function_privilege(
                          %s, 'public.prevent_sam_owner_queue_mutation()', 'EXECUTE'
                        )
                        """,
                        (role,),
                    )
                    self.assertFalse(cursor.fetchone()[0])

    def test_service_role_can_append_and_read_but_not_update_or_delete(self):
        suffix = uuid.uuid4().hex
        event_id = f"SAM-OWNER-WORK-EVENT-{suffix}"
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute(
                    self._insert_sql(),
                    (event_id, f"SAM-OWNER-WORK-{suffix}", suffix, suffix),
                )
                cursor.execute(
                    "select work_event_id from public.sam_owner_work_item_events where work_event_id=%s",
                    (event_id,),
                )
                self.assertEqual(cursor.fetchone()[0], event_id)
                cursor.execute("savepoint update_denied")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "update public.sam_owner_work_item_events set actionable=false where work_event_id=%s",
                        (event_id,),
                    )
                cursor.execute("rollback to savepoint update_denied")
                cursor.execute("savepoint delete_denied")
                with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        "delete from public.sam_owner_work_item_events where work_event_id=%s",
                        (event_id,),
                    )
                cursor.execute("rollback to savepoint delete_denied")
            connection.rollback()

    def test_table_owner_is_still_blocked_by_append_only_trigger(self):
        suffix = uuid.uuid4().hex
        event_id = f"SAM-OWNER-WORK-EVENT-{suffix}"
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    self._insert_sql(),
                    (event_id, f"SAM-OWNER-WORK-{suffix}", suffix, suffix),
                )
                cursor.execute("savepoint immutable")
                with self.assertRaises(self.psycopg.errors.RaiseException):
                    cursor.execute(
                        "update public.sam_owner_work_item_events set actionable=false where work_event_id=%s",
                        (event_id,),
                    )
                cursor.execute("rollback to savepoint immutable")
            connection.rollback()


if __name__ == "__main__":
    unittest.main()
