const { test, expect } = require("@playwright/test");

const baseURL = process.env.BEACON_VISUAL_BASE_URL || "http://127.0.0.1:5089";
const thumb = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(
  "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='480'>" +
  "<rect width='640' height='480' fill='#c99d78'/>" +
  "<circle cx='210' cy='240' r='85' fill='#f0c7ab'/>" +
  "<circle cx='430' cy='235' r='72' fill='#e9b99b'/>" +
  "<text x='320' y='430' text-anchor='middle' font-size='26'>private intake preview</text></svg>"
);

function json(route, body, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function intakeItems() {
  return [1, 2, 3].map((position) => ({
    intake_group_id: "BEACON-INTAKE-GROUP-ALBUM",
    intake_item_id: `BEACON-INTAKE-ITEM-${position}`,
    binary_asset_id: `BEACON-BINARY-${position}`,
    owner_explanation: "Ms. Piggy and her litter; capture date unknown.",
    source_message_at: "2026-07-27T08:00:00+00:00",
    capture_time: "",
    capture_time_state: "unknown",
    intake_at: "2026-07-27T08:00:10+00:00",
    album_position: position,
    album_completed: true,
    latest_review_event_id: "",
    observed_mime_type: "image/jpeg",
    byte_size: 125000,
    width: 1600,
    height: 1200,
    exact_duplicate: false,
    thumbnail_available: true,
    thumbnail_url: thumb,
    observation: {
      summary: "Several pigs are visible in a farm pen.",
      suggested_tags: ["farm life", "piglets"],
      warnings: ["Animal identity remains unconfirmed by vision"],
    },
    observation_confidence: "suggested",
    latest_library_event: "",
    effective_public_use_approved: false,
    prior_campaign_use_count: 0,
    publish: false,
    meta_call: false,
    advertise: false,
    boost: false,
    spend: false,
  }));
}

for (const viewport of [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`${viewport.name} private Telegram contact sheet keeps review gates separate`, async ({ page, context }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.route("**/api/oom-sakkie/beacon/media-intakes**", async (route) => {
      const url = new URL(route.request().url());
      if (route.request().method() === "POST" && url.pathname.endsWith("/review")) {
        return json(route, {
          success: true, status: "media_review_event_recorded", created_count: 1,
          public_use_approved: false, publish: false, meta_call: false,
          schedule: false, advertise: false, boost: false, spend: false,
        }, 201);
      }
      return json(route, { success: true, status: "media_intakes_listed", items: intakeItems() });
    });
    await page.route("**/api/beacon/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/content-operations")) {
        return json(route, {
          success: true, ranked_ideas: [], owner_explanations: {},
          evidence_quality: { metric_summary: {} }, media_summary: {},
          runtime_status: {}, capability_status: {},
          featured_owner_review_packet: null,
          weekly_owner_review_decision: null,
        });
      }
      if (path.endsWith("/media-policy")) return json(route, { success: true });
      if (path.endsWith("/media-assets")) {
        return json(route, { success: true, assets: [], counts: { total: 0, needs_review: 0, approved: 0, rejected: 0 } });
      }
      if (path.endsWith("/campaign-draft-selection")) return json(route, { success: true, ranked_media_assets: [], channel_draft_pairings: [] });
      if (path.endsWith("/facebook-posting-policy")) return json(route, { success: true, enabled: false });
      if (path.endsWith("/facebook-post-executions")) return json(route, { success: true, execution_events: [] });
      if (path.endsWith("/manual-post-evidence")) return json(route, { success: true, manual_post_events: [] });
      if (path.endsWith("/campaign-performance")) return json(route, { success: true, performance_events: [], command_brief: { recommendations: [] } });
      return json(route, { success: true });
    });
    const login = await context.request.post(`${baseURL}/owner/login`, {
      form: {
        owner_token: "beacon-browser-fixture-token-0000000000000000",
        next: "/sales/beacon-media",
      },
    });
    expect(login.ok()).toBeTruthy();
    await page.goto(`${baseURL}/sales/beacon-media`, { waitUntil: "domcontentloaded" });

    const sheet = page.locator("#beacon_intake_contact_sheet");
    await expect(sheet.locator(".beacon-intake-card")).toHaveCount(3);
    await expect(sheet).toContainText("Ms. Piggy and her litter");
    await expect(sheet).toContainText("Capture");
    await expect(sheet).toContainText("Unknown");
    await expect(sheet).toContainText("Library Accept");
    await expect(sheet).toContainText("Public-use Approve");
    await expect(sheet).toContainText("Reject");
    await expect(sheet).toContainText("Archive");
    await expect(sheet).toContainText("Edit owner context");
    await expect(page.locator("#beacon_intake_boundary")).toContainText(
      "animal identity, ownership, health, availability, location, or capture date"
    );
    await expect(page.getByText("Publish", { exact: true })).toHaveCount(0);
    await sheet.locator(".beacon-intake-thumb").first().click();
    await expect(page.locator("#beacon_intake_preview")).toBeVisible();
    await expect(page.locator("#beacon_intake_preview_image")).toBeVisible();
    await expect(page.locator("#beacon_intake_preview_close")).toBeFocused();
    await page.keyboard.press("Tab");
    await expect(page.locator("#beacon_intake_preview_close")).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(page.locator("#beacon_intake_preview")).toBeHidden();
    await expect(sheet.locator(".beacon-intake-thumb").first()).toBeFocused();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  });
}
