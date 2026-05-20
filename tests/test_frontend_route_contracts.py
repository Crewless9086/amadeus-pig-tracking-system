from pathlib import Path
import unittest


class FrontendRouteContractTests(unittest.TestCase):
    def test_litter_detail_uses_existing_litter_api_route(self):
        js = Path("static/js/litterDetail.js").read_text(encoding="utf-8")

        self.assertIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}", js)
        self.assertNotIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}/detail", js)

    def test_pig_dropdowns_pad_numeric_tags_for_display(self):
        paths = [
            Path("static/js/addLitter.js"),
            Path("static/js/addMating.js"),
            Path("static/js/pigWeights.form.js"),
            Path("static/js/weightReport.js"),
        ]

        for path in paths:
            js = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path)):
                self.assertIn("padStart(3", js)
                self.assertIn("formatTagNumber", js)

    def test_weight_form_shows_current_pen_helper_without_changing_payload(self):
        template = Path("templates/pig-weights.html").read_text(encoding="utf-8")
        js = Path("static/js/pigWeights.form.js").read_text(encoding="utf-8")

        self.assertIn('id="current_pen_helper"', template)
        self.assertIn("updateCurrentPenHelper", js)
        self.assertIn("Current pen:", js)
        self.assertIn('moved_to_pen_id: movedToPenSelect.value || ""', js)

    def test_weight_report_has_read_only_refinement_sections(self):
        template = Path("templates/weight-report.html").read_text(encoding="utf-8")
        js = Path("static/js/weightReport.js").read_text(encoding="utf-8")

        self.assertIn("Loss Flags", template)
        self.assertIn('id="loss_flags_body"', template)
        self.assertNotIn("<th>Notes</th>", template)
        self.assertIn("duplicate-marker", js)
        self.assertIn("duplicate_same_day", js)
        self.assertIn("setDateColumnVisibility", js)

    def test_weight_form_confirms_before_saving_duplicate_weight(self):
        js = Path("static/js/pigWeights.form.js").read_text(encoding="utf-8")

        self.assertIn("response.status === 409", js)
        self.assertIn("data.duplicate_weight", js)
        self.assertIn("window.confirm", js)
        self.assertIn("allow_duplicate: true", js)

    def test_dashboard_shows_monthly_sales_stream_breakdown(self):
        js = Path("static/js/dashboard.js").read_text(encoding="utf-8")

        self.assertIn("Sales This Month", js)
        self.assertIn("livestock_sold_this_month", js)
        self.assertIn("slaughter_sold_this_month", js)
        self.assertIn("meat_sold_this_month", js)


if __name__ == "__main__":
    unittest.main()
