import os
from pathlib import Path
import unittest
import uuid
from datetime import datetime, timezone

from modules.sales.sam_owner_work_queue import (
    build_owner_work_observation,
    list_owner_work_items,
    record_owner_work_observation,
)


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
        window_migration = Path(
            "supabase/migrations/202607260006_add_sam_owner_reply_window_protection.sql"
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
                cursor.execute(window_migration)
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

    def test_window_alert_persistence_is_deduplicated_and_never_delivered(self):
        observation = build_owner_work_observation(
            {
                "account_id": "147387",
                "id": "window-postgres",
                "contact_id": "699428938",
                "inbox_id": "96568",
                "channel": "Channel::Whatsapp",
                "custom_attributes": {"conversation_mode": "HUMAN"},
                "labels": ["sam_live_stock"],
                "messages": [{
                    "id": "101", "message_type": 0, "private": False,
                    "created_at": "2026-07-25T13:00:00+00:00",
                }],
            },
            review={
                "review_event_id": "SAM-LIVE-REVIEW-WINDOW-PG",
                "chatwoot_conversation_id": "window-postgres",
                "chatwoot_message_id": "101",
            },
            reconciliation_actor_id="owner-admin:server-derived-test",
            observed_at=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
        )
        first, first_status = record_owner_work_observation(
            observation, database_url=self.database_url
        )
        second, second_status = record_owner_work_observation(
            observation, database_url=self.database_url
        )
        self.assertEqual(first_status, 201)
        self.assertEqual(second_status, 200)
        self.assertTrue(first["alert_prepared"])
        self.assertFalse(second["created"])
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select count(*),bool_or(delivery_enabled),bool_or(delivered),
                           bool_or(contains_customer_content),
                           bool_or(sends_customer_message),
                           bool_or(calls_telegram),bool_or(uses_template)
                    from public.sam_owner_window_alert_events
                    where work_item_id=%s
                    """,
                    (observation["work_item_id"],),
                )
                count, delivery, delivered, content, send, telegram, template = cursor.fetchone()
        self.assertEqual(count, 1)
        self.assertFalse(any((delivery, delivered, content, send, telegram, template)))

    def test_ownership_exception_persists_normalized_without_send_or_ownership_authority(self):
        suffix = uuid.uuid4().hex
        observation = build_owner_work_observation(
            {
                "account_id": "147387",
                "id": f"ownership-{suffix}",
                "contact_id": "699428938",
                "inbox_id": "96568",
                "channel": "Channel::Whatsapp",
                "custom_attributes": {},
                "labels": [],
                "messages": [{
                    "id": "101", "message_type": 0, "private": False,
                    "created_at": "2026-07-26T10:00:00+00:00",
                }],
            },
            review={
                "review_event_id": f"SAM-LIVE-REVIEW-{suffix}",
                "chatwoot_conversation_id": f"ownership-{suffix}",
                "chatwoot_message_id": "101",
            },
            reconciliation_actor_id="owner-admin:server-derived-test",
            observed_at=datetime(2026, 7, 26, 12, tzinfo=timezone.utc),
        )
        result, status = record_owner_work_observation(
            observation, database_url=self.database_url
        )
        self.assertEqual(status, 201)
        self.assertTrue(result["created"])
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select ownership_mode,classification,actionable,
                           withheld_reasons_json,ordinary_reply_allowed,
                           send_reply_action_visible,sends_customer_message,
                           changes_conversation_ownership,calls_telegram,
                           mutates_business_state
                    from public.sam_owner_work_item_events
                    where work_event_id=%s
                    """,
                    (observation["work_event_id"],),
                )
                row = cursor.fetchone()
        self.assertEqual(row[0], "UNAVAILABLE")
        self.assertEqual(row[1], "OWNERSHIP_DECISION_REQUIRED")
        self.assertTrue(row[2])
        self.assertEqual(row[3], ["conversation_ownership_missing"])
        self.assertFalse(any(row[4:]))

    def test_window_alert_table_privileges_and_immutability(self):
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated"):
                    cursor.execute(
                        "select has_table_privilege(%s,'public.sam_owner_window_alert_events','SELECT')",
                        (role,),
                    )
                    self.assertFalse(cursor.fetchone()[0])
                    cursor.execute(
                        "select has_table_privilege(%s,'public.sam_owner_window_alert_events','INSERT')",
                        (role,),
                    )
                    self.assertFalse(cursor.fetchone()[0])
                for privilege, expected in (
                    ("SELECT", True), ("INSERT", True), ("UPDATE", False),
                    ("DELETE", False), ("TRUNCATE", False),
                ):
                    cursor.execute(
                        "select has_table_privilege('service_role','public.sam_owner_window_alert_events',%s)",
                        (privilege,),
                    )
                    self.assertEqual(cursor.fetchone()[0], expected)

    def test_actionable_queue_orders_nearest_expiry_first(self):
        suffix = uuid.uuid4().hex
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for offset, label in ((5, "later"), (1, "nearer")):
                    cursor.execute(
                        """
                        insert into public.sam_owner_work_item_events (
                          work_event_id,work_item_id,account_id,conversation_id,
                          contact_id,inbox_id,ownership_mode,latest_message_id,
                          chronology_hash,observation_hash,unanswered_count,
                          classification,missed_message_classification,lane,
                          actionable,event_type,source,reconciliation_actor_id,
                          observed_at,window_state,reply_authority_state,
                          window_reason,provider_identity_class,
                          window_evidence_hash,expires_at_utc,
                          expires_at_johannesburg,remaining_seconds,
                          alert_band,ordinary_reply_allowed,
                          send_reply_action_visible
                        ) values (
                          %s,%s,'147387',%s,'699428938','96568','HUMAN','101',
                          %s,%s,1,'WAITING_FOR_OWNER_REPLY',
                          'single_unanswered_inbound','GENERAL',true,
                          'actionable','postgres_priority',
                          'owner-admin:server-derived-test',now(),'open',
                          'ordinary_reply_allowed','reply_window_open',
                          'genuine_whatsapp',%s,now()+(%s||' hours')::interval,
                          now()+(%s||' hours')::interval,%s*3600,'none',true,true
                        )
                        """,
                        (
                            f"EVENT-{label}-{suffix}", f"WORK-{label}-{suffix}",
                            f"CONV-{label}-{suffix}", f"CHRON-{label}-{suffix}",
                            f"OBS-{label}-{suffix}", f"WINDOW-{label}-{suffix}",
                            offset, offset, offset,
                        ),
                    )
            connection.commit()
        result, status = list_owner_work_items(
            database_url=self.database_url, include_withheld=False
        )
        self.assertEqual(status, 200)
        identities = [row["work_item_id"] for row in result["items"]]
        self.assertLess(
            identities.index(f"WORK-nearer-{suffix}"),
            identities.index(f"WORK-later-{suffix}"),
        )


if __name__ == "__main__":
    unittest.main()
