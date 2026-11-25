from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib
import json
from pathlib import Path

import pytest

from modules.telemetry import rootline_command_acceptance as ca
from modules.telemetry import rootline_mixer_reservations as mixer
from modules.telemetry.rootline_auxiliary_management import (
    build_auxiliary_eligibility, build_auxiliary_tasks, mixing_daily_accounting,
    validate_auxiliary_eligibility, revalidate_auxiliary_execution_edge)
from modules.telemetry.rootline_timed_control import timed_control_scope
from tests.test_rootline_command_mode import receipt, route

store = importlib.import_module('modules.telemetry.rootline_irrigation_execution_store')
CAPTURE = json.loads((Path(__file__).parent/'fixtures/rootline_mixer_accepted_energy_stop.json').read_text())
NOW = datetime.fromisoformat(CAPTURE['observed_at'])
ENV = {'ROOTLINE_SONOFF_TRANSPORT':'home_assistant', 'ROOTLINE_HOME_ASSISTANT_ACCEPTANCE_MODE':ca.MODE,
    'ROOTLINE_TIMED_CONTROL_ENABLED':'true', 'ROOTLINE_FERTILIZER_MIXING_ENABLED':'true'}


def event(action, body):
    return store._stored_event_body(action, body, store._event_id(action, body))


def chain(*, at=NOW, duration=600, elapsed_us=None, session=None, identity='ROOTLINE-AUX-SYNTHETIC-1'):
    claim = {'execution_id':identity, 'eligibility_id':identity+'-ELIGIBILITY', 'eligibility_sha256':'a'*64,
        'consumption_key':mixer.session_key(session) if session else 'LEGACY-'+identity,
        'auxiliary_device_id':mixer.DEVICE, 'device_type':'fertilizer_mixer', 'device_id':'100204d497',
        'channel':2, 'claimed_at':at.isoformat(), 'maximum_duration_seconds':duration,
        'primary_stop_deadline':(at+timedelta(seconds=duration)).isoformat(), 'stop_mode':'scheduled',
        'acceptance_mode':ca.MODE, 'state':'claimed', 'on_attempts':0, 'off_attempts':0,
        'batch_generation':'SYNTHETIC-BATCH', **({'mixer_session':deepcopy(session)} if session else {})}
    on = receipt(claim, 'ON', at=at)
    active = {**claim, 'state':'Active', 'on_attempts':1, 'command_on_receipt':on}
    off_at = at+timedelta(microseconds=duration*1_000_000 if elapsed_us is None else elapsed_us)
    off = receipt(claim, 'OFF', at=off_at)
    terminal = ca.terminal(active, off, now=off_at, reason='energy_stop')
    terminal.update(command_program_completed=False, command_accounted_mixing_seconds=ca.command_seconds(terminal),
        accounted_mixing_seconds=0, control_completed=False)
    return [event('claim_auxiliary_before_on', claim), event('claim_auxiliary_dispatch', claim),
        event('record_auxiliary_on_outcome', {**claim, 'on_attempts':1, 'on_outcome':on}),
        event('mark_auxiliary_active', active),
        event('claim_auxiliary_off_attempt', {'execution_id':identity, 'attempt':1}),
        event('record_auxiliary_off_outcome', {'execution_id':identity, 'attempt':1, 'outcome':off}),
        event('record_auxiliary_completed', terminal)]


def context(history, *, now=NOW, generation='91', batch='SYNTHETIC-BATCH'):
    account = mixing_daily_accounting(history, now=now)
    return {'plan_generation':generation, 'batch_generation':batch, 'mixing_history_valid':account['history_valid'],
        'reserved_mixing_seconds_today':account['reserved_seconds'], 'verified_mixing_sessions_today':account['sessions'],
        'mixing_history_complete_through':now.isoformat(), 'power_suitable':True, 'mixer_session':account['mixer_session']}


def artifact(history, *, now=NOW, duration=None, generation='91', batch='SYNTHETIC-BATCH'):
    from tests.test_rootline_command_mode import Transport
    ctx = context(history, now=now, generation=generation, batch=batch)
    safety = Transport(None, lambda: now).read_safety_configuration(device_id='100204d497', channel=2)
    seconds = duration if duration is not None else (ctx['mixer_session'] or {}).get('maximum_duration_seconds', 0)
    with ca.scope(ENV), timed_control_scope(ENV):
        result = build_auxiliary_eligibility(task={'auxiliary_device_id':mixer.DEVICE, 'planned_seconds':seconds},
            safety=safety, context=ctx, flags={'ROOTLINE_FERTILIZER_MIXING_ENABLED':True}, now=now)
    return result, ctx, safety


