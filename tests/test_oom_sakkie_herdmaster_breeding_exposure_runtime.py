from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_breeding_exposure_runtime import (
    ACTION_KIND,
    execute_claimed_group,
    handle_grouped_breeding_message,
    parse_grouped_exposure_reply,
)
from pathlib import Path
from modules.oom_sakkie.family_message_lifecycle import localize_recipient_result
import pytest


def _parsed(rows):
    return {
        "telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": "9001", "provider_timestamp":"2026-08-12T11:41:25Z",
        "text": "grouped breeding facts",
        "semantic": {"domain": "herd_management", "evidence_generation": "GEN-1",
                     "breeding_actions": rows},
    }


def _evidence():
    return {"success": True, "allocation_inputs": {"pig_master_rows": [
        {"Pig_ID":"SOW-1","Tag_Number":"Ms Piggy","Current_Pen_ID":"PEN-17"},
        {"Pig_ID":"SOW-2","Tag_Number":"Linda"},
        {"Pig_ID":"BOAR-1","Tag_Number":"Bola","Current_Pen_ID":"PEN-18"},
    ],"pen_lookup":{"PEN-003":{"pen_id":"PEN-003","pen_name":"Kraam Saal 03"}}}}


@pytest.mark.parametrize('distinct_tags',[True,False])
@pytest.mark.parametrize('different_dates',[True,False])
def test_same_names_keep_each_protected_sow_and_boar_distinct(distinct_tags,different_dates):
    evidence=_evidence(); master=evidence['allocation_inputs']['pig_master_rows']
    for row,tag in zip(master,['S-A','S-B','B-A']):
        row.update(Name='Mona',Tag_Number=tag if distinct_tags else 'Mona')
    actions=[{'animal_ref':pid,'action':'exposure','boar_ref':'BOAR-1',
        'exposure_started_on':'2026-08-13' if different_dates and pid=='SOW-2' else '2026-08-12',
        'planned_days':17} for pid in ['SOW-1','SOW-2']]
    captured={}
    result,status=handle_grouped_breeding_message(_parsed(actions),issue_gateway_owner_authority('42','42'),
        evidence_loader=lambda:evidence,claim_creator=lambda **kw:captured.update(kw) or {'callback_token':'T'})
    assert status==200 and result['status']=='breeding_grouped_preview_ready'
    expected=['S-A','S-B','B-A'] if distinct_tags else ['SOW-1','SOW-2','BOAR-1']
    assert all(label in result['answer'] for label in expected) and 'Mona' not in result['answer']
    rows=captured['preview_payload']['preview']['rows']
    assert {row['pig_id'] for row in rows}=={'SOW-1','SOW-2'}
    assert {row['boar_pig_id'] for row in rows}=={'BOAR-1'}
    assert result['writes_farm_data'] is False


def test_unselected_duplicate_name_still_disambiguates_selected_sow():
    evidence=_evidence(); master=evidence['allocation_inputs']['pig_master_rows']
    master[0].update(Name='Mona',Tag_Number='S-A')
    master[1].update(Name='Mona',Tag_Number='S-B')
    result,status=handle_grouped_breeding_message(_parsed([{'animal_ref':'SOW-1','action':'exposure',
        'boar_ref':'BOAR-1','exposure_started_on':'2026-08-12','planned_days':17}]),
        issue_gateway_owner_authority('42','42'),evidence_loader=lambda:evidence,
        claim_creator=lambda **kw:{'callback_token':'T'})
    assert status==200 and result['status']=='breeding_grouped_preview_ready'
    assert '<b>S-A</b>' in result['answer'] and 'Mona' not in result['answer'] and 'S-B' not in result['answer']
    assert len(result['preview']['rows'])==1 and result['preview']['rows'][0]['pig_id']=='SOW-1'


def test_semantic_placement_resolves_one_pen_and_unified_movement_preview():
    captured={}
    result,status=handle_grouped_breeding_message(_parsed([{
        "animal_ref":"Ms Piggy","action":"exposure","boar_ref":"Bola",
        "exposure_started_on":"2026-08-12","planned_days":17,
        "placement_pen_ref":"Kraam Saal 3"}]),issue_gateway_owner_authority("42","42"),
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"T"}),
        evidence_loader=_evidence)
    assert status == 200 and result["success"] is True
    preview=captured["preview_payload"]
    assert preview["creates_movement"] is True
    assert {row["pig_id"] for row in preview["preview"]["movements"]} == {"SOW-1","BOAR-1"}
    assert {row["to_pen_id"] for row in preview["preview"]["movements"]} == {"PEN-003"}


