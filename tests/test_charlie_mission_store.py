import unittest
from datetime import datetime, timezone
from pathlib import Path

from modules.charlie.mission_store import (
    agent_sequence_for_mission,
    build_mission_review_packet,
    charlie_brain_registry,
    get_mission,
    list_missions,
    mission_status_summary,
    normalize_approval_level,
    normalize_mission_lane,
    normalize_workflow_template,
    project_memory_for_lane,
    record_mission_review_decision,
    record_mission,
    record_mission_event,
    update_mission_queue_priority,
    update_mission_status,
    update_mission_vault,
)


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


class CharlieMissionStoreTests(unittest.TestCase):
    def test_record_mission_requires_database_configuration(self):
        result, status_code = record_mission({"raw_text": "Build CHARLIE mission queue"}, database_url="")

        self.assertEqual(status_code, 503)
        self.assertFalse(result["stored"])
        self.assertEqual(result["status"], "not_configured")

    def test_record_mission_writes_mission_and_event_with_fake_connection(self):
        connection = FakeConnection()

        result, status_code = record_mission(
            {"raw_text": "Build CHARLIE mission queue", "urgency": "P1", "mission_lane": "charlie"},
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
        self.assertIn("brain_registry", mission_params["metadata_json"])
        self.assertIn("project_memory", mission_params["metadata_json"])
        self.assertIn("intake_quality", mission_params["metadata_json"])
        self.assertIn('"mission_lane": {"label": "CHARLIE CORE"', mission_params["metadata_json"])

    def test_normalize_mission_lane_maps_aliases_and_unknowns(self):
        self.assertEqual(normalize_mission_lane("FRED")["id"], "fred")
        self.assertEqual(normalize_mission_lane("private transfers")["label"], "FRED")
        self.assertEqual(normalize_mission_lane("pig tracker")["id"], "farm_pig_application")
        self.assertEqual(normalize_mission_lane("unknown lane")["id"], "unassigned")

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

        self.assertEqual(sequence[:2], ["idea_expander", "product_architect"])
        self.assertIn("qa_red_team", sequence)
        self.assertIn("product_reviewer", sequence)
        self.assertIn("security_reviewer", sequence)
        self.assertIn("evidence_reviewer", sequence)
        self.assertEqual(sequence[-1], "reviewer")

    def test_income_stream_template_adds_full_review_board(self):
        template = normalize_workflow_template("deep income stream")
        sequence = agent_sequence_for_mission("deep income stream")

        self.assertEqual(template["id"], "income_stream")
        self.assertIn("business_reviewer", sequence)
        self.assertIn("product_reviewer", sequence)
        self.assertIn("security_reviewer", sequence)
        self.assertIn("evidence_reviewer", sequence)
        self.assertLess(sequence.index("qa_red_team"), sequence.index("business_reviewer"))
        self.assertLess(sequence.index("evidence_reviewer"), sequence.index("reviewer"))

    def test_charlie_brain_registry_indexes_active_truth_docs(self):
        docs = charlie_brain_registry("charlie_core")
        paths = {item["doc_path"] for item in docs}

        self.assertIn("docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md", paths)
        self.assertTrue(all(item["status"] == "active" for item in docs))
        self.assertTrue(all("summary" in item for item in docs))

    def test_project_memory_for_lane_maps_business_lanes(self):
        memory = project_memory_for_lane({"id": "sam"})

        self.assertEqual(memory["project_key"], "sam")
        self.assertIn("Sales agent", memory["purpose"])
        self.assertIn("docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md", memory["active_truth_docs"])

    def test_charlie_brain_migration_defines_document_and_memory_tables(self):
        migration = Path("supabase/migrations/202607010001_create_charlie_brain_v1_tables.sql").read_text(encoding="utf-8")

        self.assertIn("create table if not exists public.charlie_brain_documents", migration)
        self.assertIn("create table if not exists public.charlie_project_memory", migration)
        self.assertIn("create table if not exists public.charlie_mission_brain_context", migration)

    def test_list_missions_maps_rows(self):
        now = datetime(2026, 6, 30, tzinfo=timezone.utc)
        row = (
            "MISSION-1", "new", "telegram", "12345", "67890",
            "Build queue", "Build queue", "P1", "feature build", "LEVEL 3",
            "", "", "codex_chat_updated", {"owner": "masked", "mission_lane": {"id": "sam", "label": "SAM"}}, now, now,
        )

        result, status_code = list_missions(
            limit=1,
            database_url="postgres://unit-test",
            connect_factory=lambda _: FakeConnection([row]),
        )

        self.assertEqual(status_code, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["missions"][0]["mission_id"], "MISSION-1")
        self.assertEqual(result["missions"][0]["metadata"], {"owner": "masked", "mission_lane": {"id": "sam", "label": "SAM"}})
        self.assertEqual(result["missions"][0]["mission_lane"]["id"], "sam")
        self.assertEqual(result["missions"][0]["mission_lane"]["label"], "SAM")
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
            "blocked",
            "pr_ready",
            "release_approved",
            "release_in_progress",
            "approved",
            "new",
        ])
        self.assertNotIn("done", params["owner_queue_statuses"])
        self.assertNotIn("rejected", params["owner_queue_statuses"])
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

    def test_build_mission_review_packet_collects_stage_8_evidence(self):
        packet = build_mission_review_packet({
            "mission_id": "MISSION-1",
            "status": "pr_ready",
            "title": "Review SAM workflow",
            "raw_text": "Fix SAM handoff.",
            "approval_level": "LEVEL 3",
            "mission_lane": {"id": "sam", "label": "SAM"},
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
        self.assertEqual(packet["mission"]["mission_lane"]["label"], "SAM")
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
