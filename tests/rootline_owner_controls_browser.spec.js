const {test,expect}=require('@playwright/test');
const fs=require('node:fs');const path=require('node:path');
const source=path.resolve(__dirname,'..');
const base=process.env.ROOTLINE_UI_BASE_URL || 'http://127.0.0.1:18044';
test.beforeEach(async({page})=>{if(process.env.ROOTLINE_OWNER_BROWSER_SEED==='1'){const seed=await(await page.request.get(base+'/__irrigation_dialogue_ready')).json();await page.clock.install({time:new Date(seed.owner_fixture_now)});}});
function fixtureFields(id){
 const number=(key,label,value,unit,min,max,editable=true)=>({key,label,type:'number',value,unit,min,max,editable});
 if(id.startsWith('camp_'))return [number('duration_minutes','Run duration',30,'minutes',1,120)];
 const fields={
 mixer:[number('maximum_session_minutes','Hard device timing ceiling',10,'minutes',null,null,false),number('maximum_daily_minutes','Hard daily ceiling',30,'minutes',null,null,false),number('reserve_soc_pct','Battery reserve for mixing',70,'%',50,100),number('session_minutes','Maximum new mixing session',10,'minutes',1,10),number('daily_minutes','Maximum mixing time per day',30,'minutes',1,30)],
 injection:[number('pulse_minutes','Injection duration',2,'minutes',1,10),number('pulses_per_60_minutes','Injections per 60 minutes',2,'injections',1,2),...['a','b','c','e'].map(c=>({key:'inject_camp_'+c,label:'Inject during Camp '+c.toUpperCase(),type:'checkbox',value:['b','c'].includes(c),editable:true}))],
 borehole:[number('solar_proxy_w','Solar level to stop AC backup',1500,'W',1,null),number('battery_floor_pct','Battery floor without grid supply',30,'%',0,100)],
 eskom:[number('on_soc_pct','Grid ON at battery level',30,'%',0,99),number('off_soc_pct','Grid OFF after solar recovery',35,'%',1,100)]};
 return fields[id];
}
function fixture(){
 const now='2026-11-25T16:10:00+00:00';
 const identities=[['camp_a','Camp A'],['camp_b','Camp B'],['camp_c','Camp C'],['camp_e','Camp E'],['mixer','Mixer'],['injection','Injection'],['borehole','Borehole'],['eskom','Eskom']];
 return {success:true,status:'available',contract_version:'rootline_owner_controls.v1',csrf_token:'fixture-csrf',owner_can_administer:true,observed_at:now,timezone:'Africa/Johannesburg',constraints:['Faithful browser contract fixture. No live settings or hardware effects.'],forecast:{status:'available',source:'Recorded forecast fixture',forecast_run_at:now,days:[0,1,2].map((offset)=>({date:'2026-11-'+(25+offset),temp_min_c:14,temp_max_c:25+offset,rain_mm:offset,rain_probability_pct:20,wind_kmh:12,source:'Recorded forecast fixture',forecast_run_at:now}))},devices:identities.map(([id,name])=>({id,name,state:'off_command_accepted',state_basis:'Home Assistant service call accepted',observed_at:now,next_action:id==='injection'?'During an eligible B/C run':'When current conditions allow',summary:id==='mixer'?'Daily controller target; credited time retained':id==='borehole'?'AC backup; pumping is not inferred':'Current operating policy',settings:{revision:'settings-v1',mode:'automatic',scope:'ongoing',fields:fixtureFields(id),reason:'Existing runtime limits and shutdown duties remain in place.'},actions:{run:{supported:true,reason:'Uses the current plan duration and current eligibility.'},stop:{supported:true,reason:'Requests the existing ROOTLINE stop action.'}}})),plan:{status:'saved',revision:'plan-v1',operating_date:'2026-11-25',reason:'Saved daily programme',rows:identities.slice(0,4).map(([id,name],i)=>({id:'row-'+id,device_id:id,name,order:i+1,duration_minutes:30,priority:'normal',reason:'Current crop requirement',skip:false,start_at:'2026-11-25T'+String(7+i).padStart(2,'0')+':00:00+02:00',end_at:'2026-11-25T'+String(7+i).padStart(2,'0')+':30:00+02:00',editable:true}))},history:identities.map(([id])=>({id:'event-'+id,at:now,device_id:id,kind:'run_stopped',summary:'OFF command accepted; controller time retained',actor:'ROOTLINE',status:'command_accepted'}))};
}
async function setup(page,options={}){
 const data=fixture();if(options.data)options.data(data);const requests=[];let previewBody;
 await page.route('**/*',async route=>{
  const request=route.request();const url=new URL(request.url());if(url.origin!==base)return route.abort();
  if(url.pathname.startsWith('/api/telemetry/rootline/owner-controls')){
   requests.push({method:request.method(),path:url.pathname,body:request.postDataJSON(),headers:request.headers()});
   if(url.pathname.endsWith('/preview')){previewBody=request.postDataJSON();if(options.previewDelay)await new Promise(resolve=>setTimeout(resolve,options.previewDelay));return route.fulfill({json:{success:true,status:'review',preview:{id:'review-1',digest:'digest-1',changes:[{label:previewBody.kind==='plan'?'Camp order':'Maximum mixing time per day',before:30,after:20}],effective_at:'2026-11-25T16:11:00Z',expires_at:'2099-11-25T16:20:00Z',warnings:['Checked against current operating limits.']}}});}
   if(url.pathname.endsWith('/apply')){
    if(options.rejectApply){const reject=options.rejectApply;options.rejectApply=null;return route.fulfill({status:409,json:{success:false,message:reject}});}if(options.ambiguous)return route.fulfill({json:{success:true,status:'unknown',readback_bound:false,message:'Readback unavailable.'}});
    if(previewBody.kind==='settings'){const d=data.devices.find(x=>x.id===previewBody.device_id);d.settings.revision='settings-v2';d.settings.mode=previewBody.changes.mode;d.settings.scope=previewBody.changes.scope;d.settings.fields.forEach(f=>{if(Object.hasOwn(previewBody.changes.fields,f.key))f.value=previewBody.changes.fields[f.key];});}
    if(previewBody.kind==='plan'){data.plan.revision='plan-v2';data.plan.rows=previewBody.changes.rows.map(row=>({...data.plan.rows.find(x=>x.id===row.id),...row,start_at:null,end_at:null}));}
    data.history.unshift({id:'change-1',at:'2026-11-25T16:11:00Z',device_id:previewBody.device_id||'plan',kind:previewBody.kind==='settings'?'settings_changed':previewBody.kind==='plan'?'plan_changed':'request_queued',summary:'Canonical fixture readback',actor:'Owner',status:'accepted'});
    return route.fulfill({json:{success:true,status:['run','stop'].includes(previewBody.kind)?'queued':'applied',readback_bound:true,revision:previewBody.kind==='plan'?'plan-v2':'settings-v2',effective_at:'2026-11-25T16:11:00Z'}});
   }
   const panel=url.searchParams.get('panel');if(options.failPanel===panel)return route.fulfill({status:503,json:{success:false,message:panel+' unavailable for this check'}});
   return route.fulfill({json:{success:true,owner_can_administer:data.owner_can_administer,csrf_token:data.csrf_token,observed_at:data.observed_at,constraints:data.constraints,[panel]:data[panel]}});
  }
  if(process.env.ROOTLINE_UI_BASE_URL && (url.pathname==='/irrigation'||url.pathname==='/owner/login'||url.pathname.startsWith('/static/')))return route.continue();
  if(url.pathname.startsWith('/static/')){const file=path.join(source,url.pathname);return route.fulfill({body:fs.readFileSync(file),contentType:file.endsWith('.css')?'text/css':'application/javascript'});}
  if(url.pathname==='/irrigation'){
   let nav=fs.readFileSync(path.join(source,'templates/_farm_nav.html'),'utf8').replace(/{% if owner_session_valid %}[\s\S]*?{% else %}/,'').replace(/{% endif %}/,'').replace(/{{ request.path\|urlencode }}/g,'%2Firrigation');
   let html=fs.readFileSync(path.join(source,'templates/irrigation.html'),'utf8').replace(/{% include '_farm_nav.html' %}/,nav).replace(/{{ url_for\('static', filename='([^']+)'\) }}/g,'/static/$1').replace(/{{ rootline_csrf_token\|default\('', true\) }}/g,'');
   return route.fulfill({body:html,contentType:'text/html'});
  }
  return route.fulfill({status:404,body:'Not part of this fixture'});
 });
 await page.goto(base+'/irrigation');if(new URL(page.url()).pathname==='/owner/login'){await page.getByLabel('Owner token').fill('synthetic-admin-only-'+'a'.repeat(40));await page.getByRole('button',{name:'Unlock'}).click();}await expect(page.locator('#rl-tiles .rl-tile')).toHaveCount(8);await expect(page.locator('#rl-input-state')).not.toContainText('Reading');return {data,requests};
}
async function noOverflow(page){expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);}
test('approved hierarchy, all input details, plan editing, history and desktop/mobile evidence',async({page},info)=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));const {requests}=await setup(page);
 await expect(page.locator('#rl-forecast .rl-weather')).toHaveCount(3);await expect(page.locator('#rl-plan-rows tr')).toHaveCount(4);
 await page.getByRole('button',{name:/Mixer.*Open details/}).click();await expect(page.locator('#rl-detail-title')).toHaveText('Mixer');await expect(page.locator('#rl-facts')).toContainText('Saved mode');await expect(page.locator('#rl-settings [data-key="maximum_session_minutes"]')).toBeDisabled();
 await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:info.outputPath('desktop-input-details.png'),fullPage:true});await noOverflow(page);
 await page.locator('#rl-settings [data-key="daily_minutes"]').fill('20');await page.getByLabel('Reason for the change').fill('Adjust daily requirement');await page.getByRole('button',{name:'Review setting changes'}).click();await expect(page.locator('#rl-setting-review')).toContainText('30 → 20');
 await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:info.outputPath('desktop-review.png'),fullPage:true});await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.locator('#rl-detail-status')).toContainText('Saved · revision settings-v2');await expect(page.locator('#rl-settings [data-key="daily_minutes"]')).toHaveValue('20');
 await page.getByRole('button',{name:'Move Camp B earlier'}).click();await expect(page.locator('#rl-plan-rows tr').first()).toContainText('Camp B');await page.getByRole('button',{name:'Skip Camp E today'}).click();await page.getByRole('button',{name:'Review day plan'}).click();await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.locator('#rl-plan-status')).toContainText('plan-v2');
 await page.getByRole('button',{name:'View history',exact:true}).click();await expect(page.locator('#rl-history')).toBeVisible();await expect(page.locator('#rl-history-filter')).toHaveValue('mixer');
 await page.setViewportSize({width:390,height:844});await page.getByRole('tab',{name:'Day plan & camps'}).click();await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:info.outputPath('mobile-input-details.png'),fullPage:true});await noOverflow(page);
 await page.getByRole('button',{name:'Close details'}).click();await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:info.outputPath('mobile-overview.png'),fullPage:true});await noOverflow(page);
 expect(errors).toEqual([]);expect(requests.filter(r=>r.method==='POST')).toHaveLength(4);expect(requests.filter(r=>r.method==='POST').every(r=>r.headers['x-rootline-csrf']==='fixture-csrf')).toBe(true);
 await info.attach('fixture-classification',{body:JSON.stringify({classification:'actual_changed_template_and_assets_with_faithful_non_actuating_API_contract_fixture',requests}),contentType:'application/json'});
});
test('failed readback retains draft and never announces saved',async({page})=>{
 await setup(page,{ambiguous:true});await page.getByRole('button',{name:/Mixer.*Open details/}).click();await page.locator('#rl-settings [data-key="daily_minutes"]').fill('22');await page.getByLabel('Reason for the change').fill('Test retained draft');await page.getByRole('button',{name:'Review setting changes'}).click();await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.locator('#rl-detail-status')).toContainText('Readback unavailable');await expect(page.locator('#rl-detail-status')).not.toContainText('Saved');await expect(page.locator('#rl-settings [data-key="daily_minutes"]')).toHaveValue('22');
});
test('independent forecast failure leaves devices and plan useful',async({page},info)=>{
 await setup(page,{failPanel:'forecast'});await expect(page.locator('#rl-forecast')).toContainText('unavailable');await page.getByRole('button',{name:/Borehole.*Open details/}).click();await expect(page.getByRole('button',{name:'Review setting changes'})).toBeEnabled();await expect(page.locator('#rl-plan-rows tr')).toHaveCount(4);await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:info.outputPath('forecast-unavailable.png'),fullPage:true});
});
test('manual request stays queued without claiming running or stopped',async({page})=>{
 const {requests}=await setup(page);await page.getByRole('button',{name:/Injection.*Open details/}).click();await page.getByRole('button',{name:'Request one run'}).click();await page.locator('#rl-manual-reason').fill('Owner requested eligible pulse');await page.getByRole('button',{name:'Review request'}).click();await page.getByRole('button',{name:'Confirm request'}).click();await expect(page.locator('#rl-detail-status')).toContainText('Request queued');await expect(page.locator('#rl-detail-status')).not.toContainText('running');expect(requests.filter(r=>r.method==='POST')).toHaveLength(2);
});
test('read only owner and absent values remain unavailable with no guessed policy',async({page},info)=>{
 await setup(page,{data:data=>{data.owner_can_administer=false;data.forecast.days=[];data.plan.rows=[];data.history=[];data.devices[0].settings.fields[0].value=null;}});await page.getByRole('button',{name:/Camp A.*Open details/}).click();await expect(page.locator('#rl-settings [data-key="duration_minutes"]')).toHaveValue('');await expect(page.getByRole('button',{name:'Review setting changes'})).toBeDisabled();await expect(page.locator('#rl-access')).toContainText('View only');await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:info.outputPath('read-only-empty.png'),fullPage:true});
});
test('editing during preview invalidates the pending review',async({page})=>{
 await setup(page,{previewDelay:500});await page.getByRole('button',{name:/Mixer.*Open details/}).click();await page.locator('#rl-settings [data-key="daily_minutes"]').fill('20');await page.getByLabel('Reason for the change').fill('Initial edit');await page.getByRole('button',{name:'Review setting changes'}).click();await page.locator('#rl-settings [data-key="daily_minutes"]').fill('21');await expect(page.locator('#rl-detail-status')).toContainText('draft changed during review');await expect(page.locator('#rl-setting-review')).toBeHidden();
});

