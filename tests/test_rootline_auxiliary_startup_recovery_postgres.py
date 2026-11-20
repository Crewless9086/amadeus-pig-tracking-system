"""Actual PostgreSQL startup-containment recovery and stale-sender interleavings."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import os
from pathlib import Path
from threading import Event
import uuid

import pytest

store = importlib.import_module('modules.telemetry.rootline_irrigation_execution_store')
bounded = importlib.import_module('modules.oom_sakkie.bounded_postgres_read')
TEST_URL = os.getenv('ROOTLINE_AUXILIARY_RECOVERY_POSTGRES_URL') or os.getenv('ROOTLINE_DISPOSABLE_POSTGRES_URL')
pytestmark = pytest.mark.skipif(not TEST_URL, reason='isolated auxiliary recovery PostgreSQL required')


@pytest.fixture
def db(monkeypatch):
    import psycopg
    from psycopg.conninfo import conninfo_to_dict
    target = conninfo_to_dict(TEST_URL)
    assert target.get('host') == '127.0.0.1' and target.get('dbname') in {
        'auxiliary_containment_20261120', 'rootline_managed', 'rootline_no_send_test'}
    root = Path(os.getenv('ROOTLINE_TEST_SOURCE_ROOT') or Path(__file__).resolve().parents[1])
    with psycopg.connect(TEST_URL) as connection:
        connection.execute((root/'supabase/migrations/202607070001_create_sam_live_stock_conversation_review_events.sql').read_text())
    monkeypatch.setenv('DATABASE_URL', TEST_URL)
    monkeypatch.setattr(store, 'EVENT_SOURCE', 'aux-abort-test-'+uuid.uuid4().hex)
    return TEST_URL


def seed(db, action, body):
    import psycopg
    with psycopg.connect(db) as connection, connection.cursor() as cursor:
        return store._insert_managed_event(cursor, action, body)


def rows(db, execution):
    import psycopg
    with psycopg.connect(db) as connection, connection.cursor() as cursor:
        return store._managed_edge_rows(cursor, execution['execution_id'])


def claim(kind='mixer', *, old=True):
    now = datetime.now(timezone.utc) - timedelta(seconds=90 if old else 0)
    seconds = 600 if kind == 'mixer' else 120
    return {'execution_id': 'AUX-RECOVERY-'+uuid.uuid4().hex,
        'auxiliary_device_id': 'FERTILIZER-MIXER-CH2' if kind == 'mixer' else 'FERTILIZER-INJECTION-CH1',
        'device_type': 'fertilizer_mixer' if kind == 'mixer' else 'fertilizer_injection_valve',
        'device_id': '100204d497', 'channel': 2 if kind == 'mixer' else 1,
        'consumption_key': 'AUX-CONSUME-'+uuid.uuid4().hex,
        'claimed_at': now.isoformat(), 'primary_stop_deadline': (now+timedelta(seconds=seconds)).isoformat(),
        'maximum_duration_seconds': seconds, 'state': 'claimed', 'on_attempts': 0, 'off_attempts': 0}


def off_proof(execution, *, prior=False):
    at = datetime.now(timezone.utc)-timedelta(seconds=20 if prior else 0)
    return {'authoritative': True, 'state': 'OFF', 'device_id': execution['device_id'],
        'channel': execution['channel'], 'evidence_id': uuid.uuid4().hex*2, 'retrieved_at': at.isoformat()}


def contained(db, kind='mixer', *, defect=None):
    original = claim(kind)
    held = {**original, 'state': 'claimed_recovery_required', 'reason': 'restart_or_deadline_ambiguous',
        'shutdown_verified': True, 'shutdown_evidence': off_proof(original, prior=True)}
    dispatched = dict(original)
    if defect == 'wrong_device': original['device_id'] = held['device_id'] = dispatched['device_id'] = 'other'
    if defect == 'wrong_channel': original['channel'] = held['channel'] = dispatched['channel'] = True
    if defect == 'claim_not_zero': original['on_attempts'] = 1
    if defect == 'claim_not_claimed': original['state'] = 'Active'
    if defect == 'dispatch_changed': dispatched['maximum_duration_seconds'] += 1
    if defect == 'held_binding_changed': held['consumption_key'] = 'other'
    if defect == 'held_reason': held['reason'] = 'physical_fault'
    if defect == 'held_off_unverified': held['shutdown_verified'] = False
    if defect == 'held_off_wrong_channel': held['shutdown_evidence']['channel'] = 1 if kind == 'mixer' else 2
    if defect == 'held_off_future': held['shutdown_evidence']['retrieved_at'] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    if defect == 'duration_extended': original['primary_stop_deadline'] = held['primary_stop_deadline'] = dispatched['primary_stop_deadline'] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    seed(db, 'claim_auxiliary_before_on', original)
    if defect != 'no_dispatch': seed(db, 'claim_auxiliary_dispatch', dispatched)
    if defect != 'no_off_barrier': seed(db, 'claim_auxiliary_off_attempt', {'execution_id': original['execution_id'], 'attempt': 1})
    seed(db, 'record_auxiliary_off_outcome', {'execution_id': original['execution_id'], 'attempt': 1,
        'outcome': {'accepted_unambiguous': True}})
    saved = seed(db, 'contain_auxiliary_device', held)
    if defect in {'record_auxiliary_on_outcome', 'mark_auxiliary_active', 'record_auxiliary_completed',
            'record_auxiliary_control_pulse_stopped', 'record_auxiliary_exception'}:
        seed(db, defect, {**original, 'state': 'Active', 'on_outcome': {'accepted_unambiguous': False}})
    if defect == 'second_hold': seed(db, 'contain_auxiliary_device', {**held, 'other_evidence': True})
    return original, {'execution_id': original['execution_id'], 'auxiliary_device_id': original['auxiliary_device_id'],
        'containment_event_id': saved['event_id'], 'read_final_off': lambda: off_proof(original)}


def recover(body):
    return store.rootline_irrigation_execution_store('recover_auxiliary_startup_containment', body)


def state(execution):
    return store.rootline_irrigation_execution_store('load_auxiliary_containment', execution['auxiliary_device_id'])


@pytest.mark.parametrize('kind', ['mixer', 'injector'])
def test_abort_seals_unknown_dispatch_preserves_history_and_reservation(db, kind):
    execution, body = contained(db, kind)
    before = rows(db, execution)
    result = recover(body)
    assert result['success'] and result['created'] and not result['auxiliary_contained'], result
    terminal = result['execution']
    assert terminal['provider_on_outcome'] == 'Unknown' and terminal['on_authority'] is False
    assert terminal['control_completed'] is False and terminal['objective_satisfied'] is False
    assert terminal['reservation_preserved'] is True and 'not_dispatched_verified' not in terminal
    assert rows(db, execution)[:-1] == before and not state(execution)['contained']
    assert store._verified_auxiliary_startup_abort(terminal, rows(db, execution))
    assert store.rootline_irrigation_execution_store('load_active_auxiliary', execution['auxiliary_device_id']) is None
    calls = []
    denied = store.rootline_irrigation_execution_store('dispatch_auxiliary_on_edge', {**execution, 'dispatch': lambda: calls.append('ON')})
    assert denied['accepted_unambiguous'] is False
    for action, payload in [('claim_auxiliary_off_attempt', {'execution_id': execution['execution_id'], 'attempt': 2}),
            ('mark_auxiliary_active', {**execution, 'state': 'Active', 'on_attempts': 1}),
            ('contain_auxiliary_device', {**execution, 'reason': 'late_old_hold'})]:
        assert store.rootline_irrigation_execution_store(action, payload)['success'] is False
    assert calls == [] and rows(db, execution)[-1] == terminal
    if kind == 'mixer':
        from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
        account = mixing_daily_accounting(rows(db, execution), now=datetime.now(timezone.utc))
        assert account['reserved_seconds'] == 600 and account['controller_completed_seconds'] == 0
        assert account['sessions'] == 1 and account['premix_verified'] is False


def test_replay_does_not_read_provider_or_append(db):
    execution, body = contained(db)
    first = recover(body)
    assert first['created']
    body['read_final_off'] = lambda: pytest.fail('exact replay must not read provider')
    second = recover(body)
    assert second['success'] and not second['created'] and second['execution'] == first['execution']
    assert sum(row['action'] == 'record_auxiliary_startup_aborted' for row in rows(db, execution)) == 1
    body['containment_event_id'] = 'different'
    assert not recover(body)['success']


@pytest.mark.parametrize('defect', ['wrong_device', 'wrong_channel', 'claim_not_zero', 'claim_not_claimed',
    'dispatch_changed', 'held_binding_changed', 'held_reason', 'held_off_unverified', 'held_off_wrong_channel',
    'held_off_future', 'duration_extended', 'no_dispatch', 'no_off_barrier', 'record_auxiliary_on_outcome',
    'mark_auxiliary_active', 'record_auxiliary_completed', 'record_auxiliary_control_pulse_stopped',
    'record_auxiliary_exception', 'second_hold'])
def test_unqualified_preimages_never_release_or_read_provider(db, defect):
    execution, body = contained(db, defect=defect)
    body['read_final_off'] = lambda: pytest.fail('invalid preimage must not reach fresh read')
    result = recover(body)
    assert not result['success'] and state(execution)['contained']
    assert not any(row['action'] == 'record_auxiliary_startup_aborted' for row in rows(db, execution))


@pytest.mark.parametrize('field,value', [('authoritative', False), ('state', 'ON'), ('state', 'Unknown'),
    ('channel', 1), ('channel', True), ('device_id', 'other'), ('evidence_id', ''),
    ('retrieved_at', '2026-01-01T00:00:00+00:00'), ('retrieved_at', '2099-01-01T00:00:00+00:00'),
    ('retrieved_at', '2026-11-20T05:00:00'), ('execution_id', 'other')])
def test_fresh_exact_off_required(db, field, value):
    execution, body = contained(db)
    body['read_final_off'] = lambda: {**off_proof(execution), field: value}
    assert not recover(body)['success'] and state(execution)['contained']


def test_caller_cannot_insert_terminal_directly(db):
    result = store.rootline_irrigation_execution_store('record_auxiliary_startup_aborted', {'execution_id': 'forged'})
    assert not result['success']


def test_other_active_auxiliary_or_independent_hold_is_preserved(db):
    execution, body = contained(db)
    sibling = claim('injector')
    seed(db, 'claim_auxiliary_before_on', sibling)
    body['read_final_off'] = lambda: pytest.fail('active sibling must be preserved')
    assert recover(body)['recovery_reason'] == 'auxiliary_owner_still_active'
    assert state(execution)['contained']


def test_newer_different_hold_invalidates_prepared_expected_identity(db):
    execution, body = contained(db)
    other, _ = contained(db)
    body['read_final_off'] = lambda: pytest.fail('newer hold must not be cleared')
    assert not recover(body)['success'] and state(other)['contained']


def test_recovery_does_not_clear_an_older_independent_hold(db):
    older, _ = contained(db)
    execution, body = contained(db)
    result = recover(body)
    assert result['success'] and result['auxiliary_contained'], result
    assert state(execution)['contained'] and state(execution)['evidence']['execution_id'] == older['execution_id']


def test_insert_failure_rolls_back_and_preserves_containment(db, monkeypatch):
    execution, body = contained(db); original = store._insert_managed_event
    def fail(cursor, action, record):
        result = original(cursor, action, record)
        if action == 'record_auxiliary_startup_aborted': raise RuntimeError('synthetic rollback')
        return result
    monkeypatch.setattr(store, '_insert_managed_event', fail)
    result = recover(body)
    assert not result['success'] and state(execution)['contained']
    assert not any(row['action'] == 'record_auxiliary_startup_aborted' for row in rows(db, execution))


def test_final_read_changed_preimage_fails_closed(db):
    execution, body = contained(db)
    def read():
        seed(db, 'record_auxiliary_on_outcome', {**execution, 'on_outcome': {'accepted_unambiguous': True}})
        return off_proof(execution)
    body['read_final_off'] = read
    result = recover(body)
    assert not result['success'] and state(execution)['contained']


def test_concurrent_recovery_records_one_terminal(db):
    execution, body = contained(db)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: recover(body), range(2)))
    assert all(result['success'] for result in results) and sum(result['created'] for result in results) == 1, results


def test_new_claim_waits_for_fresh_off_and_commit(db):
    execution, body = contained(db)
    entered = Event(); release = Event(); requested = Event()
    def read():
        entered.set(); assert release.wait(2)
        return off_proof(execution)
    body['read_final_off'] = read
    new = claim(old=False)
    def next_claim():
        requested.set()
        return store.rootline_irrigation_execution_store('claim_auxiliary_before_on', new)
    with ThreadPoolExecutor(max_workers=2) as pool:
        abort = pool.submit(recover, body); assert entered.wait(2)
        following = pool.submit(next_claim); assert requested.wait(2)
        assert not following.done(); release.set()
        assert abort.result(3)['created'] and following.result(3)['created']


def test_old_off_arriving_after_new_claim_cannot_stop_new_on(db, monkeypatch):
    execution, body = contained(db)
    claimed = Event(); release = Event(); commands = []
    original = store._guarded_managed_transition
    def pause(action, payload):
        result = original(action, payload)
        if action == 'claim_auxiliary_off_attempt' and payload['execution_id'] == execution['execution_id'] and payload['attempt'] == 2:
            claimed.set(); assert release.wait(3)
        return result
    monkeypatch.setattr(store, '_guarded_managed_transition', pause)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(store.rootline_irrigation_execution_store, 'dispatch_auxiliary_off_edge',
            {'execution_id': execution['execution_id'], 'attempt': 2,
                'dispatch': lambda: commands.append('OLD_OFF') or {'accepted_unambiguous': True}})
        assert claimed.wait(2)
        assert recover(body)['created']
        new = claim(old=False)
        assert store.rootline_irrigation_execution_store('claim_auxiliary_before_on', new)['created']
        accepted = store.rootline_irrigation_execution_store('dispatch_auxiliary_on_edge',
            {**new, 'dispatch': lambda: commands.append('NEW_ON') or {'accepted_unambiguous': True}})
        assert accepted['accepted_unambiguous']
        release.set(); result = pending.result(3)
    assert result['provider_command_attempted'] is False and result['status'] == 'auxiliary_execution_retired'
    assert commands == ['NEW_ON']


def test_off_already_in_flight_finishes_before_recovery_final_read(db):
    execution, body = contained(db)
    entered = Event(); release = Event(); order = []
    def old_off():
        order.append('OFF_ENTER'); entered.set(); assert release.wait(2)
        order.append('OFF_RETURN'); return {'accepted_unambiguous': True}
    def read():
        order.append('FRESH_OFF'); return off_proof(execution)
    body['read_final_off'] = read
    with ThreadPoolExecutor(max_workers=2) as pool:
        off = pool.submit(store.rootline_irrigation_execution_store, 'dispatch_auxiliary_off_edge',
            {'execution_id': execution['execution_id'], 'attempt': 2, 'dispatch': old_off})
        assert entered.wait(2)
        abort = pool.submit(recover, body)
        assert not abort.done(); release.set()
        assert off.result(3)['provider_command_attempted'] and abort.result(3)['created']
    assert order == ['OFF_ENTER', 'OFF_RETURN', 'FRESH_OFF']


def test_prepared_read_binding_and_cleanup_only_after_commit(db):
    execution, body = contained(db); events = []
    class Prepared:
        def read_locked(self, *, binding, connection, deadline):
            assert binding['execution_id'] == execution['execution_id']
            assert binding['dispatch_event_id'] and binding['containment_event_id'] == body['containment_event_id']
            assert connection.execute("select count(*) from pg_locks where pid=pg_backend_pid() and locktype='advisory' and granted").fetchone()[0] >= 2
            events.append('read'); return off_proof(execution)
        def after_abort_commit(self, terminal):
            assert rows(db, execution)[-1] == terminal
            assert not state(execution)['contained']
            events.append('cleanup'); return 'completed'
    @contextmanager
    def prepare(binding):
        events.append('prepare'); yield Prepared(); events.append('close')
    body['prepare_final_off'] = prepare
    body['read_final_off'] = lambda: pytest.fail('prepared path must use locked fresh read')
    result = recover(body)
    assert result['success'] and result['cleanup_status'] == 'completed'
    assert events == ['prepare', 'read', 'cleanup', 'close']


def test_runtime_clock_reversal_never_records_terminal(db, monkeypatch):
    execution, body = contained(db)
    def read():
        proof = off_proof(execution)
        reversed_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        class ReversedClock:
            @staticmethod
            def now(tz): return reversed_at
        monkeypatch.setattr(store, 'datetime', ReversedClock)
        return proof
    body['read_final_off'] = read
    result = recover(body)
    assert not result['success'] and result['recovery_stage'] == 'final_proof'
    assert state(execution)['contained']
    assert not any(row['action'] == 'record_auxiliary_startup_aborted' for row in rows(db, execution))


@pytest.mark.parametrize('offset', [9, -1])
def test_monotonic_elapsed_or_reversal_never_records_terminal(db, monkeypatch, offset):
    import time
    from types import SimpleNamespace
    execution, body = contained(db)
    def read():
        proof = off_proof(execution)
        observed = time.monotonic() + offset
        monkeypatch.setattr(store, 'time', SimpleNamespace(monotonic=lambda: observed))
        return proof
    body['read_final_off'] = read
    result = recover(body)
    assert not result['success'] and result['recovery_stage'] == 'final_proof'
    assert state(execution)['contained']
    assert not any(row['action'] == 'record_auxiliary_startup_aborted' for row in rows(db, execution))


@pytest.mark.parametrize('kind', ['mixer', 'injector'])
def test_coordinator_recovers_held_start_without_on_or_same_cycle_claim(db, kind):
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    from tests.test_rootline_fertilizer_auxiliary import mixer_eligibility, injection_eligibility, NOW
    execution, body = contained(db, kind)
    calls = []
    class Transport:
        def read_output_state(self, *, device_id, channel):
            assert (device_id, channel) == (execution['device_id'], execution['channel'])
            calls.append('fresh_off')
            return off_proof(execution)
        def set_state(self, **kwargs): pytest.fail('recovery grants no provider command')
        def read_safety_configuration(self, **kwargs): pytest.fail('new ON path must await later eligibility')
    artifact = mixer_eligibility() if kind == 'mixer' else injection_eligibility()
    result = advance_auxiliary_execution(eligibility=artifact,
        store=store.rootline_irrigation_execution_store, transport=Transport(), now=NOW,
        revalidate=lambda _: pytest.fail('new ON path must await later eligibility'))
    assert result['status'] == 'auxiliary_startup_aborted_reassess' and result['startup_aborted_verified']
    assert result['hardware_commands'] == 0 and not result['automatic_on_retry']
    assert result['next_trigger'] == 'next_normal_current_eligibility'
    assert calls == ['fresh_off'] and not state(execution)['contained']
    assert sum(r['action'] == 'claim_auxiliary_before_on' for r in rows(db, execution)) == 1


@pytest.mark.parametrize('kind', ['mixer', 'injector'])
def test_native_prepared_output_contract_keeps_consumed_reservation(db, kind):
    from modules.telemetry.rootline_ifttt_transport import _PreparedNoSendOutput
    execution, body = contained(db, kind)
    events = []
    class NativeStatus:
        def read_locked(self, *, binding, connection, deadline):
            assert binding['execution_id'] == execution['execution_id']
            assert connection.execute("select count(*) from pg_locks where pid=pg_backend_pid() and locktype='advisory' and granted").fetchone()[0] >= 2
            events.append('read')
            return {'device_id': execution['device_id'], 'current_outputs_authoritative': True,
                'channels': [{'channel': execution['channel'], 'output_state': 'OFF'}],
                'response_digest': 'a'*64, 'retrieved_at': datetime.now(timezone.utc).isoformat()}
        def after_commit(self, cleanup):
            pytest.fail('no-dispatch cleanup cannot release a consumed dispatch reservation')
    @contextmanager
    def prepare(binding):
        yield _PreparedNoSendOutput(None, NativeStatus(), binding)
    body['prepare_final_off'] = prepare
    body['read_final_off'] = lambda: pytest.fail('native wrapper must use locked read')
    result = recover(body)
    assert result['success'] and result['created'], result
    assert result['cleanup_status'] == 'retained_for_reconciliation'
    assert events == ['read'] and not state(execution)['contained']
    assert sum(row['action'] == 'claim_auxiliary_dispatch' for row in rows(db, execution)) == 1


def test_guarded_off_provider_exception_commits_unknown_then_propagates(db):
    execution, body = contained(db)
    calls=[]
    def unknown():
        calls.append('OFF')
        raise RuntimeError('synthetic provider timeout after attempted OFF')
    with pytest.raises(RuntimeError, match='synthetic provider timeout'):
        store.rootline_irrigation_execution_store('dispatch_auxiliary_off_edge',
            {'execution_id':execution['execution_id'],'attempt':2,'dispatch':unknown})
    recorded=[row for row in rows(db, execution) if row['action']=='record_auxiliary_off_outcome' and row['attempt']==2]
    assert len(recorded)==1
    assert recorded[0]['outcome']['status']=='auxiliary_off_outcome_unknown'
    assert calls==['OFF'] and state(execution)['contained']
    replay=store.rootline_irrigation_execution_store('dispatch_auxiliary_off_edge',
        {'execution_id':execution['execution_id'],'attempt':2,'dispatch':unknown})
    assert not replay['provider_command_attempted'] and calls==['OFF']


@pytest.mark.parametrize('malformed', [None, [], False])
def test_guarded_off_malformed_outcome_stays_unknown_and_consumed(db, malformed):
    execution, body = contained(db)
    with pytest.raises(RuntimeError, match='auxiliary_off_outcome_unknown'):
        store.rootline_irrigation_execution_store('dispatch_auxiliary_off_edge',
            {'execution_id':execution['execution_id'],'attempt':2,'dispatch':lambda:malformed})
    recorded=[row for row in rows(db, execution) if row['action']=='record_auxiliary_off_outcome' and row['attempt']==2]
    assert len(recorded)==1 and recorded[0]['outcome']['status']=='auxiliary_off_outcome_unknown'
    assert state(execution)['contained']


@pytest.mark.parametrize('kind', ['mixer', 'injector'])
@pytest.mark.parametrize('action', ['record_auxiliary_on_outcome', 'record_auxiliary_exception'])
@pytest.mark.parametrize('boundary', ['final_read', 'terminal_insert', 'after_commit'])
def test_late_history_invalidates_startup_abort_without_reopening_commands(db, monkeypatch, kind, action, boundary):
    execution, body = contained(db, kind)
    incoming = {**execution, 'on_outcome': {'accepted_unambiguous': True},
        'reason': 'late_observed_provider_result'}
    appended = []
    def append():
        result = store.rootline_irrigation_execution_store(action, incoming)
        assert result['success'] and result['created']
        appended.append(result)
    if boundary == 'final_read':
        def read():
            append()
            return off_proof(execution)
        body['read_final_off'] = read
    elif boundary == 'terminal_insert':
        original = store._insert_managed_event
        def insert(cursor, event_action, payload):
            result = original(cursor, event_action, payload)
            if event_action == 'record_auxiliary_startup_aborted':
                append()
            return result
        monkeypatch.setattr(store, '_insert_managed_event', insert)
    result = recover(body)
    if boundary == 'after_commit':
        assert result['success']
        append()
    assert len(appended) == 1
    history = rows(db, execution)
    assert any(row['action'] == action for row in history)
    assert store._auxiliary_startup_terminal(history) is None
    assert state(execution)['contained']
    terminals = [row for row in history if row['action'] == 'record_auxiliary_startup_aborted']
    assert len(terminals) == (1 if boundary == 'after_commit' else 0)
    if boundary != 'after_commit':
        assert not result['success']
    body['read_final_off'] = lambda: pytest.fail('contradictory history cannot be replayed as safe')
    assert not recover(body)['success']
    calls = []
    denied = store.rootline_irrigation_execution_store('dispatch_auxiliary_on_edge',
        {**execution, 'dispatch': lambda: calls.append('ON')})
    assert denied.get('accepted_unambiguous') is not True
    if boundary == 'after_commit':
        denied = store.rootline_irrigation_execution_store('dispatch_auxiliary_off_edge',
            {**execution, 'attempt': 2, 'dispatch': lambda: calls.append('OFF')})
        assert denied.get('provider_command_attempted') is not True
    fresh = claim(kind, old=False)
    if kind == 'injector':
        binding = {'job_id': 'ROOTLINE-IRRIGATION-JOB-'+uuid.uuid4().hex,
            'job_sha256': 'a'*64, 'segment_identity': 'ROOTLINE-JOB-SEGMENT-'+uuid.uuid4().hex,
            'zone_id': 'B12345', 'zone_execution_id': 'ZONE-'+uuid.uuid4().hex}
        parent = {**binding, 'execution_id': binding['zone_execution_id'],
            'device_id': '100204e9bc', 'channel': 1, 'state': 'Active'}
        seed(db, 'claim_before_on', parent)
        seed(db, 'mark_active', parent)
        fresh.update(binding, pulse_number=1)
    refused = store.rootline_irrigation_execution_store('claim_auxiliary_before_on', fresh)
    assert refused['created'] is False and refused['status'] == 'auxiliary_contained'
    assert calls == []
    if kind == 'mixer':
        from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
        account = mixing_daily_accounting(history, now=datetime.now(timezone.utc))
        assert account['reserved_seconds'] == 600 and account['controller_completed_seconds'] == 0


@pytest.mark.parametrize('kind', ['mixer', 'injector'])
def test_late_off_history_remains_appendable_without_new_command_authority(db, kind):
    execution, body = contained(db, kind)
    terminal = recover(body)['execution']
    outcome = {'execution_id': execution['execution_id'], 'attempt': 1,
        'outcome': {'accepted_unambiguous': False, 'status': 'late_off_acknowledgement'}}
    first = store.rootline_irrigation_execution_store('record_auxiliary_off_outcome', outcome)
    replay = store.rootline_irrigation_execution_store('record_auxiliary_off_outcome', outcome)
    assert first['created'] and not replay['created']
    assert store._verified_auxiliary_startup_abort(terminal, rows(db, execution))
    calls = []
    denied = store.rootline_irrigation_execution_store('dispatch_auxiliary_off_edge',
        {**execution, 'attempt': 2, 'dispatch': lambda: calls.append('OFF')})
    assert not denied.get('provider_command_attempted') and calls == []
