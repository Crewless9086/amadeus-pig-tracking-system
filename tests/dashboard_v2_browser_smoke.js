const assert = require("assert");
const { chromium } = require("playwright");

const baseUrl = process.env.DASHBOARD_BASE_URL || "http://127.0.0.1:5091";

const fixtures = {
  "/api/telemetry/weather/current": { current: { temperature_c: 18, humidity_pct: 72, rain_today_mm: 2.3, rain_rate_mm_h: 0, wind_speed_kmh: 9, wind_gust_kmh: 14 }, source: { data_age_minutes: 2 }, summary: { headline: "Fresh and dry at the farm." } },
  "/api/telemetry/weather/forecast": { days: [{ forecast_date: "2026-08-10", temp_min_c: 9, temp_max_c: 20, rain_sum_mm: 0 }] },
  "/api/telemetry/power/current": { current: { battery_soc_pct: 74, battery_state: "charging", solar_power_w: 2840, load_power_w: 690, grid_power_w: 0, grid_state: "off_grid" }, source: { data_age_minutes: 1 }, summary: { headline: "Battery and solar are healthy." } },
  "/api/telemetry/power/recent": { summary: { minimum_battery_soc_pct: 43, peak_solar_power_w: 3150 } },
  "/api/telemetry/irrigation/status": { current: { status: "Hold" }, today: { done_count: 0, completed_minutes: 0, skipped_count: 2, next_zone_name: "B Camp", plan: [{ zone_id: "B12345", zone_name: "B Camp", status: "Skipped", planned_minutes: 60, reason: "Observed rain" }, { zone_id: "C12345", zone_name: "C Camp", status: "Skipped", planned_minutes: 60, reason: "Observed rain" }] }, source: { source: "canonical" }, operator_summary: { notes: ["Reassess after observed rain."] } },
  "/api/pig-weights/dashboard": { summary: { on_farm_pigs: 121, sows: 18, boars: 3, piglets: 54, available_for_sale_pigs: 26, reserved_pigs: 5, lifecycle_sold_this_month: 18, lifecycle_dead_this_month: 1, lifecycle_removed_this_month: 0, sales_metrics: { recent_sales_value: 4470.51 } }, litter_attention: { items: [{ litter_id: "LIT-2026-1350", reason: "Weaning overdue", action_type: "review" }] } },
  "/api/pig-weights/matings": { records: [{ is_open: "Yes", is_overdue_farrowing: "No", expected_farrowing_date: "2026-08-20", sow_tag_number: "Mona" }] },
  "/api/pig-weights/sales-dashboard": { sales_metrics: { recent_sales_value: 7070.51, live_sale_ready: 26 } },
  "/api/reports/daily-summary": { counts: { orders_needing_attention: 1, pending_approval: 1 }, sections: { orders_needing_attention: [{ order_id: "ORD-1", customer_name: "Delia", reasons: ["Approval"] }] } },
  "/api/telemetry/rootline/daily-advisor": { zones: [{ zone_name: "B Camp", recommendation: "Run later", reasoning: ["Observed rain credit"] }], unresolved_owner_decisions: [] },
  "/api/telemetry/rootline/daily-brief": { status: "ok", executive_summary: "Rain Hold is current." },
  "/api/telemetry/rootline/daily-irrigation-plan": { status: "ok", owner_message: "B is next." },
  "/api/telemetry/rootline/water-energy-plan": { status: "ok", executive_summary: "Water plan available." },
  "/api/telemetry/rootline/operating-policy": { status: "ok" },
};

function fixtureFor(url) {
  const path = new URL(url).pathname;
  return Object.entries(fixtures).find(([prefix]) => path.startsWith(prefix))?.[1];
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  await page.route("**/api/**", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixtureFor(route.request().url()) || { status: "ok" }) }));
  await page.goto(`${baseUrl}/`, { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("#herd_total")?.textContent === "121");
  assert.equal(await page.locator(".operating-card").count(), 6);
  assert.equal(await page.locator("#status_weather").textContent(), "18 °C · 2.3 mm today");
  assert.match(await page.locator("#attention_list").textContent(), /Weaning overdue/);
  assert.equal(await page.locator("#power_battery").textContent(), "74%");
  assert.equal(await page.locator("#herd_total").textContent(), "121");
  assert.equal(await page.locator("#sales_ready").textContent(), "26");
  assert.equal(await page.locator("#breeding_open").textContent(), "1");
  assert.equal(await page.locator(".operating-card.is-loading").count(), 0);
  await page.screenshot({ path: "C:/tmp/farm-dashboard-v2-populated-desktop.png", fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.reload({ waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("#herd_total")?.textContent === "121");
  assert.equal(await page.locator(".operating-card").count(), 6);
  await page.screenshot({ path: "C:/tmp/farm-dashboard-v2-populated-mobile.png", fullPage: true });

  for (const route of ["weather", "power", "irrigation"]) {
    await page.goto(`${baseUrl}/${route}`, { waitUntil: "networkidle" });
    assert.equal(await page.locator("h1").textContent(), route[0].toUpperCase() + route.slice(1));
  }
  await browser.close();
  console.log("dashboard_v2_browser_smoke: PASS");
})().catch(error => { console.error(error); process.exit(1); });
