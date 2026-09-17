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
            cur.execute("""select count(*),count(mating_date),count(*) filter(where breeding_cycle_state='Exposure Active'),
                min(service_window_start),max(service_window_end),min(expected_farrowing_window_start),max(expected_farrowing_window_end)
                from public.mating_events where sow_pig_id = any(%s)""", (self.sows,))
            self.assertEqual(cur.fetchone(),(5,0,5,__import__('datetime').date(2026,8,12),
                __import__('datetime').date(2026,8,28),__import__('datetime').date(2026,12,4),
                __import__('datetime').date(2026,12,20)))
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

    def test_group_removal_completes_same_five_window_cycles_without_exact_dates(self):
        started = self.preview()
        execute_grouped_preview(started, confirmed_preview_sha256=started["preview_sha256"],
                                actor_id="owner-test", connect_factory=self.connect)
        rows=[]
        with self.connect() as db, db.cursor() as cur:
            cur.execute("""select sow_pig_id,boar_pig_id,exposure_identity,exposure_group_identity,occurred_on
                from public.pig_breeding_exposure_events where sow_pig_id=any(%s) and event_kind='started'
                order by sow_pig_id""",(self.sows,))
            for sow,boar,identity,group_identity,occurred_on in cur.fetchall():
                rows.append({"pig_id":sow,"action":"exposure_removal","boar_pig_id":boar,
                    "exposure_identity":identity,"exposure_group_identity":group_identity,
                    "exposure_started_on":str(occurred_on),"actual_removed_on":"2026-08-28"})
        removal=build_grouped_preview({"rows":rows},evidence_generation="REMOVAL-PROVIDER-1")
        result,status=execute_grouped_preview(removal,
            confirmed_preview_sha256=removal["preview_sha256"],actor_id="owner-test",
            connect_factory=self.connect)
        self.assertEqual((status,result["rows_changed"]),(201,5))
        with self.connect() as db, db.cursor() as cur:
            cur.execute("""select count(*),count(mating_date),min(service_window_start),
                max(service_window_end),min(expected_farrowing_window_start),
                max(expected_farrowing_window_end),count(distinct source_exposure_identity)
                from public.mating_events where sow_pig_id=any(%s)""",(self.sows,))
            self.assertEqual(cur.fetchone(),(5,0,__import__('datetime').date(2026,8,12),
                __import__('datetime').date(2026,8,28),__import__('datetime').date(2026,12,4),
                __import__('datetime').date(2026,12,20),5))
            cur.execute("select count(*) from public.mating_events where sow_pig_id=any(%s) and breeding_cycle_state='Exposure Complete'",(self.sows,))
            self.assertEqual(cur.fetchone()[0],5)
            cur.execute("select count(*) from public.pig_location_events where pig_id=any(%s)",(self.sows,))
            self.assertEqual(cur.fetchone()[0],0)
        replay,replay_status=execute_grouped_preview(removal,
            confirmed_preview_sha256=removal["preview_sha256"],actor_id="owner-test",
            connect_factory=self.connect)
        self.assertEqual((replay_status,replay["rows_changed"]),(200,0))

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

    def test_cycle_constraint_rejects_contradictory_active_and_complete_dates(self):
        with self.connect() as db, db.cursor() as cur:
            with self.assertRaises(psycopg.errors.CheckViolation):
                cur.execute("""insert into public.mating_events(
                    mating_id,sow_pig_id,boar_pig_id,source_exposure_identity,exposure_group_identity,
                    service_window_start,service_window_end,expected_farrowing_window_start,
                    expected_farrowing_window_end,exposure_planned_removal_on,service_date_basis,
                    breeding_cycle_state,exposure_actual_removal_on)
                    values(%s,%s,%s,%s,%s,'2026-08-12','2026-08-28','2026-12-04',
                           '2026-12-20','2026-08-28','exposure_window_estimate',
                           'Exposure Active','2026-08-28')""",
                    (f"MAT-{self.suffix}",self.sows[0],self.boars[0],f"EXPOSURE-{self.suffix}",f"GROUP-{self.suffix}"))
            db.rollback()

    def test_early_and_late_uit_complete_same_cycle_and_keep_original_plan(self):
        for index, actual in enumerate(("2026-08-26", "2026-08-30")):
            started = self.preview()
            started["preview"]["rows"] = [started["preview"]["rows"][index]]
            import hashlib, json
            digest = hashlib.sha256(json.dumps(started["preview"],sort_keys=True,separators=(",",":")).encode()).hexdigest()
            started["preview_sha256"] = digest
            from modules.pig_weights.herdmaster_breeding_exposure_recovery import _stable
            started["operation_id"] = _stable("HERD-BREED-GROUP-",digest)
            result,status=execute_grouped_preview(started,confirmed_preview_sha256=digest,
                actor_id="owner-test",connect_factory=self.connect)
            self.assertEqual((status,result["rows_changed"]),(201,1))
            row=started["preview"]["rows"][0]
            exposure_identity=_stable("HERD-EXPOSURE-ID-",row["pig_id"],row["boar_pig_id"],row["exposure_started_on"])
            removal=build_grouped_preview({"rows":[{"pig_id":row["pig_id"],"action":"exposure_removal",
                "boar_pig_id":row["boar_pig_id"],"exposure_identity":exposure_identity,
                "exposure_group_identity":row["exposure_group_identity"],
                "exposure_started_on":"2026-08-12","actual_removed_on":actual}]},
                evidence_generation=f"UIT-{actual}")
            result,status=execute_grouped_preview(removal,
                confirmed_preview_sha256=removal["preview_sha256"],actor_id="owner-test",
                connect_factory=self.connect)
            self.assertEqual((status,result["rows_changed"]),(201,1))
            with self.connect() as db, db.cursor() as cur:
                cur.execute("""select breeding_cycle_state,exposure_planned_removal_on,
                    exposure_actual_removal_on,service_window_end from public.mating_events
                    where source_exposure_identity=%s""",(exposure_identity,))
                self.assertEqual(cur.fetchone(),("Exposure Complete",__import__('datetime').date(2026,8,28),
                    __import__('datetime').date.fromisoformat(actual),__import__('datetime').date.fromisoformat(actual)))
        with self.connect() as db, db.cursor() as cur:
            with self.assertRaises(psycopg.errors.CheckViolation):
                cur.execute("""insert into public.mating_events(
                    mating_id,sow_pig_id,boar_pig_id,source_exposure_identity,exposure_group_identity,
                    service_window_start,service_window_end,expected_farrowing_window_start,
                    expected_farrowing_window_end,exposure_planned_removal_on,service_date_basis,
                    breeding_cycle_state,exposure_actual_removal_on)
                    values(%s,%s,%s,%s,%s,'2026-08-12','2026-08-11','2026-12-04',
                           '2026-12-03','2026-08-11','exposure_window_estimate',
                           'Exposure Complete','2026-08-11')""",
                    (f"MAT-{self.suffix}-2",self.sows[1],self.boars[0],f"EXPOSURE-{self.suffix}-2",f"GROUP-{self.suffix}"))
            db.rollback()


if __name__ == "__main__":
    unittest.main()
