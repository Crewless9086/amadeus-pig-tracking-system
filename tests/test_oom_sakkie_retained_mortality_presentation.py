"""Synthetic unit tests through the actual retained presentation modules."""
from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
import json
import pytest
from modules.oom_sakkie import herdmaster_source_transaction as tx
from modules.oom_sakkie import retained_mortality_history as history
from modules.oom_sakkie import retained_mortality_presentation as presentation
from modules.oom_sakkie.herdmaster_retained_recovery_runtime import retained_report_binding
from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
BASE = datetime(2026, 9, 1, tzinfo=timezone.utc)

def iso(minutes):
    return (BASE + timedelta(minutes=minutes)).isoformat()

def fixture():
    source = {'mission_id': 'SYNTHETIC-SOURCE', 'owner_user_id': '9000', 'chat_id': '9000', 'provider_message_id': '100', 'provider_timestamp': iso(-90), 'status': 'preview_ready', 'event_phase': 'retained_preview_generated:synthetic', 'operation_id': 'SYNTHETIC-OP', 'preview': {'confirmation_binding': {'operation_id': 'SYNTHETIC-OP', 'preview_sha256': 'a' * 64}}}
    payload = {'operation_id': 'SYNTHETIC-OP', 'preview_sha256': 'a' * 64, 'identity': {'pig_id': 'SYNTHETIC-PIG'}, 'effect_kind': 'mortality', 'event_family': 'mortality'}
    claim = {'callback_token': 'SYNTHETIC-NONPRODUCTION', 'mission_id': 'SYNTHETIC-CLAIM', 'action_kind': 'mortality', 'owner_user_id': '9000', 'private_chat_id': '9000', 'provider_message_id': '100', 'preview_payload': payload, 'preview_digest': canonical_preview_digest('mortality', payload), 'evidence_generation': 'b' * 64, 'created_at': iso(-90), 'expires_at': iso(90), 'status': 'active', 'delivery_state': 'claim_created', **{k: None for k in history.EMPTY_MARKERS}}
    source['retained_repreview'] = {'contract_version': 'retained_health_preview_v1', 'source_binding': retained_report_binding([source]), 'claim_mission_id': claim['mission_id'], 'claim_preview_digest': claim['preview_digest'], 'claim_evidence_generation': claim['evidence_generation']}
    case = {'case_id': 'SYNTHETIC-CASE', 'generation': 1, 'evidence_digest': 'c' * 64, 'dedupe_key': 'herdmaster:retained-mortality:100'}
    h = history._sha(claim['callback_token'])

    def row(kind, when, event, key, payload):
        return {'event_id': event, 'event_type': kind, 'idempotency_key': key, 'occurred_at': iso(when), 'aggregate_type': 'protected_action_claim', 'aggregate_id': h, 'source_record_id': case['case_id'], 'authority_tier': 'owner_approved', 'provenance_json': {'source_ref': 'sha256:' + 'e' * 64}, 'source_system': 'manual_presend_timeout_correction', 'causation_id': 'SYNTHETIC-CYCLE', 'payload_json': {'claim_hash': h, 'preview_digest': claim['preview_digest'], 'one_time_only': True, 'provider_attempts': 0, 'farm_writes': 0, 'new_expires_at': iso(when + 30), **payload}}
    renewal = row(history.RENEWAL, 0, 'OOM-RETAINED-RENEWAL-' + h[:32].upper(), 'retained-preview-renewal:' + h + ':' + iso(-60), {'contract_version': 'retained_preview_renewal_v1', 'old_expires_at': iso(-60), 'mission_id': claim['mission_id'], 'evidence_generation': claim['evidence_generation'], 'source_binding': source['retained_repreview']['source_binding'], 'old_status': 'active', 'new_status': 'active', 'old_delivery_state': 'claim_created', 'new_delivery_state': 'claim_created'})
    original = {k: deepcopy(renewal[k]) for k in ('event_id', 'event_type', 'idempotency_key', 'payload_json', 'occurred_at')}
    common = {'case_id': case['case_id'], 'generation': 1, 'evidence_digest': case['evidence_digest'], 'plan_sha256': 'd' * 64, 'preimage_sha256': 'e' * 64, 'prevention_revision': '1' * 40, 'prevention_tree': '2' * 40, 'deployed_revision': '3' * 40, 'authority_reference': 'SYNTHETIC-AUTHORITY', 'scheduler_triggers': 0}
    correction = row(history.CORRECTION, 60, 'OOM-PRESEND-CORRECTION-' + h[:32].upper(), 'oom-presend-timeout-correction:' + h, {**common, 'contract_version': 'oom_presend_timeout_correction.v1', 'original_renewal': original, 'archived_claim_markers': {'delivery_attempt_id': history._sha('oom_protected_delivery.v1|' + claim['callback_token'] + '|' + claim['preview_digest']), 'delivery_attempted_at': iso(2), 'delivery_ambiguous_at': iso(3), 'expires_at': iso(30), 'status': 'active', 'delivery_state': 'delivery_ambiguous', 'delivery_result': {'success': False, 'status': 'family_message_cycle_deadline_deferred', 'telegram_message_id': None, 'telegram_sends': 0, 'telegram_edits': 0}}})
    return (claim, case, source, [renewal, correction])

