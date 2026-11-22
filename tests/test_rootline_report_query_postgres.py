"""Opt-in SQL equivalence on root's leased disposable loopback database only.

All data and indexes are session-local TEMP copies of the existing table/index
shape. No public table, schema, index or setting is changed. This suite must be
run only while root has granted an exclusive local lease.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from random import Random
import time
from urllib.parse import urlparse

import pytest
import psycopg
from psycopg import sql as pgsql
from psycopg.types.json import Jsonb

from tests.test_rootline_report_query import capture_query, store

URL = os.getenv("ROOTLINE_HA_COMMAND_TEST_URL", "")
LEASE = os.getenv("ROOTLINE_REPORT_QUERY_TEST_LEASE", "")
pytestmark = pytest.mark.skipif(not URL or LEASE != "report-query40",
    reason="root-exclusive report-query40 lease and exact disposable PostgreSQL URL required")
TABLE = "public.sam_live_stock_conversation_review_events"
TEMP = "pg_temp.report_query40_events"
NOW = datetime(2020, 1, 1, tzinfo=timezone.utc)
ORIGINAL = """select review_json->'automatic_reassessment'
    from public.sam_live_stock_conversation_review_events
    where event_source=%s
      and review_json->'automatic_reassessment'->>'specialist'=%s
      and review_json->'automatic_reassessment'->>'status' in ('completed','contained')
      and coalesce(review_json->'automatic_reassessment'->>'report_work_due','true') <> 'false'
    order by created_at desc, review_event_id desc limit 1"""


@pytest.fixture
def db(monkeypatch):
    selected = urlparse(URL)
    assert selected.scheme in {"postgres", "postgresql"}
    assert selected.hostname == "127.0.0.1" and selected.port == 55485
    assert selected.path == "/rootline_ha_command_mode_test" and selected.username == "postgres"
    assert selected.password is None and not selected.query and not selected.fragment
    # These are bounded options on this disposable test connection only.
    with psycopg.connect(URL, autocommit=True, connect_timeout=5,
            options="-c statement_timeout=3000 -c lock_timeout=1000") as connection:
        identity = connection.execute("select current_database(), host(inet_server_addr()), inet_server_port()").fetchone()
        assert identity == ("rootline_ha_command_mode_test", "127.0.0.1", 55485)
        connection.execute("""create temporary table report_query40_events (
            review_event_id text primary key, event_source text not null,
            created_at timestamptz not null, review_json jsonb not null)""")
        connection.execute("""create index query40_source_created on report_query40_events
            (event_source, created_at desc, review_event_id)""")
        connection.execute("""create index query40_auto_identity_created on report_query40_events
            ((review_json->'automatic_reassessment'->>'identity'), created_at desc, review_event_id desc)
            where event_source='oom_sakkie_automatic_reassessment'""")
        calls = []
        class Cursor:
            def __enter__(self):
                self.inner = connection.cursor(); self.inner.__enter__(); return self
            def __exit__(self, *args): return self.inner.__exit__(*args)
            def execute(self, sql, params):
                calls.append((sql, params))
                assert TABLE in sql
                return self.inner.execute(sql.replace(TABLE, TEMP), params)
            def fetchone(self): return self.inner.fetchone()
        class ReadConnection:
            def cursor(self): return Cursor()
        @contextmanager
        def connect(): yield ReadConnection()
        monkeypatch.setattr(store, "connect_bounded_read", connect)
        yield connection, calls
        # Closing this connection removes its TEMP table and indexes.


def add(db, identity, seconds=0, *, source=None, body=None):
    connection, _ = db
    if body is None: body = {"specialist": "ROOTLINE", "status": "completed", "identity": identity}
    connection.execute("insert into "+TEMP+" values(%s,%s,%s,%s)",
        (identity, source or store.EVENT_SOURCE, NOW+timedelta(seconds=seconds),
         Jsonb({"automatic_reassessment": body})))


def equivalent(db, specialist="ROOTLINE"):
    connection, calls = db
    prior = connection.execute(ORIGINAL.replace(TABLE, TEMP), (store.EVENT_SOURCE, specialist)).fetchone()
    before = len(calls)
    actual = store._load("load_latest_outcome", specialist)
    assert len(calls) == before+1  # One actual store statement, not two client snapshots.
    assert actual == (prior[0] if prior else None)
    return actual


def test_empty_and_all_control_only_history(db):
    assert equivalent(db) is None
    for i, value in enumerate([False, "false"]):
        add(db, f"control-{i}", i, body={"specialist": "ROOTLINE", "status": "contained", "report_work_due": value})
    assert equivalent(db) is None


@pytest.mark.parametrize("due", [None, True, "true", "False", 0, 1, {}, []])
def test_legacy_null_and_existing_nonfalse_json_semantics(db, due):
    add(db, "legacy", 1)
    add(db, "selected", 2, body={"specialist": "ROOTLINE", "status": "contained", "report_work_due": due, "marker": "selected"})
    assert equivalent(db)["marker"] == "selected"


def test_equal_timestamp_all_ties_and_same_predicates(db):
    for identity in ["A", "B", "M"]: add(db, identity, 1)
    add(db, "Z", 1, body={"specialist": "ROOTLINE", "status": "completed", "report_work_due": False})
    add(db, "Y", 1, body={"specialist": "OTHER", "status": "completed"})
    add(db, "X", 1, source="other_source")
    add(db, "W", 1, body={"specialist": "ROOTLINE", "status": "claimed"})
    assert equivalent(db)["identity"] == "M"


def test_native_microsecond_order_and_old_legacy_report(db):
    add(db, "Z", 86400)
    add(db, "A", 86400.000001)
    assert equivalent(db)["identity"] == "A"
    db[0].execute("truncate "+TEMP)
    add(db, "old-legacy", -86400)
    db[0].execute("""insert into pg_temp.report_query40_events
        select 'control-'||i, %s, %s::timestamptz+i*interval '1 second',
        jsonb_build_object('automatic_reassessment',jsonb_build_object(
            'specialist','ROOTLINE','status','completed','report_work_due',false))
        from generate_series(1,10000) i""", (store.EVENT_SOURCE, NOW))
    assert equivalent(db)["identity"] == "old-legacy"


def test_malformed_body_and_other_specialist_cannot_replace_eligible_history(db):
    add(db, "legacy")
    for i, body in enumerate([{}, [], "scalar", 0, False, {"specialist": "ROOTLINE"},
            {"specialist": "OTHER", "status": "completed"}, {"specialist": "ROOTLINE", "status": None}]):
        add(db, f"noise-{i}", i+1, body=body)
    assert equivalent(db)["identity"] == "legacy"
    assert equivalent(db, "OTHER") == {"specialist": "OTHER", "status": "completed"}


def test_random_mixed_history_matches_exact_original_sql(db):
    rng = Random(4001)
    for i in range(500):
        body = {"specialist": rng.choice(["ROOTLINE", "OTHER", None]),
            "status": rng.choice(["completed", "contained", "claimed", None]), "marker": i}
        if rng.randrange(3): body["report_work_due"] = rng.choice([None, True, False, "false", "False", 0, {}])
        add(db, f"row-{i:04d}", rng.randrange(20), source=rng.choice([store.EVENT_SOURCE, "other_source"]), body=body)
    equivalent(db)


def plan_nodes(node):
    yield node
    for child in node.get("Plans", []): yield from plan_nodes(child)


@pytest.mark.parametrize("planning_mode", ["auto", "force_custom_plan", "force_generic_plan"])
def test_existing_index_shape_and_bounded_synthetic_scale(db, record_property, planning_mode):
    connection, calls = db
    connection.execute("""insert into pg_temp.report_query40_events
        select 'scale-'||lpad(i::text,8,'0'),
          case when i%%7=0 then 'other_source' else %s end,
          %s::timestamptz+i*interval '1 second',
          jsonb_build_object('padding',repeat('x',1024),'automatic_reassessment',jsonb_build_object(
            'identity','scale-'||i,'specialist','ROOTLINE','status','completed','report_work_due',i%%19=0))
        from generate_series(1,25000) i""", (store.EVENT_SOURCE, NOW))
    connection.execute("analyze pg_temp.report_query40_events")
    started = time.monotonic()
    selected = equivalent(db)
    oracle_and_actual_seconds = time.monotonic()-started
    sql, params = calls[-1]
    prepared_counts = None
    if planning_mode == "auto":
        plan = connection.execute("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) "+sql.replace(TABLE, TEMP), params).fetchone()[0][0]
    else:
        fragments = sql.replace(TABLE, TEMP).split("%s")
        assert len(fragments) == 5
        prepared = fragments[0] + "".join(f"${i}"+part for i, part in enumerate(fragments[1:], 1))
        connection.execute("prepare report_query40(text,text,text,text) as "+prepared)
        with connection.transaction():
            # Transaction-local test setting only; never production or app configuration.
            connection.execute("select set_config('plan_cache_mode', %s, true)", (planning_mode,))
            execute = pgsql.SQL("execute report_query40({})").format(
                pgsql.SQL(",").join(map(pgsql.Literal, params)))
            assert connection.execute(execute).fetchone()[0] == selected
            for specialist in ("OTHER", "ROOTLINE'; --"):
                probe = (store.EVENT_SOURCE, specialist, store.EVENT_SOURCE, specialist)
                command = pgsql.SQL("execute report_query40({})").format(
                    pgsql.SQL(",").join(map(pgsql.Literal, probe)))
                assert connection.execute(command).fetchone() is None
            plan = connection.execute(pgsql.SQL("EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ")+execute).fetchone()[0][0]
            prepared_counts = connection.execute(
                "select generic_plans, custom_plans from pg_prepared_statements where name='report_query40'"
            ).fetchone()
        connection.execute("deallocate report_query40")
    print(json.dumps({"planning_mode": planning_mode, "complete_explain": plan,
        "prepared_plan_counts": prepared_counts}, sort_keys=True))
    if prepared_counts is not None:
        generic_count, custom_count = prepared_counts
        assert (generic_count > 0 and custom_count == 0) if planning_mode == "force_generic_plan" else (
            custom_count > 0 and generic_count == 0)
    nodes = list(plan_nodes(plan["Plan"]))
    has_sort = any(node["Node Type"] in {"Sort", "Incremental Sort"} for node in nodes)
    directions = {node.get("Scan Direction") for node in nodes if node.get("Index Name") == "query40_source_created"}
    if planning_mode != "force_generic_plan":
        assert not has_sort, plan
        assert directions == {"Forward", "Backward"}, plan
    # Forced generic planning is an explicit sensitivity test. Current _load uses
    # one statement per fresh connection; it cannot accumulate driver preparation.
    # A generic scan/sort is retained as a limitation, never hidden or skipped.
    assert selected is not None
    assert plan["Execution Time"] < 3000  # Local fixed dataset only, not a service guarantee.
    evidence = {"planning_mode":planning_mode,"prepared_plan_counts":prepared_counts,"synthetic_rows":25000,"padding_bytes_per_row":1024,
        "statement_timeout_ms":3000,"oracle_plus_actual_seconds":oracle_and_actual_seconds,
        "execution_ms":plan["Execution Time"],"planning_ms":plan["Planning Time"],
        "source_index_directions":sorted(directions),"no_sort":not has_sort,
        "scan_nodes":[{key:node[key] for key in ("Node Type","Alias","Index Name","Scan Direction",
            "Actual Rows","Rows Removed by Filter","Actual Loops") if key in node}
            for node in nodes if node["Node Type"] in {"Seq Scan","Index Scan","Index Only Scan","Bitmap Heap Scan"}],
        "root_buffers":{key:value for key,value in plan["Plan"].items() if "Blocks" in key},
        "qualification":("Forced-generic exact semantics and bounded runtime; scan/sort permitted and recorded as planner sensitivity"
            if planning_mode == "force_generic_plan" else "Normal/custom source-index no-sort on this local dataset"),
        "production_guarantee":False}
    print(json.dumps(evidence,sort_keys=True))
    for key,value in evidence.items(): record_property(key,value)
