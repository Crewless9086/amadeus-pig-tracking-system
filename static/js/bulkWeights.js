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
const uploadOverlay = document.getElementById("bulk_upload_overlay");
const uploadOverlayTitle = document.getElementById("bulk_upload_overlay_title");
const uploadOverlayText = document.getElementById("bulk_upload_overlay_text");

const DRAFT_VERSION = 3;
let allPigs = [];
let allPens = [];
let draftRows = {};
let activeDraftId = "";
let activeBatchId = "";
let autosaveTimer = null;
let recoveredDraftPayload = null;
let lastKnownBatchData = null;

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

function setUploadOverlay(title, text) {
  if (!uploadOverlay) return;
  if (!title && !text) {
    uploadOverlay.classList.add("hidden");
    return;
  }
  if (uploadOverlayTitle) uploadOverlayTitle.textContent = title || "Uploading weights";
  if (uploadOverlayText) uploadOverlayText.textContent = text || "Please keep this page open.";
  uploadOverlay.classList.remove("hidden");
}

function setUploadLocked(isLocked) {
  [
    bulkDateInput,
    penFilterSelect,
    clearPensButton,
    saveDraftButton,
    downloadDraftButton,
    importDraftButton,
    uploadButton,
  ].forEach((element) => {
    if (element) element.disabled = Boolean(isLocked);
  });
  document.querySelectorAll("[data-bulk-weight], [data-bulk-pen], [data-bulk-notes]").forEach((input) => {
    input.disabled = Boolean(isLocked);
  });
}

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function ownerSafeFailureMessage(data) {
  const status = String((data && data.status) || (data && data.error) || "").toLowerCase();
  if (status === "non_json_response" || status === "invalid_json_response") {
    return "Upload paused because the server returned an unexpected page instead of upload results. Your draft is saved. Press Upload Weights to resume.";
  }
  if (data && data.ok === false) {
    return "Upload paused because the server could not finish this step. Your draft is saved. Press Upload Weights to resume.";
  }
  return "Upload paused. Your draft is saved. Press Upload Weights to resume.";
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
    batch_id: options.batch_id || activeBatchId || "",
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

function countValue(counts, ...keys) {
  for (const key of keys) {
    const value = Number((counts || {})[key] || 0);
    if (value) return value;
  }
  return 0;
}

function isCompleteUploadSuccess(data) {
  if (!data || (!data.success && !data.ok)) return false;
  const status = String(data.status || "").toLowerCase();
  const counts = data.counts || data;
  const failed = Number(counts.failed_count || 0);
  const blocked = Number(counts.blocked_count || 0);
  const remaining = Number(counts.remaining_count || 0);
  if (failed || blocked || remaining) return false;
  if (!status) {
    const expected = countValue(counts, "expected_count", "accepted_count", "actionable_row_count", "actionable_count");
    const processed = Number(counts.processed_count || counts.success_count || 0);
    const successCount = Number(counts.success_count || counts.saved_count || 0);
    return Boolean(expected && processed === expected && successCount === expected);
  }
  return status === "complete" || status === "uploaded";
}

function uploadFailureMessage(data, fallback = "Upload failed before completion.") {
  if (!data || typeof data !== "object") return fallback;
  return ownerSafeFailureMessage(data);
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
      message: `The server returned a response this page could not read from ${endpoint} (HTTP ${response.status}). Your draft is still saved.`,
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
      message: `The server returned an unreadable response from ${endpoint} (HTTP ${response.status}). Your draft is still saved.`,
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
    activeBatchId = payload ? payload.batch_id || "" : "";
    if (continueButton && activeBatchId) continueButton.classList.remove("hidden");
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
    throw new Error("Imported file is not a bulk weight draft file.");
  }
  if (payload.weight_date) bulkDateInput.value = payload.weight_date;
  draftRows = payload.rows || {};
  activeDraftId = payload.draft_id || createDraftId();
  activeBatchId = payload.batch_id || "";
  writeDraftPayload(buildDraftPayload({ draft_id: activeDraftId, validation_status: "imported" }));
  renderTable();
  showRecoveryBanner(buildDraftPayload({ draft_id: activeDraftId, validation_status: "imported" }));
  setMessage(`Imported draft restored with ${actionableDraftRows().length} row${actionableDraftRows().length === 1 ? "" : "s"} ready to check. Press Upload Weights when ready.`, "success");
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

function displayReason(row) {
  const reason = String(row.status_reason || row.reason || row.message || "");
  if (row.status === "duplicate" || /already has a weight|already recorded/i.test(reason)) {
    return "Already recorded for this date.";
  }
  if (row.status === "skipped" || /no weight|no pen change|no action/i.test(reason)) {
    return "No new weight or pen change entered.";
  }
  return reason || "Needs review.";
}

function renderReview(data) {
  const counts = data.counts || data || {};
  const blockedRows = data.blocked_rows || [];
  const failedRows = data.failed_rows || [];
  const rowResults = data.row_results || data.rows || [];
  const acceptedRows = data.accepted_rows || [];
  const movementRows = acceptedRows.filter((row) => row.action_type === "movement_only");
  const duplicateMovementRows = acceptedRows.filter((row) => row.action_type === "duplicate_weight_movement");
  const draft = buildDraftPayload({ validation_status: "review_snapshot" });
  const draftSubmittedCount = Number(draft.visible_row_count || 0) || countValue(counts, "submitted_count", "visible_row_count", "visible_count");
  const draftInputCount = Number(draft.actionable_row_count || 0) || countValue(counts, "expected_count", "actionable_row_count", "accepted_count", "actionable_count");
  const draftWeightCount = Number(draft.expected_row_count || 0) || countValue(counts, "weight_row_count", "weight_count", "saved_count");
  const draftMovementCount = draftRowValues().filter((row) => String(row.moved_to_pen_id || "").trim() !== "").length || countValue(counts, "movement_row_count", "movement_only_count") + countValue(counts, "duplicate_weight_movement_count") + countValue(counts, "movement_count");
  const draftSkippedCount = Math.max(draftSubmittedCount - draftInputCount, 0) || countValue(counts, "skipped_row_count", "skipped_count");
  const processedCount = countValue(counts, "processed_count", "success_count", "saved_count");
  const successCount = countValue(counts, "success_count", "saved_count");
  const duplicateCount = countValue(counts, "duplicate_count", "duplicate_weight_count");
  const blockedCount = Number(counts.blocked_count || 0);
  const failedCount = Number(counts.failed_count || 0);
  const remainingCount = countValue(counts, "remaining_count");
  const isUncertainStatus = ["non_json_response", "invalid_json_response"].includes(String(data.status || data.error || "").toLowerCase()) || data.ok === false;
  const uploadLine = isUncertainStatus
    ? "Upload status unknown. Draft is saved. Press Upload Weights to check and resume."
    : remainingCount
      ? `${remainingCount} row${remainingCount === 1 ? "" : "s"} still need upload.`
      : "No rows waiting to upload.";
  const batchLine = data.status || data.batch_id
    ? `<details class="bulk-review-notes"><summary>Technical details</summary><div>${escapeHtml(uploadLine)}${data.batch_id ? ` Batch ${escapeHtml(data.batch_id)}.` : ""}${data.status ? ` Status ${escapeHtml(data.status)}.` : ""}</div></details>`
    : "";
  const issueRows = [
    ...blockedRows.map((row) => ({ ...row, status: "blocked" })),
    ...failedRows.map((item) => ({ ...(item.row || item.original_row_json || item), status: "failed", status_reason: item.status_reason || item.error?.message || item.error?.status })),
    ...rowResults.filter((row) => ["failed", "blocked", "duplicate", "skipped"].includes(String(row.status || ""))).slice(0, 12),
  ];
  const issueHtml = issueRows.length
    ? `<div class="bulk-review-notes">
        ${issueRows.slice(0, 16).map((row) => `<div><strong>${escapeHtml(formatTagNumber(row.tag_number || row.pig_id || "-"))}</strong>: ${escapeHtml(displayReason(row))}</div>`).join("")}
      </div>`
    : "";
  const movementHtml = movementRows.length || duplicateMovementRows.length
    ? `<div class="bulk-review-notes">
        ${movementRows.length ? `<div>${movementRows.length} pen movement${movementRows.length === 1 ? "" : "s"} will be uploaded without a weight row.</div>` : ""}
        ${duplicateMovementRows.length ? `<div>${duplicateMovementRows.length} already-recorded weight row${duplicateMovementRows.length === 1 ? "" : "s"} will still upload the valid pen move.</div>` : ""}
      </div>`
    : "";

  reviewPanel.classList.remove("hidden");
  reviewPanel.innerHTML = `
    <div class="bulk-review-header">
      <strong>Draft Review</strong>
      <span>${draftSubmittedCount} active pigs visible, ${draftInputCount} row${draftInputCount === 1 ? "" : "s"} with owner input, ${draftWeightCount} weight entr${draftWeightCount === 1 ? "y" : "ies"}, ${draftMovementCount} pen change${draftMovementCount === 1 ? "" : "s"}, ${draftSkippedCount} blank/no-change skipped</span>
    </div>
    <div class="bulk-review-header">
      <strong>Upload Progress</strong>
      <span>${successCount} uploaded, ${duplicateCount} already recorded, ${draftSkippedCount} skipped blank/no-change, ${remainingCount} remaining to upload, ${blockedCount} needs review, ${failedCount} failed</span>
    </div>
    ${batchLine}
    ${movementHtml}
    ${issueHtml}
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

async function fetchActiveBatchStatus(options = {}) {
  if (!activeBatchId) return null;
  const endpoint = `/api/pig-weights/bulk-batches/${encodeURIComponent(activeBatchId)}`;
  const response = await fetch(endpoint, { method: "GET" });
  const data = await parseBulkJsonResponse(response, endpoint);
  data.batch_id = data.batch_id || activeBatchId;
  if (response.ok && data.ok) lastKnownBatchData = data;
  renderReview(data);
  const remaining = countValue(data.counts || data, "remaining_count");
  const status = String(data.status || "").toLowerCase();
  if (response.ok && data.ok && remaining > 0 && ["staged", "processing", "partial"].includes(status)) {
    if (continueButton) continueButton.classList.add("hidden");
    if (!options.silent) {
      setMessage(`Upload paused. ${remaining} row${remaining === 1 ? "" : "s"} still need upload. Press Upload Weights to resume.`, "error");
    }
  } else if (response.ok && data.ok && status === "complete") {
    if (continueButton) continueButton.classList.add("hidden");
    if (!options.silent) {
      setMessage("Previous upload is complete. Import or restore a draft only if you need to review it again.", "success");
    }
  } else if (!response.ok || !data.ok) {
    if (!options.silent) {
      setMessage("Upload status unknown. Draft is saved. Press Upload Weights to check and resume.", "error");
    }
  }
  return data;
}

async function processActiveBatch(options = {}) {
  if (!activeBatchId) {
    setMessage("No saved upload is available. Use Upload Weights to start again from the saved draft.", "error");
    return null;
  }
  const maxLoops = Number(options.maxLoops || 50);
  const maxRetries = Number(options.maxRetries || 2);
  let lastData = null;
  for (let loop = 0; loop < maxLoops; loop += 1) {
    const endpoint = `/api/pig-weights/bulk-batches/${encodeURIComponent(activeBatchId)}/process`;
    let response = null;
    let data = null;
    for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
      setUploadOverlay("Uploading weights", attempt ? `Retrying upload step ${attempt} of ${maxRetries}. Please keep this page open.` : "Processing rows. Please keep this page open.");
      try {
        response = await fetch(endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ chunk_size: 3 }),
        });
        data = await parseBulkJsonResponse(response, endpoint);
      } catch (error) {
        data = {
          ok: false,
          success: false,
          status: "network_interruption",
          error: "network_interruption",
          message: error.message || "Network interruption",
          batch_id: activeBatchId,
          counts: lastKnownBatchData ? lastKnownBatchData.counts : {},
        };
        response = { ok: false };
      }
      if (response.ok && data.ok) break;
      if (attempt < maxRetries) await sleep(500 * (attempt + 1));
    }
    data.batch_id = data.batch_id || activeBatchId;
    lastData = data;

    if (!response.ok || !data.ok) {
      persistDraft({ statusLabel: "Chunk failed - draft kept", validation_status: "chunk_failed" });
      const statusData = await fetchActiveBatchStatus({ silent: true }).catch(() => null);
      renderReview(statusData && statusData.ok ? statusData : data);
      if (continueButton) continueButton.classList.add("hidden");
      setMessage(uploadFailureMessage(data, "Upload paused. Your draft is saved. Press Upload Weights to resume."), "error");
      setUploadOverlay("", "");
      return data;
    }

    lastKnownBatchData = data;
    renderReview(data);
    const status = String(data.status || "").toLowerCase();
    const remaining = Number((data.counts || data).remaining_count || 0);
    setUploadOverlay("Uploading weights", remaining ? `Processing rows. ${remaining} row${remaining === 1 ? "" : "s"} still need upload.` : "Finishing upload summary.");
    if (status === "complete" || status === "partial" || status === "failed" || remaining <= 0) {
      if (isCompleteUploadSuccess(data)) {
        clearUploadedAndDuplicateDraftRows(data);
        activeBatchId = "";
        if (continueButton) continueButton.classList.add("hidden");
        const counts = data.counts || data;
        const duplicateCount = Number(counts.duplicate_count || 0);
        const skippedCount = Number(counts.skipped_row_count || counts.skipped_count || 0);
        renderTable();
        renderReview(data);
        setMessage(`Upload complete: ${Number(counts.success_count || 0)} row action${Number(counts.success_count || 0) === 1 ? "" : "s"} uploaded, ${duplicateCount} already recorded, ${skippedCount} blank/no-change skipped.`, "success");
      } else {
        persistDraft({ statusLabel: "Batch incomplete - draft kept", validation_status: "batch_incomplete" });
        if (continueButton) continueButton.classList.add("hidden");
        setMessage("Upload completed with issues. Your draft is saved. Press Upload Weights to retry unresolved rows.", "error");
      }
      setUploadOverlay("", "");
      return data;
    }
  }
  if (lastData) {
    persistDraft({ statusLabel: "Processing paused - draft kept", validation_status: "processing_paused" });
    if (continueButton) continueButton.classList.add("hidden");
    setMessage("Upload paused safely. Press Upload Weights to resume the saved batch.", "success");
  }
  setUploadOverlay("", "");
  return lastData;
}

async function uploadBatch() {
  clearMessage();
  setUploadLocked(true);
  uploadButton.textContent = "Uploading...";
  setUploadOverlay("Uploading weights", "Please keep this page open.");
  if (continueButton) continueButton.classList.add("hidden");

  try {
    persistDraft({ statusLabel: "Autosaved before upload", validation_status: "upload_pending" });
    if (activeBatchId) {
      await fetchActiveBatchStatus({ silent: true }).catch(() => null);
      await processActiveBatch();
      return;
    }
    setUploadOverlay("Uploading weights", "Preparing batch. Please keep this page open.");
    const { response, data } = await stageBulkBatch();
    if (!response.ok || !data.ok) {
      persistDraft({ statusLabel: "Staging failed - draft kept", validation_status: "stage_failed" });
      setMessage(uploadFailureMessage(data, "Upload paused. Your draft is saved. Press Upload Weights to resume."), "error");
      setUploadOverlay("", "");
      return;
    }
    lastKnownBatchData = data;

    const counts = data.counts || {};
    const remainingAfterStage = countValue(counts, "remaining_count");
    const actionableAfterStage = countValue(counts, "actionable_row_count", "actionable_count", "accepted_count", "expected_count");
    if (actionableAfterStage === 0 && remainingAfterStage === 0) {
      persistDraft({ statusLabel: "Nothing new to upload - draft kept", validation_status: "nothing_to_process" });
      setMessage("Nothing new to upload. Blank rows were skipped and existing weights are already recorded.", "success");
      setUploadOverlay("", "");
      return;
    }

    persistDraft({ statusLabel: "Uploading", validation_status: "staged", batch_id: activeBatchId });
    uploadButton.textContent = "Uploading rows...";
    const rowsToUpload = remainingAfterStage || actionableAfterStage;
    setMessage(`Preparing batch and uploading ${rowsToUpload} row${rowsToUpload === 1 ? "" : "s"}.`, "success");
    await processActiveBatch();
  } catch (error) {
    console.error("bulk upload error:", error);
    persistDraft({ statusLabel: "Upload error - draft kept", validation_status: "upload_exception" });
    if (continueButton) continueButton.classList.add("hidden");
    setMessage("Upload paused because the server could not finish this step. Your draft is saved. Press Upload Weights to resume.", "error");
    setUploadOverlay("", "");
  } finally {
    setUploadLocked(false);
    uploadButton.textContent = "Upload Weights";
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
    if (activeBatchId) await fetchActiveBatchStatus();
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
    setMessage("Recovered draft restored on screen. Press Upload Weights when ready.", "success");
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
    countValue,
    fetchActiveBatchStatus,
    importDraftPayload,
    loadDraft,
    parseBulkJsonResponse,
    persistDraft,
    uploadFailureMessage,
    stageBulkBatch,
    processActiveBatch,
    uploadBatch,
  };
}

(async function initPage() {
  bulkDateInput.value = todayIso();
  await loadData();
})();
