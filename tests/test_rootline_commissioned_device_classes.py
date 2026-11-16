"""Commissioned provider device classes, independent of UIID9 protocol naming.
Shapes mirror the authenticated 4CHPROR3 and MINIR4 readbacks; tokens are synthetic.
No provider, database, device, or owner-message effects are performed.
"""
from copy import deepcopy
from urllib.parse import urlparse
import pytest
from tests.test_rootline_ewelink_readback import NOW, Store, env, provider
from modules.telemetry.rootline_ewelink_readback import read_registered_device
from modules.telemetry.rootline_ewelink_oauth import OAuthFailure
from modules.telemetry.rootline_failure_diagnostics import exception_failure, sanitize_failure
from modules.telemetry.rootline_device_registry import rootline_device_registry

DEVICES=(("100204e9bc",4,"4CHPROR3",4),("100204d497",4,"4CHPROR3",4),("1002851416",138,"MINIR4",1))

def actual_shape(device_id,mutate=None):
    uiid,model,count=next(row[1:] for row in DEVICES if row[0]==device_id)
    source=env();tokens=Store(source);raw,calls=provider()
    def request(method,url,**kwargs):
        assert method=="GET"
        result=deepcopy(raw(method,url,**kwargs))
        if urlparse(url).path=="/v2/device/thing":
            device=result['thingList'][0]['itemData']
            device.update(deviceid=device_id,productModel=model,extra={'uiid':uiid})
            if count==1:
                # MINI R4 has four provider placeholders but one physical outlet.
                device['params']['pulses']=[{'outlet':0,'pulse':'off','width':0}]
                device['params']['configure']=[{'outlet':0,'startup':'off'}]
            if mutate:mutate(result)
        return result
    return source,tokens,request,calls

def read(device_id,mutate=None,**kwargs):
    source,tokens,request,calls=actual_shape(device_id,mutate)
    result=read_registered_device(device_id,token_store=tokens,environ=source,http_request=request,now=NOW,routine_read=True,**kwargs)
    return result,calls

@pytest.mark.parametrize('device_id,uiid,model,count',DEVICES)
def test_commissioned_class_and_exact_outputs_use_two_fresh_GETs(device_id,uiid,model,count):
    result,calls=read(device_id)
    assert result['device_id']==device_id and result['device_uiid']==uiid
    assert result['device_model']==model and result['physical_output_count']==count
    assert [row['channel'] for row in result['channels']]==list(range(1,count+1))
    assert all(row['output_state']=='OFF' for row in result['channels'])
    assert result['authoritative'] and result['current_outputs_authoritative']
    assert result['provider_control_calls']==0 and result['provider_calls']==2
    assert calls==[('GET','/v2/device/thing'),('GET','/v2/device/thing/status')]
    contracts=[r for r in rootline_device_registry().values() if r.get('device_id')==device_id]
    assert all(r['channel'] in range(1,count+1) for r in contracts)

@pytest.mark.parametrize('device_id,good,model,count',DEVICES)
@pytest.mark.parametrize('bad',[None,True,False,'4',9,77,-1,0,4,138])
def test_wrong_class_stays_rejected_before_output_status(device_id,good,model,count,bad):
    if type(bad) is int and bad==good:return
    def change(value):value['thingList'][0]['itemData']['extra']['uiid']=bad
    source,tokens,request,calls=actual_shape(device_id,change)
    with pytest.raises(OAuthFailure,match='^ewelink_readback_device_class_mismatch$'):
        read_registered_device(device_id,token_store=tokens,environ=source,http_request=request,now=NOW,routine_read=True)
    assert calls==[('GET','/v2/device/thing')]

@pytest.mark.parametrize('device_id', [r[0] for r in DEVICES])
@pytest.mark.parametrize('fault',['different_device','duplicate_device','different_account','missing_account','missing_extra'])
def test_exact_device_and_account_membership_preserved(device_id,fault):
    def change(value):
        device=value['thingList'][0]['itemData']
        if fault=='different_device':device['deviceid']='unregistered'
        if fault=='duplicate_device':value['thingList'].append(deepcopy(value['thingList'][0]))
        if fault=='different_account':device['apikey']='other'
        if fault=='missing_account':device.pop('apikey')
        if fault=='missing_extra':device.pop('extra')
    source,tokens,request,calls=actual_shape(device_id,change)
    with pytest.raises(OAuthFailure):
        read_registered_device(device_id,token_store=tokens,environ=source,http_request=request,now=NOW,routine_read=True)
    assert len(calls)==1

@pytest.mark.parametrize('device_id',['100204e9bc','100204d497'])
@pytest.mark.parametrize('fault',['missing','duplicate','extra','wrong_outlet'])
def test_four_channel_output_membership_remains_exact(device_id,fault):
    def change(value):
        switches=value['thingList'][0]['itemData']['params']['switches']
        if fault=='missing':switches.pop()
        if fault=='duplicate':switches[-1]=deepcopy(switches[0])
        if fault=='extra':switches.append({'outlet':4,'switch':'off'})
        if fault=='wrong_outlet':switches[-1]['outlet']=4
    with pytest.raises(OAuthFailure,match='ewelink_device_status_incomplete'):read(device_id,change)

@pytest.mark.parametrize('device_id',['unknown','bf7d5909c4eb567d96vjhk'])
def test_unknown_and_smartlife_devices_never_enter_ewelink(device_id):
    source=env();tokens=Store(source)
    with pytest.raises(OAuthFailure,match='ewelink_registered_device_rejected'):
        read_registered_device(device_id,token_store=tokens,environ=source,http_request=lambda *_a,**_kw:pytest.fail('no provider call'),now=NOW,routine_read=True)

def test_exact_class_diagnostic_survives_without_free_text():
    reason='ewelink_readback_device_class_mismatch'
    assert exception_failure(OAuthFailure(reason))=={'error_type':'OAuthFailure','reason':reason}
    assert sanitize_failure({'reason':reason,'provider_body':{'secret':'not-copied'}})=={'reason':reason}
    assert exception_failure(OAuthFailure(reason+': token=secret'))=={'error_type':'OAuthFailure'}
