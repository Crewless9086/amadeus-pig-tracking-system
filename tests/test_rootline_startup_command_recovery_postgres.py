"""Zero-ON startup retirement through the real coordinator, SQL and HA sender.

Only the HA client wire is synthetic. The dedicated loopback database is opt-in;
no production URL, provider credentials or hardware are used.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
import os
from pathlib import Path
from threading import Event
import uuid

import pytest

from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_home_assistant as ha
from modules.telemetry.rootline_ifttt_transport import RootlineIFTTTTransport
from modules.telemetry.rootline_irrigation_coordinator import (
    advance_auxiliary_execution, _bounded_auxiliary_off, bind_execution_transport)
from tests.test_rootline_auxiliary_startup_recovery_postgres import (
    contained, claim, seed, rows, state, seed_historical_event, off_proof)
from tests.test_rootline_command_mode_postgres import connect, schema, URL
from tests.test_rootline_command_mode import receipt
from tests.test_rootline_home_assistant import fixture as ha_fixture
from tests.test_rootline_fertilizer_auxiliary import mixer_eligibility, NOW

store = importlib.import_module('modules.telemetry.rootline_irrigation_execution_store')
bounded = importlib.import_module('modules.oom_sakkie.bounded_postgres_read')
pytestmark = pytest.mark.skipif(not URL, reason='explicit dedicated command-mode PostgreSQL required')
CAPTURE = json.loads((Path(__file__).parent/'fixtures/rootline_mixer_startup_history.json').read_text())
OLD_ID = CAPTURE['target_execution_id']
ENV = {'ROOTLINE_SONOFF_TRANSPORT': 'home_assistant',
    'ROOTLINE_HOME_ASSISTANT_ACCEPTANCE_MODE': ca.MODE,
    'ROOTLINE_HOME_ASSISTANT_URL': 'https://ha.example.test',
    'ROOTLINE_HOME_ASSISTANT_TOKEN': 'synthetic-offline-token',
    'ROOTLINE_TIMED_CONTROL_ENABLED': 'true', 'ROOTLINE_FERTILIZER_MIXING_ENABLED': 'true'}


@pytest.fixture
def db(monkeypatch):
    with connect() as c:
        c.execute('truncate public.sam_live_stock_conversation_review_events, public.irrigation_events')
    monkeypatch.setenv('DATABASE_URL', URL)
    monkeypatch.setattr(store, 'EVENT_SOURCE', 'containment35-'+uuid.uuid4().hex)
    for key, value in ENV.items(): monkeypatch.setenv(key, value)
    yield URL
    # The leased database is exclusively synthetic. Reuse its existing fixture
    # reset so the legacy suite can seed these exact IDs; keep append-only guards.
    with connect() as c:
        c.execute('truncate public.sam_live_stock_conversation_review_events, public.irrigation_events')


class Wire:
    def __init__(self, monkeypatch):
        self.calls = []; self.services = []; self.service_hook = None; self.failure = None; self.cost = lambda amount: None
        devices, entities, _ = ha_fixture('100204d497')
        debug = {'entities': []}
        for channel, entity in enumerate(entities, 1):
            topic = f'cube2ha/switch/100204d497/toggle_{channel}/state'
            debug['entities'].append({'entity_id': entity['entity_id'], 'discovery_data': {'payload': {
                'unique_id': entity['unique_id'], 'platform': 'switch', 'state_topic': topic,
                'command_topic': topic[:-5]+'set', 'availability_topic': 'cube2ha/100204d497/availability',
                'value_template': '{{ value_json.state }}', 'device': {'identifiers': '100204d497',
                    'manufacturer': 'SONOFF', 'model': '4CHPROR3'}}}})
        wire = self
        class Client:
            def __init__(self, environ): pass
            def __enter__(self): return self
            def __exit__(self, *_): pass
            def request(self, kind, **fields):
                wire.calls.append((kind, deepcopy(fields)))
                wire.cost(2 if kind == 'call_service' else 1)
                if kind == 'config/device_registry/list': return deepcopy(devices)
                if kind == 'config/entity_registry/list': return deepcopy(entities)
                if kind == 'mqtt/device/debug_info': return deepcopy(debug)
                if kind == 'call_service':
                    wire.services.append(deepcopy(fields))
                    if wire.service_hook: wire.service_hook()
                    if wire.failure: raise TimeoutError('synthetic ambiguous service')
                    return {'success': True}
                pytest.fail('Unexpected provider observation or I/O: '+kind)
        original_send = ha.send_state; original_read = ha.read_registered_device
        monkeypatch.setattr(ha, 'send_state', lambda **kw: original_send(**kw, client_factory=Client))
        monkeypatch.setattr(ha, 'read_registered_device', lambda *a, **kw: original_read(*a, **kw, client_factory=Client))
        self.transport = RootlineIFTTTTransport(token_store=None, environ=ENV)


def command_body(execution, body, transport):
    return {**body, 'read_final_off': lambda: pytest.fail('command retirement cannot require physical readback'),
        'recover_command_off': lambda original, binding: _bounded_auxiliary_off(original,
            store.rootline_irrigation_execution_store, bind_execution_transport(transport, original),
            startup_recovery=binding)}


def recover(body):
    return store.rootline_irrigation_execution_store('recover_auxiliary_startup_containment', body)


def captured(db):
    assert CAPTURE['complete'] and CAPTURE['history_rows_total'] == 17
    for row in CAPTURE['execution_histories']: seed_historical_event(db, row['execution'])
    original = next(row['execution'] for row in CAPTURE['execution_histories']
        if row['execution']['execution_id'] == OLD_ID and row['execution']['action'] == 'claim_auxiliary_before_on')
    held = state(original)['evidence']
    assert held['event_id'] == CAPTURE['target_containment_event_id']
    return original, {'execution_id': OLD_ID, 'auxiliary_device_id': original['auxiliary_device_id'],
        'containment_event_id': held['event_id'], 'read_final_off': lambda: off_proof(original)}


def fresh_mixer_eligibility(wire, *, generation=None):
    from modules.telemetry.rootline_auxiliary_management import build_auxiliary_eligibility
    now = datetime.now(timezone.utc)
    context = {"plan_generation": generation or "SYNTHETIC-CURRENT-"+uuid.uuid4().hex,
        "injection_active": False, "verified_mixing_minutes_today": 0,
        "verified_mixing_sessions_today": 0, "mixing_history_valid": True,
        "reserved_mixing_seconds_today": 0, "mixing_history_complete_through": now.isoformat(),
        "power_suitable": True}
    safety = wire.transport.read_safety_configuration(device_id='100204d497', channel=2)
    artifact = build_auxiliary_eligibility(task={'auxiliary_device_id': 'FERTILIZER-MIXER-CH2',
        'planned_seconds': 600}, safety=safety, context=context,
        flags={'ROOTLINE_FERTILIZER_MIXING_ENABLED': True}, now=datetime.now(timezone.utc))
    assert artifact['eligible'], artifact
    return artifact, context


def test_fresh17_actual_coordinator_sql_ha_retires_only_exact_hold(db, monkeypatch):
    original, body = captured(db); before = rows(db, original)
    # Demonstrate the physical-only route's exact original blocker first.
    physical = recover({**body, 'read_final_off': lambda: {'authoritative': False, 'state': 'Unknown'}})
    assert physical['recovery_reason'] == 'current_exact_off_unproven'
    wire = Wire(monkeypatch)
    artifact, context = fresh_mixer_eligibility(wire)
    result = advance_auxiliary_execution(eligibility=artifact, store=store.rootline_irrigation_execution_store,
        transport=wire.transport,
        revalidate=lambda _: pytest.fail('the reconciliation cycle must not enter the ON path'))
    assert result['status'] == 'auxiliary_startup_aborted_reassess', result
    assert result['hardware_commands'] == 1 and not result['auxiliary_contained']
    assert result['next_trigger'] == 'next_normal_current_eligibility'
    assert [s['service'] for s in wire.services] == ['turn_off']
    assert wire.services[0]['target']['entity_id'] == 'switch.renamed_2'
    history = rows(db, original); assert history[:len(before)] == before
    terminal = history[-1]
    assert terminal['terminal_contract'] == store._AUXILIARY_COMMAND_ABORT
    assert terminal['primary_stop_deadline'] == original['primary_stop_deadline']
    assert terminal['consumption_key'] == original['consumption_key']
    assert 'acceptance_mode' not in terminal and 'acceptance_mode' not in original
    assert terminal['command_off_receipt']['idempotency_key'] == OLD_ID+':OFF:2'
    assert terminal['shutdown_verified'] is False and terminal['physical_state'] == 'Unknown'
    assert not terminal['mixing_credit'] and not terminal['command_program_completed']
    assert terminal['on_attempts'] == 0 and terminal['off_attempts'] == 2
    assert store._verified_auxiliary_startup_abort(terminal, history)
    assert store.rootline_irrigation_execution_store('load_active_auxiliary', original['auxiliary_device_id']) is None
    from modules.telemetry.rootline_auxiliary_management import mixing_daily_accounting
    accounting = mixing_daily_accounting(history, now=ca.moment(original['claimed_at']))
    assert accounting['reserved_seconds'] == 600 and accounting['controller_completed_seconds'] == 0
    assert not accounting['premix_verified']
    replay = recover(command_body(original, body, wire.transport))
    assert replay['success'] and not replay['created'] and len(wire.services) == 1
    assert rows(db, original) == history


@pytest.mark.parametrize('dispatched', [False, True])
def test_zero_on_only_command_branch_preserves_uncertain_on(db, monkeypatch, dispatched):
    original, body = contained(db, dispatched=dispatched); wire = Wire(monkeypatch)
    result = recover(command_body(original, body, wire.transport))
    assert result['success'] is (not dispatched), result
    assert len(wire.services) == int(not dispatched)
    assert state(original)['contained'] is dispatched


@pytest.mark.parametrize('defect', ['wrong_device', 'wrong_channel', 'claim_not_zero', 'claim_not_claimed',
    'held_binding_changed', 'held_reason', 'held_off_unverified', 'held_off_wrong_channel', 'held_off_future',
    'duration_extended', 'no_off_barrier', 'record_auxiliary_on_outcome', 'mark_auxiliary_active',
    'record_auxiliary_completed', 'record_auxiliary_control_pulse_stopped', 'record_auxiliary_exception', 'second_hold'])
def test_invalid_histories_keep_hold_without_command(db, monkeypatch, defect):
    original, body = contained(db, dispatched=False, defect=defect); wire = Wire(monkeypatch)
    result = recover(command_body(original, body, wire.transport))
    assert not result['success'] and state(original)['contained'] and not wire.services


@pytest.mark.parametrize('field', ['manual_isolation_active', 'manual_off_active'])
def test_manual_flag_in_canonical_history_never_clears(db, monkeypatch, field):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    # A late canonical ON outcome with an explicit stop also invalidates zero-ON proof.
    seed(db, 'record_auxiliary_on_outcome', {**original, field: True, 'on_outcome': {'accepted_unambiguous': False}})
    assert not recover(command_body(original, body, wire.transport))['success']
    assert not wire.services and state(original)['contained']


def test_competing_owner_and_newer_hold_are_preserved(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    seed(db, 'claim_auxiliary_before_on', claim('injector'))
    result = recover(command_body(original, body, wire.transport))
    assert result['recovery_reason'] == 'auxiliary_owner_still_active'
    assert not wire.services and state(original)['contained']


def test_disabled_command_mode_keeps_physical_path(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    monkeypatch.setenv('ROOTLINE_HOME_ASSISTANT_ACCEPTANCE_MODE', 'physical')
    body = command_body(original, body, wire.transport)
    body['read_final_off'] = lambda: {'authoritative': False, 'state': 'Unknown'}
    result = recover(body)
    assert result['recovery_reason'] == 'current_exact_off_unproven' and not wire.services


def test_two_recoverers_send_one_off_consume_only_slot2(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    body = command_body(original, body, wire.transport)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: recover(body), range(2)))
    assert any(r['success'] for r in results), results
    assert len(wire.services) == 1
    history = rows(db, original)
    assert [r['attempt'] for r in history if r['action'] == 'claim_auxiliary_off_attempt'] == [1, 2]
    assert sum(r['action'] == 'record_auxiliary_startup_aborted' for r in history) == 1


def test_accepted_off_survives_terminal_failure_and_restart_without_resend(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    insert = store._insert_managed_event
    def fail(cursor, action, value):
        result = insert(cursor, action, value)
        if action == store._AUXILIARY_STARTUP_ABORT_ACTION: raise RuntimeError('synthetic terminal rollback')
        return result
    monkeypatch.setattr(store, '_insert_managed_event', fail)
    body = command_body(original, body, wire.transport)
    first = recover(body)
    assert not first['success'] and state(original)['contained'] and len(wire.services) == 1
    assert not any(r['action'] == store._AUXILIARY_STARTUP_ABORT_ACTION for r in rows(db, original))
    monkeypatch.setattr(store, '_insert_managed_event', insert)
    second = recover(body)
    assert second['success'] and second['created'] and len(wire.services) == 1
    assert second['hardware_commands'] == 0


def test_uncertain_service_uses_last_slot_only_next_normal_attempt(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    wire.failure = True; body = command_body(original, body, wire.transport)
    first = recover(body)
    assert not first['success'] and len(wire.services) == 1 and state(original)['contained']
    assert [r['attempt'] for r in rows(db, original) if r['action'] == 'claim_auxiliary_off_attempt'] == [1, 2]
    wire.failure = False
    second = recover(body)
    assert second['success'] and len(wire.services) == 2
    assert second['execution']['command_off_receipt']['idempotency_key'].endswith(':OFF:3')


def test_uncertain_database_outcome_preserves_consumed_slot_without_resend(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    insert = store._insert_managed_event
    def fail(cursor, action, value):
        result = insert(cursor, action, value)
        if action == 'record_auxiliary_off_outcome' and value['attempt'] == 2:
            raise RuntimeError('synthetic OFF persistence rollback')
        return result
    monkeypatch.setattr(store, '_insert_managed_event', fail)
    body = command_body(original, body, wire.transport)
    first = recover(body)
    assert not first['success'] and first['effects_unknown'] and len(wire.services) == 1
    monkeypatch.setattr(store, '_insert_managed_event', insert)
    second = recover(body)
    assert not second['success'] and len(wire.services) == 1 and state(original)['contained']
    assert [r['attempt'] for r in rows(db, original) if r['action'] == 'claim_auxiliary_off_attempt'] == [1, 2]


def test_callback_receipt_without_canonical_outcome_never_retires(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    body = command_body(original, body, wire.transport)
    body['recover_command_off'] = lambda *_: {'commands': 0, 'outcomes': [receipt(original, 'OFF',
        at=datetime.now(timezone.utc), attempt=2)]}
    assert not recover(body)['success'] and not wire.services and state(original)['contained']


@pytest.mark.parametrize('change', ['device', 'channel', 'execution', 'attempt', 'future', 'digest', 'missing_slot', 'forged_slot'])
def test_forged_canonical_off_receipt_or_slot_retains_hold(db, monkeypatch, change):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    proof = receipt(original, 'OFF', at=datetime.now(timezone.utc), attempt=2)
    if change == 'device': proof['device_id'] = '100204e9bc'
    if change == 'channel': proof['channel'] = 1
    if change == 'execution': proof['idempotency_key'] = 'OTHER:OFF:2'
    if change == 'attempt': proof['idempotency_key'] = original['execution_id']+':OFF:3'
    if change == 'future': proof['accepted_at'] = (datetime.now(timezone.utc)+timedelta(days=1)).isoformat()
    proof['receipt_sha256'] = ca.digest({k:v for k,v in proof.items() if k != 'receipt_sha256'})
    if change == 'digest': proof['receipt_sha256'] = 'bad'
    if change != 'missing_slot':
        if change == 'forged_slot':
            seed_historical_event(db, {'action': 'claim_auxiliary_off_attempt', 'execution_id': original['execution_id'],
                'attempt': 2, 'event_id': 'forged-slot'})
        else: seed(db, 'claim_auxiliary_off_attempt', {'execution_id': original['execution_id'], 'attempt': 2})
    seed(db, 'record_auxiliary_off_outcome', {'execution_id': original['execution_id'], 'attempt': 2, 'outcome': proof})
    result = recover(command_body(original, body, wire.transport))
    assert not result['success'] and not wire.services and state(original)['contained'], result


def test_exhausted_attempts_preserve_hold(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    for attempt in (2, 3):
        seed(db, 'claim_auxiliary_off_attempt', {'execution_id': original['execution_id'], 'attempt': attempt})
        seed(db, 'record_auxiliary_off_outcome', {'execution_id': original['execution_id'], 'attempt': attempt,
            'outcome': {'accepted_unambiguous': False, 'status': 'uncertain'}})
    result = recover(command_body(original, body, wire.transport))
    assert not result['success'] and not wire.services and state(original)['contained']


def test_later_fresh_normal_eligibility_starts_through_real_ha_guard(db, monkeypatch):
    original, body = captured(db); wire = Wire(monkeypatch)
    first_artifact, _ = fresh_mixer_eligibility(wire)
    first = advance_auxiliary_execution(eligibility=first_artifact,
        store=store.rootline_irrigation_execution_store, transport=wire.transport,
        revalidate=lambda _: pytest.fail('cleanup and ON must be separate cycles'))
    assert first['status'] == 'auxiliary_startup_aborted_reassess', first
    assert [s['service'] for s in wire.services] == ['turn_off']
    old_terminal = rows(db, original)[-1]
    # A new normal planner decision and canonical eligibility, not the spent old claim.
    fresh, context = fresh_mixer_eligibility(wire)
    assert fresh['execution_id'] not in (original['execution_id'], first_artifact['execution_id'])
    assert store.rootline_irrigation_execution_store('record_auxiliary_eligibility', fresh)['success']
    second = advance_auxiliary_execution(eligibility=fresh,
        store=store.rootline_irrigation_execution_store, transport=wire.transport, revalidate=lambda _: context)
    assert second['status'] == 'auxiliary_on_command_accepted', second
    assert [s['service'] for s in wire.services] == ['turn_off', 'turn_on']
    active = store.rootline_irrigation_execution_store('load_active_auxiliary', original['auxiliary_device_id'])
    assert active['execution_id'] == fresh['execution_id'] and ca.accepted(active['command_on_receipt'], active, 'ON')
    assert active.get('shutdown_verified') is not True
    assert rows(db, original)[-1] == old_terminal
    # A normal restart supervises this fresh duty without replaying ON.
    third = advance_auxiliary_execution(eligibility=None, auxiliary_device_id=original['auxiliary_device_id'],
        store=store.rootline_irrigation_execution_store, transport=wire.transport)
    assert third['status'] == 'auxiliary_command_duty_active', third
    assert len(wire.services) == 2


def test_pending_sender_fences_both_recovery_and_ordinary_late_worker(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    body = command_body(original, body, wire.transport)
    allocated = Event(); release = Event(); transition = store._guarded_managed_transition
    def pause(action, value):
        result = transition(action, value)
        if action == 'claim_auxiliary_off_attempt' and value.get('attempt') == 2 and result.get('created'):
            allocated.set(); assert release.wait(5)
        return result
    monkeypatch.setattr(store, '_guarded_managed_transition', pause)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(recover, body)
        assert allocated.wait(5)
        second = recover(body)
        late = store.rootline_irrigation_execution_store('dispatch_auxiliary_off_edge', {
            'execution_id': original['execution_id'], 'attempt': 3,
            'dispatch': lambda: pytest.fail('a pending startup OFF fences a stale ordinary worker')})
        assert not second['success'] and late['provider_command_attempted'] is False
        assert not wire.services
        release.set(); result = first.result(timeout=5)
    assert result['success'] and len(wire.services) == 1
    assert [r['attempt'] for r in rows(db, original) if r['action'] == 'claim_auxiliary_off_attempt'] == [1, 2]


def test_old_sender_already_allocated_is_not_duplicated_by_recovery(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    allocated = Event(); release = Event(); transition = store._guarded_managed_transition
    def pause(action, value):
        result = transition(action, value)
        if action == 'claim_auxiliary_off_attempt' and value.get('attempt') == 2 and result.get('created'):
            allocated.set(); assert release.wait(5)
        return result
    monkeypatch.setattr(store, '_guarded_managed_transition', pause)
    bound = bind_execution_transport(wire.transport, original)
    with ThreadPoolExecutor(max_workers=2) as pool:
        old = pool.submit(store.rootline_irrigation_execution_store, 'dispatch_auxiliary_off_edge', {
            'execution_id': original['execution_id'], 'attempt': 2, 'dispatch': lambda: bound.set_state(
                device_id=original['device_id'], channel=original['channel'], state='OFF',
                idempotency_key=original['execution_id']+':OFF:2')})
        assert allocated.wait(5)
        assert not recover(command_body(original, body, wire.transport))['success']
        assert not wire.services
        release.set(); assert old.result(timeout=5)['accepted_unambiguous']
    result = recover(command_body(original, body, wire.transport))
    assert result['success'] and len(wire.services) == 1
    # Even before/without retirement, the exact accepted zero-ON OFF fences old senders.
    denied = store.rootline_irrigation_execution_store('dispatch_auxiliary_off_edge', {
        'execution_id': original['execution_id'], 'attempt': 3, 'dispatch': lambda: pytest.fail('duplicate accepted OFF')})
    assert not denied['provider_command_attempted']


@pytest.mark.parametrize('when', ['before_slot', 'after_off'])
def test_competing_owner_wins_before_send_or_retirement(db, monkeypatch, when):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    body = command_body(original, body, wire.transport); callback = body['recover_command_off']
    def race(*args):
        if when == 'before_slot': seed(db, 'claim_auxiliary_before_on', claim('injector'))
        result = callback(*args)
        if when == 'after_off': seed(db, 'claim_auxiliary_before_on', claim('injector'))
        return result
    body['recover_command_off'] = race
    result = recover(body)
    assert not result['success'] and state(original)['contained']
    assert len(wire.services) == int(when == 'after_off')
    assert not recover(body)['success'] and len(wire.services) == int(when == 'after_off')


def test_late_on_history_during_off_cannot_retire_or_grant_credit(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    wire.service_hook = lambda: seed(db, 'record_auxiliary_on_outcome', {
        **original, 'on_outcome': {'accepted_unambiguous': False, 'status': 'late_unknown'}})
    result = recover(command_body(original, body, wire.transport))
    assert not result['success'] and state(original)['contained'] and len(wire.services) == 1
    assert not any(r['action'] == store._AUXILIARY_STARTUP_ABORT_ACTION for r in rows(db, original))


@pytest.mark.parametrize('after_commit', [False, True])
def test_terminal_commit_failure_is_truthful_and_restart_reuses_acceptance(db, monkeypatch, after_commit):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    factory = bounded.connect_bounded_rootline_postgres; insert = store._insert_managed_event
    marked = {'terminal': False}
    def mark(cursor, action, value):
        result = insert(cursor, action, value)
        if action == store._AUXILIARY_STARTUP_ABORT_ACTION: marked['terminal'] = True
        return result
    @contextmanager
    def connection(**kwargs):
        with factory(**kwargs) as c:
            yield c
            fail = marked['terminal'] and not kwargs.get('read_only', True)
            if fail and not after_commit: raise RuntimeError('synthetic failed terminal commit')
        if fail: raise RuntimeError('synthetic lost commit acknowledgement')
    monkeypatch.setattr(store, '_insert_managed_event', mark)
    monkeypatch.setattr(bounded, 'connect_bounded_rootline_postgres', connection)
    body = command_body(original, body, wire.transport)
    result = recover(body)
    assert not result['success'] and result['effects_unknown'] and len(wire.services) == 1, result
    monkeypatch.setattr(bounded, 'connect_bounded_rootline_postgres', factory)
    monkeypatch.setattr(store, '_insert_managed_event', insert)
    assert state(original)['contained'] is (not after_commit)
    restarted = recover(body)
    assert restarted['success'] and restarted['created'] is (not after_commit) and len(wire.services) == 1


@pytest.mark.parametrize('field,value', [('shutdown_verified', True), ('physical_state', 'OFF'),
    ('physical_delivery', 'Verified'), ('physical_outcome_verified', True), ('on_attempts', 1),
    ('dispatch_count', 1), ('off_attempts', 3), ('command_program_completed', True), ('mixing_credit', True),
    ('objective_satisfied', True), ('control_completed', True), ('command_accounted_mixing_seconds', 600),
    ('reservation_preserved', False), ('on_authority', True), ('off_outcome_event_id', 'forged')])
def test_terminal_proof_rejects_weaker_or_inflated_claims(db, monkeypatch, field, value):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    result = recover(command_body(original, body, wire.transport)); assert result['success'], result
    history = rows(db, original); changed = {**result['execution'], field: value}
    assert not store._verified_auxiliary_startup_abort(changed, history)


def test_late_history_invalidates_v3_reducer_without_reopening_sender(db, monkeypatch):
    original, body = contained(db, dispatched=False); wire = Wire(monkeypatch)
    result = recover(command_body(original, body, wire.transport)); assert result['success']
    seed(db, 'record_auxiliary_on_outcome', {**original, 'on_outcome': {'accepted_unambiguous': False}})
    assert state(original)['contained']
    assert not recover(command_body(original, body, wire.transport))['success']
    denied = store.rootline_irrigation_execution_store('dispatch_auxiliary_off_edge', {
        'execution_id': original['execution_id'], 'attempt': 3, 'dispatch': lambda: pytest.fail('retired old sender')})
    assert not denied['provider_command_attempted'] and len(wire.services) == 1


def test_costed_recovery_then_fresh_on_stay_inside_existing_cycle_budget(db, monkeypatch):
    import time
    from modules.telemetry.rootline_cycle_budget import cycle_budget, CYCLE_WORK_SECONDS, remaining_seconds
    original, body = captured(db); wire = Wire(monkeypatch)
    clock = [time.monotonic()]
    def cost(amount): clock[0] += amount
    monkeypatch.setattr(time, 'monotonic', lambda: clock[0])
    wire.cost = cost
    factory = bounded.connect_bounded_rootline_postgres
    @contextmanager
    def connection(**kwargs):
        cost(1)
        with factory(**kwargs) as c: yield c
    monkeypatch.setattr(bounded, 'connect_bounded_rootline_postgres', connection)
    durations = []
    with cycle_budget():
        start = clock[0]; cost(50)  # Explicit synthetic earlier evidence/planning cost.
        artifact, _ = fresh_mixer_eligibility(wire)
        first = advance_auxiliary_execution(eligibility=artifact,
            store=store.rootline_irrigation_execution_store, transport=wire.transport,
            revalidate=lambda _: pytest.fail('same-cycle ON'))
        assert first['status'] == 'auxiliary_startup_aborted_reassess', first
        assert remaining_seconds() > 0
        durations.append(clock[0]-start)
    assert [r['service'] for r in wire.services] == ['turn_off']
    with cycle_budget():
        start = clock[0]; cost(50)
        fresh, context = fresh_mixer_eligibility(wire)
        assert store.rootline_irrigation_execution_store('record_auxiliary_eligibility', fresh)['success']
        second = advance_auxiliary_execution(eligibility=fresh,
            store=store.rootline_irrigation_execution_store, transport=wire.transport, revalidate=lambda _: context)
        assert second['status'] == 'auxiliary_on_command_accepted', second
        assert remaining_seconds() > 0
        durations.append(clock[0]-start)
    assert CYCLE_WORK_SECONDS == 140 and all(50 < duration < CYCLE_WORK_SECONDS for duration in durations), durations
    assert [r['service'] for r in wire.services] == ['turn_off', 'turn_on']
    print({'synthetic_cycle_seconds': durations, 'existing_limit_seconds': CYCLE_WORK_SECONDS,
        'assumptions': '50s earlier work;1s each DB connection/provider preparation call;2s service acceptance',
        'physical_result': 'Unknown', 'production_latency_guarantee': False})


def test_insufficient_existing_budget_holds_without_command_or_new_claim(db, monkeypatch):
    import time
    from modules.telemetry.rootline_cycle_budget import cycle_budget
    original, body = captured(db); wire = Wire(monkeypatch)
    artifact, _ = fresh_mixer_eligibility(wire); before = rows(db, original)
    with cycle_budget(deadline=time.monotonic()+5):
        result = advance_auxiliary_execution(eligibility=artifact,
            store=store.rootline_irrigation_execution_store, transport=wire.transport,
            revalidate=lambda _: pytest.fail('no time for startup'))
    assert result['status'] == 'auxiliary_device_contained' and not wire.services
    assert rows(db, original) == before and state(original)['contained']
