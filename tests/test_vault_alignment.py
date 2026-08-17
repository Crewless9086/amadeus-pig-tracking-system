import tempfile
import unittest
from pathlib import Path

from modules.charlie.vault_alignment import (
    PRINCIPAL_AGENT_DOCS,
    REQUIRED_CURRENT_DOCS,
    REQUIRED_MARKERS,
    evaluate_vault_alignment,
)


class VaultAlignmentTests(unittest.TestCase):
    def test_repository_alignment_passes(self):
        result = evaluate_vault_alignment()
        self.assertTrue(result["passed"], result["findings"])

    def test_missing_continuous_contract_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative in set(REQUIRED_CURRENT_DOCS) | set(PRINCIPAL_AGENT_DOCS.values()) | set(REQUIRED_MARKERS):
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("\n".join(REQUIRED_MARKERS.get(relative, ())), encoding="utf-8")
            active = root / "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md"
            active.parent.mkdir(parents=True, exist_ok=True)
            active.write_text("\n".join(REQUIRED_CURRENT_DOCS), encoding="utf-8")
            result = evaluate_vault_alignment(root)
            self.assertFalse(result["passed"])
            self.assertTrue(any("lacks continuous contract" in item for item in result["findings"]))


if __name__ == "__main__":
    unittest.main()
