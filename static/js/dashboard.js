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

function renderBreakdownCard(label, value) {
  return `
    <div class="breakdown-card">
      <span class="detail-label">${label}</span>
      <span class="breakdown-value">${value}</span>
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
      <p class="section-heading">Herd</p>
      <div class="detail-grid" style="margin-bottom: 10px;">
        <div class="detail-card detail-card-wide">
          <span class="detail-label">On Farm</span>
          <span class="detail-value">${summary.on_farm_pigs}</span>
        </div>
      </div>
      <div class="breakdown-grid" style="margin-bottom: 28px;">
        ${renderBreakdownCard("Boars", summary.boars)}
        ${renderBreakdownCard("Sows", summary.sows)}
        ${renderBreakdownCard("Gilts", summary.gilts)}
        ${renderBreakdownCard("Piglets", summary.piglets)}
        ${renderBreakdownCard("Weaners", summary.weaners)}
        ${renderBreakdownCard("Growers", summary.growers)}
        ${renderBreakdownCard("Finishers", summary.finishers)}
      </div>

      <p class="section-heading">Sales</p>
      <div class="detail-grid">
        ${renderSummaryCard("Available For Sale", summary.available_for_sale_pigs)}
        ${renderSummaryCard("Reserved", summary.reserved_pigs)}
        ${renderSummaryCard("Withdrawal Hold", summary.withdrawal_hold_pigs)}
        ${renderSummaryCard("Sold This Month", summary.sold_this_month)}
      </div>
    `;
  } catch (error) {
    showDashboardMessage("Something went wrong while loading the dashboard.", "error");
  }
}

loadDashboard();