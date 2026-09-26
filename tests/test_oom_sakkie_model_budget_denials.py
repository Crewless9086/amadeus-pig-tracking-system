"""Real budget-wrapper denials with inert delivery/ledger boundaries only."""
import io
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from modules.oom_sakkie import model_budget as budget
from modules.oom_sakkie import semantic_front_door as semantic
from modules.oom_sakkie import service, telegram_gateway as gateway, telegram_voice as voice
from modules.oom_sakkie import voice_stt, family_message_lifecycle as family
from modules.charlie import private_media, private_voice, private_runtime
from tests.test_oom_sakkie_conversation_followup import journey, interpretation
from tests.test_charlie_private_runtime import FakeStore, ENV as CHARLIE_ENV, HEADERS

CODES = ('farm_model_daily_budget_exhausted', 'farm_model_budget_store_unavailable',
         'farm_model_budget_multimodal_unpriced')
ENV = {'OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED': '1',
    'OOM_SAKKIE_LLM_ROUTER_MODEL': 'gpt-4.1-mini', 'OPENAI_API_KEY': 'synthetic-only'}


@pytest.fixture(autouse=True)
def no_external_connection(monkeypatch):
    import psycopg
    import socket
    monkeypatch.setattr(psycopg, 'connect', Mock(side_effect=AssertionError('no database')))
    monkeypatch.setattr(socket, 'create_connection', Mock(side_effect=AssertionError('no network')))


def deny_ledger(monkeypatch, code):
    ledger = SimpleNamespace(reserve=Mock(side_effect=budget.ModelBudgetError(code)))
    monkeypatch.setattr(budget, '_default_store', lambda _source: ledger)
    return ledger


@pytest.mark.parametrize('language', ['en', 'af'])
@pytest.mark.parametrize('code', CODES)
def test_gateway_budget_denial_is_visible_localized_and_same_receipt_is_silent(journey, monkeypatch, code, language):
    ledger = deny_ledger(monkeypatch, code)
    monkeypatch.setenv('OOM_SAKKIE_LLM_ROUTER_MODEL', 'gpt-4.1-mini')
    fallback = Mock(side_effect=AssertionError('no broad fallback or specialist execution'))
    monkeypatch.setattr(gateway, 'handle_message', fallback)
    first, status = journey.send('What is Pig702 status?', interpretation('animal_status', language, subject='702'))
    assert status == 200 and first['success'] is False
    assert first['model_budget_denied'] is True and first['status'] == code
    assert first['request_interpreted'] is False and first['writes'] is False
    assert first['records_audit_trace'] is True
    assert len(journey.sends) == 1 and journey.sends[0][1] == first['answer']
    assert ('AI-KOSTEBEHEER' if language == 'af' else 'AI COST CONTROL') in first['answer']
    if code == 'farm_model_daily_budget_exhausted':
        assert 'US$1' in first['answer']
    elif code == 'farm_model_budget_store_unavailable':
        assert ('Dit beteken nie' if language == 'af' else 'This does not mean') in first['answer']
    else:
        assert ('nog nie' if language == 'af' else 'not yet supported') in first['answer']
    second, status = journey.send('What is Pig702 status?', interpretation('animal_status', language, subject='702'))
    assert status == 200 and len(journey.sends) == 1
    assert second['delivery']['telegram_sends'] == 0
    assert second['delivery']['status'] == 'family_message_provider_replay_noop'
    assert ledger.reserve.call_count == 2 and journey.payloads == []
    assert journey.connection.calls == [] and journey.claim.call_count == 0
    fallback.assert_not_called()


def test_budget_notice_ambiguous_delivery_does_not_send_again(journey, monkeypatch):
    deny_ledger(monkeypatch, CODES[0]); monkeypatch.setenv('OOM_SAKKIE_LLM_ROUTER_MODEL', 'gpt-4.1-mini')
    sender = Mock(return_value={'success': False, 'status': 'telegram_delivery_ambiguous'})
    monkeypatch.setattr(family, '_send_telegram', sender)
    first, status = journey.send('Farm status', interpretation())
    assert status == 503 and first['records_audit_trace'] is False
    assert first['answer'] and not first['delivery'].get('delivery_definitely_not_sent')
    second, status = journey.send('Farm status', interpretation())
    assert status == 503 and second['delivery']['telegram_sends'] == 0
    assert sender.call_count == 1 and journey.payloads == []


