"""Unseeded pre-HNX journey: real Flask/store/Postgres/Git, fake external I/O.

This is an installed Linux qualification. No real provider is called and every
review verdict below is a labelled simulation, never a pilot approval.
"""
import base64,copy,difflib,hashlib,hmac,io,json,os,re,shutil,subprocess,urllib.error,urllib.parse,urllib.request
from datetime import datetime,timedelta,timezone
from pathlib import Path
from types import SimpleNamespace
import pytest
from flask import Blueprint,Flask,jsonify,request
from tests.test_charlie_native_recovery_transactions import load
from modules.charlie.native_runner.diagnostics import PILOT,DESTINATIONS
from modules.charlie.native_runner.recovery import scope_for,digest
from modules.charlie.native_runner.service import NativeRunnerService,REQUIRED_NAMES
from modules.charlie.native_runner.execution import NativeExecutionError

REPO='Crewless9086/amadeus-pig-tracking-system'
G='slack-1787929390.145099-g1'
A='bc-c204af55-96c2-5992-b77d-0e95b585abd8';R='run-8b61a929-24e2-407c-9408-28518a2377b1'
FILE='docs/06-operations/HERMES_SUPERVISOR_BRIDGE.md'
TOKEN='test-only-worker-token-'+'x'*32
ROOT=Path(__file__).resolve().parents[1]


def git(root,*args):
    p=subprocess.run(['git',*args],cwd=root,capture_output=True,text=True)
    assert p.returncode==0,p.stderr
    return p.stdout.strip()


