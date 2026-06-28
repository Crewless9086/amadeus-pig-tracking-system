const bulkDateInput = document.getElementById("bulk_weight_date");
const penFilterSelect = document.getElementById("bulk_pen_filter");
const clearPensButton = document.getElementById("bulk_clear_pens_button");
const saveDraftButton = document.getElementById("bulk_save_draft_button");
const uploadButton = document.getElementById("bulk_upload_button");
const messageBox = document.getElementById("bulk_weights_message");
const bulkWeightBody = document.getElementById("bulk_weight_body");
const visibleCount = document.getElementById("bulk_visible_count");
const enteredCount = document.getElementById("bulk_entered_count");
const draftStatus = document.getElementById("bulk_draft_status");
const reviewPanel = document.getElementById("bulk_review_panel");
const recoveryBanner = document.getElementById("bulk_recovery_banner");
const recoverySummary = document.getElementById("bulk_recovery_summary");
const restoreDraftButton = document.getElementById("bulk_restore_draft_button");
const discardDraftButton = document.getElementById("bulk_discard_draft_button");
const downloadDraftButton = document.getElementById("bulk_download_draft_button");
const importDraftButton = document.getElementById("bulk_import_draft_button");
const importDraftInput = document.getElementById("bulk_import_draft_input");
const continueButton = document.getElementById("bulk_continue_button");

const DRAFT_VERSION = 2;
let allPigs = [];
let allPens = [];
let draftRows = {};
let activeDraftId = "";
let activeBatchId = "";
let autosaveTimer = null;
let recoveredDraftPayload = null;

