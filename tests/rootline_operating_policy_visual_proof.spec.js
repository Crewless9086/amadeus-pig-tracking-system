const { test, expect } = require("@playwright/test");

const json = (route, body, status = 200) =>
  route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });

const policy = {
  success: true,
  status: "policy_review_ready",
  migration_applied: true,
  owner_can_administer: true,
  proposals: [{
    proposal_id: "ROOTLINE-POLICY-1234567890ABCDEF12345678",
    version: 1,
    lifecycle_state: "proposed",
    proposed_at: "2026-07-27T16:00:00+00:00",
  }],
};

const contract = {
  decision_guidance: [{
    question: "When do summer and winter policy periods begin?",
    recommendation: "Keep Unknown until Charl approves exact boundaries.",
    consequence: "Runtime advice remains suppressed.",
  }],
};

for (const viewport of [
  { name: "desktop", width: 1440, height: 1000 },
  { name: "mobile", width: 390, height: 844 },
]) {
  test(`${viewport.name} ROOTLINE policy review is clear and command-inert`, async ({ page }) => {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await page.route("**/api/**", route => {
      const path = new URL(route.request().url()).pathname;
      if (path.endsWith("/rootline/operating-policy/contract")) return json(route, contract);
      if (path.endsWith("/rootline/operating-policy")) return json(route, policy);
      return json(route, { success: true });
    });

    await page.goto("/rootline/policy-review", { waitUntil: "domcontentloaded" });
    const review = page.locator("main");
    await expect(review).toContainText("Command-inert policy review");
    await expect(review).toContainText("B12345 · lucerne");
    await expect(review).toContainText("C12345 · vegetables");
    await expect(review).toContainText("Controller power-loss state");
    await expect(review).toContainText("Residual drainage");
    await expect(review.getByRole("button", { name: "Preview advice effect" })).toBeVisible();
    await expect(review.getByRole("button", { name: "Record immutable proposal" })).toBeVisible();
    await expect(review.getByRole("button", { name: "Record owner review" })).toBeVisible();
    await expect(review.getByRole("button", { name: "Activate exact version for advice" })).toHaveCount(0);
    await expect(page.locator('[name="B12345_min"]')).toBeDisabled();
    await expect(page.locator('[name="power_note"]')).toBeDisabled();
    await expect(page.locator('[name="drainage_seconds"]')).toBeDisabled();
    await expect(page.locator('[name="drainage_note"]')).toBeDisabled();
    await expect(review).not.toContainText("Irrigate now");
    await expect(review).not.toContainText("Run valve");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
  });
}
