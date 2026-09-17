import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

from scripts import apply_supabase_migration


MIGRATION_STEM = "202607260005_create_irrigation_daily_plans"
MIGRATION_PATH = f"supabase/migrations/{MIGRATION_STEM}.sql"


def registry(entries=None, schema_version=1):
    return {
        "schema_version": schema_version,
        "superseded_migrations": entries
        if entries is not None
        else {
            MIGRATION_STEM: {
                "status": "superseded_unapplied",
                "reason": "reviewed reason",
            }
        },
    }


class SupersededMigrationGuardTests(unittest.TestCase):
    def write_registry(self, directory, value):
        path = Path(directory) / "supersessions.json"
        path.write_text(
            value if isinstance(value, str) else json.dumps(value),
            encoding="utf-8",
        )
        return path

    def assert_rejected_before_access(
        self, *, migration=MIGRATION_PATH, registry_path=None, message=None
    ):
        psycopg = mock.Mock()
        patches = [
            mock.patch.object(sys, "argv", ["apply_supabase_migration.py", migration]),
            mock.patch.object(apply_supabase_migration, "load_dotenv"),
            mock.patch.object(apply_supabase_migration.os, "getenv"),
            mock.patch.dict(sys.modules, {"psycopg": psycopg}, clear=False),
        ]
        if registry_path is not None:
            patches.append(
                mock.patch.object(
                    apply_supabase_migration, "SUPERSESSIONS_PATH", registry_path
                )
            )
        entered = [patcher.start() for patcher in patches]
        try:
            with self.assertRaises(SystemExit) as raised:
                apply_supabase_migration.main()
        finally:
            for patcher in reversed(patches):
                patcher.stop()
        if message:
            self.assertIn(message, str(raised.exception))
        entered[1].assert_not_called()
        entered[2].assert_not_called()
        psycopg.connect.assert_not_called()

    def test_reviewed_registry_rejects_exact_migration_before_access(self):
        self.assert_rejected_before_access(message="Refusing superseded migration")

    def test_alternate_filename_casing_cannot_bypass(self):
        self.assert_rejected_before_access(
            migration="supabase/migrations/"
            "202607260005_CREATE_IRRIGATION_DAILY_PLANS.SQL",
            message="Refusing superseded migration",
        )

    def test_alternate_registry_key_casing_matches(self):
        with TemporaryDirectory() as directory:
            path = self.write_registry(
                directory,
                registry(
                    {
                        MIGRATION_STEM.upper(): {
                            "status": "superseded_unapplied",
                            "reason": "case-insensitive key",
                        }
                    }
                ),
            )
            self.assert_rejected_before_access(
                registry_path=path, message="Refusing superseded migration"
            )

    def test_duplicate_keys_differing_only_by_case_fail_closed(self):
        with TemporaryDirectory() as directory:
            path = self.write_registry(
                directory,
                registry(
                    {
                        MIGRATION_STEM: {
                            "status": "superseded_unapplied",
                            "reason": "first",
                        },
                        MIGRATION_STEM.upper(): {
                            "status": "superseded_unapplied",
                            "reason": "second",
                        },
                    }
                ),
            )
            self.assert_rejected_before_access(
                registry_path=path, message="key collision"
            )

    def test_missing_registry_fails_closed(self):
        with TemporaryDirectory() as directory:
            self.assert_rejected_before_access(
                registry_path=Path(directory) / "missing.json",
                message="missing or unreadable",
            )

    def test_unreadable_registry_fails_closed(self):
        with mock.patch.object(Path, "read_text", side_effect=PermissionError):
            self.assert_rejected_before_access(message="missing or unreadable")

    def test_empty_registry_file_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = self.write_registry(directory, "")
            self.assert_rejected_before_access(
                registry_path=path, message="registry is empty"
            )

    def test_empty_registry_object_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = self.write_registry(directory, {})
            self.assert_rejected_before_access(
                registry_path=path, message="schema_version"
            )

    def test_missing_superseded_migrations_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = self.write_registry(directory, {"schema_version": 1})
            self.assert_rejected_before_access(
                registry_path=path, message="missing superseded_migrations"
            )

    def test_empty_superseded_migrations_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = self.write_registry(directory, registry({}))
            self.assert_rejected_before_access(
                registry_path=path, message="non-empty object"
            )

    def test_absent_or_wrong_schema_version_fails_closed(self):
        cases = (
            {"superseded_migrations": registry()["superseded_migrations"]},
            registry(schema_version=2),
            registry(schema_version="1"),
            registry(schema_version=True),
        )
        for value in cases:
            with self.subTest(value=value), TemporaryDirectory() as directory:
                path = self.write_registry(directory, value)
                self.assert_rejected_before_access(
                    registry_path=path, message="schema_version"
                )

    def test_malformed_json_fails_closed(self):
        with TemporaryDirectory() as directory:
            path = self.write_registry(directory, "{not-json")
            self.assert_rejected_before_access(
                registry_path=path, message="registry is malformed"
            )

    def test_malformed_entry_status_and_reason_fail_closed(self):
        bad_entries = (
            [],
            {"status": "superseded_unapplied", "reason": "missing wrapper"},
            {MIGRATION_STEM: "not-an-object"},
            {MIGRATION_STEM: {"status": "other", "reason": "reason"}},
            {MIGRATION_STEM: {"status": 1, "reason": "reason"}},
            {
                MIGRATION_STEM: {
                    "status": "superseded_unapplied",
                    "reason": 1,
                }
            },
            {
                MIGRATION_STEM: {
                    "status": "superseded_unapplied",
                    "reason": " ",
                }
            },
            {
                f"{MIGRATION_STEM}.sql": {
                    "status": "superseded_unapplied",
                    "reason": "not a stem",
                }
            },
            {
                MIGRATION_STEM: {
                    "status": "superseded_unapplied",
                    "reason": "reason",
                    "extra": True,
                }
            },
        )
        for entries in bad_entries:
            with self.subTest(entries=entries), TemporaryDirectory() as directory:
                path = self.write_registry(directory, registry(entries))
                self.assert_rejected_before_access(registry_path=path)

    def test_unknown_top_level_registry_fields_fail_closed(self):
        with TemporaryDirectory() as directory:
            value = registry()
            value["extra"] = True
            path = self.write_registry(directory, value)
            self.assert_rejected_before_access(
                registry_path=path, message="invalid fields"
            )

    def test_path_traversal_and_noncanonical_paths_fail_before_access(self):
        paths = (
            f"supabase/migrations/../migrations/{MIGRATION_STEM}.sql",
            f"supabase/migrations/nested/{MIGRATION_STEM}.sql",
            f"scripts/{MIGRATION_STEM}.sql",
            str(
                (
                    apply_supabase_migration.REPO_ROOT
                    / "supabase"
                    / "migrations"
                    / f"{MIGRATION_STEM}.sql"
                ).resolve()
            ),
            f"supabase/migrations/{MIGRATION_STEM}.txt",
        )
        for path in paths:
            with self.subTest(path=path):
                self.assert_rejected_before_access(migration=path)

    def test_non_superseded_migration_returns_none_from_valid_registry(self):
        with TemporaryDirectory() as directory:
            path = self.write_registry(directory, registry())
            entry = apply_supabase_migration.supersession_for(
                Path("supabase/migrations/current.sql"), path
            )
        self.assertIsNone(entry)


if __name__ == "__main__":
    unittest.main()