test('uncertain apply keeps exactly the same request identity on explicit check',async({page})=>{
 const {requests}=await setup(page,{ambiguous:true});await page.getByRole('button',{name:/Mixer.*Open details/}).click();await page.locator('#rl-settings [data-key="daily_minutes"]').fill('22');await page.getByLabel('Reason for the change').fill('Retain identity');await page.getByRole('button',{name:'Review setting changes'}).click();await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.getByRole('button',{name:'Check same request'})).toBeVisible();await page.getByRole('button',{name:'Check same request'}).click();await expect(page.locator('#rl-detail-status')).toContainText('Readback unavailable');const applies=requests.filter(r=>r.path.endsWith('/apply'));expect(applies).toHaveLength(2);expect(applies[0].body).toEqual(applies[1].body);
});
test('refresh retains the original settings revision for an unsaved draft',async({page})=>{
 const {data,requests}=await setup(page);await page.getByRole('button',{name:/Mixer.*Open details/}).click();await page.locator('#rl-settings [data-key="daily_minutes"]').fill('22');await page.getByLabel('Reason for the change').fill('Retain draft version');data.devices.find(d=>d.id==='mixer').settings.revision='concurrent-settings-v2';await page.getByRole('button',{name:'Refresh current state'}).click();await expect(page.locator('#rl-facts')).toContainText('concurrent-settings-v2');await page.getByRole('button',{name:'Review setting changes'}).click();await expect(page.locator('#rl-setting-review')).toBeVisible();expect(requests.find(r=>r.path.endsWith('/preview')).body.expected_revision).toBe('settings-v1');
});

