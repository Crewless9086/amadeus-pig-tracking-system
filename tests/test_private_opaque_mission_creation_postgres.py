import os
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg

from modules.charlie.mission_store import record_mission


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
PREFIX = "CMQ-OPAQUE-POSTGRES-"


@unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL is required")
class PrivateOpaqueMissionCreationPostgresTests(unittest.TestCase):
    def setUp(self):
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("delete from public.charlie_mission_events where mission_id like %s", (PREFIX + "%",))
            cursor.execute("delete from public.charlie_missions where mission_id like %s", (PREFIX + "%",))

    def _mission(self, mission_id, title):
        return {"mission_id": mission_id, "title": title, "raw_text": title,
            "urgency": "P2", "mission_type": "system improvement",
            "approval_level": "LEVEL 3", "metadata": {
                "created_from": "charlie_private_executive",
                "owner_work": True,
                "opaque_identity_owner_approved": True,
            }}

    def _record(self, mission_id, title):
        return record_mission(self._mission(mission_id, title),
            source_context={"source": "charlie_private_executive"},
            database_url=DATABASE_URL, exact_identity=True)

    def _counts(self):
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("select count(*) from public.charlie_missions where mission_id like %s", (PREFIX + "%",))
            missions = cursor.fetchone()[0]
            cursor.execute("select count(*) from public.charlie_mission_events where mission_id like %s", (PREFIX + "%",))
            events = cursor.fetchone()[0]
        return missions, events

    def test_exact_replay_is_one_mission_and_one_creation_event(self):
        mission_id = PREFIX + "CMQ-20260813-05"
        title = "Opaque exact replay acceptance"
        first, first_status = self._record(mission_id, title)
        replay, replay_status = self._record(mission_id, title)
        self.assertEqual((first_status, replay_status), (201, 200))
        self.assertEqual(first["mission_id"], mission_id)
        self.assertEqual(replay["mission_id"], mission_id)
        self.assertEqual(replay["status"], "duplicate_exact_mission")
        self.assertEqual(self._counts(), (1, 1))

    def test_title_collision_cannot_touch_or_replace_other_identity(self):
        first_id, second_id = PREFIX + "TITLE-A", PREFIX + "TITLE-B"
        title = "One owner approved opaque title"
        first, first_status = self._record(first_id, title)
        conflict, conflict_status = self._record(second_id, title)
        self.assertEqual(first_status, 201)
        self.assertEqual(conflict_status, 409)
        self.assertEqual(conflict["status"], "exact_mission_title_conflict")
        self.assertEqual(conflict["conflicting_mission_id"], first_id)
        self.assertEqual(self._counts(), (1, 1))

    def test_concurrent_exact_replay_converges_on_one_identity(self):
        mission_id = PREFIX + "CONCURRENT-SAME"
        title = "Concurrent same opaque identity"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self._record(mission_id, title), range(2)))
        self.assertEqual(sorted(status for _result, status in results), [200, 201])
        self.assertEqual({result["mission_id"] for result, _status in results}, {mission_id})
        self.assertEqual(self._counts(), (1, 1))

    def test_concurrent_competing_ids_with_same_title_create_only_one(self):
        title = "Concurrent title identity collision"
        mission_ids = [PREFIX + "CONCURRENT-A", PREFIX + "CONCURRENT-B"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda mission_id: self._record(mission_id, title), mission_ids))
        self.assertEqual(sorted(status for _result, status in results), [201, 409])
        self.assertEqual(self._counts(), (1, 1))


if __name__ == "__main__":
    unittest.main()
