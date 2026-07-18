import unittest
from pathlib import Path


class CharlieExecutiveDoctrineTests(unittest.TestCase):
    def test_private_executive_and_core_boundaries_are_locked(self):
        identity = Path("docs/09-vault-brain/01-identity/CHARLIE.md").read_text(encoding="utf-8")
        core = Path("docs/09-vault-brain/01-identity/CHARLIE_CORE.md").read_text(encoding="utf-8")
        plan = Path("docs/06-operations/CHARLIE_PRIVATE_EXECUTIVE_MASTER_PLAN.md").read_text(encoding="utf-8")
        self.assertIn("CHARLIE may not write code", identity)
        self.assertIn("CORE executes missions. CHARLIE supervises CORE.", core)
        self.assertIn("Supabase operational records remain authoritative", plan)
        self.assertIn("CHARLIE does not write code", plan)


if __name__ == "__main__":
    unittest.main()
