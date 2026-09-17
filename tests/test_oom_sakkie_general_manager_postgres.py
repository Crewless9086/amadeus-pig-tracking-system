import json
import os
from concurrent.futures import ALL_COMPLETED, FIRST_COMPLETED, Future, ThreadPoolExecutor, wait as real_wait
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
import pytest
import unittest
import uuid
import time
import threading
from types import SimpleNamespace
from unittest.mock import patch

from modules.oom_sakkie import general_manager_worker as worker_module

from modules.oom_sakkie.manager_case_sources import _completed_bulk_batch_findings
from modules.oom_sakkie.general_manager_worker import (
    CLAIM_LIMIT, ManagerCaseError, PostgresManagerCaseStore, deliver_farm_manager_case,
    normalize_candidate,
)


URL = os.getenv("OOM_PROTECTED_ACTION_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not URL, reason="disposable PostgreSQL URL is required")


def connect():
    return psycopg.connect(URL)


class _IsolatedCursor:
    def __init__(self, cursor, owner):
        self.cursor, self.owner = cursor, owner

    def __enter__(self):
        self.cursor.__enter__()
        return self

    def __exit__(self, *args):
        return self.cursor.__exit__(*args)

    def execute(self, sql, params=None):
        # Relocate only the schema; execute the real worker SQL and migrations.
        self.owner.statements += 1
        self.cursor.execute(sql.replace('app_private.', self.owner.schema + '.'), params)
        return self

    def __getattr__(self, name):
        return getattr(self.cursor, name)


class _IsolatedConnection:
    def __init__(self, connection, owner):
        self.connection, self.owner = connection, owner

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def cursor(self):
        return _IsolatedCursor(self.connection.cursor(), self.owner)

    def execute(self, sql, params=None):
        return self.cursor().execute(sql, params)

    def close(self):
        self.connection.close()


@unittest.skipUnless(URL, 'disposable PostgreSQL URL is required')
class SchedulerRecoveryPostgresTests(unittest.TestCase):
    """Discovered by both pytest and the existing hosted unittest command.

    Every test owns a fresh schema, preserving other tests' rows and avoiding
    dependence on their clocks, leases or queue positions. No provider is used.
    """
    def setUp(self):
        self.schema = 'omq_recovery_' + uuid.uuid4().hex
        self.statements = 0
        self.now = datetime.now(timezone.utc)
        with connect() as db:
            db.execute('create schema ' + self.schema)
        self.addCleanup(self.drop_schema)
        with self.db() as db:
            db.execute('create table app_private.migration_log(migration_id text primary key,description text not null)')
            db.execute('''create table app_private.oom_protected_action_claims(
                callback_token text primary key,action_kind text not null,
                provider_message_id text,status text,result_payload jsonb,completed_at timestamptz)''')
            migrations = Path(__file__).parents[1] / 'supabase' / 'migrations'
            for name in ('202608170002_create_oom_manager_case_runtime.sql',
                         '202608190002_create_beacon_protected_publication_consumer.sql'):
                db.execute((migrations / name).read_text(encoding='utf-8'))
        self.store = worker_module.PostgresManagerCaseStore(connect_factory=self.db)

    def drop_schema(self):
        assert self.schema.startswith('omq_recovery_') and len(self.schema) == 45
        with connect() as db:
            db.execute('drop schema ' + self.schema + ' cascade')

    def db(self):
        return _IsolatedConnection(psycopg.connect(URL, options='-c statement_timeout=10000'), self)

    def value(self, key, **changes):
        value = candidate('event:' + key, self.now + timedelta(hours=1),
            dedupe_key='local:' + key, specialist='HERDMASTER', unknowns=[],
            evidence_refs=['event:' + key, 'observed:' + self.now.isoformat()])
        value.update(changes)
        return value

    def seed(self, values):
        with self.db() as db, db.cursor() as cur:
            for value in sorted(values, key=lambda row: worker_module.normalize_candidate(row, now=self.now)['case_id']):
                self.store._reconcile(cur, worker_module.normalize_candidate(value, now=self.now), self.now)

    def cycle(self, values, **kwargs):
        return self.store.run_cycle(values, now=self.now, source_revision='local-regression',
            brain_guard_audit={'passed': True}, **kwargs)

    def test_canonical_writer_case_identity_survives_refresh_delivery_and_replay(self):
        key = 'herdmaster-litter-follow-up:LIT-OFFLINE'
        canonical_id = 'OOM-MANAGER-HERD-LITTER-OFFLINE'
        raw = self.value('retained-litter', dedupe_key=key)
        old = worker_module.normalize_candidate(raw, now=self.now)
        with self.db() as db, db.cursor() as cur:
            self.store._reconcile(cur, {**old, 'case_id': canonical_id}, self.now)
        changed = {**raw, 'summary': 'Current canonical litter needs care',
            'evidence_refs': ['litter:LIT-OFFLINE', 'active_pigs:8'],
            'next_reassessment_at': self.now.isoformat(),
            'case_id': 'UNTRUSTED-CALLER-ID'}
        sends = []
        result = self.cycle([changed], refresh=lambda _case: changed,
            deliver=lambda row, **_kwargs: sends.append(row['case_id']) or {
                'success': True, 'delivery_confirmed': True,
                'next_reassessment_at': (self.now + timedelta(minutes=30)).isoformat()})
        self.assertTrue(result['success'], result)
        self.assertEqual(sends, [canonical_id])
        with self.db() as db:
            row = db.execute("select case_id,status,generation,next_reassessment_at from app_private.oom_manager_cases where dedupe_key=%s", (key,)).fetchone()
            self.assertEqual(row[:3], (canonical_id, 'waiting_reassessment', 2))
            self.assertGreater(row[3], self.now)
            identities = db.execute("select distinct case_id from app_private.oom_manager_case_events").fetchall()
            self.assertEqual(identities, [(canonical_id,)])
            self.assertEqual(db.execute("select count(*) from app_private.oom_manager_cases").fetchone()[0], 1)
        again = self.cycle([changed], deliver=lambda *_args, **_kwargs: self.fail('duplicate delivery'))
        self.assertTrue(again['success'], again)
        self.assertEqual(again['candidate_replays'], 1)

    def test_mixed_reconciliation_keeps_custom_identity_and_terminal_event(self):
        raw = self.value('retained-litter', dedupe_key='herdmaster-litter-follow-up:LIT-MIXED')
        custom = 'OOM-MANAGER-HERD-LITTER-MIXED'
        with self.db() as db, db.cursor() as cur:
            self.store._reconcile(cur, {**worker_module.normalize_candidate(raw, now=self.now),
                'case_id': custom}, self.now)
        changed = {**raw, 'summary': 'Changed current evidence'}
        values = [self.value('new-before'), changed, self.value('new-after')]
        result = self.cycle(values)
        self.assertTrue(result['success'], result)
        terminal = worker_module.normalize_candidate({**changed, 'terminal_state': 'completed',
            'summary': 'Canonical outcome independently verified'}, now=self.now)
        with self.db() as db, db.cursor() as cur:
            self.assertEqual(self.store._reconcile(cur, terminal, self.now), 'changed')
            cur.execute("select case_id from app_private.oom_manager_case_events where event_type='completed'")
            self.assertEqual(cur.fetchall(), [(custom,)])

    def test_313_replays_keep_epochs_and_make_progress_with_latency_budget(self):
        values = [self.value(str(i), next_reassessment_at=self.now.isoformat()) for i in range(313)]
        self.seed(values)
        newer = self.now + timedelta(seconds=1)
        values = [{**value, 'evidence_refs': [value['evidence_refs'][0], 'observed:' + newer.isoformat()]}
                  for value in values]
        by_key = {value['dedupe_key']: value for value in values}
        sends = []
        self.statements = 0
        started = time.perf_counter()
        # A 100ms cost per real SQL statement models round-trip sensitivity;
        # it is deliberately separate from measured local database wall time.
        clock = SimpleNamespace(monotonic=lambda: self.statements * 0.1)
        with patch.object(worker_module, 'time', clock):
            result = self.cycle(values, deadline_monotonic=80,
                refresh_batch=lambda cases: {row['case_id']: by_key[row['dedupe_key']] for row in cases},
                deliver=lambda row, **_kwargs: sends.append(row['case_id']) or {
                    'success': True, 'status': 'delivery_confirmed', 'delivery_confirmed': True,
                    'next_reassessment_at': (self.now + timedelta(minutes=5)).isoformat()})
        measured_statements = self.statements
        self.benchmark = {'statements': measured_statements,
            'real_database_wall_seconds': time.perf_counter() - started,
            'simulated_sql_latency_seconds': measured_statements * 0.1,
            'result': result}
        self.assertTrue(result['success'], result)
        self.assertEqual(result['candidate_replays'], 313)
        self.assertEqual(result['deliveries_confirmed'], 5)
        self.assertEqual(result['deadline_deferrals'], 0)
        self.assertLess(measured_statements, 100)
        with self.db() as db:
            rows = db.execute('select generation,evidence_refs from app_private.oom_manager_cases').fetchall()
        self.assertEqual(len(rows), 313)
        self.assertTrue(all(generation == 1 and 'observed:' + newer.isoformat() in refs for generation, refs in rows))
        repeat = self.cycle(values, deliver=lambda *_a, **_k: self.fail('duplicate provider call'),
            refresh_batch=lambda cases: {})
        self.assertEqual(repeat['deliveries_confirmed'], 0)
        self.assertEqual(len(sends), 5)

    def test_duplicate_keys_observe_prior_updates_and_stale_epochs_do_not_replace(self):
        initial = self.value('repeat')
        self.seed([initial])
        newer = self.now + timedelta(minutes=1)
        newest = self.now + timedelta(minutes=2)
        first = {**initial, 'evidence_refs': ['event:repeat', 'observed:' + newer.isoformat()]}
        changed = {**initial, 'summary': 'New canonical evidence',
                   'evidence_refs': ['event:new', 'observed:' + newest.isoformat()]}
        result = self.cycle([first, changed, initial, changed])
        self.assertTrue(result['success'], result)
        self.assertEqual(result['candidates_changed'], 1)
        with self.db() as db:
            row = db.execute('select generation,summary,evidence_refs from app_private.oom_manager_cases').fetchone()
            counts = dict(db.execute('select event_type,count(*) from app_private.oom_manager_case_events group by event_type').fetchall())
        self.assertEqual(row, (2, changed['summary'], sorted(changed['evidence_refs'])))
        self.assertEqual(counts, {'created': 1, 'evidence_changed': 1})

    def test_314_candidates_with_32_absent_terminal_findings_keep_progress(self):
        values = sorted([self.value('mixed-' + str(i),
            next_reassessment_at=self.now.isoformat()) for i in range(314)],
            key=lambda row: normalize_candidate(row, now=self.now)['case_id'])
        missing_positions = {(i + 1) * len(values) // 33 for i in range(32)}
        self.seed([row for i, row in enumerate(values) if i not in missing_positions])
        newer = self.now + timedelta(seconds=1)
        values = [{**row, 'evidence_refs': [row['evidence_refs'][0], 'observed:' + newer.isoformat()],
            **({'terminal_state': 'completed'} if i in missing_positions else {})}
            for i, row in enumerate(values)]
        values[0] = {**values[0], 'summary': 'One changed canonical finding'}
        by_key = {row['dedupe_key']: row for row in values}
        self.statements = 0
        lookups, initial_lookup_counts, initial_statement_counts, sends = [], [], [], []
        original = _IsolatedCursor.execute
        def counted(cursor, sql, params=None):
            if 'with eligible as materialized' in sql:
                initial_lookup_counts.append(len(lookups))
                initial_statement_counts.append(self.statements)
            if ('select dedupe_key,evidence_digest,generation,status' in sql
                    or 'select evidence_digest,generation,status' in sql):
                lookups.append(sql)
            return original(cursor, sql, params)
        # These are explicit synthetic timings around real PostgreSQL SQL:
        # 14 seconds before reconciliation and 120ms per protocol command.
        clock = SimpleNamespace(monotonic=lambda: 14 + self.statements * 0.12)
        started = time.perf_counter()
        with patch.object(_IsolatedCursor, 'execute', counted), patch.object(worker_module, 'time', clock):
            result = self.cycle(values, deadline_monotonic=80,
                refresh_batch=lambda cases: {row['case_id']: by_key[row['dedupe_key']] for row in cases},
                deliver=lambda row, **_kwargs: sends.append(row['case_id']) or {
                    'success': True, 'status': 'delivery_confirmed', 'delivery_confirmed': True,
                    'next_reassessment_at': (self.now + timedelta(minutes=5)).isoformat()})
        self.benchmark = {'candidates': 314, 'present': 282, 'absent_terminal': 32,
            'statements': self.statements, 'reconciliation_lookup_statements': initial_lookup_counts[0],
            'statements_through_initial_reconciliation': initial_statement_counts[0],
            'total_lookup_statements_including_claim_refresh': len(lookups),
            'real_database_wall_seconds': time.perf_counter() - started,
            'simulated_elapsed_seconds': clock.monotonic(), 'result': result}
        self.assertTrue(result['success'], result)
        self.assertEqual(result['candidate_replays'], 313)
        self.assertEqual(result['candidates_changed'], 1)
        self.assertEqual(result['candidates_created'], 0)
        self.assertEqual(result['deliveries_confirmed'], 5)
        self.assertEqual(result['deadline_deferrals'], 0)
        self.assertLessEqual(initial_lookup_counts[0], 66)
        # Audit insert + failed whole prefetch + 33 complete run prefetches +
        # 32 fresh gap reads + changed-case write/event + batched epoch update.
        self.assertLessEqual(initial_statement_counts[0], 1 + 4 + 33 * 3 + 32 + 2 + 1)
        with self.db() as db:
            rows = db.execute('select generation,evidence_refs from app_private.oom_manager_cases').fetchall()
        self.assertEqual(len(rows), 282)
        self.assertEqual(sum(generation == 2 for generation, _refs in rows), 1)
        self.assertTrue(all('observed:' + newer.isoformat() in refs for _generation, refs in rows))

    def _full_wrapper_with_slow_owner(self, slow_owner):
        from modules.oom_sakkie import manager_case_sources as sources
        from modules.telemetry import rootline_mixer_readiness_observer as readiness
        values = [self.value('wrapper-' + str(i), dedupe_key='herdmaster:wrapper-' + str(i))
                  for i in range(309)]
        values.sort(key=lambda row: normalize_candidate(row, now=self.now)['case_id'])
        absent = {(i + 1) * len(values) // 33 for i in range(32)}
        due = [self.value(owner, dedupe_key=owner + ':wrapper-due', specialist=specialist,
                         urgency=urgency, next_reassessment_at=self.now.isoformat())
               for owner, specialist, urgency in (
                   ('herdmaster', 'HERDMASTER', 'critical'),
                   ('rootline-readiness' if slow_owner == 'rootline-readiness' else 'rootline',
                    'ROOTLINE', 'urgent'),
                   ('beacon', 'BEACON', 'due'), ('sam', 'SAM', 'planned'),
                   ('runtime', 'RUNTIME', 'watch'))]
        self.seed([row for i, row in enumerate(values) if i not in absent] + due)
        values = [{**row, **({'terminal_state': 'completed'} if i in absent else {})}
                  for i, row in enumerate(values)] + due
        values[0] = {**values[0], 'summary': 'One changed canonical finding'}
        gate, slow_started, slow_finished = threading.Event(), threading.Event(), threading.Event()
        counts, sends, waits, refresh_futures = {}, [], [], []
        elapsed = [0.0]
        self.statements = 0
        clock = SimpleNamespace(monotonic=lambda: elapsed[0] + self.statements * 0.12)
        def capture_executor(**kwargs):
            executor = ThreadPoolExecutor(**kwargs)
            original_submit = executor.submit
            def submit(*args, **submit_kwargs):
                future = original_submit(*args, **submit_kwargs)
                refresh_futures.append(future)
                return future
            executor.submit = submit
            return executor

        def block_once(owner):
            slow_started.set()
            try:
                if not gate.wait(10):
                    raise AssertionError('test failed to release slow collector')
            finally:
                slow_finished.set()

        def collector(owner):
            def read(_now):
                counts[owner] = counts.get(owner, 0) + 1
                if owner == slow_owner and counts[owner] == 2:
                    block_once(owner)
                return [row for row in values if row['dedupe_key'].split(':')[0] == owner
                        or (owner == 'rootline' and row['dedupe_key'].startswith('rootline-readiness:'))]
            read.__name__ = '_' + owner
            return read
        collectors = tuple(collector(owner) for owner in ('herdmaster', 'rootline', 'beacon', 'sam', 'runtime'))
        original_collect = sources.collect_manager_candidates
        initial_calls = [0]
        def collect_with_source_cost(**kwargs):
            rows = original_collect(**kwargs)
            if threading.current_thread() is threading.main_thread():
                initial_calls[0] += 1
                elapsed[0] += 14.0
            return rows
        readiness_calls = [0]
        def read_mixer(**_kwargs):
            readiness_calls[0] += 1
            if readiness_calls[0] == 1:
                block_once('rootline-readiness')
            return [row for row in values if row['dedupe_key'].startswith('rootline-readiness:')]
        def bounded_wait(futures, timeout=None, return_when=ALL_COMPLETED):
            # Real threads and real FIRST/ALL completion semantics. Advance a
            # virtual timeout only after the blocked collector is observed.
            done, pending = real_wait(futures, timeout=0.2, return_when=return_when)
            if pending and (return_when == ALL_COMPLETED or not done):
                self.assertTrue(slow_started.wait(1))
                elapsed[0] += float(timeout or 0)
            waits.append({'mode': return_when, 'done': len(done), 'pending': len(pending)})
            return done, pending
        def deliver(case, **_kwargs):
            sends.append((case['case_id'], case['generation'], clock.monotonic()))
            return {'success': True, 'status': 'delivery_confirmed', 'delivery_confirmed': True,
                    'next_reassessment_at': (self.now + timedelta(minutes=5)).isoformat()}
        started = time.perf_counter()
        try:
            with patch.object(worker_module, 'time', clock), patch.object(worker_module, 'wait', bounded_wait), \
                    patch.object(worker_module, 'ThreadPoolExecutor', capture_executor), \
                    patch.object(sources, 'collect_manager_candidates', collect_with_source_cost), \
                    patch.object(readiness, 'collect_mixer_readiness', read_mixer):
                result = worker_module.run_general_manager_cycle(now=self.now, source_revision='local-full-wrapper',
                    store=self.store, collectors=collectors, deliver=deliver)
                measured = {'statements': self.statements, 'simulated_elapsed_seconds': clock.monotonic(),
                    'real_database_and_thread_wall_seconds': time.perf_counter() - started,
                    'result': result, 'collector_calls': dict(counts), 'waits': list(waits), 'sends': list(sends)}
                self.benchmark = measured
                self.assertEqual(initial_calls[0], 1)
                self.assertEqual(result['cases_claimed'], 5, result)
                self.assertEqual(result['candidate_replays'], 313, result)
                self.assertEqual(result['candidates_changed'], 1, result)
                self.assertEqual(result['deliveries_confirmed'], 4, result)
                self.assertEqual(result['deadline_deferrals'], 1, result)
                self.assertTrue(all(when < 50 for _key, _generation, when in sends))
                self.assertEqual(len({(key, generation) for key, generation, _when in sends}), 4)
                self.assertEqual(counts['herdmaster'], 2)
                gate.set()
                self.assertTrue(slow_finished.wait(2))
                completed, pending = real_wait(tuple(refresh_futures), timeout=2)
                self.assertFalse(pending, 'abandoned collector future has not actually returned')
                measured['first_cohort_futures_completed_before_retry'] = len(completed)
                before_retry = list(sends)
                with self.db() as db:
                    rows = db.execute('''select dedupe_key,assigned_worker_id,lease_until,last_delivery_digest,
                        evidence_digest from app_private.oom_manager_cases where next_reassessment_at=%s''',
                        (self.now + timedelta(minutes=5),)).fetchall()
                self.assertEqual(len(rows), 5)
                self.assertTrue(all(row[1:3] == (None, None) for row in rows))
                self.assertEqual(sum(row[3] == row[4] for row in rows), 4)
                # The late read has no effect; the next genuine-style cohort
                # must reclaim its own generation and suppress the four replays.
                self.statements = 0
                elapsed[0] = 0.0
                retry = worker_module.run_general_manager_cycle(now=self.now + timedelta(minutes=5),
                    source_revision='local-full-wrapper', store=self.store, collectors=collectors, deliver=deliver)
                self.assertTrue(retry['success'], retry)
                self.assertEqual(retry['deliveries_confirmed'], 1, retry)
                self.assertEqual(retry['deliveries_suppressed'], 4, retry)
                self.assertEqual(retry['deadline_deferrals'], 0, retry)
                self.assertEqual(sends[:4], before_retry)
                self.assertEqual(len({(key, generation) for key, generation, _when in sends}), 5)
                measured['retry'] = retry
                self.benchmark = measured
        finally:
            gate.set()
            if slow_started.is_set():
                self.assertTrue(slow_finished.wait(2))
            if refresh_futures:
                _completed, pending = real_wait(tuple(refresh_futures), timeout=2)
                self.assertFalse(pending, 'test leaked a running collector')

    def test_full_wrapper_slow_herd_does_not_block_ready_specialists(self):
        self._full_wrapper_with_slow_owner('herdmaster')

    def test_full_wrapper_slow_readiness_does_not_block_ready_specialists(self):
        self._full_wrapper_with_slow_owner('rootline-readiness')

    def test_ready_claim_order_rechecks_pending_head_before_next_dispatch(self):
        values = [self.value(owner, dedupe_key=owner + ':ordered', specialist=owner.upper(),
            urgency=urgency, next_reassessment_at=self.now.isoformat())
            for owner, urgency in (('herdmaster', 'critical'), ('rootline', 'urgent'),
                                   ('beacon', 'due'), ('sam', 'planned'), ('runtime', 'watch'))]
        by_key = {row['dedupe_key']: row for row in values}
        futures, original_order, delivered, closed = {}, [], [], []
        def start(cases):
            batch = worker_module._ManagerRefreshBatch.__new__(worker_module._ManagerRefreshBatch)
            batch.results, batch.jobs, batch.deadline = {}, {}, 20.0
            batch.executor = SimpleNamespace(shutdown=lambda **kwargs: closed.append(kwargs))
            for case in cases:
                original_order.append(case['dedupe_key'])
                future = futures[case['dedupe_key']] = Future()
                batch.jobs[future] = (case,)
                if case['specialist'] != 'HERDMASTER':
                    future.set_result((1.0, {(case['dedupe_key'], case['specialist']): by_key[case['dedupe_key']]}))
            return batch
        def deliver(case, **_kwargs):
            delivered.append(case['dedupe_key'])
            if case['specialist'] == 'ROOTLINE':
                row = by_key['herdmaster:ordered']
                futures[row['dedupe_key']].set_result((2.0, {(row['dedupe_key'], row['specialist']): row}))
            return {'success': True, 'status': 'delivery_confirmed', 'delivery_confirmed': True}
        with patch.object(worker_module, 'time', SimpleNamespace(monotonic=lambda: 3.0)):
            result = self.cycle(values, deadline_monotonic=80, refresh_batch=start, deliver=deliver)
        self.assertTrue(result['success'], result)
        self.assertEqual(original_order, ['herdmaster:ordered', 'rootline:ordered', 'beacon:ordered'])
        self.assertEqual(delivered, ['rootline:ordered', 'herdmaster:ordered', 'beacon:ordered',
                                     'sam:ordered', 'runtime:ordered'])
        self.assertEqual(len(closed), 1)
        with self.db() as db:
            owned = db.execute('''select count(*) from app_private.oom_manager_cases
                where assigned_worker_id is not null or lease_until is not null''').fetchone()[0]
        self.assertEqual(owned, 0)

    def test_late_refresh_completion_during_delivery_cannot_start_another_delivery(self):
        values = [self.value(owner, dedupe_key=owner + ':late', specialist=owner.upper(),
            urgency=urgency, next_reassessment_at=self.now.isoformat())
            for owner, urgency in (('herdmaster', 'critical'), ('rootline', 'urgent'), ('beacon', 'due'))]
        by_key = {row['dedupe_key']: row for row in values}
        clock, futures, sends, closed = [1.0], {}, [], []
        def start(cases):
            batch = worker_module._ManagerRefreshBatch.__new__(worker_module._ManagerRefreshBatch)
            batch.results, batch.jobs, batch.deadline = {}, {}, 20.0
            batch.executor = SimpleNamespace(shutdown=lambda **kwargs: closed.append(kwargs))
            for case in cases:
                future = futures[case['dedupe_key']] = Future()
                batch.jobs[future] = (case,)
                if case['specialist'] == 'ROOTLINE':
                    future.set_result((1.0, {(case['dedupe_key'], case['specialist']): by_key[case['dedupe_key']]}))
            return batch
        def deliver(case, **_kwargs):
            sends.append(case['dedupe_key'])
            # Caller-owned delivery occupies the loop while both reads finish.
            clock[0] = 25.0
            for owner, finished_at in (('herdmaster', 21.0), ('beacon', 19.0)):
                if not futures[owner + ':late'].done():
                    row = by_key[owner + ':late']
                    futures[row['dedupe_key']].set_result((finished_at, {(row['dedupe_key'], row['specialist']): row}))
            return {'success': True, 'status': 'delivery_confirmed', 'delivery_confirmed': True}
        with patch.object(worker_module, 'time', SimpleNamespace(monotonic=lambda: clock[0])):
            result = self.cycle(values, deadline_monotonic=80, refresh_batch=start, deliver=deliver)
        self.assertTrue(result['success'], result)
        self.assertEqual(sends, ['rootline:late', 'beacon:late'])
        self.assertEqual(result['exceptions'], 1)
        self.assertEqual(result['deadline_deferrals'], 0)
        self.assertEqual(len(closed), 1)
        with self.db() as db:
            row = db.execute('''select status,last_delivery_digest,assigned_worker_id,lease_until,next_reassessment_at
                from app_private.oom_manager_cases where dedupe_key='herdmaster:late' ''').fetchone()
            event = db.execute('''select event_payload from app_private.oom_manager_case_events
                where case_id=%s and event_type='exception' ''',
                (normalize_candidate(by_key['herdmaster:late'], now=self.now)['case_id'],)).fetchone()[0]
        self.assertEqual(row, ('waiting_reassessment', None, None, None, self.now + timedelta(minutes=5)))
        self.assertEqual(event['failure_kind'], 'TimeoutError')
        self.assertEqual(event['outcome_status'], 'manager_specialist_processing_exception_contained')

    def test_absent_terminal_is_reread_after_concurrent_insert(self):
        values = sorted([self.value('terminal-insert-' + str(i)) for i in range(3)],
            key=lambda row: normalize_candidate(row, now=self.now)['case_id'])
        lower, *higher = values
        self.seed(higher)
        terminal = {**lower, 'terminal_state': 'completed'}
        original, inserted = _IsolatedCursor.execute, []
        def after_release(cursor, sql, params=None):
            result = original(cursor, sql, params)
            if sql == 'release savepoint oom_manager_reconciliation_prefetch' and not inserted:
                inserted.append(True)
                # The incomplete initial prefetch has released its locks.
                # Commit a competing writer before the missing key's turn.
                with self.db() as db, db.cursor() as other:
                    self.store._reconcile(other, normalize_candidate(lower, now=self.now), self.now)
            return result
        with patch.object(_IsolatedCursor, 'execute', after_release):
            result = self.cycle([terminal, *higher])
        self.assertTrue(result['success'], result)
        self.assertEqual(result['candidates_changed'], 1)
        with self.db() as db:
            row = db.execute('select status,generation from app_private.oom_manager_cases where dedupe_key=%s',
                (lower['dedupe_key'],)).fetchone()
            completed = db.execute("select count(*) from app_private.oom_manager_case_events where event_type='completed'").fetchone()[0]
        self.assertEqual(row, ('completed', 2))
        self.assertEqual(completed, 1)

    def test_planned_run_relocks_changed_prior_and_preserves_duplicate_epochs(self):
        values = sorted([self.value('relock-' + str(i)) for i in range(4)],
            key=lambda row: normalize_candidate(row, now=self.now)['case_id'])
        lower, *higher = values
        self.seed(higher)
        latest = {**higher[0], 'summary': 'Concurrent latest material',
            'evidence_refs': ['event:concurrent', 'observed:' + (self.now + timedelta(minutes=2)).isoformat()]}
        replay = {**higher[-1], 'evidence_refs': [higher[-1]['evidence_refs'][0],
            'observed:' + (self.now + timedelta(minutes=1)).isoformat()]}
        original, changed = _IsolatedCursor.execute, []
        def after_release(cursor, sql, params=None):
            result = original(cursor, sql, params)
            if sql == 'release savepoint oom_manager_reconciliation_prefetch' and not changed:
                changed.append(True)
                with self.db() as db, db.cursor() as other:
                    self.store._reconcile(other, normalize_candidate(latest, now=self.now), self.now)
            return result
        with patch.object(_IsolatedCursor, 'execute', after_release):
            result = self.cycle([{**lower, 'terminal_state': 'completed'}, *higher, replay, higher[-1]])
        self.assertTrue(result['success'], result)
        with self.db() as db:
            rows = {row[0]: row[1:] for row in db.execute('select dedupe_key,generation,summary,evidence_refs from app_private.oom_manager_cases').fetchall()}
        self.assertEqual(rows[latest['dedupe_key']], (2, latest['summary'], sorted(latest['evidence_refs'])))
        self.assertEqual(rows[replay['dedupe_key']][2], sorted(replay['evidence_refs']))

    def test_deleted_run_key_releases_only_run_prelocks_before_point_fallback(self):
        threading = __import__('threading')
        values = sorted([self.value('delete-reinsert-' + str(i)) for i in range(5)],
            key=lambda row: normalize_candidate(row, now=self.now)['case_id'])
        prefix, gap, lower, middle, higher = values
        self.seed([prefix, middle, higher])
        # Model a valid case row with no referring event, so deletion can commit
        # without altering the append-only event trigger or its foreign key.
        with patch.object(self.store, '_event'):
            self.seed([lower])
        external = self.db()
        self.addCleanup(external.close)
        external_pid = external.connection.info.backend_pid
        run_locked, release_run = threading.Event(), threading.Event()
        original, prepared, prefix_lock_checks = _IsolatedCursor.execute, [], []
        def gate(cursor, sql, params=None):
            result = original(cursor, sql, params)
            if sql == 'rollback to savepoint oom_manager_reconciliation_prefetch' and run_locked.is_set():
                # The failed run has released middle/higher locks, but the
                # already reconciled lower prefix must remain locked.
                with self.assertRaises(psycopg.errors.LockNotAvailable):
                    with self.db() as observer:
                        observer.execute('select case_id from app_private.oom_manager_cases where dedupe_key=%s for update nowait',
                            (prefix['dedupe_key'],))
                prefix_lock_checks.append('55P03')
            if sql == 'release savepoint oom_manager_reconciliation_prefetch' and not prepared:
                prepared.append(True)
                with self.db() as db:
                    db.execute('delete from app_private.oom_manager_cases where dedupe_key=%s', (lower['dedupe_key'],))
                # The next run's snapshot cannot see this uncommitted insert.
                with external.cursor() as other:
                    self.store._reconcile(other, normalize_candidate(lower, now=self.now), self.now)
            elif ('select dedupe_key,evidence_digest,generation,status' in sql
                    and prepared and set(params[0]) == {row['dedupe_key'] for row in (lower, middle, higher)}):
                run_locked.set()
                if not release_run.wait(timeout=5):
                    raise AssertionError('run prefetch test gate timed out')
            return result
        def finish_external():
            with external:
                external.execute('select case_id from app_private.oom_manager_cases where dedupe_key=%s for update',
                    (middle['dedupe_key'],))
        with patch.object(_IsolatedCursor, 'execute', gate), ThreadPoolExecutor(max_workers=2) as pool:
            running = pool.submit(self.cycle, [prefix, {**gap, 'terminal_state': 'completed'}, lower, middle, higher])
            if not run_locked.wait(timeout=5):
                self.fail('run prefetch not reached: ' + str(running.result(timeout=5)))
            competing = pool.submit(finish_external)
            try:
                limit, blocked = time.monotonic() + 3, False
                with connect() as observer:
                    while time.monotonic() < limit:
                        blocked = bool(observer.execute('select cardinality(pg_blocking_pids(%s)) > 0',
                            (external_pid,)).fetchone()[0])
                        if blocked:
                            break
                        time.sleep(0.01)
                self.assertTrue(blocked, 'competing transaction never reached the run prelock')
            finally:
                release_run.set()
            competing.result(timeout=5)
            result = running.result(timeout=5)
        self.assertTrue(result['success'], result)
        self.assertEqual(prefix_lock_checks, ['55P03'])
        with self.db() as db:
            rows = db.execute('select count(*),max(generation) from app_private.oom_manager_cases').fetchone()
        self.assertEqual(rows, (4, 1))

    def test_overlapping_reversed_batches_with_new_keys_serialize(self):
        values = [self.value(str(i)) for i in range(30)]
        self.seed(values[:15])
        barrier = __import__('threading').Barrier(2)
        def run(reverse):
            barrier.wait(timeout=10)
            return self.cycle(list(reversed(values)) if reverse else values)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(run, (False, True)))
        self.assertTrue(all(row['success'] for row in results), results)
        with self.db() as db:
            count = db.execute('select count(*),max(generation) from app_private.oom_manager_cases').fetchone()
            events = db.execute('select count(*) from app_private.oom_manager_case_events').fetchone()[0]
        self.assertEqual(count, (30, 1))
        self.assertEqual(events, 30)

    def test_missing_lower_key_releases_higher_prefetch_lock_before_fallback(self):
        threading = __import__('threading')
        values = sorted([self.value('new-low-or-high'), self.value('existing-low-or-high')],
            key=lambda row: worker_module.normalize_candidate(row, now=self.now)['case_id'])
        lower, higher = values
        self.seed([higher])
        external = self.db()
        self.addCleanup(external.close)
        with external.cursor() as cur:
            self.store._reconcile(cur, worker_module.normalize_candidate(lower, now=self.now), self.now)
        external_pid = external.connection.info.backend_pid
        prefetched, release_prefetch = threading.Event(), threading.Event()
        original = _IsolatedCursor.execute
        def gate(cursor, sql, params=None):
            result = original(cursor, sql, params)
            if 'select dedupe_key,evidence_digest,generation,status' in sql:
                prefetched.set()
                if not release_prefetch.wait(timeout=5):
                    raise AssertionError('prefetch test gate timed out')
            return result
        def finish_external():
            with external:
                external.execute('select case_id from app_private.oom_manager_cases where dedupe_key=%s for update',
                                 (higher['dedupe_key'],))
        with patch.object(_IsolatedCursor, 'execute', gate), ThreadPoolExecutor(max_workers=2) as pool:
            worker = pool.submit(self.cycle, values)
            self.assertTrue(prefetched.wait(timeout=5))
            competing = pool.submit(finish_external)
            try:
                # Force the old inversion: the external transaction owns the
                # lower key and is demonstrably waiting on our higher prelock.
                limit = time.monotonic() + 3
                blocked = False
                with connect() as observer:
                    while time.monotonic() < limit:
                        blocked = bool(observer.execute('select cardinality(pg_blocking_pids(%s)) > 0',
                                                        (external_pid,)).fetchone()[0])
                        if blocked:
                            break
                        time.sleep(0.01)
                self.assertTrue(blocked, 'competing transaction never reached the higher lock')
            finally:
                release_prefetch.set()
            competing.result(timeout=5)
            result = worker.result(timeout=5)
        self.assertTrue(result['success'], result)
        with self.db() as db:
            count = db.execute('select count(*),max(generation) from app_private.oom_manager_cases').fetchone()
        self.assertEqual(count, (2, 1))

    def test_active_and_expired_delegated_generations_remain_immutable(self):
        values = [self.value('active'), self.value('expired')]
        self.seed(values)
        with self.db() as db:
            for index, value in enumerate(values):
                db.execute('''update app_private.oom_manager_cases set status='delegated',
                    assigned_worker_id='another-worker',lease_until=%s where dedupe_key=%s''',
                    (self.now + timedelta(minutes=5 if index == 0 else -5), value['dedupe_key']))
        self.cycle([{**row, 'summary': 'Competing changed evidence'} for row in values])
        with self.db() as db:
            rows = db.execute('select generation,summary,assigned_worker_id from app_private.oom_manager_cases').fetchall()
        self.assertTrue(all(row == (1, values[0]['summary'], 'another-worker') for row in rows))

    def test_expired_budget_starts_no_refresh_and_releases_only_its_claims(self):
        values = [self.value(str(i), next_reassessment_at=self.now.isoformat()) for i in range(6)]
        self.seed(values)
        with self.db() as db:
            db.execute('''update app_private.oom_manager_cases set assigned_worker_id='other',
                status='delegated',lease_until=%s where dedupe_key=%s''',
                (self.now + timedelta(minutes=5), values[0]['dedupe_key']))
        with patch.object(worker_module, 'time', SimpleNamespace(monotonic=lambda: 51)):
            result = self.cycle(values, deadline_monotonic=80,
                refresh_batch=lambda _: self.fail('refresh after reserve'),
                deliver=lambda *_a, **_k: self.fail('send after reserve'))
        self.assertEqual(result['deadline_deferrals'], 5)
        self.assertFalse(result['success'])
        with self.db() as db:
            owners = db.execute('select assigned_worker_id,count(*) from app_private.oom_manager_cases group by assigned_worker_id').fetchall()
        self.assertEqual(dict(owners), {None: 5, 'other': 1})

    def test_refresh_filters_confirmed_and_non_specialist_cases(self):
        values = [self.value('confirmed', next_reassessment_at=self.now.isoformat()),
                  self.value('nonfarm', specialist='SAM', next_reassessment_at=self.now.isoformat()),
                  self.value('needed', next_reassessment_at=self.now.isoformat())]
        self.seed(values)
        with self.db() as db:
            db.execute('update app_private.oom_manager_cases set last_delivery_digest=evidence_digest where dedupe_key=%s',
                       (values[0]['dedupe_key'],))
        refreshed = []
        def refresh(cases):
            refreshed.extend(row['dedupe_key'] for row in cases)
            return {row['case_id']: values[2] for row in cases}
        result = self.cycle(values, refresh_batch=refresh,
            deliver=lambda row: {'success': True, 'delivery_confirmed': False, 'status': 'local_suppressed'})
        self.assertTrue(result['success'], result)
        self.assertEqual(refreshed, [values[2]['dedupe_key']])

    def test_language_rejection_retains_confirmed_replacement_baseline(self):
        from modules.oom_sakkie import daily_farm_manager as daily
        identity = 'OOM-DAILY-FARM-MANAGER-2026-09-13'
        confirmed = {'daily_identity': identity, 'owner_user_id': 'local-af',
            'chat_id': 'local-af', 'material_digest': 'A', 'status': 'presented',
            'telegram_message_id': 'confirmed-A'}
        rejected = {**confirmed, 'material_digest': 'B',
            'status': 'recipient_language_render_unrecognized',
            'delivery_definitely_not_sent': True}
        rejected.pop('telegram_message_id')
        other_owner = {**confirmed, 'owner_user_id': 'other', 'chat_id': 'other',
                       'telegram_message_id': 'other-owner-card'}
        other_date = {**confirmed, 'daily_identity': 'OOM-DAILY-FARM-MANAGER-2026-09-14',
                      'telegram_message_id': 'other-date-card'}
        with self.db() as db:
            db.execute('''create table app_private.daily_receipts(
                review_event_id text primary key,event_source text,review_json jsonb,created_at timestamptz)''')
            for index, value in enumerate((confirmed, rejected, other_owner, other_date)):
                db.execute('insert into app_private.daily_receipts values(%s,%s,%s::jsonb,%s)',
                    (str(index), daily.EVENT_SOURCE, json.dumps({'daily_farm_manager': value}),
                     self.now + timedelta(seconds=index)))

        class ReceiptCursor(_IsolatedCursor):
            def execute(self, sql, params=None):
                return super().execute(sql.replace('public.sam_live_stock_conversation_review_events',
                                                   'app_private.daily_receipts'), params)

        class ReceiptConnection(_IsolatedConnection):
            def cursor(self):
                return ReceiptCursor(self.connection.cursor(), self.owner)

        # Execute the actual production selection SQL; relocate only its table.
        with patch.object(daily, 'connect_bounded_read',
                lambda: ReceiptConnection(psycopg.connect(URL), self)):
            prior = daily._load_daily(identity, {'owner_user_id': 'local-af', 'chat_id': 'local-af'})
            self.assertEqual(prior, confirmed)
            self.assertIsNone(daily._load_daily(identity,
                {'owner_user_id': 'local-af', 'chat_id': 'other'}))
        with self.db() as db:
            retained = db.execute('select review_json from app_private.daily_receipts where review_event_id=%s',
                                  ('1',)).fetchone()[0]
            self.assertEqual(retained, {'daily_farm_manager': rejected})
            self.assertEqual(db.execute('select count(*) from app_private.daily_receipts').fetchone()[0], 4)

    def test_canonical_short_morning_language_and_replay_boundary(self):
        from tests.test_oom_sakkie_daily_farm_manager import (
            test_canonical_morning_briefs_cross_family_delivery_once,
            test_morning_language_guard_reads_visible_html_and_still_rejects_english)
        for language in ('af', 'en'):
            for watchers in ('weaning', 'payment', 'both', 'empty'):
                with self.subTest(language=language, watchers=watchers):
                    test_canonical_morning_briefs_cross_family_delivery_once(language, watchers)
        for answer, accepted in (
            ('<b>AKSIE NODIG</b>\nBetaal die faktuur.', True),
            ('<b>Aksie&nbsp;nodig!</b>\nBetaal die faktuur.', True),
            ('<b>AKSIE NODIG</b>\nPlease confirm the payment.', False),
            ('<b>AKSIE NODIG</b>\n<b>Please</b> confirm&#32;the payment.', False)):
            with self.subTest(answer=answer):
                test_morning_language_guard_reads_visible_html_and_still_rejects_english(answer, accepted)

    def test_beacon_claimed_consumer_blocks_successor_then_retires_only_unconsumed_claim(self):
        initial = self.value('beacon', specialist='BEACON')
        self.seed([initial])
        case_id = worker_module.normalize_candidate(initial, now=self.now)['case_id']
        with self.db() as db:
            for token in ('consumed', 'unconsumed'):
                db.execute('''insert into app_private.oom_protected_action_claims
                    (callback_token,action_kind,provider_message_id,status)
                    values(%s,'beacon_campaign_review',%s,'active')''',
                    (token, 'scheduled:' + case_id + ':G1'))
            db.execute('''insert into app_private.beacon_protected_publication_consumers
                (consumer_id,callback_token,worker_id,status,claimed_at,updated_at)
                values('consumer','consumed','existing-worker','claimed',%s,%s)''', (self.now, self.now))
        changed = {**initial, 'summary': 'New current canonical publication proposal'}
        deferred = self.cycle([changed])
        self.assertTrue(deferred['success'], deferred)
        self.assertEqual(deferred['candidates_changed'], 0)
        with self.db() as db:
            self.assertEqual(db.execute('select generation from app_private.oom_manager_cases').fetchone()[0], 1)
            db.execute("update app_private.beacon_protected_publication_consumers set status='contained'")
        accepted = self.cycle([changed, changed])
        self.assertEqual(accepted['candidates_changed'], 1)
        with self.db() as db:
            claims = dict(db.execute('select callback_token,status from app_private.oom_protected_action_claims').fetchall())
            generation = db.execute('select generation from app_private.oom_manager_cases').fetchone()[0]
        self.assertEqual(generation, 2)
        self.assertEqual(claims, {'consumed': 'active', 'unconsumed': 'changed'})

    def test_terminal_replay_is_one_transition_and_database_error_stays_fatal(self):
        initial = self.value('terminal')
        self.seed([initial])
        terminal = {**initial, 'terminal_state': 'completed', 'summary': 'Canonical work completed'}
        result = self.cycle([terminal, terminal])
        self.assertEqual(result['candidates_changed'], 1)
        with self.db() as db:
            row = db.execute('select status,generation from app_private.oom_manager_cases').fetchone()
            count = db.execute("select count(*) from app_private.oom_manager_case_events where event_type='completed'").fetchone()[0]
        self.assertEqual(row, ('completed', 2))
        self.assertEqual(count, 1)
        with patch.object(self.store, '_reconcile', side_effect=worker_module.ManagerCaseError('local_invariant_failure')):
            failed = self.cycle([initial])
        self.assertFalse(failed['success'])
        self.assertEqual(failed['failure_kind'], 'ManagerCaseError')
        with self.db() as db:
            record = db.execute('select status,case_counts from app_private.oom_manager_worker_cycles where cycle_id=%s',
                                (failed['cycle_id'],)).fetchone()
        self.assertEqual(record[0], 'failed')
        self.assertEqual(record[1]['failure']['code'], 'local_invariant_failure')

    def test_native_daily_restart_does_not_repeat_an_ambiguous_provider_attempt(self):
        from modules.oom_sakkie import daily_farm_manager as daily
        from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
        from tests.test_oom_sakkie_daily_farm_manager import store, NOW
        state, family, sends = store(), {}, []
        def daily_store(action, identity, payload):
            if action == 'load_daily':
                rows = [row for row in state.rows.values()
                    if row.get('daily_identity') == identity
                    and row.get('status') in {'presented', 'unchanged', 'provider_ambiguous'}
                    and row.get('owner_user_id') == str(payload.get('owner_user_id'))
                    and row.get('chat_id') == str(payload.get('chat_id'))]
                return rows[-1] if rows else None
            return state(action, identity, payload)
        def family_store(action, identity, payload):
            if action == 'load':
                return [row for row in family.values() if row.get('card_mission_id') == identity]
            created = identity not in family
            if created:
                family[identity] = dict(payload)
            return {'success': True, 'created': created}
        def sender(*args):
            sends.append(args)
            return ({'success': False, 'status': 'provider_outcome_ambiguous'} if len(sends) == 1
                    else {'success': True, 'telegram_message_id': 'local-new-day'})
        def deliver(parsed, value, **kwargs):
            self.assertIsNone(kwargs.get('delivery_retry_authority'))
            return deliver_family_result(parsed, value, event_store=family_store, sender=sender, **kwargs)
        kwargs = dict(owner_user_id='77', chat_id='77', specialist_results=[],
            litter_rows=[{'Litter_ID': 'LOCAL-LITTER', 'Sow_Pig_ID': 'LOCAL-SOW',
                'Sow_Tag_Number': 'X100', 'Litter_Status': 'Active',
                'Wean_Date': '2026-08-09', 'Weaned_Count': None}],
            now=NOW, language='af', deliver=deliver, store=daily_store,
            semantic_prioritizer=lambda rows, **_: list(rows))
        # Match the production store identity so the duplicate daily claim
        # re-enters the actual family lifecycle, where attempt identity guards it.
        with patch.object(daily, 'daily_farm_manager_store', daily_store):
            first = daily.run_daily_farm_manager(**kwargs)
            repeat = daily.run_daily_farm_manager(**kwargs)
        self.assertFalse(first['success'])
        self.assertFalse(repeat['success'])
        self.assertEqual(len(sends), 1)
        self.assertEqual(sum(row['state'] == 'delivery_attempted' for row in family.values()), 1)
        self.assertFalse(any('RETRY' in identity for identity in family))
        old_family = dict(family)
        old_daily = dict(state.rows)
        with patch.object(daily, 'daily_farm_manager_store', daily_store):
            before_due = daily.run_daily_farm_manager(**{**kwargs, 'now': NOW + timedelta(days=1, hours=-1)})
            self.assertEqual(before_due['status'], 'daily_manager_not_due')
            self.assertEqual(len(sends), 1)
            next_day = daily.run_daily_farm_manager(**{**kwargs, 'now': NOW + timedelta(days=1)})
            repeat_next_day = daily.run_daily_farm_manager(**{**kwargs, 'now': NOW + timedelta(days=1)})
        self.assertEqual(next_day['status'], 'daily_manager_presented')
        self.assertEqual(repeat_next_day['status'], 'daily_manager_unchanged_silent')
        self.assertEqual(len(sends), 2)
        self.assertTrue(all(family[key] == value for key, value in old_family.items()))
        self.assertTrue(all(state.rows[key] == value for key, value in old_daily.items()))
        self.assertFalse(any('RETRY' in identity for identity in family))

    def test_delayed_owner_answer_rebuilds_current_day_without_reopening_old_day(self):
        from modules.oom_sakkie import morning_runtime as morning
        from modules.oom_sakkie import daily_farm_manager as daily
        from tests.test_oom_sakkie_daily_farm_manager import store
        from tests.test_oom_sakkie_morning_runtime import _two_manager_env, _specialist
        state, loaded_dates, sends = store(), [], []
        parsed = {'telegram_user_id': '77', 'telegram_chat_id': '77',
            'telegram_chat_type': 'private', 'provider_message_id': 'old-answer',
            'provider_timestamp': '2026-08-10T05:00:00+00:00', 'text': 'Recorded answer'}
        original_parsed = dict(parsed)
        historical = {'daily_identity': 'OOM-DAILY-FARM-MANAGER-2026-08-10',
            'status': 'provider_ambiguous', 'delivery_definitely_not_sent': False}
        state.rows['historical-ambiguous-outcome'] = dict(historical)
        def daily_store(action, identity, payload):
            if action == 'load_daily':
                loaded_dates.append(identity)
                if identity == historical['daily_identity']:
                    self.fail('delayed answer reopened historical daily identity')
            return state(action, identity, payload)
        current_time = [datetime(2026, 8, 11, 2, 0, tzinfo=timezone.utc)]
        class ProcessingClock(datetime):
            @classmethod
            def now(cls, tz=None):
                return current_time[0]
        kwargs = dict(environ=_two_manager_env(), store=daily_store,
            herd_loader=lambda: _specialist('herdmaster'),
            rootline_loader=lambda: _specialist('rootline'),
            litter_loader=lambda: {'allocation_inputs': {'litter_rows': []}},
            sales_loader=lambda: ({'success': True, 'sales_transactions': []}, 200),
            deliver=lambda *args, **kw: sends.append(kw['mission_id']) or {
                'success': True, 'telegram_message_id': 'current-day-card', 'telegram_sends': 1})
        with patch.object(morning, 'datetime', ProcessingClock), patch.object(daily, 'daily_farm_manager_store', daily_store):
            before_due = morning.reassess_current_brief_after_owner_answer(parsed, **kwargs)
            self.assertEqual(before_due['status'], 'daily_manager_not_due')
            self.assertEqual(sends, [])
            current_time[0] = datetime(2026, 8, 11, 5, 0, tzinfo=timezone.utc)
            current = morning.reassess_current_brief_after_owner_answer(parsed, **kwargs)
            repeated = morning.reassess_current_brief_after_owner_answer(parsed, **kwargs)
        self.assertEqual(current['status'], 'daily_manager_presented')
        self.assertEqual(repeated['status'], 'daily_manager_unchanged_silent')
        self.assertEqual(len(sends), 1)
        self.assertTrue(sends[0].startswith('OOM-DAILY-FARM-MANAGER-2026-08-11:'))
        self.assertEqual(set(loaded_dates), {'OOM-DAILY-FARM-MANAGER-2026-08-11'})
        self.assertEqual(parsed, original_parsed)
        self.assertEqual(state.rows['historical-ambiguous-outcome'], historical)


@pytest.fixture(scope="module", autouse=True)
def exact_migration():
    with connect() as db:
        db.execute("create schema if not exists app_private")
        db.execute("""create table if not exists app_private.migration_log(
            migration_id text primary key,description text not null)""")
        for role in ("anon", "authenticated"):
            db.execute("do $block$ begin execute 'create role %s'; exception when duplicate_object then null; end $block$" % role)
    with connect() as db:
        migrations = Path(__file__).parents[1] / "supabase" / "migrations"
        db.execute((migrations / "202608170002_create_oom_manager_case_runtime.sql").read_text(encoding="utf-8"))
        db.execute("""create table if not exists app_private.oom_protected_action_claims(
            callback_token text primary key,action_kind text not null,
            provider_message_id text,status text,result_payload jsonb,
            completed_at timestamptz)""")
        db.execute((migrations / "202608190002_create_beacon_protected_publication_consumer.sql").read_text(encoding="utf-8"))


def candidate(ref="event:one", due=None, **changes):
    value = {"dedupe_key": "rootline:current-plan", "specialist": "ROOTLINE",
        "urgency": "urgent", "evidence_refs": [ref],
        "unknowns": ["delivered_current_irrigation_plan"],
        "summary": "Current irrigation plan is contained.",
        "next_action": "Delegate to ROOTLINE and retain ownership.",
        "next_reassessment_at": (due or datetime.now(timezone.utc)).isoformat()}
    value.update(changes)
    return value


def test_exact_replay_is_one_case_and_delivery_is_not_duplicated():
    now = datetime.now(timezone.utc)
    store = PostgresManagerCaseStore(connect_factory=connect)
    sends = []
    deliver = lambda case: (sends.append(case["case_id"]) or {
        "success": True, "status": "delivery_confirmed", "delivery_confirmed": True})
    current = candidate(due=now)
    first = store.run_cycle([current], now=now, source_revision="test",
        deliver=deliver, refresh=lambda claimed: current)
    second = store.run_cycle([candidate(due=now)], now=now + timedelta(seconds=1),
        source_revision="test", deliver=deliver, refresh=lambda claimed: current)
    assert first["candidates_created"] == 1 and first["deliveries_confirmed"] == 1
    assert second["candidate_replays"] == 1 and second["deliveries_confirmed"] == 0
    assert sends and len(sends) == 1
    with connect() as db:
        assert db.execute("select count(*) from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()[0] == 1


def test_mixed_suppressions_advance_cadence_and_rotate_beyond_claim_limit(monkeypatch):
    now = datetime.now(timezone.utc) + timedelta(hours=2)
    prefix = "rotation:" + now.strftime("%Y%m%d%H%M%S%f")
    candidates = []
    for index in range(21):
        kind = "non_farm" if index < 7 else ("duplicate" if index < 14 else "no_question")
        candidates.append(candidate(ref=f"event:{index}",
            due=datetime(2000, 1, 1, tzinfo=timezone.utc),
            dedupe_key=f"{prefix}:{kind}:{index:02d}",
            specialist="SAM" if kind == "non_farm" else "HERDMASTER",
            urgency="critical", unknowns=[], summary=f"Silent {kind} case {index}",
            next_action="The specialist reassesses automatically."))
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "5721652188")
    store = PostgresManagerCaseStore(connect_factory=connect)
    by_key = {item["dedupe_key"]: item for item in candidates}
    duplicate_keys = [key for key in by_key if ":duplicate:" in key]
    with connect() as db, db.cursor() as cur:
        for item in candidates:
            assert store._reconcile(cur, normalize_candidate(item, now=now), now) == "created"
        cur.execute("""update app_private.oom_manager_cases
            set last_delivery_digest=evidence_digest where dedupe_key=any(%s)""",
            (duplicate_keys,))
    provider_sends = []
    provider = lambda *_a, **_k: provider_sends.append("unexpected")
    cycles = []
    for offset in range((len(candidates) + CLAIM_LIMIT - 1) // CLAIM_LIMIT):
        cycle_now = now + timedelta(seconds=offset)
        cycles.append(store.run_cycle(candidates, now=cycle_now,
            source_revision="test",
            deliver=lambda case: deliver_farm_manager_case(
                case, now=cycle_now, deliver=provider),
            refresh=lambda claimed: by_key[claimed["dedupe_key"]]))
    final_now = now + timedelta(seconds=len(cycles) - 1)
    assert sum(row["deliveries_suppressed"] for row in cycles) == len(candidates)
    assert all(row["cases_claimed"] <= CLAIM_LIMIT for row in cycles)
    with connect() as db:
        rows = db.execute("""select status,next_reassessment_at from app_private.oom_manager_cases
            where dedupe_key like %s order by dedupe_key""", (prefix + ":%",)).fetchall()
        statuses = db.execute("""select e.event_payload->>'outcome_status',count(*)
            from app_private.oom_manager_case_events e
            join app_private.oom_manager_cases c on c.case_id=e.case_id
            where c.dedupe_key like %s and e.event_type='delivery_suppressed'
            group by e.event_payload->>'outcome_status'""",
            (prefix + ":%",)).fetchall()
    assert len(rows) == 21 and all(row[0] == "waiting_reassessment" for row in rows)
    assert all(row[1] > final_now for row in rows)
    assert dict(statuses) == {"manager_delivery_duplicate_suppressed": 7,
        "no_owner_question_delivery_suppressed": 7,
        "non_farm_case_delivery_suppressed": 7}


def test_two_workers_skip_locked_and_backfill_disjoint_fair_cohorts():
    now=datetime.now(timezone.utc)+timedelta(hours=4)
    prefix="concurrent-fair:"+now.strftime("%Y%m%d%H%M%S%f")
    values=[candidate(f"event:{i}",now,dedupe_key=f"{prefix}:{i:02d}",
        specialist=("ROOTLINE" if i==0 else "SAM"),urgency="urgent",
        unknowns=[],summary=f"case {i}",next_action="reassess") for i in range(30)]
    seed=PostgresManagerCaseStore(connect_factory=connect)
    provider_sends=[]
    with connect() as db,db.cursor() as cur:
        for value in values:
            seed._reconcile(cur,normalize_candidate(value,now=now),now)
    barrier=__import__("threading").Barrier(2)
    def worker(_):
        store=PostgresManagerCaseStore(connect_factory=connect)
        original=store._finish_claim; first=[True]
        def held(*args,**kwargs):
            if first[0]: first[0]=False; barrier.wait(timeout=10)
            return original(*args,**kwargs)
        store._finish_claim=held
        return store.run_cycle([],now=now,source_revision="concurrency-test")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(worker,range(2)))
    assert sorted(row["cases_claimed"] for row in results)==[CLAIM_LIMIT,CLAIM_LIMIT]
    cycle_ids=[row["cycle_id"] for row in results]
    with connect() as db:
        rows=db.execute("""select event_payload->>'cycle_id',count(*) from app_private.oom_manager_case_events e
            join app_private.oom_manager_cases c using(case_id)
            where c.dedupe_key like %s and e.event_type='claimed'
            group by 1""",(prefix+":%",)).fetchall()
    assert sorted(count for _,count in rows if _ in cycle_ids)==[CLAIM_LIMIT,CLAIM_LIMIT]
    assert provider_sends == []


@pytest.mark.parametrize("exception_type", [ValueError, RuntimeError, OSError])
def test_faulty_specialist_refresh_is_contained_without_starving_later_pig(
        monkeypatch, exception_type):
    now = datetime(2025, 2, 3, 4, 5, tzinfo=timezone.utc)
    prefix = ("specialist-containment:" + now.strftime("%Y%m%d%H%M%S")
              + ":" + exception_type.__name__.lower())
    faulty = candidate("provider:mixer", now, dedupe_key=prefix + ":rootline",
        specialist="ROOTLINE", urgency="critical",
        unknowns=["current_provider_mixer_readiness"],
        summary="Mixer registry evidence needs a bounded retry.")
    pig = candidate("pig:PIG-2026-3EE5", now + timedelta(seconds=1),
        dedupe_key=prefix + ":pig", specialist="HERDMASTER", urgency="critical",
        unknowns=[], summary="Mortality follow-up has no owner question.")
    by_key = {row["dedupe_key"]: row for row in (faulty, pig)}
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS", "5721652188")
    sends = []
    def refresh(case):
        if case["dedupe_key"] == faulty["dedupe_key"]:
            raise exception_type("rootline_mixer_registry_binding_invalid")
        return by_key[case["dedupe_key"]]
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [faulty, pig], now=now + timedelta(seconds=2), source_revision="test",
        refresh=refresh, deliver=lambda case: deliver_farm_manager_case(
            case, now=now, deliver=lambda *_a, **_k: sends.append("unexpected")))
    assert result["success"] is True and result["status"] == "general_manager_cycle_completed"
    assert result["cases_claimed"] == 2 and result["exceptions"] == 1
    statuses = {row["case_id"]: row["outcome_status"] for row in result["case_results"]}
    with connect() as db:
        rows = db.execute("""select case_id,dedupe_key,status,next_reassessment_at,
            assigned_worker_id,lease_until from app_private.oom_manager_cases
            where dedupe_key like %s order by dedupe_key""", (prefix + ":%",)).fetchall()
        events = db.execute("""select c.dedupe_key,e.event_type,e.event_payload
            from app_private.oom_manager_case_events e
            join app_private.oom_manager_cases c using(case_id)
            where c.dedupe_key like %s and e.event_type in ('exception','delivery_suppressed')
            order by c.dedupe_key,e.occurred_at""", (prefix + ":%",)).fetchall()
    assert len(rows) == 2
    assert all(row[2] == "waiting_reassessment" for row in rows)
    assert all(row[3] > now + timedelta(seconds=2) for row in rows)
    assert all(row[4:] == (None, None) for row in rows)
    assert set(statuses.values()) == {
        "manager_specialist_processing_exception_contained",
        "no_owner_question_delivery_suppressed"}
    assert any(row[0] == faulty["dedupe_key"] and row[1] == "exception"
        and row[2]["outcome_status"] == "manager_specialist_processing_exception_contained"
        and row[2]["failure_kind"] == exception_type.__name__
        for row in events)
    assert sends == []
    repeat = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [faulty, pig], now=now + timedelta(seconds=3), source_revision="test",
        refresh=refresh, deliver=lambda case: sends.append("unexpected"))
    assert repeat["cases_claimed"] == 0 and sends == []


