"""Real semantic parser -> specialist -> protected preview, with I/O isolated.

Model responses below are fixtures, not live-model or farm acceptance evidence.
"""
from copy import deepcopy
import json
from unittest.mock import patch

import pytest

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_runtime import handle_authenticated_health_loss_message
from modules.oom_sakkie.semantic_front_door import interpret_owner_message, parse_semantic_response
from modules.pig_weights.herdmaster_health_loss_recording import confirm_health_loss_preview
from modules.pig_weights.herdmaster_mortality_observation import (
    bind_mortality_observation, mortality_observation, validate_mortality_sources,
)

TIME = "2026-08-01T08:30:00+02:00"
ENV = {"OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED": "true",
       "OOM_SAKKIE_LLM_ROUTER_MODEL": "fixture", "OPENAI_API_KEY": "fixture"}
AUTHORITY = issue_gateway_owner_authority("42", "42")


def fact(value, quote):
    return {"value": value, "quote": quote}


def semantic(facts, **extra):
    return {"domain": "herd_health", "intent": "mortality_report",
        "message_kind": "observation", "confidence": .98, "language": "en",
        "mortality_observation": facts, **extra}


def response(value):
    return json.dumps({"choices": [{"message": {"content": json.dumps(value)}}]})


class Response:
    def __init__(self, value): self.value = value
    def __enter__(self): return self
    def __exit__(self, *_): pass
    def read(self): return response(self.value).encode()


def evidence():
    return {"evidence_generation": "GEN-93", "as_of_timestamp": "2026-08-02T12:00:00+02:00",
        "animals": [{"pig_id": "PIG-2026-0093", "tag_number": "93", "name": "",
            "lifecycle_status": "Active", "on_farm": True, "availability": "Herd", "pen": "P1"}],
        "animal_evidence_generations": {"PIG-2026-0093": "PIG-GEN-93"},
        "matings": [], "litters": []}


class Journey:
    def __init__(self):
        self.history, self.claims, self.requests = [], [], []

    def store(self, action, _identity, payload):
        if action == "load":
            return [self.history[-1]] if self.history else []
        self.history.append(deepcopy(payload))
        return {"success": True, "created": True}

    def claim(self, **kwargs):
        self.claims.append(kwargs)
        from modules.oom_sakkie.protected_action_claims import canonical_preview_digest
        return {"preview_digest": canonical_preview_digest("mortality", kwargs["preview_payload"]),
                "callback_token": "FIXTURE", "action_kind": "mortality"}

    def turn(self, text, meaning, message_id="101", timestamp=TIME, **extra):
        parsed = {"text": text, "telegram_user_id": "42", "telegram_chat_id": "42",
            "provider_message_id": message_id, "provider_timestamp": timestamp, **extra}
        def opened(request, **_):
            self.requests.append(json.loads(request.data))
            return Response(meaning)
        # Isolate paid/network I/O while exercising the actual prompt and parser.
        with patch("modules.oom_sakkie.semantic_front_door.budgeted_urlopen", opened):
            interpreted = interpret_owner_message(parsed, environ=ENV,
                context_loader=lambda _: {"active_cases": [{"tag": "93"}] if self.history else []})
        assert interpreted is not None
        parsed["semantic"] = interpreted.as_hint()
        with patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence", return_value=evidence()):
            return handle_authenticated_health_loss_message(parsed, AUTHORITY,
                context_store=self.store, claim_creator=self.claim)


def initial(text, date_words=None, day="2026-07-31"):
    value = {"animal": fact("93", "93"), "death": fact("dead", text)}
    if date_words:
        value["date"] = fact(day, date_words)
    return semantic(value)


