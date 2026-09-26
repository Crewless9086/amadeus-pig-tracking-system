"""Synthetic Ogg silence plus canned STT/meaning, real Flask and PostgreSQL.

No microphone, spoken audio, live recognition, Telegram send or hardware call.
The existing canonical writers and durable dialogue/claim/delivery stores run.
Successful recovery cases inject the transcription boundary explicitly; they do
not claim production audio is enabled. A separate case proves real budget denial.
"""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
import time
import uuid
from unittest.mock import Mock

import psycopg
import pytest

from app import app
from modules.oom_sakkie import telegram_voice as voice, telegram_gateway as gateway
from modules.oom_sakkie import semantic_front_door, voice_stt
from modules.sales import sam_live_stock_launch_control
from tests import test_litter_weaning_ingress_postgres as weaning
from tests import test_litter_first_treatment_ingress_postgres as treatment
from tests import test_herdmaster_mortality_journey_postgres as mortality
from tests import test_oom_sakkie_plan_dialogue_postgres as dialogue
from tests.test_litter_weaning_ingress_postgres import ingress as weaning_ingress
from tests.test_litter_first_treatment_ingress_postgres import ingress as treatment_ingress
from tests.test_herdmaster_mortality_journey_postgres import journey as mortality_journey
from tests.test_oom_sakkie_plan_dialogue_postgres import journey as question_journey
from tests.telegram_voice_test_support import CannedVoiceProvider, post, voice_payload


