import hashlib
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from modules.auth.owner_access import configure_owner_access
from modules.beacon.creative_providers import (
    ALLOWED_CREATIVE_PROVIDERS,
    evaluate_disabled_provider,
)
from modules.beacon.creative_studio import (
    build_creative_job_contract,
    create_mock_creative_job,
    record_creative_review,
)
from modules.sales import sales_transaction_routes


SOURCE_HASH = hashlib.sha256(b"approved source bytes").hexdigest()
OWNER_ENV = {
    "OWNER_ACCESS_ENABLED": "1",
    "OWNER_ACCESS_ALLOW_LOCAL_DEV": "0",
    "OWNER_READ_TOKEN": "read-owner-token-1234567890abcdef",
    "OWNER_ADMIN_TOKEN": "admin-owner-token-1234567890abcdef",
    "OWNER_SESSION_SECRET": "owner-session-secret-1234567890abcdef",
}


def creative_payload(provider="elevenlabs"):
    return {
        "provider": provider,
        "prompt": "  Keep exact spacing.\nSecond line.  ",
        "parameters": {"voice": "mock", "seed": 7},
        "source_assets": [{"asset_id": "BEACON-ASSET-SOURCE", "content_sha256": SOURCE_HASH}],
        "estimated_cost": "12.50",
        "cost_currency": "ZAR",
        "cost_estimate_source": "manual provider pricing snapshot",
        "idempotency_key": "owner-evaluation-1",
    }


class FakeCursor:
    def __init__(self, source_row=("BEACON-ASSET-SOURCE", SOURCE_HASH, "server_computed_on_upload", "approved_public_use"), duplicate=False, duplicate_request_sha256=None):
        self.source_row = source_row
        self.duplicate = duplicate
        self.duplicate_request_sha256 = duplicate_request_sha256
        self.rowcount = 1
        self.statements = []
        self._fetch_row = source_row

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement, params=None):
        normalized = " ".join(statement.split())
        self.statements.append((normalized, params))
        if "from public.beacon_media_assets a where a.asset_id" in normalized:
            self.rowcount = 1 if self.source_row else 0
            self._fetch_row = self.source_row
        elif "insert into public.beacon_creative_jobs" in normalized:
            self.rowcount = 0 if self.duplicate else 1
        elif "select request_sha256 from public.beacon_creative_jobs" in normalized:
            self.rowcount = 1 if self.duplicate_request_sha256 else 0
            self._fetch_row = ((self.duplicate_request_sha256,) if self.duplicate_request_sha256 else None)
        else:
            self.rowcount = 1

    def fetchone(self):
        return self._fetch_row


class FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self._cursor


def connector(cursor):
    def connect(_database_url, connect_timeout=10):
        return FakeConnection(cursor)
    return connect


def mock_uploader(bucket, path, data, content_type, environ=None):
    if bucket != "beacon-raw-intake" or not path.endswith(".json") or not data or content_type != "application/json":
        return {"success": False, "status": "invalid_mock_upload"}, 400
    return {"success": True, "status": "supabase_storage_upload_complete"}, 201


class BeaconCreativeProviderTests(unittest.TestCase):
    def test_only_named_candidates_are_allowlisted_and_deterministic(self):
        self.assertEqual(ALLOWED_CREATIVE_PROVIDERS, {"elevenlabs", "happy_horse_1_0"})
        for provider in sorted(ALLOWED_CREATIVE_PROVIDERS):
            first = evaluate_disabled_provider(provider, "Exact prompt", {"seed": 4}, [{"asset_id": "A", "content_sha256": SOURCE_HASH}])
            second = evaluate_disabled_provider(provider, "Exact prompt", {"seed": 4}, [{"asset_id": "A", "content_sha256": SOURCE_HASH}])
            self.assertEqual(first, second)
            self.assertFalse(first["provider_enabled"])
            self.assertFalse(first["network_enabled"])
            self.assertFalse(first["credential_access"])
            self.assertFalse(first["source_transfer"])
            self.assertEqual(first["actual_cost"], 0)

        with self.assertRaisesRegex(ValueError, "creative_provider_not_allowlisted"):
            evaluate_disabled_provider("unknown", "prompt", {}, [{"asset_id": "A"}])

    def test_adapter_source_contains_no_network_sdk_or_credential_access(self):
        source = Path("modules/beacon/creative_providers.py").read_text(encoding="utf-8")
        for forbidden in ("urllib", "requests", "httpx", "socket", "psycopg", "os.environ", "api_key", "secret"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source.lower())


