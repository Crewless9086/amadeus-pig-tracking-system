import json
from unittest.mock import patch
import pytest

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_runtime import _resolve_active_context
from modules.oom_sakkie.semantic_front_door import (
    SemanticInterpretation, _eligible_clarification_context, interpret_media_owner_context,
    interpret_owner_message, parse_semantic_response,
    semantic_front_door_policy,
)


MEDIA_ENV = {"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
    "OOM_SAKKIE_LLM_ROUTER_MODEL": "semantic-test", "OPENAI_API_KEY": "secret"}


def test_media_context_uses_typed_affirmative_semantics_and_binds_digest():
    value = {"subject_tags": ["live_stock", "piglets", "litter"],
        "affirmative_current_subject": True, "negated_or_absent": False,
        "historical_or_future_only": False, "conflicting_subject": False,
        "needs_clarification": False, "confidence": .96}
    result = interpret_media_owner_context("Bella het pas 13 varkies gekry", "a" * 64,
        environ=MEDIA_ENV, http_open=lambda *_args, **_kwargs: _HttpResponse(_response(value)))
    assert result.subject_tags == ("litter", "live_stock", "piglets")
    assert result.model == "semantic-test" and len(result.semantic_digest) == 64


@pytest.mark.parametrize("override", [
    {"negated_or_absent": True}, {"historical_or_future_only": True},
    {"conflicting_subject": True}, {"needs_clarification": True}, {"confidence": .79},
])
def test_media_context_fails_closed_on_negation_time_conflict_ambiguity_or_low_confidence(override):
    value = {"subject_tags": ["live_stock", "piglets"],
        "affirmative_current_subject": True, "negated_or_absent": False,
        "historical_or_future_only": False, "conflicting_subject": False,
        "needs_clarification": False, "confidence": .96, **override}
    assert interpret_media_owner_context("bounded context", "b" * 64, environ=MEDIA_ENV,
        http_open=lambda *_args, **_kwargs: _HttpResponse(_response(value))) is None
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
from modules.oom_sakkie.service import handle_message


def _response(value):
    return json.dumps({"choices": [{"message": {"content": json.dumps(value)}}]})


class _HttpResponse:
    def __init__(self, body): self.body = body
    def __enter__(self): return self
    def __exit__(self, *_args): return False
    def read(self): return self.body.encode()


def _semantic(domain, intent, **extra):
    return {"domain": domain, "intent": intent, "message_kind": extra.get("message_kind", "general"),
        "entity_refs": extra.get("entity_refs", []),
        "continuation": extra.get("continuation", False), "observation": extra.get("observation", ""),
        "observation_facts": extra.get("observation_facts", []),
        "confirmation_facts": extra.get("confirmation_facts"),
        "breeding_actions": extra.get("breeding_actions", []),
        "farrowing_litter": extra.get("farrowing_litter"),
        "litter_first_treatment": extra.get("litter_first_treatment"),
        "protected_preview_required": extra.get("protected_preview_required", False),
        "recording_prohibited": extra.get("recording_prohibited", False),
        "requested_action": extra.get("requested_action", ""), "language": extra.get("language", "en"),
        "confidence": extra.get("confidence", .98), "needs_clarification": False,
        "clarification_question": ""}


@pytest.mark.parametrize("language", ["en", "af", "mixed"])
def test_farrowing_semantic_family_returns_typed_counts_not_numeric_animals(language):
    value = _semantic("herd_management", "record_farrowing_litter", message_kind="command",
        language=language, entity_refs=["Linda"], farrowing_litter={"sow_ref": "Linda",
            "farrowing_date": "2026-08-22", "total_born": 9, "born_alive": 8,
            "stillborn": None, "mummified": 1, "died_after_live_birth": None,
            "mating_ref": None, "father_ref": None})
    result = parse_semantic_response(_response(value))
    assert result.intent == "record_farrowing_litter"
    assert result.entity_refs == ("Linda",)
    assert result.farrowing_litter["sow_ref"] == "Linda"
    assert result.farrowing_litter["total_born"] == 9


def test_farrowing_correction_contract_preserves_target_and_reason():
    value = _semantic("herd_management", "record_farrowing_litter", message_kind="correction",
        farrowing_litter={"sow_ref": "Linda", "farrowing_date": "2026-08-22",
            "total_born": 9, "born_alive": 8, "stillborn": 0, "mummified": 1,
            "died_after_live_birth": 0, "mating_ref": None, "father_ref": None,
            "correction_of_litter_id": "LIT-OLD", "correction_reason": "Corrected birth counts"})
    result = parse_semantic_response(_response(value))
    assert result.farrowing_litter["correction_of_litter_id"] == "LIT-OLD"
    assert result.farrowing_litter["correction_reason"] == "Corrected birth counts"