@pytest.mark.parametrize("exception_type", [ValueError, RuntimeError, OSError])
def test_faulty_specialist_delivery_is_contained_per_case(monkeypatch, exception_type):
    now = datetime(2025, 2, 3, 5, 5, tzinfo=timezone.utc)
    prefix = "delivery-containment:" + exception_type.__name__.lower()
    faulty = candidate("provider:delivery", now, dedupe_key=prefix + ":rootline",
        specialist="ROOTLINE", urgency="critical")
    later = candidate("pig:PIG-LATER", now + timedelta(seconds=1),
        dedupe_key=prefix + ":pig", specialist="HERDMASTER", urgency="critical",
        unknowns=[])
    def deliver(case):
        if case["dedupe_key"] == faulty["dedupe_key"]:
            raise exception_type("specialist_delivery_failed")
        return {"success": True, "status": "no_owner_question_delivery_suppressed",
            "delivery_confirmed": False, "telegram_sends": 0,
            "next_reassessment_at": (now + timedelta(minutes=5)).isoformat()}
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [faulty, later], now=now + timedelta(seconds=2), source_revision="test",
        refresh=lambda case: case, deliver=deliver)
    assert result["success"] is True and result["cases_claimed"] == 2
    assert result["exceptions"] == 1 and result["deliveries_confirmed"] == 0
    assert {row["outcome_status"] for row in result["case_results"]} == {
        "manager_specialist_processing_exception_contained",
        "no_owner_question_delivery_suppressed"}