def event(case, kind, at, name, outcome='', **extra):
    body = {'event_id': name, 'case_id': case['case_id'], 'generation': case['generation'], 'event_type': kind, 'occurred_at': iso(at)}
    body['event_payload'] = {k: body[k] for k in ('case_id', 'generation', 'event_type', 'occurred_at')}
    body['event_payload'].update(cycle_id='SYNTHETIC-CYCLE', outcome_status=outcome, failure_kind='', provider_ambiguity_contained=False, **extra)
    return body

def case_history(case, audits):
    corrected = audits[1]
    entries = [event(case, 'created', -80, 'CREATED'), event(case, 'claimed', 1, 'CLAIMED'), event(case, 'delegated', 1, 'DELEGATED'), event(case, 'contained', 4, 'CONTAINED', 'protected_delivery_ambiguous')]
    entries[-1]['event_payload']['provider_ambiguity_contained'] = True
    entries.append(event(case, 'reassessment_scheduled', 60, corrected['event_id'] + '-REASSESS', 'proven_presend_timeout_classification_corrected', correction_audit_event_id=corrected['event_id'], plan_sha256='d' * 64))
    return (entries, {'cycle_id': 'SYNTHETIC-CYCLE', 'source_revision': '4' * 40, 'started_at': iso(1)})

def test_synthetic_audited_legacy_chain_is_complete_and_pure():
    claim, case, source, audits = fixture()
    before = deepcopy((claim, case, source, audits))
    chain = history.validate_audit_chain(claim, case, source, audits, observed_at=BASE + timedelta(minutes=180))
    events, cycle = case_history(case, audits)
    history.validate_case_history(events, claim, case, chain, cycle, observed_at=BASE + timedelta(minutes=180))
    assert (claim, case, source, audits) == before

