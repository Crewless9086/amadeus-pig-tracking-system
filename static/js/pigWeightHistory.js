const historyMessageBox = document.getElementById("history_message");
const historySummary = document.getElementById("history_summary");
const historyList = document.getElementById("history_list");

function getPigIdFromHistoryUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 2] || "");
}

function showHistoryMessage(message, type = "error") {
  historyMessageBox.classList.remove("hidden", "message-success", "message-error");
  historyMessageBox.classList.add(type === "success" ? "message-success" : "message-error");
  historyMessageBox.textContent = message;
}

function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || value === "" || Number.isNaN(Number(value))) {
    return "—";
  }
  return Number(value).toFixed(decimals);
}

function renderSummaryCard(label, value) {
  return `
    <div class="detail-card">
      <span class="detail-label">${label}</span>
      <span class="detail-value">${value}</span>
    </div>
  `;
}

function getDifferenceClass(value) {
  if (value === null || value === undefined || value === "") return "";
  if (Number(value) > 0) return "good-text";
  if (Number(value) < 0) return "bad-text";
  return "neutral-text";
}

function renderHistoryRow(item) {
  const diffClass = getDifferenceClass(item.difference_kg);
  const growthClass = getDifferenceClass(item.growth_rate_kg_day);

  return `
    <div class="history-item">
      <div class="history-item-top">
        <div class="history-item-date">${item.weight_date_display || "—"}</div>
        <div class="history-item-weight">${item.weight_kg !== null && item.weight_kg !== "" ? `${formatNumber(item.weight_kg, 2)} kg` : "—"}</div>
      </div>

      <div class="history-item-grid">
        <div>
          <span class="history-label">Difference</span>
          <span class="history-value ${diffClass}">
            ${item.difference_kg !== null ? `${item.difference_kg >= 0 ? "+" : ""}${formatNumber(item.difference_kg, 2)} kg` : "—"}
          </span>
        </div>

        <div>
          <span class="history-label">Days Since Previous</span>
          <span class="history-value">
            ${item.days_since_previous !== null ? item.days_since_previous : "—"}
          </span>
        </div>

        <div>
          <span class="history-label">Growth Rate</span>
          <span class="history-value ${growthClass}">
            ${item.growth_rate_kg_day !== null ? `${item.growth_rate_kg_day >= 0 ? "+" : ""}${formatNumber(item.growth_rate_kg_day, 3)} kg/day` : "—"}
          </span>
        </div>

        <div>
          <span class="history-label">Weighed By</span>
          <span class="history-value">${item.weighed_by || "—"}</span>
        </div>
      </div>

      <div class="history-notes">
        <span class="history-label">Condition Notes</span>
        <span class="history-value">${item.condition_notes || "—"}</span>
      </div>
    </div>
  `;
}

async function loadWeightHistory() {
  const pigId = getPigIdFromHistoryUrl();

  if (!pigId) {
    showHistoryMessage("No pig ID found in URL.", "error");
    return;
  }

  document.getElementById("history_profile_button").href = `/pig/${encodeURIComponent(pigId)}`;
  document.getElementById("history_record_weight_button").href = `/pig-weights?pig_id=${encodeURIComponent(pigId)}`;

  try {
    const response = await fetch(`/api/pig-weights/${encodeURIComponent(pigId)}/history`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showHistoryMessage("Could not load weight history.", "error");
      return;
    }

    const titleTag = data.tag_number || data.pig_id;
    document.getElementById("history_title").textContent = `Weight History • ${titleTag}`;
    document.getElementById("history_subtitle").textContent = `Pig ID: ${data.pig_id} • ${data.count} record(s)`;

    const latest = data.history[0] || null;
    const oldest = data.history[data.history.length - 1] || null;

    historySummary.innerHTML = `
      ${renderSummaryCard("Total Records", data.count)}
      ${renderSummaryCard("Latest Weight", latest && latest.weight_kg !== null ? `${formatNumber(latest.weight_kg, 2)} kg` : "—")}
      ${renderSummaryCard("Latest Date", latest ? (latest.weight_date_display || "—") : "—")}
      ${renderSummaryCard("First Recorded Weight", oldest && oldest.weight_kg !== null ? `${formatNumber(oldest.weight_kg, 2)} kg` : "—")}
    `;

    if (!data.history.length) {
      historyList.innerHTML = `
        <div class="empty-state">
          <strong>No weight history found.</strong>
          <span>Record the first weight for this pig.</span>
        </div>
      `;
      return;
    }

    historyList.innerHTML = data.history.map(renderHistoryRow).join("");
  } catch (error) {
    showHistoryMessage("Something went wrong while loading weight history.", "error");
  }
}

loadWeightHistory();