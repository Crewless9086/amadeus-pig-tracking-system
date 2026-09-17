"""Pure semantic/canonical contract checks; model output is simulated."""
from dataclasses import replace
from datetime import timedelta
import json

import pytest

from modules.oom_sakkie import manager_question_runtime as questions
from modules.oom_sakkie import telegram_gateway as gateway
from modules.oom_sakkie.semantic_front_door import parse_semantic_response
from modules.pig_weights.herdmaster_natural_health_loss_intake import evaluate_health_loss_intake
from tests.test_oom_sakkie_plan_dialogue import (NOW,OWNER,MANAGER,partial_journey,
    setup_question_reply)


def interpreted(**values):
    return parse_semantic_response(json.dumps({'choices':[{'message':{'content':json.dumps({
        'domain':'herd_health','intent':'welfare_follow_up','message_kind':'observation',
        'continuation':True,'observation':'Retained owner welfare facts.','language':'en',
        'confidence':.99,**values})}}]}))


def evaluate(states,*,text='Pig PIG-2026-ABCD was standing and eating. Correction: unknown.',clinical=None):
    report={'authenticated':True,'authenticated_principal_id':OWNER,'provider_message_id':'702',
        'provider_timestamp':NOW.isoformat(),'text':text,'welfare_observation':states,
        'clinical_observation':clinical}
    canonical={'evidence_generation':'SYNTHETIC-GENERATION','as_of_timestamp':NOW.isoformat(),
        'animals':[{'pig_id':'PIG-2026-ABCD','tag_number':'SYNTHETIC-1','name':'Test animal',
            'lifecycle_status':'Active','on_farm':True,'availability':'Sale','pen':'SYNTHETIC-PEN'}],
        'matings':[],'litters':[]}
    return evaluate_health_loss_intake(report,canonical)


@pytest.mark.parametrize('key',['eating','standing','drinking','moving','breathing'])
@pytest.mark.parametrize('state',['yes','no','unknown'])
def test_typed_states_are_canonical_without_owner_phrase_reinterpretation(key,state):
    value=evaluate({key:state},text=f'Pig PIG-2026-ABCD was {key}. Correction: unknown.')
    observed={row['fact']:row['value'] for row in value['observed_facts']}
    if state=='unknown':
        assert value['status']=='welfare_observation_uncertain'
        assert key+'_reported' not in observed
        assert not value.get('canonical_effects')
    else:
        assert value['success'] is True and observed[key+'_reported'] is (state=='yes')
        assert value['event_family']==('sick' if state=='no' else 'welfare_update')
        if state=='no':
            assert value['immediate_welfare_priority']['level']=='urgent_assessment'
            assert 'reassuring' not in value['immediate_welfare_priority']['action']
        assert all(effect['area']=='medical_observation' for effect in value['canonical_effects']
            if effect['supported'])
    # Old prose cannot carry an affirmative state into this typed correction.
    assert set(observed) <= {'event_date',key+'_reported'}


@pytest.mark.parametrize('bad',[{'cause':'infection'},{'eating':True},{'standing':'maybe'},[],
    {'drinking':1},{'moving':None}])
def test_invalid_typed_model_facts_make_interpretation_unavailable(bad):
    assert interpreted(welfare_observation=bad) is None


def test_explicit_unknown_and_absent_fact_remain_distinct():
    missing=interpreted(welfare_observation={'eating':'yes'})
    unknown=interpreted(welfare_observation={'eating':'yes','drinking':'unknown'},
        needs_clarification=False,clarification_question='')
    assert 'drinking' not in missing.welfare_observation
    assert unknown.welfare_observation['drinking']=='unknown' and unknown.needs_clarification


@pytest.mark.parametrize('sign',['injury','limping','wound','bleeding','broken_bone','swelling',
    'illness','vomiting','diarrhoea','cough','fever'])
@pytest.mark.parametrize('state',['yes','no','unknown'])
def test_clinical_meaning_survives_language_and_typed_correction(sign,state):
    value=evaluate({'standing':'yes'},text='Vark PIG-2026-ABCD. Hy staan.',
        clinical={sign:state})
    observed={row['fact']:row['value'] for row in value['observed_facts']}
    assert observed['standing_reported'] is True
    if state=='unknown':
        assert value['status']=='welfare_observation_uncertain'
        assert sign not in observed and not value['canonical_effects']
    else:
        assert observed[sign] is (state=='yes')
        assert all(row['area']=='medical_observation' for row in value['canonical_effects'] if row['supported'])
    if state=='yes':
        assert value['immediate_welfare_priority']['level']=='urgent_assessment'
        assert 'reassuring' not in value['immediate_welfare_priority']['action']
        assert not ({'injury','illness'}-{sign}) & set(observed)
    parsed=interpreted(clinical_observation={sign:state})
    assert parsed.clinical_observation=={sign:state}
    assert parsed.needs_clarification is (state=='unknown')


