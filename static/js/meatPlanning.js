const messageBox = document.getElementById("meat_planning_message");
const subtitle = document.getElementById("meat_planning_subtitle");
const summaryEl = document.getElementById("meat_planning_summary");
const rulesEl = document.getElementById("meat_planning_rules");
const countEl = document.getElementById("meat_planning_count");
const bodyEl = document.getElementById("meat_planning_body");
const bucketFilter = document.getElementById("meat_bucket_filter");
const penFilter = document.getElementById("meat_pen_filter");
const searchFilter = document.getElementById("meat_search_filter");
const resetFiltersButton = document.getElementById("reset_meat_filters");
const demandNowInput = document.getElementById("demand_now_input");
const demand30Input = document.getElementById("demand_30_input");
const demandNowResult = document.getElementById("demand_now_result");
const demand30Result = document.getElementById("demand_30_result");
const demandScenarioNote = document.getElementById("demand_scenario_note");

let meatRows = [];
let meatSummary = {};

const BUCKET_LABELS = {
  ready_now: "Ready now",
  next_14_days: "Next 14 days",
  next_30_days: "Next 30 days",
  future: "Future",
  fallback_abattoir: "Fallback abattoir",
};

document.addEventListener("DOMContentLoaded", loadMeatPlanning);

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

function clearMessage() {
  messageBox.classList.add("hidden");
  messageBox.textContent = "";
  messageBox.classList.remove("message-success", "message-error");
}

function showMessage(message) {
  messageBox.classList.remove("hidden", "message-success", "message-error");
  messageBox.classList.add("message-error");
  messageBox.textContent = message;
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
    option.textContent = BUCKET_LABELS[value] || value;
    select.appendChild(option);
  });
  if (values.includes(currentValue)) {
    select.value = currentValue;
  }
}