@pytest.mark.parametrize("failure", [
    ManagerCaseError("refreshed_dedupe_key_mismatch"),
    RuntimeError("store_lock_failed"), OSError("store_connection_failed")])
def test_refresh_claim_store_failures_remain_cycle_fatal(monkeypatch, failure):
    now = datetime(2025, 2, 3, 6, 5, tzinfo=timezone.utc)
    current = candidate("provider:store", now,
        dedupe_key="store-fatal:" + failure.__class__.__name__.lower())
    store = PostgresManagerCaseStore(connect_factory=connect)
    def fail_store(*_args, **_kwargs):
        raise failure
    monkeypatch.setattr(store, "_refresh_claim", fail_store)
    result = store.run_cycle([current], now=now + timedelta(seconds=2),
        source_revision="test", refresh=lambda case: case, deliver=lambda case: {})
    assert result["success"] is False
    assert result["status"] == "general_manager_cycle_failed"
    assert result["failure"]["kind"] == failure.__class__.__name__


def test_refresh_domain_manager_case_error_remains_cycle_fatal():
    now = datetime(2025, 2, 3, 7, 5, tzinfo=timezone.utc)
    current = candidate("provider:manager-error", now,
        dedupe_key="domain-manager-case-error")
    def refresh(_case):
        raise ManagerCaseError("specialist_invariant_failed")
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [current], now=now + timedelta(seconds=2), source_revision="test",
        refresh=refresh, deliver=lambda case: {})
    assert result["success"] is False
    assert result["failure"]["kind"] == "ManagerCaseError"


