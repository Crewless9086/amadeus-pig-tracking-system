from pathlib import Path
import unittest


class FrontendRouteContractTests(unittest.TestCase):
    def test_litter_detail_uses_existing_litter_api_route(self):
        js = Path("static/js/litterDetail.js").read_text(encoding="utf-8")
        template = Path("templates/litter-detail.html").read_text(encoding="utf-8")

        self.assertIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}", js)
        self.assertNotIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}/detail", js)
        self.assertIn('id="litter_attention_panel"', template)
        self.assertIn('id="mark_weaned_form"', template)
        self.assertIn('id="mark_weaned_button"', template)
        self.assertIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}/mark-weaned", js)
        self.assertIn('method: "POST"', js)
        self.assertIn('attention.action_type === "mark_weaned"', js)
        self.assertNotIn('attention.action_type === "review_or_wean"', js)

    def test_pig_dropdowns_pad_numeric_tags_for_display(self):
        paths = [
            Path("static/js/addLitter.js"),
            Path("static/js/addMating.js"),
            Path("static/js/pigList.js"),
            Path("static/js/pigWeights.form.js"),
            Path("static/js/weightReport.js"),
        ]

        for path in paths:
            js = path.read_text(encoding="utf-8")
            with self.subTest(path=str(path)):
                self.assertIn("padStart(3", js)
                self.assertIn("formatTagNumber", js)

    def test_pig_list_uses_numeric_aware_display_order_and_search(self):
        js = Path("static/js/pigList.js").read_text(encoding="utf-8")

        self.assertIn("pigSortKey", js)
        self.assertIn("sortPigsForDisplay", js)
        self.assertIn("sortPigsForDisplay(data.pigs || [])", js)
        self.assertIn("formattedTagNumber", js)
        self.assertIn("formatTagNumber(pig.tag_number || pig.pig_id)", js)
        self.assertIn("card.href = `/pig/${encodeURIComponent(pig.pig_id)}`", js)

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

    def test_dashboard_labels_monthly_sales_as_exits_not_income(self):
        js = Path("static/js/dashboard.js").read_text(encoding="utf-8")
        template = Path("templates/dashboard.html").read_text(encoding="utf-8")

        self.assertIn("Monthly Sales", template)
        self.assertIn("Livestock Sales", template)
        self.assertIn("Slaughter Sales", template)
        self.assertNotIn('"Sales This Month"', js)
        self.assertIn("livestock_sales_this_month", js)
        self.assertIn("slaughter_sales_this_month", js)
        self.assertIn("meat_sales_this_month", js)
        self.assertIn("slaughter_sales_value_this_month", js)

    def test_dashboard_uses_wide_operational_template_and_existing_read_apis(self):
        template = Path("templates/dashboard.html").read_text(encoding="utf-8")
        js = Path("static/js/dashboard.js").read_text(encoding="utf-8")
        css = Path("static/css/main.css").read_text(encoding="utf-8")

        self.assertIn('class="ops-shell"', template)
        self.assertIn('class="ops-dashboard"', template)
        self.assertIn("Farm Operating Dashboard", template)
        self.assertIn("width: min(100%, 1640px)", css)
        self.assertIn("/api/telemetry/weather/current", js)
        self.assertIn("/api/telemetry/weather/today?date=", js)
        self.assertIn("/api/telemetry/weather/forecast?days=3", js)
        self.assertIn("/api/telemetry/power/current", js)
        self.assertIn("/api/telemetry/irrigation/status?date=", js)
        self.assertIn("/api/telemetry/rollups/daily?date=", js)
        self.assertIn("/api/pig-weights/dashboard", js)
        self.assertIn("/api/reports/daily-summary?date=", js)
        self.assertNotIn('method: "POST"', js)

    def test_dashboard_herd_breakdown_includes_all_counted_categories(self):
        template = Path("templates/dashboard.html").read_text(encoding="utf-8")
        js = Path("static/js/dashboard.js").read_text(encoding="utf-8")

        for field in [
            "sows",
            "boars",
            "gilts",
            "piglets",
            "weaners",
            "growers",
            "finishers",
        ]:
            self.assertIn(f'id="herd_{field}"', template)
            self.assertIn(f'summary.{field}', js)

    def test_slaughter_sale_form_uses_supabase_sales_transaction_endpoints(self):
        template = Path("templates/slaughter-sale.html").read_text(encoding="utf-8")
        js = Path("static/js/slaughterSale.js").read_text(encoding="utf-8")
        dashboard = Path("templates/dashboard.html").read_text(encoding="utf-8")

        self.assertIn("Record Slaughter Sale", template)
        self.assertIn('id="slaughter_sale_form"', template)
        self.assertIn('id="submit_slaughter_sale_top"', template)
        self.assertIn('id="slaughter_pig_rows"', template)
        self.assertIn('id="add_slaughter_pig_button"', template)
        self.assertIn('id="slaughter_batch_total"', template)
        self.assertIn('id="slaughter_search"', template)
        self.assertIn('id="slaughter_status_filter"', template)
        self.assertIn('id="slaughter_payment_filter"', template)
        self.assertIn('value="JC Slaghuis"', template)
        self.assertIn('value="Bartelsfontein"', template)
        self.assertIn('value="Unpaid"', template)
        self.assertIn('value="Confirmed"', template)
        self.assertIn("formatTagNumber", js)
        self.assertIn("padStart(3", js)
        self.assertIn("addPigRow", js)
        self.assertIn("duplicateSelectedPigIds", js)
        self.assertIn("slaughter-line-total", js)
        self.assertIn('fetch("/api/pig-weights/pigs")', js)
        self.assertIn('fetch("/api/sales-transactions"', js)
        self.assertIn('method: "POST"', js)
        self.assertIn('"/api/sales-transactions?sale_stream=Slaughter&limit=25"', js)
        self.assertIn("/cancel", js)
        self.assertIn("data-update-sale-id", js)
        self.assertIn("data-item-count", js)
        self.assertIn("/payment", js)
        self.assertIn("payment_date", js)
        self.assertIn("Final batch amount", js)
        self.assertIn('method: "PATCH"', js)
        self.assertIn("applyTransactionFilters", js)
        self.assertIn("setSubmitting", js)
        self.assertIn("submitButtons.forEach", js)
        self.assertNotIn("/api/pig-weights/weights", js)
        self.assertNotIn("/api/master/pigs", js)
        self.assertIn("/sales/slaughter", dashboard)

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