def test_budget_notice_store_failure_never_claims_delivery_or_audit(journey, monkeypatch):
    deny_ledger(monkeypatch, CODES[1]); monkeypatch.setenv('OOM_SAKKIE_LLM_ROUTER_MODEL', 'gpt-4.1-mini')
    monkeypatch.setattr(family, '_event_store', lambda action, *_args: [] if action == 'load' else {'success': False})
    result, status = journey.send('Farm status', interpretation())
    assert status == 503 and result['answer'] and result['records_audit_trace'] is False
    assert result['sends_telegram'] is False and journey.sends == [] and journey.payloads == []


def test_existing_protected_replay_precedes_the_denied_model(journey, monkeypatch):
    interpreter = Mock(side_effect=AssertionError('protected receipt must not call semantic model'))
    monkeypatch.setattr(gateway, 'interpret_owner_message', interpreter)
    monkeypatch.setattr(gateway, 'handle_protected_action_input', lambda *_a: (
        {'handled': True, 'success': True, 'status': 'protected_action_replayed',
         'suppress_owner_delivery': True, 'writes_farm_data': False}, 200))
    result, status = journey.send('confirm', interpretation())
    assert status == 200 and result['status'] == 'protected_action_replayed'
    interpreter.assert_not_called()
    assert journey.sends == []


@pytest.mark.parametrize('code', CODES)
def test_real_owner_semantic_rethrows_safe_budget_denial_without_provider(monkeypatch, code):
    ledger = deny_ledger(monkeypatch, code)
    provider = Mock(side_effect=AssertionError('paid transport must not be entered'))
    with pytest.raises(budget.ModelBudgetError) as error:
        semantic.interpret_owner_message({'text': 'Farm status'}, environ=ENV,
            context_loader=lambda _parsed: {}, http_open=provider)
    assert error.value.status == code and ledger.reserve.call_count == 1
    provider.assert_not_called()
    # Optional media classification remains the existing safe None result.
    assert semantic.interpret_media_owner_context('Current pigs', 'a' * 64,
        environ=ENV, http_open=provider) is None
    provider.assert_not_called()


@pytest.mark.parametrize('language', ['en', 'af'])
def test_real_unpriced_oom_audio_returns_typed_text_only_without_provider(monkeypatch, language):
    provider = Mock(side_effect=AssertionError('unpriced audio must not call OpenAI'))
    audio = io.BytesIO(b'synthetic audio'); audio.mimetype = 'audio/ogg'
    result, status = voice_stt.transcribe_oom_sakkie_voice_audio(audio,
        environ={'OOM_SAKKIE_STT_ENABLED': '1', 'OPENAI_API_KEY': 'synthetic'},
        language=language, http_open=provider)
    assert status == 503 and result['status'] == 'farm_model_budget_endpoint_unpriced'
    assert result['model_budget_denied'] is True and result['text_only'] is True
    provider.assert_not_called()
    notice, code = voice._failure(voice.VoiceFailure(result['status'], status), language)
    assert code == 503 and ('Tik asseblief' if language == 'af' else 'Please type') in notice['answer']
    assert 'Send a new' not in notice['answer'] and 'Stuur' not in notice['answer']
    localized = family.localize_recipient_result({'output_language': language}, notice, 'OOM_SAKKIE')
    assert localized['answer'] == notice['answer']
    assert not localized.get('recipient_language_render_unrecognized')


@pytest.mark.parametrize('language', ['en', 'af'])
def test_real_charlie_audio_wrappers_preserve_unpriced_reason_and_never_post(language):
    client = Mock()
    client.get.side_effect = [SimpleNamespace(raise_for_status=lambda: None,
        json=lambda: {'result': {'file_path': 'voice/synthetic.ogg'}}),
        SimpleNamespace(raise_for_status=lambda: None, content=b'synthetic')]
    source = {'OPENAI_API_KEY': 'synthetic', 'OOM_SAKKIE_TELEGRAM_OWNER_LANGUAGE': language}
    policy = {'transcription_enabled': True, 'transcription_model': 'whisper-1', 'token': 'synthetic'}
    web, code = private_voice.transcribe_web_audio(b'synthetic', 'voice.ogg', 'audio/ogg',
        policy, environ=source, http_client=client)
    telegram = private_media.transcribe_voice([{'kind': 'voice', 'file_id': 'inert', 'file_size': 9}],
        policy, environ=source, http_client=client)
    assert code == 503
    for result in (web, telegram):
        assert result['status'] == 'farm_model_budget_endpoint_unpriced'
        assert result['text'] == '' and result['text_only'] is True
        assert ('Tik asseblief' if language == 'af' else 'Please type') in result['answer']
    client.post.assert_not_called()


