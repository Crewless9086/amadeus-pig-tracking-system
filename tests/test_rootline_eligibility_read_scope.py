"""Private per-build canonical reads preserve fresh snapshots and lifetime bounds."""
from contextvars import Context, copy_context
from contextlib import contextmanager
import threading
import time

import pytest

from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry import rootline_cycle_budget as cycle
from modules.oom_sakkie import bounded_postgres_read as bounded
from tests.test_rootline_execution_runtime import NOW, evidence, plan, controller


@pytest.fixture(autouse=True)
def isolated_capability_context():
    token = store._eligibility_reader_owner.set(None)
    try:
        yield
    finally:
        capability = store._eligibility_reader_owner.get()
        if capability is not None:
            store._release_eligibility_reader(capability)
        store._eligibility_reader_owner.reset(token)


class Client:
    def __init__(self, settings=("read committed", "on")):
        self.settings = settings
        self.closed = False
        self.rollbacks = 0
        self.statements = []
        self.fail = False
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def execute(self, sql, params=()):
        if self.fail: raise RuntimeError("query failed")
        self.statements.append((sql, params, cycle.work_deadline()))
    def fetchone(self):
        return self.settings if self.statements[-1][0].startswith("select current_setting") else None
    def fetchall(self): return []
    def rollback(self): self.rollbacks += 1
    def close(self): self.closed = True


@pytest.fixture
def clients(monkeypatch):
    values = []
    def connect(**kwargs):
        value = Client()
        values.append((value, kwargs))
        return value
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", connect)
    return values


def binding():
    def guarded(action, payload):
        with store._eligibility_reader_call(capability, guarded, action):
            return store.rootline_irrigation_execution_store(action, payload)
    capability = store._bind_eligibility_reader(store.rootline_irrigation_execution_store, guarded)
    return capability, guarded


def test_one_lazy_connection_per_build_and_two_separate_builds(clients):
    cap, guarded = binding()
    with cycle.cycle_budget():
        with store._bounded_eligibility_reads(cap, guarded):
            assert not clients
        for _ in range(2):
            with store._bounded_eligibility_reads(cap, guarded):
                assert guarded("load_zone_containment", "B12345") == {"contained": False}
                assert guarded("load_zone_containment", "C12345") == {"contained": False}
                assert guarded("load_job_events", "job") == []
                assert not clients[-1][0].closed
            assert clients[-1][0].closed and clients[-1][0].rollbacks == 1
    assert len(clients) == 2
    assert all(k["read_only"] and k["read_committed"] for _, k in clients)
    assert store._eligibility_read_scope.get() is store._eligibility_read_call.get() is None


@pytest.mark.parametrize("failure", [RuntimeError("failed"), KeyboardInterrupt(), SystemExit()])
def test_every_exit_closes_and_resets_context(clients, failure):
    cap, guarded = binding()
    with cycle.cycle_budget(), pytest.raises(type(failure)):
        with store._bounded_eligibility_reads(cap, guarded):
            guarded("load_job_events", "job")
            raise failure
    assert clients[0][0].closed and clients[0][0].rollbacks == 1
    assert store._eligibility_read_scope.get() is store._eligibility_read_call.get() is None


@pytest.mark.parametrize("failure", ["query", "settings", "expired", "acquire"])
def test_failed_scope_cannot_reacquire_or_fallback(monkeypatch, clients, failure):
    cap, guarded = binding()
    with cycle.cycle_budget():
        with store._bounded_eligibility_reads(cap, guarded):
            scope = store._eligibility_read_scope.get()
            if failure != "acquire":
                guarded("load_job_events", "job")
            if failure == "query": clients[0][0].fail = True
            elif failure == "settings":
                scope.invalidate()
            elif failure == "expired": scope.deadline = time.monotonic()-1
            else:
                def fail(**_): raise RuntimeError("acquire failed")
                monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", fail)
            with pytest.raises((RuntimeError, TimeoutError)):
                guarded("load_job_events", "job")
            count = len(clients)
            with pytest.raises(store.RootlineExecutionStoreUnavailable):
                guarded("load_job_events", "job")
            assert len(clients) == count
    assert all(c.closed for c, _ in clients)


@pytest.mark.parametrize("settings", [("repeatable read", "on"), ("read committed", "off"), None])
def test_settings_must_be_verified(monkeypatch, settings):
    client = Client(settings)
    monkeypatch.setattr(bounded, "connect_bounded_rootline_postgres", lambda **_: client)
    cap, guarded = binding()
    with cycle.cycle_budget(), pytest.raises(store.RootlineExecutionStoreUnavailable):
        with store._bounded_eligibility_reads(cap, guarded): guarded("load_job_events", "job")
    assert client.closed and client.rollbacks == 1