def test_first_treatment_is_typed_and_mutually_exclusive_from_farrowing():
    treatment = {"sow_ref": "Molly", "action_date": "2026-08-25",
        "male_count": 4, "female_count": 4, "total_count": 8,
        "earmarked": True, "antiparasitic_product_ref": "Iron Plus",
        "dose": "1 ml", "route": "injection", "batch_lot_number": "LOT-7"}
    value = _semantic("herd_management", "record_litter_first_treatment",
        message_kind="command", entity_refs=["Molly"], litter_first_treatment=treatment)
    result = parse_semantic_response(_response(value))
    assert result.intent == "record_litter_first_treatment"
    assert result.litter_first_treatment["total_count"] == 8
    assert result.farrowing_litter is None
    value["farrowing_litter"] = {"sow_ref": "Molly", "farrowing_date": "2026-08-25",
        "total_born": 8, "born_alive": 8, "stillborn": 0, "mummified": 0,
        "died_after_live_birth": 0}
    assert parse_semantic_response(_response(value)) is None


@pytest.mark.parametrize("text,language", [
    ("Linda gave birth on 2026-08-22: born 9, 8 alive and 1 mummified. Log the litter.", "en"),
    ("Linda het 2026-08-22 gekraam: 9 gebore, 8 lewendig en 1 gemummifiseer. Teken die werpsel aan.", "af"),
    ("Linda farrowed 2026-08-22, 9 gebore, 8 alive, 1 gemummifiseer; log dit.", "mixed"),
    ("Linda 2026-08-22; total 9; alive 8; mummified 1; log litter", "en"),
])
def test_actual_natural_farrowing_phrase_family_reaches_one_typed_contract(text, language):
    captured = {}
    semantic = _semantic("herd_management", "record_farrowing_litter",
        message_kind="command", language=language, entity_refs=["Linda"],
        farrowing_litter={"sow_ref": "Linda", "farrowing_date": "2026-08-22",
            "total_born": 9, "born_alive": 8, "stillborn": None,
            "mummified": 1, "died_after_live_birth": None,
            "mating_ref": None, "father_ref": None})
    def opener(request, timeout):
        captured.update(json.loads(request.data.decode()))
        return _HttpResponse(_response(semantic))
    result = interpret_owner_message({"text": text, "provider_message_id": "NATURAL-LITTER"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"},
        context_loader=lambda parsed: {}, http_open=opener)
    assert result.intent == "record_farrowing_litter"
    assert result.farrowing_litter["total_born"] == 9
    assert result.farrowing_litter["born_alive"] == 8
    assert result.farrowing_litter["mummified"] == 1
    assert text in captured["messages"][1]["content"]


def test_semantic_front_door_is_llm_first_but_has_zero_authority():
    policy = semantic_front_door_policy({"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"})
    assert policy["enabled"] and policy["configured"]
    assert not policy["can_execute"] and not policy["can_write"]
    assert not policy["can_send"] and not policy["can_control_hardware"]


@pytest.mark.parametrize("text,language,continuation", [
    ("Prepare a non-availability farm-awareness campaign.", "en", False),
    ("Berei asseblief 'n plaasbewustheidsveldtog voor wat niks te koop aanbied nie.", "af", False),
    ("Let's doen net 'n farm story, geen verkope nie.", "mixed", False),
    ("Ja, daardie plaasstorie.", "af", True),
])
def test_awareness_semantic_family_preserves_stable_intent(text, language, continuation):
    captured = {}
    def open_request(request, timeout):
        captured.update(json.loads(request.data.decode()))
        return _HttpResponse(_response(_semantic("beacon", "live_stock_awareness",
            message_kind="request", language=language, continuation=continuation)))
    result = interpret_owner_message({"text": text, "provider_message_id": "AWARENESS-1"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"},
        context_loader=lambda parsed: ({"recent_turns": [{"semantic_domain": "beacon",
            "semantic_intent": "live_stock_awareness"}]} if continuation else {}), http_open=open_request)
    assert result.domain == "beacon" and result.intent == "live_stock_awareness"
    assert result.language == language and result.continuation is continuation
    assert "stable intent live_stock_awareness" in captured["messages"][0]["content"]


@pytest.mark.parametrize("text,language,continuation", [
    ("Show me Bella's private album so I can review it for the Library.", "en", False),
    ("Wys asseblief Bella se privaat foto-album vir Biblioteek-hersiening.", "af", False),
    ("Let's review die private foto's, but publish niks nie.", "mixed", False),
    ("Ja, wys daardie album se aparte besluite.", "af", True),
])
def test_private_media_review_semantic_family_preserves_stable_intent(text, language, continuation):
    captured = {}
    def open_request(request, timeout):
        captured.update(json.loads(request.data.decode()))
        return _HttpResponse(_response(_semantic("beacon", "private_media_library_review",
            message_kind="request", language=language, continuation=continuation)))
    result = interpret_owner_message({"text": text, "provider_message_id": "MEDIA-REVIEW-1"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"},
        context_loader=lambda parsed: ({"recent_turns": [{"semantic_domain": "beacon",
            "semantic_intent": "private_media_library_review"}]} if continuation else {}),
        http_open=open_request)
    assert result.domain == "beacon" and result.intent == "private_media_library_review"
    assert result.language == language and result.continuation is continuation
    assert "stable intent private_media_library_review" in captured["messages"][0]["content"]


@pytest.mark.parametrize("text,language,continuation", [
    ("Please print the weekly weighing sheet.", "en", False),
    ("Druk asseblief die weeklikse weegstaat.", "af", False),
    ("Kan Oom die pigs se weekly sheet laat druk?", "mixed", False),
    ("Ja, druk daardie staat.", "af", True),
])
def test_documents_print_semantic_family_uses_one_stable_intent(
        text,language,continuation):
    captured={}
    def open_request(request,timeout):
        captured.update(json.loads(request.data.decode()))
        return _HttpResponse(_response(_semantic("documents",
            "weekly_weighing_sheet_print",message_kind="request",
            language=language,continuation=continuation,
            protected_preview_required=True)))
    result=interpret_owner_message({"text":text,"provider_message_id":"DOC-PRINT-1"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL":"test","OPENAI_API_KEY":"secret"},
        context_loader=lambda parsed:({"recent_turns":[{
            "semantic_domain":"documents",
            "semantic_intent":"weekly_weighing_sheet_print"}]} if continuation else {}),
        http_open=open_request)
    assert result.domain=="documents" and result.intent=="weekly_weighing_sheet_print"
    assert result.language==language and result.continuation is continuation
    assert result.protected_preview_required is True
    assert "stable intent weekly_weighing_sheet_print" in captured["messages"][0]["content"]


def test_ambiguous_documents_semantic_result_retains_one_clarification():
    payload=_semantic("documents","weekly_weighing_sheet_print",message_kind="request")
    payload.update({"needs_clarification":True,
        "clarification_question":"Do you want the weekly weighing sheet printed?"})
    result=interpret_owner_message({"text":"Print that one","provider_message_id":"DOC-2"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL":"test","OPENAI_API_KEY":"secret"},
        context_loader=lambda parsed:{},
        http_open=lambda request,timeout:_HttpResponse(_response(payload)))
    assert result.domain=="documents" and result.needs_clarification is True
    assert result.clarification_question=="Do you want the weekly weighing sheet printed?"


def test_unrelated_print_language_is_not_documents_intent():
    result=interpret_owner_message({"text":"What is today's farm plan?",
        "provider_message_id":"DOC-3"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL":"test","OPENAI_API_KEY":"secret"},
        context_loader=lambda parsed:{},http_open=lambda request,timeout:_HttpResponse(
            _response(_semantic("manager_round","daily_brief",message_kind="question"))))
    assert result.domain=="manager_round" and result.intent=="daily_brief"


def test_english_death_update_is_typed_as_herd_evidence():
    result = parse_semantic_response(_response(_semantic("herd_health", "death_report",
        entity_refs=["Pig 127"], continuation=True,
        observation="Pig 127 is reported dead and buried.")))
    assert result.domain == "herd_health" and result.continuation
    assert result.entity_refs == ("Pig 127",)
    assert "dead" in result.observation


def test_afrikaans_death_update_preserves_entity_and_meaning():
    result = parse_semantic_response(_response(_semantic("herd_health", "death_report",
        entity_refs=["Vark 127"], continuation=True, language="af",
        observation="Pig 127 is reported dead and buried.")))
    assert result.language == "af" and result.domain == "herd_health"
    assert result.entity_refs == ("Vark 127",)


def test_irrigation_shutdown_is_evidence_not_legacy_status_lookup():
    result = parse_semantic_response(_response(_semantic("rootline", "irrigation_shutdown_observed",
        entity_refs=["C Camp"], continuation=True,
        observation="C Camp irrigation physically stopped.")))
    assert result.domain == "rootline" and result.continuation
    assert result.intent == "irrigation_shutdown_observed"


def test_afrikaans_irrigation_followup_is_understood():
    result = parse_semantic_response(_response(_semantic("rootline", "irrigation_shutdown_observed",
        entity_refs=["C-kamp"], continuation=True, language="af",
        observation="C Camp irrigation physically stopped.")))
    assert result.language == "af" and result.domain == "rootline"


def test_typed_water_facts_preserve_two_independent_observations():
    result = parse_semantic_response(_response(_semantic("rootline", "water_levels_observed",
        message_kind="observation", observation="Storage tanks and reservoir are full.",
        observation_facts=[{"subject":"storage_tanks","state":"FULL"},
                           {"subject":"reservoir","state":"FULL"}])))
    assert result.observation_facts == ({"subject":"storage_tanks","state":"FULL"},
                                        {"subject":"reservoir","state":"FULL"})


def test_malformed_or_duplicated_typed_water_facts_fail_closed():
    for facts in ([{"subject":"tank","state":"FULL"}],
                  [{"subject":"reservoir","state":"FULL"},{"subject":"reservoir","state":"LOW"}],
                  [{"subject":"storage_tanks","numerator":4,"denominator":0}]):
        result = parse_semantic_response(_response(_semantic("rootline", "water_levels_observed",
            message_kind="observation", observation="tank update", observation_facts=facts)))
        assert result.observation_facts == ()


def test_typed_configuration_confirmation_preserves_explicit_polarity():
    result = parse_semantic_response(_response(_semantic("rootline", "commissioning_ready",
        message_kind="confirmation", continuation=True,
        confirmation_facts={"interlock_off":False,"no_enabled_scene":False})))
    assert result.confirmation_facts=={"interlock_off":False,"no_enabled_scene":False}


def test_malformed_configuration_confirmation_facts_fail_closed():
    for facts in ({"interlock_off":"yes"},{"unknown_setting":True},{}):
        result = parse_semantic_response(_response(_semantic("rootline", "commissioning_ready",
            message_kind="confirmation", continuation=True,confirmation_facts=facts)))
        assert result.confirmation_facts is None


def test_grouped_breeding_preview_facts_remain_complete_and_typed():
    facts = [
        {"action":"exposure","animal_ref":name,"boar_ref":boar,"exposure_started_on":"2026-08-12","planned_days":17}
        for name,boar in (("Sophie","Bola"),("Olive","Tyson"),("Shupe","Tyson"),
                          ("Lucy","Tyson"),("Lolly","Prince"))]
    facts += [{"action":"recovery_hold","animal_ref":"Ms Piggy","body_condition_score":2},
              {"action":"near_farrowing","animal_ref":"Linda","prior_mating_known":False,
               "father_known":False}]
    result = parse_semantic_response(_response(_semantic("herd_management","breeding_update",
        message_kind="observation",continuation=True,breeding_actions=facts,
        protected_preview_required=True,recording_prohibited=True)))
    assert len(result.breeding_actions) == 7
    assert result.protected_preview_required and result.recording_prohibited
    assert [row["animal_ref"] for row in result.breeding_actions] == [
        "Sophie","Olive","Shupe","Lucy","Lolly","Ms Piggy","Linda"]


def test_duplicate_or_partial_grouped_breeding_shape_fails_closed():
    facts = [{"action":"exposure","animal_ref":"Sophie","boar_ref":"Bola",
              "exposure_started_on":"2026-08-12","planned_days":17},
             {"action":"recovery_hold","animal_ref":"Sophie","body_condition_score":2}]
    result = parse_semantic_response(_response(_semantic("herd_management","breeding_update",
        breeding_actions=facts,protected_preview_required=True,recording_prohibited=True)))
    assert result.breeding_actions == ()


def test_only_fresh_earlier_unambiguous_clarification_context_is_exposed():
    parsed={"provider_timestamp":"2026-08-09T07:33:06+00:00","reply_to_message_id":"700"}
    fresh={"state":"delivered","telegram_message_id":"700",
        "delivery_provider_timestamp":"2026-08-09T07:30:00+00:00",
        "clarification_question":"Storage tanks, reservoir, or both?","semantic_domain":"rootline"}
    stale={**fresh,"telegram_message_id":"699","delivery_provider_timestamp":"2026-08-08T07:30:00+00:00"}
    unrelated={**fresh,"telegram_message_id":"701","clarification_question":"Which animals?",
        "semantic_domain":"herd_management"}
    assert _eligible_clarification_context([stale,unrelated,fresh],parsed)==[fresh]
    assert _eligible_clarification_context([fresh],{**parsed,"reply_to_message_id":"999"})==[]


def test_provider_notification_is_the_visible_reply_identity_for_typed_specialist_wait():
    parsed={"provider_timestamp":"2026-08-10T09:44:00+00:00","reply_to_message_id":"3497"}
    notice={"state":"notification_delivered","telegram_message_id":"3480",
        "notification_message_id":"3497","task_state":"waiting_for_input",
        "delivery_provider_timestamp":"2026-08-10T09:43:09+00:00",
        "semantic_domain":"rootline","semantic_intent":"fertilizer_commissioning_presence",
        "clarification_question":""}
    projected=_eligible_clarification_context([notice],parsed)
    assert len(projected)==1 and projected[0]["telegram_message_id"]=="3497"
    delayed={**parsed,"provider_timestamp":"2026-08-17T09:44:00+00:00",
        "reply_to_message_id":""}
    assert len(_eligible_clarification_context([notice],delayed))==1
    expired={**parsed,"provider_timestamp":"2026-09-10T09:44:00+00:00",
        "reply_to_message_id":""}
    assert _eligible_clarification_context([notice],expired)==[]
    scheduler={**notice,"semantic_intent":"rootline_reassessment",
        "notification_message_id":"3500"}
    assert _eligible_clarification_context([scheduler],delayed)==[]


@pytest.mark.parametrize("text,language", [
    ("Yes, I'm still here.","en"),("Ja, ek is nog by die kleppe!","af")])
def test_delayed_short_readiness_reply_receives_typed_active_context(text,language):
    captured={}
    def opener(request,timeout):
        captured.update(json.loads(request.data.decode()))
        return _HttpResponse(_response(_semantic("rootline","availability_confirmation",
            message_kind="confirmation",continuation=True,language=language)))
    notice={"state":"notification_delivered","telegram_message_id":"3480",
        "notification_message_id":"3497","task_state":"waiting_for_input",
        "delivery_provider_timestamp":"2026-08-10T09:43:09+00:00",
        "semantic_domain":"rootline","semantic_intent":"fertilizer_commissioning_presence"}
    result=interpret_owner_message({"text":text,"telegram_user_id":"42","telegram_chat_id":"42",
        "provider_message_id":"3501","provider_timestamp":"2026-08-17T09:44:00+00:00"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL":"test","OPENAI_API_KEY":"secret"},
        context_loader=lambda parsed:{"recent_turns":_eligible_clarification_context([notice],parsed)},
        http_open=opener)
    sent=json.loads(captured["messages"][1]["content"])["context"]
    assert result.continuation is True and sent["recent_turns"][0]["telegram_message_id"]=="3497"


@pytest.mark.parametrize("text,language", [("Ready","en"),("Ja","af")])
def test_completed_lifecycle_suppresses_old_typed_wait_from_semantic_context(text,language):
    notice={"state":"notification_delivered","mission_id":"MISSION","card_mission_id":"MISSION",
        "telegram_message_id":"3480","notification_message_id":"3497",
        "task_state":"waiting_for_input","delivery_provider_timestamp":"2026-08-10T09:43:09+00:00",
        "semantic_domain":"rootline","semantic_intent":"fertilizer_commissioning_presence"}
    completed={"state":"updated","mission_id":"MISSION","card_mission_id":"MISSION",
        "telegram_message_id":"3480","task_state":"completed",
        "provider_timestamp":"2026-08-10T10:00:00+00:00","semantic_domain":"rootline"}
    parsed={"text":text,"provider_message_id":"3502",
        "provider_timestamp":"2026-08-10T10:01:00+00:00","reply_to_message_id":"3497"}
    assert _eligible_clarification_context([completed,notice],parsed)==[]
    captured={}
    def opener(request,timeout):
        captured.update(json.loads(request.data.decode()))
        return _HttpResponse(_response(_semantic("general","general_clarification",
            message_kind="confirmation",continuation=False,language=language,
            needs_clarification=True,clarification_question="What should I help with?")))
    result=interpret_owner_message(parsed,
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1",
            "OOM_SAKKIE_LLM_ROUTER_MODEL":"test","OPENAI_API_KEY":"secret"},
        context_loader=lambda value:{"recent_turns":_eligible_clarification_context(
            [completed,notice],value)},http_open=opener)
    sent=json.loads(captured["messages"][1]["content"])["context"]
    assert sent["recent_turns"]==[] and result.continuation is False


def test_stale_context_cannot_turn_ambiguous_reply_into_canonical_water_facts():
    response=_semantic("rootline","water_levels_observed",message_kind="observation",
        observation="Both reported full.",observation_facts=[
            {"subject":"storage_tanks","state":"FULL"},{"subject":"reservoir","state":"FULL"}])
    result=interpret_owner_message({"text":"Albei vol","provider_message_id":"3477",
        "provider_timestamp":"2026-08-09T07:33:06+00:00"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1","OOM_SAKKIE_LLM_ROUTER_MODEL":"test",
                 "OPENAI_API_KEY":"secret"},http_open=lambda *_args,**_kwargs:_HttpResponse(_response(response)),
        context_loader=lambda _parsed:{"recent_turns":[{"state":"delivered","telegram_message_id":"700",
            "delivery_provider_timestamp":"2026-08-08T07:30:00+00:00","semantic_domain":"rootline",
            "clarification_question":"Storage tanks, reservoir, or both?"}]})
    assert result.observation_facts==() and result.needs_clarification is True


def test_generic_singular_tank_words_cannot_select_a_canonical_subject():
    for text in ("The tank is full", "Die tenk is vol"):
        response=_semantic("rootline","water_levels_observed",message_kind="observation",
            observation=text,observation_facts=[{"subject":"storage_tanks","state":"FULL"}])
        result=interpret_owner_message({"text":text,"provider_message_id":"3477",
            "provider_timestamp":"2026-08-09T07:33:06+00:00"},
            environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1","OOM_SAKKIE_LLM_ROUTER_MODEL":"test",
                     "OPENAI_API_KEY":"secret"},http_open=lambda *_args,body=_response(response),**_kwargs:_HttpResponse(body),
            context_loader=lambda _parsed:{"recent_turns":[]})
        assert result.observation_facts==()
        assert result.needs_clarification is True
        assert "storage tanks" in result.clarification_question.lower()


def test_fresh_exact_context_allows_natural_afrikaans_short_reply():
    response=_semantic("rootline","water_levels_observed",message_kind="observation",
        observation="Both are full.",observation_facts=[
            {"subject":"storage_tanks","state":"FULL"},{"subject":"reservoir","state":"FULL"}])
    context={"recent_turns":[{"state":"delivered","telegram_message_id":"700",
        "delivery_provider_timestamp":"2026-08-09T07:30:00+00:00","semantic_domain":"rootline",
        "clarification_question":"Storage tanks, reservoir, or both?"}]}
    result=interpret_owner_message({"text":"Albei vol","provider_message_id":"3477",
        "provider_timestamp":"2026-08-09T07:33:06+00:00","reply_to_message_id":"700"},
        environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1","OOM_SAKKIE_LLM_ROUTER_MODEL":"test",
                 "OPENAI_API_KEY":"secret"},http_open=lambda *_args,**_kwargs:_HttpResponse(_response(response)),
        context_loader=lambda _parsed:context)
    assert len(result.observation_facts)==2 and result.needs_clarification is False


def test_active_health_context_can_resolve_afrikaans_semantic_entity():
    context = {"status": "waiting_for_input", "mission_id": "OOM-PIG127",
        "provider_message_id": "3202", "provider_timestamp": "2026-08-03T03:51:20+00:00",
        "preview": {"evaluator": {"identity": {"tag_number": "127"}}}}
    active, ambiguous, _ = _resolve_active_context(
        "Hy het dit nie gemaak nie", [context], "3210",
        provider_timestamp="2026-08-03T18:00:00+00:00", entity_refs=["Vark 127"])
    assert not ambiguous and active["mission_id"] == "OOM-PIG127"


def test_interpreter_receives_bounded_active_context():
    captured = {}
    def opener(request, timeout):
        captured.update(json.loads(request.data.decode()))
        return _HttpResponse(_response(_semantic("herd_health", "welfare_update",
            entity_refs=["Pig 127"], continuation=True, observation="Pig 127 is weak.")))
    parsed = {"text": "Hy is baie swak", "telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": "9", "reply_to_message_id": "8"}
    result = interpret_owner_message(parsed, environ={"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"},
        context_loader=lambda _parsed: {"active_cases": [{"tag": str(i)} for i in range(20)],
                                        "recent_turns": [{"text": str(i)} for i in range(20)]},
        http_open=opener)
    assert result.domain == "herd_health"
    sent = json.loads(captured["messages"][1]["content"])["context"]
    assert len(sent["active_cases"]) == 8 and len(sent["recent_turns"]) == 8


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result",
       return_value={"success": True, "telegram_sends": 0, "telegram_edits": 1})
@patch("modules.oom_sakkie.telegram_gateway.handle_operational_specialist_message")
@patch("modules.oom_sakkie.telegram_gateway.interpret_owner_message")
def test_gateway_attaches_semantic_hint_before_specialist_routing(interpret, operational, _deliver):
    interpret.return_value = SemanticInterpretation(domain="rootline",
        intent="irrigation_shutdown_observed", message_kind="observation",
        entity_refs=("C Camp",), continuation=True,
        observation="C Camp irrigation physically stopped.", confidence=.99)
    operational.return_value = ({"handled": True, "success": True, "status": "working",
        "answer": "ROOTLINE received shutdown evidence", "specialist_identity": "ROOTLINE",
        "mission_id": "OOM-ROOTLINE-1", "writes_farm_data": False}, 200)
    env = {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1", "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "g" * 40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42", "OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL": "test", "OPENAI_API_KEY": "secret"}
    payload = {"message": {"message_id": 3219, "date": 1785790000, "text": "C Camp has stopped",
        "from": {"id": 42}, "chat": {"id": 42, "type": "private"}}}
    with patch.dict("os.environ", env, clear=True), patch(
            "modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",return_value=None):
        result, status = handle_telegram_gateway_message(payload,
            headers={"Authorization": "Bearer " + "g" * 40})
    assert status == 200 and result["message"]["specialist_identity"] == "ROOTLINE"
    routed = operational.call_args.args[0]
    assert routed["semantic"]["intent"] == "irrigation_shutdown_observed"


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result",
       return_value={"success":True,"telegram_sends":1,"telegram_edits":0})
@patch("modules.oom_sakkie.telegram_gateway.interpret_owner_message")
def test_gateway_documents_ambiguity_asks_once_without_print_claim(interpret,deliver):
    interpret.return_value=SemanticInterpretation(domain="documents",
        intent="weekly_weighing_sheet_print",message_kind="request",confidence=.55,
        needs_clarification=True,
        clarification_question="Do you want the weekly weighing sheet printed?")
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"g"*40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42",
        "OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED":"1",
        "OOM_SAKKIE_LLM_ROUTER_MODEL":"test","OPENAI_API_KEY":"secret"}
    payload={"message":{"message_id":3220,"date":1785790001,"text":"Print that one",
        "from":{"id":42},"chat":{"id":42,"type":"private"}}}
    with patch.dict("os.environ",env,clear=True), patch(
            "modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay",
            return_value=None):
        result,status=handle_telegram_gateway_message(payload,
            headers={"Authorization":"Bearer "+"g"*40})
    assert status==200 and result["message"]["status"]==(
        "documents_green_request_clarification_required")
    assert result["message"]["canonical_job_created"] is False
    delivered=deliver.call_args.args[1]
    assert delivered.get("callback_token") is None
    assert delivered["answer"]=="Do you want the weekly weighing sheet printed?"


@patch("modules.oom_sakkie.telegram_gateway.interpret_owner_message",
       side_effect=AssertionError("semantic routing must not precede exact provider replay"))
@patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay")
def test_gateway_exact_provider_replay_precedes_semantic_and_sends_nothing(recover, _interpret):
    recover.return_value={"handled":True,"success":True,
        "status":"contextual_specialist_provider_replay_suppressed",
        "answer":"CH2 remains off","replay_suppressed":True,
        "hardware_commands":0,"provider_control_calls":0,"writes_farm_data":False}
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"g"*40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":3481,"date":1786273205,
        "text":"Done; at fertilizer valves now","from":{"id":42},
        "chat":{"id":42,"type":"private"}}}
    with patch.dict("os.environ",env,clear=True):
        result,status=handle_telegram_gateway_message(payload,
            headers={"Authorization":"Bearer "+"g"*40})
    assert status==200 and result["message"]["replay_suppressed"] is True
    assert result["delivery"]["telegram_sends"]==0 and result["delivery"]["telegram_edits"]==0