def test_production_shaped_energy_stop_uses_exact_receipts_and_preserves_original():
    history = deepcopy(CAPTURE['history']); original = deepcopy(history)
    result = mixer.project_mixer_sessions(history, now=NOW)
    assert result['session_history_valid']
    assert result['command_accounted_microseconds'] == 98_377_119
    assert result['session_reserved_microseconds'] == 600_000_000
    assert result['known_residual_microseconds'] == 501_622_881
    assert result['mixer_session']['maximum_duration_seconds'] == 501
    assert result['command_shortfall_microseconds'] == 1_701_622_881
    assert result['physical_outcome'] == 'Unknown'
    assert history == original
    # Expiry of the original deadline is neither required nor an identity reset.
    later = mixer.project_mixer_sessions(history, now=NOW+timedelta(minutes=20))
    assert later['mixer_session'] == result['mixer_session']


@pytest.mark.parametrize('elapsed', [0, 1, 98_377_119, 599_999_999, 600_000_000, 600_000_001, 610_000_000])
def test_precision_floor_and_known_overrun_never_mint_allowance(elapsed):
    history = chain(elapsed_us=elapsed)
    result = mixer.project_mixer_sessions(history, now=NOW+timedelta(seconds=700))
    assert result['session_history_valid']
    assert result['known_residual_microseconds'] == max(0, 600_000_000-elapsed)
    assert result['session_reserved_microseconds'] == max(600_000_000, elapsed)
    proposed = result['mixer_session']
    assert proposed['maximum_duration_seconds'] <= proposed['remaining_microseconds']//1_000_000
    assert proposed['kind'] == ('continuation' if elapsed <= 599_000_000 else 'reservation')


def test_residual_child_and_two_new_envelopes_keep_fractional_shortfall():
    history = deepcopy(CAPTURE['history'])
    at = NOW
    for index, expected in enumerate((501, 600, 600), 1):
        before = mixer.project_mixer_sessions(history, now=at)
        session = before['mixer_session']
        assert session['maximum_duration_seconds'] == expected
        history.extend(chain(at=at, duration=expected, session=session, identity='CHILD-'+str(index)))
        at += timedelta(seconds=expected+1)
    result = mixer.project_mixer_sessions(history, now=at)
    assert result['session_history_valid']
    assert result['session_reserved_microseconds'] == 1_800_000_000
    assert result['session_count'] == 4
    assert result['known_residual_microseconds'] == result['command_shortfall_microseconds'] == 622_881
    assert result['mixer_session'] is None
    accounting = mixing_daily_accounting(history, now=at)
    assert accounting['reserved_seconds'] == 1800 and accounting['sessions'] == 4
    assert accounting['controller_completed_seconds'] == 0
    assert not accounting['premix_verified']


def test_six_sessions_including_children_are_a_separate_limit():
    history = []; at = NOW
    for index in range(6):
        proposal = mixer.project_mixer_sessions(history, now=at)['mixer_session']
        history.extend(chain(at=at, duration=proposal['maximum_duration_seconds'], elapsed_us=1_000_000,
            session=proposal, identity='SHORT-'+str(index)))
        at += timedelta(seconds=2)
    result = mixer.project_mixer_sessions(history, now=at)
    assert result['session_history_valid'] and result['session_count'] == 6
    assert result['session_reserved_microseconds'] == 600_000_000
    assert result['known_residual_microseconds'] == 594_000_000
    assert result['mixer_session'] is None


@pytest.mark.parametrize('action', mixer._REQUIRED)
@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'wrong_event_id'])
def test_each_canonical_edge_must_be_unique_and_bound(action, mutation):
    history = deepcopy(CAPTURE['history'])
    selected = next(row for row in history if row['action'] == action)
    if mutation == 'missing': history.remove(selected)
    elif mutation == 'duplicate': history.append(deepcopy(selected))
    else: selected['event_id'] = 'ROOTLINE-EXEC-'+'0'*32
    result = mixer.project_mixer_sessions(history, now=NOW)
    assert not result['session_history_valid'] and result['mixer_session'] is None
    assert not result['child_execution_ids']


