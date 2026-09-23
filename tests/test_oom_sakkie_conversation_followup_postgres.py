"""Real bounded conversational reads against an explicit disposable PostgreSQL DSN.

Only namespace qualification is adapted; production SELECTs, view definitions,
projection functions and the bounded transaction connector execute unchanged.
"""
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb
import pytest

from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.oom_sakkie import farm_manager_runtime as manager
from modules.oom_sakkie import tools
from modules.pig_weights import farm_supabase_read_service as farm

URL = os.environ.get("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="explicit disposable PostgreSQL URL is required")
NOW = datetime(2026, 9, 23, tzinfo=timezone.utc)


class Cursor:
    def __init__(self, cursor, store, inspect=False):
        self.cursor, self.store, self.inspect = cursor, store, inspect

    def execute(self, query, params=None):
        rewritten = query.replace("public.", self.store.schema + ".").replace(
            "app_private.", self.store.schema + ".")
        self.cursor.execute(rewritten, params)
        if self.inspect and query.lstrip().lower().startswith("select"):
            with self.cursor.connection.cursor() as check:
                check.execute("show transaction_read_only")
                read_only = check.fetchone()[0]
                check.execute("show transaction_isolation")
                isolation = check.fetchone()[0]
            self.store.read_states.append((read_only, isolation))
            if "lower(state.pig_id)" in query and self.store.after_identity is not None:
                callback, self.store.after_identity = self.store.after_identity, None
                callback()
        return self

    def __getattr__(self, name): return getattr(self.cursor, name)
    def __enter__(self): self.cursor.__enter__(); return self
    def __exit__(self, *args): return self.cursor.__exit__(*args)


class Connection:
    def __init__(self, connection, store, inspect=False):
        self.connection, self.store, self.inspect = connection, store, inspect
    def cursor(self): return Cursor(self.connection.cursor(), self.store, self.inspect)
    def __getattr__(self, name): return getattr(self.connection, name)
    def __enter__(self): self.connection.__enter__(); return self
    def __exit__(self, *args): return self.connection.__exit__(*args)


class Store:
    def __init__(self, schema):
        self.schema = schema
        self.read_connections = 0
        self.read_states = []
        self.after_identity = None

    def seed(self):
        return Connection(psycopg.connect(URL), self)

    def connect(self, target_url=None, **kwargs):
        assert target_url == URL, "runtime may connect only to the explicit disposable DSN"
        self.read_connections += 1
        return Connection(psycopg.connect(URL, **kwargs), self, inspect=True)

    def snapshot(self):
        result = {}
        with self.seed() as db, db.cursor() as cur:
            cur.execute("set transaction read only")
            for table, key in (("pigs", "pig_id"), ("pig_weight_events", "weight_event_id"),
                               ("mating_events", "mating_id"), ("oom_manager_cases", "case_id")):
                cur.execute(f"select to_jsonb(t) from public.{table} t order by {key}")
                result[table] = cur.fetchall()
        return result


@pytest.fixture
def store(monkeypatch):
    parsed = urlsplit(URL)
    assert parsed.scheme in {"postgres", "postgresql"}
    assert parsed.hostname in {"localhost", "127.0.0.1", "::1"}
    assert "test" in parsed.path and not parsed.query and not parsed.fragment
    assert not any(os.environ.get(key) for key in (
        "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE", "PGOPTIONS")), \
        "disposable connection must not inherit alternate libpq destinations"
    monkeypatch.setenv("DATABASE_URL", URL)
    instance = Store("conversation_read_" + uuid4().hex)
    migrations = Path(__file__).resolve().parents[1] / "supabase/migrations"
    with psycopg.connect(URL) as db:
        db.execute(sql.SQL("create schema {}").format(sql.Identifier(instance.schema)))
    try:
        with instance.seed() as db, db.cursor() as cur:
            # Empty prerequisites only satisfy the actual foundation FK targets.
            cur.execute("create table app_private.migration_log(migration_id text primary key,description text)")
            cur.execute("create table public.bulk_weight_batches(batch_id uuid primary key)")
            cur.execute("create table public.bulk_weight_batch_rows(row_id uuid primary key)")
            for name in ("202606290001_create_farm_canonical_tables.sql",
                         "202606290003_add_litter_lifecycle_fields.sql"):
                cur.execute((migrations / name).read_text(encoding="utf-8"))
            # Exact membership relation used by the actual canonical views.
            cur.execute("create table public.litter_cohort_dispositions(pig_id text primary key)")
            ddl = (migrations / "202607300001_create_litter_supersession_rail.sql").read_text(encoding="utf-8")
            for name in ("current_canonical_pigs", "current_canonical_pig_state"):
                match = re.search(r"create or replace view public\." + name + r" as.*?;", ddl, re.S)
                assert match, name
                cur.execute(match[0])
            ddl = (migrations / "202608170002_create_oom_manager_case_runtime.sql").read_text(encoding="utf-8")
            cur.execute(re.search(r"create table if not exists app_private\.oom_manager_cases \(.*?;", ddl, re.S)[0])
            cur.execute("insert into public.pens(pen_id,pen_name) values('PEN-A','Synthetic pen')")
            for pig_id, tag, name, status, on_farm in (
                ("ACTIVE", "702", "Hazel", "Active", True),
                ("SOLD", "703", "Maple", "Sold", False),
                ("DEAD", "704", "Ash", "Dead", False)):
                cur.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm,
                    sex,purpose,initial_pen_id) values(%s,%s,%s,%s,%s,'Female','Breeding','PEN-A')""",
                    (pig_id, tag, name, status, on_farm))
                cur.execute("""insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg)
                    values(%s,%s,%s,87)""", ("W-" + pig_id, pig_id, date.today()))
        original_connect = bounded.connect_bounded_rootline_postgres
        monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres",
            lambda **kwargs: original_connect(database_url=URL, connect=instance.connect, **kwargs))
        for name in ("get_pig_allocation_readiness_data", "get_mating_overview", "_current_herdmaster_breeding_loop"):
            monkeypatch.setattr(tools, name, lambda *_a, **_kw: pytest.fail("explicit animal read must not fan out to whole-herd queries"))
        yield instance
    finally:
        with psycopg.connect(URL) as db:
            db.execute(sql.SQL("drop schema {} cascade").format(sql.Identifier(instance.schema)))


def animal_question(subject, language="en"):
    return tools.herdmaster_herd_question_handler({"authenticated_owner": True,
        "subject": subject, "user_text": "What is this animal's current status?",
        "semantic_language": language})


def add_mating(store, identity, sow="ACTIVE", boar="SOLD", when=date(2026, 8, 1)):
    with store.seed() as db, db.cursor() as cur:
        cur.execute("""insert into public.mating_events(mating_id,sow_pig_id,boar_pig_id,mating_date)
            values(%s,%s,%s,%s)""", (identity, sow, boar, when))


def add_case(store, identity, key, status="open", due=NOW):
    with store.seed() as db, db.cursor() as cur:
        cur.execute("""insert into app_private.oom_manager_cases(case_id,dedupe_key,specialist,
            urgency,status,evidence_digest,evidence_refs,summary,next_action,next_reassessment_at,generation)
            values(%s,%s,'HERDMASTER','due',%s,%s,%s,'Synthetic case','Read evidence',%s,1)""",
            (identity, key, status, "0" * 64, Jsonb(["pig:ACTIVE"]), due))


@pytest.mark.parametrize("pig_id,tag,name,status,on_farm", [
    ("ACTIVE", "702", "hazel", "Active", "Yes"),
    ("SOLD", "703", "maple", "Sold", "No"),
    ("DEAD", "704", "ash", "Dead", "No")])
def test_actual_identity_and_detail_keep_lifecycle_without_active_filter(store, pig_id, tag, name, status, on_farm):
    before = store.snapshot()
    for subject in (tag, name, pig_id.lower(), " " + tag + " "):
        matches = farm.resolve_pig_read_identity(subject, connect_factory=store.connect)
        assert [row["pig_id"] for row in matches] == [pig_id]
    detail = farm.get_pig_detail(pig_id, connect_factory=store.connect)
    assert (detail["status"], detail["on_farm"], detail["current_weight_kg"]) == (status, on_farm, 87.0)
    assert detail["lifecycle"]["status"] == status
    assert detail["current_pen_id"] == "PEN-A"
    assert detail["current_pen_name"] == "Synthetic pen"
    assert detail["last_weight_date"] == date.today().isoformat()
    assert detail["source"] == "supabase_canonical"
    assert store.snapshot() == before
    assert all(read_only == "on" for read_only, _ in store.read_states)


def test_actual_parent_join_and_superseded_view_membership(store):
    with store.seed() as db, db.cursor() as cur:
        cur.execute("update public.pigs set mother_pig_id='SOLD',father_pig_id='DEAD' where pig_id='ACTIVE'")
        cur.execute("insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm) values('RETIRED-DUP','702','Hazel','Active',true)")
        cur.execute("insert into public.litter_cohort_dispositions values('RETIRED-DUP')")
    assert [row["pig_id"] for row in farm.resolve_pig_read_identity("702", connect_factory=store.connect)] == ["ACTIVE"]
    assert farm.get_pig_detail("RETIRED-DUP", connect_factory=store.connect) is None
    detail = farm.get_pig_detail("ACTIVE", connect_factory=store.connect)
    assert (detail["mother_pig_id"], detail["mother_tag_number"], detail["father_pig_id"], detail["father_tag_number"]) == ("SOLD", "703", "DEAD", "704")


def test_actual_ambiguous_name_keeps_sold_dead_candidates_and_bounded_identity(store):
    with store.seed() as db, db.cursor() as cur:
        cur.execute("update public.pigs set pig_name='Shared'")
        cur.execute("insert into public.pigs(pig_id,pig_name,status,on_farm) values('ZZ-FOURTH','Shared','Active',true)")
    matches = farm.resolve_pig_read_identity("SHARED", connect_factory=store.connect)
    assert [row["pig_id"] for row in matches] == ["ACTIVE", "DEAD", "SOLD"]
    before = store.snapshot()
    result = animal_question("Shared")
    assert result["success"] is False and result["status"] == "animal_identity_ambiguous"
    assert store.snapshot() == before


@pytest.mark.parametrize("subject", ["missing", "%", "' OR 1=1 --", "", "x" * 101])
def test_actual_missing_or_invalid_identity_never_selects_another_animal(store, subject):
    assert farm.resolve_pig_read_identity(subject, connect_factory=store.connect) == []
    assert farm.get_pig_detail(subject, connect_factory=store.connect) is None


def test_actual_scoped_mating_query_filters_before_limit_for_sow_or_boar(store):
    with store.seed() as db, db.cursor() as cur:
        for index in range(70):
            cur.execute("""insert into public.mating_events(mating_id,sow_pig_id,boar_pig_id,mating_date)
                values(%s,'SOLD','DEAD','2026-09-01')""", (f"UNRELATED-{index:03}",))
    add_mating(store, "OWN-SOW")
    add_mating(store, "OWN-BOAR", "DEAD", "ACTIVE")
    before = store.snapshot()
    detail = farm.get_pig_detail("ACTIVE", connect_factory=store.connect)
    result = farm.get_pig_mating_read_evidence("ACTIVE", detail, connect_factory=store.connect)
    assert {row["mating_id"] for row in result} == {"OWN-SOW", "OWN-BOAR"}
    assert {row["mating_date"] for row in result} == {"2026-08-01"}
    assert all(row["expected_farrowing_date"] == "2026-11-23" for row in result)
    assert store.snapshot() == before


@pytest.mark.parametrize("count", [64, 65])
def test_actual_scoped_mating_overflow_fails_closed(store, count):
    with store.seed() as db, db.cursor() as cur:
        for index in range(count):
            cur.execute("""insert into public.mating_events(mating_id,sow_pig_id,mating_date)
                values(%s,'ACTIVE','2026-08-01')""", (f"M-{index:03}",))
    detail = farm.get_pig_detail("ACTIVE", connect_factory=store.connect)
    if count == 65:
        with pytest.raises(ValueError, match="^pig_mating_evidence_truncated$"):
            farm.get_pig_mating_read_evidence("ACTIVE", detail, connect_factory=store.connect)
        assert animal_question("702")["status"] == "canonical_herd_evidence_unavailable"
    else:
        result = farm.get_pig_mating_read_evidence("ACTIVE", detail, connect_factory=store.connect)
        assert len(result) == 64 and result[0]["mating_id"] == "M-063"


@pytest.mark.parametrize("tag,status,on_farm,language", [
    ("702", "Active", "Yes", "en"), ("703", "Sold", "No", "en"), ("704", "Dead", "No", "af")])
def test_actual_typed_animal_handler_uses_one_read_only_repeatable_snapshot(store, tag, status, on_farm, language):
    before = store.snapshot()
    result = animal_question(tag, language)
    assert result["success"] is True, result["status"]
    assert result["raw"]["facts"]["identity"]["lifecycle_status"] == status
    assert result["raw"]["facts"]["identity"]["on_farm"] == on_farm
    assert result["raw"]["writes_performed"] is False
    assert result["raw"]["protected_actions_performed"] is False
    assert store.read_connections == 1
    assert store.read_states and set(store.read_states) == {("on", "repeatable read")}
    assert store.snapshot() == before


def test_actual_repeatable_read_keeps_identity_detail_and_mating_from_one_snapshot(store):
    def commit_newer_facts():
        with store.seed() as db, db.cursor() as cur:
            cur.execute("update public.pigs set status='Sold',on_farm=false where pig_id='ACTIVE'")
            cur.execute("insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg) values('NEW-W','ACTIVE',%s,99)", (date.today() + timedelta(days=1),))
            cur.execute("insert into public.mating_events(mating_id,sow_pig_id,mating_date) values('AFTER-SNAPSHOT','ACTIVE','2026-09-01')")
    store.after_identity = commit_newer_facts
    result = animal_question("702")
    assert result["success"] is True, result["status"]
    facts = result["raw"]["facts"]
    assert facts["identity"]["lifecycle_status"] == "Active"
    assert facts["latest_weight"]["weight_kg"] == 87.0
    assert facts["breeding"]["mating_event_count"] == 0
    assert store.read_connections == 1
    assert set(store.read_states) == {("on", "repeatable read")}
    latest = farm.get_pig_detail("ACTIVE", connect_factory=store.connect)
    assert (latest["status"], latest["current_weight_kg"]) == ("Sold", 99.0)
    assert [row["mating_id"] for row in farm.get_pig_mating_read_evidence("ACTIVE", latest, connect_factory=store.connect)] == ["AFTER-SNAPSHOT"]


def test_actual_bounded_connection_rejects_sql_mutation(store):
    before = store.snapshot()
    with pytest.raises(psycopg.errors.ReadOnlySqlTransaction):
        with bounded.connect_bounded_rootline_postgres() as db, db.cursor() as cur:
            cur.execute("update public.pigs set status='Dead' where pig_id='ACTIVE'")
    assert store.snapshot() == before


@pytest.mark.parametrize("kind,prefix", [
    ("mortality", "herdmaster:retained-mortality:"),
    ("farrowing", "herdmaster:expired-farrowing:"), ("welfare", "herdmaster:welfare:")])
def test_actual_case_kind_filter_precedes_backlog_limit_and_preserves_containment(store, kind, prefix):
    for index in range(70):
        add_case(store, f"UNRELATED-{index:03}", f"rootline:water:{index}", due=NOW - timedelta(days=1))
    add_case(store, "SCOPED-OPEN", prefix + "open")
    add_case(store, "SCOPED-CONTAINED", prefix + "contained", "contained")
    add_case(store, "SCOPED-COMPLETED", prefix + "completed", "completed")
    before = store.snapshot()
    result = manager._load_enquiry_cases({"kind": "case_status", "case_kind": kind})
    assert result["truncated"] is False
    assert {row["case_id"] for row in result["cases"]} == {"SCOPED-OPEN", "SCOPED-CONTAINED"}
    assert {row["status"] for row in result["cases"]} == {"open", "contained"}
    assert store.snapshot() == before
    assert all(state[0] == "on" for state in store.read_states)


@pytest.mark.parametrize("count", [64, 65])
def test_actual_case_snapshot_reports_overflow_without_mutating_cases(store, count):
    for index in range(count):
        add_case(store, f"CASE-{index:03}", f"herdmaster:retained-mortality:{index}")
    before = store.snapshot()
    result = manager._load_enquiry_cases({"case_kind": "mortality"})
    assert result["truncated"] is (count == 65)
    assert [row["case_id"] for row in result["cases"]] == [f"CASE-{index:03}" for index in range(64)]
    assert store.snapshot() == before
