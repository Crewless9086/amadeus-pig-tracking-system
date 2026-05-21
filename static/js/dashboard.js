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

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function formatOptional(value, fallback = "-") {
  return value !== null && value !== undefined && value !== "" ? escapeHtml(value) : fallback;
}

function renderLitterAttention(attention) {
  const items = attention?.items || [];
  const count = Number(attention?.count || 0);

  if (!count) {
    return `
      <p class="section-heading">Litter Attention</p>
      <div class="empty-state" style="margin-bottom: 28px;">
        <strong>No litter reminders</strong>
        <span>No litters are currently flagged for attention.</span>
      </div>
    `;
  }

  const cards = items.map(item => `
    <a href="/litter/${encodeURIComponent(item.litter_id)}" class="pig-list-card">
      <div class="pig-list-top">
        <div class="pig-list-tag">${escapeHtml(item.litter_id)}</div>
        <div class="pig-list-action">Open Litter</div>
      </div>
      <div class="pig-list-meta">${escapeHtml(item.reason || "Review litter")}</div>
      <div class="pig-list-submeta">
        Sow ${formatOptional(item.sow_tag_number)} • ${formatOptional(item.litter_status)} • Active ${formatOptional(item.active_pig_count, "0")}
      </div>
      <div class="sales-meta-grid">
        <div><span class="history-label">Farrowed</span><span class="history-value">${formatOptional(item.farrowing_date)}</span></div>
        <div><span class="history-label">Weaned</span><span class="history-value">${formatOptional(item.wean_date)}</span></div>
        <div><span class="history-label">Age Range</span><span class="history-value">${formatOptional(item.youngest_age_days)}-${formatOptional(item.oldest_age_days)} days</span></div>
        <div><span class="history-label">Weaned Count</span><span class="history-value">${formatOptional(item.weaned_count)}</span></div>
      </div>
    </a>
  `).join("");

  const moreText = count > items.length
    ? `<p style="margin: 8px 0 28px 0; color: var(--text-soft);">${count - items.length} more litter reminder(s) not shown.</p>`
    : `<div style="margin-bottom: 28px;"></div>`;

  return `
    <p class="section-heading">Litter Attention</p>
    <div class="pig-list-grid">
      ${cards}
    </div>
    ${moreText}
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
    const litterAttention = data.litter_attention;

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

      ${renderLitterAttention(litterAttention)}

      <p class="section-heading">Sales</p>
      <div class="detail-grid">
        ${renderSummaryCard("Available For Sale", summary.available_for_sale_pigs)}
        ${renderSummaryCard("Reserved", summary.reserved_pigs)}
        ${renderSummaryCard("Withdrawal Hold", summary.withdrawal_hold_pigs)}
        ${renderSummaryCard("Sales Exits This Month", summary.sold_this_month)}
        ${renderSummaryCard("Livestock Exits", summary.livestock_sold_this_month ?? 0)}
        ${renderSummaryCard("Slaughter Exits", summary.slaughter_sold_this_month ?? 0)}
        ${renderSummaryCard("Meat Exits", summary.meat_sold_this_month ?? 0)}
      </div>
    `;
  } catch (error) {
    showDashboardMessage("Something went wrong while loading the dashboard.", "error");
  }
}

loadDashboard();
