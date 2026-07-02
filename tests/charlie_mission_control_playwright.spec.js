const { test, expect } = require("@playwright/test");

const missionId = "CHARLIE-MISSION-PLAYWRIGHT-REVIEW";

const reviewPacket = {
  review_status: "ready_for_owner_review",
  summary: "Playwright review packet with real owner actions, evidence, and PR proof.",
  findings: ["Owner action buttons are visible.", "Evidence details stay open."],
  errors: [],
  bugs: [],
  changed_files: ["templates/charlie.html", "static/js/charlieMissionControl.js", "static/css/main.css"],
  test_evidence: ["node --check static/js/charlieMissionControl.js", "Playwright desktop and mobile smoke"],
  qa_evidence: ["No hidden buttons or overflow in smoke viewports."],
  release_notes: ["Owner approval remains required before merge."],
  local_preview: { url: "http://127.0.0.1:5000/charlie", status: "captured" },
  links: { pr: "https://github.com/example/amadeus-pig-tracking-system/pull/999" },
  visual_review: {
    status: "captured",
    summary: "Desktop and mobile screenshots captured by Playwright.",
    media: [],
  },
  agent_execution: {
    stages: [
      { agent: "builder", status: "pass", current_action: "Built command center", commands_run: ["node --check"], changed_files: ["static/js/charlieMissionControl.js"] },
      { agent: "tester", status: "pass", current_action: "Ran browser smoke", commands_run: ["npx playwright test"], changed_files: ["tests/charlie_mission_control_playwright.spec.js"] },
    ],
  },
  quality_gates: [{ agent: "tester", status: "pass", reason: "Smoke checks passed." }],
  unresolved_blockers: [],
};

const missions = [
  {
    mission_id: "CHARLIE-MISSION-PLAYWRIGHT-ACTIVE",
    title: "P0 Bulk Weights Fix",
    raw_text: "Supabase canonical migration runner work.",
    status: "in_progress",
    urgency: "P0",
    approval_level: "LEVEL 3",
    mission_type: "system improvement",
    queue_priority: 10,
    queue_class: "owner_work",
    updated_at: "2026-07-02T18:00:00Z",
    vault: { mission_stage: "builder", confidence_target: "98% before release review" },
    agent_workflow: [
      { agent: "idea_expander", status: "complete" },
      { agent: "planner", status: "complete" },
      { agent: "builder", status: "active", summary: "Running migration-safe build" },
      { agent: "tester", status: "pending" },
      { agent: "reviewer", status: "pending" },
    ],
    metadata: {},
  },
  {
    mission_id: missionId,
    title: "Sales Dashboard Revamp",
    raw_text: "UI and data pipeline review-ready packet.",
    status: "pr_ready",
    urgency: "P1",
    approval_level: "LEVEL 3",
    mission_type: "system improvement",
    queue_priority: 20,
    queue_class: "owner_work",
    updated_at: "2026-07-02T18:10:00Z",
    vault: { mission_stage: "review_ready", desired_outcome: "Owner can approve or send back." },
    agent_workflow: [
      { agent: "builder", status: "complete" },
      { agent: "tester", status: "complete" },
      { agent: "qa_red_team", status: "complete" },
      { agent: "reviewer", status: "complete" },
    ],
    metadata: { review_packet: reviewPacket, owner_review_decisions: [] },
  },
  {
    mission_id: "CHARLIE-MISSION-PLAYWRIGHT-BLOCKED",
    title: "Meat Planning Workflow",
    raw_text: "Optimization blocked by missing price book data.",
    status: "blocked",
    urgency: "P1",
    approval_level: "LEVEL 3",
    mission_type: "system improvement",
    queue_priority: 30,
    queue_class: "owner_work",
    updated_at: "2026-07-02T18:20:00Z",
    vault: { mission_stage: "blocked" },
    agent_workflow: [{ agent: "tester", status: "blocked" }],
    metadata: {
      review_packet: {
        review_status: "agent_blocked",
        blocked_agent: "tester",
        blocked_reason: "Missing Price Book Data",
        summary: "Blocked until pricing source is confirmed.",
        unresolved_blockers: [{ severity: "high", finding: "Confirm price book source before release.", file: "sales-dashboard" }],
      },
    },
  },
];

