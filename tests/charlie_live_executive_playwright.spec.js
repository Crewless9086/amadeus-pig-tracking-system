const { test, expect } = require("@playwright/test");

const dashboard = {
  success: true,
  private: { owner: { open_context: { goal: "Keep CORE moving", active_subject: { title: "Beacon mission" }, commitments: [{ type: "core_mission", mission_id: "M-1", goal: "Finish Beacon", status: "monitoring" }] } }, messages: [], decisions: [], evaluation: { tool_runs: 10, tool_successes: 10 } },
  missions: { counts: { in_progress: 1, approved: 3, pr_ready: 0, blocked: 1 } },
  executive: {}, analyst: { scorecard: { pending_proposals: 2 } },
  runner: { active: true, process_alive: true, heartbeat_fresh: true, local_runner_scope: "local_machine" },
  policy: { enabled: true, tts_enabled: false, browser_speech_fallback: true },
};

test("CHARLIE Live streams investigation and renders structured evidence", async ({ page }) => {
  await page.route("**/api/charlie/private/dashboard?**", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(dashboard) }));
  await page.route("**/api/charlie/private/message/stream", route => route.fulfill({
    status: 200,
    headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache" },
    body: [
      'event: turn_started\ndata: {"turn_id":"TURN-1"}\n\n',
      'event: intent_understood\ndata: {"intent_type":"read_core_status"}\n\n',
      'event: capability_started\ndata: {"capability":"read_core_status","domain":"engineering"}\n\n',
      'event: evidence_received\ndata: {"capability":"read_core_status","domain":"engineering","success":true}\n\n',
      'event: reply_ready\ndata: {"reply":"CORE has one active mission.","executive_packet":{"spoken_summary":"CORE has one active mission.","display_answer":"CORE has one active mission.","confidence":1,"evidence":[{"capability":"read_core_status","domain":"engineering","source":"Supabase","success":true,"summary":"One active mission."}]}}\n\n',
      'event: turn_completed\ndata: {"status":"ok"}\n\n',
    ].join(""),
  }));
  await page.goto("/charlie");
  await expect(page.getByText("Finish Beacon")).toBeVisible();
  await page.getByPlaceholder("Talk to CHARLIE...").fill("What is CORE doing?");
  await page.getByRole("button", { name: "SEND" }).click();
  await expect(page.getByText("CORE has one active mission.")).toBeVisible();
  await expect(page.getByText("One active mission.", { exact: true })).toBeVisible();
  await expect(page.getByText("100% evidence complete")).toBeVisible();
  await expect(page.locator("#presenceLabel")).toContainText("ready");
});

test("CHARLIE Live keeps the primary controls coherent on mobile", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.route("**/api/charlie/private/dashboard?**", route => route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(dashboard) }));
  await page.goto("/charlie");
  await expect(page.locator("#presence")).toBeVisible();
  await expect(page.locator("#micBtn")).toBeVisible();
  await expect(page.locator("#messageInput")).toBeVisible();
  const mic = await page.locator("#micBtn").boundingBox();
  const input = await page.locator("#messageInput").boundingBox();
  expect(mic.x + mic.width).toBeLessThanOrEqual(input.x);
});
