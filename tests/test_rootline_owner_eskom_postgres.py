"""Real owner-request transactions on Eskom's separate command lock; no provider IO."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import uuid
import psycopg
import pytest
from modules.telemetry import rootline_owner_controls as controls
from modules.telemetry import rootline_irrigation_execution_store as store
from modules.telemetry.rootline_energy_policy import managed_energy_decision
from tests.test_rootline_owner_controls_postgres import database_url, sql, settings_request, preview_apply, ACTOR

@pytest.fixture
def grid(sql):
    device='synthetic-grid-'+uuid.uuid4().hex
    key='ifttt_smartlife:smartlife_owner_account:'+device+':1'
    with psycopg.connect(sql) as c:
        c.execute(Path('supabase/migrations/202608170001_add_rootline_device_registry.sql').read_text('utf-8'))
        c.execute("insert into app_private.rootline_standing_authorities(standing_authority_id,version,issuer,policy_sha256,active,policy_payload) values(%s,'1','isolated-test',%s,true,'{}')",(device,'a'*64))
        c.execute("insert into app_private.rootline_device_registry(device_key,contract_version,device_record,commissioning_stage,standing_authority_id,standing_authority_version,evidence_digest,registry_generation) values(%s,'rootline_device_spine.v1','{}','standing_active',%s,'1',%s,1)",(key,device,'a'*64))
    return sql,device,key

def queued(grid,kind='run'):
    url,device,key=grid;now=datetime.now(timezone.utc)
    preview_apply(url,settings_request(url,device='eskom',mode='manual_today',scope='today',fields={'on_soc_pct':30,'off_soc_pct':35},now=now),now=now)
    state=controls.load_runtime_owner_controls(url,now=now)
    body={'kind':kind,'device_id':'eskom','expected_revision':state['devices']['eskom']['revision'],'reason':'Isolated manual grid request','idempotency_key':'preview-grid-manual','changes':{}}
    preview_apply(url,body,now=now,key='apply-grid-manual')
    state=controls.load_runtime_owner_controls(url,now=now)
    request=controls.pending_owner_request(state,'eskom',now)
    power={'observed_at':now.isoformat(),'battery_soc_pct':80,'solar_power_w':0,'load_power_w':1000,'grid_power_w':0,'battery_power_w':1000,'battery_state':'discharging'}
    previous={'authoritative':True,'device_id':device,'state':'OFF','retrieved_at':now.isoformat(),'evidence_id':'synthetic-off'}
    claim={'execution_id':'isolated-grid-'+uuid.uuid4().hex,'device_id':device,'device_key':key,'baseline_sha256':'a'*64,'desired_state':'ON','decision':managed_energy_decision(power,now=now,owner_controls=state,owner_request=request),'power_evidence':power,'previous_readback':previous,'expected_transition_id':None,'owner_request_id':request['request_id'],'claimed_at':now.isoformat()}
    return request,claim

def test_manual_grid_request_claim_dispatch_and_replay_use_real_store(grid):
    url,_,_=grid;request,claim=queued(grid)
    assert store._claim_eskom_command(claim)['created']
    state=controls.load_runtime_owner_controls(url)
    assert controls.pending_owner_request(state,'eskom',datetime.now(timezone.utc)) is None
    assert len(state['consumed'])==1
    sent=[]
    body={**claim,'dispatch':lambda:sent.append('ON') or {'accepted_unambiguous':True}}
    assert store._dispatch_eskom_command_edge(body)['dispatched']
    assert store._dispatch_eskom_command_edge(body)['dispatched'] is False
    assert sent==['ON']

def test_pause_after_grid_claim_blocks_real_dispatch(grid):
    url,_,_=grid;request,claim=queued(grid)
    assert store._claim_eskom_command(claim)['created']
    preview_apply(url,settings_request(url,device='eskom',mode='paused',scope='today',fields={'on_soc_pct':30,'off_soc_pct':35},key='preview-grid-pause'),key='apply-grid-pause')
    sent=[]
    result=store._dispatch_eskom_command_edge({**claim,'dispatch':lambda:sent.append('ON')})
    assert result['dispatched'] is False and sent==[]

@pytest.mark.parametrize('age,accepted',[(0,True),(180,False)])
def test_already_on_grid_request_consumed_only_for_fresh_readback(grid,age,accepted):
    url,device,key=grid;request,claim=queued(grid)
    previous={**claim['previous_readback'],'state':'ON','retrieved_at':(datetime.now(timezone.utc)-timedelta(seconds=age)).isoformat(),'evidence_id':'synthetic-on'}
    payload={'owner_request_id':request['request_id'],'device_key':key,'desired_state':'ON','previous_readback':previous}
    result=controls.satisfy_owner_eskom_request(payload,database_url=url)
    assert result['success'] is accepted
    state=controls.load_runtime_owner_controls(url)
    assert len(state['consumed'])==int(accepted)
    with psycopg.connect(url) as c:
        assert c.execute("select count(*) from public.sam_live_stock_conversation_review_events where event_source=%s",(store.EVENT_SOURCE,)).fetchone()[0]==0
    if accepted:
        assert result['hardware_commands']==0
        assert controls.satisfy_owner_eskom_request(payload,database_url=url)['success'] is False
        assert len(controls.load_runtime_owner_controls(url)['consumed'])==1
