"""P0 regressions for context-aware authenticated owner conversation."""

from datetime import datetime, timezone
import sys
from unittest.mock import MagicMock, patch
import os

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_runtime import (
    _claim_pending_context, _load_active_contexts, _resolve_active_context,
    handle_authenticated_health_loss_message,
)
from modules.oom_sakkie.owner_conversation_front_door import build_owner_clarification
from modules.oom_sakkie.telegram_gateway import (
    handle_telegram_gateway_message, parse_telegram_gateway_payload,
)
from modules.pig_weights.herdmaster_natural_health_loss_intake import evaluate_health_loss_intake


AUTHORITY = issue_gateway_owner_authority("42", "42")


def _parsed(text, message_id, timestamp):
    return {"text": text, "telegram_user_id": "42", "telegram_chat_id": "42",
            "provider_message_id": message_id, "provider_timestamp": timestamp}


def _pig127_context(**overrides):
    value = {"status": "waiting_for_input",
             "combined_text": "Pig 127 is laying down, not eating or standing up. I think he is not going to make it.",
             "mission_id": "OOM-HERDMASTER-368E7C97C6D82C2416716A19",
             "operation_id": "HERD-HEALTH-89C38F0EC13AF009F8BA574A24A67949",
             "provider_message_id": "3202", "provider_timestamp": "2026-08-03T03:51:20+00:00",
             "card_message_id": "3203", "preview": {"evaluator": {"identity": {
                 "pig_id": "PIG-2026-D13C", "tag_number": "127"}}}}
    value.update(overrides)
    return value


def _evidence():
    return {"evidence_generation": "GEN-PIG127", "as_of_timestamp": "2026-08-03T04:00:00+00:00",
            "animals": [{"pig_id": "PIG-2026-D13C", "name": "", "tag_number": "127",
                         "lifecycle_status": "Active", "on_farm": True,
                         "availability": "Unknown", "pen": "Unknown"}],
            "matings": [], "litters": []}


def _store(initial):
    rows, events = list(initial), []
    def store(action, identity, payload):
        if action == "load":
            return list(rows)
        events.append(payload)
        rows.insert(0, payload)
        return {"success": True, "created": True}
    return store, events


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_exact_3202_3204_3206_sequence_advances_once_without_repeated_question(loader):
    loader.return_value = _evidence()
    store, events = _store([_pig127_context()])
    followup, status = handle_authenticated_health_loss_message(
        _parsed("No, he is not able to do anything. Think he is on his last breathe",
                "3204", "2026-08-03T03:52:13+00:00"), AUTHORITY, context_store=store)
    assert status == 200 and followup["mission_id"] == _pig127_context()["mission_id"]
    assert followup["question_count"] == 1
    assert "breathing now" in followup["answer"]
    assert "able to stand, breathe normally and drink water" not in followup["answer"]
    facts = {row["fact"] for row in events[-1]["preview"]["evaluator"]["observed_facts"]}
    assert {"unable_to_stand", "not_drinking", "unable_to_function_normally",
            "apparently_close_to_death"} <= facts

    clarification, clarification_status = handle_authenticated_health_loss_message(
        _parsed("Pig 127", "3206", "2026-08-03T03:53:23+00:00"),
        AUTHORITY, context_store=store)
    assert clarification_status == 200
    assert clarification["mission_id"] == _pig127_context()["mission_id"]
    assert clarification["suppress_owner_delivery"] is True
    assert clarification["answer"] == ""
    assert events[-1]["provider_message_id"] == "3206"
    assert events[-1]["evidence_provider_message_id"] == "3204"
    assert events[-1]["evidence_provider_timestamp"] == "2026-08-03T03:52:13+00:00"
    assert events[-1]["clarification_text_sha256"]
    event_count = len(events)
    replay_3206, replay_status = handle_authenticated_health_loss_message(
        _parsed("Pig 127", "3206", "2026-08-03T03:53:23+00:00"),
        AUTHORITY, context_store=store)
    assert replay_status == 200 and replay_3206["replay_suppressed"] is True
    assert replay_3206["suppress_owner_delivery"] is True
    assert len(events) == event_count


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_process_restart_replay_of_3204_creates_no_new_preview(loader):
    loader.return_value = _evidence()
    durable = _pig127_context(
        provider_message_id="3204", provider_timestamp="2026-08-03T03:52:13+00:00",
        combined_text=("Pig 127 is laying down, not eating or standing up. "
                       "Follow-up: No, he is not able to do anything. "
                       "Think he is on his last breathe"))
    store, events = _store([durable])
    result, status = handle_authenticated_health_loss_message(
        _parsed("No, he is not able to do anything. Think he is on his last breathe",
                "3204", "2026-08-03T03:52:13+00:00"), AUTHORITY, context_store=store)
    assert status == 200 and result["replay_suppressed"] is True
    assert result["suppress_owner_delivery"] is True
    assert events == []
    loader.assert_not_called()


