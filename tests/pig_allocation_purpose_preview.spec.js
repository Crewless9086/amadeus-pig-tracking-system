const { test, expect } = require('playwright/test');
const apply = '[data-allocation-review-apply]';
const preview = '#allocation_review_preview';
const previewButton = '[data-allocation-review-preview]';
const endpoint = '**/api/pig-weights/purpose-review/apply';
const first = '[data-review-pig-id="SYNTHETIC-PURPOSE-1"]';
const second = '[data-review-pig-id="SYNTHETIC-PURPOSE-2"]';
const routePath = '/pig-allocation?mode=purpose-review';

async function enter(page, suffix='') {
  const requests = [];
  page.on('request', r => { if (r.method() === 'POST') requests.push(r.url()); });
  await page.goto(routePath + suffix);
  await page.locator(first).click();
  await expect(page.locator(apply)).toBeDisabled();
  return requests;
}
async function produce(page) {
  await page.locator(previewButton).click();
  await expect(page.locator(apply)).toBeEnabled();
}
async function alter(page, edit) {
  await page.route(endpoint, async route => {
    const response = await route.fetch();
    const data = await response.json();
    edit(data);
    await route.fulfill({json:data});
  });
}

for (const width of [1440, 390]) {
  test(`actual producer preview is reviewable at ${width}px without writes`, async ({page}, info) => {
    await page.setViewportSize({width, height:950});
    const requests = await enter(page);
    await page.locator('#allocation_review_note').fill('Keep the reason <visible> & escaped.');
    await produce(page);
    await expect(page.locator(preview)).toContainText('Tag 141');
    await expect(page.locator(preview)).toContainText('Record: SYNTHETIC-PURPOSE-1');
    await expect(page.locator(preview)).toContainText('Current purpose: Unknown');
    await expect(page.locator(preview)).toContainText('New purpose: Grow out');
    await expect(page.locator(preview)).toContainText('Qualifying post-wean weight is recorded');
    await expect(page.locator(preview)).toContainText('Keep the reason <visible> & escaped.');
    expect(requests).toHaveLength(1);
    await page.locator(preview).scrollIntoViewIfNeeded();
    await expect(page.locator(apply)).toBeInViewport();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({path:info.outputPath(`purpose-preview-${width}.png`)});
    page.once('dialog', d => d.dismiss());
    await page.locator(apply).click();
    expect(requests).toHaveLength(1);
  });
}

const broken = {
  legacy: d => { d.approved = d.effects; delete d.effects; },
  empty: d => { d.effects = []; },
  multiple: d => { d.effects.push(d.effects[0]); },
  decision_missing: d => { d.decisions = []; },
  decision_mismatch: d => { d.decisions[0].purpose = 'Sale'; },
  pig_mismatch: d => { d.effects[0].pig_id = 'OTHER'; },
  tag_mismatch: d => { d.effects[0].tag_number = '999'; },
  purpose_mismatch: d => { d.effects[0].new_purpose = 'Sale'; },
  old_purpose_stale: d => { d.effects[0].old_purpose = 'Breeding'; },
  missing_reason: d => { delete d.effects[0].reason; },
  changed_note: d => { d.effects[0].note = 'not reviewed'; },
  partial_effect: d => { delete d.effects[0].latest_weight_date; },
  inactive: d => { d.effects[0].status = 'Sold'; },
  off_farm: d => { d.effects[0].on_farm = false; },
  binding_missing: d => { delete d.confirmation_binding; },
  unsigned: d => { d.confirmation_binding.signature = ''; },
  digest_mismatch: d => { d.confirmation_binding.preview_digest = '0'.repeat(64); },
  missing_actor: d => { d.confirmation_binding.actor_id = ''; },
  expired: d => { d.confirmation_binding.issued_at -= 1801; },
  future: d => { d.confirmation_binding.issued_at += 60; },
  wrong_contract: d => { d.contract_version = 'legacy'; },
  wrong_count: d => { d.approved_count = 2; },
  unsafe_return: d => { d.return_to = 'https://example.invalid'; },
  false_success: d => { d.success = false; },
};
for (const [name, edit] of Object.entries(broken)) {
  test(`refuses ${name} producer response without a batch request`, async ({page}) => {
    const requests = await enter(page);
    await alter(page, edit);
    await page.locator(previewButton).click();
    await expect(page.locator(preview)).toContainText('complete matching preview is unavailable');
    await expect(page.locator(apply)).toBeDisabled();
    expect(requests).toHaveLength(1);
  });
}