class BeaconCreativeStudioTests(unittest.TestCase):
    def test_contract_preserves_exact_prompt_and_hashes_canonical_parameters(self):
        contract = build_creative_job_contract(creative_payload())
        self.assertEqual(contract["exact_prompt"], creative_payload()["prompt"])
        self.assertEqual(contract["prompt_sha256"], hashlib.sha256(creative_payload()["prompt"].encode()).hexdigest())
        reordered = creative_payload()
        reordered["parameters"] = {"seed": 7, "voice": "mock"}
        self.assertEqual(contract["parameters_sha256"], build_creative_job_contract(reordered)["parameters_sha256"])

    def test_contract_rejects_malformed_prompt_parameters_and_sources(self):
        cases = [
            ({**creative_payload(), "prompt": "   "}, "exact_prompt_required"),
            ({**creative_payload(), "parameters": []}, "creative_parameters_must_be_object"),
            ({**creative_payload(), "source_assets": []}, "approved_source_assets_required"),
            ({**creative_payload(), "source_assets": [{"asset_id": "A", "content_sha256": "bad"}]}, "source_asset_id_and_sha256_required"),
        ]
        for payload, error in cases:
            with self.subTest(error=error), self.assertRaisesRegex(ValueError, error):
                build_creative_job_contract(payload)

    def test_missing_unapproved_and_tampered_sources_fail_closed(self):
        rows = [
            (None, "source_asset_not_found"),
            (("BEACON-ASSET-SOURCE", SOURCE_HASH, "server_computed_on_upload", "review_note"), "source_asset_owner_approval_required"),
            (("BEACON-ASSET-SOURCE", "0" * 64, "server_computed_on_upload", "approved_public_use"), "source_asset_integrity_failed"),
            (("BEACON-ASSET-SOURCE", SOURCE_HASH, "browser_supplied", "approved_public_use"), "source_asset_hash_provenance_untrusted"),
        ]
        for row, expected in rows:
            with self.subTest(expected=expected):
                result, status = create_mock_creative_job(
                    creative_payload(), "authenticated_owner_admin", database_url="postgresql://mock",
                    connect=connector(FakeCursor(source_row=row)),
                )
                self.assertEqual(status, 409)
                self.assertEqual(result["status"], expected)

    def test_persistence_is_structured_idempotent_zero_spend_and_private(self):
        cursor = FakeCursor()
        result, status = create_mock_creative_job(
            creative_payload(), "authenticated_owner_admin", database_url="postgresql://mock",
            connect=connector(cursor), uploader=mock_uploader,
        )
        self.assertEqual(status, 201)
        self.assertEqual(result["variant"]["storage_bucket"], "beacon-raw-intake")
        self.assertEqual(result["variant"]["approval_status"], "needs_review")
        self.assertFalse(result["variant"]["public_use_approved"])
        self.assertEqual(result["actual_cost"], 0)
        sql = "\n".join(statement for statement, _params in cursor.statements)
        for table in ("beacon_creative_jobs", "beacon_creative_job_sources", "beacon_creative_provider_attempts", "beacon_creative_cost_events", "beacon_media_assets", "beacon_creative_variants"):
            self.assertIn("insert into public." + table, sql)

        request_sha256 = build_creative_job_contract(creative_payload())["request_sha256"]
        duplicate, duplicate_status = create_mock_creative_job(
            creative_payload(), "authenticated_owner_admin", database_url="postgresql://mock",
            connect=connector(FakeCursor(duplicate=True, duplicate_request_sha256=request_sha256)), uploader=mock_uploader,
        )
        self.assertEqual(duplicate_status, 200)
        self.assertEqual(duplicate["created_count"], 0)

        conflict, conflict_status = create_mock_creative_job(
            creative_payload(), "authenticated_owner_admin", database_url="postgresql://mock",
            connect=connector(FakeCursor(duplicate=True, duplicate_request_sha256="0" * 64)), uploader=mock_uploader,
        )
        self.assertEqual(conflict_status, 409)
        self.assertEqual(conflict["status"], "creative_idempotency_key_conflict")

    def test_reviews_remain_distinct_and_never_execute(self):
        for review_type in ("brand", "privacy", "safety", "animal_product_fidelity", "provider_disclosure", "evaluation", "owner_public_use"):
            cursor = FakeCursor()
            result, status = record_creative_review(
                "BEACON-CREATIVE-1", {"review_type": review_type, "decision": "approved", "recorded_by": "browser spoof"},
                "authenticated_owner_admin", database_url="postgresql://mock", connect=connector(cursor),
            )
            self.assertEqual(status, 201)
            self.assertEqual(result["review_type"], review_type)
            self.assertEqual(result["recorded_by"], "authenticated_owner_admin")
            self.assertFalse(result["approval_executes_action"])
            self.assertFalse(result["provider_enabled"])
            self.assertFalse(result["posts_publicly"])
            self.assertFalse(result["spends_money"])

    def test_migration_defines_append_only_contract_and_zero_authority(self):
        migration = Path("supabase/migrations/202607130002_create_beacon_creative_studio.sql").read_text(encoding="utf-8")
        for table in ("beacon_creative_jobs", "beacon_creative_job_sources", "beacon_creative_provider_attempts", "beacon_creative_cost_events", "beacon_creative_variants", "beacon_creative_review_events"):
            self.assertIn("create table if not exists public." + table, migration)
        self.assertIn("actual_cost = 0", migration)
        self.assertIn("campaign_selectable = false", migration)
        self.assertIn("Beacon Creative Studio records are append-only", migration)


