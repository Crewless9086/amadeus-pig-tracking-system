import os
import unittest
from unittest.mock import patch

import psycopg

from modules.beacon.weekly_owner_review_decisions import (
    record_weekly_owner_review_decision,
)
from tests.test_beacon_weekly_owner_review_decisions import (
    eligible_assets,
    exact_payload,
)


DATABASE_URL = os.getenv("BEACON_WEEKLY_REVIEW_POSTGRES_URL", "").strip()
TABLE = "public.beacon_weekly_review_decision_events"
FUNCTION = "public.prevent_beacon_weekly_review_decision_mutation()"


@unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL is required")
class WeeklyOwnerReviewDecisionPostgresTests(unittest.TestCase):
    def test_supabase_roles_and_server_boundary_are_fail_closed(self):
        failed, status = record_weekly_owner_review_decision(
            exact_payload(), owner_identity="", database_url=DATABASE_URL
        )
        self.assertEqual((status, failed["status"]), (403, "owner_identity_required"))
        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(f"select count(*) from {TABLE}")
                self.assertEqual(cursor.fetchone()[0], 0)

        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select relrowsecurity from pg_class
                    where oid=%s::regclass
                    """,
                    (TABLE,),
                )
                self.assertTrue(cursor.fetchone()[0])
                for role in ("anon", "authenticated"):
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
                            (role, TABLE, privilege),
                        )
                        self.assertFalse(
                            cursor.fetchone()[0], f"{role} retained {privilege}"
                        )
                    cursor.execute(
                        "select has_function_privilege(%s, %s, 'EXECUTE')",
                        (role, FUNCTION),
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
                    (FUNCTION,),
                )
                self.assertFalse(cursor.fetchone()[0])
                for privilege in ("SELECT", "INSERT"):
                    cursor.execute(
                        "select has_table_privilege('service_role', %s, %s)",
                        (TABLE, privilege),
                    )
                    self.assertTrue(cursor.fetchone()[0])
                for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                    cursor.execute(
                        "select has_table_privilege('service_role', %s, %s)",
                        (TABLE, privilege),
                    )
                    self.assertFalse(cursor.fetchone()[0])

        self._assert_direct_client_insert_denied("anon")
        self._assert_direct_client_insert_denied("authenticated")
        self._assert_service_role_append_only()
        self._assert_application_boundary_idempotency()

    def _assert_direct_client_insert_denied(self, role):
        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local role " + role)
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    cursor.execute(
                        f"""
                        insert into {TABLE} (
                            decision_event_id, packet_id, packet_version,
                            canonical_sha256, caption_sha256, exact_caption,
                            ordered_media_ids_json, owner_confirmed_subject,
                            album_story, channel, decision_status, owner_identity
                        ) values (
                            %s, %s, 'test-v1', %s, %s, 'denied',
                            '[]'::jsonb, 'denied', 'denied', 'Facebook Page',
                            'owner_approved', 'denied'
                        )
                        """,
                        (
                            f"{role}-event",
                            f"{role}-packet",
                            "a" * 64,
                            "b" * 64,
                        ),
                    )
            connection.rollback()

    def _assert_service_role_append_only(self):
        values = (
            "service-event",
            "service-packet",
            "a" * 64,
            "b" * 64,
        )
        insert = f"""
            insert into {TABLE} (
                decision_event_id, packet_id, packet_version,
                canonical_sha256, caption_sha256, exact_caption,
                ordered_media_ids_json, owner_confirmed_subject, album_story,
                channel, decision_status, owner_identity
            ) values (
                %s, %s, 'test-v1', %s, %s, 'service boundary',
                '[]'::jsonb, 'subject', 'album', 'Facebook Page',
                'owner_approved', 'owner-admin:postgres-proof'
            )
        """
        with psycopg.connect(DATABASE_URL) as connection:
            with connection.cursor() as cursor:
                cursor.execute("set local role service_role")
                cursor.execute(insert, values)
                cursor.execute("savepoint replay")
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    cursor.execute(insert, values)
                cursor.execute("rollback to savepoint replay")
                cursor.execute("savepoint conflict")
                with self.assertRaises(psycopg.errors.UniqueViolation):
                    cursor.execute(
                        insert,
                        ("different-event", values[1], values[2], values[3]),
                    )
                cursor.execute("rollback to savepoint conflict")
                cursor.execute("reset role")
                cursor.execute("savepoint update_proof")
                with self.assertRaises(psycopg.errors.RaiseException):
                    cursor.execute(
                        f"update {TABLE} set owner_notes='changed' where packet_id=%s",
                        (values[1],),
                    )
                cursor.execute("rollback to savepoint update_proof")
                cursor.execute("savepoint delete_proof")
                with self.assertRaises(psycopg.errors.RaiseException):
                    cursor.execute(
                        f"delete from {TABLE} where packet_id=%s", (values[1],)
                    )
                cursor.execute("rollback to savepoint delete_proof")
            connection.rollback()

    def _assert_application_boundary_idempotency(self):
        patches = (
            patch(
                "modules.beacon.weekly_owner_review_decisions.list_beacon_media_assets",
                return_value=({"assets": eligible_assets()}, 200),
            ),
            patch(
                "modules.beacon.weekly_owner_review_decisions.load_post_one_thumbnail",
                return_value=({"success": True}, 200),
            ),
        )
        with patches[0], patches[1]:
            approved, status = record_weekly_owner_review_decision(
                exact_payload(),
                owner_identity="owner-admin:postgres-proof",
                database_url=DATABASE_URL,
            )
            self.assertEqual(status, 201)
            replay, status = record_weekly_owner_review_decision(
                exact_payload(),
                owner_identity="owner-admin:postgres-proof",
                database_url=DATABASE_URL,
            )
            self.assertEqual(status, 200)
            self.assertTrue(replay["duplicate_withheld"])
            changed = exact_payload("reject")
            conflict, status = record_weekly_owner_review_decision(
                changed,
                owner_identity="owner-admin:postgres-proof",
                database_url=DATABASE_URL,
            )
            self.assertEqual(status, 409)
            self.assertEqual(conflict["status"], "conflicting_owner_decision_exists")
            for key in (
                "publish",
                "meta_call",
                "upload",
                "scheduled",
                "send",
                "spend",
                "business_data_mutation",
            ):
                self.assertFalse(approved[key])


if __name__ == "__main__":
    unittest.main()