def test_authenticated_group_creates_one_existing_rail_claim_and_no_write():
    captured = {}
    def claim_creator(**kwargs):
        captured.update(kwargs)
        return {"callback_token": "TOKEN", "preview_digest": "DIGEST"}
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold",
         "body_condition_score":2,"observed_at":"2026-08-12T08:00:00+02:00",
         "factual_note":"Body condition scored 2."},
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2026-08-12T08:00:00+02:00",
         "factual_note":"Appears close to farrowing."},
    ]), issue_gateway_owner_authority("42", "42"), claim_creator=claim_creator,
        evidence_loader=_evidence)
    assert status == 200
    assert result["status"] == "breeding_grouped_preview_ready"
    assert captured["action_kind"] == ACTION_KIND
    assert captured["preview_payload"]["writes_performed"] is False
    assert result["writes_farm_data"] is False
    assert result["sends_telegram"] is False
    af = localize_recipient_result({"output_language":"af"}, result, "HERDMASTER")
    assert "BESKERMDE VOORSKOU" in af["answer"]
    assert "SOW-1" in af["answer"] and "SOW-2" in af["answer"]
    assert "recovery_hold" not in af["answer"] and "near_farrowing" not in af["answer"]
    assert [item["text"] for item in af["reply_markup"]["inline_keyboard"][0]] == [
        "Bevestig", "Maak reg", "Kanselleer"]
    assert localize_recipient_result({"output_language":"en"}, result, "HERDMASTER") == result


def test_partial_group_fails_before_claim_or_write():
    called = []
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"exposure","boar_ref":"Bola"},
    ]), issue_gateway_owner_authority("42", "42"),
        claim_creator=lambda **kwargs: called.append(kwargs), evidence_loader=_evidence)
    assert status == 200
    assert result["success"] is False
    assert called == []
    assert result["writes_farm_data"] is False


def test_ambiguous_identity_asks_one_question_before_claim():
    evidence = _evidence()
    evidence["allocation_inputs"]["pig_master_rows"].append(
        {"Pig_ID":"SOW-3","Tag_Number":"Linda"})
    result, status = handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"Close to farrowing."},
    ]), issue_gateway_owner_authority("42", "42"), evidence_loader=lambda: evidence)
    assert status == 200
    assert result["status"] == "breeding_identity_clarification_required"
    assert result["question_count"] == 1
    assert result["question_count"] == 1


def test_non_owner_is_fail_closed():
    parsed = _parsed([{"animal_ref":"Linda","action":"near_farrowing"}])
    parsed["telegram_chat_id"] = "99"
    result, status = handle_grouped_breeding_message(
        parsed, issue_gateway_owner_authority("42", "99"))
    assert status == 403
    assert result["writes_farm_data"] is False


def test_live_claim_execution_uses_governed_default_connection_factory(monkeypatch):
    captured = {}

    def fake_execute(preview, **kwargs):
        captured.update(kwargs)
        return {"success": True, "status": "grouped_operation_completed"}, 201

    monkeypatch.setattr(
        "modules.oom_sakkie.herdmaster_breeding_exposure_runtime.execute_grouped_preview",
        fake_execute,
    )
    result, status = execute_claimed_group(
        {"preview_payload": {"preview_sha256": "DIGEST"}},
        actor_id="5721652188",
        connect_factory=None,
    )

    assert status == 201 and result["success"] is True
    assert captured["confirmed_preview_sha256"] == "DIGEST"
    assert captured["actor_id"] == "5721652188"
    assert callable(captured["connect_factory"])


def test_provider_identity_and_timezone_aware_chronology_are_required_before_claim():
    for field, value in (("provider_message_id", ""), ("provider_timestamp", ""),
                         ("provider_timestamp", "2026-08-12T11:41:25"),
                         ("provider_timestamp", "not-a-time")):
        parsed = _parsed([{"animal_ref":"Linda","action":"near_farrowing"}])
        parsed[field] = value
        called = []
        result, status = handle_grouped_breeding_message(
            parsed, issue_gateway_owner_authority("42", "42"),
            evidence_loader=_evidence, claim_creator=lambda **kw: called.append(kw))
        assert status == 422
        assert result["status"] == "breeding_provider_provenance_required"
        assert result["writes_farm_data"] is False and called == []


