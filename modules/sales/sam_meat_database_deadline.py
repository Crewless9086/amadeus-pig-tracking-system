"""Application-local PostgreSQL deadlines for read-only SAM Meat truth reads."""

from dataclasses import dataclass, field
import math
from threading import BoundedSemaphore
from time import monotonic


DEFAULT_TOTAL_SECONDS = 4.5
MAX_CONNECT_SECONDS = 3
MAX_STATEMENT_MILLISECONDS = 4000
LOCK_TIMEOUT_MILLISECONDS = 500
IDLE_TRANSACTION_TIMEOUT_MILLISECONDS = 4500
TCP_USER_TIMEOUT_MILLISECONDS = 4000
MIN_OPERATION_MILLISECONDS = 100
MAX_PROTECTED_CONNECTIONS_PER_PROCESS = 8
PROTECTED_CONNECTION_CAPACITY = BoundedSemaphore(MAX_PROTECTED_CONNECTIONS_PER_PROCESS)


class SamMeatDatabaseDeadlineExceeded(TimeoutError):
    """No safe database budget remains for another SAM Meat truth operation."""


class SamMeatDatabaseCapacityExceeded(TimeoutError):
    """The process-wide protected read-only connection budget is exhausted."""


class _ProtectedConnection:
    def __init__(self, connection, capacity):
        self._connection = connection
        self._capacity = capacity
        self._entered = None
        self._released = False

    def __enter__(self):
        try:
            self._entered = self._connection.__enter__()
            return self._entered
        except BaseException:
            self._release()
            raise

    def __exit__(self, exc_type, exc, traceback):
        try:
            return self._connection.__exit__(exc_type, exc, traceback)
        finally:
            self._release()

    def _release(self):
        if not self._released:
            self._released = True
            self._capacity.release()

    def close(self):
        try:
            return self._connection.close()
        finally:
            self._release()


@dataclass
class SamMeatDatabaseDeadline:
    total_seconds: float = DEFAULT_TOTAL_SECONDS
    clock: object = monotonic
    capacity: object = PROTECTED_CONNECTION_CAPACITY
    _started_at: float = field(init=False)

    def __post_init__(self):
        self.total_seconds = max(0.0, float(self.total_seconds))
        self._started_at = float(self.clock())

    def remaining_seconds(self):
        return max(0.0, self.total_seconds - (float(self.clock()) - self._started_at))

    def connect(self, database_url, *, row_factory=None, connect_callable=None):
        remaining = self.remaining_seconds()
        if remaining <= 0.2:
            raise SamMeatDatabaseDeadlineExceeded("sam_meat_database_deadline_exhausted")

        # Acquisition and execution caps sum to less than the remaining absolute budget.
        connect_seconds = min(
            MAX_CONNECT_SECONDS,
            max(1, int(math.floor(remaining / 2.0))),
        )
        statement_ms = min(
            MAX_STATEMENT_MILLISECONDS,
            int((remaining - connect_seconds - 0.1) * 1000),
        )
        if statement_ms < MIN_OPERATION_MILLISECONDS:
            raise SamMeatDatabaseDeadlineExceeded("sam_meat_database_deadline_exhausted")
        lock_ms = min(LOCK_TIMEOUT_MILLISECONDS, max(50, statement_ms // 4))
        idle_ms = min(
            IDLE_TRANSACTION_TIMEOUT_MILLISECONDS,
            max(statement_ms + 100, lock_ms + 100),
        )
        options = " ".join(
            (
                f"-c statement_timeout={statement_ms}",
                f"-c lock_timeout={lock_ms}",
                f"-c idle_in_transaction_session_timeout={idle_ms}",
                "-c default_transaction_read_only=on",
            )
        )
        if connect_callable is None:
            import psycopg

            connect_callable = psycopg.connect
        kwargs = {
            "autocommit": True,
            "connect_timeout": connect_seconds,
            "options": options,
            "tcp_user_timeout": TCP_USER_TIMEOUT_MILLISECONDS,
        }
        if row_factory is not None:
            kwargs["row_factory"] = row_factory
        if not self.capacity.acquire(blocking=False):
            raise SamMeatDatabaseCapacityExceeded(
                "sam_meat_database_connection_capacity_exhausted"
            )
        try:
            connection = connect_callable(database_url, **kwargs)
        except BaseException:
            self.capacity.release()
            raise
        return _ProtectedConnection(connection, self.capacity)

    def connection_factory(self, *, connect_callable=None):
        return lambda database_url: self.connect(
            database_url,
            connect_callable=connect_callable,
        )
