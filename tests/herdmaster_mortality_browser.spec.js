const { test, expect } = require('@playwright/test');

const baseURL = process.env.HERDMASTER_MORTALITY_TEST_URL;
test.skip(!baseURL, 'Requires the isolated mortality PostgreSQL application fixture');
if (baseURL && !/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(baseURL)) {
  throw new Error('Mortality browser tests require a disposable loopback application');
}
test.use({ baseURL });

test('synthetic farm manager reviews, resumes and confirms one real mortality transaction', async ({ page }, testInfo) => {
  await page.route('**/*', route => {
    const url = new URL(route.request().url());
    return ['127.0.0.1','localhost'].includes(url.hostname) ? route.continue() : route.abort();
  });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/__mortality_test_start');
  await page.getByRole('button', { name: 'Sign in as synthetic farm manager' }).click();
  await expect(page).toHaveURL(/\/pig\/PIG-2026-[A-Z0-9]{4}$/);
  const pig = page.url().split('/').pop();
  const read = async () => (await page.request.get(`/api/pig-weights/pig/${pig}`)).json();
  await expect(page.locator('#detail_notes')).toContainText('Preserved browser test history');
  const before = await read();
  expect(before.pig.status).toBe('Active');
  await page.locator('#lifecycle_action_panel summary').click();
  await expect(page.locator('#lifecycle_event_date')).toHaveValue('');
  await page.getByLabel('Afsterwedatum').fill('2026-09-09');
  await page.getByLabel('Wat jy waargeneem het (opsioneel)').fill('Nog nie begrawe nie. Geen oorsaak bekend nie.');
  await page.getByRole('button', { name: 'Hersien afsterwe' }).click();
  await expect(page.locator('#lifecycle_preview')).toContainText('AFSTERWE VOORSKOU');
  await expect(page.locator('#lifecycle_preview')).toContainText('2026-09-09');
  await expect(page.getByRole('button', { name: 'Bevestig hierdie afsterwe' })).toBeVisible();
  expect((await read()).pig.status).toBe('Active');
  await page.screenshot({path:testInfo.outputPath('preview-desktop.png'),fullPage:true});
  await page.reload();
  await page.locator('#lifecycle_action_panel summary').click();
  await expect(page.locator('#lifecycle_preview')).toContainText('2026-09-09');
  await page.setViewportSize({width:390,height:844});
  await page.locator('#lifecycle_preview').scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('preview-mobile.png')});
  await page.getByRole('button', { name: 'Bevestig hierdie afsterwe' }).click();
  await expect(page.locator('#pig_detail_message')).toContainText('bevestigde afsterwe is een keer aangeteken');
  const after = await read();
  expect(after.pig.status).toBe('Dead');
  expect(after.pig.on_farm).toBe('No');
  expect(after.pig.general_notes).toContain('Preserved browser test history');
  await expect(page.locator('#lifecycle_action_panel')).toBeHidden();
  await page.locator('#pig_detail_message').scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('completion-mobile.png')});
  expect(errors).toEqual([]);
  await testInfo.attach('canonical-before-after', {body:JSON.stringify({classification:'terminal_invoked_test_evidence',
    identity:'synthetic farm manager; simulated Telegram signature', pig,before,after},null,2),contentType:'application/json'});
});