function todayIso() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0");
  const dd = String(today.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatTagNumber(value) {
  const raw = String(value || "").trim();
  return /^\d+$/.test(raw) ? raw.padStart(3, "0") : raw;
}

function tagSortKey(pig) {
  const raw = String(pig.tag_number || pig.pig_id || "").trim();
  const numeric = /^\d+$/.test(raw) ? raw.padStart(8, "0") : raw.toLowerCase();
  return `${numeric}|${String(pig.tag_number || pig.pig_id || "").toLowerCase()}|${pig.pig_id || ""}`;
}

function penLabelForPig(pig) {
  return pig.current_pen_name || pig.current_pen_id || "-";
}

function penSortKey(pig) {
  return String(penLabelForPig(pig)).toLowerCase();
}

function formatKg(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(2)} kg`;
}

function setMessage(message, type = "error") {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add(type === "success" ? "message-success" : "message-error");
  messageBox.textContent = message;
}

function clearMessage() {
  messageBox.classList.add("hidden");
  messageBox.textContent = "";
  messageBox.classList.remove("message-success", "message-error");
}

function draftKey() {
  return `bulkWeightsDraft:v${DRAFT_VERSION}:${bulkDateInput.value || "no-date"}`;
}

function legacyDraftKey() {
  return `bulkWeightsDraft:v1:${bulkDateInput.value || "no-date"}`;
}

function readStoredDraft(key) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch (error) {
    console.error("bulk draft read error:", error);
    return null;
  }
}

function findLatestStoredDraft() {
  const drafts = [];
  for (let index = 0; index < window.localStorage.length; index += 1) {
    const key = window.localStorage.key(index);
    if (!key || !key.startsWith("bulkWeightsDraft:v")) continue;
    const payload = readStoredDraft(key);
    if (payload && payload.rows) drafts.push({ key, payload });
  }
  drafts.sort((a, b) => String(b.payload.saved_at || "").localeCompare(String(a.payload.saved_at || "")));
  return drafts[0] || null;
}

function createDraftId() {
  return `BULK-DRAFT-${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
}

function draftRowValues() {
  return Object.values(draftRows || {});
}

function actionableDraftRows() {
  return draftRowValues().filter((row) =>
    String(row.weight_kg || "").trim() !== "" ||
    String(row.moved_to_pen_id || "").trim() !== "" ||
    String(row.condition_notes || "").trim() !== ""
  );
}

function enteredWeightCount() {
  return draftRowValues().filter((row) => String(row.weight_kg || "").trim() !== "").length;
}

function buildDraftPayload(options = {}) {
  const now = options.now || new Date().toISOString();
  const rows = options.rows || draftRows || {};
  const rowValues = Object.values(rows);
  const enteredRows = rowValues.filter((row) => String(row.weight_kg || "").trim() !== "");
  const actionableRows = rowValues.filter((row) =>
    String(row.weight_kg || "").trim() !== "" ||
    String(row.moved_to_pen_id || "").trim() !== "" ||
    String(row.condition_notes || "").trim() !== ""
  );
  return {
    draft_id: options.draft_id || activeDraftId || createDraftId(),
    version: DRAFT_VERSION,
    saved_at: now,
    weight_date: options.weight_date || bulkDateInput.value,
    expected_row_count: enteredRows.length,
    actionable_row_count: actionableRows.length,
    visible_row_count: Number(visibleCount.textContent || 0) || filteredRows().length || allPigs.length,
    selected_pen_ids: selectedPenIds(),
    source: "browser_local_draft",
    validation_status: options.validation_status || "not_preflighted",
    rows,
  };
}

function writeDraftPayload(payload) {
  activeDraftId = payload.draft_id || activeDraftId || createDraftId();
  const finalPayload = { ...payload, draft_id: activeDraftId };
  window.localStorage.setItem(draftKey(), JSON.stringify(finalPayload));
  return finalPayload;
}

function persistDraft(options = {}) {
  collectDraftFromDom();
  const payload = writeDraftPayload(buildDraftPayload(options));
  draftStatus.textContent = options.statusLabel || "Saved";
  return payload;
}

function scheduleAutosave() {
  window.clearTimeout(autosaveTimer);
  autosaveTimer = window.setTimeout(() => {
    try {
      persistDraft({ statusLabel: "Autosaved" });
    } catch (error) {
      console.error("bulk draft autosave error:", error);
      draftStatus.textContent = "Draft save error";
    }
  }, 250);
}

function draftSavedLabel(payload) {
  if (!payload || !payload.saved_at) return "unknown time";
  try {
    return new Date(payload.saved_at).toLocaleString();
  } catch (error) {
    return payload.saved_at;
  }
}

function showRecoveryBanner(payload) {
  if (!recoveryBanner || !recoverySummary || !payload) return;
  recoveredDraftPayload = payload;
  recoverySummary.textContent = `Recovered unsent bulk weight draft from ${draftSavedLabel(payload)} with ${Number(payload.expected_row_count || 0)} entered weight row${Number(payload.expected_row_count || 0) === 1 ? "" : "s"}.`;
  recoveryBanner.classList.remove("hidden");
}

function hideRecoveryBanner() {
  if (recoveryBanner) recoveryBanner.classList.add("hidden");
  recoveredDraftPayload = null;
}

function isCompleteUploadSuccess(data) {
  if (!data || (!data.success && !data.ok)) return false;
  const status = String(data.status || "").toLowerCase();
  const counts = data.counts || data;
  const expected = Number(counts.expected_count || counts.accepted_count || counts.actionable_count || 0);
  const processed = Number(counts.processed_count || counts.success_count || 0);
  const successCount = Number(counts.success_count || counts.saved_count || 0);
  const failed = Number(counts.failed_count || 0);
  const blocked = Number(counts.blocked_count || 0);
  const remaining = Number(counts.remaining_count || 0);
  if (failed || blocked || remaining) return false;
  if (status && status !== "complete" && status !== "uploaded") return false;
  if (expected && processed !== expected) return false;
  if (expected && successCount !== expected) return false;
  return true;
}

function uploadFailureMessage(data, fallback = "Upload failed before completion.") {
  if (!data || typeof data !== "object") return fallback;
  const parts = [];
  if (data.message) parts.push(data.message);
  if (data.status) parts.push(`Status: ${data.status}.`);
  const counts = data.counts || data;
  const expected = Number(counts.expected_count || counts.accepted_count || counts.actionable_count || 0);
  const successCount = Number(counts.success_count || counts.saved_count || 0);
  const failed = Number(counts.failed_count || 0);
  const blocked = Number(counts.blocked_count || 0);
  const skipped = Number(counts.skipped_count || 0);
  if (expected || successCount || failed || blocked || skipped) {
    parts.push(`Expected ${expected}, succeeded ${successCount}, failed ${failed}, blocked ${blocked}, skipped ${skipped}. Draft kept for recovery/retry.`);
  }
  const firstFailed = Array.isArray(data.failed_rows) ? data.failed_rows[0] : null;
  const firstError = firstFailed && firstFailed.error ? (firstFailed.error.message || firstFailed.error.status) : "";
  if (firstError) parts.push(`First failed row: ${firstError}.`);
  return parts.join(" ") || fallback;
}

function draftCountsForFailure() {
  const rows = rowsPayload();
  const fallbackRows = Object.values(draftRows || {}).map((row) => ({
    weight_kg: row.weight_kg || "",
    moved_to_pen_id: row.moved_to_pen_id || "",
    condition_notes: row.condition_notes || "",
  }));
  const countRows = rows.length ? rows : fallbackRows;
  const submittedCount = rows.length || Number(visibleCount.textContent || 0) || fallbackRows.length;
  const actionableCount = countRows.filter((row) =>
    String(row.weight_kg || "").trim() !== "" ||
    String(row.moved_to_pen_id || "").trim() !== "" ||
    String(row.condition_notes || "").trim() !== ""
  ).length;
  return { rows, submittedCount, actionableCount };
}

async function parseBulkJsonResponse(response, endpoint) {
  const contentType = response.headers?.get ? response.headers.get("content-type") || "" : "";
  const text = await response.text();
  if (!contentType.toLowerCase().includes("application/json")) {
    const counts = draftCountsForFailure();
    return {
      ok: false,
      success: false,
      error: "non_json_response",
      status: "non_json_response",
      endpoint,
      http_status: response.status,
      content_type: contentType || "unknown",
      message: `Server returned non-JSON response from ${endpoint} (HTTP ${response.status}). Your draft is still saved.`,
      submitted_count: counts.submittedCount,
      visible_count: counts.submittedCount,
      expected_count: counts.actionableCount,
      processed_count: 0,
      success_count: 0,
      saved_count: 0,
      movement_count: 0,
      skipped_count: Math.max(counts.submittedCount - counts.actionableCount, 0),
      blocked_count: 0,
      failed_count: 0,
      row_results: [],
      response_preview: text.slice(0, 120),
      batch_id: activeBatchId || "",
    };
  }
  try {
    return JSON.parse(text || "{}");
  } catch (error) {
    const counts = draftCountsForFailure();
    return {
      ok: false,
      success: false,
      error: "invalid_json_response",
      status: "invalid_json_response",
      endpoint,
      http_status: response.status,
      content_type: contentType,
      message: `Server returned invalid JSON from ${endpoint} (HTTP ${response.status}). Your draft is still saved.`,
      submitted_count: counts.submittedCount,
      visible_count: counts.submittedCount,
      expected_count: counts.actionableCount,
      processed_count: 0,
      success_count: 0,
      saved_count: 0,
      movement_count: 0,
      skipped_count: Math.max(counts.submittedCount - counts.actionableCount, 0),
      blocked_count: 0,
      failed_count: 0,
      row_results: [],
      response_preview: text.slice(0, 120),
      batch_id: activeBatchId || "",
    };
  }
}

function downloadTextFile(filename, text) {
  const blob = new Blob([text], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function selectedPenIds() {
  return Array.from(penFilterSelect.selectedOptions).map((option) => option.value).filter(Boolean);
}

function penOptionsHtml(selectedPenId) {
  const options = ['<option value="">No pen change</option>'];
  allPens.forEach((pen) => {
    const label = pen.pen_name ? `${pen.pen_name} (${pen.pen_id})` : (pen.pen_id || "");
    options.push(`<option value="${escapeHtml(pen.pen_id || "")}" ${selectedPenId === pen.pen_id ? "selected" : ""}>${escapeHtml(label)}</option>`);
  });
  return options.join("");
}

function populatePens() {
  penFilterSelect.innerHTML = "";
  allPens.forEach((pen) => {
    const option = document.createElement("option");
    option.value = pen.pen_id || "";
    option.textContent = pen.pen_name ? `${pen.pen_name} (${pen.pen_id})` : (pen.pen_id || "");
    penFilterSelect.appendChild(option);
  });
}

function filteredRows() {
  const pens = selectedPenIds();
  const rows = pens.length
    ? allPigs.filter((pig) => pens.includes(pig.current_pen_id || ""))
    : [...allPigs];

  return rows.sort((a, b) => {
    const penCompare = penSortKey(a).localeCompare(penSortKey(b));
    if (penCompare !== 0) return penCompare;
    return tagSortKey(a).localeCompare(tagSortKey(b));
  });
}

function collectDraftFromDom() {
  document.querySelectorAll("[data-bulk-pig-row]").forEach((row) => {
    const pigId = row.dataset.pigId || "";
    if (!pigId) return;
    draftRows[pigId] = {
      weight_kg: row.querySelector("[data-bulk-weight]")?.value || "",
      moved_to_pen_id: row.querySelector("[data-bulk-pen]")?.value || "",
      condition_notes: row.querySelector("[data-bulk-notes]")?.value || "",
    };
  });
}

function countEnteredRows() {
  collectDraftFromDom();
  return enteredWeightCount();
}

function updateSummary() {
  visibleCount.textContent = String(filteredRows().length);
  enteredCount.textContent = String(countEnteredRows());
}

function renderTable() {
  clearMessage();
  reviewPanel.classList.add("hidden");
  collectDraftFromDom();
  const rows = filteredRows();
  visibleCount.textContent = String(rows.length);

  if (!rows.length) {
    bulkWeightBody.innerHTML = `<tr><td colspan="7" class="table-empty">No active pigs found for this selection.</td></tr>`;
    updateSummary();
    return;
  }

  bulkWeightBody.innerHTML = rows.map((pig) => {
    const draft = draftRows[pig.pig_id] || {};
    return `
      <tr data-bulk-pig-row data-pig-id="${escapeHtml(pig.pig_id || "")}">
        <td>${escapeHtml(formatTagNumber(pig.tag_number || pig.pig_id || "-"))}</td>
        <td>${escapeHtml(pig.last_weight_date || "-")}</td>
        <td>${escapeHtml(formatKg(pig.current_weight_kg))}</td>
        <td>
          <input data-bulk-weight type="number" step="0.01" inputmode="decimal" class="bulk-weight-input no-spinner" value="${escapeHtml(draft.weight_kg || "")}" />
        </td>
        <td>${escapeHtml(penLabelForPig(pig))}</td>
        <td>
          <select data-bulk-pen class="bulk-pen-select">${penOptionsHtml(draft.moved_to_pen_id || "")}</select>
        </td>
        <td>
          <input data-bulk-notes type="text" class="bulk-notes-input" value="${escapeHtml(draft.condition_notes || "")}" />
        </td>
      </tr>
    `;
  }).join("");

  document.querySelectorAll("[data-bulk-weight], [data-bulk-pen], [data-bulk-notes]").forEach((input) => {
    input.addEventListener("input", () => {
      updateSummary();
      scheduleAutosave();
    });
    input.addEventListener("change", () => {
      updateSummary();
      scheduleAutosave();
    });
  });
  document.querySelectorAll("[data-bulk-weight]").forEach((input) => {
    input.addEventListener("wheel", (event) => {
      event.preventDefault();
    }, { passive: false });
  });
  updateSummary();
}

function loadDraft(options = {}) {
  try {
    let payload = readStoredDraft(draftKey()) || readStoredDraft(legacyDraftKey());
    if (!payload && options.allowLatestFallback !== false) {
      const latest = findLatestStoredDraft();
      payload = latest ? latest.payload : null;
      if (payload && payload.weight_date) bulkDateInput.value = payload.weight_date;
    }
    draftRows = payload ? payload.rows || {} : {};
    activeDraftId = payload ? payload.draft_id || createDraftId() : createDraftId();
    draftStatus.textContent = payload ? "Recovered" : "Not saved";
    if (payload && actionableDraftRows().length) showRecoveryBanner({ ...payload, draft_id: activeDraftId });
  } catch (error) {
    console.error("load bulk draft error:", error);
    draftRows = {};
    activeDraftId = createDraftId();
    draftStatus.textContent = "Draft error";
  }
}

function saveDraft() {
  const payload = persistDraft({ statusLabel: "Saved" });
  setMessage(`Draft saved on this device. ${payload.expected_row_count} entered weight row${payload.expected_row_count === 1 ? "" : "s"} are recoverable after refresh.`, "success");
  updateSummary();
  showRecoveryBanner(payload);
}

function rowsPayload() {
  collectDraftFromDom();
  return allPigs.map((pig) => {
    const draft = draftRows[pig.pig_id] || {};
    return {
      pig_id: pig.pig_id,
      tag_number: pig.tag_number,
      weight_kg: draft.weight_kg || "",
      moved_to_pen_id: draft.moved_to_pen_id || "",
      condition_notes: draft.condition_notes || "",
    };
  });
}

function importDraftPayload(payload) {
  if (!payload || typeof payload !== "object" || !payload.rows || typeof payload.rows !== "object") {
    throw new Error("Imported file is not a bulk weight draft JSON file.");
  }
  if (payload.weight_date) bulkDateInput.value = payload.weight_date;
  draftRows = payload.rows || {};
  activeDraftId = payload.draft_id || createDraftId();
  activeBatchId = payload.batch_id || "";
  writeDraftPayload(buildDraftPayload({ draft_id: activeDraftId, validation_status: "imported" }));
  renderTable();
  showRecoveryBanner(buildDraftPayload({ draft_id: activeDraftId, validation_status: "imported" }));
  setMessage(`Imported draft restored with ${actionableDraftRows().length} actionable row${actionableDraftRows().length === 1 ? "" : "s"}. Review before staging.`, "success");
}

function clearUploadedAndDuplicateDraftRows(uploadData) {
  if (!isCompleteUploadSuccess(uploadData)) {
    persistDraft({ statusLabel: "Upload failed - draft kept", validation_status: "upload_incomplete" });
    return false;
  }
  window.localStorage.removeItem(draftKey());
  window.localStorage.removeItem(legacyDraftKey());
  draftRows = {};
  activeDraftId = createDraftId();
  draftStatus.textContent = "Uploaded";
  hideRecoveryBanner();
  return true;
}

function renderReview(data) {
  const counts = data.counts || data || {};
  const blockedRows = data.blocked_rows || [];
  const failedRows = data.failed_rows || [];
  const rowResults = data.row_results || data.rows || [];
  const acceptedRows = data.accepted_rows || [];
  const movementRows = acceptedRows.filter((row) => row.action_type === "movement_only");
  const duplicateMovementRows = acceptedRows.filter((row) => row.action_type === "duplicate_weight_movement");
  const submittedCount = Number(counts.submitted_count || counts.visible_count || 0);
  const actionableCount = Number(counts.expected_count || counts.accepted_count || counts.actionable_count || 0);
  const weightCount = Number(counts.weight_count || counts.saved_count || 0);
  const movementCount = Number(counts.movement_only_count || 0) + Number(counts.duplicate_weight_movement_count || 0) + Number(counts.movement_count || 0);
  const processedCount = Number(counts.processed_count || counts.success_count || counts.saved_count || 0);
  const successCount = Number(counts.success_count || counts.saved_count || 0);
  const duplicateCount = Number(counts.duplicate_count || counts.duplicate_weight_count || 0);
  const skippedCount = Number(counts.skipped_count || 0);
  const blockedCount = Number(counts.blocked_count || 0);
  const failedCount = Number(counts.failed_count || 0);
  const remainingCount = Number(counts.remaining_count || 0);
  const batchStatus = data.status ? `<div class="bulk-review-notes"><div>Batch status: ${escapeHtml(data.status)}${data.batch_id ? ` (${escapeHtml(data.batch_id)})` : ""}. Remaining rows: ${remainingCount}.</div></div>` : "";
  const blockedHtml = blockedRows.length
    ? `<div class="bulk-review-errors">
        ${blockedRows.map((row) => `
          <div><strong>${escapeHtml(formatTagNumber(row.tag_number || row.pig_id || "-"))}</strong>: ${escapeHtml(row.reason || "Needs attention")}</div>
        `).join("")}
      </div>`
    : "";
  const failedHtml = failedRows.length
    ? `<div class="bulk-review-errors">
        ${failedRows.map((item) => {
          const row = item.row || item.original_row_json || item || {};
          const error = item.error || {};
          return `<div><strong>${escapeHtml(formatTagNumber(row.tag_number || row.pig_id || "-"))}</strong>: ${escapeHtml(item.status_reason || error.message || error.status || "Save failed")}</div>`;
        }).join("")}
      </div>`
    : "";
  const rowResultsHtml = rowResults.length
    ? `<div class="bulk-review-notes">
        ${rowResults.slice(0, 12).map((row) => `<div><strong>${escapeHtml(formatTagNumber(row.tag_number || row.pig_id || "-"))}</strong>: ${escapeHtml(row.status || "review")} - ${escapeHtml(row.status_reason || row.message || "")}</div>`).join("")}
      </div>`
    : "";
  const movementHtml = movementRows.length || duplicateMovementRows.length
    ? `<div class="bulk-review-notes">
        ${movementRows.length ? `<div>${movementRows.length} pen movement${movementRows.length === 1 ? "" : "s"} will be saved without a weight row.</div>` : ""}
        ${duplicateMovementRows.length ? `<div>${duplicateMovementRows.length} duplicate weight row${duplicateMovementRows.length === 1 ? "" : "s"} will keep the existing weight and save only the pen move.</div>` : ""}
      </div>`
    : "";

  reviewPanel.classList.remove("hidden");
  reviewPanel.innerHTML = `
    <div class="bulk-review-header">
      <strong>Batch Review</strong>
      <span>${submittedCount} visible, ${actionableCount} actionable, ${weightCount} weight row${weightCount === 1 ? "" : "s"}, ${movementCount} pen change${movementCount === 1 ? "" : "s"}, ${processedCount} processed, ${successCount} success, ${duplicateCount} duplicate, ${remainingCount} remaining, ${skippedCount} skipped, ${blockedCount} blocked, ${failedCount} failed</span>
    </div>
    ${batchStatus}
    ${movementHtml}
    ${blockedHtml}
    ${failedHtml}
    ${rowResultsHtml}
  `;
}

async function preflightBatch() {
  persistDraft({ statusLabel: "Autosaved before check", validation_status: "preflight_pending" });
  const endpoint = "/api/pig-weights/weights-batch/preflight";
  const response = await fetch("/api/pig-weights/weights-batch/preflight", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      weight_date: bulkDateInput.value,
      weighed_by: "WebApp",
      rows: rowsPayload(),
    }),
  });
  const data = await parseBulkJsonResponse(response, endpoint);
  renderReview(data);
  return { response, data };
}

