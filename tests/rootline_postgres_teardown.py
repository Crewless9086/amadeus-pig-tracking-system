"""Test-only acknowledgement of closed fixture clients; never terminate sessions."""
import time

# Only these PostgreSQL-owned processes are irrelevant to client cleanup.
_BACKGROUND_TYPES = frozenset({"autovacuum worker", "parallel worker"})
_ACTIVITY = """select pid, application_name, backend_type, state
from pg_stat_activity
where datname=current_database() and pid<>pg_backend_pid()"""


def wait_for_closed_fixture_clients(observer, owned, *, timeout=1.0,
                                    clock=time.monotonic, wait=time.sleep):
    """Wait only for server disappearance of already-closed, exact owned clients.

    Autocommit gives every observation a fresh statistics snapshot. Unknown
    backend kinds and foreign clients fail immediately. PID plus unique startup
    application_name prevents a reused PID being mistaken for our connection.
    Diagnostic fields deliberately omit SQL text, DSNs and application names.
    """
    assert observer.autocommit, "cleanup observer must use fresh autocommit snapshots"
    assert 0 < timeout <= 1.0, "disconnect acknowledgement bound must be at most one second"
    assert all(db.closed for db in owned.values()), "owned fixture connection still open"
    deadline = clock() + timeout
    while True:
        clients = []
        diagnostics = []
        for pid, name, kind, state in observer.execute(_ACTIVITY).fetchall():
            identity = (pid, name)
            detail = {"pid": pid, "backend_type": kind, "state": state,
                      "owned": identity in owned}
            if kind in _BACKGROUND_TYPES:
                continue
            assert kind == "client backend", ("unknown backend type", detail)
            assert identity in owned, ("unrelated client remains", detail)
            assert owned[identity].closed, ("owned fixture connection still open", detail)
            clients.append(identity)
            diagnostics.append(detail)
        if not clients:
            assert clock() <= deadline, 'disconnect acknowledgement deadline exceeded'
            return clients
        remaining = deadline - clock()
        assert remaining > 0, ("closed fixture clients not acknowledged by server", diagnostics)
        # This is a conditional disconnect acknowledgement, never a blanket delay.
        wait(min(0.01, remaining))
