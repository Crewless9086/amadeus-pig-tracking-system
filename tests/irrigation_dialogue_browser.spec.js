const { test, expect } = require('@playwright/test');
test('application reads the same water observations and keeps a reported stop separate from execution completion',async({page},info)=>{
  await page.route('**/*',route=>['127.0.0.1','localhost'].includes(new URL(route.request().url()).hostname)?route.continue():route.abort());
  const errors=[];page.on('pageerror',error=>errors.push(error.message));
  await page.goto('/__irrigation_dialogue_start');
  await page.getByRole('button',{name:'View irrigation evidence'}).click();
  await expect(page).toHaveURL(/\/irrigation$/);
  // A farm Telegram session does not grant the separately protected owner
  // panel. Use the fixture's existing read-only owner credential via its UI.
  expect(await page.evaluate(async()=> (await fetch('/api/telemetry/irrigation/status')).status)).toBe(403);
  await page.goto('/owner/login?next=/irrigation');
  await page.getByLabel('Owner token').fill('synthetic-read-only-'+'r'.repeat(40));
  await page.getByRole('button',{name:'Unlock'}).click();
  await expect(page).toHaveURL(/\/irrigation$/);
  const readback=await page.evaluate(async()=>{const response=await fetch('/api/telemetry/irrigation/status');return {status:response.status,body:await response.json()};});
  expect(readback.status).toBe(200);
  expect(readback.body.water_evidence.storage_fraction).toEqual([1,1]);
  expect(readback.body.water_evidence.reservoir_fraction).toEqual([1,2]);
  expect(readback.body.current.shutdown_verified).toBe(false);
  expect(readback.body.zones.find(row=>row.zone_id==='C12345').lifecycle.state).toBe('Started');
  expect(readback.body.safety.hardware_commands_enabled).toBe(false);
  // The new owner page presents the same canonical source through the owner-
  // controls projection. Keep this historical gateway journey read-only and
  // bind its UI fixture to the actual canonical read above, not invented runs.
  await page.route('**/api/telemetry/rootline/owner-controls?*', route => {
    const panel=new URL(route.request().url()).searchParams.get('panel');
    const devices=readback.body.zones.map(zone=>({id:zone.zone_id,name:zone.zone_id==='C12345'?'Camp C':zone.zone_id==='B12345'?'Camp B':zone.zone_id,state:zone.lifecycle.state,state_basis:'Canonical gateway qualification fixture',summary:'Read-only canonical execution evidence',settings:{revision:null,mode:null,scope:null,fields:[],reason:'Read-only qualification; no hardware authority.'},actions:{run:{supported:false},stop:{supported:false}}}));
    const panels={devices,forecast:{status:'unavailable',days:[],reason:'Forecast not part of this gateway fixture.'},plan:{status:'unavailable',rows:[],reason:'No day-plan mutation in this read-only journey.'},history:[]};
    return route.fulfill({json:{success:true,owner_can_administer:false,constraints:['Canonical shutdown verified: '+readback.body.current.shutdown_verified], [panel]:panels[panel]}});
  });
  await page.reload();
  await expect(page.getByRole('heading',{name:'Your irrigation day'})).toBeVisible();
  await page.getByRole('button',{name:/Camp C.*Open details/}).click();
  await expect(page.locator('#rl-facts')).toContainText('Started');
  await expect(page.getByRole('button',{name:'Request one run'})).toBeDisabled();
  await expect(page.locator('#rl-access')).toContainText('View only');
  await expect(page.locator('#rl-constraints')).toContainText('shutdown verified: false');
  await page.screenshot({path:info.outputPath('irrigation-desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  await page.screenshot({path:info.outputPath('irrigation-mobile.png'),fullPage:true});
  const layout=await page.evaluate(()=>({viewport:window.innerWidth,width:document.documentElement.scrollWidth,
    overflowing:[...document.querySelectorAll('body *')].filter(node=>node.getBoundingClientRect().right>window.innerWidth)
      .map(node=>({tag:node.tagName,id:node.id,className:node.className,width:node.getBoundingClientRect().width})).slice(0,30)}));
  await info.attach('mobile-layout',{body:JSON.stringify(layout),contentType:'application/json'});
  expect(layout.width).toBeLessThanOrEqual(layout.viewport);
  await page.reload();await page.getByRole('button',{name:/Camp C.*Open details/}).click();await expect(page.locator('#rl-facts')).toContainText('Started');
  expect(errors).toEqual([]);
  await info.attach('canonical-irrigation-readback',{body:JSON.stringify({classification:'synthetic_gateway_observations_and_execution_fixture_no_physical_irrigation',canonical:readback.body}),contentType:'application/json'});
});
