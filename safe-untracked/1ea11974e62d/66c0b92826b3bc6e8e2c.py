"""Real disposable PostgreSQL, actual selected handlers; no app startup/providers."""
import ast
import copy
import hashlib
import hmac
import io
import json
import os
import re
import threading
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path

import pytest
from flask import Blueprint,Flask,jsonify,request
from types import SimpleNamespace

from modules.charlie.native_runner.recovery import digest,scope_for,transact
from modules.charlie.native_runner.canonical_client import CanonicalClient,JsonClient

M='CHARLIE-MISSION-TRANSACTION-TEST'
REV='a'*40
TOKEN='disposable-worker-token-000000000000000000'
ROOT=Path(__file__).resolve().parents[1]


def load(names,path,scope):
    tree=ast.parse((ROOT/path).read_text(encoding='utf8'))
    nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]
    assert {n.name for n in nodes}==set(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),str(ROOT/path),'exec'),scope)


@pytest.fixture
def plane(monkeypatch):
    if os.environ.get('CHARLIE_TEST_POSTGRES_DISPOSABLE')!='1':
        pytest.skip('requires owned disposable PostgreSQL harness; never use production DSN')
    import psycopg
    dsn=os.environ['CHARLIE_TEST_POSTGRES_DSN']
    assert dsn.startswith('host=127.0.0.1 ') and 'user=native_recovery_test ' in dsn
    from tests.test_charlie_native_database_privileges import initialize_privilege_database
    from modules.charlie import mission_store as real_store
    admin_dsn=os.environ['CHARLIE_TEST_POSTGRES_ADMIN_DSN'].replace('dbname=charlie_roles_test ', 'dbname=charlie_runtime_test ')
    app_dsn=initialize_privilege_database(admin_dsn)
    monkeypatch.setenv('CHARLIE_MISSION_DATABASE_URL',app_dsn)
    def connect():return real_store._connect(app_dsn)
    scope={'json':json,'datetime':datetime,'timezone':timezone,
           '_clean_text':lambda v,n:str(v or '')[:n], '_database_url':real_store._database_url,
           '_event_id':lambda m,e:hashlib.sha256((m+e+datetime.now(timezone.utc).isoformat()).encode()).hexdigest()}
    scope.update(_connect=lambda *_:connect(),_verify_database_connection=real_store._verify_database_connection,timedelta=timedelta,re=re,hashlib=hashlib,
                 MISSION_STATUSES={'in_progress','approved'},_write_normalized_vault_records=lambda *a,**k:[])
    load(['owner_execution_hold_status','_insert_event','native_runner_recovery',
          'record_hermes_native_execution_state','bind_external_supervisor_candidate',
          'update_mission_vault','_not_execution_held_sql','_public_owner_execution_hold'],
          'modules/charlie/mission_store.py',scope)
    metadata={'native_runner_blocker':{'blocker_fingerprint':'f'*64,'runner_revision':REV,'generation':'g1'},
       'dispatch_authorization':{'generation':'g1','base_sha':REV,'owner_instruction_digest':'b'*64,
        'allowed_files':['demo.py'],'allowed_effects':['edit_allowed_files']},
       'mission_vault':{'test_plan':['synthetic-contract'],'acceptance_criteria':['synthetic outcome']}}
    with connect() as c:
        with c.cursor() as q:q.execute("insert into charlie_missions(mission_id,status,raw_text,title,urgency,mission_type,approval_level,metadata_json)values(%s,'in_progress','synthetic','synthetic','normal','software','owner',%s::jsonb)",(M,json.dumps(metadata)))
    class Plane:
        store=scope
        def call(self,op,payload,principal='hermes:builder',event=None):
            return transact(M,op,payload,principal=principal,runtime={'worker_revision':REV,'web_revision':REV},
                connect=connect,owner_hold=scope['owner_execution_hold_status'],event=event or scope['_insert_event'])
        def metadata(self):
            with connect() as c:
                with c.cursor() as q:
                    q.execute('select metadata_json from charlie_missions where mission_id=%s',(M,));return q.fetchone()[0]
        def sql(self,sql,params=()):
            # Fixture setup/forensics use the isolated admin; recovery uses APP.
            with psycopg.connect(admin_dsn) as c:
                with c.cursor() as q:
                    q.execute(sql,params)
                    return q.fetchall() if q.description else None
        def add_hold(self,event_id):
            self.sql("""insert into charlie_owner_execution_hold_events
                (event_id,hold_id,mission_id,generation_identity,event_type,reason,owner_identity_hash,authorization_identity)
                values(%s,%s,%s,'g1','hold_created','synthetic fixture hold',%s,%s)""",
                (event_id,'fixture-'+event_id,M,'a'*64,'b'*64))
        def grant(self):
            return {'request_id':'OWNER-SYNTHETIC-1','scope':scope_for(M,self.metadata(),{'worker_revision':REV,'web_revision':REV}),
                    'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),
                    'limits':{'requests':2,'spend_microusd':20,'per_request_microusd':10},
                    'verification':[{'name':'synthetic-contract','argv':['python','-m','pytest','tests/test_synthetic.py']}]}
        def lease(self):
            grant=self.grant();result,code=self.call('issue',grant,'owner-admin:synthetic-signed');assert code==201,result
            g=result['receipt']['grant'];payload={'grant_id':g['grant_id'],'request_id':'consume-1','incarnation':'boot-1'}
            result,code=self.call('consume',payload);assert code==201,result
            return {k:result['receipt']['lease'][k] for k in ('grant_id','incarnation','epoch','claim_id')}
    return Plane()


def effect(proof,n=1,kind='model'):
    return {'proof':proof,'effect_id':'effect-'+str(n),'kind':kind,
            'intent':{'candidate':{},'provider':'labelled-fake-provider','model':'fake-only',
                      'request_sha256':digest(['labelled-fake-provider',n])}}


def model_receipt(proof,n=1):
    return {'proof':proof,'effect_id':'effect-'+str(n),'outcome':'confirmed',
            'evidence':{'intent_sha256':digest(effect(proof,n)['intent']),
                        'request_id':'fake-request-'+str(n),'response_sha256':'d'*64,
                        'provider':'labelled-fake-provider','model':'fake-only'}}


