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
        self.assertIn("migration_log", sql)
        self.assertNotIn("drop table", sql)
        self.assertNotIn("truncate ", sql)
        self.assertNotIn("update public.pigs", sql)
        self.assertNotIn("insert into public.pigs", sql)


if __name__ == "__main__":
    unittest.main()
