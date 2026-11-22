"""Offline validation of the persisted, receipt-bound zero-ON abort contract."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path

import pytest
from modules.telemetry import rootline_command_acceptance as ca
from tests.test_rootline_command_mode import receipt

store = importlib.import_module('modules.telemetry.rootline_irrigation_execution_store')
CAPTURE = json.loads((Path(__file__).parent/'fixtures/rootline_mixer_startup_history.json').read_text())
IDENTITY = CAPTURE['target_execution_id']


def event(action, value):
    return store._stored_event_body(action, value, store._event_id(action, value))


def terminal_history():
    history = [deepcopy(row['execution']) for row in CAPTURE['execution_histories']
        if row['execution']['execution_id'] == IDENTITY]
    claim = next(r for r in history if r['action'] == 'claim_auxiliary_before_on')
    held = next(r for r in history if r['action'] == 'contain_auxiliary_device')
    preimage = store._auxiliary_command_abort_preimage(history, held['event_id'])
    assert preimage is not None
    binding = store._auxiliary_abort_binding(preimage)
    now = datetime.now(timezone.utc)
    off = receipt(claim, 'OFF', at=now-timedelta(seconds=2), attempt=2)
    history.append(event('claim_auxiliary_off_attempt', {'execution_id': IDENTITY, 'attempt': 2,
        'startup_recovery': binding}))
    outcome = event('record_auxiliary_off_outcome', {'execution_id': IDENTITY, 'attempt': 2, 'outcome': off})
    history.append(outcome)
    terminal = event('record_auxiliary_startup_aborted', {**claim, **binding, 'state': 'Aborted',
        'terminal_contract': store._AUXILIARY_COMMAND_ABORT, 'startup_aborted_verified': True,
        'startup_unstarted_verified': True, 'reason': 'startup_never_dispatched_off_command_accepted',
        'provider_on_outcome': 'Not dispatched', 'on_attempts': 0, 'off_attempts': 2,
        'command_off_receipt': off, 'off_outcome_event_id': outcome['event_id'],
        'off_outcome_sha256': store._event_digest(outcome), 'command_duty_closed': True,
        'shutdown_verified': False, 'shutdown_evidence': None, 'physical_state': 'Unknown',
        'physical_delivery': 'Unknown', 'physical_outcome_verified': False,
        'aborted_at': (now-timedelta(seconds=1)).isoformat(), 'objective_satisfied': False,
        'control_completed': False, 'command_program_completed': False, 'mixing_credit': False,
        'verified_runtime_seconds': 0, 'command_accounted_mixing_seconds': 0,
        'reservation_preserved': True, 'on_authority': False})
    return terminal, history


def test_exact_version3_requires_no_claim_relabelling_or_physical_credit():
    terminal, history = terminal_history()
    assert store._verified_auxiliary_startup_abort(terminal, history)
    claim = next(r for r in history if r['action'] == 'claim_auxiliary_before_on')
    assert 'acceptance_mode' not in claim and 'acceptance_mode' not in terminal
    assert terminal['primary_stop_deadline'] == claim['primary_stop_deadline']
    with ca.scope({}):
        assert store._verified_auxiliary_startup_abort(terminal, history), 'a recorded valid terminal survives disabled mode'
    for contract in (store._AUXILIARY_STARTUP_ABORT, store._AUXILIARY_UNSTARTED_ABORT):
        assert not store._verified_auxiliary_startup_abort({**terminal, 'terminal_contract': contract}, history)


@pytest.mark.parametrize('field,value', [('shutdown_verified', True), ('physical_state', 'OFF'),
    ('physical_delivery', 'Verified'), ('physical_outcome_verified', True), ('on_attempts', 1),
    ('dispatch_count', 1), ('off_attempts', 3), ('command_program_completed', True), ('mixing_credit', True),
    ('objective_satisfied', True), ('control_completed', True), ('command_accounted_mixing_seconds', 600),
    ('reservation_preserved', False), ('on_authority', True), ('off_outcome_event_id', 'forged'),
    ('command_duty_closed', False), ('startup_unstarted_verified', False), ('verified_runtime_seconds', 600),
    ('acceptance_mode', ca.MODE), ('command_on_receipt', {'accepted_unambiguous': True}),
    ('primary_stop_deadline', '2099-01-01T00:00:00+00:00'), ('aborted_at', '2099-01-01T00:00:00+00:00')])
def test_persisted_terminal_rejects_inflated_or_changed_truth(field, value):
    terminal, history = terminal_history()
    assert not store._verified_auxiliary_startup_abort({**terminal, field: value}, history)


@pytest.mark.parametrize('action', ['claim_auxiliary_dispatch', 'record_auxiliary_on_outcome', 'mark_auxiliary_active'])
def test_late_on_history_invalidates_terminal_without_retry_authority(action):
    terminal, history = terminal_history(); claim = history[1]
    assert not store._verified_auxiliary_startup_abort(terminal, history+[event(action, claim)])


@pytest.mark.parametrize('field', ['manual_off_active', 'manual_isolation_active'])
def test_manual_flag_on_original_canonical_claim_is_not_cleared(field):
    terminal, history = terminal_history()
    claim = next(r for r in history if r['action'] == 'claim_auxiliary_before_on')
    claim[field] = True
    assert store._auxiliary_command_abort_preimage(history, terminal['containment_event_id']) is None
    assert not store._verified_auxiliary_startup_abort(terminal, history)


@pytest.mark.parametrize('mutation', ['missing_outcome', 'missing_slot', 'duplicate_outcome', 'wrong_attempt', 'pending_slot'])
def test_off_receipt_must_have_one_exact_complete_canonical_slot(mutation):
    terminal, history = terminal_history()
    if mutation == 'missing_outcome': history.pop()
    if mutation == 'missing_slot': history.pop(-2)
    if mutation == 'duplicate_outcome': history.append(deepcopy(history[-1]))
    if mutation == 'wrong_attempt': history[-1]['attempt'] = 3
    if mutation == 'pending_slot': history.append(event('claim_auxiliary_off_attempt', {'execution_id': IDENTITY, 'attempt': 3}))
    assert not store._verified_auxiliary_startup_abort(terminal, history)


def test_reducer_resolves_only_this_exact_hold_and_reopens_on_late_history():
    terminal, history = terminal_history(); history.append(terminal)
    held = next(r for r in history if r['action'] == 'contain_auxiliary_device')
    other = {**held, 'event_id': 'unrelated-hold', 'execution_id': 'unrelated-execution'}
    class Cursor:
        def execute(self, sql, args):
            self.result = ([(r,) for r in history] if "execution_id'=%s" in sql
                else [(other,), (held,), (terminal,)])
        def fetchall(self): return self.result
    result = store._auxiliary_containment_state(Cursor(), held['auxiliary_device_id'])
    assert result['contained'] and result['evidence'] == other
    history.append(event('record_auxiliary_on_outcome', {**held, 'on_outcome': {'accepted_unambiguous': False}}))
    result = store._auxiliary_containment_state(Cursor(), held['auxiliary_device_id'])
    assert result['contained'] and result['evidence'] == held


def test_scheduler_keeps_bounded_recovery_stage_without_payload():
    from modules.oom_sakkie.automatic_reassessment_scheduler import _managed_outcomes
    result = _managed_outcomes({'outcomes': [{'managed_device': 'mixer', 'status': 'auxiliary_device_contained',
        'recovery_stage': 'command_proof', 'recovery_reason': 'canonical_ha_off_acceptance_unproven',
        'execution': {'secret': 'must-not-project'}}]})
    assert result[1]['recovery_stage'] == 'command_proof'
    assert result[1]['recovery_reason'] == 'canonical_ha_off_acceptance_unproven'
    assert 'execution' not in result[1]
    assert len(_managed_outcomes({'recovery_reason': 'x'*1000})[0]['recovery_reason']) == 100


def test_synthetic_fixture_keeps_resolved_predecessors_and_valid_eligibility_bindings():
    from modules.telemetry.rootline_auxiliary_management import validate_auxiliary_eligibility
    assert CAPTURE['fixture_kind'] == 'DETERMINISTIC_SYNTHETIC_TEST_ONLY'
    histories = [row['execution'] for row in CAPTURE['execution_histories']]
    by_id = {row['event_id']: row for row in histories}
    assert len(histories) == 17 and len(CAPTURE['containment_rows']) == 5
    assert len({row['execution_id'] for row in histories}) == 3
    assert CAPTURE['target_containment_event_id'] in by_id
    for row in histories:
        if row['action'] == 'record_auxiliary_startup_aborted':
            assert store._verified_auxiliary_startup_abort(row,
                [item for item in histories if item['execution_id'] == row['execution_id']])
        elif row['action'] == 'reconcile_unstarted_auxiliary':
            assert row['claim_sha256'] == store._event_digest(by_id[row['claim_event_id']])
            assert row['containment_sha256'] == store._event_digest(by_id[row['containment_event_id']])
        elif row['action'] == 'record_auxiliary_eligibility':
            value = {key: item for key, item in row.items() if key not in {'action', 'event_id'}}
            assert validate_auxiliary_eligibility(value,
                now=datetime.fromisoformat(row['decision_at'])) is not None
