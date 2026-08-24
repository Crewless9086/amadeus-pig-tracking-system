from unittest.mock import patch

from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_health_loss_runtime import (
    _health_loss_message,
    _mortality_completion_message,
    _record_lifecycle_event,
    handle_authenticated_health_loss_message,
    load_canonical_health_loss_evidence,
)
from modules.oom_sakkie.telegram_gateway import handle_telegram_gateway_message
from modules.oom_sakkie.family_message_lifecycle import deliver_family_result


def parsed(text, message_id="3169"):
    return {
        "text": text,
        "telegram_user_id": "42",
        "telegram_chat_id": "42",
        "provider_message_id": message_id,
        "provider_timestamp": "2026-08-02T07:07:57+00:00",
    }


def test_all_runtime_status_fragments_follow_recipient_language_and_are_html_safe():
    keys = ("active_context_unavailable", "stale_confirmation", "pending_ambiguous",
            "identity_required", "provider_identity_required", "chronology_conflict",
            "binding_mismatch", "observation_recorded", "recording_contained",
            "completion_recovery", "cancelled", "claim_unavailable")
    english = " ".join(_health_loss_message("en", key) for key in keys)
    afrikaans = " ".join(_health_loss_message("af", key) for key in keys)
    assert "Nothing" in english and "Niks" not in english
    assert "Niks" in afrikaans and "Nothing" not in afrikaans
    completion = _mortality_completion_message({"pig_name": "A<B & C",
        "welfare_case_closed": True, "living_checks_reconciled": 1}, "en")
    assert "A&lt;B &amp; C" in completion and "A<B" not in completion


def evidence():
    return {
        "evidence_generation": "GEN-11",
        "as_of_timestamp": "2026-08-02T07:08:00+00:00",
        "animals": [{
            "pig_id": "PIG-2026-E88A", "name": "", "tag_number": "11",
            "lifecycle_status": "Active", "on_farm": True,
            "availability": "Sale", "pen": "PEN-016",
        }],
        "matings": [],
        "litters": [],
    }


def pig_125_evidence():
    packet = evidence()
    packet["evidence_generation"] = "GEN-125"
    packet["animals"] = [{
        "pig_id": "PIG-2026-125A", "name": "", "tag_number": "125",
        "lifecycle_status": "Active", "on_farm": True,
        "availability": "Herd", "pen": "PEN-125",
    }]
    return packet


def pig_125_active():
    return {
        "status": "waiting_for_input",
        "combined_text": "Pig 125 is found dead in pen. No conclusion on what it might be.",
        "mission_id": "OOM-HERDMASTER-7F3E42E3FD65581696E065D8",
        "operation_id": "HERD-PIG125-INITIAL",
        "provider_message_id": "3179",
        "provider_timestamp": "2026-08-02T14:52:09+00:00",
        "preview": {"evaluator": {"identity": {
            "pig_id": "PIG-2026-125A", "tag_number": "125"}}},
    }


