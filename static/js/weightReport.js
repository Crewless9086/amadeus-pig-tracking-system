const dateFromInput = document.getElementById("date_from");
const dateToInput = document.getElementById("date_to");
const penFilterSelect = document.getElementById("pen_filter");
const reportForm = document.getElementById("weight_report_filters");
const todayButton = document.getElementById("today_button");
const printButton = document.getElementById("print_report_button");
const messageBox = document.getElementById("weight_report_message");
const summaryEl = document.getElementById("weight_report_summary");
const penSummaryBody = document.getElementById("pen_summary_body");
const detailBody = document.getElementById("weight_detail_body");
const printRangeEl = document.getElementById("print_report_range");

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

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  return Number(value).toFixed(decimals);
}

function formatKg(value, decimals = 2) {
  const formatted = formatNumber(value, decimals);
  return formatted === "-" ? "-" : `${formatted} kg`;
}

function formatSignedKg(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  const number = Number(value);
  return `${number >= 0 ? "+" : ""}${number.toFixed(2)} kg`;
}

function formatGrowth(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "-";
  }
  const number = Number(value);
  return `${number >= 0 ? "+" : ""}${number.toFixed(3)} kg/day`;
}

function valueClass(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) return "neutral-text";
  const number = Number(value);
  if (number > 0) return "good-text";
  if (number < 0) return "bad-text";
  return "neutral-text";
}

function formatPen(item) {
  const name = item.current_pen_name || item.pen_name || "";
  const id = item.current_pen_id || item.pen_id || "";
  if (name && id) return `${name} (${id})`;
  return name || id || "-";
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

function renderSummary(summary) {
  const items = [
    ["Entries", summary.total_entries ?? 0],
    ["Pigs Weighed", summary.unique_pigs ?? 0],
    ["Avg Weight", formatKg(summary.average_weight_kg)],
    ["Avg Change", formatSignedKg(summary.average_difference_kg)],
    ["Avg Growth/day", formatGrowth(summary.average_growth_rate_kg_day)],
    ["Loss Flags", summary.weight_loss_count ?? 0],
  ];

  summaryEl.innerHTML = items.map(([label, value]) => `
    <div class="summary-metric">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `).join("");
}

function renderPenSummary(rows) {
  if (!rows.length) {
    penSummaryBody.innerHTML = `<tr><td colspan="6" class="table-empty">No pen totals for this date range.</td></tr>`;
    return;
  }

  penSummaryBody.innerHTML = rows.map((item) => `
    <tr>
      <td>${escapeHtml(formatPen(item))}</td>
      <td>${escapeHtml(item.entry_count ?? 0)}</td>
      <td>${escapeHtml(item.unique_pigs ?? 0)}</td>
      <td>${escapeHtml(formatKg(item.average_weight_kg))}</td>
      <td class="${valueClass(item.average_difference_kg)}">${escapeHtml(formatSignedKg(item.average_difference_kg))}</td>
      <td class="${Number(item.weight_loss_count || 0) > 0 ? "bad-text" : "neutral-text"}">${escapeHtml(item.weight_loss_count ?? 0)}</td>
    </tr>
  `).join("");
}

function renderDetails(rows) {
  if (!rows.length) {
    detailBody.innerHTML = `<tr><td colspan="9" class="table-empty">No active on-farm pig weights found for this date range.</td></tr>`;
    return;
  }

  detailBody.innerHTML = rows.map((item) => `
    <tr>
      <td>${escapeHtml(item.weight_date || "-")}</td>
      <td>${escapeHtml(item.tag_number || item.pig_id || "-")}</td>
      <td>${escapeHtml(formatPen(item))}</td>
      <td>${escapeHtml(formatKg(item.weight_kg))}</td>
      <td>${escapeHtml(formatKg(item.previous_weight_kg))}</td>
      <td class="${valueClass(item.difference_kg)}">${escapeHtml(formatSignedKg(item.difference_kg))}</td>
      <td class="${valueClass(item.growth_rate_kg_day)}">${escapeHtml(formatGrowth(item.growth_rate_kg_day))}</td>
      <td>${escapeHtml(item.calculated_stage || item.weight_band || "-")}</td>
      <td>${escapeHtml(item.condition_notes || "-")}</td>
    </tr>
  `).join("");
}

async function loadPens() {
  const response = await fetch("/api/pig-weights/pens");
  const data = await response.json();
  const pens = data.pens || [];

  penFilterSelect.innerHTML = `<option value="">All pens</option>`;
  pens.forEach((pen) => {
    const option = document.createElement("option");
    option.value = pen.pen_id || "";
    option.textContent = pen.pen_name ? `${pen.pen_name} (${pen.pen_id})` : (pen.pen_id || "");
    penFilterSelect.appendChild(option);
  });
}

async function loadReport() {
  clearMessage();

  const params = new URLSearchParams();
  params.set("date_from", dateFromInput.value);
  params.set("date_to", dateToInput.value);
  if (penFilterSelect.value) params.set("pen_id", penFilterSelect.value);

  try {
    const response = await fetch(`/api/pig-weights/weight-report?${params.toString()}`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      const errorMessage = data.errors ? data.errors.join(" ") : "Failed to load weight report.";
      throw new Error(errorMessage);
    }

    printRangeEl.textContent = `${data.date_from} to ${data.date_to}`;
    renderSummary(data.summary || {});
    renderPenSummary(data.pen_summary || []);
    renderDetails(data.entries || []);
  } catch (error) {
    console.error("Weight report error:", error);
    setMessage(error.message || "Something went wrong while loading the weight report.");
  }
}

function setTodayRange() {
  const today = todayIso();
  dateFromInput.value = today;
  dateToInput.value = today;
}

reportForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  await loadReport();
});

todayButton.addEventListener("click", async () => {
  setTodayRange();
  await loadReport();
});

printButton.addEventListener("click", () => {
  window.print();
});

(async function initPage() {
  setTodayRange();
  await loadPens();
  await loadReport();
})();