def test_capability_exact_identity_nonnesting_thread_and_context(clients):
    cap, guarded = binding()
    assert store._bind_eligibility_reader(lambda *_: None, guarded) is None
    with cycle.cycle_budget():
        with pytest.raises(store.RootlineExecutionStoreUnavailable):
            with store._bounded_eligibility_reads(cap, lambda *_: None): pass
        with store._bounded_eligibility_reads(cap, guarded):
            scope = store._eligibility_read_scope.get()
            with pytest.raises(store.RootlineExecutionStoreUnavailable):
                with store._bounded_eligibility_reads(cap, guarded): pass
            # An unrelated/blank context cannot borrow the retained object.
            def rejected():
                with pytest.raises(store.RootlineExecutionStoreUnavailable):
                    with scope.borrow(): pass
            Context().run(rejected)
        copied = copy_context()
        errors = []
        def foreign():
            try:
                with store._bounded_eligibility_reads(cap, guarded): pass
            except store.RootlineExecutionStoreUnavailable: errors.append(True)
        worker = threading.Thread(target=lambda: copied.run(foreign))
        worker.start(); worker.join()
        assert errors == [True]
    assert not clients


def test_minimum_entry_current_deadlines_are_retained(clients):
    cap, guarded = binding()
    entry = time.monotonic()+30
    with cycle.cycle_budget(deadline=entry):
        with store._bounded_eligibility_reads(cap, guarded):
            with cycle.mandatory_safety(): guarded("load_job_events", "job")
            tighter = time.monotonic()+10
            with cycle.cycle_budget(deadline=tighter): guarded("load_job_events", "job")
    deadlines = [d for _, _, d in clients[0][0].statements]
    assert deadlines[0] == entry and deadlines[-1] == tighter


@pytest.mark.parametrize("variant", ["canonical", "custom", "A", "protected", "no_callbacks"])
def test_current_scope_selection_and_close_before_provider(monkeypatch, clients, variant):
    source = {"ROOTLINE_AUTONOMOUS_BC_ENABLED": "true"}
    if variant == "A": source["ROOTLINE_A_ENABLED"] = "true"
    phases = []
    monkeypatch.setattr(runtime, "_refresh_a_irrigation_binding", lambda *_: None)
    monkeypatch.setattr(runtime, "build_water_energy_plan", lambda *_a, **_k: plan())
    monkeypatch.setattr(runtime, "_reconcile_contained_bc_parents", lambda **_: [])
    def build(**kwargs):
        scope = store._eligibility_read_scope.get()
        phases.append(scope)
        if variant != "no_callbacks":
            kwargs["zone_containment_reader"]("B12345")
            kwargs["zone_containment_reader"]("C12345")
            kwargs["job_event_reader"]("job")
        return {"provider_read_required": kwargs.get("_provider_preflight") is True}
    monkeypatch.setattr(runtime, "build_execution_eligibility", build)
    def read(**_):
        assert store._eligibility_read_scope.get() is None
        if variant == "canonical": assert clients[0][0].closed
        return controller()
    @runtime._bounded_irrigation_admission
    def run(*, store):
        result = runtime._current(lambda **_: (evidence(), "2026-08-08", NOW),
            read, object(), source, None, NOW, store, require_enabled=variant != "protected",
            clock=lambda: NOW, persist_resolutions=False)
        assert runtime._admission_eligibility_reader.get() is not None or variant == "custom"
        return result
    custom = (lambda action, payload: [] if action == "load_job_events" else {"contained": False})
    run(store=custom if variant == "custom" else store.rootline_irrigation_execution_store)
    if variant in {"canonical", "no_callbacks"}:
        assert all(phases) and phases[0] is not phases[1]
        assert len(clients) == (2 if variant == "canonical" else 0)
    else: assert phases == [None, None]
    assert runtime._admission_eligibility_reader.get() is None


def test_same_thread_copied_context_cannot_borrow_open_connection(clients):
    cap, guarded = binding()
    with cycle.cycle_budget():
        with store._bounded_eligibility_reads(cap, guarded):
            guarded("load_job_events", "job")
            def copied_read():
                with pytest.raises(store.RootlineExecutionStoreUnavailable, match="context"):
                    guarded("load_job_events", "job")
            copy_context().run(copied_read)
            assert clients[0][0].closed
            with pytest.raises(store.RootlineExecutionStoreUnavailable):
                guarded("load_job_events", "job")
    assert len(clients) == 1 and store._eligibility_read_scope.get() is None


def test_copied_admission_context_cannot_create_a_new_scope(clients):
    cap, guarded = binding()
    with cycle.cycle_budget():
        def copied_build():
            with pytest.raises(store.RootlineExecutionStoreUnavailable, match="context"):
                with store._bounded_eligibility_reads(cap, guarded): pass
        copy_context().run(copied_build)
        with store._bounded_eligibility_reads(cap, guarded):
            guarded("load_job_events", "job")
    store._release_eligibility_reader(cap)
    assert len(clients) == 1 and clients[0][0].closed


def test_rollback_failure_still_closes_and_resets_scope(clients):
    cap, guarded = binding()
    with cycle.cycle_budget(), pytest.raises(KeyboardInterrupt):
        with store._bounded_eligibility_reads(cap, guarded):
            guarded("load_job_events", "job")
            def failed_rollback(): raise KeyboardInterrupt()
            clients[0][0].rollback = failed_rollback
    assert clients[0][0].closed
    assert store._eligibility_read_scope.get() is store._eligibility_read_call.get() is None
