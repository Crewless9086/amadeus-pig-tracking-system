const messageBox = document.getElementById("purpose_review_message");
const subtitle = document.getElementById("purpose_review_subtitle");
const summaryEl = document.getElementById("purpose_review_summary");
const countEl = document.getElementById("purpose_review_count");
const bodyEl = document.getElementById("purpose_review_body");
const selectedCountEl = document.getElementById("purpose_review_selected_count");
const statusFilter = document.getElementById("purpose_review_status_filter");
const litterFilter = document.getElementById("purpose_review_litter_filter");
const suggestionFilter = document.getElementById("purpose_review_suggestion_filter");
const searchInput = document.getElementById("purpose_review_search");
const resetButton = document.getElementById("purpose_review_reset_filters");
const selectVisibleButton = document.getElementById("purpose_review_select_visible");
const clearSelectedButton = document.getElementById("purpose_review_clear_selected");
const previewSelectedButton = document.getElementById("purpose_review_preview_selected");
const applySelectedButton = document.getElementById("purpose_review_apply_selected");
const recheckPanel = document.getElementById("purpose_review_recheck_panel");

let reviewRows = [];
let allowedPurposes = [];
let selectedPigIds = new Set();
let purposeOverrides = {};

document.addEventListener("DOMContentLoaded", loadPurposeReview);

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function queryLitterId() {
  return new URLSearchParams(window.location.search).get("litter_id") || "";
}

function formatTagNumber(value) {
  const raw = String(value || "").trim();
  return /^\d+$/.test(raw) ? raw.padStart(3, "0") : raw;
}

function pigLabel(item) {
  const tag = formatTagNumber(item.tag_number || item.pig_id || "-");
  return item.pig_id && item.pig_id !== item.tag_number ? `${tag} (${item.pig_id})` : tag;
}

function formatKg(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(1)} kg`;
}

function formatAdg(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "-";
  return `${Number(value).toFixed(3)} kg/day`;
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "-";
  return `${Math.round(Number(value) * 100)}%`;
}

function statusLabel(value) {
  return String(value || "")
    .replace(/_/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
}

function showMessage(message, type = "error") {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add(type === "success" ? "message-success" : "message-error");
  messageBox.textContent = message;
}

function clearMessage() {
  messageBox.classList.add("hidden");
  messageBox.classList.remove("message-success", "message-error");
  messageBox.textContent = "";
}

function uniqueOptions(rows, getter) {
  return Array.from(new Set(rows.map(getter).filter(Boolean))).sort((a, b) => a.localeCompare(b));
}

function setSelectOptions(select, values, firstLabel) {
  const currentValue = select.value;
  select.innerHTML = `<option value="">${firstLabel}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = statusLabel(value);
    select.appendChild(option);
  });
  if (values.includes(currentValue)) select.value = currentValue;
}

function populateFilters(rows) {
  setSelectOptions(statusFilter, uniqueOptions(rows, (row) => row.review_status), "All statuses");
  setSelectOptions(litterFilter, uniqueOptions(rows, (row) => row.litter_id), "All litters");
  setSelectOptions(suggestionFilter, uniqueOptions(rows, (row) => row.suggested_purpose), "All suggestions");
}

