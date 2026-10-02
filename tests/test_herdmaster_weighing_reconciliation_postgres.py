"""Execute production weighing SELECTs and manager fences in isolated schemas."""
from datetime import timedelta
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import time

import psycopg
import pytest

from modules.pig_weights.herdmaster_daily_manager_evidence import load_daily_manager_evidence
from modules.oom_sakkie.general_manager_worker import PostgresManagerCaseStore, normalize_candidate
from tests.test_oom_sakkie_retained_report_recovery_postgres import URL, store, Cursor
from tests.test_herdmaster_weighing_reconciliation import TODAY, NOW, candidate

pytestmark = pytest.mark.skipif(not URL, reason="explicit isolated PostgreSQL URL required")


@pytest.fixture
def weighing_store(store):
    with store() as db, db.cursor() as cur:
        cur.execute("alter table public.pigs add column animal_type text, add column purpose text")
        cur.execute("create or replace view public.current_canonical_pigs as select * from public.pigs")
        cur.execute("create table public.pig_weight_events(weight_event_id text primary key,pig_id text,weight_date date,weight_kg numeric)")
        cur.execute("""create table public.sales_transactions(sale_id text primary key,
            sale_status text,sale_stream text,sale_date timestamptz,updated_at timestamptz)""")
        cur.execute("""create table public.sales_transaction_items(sale_item_id text primary key,
            sale_id text references public.sales_transactions,pig_id text,tag_number text,
            order_line_id text,updated_at timestamptz)""")
        cur.execute("create table public.orders(order_id text primary key,order_status text,updated_at timestamptz)")
        cur.execute("""create table public.order_lines(order_line_id text primary key,order_id text references public.orders,
            pig_id text,tag_number text,line_status text,reserved_status text,updated_at timestamptz)""")
        cur.execute("""alter table public.pig_active_outlets add column outlet_assignment_id text,
            add column outlet_type text,add column source_record_id text,add column created_at timestamptz""")
        cur.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm,animal_type,purpose)
            values('PIG-SYNTHETIC-1','T1','Synthetic animal','Active',true,'Grower','Grow_Out')""")
    return store


def load(store):
    return load_daily_manager_evidence(analysis_date=TODAY, database_url=URL,
        connect=lambda *_a, **_kw: store(), include_mortality=False)


def row(packet, pig_id="PIG-SYNTHETIC-1"):
    return next(row for row in packet["weight"]["reconciliation"]["rows"] if row["pig_id"] == pig_id)


@pytest.mark.parametrize("parent,tag", [("Completed", "T1"), ("Completed", "OLD-TAG"),
                                     ("Cancelled", "OLD-TAG")])
def test_real_snapshot_checks_cancelled_completed_parent_orders_without_inventing_exit(weighing_store, parent, tag):
    store = weighing_store
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.orders values('O1',%s,%s)", (parent, NOW))
        cur.execute("insert into public.order_lines values('OL1','O1','PIG-SYNTHETIC-1',%s,'Cancelled','Not_Reserved',%s)", (tag, NOW))
        cur.execute("insert into public.pig_weight_events values('W1','PIG-SYNTHETIC-1','2026-10-01',42)")
    first, second = load(store), load(store)
    assert first["material_digest"] == second["material_digest"]
    assert first["weight"]["current_snapshot"]["covered"] == 0
    assert row(first)["state"] == "current_on_farm"
    assert row(first)["latest_weight"]["kg"] == 42
    assert row(first)["sources"]["orders"][0]["order_line_id"] == "OL1"
    assert row(first)["sources"]["orders"][0]["tag_number"] == tag
    assert row(first)["reasons"] == []
    assert first["weight"]["individual_weighing_due_now"] == []
    with store() as db, db.cursor() as cur:
        for table in ("pig_lifecycle_events", "oom_protected_action_claims", "oom_manager_cases"):
            cur.execute("select count(*) from " + ("app_private." if table.startswith("oom_") else "public.") + table)
            assert cur.fetchone()[0] == 0


def test_real_schema_does_not_claim_support_for_legacy_individual_due_events(weighing_store):
    store = weighing_store
    with pytest.raises(psycopg.errors.CheckViolation):
        with store() as db, db.cursor() as cur:
            cur.execute("""insert into public.pig_lifecycle_events(lifecycle_event_id,pig_id,lifecycle_event_type,
                effective_at,actor_reference,source_system,source_reference,idempotency_key)
                values('DUE','PIG-SYNTHETIC-1','individual_weighing_due','2026-10-01T06:00:00Z',
                'synthetic','system','synthetic','synthetic-due')""")
    first = load(store)
    assert first["weight"]["individual_weighing_due_now"] == []
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.pig_weight_events values('W1','PIG-SYNTHETIC-1','2026-10-01',42),('W2','PIG-SYNTHETIC-1','2026-10-01',52)")
    second = load(store)
    assert second["weight"]["individual_weighing_due_now"] == []
    assert second["weight"]["individual_schedule_sources"] == []
    assert row(second)["latest_weight"] is None and "latest_weight_conflict" in row(second)["reasons"]
    assert second["material_digest"] != first["material_digest"]


def test_real_query_reservation_and_wrong_sale_identity_contain_without_new_task(weighing_store):
    store = weighing_store
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.orders values('O1','Approved',%s)", (NOW,))
        cur.execute("insert into public.order_lines values('OL1','O1','PIG-SYNTHETIC-1','T1','Reserved','Reserved',%s)", (NOW,))
        cur.execute("""insert into public.pig_active_outlets(pig_id,active,outlet_assignment_id,outlet_type,source_record_id)
            values('PIG-SYNTHETIC-1',true,'reservation:OL1','reservation','OL1')""")
    assert row(load(store))["state"] == "allocation_hold"
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.sales_transactions values('S1','Completed','Livestock',%s,%s)", (NOW, NOW))
        cur.execute("insert into public.sales_transaction_items values('SI1','S1','FOREIGN','t1',null,%s)", (NOW,))
    second = load(store)
    assert row(second)["state"] == "unresolved"
    assert "sales_identity_unproven" in row(second)["reasons"]
    assert row(second)["canonical"]["on_farm"] is True


def test_large_cohort_admission_replay_new_source_and_stale_snapshot_fence(weighing_store):
    store = weighing_store
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm,animal_type,purpose)
            select 'PIG-SYNTHETIC-'||n,'T'||n,'Animal '||n,'Active',true,'Grower','Grow_Out'
            from generate_series(2,1000) n""")
    first = load(store)
    initial = normalize_candidate(candidate(first), now=NOW)
    manager = PostgresManagerCaseStore(connect_factory=store)
    with store() as db, db.cursor() as cur:
        assert manager._reconcile(cur, initial, NOW) == "created"
        assert manager._reconcile(cur, initial, NOW) == "replayed"
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.orders values('O1','Approved',%s)", (NOW,))
        cur.execute("insert into public.order_lines values('OL1','O1','PIG-SYNTHETIC-1','T1','Reserved','Reserved',%s)", (NOW,))
    changed = normalize_candidate(candidate(load(store), NOW + timedelta(minutes=5)), now=NOW)
    with store() as db, db.cursor() as cur:
        assert manager._reconcile(cur, changed, NOW + timedelta(minutes=5)) == "changed"
        assert manager._reconcile(cur, initial, NOW + timedelta(minutes=6)) == "stale"
        cur.execute("select generation,evidence_digest from app_private.oom_manager_cases where case_id=%s", (initial["case_id"],))
        assert cur.fetchone() == (2, changed["evidence_digest"])
        cur.execute("select count(*) from app_private.oom_manager_cases")
        assert cur.fetchone()[0] == 1
        cur.execute("select count(*) from app_private.oom_protected_action_claims")
        assert cur.fetchone()[0] == 0


