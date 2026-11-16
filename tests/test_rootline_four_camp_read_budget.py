"""Scheduled A/B/C/E admission preserves fresh checks under accumulated latency."""
from datetime import timedelta
import pytest
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry import rootline_cycle_budget as cycle
from tests.rootline_four_camp_budget_fixture import OfflineAdmission, ALL_FLAGS, ZONES, NOW

@pytest.mark.parametrize('zone',ZONES)
@pytest.mark.parametrize('connection_seconds',(0,4,8))
def test_four_camp_admission_reuses_only_per_build_reads(monkeypatch,zone,connection_seconds):
 fixture=OfflineAdmission(monkeypatch,zone=zone,connection_seconds=connection_seconds)
 row=fixture.run()
 assert row['status']=='segment_started',row
 assert row['canonical_connections']==5
 assert row['controller_reads']==row['authority_reads']==2
 assert row['connections_closed']
 assert [x['state'] for x in row['commands']]==['ON']
 assert row['elapsed_seconds']<115
 assert len(fixture.notices)==1
 assert {x['phase'] for x in row['trace'] if x['kind']=='controller'}=={'initial','final'}
 assert len({x['connection_id'] for x in row['trace'] if x['kind']=='select' and x['phase']=='initial'})==2
 assert len({x['connection_id'] for x in row['trace'] if x['kind']=='select' and x['phase']=='final'})==2
 assert store._eligibility_reader_owner.get() is None
 assert store._eligibility_read_scope.get() is None
 assert cycle.work_deadline() is cycle.on_deadline() is None

@pytest.mark.parametrize('costs',[{'connection_seconds':30},{'provider_seconds':35},{'evidence_seconds':65}])
def test_slow_response_still_defers_without_command_or_connection_leak(monkeypatch,costs):
 fixture=OfflineAdmission(monkeypatch,**costs)
 row=fixture.run()
 assert row['status']=='execution_cycle_deadline_deferred',row
 assert not row['commands'] and not fixture.notices
 assert not any(action=='claim_before_on' for action,_ in fixture.memory.rows)
 assert row['connections_closed']
 assert cycle.CYCLE_WORK_SECONDS==140
 assert store._eligibility_read_scope.get() is None

@pytest.mark.parametrize('changed',['authority','provider'])
@pytest.mark.parametrize('zone',ZONES)
def test_final_fresh_checks_still_refuse_changed_evidence(monkeypatch,changed,zone):
 fixture=OfflineAdmission(monkeypatch,zone=zone,revoke_final=changed=='authority',final_on=changed=='provider')
 row=fixture.run()
 assert row['status']=='execution_eligibility_changed',row
 assert row['controller_reads']==2
 assert not row['commands'] and not fixture.notices
 assert not any(action=='claim_before_on' for action,_ in fixture.memory.rows)
 assert row['connections_closed']

@pytest.mark.parametrize('failure',['expired','canonical','power'])
def test_eskom_deadline_is_distinct_from_unavailable_readiness(monkeypatch,failure):
 fixture=OfflineAdmission(monkeypatch,connection_seconds=0)
 from modules.telemetry import rootline_managed_devices_runtime as managed
 from modules.telemetry import rootline_device_spine as spine
 from modules.telemetry import rootline_eskom_runtime as eskom
 from modules.telemetry import power_service
 seen=[]
 def managed_cycle(**kwargs):
  assert kwargs['environ']==ALL_FLAGS
  if failure=='expired':fixture.cost('managed_deadline',141)
  return {'success':True,'status':'no_active_managed_device','hardware_commands':0}
 monkeypatch.setattr(managed,'run_rootline_managed_device_cycle',managed_cycle)
 def power(**kwargs):
  seen.append('power')
  if failure=='power':raise RuntimeError('offline power unavailable')
  return {'current':{},'source':{}},200
 monkeypatch.setattr(power_service,'get_current_power_state',power)
 def canonical(*args,**kwargs):
  seen.append('canonical')
  raise RuntimeError('offline canonical unavailable')
 monkeypatch.setattr(spine,'load_device_record',canonical)
 monkeypatch.setattr(eskom,'run_eskom_cycle',lambda **kwargs:pytest.fail('unproven grid command'))
 with cycle.cycle_budget():
  value=runtime.run_rootline_managed_device_reassessment(environ=ALL_FLAGS,now=NOW,
   token_store=object(),transport=fixture,store=fixture.memory,clock=fixture.clock)
 assert value['eskom']['status']==('eskom_cycle_deadline_deferred' if failure=='expired' else 'eskom_readiness_unavailable')
 assert value['hardware_commands']==0 and not fixture.commands
 if failure=='expired':assert seen==[]