@pytest.mark.parametrize('fault', ['attempt', 'result', 'extra_result', 'missing_renewal', 'missing_correction', 'unknown_audit', 'duplicate', 'wrong_token', 'different_material', 'expiry', 'authority', 'cycle', 'missing_created', 'unknown_failure', 'mixed_effect', 'extra_containment', 'old_preview_after_correction'])
def test_incomplete_or_effectful_legacy_history_refuses(fault):
    claim, case, source, audits = fixture()
    events, cycle = case_history(case, audits)
    old = audits[1]['payload_json']['archived_claim_markers']
    if fault == 'attempt':
        old['delivery_attempt_id'] = 'wrong'
    elif fault == 'result':
        old['delivery_result']['telegram_sends'] = 1
    elif fault == 'extra_result':
        old['delivery_result']['arbitrary'] = False
    elif fault == 'missing_renewal':
        audits.pop(0)
    elif fault == 'missing_correction':
        audits.pop()
    elif fault == 'unknown_audit':
        audits.append({**deepcopy(audits[0]), 'event_id': 'UNKNOWN', 'event_type': 'unknown'})
    elif fault == 'duplicate':
        audits.append(deepcopy(audits[0]))
    elif fault == 'wrong_token':
        claim['callback_token'] = 'ANOTHER'
    elif fault == 'different_material':
        claim['evidence_generation'] = '9' * 64
    elif fault == 'expiry':
        claim['expires_at'] = iso(91)
    elif fault == 'authority':
        audits[1]['authority_tier'] = 'bounded_auto'
    elif fault == 'cycle':
        cycle['cycle_id'] = 'DIFFERENT'
    elif fault == 'missing_created':
        events.pop(0)
    elif fault == 'unknown_failure':
        events.append(event(case, 'exception', 70, 'UNKNOWN', 'provider_timeout'))
    elif fault == 'mixed_effect':
        events[1]['event_payload']['telegram_sends'] = 1
    elif fault == 'extra_containment':
        events.insert(3, event(case, 'contained', 4, 'SECOND', 'protected_delivery_ambiguous'))
    elif fault == 'old_preview_after_correction':
        events.append(event(case, 'exception', 70, 'OLD', 'retained_claim_current_preview_mismatch'))
    with pytest.raises((tx.SourceConflict, KeyError, TypeError)):
        chain = history.validate_audit_chain(claim, case, source, audits, observed_at=BASE + timedelta(minutes=180))
        history.validate_case_history(events, claim, case, chain, cycle, observed_at=BASE + timedelta(minutes=180))

def test_old_preview_mismatch_requires_full_legacy_chain():
    claim, case, source, audits = fixture()
    events, cycle = case_history(case, audits)
    events.insert(1, event(case, 'exception', -40, 'OLD', 'retained_claim_current_preview_mismatch'))
    history.validate_case_history(events, claim, case, history.validate_audit_chain(claim, case, source, audits, observed_at=BASE + timedelta(minutes=180)), cycle, observed_at=BASE + timedelta(minutes=180))
    with pytest.raises(tx.SourceConflict):
        history.validate_case_history([events[0], events[1]], claim, case, (None, {}), None, observed_at=BASE + timedelta(minutes=180))

def test_renewal_consumed_guard_requires_no_effect_and_exact_epoch():
    claim, case, source, audits = fixture()
    events, cycle = case_history(case, audits)
    guard = event(case, 'exception', 91, 'EXHAUSTED', history.RENEWAL_CONSUMED)
    guard['event_payload']['failure_kind'] = history.RENEWAL_CONSUMED
    guard['event_payload']['deadline_phase'] = ''
    guard['event_payload']['processing_timings_ms'] = {'dispatch_wait': 10, 'refresh_and_delivery': 12}
    chain = history.validate_audit_chain(claim, case, source, audits, observed_at=BASE + timedelta(minutes=180))
    history.validate_case_history(events + [guard], claim, case, chain, cycle, observed_at=BASE + timedelta(minutes=180))
    guard['event_payload']['processing_timings_ms']['dispatch_wait'] = True
    with pytest.raises(tx.SourceConflict):
        history.validate_case_history(events + [guard], claim, case, chain, cycle, observed_at=BASE + timedelta(minutes=180))

def test_same_archived_renewal_instant_accepts_db_json_serialization():
    claim, case, source, audits = fixture()
    audits[1]['payload_json']['original_renewal']['occurred_at'] = str(BASE)
    history.validate_audit_chain(claim, case, source, audits, observed_at=BASE + timedelta(minutes=180))

def test_source_predecessor_and_all_status_chronology():
    _, _, source, _ = fixture()
    rows = [{'record': source, 'review_event_id': 'ONE', 'created_at': iso(0)}]
    assert tx.require_current(rows, source) == source
    cancelled = {**source, 'status': 'contained', 'event_phase': 'owner_declined'}
    with pytest.raises(tx.SourceConflict):
        tx.require_current([{'record': cancelled}, *rows], source)
    with pytest.raises(tx.SourceConflict):
        tx.require_current([{'record': {**source, 'mission_id': 'OTHER', 'consumed_context_missions': [source['mission_id']]}}, *rows], source)
    with pytest.raises(tx.SourceConflict):
        tx.check_append(rows, cancelled, {source['mission_id']: 'stale'})
    assert tx.check_append(rows, cancelled, {source['mission_id']: tx.predecessor(source)}) is True
    assert tx.check_append([{'record': cancelled}], cancelled, {source['mission_id']: 'irrelevant-replay'}) is False
    with pytest.raises(tx.SourceConflict):
        tx.check_append([{'record': cancelled}], source, {source['mission_id']: tx.digest(cancelled)})

