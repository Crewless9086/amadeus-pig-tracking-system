"""The owned switch controls AC backup, never the independent solar pump."""
from copy import deepcopy
from datetime import timedelta
import pytest
from tests.test_rootline_continuous_borehole import NOW, provider, eligibility, Transport
from tests.test_rootline_borehole_commissioning import BoreholeStore
from modules.telemetry.rootline_energy_policy import managed_energy_decision
from modules.telemetry.rootline_borehole_commissioning import build_borehole_runtime_eligibility, advance_borehole_execution
from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
from modules.telemetry.rootline_water_energy_plan import build_water_energy_plan
from modules.oom_sakkie.rootline_transition_notifications import transition, compose_transition_notice
from modules.oom_sakkie.owner_response_composer import compose_rootline


def power(**changes):
    return {'observed_at': NOW.isoformat(), 'solar_power_w': 4800, 'battery_soc_pct': 73,
        'battery_power_w': -1800, 'battery_state': 'charging', 'grid_power_w': 0,
        'load_power_w': 1500, **changes}


class Store(BoreholeStore):
    def __init__(self):
        super().__init__(); self.edges = []
    def __call__(self, action, body):
        if action == 'load_active_auxiliaries': return []
        if action == 'adopt_borehole_observed_on':
            self.active = deepcopy(body); self.events.append((action, deepcopy(body)))
            return {'success': True, 'created': True, 'execution': self.active}
        if action in {'dispatch_borehole_on_edge', 'dispatch_borehole_off_edge'}:
            self.edges.append(action)
        return super().__call__(action, body)


def cycle(store, transport, packet, **kwargs):
    return run_rootline_managed_device_cycle(evidence={}, transport=transport, store=store,
        environ={}, now=NOW, clock=lambda: NOW, allow_new_starts=False,
        energy_reader=lambda: managed_energy_decision(packet, now=NOW),
        borehole_safety_reader=lambda: True,
        borehole_conditions_reader=lambda: {'success': True, 'stop_required': False,
            'reason': 'conditions_allow_start', 'event_id': 'ROOTLINE-EXEC-'+'9'*32,
            'assessed_at': NOW.isoformat()}, **kwargs)


def active(store, transport, *, legacy=False):
    art = eligibility()
    if legacy:
        art.update(contract_version='rootline_borehole_runtime_eligibility.v2', stop_mode='timed',
            requested_seconds=3600, native_fail_stop_seconds=14400)
    store.active = {**art, 'state': 'Active', 'on_attempts': 1,
        'claimed_at': (NOW-timedelta(minutes=10)).isoformat(),
        'primary_stop_deadline': (NOW+timedelta(minutes=50)).isoformat() if legacy else None,
        'native_fail_stop_deadline': (NOW+timedelta(hours=3)).isoformat() if legacy else None,
        'provider_start_evidence': provider('ON', NOW-timedelta(minutes=10))}
    transport.state = 'ON'
    return deepcopy(store.active)


@pytest.mark.parametrize('legacy', [False, True])
@pytest.mark.parametrize('solar_only', [False, True])
def test_full_supervision_stops_only_owned_ac_and_replay_never_sends_on(legacy, solar_only):
    store=Store(); transport=Transport(); original=active(store, transport, legacy=legacy)
    packet={'observed_at': NOW.isoformat(), 'solar_power_w': 4800} if solar_only else power()
    cycle(store, transport, packet)
    terminal=next(row for action,row in store.events if action=='record_borehole_completed')
    assert [row['state'] for row in transport.commands] == ['OFF']
    assert store.edges == ['dispatch_borehole_off_edge']
    assert terminal['execution_id'] == original['execution_id']
    assert terminal['primary_stop_deadline'] == original['primary_stop_deadline']
    assert terminal['shutdown_verified'] and terminal['provider_final_off_evidence']['state']=='OFF'
    assert terminal['stop_reason']=='sunshine_ac_backup_not_required'
    if not legacy:
        context=terminal['stop_trigger']['energy_context']
        assert context['controlled_supply']=='borehole_ac_backup' and context['pump_operation']=='Unknown'
        assert context['solar_power_w']==4800 and context['ac_backup_off_for_sunshine']
    assert 'physical_flow_verified' not in terminal
    cycle(store, transport, packet)
    assert [row['state'] for row in transport.commands] == ['OFF']