def memory_store(active=None):
    recorded = []

    def store(action, identity, payload):
        if action == "load":
            return active
        recorded.append(payload)
        return {"success": True, "created": True}

    return store, recorded


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.prepare_health_loss_owner_preview")
@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_natural_afrikaans_vark_mortality_without_date_enters_shared_preview(loader, prepare):
    loader.return_value = evidence()
    prepare.return_value = {"question_count": 1, "owner_message": "Een vraag: Op watter datum?",
        "confirmation_binding": {"operation_id": ""}, "evaluator": {"identity": {
            "pig_id": "PIG-2026-125A", "tag_number": "126"}}}
    store, recorded = memory_store()
    message = {**parsed("Vark 126 is dood, ons het hom verwyder en begrawe.", "fresh-anton-126"),
        "output_language": "af"}
    result, status = handle_authenticated_health_loss_message(
        message, issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["handled"] is True
    assert result["status"] == "waiting_for_input"
    assert len(recorded) == 1 and recorded[0]["output_language"] == "af"
    assert recorded[0]["combined_text"].startswith("Vark 126 is dood")


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.prepare_health_loss_owner_preview")
@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_fresh_mortality_preview_uses_generation_bound_visible_card(loader, prepare):
    loader.return_value = evidence()
    prepare.return_value = {"question_count": 0, "owner_message": "Voorskou",
        "confirmation_binding": {"operation_id": "HERD-FRESH", "preview_sha256": "P" * 64},
        "evaluator": {"identity": {"pig_id": "PIG-2026-E88A", "tag_number": "11"}}}
    store, _recorded = memory_store()
    result, status = handle_authenticated_health_loss_message(
        {**parsed("Vark 11 is dood en begrawe", "fresh-card"), "output_language": "af"},
        issue_gateway_owner_authority("42", "42"), context_store=store,
        claim_creator=lambda **_kwargs: {"preview_digest": "a" * 64,
            "callback_token": "FRESH", "action_kind": "mortality"})
    assert status == 200
    assert result["mission_id"].startswith("OOM-HERDMASTER-")
    assert result["card_mission_id"] == result["mission_id"] + ":PROTECTED:" + "A" * 24
    assert result["card_mission_id"] != result["mission_id"]
    prepare.assert_called_once()


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.get_litter_register_rows")
@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.get_mating_overview")
@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.get_pig_master_rows")
def test_canonical_loader_preserves_birth_and_terminal_chronology(pigs, matings, litters):
    pigs.return_value = [{
        "Pig_ID": "PIG-2026-0002", "Pig_Name": "Pig 002", "Tag_Number": "002",
        "Status": "Deceased", "On_Farm": "No", "Purpose": "Unknown",
        "Current_Pen_ID": "", "Date_Of_Birth": "2026-01-10",
        "Exit_Date": "2026-08-12",
    }]
    matings.return_value = []
    litters.return_value = []

    packet = load_canonical_health_loss_evidence()
    animal = packet["animals"][0]
    assert animal["pig_id"] == "PIG-2026-0002"
    assert animal["birth_date"] == "2026-01-10"
    assert animal["lifecycle_effective_date"] == "2026-08-12"
    assert len(packet["evidence_generation"]) == 64


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_synthetic_pig002_explicit_health_path_needs_no_semantic_front_door(loader):
    loader.return_value = {
        "evidence_generation": "SYNTHETIC-GEN-002",
        "as_of_timestamp": "2026-08-13T07:01:01+00:00",
        "animals": [{
            "pig_id": "SYNTHETIC-PIG-002", "name": "Pig 002", "tag_number": "002",
            "lifecycle_status": "Active", "on_farm": True, "availability": "Unknown",
            "pen": "Unknown", "birth_date": "2026-01-10",
            "lifecycle_effective_date": "",
        }],
        "matings": [], "litters": [],
    }
    store, recorded = memory_store()
    inbound = {
        **parsed(
            "Pig 002 is not eating, appears otherwise fine, is lying down and will be monitored.",
            "synthetic-stage2-002",
        ),
        "provider_timestamp": "2026-08-13T07:01:00+00:00",
        "semantic": {},
    }
    result, status = handle_authenticated_health_loss_message(
        inbound, issue_gateway_owner_authority("42", "42"), context_store=store,
    )
    assert status == 200
    assert result["handled"] is True
    assert result["status"] == "waiting_for_input"
    assert result["writes_farm_data"] is False
    assert result["protected_actions_performed"] is False
    assert "able to stand, breathe normally and drink water" in result["answer"]
    assert recorded[0]["semantic_interpretation"] == {}
    assert recorded[0]["preview"]["zero_io"] is True
    assert recorded[0]["preview"]["writes_farm_data"] is False


@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
@patch("modules.oom_sakkie.telegram_gateway.recover_contextual_specialist_replay", return_value=None)
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input", return_value=({"handled": False}, 200))
@patch("modules.oom_sakkie.herdmaster_health_loss_runtime._record_lifecycle_event")
@patch("modules.oom_sakkie.herdmaster_health_loss_runtime._load_active_contexts", return_value=[])
@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_authenticated_gateway_synthetic_health_acceptance_withholds_provider_send(
        loader, _contexts, record, _owner_task, _replay, deliver):
    loader.return_value = {
        "evidence_generation": "SYNTHETIC-GEN-002",
        "as_of_timestamp": "2026-08-13T07:01:01+00:00",
        "animals": [{
            "pig_id": "SYNTHETIC-PIG-002", "name": "Pig 002", "tag_number": "002",
            "lifecycle_status": "Active", "on_farm": True, "availability": "Unknown",
            "pen": "Unknown", "birth_date": "2026-01-10",
            "lifecycle_effective_date": "",
        }],
        "matings": [], "litters": [],
    }
    record.return_value = {"success": True, "created": True}
    deliver.return_value = {
        "success": True, "status": "synthetic_provider_delivery_withheld",
        "telegram_sends": 0, "telegram_edits": 0,
    }
    token = "s" * 40
    env = {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": token,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42",
        "OOM_SAKKIE_TELEGRAM_OWNER_USER_ID": "42",
        # Deliberately omit OOM_SAKKIE_SEMANTIC_FRONT_DOOR_ENABLED.
    }
    payload = {"message": {
        "message_id": "synthetic-stage2-gateway-002", "date": 1786604460,
        "text": "Pig 002 is not eating, appears otherwise fine, is lying down and will be monitored.",
        "from": {"id": 42}, "chat": {"id": 42, "type": "private"},
    }}

    result, status = handle_telegram_gateway_message(
        payload, headers={"Authorization": "Bearer " + token}, environ=env,
    )

    assert status == 200
    assert result["message"]["handled"] is True
    assert result["message"]["writes_farm_data"] is False
    assert result["message"]["protected_actions_performed"] is False
    assert result["sends_telegram"] is False
    assert result["delivery"]["telegram_sends"] == 0
    assert result["delivery"]["telegram_edits"] == 0
    assert "able to stand, breathe normally and drink water" in result["answer"]
    record.assert_called_once()
    assert record.call_args.args[0]["preview"]["zero_io"] is True
    assert record.call_args.args[0]["preview"]["writes_farm_data"] is False
    assert record.call_args.args[0]["semantic_interpretation"] == {}


def test_recovery_identity_distinguishes_corrected_mission_from_prior_misbound_case():
    identities = []

    def store(action, identity, payload):
        identities.append(identity)
        return {"success": True, "created": True}

    base = {
        "chat_id": "42",
        "provider_message_id": "3179",
        "mission_id": "OOM-HERDMASTER-PIG11-WRONG",
    }
    _record_lifecycle_event(base, context_store=store)
    _record_lifecycle_event(
        {**base, "mission_id": "OOM-HERDMASTER-PIG125-CORRECT"},
        context_store=store,
    )
    _record_lifecycle_event(base, context_store=store)

    assert identities[0] != identities[1]
    assert identities[0] == identities[2]


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_pig_11_report_is_acknowledged_and_asks_only_current_welfare_question(loader):
    loader.return_value = evidence()
    store, recorded = memory_store()
    result, status = handle_authenticated_health_loss_message(
        parsed("Pig 11 is not eating, just laying down"),
        issue_gateway_owner_authority("42", "42"),
        context_store=store,
    )
    assert status == 200
    assert result["status"] == "waiting_for_input"
    assert result["tool_used"] == "herdmaster_health_loss_preview"
    assert "HERDMASTER - HEALTH PREVIEW" in result["answer"]
    assert "able to stand, breathe normally and drink water" in result["answer"]
    assert result["writes_farm_data"] is False
    assert recorded[0]["provider_message_id"] == "3169"


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_follow_up_reuses_open_context_without_repeating_known_report(loader):
    loader.return_value = evidence()
    active = {
        "status": "waiting_for_input",
        "combined_text": "Pig 11 is not eating, just laying down",
        "mission_id": "OOM-PIG11",
        "provider_message_id": "3169",
        "provider_timestamp": "2026-08-02T07:00:00+00:00",
    }
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        parsed("She can stand, is breathing normally and is drinking water", "3170"),
        issue_gateway_owner_authority("42", "42"),
        context_store=store,
    )
    assert status == 200
    assert result["status"] == "preview_ready"
    assert result["question_count"] == 0
    assert "HERDMASTER - HEALTH PREVIEW" in result["answer"]
    assert "not eating" in recorded[0]["combined_text"]
    assert "drinking water" in recorded[0]["combined_text"]


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.confirm_health_loss_preview")
def test_exact_natural_confirmation_records_once_and_reuses_card(confirm):
    confirm.return_value=({"success":True,"status":"health_loss_observation_recorded",
                           "writes_farm_data":True,"rows_created":1},201)
    active={"status":"preview_ready","operation_id":"HERD-1","mission_id":"MISSION-1",
            "preview":{"confirmation_ready":True},"provider_timestamp":"2026-08-02T07:00:00+00:00"}
    store,recorded=memory_store(active)
    result,status=handle_authenticated_health_loss_message(
        parsed("CONFIRM HERD-1","3173"),issue_gateway_owner_authority("42","42"),context_store=store)
    assert status==201 and result["status"]=="completed"
    assert result["card_mission_id"]=="MISSION-1" and result["rows_created"]==1
    assert "No diagnosis or treatment" in result["answer"]
    assert recorded[0]["status"]=="completed"


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_unrelated_owner_message_is_not_claimed(loader):
    store, _recorded = memory_store()
    result, status = handle_authenticated_health_loss_message(
        parsed("Reservoir is three quarters"),
        issue_gateway_owner_authority("42", "42"),
        context_store=store,
    )
    assert status == 200
    assert result["handled"] is False
    loader.assert_not_called()


