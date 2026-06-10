const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "js", "oomSakkie.js"), "utf8");

const elements = new Map();
const fetchCalls = [];
const intervalCalls = [];
const timeoutCalls = [];

class FakeElement {
  constructor(id = "") {
    this.id = id;
    this.children = [];
    this.dataset = {};
    this.listeners = {};
    this.style = {};
    this.classList = {
      add: () => {},
      remove: () => {},
      toggle: () => {},
    };
    this.value = "";
    this.textContent = "";
    this.innerHTML = "";
    this.hidden = false;
    this.disabled = false;
    this.checked = false;
    this.className = "";
    this.href = "";
    this.target = "";
    this.rel = "";
    this.type = "";
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }

  prepend(child) {
    this.children.unshift(child);
    return child;
  }

  remove() {}

  focus() {}

  select() {}

  addEventListener(type, handler) {
    if (!this.listeners[type]) this.listeners[type] = [];
    this.listeners[type].push(handler);
  }

  async trigger(type, event = {}) {
    const handlers = this.listeners[type] || [];
    for (const handler of handlers) {
      await handler({
        preventDefault: () => {},
        target: this,
        ...event,
      });
    }
  }

  setAttribute(name, value) {
    this[name] = value;
  }

  getAttribute(name) {
    return this[name];
  }
}

function element(id) {
  if (!elements.has(id)) elements.set(id, new FakeElement(id));
  return elements.get(id);
}

function responseFor(url, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  if (url.includes("/message")) {
    return {
      success: true,
      answer: "Read-only answer.",
      tool_used: "farm_attention_summary",
      trace_id: "OSK-TRACE-SMOKE",
      risk_level: 0,
      stale_warnings: [],
      safety_notes: ["Smoke read-only."],
      links: [],
      pipeline: {},
      agent_activity: {},
    };
  }
  if (url.includes("/tools")) return { success: true, tools: [] };
  if (url.includes("/policy")) return { success: true, mode: "local_kiosk_read_only", blocked_capabilities: [] };
  if (url.includes("/agents/activation-plan")) return { success: true, candidates: [], accepted_learning_summary: [] };
  if (url.endsWith("/api/oom-sakkie/agents") || url.includes("/agents")) return { success: true, agents: [] };
  if (url.includes("/agent-dry-runs/handoff")) return { success: true, prompt: "Prompt only.", no_go_rules: [] };
  if (url.includes("/agent-dry-runs") && url.includes("/results")) {
    return { success: true, dry_run_result_id: "OSK-AGENT-DRYRUN-RESULT-SMOKE" };
  }
  if (url.includes("/agent-dry-runs") && method === "POST") {
    return { success: true, dry_run_request_id: "OSK-AGENT-DRYRUN-SMOKE", specialist_slug: "sentinel" };
  }
  if (url.includes("/agent-dry-runs")) return { success: true, dry_runs: [] };
  if (url.includes("/agent-dry-run-results") && url.includes("/review-packet")) {
    return { success: true, result_text: "Packet only.", findings: [], owner_options: [] };
  }
  if (url.includes("/agent-dry-run-results") && url.includes("/events")) return { success: true };
  if (url.includes("/agent-dry-run-results")) return { success: true, results: [] };
  if (url.includes("/traces/review-summary")) return { success: true, summary: {} };
  if (url.includes("/traces/") && url.includes("/feedback")) return { success: true };
  if (url.includes("/traces")) return { success: true, traces: [] };
  if (url.includes("/agent-learning/influence-proposals/from-accepted")) {
    return {
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
  }
  if (url.includes("/agent-learning/influence-proposals") && url.includes("/events")) return { success: true };
  if (url.includes("/agent-learning/influence-proposals")) {
    return {
      success: true,
      mode: "learning_influence_proposal_queue",
      learning_influence_proposals: [],
      applies_learning_now: false,
      changes_prompt_now: false,
      changes_runtime_now: false,
      dispatch_enabled: false,
      writes: false,
    };
  }
  if (url.includes("/review-advisor")) return { success: true, mode: "advisory_only", suggestions: [], issue_traces: [], unreviewed_traces: [] };
  if (url.includes("/learning-advisor/analyze")) return { success: true, queue: [], suggestions: [] };
  if (url.includes("/learning-advisor/build-packet")) return { success: true, packet: {} };
  if (url.includes("/learning-advisor/approve-build")) return { success: true, build_request_id: "OSK-BUILD-SMOKE" };
  if (url.includes("/learning-advisor/implementation-queue")) return { success: true, queue: [] };
  if (url.includes("/learning-advisor")) return { success: true, queue: [], suggestions: [] };
  if (url.includes("/build-requests/forge-handoff")) return { success: true, prompt: "Forge prompt only." };
  if (url.includes("/build-requests") && url.includes("/events")) return { success: true };
  if (url.includes("/build-requests") && url.includes("/patch-proposals")) return { success: true, patch_proposal_id: "OSK-PATCH-SMOKE" };
  if (url.includes("/build-requests")) return { success: true, build_requests: [] };
  if (url.includes("/patch-proposals") && url.includes("/deploy-decisions")) return { success: true, deploy_decision_id: "OSK-DEPLOY-SMOKE" };
  if (url.includes("/patch-proposals") && url.includes("/events")) return { success: true };
  if (url.includes("/patch-proposals")) return { success: true, patch_proposals: [] };
  if (url.includes("/deploy-decisions")) return { success: true, deploy_decisions: [] };
  return { success: true };
}

function makeButton(id, dataset = {}) {
  const button = element(id);
  button.dataset = { ...dataset };
  return button;
}

const quickAskButton = makeButton("quick_ask_smoke", { quickAsk: "What needs attention today?" });
const reviewFilterButton = makeButton("review_filter_smoke", { reviewFilter: "all" });

const document = {
  getElementById: element,
  createElement: (tagName) => {
    const created = new FakeElement();
    created.tagName = tagName.toUpperCase();
    return created;
  },
  createTextNode: (text) => ({ textContent: text }),
  querySelectorAll: (selector) => {
    if (selector === "[data-quick-ask]") return [quickAskButton];
    if (selector === "[data-review-filter]") return [reviewFilterButton];
    return [];
  },
};

const window = {
  SpeechRecognition: null,
  webkitSpeechRecognition: null,
  speechSynthesis: null,
  localStorage: {
    _values: new Map(),
    getItem(key) {
      return this._values.get(key) || null;
    },
    setItem(key, value) {
      this._values.set(key, String(value));
    },
  },
  setTimeout: (handler, ms) => {
    timeoutCalls.push({ handler, ms });
    return timeoutCalls.length;
  },
  clearTimeout: () => {},
  setInterval: (handler, ms) => {
    intervalCalls.push({ handler, ms });
    return intervalCalls.length;
  },
  clearInterval: () => {},
};

const sandbox = {
  document,
  window,
  navigator: {
    clipboard: {
      writeText: async () => {},
    },
  },
  console,
  fetch: async (url, options = {}) => {
    fetchCalls.push({ url: String(url), method: (options.method || "GET").toUpperCase(), options });
    return {
      ok: true,
      status: 200,
      json: async () => responseFor(String(url), options),
    };
  },
  encodeURIComponent,
};

window.document = document;
window.navigator = sandbox.navigator;
window.fetch = sandbox.fetch;

function startupPostCalls() {
  return fetchCalls.filter((call) => call.method !== "GET");
}

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
}

