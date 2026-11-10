"""Bounded, read-only PostgreSQL acquisition for synchronous owner paths."""
from __future__ import annotations

import os
import hashlib
from contextlib import contextmanager
import re
from decimal import Decimal
import threading
import time

CONNECT_TIMEOUT_SECONDS = 3
STATEMENT_TIMEOUT_MS = 3000
LOCK_TIMEOUT_MS = 1000
OWNER_REQUEST_DEADLINE_SECONDS = 12
ROOTLINE_CONNECT_DEADLINE_SECONDS = 5
_FALLBACK_CONNECT_SLOTS = threading.BoundedSemaphore(8)

# Exact SQL bytes of the existing private no-send contract only. Unknown SQL
# permanently leaves the reuse path; prefixes do not establish settings safety.
# These INSERTs depend on the qualified rejection-only event-table trigger.
_ROOTLINE_PRIVATE_SQL_SHA256 = frozenset({
    # rootline_ewelink_oauth_store.py: select token_binding_id,provider_account_digest,device_id,
    "02a9cd24f7c7682c259c7b2d269303a9e611ee2a5170e9080955306480d1c100",
    # rootline_ewelink_request_budget.py: with stamp as materialized (select clock_timestamp() as at),
    "1ac0384674c7c35676dda33abead0096f1f3942a758906c9b48d023bd9008a4b",
    # rootline_irrigation_execution_store.py: insert into public.sam_live_stock_conversation_review_events
    "1b8ba0058e849a33491806b786a808e38776b812ef3deb26624fb63460cf00cf",
    # sam_live_stock_launch_control.py: insert into public.sam_live_stock_conversation_review_events (
    "2f7a0c834916a26f17b890a553b57dde3b68700b90593ccf790e78e227894a83",
    # rootline_ewelink_request_budget.py: with ranked as (
    "48001f7d5f96bc44cdfdd4115ceff670405b894f71b7f747a3b81698c6d42a65",
    # rootline_ewelink_request_budget.py: select clock_timestamp()
    "4c502774edf949ff930d80b711b719e6852a76df012e9c2f0e4409b53b0b0cc0",
    # rootline_ewelink_request_budget.py: select clock_timestamp(),pg_backend_pid(),exists(select 1 from pg_locks where pid=pg_backe
    "755db8b8300393d892f55aee56556a056aea753721e6b6234115491669539494",
    # rootline_ewelink_request_budget.py: select pg_try_advisory_xact_lock(%s),current_setting('transaction_isolation'),pg_backend_p
    "7b954eefffb7852807997a4683b462ef1edafd84090ac5e2895dcc16227c4556",
    # rootline_irrigation_execution_store.py: select pg_advisory_xact_lock(%s)
    "a3ae97780e4389008d2f28f8c1365252fb73095a28e04788ba77c1c5b2c35066",
    # rootline_irrigation_execution_store.py: select review_json->'rootline_execution'
    "a5dc0392afb38780a2ef73a445b0bc3d91898857d14410bc4ead595845cd52c0",
})
_CONFIGURATION_SQL = ("select set_config(\'statement_timeout\',%s,true),"
    "set_config(\'lock_timeout\',%s,true),current_setting(\'transaction_isolation\')")
_ISOLATION_SQL = "set transaction isolation level read committed"


def _native_begin_deadline(deadline):
    from modules.telemetry.rootline_cycle_budget import work_deadline, RootlineCycleDeadlineExceeded
    current = work_deadline()
    limit = min(deadline, current) if current is not None else deadline
    if time.monotonic() >= limit:
        raise RootlineCycleDeadlineExceeded("rootline_native_begin_deadline")
    return limit


def _require_native_begin_state(connection, *, idle):
    import psycopg
    from psycopg.pq import PipelineStatus, TransactionStatus
    # A writable attribute or an injected/native-looking proxy is not ownership.
    if (type(connection) is not psycopg.Connection or connection.closed
            or connection.broken or connection.autocommit is not False
            or connection.pgconn.pipeline_status != PipelineStatus.OFF
            or connection._num_transactions != 0
            or connection.info.transaction_status not in
                ({TransactionStatus.IDLE} if idle else {TransactionStatus.IDLE, TransactionStatus.INTRANS})):
        raise RuntimeError("rootline_native_begin_state_unproven")


