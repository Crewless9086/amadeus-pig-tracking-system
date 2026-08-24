const { test, expect } = require("@playwright/test");

const blockedMission = {
  mission_id: "CHARLIE-MISSION-UI-1",
  title: "Herdmaster allocation alert engine",
  raw_text: "Build a deterministic owner-safe alert engine.",
  status: "blocked",
  urgency: "P1",
  approval_level: "LEVEL 3",
  mission_type: "system improvement",
  queue_class: "owner_work",
  agent_workflow: [
    { agent: "planner", status: "complete", findings: "Plan complete." },
    { agent: "builder", status: "blocked", findings: "PR evidence is missing." },
    { agent: "tester", status: "pending", findings: "Waiting for corrected build." },
  ],
  metadata: {
    owner_action_guidance: {
      recommended_action: "send_back",
      button_label: "Send Back to Builder",
      target_stage: "builder",
      reason: "Builder must attach the missing PR evidence.",
      what_happens: "CORE preserves the plan and resumes at Builder.",
      alternative_action: "approve_rerun",
    },
    stage_telemetry: {
      execution_id: "EXEC-1",
      last_progress_at: "2026-07-14T08:00:30+00:00",
      stages: [
        { agent: "planner", status: "complete", attempt: 1, duration_seconds: 75, changed_files_count: 0 },
        { agent: "builder", status: "blocked", attempt: 2, duration_seconds: 620, changed_files_count: 3 },
      ],
    },
    mission_governance: {
      acceptance_percent: 67,
      acceptance_counts: { passed: 2, failed: 1, pending: 0 },
      acceptance_matrix: [
        { id: "scope", requirement: "Build the scoped alert engine", status: "passed", evidence_required: "Focused tests" },
        { id: "evidence", requirement: "Attach reviewable PR evidence", status: "failed", evidence_required: "PR link and commit" },
        { id: "authority", requirement: "Keep owner authority intact", status: "passed", evidence_required: "Authority invariant" },
      ],
      fix_count: 3,
      review_runs: 4,
      backflow_count: 2,
      followup_count: 1,
      cycling: false,
      budget: { mission_limit: 4 },
    },
    review_packet: {
      summary: "Builder stopped before owner review.",
      blocked_agent: "builder",
      blocked_reason: "PR evidence is missing.",
      recommended_next_action: "Return to builder with the missing evidence requirement.",
      test_evidence: ["Focused unit tests passed."],
    },
  },
};

test("mission cockpit loads useful evidence and send-back requires owner comments", async ({ page }) => {
  let reviewRequest = null;
  await page.route("**/api/charlie/build-relay/mission-control**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      success: true,
      counts: { blocked: 1, new: 3, pr_ready: 0, approved: 0, done: 8 },
      buckets: { active: [], new: [], approved: [], review: [], blocked: [blockedMission] },
    }),
  }));
  await page.route("**/api/charlie/build-relay/runner/status**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ success: true, local_runner_scope: "render_cannot_see_laptop_runner", local_runner: {} }),
  }));
  await page.route("**/api/charlie/build-relay/policy**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ success: true, charlie_build_relay: { enabled: true } }),
  }));
  await page.route("**/api/charlie/build-relay/missions/CHARLIE-MISSION-UI-1/review", async (route) => {
    if (route.request().method() === "POST") reviewRequest = route.request().postDataJSON();
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true }) });
  });

  await page.goto("/charlie-v2");
  await expect(page.getByText("Herdmaster allocation alert engine").first()).toBeVisible();
  await expect(page.getByText("PR evidence is missing.").first()).toBeVisible();
  await expect(page.getByText("builder", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Acceptance Matrix")).toBeVisible();
  await expect(page.getByText("Send Back to Builder", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Try 2 | 10m 20s | 3 files", { exact: true })).toBeVisible();
  await expect(page.getByText("3 fixes", { exact: false }).first()).toBeVisible();
  await page.getByRole("button", { name: "Send Back to Builder", exact: true }).click();
  await expect(page.getByText("What must be corrected")).toBeVisible();
  await page.locator("#sendBackComments").fill("Attach the PR and rerun the focused tests.");
  await page.locator("#sendBackStage").selectOption("builder");
  await page.getByRole("button", { name: "Send Back to Agent" }).click();

  expect(reviewRequest).toEqual(expect.objectContaining({
    decision: "send_back",
    target_stage: "builder",
    comments: "Attach the PR and rerun the focused tests.",
  }));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(0);
});

test("control tower owner work is visible without false blocked or runner actions", async ({ page }) => {
  const working = {
    ...blockedMission,
    mission_id: "OMQ-20260813-03",
    title: "Oom Sakkie continuous farm manager",
    owner_projection: {
      outcome: "Operate the daily farm loop.",
      real_life_state: "working",
      current_worker: "Control Tower",
      next_automatic_step: "Continue the reviewed repair.",
      owner_action: "NONE",
    },
  };
  const waiting = {
    ...blockedMission,
    mission_id: "CMQ-20260813-05",
    title: "CORE operating spine",
    status: "paused",
    owner_projection: {
      outcome: "Complete one governed mission automatically.",
      real_life_state: "event_waiting",
      current_worker: "Control Tower",
      next_automatic_step: "Wait for the next governed event.",
      owner_action: "NONE",
    },
  };
  await page.route("**/api/charlie/build-relay/mission-control**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({
      success: true,
      counts: { blocked: 1, paused: 1 },
      buckets: { active: [waiting], new: [], approved: [], review: [], blocked: [working] },
    }),
  }));
  await page.route("**/api/charlie/build-relay/runner/status**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ success: true, local_runner_scope: "render_cannot_see_laptop_runner", local_runner: {} }),
  }));
  await page.route("**/api/charlie/build-relay/policy**", (route) => route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify({ success: true, charlie_build_relay: { enabled: true } }),
  }));

  await page.goto("/charlie-v2");
  await expect(page.getByText("CORE operating spine").first()).toBeVisible();
  await expect(page.getByText("EVENT WAITING", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Automatic work continues safely. No owner action is needed.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve Rerun" })).toHaveCount(0);

  await page.getByRole("button", { name: /Blocked 1/ }).click();
  await expect(page.getByText("Oom Sakkie continuous farm manager").first()).toBeVisible();
  await expect(page.getByText("WORKING", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Execution stopped", { exact: false })).toHaveCount(0);
  await expect(page.getByText("Control Tower", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Control Tower progress is shown from the canonical owner-work projection", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve Rerun" })).toHaveCount(0);
});