(async () => {
  vm.runInNewContext(source, sandbox, { filename: "oomSakkie.js" });
  await flushPromises();

  assert.strictEqual(intervalCalls.length, 0, "kiosk startup must not create background polling intervals");
  assert.deepStrictEqual(startupPostCalls(), [], "kiosk startup must not perform hidden POST requests");
  assert(fetchCalls.some((call) => call.url.includes("/api/oom-sakkie/tools")), "startup should load read-only tool catalog");

  fetchCalls.length = 0;
  await element("oom_request_sentinel_dry_run").trigger("click");
  await flushPromises();
  assert(fetchCalls.some((call) => call.method === "POST" && call.url === "/api/oom-sakkie/agent-dry-runs"), "Sentinel dry-run request must POST only after owner click");
  assert.strictEqual(intervalCalls.length, 0, "Sentinel dry-run request click must not start interval polling");

  fetchCalls.length = 0;
  element("oom_agent_dry_run_result_request_id").value = "OSK-AGENT-DRYRUN-SMOKE";
  element("oom_agent_dry_run_result_text").value = "Smoke result text.";
  element("oom_agent_dry_run_result_findings").value = "Finding one\nFinding two";
  await element("oom_record_agent_dry_run_result").trigger("click");
  await flushPromises();
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url.includes("/api/oom-sakkie/agent-dry-runs/OSK-AGENT-DRYRUN-SMOKE/results")),
    "Agent dry-run result recording must POST only after owner click",
  );
  assert.strictEqual(intervalCalls.length, 0, "Agent dry-run result recording click must not start interval polling");

  fetchCalls.length = 0;
  await element("oom_prepare_learning_influence").trigger("click");
  await flushPromises();
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url === "/api/oom-sakkie/agent-learning/influence-proposals/from-accepted"),
    "Learning influence proposal preparation must POST only after owner click",
  );
  assert.strictEqual(intervalCalls.length, 0, "Learning influence proposal preparation click must not start interval polling");

  fetchCalls.length = 0;
  await quickAskButton.trigger("click");
  await flushPromises();
  assert(fetchCalls.some((call) => call.method === "POST" && call.url === "/api/oom-sakkie/message"), "quick ask should POST a single owner-triggered message");
  assert.strictEqual(intervalCalls.length, 0, "quick ask click must not start interval polling");

  console.log("Oom Sakkie browser behavior smoke passed");
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