@pytest.mark.parametrize("text,words,day", [
    ("Pig 93 died one day ago.", "one day ago", "2026-07-31"),
    ("Pig 93 died on the thirty-first of July.", "the thirty-first of July", "2026-07-31"),
    ("We lost pig 93 the previous evening.", "the previous evening", "2026-07-31"),
    ("Vark 93 het die vorige aand gevrek.", "die vorige aand", "2026-07-31"),
    ("Pig 93 passed away on July 31. We buried him today.", "July 31", "2026-07-31"),
])
def test_equivalent_meanings_reach_same_protected_preview(text, words, day):
    journey = Journey()
    result, status = journey.turn(text, initial(text, words, day))
    assert status == 200 and result["status"] == "preview_ready"
    lifecycle = journey.history[-1]
    assert lifecycle["preview"]["evaluator"]["preview"]["event_date"] == day
    assert result["writes_farm_data"] is False
    assert "reply_markup" in result
    assert result["question_count"] == 0
    assert len(journey.claims) == 1
    user = json.loads(journey.requests[0]["messages"][1]["content"])
    assert user["provider_timestamp"] == TIME
    assert user["provider_timezone"] == "Africa/Johannesburg"
    assert "Semantic interpretation" not in lifecycle["combined_text"]


def test_short_date_reply_retains_case_original_fact_and_source_time():
    journey = Journey()
    first, status = journey.turn("We lost pig 93.", initial("We lost pig 93."))
    assert status == 200 and first["status"] == "waiting_for_input"
    assert not journey.claims
    # No death keyword, animal ID, regex date or conversational prose restatement.
    result, status = journey.turn("The thirty-first of July", semantic({
        "date": fact("2026-07-31", "The thirty-first of July")}, continuation=True),
        "102", "2026-08-02T08:30:00+02:00")
    assert status == 200 and result["status"] == "preview_ready"
    assert result["mission_id"] == first["mission_id"]
    retained = journey.history[-1]["semantic_interpretation"]["mortality_observation"]
    assert retained["death"]["provider_message_id"] == "101"
    assert retained["death"]["provider_timestamp"] == TIME
    assert retained["date"]["provider_message_id"] == "102"
    assert journey.history[-1]["preview"]["evaluator"]["preview"]["event_date"] == "2026-07-31"


def test_correction_replaces_date_invalidates_previous_preview_and_replays_once():
    journey = Journey()
    first, _ = journey.turn("We lost pig 93 yesterday.", initial("We lost pig 93 yesterday.", "yesterday"))
    correction = semantic({"date": fact("2026-07-30", "two days before that")},
        continuation=True, message_kind="correction")
    result, status = journey.turn("It happened two days before that", correction,
        "102", "2026-08-02T08:30:00+02:00")
    assert status == 200 and result["status"] == "preview_ready"
    assert result["operation_id"] != first["operation_id"]
    assert first["operation_id"] in result["invalidated_operation_ids"]
    assert journey.history[-1]["preview"]["evaluator"]["preview"]["event_date"] == "2026-07-30"
    assert result["mission_id"] == first["mission_id"]
    before = len(journey.history)
    replay, status = journey.turn("It happened two days before that", correction,
        "102", "2026-08-02T08:30:00+02:00")
    assert status == 200 and replay["operation_id"] == result["operation_id"]
    assert len(journey.history) == before
    stale, status = handle_authenticated_health_loss_message({
        "text": "CONFIRM " + first["operation_id"], "provider_message_id": "103",
        "provider_timestamp": "2026-08-02T08:31:00+02:00", "telegram_user_id": "42",
        "telegram_chat_id": "42"}, AUTHORITY, context_store=journey.store)
    assert status == 409 and stale["status"] == "health_loss_stale_confirmation_invalidated"
    assert not stale["writes_farm_data"]


