const { test, expect } = require("@playwright/test");

const baseURL = process.env.RIVERSDALE_VISUAL_BASE_URL || process.env.OOM_SAKKIE_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5000";

const rows = [
  {
    pig_id: "VISUAL-PIG-101", tag_number: "101", animal_type: "Grower", sex: "Male",
    readiness_bucket: "Livestock Candidate", outlet_priority: "Auction review",
    recommended_action: "Review for Riversdale auction", marketing_readiness: "Owner review",
    latest_weight_kg: 61.2, latest_weight_date: "2026-07-24", days_since_weight: 2,
    growth_class: "On Track", growth_basis: "Lifetime ADG", average_daily_gain_kg: 0.42,
    age_days: 174, current_pen_name: "Growers A", purpose: "Sale",
    health_status: "Clear", withdrawal_evidence_state: "cleared",
  },
  {
    pig_id: "VISUAL-PIG-102", tag_number: "102", animal_type: "Grower", sex: "Female",
    readiness_bucket: "Livestock Candidate", outlet_priority: "Auction review",
    recommended_action: "Review for Riversdale auction", marketing_readiness: "Owner review",
    latest_weight_kg: 58.7, latest_weight_date: "2026-07-23", days_since_weight: 3,
    growth_class: "Slow", growth_basis: "Lifetime ADG", average_daily_gain_kg: 0.31,
    age_days: 181, current_pen_name: "Growers B", purpose: "Sale",
    health_status: "Clear", withdrawal_evidence_state: "not_applicable",
  },
  {
    pig_id: "VISUAL-PIG-103", tag_number: "103", animal_type: "Grower", sex: "Male",
    readiness_bucket: "Livestock Candidate", outlet_priority: "Hold",
    recommended_action: "Verify withdrawal evidence", marketing_readiness: "Blocked",
    latest_weight_kg: 63.1, latest_weight_date: "2026-07-22", days_since_weight: 4,
    growth_class: "On Track", growth_basis: "Lifetime ADG", average_daily_gain_kg: 0.4,
    age_days: 176, current_pen_name: "Growers A", purpose: "Sale",
    health_status: "Follow-up hold", withdrawal_evidence_state: "unknown",
  },
  ...Array.from({ length: 18 }, (_, index) => ({
    pig_id: `VISUAL-PIG-${104 + index}`, tag_number: String(104 + index),
    animal_type: "Grower", sex: index % 2 ? "Female" : "Male",
    readiness_bucket: "Livestock Candidate", outlet_priority: "Auction review",
    recommended_action: "Review for Riversdale auction", marketing_readiness: "Owner review",
    latest_weight_kg: 55 + (index % 9), latest_weight_date: "2026-07-24", days_since_weight: 2,
    growth_class: index % 4 ? "On Track" : "Slow", growth_basis: "Lifetime ADG",
    average_daily_gain_kg: index % 4 ? 0.4 : 0.31, age_days: 160 + index,
    current_pen_name: `Growers ${String.fromCharCode(65 + (index % 3))}`, purpose: "Sale",
    health_status: "Clear", withdrawal_evidence_state: index % 5 ? "cleared" : "unknown",
  })),
];

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

