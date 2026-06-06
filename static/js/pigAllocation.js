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

let allocationRows = [];
let allocationSummary = {};

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
  const tag = formatTagNumber(item.tag_number || item.pig_id || "-");
  return item.pig_id && item.pig_id !== item.tag_number
    ? `${tag} (${item.pig_id})`
    : tag;
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

function showMessage(message) {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add("message-error");
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
    bodyEl.innerHTML = '<tr><td colspan="14" class="table-empty">No pigs match the selected filters.</td></tr>';
    countEl.textContent = "No pigs in this view.";
    return;
  }

  countEl.textContent = `Showing ${rows.length} of ${allocationRows.length} pigs.`;
  bodyEl.innerHTML = rows.map((row) => {
    const profileHref = `/pig/${encodeURIComponent(row.pig_id)}`;
    const parentText = [row.mother_id, row.father_id].filter(Boolean).join(" / ");
    const linkText = row.existing_link || row.reserved_for_order_id || "-";
    return `
      <tr>
        <td>
          <a class="detail-link" href="${profileHref}">${escapeHtml(pigLabel(row))}</a>
          <span class="table-subtext">${escapeHtml(row.pig_id || "-")}</span>
        </td>
        <td><span class="${bucketClass(row.readiness_bucket)}">${escapeHtml(row.readiness_bucket || "-")}</span></td>
        <td>
          <strong>${escapeHtml(row.outlet_priority || "-")}</strong>
          <span class="table-subtext">${escapeHtml(row.recommended_action || "-")}</span>
          <span class="table-subtext">${escapeHtml(row.marketing_readiness || "-")}</span>
        </td>
        <td>${escapeHtml(row.readiness_reason || "-")}</td>
        <td>
          <strong>${escapeHtml(formatKg(row.latest_weight_kg))}</strong>
          <span class="table-subtext">${row.latest_weight_date ? `${escapeHtml(row.latest_weight_date)} / ${escapeHtml(row.days_since_weight ?? "-")} days` : "No weight date"}</span>
        </td>
        <td>
          <strong>${escapeHtml(row.growth_class || "Unknown")}</strong>
          <span class="table-subtext">${escapeHtml(row.growth_basis || "Lifetime ADG")}: ${escapeHtml(formatAdg(row.average_daily_gain_kg))}</span>
          <span class="table-subtext">Post-wean: ${escapeHtml(formatAdg(row.post_wean_daily_gain_kg))}</span>
        </td>
        <td>
          <strong>${escapeHtml(row.meat_window_status || "-")}</strong>
          <span class="table-subtext">Meat: ${escapeHtml(row.estimated_meat_ready_date || "-")} (${escapeHtml(row.days_until_meat_ready ?? "-")} days)</span>
          <span class="table-subtext">Abattoir: ${escapeHtml(row.estimated_abattoir_ready_date || "-")} (${escapeHtml(row.days_until_abattoir_ready ?? "-")} days)</span>
        </td>
        <td>
          <strong>${escapeHtml(formatKg(row.wean_weight_kg))}</strong>
          <span class="table-subtext">${row.wean_date ? `${escapeHtml(row.wean_date)} / ${escapeHtml(row.days_since_wean ?? "-")} days` : "No wean date"}</span>
        </td>
        <td>${escapeHtml(formatPen(row))}</td>
        <td>
          <strong>${escapeHtml(row.animal_type || "-")}</strong>
          <span class="table-subtext">${escapeHtml(row.sex || "-")}</span>
        </td>
        <td>${escapeHtml(row.purpose || "Unknown")}</td>
        <td>
          <strong>${escapeHtml(row.suggested_purpose || "-")}</strong>
          <span class="table-subtext">${escapeHtml(row.suggested_purpose_reason || "-")}</span>
          <span class="table-subtext">Confidence: ${escapeHtml(row.suggested_purpose_confidence || "-")}</span>
        </td>
        <td>
          <strong>${escapeHtml(row.litter_id || "-")}</strong>
          <span class="table-subtext">${escapeHtml(parentText || "No parent links")}</span>
          <span class="table-subtext">${escapeHtml(row.litter_quality || "Unknown")} / ${escapeHtml(formatPercent(row.litter_survival_rate))} survival</span>
        </td>
        <td>${escapeHtml(linkText)}</td>
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
    subtitle.textContent = `Read-only planning view generated ${data.generated_date || "today"}. No writes are made from this page.`;
    populateFilters(allocationRows);
    renderSummary(allocationSummary);
    renderRules(data.business_rules || {});
    applyFilters();
  } catch (error) {
    console.error("Pig allocation readiness error:", error);
    showMessage(error.message || "Something went wrong while loading pig allocation readiness.");
    bodyEl.innerHTML = '<tr><td colspan="14" class="table-empty">Could not load pig allocation readiness.</td></tr>';
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
