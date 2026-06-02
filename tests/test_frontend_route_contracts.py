from pathlib import Path
import unittest


class FrontendRouteContractTests(unittest.TestCase):
    def test_litter_detail_uses_existing_litter_api_route(self):
        js = Path("static/js/litterDetail.js").read_text(encoding="utf-8")
        template = Path("templates/litter-detail.html").read_text(encoding="utf-8")

        self.assertIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}", js)
        self.assertNotIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}/detail", js)
        self.assertIn('id="litter_attention_panel"', template)
        self.assertIn("litter-detail-shell", template)
        self.assertIn("litter-detail-page", template)
        self.assertIn("litter-workspace", template)
        self.assertIn("litter-summary-grid", template)
        self.assertIn("litter-side-column", template)
        self.assertIn('id="mark_weaned_form"', template)
        self.assertIn('id="mark_weaned_button"', template)
        self.assertIn('id="newborn_health_form"', template)
        self.assertIn('id="newborn_health_antiparasitic"', template)
        self.assertIn('id="newborn_health_deworming"', template)
        self.assertIn('id="newborn_health_preview_button"', template)
        self.assertIn('id="newborn_health_apply_button"', template)
        self.assertIn('id="litter_outcome_slaughtered"', template)
        self.assertIn("renderLifecycleOutcomes", js)
        self.assertIn("litter.lifecycle_outcomes", js)
        self.assertIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}/mark-weaned", js)
        self.assertIn("/api/pig-weights/litter/${encodeURIComponent(litterId)}/newborn-health", js)
        self.assertIn("antiparasitic_product_id", js)
        self.assertIn("deworming_product_id", js)
        self.assertIn('attention.action_type === "record_litter_newborn_health"', js)
        self.assertIn('method: "POST"', js)
        self.assertIn('attention.action_type === "mark_weaned"', js)
        self.assertNotIn('attention.action_type === "review_or_wean"', js)
        self.assertIn(".litter-detail-page", Path("static/css/main.css").read_text(encoding="utf-8"))

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

    def test_mating_board_uses_section_aware_sorting(self):
        js = Path("static/js/matings.js").read_text(encoding="utf-8")

        self.assertIn("action_priority", js)
        self.assertIn("actualFarrowing || expectedFarrowing", js)
        self.assertIn(".sort(compareMatingRecords)", js)
        self.assertIn('a.action_section === "needs_action"', js)
        self.assertIn('a.action_section === "closed"', js)
        self.assertIn('compareByActionDate(a, b, "desc")', js)
        self.assertIn("isEligibleForAddLitter", js)
        self.assertIn('/master/add-litter?mating_id=', js)

    def test_add_litter_can_prefill_from_mating_query_param(self):
        js = Path("static/js/addLitter.js").read_text(encoding="utf-8")

        self.assertIn("prefillMatingFromUrl", js)
        self.assertIn("new URLSearchParams(window.location.search)", js)
        self.assertIn('params.get("mating_id")', js)
        self.assertIn("handleMatingSelect({ target: select })", js)

    def test_pig_detail_has_controlled_lifecycle_death_action(self):
        template = Path("templates/pig-detail.html").read_text(encoding="utf-8")
        js = Path("static/js/pigDetail.js").read_text(encoding="utf-8")

        self.assertIn('id="lifecycle_action_panel"', template)
        self.assertIn('id="lifecycle_death_form"', template)
        self.assertIn('id="detail_exit_reason"', template)
        self.assertIn('id="detail_carcass_weight"', template)
        self.assertIn("Record Death / Removal", template)
        self.assertIn("/api/pig-weights/pig/${encodeURIComponent(currentPigId)}/lifecycle/death", js)
        self.assertIn('method: "POST"', js)
        self.assertIn("pig.status === \"Active\" && pig.on_farm === \"Yes\"", js)
        self.assertIn("renderLifecycleHistory", js)
        self.assertIn("pig.lifecycle", js)
        self.assertIn("window.confirm", js)

    def test_breeding_analytics_page_is_read_only_kpi_overview(self):
        template = Path("templates/breeding-analytics.html").read_text(encoding="utf-8")
        js = Path("static/js/breedingAnalytics.js").read_text(encoding="utf-8")
        matings_template = Path("templates/matings.html").read_text(encoding="utf-8")

        self.assertIn("Breeding Analytics", template)
        self.assertIn("Sow Performance", template)
        self.assertIn("Boar Performance", template)
        self.assertIn("/api/pig-weights/breeding-analytics", js)
        self.assertIn('/breeding-analytics/${encodeURIComponent(row.pig_id || "")}', js)
        self.assertNotIn('method: "POST"', js)
        self.assertIn("/breeding-analytics", matings_template)

    def test_breeding_analytics_detail_page_is_read_only_drill_in(self):
        template = Path("templates/breeding-analytics-detail.html").read_text(encoding="utf-8")
        js = Path("static/js/breedingAnalyticsDetail.js").read_text(encoding="utf-8")

        self.assertIn("Breeding Analytics Detail", template)
        self.assertIn('id="breeding_quality_list"', template)
        self.assertIn('id="breeding_detail_matings_body"', template)
        self.assertIn('id="breeding_detail_litters_body"', template)
        self.assertIn("breedingAnalyticsDetail.js", template)
        self.assertIn("/api/pig-weights/breeding-analytics/${encodeURIComponent(pigId)}", js)
        self.assertIn("renderQuality", js)
        self.assertIn("renderMatings", js)
        self.assertIn("renderLitters", js)
        self.assertNotIn('method: "POST"', js)

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

        for field in ["sold", "slaughtered", "dead", "removed"]:
            self.assertIn(f'id="outcome_{field}"', template)
            self.assertIn(f"lifecycle_{field}_this_month", js)
        self.assertIn("ops-outcome-strip", template)

    def test_slaughter_sale_form_uses_supabase_sales_transaction_endpoints(self):
        template = Path("templates/slaughter-sale.html").read_text(encoding="utf-8")
        js = Path("static/js/slaughterSale.js").read_text(encoding="utf-8")
        dashboard = Path("templates/dashboard.html").read_text(encoding="utf-8")

        self.assertIn("Record Slaughter Sale", template)
        self.assertIn("slaughter-page-shell", template)
        self.assertIn("slaughter-workspace", template)
        self.assertIn("slaughter-entry-column", template)
        self.assertIn("slaughter-ledger-column", template)
        self.assertIn('id="slaughter_sale_form"', template)
        self.assertIn('id="submit_slaughter_sale_top"', template)
        self.assertIn('id="slaughter_pig_rows"', template)
        self.assertIn('id="add_slaughter_pig_button"', template)
        self.assertIn('id="slaughter_batch_total"', template)
        self.assertIn('id="slaughter_search"', template)
        self.assertIn('id="slaughter_status_filter"', template)
        self.assertIn('id="slaughter_payment_filter"', template)
        self.assertIn('id="slaughter_update_panel"', template)
        self.assertIn('id="slaughter_update_form"', template)
        self.assertIn('id="update_line_total"', template)
        self.assertIn('id="update_payment_status"', template)
        self.assertIn('id="update_payment_date"', template)
        self.assertIn('id="update_carcass_weight"', template)
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
        self.assertIn("openUpdatePanel", js)
        self.assertIn("submitUpdatePayment", js)
        self.assertIn("/payment", js)
        self.assertIn("payment_date", js)
        self.assertIn("Payment date is required when payment status is Paid.", js)
        self.assertNotIn("Final batch amount for", js)
        self.assertIn('method: "PATCH"', js)
        self.assertIn("applyTransactionFilters", js)
        self.assertIn("table-subtext", js)
        self.assertIn('colspan="6"', js)
        self.assertIn("data-sale-row", js)
        self.assertIn("/sales/slaughter/${encodeURIComponent(row.dataset.saleRow)}", js)
        self.assertIn('item.sale_status === "Completed"', js)
        self.assertIn('item.payment_status === "Paid"', js)
        self.assertIn("table-action-button", js)
        self.assertIn("setSubmitting", js)
        self.assertIn("submitButtons.forEach", js)
        self.assertNotIn("/api/pig-weights/weights", js)
        self.assertNotIn("/api/master/pigs", js)
        self.assertIn("/sales/slaughter", dashboard)

    def test_slaughter_sale_detail_page_reads_one_sale(self):
        template = Path("templates/slaughter-sale-detail.html").read_text(encoding="utf-8")
        js = Path("static/js/slaughterSaleDetail.js").read_text(encoding="utf-8")

        self.assertIn("sale_detail_back", template)
        self.assertIn("sale_detail_summary", template)
        self.assertIn("sale_items_body", template)
        self.assertIn("sale_exit_confirm_form", template)
        self.assertIn("Confirm Pig Exits", template)
        self.assertIn("window.SLAUGHTER_SALE_ID", template)
        self.assertIn("/api/sales-transactions/${encodeURIComponent(saleId)}", js)
        self.assertIn("/api/sales-transactions/${encodeURIComponent(saleId)}/confirm-pig-exits", js)
        self.assertIn('method: "POST"', js)
        self.assertIn('["Completed", "Cancelled"].includes(saleStatus)', js)
        self.assertIn('paymentStatus === "Paid"', js)
        self.assertIn("window.confirm", js)
        self.assertIn("window.history.back", js)
        self.assertIn("/sales/slaughter", js)
        self.assertIn("renderItems", js)

    def test_sales_dashboard_is_transaction_overview_with_filters_and_drill_in(self):
        template = Path("templates/sales-dashboard.html").read_text(encoding="utf-8")
        js = Path("static/js/salesDashboard.js").read_text(encoding="utf-8")

        self.assertIn("Sales Overview", template)
        self.assertIn('id="sales_period_filter"', template)
        self.assertIn('id="sales_month_filter"', template)
        self.assertIn('id="sales_year_filter"', template)
        self.assertIn('id="sales_stream_filter"', template)
        self.assertIn('id="sales_transactions_body"', template)
        self.assertIn('id="sales_total_value"', template)
        self.assertIn("/api/sales-transactions?limit=100", js)
        self.assertIn("/api/pig-weights/sales-dashboard", js)
        self.assertIn("filteredTransactions", js)
        self.assertIn("renderSalesTotals", js)
        self.assertIn("data-sale-row", js)
        self.assertIn("/sales/transactions/${encodeURIComponent(row.dataset.saleRow)}", js)
        self.assertIn("selected_month", js)
        self.assertIn("selected_year", js)

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
        self.assertIn("/bulk-weights", template)

    def test_bulk_weights_page_uses_batch_preflight_and_local_draft(self):
        template = Path("templates/bulk-weights.html").read_text(encoding="utf-8")
        js = Path("static/js/bulkWeights.js").read_text(encoding="utf-8")

        self.assertIn("Bulk Weight Entry", template)
        self.assertIn("Save Draft", template)
        self.assertIn("Upload Batch", template)
        self.assertIn("Previous Weight Date", template)
        self.assertIn("New Weight", template)
        self.assertIn('fetch("/api/pig-weights/pigs")', js)
        self.assertIn('fetch("/api/pig-weights/pens")', js)
        self.assertIn("/api/pig-weights/weights-batch/preflight", js)
        self.assertIn("/api/pig-weights/weights-batch", js)
        self.assertIn("window.localStorage", js)
        self.assertIn("Blank rows will be skipped", js)


if __name__ == "__main__":
    unittest.main()
