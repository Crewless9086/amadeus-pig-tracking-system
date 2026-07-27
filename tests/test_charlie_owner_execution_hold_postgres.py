import hashlib
import json
import os
import threading
import unittest
import uuid
from pathlib import Path

import psycopg

from modules.charlie.mission_store import (
    create_owner_execution_hold,
    list_owner_work_missions,
    owner_execution_hold_status,
    release_owner_execution_hold,
    update_mission_status,
    update_mission_vault,
)


GENERATION = "5e815d4b99d47899a93f01cf"
REPLACEMENT_FIXTURE = "CHARLIE-REPLACEMENT-AF110E2A071BC18CCAA00DF2"


class CharlieOwnerExecutionHoldPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("DATABASE_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest("DATABASE_URL not configured for disposable PostgreSQL hold tests")
        migration = Path("supabase/migrations/202607270003_create_charlie_owner_execution_holds.sql")
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("create schema if not exists app_private")
                cursor.execute(
                    """create table if not exists app_private.migration_log (
                           migration_id text primary key, description text, applied_at timestamptz default now()
                       )"""
                )
                cursor.execute(migration.read_text(encoding="utf-8"))

    def setUp(self):
        self.mission_id = f"{REPLACEMENT_FIXTURE}-FIXTURE-{uuid.uuid4().hex[:8].upper()}"
        self.metadata = {
            "orchestration": {"generation_identity": GENERATION},
            "orchestration_binding": {"validated": True, "generation_identity": GENERATION},
            "agent_workflow": [{"agent": "source_mapper", "status": "active", "authority": "read_only"}],
            "intake_quality": {"queue_class": "owner_work"},
        }
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.charlie_missions
                       (mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json)
                       values (%s,'approved','test','fixture','fixture','P2','read-only audit','LEVEL 1',%s::jsonb)""",
                    (self.mission_id, json.dumps(self.metadata)),
                )

    def _mission_hash(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select to_jsonb(m) from public.charlie_missions m where mission_id=%s", (self.mission_id,))
                return hashlib.sha256(json.dumps(cursor.fetchone()[0], sort_keys=True, default=str).encode()).hexdigest()

    def test_hold_is_append_only_replay_safe_and_release_restores_eligibility(self):
        before = self._mission_hash()
        created, status = create_owner_execution_hold(
            self.mission_id, GENERATION, "owner_hold_for_zero_runnable_observe_only_handshake",
            owner_principal="owner:test", database_url=self.database_url,
        )
        self.assertEqual((status, created["status"]), (201, "owner_execution_hold_created"))
        self.assertEqual(before, self._mission_hash())

        replay, replay_status = create_owner_execution_hold(
            self.mission_id, GENERATION, "owner_hold_for_zero_runnable_observe_only_handshake",
            owner_principal="owner:test", database_url=self.database_url,
        )
        self.assertEqual((replay_status, replay["status"]), (200, "owner_execution_hold_replayed"))

        listed, listed_status = list_owner_work_missions("approved", limit=100, database_url=self.database_url)
        self.assertEqual(listed_status, 200)
        self.assertNotIn(self.mission_id, [row["mission_id"] for row in listed["missions"]])

        transition, transition_status = update_mission_status(
            self.mission_id, "in_progress", expected_status="approved", database_url=self.database_url,
        )
        self.assertEqual((transition_status, transition["status"]), (423, "owner_execution_hold_active"))
        lease, lease_status = update_mission_vault(
            self.mission_id, {"execution_lease": {"status": "active"}},
            expected_status="approved", database_url=self.database_url,
        )
        self.assertEqual((lease_status, lease["status"]), (423, "owner_execution_hold_active"))
        metadata_update, metadata_status = update_mission_vault(
            self.mission_id, {"orchestration": {"generation_identity": "changed"}},
            expected_status="approved", database_url=self.database_url,
        )
        self.assertEqual(metadata_status, 423)
        self.assertEqual(metadata_update["status"], "owner_execution_hold_active")
        other_transition, other_status = update_mission_status(
            self.mission_id, "paused", expected_status="approved",
            database_url=self.database_url,
        )
        self.assertEqual(other_status, 423)
        self.assertEqual(other_transition["status"], "owner_execution_hold_active")

        conflict, conflict_status = create_owner_execution_hold(
            self.mission_id, GENERATION, "different_reason",
            owner_principal="owner:test", database_url=self.database_url,
        )
        self.assertEqual((conflict_status, conflict["status"]), (409, "owner_execution_hold_conflict"))
        stale, stale_status = create_owner_execution_hold(
            self.mission_id, "stale-generation", "reason",
            owner_principal="owner:test", database_url=self.database_url,
        )
        self.assertEqual((stale_status, stale["status"]), (409, "owner_execution_hold_stale_generation"))

        released, released_status = release_owner_execution_hold(
            self.mission_id, GENERATION, created["hold"]["hold_id"], "handshake_complete",
            owner_principal="owner:test", database_url=self.database_url,
        )
        self.assertEqual((released_status, released["status"]), (201, "owner_execution_hold_released"))
        release_replay, release_replay_status = release_owner_execution_hold(
            self.mission_id, GENERATION, created["hold"]["hold_id"], "handshake_complete",
            owner_principal="owner:test", database_url=self.database_url,
        )
        self.assertEqual((release_replay_status, release_replay["status"]), (200, "owner_execution_hold_release_replayed"))
        hold, hold_status = owner_execution_hold_status(self.mission_id, database_url=self.database_url)
        self.assertEqual((hold_status, hold["active"]), (200, False))
        self.assertEqual(before, self._mission_hash())
        with self.assertRaises(psycopg.Error):
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "update public.charlie_owner_execution_hold_events set reason='changed' where event_id=%s",
                        (created["hold"]["event_id"],),
                    )

    def test_database_rejects_forged_release_provenance(self):
        created, status = create_owner_execution_hold(
            self.mission_id, GENERATION, "forged_release_test",
            owner_principal="owner:test", database_url=self.database_url,
        )
        self.assertEqual(status, 201)
        with self.assertRaises(psycopg.Error):
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """insert into public.charlie_owner_execution_hold_events
                           (event_id,hold_id,mission_id,generation_identity,event_type,reason,
                            owner_identity_hash,authorization_identity,release_of_event_id)
                           values ('FORGED-RELEASE','WRONG-HOLD',%s,%s,'hold_released','forged',
                                   %s,%s,%s)""",
                        (
                            self.mission_id, GENERATION, "a" * 64, "b" * 64,
                            created["hold"]["event_id"],
                        ),
                    )

    def test_concurrent_hold_and_pickup_has_one_fail_closed_winner(self):
        barrier = threading.Barrier(2)
        results = []

        def hold():
            barrier.wait()
            results.append(("hold",) + create_owner_execution_hold(
                self.mission_id, GENERATION, "concurrent_owner_hold",
                owner_principal="owner:test", database_url=self.database_url,
            )[::-1])

        def pickup():
            barrier.wait()
            results.append(("pickup",) + update_mission_status(
                self.mission_id, "in_progress", expected_status="approved", database_url=self.database_url,
            )[::-1])

        first = threading.Thread(target=hold)
        second = threading.Thread(target=pickup)
        first.start()
        second.start()
        first.join()
        second.join()
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute("select status from public.charlie_missions where mission_id=%s", (self.mission_id,))
                status = cursor.fetchone()[0]
                cursor.execute(
                    "select count(*) from public.charlie_owner_execution_hold_events where mission_id=%s and event_type='hold_created'",
                    (self.mission_id,),
                )
                holds = cursor.fetchone()[0]
        self.assertIn((status, holds), {("approved", 1), ("in_progress", 0)})

    def test_terminal_and_nonapproved_missions_cannot_receive_hold(self):
        for status in ("paused", "rejected", "done"):
            mission_id = f"{self.mission_id}-{status}"
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """insert into public.charlie_missions
                           (mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json)
                           values (%s,%s,'test','fixture','fixture','P2','audit','LEVEL 1',%s::jsonb)""",
                        (mission_id, status, json.dumps(self.metadata)),
                    )
            result, code = create_owner_execution_hold(
                mission_id, GENERATION, "not_allowed", owner_principal="owner:test",
                database_url=self.database_url,
            )
            self.assertEqual((code, result["status"]), (409, "owner_execution_hold_status_conflict"))

        superseded_id = f"{self.mission_id}-superseded"
        superseded_metadata = {
            **self.metadata,
            "portfolio_disposition": {"status": "superseded", "history_preserved": True},
        }
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """insert into public.charlie_missions
                       (mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json)
                       values (%s,'approved','test','fixture','fixture','P2','audit','LEVEL 1',%s::jsonb)""",
                    (superseded_id, json.dumps(superseded_metadata)),
                )
        result, code = create_owner_execution_hold(
            superseded_id, GENERATION, "not_allowed", owner_principal="owner:test",
            database_url=self.database_url,
        )
        self.assertEqual((code, result["status"]), (409, "owner_execution_hold_mission_superseded"))


if __name__ == "__main__":
    unittest.main()
