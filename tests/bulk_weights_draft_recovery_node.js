const assert = require("assert");
const fs = require("fs");
const vm = require("vm");

function element(overrides = {}) {
  return {
    value: "2026-06-15",
    textContent: "71",
    classList: { add() {}, remove() {} },
    addEventListener() {},
    querySelector() { return null; },
    innerHTML: "",
    selectedOptions: [],
    options: [],
    click() {},
    remove() {},
    dataset: {},
    ...overrides,
  };
}

const elements = new Map();
const fakeRows = [
  {
    dataset: { bulkPigRow: "PIG-1", pigId: "PIG-1" },
    querySelector(selector) {
      if (selector === "[data-bulk-weight]") return element({ value: "61.2" });
      if (selector === "[data-bulk-pen]") return element({ value: "" });
      if (selector === "[data-bulk-notes]") return element({ value: "" });
      return null;
    },
  },
  {
    dataset: { bulkPigRow: "PIG-2", pigId: "PIG-2" },
    querySelector(selector) {
      if (selector === "[data-bulk-weight]") return element({ value: "" });
      if (selector === "[data-bulk-pen]") return element({ value: "PEN-2" });
      if (selector === "[data-bulk-notes]") return element({ value: "moved" });
      return null;
    },
  },
];
const documentStub = {
  getElementById(id) {
    if (!elements.has(id)) elements.set(id, element());
    return elements.get(id);
  },
  querySelectorAll(selector) {
    if (selector === "[data-bulk-pig-row]") return fakeRows;
    return [];
  },
  createElement(tag) { return element({ tagName: tag }); },
  body: { appendChild() {} },
};

elements.set("bulk_weight_date", { ...element(), value: "2026-06-15" });
elements.set("bulk_visible_count", { ...element(), textContent: "71" });

const storage = new Map();
const sandbox = {
  console,
  Blob: function Blob(parts) { this.parts = parts; },
  URL: { createObjectURL() { return "blob:test"; }, revokeObjectURL() {} },
  document: documentStub,
  window: {
    localStorage: {
      get length() { return storage.size; },
      getItem(key) { return storage.get(key) || null; },
      key(index) { return [...storage.keys()][index] || null; },
      setItem(key, value) { storage.set(key, value); },
      removeItem(key) { storage.delete(key); },
    },
    clearTimeout() {},
    setTimeout(fn) { fn(); return 1; },
    confirm() { return true; },
  },
  fetch: async () => ({ ok: true, json: async () => ({}), text: async () => "{}", headers: { get() { return "application/json"; } }, status: 200 }),
  setTimeout(fn) { fn(); return 1; },
  clearTimeout() {},
};
sandbox.window.window = sandbox.window;

const source = fs.readFileSync("static/js/bulkWeights.js", "utf8");
vm.runInNewContext(source, sandbox);