async function stubCharlieApi(page) {
  await page.route("**/api/charlie/**", async (route) => {
    const request = route.request();
    const url = request.url();
    let body = { success: true };
    if (url.includes("/missions/summary")) {
      body = {
        success: true,
        counts: { new: 0, approved: 1, in_progress: 1, blocked: 1, pr_ready: 1, release_approved: 0, release_in_progress: 0, merged: 0, deployed: 0 },
      };
    } else if (url.includes("/runner/status")) {
      body = {
        success: true,
        status: "active_mission_in_progress",
        next_action: "Local runner connected and building the active mission.",
        active_mission: missions[0],
        next_approved_mission: null,
        next_release_approved_mission: null,
        local_runner: {
          active: true,
          pid: 4242,
          last_seen: "2026-07-02T18:25:00Z",
          age_seconds: 4,
          current_agent: "builder",
          current_action: "Running migration",
          agent_runner_version: "v2",
          agent_ledger_path: ".charlie_runner/ledger.json",
          execution_artifact: ".charlie_runner/builder.final.md",
          agent_ledger: { latest_stage: { agent: "builder", status: "running", attempt: 1, summary: "Builder is active." } },
        },
      };
    } else if (url.includes("/command-center")) {
      body = {
        success: true,
        queue: { approved: [missions[0]], ordering: "priority order" },
        review: { ready: [missions[1]], blocked: [missions[2]] },
        release: { waiting_final_bridge: [], in_progress: [], verify_url_configured: true },
        vault: { version: "charlie_vault_brain_context_v1", storage: "metadata_json active", health: { status: "ok", missing_tables: [] } },
        charlie_core: { overall_target: "90%+ target", recent_readiness: [], owner_preferences: { preferences: ["visible owner actions"] }, model_registry: { models: {} }, tool_permissions: { agent_tool_allowlist: {} } },
        autonomy_readiness: { percent: 35, safe_mode: "supervised" },
        local_runner: { active: true, current_agent: "builder", current_action: "Running migration" },
        improvements: { pending: [], status: "proposal store" },
        execution_boundary: "Local runner executes builds; dashboard records owner decisions only.",
      };
    } else if (url.includes(`/missions/${missionId}/review`) && request.method() === "GET") {
      body = { success: true, review_packet: reviewPacket };
    } else if (url.includes("/missions")) {
      body = { success: true, missions };
    }
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function expectNoHorizontalOverflow(page) {
  const metrics = await page.evaluate(() => ({
    body: document.body.scrollWidth,
    viewport: document.documentElement.clientWidth,
    offenders: Array.from(document.body.querySelectorAll("*"))
      .map((element) => {
        const rect = element.getBoundingClientRect();
        return { tag: element.tagName, className: element.className, id: element.id, right: rect.right, left: rect.left, width: rect.width };
      })
      .filter((item) => item.width > 1 && (item.right > document.documentElement.clientWidth + 2 || item.left < -2))
      .slice(0, 8),
  }));
  expect(metrics.body).toBeLessThanOrEqual(metrics.viewport + 2);
  expect(metrics.offenders).toEqual([]);
}

test.describe("CHARLIE CORE Mission Control", () => {
  test.beforeEach(async ({ page }) => {
    await stubCharlieApi(page);
  });

  test("desktop command center keeps owner review actions and evidence visible", async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 950 });
    await page.goto("/charlie");
    await expect(page.locator("h1")).toContainText("CHARLIE CORE Mission Control");
    await expect(page.locator(".charlie-mission-lane.is-review")).toBeVisible();
    await expect(page.getByRole("button", { name: "Open Review" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve Final" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Send Back" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Pause" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Reject" }).first()).toBeVisible();
    await expect(page.locator(".charlie-evidence-details").first()).toHaveAttribute("open", "");
    await expect(page.locator("#charlie_runner_state")).toContainText("In Progress");
    await expect(page.locator("#charlie_artifact_summary")).toContainText("Changed files");
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: "test-results/charlie-command-center-desktop.png", fullPage: true });
  });

  test("mobile command center stacks without hiding review controls", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 900 });
    await page.goto("/charlie");
    await expect(page.locator(".charlie-system-status")).toBeVisible();
    await expect(page.getByRole("button", { name: "Open Review" }).first()).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve Final" }).first()).toBeVisible();
    await expect(page.locator(".charlie-evidence-details").first()).toHaveAttribute("open", "");
    await expectNoHorizontalOverflow(page);
    await page.screenshot({ path: "test-results/charlie-command-center-mobile.png", fullPage: true });
  });
});