def test_source_append_requires_all_related_predecessors():
    _, _, source, _ = fixture()
    target = {**source, 'mission_id': 'OTHER'}
    later = {**source, 'consumed_context_missions': ['OTHER']}
    rows = [{'record': source}, {'record': target}]
    with pytest.raises(tx.SourceConflict):
        tx.check_append(rows, later, {source['mission_id']: tx.digest(source)})
    assert tx.check_append(rows, later, {source['mission_id']: tx.digest(source), 'OTHER': tx.digest(target)})

def test_source_lock_order_is_canonical():

    class Cur:

        def __init__(self):
            self.calls = []

        def execute(self, *args):
            self.calls.append(args)
    a, b = (Cur(), Cur())
    tx.lock_sources(a, '9000', '9000', ['A', 'Z'])
    tx.lock_sources(b, '9000', '9000', ['Z', 'A'])
    assert a.calls == b.calls and len(a.calls) == 2
    with pytest.raises(tx.SourceConflict):
        tx.lock_sources(Cur(), '9000', '9001', ['A'])

def test_provisional_policy_is_frozen_and_cannot_invoke_a_database():
    claim, case, source, _ = fixture()
    requested = {k: claim[k] for k in ('action_kind', 'preview_payload', 'owner_user_id', 'private_chat_id')}
    policy = presentation.stage(source, requested, claim, case)
    original = policy.source_json
    source['status'] = 'contained'
    requested['preview_payload']['operation_id'] = 'changed'
    assert policy.source_json == original
    with pytest.raises(FrozenInstanceError):
        policy.source_json = 'changed'

    def forbidden():
        pytest.fail('provisional staging attempted database access')
    args = dict(callback_token=claim['callback_token'], preview_digest=claim['preview_digest'], owner_user_id='9000', private_chat_id='9000', action_kind='mortality', factory=forbidden, start_attempt=False, deadline_monotonic=0)
    assert presentation.claim_presentation(policy, **args) is None
    with pytest.raises(tx.SourceConflict):
        presentation.claim_presentation({'policy': True}, **args)
    with pytest.raises(tx.SourceConflict):
        presentation.claim_presentation(policy, **{**args, 'owner_user_id': 'OTHER'})

def test_borrowed_connection_cannot_commit_or_close_parent():

    class DB:

        def cursor(self):
            return 'cursor'

        def execute(self, *args):
            return args

        def commit(self):
            pytest.fail('borrowed commit')

        def close(self):
            pytest.fail('borrowed close')
    reader = tx.TransactionReader(DB())
    assert reader.transaction_managed
    with reader('unused') as borrowed:
        assert borrowed.cursor() == 'cursor'
        assert borrowed.execute('SELECT') == ('SELECT',)
        assert not hasattr(borrowed, 'commit') and (not hasattr(borrowed, 'close'))

@pytest.mark.parametrize('which', ['contained','correction'])
@pytest.mark.parametrize('field', ['telegram_sends','telegram_edits','delivery_confirmed','provider_confirmed','provider_card_message_id'])
def test_legacy_exception_never_overrides_a_real_effect(which, field):
    claim,case,source,audits=fixture(); events,cycle=case_history(case,audits)
    events[3 if which=='contained' else 4]['event_payload'][field]=1
    chain=history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))
    with pytest.raises(tx.SourceConflict,match='effect_history'):
        history.validate_case_history(events,claim,case,chain,cycle,observed_at=BASE+timedelta(minutes=180))


def test_correction_cannot_hide_another_ambiguous_marker():
    claim,case,source,audits=fixture(); events,cycle=case_history(case,audits)
    events[-1]['event_payload']['provider_ambiguity_contained']=True
    chain=history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))
    with pytest.raises(tx.SourceConflict):
        history.validate_case_history(events,claim,case,chain,cycle,observed_at=BASE+timedelta(minutes=180))