@pytest.mark.parametrize('bad',[{'diagnosis':'infection'},{'bleeding':True},
    {'fever':'maybe'},[],{'injury':1},{'wound':None}])
def test_clinical_map_rejects_invalid_model_states_and_unbounded_fields(bad):
    assert interpreted(clinical_observation=bad) is None


@pytest.mark.parametrize('state',['no','unknown'])
def test_clinical_correction_clears_only_the_addressed_sign(state):
    from modules.pig_weights.herdmaster_natural_health_loss_intake import _typed_welfare_report
    parsed=_typed_welfare_report({'standing':'yes'},NOW,'He is bleeding and coughing.',
        clinical={'bleeding':state})
    facts={row['fact']:row['value'] for row in parsed['observed']}
    assert facts.get('bleeding') is not True and parsed['clinical_checks']['cough'] is True
    assert 'cough' not in facts  # Raw wording alone cannot add a newly typed clinical fact.
    assert parsed['family']=='sick' and parsed['current_signs'] and parsed['severe_signs']
    cleared=_typed_welfare_report(None,NOW,'He is bleeding.',clinical={'bleeding':'no'})
    assert not cleared['current_signs'] and not cleared['severe_signs']


def test_clinical_only_afrikaans_report_is_not_a_reassuring_recovery():
    value=evaluate(None,text='Vark PIG-2026-ABCD. Hy bloei.',clinical={'bleeding':'yes'})
    assert value['event_family']=='injured'
    assert value['immediate_welfare_priority']['level']=='urgent_assessment'
    assert {'fact':'bleeding','value':True,'attribution':'owner_reported_observation'} in value['observed_facts']


def test_accumulated_unknown_clinical_sign_cannot_be_completed_by_omission(monkeypatch):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    partial={**partial,'semantic_facts':{**partial['semantic_facts'],
        'clinical_observation':{'bleeding':'unknown'}}}
    value=interpreted(welfare_observation={'standing':'yes'},needs_clarification=False)
    result,status=questions.handle_manager_question_reply(
        {**parsed,'provider_message_id':'702','provider_timestamp':(NOW+timedelta(minutes=1)).isoformat()},
        authority,value,question={**question,'partial_replies':[partial]})
    assert status==200 and result['status']=='manager_question_partial_reply_recorded'
    assert all(row['status']=='partial' for row in rows.values())


@pytest.mark.parametrize('language',['en','af'])
@pytest.mark.parametrize('states',[{'clinical_observation':{'bleeding':'yes'}},
    {'welfare_observation':{'breathing':'no'}}])
def test_partial_adverse_answer_has_immediate_guidance_in_configured_language(monkeypatch,language,states):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    clarification='Drink hy water?' if language=='af' else 'Is he drinking water?'
    semantic=interpreted(**states,language='unknown',needs_clarification=True,
        clarification_question=clarification)
    result,status=questions.handle_manager_question_reply(
        {**parsed,'provider_message_id':'702','output_language':language,
         'provider_timestamp':(NOW+timedelta(minutes=1)).isoformat()},
        authority,semantic,question={**question,'partial_replies':[partial]})
    assert status==200 and result['question_count']==1 and result['answer'].endswith(clarification)
    assert result['answer'].startswith('Dringend:' if language=='af' else 'Physically assess')
    assert result['recipient_language']==language and result['writes_farm_data'] is False


@pytest.mark.parametrize('state',['yes','unknown'])
def test_typed_correction_removes_only_its_old_negative_and_derived_urgency(state):
    from modules.pig_weights.herdmaster_natural_health_loss_intake import _typed_welfare_report
    for extra in ('',' He is bleeding.'):
        parsed=_typed_welfare_report({'drinking':state},NOW,'He is not drinking.'+extra)
        assert 'not_drinking' not in {row['fact'] for row in parsed['observed']}
        assert parsed['current_signs'] is bool(extra) and parsed['severe_signs'] is bool(extra)
        assert parsed['family']==('injured' if extra else 'welfare_update')


def test_independent_death_and_its_date_requirement_survive_typed_unknown():
    value=evaluate({'drinking':'unknown'},text='Pig PIG-2026-ABCD died.')
    assert value['status']=='event_date_required' and value['event_family']=='found_dead'
    assert {'fact':'animal_reported_dead','value':True} in value['observed_facts']


def test_typed_unknown_retains_independent_injury_priority_and_attributions():
    value=evaluate({'drinking':'unknown'},text='Pig PIG-2026-ABCD is bleeding. '
        'I suspect he has infection. The vet confirmed a wound.')
    assert value['status']=='welfare_observation_uncertain' and value['event_family']=='injured'
    assert value['immediate_welfare_priority']['level']=='urgent_assessment'
    assert value['owner_suspected_cause'] and value['veterinary_evidence']
    assert value['canonical_effects']==[]


