const { test, expect } = require('@playwright/test');

const baseURL = process.env.HERDMASTER_FIRST_TREATMENT_TEST_URL;
test.skip(!baseURL, 'Requires the disposable loopback first-treatment application');
if (baseURL && !/^http:\/\/(127\.0\.0\.1|localhost):\d+$/.test(baseURL)) throw new Error('Loopback test app required');
test.use({baseURL});

test.beforeEach(async ({context}) => {
  await context.route('**/*', route => {
    const url = new URL(route.request().url());
    return ['127.0.0.1','localhost'].includes(url.hostname) ? route.continue() : route.abort();
  });
});

async function enter(page) {
  await page.goto('/__first_treatment_test_start');
  await page.getByRole('button',{name:'Sign in as synthetic farm manager'}).click();
  await expect(page).toHaveURL(/\/litter\/LIT-FTTEST-/);
  const litter = page.url().split('/').pop();
  await expect(page.locator('#newborn_health_form')).toBeVisible();
  await expect(page.locator('#lifecycle_birth_active')).toHaveText('2');
  const read = async () => (await page.request.get(`/__first_treatment_test_state/${litter}`)).json();
  return {litter,read};
}

async function fillFacts(page,fixture) {
  await page.locator('#newborn_health_date').fill(fixture.date);
  await page.locator('#newborn_health_antiparasitic').selectOption(fixture.product);
  await page.locator('#newborn_health_dose').fill('1 ml');
  await page.locator('#newborn_health_route').fill('injection');
  await page.locator('#newborn_health_batch').fill('SYNTHETIC-BROWSER-LOT');
  await page.locator('#newborn_health_total_count').fill('2');
  await page.locator('#newborn_health_male_count').fill('1');
  await page.locator('#newborn_health_female_count').fill('1');
  await page.locator('#newborn_health_earmarked').selectOption('true');
  await page.locator('#newborn_health_notes').fill('Sintetiese werklike verslag.');
}

test('Afrikaans exact preview on desktop and mobile, then lost-response recovery after reload',async ({page},testInfo) => {
  const errors = [];
  page.on('pageerror',error=>errors.push(error.message));
  const {litter,read} = await enter(page);
  const before = await read();
  await expect(page.locator('#newborn_health_date')).toHaveValue('');
  await expect(page.locator('#newborn_health_antiparasitic')).toHaveValue('');
  await expect(page.locator('#newborn_health_deworming')).toHaveValue('');
  await expect(page.locator('#newborn_health_dose')).toHaveValue('');
  await expect(page.locator('#newborn_health_earmarked')).toHaveValue('');
  await expect(page.locator('#newborn_health_given_by')).toHaveAttribute('readonly','');
  await fillFacts(page,before.fixture);
  await page.locator('#newborn_health_form').scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('form-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#newborn_health_date').scrollIntoViewIfNeeded();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('form-mobile.png')});
  await page.setViewportSize({width:1440,height:1000});
  await page.getByRole('button',{name:'Kontroleer behandeling',exact:true}).click();
  await expect(page.locator('#newborn_health_apply_button')).toBeEnabled();
  await expect(page.locator('#newborn_health_preview')).toContainText('1 ml per varkie');
  await expect(page.locator('#newborn_health_preview')).toContainText('1 manlik, 1 vroulik');
  await expect(page.locator('#newborn_health_preview')).toContainText('Oormerke: aangebring');
  expect(await read()).toEqual(before);
  await page.locator('#newborn_health_preview').scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('preview-desktop.png')});
  await page.setViewportSize({width:390,height:844});
  await page.locator('#newborn_health_preview').scrollIntoViewIfNeeded();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth <= innerWidth+1)).toBe(true);
  await page.screenshot({path:testInfo.outputPath('preview-mobile.png')});
  let committedResponse;
  await page.route(`**/api/pig-weights/litter/${litter}/newborn-health`,async route=>{
    if (route.request().postDataJSON().dry_run === false && !committedResponse) {
      const actual = await route.fetch();
      committedResponse = await actual.json();
      expect(actual.status()).toBe(200);
      expect(committedResponse.canonical_readback_verified).toBe(true);
      return route.fulfill({status:502,contentType:'text/html',body:'SIMULATED response lost after the actual local commit'});
    }
    return route.continue();
  });
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Bevestig en stoor behandeling',exact:true}).click();
  await expect(page.locator('#treatment_recovery')).toBeVisible();
  const committed = await read();
  expect(committed.medical).toHaveLength(2);
  expect(committed.receipts).toHaveLength(1);
  expect(committed.litter).toEqual(before.litter);
  expect(committed.sow).toEqual(before.sow);
  expect(committed.pigs.slice(2)).toEqual(before.pigs.slice(2));
  await page.reload();
  await expect(page.locator('#treatment_recovery')).toBeVisible();
  await page.locator('#treatment_recovery').scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('recovery-mobile.png')});
  await page.getByRole('button',{name:'Herstel bevestiging en lees terug'}).click();
  await expect(page.locator('#treatment_recovery')).toBeHidden();
  await expect(page.locator('#lifecycle_first_care_summary')).toContainText('1 ml per varkie');
  await expect(page.locator('#lifecycle_first_care_summary')).toContainText('SYNTHETIC-BROWSER-LOT');
  await expect(page.locator('#newborn_health_form')).toBeHidden();
  expect(await read()).toEqual(committed);
  await page.locator('#lifecycle_first_care_summary').scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('readback-mobile.png')});
  await page.setViewportSize({width:1440,height:1000});
  await page.locator('#lifecycle_first_care_summary').scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('readback-desktop.png')});
  await expect(page.locator('#lifecycle_identity')).toBeVisible();
  await expect(page.locator('#lifecycle_birth')).toBeVisible();
  await expect(page.locator('#lifecycle_weaning')).toBeVisible();
  await expect(page.locator('#piglet_death_form')).toBeAttached();
  expect(errors).toEqual([]);
});

