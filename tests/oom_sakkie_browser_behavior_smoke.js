const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

const source = fs.readFileSync(path.join(__dirname, "..", "static", "js", "oomSakkie.js"), "utf8");

const elements = new Map();
const fetchCalls = [];
const intervalCalls = [];
const timeoutCalls = [];
const recognitionInstances = [];
const mediaRecorderInstances = [];
let backendVoiceSttEnabled = false;

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
  if (url.includes("/voice/transcribe")) {
    return {
      success: true,
      status: "transcribed",
      text: "show me the safety gates",
      always_on_mic_enabled: false,
      stores_audio: false,
      writes: false,
      dispatch_enabled: false,
      changes_runtime_now: false,
      changes_prompt_now: false,
    };
  }
  if (url.includes("/policy")) {
    return {
      success: true,
      mode: backendVoiceSttEnabled ? "local_kiosk_read_only" : "local_kiosk_read_only",
      blocked_capabilities: [],
      backend_voice_stt: {
        enabled: backendVoiceSttEnabled,
        configured: backendVoiceSttEnabled,
        max_audio_seconds: 10,
      },
    };
  }
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
  if (url.includes("/agent-dry-run-results")) {
    return {
      success: true,
      dry_run_results: [{
        dry_run_result_id: "OSK-AGENT-DRYRUN-RESULT-SMOKE",
        dry_run_request_id: "OSK-AGENT-DRYRUN-SMOKE",
        specialist_slug: "sentinel",
        result_text: "Owner cockpit smoke result.",
        findings: ["Finding one"],
        latest_event: null,
      }],
      runs_specialist: false,
      dispatch_enabled: false,
      writes: false,
      applies_runtime_change: false,
    };
  }
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
  if (url.includes("/agent-learning/influence-proposals/from-result")) {
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
  if (url.includes("/sales-campaigns") && url.includes("/events")) return { success: true };
  if (url.includes("/sales-campaigns") && url.includes("/outreach-drafts")) {
    return {
      success: true,
      draft_id: "OSK-SALES-DRAFT-SMOKE",
      records_customer_outreach_draft: true,
      sends_customer_message: false,
      creates_order: false,
      changes_stock: false,
    };
  }
  if (url.includes("/sales-campaigns")) {
    return {
      success: true,
      sales_campaigns: [{
        campaign_id: "OSK-SALES-CAMPAIGN-SMOKE",
        campaign_title: "Ready meat preorder interest check",
        opportunity: { basis_summary: "3 ready meat candidates." },
        draft: { message: "Hi [Name], checking interest before processing." },
        latest_event: null,
        sends_customer_message: false,
        creates_order: false,
        changes_stock: false,
      }],
      sends_customer_message: false,
      creates_order: false,
      changes_stock: false,
    };
  }
  if (url.includes("/sales-outreach-drafts") && url.includes("/send-design-requests")) {
    return {
      success: true,
      send_design_id: "OSK-SALES-SEND-DESIGN-SMOKE",
      records_send_design_request: true,
      sends_customer_message: false,
      calls_chatwoot: false,
      calls_n8n: false,
      creates_order: false,
      changes_stock: false,
    };
  }
  if (url.includes("/sales-outreach-drafts")) {
    return {
      success: true,
      outreach_drafts: [{
        draft_id: "OSK-SALES-DRAFT-SMOKE",
        campaign_id: "OSK-SALES-CAMPAIGN-SMOKE",
        audience_label: "known meat buyers",
        draft_text: "Hi [Name], checking interest before processing.",
        sends_customer_message: false,
        creates_order: false,
        changes_stock: false,
      }],
      sends_customer_message: false,
      creates_order: false,
      changes_stock: false,
    };
  }
  if (url.includes("/sales-send-design-requests")) {
    return {
      success: true,
      send_design_requests: [],
      sends_customer_message: false,
      calls_chatwoot: false,
      calls_n8n: false,
      creates_order: false,
      changes_stock: false,
    };
  }
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

class FakeSpeechRecognition {
  constructor() {
    this.lang = "";
    this.interimResults = false;
    this.continuous = false;
    this.onstart = null;
    this.onerror = null;
    this.onend = null;
    this.onresult = null;
    this.started = false;
    recognitionInstances.push(this);
  }

  start() {
    this.started = true;
    if (this.onstart) this.onstart();
  }

  stop() {
    this.started = false;
    if (this.onend) this.onend();
  }

  emitTranscript(text) {
    if (this.onresult) {
      this.onresult({
        results: [[{ transcript: text }]],
      });
    }
  }

  emitEnd() {
    this.started = false;
    if (this.onend) this.onend();
  }
}

class FakeMediaRecorder {
  constructor(stream) {
    this.stream = stream;
    this.ondataavailable = null;
    this.onstop = null;
    this.started = false;
    mediaRecorderInstances.push(this);
  }

  start() {
    this.started = true;
  }

  stop() {
    this.started = false;
    if (this.ondataavailable) this.ondataavailable({ data: { size: 12, type: "audio/webm", value: "fake-audio" } });
    if (this.onstop) this.onstop();
  }
}

class FakeBlob {
  constructor(parts, options = {}) {
    this.parts = parts;
    this.type = options.type || "";
    this.size = parts.length;
  }
}

class FakeFormData {
  constructor() {
    this.items = [];
  }

  append(name, value, filename) {
    this.items.push({ name, value, filename });
  }
}

const window = {
  SpeechRecognition: null,
  webkitSpeechRecognition: FakeSpeechRecognition,
  MediaRecorder: FakeMediaRecorder,
  Blob: FakeBlob,
  FormData: FakeFormData,
  speechSynthesis: null,
  isSecureContext: true,
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
    mediaDevices: {
      getUserMedia: async () => ({
        getTracks: () => [{
          stop: () => {},
        }],
      }),
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

function findByText(root, text) {
  if (!root) return null;
  if (root.textContent === text) return root;
  for (const child of root.children || []) {
    const match = findByText(child, text);
    if (match) return match;
  }
  return null;
}

async function flushPromises() {
  await Promise.resolve();
  await Promise.resolve();
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
  const acceptButton = findByText(element("oom_owner_primary_decision"), "Accept For Learning");
  assert(acceptButton, "Owner cockpit should expose one clear Accept For Learning action");
  await acceptButton.trigger("click");
  await flushPromises();
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url.includes("/api/oom-sakkie/agent-dry-run-results/OSK-AGENT-DRYRUN-RESULT-SMOKE/events")),
    "Owner cockpit Accept For Learning must POST only after owner click",
  );
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url === "/api/oom-sakkie/agent-learning/influence-proposals/from-result"),
    "Owner cockpit Accept For Learning should prepare a proposal only for the clicked result",
  );
  const fromResultCall = fetchCalls.find((call) =>
    call.method === "POST" && call.url === "/api/oom-sakkie/agent-learning/influence-proposals/from-result"
  );
  assert.deepStrictEqual(
    JSON.parse(fromResultCall.options.body),
    { source_result_id: "OSK-AGENT-DRYRUN-RESULT-SMOKE" },
    "Owner cockpit proposal preparation must send the clicked result id only",
  );
  assert.strictEqual(intervalCalls.length, 0, "Owner cockpit evidence decision click must not start interval polling");

  fetchCalls.length = 0;
  await element("oom_prepare_learning_influence").trigger("click");
  await flushPromises();
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url === "/api/oom-sakkie/agent-learning/influence-proposals/from-accepted"),
    "Learning influence proposal preparation must POST only after owner click",
  );
  assert.strictEqual(intervalCalls.length, 0, "Learning influence proposal preparation click must not start interval polling");

  fetchCalls.length = 0;
  await element("oom_approve_first_sales_campaign").trigger("click");
  await flushPromises();
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url.includes("/api/oom-sakkie/sales-campaigns/OSK-SALES-CAMPAIGN-SMOKE/events")),
    "Sales campaign approval must POST only after owner click",
  );
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url.includes("/api/oom-sakkie/sales-campaigns/OSK-SALES-CAMPAIGN-SMOKE/outreach-drafts")),
    "Sales campaign approval should queue an internal outreach draft only after owner click",
  );
  assert.strictEqual(intervalCalls.length, 0, "Sales campaign approval click must not start interval polling");

  fetchCalls.length = 0;
  const sendDesignButton = findByText(element("oom_sales_outreach_drafts"), "Prepare Send Design");
  assert(sendDesignButton, "Ledger workbench should expose an explicit Prepare Send Design action");
  await sendDesignButton.trigger("click");
  await flushPromises();
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url.includes("/api/oom-sakkie/sales-outreach-drafts/OSK-SALES-DRAFT-SMOKE/send-design-requests")),
    "Sales send-design request must POST only after owner click",
  );
  assert.strictEqual(intervalCalls.length, 0, "Sales send-design click must not start interval polling");

  fetchCalls.length = 0;
  await element("oom_voice_button").trigger("click");
  await flushPromises();
  assert.strictEqual(recognitionInstances.length, 1, "Talk should create one browser speech recognition instance");
  recognitionInstances[0].emitTranscript("show me the safety gates");
  recognitionInstances[0].emitEnd();
  await flushPromises();
  assert.strictEqual(element("oom_text").value, "show me the safety gates", "Talk should copy recognized speech into the input box");
  assert.strictEqual(element("oom_user_text").textContent, "show me the safety gates", "Talk should show the recognized draft");
  assert.deepStrictEqual(fetchCalls, [], "Talk draft capture must not POST until the owner sends it");

  fetchCalls.length = 0;
  timeoutCalls.length = 0;
  await element("oom_voice_ask_button").trigger("click");
  await flushPromises();
  recognitionInstances[0].emitTranscript("what needs my approval");
  recognitionInstances[0].emitEnd();
  await flushPromises();
  assert.strictEqual(timeoutCalls.length, 1, "Talk & Ask should schedule the explicit short auto-send window after capture");
  assert.strictEqual(timeoutCalls[0].ms, 2000, "Talk & Ask auto-send window should remain two seconds");
  await timeoutCalls[0].handler();
  await flushPromises();
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url === "/api/oom-sakkie/message"),
    "Talk & Ask should POST the captured text only after browser recognition returns text and the auto-send timer fires",
  );
  assert.strictEqual(intervalCalls.length, 0, "voice capture must not start interval polling");

  fetchCalls.length = 0;
  timeoutCalls.length = 0;
  backendVoiceSttEnabled = true;
  await element("oom_refresh_policy").trigger("click");
  await flushPromises();
  await element("oom_voice_button").trigger("click");
  await flushPromises();
  assert.strictEqual(mediaRecorderInstances.length, 1, "Talk should prefer backend STT fallback when configured");
  mediaRecorderInstances[0].stop();
  await flushPromises();
  await flushPromises();
  assert(
    fetchCalls.some((call) => call.method === "POST" && call.url === "/api/oom-sakkie/voice/transcribe"),
    "backend STT fallback should POST audio only after the owner clicks Talk",
  );
  assert.strictEqual(element("oom_text").value, "show me the safety gates", "backend STT should copy transcribed text into the input box");
  assert.strictEqual(intervalCalls.length, 0, "backend STT fallback must not start interval polling");

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