def test_reply_to_card_outranks_other_active_cases():
    other = _pig127_context(mission_id="OOM-PIG11", operation_id="HERD-PIG11",
                            card_message_id="3199", preview={"evaluator": {"identity": {
                                "pig_id": "PIG-2026-E88A", "tag_number": "11"}}})
    store, _ = _store([other, _pig127_context()])
    with patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence",
               return_value=_evidence()):
        result, status = handle_authenticated_health_loss_message(
            {**_parsed("No, he cannot stand", "3204", "2026-08-03T03:52:13+00:00"),
             "reply_to_message_id": "3203"}, AUTHORITY, context_store=store)
    assert status == 200 and result["mission_id"] == _pig127_context()["mission_id"]


def test_production_loaded_card_binding_resolves_exact_reply_before_recency():
    older_target = _pig127_context(card_message_id="3203")
    newer_other = _pig127_context(mission_id="OOM-PIG11", card_message_id="3199",
        provider_timestamp="2026-08-03T03:52:00+00:00",
        preview={"evaluator": {"identity": {"pig_id": "PIG-11", "tag_number": "11"}}})
    active, ambiguous, _ = _resolve_active_context(
        "No, he cannot stand", [newer_other, older_target], "3204",
        reply_to_message_id="3203", provider_timestamp="2026-08-03T03:52:13+00:00")
    assert ambiguous is False
    assert active["mission_id"] == older_target["mission_id"]


def test_production_loader_projects_delivered_family_card_identity():
    cursor = MagicMock()
    cursor.fetchall.return_value = [(_pig127_context(card_message_id=""),
                                     datetime.now(timezone.utc), "3203")]
    cursor_cm = MagicMock(); cursor_cm.__enter__.return_value = cursor
    connection = MagicMock(); connection.cursor.return_value = cursor_cm
    connection_cm = MagicMock(); connection_cm.__enter__.return_value = connection
    psycopg = MagicMock(); psycopg.connect.return_value = connection_cm
    with patch.dict(os.environ, {"DATABASE_URL": "postgresql://test"}), \
         patch.dict(sys.modules, {"psycopg": psycopg}):
        contexts = _load_active_contexts("42", owner_user_id="42")
    assert contexts[0]["card_message_id"] == "3203"
    sql = cursor.execute.call_args.args[0]
    assert "oom_sakkie_family_message_lifecycle" in sql
    assert "card_mission_id" in sql


def test_negative_welfare_evidence_is_retained_not_reasked_as_unknown():
    result = evaluate_health_loss_intake({"authenticated": True,
        "text": ("Pig 127 is laying down, not eating or standing up. "
                 "No, he is not able to do anything. Think he is on his last breathe"),
        "provider_timestamp": "2026-08-03T03:52:13+00:00",
        "provider_message_id": "3204", "authenticated_principal_id": "42"}, _evidence())
    assert "breathing now" in result["smallest_missing_follow_up_question"]
    assert result["smallest_missing_follow_up_question"].count("?") == 1
    assert result["writes_performed"] is False


def test_owner_front_door_replaces_legacy_v1_fallback_with_one_safe_question():
    result = build_owner_clarification(_parsed("Please check this farm issue", "3210",
                                               "2026-08-03T04:10:00+00:00"))
    assert result["status"] == "owner_context_clarification_required"
    assert result["question_count"] == 1
    assert "first version" not in result["answer"]
    assert not any(result[key] for key in (
        "writes_farm_data", "sends_customers", "publishes", "hardware_commands"))


def test_gateway_preserves_exact_reply_to_card_identity():
    parsed = parse_telegram_gateway_payload({"message": {"message_id": 3204,
        "date": 1785738733, "text": "No, he cannot stand", "from": {"id": 42},
        "chat": {"id": 42, "type": "private"},
        "reply_to_message": {"message_id": 3203}}})
    assert parsed["provider_message_id"] == "3204"
    assert parsed["reply_to_message_id"] == "3203"


