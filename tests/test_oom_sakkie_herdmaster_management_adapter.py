from copy import deepcopy
from datetime import datetime, timedelta, timezone

from modules.oom_sakkie.farm_manager_loop import build_family_brief
from modules.oom_sakkie.gateway_authority import issue_gateway_owner_authority
from modules.oom_sakkie.herdmaster_management_adapter import (
    consume_herdmaster_management_round,
    issue_scheduled_manager_context,
)


NOW = datetime(2026, 8, 2, 14, 0, tzinfo=timezone.utc)
OWNER = "42"


def task(pig_id, tag, mating_date, group="pregnancy check due"):
    return {
        "task_id": f"TASK-{pig_id}", "pig_id": pig_id, "tag_number": tag,
        "task_group": group, "why": "Current reproductive status needs proportional management.",
        "delay_consequence": "Preparation or reassessment could be delayed.",
        "known_evidence": {
            "latest_weight_kg": 100, "latest_weight_date": "2026-07-20",
            "state": "Pregnancy evidence pending", "current_mating_id": f"MAT-{pig_id}",
            "current_mating_date": mating_date,
        },
        "required_checks": ["current reproductive-status observation"],
        "provisional_recommendation": "Reassess current reproductive status",
        "completed": False, "writes_performed": False,
        "evidence_digest": f"DIGEST-{pig_id}",
    }


def canonical(generated_at=NOW):
    return {
        "success": True, "writes_performed": False,
        "generated_at": generated_at.isoformat(), "worklist_id": "HERD-WEEK-20260802",
        "tasks": [
            task("PIG-2026-E88A", "11", "2026-05-01", "herd welfare follow-up"),
            task("PIG-2026-D050", "Mona", "2026-05-02"),
            task("PIG-2026-21BE", "Mysikind", "2026-05-02"),
            task("PIG-2026-7DAA", "Baby", "2026-05-19"),
        ],
    }


def observations():
    rows = []
    for pig_id, result, mating_date, signs in (
        ("PIG-2026-D050", "Assumed Pregnant", "2026-05-02", "belly dropping and teat development"),
        ("PIG-2026-21BE", "Assumed Pregnant", "2026-05-02", "belly dropping and teat development"),
        ("PIG-2026-7DAA", "Inconclusive", "2026-05-19", "visual inspection inconclusive"),
    ):
        rows.append({
            "pig_id": pig_id, "operational_result": result, "observed_signs": signs,
            "mating_id": f"MAT-{pig_id}", "mating_date": mating_date,
            "observed_at": "2026-08-01T13:30:00+02:00",
            "source_identity": f"TELEGRAM-{pig_id}", "canonical_task_id": f"TASK-{pig_id}",
            "specialist_ownership": "HERDMASTER",
            "reassessment_trigger": "New attributable current-cycle observation",
            "decision_that_could_change": "Current reproductive preparation",
        })
    return rows


def active():
    return [{
        "pig_id": "PIG-2026-E88A", "lifecycle_id": "OOM-HERDMASTER-CE45B85C51356B77E087B099",
        "state": "preview_ready", "card_message_id": "3171",
    }]


def consume(**changes):
    values = {
        "authority": issue_gateway_owner_authority(OWNER, OWNER),
        "expected_owner_user_id": OWNER, "canonical_round": canonical(),
        "invocation_at": NOW, "attributable_owner_observations": observations(),
        "active_lifecycles": active(),
        "trusted_now": NOW,
    }
    values.update(changes)
    return consume_herdmaster_management_round(**values)


def test_authenticated_consumption_produces_three_internal_manager_actions():
    result = consume()
    assert result["success"] is True
    assert result["status"] == "herdmaster_management_round_consumed"
    assert result["accepted_work_item_count"] == 3
    specialist = result["specialist_result"]
    assert len(specialist.work_items) == 3
    text = "\n".join(item.title + " " + item.next_action for item in specialist.work_items)
    assert "Mona: Assumed Pregnant" in text
    assert "Mysikind: Assumed Pregnant" in text
    assert "Baby: Inconclusive" in text
    assert "2026-08-22 to 2026-08-26" in text
    assert "2026-08-08 to 2026-08-15" in text
    assert "scanning remains optional" in text
    assert "PIG-2026-E88A" not in text
    assert result["sends_telegram"] is False and result["writes_farm_data"] is False


