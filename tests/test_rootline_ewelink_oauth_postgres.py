import os
import json
import subprocess
import sys
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

from modules.telemetry.rootline_ewelink_oauth_store import (
    PostgresOAuthStateStore, PostgresOAuthTokenStore,
)
from modules.telemetry.rootline_ewelink_oauth import (
    ADAPTER_VERSION, _digest, _encrypt, _token_key, decrypt_access_token,
)
from modules.telemetry.rootline_ewelink_readback import read_current_device


DATABASE_URL = os.getenv("ROOTLINE_DISPOSABLE_POSTGRES_URL", "").strip()


@unittest.skipUnless(DATABASE_URL, "disposable ROOTLINE PostgreSQL URL is required")
class EWeLinkOAuthPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import psycopg
        migration = Path("supabase/migrations/202608060001_create_rootline_ewelink_oauth_vault.sql").read_text()
        rotation_migration = Path("supabase/migrations/202608130001_serialize_rootline_ewelink_refresh.sql").read_text()
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("do $$ begin create role anon; exception when duplicate_object then null; end $$")
            connection.execute("do $$ begin create role authenticated; exception when duplicate_object then null; end $$")
            connection.execute("create schema if not exists app_private")
            connection.execute("create table if not exists app_private.migration_log "
                               "(migration_id text primary key, description text not null, "
                               "applied_at timestamptz not null default now())")
            connection.execute(migration)
            connection.execute(rotation_migration)

    def setUp(self):
        import psycopg
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute("truncate app_private.rootline_ewelink_oauth_states")
            connection.execute("truncate app_private.rootline_ewelink_oauth_tokens")
            connection.execute("truncate app_private.rootline_ewelink_account_binding")

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

    def test_concurrent_first_callbacks_cannot_bind_different_accounts(self):
        now = datetime.now(timezone.utc)
        base = {"device_id": "100204e9bc", "region": "eu",
                "access_token_ciphertext": "encrypted-a", "refresh_token_ciphertext": "encrypted-r",
                "access_expires_at": now + timedelta(days=30),
                "refresh_expires_at": now + timedelta(days=60),
                "adapter_version": "rootline_ewelink_oauth_v1", "status_field_names": ["switches"],
                "created_at": now}
        items = [{**base, "token_binding_id": "ROOTLINE-EWELINK-A",
                  "provider_account_digest": "a" * 64, "response_digest": "b" * 64},
                 {**base, "token_binding_id": "ROOTLINE-EWELINK-B",
                  "provider_account_digest": "c" * 64, "response_digest": "d" * 64}]
        def append(item):
            try:
                return PostgresOAuthTokenStore(DATABASE_URL).append(item)
            except Exception:
                return False
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(append, items))
        self.assertEqual(results.count(True), 1)

    def test_rotated_ciphertext_reloads_in_fresh_store_and_reads_zero_command(self):
        now = datetime.now(timezone.utc)
        source = {"EWELINK_CLIENT_SECRET": "c" * 40, "EWELINK_OAUTH_STATE_SECRET": "s" * 40,
                  "EWELINK_CLIENT_ID": "client",
                  "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc", "EWELINK_READBACK_ENABLED": "true"}
        account = _digest("account")
        aad = f"eu|{account}|100204e9bc|{ADAPTER_VERSION}".encode()
        store = PostgresOAuthTokenStore(DATABASE_URL)
        store.append({"token_binding_id": "ROOTLINE-EWELINK-PG-ORIGINAL",
            "provider_account_digest": account, "device_id": "100204e9bc", "region": "eu",
            "access_token_ciphertext": _encrypt("expired", _token_key(source), aad),
            "refresh_token_ciphertext": _encrypt("refresh", _token_key(source), aad),
            "access_expires_at": now - timedelta(seconds=1),
            "refresh_expires_at": now + timedelta(days=30), "response_digest": "b" * 64,
            "adapter_version": ADAPTER_VERSION, "status_field_names": [], "created_at": now})
        calls = []
        def request(method, url, **kwargs):
            from urllib.parse import urlparse
            path = urlparse(url).path; calls.append((method, path))
            if path == "/v2/user/refresh": return {"at": "rotated-access", "rt": "rotated-refresh"}
            if path == "/v2/family": return {"currentFamilyId": "farm", "familyList": [{"id": "farm", "apikey": "account"}]}
            if path == "/v2/device/thing": return {"thingList": [{"itemType": 1, "itemData": {
                "deviceid": "100204e9bc", "apikey": "account", "online": True,
                "updatedAt": now.isoformat(), "params": {"fwVersion": "3.8.2",
                "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
                "pulses": [{"outlet": i, "pulse": "on", "width": 3600000} for i in range(4)],
                "configure": [{"outlet": i, "startup": "off"} for i in range(4)],
                "timers": [], "interlock": 0, "scenes": []}}}]}
            return {"params": {}}
        result = read_current_device(token_store=store, environ=source, http_request=request, now=now)
        fresh = PostgresOAuthTokenStore(DATABASE_URL)
        persisted = fresh.latest()
        self.assertNotIn("rotated-access", repr(persisted))
        self.assertNotIn("rotated-refresh", repr(persisted))
        result_after_restart = read_current_device(token_store=fresh, environ=dict(source),
            http_request=request, now=now + timedelta(seconds=1))
        self.assertTrue(result["token_refreshed"])
        self.assertFalse(result_after_restart["token_refreshed"])
        self.assertEqual(result_after_restart["provider_control_calls"], 0)
        self.assertEqual(calls.count(("POST", "/v2/user/refresh")), 1)

        probe = """
import json, os
from datetime import datetime, timezone
from modules.telemetry.rootline_ewelink_oauth import decrypt_access_token, decrypt_refresh_token
from modules.telemetry.rootline_ewelink_oauth_store import PostgresOAuthTokenStore
record = PostgresOAuthTokenStore(os.environ['ROOTLINE_DISPOSABLE_POSTGRES_URL']).latest()
source = json.loads(os.environ['ROOTLINE_EWELINK_TEST_SOURCE'])
print(json.dumps({
    'binding': record['token_binding_id'],
    'access': decrypt_access_token(record, source),
    'refresh': decrypt_refresh_token(record, source),
    'access_fresh': record['access_expires_at'] > datetime.now(timezone.utc),
}))
"""
        child_env = dict(os.environ)
        child_env["ROOTLINE_EWELINK_TEST_SOURCE"] = json.dumps(source)
        completed = subprocess.run([sys.executable, "-c", probe], cwd=str(Path.cwd()),
            env=child_env, check=True, capture_output=True, text=True)
        child = json.loads(completed.stdout)
        self.assertEqual(child["binding"], persisted["token_binding_id"])
        self.assertEqual((child["access"], child["refresh"]),
                         ("rotated-access", "rotated-refresh"))
        self.assertTrue(child["access_fresh"])

    def test_two_postgres_workers_cas_one_refresh_and_replay_has_zero_effect(self):
        now = datetime.now(timezone.utc)
        source = {"EWELINK_CLIENT_SECRET": "c" * 40, "EWELINK_OAUTH_STATE_SECRET": "s" * 40,
                  "EWELINK_CLIENT_ID": "client", "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc",
                  "EWELINK_READBACK_ENABLED": "true"}
        account = _digest("account")
        aad = f"eu|{account}|100204e9bc|{ADAPTER_VERSION}".encode()
        PostgresOAuthTokenStore(DATABASE_URL).append({
            "token_binding_id": "ROOTLINE-EWELINK-PG-CAS", "provider_account_digest": account,
            "device_id": "100204e9bc", "region": "eu",
            "access_token_ciphertext": _encrypt("expired", _token_key(source), aad),
            "refresh_token_ciphertext": _encrypt("refresh", _token_key(source), aad),
            "access_expires_at": now - timedelta(seconds=1),
            "refresh_expires_at": now + timedelta(days=30), "response_digest": "b" * 64,
            "adapter_version": ADAPTER_VERSION, "status_field_names": [], "created_at": now})
        calls = []; lock = threading.Lock()
        def request(method, url, **kwargs):
            from urllib.parse import urlparse
            path = urlparse(url).path
            with lock: calls.append((method, path))
            if path == "/v2/user/refresh": return {"at": "cas-access", "rt": "cas-refresh"}
            if path == "/v2/family": return {"currentFamilyId": "farm", "familyList": [{"id": "farm", "apikey": "account"}]}
            if path == "/v2/device/thing": return {"thingList": [{"itemType": 1, "itemData": {
                "deviceid": "100204e9bc", "apikey": "account", "online": True,
                "updatedAt": now.isoformat(), "params": {"fwVersion": "3.8.2",
                "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
                "pulses": [{"outlet": i, "pulse": "on", "width": 3600000} for i in range(4)],
                "configure": [{"outlet": i, "startup": "off"} for i in range(4)],
                "timers": [], "interlock": 0, "scenes": []}}}]}
            return {"params": {}}
        def read(_):
            return read_current_device(token_store=PostgresOAuthTokenStore(DATABASE_URL),
                environ=source, http_request=request, now=now)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(read, range(2)))
        replay = read_current_device(token_store=PostgresOAuthTokenStore(DATABASE_URL),
            environ=source, http_request=request, now=now + timedelta(seconds=1))
        self.assertEqual(calls.count(("POST", "/v2/user/refresh")), 1)
        # Both callers began from the expired predecessor and therefore report
        # that their read used the refreshed generation; CAS still permits only
        # one provider rotation and one durable successor.
        self.assertTrue(all(row["token_refreshed"] for row in results))
        import psycopg
        with psycopg.connect(DATABASE_URL) as connection:
            count, maximum = connection.execute(
                "select count(*),max(generation) from app_private.rootline_ewelink_oauth_tokens"
            ).fetchone()
        self.assertEqual((count, maximum), (2, 2))
        self.assertFalse(replay["token_refreshed"])
        self.assertTrue(all(row["provider_control_calls"] == 0 for row in results + [replay]))

    def test_provider_success_first_persist_failure_recovers_same_generation(self):
        class FailFirstInsertStore(PostgresOAuthTokenStore):
            failed = False
            @staticmethod
            def _insert_generation(cursor, item, json_module):
                if not FailFirstInsertStore.failed:
                    FailFirstInsertStore.failed = True
                    raise RuntimeError("simulated persistence failure after provider success")
                return PostgresOAuthTokenStore._insert_generation(cursor, item, json_module)
        now = datetime.now(timezone.utc)
        source = {"EWELINK_CLIENT_SECRET": "c" * 40, "EWELINK_OAUTH_STATE_SECRET": "s" * 40,
                  "EWELINK_CLIENT_ID": "client", "EWELINK_EXPECTED_DEVICE_ID": "100204e9bc",
                  "EWELINK_READBACK_ENABLED": "true"}
        account = _digest("account"); aad = f"eu|{account}|100204e9bc|{ADAPTER_VERSION}".encode()
        store = FailFirstInsertStore(DATABASE_URL)
        store.append({"token_binding_id": "ROOTLINE-EWELINK-PG-RECOVER",
            "provider_account_digest": account, "device_id": "100204e9bc", "region": "eu",
            "access_token_ciphertext": _encrypt("expired", _token_key(source), aad),
            "refresh_token_ciphertext": _encrypt("refresh", _token_key(source), aad),
            "access_expires_at": now - timedelta(seconds=1),
            "refresh_expires_at": now + timedelta(days=30), "response_digest": "b" * 64,
            "adapter_version": ADAPTER_VERSION, "status_field_names": [], "created_at": now})
        refresh_calls = []
        def request(method, url, **kwargs):
            from urllib.parse import urlparse
            path = urlparse(url).path
            if path == "/v2/user/refresh":
                refresh_calls.append(path); return {"at": "recovered-access", "rt": "recovered-refresh"}
            if path == "/v2/family": return {"currentFamilyId": "farm", "familyList": [{"id": "farm", "apikey": "account"}]}
            if path == "/v2/device/thing": return {"thingList": [{"itemType": 1, "itemData": {
                "deviceid": "100204e9bc", "apikey": "account", "online": True,
                "updatedAt": now.isoformat(), "params": {"fwVersion": "3.8.2",
                "switches": [{"outlet": i, "switch": "off"} for i in range(4)],
                "pulses": [{"outlet": i, "pulse": "on", "width": 3600000} for i in range(4)],
                "configure": [{"outlet": i, "startup": "off"} for i in range(4)],
                "timers": [], "interlock": 0, "scenes": []}}}]}
            return {"params": {}}
        result = read_current_device(token_store=store, environ=source,
            http_request=request, now=now)
        persisted = PostgresOAuthTokenStore(DATABASE_URL).latest()
        self.assertTrue(result["token_refreshed"])
        self.assertEqual(len(refresh_calls), 1)
        self.assertEqual(decrypt_access_token(persisted, source), "recovered-access")


if __name__ == "__main__":
    unittest.main()
