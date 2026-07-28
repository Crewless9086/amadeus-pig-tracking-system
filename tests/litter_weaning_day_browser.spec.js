const { test, expect } = require("@playwright/test");
const fs = require("fs");

const source = fs.readFileSync("static/js/litterDetail.js", "utf8");
const helper = source.match(
  /async function readWeaningDayResponse\(response\) \{[\s\S]*?\n\}/
);

test.beforeEach(async ({ page }) => {
  expect(helper).not.toBeNull();
  await page.setContent("<main>Weaning Day response harness</main>");
  await page.addScriptTag({content: helper[0]});
});

test("non-JSON failure gives no-retry recovery guidance", async ({ page }) => {
  const result = await page.evaluate(async () => {
    const response = new Response("<html>worker timeout</html>", {
      status: 500,
      headers: {"content-type": "text/html", "x-request-id": "REQ-SAFE"},
    });
    try {
      await readWeaningDayResponse(response);
      return {accepted: true};
    } catch (error) {
      return {accepted: false, message: error.message};
    }
  });
  expect(result.accepted).toBe(false);
  expect(result.message).toContain("Do not press Save again");
  expect(result.message).toContain("reload the litter");
  expect(result.message).toContain("REQ-SAFE");
  expect(result.message).not.toContain("<html>");
});

test("structured JSON remains available to the existing workflow", async ({ page }) => {
  const result = await page.evaluate(async () => {
    const response = new Response(JSON.stringify({
      success: false,
      status: "weaning_day_transaction_failed",
    }), {
      status: 503,
      headers: {"content-type": "application/json; charset=utf-8"},
    });
    return readWeaningDayResponse(response);
  });
  expect(result).toEqual({
    success: false,
    status: "weaning_day_transaction_failed",
  });
});
