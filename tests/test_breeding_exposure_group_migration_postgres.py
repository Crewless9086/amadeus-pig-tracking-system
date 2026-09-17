"""Upgrade compatibility for governed breeding exposure groups."""
import os
import unittest
from pathlib import Path
import psycopg

URL=os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL","").strip()

@unittest.skipUnless(URL,"disposable PostgreSQL URL is required")
class BreedingExposureGroupMigrationTests(unittest.TestCase):
    def test_legacy_start_is_preserved_and_new_ungrouped_start_is_rejected(self):
        root=Path("supabase/migrations")
        with psycopg.connect(URL) as db, db.cursor() as cur:
            # CI applies the current migration set before integration tests.
            # Reconstruct the exact pre-120003 schema transactionally; the
            # final rollback restores the shared disposable database.
            cur.execute("""alter table public.pig_breeding_exposure_events
                drop constraint if exists pig_breeding_exposure_started_group_required;
                drop index if exists public.pig_breeding_exposure_group_chronology_idx;
                alter table public.pig_breeding_exposure_events
                drop column if exists exposure_group_identity;
                delete from app_private.migration_log
                where migration_id='202608120003_add_breeding_exposure_group_identity'""")
            cur.execute("""create table if not exists public.pigs(pig_id text primary key);
                insert into public.pigs values('LEGACY-SOW'),('LEGACY-BOAR') on conflict do nothing""")
            cur.execute((root/"202608120001_create_breeding_exposure_events.sql").read_text())
            cur.execute("""insert into public.pig_breeding_exposure_events(
                exposure_event_id,exposure_identity,event_kind,sow_pig_id,boar_pig_id,
                occurred_on,planned_removal_on,observer_reference,source_reference,idempotency_key)
                values('LEGACY-EVENT','LEGACY-EXPOSURE','started','LEGACY-SOW','LEGACY-BOAR',
                '2026-08-01','2026-08-17','owner','legacy','legacy-key')""")
            cur.execute((root/"202608120003_add_breeding_exposure_group_identity.sql").read_text())
            cur.execute("select exposure_group_identity from public.pig_breeding_exposure_events where exposure_event_id='LEGACY-EVENT'")
            self.assertIsNone(cur.fetchone()[0])
            cur.execute("savepoint invalid_new")
            with self.assertRaises(psycopg.Error):
                cur.execute("""insert into public.pig_breeding_exposure_events(
                    exposure_event_id,exposure_identity,event_kind,sow_pig_id,boar_pig_id,
                    occurred_on,planned_removal_on,observer_reference,source_reference,idempotency_key)
                    values('NEW-EVENT','NEW-EXPOSURE','started','LEGACY-SOW','LEGACY-BOAR',
                    '2026-08-02','2026-08-18','owner','new','new-key')""")
            cur.execute("rollback to savepoint invalid_new")
            cur.execute("""insert into public.pig_breeding_exposure_events(
                exposure_event_id,exposure_identity,exposure_group_identity,event_kind,
                sow_pig_id,boar_pig_id,occurred_on,planned_removal_on,observer_reference,
                source_reference,idempotency_key) values('NEW-EVENT','NEW-EXPOSURE','GROUP-1',
                'started','LEGACY-SOW','LEGACY-BOAR','2026-08-02','2026-08-18','owner','new','new-key')""")
            cur.execute("""select exposure_event_id,exposure_group_identity
                from public.pig_breeding_exposure_events
                where exposure_event_id in ('LEGACY-EVENT','NEW-EVENT')
                order by exposure_event_id""")
            self.assertEqual(cur.fetchall(),[("LEGACY-EVENT",None),("NEW-EVENT","GROUP-1")])
            db.rollback()