def test_actual_collector_two_cycles_keep_one_case_and_never_dispatch_farm_or_provider(weighing_store, monkeypatch):
    from unittest.mock import Mock
    from modules.oom_sakkie import manager_case_sources as sources, farm_manager_runtime as runtime
    from modules.oom_sakkie.herdmaster_daily_manager_adapter import consume_daily_manager_evidence
    from modules.oom_sakkie.general_manager_worker import deliver_farm_manager_case
    from modules.pig_weights import farm_supabase_read_service as reads, pig_welfare_case_runtime as welfare
    store = weighing_store
    monkeypatch.setattr(sources, "_configured_owner", lambda: "42")
    monkeypatch.setattr(sources, "_completed_bulk_batch_findings", lambda now: [])
    monkeypatch.setattr(sources, "_retained_litter_followup_candidates", lambda *a: [])
    monkeypatch.setattr(sources, "_purpose_review_candidates", lambda *a, **kw: [])
    monkeypatch.setattr(welfare, "welfare_case_runtime_enabled", lambda: False)
    monkeypatch.setattr(reads, "get_allocation_input_rows", lambda **kw: {
        "snapshot_observed_at": NOW.isoformat(), "overview_rows": [], "litter_rows": []})
    monkeypatch.setattr(runtime, "_load_herdmaster", lambda _db, _owner, now:
        consume_daily_manager_evidence(load(store), observed_at=now))
    manager = PostgresManagerCaseStore(connect_factory=store)
    provider = Mock(side_effect=AssertionError("no provider authority"))
    from datetime import datetime
    from modules.oom_sakkie import general_manager_worker as worker
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return now
    monkeypatch.setattr(worker, "datetime", Clock)
    for now in (NOW, NOW + timedelta(minutes=6)):
        values = sources._herdmaster(now)
        assert len(values) == 1 and values[0]["task_class"] == "informational_watch"
        outcome = manager.run_cycle(values, now=now, source_revision="synthetic-readiness",
            brain_guard_audit={"passed": True},
            refresh=lambda _case: sources._herdmaster(now)[0],
            deliver=lambda case: deliver_farm_manager_case(case, now=now, deliver=provider))
        assert outcome["success"] is True
    provider.assert_not_called()
    with store() as db, db.cursor() as cur:
        cur.execute("select status,generation from app_private.oom_manager_cases")
        assert cur.fetchall() == [("waiting_reassessment", 1)]
        cur.execute("select count(*) from app_private.oom_protected_action_claims")
        assert cur.fetchone()[0] == 0


