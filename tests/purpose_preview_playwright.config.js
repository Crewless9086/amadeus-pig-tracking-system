const { defineConfig } = require('playwright/test');
module.exports = defineConfig({
  testDir: '.', testMatch: ['pig_allocation_purpose_preview.spec.js'],
  timeout: 15000, workers: 1,
  outputDir: process.env.PURPOSE_PREVIEW_RESULTS || '../test-results/purpose-preview',
  use: { baseURL: 'http://127.0.0.1:5219', trace: 'retain-on-failure',
    launchOptions: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE
      ? { executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE } : {} },
  webServer: { command: `${process.env.PURPOSE_PREVIEW_PYTHON || 'python'} -B -m tests.purpose_preview_server`,
    cwd: require('path').resolve(__dirname, '..'), url: 'http://127.0.0.1:5219/pig-allocation',
    reuseExistingServer: false, timeout: 20000,
    env: { PYTHON_DOTENV_DISABLED: '1', PYTHONDONTWRITEBYTECODE: '1' } },
});
