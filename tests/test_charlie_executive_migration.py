import unittest
from pathlib import Path


class CharlieExecutiveMigrationTests(unittest.TestCase):
    def test_control_plane_migration_contains_all_durable_rails(self):
        sql = Path("supabase/migrations/202607170001_create_charlie_executive_control_plane.sql").read_text(encoding="utf-8").lower()
        for table in (
            "charlie_executive_goals", "charlie_delegation_policies", "charlie_control_commands",
            "charlie_recovery_cases", "charlie_capability_trust", "charlie_eval_registry",
            "charlie_research_radar", "charlie_notification_outbox",
        ):
            self.assertIn(f"create table if not exists public.{table}", sql)
        self.assertIn("idempotency_key text not null unique", sql)
        self.assertIn("attempt_count integer not null default 1", sql)

    def test_default_policies_do_not_grant_business_red_zone_authority(self):
        sql = Path("supabase/migrations/202607170001_create_charlie_executive_control_plane.sql").read_text(encoding="utf-8").lower()
        self.assertIn("core.internal_recovery", sql)
        for capability in ("customer.send", "payment.confirm", "stock.reserve", "public.post", "lifecycle.write"):
            self.assertNotIn(f"'{capability}'", sql)
