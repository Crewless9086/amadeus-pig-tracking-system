from datetime import datetime, timedelta, timezone
from copy import deepcopy
import pytest
from modules.telemetry.rootline_borehole_conditions import (
    assess_weather, advance_conditions, continuous_device_profile, continuous_policy_valid, digest)
from modules.telemetry.rootline_borehole_commissioning import build_borehole_runtime_eligibility, advance_borehole_execution
from modules.telemetry.rootline_irrigation_execution_store import _valid_borehole_eligibility
from modules.telemetry.rootline_energy_policy import managed_energy_decision
from modules.telemetry.weather_service import DEFAULT_WEATHER_SOURCE_ID
from tests.test_rootline_borehole_commissioning import BoreholeStore, BoreholeTransport
NOW=datetime(2026,11,16,12,tzinfo=timezone.utc)

def provider(state='OFF', now=NOW):
    return {'authoritative':True,'state':state,'device_id':'1002851416','channel':1,
        'evidence_id':'a'*64,'retrieved_at':now.isoformat(),
        'borehole_configuration':{'online':True,'native_auto_off_enabled':False}}

def eligibility(now=NOW):
    return build_borehole_runtime_eligibility(need={'eligible':True},baseline={
        'current':True,'stop_mode':'conditions','registry_generation':3,'baseline_sha256':'b'*64,
        'maximum_routine_runtime_seconds':0,'native_fail_stop_seconds':0},
        authority={'inside_standing_authority':True},provider=provider(now=now),interlocks={},
        energy={'eligible':True},requested_seconds=None,now=now,
        conditions={'start_eligible':True,'event_id':'ROOTLINE-EXEC-'+'C'*32})

class Transport(BoreholeTransport):
    now=NOW
    def read_output_state(self,**kwargs): return provider(self.state,self.now)


def snapshot(now=NOW,rate=0,missing=None):
    readings=[{'observed_at':(now-timedelta(minutes=60-5*i)).isoformat(),'rain_rate_mm_h':0}
              for i in range(13) if (i not in missing if isinstance(missing, tuple) else i != missing)]
    readings[-1]['rain_rate_mm_h']=rate
    return {'success':True,'snapshot_cutoff':now.isoformat(),'weather_current':{
        'success':True,'source':{'source_id':DEFAULT_WEATHER_SOURCE_ID,'last_reading_at':now.isoformat(),
        'stale_after_minutes':30},'current':{'rain_rate_mm_h':rate}},
        'rain_release':{'source_id':DEFAULT_WEATHER_SOURCE_ID,'source_healthy':True,'conflicting':False,
        'station_readings':readings}}


def test_v5_eligibility_is_bound_and_has_no_duration():
    art=eligibility()
    assert art['eligible'] and _valid_borehole_eligibility(art)
    assert art['requested_seconds'] is None and art['stop_mode']=='conditions'
    assert not _valid_borehole_eligibility({**art,'requested_seconds':36000})
    assert not _valid_borehole_eligibility({**art,'stop_mode':'scheduled'})
    assert not _valid_borehole_eligibility({**art,'condition_evidence':{'start_eligible':True}})


@pytest.mark.parametrize('hours',[4,10,24,73])
def test_same_owned_run_crosses_old_caps_and_restart(hours):
    store=BoreholeStore();transport=Transport();art=eligibility()
    started=advance_borehole_execution(eligibility=art,store=store,transport=transport,now=NOW,clock=lambda:NOW)
    assert started['status']=='borehole_started'
    assert store.active['primary_stop_deadline'] is None and store.active['native_fail_stop_deadline'] is None
    when=NOW+timedelta(hours=hours); transport.now=when
    recovered=advance_borehole_execution(eligibility={},store=store,transport=transport,now=when,clock=lambda:when)
    assert recovered['status']=='borehole_active'
    assert store.active['execution_id']==art['execution_id']
    assert [x['state'] for x in transport.commands]==['ON']


def test_unknown_initial_on_is_not_retried_or_stopped_due_to_missing_deadline():
    store=BoreholeStore();transport=Transport(on_readback='Unknown');art=eligibility()
    first=advance_borehole_execution(eligibility=art,store=store,transport=transport,now=NOW,clock=lambda:NOW)
    assert first['status']=='borehole_start_observation_pending'
    when=NOW+timedelta(hours=11);transport.now=when
    again=advance_borehole_execution(eligibility={},store=store,transport=transport,now=when,clock=lambda:when)
    assert again['status']=='borehole_start_observation_pending'
    assert [x['state'] for x in transport.commands]==['ON']
    transport.state='ON'
    assert advance_borehole_execution(eligibility={},store=store,transport=transport,now=when,clock=lambda:when)['status']=='borehole_start_observed'


def test_condition_stop_uses_existing_off_and_records_reason():
    store=BoreholeStore();transport=Transport();art=eligibility()
    advance_borehole_execution(eligibility=art,store=store,transport=transport,now=NOW,clock=lambda:NOW)
    end=NOW+timedelta(minutes=4);transport.now=end
    result=advance_borehole_execution(eligibility={},store=store,transport=transport,now=end,clock=lambda:end,
        stop_for_energy=True,stop_reason='observed_rain')
    assert result['status']=='borehole_completed'
    assert result['execution']['stop_reason']=='observed_rain'
    assert [x['state'] for x in transport.commands]==['ON','OFF']


