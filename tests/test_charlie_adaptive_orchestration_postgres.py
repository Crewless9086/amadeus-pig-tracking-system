import json
import os
import unittest
import uuid
from unittest.mock import patch

import psycopg

from modules.charlie.mission_store import (
    build_mission_review_packet,
    consume_final_agent_artifact,
    get_mission,
    mission_status_summary,
    record_mission,
)


PRODUCTION_T0_TEXT = (
    "Perform a read-only inventory and report of "
    "docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md. Inspect only. "
    "Do not edit files, write the repository, invoke product routes, contact "
    "customers, perform business actions, deploy, publish, migrate, or control "
    "hardware. Report the documented adaptive orchestration tier and authority "
    "boundary with source evidence."
)


class CharlieAdaptiveOrchestrationPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = os.getenv("DATABASE_URL", "").strip()
        if not cls.database_url:
            raise unittest.SkipTest(
                "DATABASE_URL not configured for disposable PostgreSQL orchestration tests"
            )
        with psycopg.connect(cls.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists public.charlie_missions (
                        mission_id text primary key,
                        status text not null,
                        source text,
                        source_message_id text,
                        telegram_user_id text,
                        telegram_chat_id text,
                        raw_text text,
                        title text,
                        urgency text,
                        mission_type text,
                        approval_level text,
                        selected_next_step text,
                        owner_decision text,
                        codex_chat_write_status text,
                        metadata_json jsonb not null default '{}'::jsonb,
                        created_at timestamptz not null default now(),
                        updated_at timestamptz not null default now()
                    )
                    """
                )
                cursor.execute(
                    """
                    create table if not exists public.charlie_mission_events (
                        event_id text primary key,
                        mission_id text not null,
                        event_type text not null,
                        notes text,
                        metadata_json jsonb not null default '{}'::jsonb,
                        created_at timestamptz not null default now()
                    )
                    """
                )

    def setUp(self):
        self.mission_id = f"CHARLIE-T0-PG-{uuid.uuid4().hex[:20].upper()}"

    def tearDown(self):
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "delete from public.charlie_mission_events where mission_id=%s",
                    (self.mission_id,),
                )
                cursor.execute(
                    "delete from public.charlie_missions where mission_id=%s",
                    (self.mission_id,),
                )

    def test_production_shaped_t0_is_bound_and_ingested_before_completion(self):
        created, created_status = record_mission(
            {
                "mission_id": self.mission_id,
                "status": "approved",
                "title": "Controlled T0 adaptive orchestration production canary",
                "mission_type": "read-only audit",
                "approval_level": "LEVEL 1",
                "raw_text": PRODUCTION_T0_TEXT,
                "scope_summary": (
                    "Read only docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md."
                ),
                "acceptance_criteria": [
                    "Persist T0 orchestration generation",
                    "Select one source/domain agent",
                    "No Builder or repository writer",
                    "Produce a durable read-only artifact with source evidence",
                ],
                "forbidden_actions": [
                    "repository mutation",
                    "product/customer/business action",
                    "deployment",
                    "publication",
                    "migration",
                    "hardware control",
                ],
            },
            source_context={"source": "disposable_postgres_canary"},
            database_url=self.database_url,
        )
        self.assertEqual(created_status, 201, created)

        loaded, loaded_status = get_mission(
            self.mission_id, database_url=self.database_url
        )
        self.assertEqual(loaded_status, 200)
        mission = loaded["mission"]
        metadata = mission["metadata"]
        packet = metadata["orchestration"]
        self.assertEqual(packet["tier"], "T0")
        self.assertEqual(
            [row["agent"] for row in packet["selected_agents"]],
            ["source_mapper"],
        )
        self.assertEqual(
            [row["agent"] for row in mission["agent_workflow"]],
            ["source_mapper"],
        )
        self.assertEqual(packet["budgets"]["maximum_elapsed_minutes"], 20)
        self.assertTrue(metadata["orchestration_binding"]["validated"])
        self.assertEqual(metadata.get("review_packet"), None)

        artifact_text = json.dumps({
            "summary": "Read-only source inventory complete.",
            "files_inspected": [
                "docs/00-start-here/CHARLIE_CORE_AGENT_RUNNER_V2.md"
            ],
            "commands_run": ["read bounded documentation source"],
            "changed_files": [],
            "decision": "accept",
        }, sort_keys=True)
        import hashlib
        consumed, consumed_status = consume_final_agent_artifact(
            self.mission_id,
            "source_mapper",
            "T0-DISPOSABLE-EXECUTION",
            1,
            json.loads(artifact_text),
            hashlib.sha256(artifact_text.encode("utf-8")).hexdigest(),
            database_url=self.database_url,
        )
        self.assertEqual(consumed_status, 200, consumed)
        self.assertEqual(consumed["status"], "final_artifact_consumed")

        reloaded, _ = get_mission(self.mission_id, database_url=self.database_url)
        durable = reloaded["mission"]
        durable_metadata = durable["metadata"]
        self.assertEqual(durable["agent_workflow"][0]["status"], "complete")
        history = durable_metadata["review_packet"]["agent_artifact_history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(
            history[0]["artifact_identity"],
            consumed["claim"]["identity"],
        )
        self.assertEqual(
            durable_metadata["final_artifact_ingestion"]["last_claim"]["identity"],
            consumed["claim"]["identity"],
        )
        self.assertFalse(
            any(
                row["agent"] in {"builder", "evidence_reviewer", "business_reviewer"}
                for row in durable["agent_workflow"]
            )
        )

        owner_packet = build_mission_review_packet(durable)
        self.assertEqual(owner_packet["orchestration"]["tier"], "T0")
        self.assertEqual(
            owner_packet["orchestration_binding"]["identity"],
            durable_metadata["orchestration_binding"]["identity"],
        )
        summary, summary_status = mission_status_summary(
            database_url=self.database_url
        )
        self.assertEqual(summary_status, 200)
        row = next(
            item
            for item in summary["orchestration_throughput"]["missions"]
            if item["mission_id"] == self.mission_id
        )
        self.assertEqual(row["tier"], "T0")
        self.assertEqual(row["selected_agent_count"], 1)
        self.assertIsInstance(row["elapsed_seconds"], int)

    def test_packetless_legacy_duplicate_creates_and_reuses_one_replacement(self):
        legacy_id = f"CHARLIE-LEGACY-{uuid.uuid4().hex[:20].upper()}"
        raw_text = PRODUCTION_T0_TEXT
        with psycopg.connect(self.database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into public.charlie_missions (
                        mission_id, status, source, raw_text, title, urgency,
                        mission_type, approval_level, metadata_json,
                        created_at, updated_at
                    )
                    values (%s, 'in_progress', 'historical_canary', %s, %s, 'P2',
                            'read-only audit', 'LEVEL 1', %s::jsonb,
                            now() - interval '1 day', now() - interval '1 day')
                    """,
                    (
                        legacy_id,
                        raw_text,
                        "Read-only inventory of CORE adaptive orchestration documentation",
                        json.dumps({
                            "historical_evidence": {"preserved": True},
                            "execution_lease": {
                                "lease_id": "STALE-LEASE",
                                "expires_at": "2026-07-25T22:22:05+00:00",
                            },
                        }),
                    ),
                )
        mission = {
            "title": "Controlled T0 adaptive orchestration production canary",
            "mission_type": "read-only audit",
            "approval_level": "LEVEL 1",
            "raw_text": raw_text,
        }
        try:
            with patch.dict(
                os.environ,
                {"CORE_SOURCE_COMMIT": "c" * 40},
                clear=False,
            ):
                first, first_status = record_mission(
                    mission,
                    source_context={"source": "disposable_postgres_canary"},
                    database_url=self.database_url,
                )
                second, second_status = record_mission(
                    mission,
                    source_context={"source": "disposable_postgres_canary"},
                    database_url=self.database_url,
                )
            self.assertEqual(first_status, 201, first)
            self.assertEqual(first["status"], "legacy_duplicate_replacement_created")
            self.assertEqual(first["supersedes_mission_id"], legacy_id)
            self.assertEqual(second_status, 200, second)
            self.assertEqual(second["status"], "duplicate_open_mission")
            self.assertEqual(second["mission_id"], first["mission_id"])

            replacement, replacement_status = get_mission(
                first["mission_id"], database_url=self.database_url
            )
            self.assertEqual(replacement_status, 200)
            metadata = replacement["mission"]["metadata"]
            self.assertEqual(
                metadata["supersession"]["supersedes_mission_id"],
                legacy_id,
            )
            self.assertEqual(metadata["orchestration"]["tier"], "T0")
            self.assertEqual(
                [row["agent"] for row in metadata["orchestration"]["selected_agents"]],
                ["source_mapper"],
            )
            self.assertEqual(
                metadata["orchestration"]["selected_agents"][0]["allowed_mutations"],
                [],
            )
            self.assertTrue(metadata["orchestration_binding"]["validated"])

            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "select metadata_json from public.charlie_missions where mission_id = %s",
                        (legacy_id,),
                    )
                    historical = cursor.fetchone()[0]
                    cursor.execute(
                        """
                        select count(*) from public.charlie_missions
                        where metadata_json->'supersession'->>'supersedes_mission_id' = %s
                        """,
                        (legacy_id,),
                    )
                    replacement_count = cursor.fetchone()[0]
            self.assertEqual(historical["historical_evidence"], {"preserved": True})
            self.assertNotIn("orchestration", historical)
            self.assertEqual(replacement_count, 1)
        finally:
            with psycopg.connect(self.database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        delete from public.charlie_mission_events
                        where mission_id = %s
                           or mission_id in (
                               select mission_id from public.charlie_missions
                               where metadata_json->'supersession'->>'supersedes_mission_id' = %s
                           )
                        """,
                        (legacy_id, legacy_id),
                    )
                    cursor.execute(
                        """
                        delete from public.charlie_missions
                        where mission_id = %s
                           or metadata_json->'supersession'->>'supersedes_mission_id' = %s
                        """,
                        (legacy_id, legacy_id),
                    )


if __name__ == "__main__":
    unittest.main()
