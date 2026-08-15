const { chromium } = require("C:/Users/charl/OneDrive/1. Amadeus/AGENTS/amadeus-pig-tracking-system/node_modules/playwright");
const fs = require("fs");
const assert = require("assert");

const root = process.cwd();
const template = fs.readFileSync(`${root}/templates/paring-werpselrekord.html`, "utf8").replace(/\{\{ url_for\('static', filename='([^']+)'\) \}\}/g, "/static/$1");
const script = fs.readFileSync(`${root}/static/js/paringWerpselrekord.js`, "utf8");
const css = ["paringWerpselrekord.css", "paringWerpselrekordFollowup.css"].map(name => fs.readFileSync(`${root}/static/css/${name}`, "utf8")).join("\n");
const html = template.replace(/<link[^>]+>/g, "").replace("</head>", `<style>${css}</style></head>`).replace(/<script[^>]+><\/script>/, `<script>${script}</script>`);
const olive = {mating_id:"MAT-OLIVE",sow_name:"Olive",boar_name:"Tyson",mating_pen_name:"Paringskamp 1",sow_current_pen_name:"Kraam Saal 04",mating_date:"2026-08-12"};
const linkedMating = {mating_id:"MAT-LINKED",linked_litter_id:"LIT-LINKED",sow_name:"Maya",boar_name:"Bola",mating_pen_name:"Paringskamp 2",sow_current_pen_name:"Kraam Saal 01"};
const linkedLitter = {litter_id:"LIT-LINKED",mating_id:"MAT-LINKED",farrowing_date:"2026-07-30",farrowing_pen_name:"Jonghok 2",weaned_count:7,weaned_male_count:4,weaned_female_count:3};

(async () => {
  const browser = await chromium.launch({headless:true});
  const context = await browser.newContext({viewport:{width:1440,height:1000}});
  const calls = [];
  await context.route("**/*", route => {
    const url = new URL(route.request().url()); calls.push({path:url.pathname,method:route.request().method()});
    if (url.pathname === "/api/pig-weights/matings") return route.fulfill({contentType:"application/json",body:JSON.stringify({success:true,records:[olive,linkedMating]})});
    if (url.pathname === "/api/pig-weights/litter/LIT-LINKED") return route.fulfill({contentType:"application/json",body:JSON.stringify({success:true,litter:linkedLitter})});
    return route.fulfill({contentType:"text/html",body:html});
  });

  const blank = await context.newPage();
  await blank.goto("http://pwr.test/paring-werpselrekord");
  assert.equal(calls.filter(call => call.path.startsWith("/api/")).length, 0);
  assert.equal(await blank.locator("#pwr_piglet_rows tr").count(), 16);
  assert.equal(await blank.locator("#pwr_notes_rows tr").count(), 5);
  assert(await blank.locator("main input").evaluateAll(inputs => inputs.every(input => input.value === "")));
  assert.deepEqual(await blank.locator(".pwr-wean th").allTextContents(), ["Nr.","Tag","Kommentaar","Geslag","Gewig kg"]);

  const olivePage = await context.newPage();
  await olivePage.goto("http://pwr.test/paring-werpselrekord?mating_id=MAT-OLIVE&return_to=%2Fmatings");
  await olivePage.waitForFunction(() => document.querySelector("#pwr_sow").value === "Olive");
  assert.equal(await olivePage.locator("#pwr_header_sow").inputValue(), "Olive");
  assert.equal(await olivePage.locator("#pwr_header_boar").inputValue(), "Tyson");
  assert.equal(await olivePage.locator("#pwr_mating_pen").inputValue(), "Paringskamp 1");
  assert.equal(await olivePage.locator("#pwr_farrowing_pen").inputValue(), "");
  assert.equal(await olivePage.locator("#pwr_current_pen").count(), 0);
  assert.equal(await olivePage.getByText("Huidige hok", {exact:false}).count(), 0);
  assert.equal(await olivePage.locator("#pwr_back_link").getAttribute("href"), "/matings");
  assert.equal(await olivePage.locator("#pwr_back_label").innerText(), "Terug na Parings");

  const linked = await context.newPage();
  await linked.goto("http://pwr.test/paring-werpselrekord?litter_id=LIT-LINKED");
  await linked.waitForFunction(() => document.querySelector("#pwr_litter_id").value === "LIT-LINKED");
  assert.equal(await linked.locator("#pwr_farrowing_pen").inputValue(), "Jonghok 2");
  assert.equal(await linked.locator("#pwr_mating_pen").inputValue(), "Paringskamp 2");
  assert.equal(await linked.locator("#pwr_weaned_male_total").inputValue(), "4");
  assert.equal(await linked.locator("#pwr_weaned_female_total").inputValue(), "3");
  assert(calls.every(call => call.method === "GET"));

  await blank.emulateMedia({media:"print"});
  const pdf = await blank.pdf({format:"A4",printBackground:true,preferCSSPageSize:true});
  assert.equal((pdf.toString("latin1").match(/\/Type\s*\/Page\b/g) || []).length, 1);
  await browser.close();
  console.log("paring werpsel follow-up browser: PASS");
})().catch(error => { console.error(error); process.exit(1); });
