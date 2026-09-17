const { test, expect } = require('@playwright/test');
for(const language of ['en','af']){
  test(`confirmed ${language} Telegram welfare record appears once in the animal profile`,async({page},info)=>{
    await page.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort());
    const errors=[];page.on('pageerror',error=>errors.push(error.message));
    await page.goto('/__plan_dialogue_start/'+language);
    await page.getByRole('button',{name:'View confirmed observation'}).click();
    await expect(page).toHaveURL(/\/pig\/PIG-2026-[A-Z0-9]{4}$/);
    const records=page.locator('#welfare_observation_records');
    await expect(records.locator('.profile-record')).toHaveCount(1);
    for(const fact of language==='af'?['Eet: Ja','Staan: Ja','Drink water: Ja']:['Eating: Yes','Standing: Yes','Drinking water: Yes'])await expect(records).toContainText(fact);
    await expect(records).toContainText(language==='af'?'Bloei: Ja':'Bleeding: Yes');
    await expect(records).toContainText(language==='af'?'Oorspronklike verslag: Hy bloei, maar hy eet.':'Original report: He is bleeding, but he is eating.');
    const pig=page.url().split('/').pop();
    const readback=await page.evaluate(async pig=>{const response=await fetch(`/api/pig-weights/pig/${pig}/welfare-observations`);return {status:response.status,body:await response.json()}},pig);
    expect(readback.status).toBe(200);
    const canonical=readback.body;
    expect(canonical.history).toHaveLength(1);
    await expect(records.locator('.profile-record')).toHaveAttribute('data-observation-id',canonical.history[0].observation_event_id);
    await records.scrollIntoViewIfNeeded();await page.screenshot({path:info.outputPath('welfare-desktop.png')});
    await page.setViewportSize({width:390,height:844});await records.scrollIntoViewIfNeeded();
    expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
    await page.screenshot({path:info.outputPath('welfare-mobile.png')});
    await page.reload();await expect(records.locator('.profile-record')).toHaveCount(1);
    expect(errors).toEqual([]);
    await info.attach('canonical-welfare-record',{body:JSON.stringify({classification:'synthetic_gateway_confirmation_and_application_readback',language,pig,canonical}),contentType:'application/json'});
  });
}
