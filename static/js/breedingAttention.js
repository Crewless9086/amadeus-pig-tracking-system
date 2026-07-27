const body = document.getElementById("attention_body");
const filter = document.getElementById("attention_filter");
const counts = document.getElementById("attention_counts");
const freshness = document.getElementById("attention_freshness");
const message = document.getElementById("attention_message");
let rows = [];
let activeRow = null;
let acceptedPreviewPayload = null;

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
      <td>${escapeHtml(facts.join("; ") || "None evidenced")}</td><td>${escapeHtml(row.recommended_human_action)}</td>
      <td><button type="button" class="secondary-button observation-review" data-pig-id="${escapeHtml(row.pig_id)}">Details / Observe</button></td></tr>`;
  }).join("") : `<tr><td colspan="8" class="table-empty">No animals in this attention state.</td></tr>`;
}
async function load() {
  try {
    const response = await fetch("/api/pig-weights/breeding-attention");
    const data = await response.json();
    if (!response.ok || !data.success) throw new Error(data.limitations?.[0] || "Breeding evidence unavailable.");
    rows = data.animals || [];
    filter.innerHTML = `<option value="">All current sows and gilts</option>` +
      (data.filters || []).map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
    counts.innerHTML = (data.filters || []).map(name => `<div><span class="info-title">${escapeHtml(name)}: </span><span class="info-value">${escapeHtml(data.counts?.[name] ?? "Unknown")}</span></div>`).join("");
    freshness.textContent = `Evidence: ${data.source_status}; observed ${data.observation_timestamp || "Unknown"}.`;
    render();
  } catch (error) {
    rows = []; counts.innerHTML = "";
    freshness.textContent = "Evidence unavailable — counts are not zero.";
    message.classList.remove("hidden"); message.textContent = error.message;
    body.innerHTML = `<tr><td colspan="8" class="table-empty">Needs Data — canonical evidence unavailable.</td></tr>`;
  }
}
filter.addEventListener("change", render);
document.addEventListener("DOMContentLoaded", load);

const panel = document.getElementById("observation_panel");
const history = document.getElementById("observation_history");
const previewBox = document.getElementById("observation_preview");
const recordButton = document.getElementById("obs_record");
function localNow() {
  const value = new Date(Date.now() - new Date().getTimezoneOffset() * 60000);
  return value.toISOString().slice(0, 16);
}
function observationPayload(idempotencyKey) {
  return {
    observed_at: new Date(document.getElementById("obs_time").value).toISOString(),
    body_condition_score: document.getElementById("obs_bcs").value || null,
    visible_build: document.getElementById("obs_build").value,
    feet_legs_movement: document.getElementById("obs_legs").value,
    visible_injury: document.getElementById("obs_injury").value,
    standing_heat: document.getElementById("obs_heat").value,
    temperament: document.getElementById("obs_temperament").value,
    suitability_concern: document.getElementById("obs_suitability").value,
    factual_note: document.getElementById("obs_note").value,
    follow_up: document.getElementById("obs_follow_up").value,
    idempotency_key: idempotencyKey,
  };
}
async function openObservation(pigId) {
  activeRow = rows.find(row => row.pig_id === pigId);
  if (!activeRow) return;
  acceptedPreviewPayload = null; recordButton.disabled = true;
  panel.classList.remove("hidden");
  document.getElementById("observation_heading").textContent = `Factual observation — ${activeRow.tag_number || activeRow.pig_id}`;
  document.getElementById("observation_context").textContent = `${activeRow.current_state}; missing: ${(activeRow.missing_facts || []).join(", ") || "none"}.`;
  document.getElementById("obs_time").value = localNow();
  previewBox.classList.add("hidden");
  const response = await fetch(`/api/pig-weights/breeding-attention/${encodeURIComponent(pigId)}/observations`);
  const data = await response.json();
  history.textContent = response.ok && data.success
    ? (data.history.length ? `${data.history.length} immutable observation(s); latest ${data.history[0].observed_at}.` : "No breeding observations recorded.")
    : "Observation history unavailable — not zero.";
  panel.scrollIntoView({behavior:"smooth", block:"start"});
}
body.addEventListener("click", event => {
  const button = event.target.closest(".observation-review");
  if (button) openObservation(button.dataset.pigId);
});
document.getElementById("observation_close").addEventListener("click", () => panel.classList.add("hidden"));
document.getElementById("obs_preview").addEventListener("click", async () => {
  if (!activeRow) return;
  const payload = observationPayload(crypto.randomUUID());
  const response = await fetch(`/api/pig-weights/breeding-attention/${encodeURIComponent(activeRow.pig_id)}/observations/preview`, {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)
  });
  const data = await response.json();
  acceptedPreviewPayload = response.ok && data.success ? payload : null;
  recordButton.disabled = !acceptedPreviewPayload;
  previewBox.classList.remove("hidden");
  const change = data.system_recommendation?.advisory_change;
  previewBox.textContent = acceptedPreviewPayload
    ? `Observed: factual evidence only. Interpretation: ${data.owner_interpretation} Effect: ${data.system_recommendation.effect.join(" ")} Before: ${change.before.state} — ${change.before.recommended_human_action}. If recorded: ${change.after_if_recorded.state} — ${change.after_if_recorded.recommended_human_action}. Current advice remains unchanged until recording.`
    : (data.status || "Preview unavailable.");
});
document.getElementById("observation_form").addEventListener("input", () => {
  acceptedPreviewPayload = null; recordButton.disabled = true;
});
document.getElementById("observation_form").addEventListener("submit", async event => {
  event.preventDefault();
  if (!activeRow || !acceptedPreviewPayload) return;
  const payload = {...acceptedPreviewPayload};
  const response = await fetch(`/api/pig-weights/breeding-attention/${encodeURIComponent(activeRow.pig_id)}/observations`, {
    method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)
  });
  const data = await response.json();
  acceptedPreviewPayload = null; recordButton.disabled = true;
  previewBox.classList.remove("hidden");
  previewBox.textContent = response.ok ? "Observation appended once. Refreshing advisory evidence." : (data.status || "Observation was not recorded.");
  if (response.ok) await load();
});
