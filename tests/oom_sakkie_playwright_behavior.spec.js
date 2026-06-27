const { test, expect } = require("@playwright/test");
const { spawn } = require("child_process");
const http = require("http");

const BASE_URL = process.env.OOM_SAKKIE_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5000";
const SERVER_URL = process.env.OOM_SAKKIE_PLAYWRIGHT_SERVER_URL || `${BASE_URL}/oom-sakkie`;
let serverProcess = null;

const READ_ONLY_JSON = {
  success: true,
  tools: [],
  mode: "local_kiosk_read_only",
  agents: [],
  traces: [],
  dry_runs: [],
  results: [],
  learning_influence_proposals: [],
  build_requests: [],
  patch_proposals: [],
  deploy_decisions: [],
};

function requestURL(url) {
  return new Promise((resolve) => {
    const request = http.get(url, (response) => {
      response.resume();
      resolve(response.statusCode && response.statusCode < 500);
    });
    request.on("error", () => resolve(false));
    request.setTimeout(1000, () => {
      request.destroy();
      resolve(false);
    });
  });
}

async function waitForServer(url, timeoutMs = 120000) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (await requestURL(url)) {
      return;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function stopServerProcess() {
  if (!serverProcess || serverProcess.killed) {
    return;
  }
  const processId = serverProcess.pid;
  serverProcess.kill();
  if (process.platform === "win32" && processId) {
    await new Promise((resolve) => {
      const killer = spawn("taskkill", ["/pid", String(processId), "/T", "/F"], { stdio: "ignore" });
      killer.on("exit", resolve);
      killer.on("error", resolve);
    });
  }
  serverProcess = null;
}

async function stubOomSakkieApi(page) {
  await page.route("**/api/telemetry/irrigation/status**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ success: false, error: "Playwright isolated telemetry dependency." }),
    });
  });
  await page.route("**/api/telemetry/weather/**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ success: false, error: "Playwright isolated weather dependency." }),
    });
  });
  await page.route("**/api/pig-weights/**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ success: false, error: "Playwright isolated Google Sheets dependency." }),
    });
  });
  await page.route("**/api/sales/meat-pilot-readiness**", async (route) => {
    await route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ success: false, status: "meat_readiness_unavailable" }),
    });
  });
  await page.route("**/api/beacon/facebook-image-launch-packet", async (route) => {
    await route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ success: false, status: "beacon_packet_unavailable" }),
    });
  });
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
    } else if (url.includes("/agent-dry-run-results") && request.method() === "GET") {
      body = {
        success: true,
        dry_run_results: [{
          dry_run_result_id: "OSK-AGENT-DRYRUN-RESULT-PLAYWRIGHT",
          dry_run_request_id: "OSK-AGENT-DRYRUN-PLAYWRIGHT",
          specialist_slug: "sentinel",
          result_text: "Owner cockpit Playwright result.",
          findings: ["Finding one"],
          latest_event: null,
        }],
        runs_specialist: false,
        dispatch_enabled: false,
        writes: false,
        applies_runtime_change: false,
      };
    } else if (url.includes("/events")) {
      body = { success: true };
    } else if (url.includes("/agent-learning/influence-proposals/from-result")) {
      body = {
        success: true,
        created_count: 1,
        accepted_count: 1,
        learning_influence_proposals: [],
        applies_learning_now: false,
        changes_prompt_now: false,
        changes_runtime_now: false,
        dispatch_enabled: false,
        writes: false,
      };
    } else if (url.includes("/agent-learning/influence-proposals/from-accepted")) {
      body = {
        success: true,
        created_count: 1,
        accepted_count: 1,
        learning_influence_proposals: [{
          proposal_id: "OSK-LEARNING-INFLUENCE-PLAYWRIGHT",
          source_result_id: "OSK-AGENT-DRYRUN-RESULT-PLAYWRIGHT",
          specialist_slug: "sentinel",
          proposal_title: "Learning proposal from Sentinel evidence",
          proposal_text: "Use accepted evidence as planning input only.",
          proposed_rules: ["Planning only", "Do not change runtime"],
          applies_learning_now: false,
          changes_prompt_now: false,
          changes_runtime_now: false,
          dispatch_enabled: false,
          writes: false,
          latest_event: null,
        }],
        applies_learning_now: false,
        changes_prompt_now: false,
        changes_runtime_now: false,
        dispatch_enabled: false,
        writes: false,
      };
    } else if (url.includes("/agent-learning/influence-proposals")) {
      body = {
        success: true,
        mode: "learning_influence_proposal_queue",
        learning_influence_proposals: [{
          proposal_id: "OSK-LEARNING-INFLUENCE-PLAYWRIGHT",
          source_result_id: "OSK-AGENT-DRYRUN-RESULT-PLAYWRIGHT",
          specialist_slug: "sentinel",
          proposal_title: "Learning proposal from Sentinel evidence",
          proposal_text: "Use accepted evidence as planning input only.",
          proposed_rules: ["Planning only", "Do not change runtime"],
          applies_learning_now: false,
          changes_prompt_now: false,
          changes_runtime_now: false,
          dispatch_enabled: false,
          writes: false,
          latest_event: null,
        }],
        applies_learning_now: false,
        changes_prompt_now: false,
        changes_runtime_now: false,
        dispatch_enabled: false,
        writes: false,
      };
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

async function waitForOomSakkieReady(page) {
  await expect(page.getByRole("heading", { name: "Amadeus Farm" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Agent dock" })).toBeVisible();
  await expect(page.locator(".oom-command-deck")).toBeAttached();
  await expect(page.locator(".oom-quick-drawer")).toBeAttached();
  await expect(page.locator(".oom-system-workbench")).toBeAttached();
  await expect(page.locator("#oom_presence_portrait")).toBeAttached();
}

test.beforeAll(async () => {
  if (await requestURL(SERVER_URL)) {
    return;
  }
  const configuredCommand = process.env.OOM_SAKKIE_PLAYWRIGHT_SERVER_COMMAND;
  if (configuredCommand) {
    serverProcess = spawn(configuredCommand, {
      cwd: process.cwd(),
      env: process.env,
      shell: true,
      stdio: "ignore",
    });
  } else {
    serverProcess = spawn(".\\venv\\Scripts\\python.exe", [
      "-m",
      "flask",
      "--app",
      "app",
      "run",
      "--host",
      "127.0.0.1",
      "--port",
      "5000",
      "--no-debugger",
      "--no-reload",
    ], {
      cwd: process.cwd(),
      env: process.env,
      shell: false,
      stdio: "ignore",
    });
  }
  await waitForServer(SERVER_URL);
});

test.afterAll(async () => {
  await stopServerProcess();
});

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
  await waitForOomSakkieReady(page);

  await expect(page.locator("#oom_presence_portrait")).toBeAttached();
  const ledgerAvatar = page.locator('[data-open-agent="ledger"] span');
  await expect(ledgerAvatar).toHaveText("LD");
  await expect(ledgerAvatar).toHaveAttribute("data-agent-color", "amber");
  await expect(ledgerAvatar).toHaveAttribute("data-asset-state", "fallback");
  const startupPosts = requests.filter((request) =>
    request.method !== "GET" && request.url.includes("/api/oom-sakkie/"),
  );
  expect(startupPosts).toEqual([]);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);
});

test("cockpit uses fallback assets and degraded background states", async ({ page }) => {
  await page.goto("/oom-sakkie");
  await waitForOomSakkieReady(page);

  await page.locator('[data-open-agent="ledger"]').click();
  await expect(page.locator("#oom_specialist_name")).toHaveText("Ledger");
  await expect(page.locator("#oom_specialist_avatar")).toHaveText("LD");
  await expect(page.locator("#oom_specialist_avatar")).toHaveAttribute("data-agent-color", "amber");
  await expect(page.locator("#oom_specialist_avatar")).toHaveAttribute("data-asset-state", "fallback");

  await page.locator(".oom-system-workbench").evaluate((element) => {
    element.open = true;
  });
  await expect(page.locator("#oom_meat_pilot_readiness")).toContainText("Pilot readiness is unavailable.");
  await expect(page.locator("#oom_beacon_image_launch")).toContainText("Beacon image launch is degraded");
  await expect(page.getByRole("heading", { name: "Amadeus Farm" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Agent dock" })).toBeVisible();
});

test("dry-run/result/message POSTs require explicit owner clicks", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => {
    let json = null;
    try {
      json = request.postDataJSON();
    } catch (error) {
      json = null;
    }
    requests.push({ method: request.method(), url: request.url(), json });
  });

  await page.goto("/oom-sakkie");
  await waitForOomSakkieReady(page);
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
  await expect(page.locator("#oom_owner_primary_decision")).toBeVisible();
  await page.getByRole("button", { name: "Accept For Learning" }).first().click();
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.includes("/api/oom-sakkie/agent-dry-run-results/OSK-AGENT-DRYRUN-RESULT-PLAYWRIGHT/events"),
  )).toBe(true);
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.includes("/api/oom-sakkie/agent-learning/influence-proposals/from-result"),
  )).toBe(true);
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" &&
    request.url.includes("/api/oom-sakkie/agent-learning/influence-proposals/from-result") &&
    request.json &&
    request.json.source_result_id === "OSK-AGENT-DRYRUN-RESULT-PLAYWRIGHT",
  )).toBe(true);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);

  requests.length = 0;
  await expect(page.locator("#oom_prepare_learning_influence")).toBeVisible();
  await page.locator("#oom_prepare_learning_influence").click();
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.endsWith("/api/oom-sakkie/agent-learning/influence-proposals/from-accepted"),
  )).toBe(true);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);

  requests.length = 0;
  await page.getByRole("button", { name: "Approve For Future Planning" }).first().click();
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.includes("/api/oom-sakkie/agent-learning/influence-proposals/OSK-LEARNING-INFLUENCE-PLAYWRIGHT/events"),
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
  await page.locator(".oom-system-workbench").evaluate((element) => {
    element.open = false;
  });
  await page.locator(".oom-quick-drawer").evaluate((element) => {
    element.open = false;
  });
  await page.getByRole("button", { name: "Daily Brief" }).click();
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.endsWith("/api/oom-sakkie/message"),
  )).toBe(true);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);
});
