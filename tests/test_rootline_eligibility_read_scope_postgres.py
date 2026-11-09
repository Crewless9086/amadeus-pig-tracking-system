"""Real PostgreSQL fresh-commit visibility and bounded eligibility scope cleanup."""
from copy import deepcopy
from contextvars import copy_context
import time

import pytest

from tests.test_rootline_no_send_preparation_postgres import isolated_database, connect, DATABASE_URL
from tests.test_rootline_eligibility_read_scope import binding
from tests.test_rootline_execution_runtime import NOW, evidence, plan, controller
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry import rootline_cycle_budget as cycle
from modules.oom_sakkie import bounded_postgres_read as bounded
from modules.telemetry.rootline_execution_authority import build_execution_eligibility

pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="explicit disposable PostgreSQL URL required")


@pytest.fixture
def clients(monkeypatch):
    values = []
    original = bounded.connect_bounded_rootline_postgres
    def observed(**kwargs):
        value = original(**kwargs)
        values.append(value)
        return value
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", observed)
    yield values
    assert all(c.closed for c in values)
    assert store._eligibility_read_scope.get() is store._eligibility_read_call.get() is None


def insert(action, body):
    with connect() as connection, connection.cursor() as cursor:
        store._insert_managed_event(cursor, action, body)


def run_current(monkeypatch, current_plan, *, provider=None):
    monkeypatch.setattr(runtime, "_refresh_a_irrigation_binding", lambda *_: None)
    monkeypatch.setattr(runtime, "build_water_energy_plan", lambda *_a, **_k: current_plan)
    @runtime._bounded_irrigation_admission
    def run(*, store):
        return runtime._current(lambda **_: (evidence(), "2026-08-08", NOW),
            provider or (lambda **_: controller()), object(),
            {"ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"}, DATABASE_URL, NOW, store,
            require_enabled=True, reconcile_stale=False, persist_resolutions=False, clock=lambda: NOW)
    return run(store=store.rootline_irrigation_execution_store)


def test_committed_containment_between_selects_blocks_provider_and_on(monkeypatch, clients):
    current_plan = plan()
    current_plan["candidate_tasks"].append({**deepcopy(current_plan["candidate_tasks"][0]),
        "task_id": "irrigation_C12345", "rank": 2})
    insert("contain_zone", {"execution_id": "CONTAIN-B", "zone_id": "B12345"})
    original, reads = store._load, []
    def changed(action, payload):
        result = original(action, payload)
        reads.append((action, payload, result))
        if (action, payload) == ("load_zone_containment", "B12345"):
            # Independently committed AFTER B's first SELECT in the same scope.
            insert("contain_zone", {"execution_id": "CONTAIN-C", "zone_id": "C12345"})
        return result
    monkeypatch.setattr(store, "_load", changed)
    def provider(**_): pytest.fail("contained zones must not reach provider HTTP")
    result = run_current(monkeypatch, current_plan, provider=provider)
    assert result["artifact"]["eligible"] is False
    assert reads[1][0:2] == ("load_zone_containment", "C12345")
    assert reads[1][2]["contained"] is True
    assert len(clients) == 1 and clients[0].closed
    with connect() as connection:
        assert connection.execute("select count(*) from public.sam_live_stock_conversation_review_events "
            "where recommended_action='claim_before_on'").fetchone()[0] == 0


def test_committed_history_after_containment_blocks_provider_and_on(monkeypatch, clients):
    artifact = build_execution_eligibility(plan=plan(), evidence=evidence(),
        controller=controller(), now=NOW)
    assert artifact["eligible"] is True
    original, reads = store._load, []
    def changed(action, payload):
        result = original(action, payload)
        reads.append((action, payload, result))
        if action == "load_zone_containment":
            insert("claim_before_on", {**artifact, "execution_id": "OTHER-COMMITTED-CLAIM",
                "segment_number": artifact["current_segment"], "state": "claimed"})
        return result
    monkeypatch.setattr(store, "_load", changed)
    def provider(**_): pytest.fail("fresh claimed job must not reach provider HTTP")
    result = run_current(monkeypatch, plan(), provider=provider)
    assert result["artifact"]["status"] == "segment_in_progress"
    assert reads[-1][0] == "load_job_events"
    assert reads[-1][2][0]["execution_id"] == "OTHER-COMMITTED-CLAIM"
    assert len(clients) == 1 and clients[0].closed
    with connect() as connection:
        assert connection.execute("select count(*) from public.sam_live_stock_conversation_review_events "
            "where recommended_action='claim_before_on'").fetchone()[0] == 1


def test_actual_current_uses_separate_closed_pre_and_post_provider_scopes(monkeypatch, clients):
    def provider(**_):
        assert store._eligibility_read_scope.get() is None
        assert len(clients) == 1 and clients[0].closed
        return controller()
    result = run_current(monkeypatch, plan(), provider=provider)
    assert result["artifact"]["eligible"] is True
    assert len(clients) == 2 and clients[0] is not clients[1]
    assert all(c.closed for c in clients)


@pytest.mark.parametrize("failure", ["query", "readonly", "expiry", "baseexception", "copied_context"])
def test_real_clients_close_and_scope_cannot_reacquire(clients, failure):
    import psycopg
    cap, guarded = binding()
    try:
        with cycle.cycle_budget():
            with store._bounded_eligibility_reads(cap, guarded):
                guarded("load_job_events", "job")
                scope = store._eligibility_read_scope.get()
                if failure == "copied_context":
                    with pytest.raises(store.RootlineExecutionStoreUnavailable):
                        copy_context().run(guarded, "load_job_events", "job")
                elif failure == "expiry":
                    with cycle.cycle_budget(deadline=time.monotonic()-1), pytest.raises(TimeoutError):
                        guarded("load_job_events", "job")
                else:
                    exception = KeyboardInterrupt if failure == "baseexception" else psycopg.Error
                    with pytest.raises(exception), store._eligibility_reader_call(cap, guarded, "load_job_events"):
                        with scope.borrow() as connection:
                            if failure == "baseexception": raise KeyboardInterrupt()
                            with connection.cursor() as cursor:
                                cursor.execute("select 1/0" if failure == "query" else
                                    "insert into public.litter_cohort_dispositions(pig_id) values ('SCOPE-WRITE')")
                assert clients[0].closed
                with pytest.raises(store.RootlineExecutionStoreUnavailable):
                    guarded("load_job_events", "job")
        assert len(clients) == 1
    finally:
        store._release_eligibility_reader(cap)


def test_other_load_actions_keep_separate_legacy_connection(clients):
    cap, guarded = binding()
    try:
        with cycle.cycle_budget():
            with store._bounded_eligibility_reads(cap, guarded):
                guarded("load_job_events", "job")
                assert guarded("load_active", None) is None
                assert len(clients) == 2 and clients[1].closed and not clients[0].closed
                guarded("load_job_events", "job")
            assert clients[0].closed
    finally:
        store._release_eligibility_reader(cap)