@pytest.mark.parametrize('defect', ['off_before_on', 'future_off', 'on_hash', 'off_hash', 'other_entity',
    'other_channel', 'other_execution', 'wrong_attempt', 'wrong_duration', 'deadline_extended',
    'manual_isolation', 'manual_off', 'unknown_on', 'second_off', 'reordered', 'unknown_terminal'])
def test_ambiguous_or_conflicting_evidence_grants_no_remainder(defect):
    history = chain(at=NOW-timedelta(seconds=700), elapsed_us=98_377_119)
    claim, dispatch, on, active, barrier, off, terminal = history
    if defect == 'off_before_on': off['outcome']['accepted_at'] = (NOW-timedelta(seconds=701)).isoformat()
    elif defect == 'future_off': off['outcome']['accepted_at'] = (NOW+timedelta(seconds=1)).isoformat()
    elif defect == 'on_hash': on['on_outcome']['receipt_sha256'] = '0'*64
    elif defect == 'off_hash': off['outcome']['receipt_sha256'] = '0'*64
    elif defect == 'other_entity': off['outcome']['entity_id'] = 'switch.other'
    elif defect == 'other_channel': claim['channel'] = 1
    elif defect == 'other_execution': on['execution_id'] = 'OTHER'
    elif defect == 'wrong_attempt': barrier['attempt'] = 2
    elif defect == 'wrong_duration': terminal['maximum_duration_seconds'] = 601
    elif defect == 'deadline_extended': terminal['primary_stop_deadline'] = NOW.isoformat()
    elif defect == 'manual_isolation': terminal['manual_isolation_active'] = True
    elif defect == 'manual_off': terminal['manual_off_active'] = True
    elif defect == 'unknown_on': on['on_outcome']['accepted_unambiguous'] = False
    elif defect == 'second_off': history.append(event('record_auxiliary_off_outcome',
        {'execution_id':claim['execution_id'], 'attempt':2, 'outcome':off['outcome']}))
    elif defect == 'reordered': history[2], history[4] = history[4], history[2]
    elif defect == 'unknown_terminal': terminal['command_duty_closed'] = False
    # Even correctly rehashed conflicting stored rows must fail semantic checks.
    history = [event(row['action'], {k:v for k,v in row.items() if k not in {'action','event_id'}}) for row in history]
    result = mixer.project_mixer_sessions(history, now=NOW)
    assert not result['session_history_valid'] and result['mixer_session'] is None


def test_old_active_or_unknown_claim_blocks_new_day_without_refund():
    history = chain(at=NOW-timedelta(days=1))[:2]
    result = mixer.project_mixer_sessions(history, now=NOW)
    assert not result['session_history_valid'] and result['mixer_session'] is None


def test_midnight_cannot_move_residual_to_another_day():
    at = datetime.fromisoformat('2026-11-22T21:59:30+00:00')
    proposal = mixer.project_mixer_sessions([], now=at)['mixer_session']
    assert proposal['maximum_duration_seconds'] == 600
    history = chain(at=at, duration=30, elapsed_us=1_000_000, session=proposal)
    same = mixer.project_mixer_sessions(history, now=at+timedelta(seconds=2))
    assert same['mixer_session']['maximum_duration_seconds'] == 29
    later_same_slot = mixer.project_mixer_sessions(history, now=at+timedelta(seconds=20))
    assert same['mixer_session'] == later_same_slot['mixer_session']
    after = mixer.project_mixer_sessions(history, now=at+timedelta(seconds=31))
    assert after['mixer_session']['kind'] == 'reservation'
    assert after['known_residual_microseconds'] == 0
    assert after['mixer_session']['root_execution_id'] is None
    assert after['mixer_session']['operating_date'] == '2026-11-23'


def test_accepted_off_after_midnight_charges_known_current_day_overrun():
    at = datetime.fromisoformat('2026-11-22T21:59:30+00:00')
    proposal = mixer.project_mixer_sessions([], now=at)['mixer_session']
    history = chain(at=at, duration=30, elapsed_us=40_377_119, session=proposal)
    result = mixer.project_mixer_sessions(history, now=at+timedelta(seconds=41))
    assert result['session_history_valid']
    assert result['session_reserved_microseconds'] == 10_377_119
    assert result['command_accounted_microseconds'] == 10_377_119
    assert result['session_count'] == 1 and result['known_residual_microseconds'] == 0
    assert result['mixer_session']['remaining_microseconds'] == 1_789_622_881
    assert result['mixer_session']['kind'] == 'reservation'


