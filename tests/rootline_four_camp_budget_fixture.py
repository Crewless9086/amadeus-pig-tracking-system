"""Offline real admission/read-path replay. Boundary delays are synthetic, not live timings."""
from copy import deepcopy
from collections import Counter
from datetime import timedelta
from contextlib import contextmanager
import sys
from modules.telemetry import rootline_execution_runtime as runtime
from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry import rootline_cycle_budget as cycle
from modules.oom_sakkie import bounded_postgres_read as bounded
from tests.test_rootline_execution_authority import inputs, NOW
from tests.test_rootline_execution_runtime import Store

ALL_FLAGS={key:'true' for key in ('ROOTLINE_TIMED_CONTROL_ENABLED','ROOTLINE_AUTONOMOUS_BC_ENABLED',
 'ROOTLINE_A_ENABLED','ROOTLINE_E_ENABLED','ROOTLINE_FERTILIZER_MIXING_ENABLED',
 'ROOTLINE_FERTILIZER_INJECTION_ENABLED','ROOTLINE_BOREHOLE_ENABLED','ROOTLINE_ESKOM_ENABLED')}
ZONES=('B12345','C12345','A12345','E12345')

class OfflineAdmission:
 def __init__(self, patch, *, zone='B12345', connection_seconds=4, query_seconds=.2,
              evidence_seconds=10, provider_seconds=6, revoke_final=False, final_on=False):
  self.elapsed=0.;self.trace=[];self.connections=[];self.commands=[];self.notices=[]
  self.memory=Store();self.zone=zone;self.controller_reads=0;self.authority_reads=0
  self.connection_seconds=connection_seconds;self.query_seconds=query_seconds
  self.evidence_seconds=evidence_seconds;self.provider_seconds=provider_seconds
  self.revoke_final=revoke_final;self.final_on=final_on;self.output='OFF'
  import socket
  def no_network(*a,**k):raise AssertionError('offline_fixture_network_forbidden')
  patch.setattr(socket.socket,'connect',no_network)
  patch.setattr(socket,'create_connection',no_network)
  patch.setattr(cycle.time,'monotonic',lambda:1000+self.elapsed)
  patch.setattr(bounded,'connect_bounded_rootline_postgres',self.connect)
  patch.setattr(runtime,'_refresh_a_irrigation_binding',lambda *a:self.cost('A_binding',2))
  patch.setattr(runtime,'project_saved_program_for_execution',lambda *a,**k:deepcopy(self.plan))
  patch.setattr(runtime,'_reconcile_contained_bc_parents',lambda **k:[])
  original_load=store._load
  def load(action,payload):
   if action in store._ELIGIBILITY_READ_ACTIONS:return original_load(action,payload)
   self.cost(action,1);return self.memory(action,payload)
  patch.setattr(store,'_load',load)
  patch.setattr(store,'_bounded_claim',lambda action,fn,body:self.write(action,body))
  patch.setattr(store,'_append_history',lambda *a:False)
  from modules.sales import sam_live_stock_launch_control as sales
  def record(event,**kwargs):
   body=event['review_json']['rootline_execution']
   return self.write(body['action'],body),201
  patch.setattr(sales,'record_sam_live_stock_review_event',record)
  plan,evidence,controller=inputs(zone=zone)
  template=plan['candidate_tasks'][0]
  plan['candidate_tasks']=[dict(deepcopy(template),task_id='irrigation_'+z,rank=1 if z==zone else 2+i,
      planned_duration_minutes=120,max_execution_minutes=120,expected_segment_count=1) for i,z in enumerate(ZONES)]
  evidence['irrigation']['zones']=[dict(deepcopy(evidence['irrigation']['zones'][0]),zone_id=z) for z in ZONES]
  controller.update(current_outputs_authoritative=True,timers_enabled=True,actuation_configuration_safe=False)
  for row in controller['channels']:row.update(native_auto_off_enabled=False,native_auto_off_seconds=0)
  self.plan,self.evidence,self.controller=plan,evidence,controller
 def phase(self):
  frame=sys._getframe()
  while frame:
   if frame.f_code.co_name=='_current':
    return ('initial' if frame.f_locals.get('persist_resolutions',True) else 'final')
   frame=frame.f_back
  return 'edge'
 def cost(self,kind,seconds,**extra):
  start=self.elapsed;self.elapsed+=seconds
  self.trace.append(dict(kind=kind,phase=self.phase(),start=round(start,6),end=round(self.elapsed,6),**extra))
 def clock(self):return NOW+timedelta(seconds=self.elapsed)
 def connect(self,**kwargs):
  self.cost('connection',self.connection_seconds,shared=kwargs.get('read_committed') is True)
  cycle.remaining_seconds()
  c=OfflineConnection(self,len(self.connections),kwargs);self.connections.append(c);return c
 def write(self,action,body):
  self.cost(action,1);return self.memory(action,deepcopy(body))
 def loader(self,**kwargs):
  self.cost('evidence',self.evidence_seconds);cycle.remaining_seconds()
  return deepcopy(self.evidence),'2026-08-08',NOW
 def readback(self,**kwargs):
  assert store._eligibility_read_scope.get() is None
  assert all(c.closed for c in self.connections)
  self.controller_reads+=1;self.cost('controller',self.provider_seconds)
  cycle.remaining_seconds()
  value=deepcopy(self.controller)
  value['trusted_receipt_at']=self.clock().isoformat();value['response_digest']='READ-'+str(self.controller_reads)
  if self.final_on and self.controller_reads>1:value['channels'][2]['output_state']='ON'
  return value
 def authority(self,*args):
  self.authority_reads+=1;self.cost('authority',4)
  cycle.remaining_seconds()
  return not (self.revoke_final and self.authority_reads>1)
 def read_safety_configuration(self,**kwargs):
  assert store._eligibility_read_scope.get() is None
  self.cost('safety',self.provider_seconds);cycle.remaining_seconds()
  return {**kwargs,'zone_id':self.zone,'scheduled_authoritative':True,'output_state':'OFF',
    'response_digest':'SAFETY','observed_at':self.clock().isoformat(),'relevant_outputs_off':True}
 def set_state(self,**kwargs):
  if kwargs['state']=='ON':cycle.remaining_seconds()
  self.cost('command',1);self.commands.append(kwargs);self.output=kwargs['state']
  return {'accepted_unambiguous':True}
 def read_output_state(self,**kwargs):
  self.cost('output',self.provider_seconds)
  return {**kwargs,'authoritative':True,'state':self.output,'evidence_id':'OUT-'+str(self.elapsed),
      'retrieved_at':self.clock().isoformat()}
 def notify(self,*args):
  self.notices.append(args);return {'provider_delivery_confirmed':True,'provider_message_id':'OFFLINE'}
 def run(self):
  result=runtime.run_rootline_execution_cycle(notify=self.notify,environ=ALL_FLAGS,now=NOW,
      store=store.rootline_irrigation_execution_store,token_store=object(),transport=self,
      evidence_loader=self.loader,readback=self.readback,clock=self.clock,
      owner_user_id='42',chat_id='42',observation_store=lambda *a:{'success':True},
      authority_checker=self.authority)
  return {'status':result['status'],'elapsed_seconds':round(self.elapsed,6),'zone':self.zone,
   'canonical_connections':len(self.connections),'statements':sum(c.statements for c in self.connections),
   'connections_closed':all(c.closed for c in self.connections),'controller_reads':self.controller_reads,
   'authority_reads':self.authority_reads,'commands':self.commands,'trace':self.trace,
   'result':result,'all_flags':ALL_FLAGS,'timing':'synthetic boundary costs; no measured production latency',
   'live_calls':0,'business_outcome':False}

class OfflineConnection:
 def __init__(self,fixture,identity,kwargs):
  self.fixture=fixture;self.identity=identity;self.kwargs=kwargs;self.closed=False;self.statements=0;self.sql=''
 def __enter__(self):return self
 def __exit__(self,*args):self.close()
 def cursor(self):return OfflineCursor(self)
 def rollback(self):pass
 def close(self):self.closed=True

class OfflineCursor:
 def __init__(self,connection):self.connection=connection;self.sql=''
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def execute(self,sql,params=()):
  assert sql.lstrip().lower().startswith('select'),sql
  self.sql=sql;self.connection.statements+=1
  self.connection.fixture.cost('select',self.connection.fixture.query_seconds,
      connection_id=self.connection.identity,zone_or_job=str(params[1]) if len(params)>1 else None)
  cycle.remaining_seconds()
 def fetchone(self):
  return ('read committed','on') if self.sql.startswith('select current_setting') else None
 def fetchall(self):return []
