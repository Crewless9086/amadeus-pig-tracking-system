const { test, expect } = require("@playwright/test");
const path = require("path");

const AGENTS = [
  "idea_expander",
  "product_architect",
  "technical_architect",
  "risk_agent",
  "council_synthesis",
  "planner",
  "architect",
  "builder",
  "tester",
  "qa_red_team",
  "product_reviewer",
  "business_reviewer",
  "security_reviewer",
  "evidence_reviewer",
  "reviewer",
  "publisher",
];

const workflow = AGENTS.map((agent, index) => ({
  agent,
  status: index < 15 ? "complete" : "pending",
  findings: `${agent} evidence captured for Playwright review.`,
}));

const reviewMission = {
  mission_id: "CHARLIE-MISSION-PLAYWRIGHT-PR-READY",
  title: "CHARLIE CORE Command Center Playwright Review",
  raw_text: "Rebuild the CHARLIE CORE command center with owner-visible truth, risks, evidence, artifacts, and actions.",
  desired_outcome: "Owner can review, approve, send back, pause, or reject from the first working viewport.",
  urgency: "P1",
  approval_level: "LEVEL 3",
  status: "pr_ready",
  mission_type: "system improvement dashboard ui",
  updated_at: "2026-07-02T23:50:00Z",
  agent_workflow: workflow,
  vault: {
    mission_stage: "owner_review",
    confidence_target: "98% before owner release review",
    acceptance_criteria: [
      "Owner review controls visible on desktop and mobile.",
      "Evidence/details panels stay readable.",
    ],
    test_plan: ["Playwright desktop and mobile checks against /charlie."],
    forbidden_actions: ["Do not merge, deploy, or commit screenshots."],
  },
  mission_context_pack: {
    active_truth_docs: [
      "docs/00-start-here/CHARLIE_MISSION_PROTOCOL.md",
      "docs/09-vault-brain/07-standards/UI_DASHBOARD_STANDARD.md",
    ],
    shared_data_rules: ["Dashboard decisions record owner review state only."],
  },
  metadata: {
    review_packet: {
      review_status: "ready_for_owner_review",
      summary: "PR-ready packet with desktop/mobile visual evidence and full council order.",
      findings: ["Owner controls remain visible.", "Workflow order includes Product Architect and Council Synthesis."],
      changed_files: ["templates/charlie.html", "static/js/charlieMissionControl.js", "static/css/main.css"],
      test_evidence: ["npx playwright test --config=playwright.charlie.config.js"],
      qa_evidence: ["QA Red Team passed first-viewport owner controls."],
      release_notes: ["Command center UI rebuilt for owner review."],
      local_preview: { url: "http://127.0.0.1:5000/charlie", status: "captured" },
      links: { pr: "https://github.com/example/amadeus/pull/83" },
      visual_review: {
        status: "captured",
        summary: "Desktop and mobile screenshots captured from local /charlie.",
        media: [],
      },
      quality_gates: [{ agent: "tester", status: "pass", summary: "Browser checks passed." }],
      handoff_reports: workflow.slice(0, 6).map((item) => ({ agent: item.agent, status: "complete", summary: item.findings })),
    },
  },
};

const blockedMission = {
  ...reviewMission,
  mission_id: "CHARLIE-MISSION-PLAYWRIGHT-BLOCKED",
  title: "Blocked Runner Evidence Packet",
  status: "blocked",
  metadata: {
    review_packet: {
      review_status: "agent_blocked",
      blocked_agent: "tester",
      blocked_reason: "Mobile owner controls were previously below the fold.",
      summary: "Blocked packet proves blocker cards tell the owner what happened and what to do next.",
      unresolved_blockers: [{
        agent: "tester",
        issue: "Owner action controls must remain visible in the first mobile working viewport.",
        next_action: "Send back to Builder after checking the evidence.",
      }],
      changed_files: ["static/css/main.css"],
      test_evidence: ["Blocked state fixture for owner review controls."],
    },
  },
};