def test_forecast_once_survives_restarts_and_evidence_changes():
    weather=assess_weather(snapshot(),now=NOW)
    forecast={'observed_at':NOW.isoformat(),'days':[{'rain_sum_mm':20}]}
    state=advance_conditions({},weather=weather,forecast=forecast,active=None,now=NOW)
    assert state['reason']=='forecast_start_deferred'
    for minutes in (15,45,60,120,900):
        now=NOW+timedelta(minutes=minutes)
        state=advance_conditions(deepcopy(state),weather=assess_weather(snapshot(now),now=now),
            forecast={**forecast,'observed_at':now.isoformat()},active=None,now=now)
        assert state['forecast_defer_until']==(NOW+timedelta(hours=1)).isoformat()
        assert state['start_eligible'] is (minutes>=60)


def test_rain_hold_survives_missing_and_requires_full_hour_coverage():
    rainy=assess_weather(snapshot(rate=.1),now=NOW)
    state=advance_conditions({},weather=rainy,forecast=None,active={'execution_id':'owned'},now=NOW)
    assert state['stop_required'] and state['rain_hold']
    next_hour=NOW+timedelta(hours=1)
    missing=assess_weather(snapshot(next_hour,missing=(4,5)),now=next_hour)
    assert missing['fresh'] and not missing['dry_hour']
    state=advance_conditions(state,weather=missing,forecast=None,active=None,now=next_hour)
    assert not state['start_eligible'] and state['rain_hold']
    two_hours=NOW+timedelta(hours=2)
    dry=assess_weather(snapshot(two_hours),now=two_hours)
    state=advance_conditions(state,weather=dry,forecast=None,active=None,now=two_hours)
    assert state['start_eligible'] and not state['rain_hold']


def test_stale_unknown_is_never_dry_or_a_new_stop_without_prior_rain():
    stale=assess_weather(snapshot(),now=NOW+timedelta(hours=1))
    assert not stale['fresh'] and not stale['dry_hour']
    state=advance_conditions({},weather=stale,forecast=None,active={'execution_id':'owned'},now=NOW+timedelta(hours=1))
    assert not state['stop_required'] and not state['start_eligible']


@pytest.mark.parametrize('solar,soc,grid,eligible',[(1500,20,0,True),(1499,30,0,False),(1499,30,20,True),(1499,31,0,True)])
def test_sunshine_proxy_and_backup_floor(solar,soc,grid,eligible):
    power={'observed_at':NOW.isoformat(),'solar_power_w':solar,'battery_soc_pct':soc,
        'grid_power_w':grid,'battery_power_w':-200,'load_power_w':10000}
    result=managed_energy_decision(power,now=NOW)
    assert result['continuous_borehole_eligible'] is eligible
    assert result['borehole_energy_metered'] is False


def test_sunshine_does_not_require_household_load_or_battery_sensor():
    result=managed_energy_decision({'observed_at':NOW.isoformat(),'solar_power_w':1500},now=NOW)
    assert result['continuous_borehole_fresh'] and result['continuous_borehole_eligible']
    assert not result['mixing_eligible'] and result['eskom_requested_state']=='UNCHANGED'


def test_manual_off_is_attributable_interlock_not_observed_switch_off():
    from modules.telemetry.rootline_water_energy_plan import _project_borehole_interlocks
    rows=[{'manual_off_active':True,'observed_at':NOW.isoformat(),'provider_message_id':'owner-message'}]
    assert _project_borehole_interlocks(rows,NOW+timedelta(days=1))['manual_off_active'] is True
    rows.append({'observed_at':(NOW+timedelta(hours=1)).isoformat(),'dry_run_safe':True})
    assert _project_borehole_interlocks(rows,NOW+timedelta(days=1))['manual_off_active'] is True
    rows.append({'manual_off_active':False,'observed_at':(NOW+timedelta(hours=2)).isoformat(),'provider_message_id':'owner-resume'})
    assert _project_borehole_interlocks(rows,NOW+timedelta(days=1))['manual_off_active'] is False


def test_optional_continuous_reads_charge_global_capacity_and_preserve_shutdown_reserve():
    from tests.test_rootline_ewelink_request_budget import MemoryBudget, snapshot as budget_snapshot
    from modules.telemetry import rootline_ewelink_request_budget as budget
    client=MemoryBudget();client.backend.now=NOW
    art=eligibility();art.update(claimed_at=NOW.isoformat(),primary_stop_deadline=None,
        provider_start_evidence={'authoritative':True,'state':'ON','retrieved_at':NOW.isoformat()},
        device_type='borehole_pump_power')
    permit=client.reserve_for_on(execution_id=art['execution_id'],device_id='1002851416',channel=1,
        device_type='borehole_pump_power',region='eu')
    client.begin_on(execution_id=art['execution_id'],permit=permit,device_id='1002851416',channel=1,
        claimed_at=NOW.isoformat(),continuous=True)
    initial=client.backend.state['reserves'][art['execution_id']]['remaining']
    for seconds in (1801,36001,90001):
        client.backend.now=NOW+timedelta(seconds=seconds)
        with budget.execution_duty(art),budget.routine_execution_observation(art):
            assert len(budget_snapshot(client,device='1002851416'))==3
        assert client.backend.state['reserves'][art['execution_id']]['remaining']==initial
        assert client.backend.state['reserves'][art['execution_id']]['phase']=='on_attempt'
    assert sum(e['units'] for e in client.backend.events)==9


