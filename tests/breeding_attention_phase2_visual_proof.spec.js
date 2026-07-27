const { test, expect } = require("@playwright/test");
const fs = require("fs");

const animals = Array.from({ length: 18 }, (_, index) => ({
  pig_id: `PROTECTED-SOW-${index + 1}`,
  tag_number: `${index + 21}`,
  animal_href: "#",
  current_state: index < 6 ? "Needs Data" : (index < 9 ? "Post-litter recovery" : "Pregnancy evidence"),
  filter_state: index < 6 ? "Needs Data" : (index < 9 ? "Post-litter recovery" : "Pregnancy evidence"),
  evidence_dates: { latest_mating: "2026-07-10", latest_litter: "Unknown" },
  freshness: "Fresh",
  confidence: "Limited",
  missing_facts: ["body condition", "current heat observation", "availability"],
  conflicting_facts: [],
  recommended_human_action: "owner decision required",
}));

async function mount(page) {
  await page.route("**/api/pig-weights/breeding-attention", route => route.fulfill({
    json: {
      success: true, source_status: "Available", observation_timestamp: "2026-07-27",
      animals, filters: ["Needs Data", "Post-litter recovery", "Pregnancy evidence"],
      counts: {"Needs Data": 6, "Post-litter recovery": 3, "Pregnancy evidence": 9},
    },
  }));
  await page.route(/\/observations$/, route => route.fulfill({
    json: {success: true, history: []},
  }));
  await page.route("**/observations/preview", route => route.fulfill({
    json: {
      success: true,
      owner_interpretation: "Not recorded by this operation.",
      system_recommendation: {
        effect: ["Body-condition evidence becomes current."],
        advisory_change: {
          before: {state: "Needs Data", recommended_human_action: "owner decision required"},
          after_if_recorded: {state: "Needs Data", recommended_human_action: "owner decision required"},
        },
      },
    },
  }));
  let html = fs.readFileSync("templates/breeding-attention.html", "utf8")
    .replace(/{{[^}]+}}/g, "#")
    .replace(/<script[^>]+breedingAttention\.js[^>]*><\/script>/, "");
  html = html.replace("<head>", '<head><base href="http://localhost/">');
  await page.setContent(html);
  await page.evaluate(() => {
    if (!crypto.randomUUID) crypto.randomUUID = () => "11111111-1111-4111-8111-111111111111";
  });
  await page.addStyleTag({path: "static/css/main.css"});
  await page.addScriptTag({path: "static/js/breedingAttention.js"});
  await page.evaluate(() => load());
  await expect(page.locator("#attention_body tr")).toHaveCount(18);
}

test("desktop compact observation preview", async ({ page }) => {
  const pageErrors = [];
  page.on("pageerror", error => pageErrors.push(error.message));
  await page.setViewportSize({width: 1440, height: 1000});
  await mount(page);
  await page.locator(".observation-review").first().click();
  await page.locator("#obs_bcs").fill("3");
  await page.locator("#obs_note").fill("Observed standing and walking.");
  await page.locator("#obs_preview").click();
  expect(pageErrors).toEqual([]);
  await expect(page.locator("#obs_record")).toBeEnabled();
  await page.screenshot({path: "test-results/breeding-attention-phase2-desktop.png", fullPage: true});
});

test("mobile observation workflow remains one compact panel", async ({ page }) => {
  await page.setViewportSize({width: 390, height: 844});
  await mount(page);
  await page.locator(".observation-review").first().click();
  await expect(page.locator("#observation_panel")).toBeVisible();
  await page.screenshot({path: "test-results/breeding-attention-phase2-mobile.png", fullPage: true});
});