def test_bare_entity_without_active_case_does_not_create_health_lifecycle():
    store, events = _store([])
    result, status = handle_authenticated_health_loss_message(
        _parsed("Pig 127", "3206", "2026-08-03T03:53:23+00:00"),
        AUTHORITY, context_store=store)
    assert status == 200 and result["handled"] is False
    assert result["status"] == "health_loss_entity_without_active_context"
    assert events == []


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_ambiguous_urgent_evidence_is_bound_and_consumed_by_later_entity(loader):
    loader.return_value = _evidence()
    pig11 = _pig127_context(mission_id="OOM-PIG11", operation_id="HERD-PIG11",
                            card_message_id="3199", preview={"evaluator": {"identity": {
                                "pig_id": "PIG-2026-E88A", "tag_number": "11"}}})
    store, events = _store([pig11, _pig127_context()])
    urgent = "No, he is not able to do anything. Think he is on his last breathe"
    ambiguous, status = handle_authenticated_health_loss_message(
        _parsed(urgent, "3204", "2026-08-03T03:52:13+00:00"), AUTHORITY,
        context_store=store)
    assert status == 200 and ambiguous["status"] == "health_loss_context_disambiguation_required"
    assert events[-1]["pending_text"] == urgent
    pending_digest = events[-1]["pending_text_sha256"]

    resolved, resolved_status = handle_authenticated_health_loss_message(
        _parsed("Pig 127", "3206", "2026-08-03T03:53:23+00:00"), AUTHORITY,
        context_store=store)
    assert resolved_status == 200 and resolved["mission_id"] == _pig127_context()["mission_id"]
    assert pending_digest
    assert urgent in events[-1]["combined_text"]
    assert events[-1]["provider_message_id"] == "3206"
    assert events[0]["mission_id"] in events[-1]["consumed_context_missions"]
    assert all(row.get("mission_id") != "OOM-PIG11" for row in events[1:])


@patch.dict(os.environ, {"OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
    "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "g" * 40,
    "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42"}, clear=True)
@patch("modules.oom_sakkie.telegram_gateway.handle_operational_specialist_message",
       return_value=({"handled": False}, 200))
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.handle_authenticated_health_loss_message")
def test_gateway_edits_3204_once_but_suppresses_3206_delivery(health, deliver, _operational):
    deliver.return_value = {"success": True, "telegram_sends": 0, "telegram_edits": 1,
                            "telegram_message_id": "3203"}
    health.return_value = ({"handled": True, "success": True, "status": "waiting_for_input",
        "answer": "urgent preview", "mission_id": "OOM-PIG127",
        "card_mission_id": "OOM-PIG127", "writes_farm_data": False}, 200)
    payload = {"message": {"message_id": 3204, "date": 1785738733,
        "text": "No, he cannot stand", "from": {"id": 42},
        "chat": {"id": 42, "type": "private"}}}
    first, first_status = handle_telegram_gateway_message(
        payload, headers={"Authorization": "Bearer " + "g" * 40})
    assert first_status == 200 and first["delivery"]["telegram_edits"] == 1
    assert deliver.call_count == 1
    health.return_value = ({"handled": True, "success": True,
        "status": "health_loss_entity_clarification_retained", "answer": "",
        "mission_id": "OOM-PIG127", "card_mission_id": "OOM-PIG127",
        "suppress_owner_delivery": True, "writes_farm_data": False}, 200)
    payload["message"].update({"message_id": 3206, "date": 1785738803, "text": "Pig 127"})
    second, second_status = handle_telegram_gateway_message(
        payload, headers={"Authorization": "Bearer " + "g" * 40})
    assert second_status == 200
    assert second["delivery"]["telegram_sends"] == 0
    assert second["delivery"]["telegram_edits"] == 0
    assert deliver.call_count == 1


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_ordinary_natural_reply_to_exact_card_binds_before_vocabulary_filter(loader):
    loader.return_value = _evidence()
    store, events = _store([_pig127_context()])
    result, status = handle_authenticated_health_loss_message(
        {**_parsed("He looks worse", "3204", "2026-08-03T03:52:13+00:00"),
         "reply_to_message_id": "3203"}, AUTHORITY, context_store=store)
    assert status == 200 and result["mission_id"] == _pig127_context()["mission_id"]
    assert result["question_count"] <= 1 and len(events) == 1


def test_unmatched_reply_to_does_not_create_health_lifecycle():
    store, events = _store([_pig127_context()])
    result, status = handle_authenticated_health_loss_message(
        {**_parsed("He looks worse", "3204", "2026-08-03T03:52:13+00:00"),
         "reply_to_message_id": "9999"}, AUTHORITY, context_store=store)
    assert status == 200 and result["handled"] is False
    assert result["status"] == "health_loss_reply_without_active_context"
    assert events == []


