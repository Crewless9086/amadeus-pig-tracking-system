import tempfile
import unittest
from pathlib import Path

from scripts import codex_next_steps


SAMPLE_NEXT_STEPS = """
# NEXT STEPS

## P0 - Critical
- Fix SAM live stock location replies
- Build CHARLIE conveyor belt recovery

## P1
- Improve owner cards for blocked missions

## P2
- Document meat sales launch checklist
"""


class CodexNextStepsTests(unittest.TestCase):
    def test_extracts_option_list(self):
        options = codex_next_steps.extract_options(SAMPLE_NEXT_STEPS)

        self.assertGreaterEqual(len(options), 4)
        self.assertEqual(options[0].priority, "P0")
        self.assertIn("Fix SAM", options[0].title)

    def test_writes_selected_mission_to_temp_codex_chat(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_steps = root / "NEXT_STEPS.md"
            codex_chat = root / "CODEX_CHAT.md"
            next_steps.write_text(SAMPLE_NEXT_STEPS, encoding="utf-8")

            option, archive = codex_next_steps.write_selected_mission(
                2,
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
            )

            self.assertIsNone(archive)
            self.assertIn("Build CHARLIE conveyor", option.title)
            output = codex_chat.read_text(encoding="utf-8")
            self.assertIn("## ACTIVE MISSION", output)
            self.assertIn("Build CHARLIE conveyor", output)
            self.assertIn("## FINAL REPORT", output)

    def test_does_not_delete_existing_content_without_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_steps = root / "NEXT_STEPS.md"
            codex_chat = root / "CODEX_CHAT.md"
            next_steps.write_text(SAMPLE_NEXT_STEPS, encoding="utf-8")
            codex_chat.write_text("OWNER NOTE: keep this", encoding="utf-8")

            _, archive = codex_next_steps.write_selected_mission(
                1,
                next_steps_path=next_steps,
                codex_chat_path=codex_chat,
            )

            self.assertIsNotNone(archive)
            self.assertTrue(archive.exists())
            self.assertIn("OWNER NOTE", archive.read_text(encoding="utf-8"))

    def test_rejects_invalid_option(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            next_steps = root / "NEXT_STEPS.md"
            next_steps.write_text(SAMPLE_NEXT_STEPS, encoding="utf-8")

            with self.assertRaises(ValueError):
                codex_next_steps.write_selected_mission(9, next_steps_path=next_steps, codex_chat_path=root / "chat.md")

    def test_rejects_empty_next_steps(self):
        with self.assertRaises(ValueError):
            codex_next_steps.extract_options("")


if __name__ == "__main__":
    unittest.main()