def test_new_source_cannot_replace_foreign_worker_lease(weighing_store):
    store = weighing_store
    manager = PostgresManagerCaseStore(connect_factory=store)
    initial = normalize_candidate(candidate(load(store)), now=NOW)
    with store() as db, db.cursor() as cur:
        manager._reconcile(cur, initial, NOW)
        cur.execute("""update app_private.oom_manager_cases set status='delegated',
            assigned_worker_id='FOREIGN',lease_until=%s where case_id=%s""",
            (NOW + timedelta(minutes=10), initial["case_id"]))
        cur.execute("insert into public.pig_weight_events values('W1','PIG-SYNTHETIC-1','2026-10-01',42)")
    newer = normalize_candidate(candidate(load(store), NOW + timedelta(minutes=1)), now=NOW)
    with store() as db, db.cursor() as cur:
        assert manager._reconcile(cur, newer, NOW + timedelta(minutes=1)) == "deferred"
        cur.execute("select generation,evidence_digest,assigned_worker_id from app_private.oom_manager_cases")
        assert cur.fetchone() == (1, initial["evidence_digest"], "FOREIGN")


def test_production_reader_enforces_read_only_snapshot_and_total_timeout(weighing_store, monkeypatch):
    store = weighing_store
    original = Cursor.execute
    attempts = []
    def observe(self, statement, params=None):
        if "from public.sales_transaction_items" in statement:
            original(self, "show transaction_read_only")
            assert self.fetchone()[0] == "on"
            original(self, "show transaction_isolation")
            assert self.fetchone()[0] == "repeatable read"
            attempts.append("sales")
            original(self, "select pg_sleep(0.2)")
        return original(self, statement, params)
    monkeypatch.setattr(Cursor, "execute", observe)
    monkeypatch.setattr("modules.oom_sakkie.bounded_postgres_read.STATEMENT_TIMEOUT_MS", 40)
    started = time.monotonic()
    with pytest.raises(psycopg.errors.QueryCanceled):
        load(store)
    assert attempts == ["sales"] and time.monotonic() - started < 3
    with store() as db, db.cursor() as cur:
        cur.execute("select count(*) from app_private.oom_manager_cases")
        assert cur.fetchone()[0] == 0


