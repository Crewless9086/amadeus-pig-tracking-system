const messageBox = document.getElementById("sales_dashboard_message");
const periodLabel = document.getElementById("sales_overview_period_label");
const periodFilter = document.getElementById("sales_period_filter");
const monthFilter = document.getElementById("sales_month_filter");
const yearFilter = document.getElementById("sales_year_filter");
const streamFilter = document.getElementById("sales_stream_filter");
const fromFilter = document.getElementById("sales_from_filter");
const toFilter = document.getElementById("sales_to_filter");
const resetFiltersButton = document.getElementById("reset_sales_filters");
const transactionsBody = document.getElementById("sales_transactions_body");
const transactionsCount = document.getElementById("sales_transactions_count");
const totalsGrid = document.getElementById("sales_totals_grid");
const summaryList = document.getElementById("sales_summary_list");

let allTransactions = [];

document.addEventListener("DOMContentLoaded", async () => {
  setDefaultFilters();
  await Promise.all([
    loadSalesTransactions(),
    loadStockAvailability(),
  ]);
});

function setDefaultFilters() {
  const today = new Date();
  const year = today.getFullYear();
  const month = String(today.getMonth() + 1).padStart(2, "0");
  monthFilter.value = `${year}-${month}`;
  yearFilter.value = String(year);
  applyPeriodDefaults();
}

function money(value) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "R0.00";
  }
  return `R${Number(value).toFixed(2)}`;
}

function dateOnly(value) {
  if (!value) return "";
  return String(value).slice(0, 10);
}

function parseDate(value) {
  if (!value) return null;
  const parsed = new Date(`${dateOnly(value)}T00:00:00`);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

function streamKey(stream) {
  return String(stream || "").trim().toLowerCase();
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

function applyPeriodDefaults() {
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth();
  let from = "";
  let to = "";

  if (periodFilter.value === "this_month") {
    from = new Date(year, month, 1);
    to = new Date(year, month + 1, 0);
  } else if (periodFilter.value === "last_month") {
    from = new Date(year, month - 1, 1);
    to = new Date(year, month, 0);
  } else if (periodFilter.value === "this_year") {
    from = new Date(year, 0, 1);
    to = new Date(year, 11, 31);
  } else if (periodFilter.value === "selected_month" && monthFilter.value) {
    const [selectedYear, selectedMonth] = monthFilter.value.split("-").map(Number);
    from = new Date(selectedYear, selectedMonth - 1, 1);
    to = new Date(selectedYear, selectedMonth, 0);
  } else if (periodFilter.value === "selected_year" && yearFilter.value) {
    const selectedYear = Number(yearFilter.value);
    from = new Date(selectedYear, 0, 1);
    to = new Date(selectedYear, 11, 31);
  }

  if (periodFilter.value !== "custom") {
    fromFilter.value = from ? toIsoDate(from) : "";
    toFilter.value = to ? toIsoDate(to) : "";
  }
}

function toIsoDate(date) {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

async function loadSalesTransactions() {
  try {
    const response = await fetch("/api/sales-transactions?limit=100");
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.message || "Could not load sales transactions.");
    }
    allTransactions = data.sales_transactions || [];
    applySalesFilters();
  } catch (error) {
    showMessage(error.message || "Could not load sales overview.");
    transactionsBody.innerHTML = '<tr><td colspan="6" class="table-empty">Could not load sales transactions.</td></tr>';
  }
}

async function loadStockAvailability() {
  try {
    const response = await fetch("/api/pig-weights/sales-dashboard");
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error("Failed to load stock availability.");
    }
    renderStockAvailability(data.totals || [], data.summary || []);
  } catch (error) {
    totalsGrid.innerHTML = '<div class="empty-state"><div>Could not load available stock.</div></div>';
    summaryList.innerHTML = "";
  }
}

function filteredTransactions() {
  const selectedStream = streamFilter.value;
  const fromDate = parseDate(fromFilter.value);
  const toDate = parseDate(toFilter.value);

  return allTransactions.filter((item) => {
    const saleDate = parseDate(item.sale_date);
    if (selectedStream && item.sale_stream !== selectedStream) return false;
    if (fromDate && saleDate && saleDate < fromDate) return false;
    if (toDate && saleDate && saleDate > toDate) return false;
    return true;
  });
}

function applySalesFilters() {
  clearMessage();
  const rows = filteredTransactions();
  renderSalesTotals(rows);
  renderTransactions(rows);
  periodLabel.textContent = buildPeriodLabel(rows);
}

function buildPeriodLabel(rows) {
  const range = fromFilter.value || toFilter.value
    ? `${fromFilter.value || "start"} to ${toFilter.value || "today"}`
    : "all loaded sales";
  const stream = streamFilter.value || "all streams";
  return `${rows.length} transaction${rows.length === 1 ? "" : "s"} for ${stream}, ${range}.`;
}

function baseTotals() {
  return {
    livestock: { count: 0, value: 0, pigs: 0 },
    slaughter: { count: 0, value: 0, pigs: 0 },
    meat: { count: 0, value: 0, pigs: 0 },
  };
}