def _install_native_read_committed(connection, deadline):
    import psycopg
    _native_begin_deadline(deadline)
    _require_native_begin_state(connection, idle=True)
    # Public native setter configures the next BEGIN only. It is never server
    # proof; the existing combined verifier must acknowledge every transaction.
    connection.isolation_level = psycopg.IsolationLevel.READ_COMMITTED
    _require_native_begin_state(connection, idle=True)
    if connection.isolation_level != psycopg.IsolationLevel.READ_COMMITTED:
        raise RuntimeError("rootline_native_begin_intent_unproven")
    _native_begin_deadline(deadline)


def _local_timeouts_match(row, statement, lock):
    if not isinstance(row, (tuple, list)) or len(row) != 2:
        return False
    for value, expected in zip(row, (statement, lock)):
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)(ms|s|min|h)?", str(value))
        if not match or Decimal(match[1]) * {None: 1, "ms": 1, "s": 1000,
                "min": 60000, "h": 3600000}[match[2]] != expected:
            return False
    return True


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
                                      connect_deadline_seconds=None, reuse_local_settings=False,
                                      read_committed=False, native_begin_read_committed=False):
    """ROOTLINE pooled session with transaction-local deadline enforcement."""
    return connect_bounded_postgres(database_url=database_url, connect=connect,
        read_only=read_only, enforce_transaction_local=True,
        connect_deadline_seconds=connect_deadline_seconds,
        reuse_local_settings=reuse_local_settings, read_committed=read_committed,
        native_begin_read_committed=native_begin_read_committed)


