from unittest.mock import patch
import hashlib
import unittest

from modules.charlie.control_tower_feedback import (
    ACTION, DECISION_EVENT, DECISION_SOURCE_KIND, FEEDBACK_EVENT, SOURCE_KIND,
    handle_control_tower_feedback, process_pending_control_tower_feedback,
    shadow_observation_eligible, control_tower_feedback_readback,
)
from modules.charlie.mission_store import BOOTSTRAP_PORTFOLIO_ADMISSION
from modules.charlie.private_policy import authenticate_private_action_context
from scripts import charlie_mission_pickup as pickup


ENV = {"CHARLIE_SHADOW_CONTROL_TOWER_ENABLED": "true",
    "CHARLIE_EXECUTIVE_ENABLED": "true", "CHARLIE_TELEGRAM_BOT_TOKEN": "token",
    "CHARLIE_TELEGRAM_WEBHOOK_SECRET": "s" * 32,
    "CHARLIE_TELEGRAM_OWNER_USER_ID": "42", "CHARLIE_TELEGRAM_OWNER_CHAT_ID": "42"}
AUTH = authenticate_private_action_context(
    {"message": {"from": {"id": 42}, "chat": {"id": 42, "type": "private"}}},
    {"X-Telegram-Bot-Api-Secret-Token": "s" * 32}, "CMQ-20260813-05", ENV)


def mission():
    return {"mission_id": "CMQ-20260813-05", "status": "paused",
        "metadata": {"portfolio_admission": BOOTSTRAP_PORTFOLIO_ADMISSION}}


def transaction():
    feedback = "Genuine terminal feedback pasted by Charl."
    return {
        "feedback_transaction_id": "CTF-GENUINE-001",
        "terminal_identity": "CORE-development-terminal",
        "terminal_state": "released",
        "deployed_agent_identity": "CORE-durable-runner",
        "existing_mission_id": "CMQ-20260813-05",
        "business_status": "WORKING",
        "evidence": {"documented": ["handover"], "runtime_loaded": [],
            "provider_verified": [], "physical": []},
        "worktree_classification": "clean_retained",
        "collision_assessment": "none",
        "proposed_next_terminal": "CORE-development-terminal",
        "proposed_next_action": "CONTINUE",
        "proposed_continuation_prompt": "Continue the same mission.",
        "expected_owner_visible_result": "CORE continues without duplicated work.",
        "confidence": 0.9, "reasons": ["current evidence"],
        "worktree_identity": "C:/tmp/cmq-20260813-05-portfolio-baseline@abc",
        "feedback_occurred_at": "2026-08-15T10:00:00+00:00",
        "control_tower_reconciliation_id": "CTR-001",
        "source_kind": SOURCE_KIND,
        "owner_pasted_feedback": feedback,
        "owner_pasted_feedback_sha256": hashlib.sha256(feedback.encode("utf-8")).hexdigest(),
    }


def action(record_type="feedback"):
    return {"action": ACTION, "record_type": record_type, "transaction": transaction()}


def reader(_mission_id):
    return {"mission": mission()}, 200


def test_only_exact_bootstrap_is_observation_eligible_not_runtime_runnable():
    assert shadow_observation_eligible(mission())
    assert not shadow_observation_eligible({**mission(), "status": "approved"})
    assert not shadow_observation_eligible({**mission(), "mission_id": "CMQ-OTHER"})
    assert BOOTSTRAP_PORTFOLIO_ADMISSION["runnable"] is False


def test_producer_requires_sealed_auth_and_genuine_owner_paste_source():
    with patch("modules.charlie.control_tower_feedback.append_operational_event") as append:
        result, status = handle_control_tower_feedback(action(), runtime_context={},
            environ=ENV, mission_reader=reader)
        assert status == 403 and result["status"] == "control_tower_private_authentication_required"
        changed = action(); changed["transaction"]["source_kind"] = "conversation_memory"
        result, status = handle_control_tower_feedback(changed, runtime_context=AUTH,
            environ=ENV, mission_reader=reader)
        assert status == 400 and result["status"] == "control_tower_feedback_source_not_genuine"
        append.assert_not_called()


def test_feedback_digest_is_required_and_must_match_exact_content():
    changed = action()
    changed["transaction"]["owner_pasted_feedback"] += " changed"
    with patch("modules.charlie.control_tower_feedback.append_operational_event") as append:
        result, status = handle_control_tower_feedback(
            changed, runtime_context=AUTH, environ=ENV, mission_reader=reader)
    assert status == 400 and result["status"] == "control_tower_feedback_digest_mismatch"
    append.assert_not_called()


