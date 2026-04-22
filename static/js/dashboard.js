const dashboardMessage = document.getElementById("dashboard_message");
const dashboardSummary = document.getElementById("dashboard_summary");

function showDashboardMessage(message, type = "error") {
  dashboardMessage.classList.remove("hidden", "message-success", "message-error");
  dashboardMessage.classList.add(type === "success" ? "message-success" : "message-error");
  dashboardMessage.textContent = message;
}

function renderSummaryCard(label, value) {
  return `
    <div class="detail-card">
      <span class="detail-label">${label}</span>
      <span class="detail-value">${value}</span>
    </div>
  `;
}

async function loadDashboard() {
  try {
    const response = await fetch("/api/pig-weights/dashboard");
    const data = await response.json();

    if (!response.ok || !data.success) {
      showDashboardMessage("Could not load dashboard summary.", "error");
      return;
    }

    const summary = data.summary;

    dashboardSummary.innerHTML = `
      ${renderSummaryCard("Active Pigs", summary.active_pigs)}
      ${renderSummaryCard("On Farm", summary.on_farm_pigs)}
      ${renderSummaryCard("Sold This Month", summary.sold_this_month)}
      ${renderSummaryCard("Available For Sale", summary.available_for_sale_pigs)}
      ${renderSummaryCard("Reserved", summary.reserved_pigs)}
      ${renderSummaryCard("Withdrawal Hold", summary.withdrawal_hold_pigs)}
    `;
  } catch (error) {
    showDashboardMessage("Something went wrong while loading the dashboard.", "error");
  }
}

loadDashboard();