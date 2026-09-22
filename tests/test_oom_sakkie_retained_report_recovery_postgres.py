"""Actual retained-report SQL against disposable, isolated canonical rails."""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from modules.oom_sakkie import manager_case_sources as sources
from modules.oom_sakkie import herdmaster_retained_recovery_runtime as recovery
from modules.oom_sakkie.general_manager_worker import normalize_candidate
from tests.test_oom_sakkie_herdmaster_retained_recovery_runtime import report

URL = os.environ.get("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable PostgreSQL URL is required")
NOW = datetime(2026, 9, 22, tzinfo=timezone.utc)
OLD = NOW - timedelta(days=40)


class Cursor:
    def __init__(self, cursor, schema):
        self.cursor, self.schema = cursor, schema
    def execute(self, query, params=None):
        self.cursor.execute(query.replace("public.", self.schema + ".").replace(
            "app_private.", self.schema + "."), params)
        return self
    def __getattr__(self, name): return getattr(self.cursor, name)
    def __enter__(self): self.cursor.__enter__(); return self
    def __exit__(self, *args): return self.cursor.__exit__(*args)


class Connection:
    def __init__(self, connection, schema, read_only=False):
        self.connection, self.schema, self.read_only = connection, schema, read_only
    def cursor(self): return Cursor(self.connection.cursor(), self.schema)
    def __enter__(self):
        self.connection.__enter__()
        if self.read_only: self.connection.execute("set transaction read only")
        return self
    def __exit__(self, *args): return self.connection.__exit__(*args)


@pytest.fixture
def store(monkeypatch):
    parsed = urlsplit(URL)
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"} and "test" in parsed.path
    assert not parsed.query, "test connection must not inherit alternate libpq destinations"
    schema = "retained_reports_" + uuid4().hex
    migrations = Path(__file__).resolve().parents[1] / "supabase/migrations"
    def connect(read_only=False): return Connection(psycopg.connect(URL), schema, read_only)
    with psycopg.connect(URL) as db:
        db.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
    try:
        with connect() as db:
            with db.cursor() as cur:
                for role in ("anon", "authenticated", "service_role"):
                    cur.execute("do $$ begin if not exists(select 1 from pg_roles where rolname='" + role +
                        "') then create role " + role + "; end if; end $$")
                cur.execute("create table app_private.migration_log(migration_id text primary key,description text)")
                cur.execute("create table public.pigs(pig_id text primary key,tag_number text,pig_name text,status text,on_farm boolean)")
                cur.execute("create table public.pig_lifecycle_events(lifecycle_event_id text primary key)")
                cur.execute("create table public.litters(litter_id text primary key,sow_pig_id text,farrowing_date date,litter_status text)")
                cur.execute("create table public.litter_supersessions(superseded_litter_id text)")
                cur.execute("create table public.litter_cohort_dispositions(pig_id text)")
                for name in ("202607070001_create_sam_live_stock_conversation_review_events.sql",
                             "202608110001_create_oom_protected_action_claims.sql",
                             "202608160004_add_protected_delivery_lifecycle.sql",
                             "202608170002_create_oom_manager_case_runtime.sql"):
                    ddl = (migrations / name).read_text(encoding="utf-8")
                    ddl = ddl.replace("create schema if not exists app_private;", "")
                    cur.execute(ddl)
                ddl = (migrations / "202607300001_create_litter_supersession_rail.sql").read_text(encoding="utf-8")
                for view in ("current_canonical_pigs", "current_canonical_litters"):
                    cur.execute(re.search(r"create or replace view public\." + view + r" as.*?;", ddl, re.S)[0])
                cur.execute("insert into public.pigs values('P27','27','Synthetic pig','Active',true),('SOW-A','S-A','Linda','Active',true)")
        monkeypatch.setattr(recovery, "connect_bounded_read", lambda: connect(True))
        yield connect
    finally:
        with psycopg.connect(URL) as db:
            db.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(schema)))


def add_report(store, body, at=OLD):
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into public.sam_live_stock_conversation_review_events
            (review_event_id,event_source,review_json,created_at) values(%s,%s,%s,%s)""",
            (uuid4().hex, recovery.REPORT_SOURCE, Jsonb({"herdmaster_health_loss": body}), at))


def retain(store, key="herdmaster:retained-mortality:101", refs=None, status="exception"):
    refs = refs or ["provider_message:101", "pig:P27", "tag:27"]
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into app_private.oom_manager_cases
            (case_id,dedupe_key,specialist,urgency,status,evidence_digest,evidence_refs,
             summary,next_action,next_reassessment_at,generation)
            values(%s,%s,'HERDMASTER','urgent',%s,%s,%s,'synthetic','reassess',%s,1)""",
            (uuid4().hex, key, status, "0" * 64, Jsonb(refs), OLD))


def collect(store, now=NOW):
    return sources._retained_herd_report_recovery_candidates(now, connect=lambda: store(True))


