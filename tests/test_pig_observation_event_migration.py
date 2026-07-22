import unittest
from pathlib import Path


class PigObservationEventMigrationTests(unittest.TestCase):
    def test_observation_fact_rail_is_additive_append_only_and_owner_safe(self):
        sql = Path("supabase/migrations/202607200001_create_pig_observation_events.sql").read_text(encoding="utf-8").lower()

        self.assertIn("create table if not exists public.pig_observation_events", sql)
        self.assertIn("pig_id text not null references public.pigs(pig_id)", sql)
        self.assertIn("idempotency_key text not null unique", sql)
        self.assertIn("supersedes_observation_event_id text references public.pig_observation_events", sql)
        self.assertIn("pig_observation_events_validate_supersession", sql)
        self.assertIn("prior_event.pig_id = new.pig_id", sql)
        self.assertIn("measurements_json jsonb not null", sql)
        self.assertIn("enable row level security", sql)
        self.assertIn("before update or delete on public.pig_observation_events", sql)
        self.assertIn("pig_observation_events_block_update_delete", sql)
        self.assertIn("migration_log", sql)
        self.assertNotIn("drop table", sql)
        self.assertNotIn("truncate ", sql)
        self.assertNotIn("update public.pigs", sql)
        self.assertNotIn("insert into public.pigs", sql)

    def test_completion_migration_adds_capture_authority_without_browser_writes(self):
        sql = Path("supabase/migrations/202607220001_complete_pig_observation_and_management_intent_events.sql").read_text(encoding="utf-8").lower()

        self.assertIn("add column if not exists confidence", sql)
        self.assertIn("add column if not exists evidence_reference", sql)
        self.assertIn("create table if not exists public.pig_management_intent_events", sql)
        self.assertIn("intent_status text not null default 'advisory'", sql)
        self.assertIn("pig_observation_events_service_role_insert", sql)
        self.assertIn("pig_management_intent_events_service_role_insert", sql)
        self.assertIn("to service_role", sql)
        self.assertNotIn("to authenticated", sql)
        self.assertNotIn("update public.pigs", sql)


if __name__ == "__main__":
    unittest.main()
