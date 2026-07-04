const ordersSummary = document.getElementById("orders_summary");
const ordersTabs = document.getElementById("orders_status_tabs");
const ordersList = document.getElementById("orders_list");
const ordersMessage = document.getElementById("orders_message");

const ordersSearch = document.getElementById("orders_search");
const sourceFilter = document.getElementById("orders_source_filter");
const paymentFilter = document.getElementById("orders_payment_filter");
const locationFilter = document.getElementById("orders_location_filter");
const clearFiltersButton = document.getElementById("clear_orders_filters_button");

const STATUS_TABS = [
  { id: "active", label: "Active", statuses: ["Draft", "Pending_Approval", "Approved"] },
  { id: "draft", label: "Draft", statuses: ["Draft"] },
  { id: "pending", label: "Pending Approval", statuses: ["Pending_Approval"] },
  { id: "approved", label: "Approved", statuses: ["Approved"] },
  { id: "completed", label: "Completed", statuses: ["Completed"] },
  { id: "cancelled", label: "Cancelled", statuses: ["Cancelled"] },
  { id: "all", label: "All", statuses: null }
];

let allOrders = [];
let activeTabId = "active";

document.addEventListener("DOMContentLoaded", function () {
  setupOrderFilters();
  loadOrders();
});

function setupOrderFilters() {
  ordersSearch.addEventListener("input", applyOrderFilters);
  sourceFilter.addEventListener("change", applyOrderFilters);
  paymentFilter.addEventListener("change", applyOrderFilters);
  locationFilter.addEventListener("change", applyOrderFilters);
  clearFiltersButton.addEventListener("click", clearAllFilters);
}

function showOrdersMessage(message, type = "error") {
  ordersMessage.classList.remove("hidden", "message-success", "message-error");
  ordersMessage.classList.add(type === "success" ? "message-success" : "message-error");
  ordersMessage.textContent = message;
}

function clearOrdersMessage() {
  ordersMessage.classList.add("hidden");
  ordersMessage.textContent = "";
  ordersMessage.classList.remove("message-success", "message-error");
}

function renderSummaryCard(label, value) {
  return `
    <div class="detail-card">
      <span class="detail-label">${label}</span>
      <span class="detail-value">${value}</span>
    </div>
  `;
}

function orderStatus(order) {
  return String(order.order_status || "").trim() || "Unknown";
}

function countByStatus(statuses) {
  return allOrders.filter(order => statuses.includes(orderStatus(order))).length;
}

function getTabCounts() {
  const counts = {};
  STATUS_TABS.forEach(tab => {
    counts[tab.id] = tab.statuses
      ? allOrders.filter(order => tab.statuses.includes(orderStatus(order))).length
      : allOrders.length;
  });
  return counts;
}

function renderSummary(filteredOrders) {
  const counts = getTabCounts();
  const activeCount = countByStatus(["Draft", "Pending_Approval", "Approved"]);
  const pendingCount = countByStatus(["Pending_Approval"]);
  const approvedCount = countByStatus(["Approved"]);
  const completedCount = countByStatus(["Completed"]);
  const cancelledCount = countByStatus(["Cancelled"]);
  const visibleValue = filteredOrders.reduce((sum, order) => sum + Number(order.active_line_total || 0), 0);

  ordersSummary.innerHTML = `
    ${renderSummaryCard("Active Orders", activeCount)}
    ${renderSummaryCard("Pending Approval", pendingCount)}
    ${renderSummaryCard("Approved", approvedCount)}
    ${renderSummaryCard("Completed", completedCount)}
    ${renderSummaryCard("Cancelled", cancelledCount)}
    ${renderSummaryCard("All Orders", counts.all || 0)}
    ${renderSummaryCard("Visible Value", formatMoney(visibleValue))}
  `;
}

