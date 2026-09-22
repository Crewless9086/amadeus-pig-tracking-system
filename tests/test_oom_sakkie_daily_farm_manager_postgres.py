"""Disposable PostgreSQL proof for the existing daily append-only read/write rail."""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from modules.oom_sakkie import daily_farm_manager as daily
from modules.sales import sam_live_stock_launch_control as sam

URL = os.environ.get("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable PostgreSQL URL is required")


class _Cursor:
    def __init__(self, cursor, schema):
        self.cursor, self.schema = cursor, schema

    def execute(self, query, params=None):
        # Run the production SQL against a per-test schema with the actual DDL.
        self.cursor.execute(query.replace("public.", f'"{self.schema}".'), params)
        return self

    def __getattr__(self, name):
        return getattr(self.cursor, name)

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)


class _Connection:
    def __init__(self, connection, schema):
        self.connection, self.schema = connection, schema

    def cursor(self):
        return _Cursor(self.connection.cursor(), self.schema)

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)


@pytest.fixture
def isolated_daily_store(monkeypatch):
    schema = "daily_recovery_" + uuid4().hex
    migration = Path(__file__).resolve().parents[1] / "supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql"
    with psycopg.connect(URL) as connection:
        connection.execute(sql.SQL("create schema {}").format(sql.Identifier(schema)))
        connection.execute(migration.read_text(encoding="utf-8").replace("public.", f'"{schema}".'))
    def connect():
        return _Connection(psycopg.connect(URL), schema)
    original_record = sam.record_sam_live_stock_review_event
    def record(event, **_kwargs):
        return original_record(event, database_url=URL, connect_factory=connect)
    monkeypatch.setattr(daily, "connect_bounded_read", connect)
    monkeypatch.setattr(daily, "_load_answered_questions", lambda _binding: ())
    monkeypatch.setattr(sam, "record_sam_live_stock_review_event", record)
    try:
        yield connect, record
    finally:
        with psycopg.connect(URL) as connection:
            connection.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(schema)))


@pytest.mark.parametrize("suffix,foreign_prefix,excluded", [
    (":GENERATION:" + "A" * 20 + ":OUTCOME", False, True),
    (":DELIVERY:OUTCOME", False, False),
    (":GENERATION:" + "A" * 19 + ":OUTCOME", False, False),
    (":GENERATION:" + "A" * 20 + ":OUTCOME:EXTRA", False, False),
    (":GENERATION:" + "A" * 20 + ":OUTCOME", True, False),
])
def test_real_selector_excludes_only_exact_owned_legacy_replacement_failure(
        isolated_daily_store, suffix, foreign_prefix, excluded):
    connect, _record = isolated_daily_store
    identity = "OOM-DAILY-FARM-MANAGER-2026-09-22"
    projection = daily._owner_projection_identity(identity, "42", "42")
    failure_id = (daily._owner_projection_identity(identity, "99", "99")
                  if foreign_prefix else projection) + suffix
    confirmed = {"daily_identity": identity, "owner_user_id": "42", "chat_id": "42",
        "status": "presented", "material_digest": "A", "telegram_message_id": "700"}
    failure = {**confirmed, "status": "provider_ambiguous", "material_digest": "B"}
    failure.pop("telegram_message_id")
    with connect() as connection:
        with connection.cursor() as cursor:
            for event_id, body, offset in ((projection + ":DELIVERY:OUTCOME", confirmed, 0),
                                          (failure_id, failure, 1)):
                # The initial-failure case uses its normal identity; the prior
                # confirmed evidence has a distinct append-only receipt.
                if offset == 0:
                    event_id = projection + ":DELIVERY:PRESENTED"
                cursor.execute("""insert into public.sam_live_stock_conversation_review_events
                    (review_event_id,event_source,review_json,created_at)
                    values(%s,%s,%s,%s)""", (event_id, daily.EVENT_SOURCE,
                        Jsonb({"daily_farm_manager": body}),
                        datetime(2026, 9, 22, tzinfo=timezone.utc) + timedelta(seconds=offset)))
            cursor.execute("""insert into public.sam_live_stock_conversation_review_events
                (review_event_id,event_source,review_json,created_at) values(%s,%s,%s,%s)""",
                ("FOREIGN-OWNER", daily.EVENT_SOURCE, Jsonb({"daily_farm_manager": {
                    **failure, "owner_user_id": "99", "chat_id": "99"}}),
                    datetime(2026, 9, 22, tzinfo=timezone.utc) + timedelta(seconds=2)))
    assert daily._load_daily(identity, {"owner_user_id": "42", "chat_id": "42"}) == (
        confirmed if excluded else failure)


def test_real_daily_store_restart_recovers_legacy_failure_without_mutating_history(
        isolated_daily_store, monkeypatch):
    from tests.test_oom_sakkie_daily_farm_manager import _daily_family_transition_harness
    connect, record = isolated_daily_store
    real_daily_store = daily.daily_farm_manager_store
    state = _daily_family_transition_harness(monkeypatch)
    # Keep the actual default-store identity and actual SQL, rather than the
    # custom-store duplicate-claim shortcut. Family calls use inert providers.
    monkeypatch.setattr(daily, "daily_farm_manager_store", real_daily_store)
    assert state.run("A")["success"]
    reject_presented = [True]
    def interrupted_record(event, **kwargs):
        body = event.get("review_json", {}).get("daily_farm_manager", {})
        if body.get("status") == "presented" and reject_presented[0]:
            reject_presented[0] = False
            return {"success": False, "created": False}, 503
        return record(event, **kwargs)
    monkeypatch.setattr(sam, "record_sam_live_stock_review_event", interrupted_record)
    failed = state.run("B")
    assert not failed["success"] and len(state.sends) == 2
    identity, digest = failed["daily_identity"], failed["material_digest"]
    projection = daily._owner_projection_identity(identity, "42", "42")
    legacy_id = projection + ":GENERATION:" + digest[:20].upper() + ":OUTCOME"
    legacy_body = {"daily_identity": identity, "owner_user_id": "42", "chat_id": "42",
        "status": "provider_ambiguous", "material_digest": digest}
    assert real_daily_store("record_daily", legacy_id, legacy_body)["success"]
    before = daily._load_daily(identity, {"owner_user_id": "42", "chat_id": "42"})
    assert before["status"] == "presented" and before["material_digest"] != digest
    recovered = state.run("B")
    assert recovered["success"] and recovered["telegram_sends"] == 0
    assert len(state.sends) == 2 and len(state.deletes) == 1
    assert daily._load_daily(identity, {"owner_user_id": "42", "chat_id": "42"})["material_digest"] == digest
    assert state.run("B")["status"] == "daily_manager_unchanged_silent"
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""select review_json->'daily_farm_manager'
                from public.sam_live_stock_conversation_review_events where review_event_id=%s""",
                (legacy_id,))
            persisted = cursor.fetchone()[0]
    assert persisted["status"] == "provider_ambiguous"
    assert persisted["material_digest"] == digest
    with pytest.raises(psycopg.errors.RaiseException, match="append-only"):
        with connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""update public.sam_live_stock_conversation_review_events
                    set review_json='{}'::jsonb where review_event_id=%s""", (legacy_id,))