def test_delivery_manager_case_error_remains_cycle_fatal():
    now = datetime(2025, 2, 3, 8, 5, tzinfo=timezone.utc)
    current = candidate("provider:delivery-manager-error", now,
        dedupe_key="delivery-manager-case-error")
    def deliver(_case):
        raise ManagerCaseError("delivery_invariant_failed")
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [current], now=now + timedelta(seconds=2), source_revision="test",
        refresh=lambda case: case, deliver=deliver)
    assert result["success"] is False
    assert result["failure"]["kind"] == "ManagerCaseError"


def test_delivery_outcome_normalization_failure_remains_cycle_fatal():
    now = datetime(2025, 2, 3, 9, 5, tzinfo=timezone.utc)
    current = candidate("provider:invalid-delivery-outcome", now,
        dedupe_key="delivery-outcome-normalization-error")
    class InvalidOutcome:
        def __iter__(self):
            raise RuntimeError("delivery_outcome_normalization_failed")
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [current], now=now + timedelta(seconds=2), source_revision="test",
        refresh=lambda case: case, deliver=lambda _case: InvalidOutcome())
    assert result["success"] is False
    assert result["failure"]["kind"] == "RuntimeError"


def test_exact_pig_terminal_evidence_completes_case_once_without_delivery():
    now = datetime.now(timezone.utc) + timedelta(seconds=30)
    dedupe = "herdmaster:bulk-condition:PG-TERMINAL"
    material = candidate("observation:PG-LOW", now, dedupe_key=dedupe,
        specialist="HERDMASTER", summary="Exact pig has material low BCS evidence.",
        next_action="Retain exact-pig recovery monitoring.", unknowns=[])
    recovered = candidate("observation:PG-IN-RANGE", now, dedupe_key=dedupe,
        specialist="HERDMASTER", summary="Exact pig is back in range.",
        next_action="Complete the exact-pig BCS follow-up.", unknowns=[],
        terminal_state="completed")
    store = PostgresManagerCaseStore(connect_factory=connect)
    with connect() as db, db.cursor() as cur:
        opened = normalize_candidate(material, now=now)
        terminal = normalize_candidate(recovered, now=now)
        assert store._reconcile(cur, opened, now) == "created"
        assert store._reconcile(cur, terminal, now) == "changed"
        assert store._reconcile(cur, terminal, now) == "replayed"
    with connect() as db:
        row = db.execute("""select status,generation,evidence_digest,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key=%s""", (dedupe,)).fetchone()
        events = db.execute("""select event_type from app_private.oom_manager_case_events
            where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key=%s)
            order by occurred_at""", (dedupe,)).fetchall()
    assert row == ("completed", 2, terminal["evidence_digest"], None, None)
    assert events.count(("completed",)) == 1