function renderSummary(summary) {
  const items = [
    ["Meat pipeline", summary.meat_pipeline_count ?? 0],
    ["Ready now", summary.ready_now ?? 0],
    ["Next 14 days", summary.next_14_days ?? 0],
    ["Next 30 days", summary.next_30_days ?? 0],
    ["Future", summary.future ?? 0],
    ["Fallback abattoir", summary.fallback_abattoir ?? 0],
    ["Preorders now", summary.minimum_preorder_needed_now ?? 0],
    ["Preorders 30 days", summary.minimum_preorder_needed_30_days ?? 0],
  ];

  summaryEl.innerHTML = items.map(([label, value]) => `
    <div class="summary-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function numericInputValue(input) {
  const value = Number(input.value);
  if (Number.isNaN(value) || value < 0) {
    return 0;
  }
  return Math.floor(value);
}

function demandResultText(available, demand) {
  const difference = available - demand;
  if (demand === 0) {
    return `${available} available`;
  }
  if (difference >= 0) {
    return `${difference} surplus`;
  }
  return `${Math.abs(difference)} short`;
}

function renderDemandScenario() {
  const demandNow = numericInputValue(demandNowInput);
  const demand30 = numericInputValue(demand30Input);
  const readyNow = Number(meatSummary.ready_now || 0);
  const available30 = Number(meatSummary.minimum_preorder_needed_30_days || 0);
  const fallback = Number(meatSummary.fallback_abattoir || 0);

  demandNowResult.textContent = demandResultText(readyNow, demandNow);
  demand30Result.textContent = demandResultText(available30, demand30);

  if (demand30 > available30) {
    demandScenarioNote.textContent = "Demand is higher than the visible 30-day meat pipeline. More future pigs or preorder timing review would be needed.";
  } else if (demand30 > 0 && fallback > 0) {
    demandScenarioNote.textContent = `${fallback} pig(s) are already in fallback abattoir planning while this demand scenario is being tested.`;
  } else {
    demandScenarioNote.textContent = "Temporary calculation only. Nothing is saved or allocated.";
  }
}

function renderRules(rules) {
  if (!rules) {
    rulesEl.innerHTML = "";
    return;
  }

  const items = [
    ["Meat window", rules.meat_window_label],
    ["Abattoir window", rules.abattoir_window_label],
    ["Growth target", rules.target_growth_label],
    ["Rule source", rules.source],
  ].filter(([, value]) => value);

  rulesEl.innerHTML = items.map(([label, value]) => `
    <div class="allocation-rule">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function populateFilters(rows) {
  const bucketOrder = ["ready_now", "next_14_days", "next_30_days", "future", "fallback_abattoir"];
  setSelectOptions(bucketFilter, bucketOrder.filter((bucket) => rows.some((row) => row.planning_bucket === bucket)), "All buckets");
  setSelectOptions(penFilter, uniqueOptions(rows, formatPen), "All pens");
}

function rowSearchText(row) {
  return [
    row.pig_id,
    row.tag_number,
    row.planning_bucket,
    BUCKET_LABELS[row.planning_bucket],
    row.meat_window_status,
    row.estimated_meat_ready_date,
    row.estimated_abattoir_ready_date,
    row.growth_class,
    row.suggested_purpose,
    row.suggested_purpose_reason,
    row.outlet_priority,
    row.recommended_action,
    row.current_pen_name,
    row.current_pen_id,
    row.litter_id,
    row.litter_quality,
    row.sex,
    row.animal_type,
  ].join(" ").toLowerCase();
}

function filteredRows() {
  const bucket = bucketFilter.value;
  const pen = penFilter.value;
  const search = searchFilter.value.trim().toLowerCase();

  return meatRows.filter((row) => {
    if (bucket && row.planning_bucket !== bucket) return false;
    if (pen && formatPen(row) !== pen) return false;
    if (search && !rowSearchText(row).includes(search)) return false;
    return true;
  });
}

function renderRows(rows) {
  if (!rows.length) {
    bodyEl.innerHTML = '<tr><td colspan="8" class="table-empty">No pigs match this meat planning view.</td></tr>';
    countEl.textContent = "No pigs in this view.";
    return;
  }

  countEl.textContent = `Showing ${rows.length} of ${meatRows.length} planning rows.`;
  bodyEl.innerHTML = rows.map((row) => {
    const profileHref = `/pig/${encodeURIComponent(row.pig_id)}`;
    return `
      <tr>
        <td>
          <a class="detail-link" href="${profileHref}">${escapeHtml(pigLabel(row))}</a>
          <span class="table-subtext">${escapeHtml(row.pig_id || "-")}</span>
        </td>
        <td><span class="status-pill">${escapeHtml(BUCKET_LABELS[row.planning_bucket] || row.planning_bucket || "-")}</span></td>
        <td>
          <strong>${escapeHtml(row.meat_window_status || "-")}</strong>
          <span class="table-subtext">${escapeHtml(row.estimated_meat_ready_date || "-")} (${escapeHtml(row.days_until_meat_ready ?? "-")} days)</span>
        </td>
        <td>
          <strong>${escapeHtml(row.estimated_abattoir_ready_date || "-")}</strong>
          <span class="table-subtext">${escapeHtml(row.days_until_abattoir_ready ?? "-")} days until abattoir target</span>
        </td>
        <td>
          <strong>${escapeHtml(formatKg(row.latest_weight_kg))}</strong>
          <span class="table-subtext">${escapeHtml(row.growth_class || "-")} / ${escapeHtml(formatAdg(row.average_daily_gain_kg))}</span>
          <span class="table-subtext">${escapeHtml(row.latest_weight_date || "No weight date")}</span>
        </td>
        <td>
          <strong>${escapeHtml(row.outlet_priority || "-")}</strong>
          <span class="table-subtext">${escapeHtml(row.recommended_action || "-")}</span>
          <span class="table-subtext">${escapeHtml(row.marketing_readiness || "-")}</span>
        </td>
        <td>${escapeHtml(formatPen(row))}</td>
        <td>
          <strong>${escapeHtml(row.litter_id || "-")}</strong>
          <span class="table-subtext">${escapeHtml(row.litter_quality || "Unknown")} / ${escapeHtml(formatPercent(row.litter_survival_rate))}</span>
        </td>
      </tr>
    `;
  }).join("");
}

function applyFilters() {
  renderRows(filteredRows());
}

async function loadMeatPlanning() {
  clearMessage();
  try {
    const response = await fetch("/api/pig-weights/meat-planning");
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Could not load meat planning.");
    }

    meatRows = data.pigs || [];
    subtitle.textContent = `Read-only meat planning generated ${data.generated_date || "today"}. No writes are made from this page.`;
    meatSummary = data.summary || {};
    renderSummary(meatSummary);
    renderRules(data.business_rules || {});
    populateFilters(meatRows);
    renderDemandScenario();
    applyFilters();
  } catch (error) {
    console.error("Meat planning error:", error);
    showMessage(error.message || "Something went wrong while loading meat planning.");
    bodyEl.innerHTML = '<tr><td colspan="8" class="table-empty">Could not load meat planning.</td></tr>';
  }
}

[bucketFilter, penFilter].forEach((select) => {
  select.addEventListener("change", applyFilters);
});

searchFilter.addEventListener("input", applyFilters);
demandNowInput.addEventListener("input", renderDemandScenario);
demand30Input.addEventListener("input", renderDemandScenario);

resetFiltersButton.addEventListener("click", () => {
  bucketFilter.value = "";
  penFilter.value = "";
  searchFilter.value = "";
  applyFilters();
});
