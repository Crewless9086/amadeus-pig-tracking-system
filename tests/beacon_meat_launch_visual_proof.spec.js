const { test, expect } = require("@playwright/test");

const baseURL = process.env.BEACON_VISUAL_BASE_URL || "http://127.0.0.1:5089";
const evidenceDir = ".charlie_runner/evidence/CHARLIE-MISSION-EEB900E3BD27304D";
const exactImage = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="800"><rect width="1200" height="800" fill="#efe4cf"/><rect x="72" y="72" width="1056" height="656" rx="36" fill="#244837"/><text x="600" y="330" text-anchor="middle" fill="#fffaf0" font-family="Arial" font-size="76" font-weight="700">AMADEUS FARM</text><text x="600" y="430" text-anchor="middle" fill="#e8c976" font-family="Arial" font-size="56">Owner-approved pork launch image</text><text x="600" y="520" text-anchor="middle" fill="#fffaf0" font-family="Arial" font-size="34">Exact public-use asset BEACON-ASSET-MEAT-001</text></svg>`);
const asset = { asset_id: "BEACON-ASSET-MEAT-001", title: "Owner-approved Amadeus pork launch", original_filename: "amadeus-pork-owner-approved.jpg", media_type: "image", effective_approval_status: "approved", effective_public_use_approved: true, public_use_approved: true, preview_url: exactImage, content_sha256: "eeb900e3bd27304d", sale_stream_relevance: ["meat_launch"], privacy_risk: "low", latest_event: { event_type: "approved_public_use", notes: "Owner approved for the bounded meat launch pilot." } };
const exactText = "Amadeus Farm pork freezer interest pilot. We are opening a small owner-capped enquiry list for this launch. Message us if you would like details; SAM Meat will capture your interest and the owner will confirm all stock, cuts, price, collection or delivery facts before any order. Pilot cap: 2 enquiries.";
const packetId = "BEACON-PUBLISH-PACKET-EEB900E3";
const postId = "MOCK-FACEBOOK-POST-123456789";

function json(route, body, status = 200) { return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) }); }

async function mockBeaconApi(page) {
  let posted = false;
  await page.route("**/api/beacon/**", async (route) => {
    const request = route.request(); const url = new URL(request.url());
    if (url.pathname.endsWith("/media-policy")) return json(route, { success: true, storage_ready: true, public_use_requires_owner_approval: true });
    if (url.pathname.endsWith("/media-assets")) return json(route, { success: true, assets: [asset], summary: { approved: 1, needs_review: 0, rejected: 0, total: 1 } });
    if (url.pathname.endsWith("/campaign-draft-selection")) return json(route, { success: true, campaign_lane: "meat_launch", approved_media_count: 1, meat_launch_readiness: { owner_offer_enabled: true, pilot_cap: "", pilot_cap_valid: false, errors: ["meat_pilot_cap_positive_whole_number_required"] }, ranked_media_assets: [asset], channel_draft_pairings: [{ draft_id: "facebook_meat_launch", draft_label: "Facebook meat launch", channel: "Facebook", intent: "owner-gated interest pilot", recommended_asset_id: asset.asset_id, recommended_asset_title: asset.title, selection_reason: "Current owner-approved public-use image." }] });
    if (url.pathname.endsWith("/campaign-publish-packet")) return json(route, { success: true, publish_packet_id: packetId, campaign_lane: "meat_launch", pilot_cap: "2", approval_status: "prepared_for_exact_owner_confirmation", campaign: { name: "Amadeus Meat Launch Owner Pilot" }, selected_asset: asset, selected_draft: { channel: "Facebook", exact_text: exactText }, meat_launch_readiness: { owner_offer_enabled: true, pilot_cap: "2", pilot_cap_valid: true, ready: true, errors: [] }, safety_checks: { draft_has_no_forbidden_promise: true, no_public_send_or_post: false } });
    if (url.pathname.endsWith("/facebook-posting-policy")) return json(route, { success: true, enabled: true, page_id_configured: true, page_access_token_configured: true, required_owner_confirmation: "POST EXACT BEACON PACKET" });
    if (url.pathname.endsWith("/facebook-post-executions") && request.method() === "POST") { posted = true; return json(route, { success: true, status: "facebook_post_recorded", facebook_post_id: postId, posts_publicly: true, calls_meta: true, execution_event: { execution_status: "posted", facebook_post_id: postId, publish_packet_id: packetId, post_kind: "photo", selected_media: asset, created_at: "2026-07-14T21:45:00+02:00" } }); }
    if (url.pathname.endsWith("/facebook-post-executions")) return json(route, { success: true, execution_events: posted ? [{ execution_status: "posted", facebook_post_id: postId, publish_packet_id: packetId, post_kind: "photo", selected_media: asset, created_at: "2026-07-14T21:45:00+02:00" }] : [] });
    if (url.pathname.endsWith("/manual-post-evidence")) return json(route, { success: true, manual_post_events: [] });
    if (url.pathname.endsWith("/campaign-performance")) return json(route, { success: true, performance_events: [], command_brief: { recommendations: [] } });
    return json(route, { success: true });
  });
}

for (const viewport of [{ name: "desktop", width: 1440, height: 1000 }, { name: "mobile", width: 390, height: 844 }]) {
  test(`${viewport.name} owner-gated meat launch ready and recorded proof`, async ({ page, context }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height }); await mockBeaconApi(page);
    const login = await context.request.post(`${baseURL}/owner/login`, { form: { owner_token: "beacon-browser-fixture-token-0000000000000000", next: "/sales/beacon-media" } }); expect(login.ok()).toBeTruthy();
    await page.goto(`${baseURL}/sales/beacon-media`, { waitUntil: "domcontentloaded" }); await page.selectOption("#beacon_campaign_lane", "meat_launch"); await page.fill("#beacon_publish_cap", "2");
    await expect(page.locator("#beacon_meat_readiness_status")).toHaveText("Ready to prepare"); await page.selectOption("#beacon_publish_asset_id", asset.asset_id); await page.click("#beacon_publish_prepare");
    await expect(page.locator("#beacon_facebook_post_packet_id")).toHaveValue(packetId); await expect(page.locator("#beacon_facebook_post_exact_text")).toHaveValue(exactText); await expect(page.locator("#beacon_facebook_post_image")).toBeVisible();
    await page.fill("#beacon_facebook_post_confirmation", "POST EXACT BEACON PACKET"); await expect(page.locator("#beacon_facebook_post_execute")).toBeEnabled(); await page.click("#beacon_facebook_post_execute"); await expect(page.locator("#beacon_facebook_post_result")).toContainText(postId);
    await page.locator("#beacon_facebook_post_execute").scrollIntoViewIfNeeded(); await page.screenshot({ path: `${evidenceDir}/beacon-meat-launch-${viewport.name}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  });
}