test('definite expired preview rejection permits a fresh review without trapping the owner',async({page})=>{
 await setup(page,{rejectApply:'The preview expired. Review again.'});await page.getByRole('button',{name:/Mixer.*Open details/}).click();await page.locator('#rl-settings [data-key="daily_minutes"]').fill('22');await page.getByLabel('Reason for the change').fill('Adjusted requirement');await page.getByRole('button',{name:'Review setting changes'}).click();await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.locator('#rl-detail-status')).toContainText('preview expired');await expect(page.getByRole('button',{name:'Check same request'})).toHaveCount(0);await page.getByRole('button',{name:'Review setting changes'}).click();await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.locator('#rl-detail-status')).toContainText('Saved');
});

test('mobile plan controls remain reachable and keyboard focus stays below navigation',async({page})=>{
 await page.setViewportSize({width:390,height:844});await setup(page);await page.getByRole('button',{name:/Mixer.*Open details/}).click();await page.locator('#rl-settings [data-key="daily_minutes"]').focus();const bounds=await page.locator('#rl-settings [data-key="daily_minutes"]').boundingBox();const nav=await page.locator('.farm-nav').boundingBox();expect(bounds.y).toBeGreaterThanOrEqual(nav.y+nav.height);await page.getByRole('button',{name:'Close details'}).click();await page.getByLabel('Camp A priority').selectOption('high');await page.getByLabel('Camp A reason').fill('Earlier available window');await page.getByRole('button',{name:'Skip Camp A today'}).click();await expect(page.getByRole('button',{name:'Include Camp A today'})).toBeVisible();await noOverflow(page);await page.getByRole('tab',{name:'Day plan & camps'}).focus();await page.keyboard.press('ArrowRight');await expect(page.getByRole('tab',{name:'Run & change history'})).toBeFocused();await expect(page.locator('#rl-history')).toBeVisible();
});

