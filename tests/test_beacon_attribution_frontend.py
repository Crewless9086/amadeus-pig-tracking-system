import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BeaconAttributionFrontendTests(unittest.TestCase):
    def setUp(self):
        self.template = (ROOT / "templates" / "beacon-media.html").read_text(encoding="utf-8")
        self.script = (ROOT / "static" / "js" / "beaconMedia.js").read_text(encoding="utf-8")
        self.styles = (ROOT / "static" / "css" / "beaconMedia.css").read_text(encoding="utf-8")

    def test_attribution_panel_exposes_read_only_summary_and_authority_boundary(self):
        for marker in (
            "beacon_attribution_title", "beacon_attribution_attributed", "beacon_attribution_ambiguous",
            "beacon_attribution_unmatched", "beacon_attribution_qualified", "beacon_attribution_lost",
            "Read-only projection", "Completed, paid revenue is separated by currency",
        ):
            self.assertIn(marker, self.template)

    def test_frontend_handles_loading_empty_error_malformed_and_ambiguous_states(self):
        for marker in (
            "setAttributionLoading", "No attributed evidence", "renderAttributionError",
            'attribution.status === "malformed_evidence"', 'data-status="${escapeHtml(safe(row.status, "unmatched"))}"',
            "candidate_lead_ids", "No inferred revenue",
        ):
            self.assertIn(marker, self.script)

    def test_attribution_endpoint_and_responsive_styles_are_wired(self):
        self.assertIn('fetchJson("/api/beacon/sam-attribution")', self.script)
        self.assertIn("beacon-attribution-summary", self.styles)
        self.assertIn("beacon-attribution-row", self.styles)
        self.assertIn("grid-template-columns: 1fr", self.styles)


if __name__ == "__main__":
    unittest.main()
