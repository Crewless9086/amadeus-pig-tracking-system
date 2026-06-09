const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "tests",
  testMatch: ["oom_sakkie_playwright_behavior.spec.js"],
  timeout: 30000,
  use: {
    baseURL: process.env.OOM_SAKKIE_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5000",
    trace: "retain-on-failure",
  },
  webServer: {
    command: process.env.OOM_SAKKIE_PLAYWRIGHT_SERVER_COMMAND || "python app.py",
    url: process.env.OOM_SAKKIE_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5000/oom-sakkie",
    reuseExistingServer: true,
    timeout: 120000,
  },
});
