"""Synthetic provider semantics; actual intake, authority and canonical adapter."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json

import pytest

from modules.oom_sakkie import manager_question_runtime as manager
from modules.oom_sakkie import operational_specialist_intake as intake
from modules.oom_sakkie import owner_operational_continuation as continuation
from modules.oom_sakkie import rootline_operational_adapter as adapter
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.semantic_front_door import parse_semantic_response, interpret_owner_message

NOW = datetime(2026, 9, 12, 12, 30, tzinfo=timezone.utc)
OWNER = '990001'
AUTHORITY = issue_gateway_owner_authority(OWNER, OWNER)


def envelope(value):
    return json.dumps({'choices': [{'message': {'content': json.dumps(value)}}]})


def meaning(text, *, facts=None, kind='observation', **changes):
    value = {'domain': 'rootline', 'intent': 'water_levels_observed',
        'message_kind': kind, 'continuation': True, 'observation': text,
        'observation_facts': facts or [], 'confidence': .99, 'language': 'en',
        'needs_clarification': False, **changes}
    semantic = parse_semantic_response(envelope(value))
    assert semantic is not None
    return semantic


def incoming(text, semantic, *, provider='701', reply='700', timestamp=NOW):
    return {'text': text, 'telegram_user_id': OWNER, 'telegram_chat_id': OWNER,
        'provider_message_id': provider, 'provider_timestamp': timestamp.isoformat(),
        'reply_to_message_id': reply, 'output_language': semantic.language,
        'semantic': semantic.as_hint()}


def question():
    return {'daily_identity': 'OOM-DAILY-FARM-MANAGER-2026-09-12:OWNER:SYNTHETIC',
        'telegram_message_id': '700', 'presented_at': (NOW-timedelta(minutes=5)).isoformat(),
        'question': 'Are the storage tanks full?',
        'question_binding': {'task_id': 'SYNTHETIC-WATER',
            'dedupe_key': 'rootline:storage', 'domain': 'rootline'}}


def memory():
    rows = {}
    def store(identity, record):
        created = identity not in rows
        if created:
            rows[identity] = deepcopy(record)
        return {'success': True, 'created': created, 'record': deepcopy(rows[identity])}
    return rows, store


class FakeRootline:
    """Replace database/provider seams only; the adapter validates real payloads."""
    def __init__(self):
        self.records = {}
        self.transactions = []
        self.dispatches = []

    def store(self, action, identity, payload):
        if action == 'load':
            return deepcopy([row for row in self.records.values() if row.get('mission_id') == identity])
        created = identity not in self.records
        if created:
            self.records[identity] = deepcopy(payload)
        return {'success': True, 'created': created}

    def transaction(self, payloads, actor, database_url):
        self.transactions.append(deepcopy(payloads))
        readback = []
        for payload in payloads:
            kind = 'storage' if 'storage_fraction' in payload else 'reservoir'
            readback.append({'kind': kind, 'fraction': payload[kind+'_fraction'],
                'state': payload[kind+'_state'], 'provider_message_id': payload['provider_message_id'],
                'observed_at': payload['observed_at']})
        return {'success': True, 'status': 'recorded', 'created_count': len(payloads),
            'observation_ids': ['SYNTHETIC-OBS-'+str(i) for i in range(len(payloads))],
            'observation_generation': 'SYNTHETIC-GENERATION', 'readback': readback}, 201

    def current(self):
        self.dispatches.append(True)
        return {'success': True, 'contract_version': 'rootline_specialist_result_v1',
            'result_id': 'SYNTHETIC-READ-MODEL', 'generation': 'SYNTHETIC-GENERATION',
            'recommendations': [], 'evidence': {}, 'next_reassessment': None}

    def configure(self, monkeypatch):
        monkeypatch.setattr(adapter, 'record_tank_observations_transactional', self.transaction)
        monkeypatch.setattr(adapter, 'build_current_rootline_specialist_result', self.current)
        monkeypatch.setattr(intake, '_load_pending_specialist_context', lambda parsed: [])
        monkeypatch.setattr(intake, '_operation_event_store', self.store)


@pytest.mark.parametrize('text,language', [
    ('Storage tanks are full.', 'en'), ('The storage tanks are full.', 'en'),
    ('Die opgaartenks is vol.', 'af'), ('Yes.', 'en'), ('Ja.', 'af'),
])
def test_typed_answer_to_exact_morning_question_reaches_canonical_adapter(monkeypatch, text, language):
    semantic = meaning('The storage tanks are full.',
        facts=[{'subject': 'storage_tanks', 'state': 'FULL'}], language=language)
    parsed = incoming(text, semantic)
    rows, store = memory()
    fake = FakeRootline()
    fake.configure(monkeypatch)
    result, status = manager.handle_manager_question_reply(parsed, AUTHORITY, semantic,
        question=question(), event_store=store, event_loader=lambda key: rows.get(key, {}))
    assert status == 200 and result['manager_question_status'] == 'manager_question_reply_recorded'
    assert fake.transactions[0][0]['storage_fraction'] == [1, 1]
    assert result['canonical_observation']['readback'][0]['provider_message_id'] == '701'
    assert result['hardware_commands'] == 0


def test_current_typed_correction_replaces_old_fraction_in_raw_message(monkeypatch):
    text = 'The reservoir is 3/4 was my earlier estimate; correction: it is half full now.'
    semantic = meaning('The reservoir is now half full.', kind='correction',
        facts=[{'subject': 'reservoir', 'numerator': 1, 'denominator': 2}])
    fake = FakeRootline()
    fake.configure(monkeypatch)
    result, status = intake.handle_operational_specialist_message(
        incoming(text, semantic, reply=''), AUTHORITY, now=NOW,
        rootline_operations_dispatcher=adapter.dispatch_rootline_operation,
        rootline_observation_writer=adapter.persist_rootline_observations, operation_store=fake.store)
    assert status == 200
    assert fake.transactions[0][0]['reservoir_fraction'] == [1, 2]
    assert result['canonical_observation']['readback'][0]['fraction'] == [1, 2]
    assert result['hardware_commands'] == 0


@pytest.mark.parametrize('restriction', ['recording_prohibited', 'protected_preview_required'])
def test_protected_or_prohibited_observation_is_not_written_by_generic_intake(monkeypatch, restriction):
    semantic = meaning('Storage is full', facts=[{'subject': 'storage_tanks', 'state': 'FULL'}],
        **{restriction: True})
    fake = FakeRootline()
    fake.configure(monkeypatch)
    result, status = intake.handle_operational_specialist_message(
        incoming('Storage is full', semantic), AUTHORITY, now=NOW,
        rootline_operations_dispatcher=adapter.dispatch_rootline_operation,
        rootline_observation_writer=adapter.persist_rootline_observations, operation_store=fake.store)
    assert result['handled'] is False
    assert not fake.transactions and not fake.records


@pytest.mark.parametrize('language', ['en', 'af'])
def test_independent_partial_water_facts_keep_their_own_provider_times(monkeypatch, language):
    fake = FakeRootline()
    fake.configure(monkeypatch)
    rows, store = memory()
    active_question = question()
    clarification = 'En die reservoir?' if language == 'af' else 'And the reservoir?'
    first_semantic = meaning('Storage is full; reservoir is uncertain.', language=language,
        facts=[{'subject': 'storage_tanks', 'state': 'FULL'}],
        needs_clarification=True, clarification_question=clarification)
    first_parsed = incoming('Storage is full; reservoir is uncertain.', first_semantic)
    first, status = manager.handle_manager_question_reply(first_parsed, AUTHORITY, first_semantic,
        question=active_question, event_store=store, event_loader=lambda key: rows.get(key, {}))
    assert status == 200 and first['status'] == 'manager_question_partial_reply_recorded'
    assert first['writes_farm_data'] is True and clarification in first['answer']
    assert len(fake.transactions) == 1
    partials = [row for row in rows.values() if row['status'] == 'partial']
    assert len(partials) == 1
    replay, _ = manager.handle_manager_question_reply(first_parsed, AUTHORITY, first_semantic,
        question=active_question, event_store=store, event_loader=lambda key: rows.get(key, {}))
    assert replay['answer'] == first['answer'] and replay['writes_farm_data'] is False
    assert len(fake.transactions) == 1
    active_question['partial_replies'] = partials
    later = NOW + timedelta(minutes=2)
    second_semantic = meaning('The reservoir is half full.', language=language,
        facts=[{'subject': 'reservoir', 'numerator': 1, 'denominator': 2}])
    second, status = manager.handle_manager_question_reply(
        incoming('The reservoir is half full.', second_semantic, provider='702', timestamp=later),
        AUTHORITY, second_semantic, question=active_question, event_store=store,
        event_loader=lambda key: rows.get(key, {}))
    assert status == 200 and second['manager_question_status'] == 'manager_question_reply_recorded'
    assert len(fake.transactions) == 2
    assert fake.transactions[0][0]['observed_at'] == NOW.isoformat()
    assert fake.transactions[1][0]['observed_at'] == later.isoformat()
    assert fake.transactions[0][0]['provider_message_id'] == '701'
    assert fake.transactions[1][0]['provider_message_id'] == '702'


@pytest.mark.parametrize('kind,uncertain', [('question', False), ('request', False), ('observation', True)])
def test_literal_tank_wording_does_not_override_semantic_kind_or_uncertainty(monkeypatch, kind, uncertain):
    semantic = meaning('', kind=kind, needs_clarification=uncertain,
        clarification_question='Is that a current observation?')
    rows, store = memory()
    fake = FakeRootline()
    fake.configure(monkeypatch)
    result, status = manager.handle_manager_question_reply(
        incoming('Reservoir is full.', semantic), AUTHORITY, semantic,
        question=question(), event_store=store, event_loader=lambda key: rows.get(key, {}))
    assert not fake.transactions and not fake.dispatches
    assert not any(row.get('status') == 'recorded' for row in rows.values())
    assert result.get('manager_question_status') != 'manager_question_reply_recorded'


def active():
    return {'mission_id': 'SYNTHETIC-IRRIGATION', 'card_mission_id': 'SYNTHETIC-C-SEGMENT',
        'telegram_message_id': '800', 'execution_id': 'SYNTHETIC-EXECUTION', 'entity_id': 'C12345',
        'domain': 'irrigation', 'state': 'Active',
        'execution_started_at': (NOW-timedelta(minutes=4)).isoformat()}


@pytest.mark.parametrize('text,kind', [
    ('Has C Camp stopped?', 'question'), ('Het C kamp gestop?', 'question'),
    ('C Camp must be stopped.', 'request'), ('Stop C Camp now.', 'command'),
])
def test_question_or_request_never_becomes_a_physical_stop(text, kind):
    semantic = meaning('', kind=kind, intent='irrigation_status')
    fake = FakeRootline()
    result, status = continuation.handle_owner_operational_continuation(
        incoming(text, semantic, reply='800'), AUTHORITY,
        lifecycle_loader=lambda *_: ([], [active()], []), context_store=fake.store, now=NOW)
    assert not fake.records
    assert result.get('status') != 'Completed'
    assert result.get('writes_operational_outcome') is not True


@pytest.mark.parametrize('text', ['C Camp is off.', 'C kamp is af.'])
def test_controller_off_observation_without_physical_fact_does_not_become_stop_report(text):
    semantic = meaning('The controller reports OFF.', kind='observation')
    fake = FakeRootline()
    result, _ = continuation.handle_owner_operational_continuation(
        incoming(text, semantic, reply='800'), AUTHORITY,
        lifecycle_loader=lambda *_: ([], [active()], []), context_store=fake.store, now=NOW)
    assert result['handled'] is False and not fake.records


@pytest.mark.parametrize('text,language', [
    ('C Camp has physically stopped.', 'en'), ('Die water in C-kamp loop nie meer nie.', 'af'),
])
def test_owner_stop_report_is_attributed_without_claiming_execution_completion(text, language):
    semantic = meaning(text, intent='irrigation_status', language=language,
        irrigation_observation={'zone_id': 'C12345', 'state': 'stopped'})
    fake = FakeRootline()
    result, status = continuation.handle_owner_operational_continuation(
        incoming(text, semantic, reply='800'), AUTHORITY,
        lifecycle_loader=lambda *_: ([], [active()], []), context_store=fake.store, now=NOW)
    assert status == 200 and result['status'] == 'owner_irrigation_observation_recorded'
    assert len(fake.records) == 1
    record = next(iter(fake.records.values()))
    assert record['state'] == 'physical_stop_reported'
    assert record['execution_id'] == active()['execution_id']
    assert result['verification_pending'] is True and result['hardware_commands'] == 0
    assert result['execution_completed'] is False


@pytest.mark.parametrize('language', ['en', 'af'])
def test_clarifying_zone_preserves_original_stop_observation_and_both_message_bindings(language):
    c = active()
    b = {**c, 'mission_id': 'SYNTHETIC-B', 'card_mission_id': 'SYNTHETIC-B-SEGMENT',
        'execution_id': 'SYNTHETIC-B-EXECUTION', 'entity_id': 'B12345', 'telegram_message_id': '801'}
    fake = FakeRootline()
    original_text = 'Die water loop nie meer nie.' if language == 'af' else 'The water has stopped flowing.'
    semantic = meaning(original_text, language=language, irrigation_observation={'state': 'stopped'})
    original = incoming(original_text, semantic, reply='')
    result, status = continuation.handle_owner_operational_continuation(original, AUTHORITY,
        lifecycle_loader=lambda *_: ([], [b, c], []), context_store=fake.store, now=NOW)
    assert status == 200 and result['question_count'] == 1
    pending = next(iter(fake.records.values()))
    delivered = {**pending, 'telegram_message_id': '900',
        'clarification_delivered_at': (NOW+timedelta(seconds=5)).isoformat()}
    answer_at = NOW + timedelta(seconds=20)
    answer_semantic = meaning('C Camp.', language=language, kind='confirmation',
        intent='clarification_answer', entity_refs=['C12345'])
    answered = incoming('C Camp.', answer_semantic, provider='702', reply='900', timestamp=answer_at)
    final, status = continuation.handle_owner_operational_continuation(answered, AUTHORITY,
        lifecycle_loader=lambda *_: ([delivered], [b, c], []), context_store=fake.store, now=answer_at)
    assert status == 200 and final['status'] == 'owner_irrigation_observation_recorded'
    assert final['execution_id'] == c['execution_id'] and final['verification_pending'] is True
    assert final['observation']['provider_message_id'] == '701'
    assert final['observation']['observed_at'] == NOW.isoformat()
    records = [row for row in fake.records.values() if row.get('state') == 'physical_stop_reported']
    assert len(records) == 1
    record = records[0]
    assert record['owner_evidence'] == original_text
    assert record['provider_message_id'] == '702' and record['reply_to_message_id'] == '900'
    assert record['retained_provider_binding']['provider_message_id'] == '701'
    replay, _ = continuation.handle_owner_operational_continuation(answered, AUTHORITY,
        lifecycle_loader=lambda *_: ([], [b, c], [record]), context_store=fake.store, now=answer_at)
    assert replay['answer'] == final['answer'] and replay['writes_operational_outcome'] is False
    wrong, status = continuation.handle_owner_operational_continuation(
        {**answered, 'reply_to_message_id': '999'}, AUTHORITY,
        lifecycle_loader=lambda *_: ([], [b, c], [record]), context_store=fake.store, now=answer_at)
    assert status == 409 and wrong['writes_operational_outcome'] is False


class HttpResponse:
    def __init__(self, value):
        self.value = envelope(value)
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, size=-1):
        data = self.value.encode()
        return data if size < 0 else data[:size]


@pytest.fixture
def inert_model_accounting():
    # Preserve request pricing/admission; isolate persistence for canned HTTP.
    from tests.farm_model_test_support import isolated_model_budget
    with isolated_model_budget():
        yield


@pytest.mark.parametrize('basis,context,text', [
    ({'source': 'current_message'}, {}, 'Die watervoorraad is heeltemal vol.'),
    ({'source': 'active_question', 'telegram_message_id': '700'}, {'recent_turns': [
        {'semantic_domain': 'rootline', 'task_state': 'waiting_for_input',
         'telegram_message_id': '700', 'delivery_provider_timestamp': (NOW-timedelta(minutes=5)).isoformat(),
         'clarification_question': 'Is die watervoorraad vol?'}]}, 'Ja.'),
])
def test_actual_semantic_interpreter_preserves_typed_water_meaning_without_wording_gate(basis, context, text, inert_model_accounting):
    value = {'domain': 'rootline', 'intent': 'water_levels_observed', 'message_kind': 'observation',
        'confidence': .99, 'language': 'af', 'observation': text,
        'observation_facts': [{'subject': 'storage_tanks', 'state': 'FULL'}],
        'water_observation_context': basis}
    result = interpret_owner_message({'text': text, 'provider_timestamp': NOW.isoformat(),
        'reply_to_message_id': '700' if context else ''},
        environ={'OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED': '1',
            'OOM_SAKKIE_LLM_ROUTER_MODEL': 'gpt-4.1-mini', 'OPENAI_API_KEY': 'synthetic-only'},
        context_loader=lambda _: context, http_open=lambda *a, **k: HttpResponse(value))
    assert result.observation_facts == ({'subject': 'storage_tanks', 'state': 'FULL'},)
    assert result.needs_clarification is False


@pytest.mark.parametrize('new_domain', ['rootline', 'herd_health'])
@pytest.mark.parametrize('reply', ['', '700'])
def test_bare_yes_uses_newest_question_across_domains_unless_exact_reply(new_domain, reply, inert_model_accounting):
    value = {'domain': 'rootline', 'intent': 'water_levels_observed', 'message_kind': 'observation',
        'confidence': .99, 'observation_facts': [{'subject': 'storage_tanks', 'state': 'FULL'}],
        'water_observation_context': {'source': 'active_question', 'telegram_message_id': '700'}}
    turns = [{'semantic_domain': domain, 'task_state': 'waiting_for_input',
        'telegram_message_id': identity, 'delivery_provider_timestamp': at.isoformat(),
        'clarification_question': question_text} for domain, identity, at, question_text in [
            ('rootline', '700', NOW-timedelta(minutes=5), 'Are the storage tanks full?'),
            (new_domain, '710', NOW-timedelta(minutes=1), 'Is the sow eating?' if new_domain == 'herd_health'
                else 'Is the reservoir full?')]]
    result = interpret_owner_message({'text': 'Yes.', 'provider_timestamp': NOW.isoformat(),
        'reply_to_message_id': reply},
        environ={'OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED': '1',
            'OOM_SAKKIE_LLM_ROUTER_MODEL': 'gpt-4.1-mini', 'OPENAI_API_KEY': 'synthetic-only'},
        context_loader=lambda _: {'recent_turns': turns}, http_open=lambda *a, **k: HttpResponse(value))
    assert bool(result.observation_facts) == bool(reply)
    assert result.needs_clarification == (not bool(reply))


def test_manager_independently_rejects_old_water_question_basis_before_claim(monkeypatch):
    fake = FakeRootline(); fake.configure(monkeypatch)
    semantic = meaning('Storage full.', facts=[{'subject': 'storage_tanks', 'state': 'FULL'}],
        water_observation_context={'source': 'active_question', 'telegram_message_id': '700'})
    current = {**question(), 'telegram_message_id': '710', 'question': 'Is the reservoir full?'}
    rows, store = memory()
    result, status = manager.handle_manager_question_reply(incoming('Yes.', semantic, reply=''),
        AUTHORITY, semantic, question=current, event_store=store)
    assert status == 409 and result['status'] == 'manager_question_water_context_conflict'
    assert rows == {} and fake.transactions == []


@pytest.mark.parametrize('language', ['en', 'af'])
def test_unknown_water_subject_remains_open_until_that_subject_is_answered(monkeypatch, language):
    fake = FakeRootline(); fake.configure(monkeypatch)
    rows, store = memory(); current = question()
    cases = [
        ([{'subject': 'storage_tanks', 'state': 'FULL'}, {'subject': 'reservoir', 'state': 'UNKNOWN'}], True),
        ([{'subject': 'storage_tanks', 'state': 'LOW'}], True),
        ([{'subject': 'reservoir', 'numerator': 1, 'denominator': 2}], False)]
    for index, (facts, partial) in enumerate(cases):
        semantic = meaning('A current water observation.', facts=facts, language=language,
            clarification_question='Hoe vol is die reservoir?' if language == 'af' else 'How full is the reservoir?')
        parsed = incoming('A current water observation.', semantic, provider=str(701+index),
            timestamp=NOW+timedelta(seconds=index))
        result, status = manager.handle_manager_question_reply(parsed, AUTHORITY, semantic,
            question=current, event_store=store, event_loader=lambda key: rows.get(key, {}))
        assert status == 200
        assert (result.get('status') == 'manager_question_partial_reply_recorded') == partial
        if partial:
            receipt = next(row for row in reversed(list(rows.values())) if row['status'] == 'partial')
            current.setdefault('partial_replies', []).append(receipt)
    assert len(fake.transactions) == 3
    assert [batch[0]['provider_message_id'] for batch in fake.transactions] == ['701', '702', '703']
    assert [len(batch) for batch in fake.transactions] == [1, 1, 1]
    assert fake.transactions[-1][0]['reservoir_fraction'] == [1, 2]


def test_unknown_only_records_clarification_without_dispatch_claim(monkeypatch):
    fake = FakeRootline(); fake.configure(monkeypatch)
    semantic = meaning('The reservoir level is unknown.', facts=[{'subject': 'reservoir', 'state': 'UNKNOWN'}],
        clarification_question='How full is the reservoir?')
    rows, store = memory()
    result, status = manager.handle_manager_question_reply(incoming('I do not know.', semantic), AUTHORITY,
        semantic, question=question(), event_store=store)
    assert status == 200 and result['status'] == 'manager_question_partial_reply_recorded'
    assert result['writes_farm_data'] is False and fake.transactions == [] and fake.dispatches == []
    assert [row['status'] for row in rows.values()] == ['partial']


def test_competing_camp_clarifications_bind_only_one_execution_to_original_stop():
    c = active(); b = {**c, 'mission_id': 'SYNTHETIC-B', 'card_mission_id': 'SYNTHETIC-B-SEGMENT',
        'execution_id': 'SYNTHETIC-B-EXECUTION', 'entity_id': 'B12345', 'telegram_message_id': '801'}
    fake = FakeRootline()
    semantic = meaning('The water stopped.', irrigation_observation={'state': 'stopped'})
    continuation.handle_owner_operational_continuation(incoming('The water stopped.', semantic, reply=''),
        AUTHORITY, lifecycle_loader=lambda *_: ([], [b,c], []), context_store=fake.store, now=NOW)
    pending = {**next(iter(fake.records.values())), 'telegram_message_id': '900',
        'clarification_delivered_at': (NOW+timedelta(seconds=2)).isoformat()}
    outcomes = []
    for index, zone in enumerate(('C12345', 'B12345')):
        semantic = meaning(zone, kind='confirmation', entity_refs=[zone])
        outcomes.append(continuation.handle_owner_operational_continuation(
            incoming(zone, semantic, provider=str(702+index), reply='900', timestamp=NOW+timedelta(seconds=5+index)),
            AUTHORITY, lifecycle_loader=lambda *_: ([deepcopy(pending)], [b,c], []),
            context_store=fake.store, now=NOW+timedelta(seconds=10)))
    assert [status for _,status in outcomes] == [200,409]
    assert len([row for row in fake.records.values() if row.get('state') == 'physical_stop_reported']) == 1


class ReadConnection:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def cursor(self): return self
    def execute(self, sql, params): self.queries.append((sql, params))
    def fetchall(self): return deepcopy(self.rows)


def canonical_rows(fake):
    rows = []
    for batch in fake.transactions:
        for payload in batch:
            storage = 'storage_fraction' in payload
            key = payload['idempotency_key']; kind = 'storage' if storage else 'reservoir'
            rows.append([key, 'ROOTLINE-TANK-'+sha256(key.encode()).hexdigest()[:24].upper(),
                payload[kind+'_state'] if storage else 'Unknown',
                payload[kind+'_state'] if not storage else 'Unknown',
                datetime.fromisoformat(payload['observed_at']),
                'telegram-owner:'+sha256(OWNER.encode()).hexdigest()[:16], 'oom_sakkie_owner',
                *(payload[kind+'_fraction'] if storage else [None,None]),
                *(payload[kind+'_fraction'] if not storage else [None,None]), payload['provider_message_id']])
    return rows


@pytest.mark.parametrize('replay_state', ['FULL', 'UNKNOWN'])
def test_stranded_manager_claim_reconciles_actual_read_adapter_without_redispatch(monkeypatch, replay_state):
    from modules.oom_sakkie import bounded_postgres_read
    fake = FakeRootline(); fake.configure(monkeypatch)
    rows, store = memory()
    semantic = meaning('Storage full.', facts=[{'subject': 'storage_tanks', 'state': 'FULL'}])
    parsed = incoming('Storage full.', semantic)
    def interrupted_store(identity, record):
        if identity.endswith('-COMPLETED'):
            raise RuntimeError('synthetic interruption after canonical commit')
        return store(identity, record)
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        manager.handle_manager_question_reply(parsed, AUTHORITY, semantic, question=question(),
            event_store=interrupted_store, event_loader=lambda key: rows.get(key, {}))
    assert [row['status'] for row in rows.values()] == ['dispatch_claimed']
    connection = ReadConnection(canonical_rows(fake))
    def connect(**kwargs):
        assert kwargs['read_only'] is True and kwargs['connect_deadline_seconds'] == 3
        return connection
    monkeypatch.setattr(bounded_postgres_read, 'connect_bounded_rootline_postgres', connect)
    monkeypatch.setattr(intake, 'handle_operational_specialist_message',
        lambda *_: pytest.fail('reconciliation cannot redispatch'))
    replay_semantic = meaning('Storage full.', facts=[{'subject': 'storage_tanks', 'state': replay_state}])
    replay = {**parsed, 'semantic': replay_semantic.as_hint()}
    result, status = manager.handle_manager_question_reply(replay, AUTHORITY, replay_semantic, question=question(),
        event_store=store, event_loader=lambda key: rows.get(key, {}))
    assert status == 200 and result['manager_question_status'] == 'manager_question_reply_recorded'
    assert result['canonical_observation']['status'] == 'canonical_reconciled'
    assert result['canonical_observation']['readback'][0]['state'] == 'FULL'
    assert result['canonical_observation']['readback'][0]['fraction'] == [1, 1]
    assert result['writes_farm_data'] is False and len(fake.transactions) == 1
    assert len(connection.queries) == 1 and connection.queries[0][0].lstrip().startswith('select')


@pytest.mark.parametrize('change', ['actor', 'provider', 'time', 'fraction', 'source', 'identity', 'other_fraction', 'other_state'])
def test_read_reconciliation_rejects_changed_canonical_binding(monkeypatch, change):
    from modules.oom_sakkie import bounded_postgres_read
    fake = FakeRootline(); fake.configure(monkeypatch)
    semantic = meaning('Storage full.', facts=[{'subject':'storage_tanks','state':'FULL'}])
    parsed = incoming('Storage full.', semantic)
    rows, store = memory()
    manager.handle_manager_question_reply(parsed, AUTHORITY, semantic, question=question(),
        event_store=store, event_loader=lambda key: rows.get(key, {}))
    actual = canonical_rows(fake)
    index, value = {'actor':(5,'wrong'), 'provider':(11,'999'), 'time':(4,NOW-timedelta(seconds=1)),
        'fraction':(7,0), 'source':(6,'wrong'), 'identity':(1,'wrong'), 'other_fraction':(9,1), 'other_state':(3,'FULL')}[change]
    actual[0][index] = value
    monkeypatch.setattr(bounded_postgres_read, 'connect_bounded_rootline_postgres', lambda **_: ReadConnection(actual))
    assert manager._reconcile_rootline_claim(parsed, next(iter(rows.values()))) is None


@pytest.mark.parametrize('failure', ['exception', 'unhandled'])
def test_specialist_interruption_retains_explicit_retry_ownership(monkeypatch, failure):
    def dispatch(*_):
        if failure == 'exception': raise RuntimeError('synthetic')
        return {'handled': False}, 200
    monkeypatch.setattr(intake, 'handle_operational_specialist_message', dispatch)
    semantic = meaning('Storage full.', facts=[{'subject':'storage_tanks','state':'FULL'}])
    rows, store = memory()
    result, status = manager.handle_manager_question_reply(incoming('Storage full.', semantic), AUTHORITY,
        semantic, question=question(), event_store=store, event_loader=lambda key: rows.get(key, {}))
    assert status == 503 and result['retry_owner'] == 'same_provider_message_identity'
    assert [row['status'] for row in rows.values()] == ['dispatch_claimed', 'retry_owned']


class QuestionCursor:
    def __init__(self, family, receipts=()): self.results = [family, [(row,) for row in receipts]]
    def execute(self, *_): pass
    def fetchall(self): return self.results.pop(0)


def morning_generation(*, original=True, replacement=True):
    daily = 'OOM-DAILY-FARM-MANAGER-2026-09-12'
    card = daily+':OWNER:'+sha256(f'{OWNER}|{OWNER}'.encode()).hexdigest()[:16].upper()
    text = 'Is the reservoir full?'; digest = sha256(b'synthetic material').hexdigest()
    mission = card+(':GENERATION:'+digest[:20].upper() if replacement else ':DELIVERY')
    body = {'owner_user_id': OWNER, 'chat_id': OWNER, 'card_mission_id': card, 'mission_id': mission,
        'telegram_message_id': '710', 'state': 'brief_generation_delivered' if replacement else 'delivered',
        'delivery_provider_timestamp': (NOW-timedelta(minutes=1)).isoformat(),
        'generation_digest': digest, 'text_sha256': digest if replacement else sha256(text.encode()).hexdigest()}
    if replacement: body['rendered_text_sha256'] = sha256(text.encode()).hexdigest()
    claim = {'owner_user_id': OWNER, 'chat_id': OWNER, 'event_id': mission, 'daily_identity': daily,
        'card_mission_id': card, 'material_digest': digest, 'answer_sha256': sha256(text.encode()).hexdigest(),
        'question': text, 'question_binding': {'task_id':'SYNTHETIC-RESERVOIR',
            'dedupe_key':'rootline:reservoir', 'domain':'rootline'}} if original else {}
    return body, claim


@pytest.mark.parametrize('replacement', [False, True])
def test_current_morning_generation_restores_original_question_and_shadows_old_receipt(replacement):
    body, claim = morning_generation(replacement=replacement)
    old = {**question(), 'daily_identity': claim['daily_identity']}
    rows = manager._current_delivered_questions(QuestionCursor([(body,claim)]), OWNER, OWNER, [old])
    assert len(rows) == 1 and rows[0]['telegram_message_id'] == '710'
    assert rows[0]['question'] == claim['question'] and rows[0]['question_binding'] == claim['question_binding']
    assert manager.load_active_manager_question(incoming('Yes.', meaning('Yes.'), reply=''), loader=lambda *_: rows) == rows[0]


@pytest.mark.parametrize('damage', ['missing', 'text', 'owner', 'generation'])
def test_morning_without_exact_original_question_allows_only_explicit_current_fact(damage):
    body, claim = morning_generation(original=damage != 'missing')
    if damage == 'text': claim['answer_sha256'] = '0'*64
    if damage == 'owner': claim['owner_user_id'] = 'other'
    if damage == 'generation': claim['material_digest'] = '0'*64
    rows = manager._current_delivered_questions(QuestionCursor([(body,claim)]), OWNER, OWNER, [])
    assert len(rows) == 1 and rows[0]['question_binding']['contextual_card_recovery'] is True
    semantic = meaning('Storage full.', facts=[{'subject':'storage_tanks','state':'FULL'}],
        water_observation_context={'source':'active_question','telegram_message_id':'710'})
    receipts, store = memory()
    result, status = manager.handle_manager_question_reply(incoming('Yes.', semantic, reply='710'), AUTHORITY,
        semantic, question=rows[0], event_store=store)
    assert status == 409 and result['status'] == 'manager_question_original_question_unavailable' and receipts == {}


def test_completed_current_question_stays_retired_even_when_old_receipt_is_unanswered():
    body, claim = morning_generation()
    old = {**question(), 'daily_identity': claim['daily_identity']}
    receipt = {**claim['question_binding'], 'status':'recorded', 'daily_identity':'prior-date'}
    assert manager._current_delivered_questions(QuestionCursor([(body,claim)], [receipt]), OWNER, OWNER, [old]) == []


@pytest.mark.parametrize('state', ['updated', 'brief_generation_delivered', 'delivered'])
def test_changed_text_on_same_provider_card_cannot_restore_old_question_without_original(state):
    body, claim = morning_generation()
    old = {**question(), 'daily_identity': claim['daily_identity'], 'telegram_message_id': '710',
        'material_digest': claim['material_digest'], 'answer_sha256': claim['answer_sha256'],
        'question': claim['question'], 'question_binding': claim['question_binding']}
    changed = {**body, 'state': state, 'text_sha256': 'd'*64, 'rendered_text_sha256': 'd'*64}
    rows = manager._current_delivered_questions(QuestionCursor([(changed,{})]), OWNER, OWNER, [old])
    assert len(rows) == 1 and rows[0]['question_binding']['contextual_card_recovery'] is True
    semantic = meaning('Reservoir full.', facts=[{'subject':'reservoir','state':'FULL'}],
        water_observation_context={'source':'active_question','telegram_message_id':'710'})
    receipts, store = memory()
    result, status = manager.handle_manager_question_reply(incoming('Yes.', semantic, reply='710'),
        AUTHORITY, semantic, question=rows[0], event_store=store)
    assert status == 409 and result['status'] == 'manager_question_original_question_unavailable'
    assert receipts == {}


@pytest.mark.parametrize('reverse_order', [False, True])
def test_same_time_and_provider_card_with_conflicting_generations_remains_unresolved(reverse_order):
    body, claim = morning_generation()
    other_text = 'Are the storage tanks full?'
    other_digest = sha256(b'different synthetic material').hexdigest()
    other_mission = body['card_mission_id']+':GENERATION:'+other_digest[:20].upper()
    other_sha = sha256(other_text.encode()).hexdigest()
    other = {**body, 'mission_id': other_mission, 'generation_digest': other_digest,
        'text_sha256': other_digest, 'rendered_text_sha256': other_sha}
    other_claim = {**claim, 'event_id': other_mission, 'material_digest': other_digest,
        'answer_sha256': other_sha, 'question': other_text,
        'question_binding': {'task_id':'SYNTHETIC-STORAGE','dedupe_key':'rootline:storage','domain':'rootline'}}
    family = [(body, claim), (other, other_claim)]
    old = {**question(), 'daily_identity': claim['daily_identity']}
    if reverse_order:
        family.reverse()
    rows = manager._current_delivered_questions(QuestionCursor(family), OWNER, OWNER, [old])
    assert rows == []


def test_future_manager_reply_is_contained_before_any_claim_or_dispatch(monkeypatch):
    semantic = meaning('Storage full.', facts=[{'subject':'storage_tanks','state':'FULL'}])
    future = datetime.now(timezone.utc)+timedelta(minutes=10)
    rows, store = memory()
    monkeypatch.setattr(intake, 'handle_operational_specialist_message', lambda *_: pytest.fail('future dispatch'))
    result, status = manager.handle_manager_question_reply(incoming('Storage full.', semantic, timestamp=future),
        AUTHORITY, semantic, question={**question(), 'presented_at': datetime.now(timezone.utc).isoformat()}, event_store=store)
    assert status == 409 and result['status'] == 'manager_question_provider_chronology_invalid' and rows == {}
