"""Hosted/disposable PostgreSQL proof for protected first-treatment replay."""
import os
import uuid
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg

from modules.pig_weights.farm_supabase_write_service import (
    apply_litter_first_treatment_packet, stable_first_treatment_event_id,
)


class LitterFirstTreatmentAtomicPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")

    def setUp(self):
        suffix = uuid.uuid4().hex[:10]
        self.operation_id = f"OOM-HERD-FIRST-{suffix}"
        self.litter_id = f"LIT-FIRST-{suffix}"
        self.sow_id = f"SOW-FIRST-{suffix}"
        self.product_id = f"PROD-FIRST-{suffix}"
        self.pig_ids = [f"PIG-FIRST-{suffix}-{number}" for number in (1, 2)]
        with psycopg.connect(self.url) as db:
            db.execute("insert into public.pigs(pig_id,status,on_farm,animal_type) values(%s,'Active',true,'Sow')", (self.sow_id,))
            db.execute("insert into public.litters(litter_id,farrowing_date,sow_pig_id,litter_status) values(%s,'2026-08-20',%s,'Active')", (self.litter_id, self.sow_id))
            db.execute("insert into public.farm_products(product_id,product_name,is_active) values(%s,'Iron',true)", (self.product_id,))
            for pig_id in self.pig_ids:
                db.execute("insert into public.pigs(pig_id,status,on_farm,animal_type,litter_id) values(%s,'Active',true,'Piglet',%s)", (pig_id, self.litter_id))

    def tearDown(self):
        with psycopg.connect(self.url) as db:
            db.execute("delete from public.pig_medical_events where pig_id=any(%s)", (self.pig_ids,))
            db.execute("delete from public.pigs where pig_id=any(%s)", (self.pig_ids,))
            db.execute("delete from public.litters where litter_id=%s", (self.litter_id,))
            db.execute("delete from public.pigs where pig_id=%s", (self.sow_id,))
            db.execute("delete from public.farm_products where product_id=%s", (self.product_id,))

    def packet(self):
        rows = []
        for pig_id in self.pig_ids:
            event_id = stable_first_treatment_event_id(
                self.operation_id, pig_id, "Antiparasitic", self.product_id)
            rows.append([event_id, pig_id, "2026-08-25", "Antiparasitic",
                self.product_id, "Iron", "1", "ml", "injection", "First treatment",
                "LOT-1", "0", "", "ANTON", "No", "", "First treatment", "2026-08-25"])
        return {"litter_id": self.litter_id, "sow_pig_id": self.sow_id,
            "pig_ids": self.pig_ids, "protected_operation_id": self.operation_id,
            "action_date": "2026-08-25", "earmarked": False,
            "male_count": None, "female_count": None, "treatment_rows": rows}

    def apply(self):
        return apply_litter_first_treatment_packet(
            self.packet(), connect_factory=lambda _url: psycopg.connect(self.url))

    def test_crash_after_commit_replay_is_noop_with_same_rows(self):
        first = self.apply()  # result may be lost before claim completion
        replay = self.apply()
        self.assertEqual(first["treatment_rows_created"], 2)
        self.assertEqual(replay["status"], "first_treatment_replayed_noop")
        with psycopg.connect(self.url) as db:
            self.assertEqual(db.execute("select count(*) from public.pig_medical_events where pig_id=any(%s)", (self.pig_ids,)).fetchone()[0], 2)

    def test_concurrent_same_claim_commits_each_medical_effect_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _value: self.apply(), range(2)))
        self.assertEqual(sorted(result["treatment_rows_created"] for result in results), [0, 2])
        with psycopg.connect(self.url) as db:
            self.assertEqual(db.execute("select count(distinct medical_event_id) from public.pig_medical_events where pig_id=any(%s)", (self.pig_ids,)).fetchone()[0], 2)

