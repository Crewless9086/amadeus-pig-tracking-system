const salesSummary = document.getElementById("sales_summary");
const salesList = document.getElementById("sales_list");
const salesMessage = document.getElementById("sales_message");

const salesSearch = document.getElementById("sales_search");
const stageFilter = document.getElementById("sales_stage_filter");
const weightBandFilter = document.getElementById("sales_weight_band_filter");
const categoryFilter = document.getElementById("sales_category_filter");
const availableFilter = document.getElementById("sales_available_filter");
const reservedFilter = document.getElementById("sales_reserved_filter");
const withdrawalFilter = document.getElementById("sales_withdrawal_filter");
const clearFiltersButton = document.getElementById("clear_sales_filters_button");

let allSalesPigs = [];

function showSalesMessage(message, type = "error") {
  salesMessage.classList.remove("hidden", "message-success", "message-error");
  salesMessage.classList.add(type === "success" ? "message-success" : "message-error");
  salesMessage.textContent = message;
}

function clearSalesMessage() {
  salesMessage.classList.add("hidden");
  salesMessage.textContent = "";
  salesMessage.classList.remove("message-success", "message-error");
}

function renderSummaryCard(label, value) {
  return `
    <div class="detail-card">
      <span class="detail-label">${label}</span>
      <span class="detail-value">${value}</span>
    </div>
  `;
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(decimals);
}

function buildSalesCard(pig) {
  const card = document.createElement("a");
  card.className = "pig-list-card";
  card.href = `/pig/${encodeURIComponent(pig.pig_id)}`;

  const topRow = document.createElement("div");
  topRow.className = "pig-list-top";

  const tag = document.createElement("div");
  tag.className = "pig-list-tag";
  tag.textContent = pig.tag_number || pig.pig_id;

  const action = document.createElement("div");
  action.className = "pig-list-action";
  action.textContent = "Open Profile →";

  topRow.appendChild(tag);
  topRow.appendChild(action);

  const meta = document.createElement("div");
  meta.className = "pig-list-meta";
  meta.textContent = `Pig ID: ${pig.pig_id}`;

  const subMeta = document.createElement("div");
  subMeta.className = "pig-list-submeta";
  subMeta.textContent =
    `${pig.sale_category || "—"} • ${pig.weight_band || "—"} • ${pig.current_weight_kg !== null && pig.current_weight_kg !== "" ? `${formatNumber(pig.current_weight_kg, 2)} kg` : "No weight"}`;

  const salesInfo = document.createElement("div");
  salesInfo.className = "sales-meta-grid";
  salesInfo.innerHTML = `
    <div><span class="history-label">Stage</span><span class="history-value">${pig.calculated_stage || "—"}</span></div>
    <div><span class="history-label">Available</span><span class="history-value">${pig.available_for_sale || "—"}</span></div>
    <div><span class="history-label">Reserved</span><span class="history-value">${pig.reserved_status || "—"}</span></div>
    <div><span class="history-label">Withdrawal Clear</span><span class="history-value">${pig.withdrawal_clear || "—"}</span></div>
    <div><span class="history-label">Price Category</span><span class="history-value">${pig.suggested_price_category || "—"}</span></div>
    <div><span class="history-label">Pen</span><span class="history-value">${pig.current_pen_id || "—"}</span></div>
  `;

  card.appendChild(topRow);
  card.appendChild(meta);
  card.appendChild(subMeta);
  card.appendChild(salesInfo);

  return card;
}

function renderSalesList(pigs) {
  salesList.innerHTML = "";

  if (!pigs.length) {
    salesList.innerHTML = `
      <div class="empty-state">
        <strong>No matching pigs found.</strong>
        <span>Try a different filter combination.</span>
      </div>
    `;
    return;
  }

  pigs.forEach((pig) => {
    salesList.appendChild(buildSalesCard(pig));
  });
}

function uniqueSortedValues(items, key) {
  return [...new Set(items.map(item => item[key]).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b)));
}

function populateFilters() {
  const stages = uniqueSortedValues(allSalesPigs, "calculated_stage");
  const weightBands = uniqueSortedValues(allSalesPigs, "weight_band");
  const categories = uniqueSortedValues(allSalesPigs, "sale_category");
  const reservedStatuses = uniqueSortedValues(allSalesPigs, "reserved_status");

  stages.forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    stageFilter.appendChild(option);
  });

  weightBands.forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    weightBandFilter.appendChild(option);
  });

  categories.forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    categoryFilter.appendChild(option);
  });

  reservedStatuses.forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    reservedFilter.appendChild(option);
  });
}

function updateSummary(pigs) {
  const total = pigs.length;
  const available = pigs.filter(p => p.available_for_sale === "Yes").length;
  const saleReady = pigs.filter(p => p.available_for_sale === "Yes" && p.withdrawal_clear === "Yes").length;
  const reserved = pigs.filter(p => p.reserved_status === "Reserved").length;

  salesSummary.innerHTML = `
    ${renderSummaryCard("Total Records", total)}
    ${renderSummaryCard("Available For Sale", available)}
    ${renderSummaryCard("Commercially Clear", saleReady)}
    ${renderSummaryCard("Reserved", reserved)}
  `;
}

function filterSales() {
  const query = salesSearch.value.trim().toLowerCase();

  const filtered = allSalesPigs.filter((pig) => {
    const matchesSearch =
      !query ||
      String(pig.pig_id || "").toLowerCase().includes(query) ||
      String(pig.tag_number || "").toLowerCase().includes(query);

    const matchesStage = !stageFilter.value || pig.calculated_stage === stageFilter.value;
    const matchesWeightBand = !weightBandFilter.value || pig.weight_band === weightBandFilter.value;
    const matchesCategory = !categoryFilter.value || pig.sale_category === categoryFilter.value;
    const matchesAvailable = !availableFilter.value || pig.available_for_sale === availableFilter.value;
    const matchesReserved = !reservedFilter.value || pig.reserved_status === reservedFilter.value;
    const matchesWithdrawal = !withdrawalFilter.value || pig.withdrawal_clear === withdrawalFilter.value;

    return (
      matchesSearch &&
      matchesStage &&
      matchesWeightBand &&
      matchesCategory &&
      matchesAvailable &&
      matchesReserved &&
      matchesWithdrawal
    );
  });

  updateSummary(filtered);
  renderSalesList(filtered);
}

function clearAllFilters() {
  salesSearch.value = "";
  stageFilter.value = "";
  weightBandFilter.value = "";
  categoryFilter.value = "";
  availableFilter.value = "";
  reservedFilter.value = "";
  withdrawalFilter.value = "";

  updateSummary(allSalesPigs);
  renderSalesList(allSalesPigs);
}

async function loadSalesAvailability() {
  clearSalesMessage();

  try {
    const response = await fetch("/api/pig-weights/sales-availability");
    const data = await response.json();

    allSalesPigs = data.pigs || [];
    populateFilters();
    updateSummary(allSalesPigs);
    renderSalesList(allSalesPigs);
  } catch (error) {
    showSalesMessage("Could not load sales availability.", "error");
  }
}

salesSearch.addEventListener("input", filterSales);
stageFilter.addEventListener("change", filterSales);
weightBandFilter.addEventListener("change", filterSales);
categoryFilter.addEventListener("change", filterSales);
availableFilter.addEventListener("change", filterSales);
reservedFilter.addEventListener("change", filterSales);
withdrawalFilter.addEventListener("change", filterSales);
clearFiltersButton.addEventListener("click", clearAllFilters);

loadSalesAvailability();