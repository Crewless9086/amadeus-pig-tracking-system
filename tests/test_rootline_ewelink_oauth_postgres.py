import os
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.telemetry.rootline_ewelink_oauth_store import (
    PostgresOAuthStateStore, PostgresOAuthTokenStore,
)


DATABASE_URL = os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL", "").strip()


@unittest.skipUnless(DATABASE_URL, "disposable ROOTLINE PostgreSQL URL is required")
class EWeLinkOAuthPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        migration = Path("supabase/migrations/202608060001_create_rootline_ewelink_oauth_vault.sql").read_text()
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("do $$ begin create role anon; exception when duplicate_object then null; end $$")
            connection.execute("do $$ begin create role authenticated; exception when duplicate_object then null; end $$")
            connection.execute("create schema if not exists app_private")
            connection.execute("create table if not exists app_private.migration_log "
                               "(migration_id text primary key, description text not null, "
                               "applied_at timestamptz not null default now())")
            connection.execute(migration)

    def setUp(self):
        import psycopg
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("truncate app_private.rootline_ewelink_oauth_states")
            connection.execute("truncate app_private.rootline_ewelink_oauth_tokens")

    def test_state_is_consumed_exactly_once(self):
        now = datetime.now(timezone.utc)
        store = PostgresOAuthStateStore(DATABASE_URL)
        store.create({"state_digest": "a" * 64, "principal_digest": "b" * 64,
                      "nonce_digest": "c" * 64, "redirect_uri_digest": "d" * 64,
                      "expires_at": now + timedelta(minutes=1)})
        self.assertIsNotNone(store.consume("a" * 64, now))
        self.assertIsNone(store.consume("a" * 64, now))

    def test_token_generations_are_append_only_and_account_bound(self):
        now = datetime.now(timezone.utc)
        item = {"token_binding_id": "ROOTLINE-EWELINK-TEST", "provider_account_digest": "a" * 64,
                "device_id": "100204e9bc", "region": "eu",
                "access_token_ciphertext": "encrypted-a", "refresh_token_ciphertext": "encrypted-r",
                "access_expires_at": now + timedelta(days=30),
                "refresh_expires_at": now + timedelta(days=60), "response_digest": "b" * 64,
                "adapter_version": "rootline_ewelink_oauth_v1", "status_field_names": ["switches"],
                "created_at": now}
        store = PostgresOAuthTokenStore(DATABASE_URL)
        self.assertTrue(store.append(item))
        self.assertFalse(store.append(item))
        with self.assertRaises(Exception):
            store.append({**item, "token_binding_id": "ROOTLINE-EWELINK-OTHER",
                          "provider_account_digest": "c" * 64})


if __name__ == "__main__":
    unittest.main()
