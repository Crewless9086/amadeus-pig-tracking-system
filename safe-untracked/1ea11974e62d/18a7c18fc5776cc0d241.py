"""Production constructor and real JSON/Slack callers; external HTTP is fake."""
import io
import json
import urllib.error
import urllib.parse
from datetime import datetime,timedelta,timezone
from types import SimpleNamespace

import pytest

from modules.charlie.native_runner.diagnostics import PILOT,DESTINATIONS
from modules.charlie.native_runner.execution import NativeExecutionError
from modules.charlie.native_runner.service import NativeRunnerService,REQUIRED_NAMES


class FakeHTTP:
    """Labelled fake external I/O, with independent Slack delivery state."""
    def __init__(self):
        self.calls=[];self.messages=[];self.blockers=[];self.mode={};self.canonical_available=True

    def __call__(self,request,timeout):
        parsed=urllib.parse.urlparse(request.full_url)
        payload=json.loads(request.data) if request.data else {}
        query=urllib.parse.parse_qs(parsed.query)
        self.calls.append((request.method,parsed.hostname,parsed.path,payload))
        if parsed.hostname=='canonical.test':
            if not self.canonical_available:
                raise urllib.error.HTTPError(request.full_url,503,'fake unavailable',{},io.BytesIO(b'{}'))
            if request.method=='GET' and parsed.path.endswith('/missions/'+PILOT):
                value={'success':True,'status':'ok','mission':{'mission_id':PILOT,'metadata':{
                    'dispatch_authorization':{'generation':'synthetic-g1','authorization_id':'synthetic-PDA'}}}}
            elif parsed.path.endswith('/native-runner/blocker'):
                self.blockers.append(payload)
                value={'success':True,'status':'native_runner_blocker_recorded','blocker':payload}
            else:
                raise AssertionError('unexpected canonical effect: '+parsed.path)
        elif parsed.hostname=='slack.com':
            if parsed.path=='/api/chat.postMessage':
                channel=payload['channel'];mode=self.mode.get(channel)
                if mode=='rejected':
                    value={'ok':False,'error':'channel_not_found'}
                elif mode=='ambiguous':
                    raise TimeoutError('labelled fake unknown delivery')
                else:
                    message={**payload,'ts':str(1900000000+len(self.messages))+'.000001'}
                    self.messages.append(message)
                    if mode=='lost_ack':raise TimeoutError('labelled fake lost acknowledgement')
                    value={'ok':True,'channel':channel,'ts':message['ts'],'message':message}
                    if mode=='malformed_ack':value={'ok':True}
            elif parsed.path in {'/api/conversations.history','/api/conversations.replies'}:
                channel=query['channel'][0]
                value={'ok':True,'has_more':False,'messages':[m for m in self.messages
                    if m['channel']==channel and (not query.get('ts') or m.get('thread_ts')==query['ts'][0])]}
                if self.mode.get(channel)=='read_unavailable':raise TimeoutError('fake read unavailable')
            else:raise AssertionError('unexpected Slack endpoint')
        else:raise AssertionError('unexpected external host')
        response=io.BytesIO(json.dumps(value).encode());response.status=200
        return response


@pytest.fixture
def configured(tmp_path,monkeypatch):
    http=FakeHTTP();now=[datetime(2026,9,7,tzinfo=timezone.utc)]
    monkeypatch.setattr('urllib.request.urlopen',http)
    def make():
        for name in REQUIRED_NAMES:monkeypatch.setenv(name,'isolated-test-only-0000000000000000')
        monkeypatch.setenv('CHARLIE_CANONICAL_API_URL','https://canonical.test/api')
        monkeypatch.setenv('CHARLIE_SLACK_APPROVALS_CHANNEL_ID',DESTINATIONS['approvals'][0])
        class ForbiddenModel:
            def complete_structured(self,**kwargs):raise AssertionError('diagnostic model spending forbidden')
        service=NativeRunnerService(profile_home=tmp_path,repository_root=tmp_path/'primary-absent',
            worktree_root=tmp_path/'worktrees',configuration_source='environment',
            model=ForbiddenModel(),clock=lambda:now[0])
        assert service.governed_recovery is True
        return service
    return make,http,now


