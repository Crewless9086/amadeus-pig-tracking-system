const { defineConfig } = require("@playwright/test");

const baseURL = process.env.OOM_SAKKIE_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5000";
const serverURL = process.env.OOM_SAKKIE_PLAYWRIGHT_SERVER_URL || `${baseURL}/oom-sakkie`;

module.exports = defineConfig({
  testDir: "tests",
  testMatch: ["oom_sakkie_playwright_behavior.spec.js", "charlie_mission_control_playwright.spec.js", "charlie_live_executive_playwright.spec.js", "beacon_live_stock_visual_proof.spec.js", "beacon_meat_launch_visual_proof.spec.js"],
  timeout: 30000,
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  webServer: {
    command: process.env.OOM_SAKKIE_PLAYWRIGHT_SERVER_COMMAND || "python app.py",
    url: serverURL,
    reuseExistingServer: true,
    timeout: 120000,
  },
});