@pytest.mark.parametrize('which',['audit','case'])
def test_future_history_is_not_present_proof(which):
    claim,case,source,audits=fixture(); events,cycle=case_history(case,audits)
    if which=='audit': audits[-1]['occurred_at']=iso(181)
    else: events.append(event(case,'claimed',181,'FUTURE'))
    with pytest.raises(tx.SourceConflict,match='future'):
        chain=history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))
        history.validate_case_history(events,claim,case,chain,cycle,observed_at=BASE+timedelta(minutes=180))


def test_original_renewal_separate_select_and_update_clocks_are_preserved():
    claim,case,source,audits=fixture()
    later=(BASE+timedelta(minutes=30,seconds=1)).isoformat()
    audits[0]['payload_json']['new_expires_at']=later
    archived=audits[1]['payload_json']; archived['original_renewal']['payload_json']['new_expires_at']=later
    archived['archived_claim_markers']['expires_at']=later
    history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))
    archived['archived_claim_markers']['delivery_attempted_at']=BASE.isoformat()
    with pytest.raises(tx.SourceConflict):
        history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))


def test_copied_predecessor_digest_cannot_hide_cancelled_source():
    _,_,source,_=fixture()
    cancelled={**source,'status':'contained','event_phase':'owner_declined'}
    forged={**source,'_source_predecessor_digest':tx.digest(cancelled)}
    with pytest.raises(tx.SourceConflict,match='staged_source_changed'):
        presentation.validate_staged_source([{'record':cancelled}],forged)
    assert presentation.validate_staged_source([{'record':source}],source)==source


def test_reverse_supersession_prevents_late_append_to_unchanged_old_row():
    _,_,source,_=fixture()
    other={**source,'mission_id':'OTHER','superseded_duplicate_missions':[source['mission_id']]}
    rows=[{'record':other},{'record':source}]
    later={**source,'provider_message_id':'101'}
    with pytest.raises(tx.SourceConflict,match='append_superseded'):
        tx.check_append(rows,later,{source['mission_id']:tx.digest(source)})


def test_pending_clarification_preserves_actual_no_pig_welfare_behavior():
    from modules.pig_weights.pig_welfare_case_runtime import append_welfare_case_context
    pending={'mission_id':'SYNTHETIC-PENDING','status':'waiting_for_context',
        'provider_message_id':'101','provider_timestamp':iso(0),'owner_user_id':'9000','chat_id':'9000'}
    def forbidden(): pytest.fail('no-pig clarification attempted welfare I/O')
    result=append_welfare_case_context(pending,connect_factory=forbidden)
    assert result=={'success':False,'status':'welfare_case_identity_incomplete','rows_created':0}
    tx.require_applicable_welfare_result(pending,result)
    applicable={**pending,'preview':{'evaluator':{'identity':{'pig_id':'SYNTHETIC-PIG'}}}}
    with pytest.raises(RuntimeError): tx.require_applicable_welfare_result(applicable,result)
    with pytest.raises(RuntimeError): tx.require_applicable_welfare_result(pending,{'success':False,'status':'database_failed'})


def test_complete_never_attempted_origin_does_not_invent_a_correction():
    claim,case,source,_=fixture()
    rows=[{'review_event_id':'NEW','created_at':iso(-80),'record':source},
        {'review_event_id':'OLD','created_at':iso(-100),'record':{**source,'status':'waiting_for_input'}}]
    presentation.validate_origin(rows,source,claim,BASE+timedelta(minutes=180))
    assert history.validate_audit_chain(claim,case,source,[],observed_at=BASE+timedelta(minutes=180))==(None,{})
    history.validate_case_history([event(case,'created',-100,'CREATED')],claim,case,(None,{}),None,
        observed_at=BASE+timedelta(minutes=180))
    with pytest.raises(tx.SourceConflict):
        history.validate_case_history([event(case,'created',-100,'CREATED'),
            event(case,'contained',-40,'UNKNOWN','protected_delivery_ambiguous')],claim,case,(None,{}),None,
            observed_at=BASE+timedelta(minutes=180))