def test_latest_batch_candidate_is_stable_across_repeated_and_concurrent_cycles():
    now = datetime.now(timezone.utc) + timedelta(seconds=45)
    dedupe = "herdmaster:bulk-condition:PG-MULTI-BATCH"
    older = candidate("observation:PG-BATCH-OLDER", now, dedupe_key=dedupe,
        specialist="HERDMASTER", summary="Older low BCS evidence.",
        next_action="Retain recovery monitoring.", unknowns=[])
    latest = candidate("observation:PG-BATCH-LATEST", now, dedupe_key=dedupe,
        specialist="HERDMASTER", summary="Latest exact-pig BCS is in range.",
        next_action="Complete the exact-pig follow-up.", unknowns=[],
        terminal_state="completed")
    store = PostgresManagerCaseStore(connect_factory=connect)
    with connect() as db, db.cursor() as cur:
        assert store._reconcile(cur, normalize_candidate(older, now=now), now) == "created"
        assert store._reconcile(cur, normalize_candidate(latest, now=now), now) == "changed"
    # Every subsequent five-minute collector returns only the latest row. Two
    # independent worker connections serialize on the same stable dedupe key.
    def replay_latest(_worker):
        with connect() as db, db.cursor() as cur:
            return store._reconcile(cur, normalize_candidate(latest, now=now), now)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(replay_latest, range(2))) == ["replayed", "replayed"]
    with connect() as db:
        row = db.execute("""select status,generation,evidence_digest
            from app_private.oom_manager_cases where dedupe_key=%s""", (dedupe,)).fetchone()
        count = db.execute("""select count(*) from app_private.oom_manager_case_events
            where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key=%s)""",
            (dedupe,)).fetchone()[0]
    assert row == ("completed", 2, normalize_candidate(latest, now=now)["evidence_digest"])
    assert count == 2