def test_pending_resolution_must_be_newer_than_retained_evidence():
    pending = {"status": "waiting_for_context", "mission_id": "OOM-PENDING",
        "provider_message_id": "3204", "provider_timestamp": "2026-08-03T03:52:13+00:00",
        "pending_text": "No, he cannot stand", "candidate_bindings": [{
            "mission_id": _pig127_context()["mission_id"], "tag_number": "127"}]}
    store, events = _store([pending, _pig127_context()])
    result, status = handle_authenticated_health_loss_message(
        _parsed("Pig 127", "3206", "2026-08-03T03:52:00+00:00"), AUTHORITY,
        context_store=store)
    assert status == 409
    assert result["status"] == "health_loss_context_resolution_chronology_conflict"
    assert events == []


def test_pending_consume_claim_is_atomic_for_competing_resolutions():
    pending = {"chat_id": "42", "owner_user_id": "42", "status": "waiting_for_context",
        "mission_id": "OOM-PENDING", "provider_message_id": "3204",
        "provider_timestamp": "2026-08-03T03:52:13+00:00",
        "pending_text": "No, he cannot stand"}
    identities = set()
    def claim_store(action, identity, payload):
        if action == "load": return []
        created = identity not in identities
        identities.add(identity)
        return {"success": True, "created": created}
    first = _claim_pending_context(pending, _pig127_context(),
        _parsed("Pig 127", "3206", "2026-08-03T03:53:23+00:00"),
        context_store=claim_store)
    second = _claim_pending_context(pending, _pig127_context(),
        _parsed("Pig 127", "3207", "2026-08-03T03:53:24+00:00"),
        context_store=claim_store)
    assert first is True and second is False and len(identities) == 1


def test_multiple_pending_updates_for_same_tag_remain_typed_ambiguous():
    candidate = {"mission_id": _pig127_context()["mission_id"], "tag_number": "127"}
    pending_a = {"status": "waiting_for_context", "mission_id": "OOM-PENDING-A",
        "provider_message_id": "3204", "provider_timestamp": "2026-08-03T03:52:13+00:00",
        "candidate_bindings": [candidate]}
    pending_b = {**pending_a, "mission_id": "OOM-PENDING-B", "provider_message_id": "3205"}
    store, events = _store([pending_b, pending_a, _pig127_context()])
    result, status = handle_authenticated_health_loss_message(
        _parsed("Pig 127", "3206", "2026-08-03T03:53:23+00:00"), AUTHORITY,
        context_store=store)
    assert status == 200 and result["status"] == "health_loss_pending_context_ambiguous"
    assert result["question_count"] == 1 and events == []


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_exact_pending_card_reply_consumes_only_that_pending_evidence(loader):
    loader.return_value = _evidence()
    candidate = {"mission_id": _pig127_context()["mission_id"], "tag_number": "127"}
    pending_a = {"status": "waiting_for_context", "mission_id": "OOM-PENDING-A",
        "provider_message_id": "3204", "provider_timestamp": "2026-08-03T03:52:13+00:00",
        "pending_text": "No, he cannot stand", "card_message_id": "3300",
        "candidate_bindings": [candidate]}
    pending_b = {**pending_a, "mission_id": "OOM-PENDING-B", "provider_message_id": "3205",
                 "pending_text": "He is not eating", "card_message_id": "3301"}
    store, events = _store([pending_b, pending_a, _pig127_context()])
    result, status = handle_authenticated_health_loss_message(
        {**_parsed("Pig 127", "3206", "2026-08-03T03:53:23+00:00"),
         "reply_to_message_id": "3300"}, AUTHORITY, context_store=store)
    assert status == 200 and result["mission_id"] == _pig127_context()["mission_id"]
    assert "No, he cannot stand" in events[-1]["combined_text"]
    assert "He is not eating" not in events[-1]["combined_text"]
    assert events[-1]["consumed_context_missions"] == ["OOM-PENDING-A"]


def test_non_entity_reply_to_pending_card_cannot_create_health_lifecycle():
    pending = {"status": "waiting_for_context", "mission_id": "OOM-PENDING-A",
        "provider_message_id": "3204", "provider_timestamp": "2026-08-03T03:52:13+00:00",
        "pending_text": "No, he cannot stand", "card_message_id": "3300",
        "candidate_bindings": [{"mission_id": _pig127_context()["mission_id"],
                                "tag_number": "127"}]}
    store, events = _store([pending, _pig127_context()])
    result, status = handle_authenticated_health_loss_message(
        {**_parsed("That one", "3206", "2026-08-03T03:53:23+00:00"),
         "reply_to_message_id": "3300"}, AUTHORITY, context_store=store)
    assert status == 200 and result["status"] == "health_loss_pending_context_ambiguous"
    assert result["question_count"] == 1 and events == []