@pytest.mark.parametrize("fact_name,new_fact,text", [
    ("date", fact(None, "I cannot say which day"), "I cannot say which day"),
    ("death", fact("unknown", "I am not sure he is dead"), "I am not sure he is dead"),
])
def test_uncertainty_or_negation_cannot_resurrect_old_positive_fact(fact_name, new_fact, text):
    journey = Journey()
    first, _ = journey.turn("We lost pig 93 yesterday.", initial("We lost pig 93 yesterday.", "yesterday"))
    result, status = journey.turn(text, semantic({fact_name: new_fact},
        continuation=True, message_kind="correction"), "102", "2026-08-02T08:30:00+02:00")
    assert status == 200 and result["status"] == "waiting_for_input"
    assert first["operation_id"] in result["invalidated_operation_ids"]
    assert "reply_markup" not in result
    assert journey.history[-1]["preview"]["evaluator"]["canonical_effects"] == []


def test_facts_never_satisfy_confirmation_and_cancellation_is_not_a_phrase_list():
    journey = Journey()
    first, _ = journey.turn("We lost pig 93 yesterday.", initial("We lost pig 93 yesterday.", "yesterday"))
    lifecycle = journey.history[-1]
    recorded, status = confirm_health_loss_preview(lifecycle, "Yes, he died", actor_id="42",
        evidence_loader=lambda: pytest.fail("must not read for an unbound confirmation"))
    assert status == 409 and recorded["status"] == "exact_preview_confirmation_required"
    result, status = journey.turn("Please leave the records as they are", semantic(None,
        message_kind="command", continuation=True, recording_prohibited=True),
        "102", "2026-08-02T08:30:00+02:00")
    assert status == 200 and result["status"] == "contained"
    assert result["writes_farm_data"] is False
    assert first["operation_id"] in journey.history[-1]["invalidated_operation_ids"]


@pytest.mark.parametrize("text,meaning", [
    ("We lost pig 93.", initial("We lost pig 93.", "yesterday")),
    ("Pig 93 died yesterday.", semantic({"date": fact("2026-07-31", "yesterday")}, confidence=.4)),
])
def test_unbound_or_low_confidence_meaning_cannot_fall_back_to_a_preview(text, meaning):
    journey = Journey()
    result, status = journey.turn(text, meaning)
    assert status == 409 and result["status"] == "health_loss_semantic_evidence_unproven"
    assert not journey.claims and not journey.history


@pytest.mark.parametrize("day", ["2026-02-30", "tomorrow", True, "26-07-31"])
def test_invalid_calendar_values_are_rejected(day):
    assert parse_semantic_response(response(semantic({"date": fact(day, "yesterday")}))) is None


def test_tampered_or_foreign_source_is_rejected_before_evaluation():
    facts = bind_mortality_observation({"date": fact("2026-07-31", "yesterday")},
        text="Pig 93 died yesterday", provider_message_id="101", provider_timestamp=TIME)
    report = {"text": "Pig 93 died yesterday", "provider_message_id": "102", "provider_timestamp": TIME}
    with pytest.raises(ValueError, match="source_binding"):
        validate_mortality_sources(facts, report)
    with pytest.raises(ValueError):
        mortality_observation({"date": {**fact("2026-07-31", "yesterday"), "provider_message_id": "101"}})


def test_explicit_future_date_is_not_silently_corrected():
    journey = Journey()
    result, status = journey.turn("Pig 93 died tomorrow", initial("Pig 93 died tomorrow", "tomorrow", "2026-08-02"))
    assert status == 200 and result["status"] == "waiting_for_input"
    assert journey.history[-1]["preview"]["evaluator"]["status"] == "chronology_conflict"
    assert not journey.claims


def test_alive_correction_cancels_death_preview_without_reasking_the_answered_fact():
    journey = Journey()
    first, _ = journey.turn("We lost pig 93 yesterday.", initial("We lost pig 93 yesterday.", "yesterday"))
    result, status = journey.turn("He's actually alive", semantic({
        "death": fact("alive", "He's actually alive")}, continuation=True,
        message_kind="correction"), "102", "2026-08-02T08:30:00+02:00")
    assert status == 200 and result["status"] == "contained"
    assert "?" not in result["answer"] and "reply_markup" not in result
    assert first["operation_id"] in journey.history[-1]["invalidated_operation_ids"]
    assert journey.history[-1]["semantic_interpretation"]["mortality_observation"]["death"]["value"] == "alive"
    assert result["writes_farm_data"] is False