def test_two_completed_batches_query_and_repeated_cycles_use_only_latest_exact_pig_evidence():
    """Exercise the production collector, not a hand-built candidate sequence."""
    now = datetime.now(timezone.utc)
    suffix = now.strftime("%Y%m%d%H%M%S%f")
    pig_id = f"PG-MULTI-{suffix}"
    older_batch = f"10000000-0000-4000-8000-{suffix[-12:]}"
    latest_batch = f"20000000-0000-4000-8000-{suffix[-12:]}"
    older_draft = f"DRAFT-OLDER-{suffix}"
    latest_draft = f"DRAFT-LATEST-{suffix}"
    with connect() as db:
        db.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm)
            values(%s,%s,'Latest Evidence Pig','Active',true)""",
            (pig_id, f"TAG-{suffix}"))
        db.execute("""insert into public.bulk_weight_batches(
            batch_id,client_draft_id,weight_date,status,updated_at,completed_at)
            values(%s,%s,%s,'complete',%s,%s),(%s,%s,%s,'complete',%s,%s)""",
            (older_batch, older_draft, (now - timedelta(days=7)).date(),
             now - timedelta(days=7), now - timedelta(days=7),
             latest_batch, latest_draft, now.date(), now, now))
        db.execute("""insert into public.pig_weight_events(
            weight_event_id,pig_id,weight_date,weight_kg,source,source_sheet_row,
            bulk_batch_id,created_at) values
            (%s,%s,%s,40,'app_bulk_weight',1,%s,%s),
            (%s,%s,%s,50,'app_bulk_weight',2,%s,%s)""",
            (f"WEIGHT-OLDER-{suffix}", pig_id, (now - timedelta(days=7)).date(),
             older_batch, now - timedelta(days=7),
             f"WEIGHT-LATEST-{suffix}", pig_id, now.date(), latest_batch, now))
        db.execute("""insert into public.pig_observation_events(
            observation_event_id,pig_id,observed_at,recorded_at,observer_reference,
            observation_category,severity,factual_note,measurements_json,source_system,
            source_reference,idempotency_key) values
            (%s,%s,%s,%s,'test','body_condition','attention','older low BCS',
             '{"body_condition_score":2}'::jsonb,'owner','test',%s),
            (%s,%s,%s,%s,'test','body_condition','attention','latest low BCS',
             '{"body_condition_score":2}'::jsonb,'owner','test',%s)""",
            (f"OBS-OLDER-{suffix}", pig_id, now - timedelta(days=7),
             now - timedelta(days=7), f"bulk-bcs:{older_draft}:{pig_id}",
             f"OBS-LATEST-{suffix}", pig_id, now, now,
             f"bulk-bcs:{latest_draft}:{pig_id}"))

    findings = [row for row in _completed_bulk_batch_findings(now, connect=connect)
                if f"pig:{pig_id}" in row["evidence_refs"]]
    assert len(findings) == 2
    by_key = {row["dedupe_key"]: row for row in findings}
    condition = by_key[f"herdmaster:bulk-condition:{pig_id}"]
    weight = by_key[f"herdmaster:bulk-weight-change:{pig_id}"]
    assert f"observation:OBS-LATEST-{suffix}" in condition["evidence_refs"]
    assert f"observation:OBS-OLDER-{suffix}" not in condition["evidence_refs"]
    assert condition.get("terminal_state") is None
    assert f"weight_event:WEIGHT-LATEST-{suffix}" in weight["evidence_refs"]
    assert weight.get("terminal_state") is None

    store = PostgresManagerCaseStore(connect_factory=connect)
    first = store.run_cycle(findings, now=now, source_revision="test")
    second_findings = [row for row in _completed_bulk_batch_findings(
        now + timedelta(minutes=5), connect=connect)
        if f"pig:{pig_id}" in row["evidence_refs"]]
    second = store.run_cycle(second_findings, now=now + timedelta(minutes=5),
                             source_revision="test")
    assert first["candidates_created"] == 2
    assert second["candidate_replays"] == 2
    with connect() as db:
        rows = db.execute("""select dedupe_key,status,generation from app_private.oom_manager_cases
            where dedupe_key in (%s,%s) order by dedupe_key""",
            (condition["dedupe_key"], weight["dedupe_key"])).fetchall()
        event_count = db.execute("""select count(*) from app_private.oom_manager_case_events
            where case_id in (select case_id from app_private.oom_manager_cases
                where dedupe_key in (%s,%s))""",
            (condition["dedupe_key"], weight["dedupe_key"])).fetchone()[0]
    assert rows == [(condition["dedupe_key"], "waiting_reassessment", 1),
                    (weight["dedupe_key"], "waiting_reassessment", 1)]
    assert event_count == 2


@pytest.mark.parametrize("material_kind", ["target-page", "enquiry-policy"])
def test_beacon_material_binding_change_creates_exactly_one_successor(material_kind):
    """Builder-bound Page/policy digest changes advance one manager generation."""
    now = datetime.now(timezone.utc) + timedelta(minutes=10)
    dedupe = f"beacon:material-binding:{material_kind}"

    def value(marker):
        return {"dedupe_key": dedupe, "specialist": "BEACON", "urgency": "due",
            "evidence_refs": [f"beacon_result:{marker * 64}",
                              f"packet:BEACON-{material_kind}-{marker}"],
            "unknowns": ["current_sale_opportunity_proposal_or_exact_media_request"],
            "summary": "Current protected BEACON proposal requires owner review.",
            "next_action": "Deliver only the exact current protected card.",
            "next_reassessment_at": now.isoformat()}

    store = PostgresManagerCaseStore(connect_factory=connect)
    with connect() as db, db.cursor() as cur:
        first = normalize_candidate(value("a"), now=now)
        successor = normalize_candidate(value("b"), now=now)
        assert store._reconcile(cur, first, now) == "created"
        assert store._reconcile(cur, first, now) == "replayed"
        assert store._reconcile(cur, successor, now) == "changed"
        assert store._reconcile(cur, successor, now) == "replayed"
    with connect() as db:
        generation, digest = db.execute("""select generation,evidence_digest
            from app_private.oom_manager_cases where dedupe_key=%s""", (dedupe,)).fetchone()
    assert generation == 2
    assert digest == successor["evidence_digest"]


def test_changed_evidence_advances_generation_and_append_only_events_reject_mutation():
    now = datetime.now(timezone.utc) + timedelta(minutes=1)
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:two", now)], now=now, source_revision="test")
    assert result["candidates_changed"] == 1
    with connect() as db:
        generation = db.execute("select generation from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()[0]
        assert generation == 2
        with pytest.raises(psycopg.errors.RaiseException):
            db.execute("delete from app_private.oom_manager_case_events where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key='rootline:current-plan')")


def test_expired_lease_resumes_after_restart():
    now = datetime.now(timezone.utc) + timedelta(minutes=2)
    with connect() as db:
        db.execute("""update app_private.oom_manager_cases set status='delegated',
            lease_until=%s,next_reassessment_at=%s where dedupe_key='rootline:current-plan'""",
            (now - timedelta(seconds=1), now - timedelta(seconds=1)))
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:two", now)], now=now, source_revision="test")
    assert result["candidate_replays"] == 1
    assert result["cases_claimed"] == 1
    with connect() as db:
        row = db.execute("select status,lease_until,next_reassessment_at from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'").fetchone()
        assert row[0] == "waiting_reassessment" and row[1] is None
        assert row[2] == now + timedelta(minutes=5)


def test_reclaimed_delegated_generation_contains_changed_refresh_before_provider():
    now = datetime.now(timezone.utc) + timedelta(minutes=2, seconds=30)
    store = PostgresManagerCaseStore(connect_factory=connect)
    current = normalize_candidate(candidate("event:two", now), now=now)
    changed = candidate("event:new-after-expired-delegation", now,
        summary="Canonical evidence changed while the prior lease was outstanding.")
    with connect() as db:
        db.execute("""update app_private.oom_manager_cases set status='delegated',
            assigned_worker_id='expired-cycle',lease_until=%s,next_reassessment_at=%s
            where dedupe_key='rootline:current-plan'""",
            (now - timedelta(seconds=1), now - timedelta(seconds=1)))
    delivered = []
    result = store.run_cycle([candidate("event:two", now)], now=now,
        source_revision="test", refresh=lambda claimed: changed,
        deliver=lambda case: delivered.append(case))
    assert delivered == []
    assert result["case_results"][0]["outcome_status"] == (
        "manager_delivery_refreshed_generation_deferred")
    with connect() as db:
        row = db.execute("""select evidence_digest,status,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'""").fetchone()
    assert row == (current["evidence_digest"], "waiting_reassessment", None, None)


