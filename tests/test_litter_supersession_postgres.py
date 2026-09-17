"""Disposable-PostgreSQL proof for litter supersession projections."""
import os
import pathlib
import unittest
import uuid
import json
from concurrent.futures import ThreadPoolExecutor

import psycopg

from modules.pig_weights.litter_supersession_service import (
    apply_litter_supersession,
    canonical_sha256,
    operation_identity,
    _reference_digests,
)


ROOT = pathlib.Path(__file__).resolve().parents[1]


class LitterSupersessionPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "").strip()
        if not cls.url:
            raise unittest.SkipTest(
                "CHARLIE_DISPOSABLE_POSTGRES_URL not configured"
            )
        migration = (
            ROOT / "supabase/migrations/"
            "202607300001_create_litter_supersession_rail.sql"
        ).read_text(encoding="utf-8")
        history_migration = (
            ROOT / "supabase/migrations/"
            "202607310001_allow_immutable_sam_review_history_in_litter_supersession.sql"
        ).read_text(encoding="utf-8")
        with psycopg.connect(cls.url) as connection:
            connection.execute(
                """
                do $$ begin
                  if not exists (select 1 from pg_roles where rolname='service_role') then
                    create role service_role;
                  end if;
                  if not exists (select 1 from pg_roles where rolname='litter_test_unprivileged') then
                    create role litter_test_unprivileged;
                  end if;
                end $$;
                alter role service_role bypassrls;
                grant usage on schema public to service_role;
                grant select on all tables in schema public to service_role;
                grant update on public.pigs,public.litters,public.mating_events
                  to service_role;
                """
            )
            connection.execute(migration)
            connection.execute(history_migration)

    def setUp(self):
        suffix = uuid.uuid4().hex[:10].upper()
        self.sow = f"PIG-SOW-{suffix}"
        self.boar = f"PIG-BOAR-{suffix}"
        self.retained = f"LIT-RETAIN-{suffix}"
        self.superseded = f"LIT-SUPER-{suffix}"
        self.mating = f"MAT-{suffix}"
        self.kept = [f"PIG-K-{suffix}-{index}" for index in range(10)]
        self.hidden = [f"PIG-H-{suffix}-{index}" for index in range(10)]
        self.kept_dead = self.kept[:3]
        self.hidden_dead = self.hidden[:1]
        self.auth = f"AUTH-{suffix}"
        self.batch = uuid.uuid4()
        self.review_ids = [
            f"SAM-HIST-{suffix}-{index:03d}" for index in range(362)
        ]
        with psycopg.connect(self.url) as connection:
            connection.execute(
                """
                insert into public.pigs(pig_id,status,on_farm,sex,purpose)
                values(%s,'Active',true,'Female','Breeding'),
                      (%s,'Active',true,'Male','Breeding')
                """,
                (self.sow, self.boar),
            )
            connection.execute(
                """
                insert into public.litters(
                    litter_id,farrowing_date,sow_pig_id,boar_pig_id,total_born
                ) values(%s,'2026-07-10',%s,%s,10),
                        (%s,'2026-07-10',%s,%s,10)
                """,
                (
                    self.retained, self.sow, self.boar,
                    self.superseded, self.sow, self.boar,
                ),
            )
            for pig_id, litter_id in [
                *((pig, self.retained) for pig in self.kept),
                *((pig, self.superseded) for pig in self.hidden),
            ]:
                dead = pig_id in self.kept_dead or pig_id in self.hidden_dead
                connection.execute(
                    """
                    insert into public.pigs(
                        pig_id,status,on_farm,animal_type,litter_id,
                        mother_pig_id,father_pig_id
                    ) values(%s,%s,%s,'Piglet',%s,%s,%s)
                    """,
                    (
                        pig_id,
                        "Dead" if dead else "Active",
                        not dead,
                        litter_id,
                        self.sow,
                        self.boar,
                    ),
                )
            connection.execute(
                """
                insert into public.mating_events(
                    mating_id,sow_pig_id,boar_pig_id,mating_date,
                    related_litter_id
                ) values(%s,%s,%s,'2026-03-13',%s)
                """,
                (self.mating, self.sow, self.boar, self.retained),
            )
            connection.execute(
                """
                insert into public.bulk_weight_batches(
                    batch_id,weight_date,status,visible_row_count,skipped_row_count
                ) values(%s,'2026-07-20','complete',90,90)
                """,
                (self.batch,),
            )
            audit_pigs = (self.kept[1:] + self.hidden[1:])
            for row_index in range(90):
                connection.execute(
                    """
                    insert into public.bulk_weight_batch_rows(
                        row_id,batch_id,row_index,pig_id,status,status_reason,
                        idempotency_key
                    ) values(%s,%s,%s,%s,'skipped',
                             'No new weight or pen change entered.',%s)
                    """,
                    (
                        uuid.uuid4(), self.batch, row_index,
                        audit_pigs[row_index % len(audit_pigs)],
                        f"litter-test:{suffix}:{row_index}",
                    ),
                )
            for review_id in self.review_ids:
                connection.execute(
                    """
                    insert into public.sam_live_stock_conversation_review_events(
                      review_event_id,chatwoot_conversation_id,event_source,
                      decision_json,conversation_mode_recommendation
                    ) values(
                      %s,'historical-test','shadow_review',%s::jsonb,'READ_ONLY'
                    )
                    """,
                    (
                        review_id,
                        json.dumps({
                            "canonical_inventory_snapshot": {
                                "excluded_pig_ids": self.hidden,
                                "snapshot_only": True,
                            }
                        }),
                    ),
                )
        with psycopg.connect(self.url) as connection:
            litter_rows = connection.execute(
                """
                select to_jsonb(litter) from public.litters litter
                where litter_id=any(%s) order by litter_id
                """,
                ([self.retained, self.superseded],),
            ).fetchall()
            mating = connection.execute(
                """
                select mating_id,sow_pig_id,boar_pig_id,related_litter_id
                from public.mating_events where mating_id=%s
                """,
                (self.mating,),
            ).fetchone()
            children = connection.execute(
                """
                select to_jsonb(pig) from public.pigs pig
                where litter_id=any(%s) order by pig_id
                """,
                ([self.superseded, self.retained],),
            ).fetchall()
            digests = _reference_digests(
                connection, sorted(self.hidden), sorted(self.hidden + self.kept)
            )
        self.packet = {
            "retained_litter_id": self.retained,
            "superseded_litter_id": self.superseded,
            "retained_child_ids": self.kept,
            "superseded_child_ids": self.hidden,
            "authorization_id": self.auth,
            "mating_id": self.mating,
            "preview_sha256": "a" * 64,
            **digests,
            "input_sha256": canonical_sha256({
                "litters": litter_rows, "mating": mating, "children": children,
                "references": digests,
            }),
        }
        self.assertEqual(self.packet["historical_reference_row_count"], 362)
        self.assertEqual(
            sorted(self.packet["historical_reference_row_ids"]),
            sorted(self.review_ids),
        )
        self.assertTrue(all(
            row["classification"] == "immutable_historical_review_snapshot"
            and row["identities"] == sorted(self.hidden)
            and len(row["decision_json_sha256"]) == 64
            for row in self.packet["historical_reference_rows"]
        ))
        with psycopg.connect(self.url) as connection:
            connection.execute(
                """
                insert into public.litter_correction_authorizations(
                    authorization_id,operation_id,preview_sha256,
                    owner_principal,decision_status,confirmed_at
                ) values(%s,%s,%s,'owner:test','confirmed',now())
                """,
                (self.auth, operation_identity(self.packet), "a" * 64),
            )

    def _packet(self):
        return dict(self.packet)

    def _operation_id(self):
        return operation_identity(self._packet())

    def _service_connection(self):
        connection = psycopg.connect(self.url, autocommit=True)
        connection.execute("set role service_role")
        connection.autocommit = False
        return connection

    def test_current_history_replay_and_unrelated_digest(self):
        with psycopg.connect(self.url) as connection:
            before = connection.execute(
                "select count(*) from public.pigs where pig_id not like %s",
                (f"%{self.sow.split('-')[-1]}%",),
            ).fetchone()[0]
            active_before = connection.execute(
                """
                select count(*) from public.current_canonical_pigs
                 where pig_id=any(%s) and status='Active' and on_farm is true
                """,
                (self.kept + self.hidden,),
            ).fetchone()[0]
            retained_before = connection.execute(
                """
                select pig_id,status,on_farm from public.pigs
                 where pig_id=any(%s) order by pig_id
                """,
                (self.kept,),
            ).fetchall()
        result = apply_litter_supersession(
            self._packet(),
            connect_factory=self._service_connection,
            service_authority="herdmaster_litter_correction_service",
        )
        self.assertEqual(result["rows_created"], 101)
        replay = apply_litter_supersession(
            self._packet(),
            connect_factory=self._service_connection,
            service_authority="herdmaster_litter_correction_service",
        )
        self.assertEqual(replay["rows_created"], 0)
        with psycopg.connect(self.url) as connection:
            current_litters = connection.execute(
                "select count(*) from public.current_canonical_litters where litter_id=any(%s)",
                ([self.retained, self.superseded],),
            ).fetchone()[0]
            current_children = connection.execute(
                "select count(*) from public.current_canonical_pigs where pig_id=any(%s)",
                (self.kept + self.hidden,),
            ).fetchone()[0]
            history = connection.execute(
                "select count(*) from public.historical_litter_representations where litter_id=any(%s)",
                ([self.retained, self.superseded],),
            ).fetchone()[0]
            after = connection.execute(
                "select count(*) from public.pigs where pig_id not like %s",
                (f"%{self.sow.split('-')[-1]}%",),
            ).fetchone()[0]
            active_after = connection.execute(
                """
                select count(*) from public.current_canonical_pigs
                 where pig_id=any(%s) and status='Active' and on_farm is true
                """,
                (self.kept + self.hidden,),
            ).fetchone()[0]
            retained_after = connection.execute(
                """
                select pig_id,status,on_farm from public.pigs
                 where pig_id=any(%s) order by pig_id
                """,
                (self.kept,),
            ).fetchall()
        self.assertEqual((current_litters, current_children, history), (1, 10, 2))
        self.assertEqual(before, after)
        self.assertEqual((active_before, active_after), (16, 7))
        self.assertEqual(active_after - active_before, -9)
        self.assertEqual(retained_before, retained_after)

    def test_sam_review_snapshots_remain_byte_stable_and_non_actionable(self):
        with psycopg.connect(self.url) as connection:
            before = connection.execute(
                """
                select review_event_id,decision_json::text
                  from public.sam_live_stock_conversation_review_events
                 where review_event_id=any(%s) order by review_event_id
                """,
                (self.review_ids,),
            ).fetchall()
            self.assertEqual(
                connection.execute(
                    """
                    select count(*)
                      from public.current_actionable_sam_live_stock_review_events
                     where review_event_id=any(%s)
                    """,
                    (self.review_ids,),
                ).fetchone()[0],
                362,
            )
        apply_litter_supersession(
            self._packet(),
            connect_factory=self._service_connection,
            service_authority="herdmaster_litter_correction_service",
        )
        with psycopg.connect(self.url) as connection:
            after = connection.execute(
                """
                select review_event_id,decision_json::text
                  from public.sam_live_stock_conversation_review_events
                 where review_event_id=any(%s) order by review_event_id
                """,
                (self.review_ids,),
            ).fetchall()
            actionable = connection.execute(
                """
                select count(*)
                  from public.current_actionable_sam_live_stock_review_events
                 where review_event_id=any(%s)
                """,
                (self.review_ids,),
            ).fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(len(after), 362)
        self.assertEqual(actionable, 0)

    def test_sam_identity_outside_historical_decision_payload_blocks(self):
        with psycopg.connect(self.url) as connection:
            connection.execute(
                """
                insert into public.sam_live_stock_conversation_review_events(
                  review_event_id,chatwoot_conversation_id,event_source,
                  sam_reply_excerpt,decision_json
                ) values(%s,'historical-test','shadow_review',%s,'{}'::jsonb)
                """,
                (
                    f"SAM-NONHIST-{uuid.uuid4().hex[:12]}",
                    f"Stale actionable identity {self.hidden[0]}",
                ),
            )
        with self.assertRaisesRegex(
            RuntimeError, "outside decision_json blocks correction"
        ):
            apply_litter_supersession(
                self._packet(),
                connect_factory=self._service_connection,
                service_authority="herdmaster_litter_correction_service",
            )

    def test_actionable_sam_review_fields_each_block_historical_classification(self):
        cases = [
            ("safe_to_send", True, "", "READ_ONLY"),
            ("owner_send_required", True, "", "READ_ONLY"),
            ("no_reply_recommended", True, "", "READ_ONLY"),
            ("escalation_required", True, "", "READ_ONLY"),
            ("recommended_action", False, "contact_owner", "READ_ONLY"),
            ("conversation_mode", False, "", "AUTO"),
        ]
        with psycopg.connect(self.url) as connection:
            for index, (field, flag, recommendation, mode) in enumerate(cases):
                with self.subTest(field=field):
                    connection.execute("savepoint actionable_case")
                    flags = {
                        "safe_to_send": False,
                        "owner_send_required": False,
                        "no_reply_recommended": False,
                        "escalation_required": False,
                    }
                    if field in flags:
                        flags[field] = flag
                    connection.execute(
                        """
                        insert into public.sam_live_stock_conversation_review_events(
                          review_event_id,chatwoot_conversation_id,event_source,
                          decision_json,conversation_mode_recommendation,
                          recommended_action,safe_to_send,owner_send_required,
                          no_reply_recommended,escalation_required
                        ) values(%s,'historical-test','shadow_review',%s::jsonb,
                          %s,%s,%s,%s,%s,%s)
                        """,
                        (
                            f"SAM-ACTION-{self.auth}-{index}",
                            json.dumps({
                                "canonical_inventory_snapshot": {
                                    "excluded_pig_ids": [self.hidden[0]]
                                }
                            }),
                            mode,
                            recommendation,
                            flags["safe_to_send"],
                            flags["owner_send_required"],
                            flags["no_reply_recommended"],
                            flags["escalation_required"],
                        ),
                    )
                    with self.assertRaisesRegex(
                        RuntimeError, "action-bearing SAM review reference"
                    ):
                        _reference_digests(
                            connection,
                            sorted(self.hidden),
                            sorted(self.hidden + self.kept),
                        )
                    connection.execute("rollback to savepoint actionable_case")

    def test_disabled_or_rebound_append_only_trigger_blocks(self):
        with psycopg.connect(self.url) as connection:
            connection.execute("savepoint disabled_guard")
            connection.execute(
                """
                alter table public.sam_live_stock_conversation_review_events
                  disable trigger prevent_sam_live_stock_review_update
                """
            )
            with self.assertRaisesRegex(RuntimeError, "not provably append-only"):
                _reference_digests(
                    connection,
                    sorted(self.hidden),
                    sorted(self.hidden + self.kept),
                )
            connection.execute("rollback to savepoint disabled_guard")

            connection.execute("savepoint rebound_guard")
            connection.execute(
                """
                create or replace function public.sam_review_noop()
                returns trigger language plpgsql as $$
                begin return new; end;
                $$;
                drop trigger prevent_sam_live_stock_review_update
                  on public.sam_live_stock_conversation_review_events;
                create trigger prevent_sam_live_stock_review_update
                  before update
                  on public.sam_live_stock_conversation_review_events
                  for each row execute function public.sam_review_noop()
                """
            )
            with self.assertRaisesRegex(RuntimeError, "not provably append-only"):
                _reference_digests(
                    connection,
                    sorted(self.hidden),
                    sorted(self.hidden + self.kept),
                )
            connection.execute("rollback to savepoint rebound_guard")

            connection.execute("savepoint replaced_function_body")
            connection.execute(
                """
                create or replace function
                  public.prevent_sam_live_stock_review_mutation()
                returns trigger language plpgsql as $$
                begin return new; end;
                $$
                """
            )
            with self.assertRaisesRegex(RuntimeError, "not provably append-only"):
                _reference_digests(
                    connection,
                    sorted(self.hidden),
                    sorted(self.hidden + self.kept),
                )
            connection.execute("rollback to savepoint replaced_function_body")

    def test_review_source_path_and_exact_identity_are_fail_closed(self):
        with psycopg.connect(self.url) as connection:
            connection.execute("savepoint unsupported_source")
            connection.execute(
                """
                insert into public.sam_live_stock_conversation_review_events(
                  review_event_id,chatwoot_conversation_id,event_source,
                  decision_json,conversation_mode_recommendation
                ) values(%s,'historical-test','chatwoot_inbound',%s::jsonb,'READ_ONLY')
                """,
                (
                    f"SAM-SOURCE-{self.auth}",
                    json.dumps({
                        "canonical_inventory_snapshot": {
                            "excluded_pig_ids": [self.hidden[0]]
                        }
                    }),
                ),
            )
            with self.assertRaisesRegex(
                RuntimeError, "action-bearing SAM review reference"
            ):
                _reference_digests(
                    connection, sorted(self.hidden), sorted(self.hidden + self.kept)
                )
            connection.execute("rollback to savepoint unsupported_source")

            connection.execute("savepoint unsupported_path")
            connection.execute(
                """
                insert into public.sam_live_stock_conversation_review_events(
                  review_event_id,chatwoot_conversation_id,event_source,
                  decision_json,conversation_mode_recommendation
                ) values(%s,'historical-test','shadow_review',%s::jsonb,'READ_ONLY')
                """,
                (
                    f"SAM-PATH-{self.auth}",
                    json.dumps({"suggested_reply_text": self.hidden[0]}),
                ),
            )
            with self.assertRaisesRegex(
                RuntimeError, "outside governed snapshot path"
            ):
                _reference_digests(
                    connection, sorted(self.hidden), sorted(self.hidden + self.kept)
                )
            connection.execute("rollback to savepoint unsupported_path")

            connection.execute("savepoint substring_only")
            connection.execute(
                """
                insert into public.sam_live_stock_conversation_review_events(
                  review_event_id,chatwoot_conversation_id,event_source,
                  decision_json,conversation_mode_recommendation
                ) values(%s,'historical-test','shadow_review',%s::jsonb,'READ_ONLY')
                """,
                (
                    f"SAM-SUBSTRING-{self.auth}",
                    json.dumps({
                        "canonical_inventory_snapshot": {
                            "note": self.hidden[0] + "-NOT-AN-IDENTITY"
                        }
                    }),
                ),
            )
            digests = _reference_digests(
                connection, sorted(self.hidden), sorted(self.hidden + self.kept)
            )
            self.assertEqual(digests["historical_reference_row_count"], 362)
            connection.execute("rollback to savepoint substring_only")

    def test_concurrent_same_operation_is_one_create_and_one_replay(self):
        def apply():
            return apply_litter_supersession(
                self._packet(),
                connect_factory=self._service_connection,
                service_authority="herdmaster_litter_correction_service",
            )
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: apply(), range(2)))
        self.assertEqual(sorted(item["rows_created"] for item in results), [0, 101])
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                connection.execute(
                    "select count(*) from public.litter_supersessions where operation_id=%s",
                    (self._operation_id(),),
                ).fetchone()[0],
                1,
            )

    def test_mismatch_rolls_back_and_quarantined_identity_rejects_new_fact(self):
        bad = self._packet()
        bad["input_sha256"] = "f" * 64
        with self.assertRaises(RuntimeError):
            apply_litter_supersession(
                bad,
                connect_factory=self._service_connection,
                service_authority="herdmaster_litter_correction_service",
            )
        with psycopg.connect(self.url) as connection:
            self.assertEqual(
                connection.execute(
                    "select count(*) from public.litter_supersessions where authorization_id=%s",
                    (self.auth,),
                ).fetchone()[0],
                0,
            )
        apply_litter_supersession(
            self._packet(),
            connect_factory=self._service_connection,
            service_authority="herdmaster_litter_correction_service",
        )
        with psycopg.connect(self.url) as connection:
            connection.execute(
                """
                insert into public.pig_weight_events(
                    weight_event_id,pig_id,weight_kg,weight_date,source
                ) values(%s,%s,1.0,'2026-07-30','litter-test')
                """,
                (f"WGT-{uuid.uuid4().hex[:12]}", self.kept[0]),
            )
            with self.assertRaisesRegex(
                psycopg.Error, "superseded duplicate pig identity"
            ):
                connection.execute(
                    """
                    insert into public.pig_weight_events(
                        weight_event_id,pig_id,weight_kg,weight_date,source
                    ) values(%s,%s,1.0,'2026-07-30','litter-test')
                    """,
                    (
                        f"WGT-{uuid.uuid4().hex[:12]}",
                        self.hidden[0],
                    ),
                )

    def test_replay_rejects_full_row_drift_and_revoked_authority(self):
        apply_litter_supersession(
            self._packet(), connect_factory=self._service_connection,
            service_authority="herdmaster_litter_correction_service",
        )
        with psycopg.connect(self.url) as connection:
            connection.execute(
                "update public.pigs set notes='new retained evidence' where pig_id=%s",
                (self.kept[0],),
            )
        with self.assertRaisesRegex(RuntimeError, "canonical input digest mismatch"):
            apply_litter_supersession(
                self._packet(), connect_factory=self._service_connection,
                service_authority="herdmaster_litter_correction_service",
            )

        # Revocation is append-only and checked independently of caller input.
        with psycopg.connect(self.url) as connection:
            connection.execute(
                """
                insert into public.litter_correction_authorization_revocations(
                    authorization_id,revoked_by,reason
                ) values(%s,'owner:test','withdrawn before execution')
                """,
                (self.auth,),
            )
        with self.assertRaisesRegex(RuntimeError, "confirmation is not current"):
            apply_litter_supersession(
                self._packet(), connect_factory=self._service_connection,
                service_authority="herdmaster_litter_correction_service",
            )

    def test_audit_rows_embedded_references_and_privileges_fail_closed(self):
        apply_litter_supersession(
            self._packet(), connect_factory=self._service_connection,
            service_authority="herdmaster_litter_correction_service",
        )
        with psycopg.connect(self.url) as connection:
            protected = connection.execute(
                """
                select row_id from public.litter_supersession_audit_rows
                where operation_id=%s order by row_id limit 2
                """,
                (self._operation_id(),),
            ).fetchall()
        for row_id in protected:
            with psycopg.connect(self.url) as connection:
                with self.assertRaisesRegex(psycopg.Error, "protected litter audit"):
                    connection.execute(
                        "update public.bulk_weight_batch_rows set status_reason='tampered' where row_id=%s",
                        row_id,
                    )
            with psycopg.connect(self.url) as connection:
                with self.assertRaisesRegex(psycopg.Error, "protected litter audit"):
                    connection.execute(
                        "delete from public.bulk_weight_batch_rows where row_id=%s",
                        row_id,
                    )
        with psycopg.connect(self.url) as connection:
            with self.assertRaisesRegex(psycopg.Error, "superseded duplicate pig identity"):
                connection.execute(
                    """
                    insert into public.bulk_weight_batches(
                        batch_id,weight_date,payload_summary_json
                    ) values(%s,'2026-07-30',%s::jsonb)
                    """,
                    (uuid.uuid4(), f'{{"subject":"{self.hidden[0]}"}}'),
                )
        with self._service_connection() as connection:
            with self.assertRaises(psycopg.Error):
                connection.execute(
                    """
                    insert into public.litter_supersessions(
                      operation_id,retained_litter_id,superseded_litter_id,
                      authorization_id,mating_id,preview_sha256,reason,
                      superseded_child_ids,retained_child_ids,
                      reference_allowlist_sha256,skipped_audit_rows_sha256,input_sha256
                    ) values('DIRECT-DENIED',%s,%s,%s,%s,%s,
                      'duplicate_creation_same_farrowing','[]','[]',%s,%s,%s)
                    """,
                    (
                        self.retained, self.superseded, self.auth, self.mating,
                        "a" * 64, "b" * 64, "c" * 64, "d" * 64,
                    ),
                )
        unprivileged = psycopg.connect(self.url, autocommit=True)
        try:
            unprivileged.execute("set role litter_test_unprivileged")
            with self.assertRaises(psycopg.Error):
                unprivileged.execute(
                    """
                    select public.apply_litter_supersession_metadata(
                      'X','A','B','C',%s,'M','[]'::jsonb,'[]'::jsonb,
                      %s,%s,'[]'::jsonb,%s,%s,0,'[]'::jsonb
                    )
                    """,
                    (
                        "a" * 64, "b" * 64, "c" * 64, "d" * 64,
                        canonical_sha256([]),
                    ),
                )
        finally:
            unprivileged.close()


if __name__ == "__main__":
    unittest.main()