function renderSalesTotals(rows) {
  const totals = baseTotals();
  rows.forEach((item) => {
    const key = streamKey(item.sale_stream);
    if (!totals[key]) return;
    if (item.sale_status === "Cancelled") return;
    totals[key].count += 1;
    totals[key].value += Number(item.net_total || 0);
    totals[key].pigs += Number(item.pig_count || item.item_count || 0);
  });

  const grand = Object.values(totals).reduce((acc, item) => ({
    count: acc.count + item.count,
    value: acc.value + item.value,
    pigs: acc.pigs + item.pigs,
  }), { count: 0, value: 0, pigs: 0 });

  setTotalCard("sales_total", grand);
  setTotalCard("sales_livestock", totals.livestock);
  setTotalCard("sales_slaughter", totals.slaughter);
  setTotalCard("sales_meat", totals.meat);
}

function setTotalCard(prefix, total) {
  document.getElementById(`${prefix}_value`).textContent = money(total.value);
  document.getElementById(`${prefix}_count`).textContent = `${total.count} transaction${total.count === 1 ? "" : "s"} / ${total.pigs} pig${total.pigs === 1 ? "" : "s"}`;
}

function renderTransactions(rows) {
  if (!rows.length) {
    transactionsBody.innerHTML = '<tr><td colspan="6" class="table-empty">No sales transactions match the selected filters.</td></tr>';
    transactionsCount.textContent = "No transactions in this view.";
    return;
  }

  transactionsCount.textContent = `Showing ${rows.length} of ${allTransactions.length} loaded transactions.`;
  transactionsBody.innerHTML = rows.map((item) => {
    const isCancelled = item.sale_status === "Cancelled";
    const rowClass = isCancelled ? ' class="muted-row"' : "";
    const statusClass = isCancelled ? "status-pill status-pill-muted" : "status-pill";
    return `
      <tr${rowClass} data-sale-row="${item.sale_id}" tabindex="0">
        <td>
          <strong>${item.sale_id || "-"}</strong>
          <span class="table-subtext">${dateOnly(item.sale_date) || "-"}</span>
        </td>
        <td><span class="status-pill status-pill-muted">${item.sale_stream || "-"}</span></td>
        <td>
          <strong>${item.buyer_name || "-"}</strong>
          <span class="table-subtext">${item.destination || "No destination"}</span>
        </td>
        <td><span class="${statusClass}">${item.sale_status || "-"}</span></td>
        <td><span class="${statusClass}">${item.payment_status || "-"}</span></td>
        <td>
          <strong>${money(item.net_total)}</strong>
          <span class="table-subtext">${item.item_count ?? item.pig_count ?? "-"} item${Number(item.item_count || item.pig_count) === 1 ? "" : "s"}</span>
        </td>
      </tr>
    `;
  }).join("");
}

function renderStockAvailability(totals, summary) {
  totalsGrid.innerHTML = totals.length
    ? totals.map((item) => `
      <div class="sales-stock-card">
        <span>${item.sale_category}</span>
        <strong>${item.qty_available}</strong>
        <small>Male ${item.male_qty} / Female ${item.female_qty} / Castrated ${item.castrated_male_qty}</small>
      </div>
    `).join("")
    : '<div class="empty-state"><div>No sales totals available.</div></div>';

  summaryList.innerHTML = summary.length
    ? summary.slice(0, 12).map((item) => `
      <div class="sales-stock-row">
        <strong>${item.sale_category}</strong>
        <span>${item.weight_band || "-"}</span>
        <span>${item.qty_available} available</span>
        <span>${item.price_range || "-"}</span>
        <span>${item.status || "-"}</span>
      </div>
    `).join("")
    : '<div class="empty-state"><div>No weight band summary available.</div></div>';
}

function openTransactionRow(row) {
  if (!row) return;
  window.location.href = `/sales/transactions/${encodeURIComponent(row.dataset.saleRow)}`;
}

transactionsBody.addEventListener("click", (event) => {
  openTransactionRow(event.target.closest("[data-sale-row]"));
});

transactionsBody.addEventListener("keydown", (event) => {
  if (event.key !== "Enter" && event.key !== " ") return;
  const row = event.target.closest("[data-sale-row]");
  if (!row) return;
  event.preventDefault();
  openTransactionRow(row);
});

periodFilter.addEventListener("change", () => {
  applyPeriodDefaults();
  applySalesFilters();
});
monthFilter.addEventListener("change", () => {
  if (periodFilter.value === "selected_month") applyPeriodDefaults();
  applySalesFilters();
});
yearFilter.addEventListener("input", () => {
  if (periodFilter.value === "selected_year") applyPeriodDefaults();
  applySalesFilters();
});
streamFilter.addEventListener("change", applySalesFilters);
fromFilter.addEventListener("change", () => {
  periodFilter.value = "custom";
  applySalesFilters();
});
toFilter.addEventListener("change", () => {
  periodFilter.value = "custom";
  applySalesFilters();
});
resetFiltersButton.addEventListener("click", () => {
  periodFilter.value = "this_month";
  streamFilter.value = "";
  setDefaultFilters();
  applySalesFilters();
});