function renderStatusTabs() {
  const counts = getTabCounts();

  ordersTabs.innerHTML = STATUS_TABS.map(tab => {
    const selected = tab.id === activeTabId;
    return `
      <button
        type="button"
        class="order-status-tab${selected ? " order-status-tab-active" : ""}"
        data-tab-id="${tab.id}"
        role="tab"
        aria-selected="${selected ? "true" : "false"}"
      >
        <span>${tab.label}</span>
        <strong>${counts[tab.id] || 0}</strong>
      </button>
    `;
  }).join("");

  ordersTabs.querySelectorAll("[data-tab-id]").forEach(button => {
    button.addEventListener("click", function () {
      activeTabId = button.dataset.tabId;
      applyOrderFilters();
    });
  });
}

function uniqueSortedValues(items, key) {
  return [...new Set(items.map(item => String(item[key] || "").trim()).filter(Boolean))]
    .sort((a, b) => a.localeCompare(b));
}

function populateSelect(select, values) {
  select.innerHTML = `<option value="">All</option>`;
  values.forEach(value => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function populateFilters() {
  populateSelect(sourceFilter, uniqueSortedValues(allOrders, "order_source"));
  populateSelect(paymentFilter, uniqueSortedValues(allOrders, "payment_method"));
  populateSelect(locationFilter, uniqueSortedValues(allOrders, "collection_location"));
}

function orderMatchesTab(order) {
  const tab = STATUS_TABS.find(item => item.id === activeTabId) || STATUS_TABS[0];
  return !tab.statuses || tab.statuses.includes(orderStatus(order));
}

function orderMatchesSearch(order, query) {
  if (!query) return true;

  const searchable = [
    order.order_id,
    order.customer_name,
    order.customer_phone,
    order.customer_channel,
    order.conversation_id,
    order.requested_category,
    order.requested_weight_range,
    order.requested_sex,
    order.collection_location,
    order.notes
  ].join(" ").toLowerCase();

  return searchable.includes(query);
}

function applyOrderFilters() {
  const query = ordersSearch.value.trim().toLowerCase();

  const filtered = allOrders.filter(order => {
    const matchesTab = orderMatchesTab(order);
    const matchesSearch = orderMatchesSearch(order, query);
    const matchesSource = !sourceFilter.value || order.order_source === sourceFilter.value;
    const matchesPayment = !paymentFilter.value || order.payment_method === paymentFilter.value;
    const matchesLocation = !locationFilter.value || order.collection_location === locationFilter.value;

    return matchesTab && matchesSearch && matchesSource && matchesPayment && matchesLocation;
  });

  renderStatusTabs();
  renderSummary(filtered);
  renderOrdersList(filtered);
}

function clearAllFilters() {
  ordersSearch.value = "";
  sourceFilter.value = "";
  paymentFilter.value = "";
  locationFilter.value = "";
  activeTabId = "active";
  applyOrderFilters();
}

function statusLabel(order) {
  const approval = String(order.approval_status || "").trim();
  const status = orderStatus(order);
  return approval && approval !== status ? `${status} / ${approval}` : status;
}

function orderRequestSummary(order) {
  const parts = [
    order.requested_quantity ? `${formatPlainNumber(order.requested_quantity)}x` : "",
    order.requested_sex,
    order.requested_category,
    order.requested_weight_range
  ].filter(Boolean);

  return parts.length ? parts.join(" ") : "No request summary";
}

function buildOrderCard(order) {
  const card = document.createElement("a");
  card.className = "pig-list-card";
  card.href = `/orders/${encodeURIComponent(order.order_id)}`;

  const total = Number(order.active_line_total || order.quoted_total || order.final_total || 0);

  card.innerHTML = `
    <div class="pig-list-top">
      <div>
        <div class="pig-list-tag">${escapeHtml(order.order_id || "-")}</div>
        <div class="pig-list-meta">${escapeHtml(order.customer_name || "Unknown customer")} | ${escapeHtml(order.customer_channel || "-")} | ${escapeHtml(order.order_date || "-")}</div>
      </div>
      <div class="pig-list-action">Open Order -></div>
    </div>
    <div class="order-card-status-row">
      <span class="status-pill">${escapeHtml(statusLabel(order))}</span>
      <span class="status-pill status-pill-muted">${escapeHtml(order.payment_method || "Payment not set")}</span>
    </div>
    <div class="pig-list-submeta">${escapeHtml(orderRequestSummary(order))}</div>
    <div class="sales-meta-grid">
      <div><span class="history-label">Active Lines</span><span class="history-value">${formatPlainNumber(order.active_line_count || 0)}</span></div>
      <div><span class="history-label">Reserved</span><span class="history-value">${formatPlainNumber(order.reserved_pig_count || order.reserved_line_count || 0)}</span></div>
      <div><span class="history-label">Value</span><span class="history-value">${formatMoney(total)}</span></div>
      <div><span class="history-label">Collection</span><span class="history-value">${escapeHtml(order.collection_location || "-")}</span></div>
      <div><span class="history-label">Source</span><span class="history-value">${escapeHtml(order.order_source || "-")}</span></div>
      <div><span class="history-label">Updated</span><span class="history-value">${escapeHtml(order.updated_at || order.created_at || "-")}</span></div>
    </div>
  `;

  return card;
}

function renderOrdersList(orders) {
  ordersList.innerHTML = "";

  if (!orders.length) {
    const counts = getTabCounts();
    const currentTab = STATUS_TABS.find(tab => tab.id === activeTabId) || STATUS_TABS[0];
    const hasSearchOrFilters = Boolean(
      ordersSearch.value.trim()
      || sourceFilter.value
      || paymentFilter.value
      || locationFilter.value
    );
    const historicalCount = (counts.completed || 0) + (counts.cancelled || 0);
    const activeCount = counts.active || 0;

    let headline = "No matching orders found.";
    let detail = "Try another status tab or filter combination.";
    let actions = "";

    if (activeTabId === "active" && !hasSearchOrFilters && activeCount === 0 && historicalCount > 0) {
      headline = "No active orders right now.";
      detail = `${historicalCount} historical migrated orders are available: ${counts.completed || 0} completed and ${counts.cancelled || 0} cancelled.`;
      actions = `
        <div class="empty-state-actions">
          <button type="button" data-empty-tab="completed">Completed (${counts.completed || 0})</button>
          <button type="button" data-empty-tab="cancelled">Cancelled (${counts.cancelled || 0})</button>
          <button type="button" data-empty-tab="all">All (${counts.all || 0})</button>
        </div>
      `;
    } else if (hasSearchOrFilters) {
      detail = `No ${currentTab.label.toLowerCase()} orders match the current search and filters.`;
    }

    ordersList.innerHTML = `
      <div class="empty-state">
        <strong>${escapeHtml(headline)}</strong>
        <span>${escapeHtml(detail)}</span>
        ${actions}
      </div>
    `;
    ordersList.querySelectorAll("[data-empty-tab]").forEach(button => {
      button.addEventListener("click", function () {
        activeTabId = button.dataset.emptyTab;
        applyOrderFilters();
      });
    });
    return;
  }

  orders.forEach(order => {
    ordersList.appendChild(buildOrderCard(order));
  });
}

async function loadOrders() {
  clearOrdersMessage();

  try {
    const response = await fetch("/api/orders");
    const data = await response.json();

    if (!response.ok || !data.success) {
      throw new Error("Failed to load orders.");
    }

    allOrders = data.orders || [];
    populateFilters();
    applyOrderFilters();
  } catch (error) {
    console.error("Orders load error:", error);
    showOrdersMessage("Something went wrong while loading orders.", "error");
    ordersList.innerHTML = "";
  }
}

function formatMoney(value) {
  const amount = Number(value || 0);
  if (Number.isNaN(amount)) return "R0.00";
  return `R${amount.toLocaleString("en-ZA", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  })}`;
}

function formatPlainNumber(value) {
  const amount = Number(value || 0);
  if (Number.isNaN(amount)) return "0";
  return Number.isInteger(amount) ? String(amount) : String(amount.toFixed(2));
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll('"', "&quot;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}
