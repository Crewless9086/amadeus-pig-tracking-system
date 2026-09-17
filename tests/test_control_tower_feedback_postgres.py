import os
import hashlib
import unittest
from concurrent.futures import ThreadPoolExecutor

import psycopg

from modules.charlie.control_tower_feedback import (
    ACTION, DECISION_SOURCE_KIND, SOURCE_KIND,
    handle_control_tower_feedback, process_pending_control_tower_feedback,
)
from modules.charlie.mission_store import BOOTSTRAP_PORTFOLIO_ADMISSION
from modules.charlie.private_policy import authenticate_private_action_context

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
FEEDBACK_ID = "CTF-DISPOSABLE-POSTGRES-001"
ENV = {"CHARLIE_SHADOW_CONTROL_TOWER_ENABLED": "true",
    "CHARLIE_EXECUTIVE_ENABLED": "true", "CHARLIE_TELEGRAM_BOT_TOKEN": "token",
    "CHARLIE_TELEGRAM_WEBHOOK_SECRET": "s" * 32,
    "CHARLIE_TELEGRAM_OWNER_USER_ID": "42", "CHARLIE_TELEGRAM_OWNER_CHAT_ID": "42"}
AUTH = authenticate_private_action_context(
    {"message": {"from": {"id": 42}, "chat": {"id": 42, "type": "private"}}},
    {"X-Telegram-Bot-Api-Secret-Token": "s" * 32}, "CMQ-20260813-05", ENV)


def reader(_mission_id):
    return {"mission": {"mission_id": "CMQ-20260813-05", "status": "paused",
        "metadata": {"portfolio_admission": BOOTSTRAP_PORTFOLIO_ADMISSION}}}, 200


def transaction():
    feedback = "Synthetic disposable test only."
    return {"feedback_transaction_id": FEEDBACK_ID, "terminal_identity": "CORE-test-terminal",
        "terminal_state": "released", "deployed_agent_identity": "CORE-test-worker",
        "existing_mission_id": "CMQ-20260813-05", "business_status": "WORKING",
        "evidence": {"documented": ["disposable test"], "runtime_loaded": [],
            "provider_verified": [], "physical": []}, "worktree_classification": "clean_retained",
        "collision_assessment": "none", "proposed_next_terminal": "CORE-test-terminal",
        "proposed_next_action": "CONTINUE", "proposed_continuation_prompt": "Continue test.",
        "expected_owner_visible_result": "Disposable comparison.", "confidence": 0.9,
        "reasons": ["disposable database"], "worktree_identity": "disposable@test",
        "feedback_occurred_at": "2026-08-15T10:00:00+00:00",
        "control_tower_reconciliation_id": "CTR-DISPOSABLE-001",
        "source_kind": SOURCE_KIND, "owner_pasted_feedback": feedback,
        "owner_pasted_feedback_sha256": hashlib.sha256(feedback.encode("utf-8")).hexdigest()}


@unittest.skipUnless(DATABASE_URL, "disposable PostgreSQL URL is required")
class ControlTowerFeedbackPostgresTests(unittest.TestCase):
    def setUp(self):
        self._cleanup()

    def tearDown(self):
        self._cleanup()

    def _cleanup(self):
        if not DATABASE_URL:
            return
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("delete from public.operational_events where aggregate_type=%s and aggregate_id=%s",
                ("control_tower_feedback_transaction", FEEDBACK_ID))

    def test_concurrent_feedback_proposal_decision_comparison_and_replay(self):
        feedback = {"action": ACTION, "record_type": "feedback", "transaction": transaction()}
        with ThreadPoolExecutor(max_workers=2) as pool:
            first = list(pool.map(lambda _item: handle_control_tower_feedback(feedback,
                runtime_context=AUTH, environ=ENV, database_url=DATABASE_URL,
                mission_reader=reader), range(2)))
        self.assertEqual(sorted(status for _result, status in first), [200, 201])
        proposal_cycle = process_pending_control_tower_feedback(environ=ENV,
            database_url=DATABASE_URL, mission_reader=reader)
        self.assertEqual(proposal_cycle["processed_count"], 1)
        decision_tx = transaction()
        decision_tx.pop("owner_pasted_feedback")
        decision_tx.pop("owner_pasted_feedback_sha256")
        decision_tx["source_kind"] = DECISION_SOURCE_KIND
        decision_tx["feedback_reconciliation_id"] = "CTR-DISPOSABLE-001"
        decision_tx["control_tower_reconciliation_id"] = "CTR-DISPOSABLE-DECISION-001"
        decision = {"action": ACTION, "record_type": "human_decision", "transaction": decision_tx,
            "human_decision": {"human_decision_id": "H-DISPOSABLE-001",
                "actual_next_terminal": "CORE-test-terminal", "actual_next_action": "CONTINUE",
                "actual_continuation_prompt": "Continue test.",
                "actual_owner_visible_result": "Disposable comparison."}}
        written, written_status = handle_control_tower_feedback(decision, runtime_context=AUTH,
            environ=ENV, database_url=DATABASE_URL, mission_reader=reader)
        self.assertEqual(written_status, 201)
        comparison_cycle = process_pending_control_tower_feedback(environ=ENV,
            database_url=DATABASE_URL, mission_reader=reader)
        replay_cycle = process_pending_control_tower_feedback(environ=ENV,
            database_url=DATABASE_URL, mission_reader=reader)
        self.assertEqual(comparison_cycle["processed_count"], 1)
        self.assertEqual(replay_cycle["processed_count"], 0)
        with psycopg.connect(DATABASE_URL) as connection, connection.cursor() as cursor:
            cursor.execute("select event_type,count(*) from public.operational_events where aggregate_id=%s group by event_type order by event_type", (FEEDBACK_ID,))
            self.assertEqual(cursor.fetchall(), [
                ("control_tower_feedback_recorded", 1),
                ("control_tower_human_decision_recorded", 1),
                ("shadow_control_tower_human_comparison_recorded", 1),
                ("shadow_control_tower_proposal_recorded", 1),
            ])
        self.assertEqual(written["dispatches"], 0)
        self.assertEqual(comparison_cycle["farm_writes"], 0)