def test_supplied_future_hold_and_farrowing_dates_fail_before_claim():
    called=[]
    result,status=handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2,
         "observed_at":"2035-01-01T00:00:00+00:00"},
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2035-01-01T00:00:00+00:00"},
    ]), issue_gateway_owner_authority("42", "42"), evidence_loader=_evidence,
        claim_creator=lambda **kw:called.append(kw))
    assert status==200 and not result['success'] and not called
    assert result['question_count']==1 and 'not in the future' in result['answer']


def test_claim_persistence_failure_is_visibly_contained_without_write():
    result,status=handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2,
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"BCS 2"},
    ]),issue_gateway_owner_authority("42","42"),evidence_loader=_evidence,
       claim_creator=lambda **_kwargs:(_ for _ in ()).throw(RuntimeError("constraint")))
    assert status == 503 and result["status"] == "breeding_group_claim_unavailable"
    assert result["writes_farm_data"] is False and "Nothing was recorded" in result["answer"]
    assert "retained" not in result["answer"].lower()
    assert "original provider-bound message" in result["answer"]


def test_existing_card_bound_claim_is_a_zero_delivery_replay():
    result,status=handle_grouped_breeding_message(_parsed([
        {"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2,
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"BCS 2"},
    ]),issue_gateway_owner_authority("42","42"),evidence_loader=_evidence,
       claim_creator=lambda **_kwargs:{"status":"protected_claim_existing",
          "callback_token":"TOKEN","preview_card_message_id":"3553"})
    assert status == 200 and result["status"] == "breeding_group_preview_replay_suppressed"
    assert result["replay_suppressed"] is True and result["suppress_owner_delivery"] is True
    assert result["answer"] == "" and result["writes_farm_data"] is False


def test_claim_kind_migration_is_idempotent_private_and_allows_breeding():
    sql=Path("supabase/migrations/202608120002_allow_breeding_protected_claims.sql").read_text().lower()
    assert "herdmaster_breeding_grouped" in sql
    assert "drop constraint" in sql and "add constraint" in sql
    assert "revoke all on app_private.oom_protected_action_claims from public, anon, authenticated" in sql
    assert "on conflict (migration_id) do nothing" in sql


def test_genuine_seven_row_update_calculates_duration_and_renders_every_fact():
    evidence={"success":True,"allocation_inputs":{"pig_master_rows":[
        {"Pig_ID":pig_id,"Tag_Number":name} for name,pig_id in
        (("Sophie","S1"),("Olive","S2"),("Shupe","S3"),("Lucy","S4"),("Lolly","S5"),
         ("Ms Piggy","S6"),("Linda","S7"),("Bola","B1"),("Tyson","B2"),("Prince","B3"))]}}
    rows=[{"animal_ref":sow,"action":"exposure","boar_ref":boar,
           "exposure_started_on":"2026-08-12","planned_days":17}
          for sow,boar in (("Sophie","Bola"),("Olive","Tyson"),("Shupe","Tyson"),
                           ("Lucy","Tyson"),("Lolly","Prince"))]
    rows += [{"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2},
             {"animal_ref":"Linda","action":"near_farrowing","prior_mating_known":False,
              "father_known":False}]
    captured={}
    result,status=handle_grouped_breeding_message(_parsed(rows),
        issue_gateway_owner_authority("42","42"),evidence_loader=lambda:evidence,
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"TOKEN"}))
    assert status == 200 and result["status"] == "breeding_grouped_preview_ready"
    preview=captured["preview_payload"]["preview"]
    assert preview["row_count"] == 7
    assert [row["planned_removal_on"] for row in preview["rows"][:5]] == ["2026-08-28"]*5
    assert all(name in result["answer"] for name in
               ("Sophie","Olive","Shupe","Lucy","Lolly","Ms Piggy","Linda"))
    assert "Nothing has been recorded yet" in result["answer"]
    assert "previous mating date and father Unknown" in result["answer"]
    assert preview["rows"][5]["observed_at"] == "2026-08-12T11:41:25+00:00"
    assert preview["rows"][6]["observed_at"] == "2026-08-12T11:41:25+00:00"


