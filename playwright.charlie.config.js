const { defineConfig } = require("@playwright/test");

const baseURL = process.env.CHARLIE_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5123";
const serverURL = process.env.CHARLIE_PLAYWRIGHT_SERVER_URL || `${baseURL}/charlie`;
const skipServer = String(process.env.CHARLIE_PLAYWRIGHT_SKIP_SERVER || "").toLowerCase() === "1";

module.exports = defineConfig({
  testDir: "tests",
  testMatch: ["charlie_command_center_playwright.spec.js"],
  timeout: 45000,
  use: {
    baseURL,
    trace: "retain-on-failure",
  },
  webServer: skipServer ? undefined : {
    command: process.env.CHARLIE_PLAYWRIGHT_SERVER_COMMAND || "python -m flask --app app run --host 127.0.0.1 --port 5123",
    url: serverURL,
    reuseExistingServer: true,
    timeout: 120000,
    env: {
      OWNER_ACCESS_ENABLED: "false",
      OWNER_ACCESS_ALLOW_LOCAL_DEV: "1",
    },
  },
});