def connect_bounded_postgres(*, database_url=None, connect=None, read_only=False,
                             enforce_transaction_local=False,
                             connect_deadline_seconds=None, reuse_local_settings=False,
                             read_committed=False, native_begin_read_committed=False):
    """Acquire one bounded PostgreSQL session; context managers own cleanup."""
    url = str(database_url or os.environ.get("DATABASE_URL") or "").strip()
    if not url:
        raise RuntimeError("bounded_database_url_unavailable")
    owned_native_requested = native_begin_read_committed and connect is None
    if native_begin_read_committed and (
            not enforce_transaction_local or not reuse_local_settings or not read_committed or read_only):
        raise ValueError("rootline_native_begin_scope_invalid")
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

    native_acquisition = {"connection": None}

    def acquire_and_configure(target_url, **target_kwargs):
        connection = connect(target_url, **target_kwargs)
        # Select the unchanged legacy path BEFORE any mutation for injected or
        # non-native acquisitions. Once native setup starts there is no fallback.
        try:
            native_begin = False
            if owned_native_requested and cycle_deadline is not None:
                import psycopg
                native_begin = type(connection) is psycopg.Connection
            if native_begin:
                _install_native_read_committed(connection, acquisition_deadline)
            # Supabase transaction pooling may accept but not apply startup
            # ``options``. Establish the same bounds inside this transaction.
            # SET LOCAL cannot leak through a pooled server connection.
            with connection.cursor() as cursor:
                if read_committed and not native_begin:
                    # Must precede any SELECT (including set_config) on poolers.
                    cursor.execute("set transaction isolation level read committed", ())
                if read_only:
                    cursor.execute("set transaction read only", ())
                if reuse_local_settings:
                    if native_begin:
                        _native_begin_deadline(acquisition_deadline)
                    cursor.execute("select set_config('statement_timeout',%s,true),"
                        "set_config('lock_timeout',%s,true)" +
                        (",current_setting('transaction_isolation')" if read_committed else ""),
                        (str(STATEMENT_TIMEOUT_MS), str(LOCK_TIMEOUT_MS)))
                    row = cursor.fetchone()
                    if (not row or not _local_timeouts_match(row[:2], STATEMENT_TIMEOUT_MS, LOCK_TIMEOUT_MS)
                            or (read_committed and (len(row) != 3 or row[2] != "read committed"))):
                        raise RuntimeError("rootline_transaction_settings_unproven")
                else:
                    cursor.execute(f"set local statement_timeout='{STATEMENT_TIMEOUT_MS}ms'", ())
                    cursor.execute(f"set local lock_timeout='{LOCK_TIMEOUT_MS}ms'", ())
                    if read_committed:
                        cursor.execute("select current_setting('transaction_isolation')", ())
                        if cursor.fetchone() != ("read committed",):
                            raise RuntimeError("rootline_transaction_isolation_unproven")
            if native_begin:
                from psycopg.pq import TransactionStatus
                _native_begin_deadline(acquisition_deadline)
                _require_native_begin_state(connection, idle=False)
                if connection.info.transaction_status != TransactionStatus.INTRANS:
                    raise RuntimeError("rootline_transaction_settings_unproven")
                native_acquisition["connection"] = connection
            return connection
        except BaseException:
            try:
                connection.rollback()
            finally:
                connection.close()
            raise

    deadline = (ROOTLINE_CONNECT_DEADLINE_SECONDS if connect_deadline_seconds is None
                else float(connect_deadline_seconds))
    acquisition_deadline = time.monotonic() + deadline
    if cycle_deadline is not None:
        acquisition_deadline = min(acquisition_deadline, cycle_deadline)
    connection = _connect_with_wall_clock_deadline(
        acquire_and_configure, url, connect_kwargs, deadline)
    return (_CycleBudgetConnection(connection, cycle_deadline,
        reuse_local_settings=reuse_local_settings,
        installed_timeout=STATEMENT_TIMEOUT_MS if reuse_local_settings else None,
        installed_lock_timeout=LOCK_TIMEOUT_MS if reuse_local_settings else None,
        read_committed=read_committed, native_begin_connection=native_acquisition["connection"])
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
    def __init__(self, connection, deadline, *, reuse_local_settings=False, installed_timeout=None,
                 installed_lock_timeout=None, read_committed=False, native_begin_connection=None):
        self._connection, self.deadline = connection, deadline
        self._native_begin_connection = native_begin_connection
        # Scoped to the private no-send path, never enabled for ordinary users.
        self.reuse_local_settings = reuse_local_settings
        self._installed_timeout = installed_timeout
        self._installed_lock_timeout = installed_lock_timeout
        self._read_committed = read_committed
        self._reuse_disabled = False

    def _require_native_owner(self):
        if (self._reuse_disabled or self._connection is not self._native_begin_connection):
            raise RuntimeError("rootline_native_begin_ownership_lost")
        _require_native_begin_state(self._connection, idle=False)

    @property
    def connection(self):
        # A raw borrower can change settings/transaction state behind the wrapper.
        self._disable_reuse()
        return self._connection

    def _disable_reuse(self):
        # A retained public raw alias can mutate settings later, after a new
        # verification. This lifetime restriction cannot be reset by configure.
        self._reuse_disabled = True
        self._invalidate()

    def _invalidate(self):
        self._installed_timeout = None
        self._installed_lock_timeout = None
        self._read_committed = False

    def commit(self):
        self._invalidate()
        return self._connection.commit()

    def rollback(self):
        self._invalidate()
        return self._connection.rollback()

    def close(self):
        self._invalidate()
        return self._connection.close()

    def transaction(self, *args, **kwargs):
        self._invalidate()
        transaction = self._connection.transaction(*args, **kwargs)

        @contextmanager
        def scope():
            self._invalidate()
            try:
                with transaction as native:
                    # Preserve the native returned Transaction object and its
                    # semantics. It exposes a raw connection, so reuse cannot
                    # be trusted again even after this context has exited.
                    self._disable_reuse()
                    yield native
            finally:
                self._invalidate()
        return scope()

    def __enter__(self):
        try:
            self._connection.__enter__()
        except BaseException:
            self._invalidate()
            raise
        return self

    def __exit__(self, *args):
        self._invalidate()
        try:
            return self._connection.__exit__(*args)
        finally:
            self._invalidate()

    def _current_deadline(self):
        from modules.telemetry.rootline_cycle_budget import work_deadline, RootlineCycleDeadlineExceeded
        current = work_deadline()
        deadline = min(self.deadline, current) if current is not None else self.deadline
        if deadline <= time.monotonic():
            raise RootlineCycleDeadlineExceeded("rootline_cycle_database_deadline")
        return deadline

    def configure_transaction_timeouts(self, statement, lock, *, read_committed=False):
        """Only this fixed verifier may retain its pre-statement timeout proof."""
        from psycopg.pq import TransactionStatus
        statement, lock = int(statement), int(lock)
        if not (0 < statement <= STATEMENT_TIMEOUT_MS and 0 < lock <= LOCK_TIMEOUT_MS):
            raise ValueError("rootline_transaction_settings_invalid")
        deadline = self._current_deadline()
        if self._native_begin_connection is not None:
            self._require_native_owner()
        if (self.reuse_local_settings and not self._reuse_disabled
                and self._connection.info.transaction_status == TransactionStatus.INTRANS
                and self._read_committed and read_committed
                and self._installed_timeout is not None
                and 0 < self._installed_timeout <= min(statement, int((deadline-time.monotonic())*1000))
                and self._installed_lock_timeout is not None
                and 0 < self._installed_lock_timeout <= lock):
            return
        cursor = self.cursor()
        try:
            if read_committed and not self._read_committed:
                if self._connection.info.transaction_status != TransactionStatus.IDLE:
                    raise RuntimeError("rootline_transaction_isolation_unproven")
                if self._native_begin_connection is not None:
                    _install_native_read_committed(self._connection, deadline)
                else:
                    cursor._configure_isolation()
            row = cursor._configure_bounds(statement, lock)
            if (not isinstance(row, (tuple, list)) or len(row) != 3
                    or not _local_timeouts_match(row[:2], statement, lock)
                    or (read_committed and row[2] != "read committed")):
                raise RuntimeError("rootline_transaction_settings_unproven")
            # Recheck admission after the acknowledgement too. A no-SQL return
            # never admits a later SQL statement or bypasses its tighter bound.
            self._current_deadline()
            if self.reuse_local_settings and not self._reuse_disabled:
                self._installed_timeout = statement
                self._installed_lock_timeout = lock
                self._read_committed = row[2] == "read committed"
        except BaseException:
            self._invalidate()
            raise
        finally:
            cursor.close()

    def cursor(self, *args, **kwargs):
        if self._native_begin_connection is not None and (args or kwargs):
            self._disable_reuse()
            raise RuntimeError("rootline_native_begin_cursor_contract_changed")
        return _CycleBudgetCursor(self._connection.cursor(*args, **kwargs), self.deadline, owner=self)

    def execute(self, statement, params=None, **kwargs):
        cursor = self.cursor()
        return cursor.execute(statement, params, **kwargs)

    def __getattr__(self, name):
        if name not in {"closed", "broken"}:
            self._disable_reuse()
        return getattr(self._connection, name)


class _CycleBudgetCursor(ReadBudgetCursor):
    def __init__(self, cursor, deadline, *, owner=None):
        self._cursor, self.deadline, self.owner = cursor, deadline, owner

    @property
    def cursor(self):
        if self.owner is not None:
            self.owner._disable_reuse()
        return self._cursor

    @property
    def connection(self):
        if self.owner is not None:
            self.owner._disable_reuse()
        return self._cursor.connection

    def __getattr__(self, name):
        if self.owner is not None and name not in {
                "rowcount", "description", "statusmessage", "closed"}:
            self.owner._disable_reuse()
        return getattr(self._cursor, name)

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def fetchmany(self, *args, **kwargs):
        return self._cursor.fetchmany(*args, **kwargs)

    def close(self):
        return self._cursor.close()

    def __enter__(self):
        self._cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self._cursor.__exit__(*args)

    def _deadline(self):
        if self.owner is not None:
            return self.owner._current_deadline()
        from modules.telemetry.rootline_cycle_budget import work_deadline, RootlineCycleDeadlineExceeded
        current = work_deadline()
        deadline = min(self.deadline, current) if current is not None else self.deadline
        if deadline <= time.monotonic():
            raise RootlineCycleDeadlineExceeded("rootline_cycle_database_deadline")
        return deadline

    def _guard(self, deadline):
        from modules.telemetry.rootline_cycle_budget import RootlineCycleDeadlineExceeded
        owner = self.owner
        ephemeral_timeout = None
        for _ in range(3):
            remaining_ms = int((deadline-time.monotonic())*1000)
            if remaining_ms <= 0:
                raise RootlineCycleDeadlineExceeded("rootline_cycle_database_deadline")
            installed = ephemeral_timeout if owner._reuse_disabled else owner._installed_timeout
            if (installed is not None
                    and 0 < installed <= min(STATEMENT_TIMEOUT_MS, remaining_ms)):
                return
            setting = min(STATEMENT_TIMEOUT_MS, max(1, remaining_ms//2))
            self._cursor.execute(f"set local statement_timeout='{setting}ms'")
            if owner._reuse_disabled:
                # This acknowledgement guards only this call. A retained raw
                # alias prevents caching it for any subsequent operation.
                ephemeral_timeout = setting
            else:
                owner._installed_timeout = setting
        raise RootlineCycleDeadlineExceeded("rootline_cycle_database_deadline")

    def _configure_isolation(self):
        # Fixed internal statement; no caller-provided SQL is admitted here.
        self.owner._invalidate()
        try:
            self._guard(self._deadline())
            self._cursor.execute(_ISOLATION_SQL)
        except BaseException:
            self.owner._invalidate()
            raise

    def _configure_bounds(self, statement, lock):
        # Only the acknowledged bound guarding this exact verifier may survive
        # until execution. The verifier mutates settings; discard all knowledge
        # before inspecting its acknowledgement and never trust a partial row.
        try:
            self._guard(self._deadline())
            self._cursor.execute(_CONFIGURATION_SQL, (str(statement), str(lock)))
        finally:
            self.owner._invalidate()
        return self._cursor.fetchone()

    def execute(self, statement, params=None, **kwargs):
        from psycopg.pq import TransactionStatus
        from modules.telemetry.rootline_cycle_budget import RootlineCycleDeadlineExceeded
        deadline = self._deadline()
        owner = self.owner
        if owner is not None and owner._native_begin_connection is not None:
            owner._require_native_owner()
            if (not owner._read_committed
                    or owner._connection.info.transaction_status != TransactionStatus.INTRANS):
                raise RuntimeError("rootline_transaction_isolation_unproven")
        if owner is not None and owner.reuse_local_settings and not owner._reuse_disabled:
            digest = hashlib.sha256(statement.encode()).hexdigest() if isinstance(statement, str) else None
            if digest not in _ROOTLINE_PRIVATE_SQL_SHA256:
                owner._disable_reuse()
                if owner._native_begin_connection is not None:
                    raise RuntimeError("rootline_native_begin_sql_contract_changed")
            elif (owner._connection.info.transaction_status == TransactionStatus.INTRANS
                    and owner._read_committed and owner._installed_lock_timeout is not None
                    and 0 < owner._installed_lock_timeout <= LOCK_TIMEOUT_MS):
                try:
                    self._guard(deadline)
                    self._cursor.execute(statement, params, **kwargs)
                except BaseException:
                    owner._invalidate()
                    raise
                return self
        if owner is not None:
            owner._invalidate()
        milliseconds = max(1, min(STATEMENT_TIMEOUT_MS, int((deadline-time.monotonic())*1000)))
        self._cursor.execute(f"set local statement_timeout='{milliseconds}ms'")
        if time.monotonic() >= deadline:
            raise RootlineCycleDeadlineExceeded("rootline_cycle_database_deadline")
        self._cursor.execute(statement, params, **kwargs)
        return self
