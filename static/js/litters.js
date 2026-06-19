const littersMessage = document.getElementById("litters_message");
const littersSubtitle = document.getElementById("litters_subtitle");
const littersTotal = document.getElementById("litters_total");
const littersAttention = document.getElementById("litters_attention");
const littersMismatch = document.getElementById("litters_mismatch");
const littersFormulaConflict = document.getElementById("litters_formula_conflict");
const littersSearch = document.getElementById("litters_search");
const littersFilter = document.getElementById("litters_filter");
const littersTableBody = document.getElementById("litters_table_body");

let littersState = [];

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function showLittersMessage(message, type = "error") {
  littersMessage.classList.remove("hidden", "message-success", "message-error");
  littersMessage.classList.add(type === "success" ? "message-success" : "message-error");
  littersMessage.textContent = message;
}

function clearLittersMessage() {
  littersMessage.classList.add("hidden");
  littersMessage.textContent = "";
}

function countText(value) {
  return value === null || value === undefined || value === "" ? "-" : String(value);
}

function attentionLabel(litter) {
  if (litter.reconciliation?.formula_conflict) {
    return "Stillborn count/formula conflict";
  }
  if (litter.reconciliation?.mismatch) {
    return "Birth count mismatch";
  }
  return litter.attention_reason || (litter.needs_attention === "Yes" ? "Review litter" : "Clear");
}

function rowMatchesSearch(litter, query) {
  if (!query) return true;
  const text = [
    litter.litter_id,
    litter.sow_tag_number,
    litter.sow_pig_id,
    litter.current_pen_id,
    litter.litter_status,
    litter.attention_reason,
  ].join(" ").toLowerCase();
  return text.includes(query);
}

function filteredLitters() {
  const mode = littersFilter.value;
  const query = littersSearch.value.trim().toLowerCase();
  return littersState.filter((litter) => {
    if (!rowMatchesSearch(litter, query)) return false;
    if (mode === "mismatch") return Boolean(litter.reconciliation?.mismatch || litter.reconciliation?.formula_conflict);
    if (mode === "attention") return litter.needs_attention === "Yes" || Boolean(litter.reconciliation?.mismatch || litter.reconciliation?.formula_conflict);
    return true;
  });
}

function renderLitters() {
  const litters = filteredLitters();
  littersSubtitle.textContent = `${littersState.length} litter(s) loaded from LITTER_OVERVIEW`;

  if (!litters.length) {
    littersTableBody.innerHTML = `<tr><td colspan="7" class="table-empty">No litters match this view.</td></tr>`;
    return;
  }

  littersTableBody.innerHTML = litters.map((litter) => {
    const mismatch = Boolean(litter.reconciliation?.mismatch);
    const formulaConflict = Boolean(litter.reconciliation?.formula_conflict);
    const statusClass = mismatch || formulaConflict || litter.needs_attention === "Yes" ? "status-pill-warning" : "status-pill-muted";
    return `
      <tr>
        <td>
          <strong>${escapeHtml(litter.litter_id)}</strong>
          <span class="table-subtext">Sow ${escapeHtml(litter.sow_tag_number || litter.sow_pig_id || "-")} / ${escapeHtml(litter.farrowing_date || "-")}</span>
        </td>
        <td><span class="status-pill ${statusClass}">${escapeHtml(litter.litter_status || "Unknown")}</span></td>
        <td>${escapeHtml(countText(litter.born_alive))}</td>
        <td>
          <strong>${escapeHtml(countText(litter.linked_pig_records))}</strong>
          <span class="table-subtext">${mismatch || formulaConflict ? `Delta ${escapeHtml(litter.reconciliation.delta)}` : "Matched"}</span>
        </td>
        <td>${escapeHtml(countText(litter.active_pig_records))} / ${escapeHtml(countText(litter.exited_pig_records))}</td>
        <td>${escapeHtml(attentionLabel(litter))}</td>
        <td><a class="small-action-button" href="/litter/${encodeURIComponent(litter.litter_id)}?return_to=${encodeURIComponent("/litters")}&return_label=${encodeURIComponent("Back to Litters")}">Review</a></td>
      </tr>
    `;
  }).join("");
}

async function loadLitters() {
  clearLittersMessage();
  try {
    const response = await fetch("/api/pig-weights/litters");
    const data = await response.json();
    if (!response.ok || !data.success) {
      throw new Error(data.error || "Could not load litters.");
    }
    littersState = data.litters || [];
    littersTotal.textContent = data.count ?? littersState.length;
    littersAttention.textContent = data.attention_count ?? "-";
    littersMismatch.textContent = data.mismatch_count ?? "-";
    littersFormulaConflict.textContent = data.formula_conflict_count ?? "-";
    renderLitters();
  } catch (error) {
    showLittersMessage(error.message || "Could not load litters.");
    littersTableBody.innerHTML = `<tr><td colspan="7" class="table-empty">Litter data could not be loaded.</td></tr>`;
  }
}

littersSearch.addEventListener("input", renderLitters);
littersFilter.addEventListener("change", renderLitters);

loadLitters();