test("Auction table selection is local and print is list-only", async ({ page, context }, testInfo) => {
  const mutationRequests = [];
  let releaseList;
  const listGate = new Promise((resolve) => { releaseList = resolve; });
  let holdList = true;
  let listItems = [
    { pig_id: "VISUAL-PIG-101", owner_note: "Check loading gate" },
    { pig_id: "VISUAL-PIG-102", owner_note: "" },
    { pig_id: "VISUAL-PIG-103", owner_note: "Listed before evidence hold" },
    { pig_id: "VISUAL-PIG-104", owner_note: "Owner inspected loading condition" },
  ];
  const selectableIds = rows
    .filter((row) => row.withdrawal_evidence_state !== "unknown" && !String(row.health_status).toLowerCase().includes("hold"))
    .map((row) => row.pig_id);

  await page.route("**/api/pig-weights/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (request.method() !== "GET") mutationRequests.push({ method: request.method(), path: url.pathname });
    if (url.pathname.endsWith("/pig-allocation-readiness")) {
      return json(route, { success: true, pigs: rows, summary: { total: rows.length, buckets: { "Livestock Candidate": 21 } }, rules: {} });
    }
    if (url.pathname.endsWith("/riversdale-auction-recommendation")) {
      return json(route, {
        success: true,
        candidate_preview: rows.map((row, index) => ({
          pig_id: row.pig_id,
          herdmaster_evidence: {
            health_status: row.health_status,
            withdrawal_evidence_state: row.withdrawal_evidence_state,
            withdrawal_clear: row.withdrawal_evidence_state === "cleared" ? "Yes" : "No",
            observed_quality: index === 0 ? "suitable" : "unknown",
            auction_review: index === 0
              ? { quality_state: "suitable", follow_up: "Recheck before loading" }
              : {},
          },
        })),
        confirmation: { auction_cycle_id: "visual-cycle-1", confirmed_date: "2026-08-05", location: "Riversdale Showgrounds" },
        owner_surface: {
          version: "riversdale_auction_owner_surface_v1", auction_operating: "Available",
          confirmation_freshness: "Fresh", confirmed_date: "2026-08-05",
          candidate_preview_count: 21, eligible_cohort_count: selectableIds.length, excluded_count: 21 - selectableIds.length,
          financials: { state: "Unknown" }, exclusion_reason_counts: { withdrawal_unknown: 1 },
          missing_evidence: ["Final preparation evidence"],
        },
      });
    }
    if (url.pathname.endsWith("/riversdale-auction-list")) {
      if (holdList) await listGate;
      return json(route, {
        success: true, auction_cycle_id: "visual-cycle-1",
        selectable_pig_ids: selectableIds,
        eligibility_tokens: Object.fromEntries(selectableIds.map(id => [id, `token-${id}`])),
        causal_heads: Object.fromEntries(listItems.map(item => [
          item.pig_id, { event_id: `event-${item.pig_id}`, decision_sequence: 1 },
        ])),
        items: listItems,
      });
    }
    if (url.pathname.endsWith("/riversdale-auction-list/events")) {
      const payload = request.postDataJSON();
      if (payload.action === "remove") listItems = listItems.filter((item) => !payload.pig_ids.includes(item.pig_id));
      return json(route, { success: true, status: `auction_list_${payload.action}_recorded` }, 201);
    }
    return json(route, { success: true });
  });

  const login = await context.request.post(`${baseURL}/owner/login`, {
    form: { owner_token: "riversdale-browser-fixture-token-000000000000", next: "/pig-allocation" },
  });
  expect(login.ok()).toBeTruthy();
  await page.goto(`${baseURL}/pig-allocation`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#allocation_body tr")).toHaveCount(21);
  await expect(page.locator("#allocation_table_heading")).toHaveText("Readiness Table");
  await expect(page.locator("#riversdale_candidate_review")).toHaveCount(0);
  await expect(page.locator(".allocation-table")).toHaveCount(1);
  await expect(page.locator("#auction_print_list")).toBeHidden();
  await page.screenshot({ path: testInfo.outputPath("01-normal-readiness.png"), fullPage: true });
  await page.selectOption("#bucket_filter", "Auction Candidates");
  await expect(page.locator("#allocation_table_heading")).toHaveText("Auction Candidates");
  await expect(page.locator("#allocation_body tr")).toHaveCount(21);
  const pendingListResponse = page.waitForResponse(
    response => response.url().endsWith("/riversdale-auction-list")
  );
  holdList = false;
  releaseList();
  await pendingListResponse;
  await expect(page.locator("[data-auction-pig-id]")).toHaveCount(21);
  await expect(page.locator("[data-auction-pig-id='VISUAL-PIG-103']")).toBeDisabled();
  await expect(page.locator("a.allocation-pig-link").first()).toHaveAttribute("href", "/pig/VISUAL-PIG-101");
  await expect(page.locator("#allocation_body")).not.toContainText("Purpose: Sale");
  await expect(page.locator("#allocation_summary")).toBeHidden();
  await expect(page.locator("#allocation_review_panel")).toBeHidden();
  const firstSelectableBox = await page.locator("[data-auction-pig-id]:not(:disabled)").first().boundingBox();
  expect(firstSelectableBox.y + firstSelectableBox.height).toBeLessThan(page.viewportSize().height);
  expect((await page.locator("#riversdale_auction_panel").boundingBox()).height).toBeLessThan(100);
  await page.screenshot({ path: testInfo.outputPath("02-auction-candidates.png"), fullPage: true });
  await page.screenshot({ path: testInfo.outputPath("02b-21-candidate-first-viewport.png"), fullPage: false });
  await page.locator("[data-review-pig-id='VISUAL-PIG-101']").click();
  await expect(page.locator("#allocation_review_panel")).toBeVisible();
  await expect(page.locator("#allocation_review_heading")).toHaveText("Auction Evidence Review");
  await expect(page.locator("[data-auction-evidence-review]")).toContainText("Authoritative withdrawal");
  await expect(page.locator("[data-auction-evidence-review]")).toContainText("cleared");
  await expect(page.locator("[data-auction-evidence-review]")).toContainText("suitable");
  await expect(page.locator("[data-auction-review-record]")).toBeVisible();
  expect(mutationRequests).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("02c-integrated-evidence-review.png"), fullPage: false });
  await page.check("[data-auction-pig-id='VISUAL-PIG-101']");
  await page.check("[data-auction-pig-id='VISUAL-PIG-102']");
  await expect(page.locator("#auction_selected_count")).toHaveText("2 selected");
  expect(mutationRequests).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("03-local-selection.png"), fullPage: true });

  await page.selectOption("#bucket_filter", "Auction List");
  await expect(page.locator("#allocation_table_heading")).toHaveText("Current Auction List");
  await expect(page.locator("#auction_print_list")).toBeVisible();
  await expect(page.locator("#auction_add_selected")).toBeHidden();
  await expect(page.locator("#allocation_body tr")).toHaveCount(4);
  await expect(page.locator("[data-auction-pig-id='VISUAL-PIG-103']")).toBeEnabled();
  await expect(page.locator("#allocation_body")).toContainText("Removal remains available");
  expect(mutationRequests).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("04-auction-list.png"), fullPage: true });
  await page.click("#auction_clear_selection");

  page.once("dialog", async (dialog) => {
    expect(dialog.type()).toBe("confirm");
    expect(dialog.message()).toContain("Remove 1 selected animal");
    await dialog.dismiss();
  });
  await page.check("[data-auction-pig-id='VISUAL-PIG-101']");
  await page.click("#auction_remove_selected");
  expect(mutationRequests).toEqual([]);

  await page.click("#auction_print_list");
  await page.emulateMedia({ media: "print" });
  await expect(page.locator("#auction_print_heading")).toContainText("Riversdale Auction List");
  await expect(page.locator("#allocation_table_heading")).toBeHidden();
  await expect(page.locator("#riversdale_auction_panel")).toBeHidden();
  await expect(page.locator(".allocation-filters:visible")).toHaveCount(0);
  await expect(page.locator("#auction_table_actions")).toBeHidden();
  await expect(page.locator("#allocation_body tr")).toHaveCount(4);
  const printHeadings = await page.locator("thead th:visible").allTextContents();
  expect(printHeadings).toContain("Pig/tag");
  expect(printHeadings).not.toContain("Details");
  expect(printHeadings).not.toContain("Select");
  expect(await page.locator("thead").evaluate((element) => getComputedStyle(element).display)).toBe("table-header-group");
  await expect(page.locator(".auction-row-details-button").first()).toHaveCSS("display", "none");
  expect(mutationRequests).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("05-print-preview.png"), fullPage: true });
  await page.emulateMedia({ media: "screen" });
  await page.setViewportSize({ width: 390, height: 844 });
  const horizontalTable = await page.locator(".allocation-table-wrap").evaluate((element) => ({
    overflowX: getComputedStyle(element).overflowX,
    scrollWidth: element.scrollWidth,
    clientWidth: element.clientWidth,
  }));
  expect(["auto", "scroll"]).toContain(horizontalTable.overflowX);
  expect(horizontalTable.scrollWidth).toBeGreaterThan(horizontalTable.clientWidth);
  await page.locator(".allocation-table-wrap").scrollIntoViewIfNeeded();
  await page.screenshot({ path: testInfo.outputPath("06-mobile-horizontal-table.png"), fullPage: false });
});
