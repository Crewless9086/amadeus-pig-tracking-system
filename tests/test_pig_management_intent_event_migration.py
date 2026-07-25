import unittest
from pathlib import Path


class PigManagementIntentEventMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = Path(
            "supabase/migrations/202607220001_complete_pig_observation_and_management_intent_events.sql"
        ).read_text(encoding="utf-8").lower()

    def test_separate_append_only_advisory_rail_has_same_pig_and_idempotency_guards(self):
        required = (
            "create table if not exists public.pig_management_intent_events",
            "intent_status text not null default 'advisory' check (intent_status = 'advisory')",
            "idempotency_key text not null unique",
            "enable row level security",
            "observation_event.pig_id = new.pig_id",
            "prior_event.pig_id = new.pig_id",
            "before update or delete on public.pig_management_intent_events",
            "pig_management_intent_events_block_update_delete",
        )
        for value in required:
            with self.subTest(value=value):
                self.assertIn(value, self.sql)

    def test_authority_and_no_current_state_mutation_contract_is_static_and_explicit(self):
        self.assertIn("to service_role with check (true)", self.sql)
        self.assertNotIn("to authenticated", self.sql)
        self.assertNotIn("to anon", self.sql)
        prohibited = (
            "update public.pigs", "insert into public.pigs", "delete from public.pigs",
            "update public.orders", "update public.sales", "update public.reservations",
            "update public.slaughter", "insert into public.orders",
        )
        for statement in prohibited:
            with self.subTest(statement=statement):
                self.assertNotIn(statement, self.sql)


if __name__ == "__main__":
    unittest.main()
