const messageBox = document.getElementById("allocation_message");
const subtitle = document.getElementById("allocation_subtitle");
const summaryEl = document.getElementById("allocation_summary");
const rulesEl = document.getElementById("allocation_rules");
const countEl = document.getElementById("allocation_count");
const bodyEl = document.getElementById("allocation_body");
const bucketFilter = document.getElementById("bucket_filter");
const penFilter = document.getElementById("pen_filter");
const typeFilter = document.getElementById("type_filter");
const sexFilter = document.getElementById("sex_filter");
const purposeFilter = document.getElementById("purpose_filter");
const searchFilter = document.getElementById("search_filter");
const resetFiltersButton = document.getElementById("reset_allocation_filters");
const reviewPanel = document.getElementById("allocation_review_panel");
const reviewStatus = document.getElementById("allocation_review_status");
const reviewDetail = document.getElementById("allocation_review_detail");

let allocationRows = [];
let allocationSummary = {};
let selectedReviewPigId = "";
let latestAllocationPurposePreview = null;

const ALLOCATION_PURPOSE_OPTIONS = [
  ["Grow_Out", "Grow out / meat pipeline"],
  ["Sale", "Livestock sale"],
  ["Breeding", "Breeding"],
  ["Replacement", "Replacement"],
  ["House_Use", "House use"],
  ["Unknown", "Needs more data"],
];

const SUGGESTED_PURPOSE_MAP = {
  "Grow Out": "Grow_Out",
  "Livestock Sale": "Sale",
  Meat: "Grow_Out",
  "Abattoir Slaughter": "Grow_Out",
  "Breeding Review": "Breeding",
};

const BUCKET_ORDER = [
  "Needs Data",
  "Needs Classification",
  "Growing",
  "Livestock Candidate",
  "Slaughter Candidate",
  "Meat Candidate",
  "Retain / Breeding Candidate",
  "Allocated",
  "Exited",
];

document.addEventListener("DOMContentLoaded", loadAllocationReadiness);

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

function pigLabel(item) {
  return formatTagNumber(item.tag_number || item.pig_id || "-");
}

function formatKg(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(1)} kg`;
}

function formatAdg(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Number(value).toFixed(3)} kg/day`;
}

function formatPercent(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return `${Math.round(Number(value) * 100)}%`;
}

function formatPen(item) {
  return item.current_pen_name || item.current_pen_id || "-";
}

function showMessage(message, type = "error") {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add(type === "success" ? "message-success" : "message-error");
  messageBox.textContent = message;
}

function clearMessage() {
  messageBox.classList.add("hidden");
  messageBox.textContent = "";
  messageBox.classList.remove("message-success", "message-error");
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
    option.textContent = value;
    select.appendChild(option);
  });
  if (values.includes(currentValue)) {
    select.value = currentValue;
  }
}

function populateFilters(rows) {
  setSelectOptions(bucketFilter, BUCKET_ORDER.filter((bucket) => rows.some((row) => row.readiness_bucket === bucket)), "All buckets");
  setSelectOptions(penFilter, uniqueOptions(rows, formatPen), "All pens");
  setSelectOptions(typeFilter, uniqueOptions(rows, (row) => row.animal_type), "All types");
  setSelectOptions(sexFilter, uniqueOptions(rows, (row) => row.sex), "All sexes");
  setSelectOptions(purposeFilter, uniqueOptions(rows, (row) => row.purpose || "Unknown"), "All purposes");
}