def test_continuous_admission_expiry_is_still_thirty_seconds():
    from tests.test_rootline_ewelink_request_budget import MemoryBudget
    from modules.telemetry.rootline_ewelink_request_budget import RequestBudgetUnavailable
    client=MemoryBudget();client.backend.now=NOW
    permit=client.reserve_for_on(execution_id='candidate',device_id='1002851416',channel=1,
        device_type='borehole_pump_power',region='eu')
    client.backend.advance(31)
    with pytest.raises(RequestBudgetUnavailable):
        client.begin_on(execution_id='candidate',permit=permit,device_id='1002851416',channel=1,
            claimed_at=NOW.isoformat(),continuous=True)


def test_pending_conditional_off_survives_projection_after_rain_clears():
    from modules.telemetry.rootline_irrigation_execution_store import _active_borehole
    active={**eligibility(),'action':'mark_borehole_active','state':'Active','claimed_at':NOW.isoformat(),
        'primary_stop_deadline':None,'native_fail_stop_deadline':None,
        'provider_start_evidence':{'authoritative':True,'state':'ON'}}
    off={**active,'action':'claim_borehole_off_attempt','attempt':1,'stop_reason':'observed_rain'}
    projected=_active_borehole([off,active])
    assert projected['stop_requested'] and projected['stop_reason']=='observed_rain'


def test_real_locked_claim_branch_requires_current_condition_and_no_deadline(monkeypatch):
    from contextlib import contextmanager
    from modules.telemetry.rootline_irrigation_execution_store import _claim_borehole_material_load
    art=eligibility(); current={**art['condition_evidence'],'assessed_at':NOW.isoformat(),'stop_required':False}
    body={**art,'claimed_at':NOW.isoformat(),'state':'claimed','primary_stop_deadline':None,
        'native_fail_stop_deadline':None,'on_attempts':0,'off_attempts':0,
        'claim_provider_evidence':{**provider(),'execution_id':art['execution_id']}}
    class Cursor:
        rowcount=1
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):self.sql,self.params=sql,params
        def fetchone(self):
            if 'clock_timestamp' in self.sql:return (NOW,)
            if 'record_borehole_eligibility' in self.sql:return (art,)
            if self.params and 'record_borehole_condition_state' in self.params:return (current,)
            raise AssertionError(self.sql)
        def fetchall(self):return []
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return Cursor()
    monkeypatch.setattr('modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres',lambda **kw:Connection())
    assert _claim_borehole_material_load(body)['created']
    current['stop_required']=True
    assert not _claim_borehole_material_load(body)['created']
    current['stop_required']=False
    assert not _claim_borehole_material_load({**body,'primary_stop_deadline':(NOW+timedelta(hours=10)).isoformat()})['created']


def test_current_detected_rain_is_not_hidden_by_a_missing_historical_sample():
    data=snapshot(rate=.1)
    data['rain_release']['station_readings'][3]['rain_rate_mm_h']=None
    data['rain_release']['conflicting']=True
    result=assess_weather(data,now=NOW)
    assert result['rain_detected'] and not result['dry_hour']


def test_plain_off_completion_keeps_cause_unknown_and_does_not_create_manual_hold():
    store=BoreholeStore();transport=Transport();art=eligibility()
    advance_borehole_execution(eligibility=art,store=store,transport=transport,now=NOW,clock=lambda:NOW)
    transport.state='OFF';when=NOW+timedelta(hours=12);transport.now=when
    result=advance_borehole_execution(eligibility={},store=store,transport=transport,now=when,clock=lambda:when)
    assert result['status']=='borehole_completed'
    assert result['stop_reason']=='provider_observed_off_cause_unknown'
    assert [x['state'] for x in transport.commands]==['ON']
    assert result['water_delivery']=='Unmeasured'


def test_unattributed_manual_off_field_does_not_invent_an_owner_instruction():
    from modules.telemetry.rootline_water_energy_plan import _project_borehole_interlocks
    assert _project_borehole_interlocks([{'manual_off_active':True,'observed_at':NOW.isoformat()}],NOW) is None


def test_continuous_profile_alone_never_grants_standing_authority(monkeypatch):
    from modules.telemetry.rootline_borehole_commissioning import load_registered_borehole_baseline
    record={'provider':'ewelink','provider_account_binding':'ewelink_owner_account','device_id':'1002851416',
        'channel':1,'device_type':'pump','adapter_profile':'ewelink_borehole_conditions_v1','stop_mode':'conditions',
        'maximum_runtime_seconds':0,'native_fail_stop_seconds':0,'standing_authority':False,
        'commissioning_stage':'registered','safe_state':'OFF'}
    assert continuous_device_profile(record)
    monkeypatch.setattr('modules.telemetry.rootline_borehole_commissioning.load_device_record',lambda *a,**kw:{'device_record':record})
    assert load_registered_borehole_baseline(connect_factory=lambda:None) is None