def test_grant_consume_exact_replay_and_conflict(plane):
    grant=plane.grant();r,c=plane.call('issue',grant,'owner-admin:synthetic-signed');assert c==201
    assert plane.call('issue',grant,'owner-admin:synthetic-signed')[1]==200
    payload={'grant_id':r['receipt']['grant']['grant_id'],'request_id':'consume-1','incarnation':'boot-1'}
    assert plane.call('consume',payload)[1]==201
    assert plane.call('consume',payload)[1]==200
    assert plane.call('consume',{**payload,'incarnation':'competing-boot'})[1]==409
    assert len(plane.sql('select * from charlie_mission_events'))==2


@pytest.mark.parametrize('principal',['','hermes:builder','owner-admin:local-development','owner-read:test'])
def test_worker_cannot_issue(plane,principal):
    assert plane.call('issue',plane.grant(),principal)[1]==403
    assert 'native_recovery' not in plane.metadata()


@pytest.mark.parametrize('key',['generation','hold','candidate','allowed_files','runtime'])
def test_mismatched_owner_scope(plane,key):
    grant=plane.grant();grant['scope'][key]='wrong'
    assert plane.call('issue',grant,'owner-admin:signed')[1]==409


def test_two_connections_only_one_consumer(plane):
    r,c=plane.call('issue',plane.grant(),'owner-admin:signed');assert c==201
    barrier=threading.Barrier(2)
    def consume(i):
        barrier.wait()
        return plane.call('consume',{'grant_id':r['receipt']['grant']['grant_id'],'request_id':f'consume-{i}','incarnation':f'boot-{i}'})
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(consume,[1,2]))
    assert sorted(c for _,c in results)==[201,409]


def test_concurrent_last_budget_reservation_and_ambiguous_outcome(plane):
    proof=plane.lease();r,c=plane.call('reserve',effect(proof));assert c==201
    assert plane.call('finish',model_receipt(proof))[1]==201
    barrier=threading.Barrier(2)
    def reserve(i):barrier.wait();return plane.call('reserve',effect(proof,i))
    with ThreadPoolExecutor(2) as pool:results=list(pool.map(reserve,[2,3]))
    assert sorted(c for _,c in results)==[201,409]
    state=plane.metadata()['native_recovery'];assert state['requests']==2 and state['spend_microusd']==20
    winning=next(r['receipt']['effect']['effect_id'] for r,c in results if c==201)
    assert plane.call('finish',{'proof':proof,'effect_id':winning,'outcome':'ambiguous','evidence':{'fake_timeout':True}})[1]==201
    assert plane.call('reserve',effect(proof,4))[1]==409
    assert plane.metadata()['native_recovery']['spend_microusd']==20


def test_lost_reservation_ack_is_never_second_execution_permission(plane):
    proof=plane.lease();first,code=plane.call('reserve',effect(proof));assert code==201
    replay,code=plane.call('reserve',effect(proof));assert code==200
    assert first['receipt']['may_execute'] is True and replay['receipt']['may_execute'] is False
    changed=effect(proof);changed['intent']['request_sha256']='0'*64
    assert plane.call('reserve',changed)[1]==409


def test_projection_and_event_roll_back_together(plane):
    before=plane.metadata()
    def fail(q,m,t,n,e):
        q.execute("insert into charlie_mission_events(event_id,mission_id,event_type,metadata_json)values('rolled-back',%s,'synthetic','{}')",(m,))
        raise RuntimeError('synthetic interruption after event insert')
    r,c=plane.call('issue',plane.grant(),'owner-admin:signed',event=fail)
    assert c==503 and plane.metadata()==before and plane.sql('select * from charlie_mission_events')==[]


def test_external_projection_reset_cannot_reset_budget(plane):
    proof=plane.lease();assert plane.call('reserve',effect(proof))[1]==201
    plane.sql("update charlie_missions set metadata_json=jsonb_set(metadata_json,'{native_recovery,requests}','0')")
    r,c=plane.call('check',{'proof':proof});assert c==409 and r['status']=='native_recovery_checkpoint_conflict'


def test_owner_hold_veto_is_real_table_read(plane):
    plane.add_hold('held')
    assert plane.call('issue',plane.grant(),'owner-admin:signed')[1]==423


def test_stale_fence_and_expiry(plane):
    proof=plane.lease()
    assert plane.call('check',{'proof':{**proof,'epoch':99}})[1]==409
    assert plane.call('check',{'proof':{**proof,'incarnation':'restart-without-authority'}})[1]==409


def http_plane(plane, monkeypatch, *, owner=True):
    """Actual Flask, signed owner session and selected unchanged route decorators."""
    from modules.auth import owner_access
    for key,value in {'OWNER_ACCESS_ENABLED':'1','OWNER_ACCESS_ALLOW_LOCAL_DEV':'0',
                      'OWNER_ADMIN_TOKEN':'test-owner-admin-'+'x'*40,'OWNER_READ_TOKEN':'test-owner-read-'+'y'*40,
                      'OWNER_SESSION_SECRET':'test-session-secret-'+'z'*40}.items():monkeypatch.setenv(key,value)
    bp=Blueprint('transaction_contract',__name__)
    scope={**plane.store,'charlie_bp':bp,'jsonify':jsonify,'request':request,'hmac':hmac,
           'env_value':lambda name:REV if name=='RENDER_GIT_COMMIT' else TOKEN, 'urllib':__import__('urllib'),
           'require_strict_owner_admin_access':owner_access.require_strict_owner_admin_access,
           'strict_owner_admin_principal':owner_access.strict_owner_admin_principal,
           'get_mission':lambda _:({'success':True,'status':'ok','mission':{'mission_id':M,'metadata':plane.metadata()}},200)}
    load(['_require_hermes_gateway_access','charlie_native_runner_resume_route',
          'charlie_native_runner_recovery_operation_route','charlie_native_recovery_effect_guard',
          'charlie_hermes_native_execution_progress_route','charlie_hermes_mission_status_route',
          'charlie_native_runner_reconcile_effect_route','charlie_external_supervisor_candidate_route',
          'charlie_hermes_mission_admission_route'],
          'modules/charlie/routes.py',scope)
    app=Flask('transaction_contract');owner_access.configure_owner_access(app)
    app.register_blueprint(bp,url_prefix='/api')
    http=app.test_client()
    if owner:
        with http.session_transaction() as session:
            session['owner_access']={'role':'admin','principal_id':owner_access._stable_owner_principal('admin')}
    def opened(req,**_):
        response=http.open(urllib.parse.urlsplit(req.full_url).path,method=req.method,
                           headers=dict(req.header_items()),data=req.data)
        if response.status_code>=400:
            raise urllib.error.HTTPError(req.full_url,response.status_code,'synthetic response',{},io.BytesIO(response.data))
        class Reply:
            status=response.status_code
            def read(self):return response.data
            def __enter__(self):return self
            def __exit__(self,*_):pass
        return Reply()
    api=CanonicalClient('https://example.invalid/api',TOKEN,
                        client=JsonClient('https://example.invalid/api',TOKEN,opener=opened))
    return http,api


