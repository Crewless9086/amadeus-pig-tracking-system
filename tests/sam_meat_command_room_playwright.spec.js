const { test, expect } = require("@playwright/test");
const { spawn } = require("child_process");
const http = require("http");

const BASE_URL = process.env.SAM_MEAT_PLAYWRIGHT_BASE_URL || "http://127.0.0.1:5000";
let serverProcess = null;

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
    if (await requestURL(url)) return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Timed out waiting for ${url}`);
}

async function stopServerProcess() {
  if (!serverProcess || serverProcess.killed) return;
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

const baseLead = {
  lead_id: "OSK-SALES-LEAD-PW",
  status: "interested",
  contact_label: "Playwright Buyer",
  lead_label: "Playwright Buyer - half carcass",
  chatwoot_conversation_id: "1816",
  whatsapp_window_state: "open",
  interest: {
    product: "Half carcass",
    product_type: "half_carcass",
    cut_set: "Set A",
    location: "Riversdale",
    timing: "next week",
    delivery_or_collection: "collection",
    payment_method: "EFT",
  },
  events: [],
  latest_event: null,
};

const moneyContract = {
  contract_status: "owner_money_path_ready",
  missing_fields: [],
  lead_summary: {
    buyer_or_contact: "Playwright Buyer",
    product: "Half carcass",
    cut_set: "Set A",
    location: "Riversdale",
  },
  required_before_money_path: {
    price_per_kg: "R130/kg",
    available_week: "next week",
    estimated_weight_or_size: "25kg",
    deposit_amount_or_rule: "50% deposit",
    payment_method: "EFT",
    delivery_or_collection: "collection",
    owner_final_approval: "Yes",
  },
};

const leadWithEvents = (...eventTypes) => ({
  ...baseLead,
  events: eventTypes.map((eventType, index) => ({
    event_type: eventType,
    created_at: `2026-06-27T10:0${index}:00Z`,
    notes: "{}",
    recorded_by: "Playwright",
  })),
  latest_event: eventTypes.length ? { event_type: eventTypes[eventTypes.length - 1] } : null,
});

function stateFor(key) {
  const readyLead = leadWithEvents();
  const draft = { message: "Approved draft candidate" };
  const reservation = {
    reservation_id: "RES-1",
    status: "full_carcass_committed",
    effective_status: "full_carcass_committed",
  };
  const states = {
    missing_facts: {
      lead: { ...baseLead, interest: { product_type: "unknown" }, events: [] },
      relatedState: { contract: { contract_status: "needs_owner_confirmation", missing_fields: ["product_type"] } },
    },
    owner_price_deposit_review: {
      lead: readyLead,
      relatedState: { contract: { contract_status: "needs_owner_confirmation", missing_fields: [] } },
    },
    build_draft_reply: {
      lead: readyLead,
      relatedState: { contract: moneyContract },
    },
    approve_exact_reply: {
      lead: readyLead,
      relatedState: { contract: moneyContract, draft },
    },
    ready_for_owner_send_review: {
      lead: readyLead,
      relatedState: { contract: moneyContract, draft, messageApproved: true },
    },
    wait_for_customer_yes: {
      lead: leadWithEvents("owner_customer_followup_send_approved", "customer_followup_sent"),
      relatedState: { contract: moneyContract, draft, messageApproved: true },
    },
    record_pop_evidence: {
      lead: leadWithEvents("customer_followup_sent", "customer_booking_confirmed", "draft_order_created"),
      relatedState: { contract: moneyContract, draft, messageApproved: true, meatOps: { reservations: [reservation], assembly: {}, payment_gate: { state: "deposit_not_received" } } },
    },
    confirm_money_in_bank: {
      lead: leadWithEvents("customer_followup_sent", "customer_booking_confirmed", "draft_order_created"),
      relatedState: { contract: moneyContract, draft, messageApproved: true, meatOps: { reservations: [reservation], assembly: { payment_review_status: "pop_received_unverified" }, payment_gate: { state: "pop_received_unverified" } } },
    },
    reserve_or_pair_carcass: {
      lead: leadWithEvents("customer_followup_sent", "customer_booking_confirmed"),
      relatedState: { contract: moneyContract, draft, messageApproved: true, meatOps: { reservations: [], assembly: {}, payment_gate: {} } },
    },
    create_instruction_drafts: {
      lead: leadWithEvents("customer_followup_sent", "customer_booking_confirmed", "draft_order_created"),
      relatedState: { contract: moneyContract, draft, messageApproved: true, meatOps: { reservations: [reservation], instruction_drafts: [], assembly: { deposit_confirmed: true, ready_for_instruction_drafts: true }, payment_gate: { deposit_confirmed_in_bank: true } } },
    },
    approve_external_instruction: {
      lead: leadWithEvents("customer_followup_sent", "customer_booking_confirmed", "draft_order_created"),
      relatedState: { contract: moneyContract, draft, messageApproved: true, meatOps: { reservations: [reservation], instruction_drafts: [{ instruction_draft_id: "INS-1", effective_status: "draft" }], assembly: { deposit_confirmed: true, ready_for_instruction_drafts: true }, payment_gate: { deposit_confirmed_in_bank: true } } },
    },
    record_fulfillment: {
      lead: leadWithEvents("customer_followup_sent", "customer_booking_confirmed", "draft_order_created"),
      relatedState: { contract: moneyContract, draft, messageApproved: true, meatOps: { reservations: [reservation], instruction_drafts: [{ instruction_draft_id: "INS-1", effective_status: "approved_to_send" }], assembly: { deposit_confirmed: true, ready_for_instruction_drafts: true }, payment_gate: { deposit_confirmed_in_bank: true } }, meatFulfillment: { fulfillment: { next_gate: "confirm_abattoir_slot" } } },
    },
    reconcile_final_invoice: {
      lead: leadWithEvents("customer_followup_sent", "customer_booking_confirmed", "draft_order_created"),
      relatedState: { contract: moneyContract, draft, messageApproved: true, meatOps: { reservations: [reservation], instruction_drafts: [{ instruction_draft_id: "INS-1", effective_status: "approved_to_send" }], assembly: { deposit_confirmed: true, ready_for_instruction_drafts: true }, payment_gate: { deposit_confirmed_in_bank: true } }, meatFulfillment: { fulfillment: { next_gate: "record_final_packed_weight" } }, meatReconciliation: { reconciliation: {} } },
    },
    close_or_follow_up: {
      lead: leadWithEvents("customer_followup_sent", "customer_booking_confirmed", "draft_order_created"),
      relatedState: { contract: moneyContract, draft, messageApproved: true, meatOps: { reservations: [reservation], instruction_drafts: [{ instruction_draft_id: "INS-1", effective_status: "approved_to_send" }], assembly: { deposit_confirmed: true, ready_for_instruction_drafts: true }, payment_gate: { deposit_confirmed_in_bank: true } }, meatFulfillment: { fulfillment: { next_gate: "record_final_packed_weight" } }, meatReconciliation: { reconciliation: { balance_confirmed: true } } },
    },
  };
  return states[key];
}

async function stubSamApis(page, options = {}) {
  const calls = [];
  const lead = options.lead || { ...baseLead, events: [] };
  const contract = options.contract || { ...moneyContract };
  await page.route("**/api/sales/meat-leads?**", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, sales_leads: [lead], counts: { open: 1 } }),
    });
  });
  await page.route("**/api/sales/meat-pilot-readiness**", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, percent: 35, next_gate: "owner_review", metrics: [], checklist: [], lead_stages: [] }),
    });
  });
  await page.route("**/api/sales/meat-pricing**", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, price_entries: [] }) });
  });
  await page.route("**/api/sales/meat-leads/*/contract", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, lead_id: lead.lead_id, lead, contract }),
    });
  });
  await page.route("**/api/sales/meat-leads/*/pricing-estimate", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, pricing_estimate: { estimated_total_label: "R3,250.00", recommended_owner_approval: moneyContract.required_before_money_path } }),
    });
  });
  await page.route("**/api/sales/meat-leads/*/customer-followup-draft", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ success: true, customer_followup_draft: { message: "Draft only. Please confirm review." } }),
    });
  });
  await page.route("**/api/sales/meat-leads/*/meat-match", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, meat_match: {} }) });
  });
  await page.route("**/api/sales/meat-leads/*/meat-ops", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, reservations: [], deposits: [], instruction_drafts: [], assembly: {}, payment_gate: {} }) });
  });
  await page.route("**/api/sales/meat-leads/*/fulfillment", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, fulfillment: {}, journey_plan: {}, timeline: [] }) });
  });
  await page.route("**/api/sales/meat-leads/*/reconciliation", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url() });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, reconciliation: {}, reconciliation_events: [] }) });
  });
  await page.route("**/api/sales/meat-leads/**", async (route) => {
    calls.push({ method: route.request().method(), url: route.request().url(), fallback: true });
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ success: false, status: "unexpected_test_call" }) });
  });
  await page.route("**/api/sales/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    calls.push({ method: request.method(), url: request.url(), unified: true });
    if (path === "/api/sales/meat-leads") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, sales_leads: [lead], counts: { open: 1 } }),
      });
      return;
    }
    if (path === "/api/sales/meat-pilot-readiness") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, percent: 35, next_gate: "owner_review", metrics: [], checklist: [], lead_stages: [] }),
      });
      return;
    }
    if (path === "/api/sales/meat-pricing") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, price_entries: [] }) });
      return;
    }
    if (path.endsWith("/contract")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, lead_id: lead.lead_id, lead, contract }),
      });
      return;
    }
    if (path.endsWith("/pricing-estimate")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, pricing_estimate: { estimated_total_label: "R3,250.00", recommended_owner_approval: moneyContract.required_before_money_path } }),
      });
      return;
    }
    if (path.endsWith("/customer-followup-draft")) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ success: true, customer_followup_draft: { message: "Draft only. Please confirm review." } }),
      });
      return;
    }
    if (path.endsWith("/meat-match")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, meat_match: {} }) });
      return;
    }
    if (path.endsWith("/meat-ops")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, reservations: [], deposits: [], instruction_drafts: [], assembly: {}, payment_gate: {} }) });
      return;
    }
    if (path.endsWith("/fulfillment")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, fulfillment: {}, journey_plan: {}, timeline: [] }) });
      return;
    }
    if (path.endsWith("/reconciliation")) {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ success: true, reconciliation: {}, reconciliation_events: [] }) });
      return;
    }
    await route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ success: false, status: "unexpected_test_call" }) });
  });
  return calls;
}

test.beforeAll(async () => {
  if (await requestURL(`${BASE_URL}/sales/meat-leads`)) return;
  serverProcess = spawn(".\\venv\\Scripts\\python.exe", ["app.py"], {
    cwd: process.cwd(),
    env: { ...process.env },
    stdio: "ignore",
    windowsHide: true,
  });
  await waitForServer(`${BASE_URL}/sales/meat-leads`);
});

test.afterAll(async () => {
  await stopServerProcess();
});

test("computeLeadNextAction covers command-room states without side effects", async ({ page }) => {
  await stubSamApis(page);
  await page.goto(`${BASE_URL}/sales/meat-leads`, { waitUntil: "domcontentloaded" });
  await page.locator(".sam-command-brief").waitFor();

  const keys = [
    "missing_facts",
    "owner_price_deposit_review",
    "build_draft_reply",
    "approve_exact_reply",
    "ready_for_owner_send_review",
    "wait_for_customer_yes",
    "record_pop_evidence",
    "confirm_money_in_bank",
    "reserve_or_pair_carcass",
    "create_instruction_drafts",
    "approve_external_instruction",
    "record_fulfillment",
    "reconcile_final_invoice",
    "close_or_follow_up",
  ];

  const results = await page.evaluate((fixtures) => {
    const originalFetch = window.fetch;
    let fetchCalled = false;
    window.fetch = () => {
      fetchCalled = true;
      throw new Error("computeLeadNextAction must not fetch");
    };
    try {
      return fixtures.map((fixture) => {
        const before = JSON.stringify(fixture);
        const action = window.SamMeatCommandRoom.computeLeadNextAction(fixture.lead, fixture.relatedState);
        const after = JSON.stringify(fixture);
        return {
          expected: fixture.expected,
          action,
          unchanged: before === after,
          keyCount: action && action.key ? 1 : 0,
          fetchCalled,
          forbidden: [
            "approve",
            "send",
            "reserve",
            "record payment",
            "public post",
          ].filter((word) => JSON.stringify(action).toLowerCase().includes(`${word}_called`)),
        };
      });
    } finally {
      window.fetch = originalFetch;
    }
  }, keys.map((key) => ({ ...stateFor(key), expected: key })));

  for (const result of results) {
    expect(result.action.key).toBe(result.expected);
    expect(result.keyCount).toBe(1);
    expect(result.unchanged).toBe(true);
    expect(result.fetchCalled).toBe(false);
    expect(result.forbidden).toEqual([]);
  }
});

test("SAM command room renders gates and captures screenshot", async ({ page }) => {
  await stubSamApis(page);
  await page.goto(`${BASE_URL}/sales/meat-leads`, { waitUntil: "domcontentloaded" });
  await page.locator(".meat-leads-shell").waitFor();
  await expect(page.locator("h1")).toContainText("SAM Meat Sales Command Room");
  await expect(page.locator("#meat_leads_list .meat-lead-row")).toHaveCount(1);
  await expect(page.locator(".sam-selected-command")).toBeVisible();
  await expect(page.locator(".sam-gate-stack")).toBeVisible();
  await expect(page.locator(".sam-gate-card")).toContainText([
    /Ledger Money Gate/,
    /Butcher Availability Gate/,
    /Beacon Demand Draft/,
    /Gatekeeper Approval\/Block/,
    /Supabase History/,
  ]);
  await expect(page.locator(".sam-system-workbench")).toHaveJSProperty("open", false);
  await expect(page.locator("#meat_lead_send_message")).toBeDisabled();
  await expect(page.locator("#meat_guided_next")).toContainText(/Build Draft Reply|Review Price And Deposit|Prepare Step/);
  await expect(page.locator("#meat_guided_next")).not.toContainText(/Send|Approve And Send/);
  await page.screenshot({ path: "test-results/sam-meat-command-room.png", fullPage: true });
});

test("guided next step does not chain approval or send endpoints", async ({ page }) => {
  const calls = await stubSamApis(page, {
    contract: { contract_status: "needs_owner_confirmation", missing_fields: [] },
  });
  await page.goto(`${BASE_URL}/sales/meat-leads`, { waitUntil: "domcontentloaded" });
  await page.locator(".sam-command-brief").waitFor();
  await page.locator("#meat_guided_next").click();
  await expect(page.locator("#meat_leads_message")).toContainText("Pricing estimate prepared");

  const forbiddenFragments = [
    "/owner-money-path-approval",
    "/customer-followup-send-approval",
    "/customer-followup-send",
    "/draft-order",
    "/carcass-reservations",
    "/deposit-events",
    "/beacon/facebook-post-executions",
  ];
  const forbiddenCalls = calls.filter((call) => forbiddenFragments.some((fragment) => call.url.includes(fragment)));
  expect(forbiddenCalls).toEqual([]);
  expect(calls.some((call) => call.url.includes("/pricing-estimate"))).toBe(true);
});
