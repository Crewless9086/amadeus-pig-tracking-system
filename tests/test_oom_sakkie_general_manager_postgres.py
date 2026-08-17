import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest

from modules.oom_sakkie.general_manager_worker import PostgresManagerCaseStore


URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="disposable PostgreSQL URL is required")


def connect():
    return psycopg.connect(URL)


@pytest.fixture(scope="module", autouse=True)
def exact_migration():
    with connect() as db:
        db.execute("create schema if not exists app_private")
        db.execute("""create table if not exists app_private.migration_log(
            migration_id text primary key,description text not null)""")
        for role in ("anon", "authenticated"):
            db.execute("do $block$ begin execute 'create role %s'; exception when duplicate_object then null; end $block$" % role)
    path = Path(__file__).parents[1] / "supabase" / "migrations" / "202608170002_create_oom_manager_case_runtime.sql"
    with connect() as db:
        db.execute(path.read_text(encoding="utf-8"))


def candidate(ref="event:one", due=None):
    return {"dedupe_key": "rootline:current-plan", "specialist": "ROOTLINE",
        "urgency": "urgent", "evidence_refs": [ref],
        "unknowns": ["delivered_current_irrigation_plan"],
        "summary": "Current irrigation plan is contained.",
        "next_action": "Delegate to ROOTLINE and retain ownership.",
        "next_reassessment_at": (due or datetime.now(timezone.utc)).isoformat()}


def test_exact_replay_is_one_case_and_delivery_is_not_duplicated():
    now = datetime.now(timezone.utc)
    store = PostgresManagerCaseStore(connect_factory=connect)
    sends = []
    deliver = lambda case: (sends.append(case["case_id"]) or {
        "success": True, "status": "delivery_confirmed", "delivery_confirmed": True})
    first = store.run_cycle([candidate(due=now)], now=now, source_revision="test", deliver=deliver)
    second = store.run_cycle([candidate(due=now)], now=now + timedelta(seconds=1),
        source_revision="test", deliver=deliver)
    assert first["candidates_created"] == 1 and first["deliveries_confirmed"] == 1
    assert second["candidate_replays"] == 1 and second["deliveries_confirmed"] == 0
    assert sends and len(sends) == 1
    with connect() as db:
        assert db.execute("select count(*) from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()[0] == 1


def test_changed_evidence_advances_generation_and_append_only_events_reject_mutation():
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:two", now)], now=now, source_revision="test")
    assert result["candidates_changed"] == 1
    with connect() as db:
        generation = db.execute("select generation from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()[0]
        assert generation == 2
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute("delete from app_private.oom_manager_case_events where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key='rootline:current-plan')")


def test_expired_lease_resumes_after_restart():
    now = datetime.now(timezone.utc) + timedelta(minutes=2)
    with connect() as db:
        db.execute("""update app_private.oom_manager_cases set status='delegated',
            lease_until=%s,next_reassessment_at=%s where dedupe_key='rootline:current-plan'""",
            (now - timedelta(seconds=1), now - timedelta(seconds=1)))
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:two", now)], now=now, source_revision="test")
    assert result["candidate_replays"] == 1
    assert result["cases_claimed"] == 1
    with connect() as db:
        row = db.execute("select status,lease_until,next_reassessment_at from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()
        assert row[0] == "waiting_reassessment" and row[1] is None
        assert row[2] == now - timedelta(seconds=1)