def test_feedback_producer_appends_once_with_zero_authority():
    with patch("modules.charlie.control_tower_feedback.append_operational_event",
               return_value=({"success": True, "status": "operational_event_appended",
                              "created": True, "event_id": "EVT-1"}, 201)) as append:
        result, status = handle_control_tower_feedback(action(), runtime_context=AUTH,
            environ=ENV, mission_reader=reader)
    assert status == 201 and result["event_id"] == "EVT-1"
    packet = append.call_args.args[0]
    assert packet["event_type"] == FEEDBACK_EVENT
    assert packet["provenance"]["source_ref"] == SOURCE_KIND
    assert result["dispatches"] == result["missions_created"] == result["farm_writes"] == 0


def test_human_decision_fails_until_durable_proposal_exists():
    payload = action("human_decision")
    payload["transaction"]["source_kind"] = DECISION_SOURCE_KIND
    payload["transaction"].pop("owner_pasted_feedback")
    payload["transaction"]["feedback_reconciliation_id"] = "CTR-001"
    payload["human_decision"] = {"human_decision_id": "H-1",
        "actual_next_terminal": "CORE-development-terminal", "actual_next_action": "CONTINUE",
        "actual_continuation_prompt": "Continue.", "actual_owner_visible_result": "Continued."}
    with patch("modules.charlie.control_tower_feedback.load_operational_events",
               return_value=({"success": True, "events": []}, 200)), \
         patch("modules.charlie.control_tower_feedback.append_operational_event") as append:
        result, status = handle_control_tower_feedback(payload, runtime_context=AUTH,
            environ=ENV, mission_reader=reader)
    assert status == 409 and result["status"] == "control_tower_proposal_must_precede_decision"
    append.assert_not_called()


def test_decision_must_link_exact_original_feedback_identity():
    payload = action("human_decision")
    payload["transaction"]["source_kind"] = DECISION_SOURCE_KIND
    payload["transaction"].pop("owner_pasted_feedback")
    payload["transaction"]["feedback_reconciliation_id"] = "WRONG"
    payload["human_decision"] = {"human_decision_id": "H-1",
        "actual_next_terminal": "CORE-development-terminal", "actual_next_action": "CONTINUE",
        "actual_continuation_prompt": "Continue.", "actual_owner_visible_result": "Continued."}
    proposal = {"proposal_id": "SCTP-1", "feedback_transaction_id": "CTF-GENUINE-001"}
    events = [
        {"event_type": "shadow_control_tower_proposal_recorded",
         "payload": {"proposal": proposal}},
        {"event_type": FEEDBACK_EVENT, "payload": {"transaction": transaction()}},
    ]
    with patch("modules.charlie.control_tower_feedback.load_operational_events",
               return_value=({"success": True, "events": events}, 200)), \
         patch("modules.charlie.control_tower_feedback.append_operational_event") as append:
        result, status = handle_control_tower_feedback(payload, runtime_context=AUTH,
            environ=ENV, mission_reader=reader)
    assert status == 409 and result["status"] == "control_tower_decision_feedback_linkage_mismatch"
    append.assert_not_called()


def test_worker_consumes_feedback_then_decision_with_replay_noop():
    tx = transaction()
    proposal = {"proposal_id": "SCTP-1", "feedback_transaction_id": tx["feedback_transaction_id"],
        "existing_mission_id": "CMQ-20260813-05"}
    feedback = {"event_type": FEEDBACK_EVENT, "aggregate_id": tx["feedback_transaction_id"],
        "source_system": "control_tower_feedback_ingress_v1", "authority_tier": "observe",
        "privacy_class": "owner_private", "actor_type": "control_tower_reconciler",
        "provenance": {"source_ref": SOURCE_KIND, "owner_pasted": True},
        "payload": {"transaction": tx}}
    decision = {**feedback, "event_type": DECISION_EVENT,
        "provenance": {"source_ref": DECISION_SOURCE_KIND, "human_decision_canonical": True},
        "payload": {"proposal": proposal, "human_decision": {"human_decision_id": "H-1"}}}
    with patch("modules.charlie.control_tower_feedback.load_operational_events",
               return_value=({"success": True, "events": [feedback, decision]}, 200)), \
         patch("modules.charlie.control_tower_feedback.record_shadow_proposal",
               return_value=({"success": True, "status": "operational_event_appended"}, 201)) as record, \
         patch("modules.charlie.control_tower_feedback.compare_human_decision",
               return_value=({"success": True, "status": "operational_event_appended"}, 201)) as compare:
        result = process_pending_control_tower_feedback(environ=ENV, mission_reader=reader)
    assert result["processed_count"] == 2 and result["success"]
    record.assert_called_once(); compare.assert_called_once()
    assert result["dispatches"] == result["provider_messages"] == result["farm_writes"] == 0


