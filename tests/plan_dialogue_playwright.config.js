const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: __dirname, testMatch: 'plan_dialogue_browser.spec.js', workers: 1,
  timeout: 30000, outputDir: process.env.PLAN_DIALOGUE_BROWSER_OUTPUT || '../test-results/plan-dialogue',
  use: {baseURL:'http://127.0.0.1:55826',trace:'retain-on-failure'},
  webServer: {cwd:require('node:path').resolve(__dirname,'..'),
    command:process.env.PLAN_DIALOGUE_SERVER_COMMAND || 'python tests/plan_dialogue_qualification.py serve',
    url:'http://127.0.0.1:55826/__plan_dialogue_ready',reuseExistingServer:false,timeout:120000},
});
