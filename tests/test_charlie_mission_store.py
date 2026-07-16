import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from modules.charlie.mission_store import (
    agent_sequence_for_mission,
    build_mission_review_packet,
    consume_final_agent_artifact,
    get_mission,
    list_missions,
    list_owner_work_missions,
    mission_status_summary,
    normalize_approval_level,
    record_mission_review_decision,
    record_mission,
    record_mission_event,
    update_mission_queue_priority,
    update_mission_status,
    transition_mission_review_state,
    update_mission_vault,
    _mission_queue_class,
    _normalize_review_send_back_stage,
    _return_workflow_to_stage,
    _update_workflow_items,
)
from modules.charlie import vault_store


class FakeConnection:
    def __init__(self, rows=None):
        self.cursor_instance = FakeCursor(rows or [])

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        self.executed.append((sql, params or {}))

    def fetchall(self):
        return list(self.rows)


class FailingCursor(FakeCursor):
    def execute(self, sql, params=None):
        super().execute(sql, params)
        if "insert into public.charlie_agent_runs" in sql:
            raise RuntimeError("column agent does not exist")


class CharlieMissionStoreTests(unittest.TestCase):
    def test_review_state_transition_updates_status_and_packet_atomically(self):
        connection = FakeConnection([("MISSION-1",)])
        result, status_code = transition_mission_review_state(
            "MISSION-1",
            "approved",
            {"review_status": "internal_recovery_queued", "return_to_stage": "publisher"},
            expected_status="blocked",
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )
        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        update_sql, params = connection.cursor_instance.executed[0]
        self.assertIn("jsonb_build_object('review_packet'", update_sql)
        self.assertEqual(params["status"], "approved")
        self.assertIn("internal_recovery_queued", params["review_packet"])

    def test_final_artifact_consumption_advances_tester_to_qa_once(self):
        metadata = {
            "agent_workflow": [
                {"agent": "builder", "status": "complete", "findings": "Built."},
                {"agent": "tester", "status": "active"},
                {"agent": "qa_red_team", "status": "pending"},
            ],
            "review_packet": {"agent_artifacts": {"builder": {"summary": "Built."}}},
            "mission_vault": {},
        }
        connection = FakeConnection([(metadata,)])
        artifact = {"summary": "Focused tests passed.", "quality_gate": {"passed": True}}
        result, status_code = consume_final_agent_artifact(
            "MISSION-1", "tester", "EXEC-1", 1, artifact, "a" * 64,
            database_url="postgres://unit-test", connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "final_artifact_consumed")
        self.assertEqual(result["next_agent"], "qa_red_team")
        update_params = next(params for sql, params in connection.cursor_instance.executed if "set metadata_json" in sql)
        persisted = __import__("json").loads(update_params["metadata_json"])
        self.assertEqual([item["status"] for item in persisted["agent_workflow"]], ["complete", "complete", "active"])
        self.assertIn("builder", persisted["review_packet"]["agent_artifacts"])
        self.assertEqual(persisted["final_artifact_ingestion"]["last_claim"]["sha256"], "a" * 64)

    def test_final_artifact_duplicate_is_read_only(self):
        identity = f"MISSION-1:EXEC-1:tester:1:{'b' * 64}"
        metadata = {"final_artifact_ingestion": {"claims": [{"identity": identity, "agent": "tester"}]}}
        connection = FakeConnection([(metadata,)])
        result, status_code = consume_final_agent_artifact(
            "MISSION-1", "tester", "EXEC-1", 1, {"summary": "pass"}, "b" * 64,
            database_url="postgres://unit-test", connect_factory=lambda _: connection,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "final_artifact_already_consumed")
        self.assertEqual(len(connection.cursor_instance.executed), 1)

    def test_final_artifact_reconciles_when_stage_already_advanced(self):
        metadata = {
            "agent_workflow": [
                {"agent": "tester", "status": "complete"},
                {"agent": "qa_red_team", "status": "active"},
            ],
            "review_packet": {},
        }
        connection = FakeConnection([(metadata,)])
        result, status_code = consume_final_agent_artifact(
            "MISSION-1", "tester", "EXEC-OLD", 1, {"summary": "Tests passed."}, "c" * 64,
            database_url="postgres://unit-test", connect_factory=lambda _: connection,
        )
        self.assertEqual(status_code, 200)
        self.assertEqual(result["status"], "final_artifact_reconciled_after_advance")
        self.assertTrue(result["claim"]["reconciled_after_advance"])

    def test_update_workflow_items_tolerates_unknown_agent_names(self):
        workflow = [{"agent": "planner", "status": "active", "handoff_to": "builder"}]

        updated = _update_workflow_items(
            workflow,
            "unexpected_specialist",
            "complete",
            "Completed without crashing.",
            "frontend_design_implementer",
        )

        by_agent = {item["agent"]: item for item in updated}
        self.assertEqual(by_agent["unexpected_specialist"]["status"], "complete")
        self.assertEqual(by_agent["unexpected_specialist"]["handoff_to"], "frontend_design_implementer")
        self.assertIn("frontend_design_implementer", by_agent)

    def test_update_workflow_items_adds_optional_parallel_agents_missing_from_stored_workflow(self):
        for agent in ("risk_agent", "visual_reference_interpreter"):
            with self.subTest(agent=agent):
                updated = _update_workflow_items(
                    [{"agent": "source_mapper", "status": "complete"}],
                    agent,
                    "complete",
                    "Parallel review completed.",
                    "builder",
                )

                by_agent = {item["agent"]: item for item in updated}
                self.assertEqual(by_agent[agent]["status"], "complete")
                self.assertEqual(by_agent[agent]["handoff_to"], "builder")
                self.assertIn("builder", by_agent)

    def test_update_workflow_items_enforces_single_active_stage(self):
        workflow = [
            {"agent": "technical_architect", "status": "active", "handoff_to": "builder"},
            {"agent": "builder", "status": "pending", "handoff_to": "tester"},
            {"agent": "tester", "status": "pending", "handoff_to": "qa_red_team"},
        ]

        updated = _update_workflow_items(workflow, "builder", "active", "Build resumed.", "tester")

        active = [item["agent"] for item in updated if item.get("status") == "active"]
        self.assertEqual(active, ["builder"])
        by_agent = {item["agent"]: item for item in updated}
        self.assertEqual(by_agent["technical_architect"]["status"], "pending")

    def test_update_workflow_items_complete_activates_only_handoff(self):
        workflow = [
            {"agent": "technical_architect", "status": "active", "handoff_to": "builder"},
            {"agent": "builder", "status": "active", "handoff_to": "tester"},
            {"agent": "tester", "status": "pending", "handoff_to": "qa_red_team"},
        ]

        updated = _update_workflow_items(workflow, "builder", "complete", "Build complete.", "tester")

        active = [item["agent"] for item in updated if item.get("status") == "active"]
        self.assertEqual(active, ["tester"])

    def test_return_workflow_to_stage_clears_stale_upstream_active_stages(self):
        from modules.charlie.mission_store import _return_workflow_to_stage

        workflow = [
            {"agent": "technical_architect", "status": "active", "handoff_to": "planner"},
            {"agent": "builder", "status": "active", "handoff_to": "tester"},
            {"agent": "tester", "status": "active", "handoff_to": "qa_red_team"},
            {"agent": "qa_red_team", "status": "pending", "handoff_to": "reviewer"},
        ]

        updated = _return_workflow_to_stage(workflow, "tester", "Retest packaged PR.")

        active = [item["agent"] for item in updated if item.get("status") == "active"]
        self.assertEqual(active, ["tester"])
        by_agent = {item["agent"]: item for item in updated}
        self.assertEqual(by_agent["technical_architect"]["status"], "pending")
        self.assertEqual(by_agent["builder"]["status"], "pending")
        self.assertEqual(by_agent["qa_red_team"]["status"], "pending")

    @patch("modules.charlie.mission_store.update_mission_vault")
    @patch("modules.charlie.mission_store.get_mission")
    def test_reviewer_complete_does_not_mark_pr_ready_without_review_packet(self, get_mission_mock, update_vault_mock):
        get_mission_mock.return_value = ({
            "success": True,
            "status": "ok",
            "mission": {
                "mission_id": "MISSION-1",
                "mission_type": "feature build",
                "metadata": {
                    "agent_workflow": [{"agent": "reviewer", "status": "active"}],
                    "mission_vault": {},
                    "mission_context_pack": {},
                    "review_packet": {},
                },
            },
        }, 200)
        update_vault_mock.return_value = ({"success": True, "status": "ok"}, 200)

        from modules.charlie.mission_store import update_mission_workflow_step

        result, status_code = update_mission_workflow_step("MISSION-1", "reviewer", step_status="complete")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(update_vault_mock.call_args.kwargs.get("status"), "")

    @patch("modules.charlie.mission_store.update_mission_vault")
    @patch("modules.charlie.mission_store.get_mission")
    def test_reviewer_complete_can_mark_pr_ready_with_verified_review_packet(self, get_mission_mock, update_vault_mock):
        get_mission_mock.return_value = ({
            "success": True,
            "status": "ok",
            "mission": {
                "mission_id": "MISSION-1",
                "mission_type": "feature build",
                "metadata": {
                    "agent_workflow": [{"agent": "reviewer", "status": "active"}],
                    "mission_vault": {},
                    "mission_context_pack": {},
                    "review_packet": {"review_status": "ready_for_owner_review"},
                },
            },
        }, 200)
        update_vault_mock.return_value = ({"success": True, "status": "ok"}, 200)

        from modules.charlie.mission_store import update_mission_workflow_step

        result, status_code = update_mission_workflow_step("MISSION-1", "reviewer", step_status="complete")

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(update_vault_mock.call_args.kwargs.get("status"), "pr_ready")

    def test_send_back_target_can_append_valid_missing_agent(self):
        workflow = [
            {"agent": "idea_expander", "status": "complete", "handoff_to": "source_mapper"},
            {"agent": "source_mapper", "status": "complete", "handoff_to": "risk_agent"},
        ]

        target = _normalize_review_send_back_stage("builder", workflow)
        updated = _return_workflow_to_stage(workflow, target, "Build the risk mitigation.")

        by_agent = {item["agent"]: item for item in updated}
        self.assertEqual(target, "builder")
        self.assertEqual(by_agent["builder"]["status"], "active")
        self.assertEqual(by_agent["builder"]["findings"], "Build the risk mitigation.")

    def test_record_mission_requires_database_configuration(self):
        result, status_code = record_mission({"raw_text": "Build CHARLIE mission queue"}, database_url="")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["stored"])
        self.assertEqual(result["status"], "not_configured")

    def test_record_mission_writes_mission_and_event_with_fake_connection(self):
        connection = FakeConnection()

        result, status_code = record_mission(
            {"raw_text": "Build CHARLIE mission queue", "urgency": "P1"},
            source_context={"source": "telegram", "telegram_user_id": "12345", "telegram_chat_id": "67890"},
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 201)
        self.assertTrue(result["stored"])
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(connection.cursor_instance.executed), 3)
        mission_params = connection.cursor_instance.executed[1][1]
        self.assertEqual(mission_params["raw_text"], "Build CHARLIE mission queue")
        self.assertEqual(mission_params["telegram_user_id"], "12345")
        self.assertEqual(mission_params["urgency"], "P1")
        self.assertIn("mission_vault", mission_params["metadata_json"])
        self.assertIn("agent_workflow", mission_params["metadata_json"])
        self.assertIn("mission_context_pack", mission_params["metadata_json"])
        self.assertIn("intake_quality", mission_params["metadata_json"])

    def test_record_mission_rejects_placeholder_relay_noise(self):
        result, status_code = record_mission(
            {"title": "Build CHARLIE Relay", "raw_text": "Build CHARLIE Relay"},
            database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection(),
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["stored"])
        self.assertEqual(result["status"], "mission_intake_too_vague")
        self.assertEqual(result["reason"], "placeholder_charlie_relay_title_without_specific_goal")

    def test_mission_queue_class_detects_system_test_from_raw_text(self):
        queue_class = _mission_queue_class(
            "CHARLIE queue check",
            "Validation mission smoke test for the local runner queue.",
        )

        self.assertEqual(queue_class, "system_test")

    def test_mission_queue_class_keeps_real_owner_work_with_test_plan_wording(self):
        queue_class = _mission_queue_class(
            "Improve CHARLIE queue filters",
            "Build better owner mission filters and include focused tests for the change.",
        )

        self.assertEqual(queue_class, "owner_work")

    def test_mission_queue_class_respects_existing_metadata_queue_class(self):
        queue_class = _mission_queue_class(
            "CHARLIE queue check",
            "Validation mission smoke test for the local runner queue.",
            {"intake_quality": {"queue_class": "owner_work"}},
        )

        self.assertEqual(queue_class, "owner_work")

    def test_record_mission_suppresses_duplicate_open_mission(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        duplicate_row = (
            "MISSION-1", "new", "Build clearer queue", "Build clearer queue",
        )
        connection = FakeConnection([duplicate_row])

        result, status_code = record_mission(
            {"title": "Build clearer queue", "raw_text": "Build clearer queue"},
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        self.assertFalse(result["stored"])
        self.assertEqual(result["status"], "duplicate_open_mission")
        self.assertEqual(result["mission_id"], "MISSION-1")

    def test_agent_sequence_for_agent_build_adds_specialists_and_qa(self):
        sequence = agent_sequence_for_mission("agent build")

        self.assertEqual(sequence[:3], ["idea_expander", "source_mapper", "product_architect"])
        self.assertIn("qa_red_team", sequence)
        self.assertIn("evidence_reviewer", sequence)
        self.assertEqual(sequence[-1], "publisher")

    def test_agent_sequence_uses_raw_text_to_route_ui_system_improvement(self):
        sequence = agent_sequence_for_mission(
            "system improvement",
            "Rebuild the CHARLIE CORE dashboard command center UI from the attached screenshot.",
        )

        self.assertIn("visual_reference_interpreter", sequence)
        self.assertIn("creative_ui_designer", sequence)
        self.assertIn("ux_interaction_designer", sequence)
        self.assertIn("frontend_design_implementer", sequence)
        self.assertIn("visual_qa_reviewer", sequence)
        self.assertLess(sequence.index("visual_reference_interpreter"), sequence.index("frontend_design_implementer"))

    def test_agent_sequence_respects_explicit_no_ui_system_improvement(self):
        sequence = agent_sequence_for_mission(
            "system improvement",
            "Run a no UI owner review packet persistence canary. Do not change UI or product behavior.",
        )

        self.assertNotIn("visual_reference_interpreter", sequence)
        self.assertNotIn("creative_ui_designer", sequence)
        self.assertNotIn("ux_interaction_designer", sequence)
        self.assertNotIn("frontend_design_implementer", sequence)
        self.assertIn("risk_agent", sequence)
        self.assertIn("technical_architect", sequence)

    def test_list_missions_maps_rows(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "new", "telegram", "12345", "67890",
            "Build queue", "Build queue", "P1", "feature build", "LEVEL 3",
            "", "", "codex_chat_updated", {"owner": "masked"}, now, now,
        )

        result, status_code = list_missions(
            limit=1,
            database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([row]),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["missions"][0]["mission_id"], "MISSION-1")
        self.assertEqual(result["missions"][0]["metadata"], {"owner": "masked"})
        self.assertEqual(result["missions"][0]["vault"], {})
        self.assertEqual(result["missions"][0]["agent_workflow"], [])
        self.assertEqual(result["missions"][0]["queue_priority"], 100)
        self.assertEqual(result["missions"][0]["queue_class"], "owner_work")

    def test_list_missions_orders_status_queue_by_priority(self):
        connection = FakeConnection([])

        result, status_code = list_missions(
            status="approved",
            limit=10,
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        sql = connection.cursor_instance.executed[0][0]
        self.assertIn("metadata_json->'queue'->>'priority'", sql)
        self.assertIn("created_at asc", sql)
        self.assertIn("mission_id asc", sql)
        self.assertEqual(result["missions"], [])

    def test_list_missions_owner_queue_filters_active_owner_work_statuses(self):
        connection = FakeConnection([])

        result, status_code = list_missions(
            status="owner_queue",
            limit=30,
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        sql, params = connection.cursor_instance.executed[0]
        self.assertIn("status = any(%(owner_queue_statuses)s)", sql)
        self.assertIn("metadata_json->'intake_quality'->>'queue_class'", sql)
        self.assertIn("owner_work", sql)
        self.assertIn("when 'in_progress' then 0", sql)
        self.assertIn("metadata_json->'queue'->>'priority'", sql)
        self.assertIn("created_at asc", sql)
        self.assertEqual(params["owner_queue_statuses"], [
            "in_progress",
            "release_in_progress",
            "pr_ready",
            "blocked",
            "release_approved",
            "approved",
            "new",
        ])
        self.assertNotIn("done", params["owner_queue_statuses"])
        self.assertNotIn("rejected", params["owner_queue_statuses"])
        self.assertEqual(result["missions"], [])

    def test_list_owner_work_missions_filters_one_status_in_sql(self):
        connection = FakeConnection([])

        result, status_code = list_owner_work_missions(
            "approved",
            limit=20,
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        sql, params = connection.cursor_instance.executed[0]
        self.assertIn("where status = %(status)s", sql)
        self.assertIn("metadata_json->'intake_quality'->>'queue_class'", sql)
        self.assertIn("owner_work", sql)
        self.assertIn("metadata_json->'queue'->>'priority'", sql)
        self.assertEqual(params["status"], "approved")
        self.assertEqual(params["limit"], 20)
        self.assertEqual(result["missions"], [])

    def test_list_missions_keeps_recent_order_without_status_filter(self):
        connection = FakeConnection([])

        list_missions(
            limit=10,
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        sql = connection.cursor_instance.executed[0][0]
        self.assertIn("order by created_at desc", sql)
        self.assertNotIn("metadata_json->'queue'->>'priority'", sql)

    def test_record_mission_event_rejects_unknown_event_type(self):
        result, status_code = record_mission_event("MISSION-1", "execute_shell", database_url="")

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_event_type")

    def test_get_mission_returns_single_record(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "approved", "telegram", "12345", "67890",
            "Build queue", "Build queue", "P1", "feature build", "LEVEL 3",
            "", "Owner approved.", "codex_chat_updated", {}, now, now,
        )

        result, status_code = get_mission(
            "MISSION-1",
            database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([row]),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["mission"]["status"], "approved")
        self.assertEqual(result["mission"]["owner_decision"], "Owner approved.")

    def test_update_mission_status_records_event(self):
        connection = FakeConnection([("MISSION-1",)])

        result, status_code = update_mission_status(
            "MISSION-1",
            "approved",
            owner_decision="Owner approved.",
            event_type="approval_decision",
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["mission_status"], "approved")
        self.assertEqual(len(connection.cursor_instance.executed), 2)
        update_params = connection.cursor_instance.executed[0][1]
        self.assertEqual(update_params["status"], "approved")
        self.assertEqual(update_params["owner_decision"], "Owner approved.")

    def test_update_mission_status_expected_status_claim_lost(self):
        connection = FakeConnection([])

        result, status_code = update_mission_status(
            "MISSION-1",
            "in_progress",
            expected_status="approved",
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 409)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "status_claim_lost")
        update_sql, update_params = connection.cursor_instance.executed[0]
        self.assertIn("and status = %(expected_status)s", update_sql)
        self.assertEqual(update_params["expected_status"], "approved")

    def test_update_mission_status_can_update_approval_level(self):
        connection = FakeConnection([("MISSION-1",)])

        result, status_code = update_mission_status(
            "MISSION-1",
            "approved",
            owner_decision="Owner approved code build.",
            approval_level="level3",
            event_type="approval_decision",
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["approval_level"], "LEVEL 3")
        update_sql, update_params = connection.cursor_instance.executed[0]
        self.assertIn("approval_level = %(approval_level)s", update_sql)
        self.assertEqual(update_params["approval_level"], "LEVEL 3")

    def test_normalize_approval_level_accepts_short_forms(self):
        self.assertEqual(normalize_approval_level("level4"), "LEVEL 4")
        self.assertEqual(normalize_approval_level("4"), "LEVEL 4")
        self.assertEqual(normalize_approval_level("LEVEL-3"), "LEVEL 3")

    def test_update_mission_status_rejects_unknown_approval_level(self):
        result, status_code = update_mission_status(
            "MISSION-1",
            "approved",
            approval_level="execute",
            database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([("MISSION-1",)]),
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_approval_level")

    def test_update_mission_status_rejects_unknown_status(self):
        result, status_code = update_mission_status("MISSION-1", "execute_shell", database_url="")

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_mission_status")

    def test_update_mission_queue_priority_records_metadata_and_event(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "approved", "telegram", "12345", "67890",
            "Build queue", "Build queue", "P1", "feature build", "LEVEL 3",
            "", "", "", {"queue": {"priority": 50}}, now, now,
        )
        read_connection = FakeConnection([row])
        update_connection = FakeConnection([("MISSION-1",)])
        connections = [read_connection, update_connection]

        result, status_code = update_mission_queue_priority(
            "MISSION-1",
            10,
            database_url="postgres://unit-test",
            connect_factory=lambda _: connections.pop(0),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["queue_priority"], 10)
        self.assertEqual(len(update_connection.cursor_instance.executed), 2)
        update_sql, update_params = update_connection.cursor_instance.executed[0]
        self.assertIn("metadata_json", update_sql)
        self.assertIn('"priority": 10', update_params["metadata_json"])

    def test_update_mission_queue_priority_rejects_invalid_priority(self):
        result, status_code = update_mission_queue_priority(
            "MISSION-1",
            0,
            database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([("MISSION-1",)]),
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_queue_priority")

    def test_update_mission_vault_merges_metadata_and_records_event(self):
        connection = FakeConnection([("MISSION-1",)])

        result, status_code = update_mission_vault(
            "MISSION-1",
            {
                "mission_vault": {"mission_stage": "planned"},
                "agent_workflow": [{"agent": "planner", "status": "complete"}],
            },
            status="planned",
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["mission_status"], "planned")
        self.assertEqual(len(connection.cursor_instance.executed), 2)
        update_sql, update_params = connection.cursor_instance.executed[0]
        self.assertIn("metadata_json", update_sql)
        self.assertIn("status = %(status)s", update_sql)
        self.assertIn('"mission_stage": "planned"', update_params["metadata_json"])

    def test_update_mission_vault_writes_agent_execution_to_normalized_vault(self):
        connection = FakeConnection([("MISSION-1",)])

        result, status_code = update_mission_vault(
            "MISSION-1",
            {
                "agent_execution": {
                    "execution_id": "EXEC-1",
                    "stages": [{"agent": "builder", "status": "complete", "attempt": 1}],
                },
            },
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        normalized = result["normalized_vault_writes"]
        self.assertEqual(normalized[0]["target"], "agent_run")
        self.assertTrue(normalized[0]["success"])
        self.assertTrue(any("charlie_agent_runs" in sql for sql, _params in connection.cursor_instance.executed))

    def test_update_mission_vault_reports_normalized_write_error_detail(self):
        class FailingConnection(FakeConnection):
            def __init__(self):
                super().__init__([("MISSION-1",)])
                self.cursor_instance = FailingCursor([("MISSION-1",)])

        connection = FailingConnection()

        result, status_code = update_mission_vault(
            "MISSION-1",
            {
                "agent_execution": {
                    "execution_id": "EXEC-1",
                    "stages": [{"agent": "builder", "status": "complete", "attempt": 1}],
                },
            },
            database_url="postgres://unit-test",
            connect_factory=lambda _: connection,
        )

        self.assertEqual(status_code, 200)
        normalized = result["normalized_vault_writes"]
        self.assertFalse(normalized[0]["success"])
        self.assertEqual(normalized[0]["error_type"], "RuntimeError")
        self.assertIn("column agent does not exist", normalized[0]["error_message"])

    def test_vault_write_services_support_legacy_v1_columns(self):
        handoff_connection = FakeConnection([
            ("handoff_id",),
            ("mission_id",),
            ("from_agent",),
            ("to_agent",),
            ("status",),
            ("summary",),
            ("risks",),
            ("tests",),
            ("changed_files",),
            ("quality_gate_json",),
            ("report_json",),
            ("created_at",),
        ])
        handoff_result, handoff_status = vault_store.write_handoff_report(
            {
                "mission_id": "MISSION-1",
                "agent": "tester",
                "handoff_to": "reviewer",
                "summary": "Tests passed.",
                "status": "pass",
            },
            database_url="postgres://unit-test",
            connect_factory=lambda _: handoff_connection,
        )

        self.assertEqual(handoff_status, 200)
        self.assertTrue(handoff_result["success"])
        handoff_sql = handoff_connection.cursor_instance.executed[-1][0]
        self.assertIn("from_agent", handoff_sql)
        self.assertNotIn(" agent,", handoff_sql)

        gate_connection = FakeConnection([
            ("gate_id",),
            ("mission_id",),
            ("agent_name",),
            ("gate_name",),
            ("status",),
            ("reason",),
            ("evidence_json",),
            ("checked_at",),
        ])
        gate_result, gate_status = vault_store.write_quality_gate(
            "MISSION-1",
            "tester",
            "passed",
            reason="Tests passed.",
            database_url="postgres://unit-test",
            connect_factory=lambda _: gate_connection,
        )

        self.assertEqual(gate_status, 200)
        self.assertTrue(gate_result["success"])
        gate_sql = gate_connection.cursor_instance.executed[-1][0]
        self.assertIn("agent_name", gate_sql)
        self.assertIn("checked_at", gate_sql)

    def test_update_mission_vault_requires_metadata(self):
        result, status_code = update_mission_vault(
            "MISSION-1",
            [],
            database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([("MISSION-1",)]),
        )

        self.assertEqual(status_code, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "mission_vault_metadata_required")

    def test_update_mission_workflow_step_records_handoff_context(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "approved", "telegram", "12345", "67890",
            "Build queue", "Build queue", "P1", "feature build", "LEVEL 3",
            "", "", "", {
                "mission_vault": {"mission_stage": "intake"},
                "agent_workflow": [
                    {"agent": "planner", "status": "pending", "purpose": "Scope", "handoff_to": "architect"},
                    {"agent": "architect", "status": "pending", "purpose": "Design", "handoff_to": "builder"},
                ],
                "mission_context_pack": {"version": "charlie_context_pack_v1"},
            }, now, now,
        )
        read_connection = FakeConnection([row])
        update_connection = FakeConnection([("MISSION-1",)])
        connections = [read_connection, update_connection]

        def factory(_):
            return connections.pop(0)

        from modules.charlie.mission_store import update_mission_workflow_step

        result, status_code = update_mission_workflow_step(
            "MISSION-1",
            "planner",
            findings="Scoped for SAM money path.",
            database_url="postgres://unit-test",
            connect_factory=factory,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        update_sql, update_params = update_connection.cursor_instance.executed[0]
        self.assertIn("metadata_json", update_sql)
        self.assertIn('"planner", "status": "complete"', update_params["metadata_json"])
        self.assertIn('"architect", "status": "active"', update_params["metadata_json"])
        self.assertIn("Scoped for SAM money path", update_params["metadata_json"])

    def test_update_mission_workflow_step_adds_missing_specialist_agent(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "approved", "telegram", "12345", "67890",
            "Build UI", "Build UI", "P1", "feature build", "LEVEL 3",
            "", "", "", {
                "mission_vault": {"mission_stage": "intake"},
                "agent_workflow": [
                    {"agent": "planner", "status": "pending", "purpose": "Scope", "handoff_to": "architect"},
                    {"agent": "architect", "status": "pending", "purpose": "Design", "handoff_to": "builder"},
                ],
                "mission_context_pack": {"version": "charlie_context_pack_v1"},
            }, now, now,
        )
        read_connection = FakeConnection([row])
        update_connection = FakeConnection([("MISSION-1",)])
        connections = [read_connection, update_connection]

        def factory(_):
            return connections.pop(0)

        from modules.charlie.mission_store import update_mission_workflow_step

        result, status_code = update_mission_workflow_step(
            "MISSION-1",
            "visual_reference_interpreter",
            step_status="active",
            findings="Mapped owner reference media.",
            next_agent="creative_ui_designer",
            database_url="postgres://unit-test",
            connect_factory=factory,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        _update_sql, update_params = update_connection.cursor_instance.executed[0]
        self.assertIn('"visual_reference_interpreter", "status": "active"', update_params["metadata_json"])
        self.assertIn('"creative_ui_designer", "status": "pending"', update_params["metadata_json"])
        self.assertIn("Mapped owner reference media", update_params["metadata_json"])

    def test_update_workflow_items_allows_next_agent_without_current_agent(self):
        workflow = [{"agent": "builder", "status": "pending", "handoff_to": "tester"}]
        updated = _update_workflow_items(
            workflow, "", "pending", "", "visual_reference_interpreter"
        )
        self.assertEqual(
            [item["agent"] for item in updated],
            ["builder", "visual_reference_interpreter"],
        )

    def test_update_mission_workflow_step_records_blocked_agent_stage(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "approved", "telegram", "12345", "67890",
            "Build queue", "Build queue", "P1", "feature build", "LEVEL 3",
            "", "", "", {
                "mission_vault": {"mission_stage": "intake"},
                "agent_workflow": [
                    {"agent": "builder", "status": "active", "purpose": "Build", "handoff_to": "tester"},
                    {"agent": "tester", "status": "pending", "purpose": "Test", "handoff_to": "reviewer"},
                ],
                "mission_context_pack": {"version": "charlie_context_pack_v1"},
            }, now, now,
        )
        read_connection = FakeConnection([row])
        update_connection = FakeConnection([("MISSION-1",)])
        connections = [read_connection, update_connection]

        def factory(_):
            return connections.pop(0)

        from modules.charlie.mission_store import update_mission_workflow_step

        result, status_code = update_mission_workflow_step(
            "MISSION-1",
            "builder",
            step_status="blocked",
            findings="Final artifact missing.",
            database_url="postgres://unit-test",
            connect_factory=factory,
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        _update_sql, update_params = update_connection.cursor_instance.executed[0]
        self.assertIn('"mission_stage": "blocked_at_builder"', update_params["metadata_json"])
        self.assertIn('"builder", "status": "blocked"', update_params["metadata_json"])

    def test_build_mission_review_packet_collects_stage_8_evidence(self):
        packet = build_mission_review_packet({
            "mission_id": "MISSION-1",
            "status": "pr_ready",
            "title": "Review SAM workflow",
            "raw_text": "Fix SAM handoff.",
            "approval_level": "LEVEL 3",
            "vault": {"desired_outcome": "SAM handoff works.", "test_plan": ["python -m unittest tests.test_sam"]},
            "agent_workflow": [{"agent": "tester", "status": "complete", "findings": "Tests passed."}],
            "metadata": {
                "review_packet": {
                    "changed_files": ["modules/sam.py"],
                    "local_preview": {"url": "http://127.0.0.1:5000/sales/meat-leads"},
                    "visual_review": {
                        "contract": "charlie_visual_review_v1",
                        "ui_related": True,
                        "status": "captured",
                        "media": [{"label": "SAM view", "reference": "/api/charlie/build-relay/review-media/MISSION-1/sam.png", "media_type": "image"}],
                    },
                    "qa_evidence": ["QA passed."],
                    "handoff_reports": {"qa_red_team": {"summary": "QA passed."}},
                },
            },
        })

        self.assertTrue(packet["can_approve_final_release"])
        self.assertIn("tester: Tests passed.", packet["findings"])
        self.assertEqual(packet["changed_files"], ["modules/sam.py"])
        self.assertEqual(packet["qa_evidence"], ["QA passed."])
        self.assertIn("qa_red_team", packet["handoff_reports"])
        self.assertEqual(packet["local_preview"]["url"], "http://127.0.0.1:5000/sales/meat-leads")
        self.assertTrue(packet["visual_review"]["ui_related"])
        self.assertEqual(packet["visual_review"]["media"][0]["label"], "SAM view")
        self.assertIn("Dashboard review decisions update mission state only", packet["execution_boundary"])

    def test_record_mission_review_decision_final_approval_sets_release_approved_level_4(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "pr_ready", "telegram", "12345", "67890",
            "Build review gate", "Build review gate", "P1", "feature build", "LEVEL 3",
            "", "", "", {
                "review_packet": {
                    "summary": "Ready",
                    "visual_review": {
                        "ui_related": True,
                        "cleanup": {"required": True, "status": "pending_owner_decision", "local_path": ".charlie_runner/review_media/MISSION-1"},
                    },
                },
            }, now, now,
        )
        read_connection = FakeConnection([row])
        update_connection = FakeConnection([("MISSION-1",)])
        connections = [read_connection, update_connection]

        result, status_code = record_mission_review_decision(
            "MISSION-1",
            "approve_final_release",
            comments="Looks good.",
            database_url="postgres://unit-test",
            connect_factory=lambda _: connections.pop(0),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["mission_status"], "release_approved")
        self.assertEqual(result["approval_level"], "LEVEL 4")
        update_sql, update_params = update_connection.cursor_instance.executed[0]
        self.assertIn("metadata_json", update_sql)
        self.assertEqual(update_params["status"], "release_approved")
        self.assertEqual(update_params["approval_level"], "LEVEL 4")
        self.assertIn("approve_final_release", update_params["metadata_json"])
        self.assertIn("cleanup_requested", update_params["metadata_json"])

    def test_record_mission_review_decision_send_back_keeps_comments_for_next_runner_pickup(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "pr_ready", "telegram", "12345", "67890",
            "Build review gate", "Build review gate", "P1", "feature build", "LEVEL 3",
            "", "", "", {
                "agent_workflow": [{"agent": "builder", "status": "complete"}],
                "mission_vault": {"mission_stage": "review_ready"},
            }, now, now,
        )
        read_connection = FakeConnection([row])
        update_connection = FakeConnection([("MISSION-1",)])
        connections = [read_connection, update_connection]

        result, status_code = record_mission_review_decision(
            "MISSION-1",
            "send_back",
            comments="Fix the error panel.",
            target_stage="builder",
            database_url="postgres://unit-test",
            connect_factory=lambda _: connections.pop(0),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["mission_status"], "approved")
        update_params = update_connection.cursor_instance.executed[0][1]
        self.assertEqual(update_params["status"], "approved")
        self.assertIn("Fix the error panel.", update_params["metadata_json"])
        self.assertIn('"mission_stage": "returned_to_builder"', update_params["metadata_json"])

    def test_record_mission_review_decision_send_back_normalizes_invalid_ui_target_to_builder(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "pr_ready", "telegram", "12345", "67890",
            "No UI canary", "No UI canary", "P2", "system improvement", "LEVEL 3",
            "", "", "", {
                "agent_workflow": [
                    {"agent": "planner", "status": "complete"},
                    {"agent": "architect", "status": "complete"},
                    {"agent": "builder", "status": "complete"},
                    {"agent": "tester", "status": "complete"},
                    {"agent": "qa_red_team", "status": "complete"},
                    {"agent": "reviewer", "status": "complete"},
                ],
                "mission_vault": {"mission_stage": "review_ready"},
                "review_packet": {"review_status": "ready_for_owner_review"},
            }, now, now,
        )
        read_connection = FakeConnection([row])
        update_connection = FakeConnection([("MISSION-1",)])
        connections = [read_connection, update_connection]

        result, status_code = record_mission_review_decision(
            "MISSION-1",
            "send_back",
            comments="Fix non-UI verification evidence.",
            target_stage="frontend_design_implementer",
            database_url="postgres://unit-test",
            connect_factory=lambda _: connections.pop(0),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        update_params = update_connection.cursor_instance.executed[0][1]
        metadata_json = update_params["metadata_json"]
        self.assertIn('"target_stage": "builder"', metadata_json)
        self.assertIn('"return_to_stage": "builder"', metadata_json)
        self.assertIn('"mission_stage": "returned_to_builder"', metadata_json)
        self.assertNotIn("returned_to_frontend_design_implementer", metadata_json)

    def test_mission_status_summary_maps_counts(self):
        result, status_code = mission_status_summary(
            database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([("new", 2), ("planned", 1)]),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["counts"], {"new": 2, "planned": 1})


if __name__ == "__main__":
    unittest.main()
