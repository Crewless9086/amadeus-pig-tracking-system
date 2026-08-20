import json
import os
import threading
import unittest
from datetime import datetime, timedelta, timezone

import psycopg

from modules.beacon.protected_publication_worker import PostgresProtectedPublicationStore
from modules.oom_sakkie.general_manager_worker import PostgresManagerCaseStore


URL = os.getenv("BEACON_GENERATION_POSTGRES_URL", "")
NOW = datetime(2026, 8, 20, 8, tzinfo=timezone.utc)


@unittest.skipUnless(URL, "BEACON_GENERATION_POSTGRES_URL not configured")
class BeaconGenerationRetirementPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL) as db, db.cursor() as cur:
            cur.execute("create schema if not exists app_private")
            cur.execute("""create table if not exists app_private.oom_manager_cases (
                case_id text primary key, dedupe_key text not null unique, specialist text not null,
                urgency text not null, status text not null, evidence_digest text not null,
                evidence_refs jsonb not null, unknowns jsonb not null, summary text not null,
                next_action text not null, next_reassessment_at timestamptz not null,
                generation bigint not null, assigned_worker_id text, lease_until timestamptz,
                last_heartbeat_at timestamptz, last_delivery_digest text, last_delivery_at timestamptz,
                created_at timestamptz default now(), updated_at timestamptz default now())""")
            cur.execute("""create table if not exists app_private.oom_manager_case_events (
                event_id text primary key, case_id text references app_private.oom_manager_cases(case_id),
                generation bigint, event_type text, event_payload jsonb, occurred_at timestamptz)""")
            cur.execute("""create table if not exists app_private.oom_protected_action_claims (
                callback_token text primary key, action_kind text not null, owner_user_id text not null,
                private_chat_id text not null, mission_id text not null, provider_message_id text not null,
                preview_card_message_id text, preview_digest text not null, evidence_generation text not null,
                preview_payload jsonb not null, status text not null, expires_at timestamptz not null,
                confirmation_provider_message_id text, confirmation_provider_timestamp timestamptz,
                result_payload jsonb, created_at timestamptz default now(), completed_at timestamptz)""")
            cur.execute("""create table if not exists app_private.beacon_protected_publication_consumers (
                consumer_id text primary key, callback_token text not null unique references
                app_private.oom_protected_action_claims(callback_token), worker_id text not null,
                status text not null, outcome_json jsonb not null default '{}'::jsonb,
                claimed_at timestamptz not null, updated_at timestamptz not null, finished_at timestamptz)""")

    def setUp(self):
        with psycopg.connect(URL) as db, db.cursor() as cur:
            cur.execute("truncate app_private.beacon_protected_publication_consumers, app_private.oom_protected_action_claims, app_private.oom_manager_case_events, app_private.oom_manager_cases cascade")
            for case_id, dedupe, generation in (("CASE-A", "beacon:a", 26), ("CASE-B", "beacon:b", 5)):
                cur.execute("""insert into app_private.oom_manager_cases
                    (case_id,dedupe_key,specialist,urgency,status,evidence_digest,evidence_refs,
                     unknowns,summary,next_action,next_reassessment_at,generation)
                    values(%s,%s,'BEACON','planned','waiting_reassessment',%s,%s::jsonb,'[]','summary','next',%s,%s)""",
                    (case_id, dedupe, str(generation)[-1] * 64,
                     json.dumps(["beacon_result:" + str(generation)[-1] * 64]), NOW, generation))

    def _claim(self, token, case_id, generation, status="completed", consumed=False):
        result = {"status": "beacon_campaign_review_approved"}
        with psycopg.connect(URL) as db, db.cursor() as cur:
            cur.execute("""insert into app_private.oom_protected_action_claims
                (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,
                 provider_message_id,preview_digest,evidence_generation,preview_payload,status,
                 expires_at,result_payload,completed_at)
                values(%s,'beacon_campaign_review','42','42',%s,%s,%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s)""",
                (token, token, f"scheduled:{case_id}:G{generation}", token * 8,
                 token * 8, json.dumps({"packet_generation": f"G{generation}"}), status,
                 NOW + timedelta(days=1), json.dumps(result), NOW))
            if consumed:
                cur.execute("""insert into app_private.beacon_protected_publication_consumers
                    (consumer_id,callback_token,worker_id,status,claimed_at,updated_at)
                    values(%s,%s,'worker','contained',%s,%s)""", ("CONSUMER-" + token, token, NOW, NOW))

    def test_retirement_is_case_scoped_and_preserves_consumed_history(self):
        self._claim("A24", "CASE-A", 24)
        self._claim("A26", "CASE-A", 26, status="active")
        self._claim("B5X", "CASE-B", 5, status="active")
        self._claim("A23", "CASE-A", 23, consumed=True)
        with psycopg.connect(URL) as db, db.cursor() as cur:
            PostgresManagerCaseStore._retire_stale_beacon_claims(cur, "beacon:a", NOW)
        with psycopg.connect(URL) as db, db.cursor() as cur:
            cur.execute("select callback_token,status,result_payload from app_private.oom_protected_action_claims order by callback_token")
            rows = {row[0]: (row[1], row[2]) for row in cur.fetchall()}
        self.assertEqual(rows["A24"][0], "changed")
        self.assertEqual(rows["A24"][1]["status"], "beacon_campaign_claim_superseded_by_current_manager_generation")
        self.assertEqual(rows["A26"][0], "active")
        self.assertEqual(rows["B5X"][0], "active")
        self.assertEqual(rows["A23"][0], "completed")

    def test_manager_generation_lock_serializes_before_publication_claim(self):
        self._claim("A24", "CASE-A", 24)
        started = threading.Event()
        result = []
        manager = psycopg.connect(URL)
        try:
            with manager.cursor() as cur:
                cur.execute("select generation from app_private.oom_manager_cases where case_id='CASE-A' for update")
                cur.execute("update app_private.oom_manager_cases set generation=27 where case_id='CASE-A'")
                started.set()
                worker = threading.Thread(target=lambda: result.append(
                    PostgresProtectedPublicationStore(URL).claim("worker", NOW)))
                worker.start()
                self.assertTrue(started.is_set())
                PostgresManagerCaseStore._retire_stale_beacon_claims(cur, "beacon:a", NOW)
            manager.commit()
            worker.join(5)
            self.assertFalse(worker.is_alive())
        finally:
            manager.close()
        self.assertEqual(result, [None])
        with psycopg.connect(URL) as db, db.cursor() as cur:
            cur.execute("select status from app_private.oom_protected_action_claims where callback_token='A24'")
            self.assertEqual(cur.fetchone()[0], "changed")

    def test_claimed_publication_is_point_of_no_return_before_generation_advance(self):
        self._claim("A26", "CASE-A", 26)
        store = PostgresProtectedPublicationStore(URL)
        claimed = store.claim("worker", NOW)
        self.assertIsNotNone(claimed)
        candidate = {"case_id": "CASE-A", "dedupe_key": "beacon:a",
            "specialist": "BEACON", "urgency": "planned", "evidence_digest": "e" * 64,
            "evidence_refs": ["beacon_result:" + "e" * 64], "unknowns": [],
            "summary": "new media exception", "next_action": "wait for exact media",
            "next_reassessment_at": NOW.isoformat()}
        manager_store = PostgresManagerCaseStore()
        with psycopg.connect(URL) as db, db.cursor() as cur:
            self.assertEqual(manager_store._reconcile(cur, candidate, NOW), "deferred")
        with psycopg.connect(URL) as db, db.cursor() as cur:
            cur.execute("select generation,evidence_digest from app_private.oom_manager_cases where case_id='CASE-A'")
            self.assertEqual(cur.fetchone(), (26, "6" * 64))
        self.assertTrue(store.finish(claimed["consumer_id"], "confirmed",
            {"status": "provider_confirmed"}, NOW))
        with psycopg.connect(URL) as db, db.cursor() as cur:
            self.assertEqual(manager_store._reconcile(cur, candidate, NOW), "changed")
        with psycopg.connect(URL) as db, db.cursor() as cur:
            cur.execute("select generation,evidence_digest from app_private.oom_manager_cases where case_id='CASE-A'")
            self.assertEqual(cur.fetchone(), (27, "e" * 64))


if __name__ == "__main__":
    unittest.main()