def test_scheduled_manager_context_is_authenticated_and_bound():
    context = issue_scheduled_manager_context(OWNER, "OOM-DAILY-20260802", NOW)
    result = consume(authority=context)
    assert result["success"] is True
    assert result["binding"]["invocation_timestamp"] == NOW.isoformat()
    assert result["binding"]["invocation_context"]["type"] == "scheduled_manager"
    assert len(result["binding"]["invocation_context"]["mission_identity_sha256"]) == 64
    assert result["binding"]["specialist_contract_version"] == "herdmaster_proactive_management_round_v1"


def test_anonymous_or_mismatched_owner_is_denied_with_one_typed_exception():
    anonymous = consume(authority=None)
    mismatch = consume(authority=issue_gateway_owner_authority("99", "99"))
    for result in (anonymous, mismatch):
        assert result["status"] == "herdmaster_management_round_contained"
        assert result["systemic_exception"]["reason"] == "authenticated_manager_context_denied"
        assert result["accepted_work_item_count"] == 0
        assert result["creates_owner_card"] is False


def test_stale_evidence_generation_fails_closed_only_on_herdmaster_result():
    result = consume(canonical_round=canonical(NOW - timedelta(hours=25)))
    assert result["systemic_exception"]["reason"] == "herdmaster_evidence_generation_stale"
    brief = build_family_brief([result["specialist_result"]], now=NOW)
    assert brief.specialist_gaps == {"herdmaster": "contained"}


def test_changed_management_round_digest_is_contained():
    first = consume()
    binding = first["binding"]
    prior = [{
        "management_round_identity": binding["management_round_identity"],
        "deduplication_key": binding["deduplication_key"],
        "result_digest": "0" * 64,
        "evidence_generation": binding["evidence_generation"],
        "active_case_digest": binding["active_case_deduplication_state"]["digest"],
        "invocation_context_digest": binding["invocation_context"]["digest"],
    }]
    changed = consume(prior_consumptions=prior)
    assert changed["systemic_exception"]["reason"] == "herdmaster_management_round_binding_changed"


def test_exact_replay_creates_no_packet_card_question_or_work_item():
    first = consume()
    binding = first["binding"]
    prior = [{
        "management_round_identity": binding["management_round_identity"],
        "deduplication_key": binding["deduplication_key"],
        "result_digest": binding["result_digest"],
        "evidence_generation": binding["evidence_generation"],
        "active_case_digest": binding["active_case_deduplication_state"]["digest"],
        "invocation_context_digest": binding["invocation_context"]["digest"],
    }]
    replay = consume(prior_consumptions=prior)
    assert replay["status"] == "herdmaster_management_round_replay_suppressed"
    assert replay["specialist_result"] is None
    assert replay["accepted_work_item_count"] == 0
    assert replay["creates_owner_card"] is replay["creates_owner_question"] is False


def test_unavailable_or_malformed_specialist_fails_closed_without_authority():
    unavailable = consume(specialist_builder=None)
    malformed = consume(specialist_builder=lambda *_args, **_kwargs: {"success": True})
    raised = consume(specialist_builder=lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("offline")))
    assert unavailable["systemic_exception"]["reason"] == "herdmaster_specialist_unavailable"
    assert malformed["systemic_exception"]["reason"] == "herdmaster_management_round_malformed"
    assert raised["systemic_exception"]["reason"] == "herdmaster_management_round_malformed"
    for result in (unavailable, malformed, raised):
        assert result["sends_telegram"] is False
        assert result["writes_farm_data"] is False
        assert result["protected_actions_performed"] is False


def test_oom_sakkie_consolidates_specialist_actions_without_duplication():
    result = consume()
    brief = build_family_brief([result["specialist_result"]], now=NOW)
    assert len(brief.queue) == 3
    assert len({item.dedupe_key for item in brief.queue}) == 3
    assert all(item.provenance.specialist == "herdmaster" for item in brief.queue)
    assert all(item.assignee == "dad" for item in brief.queue)
    assert sum(len(value) for value in brief.questions.values()) <= 1
    assert brief.writes_performed == 0


