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

let allPigs = [];
let allPens = [];
let draftRows = {};

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
  return `bulkWeightsDraft:v1:${bulkDateInput.value || "no-date"}`;
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
  return Object.values(draftRows).filter((row) => String(row.weight_kg || "").trim() !== "").length;
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
    input.addEventListener("input", updateSummary);
    input.addEventListener("change", updateSummary);
  });
  document.querySelectorAll("[data-bulk-weight]").forEach((input) => {
    input.addEventListener("wheel", (event) => {
      event.preventDefault();
    }, { passive: false });
  });
  updateSummary();
}

function loadDraft() {
  try {
    const raw = window.localStorage.getItem(draftKey());
    draftRows = raw ? JSON.parse(raw).rows || {} : {};
    draftStatus.textContent = raw ? "Loaded" : "Not saved";
  } catch (error) {
    console.error("load bulk draft error:", error);
    draftRows = {};
    draftStatus.textContent = "Draft error";
  }
}

function saveDraft() {
  collectDraftFromDom();
  const payload = {
    saved_at: new Date().toISOString(),
    weight_date: bulkDateInput.value,
    rows: draftRows,
  };
  window.localStorage.setItem(draftKey(), JSON.stringify(payload));
  draftStatus.textContent = "Saved";
  setMessage("Draft saved on this device.", "success");
  updateSummary();
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
  const clearPigIds = new Set();
  (uploadData.saved_rows || []).forEach((row) => {
    if (row.pig_id) clearPigIds.add(row.pig_id);
  });
  (uploadData.movement_rows || []).forEach((row) => {
    if (row.pig_id) clearPigIds.add(row.pig_id);
  });
  (uploadData.blocked_rows || []).forEach((row) => {
    const reason = String(row.reason || "").toLowerCase();
    if (row.pig_id && reason.includes("already has a weight entry")) {
      clearPigIds.add(row.pig_id);
    }
  });

  clearPigIds.forEach((pigId) => {
    delete draftRows[pigId];
  });

  if (Object.values(draftRows).some((row) => String(row.weight_kg || "").trim() !== "")) {
    window.localStorage.setItem(draftKey(), JSON.stringify({
      saved_at: new Date().toISOString(),
      weight_date: bulkDateInput.value,
      rows: draftRows,
    }));
    draftStatus.textContent = "Needs review";
  } else {
    window.localStorage.removeItem(draftKey());
    draftRows = {};
    draftStatus.textContent = "Uploaded";
  }
}

function renderReview(data) {
  const blockedRows = data.blocked_rows || [];
  const acceptedRows = data.accepted_rows || [];
  const movementRows = acceptedRows.filter((row) => row.action_type === "movement_only");
  const duplicateMovementRows = acceptedRows.filter((row) => row.action_type === "duplicate_weight_movement");
  const blockedHtml = blockedRows.length
    ? `<div class="bulk-review-errors">
        ${blockedRows.map((row) => `
          <div><strong>${escapeHtml(formatTagNumber(row.tag_number || row.pig_id || "-"))}</strong>: ${escapeHtml(row.reason || "Needs attention")}</div>
        `).join("")}
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
      <span>${Number(data.weight_count || data.accepted_count || 0)} weights, ${Number(data.movement_only_count || 0) + Number(data.duplicate_weight_movement_count || 0)} moves, ${Number(data.skipped_count || 0)} skipped, ${Number(data.blocked_count || 0)} blocked</span>
    </div>
    ${movementHtml}
    ${blockedHtml}
  `;
}

async function preflightBatch() {
  const response = await fetch("/api/pig-weights/weights-batch/preflight", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      weight_date: bulkDateInput.value,
      weighed_by: "WebApp",
      rows: rowsPayload(),
    }),
  });
  const data = await response.json();
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
      setMessage("Batch has rows that need attention. Nothing was uploaded.", "error");
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
    const uploadResponse = await fetch("/api/pig-weights/weights-batch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        weight_date: bulkDateInput.value,
        weighed_by: "WebApp",
        rows: rowsPayload(),
      }),
    });
    const uploadData = await uploadResponse.json();

    if (!uploadResponse.ok || !uploadData.success) {
      renderReview(uploadData);
      setMessage(uploadData.message || "Batch upload failed. Check the review panel.", "error");
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
    const backendWarning = uploadData.warnings?.length
      ? ` Warning: ${uploadData.warnings.join(" ")}`
      : "";
    setMessage(`Uploaded ${uploadData.saved_count} weight record${uploadData.saved_count === 1 ? "" : "s"} and ${movementSaved} pen movement${movementSaved === 1 ? "" : "s"}. Duplicate weights protected: ${duplicateSaved}. Blank/no-change rows skipped: ${uploadData.skipped_count}.${extraSkipped}${backendWarning}${auditWarning}`, "success");
    await loadData();
  } catch (error) {
    console.error("bulk upload error:", error);
    setMessage("Something went wrong while uploading the batch.", "error");
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
  collectDraftFromDom();
  loadDraft();
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

(async function initPage() {
  bulkDateInput.value = todayIso();
  await loadData();
})();
