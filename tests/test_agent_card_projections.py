import unittest
import shutil
import tempfile
from pathlib import Path

from modules.charlie.agent_card_projection import (
    AGENT_CARD_SOURCES,
    GENERATED_MARKER,
    projection_findings,
    render_agent_card,
)


ROOT = Path(__file__).resolve().parents[1]


class AgentCardProjectionTests(unittest.TestCase):
    def test_exact_nine_cards_are_current(self):
        findings, checked = projection_findings(ROOT)
        self.assertEqual(findings, [])
        self.assertEqual(len(AGENT_CARD_SOURCES), 9)
        self.assertEqual(len(checked), 36)

    def test_every_card_is_generated_non_doctrine(self):
        for agent_id in AGENT_CARD_SOURCES:
            card = (ROOT / f"static/assets/agents/{agent_id}/agent.md").read_text(encoding="utf-8")
            self.assertEqual(card, render_agent_card(ROOT, agent_id))
            self.assertTrue(card.startswith(GENERATED_MARKER))
            self.assertIn("Status: `GENERATED / NON_DOCTRINE`", card)
            self.assertIn("This card grants no authority", card)

    def test_projection_binds_doctrine_and_asset_digests(self):
        card = render_agent_card(ROOT, "beacon")
        self.assertIn("marketing/BEACON.md", card)
        self.assertIn("beacon/agent.json", card)
        self.assertIn("Canonical doctrine SHA-256", card)
        self.assertIn("Asset metadata SHA-256", card)
        self.assertIn("Central asset registry SHA-256", card)

    def test_manual_card_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            target_root = Path(directory)
            required = {"static/assets/agents/agent_registry.json"}
            for agent_id, source in AGENT_CARD_SOURCES.items():
                required.update({
                    source,
                    f"static/assets/agents/{agent_id}/agent.json",
                    f"static/assets/agents/{agent_id}/agent.md",
                })
            for relative in required:
                target = target_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(ROOT / relative, target)
            beacon = target_root / "static/assets/agents/beacon/agent.md"
            beacon.write_text(beacon.read_text(encoding="utf-8") + "manual drift\n", encoding="utf-8")
            findings, _ = projection_findings(target_root)
            self.assertIn("agent-card projection drift: static/assets/agents/beacon/agent.md", findings)


if __name__ == "__main__":
    unittest.main()