@pytest.mark.parametrize('solar', [1500, 4800])
def test_sunshine_blocks_new_ac_start_but_allows_ownership_of_observed_on(solar):
    decision=managed_energy_decision(power(solar_power_w=solar),now=NOW)
    for observed in ['OFF','ON']:
        art=build_borehole_runtime_eligibility(need={'eligible':True},baseline={
            'current':True,'stop_mode':'conditions','registry_generation':3,'baseline_sha256':'b'*64,
            'maximum_routine_runtime_seconds':0,'native_fail_stop_seconds':0},
            authority={'inside_standing_authority':True},provider=provider(observed),interlocks={},
            energy={**decision['borehole_energy_context'],'eligible':decision['continuous_borehole_eligible']},
            requested_seconds=None,now=NOW,conditions={'start_eligible':True,'stop_required':False,
                'event_id':'ROOTLINE-EXEC-'+'C'*32})
        store=Store(); transport=Transport(); transport.state=observed
        if observed=='OFF':
            assert not art['eligible'] and not art['gates']['energy']
            advance_borehole_execution(eligibility=art,store=store,transport=transport,now=NOW,clock=lambda:NOW)
            assert transport.commands==[]
        else:
            assert art['eligible'] and art['operation']=='adopt_observed_on' and not art['start_gates']['energy']
            advance_borehole_execution(eligibility=art,store=store,transport=transport,now=NOW,clock=lambda:NOW)
            cycle(store,transport,power(solar_power_w=solar))
            assert [row['state'] for row in transport.commands]==['OFF']


def test_post_callback_supervision_rechecks_sunshine_in_same_pass():
    store=Store(); transport=Transport(); active(store,transport)
    packet=power(solar_power_w=1499)
    def after_safety(_):
        assert transport.commands==[]
        packet['solar_power_w']=4800
    cycle(store,transport,packet,after_safety=after_safety)
    assert [row['state'] for row in transport.commands]==['OFF']


@pytest.mark.parametrize('changes', [{'observed_at':(NOW-timedelta(minutes=16)).isoformat()},
    {'conflicting':True}, {'observed_at':(NOW+timedelta(seconds=1)).isoformat()}])
def test_unproven_sunshine_neither_starts_nor_manufactures_owned_shutdown(changes):
    packet=power(**changes); decision=managed_energy_decision(packet,now=NOW)
    assert not decision['continuous_borehole_fresh'] and not decision['continuous_borehole_eligible']
    store=Store();transport=Transport();active(store,transport)
    cycle(store,transport,packet)
    assert transport.commands==[] and store.active is not None


@pytest.mark.parametrize('soc,grid,battery,eligible',[(30,0,-300,False),(30,20,300,True),
    (31,0,-300,True),(31,0,300,True),(29,0,300,False)])
def test_below_sunshine_threshold_retains_existing_backup_floor(soc,grid,battery,eligible):
    result=managed_energy_decision(power(solar_power_w=1499,battery_soc_pct=soc,
        grid_power_w=grid,battery_power_w=battery),now=NOW)
    assert result['continuous_borehole_eligible'] is eligible
    assert result['borehole_eligible'] is eligible
    assert not result['borehole_energy_context']['ac_backup_off_for_sunshine']


def test_sunshine_only_does_not_make_other_device_energy_evidence_fresh():
    result=managed_energy_decision({'observed_at':NOW.isoformat(),'solar_power_w':4800},now=NOW)
    assert result['continuous_borehole_fresh'] and result['borehole_fresh']
    assert not result['fresh'] and not result['mixing_eligible']
    assert result['eskom_requested_state']=='UNCHANGED'