@pytest.mark.parametrize('fault',['missing_origin','cancelled_origin','duplicate_rows','expiry_before_creation','future_source'])
def test_origin_cannot_be_inferred_from_empty_attempt_markers(fault):
    claim,case,source,_=fixture()
    rows=[{'review_event_id':'NEW','created_at':iso(-80),'record':source},
        {'review_event_id':'OLD','created_at':iso(-100),'record':{**source,'status':'waiting_for_input'}}]
    if fault=='missing_origin': rows.pop()
    elif fault=='cancelled_origin': rows[-1]['record']['status']='contained'
    elif fault=='duplicate_rows': rows.append(deepcopy(rows[-1]))
    elif fault=='expiry_before_creation': claim['expires_at']=iso(-91)
    elif fault=='future_source': rows[0]['created_at']=iso(181)
    with pytest.raises(tx.SourceConflict): presentation.validate_origin(rows,source,claim,BASE+timedelta(minutes=180))


def real_material():
    from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
    from modules.oom_sakkie.herdmaster_health_loss_preview import prepare_health_loss_owner_preview
    claim,case,source,_=fixture()
    evidence={'animals':[{'pig_id':'SYNTHETIC-PIG','name':'Synthetic','tag_number':'27',
        'lifecycle_status':'Active','on_farm':True,'availability':'Herd','pen':'PEN-A',
        'birth_date':'','lifecycle_effective_date':''}],'matings':[],'litters':[],
        'as_of_timestamp':'2026-09-22T08:00:00+00:00'}
    evidence['evidence_generation']=tx.digest({k:evidence[k] for k in ('animals','matings','litters')})
    evidence['animal_evidence_generations']={'SYNTHETIC-PIG':tx.digest({'animal':evidence['animals'][0],'matings':[],'litters':[]})}
    source.update(provider_timestamp='2026-08-20T08:00:00+00:00',output_language='af',
        owner_text_verbatim='Vark nr 27 is dood op 19 Aug 2026. Hy is verwyder en begrawe.')
    preview=prepare_health_loss_owner_preview({'gateway_authority':issue_gateway_owner_authority('9000','9000'),
        'provider_message_id':source['provider_message_id'],'provider_timestamp':source['provider_timestamp'],
        'provider_timezone':'Africa/Johannesburg','output_language':'af','text':source['owner_text_verbatim']},evidence)
    assert preview['success'] and preview['confirmation_ready']
    source.update(preview=preview,operation_id=preview['confirmation_binding']['operation_id'])
    claim['preview_payload']={'effect_kind':'mortality','event_family':preview['evaluator']['event_family'],
        'operation_id':source['operation_id'],'preview_sha256':preview['confirmation_binding']['preview_sha256'],
        'identity':preview['evaluator']['identity']}
    claim['preview_digest']=canonical_preview_digest('mortality',claim['preview_payload'])
    claim['evidence_generation']=evidence['evidence_generation']
    source['retained_repreview'].update(claim_preview_digest=claim['preview_digest'],claim_evidence_generation=claim['evidence_generation'])
    return source,claim,evidence


def test_real_canonical_preview_clock_advance_is_not_new_material():
    source,claim,evidence=real_material()
    assert presentation.validate_material(source,claim,evidence)==source['preview']
    evidence['as_of_timestamp']='2026-09-22T08:05:00+00:00'
    assert presentation.validate_material(source,claim,evidence)==source['preview']


@pytest.mark.parametrize('fault',['global_generation','animal_generation','canonical_fact','stored_operation','stored_text'])
def test_real_preview_rejects_changed_material_or_stored_binding(fault):
    source,claim,evidence=real_material()
    if fault=='global_generation': evidence['evidence_generation']='bad'
    elif fault=='animal_generation': evidence['animal_evidence_generations']['SYNTHETIC-PIG']='bad'
    elif fault=='canonical_fact': evidence['animals'][0]['pen']='PEN-B'
    elif fault=='stored_operation': source['preview']['confirmation_binding']['operation_id']='OTHER'
    elif fault=='stored_text': source['preview']['owner_text']='Changed presentation'
    with pytest.raises(tx.SourceConflict): presentation.validate_material(source,claim,evidence)