function renderSummary(summary) {
  const items = [
    ["Total", summary.total ?? 0],
    ["Needs Decision", summary.needs_owner_decision ?? 0],
    ["Needs Data", summary.needs_data ?? 0],
    ["Classified", summary.classified ?? 0],
  ];
  summaryEl.innerHTML = items.map(([label, value]) => `
    <div class="summary-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function rowSearchText(row) {
  return [
    row.pig_id,
    row.tag_number,
    row.litter_id,
    row.sow_tag_number,
    row.boar_tag_number,
    row.review_status,
    row.readiness_bucket,
    row.readiness_reason,
    row.purpose,
    row.proposed_purpose,
    row.suggested_purpose,
    row.suggested_purpose_reason,
    row.growth_class,
    row.litter_quality,
    row.owner_action,
  ].join(" ").toLowerCase();
}

function filteredRows() {
  const status = statusFilter.value;
  const litter = litterFilter.value;
  const suggestion = suggestionFilter.value;
  const search = searchInput.value.trim().toLowerCase();
  return reviewRows.filter((row) => {
    if (status && row.review_status !== status) return false;
    if (litter && row.litter_id !== litter) return false;
    if (suggestion && row.suggested_purpose !== suggestion) return false;
    if (search && !rowSearchText(row).includes(search)) return false;
    return true;
  });
}

function purposeValueForRow(row) {
  return purposeOverrides[row.pig_id] || row.proposed_purpose || "";
}

function renderPurposeOptions(row) {
  const current = purposeValueForRow(row);
  const options = ['<option value="">Review first</option>'].concat(
    allowedPurposes.map((purpose) => `<option value="${escapeHtml(purpose)}"${purpose === current ? " selected" : ""}>${escapeHtml(purpose)}</option>`)
  );
  return `<select data-purpose-select="${escapeHtml(row.pig_id)}" ${row.review_status === "classified" ? "disabled" : ""}>${options.join("")}</select>`;
}

function statusClass(status) {
  if (status === "needs_owner_decision") return "status-pill status-pill-warning";
  if (status === "needs_data") return "status-pill status-pill-muted";
  return "status-pill";
}

function renderRows(rows) {
  updateSelectedCount();
  if (!rows.length) {
    countEl.textContent = "No pigs in this review view.";
    bodyEl.innerHTML = '<tr><td colspan="11" class="table-empty">No pigs match the selected filters.</td></tr>';
    return;
  }
  countEl.textContent = `Showing ${rows.length} of ${reviewRows.length} review row(s).`;
  bodyEl.innerHTML = rows.map((row) => {
    const canSelect = row.review_status !== "classified";
    const checked = selectedPigIds.has(row.pig_id) ? " checked" : "";
    const disabled = canSelect ? "" : " disabled";
    return `
      <tr>
        <td><input type="checkbox" data-purpose-check="${escapeHtml(row.pig_id)}"${checked}${disabled} /></td>
        <td>
          <a class="detail-link" href="/pig/${encodeURIComponent(row.pig_id)}">${escapeHtml(pigLabel(row))}</a>
          <span class="table-subtext">${escapeHtml(row.pig_id || "-")}</span>
        </td>
        <td>
          <span class="${statusClass(row.review_status)}">${escapeHtml(statusLabel(row.review_status))}</span>
          <span class="table-subtext">${escapeHtml(row.readiness_bucket || "-")}</span>
        </td>
        <td>
          <strong>${escapeHtml(row.suggested_purpose || "-")}</strong>
          <span class="table-subtext">Confidence: ${escapeHtml(row.suggested_purpose_confidence || "-")}</span>
          <span class="table-subtext">${escapeHtml(row.owner_action || "-")}</span>
        </td>
        <td>${renderPurposeOptions(row)}</td>
        <td>
          ${escapeHtml(row.suggested_purpose_reason || row.readiness_reason || "-")}
          <span class="table-subtext">${escapeHtml(row.recommended_action || "-")}</span>
        </td>
        <td>
          <strong>${escapeHtml(formatKg(row.latest_weight_kg))}</strong>
          <span class="table-subtext">${escapeHtml(row.growth_class || "Unknown")} / ${escapeHtml(formatAdg(row.average_daily_gain_kg))}</span>
          <span class="table-subtext">Post-wean: ${escapeHtml(formatAdg(row.post_wean_daily_gain_kg))}</span>
        </td>
        <td>
          <strong>${escapeHtml(formatKg(row.wean_weight_kg))}</strong>
          <span class="table-subtext">${row.wean_date ? `${escapeHtml(row.wean_date)} / ${escapeHtml(row.days_since_wean ?? "-")} days` : "No wean date"}</span>
        </td>
        <td>
          <a class="detail-link" href="/litter/${encodeURIComponent(row.litter_id)}">${escapeHtml(row.litter_id || "-")}</a>
          <span class="table-subtext">Sow ${escapeHtml(row.sow_tag_number || "--")} / ${escapeHtml(row.litter_quality || "Unknown")} / ${escapeHtml(formatPercent(row.litter_survival_rate))}</span>
        </td>
        <td>${escapeHtml(row.current_pen_name || row.current_pen_id || "-")}</td>
        <td>
          <div class="inline-action-group table-action-group">
            <button type="button" class="table-action-button" data-purpose-recheck="${escapeHtml(row.pig_id)}">Recheck</button>
          </div>
        </td>
      </tr>
    `;
  }).join("");
}

function applyFilters() {
  renderRows(filteredRows());
}

function updateSelectedCount() {
  selectedCountEl.textContent = `${selectedPigIds.size} selected`;
}

function selectedDecisions() {
  const byId = Object.fromEntries(reviewRows.map((row) => [row.pig_id, row]));
  const decisions = [];
  selectedPigIds.forEach((pigId) => {
    const row = byId[pigId];
    const purpose = purposeValueForRow(row || {});
    if (row && purpose) {
      decisions.push({
        pig_id: pigId,
        purpose,
        reason: row.suggested_purpose_reason || row.readiness_reason || "Herdmaster purpose review.",
      });
    }
  });
  return decisions;
}

async function submitPurposeDecisions(dryRun) {
  clearMessage();
  const decisions = selectedDecisions();
  if (!decisions.length) {
    showMessage("Select at least one row with an approval purpose.");
    return;
  }
  if (!dryRun && !window.confirm(`Apply purpose review for ${decisions.length} pig(s)?`)) {
    return;
  }
  try {
    const response = await fetch("/api/pig-weights/purpose-review/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ decisions, changed_by: "web_app", dry_run: dryRun }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.message || "Purpose review failed."]).join(" "));
    }
    showMessage(data.message || "Purpose review saved.", "success");
    if (!dryRun) {
      selectedPigIds.clear();
      await loadPurposeReview();
    }
  } catch (error) {
    console.error("Purpose review submit error:", error);
    showMessage(error.message || "Could not submit purpose review.");
  }
}

async function recheckPig(pigId) {
  clearMessage();
  recheckPanel.classList.remove("hidden");
  recheckPanel.innerHTML = "<p>Loading Herdmaster recheck...</p>";
  try {
    const response = await fetch("/api/pig-weights/purpose-review/recheck", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pig_id: pigId, question: "Recheck purpose recommendation from current data." }),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.message || "Recheck failed."]).join(" "));
    }
    const review = data.review || {};
    recheckPanel.innerHTML = `
      <div class="page-header section-header-compact">
        <div>
          <h2>Herdmaster Recheck</h2>
          <p>${escapeHtml(data.message || "No records were changed.")}</p>
        </div>
      </div>
      <div class="purpose-review-recheck-grid">
        <div><span>Pig</span><strong>${escapeHtml(pigLabel(review))}</strong></div>
        <div><span>Suggested</span><strong>${escapeHtml(review.suggested_purpose || "-")}</strong></div>
        <div><span>Approve As</span><strong>${escapeHtml(review.proposed_purpose || "Review first")}</strong></div>
        <div><span>Confidence</span><strong>${escapeHtml(review.suggested_purpose_confidence || "-")}</strong></div>
      </div>
      <ul class="purpose-review-points">
        ${(data.analysis_points || []).map((point) => `<li>${escapeHtml(point)}</li>`).join("")}
      </ul>
    `;
  } catch (error) {
    console.error("Purpose review recheck error:", error);
    recheckPanel.innerHTML = `<p class="ops-error-text">${escapeHtml(error.message || "Could not recheck this pig.")}</p>`;
  }
}

async function loadPurposeReview() {
  clearMessage();
  const litterId = queryLitterId();
  const url = litterId
    ? `/api/pig-weights/purpose-review?litter_id=${encodeURIComponent(litterId)}`
    : "/api/pig-weights/purpose-review";
  try {
    const response = await fetch(url);
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Could not load purpose review queue.");
    }
    reviewRows = data.pigs || [];
    allowedPurposes = data.allowed_purposes || [];
    subtitle.textContent = litterId
      ? `Herdmaster review for litter ${litterId}. Suggestions are advisory until approved.`
      : `Herdmaster review generated ${data.generated_date || "today"}. Suggestions are advisory until approved.`;
    renderSummary(data.summary || {});
    populateFilters(reviewRows);
    if (litterId && [...litterFilter.options].some((option) => option.value === litterId)) {
      litterFilter.value = litterId;
    }
    applyFilters();
  } catch (error) {
    console.error("Purpose review load error:", error);
    showMessage(error.message || "Something went wrong while loading purpose review.");
    bodyEl.innerHTML = '<tr><td colspan="11" class="table-empty">Could not load purpose review queue.</td></tr>';
  }
}

[statusFilter, litterFilter, suggestionFilter].forEach((select) => {
  select.addEventListener("change", applyFilters);
});

searchInput.addEventListener("input", applyFilters);

resetButton.addEventListener("click", () => {
  statusFilter.value = "";
  litterFilter.value = "";
  suggestionFilter.value = "";
  searchInput.value = "";
  applyFilters();
});

selectVisibleButton.addEventListener("click", () => {
  filteredRows().forEach((row) => {
    if (row.review_status !== "classified" && purposeValueForRow(row)) {
      selectedPigIds.add(row.pig_id);
    }
  });
  applyFilters();
});

clearSelectedButton.addEventListener("click", () => {
  selectedPigIds.clear();
  applyFilters();
});

previewSelectedButton.addEventListener("click", () => submitPurposeDecisions(true));
applySelectedButton.addEventListener("click", () => submitPurposeDecisions(false));

bodyEl.addEventListener("change", (event) => {
  const checkboxPigId = event.target.getAttribute("data-purpose-check");
  if (checkboxPigId) {
    if (event.target.checked) selectedPigIds.add(checkboxPigId);
    else selectedPigIds.delete(checkboxPigId);
    updateSelectedCount();
    return;
  }
  const purposePigId = event.target.getAttribute("data-purpose-select");
  if (purposePigId) {
    purposeOverrides[purposePigId] = event.target.value;
  }
});

bodyEl.addEventListener("click", (event) => {
  const pigId = event.target.getAttribute("data-purpose-recheck");
  if (pigId) {
    recheckPig(pigId);
  }
});
