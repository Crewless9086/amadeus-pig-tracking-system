const { test, expect } = require("@playwright/test");

const baseURL = process.env.BEACON_VISUAL_BASE_URL || "http://127.0.0.1:5089";
const packetId = "BEACON-WEEK-2026-07-25-P1-S1";
const canonical = "df8e0c800b5b4c78f39e5f75e97f256e18a586eedffe740de61223a048c2d73f";
const captionHash = "27fe1763541ba365134ae82ef6414c87fff7bd744a46af71dd9c988889e2e75b";
const caption = "These three came straight over to inspect the camera while Ms. Piggy stayed close to the rest of the litter behind them.\n\nFollow the farm journey for more honest moments from behind the scenes at Amadeus Farm.";
const order = ["BEACON-ASSET-3D9A65053184D8181A", "BEACON-ASSET-983952CB4A95A0BEBB", "BEACON-ASSET-13F7A5168AE3BFF676"];
const image = "data:image/svg+xml;charset=utf-8," + encodeURIComponent("<svg xmlns='http://www.w3.org/2000/svg' width='400' height='300'><rect width='400' height='300' fill='#d9c39b'/><text x='200' y='155' text-anchor='middle'>Ms. Piggy and litter</text></svg>");

function json(route, body, status = 200) {
  return route.fulfill({status, contentType: "application/json", body: JSON.stringify(body)});
}

function contentPayload(decision = null) {
  const assets = order.map((assetId, index) => ({
    order: index + 1, asset_id: assetId, owner_confirmed_subject: "Ms. Piggy and her litter",
    dimensions: "4000 × 3000", thumbnail_url: image,
  }));
  return {
    success: true, status: "owner_review_packet_ready",
    runtime_status: {endpoint_available: true, owner_authenticated_read_succeeded: true, packet_generated: true, current_opportunity_read: false, writes_performed: false, publishing_performed: false},
    evidence_quality: {historical_post_count: 23, verified_performance_event_count: 17, unusable_performance_event_count: 64, metric_summary: {}},
    ranked_ideas: [], owner_explanations: {}, media_summary: {},
    featured_owner_review_packet: {
      packet_id: packetId, canonical_sha256: canonical, caption_sha256: captionHash,
      review_status: "awaiting_exact_owner_review", caption, channel: "Facebook Page",
      album_story: "Ms. Piggy and her litter – July 2026",
      capture_date_display: "Around 21 July 2026 · camera evidence · timezone unknown",
      confirmed_publication_count: 0, prior_confirmed_use: "none_evidenced",
      supersedes: {packet_id: "BEACON-WEEK-2026-07-25-P1", canonical_sha256: "85575b"},
      media: {exact_order: order, assets}, next_gate: "exact_owner_review_required",
    },
    weekly_owner_review_decision: decision,
    weekly_owner_review_decision_state: decision ? "recorded" : "awaiting_exact_owner_review",
  };
}

for (const viewport of [{name: "desktop", width: 1440, height: 1000}, {name: "mobile", width: 390, height: 844}]) {
  test(`${viewport.name} exact weekly post review controls remain non-publishing`, async ({page, context}) => {
    let decision = null;
    await page.setViewportSize({width: viewport.width, height: viewport.height});
    await page.route("**/api/beacon/**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      if (url.pathname.endsWith("/content-operations")) return json(route, contentPayload(decision));
      if (url.pathname.endsWith(`/${packetId}/decision`) && request.method() === "POST") {
        decision = {
          decision_status: "owner_approved", decision_at: "2026-07-25T20:00:00+00:00",
          owner_identity: "authenticated owner administrator", owner_notes: "",
          proposed_publication_datetime: "", proposed_timezone: "",
          next_gate: "Approved for a separately authorized one-attempt publication",
        };
        return json(route, {success: true, ...decision, publish: false, meta_call: false, upload: false, scheduled: false}, 201);
      }
      if (url.pathname.endsWith("/media-policy")) return json(route, {success: true});
      if (url.pathname.endsWith("/media-assets")) return json(route, {success: true, assets: [], summary: {approved: 0, needs_review: 0, rejected: 0, total: 0}});
      if (url.pathname.endsWith("/campaign-draft-selection")) return json(route, {success: true, approved_media_count: 0, campaign_lane: "live_stock_awareness", ranked_media_assets: [], channel_draft_pairings: []});
      if (url.pathname.endsWith("/facebook-posting-policy")) return json(route, {success: true, enabled: false});
      if (url.pathname.endsWith("/facebook-post-executions")) return json(route, {success: true, execution_events: []});
      if (url.pathname.endsWith("/manual-post-evidence")) return json(route, {success: true, manual_post_events: []});
      if (url.pathname.endsWith("/campaign-performance")) return json(route, {success: true, performance_events: [], command_brief: {recommendations: []}});
      return json(route, {success: true});
    });
    const login = await context.request.post(`${baseURL}/owner/login`, {form: {owner_token: "beacon-browser-fixture-token-0000000000000000", next: "/sales/beacon-media"}});
    expect(login.ok()).toBeTruthy();
    await page.goto(`${baseURL}/sales/beacon-media`, {waitUntil: "domcontentloaded"});
    const panel = page.locator("#beacon_packet_decision");
    await expect(panel.getByText("Approve This Post")).toBeVisible();
    await expect(panel.getByText("Request Changes")).toBeVisible();
    await expect(panel.getByText("Reject This Post")).toBeVisible();
    await expect(panel).toContainText("Approval does not publish this post");
    await expect(page.locator("#beacon_packet_media figure")).toHaveCount(3);
    expect(await page.locator("#beacon_packet_media figcaption strong").allTextContents()).toEqual(order.map((id, index) => `${index + 1}. ${id}`));
    await panel.getByText("Approve This Post").click();
    await expect(panel).toContainText("Approved for a separately authorized one-attempt publication");
    await expect(panel.getByText("Approve This Post")).toBeDisabled();
    await expect(panel.getByText("Publish", {exact: true})).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  });
}