async function stageBulkBatch() {
  const endpoint = "/api/pig-weights/bulk-batches";
  const response = await fetch(endpoint, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      draft_id: activeDraftId || createDraftId(),
      weight_date: bulkDateInput.value,
      weighed_by: "WebApp",
      rows: rowsPayload(),
    }),
  });
  const data = await parseBulkJsonResponse(response, endpoint);
  if (data.batch_id) activeBatchId = data.batch_id;
  renderReview(data);
  return { response, data };
}

async function processActiveBatch(options = {}) {
  if (!activeBatchId) {
    setMessage("No staged batch is available. Stage the saved draft before processing.", "error");
    return null;
  }
  const maxLoops = Number(options.maxLoops || 20);
  let lastData = null;
  for (let loop = 0; loop < maxLoops; loop += 1) {
    const endpoint = `/api/pig-weights/bulk-batches/${encodeURIComponent(activeBatchId)}/process`;
    const response = await fetch(endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chunk_size: 10 }),
    });
    const data = await parseBulkJsonResponse(response, endpoint);
    data.batch_id = data.batch_id || activeBatchId;
    lastData = data;
    renderReview(data);

    if (!response.ok || !data.ok) {
      persistDraft({ statusLabel: "Chunk failed - draft kept", validation_status: "chunk_failed" });
      if (continueButton) continueButton.classList.remove("hidden");
      setMessage(uploadFailureMessage(data, "Batch processing stopped. Draft and staged batch are still saved."), "error");
      return data;
    }

    const status = String(data.status || "").toLowerCase();
    const remaining = Number((data.counts || data).remaining_count || 0);
    if (status === "complete" || status === "partial" || status === "failed" || remaining <= 0) {
      if (isCompleteUploadSuccess(data)) {
        clearUploadedAndDuplicateDraftRows(data);
        activeBatchId = "";
        if (continueButton) continueButton.classList.add("hidden");
        setMessage(`Bulk batch complete. ${Number((data.counts || data).success_count || 0)} row action${Number((data.counts || data).success_count || 0) === 1 ? "" : "s"} succeeded.`, "success");
        await loadData();
      } else {
        persistDraft({ statusLabel: "Batch incomplete - draft kept", validation_status: "batch_incomplete" });
        if (continueButton) continueButton.classList.remove("hidden");
        setMessage(uploadFailureMessage(data, "Batch is not complete. Draft and staged batch are still saved for retry."), "error");
      }
      return data;
    }
  }
  if (lastData) {
    persistDraft({ statusLabel: "Processing paused - draft kept", validation_status: "processing_paused" });
    if (continueButton) continueButton.classList.remove("hidden");
    setMessage("Processing paused after several chunks. Continue Processing will resume the staged batch.", "success");
  }
  return lastData;
}

