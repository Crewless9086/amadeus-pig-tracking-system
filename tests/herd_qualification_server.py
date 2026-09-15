"""Synthetic login/fixtures available only in the isolated qualification process."""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode, urlparse

# Validate before importing the application or installing any fixture route.
from tests.herd_qualification import DATABASE_NAME
assert os.environ.get('PYTHON_DOTENV_DISABLED') == '1'
assert urlparse(os.environ.get('DATABASE_URL', '')).hostname in {'127.0.0.1', 'localhost'}
assert urlparse(os.environ['DATABASE_URL']).path == '/' + DATABASE_NAME

ACTOR = '7400000001'
os.environ.update({
    'OOM_SAKKIE_TELEGRAM_BOT_TOKEN': 'SYNTHETIC-herd-browser-bot',
    'OOM_SAKKIE_TELEGRAM_OWNER_USER_ID': '990000',
    'OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON': json.dumps([{
        'telegram_user_id': ACTOR, 'family_key': 'dad', 'role': 'farm_manager',
        'permissions': ['farm_observation', 'weaning', 'treatment'],
        'summary_domains': ['herd'], 'language': 'af',
        'authorization_id': 'SYNTHETIC-BROWSER-ONLY', 'authorized_by_user_id': '990000',
        'authorized_at': '2026-09-01T00:00:00+02:00',
    }]),
})

import psycopg
from flask import jsonify, render_template_string, request
from app import app
from tests import first_treatment_test_support, weaning_test_support

fixtures = {}
supports = {'first_treatment': first_treatment_test_support, 'weaning': weaning_test_support}


@app.get('/__herd_test_ready')
def synthetic_readiness():
    with psycopg.connect(first_treatment_test_support.database_url()) as db:
        db.execute('SELECT 1').fetchone()
    return jsonify(classification='isolated_synthetic_fixture', ready=True)


def synthetic_entry(kind):
    support = supports[kind]
    fixture = support.seed()
    if request.args.get('sow') == 'dead':
        with psycopg.connect(support.database_url()) as db:
            db.execute("update public.pigs set status='Dead',on_farm=false where pig_id=%s", (fixture['sow'],))
    fixtures[fixture['litter']] = (kind, fixture)
    fields = {'auth_date': str(int(time.time())), 'user': json.dumps({'id': int(ACTOR), 'first_name': 'Synthetic manager'})}
    key = hmac.new(b'WebAppData', os.environ['OOM_SAKKIE_TELEGRAM_BOT_TOKEN'].encode(), hashlib.sha256).digest()
    fields['hash'] = hmac.new(key, '\n'.join(f'{key}={fields[key]}' for key in sorted(fields)).encode(), hashlib.sha256).hexdigest()
    return render_template_string('''<!doctype html><meta charset="utf-8"><title>Synthetic herd qualification</title>
      <h1>Synthetic local farm identity</h1><p>Disposable PostgreSQL. Simulated Telegram signature.</p>
      <button id="sign-in">Sign in as synthetic farm manager</button><p id="error"></p>
      <script>document.getElementById('sign-in').onclick=async()=>{
        const r=await fetch('/owner/telegram/login',{method:'POST',headers:{'Content-Type':'application/json','X-Farm-Login':'telegram'},body:JSON.stringify({init_data:{{ init | tojson }}})});
        if(r.ok)location.assign({{ target | tojson }});else document.getElementById('error').textContent='Sign-in failed';
      };</script>''', init=urlencode(fields), target='/litter/' + fixture['litter'])


def synthetic_state(kind, litter_id):
    if litter_id not in fixtures or fixtures[litter_id][0] != kind:
        return jsonify(error='Not a fixture from this test server'), 404
    fixture = fixtures[litter_id][1]
    value = supports[kind].state(fixture)
    if kind == 'first_treatment':
        from modules.pig_weights.farm_supabase_read_service import get_litter_detail
        value = {**value, 'fixture': fixture, 'detail': get_litter_detail(litter_id)}
    return jsonify(value)


for kind in supports:
    app.add_url_rule('/__' + kind + '_test_start', endpoint=kind + '_entry',
        view_func=lambda kind=kind: synthetic_entry(kind))
    app.add_url_rule('/__' + kind + '_test_state/<litter_id>', endpoint=kind + '_state',
        view_func=lambda litter_id, kind=kind: synthetic_state(kind, litter_id))

app.run(host='127.0.0.1', port=55821, debug=False, use_reloader=False)
