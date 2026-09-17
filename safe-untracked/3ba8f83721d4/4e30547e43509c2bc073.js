const { chromium } = require("playwright");
const fs = require("fs");
const assert = require("assert");
const base = "https://amadeus-pig-tracking-system.onrender.com";
const env = Object.fromEntries(fs.readFileSync("C:/Users/charl/OneDrive/1. Amadeus/AGENTS/amadeus-pig-tracking-system/.env","utf8").split(/\r?\n/).filter(x=>x.includes("=")).map(x=>{const i=x.indexOf("=");return [x.slice(0,i),x.slice(i+1).replace(/^"|"$/g,"")]}));
(async()=>{
 const browser=await chromium.launch({headless:true});
 for(const viewport of [{name:"desktop",width:1440,height:1100},{name:"mobile",width:390,height:844}]){
  const page=await browser.newPage({viewport});
  const writes=[]; page.on("request",r=>{if(!["GET","HEAD","OPTIONS"].includes(r.method())) writes.push(`${r.method()} ${new URL(r.url()).pathname}`)});
  await page.goto(`${base}/owner/login?next=/matings`);
  await page.locator("#owner_token").fill(env.OWNER_READ_TOKEN||env.OWNER_ADMIN_TOKEN);
  await Promise.all([page.waitForURL("**/matings"),page.getByRole("button",{name:"Unlock"}).click()]);
  await page.waitForLoadState("networkidle");
  assert.equal(await page.locator("h1").textContent(),"Parings");
  assert.equal(await page.locator(".mating-toggle-button").count(),0);
  const cards=page.locator(".mating-card"); if(await cards.count()){await cards.first().click();assert.equal(await cards.first().getAttribute("aria-expanded"),"true")}
  const tiles=page.locator("[data-mating-section]"); if(await tiles.count()) await tiles.first().click();
  const removal=page.locator("[data-open-removal]"); if(await removal.count()){await removal.first().click();assert.equal(await removal.first().getAttribute("aria-expanded"),"true")}
  const overflow=await page.evaluate(()=>({root:[document.documentElement.clientWidth,document.documentElement.scrollWidth],items:[...document.querySelectorAll("*")].filter(e=>e.getBoundingClientRect().right>document.documentElement.clientWidth+1).slice(0,10).map(e=>[e.tagName,e.className,e.getBoundingClientRect().right,e.textContent.trim().slice(0,50)])}));
  if(overflow.root[1]>overflow.root[0]) console.log("overflow",viewport.name,overflow);
  await page.screenshot({path:`C:/tmp/uiq-20260813-01-matings/production-${viewport.name}.png`,fullPage:true});
  assert.deepEqual(writes,["POST /owner/login"]);
  await page.close();
 }
 const state=await browser.newPage();
 await state.goto(`${base}/owner/login?next=/matings`); await state.locator("#owner_token").fill(env.OWNER_READ_TOKEN||env.OWNER_ADMIN_TOKEN);
 await Promise.all([state.waitForURL("**/matings"),state.getByRole("button",{name:"Unlock"}).click()]);
 await state.route("**/api/pig-weights/breeding-attention/exposures",r=>r.fulfill({json:{success:true,records:[]}}));
 await state.reload(); assert.equal(await state.locator("#active_exposure_workspace:not(.hidden)").count(),0);
 await state.unroute("**/api/pig-weights/breeding-attention/exposures");
 await state.route("**/api/pig-weights/breeding-attention/exposures",r=>r.fulfill({status:503,json:{success:false}}));
 await state.reload(); assert.match(await state.locator("#exposure_removal_board").textContent(),/Exposure evidence unavailable/);
 await browser.close(); console.log("uiq_production_verify: PASS");
})().catch(e=>{console.error(e);process.exit(1)});