async function uploadBatch() {
  clearMessage();
  uploadButton.disabled = true;
  uploadButton.textContent = "Staging...";
  if (continueButton) continueButton.classList.add("hidden");

  try {
    persistDraft({ statusLabel: "Autosaved before staging", validation_status: "stage_pending" });
    const { response, data } = await stageBulkBatch();
    if (!response.ok || !data.ok) {
      persistDraft({ statusLabel: "Staging failed - draft kept", validation_status: "stage_failed" });
      setMessage(uploadFailureMessage(data, "Batch could not be staged. Draft kept."), "error");
      return;
    }

    const counts = data.counts || {};
    if (Number(counts.actionable_count || 0) === 0) {
      persistDraft({ statusLabel: "No actionable rows - draft kept", validation_status: "nothing_to_process" });
      setMessage("No actionable weight or pen-change rows found. Draft kept for review.", "error");
      return;
    }

    const confirmed = window.confirm(`Stage saved as ${data.batch_id}. Process ${counts.actionable_count || 0} actionable row${Number(counts.actionable_count || 0) === 1 ? "" : "s"} in safe chunks now?`);
    if (!confirmed) {
      persistDraft({ statusLabel: "Staged - draft kept", validation_status: "staged" });
      if (continueButton) continueButton.classList.remove("hidden");
      setMessage(`Batch staged as ${data.batch_id}. Draft remains saved. Use Continue Processing when ready.`, "success");
      return;
    }

    uploadButton.textContent = "Processing chunks...";
    await processActiveBatch();
  } catch (error) {
    console.error("bulk upload error:", error);
    persistDraft({ statusLabel: "Upload error - draft kept", validation_status: "upload_exception" });
    if (continueButton && activeBatchId) continueButton.classList.remove("hidden");
    setMessage(`Upload failed before completion: ${error.message || "network/server error"}. Draft kept on this device; use Download Draft before retrying if needed.`, "error");
  } finally {
    uploadButton.disabled = false;
    uploadButton.textContent = "Stage Batch";
  }
}

