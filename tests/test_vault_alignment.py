import tempfile
import unittest
from pathlib import Path

from modules.charlie.vault_alignment import (
    AUTHORITY_ROUTING_MARKERS,
    PRINCIPAL_AGENT_DOCS,
    REQUIRED_CURRENT_DOCS,
    REQUIRED_MARKERS,
    evaluate_vault_alignment,
)

from modules.charlie.vault_retrieval import COMMON_MANDATORY_DOCS, MANDATORY_MISSION_PACKS


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

    def _current_contract_fixture(self, root):
        repository = Path(__file__).resolve().parents[1]
        mandatory = set(COMMON_MANDATORY_DOCS) | {path for paths in MANDATORY_MISSION_PACKS.values() for path in paths}
        paths = mandatory | set(REQUIRED_CURRENT_DOCS) | set(PRINCIPAL_AGENT_DOCS.values()) | set(REQUIRED_MARKERS) | set(AUTHORITY_ROUTING_MARKERS)
        for relative in paths:
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            text = (repository / relative).read_text(encoding="utf-8")
            # Current evidence may change without erasing the continuous contract.
            text = text.replace("Current honest state", "Historical implementation assessment")
            text = text.replace("continuous manager loop not proven", "see current evidence")
            text = text.replace("customer dispatch authority disabled", "see current evidence")
            destination.write_text(text, encoding="utf-8")
        (root / "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md").write_text(
            "# Control Tower Mission Register\nStatus: current-state evidence; non-doctrine\n"
            "Coordinator: current coordinator\nMission: existing mission\n"
            "History: retained separately; decisions require fresh evidence.\n", encoding="utf-8")
        active = root / "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md"
        active.write_text("\n".join(AUTHORITY_ROUTING_MARKERS["docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md"])
                          + "\n" + "\n".join(f"`{path}`" for path in sorted(paths)), encoding="utf-8")
        return mandatory

    def test_compact_register_and_changed_runtime_status_preserve_durable_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._current_contract_fixture(root)
            result = evaluate_vault_alignment(root)
        self.assertTrue(result["passed"], result["findings"])

    def test_each_mandatory_path_is_checked_not_only_first_ranked_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            mandatory = self._current_contract_fixture(root)
            for relative in sorted(mandatory):
                with self.subTest(path=relative):
                    path = root / relative
                    content = path.read_bytes()
                    path.unlink()
                    result = evaluate_vault_alignment(root)
                    self.assertFalse(result["passed"])
                    self.assertIn(f"mandatory mission-pack document missing or unreadable: {relative}", result["findings"])
                    path.write_bytes(content)

    def test_historical_or_unreadable_pack_cannot_satisfy_alignment(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._current_contract_fixture(root)
            relative = MANDATORY_MISSION_PACKS["rootline"][1]
            path = root / relative
            for content in (b"Status: historical\nFormer authority", b"\xff", b"   "):
                with self.subTest(content=content):
                    path.write_bytes(content)
                    result = evaluate_vault_alignment(root)
                    self.assertFalse(result["passed"])
                    self.assertTrue(any("mandatory mission-pack document" in issue and relative in issue for issue in result["findings"]))

    def test_history_cannot_replace_current_mission_register(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._current_contract_fixture(root)
            (root / "docs/06-operations/CONTROL_TOWER_MISSION_REGISTER.md").write_text("", encoding="utf-8")
            result = evaluate_vault_alignment(root)
        self.assertFalse(result["passed"])
        self.assertTrue(any("required current document missing or unreadable" in issue for issue in result["findings"]))

    def test_archive_links_require_an_explicit_non_doctrine_evidence_section(self):
        relative = "docs/99-archive/control-tower/20260919/retained.md"
        cases = (
            ("labelled evidence", "Current-state evidence, never reusable doctrine:\n"
             f"The register preserves older state under `{relative}`.\n"
             "Neither history nor receipts can revive old priorities or clear holds.", True),
            ("evidence heading", "## Current-state evidence, never reusable doctrine\n"
             f"- `{relative}`", True),
            ("current authority", "## Common Mandatory Governance Pack\n"
             f"- `{relative}`", False),
            ("unclassified history claim", f"Historical evidence only: `{relative}`", False),
            ("next heading resets evidence", "Current-state evidence, never reusable doctrine:\n"
             "History is retained.\n## Current authority\n"
             f"- `{relative}`", False),
            ("next label resets evidence", "Current-state evidence, never reusable doctrine:\n"
             "History is retained.\nRegistered cross-system controlling exceptions:\n"
             f"- `{relative}`", False),
            ("duplicate authority remains invalid", "Current-state evidence, never reusable doctrine:\n"
             f"- `{relative}`\n## Common Mandatory Governance Pack\n- `{relative}`", False),
        )
        for name, references, allowed in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self._current_contract_fixture(root)
                archived = root / relative
                archived.parent.mkdir(parents=True, exist_ok=True)
                archived.write_text("Status: historical evidence; non-doctrine\n", encoding="utf-8")
                active = root / "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md"
                active.write_text(active.read_text(encoding="utf-8") + "\n" + references, encoding="utf-8")
                result = evaluate_vault_alignment(root)
                self.assertEqual(result["passed"], allowed, result["findings"])
                self.assertIn(relative, result["checked_files"])
                if not allowed:
                    self.assertIn(f"archived document exposed as current authority: {relative}", result["findings"])

    def test_explicit_history_link_still_requires_preserved_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._current_contract_fixture(root)
            relative = "docs/99-archive/missing-history.md"
            active = root / "docs/09-vault-brain/10-source-map/ACTIVE_DOCS_SOURCE_MAP.md"
            active.write_text(active.read_text(encoding="utf-8") +
                              "\nCurrent-state evidence, never reusable doctrine:\n" +
                              f"- `{relative}`\n", encoding="utf-8")
            result = evaluate_vault_alignment(root)
        self.assertFalse(result["passed"])
        self.assertIn(f"active source map target missing: {relative}", result["findings"])
        self.assertNotIn(f"archived document exposed as current authority: {relative}", result["findings"])


if __name__ == "__main__":
    unittest.main()
