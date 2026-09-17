const { test, expect } = require("@playwright/test");

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

for (const viewport of [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`${viewport.name} Water and Energy Plan stays practical and command-inert`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/rootline/water-energy-plan")) {
        return json(route, {
          success: true,
          plan_id: "ROOTLINE-WEP-20260728",
          generation: 1,
          executive_summary: "Hold borehole; review water evidence.",
          owner_can_administer: true,
          current_power: {status: "fresh", battery_soc_pct: 68, age_minutes: 3},
          forecast: {status: "fresh", solar_profile: "mixed", confidence: "medium"},
          rain_capture: {current_rain_status: "no_live_rain_threshold", fresh_rain_rate_mm_h: 0, forecast_replenishment_effect: "no_meaningful_rain_signal"},
          battery_reserve: {governing_reserve_soc_pct: 67},
          tank_evidence: {status: "fresh", storage_reported_count: 4, storage_state: "OK", reservoir_reported_count: 8, reservoir_state: "OK", age_minutes: 20},
          estimated_grid_exposure: {status: "possible_unquantified", estimated_kwh: "Unavailable", estimated_cost_zar: "Unavailable", tariff_zar_per_kwh: 9},
          candidate_tasks: [{task_id: "borehole", recommendation: "Hold", reason: "Water need is not proven.", preferred_window: "overnight_or_surplus_solar", dependencies: ["genuine_water_need"], command_created: false, dispatchable: false}],
          evidence_gaps: ["SmartLife device binding unresolved"],
          authority: {controls_hardware: false, creates_command: false},
        });
      }
      return json(route, {success: true});
    });
    await page.goto("/", {waitUntil: "domcontentloaded"});
    const panel = page.locator("#rootline_water_energy_summary");
    await expect(panel).toContainText("ROOTLINE-WEP-20260728");
    await expect(panel).toContainText("SOC 68%");
    await expect(panel).toContainText("Storage 4/5 (OK)");
    await expect(panel).toContainText("Plan is not command acceptance");
    await expect(panel).toContainText("no command, schedule, workflow, retry or hardware authority");
    await expect(panel).toContainText("shared dashboard remains read-only");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  });
}
