const { defineConfig } = require('@playwright/test');

if (!process.env.HERDMASTER_QUALIFICATION_POSTGRES_URL) {
  throw new Error('Explicit disposable herd database is required; this suite must not skip');
}
const baseURL = 'http://127.0.0.1:55821';
process.env.HERDMASTER_FIRST_TREATMENT_TEST_URL = baseURL;
process.env.HERDMASTER_WEANING_TEST_URL = baseURL;

module.exports = defineConfig({
  testDir: 'tests',
  testMatch: ['litter_first_treatment_browser.spec.js', 'litter_weaning_day_browser.spec.js'],
  outputDir: 'test-results/herd',
  reporter: [['list'], ['json', { outputFile: 'test-results/herd-results.json' }]],
  workers: 1,
  timeout: 60000,
  use: { baseURL, viewport: { width: 1440, height: 1000 }, trace: 'retain-on-failure' },
  webServer: {
    command: process.env.HERDMASTER_QUALIFICATION_SERVER_COMMAND || 'python -m tests.herd_qualification serve',
    url: `${baseURL}/__herd_test_ready`,
    reuseExistingServer: false,
    timeout: 120000,
  },
});