def test_managed_energy_stop_reports_energy_reason_when_weather_allows_start():
    from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
    class ManagedStore(BoreholeStore):
        def __call__(self,action,body):
            if action=='load_active_auxiliaries':return []
            return super().__call__(action,body)
    store=ManagedStore();transport=Transport();art=eligibility()
    advance_borehole_execution(eligibility=art,store=store,transport=transport,now=NOW,clock=lambda:NOW)
    when=NOW+timedelta(minutes=3);transport.now=when
    run_rootline_managed_device_cycle(evidence={},transport=transport,store=store,environ={},
        allow_new_starts=False,now=when,clock=lambda:when,
        energy_reader=lambda:{'borehole_fresh':True,'borehole_eligible':False,'borehole_reason':'battery_low_without_verified_grid_supply'},
        borehole_safety_reader=lambda:True,
        borehole_conditions_reader=lambda:{'success':True,'stop_required':False,'reason':'conditions_allow_start'})
    terminal=next(body for action,body in store.events if action=='record_borehole_completed')
    assert terminal['stop_reason']=='battery_low_without_verified_grid_supply'


def test_real_station_jitter_spanning_hour_passes_but_601_second_gap_is_unknown():
    # Production-shaped 2026-11-16 station cadence includes a371-second interval.
    offsets=[0,290,592,924,1117,1488,1800,2076,2413,2678,3000,3348,3576,3876]
    at=NOW-timedelta(seconds=3876)
    data=snapshot()
    data['rain_release']['station_readings']=[{'observed_at':(at+timedelta(seconds=x)).isoformat(),'rain_rate_mm_h':0} for x in offsets]
    assert assess_weather(data,now=NOW)['dry_hour']
    data['rain_release']['station_readings']=[{'observed_at':(NOW-timedelta(seconds=3601-x)).isoformat(),'rain_rate_mm_h':0}
        for x in [0,600,1200,1800,2400,3000,3601]]
    assert not assess_weather(data,now=NOW)['dry_hour']


def test_first_forecast_evidence_and_observed_outcome_are_preserved():
    forecast={'observed_at':NOW.isoformat(),'days':[{'rain_sum_mm':20}]}
    state=advance_conditions({},weather=assess_weather(snapshot(),now=NOW),forecast=forecast,active=None,now=NOW)
    later=NOW+timedelta(hours=1)
    state=advance_conditions(state,weather=assess_weather(snapshot(later),now=later),
        forecast={'observed_at':later.isoformat(),'days':[{'rain_sum_mm':200}]},active=None,now=later)
    assert state['forecast_evidence']==forecast
    assert state['forecast_outcome']=='no_local_rain_at_reassessment'
    assert state['forecast_defer_until']==later.isoformat()


def test_legacy_energy_keys_stay_unchanged_while_v5_uses_separate_solar_proxy():
    power={'observed_at':NOW.isoformat(),'solar_power_w':1500,'battery_soc_pct':20,
        'grid_power_w':0,'load_power_w':10000,'battery_power_w':1000}
    result=managed_energy_decision(power,now=NOW)
    assert result['borehole_eligible'] is False
    assert result['continuous_borehole_eligible'] is True


def test_direction_materially_controls_integrated_eskom_strategy_without_weakening_floor():
    power={'observed_at':NOW.isoformat(),'solar_power_w':1000,'battery_soc_pct':35,
        'grid_power_w':0,'load_power_w':500}
    charging=managed_energy_decision({**power,'battery_power_w':-300,'battery_state':'charging'},now=NOW)
    discharging=managed_energy_decision({**power,'battery_power_w':300,'battery_state':'discharging'},now=NOW)
    assert charging['continuous_borehole_eligible'] and discharging['continuous_borehole_eligible']
    assert charging['borehole_energy_context']['eskom_requested_state']=='OFF'
    assert discharging['borehole_energy_context']['eskom_requested_state']=='UNCHANGED'
    assert charging['borehole_energy_context']['backup_strategy']=='battery_charging_above_floor'
    assert discharging['borehole_energy_context']['backup_strategy']=='battery_discharging_above_floor'
    floor=managed_energy_decision({**power,'battery_soc_pct':30,'battery_power_w':-300,'battery_state':'charging'},now=NOW)
    assert not floor['continuous_borehole_eligible'] and floor['eskom_requested_state']=='ON'


def instruction_store():
    events={}
    def store(action,identity,payload):
        if action=='load':return [row for row in events.values() if row.get('mission_id')==identity]
        if identity in events:return {'success':True,'created':False}
        events[identity]=deepcopy(payload)
        return {'success':True,'created':True}
    return store,events