class BeaconCreativeStudioRouteTests(unittest.TestCase):
    def setUp(self):
        app.config.update(TESTING=True)
        self.client = app.test_client()

    def _login(self, token):
        return self.client.post(
            "/owner/login", data={"owner_token": token, "next": "/sales/beacon-media"},
            environ_base={"REMOTE_ADDR": "203.0.113.10"},
        )

    def test_private_page_and_read_api_deny_anonymous(self):
        with patch.dict(os.environ, OWNER_ENV, clear=False):
            configure_owner_access(app)
            page = self.client.get("/sales/beacon-media", environ_base={"REMOTE_ADDR": "203.0.113.10"})
            api = self.client.get("/api/beacon/creative-studio/providers", environ_base={"REMOTE_ADDR": "203.0.113.10"})
            policy = self.client.get("/api/beacon/media-policy", environ_base={"REMOTE_ADDR": "203.0.113.10"})
            assets_read = self.client.get("/api/beacon/media-assets", environ_base={"REMOTE_ADDR": "203.0.113.10"})
            assets_write = self.client.post("/api/beacon/media-assets", json={}, environ_base={"REMOTE_ADDR": "203.0.113.10"})
            asset_event = self.client.post(
                "/api/beacon/media-assets/BEACON-ASSET-1/events", json={},
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
        self.assertEqual(page.status_code, 302)
        self.assertEqual(api.status_code, 403)
        self.assertEqual(policy.status_code, 403)
        self.assertEqual(assets_read.status_code, 403)
        self.assertEqual(assets_write.status_code, 403)
        self.assertEqual(asset_event.status_code, 403)

    def test_read_role_cannot_write_and_admin_actor_is_server_bound(self):
        with patch.dict(os.environ, OWNER_ENV, clear=False):
            configure_owner_access(app)
            self._login(OWNER_ENV["OWNER_READ_TOKEN"])
            denied = self.client.post(
                "/api/beacon/creative-studio/jobs", json=creative_payload(),
                environ_base={"REMOTE_ADDR": "203.0.113.10"},
            )
            self.client.post("/owner/logout", environ_base={"REMOTE_ADDR": "203.0.113.10"})
            self._login(OWNER_ENV["OWNER_ADMIN_TOKEN"])
            with patch.object(sales_transaction_routes, "create_mock_creative_job", return_value=({"success": True}, 201)) as create:
                allowed = self.client.post(
                    "/api/beacon/creative-studio/jobs", json={**creative_payload(), "recorded_by": "spoofed"},
                    environ_base={"REMOTE_ADDR": "203.0.113.10"},
                )
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 201)
        self.assertEqual(create.call_args.kwargs["recorded_by"], "authenticated_owner_admin")


if __name__ == "__main__":
    unittest.main()
