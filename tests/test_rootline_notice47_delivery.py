"""Real family claim/sender boundaries; no provider or external persistence."""
from concurrent.futures import ThreadPoolExecutor
from threading import Lock,Barrier
import pytest
from modules.oom_sakkie import family_message_lifecycle as family
from modules.oom_sakkie.delivery_retry_authority import issue_delivery_retry_authority
from modules.oom_sakkie.family_presentation import envelope
from tests.test_oom_sakkie_family_message_lifecycle import PARSED
RESULT={'success':True,'status':'started','answer':'Mixer ON command accepted.',
        'recipient_render_contract':'specialist_structured_recipient_v1','recipient_language':'en'}
IDENTITY='ROOTLINE-EDGE:Started'
class Rail:
    def __init__(self,clock):self.rows={};self.clock=clock;self.cost=0;self.lock=Lock();self.barrier=None
    def store(self,action,identity,payload):
        if action=='load':
            with self.lock: snapshot=list(self.rows.values())
            if self.barrier:self.barrier.wait(timeout=5)
            return snapshot
        with self.lock:
            created=identity not in self.rows
            if created:self.rows[identity]=dict(payload)
            if payload.get('state')=='delivery_attempted':self.clock[0]+=self.cost
            return {'success':True,'created':created}
def authority():
    return issue_delivery_retry_authority(mission_id=IDENTITY,card_mission_id=IDENTITY,
        text=envelope(RESULT['answer']),proof_identity='CANONICAL-INITIAL-NOTIFICATION-ZERO-SEND')
def call(rail,**kwargs):
    return family.deliver_family_result(PARSED,RESULT,specialist='ROOTLINE',mission_id=IDENTITY,
        card_mission_id=IDENTITY,event_store=rail.store,**kwargs)
@pytest.fixture
def scenario(monkeypatch):
    clock=[0.];monkeypatch.setattr(family.time,'monotonic',lambda:clock[0]);rail=Rail(clock);sends=[]
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_BOT_TOKEN','isolated-test-token')
    monkeypatch.delenv('SAM_LIVE_STOCK_TELEGRAM_BOT_TOKEN',raising=False)
    from modules.sales import sam_live_stock_launch_control as provider
    def api(*args):sends.append(args);return {'ok':True,'result':{'message_id':700,'date':1795680000}}
    monkeypatch.setattr(provider,'_telegram_api',api)
    return clock,rail,sends

def legacy_exhausted(monkeypatch,scenario):
    clock,rail,sends=scenario
    # Reproduce the production pre-fix boundary using the real _send_telegram.
    with monkeypatch.context() as legacy:
        legacy.setattr(family,'ROOTLINE_CLAIM_RESERVE_SECONDS',0)
        from contextlib import nullcontext
        from modules.telemetry import rootline_cycle_budget
        legacy.setattr(rootline_cycle_budget,'cycle_budget',lambda *_:nullcontext())
        for retry in (None,authority()):
            clock[0]=69;rail.cost=2
            value=call(rail,deadline_monotonic=100,delivery_retry_authority=retry)
            assert value['delivery_definitely_not_sent'] is True and value['telegram_sends']==0
    assert not sends and len(rail.rows)==4
    return clock,rail,sends

def test_late_cycle_does_not_claim_and_later_cycle_delivers(scenario):
    clock,rail,sends=scenario;clock[0]=69;rail.cost=2
    value=call(rail,deadline_monotonic=100)
    assert value['status']=='family_message_cycle_deadline_deferred' and not rail.rows and not sends
    clock[0]=20
    value=call(rail,deadline_monotonic=100)
    assert value['telegram_sends']==1 and len(sends)==1
    assert call(rail,deadline_monotonic=100)['telegram_sends']==0

def test_real_sender_late_zero_send_history_recovers_next_cycle(monkeypatch,scenario):
    clock,rail,sends=legacy_exhausted(monkeypatch,scenario);clock[0]=20
    value=call(rail,deadline_monotonic=100,delivery_retry_authority=authority())
    assert value['telegram_sends']==1 and len(sends)==1
    assert call(rail,deadline_monotonic=100,delivery_retry_authority=authority())['telegram_sends']==0
    assert len([r for r in rail.rows.values() if r['state']=='delivery_attempted'])==3

@pytest.mark.parametrize('damage',['ambiguous','orphan','recipient','text','unknown','duplicate','no_authority','delivered_no_id','unknown_state','foreign_record'])
def test_unproven_history_never_sends(monkeypatch,scenario,damage):
    clock,rail,sends=legacy_exhausted(monkeypatch,scenario);clock[0]=20
    key=IDENTITY+'-DELIVERY-RETRY-2-CONTAINED'
    if damage=='ambiguous':rail.rows[key]['reason']='telegram_delivery_unconfirmed'
    elif damage=='orphan':rail.rows.pop(key)
    elif damage=='recipient':rail.rows[key]['chat_id']='other'
    elif damage=='text':rail.rows[key]['text_sha256']='bad'
    elif damage=='unknown':rail.rows['unknown']={**rail.rows[key],'event_id':'unknown'}
    elif damage=='duplicate':rail.rows['duplicate']=dict(rail.rows[key])
    elif damage=='delivered_no_id':rail.rows['delivered']={**rail.rows[key],'event_id':'delivered','state':'delivered','telegram_message_id':''}
    elif damage=='unknown_state':rail.rows['other']={**rail.rows[key],'event_id':'other','state':'unexpected'}
    elif damage=='foreign_record':rail.rows['foreign']={**rail.rows[key],'event_id':'foreign','card_mission_id':'other'}
    value=call(rail,deadline_monotonic=100,delivery_retry_authority=None if damage=='no_authority' else authority())
    assert value['telegram_sends']==0 and not sends

