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


class RootlineConnectionDeadlineExceeded(TimeoutError):
    """Hard wall-clock connection boundary reached before PostgreSQL was usable."""


def connect_bounded_read(*, database_url=None, connect=None):
    return connect_bounded_postgres(database_url=database_url, connect=connect,
                                    read_only=True)


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
    read_only_option = "-c default_transaction_read_only=on " if read_only else ""
    connect_kwargs = {
        "connect_timeout": CONNECT_TIMEOUT_SECONDS,
        "options": (read_only_option +
                    f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
                    f"-c lock_timeout={LOCK_TIMEOUT_MS}"),
    }
    if not enforce_transaction_local:
        return connect(url, **connect_kwargs)

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
    return _connect_with_wall_clock_deadline(
        acquire_and_configure, url, connect_kwargs, deadline)


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