@pytest.fixture
def journey(tmp_path,monkeypatch):
    assert os.environ.get('CHARLIE_TEST_POSTGRES_DISPOSABLE')=='1'
    import psycopg
    from modules.charlie import mission_store as store
    from modules.auth import owner_access
    from modules.charlie.execution_bridge import build_hermes_native_execution_context
    dsn=os.environ['CHARLIE_TEST_POSTGRES_DSN'];assert dsn.startswith('host=127.0.0.1 ') and 'user=native_recovery_test ' in dsn
    from tests.test_charlie_native_database_privileges import initialize_privilege_database
    admin_dsn=os.environ['CHARLIE_TEST_POSTGRES_ADMIN_DSN'].replace('dbname=charlie_roles_test ', 'dbname=charlie_runtime_test ')
    app_dsn=initialize_privilege_database(admin_dsn)
    monkeypatch.setenv('CHARLIE_MISSION_DATABASE_URL',app_dsn)
    def sql(command,params=()):
        with psycopg.connect(admin_dsn) as c:
            with c.cursor() as q:
                q.execute(command,params);return q.fetchall() if q.description else None
    primary=tmp_path/'primary';primary.mkdir();bare=tmp_path/'fake-origin.git'
    # Real source/governance context, real declared verification; no hand-built prompt.
    for folder in ('docs','modules','services','scripts','tests','integrations','utils','config'):
        if (ROOT/folder).exists():shutil.copytree(ROOT/folder,primary/folder,ignore=shutil.ignore_patterns('__pycache__'))
    # Match a Linux Git checkout of text blobs, not Windows checkout CRLF bytes.
    for p in primary.rglob('*'):
        if p.is_file():p.write_bytes(p.read_bytes().replace(b'\r\n',b'\n'))
    git(primary,'init','-b','main');git(primary,'config','user.name','Synthetic qualification')
    git(primary,'config','user.email','qualification@example.invalid')
    git(primary,'add','.');git(primary,'commit','-qm','Disposable qualification base')
    rev=git(primary,'rev-parse','HEAD');git(tmp_path,'init','--bare',str(bare))
    git(primary,'remote','add','origin','https://github.com/'+REPO+'.git')
    git(primary,'config','remote.origin.pushurl',str(bare))
    instruction='Synthetic offline documentation qualification; no operational authority.'
    metadata={'external_supervisor_state':{'cursor_agent_id':A,'cursor_run_id':R,'generation':G,'execution_attempt':5,
        'branch':'cursor/charlie-mission-setup-fb0a','agent_state':'ACTIVE','run_state':'RUNNING',
        'repository_mutation':False,'remote_branch_created':False,'pr_number':0,'head_sha':'','exact_candidate':'absent',
        'slack_owner_user_id':'U-TEST-OWNER','slack_channel_id':DESTINATIONS['thread'][0],
        'slack_thread_ts':DESTINATIONS['thread'][1],'slack_event_id':'1787929390.145099'},
        'execution_succession':{'active_attempt':5},'slack_approval_channel_id':DESTINATIONS['approvals'][0],
        'mission_vault':{'problem_statement':instruction,'test_plan':['actual-supervisor-unit-tests'],
            'acceptance_criteria':['Synthetic documentation change verified at exact head']},
        'dispatch_authorization':{'version':'charlie_pre_dispatch_authorization_v2','mission_id':PILOT,'status':'valid',
            'authorization_id':'PDA-HISTORICAL-TEST','generation':G,'execution_attempt':5,'repository':REPO,
            'base_sha':'2'*40,'starting_main_sha':'2'*40,'expires_at':'2000-01-01T00:00:00+00:00',
            'owner_instruction_digest':hashlib.sha256(instruction.encode()).hexdigest(),
            'allowed_files':list(store._HERMES_PILOT_ALLOWED_FILES),'allowed_effects':list(store._PDA_ALLOWED_EFFECTS),
            'forbidden_effects':list(store._PDA_FORBIDDEN_EFFECTS),'forbidden_files':['*']}}
    sql("insert into charlie_missions(mission_id,status,source,raw_text,title,urgency,mission_type,approval_level,metadata_json) values(%s,%s,%s,%s,%s,'normal','software','owner',%s::jsonb)",
        (PILOT,'in_progress','slack',instruction,'Synthetic native qualification',json.dumps(metadata)))
    settings={name:'test-only-'+name for name in REQUIRED_NAMES}
    settings.update(CHARLIE_CANONICAL_API_URL='https://canonical.test/api',CHARLIE_HERMES_GATEWAY_TOKEN=TOKEN,
        CHARLIE_SLACK_OWNER_USER_ID='U-TEST-OWNER',CHARLIE_SLACK_CHARLIE_CHANNEL_ID=DESTINATIONS['thread'][0],
        CHARLIE_SLACK_APPROVALS_CHANNEL_ID=DESTINATIONS['approvals'][0],RENDER_GIT_COMMIT=rev,
        CHARLIE_ADMISSION_ISSUER_GITHUB_TOKEN='test-only-issuer-'+('a'*40),
        CURSOR_API_KEY='test-only-cursor-key',OPENROUTER_API_KEY='test-only-openrouter-key',
        OWNER_ACCESS_ENABLED='1',OWNER_ACCESS_ALLOW_LOCAL_DEV='0',OWNER_ADMIN_TOKEN='test-only-owner-'+'x'*40,
        OWNER_READ_TOKEN='test-only-read-'+'y'*40,OWNER_SESSION_SECRET='test-only-session-'+'z'*40)
    for k,v in settings.items():monkeypatch.setenv(k,v)
    bp=Blueprint('unseeded',__name__)
    scope={**vars(store),'charlie_bp':bp,'request':request,'jsonify':jsonify,'hmac':hmac,'urllib':urllib,
        'env_value':lambda name:settings.get(name,''),'build_hermes_native_execution_context':build_hermes_native_execution_context,
        'require_strict_owner_admin_access':owner_access.require_strict_owner_admin_access,
        'strict_owner_admin_principal':owner_access.strict_owner_admin_principal}
    load(['_require_hermes_gateway_access','charlie_native_runner_resume_route','charlie_native_runner_recovery_operation_route',
        'charlie_native_recovery_effect_guard','charlie_hermes_native_execution_progress_route','charlie_hermes_mission_status_route',
        'charlie_native_runner_reconcile_effect_route','charlie_external_supervisor_candidate_route','charlie_hermes_mission_admission_route',
        'charlie_hermes_native_recovery_route','charlie_hermes_writer_count_route','charlie_hermes_native_context_route',
        'charlie_hermes_cursor_retirement_route','charlie_hermes_dispatch_authorization_route','charlie_hermes_native_execution_route',
        'charlie_protected_admission_record_route','charlie_hermes_native_runner_blocker_route'], 'modules/charlie/routes.py',scope)
    app=Flask('unseeded');app.testing=True;owner_access.configure_owner_access(app);app.register_blueprint(bp,url_prefix='/api')
    http=app.test_client();worker_http=app.test_client()
    with http.session_transaction() as session:session['owner_access']={'role':'admin','principal_id':owner_access._stable_owner_principal('admin')}
    state=SimpleNamespace(sql=sql,store=store,http=http,settings=settings,primary=primary,bare=bare,rev=rev,
        calls=[],agent='ACTIVE',run='RUNNING',messages=[],pulls=[],models=[],admitted=set(),phases=[],lose_ack=False,lost=set(),verifications=[])
    state.metadata=lambda:sql('select metadata_json from charlie_missions where mission_id=%s',(PILOT,))[0][0]
    split_plane=None
    from modules.charlie.native_runner import execution
    original_run=execution.run_argv
    def observed_run(argv,**kwargs):
        result=original_run(argv,**kwargs)
        if argv[:3]==['python','-m','unittest']:
            from modules.charlie.native_runner.review_packet import verification_snapshot
            state.verifications.append({'argv':list(argv),'resolved_application_python':shutil.which('python'),
                'returncode':result.returncode,'stdout':result.stdout,'stderr':result.stderr,
                'head_before_packaging':git(kwargs['cwd'],'rev-parse','HEAD'),
                'tested_candidate':verification_snapshot(kwargs['cwd'],rev)})
        if argv[:3]==['python','-m','unittest'] and result.returncode:print('REAL VERIFICATION FAILURE:',result.stdout,result.stderr)
        return result
    monkeypatch.setattr(execution,'run_argv',observed_run)
    def pull():
        p=state.pulls[0];branch=p['head']['ref'];p['head']['sha']=git(bare,'rev-parse','refs/heads/'+branch)
        return copy.deepcopy(p)
    def issue(head):
        from scripts import charlie_mission_admission_guard as guard
        from modules.charlie.mission_admission import sign_mission_admission_receipt
        from modules.charlie.validation_receipt import canonical_json
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives import serialization
        key=Ed25519PrivateKey.generate()
        monkeypatch.setattr(guard,'EXTERNAL_ADMISSION_PUBLIC_KEY_B64',base64.b64encode(key.public_key().public_bytes(
            serialization.Encoding.Raw,serialization.PublicFormat.Raw)).decode())
        if split_plane:
            split_plane['key'].write_text(guard.EXTERNAL_ADMISSION_PUBLIC_KEY_B64)
        monkeypatch.setattr(guard,'REPO_ROOT',primary)
        mission,code=store.get_mission(PILOT);assert code==200,mission
        authority,code=store.read_current_mission_admission_authority(PILOT);assert code==200,authority
        m=mission['mission'];meta=m['metadata'];p=meta['review_packet'];contract=meta['mission_admission_contract']
        payload=guard._build_exact_candidate_payload(mission=m,family=meta['mission_family'],authority=authority,contract=contract,
            base=rev,head=head,branch=contract['branch'],diff_sha256=p['candidate_diff_sha256'],changed_files=p['changed_files'],
            governance_reads=guard._governance_read_identities(rev),repository=REPO)
        receipt=sign_mission_admission_receipt(payload,b'test-only-hmac-key-00000000000000000000000000')
        envelope={'version':'mission_admission_ci_envelope_v1','receipt':receipt,
            'signature_ed25519':base64.b64encode(key.sign(canonical_json(receipt))).decode()}
        response=http.post(f'/api/charlie/hermes/missions/{PILOT}/protected-admission',json={'envelope':envelope,'pr_number':1})
        assert response.status_code in {200,201},response.json
        state.admitted.add(head)
    def opened(req,timeout=30):
        parsed=urllib.parse.urlparse(req.full_url);body=json.loads(req.data) if req.data else {};query=urllib.parse.parse_qs(parsed.query)
        state.calls.append({'method':req.get_method(),'host':parsed.hostname,'path':parsed.path,'body':body})
        status=200
        if parsed.hostname=='canonical.test':
            response=worker_http.open(parsed.path+('?' + parsed.query if parsed.query else ''),method=req.get_method(),headers=dict(req.header_items()),data=req.data)
            status=response.status_code;value=response.json
        elif parsed.hostname=='api.cursor.com':
            assert req.get_header('Authorization')=='Bearer test-only-cursor-key'
            if parsed.path==f'/v1/agents/{A}' and req.get_method()=='GET':value={'id':A,'status':state.agent,'latestRunId':R}
            elif parsed.path==f'/v1/agents/{A}/runs/{R}' and req.get_method()=='GET':value={'id':R,'agentId':A,'status':state.run}
            elif parsed.path==f'/v1/agents/{A}/runs/{R}/cancel' and req.get_method()=='POST':state.run='CANCELLED';value={'id':R}
            elif parsed.path==f'/v1/agents/{A}/archive' and req.get_method()=='POST':state.agent='ARCHIVED';value={'id':A}
            else:raise AssertionError('unexpected Cursor effect')
        elif parsed.hostname=='api.github.com':
            if '/git/ref/heads/' in parsed.path:
                branch=urllib.parse.unquote(parsed.path.split('/git/ref/heads/',1)[1])
                result=subprocess.run(['git','rev-parse','--verify','refs/heads/'+branch],cwd=bare,capture_output=True,text=True)
                if result.returncode:status=404;value={'message':'Not Found'}
                else:value={'ref':'refs/heads/'+branch,'object':{'sha':result.stdout.strip()}}
            elif parsed.path.endswith('/pulls') and req.get_method()=='GET':value=[pull()] if state.pulls else []
            elif parsed.path.endswith('/pulls') and req.get_method()=='POST':
                assert not state.pulls and body['draft'] is True and body['base']=='main'
                value={'number':1,'state':'open','draft':True,'html_url':'https://github.com/'+REPO+'/pull/1',
                    'head':{'ref':body['head'],'sha':git(bare,'rev-parse','refs/heads/'+body['head']),'repo':{'full_name':REPO}},
                    'base':{'ref':'main','sha':rev,'repo':{'full_name':REPO}}}
                state.pulls.append(value);status=201
            elif parsed.path.endswith('/pulls/1') and req.get_method()=='GET':value=pull()
            elif parsed.path.endswith('/dispatches') and req.get_method()=='POST':
                issue(body['inputs']['expected_head_sha']);status=204;value=None
            elif parsed.path.endswith('/check-runs'):
                from modules.charlie.native_runner.canonical_client import GitHubObserver
                head=parsed.path.split('/commits/')[1].split('/')[0]
                assert head in state.admitted
                value={'total_count':5,'check_runs':[{'id':100+i,'name':name,'head_sha':head,'status':'completed','conclusion':'success',
                    'details_url':'https://github.com/'+REPO+'/actions/runs/'+str(100+i),'app':{'id':4742997 if name=='mission-admission' else 15368}}
                    for i,name in enumerate(sorted(GitHubObserver.REQUIRED))]}
            else:raise AssertionError('unimplemented fake GitHub contract '+parsed.path)
        elif parsed.hostname=='slack.com':
            if parsed.path=='/api/chat.postMessage':
                message={**body,'ts':str(1900000000+len(state.messages))+'.000001'};state.messages.append(message)
                value={'ok':True,'channel':body['channel'],'ts':message['ts'],'message':message}
            elif parsed.path in {'/api/conversations.history','/api/conversations.replies'}:
                value={'ok':True,'has_more':False,'messages':[m for m in state.messages if m['channel']==query['channel'][0]]}
            else:raise AssertionError('unexpected Slack path')
        else:raise AssertionError('unexpected external host '+str(parsed.hostname))
        raw=json.dumps(value).encode()
        if status>=400:raise urllib.error.HTTPError(req.full_url,status,'labelled fixture response',{},io.BytesIO(raw))
        loss_key=parsed.path+(':'+body.get('channel','') if parsed.hostname=='slack.com' else '')
        if (state.lose_ack and req.get_method()=='POST' and loss_key not in state.lost
                and (parsed.path.endswith(('/consume','/external-candidate','/release','/cancel','/archive')) or parsed.path=='/api/chat.postMessage')):
            state.lost.add(loss_key)
            raise TimeoutError('synthetic lost acknowledgement after effect was recorded')
        response=io.BytesIO(raw);response.status=status;return response
    monkeypatch.setattr(urllib.request,'urlopen',opened)
    import httpx
    def physical(transport,req):
        body=json.loads(req.read());state.models.append(body)
        assert str(req.url)=='https://openrouter.ai/api/v1/chat/completions'
        assert req.headers['authorization']=='Bearer test-only-openrouter-key'
        if body['max_tokens']==64:content={'status':'READY'}
        elif body['response_format']['json_schema']['name']=='charlie.native.patch.v1':
            packet=json.loads(body['messages'][1]['content'])
            before=next(c['content'] for c in packet['context'] if c['path']==FILE)
            after=before.replace('QUALIFICATION_PENDING','QUALIFICATION_COMPLETE') if 'QUALIFICATION_PENDING' in before else before+'\nQUALIFICATION_PENDING\n'
            patch=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='a/'+FILE,tofile='b/'+FILE))
            content={'state':'PATCH_READY','context_paths':[],'unified_diff':patch,'test_proposal':['Run actual declared supervisor unit tests.'],'reason':'Synthetic fixture patch from supplied actual file content.'}
        else:
            packet=json.loads(body['messages'][1]['content'])
            challenge='challenge' in body['response_format']['json_schema']['name']
            serialized=json.dumps(packet)
            if challenge:
                assert 'QUALIFICATION_PENDING' in serialized
                content={'verdict':'SEND_BACK','findings':['Synthetic fixture finding: replace unfinished QUALIFICATION_PENDING marker with QUALIFICATION_COMPLETE.']}
            else:
                assert 'QUALIFICATION_COMPLETE' in serialized
                content={'verdict':'APPROVE','findings':[]}
        return httpx.Response(200,request=req,json={'id':'fake-model-'+str(len(state.models)),'object':'chat.completion','created':1,
            'model':'openai/gpt-5-mini','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':json.dumps(content)}}]})
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',physical)
    if os.environ.get('CHARLIE_TEST_SPLIT_APPLICATION_PLANE')=='1':
        from tests.test_charlie_native_application_plane import start_plane
        # Fixture/table setup stays with its synthetic owner. Actual handlers
        # execute in application Python through a distinct nonowner runtime role.
        sql('grant select,insert,update,delete on charlie_missions,charlie_mission_events,operational_events to service_role')
        sql('grant select on charlie_owner_execution_hold_events to service_role')
        split_plane=start_plane(tmp_path,settings,dsn,opened,http.get_cookie('session').value)
        http=state.http=split_plane['owner'];worker_http=split_plane['worker']
        state.application_identity=split_plane['identity']
    profile=tmp_path/'profile';profile.mkdir();(profile/'config.yaml').write_text('model:\n  provider: openrouter\n  default: openai/gpt-5-mini\n')
    state.service=NativeRunnerService(profile_home=profile,repository_root=primary,worktree_root=tmp_path/'worktrees',configuration_source='environment')
    assert state.service.governed_recovery
    try:
        yield state
    finally:
        if split_plane:
            from tests.test_charlie_native_application_plane import stop_plane
            stop_plane(split_plane)
    (tmp_path/'unseeded-evidence.json').write_text(json.dumps({'calls':state.calls,'metadata':state.metadata(),'models':state.models,
        'phases':state.phases,'lost_acknowledgements':sorted(state.lost),'fake_cursor_final':{'agent':state.agent,'run':state.run},
        'fake_pr_count':len(state.pulls),'fake_messages':state.messages,'admitted_heads':sorted(state.admitted),
        'application_identity':getattr(state,'application_identity',{'scope':'in-process legacy selected-handler fixture'}),
        'worker_interpreter':{'executable':__import__('sys').executable,'prefix':__import__('sys').prefix},
        'actual_verification_commands':state.verifications,
        'events':sql('select event_type,metadata_json from charlie_mission_events order by created_at'),
        'operational_events':sql('select event_type,payload_json from operational_events order by recorded_at')},indent=2,default=str))