@pytest.mark.parametrize('mode',['anonymous','worker','role-only','read','local-dev','wrong-intent','malformed'])
def test_actual_owner_handler_denies_non_authority(plane,monkeypatch,mode):
    http,api=http_plane(plane,monkeypatch,owner=False)
    headers={'X-CHARLIE-Owner-Action':'native_runner_resume'}
    if mode=='worker':headers['Authorization']='Bearer '+TOKEN
    if mode in {'role-only','read'}:
        with http.session_transaction() as session:session['owner_access']={'role':'admin' if mode=='role-only' else 'read'}
    if mode=='local-dev':monkeypatch.setenv('OWNER_ACCESS_ALLOW_LOCAL_DEV','1')
    if mode in {'wrong-intent','malformed'}:
        http,api=http_plane(plane,monkeypatch)
    if mode=='wrong-intent':headers['X-CHARLIE-Owner-Action']='owner_execution_hold_release'
    response=http.post(f'/api/charlie/build-relay/missions/{M}/native-runner/resume',
                       json=[] if mode=='malformed' else plane.grant(),headers=headers)
    assert response.status_code in {400,403}
    assert 'native_recovery' not in plane.metadata()


def test_actual_caller_handler_grant_consume_lost_ack_restart(plane,monkeypatch):
    from modules.charlie.native_runner.recovery_session import RecoverySession
    from modules.charlie.native_runner.execution import NativeExecutionError
    http,api=http_plane(plane,monkeypatch)
    grant=plane.grant()
    response=http.post(f'/api/charlie/build-relay/missions/{M}/native-runner/resume',json=grant,
                       headers={'X-CHARLIE-Owner-Action':'native_runner_resume'})
    assert response.status_code==201,response.json
    original=api.client.opener
    lost=[True]
    def lose(req,**kw):
        response=original(req,**kw)
        if req.full_url.endswith('/consume') and lost[0]:
            lost[0]=False;raise TimeoutError('synthetic lost acknowledgement after database commit')
        return response
    api.client.opener=lose
    held={'state':'BLOCKED_HOLD','mission_id':M,'generation':'g1','blocker_fingerprint':'f'*64}
    session=RecoverySession(api,M,incarnation='synthetic-boot-1')
    receipt=session.consume(held,worker_revision=REV)
    assert receipt['lease']['incarnation']=='synthetic-boot-1'
    session.consume(held,worker_revision=REV)
    with pytest.raises(NativeExecutionError):
        RecoverySession(api,M,incarnation='synthetic-boot-2').consume(held,worker_revision=REV)
    assert len(plane.sql('select * from charlie_mission_events'))==2


def test_owner_renewal_preserves_budget_and_requires_exact_prior_state(plane):
    proof=plane.lease();assert plane.call('reserve',effect(proof))[1]==201
    assert plane.call('finish',model_receipt(proof))[1]==201
    grant=plane.grant();grant['request_id']='OWNER-SYNTHETIC-2'
    assert plane.call('issue',grant,'owner-admin:signed')[1]==409
    grant['prior_state_sha256']=digest(plane.metadata()['native_recovery'])
    result,code=plane.call('issue',grant,'owner-admin:signed');assert code==201,result
    state=plane.metadata()['native_recovery'];assert state['requests']==1 and state['spend_microusd']==10
    assert len(state['history'])==1
    result,code=plane.call('consume',{'grant_id':state['grant']['grant_id'],'request_id':'consume-2','incarnation':'boot-2'})
    assert code==201 and result['receipt']['lease']['epoch']==2
    assert plane.call('check',{'proof':proof})[1]==409


def test_owner_reconciles_ambiguous_receipt_without_second_send(plane):
    proof=plane.lease();assert plane.call('reserve',effect(proof))[1]==201
    assert plane.call('finish',{'proof':proof,'effect_id':'effect-1','outcome':'ambiguous','evidence':{'timeout':True}})[1]==201
    payload={'effect_id':'effect-1','prior_state_sha256':digest(plane.metadata()['native_recovery']),
             'evidence':model_receipt(proof)['evidence']}
    assert plane.call('reconcile',payload)[1]==403
    assert plane.call('reconcile',payload,'owner-admin:signed')[1]==201
    assert plane.call('reserve',effect(proof))[0]['receipt']['may_execute'] is False
    assert plane.metadata()['native_recovery']['requests']==1


@pytest.mark.parametrize('projection',[
    {'external_supervisor_state':{'agent_state':'ACTIVE','run_state':'RUNNING'}},
    {'hermes_native_execution':{'worker_claim_id':'HNC-OTHER'}},
    {'execution_lease':{'id':'retained'}}])
def test_actual_competing_writer_projections(plane,projection):
    plane.sql("insert into charlie_missions(mission_id,status,raw_text,title,urgency,mission_type,approval_level,metadata_json)values(%s,'in_progress','synthetic','synthetic','normal','software','owner',%s::jsonb)",('OTHER-MISSION',json.dumps(projection)))
    assert plane.call('issue',plane.grant(),'owner-admin:signed')[1]==409


