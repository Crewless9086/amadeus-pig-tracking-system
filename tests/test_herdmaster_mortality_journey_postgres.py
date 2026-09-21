"""Real-service local proof. Telegram authentication/signatures are simulations.

No provider send or LLM is used. Requires the existing disposable audit-rail
PostgreSQL bootstrap plus real canonical farm reader migrations.
"""
import hashlib
import hmac
import ipaddress
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode, urlparse

import psycopg
import pytest

from app import app
from modules.oom_sakkie.family_access import resolve_family_principal
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_runtime import (
    handle_authenticated_health_loss_message, _load_active_contexts)


DSN = os.getenv("CHARLIE_DISPOSABLE_POSTGRES_URL", "")
pytestmark = pytest.mark.skipif(not DSN, reason="disposable PostgreSQL URL required")


def signed_init(actor, *, age=0, token=None):
    fields = {"auth_date": str(int(time.time()) - age),
              "user": json.dumps({"id": int(actor), "first_name": "Synthetic manager"})}
    key = hmac.new(b"WebAppData", (token or os.environ["OOM_SAKKIE_TELEGRAM_BOT_TOKEN"]).encode(), hashlib.sha256).digest()
    check = "\n".join(f"{key}={fields[key]}" for key in sorted(fields))
    fields["hash"] = hmac.new(key, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest.fixture
def journey(monkeypatch):
    url = urlparse(DSN)
    assert (url.hostname == "localhost" or ipaddress.ip_address(url.hostname).is_loopback) and "test" in url.path
    actor = str(7000000000 + int(uuid.uuid4().hex[:7], 16))
    pig = "PIG-2026-" + uuid.uuid4().hex[:4].upper()
    tag = "LOCAL-" + uuid.uuid4().hex[:10].upper()
    pen = "PEN-" + uuid.uuid4().hex
    monkeypatch.setenv("OWNER_ACCESS_ENABLED", "true")
    monkeypatch.setenv("OWNER_ACCESS_ALLOW_LOCAL_DEV", "false")
    monkeypatch.setenv("OWNER_SESSION_SECRET", "synthetic-local-session-" + "s" * 40)
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_BOT_TOKEN", "synthetic-local-bot-token-only")
    monkeypatch.setenv("OOM_SAKKIE_TELEGRAM_OWNER_USER_ID", "990000")
    monkeypatch.setenv("OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON", json.dumps([{
        "telegram_user_id": actor, "family_key": "dad", "role": "farm_manager",
        "permissions": ["farm_observation"], "summary_domains": ["herd"], "language": "af",
        "authorization_id": "SYNTHETIC-LOCAL-ONLY", "authorized_by_user_id": "990000",
        "authorized_at": "2026-09-01T00:00:00+02:00"}]))
    with psycopg.connect(DSN) as db:
        db.execute("insert into public.pens(pen_id,pen_name) values(%s,'Synthetic mortality pen')", (pen,))
        db.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm,initial_pen_id,purpose,date_of_birth,notes)
            values(%s,%s,'Synthetic mortality animal','Active',true,%s,'Sale','2026-01-01','Preserve existing history')""", (pig,tag,pen))
        db.execute("""insert into public.pig_weight_events(weight_event_id,pig_id,weight_date,weight_kg,weighed_by,source,condition_notes)
            values(%s,%s,'2026-09-01',42.5,'synthetic-observer','local_test','Preserved earlier measurement')""",
            ('WEIGHT-'+uuid.uuid4().hex,pig))
    client = app.test_client()
    response = client.post("/owner/telegram/login", json={"init_data": signed_init(actor)}, headers={"X-Farm-Login":"telegram"})
    assert response.status_code == 200, response.get_json()
    page = client.get("/pig/" + pig)
    csrf = re.search(r'data-csrf="([^"]+)"', page.get_data(as_text=True)).group(1)
    return {"actor":actor, "pig":pig, "tag":tag, "client":client, "csrf":csrf}


def state(j):
    with psycopg.connect(DSN) as db:
        return {"pig": db.execute("select status,on_farm,exit_date,notes from public.pigs where pig_id=%s", (j["pig"],)).fetchone(),
            "weights": db.execute("select weight_event_id,weight_date,weight_kg,weighed_by,condition_notes from public.pig_weight_events where pig_id=%s order by weight_event_id", (j['pig'],)).fetchall(),
            "events": db.execute("select count(*) from public.pig_lifecycle_events where pig_id=%s", (j["pig"],)).fetchone()[0],
            "active_count": db.execute("select count(*) from public.pig_current_state where status='Active' and on_farm").fetchone()[0]}


def web(j, **payload):
    response = j["client"].post(f'/api/pig-weights/pig/{j["pig"]}/lifecycle/death', json=payload,
        headers={"X-Mortality-CSRF":j["csrf"]})
    return response.get_json(), response.status_code


def telegram(j, text, *, moment=None, message_id=None):
    actor = j["actor"]
    principal = resolve_family_principal({"telegram_user_id":actor,"telegram_chat_id":actor,"telegram_chat_type":"private"}, os.environ)
    authority = issue_gateway_owner_authority(actor,actor,principal_role=principal.role.value,capabilities=principal.effective_permissions)
    return handle_authenticated_health_loss_message({"telegram_user_id":actor,"telegram_chat_id":actor,"telegram_chat_type":"private",
        "text":text,"output_language":"af", "provider_message_id":message_id or uuid.uuid4().hex,
        "provider_timestamp":moment or datetime.now(timezone.utc).isoformat()}, authority)


def test_application_preview_restart_confirm_and_telegram_readback(journey):
    j = journey
    before = state(j)
    denied, code = web(j, event_date="2026-09-09", reason="Died", changed_by="forged-actor")
    assert code == 409 and state(j) == before
    result, code = web(j, phase="preview", event_date="2026-09-09", reason="Died", notes="Cause unknown. Not buried yet.")
    assert code == 200 and result["status"] == "preview_ready", result
    operation = result["operation_id"]
    assert state(j) == before
    resumed = j["client"].get(f'/api/pig-weights/pig/{j["pig"]}/lifecycle/death').get_json()
    assert resumed["operation_id"] == operation
    result, code = web(j, phase="confirm", operation_id=operation)
    assert code == 201 and result["success"], result
    after = state(j)
    assert after["pig"][:2] == ("Dead",False)
    assert after["active_count"] == before["active_count"] - 1 and after["events"] == 1
    assert after['weights'] == before['weights'] and len(after['weights']) == 1
    assert "Preserve existing history" in after["pig"][3] and "Not buried yet" in after["pig"][3]
    replay, code = telegram(j, "CONFIRM " + operation)
    assert code == 200 and replay["success"], replay
    assert replay['event_date'] == '2026-09-09' and 'Afsterwedatum: 2026-09-09' in replay['answer']
    assert replay['canonical_readback']['canonical_readback_verified'] is True
    assert state(j) == after
    profile = j["client"].get('/api/pig-weights/pig/' + j["pig"]).get_json()
    assert profile["pig"]["status"] == "Dead" and profile["pig"]["on_farm"] == "No"
    with psycopg.connect(DSN) as db:
        event = db.execute("select actor_reference,event_payload from public.pig_lifecycle_events where pig_id=%s", (j["pig"],)).fetchone()
        assert event[0] == j["actor"] and event[1]["source_channel"] == "application"
        assert event[1]["removal"] == {}  # A negated burial is not a completed disposal.
    with pytest.raises(psycopg.Error), psycopg.connect(DSN) as db:
        db.execute("update public.pig_lifecycle_events set event_note='rewrite forbidden' where pig_id=%s", (j["pig"],))
    assert state(j) == after


def test_telegram_missing_date_short_reply_correction_and_application_confirm(journey):
    j = journey
    start = "2026-09-09T22:30:00+00:00"  # Already September 10 in South Africa.
    result, code = telegram(j, f'Vark {j["tag"]} is dood.', moment=start)
    assert code == 200 and result["status"] == "waiting_for_input", result
    result, code = telegram(j, 'Gister', moment="2026-09-09T22:31:00+00:00")
    assert code == 200 and result["status"] == "preview_ready", result
    assert "2026-09-09" in result["answer"]
    old = result["operation_id"]
    result, code = telegram(j, 'Korreksie: dit was 2026-09-08', moment="2026-09-09T22:32:00+00:00")
    assert code == 200 and "2026-09-08" in result["answer"], result
    assert result["operation_id"] != old
    stale, code = web(j, phase="confirm", operation_id=old)
    assert code == 409 and state(j)["events"] == 0
    result, code = web(j, phase="confirm", operation_id=result["operation_id"])
    assert code == 201, result
    assert str(state(j)["pig"][2]) == "2026-09-08"


def test_invalid_dates_cross_actor_and_csrf_never_mutate(journey):
    j = journey
    before = state(j)
    for day in ("2099-01-01", "2026-02-30", "2025-01-01"):
        result, code = web(j, phase="preview", event_date=day)
        assert code == 200 and result["status"] == "waiting_for_input", result
        assert state(j) == before
    result, code = web(j, phase="preview", event_date="2026-09-09")
    assert result["status"] == "preview_ready", result
    other = app.test_client()
    response = other.post(f'/api/pig-weights/pig/{j["pig"]}/lifecycle/death',
        json={"phase":"confirm","operation_id":result["operation_id"]}, headers={"X-Mortality-CSRF":j["csrf"]})
    assert response.status_code == 403
    response = j["client"].post(f'/api/pig-weights/pig/{j["pig"]}/lifecycle/death', json={"phase":"confirm","operation_id":result["operation_id"]})
    assert response.status_code == 403 and state(j) == before


def test_farm_login_signature_expiry_revocation_and_no_admin_grant(journey, monkeypatch):
    j = journey
    with j["client"].session_transaction() as session:
        assert "owner_access" not in session and session["farm_access"]["principal_id"] == j["actor"]
    proxied = app.test_client().post('/owner/telegram/login',json={'init_data':signed_init(j['actor'])},
        headers={'X-Farm-Login':'telegram','Origin':'https://localhost'})
    assert proxied.status_code == 200
    foreign = app.test_client().post('/owner/telegram/login',json={'init_data':signed_init(j['actor'])},
        headers={'X-Farm-Login':'telegram','Origin':'https://another.example'})
    assert foreign.status_code == 403
    for init in (signed_init(j["actor"],age=301), signed_init(j["actor"],token="different-bot"),
                 signed_init("123456789"), signed_init(j["actor"]) + "&auth_date=1"):
        response = app.test_client().post('/owner/telegram/login', json={"init_data":init}, headers={"X-Farm-Login":"telegram"})
        assert response.status_code == 403
    monkeypatch.setenv("OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON", "[]")
    result, code = web(j,phase="preview",event_date="2026-09-09")
    assert code == 403 and state(j)["events"] == 0


def test_application_correction_invalidates_previous_confirmation(journey):
    j = journey
    first, code = web(j, phase="preview", event_date="2026-09-09")
    assert code == 200 and first["status"] == "preview_ready"
    corrected, code = web(j, phase="preview", event_date="2026-09-08")
    assert code == 200 and corrected["status"] == "preview_ready"
    assert first["operation_id"] in corrected["invalidated_operation_ids"]
    stale, code = web(j, phase="confirm", operation_id=first["operation_id"])
    assert code == 409 and state(j)["events"] == 0


def test_unrelated_animal_change_does_not_require_reconfirming_known_facts(journey):
    j = journey
    preview, code = web(j, phase="preview", event_date="2026-09-09")
    assert code == 200 and preview["status"] == "preview_ready"
    with psycopg.connect(DSN) as db:
        db.execute("""insert into public.pigs(pig_id,tag_number,pig_name,status,on_farm,purpose)
            values(%s,%s,'Unrelated synthetic animal','Active',true,'Sale')""",
            ("PIG-UNRELATED-"+uuid.uuid4().hex,"OTHER-"+uuid.uuid4().hex))
    result, code = web(j, phase="confirm", operation_id=preview["operation_id"])
    assert code == 201, result
    assert state(j)["events"] == 1


def test_relative_death_date_survives_midnight_followup_and_duplicate_delivery(journey):
    j = journey
    text = f'Vark {j["tag"]} is gister dood.'
    first, code = telegram(j, text, moment="2026-09-08T22:30:00+00:00", message_id="MIDNIGHT-FIRST")
    assert code == 200 and "2026-09-08" in first["answer"]
    replay, code = telegram(j, text, moment="2026-09-08T22:30:00+00:00", message_id="MIDNIGHT-FIRST")
    assert code == 200 and replay["replay_suppressed"] is True
    followup, code = telegram(j, 'He was buried today.', moment="2026-09-09T22:30:00+00:00")
    assert code == 200 and followup["status"] == "preview_ready", followup
    context = next(row for row in _load_active_contexts(j["actor"],owner_user_id=j["actor"])
                   if row.get("operation_id") == followup["operation_id"])
    assert context["preview"]["evaluator"]["preview"]["event_date"] == "2026-09-08"
    assert state(j)["events"] == 0


def test_simulated_semantic_paraphrase_preserves_owner_words_until_confirmation(journey):
    j = journey
    text = f'Tag {j["tag"]} did not make it yesterday.'
    authority = issue_gateway_owner_authority(j['actor'], j['actor'],
        principal_role='farm_manager', capabilities={'mortality_confirmation'})
    result, code = handle_authenticated_health_loss_message({
        'telegram_user_id':j['actor'],'telegram_chat_id':j['actor'],
        'provider_message_id':uuid.uuid4().hex,'provider_timestamp':datetime.now(timezone.utc).isoformat(),
        'text':text,'output_language':'en',
        'semantic':{'domain':'herd_health','confidence':0.95,'needs_clarification':False,
                    'observation':f'Pig {j["tag"]} died yesterday.'}}, authority)
    assert code == 200 and result['status']=='preview_ready', result
    assert text in result['answer'] and 'Confirm to record' in result['answer']
    assert state(j)['events']==0


@pytest.mark.parametrize('followup', [
    'He was treated on 2026-09-08.',
    'Hy is op 2026-09-08 behandel.',
    'He stopped eating on 2026-09-08.',
])
def test_dated_observation_does_not_replace_retained_death_date(journey, followup):
    j = journey
    first, code = telegram(j, f'Pig {j["tag"]} died on 2026-09-09.')
    assert code == 200 and first['status'] == 'preview_ready', first
    updated, code = telegram(j, followup)
    assert code == 200 and updated['status'] == 'preview_ready', updated
    context = next(row for row in _load_active_contexts(j['actor'], owner_user_id=j['actor'])
        if row.get('operation_id') == updated['operation_id'])
    assert context['preview']['evaluator']['preview']['event_date'] == '2026-09-09'
    recorded, code = web(j, phase='confirm', operation_id=updated['operation_id'])
    assert code == 201 and recorded['event_date'] == '2026-09-09', recorded
    assert str(state(j)['pig'][2]) == '2026-09-09'
    assert followup in state(j)['pig'][3]


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_gateway_authentication_role_capability_and_protected_callback(journey, monkeypatch, transport):
    """Real ingress/claim/services; only the outbound provider adapter is simulated."""
    from modules.oom_sakkie import telegram_gateway
    from modules.oom_sakkie import telegram_direct
    j = journey
    token = 'synthetic-gateway-' + 'g' * 40
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED','true')
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN',token)
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS',j['actor']+',990000')
    card = '1235'  # Synthetic positive Telegram card ID following native input 1234.
    deliveries = []
    def simulated_provider(parsed, result, **kwargs):
        deliveries.append(result)
        return {'success':True,'status':'simulated_provider_no_send','telegram_sends':0,
                'telegram_edits':0,'telegram_message_id':card}
    monkeypatch.setattr(telegram_gateway,'deliver_family_result',simulated_provider)
    path = '/api/oom-sakkie/channels/telegram/message'
    headers={'Authorization':'Bearer '+token}
    bad_headers={'Authorization':'Bearer wrong'}
    if transport == 'direct':
        monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED','true')
        monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED','true')
        monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET',token)
        monkeypatch.setattr(telegram_direct,'deliver_family_result',simulated_provider)
        monkeypatch.setattr(telegram_direct,'acknowledge_telegram_callback',lambda *a,**kw: ({'success':True,'status':'simulated_no_provider_ack'},200))
        path='/api/oom-sakkie/channels/telegram/direct-webhook'
        headers={'X-Telegram-Bot-Api-Secret-Token':token}
        bad_headers={'X-Telegram-Bot-Api-Secret-Token':'wrong'}
    payload = {'message':{'message_id':1234,'date':int(time.time())-2,
        'from':{'id':int(j['actor'])},'chat':{'id':int(j['actor']),'type':'private'},
        'text':f'Vark {j["tag"]} is gister dood.'}}
    rejected = app.test_client().post(path,json=payload,headers=bad_headers)
    assert rejected.status_code == 403 and state(j)['events'] == 0
    response=app.test_client().post(path,json=payload,headers=headers)
    result=response.get_json()
    assert response.status_code == 200 and result['message']['status']=='preview_ready', result
    assert result['sends_telegram'] is False and state(j)['events'] == 0
    callback=result['message']['reply_markup']['inline_keyboard'][0][0]['callback_data']
    confirmation={'callback_query':{'id':'SIMULATED-CALLBACK-'+uuid.uuid4().hex,
        'from':{'id':int(j['actor'])},'data':callback,
        'message':{'message_id':int(card),'date':int(time.time()),'text':'Simulated preview card',
            'chat':{'id':int(j['actor']),'type':'private'}}}}
    foreign=json.loads(json.dumps(confirmation))
    foreign['callback_query']['from']['id']=990000
    foreign['callback_query']['message']['chat']['id']=990000
    attempt=app.test_client().post(path,json=foreign,headers=headers)
    assert attempt.status_code == 403 and state(j)['events']==0, attempt.get_json()
    response=app.test_client().post(path,json=confirmation,headers=headers)
    result=response.get_json()
    action=result.get('message',result.get('protected_action',{}))
    assert response.status_code == 201 and action['success'], action or result
    assert result['sends_telegram'] is False and state(j)['events']==1
    replay=app.test_client().post(path,json=confirmation,headers=headers)
    assert replay.status_code == 200 and state(j)['events']==1, replay.get_json()
    assert all(item.get('answer') for item in deliveries if item.get('success'))
