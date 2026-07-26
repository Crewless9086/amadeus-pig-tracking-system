import os
from pathlib import Path
import unittest

import psycopg

from modules.beacon.organic_media_intelligence import (
    append_learning_event,
    evaluate_graduation,
)


DATABASE_URL = os.getenv("BEACON_WEEKLY_REVIEW_POSTGRES_URL", "").strip()
TABLE = "public.beacon_organic_media_learning_events"
FUNCTION = "public.prevent_beacon_organic_media_learning_mutation()"


@unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL is required")
class OrganicMediaIntelligencePostgresTests(unittest.TestCase):
    def test_privileges_append_only_replay_conflict_and_cross_post_isolation(self):
        migration = Path(
            "supabase/migrations/202607260008_create_beacon_organic_media_learning.sql"
        ).read_text(encoding="utf-8")
        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(migration)
                cursor.execute(f"truncate table {TABLE}")

        event = {
            "event_id": "LEARNING-POSTGRES-1",
            "event_kind": "post_understanding",
            "facebook_post_id": "post-one",
            "channel": "Facebook",
            "objective": "farm_awareness",
            "evidence_key": "post-one/understanding/v1",
            "payload": {"status": "ready"},
        }
        created, created_status = append_learning_event(event, DATABASE_URL)
        replay, replay_status = append_learning_event(event, DATABASE_URL)
        conflict, conflict_status = append_learning_event(
            {**event, "facebook_post_id": "post-two"}, DATABASE_URL
        )
        self.assertEqual((created_status, created["created_count"]), (201, 1))
        self.assertEqual((replay_status, replay["created_count"]), (200, 0))
        self.assertEqual(
            (conflict_status, conflict["status"]),
            (409, "organic_learning_identity_conflict"),
        )
        graduation = evaluate_graduation(DATABASE_URL)
        self.assertTrue(graduation["persistence_available"])
        self.assertEqual(graduation["observed"]["distinct_confirmed_posts"], 0)

        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                for role in ("anon", "authenticated"):
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                        cursor.execute(
                            "select has_table_privilege(%s,%s,%s)",
                            (role, TABLE, privilege),
                        )
                        self.assertFalse(cursor.fetchone()[0])
                cursor.execute(
                    """select count(*) from information_schema.table_privileges
                       where grantee='PUBLIC'
                         and table_schema='public'
                         and table_name='beacon_organic_media_learning_events'"""
                )
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute(
                    """select count(*) from information_schema.routine_privileges
                       where grantee='PUBLIC'
                         and routine_schema='public'
                         and routine_name='prevent_beacon_organic_media_learning_mutation'"""
                )
                self.assertEqual(cursor.fetchone()[0], 0)
                for role in ("anon", "authenticated", "service_role"):
                    cursor.execute(
                        "select has_function_privilege(%s,%s,'EXECUTE')",
                        (role, FUNCTION),
                    )
                    self.assertFalse(cursor.fetchone()[0])
                cursor.execute("savepoint cross_post")
                with self.assertRaises(psycopg.errors.CheckViolation):
                    cursor.execute(
                        f"""insert into {TABLE}
                        (event_id,event_kind,facebook_post_id,channel,objective,
                         evidence_key,payload_sha256,payload_json)
                        values (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)""",
                        (
                            "cross-post", "post_understanding", "post-one",
                            "Facebook", "farm_awareness", "cross/post",
                            "a" * 64,
                            """{"event_kind":"post_understanding",
                            "facebook_post_id":"post-two","channel":"Facebook",
                            "objective":"farm_awareness","measurement_window":"",
                            "publish":false,"retry":false,"schedule":false,
                            "meta_write":false,"boost":false,"advertise":false,
                            "spend":false,"send":false,
                            "business_data_mutation":false}""",
                        ),
                    )
                cursor.execute("rollback to savepoint cross_post")
                cursor.execute("savepoint update_learning")
                with self.assertRaises(psycopg.errors.RaiseException):
                    cursor.execute(f"update {TABLE} set objective='changed'")
                cursor.execute("rollback to savepoint update_learning")
                cursor.execute("savepoint delete_learning")
                with self.assertRaises(psycopg.errors.RaiseException):
                    cursor.execute(f"delete from {TABLE}")
                cursor.execute("rollback to savepoint delete_learning")
            connection.rollback()