def test_retained_3556_afrikaans_boar_first_reply_parses_exactly_five_exposures():
    rows=parse_grouped_exposure_reply(
        "Plasing was vandag 2026-08-12\n\nBola - Sophie\n"
        "Tyson - Olive, Shupe, Lucy\nPrince - Lolly",
        provider_timestamp="2026-08-12T12:44:13+00:00")
    assert [(row["boar_ref"],row["animal_ref"]) for row in rows] == [
        ("Bola","Sophie"),("Tyson","Olive"),("Tyson","Shupe"),
        ("Tyson","Lucy"),("Prince","Lolly")]
    assert {row["exposure_started_on"] for row in rows} == {"2026-08-12"}
    assert {row["planned_days"] for row in rows} == {17}


def test_grouped_parser_supports_english_colons_conjunctions_and_named_date():
    rows=parse_grouped_exposure_reply(
        "Placed on 12 August 2026\nBola: Sophie and Olive\nTyson: Shupe & Lucy")
    assert [(row["boar_ref"],row["animal_ref"]) for row in rows] == [
        ("Bola","Sophie"),("Bola","Olive"),("Tyson","Shupe"),("Tyson","Lucy")]


def test_natural_removal_resolves_existing_exposure_and_matches_browser_contract():
    evidence=_evidence()
    evidence["exposure_rows"]=[{
        "exposure_event_id":"START-1","exposure_identity":"EXP-1",
        "exposure_group_identity":"GROUP-1","event_kind":"started",
        "sow_pig_id":"SOW-1","boar_pig_id":"BOAR-1","occurred_on":"2026-08-12",
        "planned_removal_on":"2026-08-28"}]
    captured={}
    result,status=handle_grouped_breeding_message(_parsed([{
        "animal_ref":"Ms Piggy","boar_ref":"Bola","action":"exposure_removal",
        "actual_removed_on":"2026-08-28"}]),issue_gateway_owner_authority("42","42"),
        evidence_loader=lambda:evidence,
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"TOKEN"}))
    assert status == 200 and result["status"] == "breeding_grouped_preview_ready"
    row=captured["preview_payload"]["preview"]["rows"][0]
    assert row["exposure_identity"] == "EXP-1"
    assert row["service_window_start"] == "2026-08-12"
    assert row["service_window_end"] == "2026-08-28"
    assert row["expected_farrowing_window_start"] == "2026-12-04"
    assert row["expected_farrowing_window_end"] == "2026-12-20"
    assert row["exact_service_date"] is None
    assert "Exact service and conception remain Unknown" in result["answer"]


def test_grouped_parser_uses_provider_date_for_today_and_ignores_explicit_not_placed():
    rows=parse_grouped_exposure_reply(
        "Vandag geplaas\nBola - Sophie\nMs Piggy en Linda was nie geplaas nie",
        provider_timestamp="2026-08-12T12:44:13+00:00")
    assert [row["animal_ref"] for row in rows] == ["Sophie"]
    assert rows[0]["exposure_started_on"] == "2026-08-12"


def test_grouped_parser_fails_closed_on_duplicate_female_or_missing_shared_date():
    assert parse_grouped_exposure_reply("Bola - Sophie\nTyson - Sophie") == ()
    assert parse_grouped_exposure_reply(
        "2026-08-12\nBola - Sophie\nTyson - Sophie") == ()


def test_deterministic_group_parser_repairs_incomplete_llm_shape_before_binding():
    evidence={"success":True,"allocation_inputs":{"pig_master_rows":[
        {"Pig_ID":pig_id,"Tag_Number":name} for name,pig_id in
        (("Sophie","S1"),("Olive","S2"),("Shupe","S3"),("Lucy","S4"),("Lolly","S5"),
         ("Bola","B1"),("Tyson","B2"),("Prince","B3"))]}}
    parsed=_parsed([{"animal_ref":"Sophie","action":"exposure","boar_ref":"Bola"}])
    parsed["provider_message_id"]="3556"
    parsed["provider_timestamp"]="2026-08-12T12:44:13+00:00"
    parsed["text"]=("Plasing was vandag 2026-08-12\n\nBola - Sophie\n"
                    "Tyson - Olive, Shupe, Lucy\nPrince - Lolly")
    captured={}
    result,status=handle_grouped_breeding_message(parsed,issue_gateway_owner_authority("42","42"),
        evidence_loader=lambda:evidence,
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"TOKEN"}))
    assert status == 200 and result["status"] == "breeding_grouped_preview_ready"
    assert captured["provider_message_id"] == "3556"
    assert captured["preview_payload"]["preview"]["row_count"] == 5
    assert {row["planned_removal_on"] for row in captured["preview_payload"]["preview"]["rows"]} == {"2026-08-28"}