async function loadData() {
  try {
    const [pigsResponse, pensResponse] = await Promise.all([
      fetch("/api/pig-weights/pigs"),
      fetch("/api/pig-weights/pens"),
    ]);
    const pigsData = await pigsResponse.json();
    const pensData = await pensResponse.json();

    if (!pigsResponse.ok || !pensResponse.ok) {
      throw new Error("Failed to load bulk weight data.");
    }

    allPigs = pigsData.pigs || [];
    allPens = pensData.pens || [];
    populatePens();
    loadDraft();
    renderTable();
  } catch (error) {
    console.error("bulk weights load error:", error);
    setMessage(error.message || "Something went wrong while loading bulk weights.");
    bulkWeightBody.innerHTML = `<tr><td colspan="7" class="table-empty">Could not load active pigs.</td></tr>`;
  }
}

penFilterSelect.addEventListener("change", renderTable);
bulkDateInput.addEventListener("change", () => {
  try {
    persistDraft({ statusLabel: "Saved before date change" });
  } catch (error) {
    console.error("bulk draft save before date change error:", error);
  }
  hideRecoveryBanner();
  loadDraft({ allowLatestFallback: false });
  renderTable();
});
clearPensButton.addEventListener("click", () => {
  Array.from(penFilterSelect.options).forEach((option) => {
    option.selected = false;
  });
  renderTable();
});
saveDraftButton.addEventListener("click", saveDraft);
uploadButton.addEventListener("click", uploadBatch);
if (downloadDraftButton) {
  downloadDraftButton.addEventListener("click", () => {
    const payload = persistDraft({ statusLabel: "Downloaded", validation_status: "manual_export" });
    downloadTextFile(`bulk-weight-draft-${payload.weight_date || "no-date"}.json`, JSON.stringify(payload, null, 2));
    setMessage("Draft downloaded. Keep this file until the batch upload is confirmed.", "success");
  });
}
if (importDraftButton && importDraftInput) {
  importDraftButton.addEventListener("click", () => importDraftInput.click());
  importDraftInput.addEventListener("change", async () => {
    const file = importDraftInput.files && importDraftInput.files[0];
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text());
      importDraftPayload(payload);
    } catch (error) {
      console.error("bulk draft import error:", error);
      setMessage(`Draft import failed: ${error.message || "invalid file"}.`, "error");
    } finally {
      importDraftInput.value = "";
    }
  });
}
if (continueButton) {
  continueButton.addEventListener("click", async () => {
    continueButton.disabled = true;
    try {
      await processActiveBatch();
    } finally {
      continueButton.disabled = false;
    }
  });
}
if (restoreDraftButton) {
  restoreDraftButton.addEventListener("click", () => {
    if (!recoveredDraftPayload) return;
    draftRows = recoveredDraftPayload.rows || {};
    activeDraftId = recoveredDraftPayload.draft_id || activeDraftId || createDraftId();
    writeDraftPayload(buildDraftPayload({ draft_id: activeDraftId, validation_status: recoveredDraftPayload.validation_status || "restored" }));
    renderTable();
    setMessage("Recovered draft restored on screen. Review rows before uploading.", "success");
    hideRecoveryBanner();
  });
}
if (discardDraftButton) {
  discardDraftButton.addEventListener("click", () => {
    if (!window.confirm("Discard the saved bulk weight draft for this date?")) return;
    window.localStorage.removeItem(draftKey());
    window.localStorage.removeItem(legacyDraftKey());
    draftRows = {};
    activeDraftId = createDraftId();
    draftStatus.textContent = "Discarded";
    hideRecoveryBanner();
    renderTable();
    setMessage("Saved draft discarded for this date.", "success");
  });
}

if (typeof window !== "undefined") {
  window.bulkWeightsDraftRecovery = {
    buildDraftPayload,
    clearUploadedAndDuplicateDraftRows,
    isCompleteUploadSuccess,
    importDraftPayload,
    loadDraft,
    parseBulkJsonResponse,
    persistDraft,
    uploadFailureMessage,
    stageBulkBatch,
    processActiveBatch,
  };
}

(async function initPage() {
  bulkDateInput.value = todayIso();
  await loadData();
})();
