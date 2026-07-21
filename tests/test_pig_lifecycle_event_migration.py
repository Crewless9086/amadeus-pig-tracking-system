import unittest
from pathlib import Path


class PigLifecycleEventMigrationTests(unittest.TestCase):
    def test_lifecycle_audit_rail_is_additive_append_only_and_owner_safe(self):
        sql = Path("supabase/migrations/202607210001_create_pig_lifecycle_events.sql").read_text(encoding="utf-8").lower()

        self.assertIn("create table if not exists public.pig_lifecycle_events", sql)
        self.assertIn("pig_id text not null references public.pigs(pig_id) on delete restrict", sql)
        self.assertIn("lifecycle_event_type text not null check", sql)
        self.assertIn("effective_at timestamptz not null", sql)
        self.assertIn("recorded_at timestamptz not null default now()", sql)
        self.assertIn("actor_reference text not null check (btrim(actor_reference) <> '')", sql)
        self.assertIn("source_reference text not null check (btrim(source_reference) <> '')", sql)
        self.assertIn("idempotency_key text not null unique", sql)
        self.assertIn("supersedes_lifecycle_event_id text references public.pig_lifecycle_events", sql)
        self.assertIn("pig_lifecycle_events_validate_supersession", sql)
        self.assertIn("prior_event.pig_id = new.pig_id", sql)
        self.assertIn("event_payload jsonb not null", sql)
        self.assertIn("effective_at <= recorded_at", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("before update or delete on public.pig_lifecycle_events", sql)
        self.assertIn("pig_lifecycle_events_block_update_delete", sql)
        self.assertIn("migration_log", sql)
        self.assertNotIn("drop table", sql)
        self.assertNotIn("truncate ", sql)
        self.assertNotIn("update public.pigs", sql)
        self.assertNotIn("insert into public.pigs", sql)
        self.assertNotIn("alter table public.pigs", sql)


if __name__ == "__main__":
    unittest.main()
