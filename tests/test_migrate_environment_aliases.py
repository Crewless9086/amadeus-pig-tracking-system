import tempfile
import unittest
from pathlib import Path

from scripts.migrate_environment_aliases import migrate, migration_plan, parse_dotenv


class EnvironmentAliasMigrationTests(unittest.TestCase):
    def test_plan_copies_legacy_without_value_in_result_metadata(self):
        additions, equal, conflicts = migration_plan({"CHARLIE_PRIVATE_LLM_MODEL": "secretish-model"})
        self.assertEqual(additions, {"CHARLIE_LLM_MODEL": "secretish-model"})
        self.assertEqual(equal, [])
        self.assertEqual(conflicts, [])

    def test_conflict_fails_closed(self):
        additions, _equal, conflicts = migration_plan(
            {"CHARLIE_LLM_MODEL": "new", "CHARLIE_PRIVATE_LLM_MODEL": "old"}
        )
        self.assertEqual(additions, {})
        self.assertEqual(conflicts, ["CHARLIE_LLM_MODEL"])

    def test_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text("CHARLIE_PRIVATE_LLM_ENABLED=1\n", encoding="utf-8")
            before = path.read_bytes()
            result = migrate(path, backup_dir=Path(tmp) / "backups")
            self.assertFalse(result["applied"])
            self.assertEqual(path.read_bytes(), before)

    def test_apply_retains_legacy_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".env"
            path.write_text("CHARLIE_PRIVATE_LLM_ENABLED=1\n", encoding="utf-8")
            result = migrate(path, apply=True, backup_dir=root / "backups")
            values = parse_dotenv(path.read_text(encoding="utf-8"))
            self.assertTrue(result["applied"])
            self.assertEqual(values["CHARLIE_PRIVATE_LLM_ENABLED"], "1")
            self.assertEqual(values["CHARLIE_LLM_ENABLED"], "1")
            self.assertEqual(len(list((root / "backups").glob("*.bak"))), 1)

    def test_apply_refuses_any_conflict_without_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / ".env"
            path.write_text("CHARLIE_LLM_MODEL=new\nCHARLIE_PRIVATE_LLM_MODEL=old\n", encoding="utf-8")
            before = path.read_bytes()
            result = migrate(path, apply=True, backup_dir=root / "backups")
            self.assertEqual(result["conflicts"], ["CHARLIE_LLM_MODEL"])
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((root / "backups").exists())


if __name__ == "__main__":
    unittest.main()
