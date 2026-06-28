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

const DRAFT_VERSION = 2;
let allPigs = [];
let allPens = [];
let draftRows = {};
let activeDraftId = "";
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
  if (!data || !data.success) return false;
  const expected = Number(data.expected_count || data.accepted_count || 0);
  const processed = Number(data.processed_count || 0);
  const successCount = Number(data.success_count || data.saved_count || 0);
  const failed = Number(data.failed_count || 0);
  const blocked = Number(data.blocked_count || 0);
  if (failed || blocked) return false;
  if (expected && processed !== expected) return false;
  if (expected && successCount !== expected) return false;
  return true;
}

function uploadFailureMessage(data, fallback = "Upload failed before completion.") {
  if (!data || typeof data !== "object") return fallback;
  const parts = [];
  if (data.message) parts.push(data.message);
  if (data.status) parts.push(`Status: ${data.status}.`);
  const expected = Number(data.expected_count || data.accepted_count || 0);
  const successCount = Number(data.success_count || data.saved_count || 0);
  const failed = Number(data.failed_count || 0);
  const blocked = Number(data.blocked_count || 0);
  const skipped = Number(data.skipped_count || 0);
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
  const blockedRows = data.blocked_rows || [];
  const failedRows = data.failed_rows || [];
  const rowResults = data.row_results || [];
  const acceptedRows = data.accepted_rows || [];
  const movementRows = acceptedRows.filter((row) => row.action_type === "movement_only");
  const duplicateMovementRows = acceptedRows.filter((row) => row.action_type === "duplicate_weight_movement");
  const submittedCount = Number(data.submitted_count || data.visible_count || 0);
  const actionableCount = Number(data.expected_count || data.accepted_count || 0);
  const weightCount = Number(data.weight_count || data.saved_count || 0);
  const movementCount = Number(data.movement_only_count || 0) + Number(data.duplicate_weight_movement_count || 0) + Number(data.movement_count || 0);
  const processedCount = Number(data.processed_count || data.success_count || data.saved_count || 0);
  const skippedCount = Number(data.skipped_count || 0);
  const blockedCount = Number(data.blocked_count || 0);
  const failedCount = Number(data.failed_count || 0);
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
          const row = item.row || {};
          const error = item.error || {};
          return `<div><strong>${escapeHtml(formatTagNumber(row.tag_number || row.pig_id || "-"))}</strong>: ${escapeHtml(error.message || error.status || "Save failed")}</div>`;
        }).join("")}
      </div>`
    : "";
  const rowResultsHtml = rowResults.length
    ? `<div class="bulk-review-notes">
        ${rowResults.slice(0, 12).map((row) => `<div><strong>${escapeHtml(formatTagNumber(row.tag_number || row.pig_id || "-"))}</strong>: ${escapeHtml(row.status || "review")} - ${escapeHtml(row.message || "")}</div>`).join("")}
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
      <span>${submittedCount} visible, ${actionableCount} actionable, ${weightCount} weight row${weightCount === 1 ? "" : "s"}, ${movementCount} pen change${movementCount === 1 ? "" : "s"}, ${processedCount} processed, ${skippedCount} skipped, ${blockedCount} blocked, ${failedCount} failed</span>
    </div>
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

async function uploadBatch() {
  clearMessage();
  uploadButton.disabled = true;
  uploadButton.textContent = "Checking...";

  try {
    const { response, data } = await preflightBatch();
    if (!response.ok) {
      persistDraft({ statusLabel: "Preflight failed - draft kept", validation_status: "preflight_failed" });
      setMessage(uploadFailureMessage(data, "Batch has rows that need attention. Nothing was uploaded. Draft kept."), "error");
      return;
    }

    if (Number(data.accepted_count || 0) === 0) {
      setMessage("No weights entered. Nothing to upload.", "error");
      return;
    }

    const movementCount = Number(data.movement_only_count || 0) + Number(data.duplicate_weight_movement_count || 0);
    const blockedText = Number(data.blocked_count || 0)
      ? ` ${data.blocked_count} blocked/existing row${data.blocked_count === 1 ? "" : "s"} will be skipped.`
      : "";
    const moveText = movementCount
      ? ` ${movementCount} pen movement${movementCount === 1 ? "" : "s"} will also be saved.`
      : "";
    const confirmed = window.confirm(`Upload ${data.weight_count || data.accepted_count} new weight record${(data.weight_count || data.accepted_count) === 1 ? "" : "s"} now?${moveText} Blank rows will be skipped. No-change rows will be skipped.${blockedText}`);
    if (!confirmed) {
      setMessage("Batch upload cancelled. Draft is still available on this device.", "error");
      return;
    }

    uploadButton.textContent = "Uploading...";
    const uploadEndpoint = "/api/pig-weights/weights-batch";
    const uploadResponse = await fetch("/api/pig-weights/weights-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        weight_date: bulkDateInput.value,
        weighed_by: "WebApp",
        rows: rowsPayload(),
      }),
    });
    const uploadData = await parseBulkJsonResponse(uploadResponse, uploadEndpoint);

    if (!uploadResponse.ok || !uploadData.success) {
      renderReview(uploadData);
      persistDraft({ statusLabel: "Upload failed - draft kept", validation_status: "upload_failed" });
      setMessage(uploadFailureMessage(uploadData, "Batch upload needs review. Draft kept for recovery and retry."), "error");
      return;
    }

    if (!isCompleteUploadSuccess(uploadData)) {
      renderReview(uploadData);
      persistDraft({ statusLabel: "Partial upload - draft kept", validation_status: "partial_upload" });
      setMessage(uploadFailureMessage(uploadData, "Batch upload was partial. Draft kept for review and retry."), "error");
      return;
    }

    clearUploadedAndDuplicateDraftRows(uploadData);
    const extraSkipped = Number(uploadData.blocked_count || 0) || Number(uploadData.failed_count || 0)
      ? ` Blocked/existing rows skipped: ${Number(uploadData.blocked_count || 0)}. Failed rows kept for review: ${Number(uploadData.failed_count || 0)}.`
      : "";
    const movementSaved = Number(uploadData.movement_count || 0);
    const duplicateSaved = Number(uploadData.duplicate_weight_count || 0);
    const auditWarning = uploadData.audit?.warnings?.length
      ? ` Audit warning: ${uploadData.audit.warnings.join(" ")}`
      : "";
    setMessage(`Uploaded ${uploadData.saved_count} weight record${uploadData.saved_count === 1 ? "" : "s"} and ${movementSaved} pen movement${movementSaved === 1 ? "" : "s"}. Duplicate weights protected: ${duplicateSaved}. Blank/no-change rows skipped: ${uploadData.skipped_count}.${extraSkipped}${auditWarning}`, "success");
    await loadData();
  } catch (error) {
    console.error("bulk upload error:", error);
    persistDraft({ statusLabel: "Upload error - draft kept", validation_status: "upload_exception" });
    setMessage(`Upload failed before completion: ${error.message || "network/server error"}. Draft kept on this device; use Download Draft before retrying if needed.`, "error");
  } finally {
    uploadButton.disabled = false;
    uploadButton.textContent = "Upload Batch";
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
    loadDraft,
    parseBulkJsonResponse,
    persistDraft,
    uploadFailureMessage,
  };
}

(async function initPage() {
  bulkDateInput.value = todayIso();
  await loadData();
})();