def test_deadline_history_remains_eligible_for_later_admission(monkeypatch):
    from types import SimpleNamespace
    claim,case,source,audits=fixture(); events,cycle=case_history(case,audits)
    clock=[51.0]
    monkeypatch.setattr(presentation,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    with pytest.raises(presentation.PresentationDeadline): presentation.require_admission_reserve(80.0)
    # The typed rollback maps to this already-proven pre-send status. This pure
    # test proves continuing eligibility, not actual transaction/provider I/O.
    deferred=event(case,'exception',100,'DEFERRED','family_message_cycle_deadline_deferred')
    chain=history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))
    history.validate_case_history(events+[deferred],claim,case,chain,cycle,observed_at=BASE+timedelta(minutes=180))
    clock[0]=41.0
    presentation.require_admission_reserve(80.0)
    requested={k:claim[k] for k in ('action_kind','preview_payload','owner_user_id','private_chat_id')}
    assert isinstance(presentation.stage(source,requested,claim,case),presentation.RetainedMortalityPresentation)
    assert all(claim[key] is None for key in history.EMPTY_MARKERS)


def test_metadata_query_guard_checks_each_remaining_admission_budget(monkeypatch):
    from types import SimpleNamespace
    clock=[40.0]; calls=[]
    monkeypatch.setattr(presentation,'time',SimpleNamespace(monotonic=lambda:clock[0]))
    cursor=presentation.AdmissionCursor(SimpleNamespace(execute=lambda *args:calls.append(args)),80.0)
    cursor.execute('synthetic read only')
    clock[0]=50.0
    with pytest.raises(presentation.PresentationDeadline): cursor.execute('not executed')
    assert calls==[('synthetic read only',)]


def statement_timeout_wrapper(error, *, rollback_error=None, exit_error=None):
    from modules.oom_sakkie import protected_delivery_lifecycle as wrapper
    claim,case,source,audits=fixture()
    requested={k:claim[k] for k in ('action_kind','preview_payload','owner_user_id','private_chat_id')}
    policy=presentation.stage(source,requested,claim,case)
    trace=[]
    class Cursor:
        def __enter__(self): return self
        def __exit__(self,*args): return False
        def execute(self,sql,*args):
            assert sql.lower().startswith(('set ', 'select ')), 'test crossed a write boundary'
            trace.append('read/control')
            if 'advisory_xact_lock' in sql: raise error
    class DB:
        def __enter__(self): return self
        def __exit__(self,kind,*args):
            trace.append(('context_exit',None if kind is None else kind.__name__))
            if exit_error: raise exit_error
            return False
        def cursor(self): return Cursor()
        def rollback(self):
            trace.append('explicit_rollback')
            if rollback_error: raise rollback_error
    args=dict(callback_token=claim['callback_token'],preview_digest=claim['preview_digest'],owner_user_id='9000',
        private_chat_id='9000',action_kind='mortality',factory=DB,start_attempt=True,deadline_monotonic=None,
        presentation_policy=policy)
    outcome=wrapper._claim_delivery(**args)
    return outcome,trace,(claim,case,source,audits),wrapper,args


@pytest.mark.parametrize('error_name',['LockNotAvailable','QueryCanceled'])
def test_actual_wrapper_rolled_back_sql_timeout_allows_next_natural_preflight(error_name):
    from psycopg import errors
    outcome,trace,data,wrapper,args=statement_timeout_wrapper(getattr(errors,error_name)('synthetic local test'))
    assert outcome['status']==outcome['failure_kind']=='retained_mortality_presend_statement_deferred'
    assert outcome['delivery_definitely_not_sent'] is True and outcome['telegram_sends']==0
    assert trace[-2:]==['explicit_rollback',('context_exit',None)]
    claim,case,source,audits=data; events,cycle=case_history(case,audits)
    deferred=event(case,'exception',100,'REAL-WRAPPER-DEFERRAL',outcome['status'])
    deferred['event_payload']['failure_kind']=outcome['failure_kind']
    chain=history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))
    history.validate_case_history(events+[deferred],claim,case,chain,cycle,observed_at=BASE+timedelta(minutes=180))
    def forbidden(): pytest.fail('second provisional pass unexpectedly accessed database')
    assert wrapper._claim_delivery(**{**args,'start_attempt':False,'factory':forbidden}) is None
    assert all(claim[key] is None for key in history.EMPTY_MARKERS)
    # Positive provider admission and real rollback persistence are hosted PG gates,
    # not claims made by this isolated pre-send synthetic test.