def _configure(j, monkeypatch):
    monkeypatch.setenv('OOM_SAKKIE_STT_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'SYNTHETIC-NO-PROVIDER-KEY')
    j.setdefault('deliveries', [])
    j.setdefault('token', 'SYNTHETIC-VOICE-INGRESS-' + 'v' * 40)
    j.setdefault('client', app.test_client())
    j['message_sequence'] = 2000000
    for key, value in {
        'OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED': 'true',
        'OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN': j['token'],
        'OOM_SAKKIE_TELEGRAM_DIRECT_ENABLED': 'true',
        'OOM_SAKKIE_TELEGRAM_DIRECT_SEND_ENABLED': 'true',
        'OOM_SAKKIE_TELEGRAM_WEBHOOK_SECRET': j['token'],
        'OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS': j['actor'] + ',' + os.environ['OOM_SAKKIE_TELEGRAM_OWNER_USER_ID'],
    }.items():
        monkeypatch.setenv(key, value)
    def deliver(_token, method, body, **kwargs):
        assert method in {'sendMessage', 'editMessageText', 'editMessageReplyMarkup', 'answerCallbackQuery'}
        if method == 'answerCallbackQuery':
            return {'ok': True, 'result': True}
        j['message_sequence'] += 1
        card = str(body.get('message_id') or j['message_sequence'])
        j['deliveries'].append({'method': method, 'body': dict(body), 'message_id': card})
        return {'ok': True, 'result': {'message_id': card, 'date': int(time.time()),
            'chat': {'id': int(j['actor']), 'type': 'private'}, 'text': body.get('text', '')}}
    monkeypatch.setattr(sam_live_stock_launch_control, '_telegram_api', deliver)
    from modules.oom_sakkie import telegram_direct
    monkeypatch.setattr(telegram_direct, 'acknowledge_telegram_callback',
        lambda *a, **k: ({'success': True, 'status': 'SYNTHETIC-ACK'}, 200))


def _canned_transcription(monkeypatch, provider):
    # Qualify downstream recovery without bypassing the production budget guard.
    def transcribe(audio_bytes, content_type, policy, **kwargs):
        assert audio_bytes == provider.audio
        assert kwargs['language'] == provider.language
        return provider.transcript
    monkeypatch.setattr(voice_stt, '_call_openai_transcription', transcribe)


def _voice(j, monkeypatch, transport, transcript, *, reply=''):
    j['message_sequence'] += 10
    payload = voice_payload(j['actor'], j['message_sequence'], reply=reply)
    principal = voice._authorize_native(payload, gateway.parse_telegram_gateway_payload(payload), os.environ)
    provider = CannedVoiceProvider(payload, transcript, language=principal.language)
    _canned_transcription(monkeypatch, provider)
    monkeypatch.setattr(voice.urllib.request, 'build_opener', lambda *a: provider)
    response = post(j['client'], transport, payload, secret=j['token'])
    return response, payload, provider


def _input_rows(payload):
    # Inspect the raw provider identity independently, including rejected envelopes.
    message = payload['message']
    identity = voice._receipt_id({'telegram_user_id': str(message['from']['id']),
        'telegram_chat_id': str(message['chat']['id']),
        'provider_message_id': str(message['message_id'])})
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        return dict(db.execute("""select review_event_id,review_json->'telegram_voice_input'
            from public.sam_live_stock_conversation_review_events where review_event_id=any(%s)""",
            ([identity + ':start', identity + ':result'],)).fetchall())


def _retained(payload):
    rows = _input_rows(payload)
    return next(row for identity, row in rows.items() if identity.endswith(':result'))


def _callback(j, preview, card):
    return {'callback_query': {'id': 'SYNTHETIC-VOICE-CB-' + uuid.uuid4().hex,
        'from': {'id': int(j['actor'])},
        'data': preview['reply_markup']['inline_keyboard'][0][0]['callback_data'],
        'message': {'message_id': card, 'date': int(time.time()),
            'chat': {'id': int(j['actor']), 'type': 'private'}, 'text': 'SYNTHETIC preview'}}}


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
@pytest.mark.parametrize('invalid', ['credential', 'unknown', 'group', 'override', 'caption', 'callback', 'stale'])
def test_real_route_authorizes_native_family_before_download_or_stt(weaning_ingress, monkeypatch, transport, invalid):
    j = weaning_ingress; _configure(j, monkeypatch)
    payload = voice_payload(j['actor'])
    if invalid == 'unknown':
        payload['message']['from']['id'] = 123456
        payload['message']['chat']['id'] = 123456
    elif invalid == 'group':
        payload['message']['chat'] = {'id': -100456, 'type': 'supergroup'}
    elif invalid == 'override':
        payload['message']['from']['id'] = 123456
        payload['telegram_user_id'] = j['actor']
    elif invalid == 'caption':
        payload['message']['caption'] = 'SYNTHETIC supplied transcript'
    elif invalid == 'callback':
        payload['callback_data'] = 'oompa:SYNTHETIC:confirm'
        payload['telegram_user_id'] = j['actor']
        payload['telegram_chat_id'] = j['actor']
    elif invalid == 'stale':
        payload['message']['date'] -= 7 * 3600
    opener = Mock(side_effect=AssertionError('Provider before authorization'))
    monkeypatch.setattr(voice.urllib.request, 'build_opener', opener)
    claim = Mock(side_effect=AssertionError('Rejected voice must not create an input claim'))
    monkeypatch.setattr(voice, '_claim_input', claim)
    before = weaning.state(j)
    response = post(j['client'], transport, payload, secret=j['token'], bad_auth=invalid == 'credential')
    expected = {
        'credential': (403, 'telegram_gateway_auth_denied' if transport == 'gateway' else 'telegram_direct_auth_denied'),
        'unknown': (403, 'telegram_user_not_allowed'),
        'group': (403, 'telegram_family_identity_not_authorized'),
        'override': (400, 'telegram_native_flat_conflict'),
        'caption': (415, 'telegram_voice_separate_text_required'),
        'callback': (400, 'telegram_native_flat_conflict'),
        'stale': (403, 'telegram_voice_private_family_authority_required'),
    }[invalid]
    assert (response.status_code, response.get_json()['status']) == expected, response.get_json()
    assert response.get_json()['success'] is False
    opener.assert_not_called(); claim.assert_not_called()
    if invalid == 'caption':
        # The authenticated sender still receives the existing localized format notice.
        assert len(j['deliveries']) == 1 and j['deliveries'][0]['method'] == 'sendMessage'
    else:
        assert not j['deliveries']
    assert not _input_rows(payload) and weaning.state(j) == before


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_voice_weaning_retains_short_reply_previews_and_only_button_commits(weaning_ingress, monkeypatch, transport):
    j = weaning_ingress; _configure(j, monkeypatch)
    before = weaning.state(j)
    weaning.semantic(monkeypatch, {'sow_ref': j['sow'], 'action_date': 'gister', 'notes': 'Almal drink water.'})
    response, first, provider = _voice(j, monkeypatch, transport, 'Die varkies is gister gespeen. Almal drink water.')
    assert response.status_code == 200 and weaning.action(response)['question_count'] == 1, response.get_json()
    assert len(provider.requests) == 2 and weaning.state(j) == before
    weaning.semantic(monkeypatch, {'scope': 'all_current'}, continuation=True)
    response, second, provider = _voice(j, monkeypatch, transport, 'Ja, almal in die werpsel.')
    preview = weaning.action(response); card = j['deliveries'][-1]['message_id']
    assert response.status_code == 200 and preview['status'] == 'litter_weaning_preview_ready', response.get_json()
    assert preview['retained_facts']['notes'] == 'Almal drink water.'
    retained = _retained(first)
    assert retained['status'] == 'transcribed' and retained['provenance']['language'] == 'af'
    assert retained['binding']['provider_message_id'] == str(first['message']['message_id'])
    assert retained['provenance']['reported_input_only'] and not retained['provenance']['stores_audio']
    sent = len(j['deliveries'])
    repeat = post(j['client'], transport, second, secret=j['token'])
    assert repeat.status_code == 200 and len(provider.requests) == 2 and len(j['deliveries']) == sent
    cross_route = post(j['client'], 'direct' if transport == 'gateway' else 'gateway', second, secret=j['token'])
    assert cross_route.status_code == 200 and len(provider.requests) == 2 and len(j['deliveries']) == sent
    weaning.semantic(monkeypatch, {}, continuation=True, message_kind='confirmation')
    response, consent, provider = _voice(j, monkeypatch, transport, 'Ja, teken daardie presiese feite aan.', reply=card)
    assert weaning.action(response)['status'] == 'telegram_voice_preview_button_required', response.get_json()
    assert weaning.state(j) == before
    confirmed = post(j['client'], transport, _callback(j, preview, card), secret=j['token'])
    assert confirmed.status_code == 200 and weaning.action(confirmed)['canonical_readback_verified'], confirmed.get_json()
    after = weaning.state(j)
    assert after['receipts'] == 1 and after['pigs'][2:] == before['pigs'][2:]
    assert after['active_herd'] == before['active_herd'] and after['sow'] == before['sow']


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_voice_first_treatment_correction_keeps_facts_and_requires_button(treatment_ingress, monkeypatch, transport):
    j = treatment_ingress; _configure(j, monkeypatch)
    before = treatment.state(j)
    facts = treatment.facts(j); facts.pop('route')
    treatment.semantic(monkeypatch, facts)
    response, first, _ = _voice(j, monkeypatch, transport, 'Eerste behandeling gedoen: een ml, gemerk, een van elke geslag.')
    assert response.status_code == 200 and treatment.action(response)['question_count'] == 1, response.get_json()
    treatment.semantic(monkeypatch, {'route': 'injection', 'dose': '1,5 ml'}, continuation=True, message_kind='correction')
    response, _, _ = _voice(j, monkeypatch, transport, 'Ingespuit; die dosis was eintlik een komma vyf ml.')
    preview = treatment.action(response); card = j['deliveries'][-1]['message_id']
    assert preview['status'] == 'litter_first_treatment_preview_ready', response.get_json()
    assert preview['retained_facts']['earmarked'] and preview['retained_facts']['action_date'] == j['date']
    assert treatment.state(j) == before
    treatment.semantic(monkeypatch, {}, continuation=True, message_kind='confirmation')
    response, _, _ = _voice(j, monkeypatch, transport, 'Ja, teken dit aan.', reply=card)
    assert treatment.action(response)['status'] == 'telegram_voice_preview_button_required', response.get_json()
    assert treatment.state(j) == before
    callback = _callback(j, preview, card)
    confirmed = post(j['client'], transport, callback, secret=j['token'])
    assert confirmed.status_code == 200 and treatment.action(confirmed)['canonical_readback_verified'], confirmed.get_json()
    after = treatment.state(j)
    assert len(after['receipts']) == 1 and len(after['medical']) == 2
    assert all(float(row[3]) == 1.5 and row[6] == j['actor'] for row in after['medical'])
    sent = len(j['deliveries'])
    repeated = post(j['client'], transport, callback, secret=j['token'])
    assert repeated.status_code == 200 and treatment.state(j) == after and len(j['deliveries']) == sent


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_voice_mortality_uses_original_identity_and_existing_canonical_writer(mortality_journey, monkeypatch, transport):
    j = mortality_journey; _configure(j, monkeypatch)
    binding = json.loads(os.environ['OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON'])
    binding[0]['permissions'].append('mortality_confirmation')
    monkeypatch.setenv('OOM_SAKKIE_FAMILY_ACCESS_BINDINGS_JSON', json.dumps(binding))
    monkeypatch.setattr(gateway, 'interpret_owner_message', lambda *a, **k: None)
    monkeypatch.setattr(semantic_front_door, 'interpret_owner_message', lambda *a, **k: None)
    before = mortality.state(j)
    response, original, provider = _voice(j, monkeypatch, transport, f'Vark {j["tag"]} is gister dood. Nog nie begrawe nie.')
    preview = weaning.action(response); card = j['deliveries'][-1]['message_id']
    assert response.status_code == 200 and preview['status'] == 'preview_ready', response.get_json()
    assert mortality.state(j) == before and len(provider.requests) == 2
    confirmed = post(j['client'], transport, _callback(j, preview, card), secret=j['token'])
    assert confirmed.status_code == 201, confirmed.get_json()
    after = mortality.state(j)
    assert after['pig'][:2] == ('Dead', False) and after['events'] == 1
    assert after['active_count'] == before['active_count'] - 1 and after['weights'] == before['weights']
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        event = db.execute('select actor_reference,event_payload from public.pig_lifecycle_events where pig_id=%s', (j['pig'],)).fetchone()
        assert event[0] == j['actor'] and event[1]['removal'] == {}
    retained = _retained(original)
    assert retained['text'].endswith('Nog nie begrawe nie.') and retained['provenance']['reported_input_only']


def test_recognition_is_retained_before_semantic_failure_and_retry_never_retranscribes(weaning_ingress, monkeypatch):
    j = weaning_ingress; _configure(j, monkeypatch)
    monkeypatch.setattr(gateway, 'interpret_owner_message', Mock(side_effect=RuntimeError('SYNTHETIC semantic interruption')))
    response, original, provider = _voice(j, monkeypatch, 'gateway', 'Die hele werpsel is gister gespeen.')
    assert response.status_code >= 500
    assert _retained(original)['status'] == 'transcribed' and len(provider.requests) == 2
    weaning.semantic(monkeypatch, {'sow_ref': j['sow'], 'action_date': 'gister', 'scope': 'all_current'})
    response = post(j['client'], 'gateway', original, secret=j['token'])
    assert response.status_code == 200 and weaning.action(response)['status'] == 'litter_weaning_preview_ready', response.get_json()
    assert len(provider.requests) == 2 and weaning.state(j)['receipts'] == 0


def test_started_attempt_and_changed_provider_binding_never_repeat_provider_work(weaning_ingress, monkeypatch):
    j = weaning_ingress; _configure(j, monkeypatch)
    payload = voice_payload(j['actor'])
    parsed = gateway.parse_telegram_gateway_payload(payload)
    principal = voice._authorize_native(payload, parsed, os.environ)
    voice._claim_input(voice._receipt_id(parsed), voice._binding(payload, parsed, principal), os.environ)
    opener = Mock(side_effect=AssertionError('Uncertain recognition must not retry'))
    monkeypatch.setattr(voice.urllib.request, 'build_opener', opener)
    response = post(j['client'], 'gateway', payload, secret=j['token'])
    assert response.status_code == 503 and response.get_json()['status'] == 'telegram_voice_attempt_processing'
    changed = copy.deepcopy(payload); changed['message']['voice']['file_id'] += '-CHANGED'
    response = post(j['client'], 'direct', changed, secret=j['token'])
    assert response.status_code == 409 and response.get_json()['status'] == 'telegram_voice_replay_binding_conflict'
    opener.assert_not_called()
    assert len(_input_rows(payload)) == 1 and weaning.state(j)['receipts'] == 0


@pytest.mark.parametrize('individual', [False, True])
def test_spoken_ja_replies_to_delivered_daily_question_and_keeps_prior_facts(question_journey, monkeypatch, individual):
    j = question_journey
    # Existing daily-question clock is moved to this request's real freshness window.
    moment = datetime.now(timezone.utc).replace(microsecond=0) - timedelta(minutes=3)
    monkeypatch.setattr(dialogue, 'NOW', moment)
    # This voice-reply journey requires a delivered question at a fresh real
    # timestamp, even when CI runs before 06:45. Scheduling has separate gates.
    monkeypatch.setattr(dialogue.daily, 'MORNING_HOUR', 0)
    monkeypatch.setattr(dialogue.daily, 'MORNING_MINUTE', 0)
    j['provider_clock'][0] = moment
    monkeypatch.setenv('OOM_SAKKIE_STT_ENABLED', 'true')
    monkeypatch.setenv('OPENAI_API_KEY', 'SYNTHETIC-NO-PROVIDER-KEY')
    result, question = dialogue.present(j, j['actor'], 'af', individual=individual)
    partial, status = dialogue.reply(j, j['actor'], 'af', 'Hy eet.', 701,
        moment + timedelta(minutes=1), question['telegram_message_id'], partial=True)
    assert status == 200 and partial['status'] == 'manager_question_partial_reply_recorded', partial
    card = partial['delivery']['telegram_message_id']
    j['semantic']['value'] = semantic_front_door.SemanticInterpretation(domain='herd_health', intent='welfare_follow_up',
        message_kind='observation', continuation=True, observation='Hy staan en drink water.',
        welfare_observation={'standing': 'yes', 'drinking': 'yes'}, language='af', confidence=.99)
    payload = voice_payload(j['actor'], 702, reply=int(card))
    payload['message']['date'] = int((moment + timedelta(minutes=2)).timestamp())
    j['provider_clock'][0] = moment + timedelta(minutes=2)
    provider = CannedVoiceProvider(payload, 'Ja.')
    _canned_transcription(monkeypatch, provider)
    monkeypatch.setattr(voice.urllib.request, 'build_opener', lambda *a: provider)
    real_interpret = gateway.interpret_owner_message
    def interpret(parsed, **kwargs):
        assert parsed['input_provenance']['source_kind'] == 'telegram_voice'
        assert _retained(payload)['status'] == 'transcribed'
        return real_interpret(parsed, **kwargs)
    monkeypatch.setattr(gateway, 'interpret_owner_message', interpret)
    if individual:
        from modules.oom_sakkie import herdmaster_health_loss_runtime as health
        real_health = health.handle_authenticated_health_loss_message
        def specialist(parsed, authority, **kwargs):
            assert parsed['input_provenance']['source_kind'] == 'telegram_voice'
            return real_health(parsed, authority, **kwargs)
        monkeypatch.setattr(health, 'handle_authenticated_health_loss_message', specialist)
    response = post(app.test_client(), 'gateway', payload, secret=j['token'])
    body = response.get_json()
    assert response.status_code == 200, body
    assert body['message']['status'] == ('preview_ready' if individual else 'manager_question_reply_recorded'), body
    assert j['contexts'][-1]['recent_turns'][-1]['clarification_question']
    receipts = dialogue.daily._load_answered_questions({'owner_user_id': j['actor'], 'chat_id': j['actor'],
        'daily_identity': question['daily_identity']})
    assert len(receipts) == 1 and len(receipts[0]['accumulated_semantic_facts']['observations']) == 2
    assert receipts[0]['accumulated_semantic_facts']['welfare_observation'] == {'eating': 'yes', 'standing': 'yes', 'drinking': 'yes'}
    assert dialogue.questions._load_questions(j['actor'], j['actor']) == []
    sent = len(j['provider'])
    duplicate = post(app.test_client(), 'gateway', payload, secret=j['token'])
    assert duplicate.status_code == 200 and len(provider.requests) == 2 and len(j['provider']) == sent
    assert _retained(payload)['text'] == 'Ja.'
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        assert db.execute('select count(*) from public.pig_observation_events where pig_id=%s', (j['pig'],)).fetchone()[0] == 0


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_voice_rootline_confirmation_leaves_real_protected_claim_unconsumed(weaning_ingress, monkeypatch, transport):
    from modules.oom_sakkie.protected_action_claims import create_claim, bind_claim_card
    j = weaning_ingress; _configure(j, monkeypatch)
    mission = 'SYNTHETIC-VOICE-ROOTLINE-' + uuid.uuid4().hex
    claim = create_claim(action_kind='rootline_irrigation_segment', owner_user_id=j['actor'],
        private_chat_id=j['actor'], mission_id=mission, provider_message_id='SYNTHETIC-PREVIEW',
        evidence_generation='SYNTHETIC-ONLY', preview_payload={'contract_version': 'SYNTHETIC-ROOTLINE'})
    assert bind_claim_card(claim['callback_token'], '1999000')
    from modules.oom_sakkie import protected_action_runtime
    claim_callback = Mock(side_effect=AssertionError('Voice must not claim or execute ROOTLINE'))
    monkeypatch.setattr(protected_action_runtime, 'claim_callback', claim_callback)
    response, _, _ = _voice(j, monkeypatch, transport, 'Ek bevestig alles.', reply='1999000')
    assert response.status_code == 200 and weaning.action(response)['status'] == 'telegram_voice_preview_button_required', response.get_json()
    claim_callback.assert_not_called()
    with psycopg.connect(os.environ['DATABASE_URL']) as db:
        assert db.execute('select status,confirmation_provider_message_id from app_private.oom_protected_action_claims where callback_token=%s',
            (claim['callback_token'],)).fetchone() == ('active', None)


def test_voice_standing_authority_mixer_request_never_constructs_transport(weaning_ingress, monkeypatch):
    from modules.oom_sakkie import rootline_fertilizer_commissioning_runtime as mixer
    j = weaning_ingress; _configure(j, monkeypatch)
    # Use a fresh actual owner principal for the standing-authority route.
    j['actor'] = str(9100000000 + int(uuid.uuid4().hex[:7], 16))
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_OWNER_USER_ID', j['actor'])
    monkeypatch.setenv('OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS', j['actor'])
    semantic = semantic_front_door.SemanticInterpretation(domain='rootline', intent='commission_fertilizer_mixer',
        message_kind='command', requested_action='start', language='en', confidence=.99)
    monkeypatch.setattr(gateway, 'interpret_owner_message', lambda *a, **k: semantic)
    def accepted(parsed, authority):
        assert authority.principal_role == 'owner'
        assert parsed['input_provenance']['source_kind'] == 'telegram_voice'
        return {'handled': True, 'success': True, 'status': 'specialist_accepted',
            'next_specialist_step': 'supervised_fertilizer_mixer_proof', 'ready_for_supervised_proof': True}, 200
    # Only the specialist acceptance is canned; the real gateway execution entrance runs.
    monkeypatch.setattr(gateway, 'handle_operational_specialist_message', accepted)
    transport = Mock(side_effect=AssertionError('No voice execution transport'))
    monkeypatch.setattr(mixer, 'RootlineIFTTTTransport', transport)
    response, _, provider = _voice(j, monkeypatch, 'gateway', 'Start the mixer.')
    assert response.status_code == 200 and weaning.action(response)['status'] == 'telegram_voice_preview_button_required', response.get_json()
    assert weaning.action(response)['hardware_commands'] == 0 and len(provider.requests) == 2
    transport.assert_not_called()


def test_authenticated_voice_cannot_mint_delegated_irrigation_execution(weaning_ingress, monkeypatch):
    from modules.oom_sakkie.family_specialist_adapters import rootline_family_handoff
    j = weaning_ingress; _configure(j, monkeypatch)
    payload = voice_payload(j['actor'])
    provider = CannedVoiceProvider(payload, 'Begin die besproeiing.')
    _canned_transcription(monkeypatch, provider)
    monkeypatch.setattr(voice.urllib.request, 'build_opener', lambda *a: provider)
    parsed, failure = voice.prepare_telegram_voice_input(payload, gateway.parse_telegram_gateway_payload(payload))
    assert failure is None
    principal = voice._authorize_native(payload, gateway.parse_telegram_gateway_payload(payload), os.environ)
    execution = Mock(side_effect=AssertionError('No delegated voice execution'))
    result = rootline_family_handoff(parsed=parsed, principal=principal, capability='irrigation_start',
        replay_identity='SYNTHETIC-VOICE', authorization_loader=execution, eligibility_loader=execution, executor=execution)
    assert result['status'] == 'telegram_voice_preview_button_required' and result['hardware_commands'] == 0
    execution.assert_not_called()


def test_voice_reported_stop_keeps_existing_verification_pending_semantics(weaning_ingress, monkeypatch):
    from modules.oom_sakkie import owner_operational_continuation as continuation
    from tests.test_oom_sakkie_owner_operational_continuation import c_active, memory_store
    j = weaning_ingress; _configure(j, monkeypatch)
    semantic = semantic_front_door.SemanticInterpretation(domain='rootline', intent='irrigation_observation',
        message_kind='observation', irrigation_observation={'zone_id': 'C12345', 'state': 'stopped'},
        observation='C Kamp het gestop.', language='af', confidence=.99)
    monkeypatch.setattr(gateway, 'interpret_owner_message', lambda *a, **k: semantic)
    rows, store = memory_store()
    identity = 'SYNTHETIC-STOP-' + uuid.uuid4().hex
    active = {**c_active(), 'mission_id': identity, 'card_mission_id': identity + '-CARD',
        'completion_card_mission_id': identity + '-COMPLETION', 'execution_id': identity + '-EXECUTION',
        'execution_started_at': (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()}
    monkeypatch.setattr(continuation, '_load_active_context', lambda *a: ([], [active], list(rows.values())))
    monkeypatch.setattr(continuation, '_context_store', store)
    response, payload, _ = _voice(j, monkeypatch, 'gateway', 'C Kamp het gestop.')
    result = weaning.action(response)
    assert response.status_code == 200 and result['status'] == 'owner_irrigation_observation_recorded', response.get_json()
    assert result['verification_pending'] and result['execution_completed'] is False and result['hardware_commands'] == 0
    assert next(iter(rows.values()))['state'] == 'physical_stop_reported'
    assert _retained(payload)['provenance']['reported_input_only']


@pytest.mark.parametrize('fault', ['provider', 'retention'])
def test_failed_or_uncertain_recognition_has_durable_non_retranscribing_replay(weaning_ingress, monkeypatch, fault):
    j = weaning_ingress; _configure(j, monkeypatch)
    payload = voice_payload(j['actor'])
    provider = CannedVoiceProvider(payload, 'SYNTHETIC transcript never dispatched')
    if fault == 'provider':
        opener = Mock(side_effect=OSError('SYNTHETIC provider unavailable'))
        monkeypatch.setattr(voice.urllib.request, 'build_opener', opener)
    else:
        _canned_transcription(monkeypatch, provider)
        monkeypatch.setattr(voice.urllib.request, 'build_opener', lambda *a: provider)
        monkeypatch.setattr(voice, '_retain_input', Mock(side_effect=RuntimeError('SYNTHETIC interrupted result retention')))
    before = weaning.state(j)
    response = post(j['client'], 'gateway', payload, secret=j['token'])
    assert response.status_code in {502, 503} and 'nuwe Telegram-stemnota' in response.get_json()['answer'], response.get_json()
    snapshot = _input_rows(payload)
    repeated = post(j['client'], 'direct', payload, secret=j['token'])
    assert repeated.status_code in {502, 503}, repeated.get_json()
    assert _input_rows(payload) == snapshot and weaning.state(j) == before
    if fault == 'provider':
        assert opener.call_count == 1 and _retained(payload)['status'] == 'failed'
    else:
        assert len(provider.requests) == 2 and len(snapshot) == 1


@pytest.mark.parametrize('transport', ['gateway', 'direct'])
def test_unpriced_voice_is_denied_without_paid_call_or_farm_write(weaning_ingress, monkeypatch, transport):
    j = weaning_ingress; _configure(j, monkeypatch)
    payload = voice_payload(j['actor'])
    provider = CannedVoiceProvider(payload, 'Must never be transcribed')
    # Keep the real transcription and budget boundary for this case.
    monkeypatch.setattr(voice.urllib.request, 'build_opener', lambda *a: provider)
    before = weaning.state(j)
    response = post(j['client'], transport, payload, secret=j['token'])
    assert response.status_code == 503, response.get_json()
    assert response.get_json()['status'] == 'farm_model_budget_endpoint_unpriced'
    assert 'Tik asseblief' in response.get_json()['answer']
    assert len(provider.requests) == 2
    assert _retained(payload)['failure_status'] == 'farm_model_budget_endpoint_unpriced'
    sent = len(j['deliveries'])
    snapshot = _input_rows(payload)
    repeat = post(j['client'], 'direct' if transport == 'gateway' else 'gateway', payload, secret=j['token'])
    assert repeat.status_code == 503
    assert len(provider.requests) == 2 and len(j['deliveries']) == sent
    assert _input_rows(payload) == snapshot and weaning.state(j) == before