def test_malformed_confirmation_does_not_enter_health_lifecycle():
    def unexpected_store(*_args):
        raise AssertionError("malformed confirmation must not read lifecycle state")

    result, status = handle_authenticated_health_loss_message(
        parsed("CONFIRM maybe HERD-1"),
        issue_gateway_owner_authority("42", "42"),
        context_store=unexpected_store,
    )
    assert status == 200
    assert result["handled"] is False


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_new_found_dead_report_does_not_reuse_another_pigs_active_lifecycle(loader):
    loader.return_value = {**pig_125_evidence(), "as_of_timestamp": "2026-08-02T17:12:00+00:00"}
    active = {"status": "waiting_for_input", "combined_text": "Pig 11 is not eating",
              "mission_id": "OOM-PIG-11", "operation_id": "HERD-11"}
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        parsed("Pig 125 is found dead in the pen.", "3179"),
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["handled"] is True
    assert result["mission_id"] != "OOM-PIG-11"
    assert recorded[0]["provider_message_id"] == "3179"
    assert recorded[0]["combined_text"] == "Pig 125 is found dead in the pen."
    assert recorded[0]["preview"]["writes_farm_data"] is False
    assert "removed from the pen" in result["answer"].lower()


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_explicit_loss_report_with_no_conclusion_cannot_become_active_case_follow_up(loader):
    loader.return_value = pig_125_evidence()
    active = {"status": "waiting_for_input", "combined_text": "Pig 11 is not eating",
              "mission_id": "OOM-PIG-11", "operation_id": "HERD-11"}
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        parsed("Pig 125 is found dead in pen. No conclusion on what it might be.", "3179"),
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["handled"] is True
    assert result["mission_id"] != "OOM-PIG-11"
    assert recorded[0]["combined_text"] == "Pig 125 is found dead in pen. No conclusion on what it might be."
    assert "Pig 11" not in recorded[0]["combined_text"]
    assert recorded[0]["preview"]["writes_farm_data"] is False


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_exact_natural_answer_reenters_existing_pig125_mission_without_repeating_question(loader):
    loader.return_value = {**pig_125_evidence(), "as_of_timestamp": "2026-08-02T17:12:00+00:00"}
    store, recorded = memory_store(pig_125_active())
    result, status = handle_authenticated_health_loss_message(
        {**parsed("Pig 125 was seen alive this morning, but he seemed off. When I went to feed them this evening I found him dead in the pen. I'm going to spray the pens with LAB tomorrow.", "3185"),
         "provider_timestamp": "2026-08-02T17:11:58+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200
    assert result["mission_id"] == "OOM-HERDMASTER-7F3E42E3FD65581696E065D8"
    assert result["question_count"] == 1
    assert "last seen alive" not in result["answer"].lower()
    assert "when was the body found" not in result["answer"].lower()
    assert "removed from the pen" in result["answer"].lower()
    facts = recorded[0]["preview"]["evaluator"]["observed_facts"]
    assert {row["fact"]: row["value"] for row in facts}["last_seen_alive_context_reported"] == "this morning"
    assert {row["fact"]: row["value"] for row in facts}["body_found_time_context_reported"] == "this evening"
    biosecurity = next(row for row in facts if row["fact"] == "future_biosecurity_intention_reported")
    assert biosecurity["value"] == "spray the pens with LAB tomorrow"
    assert biosecurity["classification"] == "unverified_owner_wording_not_canonical_effect"
    assert recorded[0]["combined_text"].startswith(pig_125_active()["combined_text"])


def pig_125_removal_preview():
    return {**pig_125_active(),
        "status": "preview_ready", "provider_message_id": "3188",
        "provider_timestamp": "2026-08-02T18:28:00+00:00",
        "combined_text": ("Pig 125 is found dead in pen. No conclusion on what it might be. "
            "Follow-up: Pig 125 was seen alive this morning, but he seemed off. When I went to feed them this evening I found him dead in the pen. "
            "I'm going to spray the pens with LAB tomorrow. Follow-up: Pig 125 was removed and buried."),
        "operation_id": "HERD-OLD-PREVIEW",
        "owner_text": "old preview",
        "preview": {"question_count": 0, "confirmation_ready": True,
            "confirmation_binding": {"operation_id": "HERD-OLD-PREVIEW", "preview_sha256": "OLD-SHA"},
            "evaluator": {"identity": {"pig_id": "PIG-2026-125A", "tag_number": "125"}}},
    }


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_natural_preview_correction_invalidates_old_identity_and_proposes_deceased(loader):
    loader.return_value = {**pig_125_evidence(), "as_of_timestamp": "2026-08-02T18:34:00+00:00"}
    store, recorded = memory_store(pig_125_removal_preview())
    correction = {**parsed("Don’t record this yet. Pig 125 must be marked as deceased and no longer on the farm. She was found dead today, removed and buried. The exact time of death is unknown.", "3189"),
        "provider_timestamp": "2026-08-02T18:33:22+00:00"}
    result, status = handle_authenticated_health_loss_message(
        correction, issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["status"] == "preview_ready"
    assert result["owner_intent"] == "corrects_preview"
    assert result["operation_id"] != "HERD-OLD-PREVIEW"
    assert result["invalidated_operation_ids"] == ["HERD-OLD-PREVIEW"]
    assert len(recorded) == 2
    assert recorded[0]["status"] == "preview_correction_pending"
    assert recorded[0]["preview_history"][0]["preview"]["confirmation_ready"] is True
    corrected = recorded[1]
    assert corrected["event_phase"] == "preview_corrected"
    effects = {row["area"]: row for row in corrected["preview"]["evaluator"]["canonical_effects"]}
    assert effects["lifecycle"]["action"] == "record_death"
    assert effects["lifecycle"]["facts"]["date"] == "2026-08-02"
    assert effects["lifecycle"]["facts"]["time"] == "Unknown"
    assert effects["lifecycle"]["facts"]["resulting_on_farm"] is False
    assert effects["movement_pen"]["facts"]["current_pen_occupancy"] == "remove animal"
    assert result["question_count"] == 0
    assert result["writes_farm_data"] is False


def test_stale_confirmation_for_invalidated_preview_fails_closed():
    active = {**pig_125_removal_preview(),
        "operation_id": "HERD-NEW-PREVIEW",
        "invalidated_operation_ids": ["HERD-OLD-PREVIEW"]}
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        {**parsed("CONFIRM HERD-OLD-PREVIEW", "3190"),
         "provider_timestamp": "2026-08-02T18:35:00+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 409
    assert result["status"] == "health_loss_stale_confirmation_invalidated"
    assert result["writes_farm_data"] is False
    assert recorded == []


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_repeated_correction_replay_creates_no_new_preview(loader):
    correction = "Pig 125 must be marked as deceased and no longer on the farm."
    active = {**pig_125_removal_preview(), "provider_message_id": "3189",
        "provider_timestamp": "2026-08-02T18:33:22+00:00", "operation_id": "HERD-NEW",
        "correction_digest": __import__("hashlib").sha256(correction.encode()).hexdigest(),
        "owner_intent": "corrects_preview", "invalidated_operation_ids": ["HERD-OLD-PREVIEW"]}
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        {**parsed(correction, "3189"), "provider_timestamp": "2026-08-02T18:33:22+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["operation_id"] == "HERD-NEW"
    assert recorded == []
    loader.assert_not_called()


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_interrupted_correction_resumes_from_durable_pending_state(loader):
    loader.return_value = {**pig_125_evidence(), "as_of_timestamp": "2026-08-02T18:34:00+00:00"}
    correction = "Pig 125 must be marked as deceased and no longer on the farm. She was found dead today, removed and buried."
    pending = {**pig_125_removal_preview(), "status": "preview_correction_pending",
        "provider_message_id": "3189", "provider_timestamp": "2026-08-02T18:33:22+00:00",
        "owner_intent": "corrects_preview",
        "correction_digest": __import__("hashlib").sha256(correction.encode()).hexdigest(),
        "invalidated_operation_ids": ["HERD-OLD-PREVIEW"], "event_phase": "preview_invalidated",
        "preview_history": [{"operation_id": "HERD-OLD-PREVIEW",
            "preview_sha256": "OLD-SHA", "provider_message_id": "3188",
            "status": "invalidated_by_owner_correction", "preview": {"confirmation_ready": True}}]}
    store, recorded = memory_store(pending)
    result, status = handle_authenticated_health_loss_message(
        {**parsed(correction, "3189"), "provider_timestamp": "2026-08-02T18:33:22+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["status"] == "preview_ready"
    assert recorded[-1]["event_phase"] == "preview_corrected"
    assert len(recorded) == 1
    assert len(recorded[0]["preview_history"]) == 1
    assert result["invalidated_operation_ids"] == ["HERD-OLD-PREVIEW"]


def test_unrelated_reservoir_message_cannot_claim_pig125_context():
    store, recorded = memory_store(pig_125_active())
    result, status = handle_authenticated_health_loss_message(
        {**parsed("Reservoir 4/4", "3182"), "provider_timestamp": "2026-08-02T15:54:10+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["handled"] is False
    assert recorded == []


def test_multiple_active_cases_require_animal_identity_for_short_natural_reply():
    second = {**pig_125_active(), "mission_id": "OOM-PIG11", "operation_id": "HERD-PIG11",
              "preview": {"evaluator": {"identity": {"pig_id": "PIG-11", "tag_number": "11"}}}}
    store, recorded = memory_store([pig_125_active(), second])
    result, status = handle_authenticated_health_loss_message(
        {**parsed("Yes, found this evening", "3188"), "provider_timestamp": "2026-08-02T17:20:00+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["status"] == "health_loss_context_disambiguation_required"
    assert result["question_count"] == 1
    assert result["writes_farm_data"] is False and len(recorded) == 1
    assert recorded[0]["status"] == "waiting_for_context"


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_same_inbound_duplicate_mission_is_suppressed_in_favour_of_prior_case(loader):
    loader.return_value = {**pig_125_evidence(), "as_of_timestamp": "2026-08-02T18:11:00+00:00"}
    duplicate = {**pig_125_active(), "mission_id": "OOM-HERDMASTER-DUPLICATE",
                 "provider_message_id": "3185", "provider_timestamp": "2026-08-02T17:11:58+00:00",
                 "combined_text": "Pig 125 was seen alive this morning and found dead this evening"}
    contexts = [duplicate, pig_125_active()]; recorded = []; identities = set()
    def store(action, identity, payload):
        if action == "load": return list(contexts)
        recorded.append(payload)
        if identity in identities: return {"success": True, "created": False}
        identities.add(identity); contexts.insert(0, payload)
        return {"success": True, "created": True}
    result, status = handle_authenticated_health_loss_message(
        {**parsed("Pig 125 was seen alive this morning and found dead this evening", "3185"),
         "provider_timestamp": "2026-08-02T17:11:58+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["mission_id"] == pig_125_active()["mission_id"]
    assert result["superseded_duplicate_missions"] == ["OOM-HERDMASTER-DUPLICATE"]
    assert recorded[0]["mission_id"] == pig_125_active()["mission_id"]
    replay, replay_status = handle_authenticated_health_loss_message(
        {**parsed("Pig 125 was seen alive this morning and found dead this evening", "3185"),
         "provider_timestamp": "2026-08-02T17:11:58+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert replay_status == 200 and replay["mission_id"] == pig_125_active()["mission_id"]
    later, later_status = handle_authenticated_health_loss_message(
        {**parsed("Pig 125 was removed from the pen and buried", "3190"),
         "provider_timestamp": "2026-08-02T18:00:00+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert later_status == 200 and later["mission_id"] == pig_125_active()["mission_id"]
    latest, latest_status = handle_authenticated_health_loss_message(
        {**parsed("Pig 125 was buried safely", "3191"),
         "provider_timestamp": "2026-08-02T18:10:00+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert latest_status == 200 and latest["mission_id"] == pig_125_active()["mission_id"]
    assert latest["superseded_duplicate_missions"] == ["OOM-HERDMASTER-DUPLICATE"]


def test_tagless_removal_reply_selects_only_case_waiting_for_removal_evidence():
    pig125 = {**pig_125_active(), "preview": {"evaluator": {
        "identity": {"pig_id": "PIG-125", "tag_number": "125"},
        "missing_evidence": ["physical removal/disposal evidence"]}}}
    pig11 = {**pig_125_active(), "mission_id": "OOM-PIG11", "provider_message_id": "3174",
             "preview": {"evaluator": {"identity": {"pig_id": "PIG-11", "tag_number": "11"},
                                        "missing_evidence": ["appetite reassessment"]}}}
    store, _ = memory_store([pig125, pig11])
    with patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence",
               return_value={**pig_125_evidence(), "as_of_timestamp": "2026-08-02T18:01:00+00:00"}):
        result, status = handle_authenticated_health_loss_message(
            {**parsed("The body was removed from the pen and buried", "3190"),
             "provider_timestamp": "2026-08-02T18:00:00+00:00"},
            issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["mission_id"] == pig125["mission_id"]
    assert result["writes_farm_data"] is False


def test_stale_follow_up_is_contained_on_original_mission():
    store, recorded = memory_store(pig_125_active())
    result, status = handle_authenticated_health_loss_message(
        {**parsed("Pig 125 was seen alive this morning", "3185"),
         "provider_timestamp": "2026-08-02T13:00:00+00:00"},
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 409 and result["status"] == "health_loss_follow_up_chronology_conflict"
    assert result["mission_id"] == pig_125_active()["mission_id"] and recorded == []


def test_active_context_store_failure_is_visible_containment_not_new_mission():
    def broken_store(*_args): raise RuntimeError("database unavailable")
    result, status = handle_authenticated_health_loss_message(
        parsed("Pig 125 was seen alive this morning", "3185"),
        issue_gateway_owner_authority("42", "42"), context_store=broken_store)
    assert status == 503 and result["status"] == "health_loss_active_context_unavailable"
    assert result["answer"] and result["writes_farm_data"] is False


def test_mismatched_owner_context_cannot_receive_natural_follow_up():
    foreign = {**pig_125_active(), "owner_user_id": "99"}
    store, recorded = memory_store(foreign)
    result, status = handle_authenticated_health_loss_message(
        parsed("Yes, found this evening", "3188"),
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result["handled"] is False and recorded == []


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_reentry_survives_restart_and_replay_creates_no_duplicate_card_or_question(loader):
    loader.return_value = {**pig_125_evidence(), "as_of_timestamp": "2026-08-02T18:01:00+00:00"}
    contexts = [pig_125_active()]
    context_ids = set()
    def context_store(action, identity, payload):
        if action == "load": return list(contexts)
        if identity in context_ids: return {"success": True, "created": False}
        context_ids.add(identity); contexts.insert(0, payload)
        return {"success": True, "created": True}
    mission = pig_125_active()["mission_id"]
    family_events = [{"state": "delivered", "card_mission_id": mission,
                      "telegram_message_id": "3184", "text_sha256": "initial"}]
    family_ids = set()
    def family_store(action, identity, payload):
        if action == "load": return list(family_events)
        if identity in family_ids: return {"success": True, "created": False}
        family_ids.add(identity); family_events.append(payload)
        return {"success": True, "created": True}
    edits = []
    message = {**parsed("Pig 125 was seen alive this morning, but he seemed off. When I went to feed them this evening I found him dead in the pen. I'm going to spray the pens with LAB tomorrow.", "3185"),
               "provider_timestamp": "2026-08-02T17:11:58+00:00"}
    first, status = handle_authenticated_health_loss_message(message,
        issue_gateway_owner_authority("42", "42"), context_store=context_store)
    delivered = deliver_family_result(message, first, specialist="HERDMASTER",
        mission_id=first["mission_id"], card_mission_id=first["card_mission_id"],
        event_store=family_store, sender=lambda *_: (_ for _ in ()).throw(AssertionError("send")),
        editor=lambda chat, card, text: edits.append((chat, card, text)) or {"success": True})
    assert status == 200 and delivered["telegram_sends"] == 0 and delivered["telegram_edits"] == 1
    assert delivered["telegram_message_id"] == "3184" and len(edits) == 1
    replay, replay_status = handle_authenticated_health_loss_message(message,
        issue_gateway_owner_authority("42", "42"), context_store=context_store)
    replay_delivery = deliver_family_result(message, replay, specialist="HERDMASTER",
        mission_id=replay["mission_id"], card_mission_id=replay["card_mission_id"],
        event_store=family_store, sender=lambda *_: (_ for _ in ()).throw(AssertionError("send")),
        editor=lambda *_: (_ for _ in ()).throw(AssertionError("edit")))
    assert replay_status == 200 and replay["mission_id"] == mission
    assert replay_delivery["telegram_sends"] == 0 and replay_delivery["telegram_edits"] == 0
    assert len({row.get("mission_id") for row in contexts}) == 1


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.load_canonical_health_loss_evidence")
def test_rootline_presence_is_not_misclassified_as_pig11_health_follow_up(loader):
    active = {"status": "waiting_for_input", "combined_text": "Pig 11 is not eating",
              "mission_id": "OOM-PIG-11"}
    store, recorded = memory_store(active)
    result, status = handle_authenticated_health_loss_message(
        parsed("I am at the B and C valve area now, can observe both camps, and can intervene immediately for supervised commissioning.", "3181"),
        issue_gateway_owner_authority("42", "42"), context_store=store)
    assert status == 200 and result == {"handled": False, "status": "health_loss_intake_not_applicable"}
    assert recorded == []
    loader.assert_not_called()


@patch("modules.oom_sakkie.telegram_gateway.handle_authenticated_health_loss_message")
@patch("modules.oom_sakkie.telegram_gateway.handle_owner_task_input")
@patch("modules.oom_sakkie.telegram_gateway.deliver_family_result")
def test_existing_gateway_delivers_health_reply_through_backend_once(deliver, owner_task, health):
    deliver.return_value = {"success": True, "status": "family_message_delivered",
                            "telegram_sends": 1, "telegram_edits": 0,
                            "telegram_message_id": "4001"}
    owner_task.return_value = ({"handled": False}, 200)
    health.return_value = ({
        "handled": True, "success": True, "status": "waiting_for_input",
        "answer": "🚨 <b>PIG 11 NEEDS CHECKING</b>",
        "records_audit_trace": True,
    }, 200)
    env = {
        "OOM_SAKKIE_TELEGRAM_GATEWAY_ENABLED": "1",
        "OOM_SAKKIE_TELEGRAM_GATEWAY_TOKEN": "x" * 40,
        "OOM_SAKKIE_TELEGRAM_ALLOWED_USER_IDS": "42",
    }
    payload = {"message": {
        "message_id": 3169, "date": 1785654477,
        "text": "Pig 11 is not eating, just laying down",
        "from": {"id": 42}, "chat": {"id": 42, "type": "private"},
    }}
    result, status = handle_telegram_gateway_message(
        payload, headers={"Authorization": "Bearer " + "x" * 40}, environ=env,
    )
    assert status == 200
    assert result["answer"].startswith("🚨")
    assert result["reply"]["text"] == result["answer"]
    assert result["reply"]["parse_mode"] == "HTML"
    assert result["reply_transport"] == "backend_handles_owner_task_delivery"
    assert result["sends_telegram"] is True
    deliver.assert_called_once()


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.confirm_health_loss_preview")
def test_completed_context_accepts_only_exact_confirmation_replay(confirm):
    confirm.return_value=({"success":True,"status":"health_loss_replayed_withheld",
                           "writes_farm_data":False,"rows_created":0},200)
    active={"status":"completed","operation_id":"HERD-1","mission_id":"MISSION-1",
            "owner_user_id":"42","preview":{"confirmation_ready":True},
            "provider_timestamp":"2026-08-02T07:00:00+00:00"}
    store,recorded=memory_store(active)
    result,status=handle_authenticated_health_loss_message(
        parsed("CONFIRM HERD-1","3174"),issue_gateway_owner_authority("42","42"),context_store=store)
    assert status==200 and result["status"]=="completed" and result["rows_created"]==0
    assert result["mission_id"]=="MISSION-1" and result["card_mission_id"]=="MISSION-1"
    assert len(recorded)==1
    confirm.assert_called_once()

    unrelated,status=handle_authenticated_health_loss_message(
        parsed("yes she can stand","3175"),issue_gateway_owner_authority("42","42"),context_store=store)
    assert status==200 and unrelated["handled"] is False


@patch("modules.oom_sakkie.herdmaster_health_loss_runtime.confirm_health_loss_preview")
def test_mortality_write_success_with_lifecycle_store_failure_is_visible_and_recoverable(confirm):
    active = {**pig_125_removal_preview(), "operation_id": "HERD-DEATH-NEW",
        "owner_user_id": "42", "preview": {"confirmation_ready": True,
            "confirmation_binding": {"operation_id": "HERD-DEATH-NEW"}}}
    confirm.side_effect = [
        ({"success": True, "status": "mortality_lifecycle_recorded",
          "writes_farm_data": True, "rows_created": 1, "operation_id": "HERD-DEATH-NEW"}, 201),
        ({"success": True, "status": "mortality_lifecycle_replayed_withheld",
          "writes_farm_data": False, "rows_created": 0, "operation_id": "HERD-DEATH-NEW"}, 200),
    ]
    def failed_store(action, _identity, _payload):
        if action == "load": return active
        return {"success": False, "created": False}
    message = {**parsed("CONFIRM HERD-DEATH-NEW", "3190"),
        "provider_timestamp": "2026-08-02T18:40:00+00:00"}
    failed, failed_status = handle_authenticated_health_loss_message(
        message, issue_gateway_owner_authority("42", "42"), context_store=failed_store)
    assert failed_status == 503
    assert failed["status"] == "health_loss_completion_persistence_pending"
    assert failed["rows_created"] == 1 and failed["writes_farm_data"] is True
    assert "Do not repeat the farm action" in failed["answer"]
    good_store, recorded = memory_store(active)
    recovered, recovered_status = handle_authenticated_health_loss_message(
        message, issue_gateway_owner_authority("42", "42"), context_store=good_store)
    assert recovered_status == 200 and recovered["status"] == "completed"
    assert recovered["rows_created"] == 0
    assert "DEATH RECORDED" in recovered["answer"] and "no longer available on farm" in recovered["answer"]
    assert recorded[0]["status"] == "completed"
    assert confirm.call_count == 2