@pytest.mark.parametrize('fault',['unknown_body','rollback_failed','context_exit_unknown','context_exit_querycancelled'])
def test_unknown_or_unproven_rollback_never_becomes_retry_authority(fault):
    from psycopg import errors
    kwargs={}
    error=errors.LockNotAvailable('synthetic local test')
    if fault=='unknown_body': error=RuntimeError('unknown body failure')
    elif fault=='rollback_failed': kwargs['rollback_error']=RuntimeError('rollback unavailable')
    elif fault=='context_exit_unknown': kwargs['exit_error']=RuntimeError('commit outcome unknown')
    else: kwargs['exit_error']=errors.QueryCanceled('not a body statement')
    outcome,trace,data,_,_=statement_timeout_wrapper(error,**kwargs)
    assert outcome['status']=='retained_mortality_presentation_refused'
    claim,case,source,audits=data; events,cycle=case_history(case,audits)
    deferred=event(case,'exception',100,'UNSAFE',outcome['status'])
    deferred['event_payload']['failure_kind']=outcome['failure_kind']
    chain=history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))
    with pytest.raises(tx.SourceConflict,match='unsafe_case_history'):
        history.validate_case_history(events+[deferred],claim,case,chain,cycle,observed_at=BASE+timedelta(minutes=180))


@pytest.mark.parametrize('fault',['extra_field','true_ambiguity','wrong_failure','wrong_event','unbounded_timing'])
def test_known_statement_status_requires_exact_safe_persisted_shape(fault):
    claim,case,source,audits=fixture(); events,cycle=case_history(case,audits)
    status='retained_mortality_presend_statement_deferred'
    deferred=event(case,'exception',100,'DEFERRED',status); p=deferred['event_payload']; p['failure_kind']=status
    if fault=='extra_field': p['provider_sent']=True
    elif fault=='true_ambiguity': p['provider_ambiguity_contained']=True
    elif fault=='wrong_failure': p['failure_kind']='arbitrary'
    elif fault=='wrong_event': deferred['event_type']=p['event_type']='delivery_suppressed'
    else: p['processing_timings_ms']={'dispatch_wait':True,'refresh_and_delivery':0}
    chain=history.validate_audit_chain(claim,case,source,audits,observed_at=BASE+timedelta(minutes=180))
    with pytest.raises(tx.SourceConflict):
        history.validate_case_history(events+[deferred],claim,case,chain,cycle,observed_at=BASE+timedelta(minutes=180))


def test_source_body_uses_exact_persisted_json_containers_without_changing_facts():
    from modules.oom_sakkie.herdmaster_source_transaction import record_body, digest
    original = {"mission_id": "SYNTHETIC-SOURCE", "card_message_id": "SYNTHETIC-CARD",
        "_source_predecessor_digest": "private",
        "semantic_interpretation": {"breeding_actions": (),
            "observation_facts": ({"state": "YES", "count": 0, "uncertain": False},)}}
    normalized = record_body(original)
    expected = {"mission_id": "SYNTHETIC-SOURCE", "semantic_interpretation": {
        "breeding_actions": [], "observation_facts": [{"state": "YES", "count": 0, "uncertain": False}]}}
    assert normalized == expected
    assert isinstance(original["semantic_interpretation"]["breeding_actions"], tuple)
    assert normalized is not original and digest(normalized) == digest(expected)
    # Reject unsupported facts rather than stringify them into apparently valid evidence.
    with pytest.raises(TypeError):
        record_body({"mission_id": "SYNTHETIC-SOURCE", "fact": object()})