def test_missing_event_insertion_never_grants_permission(plane):
    r,c=plane.call('issue',plane.grant(),'owner-admin:signed',event=lambda *_:None)
    assert c==503 and 'native_recovery' not in plane.metadata()


def test_receipt_ok_flag_and_malformed_release_rejected(plane):
    proof=plane.lease();assert plane.call('reserve',effect(proof))[1]==201
    assert plane.call('finish',{'proof':proof,'effect_id':'effect-1','outcome':'confirmed','evidence':{'ok':True}})[1]==409
    assert plane.call('release',{'proof':proof,'request_id':'release-1','native_execution_id':None,'head_sha':None})[1]==409


@pytest.mark.parametrize('lost_release_ack',[False,True])
def test_synthetic_held_to_exact_owner_decision_journey(plane,monkeypatch,tmp_path,lost_release_ack):
    """Fake provider outcomes, actual held service/caller/Flask/store/PG transitions.

    The candidate, verification and reviewer fixtures are labelled simulated;
    this test cannot certify a real pilot patch, SEND_BACK or business outcome.
    """
    from modules.charlie.native_runner.service import NativeRunnerService
    from modules.charlie.native_runner.candidate_contract import binding_from_authority
    from modules.charlie.native_runner.canonical_client import GitHubObserver
    from modules.charlie.native_runner.recovery_session import RecoverySession
    native={'mission_id':M,'native_execution_id':'HNX-SYNTHETIC','generation':'g1','status':'valid',
            'execution_status':'RUNNING','branch':'charlie/synthetic-native-1','worktree_digest':'e'*64,
            'starting_main_sha':REV,'owner_instruction_digest':'b'*64,'allowed_files':['demo.py'],
            'allowed_effects':['edit_allowed_files'],'forbidden_files':['.env*'],
            'forbidden_effects':['merge','deploy'],'expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    metadata=plane.metadata();metadata.update(hermes_native_execution=native,
        external_supervisor_state={'slack_channel_id':'C-FAKE-THREAD','slack_thread_ts':'100.001'},
        slack_approval_channel_id='C-FAKE-OWNER')
    plane.sql('update charlie_missions set metadata_json=%s::jsonb where mission_id=%s',(json.dumps(metadata),M))
    http,api=http_plane(plane,monkeypatch)
    grant=plane.grant()
    response=http.post(f'/api/charlie/build-relay/missions/{M}/native-runner/resume',json=grant,
                       headers={'X-CHARLIE-Owner-Action':'native_runner_resume'})
    assert response.status_code==201,response.json
    messages=[]
    class FakeSlack:
        def post(self,channel,text,*,thread_ts='',idempotency_key=''):
            import uuid
            message={'channel':channel,'thread_ts':thread_ts,'ts':f'200.{len(messages)+1:06d}',
                     'client_msg_id':str(uuid.uuid5(uuid.NAMESPACE_URL,'charlie-slack:'+idempotency_key)),
                     'text_sha256':hashlib.sha256(text.encode()).hexdigest()}
            messages.append(message)
            if channel=='C-FAKE-OWNER':
                from modules.charlie.native_runner.execution import NativeExecutionError
                raise NativeExecutionError('native_transport_unavailable')
            return {'ok':True}
        def lookup(self,channel,**expected):
            rows=[m for m in messages if m['channel']==channel and all(m[k]==v for k,v in expected.items())]
            assert len(rows)==1
            return rows[0]
    observed={'pr_number':17,'head_sha':'c'*40,'draft':True,'checks':{n:'success' for n in GitHubObserver.REQUIRED},
              'all_required_checks_pass':True}
    service=NativeRunnerService(profile_home=tmp_path,repository_root=tmp_path,worktree_root=tmp_path/'worktrees',
        canonical=api,cursor=object(),github=SimpleNamespace(pull_state=lambda _:dict(observed)),
        model=SimpleNamespace(complete_structured=lambda **_:pytest.fail('no real model')),
        notifier=FakeSlack(),governed_recovery=True)
    service.status_path.parent.mkdir(parents=True)
    held={'state':'BLOCKED_HOLD','mission_id':M,'generation':'g1','blocker_fingerprint':'f'*64,'reason':'synthetic-credit-hold'}
    service.status_path.write_text(json.dumps(held))
    monkeypatch.setattr('modules.charlie.native_runner.service.run_argv',lambda *a,**k:SimpleNamespace(returncode=0,stdout=REV))
    resumed=service.resume_from_owner_grant()
    assert resumed['preserved_hold']==held
    claim=service.recovery.proof['claim_id']
    native=api.mission(M)['mission']['metadata']['hermes_native_execution']
    assert native['worker_claim_id']==claim
    # Labelled fake physical model request; no inference/network.
    calls=[]
    intent={'provider':'labelled-fake-provider','model':'fake-only','request_sha256':'a'*64}
    service.recovery.perform('model',intent,lambda:calls.append('fake-builder') or {'id':'fake-request','patch':'simulated'},
        lambda r,i:{'intent_sha256':digest(i),'request_id':r['id'],'response_sha256':digest(r),
                    'provider':i['provider'],'model':i['model']})
    candidate={'pr_number':17,'head_sha':'c'*40,'candidate_diff_sha256':'d'*64,'changed_files':['demo.py']}
    service._record_progress(M,{'native_execution_id':native['native_execution_id'],'execution_status':'PACKAGED',
                               'event':'native_packaged',**candidate},claim_id=claim)
    native={**native,**candidate}
    mission=api.mission(M)['mission']
    binding=binding_from_authority(mission,native)
    assert api.bind_candidate(M,binding)['binding']==binding
    assert api.bind_candidate(M,binding)['acknowledgement']=='exact_replay'
    expected={k:binding[k] for k in ('pr_number','base_sha','head_sha','candidate_diff_sha256','changed_files')}
    reviews={f'review_{role}':{'verdict':'APPROVE','reviewer_identity':'HNR-LABELLED-FAKE-'+role,
        'reviewer_task':'charlie_native_'+role+'_reviewer','candidate_binding':expected,'packet_sha256':'9'*64}
        for role in ('security','functional')}
    service._record_progress(M,{'native_execution_id':native['native_execution_id'],'execution_status':'CHECKS_PENDING',
        'correction_rounds':1,'event':'synthetic_review_fixtures_only',**reviews},claim_id=claim)
    mission=api.mission(M)['mission'];native=mission['metadata']['hermes_native_execution']
    if lost_release_ack:
        original=api.client.opener
        def lose_release(req,**kw):
            response=original(req,**kw)
            if req.full_url.endswith('/release'):
                raise TimeoutError('synthetic lost release acknowledgement after commit')
            return response
        api.client.opener=lose_release
    outcome=service._supervise(mission,native)
    assert outcome['state']=='OWNER_DECISION_REQUIRED'
    final=plane.metadata();assert final['hermes_native_execution']['worker_claim_id']==''
    assert final['native_recovery']['lease']['released'] is True
    assert final['native_recovery']['requests']==1 and len(calls)==1 and len(messages)==2
    release=final['native_recovery']['release']
    if lost_release_ack:api.client.opener=original
    assert api.recovery(M,'release',release)['lease']['released'] is True
    assert len(messages)==2 and final['native_runner_blocker']==metadata['native_runner_blocker']
    # Crash after DB release, before local completion: read-only reconciliation.
    events=len(plane.sql('select * from charlie_mission_events'))
    service.status_path.write_text(json.dumps(held));service._held_status=dict(held)
    service._resume_session=None
    reconciled=service.resume_from_owner_grant()
    assert reconciled['state']=='OWNER_DECISION_REQUIRED' and service.recovery is None
    assert reconciled['preserved_hold']==held and len(messages)==2
    assert len(plane.sql('select * from charlie_mission_events'))==events


