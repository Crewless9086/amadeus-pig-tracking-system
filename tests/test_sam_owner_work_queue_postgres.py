import os
from pathlib import Path
import unittest
import uuid

from modules.sales.sam_owner_work_queue import list_owner_work_items


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

    def test_actionable_filter_applies_after_latest_event_selection(self):
        suffix = uuid.uuid4().hex
        work_item_id = f"SAM-OWNER-WORK-LATEST-{suffix}"
        first_event = f"SAM-OWNER-WORK-EVENT-A-{suffix}"
        second_event = f"SAM-OWNER-WORK-EVENT-B-{suffix}"
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    self._insert_sql(),
                    (first_event, work_item_id, suffix + "a", suffix + "a"),
                )
                cursor.execute(
                    """
                    insert into public.sam_owner_work_item_events (
                      work_event_id,work_item_id,account_id,conversation_id,
                      contact_id,inbox_id,ownership_mode,latest_message_id,
                      chronology_hash,observation_hash,unanswered_count,
                      classification,missed_message_classification,lane,
                      actionable,event_type,source,reconciliation_actor_id,
                      prior_event_id,observed_at
                    ) values (
                      %s,%s,'147387','2025','699428938','96568','HUMAN','101',
                      %s,%s,1,'CUSTOMER_REPLY_PROHIBITED',
                      'withheld_provider_window_and_security','GENERAL',false,
                      'withheld','postgres_contract',
                      'owner-admin:server-derived-test',%s,now()+interval '1 second'
                    )
                    """,
                    (second_event, work_item_id, suffix + "b", suffix + "b", first_event),
                )
            connection.commit()
        result, status = list_owner_work_items(
            database_url=self.database_url, include_withheld=False
        )
        self.assertEqual(status, 200)
        self.assertNotIn(
            work_item_id, {row["work_item_id"] for row in result["items"]}
        )
        result, status = list_owner_work_items(
            database_url=self.database_url, include_withheld=True
        )
        self.assertEqual(status, 200)
        current = next(row for row in result["items"] if row["work_item_id"] == work_item_id)
        self.assertEqual(current["work_event_id"], second_event)
        self.assertFalse(current["actionable"])


if __name__ == "__main__":
    unittest.main()
