"""Disposable-PostgreSQL proof for atomic grouped breeding exposures."""
import os
import copy
import unittest
import uuid

import psycopg

from modules.pig_weights.herdmaster_breeding_exposure_recovery import (
    build_grouped_preview,
    execute_grouped_preview,
)


URL = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()


@unittest.skipUnless(URL, "disposable PostgreSQL URL is required")
class BreedingExposurePostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with psycopg.connect(URL) as db:
            db.execute(
                "create or replace view public.current_canonical_pig_state "
                "as select * from public.pig_current_state"
            )

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(URL) as db:
            db.execute("drop view if exists public.current_canonical_pig_state")

    def connect(self):
        return psycopg.connect(URL)

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:12]
        self.sows = [f"SOW-{self.suffix}-{number}" for number in range(1, 6)]
        self.boars = [f"BOAR-{self.suffix}-{number}" for number in range(1, 4)]
        with self.connect() as db, db.cursor() as cur:
            cur.executemany(
                "insert into public.pigs(pig_id,pig_name,status,on_farm,sex) "
                "values(%s,%s,'Active',true,'Female')",
                [(pig_id, pig_id) for pig_id in self.sows],
            )
            cur.executemany(
                "insert into public.pigs(pig_id,pig_name,status,on_farm,sex) "
                "values(%s,%s,'Active',true,'Male')",
                [(pig_id, pig_id) for pig_id in self.boars],
            )

    def preview(self):
        assignments = [
            (self.sows[0], self.boars[0]),
            (self.sows[1], self.boars[1]),
            (self.sows[2], self.boars[1]),
            (self.sows[3], self.boars[1]),
            (self.sows[4], self.boars[2]),
        ]
        return build_grouped_preview(
            {"rows": [
                {"pig_id": sow, "label": sow, "action": "exposure",
                 "boar_pig_id": boar, "exposure_started_on": "2026-08-12",
                 "planned_removal_on": "2026-08-28"}
                for sow, boar in assignments
            ]},
            evidence_generation="PROVIDER-MESSAGE-3556",
        )

    def test_exact_five_are_atomic_and_replay_is_zero_effect(self):
        preview = self.preview()
        result, status = execute_grouped_preview(
            preview, confirmed_preview_sha256=preview["preview_sha256"],
            actor_id="owner-test", connect_factory=self.connect,
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["rows_changed"], 5)
        replay, replay_status = execute_grouped_preview(
            preview, confirmed_preview_sha256=preview["preview_sha256"],
            actor_id="owner-test", connect_factory=self.connect,
        )
        self.assertEqual(replay_status, 200)
        self.assertEqual(replay["rows_changed"], 0)
        with self.connect() as db, db.cursor() as cur:
            cur.execute(
                "select count(*), count(distinct sow_pig_id), count(distinct exposure_identity), "
                "count(distinct exposure_group_identity) "
                "from public.pig_breeding_exposure_events "
                "where sow_pig_id = any(%s)", (self.sows,),
            )
            self.assertEqual(cur.fetchone(), (5, 5, 5, 1))
            cur.execute("select count(*) from public.mating_events where sow_pig_id = any(%s)", (self.sows,))
            self.assertEqual(cur.fetchone()[0], 0)
            cur.execute("select count(*) from public.pig_location_events where pig_id = any(%s)", (self.sows,))
            self.assertEqual(cur.fetchone()[0], 0)

    def test_one_invalid_identity_rolls_back_the_whole_group(self):
        preview = self.preview()
        preview["preview"]["rows"][4]["pig_id"] = "SOW-NOT-CANONICAL"
        result,status = execute_grouped_preview(
            preview, confirmed_preview_sha256=preview["preview_sha256"],
            actor_id="owner-test", connect_factory=self.connect,
        )
        self.assertEqual(status,409)
        self.assertEqual(result["status"],"exact_owner_confirmation_required")
        with self.connect() as db, db.cursor() as cur:
            cur.execute(
                "select count(*) from public.pig_breeding_exposure_events "
                "where sow_pig_id = any(%s)", (self.sows,),
            )
            self.assertEqual(cur.fetchone()[0], 0)

    def test_valid_identity_tamper_and_stale_august_29_preview_both_write_zero(self):
        for mutate in ("identity", "date"):
            preview=self.preview()
            if mutate == "identity":
                preview["preview"]["rows"][0]["pig_id"] = self.sows[1]
            else:
                preview["preview"]["rows"][0]["planned_removal_on"] = "2026-08-29"
            result,status=execute_grouped_preview(preview,
                confirmed_preview_sha256=preview["preview_sha256"],actor_id="owner-test",
                connect_factory=self.connect)
            self.assertEqual(status,409)
            self.assertEqual(result["status"],"exact_owner_confirmation_required")
        stale=copy.deepcopy(self.preview())
        stale["preview"]["rows"][0]["planned_removal_on"]="2026-08-29"
        raw=stale["preview"]
        import hashlib,json
        digest=hashlib.sha256(json.dumps(raw,sort_keys=True,separators=(",",":")).encode()).hexdigest()
        stale["preview_sha256"]=digest
        from modules.pig_weights.herdmaster_breeding_exposure_recovery import _stable
        stale["operation_id"]=_stable("HERD-BREED-GROUP-",digest)
        result,status=execute_grouped_preview(stale,confirmed_preview_sha256=digest,
            actor_id="owner-test",connect_factory=self.connect)
        self.assertEqual((status,result["status"],result["rows_changed"]),
            (409,"corrected_exposure_preview_required",0))
        with self.connect() as db, db.cursor() as cur:
            cur.execute("select count(*) from public.pig_breeding_exposure_events where sow_pig_id=any(%s)",(self.sows,))
            self.assertEqual(cur.fetchone()[0],0)


if __name__ == "__main__":
    unittest.main()