def test_concurrent_recovery_claim_has_one_sender(monkeypatch,scenario):
    clock,rail,sends=legacy_exhausted(monkeypatch,scenario);clock[0]=20;rail.cost=0;rail.barrier=Barrier(2)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(call,rail,deadline_monotonic=100,delivery_retry_authority=authority()) for _ in range(2)]
        results=[f.result(timeout=10) for f in futures]
    assert sum(v['telegram_sends'] for v in results)==1 and len(sends)==1

def test_sender_guard_still_contains_unexpected_claim_overrun(scenario):
    clock,rail,sends=scenario;clock[0]=20;rail.cost=60
    value=call(rail,deadline_monotonic=100)
    assert value['delivery_definitely_not_sent'] is True and not sends

def test_claim_scope_preserves_network_reserve(scenario):
    from modules.telemetry.rootline_cycle_budget import work_deadline
    clock,rail,_=scenario;clock[0]=20;seen=[];original=rail.store
    def store(action,identity,payload):
        if action=='record' and payload.get('state')=='delivery_attempted':seen.append(work_deadline())
        return original(action,identity,payload)
    rail.store=store
    call(rail,deadline_monotonic=100)
    assert seen==[30] and work_deadline() is None


def test_each_later_retry_requires_its_own_durable_zero_send_proof(monkeypatch,scenario):
    clock,rail,sends=legacy_exhausted(monkeypatch,scenario)
    clock[0]=20;rail.cost=60
    failed=call(rail,deadline_monotonic=100,delivery_retry_authority=authority())
    assert failed['delivery_definitely_not_sent'] is True and not sends
    clock[0]=20;rail.cost=2
    recovered=call(rail,deadline_monotonic=100,delivery_retry_authority=authority())
    assert recovered['telegram_sends']==1 and len(sends)==1
    attempts=[r['event_id'] for r in rail.rows.values() if r['state']=='delivery_attempted']
    assert len(attempts)==4 and len(set(attempts))==4

@pytest.mark.parametrize('recovery', [False, True])
@pytest.mark.parametrize('failure', ['failed_receipt', 'not_created', 'missing_receipt', 'unknown_commit', 'deadline_after_commit'])
def test_uncertain_claim_never_sends_or_replays(monkeypatch, scenario, recovery, failure):
    from copy import deepcopy
    from modules.telemetry.rootline_cycle_budget import RootlineCycleDeadlineExceeded, work_deadline
    clock, rail, sends = legacy_exhausted(monkeypatch, scenario) if recovery else scenario
    clock[0] = 20
    original = rail.store
    prior = deepcopy(rail.rows)
    claimed_ids = []
    def uncertain_store(action, identity, payload):
        result = original(action, identity, payload)
        if action == 'record' and payload.get('state') == 'delivery_attempted':
            claimed_ids.append(identity)
            if failure == 'unknown_commit':
                raise RuntimeError('synthetic_unknown_commit_acknowledgement')
            if failure == 'deadline_after_commit':
                raise RootlineCycleDeadlineExceeded('synthetic_claim_deadline_after_commit')
            return {'failed_receipt': {'success': False, 'created': True},
                    'not_created': {'success': True, 'created': False},
                    'missing_receipt': None}[failure]
        return result
    rail.store = uncertain_store
    kwargs = {'deadline_monotonic': 100,
              'delivery_retry_authority': authority() if recovery else None}
    if failure in {'unknown_commit', 'deadline_after_commit'}:
        expected = RuntimeError if failure == 'unknown_commit' else RootlineCycleDeadlineExceeded
        with pytest.raises(expected):
            call(rail, **kwargs)
    else:
        result = call(rail, **kwargs)
        assert result['status'] == 'family_message_delivery_ambiguous'
        assert result['telegram_sends'] == 0
    assert sends == [] and len(claimed_ids) == 1
    assert work_deadline() is None
    assert all(rail.rows[key] == value for key, value in prior.items())
    assert set(rail.rows) == set(prior) | set(claimed_ids)
    assert claimed_ids[0] + '-CONTAINED' not in rail.rows
    frozen = deepcopy(rail.rows)
    rail.store = original
    replay = call(rail, **kwargs)
    assert replay['status'] == 'family_message_delivery_ambiguous'
    assert replay['telegram_sends'] == 0 and sends == []
    assert rail.rows == frozen