from tests.test_rootline_active_supervision import reports

@pytest.mark.parametrize('connection_seconds,report_expected',[(4,True),(8,False),(30,False)])
def test_all_enabled_scheduler_keeps_managed_safety_and_reports_when_time_remains(monkeypatch,reports,connection_seconds,report_expected):
 from modules.oom_sakkie.telegram_gateway import handle_rootline_reassessment_trigger
 from tests.test_rootline_active_supervision import ScheduleStore,ENV,HEADERS,payload,current
 from tests.test_rootline_eskom_runtime import CONFIG,canonical
 from modules.telemetry import power_service
 from modules.telemetry import rootline_device_spine as spine
 fixture=OfflineAdmission(monkeypatch,connection_seconds=connection_seconds)
 source={**ENV,**CONFIG,**ALL_FLAGS}
 schedules=ScheduleStore();observations={};controls=[];managed_results=[];report_calls=[];inventory=[]
 def state(action,identity,body):
  if action=='load_identity':return observations.get(identity)
  if action.startswith('load_'):return None
  observations[identity]=body;return {'success':True,'created':True}
 def managed_store(action,body):
  inventory.append((action,fixture.elapsed))
  fixture.cost('managed_'+action,.5)
  if action in {'load_active_auxiliaries','load_eskom_events'}:return []
  if action=='load_active_borehole':return None
  pytest.fail('unexpected managed mutation '+action)
 def power(**kwargs):
  fixture.cost('power',1)
  return {'current':{'observed_at':fixture.clock().isoformat(),'battery_soc_pct':33,
    'solar_power_w':0,'load_power_w':100,'grid_power_w':100,'battery_power_w':0},
    'source':{'last_reading_at':fixture.clock().isoformat()}},200
 monkeypatch.setattr(power_service,'get_current_power_state',power)
 def load_record(*args,**kwargs):fixture.cost('grid_canonical',1);return canonical()
 monkeypatch.setattr(spine,'load_device_record',load_record)
 def managed(**kwargs):
  value=runtime.run_rootline_managed_device_reassessment(**kwargs,token_store=object(),
    transport=fixture,store=managed_store,evidence_loader=fixture.loader,clock=fixture.clock)
  managed_results.append(value);return value
 def admission(**kwargs):
  value=runtime.run_rootline_execution_cycle(**kwargs,store=store.rootline_irrigation_execution_store,
    token_store=object(),transport=fixture,evidence_loader=fixture.loader,readback=fixture.readback,
    clock=fixture.clock,authority_checker=fixture.authority)
  controls.append(value);return value
 def loader(**kwargs):
  report_calls.append(fixture.elapsed)
  return {**current(),'operating_date':NOW.date().isoformat(),'evidence_cutoff':NOW.isoformat()}
 request=payload(due_at=NOW.isoformat(),trigger_timestamp=NOW.isoformat(),evidence_cutoff=(NOW-timedelta(seconds=1)).isoformat())
 value,status=handle_rootline_reassessment_trigger(request,HEADERS,source,scheduler_now=NOW,
   state_store=state,schedule_store=schedules,specialist_loader=loader,
   family_delivery=lambda *a,**k:{'success':True,'telegram_sends':1,'telegram_message_id':'OFFLINE'},
   active_supervision_cycle=lambda **k:{'success':True,'status':'no_active_irrigation','active_execution_found':False},
   managed_device_cycle=managed,execution_cycle=admission)
 assert bool(report_calls)==report_expected,(value,fixture.trace,managed_results)
 assert len(controls)==len(managed_results)==1
 assert sum(action=='load_active_auxiliaries' for action,_ in inventory)>=2
 assert sum(action=='load_active_borehole' for action,_ in inventory)>=2
 if connection_seconds==30:
  assert controls[0]['status']=='execution_cycle_deadline_deferred'
  assert managed_results[0]['eskom']['status']=='eskom_cycle_deadline_deferred'
  assert not fixture.commands
 else:
  assert controls[0]['status']=='segment_started',controls
  assert managed_results[0]['eskom']['status']=='eskom_current_state_retained',managed_results
  assert [x['state'] for x in fixture.commands]==['ON']
  assert value['hardware_commands']==1
  if not report_expected:assert value['status']=='scheduled_rootline_reporting_deadline_deferred'
 assert all(c.closed for c in fixture.connections)
 assert cycle.work_deadline() is cycle.on_deadline() is None