for (const mutation of ['purpose', 'note', 'selection', 'roundtrip', 'reload']) {
  test(`in-flight ${mutation} invalidates even a later successful response`, async ({page}) => {
    await enter(page);
    let release, seen;
    const arrived = new Promise(r => { seen=r; });
    const gate = new Promise(r => { release=r; });
    await page.route(endpoint, async route => { const response=await route.fetch(); seen(); await gate; await route.fulfill({response}); });
    await page.locator(previewButton).click();
    await arrived;
    await expect(page.locator(preview)).toContainText('Loading');
    await expect(page.locator(apply)).toBeDisabled();
    if (mutation==='purpose') await page.locator('#allocation_review_purpose_choice').selectOption('Sale');
    if (mutation==='note') await page.locator('#allocation_review_note').fill('changed');
    if (mutation==='selection' || mutation==='roundtrip') await page.locator(second).click();
    if (mutation==='roundtrip') await page.locator(first).click();
    if (mutation==='reload') await page.evaluate(() => loadAllocationReadiness());
    release();
    await page.waitForResponse(r => r.url().includes('/purpose-review/apply'));
    await expect(page.locator(apply)).toBeDisabled();
    await expect(page.locator(preview)).not.toContainText('Review purpose change');
  });
}

test('newer preview wins over older success or failure', async ({page}) => {
  await enter(page);
  let release, seen; let count=0;
  const arrived=new Promise(r=>seen=r), gate=new Promise(r=>release=r);
  await page.route(endpoint, async route => {
    const response=await route.fetch();
    if (++count===1) { seen(); await gate; await route.fulfill({status:503,json:{success:false}}); }
    else await route.fulfill({response});
  });
  await page.locator(previewButton).click(); await arrived;
  await page.locator('#allocation_review_note').fill('new intent');
  await produce(page); release();
  await expect(page.locator(preview)).toContainText('new intent');
  await expect(page.locator(apply)).toBeEnabled();
});

test('expiry and silent form change are rechecked before Apply', async ({page}) => {
  await page.clock.install();
  const requests=await enter(page); await produce(page);
  await page.evaluate(() => { document.querySelector('#allocation_review_note').value='silent change'; });
  await page.evaluate(() => submitAllocationPurposeDecision(false));
  await expect(page.locator(apply)).toBeDisabled(); expect(requests).toHaveLength(1);
  await produce(page);
  await page.clock.fastForward(1801000);
  await expect(page.locator(apply)).toBeDisabled();
  expect(requests).toHaveLength(2);
});

test('failed preview never restores a preceding valid preview', async ({page}) => {
  await enter(page); await produce(page);
  await page.route(endpoint, route => route.fulfill({status:503,json:{success:false}}));
  await page.locator(previewButton).click();
  await expect(page.locator(preview)).toContainText('unavailable');
  await expect(page.locator(apply)).toBeDisabled();
});