def test_charlie_private_voice_denial_is_truthful_and_duplicate_update_is_silent(monkeypatch):
    store = FakeStore(); sent = []
    notice = service.model_budget_denial_result('farm_model_budget_endpoint_unpriced', voice=True)
    monkeypatch.setattr(private_runtime, 'transcribe_voice', lambda *_a, **_kw: {
        'text': '', 'status': notice['status'], 'answer': notice['answer'], 'model_budget_denied': True})
    planner = Mock(side_effect=AssertionError('denied voice must not execute a model or tool'))
    monkeypatch.setattr(private_runtime, 'plan_owner_intent', planner)
    update = {'update_id': 981, 'message': {'message_id': 982, 'from': {'id': 10},
        'chat': {'id': 10, 'type': 'private'}, 'voice': {'file_id': 'inert', 'file_size': 9}}}
    def sender(chat, text, **_kw):
        sent.append(text); return {'success': True, 'status': 'sent'}, 200
    first, code = private_runtime.handle_private_telegram_webhook(update, HEADERS,
        environ=CHARLIE_ENV, sender=sender, store=store)
    assert code == 200 and first['model_budget_denied'] is True and first['action_status_code'] == 503
    assert 'not enabled yet' not in first['reply'] and 'Please type' in first['reply']
    assert '<b>' not in first['reply'] and '<b>' not in sent[0]
    replay, code = private_runtime.handle_private_telegram_webhook(update, HEADERS,
        environ=CHARLIE_ENV, sender=sender, store=store)
    assert code == 200 and replay['status'] == 'duplicate_update_ignored' and len(sent) == 1
    planner.assert_not_called()


def test_exact_direct_help_command_remains_available_without_semantic_model(monkeypatch):
    from modules.oom_sakkie import telegram_direct as direct
    from modules.oom_sakkie import herdmaster_health_loss_runtime as health
    from modules.oom_sakkie import herdmaster_litter_weaning_runtime as weaning
    from modules.oom_sakkie import herdmaster_litter_first_treatment_runtime as treatment
    from tests.telegram_voice_test_support import environment, SECRET, OWNER
    source = {**environment(), **ENV}
    denied = Mock(side_effect=budget.ModelBudgetError(CODES[0]))
    monkeypatch.setattr(semantic, 'interpret_owner_message', denied)
    for module, name in ((direct, 'handle_protected_action_input'),
        (health, 'handle_authenticated_health_loss_message'), (weaning, 'handle_litter_weaning_message'),
        (treatment, 'handle_litter_first_treatment_message')):
        monkeypatch.setattr(module, name, lambda *_a, **_kw: ({'handled': False}, 200))
    monkeypatch.setattr(direct, 'handle_owner_task_input', lambda *_a, **_kw: ({'handled': False}, 200))
    send = Mock(return_value=({'success': True, 'status': 'sent'}, 200))
    monkeypatch.setattr(direct, 'send_owner_telegram_reply', send)
    update = {'message': {'message_id': 500, 'date': 1790000000, 'text': '/help',
        'from': {'id': int(OWNER)}, 'chat': {'id': int(OWNER), 'type': 'private'}}}
    result, status = direct.handle_telegram_direct_webhook(update,
        headers={'X-Telegram-Bot-Api-Secret-Token': SECRET}, environ=source)
    assert status == 200 and result['message']['answer']
    denied.assert_not_called(); send.assert_called_once()


def test_unstructured_budget_reason_is_never_echoed():
    result = service.model_budget_denial_result('secret https://private.invalid/raw-token')
    assert result['status'] == 'farm_model_budget_store_unavailable'
    assert 'private.invalid' not in result['answer'] and 'raw-token' not in result['answer']
