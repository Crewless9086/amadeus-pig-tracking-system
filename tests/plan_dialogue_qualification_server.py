"""Synthetic login for viewing records created through the actual gateway."""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode, urlparse

from tests.plan_dialogue_qualification import DATABASE_NAME
assert os.environ.get('PYTHON_DOTENV_DISABLED') == '1'
assert urlparse(os.environ.get('DATABASE_URL','')).hostname in {'127.0.0.1','localhost'}
assert urlparse(os.environ['DATABASE_URL']).path == '/' + DATABASE_NAME

import pytest
from tests.test_oom_sakkie_plan_dialogue_postgres import journey, test_individual_plan_partial_restart_reaches_real_bound_welfare_preview

fixtures={}
for language in ('en','af'):
    patcher=pytest.MonkeyPatch()
    try:
        fixture=journey.__wrapped__(patcher)
        test_individual_plan_partial_restart_reaches_real_bound_welfare_preview(fixture,language,patcher,'none',True)
        fixtures[language]=fixture
    finally:
        patcher.undo()

owner=fixtures['en']['owner'];manager=fixtures['af']['actor']
os.environ.update({'OOM_SAKKIE_TELEGRAM_BOT_TOKEN':'SYNTHETIC-dialogue-browser-bot',
    'OOM_SAKKIE_TELEGRAM_OWNER_USER_ID':owner,
    'OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON':json.dumps([{
        'telegram_user_id':manager,'family_key':'dad','role':'farm_manager',
        'permissions':['farm_observation','active_follow_up'],'summary_domains':['herd'],
        'language':'af','authorization_id':'SYNTHETIC-BROWSER-ONLY',
        'authorized_by_user_id':owner,'authorized_at':'2026-09-01T00:00:00Z'}])})

from flask import jsonify, render_template_string
from app import app

@app.get('/__plan_dialogue_ready')
def ready():
    return jsonify(ready=True,classification='synthetic_disposable_dialogue')

@app.get('/__plan_dialogue_start/<language>')
def entry(language):
    if language not in fixtures:
        return jsonify(error='Unknown synthetic language'),404
    fixture=fixtures[language];actor=owner if language=='en' else manager
    fields={'auth_date':str(int(time.time())),'user':json.dumps({'id':int(actor),'first_name':'Synthetic manager'})}
    key=hmac.new(b'WebAppData',os.environ['OOM_SAKKIE_TELEGRAM_BOT_TOKEN'].encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(key,'\n'.join(f'{key}={fields[key]}' for key in sorted(fields)).encode(),hashlib.sha256).hexdigest()
    return render_template_string('''<!doctype html><meta charset="utf-8"><title>Synthetic dialogue qualification</title>
      <h1>Local dialogue qualification</h1><p>The gateway confirmed one synthetic welfare record in disposable PostgreSQL.</p>
      <button id="sign-in">View confirmed observation</button><p id="error"></p>
      <script>document.getElementById('sign-in').onclick=async()=>{
        const r=await fetch('/owner/telegram/login',{method:'POST',headers:{'Content-Type':'application/json','X-Farm-Login':'telegram'},body:JSON.stringify({init_data:{{ init|tojson }}})});
        if(r.ok)location.assign({{ target|tojson }});else document.getElementById('error').textContent='Sign-in failed';
      };</script>''',init=urlencode(fields),target='/pig/'+fixture['pig'])

app.run(host='127.0.0.1',port=55826,debug=False,use_reloader=False)