def issue_grant(j):
    expiry=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat()
    grant={'request_id':'SYNTHETIC-OWNER-UNSEEDED-1','scope':scope_for(PILOT,j.metadata(),{'worker_revision':j.rev,'web_revision':j.rev}),
        'expires_at':expiry,'limits':{'requests':16,'spend_microusd':16000000,'per_request_microusd':1000000},
        'pricing_ceiling':{'provider':'openrouter','model':'openai/gpt-5-mini','input_microusd_per_token':1,'output_microusd_per_token':1,
            'evidence_sha256':digest('synthetic-price-evidence-not-a-live-tariff'),'expires_at':expiry},
        'verification':[{'name':'actual-supervisor-unit-tests','argv':['python','-m','unittest','tests.test_charlie_hermes_supervisor','-q']}]}
    response=j.http.post(f'/api/charlie/build-relay/missions/{PILOT}/native-runner/resume',json=grant,
        headers={'X-CHARLIE-Owner-Action':'native_runner_resume'})
    assert response.status_code==201,response.json
    return response.json


@pytest.mark.parametrize('lost_ack',[False,True])
def test_unseeded_held_to_owner_decision(journey,lost_ack):
    j=journey;s=j.service;j.lose_ack=lost_ack
    assert not set(j.metadata()) & {'cursor_provider_retirement','hermes_native_execution','review_packet','mission_admission','mission_admission_contract','native_recovery'}
    s._report_blocker(PILOT,'hermes_auxiliary_inference_failed',2)
    assert s._read_status()['state']=='BLOCKED_HOLD'
    assert len(j.messages)==2 and j.models==[] and j.agent=='ACTIVE' and j.run=='RUNNING'
    with pytest.raises(NativeExecutionError):s.once()
    issue_grant(j)
    assert s.canonical.resumable(),j.sql('select status,metadata_json from charlie_missions')
    for _ in range(8):
        result=s.once()
        j.phases.append(result.get('state'))
        if result.get('state')=='OWNER_DECISION_REQUIRED':break
    assert result['state']=='OWNER_DECISION_REQUIRED',result
    meta=j.metadata();native=meta['hermes_native_execution'];recovery=meta['native_recovery']
    assert j.agent=='ARCHIVED' and j.run=='CANCELLED'
    assert len(j.pulls)==1 and len(j.admitted)==2 and len(j.models)==6
    assert len(j.verifications)==2
    assert all(v['returncode']==0 and 'Ran 60 tests' in v['stdout']+v['stderr'] for v in j.verifications)
    # Verification precedes commit. Bind the tested actual content to each
    # later exact admitted head, rather than equating the pre-package HEAD.
    from modules.charlie.native_runner.protocol import canonical_candidate_diff
    admitted_content={}
    for head in j.admitted:
        paths=sorted(git(j.bare,'diff','--name-only',j.rev,head,'--').splitlines())
        patch=subprocess.run(['git','diff','--no-ext-diff','--no-textconv','--binary','--full-index',j.rev,head,'--'],
                             cwd=j.bare,capture_output=True,check=True).stdout
        admitted_content[head]={'base_sha':j.rev,'changed_files':paths,'candidate_diff_sha256':canonical_candidate_diff(paths,patch)}
    assert {json.dumps(v['tested_candidate'],sort_keys=True) for v in j.verifications}=={
        json.dumps(value,sort_keys=True) for value in admitted_content.values()}
    for verification in j.verifications:
        verification['admitted_head']=next(head for head,value in admitted_content.items() if value==verification['tested_candidate'])
    if os.environ.get('CHARLIE_TEST_SPLIT_APPLICATION_PLANE')=='1':
        assert all(v['resolved_application_python']=='/usr/local/bin/python' for v in j.verifications)
    assert native['execution_status']=='OWNER_DECISION_REQUIRED' and not native['worker_claim_id']
    assert recovery['lease']['released'] is True and recovery['requests']==6
    assert all(e['state']=='confirmed' for e in recovery['effects'].values())
    assert native['owner_notification_head']==native['head_sha'] and native['correction_rounds']==1
    assert len(j.messages)==4 and len({m['client_msg_id'] for m in j.messages})==4
    assert 'SEND_BACK' in j.phases and git(j.primary,'status','--porcelain')==''
    assert len(list((j.primary.parent/'worktrees').glob('*/'+G+'/native-1')))==1
    assert len([c for c in j.calls if c['host']=='api.github.com' and c['method']=='POST' and c['path'].endswith('/pulls')])==1
    assert len([c for c in j.calls if c['method']=='POST' and c['path'].endswith('/native-execution')])==1
    if lost_ack:assert len(j.lost)>=7


def test_new_blocker_invalidates_consumed_grant_through_real_store(journey):
    j=journey;s=j.service;s._report_blocker(PILOT,'first',2);issue_grant(j);s.resume_from_owner_grant()
    proof=copy.deepcopy(s.recovery.proof);old=j.metadata()['native_runner_blocker']['notification_identity']
    s._report_blocker(PILOT,'fresh execution failure',2)
    assert j.metadata()['native_runner_blocker']['notification_identity']!=old
    response=j.http.post(f'/api/charlie/hermes/missions/{PILOT}/native-runner/recovery/check',
        json={'proof':proof},headers={'Authorization':'Bearer '+TOKEN})
    assert response.status_code==409,response.json
    with pytest.raises(NativeExecutionError):s.resume_from_owner_grant()
    assert s._read_status()['state']=='BLOCKED_HOLD' and j.models==[] and not j.pulls
    assert not j.metadata().get('hermes_native_execution') and j.metadata()['native_recovery']['requests']==0
