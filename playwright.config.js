const { defineConfig } = require("@playwright/test");

const baseURL = process.env.OOM_SAKKIE_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5000";

module.exports = defineConfig({
  testDir: "tests",
  testMatch: ["oom_sakkie_playwright_behavior.spec.js"],
  timeout: 30000,
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
});