test('actual authenticated backend persists a borehole setting and restores the fixture policy',async({page},info)=>{
 test.skip(!process.env.ROOTLINE_UI_SERVER_COMMAND,'Requires the isolated disposable-database Flask fixture server.');
 await page.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
 await page.goto(base+'/owner/login?next=/irrigation');await page.getByLabel('Owner token').fill('synthetic-admin-only-'+'a'.repeat(40));await page.getByRole('button',{name:'Unlock'}).click();await expect(page.locator('#rl-input-state')).not.toContainText('Reading');
 const read=async()=>page.evaluate(async()=>{const response=await fetch('/api/telemetry/rootline/owner-controls?panel=devices');return {status:response.status,body:await response.json()};});
 const original=await read();expect(original.status).toBe(200);const device=original.body.devices.find(d=>d.id==='borehole');const field=device.settings.fields.find(f=>f.key==='solar_proxy_w');expect(field.editable).toBe(true);expect(field.value).toBe(1500);
 const change=async(value,reason)=>{
  await page.getByRole('button',{name:/Borehole.*Open details/}).click();await page.locator('#rl-settings [data-key="solar_proxy_w"]').fill(String(value));await page.getByLabel('Reason for the change').fill(reason);await page.getByRole('button',{name:'Review setting changes'}).click();await expect(page.locator('#rl-setting-review')).toBeVisible();await expect(page.locator('#rl-setting-review')).not.toContainText('[object Object]');await expect(page.locator('#rl-setting-review')).toContainText(String(value));await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.locator('#rl-detail-status')).toContainText('Saved · revision');
 };
 await change(1800,'Synthetic browser qualification: change AC sunshine threshold');
 await page.reload();await expect(page.locator('#rl-input-state')).not.toContainText('Reading');const updated=await read();expect(updated.body.devices.find(d=>d.id==='borehole').settings.fields.find(f=>f.key==='solar_proxy_w').value).toBe(1800);
 await page.getByRole('button',{name:/Borehole.*Open details/}).click();await expect(page.locator('#rl-settings [data-key="solar_proxy_w"]')).toHaveValue('1800');await page.getByRole('button',{name:'View history',exact:true}).click();await expect(page.locator('#rl-history-rows')).toContainText('Synthetic browser qualification');await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:info.outputPath('actual-backend-setting-readback.png'),fullPage:true});
 await change(1500,'Synthetic browser qualification: restore original AC sunshine threshold');const restored=await read();expect(restored.body.devices.find(d=>d.id==='borehole').settings.fields.find(f=>f.key==='solar_proxy_w').value).toBe(1500);
 await info.attach('actual-canonical-readback',{body:JSON.stringify({classification:'real_authenticated_routes_and_disposable_PostgreSQL_no_provider_or_hardware_effects',before:original,updated,restored}),contentType:'application/json'});
});


