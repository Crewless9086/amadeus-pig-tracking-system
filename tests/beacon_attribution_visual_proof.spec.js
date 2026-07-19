const { test, expect } = require("@playwright/test");

const baseURL = process.env.BEACON_ATTRIBUTION_VISUAL_BASE_URL || "http://127.0.0.1:5055";
const evidenceDir = ".charlie_runner/evidence/CHARLIE-SCOPE-A02DD56918ADDAC0";
const attribution = {
  success: true,
  status: "ok",
  mode: "beacon_sam_attribution_read_only",
  summary: { attributed: 2, ambiguous: 1, unmatched: 1, qualified: 1, lost: 1 },
  malformed_evidence_ids: [],
  authority: { read_only: true, posts_publicly: false, spends_money: false, creates_order: false, changes_stock: false },
  attributions: [
    { campaign_ref: "CAM-ALPHA", performance_event_id: "PERF-1", status: "attributed", method: "exact_campaign_id", lead_id: "LEAD-1", qualification: "qualified", order_id: "ORDER-1", fulfilment: "achieved", revenue: [{ currency: "ZAR", net_total: "1234.50" }], lost_reason: { status: "not_lost" } },
    { campaign_ref: "CAM-BETA", performance_event_id: "PERF-2", status: "attributed", method: "exact_campaign_id", lead_id: "LEAD-2", qualification: "lost", order_id: "", fulfilment: "failed", revenue: [], lost_reason: { status: "recorded", code: "price" } },
    { campaign_ref: "CAM-GAMMA", performance_event_id: "PERF-3", status: "ambiguous", candidate_lead_ids: ["LEAD-3", "LEAD-4"], qualification: "unresolved", order_id: "", fulfilment: "unknown", revenue: [], lost_reason: { status: "unknown" } },
    { campaign_ref: "CAM-DELTA", performance_event_id: "PERF-4", status: "unmatched", qualification: "unresolved", order_id: "", fulfilment: "unknown", revenue: [], lost_reason: { status: "unknown" } },
  ],
};

function json(route, body) { return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) }); }

for (const viewport of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`${viewport.name} renders read-only Beacon attribution without overflow`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.route("**/api/beacon/**", async (route) => {
      if (new URL(route.request().url()).pathname.endsWith("/sam-attribution")) return json(route, attribution);
      return json(route, { success: true, assets: [], summary: {}, performance_events: [], command_brief: { recommendations: [] }, execution_events: [], manual_post_events: [] });
    });
    await page.goto(`${baseURL}/sales/beacon-media`, { waitUntil: "domcontentloaded" });
    await expect(page.locator("#beacon_attribution_status")).toHaveText("Canonical evidence");
    await expect(page.locator("#beacon_attribution_count")).toHaveText("2");
    await expect(page.locator("#beacon_attribution_list")).toContainText("CAM-ALPHA");
    await expect(page.locator("#beacon_attribution_list")).toContainText("CAM-GAMMA");
    await expect(page.locator("#beacon_attribution_list")).toContainText("ZAR 1234.50");
    await expect(page.locator("#beacon_attribution_refresh")).toBeVisible();
    await page.locator("#beacon_attribution_title").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${evidenceDir}/beacon-attribution-${viewport.name}.png`, fullPage: true });
    const layout = await page.evaluate(() => ({
      width: document.documentElement.scrollWidth,
      viewport: window.innerWidth,
      overflow: [...document.querySelectorAll("*")].filter((node) => node.getBoundingClientRect().right > window.innerWidth + 1).slice(0, 6).map((node) => ({ tag: node.tagName, id: node.id, className: node.className, right: Math.round(node.getBoundingClientRect().right) })),
    }));
    expect(layout.overflow).toEqual([]);
  });
}

test("empty and malformed attribution evidence stays explicit", async ({ page }) => {
  let malformed = false;
  await page.route("**/api/beacon/**", async (route) => {
    if (new URL(route.request().url()).pathname.endsWith("/sam-attribution")) {
      return json(route, malformed ? { ...attribution, success: false, status: "malformed_evidence", attributions: [], malformed_evidence_ids: ["PERF-BAD"] } : { ...attribution, summary: { attributed: 0, ambiguous: 0, unmatched: 0, qualified: 0, lost: 0 }, attributions: [] });
    }
    return json(route, { success: true, assets: [], summary: {}, performance_events: [], command_brief: { recommendations: [] }, execution_events: [], manual_post_events: [] });
  });
  await page.goto(`${baseURL}/sales/beacon-media`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("#beacon_attribution_list")).toContainText("No attributable campaign evidence");
  malformed = true;
  await page.click("#beacon_attribution_refresh");
  await expect(page.locator("#beacon_attribution_status")).toHaveText("Evidence unavailable");
  await expect(page.locator("#beacon_attribution_list")).toContainText("Malformed evidence was not attributed");
  await expect(page.locator("#beacon_attribution_note")).toContainText("PERF-BAD");
});