test('smallest missing fact and correction invalidate preview; explicit skip closes a fresh litter',async ({page},testInfo)=>{
  const {read} = await enter(page);
  const before = await read();
  await fillFacts(page,before.fixture);
  await page.locator('#newborn_health_route').fill('');
  await page.getByRole('button',{name:'Kontroleer behandeling',exact:true}).click();
  await expect(page.locator('#litter_message')).toContainText('toedieningsroete');
  await expect(page.locator('#newborn_health_dose')).toHaveValue('1 ml');
  await expect(page.locator('#newborn_health_apply_button')).toBeDisabled();
  await page.locator('#newborn_health_route').fill('injection');
  await page.getByRole('button',{name:'Kontroleer behandeling',exact:true}).click();
  await expect(page.locator('#newborn_health_apply_button')).toBeEnabled();
  await page.locator('#newborn_health_dose').fill('1,5 ml');
  await expect(page.locator('#newborn_health_apply_button')).toBeDisabled();
  expect(await read()).toEqual(before);
  await page.getByRole('button',{name:'Kontroleer behandeling',exact:true}).click();
  await expect(page.locator('#newborn_health_preview')).toContainText('1.5 ml');
  await page.locator('#newborn_health_skip').check();
  page.once('dialog',dialog=>dialog.accept());
  await page.getByRole('button',{name:'Bevestig oorslaan',exact:true}).click();
  await expect(page.locator('#lifecycle_first_care_summary')).toContainText('oorgeslaan');
  await expect(page.locator('#newborn_health_form')).toBeHidden();
  const skipped = await read();
  expect(skipped.medical).toHaveLength(0);
  expect(skipped.receipts).toHaveLength(0);
  expect(skipped.detail.first_treatment_skipped_by).toBe('7400000001');
  expect(skipped.pigs).toEqual(before.pigs);
  await page.locator('#lifecycle_first_care_summary').scrollIntoViewIfNeeded();
  await page.screenshot({path:testInfo.outputPath('explicit-skip-desktop.png')});
});