def test_existing_reconciled_and_aborted_startups_preserve_unknown_reservations():
    base = Path(importlib.import_module('tests.test_rootline_startup_command_recovery_postgres').__file__).parent
    captured = json.loads((base/'fixtures/rootline_mixer_startup_history.json').read_text())
    rows = [row['execution'] for row in captured['execution_histories']
        if row['execution'].get('execution_id') != captured['target_execution_id']]
    first_claim = next(row for row in rows if row['action'] == 'claim_auxiliary_before_on')
    rows = [row for row in rows if row.get('execution_id') == first_claim['execution_id']]
    at = ca.moment(first_claim['claimed_at'])+timedelta(hours=1)
    result = mixer.project_mixer_sessions(rows, now=at)
    assert result['session_history_valid']
    assert result['session_reserved_microseconds'] == 600_000_000
    assert result['known_residual_microseconds'] == 0
    assert result['command_accounted_microseconds'] == 0
    assert result['mixer_session']['kind'] == 'reservation'
    assert result['mixer_session']['remaining_microseconds'] == 1_200_000_000


def test_plan_batch_and_new_decision_time_share_one_consumption_identity():
    history = CAPTURE['history']
    first, ctx, safety = artifact(history)
    second, _, _ = artifact(history, now=NOW+timedelta(seconds=1), generation='92', batch='NEW-BATCH')
    assert first['eligible'] and second['eligible']
    assert first['execution_id'] != second['execution_id']
    assert first['consumption_key'] == second['consumption_key']
    assert first['consumption_key'] != history[1]['consumption_key']
    with ca.scope(ENV), timed_control_scope(ENV):
        assert validate_auxiliary_eligibility(first, now=NOW)
        assert revalidate_auxiliary_execution_edge(first, current_context=ctx, current_safety=safety, now=NOW)
    assert not artifact(history, duration=502)[0]['eligible']


def test_task_planning_uses_child_within_full_daily_reservation():
    at = NOW-timedelta(seconds=1500)
    history = chain(at=at, duration=1800, elapsed_us=98_377_119)
    with ca.scope(ENV), timed_control_scope(ENV):
        plan = build_auxiliary_tasks(batch={'state':'monday_batch_due'}, verified_mixing=history,
            mixing_history_complete_through=NOW.isoformat(), now=NOW,
            power={'observed_at':NOW.isoformat(), 'battery_soc_pct':90, 'solar_power_w':5000,
                   'load_power_w':1000, 'grid_power_w':0, 'battery_power_w':-3000})
    task = plan['irrigation_auxiliary_tasks'][0]
    assert task['decision'] == 'Run now' and task['planned_seconds'] == 600
    assert task['reserved_minutes_today'] == 30
    assert task['command_shortfall_seconds_today'] == 1701.622881
    assert task['physical_mixing_outcome'] == 'Unknown'


def test_short_explicit_task_is_not_expanded():
    value, _, _ = artifact(CAPTURE['history'], duration=17)
    assert value['eligible'] and value['maximum_duration_seconds'] == 17


def test_child_metadata_is_bound_to_eligibility_and_claim():
    value, _, _ = artifact(CAPTURE['history'])
    claim = {**value, 'claimed_at':NOW.isoformat(),
        'primary_stop_deadline':(NOW+timedelta(seconds=501)).isoformat()}
    assert store._scheduled_auxiliary_claim_valid(claim, value, NOW)
    changed = deepcopy(claim); changed['mixer_session']['remaining_microseconds'] += 1
    assert not store._scheduled_auxiliary_claim_valid(changed, value, NOW)
    assert not store._scheduled_auxiliary_claim_valid({**claim, 'acceptance_mode':None}, value, NOW)


def test_consumed_child_disallows_replayed_predecessor_or_modified_root():
    history = deepcopy(CAPTURE['history'])
    session = mixer.project_mixer_sessions(history, now=NOW)['mixer_session']
    first = chain(at=NOW, duration=200, session=session, identity='CHILD-1')
    history.extend(first)
    next_at = NOW+timedelta(seconds=201)
    current = mixer.project_mixer_sessions(history, now=next_at)
    assert current['session_history_valid'] and current['mixer_session'] != session
    assert current['known_residual_microseconds'] == 301_622_881
    history.extend(chain(at=next_at, duration=200, session=session, identity='CHILD-STALE'))
    denied = mixer.project_mixer_sessions(history, now=next_at+timedelta(seconds=201))
    assert not denied['session_history_valid'] and denied['mixer_session'] is None