def test_unthreaded_semantic_reply_does_not_guess_between_two_cases():
    from modules.oom_sakkie.herdmaster_health_loss_runtime import _resolve_active_context
    contexts = [{"status": "waiting_for_input", "mission_id": "CASE-" + tag,
        "provider_message_id": "10" + tag, "provider_timestamp": TIME,
        "preview": {"evaluator": {"identity": {"tag_number": tag}}}} for tag in ("93", "94")]
    active, ambiguous, _ = _resolve_active_context("The previous evening", contexts,
        "103", provider_timestamp="2026-08-02T08:30:00+02:00", semantic_continuation=True)
    assert active is None and len(ambiguous) == 2


def test_reply_card_cannot_move_another_animals_facts_into_the_current_case():
    journey = Journey()
    journey.turn("We lost pig 93 yesterday.", initial("We lost pig 93 yesterday.", "yesterday"))
    journey.history[-1]["card_message_id"] = "CARD-93"
    count = len(journey.history)
    result, status = journey.turn("Pig 94 died yesterday", semantic({
        "animal": fact("94", "Pig 94"), "death": fact("dead", "died"),
        "date": fact("2026-08-01", "yesterday")}, continuation=True),
        "102", "2026-08-02T08:30:00+02:00", reply_to_message_id="CARD-93")
    assert status == 409 and result["status"] == "health_loss_semantic_context_identity_conflict"
    assert len(journey.history) == count


def test_manager_question_partial_meaning_survives_into_the_real_health_preview():
    from datetime import datetime, timedelta
    from modules.oom_sakkie.manager_question_runtime import handle_manager_question_reply
    from tests.test_oom_sakkie_manager_question_runtime import memory
    now = datetime.fromisoformat(TIME)
    question = {"daily_identity": "SYNTHETIC-DAY", "telegram_message_id": "QUESTION",
        "presented_at": (now-timedelta(minutes=5)).isoformat(),
        "question": "What happened to Pig 93?", "question_binding": {
            "task_id": "SYNTHETIC-93", "dedupe_key": "herdmaster:PIG-2026-0093",
            "domain": "herd_health", "pig_id": "PIG-2026-0093"}}
    rows = memory()
    message = {"telegram_user_id": "42", "telegram_chat_id": "42",
        "provider_message_id": "101", "provider_timestamp": TIME,
        "reply_to_message_id": "QUESTION", "text": "We lost pig 93."}
    first_meaning = initial(message["text"])
    first_meaning.update(continuation=True, needs_clarification=True,
                         clarification_question="On which day did it happen?")
    meaning = parse_semantic_response(response(first_meaning))
    result, status = handle_manager_question_reply(message, AUTHORITY, meaning,
        question=question, event_store=rows)
    assert status == 200 and result["question_count"] == 1
    question["partial_replies"] = list(rows.rows.values())
    second = {**message, "provider_message_id": "102", "text": "The previous day",
        "provider_timestamp": (now+timedelta(minutes=1)).isoformat()}
    meaning = parse_semantic_response(response(semantic({
        "date": fact("2026-07-31", "The previous day")}, continuation=True)))
    journey = Journey()
    def specialist(forwarded, authority):
        return handle_authenticated_health_loss_message(forwarded, authority,
            context_store=journey.store, claim_creator=journey.claim)
    with patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence", return_value=evidence()):
        result, status = handle_manager_question_reply(second, AUTHORITY, meaning,
            question=question, event_store=rows, health_handler=specialist)
    assert status == 200 and result["status"] == "preview_ready", result
    retained = journey.history[-1]["semantic_interpretation"]["mortality_observation"]
    assert retained["death"]["provider_message_id"] == "101"
    assert retained["date"]["provider_message_id"] == "102"
    assert journey.history[-1]["preview"]["evaluator"]["preview"]["event_date"] == "2026-07-31"
    assert result["writes_farm_data"] is False


