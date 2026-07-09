const assert = require("assert");
const fs = require("fs");
const path = require("path");
const { chromium } = require("@playwright/test");

const BASE_URL = process.env.FAMILY_TREE_BROWSER_BASE_URL || "http://127.0.0.1:5000";
const OUT_DIR = path.join(process.cwd(), ".charlie_runner", "family-tree-browser-evidence");

const successPayload = {
  success: true,
  tree: {
    pig_id: "SOW-1",
    litter_id: "LIT-1",
    sibling_count: 1,
    current_pig: {
      pig_id: "SOW-1",
      tag_number: "10",
      sex: "Female",
      calculated_stage: "Sow",
      current_weight_kg: 185,
      status: "Active",
      on_farm: "Yes",
    },
    mother: null,
    father: null,
    siblings: [{
      pig_id: "PIG-2",
      tag_number: "102",
      sex: "Female",
      calculated_stage: "Grower",
      current_weight_kg: 60,
      status: "Active",
      on_farm: "Yes",
      age_days: 120,
      current_pen_id: "PEN-1",
    }],
    breeding_context: {
      is_breeding_animal: true,
      animal_type: "sow",
      animal: {
        pig_id: "SOW-1",
        tag_number: "10",
        mating_count: 2,
        open_count: 1,
        litter_count: 1,
        farrowed_count: 1,
        born_alive_total: 8,
        weaned_total: 6,
        average_born_alive: 8,
        average_weaned: 6,
        survival_pct: 75,
      },
      data_quality: {
        flag_count: 1,
        flags: ["Review litter counts"],
      },
      matings: [{
        mating_id: "MAT-1",
        mating_date: "2026-01-01",
        sow_pig_id: "SOW-1",
        sow_tag_number: "10",
        boar_pig_id: "BOAR-1",
        boar_tag_number: "3",
        mating_status: "Farrowed",
        linked_litter_id: "LIT-1",
        quality_flags: [],
      }],
      litters: [{
        litter_id: "LIT-1",
        farrowing_date: "2026-04-24",
        sow_pig_id: "SOW-1",
        sow_tag_number: "10",
        boar_pig_id: "BOAR-1",
        boar_tag_number: "3",
        born_alive: 8,
        weaned_count: 6,
        survival_pct: 75,
        quality_flags: ["Review litter counts"],
      }],
    },
  },
};

async function assertNoHorizontalOverflow(page) {
  const overflow = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  assert(
    overflow.scrollWidth <= overflow.clientWidth + 1,
    `horizontal overflow: scrollWidth=${overflow.scrollWidth} clientWidth=${overflow.clientWidth}`,
  );
}

async function runState(browser, name, viewport, payload, status = 200) {
  const context = await browser.newContext({ viewport });
  const page = await context.newPage();
  const apiPaths = [];

  await page.route("**/api/pig-weights/pig/**/family-tree", async (route) => {
    apiPaths.push(new URL(route.request().url()).pathname);
    await route.fulfill({
      status,
      contentType: "application/json",
      body: JSON.stringify(payload),
    });
  });

  await page.goto(`${BASE_URL}/pig/SOW-1/family-tree`, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle");

  assert.strictEqual(apiPaths[0], "/api/pig-weights/pig/SOW-1/family-tree");

  const decisionPanel = page.locator("#family_tree_breeding_panel");
  const relationshipTitle = page.locator("#family_tree_relationship_title");
  const relationshipSection = page.locator("#family_tree_relationship_section");
  const siblingHeader = page.locator("#family_tree_siblings_header");
  const siblingCount = page.locator("#family_tree_sibling_count");

  if (status === 200) {
    await assert.strictEqual(await decisionPanel.isVisible(), true, `${name}: decision panel should be visible`);
    await assert.strictEqual(await relationshipTitle.isVisible(), true, `${name}: relationship title should be visible`);
    await assert.strictEqual(await relationshipSection.isVisible(), true, `${name}: relationship tree should be visible`);
    await assert.match(await page.locator("#family_tree_title").innerText(), /Family Tree - 10/);
    await assert.match(await siblingCount.innerText(), /1 sibling\(s\) found in litter LIT-1/);
    const parsedTrailingSlashPigId = await page.evaluate(() => {
      window.history.pushState({}, "", "/pig/SOW-1/family-tree/");
      return window.getPigIdFromFamilyTreeUrl();
    });
    assert.strictEqual(parsedTrailingSlashPigId, "SOW-1", `${name}: trailing slash should still resolve the pig ID`);
  } else {
    await assert.strictEqual(await page.locator("#family_tree_message").isVisible(), true, `${name}: error should be visible`);
    await assert.strictEqual(await decisionPanel.isVisible(), false, `${name}: decision panel should be hidden`);
    await assert.strictEqual(await relationshipTitle.isVisible(), false, `${name}: relationship title should be hidden`);
    await assert.strictEqual(await relationshipSection.isVisible(), false, `${name}: relationship tree should be hidden`);
    await assert.strictEqual(await siblingHeader.isVisible(), false, `${name}: sibling header should be hidden`);
    await assert.strictEqual(await siblingCount.innerText(), "", `${name}: sibling loading text should be cleared`);
  }

  await assertNoHorizontalOverflow(page);
  await page.screenshot({ path: path.join(OUT_DIR, `${name}.png`), fullPage: true });
  await context.close();
}

(async () => {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const browser = await chromium.launch();
  try {
    await runState(browser, "desktop-normal", { width: 1366, height: 900 }, successPayload);
    await runState(browser, "mobile-normal", { width: 390, height: 844 }, successPayload);
    await runState(browser, "desktop-api-error", { width: 1366, height: 900 }, {
      success: false,
      error: "Family tree API unavailable",
    }, 500);
  } finally {
    await browser.close();
  }
  console.log("Family tree browser checks passed: desktop-normal, mobile-normal, desktop-api-error");
})();
