import os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import unittest

import psycopg

from modules.beacon.media_intake import IntakeStore


DATABASE_URL = os.getenv("BEACON_WEEKLY_REVIEW_POSTGRES_URL", "").strip()
MIGRATION = Path(
    "supabase/migrations/202607270001_create_beacon_media_intake.sql"
)


@unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL is required")
class BeaconMediaIntakePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = Path(
            "supabase/migrations/202606180002_create_beacon_media_library.sql"
        ).read_text(encoding="utf-8")
        creative = Path(
            "supabase/migrations/202607130002_create_beacon_creative_studio.sql"
        ).read_text(encoding="utf-8")
        migration = MIGRATION.read_text(encoding="utf-8")
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(base)
            cursor.execute(creative)
            for table in (
                "beacon_media_library_events",
                "beacon_media_understanding_events",
                "beacon_media_intake_events",
                "beacon_media_source_links",
                "beacon_media_binaries",
                "beacon_media_intake_album_members",
                "beacon_media_intake_items",
                "beacon_media_intake_groups",
            ):
                cursor.execute(f"drop table if exists public.{table} cascade")
            cursor.execute("drop function if exists public.prevent_beacon_media_intake_mutation() cascade")
            cursor.execute(migration)

    def setUp(self):
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                """truncate table
                   public.beacon_media_library_events,
                   public.beacon_media_understanding_events,
                   public.beacon_media_intake_events,
                   public.beacon_media_source_links,
                   public.beacon_media_intake_album_members,
                   public.beacon_media_binaries,
                   public.beacon_media_intake_items,
                   public.beacon_media_intake_groups,
                   public.beacon_media_asset_events,
                   public.beacon_media_assets
                   cascade"""
            )

    def envelope(self, **changes):
        result = {
            "update_id": 100,
            "message_id": 200,
            "media_group_id": "",
            "owner_explanation": "Owner context",
            "source_message_at": "2026-07-27T09:00:00+00:00",
            "capture_time": None,
            "capture_time_state": "unknown",
            "file_id": "telegram-file",
            "file_unique_id": "telegram-unique",
            "original_filename": "one.jpg",
            "declared_mime_type": "image/jpeg",
            "media_kind": "photo",
        }
        result.update(changes)
        return result

    def identity(self, **changes):
        result = {
            "group_id": "BEACON-INTAKE-GROUP-POSTGRES",
            "item_id": "BEACON-INTAKE-ITEM-POSTGRES",
            "source_sha256": "a" * 64,
            "chat_hmac": "b" * 64,
            "owner_principal": "telegram-owner:" + "c" * 64,
        }
        result.update(changes)
        return result

    def test_replay_conflict_append_only_and_client_privileges(self):
        store = IntakeStore(DATABASE_URL)
        first, first_status = store.prepare(self.envelope(), self.identity())
        replay, replay_status = store.prepare(self.envelope(), self.identity())
        conflict, conflict_status = store.prepare(
            self.envelope(file_id="substituted"),
            self.identity(),
        )
        self.assertEqual((first_status, first["status"]), (201, "media_intake_pending_created"))
        self.assertEqual((replay_status, replay["status"]), (200, "exact_intake_replay_withheld"))
        self.assertEqual((conflict_status, conflict["status"]), (409, "intake_identity_conflict"))

        tables = (
            "beacon_media_intake_groups", "beacon_media_intake_items",
            "beacon_media_intake_album_members", "beacon_media_binaries",
            "beacon_media_source_links", "beacon_media_intake_events",
            "beacon_media_understanding_events", "beacon_media_library_events",
        )
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            for table in tables:
                qualified = f"public.{table}"
                for role in ("anon", "authenticated"):
                    for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE"):
                        cursor.execute(
                            "select has_table_privilege(%s,%s,%s)",
                            (role, qualified, privilege),
                        )
                        self.assertFalse(cursor.fetchone()[0], (role, table, privilege))
                cursor.execute(
                    """select count(*) from information_schema.table_privileges
                       where grantee='PUBLIC' and table_schema='public' and table_name=%s""",
                    (table,),
                )
                self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute(
                    """select count(*) from pg_trigger
                       where tgrelid=%s::regclass and not tgisinternal""",
                    (qualified,),
                )
                self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute("savepoint update_block")
            with self.assertRaises(psycopg.errors.RaiseException):
                cursor.execute(
                    """update public.beacon_media_intake_groups
                       set intake_group_id=intake_group_id"""
                )
            cursor.execute("rollback to savepoint update_block")
            cursor.execute("savepoint delete_block")
            with self.assertRaises(psycopg.errors.RaiseException):
                cursor.execute("delete from public.beacon_media_intake_groups")
            cursor.execute("rollback to savepoint delete_block")
            cursor.execute(
                """select count(*) from information_schema.routine_privileges
                   where grantee='PUBLIC' and routine_schema='public'
                     and routine_name='prevent_beacon_media_intake_mutation'"""
            )
            self.assertEqual(cursor.fetchone()[0], 0)
            for role in ("anon", "authenticated", "service_role"):
                cursor.execute(
                    "select has_function_privilege(%s,%s,'EXECUTE')",
                    (role, "public.prevent_beacon_media_intake_mutation()"),
                )
                self.assertFalse(cursor.fetchone()[0], role)
            connection.rollback()

    def test_identical_bytes_keep_two_sources_and_one_binary(self):
        store = IntakeStore(DATABASE_URL)
        prepared_first, prepared_first_status = store.prepare(
            self.envelope(), self.identity()
        )
        self.assertIn(prepared_first_status, (200, 201))
        self.assertIn(
            prepared_first["status"],
            {"media_intake_pending_created", "exact_intake_replay_withheld"},
        )
        second_identity = self.identity(
            item_id="BEACON-INTAKE-ITEM-POSTGRES-2",
            source_sha256="d" * 64,
            group_id="BEACON-INTAKE-GROUP-POSTGRES-2",
        )
        second_envelope = self.envelope(
            update_id=101,
            message_id=201,
            file_id="telegram-file-2",
            file_unique_id="telegram-unique-2",
            original_filename="another-name.jpg",
        )
        prepared, status = store.prepare(second_envelope, second_identity)
        self.assertEqual(status, 201)
        media = {
            "binary_asset_id": "BEACON-BINARY-POSTGRES",
            "content_sha256": "e" * 64,
            "observed_mime_type": "image/jpeg",
            "byte_size": 100,
            "width": 10,
            "height": 10,
            "storage_path": "telegram/ee/" + "e" * 64 + ".jpg",
            "thumbnail_storage_path": "telegram-thumbnails/ee/" + "e" * 64 + ".jpg",
            "thumbnail_sha256": "f" * 64,
        }
        first_final, first_status = store.finalize(self.envelope(), self.identity(), media)
        second_final, second_status = store.finalize(second_envelope, second_identity, media)
        self.assertEqual(
            (first_status, second_status),
            (201, 201),
            (first_final, second_final),
        )
        self.assertFalse(first_final["exact_duplicate"])
        self.assertTrue(second_final["exact_duplicate"])
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                "select count(*) from public.beacon_media_binaries where content_sha256=%s",
                ("e" * 64,),
            )
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute(
                """select count(*) from public.beacon_media_source_links
                   where binary_asset_id='BEACON-BINARY-POSTGRES'"""
            )
            self.assertEqual(cursor.fetchone()[0], 2)

    def test_album_is_ordered_by_message_only_after_explicit_complete(self):
        store = IntakeStore(DATABASE_URL)
        group_id = "BEACON-INTAKE-GROUP-ALBUM"
        media_group = "telegram-album"
        items = []
        for number, message_id in enumerate((302, 300, 301), 1):
            envelope = self.envelope(
                update_id=400 + number,
                message_id=message_id,
                media_group_id=media_group,
                file_id=f"album-file-{number}",
                file_unique_id=f"album-unique-{number}",
                original_filename=f"{number}.jpg",
            )
            identity = self.identity(
                group_id=group_id,
                item_id=f"BEACON-INTAKE-ALBUM-ITEM-{number}",
                source_sha256=f"{number}" * 64,
            )
            prepared, prepared_status = store.prepare(envelope, identity)
            self.assertEqual(prepared_status, 201, prepared)
            media = {
                "binary_asset_id": f"BEACON-BINARY-ALBUM-{number}",
                "content_sha256": f"{number + 3}" * 64,
                "observed_mime_type": "image/jpeg",
                "byte_size": 100,
                "width": 10,
                "height": 10,
                "storage_path": f"telegram/album/{number}.jpg",
                "thumbnail_storage_path": f"telegram-thumbnails/album/{number}.jpg",
                "thumbnail_sha256": f"{number + 6}" * 64,
            }
            finalized, finalized_status = store.finalize(envelope, identity, media)
            self.assertEqual(finalized_status, 201, finalized)
            items.append((message_id, identity["item_id"]))

        premature, premature_status = store.review_group(
            group_id,
            {
                "event_type": "library_accepted",
                "owner_action_id": "premature-album-review",
                "expected_predecessors": {},
            },
            "owner-admin:one",
        )
        self.assertEqual(
            (premature_status, premature["status"]),
            (409, "media_group_completion_required_before_review"),
        )
        complete, complete_status = store.complete_album({
            "group_id": group_id,
            "chat_hmac": "b" * 64,
            "owner_principal": "telegram-owner:" + "c" * 64,
        })
        self.assertEqual(complete_status, 201)
        self.assertEqual(
            complete["ordered_intake_item_ids"],
            [item_id for _, item_id in sorted(items)],
        )
        replay, replay_status = store.complete_album({
            "group_id": group_id,
            "chat_hmac": "b" * 64,
            "owner_principal": "telegram-owner:" + "c" * 64,
        })
        self.assertEqual((replay_status, replay["created_count"]), (200, 0))

    def test_partial_album_cannot_be_completed(self):
        store = IntakeStore(DATABASE_URL)
        envelope = self.envelope(media_group_id="partial-album")
        identity = self.identity(group_id="BEACON-INTAKE-GROUP-PARTIAL")
        prepared, status = store.prepare(envelope, identity)
        self.assertEqual(status, 201, prepared)
        completed, complete_status = store.complete_album(identity)
        self.assertEqual(
            (complete_status, completed["status"]),
            (409, "album_has_no_durable_items"),
        )

    def test_library_and_public_use_decisions_are_separate_and_replay_safe(self):
        store = IntakeStore(DATABASE_URL)
        envelope, identity = self.envelope(), self.identity()
        store.prepare(envelope, identity)
        media = {
            "binary_asset_id": "BEACON-BINARY-REVIEW",
            "content_sha256": "9" * 64,
            "observed_mime_type": "image/jpeg",
            "byte_size": 100,
            "width": 10,
            "height": 10,
            "storage_path": "telegram/review/one.jpg",
            "thumbnail_storage_path": "telegram-thumbnails/review/one.jpg",
            "thumbnail_sha256": "8" * 64,
        }
        finalized, status = store.finalize(envelope, identity, media)
        self.assertEqual(status, 201, finalized)
        binary_id = finalized["binary_asset_id"]
        public_first, public_first_status = store.review(
            binary_id, {
                "event_type": "public_use_approved",
                "owner_action_id": "public-before-library",
                "expected_predecessor_event_id": "",
            }, "owner-admin:one"
        )
        self.assertEqual(
            (public_first_status, public_first["status"]),
            (409, "library_accept_required_before_public_use"),
        )
        accepted, accepted_status = store.review(
            binary_id, {
                "event_type": "library_accepted",
                "owner_action_id": "accept-1",
                "expected_predecessor_event_id": "",
            }, "owner-admin:one"
        )
        replay, replay_status = store.review(
            binary_id, {
                "event_type": "library_accepted",
                "owner_action_id": "accept-1",
                "expected_predecessor_event_id": "",
            }, "owner-admin:one"
        )
        corrected_context, corrected_context_status = store.review(
            binary_id,
            {
                "event_type": "library_accepted",
                "notes": "substituted",
                "owner_action_id": "accept-context-2",
                "expected_predecessor_event_id": accepted["library_event_id"],
            },
            "owner-admin:one",
        )
        approved, approved_status = store.review(
            binary_id, {
                "event_type": "public_use_approved",
                "owner_action_id": "public-1",
                "expected_predecessor_event_id": corrected_context["library_event_id"],
            }, "owner-admin:one"
        )
        self.assertEqual((accepted_status, accepted["created_count"]), (201, 1))
        self.assertEqual((replay_status, replay["created_count"]), (200, 0))
        self.assertEqual((corrected_context_status, corrected_context["created_count"]), (201, 1))
        self.assertEqual(approved_status, 201, approved)
        self.assertEqual(approved["created_count"], 1)
        self.assertFalse(approved["publish"])
        revoked, revoked_status = store.review(
            binary_id, {
                "event_type": "public_use_revoked",
                "owner_action_id": "revoke-1",
                "expected_predecessor_event_id": approved["library_event_id"],
            }, "owner-admin:one"
        )
        delayed_replay, delayed_replay_status = store.review(
            binary_id, {
                "event_type": "public_use_approved",
                "owner_action_id": "public-1",
                "expected_predecessor_event_id": corrected_context["library_event_id"],
            }, "owner-admin:one"
        )
        self.assertEqual(
            (delayed_replay_status, delayed_replay["created_count"]),
            (200, 0),
        )
        reapproved, reapproved_status = store.review(
            binary_id, {
                "event_type": "public_use_approved",
                "owner_action_id": "public-2",
                "expected_predecessor_event_id": revoked["library_event_id"],
            }, "owner-admin:one"
        )
        self.assertEqual((revoked_status, revoked["created_count"]), (201, 1))
        self.assertEqual((reapproved_status, reapproved["created_count"]), (201, 1))
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                """select event_type from public.beacon_media_asset_events
                   where asset_id=%s
                     and event_type in ('approved_public_use','rejected_public_use')
                   order by created_at,event_id""",
                (finalized["beacon_asset_id"],),
            )
            canonical = [row[0] for row in cursor.fetchall()]
        self.assertEqual(
            canonical,
            ["approved_public_use", "rejected_public_use", "approved_public_use"],
        )

    def test_concurrent_decisions_cannot_create_sibling_transitions(self):
        store = IntakeStore(DATABASE_URL)
        envelope, identity = self.envelope(), self.identity()
        store.prepare(envelope, identity)
        finalized, status = store.finalize(envelope, identity, {
            "binary_asset_id": "BEACON-BINARY-CONCURRENT",
            "content_sha256": "7" * 64,
            "observed_mime_type": "image/jpeg",
            "byte_size": 100,
            "width": 10,
            "height": 10,
            "storage_path": "telegram/concurrent/one.jpg",
            "thumbnail_storage_path": "telegram-thumbnails/concurrent/one.jpg",
            "thumbnail_sha256": "6" * 64,
        })
        self.assertEqual(status, 201, finalized)

        def decide(action_id):
            return IntakeStore(DATABASE_URL).review(
                finalized["binary_asset_id"],
                {
                    "event_type": "library_accepted",
                    "owner_action_id": action_id,
                    "expected_predecessor_event_id": "",
                },
                "owner-admin:concurrent",
            )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(decide, ("race-one", "race-two")))
        statuses = sorted(status for _result, status in results)
        self.assertEqual(statuses, [201, 409], results)
        rejected = [result for result, status in results if status == 409][0]
        self.assertEqual(rejected["status"], "media_review_predecessor_changed")
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute(
                """select count(*) from public.beacon_media_library_events
                   where binary_asset_id=%s""",
                (finalized["binary_asset_id"],),
            )
            self.assertEqual(cursor.fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