def test_authenticated_off_replay_resume_feed_real_safety_reader_and_owned_off(monkeypatch):
    from modules.oom_sakkie.operational_specialist_intake import handle_operational_specialist_message
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    from modules.telemetry.rootline_water_energy_plan import read_current_borehole_faults
    from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
    store,events=instruction_store();authority=issue_gateway_owner_authority('42','42')
    message={'text':'Turn the borehole off','telegram_user_id':'42','telegram_chat_id':'42',
        'provider_message_id':'100','provider_timestamp':NOW.isoformat()}
    result,status=handle_operational_specialist_message(message,authority,now=NOW,operation_store=store,
        pending_specialist_loader=lambda _:pytest.fail('explicit OFF must precede stale context'))
    assert status==200 and result['borehole_interlocks']['manual_off_active'] is True
    assert result['hardware_commands']==0 and result['question_count']==0 and len(events)==1
    replay,status=handle_operational_specialist_message(message,authority,now=NOW+timedelta(seconds=30),operation_store=store)
    assert replay['replay_suppressed'] and len(events)==1
    conflict,status=handle_operational_specialist_message({**message,'text':'Resume borehole'},authority,now=NOW,operation_store=store)
    assert status==409 and len(events)==1
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):return self
        def fetchall(self):return [(row['outcome'],) for row in events.values()]
    monkeypatch.setattr('modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres',lambda **kw:Connection())
    when=NOW+timedelta(minutes=3)
    assert read_current_borehole_faults('offline',now=when) is False
    class ManagedStore(BoreholeStore):
        def __call__(self,action,body):
            if action=='load_active_auxiliaries':return []
            return super().__call__(action,body)
    owned=ManagedStore();transport=Transport();art=eligibility()
    advance_borehole_execution(eligibility=art,store=owned,transport=transport,now=NOW,clock=lambda:NOW)
    transport.now=when
    run_rootline_managed_device_cycle(evidence={},transport=transport,store=owned,environ={},
        allow_new_starts=False,now=when,clock=lambda:when,
        borehole_safety_reader=lambda:read_current_borehole_faults('offline',now=when),
        borehole_conditions_reader=lambda:{'success':True,'stop_required':False,'reason':'conditions_allow_start'})
    assert [x['state'] for x in transport.commands]==['ON','OFF']
    assert read_current_borehole_faults('offline',now=NOW+timedelta(days=1)) is False
    resumed,status=handle_operational_specialist_message({**message,'text':'Resume borehole',
        'provider_message_id':'101','provider_timestamp':when.isoformat()},authority,now=when,operation_store=store)
    assert status==200 and resumed['borehole_interlocks']['manual_off_active'] is False
    assert read_current_borehole_faults('offline',now=when) is True
    assert len(events)==2


@pytest.mark.parametrize('change',[{'telegram_user_id':'99'},{'telegram_chat_id':'99'},
    {'provider_timestamp':(NOW-timedelta(minutes=6)).isoformat()}])
def test_borehole_instruction_requires_authenticated_current_owner(change):
    from modules.oom_sakkie.operational_specialist_intake import handle_operational_specialist_message
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    store,events=instruction_store()
    message={'text':'Turn borehole off','telegram_user_id':'42','telegram_chat_id':'42',
        'provider_message_id':'100','provider_timestamp':NOW.isoformat(),**change}
    result,status=handle_operational_specialist_message(message,issue_gateway_owner_authority('42','42'),now=NOW,operation_store=store)
    assert status==409 and not events and result['hardware_commands']==0


def test_observed_off_or_question_is_not_parsed_as_owner_off_instruction():
    from modules.oom_sakkie.operational_specialist_intake import is_exact_borehole_instruction
    for text in ('The borehole is off','Is the borehole off?','I saw the borehole turn off','Do not turn borehole off'):
        assert not is_exact_borehole_instruction({'text':text})
    for text in ('Turn borehole off','Resume borehole','Skakel die boorgat af','Borehole isolated','Borehole isolation cleared'):
        assert is_exact_borehole_instruction({'text':text})


def test_gateway_routes_exact_off_before_stale_manager_question(monkeypatch):
    from modules.oom_sakkie import telegram_gateway as gateway
    monkeypatch.setattr(gateway,'handle_owner_task_input',lambda *a,**kw:pytest.fail('broad owner task consumed OFF'))
    monkeypatch.setattr(gateway,'recover_contextual_specialist_replay',lambda *a,**kw:None)
    monkeypatch.setattr(gateway,'handle_owner_operational_continuation',lambda *a,**kw:pytest.fail('stale continuation consumed OFF'))
    monkeypatch.setattr(gateway,'handle_manager_question_reply',lambda *a,**kw:pytest.fail('stale question consumed OFF'))
    from modules.oom_sakkie.operational_specialist_intake import handle_operational_specialist_message
    store,events=instruction_store()
    monkeypatch.setattr(gateway,'handle_operational_specialist_message',lambda parsed,authority:
        handle_operational_specialist_message(parsed,authority,now=NOW,operation_store=store))
    monkeypatch.setattr(gateway,'deliver_family_result',lambda *a,**kw:{'success':True,'telegram_sends':0,'telegram_edits':0})
    env={'OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED':'1','OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN':'x'*40,'OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS':'42'}
    payload={'message':{'message_id':4001,'date':int(NOW.timestamp()),'text':'Turn borehole off',
        'from':{'id':42},'chat':{'id':42,'type':'private'}}}
    value,status=gateway.handle_telegram_gateway_message(payload,headers={'Authorization':'Bearer '+'x'*40},environ=env)
    assert status==200 and value['message']['status']=='specialist_accepted'
    assert len(events)==1 and value['message']['borehole_interlocks']['manual_off_active'] is True


