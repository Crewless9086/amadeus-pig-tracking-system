"""Full installed pinned Hermes/SDK; only physical external transport is fake."""
import json
from pathlib import Path
import pytest
from tests.test_charlie_native_recovery_transactions import plane,http_plane,M,REV


def test_installed_auxiliary_sdk_wire_contract(tmp_path,monkeypatch):
    import httpx
    from modules.charlie.native_runner.model_adapter import HermesAuxiliaryModel,run_schema_canary
    from modules.charlie.native_runner.recovery import digest
    monkeypatch.setenv('OPENROUTER_API_KEY','test-only-no-live-key')
    monkeypatch.setenv('HERMES_HOME',str(tmp_path))
    (tmp_path/'config.yaml').write_text('model:\n  default: openai/gpt-5-mini\n  provider: openrouter\n')
    calls=[];effects=[]
    class Budget:
        grant={'limits':{'per_request_microusd':1000000},'pricing_ceiling':{'provider':'openrouter','model':'openai/gpt-5-mini','input_microusd_per_token':1,'output_microusd_per_token':1}}
        def perform(self,kind,intent,send,receipt):
            response=send();proof=receipt(response,intent);assert proof['intent_sha256']==digest(intent)
            effects.append((kind,intent,proof));return response
    def fake(transport,request):
        body=json.loads(request.read());calls.append(body)
        assert str(request.url)=='https://openrouter.ai/api/v1/chat/completions'
        assert request.headers['authorization']=='Bearer test-only-no-live-key'
        assert body['model']=='openai/gpt-5-mini' and body['max_tokens']==64
        assert body.get('tools',[])==[]
        return httpx.Response(200,request=request,json={'id':'fake-installed-1','object':'chat.completion','created':1,
            'model':'openai/gpt-5-mini','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{"status":"READY"}'}}],
            'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',fake)
    model=HermesAuxiliaryModel(profile_home=tmp_path);model.recovery=Budget()
    assert model._production_call is True
    assert run_schema_canary(model)['status']=='READY'
    assert len(calls)==len(effects)==1


@pytest.mark.parametrize('mode',['no_grant','budget','timeout','http_503'])
def test_installed_sdk_errors_cannot_escape_durable_budget(plane,tmp_path,monkeypatch,mode):
    from datetime import datetime,timedelta,timezone
    import httpx,openai
    from modules.charlie.native_runner.model_adapter import HermesAuxiliaryModel,run_schema_canary
    from modules.charlie.native_runner.recovery_session import RecoverySession
    from modules.charlie.native_runner.execution import NativeExecutionError
    from modules.charlie.native_runner.recovery import digest
    monkeypatch.setenv('OPENROUTER_API_KEY','test-only-no-live-key')
    (tmp_path/'config.yaml').write_text('model:\n  default: openai/gpt-5-mini\n  provider: openrouter\nauxiliary:\n  transient_retries: 0\n')
    http,api=http_plane(plane,monkeypatch)
    grant=plane.grant();grant['limits']={'requests':1,'spend_microusd':1000000,'per_request_microusd':1000000}
    grant['pricing_ceiling']={'provider':'openrouter','model':'openai/gpt-5-mini','input_microusd_per_token':1,
        'output_microusd_per_token':1,'evidence_sha256':digest('synthetic-pricing'),
        'expires_at':(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()}
    response=http.post(f'/api/charlie/build-relay/missions/{M}/native-runner/resume',json=grant,
        headers={'X-CHARLIE-Owner-Action':'native_runner_resume'});assert response.status_code==201,response.json
    session=RecoverySession(api,M,incarnation='installed-test-boot')
    session.consume({'mission_id':M,'state':'BLOCKED_HOLD','generation':'g1','blocker_fingerprint':'f'*64},worker_revision=REV)
    calls=[]
    def physical(transport,request):
        calls.append(json.loads(request.read()))
        if mode=='timeout':raise httpx.ReadTimeout('synthetic ambiguous provider timeout',request=request)
        if mode=='http_503':return httpx.Response(503,request=request,json={'error':'synthetic unavailable'})
        return httpx.Response(200,request=request,json={'id':'fake-installed-budget','object':'chat.completion','created':1,
            'model':'openai/gpt-5-mini','choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant','content':'{"status":"READY"}'}}]})
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',physical)
    # Retry time alone is omitted; actual SDK retry/control code still runs.
    monkeypatch.setattr(openai.OpenAI,'_sleep_for_retry',lambda *a,**k:None)
    model=HermesAuxiliaryModel(profile_home=tmp_path);model.recovery=None if mode=='no_grant' else session
    if mode=='budget':assert run_schema_canary(model)['status']=='READY'
    with pytest.raises(NativeExecutionError):run_schema_canary(model)
    state=plane.metadata()['native_recovery']
    assert len(calls)==state['requests']==(0 if mode=='no_grant' else 1)
    assert state['spend_microusd']==1000000*len(calls)
    if mode in {'timeout','http_503'}:assert next(iter(state['effects'].values()))['state']=='prepared'
