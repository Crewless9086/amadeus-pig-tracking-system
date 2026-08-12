from datetime import datetime, timedelta, timezone

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.manager_question_runtime import (
    handle_manager_question_reply, load_active_manager_question,
    semantic_context_with_manager_question)
from modules.oom_sakkie.semantic_front_door import SemanticInterpretation

NOW = datetime(2026, 8, 12, 6, 5, tzinfo=timezone.utc)
OWNER = "5721652188"


def parsed(text="They are eating, drinking and moving normally", *, message="3530",
           reply="3529", at=NOW):
    return {"text": text, "telegram_user_id": OWNER, "telegram_chat_id": OWNER,
            "provider_message_id": message, "provider_timestamp": at.isoformat(),
            "reply_to_message_id": reply}


def question(at=NOW-timedelta(minutes=5)):
    return {"daily_identity": "OOM-DAILY-FARM-MANAGER-2026-08-12",
        "telegram_message_id": "3529", "presented_at": at.isoformat(),
        "question": "Are the surviving littermates eating, drinking and moving normally?",
        "question_binding": {"task_id": "MORTALITY-1",
            "dedupe_key": "herdmaster:mortality-current-assessment", "domain": "herd"}}


def semantic(language="en", *, continuation=True, domain="herd_health"):
    return SemanticInterpretation(domain=domain, intent="group_welfare_follow_up",
        message_kind="observation", continuation=continuation,
        observation="Surviving littermates are eating, drinking and moving normally.",
        language=language, confidence=.98)


def memory():
    rows = {}
    def store(identity, record):
        created = identity not in rows
        if created:
            rows[identity] = record
        return {"success": True, "created": created, "record": rows[identity]}
    store.rows = rows
    return store


def test_exact_reply_binds_group_evidence_and_replay_is_silent():
    store = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    first, status = handle_manager_question_reply(parsed(), authority, semantic(),
        question=question(), event_store=store)
    replay, replay_status = handle_manager_question_reply(parsed(), authority, semantic(),
        question=question(), event_store=store)
    assert status == replay_status == 200
    assert first["status"] == "manager_question_reply_recorded"
    assert first["writes_farm_data"] is False and len(store.rows) == 1
    recorded = next(iter(store.rows.values()))
    assert recorded["dedupe_key"] == "herdmaster:mortality-current-assessment"
    assert "littermates" in recorded["semantic_facts"]["observation"].lower()
    assert replay["status"] == "manager_question_reply_replay_suppressed"
    assert replay["suppress_owner_delivery"] is True and replay["answer"] == ""


def test_afrikaans_non_reply_continuation_binds_same_active_question():
    value, status = handle_manager_question_reply(
        parsed("Hulle eet, drink en beweeg normaal", reply=""),
        issue_gateway_owner_authority(OWNER, OWNER), semantic("af"),
        question=question(), event_store=memory())
    assert status == 200 and value["handled"] is True
    assert value["specialist_identity"] == "HERDMASTER"


def test_unrelated_direct_specialist_request_is_not_stolen_by_manager_question():
    value, status = handle_manager_question_reply(
        parsed("What is today's irrigation plan?", reply=""),
        issue_gateway_owner_authority(OWNER, OWNER),
        semantic(continuation=False, domain="rootline"),
        question=question(), event_store=memory())
    assert status == 200 and value["handled"] is False


def test_unrelated_direct_request_replying_to_plan_card_is_not_stolen():
    value, status = handle_manager_question_reply(
        parsed("What is today's irrigation plan?", reply="3529"),
        issue_gateway_owner_authority(OWNER, OWNER),
        semantic(continuation=False, domain="rootline"),
        question=question(), event_store=memory())
    assert status == 200 and value["handled"] is False


def test_protected_grouped_breeding_update_outranks_active_herd_question():
    direct = SemanticInterpretation(domain="herd_management", intent="breeding_update",
        message_kind="observation", continuation=True,
        breeding_actions=({"action":"exposure","animal_ref":"Sophie","boar_ref":"Bola",
                           "exposure_started_on":"2026-08-12","planned_days":17},),
        protected_preview_required=True, recording_prohibited=True,
        language="en", confidence=.99)
    value, status = handle_manager_question_reply(
        parsed("Sophie was placed with Bola; preview only", reply=""),
        issue_gateway_owner_authority(OWNER, OWNER), direct,
        question=question(), event_store=memory())
    assert status == 200 and value["handled"] is False