async function main() {
  const helpers = sandbox.window.bulkWeightsDraftRecovery;
  assert(helpers, "draft recovery helpers should be exported for tests");

  const rows = {
    "PIG-1": { weight_kg: "61.2", moved_to_pen_id: "", condition_notes: "" },
    "PIG-2": { weight_kg: "", moved_to_pen_id: "PEN-2", condition_notes: "moved" },
    "PIG-3": { weight_kg: "", moved_to_pen_id: "", condition_notes: "" },
  };
  const draft = helpers.buildDraftPayload({ rows, weight_date: "2026-06-15", now: "2026-06-28T12:00:00.000Z", draft_id: "DRAFT-TEST" });
  assert.strictEqual(draft.draft_id, "DRAFT-TEST");
  assert.strictEqual(draft.expected_row_count, 1);
  assert.strictEqual(draft.actionable_row_count, 2);
  assert.strictEqual(draft.rows["PIG-1"].weight_kg, "61.2");

  assert.strictEqual(helpers.isCompleteUploadSuccess({ success: true, expected_count: 71, processed_count: 71, success_count: 71, failed_count: 0, blocked_count: 0 }), true);
  assert.strictEqual(helpers.isCompleteUploadSuccess({ success: false, expected_count: 71, processed_count: 71, success_count: 60, failed_count: 11 }), false);
  assert.strictEqual(helpers.isCompleteUploadSuccess({ success: true, expected_count: 71, processed_count: 60, success_count: 60, failed_count: 0 }), false);

  const message = helpers.uploadFailureMessage({ message: "Batch partial", status: "partial_failure", expected_count: 71, success_count: 60, failed_count: 11, blocked_count: 0, skipped_count: 0, failed_rows: [{ error: { message: "timeout after 60" } }] });
  assert(message.includes("Upload paused"));
  assert(message.includes("draft is saved"));
  assert(message.includes("Upload Weights"));
  assert(!message.includes("partial_failure"));

  helpers.persistDraft({ statusLabel: "Saved" });
  const draftKey = [...storage.keys()].find((key) => key.startsWith("bulkWeightsDraft:v"));
  assert(storage.has(draftKey), "Save Draft should write durable localStorage");
  const storedDraft = JSON.parse(storage.get(draftKey));
  assert.strictEqual(storedDraft.expected_row_count, 1);
  assert.strictEqual(storedDraft.actionable_row_count, 2);
  assert.strictEqual(storedDraft.rows["PIG-1"].weight_kg, "61.2");

  helpers.loadDraft();
  const recovered = helpers.buildDraftPayload({ now: "2026-06-28T12:00:00.000Z" });
  assert.strictEqual(recovered.rows["PIG-1"].weight_kg, "61.2", "reload recovery should restore saved rows");

  helpers.clearUploadedAndDuplicateDraftRows({ success: false, expected_count: 71, processed_count: 71, success_count: 60, failed_count: 11 });
  assert(storage.has(draftKey), "partial upload failure must not clear localStorage draft");

  const htmlResponse = {
    ok: false,
    status: 502,
    headers: { get(name) { return name === "content-type" ? "text/html; charset=utf-8" : ""; } },
    text: async () => "<html><body>Gateway timeout</body></html>",
  };
  const htmlData = await helpers.parseBulkJsonResponse(htmlResponse, "/api/pig-weights/weights-batch");
  assert.strictEqual(htmlData.error, "non_json_response");
  assert.strictEqual(htmlData.http_status, 502);
  assert(htmlData.message.includes("could not read"));
  assert(htmlData.message.includes("Your draft is still saved"));

  const invalidJsonResponse = {
    ok: false,
    status: 500,
    headers: { get(name) { return name === "content-type" ? "application/json" : ""; } },
    text: async () => "{not-json",
  };
  const invalidData = await helpers.parseBulkJsonResponse(invalidJsonResponse, "/api/pig-weights/weights-batch");
  assert.strictEqual(invalidData.error, "invalid_json_response");
  assert(invalidData.message.includes("unreadable response"));

  helpers.clearUploadedAndDuplicateDraftRows({ success: true, expected_count: 1, processed_count: 1, success_count: 1, failed_count: 0, blocked_count: 0 });
  assert(!storage.has(draftKey), "complete confirmed upload may clear the localStorage draft");
  helpers.renderTable({ collectExistingInputs: false });
  const clearedAfterUpload = helpers.buildDraftPayload({ now: "2026-06-28T12:01:00.000Z" });
  assert.strictEqual(clearedAfterUpload.expected_row_count, 0, "completed upload should clear stale New Weight inputs from draft state");
  assert.strictEqual(clearedAfterUpload.actionable_row_count, 0, "completed upload should clear stale New Pen and Notes inputs from draft state");

  storage.set("bulkWeightsDraft:v2026-06-15", JSON.stringify({
    ...storedDraft,
    weight_date: "2026-06-15",
    saved_at: "2026-06-28T12:00:00.000Z",
  }));
  elements.get("bulk_weight_date").value = "2026-06-28";
  helpers.loadDraft();
  assert.strictEqual(elements.get("bulk_weight_date").value, "2026-06-15", "page load should recover the latest unsent draft date");
  const recoveredPastDate = helpers.buildDraftPayload({ now: "2026-06-28T12:05:00.000Z" });
  assert.strictEqual(recoveredPastDate.rows["PIG-1"].weight_kg, "61.2", "past-date draft rows should recover after refresh");

  const imported = {
    draft_id: "DRAFT-IMPORT",
    weight_date: "2026-06-22",
    rows,
  };
  helpers.importDraftPayload(imported);
  assert.strictEqual(elements.get("bulk_weight_date").value, "2026-06-22", "import should restore the draft date");
  const importedDraft = helpers.buildDraftPayload({ now: "2026-06-28T12:10:00.000Z" });
  assert.strictEqual(importedDraft.draft_id, "DRAFT-IMPORT");
  assert.strictEqual(importedDraft.rows["PIG-2"].moved_to_pen_id, "PEN-2", "import should restore pen-change rows");

  helpers.discardCurrentDraft();
  const clearedAfterDiscard = helpers.buildDraftPayload({ now: "2026-06-28T12:11:00.000Z" });
  assert.strictEqual(clearedAfterDiscard.expected_row_count, 0, "discard draft should clear stale New Weight inputs from draft state");
  assert.strictEqual(clearedAfterDiscard.actionable_row_count, 0, "discard draft should clear stale New Pen and Notes inputs from draft state");

  assert.strictEqual(helpers.isCompleteUploadSuccess({ ok: true, status: "complete", counts: { actionable_count: 2, processed_count: 2, success_count: 2, failed_count: 0, blocked_count: 0, remaining_count: 0 } }), true);
  assert.strictEqual(helpers.isCompleteUploadSuccess({ ok: true, status: "partial", counts: { actionable_count: 2, processed_count: 1, success_count: 1, failed_count: 1, remaining_count: 0 } }), false);


  helpers.importDraftPayload({
    draft_id: "DRAFT-STAGED",
    batch_id: "BATCH-EXISTING",
    weight_date: "2026-06-22",
    rows,
  });
  const statusCalls = [];
  sandbox.fetch = async (url, options = {}) => {
    statusCalls.push({ url: String(url), method: options.method || "GET" });
    return {
      ok: true,
      status: 200,
      headers: { get(name) { return name === "content-type" ? "application/json" : ""; } },
      text: async () => JSON.stringify({
        ok: true,
        success: true,
        batch_id: "BATCH-EXISTING",
        status: "staged",
        counts: {
          visible_row_count: 116,
          actionable_row_count: 42,
          weight_row_count: 73,
          movement_row_count: 28,
          skipped_row_count: 43,
          duplicate_count: 31,
          remaining_count: 42,
          success_count: 0,
          failed_count: 0,
          blocked_count: 0,
        },
        rows: [],
      }),
      json: async () => ({}),
    };
  };
  await helpers.fetchActiveBatchStatus();
  assert(elements.get("bulk_weights_message").textContent.includes("Upload paused"));
  assert(elements.get("bulk_weights_message").textContent.includes("Upload Weights"));
  assert(!elements.get("bulk_weights_message").textContent.includes("No actionable"));

  const uploadCalls = [];
  sandbox.fetch = async (url, options = {}) => {
    uploadCalls.push({ url: String(url), method: options.method || "GET" });
    if (String(url).includes("/process")) {
      return {
        ok: true,
        status: 200,
        headers: { get(name) { return name === "content-type" ? "application/json" : ""; } },
        text: async () => JSON.stringify({
          ok: true,
          success: true,
          batch_id: "BATCH-EXISTING",
          status: "complete",
          counts: {
            visible_row_count: 116,
            actionable_row_count: 42,
            weight_row_count: 73,
            movement_row_count: 28,
            skipped_row_count: 43,
            duplicate_count: 31,
            remaining_count: 0,
            success_count: 42,
            failed_count: 0,
            blocked_count: 0,
          },
          rows: [],
        }),
        json: async () => ({}),
      };
    }
    return {
      ok: true,
      status: 200,
      headers: { get(name) { return name === "content-type" ? "application/json" : ""; } },
      text: async () => "{}",
      json: async () => String(url).includes("/pigs") ? { pigs: [] } : { pens: [] },
    };
  };
  await helpers.uploadBatch();
  assert(uploadCalls.some((call) => call.url.includes("/bulk-batches/BATCH-EXISTING/process")), "existing staged batch should process existing batch id");
  assert(!uploadCalls.some((call) => call.url.endsWith("/api/pig-weights/bulk-batches") && call.method === "POST"), "existing staged batch must not create a new batch");
  assert(elements.get("bulk_weights_message").textContent.includes("Upload complete"));

  helpers.importDraftPayload({
    draft_id: "DRAFT-STAGED-FAIL",
    batch_id: "BATCH-FAIL",
    weight_date: "2026-06-22",
    rows,
  });
  const failedCalls = [];
  sandbox.fetch = async (url, options = {}) => {
    failedCalls.push({ url: String(url), method: options.method || "GET" });
    if (String(url).includes("/process")) {
      return {
        ok: false,
        status: 500,
        headers: { get(name) { return name === "content-type" ? "text/html; charset=utf-8" : ""; } },
        text: async () => "<html>server error</html>",
        json: async () => ({}),
      };
    }
    return {
      ok: true,
      status: 200,
      headers: { get(name) { return name === "content-type" ? "application/json" : ""; } },
      text: async () => JSON.stringify({
        ok: true,
        success: true,
        batch_id: "BATCH-FAIL",
        status: "processing",
        counts: {
          visible_row_count: 116,
          actionable_row_count: 42,
          weight_row_count: 73,
          movement_row_count: 28,
          skipped_row_count: 43,
          duplicate_count: 31,
          remaining_count: 42,
          success_count: 0,
          failed_count: 0,
          blocked_count: 0,
        },
        rows: [],
      }),
      json: async () => ({}),
    };
  };
  await helpers.uploadBatch();
  assert.strictEqual(failedCalls.filter((call) => call.url.includes("/process")).length, 3, "process should retry transient non-JSON failures twice before pausing");
  assert(elements.get("bulk_weights_message").textContent.includes("Upload paused"));
  assert(elements.get("bulk_weights_message").textContent.includes("Upload Weights"));
  assert(!elements.get("bulk_weights_message").textContent.includes("non_json_response"));
  assert(!failedCalls.some((call) => call.url.endsWith("/api/pig-weights/bulk-batches") && call.method === "POST"), "failed existing batch must not restage");

  console.log("bulk weight draft recovery helpers passed");
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
