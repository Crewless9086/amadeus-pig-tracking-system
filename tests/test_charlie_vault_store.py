import unittest

from modules.charlie import vault_store


class FakeCursor:
    def __init__(self, rows=None, table_columns=None):
        self.rows = rows or []
        self.table_columns = table_columns or {}
        self.current_rows = self.rows
        self.calls = []

    def execute(self, sql, params=None):
        self.calls.append((sql, params or {}))
        if "information_schema.columns" in sql:
            table_name = (params or {}).get("table_name", "")
            self.current_rows = [(name,) for name in self.table_columns.get(table_name, [])]
        else:
            self.current_rows = self.rows

    def fetchall(self):
        return self.current_rows

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeConnection:
    MODERN_ARTIFACT_COLUMNS = {
        "artifact_id",
        "mission_id",
        "project_id",
        "artifact_type",
        "title",
        "summary",
        "content_json",
        "source_refs",
        "confidence",
        "created_by_agent",
        "created_at",
    }

    def __init__(self, rows=None, table_columns=None):
        self.cursor_obj = FakeCursor(
            rows=rows,
            table_columns=table_columns or {"charlie_vault_artifacts": self.MODERN_ARTIFACT_COLUMNS},
        )

    def cursor(self):
        return self.cursor_obj

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class CharlieVaultStoreTests(unittest.TestCase):
    def test_vault_tables_health_reports_all_tables_present(self):
        rows = [(name,) for name in vault_store.VAULT_TABLES]
        connection = FakeConnection(rows=rows)

        result, status = vault_store.vault_tables_health(
            database_url="postgresql://example",
            connect_factory=lambda _url: connection,
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        self.assertEqual(result["missing_tables"], [])

    def test_write_handoff_report_uses_normalized_table(self):
        connection = FakeConnection()
        report = {
            "mission_id": "MISSION-1",
            "agent": "builder",
            "stage": "built",
            "pass_fail_status": "pass",
            "validation": {"valid": True},
        }

        result, status = vault_store.write_handoff_report(
            report,
            database_url="postgresql://example",
            connect_factory=lambda _url: connection,
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        sql, params = connection.cursor_obj.calls[-1]
        self.assertIn("charlie_handoff_reports", sql)
        self.assertEqual(params["mission_id"], "MISSION-1")
        self.assertEqual(params["agent"], "builder")

    def test_write_agent_run_uses_normalized_table(self):
        connection = FakeConnection()

        result, status = vault_store.write_agent_run(
            "MISSION-1",
            "tester",
            {
                "execution_id": "EXEC-1",
                "attempt": 1,
                "status": "complete",
                "started_at": "2026-07-01T10:00:00+00:00",
                "updated_at": "2026-07-01T10:05:00+00:00",
                "token_usage": {"input": 100},
                "tool_calls": [{"tool": "node --check"}],
            },
            database_url="postgresql://example",
            connect_factory=lambda _url: connection,
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        sql, params = connection.cursor_obj.calls[-1]
        self.assertIn("charlie_agent_runs", sql)
        self.assertEqual(params["mission_id"], "MISSION-1")
        self.assertEqual(params["agent"], "tester")
        self.assertEqual(params["status"], "complete")

    def test_write_income_stream_review_requires_mission_id(self):
        result, status = vault_store.write_income_stream_review("", {})

        self.assertEqual(status, 400)
        self.assertFalse(result["success"])

    def test_list_artifacts_filters_by_type(self):
        connection = FakeConnection(rows=[
            (
                "ARTIFACT-1",
                "MISSION-1",
                "charlie_core",
                "charlie_improvement_proposal",
                "Improve tests",
                "Tighten tests",
                {"label": "charlie_self_improvement"},
                [],
                "high",
                "charlie_improvement_analyst",
                "2026-07-01T10:00:00+00:00",
            )
        ])

        result, status = vault_store.list_artifacts(
            artifact_type="charlie_improvement_proposal",
            database_url="postgresql://example",
            connect_factory=lambda _url: connection,
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        sql, params = connection.cursor_obj.calls[-1]
        self.assertIn("charlie_vault_artifacts", sql)
        self.assertIn("artifact_type = %(artifact_type)s", sql)
        self.assertEqual(params["artifact_type"], "charlie_improvement_proposal")
        self.assertEqual(result["artifacts"][0]["content"]["label"], "charlie_self_improvement")

    def test_update_artifact_content_updates_json_only(self):
        connection = FakeConnection(rows=[("ARTIFACT-1",)])

        result, status = vault_store.update_artifact_content(
            "ARTIFACT-1",
            {"status": "approved", "label": "charlie_self_improvement"},
            database_url="postgresql://example",
            connect_factory=lambda _url: connection,
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        sql, params = connection.cursor_obj.calls[-1]
        self.assertIn("update public.charlie_vault_artifacts", sql)
        self.assertEqual(params["artifact_id"], "ARTIFACT-1")
        self.assertIn("charlie_self_improvement", params["content_json"])

    def test_write_artifact_supports_legacy_artifact_schema(self):
        legacy_columns = {
            "artifact_id",
            "mission_id",
            "project_id",
            "agent_name",
            "artifact_type",
            "title",
            "summary",
            "artifact_path",
            "content_json",
            "created_at",
        }
        connection = FakeConnection(table_columns={"charlie_vault_artifacts": legacy_columns})

        result, status = vault_store.write_artifact(
            "MISSION-1",
            "charlie_improvement_proposal",
            {
                "label": "charlie_self_improvement",
                "confidence": "high",
                "source_refs": [{"mission_id": "MISSION-1"}],
            },
            title="Improve gates",
            agent="charlie_improvement_analyst",
            database_url="postgresql://example",
            connect_factory=lambda _url: connection,
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        sql, params = connection.cursor_obj.calls[-1]
        self.assertIn("agent_name", sql)
        self.assertNotIn("source_refs", sql)
        self.assertNotIn("confidence", sql)
        self.assertEqual(params["created_by_agent"], "charlie_improvement_analyst")

    def test_list_artifacts_supports_legacy_artifact_schema(self):
        legacy_columns = {
            "artifact_id",
            "mission_id",
            "project_id",
            "agent_name",
            "artifact_type",
            "title",
            "summary",
            "artifact_path",
            "content_json",
            "created_at",
        }
        connection = FakeConnection(
            rows=[
                (
                    "ARTIFACT-1",
                    "MISSION-1",
                    "charlie_core",
                    "charlie_improvement_proposal",
                    "Improve gates",
                    "Tighten gates",
                    {"label": "charlie_self_improvement"},
                    [],
                    "",
                    "charlie_improvement_analyst",
                    "2026-07-01T10:00:00+00:00",
                )
            ],
            table_columns={"charlie_vault_artifacts": legacy_columns},
        )

        result, status = vault_store.list_artifacts(
            artifact_type="charlie_improvement_proposal",
            database_url="postgresql://example",
            connect_factory=lambda _url: connection,
        )

        self.assertEqual(status, 200)
        self.assertTrue(result["success"])
        sql, _params = connection.cursor_obj.calls[-1]
        self.assertIn("agent_name as created_by_agent", sql)
        self.assertIn("'[]'::jsonb as source_refs", sql)
        self.assertEqual(result["artifacts"][0]["created_by_agent"], "charlie_improvement_analyst")


if __name__ == "__main__":
    unittest.main()