def test_edge_refuses_a_changed_session_and_conflict_diagnostics_are_bounded():
    from tests.test_rootline_command_mode import Store, Transport
    from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
    value, ctx, safety = artifact(CAPTURE['history'])
    changed = deepcopy(ctx); changed['mixer_session']['predecessor_terminal_sha256'] = '0'*64
    class Refuse(Store):
        def __call__(self, action, body):
            if action == 'claim_auxiliary_before_on':
                return {'success':True, 'created':False, 'status':'mixer_session_history_changed'}
            return super().__call__(action, body)
    memory = Refuse(); transport = Transport(memory, lambda:NOW)
    with ca.scope(ENV), timed_control_scope(ENV):
        assert not revalidate_auxiliary_execution_edge(value, current_context=changed, current_safety=safety, now=NOW)
        result = advance_auxiliary_execution(eligibility=value, store=memory, transport=transport,
            revalidate=lambda _:ctx, now=NOW, clock=lambda:NOW)
    assert result['status'] == 'auxiliary_claim_conflict'
    assert result['claim_status'] == 'mixer_session_history_changed'
    assert result['hardware_commands'] == 0 and not transport.calls


def test_planning_reader_retains_existing_startup_closure_actions(monkeypatch):
    from modules.telemetry import rootline_water_energy_plan as plan
    bounded = importlib.import_module('modules.oom_sakkie.bounded_postgres_read')
    base = Path(importlib.import_module('tests.test_rootline_startup_command_recovery_postgres').__file__).parent
    captured = json.loads((base/'fixtures/rootline_mixer_startup_history.json').read_text())
    rows = [row['execution'] for row in captured['execution_histories']
        if row['execution'].get('execution_id') != captured['target_execution_id']]
    statements = []
    class Read:
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def cursor(self): return self
        def execute(self, sql, params=None): statements.append(sql)
        def fetchall(self): return [(row,) for row in rows] if len(statements) == 1 else []
    monkeypatch.setattr(bounded, 'connect_bounded_read', lambda **_:Read())
    packet = plan._read_managed_device_evidence('synthetic-no-connection', NOW+timedelta(days=1))
    assert packet['status'] == 'Available'
    assert "'record_auxiliary_startup_aborted'" in statements[0]
    assert "'reconcile_unstarted_auxiliary'" in statements[0]
    assert mixer.project_mixer_sessions(packet['fertilizer_executions'], now=NOW+timedelta(days=1))['session_history_valid']


@pytest.mark.parametrize("prior_claim", [False, True])
def test_persisted_candidate_is_not_unknown_work_or_another_reservation(prior_claim):
    history = chain(at=NOW-timedelta(seconds=700), elapsed_us=98_377_119) if prior_claim else []
    original = mixing_daily_accounting(history, now=NOW)
    value, _, _ = artifact(history)
    assert value["eligible"]
    persisted = event("record_auxiliary_eligibility", value)
    account = mixing_daily_accounting(history+[persisted], now=NOW)
    assert account == original
    assert account["history_valid"] and account["session_history_valid"]
    assert account["mixer_session"]["maximum_duration_seconds"] == (501 if prior_claim else 600)
    assert account["sessions"] == (1 if prior_claim else 0)
    assert account["reserved_seconds"] == (600 if prior_claim else 0)


@pytest.mark.parametrize("action", ["claim_auxiliary_before_on", "claim_auxiliary_dispatch", "unknown_work"])
def test_nonproposal_incomplete_history_is_still_unknown(action):
    value, _, _ = artifact([])
    row = event(action, value)
    account = mixing_daily_accounting([row], now=NOW)
    assert account["history_valid"] is False
    assert account["session_history_valid"] is False
    assert account["mixer_session"] is None



