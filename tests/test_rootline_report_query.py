"""Store lookup transport semantics; SQL result equivalence is tested in PostgreSQL."""
from contextlib import contextmanager
import importlib

import pytest

store = importlib.import_module("modules.oom_sakkie.automatic_reassessment_store")


def capture_query(monkeypatch, *, action="load_latest_outcome", identity="ROOTLINE", row=None, error=None):
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): calls.append(("cursor_closed",))
        def execute(self, sql, params):
            calls.append((sql, params))
            if error: raise error
        def fetchone(self): return row
    class Connection:
        def cursor(self): return Cursor()
    @contextmanager
    def connect():
        calls.append(("connection_opened",))
        try: yield Connection()
        finally: calls.append(("connection_closed",))
    monkeypatch.setattr(store, "connect_bounded_read", connect)
    value = store._load(action, identity)
    return value, calls


@pytest.mark.parametrize("row,expected", [(None, None), ((None,), None),
    (({"status": "contained", "report_work_due": True, "next_due_at": "2030-01-01T00:00:00Z"},),
      {"status": "contained", "report_work_due": True, "next_due_at": "2030-01-01T00:00:00Z"})])
def test_latest_lookup_returns_original_payload_without_fabricating_due(monkeypatch, row, expected):
    value, calls = capture_query(monkeypatch, row=row)
    assert value == expected
    queries = [item for item in calls if len(item) == 2]
    assert len(queries) == 1  # Timestamp and tie resolution share one statement snapshot.
    assert calls[-2:] == [("cursor_closed",), ("connection_closed",)]


def test_specialist_remains_parameterized_in_both_phases(monkeypatch):
    specialist = "ROOTLINE'; select private_data; --"
    _, calls = capture_query(monkeypatch, identity=specialist)
    sql, params = next(item for item in calls if len(item) == 2)
    assert specialist not in sql
    assert params == (store.EVENT_SOURCE, specialist, store.EVENT_SOURCE, specialist)


@pytest.mark.parametrize("error", [TimeoutError("bounded"), RuntimeError("unavailable")])
def test_lookup_failure_propagates_to_existing_cadence_fallback(monkeypatch, error):
    with pytest.raises(type(error), match=str(error)):
        capture_query(monkeypatch, error=error)


def test_identity_lookup_retains_its_original_binding_and_order(monkeypatch):
    _, calls = capture_query(monkeypatch, action="load_schedule", identity="minute-key")
    sql, params = next(item for item in calls if len(item) == 2)
    assert params == (store.EVENT_SOURCE, "minute-key")
    assert " ".join(sql.split()) == (
        "select review_json->'automatic_reassessment' from public.sam_live_stock_conversation_review_events "
        "where event_source=%s and review_json->'automatic_reassessment'->>'identity'=%s "
        "order by created_at desc, review_event_id desc limit 1")


@pytest.mark.parametrize("second_fails", [False, True])
def test_actual_bounded_reader_acquires_and_closes_one_connection_per_lookup(monkeypatch, second_fails):
    import psycopg
    from modules.oom_sakkie import bounded_postgres_read as bounded
    connections = []
    class Cursor:
        def __init__(self, connection): self.connection = connection
        def __enter__(self): return self
        def __exit__(self, *args): self.connection.cursor_closed = True
        def execute(self, statement, params):
            self.connection.statements.append((statement, params))
            if second_fails and len(connections) > 1 and self.connection is connections[1]: raise TimeoutError("bounded read")
        def fetchone(self): return None
    class Connection:
        def __init__(self): self.statements = []; self.closed = False; self.cursor_closed = False
        def __enter__(self): return self
        def __exit__(self, *args): self.close()
        def close(self): self.closed = True
        def cursor(self): return Cursor(self)
    def acquire(url, **kwargs):
        assert url == "postgresql://synthetic.invalid/offline-no-network"
        assert "prepare_threshold" not in kwargs
        assert "default_transaction_read_only=on" in kwargs["options"]
        connection = Connection(); connections.append(connection); return connection
    monkeypatch.setenv("DATABASE_URL", "postgresql://synthetic.invalid/offline-no-network")
    monkeypatch.setattr(psycopg, "connect", acquire)
    monkeypatch.setattr(store, "connect_bounded_read", bounded.connect_bounded_read)
    assert store._load("load_latest_outcome", "ROOTLINE") is None
    if second_fails:
        with pytest.raises(TimeoutError, match="bounded read"):
            store._load("load_latest_outcome", "ROOTLINE")
    else:
        assert store._load("load_latest_outcome", "ROOTLINE") is None
    assert len(connections) == 2 and connections[0] is not connections[1]
    assert all(connection.closed and connection.cursor_closed for connection in connections)
    assert [len(connection.statements) for connection in connections] == [1, 1]
