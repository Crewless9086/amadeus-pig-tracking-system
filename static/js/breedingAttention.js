const body = document.getElementById("attention_body");
const filter = document.getElementById("attention_filter");
const counts = document.getElementById("attention_counts");
const freshness = document.getElementById("attention_freshness");
const message = document.getElementById("attention_message");
let rows = [];

function escapeHtml(value) {
  return String(value ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;")
    .replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
}
function render() {
  const selected = filter.value;
  const visible = selected ? rows.filter(row => row.filter_state === selected) : rows;
  body.innerHTML = visible.length ? visible.map(row => {
    const dates = row.evidence_dates || {};
    const facts = [...(row.missing_facts || []), ...(row.conflicting_facts || [])];
    return `<tr><td><a class="detail-link" href="${escapeHtml(row.animal_href)}">${escapeHtml(row.tag_number || row.pig_id)}</a></td>
      <td>${escapeHtml(row.current_state)}</td><td>Mating: ${escapeHtml(dates.latest_mating || "Unknown")}<br>Litter: ${escapeHtml(dates.latest_litter || "Unknown")}</td>
      <td>${escapeHtml(row.freshness || "Unknown")}</td><td>${escapeHtml(row.confidence || "Unknown")}</td>
      <td>${escapeHtml(facts.join("; ") || "None evidenced")}</td><td>${escapeHtml(row.recommended_human_action)}</td></tr>`;
  }).join("") : `<tr><td colspan="7" class="table-empty">No animals in this attention state.</td></tr>`;
}
async function load() {
  try {
    const response = await fetch("/api/pig-weights/breeding-attention");
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.limitations?.[0] || "Breeding evidence unavailable.");
    rows = data.animals || [];
    filter.innerHTML += (data.filters || []).map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    counts.innerHTML = (data.filters || []).map(name => `<div><span class="info-title">${escapeHtml(name)}: </span><span class="info-value">${escapeHtml(data.counts?.[name] ?? "Unknown")}</span></div>`).join("");
    freshness.textContent = `Evidence: ${data.source_status}; observed ${data.observation_timestamp || "Unknown"}.`;
    render();
  } catch (error) {
    rows = []; counts.innerHTML = "";
    freshness.textContent = "Evidence unavailable — counts are not zero.";
    message.classList.remove("hidden"); message.textContent = error.message;
    body.innerHTML = `<tr><td colspan="7" class="table-empty">Needs Data — canonical evidence unavailable.</td></tr>`;
  }
}
filter.addEventListener("change", render);
document.addEventListener("DOMContentLoaded", load);