@pytest.mark.parametrize('language,label', [('en','Borehole AC backup'),('af','Boorgat se AC-rugsteun')])
def test_visible_notice_and_plan_distinguish_ac_from_unknown_pumping(language,label):
    store=Store();transport=Transport();active(store,transport);cycle(store,transport,power())
    row=next(body for action,body in store.events if action=='record_borehole_completed')
    state,event=transition({**row,'event_id':'OFFLINE-AC-EDGE'})
    notice=compose_transition_notice(state,event,language=language)
    assert label in notice and ('OFF' if language=='en' else 'AF') in notice
    assert ('does not verify whether the pump' if language=='en' else 'nie hierdeur bevestig nie') in notice
    plan=build_water_energy_plan({'power':power()},NOW.date().isoformat(),now=NOW)
    task=next(x for x in plan['candidate_tasks'] if x['task_id']=='borehole')
    assert task['recommendation']=='Do Not Run' and 'AC backup OFF' in task['reason']
    response=compose_rootline({'success':True,'recommendations':[task]},language=language)
    assert label in response


@pytest.mark.parametrize('urgent', [False, True])
@pytest.mark.parametrize('elapsed', [False, True])
def test_forecast_cannot_override_sunshine_ac_off(urgent, elapsed):
    from tests.test_rootline_specialist_result import evidence, NOW as report_now
    from modules.telemetry.rootline_specialist_result import build_rootline_specialist_result
    facts=evidence()
    facts['power'].update(solar_power_w=4800,observed_at=report_now.isoformat())
    facts['forecast'].update(observed_at=(report_now-timedelta(hours=2 if elapsed else 0)).isoformat(),
        days=[{'rain_sum_mm':20,'rain_probability_max_pct':100}])
    facts['water_demand']['status']='urgent' if urgent else 'needed'
    result=build_rootline_specialist_result(facts,report_now.date().isoformat(),now=report_now)
    borehole=next(row for row in result['recommendations'] if row['subject']=='borehole')
    assert borehole['status']=='Do Not Run' and 'AC backup OFF' in borehole['reason']


@pytest.mark.parametrize('urgent', [False, True])
def test_expired_forecast_hold_followup_never_releases_ac_during_sunshine(urgent):
    from tests.test_rootline_specialist_result import evidence, NOW as report_now
    from modules.telemetry.rootline_specialist_result import build_rootline_specialist_result, reconsider_rootline_forecast_hold
    facts=evidence()
    facts['power']['solar_power_w']=1499
    facts['forecast'].update(observed_at=report_now.isoformat(),
        days=[{'rain_sum_mm':20,'rain_probability_max_pct':100}])
    previous=build_rootline_specialist_result(facts,report_now.date().isoformat(),now=report_now)
    assert next(row for row in previous['recommendations'] if row['subject']=='borehole')['status']=='Hold'
    deadline=previous['next_reassessment']['at']
    later=report_now+timedelta(minutes=65)
    facts['power'].update(solar_power_w=4800,observed_at=later.isoformat())
    facts['weather'].update(observed_at=later.isoformat(),rain_rate_mm_h=0)
    facts['forecast']['observed_at']=later.isoformat()
    facts['water_demand']['status']='urgent' if urgent else 'needed'
    result=reconsider_rootline_forecast_hold(previous,facts,now=later)
    borehole=next(row for row in result['recommendations'] if row['subject']=='borehole')
    assert borehole['status']=='Do Not Run' and 'AC backup OFF' in borehole['reason']
    assert result['follow_up']['prior_forecast_hold']
    assert result['follow_up']['forecast_hold_deadline']==deadline
    assert result['follow_up']['outcome']=='reconsidered_no_observed_rain'
