"""Disposable-PostgreSQL proof for atomic, replay-safe Weaning Day packets."""
import os
import copy
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import psycopg

from modules.pig_weights.farm_supabase_write_service import (
    apply_litter_weaning_day_packet,
)
from scripts.recover_litter_2026_322b import recover


class LitterWeaningAtomicPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest("CHARLIE_DISPOSABLE_POSTGRES_URL not configured")
        with psycopg.connect(cls.url) as connection:
            connection.execute(
                """
                create or replace view public.current_canonical_pig_state as
                select * from public.pig_current_state
                """
            )

    @classmethod
    def tearDownClass(cls):
        with psycopg.connect(cls.url) as connection:
            connection.execute(
                "drop view if exists public.current_canonical_pig_state"
            )

    def setUp(self):
        suffix = uuid.uuid4().hex[:10]
        self.litter_id = f"LIT-WEAN-{suffix}"
        self.pen_from = f"PEN-WF-{suffix}"
        self.pen_to = f"PEN-WT-{suffix}"
        self.pigs = [f"PIG-WEAN-{suffix}-1", f"PIG-WEAN-{suffix}-2"]
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.pens(pen_id,pen_name)
                    values(%s,'From'),(%s,'To')
                    """,
                    (self.pen_from, self.pen_to),
                )
                cursor.execute(
                    """
                    insert into public.litters(
                        litter_id,farrowing_date,born_alive,litter_status
                    ) values(%s,'2026-06-01',2,'Active')
                    """,
                    (self.litter_id,),
                )
                for pig_id in self.pigs:
                    cursor.execute(
                        """
                        insert into public.pigs(
                            pig_id,status,on_farm,animal_type,sex,litter_id,
                            initial_pen_id
                        ) values(%s,'Active',true,'Piglet','Female',%s,%s)
                        """,
                        (pig_id, self.litter_id, self.pen_from),
                    )

    def test_completed_incident_recovery_apply_is_permanently_disabled(self):
        with self.assertRaisesRegex(RuntimeError, "recovery is complete"):
            recover(self.url, apply=True)

    def tearDown(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.pig_medical_events where pig_id=any(%s)",
                    (self.pigs,),
                )
                cursor.execute(
                    "delete from public.pig_location_events where pig_id=any(%s)",
                    (self.pigs,),
                )
                cursor.execute(
                    "delete from public.pig_weight_events where pig_id=any(%s)",
                    (self.pigs,),
                )
                cursor.execute(
                    "delete from public.pigs where pig_id=any(%s)",
                    (self.pigs,),
                )
                cursor.execute(
                    "delete from public.litters where litter_id=%s",
                    (self.litter_id,),
                )
                cursor.execute(
                    "delete from public.pens where pen_id=any(%s)",
                    ([self.pen_from, self.pen_to],),
                )

    def packet(self):
        treatment_rows = []
        for pig_id in self.pigs:
            treatment_rows.append([
                "IGNORED-RANDOM-ID", pig_id, "2026-07-28", "Deworming",
                "", "Dewormer", "1", "ml", "oral", "Weaning Day",
                "LOT-1", "0", "", "owner", "No", "", "Observed treatment.",
                "2026-07-28",
            ])
        return {
            "litter_id": self.litter_id,
            "wean_date": date(2026, 7, 28),
            "changed_by": "owner-admin:test",
            "piglets": [
                {
                    "pig_id": self.pigs[0], "tag_number": "901",
                    "sex": "Male",
                    "weight_kg": 7.1, "from_pen_id": self.pen_from,
                    "to_pen_id": self.pen_to, "notes": "Weaning Day.",
                },
                {
                    "pig_id": self.pigs[1], "tag_number": "902",
                    "sex": "Female",
                    "weight_kg": 7.4, "from_pen_id": self.pen_from,
                    "to_pen_id": self.pen_to, "notes": "Weaning Day.",
                },
            ],
            "treatment_rows": treatment_rows,
        }

    def counts(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                values = []
                for table in (
                    "pig_medical_events",
                    "pig_weight_events",
                    "pig_location_events",
                ):
                    cursor.execute(
                        f"select count(*) from public.{table} where pig_id=any(%s)",
                        (self.pigs,),
                    )
                    values.append(cursor.fetchone()[0])
                return tuple(values)

    def row_versions(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select pig_id,updated_at from public.pigs
                    where pig_id=any(%s) order by pig_id
                    """,
                    (self.pigs,),
                )
                pigs = cursor.fetchall()
                cursor.execute(
                    "select updated_at from public.litters where litter_id=%s",
                    (self.litter_id,),
                )
                return pigs, cursor.fetchone()[0]

    def test_complete_packet_commits_once_and_exact_replay_adds_zero_facts(self):
        first = apply_litter_weaning_day_packet(
            self.packet(),
            connect_factory=lambda _url: psycopg.connect(self.url),
        )
        self.assertEqual(first["status"], "weaning_day_committed")
        self.assertEqual(self.counts(), (2, 2, 2))
        versions = self.row_versions()
        replay = apply_litter_weaning_day_packet(
            self.packet(),
            connect_factory=lambda _url: psycopg.connect(self.url),
        )
        self.assertEqual(replay["status"], "weaning_day_replayed_withheld")
        self.assertEqual(replay["operation_id"], first["operation_id"])
        self.assertEqual(replay["treatments_created"], 0)
        self.assertEqual(replay["weights_created"], 0)
        self.assertEqual(replay["movements_created"], 0)
        self.assertEqual(replay["piglets_updated"], 0)
        self.assertEqual(replay["litter_updated"], 0)
        self.assertEqual(self.counts(), (2, 2, 2))
        self.assertEqual(self.row_versions(), versions)

    def test_changed_withdrawal_or_follow_up_evidence_is_not_exact_replay(self):
        apply_litter_weaning_day_packet(
            self.packet(),
            connect_factory=lambda _url: psycopg.connect(self.url),
        )
        conflicting = copy.deepcopy(self.packet())
        conflicting["treatment_rows"][0][11] = "7"
        conflicting["treatment_rows"][0][12] = "2026-08-04"
        conflicting["treatment_rows"][0][14] = "Yes"
        conflicting["treatment_rows"][0][15] = "2026-08-04"
        with self.assertRaisesRegex(ValueError, "conflicting_treatment_fact"):
            apply_litter_weaning_day_packet(
                conflicting,
                connect_factory=lambda _url: psycopg.connect(self.url),
            )
        self.assertEqual(self.counts(), (2, 2, 2))

    def test_incomplete_pig_projection_is_repaired_but_never_called_replay(self):
        apply_litter_weaning_day_packet(
            self.packet(),
            connect_factory=lambda _url: psycopg.connect(self.url),
        )
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    update public.pigs
                    set animal_type='Piglet',litter_size_weaned=1
                    where pig_id=%s
                    """,
                    (self.pigs[0],),
                )
        result = apply_litter_weaning_day_packet(
            self.packet(),
            connect_factory=lambda _url: psycopg.connect(self.url),
        )
        self.assertEqual(result["status"], "weaning_day_committed")
        self.assertEqual(result["piglets_updated"], 1)
        self.assertEqual(result["litter_updated"], 0)
        self.assertEqual(self.counts(), (2, 2, 2))

    def test_late_conflict_rolls_back_all_earlier_packet_writes(self):
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.pig_weight_events(
                        weight_event_id,pig_id,weight_date,weight_kg,source
                    ) values(%s,%s,'2026-07-28',99,'preexisting-conflict')
                    """,
                    ("WGT-CONFLICT-" + uuid.uuid4().hex, self.pigs[1]),
                )
        with self.assertRaisesRegex(ValueError, "conflicting_weaning_weight_fact"):
            apply_litter_weaning_day_packet(
                self.packet(),
                connect_factory=lambda _url: psycopg.connect(self.url),
            )
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "select tag_number,wean_date from public.pigs where pig_id=%s",
                    (self.pigs[0],),
                )
                self.assertEqual(cursor.fetchone(), (None, None))
                cursor.execute(
                    """
                    select count(*) from public.pig_weight_events
                    where pig_id=%s and source='litter_weaning_day'
                    """,
                    (self.pigs[0],),
                )
                self.assertEqual(cursor.fetchone()[0], 0)

    def test_partial_exact_treatment_state_inserts_only_missing_fact(self):
        row = self.packet()["treatment_rows"][0]
        with psycopg.connect(self.url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.pig_medical_events(
                        medical_event_id,pig_id,treatment_date,treatment_type,
                        product_name,dose,dose_unit,route,
                        reason_for_treatment,batch_lot_number,given_by,
                        withdrawal_days,follow_up_required,medical_notes
                    ) values(%s,%s,'2026-07-28','Deworming','Dewormer','1',
                             'ml','oral','Weaning Day','LOT-1','owner',0,false,
                             'Observed treatment.')
                    """,
                    ("MED-PRE-" + uuid.uuid4().hex, row[1]),
                )
        result = apply_litter_weaning_day_packet(
            self.packet(),
            connect_factory=lambda _url: psycopg.connect(self.url),
        )
        self.assertEqual(result["treatments_created"], 1)
        self.assertEqual(self.counts(), (2, 2, 2))

    def test_concurrent_exact_packets_never_duplicate_facts(self):
        def apply_once():
            try:
                return apply_litter_weaning_day_packet(
                    self.packet(),
                    connect_factory=lambda _url: psycopg.connect(self.url),
                )["status"]
            except psycopg.errors.SerializationFailure:
                return "serialization_withheld"

        with ThreadPoolExecutor(max_workers=2) as pool:
            statuses = list(pool.map(lambda _index: apply_once(), range(2)))
        self.assertIn("weaning_day_committed", statuses)
        self.assertTrue(set(statuses).issubset({
            "weaning_day_committed",
            "weaning_day_replayed_withheld",
            "serialization_withheld",
        }))
        self.assertEqual(self.counts(), (2, 2, 2))


if __name__ == "__main__":
    unittest.main()
