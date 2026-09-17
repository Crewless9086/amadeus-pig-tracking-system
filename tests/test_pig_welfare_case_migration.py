import unittest
from pathlib import Path


class PigWelfareCaseMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sql = Path(
            "supabase/migrations/202608200002_create_pig_welfare_case_lifecycle.sql"
        ).read_text(encoding="utf-8").lower()

    def test_stable_episode_identity_allows_unrelated_concurrent_cases(self):
        self.assertIn("create table if not exists public.pig_welfare_cases", self.sql)
        self.assertIn(
            "constraint pig_welfare_case_episode_identity_unique unique (pig_id, episode_key, concern_key)",
            self.sql,
        )
        self.assertNotIn("unique (pig_id)", self.sql)
        self.assertIn("recurrence_of_welfare_case_id", self.sql)
        self.assertIn("prior_case.concern_key = new.concern_key", self.sql)
        self.assertIn("prior_case.episode_started_at < new.episode_started_at", self.sql)

    def test_lifecycle_is_explicit_append_only_and_silence_cannot_recover(self):
        self.assertIn("create table if not exists public.pig_welfare_case_events", self.sql)
        for required in (
            "'opened'", "'urgency_changed'", "'owner_assigned'",
            "'next_check_scheduled'", "'escalated'", "'closed'", "'reopened'",
        ):
            self.assertIn(required, self.sql)
        self.assertIn("closed welfare case requires explicit reopening", self.sql)
        self.assertIn("only a closed welfare case may be reopened", self.sql)
        self.assertIn("welfare correction must preserve current case state", self.sql)
        self.assertIn("death-closed living welfare case is terminal", self.sql)
        self.assertIn("death-closed welfare case requires canonical death fact link", self.sql)
        self.assertIn("unique (welfare_case_id, sequence_no)", self.sql)
        self.assertIn("order by event.sequence_no desc", self.sql)
        self.assertIn("latest.closure_kind", self.sql)
        self.assertIn("welfare case lifecycle must begin with opened", self.sql)
        self.assertIn("before update or delete", self.sql)
        self.assertIn("pig welfare case records are append-only", self.sql)
        self.assertNotIn("interval '", self.sql)

    def test_provenance_links_fact_domains_without_merging_or_writing_them(self):
        self.assertIn("create table if not exists public.pig_welfare_case_fact_links", self.sql)
        for domain in ("'observation'", "'medical'", "'treatment'", "'movement'", "'pig_lifecycle'", "'mortality'"):
            self.assertIn(domain, self.sql)
        self.assertIn("'closes_living_welfare_question'", self.sql)
        self.assertIn("fact_domain in ('pig_lifecycle', 'mortality')", self.sql)
        self.assertIn("living welfare closure link requires a death-closed case event", self.sql)
        self.assertIn("fact_id text not null", self.sql)
        self.assertIn("provenance_json jsonb not null", self.sql)
        self.assertNotIn("update public.pig_observation_events", self.sql)
        self.assertNotIn("update public.pig_medical_events", self.sql)
        self.assertNotIn("update public.pig_location_events", self.sql)
        self.assertNotIn("update public.pig_lifecycle_events", self.sql)
        self.assertNotIn("update public.pigs", self.sql)

    def test_foundation_has_no_channel_or_protected_action_authority(self):
        self.assertIn("enable row level security", self.sql)
        self.assertIn("revoke all privileges", self.sql)
        self.assertIn("with (security_invoker = true)", self.sql)
        self.assertGreaterEqual(self.sql.count("set search_path = pg_catalog, public"), 5)
        self.assertIn("revoke all privileges on function public.pig_welfare_case_event_validate_insert() from public", self.sql)
        self.assertNotIn("sendtelegram", self.sql)
        self.assertNotIn("telegram_message", self.sql)
        self.assertNotIn("diagnosis text", self.sql)
        self.assertNotIn("treatment_instruction", self.sql)
        self.assertNotIn("insert into public.pigs", self.sql)
        self.assertNotIn("alter table public.pigs", self.sql)
        self.assertNotIn("drop table", self.sql)
        self.assertNotIn("truncate ", self.sql)


if __name__ == "__main__":
    unittest.main()