def test_actual_httpx_redirect_and_retry_are_bounded(plane,monkeypatch):
    import httpx
    from modules.charlie.native_runner.request_guard import physical_request_guard
    from modules.charlie.native_runner.recovery_session import RecoverySession
    from modules.charlie.native_runner.execution import NativeExecutionError
    http,api=http_plane(plane,monkeypatch)
    grant=plane.grant();grant['limits']={'requests':2,'spend_microusd':100000,'per_request_microusd':50000}
    grant['pricing_ceiling']={'provider':'openrouter','model':'openai/gpt-5-mini','input_microusd_per_token':1,
        'output_microusd_per_token':2,'evidence_sha256':'8'*64,'expires_at':grant['expires_at']}
    response=http.post(f'/api/charlie/build-relay/missions/{M}/native-runner/resume',json=grant,
                       headers={'X-CHARLIE-Owner-Action':'native_runner_resume'});assert response.status_code==201
    recovery=RecoverySession(api,M,incarnation='transport-boot')
    recovery.consume({'generation':'g1','blocker_fingerprint':'f'*64},worker_revision=REV)
    requests=[]
    def transport(req):
        requests.append(str(req.url))
        return httpx.Response(307,headers={'location':'https://different.invalid/paid-endpoint'},json={'id':'fake-redirect'})
    with httpx.Client(transport=httpx.MockTransport(transport),follow_redirects=True) as client:
        with physical_request_guard(recovery,'openrouter','openai/gpt-5-mini'):
            with pytest.raises(NativeExecutionError):
                client.post('https://openrouter.ai/api/v1/chat/completions',json={
                    'model':'openai/gpt-5-mini','messages':[{'role':'user','content':'synthetic'}],'max_tokens':64})
    assert requests==['https://openrouter.ai/api/v1/chat/completions']
    assert plane.metadata()['native_recovery']['requests']==1
    assert next(iter(plane.metadata()['native_recovery']['effects'].values()))['state']=='prepared'


def test_owner_can_record_old_exact_readback_after_new_hold(plane):
    proof=plane.lease();assert plane.call('reserve',effect(proof))[1]==201
    plane.sql("update charlie_missions set metadata_json=jsonb_set(metadata_json,'{native_runner_blocker,blocker_fingerprint}',%s::jsonb)",
              (json.dumps('e'*64),))
    assert plane.call('check',{'proof':proof})[1]==409
    payload={'effect_id':'effect-1','prior_state_sha256':digest(plane.metadata()['native_recovery']),
             'evidence':model_receipt(proof)['evidence']}
    assert plane.call('reconcile',payload,'owner-admin:signed')[1]==201
    assert plane.call('check',{'proof':proof})[1]==409
    assert plane.metadata()['native_recovery']['requests']==1


