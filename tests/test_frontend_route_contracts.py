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

    def test_weight_form_has_top_save_action_and_blocks_weight_wheel(self):
        template = Path("templates/pig-weights.html").read_text(encoding="utf-8")
        css = Path("static/css/main.css").read_text(encoding="utf-8")
        js = Path("static/js/pigWeights.form.js").read_text(encoding="utf-8")

        self.assertIn('class="form-actions form-actions-primary"', template)
        self.assertIn('id="submit_button"', template)
        self.assertIn('id="submit_button_bottom"', template)
        self.assertIn('class="no-spinner"', template)
        self.assertIn("input.no-spinner::-webkit-inner-spin-button", css)
        self.assertIn('weightKgInput.addEventListener("wheel"', js)
        self.assertIn("event.preventDefault()", js)
        self.assertIn("submitButtons.forEach", js)

    def test_dashboard_shows_monthly_sales_stream_breakdown(self):
        js = Path("static/js/dashboard.js").read_text(encoding="utf-8")

        self.assertIn("Sales This Month", js)
        self.assertIn("livestock_sold_this_month", js)
        self.assertIn("slaughter_sold_this_month", js)
        self.assertIn("meat_sold_this_month", js)

    def test_print_sheets_page_is_read_only_weight_capture_sheet(self):
        template = Path("templates/print-sheets.html").read_text(encoding="utf-8")
        js = Path("static/js/printSheets.js").read_text(encoding="utf-8")

        self.assertIn("Weekly Weight Capture Sheet", template)
        self.assertIn("Previous Weight Date", template)
        self.assertIn("Previous Weight", template)
        self.assertIn("New Weight", template)
        self.assertIn("Current Pen", template)
        self.assertIn("New Pen", template)
        self.assertIn("Notes", template)
        self.assertNotIn("Pig_ID", template)
        self.assertIn('fetch("/api/pig-weights/pigs")', js)
        self.assertIn('fetch("/api/pig-weights/pens")', js)
        self.assertNotIn("method: \"POST\"", js)
        self.assertIn("window.print", js)
        self.assertIn("multiple", template)


if __name__ == "__main__":
    unittest.main()