def test_trigger_survives_off_failure_restart_and_later_verified_terminal():
    from modules.telemetry.rootline_irrigation_execution_store import _active_borehole
    class DurableStore(BoreholeStore):
        def __init__(self):super().__init__();self.slots=[]
        def __call__(self,action,body):
            if action=='load_active_borehole':
                if self.active is None:return None
                return _active_borehole([*reversed(self.slots),{**self.active,'action':'mark_borehole_active'}]) if self.slots else self.active
            if action=='load_borehole_off_attempts':return self.slots
            if action=='dispatch_borehole_off_edge':
                self.slots.append({k:v for k,v in body.items() if k!='dispatch'}|{'action':'claim_borehole_off_attempt'})
                return {**body['dispatch'](),'provider_command_attempted':True}
            return super().__call__(action,body)
    class FailingOff(Transport):
        def set_state(self,**kw):
            if kw['state']=='OFF':
                self.commands.append(kw);return {'accepted_unambiguous':False}
            return super().set_state(**kw)
    store=DurableStore();transport=FailingOff();art=eligibility()
    advance_borehole_execution(eligibility=art,store=store,transport=transport,now=NOW,clock=lambda:NOW)
    trigger={'condition_event_id':'ROOTLINE-EXEC-'+'D'*32,'condition_reason':'observed_rain','assessed_at':NOW.isoformat()}
    failed=advance_borehole_execution(eligibility={},store=store,transport=transport,now=NOW+timedelta(minutes=2),
        clock=lambda:NOW+timedelta(minutes=2),stop_for_energy=True,stop_reason='observed_rain',stop_trigger=trigger)
    assert failed['status']=='borehole_shutdown_unverified'
    assert len(store.slots)==3 and all(row['stop_trigger']==trigger for row in store.slots)
    # New process sees current weather clear, but the prior OFF obligation and
    # its first actual reason remain authoritative until final switchOFF.
    transport.state='OFF';when=NOW+timedelta(hours=2);transport.now=when
    terminal=advance_borehole_execution(eligibility={},store=store,transport=transport,now=when,clock=lambda:when)
    assert terminal['status']=='borehole_completed'
    assert terminal['execution']['stop_trigger']==trigger and terminal['execution']['stop_reason']=='observed_rain'
    assert len(transport.commands)==4


def test_unknown_start_safety_containment_keeps_current_trigger():
    class CapturingStore(BoreholeStore):
        def __init__(self):super().__init__();self.off=[];self.abort=None
        def __call__(self,action,body):
            if action=='dispatch_borehole_off_edge':self.off.append(body)
            if action=='record_borehole_aborted':self.abort=body
            return super().__call__(action,body)
    store=CapturingStore();transport=Transport(on_readback='Unknown')
    advance_borehole_execution(eligibility=eligibility(),store=store,transport=transport,now=NOW,clock=lambda:NOW)
    when=NOW+timedelta(minutes=2);transport.now=when
    trigger={'condition_event_id':'ROOTLINE-EXEC-'+'E'*32,'condition_reason':'observed_rain','assessed_at':when.isoformat()}
    advance_borehole_execution(eligibility={},store=store,transport=transport,now=when,clock=lambda:when,
        stop_for_energy=True,stop_reason='observed_rain',stop_trigger=trigger)
    assert store.off[0]['stop_trigger']==trigger and store.off[0]['stop_reason']=='observed_rain'
    assert store.abort['stop_trigger']==trigger and store.abort['stop_reason']=='observed_rain'


def test_real_off_dispatch_persists_trigger_in_slot_before_send(monkeypatch):
    from modules.telemetry import rootline_irrigation_execution_store as execution
    saved=[];sent=[]
    trigger={'condition_event_id':'ROOTLINE-EXEC-'+'F'*32,'condition_reason':'observed_rain'}
    monkeypatch.setattr(execution,'_guarded_managed_transition',lambda action,body:saved.append((action,body)) or {'created':True})
    monkeypatch.setattr(execution,'_managed_edge_rows',lambda *args:[])
    monkeypatch.setattr(execution,'_insert_managed_event',lambda *args:{'created':True})
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,*args):pass
    class Connection(Cursor):
        def cursor(self):return Cursor()
    monkeypatch.setattr('modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres',lambda **kw:Connection())
    def dispatch():
        assert saved[0][1]['stop_trigger']==trigger
        sent.append(True);return {'accepted_unambiguous':True}
    result=execution._dispatch_borehole_off_edge({'execution_id':'owned','attempt':1,'stop_reason':'observed_rain',
        'stop_trigger':trigger,'dispatch':dispatch})
    assert result['provider_command_attempted'] and sent==[True]