test('actual day plan persists priority and duration and manual request replay stays queued',async({page},info)=>{
 test.skip(process.env.ROOTLINE_OWNER_BROWSER_SEED!=='1','Requires canonical isolated daily-programme seed.');
 await page.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
 await page.goto(base+'/owner/login?next=/irrigation');await page.getByLabel('Owner token').fill('synthetic-admin-only-'+'a'.repeat(40));await page.getByRole('button',{name:'Unlock'}).click();await expect(page.locator('#rl-plan-rows tr')).toHaveCount(4);
 const read=async(panel)=>page.evaluate(async panel=>(await fetch('/api/telemetry/rootline/owner-controls?panel='+panel)).json(),panel);
 const original=await read('plan');const originalB=(await read('devices')).devices.find(d=>d.id==='camp_b');
 await page.getByLabel('Camp B priority').selectOption('high');await page.getByLabel('Camp B duration in minutes').fill('20');await page.getByLabel('Camp B reason').fill('Synthetic earlier available window');await page.getByRole('button',{name:'Skip Camp E today'}).click();await page.getByRole('button',{name:'Review day plan'}).click();await expect(page.locator('#rl-plan-review')).not.toContainText('[object Object]');await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.locator('#rl-plan-status')).toContainText('Saved');
 await page.reload();await expect(page.locator('#rl-plan-rows tr')).toHaveCount(4);const changed=await read('plan');expect(changed.plan.revision).not.toBe(original.plan.revision);expect(changed.plan.rows[0].device_id).toBe('camp_b');expect(changed.plan.rows[0].duration_minutes).toBe(20);expect(changed.plan.rows.find(r=>r.device_id==='camp_e').skip).toBe(true);
 await page.getByRole('button',{name:/Camp B.*Open details/}).click();await page.getByRole('button',{name:'Request one run'}).click();await page.locator('#rl-manual-reason').fill('Synthetic queue-only qualification');await page.getByRole('button',{name:'Review request'}).click();
 const applyRequest=page.waitForRequest(r=>r.url().endsWith('/owner-controls/apply'));await page.getByRole('button',{name:'Confirm request'}).click();const queuedBody=(await applyRequest).postDataJSON();await expect(page.locator('#rl-detail-status')).toContainText('Request queued');
 const replay=await page.evaluate(async body=>{const data=await(await fetch('/api/telemetry/rootline/owner-controls?panel=devices')).json();return(await fetch('/api/telemetry/rootline/owner-controls/apply',{method:'POST',headers:{'Content-Type':'application/json','X-ROOTLINE-CSRF':data.csrf_token},body:JSON.stringify(body)})).json();},queuedBody);expect(replay.status).toBe('queued');expect(replay.readback_bound).toBe(true);
 await page.evaluate(()=>window.scrollTo({top:0,behavior:'instant'}));await page.screenshot({path:info.outputPath('actual-plan-and-queued-request.png'),fullPage:true});
 // Canonical API cleanup supersedes the unconsumed synthetic request and restores the plan.
 const cleanup=await page.evaluate(async({original,originalB})=>{
  const get=async panel=>(await fetch('/api/telemetry/rootline/owner-controls?panel='+panel)).json();
  const save=async(body)=>{const auth=await get('devices');const post=async(path,payload)=>(await fetch('/api/telemetry/rootline/owner-controls/'+path,{method:'POST',headers:{'Content-Type':'application/json','X-ROOTLINE-CSRF':auth.csrf_token},body:JSON.stringify(payload)})).json();const p=await post('preview',{...body,reason:'Synthetic browser qualification restore',idempotency_key:crypto.randomUUID()});if(!p.success)return p;return post('apply',{preview_id:p.preview.id,preview_digest:p.preview.digest,idempotency_key:crypto.randomUUID()});};
  const current=await get('devices');const setting=await save({kind:'settings',device_id:'camp_b',expected_revision:current.devices.find(d=>d.id==='camp_b').settings.revision,changes:{mode:originalB.settings.mode,scope:originalB.settings.scope,fields:Object.fromEntries(originalB.settings.fields.filter(f=>f.editable).map(f=>[f.key,f.value]))}});
  const plan=await get('plan');const restored=await save({kind:'plan',expected_revision:plan.plan.revision,changes:{rows:original.plan.rows.map(({id,order,duration_minutes,priority,reason,skip})=>({id,order,duration_minutes,priority,reason,skip}))}});return {setting,restored};
 },{original,originalB});expect(cleanup.setting.readback_bound).toBe(true);expect(cleanup.restored.readback_bound).toBe(true);
 await info.attach('actual-plan-and-request-readback',{body:JSON.stringify({classification:'real_canonical_local_database_no_scheduler_or_provider',original,changed,replay,cleanup}),contentType:'application/json'});
});