def test_active_pig11_suppression_is_bound_and_does_not_depend_on_output_copy():
    result = consume()
    state = result["binding"]["active_case_deduplication_state"]
    assert state["active_pig_ids"] == ("PIG-2026-E88A",)
    assert len(state["digest"]) == 64
    assert all("PIG-2026-E88A" not in item.item_id for item in result["specialist_result"].work_items)


def test_adapter_never_inherits_specialist_delivery_or_farm_authority():
    def lying_builder(*args, **kwargs):
        from modules.pig_weights.herdmaster_management_round import build_management_round
        value = deepcopy(build_management_round(*args, **kwargs))
        value["sends_telegram"] = True
        return value
    result = consume(specialist_builder=lying_builder)
    assert result["systemic_exception"]["reason"] == "herdmaster_management_round_malformed"
    assert result["sends_telegram"] is False
    assert result["writes_mating"] is result["writes_pregnancy"] is False


def test_adapter_rejects_every_specialist_authority_escalation():
    authority_escalations = {
        "zero_io": False,
        "directly_messages_owner": True,
        "creates_mating": True,
        "changes_lifecycle": True,
        "changes_availability": True,
        "publication_execution_authority": True,
    }
    for field, escalated_value in authority_escalations.items():
        def lying_builder(*args, _field=field, _value=escalated_value, **kwargs):
            from modules.pig_weights.herdmaster_management_round import build_management_round
            value = deepcopy(build_management_round(*args, **kwargs))
            value[_field] = _value
            return value

        result = consume(specialist_builder=lying_builder)
        assert result["systemic_exception"]["reason"] == "herdmaster_management_round_malformed"
        assert result["sends_telegram"] is False
        assert result["writes_farm_data"] is False


def test_malformed_active_lifecycle_is_contained_with_zero_authority():
    for malformed in (None, ["not-a-binding"], [{"pig_id": "PIG-1"}]):
        result = consume(active_lifecycles=malformed)
        assert result["systemic_exception"]["reason"] == "herdmaster_management_round_malformed"
        assert result["writes_farm_data"] is result["sends_telegram"] is False


def test_trusted_clock_rejects_backdated_invocation_and_evidence():
    result = consume(invocation_at=NOW - timedelta(days=30), trusted_now=NOW)
    assert result["systemic_exception"]["reason"] == "authenticated_manager_context_stale"


def test_scheduled_mission_identity_is_replay_bound():
    first = consume(authority=issue_scheduled_manager_context(OWNER, "MISSION-A", NOW))
    binding = first["binding"]
    prior = [{
        "management_round_identity": binding["management_round_identity"],
        "deduplication_key": binding["deduplication_key"],
        "result_digest": binding["result_digest"],
        "evidence_generation": binding["evidence_generation"],
        "active_case_digest": binding["active_case_deduplication_state"]["digest"],
        "invocation_context_digest": binding["invocation_context"]["digest"],
    }]
    changed = consume(
        authority=issue_scheduled_manager_context(OWNER, "MISSION-B", NOW),
        prior_consumptions=prior,
    )
    assert changed["systemic_exception"]["reason"] == "herdmaster_management_round_binding_changed"


def test_conflicting_prior_rows_fail_closed_independent_of_order():
    first = consume()
    binding = first["binding"]
    exact = {
        "management_round_identity": binding["management_round_identity"],
        "deduplication_key": binding["deduplication_key"],
        "result_digest": binding["result_digest"],
        "evidence_generation": binding["evidence_generation"],
        "active_case_digest": binding["active_case_deduplication_state"]["digest"],
        "invocation_context_digest": binding["invocation_context"]["digest"],
    }
    changed = {**exact, "result_digest": "0" * 64}
    for rows in ([exact, changed], [changed, exact]):
        result = consume(prior_consumptions=rows)
        assert result["systemic_exception"]["reason"] == "herdmaster_management_round_binding_changed"