def legacy_provider_chain(*, at=NOW-timedelta(days=1), duration=600, identity='SYNTHETIC-LEGACY-MIXER'):
    """Old seven-edge controller history shape, with only synthetic identities."""
    claim = {'execution_id':identity, 'auxiliary_device_id':mixer.DEVICE,
        'device_type':'fertilizer_mixer', 'device_id':'100204d497', 'channel':2,
        'purpose':'owner_operator_commissioning', 'state':'claimed',
        'claimed_at':at.isoformat(), 'primary_stop_deadline':(at+timedelta(seconds=duration)).isoformat(),
        'maximum_duration_seconds':duration, 'on_attempts':0, 'off_attempts':0,
        'consumption_key':'SYNTHETIC-LEGACY-CONSUME', 'batch_generation':'SYNTHETIC-BATCH'}
    start = {'state':'ON','device_id':'100204d497','channel':2,'authoritative':True,
        'evidence_id':'a'*64,'retrieved_at':(at+timedelta(seconds=14)).isoformat()}
    stop = {'state':'OFF','device_id':'100204d497','channel':2,'authoritative':True,
        'evidence_id':'b'*64,'retrieved_at':(at+timedelta(seconds=duration+8)).isoformat()}
    active = event('mark_auxiliary_active', {**claim,'state':'Active','on_attempts':1,'start_evidence':start})
    terminal = event('record_auxiliary_completed', {**active,'state':'Completed',
        'completed_at':(at+timedelta(seconds=duration+11)).isoformat(),
        'shutdown_verified':True,'control_completed':True,'shutdown_evidence':stop,
        'control_completion_proof':'authoritative_provider_on_then_off',
        'accounted_mixing_seconds':duration,'physical_outcome':'Unknown'})
    return [event('claim_auxiliary_before_on',claim),event('claim_auxiliary_dispatch',claim),
        event('record_auxiliary_on_outcome',{**claim,'on_attempts':1,'on_outcome':{
            'event':'controller_1_ch2_on','status':'accepted','provider_status':200,'accepted_unambiguous':True}}),
        active,event('claim_auxiliary_off_attempt',{'execution_id':identity,'attempt':1}),
        event('record_auxiliary_off_outcome',{'execution_id':identity,'attempt':1,'outcome':{
            'event':'controller_1_ch2_off','status':'accepted','provider_status':200,'accepted_unambiguous':True}}),terminal]


@pytest.mark.parametrize('prior_day', [False, True])
def test_valid_legacy_provider_closure_resolves_duty_without_command_credit_or_refund(prior_day):
    at = NOW-timedelta(days=1) if prior_day else NOW-timedelta(seconds=700)
    history = legacy_provider_chain(at=at); original = deepcopy(history)
    assert mixer.closed_legacy_provider_session(history, now=NOW) is not None
    result = mixer.project_mixer_sessions(history, now=NOW)
    assert result['session_history_valid']
    assert result['command_accounted_microseconds'] == result['known_residual_microseconds'] == 0
    assert result['session_reserved_microseconds'] == (0 if prior_day else 600_000_000)
    assert result['session_count'] == (0 if prior_day else 1)
    assert result['mixer_session']['kind'] == 'reservation'
    assert result['physical_outcome'] == 'Unknown' and history == original


@pytest.mark.parametrize('defect', ['missing_terminal','missing_dispatch','missing_off','bad_hash',
    'unverified_shutdown','unverified_control','wrong_start_device','wrong_stop_channel',
    'early_off','future_off','ambiguous_on','manual_isolation','changed_deadline'])
def test_legacy_unclosed_or_conflicting_history_remains_blocked(defect):
    history = legacy_provider_chain()
    if defect.startswith('missing_'):
        action = {'missing_terminal':'record_auxiliary_completed','missing_dispatch':'claim_auxiliary_dispatch',
            'missing_off':'record_auxiliary_off_outcome'}[defect]
        history = [row for row in history if row['action'] != action]
    elif defect == 'bad_hash': history[-1]['event_id'] = 'bad'
    else:
        terminal = mixer._body(history[-1])
        if defect == 'unverified_shutdown': terminal['shutdown_verified'] = False
        elif defect == 'unverified_control': terminal['control_completed'] = False
        elif defect == 'wrong_start_device': terminal['start_evidence']['device_id'] = 'wrong'
        elif defect == 'wrong_stop_channel': terminal['shutdown_evidence']['channel'] = 1
        elif defect == 'early_off': terminal['shutdown_evidence']['retrieved_at'] = (NOW-timedelta(days=1,seconds=-20)).isoformat()
        elif defect == 'future_off': terminal['shutdown_evidence']['retrieved_at'] = (NOW+timedelta(seconds=1)).isoformat()
        elif defect == 'manual_isolation': terminal['manual_isolation_active'] = True
        elif defect == 'changed_deadline': terminal['primary_stop_deadline'] = NOW.isoformat()
        elif defect == 'ambiguous_on':
            body = mixer._body(history[2]); body['on_outcome']['accepted_unambiguous'] = False
            history[2] = event('record_auxiliary_on_outcome',body)
        history[-1] = event('record_auxiliary_completed',terminal)
    result = mixer.project_mixer_sessions(history, now=NOW)
    assert result['session_history_valid'] is False
    assert result['mixer_session'] is None
    assert result['command_accounted_microseconds'] == 0


