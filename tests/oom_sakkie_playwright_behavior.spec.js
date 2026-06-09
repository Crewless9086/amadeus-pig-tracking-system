const { test, expect } = require("@playwright/test");

const READ_ONLY_JSON = {
  success: true,
  tools: [],
  mode: "local_kiosk_read_only",
  agents: [],
  traces: [],
  dry_runs: [],
  results: [],
  build_requests: [],
  patch_proposals: [],
  deploy_decisions: [],
};

async function stubOomSakkieApi(page) {
  await page.route("**/api/oom-sakkie/**", async (route) => {
    const request = route.request();
    const url = request.url();
    let body = READ_ONLY_JSON;
    if (url.endsWith("/message")) {
      body = {
        success: true,
        answer: "Read-only Playwright answer.",
        tool_used: "farm_attention_summary",
        trace_id: "OSK-TRACE-PLAYWRIGHT",
        risk_level: 0,
        stale_warnings: [],
        safety_notes: ["Playwright read-only smoke."],
        links: [],
        pipeline: {},
        agent_activity: {},
      };
    } else if (url.endsWith("/agent-dry-runs") && request.method() === "POST") {
      body = {
        success: true,
        dry_run_request_id: "OSK-AGENT-DRYRUN-PLAYWRIGHT",
        specialist_slug: "sentinel",
      };
    } else if (url.includes("/agent-dry-runs/") && url.endsWith("/results")) {
      body = {
        success: true,
        dry_run_result_id: "OSK-AGENT-DRYRUN-RESULT-PLAYWRIGHT",
      };
    } else if (url.includes("/review-packet")) {
      body = {
        success: true,
        mode: "dry_run_result_review_packet",
        result_text: "Review packet only.",
        findings: [],
        owner_options: [],
        review_guard: {
          runs_specialist: false,
          dispatch_enabled: false,
          writes: false,
        },
      };
    } else if (url.includes("/events")) {
      body = { success: true };
    } else if (url.includes("/runtime-review-packet")) {
      body = {
        success: true,
        mode: "agent_runtime_review_packet_only",
        summary_status: "ready_for_bulk_claude_review_not_live_dispatch",
        dispatch_enabled: false,
        writes_enabled: false,
        review_guard: {
          runs_specialist: false,
          dispatch_enabled: false,
          writes: false,
        },
      };
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(body),
    });
  });
}

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    window.__oomSakkieIntervals = [];
    const originalSetInterval = window.setInterval.bind(window);
    window.setInterval = (...args) => {
      window.__oomSakkieIntervals.push({ delay: args[1] });
      return originalSetInterval(...args);
    };
  });
  await stubOomSakkieApi(page);
});

test("kiosk startup performs no hidden POSTs or interval polling", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => requests.push({ method: request.method(), url: request.url() }));

  await page.goto("/oom-sakkie");
  await page.waitForLoadState("networkidle");

  const startupPosts = requests.filter((request) =>
    request.method !== "GET" && request.url.includes("/api/oom-sakkie/"),
  );
  expect(startupPosts).toEqual([]);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);
});

test("dry-run/result/message POSTs require explicit owner clicks", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => requests.push({ method: request.method(), url: request.url() }));

  await page.goto("/oom-sakkie");
  await page.waitForLoadState("networkidle");
  await expect(page.locator(".oom-command-deck")).toBeVisible();
  await expect(page.locator(".oom-quick-drawer")).toBeVisible();
  await page.locator(".oom-system-workbench").evaluate((element) => {
    element.open = true;
  });
  requests.length = 0;

  await expect(page.locator("#oom_request_sentinel_dry_run")).toBeVisible();
  await page.locator("#oom_request_sentinel_dry_run").click();
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.endsWith("/api/oom-sakkie/agent-dry-runs"),
  )).toBe(true);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);

  requests.length = 0;
  await page.locator("#oom_agent_dry_run_result_request_id").fill("OSK-AGENT-DRYRUN-PLAYWRIGHT");
  await page.locator("#oom_agent_dry_run_result_text").fill("Playwright result text.");
  await page.locator("#oom_agent_dry_run_result_findings").fill("Finding one\nFinding two");
  await page.locator("#oom_record_agent_dry_run_result").click();
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.includes("/api/oom-sakkie/agent-dry-runs/OSK-AGENT-DRYRUN-PLAYWRIGHT/results"),
  )).toBe(true);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);

  requests.length = 0;
  await page.locator(".oom-quick-drawer").evaluate((element) => {
    element.open = true;
  });
  await expect.poll(() => requests.filter((request) =>
    request.method !== "GET" && request.url.includes("/api/oom-sakkie/"),
  ).length).toBe(0);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);

  requests.length = 0;
  await page.locator(".oom-command-deck [data-quick-ask]").first().click();
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.endsWith("/api/oom-sakkie/message"),
  )).toBe(true);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);
});