@patch("modules.oom_sakkie.telegram_gateway.interpret_owner_message",
       side_effect=AssertionError("delivery recovery must not rerun semantic routing"))
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay")
def test_gateway_resumes_unattempted_contextual_delivery_once(recover, deliver, _interpret):
    recover.return_value={"handled":True,"success":True,"status":"waiting_for_input",
        "answer":"Are you still there?","delivery_recovery_required":True,
        "replay_suppressed":False,"suppress_owner_delivery":False,
        "mission_id":"FERTILIZER-1","card_mission_id":"FERTILIZER-1",
        "specialist_identity":"ROOTLINE","hardware_commands":0,
        "provider_control_calls":0,"writes_farm_data":False}
    deliver.return_value={"success":True,"status":"family_message_card_updated_and_notified",
        "telegram_sends":1,"telegram_edits":1}
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"g"*40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":3486,"date":1786290019,
        "text":"CH2 inching is now on at 300 seconds","from":{"id":42},
        "chat":{"id":42,"type":"private"}}}
    with patch.dict("os.environ",env,clear=True):
        result,status=handle_telegram_gateway_message(payload,
            headers={"Authorization":"Bearer "+"g"*40})
    assert status==200 and result["answer"]=="Are you still there?"
    assert result["delivery"]["telegram_sends"]==1 and result["delivery"]["telegram_edits"]==1
    deliver.assert_called_once()


