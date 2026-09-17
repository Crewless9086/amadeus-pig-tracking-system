import re
import unittest
from pathlib import Path


RLS_MIGRATION = Path(
    "supabase/migrations/202607130003_enable_beacon_creative_studio_rls.sql"
)
CREATIVE_STUDIO_TABLES = {
    "beacon_creative_jobs",
    "beacon_creative_job_sources",
    "beacon_creative_provider_attempts",
    "beacon_creative_cost_events",
    "beacon_creative_variants",
    "beacon_creative_review_events",
}


class BeaconCreativeStudioRlsMigrationTests(unittest.TestCase):
    def test_all_private_tables_enable_rls_without_browser_policies(self):
        migration = RLS_MIGRATION.read_text(encoding="utf-8").lower()
        enabled_tables = set(
            re.findall(
                r"alter\s+table\s+public\.([a-z0-9_]+)\s+enable\s+row\s+level\s+security\s*;",
                migration,
            )
        )

        self.assertEqual(enabled_tables, CREATIVE_STUDIO_TABLES)
        self.assertEqual(migration.count("enable row level security"), len(CREATIVE_STUDIO_TABLES))

        for forbidden in (
            "create policy",
            "force row level security",
            "grant ",
            "insert into",
            "update public.",
            "delete from",
            "drop table",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, migration)


if __name__ == "__main__":
    unittest.main()
