const { test, expect } = require("@playwright/test");

const fixture = {
  success: true,
  authority_boundary: "Read-only requested-items draft. No pig is attached, allocated, reserved, promised, re-purposed or sold by this preview.",
  purpose_or_evidence_review: [],
  recommendations: [
    line("f56", "Female", "5_to_6_Kg", 10, [pig("501", "Female", 5.6, "2026-08-18", 400)]),
    line("m56", "Male", "5_to_6_Kg", 10, [pig("502", "Male", 5.5, "2026-08-18", 400, { product: "Ecomectin 1%", withdrawal_end_date: "2026-09-08" })]),
    line("f15", "Female", "15_to_19_Kg", 1, [pig("601", "Female", 15.2, "2026-08-17", 950)]),
    line("m15", "Male", "15_to_19_Kg", 1, []),
  ],
};

function pig(tag, sex, weight, weightDate, price, disclosure = null) {
  return { pig_id: `PIG-${tag}`, tag_number: tag, sex, current_weight_kg: weight,
    weight_date: weightDate, unit_price: price, weight_confidence: "fresh",
    medicine_indicator: disclosure ? `Food-chain restriction through ${disclosure.withdrawal_end_date}` : "No current recorded food-chain restriction",
    treatment_disclosure: disclosure };
}

function line(key, sex, weightRange, requested, candidates) {
  return { request_item_key: key, sex, weight_range: weightRange, requested_quantity: requested,
    status: candidates.length === requested ? "supported" : candidates.length ? "partial" : "unavailable",
    available_quantity: candidates.length, shortfall_quantity: requested - candidates.length,
    recommended_subtotal: candidates.reduce((sum, item) => sum + item.unit_price, 0) || null, candidates };
}

test("authenticated owner can enter four livestock lines once and inspect a truthful zero-write quote", async ({ page }, testInfo) => {
  const requests = [];
  page.on("request", request => requests.push({ method: request.method(), url: request.url() }));
  await page.goto("/owner/login?next=/orders/new");
  await page.locator('input[name="owner_token"]').fill(process.env.OWNER_READ_TOKEN);
  await page.locator('button[type="submit"]').click();
  await expect(page).toHaveURL(/\/orders\/new/);
  await page.route("**/api/orders/livestock-quote-preview", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(fixture) }));

  const lines = page.locator(".livestock-request-line");
  await expect(lines).toHaveCount(4);
  await expect(lines.nth(0).locator('[data-field="quantity"]')).toHaveValue("10");
  await expect(lines.nth(0).locator('[data-field="sex"]')).toHaveValue("Female");
  await expect(lines.nth(0).locator('[data-field="weight_range"]')).toHaveValue("5_to_6_Kg");
  await expect(lines.nth(1).locator('[data-field="quantity"]')).toHaveValue("10");
  await expect(lines.nth(1).locator('[data-field="sex"]')).toHaveValue("Male");
  await expect(lines.nth(2).locator('[data-field="quantity"]')).toHaveValue("1");
  await expect(lines.nth(2).locator('[data-field="sex"]')).toHaveValue("Female");
  await expect(lines.nth(2).locator('[data-field="weight_range"]')).toHaveValue("15_to_19_Kg");
  await expect(lines.nth(3).locator('[data-field="quantity"]')).toHaveValue("1");
  await expect(lines.nth(3).locator('[data-field="sex"]')).toHaveValue("Male");

  await page.locator("#customer_name").fill("Local preview only");
  await page.locator("#customer_channel").selectOption("Manual");
  await page.locator("#customer_language").selectOption("English");
  await page.locator("#order_source").selectOption("Manual");
  await page.locator("#addOrderForm button[type=submit]").click();
  await expect(page.getByRole("heading", { name: "Draft quote preview", exact: true })).toBeVisible();
  await expect(page.getByText("available 1 · shortfall 9").first()).toBeVisible();
  await expect(page.getByText("available 0 · shortfall 1")).toBeVisible();
  await expect(page.getByText(/Tag 502.*Male.*5.5 kg.*2026-08-18.*R400.00/)).toBeVisible();
  await expect(page.getByRole("heading", { name: "Consolidated medicine disclosure" })).toBeVisible();
  await expect(page.getByText(/Tags 502.*Ecomectin 1%.*2026-09-08/)).toBeVisible();
  await expect(page.getByText(/does not reserve pigs or certify veterinary, quarantine or transport clearance/)).toBeVisible();
  expect(requests.filter(item => item.method !== "GET" && !item.url.includes("/owner/login") && !item.url.includes("livestock-quote-preview"))).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("livestock-quote-desktop.png"), fullPage: true });

  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.locator("body").evaluate(el => el.scrollWidth <= el.clientWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("livestock-quote-390px.png"), fullPage: true });
});