function commandCenterPacket() {
  return {
    success: true,
    status: "ok",
    counts: { new: 1, approved: 1, in_progress: 1, blocked: 1, pr_ready: 1, merged: 0, deployed: 0 },
    charlie_core: {
      version: "charlie_core_agent_runner_v2",
      overall_target: "90%+ workflow readiness before deep income-stream missions",
      templates: ["system_improvement"],
      recent_readiness: [{
        mission_id: reviewMission.mission_id,
        title: reviewMission.title,
        status: "pr_ready",
        core_readiness: { overall_percent: 96 },
        vault_retrieval: { selected_count: 8, sources: [] },
      }],
      model_registry: { models: { default_reasoning: {} }, safety_note: "Manual routing" },
      tool_permissions: { agent_tool_allowlist: { builder: [] }, red_zone_tools: [] },
      owner_preferences: { preferences: ["Clean structure beats hidden state."] },
    },
    vault: { version: "charlie_vault_v1", storage: "metadata_json_active", health: { status: "ok", missing_tables: [] } },
    release: { waiting_final_bridge: [], in_progress: [], merged_waiting_live_verify: [], deployed: [], merged_count: 0, deployed_count: 0, verify_url_configured: false },
    queue: { approved: [], ordering: "queue.priority asc", execution_boundary: "Local runner executes builds." },
    review: { ready: [reviewMission], blocked: [blockedMission] },
    improvements: { proposals: [], pending: [], status: "ok" },
    recent_missions: [reviewMission, blockedMission],
    local_runner: { active: true, current_agent: "reviewer", current_action: "preparing owner review", agent_runner_version: "v2" },
    local_runner_scope: "local_machine",
    execution_boundary: "Dashboard records decisions and evidence. Local runner/Codex executes builds and release bridge actions.",
    autonomy_readiness: { percent: 72, safe_mode: "supervised" },
  };
}

async function stubCharlieApi(page) {
  await page.route("**/api/charlie/build-relay/**", async (route) => {
    const request = route.request();
    const url = request.url();
    const method = request.method();
    let body = { success: true, status: "ok" };

    if (url.includes("/missions/summary")) {
      body = { success: true, counts: { new: 1, approved: 1, in_progress: 1, blocked: 1, pr_ready: 1, release_approved: 0, release_in_progress: 0, merged: 0, deployed: 0 } };
    } else if (url.includes("/runner/status")) {
      body = {
        success: true,
        status: "active_mission_in_progress",
        next_action: "Reviewer is preparing owner evidence.",
        active_mission: reviewMission,
        next_approved_mission: null,
        next_release_approved_mission: null,
        local_runner: { active: true, pid: 1234, last_seen: "2026-07-02T23:51:00Z", age_seconds: 2, current_agent: "reviewer", current_action: "preparing owner review", agent_runner_version: "v2" },
        local_runner_scope: "local_machine",
      };
    } else if (url.includes("/command-center")) {
      await new Promise((resolve) => setTimeout(resolve, 600));
      body = commandCenterPacket();
    } else if (url.includes("/missions/") && url.endsWith("/review") && method === "GET") {
      body = { success: true, review_packet: reviewMission.metadata.review_packet };
    } else if (url.includes("/missions/") && url.endsWith("/review") && method === "POST") {
      body = { success: true, status: "decision_recorded" };
    } else if (url.includes("/missions")) {
      body = { success: true, missions: [reviewMission, blockedMission] };
    }

    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
}

async function expectOwnerControlsVisible(page) {
  const dock = page.locator("#charlie_owner_action_dock");
  await expect(dock).toBeVisible();
  for (const label of ["Open Review", "Refresh Evidence", "Approve Final", "Send Back", "Pause", "Reject"]) {
    const button = dock.getByRole("button", { name: label });
    await expect(button).toBeVisible();
    await expect(button).toBeEnabled();
    await button.click({ trial: true });
  }
}

test.beforeEach(async ({ page }) => {
  await stubCharlieApi(page);
});

test("desktop command center shows workflow, evidence, and owner controls", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 950 });
  await page.goto("/charlie");

  await expectOwnerControlsVisible(page);
  const agentLane = page.locator(".charlie-agent-lane");
  await expect(agentLane.getByText("Product Architect")).toBeVisible();
  await expect(agentLane.getByText("Council Synthesis")).toBeVisible();
  await expect(agentLane.getByText("Security", { exact: true })).toBeVisible();
  await expect(agentLane.getByText("Evidence", { exact: true })).toBeVisible();
  await expect(agentLane.getByText("Publisher", { exact: true })).toBeVisible();
  await expect(page.getByText("Evidence and details").first()).toBeVisible();
  await expect(page.locator(".charlie-review-list").getByText("PR-ready packet with desktop/mobile visual evidence").first()).toBeVisible();
  await expect(page.getByText("Command Center").first()).toBeVisible();

  await page.screenshot({ path: path.join("test-results", "charlie-command-center-desktop.png"), fullPage: true });
});

test("mobile keeps owner review controls in the first working viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/charlie");

  await expectOwnerControlsVisible(page);
  const rejectBox = await page.locator("#charlie_owner_action_dock").getByRole("button", { name: "Reject" }).boundingBox();
  expect(rejectBox.y + rejectBox.height).toBeLessThan(844);
  const hasHorizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(hasHorizontalOverflow).toBe(false);

  await page.screenshot({ path: path.join("test-results", "charlie-command-center-mobile.png"), fullPage: true });
});
