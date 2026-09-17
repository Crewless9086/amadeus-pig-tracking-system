import unittest
from pathlib import Path


class AgenticOsMigrationTests(unittest.TestCase):
    def test_operational_event_fabric_is_additive_audited_and_rls_enabled(self):
        sql = Path("supabase/migrations/202607190001_create_operational_event_fabric.sql").read_text(encoding="utf-8").lower()
        self.assertIn("create table if not exists public.operational_events", sql)
        self.assertIn("idempotency_key text not null unique", sql)
        self.assertIn("authority_tier text not null", sql)
        self.assertIn("privacy_class text not null", sql)
        self.assertIn("provenance_json jsonb not null", sql)
        self.assertIn("enable row level security", sql)
        self.assertNotIn("drop table", sql)
        self.assertNotIn("truncate ", sql)

    def test_observers_are_database_enforced_proposal_only(self):
        sql = Path("supabase/migrations/202607190002_create_domain_observer_runs.sql").read_text(encoding="utf-8").lower()
        self.assertIn("check (authority_tier = 'observe')", sql)
        self.assertIn("check (writes_authorized = false)", sql)
        self.assertIn("check (sends_authorized = false)", sql)
        self.assertIn("domain_observer_feedback", sql)
        self.assertIn("enable row level security", sql)
        self.assertNotIn("drop table", sql)
        self.assertNotIn("truncate ", sql)


if __name__ == "__main__":
    unittest.main()