test('explicit confirmation freezes one create/approve/execute sequence and return context', async ({page}) => {
  await enter(page, '&return_to=%2Forders%2FORD-123'); await produce(page);
  let release, seen;
  const arrived=new Promise(r=>seen=r), gate=new Promise(r=>release=r);
  const sent=[];
  await page.route('**/api/pig-weights/purpose-review/correction-batches**', async route => {
    sent.push({url:route.request().url(), body:route.request().postDataJSON()});
    if (sent.length===1) { seen(); await gate; return route.fulfill({json:{success:true,batch_id:'SYNTHETIC-BATCH'}}); }
    if (sent.length===2) return route.fulfill({json:{success:true}});
    return route.fulfill({json:{success:true,per_pig_results:[{pig_id:'SYNTHETIC-PURPOSE-1',tag_number:'141',available:true}]}});
  });
  await page.route('**/orders/ORD-123', r=>r.fulfill({contentType:'text/html',body:'Synthetic order return'}));
  page.once('dialog', d=>d.accept()); await page.locator(apply).click(); await arrived;
  await expect(page.locator(apply)).toBeDisabled();
  await expect(page.locator('#allocation_review_purpose_choice')).toBeDisabled();
  await expect(page.locator(second)).toBeDisabled();
  await page.evaluate(() => { submitAllocationPurposeDecision(false); resetAllocationReviewPreview(); });
  release(); await expect(page).toHaveURL(/\/orders\/ORD-123$/);
  expect(sent.map(r=>r.url.split('/').pop())).toEqual(['correction-batches','approve','execute']);
  expect(sent[0].body.decisions).toEqual([{pig_id:'SYNTHETIC-PURPOSE-1',purpose:'Grow_Out',reason:'Qualifying post-wean weight is recorded; owner purpose decision required.',note:''}]);
  expect(sent[0].body.confirmation_binding.signature).toMatch(/^[a-f0-9]{64}$/);
  expect(sent[0].body.return_to).toBe('/orders/ORD-123');
  expect(sent[0].body.idempotency_key).toMatch(/^purpose-correction-/);
});
for (const outcome of ['success', 'network failure']) {
  test(`obsolete preview ${outcome} cannot unlock a newer Apply`, async ({page}) => {
    await enter(page);
    let releaseOld, oldSeen, releaseCreate, createSeen; let previews=0, creates=0;
    const oldGate=new Promise(r=>releaseOld=r), arrivedOld=new Promise(r=>oldSeen=r);
    const createGate=new Promise(r=>releaseCreate=r), arrivedCreate=new Promise(r=>createSeen=r);
    await page.route(endpoint, async route => {
      const response=await route.fetch();
      if (++previews===1) { oldSeen(); await oldGate;
        if (outcome==='network failure') return route.abort();
      }
      return route.fulfill({response});
    });
    await page.locator(previewButton).click(); await arrivedOld;
    await page.locator('#allocation_review_note').fill('newer reviewed intent'); await produce(page);
    await page.route('**/api/pig-weights/purpose-review/correction-batches**', async route => {
      if (route.request().url().endsWith('/correction-batches')) {
        creates++; createSeen(); await createGate;
        return route.fulfill({status:409,json:{success:false,status:'synthetic stale canonical record'}});
      }
      throw new Error('No approval follows a rejected creation');
    });
    page.once('dialog', d=>d.accept()); await page.locator(apply).click(); await arrivedCreate;
    const settled=page.waitForEvent(outcome==='network failure' ? 'requestfailed' : 'response',
      r=>r.url().includes('/purpose-review/apply'));
    releaseOld(); await settled;
    await page.locator('#search_filter').fill('141');
    await page.evaluate(() => submitAllocationPurposeDecision(false));
    await expect(page.locator(apply)).toBeDisabled();
    await expect(page.locator(previewButton)).toBeDisabled();
    await expect(page.locator(first)).toBeDisabled();
    expect(creates).toBe(1);
    releaseCreate(); await expect(page.locator(preview)).toContainText('synthetic stale canonical record');
    await expect(page.locator(apply)).toBeDisabled();
  });
}

test('saved correction is distinguished from failed subsequent readback', async ({page}) => {
  await enter(page); await produce(page);
  const sent=[];
  await page.route('**/api/pig-weights/purpose-review/correction-batches**', async route => {
    sent.push(route.request().url());
    return route.fulfill({json:sent.length===1 ? {success:true,batch_id:'SYNTHETIC-BATCH'} : {success:true,per_pig_results:[]}});
  });
  await page.route('**/api/pig-weights/pig-allocation-readiness', route => route.fulfill({status:503,json:{success:false}}));
  page.once('dialog', d=>d.accept()); await page.locator(apply).click();
  await expect(page.locator('#allocation_message')).toContainText('Purpose saved. Latest records could not be loaded');
  await expect(page.locator(apply)).toBeDisabled(); expect(sent).toHaveLength(3);
});

test('allocation refresh preserves an existing auction evidence panel', async ({page}) => {
  const requests=await enter(page);
  // Exercise the adjacent renderer with the same selected canonical fixture row;
  // unavailable auction evidence stays unknown and never gains write authority.
  await page.evaluate(() => auctionListIds.add('SYNTHETIC-PURPOSE-1'));
  await page.selectOption('#bucket_filter', 'Auction List');
  await page.locator(first).click();
  await expect(page.locator('#auction_review_observation')).toBeVisible();
  await page.evaluate(() => loadAllocationReadiness());
  await expect(page.locator('#auction_review_observation')).toBeVisible();
  await expect(page.locator(previewButton)).toHaveCount(0);
  expect(requests).toHaveLength(0);
});