def test_changed_case_refresh_supersedes_stale_generation_then_stable_cycle_delivers():
    now = datetime.now(timezone.utc) + timedelta(minutes=3)
    stale = candidate("event:stale-weight", now,
        summary="Weekly weighing: 81 eligible tagged pig(s) missing.")
    current = candidate("batch:69086c13-4436-4548-8ab0-bed5453f6000", now,
        summary="Weekly weighing: 2 eligible tagged pig(s) missing.",
        next_action="Weigh only these missing eligible tags: 123, 151.",
        unknowns=[])
    delivered = []
    store = PostgresManagerCaseStore(connect_factory=connect)
    result = store.run_cycle(
        [stale], now=now, source_revision="test",
        refresh=lambda claimed: current,
        deliver=lambda case: (delivered.append(case) or {
            "success": True, "status": "delivery_confirmed",
            "delivery_confirmed": True}))
    assert result["deliveries_confirmed"] == 0
    assert delivered == []
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_refreshed_generation_deferred"
    stable = store.run_cycle([current], now=now + timedelta(seconds=1),
        source_revision="test", refresh=lambda claimed: current,
        deliver=lambda case: (delivered.append(case) or {
            "success": True, "status": "delivery_confirmed",
            "delivery_confirmed": True}))
    assert stable["deliveries_confirmed"] == 1
    assert delivered[0]["summary"] == current["summary"]
    assert delivered[0]["next_action"].endswith("123, 151.")
    with connect() as db:
        events = db.execute("""select event_type from app_private.oom_manager_case_events
            where case_id=%s order by occurred_at""", (delivered[0]["case_id"],)).fetchall()
    assert ("evidence_changed",) in events


def test_missing_refresh_contains_delivery_and_retains_case():
    now = datetime.now(timezone.utc) + timedelta(minutes=4)
    delivered = []
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:refresh-unavailable", now)], now=now,
        source_revision="test", refresh=lambda claimed: None,
        deliver=lambda case: delivered.append(case))
    assert delivered == []
    assert result["deliveries_confirmed"] == 0
    assert result["exceptions"] == 1
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_refresh_unavailable"


def test_confirmed_refresh_unavailable_preserves_truth_and_rotates_without_resend():
    # Keep this isolated from later-dated shared-module fixtures while still
    # exercising the real claim ordering and persistence rail.
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=10)
    prefix = "confirmed-refresh:" + now.strftime("%Y%m%d%H%M%S%f")
    confirmed = candidate("event:confirmed", now, dedupe_key=prefix + ":confirmed",
        specialist="HERDMASTER", urgency="critical", unknowns=[],
        summary="Confirmed mortality follow-up.")
    next_case = candidate("event:next", now, dedupe_key=prefix + ":next",
        specialist="SAM", urgency="critical", unknowns=[], summary="Next silent case.")
    sends = []
    store = PostgresManagerCaseStore(connect_factory=connect)
    first = store.run_cycle([confirmed], now=now, source_revision="test",
        refresh=lambda _case: confirmed,
        deliver=lambda case: (sends.append(case["case_id"]) or {
            "success": True, "status": "delivery_confirmed", "delivery_confirmed": True}))
    assert first["deliveries_confirmed"] == 1
    with connect() as db:
        before = db.execute("""select evidence_digest,last_delivery_digest,last_delivery_at
            from app_private.oom_manager_cases where dedupe_key=%s""",
            (confirmed["dedupe_key"],)).fetchone()
        db.execute("""update app_private.oom_manager_cases set next_reassessment_at=%s,status='open'
            where dedupe_key=%s""", (now + timedelta(seconds=1), confirmed["dedupe_key"]))
    retry_at = now + timedelta(seconds=2)
    retry = store.run_cycle([confirmed, next_case], now=retry_at, source_revision="test",
        refresh=lambda case: None if case["dedupe_key"] == confirmed["dedupe_key"] else next_case,
        deliver=lambda case: deliver_farm_manager_case(case, now=retry_at,
            deliver=lambda *_a, **_k: sends.append("unexpected")))
    assert retry["exceptions"] == 1
    assert retry["deliveries_confirmed"] == 0
    assert sends == [first["case_results"][0]["case_id"]]
    with connect() as db:
        after = db.execute("""select status,evidence_digest,last_delivery_digest,last_delivery_at,
            next_reassessment_at,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key=%s""",
            (confirmed["dedupe_key"],)).fetchone()
        event = db.execute("""select event_payload from app_private.oom_manager_case_events
            where case_id=%s and event_type='reassessment_scheduled'
            order by occurred_at desc limit 1""",
            (first["case_results"][0]["case_id"],)).fetchone()
    assert after[0] == "waiting_reassessment"
    assert after[1:4] == before
    assert after[4] > retry_at and after[5:] == (None, None)
    assert event[0]["confirmed_generation_preserved"] is True
    assert event[0]["outcome_status"] == "manager_delivery_refresh_unavailable"
    immediate = store.run_cycle([confirmed, next_case],
        now=retry_at + timedelta(seconds=1), source_revision="test",
        refresh=lambda _case: next_case,
        deliver=lambda case: deliver_farm_manager_case(case, now=retry_at,
            deliver=lambda *_a, **_k: sends.append("unexpected")))
    assert immediate["cases_claimed"] == 0
    later_due_at = retry_at + timedelta(minutes=6)
    later_due = store.run_cycle([confirmed, next_case], now=later_due_at,
        source_revision="test",
        refresh=lambda case: None if case["dedupe_key"] == confirmed["dedupe_key"] else next_case,
        deliver=lambda case: deliver_farm_manager_case(case, now=later_due_at,
            deliver=lambda *_a, **_k: sends.append("unexpected")))
    exact_result = next(row for row in later_due["case_results"]
        if row["case_id"] == first["case_results"][0]["case_id"])
    assert exact_result["outcome_status"] == "manager_delivery_refresh_unavailable"
    with connect() as db:
        final = db.execute("""select status,evidence_digest,last_delivery_digest,last_delivery_at,
            next_reassessment_at,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key=%s""",
            (confirmed["dedupe_key"],)).fetchone()
        preservation_events = db.execute("""select count(*)
            from app_private.oom_manager_case_events where case_id=%s
              and event_type='reassessment_scheduled'
              and event_payload->>'confirmed_generation_preserved'='true'""",
            (first["case_results"][0]["case_id"],)).fetchone()[0]
    assert final[0] == "waiting_reassessment"
    assert final[1:4] == before
    assert final[4] > later_due_at and final[5:] == (None, None)
    assert preservation_events == 2
    assert sends == [first["case_results"][0]["case_id"]]


