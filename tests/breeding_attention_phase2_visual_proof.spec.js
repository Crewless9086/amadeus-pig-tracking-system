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

async function mount(page, placementCohorts = null) {
  await page.route("**/api/pig-weights/breeding-attention", route => route.fulfill({
    json: {
      success: true, source_status: "Available", observation_timestamp: "2026-07-27",
      animals, filters: ["Needs Data", "Post-litter recovery", "Pregnancy evidence"],
      counts: {"Needs Data": 6, "Post-litter recovery": 3, "Pregnancy evidence": 9},
      operating_loop: {
        success: true,
        week_start: "2026-07-27",
        task_count: 1,
        tasks: [{
          task_id: "HERD-TASK-MS-PIGGY",
          pig_id: "PROTECTED-SOW-1",
          tag_number: "Ms Piggy",
          animal_href: "#",
          task_group: "resolve evidence before mating review",
          why: "Inspection is complete and heat was not affirmatively observed.",
          required_checks: ["availability", "family-tree constraints", "withdrawal"],
          delay_consequence: "Mating remains unsupported.",
        }],
        placement_cohorts: placementCohorts,
      },
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
  await expect(page.locator("#breeding_worklist_tasks")).toContainText("Ms Piggy");
  await expect(page.locator("#breeding_worklist_tasks")).not.toContainText("body condition");
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
  await expect(page.locator(".breeding-task")).toHaveCount(1);
  await expect(page.locator(".breeding-task button")).toBeVisible();
  await page.locator(".observation-review").first().click();
  await expect(page.locator("#observation_panel")).toBeVisible();
  await page.screenshot({path: "test-results/breeding-attention-phase2-mobile.png", fullPage: true});
});

test("proposal and recovery groups cannot imply completed placement", async ({ page }) => {
  await mount(page, {
    cohorts: [{kind:"immediate", boar_name:"Prince", start_date:"2026-08-12",
      end_date:"2026-08-28", females:[{pig_id:"PROTECTED-SOW-1", name:"Bonnie",
        evidence_class:"Controlled trial"}]}],
    current_exposures: [],
    held: [{pig_id:"PROTECTED-SOW-2", name:"Waki", state:"Body condition recovery",
      reason:"Latest valid body condition 1, observed 2026-08-11, is below the governed minimum 3.",
      body_condition_score:1, body_condition_observed_at:"2026-08-11T14:57:00+00:00",
      boar_instruction:null, placement_date:null}],
  });
  const worklist = page.locator("#breeding_worklist_tasks");
  await expect(worklist).toContainText("Voorgestelde plasing");
  await expect(worklist).toContainText("Herstel / houvas");
  await expect(worklist).toContainText("Liggaamskondisie 1");
  await expect(worklist).not.toContainText("Plaas nou");
  await expect(page.locator("#attention_counts")).toContainText("Plan alleen; nie werklike plasing nie");
});