@patch("modules.oom_sakkie.telegram_gateway.handle_message")
@patch("modules.oom_sakkie.telegram_gateway.interpret_owner_message",return_value=None)
@patch("modules.oom_sakkie.operational_specialist_intake._load_contextual_provider_replay",
       side_effect=RuntimeError("database unavailable"))
def test_gateway_replay_ledger_failure_preserves_new_read_only_route(_loader,_interpret,service):
    service.return_value=({"success":True,"answer":"Read-only answer.","tool_used":"farm_attention_summary",
        "trace_store":{"stored":False}},200)
    env={"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED":"1","OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN":"g"*40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS":"42"}
    payload={"message":{"message_id":9001,"date":1786273205,
        "text":"What is today's farm plan?","from":{"id":42},"chat":{"id":42,"type":"private"}}}
    with patch.dict("os.environ",env,clear=True), patch(
            "modules.oom_sakkie.telegram_gateway.handle_owner_operational_continuation",return_value=({"handled":False},200)), patch(
            "modules.oom_sakkie.telegram_gateway.handle_operational_specialist_message",return_value=({"handled":False},200)), patch(
            "modules.oom_sakkie.telegram_gateway.deliver_family_result",return_value={"success":True,"telegram_sends":1,"telegram_edits":0}):
        result,status=handle_telegram_gateway_message(payload,headers={"Authorization":"Bearer "+"g"*40})
    assert status==200 and result["answer"]=="Read-only answer."


@patch("modules.oom_sakkie.service.classify_intent",
       side_effect=AssertionError("legacy classifier must not run"))
@patch("modules.oom_sakkie.service.route_with_llm",
       side_effect=AssertionError("second router must not reinterpret owner meaning"))
@patch("modules.oom_sakkie.service.get_tool")
@patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
@patch("modules.oom_sakkie.service._write_tool_trace",
       return_value={"stored": False, "status": "test"})
def test_authenticated_owner_semantics_bypass_legacy_irrigation_classifier(
        _trace, _compose, get_tool, _second_router, _legacy):
    tool = get_tool.return_value
    tool.name = "rootline_water_energy_plan"
    tool.risk_level = 0
    tool.handler.return_value = {"success": True, "summary": "Adaptive B/C plan"}
    result, status = handle_message({
        "text": "What is today's irrigation plan for B and C Camps?",
        "channel": "telegram_read_only",
        "semantic_authoritative": True,
        "semantic": _semantic("rootline", "daily_irrigation_plan"),
    })
    assert status == 200
    assert result["tool_used"] == "rootline_water_energy_plan"
    assert result["intent"]["reason"] == "semantic:rootline_read_plan"


@patch("modules.oom_sakkie.service.classify_intent",
       side_effect=AssertionError("legacy classifier must not run"))
@patch("modules.oom_sakkie.service.route_with_llm",
       side_effect=AssertionError("second router must not reinterpret owner meaning"))
@patch("modules.oom_sakkie.service.get_tool")
@patch("modules.oom_sakkie.service.compose_answer_with_llm", return_value=None)
@patch("modules.oom_sakkie.service._write_tool_trace",
       return_value={"stored": False, "status": "test"})
def test_authenticated_direct_sales_question_uses_sales_capability(
        _trace, _compose, get_tool, _second_router, _legacy):
    tool = get_tool.return_value
    tool.name = "sales_dashboard"
    tool.risk_level = 0
    tool.handler.return_value = {"success": True, "summary": "Current sales status"}
    result, status = handle_message({
        "text": "Which sale payments still need attention?",
        "channel": "telegram_read_only",
        "semantic_authoritative": True,
        "semantic": _semantic("sam", "sales_payment_status"),
    })
    assert status == 200
    assert result["tool_used"] == "sales_dashboard"
    assert result["intent"]["reason"] == "semantic:sales_read_status"


@patch("modules.oom_sakkie.service.classify_intent",
       side_effect=AssertionError("legacy classifier must not run"))
@patch("modules.oom_sakkie.service.route_with_llm",
       side_effect=AssertionError("second router must not reinterpret owner meaning"))
def test_authenticated_owner_clarification_never_falls_back_to_keyword_code(
        _second_router, _legacy):
    semantic = _semantic("general", "unclear_followup")
    semantic["needs_clarification"] = True
    semantic["clarification_question"] = "Which animals do you mean?"
    result, status = handle_message({
        "text": "Animals",
        "channel": "telegram_read_only",
        "semantic_authoritative": True,
        "semantic": semantic,
    })
    assert status == 200
    assert result["needs_clarification"] is True
    assert result["tool_used"] == ""


def test_parse_semantic_response_preserves_only_bounded_breeding_actions():
    payload = _semantic("herd_management", "breeding_grouped_facts")
    payload["breeding_actions"] = [
        {"animal_ref":"Ms Piggy","action":"recovery_hold","body_condition_score":2,
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"BCS 2"},
        {"animal_ref":"Linda","action":"near_farrowing",
         "observed_at":"2026-08-12T08:00:00+02:00","factual_note":"Close to farrowing"},
    ]
    result = parse_semantic_response(_response(payload))
    assert len(result.breeding_actions) == 2
    assert result.breeding_actions[0]["animal_ref"] == "Ms Piggy"
    assert result.breeding_actions[0]["body_condition_score"] == 2
    assert result.breeding_actions[1]["action"] == "near_farrowing"
