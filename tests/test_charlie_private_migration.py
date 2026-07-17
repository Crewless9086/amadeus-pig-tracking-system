import unittest
from pathlib import Path


class CharliePrivateMigrationTests(unittest.TestCase):
    def test_private_control_tables_and_safe_policies_exist(self):
        sql = Path("supabase/migrations/202607170002_create_charlie_private_executive_interface.sql").read_text(encoding="utf-8")
        for table in ("charlie_owner_bindings", "charlie_conversation_threads", "charlie_conversation_messages", "charlie_owner_intents", "charlie_tool_executions", "charlie_approval_bundles", "charlie_owner_preferences", "charlie_brief_subscriptions", "charlie_inbound_updates"):
            self.assertIn(table, sql)
        for forbidden in ("customer_send", "payment", "reservation", "lifecycle"):
            self.assertNotIn(f"'charlie.{forbidden}'", sql)


if __name__ == "__main__":
    unittest.main()
