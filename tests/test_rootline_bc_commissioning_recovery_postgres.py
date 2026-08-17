import json, os
from pathlib import Path

import psycopg
import pytest


URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="disposable PostgreSQL URL is required")
ROOT = Path(__file__).parents[1]


def test_exact_historical_bc_acceptance_advances_commissioning_without_authority():
    with psycopg.connect(URL) as db:
        db.execute("create extension if not exists pgcrypto")
        db.execute("create schema if not exists app_private")
        db.execute("""create table if not exists app_private.migration_log(
            migration_id text primary key,description text not null)""")
        db.execute("""create table if not exists public.sam_live_stock_conversation_review_events(
            review_event_id text primary key,event_source text not null,
            review_json jsonb not null,created_at timestamptz default now())""")
        for role in ("anon", "authenticated"):
            db.execute("do $block$ begin execute 'create role %s'; exception when duplicate_object then null; end $block$" % role)
        db.execute((ROOT / "supabase/migrations/202608170001_add_rootline_device_registry.sql").read_text())
        db.execute((ROOT / "supabase/migrations/202608170003_seed_rootline_operational_devices.sql").read_text())
        observations = [{"zone_id": "B12345", "water_flow": "normal",
            "execution_id": "ROOTLINE-EXECUTION-8CF9AD2989F15CC5BDC696AE",
            "stopped_flow": "normal", "shutdown_verified": True,
            "physically_off_now": True, "provider_start_state": "ON",
            "provider_shutdown_state": "OFF", "verified_runtime_seconds": 3599},
           {"zone_id": "C12345", "water_flow": "normal",
            "execution_id": "ROOTLINE-EXECUTION-79A473B14C98D5E58B9DD2D5",
            "stopped_flow": "normal", "shutdown_verified": True,
            "physically_off_now": True, "provider_start_state": "ON",
            "provider_shutdown_state": "OFF", "verified_runtime_seconds": 3599}]
        payload = {"action": "record_acceptance",
            "acceptance_id": "ROOTLINE-PHYSICAL-3ACCC82F844FA65D5FD3E6BD",
            "observed_at": "2026-08-15T15:24:59.004604+00:00",
            "observations": observations}
        db.execute("""insert into public.sam_live_stock_conversation_review_events(
            review_event_id,event_source,review_json) values(%s,%s,%s::jsonb)""",
            ("ACCEPT", "rootline_physical_acceptance",
             json.dumps({"rootline_physical_acceptance": payload})))
        db.execute((ROOT / "supabase/migrations/202608170004_recover_rootline_bc_commissioning_evidence.sql").read_text())
        rows = db.execute("""select commissioning_stage,registry_generation,
            standing_authority_id,device_record->>'standing_authority'
            from app_private.rootline_device_registry
            where device_key like 'ifttt_ewelink:ewelink_owner_account:100204e9bc:%'
            order by device_key""").fetchall()
        assert rows == [("supervised", 2, None, "false"),
                        ("supervised", 2, None, "false")]
        assert db.execute("select count(*) from app_private.rootline_device_commissioning_evidence").fetchone()[0] == 2
        assert db.execute("select count(*) from app_private.rootline_standing_authorities").fetchone()[0] == 0