def test_managed_stop_binds_current_energy_context_and_condition_pointer():
    from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
    class ManagedStore(BoreholeStore):
        def __call__(self,action,body):
            if action=='load_active_auxiliaries':return []
            return super().__call__(action,body)
    store=ManagedStore();transport=Transport()
    advance_borehole_execution(eligibility=eligibility(),store=store,transport=transport,now=NOW,clock=lambda:NOW)
    when=NOW+timedelta(minutes=3);transport.now=when
    power={'observed_at':when.isoformat(),'solar_power_w':0,'battery_soc_pct':29,'battery_power_w':400,
        'load_power_w':1500,'grid_power_w':0}
    current=managed_energy_decision(power,now=when)
    run_rootline_managed_device_cycle(evidence={},transport=transport,store=store,environ={},allow_new_starts=False,
        now=when,clock=lambda:when,energy_reader=lambda:current,borehole_safety_reader=lambda:True,
        borehole_conditions_reader=lambda:{'success':True,'stop_required':False,'reason':'conditions_allow_start',
            'event_id':'ROOTLINE-EXEC-'+'9'*32,'assessed_at':when.isoformat()})
    terminal=next(body for action,body in store.events if action=='record_borehole_completed')
    assert terminal['stop_trigger']['energy_stop'] is True
    assert terminal['stop_trigger']['energy_context']['battery_soc_pct']==29
    assert terminal['stop_trigger']['condition_event_id']=='ROOTLINE-EXEC-'+'9'*32


@pytest.mark.parametrize('text',['Turn borehole off','Resume borehole','Borehole isolation cleared'])
def test_sealed_nonowner_read_authority_cannot_set_or_clear_owner_hold(text):
    from modules.oom_sakkie.operational_specialist_intake import handle_operational_specialist_message
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    store,events=instruction_store()
    authority=issue_gateway_owner_authority('42','42',principal_role='farm_manager',capabilities=('rootline_read_only',))
    message={'text':text,'telegram_user_id':'42','telegram_chat_id':'42','provider_message_id':'manager-1',
        'provider_timestamp':NOW.isoformat()}
    result,status=handle_operational_specialist_message(message,authority,now=NOW,operation_store=store)
    assert status==409 and result['hardware_commands']==0 and not events


@pytest.mark.parametrize('ordering',['off_first','off_between_admission_and_send','on_first'])
def test_committed_owner_off_ordering_uses_actual_locked_on_edge(monkeypatch,ordering):
    from modules.telemetry import rootline_irrigation_execution_store as execution
    from modules.telemetry.rootline_water_energy_plan import read_current_borehole_faults
    from modules.telemetry.rootline_managed_devices_runtime import run_rootline_managed_device_cycle
    now=datetime.now(timezone.utc);art=eligibility(now)
    assert _valid_borehole_eligibility(art)
    body={**art,'claimed_at':now.isoformat(),'state':'claimed','primary_stop_deadline':None,
        'native_fail_stop_deadline':None,'on_attempts':0,'off_attempts':0,
        'claim_provider_evidence':{**provider(now=now),'execution_id':art['execution_id']}}
    claim=execution._stored_event_body('claim_borehole_before_on',body,execution._event_id('claim_borehole_before_on',body))
    rows=[claim];manual=[];connections=[];locks=[]
    def commit_off():
        manual.append({'provider_message_id':'stop-race','borehole_interlocks':{
            'manual_off_active':True,'observed_at':now.isoformat(),'provider_message_id':'stop-race',
            'source':'authenticated_owner_instruction'}})
    if ordering=='off_first':commit_off()
    class Cursor:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):
            self.sql=sql
            if 'pg_advisory_xact_lock' in sql:locks.append(params[0])
            return self
        def fetchall(self):
            assert 'rootline_operational_intake' in self.sql
            assert 1874320911 in locks
            return [(value,) for value in manual]
    class Connection:
        def __init__(self):self.sequence=len(connections)+1;connections.append(self)
        def __enter__(self):return self
        def __exit__(self,*args):
            if self.sequence==1 and ordering=='off_between_admission_and_send':commit_off()
        def cursor(self):return Cursor()
        def execute(self,*args):return Cursor().execute(*args)
    def connect(**kw):
        if kw.get('read_only') is False:assert kw.get('read_committed') is True
        return Connection()
    monkeypatch.setattr('modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres',connect)
    monkeypatch.setattr(execution,'_managed_edge_rows',lambda *args:list(rows))
    monkeypatch.setattr(execution,'_latest_borehole_conditions',lambda cursor:{**art['condition_evidence'],
        'assessed_at':now.isoformat(),'start_eligible':True,'stop_required':False})
    def insert(cursor,action,value):
        rows.append(execution._stored_event_body(action,value,execution._event_id(action,value)))
        return {'created':True,'success':True}
    monkeypatch.setattr(execution,'_insert_managed_event',insert)
    transport=Transport();transport.now=now
    result=execution._dispatch_managed_on_edge({**body,'dispatch':lambda:transport.set_state(
        device_id='1002851416',channel=1,state='ON',idempotency_key=art['execution_id']+':ON')},borehole=True)
    if ordering!='on_first':
        assert not result['accepted_unambiguous'] and not transport.commands
        if ordering=='off_first':assert len(rows)==1
        else:assert len(rows)==2
        return
    assert result['accepted_unambiguous'] and [x['state'] for x in transport.commands]==['ON']
    commit_off()  # The ON was genuinely dispatched before this instruction committed.
    when=datetime.now(timezone.utc);transport.now=when
    class ManagedStore(BoreholeStore):
        def __call__(self,action,value):
            if action=='load_active_auxiliaries':return []
            return super().__call__(action,value)
    owned=ManagedStore();owned.active={**body,'state':'Active','on_attempts':1,'provider_start_evidence':provider('ON',now)}
    run_rootline_managed_device_cycle(evidence={},transport=transport,store=owned,environ={},allow_new_starts=False,
        now=when,clock=lambda:when,borehole_safety_reader=lambda:read_current_borehole_faults('offline',now=when),
        borehole_conditions_reader=lambda:{'success':True,'stop_required':False,'reason':'conditions_allow_start'})
    assert [x['state'] for x in transport.commands]==['ON','OFF']