function renderSummary(summary) {
  const buckets = summary.buckets || {};
  const items = [
    ["Total", summary.total ?? 0],
    ...BUCKET_ORDER.map((bucket) => [bucket, buckets[bucket] ?? 0]),
  ];

  summaryEl.innerHTML = items.map(([label, value]) => `
    <div class="summary-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function renderRules(rules) {
  if (!rules) {
    rulesEl.innerHTML = "";
    return;
  }

  const items = [
    ["Meat window", rules.meat_window_label],
    ["Abattoir window", rules.abattoir_window_label],
    ["Livestock sale", rules.live_sale_label],
    ["Growth target", rules.target_growth_label],
    ["Slow-growth trigger", rules.slow_growth_label],
    ["Good litter", rules.good_litter_label],
    ["Stale weight", rules.stale_weight_label],
    ["Rule source", rules.source],
  ].filter(([, value]) => value);

  rulesEl.innerHTML = items.map(([label, value]) => `
    <div class="allocation-rule">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function rowSearchText(row) {
  return [
    row.pig_id,
    row.tag_number,
    row.readiness_bucket,
    row.readiness_reason,
    row.outlet_priority,
    row.recommended_action,
    row.marketing_readiness,
    row.growth_class,
    row.growth_reason,
    row.meat_window_status,
    row.abattoir_window_status,
    row.estimated_meat_ready_date,
    row.estimated_abattoir_ready_date,
    row.litter_quality,
    row.litter_quality_reason,
    row.current_pen_name,
    row.current_pen_id,
    row.animal_type,
    row.sex,
    row.purpose,
    row.suggested_purpose,
    row.suggested_purpose_reason,
    row.suggested_purpose_confidence,
    row.litter_id,
    row.mother_id,
    row.father_id,
    row.existing_link,
  ].join(" ").toLowerCase();
}

function filteredRows() {
  const bucket = bucketFilter.value;
  const pen = penFilter.value;
  const type = typeFilter.value;
  const sex = sexFilter.value;
  const purpose = purposeFilter.value;
  const search = searchFilter.value.trim().toLowerCase();

  return allocationRows.filter((row) => {
    if (bucket && row.readiness_bucket !== bucket) return false;
    if (pen && formatPen(row) !== pen) return false;
    if (type && row.animal_type !== type) return false;
    if (sex && row.sex !== sex) return false;
    if (purpose && (row.purpose || "Unknown") !== purpose) return false;
    if (search && !rowSearchText(row).includes(search)) return false;
    return true;
  });
}

function storedPurposeForSuggestion(row) {
  const suggested = row && row.suggested_purpose ? String(row.suggested_purpose).trim() : "";
  return SUGGESTED_PURPOSE_MAP[suggested] || "";
}

function selectedReviewRow() {
  return allocationRows.find((item) => item.pig_id === selectedReviewPigId) || null;
}

function currentReviewPurpose() {
  const select = document.getElementById("allocation_review_purpose_choice");
  return select ? select.value : "";
}

function allocationReviewNote() {
  const note = document.getElementById("allocation_review_note");
  return note ? note.value.trim() : "";
}

function allocationReviewChangedBy() {
  const changedBy = document.getElementById("allocation_review_changed_by");
  return changedBy && changedBy.value.trim() ? changedBy.value.trim() : "web_app";
}

function resetAllocationReviewPreview() {
  latestAllocationPurposePreview = null;
  const preview = document.getElementById("allocation_review_preview");
  const applyButton = document.querySelector("[data-allocation-review-apply]");
  if (preview) {
    preview.innerHTML = '<p class="form-helper">Preview the purpose update before applying it.</p>';
  }
  if (applyButton) {
    applyButton.disabled = true;
  }
}

function allocationPurposeDecisionPayload(dryRun) {
  const row = selectedReviewRow();
  const purpose = currentReviewPurpose();
  if (!row || !row.pig_id) {
    throw new Error("Select a pig before previewing a purpose update.");
  }
  if (!purpose) {
    throw new Error("Choose a purpose before previewing the update.");
  }
  return {
    decisions: [{
      pig_id: row.pig_id,
      purpose,
      reason: row.suggested_purpose_reason || row.readiness_reason || "Pig Allocation owner purpose review.",
      note: allocationReviewNote(),
    }],
    changed_by: allocationReviewChangedBy(),
    dry_run: dryRun,
    allow_reclassify: true,
  };
}

function renderAllocationPurposePreview(data) {
  const preview = document.getElementById("allocation_review_preview");
  const applyButton = document.querySelector("[data-allocation-review-apply]");
  if (!preview) return;
  const approved = Array.isArray(data.approved) ? data.approved : [];
  const planned = data.planned_updates || {};
  const items = approved.map((item) => {
    const update = planned[item.pig_id] || {};
    return `
      <div class="allocation-review-preview-item">
        <strong>${escapeHtml(item.tag_number || item.pig_id || "-")}</strong>
        <span>${escapeHtml(item.old_purpose || "Unknown")} -> ${escapeHtml(item.new_purpose || "-")}</span>
        <small>${escapeHtml(update.General_Notes || item.reason || "No audit note returned.")}</small>
      </div>
    `;
  }).join("");

  preview.innerHTML = `
    <div class="allocation-review-preview-success">
      <strong>${escapeHtml(data.message || "Purpose review preview ready.")}</strong>
      ${items || '<p class="form-helper">No update row returned by the preview.</p>'}
    </div>
  `;
  if (applyButton) {
    applyButton.disabled = !data.success;
  }
}

async function submitAllocationPurposeDecision(dryRun) {
  clearMessage();
  const preview = document.getElementById("allocation_review_preview");
  const previewButton = document.querySelector("[data-allocation-review-preview]");
  const applyButton = document.querySelector("[data-allocation-review-apply]");
  if (!dryRun && !latestAllocationPurposePreview) {
    showMessage("Preview the purpose update before applying it.");
    return;
  }
  if (!dryRun && !window.confirm("Apply this purpose update to the selected pig?")) {
    return;
  }
  try {
    if (previewButton) previewButton.disabled = true;
    if (applyButton) applyButton.disabled = true;
    if (preview) {
      preview.innerHTML = `<p class="form-helper">${dryRun ? "Previewing" : "Applying"} purpose update...</p>`;
    }
    const response = await fetch("/api/pig-weights/purpose-review/apply", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(allocationPurposeDecisionPayload(dryRun)),
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error((data.errors || [data.message || "Purpose review failed."]).join(" "));
    }
    if (dryRun) {
      latestAllocationPurposePreview = data;
      renderAllocationPurposePreview(data);
      showMessage("Purpose update preview is ready. Review it, then apply if correct.", "success");
      return;
    }
    latestAllocationPurposePreview = null;
    showMessage(data.message || "Purpose review saved.", "success");
    const pigId = selectedReviewPigId;
    await loadAllocationReadiness();
    selectedReviewPigId = pigId;
    renderPurposeReview(selectedReviewRow());
  } catch (error) {
    console.error("Allocation purpose review submit error:", error);
    latestAllocationPurposePreview = null;
    if (preview) {
      preview.innerHTML = `<p class="form-helper">${escapeHtml(error.message || "Could not submit purpose review.")}</p>`;
    }
    showMessage(error.message || "Could not submit purpose review.");
  } finally {
    if (previewButton) previewButton.disabled = false;
    if (applyButton) applyButton.disabled = !latestAllocationPurposePreview;
  }
}

function renderPurposeReview(row) {
  if (!reviewDetail || !reviewStatus) return;
  latestAllocationPurposePreview = null;
  if (!row) {
    reviewStatus.textContent = "Select a pig from the table to inspect the recommendation before any purpose decision.";
    reviewDetail.innerHTML = '<div class="table-empty">No pig selected. Use Review on a table row to open a recommendation packet.</div>';
    return;
  }

  reviewStatus.textContent = `${pigLabel(row)} selected for purpose review. Preview the exact write before applying any change.`;
  const mappedPurpose = storedPurposeForSuggestion(row) || row.purpose || "Unknown";
  reviewDetail.innerHTML = `
    <div class="allocation-review-grid">
      <div class="allocation-review-primary">
        <span>Selected Pig</span>
        <strong>${escapeHtml(pigLabel(row))}</strong>
        <small>${escapeHtml(row.pig_id || "-")}</small>
      </div>
      <div>
        <span>Recommendation</span>
        <strong>${escapeHtml(row.suggested_purpose || row.outlet_priority || "Review")}</strong>
        <small>${escapeHtml(row.suggested_purpose_confidence || "confidence not supplied")}</small>
      </div>
      <div>
        <span>Latest Weight</span>
        <strong>${escapeHtml(formatKg(row.latest_weight_kg))}</strong>
        <small>${row.latest_weight_date ? `${escapeHtml(row.latest_weight_date)} / ${escapeHtml(row.days_since_weight ?? "-")} days` : "No weight date"}</small>
      </div>
      <div>
        <span>Current Purpose</span>
        <strong>${escapeHtml(row.purpose || "Unknown")}</strong>
        <small>${escapeHtml(row.readiness_bucket || "-")}</small>
      </div>
      <div>
        <span>Weaning</span>
        <strong>${escapeHtml(formatKg(row.wean_weight_kg))}</strong>
        <small>${row.wean_date ? `${escapeHtml(row.wean_date)} / ${escapeHtml(row.days_since_wean ?? "-")} days` : "No wean date"}</small>
      </div>
      <div>
        <span>Growth</span>
        <strong>${escapeHtml(row.growth_class || "Unknown")}</strong>
        <small>${escapeHtml(row.growth_reason || "No growth reason supplied.")}</small>
      </div>
      <div>
        <span>Timing</span>
        <strong>${escapeHtml(row.meat_window_status || "-")}</strong>
        <small>Meat ${escapeHtml(row.estimated_meat_ready_date || "-")} / Abattoir ${escapeHtml(row.estimated_abattoir_ready_date || "-")}</small>
      </div>
      <div>
        <span>Pen / Litter</span>
        <strong>${escapeHtml(formatPen(row))}</strong>
        <small>${escapeHtml(row.litter_id || "No litter")} / ${escapeHtml(row.litter_quality || "Unknown")}</small>
      </div>
    </div>
    <div class="allocation-review-reason">
      <span>Why this recommendation</span>
      <p>${escapeHtml(row.suggested_purpose_reason || row.readiness_reason || "No recommendation reason supplied.")}</p>
    </div>
    <div class="allocation-review-options">
      <label for="allocation_review_purpose_choice">Draft purpose option</label>
      <select id="allocation_review_purpose_choice">
        ${ALLOCATION_PURPOSE_OPTIONS.map(([value, label]) => `<option value="${escapeHtml(value)}"${value === mappedPurpose ? " selected" : ""}>${escapeHtml(label)} (${escapeHtml(value)})</option>`).join("")}
      </select>
      <label for="allocation_review_note">Owner note</label>
      <textarea id="allocation_review_note" rows="3" placeholder="Optional note for why you accepted or changed this purpose."></textarea>
      <label for="allocation_review_changed_by">Changed by</label>
      <input id="allocation_review_changed_by" type="text" value="web_app" />
      <div class="allocation-review-actions">
        <button type="button" class="btn-secondary" data-allocation-review-preview>Preview update</button>
        <button type="button" class="btn-primary" data-allocation-review-apply disabled>Apply purpose</button>
        <a class="button-link" href="/purpose-review">Open full queue</a>
      </div>
      <div id="allocation_review_preview" class="allocation-review-preview">
        <p class="form-helper">Preview the purpose update before applying it. This writes only the pig Purpose, Updated At, and audit note.</p>
      </div>
    </div>
  `;
}
function bucketClass(bucket) {
  const normalized = String(bucket || "").toLowerCase();
  if (normalized.includes("needs")) return "status-pill status-pill-warning";
  if (normalized.includes("candidate")) return "status-pill";
  if (normalized.includes("allocated")) return "status-pill status-pill-muted";
  if (normalized.includes("exited")) return "status-pill status-pill-muted";
  return "status-pill status-pill-muted";
}

function renderRows(rows) {
  if (!rows.length) {
    bodyEl.innerHTML = '<tr><td colspan="9" class="table-empty">No pigs match the selected filters.</td></tr>';
    countEl.textContent = "No pigs in this view.";
    return;
  }

  countEl.textContent = `Showing ${rows.length} of ${allocationRows.length} pigs.`;
  bodyEl.innerHTML = rows.map((row) => {
    const profileHref = `/pig/${encodeURIComponent(row.pig_id)}`;
    const parentText = [row.mother_id, row.father_id].filter(Boolean).join(" / ");
    const linkText = row.existing_link || row.reserved_for_order_id || "-";
    const typeSex = [row.animal_type, row.sex].filter(Boolean).join(" / ") || "-";
    return `
      <tr>
        <td class="allocation-pig-cell" data-label="Pig">
          <a class="detail-link allocation-pig-link" href="${profileHref}">${escapeHtml(pigLabel(row))}</a>
          <span class="table-subtext">${escapeHtml(typeSex)}</span>
        </td>
        <td data-label="Bucket"><span class="${bucketClass(row.readiness_bucket)}">${escapeHtml(row.readiness_bucket || "-")}</span></td>
        <td class="allocation-review-cell" data-label="Review">
          <button type="button" class="button-link button-link-secondary allocation-review-button" data-review-pig-id="${escapeHtml(row.pig_id || "")}">Review</button>
          <details class="allocation-row-details">
            <summary>More</summary>
            <span>Purpose confidence: ${escapeHtml(row.suggested_purpose_confidence || "-")}</span>
            <span>Suggested reason: ${escapeHtml(row.suggested_purpose_reason || "-")}</span>
            <span>Wean: ${row.wean_date ? `${escapeHtml(row.wean_date)} / ${escapeHtml(row.days_since_wean ?? "-")} days` : "No wean date"}</span>
            <span>Parents: ${escapeHtml(parentText || "No parent links")}</span>
            <span>Litter quality: ${escapeHtml(row.litter_quality || "Unknown")} / ${escapeHtml(formatPercent(row.litter_survival_rate))} survival</span>
            <span>Existing link: ${escapeHtml(linkText)}</span>
            <span>Pig ID: ${escapeHtml(row.pig_id || "-")}</span>
          </details>
        </td>
        <td class="allocation-action-cell" data-label="Action / Reason">
          <strong>${escapeHtml(row.outlet_priority || "-")}</strong>
          <span class="table-subtext">${escapeHtml(row.recommended_action || "-")}</span>
          <span class="table-subtext allocation-clamp">${escapeHtml(row.readiness_reason || "-")}</span>
        </td>
        <td data-label="Weight">
          <strong>${escapeHtml(formatKg(row.latest_weight_kg))}</strong>
          <span class="table-subtext">${row.latest_weight_date ? `${escapeHtml(row.latest_weight_date)} / ${escapeHtml(row.days_since_weight ?? "-")} days` : "No weight date"}</span>
          <span class="table-subtext">Wean: ${escapeHtml(formatKg(row.wean_weight_kg))}</span>
        </td>
        <td data-label="Growth">
          <strong>${escapeHtml(row.growth_class || "Unknown")}</strong>
          <span class="table-subtext">${escapeHtml(row.growth_basis || "Lifetime ADG")}: ${escapeHtml(formatAdg(row.average_daily_gain_kg))}</span>
          <span class="table-subtext">Post-wean: ${escapeHtml(formatAdg(row.post_wean_daily_gain_kg))}</span>
        </td>
        <td data-label="Timing">
          <strong>${escapeHtml(row.meat_window_status || "-")}</strong>
          <span class="table-subtext">Meat: ${escapeHtml(row.estimated_meat_ready_date || "-")} (${escapeHtml(row.days_until_meat_ready ?? "-")} days)</span>
          <span class="table-subtext">Abattoir: ${escapeHtml(row.estimated_abattoir_ready_date || "-")} (${escapeHtml(row.days_until_abattoir_ready ?? "-")} days)</span>
        </td>
        <td data-label="Pen">
          <strong>${escapeHtml(formatPen(row))}</strong>
          <span class="table-subtext">${escapeHtml(row.litter_id || "No litter")}</span>
        </td>
        <td data-label="Purpose">
          <strong>${escapeHtml(row.purpose || "Unknown")}</strong>
          <span class="table-subtext">Suggested: ${escapeHtml(row.suggested_purpose || "-")}</span>
          <span class="table-subtext">${escapeHtml(row.marketing_readiness || "-")}</span>
        </td>
      </tr>
    `;
  }).join("");
}

function applyFilters() {
  renderRows(filteredRows());
}

async function loadAllocationReadiness() {
  clearMessage();
  try {
    const response = await fetch("/api/pig-weights/pig-allocation-readiness");
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Could not load pig allocation readiness.");
    }
    allocationRows = data.pigs || [];
    allocationSummary = data.summary || {};
    subtitle.textContent = `Planning view generated ${data.generated_date || "today"}. Purpose changes require preview and confirmation.`;
    populateFilters(allocationRows);
    renderSummary(allocationSummary);
    renderRules(data.business_rules || {});
    applyFilters();
  } catch (error) {
    console.error("Pig allocation readiness error:", error);
    showMessage(error.message || "Something went wrong while loading pig allocation readiness.");
    bodyEl.innerHTML = '<tr><td colspan="9" class="table-empty">Could not load pig allocation readiness.</td></tr>';
  }
}

[bucketFilter, penFilter, typeFilter, sexFilter, purposeFilter].forEach((select) => {
  select.addEventListener("change", applyFilters);
});

searchFilter.addEventListener("input", applyFilters);

resetFiltersButton.addEventListener("click", () => {
  bucketFilter.value = "";
  penFilter.value = "";
  typeFilter.value = "";
  sexFilter.value = "";
  purposeFilter.value = "";
  searchFilter.value = "";
  applyFilters();
});


bodyEl.addEventListener("click", (event) => {
  const button = event.target.closest("[data-review-pig-id]");
  if (!button) return;
  selectedReviewPigId = button.dataset.reviewPigId || "";
  const row = allocationRows.find((item) => item.pig_id === selectedReviewPigId);
  renderPurposeReview(row || null);
  if (reviewPanel && typeof reviewPanel.scrollIntoView === "function") {
    reviewPanel.scrollIntoView({ behavior: "smooth", block: "start" });
  }
});

if (reviewDetail) {
  reviewDetail.addEventListener("click", (event) => {
    if (event.target.closest("[data-allocation-review-preview]")) {
      submitAllocationPurposeDecision(true);
      return;
    }
    if (event.target.closest("[data-allocation-review-apply]")) {
      submitAllocationPurposeDecision(false);
    }
  });

  reviewDetail.addEventListener("input", (event) => {
    if (event.target.closest("#allocation_review_purpose_choice, #allocation_review_note, #allocation_review_changed_by")) {
      resetAllocationReviewPreview();
    }
  });

  reviewDetail.addEventListener("change", (event) => {
    if (event.target.closest("#allocation_review_purpose_choice, #allocation_review_note, #allocation_review_changed_by")) {
      resetAllocationReviewPreview();
    }
  });
}