def test_accumulated_unknown_is_not_completed_by_a_different_answer(monkeypatch):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    partial={**partial,'semantic_facts':{**partial['semantic_facts'],
        'welfare_observation':{'drinking':'unknown'}}}
    value=interpreted(welfare_observation={'standing':'yes'},needs_clarification=False)
    result,status=questions.handle_manager_question_reply(
        {**parsed,'provider_message_id':'702','provider_timestamp':(NOW+timedelta(minutes=1)).isoformat()},
        authority,value,question={**question,'partial_replies':[partial]})
    assert status==200 and result['status']=='manager_question_partial_reply_recorded'
    assert all(row['status']=='partial' for row in rows.values())


def test_future_delivered_clarification_is_not_in_earlier_reply_context(monkeypatch):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    partial={**partial,'clarification_presented_at':(NOW+timedelta(minutes=10)).isoformat()}
    context=questions.semantic_context_with_manager_question(
        {**parsed,'provider_message_id':'702','provider_timestamp':(NOW+timedelta(minutes=5)).isoformat()},
        base_context_loader=lambda _: {'recent_turns':[]},question={**question,'partial_replies':[partial]})
    assert len(context['recent_turns'])==2 and context['recent_turns'][-1]['specialist']=='OWNER'


def test_unsent_clarification_is_not_presented_as_a_conversation_turn(monkeypatch):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    partial={**partial,'clarification_telegram_message_id':'','clarification_presented_at':''}
    context=questions.semantic_context_with_manager_question(
        {**parsed,'provider_message_id':'702','provider_timestamp':(NOW+timedelta(minutes=5)).isoformat()},
        base_context_loader=lambda _: {'recent_turns':[]},question={**question,'partial_replies':[partial]})
    assert len(context['recent_turns'])==2 and context['recent_turns'][-1]['specialist']=='OWNER'


@pytest.mark.parametrize('language',['en','af'])
def test_missing_clarification_text_never_completes_an_unresolved_answer(monkeypatch,language):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    value=interpreted(language=language,needs_clarification=True,clarification_question='')
    result,status=questions.handle_manager_question_reply(
        {**parsed,'provider_message_id':'702','provider_timestamp':(NOW+timedelta(minutes=1)).isoformat(),
         'text':'Ek weet nog nie.' if language=='af' else 'I do not know yet.'},authority,value,
        question={**question,'partial_replies':[partial]})
    assert status==200 and result['status']=='manager_question_partial_reply_recorded'
    assert result['answer']==partial['clarification_question']
    assert len(rows)==2 and all(row['status']=='partial' for row in rows.values())


def test_provider_older_inbound_never_gets_future_partial_context(monkeypatch):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    context=questions.semantic_context_with_manager_question(
        {**parsed,'provider_message_id':'699','provider_timestamp':(NOW-timedelta(seconds=1)).isoformat()},
        base_context_loader=lambda _: {'recent_turns':[]},question={**question,'partial_replies':[partial]})
    assert len(context['recent_turns'])==1
    assert context['recent_turns'][0]['clarification_question']==question['question']


@pytest.mark.parametrize('kind',['question','request','command','confirmation'])
def test_non_observation_is_not_a_completed_farm_answer(monkeypatch,kind):
    question,parsed,semantic,authority,rows,partial=partial_journey(monkeypatch)
    result,status=questions.handle_manager_question_reply(
        {**parsed,'provider_message_id':'702','provider_timestamp':(NOW+timedelta(minutes=1)).isoformat()},
        authority,replace(semantic,message_kind=kind,needs_clarification=False),
        question={**question,'partial_replies':[partial]})
    assert result['handled'] is False and len(rows)==1


@pytest.mark.parametrize('specialist_status',['preview_ready','waiting_for_input'])
def test_retained_specialist_next_step_recovers_after_pre_delivery_interruption(monkeypatch,specialist_status):
    invoke,rows,deliveries,bound,refreshes,health_inputs,specialist=setup_question_reply(
        monkeypatch,specialist_status=specialist_status)
    attempts=[]
    def deliver(parsed,result,**kwargs):
        attempts.append(result)
        if len(attempts)==1:
            return {'success':False,'status':'synthetic_interruption_before_delivery',
                    'telegram_sends':0,'telegram_edits':0}
        return {'success':True,'telegram_message_id':'702','telegram_sends':1,'telegram_edits':0}
    monkeypatch.setattr(gateway,'deliver_family_result',deliver)
    first,status=invoke();recovered,replay_status=invoke()
    assert status==202 and replay_status==200
    assert len(rows)==1 and len(health_inputs)==1 and len(attempts)==2
    assert attempts[1]['answer']==specialist['answer'] and recovered['sends_telegram']
    assert bound==([] if specialist_status=='waiting_for_input' else [('synthetic-confirmation-token','702')])