def test_stale_or_mismatched_reply_does_not_bind():
    rows = lambda _owner, _chat: [question(NOW-timedelta(days=2))]
    assert load_active_manager_question(parsed(), loader=rows) is None
    assert load_active_manager_question(parsed(reply="9999"),
        loader=lambda _owner, _chat: [question()]) is None


def test_context_places_active_manager_question_before_semantic_classification():
    context = semantic_context_with_manager_question(parsed(),
        base_context_loader=lambda _parsed: {"active_cases": [], "recent_turns": []},
        question=question())
    turn = context["recent_turns"][-1]
    assert turn["telegram_message_id"] == "3529"
    assert turn["clarification_question"].startswith("Are the surviving")


def test_partial_reply_keeps_one_smallest_visible_follow_up():
    partial = SemanticInterpretation(domain="herd_health", intent="group_welfare_follow_up",
        message_kind="observation", continuation=True, observation="They are eating.",
        language="en", confidence=.9, needs_clarification=True,
        clarification_question="Are they also drinking and moving normally?")
    state = memory()
    value, _ = handle_manager_question_reply(parsed("They are eating"),
        issue_gateway_owner_authority(OWNER, OWNER), partial,
        question=question(), event_store=state)
    assert value["status"] == "manager_question_partial_reply_recorded"
    assert value["question_count"] == 1
    assert value["answer"] == "Are they also drinking and moving normally?"
    assert next(iter(state.rows.values()))["status"] == "partial"


def test_partial_facts_are_retained_in_context_and_accumulated_on_completion():
    prior = {"owner_evidence": "They are eating.", "provider_message_id": "3530",
        "provider_timestamp": NOW.isoformat(), "domain": "herd_health",
        "semantic_facts": {"observation": "They are eating.", "observation_facts": []}}
    active = question(); active["partial_replies"] = [prior]
    context = semantic_context_with_manager_question(parsed(message="3531"),
        base_context_loader=lambda _parsed: {"recent_turns": []}, question=active)
    assert context["recent_turns"][-2]["observation"] == "They are eating."
    complete = SemanticInterpretation(domain="herd_health", intent="group_welfare_follow_up",
        message_kind="observation", continuation=True,
        observation="They are drinking and moving normally.", language="en", confidence=.98)
    state = memory()
    value, status = handle_manager_question_reply(parsed(
        "They are drinking and moving normally", message="3531"),
        issue_gateway_owner_authority(OWNER, OWNER), complete,
        question=active, event_store=state)
    record = next(iter(state.rows.values()))
    assert status == 200 and value["status"] == "manager_question_reply_recorded"
    assert record["generation"] == 2
    assert record["accumulated_semantic_facts"]["observations"] == [
        "They are eating.", "They are drinking and moving normally."]


def test_semantic_outage_keeps_question_visible_and_unanswered():
    state = memory()
    value, status = handle_manager_question_reply(parsed("Yes"),
        issue_gateway_owner_authority(OWNER, OWNER), None,
        question=question(), event_store=state)
    assert status == 409 and value["status"] == "manager_question_meaning_unavailable"
    assert value["answer"] == question()["question"] and state.rows == {}


def test_changed_provider_binding_cannot_be_suppressed_as_replay():
    state = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    first, _ = handle_manager_question_reply(parsed(), authority, semantic(),
        question=question(), event_store=state)
    changed, status = handle_manager_question_reply(
        parsed("No, one is not eating", message="3531"), authority, semantic(),
        question=question(), event_store=state)
    assert first["status"] == "manager_question_reply_recorded"
    assert status == 409 and changed["status"] == "manager_question_concurrent_reply_conflict"


def test_reloaded_partial_exact_replay_is_silent_and_does_not_advance_generation():
    partial = SemanticInterpretation(domain="herd_health", intent="group_welfare_follow_up",
        message_kind="observation", continuation=True, observation="They are eating.",
        language="en", confidence=.9, needs_clarification=True,
        clarification_question="Are they also drinking and moving normally?")
    state = memory(); authority = issue_gateway_owner_authority(OWNER, OWNER)
    first, _ = handle_manager_question_reply(parsed("They are eating"), authority, partial,
        question=question(), event_store=state)
    active = question(); active["partial_replies"] = [next(iter(state.rows.values()))]
    replay, status = handle_manager_question_reply(parsed("They are eating"), authority,
        partial, question=active, event_store=state)
    assert first["status"] == "manager_question_partial_reply_recorded"
    assert status == 200 and replay["status"] == "manager_question_reply_replay_suppressed"
    assert replay["suppress_owner_delivery"] is True and len(state.rows) == 1
