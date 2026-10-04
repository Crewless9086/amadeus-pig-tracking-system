"""Real canonical allocation and weighing reads in disposable isolated schemas.

Fixtures alone create synthetic farm rows. Production readers/projectors must not
write farm, protected-action or manager state, and no producer payload is mocked.
"""
from datetime import date, datetime, time as day_time, timedelta, timezone
import hashlib
from pathlib import Path
import re
import time

import psycopg
import pytest

from tests.test_oom_sakkie_retained_report_recovery_postgres import URL, Cursor, store
from tests.test_herdmaster_weighing_reconciliation_postgres import weighing_store

pytestmark = pytest.mark.skipif(not URL, reason="explicit isolated PostgreSQL URL required")
DAY14 = date(2026, 10, 4)
WEAN = DAY14 - timedelta(days=14)
MEMBERS = ["PURPOSE-A", "PURPOSE-B"]
KEY = "herdmaster:purpose-review:COHORT-A"


def _ddl(source, pattern):
    match = re.search(pattern, source, re.S)
    assert match, "tracked canonical fixture DDL missing"
    return match[0]


@pytest.fixture
def purpose_store(weighing_store):
    """Extend the existing isolated fixture with exact canonical read views."""
    connect = weighing_store
    migrations = Path(__file__).resolve().parents[1] / "supabase/migrations"
    canonical = (migrations / "202606290001_create_farm_canonical_tables.sql").read_text(encoding="utf-8")
    lineage = (migrations / "202607300001_create_litter_supersession_rail.sql").read_text(encoding="utf-8")
    with connect() as db, db.cursor() as cur:
        cur.execute("delete from public.pigs")
        cur.execute("""alter table public.pigs add column sex text, add column date_of_birth date,
            add column litter_id text, add column mother_pig_id text, add column father_pig_id text,
            add column wean_date date, add column wean_weight_kg numeric,
            add column earmarked boolean, add column earmark_date date""")
        cur.execute("alter table public.pig_weight_events add column created_at timestamptz default now()")
        cur.execute("alter table public.sales_transactions add column sale_channel text")
        cur.execute("""alter table public.litters add column boar_pig_id text,
            add column sow_tag_number text, add column boar_tag_number text,
            add column wean_date date, add column born_alive integer, add column weaned_count integer""")
        cur.execute((migrations / "202606280001_create_bulk_weight_batch_tables.sql").read_text(encoding="utf-8"))
        for table in ("pens", "farm_products", "pig_location_events", "pig_medical_events"):
            cur.execute(_ddl(canonical, r"create table if not exists public\." + table + r" \(.*?;"))
        # The inherited fixture has a deliberately minimal welfare projection.
        # Preserve it, then install the actual production weight/location view.
        cur.execute("alter view public.pig_current_state rename to retained_fixture_pig_current_state")
        for view in ("pig_latest_weight_events", "pig_latest_location_events", "pig_current_state"):
            cur.execute(_ddl(canonical, r"create or replace view public\." + view + r" as.*?;"))
        for view in ("current_canonical_pigs", "current_canonical_litters", "current_canonical_pig_state"):
            cur.execute(_ddl(lineage, r"create or replace view public\." + view + r" as.*?;"))
        cur.execute("insert into public.pens(pen_id,pen_name,pen_type,is_active) values('PEN-A','Synthetic weaners','Weaner',true)")
        cur.execute("""insert into public.litters(litter_id,farrowing_date,wean_date,litter_status,born_alive,weaned_count)
            values('COHORT-A','2026-08-15',%s,'Weaned',2,2)""", (WEAN,))
        for pig_id, tag in zip(MEMBERS, ("501", "502")):
            cur.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm,animal_type,
                purpose,sex,date_of_birth,litter_id,initial_pen_id,wean_date,wean_weight_kg,earmarked,earmark_date)
                values(%s,%s,%s,'Active',true,'Weaner','Unknown','Female','2026-08-15',
                    'COHORT-A','PEN-A',%s,8,true,%s)""", (pig_id, tag, "Synthetic " + tag, WEAN, WEAN))
            cur.execute("""insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg)
                values(%s,%s,%s,8)""", ("WEAN-" + pig_id, pig_id, WEAN))
    return connect


def _snapshot(connect, day=DAY14, **kwargs):
    from modules.pig_weights.herdmaster_purpose_work import load_purpose_work_snapshot
    return load_purpose_work_snapshot(analysis_date=day, database_url=URL,
        connect=lambda *_a, **_kw: connect(), **kwargs)


def _daily(connect, day=DAY14):
    from modules.pig_weights.herdmaster_daily_manager_evidence import load_daily_manager_evidence
    return load_daily_manager_evidence(analysis_date=day, database_url=URL,
        connect=lambda *_a, **_kw: connect(), include_mortality=False, include_purpose_work=True)


def _work(packet):
    result = packet["purpose_work"]
    assert result["contract"] == "herdmaster.purpose_work.v1"
    assert result["state"] == "checked"
    return result


def _cohort(packet):
    result = _work(packet)
    return next(row for row in result["cohorts"] if row["case_key"] == KEY)


def _manager(snapshot, day=DAY14):
    from modules.oom_sakkie.manager_case_sources import _purpose_review_candidates
    now = datetime.combine(day, day_time(12), tzinfo=timezone.utc)
    observed = datetime.fromisoformat(snapshot["snapshot_observed_at"])
    return _purpose_review_candidates(snapshot, now=now, today=day, observed_at=observed)


def _record_weights(connect, pig_ids=MEMBERS):
    with connect() as db, db.cursor() as cur:
        for pig_id in pig_ids:
            cur.execute("""insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg)
                values(%s,%s,%s,12)""", ("POST-" + pig_id, pig_id, DAY14))


def _fingerprint(connect, *, medical_table="pig_medical_events"):
    """Complete row digests include zero-row effect tables; no count-only proof."""
    tables = ("pigs", "litters", "pig_weight_events", "pig_location_events", medical_table,
        "orders", "order_lines", "sales_transactions", "sales_transaction_items", "pig_active_outlets",
        "pig_lifecycle_events", "operational_events", "oom_manager_cases", "oom_manager_case_events",
        "oom_protected_action_claims")
    with connect() as db, db.cursor() as cur:
        result = {}
        for table in tables:
            prefix = "app_private." if table.startswith("oom_") else "public."
            cur.execute("select coalesce(jsonb_agg(to_jsonb(t) order by to_jsonb(t)::text),'[]'::jsonb)::text from " + prefix + table + " t")
            result[table] = hashlib.sha256(cur.fetchone()[0].encode()).hexdigest()
        return result


def test_canonical_fixture_executes_all_six_real_allocation_queries(purpose_store):
    from modules.pig_weights.farm_supabase_read_service import get_allocation_input_rows
    before = _fingerprint(purpose_store)
    snapshot = get_allocation_input_rows(connect_factory=lambda _url: purpose_store(), today=DAY14)
    assert snapshot["source"] == "supabase_canonical"
    assert {row["Pig_ID"] for row in snapshot["overview_rows"]} == set(MEMBERS)
    assert snapshot["read_progress"]["query_count"] == 6
    assert snapshot["read_progress"]["connection_count"] == 1
    assert snapshot["read_progress"]["shared_snapshot"] is True
    assert all(row["state"] == "complete" for row in snapshot["read_progress"]["stages"])
    assert _fingerprint(purpose_store) == before


def test_day13_quiet_day14_one_group_then_weights_same_identity_decision(purpose_store):
    connect = purpose_store
    before = _fingerprint(connect)
    assert _work(_snapshot(connect, DAY14 - timedelta(days=1)))["cohorts"] == []
    assert _work(_daily(connect, DAY14 - timedelta(days=1)))["cohorts"] == []
    due, daily = _snapshot(connect), _daily(connect)
    group = _cohort(due)
    assert group["phase"] == "weight_due"
    assert group["member_ids"] == MEMBERS and group["weighing_ids"] == MEMBERS
    assert _cohort(daily)["material_digest"] == group["material_digest"]
    candidates = _manager(due)
    assert len(candidates) == 1 and candidates[0]["dedupe_key"] == KEY
    assert candidates[0]["task_class"] == "physical_action_due"
    assert _fingerprint(connect) == before
    _record_weights(connect)
    after_fixture_write = _fingerprint(connect)
    decision, daily_decision = _snapshot(connect), _daily(connect)
    next_group = _cohort(decision)
    assert next_group["phase"] == "decision_due" and next_group["weighing_ids"] == []
    assert next_group["member_ids"] == MEMBERS and next_group["case_key"] == group["case_key"]
    assert next_group["material_digest"] != group["material_digest"]
    assert _cohort(daily_decision)["material_digest"] == next_group["material_digest"]
    assert len(_manager(decision)) == 1
    assert _manager(decision)[0]["dedupe_key"] == KEY
    assert _manager(decision)[0]["task_class"] == "protected_decision"
    assert _fingerprint(connect) == after_fixture_write


def test_unchanged_evidence_keeps_digest_across_observation_time_and_days(purpose_store):
    before = _fingerprint(purpose_store)
    first, later = _snapshot(purpose_store), _snapshot(purpose_store, DAY14 + timedelta(days=1))
    assert _cohort(first)["material_digest"] == _cohort(later)["material_digest"]
    assert _fingerprint(purpose_store) == before


@pytest.mark.parametrize("blocked", ["held", "sold", "status_conflict", "weight_conflict", "identity_conflict"])
def test_real_canonical_exclusions_never_become_physical_weighing(purpose_store, blocked):
    with purpose_store() as db, db.cursor() as cur:
        if blocked == "held":
            cur.execute("insert into public.orders values('ORDER-A','Approved',now())")
            cur.execute("""insert into public.order_lines values
                ('LINE-A','ORDER-A','PURPOSE-A','501','Reserved','Reserved',now())""")
        elif blocked in {"sold", "status_conflict"}:
            cur.execute("update public.pigs set status='Sold',on_farm=%s where pig_id='PURPOSE-A'", (blocked == "status_conflict",))
        elif blocked == "identity_conflict":
            cur.execute("update public.pigs set tag_number='501' where pig_id='PURPOSE-B'")
        else:
            cur.execute("""insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg) values
                ('CONFLICT-A','PURPOSE-A',%s,10),('CONFLICT-B','PURPOSE-A',%s,11)""", (DAY14, DAY14))
    before = _fingerprint(purpose_store)
    for packet in (_snapshot(purpose_store), _daily(purpose_store)):
        work = _work(packet)
        assert all("PURPOSE-A" not in group["weighing_ids"] for group in work["cohorts"])
        if blocked == "identity_conflict":
            assert all(not group["weighing_ids"] for group in work["cohorts"])
        else:
            assert any("PURPOSE-B" in group["weighing_ids"] for group in work["cohorts"])
        if blocked == "sold":
            assert all("PURPOSE-A" not in group["member_ids"] for group in work["cohorts"])
        else:
            reasons = {row["pig_id"]: row["reasons"] for group in work["cohorts"] for row in group["blocked"]}
            expected = {"held": "allocation_hold", "status_conflict": "canonical_farm_status_conflict",
                "weight_conflict": "latest_weight_conflict", "identity_conflict": "canonical_identity_conflict"}
            assert expected[blocked] in reasons["PURPOSE-A"]
            if blocked == "identity_conflict":
                assert expected[blocked] in reasons["PURPOSE-B"]
    assert _fingerprint(purpose_store) == before


@pytest.mark.parametrize("loader", [_snapshot, _daily])
def test_unavailable_allocation_source_refuses_false_no_work(purpose_store, loader):
    with purpose_store() as db, db.cursor() as cur:
        cur.execute("alter table public.pig_medical_events rename to synthetic_unavailable_medical")
    before = _fingerprint(purpose_store, medical_table="synthetic_unavailable_medical")
    with pytest.raises(psycopg.errors.UndefinedTable):
        loader(purpose_store)
    assert _fingerprint(purpose_store, medical_table="synthetic_unavailable_medical") == before



@pytest.mark.parametrize("loader", [_snapshot, _daily])
def test_one_readonly_snapshot_defers_mid_read_weight_until_next_read(purpose_store, monkeypatch, loader):
    original = Cursor.execute
    inserted = []
    connections = set()
    def observe(cursor, statement, params=None):
        text = " ".join(str(statement).lower().split())
        tracked = "from public.current_canonical_pigs" in text or "from public.current_canonical_pig_state state" in text
        if tracked:
            # A separate instrumentation cursor leaves the real SELECT result
            # intact; the production query is executed exactly once.
            with cursor.cursor.connection.cursor() as guard:
                guard.execute("show transaction_read_only")
                assert guard.fetchone()[0] == "on"
                guard.execute("show transaction_isolation")
                assert guard.fetchone()[0] == "repeatable read"
            connections.add(id(cursor.cursor.connection))
        result = original(cursor, statement, params)
        if tracked and not inserted:
            inserted.append(True)
            _record_weights(purpose_store)
        return result
    monkeypatch.setattr(Cursor, "execute", observe)
    first = loader(purpose_store)
    assert len(connections) == 1
    assert _cohort(first)["phase"] == "weight_due"
    connections.clear()
    second = loader(purpose_store)
    assert len(connections) == 1
    assert _cohort(second)["phase"] == "decision_due"


def test_allocation_read_deadline_cancels_real_sql_without_manager_or_farm_write(purpose_store, monkeypatch):
    original = Cursor.execute
    attempts = []
    def slow(cursor, statement, params=None):
        if "from public.current_canonical_pig_state state" in statement:
            attempts.append(True)
            original(cursor, "select pg_sleep(0.5)")
        return original(cursor, statement, params)
    monkeypatch.setattr(Cursor, "execute", slow)
    before = _fingerprint(purpose_store)
    # Acquire first so a slow local handshake cannot satisfy this test before
    # the actual allocation SQL reaches its inherited statement deadline.
    with purpose_store() as connection:
        with connection.cursor() as cursor:
            cursor.execute("set transaction isolation level repeatable read read only")
        started = time.monotonic()
        with pytest.raises((psycopg.errors.QueryCanceled, TimeoutError)):
            _snapshot(purpose_store, connection=connection, deadline=time.monotonic() + 0.2)
        assert attempts == [True] and time.monotonic() - started < 2
    assert _fingerprint(purpose_store) == before


@pytest.mark.parametrize("loader", [_snapshot, _daily])
@pytest.mark.parametrize("stage", ["medical", "weights"])
def test_non_animal_allocation_stage_overflow_refuses_partial_work(purpose_store, monkeypatch, loader, stage):
    from modules.pig_weights import herdmaster_purpose_work as purpose
    assert purpose.ALLOCATION_STAGE_ROW_BOUND == 10000
    # Two canonical animals remain within the bound. Real non-animal rows then
    # exceed it, proving the guard belongs to each actual allocation SELECT.
    monkeypatch.setattr(purpose, "ALLOCATION_STAGE_ROW_BOUND", 2)
    with purpose_store() as db, db.cursor() as cur:
        if stage == "medical":
            cur.execute("""insert into public.pig_medical_events(medical_event_id,pig_id,treatment_date,
                treatment_type,withdrawal_days) select 'SYNTHETIC-MEDICAL-'||n,'PURPOSE-A',%s,
                'Synthetic observation',0 from generate_series(1,3) n""", (WEAN,))
        else:
            cur.execute("""insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg)
                values('SYNTHETIC-THIRD-WEIGHT','PURPOSE-A',%s,12)""", (DAY14,))
    before = _fingerprint(purpose_store)
    original = Cursor.execute
    reached = []
    def observe(cursor, statement, params=None):
        text = " ".join(str(statement).lower().split())
        if stage == "medical" and text.startswith("select pig_id, treatment_type,"):
            reached.append(stage)
        if stage == "weights" and text.startswith("select pig_id, weight_date, weight_kg from"):
            reached.append(stage)
        return original(cursor, statement, params)
    monkeypatch.setattr(Cursor, "execute", observe)
    with pytest.raises(ValueError, match="^purpose_work_allocation_source_row_bound_exceeded$"):
        loader(purpose_store)
    assert reached == [stage]
    assert _fingerprint(purpose_store) == before
