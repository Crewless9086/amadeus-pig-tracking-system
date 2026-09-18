"""Local application view over synthetic gateway/stop evidence in disposable PostgreSQL."""
import hashlib
import hmac
import json
import os
from pathlib import Path
import time
from urllib.parse import urlencode, urlparse

import pytest
from tests.irrigation_dialogue_qualification import DATABASE_NAME
assert os.environ.get('PYTHON_DOTENV_DISABLED') == '1'
assert urlparse(os.environ['DATABASE_URL']).hostname in {'127.0.0.1','localhost'}
assert urlparse(os.environ['DATABASE_URL']).path == '/' + DATABASE_NAME

from tests.test_oom_sakkie_irrigation_dialogue_postgres import (
    irrigation, test_morning_reply_partial_restart_and_duplicate_keep_independent_water_rows,
    NOW, observations, reply)
from modules.oom_sakkie import owner_operational_continuation as continuation
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result
from modules.oom_sakkie.semantic_front_door import SemanticInterpretation
from modules.sales.sam_live_stock_launch_control import (
    build_sam_live_stock_review_event, record_sam_live_stock_review_event)
from modules.telemetry.rootline_owner_status import get_rootline_owner_status

patcher = pytest.MonkeyPatch()
fixture = irrigation.__wrapped__(patcher)
test_morning_reply_partial_restart_and_duplicate_keep_independent_water_rows(fixture,'en',True)
owner = fixture['owner']
execution = 'SYNTHETIC-IRRIGATION-EXECUTION-'+owner
mission = 'SYNTHETIC-ROOTLINE-C-SEGMENT-'+owner

# Explicit synthetic execution evidence, never a controller invocation. The
# actual application projection must keep it distinct from an owner's report.
for action in ('claim_before_on','mark_active'):
    event = build_sam_live_stock_review_event({'conversation_id':execution},{},{},
        {'score':0,'safe_to_send':False,'recommended_action':'synthetic_fixture'},
        event_source='rootline_irrigation_execution')
    event.update({'review_event_id':execution+'-'+action,'chatwoot_conversation_id':execution,
        'review_json':{'rootline_execution':{'execution_id':execution,'action':action,
            'state':'Active','zone_id':'C12345','shutdown_verified':False,
            'provider_output_state':'Unknown','classification':'synthetic_execution_fixture'}},
        'decision_json':{},'facts_json':{},'customer_message_excerpt':'','sam_reply_excerpt':''})
    value,status = record_sam_live_stock_review_event(event)
    assert status < 300 and value['success'],value

parsed = {'telegram_user_id':owner,'telegram_chat_id':owner,'provider_message_id':'synthetic-active',
    'provider_timestamp':NOW.isoformat(),'text':'Synthetic active execution','output_language':'en'}
card = deliver_family_result(parsed,{'success':True,'status':'Active','answer':'C Camp irrigation is active.',
    'execution_id':execution,'recipient_render_contract':'specialist_structured_recipient_v1',
    'recipient_language':'en','hardware_commands':0},specialist='ROOTLINE',mission_id=mission,card_mission_id=mission)
assert card['success'],card
bound = continuation._context_store('record',mission+'-ACTIVE-BINDING',{
    'mission_id':mission,'card_mission_id':mission,'owner_user_id':owner,'chat_id':owner,
    'state':'active_lifecycle_bound','entity_id':'C12345','execution_id':execution,
    'execution_state':'Active','execution_started_at':NOW.isoformat()})
assert bound['success'],bound
from datetime import timedelta
fixture['semantic']['value'] = SemanticInterpretation(domain='rootline',intent='irrigation_status',
    message_kind='observation',confidence=.99,language='en',
    irrigation_observation={'zone_id':'C12345','state':'stopped'})
stop,status = reply(fixture,'The water in C Camp has stopped.',703,NOW+timedelta(minutes=3),card['telegram_message_id'])
assert status == 200 and stop['message']['verification_pending'] is True,stop
assert stop['message']['execution_completed'] is False
canonical,status = get_rootline_owner_status()
assert status == 200,canonical
assert canonical['current']['status'] == 'RUNNING',canonical
assert canonical['water_evidence']['storage_fraction'] == [1,1],canonical
assert canonical['water_evidence']['reservoir_fraction'] == [1,2],canonical
assert next(row for row in canonical['zones'] if row['zone_id']=='C12345')['lifecycle']['state'] == 'Started'
Path(__file__).resolve().parents[2].joinpath('BROWSER_APPLICATION_FIXTURE.json').write_text(json.dumps({
    'classification':'synthetic_gateway_and_execution_fixture_no_physical_irrigation',
    'owner':owner,'execution':execution,'stop_response':stop,'canonical':canonical,
    'observations':observations(fixture),'provider_calls':fixture['provider']},default=str,indent=2),encoding='utf-8')

from flask import jsonify, render_template_string
from app import app

@app.get('/__irrigation_dialogue_ready')
def ready():
    return jsonify(ready=True,classification='synthetic_disposable_irrigation',execution=execution)

@app.get('/__irrigation_dialogue_start')
def entry():
    fields={'auth_date':str(int(time.time())),'user':json.dumps({'id':int(owner),'first_name':'Synthetic owner'})}
    key=hmac.new(b'WebAppData',os.environ['OOM_SAKKIE_TELEGRAM_BOT_TOKEN'].encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(key,'\n'.join(f'{name}={fields[name]}' for name in sorted(fields)).encode(),hashlib.sha256).hexdigest()
    return render_template_string('''<!doctype html><meta charset="utf-8"><title>Local irrigation qualification</title>
      <h1>Local irrigation qualification</h1><p>Synthetic water observations and a reported stop are stored in disposable PostgreSQL.</p>
      <button id="sign-in">View irrigation evidence</button><p id="error"></p>
      <script>document.getElementById('sign-in').onclick=async()=>{
        const r=await fetch('/owner/telegram/login',{method:'POST',headers:{'Content-Type':'application/json','X-Farm-Login':'telegram'},body:JSON.stringify({init_data:{{ init|tojson }}})});
        if(r.ok)location.assign('/irrigation');else document.getElementById('error').textContent='Sign-in failed';
      };</script>''',init=urlencode(fields))

app.run(host='127.0.0.1',port=18036,debug=False,use_reloader=False)
