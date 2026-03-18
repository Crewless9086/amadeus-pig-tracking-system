const treatmentHistoryMessageBox = document.getElementById("treatment_history_message");
const treatmentHistorySummary = document.getElementById("treatment_history_summary");
const treatmentHistoryList = document.getElementById("treatment_history_list");

function getPigIdFromTreatmentHistoryUrl() {
  const parts = window.location.pathname.split("/");
  return decodeURIComponent(parts[parts.length - 2] || "");
}

function showTreatmentHistoryMessage(message, type = "error") {
  treatmentHistoryMessageBox.classList.remove("hidden", "message-success", "message-error");
  treatmentHistoryMessageBox.classList.add(type === "success" ? "message-success" : "message-error");
  treatmentHistoryMessageBox.textContent = message;
}

function renderSummaryCard(label, value) {
  return `
    <div class="detail-card">
      <span class="detail-label">${label}</span>
      <span class="detail-value">${value}</span>
    </div>
  `;
}

function renderTreatmentRow(item) {
  return `
    <div class="history-item">
      <div class="history-item-top">
        <div class="history-item-date">${item.treatment_date_display || "—"}</div>
        <div class="history-item-weight">${item.product_name || "—"}</div>
      </div>

      <div class="history-item-grid">
        <div>
          <span class="history-label">Treatment Type</span>
          <span class="history-value">${item.treatment_type || "—"}</span>
        </div>

        <div>
          <span class="history-label">Dose</span>
          <span class="history-value">${item.dose !== null && item.dose !== "" ? `${item.dose} ${item.dose_unit || ""}`.trim() : "—"}</span>
        </div>

        <div>
          <span class="history-label">Route</span>
          <span class="history-value">${item.route || "—"}</span>
        </div>

        <div>
          <span class="history-label">Given By</span>
          <span class="history-value">${item.given_by || "—"}</span>
        </div>

        <div>
          <span class="history-label">Withdrawal End Date</span>
          <span class="history-value">${item.withdrawal_end_date || "—"}</span>
        </div>

        <div>
          <span class="history-label">Follow-Up Required</span>
          <span class="history-value">${item.follow_up_required || "—"}</span>
        </div>
      </div>

      <div class="history-notes">
        <span class="history-label">Reason</span>
        <span class="history-value">${item.reason_for_treatment || "—"}</span>
      </div>

      <div class="history-notes">
        <span class="history-label">Batch / Lot Number</span>
        <span class="history-value">${item.batch_lot_number || "—"}</span>
      </div>

      <div class="history-notes">
        <span class="history-label">Medical Notes</span>
        <span class="history-value">${item.medical_notes || "—"}</span>
      </div>
    </div>
  `;
}

async function loadTreatmentHistory() {
  const pigId = getPigIdFromTreatmentHistoryUrl();

  if (!pigId) {
    showTreatmentHistoryMessage("No pig ID found in URL.", "error");
    return;
  }

  document.getElementById("treatment_history_profile_button").href = `/pig/${encodeURIComponent(pigId)}`;
  document.getElementById("treatment_history_record_button").href = `/pig/${encodeURIComponent(pigId)}/treatment`;

  try {
    const response = await fetch(`/api/pig-weights/${encodeURIComponent(pigId)}/treatments`);
    const data = await response.json();

    if (!response.ok || !data.success) {
      showTreatmentHistoryMessage("Could not load treatment history.", "error");
      return;
    }

    const titleTag = data.tag_number || data.pig_id;
    document.getElementById("treatment_history_title").textContent = `Treatment History • ${titleTag}`;
    document.getElementById("treatment_history_subtitle").textContent = `Pig ID: ${data.pig_id} • ${data.count} record(s)`;

    const latest = data.history[0] || null;

    treatmentHistorySummary.innerHTML = `
      ${renderSummaryCard("Total Records", data.count)}
      ${renderSummaryCard("Last Treatment Date", latest ? (latest.treatment_date_display || "—") : "—")}
      ${renderSummaryCard("Last Product", latest ? (latest.product_name || "—") : "—")}
      ${renderSummaryCard("Last Treatment Type", latest ? (latest.treatment_type || "—") : "—")}
    `;

    if (!data.history.length) {
      treatmentHistoryList.innerHTML = `
        <div class="empty-state">
          <strong>No treatment history found.</strong>
          <span>Record the first treatment for this pig.</span>
        </div>
      `;
      return;
    }

    treatmentHistoryList.innerHTML = data.history.map(renderTreatmentRow).join("");
  } catch (error) {
    showTreatmentHistoryMessage("Something went wrong while loading treatment history.", "error");
  }
}

loadTreatmentHistory();