def test_actual_age_query_keeps_only_exact_open_retained_reports_and_recent_intake(store):
    add_report(store, report()); retain(store)
    add_report(store, report("102", "UNTRACKED"))
    add_report(store, report("103", "NEW"), NOW - timedelta(days=1))
    add_report(store, report("104", "CLOSED"), NOW - timedelta(days=1))
    retain(store, "herdmaster:retained-mortality:104", ["provider_message:104", "pig:P27", "tag:27"], "completed")
    first = collect(store)
    assert {row["dedupe_key"] for row in first} == {
        "herdmaster:retained-mortality:101", "herdmaster:retained-mortality:103"}
    old = next(row for row in first if row["dedupe_key"].endswith(":101"))
    with store() as db, db.cursor() as cur:
        cur.execute("update app_private.oom_manager_cases set evidence_refs=%s where dedupe_key=%s",
                    (Jsonb(old["evidence_refs"]), old["dedupe_key"]))
    later = collect(store, NOW + timedelta(days=30))
    assert len(later) == 1 and later[0]["evidence_refs"] == old["evidence_refs"]
    assert normalize_candidate(later[0], now=NOW)["evidence_digest"] == normalize_candidate(old, now=NOW)["evidence_digest"]


@pytest.mark.parametrize("status", ["contained", "completed", "preview_correction_pending"])
def test_actual_latest_mission_query_sees_later_lifecycle_with_different_provider(store, status):
    add_report(store, report()); retain(store)
    add_report(store, report(provider="901", status=status), OLD + timedelta(days=1))
    assert collect(store) == []


@pytest.mark.parametrize("kind", ["principal_collision", "consumed", "superseded", "missing_member"])
def test_actual_related_identity_queries_contain_ambiguous_or_replaced_reports(store, kind):
    add_report(store, report()); retain(store)
    if kind == "principal_collision":
        add_report(store, report(owner_user_id="99", chat_id="99"))
    elif kind == "missing_member":
        with store() as db, db.cursor() as cur:
            cur.execute("update app_private.oom_manager_cases set evidence_refs=%s",
                        (Jsonb(["provider_message:101", "provider_message:102", "pig:P27", "tag:27"]),))
    else:
        link = ({"consumed_context_missions": ["REPORT-101"]} if kind == "consumed" else
                {"superseded_duplicate_bindings": [{"mission_id": "REPORT-101", "provider_message_id": "101", "tag_number": "27"}]})
        add_report(store, report("901", "CORRECTION", **link), OLD + timedelta(days=1))
    assert collect(store) == []


@pytest.mark.parametrize("status", ["cancelled", "completed", "active", "expired"])
def test_actual_claim_query_matches_original_mission_after_provider_changes(store, status):
    add_report(store, report()); retain(store)
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into app_private.oom_protected_action_claims
            (callback_token,action_kind,owner_user_id,private_chat_id,mission_id,
             provider_message_id,preview_digest,evidence_generation,preview_payload,status,expires_at)
            values('SYNTHETIC','mortality','42','42','REPORT-101','901','D','G','{}',%s,%s)""",
            (status, OLD))
    assert collect(store) == []
    with store(True) as db, db.cursor() as cur:
        cur.execute("select count(*) from app_private.oom_protected_action_claims")
        assert cur.fetchone()[0] == 1


@pytest.mark.parametrize("litter_date", [None, "2026-09-01", "2026-08-01"])
def test_actual_preview_query_never_substitutes_newer_litter_for_retained_incident(store, monkeypatch, litter_date):
    first = report("201", "REPORT-201", owner_text_verbatim="Linda 2 kleintjies dood")
    second = report("202", "REPORT-202", owner_text_verbatim="Linda kleintjies dood op 19 Aug",
        preview={"evaluator": {"identity": {"resolved": True, "pig_id": "SOW-A"}}})
    add_report(store, first); add_report(store, second)
    key = "herdmaster:retained-litter-loss:201:2026-08-19"
    retain(store, key, ["provider_message:201", "provider_message:202", "incident_date:2026-08-19"])
    if litter_date:
        with store() as db, db.cursor() as cur:
            cur.execute("insert into public.litters values('NEW-LITTER','SOW-A',%s,'Active')", (litter_date,))
    def forbidden(*args, **kwargs): raise AssertionError("no claim, farm mutation or provider effect")
    monkeypatch.setattr("modules.oom_sakkie.protected_action_claims.create_claim", forbidden)
    dry_calls = []
    def dry_selection(*args, **kwargs):
        assert kwargs["dry_run"] is True
        dry_calls.append((args, kwargs))
        return {"success": False, "errors": ["Exact selection remains unresolved"]}, 409
    monkeypatch.setattr("modules.pig_weights.pig_weights_service.mark_litter_piglets_dead", dry_selection)
    case = collect(store)[0]
    for _ in range(2):
        result = recovery.build_retained_protected_preview(case)
        expected = ("retained_litter_loss_selection_required" if litter_date == "2026-08-01"
                    else "retained_litter_loss_active_litter_unproven")
        assert result["status"] == expected
        assert result["telegram_sends"] == 0 and result["writes_farm_data"] is False
    assert len(dry_calls) == (2 if litter_date == "2026-08-01" else 0)


def test_actual_bounded_query_rejects_partial_history(store):
    retain(store)
    with store() as db, db.cursor() as cur:
        for index in range(recovery.REPORT_READ_LIMIT + 1):
            cur.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,event_source,review_json,created_at) values(%s,%s,%s,%s)""",
                (str(index), recovery.REPORT_SOURCE, Jsonb({"herdmaster_health_loss": report()}), OLD))
    with pytest.raises(ValueError, match="retained_report_read_bound_exceeded"):
        collect(store)


def test_actual_current_canonical_identity_excludes_superseded_pig(store):
    add_report(store, report()); retain(store)
    assert len(collect(store)) == 1
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.litter_cohort_dispositions values('P27')")
    assert collect(store) == []