def assert_contained(service,http):
    status=service._read_status()
    assert status['state']=='BLOCKED_HOLD'
    assert status['repository_mutation'] is False and status['remote_mutation'] is False
    assert not service.repository_root.exists()
    assert not any('/recovery/' in p or 'native-execution' in p for _,_,p,_ in http.calls)
    for message in http.messages:
        assert (message['channel'],message.get('thread_ts','')) in DESTINATIONS.values()
        assert 'secret-reason' not in message['text']
    return status


def test_production_default_first_blocker_and_polling(configured):
    make,http,now=configured;service=make()
    for _ in range(5):service._report_blocker(PILOT,'secret-reason:credential',1)
    status=assert_contained(service,http)
    assert len(http.blockers)==1 and len(http.messages)==2
    assert status['blocker_notification_state']=='delivered'
    assert all(v['sends']==1 and v['reads']==0 for v in status['diagnostic_reports'][status['blocker_fingerprint']].values())


@pytest.mark.parametrize('authority',['absent','expired'])
def test_reporting_independent_of_execution_authority_and_restart(configured,authority):
    make,http,now=configured;service=make()
    if authority=='expired':
        service.recovery=SimpleNamespace(proof={'grant_id':'expired','epoch':1,'incarnation':'old','claim_id':'old'},
                                        grant={'expires_at':'2000-01-01T00:00:00+00:00'})
    service._report_blocker(PILOT,'hermes_auxiliary_inference_failed',2)
    service._status(state='STOPPED',reason='sigterm')
    restarted=make();restarted._report_blocker(PILOT,'different-reason',2)
    assert len(http.messages)==2
    assert_contained(restarted,http)
    assert restarted.recovery is None


def test_canonical_unavailable_does_not_suppress_fixed_alerts(configured):
    make,http,now=configured;http.canonical_available=False;service=make()
    for _ in range(4):service._report_blocker(PILOT,'canonical-unavailable',2)
    assert_contained(service,http)
    assert not http.blockers and len(http.messages)==2
    assert service._read_status()['reporting_attempts']['canonical']==2


def test_one_destination_rejection_is_bounded_and_independent(configured):
    make,http,now=configured;service=make();channel=DESTINATIONS['thread'][0]
    http.mode[channel]='rejected'
    service._report_blocker(PILOT,'blocked',2)
    assert len(http.messages)==1
    service._report_blocker(PILOT,'blocked',2)
    assert len([c for c in http.calls if c[2]=='/api/chat.postMessage'])==2
    now[0]+=timedelta(seconds=61);http.mode[channel]='success'
    make()._report_blocker(PILOT,'blocked',2)
    assert len(http.messages)==2
    assert_contained(service,http)


@pytest.mark.parametrize('mode',['lost_ack','malformed_ack','ambiguous'])
def test_ambiguous_delivery_readback_never_blindly_resends(configured,mode):
    make,http,now=configured;service=make();channel=DESTINATIONS['thread'][0];http.mode[channel]=mode
    service._report_blocker(PILOT,'blocked',2)
    for _ in range(6):
        now[0]+=timedelta(seconds=61);service=make();service._report_blocker(PILOT,'blocked',2)
    status=assert_contained(service,http)
    assert len([c for c in http.calls if c[2]=='/api/chat.postMessage' and c[3]['channel']==channel])==1
    entry=status['diagnostic_reports'][status['blocker_fingerprint']]['thread']
    assert entry['state']==('prepared' if mode=='ambiguous' else 'confirmed')
    assert entry['reads']<=3