def test_legacy_provider_interval_crossing_midnight_reserves_current_day_without_credit():
    day_start = NOW.astimezone(mixer.ZoneInfo('Africa/Johannesburg')).replace(hour=0,minute=0,second=0,microsecond=0)
    history = legacy_provider_chain(at=day_start-timedelta(seconds=610))
    terminal = mixer._body(history[-1]); terminal['shutdown_evidence']['retrieved_at'] = (day_start+timedelta(seconds=20)).isoformat()
    terminal['completed_at'] = (day_start+timedelta(seconds=21)).isoformat()
    history[-1] = event('record_auxiliary_completed',terminal)
    result = mixer.project_mixer_sessions(history, now=NOW)
    assert result['session_history_valid']
    assert result['session_reserved_microseconds'] == 20_000_000 and result['session_count'] == 1
    assert result['command_accounted_microseconds'] == result['known_residual_microseconds'] == 0


def test_two_early_stops_and_legacy_closure_keep_fractional_remainder_without_retry_or_premix_hold():
    history = legacy_provider_chain()
    history += chain(at=NOW-timedelta(seconds=1400),elapsed_us=98_377_119,identity='SYNTHETIC-FIRST')
    history += chain(at=NOW-timedelta(seconds=700),elapsed_us=82_823_079,identity='SYNTHETIC-SECOND')
    account = mixer.project_mixer_sessions(history,now=NOW)
    assert account['command_accounted_microseconds'] == 181_200_198
    assert account['session_reserved_microseconds'] == 1_200_000_000
    at = NOW
    for index, seconds in enumerate((501,517,600)):
        session = mixer.project_mixer_sessions(history,now=at)['mixer_session']
        assert session['maximum_duration_seconds'] == seconds
        child = chain(at=at,duration=seconds,session=session,identity='SYNTHETIC-CHILD-'+str(index))
        terminal = mixer._body(child[-1]); terminal.update(reason='primary_deadline_reached',
            command_program_completed=True,command_accounted_mixing_seconds=seconds)
        child[-1] = event('record_auxiliary_completed',terminal)
        history += child; at += timedelta(seconds=seconds+1)
    result = mixer.project_mixer_sessions(history,now=at)
    assert result['session_count'] == 5 and result['session_reserved_microseconds'] == 1_800_000_000
    assert result['command_accounted_microseconds'] == 1_799_200_198
    assert result['command_shortfall_microseconds'] == result['known_residual_microseconds'] == 799_802
    assert result['mixer_session'] is None
    assert mixer.project_mixer_sessions(history,now=at+timedelta(minutes=10))['mixer_session'] is None
    batch = {'batch_generation':'SYNTHETIC-BATCH','mixed_after':(NOW-timedelta(hours=1)).isoformat()}
    account = mixing_daily_accounting(history,now=at,batch=batch)
    assert account['premix_command_accepted'] is True
    assert account['command_accounted_microseconds'] < 1_800_000_000
    from tests.test_rootline_command_mode import start
    from modules.telemetry.rootline_water_energy_plan import _active_irrigation_context
    _, _, parent_store, transport, clock = start(at=at-timedelta(seconds=600))
    clock[0] = at
    injection = _active_irrigation_context(parent_store.active, [], True, 'SYNTHETIC-BATCH', now=at)
    injection.update(premix_command_accepted=account['premix_command_accepted'],
        fertilizer_history_complete_through=at.isoformat())
    injection['zone_output_evidence'] = transport.read_output_state(device_id='100204e9bc',channel=1)
    with ca.scope(ENV), timed_control_scope(ENV):
        eligibility = build_auxiliary_eligibility(task={'auxiliary_device_id':'FERTILIZER-INJECTION-CH1'},
            safety=transport.read_safety_configuration(device_id='100204d497',channel=1),context=injection,
            flags={'ROOTLINE_FERTILIZER_INJECTION_ENABLED':True},now=at)
    assert eligibility['eligible'], eligibility



