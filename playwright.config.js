const { defineConfig } = require("@playwright/test");

const baseURL = process.env.OOM_SAKKIE_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5000";
const serverURL = process.env.OOM_SAKKIE_PLAYWRIGHT_SERVER_URL || `${baseURL}/oom-sakkie`;

module.exports = defineConfig({
  testDir: "tests",
  testMatch: ["oom_sakkie_playwright_behavior.spec.js", "charlie_mission_control_playwright.spec.js", "charlie_live_executive_playwright.spec.js", "beacon_live_stock_visual_proof.spec.js", "beacon_meat_launch_visual_proof.spec.js", "beacon_weekly_owner_review_visual_proof.spec.js", "beacon_media_intake_visual_proof.spec.js", "riversdale_auction_list_visual_proof.spec.js", "rootline_operating_policy_visual_proof.spec.js", "rootline_water_energy_visual_proof.spec.js", "breeding_attention_phase2_visual_proof.spec.js", "litter_weaning_day_browser.spec.js", "dashboard_litter_attention_browser.spec.js", "litter_lifecycle_visual_proof.spec.js"],
  timeout: 30000,
  use: {
    baseURL,
    trace: "retain-on-failure",
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE }
      : {},
  },
  webServer: {
    command: process.env.OOM_SAKKIE_PLAYWRIGHT_SERVER_COMMAND || "python app.py",
    url: serverURL,
    reuseExistingServer: true,
    timeout: 120000,
  },
});
