const { test, expect } = require("@playwright/test");

const attribution = {
  success: true,
  status: "ok",
  mode: "beacon_sam_attribution_read_only",
  rule_version: "beacon_sam_attribution_v1",
  attribution_window_days: 30,
  authority: { read_only: true },
  summary: { attributed: 2, ambiguous: 1, unmatched: 1, qualified: 1, lost: 1 },
  malformed_evidence_ids: [],
  attributions: [
    { campaign_ref: "CAM-MEAT-01", status: "attributed", method: "exact_campaign_id", lead_id: "LEAD-101", qualification: "qualified", order_id: "ORDER-44", revenue: [{ currency: "ZAR", net_total: "1234.50" }], fulfilment: "achieved", lost_reason: { status: "not_lost", code: "" } },
    { campaign_ref: "CAM-LIVE-02", status: "attributed", method: "exact_campaign_id", lead_id: "LEAD-102", qualification: "lost", order_id: "", order_status: "none", revenue: [], fulfilment: "unknown", lost_reason: { status: "recorded", code: "price" } },
    { campaign_ref: "CAM-WINDOW-03", status: "ambiguous", candidate_lead_ids: ["LEAD-201", "LEAD-202"], qualification: "unresolved", revenue: [], fulfilment: "unknown", lost_reason: { status: "unknown", code: "" } },
    { campaign_ref: "CAM-UNMATCHED-04", status: "unmatched", qualification: "unresolved", revenue: [], fulfilment: "unknown", lost_reason: { status: "unknown", code: "" } },
  ],
};

for (const viewport of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`${viewport.name} attribution evidence is readable and contained`, async ({ page }) => {
    await page.setViewportSize(viewport);
    await page.route("**/api/beacon/sam-attribution", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(attribution) }));
    await page.goto("http://127.0.0.1:5092/sales/beacon-media", { waitUntil: "domcontentloaded" });
    await expect(page.locator("#beacon_attribution_status")).toContainText("Canonical read-only projection");
    await expect(page.locator("#beacon_attribution_summary")).toContainText("Ambiguous");
    await expect(page.locator("#beacon_attribution_revenue")).toContainText("1234.50");
    await expect(page.locator("#beacon_attribution_evidence")).toContainText("LEAD-201");
    await expect(page.getByText("No posting, customer sends, spend, orders, reservations, stock changes, or farm writes.")).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow).toBeFalsy();
    await page.locator(".beacon-attribution-panel").screenshot({ path: `.charlie_runner/evidence/CHARLIE-SCOPE-A02DD56918ADDAC0-${viewport.name}.png` });
  });
}

test("empty, error, and malformed states fail visibly closed", async ({ page }) => {
  let response = { ...attribution, summary: { attributed: 0, ambiguous: 0, unmatched: 0, qualified: 0, lost: 0 }, attributions: [] };
  await page.route("**/api/beacon/sam-attribution", (route) => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(response) }));
  await page.goto("http://127.0.0.1:5092/sales/beacon-media", { waitUntil: "domcontentloaded" });
  await expect(page.locator("#beacon_attribution_evidence")).toContainText("No attribution evidence yet");
  response = { success: true, status: "ok" };
  await page.locator("#beacon_attribution_refresh").click();
  await expect(page.locator("#beacon_attribution_status")).toContainText("malformed or unavailable");
  response = { success: false, status: "source_unavailable" };
  await page.locator("#beacon_attribution_refresh").click();
  await expect(page.locator("#beacon_attribution_evidence")).toContainText("source_unavailable");
});