def test_instruction_insert_holds_existing_output_lock_on_same_read_committed_connection(monkeypatch):
    from modules.oom_sakkie.operational_specialist_intake import _operation_event_store
    calls=[];connection=object()
    class Connection:
        def execute(self,sql,params):calls.append(('lock',sql,params));return self
        def close(self):pass
    connection=Connection()
    def connect(**kw):
        assert kw['read_only'] is False and kw['read_committed'] is True
        return connection
    def record(event,*,connect_factory):
        actual=connect_factory()
        assert actual is connection and calls[-1][2]==(1874320911,)
        calls.append(('insert',event['review_event_id']))
        return {'success':True,'created':True},200
    monkeypatch.setenv('DATABASE_URL','postgresql://offline-test-boundary')
    monkeypatch.setattr('modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres',connect)
    monkeypatch.setattr('modules.sales.sam_live_stock_launch_control.record_sam_live_stock_review_event',record)
    result=_operation_event_store('record','instruction-test',{'mission_id':'offline-owner',
        'state':'completed','context':{'event_type':'borehole_owner_instruction'},
        'outcome':{'borehole_interlocks':{'manual_off_active':True}}})
    assert result['success'] and [row[0] for row in calls]==['lock','insert']


def test_current_manual_recheck_respects_explicit_resume_chronology(monkeypatch):
    from modules.telemetry import rootline_irrigation_execution_store as execution
    art=eligibility();current={**art['condition_evidence'],'assessed_at':NOW.isoformat(),'start_eligible':True,'stop_required':False}
    manual=[{'borehole_interlocks':{'manual_off_active':True,'observed_at':(NOW-timedelta(seconds=2)).isoformat(),
        'provider_message_id':'off'}}]
    class Cursor:
        def execute(self,*args):pass
        def fetchall(self):return [(row,) for row in manual]
    monkeypatch.setattr(execution,'_latest_borehole_conditions',lambda cursor:current)
    assert not execution._current_borehole_conditions_match(Cursor(),art,NOW)
    manual.append({'borehole_interlocks':{'manual_off_active':False,'observed_at':(NOW-timedelta(seconds=1)).isoformat(),
        'provider_message_id':'resume'}})
    assert execution._current_borehole_conditions_match(Cursor(),art,NOW)
    manual.append({'borehole_interlocks':{'manual_isolation_active':True,'observed_at':NOW.isoformat(),
        'provider_message_id':'isolation'}})
    assert not execution._current_borehole_conditions_match(Cursor(),art,NOW)


def test_condition_generation_preserves_rain_hold_when_transaction_start_order_inverts(monkeypatch):
    import json
    from modules.telemetry import rootline_irrigation_execution_store as execution
    events=[];connections=[]
    clocks=[NOW,NOW+timedelta(minutes=15),NOW+timedelta(minutes=61)]
    created=[NOW,NOW-timedelta(seconds=10),NOW+timedelta(minutes=61)]
    class Cursor:
        rowcount=1
        def __init__(self,connection):self.connection=connection;self.locked=False
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql,params=None):
            self.sql,self.params=sql,params
            if 'pg_advisory_xact_lock' in sql:self.locked=True
            if 'insert into public.sam_live_stock_conversation_review_events' in sql:
                assert self.locked
                events.append({'body':json.loads(params[-1])['rootline_execution'],'created_at':self.connection.created})
            return self
        def fetchone(self):
            if 'clock_timestamp' in self.sql:return (self.connection.now,)
            assert 'state_generation' in self.sql and 'coalesce' in self.sql
            ordered=sorted(events,key=lambda e:(e['body'].get('state_generation',0),e['created_at']))
            return (ordered[-1]['body'],) if ordered else None
        def fetchall(self):return []
    class Connection:
        def __init__(self):
            index=len(connections);self.now=clocks[index];self.created=created[index];connections.append(self)
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def cursor(self):return Cursor(self)
    def connect(**kw):
        assert kw['read_committed'] is True
        return Connection()
    monkeypatch.setattr('modules.oom_sakkie.bounded_postgres_read.connect_bounded_rootline_postgres',connect)
    def assess(at,rate=0):
        return execution._assess_borehole_conditions({'weather_snapshot':snapshot(at,rate=rate),'protection_safe':True,
            'forecast':{'observed_at':at.isoformat(),'days':[{'rain_sum_mm':20}]}})
    first=assess(clocks[0]);rainy=assess(clocks[1],.1);later=assess(clocks[2])
    assert [e['body']['state_generation'] for e in events]==[1,2,3]
    assert rainy['opportunity_id']==first['opportunity_id']==later['opportunity_id']
    assert later['rain_hold'] and not later['start_eligible']
    assert later['forecast_outcome']=='local_rain_observed'
    assert later['last_rain_at']==clocks[1].isoformat()