def test_changed_confirmed_case_with_missing_refresh_advances_exception_cadence():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=20)
    prefix = "orphan-refresh:" + now.strftime("%Y%m%d%H%M%S%f")
    old = candidate("event:old", now, dedupe_key=prefix + ":prince",
        specialist="HERDMASTER", urgency="critical",
        unknowns=["What exactly was observed about Prince?"])
    changed = candidate("event:changed", now, dedupe_key=old["dedupe_key"],
        specialist="HERDMASTER", urgency="critical",
        unknowns=["What exactly was observed about Prince?"])
    later = candidate("event:later", now, dedupe_key=prefix + ":later",
        specialist="HERDMASTER", urgency="critical", unknowns=[])
    sends = []
    store = PostgresManagerCaseStore(connect_factory=connect)
    first = store.run_cycle([old], now=now, source_revision="test",
        refresh=lambda _case: old,
        deliver=lambda case: (sends.append(case["case_id"]) or {
            "success": True, "status": "delivery_confirmed",
            "delivery_confirmed": True}))
    with connect() as db:
        confirmed_digest = db.execute("""select last_delivery_digest
            from app_private.oom_manager_cases where dedupe_key=%s""",
            (old["dedupe_key"],)).fetchone()[0]
    before_send = sends[:]
    retry_at = now + timedelta(minutes=6)
    retry = store.run_cycle([changed, later], now=retry_at, source_revision="test",
        refresh=lambda case: None if case["dedupe_key"] == changed["dedupe_key"] else later,
        deliver=lambda case: deliver_farm_manager_case(case, now=retry_at,
            deliver=lambda *_a, **_k: sends.append("unexpected")))
    assert retry["success"] is True and retry["cases_claimed"] == 2
    assert retry["exceptions"] == 1 and retry["deliveries_confirmed"] == 0
    assert sends == before_send
    with connect() as db:
        row = db.execute("""select status,evidence_digest,last_delivery_digest,
            last_delivery_at,next_reassessment_at,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key=%s""",
            (changed["dedupe_key"],)).fetchone()
        event = db.execute("""select event_payload from app_private.oom_manager_case_events
            where case_id=%s and event_type='reassessment_scheduled'
            order by occurred_at desc limit 1""",
            (first["case_results"][0]["case_id"],)).fetchone()[0]
    assert row[0] == "exception"
    assert row[1] != row[2] and row[2] == confirmed_digest
    assert row[3] is not None and row[4] > retry_at
    assert row[5:] == (None, None)
    assert event["next_reassessment_at"] == row[4].isoformat()
    immediate = store.run_cycle([changed, later], now=retry_at + timedelta(seconds=1),
        source_revision="test", refresh=lambda _case: None,
        deliver=lambda _case: sends.append("unexpected"))
    assert immediate["cases_claimed"] == 0 and sends == before_send
    later_due_at = retry_at + timedelta(minutes=6)
    repeated = store.run_cycle([changed, later], now=later_due_at,
        source_revision="test",
        refresh=lambda case: None if case["dedupe_key"] == changed["dedupe_key"] else later,
        deliver=lambda case: deliver_farm_manager_case(case, now=later_due_at,
            deliver=lambda *_a, **_k: sends.append("unexpected")))
    exact = next(item for item in repeated["case_results"]
        if item["case_id"] == first["case_results"][0]["case_id"])
    assert exact["outcome_status"] == "manager_delivery_refresh_unavailable"
    assert sends == before_send
    with connect() as db:
        repeated_row = db.execute("""select status,evidence_digest,last_delivery_digest,last_delivery_at,
            next_reassessment_at,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key=%s""",
            (changed["dedupe_key"],)).fetchone()
    assert repeated_row[0] == "exception"
    assert repeated_row[1] != repeated_row[2] == confirmed_digest
    assert repeated_row[4] > later_due_at and repeated_row[5:] == (None, None)
    successful_at = later_due_at + timedelta(minutes=6)
    successful = store.run_cycle([changed, later], now=successful_at,
        source_revision="test", refresh=lambda case: case,
        deliver=lambda case: (sends.append(case["case_id"]) or {
            "success": True, "status": "delivery_confirmed",
            "delivery_confirmed": True}))
    changed_result = next(item for item in successful["case_results"]
        if item["case_id"] == first["case_results"][0]["case_id"])
    assert changed_result["outcome_status"] == "delivery_confirmed"
    assert successful["cases_claimed"] == 2
    assert successful["deliveries_confirmed"] == 2
    assert sends.count(first["case_results"][0]["case_id"]) == 2
    with connect() as db:
        final = db.execute("""select status,evidence_digest,last_delivery_digest,
            last_delivery_at,assigned_worker_id,lease_until
            from app_private.oom_manager_cases where dedupe_key=%s""",
            (changed["dedupe_key"],)).fetchone()
    assert final[0] == "waiting_reassessment"
    assert final[1] == final[2] and final[1] != confirmed_digest
    assert final[3] == successful_at and final[4:] == (None, None)


def test_delivery_without_refresh_callback_fails_closed():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=30)
    delivered = []
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [candidate("event:no-refresh", now)], now=now, source_revision="test",
        deliver=lambda case: delivered.append(case))
    assert delivered == []
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_refresh_unavailable"


def test_unsuccessful_provider_confirmation_cannot_suppress_retry():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=40)
    current = candidate("event:ambiguous-provider-confirmation", now)
    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [current], now=now, source_revision="test", refresh=lambda claimed: current,
        deliver=lambda case: {"success": False, "status": "ambiguous",
                              "delivery_confirmed": True})
    assert result["deliveries_confirmed"] == 0
    assert result["exceptions"] == 1
    with connect() as db:
        row = db.execute("""select status,last_delivery_digest,evidence_digest
            from app_private.oom_manager_cases where dedupe_key='rootline:current-plan'""").fetchone()
    assert row[0] == "exception"
    assert row[1] != row[2]


def test_provider_ambiguity_is_contained_without_five_minute_reclaim_or_duplicate_send():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=42)
    dedupe = "beacon:provider-ambiguity-contained"
    current = candidate("beacon_result:" + "a" * 64, now,
        dedupe_key=dedupe, specialist="BEACON", urgency="due",
        summary="Current protected BEACON proposal requires owner review.",
        next_action="Retain the exact protected card without duplicate delivery.",
        unknowns=["provider_delivery_truth"])
    attempts = []

    def ambiguous(case):
        attempts.append(case["case_id"])
        return {"success": False, "status": "protected_delivery_ambiguous",
            "delivery_confirmed": False, "provider_outcome_ambiguous": True,
            "do_not_retry_provider_effect": True, "telegram_sends": 0}

    store = PostgresManagerCaseStore(connect_factory=connect)
    first = store.run_cycle([current], now=now, source_revision="test",
        refresh=lambda claimed: current, deliver=ambiguous)
    replay = store.run_cycle([current], now=now + timedelta(minutes=5),
        source_revision="test", refresh=lambda claimed: current, deliver=ambiguous)
    later_replay = store.run_cycle([current], now=now + timedelta(days=2),
        source_revision="test", refresh=lambda claimed: current, deliver=ambiguous)
    assert first["exceptions"] == 1
    assert replay["candidate_replays"] == 1
    assert replay["cases_claimed"] == 0
    assert later_replay["cases_claimed"] == 0
    assert len(attempts) == 1
    with connect() as db:
        row = db.execute("""select status,next_reassessment_at,last_delivery_digest,
            evidence_digest from app_private.oom_manager_cases where dedupe_key=%s""",
            (dedupe,)).fetchone()
        event = db.execute("""select event_payload from app_private.oom_manager_case_events
            where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key=%s)
              and event_type='contained' order by occurred_at desc limit 1""",
            (dedupe,)).fetchone()
    assert row[0] == "contained"
    assert row[2] != row[3]
    assert event[0]["provider_ambiguity_contained"] is True


def test_older_observation_epoch_cannot_replace_newer_herd_evidence():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=45)
    newer = candidate("observed:2026-08-17T13:10:00+00:00", now,
        summary="Current 79/81 coverage.")
    older = candidate("observed:2026-08-17T13:05:00+00:00", now,
        summary="Stale 0/81 coverage.")
    store = PostgresManagerCaseStore(connect_factory=connect)
    store.run_cycle([newer], now=now, source_revision="test")
    store.run_cycle([older], now=now + timedelta(seconds=1), source_revision="test")
    with connect() as db:
        row = db.execute("""select summary,evidence_refs from app_private.oom_manager_cases
            where dedupe_key=%s""", (newer["dedupe_key"],)).fetchone()
    assert row[0] == newer["summary"]
    assert row[1] == newer["evidence_refs"]


def test_exact_replay_advances_epoch_and_blocks_later_stale_material():
    now = datetime.now(timezone.utc) + timedelta(minutes=4, seconds=50)
    first = candidate("observed:2026-08-17T13:00:00+00:00", now,
        summary="Material A.")
    same_newer_epoch = candidate("observed:2026-08-17T13:10:00+00:00", now,
        summary="Material A.")
    stale_changed = candidate("observed:2026-08-17T13:05:00+00:00", now,
        summary="Stale material B.")
    store = PostgresManagerCaseStore(connect_factory=connect)
    store.run_cycle([first], now=now, source_revision="test")
    store.run_cycle([same_newer_epoch], now=now + timedelta(seconds=1), source_revision="test")
    store.run_cycle([stale_changed], now=now + timedelta(seconds=2), source_revision="test")
    with connect() as db:
        row = db.execute("""select summary,evidence_refs from app_private.oom_manager_cases
            where dedupe_key=%s""", (first["dedupe_key"],)).fetchone()
    assert row[0] == "Material A."
    assert "observed:2026-08-17T13:10:00+00:00" in row[1]


def test_concurrent_newer_hold_and_prince_evidence_is_never_overwritten_or_delivered_stale():
    now = datetime.now(timezone.utc) + timedelta(minutes=5)
    stale = candidate("event:old-zero-coverage", now,
        summary="Weekly weighing coverage is 0/81.")
    retained = candidate("event:concurrent-current", now,
        summary="Pig 151 withdrawal/sales hold remains; Prince observation remains requested.",
        next_action="Preserve both supported HERDMASTER boundaries.",
        unknowns=["pig_151_withdrawal_clearance", "prince_trial_observation"])
    delivered = []

    def concurrent_advance(_claimed):
        current = normalize_candidate(retained, now=now)
        with connect() as db:
            row = db.execute("""select generation from app_private.oom_manager_cases
                where dedupe_key=%s for update""", (current["dedupe_key"],)).fetchone()
            db.execute("""update app_private.oom_manager_cases set generation=%s,
                evidence_digest=%s,evidence_refs=%s::jsonb,unknowns=%s::jsonb,
                summary=%s,next_action=%s,assigned_worker_id=null,lease_until=null,
                updated_at=%s where dedupe_key=%s""", (int(row[0]) + 1,
                current["evidence_digest"], json.dumps(current["evidence_refs"]),
                json.dumps(current["unknowns"]), current["summary"],
                current["next_action"], now, current["dedupe_key"]))
        return stale

    result = PostgresManagerCaseStore(connect_factory=connect).run_cycle(
        [stale], now=now, source_revision="test", refresh=concurrent_advance,
        deliver=lambda case: delivered.append(case))
    assert delivered == []
    assert result["case_results"][0]["outcome_status"] == "manager_delivery_refresh_unavailable"
    with connect() as db:
        row = db.execute("""select summary,unknowns from app_private.oom_manager_cases
            where dedupe_key=%s""", (stale["dedupe_key"],)).fetchone()
    assert row[0] == retained["summary"]
    assert set(row[1]) == set(retained["unknowns"])


def test_retained_recovery_family_survives_store_claim_and_routes_one_preview_only():
    now = datetime.now(timezone.utc) + timedelta(minutes=6)
    dedupe = "herdmaster:retained-mortality:pg-" + now.strftime("%H%M%S%f")
    raw = candidate("provider_message:4050", now, dedupe_key=dedupe,
        specialist="HERDMASTER", message_family="retained_protected_recovery",
        unknowns=["fresh_canonical_mortality_preview"],
        summary="Retained Pig 146 mortality requires re-preview.",
        next_action="Route only to the protected mortality preview.")
    previews = []
    def builder(case):
        previews.append((case["case_id"], case["message_family"]))
        return {"success": True, "status": "mortality_preview_ready",
            "answer": "Exact protected preview", "callback_token": "CALLBACK",
            "confirmation_required": True, "writes_farm_data": False}
    store = PostgresManagerCaseStore(connect_factory=connect)
    result = store.run_cycle([raw], now=now, source_revision="test",
        refresh=lambda _case: raw,
        deliver=lambda case: deliver_farm_manager_case(
            case, retained_recovery=builder))
    assert previews and len(previews) == 1
    assert result["deliveries_confirmed"] == 0
    with connect() as db:
        row = db.execute("""select evidence_refs from app_private.oom_manager_cases
            where dedupe_key=%s""", (dedupe,)).fetchone()
        events = db.execute("""select event_type from app_private.oom_manager_case_events
            where case_id=(select case_id from app_private.oom_manager_cases where dedupe_key=%s)""",
            (dedupe,)).fetchall()
    assert "manager_message_family:retained_protected_recovery" in row[0]
    assert {value[0] for value in events} >= {"created", "claimed", "delegated", "delivery_suppressed"}
