from copy import deepcopy
from datetime import timedelta
from urllib.parse import urlparse
import pytest
from tests.test_rootline_ewelink_readback import Store, env, provider, NOW
from tests.test_rootline_ewelink_request_budget import MemoryBudget, fail, snapshot
from modules.telemetry import rootline_ewelink_request_budget as budget
from modules.telemetry.rootline_ewelink_readback import read_registered_device
from modules.telemetry.rootline_ewelink_oauth import OAuthFailure


def fixture(changes=None):
    source=env(); tokens=Store(source); raw,calls=provider()
    def request(method,url,**kwargs):
        if urlparse(url).path=='/v2/user/refresh':
            calls.append((method,'/v2/user/refresh')); return {'at':'new-access','rt':'new-refresh'}
        value=deepcopy(raw(method,url,**kwargs))
        if 'thingList' in value:
            value['thingList'][0]['itemData']['extra']={'uiid':4}
            if changes: changes(value)
        return value
    return source,tokens,request,calls


def test_routine_and_default_one_complete_fresh_snapshot():
    source,tokens,request,calls=fixture()
    first=read_registered_device('100204e9bc',token_store=tokens,environ=source,http_request=request,now=NOW,routine_read=True)
    assert len(calls)==first['provider_calls']==1
    assert calls==[('POST','/v2/device/thing')]
    assert first['authoritative'] and first['channels'][0]['output_state']=='OFF'
    calls.clear()
    read_registered_device('100204e9bc',token_store=tokens,environ=source,http_request=request,now=NOW)
    assert calls==[('POST','/v2/device/thing')]


@pytest.mark.parametrize('fault',['account','missing_account','duplicate','uiid','expected_account'])
def test_routine_identity_refuses_before_status(fault):
    def mutate(value):
        device=value['thingList'][0]['itemData']
        if fault=='account':device['apikey']='other'
        if fault=='missing_account':device.pop('apikey')
        if fault=='duplicate':value['thingList'].append(deepcopy(value['thingList'][0]))
        if fault=='uiid':device['extra']['uiid']=138
    source,tokens,request,calls=fixture(mutate)
    if fault=='expected_account':source['EWELINK_EXPECTED_ACCOUNT_ID']='other'
    with pytest.raises(OAuthFailure):
        read_registered_device('100204e9bc',token_store=tokens,environ=source,http_request=request,now=NOW,routine_read=True)
    assert len(calls)==1


@pytest.mark.parametrize('expired',[False,True])
def test_due_recovery_keeps_same_group_full_discovery_and_charge(expired):
    source,tokens,raw,calls=fixture();client=MemoryBudget(environ=source)
    client.backend.now=NOW
    with pytest.raises(OAuthFailure):snapshot(client,send=fail())
    client.backend.advance(3601)
    if expired:tokens.record['access_expires_at']=NOW-timedelta(seconds=1)
    else:tokens.record['access_expires_at']=NOW+timedelta(days=1)
    before=sum(r['units'] for r in client.backend.events)
    def request(method,url,**kwargs):
        return client.dispatch(region='eu',endpoint=urlparse(url).path,send=lambda _:raw(method,url,**kwargs))
    result=read_registered_device('100204e9bc',token_store=tokens,environ=source,http_request=request,now=client.backend.now,routine_read=True)
    assert [r[1] for r in calls]==(['/v2/user/refresh'] if expired else [])+['/v2/family','/v2/device/thing','/v2/device/thing/status']
    assert result['provider_calls']==3+int(expired)
    assert sum(r['units'] for r in client.backend.events)-before==3+int(expired)
    assert not client.backend.state['scopes'][budget.scope_digest(source,'eu')]['category']


def test_recovery_signal_precedes_optional_and_reserve_mutations():
    source,tokens,raw,calls=fixture();client=MemoryBudget(environ=source);client.backend.now=NOW
    with pytest.raises(OAuthFailure):snapshot(client,send=fail())
    client.backend.advance(3601);events=deepcopy(client.backend.events);state=deepcopy(client.backend.state)
    with budget.optional_observation('irrigation_routine'):
        with budget.snapshot_group(expected_device='100204e9bc',environ=source,region='eu') as group:
            group['routine_read']=True
            with pytest.raises(budget.FullSnapshotRequired):
                client.dispatch(region='eu',endpoint='/v2/device/thing',send=lambda _:pytest.fail('no send'))
            assert not group['failed']
            assert client.backend.events==events and client.backend.state==state


def test_manager_uses_canonical_timestamp_without_provider_calls():
    from modules.telemetry.rootline_mixer_readiness_observer import collect_mixer_readiness
    proof={'authoritative':True,'device_id':'100204d497','channel':2,'state':'OFF','evidence_id':'proof','retrieved_at':NOW.isoformat()}
    record={'auxiliary_device_id':'FERTILIZER-MIXER-CH2','device_id':'100204d497','channel':2,'shutdown_evidence':proof}
    def ledger(action,payload):return [record] if action=='load_auxiliary_history' else None
    for purpose in ['mixer_readiness','mixer_readiness_delivery']:
        row=collect_mixer_readiness(now=NOW+timedelta(minutes=3),execution_store=ledger,
            readback=lambda *_a,**_k:pytest.fail('no provider poll'),_observation_purpose=purpose)[0]
        assert row['canonical_observation']['current_state']=='Unknown'
        assert row['canonical_observation']['last_observed_state']=='OFF'
        assert row['canonical_observation']['observed_at']==NOW.isoformat()
        assert not row['equipment_evidence']['provider_readiness_proven']
        assert 'observed:'+NOW.isoformat() in row['evidence_refs']


def test_complete_observation_uses_fresh_outputs_and_fresh_offline_metadata():
    source,tokens,raw,calls=fixture()
    def request(method,url,**kwargs):
        value=raw(method,url,**kwargs)
        if urlparse(url).path=='/v2/device/thing':
            device=value['thingList'][0]['itemData'];device['online']=False
            device['params']['switches']=[{'outlet':i,'switch':'on'} for i in range(4)]
        return value
    result=read_registered_device('100204e9bc',token_store=tokens,environ=source,http_request=request,now=NOW,routine_read=True)
    assert result['online'] is False
    assert result['channels'][0]['output_state']=='ON'
    assert result['actuation_eligible'] is False
