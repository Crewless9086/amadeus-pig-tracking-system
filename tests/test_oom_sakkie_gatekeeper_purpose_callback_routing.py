"""Execute the tracked GateKeeper route before native backend intake; no provider/DB I/O."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import pytest
from modules.oom_sakkie import telegram_direct as direct, telegram_gateway as gateway
from modules.oom_sakkie import herdmaster_purpose_telegram as purpose
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from tests.test_oom_sakkie_purpose_telegram import MemoryClaims, context

WORKFLOW = Path(__file__).parents[1] / 'docs/04-n8n/workflows/2 - The GateKeeper/workflow.json'
SECRET = 'synthetic-direct-secret-at-least-32-characters'
CARD = 700
NODE_HARNESS = r'''
const vm = require('node:vm'); const fs = require('node:fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const workflow = input.workflow;
const nodes = Object.fromEntries(workflow.nodes.map(n => [n.name, n]));
const visited = [];
function code(name, value, original) {
  visited.push(name);
  const context = {$json:value, $vars:{}, $items:(n) => {
    if(n !== 'Code - Normalize Telegram Update') throw Error('unexpected lookup');
    return [{json:original}];
  }};
  return new vm.Script('(function(){"use strict";\n' + nodes[name].parameters.jsCode + '\n})()')
    .runInNewContext(context, {timeout:200})[0].json;
}
function switchIndex(node, value) {
  const matches = node.parameters.rules.values.flatMap((r, i) => {
    if(r.conditions.combinator !== 'and') throw Error('unexpected combinator');
    const yes = r.conditions.conditions.every(c => {
      const m = c.leftValue.match(/^=\{\{\s*\$json\.([a-z_]+)\s*\}\}$/);
      if(!m || c.operator.operation !== 'equals') throw Error('unsupported switch');
      let expected = c.rightValue;
      if(c.operator.type === 'boolean') {
        if(!['=true','=false'].includes(expected)) throw Error('unexpected boolean');
        expected = expected === '=true';
      } else if(c.operator.type !== 'string') throw Error('unexpected type');
      return value[m[1]] === expected;
    });
    return yes ? [i] : [];
  });
  if(matches.length !== 1) throw Error('nonunique route');
  return matches[0];
}
const original = code('Code - Normalize Telegram Update', input.payload, {});
let value = code('Normalize Auth Check', input.authRow, original);
let name = workflow.connections['Normalize Auth Check'].main[0][0].node;
for(let steps=0;steps<12;steps++) {
  const node=nodes[name];
  let output=0;
  if(node.type==='n8n-nodes-base.code') value=code(name,value,original);
  else if(node.type==='n8n-nodes-base.switch') { visited.push(name); output=switchIndex(node,value); }
  else { process.stdout.write(JSON.stringify({terminal:name,visited,value})); process.exit(0); }
  const edges=workflow.connections[name]?.main?.[output];
  if(!edges || edges.length!==1) {
    process.stdout.write(JSON.stringify({terminal:null,terminals:(edges||[]).map(e=>e.node),visited,value})); process.exit(0);
  }
  name=edges[0].node;
}
throw Error('route exceeded bound');
'''


def workflow():
    return json.loads(WORKFLOW.read_text(encoding='utf-8-sig'))


def native_callback(data, *, user=42, chat=42, chat_type='private'):
    # Telegram dates the source message, not the click. Never enrich the envelope.
    return {'update_id':900, 'callback_query':{'id':'SYNTHETIC-CALLBACK', 'from':{'id':user,'is_bot':False},
        'data':data, 'message':{'message_id':CARD, 'date':1700000000,
        'chat':{'id':chat,'type':chat_type}, 'text':'Synthetic purpose overview'}}}


def route(payload, *, authorized=True):
    result = subprocess.run(['node','-e',NODE_HARNESS], input=json.dumps({'workflow':workflow(),
        'payload':payload, 'authRow':{'telegram_id':'42','role':'owner'} if authorized else {}}),
        capture_output=True, text=True, check=True, timeout=5)
    return json.loads(result.stdout)


def environment():
    return {'OOM_SAKKIE_TELEGRAM_OWNER_USER_ID':'42','OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS':'42',
        'OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE':'en','OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED':'1',
        'OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED':'1','OOM_SAKKIE_TELEGRAM_BOT_TOKEN':'synthetic-bot',
        'OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET':SECRET}


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    def fail(*a,**kw):pytest.fail('No network, database or model operation is allowed')
    import psycopg
    monkeypatch.setattr(socket.socket,'connect',fail)
    monkeypatch.setattr(psycopg,'connect',fail)
    monkeypatch.setattr(gateway,'interpret_owner_message',fail)
    monkeypatch.setattr(direct,'_AUTH_FAILURE_TIMES',[])
    monkeypatch.setattr(direct,'_AUTH_LOCKED_UNTIL',0.0)


@pytest.mark.parametrize('action',['group1','why','change','page1','pick0','set3','later','date20261007','confirm','cancel','remaining'])
def test_purpose_buttons_reach_one_existing_relay_with_unchanged_native_envelope(action):
    button=purpose._button('SYNTHETIC-TOKEN','Synthetic group',action)
    raw=native_callback(button['callback_data']);out=route(raw)
    assert out['terminal']=='Relay SAM Callback to Backend'
    assert out['value']['raw_update']==raw
    assert out['value']['callback_data']==button['callback_data']
    assert 'Security Check' in out['visited'] and 'Switch - Telegram Update Type' in out['visited']
    assert not {'Answer Telegram Callback','Acknowledge Unsupported Callback'} & set(out['visited'])


@pytest.mark.parametrize('data,targets',[
    ('oompa:SYNTHETIC:confirm',['Relay SAM Callback to Backend']),
    ('sam_live_card_send:SYNTHETIC',['Relay SAM Callback to Backend']),
    ('approve_SYNTHETIC',['Call 2.4 - Approval Callback Worker','Answer Telegram Callback']),
    ('reject_SYNTHETIC',['Call 2.4 - Approval Callback Worker','Answer Telegram Callback']),
    ('quote_send|SYNTHETIC|D|C',['Call 2.4.5 - Document Send Callback Worker','Answer Telegram Callback']),
    ('quote_cancel|SYNTHETIC|D|C',['Call 2.4.5 - Document Send Callback Worker','Answer Telegram Callback']),
    ('oompurX:SYNTHETIC:group1',['Acknowledge Unsupported Callback']),
    ('other:SYNTHETIC:group1',['Acknowledge Unsupported Callback'])])
def test_existing_and_unknown_callback_families_keep_their_routes(data,targets):
    out=route(native_callback(data))
    assert ([out['terminal']] if out['terminal'] else out['terminals'])==targets


def test_unauthorized_lookup_never_reaches_callback_classifier_or_backend():
    out=route(native_callback(purpose._button('SYNTHETIC','Group','group1')['callback_data']),authorized=False)
    assert out['terminal']=='Send Not Authorized'
    assert 'Code - Normalize Telegram Callback' not in out['visited']
    assert out['value']['is_authorized'] is False


@pytest.fixture
def backend(monkeypatch):
    memory=MemoryClaims();data=context();effects=[];claim_inputs=[]
    monkeypatch.setattr(purpose.claims,'create_claim',memory.create)
    def claim(callback,**kw):
        claim_inputs.append((callback,deepcopy(kw)));return memory.callback(callback,**kw)
    monkeypatch.setattr(purpose.claims,'claim_callback',claim)
    monkeypatch.setattr(purpose,'load_context',lambda **kw:data)
    def bind(token,message):memory.rows[token]['preview_card_message_id']=message;return True
    monkeypatch.setattr(purpose.claims,'bind_claim_card',bind)
    def deliver(parsed,result,**kw):
        effects.append(('edit',deepcopy(parsed),deepcopy(result)))
        return {'success':True,'telegram_sends':0,'telegram_edits':1,'telegram_message_id':str(CARD)}
    monkeypatch.setattr(gateway,'deliver_family_result',deliver)
    def ack(callback,source):effects.append(('ack',callback));return {'success':True}
    monkeypatch.setattr(gateway,'_acknowledge_family_callback',ack)
    monkeypatch.setattr(purpose,'execute_claimed_purpose',lambda *a,**kw:pytest.fail('Navigation cannot execute farm writes'))
    raw={'update_id':1,'message':{'message_id':1,'date':int(datetime.now(timezone.utc).timestamp()),
        'from':{'id':42},'chat':{'id':42,'type':'private'},'text':'Review the purpose decisions in Telegram'}}
    parsed=gateway.parse_telegram_gateway_payload(raw);parsed['output_language']='en'
    overview,status=purpose.handle_purpose_message(parsed,issue_gateway_owner_authority('42','42',principal_role='owner'))
    assert status==200
    bind(overview['callback_token'],str(CARD))
    button=next(b for row in overview['reply_markup']['inline_keyboard'] for b in row if b['callback_data'].endswith(':group1'))
    return native_callback(button['callback_data']),memory,effects,claim_inputs


def test_generated_group_button_traverses_workflow_and_real_native_backend_purpose_route(backend):
    raw,memory,effects,inputs=backend;out=route(raw)
    assert out['terminal']=='Relay SAM Callback to Backend'
    before=datetime.now(timezone.utc)
    body,status=direct.handle_telegram_direct_webhook(out['value']['raw_update'],
        headers={'X-Telegram-Bot-Api-Secret-Token':SECRET},environ=environment())
    after=datetime.now(timezone.utc)
    assert status==200 and body['message']['status']=='purpose_telegram_group'
    assert 'Sow 1' in body['answer'] and body['writes'] is False
    assert body['delivery']['protected_preview_card_bound'] is True
    assert [e[0] for e in effects]==['ack','edit'] and effects[0][1]=='SYNTHETIC-CALLBACK'
    callback,parsed=inputs[0]
    assert callback.endswith(':details') and parsed['purpose_callback'] is True
    assert parsed['provider_message_id']=='SYNTHETIC-CALLBACK' and parsed['source_card_message_id']==str(CARD)
    assert parsed['owner_user_id']==parsed['private_chat_id']=='42'
    assert before<=datetime.fromisoformat(parsed['provider_timestamp'])<=after
    delivered=effects[1][1]
    assert delivered['source_card_timestamp']==datetime.fromtimestamp(raw['callback_query']['message']['date'],timezone.utc).isoformat()
    assert 'provider_timestamp' not in raw and 'provider_timestamp' not in raw['callback_query']
    assert memory.completed==[]


@pytest.mark.parametrize('kind',['wrong_secret','foreign_owner','group_chat','wrong_card','expired'])
def test_backend_security_and_claim_refusals_remain_after_relay(kind,backend):
    raw,memory,effects,inputs=backend;secret=SECRET
    if kind=='wrong_secret':secret='wrong'
    if kind=='foreign_owner':raw['callback_query']['from']['id']=99;raw['callback_query']['message']['chat']['id']=99
    if kind=='group_chat':raw['callback_query']['message']['chat']['type']='group'
    if kind=='wrong_card':raw['callback_query']['message']['message_id']=701
    if kind=='expired':memory.rows[next(iter(memory.rows))]['status']='expired'
    out=route(raw);assert out['terminal']=='Relay SAM Callback to Backend'
    body,status=direct.handle_telegram_direct_webhook(out['value']['raw_update'],
        headers={'X-Telegram-Bot-Api-Secret-Token':secret},environ=environment())
    assert status>=400 and body['success'] is False and memory.completed==[]
    if kind in {'wrong_secret','foreign_owner','group_chat'}:assert inputs==[] and effects==[]
    else:assert len(inputs)==1 and body['message']['writes_farm_data'] is False


def test_relay_contract_remains_one_raw_authenticated_route_with_unchanged_timeout():
    w=workflow();nodes={n['name']:n for n in w['nodes']};relay=nodes['Relay SAM Callback to Backend']['parameters']
    assert relay['method']=='POST' and relay['url'].endswith('/api/oom-sakkie/channels/telegram/direct-webhook')
    assert relay['jsonBody']=='={{ $json.raw_update }}' and relay['options']['timeout']==10000
    assert relay['headerParameters']['parameters']==[{'name':'X-Telegram-Bot-Api-Secret-Token','value':'={{$vars.OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET}}'}]
    assert sum(n['type']=='n8n-nodes-base.telegramTrigger' for n in w['nodes'])==1
    assert 'callback_query' in nodes['Telegram Trigger']['parameters']['updates']
