const { test, expect } = require("@playwright/test");

const baseURL = "http://127.0.0.1:5088";
const evidenceDir = ".charlie_runner/evidence/CHARLIE-MISSION-F7F8A97750EC42A5";

const asset = {
  asset_id: "BEACON-ASSET-LIVE-001",
  title: "Owner-approved grower pigs",
  original_filename: "grower-pigs-owner-approved.jpg",
  media_type: "image",
  effective_approval_status: "approved",
  effective_public_use_approved: true,
  content_sha256: "7f4d9a2e1b6c8d00",
  sale_stream_relevance: ["live_stock_sales"],
  privacy_risk: "low",
  latest_event: { event_type: "approved_public_use", notes: "Owner approved for public Live-Stock Sales use." },
};

const salesTruth = {
  sale_eligible: true,
  eligibility_source: "Supabase pig allocation readiness · revision ELIG-20260714-01",
  fulfilment_cap: 3,
  fulfilment_unit: "grower pigs",
  fulfilment_as_of: "Current at 14 July 2026 21:45 SAST",
  stock_lineage_approved: true,
  stock_source: "SALES_STOCK_TOTALS sheet sync · STOCK-20260714-03",
  price_lineage_approved: true,
  price_display: "R2,450 each",
  price_source: "SALES_PRICING · effective 14 July 2026",
};

const exactText = "Three grower pigs are available near Riversdale at R2,450 each. Current owner-approved fulfilment cap: 3. Message us with your location and intended use; SAM Live Stock will follow up. Campaign BEACON-SAM-LIVE-7F4D9A2E.";

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function mockBeaconApi(page) {
  const executionEvents = [];
  await page.route("**/api/beacon/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    if (url.pathname.endsWith("/media-policy")) return json(route, { success: true, storage_ready: true, public_use_requires_owner_approval: true });
    if (url.pathname.endsWith("/media-assets")) return json(route, { success: true, assets: [asset], summary: { approved: 1, needs_review: 0, rejected: 0, total: 1 } });
    if (url.pathname.endsWith("/campaign-draft-selection")) return json(route, {
      success: true, campaign_lane: "live_stock_sales", approved_media_count: 1, sales_truth: salesTruth,
      ranked_media_assets: [asset],
      channel_draft_pairings: [
        { draft_id: "facebook_live_stock_sales", draft_label: "Facebook sales post", channel: "Facebook", intent: "owner-gated live-stock sale", recommended_asset_id: asset.asset_id, recommended_asset_title: asset.title, selection_reason: "Owner-approved and lane-compatible." },
        { draft_id: "whatsapp_live_stock_sales", draft_label: "WhatsApp suggestion only", channel: "WhatsApp", intent: "copy suggestion only", recommended_asset_id: asset.asset_id, recommended_asset_title: asset.title, selection_reason: "Suggestion only; no send action." },
      ],
    });
    if (url.pathname.endsWith("/campaign-publish-packet")) return json(route, {
      success: true, publish_packet_id: "BEACON-PUBLISH-PACKET-F7F8A977", campaign_lane: "live_stock_sales", approval_status: "prepared_for_exact_owner_confirmation",
      campaign: { name: "Riversdale Grower Pig Pilot" }, selected_asset: asset, sales_truth: salesTruth,
      selected_draft: { channel: "Facebook", exact_text: exactText }, safety_checks: { no_public_send_or_post: false },
    });
    if (url.pathname.endsWith("/facebook-posting-policy")) return json(route, { success: true, enabled: true, page_id_configured: true, page_access_token_configured: true, required_owner_confirmation: "POST EXACT BEACON PACKET" });
    if (url.pathname.endsWith("/facebook-post-executions") && request.method() === "POST") {
      const executionEvent = { execution_status: "posted", facebook_post_id: "123456789_987654321", publish_packet_id: "BEACON-PUBLISH-PACKET-F7F8A977", post_kind: "photo", selected_media: asset, created_at: "2026-07-14T19:45:00Z" };
      executionEvents.unshift(executionEvent);
      return json(route, {
        success: true, status: "facebook_post_recorded", facebook_post_id: "123456789_987654321", posts_publicly: true, calls_meta: true,
        execution_event: executionEvent,
      });
    }
    if (url.pathname.endsWith("/facebook-post-executions")) return json(route, { success: true, execution_events: executionEvents });
    if (url.pathname.endsWith("/manual-post-evidence")) return json(route, { success: true, manual_post_events: [] });
    if (url.pathname.endsWith("/campaign-performance")) return json(route, { success: true, performance_events: [], command_brief: { recommendations: [] } });
    return json(route, { success: true });
  });
}

for (const viewport of [
  { name: "desktop", width: 1440, height: 900 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`${viewport.name} owner-gated populated Live-Stock Sales proof`, async ({ page, context }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await mockBeaconApi(page);
    const login = await context.request.post(`${baseURL}/owner/login`, { form: { owner_token: "beacon-browser-fixture-token-0000000000000000", next: "/sales/beacon-media" } });
    expect(login.ok()).toBeTruthy();
    await page.goto(`${baseURL}/sales/beacon-media`, { waitUntil: "domcontentloaded" });
    await page.selectOption("#beacon_campaign_lane", "live_stock_sales");
    await expect(page.locator("#beacon_sales_truth_status")).toHaveText("Sales evidence ready");
    await page.selectOption("#beacon_publish_asset_id", asset.asset_id);
    await page.click("#beacon_publish_prepare");
    await expect(page.locator("#beacon_facebook_post_packet_id")).toHaveValue("BEACON-PUBLISH-PACKET-F7F8A977");
    await page.fill("#beacon_facebook_post_confirmation", "POST EXACT BEACON PACKET");
    await page.click("#beacon_facebook_post_execute");
    await expect(page.locator("#beacon_facebook_post_result")).toContainText("123456789_987654321");
    const executionLedger = page.locator("#beacon_facebook_post_execution_list .beacon-facebook-post-item");
    await expect(executionLedger).toHaveCount(1);
    await expect(executionLedger.first()).toContainText("BEACON-PUBLISH-PACKET-F7F8A977");
    await expect(executionLedger.first()).toContainText("123456789_987654321");
    await page.locator("#beacon_sales_truth").scrollIntoViewIfNeeded();
    await page.screenshot({ path: `${evidenceDir}/beacon-live-stock-${viewport.name}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  });
}