def test_identity_readback_omits_feedback_content_and_reports_lifecycle_ids():
    events = [
        {"event_id": "E1", "event_type": FEEDBACK_EVENT, "aggregate_id": "F1",
         "occurred_at": "2026-08-15T10:00:00Z", "payload": {"transaction": transaction()}},
        {"event_id": "E2", "event_type": "shadow_control_tower_proposal_recorded",
         "aggregate_id": "F1", "payload": {"proposal": {"proposal_id": "P1"}}},
        {"event_id": "E3", "event_type": DECISION_EVENT, "aggregate_id": "F1",
         "payload": {"human_decision": {"human_decision_id": "D1"}}},
        {"event_id": "E4", "event_type": "shadow_control_tower_human_comparison_recorded",
         "aggregate_id": "F1", "payload": {
             "comparison_id": "C1", "proposal_id": "P1", "human_decision_id": "D1"}},
    ]
    with patch("modules.charlie.control_tower_feedback.load_operational_events",
               return_value=({"success": True, "events": events}, 200)):
        result, status = control_tower_feedback_readback("F1")
    assert status == 200 and len(result["events"]) == 4
    assert result["events"][-1]["comparison_id"] == "C1"
    assert result["counts"][FEEDBACK_EVENT] == 1
    assert "owner_pasted_feedback" not in str(result)
    assert result["dispatches"] == result["farm_writes"] == 0


def test_strict_owner_route_reaches_sealed_private_action_and_readback():
    from app import app
    client = app.test_client()
    policy = {"enabled": True, "owner_user_id": "42", "owner_chat_id": "42",
              "secret": "s" * 32}
    with patch("modules.charlie.routes.require_strict_owner_admin_access", return_value=None), \
         patch("modules.charlie.routes.private_policy", return_value=policy), \
         patch("modules.charlie.routes.handle_authenticated_private_action",
               return_value=({"success": True, "status": "operational_event_appended"}, 201)) as handler:
        response = client.post("/api/charlie/control-tower/feedback",
                               json={"record_type": "feedback", "transaction": transaction()})
    assert response.status_code == 201
    called_action = handler.call_args.args[0]
    assert called_action["action"] == ACTION
    assert handler.call_args.kwargs["existing_mission_id"] == "CMQ-20260813-05"

    with patch("modules.charlie.routes.require_strict_owner_admin_access", return_value=None), \
         patch("modules.charlie.routes.control_tower_feedback_readback",
               return_value=({"success": True, "events": []}, 200)) as readback:
        response = client.get("/api/charlie/control-tower/feedback?feedback_transaction_id=F1")
    assert response.status_code == 200
    readback.assert_called_once_with("F1")


def test_observe_only_runner_cycle_never_touches_mission_or_release_paths():
    old = pickup._TEST_PICKUP_AUTHORIZED
    pickup._TEST_PICKUP_AUTHORIZED = True
    try:
        with patch.dict("os.environ", {"CHARLIE_CORE_EXECUTION_MODE": "observe_only"}, clear=False), \
             patch.object(pickup, "SUPERVISOR_STOP_PATH") as stop, \
             patch.object(pickup, "process_pending_control_tower_feedback",
                          return_value={"success": True, "status": "control_tower_feedback_cycle_complete",
                              "processed_count": 0, "next_eligible_event": FEEDBACK_EVENT}), \
             patch.object(pickup, "pick_up_next_mission") as mission_pickup, \
             patch.object(pickup, "process_release_approved_mission") as release, \
             patch.object(pickup, "write_runner_heartbeat"):
            stop.exists.return_value = False
            result, status = pickup.watch_for_mission(max_checks=1, interval_seconds=5)
        assert status == 200 and result["status"] == "observe_only_cycle_complete"
        assert result["mission_pickup_attempted"] is False
        mission_pickup.assert_not_called(); release.assert_not_called()
    finally:
        pickup._TEST_PICKUP_AUTHORIZED = old


class ControlTowerFeedbackUnittest(unittest.TestCase):
    def test_observation_eligibility(self):
        test_only_exact_bootstrap_is_observation_eligible_not_runtime_runnable()

    def test_authentication_and_source(self):
        test_producer_requires_sealed_auth_and_genuine_owner_paste_source()

    def test_feedback_digest(self):
        test_feedback_digest_is_required_and_must_match_exact_content()

    def test_feedback_append(self):
        test_feedback_producer_appends_once_with_zero_authority()

    def test_proposal_precedes_decision(self):
        test_human_decision_fails_until_durable_proposal_exists()

    def test_decision_linkage(self):
        test_decision_must_link_exact_original_feedback_identity()

    def test_worker_consumption_and_replay(self):
        test_worker_consumes_feedback_then_decision_with_replay_noop()

    def test_readback(self):
        test_identity_readback_omits_feedback_content_and_reports_lifecycle_ids()

    def test_route(self):
        test_strict_owner_route_reaches_sealed_private_action_and_readback()

    def test_observe_only_runner_isolation(self):
        test_observe_only_runner_cycle_never_touches_mission_or_release_paths()