def test_authenticated_telegram_gateway_delivers_the_semantic_preview_and_buttons():
    from modules.oom_sakkie import herdmaster_health_loss_runtime as health
    from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
    journey = Journey()
    text = "We lost pig 93 one day ago."
    meaning = initial(text, "one day ago")
    env = {**ENV, "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "g" * 40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42", "DATABASE_URL": "",
        "PYTHON_DOTENV_DISABLED": "1"}
    from datetime import datetime
    payload = {"message": {"message_id": 101, "date": int(datetime.fromisoformat(TIME).timestamp()),
        "text": text, "from": {"id": 42}, "chat": {"id": 42, "type": "private"}}}
    real_protected = health._protected_preview_fields
    def protected(lifecycle, **_):
        return real_protected(lifecycle, claim_creator=journey.claim)
    with patch.dict("os.environ", env, clear=True), patch(
            "modules.oom_sakkie.semantic_front_door.budgeted_urlopen", return_value=Response(meaning)), patch(
            "modules.oom_sakkie.semantic_front_door.load_bounded_owner_context", return_value={}), patch(
            "modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay", return_value=None), patch(
            "modules.oom_sakkie.telegram_gateway.load_active_manager_question", return_value=None), patch(
            "modules.oom_sakkie.herdmaster_health_loss_runtime._load_active_contexts", return_value=[]), patch(
            "modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence", return_value=evidence()), patch(
            "modules.oom_sakkie.herdmaster_health_loss_runtime._record_lifecycle_event",
            side_effect=lambda value, **_: journey.store("record", None, value)), patch(
            "modules.oom_sakkie.herdmaster_health_loss_runtime._protected_preview_fields", side_effect=protected), patch(
            "modules.oom_sakkie.telegram_gateway._bind_protected_preview_card", side_effect=lambda result, delivery: delivery), patch(
            "modules.oom_sakkie.telegram_gateway.deliver_family_result",
            return_value={"success": True, "telegram_sends": 1, "telegram_message_id": "201"}) as delivery:
        result, status = handle_telegram_gateway_message(payload, headers={"Authorization": "Bearer " + "g" * 40})
    assert status == 200 and result["message"]["status"] == "preview_ready", result
    assert result["sends_telegram"] is True
    delivered = delivery.call_args.args[1]
    assert "2026-07-31" in delivered["answer"]
    buttons = delivered["reply_markup"]["inline_keyboard"][0]
    assert [button["callback_data"].rsplit(":", 1)[-1] for button in buttons] == ["confirm", "change", "cancel"]
    assert result["message"]["writes_farm_data"] is False


def test_death_supersedes_earlier_living_checks_without_requesting_them_again():
    journey = Journey()
    journey.history.append({"mission_id": "EXISTING-WELFARE", "owner_user_id": "42", "chat_id": "42",
        "provider_message_id": "100", "provider_timestamp": "2026-07-31T08:30:00+02:00",
        "status": "waiting_for_input", "combined_text": "Pig 93 is not eating or drinking.",
        "owner_text_verbatim": "Pig 93 is not eating or drinking.",
        "preview": {"evaluator": {"identity": {"resolved": True,
            "pig_id": "PIG-2026-0093", "tag_number": "93"}}},
        "semantic_interpretation": {"welfare_observation": {"eating": "no", "breathing": "unknown"}}})
    text = "We lost pig 93 one day ago."
    result, status = journey.turn(text, initial(text, "one day ago"))
    assert status == 200 and result["status"] == "preview_ready", result
    assert result["mission_id"] == "EXISTING-WELFARE"
    evaluated = journey.history[-1]["preview"]["evaluator"]
    assert evaluated["event_family"] == "found_dead"
    assert evaluated["smallest_missing_follow_up_question"] == ""
    assert "medical_observation" not in {row["area"] for row in evaluated["canonical_effects"]}
