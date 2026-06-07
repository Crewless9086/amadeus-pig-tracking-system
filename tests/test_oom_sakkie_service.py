import unittest
import os
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from modules.oom_sakkie.policy import get_runtime_policy
from modules.oom_sakkie.review_advisor import build_review_advice
from modules.oom_sakkie.service import IntentMatch, classify_intent, handle_message, is_unsupported_action_request
from modules.oom_sakkie.specialists import list_specialist_manifests
from modules.oom_sakkie.trace_store import (
    FEEDBACK_TYPES,
    build_feedback_id,
    build_trace_id,
    _trace_params,
    _trace_row,
    _review_filter,
    _trace_list_where_clause,
    get_trace_review_summary,
    hash_tool_result,
    list_review_advisor_traces,
    list_recent_traces,
    record_trace_feedback,
    write_trace,
)
from modules.oom_sakkie.tools import RiskLevel, TOOL_REGISTRY, list_tool_catalog


class OomSakkieServiceTests(unittest.TestCase):
    def test_tool_registry_contract(self):
        self.assertEqual(
            set(TOOL_REGISTRY),
            {
                "farm_attention_summary",
                "power_current",
                "power_recent",
                "weather_now",
                "weather_today",
                "weather_forecast",
                "irrigation_status",
                "dashboard_summary",
                "pig_allocation_readiness",
                "meat_planning",
                "sales_dashboard",
            },
        )
        for tool in TOOL_REGISTRY.values():
            with self.subTest(tool=tool.name):
                self.assertEqual(tool.risk_level, RiskLevel.READ_ONLY)
                self.assertFalse(tool.requires_confirmation)
                self.assertEqual(tool.input_schema["type"], "object")
                self.assertEqual(tool.output_schema["type"], "object")
                self.assertTrue(callable(tool.handler))

    def test_tool_catalog_serializes_runtime_registry(self):
        catalog = list_tool_catalog()
        names = {item["name"] for item in catalog}

        self.assertEqual(names, set(TOOL_REGISTRY))
        irrigation = next(item for item in catalog if item["name"] == "irrigation_status")
        self.assertEqual(irrigation["risk_level"], 0)
        self.assertEqual(irrigation["risk_label"], "READ_ONLY")
        self.assertFalse(irrigation["requires_confirmation"])
        self.assertIn("Never starts or stops irrigation", irrigation["description"])
        self.assertEqual(irrigation["input_schema"]["additionalProperties"], False)

    def test_runtime_policy_is_read_only_local_kiosk(self):
        policy = get_runtime_policy()

        self.assertTrue(policy["success"])
        self.assertEqual(policy["mode"], "local_kiosk_read_only")
        self.assertTrue(policy["backend_as_brain"])
        self.assertFalse(policy["telegram_cutover_enabled"])
        self.assertFalse(policy["llm_router_enabled"])
        self.assertFalse(policy["write_tools_enabled"])
        self.assertFalse(policy["physical_controls_enabled"])
        self.assertFalse(policy["backend_voice_vendors_enabled"])
        self.assertFalse(policy["always_on_mic_enabled"])
        self.assertEqual(policy["browser_speech_mode"], "push_to_talk_only")
        self.assertEqual(policy["continue_conversation_max_turns"], 5)
        self.assertEqual(policy["voice_auto_send_ms"], 2000)
        self.assertEqual(policy["message_endpoint_access"]["default"], "reachable_wherever_flask_is_reachable")
        self.assertEqual(policy["message_endpoint_access"]["route"], "POST /api/oom-sakkie/message")
        self.assertIn("reverse_proxy_assumption", policy["review_endpoints_access"])
        self.assertEqual(policy["kiosk_policy"]["max_risk_level"], 0)
        self.assertEqual(policy["kiosk_policy"]["requires_confirmation_tools"], [])
        self.assertEqual(policy["tool_counts"]["write_or_confirmation"], 0)
        self.assertIn("write tools", policy["blocked_capabilities"])

    def test_specialist_manifests_are_planned_and_approval_gated(self):
        manifests = list_specialist_manifests()
        names = {item["name"] for item in manifests}
        allowed_modes = {"read_only_advisory", "draft_only", "internal_planning_only"}

        self.assertIn("Sentinel", names)
        self.assertIn("Forge", names)
        self.assertIn("Prism", names)
        self.assertIn("Ledger", names)
        self.assertIn("Rootline", names)
        self.assertIn("Gatekeeper", names)
        for item in manifests:
            with self.subTest(specialist=item["name"]):
                self.assertEqual(item["status"], "planned")
                self.assertLessEqual(item["risk_level"], 1)
                self.assertTrue(item["approval_required_for"])
                self.assertTrue(item["first_inputs"])
                self.assertTrue(item["first_outputs"])
                self.assertIn(item["allowed_mode"], allowed_modes)
                self.assertNotIn("autonomous", item["allowed_mode"])
        beacon = next(item for item in manifests if item["slug"] == "beacon")
        self.assertEqual(beacon["risk_level"], 1)
        self.assertEqual(beacon["allowed_mode"], "draft_only")

    def test_review_advisor_is_advisory_and_prioritizes_trace_review(self):
        advisor = build_review_advice(
            summary={
                "success": True,
                "configured": True,
                "summary": {
                    "total_traces": 10,
                    "reviewed_traces": 4,
                    "unreviewed_traces": 6,
                    "problem_traces": 1,
                    "problem_rate_pct": 25.0,
                },
            },
            issue_traces={
                "success": True,
                "configured": True,
                "traces": [{
                    "trace_id": "OSK-ISSUE",
                    "tool_name": "weather_today",
                    "user_text": "weather today",
                    "answer": "answer",
                    "created_at": "2026-06-07T08:00:00+00:00",
                    "latest_feedback": {"feedback_type": "wrong_tool"},
                }],
            },
            unreviewed_traces={
                "success": True,
                "configured": True,
                "traces": [{
                    "trace_id": "OSK-UNREVIEWED",
                    "tool_name": "power_current",
                    "user_text": "power now",
                    "answer": "answer",
                    "created_at": "2026-06-07T08:01:00+00:00",
                    "stale_warnings": ["Power data is 42 minutes old."],
                    "latest_feedback": None,
                }],
            },
            statuses={"review_summary": 200, "issue_traces": 200, "unreviewed_traces": 200},
        )

        self.assertTrue(advisor["success"])
        self.assertEqual(advisor["mode"], "advisory_only")
        self.assertFalse(advisor["autonomous_marking_enabled"])
        self.assertFalse(advisor["writes_feedback"])
        self.assertEqual(advisor["review_queue"][0]["priority"], "high")
        self.assertEqual(advisor["review_queue"][1]["reason"], "unreviewed_with_stale_warning")
        self.assertTrue(any("Hold expansion" in action for action in advisor["suggested_actions"]))

    def test_review_advisor_reports_unconfigured_trace_store_without_writes(self):
        advisor = build_review_advice(
            summary={"success": False, "configured": False, "status": "not_configured"},
            issue_traces={"success": False, "configured": False, "traces": []},
            unreviewed_traces={"success": False, "configured": False, "traces": []},
            statuses={"review_summary": 503, "issue_traces": 503, "unreviewed_traces": 503},
        )

        self.assertFalse(advisor["success"])
        self.assertFalse(advisor["configured"])
        self.assertFalse(advisor["writes_feedback"])
        self.assertIn("Trace storage is not configured", advisor["suggested_actions"][0])

    def test_rule_routing_known_phrases(self):
        cases = {
            "what needs attention today": "farm_attention_summary",
            "what is the power like now": "power_current",
            "show me the recent power profile": "power_recent",
            "weather now please": "weather_now",
            "weather today please": "weather_today",
            "weather forecast for the next few days": "weather_forecast",
            "what is the irrigation status": "irrigation_status",
            "start irrigation": "irrigation_status",
            "how is the farm": "dashboard_summary",
            "which pigs are ready for meat": "meat_planning",
            "show me pig allocation": "pig_allocation_readiness",
            "sales dashboard overview": "sales_dashboard",
        }
        for text, expected_tool in cases.items():
            with self.subTest(text=text):
                match = classify_intent(text)
                self.assertIsNotNone(match)
                self.assertEqual(match.tool_name, expected_tool)
                self.assertGreaterEqual(match.confidence, 0.9)

    def test_unsupported_action_guard_identifies_write_or_control_phrases(self):
        self.assertTrue(is_unsupported_action_request("delete that pig record"))
        self.assertTrue(is_unsupported_action_request("send the order message"))
        self.assertTrue(is_unsupported_action_request("turn off the pump"))
        self.assertFalse(is_unsupported_action_request("what is the power doing now"))

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_low_confidence_returns_needs_clarification(self, _write_trace):
        result, status = handle_message({
            "text": "tell me something clever",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "")
        self.assertIn("not sure", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_unsupported_action_returns_read_only_block(self, _write_trace):
        result, status = handle_message({
            "text": "send the customer an order message",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["needs_clarification"])
        self.assertTrue(result["action_blocked"])
        self.assertEqual(result["tool_used"], "")
        self.assertEqual(result["risk_level"], 0)
        self.assertIn("read-only", result["answer"])
        self.assertEqual(result["stale_warnings"], [])
        self.assertIn("No write", result["safety_notes"][0])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.service.classify_intent")
    def test_synthetic_low_confidence_match_returns_clarification(self, mock_classify, _write_trace):
        mock_classify.return_value = IntentMatch("maybe_power", "power_current", 0.4, "test:low_confidence")
        result, status = handle_message({
            "text": "maybe check something",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "")
        self.assertIn("not sure", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_user_text_is_capped_before_trace(self, mock_write_trace):
        result, status = handle_message({
            "text": "power " + ("x" * 5000),
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "power_current")
        trace = mock_write_trace.call_args.args[0]
        self.assertLessEqual(len(trace["user_text"]), 2000)

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.tools.get_current_power_state")
    def test_stale_power_warning_is_returned(self, mock_power, _write_trace):
        mock_power.return_value = ({
            "success": True,
            "status": "stale",
            "source": {"is_stale": True, "data_age_minutes": 42},
            "current": {
                "battery_soc_pct": 55,
                "solar_power_w": 1200,
                "load_power_w": 800,
            },
            "summary": {"headline": "Power data is stale."},
        }, 200)

        result, status = handle_message({
            "text": "what is the power like now",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertFalse(result["needs_clarification"])
        self.assertEqual(result["tool_used"], "power_current")
        self.assertEqual(result["risk_level"], 0)
        self.assertIn("42 minutes old", result["stale_warnings"][0])
        self.assertIn("Note:", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.tools.get_meat_planning_data")
    def test_meat_planning_warning_is_returned(self, mock_meat, _write_trace):
        mock_meat.return_value = {
            "success": True,
            "source": "pig_allocation_readiness",
            "summary": {
                "ready_now": 2,
                "next_14_days": 1,
                "next_30_days": 3,
                "fallback_abattoir": 4,
            },
        }

        result, status = handle_message({
            "text": "what pigs are ready for meat",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "meat_planning")
        self.assertIn("2 ready now", result["answer"])
        self.assertEqual(result["stale_warnings"], [])
        self.assertIn("read-only planning", result["safety_notes"][0])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.tools.get_pig_allocation_readiness_data")
    def test_pig_allocation_routes_without_write(self, mock_allocation, _write_trace):
        mock_allocation.return_value = {
            "success": True,
            "summary": {
                "total": 12,
                "buckets": {
                    "Meat Candidate": 2,
                    "Livestock Candidate": 3,
                    "Retain / Breeding Candidate": 1,
                },
            },
        }

        result, status = handle_message({
            "text": "show me pig allocation",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "pig_allocation_readiness")
        self.assertEqual(result["risk_level"], 0)
        self.assertIn("12 pigs", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    @patch("modules.oom_sakkie.tools.get_irrigation_status")
    def test_irrigation_status_is_read_only_even_for_control_phrase(self, mock_irrigation, _write_trace):
        mock_irrigation.return_value = ({
            "success": True,
            "status": "ok",
            "safety": {"read_only": True, "can_control": False, "hardware_commands_enabled": False},
            "current": {"status": "IDLE", "zone_id": "Z1", "zone_name": "Zone 1"},
            "today": {"done_count": 2, "next_zone_id": "Z2", "next_zone_name": "Zone 2"},
            "operator_summary": {"headline": "Irrigation has a plan for today.", "notes": []},
        }, 200)

        result, status = handle_message({
            "text": "start irrigation",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "irrigation_status")
        self.assertEqual(result["risk_level"], 0)
        self.assertEqual(result["stale_warnings"], [])
        self.assertIn("read-only", result["safety_notes"][0])
        self.assertIn("No start/stop command was sent", result["answer"])

    @patch("modules.oom_sakkie.service.write_trace", return_value={"stored": False, "status": "test"})
    def test_mixed_action_and_read_tool_adds_safety_note(self, _write_trace):
        result, status = handle_message({
            "text": "send weather to John",
            "channel": "kiosk",
        })

        self.assertEqual(status, 200)
        self.assertEqual(result["tool_used"], "weather_today")
        self.assertFalse(result["needs_clarification"])
        self.assertIn("No write", result["safety_notes"][0])

    def test_trace_params_include_insert_placeholders(self):
        trace = {
            "trace_id": "OSK-test",
            "channel": "kiosk",
            "session_id": "session",
            "user_text": "what is the power doing now",
            "intent": "power_current",
            "confidence": 0.95,
            "tool_name": "power_current",
            "tool_args_json": {},
            "tool_result_summary": "summary",
            "tool_result_hash": "hash",
            "answer": "answer",
            "risk_level": 0,
            "stale_warnings_json": [],
            "safety_notes_json": [],
            "links_json": [],
        }
        params = _trace_params(trace)
        insert_sql = next(value for value in write_trace.__code__.co_consts if isinstance(value, str) and "insert into public.oom_sakkie_traces" in value)

        for key in params:
            self.assertIn(f"%({key})s", insert_sql)

    def test_trace_row_maps_select_tuple_positions_to_expected_keys(self):
        created_at = datetime(2026, 6, 7, 8, 0, tzinfo=timezone.utc)
        feedback_at = datetime(2026, 6, 7, 8, 5, tzinfo=timezone.utc)
        mapped = _trace_row((
            "OSK-row",
            "kiosk",
            "session-1",
            "question",
            "weather_today",
            0.95,
            "weather_today",
            "summary",
            "hash",
            "answer",
            0,
            ["stale"],
            ["safe"],
            [{"label": "Weather", "href": "/weather"}],
            created_at,
            "wrong_tool",
            "note",
            "Charl",
            feedback_at,
        ))

        self.assertEqual(mapped["trace_id"], "OSK-row")
        self.assertEqual(mapped["channel"], "kiosk")
        self.assertEqual(mapped["session_id"], "session-1")
        self.assertEqual(mapped["user_text"], "question")
        self.assertEqual(mapped["intent"], "weather_today")
        self.assertEqual(mapped["confidence"], 0.95)
        self.assertEqual(mapped["tool_name"], "weather_today")
        self.assertEqual(mapped["tool_result_summary"], "summary")
        self.assertEqual(mapped["tool_result_hash"], "hash")
        self.assertEqual(mapped["answer"], "answer")
        self.assertEqual(mapped["risk_level"], 0)
        self.assertEqual(mapped["stale_warnings"], ["stale"])
        self.assertEqual(mapped["safety_notes"], ["safe"])
        self.assertEqual(mapped["links"], [{"label": "Weather", "href": "/weather"}])
        self.assertEqual(mapped["created_at"], created_at.isoformat())
        self.assertEqual(mapped["latest_feedback"]["feedback_type"], "wrong_tool")
        self.assertEqual(mapped["latest_feedback"]["notes"], "note")
        self.assertEqual(mapped["latest_feedback"]["reviewed_by"], "Charl")
        self.assertEqual(mapped["latest_feedback"]["created_at"], feedback_at.isoformat())

    def test_append_only_migration_locks_trace_tables(self):
        migration = Path("supabase/migrations/202606060004_lock_oom_sakkie_trace_append_only.sql").read_text(encoding="utf-8")

        self.assertIn("prevent_oom_sakkie_trace_mutation", migration)
        self.assertIn("before update on public.oom_sakkie_traces", migration)
        self.assertIn("before delete on public.oom_sakkie_traces", migration)
        self.assertIn("before update on public.oom_sakkie_trace_feedback", migration)
        self.assertIn("before delete on public.oom_sakkie_trace_feedback", migration)
        self.assertIn("append-only", migration)

    def test_append_only_triggers_block_updates_when_database_url_is_configured(self):
        database_url = os.getenv("DATABASE_URL", "").strip()
        if not database_url:
            self.skipTest("DATABASE_URL not configured for append-only integration test")
        try:
            import psycopg
        except ImportError:
            self.skipTest("psycopg not installed")

        trace_id = build_trace_id()
        feedback_id = build_feedback_id(trace_id, "correct")
        trace = {
            "trace_id": trace_id,
            "channel": "test",
            "session_id": "append-only-test",
            "user_text": "append only trigger test",
            "intent": "test",
            "confidence": 1.0,
            "tool_name": "test_tool",
            "tool_args_json": {},
            "tool_result_summary": "integration test row",
            "tool_result_hash": hash_tool_result({"test": True}),
            "answer": "integration test answer",
            "risk_level": 0,
            "stale_warnings_json": [],
            "safety_notes_json": [],
            "links_json": [],
        }
        stored = write_trace(trace, database_url=database_url)
        if not stored.get("stored"):
            self.skipTest(f"trace insert unavailable: {stored.get('status')}")

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.oom_sakkie_trace_feedback (
                        feedback_id, trace_id, feedback_type, notes, reviewed_by, channel, created_at
                    )
                    values (%s, %s, 'correct', 'append-only integration test', 'unittest', 'test', now())
                    """,
                    (feedback_id, trace_id),
                )
                connection.commit()
                with self.assertRaises(Exception) as trace_update:
                    cursor.execute(
                        "update public.oom_sakkie_traces set answer = answer where trace_id = %s",
                        (trace_id,),
                    )
                connection.rollback()
                self.assertIn("append-only", str(trace_update.exception).lower())

        with psycopg.connect(database_url, connect_timeout=10) as connection:
            with connection.cursor() as cursor:
                with self.assertRaises(Exception) as feedback_update:
                    cursor.execute(
                        "update public.oom_sakkie_trace_feedback set notes = notes where feedback_id = %s",
                        (feedback_id,),
                    )
                connection.rollback()
                self.assertIn("append-only", str(feedback_update.exception).lower())

    def test_trace_list_not_configured_is_safe(self):
        result, status = list_recent_traces(database_url="")

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["traces"], [])

    def test_review_advisor_trace_list_not_configured_is_safe(self):
        result, status = list_review_advisor_traces(database_url="")

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")
        self.assertEqual(result["issue_traces"], [])
        self.assertEqual(result["unreviewed_traces"], [])

    @patch.dict("sys.modules", {"psycopg": Mock()})
    def test_review_advisor_trace_list_uses_combined_ranked_query(self):
        import sys

        executed = {}
        cursor = Mock()
        cursor.fetchall.return_value = []
        cursor.__enter__ = Mock(return_value=cursor)
        cursor.__exit__ = Mock(return_value=False)
        connection = Mock()
        connection.cursor.return_value = cursor
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=False)
        sys.modules["psycopg"].connect.return_value = connection

        def capture_execute(sql, params):
            executed["sql"] = sql
            executed["params"] = params

        cursor.execute.side_effect = capture_execute

        result, status = list_review_advisor_traces(
            limit=12,
            channel="kiosk",
            days=14,
            database_url="postgresql://example",
        )

        query = executed["sql"].lower()

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["days"], 14)
        self.assertIn("union all", query)
        self.assertIn("row_number() over", query)
        self.assertIn("partition by queue_kind", query)
        self.assertIn("t.created_at >= now()", query)
        self.assertEqual(executed["params"]["channel"], "kiosk")
        self.assertEqual(executed["params"]["limit"], 12)
        self.assertEqual(executed["params"]["days"], 14)

    def test_trace_feedback_rejects_invalid_type_before_db(self):
        result, status = record_trace_feedback(
            "OSK-TEST",
            {"feedback_type": "please_make_it_spicy"},
            database_url="postgresql://should-not-be-used",
        )

        self.assertEqual(status, 400)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "invalid_feedback_type")
        self.assertEqual(result["allowed_feedback_types"], sorted(FEEDBACK_TYPES))

    def test_trace_feedback_not_configured_is_safe(self):
        result, status = record_trace_feedback(
            "OSK-TEST",
            {"feedback_type": "correct", "notes": "worked"},
            database_url="",
        )

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

    def test_review_summary_not_configured_is_safe(self):
        result, status = get_trace_review_summary(database_url="")

        self.assertEqual(status, 503)
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "not_configured")

    def test_review_filter_allows_known_values_only(self):
        self.assertEqual(_review_filter("all"), "all")
        self.assertEqual(_review_filter("reviewed"), "reviewed")
        self.assertEqual(_review_filter("unreviewed"), "unreviewed")
        self.assertEqual(_review_filter("issues"), "issues")
        self.assertEqual(_review_filter("surprise"), "all")

    def test_trace_list_where_clause_combines_review_and_search(self):
        clause = _trace_list_where_clause("issues", True)

        self.assertIn("feedback_type is not null", clause)
        self.assertIn("feedback_type <> 'correct'", clause)
        self.assertIn("user_text", clause)
        self.assertIn("answer", clause)
        self.assertIn("tool_name", clause)
        self.assertIn("trace_id", clause)


if __name__ == "__main__":
    unittest.main()