test('mode-only camp change omits unavailable optional duration',async({page})=>{
 const {requests}=await setup(page,{data:data=>{const f=data.devices[0].settings.fields[0];f.value=null;f.required=false;f.reason='Current plan unavailable. Leave blank to retain existing policy.';}});
 await page.getByRole('button',{name:/Camp A.*Open details/}).click();await expect(page.locator('#rl-settings [data-key="duration_minutes"]')).toHaveValue('');await page.locator('#rl-mode').selectOption('paused');await page.getByLabel('Reason for the change').fill('Pause until next plan');await page.getByRole('button',{name:'Review setting changes'}).click();await expect(page.locator('#rl-setting-review')).toBeVisible();expect(requests.find(r=>r.path.endsWith('/preview')).body.changes.fields).toEqual({});await page.getByRole('button',{name:'Save reviewed changes'}).click();await expect(page.locator('#rl-detail-status')).toContainText('Saved');
});


test('injector duration and all four camp selections save through the application and survive reload',async({page})=>{
 const {requests}=await setup(page);
 await page.getByRole('button',{name:/Injection.*Open details/}).click();
 await page.locator('#rl-settings [data-key="pulse_minutes"]').fill('10');
 await page.locator('#rl-settings [data-key="pulses_per_60_minutes"]').fill('2');
 for(const camp of ['a','b','c','e'])await page.locator('#rl-settings [data-key="inject_camp_'+camp+'"]').check();
 await page.getByLabel('Reason for the change').fill('Two ten-minute injections per hour for all four camps');
 await page.getByRole('button',{name:'Review setting changes'}).click();
 await expect(page.locator('#rl-setting-review')).toBeVisible();
 const preview=requests.find(r=>r.path.endsWith('/preview'));
 expect(preview.body.device_id).toBe('injection');
 expect(preview.body.changes.fields).toEqual({pulse_minutes:10,pulses_per_60_minutes:2,inject_camp_a:true,inject_camp_b:true,inject_camp_c:true,inject_camp_e:true});
 await page.getByRole('button',{name:'Save reviewed changes'}).click();
 await expect(page.locator('#rl-detail-status')).toContainText('Saved');
 await page.reload();
 await page.getByRole('button',{name:/Injection.*Open details/}).click();
 await expect(page.locator('#rl-settings [data-key="pulse_minutes"]')).toHaveValue('10');
 for(const camp of ['a','b','c','e'])await expect(page.locator('#rl-settings [data-key="inject_camp_'+camp+'"]')).toBeChecked();
 expect(requests.filter(r=>r.method==='POST')).toHaveLength(2);
});

