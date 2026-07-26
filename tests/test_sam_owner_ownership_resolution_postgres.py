import os
from pathlib import Path
import unittest
import uuid

from modules.sales.sam_owner_ownership_resolution import record_resolution_event


class OwnerOwnershipResolutionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = (
            os.getenv("SAM_OWNER_QUEUE_TEST_DATABASE_URL", "").strip()
            or os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        )
        if not cls.database_url:
            raise unittest.SkipTest("disposable owner ownership PostgreSQL not configured")
        import psycopg
        cls.psycopg = psycopg
        migration = Path(
            "supabase/migrations/202607260007_create_sam_owner_ownership_resolution_events.sql"
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

    def _event(self):
        suffix = uuid.uuid4().hex
        return {
            "resolution_event_id": f"SAM-OWNER-RESOLUTION-EVENT-{suffix}",
            "resolution_id": f"SAM-OWNER-RESOLUTION-{suffix}",
            "event_type": "claim", "target_mode": "HUMAN",
            "work_item_id": f"SAM-OWNER-WORK-{suffix}",
            "work_event_id": f"SAM-OWNER-WORK-EVENT-{suffix}",
            "account_id": "147387", "conversation_id": "1997",
            "contact_id": "contact-1997", "inbox_id": "96568",
            "observation_hash": suffix, "chronology_hash": suffix,
            "latest_inbound_message_id": "inbound-1997",
            "unanswered_count": 1, "review_event_id": "SAM-LIVE-REVIEW-1997",
            "window_evidence_hash": suffix, "actor_id": "owner-admin:server",
            "outcome": "claimed", "reason": "", "prior_event_id": None,
            "created_at": "2026-07-26T12:00:00+00:00",
        }

    def test_anon_authenticated_and_public_have_no_direct_authority(self):
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated"):
                    cursor.execute("select has_table_privilege(%s,%s,'SELECT')", (
                        role, "public.sam_owner_ownership_resolution_events",
                    ))
                    self.assertFalse(cursor.fetchone()[0])
                    cursor.execute("select has_table_privilege(%s,%s,'INSERT')", (
                        role, "public.sam_owner_ownership_resolution_events",
                    ))
                    self.assertFalse(cursor.fetchone()[0])
                cursor.execute(
                    "select has_function_privilege('public','public.prevent_sam_owner_resolution_mutation()','EXECUTE')"
                )
                self.assertFalse(cursor.fetchone()[0])

    def test_service_role_can_append_and_read_only(self):
        event = self._event()
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute(
                    """
                    insert into public.sam_owner_ownership_resolution_events (
                      resolution_event_id,resolution_id,event_type,target_mode,
                      work_item_id,work_event_id,account_id,conversation_id,
                      contact_id,inbox_id,observation_hash,chronology_hash,
                      latest_inbound_message_id,unanswered_count,review_event_id,
                      window_evidence_hash,actor_id,outcome,created_at
                    ) values (
                      %(resolution_event_id)s,%(resolution_id)s,%(event_type)s,
                      %(target_mode)s,%(work_item_id)s,%(work_event_id)s,
                      %(account_id)s,%(conversation_id)s,%(contact_id)s,
                      %(inbox_id)s,%(observation_hash)s,%(chronology_hash)s,
                      %(latest_inbound_message_id)s,%(unanswered_count)s,
                      %(review_event_id)s,%(window_evidence_hash)s,%(actor_id)s,
                      %(outcome)s,%(created_at)s::timestamptz
                    )
                    """,
                    event,
                )
                cursor.execute(
                    "select outcome from public.sam_owner_ownership_resolution_events where resolution_event_id=%s",
                    (event["resolution_event_id"],),
                )
                self.assertEqual(cursor.fetchone()[0], "claimed")
                for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                    cursor.execute(
                        "select has_table_privilege('service_role',%s,%s)",
                        ("public.sam_owner_ownership_resolution_events", privilege),
                    )
                    self.assertFalse(cursor.fetchone()[0])
            connection.rollback()

    def test_server_persistence_is_idempotent_and_history_immutable(self):
        event = self._event()
        first, first_status = record_resolution_event(event, database_url=self.database_url)
        second, second_status = record_resolution_event(event, database_url=self.database_url)
        self.assertEqual(first_status, 201)
        self.assertTrue(first["created"])
        self.assertEqual(second_status, 200)
        self.assertFalse(second["created"])
        with self.psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(self.psycopg.errors.RaiseException):
                    cursor.execute(
                        "update public.sam_owner_ownership_resolution_events set outcome='changed' where resolution_event_id=%s",
                        (event["resolution_event_id"],),
                    )
            connection.rollback()