def test_real_database_expiry_veto(plane):
    grant=plane.grant();grant['expires_at']=(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat()
    r,c=plane.call('issue',grant,'owner-admin:signed');assert c==201
    payload={'grant_id':r['receipt']['grant']['grant_id'],'request_id':'consume-short','incarnation':'short-boot'}
    r,c=plane.call('consume',payload);assert c==201
    proof={k:r['receipt']['lease'][k] for k in ('grant_id','incarnation','epoch','claim_id')}
    plane.sql('select pg_sleep(1.1)')
    r,c=plane.call('reserve',effect(proof));assert c==409 and r['status']=='native_recovery_authority_expired'
    assert plane.metadata()['native_recovery']['requests']==0


def test_projection_update_failure_rolls_back_inserted_checkpoint(plane):
    plane.sql("""create or replace function test_recovery_update_fail() returns trigger language plpgsql as $$
        begin raise exception 'synthetic update interruption'; end $$""")
    plane.sql('create trigger recovery_test_update_fail before update on charlie_missions for each row execute function test_recovery_update_fail()')
    r,c=plane.call('issue',plane.grant(),'owner-admin:signed')
    assert c==503 and 'native_recovery' not in plane.metadata()
    assert plane.sql('select * from charlie_mission_events')==[]


def test_native_mutation_veto_inside_transaction_after_owner_hold(plane,monkeypatch):
    native={'mission_id':M,'native_execution_id':'HNX-LOCK-TEST','generation':'g1','status':'valid',
        'branch':'charlie/lock-native-1','worktree_digest':'e'*64,'starting_main_sha':REV,
        'owner_instruction_digest':'b'*64,'allowed_files':['demo.py'],'allowed_effects':['edit_allowed_files'],
        'execution_status':'RUNNING','expires_at':(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()}
    metadata=plane.metadata();metadata['hermes_native_execution']=native
    plane.sql('update charlie_missions set metadata_json=%s::jsonb',(json.dumps(metadata),))
    proof=plane.lease()
    http,api=http_plane(plane,monkeypatch);api.recovery_proof=proof
    # The HTTP preflight succeeds; an owner hold is inserted before the actual
    # progress function locks/reads its row. The inner guard must still veto.
    assert api.recovery(M,'check',{'proof':proof})['lease']['claim_id']==proof['claim_id']
    plane.add_hold('new-hold')
    before=plane.metadata()
    payload={'native_execution_id':native['native_execution_id'],'worker_claim_id':proof['claim_id'],
             'event':'native_packaged','execution_status':'PACKAGED','recovery_proof':proof}
    r,c=plane.store['record_hermes_native_execution_state'](M,payload,authenticated_principal='hermes:charlie-builder')
    assert c==423 and plane.metadata()==before


def test_regrant_atomically_transfers_exact_retained_claim_and_renews_native(plane):
    native={'mission_id':M,'native_execution_id':'HNX-TRANSFER-TEST','generation':'g1','status':'valid',
        'branch':'charlie/transfer-native-1','worktree_digest':'e'*64,'starting_main_sha':REV,
        'owner_instruction_digest':'b'*64,'allowed_files':['demo.py'],'allowed_effects':['edit_allowed_files'],
        'execution_status':'RUNNING','expires_at':(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()}
    metadata=plane.metadata();metadata['hermes_native_execution']=native
    plane.sql('update charlie_missions set metadata_json=%s::jsonb',(json.dumps(metadata),))
    old=plane.lease()
    assert plane.metadata()['hermes_native_execution']['worker_claim_id']==old['claim_id']
    grant=plane.grant();grant.update(request_id='OWNER-TRANSFER',prior_state_sha256=digest(plane.metadata()['native_recovery']))
    result,code=plane.call('issue',grant,'owner-admin:signed');assert code==201,result
    result,code=plane.call('consume',{'grant_id':result['receipt']['grant']['grant_id'],
                                    'request_id':'consume-new-boot','incarnation':'new-boot'})
    assert code==201,result
    updated=plane.metadata()['hermes_native_execution']
    assert updated['native_execution_id']==native['native_execution_id']
    assert updated['worker_claim_id']!=old['claim_id'] and updated['expires_at']==grant['expires_at']
    assert plane.call('check',{'proof':old})[1]==409


def test_legacy_allocation_and_native_consume_serialize_across_connections(plane):
    plane.sql("insert into charlie_missions(mission_id,status,raw_text,title,urgency,mission_type,approval_level,metadata_json)values('LEGACY-TEST','in_progress','synthetic','synthetic','normal','software','owner','{}')")
    result,code=plane.call('issue',plane.grant(),'owner-admin:signed');assert code==201
    grant_id=result['receipt']['grant']['grant_id'];barrier=threading.Barrier(2)
    def native():
        barrier.wait()
        return plane.call('consume',{'grant_id':grant_id,'request_id':'consume-race','incarnation':'native-boot'})
    def legacy():
        barrier.wait()
        return plane.store['update_mission_vault']('LEGACY-TEST',{'execution_lease':{'lease_id':'legacy-lease'}})
    with ThreadPoolExecutor(2) as pool:
        a,b=pool.submit(native),pool.submit(legacy);results=[a.result(),b.result()]
    assert sum(c in {200,201} for _,c in results)==1,results
    assert sum(c==409 for _,c in results)==1,results


def synthetic_session(plane,monkeypatch,*,pricing=False):
    from modules.charlie.native_runner.recovery_session import RecoverySession
    http,api=http_plane(plane,monkeypatch)
    grant=plane.grant()
    if pricing:
        grant['limits']={'requests':2,'spend_microusd':100000,'per_request_microusd':50000}
        grant['pricing_ceiling']={'provider':'openrouter','model':'openai/gpt-5-mini','input_microusd_per_token':1,
            'output_microusd_per_token':2,'evidence_sha256':'8'*64,'expires_at':grant['expires_at']}
    response=http.post(f'/api/charlie/build-relay/missions/{M}/native-runner/resume',json=grant,
                       headers={'X-CHARLIE-Owner-Action':'native_runner_resume'})
    assert response.status_code==201,response.json
    session=RecoverySession(api,M,incarnation='synthetic-http-boot')
    session.consume({'generation':'g1','blocker_fingerprint':'f'*64},worker_revision=REV)
    api.recovery_proof=session.proof
    return http,api,session


@pytest.mark.parametrize('fault',['none','n','multimodal','async','transport-retry','unknown-transport','fallback',
                                'plugins','web-search','models','provider-routing','conflicting-output','message-extra'])
def test_physical_httpx_success_and_denials(plane,monkeypatch,fault):
    import asyncio,httpx
    from modules.charlie.native_runner.request_guard import physical_request_guard
    from modules.charlie.native_runner.execution import NativeExecutionError
    _,_,session=synthetic_session(plane,monkeypatch,pricing=True)
    calls=[]
    def fake(req):calls.append(req);return httpx.Response(200,json={'id':'labelled-fake-request'})
    payload={'model':'openai/gpt-5-mini','messages':[{'role':'user','content':'synthetic'}],'max_tokens':64}
    if fault=='n':payload['n']=2
    if fault=='multimodal':payload['messages'][0]['content']=[{'type':'image_url','image_url':{'url':'https://example.invalid'}}]
    if fault=='plugins':payload['plugins']=[{'id':'web'}]
    if fault=='web-search':payload['web_search_options']={'search_context_size':'high'}
    if fault=='models':payload['models']=['unapproved/expensive']
    if fault=='provider-routing':payload['provider']={'order':['unapproved']}
    if fault=='conflicting-output':payload['max_completion_tokens']=999999
    if fault=='message-extra':payload['messages'][0]['tool_calls']=[{'function':{'name':'unapproved'}}]
    transport=httpx.MockTransport(fake)
    if fault=='transport-retry':transport=httpx.HTTPTransport(retries=1)
    if fault=='unknown-transport':
        class Unknown(httpx.BaseTransport):
            def handle_request(self,req):pytest.fail('unknown transport executed')
        transport=Unknown()
    url='https://example.invalid/fallback' if fault=='fallback' else 'https://openrouter.ai/api/v1/chat/completions'
    with physical_request_guard(session,'openrouter','openai/gpt-5-mini'):
        if fault=='async':
            async def send():
                async with httpx.AsyncClient(transport=transport) as client:await client.post(url,json=payload)
            with pytest.raises(NativeExecutionError):asyncio.run(send())
        else:
            with httpx.Client(transport=transport) as client:
                if fault=='none':assert client.post(url,json=payload).status_code==200
                else:
                    with pytest.raises(NativeExecutionError):client.post(url,json=payload)
    state=plane.metadata()['native_recovery']
    assert len(calls)==(1 if fault=='none' else 0)
    assert state['requests']==len(calls)
    assert all(e['state']=='confirmed' for e in state['effects'].values())


@pytest.mark.parametrize('held_generation',['','wrong-generation'])
def test_historical_blank_generation_and_changed_worker_revision(plane,monkeypatch,held_generation):
    from modules.charlie.native_runner.recovery_session import RecoverySession
    from modules.charlie.native_runner.execution import NativeExecutionError
    metadata=plane.metadata();metadata['native_runner_blocker']['generation']=''
    plane.sql('update charlie_missions set metadata_json=%s::jsonb',(json.dumps(metadata),))
    http,api=http_plane(plane,monkeypatch)
    grant=plane.grant();grant['scope']['runtime']['worker_revision']='c'*40
    response=http.post(f'/api/charlie/build-relay/missions/{M}/native-runner/resume',json=grant,
                       headers={'X-CHARLIE-Owner-Action':'native_runner_resume'})
    assert response.status_code==201,response.json
    session=RecoverySession(api,M)
    held={'generation':held_generation,'blocker_fingerprint':'f'*64}
    if held_generation:
        with pytest.raises(NativeExecutionError):session.consume(held,worker_revision='c'*40)
        assert 'lease' not in plane.metadata()['native_recovery']
    else:assert session.consume(held,worker_revision='c'*40)['lease']['released'] is False
    assert plane.metadata()['native_runner_blocker']==metadata['native_runner_blocker']


def test_prior_pda_base_retained_and_exact_current_base_approved(plane):
    old='22ce27612458a3283c1c2fb5310a07f5e4066d86'
    plane.sql("update charlie_missions set metadata_json=jsonb_set(metadata_json,'{dispatch_authorization,base_sha}',%s::jsonb)",(json.dumps(old),))
    grant=plane.grant()
    assert grant['scope']['prior_dispatch_base_sha']==old and grant['scope']['starting_main_sha']==REV
    proof=plane.lease()
    plane.sql("update charlie_missions set metadata_json=jsonb_set(metadata_json,'{dispatch_authorization,base_sha}',%s::jsonb)",(json.dumps(REV),))
    assert plane.call('check',{'proof':proof})[1]==200
    assert plane.metadata()['native_recovery']['grant']['scope']['prior_dispatch_base_sha']==old


def test_confirmed_notification_regrant_readback_never_resends(plane,monkeypatch,tmp_path):
    from modules.charlie.native_runner.service import NativeRunnerService
    from modules.charlie.native_runner.recovery_session import RecoverySession
    metadata=plane.metadata();metadata['external_supervisor_state']={'slack_channel_id':'C-FAKE','slack_thread_ts':'100.001'}
    metadata['review_packet']={'candidate_revision':'b'*40,'pr_number':17,'branch_name':'charlie/fake'}
    plane.sql('update charlie_missions set metadata_json=%s::jsonb',(json.dumps(metadata),))
    http,api,session=synthetic_session(plane,monkeypatch)
    service=object.__new__(NativeRunnerService);service.recovery=session
    calls=[]
    service.notifier=SimpleNamespace(post=lambda *a,**k:calls.append(k),
        lookup=lambda channel,**k:{'channel':channel,'ts':'200.001',**k})
    service._owner_notification('original_thread','b'*40,'C-FAKE','simulated',thread_ts='100.001',idempotency_key='same-head')
    state=plane.metadata()['native_recovery'];grant=plane.grant();grant.update(request_id='OWNER-RESTART',prior_state_sha256=digest(state))
    assert plane.call('issue',grant,'owner-admin:synthetic-signed')[1]==201
    service.recovery=RecoverySession(api,M,incarnation='restarted-boot')
    service.recovery.consume({'generation':'g1','blocker_fingerprint':'f'*64},worker_revision=REV)
    service._owner_notification('original_thread','b'*40,'C-FAKE','simulated',thread_ts='100.001',idempotency_key='same-head')
    assert len(calls)==1 and len(plane.metadata()['native_recovery']['effects'])==1


@pytest.mark.parametrize('fault',['none','wrong-pr','wrong-head','no-reservation','repeat'])
def test_actual_admission_handler_requires_exact_once_only_intent(plane,monkeypatch,fault):
    from modules.charlie.native_runner.execution import NativeExecutionError
    metadata=plane.metadata();metadata['review_packet']={'candidate_revision':'b'*40,'pr_number':17,'branch_name':'charlie/fake'}
    plane.sql('update charlie_missions set metadata_json=%s::jsonb',(json.dumps(metadata),))
    _,api,session=synthetic_session(plane,monkeypatch)
    calls=[]
    class Ack:
        status=204
        def __enter__(self):return self
        def __exit__(self,*_):pass
    monkeypatch.setattr(urllib.request,'urlopen',lambda *a,**k:calls.append('fake-issuer') or Ack())
    identity={'operation':'admission_dispatch','mission_id':M,'head_sha':'b'*40,'pr_number':17}
    call=lambda:api.request_admission(M,'c'*40 if fault=='wrong-head' else 'b'*40,18 if fault=='wrong-pr' else 17)
    if fault=='no-reservation':
        with pytest.raises(NativeExecutionError):call()
    else:
        def perform():
            result=call()
            if fault=='repeat':
                with pytest.raises(NativeExecutionError):call()
            return result
        if fault in {'wrong-pr','wrong-head'}:
            with pytest.raises(NativeExecutionError):session.perform('canonical',{'identity':identity},perform,lambda *_:{})
        else:
            session.perform('canonical',{'identity':identity},perform,
                lambda r,i:{'intent_sha256':digest(i),'identity':identity,'result_sha256':digest(r)})
    assert len(calls)==(1 if fault in {'none','repeat'} else 0)


@pytest.mark.parametrize('fault',['worktree','forbidden-files','forbidden-effects','first-contract-forbidden'])
def test_native_execution_and_forbidden_contract_cannot_drift(plane,fault):
    metadata=plane.metadata()
    metadata['hermes_native_execution']={'mission_id':M,'native_execution_id':'HNX-SYNTHETIC',
        'generation':'g1','worktree_digest':'e'*64,'branch':'charlie/fake','starting_main_sha':REV,
        'forbidden_files':['.env*'],'forbidden_effects':['merge','deploy']}
    plane.sql('update charlie_missions set metadata_json=%s::jsonb',(json.dumps(metadata),))
    proof=plane.lease();metadata=plane.metadata()
    if fault=='worktree':metadata['hermes_native_execution']['worktree_digest']='d'*64
    if fault=='forbidden-files':metadata['hermes_native_execution']['forbidden_files']=['wrong']
    if fault=='forbidden-effects':metadata['hermes_native_execution']['forbidden_effects']=['wrong']
    if fault=='first-contract-forbidden':
        metadata['mission_admission_contract']={'base_sha':REV,'generation':'g1','branch':'charlie/fake',
            'allowed_files':['demo.py'],'allowed_effects':['edit_allowed_files'],
            'forbidden_files':['wrong'],'forbidden_effects':['merge','deploy'],
            'required_tests':['synthetic-contract'],'operational_acceptance':['synthetic outcome']}
    plane.sql('update charlie_missions set metadata_json=%s::jsonb',(json.dumps(metadata),))
    result,code=plane.call('check',{'proof':proof})
    assert code==409,result
    assert plane.call('reserve',effect(proof))[1]==409
    assert not plane.metadata()['native_recovery']['effects']


def test_native_adapter_cap_survives_actual_pinned_hermes_kwargs_to_transport(plane,monkeypatch,tmp_path):
    """Actual pinned function body; provider helpers/SDK response are labelled fakes."""
    import httpx,sys,types,typing
    from contextlib import nullcontext
    from modules.charlie.native_runner.model_adapter import HermesAuxiliaryModel,run_schema_canary
    pinned=Path(os.environ['CHARLIE_PINNED_AUXILIARY_SOURCE'])
    data=pinned.read_bytes()
    assert hashlib.sha256(data).hexdigest()=='7557bf020a4e93251fe15d46b6d28597a5813bca86aae37e8b53913e255498b5'
    node=next(n for n in ast.parse(data.decode('utf8')).body if isinstance(n,ast.FunctionDef) and n.name=='_build_call_kwargs')
    omitted=object()
    scope={'Optional':typing.Optional,'Any':typing.Any,'Dict':dict,'OMIT_TEMPERATURE':omitted,
        '_fixed_temperature_for_model':lambda *a:omitted,'base_url_host_matches':lambda *a:False,
        '_is_anthropic_compat_endpoint':lambda *a:False,'_contains_profile_reasoning_fields':lambda *a:False,
        'logger':SimpleNamespace(debug=lambda *a:None)}
    providers=types.ModuleType('providers');providers.__path__=[];providers.get_provider_profile=lambda _:None
    base=types.ModuleType('providers.base');base.ProviderProfile=type('LabelledFakeProfile',(),{})
    agent=types.ModuleType('agent');agent.__path__=[]
    gemini=types.ModuleType('agent.gemini_native_adapter');gemini.is_native_gemini_base_url=lambda _:False
    for name,module in [('providers',providers),('providers.base',base),('agent',agent),('agent.gemini_native_adapter',gemini)]:
        monkeypatch.setitem(sys.modules,name,module)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(pinned),'exec'),scope)
    build=scope['_build_call_kwargs']
    old=build('openrouter','openai/gpt-5-mini',[{'role':'user','content':'synthetic'}],max_tokens=64,
              task='charlie_native_builder',base_url='https://openrouter.ai/api/v1')
    assert 'max_tokens' not in old and 'max_completion_tokens' not in old
    _,_,session=synthetic_session(plane,monkeypatch,pricing=True)
    requests=[]
    def transport(req):
        requests.append(json.loads(req.content))
        return httpx.Response(200,json={'id':'labelled-fake-pinned-request','choices':[{'message':{'content':'{"status":"READY"}'}}]})
    def call(**kw):
        route=kw.pop('route_info');route.update(provider=kw['provider'],model=kw['model'])
        wire=build(**kw,base_url='https://openrouter.ai/api/v1')
        assert 'max_tokens' not in wire  # Pinned helper still drops the ordinary kwarg.
        body={k:v for k,v in wire.items() if k not in {'timeout','extra_body'}}
        body.update(wire.get('extra_body') or {})  # Explicit simulated SDK extra_body merge.
        with httpx.Client(transport=httpx.MockTransport(transport)) as client:
            response=client.post('https://openrouter.ai/api/v1/chat/completions',json=body)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=response.json()['choices'][0]['message']['content']))])
    call.__module__='agent.auxiliary_client'  # Exercise production guard, with fake wire I/O.
    model=HermesAuxiliaryModel(profile_home=tmp_path,call=call);model.recovery=session
    monkeypatch.setattr(model,'_profile_scope',lambda:nullcontext())
    assert run_schema_canary(model)['status']=='READY'
    assert len(requests)==1 and requests[0]['max_tokens']==64 and 'max_completion_tokens' not in requests[0]
    state=plane.metadata()['native_recovery']
    assert state['requests']==1 and next(iter(state['effects'].values()))['state']=='confirmed'
