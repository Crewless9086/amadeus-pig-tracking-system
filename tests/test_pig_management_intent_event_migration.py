import unittest
from pathlib import Path


class PigManagementIntentEventMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = Path(
            "supabase/migrations/202607220001_complete_pig_observation_and_management_intent_events.sql"
        ).read_text(encoding="utf-8").lower()

    def test_observations_gain_required_confidence_and_optional_evidence(self):
        self.assertIn("alter table public.pig_observation_events", self.sql)
        self.assertIn("confidence numeric(4, 3) not null", self.sql)
        self.assertIn("confidence >= 0 and confidence <= 1", self.sql)
        self.assertIn("evidence_reference text", self.sql)

    def test_management_intents_are_separate_append_only_advisory_records(self):
        self.assertIn("create table if not exists public.pig_management_intent_events", self.sql)
        self.assertIn("management_intent_event_id text primary key", self.sql)
        self.assertIn("author_reference text not null", self.sql)
        self.assertIn("'sell_after_weaning'", self.sql)
        self.assertIn("intent_status text not null default 'advisory'", self.sql)
        self.assertIn("observation_event_id text references public.pig_observation_events", self.sql)
        self.assertIn("idempotency_key text not null unique", self.sql)
        self.assertIn("enable row level security", self.sql)
        self.assertIn("pig_management_intent_events_validate_references", self.sql)
        self.assertIn("observation_event.pig_id = new.pig_id", self.sql)
        self.assertIn("prior_event.pig_id = new.pig_id", self.sql)
        self.assertIn("before update or delete on public.pig_management_intent_events", self.sql)
        self.assertIn("pig_management_intent_events_block_update_delete", self.sql)

    def test_intent_migration_cannot_change_current_or_operational_state(self):
        prohibited = (
            "update public.pigs",
            "insert into public.pigs",
            "delete from public.pigs",
            "update public.orders",
            "update public.sales",
            "update public.reservations",
            "update public.slaughter",
        )
        for statement in prohibited:
            with self.subTest(statement=statement):
                self.assertNotIn(statement, self.sql)
        self.assertIn("without operational writes", self.sql)


if __name__ == "__main__":
    unittest.main()
