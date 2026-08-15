const { test, expect } = require("@playwright/test");

test("active litter follows the five-section paper lifecycle", async ({ page }, testInfo) => {
  await page.route("**/api/pig-weights/litter/LIT-2026-C9D3", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({success: true, litter: {
      litter_id: "LIT-2026-C9D3",
      mother_pig_id: "PIG-SOW",
      mother_tag_number: "Teena",
      father_pig_id: "PIG-BOAR",
      father_tag_number: "Bola",
      litter_status: "Active",
      detail_state: "active",
      count: 2,
      active_count: 2,
      male_count: 1,
      female_count: 1,
      mating_date: "2026-03-10",
      expected_farrowing_date: "2026-07-02",
      birth_date: "2026-07-02",
      estimated_wean_date: "2026-08-06",
      wean_tag_attention_start_date: "2026-08-03",
      days_until_estimated_wean: -4,
      lifecycle_outcomes: {active: 2, dead: 0, sold: 0, slaughtered: 0, removed: 0, other: 0},
      reconciliation: {total_born: 2, born_alive: 2, stillborn_count: 0, mismatch: false},
      attention: {action_type: "mark_weaned", reason: "Speen is vier dae laat.", recommended_action: "Voltooi die speenwerkvloei."},
      piglets: [
        {pig_id: "PIG-1", tag_number: "", sex: "Male", status: "Active", on_farm: "Yes", current_weight_kg: 8.4, wean_weight_kg: null, current_pen_id: "Kraam 01"},
        {pig_id: "PIG-2", tag_number: "202", sex: "Female", status: "Active", on_farm: "Yes", current_weight_kg: 9.1, wean_weight_kg: null, current_pen_id: "Kraam 01"},
      ],
    }}),
  }));
  await page.route("**/api/pig-weights/products", (route) => route.fulfill({status: 200, contentType: "application/json", body: JSON.stringify({products: []})}));
  await page.route("**/api/pig-weights/pens", (route) => route.fulfill({status: 200, contentType: "application/json", body: JSON.stringify({pens: []})}));

  await page.goto("/litter/LIT-2026-C9D3?return_to=%2Fmatings&return_label=Back+to+Breeding+Board");

  await expect(page.locator("#litter_title")).toHaveText("Werpsel - LIT-2026-C9D3");
  await expect(page.locator(".lifecycle-stage")).toHaveCount(5);
  for (const heading of ["Paring en identiteit", "Geboorte", "Eerste behandeling", "Speen en tweede behandeling", "Vrektes en notas"]) {
    await expect(page.getByRole("heading", {name: heading, exact: true})).toBeVisible();
  }
  await expect(page.locator("#lifecycle_next_action")).toContainText("Speen");
  await expect(page.locator("#newborn_health_form")).toBeVisible();
  await expect(page.locator("#weaning_day_form")).toBeVisible();
  await expect(page.locator("#piglet_death_form")).toBeVisible();
  await expect(page.locator(".litter-piglet-table th")).toHaveCount(6);
  await expect(page.locator(".lifecycle-corrections")).not.toHaveAttribute("open", "");
  await page.screenshot({path: testInfo.outputPath("litter-lifecycle-desktop.png"), fullPage: true});
});