def test_complete_semantic_packet_outranks_syntactically_valid_sow_first_lines():
    evidence={"success":True,"allocation_inputs":{"pig_master_rows":[
        {"Pig_ID":pig_id,"Tag_Number":name} for name,pig_id in
        (("Sophie","S1"),("Olive","S2"),("Shupe","S3"),("Lucy","S4"),("Lolly","S5"),
         ("Ms Piggy","S6"),("Linda","S7"),("Bola","B1"),("Tyson","B2"),("Prince","B3"))]}}
    rows=[{"animal_ref":sow,"action":"exposure","boar_ref":boar,
           "exposure_started_on":"2026-08-12","planned_days":17}
          for sow,boar in (("Sophie","Bola"),("Olive","Tyson"),("Shupe","Tyson"),
                           ("Lucy","Tyson"),("Lolly","Prince"))]
    rows += [{"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2},
             {"animal_ref":"Linda","action":"near_farrowing","prior_mating_known":False,
              "father_known":False}]
    parsed=_parsed(rows)
    parsed["text"]=("Breeding update for 12 August 2026\nSophie — Bola\nOlive — Tyson\n"
                    "Shupe — Tyson\nLucy — Tyson\nLolly — Prince")
    captured={}
    result,status=handle_grouped_breeding_message(parsed,issue_gateway_owner_authority("42","42"),
        evidence_loader=lambda:evidence,
        claim_creator=lambda **kwargs:(captured.update(kwargs) or {"callback_token":"TOKEN"}))
    assert status == 200 and result["status"] == "breeding_grouped_preview_ready"
    preview=captured["preview_payload"]["preview"]
    assert preview["row_count"] == 7
    assert [(row["label"],row["boar_pig_id"]) for row in preview["rows"][:5]] == [
        ("Sophie","B1"),("Olive","B2"),("Shupe","B2"),
        ("Lucy","B2"),("Lolly","B3")]
    assert {row["planned_removal_on"] for row in preview["rows"][:5]} == {"2026-08-28"}


# Synthetic owner facts; these are never sent and imply no live observation.
from datetime import datetime, timedelta, timezone

CONDITION_NOW = datetime(2026, 10, 3, 10, tzinfo=timezone.utc)


def _condition_request(**facts):
    parsed=_parsed([{'animal_ref':'Teena','action':'condition_observation',
                    'body_condition_score':3,'observed_on':'2026-10-03', **facts}])
    parsed.update(provider_timestamp=CONDITION_NOW.isoformat(), text='Teena condition 3 on 3 October 2026')
    return parsed


def _condition_evidence():
    # Actual canonical allocation reader fields, not a model-selected identity.
    return {'success':True,'allocation_inputs':{'pig_master_rows':[
        {'Pig_ID':'SOW-T','Tag_Number':'Teena','Sex':'Female','Status':'Active','On_Farm':'Yes'}]}}


def _condition_handle(parsed=None, evidence=None, **kwargs):
    calls=[]
    result,status=handle_grouped_breeding_message(parsed or _condition_request(),
        issue_gateway_owner_authority('42','42'), evidence_loader=lambda:evidence or _condition_evidence(),
        claim_creator=lambda **kw:calls.append(kw) or {'callback_token':'C'},
        now=CONDITION_NOW, **kwargs)
    return result,status,calls


@pytest.mark.parametrize('language,score_word,date_word,hold_word',[
    ('en','body condition','3 October 2026','any recovery hold stays unchanged'),
    ('af','liggaamskondisie','3 Oktober 2026','enige herstelhou bly onveranderd')])
def test_named_dated_condition_prepares_score_only_in_recipient_language(language,score_word,date_word,hold_word):
    parsed=_condition_request();parsed['output_language']=language
    result,status,calls=_condition_handle(parsed)
    assert status==200 and result['status']=='breeding_grouped_preview_ready' and len(calls)==1
    row=calls[0]['preview_payload']['preview']['rows'][0]
    assert row['pig_id']=='SOW-T' and row['action']=='condition_observation'
    assert row['body_condition_score']==3 and row['observed_at']=='2026-10-02T22:00:00+00:00'
    assert row['observation_precision']=='date' and row['observation_date']=='2026-10-03'
    assert row['observation_timezone']=='Africa/Johannesburg'
    assert row['reported_at']==CONDITION_NOW.isoformat()
    assert all(piece in result['answer'] for piece in ['Teena','3/5',score_word,date_word,hold_word])
    assert '22:00' not in result['answer'] and result['confirmation_required'] is True
    assert localize_recipient_result({'output_language':language},result,'HERDMASTER')['answer']==result['answer']
    assert calls[0]['action_kind']==ACTION_KIND and not result['writes_farm_data']
    assert len(result['answer']) < 430 and 'complete group' not in result['answer']
    assert ('Confirm to save this observation.' if language=='en' else 'Bevestig om hierdie waarneming te stoor.') in result['answer']
    assert not calls[0]['preview_payload']['creates_movement']


@pytest.mark.parametrize('score',[True,False,float('nan'),float('inf'),float('-inf'),0,5.1,'unknown',None])
def test_invalid_condition_scores_never_create_a_claim(score):
    result,status,calls=_condition_handle(_condition_request(body_condition_score=score))
    assert status==200 and not result['success'] and calls==[]
    assert 'score from 1 to 5' in result['answer'] and result['question_count']==1


@pytest.mark.parametrize('facts',[
    {'observed_on':None}, {'observed_on':'bad'}, {'observed_on':'2026-02-30'},
    {'observed_on':'2026-10-04'}, {'observed_on':None,'observed_at':'2026-10-03T10:00:00'},
    {'observed_on':'2026-10-02','observed_at':'2026-10-03T09:00:00Z'},
    {'observed_on':None,'observed_at':'2026-10-03T10:00:01Z'}])
def test_missing_malformed_future_and_conflicting_condition_dates_clarify_before_claim(facts):
    result,status,calls=_condition_handle(_condition_request(**facts))
    assert status==200 and not result['success'] and calls==[]
    assert 'On what date was this observed?' in result['answer'] and result['question_count']==1


def test_exact_aware_observation_instant_and_old_historical_date_are_preserved():
    for facts,expected,precision in [({'observed_on':None,'observed_at':'2026-10-03T11:42:13+02:00'},
                                    '2026-10-03T09:42:13+00:00','instant'),
                                   ({'observed_on':'2026-08-24'},'2026-08-23T22:00:00+00:00','date')]:
        result,status,calls=_condition_handle(_condition_request(**facts))
        assert status==200 and result['success']
        row=calls[0]['preview_payload']['preview']['rows'][0]
        assert row['observed_at']==expected and row['observation_precision']==precision
        assert ('11:42:13' in result['answer']) == (precision=='instant')
        assert 'current score' not in result['answer'].lower()


@pytest.mark.parametrize('change',[{'Status':'Sold'},{'Status':'Dead'},{'On_Farm':'No'},
                                   {'On_Farm':'Unknown'},{'Sex':'Male'}])
def test_condition_inactive_or_unproven_canonical_subject_cannot_create_claim(change):
    evidence=_condition_evidence();evidence['allocation_inputs']['pig_master_rows'][0].update(change)
    result,status,calls=_condition_handle(evidence=evidence)
    assert not result['success'] and calls==[] and 'active sow' in result['answer']


def test_condition_ambiguous_identity_and_bare_pronoun_cannot_borrow_six_subject_plan():
    evidence=_condition_evidence();evidence['allocation_inputs']['pig_master_rows'].append(
        {**evidence['allocation_inputs']['pig_master_rows'][0],'Pig_ID':'SOW-OTHER'})
    for parsed,source in [(_condition_request(),evidence),(_condition_request(animal_ref='her'),_condition_evidence())]:
        parsed['semantic']['continuation']=True
        parsed['conversation_context']=[{'canonical_read_subjects':['SOW-T','S2','S3','S4','S5','S6']}]
        result,status,calls=_condition_handle(parsed,source)
        assert not result['success'] and calls==[] and result['question_count']==1


@pytest.mark.parametrize('offset',[-21601,31])
def test_condition_stale_or_future_provider_message_refuses_before_evidence(offset):
    parsed=_condition_request();parsed['provider_timestamp']=(CONDITION_NOW+timedelta(seconds=offset)).isoformat()
    result,status,calls=_condition_handle(parsed)
    assert status==409 and result['status']=='breeding_observation_message_stale' and not calls


def test_supplied_hold_and_near_farrowing_observation_dates_are_not_replaced_by_receipt_time():
    captured=[]
    result,status=handle_grouped_breeding_message(_parsed([
        {'animal_ref':'Ms Piggy','action':'recovery_hold','body_condition_score':2,'observed_at':'2026-08-10T09:12:00+02:00'},
        {'animal_ref':'Linda','action':'near_farrowing','observed_on':'2026-08-11'}]),
        issue_gateway_owner_authority('42','42'), evidence_loader=_evidence,
        claim_creator=lambda **kw:captured.append(kw) or {'callback_token':'T'})
    assert status==200 and result['success']
    rows=captured[0]['preview_payload']['preview']['rows']
    assert [row['observed_at'] for row in rows]==['2026-08-10T07:12:00+00:00','2026-08-10T22:00:00+00:00']
    assert rows[1]['observation_precision']=='date'


def test_condition_replay_existing_card_is_silent_and_provider_identity_remains_exact():
    captured=[]
    def existing(**kw):
        captured.append(kw)
        return {'status':'protected_claim_existing','callback_token':'C','preview_card_message_id':'CARD'}
    parsed=_condition_request()
    result,status=handle_grouped_breeding_message(parsed,issue_gateway_owner_authority('42','42'),
        evidence_loader=_condition_evidence,claim_creator=existing,now=CONDITION_NOW)
    assert status==200 and result['suppress_owner_delivery'] and result['answer']==''
    assert captured[0]['provider_message_id']==parsed['provider_message_id']
    assert captured[0]['owner_user_id']==captured[0]['private_chat_id']=='42'


def test_condition_farm_manager_role_cannot_prepare_owner_only_claim():
    result,status=handle_grouped_breeding_message(_condition_request(),
        issue_gateway_owner_authority('42','42',principal_role='farm_manager',capabilities=('herd_report',)),
        evidence_loader=lambda:pytest.fail('no read before owner authority'),
        claim_creator=lambda **kw:pytest.fail('no claim'),now=CONDITION_NOW)
    assert status==403 and result['status']=='breeding_group_owner_required'


def test_condition_failed_source_result_is_not_accepted_as_current_identity():
    evidence=_condition_evidence();evidence['success']=False
    result,status,calls=_condition_handle(evidence=evidence)
    assert status==503 and result['status']=='breeding_evidence_unavailable' and not calls


@pytest.mark.parametrize('language',['en','af'])
def test_condition_stale_clarification_survives_final_recipient_localization(language):
    parsed=_condition_request();parsed.update(output_language=language,
        provider_timestamp=(CONDITION_NOW-timedelta(hours=7)).isoformat())
    result,status,calls=_condition_handle(parsed)
    delivered=localize_recipient_result({'output_language':language},result,'HERDMASTER')
    assert status==409 and not calls and result['question_count']==1
    assert delivered['answer']==result['answer'] and not delivered.get('suppress_owner_delivery')
    assert not delivered.get('recipient_language_render_unrecognized')
    assert '\n\n' in delivered['answer'] and '\\n' not in delivered['answer']
    assert delivered['status']=='breeding_observation_message_stale'
    assert ('waarnemingsdatum weer' if language=='af' else 'observation date again') in delivered['answer']


@pytest.mark.parametrize('language',['en','af'])
@pytest.mark.parametrize('reason',['date','score','identity','stale'])
def test_condition_clarification_is_deliverable_in_both_languages(reason,language):
    facts={'date':{'observed_on':None},'score':{'body_condition_score':False},
           'identity':{'animal_ref':'unknown sow'},'stale':{}}[reason]
    parsed=_condition_request(**facts);parsed['output_language']=language
    if reason=='stale':
        parsed['provider_timestamp']=(CONDITION_NOW-timedelta(hours=7)).isoformat()
    result,status,calls=_condition_handle(parsed)
    delivered=localize_recipient_result({'output_language':language},result,'HERDMASTER')
    assert not result['success'] and not calls and result['question_count']==1
    assert delivered['answer']==result['answer'] and '\n\n' in delivered['answer']
    assert not delivered.get('recipient_language_render_unrecognized')
    assert result['writes_farm_data'] is False