// Draft insertion for root-owned browser suite after backend freeze. Not executed.
// Uses existing test/expect/base and beforeEach deterministic server clock.
test('actual injector programme saves two ten-minute injections for all registered camps',async({page},info)=>{
 test.skip(!process.env.ROOTLINE_UI_SERVER_COMMAND || process.env.ROOTLINE_OWNER_BROWSER_SEED!=='1','Requires disposable PostgreSQL canonical Flask fixture.');
 await page.route('**/*',route=>new URL(route.request().url()).origin===base?route.continue():route.abort());
 await page.goto(base+'/owner/login?next=/irrigation');
 await page.getByLabel('Owner token').fill('synthetic-admin-only-'+'a'.repeat(40));
 await page.getByRole('button',{name:'Unlock'}).click();
 await expect(page.locator('#rl-input-state')).not.toContainText('Reading');
 const read=async()=>page.evaluate(async()=>{const r=await fetch('/api/telemetry/rootline/owner-controls?panel=devices');if(!r.ok)throw new Error('Canonical devices unavailable');return r.json();});
 const target={pulse_minutes:10,pulses_per_60_minutes:2,inject_camp_a:true,inject_camp_b:true,inject_camp_c:true,inject_camp_e:true};
 const values=d=>Object.fromEntries(d.devices.find(x=>x.id==='injection').settings.fields.filter(f=>Object.hasOwn(target,f.key)).map(f=>[f.key,f.value]));
 let before=await read();let original=values(before);
 expect(Object.keys(original).sort()).toEqual(Object.keys(target).sort());
 for(const f of before.devices.find(x=>x.id==='injection').settings.fields.filter(f=>Object.hasOwn(target,f.key)))expect(f.editable).toBe(true);
 const save=async(fields,reason)=>{
  await page.getByRole('button',{name:/Injection.*Open details/}).click();
  for(const [key,value] of Object.entries(fields)){
   const input=page.locator('#rl-settings [data-key="'+key+'"]');
   if(typeof value==='boolean')await input.setChecked(value);else await input.fill(String(value));
  }
  await page.getByLabel('Reason for the change').fill(reason);
  const previewResponse=page.waitForResponse(r=>r.url().endsWith('/api/telemetry/rootline/owner-controls/preview') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Review setting changes'}).click();
  const preview=await previewResponse;expect(preview.ok()).toBe(true);
  expect(preview.request().headers()['x-rootline-csrf']).toBeTruthy();
  const body=await preview.json();expect(body.success).toBe(true);expect(body.preview.id).toBeTruthy();
  await expect(page.locator('#rl-setting-review')).toBeVisible();
  const applyResponse=page.waitForResponse(r=>r.url().endsWith('/api/telemetry/rootline/owner-controls/apply') && r.request().method()==='POST');
  await page.getByRole('button',{name:'Save reviewed changes'}).click();
  const applied=await applyResponse;expect(applied.ok()).toBe(true);const receipt=await applied.json();
  expect(receipt.success).toBe(true);expect(receipt.readback_bound).toBe(true);
  await expect(page.locator('#rl-detail-status')).toContainText('Saved · revision');return receipt;
 };
 if(Object.entries(target).every(([key,value])=>original[key]===value)){
  await save({pulse_minutes:2,pulses_per_60_minutes:2,inject_camp_a:false,inject_camp_b:true,inject_camp_c:true,inject_camp_e:false},'Synthetic injector acceptance: establish distinct starting fixture');
  before=await read();original=values(before);
 }
 const applied=await save(target,'Synthetic injector acceptance: two ten-minute injections, Camps A B C E');
 await page.reload();await expect(page.locator('#rl-input-state')).not.toContainText('Reading');
 const updated=await read();expect(values(updated)).toEqual(target);
 expect(updated.devices.find(x=>x.id==='injection').settings.revision).not.toBe(before.devices.find(x=>x.id==='injection').settings.revision);
 await page.getByRole('button',{name:/Injection.*Open details/}).click();
 for(const [key,value] of Object.entries(target)){
  const input=page.locator('#rl-settings [data-key="'+key+'"]');
  if(typeof value==='boolean')await expect(input).toBeChecked();else await expect(input).toHaveValue(String(value));
 }
 await page.getByRole('button',{name:'View history',exact:true}).click();
 await expect(page.locator('#rl-history-rows')).toContainText('Synthetic injector acceptance');
 await page.screenshot({path:info.outputPath('actual-injector-programme-readback.png'),fullPage:true});
 await save(original,'Synthetic injector acceptance: restore original fixture policy');
 const restored=await read();expect(values(restored)).toEqual(original);
 await info.attach('actual-injector-canonical-readback',{body:JSON.stringify({classification:'actual authenticated Flask and disposable PostgreSQL; no scheduler/provider/device calls',before,applied,updated,restored}),contentType:'application/json'});
});