def recovered_command_chain(*, at=NOW-timedelta(seconds=700), attempts=2):
    rows = chain(at=at,elapsed_us=98_377_119,identity='SYNTHETIC-RETRY-MIXER')
    claim = rows[0]; terminal = mixer._body(rows[-1]); receipt = deepcopy(terminal['command_off_receipt'])
    receipt['idempotency_key'] = claim['execution_id']+':OFF:'+str(attempts)
    receipt['receipt_sha256'] = ca.digest({k:v for k,v in receipt.items() if k != 'receipt_sha256'})
    terminal['command_off_receipt'] = receipt
    retried = rows[:4]
    for number in range(1,attempts+1):
        retried.append(event('claim_auxiliary_off_attempt',{'execution_id':claim['execution_id'],'attempt':number}))
        outcome = receipt if number == attempts else {'accepted_unambiguous':False,
            'provider_command_attempted':True,'status':'synthetic_timeout_unknown'}
        retried.append(event('record_auxiliary_off_outcome',{'execution_id':claim['execution_id'],
            'attempt':number,'outcome':outcome}))
    return retried+[event('record_auxiliary_completed',terminal)]


@pytest.mark.parametrize('attempts', [2,3])
@pytest.mark.parametrize('prior_day', [False,True])
def test_valid_off_retry_closes_duty_without_refund_or_elapsed_credit(attempts,prior_day):
    at = NOW-timedelta(days=1) if prior_day else NOW-timedelta(seconds=700)
    history = recovered_command_chain(at=at,attempts=attempts)
    assert mixer.closed_command_session(history,now=NOW) is None
    assert mixer.closed_recovered_command_session(history,now=NOW) is not None
    result = mixer.project_mixer_sessions(history,now=NOW)
    assert result['session_history_valid']
    assert result['command_accounted_microseconds'] == result['known_residual_microseconds'] == 0
    assert result['session_reserved_microseconds'] == (0 if prior_day else 600_000_000)
    assert result['mixer_session']['kind'] == 'reservation'


@pytest.mark.parametrize('defect', ['missing_barrier','missing_result','duplicate_result','duplicate_barrier',
    'out_of_order','wrong_identity','bad_hash','wrong_attempt','final_unknown','earlier_accepted','bad_final_receipt','earlier_device','earlier_channel',
    'earlier_state','earlier_key','earlier_future'])
def test_off_retry_gaps_conflicts_and_unknown_final_never_release_duty(defect):
    rows = recovered_command_chain()
    if defect == 'missing_barrier': del rows[4]
    elif defect == 'missing_result': del rows[5]
    elif defect == 'duplicate_result': rows.insert(6,deepcopy(rows[5]))
    elif defect == 'duplicate_barrier': rows.insert(5,deepcopy(rows[4]))
    elif defect == 'out_of_order': rows[4],rows[5] = rows[5],rows[4]
    elif defect == 'bad_hash': rows[5]['event_id'] = 'bad'
    else:
        index = 5 if defect in {'wrong_identity','wrong_attempt','earlier_accepted'} or defect.startswith('earlier_') else 7
        action = rows[index]['action']; body = mixer._body(rows[index])
        if defect == 'wrong_identity': body['execution_id'] = 'OTHER-EXECUTION'
        elif defect == 'wrong_attempt': body['attempt'] = 3
        elif defect == 'earlier_accepted': body['outcome']['accepted_unambiguous'] = True
        elif defect == 'earlier_device': body['outcome']['device_id'] = 'other'
        elif defect == 'earlier_channel': body['outcome']['channel'] = 1
        elif defect == 'earlier_state': body['outcome']['requested_state'] = 'ON'
        elif defect == 'earlier_key': body['outcome']['idempotency_key'] = 'other:OFF:1'
        elif defect == 'earlier_future': body['outcome']['command_attempted_at'] = (NOW+timedelta(seconds=1)).isoformat()
        elif defect == 'final_unknown': body['outcome']['accepted_unambiguous'] = False
        elif defect == 'bad_final_receipt': body['outcome']['receipt_sha256'] = 'bad'
        rows[index] = event(action,body)
    assert mixer.closed_recovered_command_session(rows,now=NOW) is None
    assert mixer.project_mixer_sessions(rows,now=NOW)['mixer_session'] is None
