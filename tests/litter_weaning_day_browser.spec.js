const { test, expect } = require("@playwright/test");
const fs = require("fs");

const source = fs.readFileSync("static/js/litterDetail.js", "utf8");
const helper = source.match(
  /async function readWeaningDayResponse\(response\) \{[\s\S]*?\n\}/
);

test.beforeEach(async ({ page }) => {
  expect(helper).not.toBeNull();
  await page.setContent("<main>Weaning Day response harness</main>");
  await page.addScriptTag({content: helper[0]});
});

test("non-JSON failure gives no-retry recovery guidance", async ({ page }) => {
  const result = await page.evaluate(async () => {
    const response = new Response("<html>worker timeout</html>", {
      status: 500,
      headers: {"content-type": "text/html", "x-request-id": "REQ-SAFE"},
    });
    try {
      await readWeaningDayResponse(response);
      return {accepted: true};
    } catch (error) {
      return {accepted: false, message: error.message};
    }
  });
  expect(result.accepted).toBe(false);
  expect(result.message).toContain("herstel");
  expect(result.message).toContain("speenuitslag");
  expect(result.message).toContain("REQ-SAFE");
  expect(result.message).not.toContain("<html>");
});

test.describe('real isolated application and PostgreSQL', () => {
  const baseURL = process.env.HERDMASTER_WEANING_TEST_URL;
  test.skip(!baseURL, 'Requires the disposable loopback weaning application fixture');
  if (baseURL && !/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(baseURL)) throw new Error('Loopback test app required');
  test.use({baseURL});

  test('Afrikaans manager previews optional facts and recovers a lost commit response after reload', async ({page}, testInfo) => {
    await page.route('**/*', route => {
      const url = new URL(route.request().url());
      return ['127.0.0.1','localhost'].includes(url.hostname) ? route.continue() : route.abort();
    });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('/__weaning_test_start');
    await page.getByRole('button', {name:'Sign in as synthetic farm manager'}).click();
    await expect(page).toHaveURL(/\/litter\/LIT-WTEST-/);
    const litter = page.url().split('/').pop();
    const read = async () => (await page.request.get(`/__weaning_test_state/${litter}`)).json();
    await expect(page.locator('.piglet-wean-weight-input')).toHaveCount(2);
    const before = await read();
    await expect(page.locator('#weaning_day_date')).toHaveValue('');
    await expect(page.locator('#weaning_day_antiparasitic')).toHaveValue('');
    await expect(page.locator('#weaning_day_dose')).toHaveValue('');
    const denied = await page.request.post(`/api/pig-weights/litter/${litter}/weaning-day`, {data:{dry_run:false}});
    expect(denied.status()).toBe(403);
    await page.locator('#weaning_day_date').fill('2026-09-10');
    await page.locator('#weaning_day_notes').fill('Al die huidige varkies drink water.');
    await page.getByRole('button', {name:'Kontroleer speen', exact:true}).click();
    await expect(page.locator('#weaning_day_apply_button')).toBeEnabled();
    await expect(page.locator('#weaning_day_preview')).toContainText('2 varkies');
    await expect(page.locator('#weaning_day_preview')).toContainText('gewig nie opgegee nie');
    await expect(page.locator('#weaning_day_preview')).toContainText('Geen behandeling opgegee nie');
    expect(await read()).toEqual(before);
    await page.locator('#weaning_day_preview').scrollIntoViewIfNeeded();
    await page.screenshot({path:testInfo.outputPath('preview-desktop.png')});
    await page.setViewportSize({width:390,height:844});
    await page.locator('#weaning_day_preview').scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    await page.screenshot({path:testInfo.outputPath('preview-mobile.png')});
    let committedResponse;
    await page.route(`**/api/pig-weights/litter/${litter}/weaning-day`, async route => {
      const payload = route.request().postDataJSON();
      if (payload.dry_run === false && !committedResponse) {
        const response = await route.fetch();
        committedResponse = await response.json();
        return route.abort('connectionreset');
      }
      return route.continue();
    });
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', {name:'Bevestig en voltooi speen', exact:true}).click();
    await expect(page.locator('#weaning_recovery')).toBeVisible();
    expect(committedResponse, JSON.stringify(committedResponse)).toMatchObject({canonical_readback_verified:true});
    expect((await read()).receipts).toBe(1);
    await page.reload();
    await expect(page.locator('#weaning_recovery')).toBeVisible();
    await expect(page.locator('#weaning_recovery_details')).toContainText('2026-09-10');
    await page.locator('#weaning_recovery').scrollIntoViewIfNeeded();
    await page.screenshot({path:testInfo.outputPath('recovery-mobile.png')});
    await page.getByRole('button', {name:'Herstel hierdie bevestiging'}).click();
    await expect(page.locator('#litter_message')).toContainText('Speen is gestoor en teruggelees: 2 varkies');
    await expect(page.locator('#weaning_recovery')).toBeHidden();
    await expect(page.locator('#closed_male_count')).toHaveText('Onbekend');
    await expect(page.locator('#closed_female_count')).toHaveText('Onbekend');
    const after = await read();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
    expect(after.receipts).toBe(1);
    expect(after.active_herd).toBe(before.active_herd);
    expect(after.sow).toEqual(before.sow);
    expect(after.pigs.slice(2)).toEqual(before.pigs.slice(2));
    expect(after.pigs[0].slice(5,8)).toEqual([null,null,null]);
    await page.locator('#litter_message').scrollIntoViewIfNeeded();
    await page.screenshot({path:testInfo.outputPath('completion-mobile.png')});
    await page.setViewportSize({width:1440,height:1000});
    await page.screenshot({path:testInfo.outputPath('completion-desktop.png')});
    expect(errors).toEqual([]);
    await testInfo.attach('canonical-before-after', {body:JSON.stringify({classification:'terminal_invoked_test_evidence',
      identity:'Synthetic manager; simulated Telegram login signature', litter,before,after,committedResponse},null,2),contentType:'application/json'});
  });
});

test("structured JSON remains available to the existing workflow", async ({ page }) => {
  const result = await page.evaluate(async () => {
    const response = new Response(JSON.stringify({
      success: false,
      status: "weaning_day_transaction_failed",
    }), {
      status: 503,
      headers: {"content-type": "application/json; charset=utf-8"},
    });
    return readWeaningDayResponse(response);
  });
  expect(result).toEqual({
    success: false,
    status: "weaning_day_transaction_failed",
  });
});
