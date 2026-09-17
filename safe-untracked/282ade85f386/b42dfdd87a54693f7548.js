const { chromium } = require("C:/Users/charl/OneDrive/1. Amadeus/AGENTS/amadeus-pig-tracking-system/node_modules/playwright");
const fs = require("fs");
const path = require("path");
const assert = require("assert");

const base = process.env.PWR_BASE_URL || "http://127.0.0.1:5095";
const output = path.resolve(process.env.PWR_OUTPUT || "output/ui/paring-werpselrekord-followup");
fs.mkdirSync(output, {recursive:true});
const env = Object.fromEntries(fs.readFileSync("C:/Users/charl/OneDrive/1. Amadeus/AGENTS/amadeus-pig-tracking-system/.env", "utf8").split(/\r?\n/).filter(line => line.trim() && !line.trim().startsWith("#") && line.includes("=")).map(line => { const split=line.indexOf("="); return [line.slice(0,split).trim(),line.slice(split+1).trim().replace(/^[\"']|[\"']$/g,"")]; }));
const clean = value => String(value ?? "").trim();

async function authenticatedContext(browser, viewport) {
  const context = await browser.newContext({viewport});
  const page = await context.newPage();
  await page.goto(`${base}/owner/login?next=/paring-werpselrekord`, {waitUntil:"domcontentloaded"});
  await page.locator("#owner_token").fill(env.OWNER_ADMIN_TOKEN);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(`${base}/paring-werpselrekord`);
  await page.close();
  return context;
}

async function capture(page, url, name, expectedMatingId="") {
  await page.goto(url, {waitUntil:"networkidle"});
  if (expectedMatingId) await page.waitForFunction(id => document.querySelector("#pwr_mating_id").value === id, expectedMatingId);
  await page.screenshot({path:path.join(output, `${name}-desktop.png`), fullPage:true});
  await page.emulateMedia({media:"print"});
  const pdf = await page.pdf({path:path.join(output, `${name}-a4.pdf`), format:"A4", printBackground:true, preferCSSPageSize:true});
  assert.equal((pdf.toString("latin1").match(/\/Type\s*\/Page\b/g) || []).length, 1, `${name} must be one A4 page`);
  await page.emulateMedia({media:"screen"});
}

(async () => {
  const browser = await chromium.launch({headless:true});
  const desktop = await authenticatedContext(browser, {width:1440,height:1000});
  const requests = [];
  desktop.on("request", request => requests.push({method:request.method(),url:request.url()}));
  const apiPage = await desktop.newPage();
  await apiPage.goto(`${base}/paring-werpselrekord`, {waitUntil:"domcontentloaded"});
  const matings = await apiPage.evaluate(async () => (await fetch("/api/pig-weights/matings")).json());
  assert.equal(matings.success, true);
  const olive = matings.records.find(row => clean(row.sow_name).toLowerCase() === "olive" && !clean(row.linked_litter_id));
  const linked = matings.records.find(row => clean(row.mating_id) && clean(row.linked_litter_id));
  assert(olive, "Genuine mating-only Olive record not found");
  assert(linked, "Genuine linked mating/litter record not found");
  const litter = await apiPage.evaluate(async id => (await fetch(`/api/pig-weights/litter/${encodeURIComponent(id)}`)).json(), linked.linked_litter_id);
  assert.equal(litter.success, true);
  await apiPage.close();

  const blank = await desktop.newPage();
  const blankApi = [];
  blank.on("request", request => { if (request.url().includes("/api/pig-weights/")) blankApi.push(request.url()); });
  await capture(blank, `${base}/paring-werpselrekord`, "blank");
  assert.equal(blankApi.length, 0);
  assert.equal(await blank.locator("#pwr_piglet_rows tr").count(), 16);
  assert.equal(await blank.locator("#pwr_notes_rows tr").count(), 5);
  assert(await blank.locator("main input").evaluateAll(inputs => inputs.every(input => input.value === "")));
  assert.deepEqual(await blank.locator(".pwr-wean th").allTextContents(), ["Nr.","Tag","Kommentaar","Geslag","Gewig kg"]);
  await blank.locator("#pwr_sow").fill("Handinvul toets");
  assert.equal(await blank.locator("#pwr_sow").inputValue(), "Handinvul toets");
  await blank.locator("#pwr_sow").fill("");

  const olivePage = await desktop.newPage();
  await capture(olivePage, `${base}/paring-werpselrekord?mating_id=${encodeURIComponent(olive.mating_id)}&return_to=${encodeURIComponent("/matings")}`, "olive-mating-only", clean(olive.mating_id));
  assert.equal(await olivePage.locator("#pwr_header_sow").inputValue(), clean(olive.sow_name));
  assert.equal(await olivePage.locator("#pwr_header_boar").inputValue(), clean(olive.boar_name));
  assert.equal(await olivePage.locator("#pwr_farrowing_pen").inputValue(), "");
  assert.equal(await olivePage.locator("#pwr_back_label").innerText(), "Terug na Parings");
  assert.equal(await olivePage.locator("#pwr_back_link").getAttribute("href"), "/matings");
  const returnPage = await desktop.newPage();
  await returnPage.goto(`${base}/paring-werpselrekord?mating_id=${encodeURIComponent(olive.mating_id)}&return_to=${encodeURIComponent("/matings")}`, {waitUntil:"networkidle"});
  await returnPage.locator("#pwr_back_link").click();
  await returnPage.waitForURL(`${base}/matings`);
  await returnPage.close();

  const linkedPage = await desktop.newPage();
  await capture(linkedPage, `${base}/paring-werpselrekord?litter_id=${encodeURIComponent(linked.linked_litter_id)}`, "linked-record", clean(linked.mating_id));
  const expectedPen = clean(litter.litter.farrowing_pen_name || litter.litter.farrowing_pen_id || litter.litter.litter_pen_name || litter.litter.litter_pen_id);
  assert.equal(await linkedPage.locator("#pwr_farrowing_pen").inputValue(), expectedPen);
  assert.equal(await linkedPage.locator("#pwr_header_sow").inputValue(), clean(linked.sow_name));
  assert.equal(await linkedPage.locator("#pwr_header_boar").inputValue(), clean(linked.boar_name));

  const mobile = await authenticatedContext(browser, {width:390,height:844});
  const mobileRequests = [];
  mobile.on("request", request => mobileRequests.push({method:request.method(),url:request.url()}));
  for (const [name,url,id] of [["blank",`${base}/paring-werpselrekord`,""],["olive-mating-only",`${base}/paring-werpselrekord?mating_id=${encodeURIComponent(olive.mating_id)}&return_to=${encodeURIComponent("/matings")}`,clean(olive.mating_id)],["linked-record",`${base}/paring-werpselrekord?litter_id=${encodeURIComponent(linked.linked_litter_id)}`,clean(linked.mating_id)]]) {
    const page = await mobile.newPage(); await page.goto(url,{waitUntil:"networkidle"});
    if (id) await page.waitForFunction(value => document.querySelector("#pwr_mating_id").value === value, id);
    const widths = await page.evaluate(() => ({scroll:document.documentElement.scrollWidth,client:document.documentElement.clientWidth}));
    assert(widths.scroll <= widths.client); await page.screenshot({path:path.join(output,`${name}-mobile.png`),fullPage:true}); await page.close();
  }
  const secondMatings = await linkedPage.evaluate(async () => (await fetch("/api/pig-weights/matings")).json());
  assert.deepEqual(secondMatings.records, matings.records);
  assert(requests.every(request => request.method === "GET"));
  assert(mobileRequests.every(request => request.method === "GET"));
  const evidence = {base,olive_mating_id:olive.mating_id,olive_sow:olive.sow_name,olive_boar:olive.boar_name,olive_linked_litter:olive.linked_litter_id || "",olive_farrowing_pen:"",olive_current_pen:olive.sow_current_pen_name || olive.sow_current_pen_id || "",linked_mating_id:linked.mating_id,linked_litter_id:linked.linked_litter_id,linked_sow:linked.sow_name,linked_boar:linked.boar_name,linked_attributable_pen:expectedPen || "Unknown",blank_prefill_calls:0,blank_editable:true,matings_return_navigation:true,piglet_rows:16,notes_rows:5,a4_pages_each:1,canonical_payload_repeat_equal:true,non_get_requests:0};
  fs.writeFileSync(path.join(output,"canonical-sample-evidence.json"), JSON.stringify(evidence,null,2));
  await mobile.close(); await desktop.close(); await browser.close();
  console.log(JSON.stringify(evidence,null,2));
})().catch(error => { console.error(error.stack || error); process.exit(1); });
