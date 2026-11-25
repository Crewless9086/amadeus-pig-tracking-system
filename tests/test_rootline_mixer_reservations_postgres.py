"""ROOT-EXECUTED ONLY: real transactions on the existing leased test database.

No database lifecycle is owned here. ROOTLINE_HA_COMMAND_TEST_URL must identify
the already assigned loopback:55485/rootline_ha_command_mode_test database.
Only the Home Assistant wire is synthetic; canonical claims, locks, dispatch,
receipt persistence, OFF and replay use production functions and PostgreSQL.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
import time
from threading import Event
import uuid

import pytest
import psycopg

from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_mixer_reservations as mixer
from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_command_mode_postgres import URL, connect, schema
from tests.test_rootline_startup_command_recovery_postgres import Wire
from tests.test_rootline_mixer_reservations import chain, artifact, event, context, ENV, legacy_provider_chain, recovered_command_chain

store = importlib.import_module('modules.telemetry.rootline_irrigation_execution_store')
bounded = importlib.import_module('modules.oom_sakkie.bounded_postgres_read')
pytestmark = pytest.mark.skipif(not URL, reason='root-owned explicit leased local PostgreSQL required')


@pytest.fixture
def db(monkeypatch):
    with connect() as connection:
        connection.execute('truncate public.sam_live_stock_conversation_review_events, public.irrigation_events')
    monkeypatch.setenv('DATABASE_URL', URL)
    monkeypatch.setattr(store, 'EVENT_SOURCE', 'mixer41-'+uuid.uuid4().hex)
    for key, value in ENV.items(): monkeypatch.setenv(key, value)
    yield store.rootline_irrigation_execution_store


def seed(history, *, connection=None):
    def insert(c):
        for index, row in enumerate(history):
            c.execute('''insert into public.sam_live_stock_conversation_review_events
                (review_event_id,chatwoot_conversation_id,source_agent,event_source,recommended_action,review_json,created_at)
                values (%s,%s,'rootline_backend',%s,%s,%s::jsonb,%s)''',
                (row['event_id'], row['execution_id'], store.EVENT_SOURCE, row['action'],
                 json.dumps({'rootline_execution':row}),
                 datetime.now(timezone.utc)-timedelta(seconds=1)+timedelta(microseconds=index)))
    if connection is not None: insert(connection)
    else:
        with connect() as c: insert(c)


def history():
    with connect() as c, c.cursor() as cursor:
        return store._mixer_reservation_rows(cursor)


def proposed(rows, *, generation='91', seconds=None):
    now = datetime.now(timezone.utc)
    value, ctx, safety = artifact(rows, now=now, generation=generation, duration=seconds)
    assert value['eligible'], value
    with connect() as c, c.cursor() as cursor:
        store._insert_managed_event(cursor, 'record_auxiliary_eligibility', value)
    body = {key:value.get(key) for key in ('execution_id','eligibility_id','eligibility_sha256','consumption_key',
        'auxiliary_device_id','device_type','device_id','channel','zone_id','job_id','job_sha256',
        'segment_identity','zone_execution_id','pulse_number','phase_number','batch_generation',
        'maximum_duration_seconds','stop_mode','acceptance_mode','mixer_session')}
    body.update(claimed_at=now.isoformat(), primary_stop_deadline=(now+timedelta(seconds=value['maximum_duration_seconds'])).isoformat(),
        state='claimed', on_attempts=0, off_attempts=0)
    return value, ctx, body


def predecessor():
    now = datetime.now(timezone.utc)
    return chain(at=now-timedelta(seconds=700), elapsed_us=98_377_119,
        identity='ROOTLINE-AUX-MIXER41-PREDECESSOR')


def test_real_claim_full_receipt_history_and_remaining_budget(db):
    before = predecessor(); seed(before)
    value, _, body = proposed(before)
    assert value['maximum_duration_seconds'] == 501
    result = store._claim_single_auxiliary(body)
    assert result['created'], result
    after = history()
    assert all(row in after for row in before)
    claims = [row for row in after if row['action'] == 'claim_auxiliary_before_on']
    assert len(claims) == 2
    account = mixer.project_mixer_sessions(after, now=datetime.now(timezone.utc))
    assert account['session_reserved_microseconds'] == 600_000_000
    assert account['session_count'] == 2 and account['mixer_session'] is None
    assert not store._claim_single_auxiliary(body)['created']


def test_real_coordinator_sql_and_offline_ha_wire_use_new_child_once(db, monkeypatch):
    before = predecessor(); seed(before)
    wire = Wire(monkeypatch)
    value, ctx, _ = proposed(before)
    result = advance_auxiliary_execution(eligibility=value, store=db, transport=wire.transport,
        revalidate=lambda _:ctx)
    assert result['status'] == 'auxiliary_on_command_accepted', result
    child = result['execution']
    assert child['mixer_session'] == value['mixer_session']
    stopped = advance_auxiliary_execution(eligibility=None, store=db, transport=wire.transport,
        auxiliary_device_id=mixer.DEVICE, stop_for_energy=True)
    assert stopped['status'] == 'auxiliary_off_command_accepted', stopped
    after = history()
    group = [row for row in after if row.get('execution_id') == child['execution_id']]
    proof = mixer.closed_command_session(group, now=datetime.now(timezone.utc))
    assert proof is not None
    assert [service['service'] for service in wire.services] == ['turn_on', 'turn_off']
    assert stopped['execution']['physical_outcome'] == 'Unknown'
    assert all(row in after for row in before)
    replay = advance_auxiliary_execution(eligibility=value, store=db, transport=wire.transport,
        revalidate=lambda _:ctx)
    assert replay['hardware_commands'] == 0
    assert len(wire.services) == 2


def test_parallel_stale_generations_admit_only_one_child(db):
    before = predecessor(); seed(before)
    first = proposed(before, generation='91')[2]
    second = proposed(before, generation='92')[2]
    assert first['execution_id'] != second['execution_id']
    assert first['consumption_key'] == second['consumption_key']
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(store._claim_single_auxiliary, (first, second)))
    assert sum(row['created'] for row in results) == 1, results
    assert len([row for row in history() if row['action'] == 'claim_auxiliary_before_on']) == 2


class CursorSpy:
    def __init__(self, cursor, hook): self.cursor, self.hook = cursor, hook
    def __enter__(self): self.cursor.__enter__(); return self
    def __exit__(self, *args): return self.cursor.__exit__(*args)
    def execute(self, sql, params=None):
        self.hook('before', sql, params, self.cursor)
        result = self.cursor.execute(sql, params)
        self.hook('after', sql, params, self.cursor)
        return result
    def __getattr__(self, name): return getattr(self.cursor, name)


class ConnectionSpy:
    def __init__(self, connection, hook): self.connection, self.hook = connection, hook
    def cursor(self, *args, **kwargs): return CursorSpy(self.connection.cursor(*args, **kwargs), self.hook)
    def __getattr__(self, name): return getattr(self.connection, name)


def test_waiter_rereads_committed_history_after_existing_lock(db, monkeypatch):
    before = predecessor(); seed(before)
    winner = proposed(before)[2]; waiter = proposed(before, generation='92')[2]
    entered = Event(); read_committed = []
    original = bounded.connect_bounded_rootline_postgres
    original_connect = psycopg.connect
    def repeatable_default(*args, **kwargs):
        c = original_connect(*args, **kwargs)
        c.isolation_level = psycopg.IsolationLevel.REPEATABLE_READ
        return c
    monkeypatch.setattr(psycopg, 'connect', repeatable_default)
    def hook(stage, sql, params, cursor):
        if stage == 'before' and sql == 'select pg_advisory_xact_lock(%s)': entered.set()
    @contextmanager
    def acquire(**kwargs):
        read_committed.append(kwargs.get('read_committed'))
        with original(**kwargs) as c: yield ConnectionSpy(c, hook)
    monkeypatch.setattr(bounded, 'connect_bounded_rootline_postgres', acquire)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with connect() as owner:
            owner.execute('select pg_advisory_xact_lock(%s)', (1874320911,))
            future = pool.submit(store._claim_single_auxiliary, waiter)
            assert entered.wait(2)
            assert not future.done()
            with owner.cursor() as cursor:
                store._insert_managed_event(cursor, 'claim_auxiliary_before_on', winner)
        result = future.result(timeout=5)
    assert read_committed == [True]
    assert not result['created'] and result['status'] == 'eligibility_already_consumed', result


def test_failed_insert_rolls_back_and_same_slot_remains_eligible(db, monkeypatch):
    before = predecessor(); seed(before); body = proposed(before)[2]
    original = bounded.connect_bounded_rootline_postgres
    def fail_after_insert(stage, sql, params, cursor):
        if stage == 'after' and sql.lstrip().startswith('insert into public.sam_live_stock_conversation_review_events'):
            raise RuntimeError('synthetic transaction rollback after actual INSERT')
    @contextmanager
    def acquire(**kwargs):
        with original(**kwargs) as c: yield ConnectionSpy(c, fail_after_insert)
    with monkeypatch.context() as m:
        m.setattr(bounded, 'connect_bounded_rootline_postgres', acquire)
        with pytest.raises(RuntimeError, match='synthetic transaction rollback'):
            store._claim_single_auxiliary(body)
    assert len([row for row in history() if row['action'] == 'claim_auxiliary_before_on']) == 1
    assert store._claim_single_auxiliary(body)['created']


@pytest.mark.parametrize('defect', ['missing_dispatch', 'missing_off', 'ambiguous_on', 'manual_isolation',
    'extended_deadline', 'second_claim', 'six_sessions', 'over_daily_cap', 'changed_root'])
def test_atomic_admission_rejects_new_conflict_after_eligibility(db, defect):
    before = predecessor(); value, _, body = proposed(before)
    changed = deepcopy(before)
    if defect == 'missing_dispatch': changed = [r for r in changed if r['action'] != 'claim_auxiliary_dispatch']
    elif defect == 'missing_off': changed = [r for r in changed if r['action'] != 'record_auxiliary_off_outcome']
    elif defect == 'ambiguous_on': changed[2]['on_outcome']['accepted_unambiguous'] = False
    elif defect == 'manual_isolation': changed[-1]['manual_isolation_active'] = True
    elif defect == 'extended_deadline': changed[-1]['primary_stop_deadline'] = datetime.now(timezone.utc).isoformat()
    elif defect == 'second_claim':
        extra = deepcopy(changed[0]); extra['event_id'] += '-SECOND'; changed.append(extra)
    elif defect == 'changed_root': changed[0]['maximum_duration_seconds'] = 601
    elif defect in {'six_sessions', 'over_daily_cap'}:
        at = datetime.now(timezone.utc)-timedelta(seconds=13000)
        changed = []
        count = 6 if defect == 'six_sessions' else 4
        for index in range(count):
            changed.extend(chain(at=at+timedelta(seconds=index*700), duration=600,
                identity='LEGACY-CAP-'+str(index)))
    seed(changed)
    result = store._claim_single_auxiliary(body)
    assert not result['created'], result
    assert not any(row.get('execution_id') == value['execution_id'] and row['action'] == 'claim_auxiliary_before_on'
        for row in history())


@pytest.mark.parametrize('plan_mode', ['auto', 'force_custom_plan', 'force_generic_plan'])
def test_complete_history_reader_has_no_date_action_or_count_cutoff(db, plan_mode):
    before = predecessor(); seed(before)
    ancient = chain(at=datetime.now(timezone.utc)-timedelta(days=100), identity='ANCIENT-CLOSED')
    seed(ancient)
    # Sparse outcomes with no device binding must still join to their execution.
    with connect() as c:
        # Retain deliberately small statistics before the bulk insert: source
        # completeness must not rely on a favorable fresh join estimate.
        c.execute('analyze public.sam_live_stock_conversation_review_events')
        c.execute('''insert into public.sam_live_stock_conversation_review_events
            (review_event_id,chatwoot_conversation_id,source_agent,event_source,recommended_action,review_json)
            select 'MIX41-NOISE-'||n,'NOISE-'||n,'rootline_backend',%s,'noise',
                jsonb_build_object('rootline_execution',jsonb_build_object('execution_id','NOISE-'||n,
                    'action','noise','auxiliary_device_id','FERTILIZER-INJECTION-CH1',
                    'device_type','fertilizer_injection_valve','device_id','100204d497','channel',1))
            from generate_series(1,20000) n''', (store.EVENT_SOURCE,))
    statements = []
    def capture(stage, sql, params, cursor):
        if stage == 'before': statements.append((sql, params))
    with connect() as c, c.cursor() as cursor:
        cursor.execute("select set_config('statement_timeout','3000',true), set_config('plan_cache_mode',%s,true)", (plan_mode,))
        started = time.monotonic()
        selected = store._mixer_reservation_rows(CursorSpy(cursor, capture))
        elapsed = time.monotonic()-started
        assert len(selected) == len(before)+len(ancient)
        assert all(row in selected for row in before+ancient)
        assert elapsed < 3, elapsed
        sql, params = statements[0]
        cursor.execute('explain (analyze, buffers, format json) '+sql, params)
        measured = cursor.fetchone()[0][0]
    assert measured['Execution Time'] < 3000
    assert measured['Plan']['Actual Rows'] == len(selected)
    print(json.dumps({'mixer41_complete_history_rows':len(selected), 'unrelated_rows':20000,
        'elapsed_seconds':elapsed, 'plan_cache_mode':plan_mode, 'small_statistics_before_bulk_insert':True,
        'arbitrary_cutoff':False, 'explain':measured}))


def test_real_claim_retains_old_verified_provider_closure_without_command_credit(db):
    now = datetime.now(timezone.utc)
    legacy = legacy_provider_chain(at=now-timedelta(days=1))
    before = legacy+predecessor(); seed(before)
    value, _, body = proposed(before)
    assert value['maximum_duration_seconds'] == 501
    result = store._claim_single_auxiliary(body)
    assert result['created'], result
    after = history()
    assert all(row in after for row in before)
    account = mixer.project_mixer_sessions(after, now=datetime.now(timezone.utc))
    assert account['command_accounted_microseconds'] == 98_377_119
    assert account['session_reserved_microseconds'] == 600_000_000


@pytest.mark.parametrize('defect', ['missing_terminal', 'unverified_shutdown'])
def test_real_claim_rechecks_legacy_closure_before_admission(db, defect):
    now = datetime.now(timezone.utc)
    legacy = legacy_provider_chain(at=now-timedelta(days=1))
    previous = predecessor()
    before = legacy+previous
    _, _, body = proposed(before)
    if defect == 'missing_terminal': legacy = legacy[:-1]
    else:
        terminal = mixer._body(legacy[-1]); terminal['shutdown_verified'] = False
        legacy[-1] = event('record_auxiliary_completed', terminal)
    seed(legacy+previous)
    result = store._claim_single_auxiliary(body)
    assert not result['created'] and result['status'] == 'mixer_session_history_changed', result
    assert not any(row.get('execution_id') == body['execution_id'] and row['action'] == 'claim_auxiliary_before_on'
        for row in history())


@pytest.mark.parametrize('attempts', [2,3])
def test_real_claim_after_bounded_off_retry_preserves_reservation(db, attempts):
    before = recovered_command_chain(at=datetime.now(timezone.utc)-timedelta(seconds=700),attempts=attempts)
    seed(before)
    value, _, body = proposed(before)
    assert value['mixer_session']['kind'] == 'reservation'
    assert value['maximum_duration_seconds'] == 600
    result = store._claim_single_auxiliary(body)
    assert result['created'], result
    after = history()
    assert all(row in after for row in before)
    account = mixer.project_mixer_sessions(after, now=datetime.now(timezone.utc))
    assert account['session_reserved_microseconds'] == 1_200_000_000
    assert account['command_accounted_microseconds'] == account['known_residual_microseconds'] == 0


def test_real_claim_rejects_off_retry_result_gap(db):
    before = recovered_command_chain(at=datetime.now(timezone.utc)-timedelta(seconds=700))
    _, _, body = proposed(before)
    seed([row for row in before if not (row['action']=='record_auxiliary_off_outcome' and row['attempt']==1)])
    result = store._claim_single_auxiliary(body)
    assert not result['created'] and result['status'] == 'mixer_session_history_changed', result
