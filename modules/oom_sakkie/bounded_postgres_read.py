"""Bounded, read-only PostgreSQL acquisition for synchronous owner paths."""
from __future__ import annotations

import os

CONNECT_TIMEOUT_SECONDS = 3
STATEMENT_TIMEOUT_MS = 3000
LOCK_TIMEOUT_MS = 1000
OWNER_REQUEST_DEADLINE_SECONDS = 12


def connect_bounded_read(*, database_url=None, connect=None):
    return connect_bounded_postgres(database_url=database_url, connect=connect,
                                    read_only=True)


def connect_bounded_postgres(*, database_url=None, connect=None, read_only=False):
    """Acquire one bounded PostgreSQL session; context managers own cleanup."""
    url = str(database_url or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("bounded_database_url_unavailable")
    if connect is None:
        import psycopg
        connect = psycopg.connect
    read_only_option = "-c default_transaction_read_only=on " if read_only else ""
    return connect(
        url,
        connect_timeout=CONNECT_TIMEOUT_SECONDS,
        options=(read_only_option +
                 f"-c statement_timeout={STATEMENT_TIMEOUT_MS} "
                 f"-c lock_timeout={LOCK_TIMEOUT_MS}"),
    )


def is_database_unavailable(exc):
    """Classify psycopg acquisition/query deadline failures without broad catches."""
    return (exc.__class__.__module__.split(".", 1)[0] == "psycopg"
            or exc.__class__.__name__ in {
                "OperationalError", "ConnectionTimeout", "QueryCanceled",
                "QueryCanceledError", "LockNotAvailable", "PoolTimeout"})