def test_concurrent_current_source_reassessments_change_one_generation_once(weighing_store):
    store = weighing_store
    manager = PostgresManagerCaseStore(connect_factory=store)
    first = normalize_candidate(candidate(load(store)), now=NOW)
    with store() as db, db.cursor() as cur:
        manager._reconcile(cur, first, NOW)
        cur.execute("insert into public.pig_weight_events values('W1','PIG-SYNTHETIC-1','2026-10-01',42)")
    current = normalize_candidate(candidate(load(store), NOW + timedelta(minutes=1)), now=NOW)
    barrier = Barrier(2)
    def reassess():
        with store() as db, db.cursor() as cur:
            barrier.wait(timeout=3)
            return manager._reconcile(cur, current, NOW + timedelta(minutes=1))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: reassess(), range(2)))
    assert sorted(results) == ["changed", "replayed"]
    with store() as db, db.cursor() as cur:
        cur.execute("select generation,evidence_digest from app_private.oom_manager_cases")
        assert cur.fetchall() == [(2, current["evidence_digest"])]
        cur.execute("select count(*) from app_private.oom_manager_case_events where event_type='evidence_changed'")
        assert cur.fetchone()[0] == 1


def test_new_committed_weight_during_read_waits_for_next_consistent_snapshot(weighing_store, monkeypatch):
    store = weighing_store
    original = Cursor.execute
    inserted = []
    def observe(self, statement, params=None):
        result = original(self, statement, params)
        if "from public.current_canonical_pigs" in statement and not inserted:
            inserted.append(True)
            with store() as db, db.cursor() as cur:
                cur.execute("insert into public.pig_weight_events values('W1','PIG-SYNTHETIC-1','2026-10-01',42)")
        return result
    monkeypatch.setattr(Cursor, "execute", observe)
    first, second = load(store), load(store)
    assert row(first)["latest_weight"] is None
    assert row(second)["latest_weight"]["kg"] == 42
    assert first["material_digest"] != second["material_digest"]


def test_source_overflow_fails_closed_without_partial_reconciled_packet(weighing_store):
    store = weighing_store
    with store() as db, db.cursor() as cur:
        cur.execute("insert into public.sales_transactions values('S1','Cancelled','Livestock',%s,%s)", (NOW, NOW))
        cur.execute("""insert into public.sales_transaction_items(sale_item_id,sale_id,pig_id,tag_number)
            select 'ITEM'||n,'S1','PIG-SYNTHETIC-1','T1' from generate_series(1,10001) n""")
    with pytest.raises(RuntimeError, match="reconciliation_row_bound_exceeded"):
        load(store)
    with store() as db, db.cursor() as cur:
        cur.execute("select count(*) from app_private.oom_manager_cases")
        assert cur.fetchone()[0] == 0


@pytest.mark.parametrize("second,conflicting", [("40.0", False),
    ("40.000000", False), ("40.000000000000000001", True), ("41.0", True)])
def test_actual_numeric_variable_scale_agrees_with_weekly_coverage(weighing_store, second, conflicting):
    store = weighing_store
    with store() as db, db.cursor() as cur:
        cur.execute("""insert into public.pig_weight_events values
            ('W0','PIG-SYNTHETIC-1','2026-09-30',%s),
            ('W1','PIG-SYNTHETIC-1','2026-09-30',%s)""", (Decimal("40"), Decimal(second)))
        cur.execute("select weight_kg::text from public.pig_weight_events order by weight_event_id")
        assert cur.fetchall() == [("40",), (second,)]
    value = load(store)
    check = row(value)
    assert ("latest_weight_conflict" in check["reasons"]) is conflicting
    assert value["weight"]["current_snapshot"]["covered"] == (0 if conflicting else 1)
    if conflicting:
        assert check["latest_weight"] is None
        assert value["weight"]["current_snapshot"]["status"] == "conflicting"
    else:
        assert check["latest_weight"] == {"date": "2026-09-30", "kg": 40.0,
            "event_ids": ["W0", "W1"]}
        assert value["weight"]["current_snapshot"]["status"] == "complete"
    assert {item["weight_event_id"]: str(item["weight_kg"])
        for item in check["sources"]["latest_weights"]} == {"W0": "40", "W1": second}
