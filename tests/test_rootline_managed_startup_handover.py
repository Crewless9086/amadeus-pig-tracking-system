"""Coordinator regressions for real readback latency and retired startup ownership."""
from datetime import datetime, timedelta, timezone
import pytest
from modules.telemetry.rootline_irrigation_coordinator import advance_auxiliary_execution
from modules.telemetry.rootline_borehole_commissioning import advance_borehole_execution, build_borehole_runtime_eligibility
from tests import test_rootline_fertilizer_auxiliary as aux
from tests import test_rootline_borehole_commissioning as borehole

@pytest.mark.parametrize('kind',['mixer','injector','borehole'])
def test_late_active_refusal_never_reports_started_and_recovers_off(kind):
    if kind=='borehole':
        class Store(borehole.BoreholeStore):
            def __call__(self,action,body):
                if action=='mark_borehole_active':return {'success':False,'created':False}
                return super().__call__(action,body)
        artifact=build_borehole_runtime_eligibility(need={'eligible':True},
            baseline={**borehole.canonical(),'registry_generation':2},
            authority={'inside_standing_authority':True},provider={'authoritative':True,'state':'OFF'},
            interlocks={'dry_run_safe':True,'low_water_clear':True,'supply_pressure_safe':True,'full_tank_not_blocking':True},
            energy={'eligible':True},requested_seconds=60,now=borehole.NOW)
        transport=borehole.BoreholeTransport();store=Store()
        result=advance_borehole_execution(eligibility=artifact,store=store,transport=transport,now=borehole.NOW)
        calls=transport.commands
    else:
        class Store(aux.Store):
            def __call__(self,action,body):
                if action=='mark_auxiliary_active':return {'success':False,'created':False}
                return super().__call__(action,body)
        transport=aux.Transport();store=Store()
        if kind=='injector':artifact=aux.injection_eligibility();context=aux.injection_context()
        else:
            artifact=aux.mixer_eligibility()
            context={'plan_generation':'PLAN-MIX-1','injection_active':False,
                'verified_mixing_minutes_today':0,'verified_mixing_sessions_today':0,
                'mixing_history_valid':True,'reserved_mixing_seconds_today':0,
                'mixing_history_complete_through':aux.NOW.isoformat(),'power_suitable':True}
        result=advance_auxiliary_execution(eligibility=artifact,store=store,transport=transport,
            now=aux.NOW,clock=lambda:aux.NOW,revalidate=lambda _:context)
        calls=transport.calls
    assert 'started' not in result['status']
    assert [r['state'] for r in calls]==['ON','OFF']

@pytest.mark.parametrize('provider_future',[False,True])
def test_actual_post_read_clock_accepts_delayed_off_but_not_future_provider_time(provider_future):
    start=datetime(2026,10,29,10,0,tzinfo=timezone.utc);clock=[start+timedelta(seconds=600)]
    execution={'execution_id':'MIX-LATENCY','auxiliary_device_id':'FERTILIZER-MIXER-CH2',
        'device_type':'fertilizer_mixer','device_id':'100204d497','channel':2,
        'claimed_at':start.isoformat(),'primary_stop_deadline':(start+timedelta(seconds=600)).isoformat(),
        'state':'Active','on_attempts':1,'off_attempts':0,'maximum_duration_seconds':600,
        'start_evidence':{'authoritative':True,'state':'ON','evidence_id':'START',
            'retrieved_at':start.isoformat()}}
    store=aux.Store();store.active=execution
    class Transport:
        def set_state(self,**kw):assert kw['state']=='OFF';clock[0]+=timedelta(seconds=1);return {'accepted_unambiguous':True}
        def read_output_state(self,**kw):
            clock[0]+=timedelta(seconds=1)
            return {'authoritative':True,'state':'OFF','evidence_id':'STOP',
                'retrieved_at':(clock[0]+timedelta(seconds=1 if provider_future else 0)).isoformat()}
    result=advance_auxiliary_execution(eligibility=None,store=store,transport=Transport(),
        now=clock[0],clock=lambda:clock[0])
    completed=result['execution']
    assert completed['completed_at']==(start+timedelta(seconds=602)).isoformat()
    assert completed['accounted_mixing_seconds']==(0 if provider_future else 600)
    assert completed['control_completed'] is (not provider_future)


def test_borehole_completion_uses_clock_after_provider_read():
    start=datetime(2026,10,29,10,0,tzinfo=timezone.utc);clock=[start+timedelta(seconds=60)]
    store=borehole.BoreholeStore();store.active={'execution_id':'BOREHOLE-LATENCY','state':'Active',
        'claimed_at':start.isoformat(),'primary_stop_deadline':clock[0].isoformat(),
        'provider_start_evidence':{'authoritative':True,'state':'ON','evidence_id':'START'}}
    class Transport(borehole.BoreholeTransport):
        def read_output_state(self,**kw):
            clock[0]+=timedelta(seconds=2)
            return {**super().read_output_state(**kw),'retrieved_at':clock[0].isoformat()}
    result=advance_borehole_execution(eligibility=None,store=store,transport=Transport(),
        now=clock[0],clock=lambda:clock[0])
    assert result['status']=='borehole_completed'
    assert result['execution']['completed_at']==clock[0].isoformat()
    assert result['execution']['provider_final_off_evidence']['retrieved_at']==clock[0].isoformat()


def test_bound_owner_dry_run_profile_needs_no_invented_pressure_or_low_water_reading():
    from copy import deepcopy
    from modules.telemetry.rootline_borehole_commissioning import borehole_protection_assessment, DEVICE_KEY
    now=datetime(2026,10,29,12,0,tzinfo=timezone.utc)
    baseline={'current':True,'device_key':DEVICE_KEY,'installed_protection_profile':{
        'device_key':DEVICE_KEY,'canonical_reference_resolved':True,
        'reference':{'observed_at':(now-timedelta(minutes=1)).isoformat()},
        'manual_isolation_proven':True,'pump_controller_internal_protection':True,
        'covered_risks':['dry_run'],'full_tank_cutoff_installed':True}}
    original=deepcopy(baseline);observations={}
    assert all(borehole_protection_assessment(baseline,observations,now=now).values())
    assert baseline==original and observations=={}  # Eligibility adds no measurement.
    for key,unsafe,gate in [('dry_run_safe',False,'dry_run'),('low_water_clear',False,'low_water'),
            ('supply_pressure_safe',False,'supply_pressure'),('full_tank_cutoff_fault',True,'full_tank')]:
        assert not borehole_protection_assessment(baseline,{key:unsafe},now=now)[gate]
    assert not any(borehole_protection_assessment(baseline,{'manual_isolation_active':True},now=now).values())
    for key,value in [('canonical_reference_resolved',False),('manual_isolation_proven',False),
            ('device_key','wrong-device'),('reference',{'observed_at':(now+timedelta(seconds=1)).isoformat()})]:
        invalid=deepcopy(baseline);invalid['installed_protection_profile'][key]=value
        assert not all(borehole_protection_assessment(invalid,{},now=now).values())
    invalid=deepcopy(baseline);invalid['installed_protection_profile']['covered_risks']=[]
    assert not borehole_protection_assessment(invalid,{},now=now)['dry_run']
    assert not borehole_protection_assessment(invalid,{},now=now)['low_water']
