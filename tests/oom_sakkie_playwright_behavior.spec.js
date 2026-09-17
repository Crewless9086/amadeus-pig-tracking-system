const { test, expect } = require("@playwright/test");

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
    } else if (url.endsWith("/owner-attention") && request.method() === "GET") {
      const attentionItems = [
        { work_id: "attn-welfare", title: "Prince has an active welfare case.", specialist_owner: "HERDMASTER", task_class: "status_reconciliation", priority: "urgent", freshness: "current", exact_owner_action: "HERDMASTER owns current status reconciliation.", semantic_emoji: "🔄", detail_target: "/pig/PIG-125" },
        { work_id: "attn-molly", title: "Molly — litter first treatment is due and ready.", specialist_owner: "HERDMASTER", task_class: "physical_action_due", priority: "due", freshness: "current", exact_owner_action: "Molly's litter — perform the first treatment now in the existing litter treatment journey.", semantic_emoji: "⚖️", detail_target: "/litter/LIT-MOLLY" },
        { work_id: "attn-weight", title: "Weekly weighing is upcoming.", specialist_owner: "HERDMASTER", task_class: "physical_action_due", priority: "planned", freshness: "current", exact_owner_action: "Weigh during the governed Monday window.", semantic_emoji: "👀", detail_target: "/bulk-weights" },
        { work_id: "attn-rootline", title: "ROOTLINE retry is pending.", specialist_owner: "ROOTLINE", task_class: "status_reconciliation", priority: "watch", freshness: "aging", exact_owner_action: "No owner action now — ROOTLINE owns the retry.", semantic_emoji: "🔄", detail_target: "/irrigation" },
      ];
      attentionItems[0] = { ...attentionItems[0], attention_group: "oom_sakkie_checking", owner_action_eligible: false, owner_urgency: "none", operational_status: "waiting_reassessment", assigned_to: "Oom Sakkie / Herdmaster", secondary_reference: "tag 125", provenance: ["pig:PIG-125"] };
      attentionItems[1] = { ...attentionItems[1], attention_group: "farm_work_ready", owner_action_eligible: true, owner_urgency: "due", operational_status: "open", assigned_to: "Farm team", secondary_reference: "LIT-MOLLY", provenance: ["litter:LIT-MOLLY"] };
      attentionItems[2] = { ...attentionItems[2], attention_group: "watch", owner_action_eligible: false, owner_urgency: "none", operational_status: "open", assigned_to: "Herdmaster", secondary_reference: "weekly cohort", provenance: ["cohort:weekly"] };
      attentionItems[3] = { ...attentionItems[3], attention_group: "oom_sakkie_checking", owner_action_eligible: false, owner_urgency: "none", operational_status: "delegated", assigned_to: "oom-manager-cycle", secondary_reference: "current plan", provenance: ["plan:current"] };
      body = {
        success: true,
        total_count: 1,
        open_context_count: 4,
        hidden_count: 0,
        view_all_target: "/owner-attention",
        items: attentionItems,
        top_items: [attentionItems[1]],
        groups: { needs_you: [], farm_work_ready: [attentionItems[1]], oom_sakkie_checking: [attentionItems[0], attentionItems[3]], watch: [attentionItems[2]], recently_completed: [] },
        group_counts: { needs_you: 0, farm_work_ready: 1, oom_sakkie_checking: 2, watch: 1, recently_completed: 0 },
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

async function authenticateOwner(page) {
  await page.goto("/owner/login?next=/owner-attention");
  await page.locator('input[name="owner_token"]').fill(process.env.OWNER_READ_TOKEN);
  await Promise.all([
    page.waitForURL("**/owner-attention"),
    page.locator('button[type="submit"]').click(),
  ]);
}

test("authenticated owner attention is accessible and responsive", async ({ page }, testInfo) => {
  await authenticateOwner(page);
  await page.goto("/");
  await expect(page.locator(".attention-item")).toHaveCount(1);
  await expect(page.locator(".attention-item").first()).toHaveAttribute("data-work-id", "attn-molly");
  await expect(page.locator(".attention-item").first()).toHaveAttribute("href", "/litter/LIT-MOLLY");
  await expect(page.locator("#attention_view_all")).toHaveText("Full view · 4 current");
  await testInfo.attach("owner-attention-home-desktop", {
    body: await page.screenshot({ fullPage: true }), contentType: "image/png",
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await testInfo.attach("owner-attention-home-mobile", {
    body: await page.screenshot({ fullPage: true }), contentType: "image/png",
  });
  await page.locator("#attention_view_all").click();
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.setViewportSize({ width: 1280, height: 720 });
  await expect(page.getByRole("heading", { name: "Owner attention" })).toBeVisible();
  await expect(page.locator(".attention-all-item")).toHaveCount(4);
  await expect(page.locator(".attention-all-item").first().locator(".attention-detail-link"))
    .toHaveAttribute("href", "/litter/LIT-MOLLY");
  await expect(page.locator(".attention-all-item").first()).toContainText("Molly");
  await expect(page.getByText("Prince has an active welfare case.")).not.toBeVisible();
  await page.getByText("Oom Sakkie is checking").click();
  await expect(page.getByText("Prince has an active welfare case.")).toBeVisible();
  await expect(page.getByText("No owner action now — ROOTLINE owns the retry.")).toBeVisible();
  await expect(page.locator('.attention-emoji[aria-hidden="true"]')).toHaveCount(4);
  await page.locator(".manager-link").focus();
  await page.keyboard.press("Tab");
  await expect(page.locator(".attention-group").first().locator(":scope > summary")).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await testInfo.attach("owner-attention-desktop", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".attention-all-item").first()).toBeVisible();
  await page.locator(".attention-detail-link").first().focus();
  await expect(page.locator(".attention-detail-link").first()).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  await testInfo.attach("owner-attention-mobile", {
    body: await page.screenshot({ fullPage: true }),
    contentType: "image/png",
  });
});

test("kiosk startup performs no hidden POSTs or interval polling", async ({ page }) => {
  const requests = [];
  page.on("request", (request) => requests.push({ method: request.method(), url: request.url() }));

  await page.goto("/oom-sakkie");
  await page.waitForLoadState("networkidle");

  const presencePortrait = page.locator("#oom_presence_portrait img");
  await expect(presencePortrait).toBeVisible();
  await expect.poll(() => presencePortrait.evaluate((img) => img.naturalWidth > 0 && img.naturalHeight > 0)).toBe(true);
  const startupPosts = requests.filter((request) =>
    request.method !== "GET" && request.url.includes("/api/oom-sakkie/"),
  );
  expect(startupPosts).toEqual([]);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);
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
  await page.locator(".oom-command-deck [data-quick-ask]").first().click();
  await expect.poll(() => requests.some((request) =>
    request.method === "POST" && request.url.endsWith("/api/oom-sakkie/message"),
  )).toBe(true);
  await expect.poll(() => page.evaluate(() => window.__oomSakkieIntervals.length)).toBe(0);
});

test("purpose review compatibility opens the responsive unified allocation mode", async ({ page }) => {
  await page.route("**/api/pig-weights/pig-allocation-readiness", route => route.fulfill({
    status: 200, contentType: "application/json", body: JSON.stringify({
      success: true, generated_date: "2026-08-21",
      summary: { total: 1, buckets: { "Needs Classification": 1 } },
      business_rules: { source: "terminal-invoked synthetic fixture" },
      pigs: [{ pig_id: "PIG-SYNTH-1", tag_number: "Rosie", litter_id: "LIT-SYNTH-1",
        sow_tag_number: "Molly", status: "Active", on_farm: "Yes", purpose: "Unknown",
        readiness_bucket: "Needs Classification", suggested_purpose: "Breeding Review",
        suggested_purpose_reason: "Synthetic growth and litter evidence.",
        recommended_action: "Review purpose", current_pen_name: "Weaner pen" }],
    }),
  }));
  await page.route("**/api/pig-weights/riversdale-auction-**", route => route.fulfill({
    status: 503, contentType: "application/json", body: JSON.stringify({ success: false }),
  }));
  await page.goto("/purpose-review?litter_id=LIT-SYNTH-1");
  await expect(page).toHaveURL(/\/pig-allocation\?mode=purpose-review&litter_id=LIT-SYNTH-1$/);
  await expect(page.getByRole("heading", { name: "Pig Allocation · Purpose Review" })).toBeVisible();
  await expect(page.getByText("Rosie", { exact: true })).toBeVisible();
  await expect(page.locator("#riversdale_auction_panel")).toBeHidden();
  await expect(page.locator("label[for='search_filter']")).toHaveText("Search");
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    await page.setViewportSize(viewport);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(1);
    await expect(page.locator("#allocation_review_panel")).toBeVisible();
  }
});
