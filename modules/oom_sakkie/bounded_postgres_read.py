"""Bounded, read-only PostgreSQL acquisition for synchronous owner paths."""
from __future__ import annotations

import os
import threading
import time

CONNECT_TIMEOUT_SECONDS = 3
STATEMENT_TIMEOUT_MS = 3000
LOCK_TIMEOUT_MS = 1000
OWNER_REQUEST_DEADLINE_SECONDS = 12
ROOTLINE_CONNECT_DEADLINE_SECONDS = 5
_FALLBACK_CONNECT_SLOTS = threading.BoundedSemaphore(8)


class ReadBudgetCursor:
    """Apply one wall-clock read budget across every statement in a snapshot."""
    def __init__(self, cursor, deadline, *, failure_kind="bounded_read_deadline"):
        self.cursor, self.deadline, self.failure_kind = cursor, deadline, failure_kind

    def execute(self, statement, params=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(self.failure_kind)
        self.cursor.execute("select set_config('statement_timeout',%s,true)",
            (str(max(1, min(STATEMENT_TIMEOUT_MS, int(remaining * 1000)))),))
        return self.cursor.execute(statement, params)

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class RootlineConnectionDeadlineExceeded(TimeoutError):
    """Hard wall-clock connection boundary reached before PostgreSQL was usable."""


def connect_bounded_read(*, database_url=None, connect=None,
                         connect_deadline_seconds=3):
    return connect_bounded_postgres(database_url=database_url, connect=connect,
                                    read_only=True,
                                    connect_deadline_seconds=connect_deadline_seconds)


def connect_bounded_rootline_postgres(*, database_url=None, connect=None, read_only=True,
                                      connect_deadline_seconds=None):
    """ROOTLINE pooled session with transaction-local deadline enforcement."""
    return connect_bounded_postgres(database_url=database_url, connect=connect,
        read_only=read_only, enforce_transaction_local=True,
        connect_deadline_seconds=connect_deadline_seconds)


def connect_bounded_postgres(*, database_url=None, connect=None, read_only=False,
                             enforce_transaction_local=False,
                             connect_deadline_seconds=None):
    """Acquire one bounded PostgreSQL session; context managers own cleanup."""
    url = str(database_url or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("bounded_database_url_unavailable")
    if connect is None:
        import psycopg
        connect = psycopg.connect
    from modules.telemetry.rootline_cycle_budget import work_deadline, remaining_seconds
    cycle_deadline = work_deadline()
    if cycle_deadline is not None:
        connect_deadline_seconds = remaining_seconds(
            connect_deadline_seconds or ROOTLINE_CONNECT_DEADLINE_SECONDS)
    read_only_option = "-c default_transaction_read_only=on " if read_only else ""
    connect_kwargs = {
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "options": (read_only_option +
                    f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
                    f"-c lock_timeout={LOCK_TIMEOUT_MS}"),
    }
    if not enforce_transaction_local:
        if connect_deadline_seconds is None:
            return connect(url, **connect_kwargs)
        connection = _connect_with_wall_clock_deadline(
            connect, url, connect_kwargs, float(connect_deadline_seconds))
        return (_CycleBudgetConnection(connection, cycle_deadline)
            if cycle_deadline is not None else connection)

    def acquire_and_configure(target_url, **target_kwargs):
        connection = connect(target_url, **target_kwargs)
        try:
            # Supabase transaction pooling may accept but not apply startup
            # ``options``. Establish the same bounds inside this transaction.
            # SET LOCAL cannot leak through a pooled server connection.
            with connection.cursor() as cursor:
                if read_only:
                    cursor.execute("set transaction read only", ())
                cursor.execute(f"set local statement_timeout='{STATEMENT_TIMEOUT_MS}ms'", ())
                cursor.execute(f"set local lock_timeout='{LOCK_TIMEOUT_MS}ms'", ())
            return connection
        except BaseException:
            try:
                connection.rollback()
            finally:
                connection.close()
            raise

    deadline = (ROOTLINE_CONNECT_DEADLINE_SECONDS if connect_deadline_seconds is None
                else float(connect_deadline_seconds))
    connection = _connect_with_wall_clock_deadline(
        acquire_and_configure, url, connect_kwargs, deadline)
    return (_CycleBudgetConnection(connection, cycle_deadline)
        if cycle_deadline is not None else connection)


def is_database_unavailable(exc):
    """Classify psycopg acquisition/query deadline failures without broad catches."""
    return (exc.__class__.__module__.split(".", 1)[0] == "psycopg"
            or exc.__class__.__name__ in {
                "OperationalError", "ConnectionTimeout", "QueryCanceled",
                "QueryCanceledError", "LockNotAvailable", "PoolTimeout",
                "RootlineConnectionDeadlineExceeded"})


def _connect_with_wall_clock_deadline(connect, url, kwargs, deadline_seconds):
    """Bound DNS/socket/TLS/libpq acquisition independently of driver retries."""
    if deadline_seconds <= 0:
        raise RootlineConnectionDeadlineExceeded("rootline_database_connect_deadline_invalid")
    return _thread_bounded_connect(connect, url, kwargs, deadline_seconds)


def _thread_bounded_connect(connect, url, kwargs, deadline_seconds):
    if not _FALLBACK_CONNECT_SLOTS.acquire(blocking=False):
        raise RootlineConnectionDeadlineExceeded(
            "rootline_database_connect_slots_exhausted")
    condition = threading.Condition()
    state = {"ready": False, "success": False, "value": None,
             "decision": None}

    def attempt():
        connection_to_close = None
        try:
            value = connect(url, **kwargs); success = True
        except BaseException as exc:
            value = exc; success = False
        try:
            with condition:
                state.update(ready=True, success=success, value=value)
                condition.notify_all()
                while state["decision"] is None:
                    condition.wait()
                if state["decision"] == "abandoned" and success:
                    connection_to_close = value
        finally:
            _FALLBACK_CONNECT_SLOTS.release()
            if connection_to_close is not None:
                try:
                    connection_to_close.close()
                except Exception:
                    pass

    worker = threading.Thread(target=attempt, name="rootline-bounded-db-connect", daemon=True)
    deadline = time.monotonic() + deadline_seconds
    try:
        worker.start()
    except BaseException as exc:
        _FALLBACK_CONNECT_SLOTS.release()
        raise RootlineConnectionDeadlineExceeded(
            "rootline_database_connect_worker_start_failed") from exc
    try:
        with condition:
            while not state["ready"]:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    state["decision"] = "abandoned"
                    condition.notify_all()
                    raise RootlineConnectionDeadlineExceeded(
                        "rootline_database_connect_wall_clock_deadline_exceeded")
                condition.wait(remaining)
            if time.monotonic() >= deadline:
                state["decision"] = "abandoned"
                condition.notify_all()
                raise RootlineConnectionDeadlineExceeded(
                    "rootline_database_connect_wall_clock_deadline_exceeded")
            state["decision"] = "accepted"
            condition.notify_all()
            success, value = state["success"], state["value"]
    except BaseException:
        with condition:
            if state["decision"] is None:
                state["decision"] = "abandoned"
                condition.notify_all()
        raise
    if success:
        return value
    raise value


class _CycleBudgetConnection:
    """Borrow a synchronous connection under one request's remaining budget.

    No mutation is moved to a worker. The native connection context retains
    commit/rollback ownership; expiry inside it rolls back the current work.
    """
    def __init__(self, connection, deadline):
        self.connection, self.deadline = connection, deadline

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def cursor(self, *args, **kwargs):
        return _CycleBudgetCursor(self.connection.cursor(*args, **kwargs), self.deadline)

    def execute(self, statement, params=None, **kwargs):
        cursor = self.cursor()
        return cursor.execute(statement, params, **kwargs)

    def __getattr__(self, name):
        return getattr(self.connection, name)


class _CycleBudgetCursor(ReadBudgetCursor):
    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def execute(self, statement, params=None, **kwargs):
        from modules.telemetry.rootline_cycle_budget import RootlineCycleDeadlineExceeded
        remaining = self.deadline-time.monotonic()
        if remaining <= 0:
            raise RootlineCycleDeadlineExceeded("rootline_cycle_database_deadline")
        milliseconds = max(1, min(STATEMENT_TIMEOUT_MS, int(remaining*1000)))
        # SET LOCAL does not establish a snapshot. A caller may still choose
        # REPEATABLE READ before its first data query on this transaction.
        self.cursor.execute(f"set local statement_timeout='{milliseconds}ms'")
        if time.monotonic() >= self.deadline:
            raise RootlineCycleDeadlineExceeded("rootline_cycle_database_deadline")
        self.cursor.execute(statement, params, **kwargs)
        return self
