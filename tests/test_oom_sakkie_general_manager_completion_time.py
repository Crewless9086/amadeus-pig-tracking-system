"""Real cycle/claim/event paths with synthetic database I/O and a controlled UTC clock."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from modules.oom_sakkie import general_manager_worker as worker

START = datetime(2026, 10, 18, 14, 30, tzinfo=timezone.utc)


class Database:
    def __init__(self, *, rows=True, failed=False, deferred=False, audit_unavailable=False,
                 frozen=False):
        self.commands = []
        self.elapsed = 0
        self.connections = 0
        self.closed = []
        self.owner = None
        self.lease = None
        self.rows = rows
        self.failed = failed
        self.deferred = deferred
        self.audit_unavailable = audit_unavailable
        self.frozen = frozen
        self.case = ('OOM-CASE-TIMING', 'sam:customer:timing', 'SAM', 'due',
            'waiting_reassessment', 'd' * 64, ['conversation:synthetic'],
            ['customer_follow_up'], 'Customer follow-up is unresolved.',
            'Reassess current evidence.', START, 1, None)

    def connect(self):
        self.connections += 1
        final = self.connections == (3 if self.failed or not self.rows else 4)
        if final and self.audit_unavailable:
            raise OSError('synthetic audit connection unavailable')
        db = self

        class Connection:
            def __enter__(self):
                if final and not db.frozen:
                    db.elapsed += 5
                return self
            def __exit__(self, *_args): return False
            def cursor(self): return Cursor()
            def close(self): db.closed.append(self)

        class Cursor:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def execute(self, sql, params=None):
                self.sql = sql
                db.commands.append((sql, params))
                if 'assigned_worker_id=%s,lease_until=%s,last_heartbeat_at=%s' in sql:
                    db.owner, db.lease = params[:2]
                if sql.startswith('with expected as') and not db.frozen:
                    db.elapsed = 26
            def fetchall(self):
                if 'join eligible' in self.sql:
                    return [db.case] if db.rows else []
                if self.sql.startswith('with expected as'):
                    return [(db.case[0],)]
                return []
            def fetchone(self):
                return (1, 'd' * 64, None, 'delegated', db.owner, db.lease)
        return Connection()

    def deliver(self, case, **_kwargs):
        if not self.frozen:
            self.elapsed = 26
        if self.failed:
            raise worker.ManagerCaseError('synthetic_cycle_failure')
        # Real existing SAM suppression; no provider/domain write path is called.
        return worker.deliver_farm_manager_case(case)


def cycle(monkeypatch, db):
    class UTCClock(datetime):
        @classmethod
        def now(cls, tz=None):
            current = START + timedelta(seconds=db.elapsed)
            return current.astimezone(tz) if tz else current.replace(tzinfo=None)

    monkeypatch.setattr(worker, 'datetime', UTCClock)
    monkeypatch.setattr(worker, 'time', SimpleNamespace(monotonic=lambda: float(db.elapsed)))
    audit = worker.build_scheduled_brain_guard_audit(source_revision='synthetic-source', now=START,
        alignment_result={'version': 'fixture', 'passed': True, 'findings': [], 'checked_files': []})
    return worker.PostgresManagerCaseStore(connect_factory=db.connect).run_cycle(
        [], now=START, source_revision='synthetic-source', deliver=db.deliver,
        brain_guard_audit=audit, deadline_monotonic=20 if db.deferred else None)


def terminal(db, *, failed=False):
    marker = 'status,case_counts,completed_at' if failed else 'set heartbeat_at=%s'
    matches = [params for sql, params in db.commands
               if 'oom_manager_worker_cycles' in sql and marker in sql]
    assert len(matches) == 1
    return matches[0]


def assert_start_unchanged(db, result):
    start = next(params for sql, params in db.commands
                 if 'oom_manager_worker_cycles' in sql and 'completed_at' not in sql)
    assert start[4] == start[5] == START
    assert start[6] == START + worker.CADENCE
    assert result['cycle_id'].startswith('OOM-MANAGER-CYCLE-20261018T143000000000Z-')
    assert result['next_cycle_at'] == (START + worker.CADENCE).isoformat()


def test_pending_event_precedes_fresh_success_finish(monkeypatch):
    db = Database()
    result = cycle(monkeypatch, db)
    pending = [params for sql, params in db.commands
               if 'insert into app_private.oom_manager_case_events' in sql
               and params[3] == 'delivery_suppressed']
    assert len(pending) == 1
    assert pending[0][-1] == START + timedelta(seconds=26)
    assert 'non_farm_case_delivery_suppressed' in pending[0][-2]
    end = terminal(db)
    assert result['success'] is True and end[2] == 'completed'
    assert end[0] == end[4] == START + timedelta(seconds=31)
    assert START < pending[0][-1] < end[4]
    assert result['heartbeat_at'] == end[0].isoformat()
    assert_start_unchanged(db, result)


def test_failure_finish_is_sampled_after_failure_connection_setup(monkeypatch):
    db = Database(failed=True)
    result = cycle(monkeypatch, db)
    end = terminal(db, failed=True)
    assert result['status'] == 'general_manager_cycle_failed'
    assert end[4] == START
    assert end[5] == end[8] == START + timedelta(seconds=31)
    assert result['heartbeat_at'] == end[5].isoformat()
    assert_start_unchanged(db, result)


def test_deferred_cycle_has_fresh_failed_finish_without_delivery(monkeypatch):
    db = Database(deferred=True)
    db.deliver = lambda *_a, **_k: pytest.fail('deferred work must not dispatch')
    result = cycle(monkeypatch, db)
    end = terminal(db)
    assert result['status'] == 'general_manager_cycle_deadline_contained'
    assert result['deadline_deferrals'] == 1 and end[2] == 'failed'
    assert end[0] == end[4] == START + timedelta(seconds=31)
    assert result['heartbeat_at'] == end[0].isoformat()
    assert_start_unchanged(db, result)


def test_failed_audit_connection_keeps_fresh_returned_failure_observation(monkeypatch):
    db = Database(failed=True, audit_unavailable=True)
    result = cycle(monkeypatch, db)
    assert result['status'] == 'general_manager_cycle_failed'
    assert result['heartbeat_at'] == (START + timedelta(seconds=26)).isoformat()
    assert not any('status,case_counts,completed_at' in sql for sql, _ in db.commands)
    assert_start_unchanged(db, result)


@pytest.mark.parametrize('rows', [False, True])
def test_frozen_injected_clock_remains_deterministic(monkeypatch, rows):
    db = Database(rows=rows, frozen=True)
    result = cycle(monkeypatch, db)
    end = terminal(db)
    assert result['success'] is True
    assert end[0] == end[4] == START
    assert result['heartbeat_at'] == START.isoformat()
    assert_start_unchanged(db, result)