def test_held_watch_reports_without_execution_or_self_approval(configured,monkeypatch):
    make,http,now=configured;service=make()
    service._status(state='BLOCKED_HOLD',mission_id=PILOT,reason='blocked',repeated=2,
                    blocker_fingerprint='f'*64,repository_mutation=False,remote_mutation=False)
    class Stop:
        calls=0
        def is_set(self):return self.calls>=2
        def wait(self,_):self.calls+=1;now[0]+=timedelta(seconds=61)
    def denied():raise NativeExecutionError('native_recovery_grant_required')
    monkeypatch.setattr(service,'resume_from_owner_grant',denied)
    monkeypatch.setattr(service,'once',lambda:pytest.fail('held watch must not execute'))
    service.watch(stop_event=Stop())
    assert len(http.messages)==2
    assert_contained(service,http)


def test_reporting_cannot_redirect_to_mission_supplied_destinations(configured):
    make,http,now=configured;service=make()
    service._status(state='BLOCKED_HOLD',mission_id='UNAPPROVED-MISSION',reason='blocked',
                    blocker_fingerprint='f'*64,repository_mutation=False,remote_mutation=False)
    service._report_blocker('UNAPPROVED-MISSION','blocked',2)
    assert not any(host=='slack.com' for _,host,_,_ in http.calls)


@pytest.mark.parametrize('alteration',[{'state':'new'},{'sends':0},{'state':'prepared'},{'identity':{}},{'reads':True},{'state':[]},{'state':{}}])
def test_malformed_retained_delivery_state_cannot_authorize_send(configured,alteration):
    make,http,now=configured;service=make();service._report_blocker(PILOT,'blocked',2)
    status=service._read_status();entries=status['diagnostic_reports'][status['blocker_fingerprint']]
    entries['thread'].update(alteration);service._status(diagnostic_reports=status['diagnostic_reports'])
    before=len(http.calls)
    with pytest.raises(NativeExecutionError,match='native_diagnostic_state_invalid'):
        make()._report_governed_diagnostics()
    assert len(http.calls)==before and len(http.messages)==2


def test_malformed_second_destination_blocks_all_reporting_io(configured):
    make,http,now=configured;service=make();service._report_blocker(PILOT,'blocked',2)
    status=service._read_status();entries=status['diagnostic_reports'][status['blocker_fingerprint']]
    entries.pop('thread');entries['approvals']['state']=[]
    service._status(diagnostic_reports=status['diagnostic_reports']);before=len(http.calls)
    with pytest.raises(NativeExecutionError):make()._report_governed_diagnostics()
    assert len(http.calls)==before


def test_new_failure_after_grant_consumption_changes_hold_identity(configured):
    make,http,now=configured;service=make();service._report_blocker(PILOT,'blocked',2)
    prior=service._read_status()['blocker_fingerprint']
    # Only this test fixture establishes a resumed local state; reporting never does.
    state=service._read_status();state['state']='RUNNING'
    service.status_path.write_text(__import__('json').dumps(state))
    service._held_status={}
    service.recovery=SimpleNamespace(proof={'grant_id':'consumed-grant','epoch':1,'incarnation':'same','claim_id':'exact'})
    service._report_blocker(PILOT,'blocked',2)
    assert service._read_status()['blocker_fingerprint']!=prior
    assert_contained(service,http)


@pytest.mark.parametrize('mode',['numeric','conflicting'])
def test_slack_timestamp_receipt_is_exact_string(configured,mode):
    from modules.charlie.native_runner.diagnostics import exact_receipt,acknowledged_post
    make,http,now=configured;service=make();service._report_blocker(PILOT,'blocked',2)
    status=service._read_status();entry=status['diagnostic_reports'][status['blocker_fingerprint']]['thread']
    if mode=='numeric':
        with pytest.raises(NativeExecutionError):exact_receipt({**entry['receipt'],'ts':1.2},entry['identity'])
    else:
        message=next(m for m in http.messages if m['channel']==DESTINATIONS['thread'][0])
        with pytest.raises(NativeExecutionError):acknowledged_post({'ok':True,'channel':message['channel'],'ts':'200.001','message':message},entry['identity'])
