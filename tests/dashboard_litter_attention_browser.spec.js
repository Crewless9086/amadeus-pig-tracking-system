const { test, expect } = require("@playwright/test");
const fs = require("fs");

const source = fs.readFileSync("static/js/dashboard.js", "utf8");
const helper = source.match(/function litterAttentionIdentity\(item\) \{[\s\S]*?\n\}/);

test.beforeEach(async ({ page }) => {
  expect(helper).not.toBeNull();
  await page.setContent('<h1 id="headline"></h1><p id="context"></p>');
  await page.addScriptTag({content: helper[0]});
});

test("Molly is primary and the litter identifier is secondary", async ({ page }) => {
  await page.evaluate(() => {
    const identity = litterAttentionIdentity({sow_name: "Molly", litter_id: "LIT-2026-5C36"});
    document.querySelector("#headline").textContent = identity.headline;
    document.querySelector("#context").textContent = identity.context;
  });
  await expect(page.locator("#headline")).toHaveText("Molly");
  await expect(page.locator("#context")).toHaveText("· LIT-2026-5C36");
});

test("unknown sow identity safely falls back to the litter identifier", async ({ page }) => {
  const identity = await page.evaluate(() => litterAttentionIdentity({
    sow_name: "", sow_tag_number: "", litter_id: "LIT-2026-5C36",
  }));
  expect(identity).toEqual({headline: "LIT-2026-5C36", context: ""});
});
