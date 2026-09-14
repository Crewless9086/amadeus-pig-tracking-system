const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir:__dirname,testMatch:'irrigation_dialogue_browser.spec.js',workers:1,timeout:30000,
  outputDir:process.env.IRRIGATION_DIALOGUE_BROWSER_OUTPUT || '../test-results/irrigation-dialogue',
  use:{baseURL:'http://127.0.0.1:55836',trace:'retain-on-failure'},
  webServer:{cwd:require('node:path').resolve(__dirname,'..'),
    command:process.env.IRRIGATION_DIALOGUE_SERVER_COMMAND || 'python tests/irrigation_dialogue_qualification.py serve',
    url:'http://127.0.0.1:55836/__irrigation_dialogue_ready',
    reuseExistingServer:process.env.IRRIGATION_DIALOGUE_BROWSER_REUSE==='1',timeout:120000},
});
