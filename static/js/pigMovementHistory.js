const movementHistoryMessageBox = document.getElementById("movement_history_message");
const movementHistorySummary = document.getElementById("movement_history_summary");
const movementHistoryList = document.getElementById("movement_history_list");

function getPigIdFromMovementHistoryUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 2] || "");
}

function showMovementHistoryMessage(message, type = "error") {
  movementHistoryMessageBox.classList.remove("hidden", "message-success", "message-error");
  movementHistoryMessageBox.classList.add(type === "success" ? "message-success" : "message-error");
  movementHistoryMessageBox.textContent = message;
}

function renderSummaryCard(label, value) {
  return `
    <div class="detail-card">
      <span class="detail-label">${label}</span>
      <span class="detail-value">${value}</span>
    </div>
  `;
}

function renderMovementRow(item) {
  return `
    <div class="history-item">
      <div class="history-item-top">
        <div class="history-item-date">${item.move_date_display || "—"}</div>
        <div class="history-item-weight">${item.to_pen_name || item.to_pen_id || "—"}</div>
      </div>

      <div class="history-item-grid">
        <div>
          <span class="history-label">From Pen</span>
          <span class="history-value">${item.from_pen_name || item.from_pen_id || "—"}</span>
        </div>

        <div>
          <span class="history-label">To Pen</span>
          <span class="history-value">${item.to_pen_name || item.to_pen_id || "—"}</span>
        </div>

        <div>
          <span class="history-label">Reason For Move</span>
          <span class="history-value">${item.reason_for_move || "—"}</span>
        </div>

        <div>
          <span class="history-label">Moved By</span>
          <span class="history-value">${item.moved_by || "—"}</span>
        </div>
      </div>

      <div class="history-notes">
        <span class="history-label">Move Notes</span>
        <span class="history-value">${item.move_notes || "—"}</span>
      </div>
    </div>
  `;
}

async function loadMovementHistory() {
  const pigId = getPigIdFromMovementHistoryUrl();

  if (!pigId) {
    showMovementHistoryMessage("No pig ID found in URL.", "error");
    return;
  }

  document.getElementById("movement_history_profile_button").href = `/pig/${encodeURIComponent(pigId)}`;
  document.getElementById("movement_history_record_button").href = `/pig/${encodeURIComponent(pigId)}/movement`;

  try {
    const response = await fetch(`/api/pig-weights/pig/${encodeURIComponent(pigId)}/movements`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showMovementHistoryMessage("Could not load movement history.", "error");
      return;
    }

    const titleTag = data.tag_number || data.pig_id;

    document.getElementById("movement_history_title").textContent = `Movement History • ${titleTag}`;
    document.getElementById("movement_history_subtitle").textContent = `Pig ID: ${data.pig_id} • ${data.count} record(s)`;

    const latest = data.history[0] || null;

    movementHistorySummary.innerHTML = `
      ${renderSummaryCard("Total Records", data.count)}
      ${renderSummaryCard("Current Pen", data.current_pen_id || "—")}
      ${renderSummaryCard("Last Move Date", latest ? (latest.move_date_display || "—") : "—")}
      ${renderSummaryCard("Last Destination", latest ? (latest.to_pen_name || latest.to_pen_id || "—") : "—")}
    `;

    if (!data.history.length) {
      movementHistoryList.innerHTML = `
        <div class="empty-state">
          <strong>No movement history found.</strong>
          <span>Record the first movement for this pig.</span>
        </div>
      `;
      return;
    }

    movementHistoryList.innerHTML = data.history.map(renderMovementRow).join("");
  } catch (error) {
    console.error("loadMovementHistory error:", error);
    showMovementHistoryMessage("Something went wrong while loading movement history.", "error");
  }
}

loadMovementHistory();