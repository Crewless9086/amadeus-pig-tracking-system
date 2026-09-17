import copy
import os
import unittest
import uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

import psycopg

from modules.pig_weights.herdmaster_piglet_observation_action import (
    action_digest, execute_action, normalize_application, _confirmation_binding,
)


class PigletObservationActionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url: raise unittest.SkipTest("disposable PostgreSQL URL required")
        os.environ["OWNER_SESSION_SECRET"] = "postgres-observation-confirmation-secret"
        with psycopg.connect(cls.url) as connection:
            if connection.execute("select to_regclass('public.pig_observation_events')").fetchone()[0] is None:
                connection.execute(Path("supabase/migrations/202607200001_create_pig_observation_events.sql").read_text(encoding="utf-8"))

    def setUp(self):
        suffix = uuid.uuid4().hex[:10]
        self.litter = "LIT-OBS-" + suffix
        self.pigs = ["PIG-OBS-" + suffix + "-1", "PIG-OBS-" + suffix + "-2"]
        with psycopg.connect(self.url) as connection:
            connection.execute("insert into public.litters(litter_id,farrowing_date,born_alive,litter_status) values(%s,'2026-08-01',2,'Active')", (self.litter,))
            for pig in self.pigs:
                connection.execute("insert into public.pigs(pig_id,status,on_farm,animal_type,sex,litter_id) values(%s,'Active',true,'Piglet','Female',%s)", (pig, self.litter))

    def payload(self, key="batch-1"):
        return {"litter_id": self.litter, "observed_on": "2026-08-11",
                "source_context": "historical_weaning", "source_reference": "paper-note",
                "idempotency_key": key, "observations": [
                    {"pig_id": self.pigs[0], "traits": ["good_build"], "sentiment": "positive", "factual_note": "Good build."},
                    {"pig_id": self.pigs[1], "traits": ["concern"], "sentiment": "concerning", "factual_note": "Weak hind leg."}]}

    def execute(self, payload, actor="owner-a"):
        action, errors = normalize_application(payload); self.assertFalse(errors)
        return execute_action(payload, actor_id=actor,
            confirmation_binding=_confirmation_binding(action_digest(action), actor),
            channel="application", connect_factory=lambda _url: psycopg.connect(self.url))

    def count(self):
        with psycopg.connect(self.url) as connection:
            return connection.execute("select count(*) from public.pig_observation_events where pig_id=any(%s)", (self.pigs,)).fetchone()[0]

    def test_execute_replay_correction_and_immutable_original(self):
        first, status = self.execute(self.payload())
        self.assertEqual((status, first["rows_created"], self.count()), (201, 2, 2))
        replay, status = self.execute(self.payload())
        self.assertEqual((status, replay["rows_created"], self.count()), (200, 0, 2))
        correction = self.payload("correction-1")
        correction["observations"] = [{"pig_id": self.pigs[0], "traits": ["good_build"],
            "sentiment": "positive", "factual_note": "Correction: legs were not assessed.",
            "supersedes_observation_event_id": first["canonical_readback"][0]["observation_event_id"]}]
        corrected, status = self.execute(correction)
        self.assertEqual((status, self.count()), (201, 3))
        with psycopg.connect(self.url) as connection:
            original = connection.execute("select factual_note from public.pig_observation_events where observation_event_id=%s", (first["canonical_readback"][0]["observation_event_id"],)).fetchone()
        self.assertEqual(original[0], "Good build.")

    def test_partial_group_and_late_failure_rollback_every_observation(self):
        invalid = self.payload(); invalid["observations"][1]["pig_id"] = "UNKNOWN-PIG"
        result, status = self.execute(invalid)
        self.assertEqual((status, self.count()), (409, 0))
        conflict = self.payload("late-conflict")
        with psycopg.connect(self.url) as connection:
            connection.execute("insert into public.pig_observation_events(observation_event_id,pig_id,observed_at,observer_reference,observation_category,factual_note,source_system,source_reference,idempotency_key) values(%s,%s,'2026-08-11','owner-a','other','conflict','owner','{}',%s)", ("OBS-CONFLICT-"+uuid.uuid4().hex, self.pigs[1], "late-conflict:"+self.pigs[1]+":1"))
        result, status = self.execute(conflict)
        self.assertEqual(status, 409)
        self.assertEqual(self.count(), 1)

    def test_concurrent_exact_replay_has_one_writer(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.execute(self.payload("concurrent")), range(2)))
        self.assertEqual(self.count(), 2)
        self.assertEqual(sorted(result[0].get("rows_created", -1) for result in results), [0, 2], results)
        self.assertTrue({result[1] for result in results}.issubset({201, 200, 409}))


if __name__ == "__main__": unittest.main()
